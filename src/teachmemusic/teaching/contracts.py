"""Immutable contracts for lessons, teaching evidence, and run provenance."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from fractions import Fraction

from teachmemusic.performance import (
    PERFORMANCE_CONTRACT_VERSION,
    ObservationDimension,
    ObservationSource,
    PerformanceBundle,
)

TEACHING_CONTRACT_ID = "org.teachmemusic.teaching-evidence"
TEACHING_CONTRACT_VERSION = "0.2.0"


class LearnerTrack(StrEnum):
    """Public learner-selected teaching tracks."""

    BEGINNER = "beginner"
    INTERMEDIATE = "intermediate"
    ADVANCED = "advanced"


class CanonicalAnchorKind(StrEnum):
    """Canonical entity families addressable by a teaching contract."""

    PACKAGE = "package"
    SCORE = "score"
    PART = "part"
    MEASURE = "measure"
    STAFF = "staff"
    VOICE = "voice"
    EVENT = "event"
    CHORD = "chord"
    HARMONY = "harmony"
    SPAN = "span"
    DIRECTION = "direction"


class SkillDomain(StrEnum):
    """Target domains preserved separately in a lesson plan."""

    READING = "reading"
    PITCH = "pitch"
    RHYTHM = "rhythm"
    COORDINATION = "coordination"
    CONTINUITY = "continuity"
    ARTICULATION = "articulation"
    DYNAMICS = "dynamics"
    BALANCE = "balance"
    PHRASING = "phrasing"
    PEDAL = "pedal"
    AURAL = "aural"
    MEMORY = "memory"
    STRUCTURE = "structure"
    SELF_REGULATION = "self-regulation"


class DemandDimension(StrEnum):
    """Task-demand axes used without collapsing them into one difficulty."""

    SCORE_LITERACY = "score-literacy"
    RANGE = "range"
    TEXTURE = "texture"
    SIMULTANEITY = "simultaneity"
    LEAPS = "leaps"
    RHYTHMIC_DENSITY = "rhythmic-density"
    METER = "meter"
    TEMPO = "tempo"
    COORDINATION = "coordination"
    CONTINUITY = "continuity"
    EXPRESSION = "expression"
    AURAL = "aural"
    MEMORY = "memory"
    STRUCTURE = "structure"
    PASSAGE_LENGTH = "passage-length"


class PracticeMode(StrEnum):
    """Approved first-loop practice modes."""

    LISTEN = "listen"
    EAR_FIRST = "ear-first"
    FOLLOW_PITCH = "follow-pitch"
    PULSE_GUIDED = "pulse-guided"
    SUPPORTED_PERFORMANCE = "supported-performance"
    INDEPENDENT_PERFORMANCE = "independent-performance"
    RETENTION = "retention"
    TRANSFER = "transfer"


class LessonNodeKind(StrEnum):
    """Kinds of node in the ordered lesson graph."""

    EXERCISE = "exercise"
    INTEGRATION = "integration"
    RETENTION = "retention"
    TRANSFER = "transfer"


class EvidenceState(StrEnum):
    """Dimension-specific evidence states from the approved methodology."""

    NOT_ATTEMPTED = "not-attempted"
    EXPOSED = "exposed"
    ATTEMPTED = "attempted"
    CORRECTED_SUPPORTED = "corrected-supported"
    STABLE_SUPPORTED = "stable-supported"
    INDEPENDENT_IN_SESSION = "independent-in-session"
    RETAINED = "retained"
    TRANSFERRED = "transferred"
    INCONCLUSIVE = "inconclusive"
    HUMAN_REVIEWED = "human-reviewed"


class EvidenceContext(StrEnum):
    """Context in which one evidence state was obtained."""

    ACQUISITION = "acquisition"
    INDEPENDENT = "independent"
    INTEGRATION = "integration"
    RETENTION = "retention"
    TRANSFER = "transfer"


class PolicyAction(StrEnum):
    """Frozen first-policy action vocabulary."""

    CORRECT = "correct"
    STABILIZE = "stabilize"
    REDUCE_SUPPORT = "reduce-support"
    INTEGRATE = "integrate"
    RETAIN = "retain"
    TRANSFER = "transfer"
    INCONCLUSIVE = "inconclusive"
    HUMAN_REVIEW = "human-review"
    SAFE_STOP = "safe-stop"


class FeedbackTiming(StrEnum):
    """Whether feedback interrupts or follows an attempt."""

    IMMEDIATE = "immediate"
    END_OF_ATTEMPT = "end-of-attempt"


class PlanAuditOutcome(StrEnum):
    """Owner/human disposition of the untouched generated plan."""

    PASS_NO_CHANGE = "pass-no-change"
    PASS_WITH_NONPEDAGOGICAL_FIX = "pass-with-nonpedagogical-fix"
    QUALIFIED_HUMAN_INTERVENTION = "qualified-human-intervention"
    FAIL_STOP = "fail-stop"


class RunEventKind(StrEnum):
    """Append-only event families in the first evidence record."""

    RUN_CREATED = "run-created"
    DATA_AUTHORIZED = "data-authorized"
    PLAN_GENERATED = "plan-generated"
    PLAN_AUDITED = "plan-audited"
    CALIBRATION_RECORDED = "calibration-recorded"
    ATTEMPT_RECORDED = "attempt-recorded"
    OBSERVATION_RECORDED = "observation-recorded"
    EVIDENCE_RECORDED = "evidence-recorded"
    FEEDBACK_RECORDED = "feedback-recorded"
    POLICY_DECIDED = "policy-decided"
    SELF_REPORT_RECORDED = "self-report-recorded"
    OUTSIDE_PRACTICE_RECORDED = "outside-practice-recorded"
    PAUSED = "paused"
    STOPPED = "stopped"
    EXPORTED = "exported"
    GATE_DECIDED = "gate-decided"


@dataclass(frozen=True, slots=True)
class ContractVersionSet:
    """Versions frozen for one teaching run."""

    application_version: str
    canonical_schema_id: str
    canonical_schema_version: str
    parser_version: str
    analysis_version: str
    planner_version: str
    policy_version: str
    feedback_version: str
    calibration_version: str
    teaching_contract_version: str = TEACHING_CONTRACT_VERSION
    performance_contract_version: str = PERFORMANCE_CONTRACT_VERSION


@dataclass(frozen=True, slots=True)
class LearnerContextSnapshot:
    """Run-specific context, not an inferred permanent learner label."""

    id: str
    track: LearnerTrack
    goals: tuple[str, ...] = ()
    prior_experience: tuple[str, ...] = ()
    accessibility_choices: tuple[str, ...] = ()
    outside_practice: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class DataAuthorization:
    """Owner-approved local evidence categories for one run."""

    id: str
    approved: bool
    approved_at_utc: str | None
    capture_midi: bool
    capture_self_report: bool
    capture_environment: bool
    allow_export: bool
    excluded_sources: tuple[str, ...] = ("audio", "video", "biometric", "cloud")


@dataclass(frozen=True, slots=True)
class TeachingRunManifest:
    """Identity and provenance frozen before plan or learner evidence."""

    id: str
    created_at_utc: str
    score_digest_sha256: str
    package_id: str
    score_id: str
    scope_label: str
    learner_context_id: str
    data_authorization_id: str
    versions: ContractVersionSet


@dataclass(frozen=True, slots=True)
class CanonicalAnchor:
    """One typed opaque reference to immutable canonical content."""

    kind: CanonicalAnchorKind
    canonical_id: str


@dataclass(frozen=True, slots=True)
class CanonicalAnchorSet:
    """Exact canonical entities and score-time extent taught by an exercise."""

    id: str
    package_id: str
    score_id: str
    anchors: tuple[CanonicalAnchor, ...]
    start_quarters: Fraction
    end_quarters: Fraction


@dataclass(frozen=True, slots=True)
class SyntheticExpectedEvent:
    """One non-canonical event created by an explicit teaching rule."""

    id: str
    onset_quarters: Fraction
    duration_quarters: Fraction
    midi_note: int
    source_canonical_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class SyntheticExerciseMaterial:
    """Typed transfer material kept outside the canonical-score namespace."""

    id: str
    source_canonical_ids: tuple[str, ...]
    events: tuple[SyntheticExpectedEvent, ...]
    rationale: str


@dataclass(frozen=True, slots=True)
class TaskDemand:
    """One bounded demand judgment with source evidence and uncertainty."""

    id: str
    dimension: DemandDimension
    level: int
    evidence_canonical_ids: tuple[str, ...]
    rationale: str
    uncertainty: str | None = None


@dataclass(frozen=True, slots=True)
class SupportState:
    """Every assistance condition that changes interpretation of an attempt."""

    id: str
    notation_visible: bool
    cursor_visible: bool
    note_names_visible: bool
    keyboard_highlighting: bool
    fingering_visible: bool
    demonstration_available: bool
    follow_mode: bool
    metronome: bool
    tempo_percent: int
    isolated_layers: tuple[str, ...] = ()
    isolated_dimensions: tuple[str, ...] = ()
    max_replays: int | None = None
    prompts_visible: bool = False
    accessibility_accommodations: tuple[str, ...] = ()
    tempo_bpm: Fraction | None = None


@dataclass(frozen=True, slots=True)
class ExpectedFact:
    """One expected, canonically anchored fact for a declared target."""

    id: str
    dimension: ObservationDimension
    canonical_ids: tuple[str, ...]
    expected_value: str
    observable_sources: tuple[ObservationSource, ...]
    synthetic_event_ids: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class EvidenceRequirement:
    """Evidence needed to leave or complete an exercise node."""

    id: str
    dimension: ObservationDimension
    minimum_state: EvidenceState
    context: EvidenceContext


@dataclass(frozen=True, slots=True)
class Exercise:
    """One stable musical target and its permitted teaching conditions."""

    id: str
    anchor_set: CanonicalAnchorSet | None
    boundary_reason: str
    layer_scope: tuple[str, ...]
    primary_skill: SkillDomain
    secondary_skills: tuple[SkillDomain, ...]
    task_demands: tuple[TaskDemand, ...]
    expected_facts: tuple[ExpectedFact, ...]
    practice_modes: tuple[PracticeMode, ...]
    initial_support: SupportState
    exit_evidence: tuple[EvidenceRequirement, ...]
    integration_successors: tuple[str, ...] = ()
    retention_successors: tuple[str, ...] = ()
    transfer_successors: tuple[str, ...] = ()
    review_routes: tuple[PolicyAction, ...] = (
        PolicyAction.INCONCLUSIVE,
        PolicyAction.HUMAN_REVIEW,
        PolicyAction.SAFE_STOP,
    )
    synthetic_material: SyntheticExerciseMaterial | None = None


@dataclass(frozen=True, slots=True)
class LessonNode:
    """One node and its declared graph relationships."""

    id: str
    kind: LessonNodeKind
    exercise_id: str
    prerequisites: tuple[str, ...] = ()
    successors: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class LessonPlan:
    """Untouched automatic plan captured before human review."""

    id: str
    run_id: str
    input_digest_sha256: str
    generated_at_utc: str
    planner_version: str
    policy_version: str
    track: LearnerTrack
    target_skills: tuple[SkillDomain, ...]
    exercises: tuple[Exercise, ...]
    nodes: tuple[LessonNode, ...]
    root_node_ids: tuple[str, ...]
    diagnostics: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class PlanIntervention:
    """One explicit difference from the untouched generated plan."""

    id: str
    plan_id: str
    path: str
    before_json: str
    after_json: str
    reason: str
    pedagogical: bool


@dataclass(frozen=True, slots=True)
class PlanAudit:
    """Human integrity, safety, and pedagogical disposition of a plan."""

    id: str
    plan_id: str
    reviewer: str
    reviewed_at_utc: str
    outcome: PlanAuditOutcome
    source_faithful: bool
    musically_coherent: bool
    safe: bool
    executable: bool
    interventions: tuple[PlanIntervention, ...] = ()
    notes: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class EvidenceRecord:
    """Dimension-specific learner evidence under one declared condition."""

    id: str
    attempt_id: str
    exercise_id: str
    requirement_id: str
    dimension: ObservationDimension
    state: EvidenceState
    context: EvidenceContext
    observation_ids: tuple[str, ...]
    support_state_id: str
    limitations: tuple[str, ...] = ()
    human_review: str | None = None


@dataclass(frozen=True, slots=True)
class FeedbackAction:
    """Factual feedback with one controllable next action."""

    id: str
    evidence_record_ids: tuple[str, ...]
    timing: FeedbackTiming
    target: str
    observation: str
    boundary: str | None
    action: str
    reason: str


@dataclass(frozen=True, slots=True)
class PolicyDecision:
    """One reproducible action selected by the frozen teaching policy."""

    id: str
    run_id: str
    exercise_id: str
    action: PolicyAction
    evidence_record_ids: tuple[str, ...]
    feedback_id: str | None
    reason: str
    policy_version: str
    next_node_id: str | None
    created_at_utc: str


@dataclass(frozen=True, slots=True)
class RunEvent:
    """One append-only provenance event in a teaching run."""

    id: str
    run_id: str
    sequence_number: int
    kind: RunEventKind
    payload_id: str
    occurred_at_utc: str
    supersedes_event_id: str | None = None


@dataclass(frozen=True, slots=True)
class EvidenceExport:
    """Complete local-first evidence envelope; never a mastery claim itself."""

    id: str
    exported_at_utc: str
    manifest: TeachingRunManifest
    learner_context: LearnerContextSnapshot
    data_authorization: DataAuthorization
    plans: tuple[LessonPlan, ...]
    audits: tuple[PlanAudit, ...]
    performance: PerformanceBundle
    evidence_records: tuple[EvidenceRecord, ...] = ()
    feedback_actions: tuple[FeedbackAction, ...] = ()
    policy_decisions: tuple[PolicyDecision, ...] = ()
    run_events: tuple[RunEvent, ...] = ()
    omissions: tuple[str, ...] = ()
    contract_id: str = TEACHING_CONTRACT_ID
    contract_version: str = TEACHING_CONTRACT_VERSION
