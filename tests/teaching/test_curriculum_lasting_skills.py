"""Executable DEV-009 Task 9B.4 retention and transfer evidence."""

from __future__ import annotations

from dataclasses import replace
from fractions import Fraction

import pytest

from teachmemusic.analysis import analyze_canonical_score
from teachmemusic.score import CanonicalMusicPackage
from teachmemusic.teaching import (
    ActivityForm,
    ArtifactResolution,
    CompatibleTempoEvidence,
    CurriculumEdgeKind,
    CurriculumSerializationError,
    LastingSkillStageKind,
    RetentionCheckpointKind,
    SemanticReference,
    TempoReferenceAuthority,
    TransferTargetRequest,
    derive_passage_requirements,
    generate_acquisition_graph,
    generate_lasting_skill_graph,
    generate_prerequisite_branches,
    lasting_skill_graph_slice_from_json,
    lasting_skill_graph_slice_to_json,
    validate_lasting_skill_graph_slice,
)


def _requirements(package: CanonicalMusicPackage):
    return derive_passage_requirements(
        package,
        analyze_canonical_score(package, end_measure_ordinal=2),
    )


def _acquisition(requirements):
    percentages = {
        "single-layer": 70,
        "upper-layer": 85,
        "lower-layer": 70,
        "combined": 70,
    }
    evidence = tuple(
        CompatibleTempoEvidence(
            SemanticReference("practice-scope-assignment", scope.id, scope.semantic_fingerprint),
            "independent-piece",
            percentages[scope.notation_condition.value],
            percentages[scope.notation_condition.value],
            True,
            True,
            (f"evidence:{scope.notation_condition.value}",),
        )
        for scope in requirements.scopes
    )
    return generate_acquisition_graph(
        requirements,
        generate_prerequisite_branches(requirements),
        reference_tempo_bpm=Fraction(100),
        reference_authority=TempoReferenceAuthority.CALLER,
        tempo_evidence=evidence,
    )


def _transfer_requests(source, target) -> tuple[TransferTargetRequest, ...]:
    requests: list[TransferTargetRequest] = []
    for primitive_id in ("PRIM-LAY-001", "PRIM-RHY-002"):
        source_requirement = next(
            item for item in source.requirements if item.primitive_ref.id == primitive_id
        )
        target_requirement = next(
            item
            for item in target.requirements
            if item.primitive_ref.id == primitive_id
            and next(
                scope.notation_condition.value
                for scope in target.scopes
                if scope.id == item.practice_scope_ref.id
            )
            == "upper-layer"
        )
        requests.append(
            TransferTargetRequest(
                source_requirement.id,
                target_requirement.id,
                ("material", "score"),
                tuple(sorted(target_requirement.canonical_evidence_refs)),
            )
        )
    return tuple(requests)


def test_lasting_skill_graph_round_trips_strictly(
    hot_cross_buns_package: CanonicalMusicPackage,
    happy_birthday_package: CanonicalMusicPackage,
) -> None:
    """TEST-CURR-CONTRACT-004: the 0.3 lasting-skill slice has strict JSON."""

    source = _requirements(hot_cross_buns_package)
    target = _requirements(happy_birthday_package)
    acquisition = _acquisition(source)
    graph = generate_lasting_skill_graph(
        source,
        acquisition,
        target,
        transfer_requests=_transfer_requests(source, target),
    )
    payload = lasting_skill_graph_slice_to_json(graph)

    assert '"graph_identity": "TMM-CURRICULUM-GRAPH-0.3"' in payload
    assert lasting_skill_graph_slice_from_json(payload) == graph
    assert lasting_skill_graph_slice_to_json(graph) == payload
    with pytest.raises(CurriculumSerializationError, match="unexpected"):
        lasting_skill_graph_slice_from_json(
            payload.replace('"source_analysis_id"', '"unexpected": true, "source_analysis_id"', 1)
        )


def test_retention_uses_exact_delays_same_target_and_no_answer_reveal(
    hot_cross_buns_package: CanonicalMusicPackage,
    happy_birthday_package: CanonicalMusicPackage,
) -> None:
    """TEST-CURR-VALIDATION-011: R1/R2 preserve same-target identity."""

    source = _requirements(hot_cross_buns_package)
    target = _requirements(happy_birthday_package)
    acquisition = _acquisition(source)
    graph = generate_lasting_skill_graph(
        source,
        acquisition,
        target,
        transfer_requests=_transfer_requests(source, target),
    )
    exercise_by_id = {item.id: item for item in graph.exercises}
    node_by_id = {item.id: item for item in graph.nodes}

    assert validate_lasting_skill_graph_slice(graph, source, acquisition, target) == ()
    assert graph.resolution is ArtifactResolution.RESOLVED
    assert len(graph.retention_schedules) == 2
    assert all(
        tuple(window.checkpoint for window in schedule.windows)
        == (RetentionCheckpointKind.R1, RetentionCheckpointKind.R2)
        for schedule in graph.retention_schedules
    )
    assert all(
        tuple(
            (window.due_after_hours, window.valid_after_hours, window.valid_before_hours)
            for window in schedule.windows
        )
        == ((24, 20, 72), (168, 120, 240))
        for schedule in graph.retention_schedules
    )
    retention_stages = tuple(
        item for item in graph.stages if item.kind is LastingSkillStageKind.RETENTION
    )
    assert len(retention_stages) == 4
    for stage in retention_stages:
        exercise = exercise_by_id[node_by_id[stage.node_id].exercise_ref.id]
        assert exercise.practice_scope_ref == stage.practice_scope_ref
        assert exercise.return_target_id == stage.return_node_id
        assert tuple(item.form for item in exercise.activity_sequence) == (
            ActivityForm.ORIENT,
            ActivityForm.PERFORM,
        )
        assert {item.evidence_context for item in exercise.required_evidence_exits} == {"retention"}


def test_transfer_is_different_untrained_and_cannot_backfill_source_evidence(
    hot_cross_buns_package: CanonicalMusicPackage,
    happy_birthday_package: CanonicalMusicPackage,
) -> None:
    """TEST-CURR-VALIDATION-012: transfer stays a linked different-target claim."""

    source = _requirements(hot_cross_buns_package)
    target = _requirements(happy_birthday_package)
    acquisition = _acquisition(source)
    graph = generate_lasting_skill_graph(
        source,
        acquisition,
        target,
        transfer_requests=_transfer_requests(source, target),
    )
    node_by_id = {item.id: item for item in graph.nodes}
    exercise_by_id = {item.id: item for item in graph.exercises}

    assert len(graph.transfer_targets) == 2
    for assignment in graph.transfer_targets:
        assert assignment.source_scope_ref != assignment.target_scope_ref
        assert assignment.training_state_guard == "previously-untrained-at-attempt-open"
        assert assignment.difference_dimensions == ("material", "score")
    for stage in (item for item in graph.stages if item.kind is LastingSkillStageKind.TRANSFER):
        exercise = exercise_by_id[node_by_id[stage.node_id].exercise_ref.id]
        assert exercise.requirement_ref == stage.requirement_ref
        assert exercise.practice_scope_ref == stage.practice_scope_ref
        assert stage.source_requirement_ref != stage.requirement_ref
        assert {item.evidence_context for item in exercise.required_evidence_exits} == {"transfer"}
        assert any(
            edge.kind is CurriculumEdgeKind.SCHEDULE_TRANSFER
            and edge.target_node_id == stage.node_id
            and "R1-passed" in edge.guard
            for edge in graph.edges
        )
        assert not any(
            edge.kind is CurriculumEdgeKind.ON_SATISFIED and edge.source_node_id == stage.node_id
            for edge in graph.edges
        )


def test_missing_or_same_target_transfer_fails_closed(
    hot_cross_buns_package: CanonicalMusicPackage,
) -> None:
    """TEST-CURR-ROBUSTNESS-004: unresolved target difference emits no route."""

    source = _requirements(hot_cross_buns_package)
    acquisition = _acquisition(source)
    absent = generate_lasting_skill_graph(
        source,
        acquisition,
        source,
        transfer_requests=(),
    )
    requirement = next(
        item for item in source.requirements if item.primitive_ref.id == "PRIM-LAY-001"
    )
    same = generate_lasting_skill_graph(
        source,
        acquisition,
        source,
        transfer_requests=(
            TransferTargetRequest(
                requirement.id,
                requirement.id,
                ("material",),
                tuple(sorted(requirement.canonical_evidence_refs)),
            ),
        ),
    )

    for graph in (absent, same):
        assert graph.resolution is ArtifactResolution.REVIEW_REQUIRED
        assert graph.nodes == ()
        assert graph.exercises == ()
        assert [item.code for item in graph.diagnostics] == ["TMM-TRANSFER-TARGET-UNRESOLVED"]
        assert validate_lasting_skill_graph_slice(graph) == ()


def test_retention_window_mutation_changes_identity_and_fails_validation(
    hot_cross_buns_package: CanonicalMusicPackage,
    happy_birthday_package: CanonicalMusicPackage,
) -> None:
    """TEST-CURR-ROBUSTNESS-005: delay drift is visible and non-loadable."""

    source = _requirements(hot_cross_buns_package)
    target = _requirements(happy_birthday_package)
    acquisition = _acquisition(source)
    graph = generate_lasting_skill_graph(
        source,
        acquisition,
        target,
        transfer_requests=_transfer_requests(source, target),
    )
    first_schedule = graph.retention_schedules[0]
    changed_window = replace(first_schedule.windows[0], due_after_hours=25)
    changed_schedule = replace(
        first_schedule,
        windows=(changed_window, first_schedule.windows[1]),
    )
    changed = replace(
        graph,
        retention_schedules=(changed_schedule, *graph.retention_schedules[1:]),
    )
    codes = {item.code for item in validate_lasting_skill_graph_slice(changed)}

    assert "TMM-RETENTION-SCHEDULE-INVALID" in codes
    assert "TMM-CONTRACT-FINGERPRINT-MISMATCH" in codes


def test_unresolved_retention_delay_fails_closed_before_graph_generation(
    hot_cross_buns_package: CanonicalMusicPackage,
    happy_birthday_package: CanonicalMusicPackage,
) -> None:
    """TEST-CURR-ROBUSTNESS-006: absent schedule facts never use defaults silently."""

    source = _requirements(hot_cross_buns_package)
    target = _requirements(happy_birthday_package)
    graph = generate_lasting_skill_graph(
        source,
        _acquisition(source),
        target,
        transfer_requests=_transfer_requests(source, target),
        retention_windows=(),
    )

    assert graph.resolution is ArtifactResolution.REVIEW_REQUIRED
    assert graph.nodes == ()
    assert [item.code for item in graph.diagnostics] == ["TMM-RETENTION-SCHEDULE-INVALID"]
