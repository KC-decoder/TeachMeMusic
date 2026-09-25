"""Task 7I generated, mutation, and differential conformance evidence."""

from __future__ import annotations

from dataclasses import replace
from fractions import Fraction
from pathlib import Path

import pytest
from lxml import etree

from teachmemusic.score.musicxml.diagnostics import MusicXmlBoundaryError
from teachmemusic.score.musicxml.standards import resource_root
from teachmemusic.score.parser import parse_musicxml_timeline
from teachmemusic.score.v2.temporal_validation import validate_temporal_score

from .semantic_oracle import _root_xml, canonical_oracle, source_oracle


def _score(body: str, *, divisions: int) -> bytes:
    return (
        '<score-partwise version="4.0"><part-list><score-part id="P1">'
        "<part-name>Generated</part-name></score-part></part-list>"
        f'<part id="P1"><measure number="1"><attributes><divisions>{divisions}'
        f"</divisions></attributes>{body}</measure></part></score-partwise>"
    ).encode()


@pytest.mark.parametrize("divisions", (1, 2, 3, 7, 480))
@pytest.mark.parametrize("duration", (1, 2, 5, 11))
def test_generated_exact_timing_matches_independent_oracle(divisions: int, duration: int) -> None:
    """TEST-MXML-PROPERTY-001: rational timing holds across source units."""

    source = _score(
        "<note><pitch><step>F</step><alter>-0.5</alter><octave>4</octave></pitch>"
        f"<duration>{duration}</duration><voice>7</voice><type>quarter</type>"
        "<staff>2</staff></note>",
        divisions=divisions,
    )
    expected = Fraction(duration, divisions)
    result = parse_musicxml_timeline(source)

    assert result.score.parts[0].measures[0].events[0].duration == expected
    assert canonical_oracle(result) == source_oracle(source)


@pytest.mark.parametrize("chord_size", (2, 3, 5, 8))
def test_generated_chords_preserve_one_onset_and_identity(chord_size: int) -> None:
    """TEST-MXML-PROPERTY-002: generated chord sizes retain shared identity."""

    notes = []
    for index in range(chord_size):
        chord = "<chord/>" if index else ""
        notes.append(
            f"<note>{chord}<pitch><step>C</step><alter>{index}</alter>"
            f"<octave>4</octave></pitch><duration>3</duration><voice>{index + 1}</voice>"
            f"<type>quarter</type><staff>{1 + index % 2}</staff></note>"
        )
    source = _score("".join(notes), divisions=3)
    result = parse_musicxml_timeline(source)
    events = result.score.parts[0].measures[0].events

    assert {event.onset for event in events} == {Fraction(0)}
    assert len({event.chord_id for event in events}) == 1
    assert canonical_oracle(result) == source_oracle(source)


@pytest.mark.parametrize("cursor", ("<forward/>", "<backup><duration>0</duration></backup>"))
def test_invalid_cursor_mutations_fail_at_the_boundary(cursor: str) -> None:
    """TEST-MXML-PROPERTY-003: missing or non-positive cursor duration is invalid."""

    with pytest.raises(MusicXmlBoundaryError, match="MXML_XSD_INVALID"):
        parse_musicxml_timeline(_score(cursor, divisions=1))


def test_mutated_canonical_timing_and_identity_fail_validation() -> None:
    """TEST-MXML-MUTATION-002: invalid duration and duplicate IDs fail closed."""

    source = _score(
        "<note><pitch><step>C</step><octave>4</octave></pitch>"
        "<duration>1</duration><type>quarter</type></note>"
        "<note><pitch><step>D</step><octave>4</octave></pitch>"
        "<duration>1</duration><type>quarter</type></note>",
        divisions=1,
    )
    score = parse_musicxml_timeline(source).score
    part = score.parts[0]
    measure = part.measures[0]

    bad_duration = replace(measure.events[0], duration=Fraction(-1))
    duration_score = replace(
        score,
        parts=(
            replace(part, measures=(replace(measure, events=(bad_duration, *measure.events[1:])),)),
        ),
    )
    assert any(
        issue.code == "TEMPORAL_EVENT_TIME" for issue in validate_temporal_score(duration_score)
    )

    duplicate = replace(measure.events[1], id=measure.events[0].id)
    identity_score = replace(
        score,
        parts=(replace(part, measures=(replace(measure, events=(measure.events[0], duplicate)),)),),
    )
    assert any(
        issue.code == "TEMPORAL_EVENT_ID" for issue in validate_temporal_score(identity_score)
    )


@pytest.mark.parametrize(
    ("directory", "version"),
    (
        ("TMM-REF-CANDIDATE-001-Hot-Cross-Buns", "4.0"),
        ("TMM-REF-CANDIDATE-002-Happy-Birthday", "2.0"),
    ),
)
def test_official_partwise_to_timewise_transform_is_semantically_equivalent(
    directory: str, version: str
) -> None:
    """TEST-MXML-DIFFERENTIAL-001: official alternate form yields one timeline."""

    path = next((Path("tests/fixtures/scores") / directory).glob("*.mxl"))
    partwise = _root_xml(path.read_bytes())
    stylesheet = etree.XSLT(etree.parse(str(resource_root() / version / "schema/parttime.xsl")))
    timewise = bytes(stylesheet(etree.fromstring(partwise)))

    partwise_result = parse_musicxml_timeline(partwise)
    timewise_result = parse_musicxml_timeline(timewise)
    assert timewise_result.document_form == "score-timewise"
    partwise_source = source_oracle(partwise)
    timewise_source = source_oracle(timewise)
    assert timewise_source.provenance != partwise_source.provenance
    assert timewise_source.provenance.document_form == "score-timewise"
    assert timewise_source.provenance.source_sha256 != partwise_source.provenance.source_sha256
    assert replace(timewise_source, provenance=partwise_source.provenance) == partwise_source

    partwise_canonical = canonical_oracle(partwise_result)
    timewise_canonical = canonical_oracle(timewise_result)
    assert timewise_canonical.provenance != partwise_canonical.provenance
    assert (
        replace(timewise_canonical, provenance=partwise_canonical.provenance) == partwise_canonical
    )
