"""Deterministic functional text for graph-declared missing fundamentals."""

from __future__ import annotations

from dataclasses import replace

from .curriculum_contracts import (
    CURRICULUM_CONTRACT_VERSION,
    FUNDAMENTAL_EXPLANATION_VERSION,
    ArtifactResolution,
    CurriculumFundamentalExplanation,
    CurriculumPassagePresentation,
    PassageRequirementSet,
    PrerequisiteBranchSet,
    RuleReference,
    SemanticReference,
)
from .curriculum_fingerprint import semantic_fingerprint
from .curriculum_validation import (
    require_valid_curriculum_fundamental_explanation,
    require_valid_curriculum_passage_presentation,
    require_valid_prerequisite_branch_set,
    require_valid_requirement_set,
)
from .presentation import build_curriculum_passage_guidance

_EXPLANATION_RULE_ID = "EXPLANATION-RULE-001"


class CurriculumFundamentalExplanationError(ValueError):
    """Raised when functional prerequisite text would lose provenance."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(f"{code}: {message}")


def build_curriculum_fundamental_explanation(
    requirements: PassageRequirementSet,
    branches: PrerequisiteBranchSet,
    presentation: CurriculumPassagePresentation,
    requirement_id: str,
) -> CurriculumFundamentalExplanation:
    """Build functional text for one prerequisite selected by the policy.

    The caller remains responsible for deciding that the requirement needs its
    prerequisite branch. This function only renders that already-declared
    branch and never infers learner state from score content.
    """

    require_valid_requirement_set(requirements)
    require_valid_prerequisite_branch_set(branches, requirements)
    require_valid_curriculum_passage_presentation(presentation)
    if branches.resolution is not ArtifactResolution.RESOLVED:
        raise CurriculumFundamentalExplanationError(
            "TMM-EXPLANATION-BRANCH-UNRESOLVED",
            "functional text requires a resolved prerequisite graph",
        )
    if requirements.analysis_id != branches.analysis_id:
        raise CurriculumFundamentalExplanationError(
            "TMM-EXPLANATION-ANALYSIS-MISMATCH",
            "requirements and prerequisite graph use different analysis inputs",
        )

    requirement = next(
        (item for item in requirements.requirements if item.id == requirement_id),
        None,
    )
    branch = next(
        (item for item in branches.branches if item.requirement_ref.id == requirement_id),
        None,
    )
    if requirement is None or branch is None:
        raise CurriculumFundamentalExplanationError(
            "TMM-EXPLANATION-REQUIREMENT-MISSING",
            "the requested requirement has no declared prerequisite branch",
        )
    if requirement.resolution is not ArtifactResolution.RESOLVED:
        raise CurriculumFundamentalExplanationError(
            "TMM-EXPLANATION-REQUIREMENT-UNRESOLVED",
            "functional text cannot be emitted for an unresolved requirement",
        )
    if requirement.practice_scope_ref != presentation.practice_scope_ref:
        raise CurriculumFundamentalExplanationError(
            "TMM-EXPLANATION-SCOPE-MISMATCH",
            "the requested requirement is outside the active passage presentation",
        )

    node_by_id = {item.id: item for item in branches.nodes}
    prerequisite_node = node_by_id[branch.prerequisite_node_id]
    application_node = node_by_id[branch.application_node_id]
    if prerequisite_node.exercise_ref is None or application_node.exercise_ref is None:
        raise CurriculumFundamentalExplanationError(
            "TMM-EXPLANATION-EXERCISE-MISSING",
            "the declared prerequisite or application node has no exercise",
        )

    exercise_by_id = {item.id: item for item in branches.exercises}
    prerequisite_exercise = exercise_by_id.get(prerequisite_node.exercise_ref.id)
    application_exercise = exercise_by_id.get(application_node.exercise_ref.id)
    if prerequisite_exercise is None or application_exercise is None:
        raise CurriculumFundamentalExplanationError(
            "TMM-EXPLANATION-EXERCISE-MISSING",
            "the declared prerequisite or application exercise is absent",
        )
    if prerequisite_exercise.return_target_id != branch.application_node_id:
        raise CurriculumFundamentalExplanationError(
            "TMM-EXPLANATION-RETURN-MISMATCH",
            "the prerequisite does not return to its exact piece-application node",
        )

    guidance = build_curriculum_passage_guidance(requirements, presentation)
    item = next(
        (entry for entry in guidance.items if entry.requirement_ref.id == requirement_id),
        None,
    )
    if item is None:
        raise CurriculumFundamentalExplanationError(
            "TMM-EXPLANATION-GUIDANCE-MISSING",
            "the requested prerequisite has no traceable passage guidance",
        )

    layer = {
        "single-layer": "selected passage",
        "upper-layer": "upper written layer",
        "lower-layer": "lower written layer",
        "combined": "combined written layers",
    }[presentation.notation_condition.value]
    generation_rule = RuleReference(
        _EXPLANATION_RULE_ID,
        FUNDAMENTAL_EXPLANATION_VERSION,
        semantic_fingerprint((_EXPLANATION_RULE_ID, FUNDAMENTAL_EXPLANATION_VERSION)),
    )
    provisional = CurriculumFundamentalExplanation(
        schema_version=CURRICULUM_CONTRACT_VERSION,
        id="curriculum-fundamental-explanation:pending",
        semantic_fingerprint="",
        analysis_id=requirements.analysis_id,
        package_id=presentation.package_id,
        score_id=presentation.score_id,
        requirement_ref=item.requirement_ref,
        primitive_ref=item.primitive_ref,
        practice_scope_ref=presentation.practice_scope_ref,
        presentation_ref=SemanticReference(
            "curriculum-passage-presentation",
            presentation.id,
            presentation.semantic_fingerprint,
        ),
        prerequisite_exercise_ref=prerequisite_node.exercise_ref,
        application_exercise_ref=application_node.exercise_ref,
        prerequisite_node_id=branch.prerequisite_node_id,
        return_node_id=branch.application_node_id,
        heading=item.heading,
        explanation=item.explanation,
        why_it_matters=(
            f"The highlighted events in the {layer} require this skill before "
            "you apply it in the chosen piece."
        ),
        action_prompt=item.action_prompt,
        return_prompt=item.reconnect_prompt,
        target_parameters=item.target_parameters,
        focus_event_ids=item.focus_event_ids,
        generation_rule=generation_rule,
        diagnostics=(),
        resolution=ArtifactResolution.RESOLVED,
    )
    fingerprint = semantic_fingerprint(provisional)
    result = replace(
        provisional,
        id=f"curriculum-fundamental-explanation:{fingerprint}",
        semantic_fingerprint=fingerprint,
    )
    require_valid_curriculum_fundamental_explanation(
        result,
        requirements=requirements,
        branches=branches,
        presentation=presentation,
    )
    return result
