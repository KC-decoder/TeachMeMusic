"""Executable DEV-009 9D.1–9D.2 written-layer matching evidence."""

from __future__ import annotations

from dataclasses import replace
from fractions import Fraction

import pytest

from teachmemusic.analysis import analyze_canonical_score
from teachmemusic.performance import (
    COMBINED_LAYER_ALIGNMENT_POLICY_VERSION,
    AttemptAlignmentError,
    AttemptCompletion,
    CalibrationProfile,
    LearnerAttempt,
    MidiEventKind,
    NormalizedMidiEvent,
    ObservationDimension,
    ObservationStatus,
    align_layer_attempt,
    expected_layer_target_fingerprint,
)
from teachmemusic.score import CanonicalMusicPackage
from teachmemusic.teaching import (
    AcquisitionStageKind,
    CompatibleTempoEvidence,
    CurriculumEvidenceError,
    CurriculumEvidenceResult,
    CurriculumMasteryStatus,
    CurriculumPolicyError,
    CurriculumUnlockAction,
    EvidenceContext,
    ExpectedPerformanceProjectionError,
    LastingSkillStageKind,
    NotationCondition,
    PracticeMode,
    SemanticReference,
    SupportState,
    TempoReferenceAuthority,
    TransferTargetRequest,
    build_curriculum_combined_expected_performance,
    build_curriculum_evidence_records,
    build_curriculum_layer_expected_performance,
    build_curriculum_passage_presentation,
    curriculum_evidence_record_from_json,
    curriculum_evidence_record_to_json,
    curriculum_mastery_projection_from_json,
    curriculum_mastery_projection_to_json,
    curriculum_unlock_decision_from_json,
    curriculum_unlock_decision_to_json,
    decide_curriculum_unlock,
    derive_passage_requirements,
    generate_acquisition_graph,
    generate_lasting_skill_graph,
    generate_prerequisite_branches,
    require_compatible_curriculum_evidence,
)


def _calibration() -> CalibrationProfile:
    return CalibrationProfile(
        id="calibration:curriculum-layer",
        version="calibration-v1",
        device_id="device:casio-px-770",
        input_name="CASIO USB-MIDI",
        timestamp_origin="browser-monotonic-microseconds",
        pitch_numbering_confirmed=True,
        sustain_available=True,
        clock_offset_microseconds=0,
        clock_jitter_microseconds=1_000,
        timing_window_microseconds=50_000,
        chord_window_microseconds=50_000,
        approved=True,
        approved_at_utc="2026-10-10T12:00:00Z",
    )


def _exact_attempt(expected, *, attempt_id: str) -> LearnerAttempt:
    start = 1_000_000
    events: list[NormalizedMidiEvent] = []
    serial = 0
    for note in expected.notes:
        events.append(
            NormalizedMidiEvent(
                id=f"midi-event:{attempt_id.split(':')[-1]}-{serial:04d}",
                raw_message_id=None,
                kind=MidiEventKind.NOTE_ON,
                timestamp_microseconds=start + note.start_microseconds,
                channel=1,
                note=note.midi_pitch,
                velocity=80,
            )
        )
        serial += 1
        events.append(
            NormalizedMidiEvent(
                id=f"midi-event:{attempt_id.split(':')[-1]}-{serial:04d}",
                raw_message_id=None,
                kind=MidiEventKind.NOTE_OFF,
                timestamp_microseconds=start + note.end_microseconds,
                channel=1,
                note=note.midi_pitch,
                velocity=0,
            )
        )
        serial += 1
    ordered = tuple(sorted(events, key=lambda item: (item.timestamp_microseconds, item.id)))
    return LearnerAttempt(
        id=attempt_id,
        run_id="run:curriculum-layer",
        exercise_id=expected.exercise_id,
        calibration_id="calibration:curriculum-layer",
        practice_mode=expected.practice_mode,
        support_state_id="support:curriculum-layer",
        started_at_utc="2026-10-10T12:01:00Z",
        start_microseconds=start,
        end_microseconds=ordered[-1].timestamp_microseconds + 1_000,
        completion=AttemptCompletion.COMPLETED,
        normalized_events=ordered,
    )


def _support(
    *, support_id: str = "support:curriculum-layer", tempo_percent: int = 60
) -> SupportState:
    return SupportState(
        id=support_id,
        notation_visible=True,
        cursor_visible=True,
        note_names_visible=False,
        keyboard_highlighting=True,
        fingering_visible=False,
        demonstration_available=True,
        follow_mode=True,
        metronome=False,
        tempo_percent=tempo_percent,
        isolated_layers=("written-layer",),
        isolated_dimensions=("pitch", "order"),
    )


def _layer_fixture(package: CanonicalMusicPackage):
    requirements = derive_passage_requirements(
        package,
        analyze_canonical_score(package, end_measure_ordinal=2),
    )
    presentations = {
        condition: build_curriculum_passage_presentation(
            package,
            requirements,
            next(
                scope.id for scope in requirements.scopes if scope.notation_condition is condition
            ),
        )
        for condition in (
            NotationCondition.UPPER_LAYER,
            NotationCondition.LOWER_LAYER,
            NotationCondition.COMBINED,
        )
    }
    return requirements, presentations


def _acquisition_graph(requirements):
    percentages = {
        "single-layer": 70,
        "upper-layer": 85,
        "lower-layer": 70,
        "combined": 70,
    }
    tempo_evidence = tuple(
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
        reference_tempo_bpm=Fraction(120),
        reference_authority=TempoReferenceAuthority.SOURCE,
        tempo_evidence=tempo_evidence,
    )


def _records_for_target(
    requirements,
    expected,
    *,
    attempt_id: str,
    evidence_context: EvidenceContext,
    requirement_id: str,
):
    attempt = _exact_attempt(expected, attempt_id=attempt_id)
    records = build_curriculum_evidence_records(
        requirements,
        expected,
        attempt,
        _support(),
        align_layer_attempt(expected, attempt, _calibration()),
        evidence_context,
    )
    return tuple(item for item in records if item.requirement_ref.id == requirement_id)


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
                scope.notation_condition
                for scope in target.scopes
                if scope.id == item.practice_scope_ref.id
            )
            is NotationCondition.UPPER_LAYER
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


def test_upper_and_lower_layers_produce_independent_comparison_targets(
    happy_birthday_package: CanonicalMusicPackage,
) -> None:
    """TEST-CURR-VALIDATION-018: each written layer has isolated evidence."""

    _, presentations = _layer_fixture(happy_birthday_package)
    expected = {
        condition: build_curriculum_layer_expected_performance(
            happy_birthday_package,
            presentations[condition],
            PracticeMode.SUPPORTED_PERFORMANCE,
        )
        for condition in (NotationCondition.UPPER_LAYER, NotationCondition.LOWER_LAYER)
    }

    assert (
        expected[NotationCondition.UPPER_LAYER].exercise_id
        != expected[NotationCondition.LOWER_LAYER].exercise_id
    )
    for condition, target in expected.items():
        assert target.layer_target is not None
        active = set(target.layer_target.active_event_ids)
        inactive = set(target.layer_target.inactive_event_ids)
        source_ids = {item for note in target.notes for item in note.expected_ids}
        assert source_ids <= active
        assert source_ids.isdisjoint(inactive)
        attempt = _exact_attempt(target, attempt_id=f"attempt:{condition.value}")
        observations = align_layer_attempt(target, attempt, _calibration())
        assert observations
        assert all(set(item.expected_canonical_ids) <= active for item in observations)
        pitch = tuple(item for item in observations if item.dimension is ObservationDimension.PITCH)
        assert pitch
        assert all(item.status is ObservationStatus.MATCH for item in pitch)
        assert all(
            item.matching_policy is not None
            and item.matching_policy.startswith("curriculum-layer-alignment-v1:")
            for item in observations
        )


def test_single_layer_score_uses_the_same_isolated_matching_boundary(
    hot_cross_buns_package: CanonicalMusicPackage,
) -> None:
    """TEST-CURR-VALIDATION-019: monophonic material uses the layer contract."""

    requirements = derive_passage_requirements(
        hot_cross_buns_package,
        analyze_canonical_score(hot_cross_buns_package, end_measure_ordinal=2),
    )
    scope = next(
        item
        for item in requirements.scopes
        if item.notation_condition is NotationCondition.SINGLE_LAYER
    )
    presentation = build_curriculum_passage_presentation(
        hot_cross_buns_package,
        requirements,
        scope.id,
    )
    expected = build_curriculum_layer_expected_performance(
        hot_cross_buns_package,
        presentation,
        PracticeMode.SUPPORTED_PERFORMANCE,
    )
    observations = align_layer_attempt(
        expected,
        _exact_attempt(expected, attempt_id="attempt:single-layer"),
        _calibration(),
    )

    assert expected.layer_target is not None
    assert expected.layer_target.notation_condition == "single-layer"
    assert all(
        set(item.expected_canonical_ids) <= set(expected.layer_target.active_event_ids)
        for item in observations
    )


def test_an_attempt_for_one_layer_cannot_satisfy_another_layer(
    happy_birthday_package: CanonicalMusicPackage,
) -> None:
    """TEST-CURR-ROBUSTNESS-014: cross-layer attempt reuse fails closed."""

    _, presentations = _layer_fixture(happy_birthday_package)
    upper = build_curriculum_layer_expected_performance(
        happy_birthday_package,
        presentations[NotationCondition.UPPER_LAYER],
        PracticeMode.SUPPORTED_PERFORMANCE,
    )
    lower = build_curriculum_layer_expected_performance(
        happy_birthday_package,
        presentations[NotationCondition.LOWER_LAYER],
        PracticeMode.SUPPORTED_PERFORMANCE,
    )
    upper_attempt = _exact_attempt(upper, attempt_id="attempt:upper-layer")

    with pytest.raises(AttemptAlignmentError, match="PERF_ALIGNMENT_EXERCISE"):
        align_layer_attempt(lower, upper_attempt, _calibration())

    assert upper.layer_target is not None
    assert lower.layer_target is not None
    leaked_note = replace(upper.notes[0], expected_ids=(lower.layer_target.active_event_ids[0],))
    leaked = replace(upper, notes=(leaked_note, *upper.notes[1:]))
    with pytest.raises(AttemptAlignmentError, match="PERF_ALIGNMENT_LAYER_LEAK"):
        align_layer_attempt(leaked, upper_attempt, _calibration())

    tampered = replace(
        upper,
        layer_target=replace(upper.layer_target, execution_assignment="unsupported-hand"),
    )
    with pytest.raises(AttemptAlignmentError, match="PERF_ALIGNMENT_LAYER_ASSIGNMENT"):
        align_layer_attempt(tampered, upper_attempt, _calibration())


def test_combined_layer_matching_remains_deferred_to_task_9d2(
    happy_birthday_package: CanonicalMusicPackage,
) -> None:
    """TEST-CURR-ROBUSTNESS-015: 9D.1 cannot claim combined evidence."""

    _, presentations = _layer_fixture(happy_birthday_package)

    with pytest.raises(
        ExpectedPerformanceProjectionError,
        match="TEACH_EXPECTED_COMBINED_DEFERRED",
    ):
        build_curriculum_layer_expected_performance(
            happy_birthday_package,
            presentations[NotationCondition.COMBINED],
            PracticeMode.SUPPORTED_PERFORMANCE,
        )


def test_combined_target_preserves_component_identity_per_pitch(
    happy_birthday_package: CanonicalMusicPackage,
) -> None:
    """TEST-CURR-VALIDATION-020: combined notes retain component identity."""

    requirements, presentations = _layer_fixture(happy_birthday_package)
    component_presentations = (
        presentations[NotationCondition.UPPER_LAYER],
        presentations[NotationCondition.LOWER_LAYER],
    )
    expected = build_curriculum_combined_expected_performance(
        happy_birthday_package,
        requirements,
        presentations[NotationCondition.COMBINED],
        component_presentations,
        PracticeMode.SUPPORTED_PERFORMANCE,
    )

    assert expected.layer_target is not None
    target = expected.layer_target
    assert tuple(item.practice_scope_id for item in target.components) == tuple(
        item.practice_scope_ref.id for item in component_presentations
    )
    component_events = {
        item.practice_scope_id: set(item.active_event_ids) for item in target.components
    }
    assert set().union(*component_events.values()) == set(target.active_event_ids)
    assert all(
        tuple(item.expected_id for item in note.layer_memberships) == note.expected_ids
        and all(
            item.expected_id in component_events[item.component_scope_id]
            for item in note.layer_memberships
        )
        for note in expected.notes
    )

    observations = align_layer_attempt(
        expected,
        _exact_attempt(expected, attempt_id="attempt:combined-layer"),
        _calibration(),
    )
    musical = tuple(
        item
        for item in observations
        if item.dimension in {ObservationDimension.PITCH, ObservationDimension.CHORD_SET}
    )
    assert musical
    assert all(item.status is ObservationStatus.MATCH for item in musical)
    assert all(
        item.matching_policy is not None
        and item.matching_policy.startswith(f"{COMBINED_LAYER_ALIGNMENT_POLICY_VERSION}:")
        for item in observations
    )
    topology = tuple(
        item
        for item in observations
        if item.dimension is ObservationDimension.HUMAN_REVIEW
        and item.expected_value is not None
        and item.expected_value.startswith("canonical-layer-pitches:")
    )
    assert topology
    assert all(
        component.practice_scope_id in item.expected_value
        for component in target.components
        for item in topology
    )
    assert all(not item.blocking for item in topology)


def test_component_and_combined_attempts_cannot_backfill_each_other(
    happy_birthday_package: CanonicalMusicPackage,
) -> None:
    """TEST-CURR-ROBUSTNESS-016: component and combined evidence stay separate."""

    requirements, presentations = _layer_fixture(happy_birthday_package)
    upper = build_curriculum_layer_expected_performance(
        happy_birthday_package,
        presentations[NotationCondition.UPPER_LAYER],
        PracticeMode.SUPPORTED_PERFORMANCE,
    )
    lower = build_curriculum_layer_expected_performance(
        happy_birthday_package,
        presentations[NotationCondition.LOWER_LAYER],
        PracticeMode.SUPPORTED_PERFORMANCE,
    )
    combined = build_curriculum_combined_expected_performance(
        happy_birthday_package,
        requirements,
        presentations[NotationCondition.COMBINED],
        (
            presentations[NotationCondition.UPPER_LAYER],
            presentations[NotationCondition.LOWER_LAYER],
        ),
        PracticeMode.SUPPORTED_PERFORMANCE,
    )
    upper_attempt = _exact_attempt(upper, attempt_id="attempt:upper-success")
    lower_attempt = _exact_attempt(lower, attempt_id="attempt:lower-success")
    combined_attempt = _exact_attempt(combined, attempt_id="attempt:combined-success")

    assert all(
        item.status is ObservationStatus.MATCH
        for item in align_layer_attempt(upper, upper_attempt, _calibration())
        if item.dimension is ObservationDimension.PITCH
    )
    assert all(
        item.status is ObservationStatus.MATCH
        for item in align_layer_attempt(lower, lower_attempt, _calibration())
        if item.dimension is ObservationDimension.PITCH
    )
    for component_attempt in (upper_attempt, lower_attempt):
        with pytest.raises(AttemptAlignmentError, match="PERF_ALIGNMENT_EXERCISE"):
            align_layer_attempt(combined, component_attempt, _calibration())
    for component_expected in (upper, lower):
        with pytest.raises(AttemptAlignmentError, match="PERF_ALIGNMENT_EXERCISE"):
            align_layer_attempt(component_expected, combined_attempt, _calibration())


def test_combined_target_rejects_incomplete_component_union(
    happy_birthday_package: CanonicalMusicPackage,
) -> None:
    """TEST-CURR-ROBUSTNESS-017: incomplete combined topology fails closed."""

    requirements, presentations = _layer_fixture(happy_birthday_package)
    expected = build_curriculum_combined_expected_performance(
        happy_birthday_package,
        requirements,
        presentations[NotationCondition.COMBINED],
        (
            presentations[NotationCondition.UPPER_LAYER],
            presentations[NotationCondition.LOWER_LAYER],
        ),
        PracticeMode.SUPPORTED_PERFORMANCE,
    )
    assert expected.layer_target is not None
    first_component = expected.layer_target.components[0]
    incomplete_component = replace(
        first_component,
        active_event_ids=first_component.active_event_ids[1:],
    )
    provisional_target = replace(
        expected.layer_target,
        components=(incomplete_component, *expected.layer_target.components[1:]),
        semantic_fingerprint="",
    )
    tampered_target = replace(
        provisional_target,
        semantic_fingerprint=expected_layer_target_fingerprint(provisional_target),
    )
    tampered = replace(
        expected,
        exercise_id=f"curriculum-layer-attempt:{tampered_target.semantic_fingerprint}",
        layer_target=tampered_target,
    )

    with pytest.raises(AttemptAlignmentError, match="PERF_ALIGNMENT_COMPONENT_UNION"):
        align_layer_attempt(
            tampered,
            _exact_attempt(tampered, attempt_id="attempt:incomplete-union"),
            _calibration(),
        )


def test_combined_target_rejects_cross_component_note_membership(
    happy_birthday_package: CanonicalMusicPackage,
) -> None:
    """TEST-CURR-ROBUSTNESS-018: per-note component identity fails closed."""

    requirements, presentations = _layer_fixture(happy_birthday_package)
    expected = build_curriculum_combined_expected_performance(
        happy_birthday_package,
        requirements,
        presentations[NotationCondition.COMBINED],
        (
            presentations[NotationCondition.UPPER_LAYER],
            presentations[NotationCondition.LOWER_LAYER],
        ),
        PracticeMode.SUPPORTED_PERFORMANCE,
    )
    assert expected.layer_target is not None
    first_note = expected.notes[0]
    membership = first_note.layer_memberships[0]
    other_component = next(
        item
        for item in expected.layer_target.components
        if item.practice_scope_id != membership.component_scope_id
    )
    forged_membership = replace(
        membership,
        component_scope_id=other_component.practice_scope_id,
        component_scope_fingerprint=other_component.practice_scope_fingerprint,
        notation_condition=other_component.notation_condition,
    )
    forged_note = replace(first_note, layer_memberships=(forged_membership,))
    forged = replace(expected, notes=(forged_note, *expected.notes[1:]))

    with pytest.raises(AttemptAlignmentError, match="PERF_ALIGNMENT_MEMBERSHIP_MISMATCH"):
        align_layer_attempt(
            forged,
            _exact_attempt(forged, attempt_id="attempt:forged-membership"),
            _calibration(),
        )


def test_curriculum_evidence_is_support_aware_and_strictly_serializable(
    happy_birthday_package: CanonicalMusicPackage,
) -> None:
    """TEST-CURR-CONTRACT-007: evidence preserves exact support and wire identity."""

    requirements, presentations = _layer_fixture(happy_birthday_package)
    expected = build_curriculum_layer_expected_performance(
        happy_birthday_package,
        presentations[NotationCondition.UPPER_LAYER],
        PracticeMode.SUPPORTED_PERFORMANCE,
    )
    attempt = _exact_attempt(expected, attempt_id="attempt:evidence-upper")
    observations = align_layer_attempt(expected, attempt, _calibration())
    records = build_curriculum_evidence_records(
        requirements,
        expected,
        attempt,
        _support(),
        observations,
        EvidenceContext.ACQUISITION,
    )

    assert records
    assert all(item.result is CurriculumEvidenceResult.MATCHED for item in records)
    assert all(item.component_scope_refs == () for item in records)
    assert all(item.support_state_ref.id == attempt.support_state_id for item in records)
    payload = curriculum_evidence_record_to_json(records[0])
    assert curriculum_evidence_record_from_json(payload) == records[0]
    assert curriculum_evidence_record_to_json(records[0]) == payload


def test_component_and_combined_results_preserve_exact_evidence_context(
    happy_birthday_package: CanonicalMusicPackage,
) -> None:
    """TEST-CURR-VALIDATION-021: factual records retain isolated topology."""

    requirements, presentations = _layer_fixture(happy_birthday_package)
    combined = build_curriculum_combined_expected_performance(
        happy_birthday_package,
        requirements,
        presentations[NotationCondition.COMBINED],
        (
            presentations[NotationCondition.UPPER_LAYER],
            presentations[NotationCondition.LOWER_LAYER],
        ),
        PracticeMode.SUPPORTED_PERFORMANCE,
    )
    attempt = _exact_attempt(combined, attempt_id="attempt:evidence-combined")
    observations = align_layer_attempt(combined, attempt, _calibration())
    records = build_curriculum_evidence_records(
        requirements,
        combined,
        attempt,
        _support(),
        observations,
        EvidenceContext.INTEGRATION,
    )

    assert records
    assert all(item.notation_condition is NotationCondition.COMBINED for item in records)
    assert all(len(item.component_scope_refs) == 2 for item in records)
    assert all(item.evidence_context is EvidenceContext.INTEGRATION for item in records)
    assert all(item.result is CurriculumEvidenceResult.MATCHED for item in records)
    assert all(item.context_observation_ids for item in records)


def test_curriculum_evidence_rejects_support_or_context_reuse(
    happy_birthday_package: CanonicalMusicPackage,
) -> None:
    """TEST-CURR-ROBUSTNESS-019: support and context changes fail closed."""

    requirements, presentations = _layer_fixture(happy_birthday_package)
    expected = build_curriculum_layer_expected_performance(
        happy_birthday_package,
        presentations[NotationCondition.UPPER_LAYER],
        PracticeMode.SUPPORTED_PERFORMANCE,
    )
    attempt = _exact_attempt(expected, attempt_id="attempt:evidence-support")
    observations = align_layer_attempt(expected, attempt, _calibration())
    support = _support()
    records = build_curriculum_evidence_records(
        requirements,
        expected,
        attempt,
        support,
        observations,
        EvidenceContext.ACQUISITION,
    )
    require_compatible_curriculum_evidence(
        records,
        requirements,
        expected,
        attempt,
        support,
        observations,
        EvidenceContext.ACQUISITION,
    )

    with pytest.raises(CurriculumEvidenceError, match="TMM-EVIDENCE-INCOMPATIBLE"):
        require_compatible_curriculum_evidence(
            records,
            requirements,
            expected,
            attempt,
            _support(tempo_percent=50),
            observations,
            EvidenceContext.ACQUISITION,
        )
    with pytest.raises(CurriculumEvidenceError, match="TMM-EVIDENCE-CONTEXT-MISMATCH"):
        build_curriculum_evidence_records(
            requirements,
            expected,
            attempt,
            support,
            observations,
            EvidenceContext.INDEPENDENT,
        )


def test_component_evidence_cannot_backfill_combined_evidence(
    happy_birthday_package: CanonicalMusicPackage,
) -> None:
    """TEST-CURR-ROBUSTNESS-020: component records cannot satisfy integration."""

    requirements, presentations = _layer_fixture(happy_birthday_package)
    upper = build_curriculum_layer_expected_performance(
        happy_birthday_package,
        presentations[NotationCondition.UPPER_LAYER],
        PracticeMode.SUPPORTED_PERFORMANCE,
    )
    upper_attempt = _exact_attempt(upper, attempt_id="attempt:evidence-upper-isolated")
    upper_observations = align_layer_attempt(upper, upper_attempt, _calibration())
    isolated = build_curriculum_evidence_records(
        requirements,
        upper,
        upper_attempt,
        _support(),
        upper_observations,
        EvidenceContext.ACQUISITION,
    )
    combined = build_curriculum_combined_expected_performance(
        happy_birthday_package,
        requirements,
        presentations[NotationCondition.COMBINED],
        (
            presentations[NotationCondition.UPPER_LAYER],
            presentations[NotationCondition.LOWER_LAYER],
        ),
        PracticeMode.SUPPORTED_PERFORMANCE,
    )
    combined_attempt = _exact_attempt(combined, attempt_id="attempt:evidence-integration")
    combined_observations = align_layer_attempt(combined, combined_attempt, _calibration())

    with pytest.raises(CurriculumEvidenceError, match="TMM-EVIDENCE-INCOMPATIBLE"):
        require_compatible_curriculum_evidence(
            isolated,
            requirements,
            combined,
            combined_attempt,
            _support(),
            combined_observations,
            EvidenceContext.INTEGRATION,
        )


def test_curriculum_evidence_reports_facts_without_mastery_inference(
    happy_birthday_package: CanonicalMusicPackage,
) -> None:
    """TEST-CURR-VALIDATION-022: discrepancy and uncertainty stay factual."""

    requirements, presentations = _layer_fixture(happy_birthday_package)
    expected = build_curriculum_layer_expected_performance(
        happy_birthday_package,
        presentations[NotationCondition.UPPER_LAYER],
        PracticeMode.SUPPORTED_PERFORMANCE,
    )
    attempt = _exact_attempt(expected, attempt_id="attempt:evidence-factual")
    observations = align_layer_attempt(expected, attempt, _calibration())
    pitch_index = next(
        index
        for index, item in enumerate(observations)
        if item.dimension is ObservationDimension.PITCH
    )
    discrepancy_observations = list(observations)
    discrepancy_observations[pitch_index] = replace(
        observations[pitch_index],
        status=ObservationStatus.DISCREPANCY,
    )
    discrepancy = build_curriculum_evidence_records(
        requirements,
        expected,
        attempt,
        _support(),
        tuple(discrepancy_observations),
        EvidenceContext.ACQUISITION,
    )
    assert any(
        item.dimension is ObservationDimension.PITCH
        and item.result is CurriculumEvidenceResult.DISCREPANCY
        for item in discrepancy
    )

    uncertain_observations = list(observations)
    uncertain_observations[pitch_index] = replace(
        observations[pitch_index],
        status=ObservationStatus.AMBIGUOUS,
        limitations=("Pitch identity could not be resolved.",),
    )
    inconclusive = build_curriculum_evidence_records(
        requirements,
        expected,
        attempt,
        _support(),
        tuple(uncertain_observations),
        EvidenceContext.ACQUISITION,
    )
    assert any(
        item.dimension is ObservationDimension.PITCH
        and item.result is CurriculumEvidenceResult.INCONCLUSIVE
        and item.limitations == ("Pitch identity could not be resolved.",)
        for item in inconclusive
    )


def test_exact_independent_mastery_unlocks_only_the_declared_successor(
    happy_birthday_package: CanonicalMusicPackage,
) -> None:
    """TEST-CURR-CONTRACT-008 / TEST-CURR-POLICY-004: strict artifacts select one edge."""

    requirements, presentations = _layer_fixture(happy_birthday_package)
    graph = _acquisition_graph(requirements)
    upper_stage = next(
        item
        for item in graph.stages
        if item.kind is AcquisitionStageKind.COMPONENT_ACQUISITION
        and item.practice_scope_ref.id
        == presentations[NotationCondition.UPPER_LAYER].practice_scope_ref.id
    )
    upper_node = next(item for item in graph.nodes if item.id == upper_stage.node_id)
    expected = build_curriculum_layer_expected_performance(
        happy_birthday_package,
        presentations[NotationCondition.UPPER_LAYER],
        PracticeMode.INDEPENDENT_PERFORMANCE,
    )
    records = _records_for_target(
        requirements,
        expected,
        attempt_id="attempt:unlock-upper",
        evidence_context=EvidenceContext.INDEPENDENT,
        requirement_id=upper_node.requirement_ref.id,
    )
    declared_successor = next(
        item
        for item in graph.edges
        if item.source_node_id == upper_node.id and item.kind.value == "on-satisfied"
    )
    successor_node = next(
        item for item in graph.nodes if item.id == declared_successor.target_node_id
    )

    projection, decision = decide_curriculum_unlock(
        graph,
        upper_node.id,
        _support(),
        records,
        previously_satisfied_node_ids=tuple(
            dict.fromkeys((*upper_node.component_node_ids, *successor_node.component_node_ids))
        ),
    )

    assert projection.status is CurriculumMasteryStatus.MASTERED
    assert projection.evidence_context is EvidenceContext.INDEPENDENT
    assert decision.action is CurriculumUnlockAction.UNLOCK_SUCCESSOR
    assert decision.selected_edge_id in decision.eligible_edge_ids
    selected = next(item for item in graph.edges if item.id == decision.selected_edge_id)
    assert selected.source_node_id == upper_node.id
    assert selected.target_node_id == decision.next_node_id

    projection_payload = curriculum_mastery_projection_to_json(projection)
    decision_payload = curriculum_unlock_decision_to_json(decision)
    assert curriculum_mastery_projection_from_json(projection_payload) == projection
    assert curriculum_unlock_decision_from_json(decision_payload) == decision


def test_component_completion_gates_but_cannot_certify_combined_mastery(
    happy_birthday_package: CanonicalMusicPackage,
) -> None:
    """TEST-CURR-VALIDATION-023: components gate, never backfill, integration."""

    requirements, presentations = _layer_fixture(happy_birthday_package)
    graph = _acquisition_graph(requirements)
    component_stages = tuple(
        item for item in graph.stages if item.kind is AcquisitionStageKind.COMPONENT_ACQUISITION
    )
    upper_stage, lower_stage = component_stages
    lower_node = next(item for item in graph.nodes if item.id == lower_stage.node_id)
    lower_expected = build_curriculum_layer_expected_performance(
        happy_birthday_package,
        presentations[NotationCondition.LOWER_LAYER],
        PracticeMode.INDEPENDENT_PERFORMANCE,
    )
    lower_records = _records_for_target(
        requirements,
        lower_expected,
        attempt_id="attempt:unlock-lower",
        evidence_context=EvidenceContext.INDEPENDENT,
        requirement_id=lower_node.requirement_ref.id,
    )
    _, lower_without_upper = decide_curriculum_unlock(
        graph,
        lower_node.id,
        _support(),
        lower_records,
        previously_satisfied_node_ids=lower_node.component_node_ids,
    )
    _, lower_with_upper = decide_curriculum_unlock(
        graph,
        lower_node.id,
        _support(),
        lower_records,
        previously_satisfied_node_ids=(
            *lower_node.component_node_ids,
            upper_stage.node_id,
        ),
    )

    coordination = next(
        item for item in graph.stages if item.kind is AcquisitionStageKind.SELF_PACED_COORDINATION
    )
    coordination_node = next(item for item in graph.nodes if item.id == coordination.node_id)
    assert lower_without_upper.action is CurriculumUnlockAction.COMPLETE_NODE
    assert lower_without_upper.next_node_id is None
    assert any(
        item.reason_code == "TMM-POLICY-COMPONENTS-INCOMPLETE"
        for item in lower_without_upper.rejected_edges
    )
    assert lower_with_upper.next_node_id == coordination.node_id

    upper_node = next(item for item in graph.nodes if item.id == upper_stage.node_id)
    upper_expected = build_curriculum_layer_expected_performance(
        happy_birthday_package,
        presentations[NotationCondition.UPPER_LAYER],
        PracticeMode.INDEPENDENT_PERFORMANCE,
    )
    upper_records = _records_for_target(
        requirements,
        upper_expected,
        attempt_id="attempt:component-cannot-integrate",
        evidence_context=EvidenceContext.INDEPENDENT,
        requirement_id=upper_node.requirement_ref.id,
    )
    with pytest.raises(CurriculumPolicyError, match="TMM-POLICY-EVIDENCE-INCOMPATIBLE"):
        decide_curriculum_unlock(
            graph,
            coordination_node.id,
            _support(),
            upper_records,
            previously_satisfied_node_ids=(upper_stage.node_id, lower_stage.node_id),
        )

    combined_expected = build_curriculum_combined_expected_performance(
        happy_birthday_package,
        requirements,
        presentations[NotationCondition.COMBINED],
        (
            presentations[NotationCondition.UPPER_LAYER],
            presentations[NotationCondition.LOWER_LAYER],
        ),
        PracticeMode.SUPPORTED_PERFORMANCE,
    )
    combined_records = _records_for_target(
        requirements,
        combined_expected,
        attempt_id="attempt:exact-integration",
        evidence_context=EvidenceContext.INTEGRATION,
        requirement_id=coordination_node.requirement_ref.id,
    )
    projection, decision = decide_curriculum_unlock(
        graph,
        coordination_node.id,
        _support(),
        combined_records,
        previously_satisfied_node_ids=(upper_stage.node_id, lower_stage.node_id),
    )
    assert projection.status is CurriculumMasteryStatus.MASTERED
    assert len(projection.component_scope_refs) == 2
    assert decision.action is CurriculumUnlockAction.UNLOCK_SUCCESSOR


def test_support_context_and_attempt_completeness_do_not_collapse(
    happy_birthday_package: CanonicalMusicPackage,
) -> None:
    """TEST-CURR-ROBUSTNESS-021: evidence cannot cross support or context."""

    requirements, presentations = _layer_fixture(happy_birthday_package)
    graph = _acquisition_graph(requirements)
    upper_stage = next(
        item
        for item in graph.stages
        if item.kind is AcquisitionStageKind.COMPONENT_ACQUISITION
        and item.practice_scope_ref.id
        == presentations[NotationCondition.UPPER_LAYER].practice_scope_ref.id
    )
    node = next(item for item in graph.nodes if item.id == upper_stage.node_id)
    independent = build_curriculum_layer_expected_performance(
        happy_birthday_package,
        presentations[NotationCondition.UPPER_LAYER],
        PracticeMode.INDEPENDENT_PERFORMANCE,
    )
    first = _records_for_target(
        requirements,
        independent,
        attempt_id="attempt:complete-a",
        evidence_context=EvidenceContext.INDEPENDENT,
        requirement_id=node.requirement_ref.id,
    )
    second = _records_for_target(
        requirements,
        independent,
        attempt_id="attempt:complete-b",
        evidence_context=EvidenceContext.INDEPENDENT,
        requirement_id=node.requirement_ref.id,
    )
    split = (first[0], *second[1:])
    projection, decision = decide_curriculum_unlock(
        graph,
        node.id,
        _support(),
        split,
        previously_satisfied_node_ids=node.component_node_ids,
    )
    assert projection.status is CurriculumMasteryStatus.INCONCLUSIVE
    assert projection.complete_passing_attempt_ids == ()
    assert decision.action is CurriculumUnlockAction.HOLD_FOR_EVIDENCE

    with pytest.raises(CurriculumPolicyError, match="TMM-POLICY-EVIDENCE-INCOMPATIBLE"):
        decide_curriculum_unlock(
            graph,
            node.id,
            _support(tempo_percent=50),
            first,
        )

    supported = build_curriculum_layer_expected_performance(
        happy_birthday_package,
        presentations[NotationCondition.UPPER_LAYER],
        PracticeMode.SUPPORTED_PERFORMANCE,
    )
    acquisition_records = _records_for_target(
        requirements,
        supported,
        attempt_id="attempt:acquisition-not-independent",
        evidence_context=EvidenceContext.ACQUISITION,
        requirement_id=node.requirement_ref.id,
    )
    with pytest.raises(CurriculumPolicyError, match="TMM-POLICY-EVIDENCE-INCOMPATIBLE"):
        decide_curriculum_unlock(graph, node.id, _support(), acquisition_records)


def test_retention_and_transfer_remain_separate_authoritative_claims(
    hot_cross_buns_package: CanonicalMusicPackage,
    happy_birthday_package: CanonicalMusicPackage,
) -> None:
    """TEST-CURR-ROBUSTNESS-022: lasting-skill contexts cannot backfill."""

    source = derive_passage_requirements(
        hot_cross_buns_package,
        analyze_canonical_score(hot_cross_buns_package, end_measure_ordinal=2),
    )
    target, target_presentations = _layer_fixture(happy_birthday_package)
    acquisition = _acquisition_graph(source)
    graph = generate_lasting_skill_graph(
        source,
        acquisition,
        target,
        transfer_requests=_transfer_requests(source, target),
    )
    node_by_id = {item.id: item for item in graph.nodes}

    retention_stage = next(
        item for item in graph.stages if item.kind is LastingSkillStageKind.RETENTION
    )
    retention_node = node_by_id[retention_stage.node_id]
    source_scope = next(
        item for item in source.scopes if item.id == retention_stage.practice_scope_ref.id
    )
    source_presentation = build_curriculum_passage_presentation(
        hot_cross_buns_package,
        source,
        source_scope.id,
    )
    retention_expected = build_curriculum_layer_expected_performance(
        hot_cross_buns_package,
        source_presentation,
        PracticeMode.RETENTION,
    )
    retention_records = _records_for_target(
        source,
        retention_expected,
        attempt_id="attempt:retention-exact",
        evidence_context=EvidenceContext.RETENTION,
        requirement_id=retention_node.requirement_ref.id,
    )
    retention_projection, retention_decision = decide_curriculum_unlock(
        graph,
        retention_node.id,
        _support(),
        retention_records,
    )
    assert retention_projection.status is CurriculumMasteryStatus.MASTERED
    assert retention_projection.evidence_context is EvidenceContext.RETENTION
    assert retention_decision.action in {
        CurriculumUnlockAction.UNLOCK_SUCCESSOR,
        CurriculumUnlockAction.COMPLETE_NODE,
    }

    transfer_stage = next(
        item for item in graph.stages if item.kind is LastingSkillStageKind.TRANSFER
    )
    transfer_node = node_by_id[transfer_stage.node_id]
    transfer_scope = next(
        item for item in target.scopes if item.id == transfer_stage.practice_scope_ref.id
    )
    transfer_expected = build_curriculum_layer_expected_performance(
        happy_birthday_package,
        target_presentations[transfer_scope.notation_condition],
        PracticeMode.TRANSFER,
    )
    transfer_records = _records_for_target(
        target,
        transfer_expected,
        attempt_id="attempt:transfer-exact",
        evidence_context=EvidenceContext.TRANSFER,
        requirement_id=transfer_node.requirement_ref.id,
    )
    transfer_projection, _ = decide_curriculum_unlock(
        graph,
        transfer_node.id,
        _support(),
        transfer_records,
    )
    assert transfer_projection.status is CurriculumMasteryStatus.MASTERED
    assert transfer_projection.evidence_context is EvidenceContext.TRANSFER

    with pytest.raises(CurriculumPolicyError, match="TMM-POLICY-EVIDENCE-INCOMPATIBLE"):
        decide_curriculum_unlock(
            graph,
            transfer_node.id,
            _support(),
            retention_records,
        )


def test_supported_acquisition_requires_two_complete_passes_and_retries_discrepancy(
    happy_birthday_package: CanonicalMusicPackage,
) -> None:
    """TEST-CURR-POLICY-005: supported stability is complete and non-averaged."""

    requirements, presentations = _layer_fixture(happy_birthday_package)
    graph = _acquisition_graph(requirements)
    upper_stage = next(
        item
        for item in graph.stages
        if item.kind is AcquisitionStageKind.COMPONENT_ACQUISITION
        and item.practice_scope_ref.id
        == presentations[NotationCondition.UPPER_LAYER].practice_scope_ref.id
    )
    application_node = next(item for item in graph.nodes if item.id == upper_stage.node_id)
    branch = next(
        item
        for item in graph.branches
        if item.requirement_ref.id == application_node.requirement_ref.id
    )
    prerequisite_node = next(item for item in graph.nodes if item.id == branch.prerequisite_node_id)
    expected = build_curriculum_layer_expected_performance(
        happy_birthday_package,
        presentations[NotationCondition.UPPER_LAYER],
        PracticeMode.SUPPORTED_PERFORMANCE,
    )
    first = _records_for_target(
        requirements,
        expected,
        attempt_id="attempt:supported-first",
        evidence_context=EvidenceContext.ACQUISITION,
        requirement_id=prerequisite_node.requirement_ref.id,
    )
    second = _records_for_target(
        requirements,
        expected,
        attempt_id="attempt:supported-second",
        evidence_context=EvidenceContext.ACQUISITION,
        requirement_id=prerequisite_node.requirement_ref.id,
    )
    with pytest.raises(
        CurriculumPolicyError,
        match="TMM-POLICY-ATTEMPT-SEQUENCE-REQUIRED",
    ):
        decide_curriculum_unlock(
            graph,
            prerequisite_node.id,
            _support(),
            first,
        )
    one_projection, one_decision = decide_curriculum_unlock(
        graph,
        prerequisite_node.id,
        _support(),
        first,
        attempt_sequence=("attempt:supported-first",),
    )
    assert one_projection.status is CurriculumMasteryStatus.INCONCLUSIVE
    assert one_decision.action is CurriculumUnlockAction.HOLD_FOR_EVIDENCE

    stable_projection, stable_decision = decide_curriculum_unlock(
        graph,
        prerequisite_node.id,
        _support(),
        (*first, *second),
        attempt_sequence=("attempt:supported-first", "attempt:supported-second"),
        previously_satisfied_node_ids=application_node.component_node_ids,
    )
    assert stable_projection.status is CurriculumMasteryStatus.MASTERED
    assert stable_projection.complete_passing_attempt_ids == (
        "attempt:supported-first",
        "attempt:supported-second",
    )
    assert stable_decision.next_node_id == application_node.id
    with pytest.raises(
        CurriculumPolicyError,
        match="TMM-POLICY-ATTEMPT-SEQUENCE-INCOMPATIBLE",
    ):
        decide_curriculum_unlock(
            graph,
            prerequisite_node.id,
            _support(),
            (*first, *second),
            attempt_sequence=("attempt:supported-second",),
        )

    discrepancy_attempt = _exact_attempt(
        expected,
        attempt_id="attempt:supported-discrepancy",
    )
    observations = list(align_layer_attempt(expected, discrepancy_attempt, _calibration()))
    pitch_index = next(
        index
        for index, item in enumerate(observations)
        if item.dimension is ObservationDimension.PITCH
    )
    observations[pitch_index] = replace(
        observations[pitch_index],
        status=ObservationStatus.DISCREPANCY,
    )
    discrepancy_records = tuple(
        item
        for item in build_curriculum_evidence_records(
            requirements,
            expected,
            discrepancy_attempt,
            _support(),
            tuple(observations),
            EvidenceContext.ACQUISITION,
        )
        if item.requirement_ref.id == prerequisite_node.requirement_ref.id
    )
    discrepancy_projection, discrepancy_decision = decide_curriculum_unlock(
        graph,
        prerequisite_node.id,
        _support(),
        discrepancy_records,
        attempt_sequence=("attempt:supported-discrepancy",),
    )
    assert discrepancy_projection.status is CurriculumMasteryStatus.NOT_MASTERED
    assert discrepancy_decision.action is CurriculumUnlockAction.RETRY_CURRENT

    interrupted_projection, interrupted_decision = decide_curriculum_unlock(
        graph,
        prerequisite_node.id,
        _support(),
        (*first, *second, *discrepancy_records),
        attempt_sequence=(
            "attempt:supported-first",
            "attempt:supported-second",
            "attempt:supported-discrepancy",
        ),
    )
    assert interrupted_projection.status is CurriculumMasteryStatus.NOT_MASTERED
    assert interrupted_decision.action is CurriculumUnlockAction.RETRY_CURRENT
