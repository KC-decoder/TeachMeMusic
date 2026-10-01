"""TeachMeMusic-owned, audio-engine-independent playback contracts.

Times exposed to the browser are integer microseconds. Source score positions
and tempo values remain exact fractions so the plan can always be traced back
to canonical facts without depending on Tone.js or renderer objects.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from fractions import Fraction

from .contracts import ViewerDiagnostic

PLAYBACK_CONTRACT_ID = "org.teachmemusic.playback-plan"
PLAYBACK_CONTRACT_VERSION = "0.2.0"


@dataclass(frozen=True, slots=True)
class PlaybackClef:
    """The active canonical clef used to group a virtual-piano contribution."""

    sign: str
    line: int | None
    octave_change: int | None


@dataclass(frozen=True, slots=True)
class PlaybackSourceEvent:
    """One canonical event contributing to a scheduled sounding note."""

    event_id: str
    part_id: str
    measure_id: str
    staff: str
    voice: str
    score_onset: Fraction
    clef_group_id: str | None
    clef: PlaybackClef | None


@dataclass(frozen=True, slots=True)
class PlaybackNote:
    """One audible note after repeat expansion and sounding-tie resolution."""

    id: str
    start_microseconds: int
    end_microseconds: int
    midi_pitch: int
    source_events: tuple[PlaybackSourceEvent, ...]
    chord_id: str | None = None
    dynamic_percent: Fraction | None = None


@dataclass(frozen=True, slots=True)
class TempoControl:
    """One tempo state established on the expanded playback timeline."""

    id: str
    at_microseconds: int
    quarter_notes_per_minute: Fraction
    source_score_onset: Fraction
    origin: str
    source_part_id: str | None = None
    source_measure_id: str | None = None
    source_order: int | None = None


@dataclass(frozen=True, slots=True)
class GraceRealization:
    """Audible timing assigned to one zero-time canonical grace event."""

    event_id: str
    anchor_event_ids: tuple[str, ...]
    relation: str
    origin: str
    duration_quarter_notes: Fraction
    cluster_index: int
    cluster_size: int


@dataclass(frozen=True, slots=True)
class PlaybackMeasureVisit:
    """One visit to a canonical measure position after repeat expansion."""

    visit_index: int
    source_measure_index: int
    source_measure_number: str
    source_measure_ids: tuple[str, ...]
    source_score_onset: Fraction
    start_microseconds: int
    end_microseconds: int
    entry_reason: str = "sequential"


@dataclass(frozen=True, slots=True)
class PlaybackPlan:
    """Deterministic canonical playback timeline consumed by later adapters."""

    package_id: str
    score_id: str
    canonical_schema_id: str
    canonical_schema_version: str
    duration_microseconds: int
    notes: tuple[PlaybackNote, ...]
    tempo_controls: tuple[TempoControl, ...]
    measure_visits: tuple[PlaybackMeasureVisit, ...]
    grace_realizations: tuple[GraceRealization, ...] = ()
    navigation_section_starts: tuple[int, ...] = (0,)
    diagnostics: tuple[ViewerDiagnostic, ...] = ()
    contract_id: str = PLAYBACK_CONTRACT_ID
    contract_version: str = PLAYBACK_CONTRACT_VERSION


@dataclass(frozen=True, slots=True)
class PlaybackPlanIssue:
    """One stable playback-contract validation issue."""

    code: str
    path: str
    message: str


class PlaybackPlanError(ValueError):
    """Raised when an invalid playback plan would cross the app boundary."""

    def __init__(self, issues: tuple[PlaybackPlanIssue, ...]) -> None:
        self.issues = issues
        first = issues[0]
        super().__init__(f"{first.code} at {first.path}: {first.message}")


@dataclass(frozen=True, slots=True)
class PlaybackState:
    """Deterministic transport state at one half-open timeline position."""

    position_microseconds: int
    active_note_ids: tuple[str, ...]
    next_note_index: int
    completed: bool


def validate_playback_plan(plan: PlaybackPlan) -> tuple[PlaybackPlanIssue, ...]:
    """Validate the contract, ordering, timing, identity, and source invariants."""

    issues: list[PlaybackPlanIssue] = []

    def add(code: str, path: str, message: str) -> None:
        issues.append(PlaybackPlanIssue(code, path, message))

    if plan.contract_id != PLAYBACK_CONTRACT_ID:
        add("PLAYBACK_CONTRACT_ID", "contract_id", "unsupported playback contract ID")
    if plan.contract_version != PLAYBACK_CONTRACT_VERSION:
        add(
            "PLAYBACK_CONTRACT_VERSION",
            "contract_version",
            "unsupported playback contract version",
        )
    for path, value in (
        ("package_id", plan.package_id),
        ("score_id", plan.score_id),
        ("canonical_schema_id", plan.canonical_schema_id),
        ("canonical_schema_version", plan.canonical_schema_version),
    ):
        if not value:
            add("PLAYBACK_REQUIRED_VALUE", path, "value is empty")
    if plan.duration_microseconds < 0:
        add("PLAYBACK_DURATION", "duration_microseconds", "duration is negative")

    note_ids: set[str] = set()
    previous_note_key: tuple[int, int, str] | None = None
    for index, note in enumerate(plan.notes):
        path = f"notes[{index}]"
        key = (note.start_microseconds, note.midi_pitch, note.id)
        if previous_note_key is not None and key < previous_note_key:
            add("PLAYBACK_NOTE_ORDER", path, "notes are not deterministically ordered")
        previous_note_key = key
        if not note.id or note.id in note_ids:
            add("PLAYBACK_NOTE_ID", f"{path}.id", "note ID is empty or duplicated")
        note_ids.add(note.id)
        if not 0 <= note.start_microseconds < note.end_microseconds:
            add("PLAYBACK_NOTE_TIME", path, "note has an invalid half-open time range")
        if note.end_microseconds > plan.duration_microseconds:
            add("PLAYBACK_NOTE_RANGE", path, "note exceeds the playback duration")
        if not 0 <= note.midi_pitch <= 127:
            add("PLAYBACK_MIDI_PITCH", f"{path}.midi_pitch", "MIDI pitch is out of range")
        if not note.source_events:
            add("PLAYBACK_NOTE_SOURCE", f"{path}.source_events", "note has no source event")
        source_ids: set[str] = set()
        for source_index, source in enumerate(note.source_events):
            source_path = f"{path}.source_events[{source_index}]"
            if not all((source.event_id, source.part_id, source.measure_id)):
                add("PLAYBACK_SOURCE_ID", source_path, "canonical source identity is empty")
            if source.event_id in source_ids:
                add("PLAYBACK_SOURCE_DUPLICATE", source_path, "source event is duplicated")
            source_ids.add(source.event_id)
            if (source.clef is None) != (source.clef_group_id is None):
                add(
                    "PLAYBACK_CLEF_GROUP",
                    source_path,
                    "clef and clef-group identity must be present together",
                )
        if note.dynamic_percent is not None and note.dynamic_percent < 0:
            add("PLAYBACK_DYNAMICS", f"{path}.dynamic_percent", "dynamics are negative")

    previous_tempo_key: tuple[int, str] | None = None
    tempo_ids: set[str] = set()
    for index, control in enumerate(plan.tempo_controls):
        path = f"tempo_controls[{index}]"
        tempo_key = (control.at_microseconds, control.id)
        if previous_tempo_key is not None and tempo_key < previous_tempo_key:
            add("PLAYBACK_TEMPO_ORDER", path, "tempo controls are not ordered")
        previous_tempo_key = tempo_key
        if not control.id or control.id in tempo_ids:
            add("PLAYBACK_TEMPO_ID", f"{path}.id", "tempo ID is empty or duplicated")
        tempo_ids.add(control.id)
        if not 0 <= control.at_microseconds <= plan.duration_microseconds:
            add("PLAYBACK_TEMPO_TIME", path, "tempo control is outside the timeline")
        if control.quarter_notes_per_minute <= 0:
            add("PLAYBACK_TEMPO_VALUE", path, "tempo is not positive")
        if control.origin not in {"canonical", "caller-fallback"}:
            add("PLAYBACK_TEMPO_ORIGIN", path, "tempo origin is unsupported")
    if plan.duration_microseconds and (
        not plan.tempo_controls or plan.tempo_controls[0].at_microseconds != 0
    ):
        add("PLAYBACK_INITIAL_TEMPO", "tempo_controls", "timeline has no initial tempo")
    if (
        not plan.navigation_section_starts
        or plan.navigation_section_starts[0] != 0
        or tuple(sorted(set(plan.navigation_section_starts))) != plan.navigation_section_starts
    ):
        add(
            "PLAYBACK_NAVIGATION_SECTIONS",
            "navigation_section_starts",
            "section starts must be sorted, unique, and begin at measure index zero",
        )

    grace_event_ids: set[str] = set()
    for index, grace in enumerate(plan.grace_realizations):
        path = f"grace_realizations[{index}]"
        if not grace.event_id or grace.event_id in grace_event_ids:
            add("PLAYBACK_GRACE_ID", f"{path}.event_id", "grace event ID is empty or duplicated")
        grace_event_ids.add(grace.event_id)
        if not grace.anchor_event_ids:
            add("PLAYBACK_GRACE_ANCHOR", path, "grace realization has no anchor event")
        if grace.relation not in {"following", "previous"}:
            add("PLAYBACK_GRACE_RELATION", path, "grace relation is unsupported")
        if grace.origin not in {
            "source-make-time",
            "source-steal-following",
            "source-steal-previous",
            "caller-fallback",
        }:
            add("PLAYBACK_GRACE_ORIGIN", path, "grace timing origin is unsupported")
        if grace.duration_quarter_notes <= 0:
            add("PLAYBACK_GRACE_DURATION", path, "grace duration is not positive")
        if not 0 <= grace.cluster_index < grace.cluster_size:
            add("PLAYBACK_GRACE_CLUSTER", path, "grace cluster position is invalid")

    expected_visit_start = 0
    for index, visit in enumerate(plan.measure_visits):
        path = f"measure_visits[{index}]"
        if visit.visit_index != index:
            add("PLAYBACK_VISIT_INDEX", path, "visit indices are not contiguous")
        if visit.start_microseconds != expected_visit_start:
            add("PLAYBACK_VISIT_GAP", path, "measure visits do not form a contiguous timeline")
        if visit.end_microseconds < visit.start_microseconds:
            add("PLAYBACK_VISIT_TIME", path, "measure visit ends before it starts")
        if not visit.source_measure_ids:
            add("PLAYBACK_VISIT_SOURCE", path, "measure visit has no canonical source")
        if visit.entry_reason not in {"initial", "sequential", "repeat", "jump", "coda"}:
            add("PLAYBACK_VISIT_REASON", path, "measure visit entry reason is unsupported")
        expected_visit_start = visit.end_microseconds
    if plan.measure_visits and expected_visit_start != plan.duration_microseconds:
        add(
            "PLAYBACK_VISIT_DURATION",
            "measure_visits",
            "measure visits do not end at the playback duration",
        )
    return tuple(issues)


def require_valid_playback_plan(plan: PlaybackPlan) -> None:
    """Raise if a playback plan cannot safely cross the application boundary."""

    issues = validate_playback_plan(plan)
    if issues:
        raise PlaybackPlanError(issues)


def playback_state_at(plan: PlaybackPlan, position_microseconds: int) -> PlaybackState:
    """Return active notes and the next unsounded note at a transport position."""

    require_valid_playback_plan(plan)
    if not 0 <= position_microseconds <= plan.duration_microseconds:
        raise ValueError("position_microseconds is outside the playback timeline")
    active = tuple(
        note.id
        for note in plan.notes
        if note.start_microseconds <= position_microseconds < note.end_microseconds
    )
    next_index = len(plan.notes)
    for index, note in enumerate(plan.notes):
        if note.start_microseconds >= position_microseconds and note.id not in active:
            next_index = index
            break
    return PlaybackState(
        position_microseconds=position_microseconds,
        active_note_ids=active,
        next_note_index=next_index,
        completed=position_microseconds == plan.duration_microseconds,
    )


def _fraction_to_dict(value: Fraction) -> dict[str, int]:
    return {"numerator": value.numerator, "denominator": value.denominator}


def playback_plan_to_dict(plan: PlaybackPlan) -> dict[str, object]:
    """Return the deterministic JSON-ready playback boundary value."""

    return {
        "contract_id": plan.contract_id,
        "contract_version": plan.contract_version,
        "package_id": plan.package_id,
        "score_id": plan.score_id,
        "canonical_schema_id": plan.canonical_schema_id,
        "canonical_schema_version": plan.canonical_schema_version,
        "duration_microseconds": plan.duration_microseconds,
        "navigation_section_starts": list(plan.navigation_section_starts),
        "notes": [
            {
                "id": note.id,
                "start_microseconds": note.start_microseconds,
                "end_microseconds": note.end_microseconds,
                "midi_pitch": note.midi_pitch,
                "chord_id": note.chord_id,
                "dynamic_percent": (
                    _fraction_to_dict(note.dynamic_percent)
                    if note.dynamic_percent is not None
                    else None
                ),
                "source_events": [
                    {
                        "event_id": source.event_id,
                        "part_id": source.part_id,
                        "measure_id": source.measure_id,
                        "staff": source.staff,
                        "voice": source.voice,
                        "score_onset": _fraction_to_dict(source.score_onset),
                        "clef_group_id": source.clef_group_id,
                        "clef": (
                            {
                                "sign": source.clef.sign,
                                "line": source.clef.line,
                                "octave_change": source.clef.octave_change,
                            }
                            if source.clef is not None
                            else None
                        ),
                    }
                    for source in note.source_events
                ],
            }
            for note in plan.notes
        ],
        "tempo_controls": [
            {
                "id": control.id,
                "at_microseconds": control.at_microseconds,
                "quarter_notes_per_minute": _fraction_to_dict(control.quarter_notes_per_minute),
                "source_score_onset": _fraction_to_dict(control.source_score_onset),
                "origin": control.origin,
                "source_part_id": control.source_part_id,
                "source_measure_id": control.source_measure_id,
                "source_order": control.source_order,
            }
            for control in plan.tempo_controls
        ],
        "grace_realizations": [
            {
                "event_id": grace.event_id,
                "anchor_event_ids": list(grace.anchor_event_ids),
                "relation": grace.relation,
                "origin": grace.origin,
                "duration_quarter_notes": _fraction_to_dict(grace.duration_quarter_notes),
                "cluster_index": grace.cluster_index,
                "cluster_size": grace.cluster_size,
            }
            for grace in plan.grace_realizations
        ],
        "measure_visits": [
            {
                "visit_index": visit.visit_index,
                "source_measure_index": visit.source_measure_index,
                "source_measure_number": visit.source_measure_number,
                "source_measure_ids": list(visit.source_measure_ids),
                "source_score_onset": _fraction_to_dict(visit.source_score_onset),
                "start_microseconds": visit.start_microseconds,
                "end_microseconds": visit.end_microseconds,
                "entry_reason": visit.entry_reason,
            }
            for visit in plan.measure_visits
        ],
        "diagnostics": [
            {
                "code": item.code,
                "severity": item.severity.value,
                "message": item.message,
                "canonical_ids": list(item.canonical_ids),
            }
            for item in plan.diagnostics
        ],
    }


def playback_plan_to_json(plan: PlaybackPlan) -> str:
    """Serialize a validated playback plan with stable ordering and spacing."""

    require_valid_playback_plan(plan)
    return json.dumps(
        playback_plan_to_dict(plan),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
