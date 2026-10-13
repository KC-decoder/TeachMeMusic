"""Pre-decision experimental state snapshots for DEV-009 Task 9I.1."""

from __future__ import annotations

from dataclasses import replace
from fractions import Fraction
from typing import Protocol

from teachmemusic.performance import PERFORMANCE_CONTRACT_VERSION, Observation

from .contracts import EVIDENCE_ARCHIVE_CONTRACT_VERSION, SupportState
from .curriculum_contracts import (
    ACTION_INVENTORY_VERSION,
    ACTION_SELECTION_VERSION,
    CURRICULUM_CONTRACT_VERSION,
    DECISION_SNAPSHOT_VERSION,
    EXPERIMENT_MANIFEST_VERSION,
    TEMPO_POLICY_ID,
    TRANSITION_RESULT_VERSION,
    AcquisitionGraphSlice,
    ArtifactResolution,
    CurriculumActionCandidate,
    CurriculumActionEligibility,
    CurriculumActionInventory,
    CurriculumActionSelection,
    CurriculumBudgetCounter,
    CurriculumDecisionSnapshot,
    CurriculumEdgeKind,
    CurriculumEvidenceRecord,
    CurriculumExperimentManifest,
    CurriculumExperimentStatus,
    CurriculumGraphEdge,
    CurriculumGraphNode,
    CurriculumGuardResult,
    CurriculumLearningOutcome,
    CurriculumMasteryProjection,
    CurriculumMasteryStatus,
    CurriculumNodeKind,
    CurriculumPolicyAction,
    CurriculumResearchReward,
    CurriculumTransitionResult,
    SemanticReference,
)
from .curriculum_fingerprint import derived_id, semantic_fingerprint
from .curriculum_validation import (
    require_valid_acquisition_graph_slice,
    require_valid_curriculum_action_inventory,
    require_valid_curriculum_action_selection,
    require_valid_curriculum_decision_snapshot,
    require_valid_curriculum_evidence_record,
    require_valid_curriculum_experiment_manifest,
    require_valid_curriculum_learning_outcome,
    require_valid_curriculum_mastery_projection,
    require_valid_curriculum_research_reward,
    require_valid_curriculum_transition_result,
)

_ACTIONABLE_EDGE_KINDS = frozenset(
    {
        CurriculumEdgeKind.ON_SATISFIED,
        CurriculumEdgeKind.CHECKPOINT_AFTER,
        CurriculumEdgeKind.RETURN_TO,
    }
)


class CurriculumTrajectoryError(ValueError):
    """Raised when policy knowledge cannot form one exact snapshot."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(f"{code}: {message}")


class _Identified(Protocol):
    @property
    def id(self) -> str: ...


def build_curriculum_decision_snapshot(
    graph: AcquisitionGraphSlice,
    current_node_id: str,
    support: SupportState,
    mastery: CurriculumMasteryProjection,
    evidence_records: tuple[CurriculumEvidenceRecord, ...],
    observations: tuple[Observation, ...],
    *,
    run_id: str,
    learner_context_id: str,
    decision_sequence: int,
    evidence_snapshot_sequence: int,
    previously_satisfied_node_ids: tuple[str, ...] = (),
    budget_state: tuple[CurriculumBudgetCounter, ...] = (),
) -> CurriculumDecisionSnapshot:
    """Freeze exactly what the deterministic policy knows before selecting an action."""

    if any(not isinstance(item, CurriculumEvidenceRecord) for item in evidence_records):
        raise CurriculumTrajectoryError(
            "TMM-POLICY-SNAPSHOT-EVIDENCE-TYPE",
            "decision snapshots accept curriculum evidence records only",
        )
    if any(not isinstance(item, Observation) for item in observations):
        raise CurriculumTrajectoryError(
            "TMM-POLICY-SNAPSHOT-OBSERVATION-TYPE",
            "decision snapshots accept factual performance observations only",
        )
    require_valid_acquisition_graph_slice(graph)
    require_valid_curriculum_mastery_projection(mastery)
    for record in evidence_records:
        require_valid_curriculum_evidence_record(record)

    graph_ref = _ref("acquisition-graph-slice", graph)
    if mastery.graph_ref != graph_ref or mastery.node_id != current_node_id:
        raise CurriculumTrajectoryError(
            "TMM-POLICY-SNAPSHOT-MISMATCH",
            "mastery does not belong to the supplied graph and current node",
        )
    node = next((item for item in graph.nodes if item.id == current_node_id), None)
    if node is None or node.exercise_ref is None:
        raise CurriculumTrajectoryError(
            "TMM-POLICY-SNAPSHOT-MISMATCH",
            "current node is absent or does not identify one playable exercise",
        )
    exercise = next((item for item in graph.exercises if item.id == node.exercise_ref.id), None)
    if exercise is None or _ref("exercise-instance", exercise) != node.exercise_ref:
        raise CurriculumTrajectoryError(
            "TMM-POLICY-SNAPSHOT-MISMATCH",
            "current-node exercise is absent or has changed",
        )
    if (
        mastery.exercise_ref != node.exercise_ref
        or mastery.requirement_ref != exercise.requirement_ref
        or mastery.practice_scope_ref != exercise.practice_scope_ref
        or mastery.primitive_ref != node.primitive_ref
        or mastery.support_state_ref != _ref("support-state", support)
    ):
        raise CurriculumTrajectoryError(
            "TMM-POLICY-SNAPSHOT-MISMATCH",
            "scope, requirement, primitive, exercise, or support identity has drifted",
        )

    evidence_ids = tuple(item.id for item in evidence_records)
    if any(
        record.requirement_ref != mastery.requirement_ref
        or record.primitive_ref != mastery.primitive_ref
        or record.practice_scope_ref != mastery.practice_scope_ref
        or record.component_scope_refs != mastery.component_scope_refs
        or record.support_state_ref != mastery.support_state_ref
        or record.evidence_context is not mastery.evidence_context
        or record.dimension not in mastery.required_dimensions
        for record in evidence_records
    ):
        raise CurriculumTrajectoryError(
            "TMM-POLICY-SNAPSHOT-MISMATCH",
            "an evidence record is outside the current mastery state",
        )
    projected_evidence_ids = tuple(
        dict.fromkeys(
            identifier
            for decision in mastery.dimension_decisions
            for identifier in decision.evidence_record_ids
        )
    )
    if not set(projected_evidence_ids) <= set(evidence_ids):
        raise CurriculumTrajectoryError(
            "TMM-POLICY-SNAPSHOT-MISMATCH",
            "mastery evidence is missing from the supplied snapshot",
        )
    if tuple(dict.fromkeys(item.attempt_id for item in evidence_records)) != (
        mastery.evaluated_attempt_ids
    ):
        raise CurriculumTrajectoryError(
            "TMM-POLICY-SNAPSHOT-MISMATCH",
            "attempt order differs from the mastery projection",
        )

    observation_by_id = {item.id: item for item in observations}
    if len(observation_by_id) != len(observations):
        raise CurriculumTrajectoryError(
            "TMM-CONTRACT-DUPLICATE-ID",
            "observation identifiers repeat",
        )
    referenced_observation_ids = {
        identifier
        for record in evidence_records
        for identifier in (*record.observation_ids, *record.context_observation_ids)
    }
    if not referenced_observation_ids <= observation_by_id.keys():
        raise CurriculumTrajectoryError(
            "TMM-POLICY-SNAPSHOT-MISMATCH",
            "an evidence observation is missing from the supplied snapshot",
        )
    if any(item.attempt_id not in mastery.evaluated_attempt_ids for item in observations):
        raise CurriculumTrajectoryError(
            "TMM-POLICY-SNAPSHOT-MISMATCH",
            "an observation belongs to an attempt outside the decision state",
        )

    node_ids = {item.id for item in graph.nodes}
    if (
        len(set(previously_satisfied_node_ids)) != len(previously_satisfied_node_ids)
        or not set(previously_satisfied_node_ids) <= node_ids
        or current_node_id in previously_satisfied_node_ids
    ):
        raise CurriculumTrajectoryError(
            "TMM-POLICY-SNAPSHOT-MISMATCH",
            "previously satisfied nodes are duplicate, foreign, or include the current node",
        )

    evidence_refs = tuple(_ref("curriculum-evidence-record", item) for item in evidence_records)
    observation_refs = tuple(_ref("performance-observation", item) for item in observations)
    evidence_fingerprint = semantic_fingerprint(
        (
            evidence_snapshot_sequence,
            evidence_refs,
            observation_refs,
            mastery.evaluated_attempt_ids,
        )
    )
    material = exercise.material
    provisional = CurriculumDecisionSnapshot(
        schema_version=CURRICULUM_CONTRACT_VERSION,
        id="curriculum-decision-snapshot:pending",
        semantic_fingerprint="",
        snapshot_version=DECISION_SNAPSHOT_VERSION,
        run_id=run_id,
        learner_context_id=learner_context_id,
        decision_sequence=decision_sequence,
        score_package_digest=material.score_package_digest,
        score_id=material.score_id,
        graph_ref=graph_ref,
        current_node_id=current_node_id,
        exercise_ref=node.exercise_ref,
        requirement_ref=mastery.requirement_ref,
        primitive_ref=mastery.primitive_ref,
        practice_scope_ref=mastery.practice_scope_ref,
        component_scope_refs=mastery.component_scope_refs,
        support_state_ref=mastery.support_state_ref,
        policy_identity=TEMPO_POLICY_ID,
        policy_configuration_ref=_ref(
            "deterministic-policy-config",
            graph.tempo_configuration,
        ),
        mastery_projection_ref=_ref("curriculum-mastery-projection", mastery),
        evidence_snapshot_sequence=evidence_snapshot_sequence,
        evidence_snapshot_fingerprint=evidence_fingerprint,
        evidence_record_refs=evidence_refs,
        observation_refs=observation_refs,
        attempt_sequence=mastery.evaluated_attempt_ids,
        previously_satisfied_node_ids=previously_satisfied_node_ids,
        budget_state=budget_state,
        curriculum_contract_version=CURRICULUM_CONTRACT_VERSION,
        performance_contract_version=PERFORMANCE_CONTRACT_VERSION,
        evidence_archive_contract_version=EVIDENCE_ARCHIVE_CONTRACT_VERSION,
        resolution=ArtifactResolution.RESOLVED,
    )
    snapshot = replace(
        provisional,
        id=derived_id("curriculum-decision-snapshot", provisional),
        semantic_fingerprint=semantic_fingerprint(provisional),
    )
    require_valid_curriculum_decision_snapshot(snapshot)
    return snapshot


def build_curriculum_action_inventory(
    graph: AcquisitionGraphSlice,
    mastery: CurriculumMasteryProjection,
    snapshot: CurriculumDecisionSnapshot,
) -> CurriculumActionInventory:
    """Record every implemented graph action and guard before selection."""

    require_valid_acquisition_graph_slice(graph)
    require_valid_curriculum_mastery_projection(mastery)
    require_valid_curriculum_decision_snapshot(snapshot)
    graph_ref = _ref("acquisition-graph-slice", graph)
    mastery_ref = _ref("curriculum-mastery-projection", mastery)
    if (
        snapshot.graph_ref != graph_ref
        or snapshot.current_node_id != mastery.node_id
        or snapshot.mastery_projection_ref != mastery_ref
        or snapshot.policy_configuration_ref
        != _ref("deterministic-policy-config", graph.tempo_configuration)
        or snapshot.policy_identity != TEMPO_POLICY_ID
    ):
        raise CurriculumTrajectoryError(
            "TMM-POLICY-SNAPSHOT-MISMATCH",
            "action inventory graph, mastery, or policy differs from the snapshot",
        )

    nodes = {item.id: item for item in graph.nodes}
    current = nodes.get(snapshot.current_node_id)
    if current is None:
        raise CurriculumTrajectoryError(
            "TMM-POLICY-SNAPSHOT-MISMATCH",
            "snapshot current node is absent from the supplied graph",
        )
    satisfied_before = set(snapshot.previously_satisfied_node_ids)
    if not satisfied_before <= nodes.keys():
        raise CurriculumTrajectoryError(
            "TMM-POLICY-SNAPSHOT-MISMATCH",
            "snapshot satisfied-node state is outside the supplied graph",
        )
    counters = {item.key: item for item in snapshot.budget_state}
    candidates = tuple(
        _action_candidate(
            edge,
            nodes[edge.target_node_id],
            current.component_node_ids,
            mastery.status,
            satisfied_before,
            counters,
        )
        for edge in sorted(
            (
                item
                for item in graph.edges
                if item.source_node_id == current.id and item.kind in _ACTIONABLE_EDGE_KINDS
            ),
            key=lambda item: (item.precedence, item.kind.value, item.id),
        )
    )
    provisional = CurriculumActionInventory(
        schema_version=CURRICULUM_CONTRACT_VERSION,
        id="curriculum-action-inventory:pending",
        semantic_fingerprint="",
        inventory_version=ACTION_INVENTORY_VERSION,
        snapshot_ref=_ref("curriculum-decision-snapshot", snapshot),
        graph_ref=graph_ref,
        current_node_id=current.id,
        mastery_projection_ref=mastery_ref,
        policy_identity=TEMPO_POLICY_ID,
        policy_configuration_ref=snapshot.policy_configuration_ref,
        candidates=candidates,
        resolution=ArtifactResolution.RESOLVED,
    )
    inventory = replace(
        provisional,
        id=derived_id("curriculum-action-inventory", provisional),
        semantic_fingerprint=semantic_fingerprint(provisional),
    )
    require_valid_curriculum_action_inventory(inventory, snapshot, graph, mastery)
    return inventory


def select_curriculum_action(
    inventory: CurriculumActionInventory,
    snapshot: CurriculumDecisionSnapshot,
    graph: AcquisitionGraphSlice,
    mastery: CurriculumMasteryProjection,
) -> CurriculumActionSelection:
    """Select exactly one allowed action through the frozen deterministic order."""

    require_valid_curriculum_action_inventory(inventory, snapshot, graph, mastery)
    allowed = tuple(
        candidate
        for candidate in inventory.candidates
        if candidate.eligibility is CurriculumActionEligibility.ALLOWED
    )
    if not allowed:
        raise CurriculumTrajectoryError(
            "TMM-POLICY-NO-ALLOWED-ACTION",
            "the exact action inventory contains no allowed candidate",
        )
    selected = min(allowed, key=_candidate_selection_key)
    provisional = CurriculumActionSelection(
        schema_version=CURRICULUM_CONTRACT_VERSION,
        id="curriculum-action-selection:pending",
        semantic_fingerprint="",
        selection_version=ACTION_SELECTION_VERSION,
        snapshot_ref=inventory.snapshot_ref,
        inventory_ref=_ref("curriculum-action-inventory", inventory),
        policy_identity=inventory.policy_identity,
        policy_configuration_ref=inventory.policy_configuration_ref,
        selected_candidate=selected,
        behavior_probability=Fraction(1),
        reason_code="TMM-POLICY-DETERMINISTIC-FIRST-ALLOWED",
        resolution=ArtifactResolution.RESOLVED,
    )
    selection = replace(
        provisional,
        id=derived_id("curriculum-action-selection", provisional),
        semantic_fingerprint=semantic_fingerprint(provisional),
    )
    require_valid_curriculum_action_selection(selection, inventory, snapshot)
    return selection


def build_curriculum_transition_result(
    selection: CurriculumActionSelection,
    prior_snapshot: CurriculumDecisionSnapshot,
    outcome: CurriculumLearningOutcome,
    research_reward: CurriculumResearchReward,
    next_snapshot: CurriculumDecisionSnapshot,
) -> CurriculumTransitionResult:
    """Bind one selected action to later facts, reward, and exact next state."""

    require_valid_curriculum_action_selection(selection, snapshot=prior_snapshot)
    require_valid_curriculum_learning_outcome(outcome)
    require_valid_curriculum_research_reward(research_reward, outcome=outcome)
    require_valid_curriculum_decision_snapshot(next_snapshot)
    provisional = CurriculumTransitionResult(
        schema_version=CURRICULUM_CONTRACT_VERSION,
        id="curriculum-transition-result:pending",
        semantic_fingerprint="",
        transition_version=TRANSITION_RESULT_VERSION,
        selection_ref=_ref("curriculum-action-selection", selection),
        outcome_ref=_ref("curriculum-learning-outcome", outcome),
        research_reward_ref=_ref("curriculum-research-reward", research_reward),
        next_snapshot_ref=_ref("curriculum-decision-snapshot", next_snapshot),
        resolution=ArtifactResolution.RESOLVED,
    )
    result = replace(
        provisional,
        id=derived_id("curriculum-transition-result", provisional),
        semantic_fingerprint=semantic_fingerprint(provisional),
    )
    require_valid_curriculum_transition_result(
        result,
        selection,
        prior_snapshot,
        outcome,
        research_reward,
        next_snapshot,
    )
    return result


def build_curriculum_experiment_manifest(
    snapshots: tuple[CurriculumDecisionSnapshot, ...],
    inventories: tuple[CurriculumActionInventory, ...],
    selections: tuple[CurriculumActionSelection, ...],
    outcomes: tuple[CurriculumLearningOutcome, ...],
    rewards: tuple[CurriculumResearchReward, ...],
    transitions: tuple[CurriculumTransitionResult, ...],
) -> CurriculumExperimentManifest:
    """Freeze a compact ordered index over a complete bounded trajectory."""

    transition_count = len(transitions)
    if transition_count == 0 or (
        len(snapshots) != transition_count + 1
        or len(inventories) != transition_count
        or len(selections) != transition_count
        or len(outcomes) != transition_count
        or len(rewards) != transition_count
    ):
        raise CurriculumTrajectoryError(
            "TMM-POLICY-MANIFEST-CARDINALITY",
            "one transition requires two snapshots and one of every other artifact",
        )
    for snapshot in snapshots:
        require_valid_curriculum_decision_snapshot(snapshot)
    for index in range(transition_count):
        require_valid_curriculum_action_inventory(inventories[index], snapshot=snapshots[index])
        require_valid_curriculum_action_selection(
            selections[index],
            inventories[index],
            snapshots[index],
        )
        require_valid_curriculum_learning_outcome(outcomes[index])
        require_valid_curriculum_research_reward(rewards[index], outcome=outcomes[index])
        require_valid_curriculum_transition_result(
            transitions[index],
            selections[index],
            snapshots[index],
            outcomes[index],
            rewards[index],
            snapshots[index + 1],
        )

    first = snapshots[0]
    provisional = CurriculumExperimentManifest(
        schema_version=CURRICULUM_CONTRACT_VERSION,
        id="curriculum-experiment-manifest:pending",
        semantic_fingerprint="",
        manifest_version=EXPERIMENT_MANIFEST_VERSION,
        run_id=first.run_id,
        score_package_digest=first.score_package_digest,
        score_id=first.score_id,
        learner_context_id=first.learner_context_id,
        graph_ref=first.graph_ref,
        policy_identity=first.policy_identity,
        policy_configuration_ref=first.policy_configuration_ref,
        snapshot_refs=tuple(_ref("curriculum-decision-snapshot", item) for item in snapshots),
        action_inventory_refs=tuple(
            _ref("curriculum-action-inventory", item) for item in inventories
        ),
        action_selection_refs=tuple(
            _ref("curriculum-action-selection", item) for item in selections
        ),
        outcome_refs=tuple(_ref("curriculum-learning-outcome", item) for item in outcomes),
        research_reward_refs=tuple(_ref("curriculum-research-reward", item) for item in rewards),
        transition_refs=tuple(_ref("curriculum-transition-result", item) for item in transitions),
        first_decision_sequence=first.decision_sequence,
        last_decision_sequence=snapshots[-1].decision_sequence,
        curriculum_contract_version=first.curriculum_contract_version,
        performance_contract_version=first.performance_contract_version,
        evidence_archive_contract_version=first.evidence_archive_contract_version,
        status=CurriculumExperimentStatus.BOUNDED_COMPLETE,
        resolution=ArtifactResolution.RESOLVED,
    )
    manifest = replace(
        provisional,
        id=derived_id("curriculum-experiment-manifest", provisional),
        semantic_fingerprint=semantic_fingerprint(provisional),
    )
    require_valid_curriculum_experiment_manifest(
        manifest,
        snapshots,
        inventories,
        selections,
        outcomes,
        rewards,
        transitions,
    )
    return manifest


def _candidate_selection_key(
    candidate: CurriculumActionCandidate,
) -> tuple[int, str, str]:
    """Return the frozen graph-precedence, edge-kind, edge-ID ordering."""

    edge_kind = next(
        value.removeprefix("edge-kind=")
        for value in candidate.tie_break_values
        if value.startswith("edge-kind=")
    )
    return candidate.precedence, edge_kind, candidate.edge_id


def _action_candidate(
    edge: CurriculumGraphEdge,
    target: CurriculumGraphNode,
    current_component_node_ids: tuple[str, ...],
    mastery_status: CurriculumMasteryStatus,
    satisfied_before: set[str],
    counters: dict[str, CurriculumBudgetCounter],
) -> CurriculumActionCandidate:
    mastery_passed = mastery_status is CurriculumMasteryStatus.MASTERED
    if mastery_passed:
        mastery_reason = "TMM-POLICY-CURRENT-NODE-SATISFIED"
    elif mastery_status is CurriculumMasteryStatus.NOT_MASTERED:
        mastery_reason = "TMM-POLICY-CURRENT-NODE-NOT-MASTERED"
    else:
        mastery_reason = "TMM-POLICY-EVIDENCE-INCOMPLETE"
    current_components_passed = set(current_component_node_ids) <= satisfied_before
    satisfied_after = satisfied_before | ({edge.source_node_id} if mastery_passed else set())
    target_components_passed = set(target.component_node_ids) <= satisfied_after
    guards = [
        CurriculumGuardResult(edge.guard, mastery_passed, mastery_reason),
        CurriculumGuardResult(
            "current-node-components-satisfied",
            current_components_passed,
            (
                "TMM-POLICY-CURRENT-DEPENDENCIES-SATISFIED"
                if current_components_passed
                else "TMM-POLICY-CURRENT-DEPENDENCIES-INCOMPLETE"
            ),
        ),
        CurriculumGuardResult(
            "target-node-components-satisfied",
            target_components_passed,
            (
                "TMM-POLICY-TARGET-DEPENDENCIES-SATISFIED"
                if target_components_passed
                else "TMM-POLICY-COMPONENTS-INCOMPLETE"
            ),
        ),
    ]
    if edge.budget_key is not None:
        counter = counters.get(edge.budget_key)
        budget_passed = counter is not None and counter.used < counter.limit
        guards.append(
            CurriculumGuardResult(
                f"budget:{edge.budget_key}",
                budget_passed,
                (
                    "TMM-POLICY-BUDGET-AVAILABLE"
                    if budget_passed
                    else (
                        "TMM-POLICY-BUDGET-MISSING"
                        if counter is None
                        else "TMM-POLICY-BUDGET-EXHAUSTED"
                    )
                ),
            )
        )
    failed = next((item for item in guards if not item.passed), None)
    eligibility = (
        CurriculumActionEligibility.ALLOWED
        if failed is None
        else CurriculumActionEligibility.EXCLUDED
    )
    return CurriculumActionCandidate(
        action=_policy_action(edge.kind, target.kind),
        edge_id=edge.id,
        target_node_id=target.id,
        eligibility=eligibility,
        guard_results=tuple(guards),
        precedence=edge.precedence,
        tie_break_values=(
            f"graph-precedence={edge.precedence}",
            f"edge-kind={edge.kind.value}",
            f"edge-id={edge.id}",
        ),
        reason_code=("TMM-POLICY-ACTION-ALLOWED" if failed is None else failed.reason_code),
    )


def _policy_action(
    edge_kind: CurriculumEdgeKind,
    target_kind: CurriculumNodeKind,
) -> CurriculumPolicyAction:
    if edge_kind is CurriculumEdgeKind.CHECKPOINT_AFTER:
        return CurriculumPolicyAction.RUN_CUMULATIVE
    if target_kind is CurriculumNodeKind.DIAGNOSTIC:
        return CurriculumPolicyAction.RUN_DIAGNOSTIC
    if target_kind is CurriculumNodeKind.PREREQUISITE:
        return CurriculumPolicyAction.TEACH_PREREQUISITE
    if target_kind is CurriculumNodeKind.RETENTION:
        return CurriculumPolicyAction.RUN_RETENTION
    if target_kind is CurriculumNodeKind.TRANSFER:
        return CurriculumPolicyAction.RUN_TRANSFER
    return CurriculumPolicyAction.PROGRESS


def _ref(artifact_type: str, value: _Identified) -> SemanticReference:
    return SemanticReference(
        artifact_type=artifact_type,
        id=value.id,
        semantic_fingerprint=semantic_fingerprint(value),
    )
