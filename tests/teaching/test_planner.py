"""Tests for the deterministic automatic Beginner lesson planner."""

from dataclasses import replace
from fractions import Fraction
from hashlib import sha256
from pathlib import Path

import pytest

from teachmemusic.analysis import analyze_canonical_score
from teachmemusic.score import CanonicalMusicPackage
from teachmemusic.teaching import (
    LearnerContextSnapshot,
    LearnerTrack,
    LessonNodeKind,
    PlannerError,
    PracticeMode,
    SkillDomain,
    generate_beginner_lesson_plan,
    lesson_plan_from_json,
    lesson_plan_to_json,
    validate_lesson_plan,
)

_WHEN = "2026-09-30T12:00:00Z"


def _learner(track: LearnerTrack = LearnerTrack.BEGINNER) -> LearnerContextSnapshot:
    return LearnerContextSnapshot(
        id="learner-context:owner-pilot",
        track=track,
        goals=("Learn the selected score accurately and transferably.",),
    )


def _plan(
    package: CanonicalMusicPackage,
    *,
    run_id: str,
    end_measure_ordinal: int | None = None,
):
    analysis = analyze_canonical_score(package, end_measure_ordinal=end_measure_ordinal)
    return generate_beginner_lesson_plan(
        package,
        analysis,
        _learner(),
        run_id=run_id,
        generated_at_utc=_WHEN,
    )


def _measure_ranges(plan) -> tuple[tuple[int, ...], ...]:
    result = []
    for exercise in plan.exercises:
        if exercise.anchor_set is None:
            continue
        suffixes = tuple(
            int(anchor.canonical_id.rsplit(":m", 1)[1])
            for anchor in exercise.anchor_set.anchors
            if anchor.kind.value == "measure"
        )
        result.append(suffixes)
    return tuple(result)


def test_hot_cross_buns_plan_matches_the_approved_external_oracle_shape(
    hot_cross_buns_package: CanonicalMusicPackage,
) -> None:
    """TEST-PLANNER-001: the amended automatic HCB graph has the approved structure."""

    first = _plan(hot_cross_buns_package, run_id="run:hcb-planner")
    second = _plan(hot_cross_buns_package, run_id="run:hcb-planner")
    kinds = tuple(node.kind for node in first.nodes)

    assert first == second
    assert validate_lesson_plan(first, hot_cross_buns_package) == ()
    serialized = lesson_plan_to_json(first)
    assert lesson_plan_from_json(serialized) == first
    assert sha256(serialized.encode()).hexdigest() == (
        "254ae7cca884ea767df7d33979cf4b44e2474d52d635f55e4aa0bc275892cf00"
    )
    assert len(first.exercises) == len(first.nodes) == 16
    assert kinds.count(LessonNodeKind.EXERCISE) == 8
    assert kinds.count(LessonNodeKind.INTEGRATION) == 4
    assert kinds.count(LessonNodeKind.RETENTION) == 2
    assert kinds.count(LessonNodeKind.TRANSFER) == 2
    assert _measure_ranges(first) == (
        (1, 2, 3, 4, 5, 6, 7, 8),
        (1,),
        (1, 2),
        (1, 2),
        (3, 4),
        (1, 2, 3, 4),
        (5,),
        (6,),
        (5, 6),
        (7, 8),
        (5, 6, 7, 8),
        (1, 2, 3, 4, 5, 6, 7, 8),
        (1, 2, 3, 4, 5, 6, 7, 8),
        (1, 2, 3, 4, 5, 6, 7, 8),
    )
    synthetic = tuple(
        tuple(event.midi_note for event in exercise.synthetic_material.events)
        for exercise in first.exercises
        if exercise.synthetic_material is not None
    )
    assert synthetic == ((69, 67, 69), (71, 71, 71, 71))
    orientation = first.exercises[0]
    assert orientation.practice_modes == (PracticeMode.LISTEN,)
    assert orientation.initial_support.tempo_percent == 70
    assert orientation.initial_support.tempo_bpm == Fraction(336, 5)
    first_bar = first.exercises[1]
    assert first_bar.practice_modes == (PracticeMode.FOLLOW_PITCH,)
    assert first_bar.initial_support.notation_visible is True
    assert first_bar.initial_support.keyboard_highlighting is True
    assert first.exercises[-5].retention_successors
    assert first.exercises[-4].transfer_successors


def test_generic_planner_validates_happy_birthday_and_moonlight_scope(
    happy_birthday_package: CanonicalMusicPackage,
    moonlight_package: CanonicalMusicPackage,
) -> None:
    """TEST-PLANNER-002: the same rules plan layered and complex scores."""

    birthday = _plan(happy_birthday_package, run_id="run:birthday-planner")
    moonlight = _plan(
        moonlight_package,
        run_id="run:moonlight-planner",
        end_measure_ordinal=69,
    )

    assert validate_lesson_plan(birthday, happy_birthday_package) == ()
    assert validate_lesson_plan(moonlight, moonlight_package) == ()
    assert SkillDomain.COORDINATION in birthday.target_skills
    assert SkillDomain.COORDINATION in moonlight.target_skills
    assert any("high structural demand" in item for item in moonlight.diagnostics)
    moonlight_measures = {
        int(anchor.canonical_id.rsplit(":m", 1)[1])
        for exercise in moonlight.exercises
        if exercise.anchor_set is not None
        for anchor in exercise.anchor_set.anchors
        if anchor.kind.value == "measure"
    }
    assert moonlight_measures == set(range(1, 70))


def test_planner_rejects_unapproved_tracks_and_analysis_package_drift(
    hot_cross_buns_package: CanonicalMusicPackage,
    happy_birthday_package: CanonicalMusicPackage,
) -> None:
    """TEST-PLANNER-003: unsupported policy and foreign evidence fail closed."""

    analysis = analyze_canonical_score(hot_cross_buns_package)
    with pytest.raises(PlannerError, match="PLANNER_TRACK"):
        generate_beginner_lesson_plan(
            hot_cross_buns_package,
            analysis,
            _learner(LearnerTrack.ADVANCED),
            run_id="run:advanced",
            generated_at_utc=_WHEN,
        )
    with pytest.raises(ValueError, match="ANALYSIS_PACKAGE"):
        generate_beginner_lesson_plan(
            happy_birthday_package,
            analysis,
            _learner(),
            run_id="run:foreign-analysis",
            generated_at_utc=_WHEN,
        )


def test_synthetic_transfer_material_cannot_masquerade_as_canonical(
    hot_cross_buns_package: CanonicalMusicPackage,
) -> None:
    """TEST-PLANNER-004: transfer events remain explicit non-canonical data."""

    plan = _plan(hot_cross_buns_package, run_id="run:synthetic-boundary")
    transfer = next(
        exercise for exercise in plan.exercises if exercise.synthetic_material is not None
    )
    assert transfer.anchor_set is None
    assert all(
        event.id.startswith("synthetic-event:") for event in transfer.synthetic_material.events
    )

    invalid = replace(transfer, anchor_set=plan.exercises[0].anchor_set)
    exercises = tuple(invalid if item.id == transfer.id else item for item in plan.exercises)
    issues = validate_lesson_plan(
        replace(plan, exercises=exercises),
        hot_cross_buns_package,
    )
    assert "TEACH_MATERIAL_EXCLUSIVE" in {issue.code for issue in issues}

    canonical = plan.exercises[0]
    assert canonical.anchor_set is not None
    anchors = canonical.anchor_set.anchors
    event_index = next(
        index for index, anchor in enumerate(anchors) if anchor.kind.value == "event"
    )
    mislabeled = replace(anchors[event_index], kind=anchors[0].kind)
    changed_anchors = anchors[:event_index] + (mislabeled,) + anchors[event_index + 1 :]
    changed_set = replace(canonical.anchor_set, anchors=changed_anchors)
    changed_exercise = replace(canonical, anchor_set=changed_set)
    changed_exercises = (changed_exercise,) + plan.exercises[1:]
    issues = validate_lesson_plan(
        replace(plan, exercises=changed_exercises),
        hot_cross_buns_package,
    )
    assert "TEACH_ANCHOR_KIND_REFERENCE" in {issue.code for issue in issues}


def test_canonical_mutation_changes_the_automatic_plan(
    hot_cross_buns_package: CanonicalMusicPackage,
) -> None:
    """TEST-PLANNER-005: plan identity and facts are content-bound."""

    analysis = analyze_canonical_score(hot_cross_buns_package)
    changed_analysis = replace(analysis, canonical_digest_sha256="b" * 64)

    with pytest.raises(ValueError, match="ANALYSIS_PACKAGE_DIGEST"):
        generate_beginner_lesson_plan(
            hot_cross_buns_package,
            changed_analysis,
            _learner(),
            run_id="run:mutated-analysis",
            generated_at_utc=_WHEN,
        )


def test_planner_source_contains_no_governed_piece_or_manual_plan_branch() -> None:
    """TEST-PLANNER-006: generation has no title, fixture, or oracle branch."""

    import teachmemusic.teaching.planner as planner_module

    source = Path(planner_module.__file__).read_text()
    forbidden = (
        "Hot Cross Buns",
        "Happy Birthday",
        "Moonlight Sonata",
        "HCB-",
        "TMM-REF-CANDIDATE",
        "tests/fixtures",
        "worked-teaching-plan",
    )

    assert not any(value in source for value in forbidden)
