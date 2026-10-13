"""Deterministic evidence-to-feedback teaching policy."""

from __future__ import annotations

from dataclasses import dataclass, replace
from fractions import Fraction

from teachmemusic.performance import (
    AttemptCompletion,
    LearnerAttempt,
    Observation,
    ObservationDimension,
    ObservationStatus,
)
from teachmemusic.performance.validation import is_stable_id

from .contracts import (
    AttemptMastery,
    EvidenceContext,
    EvidenceRecord,
    EvidenceRequirement,
    EvidenceState,
    Exercise,
    FeedbackAction,
    FeedbackTiming,
    LearnerTrack,
    LessonNode,
    LessonNodeKind,
    LessonPlan,
    MasteryAction,
    PolicyAction,
    PolicyDecision,
    PracticeMode,
    SupportState,
)
from .validation import require_valid_lesson_plan, validate_lesson_plan

TEACHING_POLICY_VERSION = "deterministic-teaching-policy-v2"

_MASTERY_THRESHOLD_PERCENT = 95
_SLOW_DOWN_TRIGGER_PERCENT = 50
_SLOW_TEMPO_RATIO = Fraction(7, 10)

_GUIDED_MODES = {PracticeMode.EAR_FIRST.value, PracticeMode.FOLLOW_PITCH.value}
_UNCERTAIN_STATUSES = {
    ObservationStatus.AMBIGUOUS,
    ObservationStatus.UNOBSERVABLE,
    ObservationStatus.INVALID_INPUT,
}
_DIMENSION_PRIORITY = (
    ObservationDimension.INPUT,
    ObservationDimension.PITCH,
    ObservationDimension.ORDER,
    ObservationDimension.CHORD_SET,
    ObservationDimension.ONSET,
    ObservationDimension.DURATION,
    ObservationDimension.CONTINUITY,
    ObservationDimension.RELEASE,
    ObservationDimension.PEDAL,
    ObservationDimension.VELOCITY,
    ObservationDimension.SELF_REPORT,
    ObservationDimension.HUMAN_REVIEW,
)


class TeachingPolicyError(ValueError):
    """Raised when a policy request is inconsistent or unsupported."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(f"{code}: {message}")


@dataclass(frozen=True, slots=True)
class TeachingPolicyResult:
    """One immutable policy cycle before append-only persistence."""

    attempt_id: str
    exercise_id: str
    support: SupportState
    observations: tuple[Observation, ...]
    evidence_records: tuple[EvidenceRecord, ...]
    feedback: FeedbackAction
    decision: PolicyDecision
    discrepancy_signature: tuple[str, ...]
    next_support: SupportState | None = None
    mastery: AttemptMastery | None = None


def apply_teaching_policy(
    plan: LessonPlan,
    attempt: LearnerAttempt,
    support: SupportState,
    observations: tuple[Observation, ...],
    *,
    created_at_utc: str,
    history: tuple[TeachingPolicyResult, ...] = (),
    unsafe_condition: str | None = None,
) -> TeachingPolicyResult:
    """Create factual evidence, feedback, and exactly one next action.

    The policy is deliberately pure. It does not score, persist, infer causes,
    or learn online. ``history`` contains prior immutable results and is used
    only to distinguish correction, stability, a support change, and an
    unchanged discrepancy after that change.
    """

    require_valid_lesson_plan(plan)
    exercise, node = _request_context(plan, attempt, support, observations, created_at_utc)
    relevant_history = tuple(item for item in history if item.exercise_id == exercise.id)
    _validate_history(relevant_history, plan.run_id)
    signature = _discrepancy_signature(observations, exercise)

    if unsafe_condition is not None:
        if not unsafe_condition.strip():
            raise TeachingPolicyError(
                "TEACH_POLICY_SAFETY", "unsafe condition must be non-empty when provided"
            )
        records = _evidence_records(
            exercise,
            attempt,
            observations,
            relevant_history,
            forced_state=EvidenceState.INCONCLUSIVE,
            extra_limitation=(
                "Learner-reported discomfort requires a safety stop; no diagnosis was made.",
            ),
        )
        return _result(
            plan,
            exercise,
            node,
            attempt,
            support,
            observations,
            records,
            signature,
            PolicyAction.SAFE_STOP,
            created_at_utc,
            target="Safe physical practice",
            observation="The learner reported discomfort or another unsafe condition.",
            boundary="The report is preserved as learner input; MIDI cannot diagnose its cause.",
            action="Stop physical practice and seek appropriate human guidance before resuming.",
            reason="Safety takes priority over musical progression.",
            next_node_id=None,
        )

    input_problem = _input_problem(attempt, observations)
    if input_problem is not None:
        records = _evidence_records(
            exercise,
            attempt,
            observations,
            relevant_history,
            forced_state=EvidenceState.INCONCLUSIVE,
            extra_limitation=(input_problem,),
        )
        return _result(
            plan,
            exercise,
            node,
            attempt,
            support,
            observations,
            records,
            signature,
            PolicyAction.INCONCLUSIVE,
            created_at_utc,
            target="A complete, trustworthy learner attempt",
            observation=input_problem,
            boundary="No musical conclusion or learner penalty is justified from this input.",
            action="Repair or complete the input, then retry the same exercise.",
            reason="Progression requires valid evidence rather than an attempt count.",
            next_node_id=node.id,
        )

    review_reason = _human_review_reason(exercise, observations)
    if review_reason is not None:
        records = _evidence_records(
            exercise,
            attempt,
            observations,
            relevant_history,
            forced_state=EvidenceState.INCONCLUSIVE,
            extra_limitation=(review_reason,),
        )
        return _result(
            plan,
            exercise,
            node,
            attempt,
            support,
            observations,
            records,
            signature,
            PolicyAction.HUMAN_REVIEW,
            created_at_utc,
            target=_target_text(exercise, _first_target_dimension(exercise)),
            observation=review_reason,
            boundary="The available automated evidence cannot establish this target.",
            action="Keep the exercise unresolved and request bounded human review.",
            reason="The policy must not turn an unobservable or ambiguous fact into a pass.",
            next_node_id=node.id,
        )

    records = _evidence_records(exercise, attempt, observations, relevant_history)
    mastery = summarize_guided_mastery(
        plan.track, exercise, support, observations, relevant_history
    )
    if mastery is not None:
        if mastery.action is MasteryAction.EXERCISE_COMPLETE:
            action, next_node_id, action_text, reason = _progression(exercise, node, plan)
            mastery = replace(mastery, next_node_id=next_node_id)
            return _result(
                plan,
                exercise,
                node,
                attempt,
                support,
                observations,
                records,
                signature,
                action,
                created_at_utc,
                target="Complete the current note-event exercise",
                observation=(
                    f"{mastery.correct_note_count} of {mastery.expected_note_count} "
                    "expected note events matched."
                ),
                boundary="The mastery gate applies only to this bounded follow-pitch exercise.",
                action=action_text,
                reason=reason,
                next_node_id=next_node_id,
                mastery=mastery,
            )

        if mastery.action is MasteryAction.SLOW_DOWN:
            next_support = _slower_mastery_support(exercise.initial_support)
            action_text = "Repeat at 70% of the planned exercise tempo."
            reason = "Two consecutive attempts contained more than 50% incorrect note events."
        elif mastery.action is MasteryAction.RETURN_TO_NORMAL:
            next_support = exercise.initial_support
            action_text = "Repeat once at the planned exercise tempo."
            reason = "The reduced-tempo attempt reached the 95% mastery threshold."
        else:
            next_support = None
            action_text = "Repeat the same exercise."
            reason = "The exercise remains below the 95% mastery threshold."
        return _result(
            plan,
            exercise,
            node,
            attempt,
            support,
            observations,
            records,
            signature,
            PolicyAction.CORRECT,
            created_at_utc,
            target="Complete the current note-event exercise",
            observation=(
                f"{mastery.correct_note_count} of {mastery.expected_note_count} "
                "expected note events matched."
            ),
            boundary="The mastery gate applies only to this bounded follow-pitch exercise.",
            action=action_text,
            reason=reason,
            next_node_id=node.id,
            next_support=next_support,
            mastery=mastery,
        )

    discrepancies = _target_discrepancies(exercise, observations)
    if discrepancies:
        selected = _prioritized(discrepancies)[0]
        repeated = _matching_discrepancy_history(signature, relevant_history)
        if repeated:
            previous = repeated[-1]
            if previous.next_support is not None and (
                previous.next_support.id == support.id or previous.support.id == support.id
            ):
                return _review_after_failed_adaptation(
                    plan,
                    exercise,
                    node,
                    attempt,
                    support,
                    observations,
                    records,
                    signature,
                    selected,
                    created_at_utc,
                )
            if any(item.support.id != support.id for item in repeated):
                return _review_after_failed_adaptation(
                    plan,
                    exercise,
                    node,
                    attempt,
                    support,
                    observations,
                    records,
                    signature,
                    selected,
                    created_at_utc,
                )
            adapted = _adapt_support(support, selected.dimension)
            if adapted is None:
                return _review_after_failed_adaptation(
                    plan,
                    exercise,
                    node,
                    attempt,
                    support,
                    observations,
                    records,
                    signature,
                    selected,
                    created_at_utc,
                )
            return _result(
                plan,
                exercise,
                node,
                attempt,
                support,
                observations,
                records,
                signature,
                PolicyAction.CORRECT,
                created_at_utc,
                target=_target_text(exercise, selected.dimension),
                observation=_observation_text(selected),
                boundary=_support_boundary(support, selected),
                action=(
                    "Retry the same target with one changed condition: "
                    f"{_support_change(support, adapted)}."
                ),
                reason=(
                    "The same discrepancy recurred, so an unchanged repetition is not justified."
                ),
                next_node_id=node.id,
                next_support=adapted,
            )

        timing = (
            FeedbackTiming.IMMEDIATE
            if selected.blocking and attempt.practice_mode in _GUIDED_MODES
            else FeedbackTiming.END_OF_ATTEMPT
        )
        return _result(
            plan,
            exercise,
            node,
            attempt,
            support,
            observations,
            records,
            signature,
            PolicyAction.CORRECT,
            created_at_utc,
            target=_target_text(exercise, selected.dimension),
            observation=_observation_text(selected),
            boundary=_support_boundary(support, selected),
            action=_correction_action(selected),
            reason="A declared target discrepancy must be addressed before progression.",
            next_node_id=node.id,
            timing=timing,
        )

    unsatisfied = tuple(
        record
        for record, requirement in zip(records, exercise.exit_evidence, strict=True)
        if not _satisfies(record.state, requirement.minimum_state)
    )
    if unsatisfied:
        return _result(
            plan,
            exercise,
            node,
            attempt,
            support,
            observations,
            records,
            signature,
            PolicyAction.STABILIZE,
            created_at_utc,
            target=_target_text(exercise, unsatisfied[0].dimension),
            observation="The declared targets matched in this attempt under the recorded support.",
            boundary=_support_boundary(support),
            action="Repeat the same bounded exercise once under the same recorded condition.",
            reason="One matching performance is evidence, but not yet stable evidence.",
            next_node_id=node.id,
        )

    prior_reduction = _successful_support_reduction(support, relevant_history)
    weaker = None if prior_reduction else _reduce_support(support)
    if weaker is not None and _supports_fading(exercise):
        return _result(
            plan,
            exercise,
            node,
            attempt,
            support,
            observations,
            records,
            signature,
            PolicyAction.REDUCE_SUPPORT,
            created_at_utc,
            target=_target_text(exercise, _first_target_dimension(exercise)),
            observation="The declared targets were stable under the current recorded support.",
            boundary=_support_boundary(support),
            action=f"Repeat with one aid removed: {_support_change(support, weaker)}.",
            reason="Stable supported evidence justifies testing one weaker support condition.",
            next_node_id=node.id,
            next_support=weaker,
        )

    action, next_node_id, action_text, reason = _progression(exercise, node, plan)
    return _result(
        plan,
        exercise,
        node,
        attempt,
        support,
        observations,
        records,
        signature,
        action,
        created_at_utc,
        target=_target_text(exercise, _first_target_dimension(exercise)),
        observation="The declared evidence requirement was met under the recorded condition.",
        boundary=_support_boundary(support),
        action=action_text,
        reason=reason,
        next_node_id=next_node_id,
    )


def _request_context(
    plan: LessonPlan,
    attempt: LearnerAttempt,
    support: SupportState,
    observations: tuple[Observation, ...],
    created_at_utc: str,
) -> tuple[Exercise, LessonNode]:
    if not created_at_utc.strip():
        raise TeachingPolicyError("TEACH_POLICY_TIMESTAMP", "decision timestamp is required")
    if attempt.run_id != plan.run_id:
        raise TeachingPolicyError("TEACH_POLICY_RUN", "attempt and plan use different runs")
    exercises = {item.id: item for item in plan.exercises}
    exercise = exercises.get(attempt.exercise_id)
    if exercise is None:
        raise TeachingPolicyError("TEACH_POLICY_EXERCISE", "attempt exercise is absent from plan")
    if attempt.support_state_id != support.id:
        raise TeachingPolicyError(
            "TEACH_POLICY_SUPPORT", "attempt and supplied support state differ"
        )
    if not is_stable_id(support.id):
        raise TeachingPolicyError("TEACH_POLICY_SUPPORT", "support ID is not stable")
    supplied_exercise = replace(exercise, initial_support=support)
    supplied_plan = replace(
        plan,
        exercises=tuple(
            supplied_exercise if item.id == exercise.id else item for item in plan.exercises
        ),
    )
    support_issues = validate_lesson_plan(supplied_plan)
    if support_issues:
        issue = support_issues[0]
        raise TeachingPolicyError(
            "TEACH_POLICY_SUPPORT", f"supplied support is invalid: {issue.code}"
        )
    if attempt.practice_mode not in {mode.value for mode in exercise.practice_modes}:
        raise TeachingPolicyError(
            "TEACH_POLICY_MODE", "attempt practice mode is not permitted by the exercise"
        )
    if not observations:
        raise TeachingPolicyError("TEACH_POLICY_OBSERVATIONS", "attempt has no observations")
    for item in observations:
        if item.attempt_id != attempt.id or item.exercise_id != exercise.id:
            raise TeachingPolicyError(
                "TEACH_POLICY_OBSERVATION_REFERENCE",
                "observation belongs to another attempt or exercise",
            )
    nodes = tuple(item for item in plan.nodes if item.exercise_id == exercise.id)
    if len(nodes) != 1:
        raise TeachingPolicyError(
            "TEACH_POLICY_NODE", "exercise must resolve to exactly one lesson node"
        )
    return exercise, nodes[0]


def _validate_history(history: tuple[TeachingPolicyResult, ...], run_id: str) -> None:
    for item in history:
        if item.decision.run_id != run_id:
            raise TeachingPolicyError("TEACH_POLICY_HISTORY", "history belongs to another run")
        attempt_token = item.attempt_id.split(":", 1)[-1]
        if item.decision.id != f"policy-decision:{attempt_token}":
            raise TeachingPolicyError("TEACH_POLICY_HISTORY", "history identity is inconsistent")
        if item.decision.policy_version != TEACHING_POLICY_VERSION:
            raise TeachingPolicyError("TEACH_POLICY_HISTORY", "history policy version differs")


def _input_problem(attempt: LearnerAttempt, observations: tuple[Observation, ...]) -> str | None:
    if attempt.completion is not AttemptCompletion.COMPLETED:
        return f"The attempt ended as {attempt.completion.value}."
    for item in observations:
        if item.status is ObservationStatus.INVALID_INPUT:
            return _observation_text(item)
        if item.dimension is ObservationDimension.INPUT and (
            item.status is not ObservationStatus.MATCH or item.blocking
        ):
            return _observation_text(item)
    return None


def _human_review_reason(exercise: Exercise, observations: tuple[Observation, ...]) -> str | None:
    required = {item.dimension for item in exercise.exit_evidence}
    by_dimension: dict[ObservationDimension, list[Observation]] = {
        dimension: [] for dimension in required
    }
    for item in observations:
        if item.dimension in by_dimension:
            by_dimension[item.dimension].append(item)
    missing = tuple(dimension for dimension, items in by_dimension.items() if not items)
    if missing:
        names = ", ".join(item.value for item in _ordered_dimensions(missing))
        return f"No observation was available for required dimension(s): {names}."
    for requirement in exercise.exit_evidence:
        if requirement.minimum_state is EvidenceState.HUMAN_REVIEWED:
            return f"The {requirement.dimension.value} target explicitly requires human review."
    uncertain = tuple(
        item
        for item in observations
        if item.dimension in required and item.status in _UNCERTAIN_STATUSES
    )
    if uncertain:
        selected = _prioritized(uncertain)[0]
        return _observation_text(selected)
    return None


def _evidence_records(
    exercise: Exercise,
    attempt: LearnerAttempt,
    observations: tuple[Observation, ...],
    history: tuple[TeachingPolicyResult, ...],
    *,
    forced_state: EvidenceState | None = None,
    extra_limitation: tuple[str, ...] = (),
) -> tuple[EvidenceRecord, ...]:
    result: list[EvidenceRecord] = []
    attempt_token = attempt.id.split(":", 1)[-1]
    for index, requirement in enumerate(exercise.exit_evidence):
        relevant = tuple(item for item in observations if item.dimension is requirement.dimension)
        state = forced_state or _evidence_state(
            requirement,
            relevant,
            attempt.support_state_id,
            history,
        )
        limitations = tuple(
            dict.fromkeys(
                (*extra_limitation, *(text for item in relevant for text in item.limitations))
            )
        )
        result.append(
            EvidenceRecord(
                id=f"evidence-record:{attempt_token}:{index}:{requirement.dimension.value}",
                attempt_id=attempt.id,
                exercise_id=exercise.id,
                requirement_id=requirement.id,
                dimension=requirement.dimension,
                state=state,
                context=requirement.context,
                observation_ids=tuple(item.id for item in relevant),
                support_state_id=attempt.support_state_id,
                limitations=limitations,
            )
        )
    return tuple(result)


def _evidence_state(
    requirement: EvidenceRequirement,
    observations: tuple[Observation, ...],
    support_state_id: str,
    history: tuple[TeachingPolicyResult, ...],
) -> EvidenceState:
    if not observations or any(item.status in _UNCERTAIN_STATUSES for item in observations):
        return EvidenceState.INCONCLUSIVE
    if any(item.status is ObservationStatus.DISCREPANCY for item in observations):
        return EvidenceState.ATTEMPTED
    if not all(item.status is ObservationStatus.MATCH for item in observations):
        return EvidenceState.INCONCLUSIVE
    if requirement.context is EvidenceContext.TRANSFER:
        return EvidenceState.TRANSFERRED
    if requirement.context is EvidenceContext.RETENTION:
        return EvidenceState.RETAINED
    if requirement.context in {EvidenceContext.INDEPENDENT, EvidenceContext.INTEGRATION}:
        return EvidenceState.INDEPENDENT_IN_SESSION

    previous_records = tuple(
        record
        for item in history
        for record in item.evidence_records
        if record.dimension is requirement.dimension
    )
    reduced_support_success = any(
        item.decision.action is PolicyAction.REDUCE_SUPPORT
        and item.next_support is not None
        and item.next_support.id == support_state_id
        for item in history
    )
    if reduced_support_success or any(
        record.support_state_id == support_state_id
        and record.state
        in {
            EvidenceState.ATTEMPTED,
            EvidenceState.CORRECTED_SUPPORTED,
            EvidenceState.STABLE_SUPPORTED,
        }
        and all(
            observation.status is ObservationStatus.MATCH
            for item in history
            if record in item.evidence_records
            for observation in item.observations
            if observation.dimension is requirement.dimension
        )
        for record in previous_records
    ):
        return EvidenceState.STABLE_SUPPORTED
    if any(
        observation.dimension is requirement.dimension
        and observation.status is ObservationStatus.DISCREPANCY
        for item in history
        for observation in item.observations
    ):
        return EvidenceState.CORRECTED_SUPPORTED
    return EvidenceState.ATTEMPTED


def _target_discrepancies(
    exercise: Exercise, observations: tuple[Observation, ...]
) -> tuple[Observation, ...]:
    required = {item.dimension for item in exercise.exit_evidence}
    return tuple(
        item
        for item in observations
        if item.dimension in required and item.status is ObservationStatus.DISCREPANCY
    )


def _discrepancy_signature(
    observations: tuple[Observation, ...], exercise: Exercise
) -> tuple[str, ...]:
    return tuple(
        sorted(
            "|".join(
                (
                    item.dimension.value,
                    item.expected_value or "",
                    item.observed_value or "",
                    ",".join(item.expected_canonical_ids),
                )
            )
            for item in _target_discrepancies(exercise, observations)
        )
    )


def _matching_discrepancy_history(
    signature: tuple[str, ...], history: tuple[TeachingPolicyResult, ...]
) -> tuple[TeachingPolicyResult, ...]:
    if not signature:
        return ()
    return tuple(item for item in history if item.discrepancy_signature == signature)


def _review_after_failed_adaptation(
    plan: LessonPlan,
    exercise: Exercise,
    node: LessonNode,
    attempt: LearnerAttempt,
    support: SupportState,
    observations: tuple[Observation, ...],
    records: tuple[EvidenceRecord, ...],
    signature: tuple[str, ...],
    selected: Observation,
    created_at_utc: str,
) -> TeachingPolicyResult:
    return _result(
        plan,
        exercise,
        node,
        attempt,
        support,
        observations,
        records,
        signature,
        PolicyAction.HUMAN_REVIEW,
        created_at_utc,
        target=_target_text(exercise, selected.dimension),
        observation=_observation_text(selected),
        boundary=(
            "The same discrepancy remained after, or instead of, the one justified support change."
        ),
        action="Pause automatic repetition and request bounded human review.",
        reason="The deterministic policy has no further justified condition change.",
        next_node_id=node.id,
    )


def _result(
    plan: LessonPlan,
    exercise: Exercise,
    node: LessonNode,
    attempt: LearnerAttempt,
    support: SupportState,
    observations: tuple[Observation, ...],
    records: tuple[EvidenceRecord, ...],
    signature: tuple[str, ...],
    policy_action: PolicyAction,
    created_at_utc: str,
    *,
    target: str,
    observation: str,
    boundary: str | None,
    action: str,
    reason: str,
    next_node_id: str | None,
    next_support: SupportState | None = None,
    timing: FeedbackTiming = FeedbackTiming.END_OF_ATTEMPT,
    mastery: AttemptMastery | None = None,
) -> TeachingPolicyResult:
    del node
    attempt_token = attempt.id.split(":", 1)[-1]
    feedback = FeedbackAction(
        id=f"feedback:{attempt_token}:policy",
        evidence_record_ids=tuple(item.id for item in records),
        timing=timing,
        target=target,
        observation=observation,
        boundary=boundary,
        action=action,
        reason=reason,
    )
    decision = PolicyDecision(
        id=f"policy-decision:{attempt_token}",
        run_id=plan.run_id,
        exercise_id=exercise.id,
        action=policy_action,
        evidence_record_ids=tuple(item.id for item in records),
        feedback_id=feedback.id,
        reason=reason,
        policy_version=TEACHING_POLICY_VERSION,
        next_node_id=next_node_id,
        created_at_utc=created_at_utc,
    )
    return TeachingPolicyResult(
        attempt_id=attempt.id,
        exercise_id=exercise.id,
        support=support,
        observations=observations,
        evidence_records=records,
        feedback=feedback,
        decision=decision,
        discrepancy_signature=signature,
        next_support=next_support,
        mastery=mastery,
    )


def summarize_guided_mastery(
    learner_track: LearnerTrack,
    exercise: Exercise,
    support: SupportState,
    observations: tuple[Observation, ...],
    history: tuple[TeachingPolicyResult, ...],
) -> AttemptMastery | None:
    """Summarize one safe Beginner follow-pitch attempt for learner progression."""

    if learner_track is not LearnerTrack.BEGINNER:
        return None
    if not exercise.practice_modes or PracticeMode.FOLLOW_PITCH not in exercise.practice_modes:
        return None
    if any(item.context is not EvidenceContext.ACQUISITION for item in exercise.exit_evidence):
        return None
    supported_dimensions = {
        ObservationDimension.PITCH,
        ObservationDimension.ORDER,
        ObservationDimension.CHORD_SET,
    }
    if any(item.dimension not in supported_dimensions for item in exercise.exit_evidence):
        return None

    pitch = tuple(item for item in observations if item.dimension is ObservationDimension.PITCH)
    expected = tuple(item for item in pitch if item.expected_canonical_ids)
    if not expected:
        return None
    correct = sum(item.status is ObservationStatus.MATCH for item in expected)
    extras = sum(
        item.status is ObservationStatus.DISCREPANCY and not item.expected_canonical_ids
        for item in pitch
    )
    denominator = len(expected) + extras
    green_percent = (100 * correct) // denominator
    reduced_tempo = _is_mastery_slow_support(support)

    if green_percent >= _MASTERY_THRESHOLD_PERCENT:
        action = (
            MasteryAction.RETURN_TO_NORMAL if reduced_tempo else MasteryAction.EXERCISE_COMPLETE
        )
    elif reduced_tempo:
        action = MasteryAction.RETRY
    else:
        previous = history[-1].mastery if history else None
        previous_was_low = (
            previous is not None
            and not previous.reduced_tempo
            and previous.green_percent < _SLOW_DOWN_TRIGGER_PERCENT
        )
        action = (
            MasteryAction.SLOW_DOWN
            if green_percent < _SLOW_DOWN_TRIGGER_PERCENT and previous_was_low
            else MasteryAction.RETRY
        )

    return AttemptMastery(
        correct_note_count=correct,
        expected_note_count=len(expected),
        extra_note_count=extras,
        green_percent=green_percent,
        threshold_percent=_MASTERY_THRESHOLD_PERCENT,
        action=action,
        next_node_id=None,
        reduced_tempo=reduced_tempo,
    )


def _is_mastery_slow_support(support: SupportState) -> bool:
    return support.id.endswith(":mastery-slow")


def _slower_mastery_support(baseline: SupportState) -> SupportState:
    return replace(
        baseline,
        id=f"{baseline.id}:mastery-slow",
        tempo_percent=max(1, int(baseline.tempo_percent * _SLOW_TEMPO_RATIO)),
        tempo_bpm=(
            baseline.tempo_bpm * _SLOW_TEMPO_RATIO if baseline.tempo_bpm is not None else None
        ),
    )


def _prioritized(observations: tuple[Observation, ...]) -> tuple[Observation, ...]:
    priority = {dimension: index for index, dimension in enumerate(_DIMENSION_PRIORITY)}
    return tuple(
        sorted(
            observations,
            key=lambda item: (
                not item.blocking,
                priority.get(item.dimension, len(priority)),
                item.id,
            ),
        )
    )


def _ordered_dimensions(
    dimensions: tuple[ObservationDimension, ...],
) -> tuple[ObservationDimension, ...]:
    priority = {dimension: index for index, dimension in enumerate(_DIMENSION_PRIORITY)}
    return tuple(sorted(dimensions, key=lambda item: priority.get(item, len(priority))))


def _first_target_dimension(exercise: Exercise) -> ObservationDimension:
    return _ordered_dimensions(tuple(item.dimension for item in exercise.exit_evidence))[0]


def _target_text(exercise: Exercise, dimension: ObservationDimension) -> str:
    facts = tuple(item for item in exercise.expected_facts if item.dimension is dimension)
    expected = "; ".join(item.expected_value for item in facts) or dimension.value
    return f"{dimension.value}: {expected}"


def _observation_text(observation: Observation) -> str:
    expected = observation.expected_value or "the declared target"
    observed = observation.observed_value or observation.measured_value or observation.status.value
    location = (
        ", ".join(observation.expected_canonical_ids)
        if observation.expected_canonical_ids
        else "the declared exercise range"
    )
    return f"At {location}, expected {expected}; observed {observed}."


def _support_boundary(support: SupportState, observation: Observation | None = None) -> str:
    aids = [
        label
        for enabled, label in (
            (support.note_names_visible, "note names"),
            (support.keyboard_highlighting, "key highlighting"),
            (support.follow_mode, "follow mode"),
            (support.metronome, "metronome"),
            (support.demonstration_available, "demonstration"),
            (support.prompts_visible, "prompts"),
        )
        if enabled
    ]
    text = f"Evidence applies only to support {support.id}"
    text += f" ({', '.join(aids)})" if aids else " (no listed active aid)"
    if observation is not None and observation.limitations:
        text += "; " + "; ".join(observation.limitations)
    return text + "."


def _correction_action(observation: Observation) -> str:
    if observation.dimension in {ObservationDimension.PITCH, ObservationDimension.ORDER}:
        return "Retry the smallest affected note pattern under the same support."
    if observation.dimension in {
        ObservationDimension.ONSET,
        ObservationDimension.DURATION,
    }:
        return "Count or clap the affected rhythm once, then retry the same bounded passage."
    if observation.dimension is ObservationDimension.CONTINUITY:
        return "Practise only the transition around the observed pause, then retry the passage."
    if observation.dimension is ObservationDimension.CHORD_SET:
        return "Re-form the affected chord, then retry that bounded chord event."
    return "Retry only the smallest affected target under the same recorded support."


def _adapt_support(support: SupportState, dimension: ObservationDimension) -> SupportState | None:
    if dimension in {
        ObservationDimension.PITCH,
        ObservationDimension.ORDER,
        ObservationDimension.CHORD_SET,
    }:
        candidates = (
            ("keyboard-highlighting", "keyboard_highlighting"),
            ("note-names", "note_names_visible"),
            ("demonstration", "demonstration_available"),
            ("prompts", "prompts_visible"),
        )
    else:
        candidates = (
            ("metronome", "metronome"),
            ("cursor", "cursor_visible"),
            ("prompts", "prompts_visible"),
            ("demonstration", "demonstration_available"),
        )
    for label, field_name in candidates:
        if not getattr(support, field_name):
            return _replace_support_flag(
                support,
                field_name,
                True,
                identifier=f"{support.id}:adapt-{label}",
            )
    return None


def _reduce_support(support: SupportState) -> SupportState | None:
    candidates = (
        ("note-names", "note_names_visible"),
        ("key-highlighting", "keyboard_highlighting"),
        ("follow-mode", "follow_mode"),
        ("prompts", "prompts_visible"),
        ("demonstration", "demonstration_available"),
        ("cursor", "cursor_visible"),
        ("fingering", "fingering_visible"),
        ("metronome", "metronome"),
    )
    for label, field_name in candidates:
        if getattr(support, field_name):
            return _replace_support_flag(
                support,
                field_name,
                False,
                identifier=f"{support.id}:without-{label}",
            )
    return None


def _replace_support_flag(
    support: SupportState,
    field_name: str,
    value: bool,
    *,
    identifier: str,
) -> SupportState:
    replacements = {
        "notation_visible": lambda: replace(support, id=identifier, notation_visible=value),
        "cursor_visible": lambda: replace(support, id=identifier, cursor_visible=value),
        "note_names_visible": lambda: replace(support, id=identifier, note_names_visible=value),
        "keyboard_highlighting": lambda: replace(
            support, id=identifier, keyboard_highlighting=value
        ),
        "fingering_visible": lambda: replace(support, id=identifier, fingering_visible=value),
        "demonstration_available": lambda: replace(
            support, id=identifier, demonstration_available=value
        ),
        "follow_mode": lambda: replace(support, id=identifier, follow_mode=value),
        "metronome": lambda: replace(support, id=identifier, metronome=value),
        "prompts_visible": lambda: replace(support, id=identifier, prompts_visible=value),
    }
    replacement = replacements.get(field_name)
    if replacement is None:
        raise TeachingPolicyError(
            "TEACH_POLICY_SUPPORT_CHANGE", f"unsupported support flag {field_name!r}"
        )
    return replacement()


def _support_change(before: SupportState, after: SupportState) -> str:
    labels = {
        "notation_visible": "notation",
        "cursor_visible": "cursor",
        "note_names_visible": "note names",
        "keyboard_highlighting": "key highlighting",
        "fingering_visible": "fingering",
        "demonstration_available": "demonstration",
        "follow_mode": "follow mode",
        "metronome": "metronome",
        "prompts_visible": "prompts",
    }
    changes = tuple(
        f"{label} {'on' if getattr(after, name) else 'off'}"
        for name, label in labels.items()
        if getattr(before, name) != getattr(after, name)
    )
    if len(changes) != 1:
        raise TeachingPolicyError(
            "TEACH_POLICY_SUPPORT_CHANGE", "policy must change exactly one support condition"
        )
    return changes[0]


def _supports_fading(exercise: Exercise) -> bool:
    return any(item.context is EvidenceContext.ACQUISITION for item in exercise.exit_evidence)


def _successful_support_reduction(
    support: SupportState, history: tuple[TeachingPolicyResult, ...]
) -> bool:
    return any(
        item.decision.action is PolicyAction.REDUCE_SUPPORT
        and item.next_support is not None
        and item.next_support.id == support.id
        for item in history
    )


def _progression(
    exercise: Exercise, node: LessonNode, plan: LessonPlan
) -> tuple[PolicyAction, str | None, str, str]:
    nodes = {item.id: item for item in plan.nodes}

    def first(identifier_set: tuple[str, ...]) -> str | None:
        return identifier_set[0] if identifier_set else None

    context = exercise.exit_evidence[0].context
    if context is EvidenceContext.TRANSFER:
        target = first(exercise.transfer_successors) or first(node.successors)
        return (
            PolicyAction.TRANSFER,
            target,
            "Record this bounded transfer evidence and continue only to a "
            "declared transfer successor.",
            "Transfer remains separate from practised-piece performance and causal claims.",
        )
    if context is EvidenceContext.RETENTION:
        target = first(exercise.transfer_successors) or first(node.successors)
        action = PolicyAction.TRANSFER if target else PolicyAction.RETAIN
        text = (
            "Proceed to the declared untrained transfer check."
            if target
            else "Record the retained evidence and end this automatic route."
        )
        return action, target, text, "Retention evidence is preserved separately from acquisition."
    retention = first(exercise.retention_successors)
    if retention is not None:
        return (
            PolicyAction.RETAIN,
            retention,
            "Schedule the declared delayed retrieval node before renewed help.",
            "Independent in-session evidence justifies a retention check, not immediate mastery.",
        )
    integration = first(exercise.integration_successors)
    if integration is not None:
        return (
            PolicyAction.INTEGRATE,
            integration,
            "Continue to the declared integration exercise.",
            "Isolated evidence must survive the larger musical context.",
        )
    transfer = first(exercise.transfer_successors)
    if transfer is not None:
        return (
            PolicyAction.TRANSFER,
            transfer,
            "Continue to the declared untrained transfer check.",
            "The target now requires separate evidence in related untrained material.",
        )
    successor = first(node.successors)
    if successor is not None:
        kind = nodes[successor].kind
        action = {
            LessonNodeKind.RETENTION: PolicyAction.RETAIN,
            LessonNodeKind.TRANSFER: PolicyAction.TRANSFER,
        }.get(kind, PolicyAction.INTEGRATE)
        return (
            action,
            successor,
            "Continue to the next declared lesson node without changing prior evidence.",
            "The current requirement is satisfied and the graph declares the next context.",
        )
    return (
        PolicyAction.HUMAN_REVIEW,
        node.id,
        "Keep the route complete but unresolved until a human reviews the evidence.",
        "The frozen action vocabulary has no automatic completion action for this terminal node.",
    )


def _satisfies(actual: EvidenceState, required: EvidenceState) -> bool:
    if actual in {EvidenceState.INCONCLUSIVE, EvidenceState.HUMAN_REVIEWED}:
        return actual is required
    ranks = {
        EvidenceState.NOT_ATTEMPTED: 0,
        EvidenceState.EXPOSED: 1,
        EvidenceState.ATTEMPTED: 2,
        EvidenceState.CORRECTED_SUPPORTED: 3,
        EvidenceState.STABLE_SUPPORTED: 4,
        EvidenceState.INDEPENDENT_IN_SESSION: 5,
        EvidenceState.RETAINED: 6,
        EvidenceState.TRANSFERRED: 6,
    }
    return ranks.get(actual, -1) >= ranks.get(required, 10)
