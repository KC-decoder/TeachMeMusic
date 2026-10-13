"""DEV-009 contracts for deterministic practice scope and skill requirements.

These records belong to the existing TeachMeMusic teaching authority.  The
verified evidence archive remains on teaching contract 0.3.0 while the
curriculum implementation is assembled; only these complete artifact types
use the accepted 0.4.0 target schema.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from fractions import Fraction

from teachmemusic.performance import AttemptCompletion, ObservationDimension

from .contracts import CanonicalAnchorSet, EvidenceContext, PracticeMode

CURRICULUM_CONTRACT_ID = "org.teachmemusic.teaching-evidence"
CURRICULUM_CONTRACT_VERSION = "0.4.0"
PRIMITIVE_CATALOGUE_ID = "TMM-PRIMITIVES-0.1"
REQUIREMENT_RULE_VERSION = "0.1.0"
EXERCISE_TEMPLATE_CATALOGUE_ID = "TMM-EXERCISE-TEMPLATES-0.1"
CURRICULUM_GRAPH_ID = "TMM-CURRICULUM-GRAPH-0.2"
BRANCH_GENERATOR_VERSION = "0.2.0"
TEMPO_POLICY_ID = "TMM-DETERMINISTIC-POLICY-0.2"
TEMPO_CONFIGURATION_VERSION = "0.2.0"
LASTING_SKILL_GRAPH_ID = "TMM-CURRICULUM-GRAPH-0.3"
LASTING_SKILL_GENERATOR_VERSION = "0.1.0"
FUNDAMENTAL_EXPLANATION_VERSION = "0.1.0"
FUNDAMENTAL_DEMONSTRATION_VERSION = "0.1.0"
FUNDAMENTAL_PRACTICE_VERSION = "0.1.0"
FUNDAMENTAL_RETURN_VERSION = "0.1.0"
LEARNING_OUTCOME_VERSION = "0.1.0"
RESEARCH_REWARD_VERSION = "0.1.0"
GAME_REWARD_VERSION = "0.1.0"
DECISION_SNAPSHOT_VERSION = "0.1.0"
ACTION_INVENTORY_VERSION = "0.1.0"
ACTION_SELECTION_VERSION = "0.1.0"
TRANSITION_RESULT_VERSION = "0.1.0"
EXPERIMENT_MANIFEST_VERSION = "0.1.0"
METRIC_SOURCE_RECORD_VERSION = "0.1.0"
METRIC_SUMMARY_VERSION = "0.1.0"


class ArtifactResolution(StrEnum):
    """Fail-closed result of deriving or validating a curriculum artifact."""

    RESOLVED = "resolved"
    REVIEW_REQUIRED = "review-required"
    UNSUPPORTED = "unsupported"
    FATAL = "fatal"


class DiagnosticSeverity(StrEnum):
    """Stable severity ordering for curriculum diagnostics."""

    INFO = "info"
    REVIEW = "review"
    UNSUPPORTED = "unsupported"
    FATAL = "fatal"


class NotationCondition(StrEnum):
    """What written layer configuration is active in one practice scope."""

    SINGLE_LAYER = "single-layer"
    UPPER_LAYER = "upper-layer"
    LOWER_LAYER = "lower-layer"
    COMBINED = "combined"


class ExecutionAssignment(StrEnum):
    """Physical execution assignment kept separate from written layers."""

    UNASSIGNED = "unassigned"
    RIGHT_HAND = "right-hand"
    LEFT_HAND = "left-hand"
    BOTH_HANDS = "both-hands"


class InterpretationProducer(StrEnum):
    """Authority that produced a layer or hand interpretation."""

    SOURCE_EXPLICIT = "source-explicit"
    DETERMINISTIC_RULE = "deterministic-rule"
    HUMAN_REVIEW = "human-review"


class ReviewState(StrEnum):
    """Review state retained without mutating an earlier proposal."""

    NOT_REQUIRED = "not-required"
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


class CurriculumEvidenceResult(StrEnum):
    """Factual result retained before mastery or progression is decided."""

    MATCHED = "matched"
    DISCREPANCY = "discrepancy"
    INCONCLUSIVE = "inconclusive"


class CurriculumMasteryStatus(StrEnum):
    """Authoritative result of projecting exact evidence onto one graph node."""

    MASTERED = "mastered"
    NOT_MASTERED = "not-mastered"
    INCONCLUSIVE = "inconclusive"


class CurriculumUnlockAction(StrEnum):
    """Bounded action emitted by the deterministic graph-unlock boundary."""

    UNLOCK_SUCCESSOR = "unlock-successor"
    COMPLETE_NODE = "complete-node"
    RETRY_CURRENT = "retry-current"
    HOLD_FOR_EVIDENCE = "hold-for-evidence"


class CurriculumPolicyAction(StrEnum):
    """Frozen policy-action vocabulary available to trajectory records."""

    RUN_DIAGNOSTIC = "run-diagnostic"
    TEACH_PREREQUISITE = "teach-prerequisite"
    RETRY = "retry"
    STRENGTHEN_SUPPORT = "strengthen-support"
    FADE_SUPPORT = "fade-support"
    SLOW_DOWN = "slow-down"
    RESTORE_PLANNED_TEMPO = "restore-planned-tempo"
    REMEDIATE = "remediate"
    RUN_CUMULATIVE = "run-cumulative"
    SCHEDULE_RETENTION = "schedule-retention"
    RUN_RETENTION = "run-retention"
    RUN_TRANSFER = "run-transfer"
    PROGRESS = "progress"
    INCONCLUSIVE = "inconclusive"
    HUMAN_REVIEW = "human-review"
    SAFE_STOP = "safe-stop"
    PAUSE = "pause"
    PROBE_TEMPO = "probe-tempo"
    MAINTAIN_TEMPO = "maintain-tempo"
    INCREASE_TEMPO = "increase-tempo"
    DECREASE_TEMPO = "decrease-tempo"
    REMOVE_TEMPO_CONSTRAINT = "remove-tempo-constraint"


class CurriculumExperimentStatus(StrEnum):
    """Scope of one frozen deterministic experiment manifest."""

    BOUNDED_COMPLETE = "bounded-complete"


class CurriculumActionEligibility(StrEnum):
    """Whether every guard for one declared action candidate passed."""

    ALLOWED = "allowed"
    EXCLUDED = "excluded"


class ResearchRewardComponentStatus(StrEnum):
    """Whether one numeric research component is defensibly available."""

    MEASURED = "measured"
    INCONCLUSIVE = "inconclusive"
    NOT_APPLICABLE = "not-applicable"
    INVALID_INPUT = "invalid-input"


class GameRewardSignal(StrEnum):
    """Non-authoritative acknowledgement shown to a learner."""

    RESULT_UNAVAILABLE = "result-unavailable"
    ATTEMPT_ACKNOWLEDGED = "attempt-acknowledged"
    ACCURATE_ATTEMPT_CELEBRATION = "accurate-attempt-celebration"


class PrimitiveFamily(StrEnum):
    """Bounded first catalogue families."""

    LISTENING = "listening"
    KEYBOARD = "keyboard"
    SCORE_LITERACY = "score-literacy"
    RHYTHM = "rhythm"
    PATTERN = "pattern"
    HARMONY = "harmony"
    LAYER_CONTROL = "layer-control"
    COORDINATION = "coordination"
    TECHNIQUE = "technique"
    EXPRESSION = "expression"
    MEMORY = "memory"
    SELF_REGULATION = "self-regulation"


class RequirementRole(StrEnum):
    """Pedagogical role of a passage-skill relationship."""

    FOUNDATION = "foundation"
    PASSAGE_APPLICATION = "passage-application"
    LAYER_INTEGRATION = "layer-integration"
    EXPRESSION = "expression"
    RECOVERY = "recovery"


class RequirementNecessity(StrEnum):
    """Whether a resolved requirement may gate its target passage."""

    REQUIRED = "required"
    SUPPORTING = "supporting"
    UNRESOLVED = "unresolved"


class RequirementProducer(StrEnum):
    """Producer class for requirement provenance."""

    DETERMINISTIC_SCORE_RULE = "deterministic-score-rule"
    METHODOLOGY_RULE = "methodology-rule"
    HUMAN_REVIEW = "human-review"


class ExerciseTemplateFamily(StrEnum):
    """Exercise families implemented by the bounded Task 9B slices."""

    DIAGNOSTIC = "diagnostic"
    PREREQUISITE = "prerequisite"
    PIECE_APPLICATION = "piece-application"
    INTEGRATION = "integration"
    RETENTION = "retention"
    TRANSFER = "transfer"


class ActivityForm(StrEnum):
    """Semantic activity forms; presentation remains downstream."""

    ORIENT = "orient"
    EXPLAIN = "explain"
    DEMONSTRATE_LISTEN = "demonstrate-listen"
    PERFORM = "perform"
    RECONNECT = "reconnect"


class CurriculumNodeKind(StrEnum):
    """Implemented node kinds from the frozen graph vocabulary."""

    PRIMITIVE = "primitive"
    DIAGNOSTIC = "diagnostic"
    PREREQUISITE = "prerequisite"
    APPLICATION = "application"
    INTEGRATION = "integration"
    RETENTION = "retention"
    TRANSFER = "transfer"


class CurriculumEdgeKind(StrEnum):
    """Implemented edge kinds from the frozen graph vocabulary."""

    REQUIRES = "requires"
    REALIZED_BY = "realized-by"
    ON_SATISFIED = "on-satisfied"
    ON_UNCONFIRMED = "on-unconfirmed"
    RETURN_TO = "return-to"
    COMPONENT_OF = "component-of"
    CHECKPOINT_AFTER = "checkpoint-after"
    SCHEDULE_RETENTION = "schedule-retention"
    SCHEDULE_TRANSFER = "schedule-transfer"


class TempoReferenceAuthority(StrEnum):
    """Authority of the reference tempo used by one generated route."""

    SOURCE = "source-authoritative"
    CALLER = "caller-reference"


class TempoPlanState(StrEnum):
    """Whether an exact controlled-tempo condition is available."""

    DIAGNOSTIC_REQUIRED = "diagnostic-required"
    CONTROLLED = "controlled"
    PERFORMANCE_TEMPO_STABLE = "performance-tempo-stable"


class TempoPolicyAction(StrEnum):
    """Explicit ADR-0012 tempo actions; none imply musical mastery."""

    PROBE = "probe-tempo"
    MAINTAIN = "maintain-tempo"
    INCREASE = "increase-tempo"
    DECREASE = "decrease-tempo"
    REMOVE_CONSTRAINT = "remove-tempo-constraint"


class AcquisitionStageKind(StrEnum):
    """Ordered conditions in the Task 9B.3 acquisition graph slice."""

    TEMPO_DIAGNOSTIC = "tempo-diagnostic"
    COMPONENT_ACQUISITION = "component-acquisition"
    SELF_PACED_COORDINATION = "self-paced-coordination"
    PULSE_INTEGRATION = "pulse-integration"
    PHRASE_CONTROLLED_TEMPO = "phrase-controlled-tempo"
    LEARNED_TO_DATE = "learned-to-date"
    TEMPO_DEVELOPMENT = "tempo-development"


class RetentionCheckpointKind(StrEnum):
    """Named delayed retrieval checkpoints in the frozen Beginner policy."""

    R1 = "R1"
    R2 = "R2"


class RetentionAnchorKind(StrEnum):
    """Evidence event from which one retention delay is measured."""

    ACQUISITION = "independent-acquisition"
    PASSING_R1 = "passing-R1"


class LastingSkillStageKind(StrEnum):
    """Post-acquisition evidence families added by Task 9B.4."""

    RETENTION = "retention"
    TRANSFER = "transfer"


@dataclass(frozen=True, slots=True)
class DiagnosticParameter:
    """One typed stable diagnostic parameter."""

    name: str
    value_type: str
    value: str


@dataclass(frozen=True, slots=True)
class CurriculumDiagnostic:
    """Machine-stable curriculum diagnostic; UI text is a later projection."""

    code: str
    severity: DiagnosticSeverity
    outcome: ArtifactResolution
    path: str
    related_ids: tuple[str, ...] = ()
    parameters: tuple[DiagnosticParameter, ...] = ()


@dataclass(frozen=True, slots=True)
class SemanticReference:
    """Reference that prevents identity from drifting across boundaries."""

    artifact_type: str
    id: str
    semantic_fingerprint: str


@dataclass(frozen=True, slots=True)
class RuleReference:
    """Versioned deterministic or methodology rule reference."""

    rule_id: str
    rule_version: str
    semantic_fingerprint: str


@dataclass(frozen=True, slots=True)
class ScoreRange:
    """Half-open exact score-time range."""

    start: Fraction
    end: Fraction


@dataclass(frozen=True, slots=True)
class PracticeLayerGroup:
    """One stable group of canonical layer members in a practice scope."""

    id: str
    analysis_layer_ids: tuple[str, ...]
    staff_ids: tuple[str, ...]
    voice_ids: tuple[str, ...]
    measure_ids: tuple[str, ...]
    event_ids: tuple[str, ...]
    continuity_evidence_refs: tuple[str, ...] = ()
    review_ref: str | None = None


@dataclass(frozen=True, slots=True)
class ScopeOmission:
    """One explicit omission from otherwise complete event membership."""

    event_id: str
    reason_code: str
    rule_or_review_ref: str
    visible_as_context: bool


@dataclass(frozen=True, slots=True)
class PracticeInterpretation:
    """Provenance for notation grouping and any execution interpretation."""

    producer: InterpretationProducer
    rule_ref: RuleReference
    source_evidence_refs: tuple[str, ...]
    analysis_evidence_refs: tuple[str, ...]
    rationale_code: str
    uncertainty: str | None = None


@dataclass(frozen=True, slots=True)
class PracticeScopeAssignment:
    """Exact active, contextual, and omitted canonical material for practice."""

    schema_version: str
    id: str
    semantic_fingerprint: str
    diagnostics: tuple[CurriculumDiagnostic, ...]
    score_package_digest: str
    score_id: str
    part_id: str
    score_range: ScoreRange
    canonical_anchor_set_id: str
    analysis_version: str
    derivation_rule: RuleReference
    notation_condition: NotationCondition
    layer_groups: tuple[PracticeLayerGroup, ...]
    event_universe_ids: tuple[str, ...]
    active_target_ids: tuple[str, ...]
    inactive_context_ids: tuple[str, ...]
    omissions: tuple[ScopeOmission, ...]
    component_scope_ids: tuple[str, ...]
    execution_assignment: ExecutionAssignment
    interpretation: PracticeInterpretation
    review_state: ReviewState
    review_ref: str | None
    resolution: ArtifactResolution


@dataclass(frozen=True, slots=True)
class ParameterDefinition:
    """Typed parameter admitted by one primitive definition."""

    name: str
    value_type: str
    required: bool


@dataclass(frozen=True, slots=True)
class TypedParameter:
    """Exact passage-specific parameter; arbitrary JSON maps are forbidden."""

    name: str
    value_type: str
    value: str


@dataclass(frozen=True, slots=True)
class LearningPrimitive:
    """Reusable learner-independent capability in TMM-PRIMITIVES-0.1."""

    schema_version: str
    id: str
    semantic_fingerprint: str
    diagnostics: tuple[CurriculumDiagnostic, ...]
    catalogue_id: str
    catalogue_version: str
    family: PrimitiveFamily
    capability: str
    definition: str
    parameter_schema: tuple[ParameterDefinition, ...]
    prerequisite_ids: tuple[str, ...]
    observable_dimensions: tuple[str, ...]
    unobservable_dimensions: tuple[str, ...]
    evidence_contexts: tuple[str, ...]
    resolution: ArtifactResolution


@dataclass(frozen=True, slots=True)
class PassageSkillRequirement:
    """Why one exact practice scope requires one learning primitive."""

    schema_version: str
    id: str
    semantic_fingerprint: str
    diagnostics: tuple[CurriculumDiagnostic, ...]
    primitive_ref: SemanticReference
    practice_scope_ref: SemanticReference
    target_parameters: tuple[TypedParameter, ...]
    canonical_evidence_refs: tuple[str, ...]
    analysis_evidence_refs: tuple[str, ...]
    derivation_rule: RuleReference
    producer: RequirementProducer
    role: RequirementRole
    necessity: RequirementNecessity
    prerequisite_requirement_ids: tuple[str, ...]
    required_dimensions: tuple[str, ...]
    unobservable_dimensions: tuple[str, ...]
    resolution: ArtifactResolution
    review_ref: str | None


@dataclass(frozen=True, slots=True)
class PassageRequirementSet:
    """Deterministic 9B.1 result consumed by later graph generation."""

    analysis_id: str
    anchor_sets: tuple[CanonicalAnchorSet, ...]
    scopes: tuple[PracticeScopeAssignment, ...]
    primitives: tuple[LearningPrimitive, ...]
    requirements: tuple[PassageSkillRequirement, ...]
    diagnostics: tuple[CurriculumDiagnostic, ...] = ()


@dataclass(frozen=True, slots=True)
class CanonicalExcerptMaterial:
    """Canonical source material referenced without copying score facts."""

    material_type: str
    score_package_digest: str
    score_id: str
    practice_scope_ref: SemanticReference
    canonical_anchor_set_id: str
    active_target_ids: tuple[str, ...]
    inactive_context_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ExerciseActivity:
    """One ordered semantic activity in a generated exercise."""

    id: str
    form: ActivityForm
    evidence_producing: bool


@dataclass(frozen=True, slots=True)
class ExerciseSupportEnvelope:
    """Named support conditions admitted by an exercise instance."""

    initial_condition: str
    permitted_conditions: tuple[str, ...]
    independent_condition: str | None


@dataclass(frozen=True, slots=True)
class ExerciseEvidenceExit:
    """One dimension-specific evidence exit."""

    dimension: str
    evidence_context: str
    minimum_state: str


@dataclass(frozen=True, slots=True)
class ExerciseInstance:
    """Immutable prerequisite, application, diagnostic, or integration exercise."""

    schema_version: str
    id: str
    semantic_fingerprint: str
    diagnostics: tuple[CurriculumDiagnostic, ...]
    template_ref: SemanticReference
    requirement_ref: SemanticReference
    practice_scope_ref: SemanticReference
    material: CanonicalExcerptMaterial
    activity_sequence: tuple[ExerciseActivity, ...]
    support_envelope: ExerciseSupportEnvelope
    required_evidence_exits: tuple[ExerciseEvidenceExit, ...]
    return_target_id: str
    generation_inputs: tuple[SemanticReference, ...]
    generation_rule: RuleReference
    resolution: ArtifactResolution


@dataclass(frozen=True, slots=True)
class CurriculumGraphNode:
    """Frozen Task 9A.8 graph-node shape used by DEV-009 graph slices."""

    id: str
    kind: CurriculumNodeKind
    scope_ref: SemanticReference | None
    primitive_ref: SemanticReference | None
    requirement_ref: SemanticReference | None
    exercise_ref: SemanticReference | None
    component_node_ids: tuple[str, ...]
    budget_key: str | None
    terminal_outcome: str | None


@dataclass(frozen=True, slots=True)
class CurriculumGraphEdge:
    """Frozen Task 9A.8 graph-edge shape used by DEV-009 graph slices."""

    id: str
    kind: CurriculumEdgeKind
    source_node_id: str
    target_node_id: str
    terminal_outcome: str | None
    guard: str
    budget_key: str | None
    return_node_id: str | None
    precedence: int


@dataclass(frozen=True, slots=True)
class RequirementTeachingBranch:
    """Diagnostic and prerequisite route for one exact passage requirement."""

    requirement_ref: SemanticReference
    diagnostic_node_id: str
    prerequisite_node_id: str
    application_node_id: str
    prerequisite_requirement_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class PrerequisiteBranchSet:
    """Composable Task 9B.2 graph slice; not yet the complete curriculum graph."""

    graph_identity: str
    analysis_id: str
    nodes: tuple[CurriculumGraphNode, ...]
    edges: tuple[CurriculumGraphEdge, ...]
    exercises: tuple[ExerciseInstance, ...]
    branches: tuple[RequirementTeachingBranch, ...]
    diagnostics: tuple[CurriculumDiagnostic, ...]
    resolution: ArtifactResolution


@dataclass(frozen=True, slots=True)
class TempoConfiguration:
    """Frozen numeric hypotheses for the first ADR-0012 policy baseline."""

    schema_version: str
    id: str
    semantic_fingerprint: str
    policy_identity: str
    diagnostic_probe_percentages: tuple[int, ...]
    tempo_increment_percentage: int
    tempo_tolerance_percentage: int
    diagnostic_attempt_budget: int
    acquisition_retry_budget: int
    tempo_probe_retry_budget: int
    remediation_budget: int
    phrase_group_size: int
    stable_performance_passes: int


@dataclass(frozen=True, slots=True)
class CompatibleTempoEvidence:
    """Compatible evidence for one exact scope and support condition."""

    practice_scope_ref: SemanticReference
    support_condition: str
    controlled_percentage: int
    supported_ceiling_percentage: int
    required_non_tempo_gates_passed: bool
    pulse_gate_passed: bool
    evidence_refs: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ControlledTempoPlan:
    """Replayable initial tempo selection for one exact practice scope."""

    schema_version: str
    id: str
    semantic_fingerprint: str
    practice_scope_ref: SemanticReference
    configuration_ref: SemanticReference
    reference_tempo_bpm: Fraction
    reference_authority: TempoReferenceAuthority
    state: TempoPlanState
    current_controlled_percentage: int | None
    tested_percentage: int | None
    supported_ceiling_percentage: int | None
    diagnostic_probe_percentages: tuple[int, ...]
    evidence_refs: tuple[str, ...]
    reason_code: str


@dataclass(frozen=True, slots=True)
class TempoProbeResult:
    """Exact result of one bounded tempo probe."""

    tested_percentage: int
    required_non_tempo_gates_passed: bool
    pulse_gate_passed: bool
    evidence_ref: str


@dataclass(frozen=True, slots=True)
class TempoTransition:
    """One deterministic tempo action and resulting replayable condition."""

    action: TempoPolicyAction
    previous_controlled_percentage: int | None
    tested_percentage: int
    resulting_controlled_percentage: int | None
    resulting_supported_ceiling_percentage: int | None
    next_probe_percentage: int | None
    evidence_ref: str
    reason_code: str


@dataclass(frozen=True, slots=True)
class AcquisitionStage:
    """One ordered layer, coordination, cumulative, or tempo stage."""

    id: str
    kind: AcquisitionStageKind
    order: int
    node_id: str
    practice_scope_ref: SemanticReference
    component_node_ids: tuple[str, ...]
    tempo_plan_ref: SemanticReference
    evidence_context: str


@dataclass(frozen=True, slots=True)
class AcquisitionGraphSlice:
    """Composable Task 9B.3 graph slice, prior to retention and transfer."""

    schema_version: str
    id: str
    semantic_fingerprint: str
    graph_identity: str
    analysis_id: str
    tempo_configuration: TempoConfiguration
    tempo_plans: tuple[ControlledTempoPlan, ...]
    nodes: tuple[CurriculumGraphNode, ...]
    edges: tuple[CurriculumGraphEdge, ...]
    exercises: tuple[ExerciseInstance, ...]
    branches: tuple[RequirementTeachingBranch, ...]
    stages: tuple[AcquisitionStage, ...]
    diagnostics: tuple[CurriculumDiagnostic, ...]
    resolution: ArtifactResolution


@dataclass(frozen=True, slots=True)
class RetentionWindow:
    """Exact relative due time and valid observation window for one check."""

    schema_version: str
    id: str
    semantic_fingerprint: str
    checkpoint: RetentionCheckpointKind
    anchor: RetentionAnchorKind
    due_after_hours: int
    valid_after_hours: int
    valid_before_hours: int
    rule_ref: RuleReference


@dataclass(frozen=True, slots=True)
class RetentionSchedule:
    """Two-check schedule for one exact source requirement and target."""

    schema_version: str
    id: str
    semantic_fingerprint: str
    source_requirement_ref: SemanticReference
    source_scope_ref: SemanticReference
    source_node_id: str
    return_node_id: str
    windows: tuple[RetentionWindow, ...]


@dataclass(frozen=True, slots=True)
class TransferTargetRequest:
    """Caller-resolved source/target selection; generation never guesses it."""

    source_requirement_id: str
    target_requirement_id: str
    difference_dimensions: tuple[str, ...]
    difference_evidence_refs: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class TransferTargetAssignment:
    """Proven same-primitive, materially different transfer relationship."""

    schema_version: str
    id: str
    semantic_fingerprint: str
    source_requirement_ref: SemanticReference
    source_scope_ref: SemanticReference
    target_requirement_ref: SemanticReference
    target_scope_ref: SemanticReference
    primitive_ref: SemanticReference
    difference_dimensions: tuple[str, ...]
    difference_evidence_refs: tuple[str, ...]
    training_state_guard: str
    similarity_rule: RuleReference
    return_node_id: str
    resolution: ArtifactResolution


@dataclass(frozen=True, slots=True)
class LastingSkillStage:
    """One separately evidenced delayed retention or transfer node."""

    id: str
    kind: LastingSkillStageKind
    order: int
    node_id: str
    requirement_ref: SemanticReference
    practice_scope_ref: SemanticReference
    source_requirement_ref: SemanticReference
    source_node_id: str
    return_node_id: str
    schedule_ref: SemanticReference | None
    transfer_target_ref: SemanticReference | None
    evidence_context: str


@dataclass(frozen=True, slots=True)
class LastingSkillGraphSlice:
    """Composable Task 9B.4 graph with isolated retention and transfer."""

    schema_version: str
    id: str
    semantic_fingerprint: str
    graph_identity: str
    source_analysis_id: str
    transfer_analysis_id: str
    acquisition_graph_ref: SemanticReference
    nodes: tuple[CurriculumGraphNode, ...]
    edges: tuple[CurriculumGraphEdge, ...]
    exercises: tuple[ExerciseInstance, ...]
    retention_schedules: tuple[RetentionSchedule, ...]
    transfer_targets: tuple[TransferTargetAssignment, ...]
    stages: tuple[LastingSkillStage, ...]
    diagnostics: tuple[CurriculumDiagnostic, ...]
    resolution: ArtifactResolution


@dataclass(frozen=True, slots=True)
class CurriculumRendererTarget:
    """One canonical scope member addressable in the verified notation bundle."""

    canonical_id: str
    canonical_kind: str
    renderer_anchor: str


@dataclass(frozen=True, slots=True)
class CurriculumPassagePresentation:
    """A resolved practice scope projected onto complete visible notation."""

    schema_version: str
    id: str
    semantic_fingerprint: str
    analysis_id: str
    package_id: str
    score_id: str
    part_id: str
    practice_scope_ref: SemanticReference
    score_range: ScoreRange
    notation_condition: NotationCondition
    execution_assignment: ExecutionAssignment
    measure_ids: tuple[str, ...]
    event_universe_ids: tuple[str, ...]
    visible_event_ids: tuple[str, ...]
    active_target_ids: tuple[str, ...]
    inactive_context_ids: tuple[str, ...]
    omitted_event_ids: tuple[str, ...]
    visible_omitted_event_ids: tuple[str, ...]
    measure_renderer_targets: tuple[CurriculumRendererTarget, ...]
    active_renderer_targets: tuple[CurriculumRendererTarget, ...]
    inactive_renderer_targets: tuple[CurriculumRendererTarget, ...]
    visible_omitted_renderer_targets: tuple[CurriculumRendererTarget, ...]
    notation_renderer_sha256: str
    diagnostics: tuple[CurriculumDiagnostic, ...]
    resolution: ArtifactResolution


@dataclass(frozen=True, slots=True)
class CurriculumGuidanceItem:
    """One provenance-preserving explanation and action for active material."""

    id: str
    requirement_ref: SemanticReference
    primitive_ref: SemanticReference
    primitive_family: PrimitiveFamily
    heading: str
    explanation: str
    action_prompt: str
    reconnect_prompt: str
    target_parameters: tuple[TypedParameter, ...]
    focus_event_ids: tuple[str, ...]
    canonical_evidence_refs: tuple[str, ...]
    analysis_evidence_refs: tuple[str, ...]
    derivation_rule: RuleReference


@dataclass(frozen=True, slots=True)
class CurriculumPassageGuidance:
    """Traceable learner guidance for one exact passage presentation."""

    schema_version: str
    id: str
    semantic_fingerprint: str
    analysis_id: str
    package_id: str
    score_id: str
    presentation_ref: SemanticReference
    practice_scope_ref: SemanticReference
    notation_condition: NotationCondition
    execution_assignment: ExecutionAssignment
    items: tuple[CurriculumGuidanceItem, ...]
    diagnostics: tuple[CurriculumDiagnostic, ...]
    resolution: ArtifactResolution


@dataclass(frozen=True, slots=True)
class CurriculumFundamentalExplanation:
    """Functional deterministic text for one graph-declared prerequisite."""

    schema_version: str
    id: str
    semantic_fingerprint: str
    analysis_id: str
    package_id: str
    score_id: str
    requirement_ref: SemanticReference
    primitive_ref: SemanticReference
    practice_scope_ref: SemanticReference
    presentation_ref: SemanticReference
    prerequisite_exercise_ref: SemanticReference
    application_exercise_ref: SemanticReference
    prerequisite_node_id: str
    return_node_id: str
    heading: str
    explanation: str
    why_it_matters: str
    action_prompt: str
    return_prompt: str
    target_parameters: tuple[TypedParameter, ...]
    focus_event_ids: tuple[str, ...]
    generation_rule: RuleReference
    diagnostics: tuple[CurriculumDiagnostic, ...]
    resolution: ArtifactResolution


@dataclass(frozen=True, slots=True)
class CurriculumFundamentalDemonstration:
    """Existing notation/playback/piano bound to one prerequisite activity."""

    schema_version: str
    id: str
    semantic_fingerprint: str
    analysis_id: str
    package_id: str
    score_id: str
    explanation_ref: SemanticReference
    requirement_ref: SemanticReference
    primitive_ref: SemanticReference
    practice_scope_ref: SemanticReference
    presentation_ref: SemanticReference
    prerequisite_exercise_ref: SemanticReference
    prerequisite_node_id: str
    return_node_id: str
    demonstration_activity_id: str
    focus_event_ids: tuple[str, ...]
    playback_source_event_ids: tuple[str, ...]
    silent_active_event_ids: tuple[str, ...]
    playback_plan_sha256: str
    tempo_bpm: Fraction
    generation_rule: RuleReference
    diagnostics: tuple[CurriculumDiagnostic, ...]
    resolution: ArtifactResolution


@dataclass(frozen=True, slots=True)
class CurriculumFundamentalPractice:
    """Playable learner response for one graph-declared prerequisite."""

    schema_version: str
    id: str
    semantic_fingerprint: str
    analysis_id: str
    package_id: str
    score_id: str
    explanation_ref: SemanticReference
    demonstration_ref: SemanticReference
    requirement_ref: SemanticReference
    primitive_ref: SemanticReference
    practice_scope_ref: SemanticReference
    presentation_ref: SemanticReference
    prerequisite_exercise_ref: SemanticReference
    prerequisite_node_id: str
    return_node_id: str
    performance_activity_id: str
    practice_mode: PracticeMode
    support_envelope: ExerciseSupportEnvelope
    required_evidence_exits: tuple[ExerciseEvidenceExit, ...]
    expected_performance_id: str
    expected_target_fingerprint: str
    expected_active_event_ids: tuple[str, ...]
    expected_note_ids: tuple[str, ...]
    target_dimensions: tuple[ObservationDimension, ...]
    expected_performance_sha256: str
    tempo_bpm: Fraction
    generation_rule: RuleReference
    diagnostics: tuple[CurriculumDiagnostic, ...]
    resolution: ArtifactResolution


@dataclass(frozen=True, slots=True)
class CurriculumLearningOutcome:
    """Reward-free factual result of one exact learner attempt."""

    schema_version: str
    id: str
    semantic_fingerprint: str
    run_id: str
    practice_ref: SemanticReference
    expected_performance_ref: SemanticReference
    attempt_ref: SemanticReference
    calibration_ref: SemanticReference
    support_state_ref: SemanticReference
    completion: AttemptCompletion
    raw_message_ids: tuple[str, ...]
    normalized_event_ids: tuple[str, ...]
    observation_refs: tuple[SemanticReference, ...]
    generation_rule: RuleReference
    diagnostics: tuple[CurriculumDiagnostic, ...]
    resolution: ArtifactResolution


@dataclass(frozen=True, slots=True)
class ResearchRewardComponent:
    """One exact, independently inspectable research-reward component."""

    component_id: str
    dimension: ObservationDimension | None
    status: ResearchRewardComponentStatus
    value: Fraction | None
    matched_observation_count: int
    discrepancy_observation_count: int
    unresolved_observation_count: int
    observation_refs: tuple[SemanticReference, ...]
    calculation_rule: RuleReference
    reason_code: str


@dataclass(frozen=True, slots=True)
class CurriculumResearchReward:
    """Versioned reward components projected without changing raw outcomes."""

    schema_version: str
    id: str
    semantic_fingerprint: str
    run_id: str
    outcome_ref: SemanticReference
    expected_performance_ref: SemanticReference
    components: tuple[ResearchRewardComponent, ...]
    generation_rule: RuleReference
    diagnostics: tuple[CurriculumDiagnostic, ...]
    resolution: ArtifactResolution


@dataclass(frozen=True, slots=True)
class CurriculumGameReward:
    """Presentation-only acknowledgement derived from an authoritative result."""

    schema_version: str
    id: str
    semantic_fingerprint: str
    run_id: str
    outcome_ref: SemanticReference
    research_reward_ref: SemanticReference
    signal: GameRewardSignal
    message_code: str
    source_component_ids: tuple[str, ...]
    generation_rule: RuleReference
    diagnostics: tuple[CurriculumDiagnostic, ...]
    resolution: ArtifactResolution


@dataclass(frozen=True, slots=True)
class CurriculumPieceReturn:
    """Policy-authorized handoff from prerequisite practice to its passage."""

    schema_version: str
    id: str
    semantic_fingerprint: str
    analysis_id: str
    package_id: str
    score_id: str
    practice_ref: SemanticReference
    requirement_ref: SemanticReference
    primitive_ref: SemanticReference
    practice_scope_ref: SemanticReference
    presentation_ref: SemanticReference
    prerequisite_exercise_ref: SemanticReference
    application_exercise_ref: SemanticReference
    graph_ref: SemanticReference
    mastery_projection_ref: SemanticReference
    unlock_decision_ref: SemanticReference
    support_state_ref: SemanticReference
    prerequisite_node_id: str
    return_node_id: str
    return_edge_id: str
    reconnect_activity_id: str
    completed_attempt_ids: tuple[str, ...]
    evidence_record_ids: tuple[str, ...]
    active_event_ids: tuple[str, ...]
    generation_rule: RuleReference
    diagnostics: tuple[CurriculumDiagnostic, ...]
    resolution: ArtifactResolution


@dataclass(frozen=True, slots=True)
class CurriculumEvidenceRecord:
    """One support-bound factual result for an exact requirement and scope."""

    schema_version: str
    id: str
    semantic_fingerprint: str
    attempt_id: str
    expected_target_ref: SemanticReference
    requirement_ref: SemanticReference
    primitive_ref: SemanticReference
    practice_scope_ref: SemanticReference
    component_scope_refs: tuple[SemanticReference, ...]
    notation_condition: NotationCondition
    execution_assignment: ExecutionAssignment
    dimension: ObservationDimension
    evidence_context: EvidenceContext
    result: CurriculumEvidenceResult
    observation_ids: tuple[str, ...]
    context_observation_ids: tuple[str, ...]
    support_state_ref: SemanticReference
    limitations: tuple[str, ...]
    resolution: ArtifactResolution


@dataclass(frozen=True, slots=True)
class CurriculumDimensionDecision:
    """One required dimension kept distinct in a mastery projection."""

    dimension: ObservationDimension
    result: CurriculumEvidenceResult | None
    evidence_record_ids: tuple[str, ...]
    passing_attempt_ids: tuple[str, ...]
    reason_code: str


@dataclass(frozen=True, slots=True)
class CurriculumMasteryProjection:
    """Replayable node-local mastery result over compatible factual evidence."""

    schema_version: str
    id: str
    semantic_fingerprint: str
    graph_ref: SemanticReference
    node_id: str
    exercise_ref: SemanticReference
    requirement_ref: SemanticReference
    primitive_ref: SemanticReference
    practice_scope_ref: SemanticReference
    component_scope_refs: tuple[SemanticReference, ...]
    evidence_context: EvidenceContext
    support_state_ref: SemanticReference
    required_dimensions: tuple[ObservationDimension, ...]
    dimension_decisions: tuple[CurriculumDimensionDecision, ...]
    evaluated_attempt_ids: tuple[str, ...]
    complete_passing_attempt_ids: tuple[str, ...]
    minimum_state: str
    status: CurriculumMasteryStatus
    resolution: ArtifactResolution


@dataclass(frozen=True, slots=True)
class RejectedCurriculumEdge:
    """One graph-declared successor rejected by a named deterministic guard."""

    edge_id: str
    reason_code: str


@dataclass(frozen=True, slots=True)
class CurriculumUnlockDecision:
    """Exactly one deterministic outcome for one authoritative projection."""

    schema_version: str
    id: str
    semantic_fingerprint: str
    policy_identity: str
    graph_ref: SemanticReference
    current_node_id: str
    projection_ref: SemanticReference
    previously_satisfied_node_ids: tuple[str, ...]
    eligible_edge_ids: tuple[str, ...]
    rejected_edges: tuple[RejectedCurriculumEdge, ...]
    selected_edge_id: str | None
    next_node_id: str | None
    action: CurriculumUnlockAction
    reason_code: str
    resolution: ArtifactResolution


@dataclass(frozen=True, slots=True)
class CurriculumBudgetCounter:
    """One exact bounded-policy counter before a decision is made."""

    key: str
    used: int
    limit: int


@dataclass(frozen=True, slots=True)
class CurriculumDecisionSnapshot:
    """Immutable state and observation knowledge before one policy decision."""

    schema_version: str
    id: str
    semantic_fingerprint: str
    snapshot_version: str
    run_id: str
    learner_context_id: str
    decision_sequence: int
    score_package_digest: str
    score_id: str
    graph_ref: SemanticReference
    current_node_id: str
    exercise_ref: SemanticReference
    requirement_ref: SemanticReference
    primitive_ref: SemanticReference
    practice_scope_ref: SemanticReference
    component_scope_refs: tuple[SemanticReference, ...]
    support_state_ref: SemanticReference
    policy_identity: str
    policy_configuration_ref: SemanticReference
    mastery_projection_ref: SemanticReference
    evidence_snapshot_sequence: int
    evidence_snapshot_fingerprint: str
    evidence_record_refs: tuple[SemanticReference, ...]
    observation_refs: tuple[SemanticReference, ...]
    attempt_sequence: tuple[str, ...]
    previously_satisfied_node_ids: tuple[str, ...]
    budget_state: tuple[CurriculumBudgetCounter, ...]
    curriculum_contract_version: str
    performance_contract_version: str
    evidence_archive_contract_version: str
    resolution: ArtifactResolution


@dataclass(frozen=True, slots=True)
class CurriculumGuardResult:
    """One stable evaluation of a guard governing an action candidate."""

    guard: str
    passed: bool
    reason_code: str


@dataclass(frozen=True, slots=True)
class CurriculumActionCandidate:
    """One graph-declared action retained before policy selection."""

    action: CurriculumPolicyAction
    edge_id: str
    target_node_id: str
    eligibility: CurriculumActionEligibility
    guard_results: tuple[CurriculumGuardResult, ...]
    precedence: int
    tie_break_values: tuple[str, ...]
    reason_code: str


@dataclass(frozen=True, slots=True)
class CurriculumActionInventory:
    """Complete allowed/excluded graph actions for one exact snapshot."""

    schema_version: str
    id: str
    semantic_fingerprint: str
    inventory_version: str
    snapshot_ref: SemanticReference
    graph_ref: SemanticReference
    current_node_id: str
    mastery_projection_ref: SemanticReference
    policy_identity: str
    policy_configuration_ref: SemanticReference
    candidates: tuple[CurriculumActionCandidate, ...]
    resolution: ArtifactResolution


@dataclass(frozen=True, slots=True)
class CurriculumActionSelection:
    """One deterministic action selected from one exact action inventory."""

    schema_version: str
    id: str
    semantic_fingerprint: str
    selection_version: str
    snapshot_ref: SemanticReference
    inventory_ref: SemanticReference
    policy_identity: str
    policy_configuration_ref: SemanticReference
    selected_candidate: CurriculumActionCandidate
    behavior_probability: Fraction
    reason_code: str
    resolution: ArtifactResolution


@dataclass(frozen=True, slots=True)
class CurriculumTransitionResult:
    """Exact factual result and next state following one selected action."""

    schema_version: str
    id: str
    semantic_fingerprint: str
    transition_version: str
    selection_ref: SemanticReference
    outcome_ref: SemanticReference
    research_reward_ref: SemanticReference
    next_snapshot_ref: SemanticReference
    resolution: ArtifactResolution


@dataclass(frozen=True, slots=True)
class CurriculumExperimentManifest:
    """Run-level index over one complete bounded deterministic trajectory."""

    schema_version: str
    id: str
    semantic_fingerprint: str
    manifest_version: str
    run_id: str
    score_package_digest: str
    score_id: str
    learner_context_id: str
    graph_ref: SemanticReference
    policy_identity: str
    policy_configuration_ref: SemanticReference
    snapshot_refs: tuple[SemanticReference, ...]
    action_inventory_refs: tuple[SemanticReference, ...]
    action_selection_refs: tuple[SemanticReference, ...]
    outcome_refs: tuple[SemanticReference, ...]
    research_reward_refs: tuple[SemanticReference, ...]
    transition_refs: tuple[SemanticReference, ...]
    first_decision_sequence: int
    last_decision_sequence: int
    curriculum_contract_version: str
    performance_contract_version: str
    evidence_archive_contract_version: str
    status: CurriculumExperimentStatus
    resolution: ArtifactResolution


@dataclass(frozen=True, slots=True)
class CurriculumMetricInputRecord:
    """Content-addressed inputs for one transition's governed metrics."""

    decision_sequence: int
    prior_snapshot_ref: SemanticReference
    action_inventory_ref: SemanticReference
    action_selection_ref: SemanticReference
    outcome_ref: SemanticReference
    research_reward_ref: SemanticReference
    transition_ref: SemanticReference
    next_snapshot_ref: SemanticReference
    metric_input_fingerprint: str


@dataclass(frozen=True, slots=True)
class CurriculumMetricSourceRecord:
    """App-owned authority from which de-identified metric views may derive."""

    schema_version: str
    id: str
    semantic_fingerprint: str
    source_record_version: str
    manifest_ref: SemanticReference
    run_id: str
    score_package_digest: str
    score_id: str
    graph_ref: SemanticReference
    policy_identity: str
    policy_configuration_ref: SemanticReference
    metric_inputs: tuple[CurriculumMetricInputRecord, ...]
    first_decision_sequence: int
    last_decision_sequence: int
    curriculum_contract_version: str
    performance_contract_version: str
    evidence_archive_contract_version: str
    resolution: ArtifactResolution


@dataclass(frozen=True, slots=True)
class CurriculumMetricComponentSummary:
    """One explicitly allowlisted exact research component for export."""

    component_id: str
    dimension: ObservationDimension | None
    status: ResearchRewardComponentStatus
    value: Fraction | None
    matched_observation_count: int
    discrepancy_observation_count: int
    unresolved_observation_count: int
    reason_code: str


@dataclass(frozen=True, slots=True)
class CurriculumMetricDecisionSummary:
    """De-identified metrics for one manifest-governed decision transition."""

    decision_sequence: int
    metric_input_fingerprint: str
    prior_snapshot_ref: SemanticReference
    action_selection_ref: SemanticReference
    outcome_ref: SemanticReference
    research_reward_ref: SemanticReference
    next_snapshot_ref: SemanticReference
    current_node_id: str
    next_node_id: str
    prior_support_state_ref: SemanticReference
    next_support_state_ref: SemanticReference
    selected_action: CurriculumPolicyAction
    behavior_probability: Fraction
    completion: AttemptCompletion
    reward_components: tuple[CurriculumMetricComponentSummary, ...]


@dataclass(frozen=True, slots=True)
class CurriculumMetricSummaryExport:
    """Tracker-neutral de-identified projection from the app-owned authority."""

    schema_version: str
    id: str
    semantic_fingerprint: str
    summary_version: str
    source_record_ref: SemanticReference
    score_id: str
    graph_ref: SemanticReference
    policy_identity: str
    policy_configuration_ref: SemanticReference
    decision_metrics: tuple[CurriculumMetricDecisionSummary, ...]
    first_decision_sequence: int
    last_decision_sequence: int
    resolution: ArtifactResolution
