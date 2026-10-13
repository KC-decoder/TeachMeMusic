"""App-owned metric records and de-identified projections for DEV-009 Task 9K."""

from __future__ import annotations

from dataclasses import replace
from typing import Protocol

from .curriculum_contracts import (
    CURRICULUM_CONTRACT_VERSION,
    METRIC_SOURCE_RECORD_VERSION,
    METRIC_SUMMARY_VERSION,
    ArtifactResolution,
    CurriculumActionInventory,
    CurriculumActionSelection,
    CurriculumDecisionSnapshot,
    CurriculumExperimentManifest,
    CurriculumLearningOutcome,
    CurriculumMetricComponentSummary,
    CurriculumMetricDecisionSummary,
    CurriculumMetricInputRecord,
    CurriculumMetricSourceRecord,
    CurriculumMetricSummaryExport,
    CurriculumResearchReward,
    CurriculumTransitionResult,
    SemanticReference,
)
from .curriculum_fingerprint import derived_id, semantic_fingerprint
from .curriculum_validation import (
    require_valid_curriculum_experiment_manifest,
    require_valid_curriculum_metric_source_record,
    require_valid_curriculum_metric_summary_export,
)

DEIDENTIFIED_METRIC_SUMMARY_ALLOWLIST = (
    "type",
    "schema_version",
    "id",
    "artifact_type",
    "semantic_fingerprint",
    "summary_version",
    "source_record_ref",
    "score_id",
    "graph_ref",
    "policy_identity",
    "policy_configuration_ref",
    "decision_metrics",
    "first_decision_sequence",
    "last_decision_sequence",
    "resolution",
    "decision_sequence",
    "metric_input_fingerprint",
    "prior_snapshot_ref",
    "action_selection_ref",
    "outcome_ref",
    "research_reward_ref",
    "next_snapshot_ref",
    "current_node_id",
    "next_node_id",
    "prior_support_state_ref",
    "next_support_state_ref",
    "selected_action",
    "behavior_probability",
    "completion",
    "reward_components",
    "component_id",
    "dimension",
    "status",
    "value",
    "matched_observation_count",
    "discrepancy_observation_count",
    "unresolved_observation_count",
    "reason_code",
    "numerator",
    "denominator",
)


class _Identified(Protocol):
    @property
    def id(self) -> str: ...

    @property
    def semantic_fingerprint(self) -> str: ...


def build_curriculum_metric_source_record(
    manifest: CurriculumExperimentManifest,
    snapshots: tuple[CurriculumDecisionSnapshot, ...],
    inventories: tuple[CurriculumActionInventory, ...],
    selections: tuple[CurriculumActionSelection, ...],
    outcomes: tuple[CurriculumLearningOutcome, ...],
    rewards: tuple[CurriculumResearchReward, ...],
    transitions: tuple[CurriculumTransitionResult, ...],
) -> CurriculumMetricSourceRecord:
    """Bind exact trajectory inputs without copying evidence or learner identity."""

    require_valid_curriculum_experiment_manifest(
        manifest,
        snapshots,
        inventories,
        selections,
        outcomes,
        rewards,
        transitions,
    )
    inputs = tuple(
        _metric_input_record(
            snapshots[index],
            inventories[index],
            selections[index],
            outcomes[index],
            rewards[index],
            transitions[index],
            snapshots[index + 1],
        )
        for index in range(len(transitions))
    )
    provisional = CurriculumMetricSourceRecord(
        schema_version=CURRICULUM_CONTRACT_VERSION,
        id="curriculum-metric-source-record:pending",
        semantic_fingerprint="",
        source_record_version=METRIC_SOURCE_RECORD_VERSION,
        manifest_ref=_ref("curriculum-experiment-manifest", manifest),
        run_id=manifest.run_id,
        score_package_digest=manifest.score_package_digest,
        score_id=manifest.score_id,
        graph_ref=manifest.graph_ref,
        policy_identity=manifest.policy_identity,
        policy_configuration_ref=manifest.policy_configuration_ref,
        metric_inputs=inputs,
        first_decision_sequence=manifest.first_decision_sequence,
        last_decision_sequence=manifest.last_decision_sequence,
        curriculum_contract_version=manifest.curriculum_contract_version,
        performance_contract_version=manifest.performance_contract_version,
        evidence_archive_contract_version=manifest.evidence_archive_contract_version,
        resolution=ArtifactResolution.RESOLVED,
    )
    record = replace(
        provisional,
        id=derived_id("curriculum-metric-source-record", provisional),
        semantic_fingerprint=semantic_fingerprint(provisional),
    )
    require_valid_curriculum_metric_source_record(record, manifest)
    return record


def build_curriculum_metric_summary_export(
    source: CurriculumMetricSourceRecord,
    manifest: CurriculumExperimentManifest,
    snapshots: tuple[CurriculumDecisionSnapshot, ...],
    inventories: tuple[CurriculumActionInventory, ...],
    selections: tuple[CurriculumActionSelection, ...],
    outcomes: tuple[CurriculumLearningOutcome, ...],
    rewards: tuple[CurriculumResearchReward, ...],
    transitions: tuple[CurriculumTransitionResult, ...],
) -> CurriculumMetricSummaryExport:
    """Project the allowlisted de-identified metric view from local authority."""

    require_valid_curriculum_experiment_manifest(
        manifest,
        snapshots,
        inventories,
        selections,
        outcomes,
        rewards,
        transitions,
    )
    require_valid_curriculum_metric_source_record(source, manifest)
    decision_metrics = tuple(
        _decision_summary(
            source.metric_inputs[index],
            snapshots[index],
            selections[index],
            outcomes[index],
            rewards[index],
            snapshots[index + 1],
        )
        for index in range(len(source.metric_inputs))
    )
    provisional = CurriculumMetricSummaryExport(
        schema_version=CURRICULUM_CONTRACT_VERSION,
        id="curriculum-metric-summary-export:pending",
        semantic_fingerprint="",
        summary_version=METRIC_SUMMARY_VERSION,
        source_record_ref=_ref("curriculum-metric-source-record", source),
        score_id=source.score_id,
        graph_ref=source.graph_ref,
        policy_identity=source.policy_identity,
        policy_configuration_ref=source.policy_configuration_ref,
        decision_metrics=decision_metrics,
        first_decision_sequence=source.first_decision_sequence,
        last_decision_sequence=source.last_decision_sequence,
        resolution=ArtifactResolution.RESOLVED,
    )
    summary = replace(
        provisional,
        id=derived_id("curriculum-metric-summary-export", provisional),
        semantic_fingerprint=semantic_fingerprint(provisional),
    )
    require_valid_curriculum_metric_summary_export(
        summary,
        source,
        snapshots,
        selections,
        outcomes,
        rewards,
    )
    return summary


def _metric_input_record(
    prior: CurriculumDecisionSnapshot,
    inventory: CurriculumActionInventory,
    selection: CurriculumActionSelection,
    outcome: CurriculumLearningOutcome,
    reward: CurriculumResearchReward,
    transition: CurriculumTransitionResult,
    next_snapshot: CurriculumDecisionSnapshot,
) -> CurriculumMetricInputRecord:
    references = (
        _ref("curriculum-decision-snapshot", prior),
        _ref("curriculum-action-inventory", inventory),
        _ref("curriculum-action-selection", selection),
        _ref("curriculum-learning-outcome", outcome),
        _ref("curriculum-research-reward", reward),
        _ref("curriculum-transition-result", transition),
        _ref("curriculum-decision-snapshot", next_snapshot),
    )
    return CurriculumMetricInputRecord(
        decision_sequence=prior.decision_sequence,
        prior_snapshot_ref=references[0],
        action_inventory_ref=references[1],
        action_selection_ref=references[2],
        outcome_ref=references[3],
        research_reward_ref=references[4],
        transition_ref=references[5],
        next_snapshot_ref=references[6],
        metric_input_fingerprint=semantic_fingerprint(references),
    )


def _decision_summary(
    metric_input: CurriculumMetricInputRecord,
    prior: CurriculumDecisionSnapshot,
    selection: CurriculumActionSelection,
    outcome: CurriculumLearningOutcome,
    reward: CurriculumResearchReward,
    next_snapshot: CurriculumDecisionSnapshot,
) -> CurriculumMetricDecisionSummary:
    return CurriculumMetricDecisionSummary(
        decision_sequence=metric_input.decision_sequence,
        metric_input_fingerprint=metric_input.metric_input_fingerprint,
        prior_snapshot_ref=metric_input.prior_snapshot_ref,
        action_selection_ref=metric_input.action_selection_ref,
        outcome_ref=metric_input.outcome_ref,
        research_reward_ref=metric_input.research_reward_ref,
        next_snapshot_ref=metric_input.next_snapshot_ref,
        current_node_id=prior.current_node_id,
        next_node_id=next_snapshot.current_node_id,
        prior_support_state_ref=prior.support_state_ref,
        next_support_state_ref=next_snapshot.support_state_ref,
        selected_action=selection.selected_candidate.action,
        behavior_probability=selection.behavior_probability,
        completion=outcome.completion,
        reward_components=tuple(
            CurriculumMetricComponentSummary(
                component_id=component.component_id,
                dimension=component.dimension,
                status=component.status,
                value=component.value,
                matched_observation_count=component.matched_observation_count,
                discrepancy_observation_count=component.discrepancy_observation_count,
                unresolved_observation_count=component.unresolved_observation_count,
                reason_code=component.reason_code,
            )
            for component in reward.components
        ),
    )


def _ref(artifact_type: str, value: _Identified) -> SemanticReference:
    return SemanticReference(
        artifact_type,
        value.id,
        value.semantic_fingerprint,
    )
