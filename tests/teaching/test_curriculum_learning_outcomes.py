"""Executable DEV-009 Task 9H.1 raw-learning-outcome evidence."""

from __future__ import annotations

from dataclasses import replace
from fractions import Fraction

import pytest

from teachmemusic.performance import (
    AttemptCompletion,
    LearnerAttempt,
    MidiEventKind,
    NormalizedMidiEvent,
    ObservationDimension,
    ObservationStatus,
    RawMidiMessage,
    align_layer_attempt,
)
from teachmemusic.score import CanonicalMusicPackage
from teachmemusic.teaching import (
    CurriculumGameRewardError,
    CurriculumLearningOutcomeError,
    CurriculumResearchRewardError,
    CurriculumSerializationError,
    GameRewardSignal,
    ResearchRewardComponentStatus,
    SupportState,
    build_curriculum_fundamental_practice,
    build_curriculum_game_reward,
    build_curriculum_learning_outcome,
    build_curriculum_research_reward,
    curriculum_game_reward_from_json,
    curriculum_game_reward_to_json,
    curriculum_learning_outcome_from_json,
    curriculum_learning_outcome_to_json,
    curriculum_research_reward_from_json,
    curriculum_research_reward_to_json,
    require_compatible_curriculum_game_reward,
    validate_curriculum_game_reward,
    validate_curriculum_learning_outcome,
    validate_curriculum_research_reward,
)
from tests.teaching.test_curriculum_fundamental_practice import (
    _calibration,
    _resolved_fundamental,
)


def _support() -> SupportState:
    return SupportState(
        id="support:raw-outcome-guided",
        notation_visible=True,
        cursor_visible=True,
        note_names_visible=False,
        keyboard_highlighting=True,
        fingering_visible=False,
        demonstration_available=True,
        follow_mode=True,
        metronome=False,
        tempo_percent=100,
        max_replays=5,
        prompts_visible=True,
        tempo_bpm=Fraction(60),
    )


def _attempt(expected, *, completion: AttemptCompletion = AttemptCompletion.COMPLETED):
    start = 1_000_000
    raw: list[RawMidiMessage] = []
    events: list[NormalizedMidiEvent] = []
    timeline: list[tuple[int, int, bool]] = []
    for index, note in enumerate(expected.notes):
        timeline.extend(
            (
                (start + note.start_microseconds, index, True),
                (start + note.end_microseconds, index, False),
            )
        )
    for sequence, (timestamp, note_index, is_on) in enumerate(sorted(timeline)):
        note = expected.notes[note_index]
        phase = "on" if is_on else "off"
        raw_message = RawMidiMessage(
            id=f"midi-message:outcome-{sequence:04d}-{phase}",
            sequence_number=sequence,
            timestamp_microseconds=timestamp,
            data=((0x90 if is_on else 0x80), note.midi_pitch, 80 if is_on else 0),
        )
        raw.append(raw_message)
        events.append(
            NormalizedMidiEvent(
                id=f"midi-event:outcome-{sequence:04d}-{phase}",
                raw_message_id=raw_message.id,
                kind=MidiEventKind.NOTE_ON if is_on else MidiEventKind.NOTE_OFF,
                timestamp_microseconds=timestamp,
                channel=1,
                note=note.midi_pitch,
                velocity=80 if is_on else 0,
            )
        )
    return LearnerAttempt(
        id="attempt:raw-learning-outcome",
        run_id="run:raw-learning-outcome",
        exercise_id=expected.exercise_id,
        calibration_id="calibration:fundamental-practice",
        practice_mode=expected.practice_mode,
        support_state_id="support:raw-outcome-guided",
        started_at_utc="2026-10-12T18:00:00Z",
        start_microseconds=start,
        end_microseconds=max((item.timestamp_microseconds for item in raw), default=start) + 1,
        completion=completion,
        raw_messages=tuple(raw),
        normalized_events=tuple(events),
    )


def _outcome_inputs(package: CanonicalMusicPackage):
    inputs = _resolved_fundamental(package, primitive_id="PRIM-KEY-001")
    practice = build_curriculum_fundamental_practice(package, *inputs)
    calibration = _calibration()
    support = _support()
    attempt = _attempt(practice.expected)
    observations = align_layer_attempt(practice.expected, attempt, calibration)
    return practice, attempt, calibration, support, observations


def test_raw_learning_outcome_round_trips_without_reward_fields(
    hot_cross_buns_package: CanonicalMusicPackage,
) -> None:
    """TEST-CURR-CONTRACT-013: raw facts round-trip before any reward exists."""

    practice, attempt, calibration, support, observations = _outcome_inputs(hot_cross_buns_package)
    outcome = build_curriculum_learning_outcome(
        practice.binding,
        practice.expected,
        attempt,
        calibration,
        support,
        observations,
    )
    payload = curriculum_learning_outcome_to_json(outcome)

    assert curriculum_learning_outcome_from_json(payload) == outcome
    assert outcome.raw_message_ids == tuple(item.id for item in attempt.raw_messages)
    assert outcome.normalized_event_ids == tuple(item.id for item in attempt.normalized_events)
    assert tuple(item.id for item in outcome.observation_refs) == tuple(
        item.id for item in observations
    )
    assert "reward" not in payload

    with pytest.raises(CurriculumSerializationError, match="unexpected"):
        curriculum_learning_outcome_from_json(
            payload.replace('"resolution"', '"research_reward": 1, "resolution"')
        )


def test_interrupted_attempt_remains_a_factual_outcome_without_fabricated_success(
    hot_cross_buns_package: CanonicalMusicPackage,
) -> None:
    """TEST-CURR-VALIDATION-027: interruption is retained, not scored or discarded."""

    practice, _, calibration, support, _ = _outcome_inputs(hot_cross_buns_package)
    attempt = replace(
        _attempt(practice.expected, completion=AttemptCompletion.INTERRUPTED),
        raw_messages=(),
        normalized_events=(),
        diagnostics=("Learner ended the bounded attempt before playing.",),
    )
    outcome = build_curriculum_learning_outcome(
        practice.binding,
        practice.expected,
        attempt,
        calibration,
        support,
        (),
    )

    assert outcome.completion is AttemptCompletion.INTERRUPTED
    assert outcome.raw_message_ids == ()
    assert outcome.normalized_event_ids == ()
    assert outcome.observation_refs == ()


def test_outcome_rejects_attempt_support_and_event_drift(
    hot_cross_buns_package: CanonicalMusicPackage,
) -> None:
    """TEST-CURR-ROBUSTNESS-031: outcome provenance fails closed on drift."""

    practice, attempt, calibration, support, observations = _outcome_inputs(hot_cross_buns_package)
    outcome = build_curriculum_learning_outcome(
        practice.binding,
        practice.expected,
        attempt,
        calibration,
        support,
        observations,
    )
    drifted = replace(outcome, raw_message_ids=outcome.raw_message_ids[:-1])
    codes = {
        item.code
        for item in validate_curriculum_learning_outcome(
            drifted,
            practice.binding,
            practice.expected,
            attempt,
            calibration,
            support,
            observations,
        )
    }
    assert "TMM-OUTCOME-ATTEMPT-MISMATCH" in codes
    assert "TMM-CONTRACT-FINGERPRINT-MISMATCH" in codes

    with pytest.raises(CurriculumLearningOutcomeError, match="TMM-OUTCOME-SUPPORT"):
        build_curriculum_learning_outcome(
            practice.binding,
            practice.expected,
            attempt,
            calibration,
            replace(support, id="support:other"),
            observations,
        )


def test_research_reward_round_trips_exact_separate_components(
    hot_cross_buns_package: CanonicalMusicPackage,
) -> None:
    """TEST-CURR-CONTRACT-014: exact components retain rules and provenance."""

    practice, attempt, calibration, support, observations = _outcome_inputs(hot_cross_buns_package)
    outcome = build_curriculum_learning_outcome(
        practice.binding,
        practice.expected,
        attempt,
        calibration,
        support,
        observations,
    )
    reward = build_curriculum_research_reward(outcome, practice.expected, observations)
    payload = curriculum_research_reward_to_json(reward)
    components = {item.component_id: item for item in reward.components}

    assert curriculum_research_reward_from_json(payload) == reward
    assert components["attempt-completion"].value == Fraction(1)
    assert components["dimension-match:pitch"].value == Fraction(1)
    assert all(item.calculation_rule.rule_version == "0.1.0" for item in reward.components)
    assert '"total"' not in payload
    assert '"game"' not in payload

    with pytest.raises(CurriculumSerializationError, match="unexpected"):
        curriculum_research_reward_from_json(
            payload.replace('"resolution"', '"total_reward": 1, "resolution"')
        )


def test_reward_uses_null_for_unavailable_components_and_exact_match_fractions(
    hot_cross_buns_package: CanonicalMusicPackage,
) -> None:
    """TEST-CURR-VALIDATION-028: uncertainty is null and rates are rational."""

    practice, attempt, calibration, support, observations = _outcome_inputs(hot_cross_buns_package)
    pitch_index = next(
        index
        for index, item in enumerate(observations)
        if item.dimension is ObservationDimension.PITCH and item.status is ObservationStatus.MATCH
    )
    changed = list(observations)
    changed[pitch_index] = replace(changed[pitch_index], status=ObservationStatus.DISCREPANCY)
    changed_observations = tuple(changed)
    outcome = build_curriculum_learning_outcome(
        practice.binding,
        practice.expected,
        attempt,
        calibration,
        support,
        changed_observations,
    )
    reward = build_curriculum_research_reward(
        outcome,
        practice.expected,
        changed_observations,
    )
    components = {item.component_id: item for item in reward.components}
    pitch = components["dimension-match:pitch"]
    expected_value = Fraction(
        pitch.matched_observation_count,
        pitch.matched_observation_count + pitch.discrepancy_observation_count,
    )

    assert pitch.value == expected_value
    assert pitch.value < 1
    inconclusive = tuple(
        item
        for item in reward.components
        if item.status is ResearchRewardComponentStatus.INCONCLUSIVE
    )
    assert inconclusive
    assert all(item.value is None for item in inconclusive)

    interrupted_attempt = replace(
        attempt,
        completion=AttemptCompletion.INTERRUPTED,
        raw_messages=(),
        normalized_events=(),
    )
    interrupted_outcome = build_curriculum_learning_outcome(
        practice.binding,
        practice.expected,
        interrupted_attempt,
        calibration,
        support,
        (),
    )
    interrupted_reward = build_curriculum_research_reward(
        interrupted_outcome,
        practice.expected,
        (),
    )
    completion = interrupted_reward.components[0]
    assert completion.status is ResearchRewardComponentStatus.INCONCLUSIVE
    assert completion.value is None


def test_research_reward_rejects_source_and_component_drift(
    hot_cross_buns_package: CanonicalMusicPackage,
) -> None:
    """TEST-CURR-ROBUSTNESS-032: reward rules and factual inputs fail closed."""

    practice, attempt, calibration, support, observations = _outcome_inputs(hot_cross_buns_package)
    outcome = build_curriculum_learning_outcome(
        practice.binding,
        practice.expected,
        attempt,
        calibration,
        support,
        observations,
    )
    reward = build_curriculum_research_reward(outcome, practice.expected, observations)
    pitch_index = next(
        index
        for index, item in enumerate(reward.components)
        if item.component_id == "dimension-match:pitch"
    )
    changed_components = list(reward.components)
    changed_components[pitch_index] = replace(changed_components[pitch_index], value=Fraction(0))
    drifted = replace(reward, components=tuple(changed_components))
    codes = {
        item.code
        for item in validate_curriculum_research_reward(
            drifted,
            outcome,
            practice.expected,
            observations,
        )
    }

    assert "TMM-REWARD-VALUE-MISMATCH" in codes
    assert "TMM-CONTRACT-FINGERPRINT-MISMATCH" in codes
    with pytest.raises(CurriculumResearchRewardError, match="TMM-REWARD-OBSERVATION-MISMATCH"):
        build_curriculum_research_reward(outcome, practice.expected, observations[:-1])


def test_game_reward_round_trips_as_a_presentation_only_acknowledgement(
    hot_cross_buns_package: CanonicalMusicPackage,
) -> None:
    """TEST-CURR-CONTRACT-015: game feedback cannot carry policy authority."""

    practice, attempt, calibration, support, observations = _outcome_inputs(hot_cross_buns_package)
    outcome = build_curriculum_learning_outcome(
        practice.binding,
        practice.expected,
        attempt,
        calibration,
        support,
        observations,
    )
    research_reward = build_curriculum_research_reward(
        outcome,
        practice.expected,
        observations,
    )
    game_reward = build_curriculum_game_reward(outcome, research_reward)
    payload = curriculum_game_reward_to_json(game_reward)

    assert curriculum_game_reward_from_json(payload) == game_reward
    assert game_reward.signal is GameRewardSignal.ATTEMPT_ACKNOWLEDGED
    assert game_reward.message_code == "GAME_ATTEMPT_ACKNOWLEDGED"
    assert game_reward.source_component_ids
    for prohibited in ('"mastery"', '"unlock"', '"policy"', '"points"', '"evidence"'):
        assert prohibited not in payload

    with pytest.raises(CurriculumSerializationError, match="unexpected"):
        curriculum_game_reward_from_json(
            payload.replace('"resolution"', '"points": 100, "resolution"')
        )


def test_game_reward_reports_unavailable_result_without_fabricating_success(
    hot_cross_buns_package: CanonicalMusicPackage,
) -> None:
    """TEST-CURR-VALIDATION-029: absent measurements cannot become celebration."""

    practice, attempt, calibration, support, _ = _outcome_inputs(hot_cross_buns_package)
    interrupted_attempt = replace(
        attempt,
        completion=AttemptCompletion.INTERRUPTED,
        raw_messages=(),
        normalized_events=(),
    )
    outcome = build_curriculum_learning_outcome(
        practice.binding,
        practice.expected,
        interrupted_attempt,
        calibration,
        support,
        (),
    )
    research_reward = build_curriculum_research_reward(outcome, practice.expected, ())
    game_reward = build_curriculum_game_reward(outcome, research_reward)

    assert game_reward.signal is GameRewardSignal.RESULT_UNAVAILABLE
    assert game_reward.message_code == "GAME_RESULT_UNAVAILABLE"
    assert game_reward.source_component_ids == ()


def test_game_reward_rejects_signal_and_source_result_drift(
    hot_cross_buns_package: CanonicalMusicPackage,
) -> None:
    """TEST-CURR-ROBUSTNESS-033: display feedback reconstructs from its source."""

    practice, attempt, calibration, support, observations = _outcome_inputs(hot_cross_buns_package)
    outcome = build_curriculum_learning_outcome(
        practice.binding,
        practice.expected,
        attempt,
        calibration,
        support,
        observations,
    )
    research_reward = build_curriculum_research_reward(
        outcome,
        practice.expected,
        observations,
    )
    game_reward = build_curriculum_game_reward(outcome, research_reward)
    drifted = replace(
        game_reward,
        signal=GameRewardSignal.RESULT_UNAVAILABLE,
        message_code="GAME_RESULT_UNAVAILABLE",
        source_component_ids=(),
    )
    codes = {
        item.code for item in validate_curriculum_game_reward(drifted, outcome, research_reward)
    }

    assert "TMM-GAME-REWARD-COMPONENT-MISMATCH" in codes
    assert "TMM-GAME-REWARD-SIGNAL-MISMATCH" in codes
    assert "TMM-CONTRACT-FINGERPRINT-MISMATCH" in codes
    with pytest.raises(CurriculumGameRewardError, match="TMM-GAME-REWARD-INCOMPATIBLE"):
        require_compatible_curriculum_game_reward(drifted, outcome, research_reward)
