"""Tests for immutable learner-performance boundary contracts."""

from dataclasses import FrozenInstanceError, replace

import pytest

from teachmemusic.performance import (
    AttemptCompletion,
    CalibrationProfile,
    EvidenceConfidence,
    LearnerAttempt,
    MidiEventKind,
    NormalizedMidiEvent,
    Observation,
    ObservationDimension,
    ObservationSource,
    ObservationStatus,
    PerformanceBundle,
    PerformanceSerializationError,
    RawMidiMessage,
    performance_bundle_from_dict,
    performance_bundle_from_json,
    performance_bundle_to_dict,
    performance_bundle_to_json,
    validate_performance_bundle,
)


def valid_performance_bundle() -> PerformanceBundle:
    """Return a small, fully linked performance example."""

    calibration = CalibrationProfile(
        id="calibration:one",
        version="calibration-v1",
        device_id="device:casio",
        input_name="Casio MIDI",
        timestamp_origin="monotonic-microseconds",
        pitch_numbering_confirmed=True,
        sustain_available=True,
        clock_offset_microseconds=0,
        clock_jitter_microseconds=500,
        timing_window_microseconds=100_000,
        chord_window_microseconds=50_000,
        approved=True,
        approved_at_utc="2026-09-30T12:00:00Z",
    )
    raw_on = RawMidiMessage(
        id="midi-message:on",
        sequence_number=0,
        timestamp_microseconds=1_000,
        data=(0x90, 60, 96),
    )
    raw_off = RawMidiMessage(
        id="midi-message:off",
        sequence_number=1,
        timestamp_microseconds=2_000,
        data=(0x80, 60, 0),
    )
    note_on = NormalizedMidiEvent(
        id="midi-event:on",
        raw_message_id=raw_on.id,
        kind=MidiEventKind.NOTE_ON,
        timestamp_microseconds=raw_on.timestamp_microseconds,
        channel=1,
        note=60,
        velocity=96,
    )
    note_off = NormalizedMidiEvent(
        id="midi-event:off",
        raw_message_id=raw_off.id,
        kind=MidiEventKind.NOTE_OFF,
        timestamp_microseconds=raw_off.timestamp_microseconds,
        channel=1,
        note=60,
        velocity=0,
    )
    attempt = LearnerAttempt(
        id="attempt:one",
        run_id="run:one",
        exercise_id="exercise:one",
        calibration_id=calibration.id,
        practice_mode="supported-performance",
        support_state_id="support:one",
        started_at_utc="2026-09-30T12:01:00Z",
        start_microseconds=0,
        end_microseconds=3_000,
        completion=AttemptCompletion.COMPLETED,
        raw_messages=(raw_on, raw_off),
        normalized_events=(note_on, note_off),
    )
    observation = Observation(
        id="observation:pitch-one",
        attempt_id=attempt.id,
        exercise_id=attempt.exercise_id,
        dimension=ObservationDimension.PITCH,
        status=ObservationStatus.MATCH,
        source=ObservationSource.MIDI,
        expected_canonical_ids=("event:score-note-1",),
        observed_event_ids=(note_on.id,),
        expected_value="midi:60",
        observed_value="midi:60",
        matching_policy="exact-pitch-v1",
        confidence=EvidenceConfidence.HIGH,
    )
    return PerformanceBundle(
        calibrations=(calibration,),
        attempts=(attempt,),
        observations=(observation,),
    )


def test_valid_performance_bundle_round_trips_deterministically() -> None:
    """TEST-PERF-CONTRACT-001: strict round trips preserve the complete value."""

    bundle = valid_performance_bundle()
    payload = performance_bundle_to_json(bundle)

    assert validate_performance_bundle(bundle) == ()
    assert payload.endswith("\n")
    assert performance_bundle_to_json(bundle) == payload
    assert performance_bundle_from_json(payload) == bundle
    assert performance_bundle_from_dict(performance_bundle_to_dict(bundle)) == bundle
    assert type(performance_bundle_to_dict(bundle)["contract_id"]) is str


def test_performance_contracts_are_immutable() -> None:
    """TEST-PERF-CONTRACT-002: captured boundary values are immutable."""

    bundle = valid_performance_bundle()
    with pytest.raises(FrozenInstanceError):
        bundle.contract_version = "changed"  # type: ignore[misc]


def test_performance_decoder_rejects_unknown_and_duplicate_fields() -> None:
    """TEST-PERF-CONTRACT-003: malformed or ambiguous input fails closed."""

    data = performance_bundle_to_dict(valid_performance_bundle())
    data["unexpected"] = True
    with pytest.raises(PerformanceSerializationError, match="unexpected"):
        performance_bundle_from_dict(data)

    with pytest.raises(PerformanceSerializationError, match="duplicate JSON key"):
        performance_bundle_from_json('{"type":"PerformanceBundle","type":"again"}')

    with pytest.raises(PerformanceSerializationError, match="PERF_CONTRACT_VERSION"):
        performance_bundle_to_json(
            replace(valid_performance_bundle(), contract_version="unsupported")
        )


def test_performance_validation_rejects_zero_velocity_note_on() -> None:
    """TEST-PERF-CONTRACT-004: velocity-zero note-on requires normalization."""

    bundle = valid_performance_bundle()
    attempt = bundle.attempts[0]
    bad_event = replace(attempt.normalized_events[0], velocity=0)
    bad_attempt = replace(
        attempt,
        normalized_events=(bad_event, attempt.normalized_events[1]),
    )
    issues = validate_performance_bundle(replace(bundle, attempts=(bad_attempt,)))

    assert "PERF_ZERO_VELOCITY_NOTE_ON" in {issue.code for issue in issues}


def test_unobservable_evidence_must_block_progression() -> None:
    """TEST-PERF-CONTRACT-005: unobservable facts block teaching evidence."""

    bundle = valid_performance_bundle()
    invalid = replace(
        bundle.observations[0],
        status=ObservationStatus.UNOBSERVABLE,
        blocking=False,
    )
    issues = validate_performance_bundle(replace(bundle, observations=(invalid,)))

    assert "PERF_INVALID_NOT_BLOCKING" in {issue.code for issue in issues}


def test_unknown_attempt_completion_is_rejected() -> None:
    """TEST-PERF-CONTRACT-006: unknown performance states fail validation."""

    bundle = valid_performance_bundle()
    invalid = replace(bundle.attempts[0], completion="unknown")  # type: ignore[arg-type]
    issues = validate_performance_bundle(replace(bundle, attempts=(invalid,)))

    assert "PERF_COMPLETION" in {issue.code for issue in issues}
