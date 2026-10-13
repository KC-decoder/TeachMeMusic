"""Reward-free learning outcomes for exact curriculum attempts."""

from __future__ import annotations

from dataclasses import replace

from teachmemusic.performance import (
    CalibrationProfile,
    ExpectedPerformance,
    LearnerAttempt,
    Observation,
    PerformanceBundle,
    require_valid_performance_bundle,
)

from .contracts import SupportState
from .curriculum_contracts import (
    CURRICULUM_CONTRACT_VERSION,
    LEARNING_OUTCOME_VERSION,
    ArtifactResolution,
    CurriculumFundamentalPractice,
    CurriculumLearningOutcome,
    ExerciseInstance,
    RuleReference,
    SemanticReference,
)
from .curriculum_fingerprint import semantic_fingerprint
from .curriculum_validation import (
    require_valid_curriculum_fundamental_practice,
    require_valid_curriculum_learning_outcome,
    require_valid_exercise_instance,
)

_OUTCOME_RULE_ID = "LEARNING-OUTCOME-RULE-001"
_EXERCISE_OUTCOME_RULE_ID = "LEARNING-OUTCOME-RULE-002"


class CurriculumLearningOutcomeError(ValueError):
    """Raised when attempt facts cannot become one exact raw outcome."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(f"{code}: {message}")


def build_curriculum_learning_outcome(
    practice: CurriculumFundamentalPractice,
    expected: ExpectedPerformance,
    attempt: LearnerAttempt,
    calibration: CalibrationProfile,
    support: SupportState,
    observations: tuple[Observation, ...],
) -> CurriculumLearningOutcome:
    """Bind raw attempt facts without calculating reward, mastery, or action."""

    if any(not isinstance(item, Observation) for item in observations):
        raise CurriculumLearningOutcomeError(
            "TMM-OUTCOME-OBSERVATION-TYPE",
            "learning outcomes accept factual performance observations only",
        )
    require_valid_curriculum_fundamental_practice(practice, expected=expected)
    require_valid_performance_bundle(
        PerformanceBundle(
            calibrations=(calibration,),
            attempts=(attempt,),
            observations=observations,
        )
    )
    if attempt.exercise_id != expected.exercise_id:
        raise CurriculumLearningOutcomeError(
            "TMM-OUTCOME-ATTEMPT-TARGET",
            "attempt and expected performance identify different targets",
        )
    if attempt.exercise_id != practice.expected_performance_id:
        raise CurriculumLearningOutcomeError(
            "TMM-OUTCOME-PRACTICE-TARGET",
            "attempt is detached from the declared practice target",
        )
    if semantic_fingerprint(expected) != practice.expected_performance_sha256:
        raise CurriculumLearningOutcomeError(
            "TMM-OUTCOME-EXPECTED-FINGERPRINT",
            "expected performance differs from the practice binding",
        )
    if attempt.calibration_id != calibration.id:
        raise CurriculumLearningOutcomeError(
            "TMM-OUTCOME-CALIBRATION",
            "attempt and calibration identities differ",
        )
    if attempt.support_state_id != support.id:
        raise CurriculumLearningOutcomeError(
            "TMM-OUTCOME-SUPPORT",
            "attempt and support-state identities differ",
        )
    for observation in observations:
        if observation.attempt_id != attempt.id or observation.exercise_id != attempt.exercise_id:
            raise CurriculumLearningOutcomeError(
                "TMM-OUTCOME-OBSERVATION",
                "observation belongs to another attempt or target",
            )

    return _build_outcome(
        SemanticReference(
            "curriculum-fundamental-practice",
            practice.id,
            practice.semantic_fingerprint,
        ),
        _OUTCOME_RULE_ID,
        expected,
        attempt,
        calibration,
        support,
        observations,
        practice=practice,
    )


def build_curriculum_exercise_learning_outcome(
    exercise: ExerciseInstance,
    expected: ExpectedPerformance,
    attempt: LearnerAttempt,
    calibration: CalibrationProfile,
    support: SupportState,
    observations: tuple[Observation, ...],
) -> CurriculumLearningOutcome:
    """Bind one graph exercise attempt without creating a parallel outcome type."""

    if any(not isinstance(item, Observation) for item in observations):
        raise CurriculumLearningOutcomeError(
            "TMM-OUTCOME-OBSERVATION-TYPE",
            "learning outcomes accept factual performance observations only",
        )
    require_valid_exercise_instance(exercise)
    require_valid_performance_bundle(
        PerformanceBundle(
            calibrations=(calibration,),
            attempts=(attempt,),
            observations=observations,
        )
    )
    target = expected.layer_target
    if (
        target is None
        or target.practice_scope_id != exercise.practice_scope_ref.id
        or target.practice_scope_fingerprint != exercise.practice_scope_ref.semantic_fingerprint
        or target.active_event_ids != exercise.material.active_target_ids
        or target.inactive_event_ids != exercise.material.inactive_context_ids
    ):
        raise CurriculumLearningOutcomeError(
            "TMM-OUTCOME-EXERCISE-TARGET",
            "expected performance differs from the graph exercise material",
        )
    if attempt.exercise_id != expected.exercise_id:
        raise CurriculumLearningOutcomeError(
            "TMM-OUTCOME-ATTEMPT-TARGET",
            "attempt and expected performance identify different targets",
        )
    if attempt.calibration_id != calibration.id:
        raise CurriculumLearningOutcomeError(
            "TMM-OUTCOME-CALIBRATION",
            "attempt and calibration identities differ",
        )
    if attempt.support_state_id != support.id:
        raise CurriculumLearningOutcomeError(
            "TMM-OUTCOME-SUPPORT",
            "attempt and support-state identities differ",
        )
    for observation in observations:
        if observation.attempt_id != attempt.id or observation.exercise_id != attempt.exercise_id:
            raise CurriculumLearningOutcomeError(
                "TMM-OUTCOME-OBSERVATION",
                "observation belongs to another attempt or target",
            )
    return _build_outcome(
        SemanticReference(
            "exercise-instance",
            exercise.id,
            exercise.semantic_fingerprint,
        ),
        _EXERCISE_OUTCOME_RULE_ID,
        expected,
        attempt,
        calibration,
        support,
        observations,
        exercise=exercise,
    )


def _build_outcome(
    practice_ref: SemanticReference,
    rule_id: str,
    expected: ExpectedPerformance,
    attempt: LearnerAttempt,
    calibration: CalibrationProfile,
    support: SupportState,
    observations: tuple[Observation, ...],
    *,
    practice: CurriculumFundamentalPractice | None = None,
    exercise: ExerciseInstance | None = None,
) -> CurriculumLearningOutcome:
    rule = RuleReference(
        rule_id,
        LEARNING_OUTCOME_VERSION,
        semantic_fingerprint((rule_id, LEARNING_OUTCOME_VERSION)),
    )
    provisional = CurriculumLearningOutcome(
        schema_version=CURRICULUM_CONTRACT_VERSION,
        id="curriculum-learning-outcome:pending",
        semantic_fingerprint="",
        run_id=attempt.run_id,
        practice_ref=practice_ref,
        expected_performance_ref=SemanticReference(
            "expected-performance",
            expected.exercise_id,
            semantic_fingerprint(expected),
        ),
        attempt_ref=SemanticReference(
            "learner-attempt",
            attempt.id,
            semantic_fingerprint(attempt),
        ),
        calibration_ref=SemanticReference(
            "calibration-profile",
            calibration.id,
            semantic_fingerprint(calibration),
        ),
        support_state_ref=SemanticReference(
            "support-state",
            support.id,
            semantic_fingerprint(support),
        ),
        completion=attempt.completion,
        raw_message_ids=tuple(item.id for item in attempt.raw_messages),
        normalized_event_ids=tuple(item.id for item in attempt.normalized_events),
        observation_refs=tuple(
            SemanticReference("performance-observation", item.id, semantic_fingerprint(item))
            for item in observations
        ),
        generation_rule=rule,
        diagnostics=(),
        resolution=ArtifactResolution.RESOLVED,
    )
    fingerprint = semantic_fingerprint(provisional)
    outcome = replace(
        provisional,
        id=f"curriculum-learning-outcome:{fingerprint}",
        semantic_fingerprint=fingerprint,
    )
    require_valid_curriculum_learning_outcome(
        outcome,
        practice,
        expected,
        attempt,
        calibration,
        support,
        observations,
        exercise=exercise,
    )
    return outcome


def require_compatible_curriculum_learning_outcome(
    value: CurriculumLearningOutcome,
    practice: CurriculumFundamentalPractice,
    expected: ExpectedPerformance,
    attempt: LearnerAttempt,
    calibration: CalibrationProfile,
    support: SupportState,
    observations: tuple[Observation, ...],
) -> None:
    """Reject an outcome that cannot be reconstructed from its factual inputs."""

    rebuilt = build_curriculum_learning_outcome(
        practice,
        expected,
        attempt,
        calibration,
        support,
        observations,
    )
    if value != rebuilt:
        raise CurriculumLearningOutcomeError(
            "TMM-OUTCOME-INCOMPATIBLE",
            "outcome does not reconstruct from the supplied attempt facts",
        )


def require_compatible_curriculum_exercise_learning_outcome(
    value: CurriculumLearningOutcome,
    exercise: ExerciseInstance,
    expected: ExpectedPerformance,
    attempt: LearnerAttempt,
    calibration: CalibrationProfile,
    support: SupportState,
    observations: tuple[Observation, ...],
) -> None:
    """Reject a graph-exercise outcome that cannot reconstruct exactly."""

    rebuilt = build_curriculum_exercise_learning_outcome(
        exercise,
        expected,
        attempt,
        calibration,
        support,
        observations,
    )
    if value != rebuilt:
        raise CurriculumLearningOutcomeError(
            "TMM-OUTCOME-INCOMPATIBLE",
            "outcome does not reconstruct from the supplied graph-exercise facts",
        )
