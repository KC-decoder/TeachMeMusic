"""Executable DEV-009 Task 9G.1 deterministic-text evidence."""

from __future__ import annotations

from dataclasses import replace

import pytest

from teachmemusic.analysis import analyze_canonical_score
from teachmemusic.score import CanonicalMusicPackage
from teachmemusic.teaching import (
    ArtifactResolution,
    CurriculumFundamentalExplanationError,
    CurriculumSerializationError,
    NotationCondition,
    build_curriculum_fundamental_explanation,
    build_curriculum_passage_presentation,
    curriculum_fundamental_explanation_from_json,
    curriculum_fundamental_explanation_to_json,
    derive_passage_requirements,
    generate_prerequisite_branches,
    validate_curriculum_fundamental_explanation,
)


def test_functional_explanation_is_deterministic_traceable_and_strictly_serialized(
    hot_cross_buns_package: CanonicalMusicPackage,
) -> None:
    """TEST-CURR-CONTRACT-009: one prerequisite explanation round-trips exactly."""

    requirements = derive_passage_requirements(
        hot_cross_buns_package,
        analyze_canonical_score(hot_cross_buns_package, end_measure_ordinal=2),
    )
    branches = generate_prerequisite_branches(requirements)
    scope = requirements.scopes[0]
    presentation = build_curriculum_passage_presentation(
        hot_cross_buns_package,
        requirements,
        scope.id,
    )
    requirement = next(
        item for item in requirements.requirements if item.primitive_ref.id == "PRIM-KEY-001"
    )

    first = build_curriculum_fundamental_explanation(
        requirements,
        branches,
        presentation,
        requirement.id,
    )
    second = build_curriculum_fundamental_explanation(
        requirements,
        branches,
        presentation,
        requirement.id,
    )
    payload = curriculum_fundamental_explanation_to_json(first)

    assert first == second
    assert first.requirement_ref.id == requirement.id
    assert first.primitive_ref.id == requirement.primitive_ref.id
    assert first.practice_scope_ref == requirement.practice_scope_ref
    assert first.prerequisite_node_id != first.return_node_id
    assert first.focus_event_ids
    assert set(first.focus_event_ids) <= set(presentation.active_target_ids)
    assert "chosen piece" in first.why_it_matters
    assert "surrounding visible score" in first.return_prompt
    assert '"type": "curriculum-fundamental-explanation"' in payload
    assert curriculum_fundamental_explanation_from_json(payload) == first
    assert curriculum_fundamental_explanation_to_json(first) == payload
    with pytest.raises(CurriculumSerializationError, match="unexpected"):
        curriculum_fundamental_explanation_from_json(
            payload.replace('"action_prompt"', '"unexpected": true, "action_prompt"')
        )


def test_layered_explanation_names_written_layer_without_inventing_a_hand(
    happy_birthday_package: CanonicalMusicPackage,
) -> None:
    """TEST-CURR-VALIDATION-024: text stays active-layer and score grounded."""

    requirements = derive_passage_requirements(
        happy_birthday_package,
        analyze_canonical_score(happy_birthday_package, end_measure_ordinal=2),
    )
    branches = generate_prerequisite_branches(requirements)
    scope = next(
        item
        for item in requirements.scopes
        if item.notation_condition is NotationCondition.LOWER_LAYER
    )
    presentation = build_curriculum_passage_presentation(
        happy_birthday_package,
        requirements,
        scope.id,
    )
    requirement = next(
        item
        for item in requirements.requirements
        if item.practice_scope_ref.id == scope.id and item.primitive_ref.id == "PRIM-HAR-001"
    )
    explanation = build_curriculum_fundamental_explanation(
        requirements,
        branches,
        presentation,
        requirement.id,
    )
    text = " ".join(
        (
            explanation.explanation,
            explanation.why_it_matters,
            explanation.action_prompt,
            explanation.return_prompt,
        )
    ).lower()

    assert "lower written layer" in text
    assert "right hand" not in text
    assert "left hand" not in text
    assert set(explanation.focus_event_ids).isdisjoint(presentation.inactive_context_ids)
    assert (
        validate_curriculum_fundamental_explanation(
            explanation,
            requirements,
            branches,
            presentation,
        )
        == ()
    )


def test_explanation_rejects_changed_return_and_foreign_scope(
    hot_cross_buns_package: CanonicalMusicPackage,
    happy_birthday_package: CanonicalMusicPackage,
) -> None:
    """TEST-CURR-ROBUSTNESS-024: text cannot detach from its graph return."""

    requirements = derive_passage_requirements(
        hot_cross_buns_package,
        analyze_canonical_score(hot_cross_buns_package, end_measure_ordinal=2),
    )
    branches = generate_prerequisite_branches(requirements)
    presentation = build_curriculum_passage_presentation(
        hot_cross_buns_package,
        requirements,
        requirements.scopes[0].id,
    )
    first_requirement, second_requirement = requirements.requirements[:2]
    explanation = build_curriculum_fundamental_explanation(
        requirements,
        branches,
        presentation,
        first_requirement.id,
    )
    second_branch = next(
        item for item in branches.branches if item.requirement_ref.id == second_requirement.id
    )
    changed = replace(explanation, return_node_id=second_branch.application_node_id)
    codes = {
        item.code
        for item in validate_curriculum_fundamental_explanation(
            changed,
            requirements,
            branches,
            presentation,
        )
    }

    assert "TMM-EXPLANATION-BRANCH-MISMATCH" in codes
    assert "TMM-EXPLANATION-RETURN-MISMATCH" in codes
    assert "TMM-CONTRACT-FINGERPRINT-MISMATCH" in codes

    foreign_requirements = derive_passage_requirements(
        happy_birthday_package,
        analyze_canonical_score(happy_birthday_package, end_measure_ordinal=2),
    )
    foreign_scope = next(
        item
        for item in foreign_requirements.scopes
        if item.notation_condition is NotationCondition.UPPER_LAYER
    )
    foreign_presentation = build_curriculum_passage_presentation(
        happy_birthday_package,
        foreign_requirements,
        foreign_scope.id,
    )
    with pytest.raises(
        CurriculumFundamentalExplanationError,
        match="TMM-EXPLANATION-SCOPE-MISMATCH",
    ):
        build_curriculum_fundamental_explanation(
            requirements,
            branches,
            foreign_presentation,
            first_requirement.id,
        )


def test_unresolved_complex_topology_emits_no_explanation(
    moonlight_package: CanonicalMusicPackage,
    hot_cross_buns_package: CanonicalMusicPackage,
) -> None:
    """TEST-CURR-ROBUSTNESS-025: unresolved pedagogy cannot produce prose."""

    requirements = derive_passage_requirements(
        moonlight_package,
        analyze_canonical_score(moonlight_package, end_measure_ordinal=69),
    )
    branches = generate_prerequisite_branches(requirements)

    assert branches.resolution is ArtifactResolution.REVIEW_REQUIRED
    assert branches.branches == ()
    resolved_requirements = derive_passage_requirements(
        hot_cross_buns_package,
        analyze_canonical_score(hot_cross_buns_package, end_measure_ordinal=2),
    )
    resolved_presentation = build_curriculum_passage_presentation(
        hot_cross_buns_package,
        resolved_requirements,
        resolved_requirements.scopes[0].id,
    )
    with pytest.raises(
        CurriculumFundamentalExplanationError,
        match="TMM-EXPLANATION-BRANCH-UNRESOLVED",
    ):
        build_curriculum_fundamental_explanation(
            requirements,
            branches,
            resolved_presentation,
            "missing",
        )
