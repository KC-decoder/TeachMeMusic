"""Executable DEV-009 9C curriculum-to-presentation evidence."""

from __future__ import annotations

import json
from dataclasses import replace

import pytest

from teachmemusic.analysis import analyze_canonical_score
from teachmemusic.score import CanonicalMusicPackage
from teachmemusic.teaching import (
    ArtifactResolution,
    CurriculumPassageGuidance,
    CurriculumPresentationError,
    CurriculumSerializationError,
    NotationCondition,
    build_curriculum_expected_playback,
    build_curriculum_passage_guidance,
    build_curriculum_passage_presentation,
    curriculum_passage_guidance_from_json,
    curriculum_passage_guidance_to_json,
    curriculum_passage_presentation_from_json,
    curriculum_passage_presentation_to_json,
    derive_passage_requirements,
    validate_curriculum_passage_guidance,
    validate_curriculum_passage_presentation,
)


def test_bounded_curriculum_presentation_has_strict_deterministic_round_trip(
    hot_cross_buns_package: CanonicalMusicPackage,
) -> None:
    """TEST-CURR-CONTRACT-005: a bounded presentation round-trips exactly."""

    requirements = derive_passage_requirements(
        hot_cross_buns_package,
        analyze_canonical_score(hot_cross_buns_package, end_measure_ordinal=2),
    )
    scope = requirements.scopes[0]
    first = build_curriculum_passage_presentation(
        hot_cross_buns_package,
        requirements,
        scope.id,
    )
    second = build_curriculum_passage_presentation(
        hot_cross_buns_package,
        requirements,
        scope.id,
    )
    payload = curriculum_passage_presentation_to_json(first)

    assert first == second
    assert first.practice_scope_ref.id == scope.id
    assert first.score_range == scope.score_range
    assert len(first.measure_ids) == 2
    assert tuple(item.canonical_id for item in first.measure_renderer_targets) == first.measure_ids
    assert tuple(item.canonical_id for item in first.active_renderer_targets) == (
        first.active_target_ids
    )
    assert first.visible_event_ids == first.event_universe_ids
    assert first.inactive_context_ids == ()
    assert '"type": "curriculum-passage-presentation"' in payload
    assert curriculum_passage_presentation_from_json(payload) == first
    assert curriculum_passage_presentation_to_json(first) == payload


def test_polyphonic_layer_presentations_keep_the_complete_passage_visible(
    happy_birthday_package: CanonicalMusicPackage,
) -> None:
    """TEST-CURR-VALIDATION-014: isolated layers retain complete score context."""

    requirements = derive_passage_requirements(
        happy_birthday_package,
        analyze_canonical_score(happy_birthday_package, end_measure_ordinal=2),
    )
    upper_scope = next(
        item
        for item in requirements.scopes
        if item.notation_condition is NotationCondition.UPPER_LAYER
    )
    lower_scope = next(
        item
        for item in requirements.scopes
        if item.notation_condition is NotationCondition.LOWER_LAYER
    )
    upper = build_curriculum_passage_presentation(
        happy_birthday_package,
        requirements,
        upper_scope.id,
    )
    lower = build_curriculum_passage_presentation(
        happy_birthday_package,
        requirements,
        lower_scope.id,
    )

    assert upper.notation_renderer_sha256 == lower.notation_renderer_sha256
    assert upper.measure_renderer_targets == lower.measure_renderer_targets
    assert upper.event_universe_ids == lower.event_universe_ids
    assert upper.visible_event_ids == upper.event_universe_ids
    assert lower.visible_event_ids == lower.event_universe_ids
    assert set(upper.active_target_ids).isdisjoint(lower.active_target_ids)
    assert set(upper.inactive_context_ids) == set(lower.active_target_ids)
    assert set(lower.inactive_context_ids) == set(upper.active_target_ids)
    assert tuple(item.canonical_id for item in upper.active_renderer_targets) == (
        upper.active_target_ids
    )
    assert tuple(item.canonical_id for item in upper.inactive_renderer_targets) == (
        upper.inactive_context_ids
    )


def test_curriculum_expected_playback_uses_only_the_active_single_layer(
    hot_cross_buns_package: CanonicalMusicPackage,
) -> None:
    """TEST-CURR-VALIDATION-016: expected sound is the exact active layer."""

    requirements = derive_passage_requirements(
        hot_cross_buns_package,
        analyze_canonical_score(hot_cross_buns_package, end_measure_ordinal=2),
    )
    presentation = build_curriculum_passage_presentation(
        hot_cross_buns_package,
        requirements,
        requirements.scopes[0].id,
    )

    playback = build_curriculum_expected_playback(
        hot_cross_buns_package,
        presentation,
        tempo_bpm=72,
    )
    source_ids = {source.event_id for note in playback.notes for source in note.source_events}

    assert playback.package_id == presentation.package_id
    assert playback.score_id == presentation.score_id
    assert source_ids
    assert source_ids <= set(presentation.active_target_ids)
    assert source_ids.isdisjoint(presentation.inactive_context_ids)
    assert playback.tempo_controls[0].quarter_notes_per_minute == 72
    assert playback.diagnostics[0].code == "TMM-CURRICULUM-ACTIVE-PLAYBACK"


def test_separate_polyphonic_layers_never_enter_each_others_expected_playback(
    happy_birthday_package: CanonicalMusicPackage,
) -> None:
    """TEST-CURR-ROBUSTNESS-011: upper/lower sound and keys remain isolated."""

    requirements = derive_passage_requirements(
        happy_birthday_package,
        analyze_canonical_score(happy_birthday_package, end_measure_ordinal=2),
    )
    presentations = {
        condition: build_curriculum_passage_presentation(
            happy_birthday_package,
            requirements,
            next(
                scope.id for scope in requirements.scopes if scope.notation_condition is condition
            ),
        )
        for condition in (NotationCondition.UPPER_LAYER, NotationCondition.LOWER_LAYER)
    }
    source_sets: dict[NotationCondition, set[str]] = {}
    for condition, presentation in presentations.items():
        playback = build_curriculum_expected_playback(
            happy_birthday_package,
            presentation,
        )
        sources = {source.event_id for note in playback.notes for source in note.source_events}
        assert sources
        assert sources <= set(presentation.active_target_ids)
        assert sources.isdisjoint(presentation.inactive_context_ids)
        source_sets[condition] = sources

    assert source_sets[NotationCondition.UPPER_LAYER].isdisjoint(
        source_sets[NotationCondition.LOWER_LAYER]
    )


def test_curriculum_expected_playback_rejects_foreign_package_and_tempo(
    hot_cross_buns_package: CanonicalMusicPackage,
    happy_birthday_package: CanonicalMusicPackage,
) -> None:
    """TEST-CURR-ROBUSTNESS-012: playback projection fails closed on drift."""

    requirements = derive_passage_requirements(
        hot_cross_buns_package,
        analyze_canonical_score(hot_cross_buns_package, end_measure_ordinal=2),
    )
    presentation = build_curriculum_passage_presentation(
        hot_cross_buns_package,
        requirements,
        requirements.scopes[0].id,
    )

    with pytest.raises(
        CurriculumPresentationError,
        match="TMM-PRESENTATION-PLAYBACK-PACKAGE-MISMATCH",
    ):
        build_curriculum_expected_playback(happy_birthday_package, presentation)
    with pytest.raises(
        CurriculumPresentationError,
        match="TMM-PRESENTATION-PLAYBACK-TEMPO",
    ):
        build_curriculum_expected_playback(
            hot_cross_buns_package,
            presentation,
            tempo_bpm=0,
        )


def test_curriculum_guidance_is_traceable_deterministic_and_strictly_serialized(
    hot_cross_buns_package: CanonicalMusicPackage,
) -> None:
    """TEST-CURR-CONTRACT-006: active guidance preserves exact provenance."""

    requirements = derive_passage_requirements(
        hot_cross_buns_package,
        analyze_canonical_score(hot_cross_buns_package, end_measure_ordinal=2),
    )
    presentation = build_curriculum_passage_presentation(
        hot_cross_buns_package,
        requirements,
        requirements.scopes[0].id,
    )
    first = build_curriculum_passage_guidance(requirements, presentation)
    second = build_curriculum_passage_guidance(requirements, presentation)
    payload = curriculum_passage_guidance_to_json(first)

    assert first == second
    assert first.presentation_ref.id == presentation.id
    assert first.practice_scope_ref == presentation.practice_scope_ref
    assert len(first.items) == len(
        [
            item
            for item in requirements.requirements
            if item.practice_scope_ref.id == presentation.practice_scope_ref.id
            and item.resolution is ArtifactResolution.RESOLVED
        ]
    )
    assert all(item.heading and item.explanation and item.action_prompt for item in first.items)
    assert all(
        set(item.focus_event_ids) <= set(presentation.active_target_ids) for item in first.items
    )
    assert all(
        item.requirement_ref.semantic_fingerprint
        == next(
            requirement.semantic_fingerprint
            for requirement in requirements.requirements
            if requirement.id == item.requirement_ref.id
        )
        for item in first.items
    )
    memory = next(item for item in first.items if item.primitive_family.value == "memory")
    assert memory.focus_event_ids == presentation.active_target_ids[:1]
    assert set(memory.canonical_evidence_refs) & set(presentation.measure_ids)
    assert '"type": "curriculum-passage-guidance"' in payload
    assert curriculum_passage_guidance_from_json(payload) == first
    assert curriculum_passage_guidance_to_json(first) == payload


def test_polyphonic_guidance_names_written_layers_without_inventing_hands(
    happy_birthday_package: CanonicalMusicPackage,
) -> None:
    """TEST-CURR-VALIDATION-017: guidance remains exact and layer-specific."""

    requirements = derive_passage_requirements(
        happy_birthday_package,
        analyze_canonical_score(happy_birthday_package, end_measure_ordinal=2),
    )
    guidance: dict[NotationCondition, CurriculumPassageGuidance] = {}
    for condition in (NotationCondition.UPPER_LAYER, NotationCondition.LOWER_LAYER):
        scope = next(item for item in requirements.scopes if item.notation_condition is condition)
        presentation = build_curriculum_passage_presentation(
            happy_birthday_package,
            requirements,
            scope.id,
        )
        guidance[condition] = build_curriculum_passage_guidance(requirements, presentation)
        text = " ".join(
            f"{item.explanation} {item.action_prompt} {item.reconnect_prompt}"
            for item in guidance[condition].items
        ).lower()
        assert condition.value.replace("-layer", " written layer") in text
        assert "right hand" not in text
        assert "left hand" not in text
        assert all(
            set(item.focus_event_ids).isdisjoint(presentation.inactive_context_ids)
            for item in guidance[condition].items
        )

    assert guidance[NotationCondition.UPPER_LAYER].id != guidance[NotationCondition.LOWER_LAYER].id
    assert any(
        item.primitive_family.value == "harmony"
        for item in guidance[NotationCondition.LOWER_LAYER].items
    )


def test_curriculum_guidance_mutation_and_foreign_inputs_fail_closed(
    hot_cross_buns_package: CanonicalMusicPackage,
    happy_birthday_package: CanonicalMusicPackage,
) -> None:
    """TEST-CURR-ROBUSTNESS-013: guidance rejects scope and focus drift."""

    requirements = derive_passage_requirements(
        happy_birthday_package,
        analyze_canonical_score(happy_birthday_package, end_measure_ordinal=2),
    )
    scope = next(
        item
        for item in requirements.scopes
        if item.notation_condition is NotationCondition.UPPER_LAYER
    )
    presentation = build_curriculum_passage_presentation(
        happy_birthday_package,
        requirements,
        scope.id,
    )
    guidance = build_curriculum_passage_guidance(requirements, presentation)
    changed_item = replace(
        guidance.items[0],
        focus_event_ids=(presentation.inactive_context_ids[0],),
    )
    changed = replace(guidance, items=(changed_item, *guidance.items[1:]))
    codes = {
        item.code
        for item in validate_curriculum_passage_guidance(
            changed,
            requirements,
            presentation,
        )
    }

    assert "TMM-GUIDANCE-ACTIVE-TARGET-MISMATCH" in codes
    assert "TMM-GUIDANCE-EVIDENCE-MISMATCH" in codes
    assert "TMM-CONTRACT-FINGERPRINT-MISMATCH" in codes

    foreign_requirements = derive_passage_requirements(
        hot_cross_buns_package,
        analyze_canonical_score(hot_cross_buns_package, end_measure_ordinal=2),
    )
    foreign_codes = {
        item.code
        for item in validate_curriculum_passage_guidance(
            guidance,
            foreign_requirements,
            presentation,
        )
    }
    assert "TMM-GUIDANCE-REQUIREMENT-MISMATCH" in foreign_codes


def test_presentation_mutations_and_foreign_inputs_fail_closed(
    hot_cross_buns_package: CanonicalMusicPackage,
    happy_birthday_package: CanonicalMusicPackage,
    moonlight_package: CanonicalMusicPackage,
) -> None:
    """TEST-CURR-ROBUSTNESS-009: drift, mismatch, and ambiguity are rejected."""

    requirements = derive_passage_requirements(
        hot_cross_buns_package,
        analyze_canonical_score(hot_cross_buns_package, end_measure_ordinal=2),
    )
    scope = requirements.scopes[0]
    presentation = build_curriculum_passage_presentation(
        hot_cross_buns_package,
        requirements,
        scope.id,
    )
    changed = replace(presentation, visible_event_ids=presentation.visible_event_ids[1:])
    codes = {item.code for item in validate_curriculum_passage_presentation(changed, scope)}

    assert "TMM-PRESENTATION-VISIBLE-PARTITION" in codes
    assert "TMM-CONTRACT-FINGERPRINT-MISMATCH" in codes
    with pytest.raises(CurriculumPresentationError, match="TMM-PRESENTATION-SCOPE-MISSING"):
        build_curriculum_passage_presentation(
            hot_cross_buns_package,
            requirements,
            "practice-scope-assignment:missing",
        )
    with pytest.raises(CurriculumPresentationError, match="TMM-PRESENTATION-PACKAGE-MISMATCH"):
        build_curriculum_passage_presentation(
            happy_birthday_package,
            requirements,
            scope.id,
        )

    moonlight_requirements = derive_passage_requirements(
        moonlight_package,
        analyze_canonical_score(moonlight_package, end_measure_ordinal=69),
    )
    unresolved = moonlight_requirements.scopes[0]
    assert unresolved.resolution is ArtifactResolution.REVIEW_REQUIRED
    with pytest.raises(CurriculumPresentationError, match="TMM-PRESENTATION-SCOPE-UNRESOLVED"):
        build_curriculum_passage_presentation(
            moonlight_package,
            moonlight_requirements,
            unresolved.id,
        )

    wire = json.loads(curriculum_passage_presentation_to_json(presentation))
    wire["unknown"] = True
    with pytest.raises(CurriculumSerializationError, match="unexpected"):
        curriculum_passage_presentation_from_json(json.dumps(wire))
