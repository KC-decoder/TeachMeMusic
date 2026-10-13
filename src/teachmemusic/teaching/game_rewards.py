"""Learner-facing acknowledgements kept downstream of research rewards."""

from __future__ import annotations

from dataclasses import replace
from fractions import Fraction

from .curriculum_contracts import (
    CURRICULUM_CONTRACT_VERSION,
    GAME_REWARD_VERSION,
    ArtifactResolution,
    CurriculumGameReward,
    CurriculumLearningOutcome,
    CurriculumResearchReward,
    GameRewardSignal,
    ResearchRewardComponentStatus,
    RuleReference,
    SemanticReference,
)
from .curriculum_fingerprint import semantic_fingerprint
from .curriculum_validation import (
    require_valid_curriculum_game_reward,
    require_valid_curriculum_learning_outcome,
    require_valid_curriculum_research_reward,
)

_PROJECTION_RULE_ID = "GAME-REWARD-PRESENTATION-001"


class CurriculumGameRewardError(ValueError):
    """Raised when a presentation reward is detached from its source result."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(f"{code}: {message}")


def build_curriculum_game_reward(
    outcome: CurriculumLearningOutcome,
    research_reward: CurriculumResearchReward,
) -> CurriculumGameReward:
    """Project a display signal without creating evidence or policy authority."""

    require_valid_curriculum_learning_outcome(outcome)
    require_valid_curriculum_research_reward(research_reward, outcome)

    measured_dimensions = tuple(
        component
        for component in research_reward.components
        if component.dimension is not None
        and component.status is ResearchRewardComponentStatus.MEASURED
    )
    all_dimensions = tuple(
        component for component in research_reward.components if component.dimension is not None
    )
    completion = research_reward.components[0]
    source_component_ids = tuple(component.component_id for component in measured_dimensions)

    if not measured_dimensions:
        signal = GameRewardSignal.RESULT_UNAVAILABLE
        message_code = "GAME_RESULT_UNAVAILABLE"
    elif (
        completion.status is ResearchRewardComponentStatus.MEASURED
        and completion.value == Fraction(1)
        and len(measured_dimensions) == len(all_dimensions)
        and all(component.value == Fraction(1) for component in measured_dimensions)
    ):
        signal = GameRewardSignal.ACCURATE_ATTEMPT_CELEBRATION
        message_code = "GAME_ACCURATE_ATTEMPT"
    else:
        signal = GameRewardSignal.ATTEMPT_ACKNOWLEDGED
        message_code = "GAME_ATTEMPT_ACKNOWLEDGED"

    provisional = CurriculumGameReward(
        schema_version=CURRICULUM_CONTRACT_VERSION,
        id="curriculum-game-reward:pending",
        semantic_fingerprint="",
        run_id=outcome.run_id,
        outcome_ref=SemanticReference(
            "curriculum-learning-outcome",
            outcome.id,
            outcome.semantic_fingerprint,
        ),
        research_reward_ref=SemanticReference(
            "curriculum-research-reward",
            research_reward.id,
            research_reward.semantic_fingerprint,
        ),
        signal=signal,
        message_code=message_code,
        source_component_ids=source_component_ids,
        generation_rule=_rule(),
        diagnostics=(),
        resolution=ArtifactResolution.RESOLVED,
    )
    fingerprint = semantic_fingerprint(provisional)
    reward = replace(
        provisional,
        id=f"curriculum-game-reward:{fingerprint}",
        semantic_fingerprint=fingerprint,
    )
    require_valid_curriculum_game_reward(reward, outcome, research_reward)
    return reward


def require_compatible_curriculum_game_reward(
    value: CurriculumGameReward,
    outcome: CurriculumLearningOutcome,
    research_reward: CurriculumResearchReward,
) -> None:
    """Reject a display acknowledgement that cannot be reconstructed exactly."""

    rebuilt = build_curriculum_game_reward(outcome, research_reward)
    if value != rebuilt:
        raise CurriculumGameRewardError(
            "TMM-GAME-REWARD-INCOMPATIBLE",
            "game reward does not reconstruct from the supplied research result",
        )


def _rule() -> RuleReference:
    return RuleReference(
        _PROJECTION_RULE_ID,
        GAME_REWARD_VERSION,
        semantic_fingerprint((_PROJECTION_RULE_ID, GAME_REWARD_VERSION)),
    )
