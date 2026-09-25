"""Task 7H evidence for canonical playback mapping and invariants."""

from __future__ import annotations

from dataclasses import replace
from fractions import Fraction
from pathlib import Path

from teachmemusic.score.parser import parse_musicxml_timeline
from teachmemusic.score.v2.playback import MidiInstrument
from teachmemusic.score.v2.temporal_codec import temporal_from_dict, temporal_to_dict
from teachmemusic.score.v2.temporal_validation import validate_temporal_score


def _fixture(directory: str) -> bytes:
    path = next((Path("tests/fixtures/scores") / directory).glob("*.mxl"))
    return path.read_bytes()


def test_hot_cross_buns_initial_midi_and_tempo_are_canonical() -> None:
    """TEST-MXML-PLAYBACK-001: verified beginner playback facts map exactly."""

    score = parse_musicxml_timeline(_fixture("TMM-REF-CANDIDATE-001-Hot-Cross-Buns")).score
    instrument = score.parts[0].instruments[0]
    midi = instrument.playback.midi[0]
    assert (midi.channel, midi.program, midi.volume, midi.pan) == (
        1,
        1,
        Fraction(393701, 5000),
        Fraction(0),
    )
    assert instrument.playback.devices[0].port == 1
    sound = score.parts[0].measures[0].sounds[0]
    assert (sound.onset, sound.score_onset, sound.tempo) == (
        Fraction(0),
        Fraction(0),
        Fraction(96),
    )
    assert not validate_temporal_score(score)


def test_happy_birthday_initial_midi_is_no_longer_deferred() -> None:
    """TEST-MXML-PLAYBACK-002: MusicXML 2.0 MIDI setup crosses the boundary."""

    result = parse_musicxml_timeline(_fixture("TMM-REF-CANDIDATE-002-Happy-Birthday"))
    midi = result.score.parts[0].instruments[0].playback.midi[0]
    assert (midi.instrument_id, midi.channel, midi.program) == ("P1-I3", 1, 1)
    assert "midi-instrument" not in {item.tag for item in result.deferred}
    assert not validate_temporal_score(result.score)


def test_clair_de_lune_tempo_and_dynamics_changes_keep_score_time() -> None:
    """TEST-MXML-PLAYBACK-003: complex fixture playback changes retain order/time."""

    score = parse_musicxml_timeline(_fixture("TMM-REF-CANDIDATE-003-Clair-de-Lune")).score
    sounds = tuple(sound for measure in score.parts[0].measures for sound in measure.sounds)
    assert len(sounds) == 68
    assert sum(sound.tempo is not None for sound in sounds) == 55
    assert sum(sound.dynamics is not None for sound in sounds) == 13
    assert [sound.tempo for sound in sounds if sound.tempo is not None][:3] == [48, 49, 50]
    assert sounds[7].onset == Fraction(3, 2)
    assert sounds[7].score_onset == Fraction(111, 2)
    assert not validate_temporal_score(score)


def test_playback_graph_strict_json_round_trip() -> None:
    """TEST-MXML-PLAYBACK-004: exact fractions survive the closed codec."""

    score = parse_musicxml_timeline(_fixture("TMM-REF-CANDIDATE-001-Hot-Cross-Buns")).score
    assert temporal_from_dict(temporal_to_dict(score)) == score


def test_invalid_midi_range_fails_canonical_validation() -> None:
    """TEST-MXML-PLAYBACK-005: impossible MIDI channels fail closed."""

    score = parse_musicxml_timeline(_fixture("TMM-REF-CANDIDATE-001-Hot-Cross-Buns")).score
    part = score.parts[0]
    instrument = part.instruments[0]
    original = instrument.playback.midi[0]
    invalid_midi = MidiInstrument(
        instrument_id=original.instrument_id,
        channel=17,
        name=original.name,
        bank=original.bank,
        program=original.program,
        unpitched=original.unpitched,
        volume=original.volume,
        pan=original.pan,
        elevation=original.elevation,
    )
    invalid_playback = replace(instrument.playback, midi=(invalid_midi,))
    invalid_instrument = replace(instrument, playback=invalid_playback)
    invalid_part = replace(part, instruments=(invalid_instrument,))
    invalid_score = replace(score, parts=(invalid_part,))
    assert {issue.code for issue in validate_temporal_score(invalid_score)} == {
        "TEMPORAL_INSTRUMENT_ID"
    }
