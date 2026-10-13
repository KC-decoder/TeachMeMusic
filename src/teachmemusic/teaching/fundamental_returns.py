"""Exact prerequisite-to-piece handoff for DEV-009 Task 9G.4."""

from __future__ import annotations

from dataclasses import replace

from .curriculum_contracts import (
    CURRICULUM_CONTRACT_VERSION,
    FUNDAMENTAL_RETURN_VERSION,
    AcquisitionGraphSlice,
    ActivityForm,
    ArtifactResolution,
    CurriculumEdgeKind,
    CurriculumFundamentalDemonstration,
    CurriculumFundamentalExplanation,
    CurriculumFundamentalPractice,
    CurriculumMasteryProjection,
    CurriculumMasteryStatus,
    CurriculumPassagePresentation,
    CurriculumPieceReturn,
    CurriculumUnlockAction,
    CurriculumUnlockDecision,
    PassageRequirementSet,
    PrerequisiteBranchSet,
    RuleReference,
    SemanticReference,
)
from .curriculum_fingerprint import semantic_fingerprint
from .curriculum_validation import (
    require_valid_acquisition_graph_slice,
    require_valid_curriculum_fundamental_practice,
    require_valid_curriculum_mastery_projection,
    require_valid_curriculum_piece_return,
    require_valid_curriculum_unlock_decision,
)

_RETURN_RULE_ID = "FUNDAMENTAL-RETURN-RULE-001"


class CurriculumPieceReturnError(ValueError):
    """Raised when a prerequisite cannot return to its exact source passage."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(f"{code}: {message}")


def build_curriculum_piece_return(
    requirements: PassageRequirementSet,
    branches: PrerequisiteBranchSet,
    graph: AcquisitionGraphSlice,
    presentation: CurriculumPassagePresentation,
    explanation: CurriculumFundamentalExplanation,
    demonstration: CurriculumFundamentalDemonstration,
    practice: CurriculumFundamentalPractice,
    mastery: CurriculumMasteryProjection,
    decision: CurriculumUnlockDecision,
) -> CurriculumPieceReturn:
    """Build a handoff only from an authoritative exact return decision.

    This function consumes mastery and policy artifacts; it never derives
    mastery, chooses a successor, or treats demonstration playback as evidence.
    """

    require_valid_acquisition_graph_slice(graph)
    require_valid_curriculum_fundamental_practice(
        practice,
        explanation,
        demonstration,
        requirements,
        branches,
        presentation,
    )
    require_valid_curriculum_mastery_projection(mastery)
    require_valid_curriculum_unlock_decision(decision, mastery, graph)
    if graph.resolution is not ArtifactResolution.RESOLVED:
        raise CurriculumPieceReturnError(
            "TMM-RETURN-GRAPH-UNRESOLVED",
            "only a resolved curriculum graph can authorize a piece return",
        )

    branch = next(
        (
            item
            for item in branches.branches
            if item.requirement_ref.id == practice.requirement_ref.id
        ),
        None,
    )
    if (
        branch is None
        or branch.prerequisite_node_id != practice.prerequisite_node_id
        or branch.application_node_id != practice.return_node_id
    ):
        raise CurriculumPieceReturnError(
            "TMM-RETURN-BRANCH-MISMATCH",
            "practice is detached from its declared prerequisite branch",
        )

    return_edges = tuple(
        edge
        for edge in graph.edges
        if edge.kind is CurriculumEdgeKind.RETURN_TO
        and edge.source_node_id == practice.prerequisite_node_id
    )
    if (
        len(return_edges) != 1
        or return_edges[0].target_node_id != practice.return_node_id
        or return_edges[0].return_node_id != practice.return_node_id
    ):
        raise CurriculumPieceReturnError(
            "TMM-RETURN-EDGE-MISMATCH",
            "the graph does not contain one exact prerequisite-to-application return",
        )
    return_edge = return_edges[0]
    if (
        mastery.status is not CurriculumMasteryStatus.MASTERED
        or mastery.node_id != practice.prerequisite_node_id
        or mastery.exercise_ref != practice.prerequisite_exercise_ref
        or mastery.requirement_ref != practice.requirement_ref
        or mastery.primitive_ref != practice.primitive_ref
        or mastery.practice_scope_ref != practice.practice_scope_ref
    ):
        raise CurriculumPieceReturnError(
            "TMM-RETURN-MASTERY-MISMATCH",
            "mastery does not authorize return from this exact prerequisite",
        )
    if (
        decision.action is not CurriculumUnlockAction.UNLOCK_SUCCESSOR
        or decision.current_node_id != practice.prerequisite_node_id
        or decision.selected_edge_id != return_edge.id
        or decision.next_node_id != practice.return_node_id
    ):
        raise CurriculumPieceReturnError(
            "TMM-RETURN-DECISION-MISMATCH",
            "the policy did not select this exact return edge",
        )

    exercise_by_id = {item.id: item for item in branches.exercises}
    prerequisite = exercise_by_id.get(practice.prerequisite_exercise_ref.id)
    application_node = next(
        (item for item in branches.nodes if item.id == practice.return_node_id),
        None,
    )
    application = (
        exercise_by_id.get(application_node.exercise_ref.id)
        if application_node is not None and application_node.exercise_ref is not None
        else None
    )
    reconnect = (
        tuple(
            activity
            for activity in prerequisite.activity_sequence
            if activity.form is ActivityForm.RECONNECT
        )
        if prerequisite is not None
        else ()
    )
    if (
        prerequisite is None
        or application is None
        or application_node is None
        or application_node.exercise_ref is None
        or len(reconnect) != 1
        or reconnect[0].evidence_producing
        or prerequisite.return_target_id != application_node.id
        or application.material.practice_scope_ref != practice.practice_scope_ref
        or application.material.active_target_ids != presentation.active_target_ids
    ):
        raise CurriculumPieceReturnError(
            "TMM-RETURN-APPLICATION-MISMATCH",
            "the return target is not the exact application exercise and source passage",
        )

    evidence_record_ids = tuple(
        dict.fromkeys(
            record_id
            for dimension in mastery.dimension_decisions
            for record_id in dimension.evidence_record_ids
        )
    )
    if not mastery.complete_passing_attempt_ids or not evidence_record_ids:
        raise CurriculumPieceReturnError(
            "TMM-RETURN-EVIDENCE-INCOMPLETE",
            "a return requires passing attempts and their authoritative evidence records",
        )

    rule = RuleReference(
        _RETURN_RULE_ID,
        FUNDAMENTAL_RETURN_VERSION,
        semantic_fingerprint((_RETURN_RULE_ID, FUNDAMENTAL_RETURN_VERSION)),
    )
    provisional = CurriculumPieceReturn(
        schema_version=CURRICULUM_CONTRACT_VERSION,
        id="curriculum-piece-return:pending",
        semantic_fingerprint="",
        analysis_id=practice.analysis_id,
        package_id=practice.package_id,
        score_id=practice.score_id,
        practice_ref=SemanticReference(
            "curriculum-fundamental-practice",
            practice.id,
            practice.semantic_fingerprint,
        ),
        requirement_ref=practice.requirement_ref,
        primitive_ref=practice.primitive_ref,
        practice_scope_ref=practice.practice_scope_ref,
        presentation_ref=practice.presentation_ref,
        prerequisite_exercise_ref=practice.prerequisite_exercise_ref,
        application_exercise_ref=application_node.exercise_ref,
        graph_ref=mastery.graph_ref,
        mastery_projection_ref=SemanticReference(
            "curriculum-mastery-projection",
            mastery.id,
            mastery.semantic_fingerprint,
        ),
        unlock_decision_ref=SemanticReference(
            "curriculum-unlock-decision",
            decision.id,
            decision.semantic_fingerprint,
        ),
        support_state_ref=mastery.support_state_ref,
        prerequisite_node_id=practice.prerequisite_node_id,
        return_node_id=practice.return_node_id,
        return_edge_id=return_edge.id,
        reconnect_activity_id=reconnect[0].id,
        completed_attempt_ids=mastery.complete_passing_attempt_ids,
        evidence_record_ids=evidence_record_ids,
        active_event_ids=presentation.active_target_ids,
        generation_rule=rule,
        diagnostics=(),
        resolution=ArtifactResolution.RESOLVED,
    )
    fingerprint = semantic_fingerprint(provisional)
    result = replace(
        provisional,
        id=f"curriculum-piece-return:{fingerprint}",
        semantic_fingerprint=fingerprint,
    )
    require_valid_curriculum_piece_return(
        result,
        practice,
        mastery,
        decision,
        branches,
        graph,
        presentation,
    )
    return result
