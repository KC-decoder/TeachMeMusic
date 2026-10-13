"""Deterministic expected-performance alignment and factual observations."""

from __future__ import annotations

import hashlib
import json
from collections import defaultdict, deque
from dataclasses import dataclass, replace

from .contracts import (
    AttemptCompletion,
    CalibrationProfile,
    EvidenceConfidence,
    LearnerAttempt,
    MidiEventKind,
    NormalizedMidiEvent,
    Observation,
    ObservationDimension,
    ObservationSource,
    ObservationStatus,
    PerformanceBundle,
)
from .validation import (
    PerformanceValidationError,
    is_stable_id,
    require_valid_performance_bundle,
)

ALIGNMENT_POLICY_VERSION = "deterministic-alignment-v1"
LAYER_ALIGNMENT_POLICY_VERSION = "curriculum-layer-alignment-v1"
COMBINED_LAYER_ALIGNMENT_POLICY_VERSION = "curriculum-combined-layer-alignment-v1"
_UNTIMED_MODES = {"ear-first", "follow-pitch"}
_PRACTICE_MODES = {
    "listen",
    "ear-first",
    "follow-pitch",
    "pulse-guided",
    "supported-performance",
    "independent-performance",
    "retention",
    "transfer",
}


class AttemptAlignmentError(ValueError):
    """Raised when an alignment request violates the performance boundary."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(f"{code}: {message}")


@dataclass(frozen=True, slots=True)
class ExpectedLayerMembership:
    """One canonical note source retained inside its component layer."""

    expected_id: str
    component_scope_id: str
    component_scope_fingerprint: str
    notation_condition: str


@dataclass(frozen=True, slots=True)
class ExpectedPerformanceNote:
    """One expected sounding note projected from verified exercise playback."""

    id: str
    start_microseconds: int
    end_microseconds: int
    midi_pitch: int
    expected_ids: tuple[str, ...]
    chord_id: str | None = None
    layers: tuple[str, ...] = ()
    layer_memberships: tuple[ExpectedLayerMembership, ...] = ()


@dataclass(frozen=True, slots=True)
class ExpectedLayerComponent:
    """One resolved component retained by a combined comparison target."""

    presentation_id: str
    presentation_fingerprint: str
    practice_scope_id: str
    practice_scope_fingerprint: str
    notation_condition: str
    execution_assignment: str
    active_event_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ExpectedLayerTarget:
    """Exact curriculum layer whose played evidence may be compared."""

    presentation_id: str
    presentation_fingerprint: str
    practice_scope_id: str
    practice_scope_fingerprint: str
    notation_condition: str
    execution_assignment: str
    active_event_ids: tuple[str, ...]
    inactive_event_ids: tuple[str, ...]
    semantic_fingerprint: str
    components: tuple[ExpectedLayerComponent, ...] = ()


@dataclass(frozen=True, slots=True)
class ExpectedPerformance:
    """MIDI-neutral expected facts for one exercise and practice mode."""

    exercise_id: str
    practice_mode: str
    notes: tuple[ExpectedPerformanceNote, ...]
    target_dimensions: tuple[ObservationDimension, ...]
    source_contract_version: str
    layer_target: ExpectedLayerTarget | None = None


@dataclass(frozen=True, slots=True)
class _PlayedNote:
    on: NormalizedMidiEvent
    off: NormalizedMidiEvent | None = None


@dataclass(frozen=True, slots=True)
class _Pair:
    expected_index: int | None
    played_index: int | None


class _ObservationBuilder:
    def __init__(self, attempt: LearnerAttempt, policy_version: str) -> None:
        self.attempt = attempt
        self.policy_version = policy_version
        self.items: list[Observation] = []
        self.counts: dict[ObservationDimension, int] = defaultdict(int)

    def add(
        self,
        dimension: ObservationDimension,
        status: ObservationStatus,
        *,
        expected_ids: tuple[str, ...] = (),
        observed_ids: tuple[str, ...] = (),
        expected_value: str | None = None,
        observed_value: str | None = None,
        measured_value: str | None = None,
        confidence: EvidenceConfidence = EvidenceConfidence.HIGH,
        blocking: bool = False,
        limitations: tuple[str, ...] = (),
        policy_suffix: str,
    ) -> None:
        index = self.counts[dimension]
        self.counts[dimension] += 1
        attempt_token = self.attempt.id.split(":", 1)[-1]
        self.items.append(
            Observation(
                id=f"observation:{attempt_token}:{dimension.value}:{index}",
                attempt_id=self.attempt.id,
                exercise_id=self.attempt.exercise_id,
                dimension=dimension,
                status=status,
                source=ObservationSource.MIDI,
                expected_canonical_ids=tuple(dict.fromkeys(expected_ids)),
                observed_event_ids=tuple(dict.fromkeys(observed_ids)),
                expected_value=expected_value,
                observed_value=observed_value,
                measured_value=measured_value,
                matching_policy=f"{self.policy_version}:{policy_suffix}",
                confidence=confidence,
                blocking=blocking,
                limitations=limitations,
            )
        )


def align_attempt(
    expected: ExpectedPerformance,
    attempt: LearnerAttempt,
    calibration: CalibrationProfile,
) -> tuple[Observation, ...]:
    """Align one complete attempt without scoring or teaching judgment."""

    _require_valid_request(expected, attempt, calibration)
    policy_version = ALIGNMENT_POLICY_VERSION
    if expected.layer_target is not None:
        layer_policy_version = LAYER_ALIGNMENT_POLICY_VERSION
        if expected.layer_target.notation_condition == "combined":
            layer_policy_version = COMBINED_LAYER_ALIGNMENT_POLICY_VERSION
        policy_version = f"{layer_policy_version}:{expected.layer_target.semantic_fingerprint}"
    builder = _ObservationBuilder(attempt, policy_version)
    invalid_reasons = _input_invalid_reasons(attempt, calibration)
    if invalid_reasons:
        builder.add(
            ObservationDimension.INPUT,
            ObservationStatus.INVALID_INPUT,
            expected_value="approved complete calibrated attempt",
            observed_value="; ".join(invalid_reasons),
            confidence=EvidenceConfidence.HIGH,
            blocking=True,
            limitations=("No musical comparison was inferred from invalid input.",),
            policy_suffix="input",
        )
        return tuple(builder.items)

    diagnostic_limitations = tuple(attempt.diagnostics)
    builder.add(
        ObservationDimension.INPUT,
        ObservationStatus.AMBIGUOUS if diagnostic_limitations else ObservationStatus.MATCH,
        expected_value="approved complete calibrated attempt without unresolved diagnostics",
        observed_value=(
            "completed with diagnostics" if diagnostic_limitations else "completed and calibrated"
        ),
        confidence=(EvidenceConfidence.LOW if diagnostic_limitations else EvidenceConfidence.HIGH),
        blocking=bool(diagnostic_limitations),
        limitations=diagnostic_limitations,
        policy_suffix="input",
    )

    played, unmatched_offs = _played_notes(attempt)
    pairs = _sequence_alignment(expected.notes, played)
    ambiguous_groups = _ambiguous_expected_groups(expected.notes)
    ambiguous_expected = {index for group in ambiguous_groups for index in group}
    ambiguous_played = {
        pair.played_index
        for pair in pairs
        if pair.expected_index in ambiguous_expected and pair.played_index is not None
    }

    for group in ambiguous_groups:
        observed = tuple(
            played[pair.played_index].on.id
            for pair in pairs
            if pair.expected_index in group and pair.played_index is not None
        )
        pitches = ",".join(str(expected.notes[index].midi_pitch) for index in group)
        builder.add(
            ObservationDimension.PITCH,
            ObservationStatus.AMBIGUOUS,
            expected_ids=_expected_ids(expected.notes, group),
            observed_ids=observed,
            expected_value=f"overlapping-midi-instances:{pitches}",
            observed_value="MIDI cannot identify which overlapping canonical instance sounded",
            confidence=EvidenceConfidence.UNKNOWN,
            blocking=True,
            limitations=(
                "Overlapping equal-pitch canonical notes have no independent MIDI identity.",
            ),
            policy_suffix="identity",
        )

    exact_pairs: dict[int, int] = {}
    expected_pitch_counts: dict[int, int] = defaultdict(int)
    total_played_pitch_counts: dict[int, int] = defaultdict(int)
    for expected_item in expected.notes:
        expected_pitch_counts[expected_item.midi_pitch] += 1
    for played_item in played:
        assert played_item.on.note is not None
        total_played_pitch_counts[played_item.on.note] += 1

    for pair in pairs:
        if pair.expected_index in ambiguous_expected or pair.played_index in ambiguous_played:
            continue
        expected_note = (
            expected.notes[pair.expected_index] if pair.expected_index is not None else None
        )
        played_note = played[pair.played_index] if pair.played_index is not None else None
        if expected_note is not None and played_note is not None:
            assert played_note.on.note is not None
            exact = expected_note.midi_pitch == played_note.on.note
            if exact:
                assert pair.expected_index is not None and pair.played_index is not None
                exact_pairs[pair.expected_index] = pair.played_index
            builder.add(
                ObservationDimension.PITCH,
                ObservationStatus.MATCH if exact else ObservationStatus.DISCREPANCY,
                expected_ids=expected_note.expected_ids,
                observed_ids=(played_note.on.id,),
                expected_value=f"midi:{expected_note.midi_pitch}",
                observed_value=(
                    f"midi:{played_note.on.note}"
                    if exact
                    else f"substituted-midi:{played_note.on.note}"
                ),
                confidence=EvidenceConfidence.HIGH,
                blocking=not exact,
                policy_suffix="pitch-sequence",
            )
        elif expected_note is not None:
            builder.add(
                ObservationDimension.PITCH,
                ObservationStatus.DISCREPANCY,
                expected_ids=expected_note.expected_ids,
                expected_value=f"midi:{expected_note.midi_pitch}",
                observed_value="missing",
                confidence=EvidenceConfidence.HIGH,
                blocking=True,
                policy_suffix="pitch-sequence",
            )
        elif played_note is not None:
            assert played_note.on.note is not None
            repeated = (
                expected_pitch_counts.get(played_note.on.note, 0) > 0
                and total_played_pitch_counts[played_note.on.note]
                > expected_pitch_counts[played_note.on.note]
            )
            builder.add(
                ObservationDimension.PITCH,
                ObservationStatus.DISCREPANCY,
                observed_ids=(played_note.on.id,),
                expected_value="no unmatched played note",
                observed_value=(
                    f"repeated-midi:{played_note.on.note}"
                    if repeated
                    else f"extra-unmatched-midi:{played_note.on.note}"
                ),
                confidence=EvidenceConfidence.HIGH,
                blocking=True,
                policy_suffix="pitch-sequence",
            )

    _add_order_observation(builder, expected, played)
    _add_timing_observations(builder, expected, played, exact_pairs, attempt, calibration)
    _add_release_observations(builder, expected, played, exact_pairs, unmatched_offs)
    _add_chord_observations(builder, expected, played, pairs, calibration)
    _add_layer_observations(builder, expected, played, pairs)
    _add_continuity_observation(builder, expected, played, exact_pairs)
    _add_velocity_observation(builder, played)
    _add_pedal_observation(builder, expected, attempt, calibration)

    result = tuple(builder.items)
    try:
        require_valid_performance_bundle(
            PerformanceBundle(
                calibrations=(calibration,),
                attempts=(attempt,),
                observations=result,
            )
        )
    except PerformanceValidationError as error:
        raise AttemptAlignmentError("PERF_ALIGNMENT_RESULT", str(error)) from error
    return result


def expected_layer_target_fingerprint(target: ExpectedLayerTarget) -> str:
    """Return the deterministic semantic identity for one layer target."""

    payload: dict[str, object] = {
        "presentation_id": target.presentation_id,
        "presentation_fingerprint": target.presentation_fingerprint,
        "practice_scope_id": target.practice_scope_id,
        "practice_scope_fingerprint": target.practice_scope_fingerprint,
        "notation_condition": target.notation_condition,
        "execution_assignment": target.execution_assignment,
        "active_event_ids": list(target.active_event_ids),
        "inactive_event_ids": list(target.inactive_event_ids),
    }
    if target.components:
        payload["components"] = [
            {
                "presentation_id": item.presentation_id,
                "presentation_fingerprint": item.presentation_fingerprint,
                "practice_scope_id": item.practice_scope_id,
                "practice_scope_fingerprint": item.practice_scope_fingerprint,
                "notation_condition": item.notation_condition,
                "execution_assignment": item.execution_assignment,
                "active_event_ids": list(item.active_event_ids),
            }
            for item in target.components
        ]
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def align_layer_attempt(
    expected: ExpectedPerformance,
    attempt: LearnerAttempt,
    calibration: CalibrationProfile,
) -> tuple[Observation, ...]:
    """Align an attempt only when it is bound to one exact written-layer target."""

    if expected.layer_target is None:
        raise AttemptAlignmentError(
            "PERF_ALIGNMENT_LAYER_TARGET",
            "an exact written-layer target is required",
        )
    return align_attempt(expected, attempt, calibration)


def _require_valid_request(
    expected: ExpectedPerformance,
    attempt: LearnerAttempt,
    calibration: CalibrationProfile,
) -> None:
    if not is_stable_id(expected.exercise_id) or expected.exercise_id != attempt.exercise_id:
        raise AttemptAlignmentError(
            "PERF_ALIGNMENT_EXERCISE", "expected performance and attempt differ"
        )
    if expected.practice_mode != attempt.practice_mode:
        raise AttemptAlignmentError(
            "PERF_ALIGNMENT_MODE", "expected performance and attempt use different modes"
        )
    if expected.practice_mode not in _PRACTICE_MODES:
        raise AttemptAlignmentError(
            "PERF_ALIGNMENT_MODE", "expected performance mode is unsupported"
        )
    if expected.practice_mode in {"listen"}:
        raise AttemptAlignmentError(
            "PERF_ALIGNMENT_NONPERFORMANCE_MODE", "listen mode has no played attempt"
        )
    if not expected.source_contract_version:
        raise AttemptAlignmentError(
            "PERF_ALIGNMENT_SOURCE_VERSION", "expected source version is missing"
        )
    if not expected.notes:
        raise AttemptAlignmentError("PERF_ALIGNMENT_EXPECTED", "expected note sequence is empty")
    _require_valid_layer_target(expected)
    if len(set(expected.target_dimensions)) != len(expected.target_dimensions):
        raise AttemptAlignmentError(
            "PERF_ALIGNMENT_DIMENSION", "target observation dimensions repeat"
        )
    if any(not isinstance(item, ObservationDimension) for item in expected.target_dimensions):
        raise AttemptAlignmentError(
            "PERF_ALIGNMENT_DIMENSION", "target observation dimension is unsupported"
        )
    previous: tuple[int, int, int, str] | None = None
    note_ids: set[str] = set()
    for note in expected.notes:
        if not note.id or note.id in note_ids:
            raise AttemptAlignmentError(
                "PERF_ALIGNMENT_EXPECTED_ID", "expected note identity is empty or duplicated"
            )
        note_ids.add(note.id)
        if not 0 <= note.start_microseconds < note.end_microseconds:
            raise AttemptAlignmentError(
                "PERF_ALIGNMENT_EXPECTED_TIME", "expected note has an invalid time range"
            )
        if (
            not 0 <= note.midi_pitch <= 127
            or not note.expected_ids
            or any(not is_stable_id(identifier) for identifier in note.expected_ids)
        ):
            raise AttemptAlignmentError(
                "PERF_ALIGNMENT_EXPECTED_NOTE", "expected note lacks pitch or source identity"
            )
        key = (note.start_microseconds, note.midi_pitch, note.end_microseconds, note.id)
        if previous is not None and key < previous:
            raise AttemptAlignmentError(
                "PERF_ALIGNMENT_EXPECTED_ORDER", "expected notes are not ordered"
            )
        previous = key
    try:
        require_valid_performance_bundle(
            PerformanceBundle(calibrations=(calibration,), attempts=(attempt,))
        )
    except PerformanceValidationError as error:
        raise AttemptAlignmentError("PERF_ALIGNMENT_INPUT_CONTRACT", str(error)) from error


def _require_valid_layer_target(expected: ExpectedPerformance) -> None:
    target = expected.layer_target
    if target is None:
        return
    if target.notation_condition not in {
        "single-layer",
        "upper-layer",
        "lower-layer",
        "combined",
    }:
        raise AttemptAlignmentError(
            "PERF_ALIGNMENT_LAYER_CONDITION",
            "layer target notation condition is unsupported",
        )
    for identifier in (target.presentation_id, target.practice_scope_id):
        if not is_stable_id(identifier):
            raise AttemptAlignmentError(
                "PERF_ALIGNMENT_LAYER_REFERENCE",
                "layer target references must be stable namespaced identities",
            )
    if target.execution_assignment not in {
        "unassigned",
        "right-hand",
        "left-hand",
        "both-hands",
    }:
        raise AttemptAlignmentError(
            "PERF_ALIGNMENT_LAYER_ASSIGNMENT",
            "layer target execution assignment is unsupported",
        )
    if not target.active_event_ids or len(set(target.active_event_ids)) != len(
        target.active_event_ids
    ):
        raise AttemptAlignmentError(
            "PERF_ALIGNMENT_LAYER_ACTIVE",
            "layer target active identities are empty or duplicated",
        )
    if len(set(target.inactive_event_ids)) != len(target.inactive_event_ids):
        raise AttemptAlignmentError(
            "PERF_ALIGNMENT_LAYER_INACTIVE",
            "layer target inactive identities repeat",
        )
    if any(
        not is_stable_id(identifier)
        for identifier in (*target.active_event_ids, *target.inactive_event_ids)
    ):
        raise AttemptAlignmentError(
            "PERF_ALIGNMENT_LAYER_EVENT_ID",
            "layer target event identities must be stable",
        )
    active = set(target.active_event_ids)
    inactive = set(target.inactive_event_ids)
    if active & inactive:
        raise AttemptAlignmentError(
            "PERF_ALIGNMENT_LAYER_OVERLAP",
            "active and inactive layer identities overlap",
        )
    _require_valid_layer_components(target, active)
    fingerprints = (
        target.presentation_fingerprint,
        target.practice_scope_fingerprint,
        target.semantic_fingerprint,
    )
    if any(
        len(value) != 64 or any(char not in "0123456789abcdef" for char in value)
        for value in fingerprints
    ):
        raise AttemptAlignmentError(
            "PERF_ALIGNMENT_LAYER_FINGERPRINT",
            "layer target fingerprints must be lowercase SHA-256 values",
        )
    if target.semantic_fingerprint != expected_layer_target_fingerprint(target):
        raise AttemptAlignmentError(
            "PERF_ALIGNMENT_LAYER_FINGERPRINT",
            "layer target semantic fingerprint does not match its contents",
        )
    if expected.exercise_id != f"curriculum-layer-attempt:{target.semantic_fingerprint}":
        raise AttemptAlignmentError(
            "PERF_ALIGNMENT_LAYER_EXERCISE",
            "attempt target identity does not match the written-layer target",
        )
    expected_source_ids = {
        identifier for note in expected.notes for identifier in note.expected_ids
    }
    if not expected_source_ids <= active or expected_source_ids & inactive:
        raise AttemptAlignmentError(
            "PERF_ALIGNMENT_LAYER_LEAK",
            "expected notes contain canonical identities outside the active layer",
        )
    _require_valid_note_memberships(expected)


def _require_valid_layer_components(
    target: ExpectedLayerTarget,
    active: set[str],
) -> None:
    components = target.components
    if target.notation_condition != "combined":
        if components:
            raise AttemptAlignmentError(
                "PERF_ALIGNMENT_COMPONENT_UNEXPECTED",
                "an isolated layer target cannot declare component scopes",
            )
        return
    if len(components) < 2:
        raise AttemptAlignmentError(
            "PERF_ALIGNMENT_COMPONENT_COUNT",
            "a combined layer target requires at least two components",
        )
    component_ids = tuple(item.practice_scope_id for item in components)
    if len(set(component_ids)) != len(component_ids):
        raise AttemptAlignmentError(
            "PERF_ALIGNMENT_COMPONENT_DUPLICATE",
            "combined component scope identity repeats",
        )
    component_events: list[set[str]] = []
    for component in components:
        if component.notation_condition not in {
            "single-layer",
            "upper-layer",
            "lower-layer",
        }:
            raise AttemptAlignmentError(
                "PERF_ALIGNMENT_COMPONENT_CONDITION",
                "combined component notation condition is unsupported",
            )
        if component.execution_assignment not in {
            "unassigned",
            "right-hand",
            "left-hand",
            "both-hands",
        }:
            raise AttemptAlignmentError(
                "PERF_ALIGNMENT_COMPONENT_ASSIGNMENT",
                "combined component execution assignment is unsupported",
            )
        if not is_stable_id(component.presentation_id) or not is_stable_id(
            component.practice_scope_id
        ):
            raise AttemptAlignmentError(
                "PERF_ALIGNMENT_COMPONENT_REFERENCE",
                "combined component references must be stable identities",
            )
        if any(
            len(value) != 64 or any(char not in "0123456789abcdef" for char in value)
            for value in (
                component.presentation_fingerprint,
                component.practice_scope_fingerprint,
            )
        ):
            raise AttemptAlignmentError(
                "PERF_ALIGNMENT_COMPONENT_FINGERPRINT",
                "combined component fingerprints must be lowercase SHA-256 values",
            )
        if not component.active_event_ids or len(set(component.active_event_ids)) != len(
            component.active_event_ids
        ):
            raise AttemptAlignmentError(
                "PERF_ALIGNMENT_COMPONENT_ACTIVE",
                "combined component active identities are empty or duplicated",
            )
        if any(not is_stable_id(identifier) for identifier in component.active_event_ids):
            raise AttemptAlignmentError(
                "PERF_ALIGNMENT_COMPONENT_EVENT_ID",
                "combined component event identities must be stable",
            )
        component_events.append(set(component.active_event_ids))
    if any(
        left & right
        for index, left in enumerate(component_events)
        for right in component_events[index + 1 :]
    ):
        raise AttemptAlignmentError(
            "PERF_ALIGNMENT_COMPONENT_OVERLAP",
            "combined component event memberships overlap",
        )
    if set().union(*component_events) != active:
        raise AttemptAlignmentError(
            "PERF_ALIGNMENT_COMPONENT_UNION",
            "combined components do not form the exact active target",
        )


def _require_valid_note_memberships(expected: ExpectedPerformance) -> None:
    target = expected.layer_target
    assert target is not None
    if target.notation_condition != "combined":
        if any(note.layer_memberships for note in expected.notes):
            raise AttemptAlignmentError(
                "PERF_ALIGNMENT_MEMBERSHIP_UNEXPECTED",
                "isolated expected notes cannot declare combined memberships",
            )
        return
    components = {item.practice_scope_id: item for item in target.components}
    for note in expected.notes:
        memberships = note.layer_memberships
        if tuple(item.expected_id for item in memberships) != note.expected_ids:
            raise AttemptAlignmentError(
                "PERF_ALIGNMENT_MEMBERSHIP_COVERAGE",
                "combined note memberships do not preserve every source identity in order",
            )
        for membership in memberships:
            component = components.get(membership.component_scope_id)
            if (
                component is None
                or membership.component_scope_fingerprint != component.practice_scope_fingerprint
                or membership.notation_condition != component.notation_condition
                or membership.expected_id not in component.active_event_ids
            ):
                raise AttemptAlignmentError(
                    "PERF_ALIGNMENT_MEMBERSHIP_MISMATCH",
                    "combined note membership differs from its component scope",
                )


def _input_invalid_reasons(
    attempt: LearnerAttempt, calibration: CalibrationProfile
) -> tuple[str, ...]:
    reasons: list[str] = []
    if attempt.calibration_id != calibration.id:
        reasons.append("attempt references another calibration")
    if not calibration.approved:
        reasons.append("calibration is not approved")
    if not calibration.pitch_numbering_confirmed:
        reasons.append("MIDI pitch numbering is not confirmed")
    if attempt.completion is not AttemptCompletion.COMPLETED:
        reasons.append(f"attempt ended as {attempt.completion.value}")
    return tuple(reasons)


def _played_notes(
    attempt: LearnerAttempt,
) -> tuple[tuple[_PlayedNote, ...], tuple[NormalizedMidiEvent, ...]]:
    result: list[_PlayedNote] = []
    active: dict[tuple[int, int], deque[int]] = defaultdict(deque)
    unmatched_offs: list[NormalizedMidiEvent] = []
    for event in attempt.normalized_events:
        if event.kind is MidiEventKind.NOTE_ON:
            assert event.channel is not None and event.note is not None
            result.append(_PlayedNote(event))
            active[(event.channel, event.note)].append(len(result) - 1)
        elif event.kind is MidiEventKind.NOTE_OFF:
            assert event.channel is not None and event.note is not None
            candidates = active[(event.channel, event.note)]
            if candidates:
                index = candidates.popleft()
                result[index] = replace(result[index], off=event)
            else:
                unmatched_offs.append(event)
    return tuple(result), tuple(unmatched_offs)


def _sequence_alignment(
    expected: tuple[ExpectedPerformanceNote, ...],
    played: tuple[_PlayedNote, ...],
) -> tuple[_Pair, ...]:
    rows = len(expected) + 1
    columns = len(played) + 1
    costs = [[0] * columns for _ in range(rows)]
    moves = [[""] * columns for _ in range(rows)]
    for i in range(1, rows):
        costs[i][0] = i
        moves[i][0] = "missing"
    for j in range(1, columns):
        costs[0][j] = j
        moves[0][j] = "extra"
    for i in range(1, rows):
        for j in range(1, columns):
            observed_pitch = played[j - 1].on.note
            substitution = 0 if expected[i - 1].midi_pitch == observed_pitch else 1
            candidates = (
                (costs[i - 1][j - 1] + substitution, 0 if substitution == 0 else 1, "pair"),
                (costs[i - 1][j] + 1, 2, "missing"),
                (costs[i][j - 1] + 1, 3, "extra"),
            )
            cost, _, move = min(candidates)
            costs[i][j] = cost
            moves[i][j] = move
    pairs: list[_Pair] = []
    i = len(expected)
    j = len(played)
    while i or j:
        move = moves[i][j]
        if move == "pair":
            pairs.append(_Pair(i - 1, j - 1))
            i -= 1
            j -= 1
        elif move == "missing":
            pairs.append(_Pair(i - 1, None))
            i -= 1
        else:
            pairs.append(_Pair(None, j - 1))
            j -= 1
    return tuple(reversed(pairs))


def _ambiguous_expected_groups(
    notes: tuple[ExpectedPerformanceNote, ...],
) -> tuple[tuple[int, ...], ...]:
    candidates: dict[int, set[int]] = defaultdict(set)
    for left, left_note in enumerate(notes):
        for right in range(left + 1, len(notes)):
            right_note = notes[right]
            if right_note.start_microseconds >= left_note.end_microseconds:
                break
            if left_note.midi_pitch == right_note.midi_pitch:
                candidates[left].update((left, right))
    groups: list[set[int]] = []
    for values in candidates.values():
        overlapping = [group for group in groups if group & values]
        if not overlapping:
            groups.append(set(values))
        else:
            merged = set(values)
            for group in overlapping:
                merged.update(group)
                groups.remove(group)
            groups.append(merged)
    return tuple(tuple(sorted(group)) for group in sorted(groups, key=min))


def _expected_ids(
    notes: tuple[ExpectedPerformanceNote, ...], indices: tuple[int, ...] | range
) -> tuple[str, ...]:
    return tuple(
        dict.fromkeys(identifier for index in indices for identifier in notes[index].expected_ids)
    )


def _add_order_observation(
    builder: _ObservationBuilder,
    expected: ExpectedPerformance,
    played: tuple[_PlayedNote, ...],
) -> None:
    if ObservationDimension.ORDER not in expected.target_dimensions:
        return
    expected_pitches = tuple(note.midi_pitch for note in expected.notes)
    played_pitches = tuple(note.on.note for note in played)
    matches = expected_pitches == played_pitches
    builder.add(
        ObservationDimension.ORDER,
        ObservationStatus.MATCH if matches else ObservationStatus.DISCREPANCY,
        expected_ids=_expected_ids(expected.notes, range(len(expected.notes))),
        observed_ids=tuple(note.on.id for note in played),
        expected_value="midi-sequence:" + ",".join(map(str, expected_pitches)),
        observed_value="midi-sequence:" + ",".join(map(str, played_pitches)),
        confidence=EvidenceConfidence.HIGH,
        blocking=not matches,
        policy_suffix="order",
    )


def _add_timing_observations(
    builder: _ObservationBuilder,
    expected: ExpectedPerformance,
    played: tuple[_PlayedNote, ...],
    exact_pairs: dict[int, int],
    attempt: LearnerAttempt,
    calibration: CalibrationProfile,
) -> None:
    targets = set(expected.target_dimensions)
    timing_dimensions = targets & {ObservationDimension.ONSET, ObservationDimension.DURATION}
    if not timing_dimensions:
        return
    if expected.practice_mode in _UNTIMED_MODES:
        for dimension in sorted(timing_dimensions, key=lambda item: item.value):
            builder.add(
                dimension,
                ObservationStatus.UNOBSERVABLE,
                expected_ids=_expected_ids(expected.notes, range(len(expected.notes))),
                expected_value="timed comparison",
                observed_value=f"{expected.practice_mode} is untimed",
                confidence=EvidenceConfidence.UNKNOWN,
                blocking=True,
                limitations=("Untimed practice cannot produce valid rhythm evidence.",),
                policy_suffix="timing",
            )
        return
    window = calibration.timing_window_microseconds
    if window is None:
        for dimension in sorted(timing_dimensions, key=lambda item: item.value):
            builder.add(
                dimension,
                ObservationStatus.UNOBSERVABLE,
                expected_ids=_expected_ids(expected.notes, range(len(expected.notes))),
                expected_value="calibrated timed comparison",
                observed_value="timing window is unset",
                confidence=EvidenceConfidence.UNKNOWN,
                blocking=True,
                limitations=("No physical/acoustic timing tolerance was approved by calibration.",),
                policy_suffix="timing",
            )
        return
    for expected_index, expected_note in enumerate(expected.notes):
        played_index = exact_pairs.get(expected_index)
        played_note = played[played_index] if played_index is not None else None
        if ObservationDimension.ONSET in timing_dimensions:
            if played_note is None:
                builder.add(
                    ObservationDimension.ONSET,
                    ObservationStatus.DISCREPANCY,
                    expected_ids=expected_note.expected_ids,
                    expected_value=f"onset-microseconds:{expected_note.start_microseconds}",
                    observed_value="missing",
                    confidence=EvidenceConfidence.HIGH,
                    blocking=True,
                    policy_suffix="onset",
                )
            else:
                observed_onset = played_note.on.timestamp_microseconds - attempt.start_microseconds
                delta = observed_onset - expected_note.start_microseconds
                within = abs(delta) <= window
                builder.add(
                    ObservationDimension.ONSET,
                    ObservationStatus.MATCH if within else ObservationStatus.DISCREPANCY,
                    expected_ids=expected_note.expected_ids,
                    observed_ids=(played_note.on.id,),
                    expected_value=f"onset-microseconds:{expected_note.start_microseconds}",
                    observed_value=(
                        f"within-window:{observed_onset}"
                        if within
                        else f"{'late' if delta > 0 else 'early'}:{observed_onset}"
                    ),
                    measured_value=f"signed-delta-microseconds:{delta}",
                    confidence=EvidenceConfidence.HIGH,
                    blocking=not within,
                    policy_suffix="onset",
                )
        if ObservationDimension.DURATION in timing_dimensions:
            expected_duration = expected_note.end_microseconds - expected_note.start_microseconds
            if played_note is None or played_note.off is None:
                observed_ids = () if played_note is None else (played_note.on.id,)
                builder.add(
                    ObservationDimension.DURATION,
                    ObservationStatus.DISCREPANCY,
                    expected_ids=expected_note.expected_ids,
                    observed_ids=observed_ids,
                    expected_value=f"duration-microseconds:{expected_duration}",
                    observed_value="missing" if played_note is None else "interrupted-no-release",
                    confidence=EvidenceConfidence.HIGH,
                    blocking=True,
                    policy_suffix="duration",
                )
            else:
                observed_duration = (
                    played_note.off.timestamp_microseconds - played_note.on.timestamp_microseconds
                )
                delta = observed_duration - expected_duration
                within = abs(delta) <= window
                builder.add(
                    ObservationDimension.DURATION,
                    ObservationStatus.MATCH if within else ObservationStatus.DISCREPANCY,
                    expected_ids=expected_note.expected_ids,
                    observed_ids=(played_note.on.id, played_note.off.id),
                    expected_value=f"duration-microseconds:{expected_duration}",
                    observed_value=(
                        f"within-window:{observed_duration}"
                        if within
                        else f"{'long' if delta > 0 else 'short'}:{observed_duration}"
                    ),
                    measured_value=f"signed-delta-microseconds:{delta}",
                    confidence=EvidenceConfidence.HIGH,
                    blocking=not within,
                    policy_suffix="duration",
                )


def _add_release_observations(
    builder: _ObservationBuilder,
    expected: ExpectedPerformance,
    played: tuple[_PlayedNote, ...],
    exact_pairs: dict[int, int],
    unmatched_offs: tuple[NormalizedMidiEvent, ...],
) -> None:
    for expected_index, expected_note in enumerate(expected.notes):
        played_index = exact_pairs.get(expected_index)
        if played_index is None:
            continue
        played_note = played[played_index]
        released = played_note.off is not None
        builder.add(
            ObservationDimension.RELEASE,
            ObservationStatus.MATCH if released else ObservationStatus.DISCREPANCY,
            expected_ids=expected_note.expected_ids,
            observed_ids=(
                (played_note.on.id, played_note.off.id)
                if played_note.off is not None
                else (played_note.on.id,)
            ),
            expected_value="matched-note-off",
            observed_value="released" if released else "interrupted-no-release",
            measured_value=(
                "held-microseconds:"
                f"{played_note.off.timestamp_microseconds - played_note.on.timestamp_microseconds}"
                if played_note.off is not None
                else None
            ),
            confidence=EvidenceConfidence.HIGH,
            blocking=not released,
            policy_suffix="release",
        )
    for event in unmatched_offs:
        builder.add(
            ObservationDimension.RELEASE,
            ObservationStatus.DISCREPANCY,
            observed_ids=(event.id,),
            expected_value="note-off paired with a prior note-on",
            observed_value=f"unmatched-note-off-midi:{event.note}",
            confidence=EvidenceConfidence.HIGH,
            blocking=True,
            policy_suffix="release",
        )


def _add_chord_observations(
    builder: _ObservationBuilder,
    expected: ExpectedPerformance,
    played: tuple[_PlayedNote, ...],
    pairs: tuple[_Pair, ...],
    calibration: CalibrationProfile,
) -> None:
    groups: dict[int, list[int]] = defaultdict(list)
    for index, note in enumerate(expected.notes):
        groups[note.start_microseconds].append(index)
    pair_by_expected = {
        pair.expected_index: pair.played_index
        for pair in pairs
        if pair.expected_index is not None and pair.played_index is not None
    }
    for onset, indices in sorted(groups.items()):
        if len(indices) < 2:
            continue
        expected_ids = _expected_ids(expected.notes, tuple(indices))
        expected_pitches = tuple(sorted(expected.notes[index].midi_pitch for index in indices))
        mapped = tuple(
            played[pair_by_expected[index]]
            for index in indices
            if index in pair_by_expected and pair_by_expected[index] is not None
        )
        mapped_timestamps = tuple(note.on.timestamp_microseconds for note in mapped)
        if calibration.chord_window_microseconds is not None and mapped_timestamps:
            anchor = min(mapped_timestamps)
            grouped = tuple(
                note
                for note in played
                if abs(note.on.timestamp_microseconds - anchor)
                <= calibration.chord_window_microseconds
            )
        else:
            grouped = mapped
        observed_ids = tuple(note.on.id for note in grouped)
        if calibration.chord_window_microseconds is None:
            builder.add(
                ObservationDimension.CHORD_SET,
                ObservationStatus.UNOBSERVABLE,
                expected_ids=expected_ids,
                observed_ids=observed_ids,
                expected_value="midi-multiset:" + ",".join(map(str, expected_pitches)),
                observed_value="chord grouping window is unset",
                confidence=EvidenceConfidence.UNKNOWN,
                blocking=True,
                limitations=("Simultaneous-note grouping was not calibrated.",),
                policy_suffix="chord",
            )
            continue
        observed_pitches = tuple(
            sorted(note.on.note for note in grouped if note.on.note is not None)
        )
        timestamps = tuple(note.on.timestamp_microseconds for note in grouped)
        spread = max(timestamps) - min(timestamps) if timestamps else 0
        matches = (
            expected_pitches == observed_pitches
            and len(grouped) == len(indices)
            and spread <= calibration.chord_window_microseconds
        )
        builder.add(
            ObservationDimension.CHORD_SET,
            ObservationStatus.MATCH if matches else ObservationStatus.DISCREPANCY,
            expected_ids=expected_ids,
            observed_ids=observed_ids,
            expected_value="midi-multiset:" + ",".join(map(str, expected_pitches)),
            observed_value=(
                "midi-multiset:"
                + ",".join(map(str, observed_pitches))
                + (";rolled" if spread > calibration.chord_window_microseconds else "")
            ),
            measured_value=f"spread-microseconds:{spread};expected-onset:{onset}",
            confidence=EvidenceConfidence.HIGH,
            blocking=not matches,
            policy_suffix="chord",
        )


def _add_layer_observations(
    builder: _ObservationBuilder,
    expected: ExpectedPerformance,
    played: tuple[_PlayedNote, ...],
    pairs: tuple[_Pair, ...],
) -> None:
    groups: dict[int, list[int]] = defaultdict(list)
    for index, note in enumerate(expected.notes):
        groups[note.start_microseconds].append(index)
    pair_by_expected = {
        pair.expected_index: pair.played_index
        for pair in pairs
        if pair.expected_index is not None and pair.played_index is not None
    }
    for indices in groups.values():
        layers = tuple(
            dict.fromkeys(layer for index in indices for layer in expected.notes[index].layers)
        )
        if len(layers) < 2:
            continue
        topology = tuple(
            (
                f"midi:{expected.notes[index].midi_pitch}["
                + ",".join(
                    f"{membership.expected_id}@{membership.component_scope_id}"
                    for membership in expected.notes[index].layer_memberships
                )
                + "]"
            )
            for index in indices
        )
        observed_ids = tuple(
            played[pair_by_expected[index]].on.id for index in indices if index in pair_by_expected
        )
        builder.add(
            ObservationDimension.HUMAN_REVIEW,
            ObservationStatus.AMBIGUOUS,
            expected_ids=_expected_ids(expected.notes, tuple(indices)),
            observed_ids=observed_ids,
            expected_value=(
                "canonical-layer-pitches:" + "|".join(topology)
                if all(expected.notes[index].layer_memberships for index in indices)
                else "canonical-layers:" + ",".join(layers)
            ),
            observed_value="MIDI channels do not establish hand, staff, or voice",
            confidence=EvidenceConfidence.UNKNOWN,
            blocking=False,
            limitations=(
                "Expected written-layer identity is preserved per pitch, but MIDI does not "
                "prove which physical hand produced it.",
            ),
            policy_suffix="layer-identity",
        )


def _add_continuity_observation(
    builder: _ObservationBuilder,
    expected: ExpectedPerformance,
    played: tuple[_PlayedNote, ...],
    exact_pairs: dict[int, int],
) -> None:
    if ObservationDimension.CONTINUITY not in expected.target_dimensions:
        return
    missing = len(expected.notes) - len(exact_pairs)
    extra = len(played) - len(exact_pairs)
    interrupted = sum(played[index].off is None for index in exact_pairs.values())
    matches = missing == 0 and extra == 0 and interrupted == 0
    builder.add(
        ObservationDimension.CONTINUITY,
        ObservationStatus.MATCH if matches else ObservationStatus.DISCREPANCY,
        expected_ids=_expected_ids(expected.notes, range(len(expected.notes))),
        observed_ids=tuple(
            event_id
            for note in played
            for event_id in ((note.on.id,) if note.off is None else (note.on.id, note.off.id))
        ),
        expected_value="complete expected sequence without interruption",
        observed_value=f"missing:{missing};extra:{extra};interrupted:{interrupted}",
        confidence=EvidenceConfidence.HIGH,
        blocking=not matches,
        policy_suffix="continuity",
    )


def _add_velocity_observation(
    builder: _ObservationBuilder, played: tuple[_PlayedNote, ...]
) -> None:
    if not played:
        return
    builder.add(
        ObservationDimension.VELOCITY,
        ObservationStatus.AMBIGUOUS,
        observed_ids=tuple(note.on.id for note in played),
        expected_value="no calibrated canonical-to-MIDI velocity target",
        observed_value="midi-velocities:" + ",".join(str(note.on.velocity) for note in played),
        confidence=EvidenceConfidence.HIGH,
        blocking=False,
        limitations=(
            "MIDI velocity is retained but does not establish acoustic tone or dynamics.",
        ),
        policy_suffix="velocity",
    )


def _add_pedal_observation(
    builder: _ObservationBuilder,
    expected: ExpectedPerformance,
    attempt: LearnerAttempt,
    calibration: CalibrationProfile,
) -> None:
    pedal_events = tuple(
        event
        for event in attempt.normalized_events
        if event.kind is MidiEventKind.CONTROL_CHANGE and event.controller == 64
    )
    targeted = ObservationDimension.PEDAL in expected.target_dimensions
    if not pedal_events and not targeted:
        return
    if targeted and (calibration.sustain_available is not True or not pedal_events):
        builder.add(
            ObservationDimension.PEDAL,
            ObservationStatus.UNOBSERVABLE,
            expected_value="canonical pedal comparison",
            observed_value="sustain input was unavailable or unconfirmed",
            confidence=EvidenceConfidence.UNKNOWN,
            blocking=True,
            limitations=("Absent pedal messages cannot prove pedalling.",),
            policy_suffix="pedal",
        )
        return
    builder.add(
        ObservationDimension.PEDAL,
        ObservationStatus.AMBIGUOUS,
        observed_ids=tuple(event.id for event in pedal_events),
        expected_value="no canonical pedal target in expected playback",
        observed_value="controller-64-values:"
        + ",".join(str(event.value) for event in pedal_events),
        confidence=EvidenceConfidence.HIGH,
        blocking=targeted,
        limitations=(
            "Pedal messages are retained, but this expected playback has no pedal timeline.",
        ),
        policy_suffix="pedal",
    )
