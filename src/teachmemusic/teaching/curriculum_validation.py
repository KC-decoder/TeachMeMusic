"""Fail-closed validation for DEV-009 curriculum contracts."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from fractions import Fraction

from teachmemusic.analysis import ScoreAnalysis
from teachmemusic.performance import (
    PERFORMANCE_CONTRACT_VERSION,
    AttemptCompletion,
    CalibrationProfile,
    ExpectedPerformance,
    LearnerAttempt,
    Observation,
    ObservationDimension,
    ObservationStatus,
)
from teachmemusic.performance.validation import is_stable_id
from teachmemusic.score import CanonicalMusicPackage
from teachmemusic.viewer import PlaybackPlan, playback_plan_to_dict

from .contracts import (
    EVIDENCE_ARCHIVE_CONTRACT_VERSION,
    EvidenceContext,
    PracticeMode,
    SupportState,
)
from .curriculum_contracts import (
    ACTION_INVENTORY_VERSION,
    ACTION_SELECTION_VERSION,
    CURRICULUM_CONTRACT_VERSION,
    CURRICULUM_GRAPH_ID,
    DECISION_SNAPSHOT_VERSION,
    EXPERIMENT_MANIFEST_VERSION,
    FUNDAMENTAL_DEMONSTRATION_VERSION,
    FUNDAMENTAL_EXPLANATION_VERSION,
    FUNDAMENTAL_PRACTICE_VERSION,
    FUNDAMENTAL_RETURN_VERSION,
    GAME_REWARD_VERSION,
    LASTING_SKILL_GRAPH_ID,
    LEARNING_OUTCOME_VERSION,
    METRIC_SOURCE_RECORD_VERSION,
    METRIC_SUMMARY_VERSION,
    PRIMITIVE_CATALOGUE_ID,
    RESEARCH_REWARD_VERSION,
    TEMPO_POLICY_ID,
    TRANSITION_RESULT_VERSION,
    AcquisitionGraphSlice,
    AcquisitionStageKind,
    ActivityForm,
    ArtifactResolution,
    ControlledTempoPlan,
    CurriculumActionCandidate,
    CurriculumActionEligibility,
    CurriculumActionInventory,
    CurriculumActionSelection,
    CurriculumDecisionSnapshot,
    CurriculumEdgeKind,
    CurriculumEvidenceRecord,
    CurriculumEvidenceResult,
    CurriculumExperimentManifest,
    CurriculumExperimentStatus,
    CurriculumFundamentalDemonstration,
    CurriculumFundamentalExplanation,
    CurriculumFundamentalPractice,
    CurriculumGameReward,
    CurriculumGraphEdge,
    CurriculumGraphNode,
    CurriculumLearningOutcome,
    CurriculumMasteryProjection,
    CurriculumMasteryStatus,
    CurriculumMetricSourceRecord,
    CurriculumMetricSummaryExport,
    CurriculumNodeKind,
    CurriculumPassageGuidance,
    CurriculumPassagePresentation,
    CurriculumPieceReturn,
    CurriculumRendererTarget,
    CurriculumResearchReward,
    CurriculumTransitionResult,
    CurriculumUnlockAction,
    CurriculumUnlockDecision,
    ExecutionAssignment,
    ExerciseInstance,
    GameRewardSignal,
    LastingSkillGraphSlice,
    LastingSkillStageKind,
    LearningPrimitive,
    PassageRequirementSet,
    PassageSkillRequirement,
    PracticeScopeAssignment,
    PrerequisiteBranchSet,
    PrimitiveFamily,
    RequirementNecessity,
    ResearchRewardComponentStatus,
    RetentionAnchorKind,
    RetentionCheckpointKind,
    RetentionSchedule,
    RetentionWindow,
    ReviewState,
    RuleReference,
    SemanticReference,
    TempoConfiguration,
    TempoPlanState,
    TransferTargetAssignment,
)
from .curriculum_fingerprint import semantic_fingerprint

_SHA256 = re.compile(r"^[0-9a-f]{64}$")


@dataclass(frozen=True, slots=True)
class CurriculumValidationIssue:
    """One stable curriculum-contract invariant failure."""

    code: str
    path: str
    message: str


class CurriculumValidationError(ValueError):
    """Raised when a curriculum artifact cannot cross its public boundary."""

    def __init__(self, issues: tuple[CurriculumValidationIssue, ...]) -> None:
        if not issues:
            raise ValueError("at least one validation issue is required")
        self.issues = issues
        super().__init__(
            "; ".join(f"{item.code} at {item.path}: {item.message}" for item in issues)
        )


def validate_practice_scope(
    value: PracticeScopeAssignment,
    analysis: ScoreAnalysis | None = None,
) -> tuple[CurriculumValidationIssue, ...]:
    """Validate exact scope membership, identity, and optional analysis links."""

    issues: list[CurriculumValidationIssue] = []
    _common(value.schema_version, value.id, value.semantic_fingerprint, "scope", issues)
    if value.score_range.start >= value.score_range.end:
        _add(issues, "TMM-CONTRACT-INVALID-EXACT-VALUE", "scope.score_range", "empty range")
    _rule_reference(value.derivation_rule, "scope.derivation_rule", issues)
    _rule_reference(value.interpretation.rule_ref, "scope.interpretation.rule_ref", issues)
    _unique_ids(value.event_universe_ids, "scope.event_universe_ids", issues)
    _unique_ids(value.active_target_ids, "scope.active_target_ids", issues)
    _unique_ids(value.inactive_context_ids, "scope.inactive_context_ids", issues)
    omitted = tuple(item.event_id for item in value.omissions)
    _unique_ids(omitted, "scope.omissions", issues)
    active = set(value.active_target_ids)
    inactive = set(value.inactive_context_ids)
    omitted_set = set(omitted)
    if active & inactive or active & omitted_set or inactive & omitted_set:
        _add(
            issues,
            "TMM-SCOPE-OVERLAPPING-PARTITION",
            "scope",
            "active, context, and omitted membership overlap",
        )
    if active | inactive | omitted_set != set(value.event_universe_ids):
        _add(
            issues,
            "TMM-SCOPE-INCOMPLETE-PARTITION",
            "scope",
            "membership does not exactly cover the event universe",
        )
    if value.resolution is ArtifactResolution.RESOLVED and not active:
        _add(issues, "TMM-SCOPE-INCOMPLETE-PARTITION", "scope.active_target_ids", "empty target")
    group_ids: set[str] = set()
    grouped_events: set[str] = set()
    for index, group in enumerate(value.layer_groups):
        path = f"scope.layer_groups[{index}]"
        _stable_id(group.id, f"{path}.id", issues)
        if group.id in group_ids:
            _add(issues, "TMM-CONTRACT-DUPLICATE-ID", f"{path}.id", "duplicate group")
        group_ids.add(group.id)
        _unique_ids(group.analysis_layer_ids, f"{path}.analysis_layer_ids", issues)
        _unique_ids(group.event_ids, f"{path}.event_ids", issues)
        if not set(group.event_ids) <= active:
            _add(
                issues,
                "TMM-SCOPE-COMPONENT-MISMATCH",
                f"{path}.event_ids",
                "layer group contains an inactive event",
            )
        grouped_events.update(group.event_ids)
    if value.resolution is ArtifactResolution.RESOLVED and grouped_events != active:
        _add(
            issues,
            "TMM-SCOPE-COMPONENT-MISMATCH",
            "scope.layer_groups",
            "layer groups do not exactly cover active events",
        )
    if (
        value.resolution is ArtifactResolution.RESOLVED
        and value.notation_condition.value == "combined"
        and len(value.component_scope_ids) < 2
    ):
        _add(
            issues,
            "TMM-SCOPE-COMPONENT-MISMATCH",
            "scope.component_scope_ids",
            "combined scope requires at least two component scopes",
        )
    if value.notation_condition.value != "combined" and value.component_scope_ids:
        _add(
            issues,
            "TMM-SCOPE-COMPONENT-MISMATCH",
            "scope.component_scope_ids",
            "non-combined scope cannot declare component scopes",
        )
    if (
        value.execution_assignment is not ExecutionAssignment.UNASSIGNED
        and value.interpretation.producer.value == "deterministic-rule"
    ):
        _add(
            issues,
            "TMM-HAND-INTERPRETATION-REQUIRED",
            "scope.execution_assignment",
            "deterministic notation grouping cannot invent a physical hand",
        )
    if value.resolution is ArtifactResolution.RESOLVED:
        if value.review_state is ReviewState.PENDING or value.review_ref is not None:
            _add(
                issues,
                "TMM-REQUIREMENT-AMBIGUOUS",
                "scope.review_state",
                "resolved scope cannot await review",
            )
    elif value.review_state is ReviewState.NOT_REQUIRED:
        _add(
            issues,
            "TMM-REQUIREMENT-AMBIGUOUS",
            "scope.review_state",
            "unresolved scope must expose review state",
        )
    _fingerprint(value, "scope", issues)
    if analysis is not None:
        if value.score_package_digest != analysis.canonical_digest_sha256:
            _add(
                issues,
                "TMM-SCOPE-FOREIGN-REFERENCE",
                "scope.score_package_digest",
                "digest does not match analysis",
            )
        if value.analysis_version != analysis.analysis_version:
            _add(
                issues,
                "TMM-CONTRACT-UNKNOWN-VERSION",
                "scope.analysis_version",
                "analysis rule version differs",
            )
        if (
            value.score_id != analysis.scope.score_id
            or value.part_id not in analysis.scope.part_ids
        ):
            _add(
                issues,
                "TMM-SCOPE-FOREIGN-REFERENCE",
                "scope.score_id",
                "score or part lies outside analysis scope",
            )
        known_events = {event_id for layer in analysis.layers for event_id in layer.event_ids}
        if set(value.event_universe_ids) != known_events:
            _add(
                issues,
                "TMM-SCOPE-FOREIGN-REFERENCE",
                "scope.event_universe_ids",
                "event universe differs from analysis scope",
            )
        known_layers = {layer.id for layer in analysis.layers}
        if any(
            layer_id not in known_layers
            for group in value.layer_groups
            for layer_id in group.analysis_layer_ids
        ):
            _add(
                issues,
                "TMM-SCOPE-FOREIGN-REFERENCE",
                "scope.layer_groups",
                "scope contains an unknown analysis layer",
            )
    return tuple(issues)


def validate_curriculum_passage_presentation(
    value: CurriculumPassagePresentation,
    scope: PracticeScopeAssignment | None = None,
) -> tuple[CurriculumValidationIssue, ...]:
    """Validate one exact practice scope projected onto verified notation."""

    issues: list[CurriculumValidationIssue] = []
    _common(
        value.schema_version,
        value.id,
        value.semantic_fingerprint,
        "passage_presentation",
        issues,
    )
    for name, identifier in (
        ("analysis_id", value.analysis_id),
        ("package_id", value.package_id),
        ("score_id", value.score_id),
        ("part_id", value.part_id),
    ):
        _stable_id(identifier, f"passage_presentation.{name}", issues)
    if value.practice_scope_ref.artifact_type != "practice-scope-assignment":
        _add(
            issues,
            "TMM-SCOPE-FOREIGN-REFERENCE",
            "passage_presentation.practice_scope_ref",
            "reference is not a practice scope",
        )
    if value.score_range.start >= value.score_range.end:
        _add(
            issues,
            "TMM-CONTRACT-INVALID-EXACT-VALUE",
            "passage_presentation.score_range",
            "empty range",
        )
    if value.resolution is not ArtifactResolution.RESOLVED or value.diagnostics:
        _add(
            issues,
            "TMM-REQUIREMENT-AMBIGUOUS",
            "passage_presentation.resolution",
            "only a clean resolved scope may cross the presentation boundary",
        )
    for name, identifiers in (
        ("measure_ids", value.measure_ids),
        ("event_universe_ids", value.event_universe_ids),
        ("visible_event_ids", value.visible_event_ids),
        ("active_target_ids", value.active_target_ids),
        ("inactive_context_ids", value.inactive_context_ids),
        ("omitted_event_ids", value.omitted_event_ids),
        ("visible_omitted_event_ids", value.visible_omitted_event_ids),
    ):
        _unique_ids(identifiers, f"passage_presentation.{name}", issues)
    active = set(value.active_target_ids)
    inactive = set(value.inactive_context_ids)
    omitted = set(value.omitted_event_ids)
    visible_omitted = set(value.visible_omitted_event_ids)
    universe = set(value.event_universe_ids)
    visible = set(value.visible_event_ids)
    if not value.measure_ids or not active:
        _add(
            issues,
            "TMM-PRESENTATION-EMPTY-RANGE",
            "passage_presentation",
            "bounded notation requires measures and active events",
        )
    if active & inactive or active & omitted or inactive & omitted:
        _add(
            issues,
            "TMM-SCOPE-OVERLAPPING-PARTITION",
            "passage_presentation",
            "active, inactive, and omitted membership overlap",
        )
    if active | inactive | omitted != universe:
        _add(
            issues,
            "TMM-SCOPE-INCOMPLETE-PARTITION",
            "passage_presentation.event_universe_ids",
            "membership does not exactly cover the event universe",
        )
    if not visible_omitted <= omitted or visible != active | inactive | visible_omitted:
        _add(
            issues,
            "TMM-PRESENTATION-VISIBLE-PARTITION",
            "passage_presentation.visible_event_ids",
            "visible notation must contain all active and inactive context",
        )
    for path, targets, identifiers, kind in (
        (
            "measure_renderer_targets",
            value.measure_renderer_targets,
            value.measure_ids,
            "measure",
        ),
        (
            "active_renderer_targets",
            value.active_renderer_targets,
            value.active_target_ids,
            "event",
        ),
        (
            "inactive_renderer_targets",
            value.inactive_renderer_targets,
            value.inactive_context_ids,
            "event",
        ),
        (
            "visible_omitted_renderer_targets",
            value.visible_omitted_renderer_targets,
            value.visible_omitted_event_ids,
            "event",
        ),
    ):
        _validate_renderer_targets(
            targets,
            identifiers,
            kind,
            f"passage_presentation.{path}",
            issues,
        )
    if _SHA256.fullmatch(value.notation_renderer_sha256) is None:
        _add(
            issues,
            "TMM-PRESENTATION-RENDERER-DIGEST",
            "passage_presentation.notation_renderer_sha256",
            "expected SHA-256",
        )
    if scope is not None and (
        value.practice_scope_ref.id != scope.id
        or value.practice_scope_ref.semantic_fingerprint != scope.semantic_fingerprint
        or value.score_id != scope.score_id
        or value.part_id != scope.part_id
        or value.score_range != scope.score_range
        or value.notation_condition is not scope.notation_condition
        or value.execution_assignment is not scope.execution_assignment
        or value.event_universe_ids != scope.event_universe_ids
        or value.active_target_ids != scope.active_target_ids
        or value.inactive_context_ids != scope.inactive_context_ids
        or value.omitted_event_ids != tuple(item.event_id for item in scope.omissions)
        or value.visible_omitted_event_ids
        != tuple(item.event_id for item in scope.omissions if item.visible_as_context)
    ):
        _add(
            issues,
            "TMM-SCOPE-FOREIGN-REFERENCE",
            "passage_presentation.practice_scope_ref",
            "presentation differs from its resolved practice scope",
        )
    _fingerprint(value, "passage_presentation", issues)
    return tuple(issues)


def validate_curriculum_passage_guidance(
    value: CurriculumPassageGuidance,
    requirements: PassageRequirementSet | None = None,
    presentation: CurriculumPassagePresentation | None = None,
) -> tuple[CurriculumValidationIssue, ...]:
    """Validate traceable explanations and prompts for one exact presentation."""

    issues: list[CurriculumValidationIssue] = []
    _common(
        value.schema_version,
        value.id,
        value.semantic_fingerprint,
        "passage_guidance",
        issues,
    )
    for name, identifier in (
        ("analysis_id", value.analysis_id),
        ("package_id", value.package_id),
        ("score_id", value.score_id),
    ):
        _stable_id(identifier, f"passage_guidance.{name}", issues)
    if value.presentation_ref.artifact_type != "curriculum-passage-presentation":
        _add(
            issues,
            "TMM-GUIDANCE-FOREIGN-REFERENCE",
            "passage_guidance.presentation_ref",
            "reference is not a curriculum passage presentation",
        )
    if value.practice_scope_ref.artifact_type != "practice-scope-assignment":
        _add(
            issues,
            "TMM-GUIDANCE-FOREIGN-REFERENCE",
            "passage_guidance.practice_scope_ref",
            "reference is not a practice scope",
        )
    if value.resolution is not ArtifactResolution.RESOLVED or value.diagnostics:
        _add(
            issues,
            "TMM-GUIDANCE-AMBIGUOUS",
            "passage_guidance.resolution",
            "only clean resolved guidance may cross the presentation boundary",
        )
    if not value.items:
        _add(
            issues,
            "TMM-GUIDANCE-EMPTY",
            "passage_guidance.items",
            "at least one guidance item is required",
        )
    _unique_ids(tuple(item.id for item in value.items), "passage_guidance.items", issues)
    requirement_ids = tuple(item.requirement_ref.id for item in value.items)
    _unique_ids(requirement_ids, "passage_guidance.requirement_refs", issues)
    active = set(presentation.active_target_ids) if presentation is not None else set()
    inactive = set(presentation.inactive_context_ids) if presentation is not None else set()
    for index, item in enumerate(value.items):
        path = f"passage_guidance.items[{index}]"
        if item.requirement_ref.artifact_type != "passage-skill-requirement":
            _add(
                issues,
                "TMM-GUIDANCE-FOREIGN-REFERENCE",
                f"{path}.requirement_ref",
                "reference is not a passage skill requirement",
            )
        if item.primitive_ref.artifact_type != "learning-primitive":
            _add(
                issues,
                "TMM-GUIDANCE-FOREIGN-REFERENCE",
                f"{path}.primitive_ref",
                "reference is not a learning primitive",
            )
        if any(
            not text.strip()
            for text in (
                item.heading,
                item.explanation,
                item.action_prompt,
                item.reconnect_prompt,
            )
        ):
            _add(
                issues,
                "TMM-GUIDANCE-TEXT-MISSING",
                path,
                "heading, explanation, action, and reconnection text are required",
            )
        parameter_names = tuple(parameter.name for parameter in item.target_parameters)
        if parameter_names != tuple(sorted(parameter_names)) or len(parameter_names) != len(
            set(parameter_names)
        ):
            _add(
                issues,
                "TMM-CONTRACT-INVALID-EXACT-VALUE",
                f"{path}.target_parameters",
                "parameters must be uniquely sorted by name",
            )
        for name, identifiers in (
            ("focus_event_ids", item.focus_event_ids),
            ("canonical_evidence_refs", item.canonical_evidence_refs),
            ("analysis_evidence_refs", item.analysis_evidence_refs),
        ):
            _unique_ids(identifiers, f"{path}.{name}", issues)
        if not item.focus_event_ids:
            _add(
                issues,
                "TMM-GUIDANCE-ACTIVE-TARGET-MISMATCH",
                f"{path}.focus_event_ids",
                "guidance must focus at least one canonical event",
            )
        if presentation is not None and (
            not set(item.focus_event_ids) <= active or bool(set(item.focus_event_ids) & inactive)
        ):
            _add(
                issues,
                "TMM-GUIDANCE-ACTIVE-TARGET-MISMATCH",
                f"{path}.focus_event_ids",
                "guidance focuses material outside the presentation's active layer",
            )
        _rule_reference(item.derivation_rule, f"{path}.derivation_rule", issues)

    if presentation is not None and (
        value.presentation_ref
        != SemanticReference(
            "curriculum-passage-presentation",
            presentation.id,
            presentation.semantic_fingerprint,
        )
        or value.practice_scope_ref != presentation.practice_scope_ref
        or value.analysis_id != presentation.analysis_id
        or value.package_id != presentation.package_id
        or value.score_id != presentation.score_id
        or value.notation_condition is not presentation.notation_condition
        or value.execution_assignment is not presentation.execution_assignment
    ):
        _add(
            issues,
            "TMM-GUIDANCE-FOREIGN-REFERENCE",
            "passage_guidance.presentation_ref",
            "guidance differs from its exact presentation",
        )

    if requirements is not None:
        requirement_by_id = {item.id: item for item in requirements.requirements}
        primitive_by_id = {item.id: item for item in requirements.primitives}
        expected = tuple(
            item.id
            for item in requirements.requirements
            if item.practice_scope_ref.id == value.practice_scope_ref.id
            and item.resolution is ArtifactResolution.RESOLVED
        )
        if value.analysis_id != requirements.analysis_id or set(requirement_ids) != set(expected):
            _add(
                issues,
                "TMM-GUIDANCE-REQUIREMENT-MISMATCH",
                "passage_guidance.items",
                "guidance does not exactly cover the resolved requirements for its scope",
            )
        for index, item in enumerate(value.items):
            path = f"passage_guidance.items[{index}]"
            requirement = requirement_by_id.get(item.requirement_ref.id)
            primitive = primitive_by_id.get(item.primitive_ref.id)
            if requirement is None or primitive is None:
                _add(
                    issues,
                    "TMM-GUIDANCE-FOREIGN-REFERENCE",
                    path,
                    "requirement or primitive is absent from the source set",
                )
                continue
            if (
                requirement.practice_scope_ref != value.practice_scope_ref
                or item.requirement_ref.semantic_fingerprint != requirement.semantic_fingerprint
                or requirement.primitive_ref.id != primitive.id
                or item.primitive_ref.semantic_fingerprint != primitive.semantic_fingerprint
                or item.primitive_family is not primitive.family
                or item.target_parameters != requirement.target_parameters
                or item.canonical_evidence_refs != requirement.canonical_evidence_refs
                or item.analysis_evidence_refs != requirement.analysis_evidence_refs
                or item.derivation_rule != requirement.derivation_rule
            ):
                _add(
                    issues,
                    "TMM-GUIDANCE-REQUIREMENT-MISMATCH",
                    path,
                    "guidance changed its source requirement or primitive",
                )
            if presentation is not None:
                evidence = set(requirement.canonical_evidence_refs)
                expected_focus = tuple(
                    identifier
                    for identifier in presentation.active_target_ids
                    if identifier in evidence
                )
                if (
                    not expected_focus
                    and primitive.family is PrimitiveFamily.MEMORY
                    and evidence & set(presentation.measure_ids)
                ):
                    expected_focus = presentation.active_target_ids[:1]
                if item.focus_event_ids != expected_focus:
                    _add(
                        issues,
                        "TMM-GUIDANCE-EVIDENCE-MISMATCH",
                        f"{path}.focus_event_ids",
                        "focused events differ from the deterministic evidence projection",
                    )
    _fingerprint(value, "passage_guidance", issues)
    return tuple(issues)


def validate_curriculum_fundamental_explanation(
    value: CurriculumFundamentalExplanation,
    requirements: PassageRequirementSet | None = None,
    branches: PrerequisiteBranchSet | None = None,
    presentation: CurriculumPassagePresentation | None = None,
) -> tuple[CurriculumValidationIssue, ...]:
    """Validate functional text and its exact prerequisite-to-piece return."""

    issues: list[CurriculumValidationIssue] = []
    _common(
        value.schema_version,
        value.id,
        value.semantic_fingerprint,
        "fundamental_explanation",
        issues,
    )
    for name, identifier in (
        ("analysis_id", value.analysis_id),
        ("package_id", value.package_id),
        ("score_id", value.score_id),
        ("prerequisite_node_id", value.prerequisite_node_id),
        ("return_node_id", value.return_node_id),
    ):
        _stable_id(identifier, f"fundamental_explanation.{name}", issues)
    expected_reference_types = (
        (value.requirement_ref, "passage-skill-requirement", "requirement_ref"),
        (value.primitive_ref, "learning-primitive", "primitive_ref"),
        (value.practice_scope_ref, "practice-scope-assignment", "practice_scope_ref"),
        (
            value.presentation_ref,
            "curriculum-passage-presentation",
            "presentation_ref",
        ),
        (value.prerequisite_exercise_ref, "exercise-instance", "prerequisite_exercise_ref"),
        (value.application_exercise_ref, "exercise-instance", "application_exercise_ref"),
    )
    for reference, expected_type, name in expected_reference_types:
        if reference.artifact_type != expected_type:
            _add(
                issues,
                "TMM-EXPLANATION-FOREIGN-REFERENCE",
                f"fundamental_explanation.{name}",
                f"expected {expected_type}",
            )
    if value.resolution is not ArtifactResolution.RESOLVED or value.diagnostics:
        _add(
            issues,
            "TMM-EXPLANATION-AMBIGUOUS",
            "fundamental_explanation.resolution",
            "only clean resolved explanations may cross the functional boundary",
        )
    for name, text in (
        ("heading", value.heading),
        ("explanation", value.explanation),
        ("why_it_matters", value.why_it_matters),
        ("action_prompt", value.action_prompt),
        ("return_prompt", value.return_prompt),
    ):
        if not text.strip():
            _add(
                issues,
                "TMM-EXPLANATION-TEXT-MISSING",
                f"fundamental_explanation.{name}",
                "functional explanation text is required",
            )
    parameter_names = tuple(item.name for item in value.target_parameters)
    if parameter_names != tuple(sorted(parameter_names)) or len(parameter_names) != len(
        set(parameter_names)
    ):
        _add(
            issues,
            "TMM-CONTRACT-INVALID-EXACT-VALUE",
            "fundamental_explanation.target_parameters",
            "parameters must be uniquely sorted by name",
        )
    _unique_ids(
        value.focus_event_ids,
        "fundamental_explanation.focus_event_ids",
        issues,
    )
    if not value.focus_event_ids:
        _add(
            issues,
            "TMM-EXPLANATION-ACTIVE-TARGET-MISMATCH",
            "fundamental_explanation.focus_event_ids",
            "an explanation must focus at least one active canonical event",
        )
    _rule_reference(
        value.generation_rule,
        "fundamental_explanation.generation_rule",
        issues,
    )
    if (
        value.generation_rule.rule_id != "EXPLANATION-RULE-001"
        or value.generation_rule.rule_version != FUNDAMENTAL_EXPLANATION_VERSION
    ):
        _add(
            issues,
            "TMM-EXPLANATION-RULE-MISMATCH",
            "fundamental_explanation.generation_rule",
            "the explanation is not governed by the accepted deterministic rule",
        )

    if presentation is not None:
        expected_presentation_ref = SemanticReference(
            "curriculum-passage-presentation",
            presentation.id,
            presentation.semantic_fingerprint,
        )
        if (
            value.presentation_ref != expected_presentation_ref
            or value.practice_scope_ref != presentation.practice_scope_ref
            or value.analysis_id != presentation.analysis_id
            or value.package_id != presentation.package_id
            or value.score_id != presentation.score_id
        ):
            _add(
                issues,
                "TMM-EXPLANATION-PRESENTATION-MISMATCH",
                "fundamental_explanation.presentation_ref",
                "the explanation differs from its exact passage presentation",
            )
        if not set(value.focus_event_ids) <= set(presentation.active_target_ids) or bool(
            set(value.focus_event_ids) & set(presentation.inactive_context_ids)
        ):
            _add(
                issues,
                "TMM-EXPLANATION-ACTIVE-TARGET-MISMATCH",
                "fundamental_explanation.focus_event_ids",
                "the explanation focuses material outside the active layer",
            )

    if requirements is not None:
        requirement = next(
            (item for item in requirements.requirements if item.id == value.requirement_ref.id),
            None,
        )
        primitive = next(
            (item for item in requirements.primitives if item.id == value.primitive_ref.id),
            None,
        )
        if requirement is None or primitive is None:
            _add(
                issues,
                "TMM-EXPLANATION-REQUIREMENT-MISMATCH",
                "fundamental_explanation.requirement_ref",
                "the requirement or primitive is absent from the source set",
            )
        else:
            if (
                value.analysis_id != requirements.analysis_id
                or value.requirement_ref.semantic_fingerprint != requirement.semantic_fingerprint
                or requirement.primitive_ref.id != primitive.id
                or value.primitive_ref.semantic_fingerprint != primitive.semantic_fingerprint
                or value.practice_scope_ref != requirement.practice_scope_ref
                or value.target_parameters != requirement.target_parameters
            ):
                _add(
                    issues,
                    "TMM-EXPLANATION-REQUIREMENT-MISMATCH",
                    "fundamental_explanation.requirement_ref",
                    "the explanation changed its source requirement or primitive",
                )
            if presentation is not None:
                evidence = set(requirement.canonical_evidence_refs)
                expected_focus = tuple(
                    identifier
                    for identifier in presentation.active_target_ids
                    if identifier in evidence
                )
                if (
                    not expected_focus
                    and primitive.family is PrimitiveFamily.MEMORY
                    and evidence & set(presentation.measure_ids)
                ):
                    expected_focus = presentation.active_target_ids[:1]
                if value.focus_event_ids != expected_focus:
                    _add(
                        issues,
                        "TMM-EXPLANATION-EVIDENCE-MISMATCH",
                        "fundamental_explanation.focus_event_ids",
                        "focused events differ from the deterministic evidence projection",
                    )

    if branches is not None:
        branch = next(
            (
                item
                for item in branches.branches
                if item.requirement_ref.id == value.requirement_ref.id
            ),
            None,
        )
        node_by_id = {item.id: item for item in branches.nodes}
        if branch is None:
            _add(
                issues,
                "TMM-EXPLANATION-BRANCH-MISMATCH",
                "fundamental_explanation.requirement_ref",
                "the explanation has no declared prerequisite branch",
            )
        else:
            prerequisite_node = node_by_id.get(branch.prerequisite_node_id)
            application_node = node_by_id.get(branch.application_node_id)
            if (
                value.prerequisite_node_id != branch.prerequisite_node_id
                or value.return_node_id != branch.application_node_id
                or prerequisite_node is None
                or application_node is None
                or prerequisite_node.exercise_ref != value.prerequisite_exercise_ref
                or application_node.exercise_ref != value.application_exercise_ref
            ):
                _add(
                    issues,
                    "TMM-EXPLANATION-BRANCH-MISMATCH",
                    "fundamental_explanation.return_node_id",
                    "the explanation changed its prerequisite or piece-application route",
                )
            exercise_by_id = {item.id: item for item in branches.exercises}
            prerequisite_exercise = exercise_by_id.get(value.prerequisite_exercise_ref.id)
            application_exercise = exercise_by_id.get(value.application_exercise_ref.id)
            if (
                prerequisite_exercise is None
                or application_exercise is None
                or prerequisite_exercise.return_target_id != value.return_node_id
                or prerequisite_exercise.requirement_ref != value.requirement_ref
                or application_exercise.requirement_ref != value.requirement_ref
            ):
                _add(
                    issues,
                    "TMM-EXPLANATION-RETURN-MISMATCH",
                    "fundamental_explanation.return_node_id",
                    "the explanation does not return through its declared application exercise",
                )
    _fingerprint(value, "fundamental_explanation", issues)
    return tuple(issues)


def validate_curriculum_fundamental_demonstration(
    value: CurriculumFundamentalDemonstration,
    explanation: CurriculumFundamentalExplanation | None = None,
    requirements: PassageRequirementSet | None = None,
    branches: PrerequisiteBranchSet | None = None,
    presentation: CurriculumPassagePresentation | None = None,
    playback: PlaybackPlan | None = None,
) -> tuple[CurriculumValidationIssue, ...]:
    """Validate one prerequisite's existing notation/playback/piano binding."""

    issues: list[CurriculumValidationIssue] = []
    _common(
        value.schema_version,
        value.id,
        value.semantic_fingerprint,
        "fundamental_demonstration",
        issues,
    )
    for name, identifier in (
        ("analysis_id", value.analysis_id),
        ("package_id", value.package_id),
        ("score_id", value.score_id),
        ("prerequisite_node_id", value.prerequisite_node_id),
        ("return_node_id", value.return_node_id),
        ("demonstration_activity_id", value.demonstration_activity_id),
    ):
        _stable_id(identifier, f"fundamental_demonstration.{name}", issues)
    expected_reference_types = (
        (value.explanation_ref, "curriculum-fundamental-explanation", "explanation_ref"),
        (value.requirement_ref, "passage-skill-requirement", "requirement_ref"),
        (value.primitive_ref, "learning-primitive", "primitive_ref"),
        (value.practice_scope_ref, "practice-scope-assignment", "practice_scope_ref"),
        (
            value.presentation_ref,
            "curriculum-passage-presentation",
            "presentation_ref",
        ),
        (value.prerequisite_exercise_ref, "exercise-instance", "prerequisite_exercise_ref"),
    )
    for reference, expected_type, name in expected_reference_types:
        if reference.artifact_type != expected_type:
            _add(
                issues,
                "TMM-DEMONSTRATION-FOREIGN-REFERENCE",
                f"fundamental_demonstration.{name}",
                f"expected {expected_type}",
            )
    if value.resolution is not ArtifactResolution.RESOLVED or value.diagnostics:
        _add(
            issues,
            "TMM-DEMONSTRATION-AMBIGUOUS",
            "fundamental_demonstration.resolution",
            "only clean resolved demonstrations may cross the functional boundary",
        )
    for name, identifiers in (
        ("focus_event_ids", value.focus_event_ids),
        ("playback_source_event_ids", value.playback_source_event_ids),
        ("silent_active_event_ids", value.silent_active_event_ids),
    ):
        _unique_ids(identifiers, f"fundamental_demonstration.{name}", issues)
    if not value.focus_event_ids or not value.playback_source_event_ids:
        _add(
            issues,
            "TMM-DEMONSTRATION-TARGET-MISSING",
            "fundamental_demonstration.focus_event_ids",
            "demonstration requires focused notation and audible active material",
        )
    if set(value.playback_source_event_ids) & set(value.silent_active_event_ids):
        _add(
            issues,
            "TMM-DEMONSTRATION-ACTIVE-PARTITION",
            "fundamental_demonstration.playback_source_event_ids",
            "audible and silent active identities overlap",
        )
    if _SHA256.fullmatch(value.playback_plan_sha256) is None:
        _add(
            issues,
            "TMM-CONTRACT-INVALID-EXACT-VALUE",
            "fundamental_demonstration.playback_plan_sha256",
            "expected SHA-256",
        )
    if value.tempo_bpm <= 0:
        _add(
            issues,
            "TMM-DEMONSTRATION-TEMPO",
            "fundamental_demonstration.tempo_bpm",
            "tempo must be positive",
        )
    _rule_reference(
        value.generation_rule,
        "fundamental_demonstration.generation_rule",
        issues,
    )
    if (
        value.generation_rule.rule_id != "DEMONSTRATION-RULE-001"
        or value.generation_rule.rule_version != FUNDAMENTAL_DEMONSTRATION_VERSION
    ):
        _add(
            issues,
            "TMM-DEMONSTRATION-RULE-MISMATCH",
            "fundamental_demonstration.generation_rule",
            "the demonstration is not governed by the accepted deterministic rule",
        )

    if explanation is not None:
        expected_explanation_ref = SemanticReference(
            "curriculum-fundamental-explanation",
            explanation.id,
            explanation.semantic_fingerprint,
        )
        if (
            value.explanation_ref != expected_explanation_ref
            or value.requirement_ref != explanation.requirement_ref
            or value.primitive_ref != explanation.primitive_ref
            or value.practice_scope_ref != explanation.practice_scope_ref
            or value.presentation_ref != explanation.presentation_ref
            or value.prerequisite_exercise_ref != explanation.prerequisite_exercise_ref
            or value.prerequisite_node_id != explanation.prerequisite_node_id
            or value.return_node_id != explanation.return_node_id
            or value.focus_event_ids != explanation.focus_event_ids
            or value.analysis_id != explanation.analysis_id
            or value.package_id != explanation.package_id
            or value.score_id != explanation.score_id
        ):
            _add(
                issues,
                "TMM-DEMONSTRATION-EXPLANATION-MISMATCH",
                "fundamental_demonstration.explanation_ref",
                "the demonstration differs from its exact prerequisite explanation",
            )
        issues.extend(
            validate_curriculum_fundamental_explanation(
                explanation,
                requirements,
                branches,
                presentation,
            )
        )

    if presentation is not None:
        expected_presentation_ref = SemanticReference(
            "curriculum-passage-presentation",
            presentation.id,
            presentation.semantic_fingerprint,
        )
        active = set(presentation.active_target_ids)
        if (
            value.presentation_ref != expected_presentation_ref
            or value.practice_scope_ref != presentation.practice_scope_ref
            or value.analysis_id != presentation.analysis_id
            or value.package_id != presentation.package_id
            or value.score_id != presentation.score_id
        ):
            _add(
                issues,
                "TMM-DEMONSTRATION-PRESENTATION-MISMATCH",
                "fundamental_demonstration.presentation_ref",
                "the demonstration differs from its exact passage presentation",
            )
        if (
            not set(value.focus_event_ids) <= active
            or set(value.playback_source_event_ids) | set(value.silent_active_event_ids) != active
        ):
            _add(
                issues,
                "TMM-DEMONSTRATION-ACTIVE-PARTITION",
                "fundamental_demonstration.playback_source_event_ids",
                "the audible/silent partition differs from the active score layer",
            )

    if branches is not None:
        node_by_id = {item.id: item for item in branches.nodes}
        exercise_by_id = {item.id: item for item in branches.exercises}
        node = node_by_id.get(value.prerequisite_node_id)
        exercise = exercise_by_id.get(value.prerequisite_exercise_ref.id)
        activity = (
            next(
                (
                    item
                    for item in exercise.activity_sequence
                    if item.id == value.demonstration_activity_id
                ),
                None,
            )
            if exercise is not None
            else None
        )
        if (
            node is None
            or exercise is None
            or node.exercise_ref != value.prerequisite_exercise_ref
            or exercise.requirement_ref != value.requirement_ref
            or exercise.practice_scope_ref != value.practice_scope_ref
            or exercise.return_target_id != value.return_node_id
            or activity is None
            or activity.form is not ActivityForm.DEMONSTRATE_LISTEN
            or activity.evidence_producing
        ):
            _add(
                issues,
                "TMM-DEMONSTRATION-ACTIVITY-MISMATCH",
                "fundamental_demonstration.demonstration_activity_id",
                "the binding is not the declared non-evidence prerequisite demonstration",
            )

    if playback is not None:
        playback_sources = {
            source.event_id for note in playback.notes for source in note.source_events
        }
        expected_digest = _playback_plan_sha256(playback)
        if (
            playback.package_id != value.package_id
            or playback.score_id != value.score_id
            or playback_sources != set(value.playback_source_event_ids)
            or expected_digest != value.playback_plan_sha256
        ):
            _add(
                issues,
                "TMM-DEMONSTRATION-PLAYBACK-MISMATCH",
                "fundamental_demonstration.playback_plan_sha256",
                "the playback plan differs from the bound active demonstration",
            )
    _fingerprint(value, "fundamental_demonstration", issues)
    return tuple(issues)


def validate_curriculum_fundamental_practice(
    value: CurriculumFundamentalPractice,
    explanation: CurriculumFundamentalExplanation | None = None,
    demonstration: CurriculumFundamentalDemonstration | None = None,
    requirements: PassageRequirementSet | None = None,
    branches: PrerequisiteBranchSet | None = None,
    presentation: CurriculumPassagePresentation | None = None,
    expected: ExpectedPerformance | None = None,
) -> tuple[CurriculumValidationIssue, ...]:
    """Validate the exact learner-response side of one prerequisite."""

    issues: list[CurriculumValidationIssue] = []
    _common(
        value.schema_version,
        value.id,
        value.semantic_fingerprint,
        "fundamental_practice",
        issues,
    )
    for name, identifier in (
        ("analysis_id", value.analysis_id),
        ("package_id", value.package_id),
        ("score_id", value.score_id),
        ("prerequisite_node_id", value.prerequisite_node_id),
        ("return_node_id", value.return_node_id),
        ("performance_activity_id", value.performance_activity_id),
        ("expected_performance_id", value.expected_performance_id),
    ):
        _stable_id(identifier, f"fundamental_practice.{name}", issues)
    expected_reference_types = (
        (value.explanation_ref, "curriculum-fundamental-explanation", "explanation_ref"),
        (
            value.demonstration_ref,
            "curriculum-fundamental-demonstration",
            "demonstration_ref",
        ),
        (value.requirement_ref, "passage-skill-requirement", "requirement_ref"),
        (value.primitive_ref, "learning-primitive", "primitive_ref"),
        (value.practice_scope_ref, "practice-scope-assignment", "practice_scope_ref"),
        (
            value.presentation_ref,
            "curriculum-passage-presentation",
            "presentation_ref",
        ),
        (value.prerequisite_exercise_ref, "exercise-instance", "prerequisite_exercise_ref"),
    )
    for reference, expected_type, name in expected_reference_types:
        if reference.artifact_type != expected_type:
            _add(
                issues,
                "TMM-PRACTICE-FOREIGN-REFERENCE",
                f"fundamental_practice.{name}",
                f"expected {expected_type}",
            )
    if value.resolution is not ArtifactResolution.RESOLVED or value.diagnostics:
        _add(
            issues,
            "TMM-PRACTICE-AMBIGUOUS",
            "fundamental_practice.resolution",
            "only clean resolved practice bindings may become learner attempts",
        )
    if value.practice_mode is not PracticeMode.SUPPORTED_PERFORMANCE:
        _add(
            issues,
            "TMM-PRACTICE-MODE-MISMATCH",
            "fundamental_practice.practice_mode",
            "a prerequisite learner response uses supported performance",
        )
    conditions = value.support_envelope.permitted_conditions
    if (
        not conditions
        or len(set(conditions)) != len(conditions)
        or value.support_envelope.initial_condition not in conditions
        or (
            value.support_envelope.independent_condition is not None
            and value.support_envelope.independent_condition not in conditions
        )
    ):
        _add(
            issues,
            "TMM-PRACTICE-SUPPORT-MISMATCH",
            "fundamental_practice.support_envelope",
            "support conditions are empty, duplicated, or internally inconsistent",
        )
    exit_dimensions = tuple(item.dimension for item in value.required_evidence_exits)
    if (
        not exit_dimensions
        or len(set(exit_dimensions)) != len(exit_dimensions)
        or any(
            not item.dimension.strip()
            or item.evidence_context != EvidenceContext.ACQUISITION.value
            or not item.minimum_state.strip()
            for item in value.required_evidence_exits
        )
    ):
        _add(
            issues,
            "TMM-PRACTICE-EVIDENCE-EXIT-MISMATCH",
            "fundamental_practice.required_evidence_exits",
            "prerequisite evidence exits must be unique acquisition requirements",
        )
    if any(
        item not in {dimension.value for dimension in value.target_dimensions}
        for item in exit_dimensions
    ):
        _add(
            issues,
            "TMM-PRACTICE-DIMENSION-MISMATCH",
            "fundamental_practice.required_evidence_exits",
            "every required evidence exit must be an expected target dimension",
        )
    _unique_ids(
        value.expected_active_event_ids,
        "fundamental_practice.expected_active_event_ids",
        issues,
    )
    _unique_ids(
        value.expected_note_ids,
        "fundamental_practice.expected_note_ids",
        issues,
    )
    if not value.expected_active_event_ids or not value.expected_note_ids:
        _add(
            issues,
            "TMM-PRACTICE-TARGET-MISSING",
            "fundamental_practice.expected_active_event_ids",
            "playable practice requires active material and expected notes",
        )
    if not value.target_dimensions or len(set(value.target_dimensions)) != len(
        value.target_dimensions
    ):
        _add(
            issues,
            "TMM-PRACTICE-DIMENSION-MISMATCH",
            "fundamental_practice.target_dimensions",
            "target dimensions are empty or duplicated",
        )
    for name, digest in (
        ("expected_target_fingerprint", value.expected_target_fingerprint),
        ("expected_performance_sha256", value.expected_performance_sha256),
    ):
        if _SHA256.fullmatch(digest) is None:
            _add(
                issues,
                "TMM-CONTRACT-INVALID-EXACT-VALUE",
                f"fundamental_practice.{name}",
                "expected SHA-256",
            )
    if value.tempo_bpm <= 0:
        _add(
            issues,
            "TMM-PRACTICE-TEMPO",
            "fundamental_practice.tempo_bpm",
            "tempo must be positive",
        )
    _rule_reference(value.generation_rule, "fundamental_practice.generation_rule", issues)
    if (
        value.generation_rule.rule_id != "FUNDAMENTAL-PRACTICE-RULE-001"
        or value.generation_rule.rule_version != FUNDAMENTAL_PRACTICE_VERSION
    ):
        _add(
            issues,
            "TMM-PRACTICE-RULE-MISMATCH",
            "fundamental_practice.generation_rule",
            "practice is not governed by the accepted deterministic rule",
        )

    if explanation is not None:
        expected_explanation_ref = SemanticReference(
            "curriculum-fundamental-explanation",
            explanation.id,
            explanation.semantic_fingerprint,
        )
        if (
            value.explanation_ref != expected_explanation_ref
            or value.requirement_ref != explanation.requirement_ref
            or value.primitive_ref != explanation.primitive_ref
            or value.practice_scope_ref != explanation.practice_scope_ref
            or value.presentation_ref != explanation.presentation_ref
            or value.prerequisite_exercise_ref != explanation.prerequisite_exercise_ref
            or value.prerequisite_node_id != explanation.prerequisite_node_id
            or value.return_node_id != explanation.return_node_id
            or value.analysis_id != explanation.analysis_id
            or value.package_id != explanation.package_id
            or value.score_id != explanation.score_id
        ):
            _add(
                issues,
                "TMM-PRACTICE-EXPLANATION-MISMATCH",
                "fundamental_practice.explanation_ref",
                "practice differs from its exact prerequisite explanation",
            )
        issues.extend(
            validate_curriculum_fundamental_explanation(
                explanation,
                requirements,
                branches,
                presentation,
            )
        )

    if demonstration is not None:
        expected_demonstration_ref = SemanticReference(
            "curriculum-fundamental-demonstration",
            demonstration.id,
            demonstration.semantic_fingerprint,
        )
        if (
            value.demonstration_ref != expected_demonstration_ref
            or value.explanation_ref != demonstration.explanation_ref
            or value.prerequisite_exercise_ref != demonstration.prerequisite_exercise_ref
            or value.prerequisite_node_id != demonstration.prerequisite_node_id
            or value.return_node_id != demonstration.return_node_id
            or value.performance_activity_id == demonstration.demonstration_activity_id
        ):
            _add(
                issues,
                "TMM-PRACTICE-DEMONSTRATION-MISMATCH",
                "fundamental_practice.demonstration_ref",
                "practice is detached from, or conflated with, its demonstration",
            )
        issues.extend(
            validate_curriculum_fundamental_demonstration(
                demonstration,
                explanation,
                requirements,
                branches,
                presentation,
            )
        )

    if presentation is not None:
        active = set(presentation.active_target_ids)
        if (
            value.presentation_ref.id != presentation.id
            or value.presentation_ref.semantic_fingerprint != presentation.semantic_fingerprint
            or value.expected_active_event_ids != presentation.active_target_ids
            or not active
        ):
            _add(
                issues,
                "TMM-PRACTICE-PRESENTATION-MISMATCH",
                "fundamental_practice.expected_active_event_ids",
                "practice differs from the exact active passage presentation",
            )

    if branches is not None:
        exercise = next(
            (item for item in branches.exercises if item.id == value.prerequisite_exercise_ref.id),
            None,
        )
        activity = (
            next(
                (
                    item
                    for item in exercise.activity_sequence
                    if item.id == value.performance_activity_id
                ),
                None,
            )
            if exercise is not None
            else None
        )
        if (
            exercise is None
            or activity is None
            or activity.form is not ActivityForm.PERFORM
            or not activity.evidence_producing
            or exercise.support_envelope != value.support_envelope
            or exercise.required_evidence_exits != value.required_evidence_exits
            or exercise.material.active_target_ids != value.expected_active_event_ids
            or exercise.return_target_id != value.return_node_id
        ):
            _add(
                issues,
                "TMM-PRACTICE-ACTIVITY-MISMATCH",
                "fundamental_practice.performance_activity_id",
                "binding is not the declared evidence-producing prerequisite activity",
            )

    if expected is not None:
        target = expected.layer_target
        if (
            target is None
            or expected.exercise_id != value.expected_performance_id
            or expected.practice_mode != value.practice_mode.value
            or target.semantic_fingerprint != value.expected_target_fingerprint
            or target.active_event_ids != value.expected_active_event_ids
            or tuple(item.id for item in expected.notes) != value.expected_note_ids
            or expected.target_dimensions != value.target_dimensions
            or semantic_fingerprint(expected) != value.expected_performance_sha256
        ):
            _add(
                issues,
                "TMM-PRACTICE-EXPECTED-MISMATCH",
                "fundamental_practice.expected_performance_sha256",
                "expected performance differs from the bound learner target",
            )
    _fingerprint(value, "fundamental_practice", issues)
    return tuple(issues)


def validate_curriculum_learning_outcome(
    value: CurriculumLearningOutcome,
    practice: CurriculumFundamentalPractice | None = None,
    expected: ExpectedPerformance | None = None,
    attempt: LearnerAttempt | None = None,
    calibration: CalibrationProfile | None = None,
    support: SupportState | None = None,
    observations: tuple[Observation, ...] | None = None,
    exercise: ExerciseInstance | None = None,
) -> tuple[CurriculumValidationIssue, ...]:
    """Validate one reward-free factual attempt outcome."""

    issues: list[CurriculumValidationIssue] = []
    _common(value.schema_version, value.id, value.semantic_fingerprint, "outcome", issues)
    _stable_id(value.run_id, "outcome.run_id", issues)
    outcome_rules = {
        "LEARNING-OUTCOME-RULE-001": "curriculum-fundamental-practice",
        "LEARNING-OUTCOME-RULE-002": "exercise-instance",
    }
    practice_artifact_type = outcome_rules.get(
        value.generation_rule.rule_id,
        "curriculum-fundamental-practice",
    )
    for reference, artifact_type, name in (
        (value.practice_ref, practice_artifact_type, "practice_ref"),
        (value.expected_performance_ref, "expected-performance", "expected_performance_ref"),
        (value.attempt_ref, "learner-attempt", "attempt_ref"),
        (value.calibration_ref, "calibration-profile", "calibration_ref"),
        (value.support_state_ref, "support-state", "support_state_ref"),
    ):
        _semantic_reference(reference, artifact_type, f"outcome.{name}", issues)
    if not isinstance(value.completion, AttemptCompletion):
        _add(
            issues,
            "TMM-OUTCOME-COMPLETION",
            "outcome.completion",
            "unknown attempt completion state",
        )
    for name, identifiers in (
        ("raw_message_ids", value.raw_message_ids),
        ("normalized_event_ids", value.normalized_event_ids),
    ):
        _unique_ids(identifiers, f"outcome.{name}", issues)
    for index, reference in enumerate(value.observation_refs):
        _semantic_reference(
            reference,
            "performance-observation",
            f"outcome.observation_refs[{index}]",
            issues,
        )
    if len({item.id for item in value.observation_refs}) != len(value.observation_refs):
        _add(
            issues,
            "TMM-OUTCOME-OBSERVATION-DUPLICATE",
            "outcome.observation_refs",
            "observation references repeat",
        )
    _rule_reference(value.generation_rule, "outcome.generation_rule", issues)
    if (
        value.generation_rule.rule_id not in outcome_rules
        or value.generation_rule.rule_version != LEARNING_OUTCOME_VERSION
    ):
        _add(
            issues,
            "TMM-OUTCOME-RULE-MISMATCH",
            "outcome.generation_rule",
            "outcome is not governed by the accepted factual assembly rule",
        )
    if value.resolution is not ArtifactResolution.RESOLVED or value.diagnostics:
        _add(
            issues,
            "TMM-OUTCOME-ARTIFACT-INVALID",
            "outcome.resolution",
            "a preserved factual outcome must be a clean resolved artifact",
        )

    if practice is not None:
        practice_ref = SemanticReference(
            "curriculum-fundamental-practice",
            practice.id,
            practice.semantic_fingerprint,
        )
        if value.practice_ref != practice_ref:
            _add(
                issues,
                "TMM-OUTCOME-PRACTICE-MISMATCH",
                "outcome.practice_ref",
                "outcome is detached from the supplied practice binding",
            )
    if exercise is not None:
        exercise_ref = SemanticReference(
            "exercise-instance",
            exercise.id,
            exercise.semantic_fingerprint,
        )
        if value.practice_ref != exercise_ref:
            _add(
                issues,
                "TMM-OUTCOME-EXERCISE-MISMATCH",
                "outcome.practice_ref",
                "outcome is detached from the supplied graph exercise",
            )
    if practice is not None and exercise is not None:
        _add(
            issues,
            "TMM-OUTCOME-TARGET-AMBIGUOUS",
            "outcome.practice_ref",
            "an outcome cannot bind both a fundamental practice and a graph exercise",
        )
    if expected is not None:
        expected_ref = SemanticReference(
            "expected-performance",
            expected.exercise_id,
            semantic_fingerprint(expected),
        )
        if value.expected_performance_ref != expected_ref:
            _add(
                issues,
                "TMM-OUTCOME-EXPECTED-MISMATCH",
                "outcome.expected_performance_ref",
                "outcome is detached from the supplied expected performance",
            )
    if attempt is not None:
        attempt_ref = SemanticReference(
            "learner-attempt",
            attempt.id,
            semantic_fingerprint(attempt),
        )
        if (
            value.run_id != attempt.run_id
            or value.attempt_ref != attempt_ref
            or value.completion is not attempt.completion
            or value.raw_message_ids != tuple(item.id for item in attempt.raw_messages)
            or value.normalized_event_ids != tuple(item.id for item in attempt.normalized_events)
        ):
            _add(
                issues,
                "TMM-OUTCOME-ATTEMPT-MISMATCH",
                "outcome.attempt_ref",
                "outcome does not preserve the supplied attempt exactly",
            )
    if calibration is not None:
        calibration_ref = SemanticReference(
            "calibration-profile",
            calibration.id,
            semantic_fingerprint(calibration),
        )
        if value.calibration_ref != calibration_ref:
            _add(
                issues,
                "TMM-OUTCOME-CALIBRATION-MISMATCH",
                "outcome.calibration_ref",
                "outcome is detached from the supplied calibration",
            )
    if support is not None:
        support_ref = SemanticReference(
            "support-state",
            support.id,
            semantic_fingerprint(support),
        )
        if value.support_state_ref != support_ref:
            _add(
                issues,
                "TMM-OUTCOME-SUPPORT-MISMATCH",
                "outcome.support_state_ref",
                "outcome is detached from the supplied support condition",
            )
    if observations is not None:
        observation_refs = tuple(
            SemanticReference(
                "performance-observation",
                item.id,
                semantic_fingerprint(item),
            )
            for item in observations
        )
        if value.observation_refs != observation_refs:
            _add(
                issues,
                "TMM-OUTCOME-OBSERVATION-MISMATCH",
                "outcome.observation_refs",
                "outcome does not preserve the supplied observations exactly",
            )
    _fingerprint(value, "outcome", issues)
    return tuple(issues)


def validate_curriculum_research_reward(
    value: CurriculumResearchReward,
    outcome: CurriculumLearningOutcome | None = None,
    expected: ExpectedPerformance | None = None,
    observations: tuple[Observation, ...] | None = None,
) -> tuple[CurriculumValidationIssue, ...]:
    """Validate independently versioned research-reward components."""

    issues: list[CurriculumValidationIssue] = []
    _common(value.schema_version, value.id, value.semantic_fingerprint, "reward", issues)
    _stable_id(value.run_id, "reward.run_id", issues)
    _semantic_reference(
        value.outcome_ref,
        "curriculum-learning-outcome",
        "reward.outcome_ref",
        issues,
    )
    _semantic_reference(
        value.expected_performance_ref,
        "expected-performance",
        "reward.expected_performance_ref",
        issues,
    )
    _rule_reference(value.generation_rule, "reward.generation_rule", issues)
    if (
        value.generation_rule.rule_id != "RESEARCH-REWARD-PROJECTION-001"
        or value.generation_rule.rule_version != RESEARCH_REWARD_VERSION
    ):
        _add(
            issues,
            "TMM-REWARD-RULE-MISMATCH",
            "reward.generation_rule",
            "reward projection uses an unknown rule version",
        )
    if value.resolution is not ArtifactResolution.RESOLVED or value.diagnostics:
        _add(
            issues,
            "TMM-REWARD-ARTIFACT-INVALID",
            "reward.resolution",
            "research-reward projection must be a clean resolved artifact",
        )

    component_ids = tuple(item.component_id for item in value.components)
    if len(component_ids) != len(set(component_ids)):
        _add(
            issues,
            "TMM-REWARD-COMPONENT-DUPLICATE",
            "reward.components",
            "research component identities repeat",
        )
    if not value.components or value.components[0].component_id != "attempt-completion":
        _add(
            issues,
            "TMM-REWARD-COMPLETION-MISSING",
            "reward.components",
            "attempt completion must be the first component",
        )
    if len(value.components) < 2:
        _add(
            issues,
            "TMM-REWARD-DIMENSION-MISSING",
            "reward.components",
            "reward projection must expose at least one performance dimension",
        )
    expected_order = ["attempt-completion"]
    expected_order.extend(
        f"dimension-match:{dimension.value}"
        for dimension in ObservationDimension
        if f"dimension-match:{dimension.value}" in component_ids
    )
    if list(component_ids) != expected_order:
        _add(
            issues,
            "TMM-REWARD-COMPONENT-ORDER",
            "reward.components",
            "components are not in deterministic dimension order",
        )

    seen_observations: list[str] = []
    for index, component in enumerate(value.components):
        path = f"reward.components[{index}]"
        is_completion = component.component_id == "attempt-completion"
        expected_component_id = (
            "attempt-completion"
            if component.dimension is None
            else f"dimension-match:{component.dimension.value}"
        )
        if component.component_id != expected_component_id:
            _add(
                issues,
                "TMM-REWARD-COMPONENT-IDENTITY",
                f"{path}.component_id",
                "component identity and dimension differ",
            )
        if is_completion and component.dimension is not None:
            _add(
                issues,
                "TMM-REWARD-COMPONENT-IDENTITY",
                f"{path}.dimension",
                "completion component cannot name a musical dimension",
            )
        if is_completion and (
            component.observation_refs
            or any(
                (
                    component.matched_observation_count,
                    component.discrepancy_observation_count,
                    component.unresolved_observation_count,
                )
            )
        ):
            _add(
                issues,
                "TMM-REWARD-COMPLETION-OBSERVATION-LEAK",
                path,
                "completion must not reinterpret performance observations",
            )
        for name, count in (
            ("matched_observation_count", component.matched_observation_count),
            ("discrepancy_observation_count", component.discrepancy_observation_count),
            ("unresolved_observation_count", component.unresolved_observation_count),
        ):
            if count < 0:
                _add(
                    issues,
                    "TMM-REWARD-COUNT-INVALID",
                    f"{path}.{name}",
                    "observation count cannot be negative",
                )
        count_total = (
            component.matched_observation_count
            + component.discrepancy_observation_count
            + component.unresolved_observation_count
        )
        if count_total != len(component.observation_refs):
            _add(
                issues,
                "TMM-REWARD-COUNT-MISMATCH",
                path,
                "component counts do not cover its observation references",
            )
        for ref_index, reference in enumerate(component.observation_refs):
            _semantic_reference(
                reference,
                "performance-observation",
                f"{path}.observation_refs[{ref_index}]",
                issues,
            )
            seen_observations.append(reference.id)
        if len({item.id for item in component.observation_refs}) != len(component.observation_refs):
            _add(
                issues,
                "TMM-REWARD-OBSERVATION-DUPLICATE",
                f"{path}.observation_refs",
                "component observation references repeat",
            )
        _rule_reference(component.calculation_rule, f"{path}.calculation_rule", issues)
        expected_rule = (
            "RESEARCH-REWARD-COMPLETION-001"
            if is_completion
            else "RESEARCH-REWARD-DIMENSION-MATCH-001"
        )
        if (
            component.calculation_rule.rule_id != expected_rule
            or component.calculation_rule.rule_version != RESEARCH_REWARD_VERSION
        ):
            _add(
                issues,
                "TMM-REWARD-RULE-MISMATCH",
                f"{path}.calculation_rule",
                "component uses an unknown calculation rule version",
            )
        if not re.fullmatch(r"[A-Z][A-Z0-9_]*", component.reason_code):
            _add(
                issues,
                "TMM-REWARD-REASON-INVALID",
                f"{path}.reason_code",
                "component reason code is not stable",
            )
        if component.status is ResearchRewardComponentStatus.MEASURED:
            if component.value is None or not Fraction(0) <= component.value <= Fraction(1):
                _add(
                    issues,
                    "TMM-REWARD-VALUE-INVALID",
                    f"{path}.value",
                    "measured reward must be an exact value from zero through one",
                )
            elif not is_completion:
                denominator = (
                    component.matched_observation_count + component.discrepancy_observation_count
                )
                expected_value = (
                    Fraction(component.matched_observation_count, denominator)
                    if denominator
                    else None
                )
                if component.value != expected_value or component.unresolved_observation_count:
                    _add(
                        issues,
                        "TMM-REWARD-VALUE-MISMATCH",
                        f"{path}.value",
                        "dimension value does not equal its exact resolved match fraction",
                    )
            elif component.value != Fraction(1) or component.reason_code != "ATTEMPT_COMPLETED":
                _add(
                    issues,
                    "TMM-REWARD-COMPLETION-VALUE-MISMATCH",
                    f"{path}.value",
                    "measured completion must be the exact completed value",
                )
        elif component.value is not None:
            _add(
                issues,
                "TMM-REWARD-UNAVAILABLE-HAS-VALUE",
                f"{path}.value",
                "unavailable or inconclusive reward must use null",
            )

    if len(seen_observations) != len(set(seen_observations)):
        _add(
            issues,
            "TMM-REWARD-OBSERVATION-LEAK",
            "reward.components",
            "one factual observation contributes to more than one component",
        )
    if outcome is not None:
        outcome_ref = SemanticReference(
            "curriculum-learning-outcome",
            outcome.id,
            outcome.semantic_fingerprint,
        )
        if value.run_id != outcome.run_id or value.outcome_ref != outcome_ref:
            _add(
                issues,
                "TMM-REWARD-OUTCOME-MISMATCH",
                "reward.outcome_ref",
                "reward is detached from the supplied factual outcome",
            )
        completion = next(
            (item for item in value.components if item.component_id == "attempt-completion"),
            None,
        )
        completion_expectations = {
            AttemptCompletion.COMPLETED: (
                ResearchRewardComponentStatus.MEASURED,
                Fraction(1),
                "ATTEMPT_COMPLETED",
            ),
            AttemptCompletion.INPUT_FAILURE: (
                ResearchRewardComponentStatus.INVALID_INPUT,
                None,
                "ATTEMPT_INPUT_FAILURE",
            ),
            AttemptCompletion.INTERRUPTED: (
                ResearchRewardComponentStatus.INCONCLUSIVE,
                None,
                "ATTEMPT_INTERRUPTED",
            ),
            AttemptCompletion.CANCELLED: (
                ResearchRewardComponentStatus.NOT_APPLICABLE,
                None,
                "ATTEMPT_CANCELLED",
            ),
            AttemptCompletion.SAFE_STOP: (
                ResearchRewardComponentStatus.NOT_APPLICABLE,
                None,
                "ATTEMPT_SAFE_STOP",
            ),
        }
        expected_completion = completion_expectations[outcome.completion]
        if (
            completion is None
            or (
                completion.status,
                completion.value,
                completion.reason_code,
            )
            != expected_completion
        ):
            _add(
                issues,
                "TMM-REWARD-COMPLETION-MISMATCH",
                "reward.components",
                "completion component differs from the factual attempt ending",
            )
    if expected is not None:
        expected_ref = SemanticReference(
            "expected-performance",
            expected.exercise_id,
            semantic_fingerprint(expected),
        )
        if value.expected_performance_ref != expected_ref:
            _add(
                issues,
                "TMM-REWARD-EXPECTED-MISMATCH",
                "reward.expected_performance_ref",
                "reward is detached from the supplied expected performance",
            )
        missing = {
            f"dimension-match:{dimension.value}" for dimension in expected.target_dimensions
        } - set(component_ids)
        if missing:
            _add(
                issues,
                "TMM-REWARD-TARGET-DIMENSION-MISSING",
                "reward.components",
                "target dimensions lack explicit reward availability",
            )
    if observations is not None:
        source_refs = tuple(
            SemanticReference("performance-observation", item.id, semantic_fingerprint(item))
            for item in observations
        )
        component_refs = tuple(
            reference for component in value.components for reference in component.observation_refs
        )
        if set(component_refs) != set(source_refs) or len(component_refs) != len(source_refs):
            _add(
                issues,
                "TMM-REWARD-OBSERVATION-MISMATCH",
                "reward.components",
                "reward components do not partition supplied observations exactly",
            )
        for component in value.components:
            if component.dimension is None:
                continue
            selected = tuple(item for item in observations if item.dimension is component.dimension)
            selected_refs = tuple(
                SemanticReference("performance-observation", item.id, semantic_fingerprint(item))
                for item in selected
            )
            matches = sum(item.status is ObservationStatus.MATCH for item in selected)
            discrepancies = sum(item.status is ObservationStatus.DISCREPANCY for item in selected)
            if (
                component.matched_observation_count != matches
                or component.discrepancy_observation_count != discrepancies
                or component.unresolved_observation_count != len(selected) - matches - discrepancies
                or component.observation_refs != selected_refs
            ):
                _add(
                    issues,
                    "TMM-REWARD-COUNT-MISMATCH",
                    "reward.components",
                    "component counts differ from supplied factual observations",
                )
            statuses = {item.status for item in selected}
            expected_result: tuple[
                ResearchRewardComponentStatus,
                Fraction | None,
                str,
            ]
            if ObservationStatus.INVALID_INPUT in statuses:
                expected_result = (
                    ResearchRewardComponentStatus.INVALID_INPUT,
                    None,
                    "INVALID_INPUT_OBSERVATION",
                )
            elif statuses & {ObservationStatus.AMBIGUOUS, ObservationStatus.UNOBSERVABLE}:
                expected_result = (
                    ResearchRewardComponentStatus.INCONCLUSIVE,
                    None,
                    "UNRESOLVED_OBSERVATION",
                )
            elif not selected:
                expected_result = (
                    ResearchRewardComponentStatus.INCONCLUSIVE,
                    None,
                    "TARGET_DIMENSION_UNOBSERVED",
                )
            else:
                denominator = matches + discrepancies
                expected_result = (
                    ResearchRewardComponentStatus.MEASURED,
                    Fraction(matches, denominator),
                    "EXACT_MATCH_FRACTION",
                )
            if (
                component.status,
                component.value,
                component.reason_code,
            ) != expected_result:
                _add(
                    issues,
                    "TMM-REWARD-RESULT-MISMATCH",
                    "reward.components",
                    "component result differs from supplied factual observations",
                )
    _fingerprint(value, "reward", issues)
    return tuple(issues)


def validate_curriculum_game_reward(
    value: CurriculumGameReward,
    outcome: CurriculumLearningOutcome | None = None,
    research_reward: CurriculumResearchReward | None = None,
) -> tuple[CurriculumValidationIssue, ...]:
    """Validate a presentation-only acknowledgement of an existing result."""

    issues: list[CurriculumValidationIssue] = []
    _common(
        value.schema_version,
        value.id,
        value.semantic_fingerprint,
        "game_reward",
        issues,
    )
    _stable_id(value.run_id, "game_reward.run_id", issues)
    _semantic_reference(
        value.outcome_ref,
        "curriculum-learning-outcome",
        "game_reward.outcome_ref",
        issues,
    )
    _semantic_reference(
        value.research_reward_ref,
        "curriculum-research-reward",
        "game_reward.research_reward_ref",
        issues,
    )
    _rule_reference(value.generation_rule, "game_reward.generation_rule", issues)
    if (
        value.generation_rule.rule_id != "GAME-REWARD-PRESENTATION-001"
        or value.generation_rule.rule_version != GAME_REWARD_VERSION
    ):
        _add(
            issues,
            "TMM-GAME-REWARD-RULE-MISMATCH",
            "game_reward.generation_rule",
            "game reward uses an unknown presentation rule version",
        )
    if value.resolution is not ArtifactResolution.RESOLVED or value.diagnostics:
        _add(
            issues,
            "TMM-GAME-REWARD-ARTIFACT-INVALID",
            "game_reward.resolution",
            "game reward must be a clean resolved presentation artifact",
        )

    message_by_signal = {
        GameRewardSignal.RESULT_UNAVAILABLE: "GAME_RESULT_UNAVAILABLE",
        GameRewardSignal.ATTEMPT_ACKNOWLEDGED: "GAME_ATTEMPT_ACKNOWLEDGED",
        GameRewardSignal.ACCURATE_ATTEMPT_CELEBRATION: "GAME_ACCURATE_ATTEMPT",
    }
    expected_message = message_by_signal.get(value.signal)
    if expected_message is None or value.message_code != expected_message:
        _add(
            issues,
            "TMM-GAME-REWARD-MESSAGE-MISMATCH",
            "game_reward.message_code",
            "message code does not match the bounded display signal",
        )
    if len(value.source_component_ids) != len(set(value.source_component_ids)):
        _add(
            issues,
            "TMM-GAME-REWARD-COMPONENT-DUPLICATE",
            "game_reward.source_component_ids",
            "source research components repeat",
        )
    for index, component_id in enumerate(value.source_component_ids):
        if not component_id.startswith("dimension-match:"):
            _add(
                issues,
                "TMM-GAME-REWARD-COMPONENT-INVALID",
                f"game_reward.source_component_ids[{index}]",
                "only measured dimension components may drive a display signal",
            )

    if outcome is not None:
        outcome_ref = SemanticReference(
            "curriculum-learning-outcome",
            outcome.id,
            outcome.semantic_fingerprint,
        )
        if value.run_id != outcome.run_id or value.outcome_ref != outcome_ref:
            _add(
                issues,
                "TMM-GAME-REWARD-OUTCOME-MISMATCH",
                "game_reward.outcome_ref",
                "game reward is detached from the supplied factual outcome",
            )
    if research_reward is not None:
        research_ref = SemanticReference(
            "curriculum-research-reward",
            research_reward.id,
            research_reward.semantic_fingerprint,
        )
        if (
            value.run_id != research_reward.run_id
            or value.research_reward_ref != research_ref
            or value.outcome_ref != research_reward.outcome_ref
        ):
            _add(
                issues,
                "TMM-GAME-REWARD-RESEARCH-MISMATCH",
                "game_reward.research_reward_ref",
                "game reward is detached from the supplied research result",
            )
        measured_dimensions = tuple(
            component
            for component in research_reward.components
            if component.dimension is not None
            and component.status is ResearchRewardComponentStatus.MEASURED
        )
        all_dimensions = tuple(
            component for component in research_reward.components if component.dimension is not None
        )
        expected_source_ids = tuple(component.component_id for component in measured_dimensions)
        completion = research_reward.components[0] if research_reward.components else None
        if not measured_dimensions:
            expected_signal = GameRewardSignal.RESULT_UNAVAILABLE
        elif (
            completion is not None
            and completion.status is ResearchRewardComponentStatus.MEASURED
            and completion.value == Fraction(1)
            and len(measured_dimensions) == len(all_dimensions)
            and all(component.value == Fraction(1) for component in measured_dimensions)
        ):
            expected_signal = GameRewardSignal.ACCURATE_ATTEMPT_CELEBRATION
        else:
            expected_signal = GameRewardSignal.ATTEMPT_ACKNOWLEDGED
        if value.source_component_ids != expected_source_ids:
            _add(
                issues,
                "TMM-GAME-REWARD-COMPONENT-MISMATCH",
                "game_reward.source_component_ids",
                "display sources differ from measured research components",
            )
        if value.signal is not expected_signal:
            _add(
                issues,
                "TMM-GAME-REWARD-SIGNAL-MISMATCH",
                "game_reward.signal",
                "display signal differs from the supplied research result",
            )
    _fingerprint(value, "game_reward", issues)
    return tuple(issues)


def validate_curriculum_piece_return(
    value: CurriculumPieceReturn,
    practice: CurriculumFundamentalPractice | None = None,
    mastery: CurriculumMasteryProjection | None = None,
    decision: CurriculumUnlockDecision | None = None,
    branches: PrerequisiteBranchSet | None = None,
    graph: AcquisitionGraphSlice | None = None,
    presentation: CurriculumPassagePresentation | None = None,
) -> tuple[CurriculumValidationIssue, ...]:
    """Validate one policy-authorized prerequisite-to-piece handoff."""

    issues: list[CurriculumValidationIssue] = []
    _common(value.schema_version, value.id, value.semantic_fingerprint, "piece_return", issues)
    for name, identifier in (
        ("analysis_id", value.analysis_id),
        ("package_id", value.package_id),
        ("score_id", value.score_id),
        ("prerequisite_node_id", value.prerequisite_node_id),
        ("return_node_id", value.return_node_id),
        ("return_edge_id", value.return_edge_id),
        ("reconnect_activity_id", value.reconnect_activity_id),
    ):
        _stable_id(identifier, f"piece_return.{name}", issues)
    for reference, artifact_type, name in (
        (value.practice_ref, "curriculum-fundamental-practice", "practice_ref"),
        (value.requirement_ref, "passage-skill-requirement", "requirement_ref"),
        (value.primitive_ref, "learning-primitive", "primitive_ref"),
        (value.practice_scope_ref, "practice-scope-assignment", "practice_scope_ref"),
        (
            value.presentation_ref,
            "curriculum-passage-presentation",
            "presentation_ref",
        ),
        (value.prerequisite_exercise_ref, "exercise-instance", "prerequisite_exercise_ref"),
        (value.application_exercise_ref, "exercise-instance", "application_exercise_ref"),
        (value.graph_ref, "acquisition-graph-slice", "graph_ref"),
        (
            value.mastery_projection_ref,
            "curriculum-mastery-projection",
            "mastery_projection_ref",
        ),
        (value.unlock_decision_ref, "curriculum-unlock-decision", "unlock_decision_ref"),
        (value.support_state_ref, "support-state", "support_state_ref"),
    ):
        _semantic_reference(reference, artifact_type, f"piece_return.{name}", issues)
    for name, identifiers in (
        ("completed_attempt_ids", value.completed_attempt_ids),
        ("evidence_record_ids", value.evidence_record_ids),
        ("active_event_ids", value.active_event_ids),
    ):
        _unique_ids(identifiers, f"piece_return.{name}", issues)
        if not identifiers:
            _add(
                issues,
                "TMM-RETURN-EVIDENCE-INCOMPLETE",
                f"piece_return.{name}",
                "an exact return cannot omit completed practice or passage identity",
            )
    _rule_reference(value.generation_rule, "piece_return.generation_rule", issues)
    if (
        value.generation_rule.rule_id != "FUNDAMENTAL-RETURN-RULE-001"
        or value.generation_rule.rule_version != FUNDAMENTAL_RETURN_VERSION
    ):
        _add(
            issues,
            "TMM-RETURN-RULE-MISMATCH",
            "piece_return.generation_rule",
            "the return is not governed by the accepted deterministic rule",
        )
    if value.resolution is not ArtifactResolution.RESOLVED or value.diagnostics:
        _add(
            issues,
            "TMM-RETURN-AMBIGUOUS",
            "piece_return.resolution",
            "only a clean policy-authorized return may cross this boundary",
        )

    if practice is not None:
        expected_ref = SemanticReference(
            "curriculum-fundamental-practice",
            practice.id,
            practice.semantic_fingerprint,
        )
        if (
            value.practice_ref != expected_ref
            or value.analysis_id != practice.analysis_id
            or value.package_id != practice.package_id
            or value.score_id != practice.score_id
            or value.requirement_ref != practice.requirement_ref
            or value.primitive_ref != practice.primitive_ref
            or value.practice_scope_ref != practice.practice_scope_ref
            or value.presentation_ref != practice.presentation_ref
            or value.prerequisite_exercise_ref != practice.prerequisite_exercise_ref
            or value.prerequisite_node_id != practice.prerequisite_node_id
            or value.return_node_id != practice.return_node_id
        ):
            _add(
                issues,
                "TMM-RETURN-PRACTICE-MISMATCH",
                "piece_return.practice_ref",
                "the return differs from its exact completed prerequisite practice",
            )
        issues.extend(validate_curriculum_fundamental_practice(practice))

    if mastery is not None:
        evidence_ids = tuple(
            dict.fromkeys(
                identifier
                for item in mastery.dimension_decisions
                for identifier in item.evidence_record_ids
            )
        )
        expected_ref = SemanticReference(
            "curriculum-mastery-projection",
            mastery.id,
            mastery.semantic_fingerprint,
        )
        if (
            value.mastery_projection_ref != expected_ref
            or value.graph_ref != mastery.graph_ref
            or value.support_state_ref != mastery.support_state_ref
            or value.prerequisite_node_id != mastery.node_id
            or value.prerequisite_exercise_ref != mastery.exercise_ref
            or value.requirement_ref != mastery.requirement_ref
            or value.primitive_ref != mastery.primitive_ref
            or value.practice_scope_ref != mastery.practice_scope_ref
            or value.completed_attempt_ids != mastery.complete_passing_attempt_ids
            or value.evidence_record_ids != evidence_ids
            or mastery.status is not CurriculumMasteryStatus.MASTERED
        ):
            _add(
                issues,
                "TMM-RETURN-MASTERY-MISMATCH",
                "piece_return.mastery_projection_ref",
                "the return changed or bypassed authoritative mastery evidence",
            )
        issues.extend(validate_curriculum_mastery_projection(mastery))

    if decision is not None:
        expected_ref = SemanticReference(
            "curriculum-unlock-decision",
            decision.id,
            decision.semantic_fingerprint,
        )
        if (
            value.unlock_decision_ref != expected_ref
            or decision.action is not CurriculumUnlockAction.UNLOCK_SUCCESSOR
            or value.prerequisite_node_id != decision.current_node_id
            or value.return_edge_id != decision.selected_edge_id
            or value.return_node_id != decision.next_node_id
        ):
            _add(
                issues,
                "TMM-RETURN-DECISION-MISMATCH",
                "piece_return.unlock_decision_ref",
                "the return was not selected by the exact authoritative policy decision",
            )
        issues.extend(validate_curriculum_unlock_decision(decision, mastery, graph))

    if branches is not None:
        branch = next(
            (
                item
                for item in branches.branches
                if item.requirement_ref.id == value.requirement_ref.id
            ),
            None,
        )
        nodes = {item.id: item for item in branches.nodes}
        exercises = {item.id: item for item in branches.exercises}
        prerequisite = exercises.get(value.prerequisite_exercise_ref.id)
        application_node = nodes.get(value.return_node_id)
        application = (
            exercises.get(application_node.exercise_ref.id)
            if application_node is not None and application_node.exercise_ref is not None
            else None
        )
        reconnect = (
            tuple(
                item
                for item in prerequisite.activity_sequence
                if item.form is ActivityForm.RECONNECT
            )
            if prerequisite is not None
            else ()
        )
        if (
            branch is None
            or branch.prerequisite_node_id != value.prerequisite_node_id
            or branch.application_node_id != value.return_node_id
            or application_node is None
            or application_node.exercise_ref != value.application_exercise_ref
            or application is None
            or application.material.practice_scope_ref != value.practice_scope_ref
            or application.material.active_target_ids != value.active_event_ids
            or len(reconnect) != 1
            or reconnect[0].id != value.reconnect_activity_id
            or reconnect[0].evidence_producing
        ):
            _add(
                issues,
                "TMM-RETURN-APPLICATION-MISMATCH",
                "piece_return.application_exercise_ref",
                "the return target is not the graph-declared application exercise",
            )

    if graph is not None:
        expected_graph_ref = SemanticReference(
            "acquisition-graph-slice",
            graph.id,
            graph.semantic_fingerprint,
        )
        edge = next((item for item in graph.edges if item.id == value.return_edge_id), None)
        if (
            value.graph_ref != expected_graph_ref
            or edge is None
            or edge.kind is not CurriculumEdgeKind.RETURN_TO
            or edge.source_node_id != value.prerequisite_node_id
            or edge.target_node_id != value.return_node_id
            or edge.return_node_id != value.return_node_id
        ):
            _add(
                issues,
                "TMM-RETURN-EDGE-MISMATCH",
                "piece_return.return_edge_id",
                "the selected graph edge is not the declared exact return",
            )

    if presentation is not None and (
        value.presentation_ref.id != presentation.id
        or value.presentation_ref.semantic_fingerprint != presentation.semantic_fingerprint
        or value.practice_scope_ref != presentation.practice_scope_ref
        or value.active_event_ids != presentation.active_target_ids
        or value.analysis_id != presentation.analysis_id
        or value.package_id != presentation.package_id
        or value.score_id != presentation.score_id
    ):
        _add(
            issues,
            "TMM-RETURN-PASSAGE-MISMATCH",
            "piece_return.active_event_ids",
            "the return changed the exact source passage",
        )
    _fingerprint(value, "piece_return", issues)
    return tuple(issues)


def _playback_plan_sha256(value: PlaybackPlan) -> str:
    payload = json.dumps(
        playback_plan_to_dict(value),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _validate_renderer_targets(
    targets: tuple[CurriculumRendererTarget, ...],
    canonical_ids: tuple[str, ...],
    canonical_kind: str,
    path: str,
    issues: list[CurriculumValidationIssue],
) -> None:
    target_ids = tuple(item.canonical_id for item in targets)
    if target_ids != canonical_ids:
        _add(
            issues,
            "TMM-PRESENTATION-RENDERER-CROSSWALK",
            path,
            "renderer targets do not preserve canonical order and membership",
        )
    if len({item.renderer_anchor for item in targets}) != len(targets) or any(
        not item.renderer_anchor or item.canonical_kind != canonical_kind for item in targets
    ):
        _add(
            issues,
            "TMM-PRESENTATION-RENDERER-CROSSWALK",
            path,
            "renderer targets are missing, duplicated, or typed incorrectly",
        )


def validate_primitive(
    value: LearningPrimitive,
    catalogue: tuple[LearningPrimitive, ...] | None = None,
) -> tuple[CurriculumValidationIssue, ...]:
    """Validate one primitive and optional catalogue references."""

    issues: list[CurriculumValidationIssue] = []
    _common(value.schema_version, value.id, value.semantic_fingerprint, "primitive", issues)
    if value.catalogue_id != PRIMITIVE_CATALOGUE_ID:
        _add(issues, "TMM-PRIMITIVE-UNKNOWN", "primitive.catalogue_id", "unknown catalogue")
    if not value.capability.strip() or not value.definition.strip():
        _add(
            issues,
            "TMM-CONTRACT-INVALID-EXACT-VALUE",
            "primitive",
            "capability and definition are required",
        )
    _unique_ids(value.prerequisite_ids, "primitive.prerequisite_ids", issues)
    names = tuple(item.name for item in value.parameter_schema)
    if len(names) != len(set(names)):
        _add(
            issues,
            "TMM-CONTRACT-DUPLICATE-ID",
            "primitive.parameter_schema",
            "parameter name repeats",
        )
    _fingerprint(value, "primitive", issues)
    if catalogue is not None:
        known = {item.id for item in catalogue}
        if not set(value.prerequisite_ids) <= known:
            _add(
                issues,
                "TMM-PRIMITIVE-UNKNOWN",
                "primitive.prerequisite_ids",
                "prerequisite is not in catalogue",
            )
    return tuple(issues)


def validate_requirement(
    value: PassageSkillRequirement,
    scope: PracticeScopeAssignment | None = None,
    primitives: tuple[LearningPrimitive, ...] = (),
) -> tuple[CurriculumValidationIssue, ...]:
    """Validate one source-linked primitive requirement."""

    issues: list[CurriculumValidationIssue] = []
    _common(value.schema_version, value.id, value.semantic_fingerprint, "requirement", issues)
    primitive_by_id = {item.id: item for item in primitives}
    primitive = primitive_by_id.get(value.primitive_ref.id)
    if primitives and primitive is None:
        _add(
            issues,
            "TMM-PRIMITIVE-UNKNOWN",
            "requirement.primitive_ref",
            "primitive is absent from catalogue",
        )
    elif (
        primitive is not None
        and primitive.semantic_fingerprint != value.primitive_ref.semantic_fingerprint
    ):
        _add(
            issues,
            "TMM-CONTRACT-FINGERPRINT-MISMATCH",
            "requirement.primitive_ref",
            "primitive fingerprint differs",
        )
    if primitive is not None:
        definitions = {item.name: item for item in primitive.parameter_schema}
        actual = {item.name: item for item in value.target_parameters}
        if unknown := set(actual) - set(definitions):
            _add(
                issues,
                "TMM-CONTRACT-INVALID-EXACT-VALUE",
                "requirement.target_parameters",
                f"unknown primitive parameters: {sorted(unknown)!r}",
            )
        if missing := {
            name
            for name, definition in definitions.items()
            if definition.required and name not in actual
        }:
            _add(
                issues,
                "TMM-REQUIREMENT-EVIDENCE-INCOMPLETE",
                "requirement.target_parameters",
                f"required primitive parameters are absent: {sorted(missing)!r}",
            )
        if any(
            name in definitions and parameter.value_type != definitions[name].value_type
            for name, parameter in actual.items()
        ):
            _add(
                issues,
                "TMM-CONTRACT-INVALID-EXACT-VALUE",
                "requirement.target_parameters",
                "parameter type does not match primitive schema",
            )
    if scope is not None:
        if scope.id != value.practice_scope_ref.id:
            _add(
                issues,
                "TMM-SCOPE-FOREIGN-REFERENCE",
                "requirement.practice_scope_ref",
                "scope ID differs",
            )
        if scope.semantic_fingerprint != value.practice_scope_ref.semantic_fingerprint:
            _add(
                issues,
                "TMM-CONTRACT-FINGERPRINT-MISMATCH",
                "requirement.practice_scope_ref",
                "scope fingerprint differs",
            )
        context = set(scope.event_universe_ids)
        context.update(group_id for group in scope.layer_groups for group_id in group.measure_ids)
        context.update(group_id for group in scope.layer_groups for group_id in group.staff_ids)
        context.update(group_id for group in scope.layer_groups for group_id in group.voice_ids)
        context.update((scope.score_id, scope.part_id))
        if not set(value.canonical_evidence_refs) <= context:
            _add(
                issues,
                "TMM-SCOPE-FOREIGN-REFERENCE",
                "requirement.canonical_evidence_refs",
                "canonical evidence lies outside scope context",
            )
    if not value.canonical_evidence_refs:
        _add(
            issues,
            "TMM-REQUIREMENT-EVIDENCE-INCOMPLETE",
            "requirement.canonical_evidence_refs",
            "no canonical evidence",
        )
    _unique_ids(value.canonical_evidence_refs, "requirement.canonical_evidence_refs", issues)
    _unique_ids(value.analysis_evidence_refs, "requirement.analysis_evidence_refs", issues)
    parameter_names = tuple(item.name for item in value.target_parameters)
    if parameter_names != tuple(sorted(parameter_names)) or len(parameter_names) != len(
        set(parameter_names)
    ):
        _add(
            issues,
            "TMM-CONTRACT-INVALID-EXACT-VALUE",
            "requirement.target_parameters",
            "parameters must be uniquely sorted by name",
        )
    _rule_reference(value.derivation_rule, "requirement.derivation_rule", issues)
    if value.resolution is ArtifactResolution.RESOLVED:
        if value.necessity is RequirementNecessity.UNRESOLVED or value.review_ref is not None:
            _add(
                issues,
                "TMM-REQUIREMENT-AMBIGUOUS",
                "requirement.resolution",
                "resolved requirement retains unresolved state",
            )
        if not value.required_dimensions:
            _add(
                issues,
                "TMM-REQUIREMENT-UNOBSERVABLE",
                "requirement.required_dimensions",
                "resolved requirement has no observable target",
            )
    _fingerprint(value, "requirement", issues)
    return tuple(issues)


def validate_requirement_set(
    value: PassageRequirementSet,
    package: CanonicalMusicPackage | None = None,
    analysis: ScoreAnalysis | None = None,
) -> tuple[CurriculumValidationIssue, ...]:
    """Validate one complete deterministic scope-and-requirement result."""

    del package  # package cross-reference is already represented by the validated analysis digest.
    issues: list[CurriculumValidationIssue] = []
    scope_by_id = {item.id: item for item in value.scopes}
    if len(scope_by_id) != len(value.scopes):
        _add(issues, "TMM-CONTRACT-DUPLICATE-ID", "result.scopes", "scope ID repeats")
    anchor_by_id = {item.id: item for item in value.anchor_sets}
    if len(anchor_by_id) != len(value.anchor_sets):
        _add(
            issues,
            "TMM-CONTRACT-DUPLICATE-ID",
            "result.anchor_sets",
            "anchor-set ID repeats",
        )
    primitive_by_id = {item.id: item for item in value.primitives}
    if len(primitive_by_id) != len(value.primitives):
        _add(issues, "TMM-CONTRACT-DUPLICATE-ID", "result.primitives", "primitive ID repeats")
    requirement_ids = {item.id for item in value.requirements}
    if len(requirement_ids) != len(value.requirements):
        _add(
            issues,
            "TMM-CONTRACT-DUPLICATE-ID",
            "result.requirements",
            "requirement ID repeats",
        )
    for practice_scope in value.scopes:
        issues.extend(validate_practice_scope(practice_scope, analysis))
        if practice_scope.canonical_anchor_set_id not in anchor_by_id:
            _add(
                issues,
                "TMM-SCOPE-FOREIGN-REFERENCE",
                f"result.scopes[{practice_scope.id}].canonical_anchor_set_id",
                "anchor set is absent",
            )
        if any(item not in scope_by_id for item in practice_scope.component_scope_ids):
            _add(
                issues,
                "TMM-SCOPE-COMPONENT-MISMATCH",
                f"result.scopes[{practice_scope.id}].component_scope_ids",
                "component scope is absent",
            )
        elif (
            practice_scope.resolution is ArtifactResolution.RESOLVED
            and practice_scope.notation_condition.value == "combined"
        ):
            components = tuple(scope_by_id[item] for item in practice_scope.component_scope_ids)
            component_events = [set(item.active_target_ids) for item in components]
            overlaps = any(
                left & right
                for index, left in enumerate(component_events)
                for right in component_events[index + 1 :]
            )
            if overlaps or set().union(*component_events) != set(practice_scope.active_target_ids):
                _add(
                    issues,
                    "TMM-SCOPE-COMPONENT-MISMATCH",
                    f"result.scopes[{practice_scope.id}].component_scope_ids",
                    "components do not form an exact disjoint combined target",
                )
    for primitive in value.primitives:
        issues.extend(validate_primitive(primitive, value.primitives))
    issues.extend(_catalogue_cycle_issues(value.primitives))
    for requirement in value.requirements:
        requirement_scope = scope_by_id.get(requirement.practice_scope_ref.id)
        issues.extend(validate_requirement(requirement, requirement_scope, value.primitives))
        if requirement.prerequisite_requirement_ids != tuple(
            sorted(set(requirement.prerequisite_requirement_ids))
        ):
            _add(
                issues,
                "TMM-CONTRACT-INVALID-EXACT-VALUE",
                f"result.requirements[{requirement.id}].prerequisite_requirement_ids",
                "prerequisite requirement IDs must be a uniquely sorted semantic set",
            )
        if not set(requirement.prerequisite_requirement_ids) <= requirement_ids:
            _add(
                issues,
                "TMM-REQUIREMENT-EVIDENCE-INCOMPLETE",
                f"result.requirements[{requirement.id}].prerequisite_requirement_ids",
                "prerequisite requirement is absent",
            )
        else:
            requirement_primitive = primitive_by_id.get(requirement.primitive_ref.id)
            permitted_primitive_ids = (
                set(requirement_primitive.prerequisite_ids) if requirement_primitive else set()
            )
            permitted_scope_ids = {requirement.practice_scope_ref.id}
            if requirement_scope is not None:
                permitted_scope_ids.update(requirement_scope.component_scope_ids)
            for dependency_id in requirement.prerequisite_requirement_ids:
                dependency = next(item for item in value.requirements if item.id == dependency_id)
                if (
                    dependency.primitive_ref.id not in permitted_primitive_ids
                    or dependency.practice_scope_ref.id not in permitted_scope_ids
                ):
                    _add(
                        issues,
                        "TMM-REQUIREMENT-EVIDENCE-INCOMPLETE",
                        f"result.requirements[{requirement.id}].prerequisite_requirement_ids",
                        "prerequisite is not a permitted primitive/scope dependency",
                    )
    if analysis is not None and value.analysis_id != analysis.id:
        _add(
            issues,
            "TMM-SCOPE-FOREIGN-REFERENCE",
            "result.analysis_id",
            "analysis ID differs",
        )
    return tuple(issues)


def validate_exercise_instance(
    value: ExerciseInstance,
    requirement: PassageSkillRequirement | None = None,
    scope: PracticeScopeAssignment | None = None,
) -> tuple[CurriculumValidationIssue, ...]:
    """Validate one generated canonical-excerpt exercise and its return."""

    issues: list[CurriculumValidationIssue] = []
    _common(value.schema_version, value.id, value.semantic_fingerprint, "exercise", issues)
    if value.material.material_type != "canonical-excerpt":
        _add(
            issues,
            "TMM-EXERCISE-MATERIAL-CONFLICT",
            "exercise.material.material_type",
            "implemented 9B slices admit only exact canonical excerpts",
        )
    if not value.material.active_target_ids:
        _add(
            issues,
            "TMM-EXERCISE-MATERIAL-CONFLICT",
            "exercise.material.active_target_ids",
            "canonical target is empty",
        )
    _unique_ids(value.material.active_target_ids, "exercise.material.active_target_ids", issues)
    _unique_ids(
        value.material.inactive_context_ids,
        "exercise.material.inactive_context_ids",
        issues,
    )
    if set(value.material.active_target_ids) & set(value.material.inactive_context_ids):
        _add(
            issues,
            "TMM-EXERCISE-MATERIAL-CONFLICT",
            "exercise.material",
            "active target overlaps inactive context",
        )
    activity_ids = tuple(item.id for item in value.activity_sequence)
    _unique_ids(activity_ids, "exercise.activity_sequence", issues)
    if not value.activity_sequence or not any(
        item.evidence_producing for item in value.activity_sequence
    ):
        _add(
            issues,
            "TMM-REQUIREMENT-EVIDENCE-INCOMPLETE",
            "exercise.activity_sequence",
            "exercise has no evidence-producing response",
        )
    dimensions = tuple(item.dimension for item in value.required_evidence_exits)
    if not dimensions or len(dimensions) != len(set(dimensions)):
        _add(
            issues,
            "TMM-REQUIREMENT-EVIDENCE-INCOMPLETE",
            "exercise.required_evidence_exits",
            "evidence exits must be non-empty and dimension-unique",
        )
    if (
        not value.support_envelope.permitted_conditions
        or value.support_envelope.initial_condition
        not in value.support_envelope.permitted_conditions
        or (
            value.support_envelope.independent_condition is not None
            and value.support_envelope.independent_condition
            not in value.support_envelope.permitted_conditions
        )
    ):
        _add(
            issues,
            "TMM-EXERCISE-SUPPORT-OUTSIDE-ENVELOPE",
            "exercise.support_envelope",
            "initial or independent support is not permitted",
        )
    _stable_id(value.return_target_id, "exercise.return_target_id", issues)
    _rule_reference(value.generation_rule, "exercise.generation_rule", issues)
    if requirement is not None:
        if (
            value.requirement_ref.id != requirement.id
            or value.requirement_ref.semantic_fingerprint != requirement.semantic_fingerprint
        ):
            _add(
                issues,
                "TMM-SCOPE-FOREIGN-REFERENCE",
                "exercise.requirement_ref",
                "requirement reference differs",
            )
        if set(dimensions) != set(requirement.required_dimensions):
            _add(
                issues,
                "TMM-REQUIREMENT-EVIDENCE-INCOMPLETE",
                "exercise.required_evidence_exits",
                "exercise dimensions differ from its requirement",
            )
    if scope is not None:
        if (
            value.practice_scope_ref.id != scope.id
            or value.practice_scope_ref.semantic_fingerprint != scope.semantic_fingerprint
            or value.material.practice_scope_ref != value.practice_scope_ref
        ):
            _add(
                issues,
                "TMM-SCOPE-FOREIGN-REFERENCE",
                "exercise.practice_scope_ref",
                "practice-scope reference differs",
            )
        if (
            value.material.score_package_digest != scope.score_package_digest
            or value.material.score_id != scope.score_id
            or value.material.canonical_anchor_set_id != scope.canonical_anchor_set_id
            or value.material.active_target_ids != scope.active_target_ids
            or value.material.inactive_context_ids != scope.inactive_context_ids
        ):
            _add(
                issues,
                "TMM-EXERCISE-MATERIAL-CONFLICT",
                "exercise.material",
                "canonical excerpt differs from the resolved scope",
            )
    _fingerprint(value, "exercise", issues)
    return tuple(issues)


def validate_prerequisite_branch_set(
    value: PrerequisiteBranchSet,
    requirements: PassageRequirementSet,
) -> tuple[CurriculumValidationIssue, ...]:
    """Validate the composable 9B.2 branch slice and exact return edges."""

    issues: list[CurriculumValidationIssue] = []
    if value.graph_identity != CURRICULUM_GRAPH_ID:
        _add(
            issues,
            "TMM-CONTRACT-UNKNOWN-VERSION",
            "branches.graph_identity",
            "unknown curriculum graph identity",
        )
    if value.analysis_id != requirements.analysis_id:
        _add(
            issues,
            "TMM-SCOPE-FOREIGN-REFERENCE",
            "branches.analysis_id",
            "analysis identity differs",
        )
    unresolved = any(
        item.resolution is not ArtifactResolution.RESOLVED for item in requirements.scopes
    )
    if unresolved:
        if value.resolution is not ArtifactResolution.REVIEW_REQUIRED:
            _add(
                issues,
                "TMM-REQUIREMENT-AMBIGUOUS",
                "branches.resolution",
                "unresolved scope must stop for review",
            )
        if value.nodes or value.edges or value.exercises or value.branches:
            _add(
                issues,
                "TMM-GRAPH-ROOT-INVALID",
                "branches",
                "review-required scope cannot emit playable branches",
            )
        if not value.diagnostics:
            _add(
                issues,
                "TMM-REQUIREMENT-AMBIGUOUS",
                "branches.diagnostics",
                "review stop has no diagnostic",
            )
        return tuple(issues)

    if value.resolution is not ArtifactResolution.RESOLVED or value.diagnostics:
        _add(
            issues,
            "TMM-REQUIREMENT-AMBIGUOUS",
            "branches.resolution",
            "resolved inputs require a clean resolved branch set",
        )
    node_by_id = _unique_by_id(value.nodes, "branches.nodes", issues)
    _unique_by_id(value.edges, "branches.edges", issues)
    exercise_by_id = _unique_by_id(value.exercises, "branches.exercises", issues)
    requirement_by_id = {item.id: item for item in requirements.requirements}
    scope_by_id = {item.id: item for item in requirements.scopes}
    branch_by_requirement = {item.requirement_ref.id: item for item in value.branches}
    if len(branch_by_requirement) != len(value.branches):
        _add(
            issues,
            "TMM-CONTRACT-DUPLICATE-ID",
            "branches.branches",
            "requirement branch repeats",
        )
    if set(branch_by_requirement) != set(requirement_by_id):
        _add(
            issues,
            "TMM-GRAPH-NODE-UNREACHABLE",
            "branches.branches",
            "branch coverage differs from resolved requirements",
        )
    for exercise in value.exercises:
        requirement = requirement_by_id.get(exercise.requirement_ref.id)
        scope = scope_by_id.get(exercise.practice_scope_ref.id)
        issues.extend(validate_exercise_instance(exercise, requirement, scope))
    for node in value.nodes:
        _stable_id(node.id, f"branches.nodes[{node.id}].id", issues)
        if node.exercise_ref is not None:
            referenced_exercise = exercise_by_id.get(node.exercise_ref.id)
            if (
                referenced_exercise is None
                or referenced_exercise.semantic_fingerprint
                != node.exercise_ref.semantic_fingerprint
            ):
                _add(
                    issues,
                    "TMM-SCOPE-FOREIGN-REFERENCE",
                    f"branches.nodes[{node.id}].exercise_ref",
                    "exercise reference is absent or changed",
                )
    for edge in value.edges:
        _stable_id(edge.id, f"branches.edges[{edge.id}].id", issues)
        if edge.source_node_id not in node_by_id or edge.target_node_id not in node_by_id:
            _add(
                issues,
                "TMM-GRAPH-NODE-UNREACHABLE",
                f"branches.edges[{edge.id}]",
                "edge endpoint is absent",
            )
    for requirement_id, branch in branch_by_requirement.items():
        requirement = requirement_by_id[requirement_id]
        expected = {
            branch.diagnostic_node_id: "diagnostic",
            branch.prerequisite_node_id: "prerequisite",
            branch.application_node_id: "application",
        }
        for node_id, kind in expected.items():
            branch_node = node_by_id.get(node_id)
            if (
                branch_node is None
                or branch_node.kind.value != kind
                or branch_node.requirement_ref != branch.requirement_ref
            ):
                _add(
                    issues,
                    "TMM-GRAPH-NODE-UNREACHABLE",
                    f"branches[{requirement_id}]",
                    f"{kind} node is absent or mismatched",
                )
            elif branch_node.exercise_ref is not None:
                branch_exercise = exercise_by_id.get(branch_node.exercise_ref.id)
                if (
                    branch_exercise is not None
                    and branch_exercise.return_target_id != branch.application_node_id
                ):
                    _add(
                        issues,
                        "TMM-EXERCISE-RETURN-TARGET-MISSING",
                        f"branches[{requirement_id}].{kind}",
                        "exercise return target differs from its source application",
                    )
        if branch.prerequisite_requirement_ids != requirement.prerequisite_requirement_ids:
            _add(
                issues,
                "TMM-REQUIREMENT-EVIDENCE-INCOMPLETE",
                f"branches[{requirement_id}].prerequisite_requirement_ids",
                "branch dependencies differ from requirement dependencies",
            )
        for dependency_id in requirement.prerequisite_requirement_ids:
            dependency_branch = branch_by_requirement.get(dependency_id)
            if dependency_branch is None or not any(
                edge.kind is CurriculumEdgeKind.REQUIRES
                and edge.source_node_id == branch.application_node_id
                and edge.target_node_id == dependency_branch.application_node_id
                for edge in value.edges
            ):
                _add(
                    issues,
                    "TMM-REQUIREMENT-EVIDENCE-INCOMPLETE",
                    f"branches[{requirement_id}].requires",
                    "required application dependency edge is missing",
                )
        expected_transitions = {
            (
                CurriculumEdgeKind.ON_SATISFIED,
                branch.diagnostic_node_id,
                branch.application_node_id,
            ),
            (
                CurriculumEdgeKind.ON_UNCONFIRMED,
                branch.diagnostic_node_id,
                branch.prerequisite_node_id,
            ),
            (
                CurriculumEdgeKind.RETURN_TO,
                branch.prerequisite_node_id,
                branch.application_node_id,
            ),
        }
        actual = {(edge.kind, edge.source_node_id, edge.target_node_id) for edge in value.edges}
        if not expected_transitions <= actual:
            _add(
                issues,
                "TMM-GRAPH-RETURN-MISMATCH",
                f"branches[{requirement_id}]",
                "diagnostic or exact source-return edge is missing",
            )
        return_edges = tuple(
            edge
            for edge in value.edges
            if edge.kind is CurriculumEdgeKind.RETURN_TO
            and edge.source_node_id == branch.prerequisite_node_id
        )
        if len(return_edges) != 1 or return_edges[0].return_node_id != branch.application_node_id:
            _add(
                issues,
                "TMM-GRAPH-RETURN-MISMATCH",
                f"branches[{requirement_id}].return",
                "prerequisite does not return to its exact source application",
            )
    issues.extend(_graph_static_cycle_issues(value.edges))
    return tuple(issues)


def validate_tempo_configuration(
    value: TempoConfiguration,
) -> tuple[CurriculumValidationIssue, ...]:
    """Validate the frozen numeric ADR-0012 baseline without float defaults."""

    issues: list[CurriculumValidationIssue] = []
    _common(value.schema_version, value.id, value.semantic_fingerprint, "tempo", issues)
    if value.policy_identity != TEMPO_POLICY_ID:
        _add(
            issues,
            "TMM-CONTRACT-UNKNOWN-VERSION",
            "tempo.policy_identity",
            "unknown deterministic tempo policy",
        )
    probes = value.diagnostic_probe_percentages
    if (
        not probes
        or probes != tuple(sorted(set(probes), reverse=True))
        or probes[0] != 100
        or any(item < 1 or item > 100 for item in probes)
        or len(probes) > value.diagnostic_attempt_budget
    ):
        _add(
            issues,
            "TMM-CONTRACT-INVALID-EXACT-VALUE",
            "tempo.diagnostic_probe_percentages",
            "probes must be unique, descending, bounded, start at 100, and fit the budget",
        )
    if not 1 <= value.tempo_increment_percentage <= 25:
        _add(
            issues,
            "TMM-CONTRACT-INVALID-EXACT-VALUE",
            "tempo.tempo_increment_percentage",
            "increment must be between 1 and 25 percentage points",
        )
    if not 0 <= value.tempo_tolerance_percentage <= 10:
        _add(
            issues,
            "TMM-CONTRACT-INVALID-EXACT-VALUE",
            "tempo.tempo_tolerance_percentage",
            "tolerance must be between 0 and 10 percentage points",
        )
    if any(
        item < 1
        for item in (
            value.diagnostic_attempt_budget,
            value.acquisition_retry_budget,
            value.tempo_probe_retry_budget,
            value.remediation_budget,
            value.phrase_group_size,
            value.stable_performance_passes,
        )
    ):
        _add(
            issues,
            "TMM-CONTRACT-INVALID-EXACT-VALUE",
            "tempo",
            "all budgets and cadence values must be positive",
        )
    _fingerprint(value, "tempo", issues)
    return tuple(issues)


def validate_controlled_tempo_plan(
    value: ControlledTempoPlan,
    configuration: TempoConfiguration,
) -> tuple[CurriculumValidationIssue, ...]:
    """Validate one exact, scope-local controlled-tempo selection."""

    issues: list[CurriculumValidationIssue] = []
    _common(value.schema_version, value.id, value.semantic_fingerprint, "tempo_plan", issues)
    expected_ref = (
        configuration.id,
        configuration.semantic_fingerprint,
    )
    if (
        value.configuration_ref.artifact_type != "tempo-configuration"
        or (value.configuration_ref.id, value.configuration_ref.semantic_fingerprint)
        != expected_ref
    ):
        _add(
            issues,
            "TMM-CONTRACT-FINGERPRINT-MISMATCH",
            "tempo_plan.configuration_ref",
            "tempo configuration reference differs",
        )
    if value.reference_tempo_bpm <= 0:
        _add(
            issues,
            "TMM-CONTRACT-INVALID-EXACT-VALUE",
            "tempo_plan.reference_tempo_bpm",
            "reference tempo must be positive",
        )
    percentages = (
        value.current_controlled_percentage,
        value.tested_percentage,
        value.supported_ceiling_percentage,
    )
    if any(item is not None and not 1 <= item <= 100 for item in percentages):
        _add(
            issues,
            "TMM-CONTRACT-INVALID-EXACT-VALUE",
            "tempo_plan",
            "tempo percentages must be bounded integers",
        )
    if value.state is TempoPlanState.DIAGNOSTIC_REQUIRED:
        if (
            value.current_controlled_percentage is not None
            or value.supported_ceiling_percentage is not None
            or value.diagnostic_probe_percentages != configuration.diagnostic_probe_percentages
            or value.evidence_refs
        ):
            _add(
                issues,
                "TMM-EVIDENCE-INCOMPATIBLE",
                "tempo_plan",
                "diagnostic-required plan cannot claim supported tempo evidence",
            )
    elif (
        value.current_controlled_percentage is None
        or value.supported_ceiling_percentage is None
        or value.current_controlled_percentage > value.supported_ceiling_percentage
        or value.diagnostic_probe_percentages
        or not value.evidence_refs
    ):
        _add(
            issues,
            "TMM-EVIDENCE-INCOMPATIBLE",
            "tempo_plan",
            "controlled plan requires compatible evidence and a bounded ceiling",
        )
    _fingerprint(value, "tempo_plan", issues)
    return tuple(issues)


def validate_acquisition_graph_slice(
    value: AcquisitionGraphSlice,
) -> tuple[CurriculumValidationIssue, ...]:
    """Validate the composable 9B.3 layer, cumulative, and tempo slice."""

    issues: list[CurriculumValidationIssue] = []
    _common(value.schema_version, value.id, value.semantic_fingerprint, "acquisition", issues)
    if value.graph_identity != CURRICULUM_GRAPH_ID:
        _add(
            issues,
            "TMM-CONTRACT-UNKNOWN-VERSION",
            "acquisition.graph_identity",
            "unknown curriculum graph identity",
        )
    issues.extend(validate_tempo_configuration(value.tempo_configuration))
    for plan in value.tempo_plans:
        issues.extend(validate_controlled_tempo_plan(plan, value.tempo_configuration))
    if value.resolution is ArtifactResolution.REVIEW_REQUIRED:
        if (
            value.nodes
            or value.edges
            or value.exercises
            or value.branches
            or value.stages
            or value.tempo_plans
            or not value.diagnostics
        ):
            _add(
                issues,
                "TMM-GRAPH-ROOT-INVALID",
                "acquisition",
                "review stop cannot emit a playable acquisition route",
            )
        _fingerprint(value, "acquisition", issues)
        return tuple(issues)
    if value.resolution is not ArtifactResolution.RESOLVED or value.diagnostics:
        _add(
            issues,
            "TMM-REQUIREMENT-AMBIGUOUS",
            "acquisition.resolution",
            "resolved graph slice must have no stop diagnostics",
        )
    node_by_id = _unique_by_id(value.nodes, "acquisition.nodes", issues)
    _unique_by_id(value.edges, "acquisition.edges", issues)
    exercise_by_id = _unique_by_id(value.exercises, "acquisition.exercises", issues)
    plan_by_id = {item.id: item for item in value.tempo_plans}
    if len(plan_by_id) != len(value.tempo_plans):
        _add(
            issues,
            "TMM-CONTRACT-DUPLICATE-ID",
            "acquisition.tempo_plans",
            "tempo-plan identity repeats",
        )
    for exercise in value.exercises:
        issues.extend(validate_exercise_instance(exercise))
    for node in value.nodes:
        _stable_id(node.id, f"acquisition.nodes[{node.id}].id", issues)
        if node.exercise_ref is not None:
            referenced_exercise = exercise_by_id.get(node.exercise_ref.id)
            if (
                referenced_exercise is None
                or referenced_exercise.semantic_fingerprint
                != node.exercise_ref.semantic_fingerprint
            ):
                _add(
                    issues,
                    "TMM-SCOPE-FOREIGN-REFERENCE",
                    f"acquisition.nodes[{node.id}].exercise_ref",
                    "exercise reference is absent or changed",
                )
    for edge in value.edges:
        if edge.source_node_id not in node_by_id or edge.target_node_id not in node_by_id:
            _add(
                issues,
                "TMM-GRAPH-NODE-UNREACHABLE",
                f"acquisition.edges[{edge.id}]",
                "edge endpoint is absent",
            )
    if tuple(item.order for item in value.stages) != tuple(range(len(value.stages))):
        _add(
            issues,
            "TMM-CONTRACT-INVALID-EXACT-VALUE",
            "acquisition.stages",
            "stage order must be contiguous and semantic",
        )
    stage_ids = tuple(item.id for item in value.stages)
    _unique_ids(stage_ids, "acquisition.stages", issues)
    for stage in value.stages:
        if stage.node_id not in node_by_id:
            _add(
                issues,
                "TMM-GRAPH-NODE-UNREACHABLE",
                f"acquisition.stages[{stage.id}].node_id",
                "stage node is absent",
            )
        referenced_plan = plan_by_id.get(stage.tempo_plan_ref.id)
        if (
            referenced_plan is None
            or referenced_plan.semantic_fingerprint != stage.tempo_plan_ref.semantic_fingerprint
            or referenced_plan.practice_scope_ref != stage.practice_scope_ref
        ):
            _add(
                issues,
                "TMM-EVIDENCE-INCOMPATIBLE",
                f"acquisition.stages[{stage.id}].tempo_plan_ref",
                "stage tempo plan is absent, changed, or belongs to another scope",
            )
        elif stage.kind is AcquisitionStageKind.TEMPO_DIAGNOSTIC:
            if referenced_plan.state is not TempoPlanState.DIAGNOSTIC_REQUIRED:
                _add(
                    issues,
                    "TMM-EVIDENCE-INCOMPATIBLE",
                    f"acquisition.stages[{stage.id}]",
                    "tempo diagnostic has an already controlled plan",
                )
        elif stage.kind is not AcquisitionStageKind.SELF_PACED_COORDINATION and (
            referenced_plan.state is TempoPlanState.DIAGNOSTIC_REQUIRED
        ):
            _add(
                issues,
                "TMM-EVIDENCE-INCOMPATIBLE",
                f"acquisition.stages[{stage.id}]",
                "pulse-bearing stage has no controlled-tempo evidence",
            )
        if stage.kind is AcquisitionStageKind.SELF_PACED_COORDINATION:
            if len(stage.component_node_ids) < 2:
                _add(
                    issues,
                    "TMM-SCOPE-COMPONENT-MISMATCH",
                    f"acquisition.stages[{stage.id}].component_node_ids",
                    "coordination requires at least two completed components",
                )
            for component_id in stage.component_node_ids:
                if not any(
                    edge.kind is CurriculumEdgeKind.COMPONENT_OF
                    and edge.source_node_id == component_id
                    and edge.target_node_id == stage.node_id
                    for edge in value.edges
                ):
                    _add(
                        issues,
                        "TMM-SCOPE-COMPONENT-MISMATCH",
                        f"acquisition.stages[{stage.id}].component_node_ids",
                        "coordination component edge is missing",
                    )
    kinds = tuple(item.kind for item in value.stages)
    if AcquisitionStageKind.LEARNED_TO_DATE in kinds:
        learned_index = kinds.index(AcquisitionStageKind.LEARNED_TO_DATE)
        if AcquisitionStageKind.PHRASE_CONTROLLED_TEMPO not in kinds[:learned_index] or not any(
            edge.kind is CurriculumEdgeKind.CHECKPOINT_AFTER
            and edge.target_node_id == value.stages[learned_index].node_id
            for edge in value.edges
        ):
            _add(
                issues,
                "TMM-GRAPH-CHECKPOINT-MISSING",
                "acquisition.stages",
                "learned-to-date checkpoint is not gated by controlled phrase work",
            )
    if AcquisitionStageKind.TEMPO_DEVELOPMENT in kinds and (
        AcquisitionStageKind.LEARNED_TO_DATE not in kinds
        or kinds.index(AcquisitionStageKind.TEMPO_DEVELOPMENT)
        < kinds.index(AcquisitionStageKind.LEARNED_TO_DATE)
    ):
        _add(
            issues,
            "TMM-GRAPH-CHECKPOINT-MISSING",
            "acquisition.stages",
            "tempo development must follow learned-to-date integration",
        )
    _fingerprint(value, "acquisition", issues)
    return tuple(issues)


def validate_lasting_skill_graph_slice(
    value: LastingSkillGraphSlice,
    source_requirements: PassageRequirementSet | None = None,
    acquisition: AcquisitionGraphSlice | None = None,
    transfer_requirements: PassageRequirementSet | None = None,
) -> tuple[CurriculumValidationIssue, ...]:
    """Validate isolated delayed-retrieval and different-target routes."""

    issues: list[CurriculumValidationIssue] = []
    _common(value.schema_version, value.id, value.semantic_fingerprint, "lasting", issues)
    if value.graph_identity != LASTING_SKILL_GRAPH_ID:
        _add(
            issues,
            "TMM-CONTRACT-UNKNOWN-VERSION",
            "lasting.graph_identity",
            "unknown lasting-skill graph identity",
        )
    if value.resolution is ArtifactResolution.REVIEW_REQUIRED:
        if (
            value.nodes
            or value.edges
            or value.exercises
            or value.retention_schedules
            or value.transfer_targets
            or value.stages
            or not value.diagnostics
        ):
            _add(
                issues,
                "TMM-GRAPH-ROOT-INVALID",
                "lasting",
                "review stop cannot emit playable retention or transfer routes",
            )
        _fingerprint(value, "lasting", issues)
        return tuple(issues)
    if value.resolution is not ArtifactResolution.RESOLVED or value.diagnostics:
        _add(
            issues,
            "TMM-REQUIREMENT-AMBIGUOUS",
            "lasting.resolution",
            "resolved lasting-skill graph must have no stop diagnostics",
        )
    node_by_id = _unique_by_id(value.nodes, "lasting.nodes", issues)
    _unique_by_id(value.edges, "lasting.edges", issues)
    exercise_by_id = _unique_by_id(value.exercises, "lasting.exercises", issues)
    schedule_by_id = {item.id: item for item in value.retention_schedules}
    assignment_by_id = {item.id: item for item in value.transfer_targets}
    if len(schedule_by_id) != len(value.retention_schedules):
        _add(
            issues,
            "TMM-CONTRACT-DUPLICATE-ID",
            "lasting.retention_schedules",
            "retention schedule identity repeats",
        )
    if len(assignment_by_id) != len(value.transfer_targets):
        _add(
            issues,
            "TMM-CONTRACT-DUPLICATE-ID",
            "lasting.transfer_targets",
            "transfer target identity repeats",
        )
    if not value.retention_schedules:
        _add(
            issues,
            "TMM-RETENTION-SCHEDULE-INVALID",
            "lasting.retention_schedules",
            "resolved graph requires at least one delayed retention schedule",
        )
    if not value.transfer_targets:
        _add(
            issues,
            "TMM-TRANSFER-TARGET-UNRESOLVED",
            "lasting.transfer_targets",
            "resolved graph requires at least one proven transfer target",
        )

    if acquisition is not None:
        if (
            value.acquisition_graph_ref.artifact_type != "acquisition-graph-slice"
            or value.acquisition_graph_ref.id != acquisition.id
            or value.acquisition_graph_ref.semantic_fingerprint != acquisition.semantic_fingerprint
        ):
            _add(
                issues,
                "TMM-CONTRACT-FINGERPRINT-MISMATCH",
                "lasting.acquisition_graph_ref",
                "acquisition graph reference differs",
            )
        if (
            value.nodes[: len(acquisition.nodes)] != acquisition.nodes
            or value.edges[: len(acquisition.edges)] != acquisition.edges
            or value.exercises[: len(acquisition.exercises)] != acquisition.exercises
        ):
            _add(
                issues,
                "TMM-GRAPH-ROOT-INVALID",
                "lasting",
                "composition changed or reordered the acquisition slice",
            )
        if value.source_analysis_id != acquisition.analysis_id:
            _add(
                issues,
                "TMM-SCOPE-FOREIGN-REFERENCE",
                "lasting.source_analysis_id",
                "source analysis differs from acquisition",
            )

    source_requirement_by_id = (
        {item.id: item for item in source_requirements.requirements}
        if source_requirements is not None
        else {}
    )
    source_scope_by_id = (
        {item.id: item for item in source_requirements.scopes}
        if source_requirements is not None
        else {}
    )
    target_requirement_by_id = (
        {item.id: item for item in transfer_requirements.requirements}
        if transfer_requirements is not None
        else {}
    )
    target_scope_by_id = (
        {item.id: item for item in transfer_requirements.scopes}
        if transfer_requirements is not None
        else {}
    )
    if (
        source_requirements is not None
        and value.source_analysis_id != source_requirements.analysis_id
    ):
        _add(
            issues,
            "TMM-SCOPE-FOREIGN-REFERENCE",
            "lasting.source_analysis_id",
            "source requirement analysis differs",
        )
    if (
        transfer_requirements is not None
        and value.transfer_analysis_id != transfer_requirements.analysis_id
    ):
        _add(
            issues,
            "TMM-SCOPE-FOREIGN-REFERENCE",
            "lasting.transfer_analysis_id",
            "transfer requirement analysis differs",
        )

    r1_node_by_requirement: dict[str, str] = {}
    for schedule in value.retention_schedules:
        _validate_retention_schedule(schedule, issues)
        source_requirement = source_requirement_by_id.get(schedule.source_requirement_ref.id)
        source_scope = source_scope_by_id.get(schedule.source_scope_ref.id)
        if source_requirements is not None and (
            source_requirement is None
            or source_scope is None
            or schedule.source_requirement_ref
            != SemanticReference(
                "passage-skill-requirement",
                source_requirement.id,
                source_requirement.semantic_fingerprint,
            )
            or schedule.source_scope_ref
            != SemanticReference(
                "practice-scope-assignment", source_scope.id, source_scope.semantic_fingerprint
            )
            or source_requirement.practice_scope_ref != schedule.source_scope_ref
        ):
            _add(
                issues,
                "TMM-SCOPE-FOREIGN-REFERENCE",
                f"lasting.retention_schedules[{schedule.id}]",
                "source requirement or scope is absent, changed, or mismatched",
            )
        if schedule.source_node_id not in node_by_id or schedule.return_node_id not in node_by_id:
            _add(
                issues,
                "TMM-GRAPH-RETURN-MISMATCH",
                f"lasting.retention_schedules[{schedule.id}]",
                "source or return node is absent",
            )
        matching = tuple(
            stage
            for stage in value.stages
            if stage.kind is LastingSkillStageKind.RETENTION
            and stage.schedule_ref is not None
            and stage.schedule_ref.id == schedule.id
        )
        if len(matching) != 2:
            _add(
                issues,
                "TMM-RETENTION-SCHEDULE-INVALID",
                f"lasting.retention_schedules[{schedule.id}]",
                "schedule must produce exactly R1 and R2 stages",
            )
        elif matching:
            r1_node_by_requirement[schedule.source_requirement_ref.id] = matching[0].node_id

    for assignment in value.transfer_targets:
        _validate_transfer_assignment(
            assignment,
            source_requirement_by_id,
            source_scope_by_id,
            target_requirement_by_id,
            target_scope_by_id,
            issues,
        )
        if assignment.return_node_id not in node_by_id:
            _add(
                issues,
                "TMM-GRAPH-RETURN-MISMATCH",
                f"lasting.transfer_targets[{assignment.id}].return_node_id",
                "return node is absent",
            )

    if tuple(item.order for item in value.stages) != tuple(range(len(value.stages))):
        _add(
            issues,
            "TMM-CONTRACT-INVALID-EXACT-VALUE",
            "lasting.stages",
            "stage order must be contiguous",
        )
    _unique_ids(tuple(item.id for item in value.stages), "lasting.stages", issues)
    for stage in value.stages:
        node = node_by_id.get(stage.node_id)
        if node is None or node.exercise_ref is None:
            _add(
                issues,
                "TMM-GRAPH-NODE-UNREACHABLE",
                f"lasting.stages[{stage.id}]",
                "playable stage node or exercise reference is absent",
            )
            continue
        exercise = exercise_by_id.get(node.exercise_ref.id)
        if (
            exercise is None
            or exercise.semantic_fingerprint != node.exercise_ref.semantic_fingerprint
        ):
            _add(
                issues,
                "TMM-SCOPE-FOREIGN-REFERENCE",
                f"lasting.stages[{stage.id}].exercise_ref",
                "exercise is absent or changed",
            )
            continue
        issues.extend(validate_exercise_instance(exercise))
        contexts = {item.evidence_context for item in exercise.required_evidence_exits}
        if contexts != {stage.evidence_context} or stage.evidence_context not in {
            "retention",
            "transfer",
        }:
            _add(
                issues,
                "TMM-EVIDENCE-INCOMPATIBLE",
                f"lasting.stages[{stage.id}]",
                "retention and transfer evidence contexts must remain isolated",
            )
        if any(item.form.value == "demonstrate-listen" for item in exercise.activity_sequence):
            _add(
                issues,
                "TMM-RETENTION-SCHEDULE-INVALID"
                if stage.kind is LastingSkillStageKind.RETENTION
                else "TMM-TRANSFER-TARGET-UNRESOLVED",
                f"lasting.stages[{stage.id}].activity_sequence",
                "measured lasting-skill checks cannot reveal the answer first",
            )
        expected_kind = (
            CurriculumNodeKind.RETENTION
            if stage.kind is LastingSkillStageKind.RETENTION
            else CurriculumNodeKind.TRANSFER
        )
        if node.kind is not expected_kind:
            _add(
                issues,
                "TMM-GRAPH-NODE-UNREACHABLE",
                f"lasting.stages[{stage.id}].node_id",
                "stage node kind differs",
            )
        return_edges = tuple(
            edge
            for edge in value.edges
            if edge.kind is CurriculumEdgeKind.RETURN_TO and edge.source_node_id == stage.node_id
        )
        if (
            len(return_edges) != 1
            or return_edges[0].target_node_id != stage.return_node_id
            or return_edges[0].return_node_id != stage.return_node_id
            or exercise.return_target_id != stage.return_node_id
        ):
            _add(
                issues,
                "TMM-GRAPH-RETURN-MISMATCH",
                f"lasting.stages[{stage.id}]",
                "lasting-skill stage lacks its exact source return",
            )
        if stage.kind is LastingSkillStageKind.RETENTION:
            if stage.schedule_ref is None or stage.transfer_target_ref is not None:
                _add(
                    issues,
                    "TMM-RETENTION-SCHEDULE-INVALID",
                    f"lasting.stages[{stage.id}]",
                    "retention stage lacks its exact schedule",
                )
        elif stage.transfer_target_ref is None or stage.schedule_ref is not None:
            _add(
                issues,
                "TMM-TRANSFER-TARGET-UNRESOLVED",
                f"lasting.stages[{stage.id}]",
                "transfer stage lacks its exact target assignment",
            )
        elif not any(
            edge.kind is CurriculumEdgeKind.SCHEDULE_TRANSFER
            and edge.source_node_id == r1_node_by_requirement.get(stage.source_requirement_ref.id)
            and edge.target_node_id == stage.node_id
            for edge in value.edges
        ):
            _add(
                issues,
                "TMM-TRANSFER-TARGET-UNRESOLVED",
                f"lasting.stages[{stage.id}]",
                "transfer is not gated by the matching passing R1 node",
            )

    for node in value.nodes:
        _stable_id(node.id, f"lasting.nodes[{node.id}].id", issues)
    for edge in value.edges:
        _stable_id(edge.id, f"lasting.edges[{edge.id}].id", issues)
        if edge.source_node_id not in node_by_id or edge.target_node_id not in node_by_id:
            _add(
                issues,
                "TMM-GRAPH-NODE-UNREACHABLE",
                f"lasting.edges[{edge.id}]",
                "edge endpoint is absent",
            )
        source = node_by_id.get(edge.source_node_id)
        if (
            source is not None
            and source.kind in {CurriculumNodeKind.RETENTION, CurriculumNodeKind.TRANSFER}
            and edge.kind
            not in {
                CurriculumEdgeKind.RETURN_TO,
                CurriculumEdgeKind.SCHEDULE_RETENTION,
                CurriculumEdgeKind.SCHEDULE_TRANSFER,
            }
        ):
            _add(
                issues,
                "TMM-EVIDENCE-INCOMPATIBLE",
                f"lasting.edges[{edge.id}]",
                "lasting-skill evidence cannot backfill acquisition or integration",
            )
    _fingerprint(value, "lasting", issues)
    return tuple(issues)


def _validate_retention_schedule(
    schedule: RetentionSchedule,
    issues: list[CurriculumValidationIssue],
) -> None:
    _common(
        schedule.schema_version,
        schedule.id,
        schedule.semantic_fingerprint,
        "retention_schedule",
        issues,
    )
    expected = (
        (RetentionCheckpointKind.R1, RetentionAnchorKind.ACQUISITION, 24, 20, 72),
        (RetentionCheckpointKind.R2, RetentionAnchorKind.PASSING_R1, 168, 120, 240),
    )
    _stable_id(schedule.source_node_id, f"retention_schedule[{schedule.id}].source_node_id", issues)
    _stable_id(schedule.return_node_id, f"retention_schedule[{schedule.id}].return_node_id", issues)
    if (
        schedule.source_requirement_ref.artifact_type != "passage-skill-requirement"
        or schedule.source_scope_ref.artifact_type != "practice-scope-assignment"
    ):
        _add(
            issues,
            "TMM-SCOPE-FOREIGN-REFERENCE",
            f"retention_schedule[{schedule.id}]",
            "schedule references have the wrong artifact types",
        )
    actual = tuple(
        (
            window.checkpoint,
            window.anchor,
            window.due_after_hours,
            window.valid_after_hours,
            window.valid_before_hours,
        )
        for window in schedule.windows
    )
    if actual != expected:
        _add(
            issues,
            "TMM-RETENTION-SCHEDULE-INVALID",
            f"retention_schedule[{schedule.id}].windows",
            "expected exact R1 24h/20-72h and R2 7d/5-10d windows",
        )
    for window in schedule.windows:
        _common(
            window.schema_version,
            window.id,
            window.semantic_fingerprint,
            f"retention_window[{window.id}]",
            issues,
        )
        _rule_reference(window.rule_ref, f"retention_window[{window.id}].rule_ref", issues)
        _fingerprint(window, f"retention_window[{window.id}]", issues)
    _fingerprint(schedule, f"retention_schedule[{schedule.id}]", issues)


def _validate_transfer_assignment(
    assignment: TransferTargetAssignment,
    source_requirement_by_id: dict[str, PassageSkillRequirement],
    source_scope_by_id: dict[str, PracticeScopeAssignment],
    target_requirement_by_id: dict[str, PassageSkillRequirement],
    target_scope_by_id: dict[str, PracticeScopeAssignment],
    issues: list[CurriculumValidationIssue],
) -> None:
    path = f"transfer_target[{assignment.id}]"
    _common(
        assignment.schema_version,
        assignment.id,
        assignment.semantic_fingerprint,
        path,
        issues,
    )
    source = source_requirement_by_id.get(assignment.source_requirement_ref.id)
    target = target_requirement_by_id.get(assignment.target_requirement_ref.id)
    source_scope = source_scope_by_id.get(assignment.source_scope_ref.id)
    target_scope = target_scope_by_id.get(assignment.target_scope_ref.id)
    permitted_differences = {
        "score",
        "passage",
        "material",
        "parameters",
        "notation-condition",
        "register",
        "meter",
        "rhythm",
        "harmony",
        "layer-topology",
    }
    if (
        assignment.source_requirement_ref.artifact_type != "passage-skill-requirement"
        or assignment.target_requirement_ref.artifact_type != "passage-skill-requirement"
        or assignment.source_scope_ref.artifact_type != "practice-scope-assignment"
        or assignment.target_scope_ref.artifact_type != "practice-scope-assignment"
        or assignment.primitive_ref.artifact_type != "learning-primitive"
        or assignment.source_requirement_ref == assignment.target_requirement_ref
        or assignment.source_scope_ref == assignment.target_scope_ref
        or not assignment.difference_dimensions
        or assignment.difference_dimensions != tuple(sorted(set(assignment.difference_dimensions)))
        or not set(assignment.difference_dimensions) <= permitted_differences
        or not assignment.difference_evidence_refs
        or assignment.difference_evidence_refs
        != tuple(sorted(set(assignment.difference_evidence_refs)))
        or assignment.training_state_guard != "previously-untrained-at-attempt-open"
        or assignment.resolution is not ArtifactResolution.RESOLVED
    ):
        _add(
            issues,
            "TMM-TRANSFER-TARGET-UNRESOLVED",
            path,
            "intrinsic source, target, difference, or training-state facts are invalid",
        )
    if source_requirement_by_id and (
        source is None
        or target is None
        or source_scope is None
        or target_scope is None
        or source.primitive_ref != target.primitive_ref
        or assignment.primitive_ref != source.primitive_ref
        or source.practice_scope_ref != assignment.source_scope_ref
        or target.practice_scope_ref != assignment.target_scope_ref
    ):
        _add(
            issues,
            "TMM-TRANSFER-TARGET-UNRESOLVED",
            path,
            "source, target, scope, or shared primitive is absent or mismatched",
        )
    if source_scope is not None and target_scope is not None:
        materially_different = (
            source_scope.id != target_scope.id
            and source_scope.active_target_ids != target_scope.active_target_ids
            and (
                source_scope.score_package_digest != target_scope.score_package_digest
                or source_scope.score_range != target_scope.score_range
                or (
                    source is not None
                    and target is not None
                    and source.target_parameters != target.target_parameters
                )
                or (
                    source is not None
                    and target is not None
                    and source.canonical_evidence_refs != target.canonical_evidence_refs
                )
            )
        )
        known_evidence = set(target.canonical_evidence_refs if target is not None else ())
        known_evidence.update(target.analysis_evidence_refs if target is not None else ())
        known_evidence.update(target_scope.active_target_ids)
        if (
            not materially_different
            or not set(assignment.difference_evidence_refs) <= known_evidence
        ):
            _add(
                issues,
                "TMM-TRANSFER-TARGET-UNRESOLVED",
                path,
                "target difference or previously-untrained guard is unresolved",
            )
    _rule_reference(assignment.similarity_rule, f"{path}.similarity_rule", issues)
    _fingerprint(assignment, path, issues)


def require_valid_practice_scope(value: PracticeScopeAssignment) -> None:
    """Raise when one practice scope is invalid."""

    if issues := validate_practice_scope(value):
        raise CurriculumValidationError(issues)


def validate_curriculum_evidence_record(
    value: CurriculumEvidenceRecord,
) -> tuple[CurriculumValidationIssue, ...]:
    """Validate one factual DEV-009 record without inferring mastery."""

    issues: list[CurriculumValidationIssue] = []
    _common(value.schema_version, value.id, value.semantic_fingerprint, "evidence", issues)
    _stable_id(value.attempt_id, "evidence.attempt_id", issues)
    _semantic_reference(
        value.expected_target_ref,
        "expected-layer-target",
        "evidence.expected_target_ref",
        issues,
    )
    _semantic_reference(
        value.requirement_ref,
        "passage-skill-requirement",
        "evidence.requirement_ref",
        issues,
    )
    _semantic_reference(
        value.primitive_ref,
        "learning-primitive",
        "evidence.primitive_ref",
        issues,
    )
    _semantic_reference(
        value.practice_scope_ref,
        "practice-scope-assignment",
        "evidence.practice_scope_ref",
        issues,
    )
    _semantic_reference(
        value.support_state_ref,
        "support-state",
        "evidence.support_state_ref",
        issues,
    )
    component_ids: list[str] = []
    for index, reference in enumerate(value.component_scope_refs):
        _semantic_reference(
            reference,
            "practice-scope-assignment",
            f"evidence.component_scope_refs[{index}]",
            issues,
        )
        component_ids.append(reference.id)
    if len(component_ids) != len(set(component_ids)):
        _add(
            issues,
            "TMM-CONTRACT-DUPLICATE-ID",
            "evidence.component_scope_refs",
            "component scope repeats",
        )
    if value.notation_condition.value == "combined":
        if len(value.component_scope_refs) < 2:
            _add(
                issues,
                "TMM-EVIDENCE-COMPONENT-MISMATCH",
                "evidence.component_scope_refs",
                "combined evidence requires component identities",
            )
    elif value.component_scope_refs:
        _add(
            issues,
            "TMM-EVIDENCE-COMPONENT-MISMATCH",
            "evidence.component_scope_refs",
            "isolated evidence cannot carry combined components",
        )
    if not isinstance(value.dimension, ObservationDimension):
        _add(
            issues,
            "TMM-CONTRACT-INVALID-EXACT-VALUE",
            "evidence.dimension",
            "unknown observation dimension",
        )
    if not isinstance(value.evidence_context, EvidenceContext):
        _add(
            issues,
            "TMM-CONTRACT-INVALID-EXACT-VALUE",
            "evidence.evidence_context",
            "unknown evidence context",
        )
    if not isinstance(value.result, CurriculumEvidenceResult):
        _add(
            issues,
            "TMM-CONTRACT-INVALID-EXACT-VALUE",
            "evidence.result",
            "unknown factual result",
        )
    _unique_ids(value.observation_ids, "evidence.observation_ids", issues)
    _unique_ids(value.context_observation_ids, "evidence.context_observation_ids", issues)
    if not value.observation_ids:
        _add(
            issues,
            "TMM-EVIDENCE-OBSERVATION-MISSING",
            "evidence.observation_ids",
            "a factual result requires observations",
        )
    if set(value.observation_ids) & set(value.context_observation_ids):
        _add(
            issues,
            "TMM-EVIDENCE-OBSERVATION-OVERLAP",
            "evidence.context_observation_ids",
            "context observations cannot replace scoring observations",
        )
    if any(not item.strip() for item in value.limitations):
        _add(
            issues,
            "TMM-CONTRACT-INVALID-EXACT-VALUE",
            "evidence.limitations",
            "limitations must be non-empty strings",
        )
    if value.result is CurriculumEvidenceResult.INCONCLUSIVE and not value.limitations:
        _add(
            issues,
            "TMM-EVIDENCE-LIMITATION-MISSING",
            "evidence.limitations",
            "inconclusive evidence must explain its boundary",
        )
    if value.resolution is not ArtifactResolution.RESOLVED:
        _add(
            issues,
            "TMM-EVIDENCE-UNRESOLVED",
            "evidence.resolution",
            "a persisted result must be structurally resolved",
        )
    _fingerprint(value, "evidence", issues)
    return tuple(issues)


def require_valid_curriculum_evidence_record(value: CurriculumEvidenceRecord) -> None:
    """Raise when one support-bound evidence record is invalid."""

    if issues := validate_curriculum_evidence_record(value):
        raise CurriculumValidationError(issues)


def validate_curriculum_mastery_projection(
    value: CurriculumMasteryProjection,
) -> tuple[CurriculumValidationIssue, ...]:
    """Validate one exact, dimension-preserving node mastery projection."""

    issues: list[CurriculumValidationIssue] = []
    _common(value.schema_version, value.id, value.semantic_fingerprint, "mastery", issues)
    if value.graph_ref.artifact_type not in {
        "acquisition-graph-slice",
        "lasting-skill-graph-slice",
    }:
        _add(
            issues,
            "TMM-SCOPE-FOREIGN-REFERENCE",
            "mastery.graph_ref",
            "reference is not a supported curriculum graph",
        )
    for reference, artifact_type, path in (
        (value.exercise_ref, "exercise-instance", "mastery.exercise_ref"),
        (
            value.requirement_ref,
            "passage-skill-requirement",
            "mastery.requirement_ref",
        ),
        (value.primitive_ref, "learning-primitive", "mastery.primitive_ref"),
        (
            value.practice_scope_ref,
            "practice-scope-assignment",
            "mastery.practice_scope_ref",
        ),
        (value.support_state_ref, "support-state", "mastery.support_state_ref"),
    ):
        _semantic_reference(reference, artifact_type, path, issues)
    for index, reference in enumerate(value.component_scope_refs):
        _semantic_reference(
            reference,
            "practice-scope-assignment",
            f"mastery.component_scope_refs[{index}]",
            issues,
        )
    _stable_id(value.node_id, "mastery.node_id", issues)
    if len(value.required_dimensions) != len(set(value.required_dimensions)):
        _add(
            issues,
            "TMM-CONTRACT-DUPLICATE-ID",
            "mastery.required_dimensions",
            "required dimension repeats",
        )
    if not value.required_dimensions:
        _add(
            issues,
            "TMM-POLICY-DIMENSION-MISSING",
            "mastery.required_dimensions",
            "mastery projection requires dimension-specific exits",
        )
    if tuple(item.dimension for item in value.dimension_decisions) != (value.required_dimensions):
        _add(
            issues,
            "TMM-POLICY-DIMENSION-MISMATCH",
            "mastery.dimension_decisions",
            "dimension decisions must exactly match required dimensions in order",
        )
    for index, decision in enumerate(value.dimension_decisions):
        path = f"mastery.dimension_decisions[{index}]"
        _unique_ids(decision.evidence_record_ids, f"{path}.evidence_record_ids", issues)
        _unique_ids(decision.passing_attempt_ids, f"{path}.passing_attempt_ids", issues)
        if not decision.reason_code:
            _add(
                issues,
                "TMM-CONTRACT-INVALID-EXACT-VALUE",
                f"{path}.reason_code",
                "dimension decision requires a stable reason",
            )
    _unique_ids(value.evaluated_attempt_ids, "mastery.evaluated_attempt_ids", issues)
    _unique_ids(
        value.complete_passing_attempt_ids,
        "mastery.complete_passing_attempt_ids",
        issues,
    )
    if not set(value.complete_passing_attempt_ids) <= set(value.evaluated_attempt_ids):
        _add(
            issues,
            "TMM-POLICY-ATTEMPT-SEQUENCE-INCOMPATIBLE",
            "mastery.complete_passing_attempt_ids",
            "passing attempts must belong to the evaluated sequence",
        )
    if value.minimum_state == "stable-supported":
        required_passes = 2
    elif value.minimum_state in {
        "diagnostic-observed",
        "independent-in-session",
        "supported",
    }:
        required_passes = 1
    else:
        required_passes = 0
        _add(
            issues,
            "TMM-POLICY-MINIMUM-STATE-UNSUPPORTED",
            "mastery.minimum_state",
            "unknown minimum evidence state",
        )
    stable_tail = value.evaluated_attempt_ids[-required_passes:]
    supports_mastery = len(stable_tail) >= required_passes and all(
        item in value.complete_passing_attempt_ids for item in stable_tail
    )
    has_discrepancy = any(
        item.result is CurriculumEvidenceResult.DISCREPANCY for item in value.dimension_decisions
    )
    if value.status is CurriculumMasteryStatus.MASTERED and not supports_mastery:
        _add(
            issues,
            "TMM-POLICY-MASTERY-UNSUPPORTED",
            "mastery.status",
            "mastery lacks the required complete passing attempts",
        )
    elif value.status is CurriculumMasteryStatus.NOT_MASTERED and not has_discrepancy:
        _add(
            issues,
            "TMM-POLICY-MASTERY-UNSUPPORTED",
            "mastery.status",
            "not-mastered requires a dimension discrepancy",
        )
    elif value.status is CurriculumMasteryStatus.INCONCLUSIVE and (
        supports_mastery or has_discrepancy
    ):
        _add(
            issues,
            "TMM-POLICY-MASTERY-UNSUPPORTED",
            "mastery.status",
            "inconclusive cannot conceal complete mastery or a discrepancy",
        )
    if value.resolution is not ArtifactResolution.RESOLVED:
        _add(
            issues,
            "TMM-POLICY-DECISION-UNRESOLVED",
            "mastery.resolution",
            "persisted mastery projection must be resolved",
        )
    _fingerprint(value, "mastery", issues)
    return tuple(issues)


def require_valid_curriculum_mastery_projection(
    value: CurriculumMasteryProjection,
) -> None:
    """Raise when one node-local mastery projection is invalid."""

    if issues := validate_curriculum_mastery_projection(value):
        raise CurriculumValidationError(issues)


def validate_curriculum_unlock_decision(
    value: CurriculumUnlockDecision,
    projection: CurriculumMasteryProjection | None = None,
    graph: AcquisitionGraphSlice | LastingSkillGraphSlice | None = None,
) -> tuple[CurriculumValidationIssue, ...]:
    """Validate one exact deterministic graph-unlock result."""

    issues: list[CurriculumValidationIssue] = []
    _common(value.schema_version, value.id, value.semantic_fingerprint, "unlock", issues)
    if value.policy_identity != TEMPO_POLICY_ID:
        _add(
            issues,
            "TMM-CONTRACT-UNKNOWN-VERSION",
            "unlock.policy_identity",
            "unknown deterministic policy identity",
        )
    if value.graph_ref.artifact_type not in {
        "acquisition-graph-slice",
        "lasting-skill-graph-slice",
    }:
        _add(
            issues,
            "TMM-SCOPE-FOREIGN-REFERENCE",
            "unlock.graph_ref",
            "reference is not a supported curriculum graph",
        )
    _semantic_reference(
        value.projection_ref,
        "curriculum-mastery-projection",
        "unlock.projection_ref",
        issues,
    )
    _stable_id(value.current_node_id, "unlock.current_node_id", issues)
    _unique_ids(
        value.previously_satisfied_node_ids,
        "unlock.previously_satisfied_node_ids",
        issues,
    )
    _unique_ids(value.eligible_edge_ids, "unlock.eligible_edge_ids", issues)
    rejected_ids = tuple(item.edge_id for item in value.rejected_edges)
    _unique_ids(rejected_ids, "unlock.rejected_edges", issues)
    selected_pair = (value.selected_edge_id, value.next_node_id)
    if (selected_pair[0] is None) != (selected_pair[1] is None):
        _add(
            issues,
            "TMM-POLICY-EDGE-SELECTION",
            "unlock.selected_edge_id",
            "selected edge and next node must appear together",
        )
    if value.action is CurriculumUnlockAction.UNLOCK_SUCCESSOR:
        if value.selected_edge_id not in value.eligible_edge_ids or value.next_node_id is None:
            _add(
                issues,
                "TMM-POLICY-EDGE-SELECTION",
                "unlock.action",
                "unlock action requires one eligible selected edge and target",
            )
    elif value.selected_edge_id is not None or value.next_node_id is not None:
        _add(
            issues,
            "TMM-POLICY-EDGE-SELECTION",
            "unlock.action",
            "non-unlock action cannot select a graph successor",
        )
    if not value.reason_code:
        _add(
            issues,
            "TMM-CONTRACT-INVALID-EXACT-VALUE",
            "unlock.reason_code",
            "unlock decision requires a stable reason",
        )
    if value.resolution is not ArtifactResolution.RESOLVED:
        _add(
            issues,
            "TMM-POLICY-DECISION-UNRESOLVED",
            "unlock.resolution",
            "persisted unlock decision must be resolved",
        )
    if projection is not None:
        expected_ref = SemanticReference(
            "curriculum-mastery-projection",
            projection.id,
            projection.semantic_fingerprint,
        )
        if value.projection_ref != expected_ref or value.current_node_id != projection.node_id:
            _add(
                issues,
                "TMM-POLICY-PROJECTION-MISMATCH",
                "unlock.projection_ref",
                "decision does not belong to the supplied mastery projection",
            )
    if graph is not None:
        expected_graph_ref = SemanticReference(
            "acquisition-graph-slice"
            if isinstance(graph, AcquisitionGraphSlice)
            else "lasting-skill-graph-slice",
            graph.id,
            graph.semantic_fingerprint,
        )
        edge_by_id = {item.id: item for item in graph.edges}
        if value.graph_ref != expected_graph_ref:
            _add(
                issues,
                "TMM-POLICY-GRAPH-MISMATCH",
                "unlock.graph_ref",
                "decision does not belong to the supplied graph",
            )
        if value.selected_edge_id is not None:
            edge = edge_by_id.get(value.selected_edge_id)
            if (
                edge is None
                or edge.source_node_id != value.current_node_id
                or edge.target_node_id != value.next_node_id
            ):
                _add(
                    issues,
                    "TMM-POLICY-EDGE-SELECTION",
                    "unlock.selected_edge_id",
                    "selected edge is absent or does not connect the declared nodes",
                )
    _fingerprint(value, "unlock", issues)
    return tuple(issues)


def require_valid_curriculum_unlock_decision(
    value: CurriculumUnlockDecision,
    projection: CurriculumMasteryProjection | None = None,
    graph: AcquisitionGraphSlice | LastingSkillGraphSlice | None = None,
) -> None:
    """Raise when one deterministic unlock decision is invalid."""

    if issues := validate_curriculum_unlock_decision(value, projection, graph):
        raise CurriculumValidationError(issues)


def validate_curriculum_decision_snapshot(
    value: CurriculumDecisionSnapshot,
) -> tuple[CurriculumValidationIssue, ...]:
    """Validate the immutable knowledge available before one policy decision."""

    issues: list[CurriculumValidationIssue] = []
    _common(value.schema_version, value.id, value.semantic_fingerprint, "snapshot", issues)
    if value.snapshot_version != DECISION_SNAPSHOT_VERSION:
        _add(
            issues,
            "TMM-CONTRACT-UNKNOWN-VERSION",
            "snapshot.snapshot_version",
            "unknown decision-snapshot version",
        )
    for identifier, path in (
        (value.run_id, "snapshot.run_id"),
        (value.learner_context_id, "snapshot.learner_context_id"),
        (value.score_id, "snapshot.score_id"),
        (value.current_node_id, "snapshot.current_node_id"),
    ):
        _stable_id(identifier, path, issues)
    if value.decision_sequence < 1 or value.evidence_snapshot_sequence < 0:
        _add(
            issues,
            "TMM-CONTRACT-INVALID-EXACT-VALUE",
            "snapshot.decision_sequence",
            "decision sequences start at one and evidence sequences are non-negative",
        )
    if _SHA256.fullmatch(value.score_package_digest) is None:
        _add(
            issues,
            "TMM-CONTRACT-INVALID-EXACT-VALUE",
            "snapshot.score_package_digest",
            "expected SHA-256",
        )
    if value.graph_ref.artifact_type not in {
        "acquisition-graph-slice",
        "lasting-skill-graph-slice",
    }:
        _add(
            issues,
            "TMM-SCOPE-FOREIGN-REFERENCE",
            "snapshot.graph_ref",
            "reference is not a supported curriculum graph",
        )
    for reference, artifact_type, path in (
        (value.exercise_ref, "exercise-instance", "snapshot.exercise_ref"),
        (
            value.requirement_ref,
            "passage-skill-requirement",
            "snapshot.requirement_ref",
        ),
        (value.primitive_ref, "learning-primitive", "snapshot.primitive_ref"),
        (
            value.practice_scope_ref,
            "practice-scope-assignment",
            "snapshot.practice_scope_ref",
        ),
        (value.support_state_ref, "support-state", "snapshot.support_state_ref"),
        (
            value.policy_configuration_ref,
            "deterministic-policy-config",
            "snapshot.policy_configuration_ref",
        ),
        (
            value.mastery_projection_ref,
            "curriculum-mastery-projection",
            "snapshot.mastery_projection_ref",
        ),
    ):
        _semantic_reference(reference, artifact_type, path, issues)
    for index, reference in enumerate(value.component_scope_refs):
        _semantic_reference(
            reference,
            "practice-scope-assignment",
            f"snapshot.component_scope_refs[{index}]",
            issues,
        )
    for references, artifact_type, path in (
        (
            value.evidence_record_refs,
            "curriculum-evidence-record",
            "snapshot.evidence_record_refs",
        ),
        (
            value.observation_refs,
            "performance-observation",
            "snapshot.observation_refs",
        ),
    ):
        reference_ids: list[str] = []
        for index, reference in enumerate(references):
            _semantic_reference(reference, artifact_type, f"{path}[{index}]", issues)
            reference_ids.append(reference.id)
        _unique_ids(tuple(reference_ids), path, issues)
    _unique_ids(value.attempt_sequence, "snapshot.attempt_sequence", issues)
    _unique_ids(
        value.previously_satisfied_node_ids,
        "snapshot.previously_satisfied_node_ids",
        issues,
    )
    budget_keys = tuple(item.key for item in value.budget_state)
    _unique_ids(budget_keys, "snapshot.budget_state", issues)
    for index, item in enumerate(value.budget_state):
        if not item.key.strip() or item.used < 0 or item.limit < 0 or item.used > item.limit:
            _add(
                issues,
                "TMM-POLICY-BUDGET-EXHAUSTED",
                f"snapshot.budget_state[{index}]",
                "budget counters require a stable key and 0 <= used <= limit",
            )
    if value.policy_identity != TEMPO_POLICY_ID:
        _add(
            issues,
            "TMM-CONTRACT-UNKNOWN-VERSION",
            "snapshot.policy_identity",
            "unknown deterministic policy identity",
        )
    for actual, expected, path in (
        (
            value.curriculum_contract_version,
            CURRICULUM_CONTRACT_VERSION,
            "snapshot.curriculum_contract_version",
        ),
        (
            value.performance_contract_version,
            PERFORMANCE_CONTRACT_VERSION,
            "snapshot.performance_contract_version",
        ),
        (
            value.evidence_archive_contract_version,
            EVIDENCE_ARCHIVE_CONTRACT_VERSION,
            "snapshot.evidence_archive_contract_version",
        ),
    ):
        if actual != expected:
            _add(
                issues,
                "TMM-CONTRACT-UNKNOWN-VERSION",
                path,
                "governing contract version differs from the implemented boundary",
            )
    expected_evidence_fingerprint = semantic_fingerprint(
        (
            value.evidence_snapshot_sequence,
            value.evidence_record_refs,
            value.observation_refs,
            value.attempt_sequence,
        )
    )
    if value.evidence_snapshot_fingerprint != expected_evidence_fingerprint:
        _add(
            issues,
            "TMM-POLICY-SNAPSHOT-MISMATCH",
            "snapshot.evidence_snapshot_fingerprint",
            "evidence and observation identities do not match the snapshot digest",
        )
    if value.resolution is not ArtifactResolution.RESOLVED:
        _add(
            issues,
            "TMM-POLICY-DECISION-UNRESOLVED",
            "snapshot.resolution",
            "a persisted pre-decision snapshot must be resolved",
        )
    _fingerprint(value, "snapshot", issues)
    return tuple(issues)


def require_valid_curriculum_decision_snapshot(
    value: CurriculumDecisionSnapshot,
) -> None:
    """Raise when a pre-decision state/observation snapshot is invalid."""

    if issues := validate_curriculum_decision_snapshot(value):
        raise CurriculumValidationError(issues)


def validate_curriculum_action_inventory(
    value: CurriculumActionInventory,
    snapshot: CurriculumDecisionSnapshot | None = None,
    graph: AcquisitionGraphSlice | None = None,
    mastery: CurriculumMasteryProjection | None = None,
) -> tuple[CurriculumValidationIssue, ...]:
    """Validate the complete pre-selection action inventory for one snapshot."""

    issues: list[CurriculumValidationIssue] = []
    _common(value.schema_version, value.id, value.semantic_fingerprint, "inventory", issues)
    if value.inventory_version != ACTION_INVENTORY_VERSION:
        _add(
            issues,
            "TMM-CONTRACT-UNKNOWN-VERSION",
            "inventory.inventory_version",
            "unknown action-inventory version",
        )
    _semantic_reference(
        value.snapshot_ref,
        "curriculum-decision-snapshot",
        "inventory.snapshot_ref",
        issues,
    )
    _semantic_reference(
        value.graph_ref,
        "acquisition-graph-slice",
        "inventory.graph_ref",
        issues,
    )
    _semantic_reference(
        value.mastery_projection_ref,
        "curriculum-mastery-projection",
        "inventory.mastery_projection_ref",
        issues,
    )
    _semantic_reference(
        value.policy_configuration_ref,
        "deterministic-policy-config",
        "inventory.policy_configuration_ref",
        issues,
    )
    _stable_id(value.current_node_id, "inventory.current_node_id", issues)
    if value.policy_identity != TEMPO_POLICY_ID:
        _add(
            issues,
            "TMM-CONTRACT-UNKNOWN-VERSION",
            "inventory.policy_identity",
            "unknown deterministic policy identity",
        )
    candidate_edge_ids = tuple(item.edge_id for item in value.candidates)
    _unique_ids(candidate_edge_ids, "inventory.candidates", issues)
    for index, candidate in enumerate(value.candidates):
        path = f"inventory.candidates[{index}]"
        _stable_id(candidate.edge_id, f"{path}.edge_id", issues)
        _stable_id(candidate.target_node_id, f"{path}.target_node_id", issues)
        if candidate.precedence < 0:
            _add(
                issues,
                "TMM-CONTRACT-INVALID-EXACT-VALUE",
                f"{path}.precedence",
                "action precedence must be non-negative",
            )
        guards = candidate.guard_results
        if not guards:
            _add(
                issues,
                "TMM-POLICY-GUARD-INCOMPLETE",
                f"{path}.guard_results",
                "action candidates require explicit guard results",
            )
        guard_names = tuple(item.guard for item in guards)
        if len(guard_names) != len(set(guard_names)):
            _add(
                issues,
                "TMM-CONTRACT-DUPLICATE-ID",
                f"{path}.guard_results",
                "guard name repeats",
            )
        if any(not item.guard.strip() or not item.reason_code.strip() for item in guards):
            _add(
                issues,
                "TMM-CONTRACT-INVALID-EXACT-VALUE",
                f"{path}.guard_results",
                "guard names and reason codes must be non-empty",
            )
        all_passed = bool(guards) and all(item.passed for item in guards)
        expected_eligibility = (
            CurriculumActionEligibility.ALLOWED
            if all_passed
            else CurriculumActionEligibility.EXCLUDED
        )
        if candidate.eligibility is not expected_eligibility:
            _add(
                issues,
                "TMM-POLICY-GUARD-MISMATCH",
                f"{path}.eligibility",
                "candidate eligibility does not match its complete guard results",
            )
        failed = next((item for item in guards if not item.passed), None)
        expected_reason = "TMM-POLICY-ACTION-ALLOWED" if failed is None else failed.reason_code
        if candidate.reason_code != expected_reason:
            _add(
                issues,
                "TMM-POLICY-GUARD-MISMATCH",
                f"{path}.reason_code",
                "candidate reason does not identify the first failed guard",
            )
        expected_ties = (
            f"graph-precedence={candidate.precedence}",
            next(
                (item for item in candidate.tie_break_values if item.startswith("edge-kind=")),
                "",
            ),
            f"edge-id={candidate.edge_id}",
        )
        if candidate.tie_break_values != expected_ties or not expected_ties[1]:
            _add(
                issues,
                "TMM-POLICY-TIE-UNRESOLVED",
                f"{path}.tie_break_values",
                "tie-break values must preserve precedence, edge kind, and edge identity",
            )
    if value.resolution is not ArtifactResolution.RESOLVED:
        _add(
            issues,
            "TMM-POLICY-DECISION-UNRESOLVED",
            "inventory.resolution",
            "a persisted action inventory must be resolved",
        )

    if snapshot is not None:
        expected_snapshot_ref = SemanticReference(
            "curriculum-decision-snapshot",
            snapshot.id,
            snapshot.semantic_fingerprint,
        )
        if (
            value.snapshot_ref != expected_snapshot_ref
            or value.graph_ref != snapshot.graph_ref
            or value.current_node_id != snapshot.current_node_id
            or value.mastery_projection_ref != snapshot.mastery_projection_ref
            or value.policy_identity != snapshot.policy_identity
            or value.policy_configuration_ref != snapshot.policy_configuration_ref
        ):
            _add(
                issues,
                "TMM-POLICY-SNAPSHOT-MISMATCH",
                "inventory.snapshot_ref",
                "inventory does not belong to the supplied pre-decision snapshot",
            )
    if mastery is not None:
        expected_mastery_ref = SemanticReference(
            "curriculum-mastery-projection",
            mastery.id,
            mastery.semantic_fingerprint,
        )
        if (
            value.mastery_projection_ref != expected_mastery_ref
            or value.current_node_id != mastery.node_id
        ):
            _add(
                issues,
                "TMM-POLICY-SNAPSHOT-MISMATCH",
                "inventory.mastery_projection_ref",
                "inventory does not belong to the supplied mastery projection",
            )
    if graph is not None:
        graph_ref = SemanticReference(
            "acquisition-graph-slice",
            graph.id,
            graph.semantic_fingerprint,
        )
        actionable_kinds = {
            CurriculumEdgeKind.ON_SATISFIED,
            CurriculumEdgeKind.CHECKPOINT_AFTER,
            CurriculumEdgeKind.RETURN_TO,
        }
        expected_edges = tuple(
            sorted(
                (
                    item
                    for item in graph.edges
                    if item.source_node_id == value.current_node_id
                    and item.kind in actionable_kinds
                ),
                key=lambda item: (item.precedence, item.kind.value, item.id),
            )
        )
        if value.graph_ref != graph_ref or candidate_edge_ids != tuple(
            item.id for item in expected_edges
        ):
            _add(
                issues,
                "TMM-POLICY-ACTION-INVENTORY-INCOMPLETE",
                "inventory.candidates",
                "inventory does not exactly cover the graph-declared runtime edges",
            )
        for candidate, edge in zip(value.candidates, expected_edges, strict=False):
            expected_ties = (
                f"graph-precedence={edge.precedence}",
                f"edge-kind={edge.kind.value}",
                f"edge-id={edge.id}",
            )
            if (
                candidate.target_node_id != edge.target_node_id
                or candidate.precedence != edge.precedence
                or candidate.tie_break_values != expected_ties
                or not candidate.guard_results
                or candidate.guard_results[0].guard != edge.guard
            ):
                _add(
                    issues,
                    "TMM-POLICY-GUARD-MISMATCH",
                    "inventory.candidates",
                    "candidate edge, guard, precedence, or tie-break data has drifted",
                )
                break
    _fingerprint(value, "inventory", issues)
    return tuple(issues)


def _action_candidate_selection_key(
    candidate: CurriculumActionCandidate,
) -> tuple[int, str, str]:
    """Return the frozen graph-precedence, edge-kind, edge-ID ordering."""

    edge_kind = next(
        (
            value.removeprefix("edge-kind=")
            for value in candidate.tie_break_values
            if value.startswith("edge-kind=")
        ),
        "",
    )
    return candidate.precedence, edge_kind, candidate.edge_id


def require_valid_curriculum_action_inventory(
    value: CurriculumActionInventory,
    snapshot: CurriculumDecisionSnapshot | None = None,
    graph: AcquisitionGraphSlice | None = None,
    mastery: CurriculumMasteryProjection | None = None,
) -> None:
    """Raise when a pre-selection action inventory is invalid."""

    if issues := validate_curriculum_action_inventory(value, snapshot, graph, mastery):
        raise CurriculumValidationError(issues)


def validate_curriculum_action_selection(
    value: CurriculumActionSelection,
    inventory: CurriculumActionInventory | None = None,
    snapshot: CurriculumDecisionSnapshot | None = None,
) -> tuple[CurriculumValidationIssue, ...]:
    """Validate one deterministic selection from an exact action inventory."""

    issues: list[CurriculumValidationIssue] = []
    _common(value.schema_version, value.id, value.semantic_fingerprint, "selection", issues)
    if value.selection_version != ACTION_SELECTION_VERSION:
        _add(
            issues,
            "TMM-CONTRACT-UNKNOWN-VERSION",
            "selection.selection_version",
            "unknown action-selection version",
        )
    _semantic_reference(
        value.snapshot_ref,
        "curriculum-decision-snapshot",
        "selection.snapshot_ref",
        issues,
    )
    _semantic_reference(
        value.inventory_ref,
        "curriculum-action-inventory",
        "selection.inventory_ref",
        issues,
    )
    _semantic_reference(
        value.policy_configuration_ref,
        "deterministic-policy-config",
        "selection.policy_configuration_ref",
        issues,
    )
    if value.policy_identity != TEMPO_POLICY_ID:
        _add(
            issues,
            "TMM-CONTRACT-UNKNOWN-VERSION",
            "selection.policy_identity",
            "unknown deterministic policy identity",
        )
    selected = value.selected_candidate
    _stable_id(selected.edge_id, "selection.selected_candidate.edge_id", issues)
    _stable_id(
        selected.target_node_id,
        "selection.selected_candidate.target_node_id",
        issues,
    )
    if selected.precedence < 0:
        _add(
            issues,
            "TMM-CONTRACT-INVALID-EXACT-VALUE",
            "selection.selected_candidate.precedence",
            "selected action precedence must be non-negative",
        )
    guard_names = tuple(item.guard for item in selected.guard_results)
    if not selected.guard_results or len(guard_names) != len(set(guard_names)):
        _add(
            issues,
            "TMM-POLICY-GUARD-INCOMPLETE",
            "selection.selected_candidate.guard_results",
            "the selected candidate requires unique complete guard results",
        )
    if any(
        not item.guard.strip() or not item.reason_code.strip() for item in selected.guard_results
    ):
        _add(
            issues,
            "TMM-CONTRACT-INVALID-EXACT-VALUE",
            "selection.selected_candidate.guard_results",
            "selected guard names and reason codes must be non-empty",
        )
    if selected.eligibility is not CurriculumActionEligibility.ALLOWED or not all(
        item.passed for item in selected.guard_results
    ):
        _add(
            issues,
            "TMM-POLICY-ACTION-NOT-ALLOWED",
            "selection.selected_candidate",
            "the selected candidate must be allowed with every guard satisfied",
        )
    expected_ties = (
        f"graph-precedence={selected.precedence}",
        next(
            (item for item in selected.tie_break_values if item.startswith("edge-kind=")),
            "",
        ),
        f"edge-id={selected.edge_id}",
    )
    if selected.tie_break_values != expected_ties or not expected_ties[1]:
        _add(
            issues,
            "TMM-POLICY-TIE-UNRESOLVED",
            "selection.selected_candidate.tie_break_values",
            "selected tie-break values must preserve precedence, edge kind, and edge identity",
        )
    if selected.reason_code != "TMM-POLICY-ACTION-ALLOWED":
        _add(
            issues,
            "TMM-POLICY-GUARD-MISMATCH",
            "selection.selected_candidate.reason_code",
            "the selected candidate must retain its allowed reason",
        )
    if value.behavior_probability != Fraction(1):
        _add(
            issues,
            "TMM-POLICY-PROBABILITY-MISMATCH",
            "selection.behavior_probability",
            "the frozen deterministic policy must record exact probability 1",
        )
    if value.reason_code != "TMM-POLICY-DETERMINISTIC-FIRST-ALLOWED":
        _add(
            issues,
            "TMM-POLICY-SELECTION-MISMATCH",
            "selection.reason_code",
            "selection reason does not identify the frozen deterministic rule",
        )
    if value.resolution is not ArtifactResolution.RESOLVED:
        _add(
            issues,
            "TMM-POLICY-DECISION-UNRESOLVED",
            "selection.resolution",
            "a persisted action selection must be resolved",
        )

    if inventory is not None:
        expected_inventory_ref = SemanticReference(
            "curriculum-action-inventory",
            inventory.id,
            inventory.semantic_fingerprint,
        )
        allowed = tuple(
            candidate
            for candidate in inventory.candidates
            if candidate.eligibility is CurriculumActionEligibility.ALLOWED
        )
        expected = min(allowed, key=_action_candidate_selection_key) if allowed else None
        if (
            value.inventory_ref != expected_inventory_ref
            or value.snapshot_ref != inventory.snapshot_ref
            or value.policy_identity != inventory.policy_identity
            or value.policy_configuration_ref != inventory.policy_configuration_ref
        ):
            _add(
                issues,
                "TMM-POLICY-SNAPSHOT-MISMATCH",
                "selection.inventory_ref",
                "selection does not belong to the supplied action inventory",
            )
        if expected is None:
            _add(
                issues,
                "TMM-POLICY-NO-ALLOWED-ACTION",
                "selection.selected_candidate",
                "the supplied inventory contains no allowed candidate",
            )
        elif value.selected_candidate != expected:
            _add(
                issues,
                "TMM-POLICY-SELECTION-MISMATCH",
                "selection.selected_candidate",
                "selected candidate is not first under frozen precedence and tie-breaks",
            )
    if snapshot is not None:
        expected_snapshot_ref = SemanticReference(
            "curriculum-decision-snapshot",
            snapshot.id,
            snapshot.semantic_fingerprint,
        )
        if (
            value.snapshot_ref != expected_snapshot_ref
            or value.policy_identity != snapshot.policy_identity
            or value.policy_configuration_ref != snapshot.policy_configuration_ref
        ):
            _add(
                issues,
                "TMM-POLICY-SNAPSHOT-MISMATCH",
                "selection.snapshot_ref",
                "selection does not belong to the supplied pre-decision snapshot",
            )
    _fingerprint(value, "selection", issues)
    return tuple(issues)


def validate_curriculum_transition_result(
    value: CurriculumTransitionResult,
    selection: CurriculumActionSelection | None = None,
    prior_snapshot: CurriculumDecisionSnapshot | None = None,
    outcome: CurriculumLearningOutcome | None = None,
    reward: CurriculumResearchReward | None = None,
    next_snapshot: CurriculumDecisionSnapshot | None = None,
) -> tuple[CurriculumValidationIssue, ...]:
    """Validate one selected action's factual result and exact next state."""

    issues: list[CurriculumValidationIssue] = []
    _common(value.schema_version, value.id, value.semantic_fingerprint, "transition", issues)
    if value.transition_version != TRANSITION_RESULT_VERSION:
        _add(
            issues,
            "TMM-CONTRACT-UNKNOWN-VERSION",
            "transition.transition_version",
            "unknown transition-result version",
        )
    for reference, artifact_type, name in (
        (value.selection_ref, "curriculum-action-selection", "selection_ref"),
        (value.outcome_ref, "curriculum-learning-outcome", "outcome_ref"),
        (value.research_reward_ref, "curriculum-research-reward", "research_reward_ref"),
        (value.next_snapshot_ref, "curriculum-decision-snapshot", "next_snapshot_ref"),
    ):
        _semantic_reference(reference, artifact_type, f"transition.{name}", issues)
    if value.resolution is not ArtifactResolution.RESOLVED:
        _add(
            issues,
            "TMM-POLICY-TRANSITION-UNRESOLVED",
            "transition.resolution",
            "a persisted transition result must be resolved",
        )

    if selection is not None and value.selection_ref != SemanticReference(
        "curriculum-action-selection",
        selection.id,
        selection.semantic_fingerprint,
    ):
        _add(
            issues,
            "TMM-POLICY-TRANSITION-MISMATCH",
            "transition.selection_ref",
            "transition does not identify the supplied action selection",
        )
    if outcome is not None and value.outcome_ref != SemanticReference(
        "curriculum-learning-outcome",
        outcome.id,
        outcome.semantic_fingerprint,
    ):
        _add(
            issues,
            "TMM-POLICY-TRANSITION-MISMATCH",
            "transition.outcome_ref",
            "transition does not identify the supplied factual outcome",
        )
    if reward is not None and value.research_reward_ref != SemanticReference(
        "curriculum-research-reward",
        reward.id,
        reward.semantic_fingerprint,
    ):
        _add(
            issues,
            "TMM-POLICY-TRANSITION-MISMATCH",
            "transition.research_reward_ref",
            "transition does not identify the supplied research reward",
        )
    if next_snapshot is not None and value.next_snapshot_ref != SemanticReference(
        "curriculum-decision-snapshot",
        next_snapshot.id,
        next_snapshot.semantic_fingerprint,
    ):
        _add(
            issues,
            "TMM-POLICY-TRANSITION-MISMATCH",
            "transition.next_snapshot_ref",
            "transition does not identify the supplied next state",
        )

    if (
        selection is not None
        and prior_snapshot is not None
        and selection.snapshot_ref
        != SemanticReference(
            "curriculum-decision-snapshot",
            prior_snapshot.id,
            prior_snapshot.semantic_fingerprint,
        )
    ):
        _add(
            issues,
            "TMM-POLICY-TRANSITION-MISMATCH",
            "transition.selection_ref",
            "selection is detached from the supplied prior state",
        )
    if prior_snapshot is not None and next_snapshot is not None:
        unchanged = (
            prior_snapshot.run_id == next_snapshot.run_id,
            prior_snapshot.learner_context_id == next_snapshot.learner_context_id,
            prior_snapshot.score_package_digest == next_snapshot.score_package_digest,
            prior_snapshot.score_id == next_snapshot.score_id,
            prior_snapshot.graph_ref == next_snapshot.graph_ref,
            prior_snapshot.policy_identity == next_snapshot.policy_identity,
            prior_snapshot.policy_configuration_ref == next_snapshot.policy_configuration_ref,
            prior_snapshot.curriculum_contract_version == next_snapshot.curriculum_contract_version,
            prior_snapshot.performance_contract_version
            == next_snapshot.performance_contract_version,
            prior_snapshot.evidence_archive_contract_version
            == next_snapshot.evidence_archive_contract_version,
        )
        if not all(unchanged):
            _add(
                issues,
                "TMM-POLICY-TRANSITION-MISMATCH",
                "transition.next_snapshot_ref",
                "run, learner, score, graph, policy, or contract identity changed",
            )
        if (
            next_snapshot.decision_sequence != prior_snapshot.decision_sequence + 1
            or next_snapshot.evidence_snapshot_sequence
            != prior_snapshot.evidence_snapshot_sequence + 1
            or next_snapshot.previously_satisfied_node_ids
            != (*prior_snapshot.previously_satisfied_node_ids, prior_snapshot.current_node_id)
        ):
            _add(
                issues,
                "TMM-POLICY-TRANSITION-SEQUENCE",
                "transition.next_snapshot_ref",
                "next state does not advance the exact decision and evidence sequence",
            )
    if (
        selection is not None
        and next_snapshot is not None
        and selection.selected_candidate.target_node_id != next_snapshot.current_node_id
    ):
        _add(
            issues,
            "TMM-POLICY-TRANSITION-MISMATCH",
            "transition.next_snapshot_ref",
            "next state is not the selected graph target",
        )
    if (
        outcome is not None
        and next_snapshot is not None
        and (
            outcome.run_id != next_snapshot.run_id
            or next_snapshot.attempt_sequence != (outcome.attempt_ref.id,)
            or next_snapshot.observation_refs != outcome.observation_refs
        )
    ):
        _add(
            issues,
            "TMM-POLICY-TRANSITION-EVIDENCE-MISMATCH",
            "transition.outcome_ref",
            "next state does not preserve the factual outcome attempt and observations",
        )
    if (
        outcome is not None
        and reward is not None
        and (
            reward.run_id != outcome.run_id
            or reward.outcome_ref
            != SemanticReference(
                "curriculum-learning-outcome",
                outcome.id,
                outcome.semantic_fingerprint,
            )
        )
    ):
        _add(
            issues,
            "TMM-POLICY-TRANSITION-REWARD-MISMATCH",
            "transition.research_reward_ref",
            "research reward is detached from the factual outcome",
        )
    _fingerprint(value, "transition", issues)
    return tuple(issues)


def validate_curriculum_experiment_manifest(
    value: CurriculumExperimentManifest,
    snapshots: tuple[CurriculumDecisionSnapshot, ...] | None = None,
    inventories: tuple[CurriculumActionInventory, ...] | None = None,
    selections: tuple[CurriculumActionSelection, ...] | None = None,
    outcomes: tuple[CurriculumLearningOutcome, ...] | None = None,
    rewards: tuple[CurriculumResearchReward, ...] | None = None,
    transitions: tuple[CurriculumTransitionResult, ...] | None = None,
) -> tuple[CurriculumValidationIssue, ...]:
    """Validate a compact run-level index over ordered trajectory artifacts."""

    issues: list[CurriculumValidationIssue] = []
    _common(value.schema_version, value.id, value.semantic_fingerprint, "manifest", issues)
    if value.manifest_version != EXPERIMENT_MANIFEST_VERSION:
        _add(
            issues,
            "TMM-CONTRACT-UNKNOWN-VERSION",
            "manifest.manifest_version",
            "unknown experiment-manifest version",
        )
    _stable_id(value.run_id, "manifest.run_id", issues)
    _stable_id(value.score_id, "manifest.score_id", issues)
    _stable_id(value.learner_context_id, "manifest.learner_context_id", issues)
    if _SHA256.fullmatch(value.score_package_digest) is None:
        _add(
            issues,
            "TMM-CONTRACT-INVALID-EXACT-VALUE",
            "manifest.score_package_digest",
            "score package digest must be SHA-256",
        )
    _semantic_reference(value.graph_ref, "acquisition-graph-slice", "manifest.graph_ref", issues)
    _semantic_reference(
        value.policy_configuration_ref,
        "deterministic-policy-config",
        "manifest.policy_configuration_ref",
        issues,
    )
    if value.policy_identity != TEMPO_POLICY_ID:
        _add(
            issues,
            "TMM-CONTRACT-UNKNOWN-VERSION",
            "manifest.policy_identity",
            "unknown deterministic policy identity",
        )
    reference_groups = (
        (value.snapshot_refs, "curriculum-decision-snapshot", "snapshot_refs"),
        (value.action_inventory_refs, "curriculum-action-inventory", "action_inventory_refs"),
        (value.action_selection_refs, "curriculum-action-selection", "action_selection_refs"),
        (value.outcome_refs, "curriculum-learning-outcome", "outcome_refs"),
        (value.research_reward_refs, "curriculum-research-reward", "research_reward_refs"),
        (value.transition_refs, "curriculum-transition-result", "transition_refs"),
    )
    for references, artifact_type, name in reference_groups:
        for index, reference in enumerate(references):
            _semantic_reference(
                reference,
                artifact_type,
                f"manifest.{name}[{index}]",
                issues,
            )
        if len({item.id for item in references}) != len(references):
            _add(
                issues,
                "TMM-CONTRACT-DUPLICATE-ID",
                f"manifest.{name}",
                "manifest references repeat",
            )
    transition_count = len(value.transition_refs)
    if transition_count == 0 or (
        len(value.snapshot_refs) != transition_count + 1
        or len(value.action_inventory_refs) != transition_count
        or len(value.action_selection_refs) != transition_count
        or len(value.outcome_refs) != transition_count
        or len(value.research_reward_refs) != transition_count
    ):
        _add(
            issues,
            "TMM-POLICY-MANIFEST-CARDINALITY",
            "manifest.transition_refs",
            "one transition requires two snapshots and one of every other trajectory artifact",
        )
    if (
        value.first_decision_sequence < 0
        or value.last_decision_sequence < value.first_decision_sequence
        or value.last_decision_sequence - value.first_decision_sequence != transition_count
    ):
        _add(
            issues,
            "TMM-POLICY-MANIFEST-SEQUENCE",
            "manifest.last_decision_sequence",
            "manifest decision bounds do not match its ordered transitions",
        )
    if (
        value.curriculum_contract_version != CURRICULUM_CONTRACT_VERSION
        or value.performance_contract_version != PERFORMANCE_CONTRACT_VERSION
        or value.evidence_archive_contract_version != EVIDENCE_ARCHIVE_CONTRACT_VERSION
    ):
        _add(
            issues,
            "TMM-CONTRACT-UNKNOWN-VERSION",
            "manifest",
            "manifest governing contract versions are unsupported",
        )
    if (
        value.status is not CurriculumExperimentStatus.BOUNDED_COMPLETE
        or value.resolution is not ArtifactResolution.RESOLVED
    ):
        _add(
            issues,
            "TMM-POLICY-MANIFEST-UNRESOLVED",
            "manifest.status",
            "a frozen bounded manifest must be complete and resolved",
        )

    supplied = (snapshots, inventories, selections, outcomes, rewards, transitions)
    if any(item is not None for item in supplied) and any(item is None for item in supplied):
        _add(
            issues,
            "TMM-POLICY-MANIFEST-CONTEXT-INCOMPLETE",
            "manifest",
            "contextual validation requires every trajectory artifact family",
        )
    if all(item is not None for item in supplied):
        assert snapshots is not None
        assert inventories is not None
        assert selections is not None
        assert outcomes is not None
        assert rewards is not None
        assert transitions is not None
        exact_groups = (
            (value.snapshot_refs, snapshots, "curriculum-decision-snapshot", "snapshot_refs"),
            (
                value.action_inventory_refs,
                inventories,
                "curriculum-action-inventory",
                "action_inventory_refs",
            ),
            (
                value.action_selection_refs,
                selections,
                "curriculum-action-selection",
                "action_selection_refs",
            ),
            (value.outcome_refs, outcomes, "curriculum-learning-outcome", "outcome_refs"),
            (
                value.research_reward_refs,
                rewards,
                "curriculum-research-reward",
                "research_reward_refs",
            ),
            (
                value.transition_refs,
                transitions,
                "curriculum-transition-result",
                "transition_refs",
            ),
        )
        for manifest_refs, artifacts, artifact_type, name in exact_groups:
            expected_refs = tuple(
                SemanticReference(artifact_type, item.id, semantic_fingerprint(item))
                for item in artifacts
            )
            if manifest_refs != expected_refs:
                _add(
                    issues,
                    "TMM-POLICY-MANIFEST-REFERENCE-MISMATCH",
                    f"manifest.{name}",
                    "manifest references differ from supplied artifacts or order",
                )
        if snapshots:
            first = snapshots[0]
            common_snapshot_identity = all(
                snapshot.run_id == value.run_id
                and snapshot.score_package_digest == value.score_package_digest
                and snapshot.score_id == value.score_id
                and snapshot.learner_context_id == value.learner_context_id
                and snapshot.graph_ref == value.graph_ref
                and snapshot.policy_identity == value.policy_identity
                and snapshot.policy_configuration_ref == value.policy_configuration_ref
                and snapshot.curriculum_contract_version == value.curriculum_contract_version
                and snapshot.performance_contract_version == value.performance_contract_version
                and snapshot.evidence_archive_contract_version
                == value.evidence_archive_contract_version
                and snapshot.decision_sequence == value.first_decision_sequence + index
                for index, snapshot in enumerate(snapshots)
            )
            if (
                first.decision_sequence != value.first_decision_sequence
                or snapshots[-1].decision_sequence != value.last_decision_sequence
                or not common_snapshot_identity
            ):
                _add(
                    issues,
                    "TMM-POLICY-MANIFEST-SNAPSHOT-MISMATCH",
                    "manifest.snapshot_refs",
                    "snapshot identity or decision order differs from the manifest",
                )
        chain_count = min(
            len(transitions),
            max(len(snapshots) - 1, 0),
            len(inventories),
            len(selections),
            len(outcomes),
            len(rewards),
        )
        for index in range(chain_count):
            if not (
                inventories[index].snapshot_ref
                == SemanticReference(
                    "curriculum-decision-snapshot",
                    snapshots[index].id,
                    semantic_fingerprint(snapshots[index]),
                )
                and selections[index].inventory_ref
                == SemanticReference(
                    "curriculum-action-inventory",
                    inventories[index].id,
                    semantic_fingerprint(inventories[index]),
                )
                and selections[index].snapshot_ref == inventories[index].snapshot_ref
                and transitions[index].selection_ref
                == SemanticReference(
                    "curriculum-action-selection",
                    selections[index].id,
                    semantic_fingerprint(selections[index]),
                )
                and transitions[index].outcome_ref
                == SemanticReference(
                    "curriculum-learning-outcome",
                    outcomes[index].id,
                    semantic_fingerprint(outcomes[index]),
                )
                and transitions[index].research_reward_ref
                == SemanticReference(
                    "curriculum-research-reward",
                    rewards[index].id,
                    semantic_fingerprint(rewards[index]),
                )
                and transitions[index].next_snapshot_ref
                == SemanticReference(
                    "curriculum-decision-snapshot",
                    snapshots[index + 1].id,
                    semantic_fingerprint(snapshots[index + 1]),
                )
            ):
                _add(
                    issues,
                    "TMM-POLICY-MANIFEST-CHAIN-MISMATCH",
                    f"manifest.transition_refs[{index}]",
                    "trajectory artifacts do not form one ordered transition chain",
                )
    _fingerprint(value, "manifest", issues)
    return tuple(issues)


def validate_curriculum_metric_source_record(
    value: CurriculumMetricSourceRecord,
    manifest: CurriculumExperimentManifest | None = None,
) -> tuple[CurriculumValidationIssue, ...]:
    """Validate the compact app-owned authority for later metric projections."""

    issues: list[CurriculumValidationIssue] = []
    _common(value.schema_version, value.id, value.semantic_fingerprint, "metrics", issues)
    if value.source_record_version != METRIC_SOURCE_RECORD_VERSION:
        _add(
            issues,
            "TMM-CONTRACT-UNKNOWN-VERSION",
            "metrics.source_record_version",
            "unknown metric-source-record version",
        )
    _semantic_reference(
        value.manifest_ref,
        "curriculum-experiment-manifest",
        "metrics.manifest_ref",
        issues,
    )
    _stable_id(value.run_id, "metrics.run_id", issues)
    _stable_id(value.score_id, "metrics.score_id", issues)
    if _SHA256.fullmatch(value.score_package_digest) is None:
        _add(
            issues,
            "TMM-CONTRACT-INVALID-EXACT-VALUE",
            "metrics.score_package_digest",
            "score package digest must be SHA-256",
        )
    _semantic_reference(value.graph_ref, "acquisition-graph-slice", "metrics.graph_ref", issues)
    _semantic_reference(
        value.policy_configuration_ref,
        "deterministic-policy-config",
        "metrics.policy_configuration_ref",
        issues,
    )
    if value.policy_identity != TEMPO_POLICY_ID:
        _add(
            issues,
            "TMM-CONTRACT-UNKNOWN-VERSION",
            "metrics.policy_identity",
            "unknown deterministic policy identity",
        )

    expected_types = (
        ("prior_snapshot_ref", "curriculum-decision-snapshot"),
        ("action_inventory_ref", "curriculum-action-inventory"),
        ("action_selection_ref", "curriculum-action-selection"),
        ("outcome_ref", "curriculum-learning-outcome"),
        ("research_reward_ref", "curriculum-research-reward"),
        ("transition_ref", "curriculum-transition-result"),
        ("next_snapshot_ref", "curriculum-decision-snapshot"),
    )
    for index, metric_input in enumerate(value.metric_inputs):
        references = tuple(getattr(metric_input, name) for name, _ in expected_types)
        for (name, artifact_type), reference in zip(expected_types, references, strict=True):
            _semantic_reference(
                reference,
                artifact_type,
                f"metrics.metric_inputs[{index}].{name}",
                issues,
            )
        if metric_input.metric_input_fingerprint != semantic_fingerprint(references):
            _add(
                issues,
                "TMM-METRICS-INPUT-FINGERPRINT-MISMATCH",
                f"metrics.metric_inputs[{index}].metric_input_fingerprint",
                "the metric input fingerprint does not bind the exact source references",
            )
    transition_count = len(value.metric_inputs)
    if transition_count == 0:
        _add(
            issues,
            "TMM-METRICS-SOURCE-EMPTY",
            "metrics.metric_inputs",
            "a metric source record requires at least one transition",
        )
    expected_sequences = tuple(range(value.first_decision_sequence, value.last_decision_sequence))
    actual_sequences = tuple(item.decision_sequence for item in value.metric_inputs)
    if (
        value.first_decision_sequence < 0
        or value.last_decision_sequence - value.first_decision_sequence != transition_count
        or actual_sequences != expected_sequences
    ):
        _add(
            issues,
            "TMM-METRICS-SOURCE-SEQUENCE",
            "metrics.metric_inputs",
            "metric inputs must preserve the manifest's contiguous decision sequence",
        )
    if any(
        left.next_snapshot_ref != right.prior_snapshot_ref
        for left, right in zip(value.metric_inputs, value.metric_inputs[1:], strict=False)
    ):
        _add(
            issues,
            "TMM-METRICS-SOURCE-CHAIN-MISMATCH",
            "metrics.metric_inputs",
            "adjacent metric inputs do not share the same transition boundary",
        )
    if (
        value.curriculum_contract_version != CURRICULUM_CONTRACT_VERSION
        or value.performance_contract_version != PERFORMANCE_CONTRACT_VERSION
        or value.evidence_archive_contract_version != EVIDENCE_ARCHIVE_CONTRACT_VERSION
    ):
        _add(
            issues,
            "TMM-CONTRACT-UNKNOWN-VERSION",
            "metrics",
            "metric source governing contract versions are unsupported",
        )
    if value.resolution is not ArtifactResolution.RESOLVED:
        _add(
            issues,
            "TMM-METRICS-SOURCE-UNRESOLVED",
            "metrics.resolution",
            "an app-owned metric source record must be resolved",
        )

    if manifest is not None:
        expected_manifest_ref = SemanticReference(
            "curriculum-experiment-manifest",
            manifest.id,
            manifest.semantic_fingerprint,
        )
        common_identity = (
            value.manifest_ref == expected_manifest_ref,
            value.run_id == manifest.run_id,
            value.score_package_digest == manifest.score_package_digest,
            value.score_id == manifest.score_id,
            value.graph_ref == manifest.graph_ref,
            value.policy_identity == manifest.policy_identity,
            value.policy_configuration_ref == manifest.policy_configuration_ref,
            value.first_decision_sequence == manifest.first_decision_sequence,
            value.last_decision_sequence == manifest.last_decision_sequence,
            value.curriculum_contract_version == manifest.curriculum_contract_version,
            value.performance_contract_version == manifest.performance_contract_version,
            value.evidence_archive_contract_version == manifest.evidence_archive_contract_version,
        )
        if not all(common_identity):
            _add(
                issues,
                "TMM-METRICS-SOURCE-MANIFEST-MISMATCH",
                "metrics.manifest_ref",
                "metric source identity differs from the supplied manifest",
            )
        expected_inputs = tuple(
            (
                manifest.snapshot_refs[index],
                manifest.action_inventory_refs[index],
                manifest.action_selection_refs[index],
                manifest.outcome_refs[index],
                manifest.research_reward_refs[index],
                manifest.transition_refs[index],
                manifest.snapshot_refs[index + 1],
            )
            for index in range(len(manifest.transition_refs))
        )
        actual_inputs = tuple(
            (
                item.prior_snapshot_ref,
                item.action_inventory_ref,
                item.action_selection_ref,
                item.outcome_ref,
                item.research_reward_ref,
                item.transition_ref,
                item.next_snapshot_ref,
            )
            for item in value.metric_inputs
        )
        if actual_inputs != expected_inputs:
            _add(
                issues,
                "TMM-METRICS-SOURCE-REFERENCE-MISMATCH",
                "metrics.metric_inputs",
                "metric input references differ from the ordered manifest",
            )
    _fingerprint(value, "metrics", issues)
    return tuple(issues)


def require_valid_curriculum_metric_source_record(
    value: CurriculumMetricSourceRecord,
    manifest: CurriculumExperimentManifest | None = None,
) -> None:
    """Raise when the app-owned metric source loses exact trajectory identity."""

    if issues := validate_curriculum_metric_source_record(value, manifest):
        raise CurriculumValidationError(issues)


def validate_curriculum_metric_summary_export(
    value: CurriculumMetricSummaryExport,
    source: CurriculumMetricSourceRecord | None = None,
    snapshots: tuple[CurriculumDecisionSnapshot, ...] | None = None,
    selections: tuple[CurriculumActionSelection, ...] | None = None,
    outcomes: tuple[CurriculumLearningOutcome, ...] | None = None,
    rewards: tuple[CurriculumResearchReward, ...] | None = None,
) -> tuple[CurriculumValidationIssue, ...]:
    """Validate one de-identified allowlisted projection of governed metrics."""

    issues: list[CurriculumValidationIssue] = []
    _common(value.schema_version, value.id, value.semantic_fingerprint, "summary", issues)
    if value.summary_version != METRIC_SUMMARY_VERSION:
        _add(
            issues,
            "TMM-CONTRACT-UNKNOWN-VERSION",
            "summary.summary_version",
            "unknown de-identified metric-summary version",
        )
    _semantic_reference(
        value.source_record_ref,
        "curriculum-metric-source-record",
        "summary.source_record_ref",
        issues,
    )
    _stable_id(value.score_id, "summary.score_id", issues)
    _semantic_reference(value.graph_ref, "acquisition-graph-slice", "summary.graph_ref", issues)
    _semantic_reference(
        value.policy_configuration_ref,
        "deterministic-policy-config",
        "summary.policy_configuration_ref",
        issues,
    )
    if value.policy_identity != TEMPO_POLICY_ID:
        _add(
            issues,
            "TMM-CONTRACT-UNKNOWN-VERSION",
            "summary.policy_identity",
            "unknown deterministic policy identity",
        )

    for index, decision in enumerate(value.decision_metrics):
        if _SHA256.fullmatch(decision.metric_input_fingerprint) is None:
            _add(
                issues,
                "TMM-METRICS-SUMMARY-FINGERPRINT",
                f"summary.decision_metrics[{index}].metric_input_fingerprint",
                "metric input fingerprint must be SHA-256",
            )
        for reference, artifact_type, name in (
            (decision.prior_snapshot_ref, "curriculum-decision-snapshot", "prior_snapshot_ref"),
            (
                decision.action_selection_ref,
                "curriculum-action-selection",
                "action_selection_ref",
            ),
            (decision.outcome_ref, "curriculum-learning-outcome", "outcome_ref"),
            (
                decision.research_reward_ref,
                "curriculum-research-reward",
                "research_reward_ref",
            ),
            (decision.next_snapshot_ref, "curriculum-decision-snapshot", "next_snapshot_ref"),
            (decision.prior_support_state_ref, "support-state", "prior_support_state_ref"),
            (decision.next_support_state_ref, "support-state", "next_support_state_ref"),
        ):
            _semantic_reference(
                reference,
                artifact_type,
                f"summary.decision_metrics[{index}].{name}",
                issues,
            )
        _stable_id(
            decision.current_node_id, f"summary.decision_metrics[{index}].current_node_id", issues
        )
        _stable_id(decision.next_node_id, f"summary.decision_metrics[{index}].next_node_id", issues)
        if decision.behavior_probability != Fraction(1):
            _add(
                issues,
                "TMM-METRICS-SUMMARY-PROBABILITY",
                f"summary.decision_metrics[{index}].behavior_probability",
                "the deterministic baseline must export exact probability 1",
            )
        component_ids = tuple(item.component_id for item in decision.reward_components)
        if not component_ids or len(component_ids) != len(set(component_ids)):
            _add(
                issues,
                "TMM-METRICS-SUMMARY-COMPONENTS",
                f"summary.decision_metrics[{index}].reward_components",
                "reward component IDs must be present and unique",
            )
        for component_index, component in enumerate(decision.reward_components):
            path = f"summary.decision_metrics[{index}].reward_components[{component_index}]"
            if not component.component_id.strip() or not component.reason_code.strip():
                _add(
                    issues,
                    "TMM-CONTRACT-INVALID-EXACT-VALUE",
                    path,
                    "component and reason identifiers must be non-empty",
                )
            counts = (
                component.matched_observation_count,
                component.discrepancy_observation_count,
                component.unresolved_observation_count,
            )
            if any(count < 0 for count in counts):
                _add(
                    issues,
                    "TMM-METRICS-SUMMARY-COUNT",
                    path,
                    "observation counts must be non-negative",
                )
            if component.status is ResearchRewardComponentStatus.MEASURED:
                if component.value is None or not Fraction(0) <= component.value <= Fraction(1):
                    _add(
                        issues,
                        "TMM-METRICS-SUMMARY-VALUE",
                        path,
                        "measured components require an exact value between zero and one",
                    )
            elif component.value is not None:
                _add(
                    issues,
                    "TMM-METRICS-SUMMARY-VALUE",
                    path,
                    "unmeasured components must preserve a null value",
                )

    transition_count = len(value.decision_metrics)
    expected_sequences = tuple(range(value.first_decision_sequence, value.last_decision_sequence))
    actual_sequences = tuple(item.decision_sequence for item in value.decision_metrics)
    if (
        transition_count == 0
        or value.first_decision_sequence < 0
        or value.last_decision_sequence - value.first_decision_sequence != transition_count
        or actual_sequences != expected_sequences
    ):
        _add(
            issues,
            "TMM-METRICS-SUMMARY-SEQUENCE",
            "summary.decision_metrics",
            "summary decisions must preserve one contiguous source sequence",
        )
    if value.resolution is not ArtifactResolution.RESOLVED:
        _add(
            issues,
            "TMM-METRICS-SUMMARY-UNRESOLVED",
            "summary.resolution",
            "a de-identified metric summary must be resolved",
        )

    if source is not None:
        source_identity = (
            value.source_record_ref
            == SemanticReference(
                "curriculum-metric-source-record",
                source.id,
                source.semantic_fingerprint,
            ),
            value.score_id == source.score_id,
            value.graph_ref == source.graph_ref,
            value.policy_identity == source.policy_identity,
            value.policy_configuration_ref == source.policy_configuration_ref,
            value.first_decision_sequence == source.first_decision_sequence,
            value.last_decision_sequence == source.last_decision_sequence,
        )
        if not all(source_identity):
            _add(
                issues,
                "TMM-METRICS-SUMMARY-SOURCE-MISMATCH",
                "summary.source_record_ref",
                "summary identity differs from the app-owned source record",
            )
        summary_source_inputs = tuple(
            (
                item.decision_sequence,
                item.metric_input_fingerprint,
                item.prior_snapshot_ref,
                item.action_selection_ref,
                item.outcome_ref,
                item.research_reward_ref,
                item.next_snapshot_ref,
            )
            for item in value.decision_metrics
        )
        expected_source_inputs = tuple(
            (
                item.decision_sequence,
                item.metric_input_fingerprint,
                item.prior_snapshot_ref,
                item.action_selection_ref,
                item.outcome_ref,
                item.research_reward_ref,
                item.next_snapshot_ref,
            )
            for item in source.metric_inputs
        )
        if summary_source_inputs != expected_source_inputs:
            _add(
                issues,
                "TMM-METRICS-SUMMARY-SOURCE-MISMATCH",
                "summary.decision_metrics",
                "summary references differ from the app-owned source record",
            )

    contextual = (snapshots, selections, outcomes, rewards)
    if any(item is not None for item in contextual) and any(item is None for item in contextual):
        _add(
            issues,
            "TMM-METRICS-SUMMARY-CONTEXT-INCOMPLETE",
            "summary",
            "contextual validation requires every allowlisted source family",
        )
    if all(item is not None for item in contextual):
        assert snapshots is not None
        assert selections is not None
        assert outcomes is not None
        assert rewards is not None
        if (
            len(snapshots) != transition_count + 1
            or len(selections) != transition_count
            or len(outcomes) != transition_count
            or len(rewards) != transition_count
        ):
            _add(
                issues,
                "TMM-METRICS-SUMMARY-CARDINALITY",
                "summary.decision_metrics",
                "summary context does not contain one complete source transition per decision",
            )
        compare_count = min(
            transition_count,
            max(len(snapshots) - 1, 0),
            len(selections),
            len(outcomes),
            len(rewards),
        )
        for index in range(compare_count):
            decision = value.decision_metrics[index]
            reward_components = tuple(
                (
                    item.component_id,
                    item.dimension,
                    item.status,
                    item.value,
                    item.matched_observation_count,
                    item.discrepancy_observation_count,
                    item.unresolved_observation_count,
                    item.reason_code,
                )
                for item in decision.reward_components
            )
            expected_components = tuple(
                (
                    item.component_id,
                    item.dimension,
                    item.status,
                    item.value,
                    item.matched_observation_count,
                    item.discrepancy_observation_count,
                    item.unresolved_observation_count,
                    item.reason_code,
                )
                for item in rewards[index].components
            )
            expected_identity = (
                decision.current_node_id == snapshots[index].current_node_id,
                decision.next_node_id == snapshots[index + 1].current_node_id,
                decision.prior_support_state_ref == snapshots[index].support_state_ref,
                decision.next_support_state_ref == snapshots[index + 1].support_state_ref,
                decision.selected_action == selections[index].selected_candidate.action,
                decision.behavior_probability == selections[index].behavior_probability,
                decision.completion == outcomes[index].completion,
                reward_components == expected_components,
            )
            if not all(expected_identity):
                _add(
                    issues,
                    "TMM-METRICS-SUMMARY-PROJECTION-MISMATCH",
                    f"summary.decision_metrics[{index}]",
                    "summary values differ from the allowlisted authoritative artifacts",
                )
    _fingerprint(value, "summary", issues)
    return tuple(issues)


def require_valid_curriculum_metric_summary_export(
    value: CurriculumMetricSummaryExport,
    source: CurriculumMetricSourceRecord | None = None,
    snapshots: tuple[CurriculumDecisionSnapshot, ...] | None = None,
    selections: tuple[CurriculumActionSelection, ...] | None = None,
    outcomes: tuple[CurriculumLearningOutcome, ...] | None = None,
    rewards: tuple[CurriculumResearchReward, ...] | None = None,
) -> None:
    """Raise when a metric summary exceeds or drifts from its allowlist."""

    if issues := validate_curriculum_metric_summary_export(
        value,
        source,
        snapshots,
        selections,
        outcomes,
        rewards,
    ):
        raise CurriculumValidationError(issues)


def require_valid_curriculum_action_selection(
    value: CurriculumActionSelection,
    inventory: CurriculumActionInventory | None = None,
    snapshot: CurriculumDecisionSnapshot | None = None,
) -> None:
    """Raise when a deterministic action selection is invalid."""

    if issues := validate_curriculum_action_selection(value, inventory, snapshot):
        raise CurriculumValidationError(issues)


def require_valid_curriculum_transition_result(
    value: CurriculumTransitionResult,
    selection: CurriculumActionSelection | None = None,
    prior_snapshot: CurriculumDecisionSnapshot | None = None,
    outcome: CurriculumLearningOutcome | None = None,
    reward: CurriculumResearchReward | None = None,
    next_snapshot: CurriculumDecisionSnapshot | None = None,
) -> None:
    """Raise when an executed selection loses outcome or next-state identity."""

    if issues := validate_curriculum_transition_result(
        value,
        selection,
        prior_snapshot,
        outcome,
        reward,
        next_snapshot,
    ):
        raise CurriculumValidationError(issues)


def require_valid_curriculum_experiment_manifest(
    value: CurriculumExperimentManifest,
    snapshots: tuple[CurriculumDecisionSnapshot, ...] | None = None,
    inventories: tuple[CurriculumActionInventory, ...] | None = None,
    selections: tuple[CurriculumActionSelection, ...] | None = None,
    outcomes: tuple[CurriculumLearningOutcome, ...] | None = None,
    rewards: tuple[CurriculumResearchReward, ...] | None = None,
    transitions: tuple[CurriculumTransitionResult, ...] | None = None,
) -> None:
    """Raise when a bounded experiment manifest loses its ordered chain."""

    if issues := validate_curriculum_experiment_manifest(
        value,
        snapshots,
        inventories,
        selections,
        outcomes,
        rewards,
        transitions,
    ):
        raise CurriculumValidationError(issues)


def require_valid_curriculum_passage_presentation(
    value: CurriculumPassagePresentation,
    scope: PracticeScopeAssignment | None = None,
) -> None:
    """Raise when a curriculum passage cannot cross presentation safely."""

    if issues := validate_curriculum_passage_presentation(value, scope):
        raise CurriculumValidationError(issues)


def require_valid_curriculum_passage_guidance(
    value: CurriculumPassageGuidance,
    requirements: PassageRequirementSet | None = None,
    presentation: CurriculumPassagePresentation | None = None,
) -> None:
    """Raise when learner guidance cannot cross the presentation boundary."""

    if issues := validate_curriculum_passage_guidance(value, requirements, presentation):
        raise CurriculumValidationError(issues)


def require_valid_curriculum_fundamental_explanation(
    value: CurriculumFundamentalExplanation,
    requirements: PassageRequirementSet | None = None,
    branches: PrerequisiteBranchSet | None = None,
    presentation: CurriculumPassagePresentation | None = None,
) -> None:
    """Raise when functional prerequisite text loses its exact return route."""

    if issues := validate_curriculum_fundamental_explanation(
        value,
        requirements,
        branches,
        presentation,
    ):
        raise CurriculumValidationError(issues)


def require_valid_curriculum_fundamental_demonstration(
    value: CurriculumFundamentalDemonstration,
    explanation: CurriculumFundamentalExplanation | None = None,
    requirements: PassageRequirementSet | None = None,
    branches: PrerequisiteBranchSet | None = None,
    presentation: CurriculumPassagePresentation | None = None,
    playback: PlaybackPlan | None = None,
) -> None:
    """Raise when a prerequisite demonstration loses its exact provenance."""

    if issues := validate_curriculum_fundamental_demonstration(
        value,
        explanation,
        requirements,
        branches,
        presentation,
        playback,
    ):
        raise CurriculumValidationError(issues)


def require_valid_curriculum_fundamental_practice(
    value: CurriculumFundamentalPractice,
    explanation: CurriculumFundamentalExplanation | None = None,
    demonstration: CurriculumFundamentalDemonstration | None = None,
    requirements: PassageRequirementSet | None = None,
    branches: PrerequisiteBranchSet | None = None,
    presentation: CurriculumPassagePresentation | None = None,
    expected: ExpectedPerformance | None = None,
) -> None:
    """Raise when a prerequisite learner response loses its exact target."""

    if issues := validate_curriculum_fundamental_practice(
        value,
        explanation,
        demonstration,
        requirements,
        branches,
        presentation,
        expected,
    ):
        raise CurriculumValidationError(issues)


def require_valid_curriculum_learning_outcome(
    value: CurriculumLearningOutcome,
    practice: CurriculumFundamentalPractice | None = None,
    expected: ExpectedPerformance | None = None,
    attempt: LearnerAttempt | None = None,
    calibration: CalibrationProfile | None = None,
    support: SupportState | None = None,
    observations: tuple[Observation, ...] | None = None,
    exercise: ExerciseInstance | None = None,
) -> None:
    """Raise when a factual outcome loses any exact attempt input."""

    if issues := validate_curriculum_learning_outcome(
        value,
        practice,
        expected,
        attempt,
        calibration,
        support,
        observations,
        exercise,
    ):
        raise CurriculumValidationError(issues)


def require_valid_curriculum_research_reward(
    value: CurriculumResearchReward,
    outcome: CurriculumLearningOutcome | None = None,
    expected: ExpectedPerformance | None = None,
    observations: tuple[Observation, ...] | None = None,
) -> None:
    """Raise when research-reward components lose evidence or rule identity."""

    if issues := validate_curriculum_research_reward(
        value,
        outcome,
        expected,
        observations,
    ):
        raise CurriculumValidationError(issues)


def require_valid_curriculum_game_reward(
    value: CurriculumGameReward,
    outcome: CurriculumLearningOutcome | None = None,
    research_reward: CurriculumResearchReward | None = None,
) -> None:
    """Raise when a learner-facing acknowledgement gains unsupported meaning."""

    if issues := validate_curriculum_game_reward(value, outcome, research_reward):
        raise CurriculumValidationError(issues)


def require_valid_curriculum_piece_return(
    value: CurriculumPieceReturn,
    practice: CurriculumFundamentalPractice | None = None,
    mastery: CurriculumMasteryProjection | None = None,
    decision: CurriculumUnlockDecision | None = None,
    branches: PrerequisiteBranchSet | None = None,
    graph: AcquisitionGraphSlice | None = None,
    presentation: CurriculumPassagePresentation | None = None,
) -> None:
    """Raise when a prerequisite return loses evidence or passage identity."""

    if issues := validate_curriculum_piece_return(
        value,
        practice,
        mastery,
        decision,
        branches,
        graph,
        presentation,
    ):
        raise CurriculumValidationError(issues)


def require_valid_primitive(value: LearningPrimitive) -> None:
    """Raise when one primitive is invalid."""

    if issues := validate_primitive(value):
        raise CurriculumValidationError(issues)


def require_valid_requirement(value: PassageSkillRequirement) -> None:
    """Raise when one requirement is invalid."""

    if issues := validate_requirement(value):
        raise CurriculumValidationError(issues)


def require_valid_requirement_set(
    value: PassageRequirementSet,
    package: CanonicalMusicPackage | None = None,
    analysis: ScoreAnalysis | None = None,
) -> None:
    """Raise when a complete requirement set is invalid."""

    if issues := validate_requirement_set(value, package, analysis):
        raise CurriculumValidationError(issues)


def require_valid_exercise_instance(value: ExerciseInstance) -> None:
    """Raise when one generated exercise is invalid."""

    if issues := validate_exercise_instance(value):
        raise CurriculumValidationError(issues)


def require_valid_prerequisite_branch_set(
    value: PrerequisiteBranchSet,
    requirements: PassageRequirementSet,
) -> None:
    """Raise when a generated prerequisite branch slice is invalid."""

    if issues := validate_prerequisite_branch_set(value, requirements):
        raise CurriculumValidationError(issues)


def require_valid_tempo_configuration(value: TempoConfiguration) -> None:
    """Raise when the frozen tempo configuration is invalid."""

    if issues := validate_tempo_configuration(value):
        raise CurriculumValidationError(issues)


def require_valid_acquisition_graph_slice(value: AcquisitionGraphSlice) -> None:
    """Raise when a generated 9B.3 acquisition slice is invalid."""

    if issues := validate_acquisition_graph_slice(value):
        raise CurriculumValidationError(issues)


def require_valid_lasting_skill_graph_slice(
    value: LastingSkillGraphSlice,
    source_requirements: PassageRequirementSet | None = None,
    acquisition: AcquisitionGraphSlice | None = None,
    transfer_requirements: PassageRequirementSet | None = None,
) -> None:
    """Raise when a generated 9B.4 retention/transfer slice is invalid."""

    if issues := validate_lasting_skill_graph_slice(
        value,
        source_requirements,
        acquisition,
        transfer_requirements,
    ):
        raise CurriculumValidationError(issues)


def _common(
    schema_version: str,
    identifier: str,
    fingerprint: str,
    path: str,
    issues: list[CurriculumValidationIssue],
) -> None:
    if schema_version != CURRICULUM_CONTRACT_VERSION:
        _add(issues, "TMM-CONTRACT-UNKNOWN-VERSION", f"{path}.schema_version", "unsupported")
    _stable_id(identifier, f"{path}.id", issues)
    if _SHA256.fullmatch(fingerprint) is None:
        _add(
            issues,
            "TMM-CONTRACT-INVALID-EXACT-VALUE",
            f"{path}.semantic_fingerprint",
            "expected SHA-256",
        )


def _fingerprint(
    value: (
        PracticeScopeAssignment
        | LearningPrimitive
        | PassageSkillRequirement
        | ExerciseInstance
        | TempoConfiguration
        | ControlledTempoPlan
        | AcquisitionGraphSlice
        | RetentionWindow
        | RetentionSchedule
        | TransferTargetAssignment
        | LastingSkillGraphSlice
        | CurriculumPassagePresentation
        | CurriculumPassageGuidance
        | CurriculumFundamentalExplanation
        | CurriculumFundamentalDemonstration
        | CurriculumFundamentalPractice
        | CurriculumLearningOutcome
        | CurriculumResearchReward
        | CurriculumGameReward
        | CurriculumPieceReturn
        | CurriculumEvidenceRecord
        | CurriculumMasteryProjection
        | CurriculumUnlockDecision
        | CurriculumDecisionSnapshot
        | CurriculumActionInventory
        | CurriculumActionSelection
        | CurriculumTransitionResult
        | CurriculumExperimentManifest
        | CurriculumMetricSourceRecord
        | CurriculumMetricSummaryExport
    ),
    path: str,
    issues: list[CurriculumValidationIssue],
) -> None:
    if value.semantic_fingerprint != semantic_fingerprint(value):
        _add(
            issues,
            "TMM-CONTRACT-FINGERPRINT-MISMATCH",
            f"{path}.semantic_fingerprint",
            "semantic fields do not match fingerprint",
        )


def _catalogue_cycle_issues(
    values: tuple[LearningPrimitive, ...],
) -> tuple[CurriculumValidationIssue, ...]:
    graph = {item.id: item.prerequisite_ids for item in values}
    visiting: set[str] = set()
    visited: set[str] = set()
    issues: list[CurriculumValidationIssue] = []

    def visit(identifier: str) -> None:
        if identifier in visiting:
            _add(
                issues,
                "TMM-PRIMITIVE-PREREQUISITE-CYCLE",
                f"primitive[{identifier}]",
                "catalogue prerequisite cycle",
            )
            return
        if identifier in visited:
            return
        visiting.add(identifier)
        for dependency in graph.get(identifier, ()):
            visit(dependency)
        visiting.remove(identifier)
        visited.add(identifier)

    for identifier in graph:
        visit(identifier)
    return tuple(issues)


def _unique_by_id[T: (CurriculumGraphNode, CurriculumGraphEdge, ExerciseInstance)](
    values: tuple[T, ...],
    path: str,
    issues: list[CurriculumValidationIssue],
) -> dict[str, T]:
    result = {item.id: item for item in values}
    if len(result) != len(values):
        _add(issues, "TMM-CONTRACT-DUPLICATE-ID", path, "identifier repeats")
    return result


def _graph_static_cycle_issues(
    edges: tuple[CurriculumGraphEdge, ...],
) -> tuple[CurriculumValidationIssue, ...]:
    graph: dict[str, list[str]] = {}
    for edge in edges:
        if edge.kind is CurriculumEdgeKind.REQUIRES:
            graph.setdefault(edge.source_node_id, []).append(edge.target_node_id)
    visiting: set[str] = set()
    visited: set[str] = set()
    issues: list[CurriculumValidationIssue] = []

    def visit(identifier: str) -> None:
        if identifier in visiting:
            _add(
                issues,
                "TMM-GRAPH-STATIC-CYCLE",
                f"branches.nodes[{identifier}]",
                "static prerequisite cycle",
            )
            return
        if identifier in visited:
            return
        visiting.add(identifier)
        for target in graph.get(identifier, ()):
            visit(target)
        visiting.remove(identifier)
        visited.add(identifier)

    for identifier in graph:
        visit(identifier)
    return tuple(issues)


def _rule_reference(
    value: RuleReference,
    path: str,
    issues: list[CurriculumValidationIssue],
) -> None:
    if not value.rule_id or not value.rule_version:
        _add(issues, "TMM-CONTRACT-INVALID-EXACT-VALUE", path, "rule identity is empty")
    if value.semantic_fingerprint != semantic_fingerprint((value.rule_id, value.rule_version)):
        _add(
            issues,
            "TMM-CONTRACT-FINGERPRINT-MISMATCH",
            f"{path}.semantic_fingerprint",
            "rule identity does not match fingerprint",
        )


def _semantic_reference(
    value: SemanticReference,
    artifact_type: str,
    path: str,
    issues: list[CurriculumValidationIssue],
) -> None:
    if value.artifact_type != artifact_type:
        _add(
            issues,
            "TMM-CONTRACT-INVALID-EXACT-VALUE",
            f"{path}.artifact_type",
            f"expected {artifact_type}",
        )
    _stable_id(value.id, f"{path}.id", issues)
    if _SHA256.fullmatch(value.semantic_fingerprint) is None:
        _add(
            issues,
            "TMM-CONTRACT-INVALID-EXACT-VALUE",
            f"{path}.semantic_fingerprint",
            "expected SHA-256",
        )


def _unique_ids(
    values: tuple[str, ...],
    path: str,
    issues: list[CurriculumValidationIssue],
) -> None:
    if len(values) != len(set(values)):
        _add(issues, "TMM-CONTRACT-DUPLICATE-ID", path, "reference repeats")
    for index, value in enumerate(values):
        _stable_id(value, f"{path}[{index}]", issues)


def _stable_id(value: object, path: str, issues: list[CurriculumValidationIssue]) -> None:
    primitive_id = isinstance(value, str) and re.fullmatch(r"PRIM-[A-Z]+-[0-9]{3}", value)
    if not is_stable_id(value) and not primitive_id:
        _add(issues, "TMM-CONTRACT-INVALID-EXACT-VALUE", path, "invalid stable ID")


def _add(
    issues: list[CurriculumValidationIssue],
    code: str,
    path: str,
    message: str,
) -> None:
    issues.append(CurriculumValidationIssue(code, path, message))
