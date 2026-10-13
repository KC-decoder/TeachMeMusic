"""Tests for deterministic, mode-aware factual attempt alignment."""

from __future__ import annotations

from dataclasses import replace

import pytest

from teachmemusic.analysis import analyze_canonical_score
from teachmemusic.performance import (
    AttemptCompletion,
    CalibrationProfile,
    ExpectedPerformance,
    ExpectedPerformanceNote,
    LearnerAttempt,
    MidiEventKind,
    NormalizedMidiEvent,
    ObservationDimension,
    ObservationStatus,
    PerformanceBundle,
    align_attempt,
    validate_performance_bundle,
)
from teachmemusic.score import CanonicalMusicPackage
from teachmemusic.teaching import (
    ExpectedPerformanceProjectionError,
    LearnerContextSnapshot,
    LearnerTrack,
    PracticeMode,
    build_exercise_presentation,
    build_expected_performance,
    generate_beginner_lesson_plan,
)


def _calibration(
    *, timing_window: int | None = 50_000, chord_window: int | None = 50_000
) -> CalibrationProfile:
    return CalibrationProfile(
        id="calibration:alignment",
        version="calibration-v1",
        device_id="device:casio-px-770",
        input_name="CASIO USB-MIDI",
        timestamp_origin="browser-monotonic-microseconds",
        pitch_numbering_confirmed=True,
        sustain_available=True,
        clock_offset_microseconds=0,
        clock_jitter_microseconds=3_400,
        timing_window_microseconds=timing_window,
        chord_window_microseconds=chord_window,
        approved=True,
        approved_at_utc="2026-10-01T20:00:00Z",
    )


def _expected(
    notes: tuple[ExpectedPerformanceNote, ...] | None = None,
    *,
    mode: str = "supported-performance",
    dimensions: tuple[ObservationDimension, ...] = (
        ObservationDimension.PITCH,
        ObservationDimension.ORDER,
        ObservationDimension.ONSET,
        ObservationDimension.DURATION,
        ObservationDimension.CONTINUITY,
    ),
) -> ExpectedPerformance:
    return ExpectedPerformance(
        exercise_id="exercise:alignment",
        practice_mode=mode,
        notes=notes
        or (
            ExpectedPerformanceNote(
                id="playback-note:expected-0",
                start_microseconds=0,
                end_microseconds=500_000,
                midi_pitch=60,
                expected_ids=("event:expected-0",),
                layers=("part:p1|staff=1|voice=1",),
            ),
            ExpectedPerformanceNote(
                id="playback-note:expected-1",
                start_microseconds=500_000,
                end_microseconds=1_000_000,
                midi_pitch=62,
                expected_ids=("event:expected-1",),
                layers=("part:p1|staff=1|voice=1",),
            ),
        ),
        target_dimensions=dimensions,
        source_contract_version="test-presentation@1;test-playback@1",
    )


def _attempt(
    notes: tuple[tuple[int, int, int | None], ...],
    *,
    mode: str = "supported-performance",
    completion: AttemptCompletion = AttemptCompletion.COMPLETED,
    pedal: tuple[tuple[int, int], ...] = (),
    exercise_id: str = "exercise:alignment",
) -> LearnerAttempt:
    start = 1_000_000
    events: list[NormalizedMidiEvent] = []
    serial = 0
    for pitch, relative_onset, relative_release in notes:
        events.append(
            NormalizedMidiEvent(
                id=f"midi-event:{serial:03d}",
                raw_message_id=None,
                kind=MidiEventKind.NOTE_ON,
                timestamp_microseconds=start + relative_onset,
                channel=1,
                note=pitch,
                velocity=80 + serial,
            )
        )
        serial += 1
        if relative_release is not None:
            events.append(
                NormalizedMidiEvent(
                    id=f"midi-event:{serial:03d}",
                    raw_message_id=None,
                    kind=MidiEventKind.NOTE_OFF,
                    timestamp_microseconds=start + relative_release,
                    channel=1,
                    note=pitch,
                    velocity=0,
                )
            )
            serial += 1
    for relative_time, value in pedal:
        events.append(
            NormalizedMidiEvent(
                id=f"midi-event:{serial:03d}",
                raw_message_id=None,
                kind=MidiEventKind.CONTROL_CHANGE,
                timestamp_microseconds=start + relative_time,
                channel=1,
                controller=64,
                value=value,
            )
        )
        serial += 1
    ordered = tuple(sorted(events, key=lambda item: (item.timestamp_microseconds, item.id)))
    end = max((item.timestamp_microseconds for item in ordered), default=start) + 100_000
    return LearnerAttempt(
        id="attempt:alignment",
        run_id="run:alignment",
        exercise_id=exercise_id,
        calibration_id="calibration:alignment",
        practice_mode=mode,
        support_state_id="support:alignment",
        started_at_utc="2026-10-01T20:01:00Z",
        start_microseconds=start,
        end_microseconds=end,
        completion=completion,
        normalized_events=ordered,
    )


def _by_dimension(observations, dimension: ObservationDimension):
    return tuple(item for item in observations if item.dimension is dimension)


def test_exact_monophonic_attempt_produces_separate_factual_matches() -> None:
    """TEST-ALIGN-001: exact pitch, order, timing, release, and continuity match."""

    attempt = _attempt(((60, 10_000, 510_000), (62, 510_000, 1_010_000)))
    observations = align_attempt(_expected(), attempt, _calibration())

    assert all(
        item.status is ObservationStatus.MATCH
        for dimension in (
            ObservationDimension.INPUT,
            ObservationDimension.PITCH,
            ObservationDimension.ORDER,
            ObservationDimension.ONSET,
            ObservationDimension.DURATION,
            ObservationDimension.RELEASE,
            ObservationDimension.CONTINUITY,
        )
        for item in _by_dimension(observations, dimension)
    )
    assert _by_dimension(observations, ObservationDimension.VELOCITY)[0].status is (
        ObservationStatus.AMBIGUOUS
    )
    bundle = replace(
        PerformanceBundle(),
        calibrations=(_calibration(),),
        attempts=(attempt,),
        observations=observations,
    )
    assert validate_performance_bundle(bundle) == ()
    assert align_attempt(_expected(), attempt, _calibration()) == observations


def test_exact_alignment_property_holds_at_pitch_and_window_boundaries() -> None:
    """TEST-ALIGN-009: exact matching is stable across bounded representative values."""

    for pitch in (21, 60, 108):
        for onset_delta in (-50_000, 0, 50_000):
            expected = _expected(
                notes=(
                    ExpectedPerformanceNote(
                        id=f"playback-note:property-{pitch}",
                        start_microseconds=100_000,
                        end_microseconds=500_000,
                        midi_pitch=pitch,
                        expected_ids=(f"event:property-{pitch}",),
                    ),
                ),
                dimensions=(
                    ObservationDimension.PITCH,
                    ObservationDimension.ONSET,
                    ObservationDimension.DURATION,
                ),
            )
            attempt = _attempt(((pitch, 100_000 + onset_delta, 500_000 + onset_delta),))
            observations = align_attempt(expected, attempt, _calibration())
            for dimension in (
                ObservationDimension.PITCH,
                ObservationDimension.ONSET,
                ObservationDimension.DURATION,
            ):
                assert all(
                    item.status is ObservationStatus.MATCH
                    for item in _by_dimension(observations, dimension)
                )


@pytest.mark.parametrize(
    ("notes", "marker"),
    [
        (((60, 0, 500_000), (63, 500_000, 1_000_000)), "substituted-midi:63"),
        (((60, 0, 500_000),), "missing"),
        (
            ((60, 0, 200_000), (61, 250_000, 450_000), (62, 500_000, 1_000_000)),
            "extra-unmatched-midi:61",
        ),
        (
            ((60, 0, 200_000), (60, 250_000, 450_000), (62, 500_000, 1_000_000)),
            "repeated-midi:60",
        ),
    ],
)
def test_pitch_mutations_remain_explicit_and_blocking(notes, marker: str) -> None:
    """TEST-ALIGN-002: substitutions, missing, extra, and repeated notes survive."""

    observations = align_attempt(_expected(), _attempt(notes), _calibration())
    discrepancies = tuple(
        item
        for item in _by_dimension(observations, ObservationDimension.PITCH)
        if item.status is ObservationStatus.DISCREPANCY
    )

    assert discrepancies
    assert any(marker in (item.observed_value or "") for item in discrepancies)
    assert all(item.blocking for item in discrepancies)


def test_timing_mutations_report_late_short_and_interrupted_without_guessing() -> None:
    """TEST-ALIGN-003: timing and release mutations use separate observations."""

    mutated = _attempt(((60, 200_000, 400_000), (62, 500_000, None)))
    observations = align_attempt(_expected(), mutated, _calibration())

    onset_values = {
        item.observed_value for item in _by_dimension(observations, ObservationDimension.ONSET)
    }
    duration_values = {
        item.observed_value for item in _by_dimension(observations, ObservationDimension.DURATION)
    }
    release_values = {
        item.observed_value for item in _by_dimension(observations, ObservationDimension.RELEASE)
    }
    assert "late:200000" in onset_values
    assert "short:200000" in duration_values
    assert "interrupted-no-release" in duration_values
    assert "interrupted-no-release" in release_values


@pytest.mark.parametrize(
    ("mode", "calibration"),
    [
        ("follow-pitch", _calibration()),
        ("supported-performance", _calibration(timing_window=None)),
    ],
)
def test_unsupported_timing_is_unobservable_never_a_false_pass(mode, calibration) -> None:
    """TEST-ALIGN-004: untimed or uncalibrated rhythm evidence fails closed."""

    expected = _expected(mode=mode)
    attempt = _attempt(((60, 0, 500_000), (62, 500_000, 1_000_000)), mode=mode)
    observations = align_attempt(expected, attempt, calibration)

    timing = _by_dimension(observations, ObservationDimension.ONSET) + _by_dimension(
        observations, ObservationDimension.DURATION
    )
    assert timing
    assert all(item.status is ObservationStatus.UNOBSERVABLE for item in timing)
    assert all(item.blocking for item in timing)


def test_chords_preserve_spread_and_layer_ambiguity() -> None:
    """TEST-ALIGN-005: chord sets compare while MIDI layer identity stays ambiguous."""

    expected = _expected(
        notes=(
            ExpectedPerformanceNote(
                "playback-note:chord-0",
                0,
                500_000,
                60,
                ("event:chord-0",),
                "chord:one",
                ("part:p1|staff=1|voice=1",),
            ),
            ExpectedPerformanceNote(
                "playback-note:chord-1",
                0,
                500_000,
                64,
                ("event:chord-1",),
                "chord:one",
                ("part:p1|staff=2|voice=1",),
            ),
        ),
        dimensions=(ObservationDimension.PITCH, ObservationDimension.ORDER),
    )
    attempt = _attempt(((60, 0, 500_000), (64, 30_000, 530_000)))
    observations = align_attempt(expected, attempt, _calibration(chord_window=50_000))

    chord = _by_dimension(observations, ObservationDimension.CHORD_SET)[0]
    layer = _by_dimension(observations, ObservationDimension.HUMAN_REVIEW)[0]
    assert chord.status is ObservationStatus.MATCH
    assert chord.measured_value == "spread-microseconds:30000;expected-onset:0"
    assert layer.status is ObservationStatus.AMBIGUOUS
    assert "hand, staff, or voice" in (layer.observed_value or "")

    uncalibrated = align_attempt(expected, attempt, _calibration(chord_window=None))
    assert _by_dimension(uncalibrated, ObservationDimension.CHORD_SET)[0].status is (
        ObservationStatus.UNOBSERVABLE
    )

    extra = _attempt(((60, 0, 500_000), (64, 20_000, 520_000), (67, 30_000, 530_000)))
    extra_observations = align_attempt(expected, extra, _calibration(chord_window=50_000))
    assert _by_dimension(extra_observations, ObservationDimension.CHORD_SET)[0].status is (
        ObservationStatus.DISCREPANCY
    )


def test_overlapping_unison_and_pedal_are_retained_without_false_identity() -> None:
    """TEST-ALIGN-006: ambiguous unison identity and pedal evidence remain explicit."""

    expected = _expected(
        notes=(
            ExpectedPerformanceNote(
                "playback-note:unison-0",
                0,
                500_000,
                60,
                ("event:unison-0",),
            ),
            ExpectedPerformanceNote(
                "playback-note:unison-1",
                0,
                500_000,
                60,
                ("event:unison-1",),
            ),
        ),
        dimensions=(ObservationDimension.PITCH,),
    )
    attempt = _attempt(((60, 0, 500_000),), pedal=((100_000, 127), (400_000, 0)))
    observations = align_attempt(expected, attempt, _calibration())

    assert _by_dimension(observations, ObservationDimension.PITCH)[0].status is (
        ObservationStatus.AMBIGUOUS
    )
    pedal = _by_dimension(observations, ObservationDimension.PEDAL)[0]
    assert pedal.status is ObservationStatus.AMBIGUOUS
    assert pedal.observed_value == "controller-64-values:127,0"

    pedal_target = _expected(dimensions=(ObservationDimension.PITCH, ObservationDimension.PEDAL))
    no_pedal = align_attempt(
        pedal_target,
        _attempt(((60, 0, 500_000), (62, 500_000, 1_000_000))),
        _calibration(),
    )
    assert _by_dimension(no_pedal, ObservationDimension.PEDAL)[0].status is (
        ObservationStatus.UNOBSERVABLE
    )


def test_incomplete_attempt_returns_only_blocking_invalid_input() -> None:
    """TEST-ALIGN-007: incomplete capture cannot produce a musical pass."""

    attempt = _attempt(((60, 0, 500_000),), completion=AttemptCompletion.INPUT_FAILURE)
    observations = align_attempt(_expected(), attempt, _calibration())

    assert len(observations) == 1
    assert observations[0].dimension is ObservationDimension.INPUT
    assert observations[0].status is ObservationStatus.INVALID_INPUT
    assert observations[0].blocking


def test_verified_exercise_projection_builds_the_alignment_target(
    hot_cross_buns_package: CanonicalMusicPackage,
) -> None:
    """TEST-ALIGN-008: expected notes come from the verified exercise playback."""

    plan = generate_beginner_lesson_plan(
        hot_cross_buns_package,
        analyze_canonical_score(hot_cross_buns_package),
        LearnerContextSnapshot(id="learner-context:alignment", track=LearnerTrack.BEGINNER),
        run_id="run:alignment-projection",
        generated_at_utc="2026-10-01T12:00:00Z",
    )
    exercise = plan.exercises[2]
    presentation = build_exercise_presentation(hot_cross_buns_package, plan, exercise.id)
    expected = build_expected_performance(exercise, presentation, PracticeMode.FOLLOW_PITCH)

    assert expected.exercise_id == exercise.id
    assert expected.practice_mode == "follow-pitch"
    assert tuple(item.id for item in expected.notes) == tuple(
        item.id for item in presentation.demonstration.notes
    )
    assert {identifier for note in expected.notes for identifier in note.expected_ids} <= set(
        presentation.event_ids
    )
    with pytest.raises(ExpectedPerformanceProjectionError, match="TEACH_EXPECTED_MODE"):
        build_expected_performance(exercise, presentation, PracticeMode.RETENTION)
    with pytest.raises(ExpectedPerformanceProjectionError, match="TEACH_EXPECTED_CONTENT"):
        build_expected_performance(
            exercise,
            replace(presentation, expected_content_sha256="0" * 64),
            PracticeMode.FOLLOW_PITCH,
        )

    transfer_exercise = plan.exercises[-2]
    transfer_presentation = build_exercise_presentation(
        hot_cross_buns_package, plan, transfer_exercise.id
    )
    transfer_expected = build_expected_performance(
        transfer_exercise, transfer_presentation, PracticeMode.TRANSFER
    )
    transfer_attempt = _attempt(
        tuple(
            (note.midi_pitch, note.start_microseconds, note.end_microseconds)
            for note in transfer_expected.notes
        ),
        mode="transfer",
        exercise_id=transfer_exercise.id,
    )
    transfer_observations = align_attempt(transfer_expected, transfer_attempt, _calibration())
    assert all(
        item.status is ObservationStatus.MATCH
        for item in _by_dimension(transfer_observations, ObservationDimension.PITCH)
    )
    assert all(
        identifier.startswith("synthetic-event:")
        for note in transfer_expected.notes
        for identifier in note.expected_ids
    )
