"""Deterministic DEV-009 Task 9B.2 prerequisite branch generation."""

from __future__ import annotations

from dataclasses import replace

from .curriculum_contracts import (
    BRANCH_GENERATOR_VERSION,
    CURRICULUM_CONTRACT_VERSION,
    CURRICULUM_GRAPH_ID,
    EXERCISE_TEMPLATE_CATALOGUE_ID,
    ActivityForm,
    ArtifactResolution,
    CanonicalExcerptMaterial,
    CurriculumEdgeKind,
    CurriculumGraphEdge,
    CurriculumGraphNode,
    CurriculumNodeKind,
    ExerciseActivity,
    ExerciseEvidenceExit,
    ExerciseInstance,
    ExerciseSupportEnvelope,
    ExerciseTemplateFamily,
    PassageRequirementSet,
    PassageSkillRequirement,
    PracticeScopeAssignment,
    PrerequisiteBranchSet,
    RequirementTeachingBranch,
    RuleReference,
    SemanticReference,
)
from .curriculum_fingerprint import derived_id, semantic_fingerprint
from .curriculum_validation import (
    require_valid_prerequisite_branch_set,
    require_valid_requirement_set,
)

_TEMPLATE_IDS = {
    ExerciseTemplateFamily.DIAGNOSTIC: "TEMPLATE-DIAGNOSTIC-001",
    ExerciseTemplateFamily.PREREQUISITE: "TEMPLATE-PREREQUISITE-001",
    ExerciseTemplateFamily.PIECE_APPLICATION: "TEMPLATE-PIECE-APPLICATION-001",
}


def generate_prerequisite_branches(
    requirements: PassageRequirementSet,
) -> PrerequisiteBranchSet:
    """Generate diagnostic, prerequisite, and exact source-return branches.

    This composable slice deliberately stops before phrase, layer-integration,
    retention, and transfer graph generation.
    """

    require_valid_requirement_set(requirements)
    if any(scope.resolution is not ArtifactResolution.RESOLVED for scope in requirements.scopes):
        result = PrerequisiteBranchSet(
            graph_identity=CURRICULUM_GRAPH_ID,
            analysis_id=requirements.analysis_id,
            nodes=(),
            edges=(),
            exercises=(),
            branches=(),
            diagnostics=requirements.diagnostics
            or tuple(
                diagnostic for scope in requirements.scopes for diagnostic in scope.diagnostics
            ),
            resolution=ArtifactResolution.REVIEW_REQUIRED,
        )
        require_valid_prerequisite_branch_set(result, requirements)
        return result

    scope_by_id = {item.id: item for item in requirements.scopes}
    primitive_by_id = {item.id: item for item in requirements.primitives}
    requirement_by_id = {item.id: item for item in requirements.requirements}
    application_node_ids = {
        item.id: derived_id("curriculum-node", ("application", item.id))
        for item in requirements.requirements
    }
    nodes: list[CurriculumGraphNode] = []
    edges: list[CurriculumGraphEdge] = []
    exercises: list[ExerciseInstance] = []
    branches: list[RequirementTeachingBranch] = []

    for primitive in requirements.primitives:
        if not any(item.primitive_ref.id == primitive.id for item in requirements.requirements):
            continue
        primitive_ref = SemanticReference(
            "learning-primitive", primitive.id, primitive.semantic_fingerprint
        )
        nodes.append(
            CurriculumGraphNode(
                id=derived_id("curriculum-node", ("primitive", primitive.id)),
                kind=CurriculumNodeKind.PRIMITIVE,
                scope_ref=None,
                primitive_ref=primitive_ref,
                requirement_ref=None,
                exercise_ref=None,
                component_node_ids=(),
                budget_key=None,
                terminal_outcome=None,
            )
        )

    for requirement in requirements.requirements:
        scope = scope_by_id[requirement.practice_scope_ref.id]
        primitive = primitive_by_id[requirement.primitive_ref.id]
        application_node_id = application_node_ids[requirement.id]
        diagnostic_node_id = derived_id("curriculum-node", ("diagnostic", requirement.id))
        prerequisite_node_id = derived_id("curriculum-node", ("prerequisite", requirement.id))
        requirement_ref = SemanticReference(
            "passage-skill-requirement", requirement.id, requirement.semantic_fingerprint
        )
        primitive_ref = SemanticReference(
            "learning-primitive", primitive.id, primitive.semantic_fingerprint
        )

        diagnostic = _exercise(
            ExerciseTemplateFamily.DIAGNOSTIC,
            requirement,
            scope,
            application_node_id,
        )
        prerequisite = _exercise(
            ExerciseTemplateFamily.PREREQUISITE,
            requirement,
            scope,
            application_node_id,
        )
        application = _exercise(
            ExerciseTemplateFamily.PIECE_APPLICATION,
            requirement,
            scope,
            application_node_id,
        )
        exercises.extend((diagnostic, prerequisite, application))
        diagnostic_ref = _exercise_ref(diagnostic)
        prerequisite_ref = _exercise_ref(prerequisite)
        application_ref = _exercise_ref(application)

        nodes.extend(
            (
                CurriculumGraphNode(
                    diagnostic_node_id,
                    CurriculumNodeKind.DIAGNOSTIC,
                    requirement.practice_scope_ref,
                    primitive_ref,
                    requirement_ref,
                    diagnostic_ref,
                    (),
                    None,
                    None,
                ),
                CurriculumGraphNode(
                    prerequisite_node_id,
                    CurriculumNodeKind.PREREQUISITE,
                    requirement.practice_scope_ref,
                    primitive_ref,
                    requirement_ref,
                    prerequisite_ref,
                    (),
                    None,
                    None,
                ),
                CurriculumGraphNode(
                    application_node_id,
                    CurriculumNodeKind.APPLICATION,
                    requirement.practice_scope_ref,
                    primitive_ref,
                    requirement_ref,
                    application_ref,
                    tuple(
                        application_node_ids[item]
                        for item in requirement.prerequisite_requirement_ids
                    ),
                    None,
                    None,
                ),
            )
        )
        primitive_node_id = derived_id("curriculum-node", ("primitive", primitive.id))
        for exercise_node_id in (
            diagnostic_node_id,
            prerequisite_node_id,
            application_node_id,
        ):
            edges.append(
                _edge(
                    CurriculumEdgeKind.REALIZED_BY,
                    primitive_node_id,
                    exercise_node_id,
                    "compatible-exercise-instance",
                    0,
                )
            )
        edges.extend(
            (
                _edge(
                    CurriculumEdgeKind.ON_SATISFIED,
                    diagnostic_node_id,
                    application_node_id,
                    "compatible-diagnostic-pass",
                    0,
                ),
                _edge(
                    CurriculumEdgeKind.ON_UNCONFIRMED,
                    diagnostic_node_id,
                    prerequisite_node_id,
                    "diagnostic-unconfirmed-or-discrepant",
                    1,
                ),
                _edge(
                    CurriculumEdgeKind.RETURN_TO,
                    prerequisite_node_id,
                    application_node_id,
                    "prerequisite-exit-supported",
                    0,
                    return_node_id=application_node_id,
                ),
            )
        )
        for dependency_id in requirement.prerequisite_requirement_ids:
            dependency = requirement_by_id[dependency_id]
            edges.append(
                _edge(
                    CurriculumEdgeKind.REQUIRES,
                    application_node_id,
                    application_node_ids[dependency.id],
                    "prerequisite-application-supported",
                    0,
                )
            )
        branches.append(
            RequirementTeachingBranch(
                requirement_ref,
                diagnostic_node_id,
                prerequisite_node_id,
                application_node_id,
                requirement.prerequisite_requirement_ids,
            )
        )

    result = PrerequisiteBranchSet(
        graph_identity=CURRICULUM_GRAPH_ID,
        analysis_id=requirements.analysis_id,
        nodes=tuple(sorted(nodes, key=lambda item: (item.kind.value, item.id))),
        edges=tuple(
            sorted(
                edges,
                key=lambda item: (
                    item.source_node_id,
                    item.precedence,
                    item.kind.value,
                    item.target_node_id,
                ),
            )
        ),
        exercises=tuple(sorted(exercises, key=lambda item: item.id)),
        branches=tuple(sorted(branches, key=lambda item: item.requirement_ref.id)),
        diagnostics=(),
        resolution=ArtifactResolution.RESOLVED,
    )
    require_valid_prerequisite_branch_set(result, requirements)
    return result


def _exercise(
    family: ExerciseTemplateFamily,
    requirement: PassageSkillRequirement,
    scope: PracticeScopeAssignment,
    return_target_id: str,
) -> ExerciseInstance:
    template_id = _TEMPLATE_IDS[family]
    template_ref = SemanticReference(
        "exercise-template",
        template_id,
        semantic_fingerprint((EXERCISE_TEMPLATE_CATALOGUE_ID, template_id)),
    )
    requirement_ref = SemanticReference(
        "passage-skill-requirement", requirement.id, requirement.semantic_fingerprint
    )
    forms = {
        ExerciseTemplateFamily.DIAGNOSTIC: (ActivityForm.ORIENT, ActivityForm.PERFORM),
        ExerciseTemplateFamily.PREREQUISITE: (
            ActivityForm.EXPLAIN,
            ActivityForm.DEMONSTRATE_LISTEN,
            ActivityForm.PERFORM,
            ActivityForm.RECONNECT,
        ),
        ExerciseTemplateFamily.PIECE_APPLICATION: (
            ActivityForm.ORIENT,
            ActivityForm.DEMONSTRATE_LISTEN,
            ActivityForm.PERFORM,
        ),
    }[family]
    key = (family.value, requirement.id)
    activities = tuple(
        ExerciseActivity(
            derived_id("exercise-activity", (*key, index, form.value)),
            form,
            form is ActivityForm.PERFORM,
        )
        for index, form in enumerate(forms)
    )
    if family is ExerciseTemplateFamily.DIAGNOSTIC:
        support = ExerciseSupportEnvelope(
            "diagnostic-independent", ("diagnostic-independent",), "diagnostic-independent"
        )
        context = "diagnostic"
        minimum_state = "diagnostic-observed"
    elif family is ExerciseTemplateFamily.PREREQUISITE:
        support = ExerciseSupportEnvelope(
            "guided", ("guided", "reduced-support", "independent"), "independent"
        )
        context = "acquisition"
        minimum_state = "stable-supported"
    else:
        support = ExerciseSupportEnvelope(
            "guided-piece", ("guided-piece", "independent-piece"), "independent-piece"
        )
        context = "passage-application"
        minimum_state = "independent-in-session"
    material = CanonicalExcerptMaterial(
        "canonical-excerpt",
        scope.score_package_digest,
        scope.score_id,
        requirement.practice_scope_ref,
        scope.canonical_anchor_set_id,
        scope.active_target_ids,
        scope.inactive_context_ids,
    )
    exits = tuple(
        ExerciseEvidenceExit(dimension, context, minimum_state)
        for dimension in requirement.required_dimensions
    )
    generation_rule = _rule("BRANCH-RULE-001")
    provisional = ExerciseInstance(
        CURRICULUM_CONTRACT_VERSION,
        "exercise-instance:pending",
        "",
        (),
        template_ref,
        requirement_ref,
        requirement.practice_scope_ref,
        material,
        activities,
        support,
        exits,
        return_target_id,
        (requirement_ref, requirement.practice_scope_ref),
        generation_rule,
        ArtifactResolution.RESOLVED,
    )
    fingerprint = semantic_fingerprint(provisional)
    return replace(
        provisional,
        id=f"exercise-instance:{fingerprint}",
        semantic_fingerprint=fingerprint,
    )


def _exercise_ref(value: ExerciseInstance) -> SemanticReference:
    return SemanticReference("exercise-instance", value.id, value.semantic_fingerprint)


def _edge(
    kind: CurriculumEdgeKind,
    source_node_id: str,
    target_node_id: str,
    guard: str,
    precedence: int,
    *,
    return_node_id: str | None = None,
) -> CurriculumGraphEdge:
    payload = (kind.value, source_node_id, target_node_id, guard, precedence, return_node_id)
    return CurriculumGraphEdge(
        derived_id("curriculum-edge", payload),
        kind,
        source_node_id,
        target_node_id,
        None,
        guard,
        None,
        return_node_id,
        precedence,
    )


def _rule(identifier: str) -> RuleReference:
    return RuleReference(
        identifier,
        BRANCH_GENERATOR_VERSION,
        semantic_fingerprint((identifier, BRANCH_GENERATOR_VERSION)),
    )
