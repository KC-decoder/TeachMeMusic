"""Tests for the frozen deterministic teaching policy."""

from dataclasses import replace
from fractions import Fraction

import pytest

from teachmemusic.performance import (
    AttemptCompletion,
    EvidenceConfidence,
    LearnerAttempt,
    Observation,
    ObservationDimension,
    ObservationSource,
    ObservationStatus,
)
from teachmemusic.teaching import (
    TEACHING_POLICY_VERSION,
    EvidenceContext,
    EvidenceState,
    LearnerTrack,
    LessonNode,
    LessonNodeKind,
    MasteryAction,
    PolicyAction,
    PracticeMode,
    TeachingPolicyError,
    apply_teaching_policy,
    validate_evidence_export,
    validate_lesson_plan,
)
from tests.teaching.test_contracts import valid_evidence_export, valid_lesson_plan


def _plan(
    *,
    minimum: EvidenceState = EvidenceState.STABLE_SUPPORTED,
    context: EvidenceContext = EvidenceContext.ACQUISITION,
    successor_kind: LessonNodeKind | None = None,
):
    plan = valid_lesson_plan()
    source = plan.exercises[0]
    requirement = replace(source.exit_evidence[0], minimum_state=minimum, context=context)
    support = source.initial_support
    if context in {EvidenceContext.INDEPENDENT, EvidenceContext.RETENTION}:
        support = replace(
            support,
            cursor_visible=False,
            note_names_visible=False,
            keyboard_highlighting=False,
            demonstration_available=False,
            follow_mode=False,
            metronome=False,
            prompts_visible=False,
        )
    source = replace(source, exit_evidence=(requirement,), initial_support=support)
    if successor_kind is None:
        result = replace(plan, exercises=(source,))
        assert validate_lesson_plan(result) == ()
        return result

    target = replace(
        source,
        id="exercise:two",
        anchor_set=replace(source.anchor_set, id="anchor-set:two"),  # type: ignore[arg-type]
        task_demands=(replace(source.task_demands[0], id="demand:two"),),
        expected_facts=(replace(source.expected_facts[0], id="expected-fact:two"),),
        exit_evidence=(
            replace(
                requirement,
                id="evidence-requirement:two",
            ),
        ),
        initial_support=replace(support, id="support:two"),
        integration_successors=(),
        retention_successors=(),
        transfer_successors=(),
    )
    first_node = replace(plan.nodes[0], successors=("lesson-node:two",))
    second_node = LessonNode(
        id="lesson-node:two",
        kind=successor_kind,
        exercise_id=target.id,
        prerequisites=(first_node.id,),
    )
    successors = {
        LessonNodeKind.INTEGRATION: {"integration_successors": (second_node.id,)},
        LessonNodeKind.RETENTION: {"retention_successors": (second_node.id,)},
        LessonNodeKind.TRANSFER: {"transfer_successors": (second_node.id,)},
    }[successor_kind]
    source = replace(source, **successors)
    result = replace(
        plan,
        exercises=(source, target),
        nodes=(first_node, second_node),
    )
    assert validate_lesson_plan(result) == ()
    return result


def _attempt(plan, *, serial: int = 1, support=None, mode: str | None = None):
    exercise = plan.exercises[0]
    support = support or exercise.initial_support
    return LearnerAttempt(
        id=f"attempt:policy-{serial}",
        run_id=plan.run_id,
        exercise_id=exercise.id,
        calibration_id="calibration:policy",
        practice_mode=mode or exercise.practice_modes[0].value,
        support_state_id=support.id,
        started_at_utc=f"2026-10-01T22:{serial:02d}:00Z",
        start_microseconds=0,
        end_microseconds=1_000_000,
        completion=AttemptCompletion.COMPLETED,
    )


def _observations(
    attempt: LearnerAttempt,
    status: ObservationStatus,
    *,
    blocking: bool = False,
    dimension: ObservationDimension = ObservationDimension.PITCH,
):
    return (
        Observation(
            id=f"observation:{attempt.id.split(':', 1)[1]}:input",
            attempt_id=attempt.id,
            exercise_id=attempt.exercise_id,
            dimension=ObservationDimension.INPUT,
            status=ObservationStatus.MATCH,
            source=ObservationSource.MIDI,
            expected_value="complete calibrated input",
            observed_value="complete calibrated input",
            confidence=EvidenceConfidence.HIGH,
        ),
        Observation(
            id=f"observation:{attempt.id.split(':', 1)[1]}:{dimension.value}",
            attempt_id=attempt.id,
            exercise_id=attempt.exercise_id,
            dimension=dimension,
            status=status,
            source=ObservationSource.MIDI,
            expected_canonical_ids=("event:score-note-1",),
            observed_event_ids=(f"midi-event:{attempt.id.split(':', 1)[1]}",),
            expected_value="midi:60",
            observed_value="midi:60" if status is ObservationStatus.MATCH else "midi:62",
            matching_policy="test-policy",
            confidence=EvidenceConfidence.HIGH,
            blocking=blocking,
        ),
    )


def _pitch_attempt_observations(
    attempt: LearnerAttempt,
    statuses: tuple[ObservationStatus, ...],
    *,
    extra: int = 0,
) -> tuple[Observation, ...]:
    items = [
        Observation(
            id=f"observation:{attempt.id.split(':', 1)[1]}:input",
            attempt_id=attempt.id,
            exercise_id=attempt.exercise_id,
            dimension=ObservationDimension.INPUT,
            status=ObservationStatus.MATCH,
            source=ObservationSource.MIDI,
            expected_value="complete calibrated input",
            observed_value="complete calibrated input",
            confidence=EvidenceConfidence.HIGH,
        )
    ]
    for index, status in enumerate(statuses):
        items.append(
            Observation(
                id=f"observation:{attempt.id.split(':', 1)[1]}:pitch:{index}",
                attempt_id=attempt.id,
                exercise_id=attempt.exercise_id,
                dimension=ObservationDimension.PITCH,
                status=status,
                source=ObservationSource.MIDI,
                expected_canonical_ids=(f"event:score-note-{index + 1}",),
                observed_event_ids=(f"midi-event:{index + 1}",),
                expected_value="midi:60",
                observed_value="midi:60" if status is ObservationStatus.MATCH else "missing",
                matching_policy="test-policy",
                confidence=EvidenceConfidence.HIGH,
                blocking=status is not ObservationStatus.MATCH,
            )
        )
    for index in range(extra):
        items.append(
            Observation(
                id=f"observation:{attempt.id.split(':', 1)[1]}:extra:{index}",
                attempt_id=attempt.id,
                exercise_id=attempt.exercise_id,
                dimension=ObservationDimension.PITCH,
                status=ObservationStatus.DISCREPANCY,
                source=ObservationSource.MIDI,
                observed_event_ids=(f"midi-extra:{index + 1}",),
                expected_value="no unmatched played note",
                observed_value="extra-unmatched-midi:62",
                matching_policy="test-policy",
                confidence=EvidenceConfidence.HIGH,
                blocking=True,
            )
        )
    return tuple(items)


def _apply(plan, attempt, observations, **kwargs):
    return apply_teaching_policy(
        plan,
        attempt,
        kwargs.pop("support", plan.exercises[0].initial_support),
        observations,
        created_at_utc="2026-10-01T23:00:00Z",
        **kwargs,
    )


def test_policy_corrects_blocking_guided_discrepancy_immediately() -> None:
    """TEST-POLICY-001: guided blocking facts receive bounded correction."""

    plan = _plan()
    exercise = replace(plan.exercises[0], practice_modes=(PracticeMode.FOLLOW_PITCH,))
    plan = replace(plan, exercises=(exercise,))
    attempt = _attempt(plan, mode=PracticeMode.FOLLOW_PITCH.value)

    result = _apply(
        plan, attempt, _observations(attempt, ObservationStatus.DISCREPANCY, blocking=True)
    )

    assert result.decision.action is PolicyAction.CORRECT
    assert result.feedback.timing.value == "end-of-attempt"
    assert result.mastery is not None
    assert result.mastery.action is MasteryAction.RETRY
    assert result.mastery.green_percent == 0
    assert result.decision.next_node_id == plan.nodes[0].id
    assert result.decision.policy_version == TEACHING_POLICY_VERSION
    assert result.evidence_records[0].state is EvidenceState.ATTEMPTED


def test_follow_pitch_mastery_completes_at_95_percent_and_advances() -> None:
    """TEST-POLICY-011: a safe 95% follow-pitch result advances the graph."""

    plan = _plan(successor_kind=LessonNodeKind.INTEGRATION)
    source = replace(
        plan.exercises[0],
        practice_modes=(PracticeMode.FOLLOW_PITCH,),
        initial_support=replace(
            plan.exercises[0].initial_support,
            tempo_percent=100,
            tempo_bpm=Fraction(60),
        ),
    )
    plan = replace(plan, exercises=(source, plan.exercises[1]))
    attempt = _attempt(plan, mode=PracticeMode.FOLLOW_PITCH.value)
    observations = _pitch_attempt_observations(
        attempt,
        (ObservationStatus.MATCH,) * 19 + (ObservationStatus.DISCREPANCY,),
    )

    result = _apply(plan, attempt, observations)

    assert result.mastery is not None
    assert result.mastery.green_percent == 95
    assert result.mastery.action is MasteryAction.EXERCISE_COMPLETE
    assert result.mastery.next_node_id == plan.nodes[1].id
    assert result.decision.next_node_id == plan.nodes[1].id


def test_follow_pitch_mastery_slows_after_two_low_attempts_then_restores_tempo() -> None:
    """TEST-POLICY-012: repeated low evidence slows, then requires normal-speed mastery."""

    plan = _plan(successor_kind=LessonNodeKind.INTEGRATION)
    source = replace(
        plan.exercises[0],
        practice_modes=(PracticeMode.FOLLOW_PITCH,),
        initial_support=replace(
            plan.exercises[0].initial_support,
            tempo_percent=100,
            tempo_bpm=Fraction(60),
        ),
    )
    plan = replace(plan, exercises=(source, plan.exercises[1]))

    first_attempt = _attempt(plan, serial=1, mode=PracticeMode.FOLLOW_PITCH.value)
    first = _apply(
        plan,
        first_attempt,
        _pitch_attempt_observations(
            first_attempt,
            (ObservationStatus.MATCH, ObservationStatus.DISCREPANCY, ObservationStatus.DISCREPANCY),
        ),
    )
    assert first.mastery is not None
    assert first.mastery.action is MasteryAction.RETRY

    second_attempt = _attempt(plan, serial=2, mode=PracticeMode.FOLLOW_PITCH.value)
    second = _apply(
        plan,
        second_attempt,
        _pitch_attempt_observations(
            second_attempt,
            (ObservationStatus.MATCH, ObservationStatus.DISCREPANCY, ObservationStatus.DISCREPANCY),
        ),
        history=(first,),
    )
    assert second.mastery is not None
    assert second.mastery.action is MasteryAction.SLOW_DOWN
    assert second.next_support is not None
    assert second.next_support.tempo_bpm == source.initial_support.tempo_bpm * Fraction(7, 10)

    slow = second.next_support
    third_attempt = _attempt(
        plan,
        serial=3,
        support=slow,
        mode=PracticeMode.FOLLOW_PITCH.value,
    )
    third = _apply(
        plan,
        third_attempt,
        _pitch_attempt_observations(third_attempt, (ObservationStatus.MATCH,) * 3),
        support=slow,
        history=(first, second),
    )
    assert third.mastery is not None
    assert third.mastery.action is MasteryAction.RETURN_TO_NORMAL
    assert third.next_support == source.initial_support

    fourth_attempt = _attempt(plan, serial=4, mode=PracticeMode.FOLLOW_PITCH.value)
    fourth = _apply(
        plan,
        fourth_attempt,
        _pitch_attempt_observations(fourth_attempt, (ObservationStatus.MATCH,) * 3),
        history=(first, second, third),
    )
    assert fourth.mastery is not None
    assert fourth.mastery.action is MasteryAction.EXERCISE_COMPLETE


def test_follow_pitch_mastery_does_not_extend_beyond_beginner_track() -> None:
    """TEST-POLICY-013: the bounded mastery rule cannot grade another track."""

    plan = _plan()
    exercise = replace(plan.exercises[0], practice_modes=(PracticeMode.FOLLOW_PITCH,))
    plan = replace(plan, track=LearnerTrack.INTERMEDIATE, exercises=(exercise,))
    attempt = _attempt(plan, mode=PracticeMode.FOLLOW_PITCH.value)

    result = _apply(
        plan,
        attempt,
        _pitch_attempt_observations(attempt, (ObservationStatus.MATCH,)),
    )

    assert result.mastery is None
    assert result.decision.action is PolicyAction.STABILIZE


def test_policy_stabilizes_then_reduces_exactly_one_support() -> None:
    """TEST-POLICY-002: evidence, not a score or retry count, fades one aid."""

    plan = _plan()
    first_attempt = _attempt(plan, serial=1)
    first = _apply(plan, first_attempt, _observations(first_attempt, ObservationStatus.MATCH))
    second_attempt = _attempt(plan, serial=2)
    second = _apply(
        plan,
        second_attempt,
        _observations(second_attempt, ObservationStatus.MATCH),
        history=(first,),
    )

    assert first.decision.action is PolicyAction.STABILIZE
    assert first.evidence_records[0].state is EvidenceState.ATTEMPTED
    assert second.evidence_records[0].state is EvidenceState.STABLE_SUPPORTED
    assert second.decision.action is PolicyAction.REDUCE_SUPPORT
    assert second.next_support is not None
    changed = tuple(
        name
        for name in (
            "cursor_visible",
            "note_names_visible",
            "keyboard_highlighting",
            "demonstration_available",
            "follow_mode",
            "metronome",
            "prompts_visible",
        )
        if getattr(second.support, name) != getattr(second.next_support, name)
    )
    assert changed == ("note_names_visible",)


def test_repeated_unchanged_error_adapts_once_then_requests_review() -> None:
    """TEST-POLICY-003: unchanged errors cannot loop or auto-unlock."""

    plan = _plan()
    source = plan.exercises[0]
    source = replace(
        source,
        initial_support=replace(source.initial_support, keyboard_highlighting=False),
    )
    plan = replace(plan, exercises=(source,))
    first_attempt = _attempt(plan, serial=1)
    first = _apply(
        plan,
        first_attempt,
        _observations(first_attempt, ObservationStatus.DISCREPANCY, blocking=True),
    )
    second_attempt = _attempt(plan, serial=2)
    second = _apply(
        plan,
        second_attempt,
        _observations(second_attempt, ObservationStatus.DISCREPANCY, blocking=True),
        history=(first,),
    )
    assert second.decision.action is PolicyAction.CORRECT
    assert second.next_support is not None

    adapted = second.next_support
    third_attempt = _attempt(plan, serial=3, support=adapted)
    third = _apply(
        plan,
        third_attempt,
        _observations(third_attempt, ObservationStatus.DISCREPANCY, blocking=True),
        support=adapted,
        history=(first, second),
    )

    assert third.decision.action is PolicyAction.HUMAN_REVIEW
    assert third.decision.next_node_id == plan.nodes[0].id
    assert third.next_support is None


@pytest.mark.parametrize(
    ("status", "completion", "expected_action"),
    [
        (ObservationStatus.INVALID_INPUT, AttemptCompletion.COMPLETED, PolicyAction.INCONCLUSIVE),
        (ObservationStatus.MATCH, AttemptCompletion.INTERRUPTED, PolicyAction.INCONCLUSIVE),
        (ObservationStatus.UNOBSERVABLE, AttemptCompletion.COMPLETED, PolicyAction.HUMAN_REVIEW),
        (ObservationStatus.AMBIGUOUS, AttemptCompletion.COMPLETED, PolicyAction.HUMAN_REVIEW),
    ],
)
def test_policy_uncertainty_routes_fail_closed(status, completion, expected_action) -> None:
    """TEST-POLICY-004: invalid, partial, ambiguous, and unobservable facts fail closed."""

    plan = _plan()
    attempt = replace(_attempt(plan), completion=completion)
    observations = list(
        _observations(attempt, status, blocking=status is not ObservationStatus.MATCH)
    )
    if status is ObservationStatus.INVALID_INPUT:
        observations[0] = replace(observations[0], status=status, blocking=True)

    result = _apply(plan, attempt, tuple(observations))

    assert result.decision.action is expected_action
    assert all(item.state is EvidenceState.INCONCLUSIVE for item in result.evidence_records)
    assert result.decision.next_node_id == plan.nodes[0].id


def test_policy_safety_report_stops_without_diagnosis() -> None:
    """TEST-POLICY-005: learner discomfort overrides ordinary progression."""

    plan = _plan()
    attempt = _attempt(plan)
    result = _apply(
        plan,
        attempt,
        _observations(attempt, ObservationStatus.MATCH),
        unsafe_condition="wrist pain",
    )

    assert result.decision.action is PolicyAction.SAFE_STOP
    assert result.decision.next_node_id is None
    assert "cannot diagnose" in (result.feedback.boundary or "")
    assert "wrist pain" not in result.feedback.reason


@pytest.mark.parametrize(
    ("context", "minimum", "kind", "expected_action", "expected_state"),
    [
        (
            EvidenceContext.INTEGRATION,
            EvidenceState.INDEPENDENT_IN_SESSION,
            LessonNodeKind.INTEGRATION,
            PolicyAction.INTEGRATE,
            EvidenceState.INDEPENDENT_IN_SESSION,
        ),
        (
            EvidenceContext.INDEPENDENT,
            EvidenceState.INDEPENDENT_IN_SESSION,
            LessonNodeKind.RETENTION,
            PolicyAction.RETAIN,
            EvidenceState.INDEPENDENT_IN_SESSION,
        ),
        (
            EvidenceContext.RETENTION,
            EvidenceState.RETAINED,
            LessonNodeKind.TRANSFER,
            PolicyAction.TRANSFER,
            EvidenceState.RETAINED,
        ),
    ],
)
def test_policy_routes_integration_retention_and_transfer(
    context, minimum, kind, expected_action, expected_state
) -> None:
    """TEST-POLICY-006: later evidence contexts remain separate and graph-bound."""

    plan = _plan(minimum=minimum, context=context, successor_kind=kind)
    attempt = _attempt(plan)
    result = _apply(plan, attempt, _observations(attempt, ObservationStatus.MATCH))

    assert result.evidence_records[0].state is expected_state
    assert result.decision.action is expected_action
    assert result.decision.next_node_id == plan.nodes[1].id


def test_policy_requires_explicit_human_review_evidence() -> None:
    """TEST-POLICY-007: automated matching cannot fabricate human-reviewed evidence."""

    plan = _plan(minimum=EvidenceState.HUMAN_REVIEWED)
    attempt = _attempt(plan)
    result = _apply(plan, attempt, _observations(attempt, ObservationStatus.MATCH))

    assert result.decision.action is PolicyAction.HUMAN_REVIEW
    assert result.evidence_records[0].state is EvidenceState.INCONCLUSIVE


def test_policy_rejects_cross_run_history() -> None:
    """TEST-POLICY-008: history cannot silently cross run or policy boundaries."""

    plan = _plan()
    first_attempt = _attempt(plan)
    first = _apply(plan, first_attempt, _observations(first_attempt, ObservationStatus.MATCH))
    attempt = _attempt(plan, serial=2)
    bad = replace(first, decision=replace(first.decision, run_id="run:other"))

    with pytest.raises(TeachingPolicyError, match="TEACH_POLICY_HISTORY"):
        _apply(
            plan,
            attempt,
            _observations(attempt, ObservationStatus.MATCH),
            history=(bad,),
        )


def test_policy_outputs_fit_the_existing_evidence_envelope() -> None:
    """TEST-POLICY-009: policy records preserve the frozen export contracts."""

    export = valid_evidence_export()
    plan = export.plans[0]
    attempt = export.performance.attempts[0]
    result = apply_teaching_policy(
        plan,
        attempt,
        plan.exercises[0].initial_support,
        export.performance.observations,
        created_at_utc="2026-10-01T23:30:00Z",
    )
    completed = replace(
        export,
        evidence_records=result.evidence_records,
        feedback_actions=(result.feedback,),
        policy_decisions=(result.decision,),
        run_events=(),
    )

    assert validate_evidence_export(completed) == ()


def test_policy_table_covers_every_frozen_action() -> None:
    """TEST-POLICY-010: tests exercise the complete frozen action vocabulary."""

    acquisition = _plan()
    mismatch_attempt = _attempt(acquisition, serial=10)
    correct = _apply(
        acquisition,
        mismatch_attempt,
        _observations(mismatch_attempt, ObservationStatus.DISCREPANCY),
    )
    first_attempt = _attempt(acquisition, serial=11)
    stabilize = _apply(
        acquisition,
        first_attempt,
        _observations(first_attempt, ObservationStatus.MATCH),
    )
    second_attempt = _attempt(acquisition, serial=12)
    reduce_support = _apply(
        acquisition,
        second_attempt,
        _observations(second_attempt, ObservationStatus.MATCH),
        history=(stabilize,),
    )

    integration_plan = _plan(
        minimum=EvidenceState.INDEPENDENT_IN_SESSION,
        context=EvidenceContext.INTEGRATION,
        successor_kind=LessonNodeKind.INTEGRATION,
    )
    integration_attempt = _attempt(integration_plan, serial=13)
    integrate = _apply(
        integration_plan,
        integration_attempt,
        _observations(integration_attempt, ObservationStatus.MATCH),
    )
    independent_plan = _plan(
        minimum=EvidenceState.INDEPENDENT_IN_SESSION,
        context=EvidenceContext.INDEPENDENT,
        successor_kind=LessonNodeKind.RETENTION,
    )
    independent_attempt = _attempt(independent_plan, serial=14)
    retain = _apply(
        independent_plan,
        independent_attempt,
        _observations(independent_attempt, ObservationStatus.MATCH),
    )
    retention_plan = _plan(
        minimum=EvidenceState.RETAINED,
        context=EvidenceContext.RETENTION,
        successor_kind=LessonNodeKind.TRANSFER,
    )
    retention_attempt = _attempt(retention_plan, serial=15)
    transfer = _apply(
        retention_plan,
        retention_attempt,
        _observations(retention_attempt, ObservationStatus.MATCH),
    )

    invalid_attempt = replace(
        _attempt(acquisition, serial=16), completion=AttemptCompletion.INPUT_FAILURE
    )
    inconclusive = _apply(
        acquisition,
        invalid_attempt,
        _observations(invalid_attempt, ObservationStatus.MATCH),
    )
    review_attempt = _attempt(acquisition, serial=17)
    human_review = _apply(
        acquisition,
        review_attempt,
        _observations(review_attempt, ObservationStatus.UNOBSERVABLE, blocking=True),
    )
    stop_attempt = _attempt(acquisition, serial=18)
    safe_stop = _apply(
        acquisition,
        stop_attempt,
        _observations(stop_attempt, ObservationStatus.MATCH),
        unsafe_condition="unsafe discomfort",
    )

    emitted = {
        item.decision.action
        for item in (
            correct,
            stabilize,
            reduce_support,
            integrate,
            retain,
            transfer,
            inconclusive,
            human_review,
            safe_stop,
        )
    }
    assert emitted == set(PolicyAction)
