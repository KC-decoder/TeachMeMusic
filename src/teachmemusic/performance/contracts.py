"""Immutable, MIDI-adapter-neutral learner-performance contracts."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

PERFORMANCE_CONTRACT_ID = "org.teachmemusic.performance-contracts"
PERFORMANCE_CONTRACT_VERSION = "0.1.0"


class MidiEventKind(StrEnum):
    """Normalized event families admitted by the first performance boundary."""

    NOTE_ON = "note-on"
    NOTE_OFF = "note-off"
    CONTROL_CHANGE = "control-change"
    CONNECTION = "connection"
    DIAGNOSTIC = "diagnostic"


class AttemptCompletion(StrEnum):
    """Why one bounded learner attempt ended."""

    COMPLETED = "completed"
    INTERRUPTED = "interrupted"
    CANCELLED = "cancelled"
    INPUT_FAILURE = "input-failure"
    SAFE_STOP = "safe-stop"


class ObservationDimension(StrEnum):
    """Dimensions kept separate in factual attempt evidence."""

    INPUT = "input"
    PITCH = "pitch"
    ORDER = "order"
    CHORD_SET = "chord-set"
    ONSET = "onset"
    DURATION = "duration"
    CONTINUITY = "continuity"
    VELOCITY = "velocity"
    RELEASE = "release"
    PEDAL = "pedal"
    SELF_REPORT = "self-report"
    HUMAN_REVIEW = "human-review"


class ObservationStatus(StrEnum):
    """Factual result of one declared comparison."""

    MATCH = "match"
    DISCREPANCY = "discrepancy"
    AMBIGUOUS = "ambiguous"
    UNOBSERVABLE = "unobservable"
    INVALID_INPUT = "invalid-input"


class ObservationSource(StrEnum):
    """Evidence source that supports an observation."""

    MIDI = "midi"
    LEARNER_REPORT = "learner-report"
    HUMAN_REVIEW = "human-review"


class EvidenceConfidence(StrEnum):
    """Bounded confidence vocabulary; never a probability claim."""

    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class CalibrationProfile:
    """Frozen input and timing assumptions for one set of attempts."""

    id: str
    version: str
    device_id: str
    input_name: str
    timestamp_origin: str
    pitch_numbering_confirmed: bool
    sustain_available: bool | None
    clock_offset_microseconds: int | None
    clock_jitter_microseconds: int | None
    timing_window_microseconds: int | None
    chord_window_microseconds: int | None
    limitations: tuple[str, ...] = ()
    approved: bool = False
    approved_at_utc: str | None = None


@dataclass(frozen=True, slots=True)
class RawMidiMessage:
    """One original bounded MIDI message with a monotonic receive time."""

    id: str
    sequence_number: int
    timestamp_microseconds: int
    data: tuple[int, ...]


@dataclass(frozen=True, slots=True)
class NormalizedMidiEvent:
    """One explicit interpretation of a raw MIDI or connection event."""

    id: str
    raw_message_id: str | None
    kind: MidiEventKind
    timestamp_microseconds: int
    channel: int | None = None
    note: int | None = None
    velocity: int | None = None
    controller: int | None = None
    value: int | None = None
    detail: str | None = None


@dataclass(frozen=True, slots=True)
class SelfReportItem:
    """One learner statement retained separately from measured evidence."""

    prompt_id: str
    response: str


@dataclass(frozen=True, slots=True)
class LearnerAttempt:
    """One bounded attempt before alignment, scoring, or teaching judgment."""

    id: str
    run_id: str
    exercise_id: str
    calibration_id: str
    practice_mode: str
    support_state_id: str
    started_at_utc: str
    start_microseconds: int
    end_microseconds: int
    completion: AttemptCompletion
    raw_messages: tuple[RawMidiMessage, ...] = ()
    normalized_events: tuple[NormalizedMidiEvent, ...] = ()
    self_report: tuple[SelfReportItem, ...] = ()
    diagnostics: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class Observation:
    """One factual, source-labelled expected-versus-observed result."""

    id: str
    attempt_id: str
    exercise_id: str
    dimension: ObservationDimension
    status: ObservationStatus
    source: ObservationSource
    expected_canonical_ids: tuple[str, ...] = ()
    observed_event_ids: tuple[str, ...] = ()
    expected_value: str | None = None
    observed_value: str | None = None
    measured_value: str | None = None
    matching_policy: str | None = None
    confidence: EvidenceConfidence = EvidenceConfidence.UNKNOWN
    blocking: bool = False
    limitations: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class PerformanceBundle:
    """Versioned collection crossing the pure performance boundary."""

    calibrations: tuple[CalibrationProfile, ...] = ()
    attempts: tuple[LearnerAttempt, ...] = ()
    observations: tuple[Observation, ...] = ()
    contract_id: str = PERFORMANCE_CONTRACT_ID
    contract_version: str = PERFORMANCE_CONTRACT_VERSION
