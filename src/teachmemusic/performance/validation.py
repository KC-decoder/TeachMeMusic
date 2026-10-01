"""Invariant validation for learner-performance contracts."""

from __future__ import annotations

import re
from dataclasses import dataclass

from .contracts import (
    PERFORMANCE_CONTRACT_ID,
    PERFORMANCE_CONTRACT_VERSION,
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
    RawMidiMessage,
)

_ID_PATTERN = re.compile(r"^[a-z][a-z0-9-]*:[A-Za-z0-9][A-Za-z0-9._:-]*$")


@dataclass(frozen=True, slots=True)
class PerformanceValidationIssue:
    """One stable performance-contract invariant failure."""

    code: str
    path: str
    message: str


class PerformanceValidationError(ValueError):
    """Raised when a performance contract cannot safely cross a boundary."""

    def __init__(self, issues: tuple[PerformanceValidationIssue, ...]) -> None:
        if not issues:
            raise ValueError("at least one validation issue is required")
        self.issues = issues
        super().__init__(
            "; ".join(f"{issue.code} at {issue.path}: {issue.message}" for issue in issues)
        )


def is_stable_id(value: object) -> bool:
    """Return whether a value is a stable namespaced contract identity."""

    return isinstance(value, str) and _ID_PATTERN.fullmatch(value) is not None


def validate_performance_bundle(
    bundle: PerformanceBundle,
) -> tuple[PerformanceValidationIssue, ...]:
    """Return every deterministic performance-contract issue."""

    issues: list[PerformanceValidationIssue] = []
    if bundle.contract_id != PERFORMANCE_CONTRACT_ID:
        _add(issues, "PERF_CONTRACT_ID", "bundle.contract_id", "unsupported contract ID")
    if bundle.contract_version != PERFORMANCE_CONTRACT_VERSION:
        _add(
            issues,
            "PERF_CONTRACT_VERSION",
            "bundle.contract_version",
            "unsupported contract version",
        )
    for field_name in ("calibrations", "attempts", "observations"):
        _tuple(getattr(bundle, field_name), f"bundle.{field_name}", issues)

    calibration_ids = _unique_ids(bundle.calibrations, "bundle.calibrations", issues)
    attempt_ids = _unique_ids(bundle.attempts, "bundle.attempts", issues)
    observation_ids = _unique_ids(bundle.observations, "bundle.observations", issues)
    if (
        calibration_ids & attempt_ids
        or calibration_ids & observation_ids
        or attempt_ids & observation_ids
    ):
        _add(issues, "PERF_GLOBAL_ID_DUPLICATE", "bundle", "IDs must be unique across families")

    for index, calibration in enumerate(bundle.calibrations):
        _validate_calibration(calibration, f"bundle.calibrations[{index}]", issues)

    attempt_event_ids: dict[str, set[str]] = {}
    for index, attempt in enumerate(bundle.attempts):
        path = f"bundle.attempts[{index}]"
        _validate_attempt(attempt, path, calibration_ids, issues)
        attempt_event_ids[attempt.id] = {event.id for event in attempt.normalized_events}

    attempts = {attempt.id: attempt for attempt in bundle.attempts}
    for index, observation in enumerate(bundle.observations):
        path = f"bundle.observations[{index}]"
        _validate_observation(observation, path, attempts, attempt_event_ids, issues)
    return tuple(issues)


def require_valid_performance_bundle(bundle: PerformanceBundle) -> None:
    """Raise if a performance bundle violates any invariant."""

    issues = validate_performance_bundle(bundle)
    if issues:
        raise PerformanceValidationError(issues)


def _validate_calibration(
    value: CalibrationProfile,
    path: str,
    issues: list[PerformanceValidationIssue],
) -> None:
    _id(value.id, f"{path}.id", issues)
    for name in ("version", "device_id", "input_name", "timestamp_origin"):
        _nonempty(getattr(value, name), f"{path}.{name}", issues)
    for name in (
        "clock_offset_microseconds",
        "clock_jitter_microseconds",
        "timing_window_microseconds",
        "chord_window_microseconds",
    ):
        item = getattr(value, name)
        if item is not None and (not isinstance(item, int) or isinstance(item, bool)):
            _add(issues, "PERF_INTEGER", f"{path}.{name}", "expected integer or null")
        elif item is not None and name != "clock_offset_microseconds" and item < 0:
            _add(issues, "PERF_NONNEGATIVE", f"{path}.{name}", "value is negative")
    if not isinstance(value.pitch_numbering_confirmed, bool):
        _add(issues, "PERF_BOOLEAN", f"{path}.pitch_numbering_confirmed", "expected boolean")
    if value.sustain_available is not None and not isinstance(value.sustain_available, bool):
        _add(issues, "PERF_BOOLEAN", f"{path}.sustain_available", "expected boolean or null")
    _tuple(value.limitations, f"{path}.limitations", issues)
    _strings(value.limitations, f"{path}.limitations", issues)
    if value.approved and not value.approved_at_utc:
        _add(issues, "PERF_APPROVAL_TIME", f"{path}.approved_at_utc", "approval time is missing")
    if not value.approved and value.approved_at_utc is not None:
        _add(
            issues,
            "PERF_APPROVAL_STATE",
            f"{path}.approved_at_utc",
            "unapproved calibration cannot have an approval time",
        )


def _validate_attempt(
    attempt: LearnerAttempt,
    path: str,
    calibration_ids: set[str],
    issues: list[PerformanceValidationIssue],
) -> None:
    for name in ("id", "run_id", "exercise_id", "calibration_id", "support_state_id"):
        _id(getattr(attempt, name), f"{path}.{name}", issues)
    for name in ("practice_mode", "started_at_utc"):
        _nonempty(getattr(attempt, name), f"{path}.{name}", issues)
    if not isinstance(attempt.completion, AttemptCompletion):
        _add(issues, "PERF_COMPLETION", f"{path}.completion", "unknown completion state")
    if attempt.calibration_id not in calibration_ids:
        _add(
            issues,
            "PERF_CALIBRATION_REFERENCE",
            f"{path}.calibration_id",
            "calibration does not exist",
        )
    if attempt.start_microseconds < 0 or attempt.end_microseconds < attempt.start_microseconds:
        _add(issues, "PERF_ATTEMPT_TIME", path, "attempt has an invalid monotonic range")
    for field_name in ("raw_messages", "normalized_events", "self_report", "diagnostics"):
        _tuple(getattr(attempt, field_name), f"{path}.{field_name}", issues)
    _strings(attempt.diagnostics, f"{path}.diagnostics", issues)

    raw_ids = _unique_ids(attempt.raw_messages, f"{path}.raw_messages", issues)
    event_ids = _unique_ids(attempt.normalized_events, f"{path}.normalized_events", issues)
    if raw_ids & event_ids:
        _add(issues, "PERF_ATTEMPT_ID_DUPLICATE", path, "raw and normalized IDs overlap")
    previous_raw: tuple[int, int] | None = None
    for index, message in enumerate(attempt.raw_messages):
        message_path = f"{path}.raw_messages[{index}]"
        _validate_raw_message(message, message_path, attempt, issues)
        raw_key = (message.timestamp_microseconds, message.sequence_number)
        if previous_raw is not None and raw_key <= previous_raw:
            _add(issues, "PERF_RAW_ORDER", message_path, "raw messages are not strictly ordered")
        previous_raw = raw_key

    previous_event: tuple[int, str] | None = None
    for index, event in enumerate(attempt.normalized_events):
        event_path = f"{path}.normalized_events[{index}]"
        _validate_event(event, event_path, attempt, raw_ids, issues)
        event_key = (event.timestamp_microseconds, event.id)
        if previous_event is not None and event_key < previous_event:
            _add(issues, "PERF_EVENT_ORDER", event_path, "events are not deterministically ordered")
        previous_event = event_key
    prompt_ids: set[str] = set()
    for index, item in enumerate(attempt.self_report):
        report_path = f"{path}.self_report[{index}]"
        _id(item.prompt_id, f"{report_path}.prompt_id", issues)
        _nonempty(item.response, f"{report_path}.response", issues)
        if item.prompt_id in prompt_ids:
            _add(issues, "PERF_REPORT_DUPLICATE", report_path, "prompt is duplicated")
        prompt_ids.add(item.prompt_id)


def _validate_raw_message(
    message: RawMidiMessage,
    path: str,
    attempt: LearnerAttempt,
    issues: list[PerformanceValidationIssue],
) -> None:
    _id(message.id, f"{path}.id", issues)
    if message.sequence_number < 0:
        _add(issues, "PERF_RAW_SEQUENCE", f"{path}.sequence_number", "sequence is negative")
    if not (
        attempt.start_microseconds <= message.timestamp_microseconds <= attempt.end_microseconds
    ):
        _add(
            issues,
            "PERF_RAW_TIME",
            f"{path}.timestamp_microseconds",
            "message is outside attempt",
        )
    _tuple(message.data, f"{path}.data", issues)
    if not 1 <= len(message.data) <= 3:
        _add(issues, "PERF_RAW_LENGTH", f"{path}.data", "expected one to three MIDI bytes")
    for index, byte in enumerate(message.data):
        if not isinstance(byte, int) or isinstance(byte, bool) or not 0 <= byte <= 255:
            _add(issues, "PERF_MIDI_BYTE", f"{path}.data[{index}]", "byte is outside 0..255")


def _validate_event(
    event: NormalizedMidiEvent,
    path: str,
    attempt: LearnerAttempt,
    raw_ids: set[str],
    issues: list[PerformanceValidationIssue],
) -> None:
    _id(event.id, f"{path}.id", issues)
    if event.raw_message_id is not None:
        _id(event.raw_message_id, f"{path}.raw_message_id", issues)
        if event.raw_message_id not in raw_ids:
            _add(
                issues,
                "PERF_RAW_REFERENCE",
                f"{path}.raw_message_id",
                "raw message does not exist in attempt",
            )
    if not (attempt.start_microseconds <= event.timestamp_microseconds <= attempt.end_microseconds):
        _add(
            issues,
            "PERF_EVENT_TIME",
            f"{path}.timestamp_microseconds",
            "event is outside attempt",
        )
    if not isinstance(event.kind, MidiEventKind):
        _add(issues, "PERF_EVENT_KIND", f"{path}.kind", "unknown event kind")
        return
    if event.channel is not None and not 1 <= event.channel <= 16:
        _add(issues, "PERF_MIDI_CHANNEL", f"{path}.channel", "channel is outside 1..16")
    if event.note is not None and not 0 <= event.note <= 127:
        _add(issues, "PERF_MIDI_NOTE", f"{path}.note", "note is outside 0..127")
    if event.velocity is not None and not 0 <= event.velocity <= 127:
        _add(issues, "PERF_MIDI_VELOCITY", f"{path}.velocity", "velocity is outside 0..127")
    if event.controller is not None and not 0 <= event.controller <= 127:
        _add(issues, "PERF_MIDI_CONTROLLER", f"{path}.controller", "controller is outside 0..127")
    if event.value is not None and not 0 <= event.value <= 127:
        _add(issues, "PERF_MIDI_VALUE", f"{path}.value", "value is outside 0..127")

    if event.kind in {MidiEventKind.NOTE_ON, MidiEventKind.NOTE_OFF}:
        if event.channel is None or event.note is None or event.velocity is None:
            _add(issues, "PERF_NOTE_FIELDS", path, "note event lacks channel, note, or velocity")
        if event.kind is MidiEventKind.NOTE_ON and event.velocity == 0:
            _add(
                issues,
                "PERF_ZERO_VELOCITY_NOTE_ON",
                f"{path}.velocity",
                "velocity-zero note-on must normalize to note-off",
            )
        if event.controller is not None or event.value is not None:
            _add(issues, "PERF_NOTE_FIELDS", path, "note event contains controller fields")
    elif event.kind is MidiEventKind.CONTROL_CHANGE:
        if event.channel is None or event.controller is None or event.value is None:
            _add(issues, "PERF_CONTROL_FIELDS", path, "control event lacks required fields")
        if event.note is not None or event.velocity is not None:
            _add(issues, "PERF_CONTROL_FIELDS", path, "control event contains note fields")
    elif any(
        item is not None
        for item in (event.channel, event.note, event.velocity, event.controller, event.value)
    ):
        _add(issues, "PERF_META_FIELDS", path, "meta event contains MIDI data fields")
    if event.kind in {MidiEventKind.CONNECTION, MidiEventKind.DIAGNOSTIC} and not event.detail:
        _add(issues, "PERF_EVENT_DETAIL", f"{path}.detail", "meta event detail is missing")


def _validate_observation(
    observation: Observation,
    path: str,
    attempts: dict[str, LearnerAttempt],
    attempt_event_ids: dict[str, set[str]],
    issues: list[PerformanceValidationIssue],
) -> None:
    for name in ("id", "attempt_id", "exercise_id"):
        _id(getattr(observation, name), f"{path}.{name}", issues)
    if not isinstance(observation.dimension, ObservationDimension):
        _add(issues, "PERF_OBSERVATION_DIMENSION", f"{path}.dimension", "unknown dimension")
    if not isinstance(observation.status, ObservationStatus):
        _add(issues, "PERF_OBSERVATION_STATUS", f"{path}.status", "unknown status")
    if not isinstance(observation.source, ObservationSource):
        _add(issues, "PERF_OBSERVATION_SOURCE", f"{path}.source", "unknown source")
    if not isinstance(observation.confidence, EvidenceConfidence):
        _add(issues, "PERF_OBSERVATION_CONFIDENCE", f"{path}.confidence", "unknown confidence")
    for field_name in ("expected_canonical_ids", "observed_event_ids", "limitations"):
        values = getattr(observation, field_name)
        _tuple(values, f"{path}.{field_name}", issues)
        _strings(values, f"{path}.{field_name}", issues)
        if len(set(values)) != len(values):
            _add(issues, "PERF_OBSERVATION_DUPLICATE", f"{path}.{field_name}", "values repeat")
    for index, identifier in enumerate(observation.expected_canonical_ids):
        _id(identifier, f"{path}.expected_canonical_ids[{index}]", issues)
    for index, identifier in enumerate(observation.observed_event_ids):
        _id(identifier, f"{path}.observed_event_ids[{index}]", issues)
    attempt = attempts.get(observation.attempt_id)
    if attempt is None:
        _add(issues, "PERF_ATTEMPT_REFERENCE", f"{path}.attempt_id", "attempt does not exist")
    else:
        if observation.exercise_id != attempt.exercise_id:
            _add(
                issues,
                "PERF_EXERCISE_REFERENCE",
                f"{path}.exercise_id",
                "observation exercise differs from its attempt",
            )
        known_event_ids = attempt_event_ids[attempt.id]
        for index, event_id in enumerate(observation.observed_event_ids):
            if event_id not in known_event_ids:
                _add(
                    issues,
                    "PERF_EVENT_REFERENCE",
                    f"{path}.observed_event_ids[{index}]",
                    "normalized event does not exist in attempt",
                )
    if observation.status in {ObservationStatus.MATCH, ObservationStatus.DISCREPANCY} and not (
        observation.expected_canonical_ids or observation.expected_value is not None
    ):
        _add(issues, "PERF_EXPECTED_VALUE", path, "comparison has no expected fact")
    if (
        observation.status in {ObservationStatus.UNOBSERVABLE, ObservationStatus.INVALID_INPUT}
        and observation.blocking is False
    ):
        _add(
            issues,
            "PERF_INVALID_NOT_BLOCKING",
            f"{path}.blocking",
            "invalid evidence must block",
        )


def _unique_ids(
    values: tuple[object, ...],
    path: str,
    issues: list[PerformanceValidationIssue],
) -> set[str]:
    result: set[str] = set()
    for index, value in enumerate(values):
        identifier = getattr(value, "id", None)
        _id(identifier, f"{path}[{index}].id", issues)
        if isinstance(identifier, str):
            if identifier in result:
                _add(issues, "PERF_ID_DUPLICATE", f"{path}[{index}].id", "ID is duplicated")
            result.add(identifier)
    return result


def _id(value: object, path: str, issues: list[PerformanceValidationIssue]) -> None:
    if not is_stable_id(value):
        _add(issues, "PERF_STABLE_ID", path, "expected namespaced stable ID")


def _nonempty(value: object, path: str, issues: list[PerformanceValidationIssue]) -> None:
    if not isinstance(value, str) or not value.strip():
        _add(issues, "PERF_REQUIRED_TEXT", path, "value is empty")


def _tuple(value: object, path: str, issues: list[PerformanceValidationIssue]) -> None:
    if not isinstance(value, tuple):
        _add(issues, "PERF_IMMUTABLE_COLLECTION", path, "expected tuple")


def _strings(
    values: object,
    path: str,
    issues: list[PerformanceValidationIssue],
) -> None:
    if not isinstance(values, tuple):
        return
    for index, value in enumerate(values):
        _nonempty(value, f"{path}[{index}]", issues)


def _add(
    issues: list[PerformanceValidationIssue],
    code: str,
    path: str,
    message: str,
) -> None:
    issues.append(PerformanceValidationIssue(code, path, message))
