"""Executable DEV-009 Task 9B.2 prerequisite-branch evidence."""

from __future__ import annotations

from dataclasses import replace

import pytest

from teachmemusic.analysis import analyze_canonical_score
from teachmemusic.score import CanonicalMusicPackage
from teachmemusic.teaching import (
    ArtifactResolution,
    CurriculumEdgeKind,
    CurriculumNodeKind,
    CurriculumSerializationError,
    derive_passage_requirements,
    exercise_instance_from_json,
    exercise_instance_to_json,
    generate_prerequisite_branches,
    validate_prerequisite_branch_set,
)


def test_generated_exercise_instances_round_trip_strictly(
    hot_cross_buns_package: CanonicalMusicPackage,
) -> None:
    """TEST-CURR-CONTRACT-002: 9B.2 exercise instances use the frozen wire shape."""

    requirements = derive_passage_requirements(
        hot_cross_buns_package, analyze_canonical_score(hot_cross_buns_package)
    )
    generated = generate_prerequisite_branches(requirements)
    exercise = generated.exercises[0]
    payload = exercise_instance_to_json(exercise)

    assert '"type": "exercise-instance"' in payload
    assert '"type": "canonical-excerpt"' in payload
    assert '"material_type"' not in payload
    assert exercise_instance_from_json(payload) == exercise
    assert exercise_instance_to_json(exercise) == payload
    with pytest.raises(CurriculumSerializationError, match="unexpected"):
        exercise_instance_from_json(
            payload.replace('"activity_sequence"', '"unexpected": true, "activity_sequence"')
        )


def test_each_requirement_gets_diagnostic_prerequisite_and_exact_return(
    hot_cross_buns_package: CanonicalMusicPackage,
) -> None:
    """TEST-CURR-VALIDATION-005: every resolved target gets one complete branch."""

    requirements = derive_passage_requirements(
        hot_cross_buns_package, analyze_canonical_score(hot_cross_buns_package)
    )
    generated = generate_prerequisite_branches(requirements)
    nodes = {item.id: item for item in generated.nodes}

    assert generated.resolution is ArtifactResolution.RESOLVED
    assert validate_prerequisite_branch_set(generated, requirements) == ()
    assert len(generated.branches) == len(requirements.requirements)
    assert len(generated.exercises) == 3 * len(requirements.requirements)
    for branch in generated.branches:
        assert nodes[branch.diagnostic_node_id].kind is CurriculumNodeKind.DIAGNOSTIC
        assert nodes[branch.prerequisite_node_id].kind is CurriculumNodeKind.PREREQUISITE
        assert nodes[branch.application_node_id].kind is CurriculumNodeKind.APPLICATION
        return_edges = tuple(
            edge
            for edge in generated.edges
            if edge.kind is CurriculumEdgeKind.RETURN_TO
            and edge.source_node_id == branch.prerequisite_node_id
        )
        assert len(return_edges) == 1
        assert return_edges[0].target_node_id == branch.application_node_id
        assert return_edges[0].return_node_id == branch.application_node_id


def test_diagnostic_branch_bypasses_only_its_own_introduction(
    hot_cross_buns_package: CanonicalMusicPackage,
) -> None:
    """TEST-CURR-VALIDATION-006: pass and unconfirmed routes remain target-local."""

    requirements = derive_passage_requirements(
        hot_cross_buns_package, analyze_canonical_score(hot_cross_buns_package)
    )
    generated = generate_prerequisite_branches(requirements)

    for branch in generated.branches:
        outgoing = tuple(
            edge for edge in generated.edges if edge.source_node_id == branch.diagnostic_node_id
        )
        assert {
            (CurriculumEdgeKind.ON_SATISFIED, branch.application_node_id),
            (CurriculumEdgeKind.ON_UNCONFIRMED, branch.prerequisite_node_id),
        } <= {(item.kind, item.target_node_id) for item in outgoing}
        assert not any(
            item.kind in {CurriculumEdgeKind.ON_SATISFIED, CurriculumEdgeKind.ON_UNCONFIRMED}
            and item.target_node_id not in {branch.application_node_id, branch.prerequisite_node_id}
            for item in outgoing
        )


def test_happy_birthday_combined_dependencies_reference_component_requirements(
    happy_birthday_package: CanonicalMusicPackage,
) -> None:
    """TEST-CURR-VALIDATION-007: combined coordination retains component closure."""

    requirements = derive_passage_requirements(
        happy_birthday_package, analyze_canonical_score(happy_birthday_package)
    )
    generated = generate_prerequisite_branches(requirements)
    scope_by_id = {item.id: item for item in requirements.scopes}
    requirement_by_id = {item.id: item for item in requirements.requirements}
    combined = next(item for item in requirements.scopes if item.notation_condition == "combined")
    coordination = next(
        item
        for item in requirements.requirements
        if item.practice_scope_ref.id == combined.id and item.primitive_ref.id == "PRIM-COORD-001"
    )
    dependencies = tuple(
        requirement_by_id[item] for item in coordination.prerequisite_requirement_ids
    )

    assert validate_prerequisite_branch_set(generated, requirements) == ()
    assert {
        item.practice_scope_ref.id
        for item in dependencies
        if item.primitive_ref.id == "PRIM-LAY-001"
    } == set(combined.component_scope_ids)
    assert all(
        scope_by_id[item.practice_scope_ref.id].resolution is ArtifactResolution.RESOLVED
        for item in dependencies
    )


def test_changed_prerequisite_return_fails_with_stable_diagnostic(
    hot_cross_buns_package: CanonicalMusicPackage,
) -> None:
    """TEST-CURR-VALIDATION-008: a side quest cannot return to another target."""

    requirements = derive_passage_requirements(
        hot_cross_buns_package, analyze_canonical_score(hot_cross_buns_package)
    )
    generated = generate_prerequisite_branches(requirements)
    first, second = generated.branches[:2]
    changed_edges = tuple(
        replace(
            edge,
            target_node_id=second.application_node_id,
            return_node_id=second.application_node_id,
        )
        if edge.kind is CurriculumEdgeKind.RETURN_TO
        and edge.source_node_id == first.prerequisite_node_id
        else edge
        for edge in generated.edges
    )
    changed = replace(generated, edges=changed_edges)
    codes = {item.code for item in validate_prerequisite_branch_set(changed, requirements)}

    assert "TMM-GRAPH-RETURN-MISMATCH" in codes


def test_branch_generation_is_deterministic_and_review_scopes_stop(
    hot_cross_buns_package: CanonicalMusicPackage,
    moonlight_package: CanonicalMusicPackage,
) -> None:
    """TEST-CURR-ROBUSTNESS-002: repeated input is exact and ambiguity fails closed."""

    hot_requirements = derive_passage_requirements(
        hot_cross_buns_package, analyze_canonical_score(hot_cross_buns_package)
    )
    first = generate_prerequisite_branches(hot_requirements)
    second = generate_prerequisite_branches(hot_requirements)
    moonlight_requirements = derive_passage_requirements(
        moonlight_package, analyze_canonical_score(moonlight_package, end_measure_ordinal=69)
    )
    moonlight = generate_prerequisite_branches(moonlight_requirements)

    assert first == second
    assert moonlight.resolution is ArtifactResolution.REVIEW_REQUIRED
    assert moonlight.nodes == ()
    assert moonlight.edges == ()
    assert moonlight.exercises == ()
    assert moonlight.branches == ()
    assert [item.code for item in moonlight.diagnostics] == ["TMM-HAND-INTERPRETATION-REQUIRED"]
    assert validate_prerequisite_branch_set(moonlight, moonlight_requirements) == ()
