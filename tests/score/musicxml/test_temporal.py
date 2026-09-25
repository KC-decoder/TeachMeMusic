"""Task 7F evidence for exact temporal mapping through the public edge."""

from __future__ import annotations

from fractions import Fraction
from pathlib import Path

import pytest

from teachmemusic.score.musicxml.temporal import TemporalMappingError
from teachmemusic.score.parser import parse_musicxml_timeline, parse_musicxml_timeline_package
from teachmemusic.score.v2.serialization import package_from_json, package_to_json


def _fixture(directory: str) -> bytes:
    path = next((Path("tests/fixtures/scores") / directory).glob("*.mxl"))
    return path.read_bytes()


def _xml(form: str, measure_body: str, *, version: str = "4.0") -> bytes:
    kind = "Partwise" if form == "partwise" else "Timewise"
    if form == "partwise":
        body = f'<part id="P1"><measure number="1">{measure_body}</measure></part>'
    else:
        body = f'<measure number="1"><part id="P1">{measure_body}</part></measure>'
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        f'<!DOCTYPE score-{form} PUBLIC "-//Recordare//DTD MusicXML {version} {kind}//EN" '
        f'"http://www.musicxml.org/dtds/{form}.dtd">'
        f'<score-{form} version="{version}"><part-list><score-part id="P1">'
        f"<part-name>Test</part-name></score-part></part-list>{body}</score-{form}>"
    ).encode()


def test_hot_cross_buns_temporal_projection_matches_ground_truth() -> None:
    """TEST-MXML-TEMPORAL-001: all eight verified beginner measures map."""

    result = parse_musicxml_timeline(_fixture("TMM-REF-CANDIDATE-001-Hot-Cross-Buns"))
    part = result.score.parts[0]
    assert result.completeness == "temporal-only"
    assert result.musicxml_version == "4.0"
    assert len(part.measures) == 8
    assert [measure.extent for measure in part.measures] == [Fraction(4)] * 8
    assert sum(len(measure.events) for measure in part.measures) == 20
    assert [event.kind for event in part.measures[1].events] == ["pitched", "rest"]
    assert [
        (event.pitch.step if event.pitch else None, event.onset, event.duration)
        for event in part.measures[0].events
    ] == [("B", Fraction(0), Fraction(2)), ("A", Fraction(2), Fraction(2))]
    assert part.measures[0].attributes[0].keys[0].fifths == 1
    assert part.measures[0].attributes[0].times[0].beats == ("4",)
    assert part.measures[-1].barlines[-1].style == "light-heavy"
    assert len(result.score.annotations.lyrics) == 34
    assert part.measures[0].sounds[0].tempo == 96
    assert "sound" not in {item.tag for item in result.deferred}
    assert "print" not in {item.tag for item in result.deferred}


def test_happy_birthday_polyphony_and_chords_match_ground_truth() -> None:
    """TEST-MXML-TEMPORAL-002: 59 source events retain exact time and voices."""

    result = parse_musicxml_timeline(_fixture("TMM-REF-CANDIDATE-002-Happy-Birthday"))
    part = result.score.parts[0]
    assert result.musicxml_version == "2.0"
    assert len(part.measures) == 8
    assert all(measure.extent == Fraction(3) for measure in part.measures)
    events = [event for measure in part.measures for event in measure.events]
    assert len(events) == 59
    assert sum(event.kind == "pitched" for event in events) == 52
    assert sum(event.kind == "rest" for event in events) == 7
    assert all(measure.staves == ("1", "2") for measure in part.measures)
    assert all(measure.voices == ("1", "5") for measure in part.measures)
    assert len({event.chord_id for event in events if event.chord_id is not None}) == 9
    assert all(len(measure.cursor_moves) == 1 for measure in part.measures)
    first = part.measures[0]
    assert [(event.onset, event.duration) for event in first.events[:4]] == [
        (Fraction(0), Fraction(1, 2)),
        (Fraction(1, 2), Fraction(1, 2)),
        (Fraction(1), Fraction(1)),
        (Fraction(2), Fraction(1)),
    ]
    assert [
        (event.pitch.step, event.pitch.octave) for event in first.events[5:] if event.pitch
    ] == [("C", 3), ("E", 3), ("G", 3)]
    assert len(result.score.annotations.harmonies) == 3
    assert part.instruments[0].playback.midi[0].program == 1
    assert "midi-instrument" not in {item.tag for item in result.deferred}


@pytest.mark.parametrize("form", ["partwise", "timewise"])
@pytest.mark.parametrize("version", ["2.0", "4.0"])
def test_both_document_forms_and_cursor_moves(form: str, version: str) -> None:
    """TEST-MXML-TEMPORAL-003: both roots map a shared musical timeline."""

    body = (
        "<attributes><divisions>2</divisions><time><beats>3</beats><beat-type>4"
        "</beat-type></time><clef><sign>G</sign><line>2</line></clef></attributes>"
        "<note><pitch><step>C</step><octave>4</octave></pitch><duration>2</duration>"
        "<voice>1</voice><type>quarter</type></note>"
        "<forward><duration>4</duration></forward>"
        "<backup><duration>6</duration></backup>"
        "<note><rest/><duration>6</duration><voice>2</voice><type>half</type><dot/>"
        "</note>"
    )
    result = parse_musicxml_timeline(_xml(form, body, version=version))
    measure = result.score.parts[0].measures[0]
    assert measure.extent == Fraction(3)
    assert measure.voices == ("1", "2")
    assert [(move.kind, move.before, move.after) for move in measure.cursor_moves] == [
        ("forward", Fraction(1), Fraction(3)),
        ("backup", Fraction(3), Fraction(0)),
    ]
    assert measure.events[-1].duration == Fraction(3)


def test_chord_without_preceding_note_fails_closed() -> None:
    """TEST-MXML-TEMPORAL-004: malformed musical grouping cannot be guessed."""

    body = (
        "<attributes><divisions>1</divisions></attributes>"
        "<note><chord/><pitch><step>C</step><octave>4</octave></pitch>"
        "<duration>1</duration><type>quarter</type></note>"
    )
    with pytest.raises(TemporalMappingError, match="chord follower"):
        parse_musicxml_timeline(_xml("partwise", body))


def test_midmeasure_divisions_beams_tuplets_and_barline() -> None:
    """TEST-MXML-TEMPORAL-005: written rhythm survives changes of source units."""

    body = (
        "<attributes><divisions>2</divisions></attributes>"
        "<note><pitch><step>D</step><alter>-1</alter><octave>4</octave></pitch>"
        '<duration>1</duration><type>eighth</type><beam number="1">begin</beam></note>'
        "<attributes><divisions>6</divisions></attributes>"
        "<note><pitch><step>E</step><octave>4</octave></pitch><duration>2</duration>"
        "<type>eighth</type><time-modification><actual-notes>3</actual-notes>"
        "<normal-notes>2</normal-notes><normal-type>quarter</normal-type>"
        '<normal-dot/></time-modification><beam number="1">end</beam>'
        '<notations><tuplet type="start" number="1"/></notations></note>'
        '<barline location="right"><bar-style>light-heavy</bar-style></barline>'
    )
    measure = parse_musicxml_timeline(_xml("partwise", body)).score.parts[0].measures[0]
    assert measure.events[0].pitch is not None
    assert measure.events[0].pitch.alter == Fraction(-1)
    assert [event.onset for event in measure.events] == [Fraction(0), Fraction(1, 2)]
    assert measure.events[1].duration == Fraction(1, 3)
    assert measure.events[1].time_modification == (3, 2)
    assert (measure.events[1].normal_type, measure.events[1].normal_dots) == ("quarter", 1)
    assert [(beam.number, beam.value) for beam in measure.events[1].beams] == [(1, "end")]
    assert measure.events[1].tuplets[0].action == "start"
    assert measure.barlines[0].style == "light-heavy"


def test_thirty_second_written_duration_uses_musicxml_spelling() -> None:
    """TEST-MXML-CORPUS-006: the standard 32nd token maps exactly."""

    body = (
        "<attributes><divisions>8</divisions></attributes>"
        "<note><pitch><step>C</step><octave>4</octave></pitch>"
        "<duration>1</duration><type>32nd</type></note>"
    )
    event = parse_musicxml_timeline(_xml("partwise", body)).score.parts[0].measures[0].events[0]
    assert event.written_type == "32nd"
    assert event.written_duration == Fraction(1, 8)


def test_missing_divisions_uses_standard_default_without_inventing_attribute() -> None:
    """TEST-MXML-CORPUS-007: absent divisions uses 1 only for arithmetic."""

    body = (
        "<attributes><time><beats>4</beats><beat-type>4</beat-type></time></attributes>"
        "<note><rest/><duration>4</duration><type>whole</type></note>"
    )
    measure = parse_musicxml_timeline(_xml("partwise", body)).score.parts[0].measures[0]
    assert measure.extent == 4
    assert measure.events[0].duration == 4
    assert measure.attributes[0].divisions is None


def test_chord_can_span_staff_and_voice_without_losing_shared_onset() -> None:
    """TEST-MXML-CORPUS-008: chord membership is not staff/voice identity."""

    body = (
        "<attributes><divisions>1</divisions><staves>2</staves></attributes>"
        "<note><pitch><step>E</step><octave>5</octave></pitch><duration>1</duration>"
        "<voice>X</voice><type>quarter</type><staff>1</staff></note>"
        "<note><chord/><pitch><step>C</step><octave>4</octave></pitch>"
        "<duration>1</duration><voice>Y</voice><type>quarter</type><staff>2</staff></note>"
    )
    events = parse_musicxml_timeline(_xml("partwise", body)).score.parts[0].measures[0].events
    assert [event.onset for event in events] == [0, 0]
    assert [event.staff for event in events] == ["1", "2"]
    assert [event.voice for event in events] == ["X", "Y"]
    assert events[0].chord_id == events[0].id == events[1].chord_id


def test_nested_slash_measure_style_maps_action_and_note_type() -> None:
    """TEST-MXML-CORPUS-009: slash child content is not parsed as an integer."""

    body = (
        "<attributes><divisions>1</divisions><measure-style>"
        '<slash type="start" use-stems="no"><slash-type>quarter</slash-type>'
        "<slash-dot/></slash></measure-style></attributes>"
        "<note><rest/><duration>1</duration><type>quarter</type></note>"
    )
    style = parse_musicxml_timeline(_xml("partwise", body)).score.parts[0].measures[0]
    assert style.attributes[0].measure_styles[0].action == "start"
    assert style.attributes[0].measure_styles[0].value is None
    assert style.attributes[0].measure_styles[0].slash_type == "quarter"
    assert style.attributes[0].measure_styles[0].slash_dots == 1


def test_part_body_omitted_from_part_list_is_preserved() -> None:
    """TEST-MXML-CORPUS-010: unlisted body parts are retained explicitly."""

    source = (
        b'<score-partwise version="4.0"><part-list><score-part id="P1">'
        b"<part-name>Listed</part-name></score-part></part-list>"
        b'<part id="P1"><measure number="1"><note><rest/><duration>1</duration>'
        b"<type>quarter</type></note></measure></part>"
        b'<part id="P2"><measure number="1"><note><rest/><duration>1</duration>'
        b"<type>quarter</type></note></measure></part></score-partwise>"
    )
    parts = parse_musicxml_timeline(source).score.parts
    assert [(part.id, part.name) for part in parts] == [("P1", "Listed"), ("P2", None)]
    assert len(parts[1].measures[0].events) == 1


def test_backup_underflow_preserves_raw_duration_and_explicit_recovery() -> None:
    """TEST-MXML-CORPUS-014: oversized backup uses a recorded compatibility reset."""

    body = (
        "<attributes><divisions>1</divisions></attributes>"
        "<note><rest/><duration>4</duration><type>whole</type></note>"
        "<backup><duration>384</duration></backup>"
        "<note><rest/><duration>4</duration><voice>2</voice><type>whole</type></note>"
    )
    result = parse_musicxml_timeline(_xml("partwise", body))
    measure = result.score.parts[0].measures[0]
    assert measure.extent == 4
    assert [event.onset for event in measure.events] == [0, 0]
    assert len(measure.cursor_moves) == 1
    move = measure.cursor_moves[0]
    assert (move.before, move.after, move.source_duration) == (4, 0, 384)
    assert move.underflow_recovered
    assert parse_musicxml_timeline_package(_xml("partwise", body)).documents


def test_backup_past_measure_start_fails_closed() -> None:
    """TEST-MXML-TEMPORAL-006: cursor underflow is not silently clamped."""

    body = (
        "<attributes><divisions>1</divisions></attributes><backup><duration>1</duration></backup>"
    )
    with pytest.raises(TemporalMappingError, match="precedes measure start"):
        parse_musicxml_timeline(_xml("partwise", body))


@pytest.mark.parametrize("version", ("1.0", "1.1", "2.0", "3.0", "3.1", "4.0", "4.1-draft"))
@pytest.mark.parametrize("form", ("partwise", "timewise"))
def test_minimal_temporal_mapping_across_pinned_versions(version: str, form: str) -> None:
    """TEST-MXML-TEMPORAL-013: native validation and timing cross all versions."""

    public_version = "4.1" if version == "4.1-draft" else version
    label = "Partwise" if form == "partwise" else "Timewise"
    version_attr = "" if version == "1.0" else f' version="{public_version}"'
    body = (
        "<attributes><divisions>1</divisions></attributes>"
        "<note><pitch><step>C</step><octave>4</octave></pitch>"
        "<duration>1</duration><type>quarter</type></note>"
    )
    measures = (
        f'<part id="P1"><measure number="1">{body}</measure></part>'
        if form == "partwise"
        else f'<measure number="1"><part id="P1">{body}</part></measure>'
    )
    source = (
        f'<!DOCTYPE score-{form} PUBLIC "-//Recordare//DTD MusicXML '
        f'{public_version} {label}//EN" "http://www.musicxml.org/dtds/{form}.dtd">'
        f'<score-{form}{version_attr}><part-list><score-part id="P1">'
        f"<part-name>Test</part-name></score-part></part-list>{measures}</score-{form}>"
    ).encode()
    result = parse_musicxml_timeline(source)
    assert result.musicxml_version == version
    assert result.score.parts[0].measures[0].events[0].score_onset == 0
    assert parse_musicxml_timeline_package(source).documents


def test_moonlight_sonata_complex_fixture_maps_without_loss() -> None:
    """TEST-MXML-FIXTURE-001: the approved complex fixture must pass one general path."""

    source = _fixture("TMM-REF-CANDIDATE-004-Moonlight-Sonata")
    result = parse_musicxml_timeline(source)
    assert len(result.score.parts) == 1
    assert len(result.score.parts[0].measures) == 335
    assert result.deferred == ()
    inferred = tuple(
        endpoint
        for span in result.score.annotations.time_spans
        for endpoint in span.endpoints
        if endpoint.inferred
    )
    assert len(inferred) == 3
    assert {endpoint.anchor.measure_id.rsplit(":", 1)[-1] for endpoint in inferred} == {
        "m18",
        "m54",
    }
    assert {endpoint.inference_reason for endpoint in inferred} == {
        "musescore-2-adjacent-wedge-recovery"
    }
    pedal_points = [
        direction
        for direction in result.score.annotations.directions
        if direction.family == "pedal"
    ]
    measure_135_id = next(
        measure.id for measure in result.score.parts[0].measures if measure.number == "135"
    )
    assert any(
        direction.value == "stop"
        and direction.anchor.measure_id == measure_135_id
        and direction.anchor.staff == "1"
        and direction.pedal_line is None
        and direction.pedal_sign is None
        for direction in pedal_points
    )
    assert any(
        [endpoint.anchor.staff for endpoint in span.endpoints] == ["2", "2"]
        and [endpoint.pedal_line for endpoint in span.endpoints] == [True, True]
        for span in result.score.annotations.time_spans
        if span.kind == "pedal"
    )
    source_only_wavy_stops = [
        span
        for span in result.score.annotations.spans
        if span.kind == "wavy-line" and [endpoint.action for endpoint in span.endpoints] == ["stop"]
    ]
    assert [span.number for span in source_only_wavy_stops] == ["1", "2", "3", "4", "5"]
    package = parse_musicxml_timeline_package(source)
    assert package_from_json(package_to_json(package)) == package


def test_deux_arabesques_complex_fixture_maps_without_loss() -> None:
    """TEST-MXML-FIXTURE-007: a second MuseScore 2.x complex score is lossless."""

    source = _fixture("TMM-REF-CANDIDATE-005-Deux-Arabesques")
    result = parse_musicxml_timeline(source)
    part = result.score.parts[0]
    events = [event for measure in part.measures for event in measure.events]

    assert result.musicxml_version == "3.0"
    assert len(result.score.parts) == 1
    assert len(part.measures) == 217
    assert len(events) == 3_758
    assert sum(event.kind == "pitched" for event in events) == 3_428
    assert sum(event.kind == "rest" for event in events) == 330
    assert result.deferred == ()
    assert not any(
        endpoint.inferred
        for span in result.score.annotations.time_spans
        for endpoint in span.endpoints
    )

    package = parse_musicxml_timeline_package(source)
    assert package_from_json(package_to_json(package)) == package
