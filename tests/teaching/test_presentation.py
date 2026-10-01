"""Tests for exact exercise display and expected-piano demonstration."""

from fractions import Fraction

import pytest

from teachmemusic.analysis import analyze_canonical_score
from teachmemusic.score import CanonicalMusicPackage
from teachmemusic.teaching import (
    ExercisePresentationError,
    LearnerContextSnapshot,
    LearnerTrack,
    build_exercise_presentation,
    exercise_presentation_to_dict,
    generate_beginner_lesson_plan,
    validate_exercise_presentation,
)


def _plan(package: CanonicalMusicPackage):
    return generate_beginner_lesson_plan(
        package,
        analyze_canonical_score(package),
        LearnerContextSnapshot(
            id="learner-context:presentation-test",
            track=LearnerTrack.BEGINNER,
        ),
        run_id="run:presentation-test",
        generated_at_utc="2026-10-01T12:00:00Z",
    )


def test_canonical_exercise_projection_is_exact_bounded_and_traceable(
    hot_cross_buns_package: CanonicalMusicPackage,
) -> None:
    """TEST-PRESENTATION-001: canonical display and playback stay in range."""

    plan = _plan(hot_cross_buns_package)
    exercise = plan.exercises[2]
    value = build_exercise_presentation(
        hot_cross_buns_package,
        plan,
        exercise.id,
    )

    assert validate_exercise_presentation(value) == ()
    assert value.material_kind == "canonical"
    assert value.measure_numbers == ("1", "2")
    assert value.aid_state.tempo_bpm == 60
    assert value.aid_state.count_in_beats == 4
    assert value.notation_renderer_sha256 is not None
    assert value.demonstration.duration_microseconds == 8_000_000
    assert {
        source.measure_id for note in value.demonstration.notes for source in note.source_events
    } <= set(value.measure_ids)
    assert {
        source.event_id for note in value.demonstration.notes for source in note.source_events
    } <= set(value.event_ids)
    encoded = exercise_presentation_to_dict(value)
    assert encoded["expected_content_sha256"] == value.expected_content_sha256
    assert encoded["demonstration"]["duration_microseconds"] == 8_000_000


def test_presentation_aids_do_not_change_expected_content(
    hot_cross_buns_package: CanonicalMusicPackage,
) -> None:
    """TEST-PRESENTATION-002: tempo and count-in are reversible aids only."""

    plan = _plan(hot_cross_buns_package)
    exercise = plan.exercises[2]
    slow = build_exercise_presentation(
        hot_cross_buns_package,
        plan,
        exercise.id,
        tempo_bpm=Fraction(48),
        count_in_enabled=True,
    )
    faster = build_exercise_presentation(
        hot_cross_buns_package,
        plan,
        exercise.id,
        tempo_bpm=Fraction(72),
        count_in_enabled=False,
    )

    assert slow.expected_content_sha256 == faster.expected_content_sha256
    assert slow.measure_ids == faster.measure_ids
    assert slow.event_ids == faster.event_ids
    assert slow.notation_renderer_sha256 == faster.notation_renderer_sha256
    assert slow.demonstration.duration_microseconds > faster.demonstration.duration_microseconds
    assert slow.aid_state.count_in_beats == 4
    assert faster.aid_state.count_in_beats == 0


def test_synthetic_transfer_is_playable_without_becoming_canonical(
    hot_cross_buns_package: CanonicalMusicPackage,
) -> None:
    """TEST-PRESENTATION-003: transfer playback retains its separate identity."""

    plan = _plan(hot_cross_buns_package)
    exercise = plan.exercises[-2]
    value = build_exercise_presentation(hot_cross_buns_package, plan, exercise.id)

    assert validate_exercise_presentation(value) == ()
    assert value.material_kind == "synthetic-transfer"
    assert value.measure_ids == ()
    assert value.notation_renderer_sha256 is None
    assert [note.midi_pitch for note in value.demonstration.notes] == [69, 67, 69]
    assert all(item.startswith("synthetic-event:") for item in value.event_ids)
    assert all(item not in value.event_ids for item in value.provenance_ids)


def test_every_generated_hot_cross_buns_exercise_projects(
    hot_cross_buns_package: CanonicalMusicPackage,
) -> None:
    """TEST-PRESENTATION-004: all 16 generated exercises are executable."""

    plan = _plan(hot_cross_buns_package)
    values = tuple(
        build_exercise_presentation(hot_cross_buns_package, plan, exercise.id)
        for exercise in plan.exercises
    )

    assert len(values) == 16
    assert all(value.demonstration.notes for value in values)
    assert all(validate_exercise_presentation(value) == () for value in values)


def test_projection_rejects_unknown_exercise_and_unbounded_tempo(
    hot_cross_buns_package: CanonicalMusicPackage,
) -> None:
    """TEST-PRESENTATION-005: invalid learner controls fail closed."""

    plan = _plan(hot_cross_buns_package)
    with pytest.raises(ExercisePresentationError, match="TEACH_PRESENTATION_EXERCISE"):
        build_exercise_presentation(hot_cross_buns_package, plan, "exercise:missing")
    with pytest.raises(ExercisePresentationError, match="TEACH_PRESENTATION_TEMPO"):
        build_exercise_presentation(
            hot_cross_buns_package,
            plan,
            plan.exercises[0].id,
            tempo_bpm=401,
        )
