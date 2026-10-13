"""Fail-closed deterministic reconstruction for DEV-009 curriculum trajectories."""

from __future__ import annotations

from typing import NoReturn

from teachmemusic.performance import (
    AttemptAlignmentError,
    CalibrationProfile,
    ExpectedPerformance,
    LearnerAttempt,
    Observation,
    PerformanceBundle,
    PerformanceValidationError,
    align_layer_attempt,
    require_valid_performance_bundle,
)

from .contracts import EvidenceContext, SupportState
from .curriculum_contracts import (
    AcquisitionGraphSlice,
    CurriculumActionInventory,
    CurriculumActionSelection,
    CurriculumDecisionSnapshot,
    CurriculumEvidenceRecord,
    CurriculumExperimentManifest,
    CurriculumLearningOutcome,
    CurriculumMasteryProjection,
    CurriculumResearchReward,
    PassageRequirementSet,
    SemanticReference,
)
from .curriculum_evidence import CurriculumEvidenceError, build_curriculum_evidence_records
from .curriculum_fingerprint import semantic_fingerprint
from .curriculum_policy import CurriculumPolicyError, project_curriculum_mastery
from .curriculum_trajectory import (
    CurriculumTrajectoryError,
    build_curriculum_action_inventory,
    select_curriculum_action,
)
from .curriculum_validation import (
    CurriculumValidationError,
    require_valid_curriculum_action_inventory,
    require_valid_curriculum_action_selection,
    require_valid_curriculum_decision_snapshot,
    require_valid_curriculum_experiment_manifest,
    require_valid_curriculum_learning_outcome,
    require_valid_curriculum_mastery_projection,
    require_valid_curriculum_research_reward,
)
from .research_rewards import (
    CurriculumResearchRewardError,
    build_curriculum_research_reward,
)


class CurriculumReplayError(ValueError):
    """Raised when governed evidence cannot be reconstructed exactly."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(f"{code}: {message}")


_VERSION_MISMATCH_CODES = frozenset(
    {
        "TMM-CONTRACT-UNKNOWN-VERSION",
        "TMM-OUTCOME-RULE-MISMATCH",
        "TMM-REWARD-RULE-MISMATCH",
    }
)


def _raise_replay_validation(
    error: CurriculumValidationError,
    context: str,
) -> NoReturn:
    version_paths = tuple(
        issue.path for issue in error.issues if issue.code in _VERSION_MISMATCH_CODES
    )
    if version_paths:
        raise CurriculumReplayError(
            "TMM-REPLAY-VERSION-MISMATCH",
            f"{context} uses unsupported versions at {', '.join(version_paths)}; "
            "an explicit tested migration is required",
        ) from error
    raise CurriculumReplayError(
        "TMM-POLICY-REPLAY-MISMATCH",
        f"{context} is incompatible: {error}",
    ) from error


def reconstruct_curriculum_observations(
    manifest: CurriculumExperimentManifest,
    outcome: CurriculumLearningOutcome,
    expected: ExpectedPerformance,
    attempt: LearnerAttempt,
    calibration: CalibrationProfile,
    recorded_observations: tuple[Observation, ...],
) -> tuple[Observation, ...]:
    """Rebuild one manifest-governed observation sequence without reinterpretation."""

    try:
        require_valid_curriculum_experiment_manifest(manifest)
        outcome_ref = SemanticReference(
            "curriculum-learning-outcome",
            outcome.id,
            semantic_fingerprint(outcome),
        )
        if outcome_ref not in manifest.outcome_refs:
            raise CurriculumReplayError(
                "TMM-STORE-REFERENCE-MISSING",
                "the supplied factual outcome is absent from the experiment manifest",
            )
        require_valid_performance_bundle(
            PerformanceBundle(
                calibrations=(calibration,),
                attempts=(attempt,),
                observations=recorded_observations,
            )
        )
        require_valid_curriculum_learning_outcome(
            outcome,
            expected=expected,
            attempt=attempt,
            calibration=calibration,
            observations=recorded_observations,
        )
        reconstructed = align_layer_attempt(expected, attempt, calibration)
    except CurriculumReplayError:
        raise
    except CurriculumValidationError as error:
        _raise_replay_validation(error, "the governed observation inputs")
    except (AttemptAlignmentError, PerformanceValidationError) as error:
        raise CurriculumReplayError(
            "TMM-POLICY-REPLAY-MISMATCH",
            f"the governed observation inputs are incompatible: {error}",
        ) from error

    if reconstructed != recorded_observations:
        raise CurriculumReplayError(
            "TMM-POLICY-REPLAY-MISMATCH",
            "reconstructed observations differ from the recorded factual sequence",
        )
    return reconstructed


def reconstruct_curriculum_mastery_projection(
    manifest: CurriculumExperimentManifest,
    outcome: CurriculumLearningOutcome,
    next_snapshot: CurriculumDecisionSnapshot,
    graph: AcquisitionGraphSlice,
    requirements: PassageRequirementSet,
    expected: ExpectedPerformance,
    attempt: LearnerAttempt,
    calibration: CalibrationProfile,
    support: SupportState,
    evidence_context: EvidenceContext,
    recorded_observations: tuple[Observation, ...],
    recorded_evidence: tuple[CurriculumEvidenceRecord, ...],
    recorded_projection: CurriculumMasteryProjection,
) -> CurriculumMasteryProjection:
    """Rebuild one manifest-governed learner-state projection exactly."""

    replayed_observations = reconstruct_curriculum_observations(
        manifest,
        outcome,
        expected,
        attempt,
        calibration,
        recorded_observations,
    )
    try:
        require_valid_curriculum_decision_snapshot(next_snapshot)
        require_valid_curriculum_mastery_projection(recorded_projection)
        snapshot_ref = SemanticReference(
            "curriculum-decision-snapshot",
            next_snapshot.id,
            semantic_fingerprint(next_snapshot),
        )
        if snapshot_ref not in manifest.snapshot_refs:
            raise CurriculumReplayError(
                "TMM-STORE-REFERENCE-MISSING",
                "the supplied next-state snapshot is absent from the experiment manifest",
            )
        graph_ref = SemanticReference(
            "acquisition-graph-slice",
            graph.id,
            semantic_fingerprint(graph),
        )
        projection_ref = SemanticReference(
            "curriculum-mastery-projection",
            recorded_projection.id,
            semantic_fingerprint(recorded_projection),
        )
        support_ref = SemanticReference(
            "support-state",
            support.id,
            semantic_fingerprint(support),
        )
        if (
            manifest.graph_ref != graph_ref
            or next_snapshot.graph_ref != graph_ref
            or next_snapshot.mastery_projection_ref != projection_ref
            or next_snapshot.support_state_ref != support_ref
        ):
            raise CurriculumReplayError(
                "TMM-POLICY-REPLAY-MISMATCH",
                "the next state is detached from its graph, support, or mastery projection",
            )
        node = next(
            (item for item in graph.nodes if item.id == next_snapshot.current_node_id),
            None,
        )
        if node is None or node.requirement_ref is None:
            raise CurriculumReplayError(
                "TMM-POLICY-REPLAY-MISMATCH",
                "the next-state node or requirement is absent from the governed graph",
            )
        rebuilt_evidence = tuple(
            item
            for item in build_curriculum_evidence_records(
                requirements,
                expected,
                attempt,
                support,
                replayed_observations,
                evidence_context,
            )
            if item.requirement_ref == node.requirement_ref
        )
        evidence_refs = tuple(
            SemanticReference(
                "curriculum-evidence-record",
                item.id,
                semantic_fingerprint(item),
            )
            for item in recorded_evidence
        )
        observation_refs = tuple(
            SemanticReference(
                "performance-observation",
                item.id,
                semantic_fingerprint(item),
            )
            for item in replayed_observations
        )
        if (
            rebuilt_evidence != recorded_evidence
            or next_snapshot.evidence_record_refs != evidence_refs
            or next_snapshot.observation_refs != observation_refs
        ):
            raise CurriculumReplayError(
                "TMM-POLICY-REPLAY-MISMATCH",
                "reconstructed evidence differs from the recorded next-state inputs",
            )
        reconstructed = project_curriculum_mastery(
            graph,
            next_snapshot.current_node_id,
            support,
            rebuilt_evidence,
            attempt_sequence=next_snapshot.attempt_sequence,
        )
    except CurriculumReplayError:
        raise
    except CurriculumValidationError as error:
        _raise_replay_validation(error, "the governed learner-state inputs")
    except (CurriculumEvidenceError, CurriculumPolicyError) as error:
        raise CurriculumReplayError(
            "TMM-POLICY-REPLAY-MISMATCH",
            f"the governed learner-state inputs are incompatible: {error}",
        ) from error

    if reconstructed != recorded_projection:
        raise CurriculumReplayError(
            "TMM-POLICY-REPLAY-MISMATCH",
            "reconstructed learner state differs from the recorded mastery projection",
        )
    return reconstructed


def reconstruct_curriculum_action_decision(
    manifest: CurriculumExperimentManifest,
    snapshot: CurriculumDecisionSnapshot,
    graph: AcquisitionGraphSlice,
    mastery: CurriculumMasteryProjection,
    recorded_inventory: CurriculumActionInventory,
    recorded_selection: CurriculumActionSelection,
) -> tuple[CurriculumActionInventory, CurriculumActionSelection]:
    """Rebuild one manifest-governed action inventory and selection exactly."""

    try:
        require_valid_curriculum_experiment_manifest(manifest)
        require_valid_curriculum_decision_snapshot(snapshot)
        require_valid_curriculum_mastery_projection(mastery)
        require_valid_curriculum_action_inventory(
            recorded_inventory,
            snapshot,
            graph,
            mastery,
        )
        require_valid_curriculum_action_selection(
            recorded_selection,
            recorded_inventory,
            snapshot,
        )
        snapshot_ref = SemanticReference(
            "curriculum-decision-snapshot",
            snapshot.id,
            semantic_fingerprint(snapshot),
        )
        inventory_ref = SemanticReference(
            "curriculum-action-inventory",
            recorded_inventory.id,
            semantic_fingerprint(recorded_inventory),
        )
        selection_ref = SemanticReference(
            "curriculum-action-selection",
            recorded_selection.id,
            semantic_fingerprint(recorded_selection),
        )
        if (
            snapshot_ref not in manifest.snapshot_refs
            or inventory_ref not in manifest.action_inventory_refs
            or selection_ref not in manifest.action_selection_refs
        ):
            raise CurriculumReplayError(
                "TMM-STORE-REFERENCE-MISSING",
                "the supplied decision artifacts are absent from the experiment manifest",
            )
        graph_ref = SemanticReference(
            "acquisition-graph-slice",
            graph.id,
            semantic_fingerprint(graph),
        )
        mastery_ref = SemanticReference(
            "curriculum-mastery-projection",
            mastery.id,
            semantic_fingerprint(mastery),
        )
        if (
            manifest.graph_ref != graph_ref
            or snapshot.graph_ref != graph_ref
            or snapshot.mastery_projection_ref != mastery_ref
        ):
            raise CurriculumReplayError(
                "TMM-POLICY-REPLAY-MISMATCH",
                "the decision state is detached from its graph or mastery projection",
            )
        reconstructed_inventory = build_curriculum_action_inventory(
            graph,
            mastery,
            snapshot,
        )
        if reconstructed_inventory != recorded_inventory:
            raise CurriculumReplayError(
                "TMM-POLICY-REPLAY-MISMATCH",
                "reconstructed permitted actions differ from the recorded inventory",
            )
        reconstructed_selection = select_curriculum_action(
            reconstructed_inventory,
            snapshot,
            graph,
            mastery,
        )
    except CurriculumReplayError:
        raise
    except CurriculumValidationError as error:
        _raise_replay_validation(error, "the governed action-decision inputs")
    except CurriculumTrajectoryError as error:
        raise CurriculumReplayError(
            "TMM-POLICY-REPLAY-MISMATCH",
            f"the governed action-decision inputs are incompatible: {error}",
        ) from error

    if reconstructed_selection != recorded_selection:
        raise CurriculumReplayError(
            "TMM-POLICY-REPLAY-MISMATCH",
            "reconstructed selected action differs from the recorded selection",
        )
    return reconstructed_inventory, reconstructed_selection


def reconstruct_curriculum_research_reward(
    manifest: CurriculumExperimentManifest,
    outcome: CurriculumLearningOutcome,
    expected: ExpectedPerformance,
    attempt: LearnerAttempt,
    calibration: CalibrationProfile,
    recorded_observations: tuple[Observation, ...],
    recorded_reward: CurriculumResearchReward,
) -> CurriculumResearchReward:
    """Rebuild manifest-governed research components without aggregation."""

    if not isinstance(recorded_reward, CurriculumResearchReward):
        raise CurriculumReplayError(
            "TMM-REWARD-REPLAY-TYPE",
            "reward replay accepts a research reward only",
        )
    replayed_observations = reconstruct_curriculum_observations(
        manifest,
        outcome,
        expected,
        attempt,
        calibration,
        recorded_observations,
    )
    try:
        require_valid_curriculum_research_reward(
            recorded_reward,
            outcome,
            expected,
            replayed_observations,
        )
        reward_ref = SemanticReference(
            "curriculum-research-reward",
            recorded_reward.id,
            semantic_fingerprint(recorded_reward),
        )
        if reward_ref not in manifest.research_reward_refs:
            raise CurriculumReplayError(
                "TMM-STORE-REFERENCE-MISSING",
                "the supplied research reward is absent from the experiment manifest",
            )
        reconstructed = build_curriculum_research_reward(
            outcome,
            expected,
            replayed_observations,
        )
    except CurriculumReplayError:
        raise
    except CurriculumValidationError as error:
        _raise_replay_validation(error, "the governed research-reward inputs")
    except CurriculumResearchRewardError as error:
        raise CurriculumReplayError(
            "TMM-POLICY-REPLAY-MISMATCH",
            f"the governed research-reward inputs are incompatible: {error}",
        ) from error

    if reconstructed != recorded_reward:
        raise CurriculumReplayError(
            "TMM-POLICY-REPLAY-MISMATCH",
            "reconstructed research components differ from the recorded reward",
        )
    return reconstructed
