"""Task 7F temporal-package, transposition, and strict-codec evidence."""

from __future__ import annotations

from copy import deepcopy
from fractions import Fraction
from pathlib import Path

import pytest

from teachmemusic.score.parser import parse_musicxml_timeline, parse_musicxml_timeline_package
from teachmemusic.score.v2.documents import ScoreDocument, TemporalScoreContent
from teachmemusic.score.v2.serialization import (
    CanonicalSerializationError,
    package_from_dict,
    package_from_json,
    package_to_dict,
    package_to_json,
)
from teachmemusic.score.v2.validation import validate_package


def _fixture(directory: str) -> tuple[bytes, str]:
    path = next((Path("tests/fixtures/scores") / directory).glob("*.mxl"))
    return path.read_bytes(), path.name


def _partwise(parts: str, names: tuple[str, ...] = ("P1",)) -> bytes:
    part_list = "".join(
        f'<score-part id="{name}"><part-name>{name}</part-name>'
        f'<score-instrument id="I-{name}"><instrument-name>Piano</instrument-name>'
        f"</score-instrument></score-part>"
        for name in names
    )
    return (
        '<?xml version="1.0" encoding="utf-8"?>'
        '<!DOCTYPE score-partwise PUBLIC "-//Recordare//DTD MusicXML 4.0 Partwise//EN" '
        '"http://www.musicxml.org/dtds/partwise.dtd">'
        f'<score-partwise version="4.0"><part-list>{part_list}</part-list>'
        f"{parts}</score-partwise>"
    ).encode()


@pytest.mark.parametrize(
    "directory",
    ("TMM-REF-CANDIDATE-001-Hot-Cross-Buns", "TMM-REF-CANDIDATE-002-Happy-Birthday"),
)
def test_temporal_fixture_package_round_trips_exactly(directory: str) -> None:
    """TEST-MXML-TEMPORAL-007: real temporal subsets survive strict v2 JSON."""

    source, name = _fixture(directory)
    package = parse_musicxml_timeline_package(source, logical_name=name)
    assert validate_package(package) == ()
    assert len(package.provenance.sources) == 1
    assert package.provenance.sources[0].sha256.value is not None
    score_document = package.documents[0]
    assert isinstance(score_document, ScoreDocument)
    assert isinstance(score_document.content, TemporalScoreContent)
    assert score_document.content.completeness == "temporal-only"
    assert score_document.content.deferred == ()
    encoded = package_to_json(package)
    assert package_from_json(encoded) == package
    assert package_to_json(package_from_json(encoded)) == encoded


def test_transposition_and_midmeasure_score_order() -> None:
    """TEST-MXML-TEMPORAL-008: written/sounding pitches differ predictably."""

    source = _partwise(
        '<part id="P1">'
        '<measure number="1"><attributes><divisions>1</divisions>'
        "<transpose><diatonic>-1</diatonic><chromatic>-2</chromatic></transpose>"
        "</attributes><note><pitch><step>C</step><octave>4</octave></pitch>"
        '<duration>1</duration><instrument id="I-P1"/><voice>1</voice>'
        "<type>quarter</type></note></measure>"
        '<measure number="2"><note><pitch><step>C</step><octave>4</octave></pitch>'
        "<duration>1</duration><voice>1</voice><type>quarter</type></note>"
        "<backup><duration>1</duration></backup>"
        "<attributes><transpose><diatonic>0</diatonic><chromatic>0</chromatic>"
        "</transpose></attributes>"
        "<note><pitch><step>C</step><octave>4</octave></pitch><duration>1</duration>"
        "<voice>2</voice><type>quarter</type></note></measure>"
        "</part>"
    )
    result = parse_musicxml_timeline(source)
    first, second = result.score.parts[0].measures
    assert first.events[0].pitch is not None
    assert first.events[0].pitch.step == "C"
    assert first.events[0].instrument_id == "I-P1"
    assert first.events[0].sounding_pitches[0].semitone == Fraction(58)
    assert (
        first.events[0].sounding_pitches[0].step,
        first.events[0].sounding_pitches[0].alter,
        first.events[0].sounding_pitches[0].octave,
    ) == ("B", Fraction(-1), 3)
    # The later XML attribute at onset zero applies in musical score order.
    assert [event.sounding_pitches[0].semitone for event in second.events] == [60, 60]
    assert [event.score_onset for event in second.events] == [1, 1]
    assert [event.semantic_order for event in second.events] == [1, 2]
    assert validate_package(parse_musicxml_timeline_package(source)) == ()


def test_grace_timing_and_doubled_sounding_pitch() -> None:
    """TEST-MXML-TEMPORAL-009: grace timing and octave doubling stay typed."""

    source = _partwise(
        '<part id="P1"><measure number="1"><attributes><divisions>4</divisions>'
        '<transpose><chromatic>0</chromatic><double above="yes"/></transpose>'
        '</attributes><note><grace slash="yes" steal-time-following="25"/>'
        "<pitch><step>D</step><octave>4</octave></pitch><type>eighth</type></note>"
        "<note><pitch><step>E</step><octave>4</octave></pitch><duration>4</duration>"
        "<type>quarter</type></note></measure></part>"
    )
    score = parse_musicxml_timeline(source).score
    grace, main = score.parts[0].measures[0].events
    assert grace.duration == 0
    assert grace.written_duration == Fraction(1, 2)
    assert grace.performed_duration is None
    assert grace.grace_timing is not None
    assert grace.grace_timing.slash is True
    assert grace.grace_timing.steal_following_percent == 25
    assert [pitch.semitone for pitch in grace.sounding_pitches] == [62, 74]
    assert [pitch.semitone for pitch in main.sounding_pitches] == [64, 76]
    assert validate_package(parse_musicxml_timeline_package(source)) == ()


def test_noncontrolling_measures_align_by_exact_score_time() -> None:
    """TEST-MXML-TEMPORAL-010: unequal barlines do not force ordinal alignment."""

    source = _partwise(
        '<part id="P1"><measure number="1"><attributes><divisions>1</divisions>'
        "</attributes><note><rest/><duration>4</duration><type>whole</type></note>"
        '</measure><measure number="2"><note><rest/><duration>4</duration>'
        "<type>whole</type></note></measure></part>"
        '<part id="P2"><measure number="1">'
        "<attributes><divisions>1</divisions></attributes><note><rest/>"
        "<duration>2</duration><type>half</type></note></measure>"
        '<measure number="1a" non-controlling="yes"><note><rest/>'
        "<duration>2</duration><type>half</type></note></measure>"
        '<measure number="2"><note><rest/><duration>4</duration>'
        "<type>whole</type></note></measure></part>",
        names=("P1", "P2"),
    )
    result = parse_musicxml_timeline(source)
    second_part = result.score.parts[1]
    assert [measure.score_onset for measure in second_part.measures] == [0, 2, 4]
    assert [measure.non_controlling for measure in second_part.measures] == [False, True, False]
    assert [(alignment.onset, alignment.measures) for alignment in result.score.alignments] == [
        (Fraction(0), (("P1", 1), ("P2", 1))),
        (Fraction(4), (("P1", 2), ("P2", 3))),
    ]
    assert validate_package(parse_musicxml_timeline_package(source)) == ()


def test_two_part_partwise_and_timewise_have_same_temporal_score() -> None:
    """TEST-MXML-TEMPORAL-012: form changes do not change musical structure."""

    part_list = (
        '<part-list><part-group type="start" number="1"><group-name>Keyboard</group-name>'
        '</part-group><score-part id="P1"><part-name>Upper</part-name></score-part>'
        '<score-part id="P2"><part-name>Lower</part-name></score-part>'
        '<part-group type="stop" number="1"/></part-list>'
    )
    upper_first = (
        "<attributes><divisions>1</divisions><staves>2</staves>"
        '<clef number="1"><sign>G</sign><line>2</line></clef>'
        '<clef number="2"><sign>F</sign><line>4</line></clef></attributes>'
        "<note><pitch><step>C</step><octave>4</octave></pitch><duration>1</duration>"
        "<voice>1</voice><type>quarter</type><staff>1</staff></note>"
        "<note><pitch><step>E</step><octave>3</octave></pitch><duration>1</duration>"
        "<voice>1</voice><type>quarter</type><staff>2</staff></note>"
    )
    lower_first = (
        "<attributes><divisions>1</divisions></attributes>"
        "<note><rest/><duration>2</duration><voice>5</voice><type>half</type></note>"
    )
    upper_second = "<note><rest/><duration>2</duration><type>half</type></note>"
    lower_second = (
        "<note><pitch><step>G</step><octave>3</octave></pitch><duration>2</duration>"
        "<voice>5</voice><type>half</type></note>"
    )

    def doctype(form: str) -> str:
        return (
            f'<!DOCTYPE score-{form} PUBLIC "-//Recordare//DTD MusicXML 4.0 '
            f'{"Partwise" if form == "partwise" else "Timewise"}//EN" '
            f'"http://www.musicxml.org/dtds/{form}.dtd">'
        )

    partwise = (
        doctype("partwise")
        + '<score-partwise version="4.0">'
        + part_list
        + f'<part id="P1"><measure number="1">{upper_first}</measure>'
        + f'<measure number="2">{upper_second}</measure></part>'
        + f'<part id="P2"><measure number="1">{lower_first}</measure>'
        + f'<measure number="2">{lower_second}</measure></part></score-partwise>'
    ).encode()
    timewise = (
        doctype("timewise")
        + '<score-timewise version="4.0">'
        + part_list
        + f'<measure number="1"><part id="P1">{upper_first}</part>'
        + f'<part id="P2">{lower_first}</part></measure>'
        + f'<measure number="2"><part id="P1">{upper_second}</part>'
        + f'<part id="P2">{lower_second}</part></measure></score-timewise>'
    ).encode()
    partwise_score = parse_musicxml_timeline(partwise).score
    timewise_score = parse_musicxml_timeline(timewise).score
    assert partwise_score == timewise_score
    assert len(partwise_score.groups) == 2
    assert [staff.source_number for staff in partwise_score.parts[0].staves] == ["1", "2"]
    assert [event.staff for event in partwise_score.parts[0].measures[0].events] == ["1", "2"]
    assert [
        (alignment.onset, len(alignment.measures)) for alignment in partwise_score.alignments
    ] == [(Fraction(0), 2), (Fraction(2), 2)]
    assert validate_package(parse_musicxml_timeline_package(partwise)) == ()
    assert validate_package(parse_musicxml_timeline_package(timewise)) == ()


def test_temporal_json_rejects_unknown_and_inconsistent_fields() -> None:
    """TEST-MXML-TEMPORAL-011: strict decoding and temporal invariants fail closed."""

    source, name = _fixture("TMM-REF-CANDIDATE-001-Hot-Cross-Buns")
    original = package_to_dict(parse_musicxml_timeline_package(source, logical_name=name))
    modified = deepcopy(original)
    score = modified["documents"][0]["content"]["score"]
    score["parts"][0]["measures"][0]["events"][0]["extra"] = 1
    with pytest.raises(CanonicalSerializationError, match="unexpected"):
        package_from_dict(modified)

    modified = deepcopy(original)
    event = modified["documents"][0]["content"]["score"]["parts"][0]["measures"][0]["events"][0]
    event["score_onset"]["numerator"] = 99
    with pytest.raises(CanonicalSerializationError, match="TEMPORAL_EVENT_SCORE_TIME"):
        package_from_dict(modified)

    modified = deepcopy(original)
    event = modified["documents"][0]["content"]["score"]["parts"][0]["measures"][0]["events"][0]
    event["duration"]["denominator"] = 2
    with pytest.raises(CanonicalSerializationError, match="rational must be reduced"):
        package_from_dict(modified)
