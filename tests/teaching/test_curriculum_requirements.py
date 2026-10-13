"""Executable DEV-009 9B.1 contract and passage-requirement evidence."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from teachmemusic.analysis import analyze_canonical_score
from teachmemusic.score import CanonicalMusicPackage
from teachmemusic.teaching import (
    ArtifactResolution,
    CurriculumSerializationError,
    ExecutionAssignment,
    NotationCondition,
    derive_passage_requirements,
    learning_primitive_from_json,
    learning_primitive_to_json,
    passage_requirement_from_json,
    passage_requirement_to_json,
    practice_scope_from_json,
    practice_scope_to_json,
    validate_practice_scope,
    validate_requirement_set,
)


def test_curriculum_artifacts_have_strict_deterministic_round_trips(
    hot_cross_buns_package: CanonicalMusicPackage,
) -> None:
    """TEST-CURR-CONTRACT-001: completed 0.4 artifact types round-trip exactly."""

    analysis = analyze_canonical_score(hot_cross_buns_package)
    result = derive_passage_requirements(hot_cross_buns_package, analysis)
    scope = result.scopes[0]
    primitive = result.primitives[0]
    requirement = result.requirements[0]

    scope_json = practice_scope_to_json(scope)
    primitive_json = learning_primitive_to_json(primitive)
    requirement_json = passage_requirement_to_json(requirement)

    assert '"type": "practice-scope-assignment"' in scope_json
    assert '"type": "learning-primitive"' in primitive_json
    assert '"type": "passage-skill-requirement"' in requirement_json
    assert '"type": "SemanticReference"' not in requirement_json
    assert '"artifact_type"' not in requirement_json
    assert '"type": "learning-primitive"' in requirement_json
    assert '"type": "RuleReference"' not in requirement_json
    assert practice_scope_from_json(scope_json) == scope
    assert learning_primitive_from_json(primitive_json) == primitive
    assert passage_requirement_from_json(requirement_json) == requirement
    assert practice_scope_to_json(scope) == scope_json
    with pytest.raises(CurriculumSerializationError, match="expected"):
        practice_scope_from_json(scope_json.replace("practice-scope-assignment", "scope"))
    with pytest.raises(CurriculumSerializationError, match="unexpected"):
        practice_scope_from_json(
            scope_json.replace('"active_target_ids"', '"unknown": true, "active_target_ids"')
        )


def test_hot_cross_buns_derives_one_complete_single_layer_scope(
    hot_cross_buns_package: CanonicalMusicPackage,
) -> None:
    """TEST-CURR-VALIDATION-001: monophonic scope and requirements are exact."""

    analysis = analyze_canonical_score(hot_cross_buns_package)
    first = derive_passage_requirements(hot_cross_buns_package, analysis)
    second = derive_passage_requirements(hot_cross_buns_package, analysis)
    scope = first.scopes[0]
    primitive_ids = {item.primitive_ref.id for item in first.requirements}

    assert first == second
    assert validate_requirement_set(first, hot_cross_buns_package, analysis) == ()
    assert len(first.scopes) == 1
    assert scope.notation_condition is NotationCondition.SINGLE_LAYER
    assert scope.execution_assignment is ExecutionAssignment.UNASSIGNED
    assert scope.resolution is ArtifactResolution.RESOLVED
    assert set(scope.active_target_ids) == set(scope.event_universe_ids)
    assert scope.inactive_context_ids == ()
    assert {"PRIM-KEY-001", "PRIM-READ-001", "PRIM-RHY-002", "PRIM-PAT-001"} <= primitive_ids
    assert not {"PRIM-HAR-001", "PRIM-COORD-001"} & primitive_ids


def test_happy_birthday_derives_isolated_layers_and_combined_scope(
    happy_birthday_package: CanonicalMusicPackage,
) -> None:
    """TEST-CURR-VALIDATION-002: polyphony stays partitioned and title blind."""

    analysis = analyze_canonical_score(happy_birthday_package)
    result = derive_passage_requirements(happy_birthday_package, analysis)
    upper, lower, combined = result.scopes
    requirements = {
        scope.id: {
            item.primitive_ref.id
            for item in result.requirements
            if item.practice_scope_ref.id == scope.id
        }
        for scope in result.scopes
    }

    assert validate_requirement_set(result, happy_birthday_package, analysis) == ()
    assert [item.notation_condition for item in result.scopes] == [
        NotationCondition.UPPER_LAYER,
        NotationCondition.LOWER_LAYER,
        NotationCondition.COMBINED,
    ]
    assert all(
        item.execution_assignment is ExecutionAssignment.UNASSIGNED for item in result.scopes
    )
    assert len(upper.active_target_ids) == 25
    assert len(lower.active_target_ids) == 34
    assert set(upper.active_target_ids).isdisjoint(lower.active_target_ids)
    assert set(upper.active_target_ids) | set(lower.active_target_ids) == set(
        combined.active_target_ids
    )
    assert combined.component_scope_ids == (upper.id, lower.id)
    assert "PRIM-HAR-001" in requirements[lower.id]
    assert {"PRIM-COORD-001", "PRIM-COORD-002"} <= requirements[combined.id]


def test_scope_validation_reports_partition_and_fingerprint_mutations(
    hot_cross_buns_package: CanonicalMusicPackage,
) -> None:
    """TEST-CURR-VALIDATION-003: scope corruption yields stable diagnostics."""

    analysis = analyze_canonical_score(hot_cross_buns_package)
    scope = derive_passage_requirements(hot_cross_buns_package, analysis).scopes[0]
    changed = replace(scope, active_target_ids=scope.active_target_ids[1:])
    codes = {item.code for item in validate_practice_scope(changed, analysis)}

    assert "TMM-SCOPE-INCOMPLETE-PARTITION" in codes
    assert "TMM-SCOPE-COMPONENT-MISMATCH" in codes
    assert "TMM-CONTRACT-FINGERPRINT-MISMATCH" in codes


def test_complex_layer_topology_fails_closed_for_review(
    moonlight_package: CanonicalMusicPackage,
) -> None:
    """TEST-CURR-VALIDATION-004: unresolved Moonlight grouping is not guessed."""

    analysis = analyze_canonical_score(moonlight_package, end_measure_ordinal=69)
    result = derive_passage_requirements(moonlight_package, analysis)

    assert validate_requirement_set(result, moonlight_package, analysis) == ()
    assert len(result.scopes) == 1
    assert result.scopes[0].resolution is ArtifactResolution.REVIEW_REQUIRED
    assert result.scopes[0].execution_assignment is ExecutionAssignment.UNASSIGNED
    assert result.requirements == ()
    assert [item.code for item in result.diagnostics] == ["TMM-HAND-INTERPRETATION-REQUIRED"]


def test_requirement_derivation_source_has_no_piece_or_fixture_branch() -> None:
    """TEST-CURR-ROBUSTNESS-001: production derivation contains no title shortcut."""

    import teachmemusic.teaching.requirements as requirements_module

    source = Path(requirements_module.__file__).read_text()
    forbidden = (
        "Hot Cross Buns",
        "Happy Birthday",
        "Moonlight Sonata",
        "TMM-REF-CANDIDATE",
        "tests/fixtures",
    )

    assert not any(value in source for value in forbidden)
