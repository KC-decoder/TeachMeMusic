"""Independent semantic-equivalence evidence for governed score fixtures."""

from __future__ import annotations

from dataclasses import replace
from fractions import Fraction
from pathlib import Path

import pytest

from teachmemusic.score.musicxml.standards import resource_root
from teachmemusic.score.parser import (
    parse_musicxml_auxiliary,
    parse_musicxml_timeline,
    parse_musicxml_timeline_package,
)

from .semantic_oracle import (
    OracleSemanticRecord,
    OracleValue,
    canonical_auxiliary_oracle,
    canonical_oracle,
    canonical_package_oracle,
    source_auxiliary_oracle,
    source_oracle,
    source_package_oracle,
)

FIXTURES = (
    "TMM-REF-CANDIDATE-001-Hot-Cross-Buns",
    "TMM-REF-CANDIDATE-002-Happy-Birthday",
    "TMM-REF-CANDIDATE-003-Clair-de-Lune",
    "TMM-REF-CANDIDATE-004-Moonlight-Sonata",
    "TMM-REF-CANDIDATE-005-Deux-Arabesques",
)


def _fixture(directory: str) -> bytes:
    path = next((Path("tests/fixtures/scores") / directory).glob("*.mxl"))
    return path.read_bytes()


def _figured_bass_score() -> bytes:
    return (
        b'<?xml version="1.0" encoding="utf-8"?>'
        b'<score-partwise version="4.0"><part-list>'
        b'<score-part id="P1"><part-name>Piano</part-name></score-part>'
        b'</part-list><part id="P1"><measure number="1">'
        b"<attributes><divisions>2</divisions></attributes>"
        b'<figured-bass parentheses="yes" print-object="no" print-dot="yes" '
        b'print-spacing="no" placement="above" id="bass-1">'
        b"<figure><prefix>sharp</prefix><figure-number>6</figure-number>"
        b'<suffix>natural</suffix><extend type="start"/></figure>'
        b'<figure><figure-number>4</figure-number><extend type="continue"/></figure>'
        b'<figure><figure-number>3</figure-number><extend type="stop"/></figure>'
        b"<duration>3</duration></figured-bass>"
        b"<note><pitch><step>C</step><octave>4</octave></pitch><duration>2</duration>"
        b"<type>quarter</type></note></measure></part></score-partwise>"
    )


def _linked_score() -> bytes:
    return b"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE score-partwise PUBLIC "-//Recordare//DTD MusicXML 4.0 Partwise//EN"
  "http://www.musicxml.org/dtds/partwise.dtd">
<score-partwise version="4.0" xmlns:xlink="http://www.w3.org/1999/xlink">
  <work><work-title>Linked</work-title><opus xlink:href="collection.xml"/></work>
  <credit page="1">
    <link xlink:href="https://example.test/credit" name="credit-link"/>
    <bookmark id="credit-target" name="Credit"/>
    <credit-words>Linked score</credit-words>
  </credit>
  <part-list>
    <score-part id="P1">
      <part-link xlink:href="parts/piano.musicxml">
        <instrument-link id="P1-I1"/><group-link>score</group-link>
      </part-link>
      <part-name>Piano</part-name>
      <score-instrument id="P1-I1"><instrument-name>Piano</instrument-name></score-instrument>
    </score-part>
  </part-list>
  <part id="P1"><measure number="1">
    <link xlink:href="#credit-target" element="credit" position="1"/>
    <bookmark id="measure-target" name="Measure"/>
  </measure></part>
</score-partwise>"""


def _opus(version: str) -> bytes:
    public_version = "4.1" if version == "4.1-draft" else version
    version_attribute = "" if version in {"1.0", "1.1"} else f' version="{public_version}"'
    return (
        '<?xml version="1.0"?>'
        f'<!DOCTYPE opus PUBLIC "-//Recordare//DTD MusicXML {public_version} Opus//EN" '
        '"http://www.musicxml.org/dtds/opus.dtd">'
        f"<opus{version_attribute}><title>Collection</title></opus>"
    ).encode()


def _nested_opus() -> bytes:
    return b"""<?xml version="1.0"?>
<!DOCTYPE opus PUBLIC "-//Recordare//DTD MusicXML 4.0 Opus//EN"
  "http://www.musicxml.org/dtds/opus.dtd">
<opus version="4.0" xmlns:xlink="http://www.w3.org/1999/xlink">
  <title>Collection</title>
  <score xlink:href="one.musicxml" new-page="yes"/>
  <opus><title>Nested</title><opus-link xlink:href="nested.xml"/></opus>
</opus>"""


@pytest.mark.parametrize("directory", FIXTURES)
def test_independent_temporal_oracle_matches_canonical_score(directory: str) -> None:
    """TEST-MXML-EQUIVALENCE-001: bounded independent semantic slices agree."""

    source = _fixture(directory)
    expected = source_oracle(source)
    actual = canonical_oracle(parse_musicxml_timeline(source))
    assert actual == expected


def _fact(record: OracleSemanticRecord, name: str) -> OracleValue:
    return dict(record.facts)[name]


def _replace_fact(
    record: OracleSemanticRecord, name: str, value: OracleValue
) -> OracleSemanticRecord:
    return replace(
        record,
        facts=tuple((key, value if key == name else current) for key, current in record.facts),
    )


def test_metadata_oracle_preserves_empty_absent_and_ordered_values() -> None:
    """TEST-MXML-EQUIVALENCE-002: metadata source states and order are observable."""

    source = _fixture("TMM-REF-CANDIDATE-001-Hot-Cross-Buns")
    expected = source_oracle(source)
    actual = canonical_oracle(parse_musicxml_timeline(source))
    part_header = next(item for item in actual.metadata if item.kind == "part-header")
    assert _fact(part_header, "name") == ""
    assert _fact(part_header, "abbreviation") is None

    absent_name = _replace_fact(part_header, "name", None)
    replaced = tuple(absent_name if item == part_header else item for item in actual.metadata)
    assert replace(actual, metadata=replaced) != expected

    identification = next(
        item
        for item in actual.metadata
        if item.scope == ("score",) and item.kind == "identification"
    )
    miscellaneous = _fact(identification, "miscellaneous")
    assert isinstance(miscellaneous, tuple) and len(miscellaneous) == 2
    reordered = _replace_fact(identification, "miscellaneous", tuple(reversed(miscellaneous)))
    replaced = tuple(reordered if item == identification else item for item in actual.metadata)
    assert replace(actual, metadata=replaced) != expected


def test_attribute_oracle_detects_state_identity_and_order_mutations() -> None:
    """TEST-MXML-EQUIVALENCE-003: attribute state, identity, and order are observable."""

    source = _fixture("TMM-REF-CANDIDATE-001-Hot-Cross-Buns")
    expected = source_oracle(source)
    actual = canonical_oracle(parse_musicxml_timeline(source))
    attribute = actual.attributes[0]
    clefs = _fact(attribute, "clefs")
    assert isinstance(clefs, tuple) and len(clefs) == 1
    clef = clefs[0]
    assert isinstance(clef, tuple)
    assert clef[7] is None and clef[8] is None
    explicit_and_identified = (*clef[:7], True, "clef-id")
    mutated_attribute = _replace_fact(attribute, "clefs", (explicit_and_identified,))
    assert replace(actual, attributes=(mutated_attribute,)) != expected

    complex_source = _fixture("TMM-REF-CANDIDATE-003-Clair-de-Lune")
    complex_expected = source_oracle(complex_source)
    complex_actual = canonical_oracle(parse_musicxml_timeline(complex_source))
    assert len(complex_actual.attributes) > 1
    reordered_attributes = (
        complex_actual.attributes[1],
        complex_actual.attributes[0],
        *complex_actual.attributes[2:],
    )
    assert replace(complex_actual, attributes=reordered_attributes) != complex_expected


def test_barline_oracle_detects_empty_navigation_and_style_mutations() -> None:
    """TEST-MXML-EQUIVALENCE-004: barline text, navigation, and style are observable."""

    source = _fixture("TMM-REF-CANDIDATE-004-Moonlight-Sonata")
    expected = source_oracle(source)
    actual = canonical_oracle(parse_musicxml_timeline(source))
    empty_ending = next(item for item in actual.barlines if _fact(item, "ending_text") == "")
    collapsed = _replace_fact(empty_ending, "ending_text", None)
    replaced = tuple(collapsed if item == empty_ending else item for item in actual.barlines)
    assert replace(actual, barlines=replaced) != expected

    first = actual.barlines[0]
    changed_style = _replace_fact(first, "style", "dashed")
    changed_navigation = _replace_fact(
        changed_style, "navigation", (("segno", "segno-1", "nav-id", None),)
    )
    replaced = (changed_navigation, *actual.barlines[1:])
    assert replace(actual, barlines=replaced) != expected


def test_span_endpoint_oracle_detects_anchor_identity_and_order_mutations() -> None:
    """TEST-MXML-EQUIVALENCE-005: note-span anchors, identity, and order are observable."""

    source = _fixture("TMM-REF-CANDIDATE-004-Moonlight-Sonata")
    expected = source_oracle(source)
    actual = canonical_oracle(parse_musicxml_timeline(source))
    endpoint = actual.span_endpoints[0]
    anchor = _fact(endpoint, "anchor")
    assert isinstance(anchor, tuple)
    changed_anchor = (*anchor[:2], "mutated-event-id", *anchor[3:])
    changed_endpoint = _replace_fact(endpoint, "anchor", changed_anchor)
    changed_endpoint = _replace_fact(changed_endpoint, "source_id", "mutated-span-id")
    replaced = (changed_endpoint, *actual.span_endpoints[1:])
    assert replace(actual, span_endpoints=replaced) != expected

    reordered = (
        actual.span_endpoints[1],
        actual.span_endpoints[0],
        *actual.span_endpoints[2:],
    )
    assert replace(actual, span_endpoints=reordered) != expected


def test_event_mark_oracle_detects_semantic_and_source_state_mutations() -> None:
    """TEST-MXML-EQUIVALENCE-006: note-attached notation distinctions are observable."""

    source = _fixture("TMM-REF-CANDIDATE-005-Deux-Arabesques")
    expected = source_oracle(source)
    actual = canonical_oracle(parse_musicxml_timeline(source))
    mark = actual.event_marks[0]
    changed = _replace_fact(mark, "placement", "above")
    changed = _replace_fact(changed, "group_id", "mutated-group-id")
    changed = _replace_fact(changed, "mark_kind", "accent")
    replaced = (changed, *actual.event_marks[1:])
    assert replace(actual, event_marks=replaced) != expected


def test_direction_oracle_detects_component_and_time_span_mutations() -> None:
    """TEST-MXML-EQUIVALENCE-007: direction and time-span source facts are observable."""

    source = _fixture("TMM-REF-CANDIDATE-004-Moonlight-Sonata")
    expected = source_oracle(source)
    actual = canonical_oracle(parse_musicxml_timeline(source))
    direction = actual.directions[0]
    changed_direction = _replace_fact(direction, "component_order", 999)
    changed_direction = _replace_fact(changed_direction, "direction_id", "direction-id")
    replaced_directions = (changed_direction, *actual.directions[1:])
    assert replace(actual, directions=replaced_directions) != expected

    pedal = next(
        item
        for item in actual.time_span_endpoints
        if _fact(item, "span_kind") == "pedal" and _fact(item, "action") == "start"
    )
    assert _fact(pedal, "pedal_line") is True
    changed_pedal = _replace_fact(pedal, "pedal_line", None)
    changed_pedal = _replace_fact(changed_pedal, "source_id", "pedal-endpoint-id")
    replaced_spans = tuple(
        changed_pedal if item == pedal else item for item in actual.time_span_endpoints
    )
    assert replace(actual, time_span_endpoints=replaced_spans) != expected


def test_resolved_notation_topology_detects_endpoint_order_mutation() -> None:
    """TEST-MXML-EQUIVALENCE-008: independently resolved note-span topology is exact."""

    source = _fixture("TMM-REF-CANDIDATE-003-Clair-de-Lune")
    expected = source_oracle(source)
    actual = canonical_oracle(parse_musicxml_timeline(source))
    span = next(
        item
        for item in actual.notation_spans
        if isinstance(_fact(item, "endpoints"), tuple) and len(_fact(item, "endpoints")) > 1  # type: ignore[arg-type]
    )
    endpoints = _fact(span, "endpoints")
    assert isinstance(endpoints, tuple)
    reversed_span = _replace_fact(span, "endpoints", tuple(reversed(endpoints)))
    replaced = tuple(reversed_span if item == span else item for item in actual.notation_spans)
    assert replace(actual, notation_spans=replaced) != expected


def test_resolved_time_topology_detects_recovery_provenance_mutation() -> None:
    """TEST-MXML-EQUIVALENCE-009: inferred span recovery remains explicit and observable."""

    source = _fixture("TMM-REF-CANDIDATE-004-Moonlight-Sonata")
    expected = source_oracle(source)
    actual = canonical_oracle(parse_musicxml_timeline(source))
    recovered = next(
        item
        for item in actual.time_spans
        if any(endpoint[-2] is True for endpoint in _fact(item, "endpoints"))  # type: ignore[union-attr]
    )
    endpoints = _fact(recovered, "endpoints")
    assert isinstance(endpoints, tuple)
    assert sum(endpoint[-2] is True for endpoint in endpoints) == 1
    mutated_endpoints = tuple(
        (*endpoint[:-1], "mutated-recovery-reason") if endpoint[-2] is True else endpoint
        for endpoint in endpoints
    )
    mutated = _replace_fact(recovered, "endpoints", mutated_endpoints)
    replaced = tuple(mutated if item == recovered else item for item in actual.time_spans)
    assert replace(actual, time_spans=replaced) != expected


def test_lyric_oracle_detects_segment_and_source_order_mutations() -> None:
    """TEST-MXML-EQUIVALENCE-010: lyric content, order, and source states are exact."""

    source = _fixture("TMM-REF-CANDIDATE-001-Hot-Cross-Buns")
    expected = source_oracle(source)
    actual = canonical_oracle(parse_musicxml_timeline(source))
    assert len(actual.lyrics) == 34
    lyric = actual.lyrics[0]
    segments = _fact(lyric, "segments")
    assert isinstance(segments, tuple) and segments
    first = segments[0]
    assert isinstance(first, tuple)
    changed = _replace_fact(lyric, "segments", ((*first[:1], "middle", *first[2:]),))
    changed = _replace_fact(changed, "source_order", 99)
    assert replace(actual, lyrics=(changed, *actual.lyrics[1:])) != expected


def test_harmony_oracle_detects_chord_and_print_state_mutations() -> None:
    """TEST-MXML-EQUIVALENCE-011: harmony meaning and source controls are exact."""

    source = _fixture("TMM-REF-CANDIDATE-002-Happy-Birthday")
    expected = source_oracle(source)
    actual = canonical_oracle(parse_musicxml_timeline(source))
    assert len(actual.harmonies) == 3
    harmony = actual.harmonies[1]
    assert _fact(harmony, "harmony_kind") == "dominant"
    changed = _replace_fact(harmony, "harmony_kind", "major")
    changed = _replace_fact(changed, "print_frame", True)
    replaced = tuple(changed if item == harmony else item for item in actual.harmonies)
    assert replace(actual, harmonies=replaced) != expected


def test_figured_bass_oracle_matches_positive_semantics_and_detects_mutation() -> None:
    """TEST-MXML-EQUIVALENCE-012: figured-bass semantics have positive evidence."""

    source = _figured_bass_score()
    expected = source_oracle(source)
    actual = canonical_oracle(parse_musicxml_timeline(source))
    assert actual == expected
    assert len(actual.figured_bass) == 1
    bass = actual.figured_bass[0]
    assert _fact(bass, "duration") == Fraction(3, 2)
    changed = _replace_fact(bass, "print_spacing", True)
    assert replace(actual, figured_bass=(changed,)) != expected


def test_layout_and_presentation_oracle_detects_exact_value_mutations() -> None:
    """TEST-MXML-EQUIVALENCE-013: layout and presentation values are observable."""

    source = _fixture("TMM-REF-CANDIDATE-002-Happy-Birthday")
    expected = source_oracle(source)
    actual = canonical_oracle(parse_musicxml_timeline(source))
    assert len(actual.layouts) == 9
    measure_layout = actual.layouts[1]
    assert _fact(measure_layout, "width") == Fraction(5249, 20)
    changed_layout = _replace_fact(measure_layout, "width", Fraction(999))
    assert (
        replace(actual, layouts=(actual.layouts[0], changed_layout, *actual.layouts[2:]))
        != expected
    )

    styled_source = _fixture("TMM-REF-CANDIDATE-001-Hot-Cross-Buns")
    styled_expected = source_oracle(styled_source)
    styled_actual = canonical_oracle(parse_musicxml_timeline(styled_source))
    assert len(styled_actual.presentations) == 57
    presentation = styled_actual.presentations[0]
    style = _fact(presentation, "style")
    assert isinstance(style, tuple)
    changed_style = (*style[:4], "#FF0000", *style[5:])
    changed_presentation = _replace_fact(presentation, "style", changed_style)
    assert (
        replace(
            styled_actual,
            presentations=(changed_presentation, *styled_actual.presentations[1:]),
        )
        != styled_expected
    )


def test_playback_oracle_detects_midi_sound_and_note_state_mutations() -> None:
    """TEST-MXML-EQUIVALENCE-014: represented playback state is independently exact."""

    source = _fixture("TMM-REF-CANDIDATE-001-Hot-Cross-Buns")
    expected = source_oracle(source)
    actual = canonical_oracle(parse_musicxml_timeline(source))
    part = actual.playback[0]
    instruments = _fact(part, "instruments")
    assert isinstance(instruments, tuple)
    assert instruments[0][1] == ""  # type: ignore[index]
    missing_empty_name = _replace_fact(
        part,
        "instruments",
        ((*instruments[0][:1], None, *instruments[0][2:]),),  # type: ignore[index]
    )
    assert replace(actual, playback=(missing_empty_name, *actual.playback[1:])) != expected

    sound = next(item for item in actual.playback if item.kind == "sound")
    changed_sound = _replace_fact(sound, "tempo", Fraction(120))
    replaced_playback = tuple(changed_sound if item == sound else item for item in actual.playback)
    assert replace(actual, playback=replaced_playback) != expected

    note = next(item for item in actual.playback if item.kind == "note-playback")
    changed_note = _replace_fact(note, "dynamics", Fraction(75))
    replaced_playback = tuple(changed_note if item == note else item for item in actual.playback)
    assert replace(actual, playback=replaced_playback) != expected


def test_link_oracle_matches_positive_resource_graph_and_detects_mutation() -> None:
    """TEST-MXML-EQUIVALENCE-015: links, bookmarks, and linked parts are exact."""

    source = _linked_score()
    expected = source_oracle(source)
    actual = canonical_oracle(parse_musicxml_timeline(source))
    assert actual == expected
    assert len(actual.links) == 6
    work_opus = actual.links[0]
    link = _fact(work_opus, "link")
    assert isinstance(link, tuple) and link[0] == "collection.xml"
    changed_link = ("changed.xml", *link[1:])
    changed_opus = _replace_fact(work_opus, "link", changed_link)
    assert replace(actual, links=(changed_opus, *actual.links[1:])) != expected

    credit_link = actual.links[1]
    changed_order = _replace_fact(credit_link, "source_order", 99)
    assert (
        replace(
            actual,
            links=(actual.links[0], changed_order, *actual.links[2:]),
        )
        != expected
    )


@pytest.mark.parametrize("directory", FIXTURES)
def test_provenance_and_existing_temporal_package_facts_match_source(directory: str) -> None:
    """TEST-MXML-EQUIVALENCE-016: source identity and partial-package facts are exact."""

    fixture_path = next((Path("tests/fixtures/scores") / directory).glob("*.mxl"))
    source = fixture_path.read_bytes()
    expected = source_package_oracle(source, fixture_path.name)
    actual = canonical_package_oracle(
        parse_musicxml_timeline_package(source, logical_name=fixture_path.name)
    )
    assert actual == expected
    assert actual.completeness == "temporal-only"

    changed_source = (*actual.source[:-1], ("explicit-value", "score-timewise"))
    assert replace(actual, source=changed_source) != expected
    assert replace(actual, package_id=("package", "package:mutated")) != expected


@pytest.mark.parametrize(
    "version",
    ("1.0", "1.1", "2.0", "3.0", "3.1", "4.0", "4.1-draft"),
)
def test_opus_auxiliary_semantics_match_independent_source(version: str) -> None:
    """TEST-MXML-EQUIVALENCE-017: opus version and recursive content are exact."""

    source = _opus(version)
    expected = source_auxiliary_oracle(source)
    actual = canonical_auxiliary_oracle(parse_musicxml_auxiliary(source))
    assert actual == expected

    if version == "4.0":
        nested_source = _nested_opus()
        nested_expected = source_auxiliary_oracle(nested_source)
        nested_actual = canonical_auxiliary_oracle(parse_musicxml_auxiliary(nested_source))
        assert nested_actual == nested_expected
        first = nested_actual.items[0]
        assert isinstance(first, tuple)
        changed_first = (*first[:2], False, *first[3:])
        assert (
            replace(nested_actual, items=(changed_first, *nested_actual.items[1:]))
            != nested_expected
        )


@pytest.mark.parametrize(
    ("version", "expected_entries"),
    (("3.0", 886), ("3.1", 886), ("4.0", 894), ("4.1-draft", 908)),
)
def test_sound_catalog_semantics_match_independent_source(
    version: str, expected_entries: int
) -> None:
    """TEST-MXML-EQUIVALENCE-018: every pinned sound-catalog row is exact."""

    path = resource_root() / version / "schema" / "sounds.xml"
    source = path.read_bytes()
    expected = source_auxiliary_oracle(source)
    actual = canonical_auxiliary_oracle(parse_musicxml_auxiliary(source, logical_name=path.name))
    assert actual == expected
    assert len(actual.items) == expected_entries

    first = actual.items[0]
    assert isinstance(first, tuple)
    changed_first = (*first[:1], not first[1], *first[2:])
    assert replace(actual, items=(changed_first, *actual.items[1:])) != expected


def test_oracle_detects_a_semantic_pitch_mutation() -> None:
    """TEST-MXML-MUTATION-001: an altered canonical pitch cannot compare equal."""

    source = _fixture("TMM-REF-CANDIDATE-001-Hot-Cross-Buns")
    expected = source_oracle(source)
    actual = canonical_oracle(parse_musicxml_timeline(source))
    first = actual.events[0]
    changed_pitch = ("C", first.pitch[1], first.pitch[2]) if first.pitch is not None else None
    mutated = replace(actual, events=(replace(first, pitch=changed_pitch), *actual.events[1:]))
    assert mutated != expected
