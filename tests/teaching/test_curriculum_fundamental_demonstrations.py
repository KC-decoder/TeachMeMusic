"""Executable DEV-009 9G.2 functional-demonstration evidence."""

from __future__ import annotations

from dataclasses import replace

import pytest

from teachmemusic.analysis import analyze_canonical_score
from teachmemusic.score import CanonicalMusicPackage
from teachmemusic.teaching import (
    ArtifactResolution,
    CurriculumFundamentalDemonstrationError,
    CurriculumSerializationError,
    NotationCondition,
    build_curriculum_fundamental_demonstration,
    build_curriculum_fundamental_explanation,
    build_curriculum_passage_presentation,
    curriculum_fundamental_demonstration_from_json,
    curriculum_fundamental_demonstration_to_json,
    derive_passage_requirements,
    generate_prerequisite_branches,
    validate_curriculum_fundamental_demonstration,
)


def _resolved_fundamental(
    package: CanonicalMusicPackage,
    *,
    primitive_id: str,
    notation_condition: NotationCondition | None = None,
):
    requirements = derive_passage_requirements(
        package,
        analyze_canonical_score(package, end_measure_ordinal=2),
    )
    branches = generate_prerequisite_branches(requirements)
    scope = next(
        item
        for item in requirements.scopes
        if notation_condition is None or item.notation_condition is notation_condition
    )
    presentation = build_curriculum_passage_presentation(
        package,
        requirements,
        scope.id,
    )
    requirement = next(
        item
        for item in requirements.requirements
        if item.practice_scope_ref.id == scope.id and item.primitive_ref.id == primitive_id
    )
    explanation = build_curriculum_fundamental_explanation(
        requirements,
        branches,
        presentation,
        requirement.id,
    )
    return requirements, branches, presentation, explanation


def test_fundamental_demonstration_is_deterministic_and_strictly_serialized(
    hot_cross_buns_package: CanonicalMusicPackage,
) -> None:
    """TEST-CURR-CONTRACT-010: the prerequisite demonstration round-trips."""

    requirements, branches, presentation, explanation = _resolved_fundamental(
        hot_cross_buns_package,
        primitive_id="PRIM-KEY-001",
    )
    first = build_curriculum_fundamental_demonstration(
        hot_cross_buns_package,
        requirements,
        branches,
        presentation,
        explanation,
        tempo_bpm=72,
    )
    second = build_curriculum_fundamental_demonstration(
        hot_cross_buns_package,
        requirements,
        branches,
        presentation,
        explanation,
        tempo_bpm=72,
    )
    payload = curriculum_fundamental_demonstration_to_json(first.binding)

    assert first == second
    assert first.binding.explanation_ref.id == explanation.id
    assert first.binding.prerequisite_exercise_ref == explanation.prerequisite_exercise_ref
    assert first.binding.return_node_id == explanation.return_node_id
    assert first.binding.focus_event_ids == explanation.focus_event_ids
    assert len(first.binding.playback_source_event_ids) == 3
    assert len(first.binding.silent_active_event_ids) == 1
    assert first.binding.tempo_bpm == 72
    assert first.playback.tempo_controls[0].quarter_notes_per_minute == 72
    assert '"type": "curriculum-fundamental-demonstration"' in payload
    assert curriculum_fundamental_demonstration_from_json(payload) == first.binding
    assert curriculum_fundamental_demonstration_to_json(first.binding) == payload
    with pytest.raises(CurriculumSerializationError, match="unexpected"):
        curriculum_fundamental_demonstration_from_json(
            payload.replace('"tempo_bpm"', '"unexpected": true, "tempo_bpm"')
        )


def test_layered_fundamental_demonstration_keeps_sound_in_the_selected_layer(
    happy_birthday_package: CanonicalMusicPackage,
) -> None:
    """TEST-CURR-VALIDATION-025: one prerequisite uses one written layer."""

    requirements, branches, presentation, explanation = _resolved_fundamental(
        happy_birthday_package,
        primitive_id="PRIM-HAR-001",
        notation_condition=NotationCondition.LOWER_LAYER,
    )
    projection = build_curriculum_fundamental_demonstration(
        happy_birthday_package,
        requirements,
        branches,
        presentation,
        explanation,
    )
    sources = set(projection.binding.playback_source_event_ids)

    assert sources
    assert sources <= set(presentation.active_target_ids)
    assert sources.isdisjoint(presentation.inactive_context_ids)
    assert sources | set(projection.binding.silent_active_event_ids) == set(
        presentation.active_target_ids
    )
    assert projection.binding.return_node_id == explanation.return_node_id
    assert (
        validate_curriculum_fundamental_demonstration(
            projection.binding,
            explanation,
            requirements,
            branches,
            presentation,
            projection.playback,
        )
        == ()
    )


def test_demonstration_rejects_provenance_and_playback_drift(
    hot_cross_buns_package: CanonicalMusicPackage,
) -> None:
    """TEST-CURR-ROBUSTNESS-026: activity, layer, and playback drift fail closed."""

    requirements, branches, presentation, explanation = _resolved_fundamental(
        hot_cross_buns_package,
        primitive_id="PRIM-KEY-001",
    )
    projection = build_curriculum_fundamental_demonstration(
        hot_cross_buns_package,
        requirements,
        branches,
        presentation,
        explanation,
    )
    changed = replace(
        projection.binding,
        demonstration_activity_id="exercise-activity:foreign",
        playback_source_event_ids=projection.binding.playback_source_event_ids[1:],
    )
    codes = {
        item.code
        for item in validate_curriculum_fundamental_demonstration(
            changed,
            explanation,
            requirements,
            branches,
            presentation,
            projection.playback,
        )
    }

    assert "TMM-DEMONSTRATION-ACTIVITY-MISMATCH" in codes
    assert "TMM-DEMONSTRATION-ACTIVE-PARTITION" in codes
    assert "TMM-DEMONSTRATION-PLAYBACK-MISMATCH" in codes
    assert "TMM-CONTRACT-FINGERPRINT-MISMATCH" in codes


def test_unresolved_complex_topology_cannot_emit_a_demonstration(
    moonlight_package: CanonicalMusicPackage,
    hot_cross_buns_package: CanonicalMusicPackage,
) -> None:
    """TEST-CURR-ROBUSTNESS-027: unresolved pedagogy has no demonstration."""

    moonlight_requirements = derive_passage_requirements(
        moonlight_package,
        analyze_canonical_score(moonlight_package, end_measure_ordinal=69),
    )
    moonlight_branches = generate_prerequisite_branches(moonlight_requirements)
    requirements, _, presentation, explanation = _resolved_fundamental(
        hot_cross_buns_package,
        primitive_id="PRIM-KEY-001",
    )

    assert moonlight_branches.resolution is ArtifactResolution.REVIEW_REQUIRED
    assert moonlight_branches.exercises == ()
    with pytest.raises(
        CurriculumFundamentalDemonstrationError,
        match="TMM-DEMONSTRATION-BRANCH-UNRESOLVED",
    ):
        build_curriculum_fundamental_demonstration(
            hot_cross_buns_package,
            requirements,
            moonlight_branches,
            presentation,
            explanation,
        )
