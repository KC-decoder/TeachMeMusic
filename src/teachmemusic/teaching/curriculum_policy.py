"""Authoritative deterministic mastery and graph unlock for DEV-009 Task 9D.4."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, replace

from teachmemusic.performance import ObservationDimension

from .contracts import EvidenceContext, SupportState
from .curriculum_contracts import (
    CURRICULUM_CONTRACT_VERSION,
    TEMPO_POLICY_ID,
    AcquisitionGraphSlice,
    ArtifactResolution,
    CurriculumDimensionDecision,
    CurriculumEdgeKind,
    CurriculumEvidenceRecord,
    CurriculumEvidenceResult,
    CurriculumGraphEdge,
    CurriculumGraphNode,
    CurriculumMasteryProjection,
    CurriculumMasteryStatus,
    CurriculumPolicyAction,
    CurriculumUnlockAction,
    CurriculumUnlockDecision,
    ExerciseInstance,
    LastingSkillGraphSlice,
    RejectedCurriculumEdge,
    SemanticReference,
)
from .curriculum_fingerprint import semantic_fingerprint
from .curriculum_validation import (
    require_valid_acquisition_graph_slice,
    require_valid_curriculum_evidence_record,
    require_valid_curriculum_mastery_projection,
    require_valid_curriculum_unlock_decision,
    require_valid_lasting_skill_graph_slice,
)


class CurriculumPolicyError(ValueError):
    """Raised when supplied state cannot produce an authoritative decision."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(f"{code}: {message}")


@dataclass(frozen=True, slots=True)
class CurriculumSupportDecision:
    """One bounded retry, remediation, support, or progression decision."""

    schema_version: str
    id: str
    semantic_fingerprint: str
    policy_identity: str
    graph_ref: SemanticReference
    node_id: str
    exercise_ref: SemanticReference
    projection_ref: SemanticReference
    unlock_ref: SemanticReference
    decision_sequence: int
    mastery_status: CurriculumMasteryStatus
    support_condition_before: str
    support_state_before_ref: SemanticReference
    action: CurriculumPolicyAction
    target_node_id: str
    support_condition_after: str | None
    support_state_after_ref: SemanticReference | None
    retry_count: int
    retry_limit: int
    remediation_count: int
    remediation_limit: int
    reason_code: str
    resolution: ArtifactResolution


def decide_curriculum_support(
    graph: AcquisitionGraphSlice,
    current_node_id: str,
    current_condition: str,
    support_states: tuple[tuple[str, SupportState], ...],
    mastery: CurriculumMasteryProjection,
    unlock: CurriculumUnlockDecision,
    *,
    decision_sequence: int,
    history: tuple[CurriculumSupportDecision, ...] = (),
) -> CurriculumSupportDecision:
    """Apply the frozen finite retry/remediation/support policy to one node."""

    require_valid_acquisition_graph_slice(graph)
    require_valid_curriculum_mastery_projection(mastery)
    require_valid_curriculum_unlock_decision(unlock, mastery, graph)
    node = next((item for item in graph.nodes if item.id == current_node_id), None)
    if node is None or node.exercise_ref is None:
        raise CurriculumPolicyError(
            "TMM-POLICY-NODE-NOT-PLAYABLE",
            "support decisions require one graph-declared playable node",
        )
    exercise = next((item for item in graph.exercises if item.id == node.exercise_ref.id), None)
    if exercise is None or node.exercise_ref != _exercise_ref(exercise):
        raise CurriculumPolicyError(
            "TMM-POLICY-EXERCISE-MISMATCH",
            "support decision exercise is absent or has changed",
        )
    condition_names = tuple(item[0] for item in support_states)
    if condition_names != exercise.support_envelope.permitted_conditions or len(
        condition_names
    ) != len(set(condition_names)):
        raise CurriculumPolicyError(
            "TMM-POLICY-SUPPORT-LATTICE",
            "support states must exactly cover the exercise envelope in declared order",
        )
    support_by_condition = dict(support_states)
    current_support = support_by_condition.get(current_condition)
    if current_support is None:
        raise CurriculumPolicyError(
            "TMM-POLICY-SUPPORT-LATTICE",
            "current support condition is absent from the exercise envelope",
        )
    if (
        mastery.graph_ref != _graph_ref(graph)
        or mastery.node_id != current_node_id
        or mastery.exercise_ref != node.exercise_ref
        or mastery.support_state_ref != _support_ref(current_support)
        or unlock.graph_ref != mastery.graph_ref
        or unlock.current_node_id != current_node_id
        or unlock.projection_ref != _projection_ref(mastery)
    ):
        raise CurriculumPolicyError(
            "TMM-POLICY-SUPPORT-MISMATCH",
            "graph, exercise, projection, unlock, condition, or support identity drifted",
        )
    _require_support_history(graph, node, history, decision_sequence)

    retry_limit = graph.tempo_configuration.acquisition_retry_budget
    remediation_limit = graph.tempo_configuration.remediation_budget
    retry_count = sum(
        item.action is CurriculumPolicyAction.RETRY
        and item.support_condition_before == current_condition
        for item in history
    )
    remediation_count = sum(item.action is CurriculumPolicyAction.REMEDIATE for item in history)
    current_index = condition_names.index(current_condition)
    next_condition: str | None = current_condition
    next_support: SupportState | None = current_support
    target_node_id = current_node_id

    if mastery.status is CurriculumMasteryStatus.INCONCLUSIVE:
        action = CurriculumPolicyAction.INCONCLUSIVE
        reason = "TMM-POLICY-EVIDENCE-INCOMPLETE"
    elif mastery.status is CurriculumMasteryStatus.NOT_MASTERED:
        consecutive_failures = (
            _consecutive_support_results(
                history,
                current_condition,
                CurriculumMasteryStatus.NOT_MASTERED,
            )
            + 1
        )
        if consecutive_failures == 1 and retry_count < retry_limit:
            action = CurriculumPolicyAction.RETRY
            retry_count += 1
            reason = "TMM-POLICY-UNCHANGED-RETRY"
        elif current_index > 0:
            action = CurriculumPolicyAction.STRENGTHEN_SUPPORT
            next_condition = condition_names[current_index - 1]
            next_support = support_by_condition[next_condition]
            reason = "TMM-POLICY-SUPPORT-STRENGTHENED"
        elif remediation_count < remediation_limit:
            remediation_node_id = _remediation_node_id(graph, current_node_id)
            if remediation_node_id is None:
                action = CurriculumPolicyAction.HUMAN_REVIEW
                next_condition = None
                next_support = None
                reason = "TMM-POLICY-REMEDIATION-UNAVAILABLE"
            else:
                action = CurriculumPolicyAction.REMEDIATE
                target_node_id = remediation_node_id
                next_condition = None
                next_support = None
                remediation_count += 1
                reason = "TMM-POLICY-SMALLEST-REMEDIATION"
        else:
            action = CurriculumPolicyAction.HUMAN_REVIEW
            next_condition = None
            next_support = None
            reason = "TMM-POLICY-REMEDIATION-BUDGET-EXHAUSTED"
    elif current_condition != exercise.support_envelope.independent_condition:
        consecutive_passes = (
            _consecutive_support_results(
                history,
                current_condition,
                CurriculumMasteryStatus.MASTERED,
            )
            + 1
        )
        if consecutive_passes < graph.tempo_configuration.stable_performance_passes:
            action = CurriculumPolicyAction.RETRY
            retry_count += 1
            reason = "TMM-POLICY-STABILITY-CONFIRMATION-REQUIRED"
        else:
            action = CurriculumPolicyAction.FADE_SUPPORT
            next_condition = condition_names[current_index + 1]
            next_support = support_by_condition[next_condition]
            reason = "TMM-POLICY-SUPPORT-FADED-ONE-CONDITION"
    elif unlock.action in {
        CurriculumUnlockAction.UNLOCK_SUCCESSOR,
        CurriculumUnlockAction.COMPLETE_NODE,
    }:
        action = CurriculumPolicyAction.PROGRESS
        target_node_id = unlock.next_node_id or current_node_id
        reason = "TMM-POLICY-INDEPENDENT-CONDITION-SUPPORTED"
    else:
        action = CurriculumPolicyAction.INCONCLUSIVE
        reason = unlock.reason_code

    provisional = CurriculumSupportDecision(
        schema_version=CURRICULUM_CONTRACT_VERSION,
        id="curriculum-support-decision:pending",
        semantic_fingerprint="",
        policy_identity=TEMPO_POLICY_ID,
        graph_ref=_graph_ref(graph),
        node_id=current_node_id,
        exercise_ref=node.exercise_ref,
        projection_ref=_projection_ref(mastery),
        unlock_ref=_unlock_ref(unlock),
        decision_sequence=decision_sequence,
        mastery_status=mastery.status,
        support_condition_before=current_condition,
        support_state_before_ref=_support_ref(current_support),
        action=action,
        target_node_id=target_node_id,
        support_condition_after=next_condition,
        support_state_after_ref=(_support_ref(next_support) if next_support is not None else None),
        retry_count=retry_count,
        retry_limit=retry_limit,
        remediation_count=remediation_count,
        remediation_limit=remediation_limit,
        reason_code=reason,
        resolution=ArtifactResolution.RESOLVED,
    )
    decision = replace(
        provisional,
        id=f"curriculum-support-decision:{semantic_fingerprint(provisional)}",
        semantic_fingerprint=semantic_fingerprint(provisional),
    )
    require_valid_curriculum_support_decision(decision, graph, mastery, unlock)
    return decision


def require_valid_curriculum_support_decision(
    decision: CurriculumSupportDecision,
    graph: AcquisitionGraphSlice,
    mastery: CurriculumMasteryProjection,
    unlock: CurriculumUnlockDecision,
) -> None:
    """Fail closed when one support-policy decision loses exact provenance."""

    require_valid_acquisition_graph_slice(graph)
    require_valid_curriculum_mastery_projection(mastery)
    require_valid_curriculum_unlock_decision(unlock, mastery, graph)
    node = next((item for item in graph.nodes if item.id == decision.node_id), None)
    if (
        decision.schema_version != CURRICULUM_CONTRACT_VERSION
        or decision.policy_identity != TEMPO_POLICY_ID
        or decision.graph_ref != _graph_ref(graph)
        or node is None
        or node.exercise_ref is None
        or decision.exercise_ref != node.exercise_ref
        or decision.projection_ref != _projection_ref(mastery)
        or decision.unlock_ref != _unlock_ref(unlock)
        or mastery.node_id != decision.node_id
        or unlock.current_node_id != decision.node_id
    ):
        raise CurriculumPolicyError(
            "TMM-POLICY-SUPPORT-MISMATCH",
            "support decision provenance does not match its exact policy inputs",
        )
    if (
        decision.decision_sequence < 0
        or not decision.support_condition_before
        or not decision.target_node_id
        or decision.retry_count < 0
        or decision.retry_count > decision.retry_limit
        or decision.remediation_count < 0
        or decision.remediation_count > decision.remediation_limit
        or decision.resolution is not ArtifactResolution.RESOLVED
    ):
        raise CurriculumPolicyError(
            "TMM-POLICY-SUPPORT-BOUNDS",
            "support decision sequence, conditions, counters, or resolution are invalid",
        )
    if decision.action in {
        CurriculumPolicyAction.REMEDIATE,
        CurriculumPolicyAction.HUMAN_REVIEW,
    }:
        if (
            decision.support_condition_after is not None
            or decision.support_state_after_ref is not None
        ):
            raise CurriculumPolicyError(
                "TMM-POLICY-SUPPORT-MISMATCH",
                "remediation or review cannot fabricate a next support state",
            )
    elif decision.support_condition_after is None or decision.support_state_after_ref is None:
        raise CurriculumPolicyError(
            "TMM-POLICY-SUPPORT-MISMATCH",
            "same-node or fading decisions require an exact next support state",
        )
    expected_fingerprint = semantic_fingerprint(decision)
    if (
        decision.semantic_fingerprint != expected_fingerprint
        or decision.id != f"curriculum-support-decision:{expected_fingerprint}"
    ):
        raise CurriculumPolicyError(
            "TMM-POLICY-SUPPORT-FINGERPRINT",
            "support decision content identity has drifted",
        )


_CONTEXT_BY_EXIT = {
    "diagnostic": EvidenceContext.ACQUISITION,
    "tempo-diagnostic": EvidenceContext.ACQUISITION,
    "acquisition": EvidenceContext.ACQUISITION,
    "component-acquisition": EvidenceContext.ACQUISITION,
    "passage-application": EvidenceContext.INDEPENDENT,
    "connected-learned-to-date": EvidenceContext.INDEPENDENT,
    "tempo-development": EvidenceContext.INDEPENDENT,
    "coordination-preparation": EvidenceContext.INTEGRATION,
    "integration": EvidenceContext.INTEGRATION,
    "retention": EvidenceContext.RETENTION,
    "transfer": EvidenceContext.TRANSFER,
}

_TRAVERSABLE_SUCCESS_EDGES = frozenset(
    {
        CurriculumEdgeKind.ON_SATISFIED,
        CurriculumEdgeKind.CHECKPOINT_AFTER,
        CurriculumEdgeKind.RETURN_TO,
    }
)


def decide_curriculum_unlock(
    graph: AcquisitionGraphSlice | LastingSkillGraphSlice,
    current_node_id: str,
    support: SupportState,
    evidence_records: tuple[CurriculumEvidenceRecord, ...],
    *,
    attempt_sequence: tuple[str, ...] = (),
    previously_satisfied_node_ids: tuple[str, ...] = (),
) -> tuple[CurriculumMasteryProjection, CurriculumUnlockDecision]:
    """Project exact factual evidence and select at most one declared successor.

    ``evidence_records`` is intentionally node-local. Supplying evidence for a
    different requirement, scope, support state, or context fails closed rather
    than being silently ignored.
    """

    projection = project_curriculum_mastery(
        graph,
        current_node_id,
        support,
        evidence_records,
        attempt_sequence=attempt_sequence,
    )
    node = next(item for item in graph.nodes if item.id == current_node_id)
    decision = _select_unlock(
        graph,
        node,
        projection,
        previously_satisfied_node_ids,
    )
    require_valid_curriculum_unlock_decision(decision, projection, graph)
    return projection, decision


def project_curriculum_mastery(
    graph: AcquisitionGraphSlice | LastingSkillGraphSlice,
    current_node_id: str,
    support: SupportState,
    evidence_records: tuple[CurriculumEvidenceRecord, ...],
    *,
    attempt_sequence: tuple[str, ...] = (),
) -> CurriculumMasteryProjection:
    """Project node-local learner state without selecting a graph action."""

    if any(not isinstance(item, CurriculumEvidenceRecord) for item in evidence_records):
        raise CurriculumPolicyError(
            "TMM-POLICY-EVIDENCE-TYPE",
            "mastery projection accepts curriculum evidence records only",
        )
    _require_valid_graph(graph)
    if graph.resolution is not ArtifactResolution.RESOLVED:
        raise CurriculumPolicyError(
            "TMM-POLICY-GRAPH-UNRESOLVED",
            "only a resolved curriculum graph can authorize progression",
        )
    nodes = {item.id: item for item in graph.nodes}
    node = nodes.get(current_node_id)
    if node is None:
        raise CurriculumPolicyError(
            "TMM-POLICY-NODE-MISSING",
            "current node is absent from the supplied graph",
        )
    exercise = _exercise_for_node(graph, node)
    context = _evidence_context(exercise)
    support_ref = SemanticReference("support-state", support.id, semantic_fingerprint(support))
    required_dimensions = _required_dimensions(exercise)
    minimum_state = _minimum_state(exercise)
    component_scope_refs = _require_compatible_records(
        evidence_records,
        node,
        exercise,
        context,
        support_ref,
        required_dimensions,
    )
    projection = _project_mastery(
        graph,
        node,
        exercise,
        context,
        support_ref,
        component_scope_refs,
        required_dimensions,
        minimum_state,
        evidence_records,
        attempt_sequence,
    )
    require_valid_curriculum_mastery_projection(projection)
    return projection


def _require_valid_graph(graph: AcquisitionGraphSlice | LastingSkillGraphSlice) -> None:
    if isinstance(graph, AcquisitionGraphSlice):
        require_valid_acquisition_graph_slice(graph)
    else:
        require_valid_lasting_skill_graph_slice(graph)


def _exercise_for_node(
    graph: AcquisitionGraphSlice | LastingSkillGraphSlice,
    node: CurriculumGraphNode,
) -> ExerciseInstance:
    if node.exercise_ref is None or node.requirement_ref is None or node.primitive_ref is None:
        raise CurriculumPolicyError(
            "TMM-POLICY-NODE-NOT-PLAYABLE",
            "mastery requires a playable node with exact requirement and primitive references",
        )
    exercise = next((item for item in graph.exercises if item.id == node.exercise_ref.id), None)
    if exercise is None or exercise.semantic_fingerprint != node.exercise_ref.semantic_fingerprint:
        raise CurriculumPolicyError(
            "TMM-POLICY-EXERCISE-MISMATCH",
            "node exercise is absent or has changed",
        )
    if (
        exercise.requirement_ref != node.requirement_ref
        or exercise.practice_scope_ref != node.scope_ref
    ):
        raise CurriculumPolicyError(
            "TMM-POLICY-EXERCISE-MISMATCH",
            "node and exercise target different requirement or scope identities",
        )
    return exercise


def _evidence_context(exercise: ExerciseInstance) -> EvidenceContext:
    exit_contexts = {item.evidence_context for item in exercise.required_evidence_exits}
    if len(exit_contexts) != 1:
        raise CurriculumPolicyError(
            "TMM-POLICY-CONTEXT-AMBIGUOUS",
            "all exits of one playable node must use one evidence context",
        )
    name = next(iter(exit_contexts))
    try:
        return _CONTEXT_BY_EXIT[name]
    except KeyError as error:
        raise CurriculumPolicyError(
            "TMM-POLICY-CONTEXT-UNSUPPORTED",
            f"unsupported exercise evidence context {name!r}",
        ) from error


def _required_dimensions(exercise: ExerciseInstance) -> tuple[ObservationDimension, ...]:
    dimensions: list[ObservationDimension] = []
    for exit_requirement in exercise.required_evidence_exits:
        try:
            dimension = ObservationDimension(exit_requirement.dimension)
        except ValueError as error:
            raise CurriculumPolicyError(
                "TMM-POLICY-DIMENSION-UNSUPPORTED",
                f"unsupported required dimension {exit_requirement.dimension!r}",
            ) from error
        if dimension in dimensions:
            raise CurriculumPolicyError(
                "TMM-POLICY-DIMENSION-DUPLICATE",
                "exercise repeats a required evidence dimension",
            )
        dimensions.append(dimension)
    if not dimensions:
        raise CurriculumPolicyError(
            "TMM-POLICY-DIMENSION-MISSING",
            "playable node has no required evidence dimensions",
        )
    return tuple(dimensions)


def _minimum_state(exercise: ExerciseInstance) -> str:
    states = {item.minimum_state for item in exercise.required_evidence_exits}
    if len(states) != 1:
        raise CurriculumPolicyError(
            "TMM-POLICY-MINIMUM-STATE-AMBIGUOUS",
            "all exits of one playable node must use one minimum evidence state",
        )
    state = next(iter(states))
    if state not in {
        "diagnostic-observed",
        "stable-supported",
        "independent-in-session",
        "supported",
    }:
        raise CurriculumPolicyError(
            "TMM-POLICY-MINIMUM-STATE-UNSUPPORTED",
            f"unsupported minimum evidence state {state!r}",
        )
    return state


def _require_compatible_records(
    records: tuple[CurriculumEvidenceRecord, ...],
    node: CurriculumGraphNode,
    exercise: ExerciseInstance,
    context: EvidenceContext,
    support_ref: SemanticReference,
    required_dimensions: tuple[ObservationDimension, ...],
) -> tuple[SemanticReference, ...]:
    component_scope_refs: tuple[SemanticReference, ...] | None = None
    expected_target_ref: SemanticReference | None = None
    for record in records:
        require_valid_curriculum_evidence_record(record)
        if (
            record.requirement_ref != exercise.requirement_ref
            or record.primitive_ref != node.primitive_ref
            or record.practice_scope_ref != exercise.practice_scope_ref
            or record.evidence_context is not context
            or record.support_state_ref != support_ref
            or record.dimension not in required_dimensions
        ):
            raise CurriculumPolicyError(
                "TMM-POLICY-EVIDENCE-INCOMPATIBLE",
                "record differs from the current node, scope, support, context, or exits",
            )
        if expected_target_ref is None:
            expected_target_ref = record.expected_target_ref
            component_scope_refs = record.component_scope_refs
        elif (
            record.expected_target_ref != expected_target_ref
            or record.component_scope_refs != component_scope_refs
        ):
            raise CurriculumPolicyError(
                "TMM-POLICY-EVIDENCE-INCOMPATIBLE",
                "records do not share one exact expected target and component topology",
            )
    return component_scope_refs or ()


def _project_mastery(
    graph: AcquisitionGraphSlice | LastingSkillGraphSlice,
    node: CurriculumGraphNode,
    exercise: ExerciseInstance,
    context: EvidenceContext,
    support_ref: SemanticReference,
    component_scope_refs: tuple[SemanticReference, ...],
    required_dimensions: tuple[ObservationDimension, ...],
    minimum_state: str,
    records: tuple[CurriculumEvidenceRecord, ...],
    attempt_sequence: tuple[str, ...],
) -> CurriculumMasteryProjection:
    if node.primitive_ref is None:
        raise CurriculumPolicyError(
            "TMM-POLICY-NODE-NOT-PLAYABLE",
            "mastery requires an exact primitive reference",
        )
    by_attempt: dict[str, dict[ObservationDimension, list[CurriculumEvidenceRecord]]] = defaultdict(
        lambda: defaultdict(list)
    )
    for record in records:
        by_attempt[record.attempt_id][record.dimension].append(record)

    record_attempt_ids = tuple(dict.fromkeys(item.attempt_id for item in records))
    if minimum_state == "stable-supported" and records and not attempt_sequence:
        raise CurriculumPolicyError(
            "TMM-POLICY-ATTEMPT-SEQUENCE-REQUIRED",
            "stable-supported mastery requires an explicit complete attempt sequence",
        )
    if attempt_sequence:
        if len(attempt_sequence) != len(set(attempt_sequence)) or set(attempt_sequence) != set(
            record_attempt_ids
        ):
            raise CurriculumPolicyError(
                "TMM-POLICY-ATTEMPT-SEQUENCE-INCOMPATIBLE",
                "attempt sequence must name every supplied attempt exactly once",
            )
        evaluated_attempt_ids = attempt_sequence
    else:
        evaluated_attempt_ids = record_attempt_ids

    complete_passing_attempts = tuple(
        attempt_id
        for attempt_id in evaluated_attempt_ids
        if all(
            dimension in by_attempt[attempt_id]
            and all(
                record.result is CurriculumEvidenceResult.MATCHED
                for record in by_attempt[attempt_id][dimension]
            )
            for dimension in required_dimensions
        )
    )
    if minimum_state == "stable-supported":
        mastered = len(evaluated_attempt_ids) >= 2 and all(
            attempt_id in complete_passing_attempts for attempt_id in evaluated_attempt_ids[-2:]
        )
    else:
        mastered = bool(evaluated_attempt_ids) and (
            evaluated_attempt_ids[-1] in complete_passing_attempts
        )
    current_attempt_id = evaluated_attempt_ids[-1] if evaluated_attempt_ids else None
    current_records = tuple(record for record in records if record.attempt_id == current_attempt_id)
    if mastered:
        status = CurriculumMasteryStatus.MASTERED
    elif any(record.result is CurriculumEvidenceResult.DISCREPANCY for record in current_records):
        status = CurriculumMasteryStatus.NOT_MASTERED
    else:
        status = CurriculumMasteryStatus.INCONCLUSIVE

    dimension_decisions: list[CurriculumDimensionDecision] = []
    for dimension in required_dimensions:
        selected = tuple(record for record in current_records if record.dimension is dimension)
        passing_attempts = tuple(
            attempt_id
            for attempt_id in evaluated_attempt_ids
            if dimension in by_attempt[attempt_id]
            and all(
                record.result is CurriculumEvidenceResult.MATCHED
                for record in by_attempt[attempt_id][dimension]
            )
        )
        if selected and all(
            record.result is CurriculumEvidenceResult.MATCHED for record in selected
        ):
            result: CurriculumEvidenceResult | None = CurriculumEvidenceResult.MATCHED
            reason = "TMM-POLICY-DIMENSION-MATCHED"
        elif any(record.result is CurriculumEvidenceResult.DISCREPANCY for record in selected):
            result = CurriculumEvidenceResult.DISCREPANCY
            reason = "TMM-POLICY-DIMENSION-DISCREPANCY"
        elif selected:
            result = CurriculumEvidenceResult.INCONCLUSIVE
            reason = "TMM-POLICY-DIMENSION-INCONCLUSIVE"
        else:
            result = None
            reason = "TMM-POLICY-DIMENSION-MISSING"
        dimension_decisions.append(
            CurriculumDimensionDecision(
                dimension,
                result,
                tuple(item.id for item in selected),
                passing_attempts,
                reason,
            )
        )

    graph_ref = _graph_ref(graph)
    provisional = CurriculumMasteryProjection(
        CURRICULUM_CONTRACT_VERSION,
        "curriculum-mastery-projection:pending",
        "",
        graph_ref,
        node.id,
        SemanticReference("exercise-instance", exercise.id, exercise.semantic_fingerprint),
        exercise.requirement_ref,
        node.primitive_ref,
        exercise.practice_scope_ref,
        component_scope_refs,
        context,
        support_ref,
        required_dimensions,
        tuple(dimension_decisions),
        evaluated_attempt_ids,
        complete_passing_attempts,
        minimum_state,
        status,
        ArtifactResolution.RESOLVED,
    )
    fingerprint = semantic_fingerprint(provisional)
    return replace(
        provisional,
        id=f"curriculum-mastery-projection:{fingerprint}",
        semantic_fingerprint=fingerprint,
    )


def _select_unlock(
    graph: AcquisitionGraphSlice | LastingSkillGraphSlice,
    node: CurriculumGraphNode,
    projection: CurriculumMasteryProjection,
    previously_satisfied_node_ids: tuple[str, ...],
) -> CurriculumUnlockDecision:
    if len(previously_satisfied_node_ids) != len(set(previously_satisfied_node_ids)):
        raise CurriculumPolicyError(
            "TMM-POLICY-SATISFIED-NODE-DUPLICATE",
            "previously satisfied node identities must be unique",
        )
    known_nodes = {item.id: item for item in graph.nodes}
    if any(item not in known_nodes for item in previously_satisfied_node_ids):
        raise CurriculumPolicyError(
            "TMM-POLICY-SATISFIED-NODE-FOREIGN",
            "previously satisfied node is absent from the graph",
        )

    eligible: list[CurriculumGraphEdge] = []
    rejected: list[RejectedCurriculumEdge] = []
    current_dependencies_met = set(node.component_node_ids) <= set(previously_satisfied_node_ids)
    if projection.status is CurriculumMasteryStatus.MASTERED:
        satisfied = {*previously_satisfied_node_ids, node.id}
        outgoing = tuple(
            item
            for item in graph.edges
            if item.source_node_id == node.id and item.kind in _TRAVERSABLE_SUCCESS_EDGES
        )
        for edge in outgoing:
            target = known_nodes[edge.target_node_id]
            if not current_dependencies_met:
                rejected.append(
                    RejectedCurriculumEdge(edge.id, "TMM-POLICY-CURRENT-DEPENDENCIES-INCOMPLETE")
                )
            elif not set(target.component_node_ids) <= satisfied:
                rejected.append(RejectedCurriculumEdge(edge.id, "TMM-POLICY-COMPONENTS-INCOMPLETE"))
            else:
                eligible.append(edge)
        eligible.sort(key=lambda item: (item.precedence, item.kind.value, item.id))

    if projection.status is CurriculumMasteryStatus.MASTERED and not current_dependencies_met:
        action = CurriculumUnlockAction.HOLD_FOR_EVIDENCE
        reason = "TMM-POLICY-CURRENT-DEPENDENCIES-INCOMPLETE"
        selected = None
    elif projection.status is CurriculumMasteryStatus.NOT_MASTERED:
        action = CurriculumUnlockAction.RETRY_CURRENT
        reason = "TMM-POLICY-RETRY-REQUIRED"
        selected = None
    elif projection.status is CurriculumMasteryStatus.INCONCLUSIVE:
        action = CurriculumUnlockAction.HOLD_FOR_EVIDENCE
        reason = "TMM-POLICY-EVIDENCE-INCOMPLETE"
        selected = None
    elif eligible:
        action = CurriculumUnlockAction.UNLOCK_SUCCESSOR
        reason = "TMM-POLICY-GRAPH-SUCCESSOR-UNLOCKED"
        selected = eligible[0]
        for edge in eligible[1:]:
            rejected.append(RejectedCurriculumEdge(edge.id, "TMM-POLICY-LOWER-PRECEDENCE"))
    else:
        action = CurriculumUnlockAction.COMPLETE_NODE
        reason = "TMM-POLICY-COMPONENTS-INCOMPLETE" if rejected else "TMM-POLICY-NODE-COMPLETE"
        selected = None

    graph_ref = _graph_ref(graph)
    projection_ref = SemanticReference(
        "curriculum-mastery-projection",
        projection.id,
        projection.semantic_fingerprint,
    )
    provisional = CurriculumUnlockDecision(
        CURRICULUM_CONTRACT_VERSION,
        "curriculum-unlock-decision:pending",
        "",
        TEMPO_POLICY_ID,
        graph_ref,
        node.id,
        projection_ref,
        tuple(previously_satisfied_node_ids),
        tuple(item.id for item in eligible),
        tuple(rejected),
        selected.id if selected is not None else None,
        selected.target_node_id if selected is not None else None,
        action,
        reason,
        ArtifactResolution.RESOLVED,
    )
    fingerprint = semantic_fingerprint(provisional)
    return replace(
        provisional,
        id=f"curriculum-unlock-decision:{fingerprint}",
        semantic_fingerprint=fingerprint,
    )


def _graph_ref(
    graph: AcquisitionGraphSlice | LastingSkillGraphSlice,
) -> SemanticReference:
    artifact_type = (
        "acquisition-graph-slice"
        if isinstance(graph, AcquisitionGraphSlice)
        else "lasting-skill-graph-slice"
    )
    return SemanticReference(artifact_type, graph.id, graph.semantic_fingerprint)


def _exercise_ref(exercise: ExerciseInstance) -> SemanticReference:
    return SemanticReference(
        "exercise-instance",
        exercise.id,
        exercise.semantic_fingerprint,
    )


def _projection_ref(projection: CurriculumMasteryProjection) -> SemanticReference:
    return SemanticReference(
        "curriculum-mastery-projection",
        projection.id,
        projection.semantic_fingerprint,
    )


def _unlock_ref(unlock: CurriculumUnlockDecision) -> SemanticReference:
    return SemanticReference(
        "curriculum-unlock-decision",
        unlock.id,
        unlock.semantic_fingerprint,
    )


def _support_ref(support: SupportState) -> SemanticReference:
    return SemanticReference(
        "support-state",
        support.id,
        semantic_fingerprint(support),
    )


def _require_support_history(
    graph: AcquisitionGraphSlice,
    node: CurriculumGraphNode,
    history: tuple[CurriculumSupportDecision, ...],
    decision_sequence: int,
) -> None:
    if decision_sequence != len(history):
        raise CurriculumPolicyError(
            "TMM-POLICY-SUPPORT-SEQUENCE",
            "decision sequence must follow the complete supplied support history",
        )
    expected_graph_ref = _graph_ref(graph)
    for index, decision in enumerate(history):
        if (
            decision.decision_sequence != index
            or decision.graph_ref != expected_graph_ref
            or decision.node_id != node.id
            or decision.exercise_ref != node.exercise_ref
            or decision.policy_identity != TEMPO_POLICY_ID
            or decision.semantic_fingerprint != semantic_fingerprint(decision)
            or decision.id != f"curriculum-support-decision:{decision.semantic_fingerprint}"
        ):
            raise CurriculumPolicyError(
                "TMM-POLICY-SUPPORT-HISTORY",
                "support history is reordered, detached, or content-invalid",
            )


def _consecutive_support_results(
    history: tuple[CurriculumSupportDecision, ...],
    condition: str,
    status: CurriculumMasteryStatus,
) -> int:
    count = 0
    for decision in reversed(history):
        if decision.support_condition_before != condition or decision.mastery_status is not status:
            break
        count += 1
    return count


def _remediation_node_id(
    graph: AcquisitionGraphSlice,
    application_node_id: str,
) -> str | None:
    branch = next(
        (item for item in graph.branches if item.application_node_id == application_node_id),
        None,
    )
    return branch.prerequisite_node_id if branch is not None else None
