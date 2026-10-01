"""Immutable contracts for deterministic canonical-score analysis."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from fractions import Fraction

ANALYSIS_CONTRACT_ID = "org.teachmemusic.canonical-analysis"
ANALYSIS_CONTRACT_VERSION = "0.1.0"
ANALYSIS_VERSION = "canonical-analysis-rules/0.1.0"


class AnalysisDerivation(StrEnum):
    """Whether an analysis value is counted or derived from source facts."""

    SOURCE_SUMMARY = "source-summary"
    DETERMINISTIC_DERIVATION = "deterministic-derivation"


class AnalysisFactKind(StrEnum):
    """Stable score-level fact vocabulary."""

    PART_COUNT = "part-count"
    MEASURE_POSITION_COUNT = "measure-position-count"
    EVENT_COUNT = "event-count"
    PITCHED_EVENT_COUNT = "pitched-event-count"
    UNPITCHED_EVENT_COUNT = "unpitched-event-count"
    REST_EVENT_COUNT = "rest-event-count"
    STAFF_COUNT = "staff-count"
    VOICE_COUNT = "voice-count"
    CHORD_COUNT = "chord-count"
    PITCH_RANGE = "pitch-range"
    WRITTEN_DURATION_VOCABULARY = "written-duration-vocabulary"
    METER_VOCABULARY = "meter-vocabulary"
    CLEF_VOCABULARY = "clef-vocabulary"


class RepetitionKind(StrEnum):
    """Dimensions under which measure-layer material repeats."""

    EXACT_PITCH_AND_RHYTHM = "exact-pitch-and-rhythm"
    RHYTHM_ONLY = "rhythm-only"


class BoundaryReason(StrEnum):
    """Deterministic reasons for a candidate musical boundary."""

    SCOPE_START = "scope-start"
    SCOPE_END = "scope-end"
    PRECEDING_TERMINAL_REST = "preceding-terminal-rest"
    REPETITION_ENTRY = "repetition-entry"
    TEXTURE_CHANGE = "texture-change"
    RHYTHM_CHANGE = "rhythm-change"
    MEASURE_FALLBACK = "measure-fallback"


class AnalysisConfidence(StrEnum):
    """Bounded confidence label, not a statistical probability."""

    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class AnalysisDemandDimension(StrEnum):
    """Task dimensions estimated without choosing a teaching policy."""

    SCORE_LITERACY = "score-literacy"
    RANGE = "range"
    TEXTURE = "texture"
    SIMULTANEITY = "simultaneity"
    LEAPS = "leaps"
    RHYTHMIC_DENSITY = "rhythmic-density"
    METER = "meter"
    COORDINATION = "coordination"
    CONTINUITY = "continuity"
    STRUCTURE = "structure"
    PASSAGE_LENGTH = "passage-length"


@dataclass(frozen=True, slots=True)
class AnalysisScope:
    """Canonical score slice included in one analysis."""

    package_id: str
    score_id: str
    part_ids: tuple[str, ...]
    start_measure_ordinal: int
    end_measure_ordinal: int


@dataclass(frozen=True, slots=True)
class AnalysisFact:
    """One inspectable value with exact canonical evidence."""

    id: str
    kind: AnalysisFactKind
    value: str
    evidence_ids: tuple[str, ...]
    derivation: AnalysisDerivation
    algorithm: str
    uncertainty: str | None = None


@dataclass(frozen=True, slots=True)
class LayerProfile:
    """A part/staff/voice layer observed in the selected score scope."""

    id: str
    part_id: str
    staff_id: str
    voice_id: str
    measure_ids: tuple[str, ...]
    event_ids: tuple[str, ...]
    pitched_event_count: int
    unpitched_event_count: int
    rest_event_count: int
    distinct_onset_count: int
    lowest_written_semitone: Fraction | None
    highest_written_semitone: Fraction | None


@dataclass(frozen=True, slots=True)
class RhythmProfile:
    """Exact rhythmic inventory for the selected scope."""

    written_durations: tuple[Fraction, ...]
    shortest_duration: Fraction | None
    longest_duration: Fraction | None
    dotted_event_count: int
    tuplet_event_count: int
    grace_event_count: int
    distinct_onset_count: int
    evidence_event_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class TextureProfile:
    """Layering, chord, and simultaneity facts for the selected scope."""

    layer_count: int
    staff_count: int
    voice_count: int
    chord_count: int
    max_simultaneous_pitches: int
    max_active_layers: int
    evidence_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class RepetitionGroup:
    """Two or more layer-scoped measures with the same declared signature."""

    id: str
    kind: RepetitionKind
    layer_id: str
    occurrence_measure_ids: tuple[str, ...]
    evidence_event_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class BoundaryCandidate:
    """A source-linked candidate segmentation point, not a lesson decision."""

    id: str
    score_onset: Fraction
    measure_ids: tuple[str, ...]
    reasons: tuple[BoundaryReason, ...]
    evidence_ids: tuple[str, ...]
    confidence: AnalysisConfidence
    fallback: bool


@dataclass(frozen=True, slots=True)
class DemandEstimate:
    """Transparent rule-based task estimate with evidence and uncertainty."""

    id: str
    dimension: AnalysisDemandDimension
    level: int | None
    metric: str
    evidence_ids: tuple[str, ...]
    rationale: str
    uncertainty: str | None = None


@dataclass(frozen=True, slots=True)
class ScoreAnalysis:
    """Complete deterministic analysis for one canonical score scope."""

    id: str
    canonical_digest_sha256: str
    analysis_version: str
    scope: AnalysisScope
    facts: tuple[AnalysisFact, ...]
    layers: tuple[LayerProfile, ...]
    rhythm: RhythmProfile
    texture: TextureProfile
    repetitions: tuple[RepetitionGroup, ...]
    boundaries: tuple[BoundaryCandidate, ...]
    demands: tuple[DemandEstimate, ...]
    limitations: tuple[str, ...] = ()
    contract_id: str = ANALYSIS_CONTRACT_ID
    contract_version: str = ANALYSIS_CONTRACT_VERSION
