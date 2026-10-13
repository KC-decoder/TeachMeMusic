"""End-to-end deterministic route evidence for DEV-009 Task 9E."""

from __future__ import annotations

from fractions import Fraction

import pytest

from teachmemusic.analysis import analyze_canonical_score
from teachmemusic.performance import (
    AttemptCompletion,
    CalibrationProfile,
    LearnerAttempt,
    MidiEventKind,
    NormalizedMidiEvent,
    ObservationStatus,
    align_layer_attempt,
)
from teachmemusic.score import CanonicalMusicPackage
from teachmemusic.teaching import (
    AcquisitionStageKind,
    ArtifactResolution,
    CompatibleTempoEvidence,
    CurriculumEvidenceResult,
    CurriculumMasteryStatus,
    CurriculumPresentationError,
    CurriculumUnlockAction,
    EvidenceContext,
    ExecutionAssignment,
    NotationCondition,
    PracticeMode,
    ReviewState,
    SemanticReference,
    SupportState,
    TempoReferenceAuthority,
    build_curriculum_combined_expected_performance,
    build_curriculum_evidence_records,
    build_curriculum_layer_expected_performance,
    build_curriculum_passage_presentation,
    decide_curriculum_unlock,
    derive_passage_requirements,
    generate_acquisition_graph,
    generate_prerequisite_branches,
    validate_acquisition_graph_slice,
    validate_curriculum_passage_presentation,
    validate_prerequisite_branch_set,
    validate_requirement_set,
)


def _calibration() -> CalibrationProfile:
    return CalibrationProfile(
        id="calibration:cross-score-route",
        version="calibration-v1",
        device_id="device:route-fixture",
        input_name="Deterministic route fixture",
        timestamp_origin="monotonic-microseconds",
        pitch_numbering_confirmed=True,
        sustain_available=True,
        clock_offset_microseconds=0,
        clock_jitter_microseconds=1_000,
        timing_window_microseconds=50_000,
        chord_window_microseconds=50_000,
        approved=True,
        approved_at_utc="2026-10-11T12:00:00Z",
    )


def _hcb_support() -> SupportState:
    return SupportState(
        id="support:hcb-route-70",
        notation_visible=True,
        cursor_visible=False,
        note_names_visible=False,
        keyboard_highlighting=False,
        fingering_visible=False,
        demonstration_available=False,
        follow_mode=False,
        metronome=True,
        tempo_percent=70,
        isolated_layers=("single-written-layer",),
        isolated_dimensions=(),
        tempo_bpm=Fraction(70),
    )


def _exact_attempt(
    expected,
    *,
    attempt_id: str,
    support_state_id: str,
) -> LearnerAttempt:
    start = 1_000_000
    events: list[NormalizedMidiEvent] = []
    for index, note in enumerate(expected.notes):
        events.extend(
            (
                NormalizedMidiEvent(
                    id=f"midi-event:route-{attempt_id.rsplit(':', 1)[-1]}-{index:03d}-on",
                    raw_message_id=None,
                    kind=MidiEventKind.NOTE_ON,
                    timestamp_microseconds=start + note.start_microseconds,
                    channel=1,
                    note=note.midi_pitch,
                    velocity=80,
                ),
                NormalizedMidiEvent(
                    id=f"midi-event:route-{attempt_id.rsplit(':', 1)[-1]}-{index:03d}-off",
                    raw_message_id=None,
                    kind=MidiEventKind.NOTE_OFF,
                    timestamp_microseconds=start + note.end_microseconds,
                    channel=1,
                    note=note.midi_pitch,
                    velocity=0,
                ),
            )
        )
    ordered = tuple(sorted(events, key=lambda item: (item.timestamp_microseconds, item.id)))
    return LearnerAttempt(
        id=attempt_id,
        run_id="run:cross-score-route",
        exercise_id=expected.exercise_id,
        calibration_id="calibration:cross-score-route",
        practice_mode=expected.practice_mode,
        support_state_id=support_state_id,
        started_at_utc="2026-10-11T12:01:00Z",
        start_microseconds=start,
        end_microseconds=ordered[-1].timestamp_microseconds + 1_000,
        completion=AttemptCompletion.COMPLETED,
        normalized_events=ordered,
    )


def test_hot_cross_buns_completes_the_single_layer_deterministic_route(
    hot_cross_buns_package: CanonicalMusicPackage,
) -> None:
    """TEST-CURR-POLICY-006: the full monophonic route composes end to end."""

    analysis = analyze_canonical_score(hot_cross_buns_package)
    requirements = derive_passage_requirements(hot_cross_buns_package, analysis)
    scope = requirements.scopes[0]
    branches = generate_prerequisite_branches(requirements)
    tempo_evidence = (
        CompatibleTempoEvidence(
            SemanticReference(
                "practice-scope-assignment",
                scope.id,
                scope.semantic_fingerprint,
            ),
            "independent-piece",
            70,
            70,
            True,
            True,
            ("evidence:hcb-independent-70",),
        ),
    )
    graph = generate_acquisition_graph(
        requirements,
        branches,
        reference_tempo_bpm=Fraction(100),
        reference_authority=TempoReferenceAuthority.CALLER,
        tempo_evidence=tempo_evidence,
    )
    presentation = build_curriculum_passage_presentation(
        hot_cross_buns_package,
        requirements,
        scope.id,
    )
    expected = build_curriculum_layer_expected_performance(
        hot_cross_buns_package,
        presentation,
        PracticeMode.INDEPENDENT_PERFORMANCE,
        tempo_bpm=Fraction(70),
    )

    assert validate_requirement_set(requirements, hot_cross_buns_package, analysis) == ()
    assert validate_acquisition_graph_slice(graph) == ()
    assert validate_curriculum_passage_presentation(presentation, scope) == ()
    assert scope.notation_condition is NotationCondition.SINGLE_LAYER
    assert scope.inactive_context_ids == ()
    assert len(scope.active_target_ids) == 20
    assert tuple(stage.kind for stage in graph.stages) == (
        AcquisitionStageKind.COMPONENT_ACQUISITION,
        AcquisitionStageKind.PULSE_INTEGRATION,
        AcquisitionStageKind.PHRASE_CONTROLLED_TEMPO,
        AcquisitionStageKind.LEARNED_TO_DATE,
        AcquisitionStageKind.TEMPO_DEVELOPMENT,
    )
    assert all(
        stage.kind is not AcquisitionStageKind.SELF_PACED_COORDINATION for stage in graph.stages
    )
    assert expected.layer_target is not None
    assert expected.layer_target.notation_condition == NotationCondition.SINGLE_LAYER.value
    sounding_source_ids = {source_id for note in expected.notes for source_id in note.expected_ids}
    assert len(expected.notes) == 17
    assert sounding_source_ids < set(scope.active_target_ids)
    assert len(set(scope.active_target_ids) - sounding_source_ids) == 3

    node_by_id = {item.id: item for item in graph.nodes}
    exercise_by_id = {item.id: item for item in graph.exercises}
    satisfied = set(node_by_id[graph.stages[0].node_id].component_node_ids)
    decisions = []
    for index, stage in enumerate(graph.stages):
        node = node_by_id[stage.node_id]
        assert node.exercise_ref is not None
        exercise = exercise_by_id[node.exercise_ref.id]
        assert {item.evidence_context for item in exercise.required_evidence_exits} <= {
            "passage-application",
            "connected-learned-to-date",
            "tempo-development",
        }
        attempt = _exact_attempt(
            expected,
            attempt_id=f"attempt:hcb-route-{index}",
            support_state_id=_hcb_support().id,
        )
        observations = align_layer_attempt(expected, attempt, _calibration())
        records = tuple(
            item
            for item in build_curriculum_evidence_records(
                requirements,
                expected,
                attempt,
                _hcb_support(),
                observations,
                EvidenceContext.INDEPENDENT,
            )
            if item.requirement_ref.id == node.requirement_ref.id
        )

        assert records
        assert all(item.result is CurriculumEvidenceResult.MATCHED for item in records)
        assert all(item.evidence_context is EvidenceContext.INDEPENDENT for item in records)
        assert all(
            item.status is ObservationStatus.MATCH
            for item in observations
            if item.dimension in {record.dimension for record in records}
        )
        projection, decision = decide_curriculum_unlock(
            graph,
            node.id,
            _hcb_support(),
            records,
            previously_satisfied_node_ids=tuple(
                item.id for item in graph.nodes if item.id in satisfied
            ),
        )
        assert projection.status is CurriculumMasteryStatus.MASTERED
        assert projection.evidence_context is EvidenceContext.INDEPENDENT
        decisions.append(decision)
        satisfied.add(node.id)

        if index + 1 < len(graph.stages):
            assert decision.action is CurriculumUnlockAction.UNLOCK_SUCCESSOR
            assert decision.next_node_id == graph.stages[index + 1].node_id
        else:
            assert decision.action is CurriculumUnlockAction.COMPLETE_NODE
            assert decision.next_node_id is None

    assert tuple(item.current_node_id for item in decisions) == tuple(
        item.node_id for item in graph.stages
    )


def _happy_birthday_support(
    condition: NotationCondition,
    mode: PracticeMode,
    *,
    tempo_percent: int,
    tempo_bpm: Fraction,
) -> SupportState:
    independent = mode is PracticeMode.INDEPENDENT_PERFORMANCE
    return SupportState(
        id=f"support:hb-route:{condition.value}:{mode.value}:{tempo_percent}",
        notation_visible=True,
        cursor_visible=not independent,
        note_names_visible=False,
        keyboard_highlighting=not independent,
        fingering_visible=False,
        demonstration_available=not independent,
        follow_mode=False,
        metronome=True,
        tempo_percent=tempo_percent,
        isolated_layers=(condition.value,),
        isolated_dimensions=(),
        tempo_bpm=tempo_bpm,
    )


def test_happy_birthday_completes_the_layered_deterministic_route(
    happy_birthday_package: CanonicalMusicPackage,
) -> None:
    """TEST-CURR-POLICY-007: components gate the complete polyphonic route."""

    analysis = analyze_canonical_score(happy_birthday_package)
    requirements = derive_passage_requirements(happy_birthday_package, analysis)
    scopes = {item.notation_condition: item for item in requirements.scopes}
    percentages = {
        NotationCondition.UPPER_LAYER: 85,
        NotationCondition.LOWER_LAYER: 70,
        NotationCondition.COMBINED: 70,
    }
    tempo_evidence = tuple(
        CompatibleTempoEvidence(
            SemanticReference(
                "practice-scope-assignment",
                scope.id,
                scope.semantic_fingerprint,
            ),
            "independent-piece",
            percentages[condition],
            percentages[condition],
            True,
            True,
            (f"evidence:hb-{condition.value}",),
        )
        for condition, scope in scopes.items()
    )
    graph = generate_acquisition_graph(
        requirements,
        generate_prerequisite_branches(requirements),
        reference_tempo_bpm=Fraction(120),
        reference_authority=TempoReferenceAuthority.SOURCE,
        tempo_evidence=tempo_evidence,
    )
    presentations = {
        condition: build_curriculum_passage_presentation(
            happy_birthday_package,
            requirements,
            scope.id,
        )
        for condition, scope in scopes.items()
    }

    upper = scopes[NotationCondition.UPPER_LAYER]
    lower = scopes[NotationCondition.LOWER_LAYER]
    combined = scopes[NotationCondition.COMBINED]
    assert validate_requirement_set(requirements, happy_birthday_package, analysis) == ()
    assert validate_acquisition_graph_slice(graph) == ()
    assert all(
        validate_curriculum_passage_presentation(presentations[condition], scope) == ()
        for condition, scope in scopes.items()
    )
    assert len(upper.active_target_ids) == 25
    assert len(upper.inactive_context_ids) == 34
    assert len(lower.active_target_ids) == 34
    assert len(lower.inactive_context_ids) == 25
    assert len(combined.active_target_ids) == 59
    assert combined.inactive_context_ids == ()
    assert set(upper.active_target_ids).isdisjoint(lower.active_target_ids)
    assert set(upper.active_target_ids) | set(lower.active_target_ids) == set(
        combined.active_target_ids
    )
    assert combined.component_scope_ids == (upper.id, lower.id)
    assert tuple(stage.kind for stage in graph.stages) == (
        AcquisitionStageKind.COMPONENT_ACQUISITION,
        AcquisitionStageKind.COMPONENT_ACQUISITION,
        AcquisitionStageKind.SELF_PACED_COORDINATION,
        AcquisitionStageKind.PULSE_INTEGRATION,
        AcquisitionStageKind.PHRASE_CONTROLLED_TEMPO,
        AcquisitionStageKind.LEARNED_TO_DATE,
        AcquisitionStageKind.TEMPO_DEVELOPMENT,
    )

    stage_specs = (
        (
            NotationCondition.UPPER_LAYER,
            PracticeMode.INDEPENDENT_PERFORMANCE,
            EvidenceContext.INDEPENDENT,
            "passage-application",
        ),
        (
            NotationCondition.LOWER_LAYER,
            PracticeMode.INDEPENDENT_PERFORMANCE,
            EvidenceContext.INDEPENDENT,
            "passage-application",
        ),
        (
            NotationCondition.COMBINED,
            PracticeMode.SUPPORTED_PERFORMANCE,
            EvidenceContext.INTEGRATION,
            "coordination-preparation",
        ),
        (
            NotationCondition.COMBINED,
            PracticeMode.SUPPORTED_PERFORMANCE,
            EvidenceContext.INTEGRATION,
            "integration",
        ),
        (
            NotationCondition.COMBINED,
            PracticeMode.INDEPENDENT_PERFORMANCE,
            EvidenceContext.INDEPENDENT,
            "passage-application",
        ),
        (
            NotationCondition.COMBINED,
            PracticeMode.INDEPENDENT_PERFORMANCE,
            EvidenceContext.INDEPENDENT,
            "connected-learned-to-date",
        ),
        (
            NotationCondition.COMBINED,
            PracticeMode.INDEPENDENT_PERFORMANCE,
            EvidenceContext.INDEPENDENT,
            "tempo-development",
        ),
    )
    node_by_id = {item.id: item for item in graph.nodes}
    exercise_by_id = {item.id: item for item in graph.exercises}
    plan_by_id = {item.id: item for item in graph.tempo_plans}
    stage_node_ids = {item.node_id for item in graph.stages}
    prerequisite_closure = {
        dependency
        for stage in graph.stages
        for dependency in node_by_id[stage.node_id].component_node_ids
        if dependency not in stage_node_ids
    }
    satisfied = set(prerequisite_closure)
    decisions = []
    component_sound_ids: dict[NotationCondition, set[str]] = {}
    combined_sound_ids: set[str] = set()

    for index, (stage, spec) in enumerate(zip(graph.stages, stage_specs, strict=True)):
        condition, mode, evidence_context, exit_context = spec
        node = node_by_id[stage.node_id]
        assert node.exercise_ref is not None
        assert node.requirement_ref is not None
        exercise = exercise_by_id[node.exercise_ref.id]
        assert {item.evidence_context for item in exercise.required_evidence_exits} == {
            exit_context
        }
        plan = plan_by_id[stage.tempo_plan_ref.id]
        assert plan.current_controlled_percentage is not None
        tempo_percent = plan.current_controlled_percentage
        tempo_bpm = Fraction(120 * tempo_percent, 100)
        if condition is NotationCondition.COMBINED:
            expected = build_curriculum_combined_expected_performance(
                happy_birthday_package,
                requirements,
                presentations[condition],
                (
                    presentations[NotationCondition.UPPER_LAYER],
                    presentations[NotationCondition.LOWER_LAYER],
                ),
                mode,
                tempo_bpm=tempo_bpm,
            )
        else:
            expected = build_curriculum_layer_expected_performance(
                happy_birthday_package,
                presentations[condition],
                mode,
                tempo_bpm=tempo_bpm,
            )
        support = _happy_birthday_support(
            condition,
            mode,
            tempo_percent=tempo_percent,
            tempo_bpm=tempo_bpm,
        )
        attempt = _exact_attempt(
            expected,
            attempt_id=f"attempt:hb-route-{index}",
            support_state_id=support.id,
        )
        observations = align_layer_attempt(expected, attempt, _calibration())
        records = tuple(
            item
            for item in build_curriculum_evidence_records(
                requirements,
                expected,
                attempt,
                support,
                observations,
                evidence_context,
            )
            if item.requirement_ref.id == node.requirement_ref.id
        )

        assert records
        assert all(item.result is CurriculumEvidenceResult.MATCHED for item in records)
        assert all(item.evidence_context is evidence_context for item in records)
        assert expected.layer_target is not None
        sound_ids = {source_id for note in expected.notes for source_id in note.expected_ids}
        if condition is NotationCondition.COMBINED:
            combined_sound_ids = sound_ids
            assert len(expected.layer_target.components) == 2
        else:
            component_sound_ids[condition] = sound_ids

        if stage.kind is AcquisitionStageKind.COMPONENT_ACQUISITION and index == 1:
            projection, blocked = decide_curriculum_unlock(
                graph,
                node.id,
                support,
                records,
                previously_satisfied_node_ids=tuple(
                    item.id for item in graph.nodes if item.id in prerequisite_closure
                ),
            )
            assert projection.status is CurriculumMasteryStatus.MASTERED
            assert blocked.action is CurriculumUnlockAction.COMPLETE_NODE
            assert blocked.next_node_id is None
            assert any(
                item.reason_code == "TMM-POLICY-COMPONENTS-INCOMPLETE"
                for item in blocked.rejected_edges
            )

        projection, decision = decide_curriculum_unlock(
            graph,
            node.id,
            support,
            records,
            previously_satisfied_node_ids=tuple(
                item.id for item in graph.nodes if item.id in satisfied
            ),
        )
        assert projection.status is CurriculumMasteryStatus.MASTERED
        assert projection.evidence_context is evidence_context
        decisions.append(decision)
        satisfied.add(node.id)

        if index + 1 < len(graph.stages):
            assert decision.action is CurriculumUnlockAction.UNLOCK_SUCCESSOR
            assert decision.next_node_id == graph.stages[index + 1].node_id
        else:
            assert decision.action is CurriculumUnlockAction.COMPLETE_NODE
            assert decision.next_node_id is None

    assert len(component_sound_ids[NotationCondition.UPPER_LAYER]) == 25
    assert len(component_sound_ids[NotationCondition.LOWER_LAYER]) == 27
    assert len(combined_sound_ids) == 52
    assert (
        component_sound_ids[NotationCondition.UPPER_LAYER]
        | component_sound_ids[NotationCondition.LOWER_LAYER]
        == combined_sound_ids
    )
    assert tuple(item.current_node_id for item in decisions) == tuple(
        item.node_id for item in graph.stages
    )


def test_moonlight_stops_at_the_bounded_interpretation_review(
    moonlight_package: CanonicalMusicPackage,
) -> None:
    """TEST-CURR-POLICY-008: complex topology cannot become guessed teaching."""

    analysis = analyze_canonical_score(moonlight_package, end_measure_ordinal=69)
    requirements = derive_passage_requirements(moonlight_package, analysis)
    branches = generate_prerequisite_branches(requirements)
    graph = generate_acquisition_graph(
        requirements,
        branches,
        reference_tempo_bpm=Fraction(60),
        reference_authority=TempoReferenceAuthority.CALLER,
    )
    scope = requirements.scopes[0]
    diagnostic = requirements.diagnostics[0]

    assert (analysis.scope.start_measure_ordinal, analysis.scope.end_measure_ordinal) == (1, 69)
    assert len(analysis.facts) == 13
    assert (
        analysis.texture.layer_count,
        analysis.texture.staff_count,
        analysis.texture.voice_count,
        analysis.texture.chord_count,
        analysis.texture.max_simultaneous_pitches,
        analysis.texture.max_active_layers,
    ) == (6, 2, 4, 106, 6, 4)
    assert tuple(
        (
            layer.staff_id.rsplit(":", 1)[-1],
            layer.voice_id.rsplit(":", 1)[-1],
            len(layer.event_ids),
            layer.pitched_event_count,
            layer.rest_event_count,
        )
        for layer in analysis.layers
    ) == (
        ("1", "1", 367, 338, 29),
        ("1", "2", 479, 477, 2),
        ("2", "1", 13, 13, 0),
        ("2", "2", 95, 95, 0),
        ("2", "5", 250, 250, 0),
        ("2", "6", 8, 8, 0),
    )

    assert validate_requirement_set(requirements, moonlight_package, analysis) == ()
    assert scope.resolution is ArtifactResolution.REVIEW_REQUIRED
    assert scope.notation_condition is NotationCondition.COMBINED
    assert scope.execution_assignment is ExecutionAssignment.UNASSIGNED
    assert scope.review_state is ReviewState.PENDING
    assert scope.review_ref is None
    assert scope.layer_groups == ()
    assert scope.component_scope_ids == ()
    assert scope.omissions == ()
    assert len(scope.event_universe_ids) == 1_212
    assert scope.active_target_ids == scope.event_universe_ids
    assert scope.inactive_context_ids == ()
    assert requirements.requirements == ()
    assert diagnostic.code == "TMM-HAND-INTERPRETATION-REQUIRED"
    assert diagnostic.path == "practice-scope.layer-groups"
    assert diagnostic.outcome is ArtifactResolution.REVIEW_REQUIRED
    assert diagnostic.related_ids == tuple(layer.id for layer in analysis.layers)

    assert validate_prerequisite_branch_set(branches, requirements) == ()
    assert branches.resolution is ArtifactResolution.REVIEW_REQUIRED
    assert branches.diagnostics == requirements.diagnostics
    assert branches.nodes == ()
    assert branches.edges == ()
    assert branches.exercises == ()
    assert branches.branches == ()

    assert validate_acquisition_graph_slice(graph) == ()
    assert graph.resolution is ArtifactResolution.REVIEW_REQUIRED
    assert graph.diagnostics == requirements.diagnostics
    assert graph.nodes == ()
    assert graph.edges == ()
    assert graph.exercises == ()
    assert graph.branches == ()
    assert graph.stages == ()
    assert graph.tempo_plans == ()

    with pytest.raises(CurriculumPresentationError, match="TMM-PRESENTATION-SCOPE-UNRESOLVED"):
        build_curriculum_passage_presentation(
            moonlight_package,
            requirements,
            scope.id,
        )
