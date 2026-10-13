"""Executable DEV-009 Task 9G.3 playable-prerequisite evidence."""

from __future__ import annotations

from dataclasses import replace

import pytest

from teachmemusic.analysis import analyze_canonical_score
from teachmemusic.performance import (
    AttemptCompletion,
    CalibrationProfile,
    LearnerAttempt,
    MidiEventKind,
    NormalizedMidiEvent,
    ObservationDimension,
    ObservationStatus,
    align_layer_attempt,
)
from teachmemusic.score import CanonicalMusicPackage
from teachmemusic.teaching import (
    ArtifactResolution,
    CurriculumFundamentalPracticeError,
    CurriculumSerializationError,
    NotationCondition,
    build_curriculum_fundamental_demonstration,
    build_curriculum_fundamental_explanation,
    build_curriculum_fundamental_practice,
    build_curriculum_passage_presentation,
    curriculum_fundamental_practice_from_json,
    curriculum_fundamental_practice_to_json,
    derive_passage_requirements,
    generate_prerequisite_branches,
    validate_curriculum_fundamental_practice,
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
    demonstration = build_curriculum_fundamental_demonstration(
        package,
        requirements,
        branches,
        presentation,
        explanation,
    ).binding
    return requirements, branches, presentation, explanation, demonstration


def _calibration() -> CalibrationProfile:
    return CalibrationProfile(
        id="calibration:fundamental-practice",
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
        approved_at_utc="2026-10-12T12:00:00Z",
    )


def _exact_attempt(expected) -> LearnerAttempt:
    start = 1_000_000
    events: list[NormalizedMidiEvent] = []
    for index, note in enumerate(expected.notes):
        events.extend(
            (
                NormalizedMidiEvent(
                    id=f"midi-event:practice-{index:04d}-on",
                    raw_message_id=None,
                    kind=MidiEventKind.NOTE_ON,
                    timestamp_microseconds=start + note.start_microseconds,
                    channel=1,
                    note=note.midi_pitch,
                    velocity=80,
                ),
                NormalizedMidiEvent(
                    id=f"midi-event:practice-{index:04d}-off",
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
        id="attempt:fundamental-practice",
        run_id="run:fundamental-practice",
        exercise_id=expected.exercise_id,
        calibration_id="calibration:fundamental-practice",
        practice_mode=expected.practice_mode,
        support_state_id="support:guided",
        started_at_utc="2026-10-12T12:01:00Z",
        start_microseconds=start,
        end_microseconds=ordered[-1].timestamp_microseconds + 1_000,
        completion=AttemptCompletion.COMPLETED,
        normalized_events=ordered,
    )


def test_fundamental_practice_is_deterministic_strict_and_playable(
    hot_cross_buns_package: CanonicalMusicPackage,
) -> None:
    """TEST-CURR-CONTRACT-011: exact perform target round-trips and aligns."""

    inputs = _resolved_fundamental(
        hot_cross_buns_package,
        primitive_id="PRIM-KEY-001",
    )
    first = build_curriculum_fundamental_practice(
        hot_cross_buns_package,
        *inputs,
        tempo_bpm=72,
    )
    second = build_curriculum_fundamental_practice(
        hot_cross_buns_package,
        *inputs,
        tempo_bpm=72,
    )
    payload = curriculum_fundamental_practice_to_json(first.binding)
    observations = align_layer_attempt(
        first.expected, _exact_attempt(first.expected), _calibration()
    )

    assert first == second
    assert first.binding.performance_activity_id != inputs[-1].demonstration_activity_id
    assert first.binding.support_envelope.initial_condition == "guided"
    assert first.binding.required_evidence_exits
    assert first.binding.expected_active_event_ids == inputs[2].active_target_ids
    assert all(
        item.status is ObservationStatus.MATCH
        for item in observations
        if item.dimension
        in {
            ObservationDimension.PITCH,
            ObservationDimension.ORDER,
            ObservationDimension.ONSET,
            ObservationDimension.DURATION,
            ObservationDimension.CONTINUITY,
        }
    )
    assert '"type": "curriculum-fundamental-practice"' in payload
    assert curriculum_fundamental_practice_from_json(payload) == first.binding
    with pytest.raises(CurriculumSerializationError, match="unexpected"):
        curriculum_fundamental_practice_from_json(
            payload.replace('"tempo_bpm"', '"unexpected": true, "tempo_bpm"')
        )


def test_layered_practice_preserves_active_material_support_and_evidence_exits(
    happy_birthday_package: CanonicalMusicPackage,
) -> None:
    """TEST-CURR-VALIDATION-026: one written layer has one attempt envelope."""

    inputs = _resolved_fundamental(
        happy_birthday_package,
        primitive_id="PRIM-HAR-001",
        notation_condition=NotationCondition.LOWER_LAYER,
    )
    projection = build_curriculum_fundamental_practice(
        happy_birthday_package,
        *inputs,
    )
    binding = projection.binding

    assert binding.expected_active_event_ids == inputs[2].active_target_ids
    assert set(binding.expected_active_event_ids).isdisjoint(inputs[2].inactive_context_ids)
    assert binding.support_envelope.permitted_conditions == (
        "guided",
        "reduced-support",
        "independent",
    )
    assert {item.dimension for item in binding.required_evidence_exits}
    assert {item.evidence_context for item in binding.required_evidence_exits} == {"acquisition"}
    assert {item.dimension for item in binding.required_evidence_exits} <= {
        item.value for item in binding.target_dimensions
    }
    assert (
        validate_curriculum_fundamental_practice(
            binding,
            inputs[3],
            inputs[4],
            inputs[0],
            inputs[1],
            inputs[2],
            projection.expected,
        )
        == ()
    )


def test_practice_rejects_activity_support_target_and_expected_drift(
    hot_cross_buns_package: CanonicalMusicPackage,
) -> None:
    """TEST-CURR-ROBUSTNESS-028: attempt-authority drift fails closed."""

    inputs = _resolved_fundamental(
        hot_cross_buns_package,
        primitive_id="PRIM-KEY-001",
    )
    projection = build_curriculum_fundamental_practice(hot_cross_buns_package, *inputs)
    changed = replace(
        projection.binding,
        performance_activity_id=inputs[-1].demonstration_activity_id,
        expected_active_event_ids=projection.binding.expected_active_event_ids[1:],
        expected_performance_sha256="0" * 64,
    )
    codes = {
        item.code
        for item in validate_curriculum_fundamental_practice(
            changed,
            inputs[3],
            inputs[4],
            inputs[0],
            inputs[1],
            inputs[2],
            projection.expected,
        )
    }

    assert "TMM-PRACTICE-DEMONSTRATION-MISMATCH" in codes
    assert "TMM-PRACTICE-PRESENTATION-MISMATCH" in codes
    assert "TMM-PRACTICE-ACTIVITY-MISMATCH" in codes
    assert "TMM-PRACTICE-EXPECTED-MISMATCH" in codes
    assert "TMM-CONTRACT-FINGERPRINT-MISMATCH" in codes


def test_unresolved_complex_topology_cannot_emit_playable_practice(
    moonlight_package: CanonicalMusicPackage,
    hot_cross_buns_package: CanonicalMusicPackage,
) -> None:
    """TEST-CURR-ROBUSTNESS-029: unresolved pedagogy has no learner attempt."""

    requirements = derive_passage_requirements(
        moonlight_package,
        analyze_canonical_score(moonlight_package, end_measure_ordinal=69),
    )
    branches = generate_prerequisite_branches(requirements)
    resolved = _resolved_fundamental(
        hot_cross_buns_package,
        primitive_id="PRIM-KEY-001",
    )

    assert branches.resolution is ArtifactResolution.REVIEW_REQUIRED
    with pytest.raises(
        CurriculumFundamentalPracticeError,
        match="TMM-PRACTICE-BRANCH-UNRESOLVED",
    ):
        build_curriculum_fundamental_practice(
            hot_cross_buns_package,
            requirements,
            branches,
            *resolved[2:],
        )
