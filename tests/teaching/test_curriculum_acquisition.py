"""Executable DEV-009 Task 9B.3 acquisition and tempo evidence."""

from __future__ import annotations

from dataclasses import replace
from fractions import Fraction

import pytest

from teachmemusic.analysis import analyze_canonical_score
from teachmemusic.score import CanonicalMusicPackage
from teachmemusic.teaching import (
    AcquisitionStageKind,
    ArtifactResolution,
    CompatibleTempoEvidence,
    CurriculumSerializationError,
    SemanticReference,
    TempoPlanState,
    TempoPolicyAction,
    TempoProbeResult,
    TempoReferenceAuthority,
    acquisition_graph_slice_from_json,
    acquisition_graph_slice_to_json,
    decide_tempo_probe,
    default_tempo_configuration,
    derive_passage_requirements,
    generate_acquisition_graph,
    generate_prerequisite_branches,
    validate_acquisition_graph_slice,
)


def _bounded_inputs(package: CanonicalMusicPackage):
    analysis = analyze_canonical_score(package, end_measure_ordinal=2)
    requirements = derive_passage_requirements(package, analysis)
    return requirements, generate_prerequisite_branches(requirements)


def _tempo_evidence(requirements, percentages: dict[str, int]):
    return tuple(
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


def test_acquisition_graph_and_tempo_configuration_round_trip_strictly(
    hot_cross_buns_package: CanonicalMusicPackage,
) -> None:
    """TEST-CURR-CONTRACT-003: the 0.2 graph slice has strict stable JSON."""

    requirements, branches = _bounded_inputs(hot_cross_buns_package)
    graph = generate_acquisition_graph(
        requirements,
        branches,
        reference_tempo_bpm=Fraction(100),
        reference_authority=TempoReferenceAuthority.CALLER,
        tempo_evidence=_tempo_evidence(requirements, {"single-layer": 70}),
    )
    payload = acquisition_graph_slice_to_json(graph)

    assert '"graph_identity": "TMM-CURRICULUM-GRAPH-0.2"' in payload
    assert '"policy_identity": "TMM-DETERMINISTIC-POLICY-0.2"' in payload
    assert acquisition_graph_slice_from_json(payload) == graph
    assert acquisition_graph_slice_to_json(graph) == payload
    with pytest.raises(CurriculumSerializationError, match="unexpected"):
        acquisition_graph_slice_from_json(
            payload.replace('"analysis_id"', '"unexpected": true, "analysis_id"', 1)
        )


def test_single_layer_route_collapses_coordination_and_keeps_separate_tempo_loop(
    hot_cross_buns_package: CanonicalMusicPackage,
) -> None:
    """TEST-CURR-VALIDATION-009: single-layer acquisition emits no empty hand work."""

    requirements, branches = _bounded_inputs(hot_cross_buns_package)
    graph = generate_acquisition_graph(
        requirements,
        branches,
        reference_tempo_bpm=Fraction(100),
        reference_authority=TempoReferenceAuthority.CALLER,
        tempo_evidence=_tempo_evidence(requirements, {"single-layer": 70}),
    )

    assert validate_acquisition_graph_slice(graph) == ()
    assert tuple(item.kind for item in graph.stages) == (
        AcquisitionStageKind.COMPONENT_ACQUISITION,
        AcquisitionStageKind.PULSE_INTEGRATION,
        AcquisitionStageKind.PHRASE_CONTROLLED_TEMPO,
        AcquisitionStageKind.LEARNED_TO_DATE,
        AcquisitionStageKind.TEMPO_DEVELOPMENT,
    )
    assert all(
        item.kind is not AcquisitionStageKind.SELF_PACED_COORDINATION for item in graph.stages
    )
    assert graph.tempo_plans[0].current_controlled_percentage == 70


def test_happy_birthday_layers_coordinate_before_pulse_and_cumulative_work(
    happy_birthday_package: CanonicalMusicPackage,
) -> None:
    """TEST-CURR-VALIDATION-010: component identity gates combined acquisition."""

    requirements, branches = _bounded_inputs(happy_birthday_package)
    graph = generate_acquisition_graph(
        requirements,
        branches,
        reference_tempo_bpm=Fraction(120),
        reference_authority=TempoReferenceAuthority.SOURCE,
        tempo_evidence=_tempo_evidence(
            requirements,
            {"upper-layer": 85, "lower-layer": 70, "combined": 85},
        ),
    )
    kinds = tuple(item.kind for item in graph.stages)
    coordination = next(
        item for item in graph.stages if item.kind is AcquisitionStageKind.SELF_PACED_COORDINATION
    )
    pulse = next(
        item for item in graph.stages if item.kind is AcquisitionStageKind.PULSE_INTEGRATION
    )
    pulse_node = next(item for item in graph.nodes if item.id == pulse.node_id)
    assert pulse_node.exercise_ref is not None
    pulse_exercise = next(item for item in graph.exercises if item.id == pulse_node.exercise_ref.id)

    assert validate_acquisition_graph_slice(graph) == ()
    assert kinds == (
        AcquisitionStageKind.COMPONENT_ACQUISITION,
        AcquisitionStageKind.COMPONENT_ACQUISITION,
        AcquisitionStageKind.SELF_PACED_COORDINATION,
        AcquisitionStageKind.PULSE_INTEGRATION,
        AcquisitionStageKind.PHRASE_CONTROLLED_TEMPO,
        AcquisitionStageKind.LEARNED_TO_DATE,
        AcquisitionStageKind.TEMPO_DEVELOPMENT,
    )
    assert len(coordination.component_node_ids) == 2
    assert {item.evidence_context for item in pulse_exercise.required_evidence_exits} == {
        "integration"
    }
    assert (
        next(
            item
            for item in graph.tempo_plans
            if item.practice_scope_ref.id == coordination.practice_scope_ref.id
        ).current_controlled_percentage
        == 70
    )
    assert graph.tempo_configuration.phrase_group_size == 2


def test_no_compatible_tempo_evidence_generates_only_bounded_diagnostics(
    happy_birthday_package: CanonicalMusicPackage,
) -> None:
    """TEST-CURR-POLICY-001: missing tempo evidence is sampled, never guessed."""

    requirements, branches = _bounded_inputs(happy_birthday_package)
    graph = generate_acquisition_graph(
        requirements,
        branches,
        reference_tempo_bpm=Fraction(120),
        reference_authority=TempoReferenceAuthority.SOURCE,
    )

    assert validate_acquisition_graph_slice(graph) == ()
    assert all(item.state is TempoPlanState.DIAGNOSTIC_REQUIRED for item in graph.tempo_plans)
    assert all(item.kind is AcquisitionStageKind.TEMPO_DIAGNOSTIC for item in graph.stages)
    assert all(item.diagnostic_probe_percentages == (100, 85, 70, 55) for item in graph.tempo_plans)


def test_reduced_and_rhythm_ready_golden_tempo_trajectories(
    happy_birthday_package: CanonicalMusicPackage,
) -> None:
    """TEST-CURR-POLICY-002: both ADR-0012 golden entry paths are replayable."""

    requirements, branches = _bounded_inputs(happy_birthday_package)
    reduced = generate_acquisition_graph(
        requirements,
        branches,
        reference_tempo_bpm=Fraction(120),
        reference_authority=TempoReferenceAuthority.SOURCE,
        tempo_evidence=_tempo_evidence(
            requirements,
            {"upper-layer": 70, "lower-layer": 70, "combined": 70},
        ),
    )
    reduced_plan = next(
        item
        for item in reduced.tempo_plans
        if item.practice_scope_ref.id
        == next(
            scope.id
            for scope in requirements.scopes
            if scope.notation_condition.value == "combined"
        )
    )
    supported = decide_tempo_probe(
        reduced_plan,
        TempoProbeResult(80, True, True, "evidence:combined-at-80"),
    )
    unstable = decide_tempo_probe(
        reduced_plan,
        TempoProbeResult(80, True, False, "evidence:combined-unstable-at-80"),
    )
    ready = generate_acquisition_graph(
        requirements,
        branches,
        reference_tempo_bpm=Fraction(120),
        reference_authority=TempoReferenceAuthority.SOURCE,
        tempo_evidence=_tempo_evidence(
            requirements,
            {"upper-layer": 100, "lower-layer": 100, "combined": 100},
        ),
    )

    assert supported.action is TempoPolicyAction.INCREASE
    assert supported.resulting_controlled_percentage == 80
    assert unstable.action is TempoPolicyAction.MAINTAIN
    assert unstable.resulting_controlled_percentage == 70
    assert all(item.current_controlled_percentage == 100 for item in ready.tempo_plans)
    assert all(item.kind is not AcquisitionStageKind.TEMPO_DIAGNOSTIC for item in ready.stages)


def test_checkpoint_mutation_and_unresolved_topology_fail_closed(
    hot_cross_buns_package: CanonicalMusicPackage,
    moonlight_package: CanonicalMusicPackage,
) -> None:
    """TEST-CURR-ROBUSTNESS-003: missing checkpoints and ambiguous layers stop."""

    requirements, branches = _bounded_inputs(hot_cross_buns_package)
    graph = generate_acquisition_graph(
        requirements,
        branches,
        reference_tempo_bpm=Fraction(100),
        reference_authority=TempoReferenceAuthority.CALLER,
        tempo_evidence=_tempo_evidence(requirements, {"single-layer": 70}),
    )
    changed = replace(
        graph,
        edges=tuple(edge for edge in graph.edges if edge.kind.value != "checkpoint-after"),
    )
    codes = {item.code for item in validate_acquisition_graph_slice(changed)}
    moonlight_requirements = derive_passage_requirements(
        moonlight_package,
        analyze_canonical_score(moonlight_package, end_measure_ordinal=69),
    )
    moonlight = generate_acquisition_graph(
        moonlight_requirements,
        generate_prerequisite_branches(moonlight_requirements),
        reference_tempo_bpm=Fraction(60),
        reference_authority=TempoReferenceAuthority.CALLER,
    )

    assert "TMM-GRAPH-CHECKPOINT-MISSING" in codes
    assert "TMM-CONTRACT-FINGERPRINT-MISMATCH" in codes
    assert moonlight.resolution is ArtifactResolution.REVIEW_REQUIRED
    assert moonlight.stages == ()
    assert [item.code for item in moonlight.diagnostics] == ["TMM-HAND-INTERPRETATION-REQUIRED"]
    assert validate_acquisition_graph_slice(moonlight) == ()


def test_frozen_numeric_configuration_is_stable() -> None:
    """TEST-CURR-POLICY-003: numeric probes, budgets, and cadence are frozen."""

    first = default_tempo_configuration()
    second = default_tempo_configuration()

    assert first == second
    assert first.diagnostic_probe_percentages == (100, 85, 70, 55)
    assert first.tempo_increment_percentage == 10
    assert first.tempo_tolerance_percentage == 5
    assert first.diagnostic_attempt_budget == 4
    assert first.acquisition_retry_budget == 3
    assert first.tempo_probe_retry_budget == 2
    assert first.remediation_budget == 2
    assert first.phrase_group_size == 2
    assert first.stable_performance_passes == 2
