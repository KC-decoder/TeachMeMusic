"""Strict serialization for complete DEV-009 curriculum artifact types."""

from __future__ import annotations

import json
import types
from collections.abc import Callable
from dataclasses import fields, is_dataclass
from typing import Union, get_args, get_origin, get_type_hints

from teachmemusic._contract_codec import (
    ContractCodecError,
    contract_from_data,
    contract_json_data,
    contract_to_data,
)

from .curriculum_contracts import (
    AcquisitionGraphSlice,
    CanonicalExcerptMaterial,
    CurriculumActionInventory,
    CurriculumActionSelection,
    CurriculumDecisionSnapshot,
    CurriculumEvidenceRecord,
    CurriculumExperimentManifest,
    CurriculumFundamentalDemonstration,
    CurriculumFundamentalExplanation,
    CurriculumFundamentalPractice,
    CurriculumGameReward,
    CurriculumLearningOutcome,
    CurriculumMasteryProjection,
    CurriculumMetricSourceRecord,
    CurriculumMetricSummaryExport,
    CurriculumPassageGuidance,
    CurriculumPassagePresentation,
    CurriculumPieceReturn,
    CurriculumResearchReward,
    CurriculumTransitionResult,
    CurriculumUnlockDecision,
    ExerciseInstance,
    LastingSkillGraphSlice,
    LearningPrimitive,
    PassageSkillRequirement,
    PracticeScopeAssignment,
    SemanticReference,
    TempoConfiguration,
)
from .curriculum_validation import (
    CurriculumValidationError,
    require_valid_acquisition_graph_slice,
    require_valid_curriculum_action_inventory,
    require_valid_curriculum_action_selection,
    require_valid_curriculum_decision_snapshot,
    require_valid_curriculum_evidence_record,
    require_valid_curriculum_experiment_manifest,
    require_valid_curriculum_fundamental_demonstration,
    require_valid_curriculum_fundamental_explanation,
    require_valid_curriculum_fundamental_practice,
    require_valid_curriculum_game_reward,
    require_valid_curriculum_learning_outcome,
    require_valid_curriculum_mastery_projection,
    require_valid_curriculum_metric_source_record,
    require_valid_curriculum_metric_summary_export,
    require_valid_curriculum_passage_guidance,
    require_valid_curriculum_passage_presentation,
    require_valid_curriculum_piece_return,
    require_valid_curriculum_research_reward,
    require_valid_curriculum_transition_result,
    require_valid_curriculum_unlock_decision,
    require_valid_exercise_instance,
    require_valid_lasting_skill_graph_slice,
    require_valid_practice_scope,
    require_valid_primitive,
    require_valid_requirement,
    require_valid_tempo_configuration,
)


class CurriculumSerializationError(ValueError):
    """Raised when curriculum JSON is malformed, unsupported, or invalid."""


_WIRE_TYPES: dict[type[object], str] = {
    PracticeScopeAssignment: "practice-scope-assignment",
    LearningPrimitive: "learning-primitive",
    PassageSkillRequirement: "passage-skill-requirement",
    ExerciseInstance: "exercise-instance",
    TempoConfiguration: "deterministic-policy-config",
    AcquisitionGraphSlice: "acquisition-graph-slice",
    LastingSkillGraphSlice: "lasting-skill-graph-slice",
    CurriculumPassagePresentation: "curriculum-passage-presentation",
    CurriculumPassageGuidance: "curriculum-passage-guidance",
    CurriculumFundamentalExplanation: "curriculum-fundamental-explanation",
    CurriculumFundamentalDemonstration: "curriculum-fundamental-demonstration",
    CurriculumFundamentalPractice: "curriculum-fundamental-practice",
    CurriculumLearningOutcome: "curriculum-learning-outcome",
    CurriculumResearchReward: "curriculum-research-reward",
    CurriculumGameReward: "curriculum-game-reward",
    CurriculumPieceReturn: "curriculum-piece-return",
    CurriculumEvidenceRecord: "curriculum-evidence-record",
    CurriculumMasteryProjection: "curriculum-mastery-projection",
    CurriculumUnlockDecision: "curriculum-unlock-decision",
    CurriculumDecisionSnapshot: "curriculum-decision-snapshot",
    CurriculumActionInventory: "curriculum-action-inventory",
    CurriculumActionSelection: "curriculum-action-selection",
    CurriculumTransitionResult: "curriculum-transition-result",
    CurriculumExperimentManifest: "curriculum-experiment-manifest",
    CurriculumMetricSourceRecord: "curriculum-metric-source-record",
    CurriculumMetricSummaryExport: "curriculum-metric-summary-export",
}


def practice_scope_to_dict(value: PracticeScopeAssignment) -> dict[str, object]:
    return _to_dict(value, require_valid_practice_scope)


def practice_scope_to_json(value: PracticeScopeAssignment) -> str:
    return _to_json(value, require_valid_practice_scope)


def practice_scope_from_dict(data: object) -> PracticeScopeAssignment:
    return _from_dict(data, PracticeScopeAssignment, require_valid_practice_scope)


def practice_scope_from_json(payload: str) -> PracticeScopeAssignment:
    return _from_json(payload, PracticeScopeAssignment, require_valid_practice_scope)


def learning_primitive_to_dict(value: LearningPrimitive) -> dict[str, object]:
    return _to_dict(value, require_valid_primitive)


def learning_primitive_to_json(value: LearningPrimitive) -> str:
    return _to_json(value, require_valid_primitive)


def learning_primitive_from_dict(data: object) -> LearningPrimitive:
    return _from_dict(data, LearningPrimitive, require_valid_primitive)


def learning_primitive_from_json(payload: str) -> LearningPrimitive:
    return _from_json(payload, LearningPrimitive, require_valid_primitive)


def passage_requirement_to_dict(value: PassageSkillRequirement) -> dict[str, object]:
    return _to_dict(value, require_valid_requirement)


def passage_requirement_to_json(value: PassageSkillRequirement) -> str:
    return _to_json(value, require_valid_requirement)


def passage_requirement_from_dict(data: object) -> PassageSkillRequirement:
    return _from_dict(data, PassageSkillRequirement, require_valid_requirement)


def passage_requirement_from_json(payload: str) -> PassageSkillRequirement:
    return _from_json(payload, PassageSkillRequirement, require_valid_requirement)


def exercise_instance_to_dict(value: ExerciseInstance) -> dict[str, object]:
    return _to_dict(value, require_valid_exercise_instance)


def exercise_instance_to_json(value: ExerciseInstance) -> str:
    return _to_json(value, require_valid_exercise_instance)


def exercise_instance_from_dict(data: object) -> ExerciseInstance:
    return _from_dict(data, ExerciseInstance, require_valid_exercise_instance)


def exercise_instance_from_json(payload: str) -> ExerciseInstance:
    return _from_json(payload, ExerciseInstance, require_valid_exercise_instance)


def tempo_configuration_to_dict(value: TempoConfiguration) -> dict[str, object]:
    return _to_dict(value, require_valid_tempo_configuration)


def tempo_configuration_to_json(value: TempoConfiguration) -> str:
    return _to_json(value, require_valid_tempo_configuration)


def tempo_configuration_from_dict(data: object) -> TempoConfiguration:
    return _from_dict(data, TempoConfiguration, require_valid_tempo_configuration)


def tempo_configuration_from_json(payload: str) -> TempoConfiguration:
    return _from_json(payload, TempoConfiguration, require_valid_tempo_configuration)


def acquisition_graph_slice_to_dict(value: AcquisitionGraphSlice) -> dict[str, object]:
    return _to_dict(value, require_valid_acquisition_graph_slice)


def acquisition_graph_slice_to_json(value: AcquisitionGraphSlice) -> str:
    return _to_json(value, require_valid_acquisition_graph_slice)


def acquisition_graph_slice_from_dict(data: object) -> AcquisitionGraphSlice:
    return _from_dict(data, AcquisitionGraphSlice, require_valid_acquisition_graph_slice)


def acquisition_graph_slice_from_json(payload: str) -> AcquisitionGraphSlice:
    return _from_json(payload, AcquisitionGraphSlice, require_valid_acquisition_graph_slice)


def lasting_skill_graph_slice_to_dict(value: LastingSkillGraphSlice) -> dict[str, object]:
    return _to_dict(value, require_valid_lasting_skill_graph_slice)


def lasting_skill_graph_slice_to_json(value: LastingSkillGraphSlice) -> str:
    return _to_json(value, require_valid_lasting_skill_graph_slice)


def lasting_skill_graph_slice_from_dict(data: object) -> LastingSkillGraphSlice:
    return _from_dict(data, LastingSkillGraphSlice, require_valid_lasting_skill_graph_slice)


def lasting_skill_graph_slice_from_json(payload: str) -> LastingSkillGraphSlice:
    return _from_json(payload, LastingSkillGraphSlice, require_valid_lasting_skill_graph_slice)


def curriculum_passage_presentation_to_dict(
    value: CurriculumPassagePresentation,
) -> dict[str, object]:
    return _to_dict(value, require_valid_curriculum_passage_presentation)


def curriculum_passage_presentation_to_json(value: CurriculumPassagePresentation) -> str:
    return _to_json(value, require_valid_curriculum_passage_presentation)


def curriculum_passage_presentation_from_dict(
    data: object,
) -> CurriculumPassagePresentation:
    return _from_dict(
        data,
        CurriculumPassagePresentation,
        require_valid_curriculum_passage_presentation,
    )


def curriculum_passage_presentation_from_json(
    payload: str,
) -> CurriculumPassagePresentation:
    return _from_json(
        payload,
        CurriculumPassagePresentation,
        require_valid_curriculum_passage_presentation,
    )


def curriculum_passage_guidance_to_dict(
    value: CurriculumPassageGuidance,
) -> dict[str, object]:
    return _to_dict(value, require_valid_curriculum_passage_guidance)


def curriculum_passage_guidance_to_json(value: CurriculumPassageGuidance) -> str:
    return _to_json(value, require_valid_curriculum_passage_guidance)


def curriculum_passage_guidance_from_dict(
    data: object,
) -> CurriculumPassageGuidance:
    return _from_dict(
        data,
        CurriculumPassageGuidance,
        require_valid_curriculum_passage_guidance,
    )


def curriculum_passage_guidance_from_json(
    payload: str,
) -> CurriculumPassageGuidance:
    return _from_json(
        payload,
        CurriculumPassageGuidance,
        require_valid_curriculum_passage_guidance,
    )


def curriculum_fundamental_explanation_to_dict(
    value: CurriculumFundamentalExplanation,
) -> dict[str, object]:
    return _to_dict(value, require_valid_curriculum_fundamental_explanation)


def curriculum_fundamental_explanation_to_json(
    value: CurriculumFundamentalExplanation,
) -> str:
    return _to_json(value, require_valid_curriculum_fundamental_explanation)


def curriculum_fundamental_explanation_from_dict(
    data: object,
) -> CurriculumFundamentalExplanation:
    return _from_dict(
        data,
        CurriculumFundamentalExplanation,
        require_valid_curriculum_fundamental_explanation,
    )


def curriculum_fundamental_explanation_from_json(
    payload: str,
) -> CurriculumFundamentalExplanation:
    return _from_json(
        payload,
        CurriculumFundamentalExplanation,
        require_valid_curriculum_fundamental_explanation,
    )


def curriculum_fundamental_demonstration_to_dict(
    value: CurriculumFundamentalDemonstration,
) -> dict[str, object]:
    return _to_dict(value, require_valid_curriculum_fundamental_demonstration)


def curriculum_fundamental_demonstration_to_json(
    value: CurriculumFundamentalDemonstration,
) -> str:
    return _to_json(value, require_valid_curriculum_fundamental_demonstration)


def curriculum_fundamental_demonstration_from_dict(
    data: object,
) -> CurriculumFundamentalDemonstration:
    return _from_dict(
        data,
        CurriculumFundamentalDemonstration,
        require_valid_curriculum_fundamental_demonstration,
    )


def curriculum_fundamental_demonstration_from_json(
    payload: str,
) -> CurriculumFundamentalDemonstration:
    return _from_json(
        payload,
        CurriculumFundamentalDemonstration,
        require_valid_curriculum_fundamental_demonstration,
    )


def curriculum_fundamental_practice_to_dict(
    value: CurriculumFundamentalPractice,
) -> dict[str, object]:
    return _to_dict(value, require_valid_curriculum_fundamental_practice)


def curriculum_fundamental_practice_to_json(
    value: CurriculumFundamentalPractice,
) -> str:
    return _to_json(value, require_valid_curriculum_fundamental_practice)


def curriculum_fundamental_practice_from_dict(
    data: object,
) -> CurriculumFundamentalPractice:
    return _from_dict(
        data,
        CurriculumFundamentalPractice,
        require_valid_curriculum_fundamental_practice,
    )


def curriculum_fundamental_practice_from_json(
    payload: str,
) -> CurriculumFundamentalPractice:
    return _from_json(
        payload,
        CurriculumFundamentalPractice,
        require_valid_curriculum_fundamental_practice,
    )


def curriculum_learning_outcome_to_dict(
    value: CurriculumLearningOutcome,
) -> dict[str, object]:
    return _to_dict(value, require_valid_curriculum_learning_outcome)


def curriculum_learning_outcome_to_json(value: CurriculumLearningOutcome) -> str:
    return _to_json(value, require_valid_curriculum_learning_outcome)


def curriculum_learning_outcome_from_dict(data: object) -> CurriculumLearningOutcome:
    return _from_dict(
        data,
        CurriculumLearningOutcome,
        require_valid_curriculum_learning_outcome,
    )


def curriculum_learning_outcome_from_json(payload: str) -> CurriculumLearningOutcome:
    return _from_json(
        payload,
        CurriculumLearningOutcome,
        require_valid_curriculum_learning_outcome,
    )


def curriculum_research_reward_to_dict(
    value: CurriculumResearchReward,
) -> dict[str, object]:
    return _to_dict(value, require_valid_curriculum_research_reward)


def curriculum_research_reward_to_json(value: CurriculumResearchReward) -> str:
    return _to_json(value, require_valid_curriculum_research_reward)


def curriculum_research_reward_from_dict(data: object) -> CurriculumResearchReward:
    return _from_dict(
        data,
        CurriculumResearchReward,
        require_valid_curriculum_research_reward,
    )


def curriculum_research_reward_from_json(payload: str) -> CurriculumResearchReward:
    return _from_json(
        payload,
        CurriculumResearchReward,
        require_valid_curriculum_research_reward,
    )


def curriculum_game_reward_to_dict(value: CurriculumGameReward) -> dict[str, object]:
    return _to_dict(value, require_valid_curriculum_game_reward)


def curriculum_game_reward_to_json(value: CurriculumGameReward) -> str:
    return _to_json(value, require_valid_curriculum_game_reward)


def curriculum_game_reward_from_dict(data: object) -> CurriculumGameReward:
    return _from_dict(data, CurriculumGameReward, require_valid_curriculum_game_reward)


def curriculum_game_reward_from_json(payload: str) -> CurriculumGameReward:
    return _from_json(payload, CurriculumGameReward, require_valid_curriculum_game_reward)


def curriculum_piece_return_to_dict(value: CurriculumPieceReturn) -> dict[str, object]:
    return _to_dict(value, require_valid_curriculum_piece_return)


def curriculum_piece_return_to_json(value: CurriculumPieceReturn) -> str:
    return _to_json(value, require_valid_curriculum_piece_return)


def curriculum_piece_return_from_dict(data: object) -> CurriculumPieceReturn:
    return _from_dict(data, CurriculumPieceReturn, require_valid_curriculum_piece_return)


def curriculum_piece_return_from_json(payload: str) -> CurriculumPieceReturn:
    return _from_json(payload, CurriculumPieceReturn, require_valid_curriculum_piece_return)


def curriculum_evidence_record_to_dict(
    value: CurriculumEvidenceRecord,
) -> dict[str, object]:
    return _to_dict(value, require_valid_curriculum_evidence_record)


def curriculum_evidence_record_to_json(value: CurriculumEvidenceRecord) -> str:
    return _to_json(value, require_valid_curriculum_evidence_record)


def curriculum_evidence_record_from_dict(data: object) -> CurriculumEvidenceRecord:
    return _from_dict(
        data,
        CurriculumEvidenceRecord,
        require_valid_curriculum_evidence_record,
    )


def curriculum_evidence_record_from_json(payload: str) -> CurriculumEvidenceRecord:
    return _from_json(
        payload,
        CurriculumEvidenceRecord,
        require_valid_curriculum_evidence_record,
    )


def curriculum_mastery_projection_to_dict(
    value: CurriculumMasteryProjection,
) -> dict[str, object]:
    return _to_dict(value, require_valid_curriculum_mastery_projection)


def curriculum_mastery_projection_to_json(value: CurriculumMasteryProjection) -> str:
    return _to_json(value, require_valid_curriculum_mastery_projection)


def curriculum_mastery_projection_from_dict(data: object) -> CurriculumMasteryProjection:
    return _from_dict(
        data,
        CurriculumMasteryProjection,
        require_valid_curriculum_mastery_projection,
    )


def curriculum_mastery_projection_from_json(payload: str) -> CurriculumMasteryProjection:
    return _from_json(
        payload,
        CurriculumMasteryProjection,
        require_valid_curriculum_mastery_projection,
    )


def curriculum_unlock_decision_to_dict(
    value: CurriculumUnlockDecision,
) -> dict[str, object]:
    return _to_dict(value, require_valid_curriculum_unlock_decision)


def curriculum_unlock_decision_to_json(value: CurriculumUnlockDecision) -> str:
    return _to_json(value, require_valid_curriculum_unlock_decision)


def curriculum_unlock_decision_from_dict(data: object) -> CurriculumUnlockDecision:
    return _from_dict(
        data,
        CurriculumUnlockDecision,
        require_valid_curriculum_unlock_decision,
    )


def curriculum_unlock_decision_from_json(payload: str) -> CurriculumUnlockDecision:
    return _from_json(
        payload,
        CurriculumUnlockDecision,
        require_valid_curriculum_unlock_decision,
    )


def curriculum_decision_snapshot_to_dict(
    value: CurriculumDecisionSnapshot,
) -> dict[str, object]:
    return _to_dict(value, require_valid_curriculum_decision_snapshot)


def curriculum_decision_snapshot_to_json(value: CurriculumDecisionSnapshot) -> str:
    return _to_json(value, require_valid_curriculum_decision_snapshot)


def curriculum_decision_snapshot_from_dict(data: object) -> CurriculumDecisionSnapshot:
    return _from_dict(
        data,
        CurriculumDecisionSnapshot,
        require_valid_curriculum_decision_snapshot,
    )


def curriculum_decision_snapshot_from_json(payload: str) -> CurriculumDecisionSnapshot:
    return _from_json(
        payload,
        CurriculumDecisionSnapshot,
        require_valid_curriculum_decision_snapshot,
    )


def curriculum_action_inventory_to_dict(
    value: CurriculumActionInventory,
) -> dict[str, object]:
    return _to_dict(value, require_valid_curriculum_action_inventory)


def curriculum_action_inventory_to_json(value: CurriculumActionInventory) -> str:
    return _to_json(value, require_valid_curriculum_action_inventory)


def curriculum_action_inventory_from_dict(data: object) -> CurriculumActionInventory:
    return _from_dict(
        data,
        CurriculumActionInventory,
        require_valid_curriculum_action_inventory,
    )


def curriculum_action_inventory_from_json(payload: str) -> CurriculumActionInventory:
    return _from_json(
        payload,
        CurriculumActionInventory,
        require_valid_curriculum_action_inventory,
    )


def curriculum_action_selection_to_dict(
    value: CurriculumActionSelection,
) -> dict[str, object]:
    return _to_dict(value, require_valid_curriculum_action_selection)


def curriculum_action_selection_to_json(value: CurriculumActionSelection) -> str:
    return _to_json(value, require_valid_curriculum_action_selection)


def curriculum_action_selection_from_dict(data: object) -> CurriculumActionSelection:
    return _from_dict(
        data,
        CurriculumActionSelection,
        require_valid_curriculum_action_selection,
    )


def curriculum_action_selection_from_json(payload: str) -> CurriculumActionSelection:
    return _from_json(
        payload,
        CurriculumActionSelection,
        require_valid_curriculum_action_selection,
    )


def curriculum_transition_result_to_dict(
    value: CurriculumTransitionResult,
) -> dict[str, object]:
    return _to_dict(value, require_valid_curriculum_transition_result)


def curriculum_transition_result_to_json(value: CurriculumTransitionResult) -> str:
    return _to_json(value, require_valid_curriculum_transition_result)


def curriculum_transition_result_from_dict(data: object) -> CurriculumTransitionResult:
    return _from_dict(
        data,
        CurriculumTransitionResult,
        require_valid_curriculum_transition_result,
    )


def curriculum_transition_result_from_json(payload: str) -> CurriculumTransitionResult:
    return _from_json(
        payload,
        CurriculumTransitionResult,
        require_valid_curriculum_transition_result,
    )


def curriculum_experiment_manifest_to_dict(
    value: CurriculumExperimentManifest,
) -> dict[str, object]:
    return _to_dict(value, require_valid_curriculum_experiment_manifest)


def curriculum_experiment_manifest_to_json(value: CurriculumExperimentManifest) -> str:
    return _to_json(value, require_valid_curriculum_experiment_manifest)


def curriculum_experiment_manifest_from_dict(data: object) -> CurriculumExperimentManifest:
    return _from_dict(
        data,
        CurriculumExperimentManifest,
        require_valid_curriculum_experiment_manifest,
    )


def curriculum_experiment_manifest_from_json(payload: str) -> CurriculumExperimentManifest:
    return _from_json(
        payload,
        CurriculumExperimentManifest,
        require_valid_curriculum_experiment_manifest,
    )


def curriculum_metric_source_record_to_dict(
    value: CurriculumMetricSourceRecord,
) -> dict[str, object]:
    return _to_dict(value, require_valid_curriculum_metric_source_record)


def curriculum_metric_source_record_to_json(value: CurriculumMetricSourceRecord) -> str:
    return _to_json(value, require_valid_curriculum_metric_source_record)


def curriculum_metric_source_record_from_dict(data: object) -> CurriculumMetricSourceRecord:
    return _from_dict(
        data,
        CurriculumMetricSourceRecord,
        require_valid_curriculum_metric_source_record,
    )


def curriculum_metric_source_record_from_json(payload: str) -> CurriculumMetricSourceRecord:
    return _from_json(
        payload,
        CurriculumMetricSourceRecord,
        require_valid_curriculum_metric_source_record,
    )


def curriculum_metric_summary_export_to_dict(
    value: CurriculumMetricSummaryExport,
) -> dict[str, object]:
    return _to_dict(value, require_valid_curriculum_metric_summary_export)


def curriculum_metric_summary_export_to_json(value: CurriculumMetricSummaryExport) -> str:
    return _to_json(value, require_valid_curriculum_metric_summary_export)


def curriculum_metric_summary_export_from_dict(data: object) -> CurriculumMetricSummaryExport:
    return _from_dict(
        data,
        CurriculumMetricSummaryExport,
        require_valid_curriculum_metric_summary_export,
    )


def curriculum_metric_summary_export_from_json(payload: str) -> CurriculumMetricSummaryExport:
    return _from_json(
        payload,
        CurriculumMetricSummaryExport,
        require_valid_curriculum_metric_summary_export,
    )


def _to_dict[
    T: (
        PracticeScopeAssignment,
        LearningPrimitive,
        PassageSkillRequirement,
        ExerciseInstance,
        TempoConfiguration,
        AcquisitionGraphSlice,
        LastingSkillGraphSlice,
        CurriculumPassagePresentation,
        CurriculumPassageGuidance,
        CurriculumFundamentalExplanation,
        CurriculumFundamentalDemonstration,
        CurriculumFundamentalPractice,
        CurriculumLearningOutcome,
        CurriculumResearchReward,
        CurriculumGameReward,
        CurriculumPieceReturn,
        CurriculumEvidenceRecord,
        CurriculumMasteryProjection,
        CurriculumUnlockDecision,
        CurriculumDecisionSnapshot,
        CurriculumActionInventory,
        CurriculumActionSelection,
        CurriculumTransitionResult,
        CurriculumExperimentManifest,
        CurriculumMetricSourceRecord,
        CurriculumMetricSummaryExport,
    )
](
    value: T,
    validator: Callable[[T], None],
) -> dict[str, object]:
    try:
        validator(value)
        data = contract_to_data(value)
    except (ContractCodecError, CurriculumValidationError) as error:
        raise CurriculumSerializationError(str(error)) from error
    if not isinstance(data, dict):
        raise CurriculumSerializationError("curriculum artifact did not encode as an object")
    wire = _strip_nested_codec_tags(data)
    wire["type"] = _WIRE_TYPES[type(value)]
    return wire


def _to_json[
    T: (
        PracticeScopeAssignment,
        LearningPrimitive,
        PassageSkillRequirement,
        ExerciseInstance,
        TempoConfiguration,
        AcquisitionGraphSlice,
        LastingSkillGraphSlice,
        CurriculumPassagePresentation,
        CurriculumPassageGuidance,
        CurriculumFundamentalExplanation,
        CurriculumFundamentalDemonstration,
        CurriculumFundamentalPractice,
        CurriculumLearningOutcome,
        CurriculumResearchReward,
        CurriculumGameReward,
        CurriculumPieceReturn,
        CurriculumEvidenceRecord,
        CurriculumMasteryProjection,
        CurriculumUnlockDecision,
        CurriculumDecisionSnapshot,
        CurriculumActionInventory,
        CurriculumActionSelection,
        CurriculumTransitionResult,
        CurriculumExperimentManifest,
        CurriculumMetricSourceRecord,
        CurriculumMetricSummaryExport,
    )
](
    value: T,
    validator: Callable[[T], None],
) -> str:
    return (
        json.dumps(
            _to_dict(value, validator),
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
            allow_nan=False,
        )
        + "\n"
    )


def _from_dict[
    T: (
        PracticeScopeAssignment,
        LearningPrimitive,
        PassageSkillRequirement,
        ExerciseInstance,
        TempoConfiguration,
        AcquisitionGraphSlice,
        LastingSkillGraphSlice,
        CurriculumPassagePresentation,
        CurriculumPassageGuidance,
        CurriculumFundamentalExplanation,
        CurriculumFundamentalDemonstration,
        CurriculumFundamentalPractice,
        CurriculumLearningOutcome,
        CurriculumResearchReward,
        CurriculumGameReward,
        CurriculumPieceReturn,
        CurriculumEvidenceRecord,
        CurriculumMasteryProjection,
        CurriculumUnlockDecision,
        CurriculumDecisionSnapshot,
        CurriculumActionInventory,
        CurriculumActionSelection,
        CurriculumTransitionResult,
        CurriculumExperimentManifest,
        CurriculumMetricSourceRecord,
        CurriculumMetricSummaryExport,
    )
](
    data: object,
    expected: type[T],
    validator: Callable[[T], None],
) -> T:
    if not isinstance(data, dict):
        raise CurriculumSerializationError("curriculum artifact must be an object")
    expected_wire_type = _WIRE_TYPES[expected]
    if data.get("type") != expected_wire_type:
        raise CurriculumSerializationError(
            f"type: expected {expected_wire_type!r}, received {data.get('type')!r}"
        )
    prepared = _restore_codec_tags(data, expected, root=True)
    try:
        value = contract_from_data(prepared, expected)
        validator(value)
    except (ContractCodecError, CurriculumValidationError) as error:
        raise CurriculumSerializationError(str(error)) from error
    return value


def _from_json[
    T: (
        PracticeScopeAssignment,
        LearningPrimitive,
        PassageSkillRequirement,
        ExerciseInstance,
        TempoConfiguration,
        AcquisitionGraphSlice,
        LastingSkillGraphSlice,
        CurriculumPassagePresentation,
        CurriculumPassageGuidance,
        CurriculumFundamentalExplanation,
        CurriculumFundamentalDemonstration,
        CurriculumFundamentalPractice,
        CurriculumLearningOutcome,
        CurriculumResearchReward,
        CurriculumGameReward,
        CurriculumPieceReturn,
        CurriculumEvidenceRecord,
        CurriculumMasteryProjection,
        CurriculumUnlockDecision,
        CurriculumDecisionSnapshot,
        CurriculumActionInventory,
        CurriculumActionSelection,
        CurriculumTransitionResult,
        CurriculumExperimentManifest,
        CurriculumMetricSourceRecord,
        CurriculumMetricSummaryExport,
    )
](
    payload: str,
    expected: type[T],
    validator: Callable[[T], None],
) -> T:
    try:
        data = contract_json_data(payload)
    except ContractCodecError as error:
        raise CurriculumSerializationError(str(error)) from error
    return _from_dict(data, expected, validator)


def _strip_nested_codec_tags(data: dict[str, object]) -> dict[str, object]:
    """Project internal dataclass tags into the frozen curriculum wire shape."""

    def visit(value: object, *, root: bool = False) -> object:
        if isinstance(value, list):
            return [visit(item) for item in value]
        if not isinstance(value, dict):
            return value
        result = {key: visit(item) for key, item in value.items() if key != "type"}
        codec_type = value.get("type")
        if codec_type == "SemanticReference":
            result["type"] = result.pop("artifact_type")
        elif codec_type == "CanonicalExcerptMaterial":
            result["type"] = result.pop("material_type")
        elif root:
            result["type"] = codec_type
        return result

    projected = visit(data, root=True)
    if not isinstance(projected, dict):
        raise CurriculumSerializationError("curriculum artifact did not project as an object")
    return projected


def _restore_codec_tags(data: object, expected: object, *, root: bool = False) -> object:
    """Restore private dataclass tags before invoking the shared strict codec."""

    origin = get_origin(expected)
    args = get_args(expected)
    if origin is tuple:
        if not isinstance(data, list) or len(args) != 2 or args[1] is not Ellipsis:
            return data
        return [_restore_codec_tags(item, args[0]) for item in data]
    if origin in {Union, types.UnionType}:
        if data is None:
            return None
        candidate = next((item for item in args if item is not type(None)), object)
        return _restore_codec_tags(data, candidate)
    if isinstance(expected, type) and is_dataclass(expected):
        if not isinstance(data, dict):
            return data
        hints = get_type_hints(expected)
        if expected is SemanticReference:
            restored_reference = {
                "type": expected.__name__,
                "artifact_type": data.get("type"),
                "id": data.get("id"),
                "semantic_fingerprint": data.get("semantic_fingerprint"),
            }
            for key, value in data.items():
                if key not in {"type", "id", "semantic_fingerprint"}:
                    restored_reference[key] = value
            return restored_reference
        if expected is CanonicalExcerptMaterial:
            restored_material = {
                "type": expected.__name__,
                "material_type": data.get("type"),
            }
            for key, value in data.items():
                if key != "type":
                    restored_material[key] = _restore_codec_tags(value, hints.get(key, object))
            return restored_material
        restored = {
            field.name: _restore_codec_tags(data.get(field.name), hints[field.name])
            for field in fields(expected)
        }
        restored["type"] = expected.__name__
        expected_keys = {field.name for field in fields(expected)}
        for key, value in data.items():
            if key not in expected_keys and not (root and key == "type"):
                restored[key] = value
        return restored
    if root and isinstance(data, dict):
        return dict(data)
    return data
