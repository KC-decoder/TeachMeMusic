"""Executable DEV-009 Task 9G.4 exact return-to-piece evidence."""

from __future__ import annotations

from dataclasses import replace
from fractions import Fraction

import pytest

from teachmemusic.analysis import analyze_canonical_score
from teachmemusic.performance import (
    AttemptCompletion,
    CalibrationProfile,
    LearnerAttempt,
    MidiEventKind,
    NormalizedMidiEvent,
    align_layer_attempt,
)
from teachmemusic.score import CanonicalMusicPackage
from teachmemusic.teaching import (
    CompatibleTempoEvidence,
    CurriculumPieceReturnError,
    CurriculumSerializationError,
    EvidenceContext,
    SemanticReference,
    SupportState,
    TempoReferenceAuthority,
    build_curriculum_evidence_records,
    build_curriculum_fundamental_demonstration,
    build_curriculum_fundamental_explanation,
    build_curriculum_fundamental_practice,
    build_curriculum_passage_presentation,
    build_curriculum_piece_return,
    curriculum_piece_return_from_json,
    curriculum_piece_return_to_json,
    decide_curriculum_unlock,
    derive_passage_requirements,
    generate_acquisition_graph,
    generate_prerequisite_branches,
    validate_curriculum_piece_return,
)


def _calibration() -> CalibrationProfile:
    return CalibrationProfile(
        id="calibration:fundamental-return",
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
        approved_at_utc="2026-10-12T15:00:00Z",
    )


def _support() -> SupportState:
    return SupportState(
        id="support:guided",
        notation_visible=True,
        cursor_visible=True,
        note_names_visible=True,
        keyboard_highlighting=True,
        fingering_visible=False,
        demonstration_available=True,
        follow_mode=True,
        metronome=False,
        tempo_percent=60,
        isolated_layers=("written-layer",),
        isolated_dimensions=("pitch", "order"),
    )


def _exact_attempt(expected, attempt_id: str) -> LearnerAttempt:
    start = 1_000_000
    events: list[NormalizedMidiEvent] = []
    for index, note in enumerate(expected.notes):
        events.extend(
            (
                NormalizedMidiEvent(
                    id=f"midi-event:return-{attempt_id[-1]}-{index:04d}-on",
                    raw_message_id=None,
                    kind=MidiEventKind.NOTE_ON,
                    timestamp_microseconds=start + note.start_microseconds,
                    channel=1,
                    note=note.midi_pitch,
                    velocity=80,
                ),
                NormalizedMidiEvent(
                    id=f"midi-event:return-{attempt_id[-1]}-{index:04d}-off",
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
        run_id="run:fundamental-return",
        exercise_id=expected.exercise_id,
        calibration_id="calibration:fundamental-return",
        practice_mode=expected.practice_mode,
        support_state_id="support:guided",
        started_at_utc="2026-10-12T15:01:00Z",
        start_microseconds=start,
        end_microseconds=ordered[-1].timestamp_microseconds + 1_000,
        completion=AttemptCompletion.COMPLETED,
        normalized_events=ordered,
    )


def _return_fixture(package: CanonicalMusicPackage):
    requirements = derive_passage_requirements(
        package,
        analyze_canonical_score(package, end_measure_ordinal=2),
    )
    branches = generate_prerequisite_branches(requirements)
    scope = requirements.scopes[0]
    presentation = build_curriculum_passage_presentation(package, requirements, scope.id)
    requirement = next(
        item
        for item in requirements.requirements
        if item.practice_scope_ref.id == scope.id and item.primitive_ref.id == "PRIM-KEY-001"
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
    practice_projection = build_curriculum_fundamental_practice(
        package,
        requirements,
        branches,
        presentation,
        explanation,
        demonstration,
    )
    graph = generate_acquisition_graph(
        requirements,
        branches,
        reference_tempo_bpm=Fraction(100),
        reference_authority=TempoReferenceAuthority.CALLER,
        tempo_evidence=(
            CompatibleTempoEvidence(
                SemanticReference(
                    "practice-scope-assignment",
                    scope.id,
                    scope.semantic_fingerprint,
                ),
                "independent-piece",
                60,
                60,
                True,
                True,
                ("evidence:controlled-tempo",),
            ),
        ),
    )
    records = []
    observations = []
    attempt_ids = ("attempt:fundamental-return-1", "attempt:fundamental-return-2")
    for attempt_id in attempt_ids:
        attempt = _exact_attempt(practice_projection.expected, attempt_id)
        attempt_observations = align_layer_attempt(
            practice_projection.expected,
            attempt,
            _calibration(),
        )
        observations.extend(attempt_observations)
        records.extend(
            item
            for item in build_curriculum_evidence_records(
                requirements,
                practice_projection.expected,
                attempt,
                _support(),
                attempt_observations,
                EvidenceContext.ACQUISITION,
            )
            if item.requirement_ref.id == requirement.id
        )
    mastery, decision = decide_curriculum_unlock(
        graph,
        explanation.prerequisite_node_id,
        _support(),
        tuple(records),
        attempt_sequence=attempt_ids,
    )
    result = build_curriculum_piece_return(
        requirements,
        branches,
        graph,
        presentation,
        explanation,
        demonstration,
        practice_projection.binding,
        mastery,
        decision,
    )
    return (
        requirements,
        branches,
        graph,
        presentation,
        explanation,
        demonstration,
        practice_projection,
        mastery,
        decision,
        tuple(records),
        tuple(observations),
        result,
    )


def test_piece_return_is_deterministic_strict_and_evidence_preserving(
    hot_cross_buns_package: CanonicalMusicPackage,
) -> None:
    """TEST-CURR-CONTRACT-012: one exact policy-authorized return round-trips."""

    fixture = _return_fixture(hot_cross_buns_package)
    result = fixture[-1]
    payload = curriculum_piece_return_to_json(result)

    assert result.return_node_id == fixture[4].return_node_id
    assert result.application_exercise_ref == fixture[4].application_exercise_ref
    assert result.completed_attempt_ids == fixture[7].complete_passing_attempt_ids
    assert result.evidence_record_ids == tuple(
        dict.fromkeys(
            identifier
            for item in fixture[7].dimension_decisions
            for identifier in item.evidence_record_ids
        )
    )
    assert result.active_event_ids == fixture[3].active_target_ids
    assert '"type": "curriculum-piece-return"' in payload
    assert curriculum_piece_return_from_json(payload) == result
    with pytest.raises(CurriculumSerializationError, match="unexpected"):
        curriculum_piece_return_from_json(
            payload.replace('"score_id"', '"unexpected": true, "score_id"')
        )


def test_piece_return_rejects_route_passage_and_evidence_drift(
    hot_cross_buns_package: CanonicalMusicPackage,
) -> None:
    """TEST-CURR-ROBUSTNESS-030: a detached or altered return fails closed."""

    fixture = _return_fixture(hot_cross_buns_package)
    changed = replace(
        fixture[-1],
        return_node_id=fixture[4].prerequisite_node_id,
        active_event_ids=fixture[3].active_target_ids[1:],
        evidence_record_ids=fixture[-1].evidence_record_ids[1:],
    )
    codes = {
        item.code
        for item in validate_curriculum_piece_return(
            changed,
            fixture[6].binding,
            fixture[7],
            fixture[8],
            fixture[1],
            fixture[2],
            fixture[3],
        )
    }

    assert "TMM-RETURN-PRACTICE-MISMATCH" in codes
    assert "TMM-RETURN-MASTERY-MISMATCH" in codes
    assert "TMM-RETURN-DECISION-MISMATCH" in codes
    assert "TMM-RETURN-APPLICATION-MISMATCH" in codes
    assert "TMM-RETURN-EDGE-MISMATCH" in codes
    assert "TMM-RETURN-PASSAGE-MISMATCH" in codes
    assert "TMM-CONTRACT-FINGERPRINT-MISMATCH" in codes


def test_piece_return_requires_authoritative_mastery_and_unlock(
    hot_cross_buns_package: CanonicalMusicPackage,
) -> None:
    """TEST-CURR-POLICY-009: capture alone cannot bypass mastery or policy."""

    fixture = _return_fixture(hot_cross_buns_package)
    inconclusive, hold = decide_curriculum_unlock(
        fixture[2],
        fixture[4].prerequisite_node_id,
        _support(),
        (),
    )

    with pytest.raises(CurriculumPieceReturnError, match="TMM-RETURN-MASTERY-MISMATCH"):
        build_curriculum_piece_return(
            fixture[0],
            fixture[1],
            fixture[2],
            fixture[3],
            fixture[4],
            fixture[5],
            fixture[6].binding,
            inconclusive,
            hold,
        )
