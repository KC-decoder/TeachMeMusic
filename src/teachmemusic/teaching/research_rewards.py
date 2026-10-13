"""Versioned research-reward projections over immutable learning outcomes."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import replace
from fractions import Fraction

from teachmemusic.performance import (
    AttemptCompletion,
    ExpectedPerformance,
    Observation,
    ObservationDimension,
    ObservationStatus,
)

from .curriculum_contracts import (
    CURRICULUM_CONTRACT_VERSION,
    RESEARCH_REWARD_VERSION,
    ArtifactResolution,
    CurriculumLearningOutcome,
    CurriculumResearchReward,
    ResearchRewardComponent,
    ResearchRewardComponentStatus,
    RuleReference,
    SemanticReference,
)
from .curriculum_fingerprint import semantic_fingerprint
from .curriculum_validation import (
    require_valid_curriculum_learning_outcome,
    require_valid_curriculum_research_reward,
)

_PROJECTION_RULE_ID = "RESEARCH-REWARD-PROJECTION-001"
_COMPLETION_RULE_ID = "RESEARCH-REWARD-COMPLETION-001"
_DIMENSION_RULE_ID = "RESEARCH-REWARD-DIMENSION-MATCH-001"


class CurriculumResearchRewardError(ValueError):
    """Raised when factual outcomes cannot support a reward projection."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(f"{code}: {message}")


def build_curriculum_research_reward(
    outcome: CurriculumLearningOutcome,
    expected: ExpectedPerformance,
    observations: tuple[Observation, ...],
) -> CurriculumResearchReward:
    """Project exact numeric components without emitting an aggregate reward."""

    if any(not isinstance(item, Observation) for item in observations):
        raise CurriculumResearchRewardError(
            "TMM-REWARD-OBSERVATION-TYPE",
            "research rewards accept factual performance observations only",
        )
    require_valid_curriculum_learning_outcome(outcome)
    expected_ref = SemanticReference(
        "expected-performance",
        expected.exercise_id,
        semantic_fingerprint(expected),
    )
    if outcome.expected_performance_ref != expected_ref:
        raise CurriculumResearchRewardError(
            "TMM-REWARD-EXPECTED-MISMATCH",
            "reward projection received a different expected performance",
        )
    observation_refs = tuple(
        SemanticReference("performance-observation", item.id, semantic_fingerprint(item))
        for item in observations
    )
    if outcome.observation_refs != observation_refs:
        raise CurriculumResearchRewardError(
            "TMM-REWARD-OBSERVATION-MISMATCH",
            "reward projection received observations outside the preserved outcome",
        )

    components = [_completion_component(outcome.completion)]
    by_dimension: dict[ObservationDimension, list[Observation]] = defaultdict(list)
    for observation in observations:
        by_dimension[observation.dimension].append(observation)
    included_dimensions = set(expected.target_dimensions) | set(by_dimension)
    components.extend(
        _dimension_component(dimension, tuple(by_dimension.get(dimension, ())))
        for dimension in ObservationDimension
        if dimension in included_dimensions
    )

    provisional = CurriculumResearchReward(
        schema_version=CURRICULUM_CONTRACT_VERSION,
        id="curriculum-research-reward:pending",
        semantic_fingerprint="",
        run_id=outcome.run_id,
        outcome_ref=SemanticReference(
            "curriculum-learning-outcome",
            outcome.id,
            outcome.semantic_fingerprint,
        ),
        expected_performance_ref=expected_ref,
        components=tuple(components),
        generation_rule=_rule(_PROJECTION_RULE_ID),
        diagnostics=(),
        resolution=ArtifactResolution.RESOLVED,
    )
    fingerprint = semantic_fingerprint(provisional)
    reward = replace(
        provisional,
        id=f"curriculum-research-reward:{fingerprint}",
        semantic_fingerprint=fingerprint,
    )
    require_valid_curriculum_research_reward(reward, outcome, expected, observations)
    return reward


def require_compatible_curriculum_research_reward(
    value: CurriculumResearchReward,
    outcome: CurriculumLearningOutcome,
    expected: ExpectedPerformance,
    observations: tuple[Observation, ...],
) -> None:
    """Reject reward components that do not exactly reconstruct from evidence."""

    rebuilt = build_curriculum_research_reward(outcome, expected, observations)
    if value != rebuilt:
        raise CurriculumResearchRewardError(
            "TMM-REWARD-INCOMPATIBLE",
            "research reward does not reconstruct from the supplied outcome",
        )


def _completion_component(completion: AttemptCompletion) -> ResearchRewardComponent:
    status: ResearchRewardComponentStatus
    value: Fraction | None
    reason: str
    if completion is AttemptCompletion.COMPLETED:
        status = ResearchRewardComponentStatus.MEASURED
        value = Fraction(1)
        reason = "ATTEMPT_COMPLETED"
    elif completion is AttemptCompletion.INPUT_FAILURE:
        status = ResearchRewardComponentStatus.INVALID_INPUT
        value = None
        reason = "ATTEMPT_INPUT_FAILURE"
    elif completion is AttemptCompletion.INTERRUPTED:
        status = ResearchRewardComponentStatus.INCONCLUSIVE
        value = None
        reason = "ATTEMPT_INTERRUPTED"
    else:
        status = ResearchRewardComponentStatus.NOT_APPLICABLE
        value = None
        reason = f"ATTEMPT_{completion.value.replace('-', '_').upper()}"
    return ResearchRewardComponent(
        component_id="attempt-completion",
        dimension=None,
        status=status,
        value=value,
        matched_observation_count=0,
        discrepancy_observation_count=0,
        unresolved_observation_count=0,
        observation_refs=(),
        calculation_rule=_rule(_COMPLETION_RULE_ID),
        reason_code=reason,
    )


def _dimension_component(
    dimension: ObservationDimension,
    observations: tuple[Observation, ...],
) -> ResearchRewardComponent:
    matches = sum(item.status is ObservationStatus.MATCH for item in observations)
    discrepancies = sum(item.status is ObservationStatus.DISCREPANCY for item in observations)
    unresolved = len(observations) - matches - discrepancies
    references = tuple(
        SemanticReference("performance-observation", item.id, semantic_fingerprint(item))
        for item in observations
    )
    statuses = {item.status for item in observations}
    if ObservationStatus.INVALID_INPUT in statuses:
        status = ResearchRewardComponentStatus.INVALID_INPUT
        value = None
        reason = "INVALID_INPUT_OBSERVATION"
    elif statuses & {ObservationStatus.AMBIGUOUS, ObservationStatus.UNOBSERVABLE}:
        status = ResearchRewardComponentStatus.INCONCLUSIVE
        value = None
        reason = "UNRESOLVED_OBSERVATION"
    elif not observations:
        status = ResearchRewardComponentStatus.INCONCLUSIVE
        value = None
        reason = "TARGET_DIMENSION_UNOBSERVED"
    else:
        denominator = matches + discrepancies
        if denominator == 0:
            status = ResearchRewardComponentStatus.INCONCLUSIVE
            value = None
            reason = "NO_SCORABLE_OBSERVATION"
        else:
            status = ResearchRewardComponentStatus.MEASURED
            value = Fraction(matches, denominator)
            reason = "EXACT_MATCH_FRACTION"
    return ResearchRewardComponent(
        component_id=f"dimension-match:{dimension.value}",
        dimension=dimension,
        status=status,
        value=value,
        matched_observation_count=matches,
        discrepancy_observation_count=discrepancies,
        unresolved_observation_count=unresolved,
        observation_refs=references,
        calculation_rule=_rule(_DIMENSION_RULE_ID),
        reason_code=reason,
    )


def _rule(identifier: str) -> RuleReference:
    return RuleReference(
        identifier,
        RESEARCH_REWARD_VERSION,
        semantic_fingerprint((identifier, RESEARCH_REWARD_VERSION)),
    )
