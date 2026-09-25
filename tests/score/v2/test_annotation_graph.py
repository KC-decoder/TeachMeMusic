"""Task 7G event-anchored notation-span evidence."""

from __future__ import annotations

import json
from copy import deepcopy
from fractions import Fraction
from pathlib import Path

import pytest

from teachmemusic.score.musicxml.temporal import TemporalMappingError
from teachmemusic.score.parser import parse_musicxml_timeline, parse_musicxml_timeline_package
from teachmemusic.score.v2.serialization import (
    CanonicalSerializationError,
    package_from_dict,
    package_from_json,
    package_to_dict,
    package_to_json,
)


def _partwise(
    body: str,
    *,
    version: str = "4.0",
    part_list: str | None = None,
    identification: str = "",
) -> bytes:
    public_version = "4.1" if version == "4.1-draft" else version
    version_attr = "" if version == "1.0" else f' version="{public_version}"'
    effective_part_list = part_list or (
        '<score-part id="P1"><part-name>Piano</part-name></score-part>'
    )
    return (
        '<?xml version="1.0" encoding="utf-8"?>'
        f'<!DOCTYPE score-partwise PUBLIC "-//Recordare//DTD MusicXML '
        f'{public_version} Partwise//EN" '
        '"http://www.musicxml.org/dtds/partwise.dtd">'
        f"<score-partwise{version_attr}>{identification}<part-list>"
        f"{effective_part_list}"
        "</part-list>"
        f'<part id="P1">{body}</part></score-partwise>'
    ).encode()


def _spanned_score() -> bytes:
    return _partwise(
        '<measure number="1"><attributes><divisions>1</divisions><staves>2</staves>'
        '<clef number="1"><sign>G</sign><line>2</line></clef>'
        '<clef number="2"><sign>F</sign><line>4</line></clef></attributes>'
        "<note><pitch><step>C</step><octave>4</octave></pitch><duration>1</duration>"
        '<tie type="start"/><voice>1</voice><type>quarter</type><staff>1</staff>'
        '<notations><tied type="start"/><slur number="1" type="start"/>'
        "</notations></note></measure>"
        '<measure number="2"><note><pitch><step>C</step><octave>4</octave></pitch>'
        '<duration>1</duration><tie type="stop"/><voice>2</voice><type>quarter</type>'
        '<staff>2</staff><notations><tied type="stop"/>'
        '<slur number="1" type="stop"/></notations></note></measure>'
    )


def _fixture(directory: str) -> bytes:
    path = next((Path("tests/fixtures/scores") / directory).glob("*.mxl"))
    return path.read_bytes()


def _enum_values(version: str, name: str) -> tuple[str, ...]:
    inventory = json.loads(
        Path("src/teachmemusic/score/musicxml/resources/inventory.json").read_text(encoding="utf-8")
    )
    type_paths = {
        component["path"]
        for component in inventory["components"]
        if component["version"] == version
        and component["kind"] == "xsd-simple-type"
        and component["name"] == name
        and component.get("source_file") == "schema/musicxml.xsd"
    }
    return tuple(
        component["attributes"]["value"]
        for component in inventory["components"]
        if component["version"] == version
        and component["kind"] == "xsd-enumeration"
        and any(component["path"].startswith(f"{path}/") for path in type_paths)
    )


def test_cross_measure_staff_voice_spans_round_trip() -> None:
    """TEST-MXML-ANNOTATION-001: distinct ties/slur retain anchored endpoints."""

    source = _spanned_score()
    result = parse_musicxml_timeline(source)
    spans = result.score.annotations.spans
    assert {span.kind for span in spans} == {"sounding-tie", "notated-tie", "slur"}
    assert all(
        [endpoint.action for endpoint in span.endpoints] == ["start", "stop"] for span in spans
    )
    assert all(
        [endpoint.anchor.staff for endpoint in span.endpoints] == ["1", "2"] for span in spans
    )
    assert all(
        [endpoint.anchor.voice for endpoint in span.endpoints] == ["1", "2"] for span in spans
    )
    assert all(
        [endpoint.anchor.score_onset for endpoint in span.endpoints] == [0, 1] for span in spans
    )
    assert not any(item.tag in {"tie", "tied", "slur"} for item in result.deferred)
    package = parse_musicxml_timeline_package(source)
    assert package_from_json(package_to_json(package)) == package


def test_unmatched_notation_span_fails_closed() -> None:
    """TEST-MXML-ANNOTATION-002: no partial score for dangling slur endpoints."""

    source = _partwise(
        '<measure number="1"><attributes><divisions>1</divisions></attributes>'
        "<note><pitch><step>C</step><octave>4</octave></pitch><duration>1</duration>"
        '<type>quarter</type><notations><slur type="start"/></notations>'
        "</note></measure>"
    )
    with pytest.raises(TemporalMappingError, match="unclosed notation spans"):
        parse_musicxml_timeline_package(source)


def test_musescore_2_adjacent_wedge_omissions_are_explicitly_recovered() -> None:
    """TEST-MXML-FIXTURE-002: two exact MuseScore 2.x wedge patterns recover."""

    source = _partwise(
        '<measure number="1"><attributes><divisions>1</divisions></attributes>'
        '<direction><direction-type><wedge number="1" type="crescendo"/>'
        "</direction-type><staff>1</staff></direction>"
        "<note><rest/><duration>2</duration><type>half</type></note>"
        '<direction><direction-type><wedge number="1" type="stop"/>'
        "</direction-type><staff>1</staff></direction>"
        '<direction><direction-type><wedge number="1" type="diminuendo"/>'
        "</direction-type><staff>1</staff></direction>"
        "<note><rest/><duration>2</duration><type>half</type></note></measure>"
        '<measure number="2">'
        '<direction><direction-type><wedge number="2" type="crescendo"/>'
        "</direction-type><staff>1</staff></direction>"
        "<note><rest/><duration>2</duration><type>half</type></note>"
        '<direction><direction-type><wedge number="3" type="diminuendo"/>'
        "</direction-type><staff>1</staff></direction>"
        "<note><rest/><duration>2</duration><type>half</type></note></measure>",
        version="3.1",
        identification=(
            "<identification><encoding><software>MuseScore 2.3.2</software>"
            "</encoding></identification>"
        ),
    )
    package = parse_musicxml_timeline_package(source)
    spans = package.documents[0].content.score.annotations.time_spans
    recovered = tuple(
        endpoint for span in spans for endpoint in span.endpoints if endpoint.inferred
    )
    assert len(spans) == 4
    assert [endpoint.anchor.onset for endpoint in recovered] == [4, 2, 4]
    assert [endpoint.anchor.measure_id for endpoint in recovered] == [
        "P1:m1",
        "P1:m2",
        "P1:m2",
    ]
    assert all(endpoint.source_type is None for endpoint in recovered)
    assert {endpoint.inference_reason for endpoint in recovered} == {
        "musescore-2-adjacent-wedge-recovery"
    }
    assert package_from_json(package_to_json(package)) == package


@pytest.mark.parametrize(
    ("software", "body"),
    (
        (
            "MuseScore 3.0",
            '<direction><direction-type><wedge number="1" type="crescendo"/>'
            "</direction-type><staff>1</staff></direction>"
            "<note><rest/><duration>2</duration><type>half</type></note>"
            '<direction><direction-type><wedge number="1" type="stop"/>'
            "</direction-type><staff>1</staff></direction>"
            '<direction><direction-type><wedge number="1" type="diminuendo"/>'
            "</direction-type><staff>1</staff></direction>"
            "<note><rest/><duration>2</duration><type>half</type></note>",
        ),
        (
            "MuseScore 2.3.2",
            '<direction><direction-type><wedge number="1" type="crescendo"/>'
            "</direction-type><staff>1</staff></direction>"
            "<note><rest/><duration>4</duration><type>whole</type></note>",
        ),
        (
            "MuseScore 2.3.2",
            '<direction><direction-type><wedge number="1" type="crescendo"/>'
            "</direction-type><staff>1</staff></direction>"
            "<note><rest/><duration>2</duration><type>half</type></note>"
            '<direction><direction-type><wedge number="2" type="crescendo"/>'
            "</direction-type><staff>1</staff></direction>"
            "<note><rest/><duration>2</duration><type>half</type></note>",
        ),
    ),
)
def test_wedge_recovery_rejects_other_exporters_and_shapes(software: str, body: str) -> None:
    """TEST-MXML-FIXTURE-003: recovery is exporter- and shape-bounded."""

    source = _partwise(
        '<measure number="1"><attributes><divisions>1</divisions></attributes>'
        + body
        + "</measure>",
        version="3.1",
        identification=(
            f"<identification><encoding><software>{software}</software></encoding></identification>"
        ),
    )
    with pytest.raises(TemporalMappingError, match="unclosed time spans"):
        parse_musicxml_timeline_package(source)


def test_sign_pedal_point_does_not_capture_a_line_span() -> None:
    """TEST-MXML-FIXTURE-004: sign-only releases and pedal lines stay distinct."""

    source = _partwise(
        '<measure number="1"><attributes><divisions>1</divisions><staves>2</staves>'
        '<clef number="1"><sign>G</sign><line>2</line></clef>'
        '<clef number="2"><sign>F</sign><line>4</line></clef></attributes>'
        "<note><rest/><duration>1</duration><type>quarter</type><staff>1</staff></note>"
        '<direction placement="above"><direction-type><pedal type="stop"/>'
        "</direction-type><staff>1</staff></direction><backup><duration>1</duration></backup>"
        '<direction placement="below"><direction-type><pedal type="start" line="yes"/>'
        "</direction-type><staff>2</staff></direction>"
        "<note><rest/><duration>1</duration><type>quarter</type><staff>2</staff></note>"
        '<direction placement="below"><direction-type><pedal type="stop" line="yes"/>'
        "</direction-type><staff>2</staff></direction></measure>",
        version="3.1",
    )
    package = parse_musicxml_timeline_package(source)
    graph = package.documents[0].content.score.annotations
    pedal_points = [direction for direction in graph.directions if direction.family == "pedal"]
    pedal_spans = [span for span in graph.time_spans if span.kind == "pedal"]
    assert len(pedal_points) == 1
    assert (
        pedal_points[0].value,
        pedal_points[0].anchor.staff,
        pedal_points[0].pedal_number,
        pedal_points[0].pedal_line,
        pedal_points[0].pedal_sign,
    ) == ("stop", "1", "1", None, None)
    assert len(pedal_spans) == 1
    assert [endpoint.anchor.staff for endpoint in pedal_spans[0].endpoints] == ["2", "2"]
    assert [endpoint.pedal_line for endpoint in pedal_spans[0].endpoints] == [True, True]
    assert package_from_json(package_to_json(package)) == package


def test_mixed_pedal_display_styles_keep_one_temporal_action() -> None:
    """TEST-MXML-FIXTURE-006: display changes do not split a pedal action."""

    source = _partwise(
        '<measure number="1"><attributes><divisions>1</divisions></attributes>'
        '<direction><direction-type><pedal type="start" line="no"/>'
        "</direction-type><staff>1</staff></direction>"
        "<note><rest/><duration>1</duration><type>quarter</type></note>"
        '<direction><direction-type><pedal type="stop" line="yes"/>'
        "</direction-type><staff>1</staff></direction></measure>",
        version="4.0",
    )
    package = parse_musicxml_timeline_package(source)
    graph = package.documents[0].content.score.annotations
    pedal_points = [direction for direction in graph.directions if direction.family == "pedal"]
    pedal_spans = [span for span in graph.time_spans if span.kind == "pedal"]
    assert [direction.value for direction in pedal_points] == ["start"]
    assert len(pedal_spans) == 1
    assert [endpoint.source_type for endpoint in pedal_spans[0].endpoints] == ["start", "stop"]
    assert [endpoint.pedal_line for endpoint in pedal_spans[0].endpoints] == [False, True]
    assert package_from_json(package_to_json(package)) == package


@pytest.mark.parametrize("software", ("MuseScore 2.3.2", "MuseScore 3.0"))
def test_musescore_2_source_only_wavy_stop_is_preserved(software: str) -> None:
    """TEST-MXML-FIXTURE-005: only MuseScore 2.x wavy stops may be singleton spans."""

    source = _partwise(
        '<measure number="1"><attributes><divisions>1</divisions></attributes>'
        "<note><pitch><step>C</step><octave>5</octave></pitch><duration>1</duration>"
        '<type>quarter</type><notations><ornaments><wavy-line type="stop" number="1"/>'
        "</ornaments></notations></note></measure>",
        version="3.1",
        identification=(
            f"<identification><encoding><software>{software}</software></encoding></identification>"
        ),
    )
    if software == "MuseScore 3.0":
        with pytest.raises(TemporalMappingError, match="span stop without start"):
            parse_musicxml_timeline_package(source)
        return
    package = parse_musicxml_timeline_package(source)
    spans = package.documents[0].content.score.annotations.spans
    assert len(spans) == 1
    assert spans[0].kind == "wavy-line"
    assert [endpoint.action for endpoint in spans[0].endpoints] == ["stop"]
    assert package_from_json(package_to_json(package)) == package


def test_unmatched_tie_is_preserved_without_blocking_a_later_tie() -> None:
    """TEST-MXML-CORPUS-011: incomplete ties remain explicit singletons."""

    def note(action: str) -> str:
        return (
            "<note><pitch><step>C</step><octave>5</octave></pitch><duration>1</duration>"
            f'<type>quarter</type><notations><tied type="{action}"/></notations></note>'
        )

    source = _partwise(
        '<measure number="1"><attributes><divisions>1</divisions></attributes>'
        + note("start")
        + "</measure>"
        + '<measure number="2">'
        + note("start")
        + "</measure>"
        + '<measure number="3">'
        + note("stop")
        + "</measure>"
    )
    spans = parse_musicxml_timeline(source).score.annotations.spans
    assert [[endpoint.action for endpoint in span.endpoints] for span in spans] == [
        ["start"],
        ["start", "stop"],
    ]


def test_tie_stop_precedes_restart_on_same_event() -> None:
    """TEST-MXML-CORPUS-012: a middle tied note closes then restarts a tie."""

    source = _partwise(
        '<measure number="1"><attributes><divisions>1</divisions></attributes>'
        "<note><pitch><step>F</step><octave>4</octave></pitch><duration>1</duration>"
        '<type>quarter</type><notations><tied type="start"/></notations></note>'
        "<note><pitch><step>F</step><octave>4</octave></pitch><duration>1</duration>"
        '<type>quarter</type><notations><tied type="start"/><tied type="stop"/>'
        "</notations></note>"
        "<note><pitch><step>F</step><octave>4</octave></pitch><duration>1</duration>"
        '<type>quarter</type><notations><tied type="stop"/></notations></note></measure>'
    )
    spans = parse_musicxml_timeline(source).score.annotations.spans
    assert len(spans) == 2
    assert all(
        [endpoint.action for endpoint in span.endpoints] == ["start", "stop"] for span in spans
    )


def test_enharmonic_cross_voice_tie_and_let_ring_are_preserved() -> None:
    """TEST-MXML-CORPUS-013: tie identity follows sounding pitch and tie form."""

    source = _partwise(
        '<measure number="1"><attributes><divisions>1</divisions></attributes>'
        "<note><pitch><step>A</step><alter>1</alter><octave>4</octave></pitch>"
        '<duration>1</duration><voice>1</voice><type>quarter</type><notations><tied type="start"/>'
        "</notations></note>"
        "<note><pitch><step>B</step><alter>-1</alter><octave>4</octave></pitch>"
        '<duration>1</duration><voice>2</voice><type>quarter</type><notations><tied type="stop"/>'
        "</notations></note>"
        "<note><pitch><step>G</step><octave>5</octave></pitch><duration>1</duration>"
        '<voice>1</voice><type>quarter</type><notations><tied type="let-ring"/>'
        "</notations></note></measure>"
    )
    spans = parse_musicxml_timeline(source).score.annotations.spans
    assert [[endpoint.action for endpoint in span.endpoints] for span in spans] == [
        ["start", "stop"],
        ["let-ring"],
    ]
    assert spans[0].endpoints[0].anchor.voice == "1"
    assert spans[0].endpoints[1].anchor.voice == "2"


def test_multistaff_stop_before_start_pairs_in_musical_order() -> None:
    """TEST-MXML-ANNOTATION-089: valid reverse document order resolves by action."""

    source = _partwise(
        '<measure number="1"><attributes><divisions>1</divisions><staves>2</staves>'
        '<clef number="1"><sign>G</sign><line>2</line></clef>'
        '<clef number="2"><sign>F</sign><line>4</line></clef></attributes>'
        '<direction><direction-type><pedal type="stop" line="yes"/></direction-type>'
        "<staff>1</staff></direction><direction><direction-type>"
        '<pedal type="start" line="yes"/></direction-type>'
        "<staff>2</staff></direction><note><pitch><step>C</step><octave>5</octave>"
        "</pitch><duration>1</duration><voice>1</voice><type>quarter</type><staff>1</staff>"
        '<notations><slur number="1" type="stop"/></notations></note><backup>'
        "<duration>1</duration></backup><note><pitch><step>C</step><octave>4</octave>"
        "</pitch><duration>1</duration><voice>2</voice><type>quarter</type><staff>2</staff>"
        '<notations><slur number="1" type="start"/></notations></note></measure>'
    )
    package = parse_musicxml_timeline_package(source)
    graph = package.documents[0].content.score.annotations
    assert [endpoint.action for endpoint in graph.spans[0].endpoints] == ["start", "stop"]
    assert [endpoint.anchor.voice for endpoint in graph.spans[0].endpoints] == ["2", "1"]
    assert [endpoint.action for endpoint in graph.time_spans[0].endpoints] == ["start", "stop"]
    assert [endpoint.anchor.staff for endpoint in graph.time_spans[0].endpoints] == ["2", "1"]
    assert package_from_json(package_to_json(package)) == package


def test_clair_de_lune_multistaff_spans_resolve_without_repair() -> None:
    """TEST-MXML-ANNOTATION-090: source-ordered stops pair with later starts."""

    package = parse_musicxml_timeline_package(
        _fixture("TMM-REF-CANDIDATE-003-Clair-de-Lune"),
        logical_name="clair-de-lune-debussy.mxl",
    )
    content = package.documents[0].content
    score = content.score
    assert len(score.parts) == 1
    assert len(score.parts[0].measures) == 72
    assert len(score.annotations.spans) == 380
    assert len(score.annotations.time_spans) == 129
    assert content.deferred == ()
    assert not any(item.tag in {"slur", "pedal"} for item in content.deferred)
    assert package_from_json(package_to_json(package)) == package


def test_note_position_color_and_font_style_round_trip() -> None:
    """TEST-MXML-PRESENTATION-001: initial shared note style remains exact."""

    source = _partwise(
        '<measure number="1"><attributes><divisions>1</divisions></attributes>'
        '<note default-x="10.5" relative-x="-1.25" color="#112233" '
        'font-style="italic" font-weight="bold"><pitch><step>C</step><octave>4</octave>'
        "</pitch><duration>1</duration><type>quarter</type></note></measure>"
    )
    package = parse_musicxml_timeline_package(source)
    style = package.documents[0].content.score.parts[0].measures[0].events[0].presentation
    assert style is not None
    assert (style.default_x, style.relative_x) == (Fraction(21, 2), Fraction(-5, 4))
    assert (style.default_y, style.relative_y) == (None, None)
    assert (style.color, style.font_style, style.font_weight) == (
        "#112233",
        "italic",
        "bold",
    )
    assert package_from_json(package_to_json(package)) == package

    modified = package_to_dict(package)
    modified["documents"][0]["content"]["score"]["parts"][0]["measures"][0]["events"][0][
        "presentation"
    ]["font_style"] = "oblique"
    with pytest.raises(CanonicalSerializationError, match="TEMPORAL_PRESENTATION"):
        package_from_dict(modified)


def test_direction_text_presentation_round_trip() -> None:
    """TEST-MXML-PRESENTATION-002: shared text styling remains exact."""

    source = _partwise(
        '<measure number="1"><attributes><divisions>1</divisions></attributes>'
        '<direction><direction-type><words default-x="10.5" relative-y="-2" '
        'color="#AABBCC" font-family="Bravura, serif" font-style="italic" '
        'font-size="12.5" font-weight="bold" justify="center" halign="right" '
        'valign="baseline" enclosure="rectangle" letter-spacing="-0.1" '
        'line-height="normal" underline="2" overline="1" line-through="3" '
        'rotation="-45" dir="rtl" xml:lang="fr" xml:space="preserve">'
        "Texte</words></direction-type></direction>"
        "<note><rest/><duration>1</duration><type>quarter</type></note></measure>"
    )
    package = parse_musicxml_timeline_package(source)
    direction = package.documents[0].content.score.annotations.directions[0]
    style = direction.presentation
    assert direction.value == "Texte"
    assert style is not None
    assert (style.default_x, style.relative_y) == (Fraction(21, 2), Fraction(-2))
    assert style.font_family == "Bravura, serif"
    assert style.font_size is not None
    assert (style.font_size.number, style.font_size.keyword) == (Fraction(25, 2), None)
    assert (style.justify, style.halign, style.valign) == ("center", "right", "baseline")
    assert style.letter_spacing is not None and style.line_height is not None
    assert (style.letter_spacing.number, style.letter_spacing.keyword) == (
        Fraction(-1, 10),
        None,
    )
    assert (style.line_height.number, style.line_height.keyword) == (None, "normal")
    assert (style.underline, style.overline, style.line_through) == (2, 1, 3)
    assert (style.rotation, style.text_direction) == (Fraction(-45), "rtl")
    assert (style.language, style.space) == ("fr", "preserve")
    assert package_from_json(package_to_json(package)) == package

    modified = package_to_dict(package)
    modified["documents"][0]["content"]["score"]["annotations"]["directions"][0]["presentation"][
        "enclosure"
    ] = "cloud"
    modified["documents"][0]["content"]["score"]["parts"][0]["measures"][0]["directions"][0][
        "presentation"
    ]["enclosure"] = "cloud"
    with pytest.raises(CanonicalSerializationError, match="ANNOTATION_DIRECTION"):
        package_from_dict(modified)


def test_annotation_json_rejects_tampered_anchor_and_marker() -> None:
    """TEST-MXML-ANNOTATION-003: graph and source markers must agree."""

    original = package_to_dict(parse_musicxml_timeline_package(_spanned_score()))
    modified = deepcopy(original)
    content = modified["documents"][0]["content"]
    content["score"]["annotations"]["spans"][0]["endpoints"][0]["anchor"]["event_id"] = "bogus"
    with pytest.raises(CanonicalSerializationError, match="ANNOTATION_SPAN_GRAPH"):
        package_from_dict(modified)

    modified = deepcopy(original)
    content = modified["documents"][0]["content"]
    content["score"]["parts"][0]["measures"][0]["events"][0]["span_markers"] = []
    with pytest.raises(CanonicalSerializationError, match="ANNOTATION_SPAN_STATE"):
        package_from_dict(modified)


def test_reference_lyrics_and_harmonies_are_typed() -> None:
    """TEST-MXML-ANNOTATION-004: real lyric and harmony facts enter the graph."""

    buns = parse_musicxml_timeline(_fixture("TMM-REF-CANDIDATE-001-Hot-Cross-Buns"))
    lyrics = buns.score.annotations.lyrics
    assert len(lyrics) == 34
    assert [(item.number, item.text) for item in lyrics[:2]] == [("1", "Hot"), ("2", "Mi")]
    assert all(item.anchor.event_id for item in lyrics)

    birthday = parse_musicxml_timeline(_fixture("TMM-REF-CANDIDATE-002-Happy-Birthday"))
    harmonies = birthday.score.annotations.harmonies
    assert len(harmonies) == 3
    assert [(item.root_step, item.kind, item.kind_text) for item in harmonies] == [
        ("C", "major", ""),
        ("G", "dominant", "7"),
        ("C", "major", ""),
    ]
    assert all(item.anchor.measure_id for item in harmonies)
    original = package_to_dict(
        parse_musicxml_timeline_package(_fixture("TMM-REF-CANDIDATE-002-Happy-Birthday"))
    )
    modified = deepcopy(original)
    modified["documents"][0]["content"]["score"]["parts"][0]["measures"][0]["harmonies"][0][
        "anchor"
    ]["measure_id"] = "wrong"
    with pytest.raises(CanonicalSerializationError, match="ANNOTATION_HARMONY"):
        package_from_dict(modified)


def test_overlapping_slur_numbers_are_scoped_by_voice() -> None:
    """TEST-MXML-ANNOTATION-005: concurrent same-number spans remain distinct."""

    source = _partwise(
        '<measure number="1"><attributes><divisions>1</divisions></attributes>'
        "<note><pitch><step>C</step><octave>4</octave></pitch><duration>1</duration>"
        '<voice>1</voice><type>quarter</type><notations><slur type="start"/>'
        "</notations></note>"
        "<note><pitch><step>D</step><octave>4</octave></pitch><duration>1</duration>"
        '<voice>1</voice><type>quarter</type><notations><slur type="stop"/>'
        "</notations></note>"
        "<backup><duration>2</duration></backup>"
        "<note><pitch><step>E</step><octave>4</octave></pitch><duration>1</duration>"
        '<voice>2</voice><type>quarter</type><notations><slur type="start"/>'
        "</notations></note>"
        "<note><pitch><step>F</step><octave>4</octave></pitch><duration>1</duration>"
        '<voice>2</voice><type>quarter</type><notations><slur type="stop"/>'
        "</notations></note></measure>"
    )
    spans = parse_musicxml_timeline(source).score.annotations.spans
    assert len(spans) == 2
    assert len({span.id for span in spans}) == 2
    assert {span.endpoints[0].anchor.voice for span in spans} == {"1", "2"}


def test_simple_harmony_has_exact_time_anchor() -> None:
    """TEST-MXML-ANNOTATION-006: a 4.0 chord symbol maps to a typed time anchor."""

    source = _partwise(
        '<measure number="1"><attributes><divisions>2</divisions></attributes>'
        "<note><rest/><duration>1</duration><type>eighth</type></note>"
        "<harmony><root><root-step>G</root-step></root>"
        '<kind text="7">dominant</kind><staff>1</staff></harmony>'
        "<note><rest/><duration>1</duration><type>eighth</type></note></measure>"
    )
    result = parse_musicxml_timeline(source)
    harmony = result.score.annotations.harmonies[0]
    assert harmony.root_step == "G"
    assert harmony.kind == "dominant"
    assert harmony.kind_text == "7"
    assert harmony.anchor.onset.numerator == 1
    assert harmony.anchor.onset.denominator == 2
    assert not any(item.tag == "harmony" for item in result.deferred)


def _marked_score() -> bytes:
    return _partwise(
        '<measure number="1"><attributes><divisions>2</divisions></attributes>'
        '<direction placement="above"><direction-type><words>Allegro</words>'
        "</direction-type><staff>1</staff></direction>"
        "<note><pitch><step>C</step><octave>4</octave></pitch><duration>2</duration>"
        '<type>quarter</type><notehead filled="yes" parentheses="no">diamond</notehead>'
        "<notations><articulations><staccato/></articulations>"
        "<ornaments><trill-mark/></ornaments>"
        "<technical><fingering>2</fingering></technical></notations></note>"
        '<direction placement="below"><direction-type><dynamics><mf/></dynamics>'
        "</direction-type><offset>-1</offset><staff>1</staff></direction>"
        "<direction><direction-type><rehearsal>A</rehearsal></direction-type></direction>"
        "<direction><direction-type><segno/></direction-type></direction>"
        "<note><rest/><duration>2</duration><type>quarter</type></note></measure>"
    )


def test_note_marks_and_directions_have_typed_anchors() -> None:
    """TEST-MXML-ANNOTATION-007: point notation retains exact note/time anchors."""

    source = _marked_score()
    result = parse_musicxml_timeline(source)
    graph = result.score.annotations
    assert [(mark.value, mark.filled, mark.parentheses) for mark in graph.noteheads] == [
        ("diamond", True, False)
    ]
    assert [(mark.family, mark.kind, mark.text) for mark in graph.event_marks] == [
        ("articulation", "staccato", None),
        ("ornament", "trill-mark", None),
        ("technical", "fingering", "2"),
    ]
    assert [mark.family for mark in graph.directions] == [
        "words",
        "dynamic",
        "rehearsal",
        "segno",
    ]
    assert [mark.value for mark in graph.directions] == ["Allegro", "mf", "A", ""]
    assert graph.directions[1].anchor.onset.numerator == 1
    assert graph.directions[1].anchor.onset.denominator == 2
    assert not any(
        item.tag in {"notehead", "articulations", "ornaments", "technical", "direction"}
        for item in result.deferred
    )
    package = parse_musicxml_timeline_package(source)
    assert package_from_json(package_to_json(package)) == package


def test_point_annotation_tampering_fails_closed() -> None:
    """TEST-MXML-ANNOTATION-008: marks and direction anchors are validated."""

    original = package_to_dict(parse_musicxml_timeline_package(_marked_score()))
    modified = deepcopy(original)
    score = modified["documents"][0]["content"]["score"]
    score["parts"][0]["measures"][0]["events"][0]["event_markers"][0]["family"] = "unknown"
    with pytest.raises(CanonicalSerializationError, match="ANNOTATION_EVENT_MARK"):
        package_from_dict(modified)

    modified = deepcopy(original)
    score = modified["documents"][0]["content"]["score"]
    score["parts"][0]["measures"][0]["directions"][0]["anchor"]["measure_id"] = "wrong"
    with pytest.raises(CanonicalSerializationError, match="ANNOTATION_DIRECTION"):
        package_from_dict(modified)


def test_figured_bass_attaches_to_following_regular_note() -> None:
    """TEST-MXML-ANNOTATION-009: simple figures retain order and exact duration."""

    source = _partwise(
        '<measure number="1"><attributes><divisions>2</divisions></attributes>'
        "<figured-bass><figure><prefix>sharp</prefix><figure-number>6</figure-number>"
        "<suffix>natural</suffix></figure><duration>2</duration></figured-bass>"
        "<note><pitch><step>C</step><octave>4</octave></pitch><duration>2</duration>"
        "<type>quarter</type></note></measure>"
    )
    result = parse_musicxml_timeline(source)
    bass = result.score.annotations.figured_bass[0]
    assert [(item.prefix, item.number, item.suffix) for item in bass.figures] == [
        ("sharp", "6", "natural")
    ]
    assert bass.anchor.event_id == result.score.parts[0].measures[0].events[0].id
    assert bass.duration == 1
    assert not any(item.tag == "figured-bass" for item in result.deferred)
    original = package_to_dict(parse_musicxml_timeline_package(source))
    modified = deepcopy(original)
    modified["documents"][0]["content"]["score"]["parts"][0]["measures"][0]["figured_bass"][0][
        "anchor"
    ]["event_id"] = "wrong"
    with pytest.raises(CanonicalSerializationError, match="ANNOTATION_FIGURED_BASS"):
        package_from_dict(modified)


def test_cross_measure_direction_spans() -> None:
    """TEST-MXML-ANNOTATION-010: wedges and octave shifts keep time anchors."""

    source = _partwise(
        '<measure number="1"><attributes><divisions>1</divisions></attributes>'
        '<direction><direction-type><wedge number="1" type="crescendo"/>'
        "</direction-type></direction>"
        '<direction><direction-type><octave-shift number="2" size="8" type="down"/>'
        "</direction-type></direction>"
        "<note><pitch><step>C</step><octave>4</octave></pitch><duration>1</duration>"
        "<type>quarter</type></note></measure>"
        '<measure number="2"><direction><direction-type><wedge number="1" type="stop"/>'
        "</direction-type></direction>"
        '<direction><direction-type><octave-shift number="2" size="8" type="stop"/>'
        "</direction-type></direction>"
        "<note><pitch><step>D</step><octave>4</octave></pitch><duration>1</duration>"
        "<type>quarter</type></note></measure>"
    )
    result = parse_musicxml_timeline(source)
    spans = result.score.annotations.time_spans
    assert {span.kind for span in spans} == {"wedge", "octave-shift"}
    assert {span.opening for span in spans} == {"crescendo", "down"}
    assert all([item.anchor.score_onset for item in span.endpoints] == [0, 1] for span in spans)
    assert package_from_json(package_to_json(parse_musicxml_timeline_package(source))) == (
        parse_musicxml_timeline_package(source)
    )


def test_time_span_without_start_fails_closed() -> None:
    """TEST-MXML-ANNOTATION-011: dangling direction span yields no package."""

    source = _partwise(
        '<measure number="1"><attributes><divisions>1</divisions></attributes>'
        '<direction><direction-type><wedge type="stop"/></direction-type></direction>'
        "<note><rest/><duration>1</duration><type>quarter</type></note></measure>"
    )
    with pytest.raises(TemporalMappingError, match="time-span stop without start"):
        parse_musicxml_timeline_package(source)


def test_other_printed_direction_spans_keep_ordered_endpoints() -> None:
    """TEST-MXML-ANNOTATION-012: dashes, brackets, and pedal stay distinct."""

    def directions(action: str) -> str:
        return "".join(
            f'<direction><direction-type><{kind} number="{index}" type="{action}"'
            + (' line-end="none"' if kind == "bracket" else "")
            + (' line="yes"' if kind == "pedal" else "")
            + "/></direction-type></direction>"
            for index, kind in enumerate(("dashes", "bracket", "pedal"), start=1)
        )

    source = _partwise(
        '<measure number="1"><attributes><divisions>1</divisions></attributes>'
        + directions("start")
        + "<note><rest/><duration>1</duration><type>quarter</type></note></measure>"
        + '<measure number="2">'
        + directions("continue")
        + "<note><rest/><duration>1</duration><type>quarter</type></note></measure>"
        + '<measure number="3">'
        + directions("stop")
        + "<note><rest/><duration>1</duration><type>quarter</type></note></measure>"
    )
    result = parse_musicxml_timeline(source)
    spans = result.score.annotations.time_spans
    assert {span.kind for span in spans} == {"dashes", "bracket", "pedal"}
    assert all(
        [endpoint.action for endpoint in span.endpoints] == ["start", "continue", "stop"]
        for span in spans
    )
    assert all(
        [endpoint.anchor.score_onset for endpoint in span.endpoints] == [0, 1, 2] for span in spans
    )


@pytest.mark.parametrize("version", ("1.0", "1.1", "2.0", "3.0", "3.1", "4.0", "4.1-draft"))
def test_notehead_shape_maps_across_pinned_versions(version: str) -> None:
    """TEST-MXML-ANNOTATION-013: native notehead fields survive all versions."""

    source = _partwise(
        '<measure number="1"><attributes><divisions>1</divisions></attributes>'
        "<note><pitch><step>C</step><octave>4</octave></pitch><duration>1</duration>"
        '<type>quarter</type><notehead filled="yes" parentheses="no">diamond</notehead>'
        "</note></measure>",
        version=version,
    )
    result = parse_musicxml_timeline(source)
    mark = result.score.annotations.noteheads[0]
    assert (mark.value, mark.filled, mark.parentheses, mark.text) == (
        "diamond",
        True,
        False,
        (),
    )
    assert not any(item.tag in {"notehead", "@filled", "@parentheses"} for item in result.deferred)


@pytest.mark.parametrize("version", ("3.0", "3.1", "4.0", "4.1-draft"))
def test_notehead_text_preserves_order_and_style(version: str) -> None:
    """TEST-MXML-ANNOTATION-014: educational notehead text and style stay typed."""

    source = _partwise(
        '<measure number="1"><attributes><divisions>1</divisions></attributes>'
        "<note><pitch><step>C</step><octave>4</octave></pitch><duration>1</duration>"
        "<type>quarter</type><notehead-text>"
        '<display-text font-style="italic">A</display-text>'
        "<accidental-text>sharp</accidental-text></notehead-text>"
        "</note></measure>",
        version=version,
    )
    result = parse_musicxml_timeline(source)
    mark = result.score.annotations.noteheads[0]
    assert mark.value is None
    assert [(segment.kind, segment.text) for segment in mark.text] == [
        ("display-text", "A"),
        ("accidental-text", "sharp"),
    ]
    assert result.deferred == ()
    assert any(
        item.element_name == "display-text" and item.style.font_style == "italic"
        for item in result.score.source_presentations
    )
    assert not any(
        item.tag in {"notehead-text", "display-text", "accidental-text"} for item in result.deferred
    )
    package = parse_musicxml_timeline_package(source)
    assert package_from_json(package_to_json(package)) == package


def test_notehead_text_tampering_fails_closed() -> None:
    """TEST-MXML-ANNOTATION-015: invalid notehead text cannot enter v2."""

    source = _partwise(
        '<measure number="1"><attributes><divisions>1</divisions></attributes>'
        "<note><pitch><step>C</step><octave>4</octave></pitch><duration>1</duration>"
        "<type>quarter</type><notehead-text><display-text>A</display-text>"
        "</notehead-text></note></measure>"
    )
    original = package_to_dict(parse_musicxml_timeline_package(source))
    modified = deepcopy(original)
    marker = modified["documents"][0]["content"]["score"]["parts"][0]["measures"][0]["events"][0][
        "notehead_marker"
    ]
    marker["text"][0]["kind"] = "unrecognized"
    with pytest.raises(CanonicalSerializationError, match="ANNOTATION_NOTEHEAD"):
        package_from_dict(modified)


@pytest.mark.parametrize("version", ("3.1", "4.0", "4.1-draft"))
def test_notehead_smufl_glyph_is_retained(version: str) -> None:
    """TEST-MXML-ANNOTATION-016: explicit glyph refinement stays typed."""

    source = _partwise(
        '<measure number="1"><attributes><divisions>1</divisions></attributes>'
        "<note><pitch><step>C</step><octave>4</octave></pitch><duration>1</duration>"
        '<type>quarter</type><notehead smufl="noteheadDiamondBlack">diamond</notehead>'
        "</note></measure>",
        version=version,
    )
    result = parse_musicxml_timeline(source)
    assert result.score.annotations.noteheads[0].smufl == "noteheadDiamondBlack"
    assert not any(item.tag == "@smufl" for item in result.deferred)


@pytest.mark.parametrize("version", ("1.0", "1.1", "2.0", "3.0", "3.1", "4.0", "4.1-draft"))
def test_articulation_vocabulary_maps_across_pinned_versions(version: str) -> None:
    """TEST-MXML-ANNOTATION-017: every native articulation name stays typed."""

    names = [
        "accent",
        "strong-accent",
        "staccato",
        "tenuto",
        "detached-legato",
        "staccatissimo",
        "spiccato",
        "scoop",
        "plop",
        "doit",
        "falloff",
        "breath-mark",
        "caesura",
    ]
    if version not in {"1.0", "1.1"}:
        names.extend(("stress", "unstress"))
    if version in {"3.1", "4.0", "4.1-draft"}:
        names.append("soft-accent")
    names.append("other-articulation")
    children = "".join(
        '<strong-accent placement="above" type="down"/>'
        if name == "strong-accent"
        else '<scoop line-shape="curved" line-type="dashed"/>'
        if name == "scoop"
        else "<other-articulation>custom</other-articulation>"
        if name == "other-articulation"
        else f"<{name}/>"
        for name in names
    )
    source = _partwise(
        '<measure number="1"><attributes><divisions>1</divisions></attributes>'
        "<note><pitch><step>C</step><octave>4</octave></pitch><duration>1</duration>"
        f"<type>quarter</type><notations><articulations>{children}</articulations>"
        "</notations></note></measure>",
        version=version,
    )
    result = parse_musicxml_timeline(source)
    marks = result.score.annotations.event_marks
    assert [mark.kind for mark in marks] == names
    strong = next(mark for mark in marks if mark.kind == "strong-accent")
    scoop = next(mark for mark in marks if mark.kind == "scoop")
    custom = next(mark for mark in marks if mark.kind == "other-articulation")
    assert (strong.placement, strong.mark_type) == ("above", "down")
    assert (scoop.line_shape, scoop.line_type) == ("curved", "dashed")
    assert custom.text == "custom"
    assert not any(
        item.tag in {"articulations", "@placement", "@type", "@line-shape", "@line-type"}
        for item in result.deferred
    )
    assert package_from_json(package_to_json(parse_musicxml_timeline_package(source))) == (
        parse_musicxml_timeline_package(source)
    )


def test_articulation_tampering_fails_closed() -> None:
    """TEST-MXML-ANNOTATION-018: invalid typed articulation data is rejected."""

    original = package_to_dict(parse_musicxml_timeline_package(_marked_score()))
    modified = deepcopy(original)
    marker = modified["documents"][0]["content"]["score"]["parts"][0]["measures"][0]["events"][0][
        "event_markers"
    ][0]
    marker["placement"] = "sideways"
    with pytest.raises(CanonicalSerializationError, match="ANNOTATION_EVENT_MARK"):
        package_from_dict(modified)


@pytest.mark.parametrize("version", ("1.0", "1.1", "2.0", "3.0", "3.1", "4.0", "4.1-draft"))
def test_articulation_semantic_attributes_map_across_versions(version: str) -> None:
    """TEST-MXML-ANNOTATION-019: articulation enum values are not collapsed."""

    group_id = ' id="articulation-group"' if version in {"3.1", "4.0", "4.1-draft"} else ""
    smufl = ' smufl="articStaccatoAbove"' if version in {"3.1", "4.0", "4.1-draft"} else ""
    children = (
        '<strong-accent placement="above" type="up"/>'
        '<strong-accent placement="below" type="down"/>'
        '<scoop line-shape="curved" line-type="solid"/>'
        '<plop line-shape="straight" line-type="dashed"/>'
        '<doit line-shape="curved" line-type="dotted"/>'
        '<falloff line-shape="straight" line-type="wavy"/>'
        f"<other-articulation{smufl}>custom</other-articulation>"
    )
    source = _partwise(
        '<measure number="1"><attributes><divisions>1</divisions></attributes>'
        "<note><pitch><step>C</step><octave>4</octave></pitch><duration>1</duration>"
        f"<type>quarter</type><notations><articulations{group_id}>{children}</articulations>"
        "</notations></note></measure>",
        version=version,
    )
    marks = parse_musicxml_timeline(source).score.annotations.event_marks
    assert [(mark.placement, mark.mark_type) for mark in marks[:2]] == [
        ("above", "up"),
        ("below", "down"),
    ]
    assert [(mark.line_shape, mark.line_type) for mark in marks[2:6]] == [
        ("curved", "solid"),
        ("straight", "dashed"),
        ("curved", "dotted"),
        ("straight", "wavy"),
    ]
    if group_id:
        assert all(mark.group_id == "articulation-group" for mark in marks)
        assert marks[-1].smufl == "articStaccatoAbove"


@pytest.mark.parametrize("version", ("1.0", "1.1", "2.0", "3.0", "3.1", "4.0", "4.1-draft"))
def test_point_ornament_vocabulary_maps_across_pinned_versions(version: str) -> None:
    """TEST-MXML-ANNOTATION-020: native point ornaments stay ordered and typed."""

    names = ["trill-mark", "turn", "delayed-turn"]
    if version not in {"1.0", "1.1"}:
        names.append("inverted-turn")
    if version not in {"1.0", "1.1", "2.0"}:
        names.extend(("delayed-inverted-turn", "vertical-turn"))
    if version in {"3.1", "4.0", "4.1-draft"}:
        names.extend(("inverted-vertical-turn", "haydn"))
    names.extend(("shake", "mordent", "inverted-mordent", "schleifer"))
    if version != "1.0":
        names.append("tremolo")
    names.append("other-ornament")
    children = "".join(
        "<tremolo>3</tremolo>"
        if name == "tremolo"
        else "<other-ornament>custom</other-ornament>"
        if name == "other-ornament"
        else f"<{name}/>"
        for name in names
    )
    source = _partwise(
        '<measure number="1"><attributes><divisions>1</divisions></attributes>'
        "<note><pitch><step>C</step><octave>4</octave></pitch><duration>1</duration>"
        f"<type>quarter</type><notations><ornaments>{children}</ornaments>"
        "</notations></note></measure>",
        version=version,
    )
    result = parse_musicxml_timeline(source)
    marks = result.score.annotations.event_marks
    assert [mark.kind for mark in marks] == names
    if version != "1.0":
        tremolo = next(mark for mark in marks if mark.kind == "tremolo")
        assert (tremolo.mark_type, tremolo.tremolo_marks) == ("single", 3)
    assert marks[-1].text == "custom"
    assert not any(item.tag in {"ornaments", "tremolo"} for item in result.deferred)
    assert package_from_json(package_to_json(parse_musicxml_timeline_package(source))) == (
        parse_musicxml_timeline_package(source)
    )


def test_ornament_semantics_and_accidental_scope_are_typed() -> None:
    """TEST-MXML-ANNOTATION-021: playback, shape, and scoped accidentals survive."""

    source = _partwise(
        '<measure number="1"><attributes><divisions>1</divisions></attributes>'
        "<note><pitch><step>C</step><octave>4</octave></pitch><duration>1</duration>"
        '<type>quarter</type><notations><ornaments id="ornament-group">'
        '<turn placement="above" slash="yes" start-note="upper" trill-step="half" '
        'two-note-turn="whole" accelerate="yes" beats="6" second-beat="20" '
        'last-beat="80"/><accidental-mark placement="below" bracket="yes" '
        'parentheses="no" smufl="accidentalSharp">sharp</accidental-mark>'
        '<mordent long="yes" approach="above" departure="below"/>'
        '</ornaments><accidental-mark placement="above" bracket="no" '
        'parentheses="yes">flat</accidental-mark></notations></note></measure>'
    )
    result = parse_musicxml_timeline(source)
    turn, mordent, standalone = result.score.annotations.event_marks
    assert turn.group_id == "ornament-group"
    assert turn.slash is True
    assert turn.playback is not None
    assert (
        turn.playback.start_note,
        turn.playback.trill_step,
        turn.playback.two_note_turn,
        turn.playback.accelerate,
        turn.playback.beats,
        turn.playback.second_beat,
        turn.playback.last_beat,
    ) == ("upper", "half", "whole", True, 6, 20, 80)
    assert len(turn.accidentals) == 1
    accidental = turn.accidentals[0]
    assert (
        accidental.value,
        accidental.placement,
        accidental.bracket,
        accidental.parentheses,
        accidental.smufl,
    ) == ("sharp", "below", True, False, "accidentalSharp")
    assert (mordent.long, mordent.approach, mordent.departure) == (True, "above", "below")
    assert (
        standalone.kind,
        standalone.text,
        standalone.bracket,
        standalone.parentheses,
    ) == ("accidental-mark", "flat", False, True)
    assert not any(
        item.tag
        in {
            "@slash",
            "@start-note",
            "@trill-step",
            "@two-note-turn",
            "@accelerate",
            "@beats",
            "@second-beat",
            "@last-beat",
            "@long",
            "@approach",
            "@departure",
            "accidental-mark",
        }
        for item in result.deferred
    )


@pytest.mark.parametrize("version", ("1.0", "1.1", "2.0", "3.0", "3.1", "4.0", "4.1-draft"))
def test_wavy_line_is_a_numbered_span_with_endpoint_semantics(version: str) -> None:
    """TEST-MXML-ANNOTATION-022: wavy-line endpoints and accidentals remain distinct."""

    def note(step: str, action: str, extra: str = "", accidental: str = "") -> str:
        return (
            f"<note><pitch><step>{step}</step><octave>4</octave></pitch><duration>1</duration>"
            '<type>quarter</type><notations><ornaments><wavy-line number="2" '
            f'type="{action}"{extra}/>{accidental}</ornaments></notations></note>'
        )

    smufl = ' smufl="wiggleTrill"' if version in {"4.0", "4.1-draft"} else ""
    source = _partwise(
        '<measure number="1"><attributes><divisions>1</divisions></attributes>'
        + note(
            "C",
            "start",
            f' placement="above"{smufl} start-note="upper" beats="4"',
            '<accidental-mark placement="above">sharp</accidental-mark>',
        )
        + "</measure>"
        + '<measure number="2">'
        + note("D", "continue")
        + "</measure>"
        + '<measure number="3">'
        + note("E", "stop")
        + "</measure>",
        version=version,
    )
    package = parse_musicxml_timeline_package(source)
    span = package.documents[0].content.score.annotations.spans[0]
    assert (span.kind, span.number) == ("wavy-line", "2")
    assert [endpoint.action for endpoint in span.endpoints] == ["start", "continue", "stop"]
    assert span.endpoints[0].placement == "above"
    assert span.endpoints[0].smufl == ("wiggleTrill" if smufl else None)
    assert span.endpoints[0].playback is not None
    assert span.endpoints[0].playback.beats == 4
    assert span.endpoints[0].accidentals[0].value == "sharp"
    assert not any(
        item.tag in {"wavy-line", "accidental-mark"}
        for item in package.documents[0].content.deferred
    )
    assert package_from_json(package_to_json(package)) == package


@pytest.mark.parametrize("version", ("2.0", "3.0", "3.1", "4.0", "4.1-draft"))
def test_single_unmeasured_and_double_tremolos_stay_distinct(version: str) -> None:
    """TEST-MXML-ANNOTATION-023: point tremolos do not collapse into spans."""

    def note(step: str, tremolo: str, *, half: bool = False) -> str:
        modification = (
            "<time-modification><actual-notes>2</actual-notes><normal-notes>1</normal-notes>"
            "</time-modification>"
            if half
            else ""
        )
        note_type = "half" if half else "quarter"
        return (
            f"<note><pitch><step>{step}</step><octave>4</octave></pitch><duration>1</duration>"
            f"<type>{note_type}</type>{modification}<notations><ornaments>{tremolo}"
            "</ornaments></notations></note>"
        )

    unmeasured = version in {"3.1", "4.0", "4.1-draft"}
    final_tremolo = (
        '<tremolo type="unmeasured" smufl="buzzRoll">0</tremolo>'
        if unmeasured
        else "<tremolo>1</tremolo>"
    )
    source = _partwise(
        '<measure number="1"><attributes><divisions>1</divisions></attributes>'
        + note("C", '<tremolo type="single">3</tremolo>')
        + note("D", '<tremolo type="start">2</tremolo>', half=True)
        + note("E", '<tremolo type="stop">2</tremolo>', half=True)
        + note("F", final_tremolo)
        + "</measure>",
        version=version,
    )
    result = parse_musicxml_timeline(source)
    points = [mark for mark in result.score.annotations.event_marks if mark.kind == "tremolo"]
    assert [(mark.mark_type, mark.tremolo_marks, mark.smufl) for mark in points] == [
        ("single", 3, None),
        ("unmeasured", 0, "buzzRoll") if unmeasured else ("single", 1, None),
    ]
    span = next(item for item in result.score.annotations.spans if item.kind == "tremolo")
    assert [endpoint.tremolo_marks for endpoint in span.endpoints] == [2, 2]
    assert not any(item.tag == "tremolo" for item in result.deferred)


def test_invalid_typed_ornament_data_fails_closed() -> None:
    """TEST-MXML-ANNOTATION-024: invalid canonical ornament semantics are rejected."""

    source = _partwise(
        '<measure number="1"><attributes><divisions>1</divisions></attributes>'
        "<note><pitch><step>C</step><octave>4</octave></pitch><duration>1</duration>"
        '<type>quarter</type><notations><ornaments><trill-mark start-note="upper"/>'
        "</ornaments></notations></note></measure>"
    )
    original = package_to_dict(parse_musicxml_timeline_package(source))
    modified = deepcopy(original)
    marker = modified["documents"][0]["content"]["score"]["parts"][0]["measures"][0]["events"][0][
        "event_markers"
    ][0]
    marker["playback"]["start_note"] = "sideways"
    with pytest.raises(CanonicalSerializationError, match="ANNOTATION_EVENT_MARK"):
        package_from_dict(modified)


@pytest.mark.parametrize("version", ("1.0", "1.1", "2.0", "3.0", "3.1", "4.0", "4.1-draft"))
def test_ornament_semantic_enums_map_across_versions(version: str) -> None:
    """TEST-MXML-ANNOTATION-025: every trill-sound enum value remains distinct."""

    trill_marks = "".join(
        f'<trill-mark placement="{placement}" start-note="{start}" '
        f'trill-step="{step}" two-note-turn="{turn}" accelerate="{accelerate}" '
        f'beats="{index + 2}" second-beat="{index * 10}" last-beat="{80 + index}"/>'
        for index, (placement, start, step, turn, accelerate) in enumerate(
            (
                ("above", "upper", "whole", "whole", "yes"),
                ("below", "main", "half", "half", "no"),
                ("above", "below", "unison", "none", "yes"),
            )
        )
    )
    source = _partwise(
        '<measure number="1"><attributes><divisions>1</divisions></attributes>'
        "<note><pitch><step>C</step><octave>4</octave></pitch><duration>1</duration>"
        f"<type>quarter</type><notations><ornaments>{trill_marks}"
        '<mordent long="yes"/><inverted-mordent long="no"/>'
        '<accidental-mark placement="above">sharp</accidental-mark>'
        '<other-ornament placement="below">custom</other-ornament>'
        "</ornaments></notations></note></measure>",
        version=version,
    )
    marks = parse_musicxml_timeline(source).score.annotations.event_marks
    trills = marks[:3]
    assert [mark.placement for mark in trills] == ["above", "below", "above"]
    assert [mark.playback.start_note for mark in trills if mark.playback] == [
        "upper",
        "main",
        "below",
    ]
    assert [mark.playback.trill_step for mark in trills if mark.playback] == [
        "whole",
        "half",
        "unison",
    ]
    assert [mark.playback.two_note_turn for mark in trills if mark.playback] == [
        "whole",
        "half",
        "none",
    ]
    assert [mark.playback.accelerate for mark in trills if mark.playback] == [True, False, True]
    assert [(marks[3].long, marks[4].long)] == [(True, False)]
    assert marks[4].accidentals[0].value == "sharp"
    assert marks[5].placement == "below"


@pytest.mark.parametrize(
    ("version", "numbers"),
    (("1.0", range(1, 7)), ("1.1", range(1, 7))),
)
def test_legacy_wavy_line_number_enums_remain_distinct(version: str, numbers: range) -> None:
    """TEST-MXML-ANNOTATION-026: every legacy beam-level span number survives."""

    def note(step: str, action: str) -> str:
        lines = "".join(f'<wavy-line type="{action}" number="{number}"/>' for number in numbers)
        return (
            f"<note><pitch><step>{step}</step><octave>4</octave></pitch><duration>1</duration>"
            f"<type>quarter</type><notations><ornaments>{lines}</ornaments></notations></note>"
        )

    source = _partwise(
        '<measure number="1"><attributes><divisions>1</divisions></attributes>'
        + note("C", "start")
        + note("D", "stop")
        + "</measure>",
        version=version,
    )
    spans = parse_musicxml_timeline(source).score.annotations.spans
    assert [span.number for span in spans] == [str(number) for number in numbers]
    assert all(
        [endpoint.action for endpoint in span.endpoints] == ["start", "stop"] for span in spans
    )


@pytest.mark.parametrize("version", ("1.0", "1.1", "2.0", "3.0", "3.1", "4.0", "4.1-draft"))
def test_technical_point_vocabulary_maps_across_pinned_versions(version: str) -> None:
    """TEST-MXML-ANNOTATION-027: native technical point names stay typed."""

    names = [
        "up-bow",
        "down-bow",
        "harmonic",
        "open-string",
        "thumb-position",
        "fingering",
    ]
    if version != "1.0":
        names.append("pluck")
    names.extend(
        (
            "double-tongue",
            "triple-tongue",
            "stopped",
            "snap-pizzicato",
            "fret",
            "string",
            "bend",
            "tap",
            "heel",
            "toe",
            "fingernails",
        )
    )
    if version not in {"1.0", "1.1", "2.0"}:
        names.extend(("hole", "arrow", "handbell"))
    if version in {"3.1", "4.0", "4.1-draft"}:
        names.extend(
            (
                "brass-bend",
                "flip",
                "smear",
                "open",
                "half-muted",
                "harmon-mute",
                "golpe",
            )
        )
    names.append("other-technical")
    text = {
        "fingering": "2",
        "fret": "3",
        "string": "1",
        "tap": "T",
        "handbell": "damp",
        "other-technical": "custom",
    }
    nested = {
        "harmonic": (
            '<harmonic number="2"><natural/><base-pitch/></harmonic>'
            if version == "4.1-draft"
            else "<harmonic><natural/><base-pitch/></harmonic>"
        ),
        "bend": '<bend accelerate="yes" beats="4" first-beat="25" last-beat="75">'
        "<bend-alter>1</bend-alter><pre-bend/></bend>",
        "hole": "<hole><hole-closed>yes</hole-closed></hole>",
        "arrow": "<arrow><arrow-direction>up</arrow-direction></arrow>",
        "harmon-mute": "<harmon-mute><harmon-closed>no</harmon-closed></harmon-mute>",
    }

    def child(name: str) -> str:
        if name in nested:
            return nested[name]
        if name in text:
            attributes = (
                ' substitution="yes" alternate="no"'
                if name == "fingering"
                else (
                    ' hand="left"'
                    if name == "tap" and version in {"3.1", "4.0", "4.1-draft"}
                    else ""
                )
            )
            return f"<{name}{attributes}>{text[name]}</{name}>"
        attributes = (
            ' placement="above"'
            if name == "up-bow"
            else (
                ' placement="below"'
                if name == "down-bow"
                else (' substitution="yes"' if name == "heel" and version != "1.0" else "")
            )
        )
        return f"<{name}{attributes}/>"

    children = "".join(child(name) for name in names)
    source = _partwise(
        '<measure number="1"><attributes><divisions>1</divisions></attributes>'
        "<note><pitch><step>C</step><octave>4</octave></pitch><duration>1</duration>"
        f"<type>quarter</type><notations><technical>{children}</technical>"
        "</notations></note></measure>",
        version=version,
    )
    result = parse_musicxml_timeline(source)
    marks = result.score.annotations.event_marks
    assert [mark.kind for mark in marks] == names
    assert next(mark for mark in marks if mark.kind == "fret").text == "3"
    assert next(mark for mark in marks if mark.kind == "string").text == "1"
    harmonic = next(mark for mark in marks if mark.kind == "harmonic").technical.harmonic
    assert harmonic
    assert harmonic.number == ("2" if version == "4.1-draft" else None)
    assert next(mark for mark in marks if mark.kind == "bend").technical.bend
    assert marks[-1].text == "custom"
    assert not any(item.tag == "technical" for item in result.deferred)
    assert package_from_json(package_to_json(parse_musicxml_timeline_package(source))) == (
        parse_musicxml_timeline_package(source)
    )


def test_nested_technical_semantics_remain_structured() -> None:
    """TEST-MXML-ANNOTATION-028: nested instrument techniques are not flattened."""

    source = _partwise(
        '<measure number="1"><attributes><divisions>4</divisions></attributes>'
        "<note><pitch><step>C</step><octave>4</octave></pitch><duration>4</duration>"
        '<type>quarter</type><notations><technical id="techniques">'
        '<harmonic print-object="no"><artificial/><touching-pitch/></harmonic>'
        '<bend shape="curved" accelerate="yes" beats="5" first-beat="20" last-beat="80">'
        '<bend-alter>-1.5</bend-alter><release offset="2"/>'
        '<with-bar placement="above">dip</with-bar></bend>'
        '<hole placement="above"><hole-type>right index</hole-type>'
        '<hole-closed location="left">half</hole-closed><hole-shape>square</hole-shape></hole>'
        '<arrow placement="below" smufl="arrowBlackUp"><arrow-direction>up</arrow-direction>'
        "<arrow-style>filled</arrow-style><arrowhead/></arrow>"
        "<arrow><circular-arrow>clockwise</circular-arrow></arrow>"
        '<harmon-mute><harmon-closed location="bottom">half</harmon-closed></harmon-mute>'
        '<fingering substitution="yes" alternate="no">4</fingering>'
        '<heel substitution="yes"/><tap hand="left">T</tap>'
        "</technical></notations></note></measure>"
    )
    package = parse_musicxml_timeline_package(source)
    marks = package.documents[0].content.score.annotations.event_marks
    harmonic, bend, hole, arrow, circular, mute, fingering, heel, tap = marks
    assert harmonic.group_id == "techniques"
    assert harmonic.technical.harmonic.harmonic_type == "artificial"
    assert harmonic.technical.harmonic.pitch_type == "touching-pitch"
    assert harmonic.technical.harmonic.print_object is False
    assert bend.technical.bend.alter.numerator == -3
    assert bend.technical.bend.alter.denominator == 2
    assert bend.technical.bend.action == "release"
    assert bend.technical.bend.release_offset == 2
    assert bend.technical.bend.with_bar == "dip"
    assert bend.technical.bend.with_bar_placement == "above"
    assert bend.technical.bend.accelerate is True
    assert hole.technical.hole.closed == "half"
    assert hole.technical.hole.closed_location == "left"
    assert (arrow.technical.arrow.direction, arrow.technical.arrow.style) == ("up", "filled")
    assert arrow.technical.arrow.arrowhead_only is True
    assert circular.technical.arrow.circular == "clockwise"
    assert mute.technical.harmon_mute.closed_location == "bottom"
    assert (fingering.technical.substitution, fingering.technical.alternate) == (True, False)
    assert heel.technical.substitution is True
    assert tap.technical.hand == "left"
    assert arrow.smufl == "arrowBlackUp"
    assert not any(
        item.tag
        in {
            "harmonic",
            "bend",
            "bend-alter",
            "release",
            "with-bar",
            "hole",
            "arrow",
            "harmon-mute",
            "@shape",
            "@offset",
            "@location",
            "@hand",
        }
        for item in package.documents[0].content.deferred
    )
    assert package_from_json(package_to_json(package)) == package


@pytest.mark.parametrize("version", ("1.0", "1.1", "2.0", "3.0", "3.1", "4.0", "4.1-draft"))
def test_hammer_on_and_pull_off_are_numbered_spans(version: str) -> None:
    """TEST-MXML-ANNOTATION-029: fretted techniques retain paired endpoints."""

    def note(step: str, action: str) -> str:
        return (
            f"<note><pitch><step>{step}</step><octave>4</octave></pitch><duration>1</duration>"
            '<type>quarter</type><notations><technical><hammer-on number="2" '
            f'type="{action}">H</hammer-on><pull-off number="3" type="{action}">P</pull-off>'
            "</technical></notations></note>"
        )

    source = _partwise(
        '<measure number="1"><attributes><divisions>1</divisions></attributes>'
        + note("C", "start")
        + note("D", "stop")
        + "</measure>",
        version=version,
    )
    package = parse_musicxml_timeline_package(source)
    spans = package.documents[0].content.score.annotations.spans
    assert [(span.kind, span.number) for span in spans] == [
        ("hammer-on", "2"),
        ("pull-off", "3"),
    ]
    assert [[endpoint.text for endpoint in span.endpoints] for span in spans] == [
        ["H", "H"],
        ["P", "P"],
    ]
    assert not any(
        item.tag in {"hammer-on", "pull-off"} for item in package.documents[0].content.deferred
    )
    assert package_from_json(package_to_json(package)) == package


def test_invalid_typed_technical_data_fails_closed() -> None:
    """TEST-MXML-ANNOTATION-030: malformed technical semantics cannot enter v2."""

    source = _partwise(
        '<measure number="1"><attributes><divisions>1</divisions></attributes>'
        "<note><pitch><step>C</step><octave>4</octave></pitch><duration>1</duration>"
        "<type>quarter</type><notations><technical><arrow>"
        "<arrow-direction>up</arrow-direction></arrow></technical></notations></note></measure>"
    )
    modified = package_to_dict(parse_musicxml_timeline_package(source))
    marker = modified["documents"][0]["content"]["score"]["parts"][0]["measures"][0]["events"][0][
        "event_markers"
    ][0]
    marker["technical"]["arrow"]["direction"] = "sideways"
    with pytest.raises(CanonicalSerializationError, match="ANNOTATION_EVENT_MARK"):
        package_from_dict(modified)


@pytest.mark.parametrize("version", ("3.0", "3.1", "4.0", "4.1-draft"))
def test_instrument_technical_enum_values_remain_distinct(version: str) -> None:
    """TEST-MXML-ANNOTATION-031: instrument-specific enums retain exact values."""

    directions = (
        "left",
        "up",
        "right",
        "down",
        "northwest",
        "northeast",
        "southeast",
        "southwest",
        "left right",
        "up down",
        "northwest southeast",
        "northeast southwest",
        "other",
    )
    styles = ("single", "double", "filled", "hollow", "paired", "combined", "other")
    arrows = "".join(
        f"<arrow><arrow-direction>{direction}</arrow-direction>"
        + (f"<arrow-style>{styles[index]}</arrow-style>" if index < len(styles) else "")
        + ("<arrowhead/>" if index == 0 and version != "3.0" else "")
        + "</arrow>"
        for index, direction in enumerate(directions)
    ) + "".join(
        f"<arrow><circular-arrow>{value}</circular-arrow></arrow>"
        for value in ("clockwise", "anticlockwise")
    )
    handbells = (
        "damp",
        "echo",
        "gyro",
        "hand martellato",
        "mallet lift",
        "mallet table",
        "martellato",
        "martellato lift",
        "muted martellato",
        "pluck lift",
        "swing",
    )
    if version != "3.0":
        handbells = ("belltree", *handbells)
    holes = "".join(
        f'<hole><hole-closed location="{location}">{closed}</hole-closed></hole>'
        for closed, location in zip(
            ("yes", "no", "half", "half"), ("right", "bottom", "left", "top"), strict=True
        )
    )
    later = ""
    if version != "3.0":
        later = "".join(
            f'<harmon-mute><harmon-closed location="{location}">{closed}'
            "</harmon-closed></harmon-mute>"
            for closed, location in zip(
                ("yes", "no", "half", "half"),
                ("right", "bottom", "left", "top"),
                strict=True,
            )
        ) + "".join(f'<tap hand="{hand}">T</tap>' for hand in ("left", "right"))
    shapes = (
        "".join(
            f'<bend shape="{shape}"><bend-alter>1</bend-alter></bend>'
            for shape in ("angled", "curved")
        )
        if version in {"4.0", "4.1-draft"}
        else ""
    )
    source = _partwise(
        '<measure number="1"><attributes><divisions>1</divisions></attributes>'
        "<note><pitch><step>C</step><octave>4</octave></pitch><duration>1</duration>"
        f"<type>quarter</type><notations><technical>{arrows}{holes}"
        + "".join(f"<handbell>{value}</handbell>" for value in handbells)
        + later
        + shapes
        + "</technical></notations></note></measure>",
        version=version,
    )
    marks = parse_musicxml_timeline(source).score.annotations.event_marks
    arrow_marks = [mark.technical.arrow for mark in marks if mark.kind == "arrow"]
    assert [mark.direction for mark in arrow_marks[: len(directions)]] == list(directions)
    assert {mark.style for mark in arrow_marks} >= {*styles, None}
    assert {mark.circular for mark in arrow_marks} >= {"clockwise", "anticlockwise"}
    assert {mark.text for mark in marks if mark.kind == "handbell"} == set(handbells)
    assert {mark.technical.hole.closed for mark in marks if mark.kind == "hole"} == {
        "yes",
        "no",
        "half",
    }
    if version != "3.0":
        assert {mark.technical.hand for mark in marks if mark.kind == "tap"} == {
            "left",
            "right",
        }
    if shapes:
        assert {mark.technical.bend.shape for mark in marks if mark.kind == "bend"} == {
            "angled",
            "curved",
        }


@pytest.mark.parametrize("version", ("1.0", "1.1"))
def test_legacy_technical_span_number_enums_remain_distinct(version: str) -> None:
    """TEST-MXML-ANNOTATION-032: all legacy technical span numbers survive."""

    def note(step: str, action: str) -> str:
        spans = "".join(
            f'<hammer-on type="{action}" number="{number}">H</hammer-on>'
            f'<pull-off type="{action}" number="{number}">P</pull-off>'
            for number in range(1, 7)
        )
        return (
            f"<note><pitch><step>{step}</step><octave>4</octave></pitch><duration>1</duration>"
            f"<type>quarter</type><notations><technical>{spans}</technical></notations></note>"
        )

    source = _partwise(
        '<measure number="1"><attributes><divisions>1</divisions></attributes>'
        + note("C", "start")
        + note("D", "stop")
        + "</measure>",
        version=version,
    )
    spans = parse_musicxml_timeline(source).score.annotations.spans
    assert [(span.kind, span.number) for span in spans] == [
        (kind, str(number)) for number in range(1, 7) for kind in ("hammer-on", "pull-off")
    ]


@pytest.mark.parametrize("version", ("1.0", "1.1", "2.0", "3.0", "3.1", "4.0", "4.1-draft"))
def test_general_point_notations_map_across_pinned_versions(version: str) -> None:
    """TEST-MXML-ANNOTATION-033: fermata and arpeggiation semantics stay typed."""

    xsd = version not in {"1.0", "1.1"}
    identified = version in {"3.1", "4.0", "4.1-draft"}
    extended_fermata = version in {"3.1", "4.0", "4.1-draft"}
    fermata_id = ' id="fermata-1"' if identified else ""
    fermata = (
        f'<fermata type="upright"{fermata_id}>'
        f"{'double-dot' if extended_fermata else 'angled'}</fermata>"
        if xsd
        else '<fermata type="upright"/>'
    )
    arpeggiate = (
        '<arpeggiate number="2" direction="up" placement="above"'
        + (' id="arp-1"' if identified else "")
        + (' unbroken="yes"' if version in {"4.0", "4.1-draft"} else "")
        + '/><non-arpeggiate number="3" type="top" placement="below"/>'
    )
    other = (
        '<other-notation number="4" type="single" placement="above"'
        + (' id="other-1" smufl="ornamentTurn"' if identified else "")
        + ">custom</other-notation>"
        if xsd
        else ""
    )
    source = _partwise(
        '<measure number="1"><attributes><divisions>1</divisions></attributes>'
        "<note><pitch><step>C</step><octave>4</octave></pitch><duration>1</duration>"
        f"<type>quarter</type><notations>{fermata}{arpeggiate}{other}</notations>"
        "</note></measure>",
        version=version,
    )
    result = parse_musicxml_timeline(source)
    marks = result.score.annotations.event_marks
    assert [mark.kind for mark in marks] == [
        "fermata",
        "arpeggiate",
        "non-arpeggiate",
        *(("other-notation",) if xsd else ()),
    ]
    assert marks[0].mark_type == "upright"
    assert marks[0].text == ("double-dot" if extended_fermata else ("angled" if xsd else None))
    assert (marks[1].number, marks[1].mark_type, marks[1].placement) == ("2", "up", "above")
    assert marks[1].unbroken is (True if version in {"4.0", "4.1-draft"} else None)
    assert (marks[2].number, marks[2].mark_type) == ("3", "top")
    assert not any(
        item.tag in {"fermata", "arpeggiate", "non-arpeggiate", "other-notation"}
        for item in result.deferred
    )
    package = parse_musicxml_timeline_package(source)
    assert package_from_json(package_to_json(package)) == package


@pytest.mark.parametrize("version", ("1.0", "1.1", "2.0", "3.0", "3.1", "4.0", "4.1-draft"))
def test_glissando_and_slide_spans_map_across_pinned_versions(version: str) -> None:
    """TEST-MXML-ANNOTATION-034: general line spans preserve their endpoints."""

    text = "" if version == "1.0" else "gliss."
    identified = version in {"3.1", "4.0", "4.1-draft"}

    def note(step: str, action: str) -> str:
        identity = f' id="gliss-{action}"' if identified else ""
        slide_identity = f' id="slide-{action}"' if identified else ""
        return (
            f"<note><pitch><step>{step}</step><octave>4</octave></pitch><duration>1</duration>"
            '<type>quarter</type><notations><glissando number="2" line-type="wavy" '
            f'type="{action}"{identity}>{text}</glissando>'
            '<slide number="3" line-type="dashed" '
            f'type="{action}"{slide_identity}>{text}</slide>'
            "</notations></note>"
        )

    source = _partwise(
        '<measure number="1"><attributes><divisions>1</divisions></attributes>'
        + note("C", "start")
        + note("D", "stop")
        + "</measure>",
        version=version,
    )
    result = parse_musicxml_timeline(source)
    spans = result.score.annotations.spans
    assert [(span.kind, span.number) for span in spans] == [("glissando", "2"), ("slide", "3")]
    assert [[endpoint.line_type for endpoint in span.endpoints] for span in spans] == [
        ["wavy", "wavy"],
        ["dashed", "dashed"],
    ]
    assert all(
        [endpoint.text for endpoint in span.endpoints] == [text or None, text or None]
        for span in spans
    )
    assert not any(item.tag in {"glissando", "slide"} for item in result.deferred)


@pytest.mark.parametrize("version", ("1.0", "1.1", "2.0", "3.0", "3.1", "4.0", "4.1-draft"))
def test_note_dynamics_map_across_pinned_versions(version: str) -> None:
    """TEST-MXML-ANNOTATION-035: notation dynamics retain vocabulary and scope."""

    later = version in {"3.1", "4.0", "4.1-draft"}
    names = (
        "p",
        "pp",
        "ppp",
        "pppp",
        "ppppp",
        "pppppp",
        "f",
        "ff",
        "fff",
        "ffff",
        "fffff",
        "ffffff",
        "mp",
        "mf",
        "sf",
        "sfp",
        "sfpp",
        "fp",
        "rf",
        "rfz",
        "sfz",
        "sffz",
        "fz",
        *(("n", "pf", "sfzp") if later else ()),
    )
    identity = ' id="dyn-1"' if later else ""
    smufl = ' smufl="dynamicForte"' if later else ""
    source = _partwise(
        '<measure number="1"><attributes><divisions>1</divisions></attributes>'
        "<note><pitch><step>C</step><octave>4</octave></pitch><duration>1</duration>"
        f'<type>quarter</type><notations><dynamics placement="below"{identity}>'
        + "".join(f"<{name}/>" for name in names)
        + f"<other-dynamics{smufl}>subito</other-dynamics>"
        "</dynamics></notations></note></measure>",
        version=version,
    )
    result = parse_musicxml_timeline(source)
    marks = result.score.annotations.event_marks
    assert [mark.kind for mark in marks] == [*names, "other-dynamics"]
    assert all(mark.family == "dynamic" and mark.placement == "below" for mark in marks)
    assert marks[-1].text == "subito"
    assert marks[-1].smufl == ("dynamicForte" if later else None)
    assert not any(item.tag == "dynamics" for item in result.deferred)


@pytest.mark.parametrize("version", ("3.1", "4.0", "4.1-draft"))
def test_direction_dynamics_share_group_identity_and_glyph(version: str) -> None:
    """TEST-MXML-ANNOTATION-036: direction dynamics share typed identity semantics."""

    source = _partwise(
        '<measure number="1"><attributes><divisions>1</divisions></attributes>'
        '<direction placement="above"><direction-type><dynamics id="dyn-direction">'
        '<other-dynamics smufl="dynamicForte">forte subito</other-dynamics>'
        "</dynamics></direction-type></direction>"
        "<note><rest/><duration>1</duration><type>quarter</type></note></measure>",
        version=version,
    )
    result = parse_musicxml_timeline(source)
    mark = result.score.annotations.directions[0]
    assert (mark.family, mark.value, mark.placement) == ("dynamic", "forte subito", "above")
    assert (mark.group_id, mark.smufl) == ("dyn-direction", "dynamicForte")
    assert not any(item.tag in {"dynamics", "other-dynamics"} for item in result.deferred)
    package = parse_musicxml_timeline_package(source)
    assert package_from_json(package_to_json(package)) == package
    modified = package_to_dict(package)
    direction = modified["documents"][0]["content"]["score"]["parts"][0]["measures"][0][
        "directions"
    ][0]
    direction["group_id"] = ""
    with pytest.raises(CanonicalSerializationError, match="ANNOTATION_DIRECTION"):
        package_from_dict(modified)


@pytest.mark.parametrize("version", ("1.0", "1.1", "2.0", "3.0", "3.1", "4.0", "4.1-draft"))
def test_barline_fermatas_are_retained_across_pinned_versions(version: str) -> None:
    """TEST-MXML-ANNOTATION-037: barline fermatas are not mistaken for note marks."""

    xsd = version not in {"1.0", "1.1"}
    identified = version in {"3.1", "4.0", "4.1-draft"}
    shape = "curlew" if identified else "square"
    fermata_id = ' id="bar-fermata"' if identified else ""
    fermata = (
        f'<fermata type="inverted"{fermata_id}>{shape}</fermata>'
        if xsd
        else '<fermata type="inverted"/>'
    )
    source = _partwise(
        '<measure number="1"><attributes><divisions>1</divisions></attributes>'
        "<note><rest/><duration>1</duration><type>quarter</type></note>"
        f'<barline location="right"><bar-style>light-heavy</bar-style>{fermata}</barline>'
        "</measure>",
        version=version,
    )
    result = parse_musicxml_timeline(source)
    mapped = result.score.parts[0].measures[0].barlines[0].fermatas[0]
    assert (mapped.shape, mapped.orientation) == ((shape if xsd else None), "inverted")
    assert mapped.source_id == ("bar-fermata" if identified else None)
    assert not any(item.tag == "fermata" for item in result.deferred)
    package = parse_musicxml_timeline_package(source)
    assert package_from_json(package_to_json(package)) == package
    modified = package_to_dict(package)
    fermata_value = modified["documents"][0]["content"]["score"]["parts"][0]["measures"][0][
        "barlines"
    ][0]["fermatas"][0]
    fermata_value["shape"] = "invalid-shape"
    with pytest.raises(CanonicalSerializationError, match="TEMPORAL_BARLINE_FERMATA"):
        package_from_dict(modified)


def test_slide_playback_other_notation_and_tampering_fail_closed() -> None:
    """TEST-MXML-ANNOTATION-038: rich spans round-trip and invalid values are rejected."""

    def note(step: str, action: str) -> str:
        return (
            f"<note><pitch><step>{step}</step><octave>4</octave></pitch><duration>1</duration>"
            '<type>quarter</type><notations><slide number="2" type="'
            f'{action}" accelerate="yes" beats="4" first-beat="25" last-beat="75">slide</slide>'
            '<fermata type="upright">angled</fermata>'
            '<other-notation number="3" type="'
            f'{action}" placement="above" print-object="no" smufl="ornamentTurn">custom'
            "</other-notation></notations></note>"
        )

    source = _partwise(
        '<measure number="1"><attributes><divisions>1</divisions></attributes>'
        + note("C", "start")
        + note("D", "stop")
        + "</measure>"
    )
    package = parse_musicxml_timeline_package(source)
    slide, other = package.documents[0].content.score.annotations.spans
    assert slide.endpoints[0].bend_sound.beats == 4
    assert slide.endpoints[0].bend_sound.accelerate is True
    assert (other.endpoints[0].placement, other.endpoints[0].print_object) == ("above", False)
    assert package_from_json(package_to_json(package)) == package

    modified = package_to_dict(package)
    endpoint = modified["documents"][0]["content"]["score"]["parts"][0]["measures"][0]["events"][0][
        "span_markers"
    ][0]
    endpoint["bend_sound"]["first_beat"] = {"numerator": 101, "denominator": 1}
    with pytest.raises(CanonicalSerializationError, match="ANNOTATION_SPAN_MARKER"):
        package_from_dict(modified)

    modified = package_to_dict(package)
    event_mark = modified["documents"][0]["content"]["score"]["parts"][0]["measures"][0]["events"][
        0
    ]["event_markers"][0]
    event_mark["text"] = "invalid-shape"
    with pytest.raises(CanonicalSerializationError, match="ANNOTATION_EVENT_MARK"):
        package_from_dict(modified)


@pytest.mark.parametrize("version", ("1.0", "1.1"))
def test_legacy_general_notation_enums_remain_distinct(version: str) -> None:
    """TEST-MXML-ANNOTATION-039: legacy level, line, direction, and type enums survive."""

    numbers = range(1, 7)
    line_types = ("solid", "dashed", "dotted", "wavy", "solid", "dashed")

    def line_marks(action: str) -> str:
        return "".join(
            f'<glissando number="{number}" type="{action}" line-type="{line_type}"/>'
            f'<slide number="{number}" type="{action}" line-type="{line_type}" '
            f'accelerate="{"yes" if action == "start" else "no"}"/>'
            for number, line_type in zip(numbers, line_types, strict=True)
        )

    def other_marks(action: str) -> str:
        return "".join(
            f'<other-notation number="{number}" type="{action}" '
            f'placement="{"above" if number % 2 else "below"}">custom</other-notation>'
            for number in numbers
        )

    def note(number: int) -> str:
        prefix = line_marks("start") if number == 1 else ""
        suffix = line_marks("stop") if number == 6 else ""
        other_prefix = other_marks("start") if number == 1 else ""
        other_suffix = other_marks("stop") if number == 6 else ""
        return (
            "<note><pitch><step>C</step><octave>4</octave></pitch><duration>1</duration>"
            f"<type>quarter</type><notations>{prefix}{suffix}"
            f'<arpeggiate number="{number}" direction="{"up" if number % 2 else "down"}" '
            f'placement="{"above" if number % 2 else "below"}"/>'
            f'<non-arpeggiate number="{number}" type="{"top" if number % 2 else "bottom"}" '
            f'placement="{"above" if number % 2 else "below"}"/>'
            f"{other_prefix}{other_suffix}</notations></note>"
        )

    source = _partwise(
        '<measure number="1"><attributes><divisions>1</divisions></attributes>'
        + "".join(note(number) for number in numbers)
        + "</measure>",
        version=version,
    )
    graph = parse_musicxml_timeline(source).score.annotations
    assert {(span.kind, span.number) for span in graph.spans} == {
        (kind, str(number))
        for kind in ("glissando", "slide", "other-notation")
        for number in numbers
    }
    assert [mark.number for mark in graph.event_marks if mark.kind == "arpeggiate"] == [
        str(number) for number in numbers
    ]
    assert {mark.mark_type for mark in graph.event_marks if mark.kind == "arpeggiate"} == {
        "up",
        "down",
    }
    assert {mark.mark_type for mark in graph.event_marks if mark.kind == "non-arpeggiate"} == {
        "top",
        "bottom",
    }


@pytest.mark.parametrize("version", ("2.0", "3.0", "3.1", "4.0", "4.1-draft"))
def test_fermata_shape_enums_remain_distinct(version: str) -> None:
    """TEST-MXML-ANNOTATION-040: every version-specific fermata shape survives."""

    shapes = ["normal", "angled", "square", ""]
    if version in {"3.1", "4.0", "4.1-draft"}:
        shapes.extend(("double-angled", "double-square", "double-dot", "half-curve", "curlew"))
    notes = "".join(
        "<note><pitch><step>C</step><octave>4</octave></pitch><duration>1</duration>"
        f'<type>quarter</type><notations><fermata type="{"upright" if index % 2 else "inverted"}">'
        f"{shape}</fermata></notations></note>"
        for index, shape in enumerate(shapes)
    )
    source = _partwise(
        '<measure number="1"><attributes><divisions>1</divisions></attributes>'
        + notes
        + "</measure>",
        version=version,
    )
    marks = parse_musicxml_timeline(source).score.annotations.event_marks
    assert [mark.text for mark in marks] == [shape or None for shape in shapes]
    assert {mark.mark_type for mark in marks} == {"upright", "inverted"}


@pytest.mark.parametrize("version", ("1.0", "1.1", "2.0", "3.0", "3.1", "4.0", "4.1-draft"))
def test_simple_point_directions_map_across_pinned_versions(version: str) -> None:
    """TEST-MXML-ANNOTATION-041: common point directions retain semantic content."""

    identified = version in {"3.1", "4.0", "4.1-draft"}
    printable = version not in {"1.0", "1.1"}
    names_and_values = (
        ("rehearsal", "A"),
        ("segno", ""),
        ("coda", ""),
        ("words", "dolce"),
        ("damp", ""),
        ("damp-all", ""),
        ("eyeglasses", ""),
        ("other-direction", "custom"),
    )
    direction_types = []
    for index, (name, value) in enumerate(names_and_values):
        type_id = f' id="direction-type-{index}"' if identified else ""
        source_id = f' id="direction-source-{index}"' if identified else ""
        smufl = (
            ' smufl="segno"'
            if identified and name == "segno"
            else (
                ' smufl="coda"'
                if identified and name == "coda"
                else (' smufl="segno"' if identified and name == "other-direction" else "")
            )
        )
        print_object = (
            f' print-object="{"yes" if identified else "no"}"'
            if printable and name == "other-direction"
            else ""
        )
        direction_types.append(
            f"<direction-type{type_id}><{name}{source_id}{smufl}{print_object}>"
            f"{value}</{name}></direction-type>"
        )
    direction_id = ' id="direction-1"' if identified else ""
    source = _partwise(
        '<measure number="1"><attributes><divisions>1</divisions></attributes>'
        f'<direction placement="above"{direction_id}>' + "".join(direction_types) + "</direction>"
        "<note><rest/><duration>1</duration><type>quarter</type></note></measure>",
        version=version,
    )
    result = parse_musicxml_timeline(source)
    marks = result.score.annotations.directions
    assert [(mark.family, mark.value) for mark in marks] == list(names_and_values)
    assert all(mark.placement == "above" for mark in marks)
    assert [mark.direction_id for mark in marks] == ["direction-1" if identified else None] * len(
        marks
    )
    expected_type_ids = (
        [f"direction-type-{index}" for index in range(len(marks))]
        if identified
        else [None] * len(marks)
    )
    expected_source_ids = (
        [f"direction-source-{index}" for index in range(len(marks))]
        if identified
        else [None] * len(marks)
    )
    assert [mark.direction_type_id for mark in marks] == expected_type_ids
    assert [mark.source_id for mark in marks] == expected_source_ids
    assert marks[1].smufl == ("segno" if identified else None)
    assert marks[2].smufl == ("coda" if identified else None)
    assert marks[-1].smufl == ("segno" if identified else None)
    assert marks[-1].print_object is (identified if printable else None)
    assert not any(item.tag in {name for name, _ in names_and_values} for item in result.deferred)
    package = parse_musicxml_timeline_package(source)
    assert package_from_json(package_to_json(package)) == package


@pytest.mark.parametrize("version", ("3.0", "3.1", "4.0", "4.1-draft"))
def test_versioned_point_direction_vocabularies_are_distinct(version: str) -> None:
    """TEST-MXML-ANNOTATION-042: mute, symbol, and staff-division enums survive."""

    later = version in {"3.1", "4.0", "4.1-draft"}
    values = [("string-mute", "on"), ("string-mute", "off")]
    children = [
        f'<direction-type><string-mute type="{value}"/></direction-type>' for _, value in values
    ]
    if later:
        values.extend(
            (
                ("symbol", "accidentalSharp"),
                ("staff-divide", "down"),
                ("staff-divide", "up"),
                ("staff-divide", "up-down"),
            )
        )
        children.extend(
            (
                "<direction-type><symbol>accidentalSharp</symbol></direction-type>",
                '<direction-type><staff-divide type="down"/></direction-type>',
                '<direction-type><staff-divide type="up"/></direction-type>',
                '<direction-type><staff-divide type="up-down"/></direction-type>',
            )
        )
    source = _partwise(
        '<measure number="1"><attributes><divisions>1</divisions></attributes><direction>'
        + "".join(children)
        + "</direction><note><rest/><duration>1</duration><type>quarter</type></note></measure>",
        version=version,
    )
    result = parse_musicxml_timeline(source)
    assert [(mark.family, mark.value) for mark in result.score.annotations.directions] == values
    assert not any(
        item.tag in {"string-mute", "symbol", "staff-divide"} for item in result.deferred
    )


@pytest.mark.parametrize("system", ("only-top", "also-top", "none"))
def test_direction_and_time_span_identity_and_system_scope_survive(system: str) -> None:
    """TEST-MXML-ANNOTATION-043: direction context is retained on points and spans."""

    source = _partwise(
        '<measure number="1"><attributes><divisions>1</divisions></attributes>'
        f'<direction id="point-direction" system="{system}">'
        '<direction-type id="point-type"><words id="point-source">cantabile</words>'
        "</direction-type></direction>"
        f'<direction id="span-start-direction" system="{system}">'
        '<direction-type id="span-start-type"><dashes id="span-start-source" '
        'number="2" type="start"/></direction-type></direction>'
        "<note><rest/><duration>1</duration><type>quarter</type></note>"
        f'<direction id="span-stop-direction" system="{system}">'
        '<direction-type id="span-stop-type"><dashes id="span-stop-source" '
        'number="2" type="stop"/></direction-type></direction></measure>',
        version="4.0",
    )
    package = parse_musicxml_timeline_package(source)
    score = package.documents[0].content.score
    direction = score.annotations.directions[0]
    assert (
        direction.direction_id,
        direction.direction_type_id,
        direction.source_id,
        direction.system_relation,
    ) == ("point-direction", "point-type", "point-source", system)
    endpoints = score.annotations.time_spans[0].endpoints
    assert [endpoint.direction_id for endpoint in endpoints] == [
        "span-start-direction",
        "span-stop-direction",
    ]
    assert [endpoint.direction_type_id for endpoint in endpoints] == [
        "span-start-type",
        "span-stop-type",
    ]
    assert [endpoint.source_id for endpoint in endpoints] == [
        "span-start-source",
        "span-stop-source",
    ]
    assert [endpoint.system_relation for endpoint in endpoints] == [system, system]
    assert package_from_json(package_to_json(package)) == package


def test_simple_direction_tampering_fails_closed() -> None:
    """TEST-MXML-ANNOTATION-044: invalid point and span semantics are rejected."""

    source = _partwise(
        '<measure number="1"><attributes><divisions>1</divisions></attributes>'
        '<direction system="only-top"><direction-type><string-mute type="on"/>'
        "</direction-type></direction>"
        '<direction><direction-type><dashes type="start"/></direction-type></direction>'
        "<note><rest/><duration>1</duration><type>quarter</type></note>"
        '<direction><direction-type><dashes type="stop"/></direction-type></direction>'
        "</measure>"
    )
    original = package_to_dict(parse_musicxml_timeline_package(source))
    modified = deepcopy(original)
    direction = modified["documents"][0]["content"]["score"]["parts"][0]["measures"][0][
        "directions"
    ][0]
    direction["value"] = "invalid"
    with pytest.raises(CanonicalSerializationError, match="ANNOTATION_DIRECTION"):
        package_from_dict(modified)

    modified = deepcopy(original)
    marker = modified["documents"][0]["content"]["score"]["parts"][0]["measures"][0][
        "time_span_markers"
    ][0]
    marker["system_relation"] = "invalid"
    with pytest.raises(CanonicalSerializationError, match="ANNOTATION_TIME_SPAN"):
        package_from_dict(modified)


@pytest.mark.parametrize("version", ("1.0", "1.1", "2.0", "3.0", "3.1", "4.0", "4.1-draft"))
def test_regular_metronome_marks_map_across_pinned_versions(version: str) -> None:
    """TEST-MXML-ANNOTATION-045: regular tempo marks preserve exact beat content."""

    identified = version in {"3.1", "4.0", "4.1-draft"}
    source_id = ' id="metronome-1"' if identified else ""
    source = _partwise(
        '<measure number="1"><attributes><divisions>1</divisions></attributes>'
        '<direction placement="above"><direction-type><metronome parentheses="yes"'
        f"{source_id}>"
        "<beat-unit>quarter</beat-unit><beat-unit-dot/><per-minute>120</per-minute>"
        "</metronome></direction-type></direction>"
        "<note><rest/><duration>1</duration><type>quarter</type></note></measure>",
        version=version,
    )
    result = parse_musicxml_timeline(source)
    direction = result.score.annotations.directions[0]
    assert (direction.family, direction.value, direction.source_id) == (
        "metronome",
        "120",
        "metronome-1" if identified else None,
    )
    assert direction.data is not None and direction.data.metronome is not None
    mark = direction.data.metronome
    assert [(beat.note_type, beat.dots, beat.tied_to_previous) for beat in mark.beats] == [
        ("quarter", 1, False)
    ]
    assert (mark.per_minute, mark.parentheses) == ("120", True)
    assert not any(item.tag == "metronome" for item in result.deferred)
    package = parse_musicxml_timeline_package(source)
    assert package_from_json(package_to_json(package)) == package


@pytest.mark.parametrize("version", ("1.1", "2.0", "3.0", "3.1", "4.0", "4.1-draft"))
def test_harp_pedals_and_scordatura_map_across_applicable_versions(version: str) -> None:
    """TEST-MXML-ANNOTATION-046: tuning directions retain exact spelling and order."""

    source = _partwise(
        '<measure number="1"><attributes><divisions>1</divisions></attributes><direction>'
        "<direction-type><harp-pedals>"
        "<pedal-tuning><pedal-step>D</pedal-step><pedal-alter>-1</pedal-alter>"
        "</pedal-tuning><pedal-tuning><pedal-step>C</pedal-step><pedal-alter>0</pedal-alter>"
        "</pedal-tuning></harp-pedals></direction-type>"
        '<direction-type><scordatura><accord string="2"><tuning-step>G</tuning-step>'
        "<tuning-alter>0.5</tuning-alter><tuning-octave>4</tuning-octave></accord>"
        "</scordatura></direction-type></direction>"
        "<note><rest/><duration>1</duration><type>quarter</type></note></measure>",
        version=version,
    )
    directions = parse_musicxml_timeline(source).score.annotations.directions
    assert [direction.family for direction in directions] == ["harp-pedals", "scordatura"]
    assert directions[0].data is not None
    assert [(pitch.step, pitch.alter) for pitch in directions[0].data.harp_pedals] == [
        ("D", -1),
        ("C", 0),
    ]
    assert directions[1].data is not None
    accord = directions[1].data.scordatura[0]
    assert (accord.step, accord.alter, accord.octave, accord.string) == ("G", Fraction(1, 2), 4, 2)


@pytest.mark.parametrize("version", ("3.0", "3.1", "4.0", "4.1-draft"))
def test_accordion_and_principal_voice_semantics_map(version: str) -> None:
    """TEST-MXML-ANNOTATION-047: registration and voice-analysis values survive."""

    identified = version in {"3.1", "4.0", "4.1-draft"}
    source_id = ' id="voice-mark"' if identified else ""
    source = _partwise(
        '<measure number="1"><attributes><divisions>1</divisions></attributes><direction>'
        "<direction-type><accordion-registration><accordion-high/><accordion-middle>3"
        "</accordion-middle><accordion-low/></accordion-registration></direction-type>"
        f'<direction-type><principal-voice type="start" symbol="Hauptstimme"{source_id}>'
        "primary</principal-voice></direction-type></direction>"
        "<note><rest/><duration>1</duration><type>quarter</type></note></measure>",
        version=version,
    )
    directions = parse_musicxml_timeline(source).score.annotations.directions
    assert [direction.family for direction in directions] == [
        "accordion-registration",
        "principal-voice",
    ]
    assert directions[0].data is not None
    accordion = directions[0].data.accordion
    assert accordion is not None and (accordion.high, accordion.middle, accordion.low) == (
        True,
        3,
        True,
    )
    assert directions[1].data is not None
    principal = directions[1].data.principal_voice
    assert principal is not None and (
        principal.action,
        principal.symbol,
        principal.text,
    ) == ("start", "Hauptstimme", "primary")


@pytest.mark.parametrize("version", ("2.0", "3.0", "3.1", "4.0", "4.1-draft"))
def test_metric_modulation_retains_notes_beams_ties_and_tuplets(version: str) -> None:
    """TEST-MXML-ANNOTATION-048: structured metric modulation round-trips."""

    def metronome_note(note_type: str, tie: str, action: str) -> str:
        return (
            f"<metronome-note><metronome-type>{note_type}</metronome-type><metronome-dot/>"
            f'<metronome-beam number="1">{"begin" if action == "start" else "end"}'
            "</metronome-beam>"
            + (f'<metronome-tied type="{tie}"/>' if version not in {"2.0", "3.0"} else "")
            + f'<metronome-tuplet type="{action}" bracket="yes" show-number="both">'
            "<actual-notes>3</actual-notes><normal-notes>2</normal-notes>"
            "<normal-type>eighth</normal-type><normal-dot/></metronome-tuplet>"
            "</metronome-note>"
        )

    source = _partwise(
        '<measure number="1"><attributes><divisions>1</divisions></attributes><direction>'
        '<direction-type><metronome parentheses="no"'
        + (' print-object="no"' if version in {"4.0", "4.1-draft"} else "")
        + ">"
        + ("<metronome-arrows/>" if version in {"3.1", "4.0", "4.1-draft"} else "")
        + metronome_note("eighth", "start", "start")
        + "<metronome-relation>equals</metronome-relation>"
        + metronome_note("quarter", "stop", "stop")
        + "</metronome></direction-type></direction>"
        "<note><rest/><duration>1</duration><type>quarter</type></note></measure>",
        version=version,
    )
    package = parse_musicxml_timeline_package(source)
    direction = package.documents[0].content.score.annotations.directions[0]
    assert direction.print_object is (False if version in {"4.0", "4.1-draft"} else None)
    assert direction.data is not None and direction.data.metronome is not None
    mark = direction.data.metronome
    assert mark.arrows is (version in {"3.1", "4.0", "4.1-draft"})
    assert mark.relation == "equals"
    assert [note.note_type for note in mark.notes] == ["eighth", "quarter"]
    assert [note.tie for note in mark.notes] == (
        [None, None] if version in {"2.0", "3.0"} else ["start", "stop"]
    )
    assert [note.beams[0].value for note in mark.notes] == ["begin", "end"]
    assert all(note.tuplet is not None and note.tuplet.normal_dots == 1 for note in mark.notes)
    assert package_from_json(package_to_json(package)) == package


@pytest.mark.parametrize("version", ("3.0", "3.1", "4.0", "4.1-draft"))
def test_all_native_percussion_pictogram_values_map(version: str) -> None:
    """TEST-MXML-ANNOTATION-049: every native percussion enum remains distinct."""

    value_types = (
        "glass-value",
        "metal-value",
        "wood-value",
        "pitched-value",
        "membrane-value",
        "effect-value",
        "beater-value",
        "stick-location",
    )
    element_for_type = {name: name.removesuffix("-value") for name in value_types}
    direction_types = []
    expected = []
    for type_name in value_types:
        kind = element_for_type[type_name]
        for value in _enum_values(version, type_name):
            direction_types.append(
                f"<direction-type><percussion><{kind}>{value}</{kind}>"
                "</percussion></direction-type>"
            )
            expected.append((kind, value))
    stick_types = _enum_values(version, "stick-type")
    stick_materials = _enum_values(version, "stick-material")
    for index, stick_type in enumerate(stick_types):
        material = stick_materials[index % len(stick_materials)]
        parentheses = ' parentheses="yes"' if version != "3.0" else ""
        direction_types.append(
            f'<direction-type><percussion><stick tip="up"{parentheses}>'
            f"<stick-type>{stick_type}</stick-type><stick-material>{material}</stick-material>"
            "</stick></percussion></direction-type>"
        )
        expected.append(("stick", None))
    direction_types.extend(
        (
            "<direction-type><percussion><timpani/></percussion></direction-type>",
            "<direction-type><percussion><other-percussion>found object</other-percussion>"
            "</percussion></direction-type>",
        )
    )
    expected.extend((("timpani", ""), ("other-percussion", "found object")))
    source = _partwise(
        '<measure number="1"><attributes><divisions>1</divisions></attributes><direction>'
        + "".join(direction_types)
        + "</direction><note><rest/><duration>1</duration><type>quarter</type></note></measure>",
        version=version,
    )
    directions = parse_musicxml_timeline(source).score.annotations.directions
    actual = []
    for direction in directions:
        assert direction.data is not None and direction.data.percussion is not None
        pictogram = direction.data.percussion
        actual.append((pictogram.kind, pictogram.value))
    assert actual == expected


def test_complex_direction_tampering_fails_closed() -> None:
    """TEST-MXML-ANNOTATION-050: invalid nested direction data is rejected."""

    source = _partwise(
        '<measure number="1"><attributes><divisions>1</divisions></attributes><direction>'
        '<direction-type><principal-voice type="start" symbol="plain">lead'
        "</principal-voice></direction-type></direction>"
        "<note><rest/><duration>1</duration><type>quarter</type></note></measure>",
        version="4.0",
    )
    original = package_to_dict(parse_musicxml_timeline_package(source))
    modified = deepcopy(original)
    data = modified["documents"][0]["content"]["score"]["parts"][0]["measures"][0]["directions"][0][
        "data"
    ]
    data["principal_voice"]["symbol"] = "invalid"
    with pytest.raises(CanonicalSerializationError, match="ANNOTATION_DIRECTION"):
        package_from_dict(modified)


@pytest.mark.parametrize("version", ("1.0", "1.1", "2.0", "3.0", "3.1", "4.0", "4.1-draft"))
def test_ordered_lyric_text_and_elision_map_across_versions(version: str) -> None:
    """TEST-MXML-ANNOTATION-051: multi-segment lyric content remains ordered."""

    xsd = version not in {"1.0", "1.1"}
    identified = version in {"3.1", "4.0", "4.1-draft"}
    extend_type = ' type="start"' if version in {"3.0", "3.1", "4.0", "4.1-draft"} else ""
    lyric_id = ' id="lyric-1"' if identified else ""
    time_only = ' time-only="1,3"' if identified else ""
    print_object = ' print-object="no"' if version not in {"1.0", "1.1", "2.0"} else ""
    elision = (
        '<elision smufl="lyricsElision">_</elision>'
        if identified
        else ("<elision>_</elision>" if xsd else "<elision/>")
    )
    source = _partwise(
        '<measure number="1"><attributes><divisions>1</divisions></attributes>'
        "<note><pitch><step>C</step><octave>4</octave></pitch><duration>1</duration>"
        '<type>quarter</type><lyric number="1" name="verse"'
        f"{lyric_id}{time_only}{print_object}><syllabic>begin</syllabic><text>hel</text>"
        f"{elision}<syllabic>end</syllabic><text>lo</text><extend{extend_type}/>"
        "<end-line/><end-paragraph/></lyric></note></measure>",
        version=version,
    )
    package = parse_musicxml_timeline_package(source)
    lyric = package.documents[0].content.score.annotations.lyrics[0]
    assert (lyric.number, lyric.name, lyric.syllabic, lyric.text) == (
        "1",
        "verse",
        "begin",
        "hel_lo" if xsd else "hello",
    )
    assert [(segment.syllabic, segment.text) for segment in lyric.segments] == [
        ("begin", "hel"),
        ("end", "lo"),
    ]
    assert lyric.segments[1].elision_before == ("_" if xsd else "")
    assert lyric.segments[1].elision_smufl == ("lyricsElision" if identified else None)
    assert lyric.extend_present and lyric.extend == (
        "start" if version in {"3.0", "3.1", "4.0", "4.1-draft"} else None
    )
    assert lyric.end_line and lyric.end_paragraph
    assert lyric.print_object is (False if print_object else None)
    assert lyric.time_only == ("1,3" if identified else None)
    assert lyric.source_id == ("lyric-1" if identified else None)
    assert package_from_json(package_to_json(package)) == package


@pytest.mark.parametrize("kind", ("extend", "laughing", "humming"))
def test_non_text_lyric_vocal_states_are_not_dropped(kind: str) -> None:
    """TEST-MXML-ANNOTATION-052: melisma, laughter, and humming remain distinct."""

    source = _partwise(
        '<measure number="1"><attributes><divisions>1</divisions></attributes>'
        "<note><pitch><step>C</step><octave>4</octave></pitch><duration>1</duration>"
        f"<type>quarter</type><lyric><{kind}/></lyric></note></measure>",
        version="4.0",
    )
    result = parse_musicxml_timeline(source)
    lyric = result.score.annotations.lyrics[0]
    assert lyric.segments == () and lyric.text == ""
    assert (lyric.extend_present, lyric.laughing, lyric.humming) == (
        kind == "extend",
        kind == "laughing",
        kind == "humming",
    )
    assert not any(item.tag == kind for item in result.deferred)


@pytest.mark.parametrize("syllabic", ("single", "begin", "middle", "end"))
def test_all_syllabic_values_remain_distinct(syllabic: str) -> None:
    """TEST-MXML-ANNOTATION-053: the complete syllabic vocabulary survives."""

    source = _partwise(
        '<measure number="1"><attributes><divisions>1</divisions></attributes>'
        "<note><pitch><step>C</step><octave>4</octave></pitch><duration>1</duration>"
        f"<type>quarter</type><lyric><syllabic>{syllabic}</syllabic>"
        "<text>word</text></lyric></note></measure>"
    )
    lyric = parse_musicxml_timeline(source).score.annotations.lyrics[0]
    assert lyric.syllabic == syllabic


def test_lyric_tampering_fails_closed() -> None:
    """TEST-MXML-ANNOTATION-054: incoherent lyric structures are rejected."""

    source = _partwise(
        '<measure number="1"><attributes><divisions>1</divisions></attributes>'
        "<note><pitch><step>C</step><octave>4</octave></pitch><duration>1</duration>"
        "<type>quarter</type><lyric><syllabic>single</syllabic>"
        "<text>word</text></lyric></note></measure>"
    )
    original = package_to_dict(parse_musicxml_timeline_package(source))
    modified = deepcopy(original)
    marker = modified["documents"][0]["content"]["score"]["parts"][0]["measures"][0]["events"][0][
        "lyric_markers"
    ][0]
    marker["segments"][0]["syllabic"] = "invalid"
    with pytest.raises(CanonicalSerializationError, match="ANNOTATION_LYRIC"):
        package_from_dict(modified)


@pytest.mark.parametrize("version", ("1.0", "1.1", "2.0", "3.0", "3.1", "4.0", "4.1-draft"))
def test_all_native_harmony_kinds_map(version: str) -> None:
    """TEST-MXML-ANNOTATION-055: every native chord kind remains distinct."""

    kinds = _enum_values(version, "kind-value") or ("major",)
    harmonies = "".join(
        f"<harmony><root><root-step>C</root-step></root><kind>{kind}</kind></harmony>"
        for kind in kinds
    )
    source = _partwise(
        '<measure number="1"><attributes><divisions>1</divisions></attributes>'
        + harmonies
        + "<note><rest/><duration>1</duration><type>quarter</type></note></measure>",
        version=version,
    )
    result = parse_musicxml_timeline(source)
    assert [harmony.kind for harmony in result.score.annotations.harmonies] == list(kinds)
    assert not any(item.tag in {"root", "root-step", "kind"} for item in result.deferred)


@pytest.mark.parametrize("version", ("3.1", "4.0", "4.1-draft"))
def test_full_pop_harmony_structure_and_offset_round_trip(version: str) -> None:
    """TEST-MXML-ANNOTATION-056: chord, degree, frame, identity, and offset survive."""

    system = ' system="also-top"' if version in {"4.0", "4.1-draft"} else ""
    arrangement = ' arrangement="diagonal"' if system else ""
    source = _partwise(
        '<measure number="1"><attributes><divisions>2</divisions></attributes>'
        '<harmony type="explicit" print-object="no" print-frame="yes"'
        f'{arrangement} id="harmony-1"{system}>'
        "<root><root-step>F</root-step><root-alter>1</root-alter></root>"
        '<kind text="7" use-symbols="yes" stack-degrees="no" '
        'parentheses-degrees="yes" bracket-degrees="no">dominant</kind>'
        "<inversion>1</inversion><bass><bass-step>A</bass-step><bass-alter>-1</bass-alter>"
        '</bass><degree print-object="no"><degree-value symbol="major" text="9">9'
        '</degree-value><degree-alter plus-minus="yes">1</degree-alter>'
        '<degree-type text="add">add</degree-type></degree>'
        '<frame unplayed="x"><frame-strings>6</frame-strings><frame-frets>4</frame-frets>'
        '<first-fret text="I" location="left">1</first-fret>'
        "<frame-note><string>6</string><fret>3</fret><fingering>2</fingering>"
        '<barre type="start"/></frame-note><frame-note><string>1</string><fret>3</fret>'
        '<barre type="stop"/></frame-note></frame><offset>1</offset><staff>1</staff></harmony>'
        "<note><rest/><duration>2</duration><type>quarter</type></note></measure>",
        version=version,
    )
    package = parse_musicxml_timeline_package(source)
    harmony = package.documents[0].content.score.annotations.harmonies[0]
    assert harmony.anchor.onset == Fraction(1, 2)
    assert (harmony.root_step, harmony.root_alter, harmony.kind, harmony.kind_text) == (
        "F",
        1,
        "dominant",
        "7",
    )
    assert (harmony.harmony_type, harmony.print_object, harmony.print_frame) == (
        "explicit",
        False,
        True,
    )
    assert (harmony.arrangement, harmony.source_id, harmony.system_relation) == (
        "diagonal" if arrangement else None,
        "harmony-1",
        "also-top" if system else None,
    )
    chord = harmony.chords[0]
    assert (chord.inversion, chord.bass.step, chord.bass.alter) == (1, "A", -1)
    assert (
        chord.use_symbols,
        chord.stack_degrees,
        chord.parentheses_degrees,
        chord.bracket_degrees,
    ) == (True, False, True, False)
    degree = chord.degrees[0]
    assert (
        degree.value,
        degree.alter,
        degree.degree_type,
        degree.symbol,
        degree.value_text,
        degree.type_text,
        degree.plus_minus,
        degree.print_object,
    ) == (9, 1, "add", "major", "9", "add", True, False)
    assert harmony.frame is not None
    assert (harmony.frame.strings, harmony.frame.frets, harmony.frame.first_fret) == (6, 4, 1)
    assert [(note.string, note.fret, note.barre) for note in harmony.frame.notes] == [
        (6, 3, "start"),
        (1, 3, "stop"),
    ]
    assert package_from_json(package_to_json(package)) == package


@pytest.mark.parametrize(
    "mode", ("major", "minor", "natural minor", "melodic minor", "harmonic minor")
)
def test_numeral_harmony_and_modes_map(mode: str) -> None:
    """TEST-MXML-ANNOTATION-057: functional numeral roots and key context survive."""

    source = _partwise(
        '<measure number="1"><attributes><divisions>1</divisions></attributes>'
        "<harmony><numeral><numeral-root>5</numeral-root><numeral-alter>-1</numeral-alter>"
        f"<numeral-key><numeral-fifths>-3</numeral-fifths><numeral-mode>{mode}"
        "</numeral-mode></numeral-key></numeral><kind>major</kind></harmony>"
        "<note><rest/><duration>1</duration><type>quarter</type></note></measure>",
        version="4.0",
    )
    harmony = parse_musicxml_timeline(source).score.annotations.harmonies[0]
    assert harmony.root_step is None
    numeral = harmony.chords[0].numeral
    assert numeral is not None and (
        numeral.root,
        numeral.alter,
        numeral.key_fifths,
        numeral.key_mode,
    ) == (5, -1, -3, mode)


def test_stacked_and_deprecated_function_harmonies_remain_ordered() -> None:
    """TEST-MXML-ANNOTATION-058: stacked chord groups retain distinct source forms."""

    source = _partwise(
        '<measure number="1"><attributes><divisions>1</divisions></attributes>'
        "<harmony><function>V</function><kind>dominant</kind>"
        "<root><root-step>D</root-step></root><kind>minor</kind></harmony>"
        "<note><rest/><duration>1</duration><type>quarter</type></note></measure>",
        version="3.1",
    )
    harmony = parse_musicxml_timeline(source).score.annotations.harmonies[0]
    assert len(harmony.chords) == 2
    assert (harmony.chords[0].function, harmony.chords[0].kind) == ("V", "dominant")
    assert (harmony.chords[1].root_step, harmony.chords[1].kind) == ("D", "minor")


@pytest.mark.parametrize("degree_type", ("add", "alter", "subtract"))
@pytest.mark.parametrize("symbol", ("major", "minor", "augmented", "diminished", "half-diminished"))
def test_degree_type_and_symbol_vocabularies_map(degree_type: str, symbol: str) -> None:
    """TEST-MXML-ANNOTATION-059: degree operation and symbol enums remain distinct."""

    source = _partwise(
        '<measure number="1"><attributes><divisions>1</divisions></attributes>'
        "<harmony><root><root-step>C</root-step></root><kind>major</kind><degree>"
        f'<degree-value symbol="{symbol}">5</degree-value><degree-alter>0</degree-alter>'
        f"<degree-type>{degree_type}</degree-type></degree></harmony>"
        "<note><rest/><duration>1</duration><type>quarter</type></note></measure>"
    )
    degree = parse_musicxml_timeline(source).score.annotations.harmonies[0].chords[0].degrees[0]
    assert (degree.degree_type, degree.symbol) == (degree_type, symbol)


def test_harmony_tampering_fails_closed() -> None:
    """TEST-MXML-ANNOTATION-060: incoherent harmony structures are rejected."""

    source = _partwise(
        '<measure number="1"><attributes><divisions>1</divisions></attributes>'
        "<harmony><root><root-step>C</root-step></root><kind>major</kind></harmony>"
        "<note><rest/><duration>1</duration><type>quarter</type></note></measure>"
    )
    original = package_to_dict(parse_musicxml_timeline_package(source))
    modified = deepcopy(original)
    harmony = modified["documents"][0]["content"]["score"]["parts"][0]["measures"][0]["harmonies"][
        0
    ]
    harmony["chords"][0]["kind"] = "invalid"
    with pytest.raises(CanonicalSerializationError, match="ANNOTATION_HARMONY"):
        package_from_dict(modified)


def test_semantic_direction_span_details_and_pedal_transitions_round_trip() -> None:
    """TEST-MXML-ANNOTATION-061: line semantics and every pedal transition survive."""

    source = _partwise(
        '<measure number="1"><attributes><divisions>1</divisions></attributes>'
        '<direction><direction-type><wedge number="1" type="crescendo" spread="12.5" '
        'niente="yes" line-type="dashed" dash-length="3" space-length="2"/>'
        "</direction-type></direction>"
        '<direction><direction-type><bracket number="2" type="start" line-end="arrow" '
        'end-length="5" line-type="dotted" dash-length="1" space-length="2"/>'
        "</direction-type></direction>"
        '<direction><direction-type><octave-shift number="3" type="down" size="15" '
        'dash-length="4" space-length="3"/></direction-type></direction>'
        '<direction><direction-type><pedal number="4" type="start" line="yes" sign="yes" '
        'abbreviated="no"/></direction-type></direction>'
        '<direction><direction-type><pedal number="4" type="change" line="yes" sign="yes"/>'
        "</direction-type></direction>"
        '<direction><direction-type><pedal number="4" type="continue" line="yes"/>'
        "</direction-type></direction>"
        '<direction><direction-type><pedal number="4" type="discontinue" line="yes"/>'
        "</direction-type></direction>"
        '<direction><direction-type><pedal number="4" type="resume" line="yes"/>'
        "</direction-type></direction>"
        "<note><rest/><duration>1</duration><type>quarter</type></note>"
        '<direction><direction-type><wedge number="1" type="stop" spread="0"/>'
        "</direction-type></direction>"
        '<direction><direction-type><bracket number="2" type="stop" line-end="none"/>'
        "</direction-type></direction>"
        '<direction><direction-type><octave-shift number="3" type="stop" size="15"/>'
        "</direction-type></direction>"
        '<direction><direction-type><pedal number="4" type="stop" line="yes" sign="yes"/>'
        "</direction-type></direction>"
        '<direction><direction-type><pedal number="5" type="sostenuto" line="no" sign="yes"/>'
        "</direction-type></direction>"
        '<direction><direction-type><pedal number="5" type="stop" line="no" sign="yes"/>'
        "</direction-type></direction></measure>",
        version="4.0",
    )
    package = parse_musicxml_timeline_package(source)
    spans = {
        span.number: span for span in package.documents[0].content.score.annotations.time_spans
    }
    wedge = spans["1"].endpoints[0]
    assert (wedge.source_type, wedge.spread, wedge.niente, wedge.line_type) == (
        "crescendo",
        Fraction(25, 2),
        True,
        "dashed",
    )
    assert (wedge.dash_length, wedge.space_length) == (3, 2)
    bracket = spans["2"].endpoints[0]
    assert (bracket.line_end, bracket.end_length, bracket.line_type) == (
        "arrow",
        5,
        "dotted",
    )
    assert spans["3"].endpoints[0].octave_size == 15
    assert [endpoint.source_type for endpoint in spans["4"].endpoints] == [
        "start",
        "change",
        "continue",
        "discontinue",
        "resume",
        "stop",
    ]
    assert [endpoint.action for endpoint in spans["4"].endpoints] == [
        "start",
        "continue",
        "continue",
        "continue",
        "continue",
        "stop",
    ]
    pedal_marks = [
        direction
        for direction in package.documents[0].content.score.annotations.directions
        if direction.family == "pedal"
    ]
    assert [direction.value for direction in pedal_marks] == ["sostenuto", "stop"]
    assert [direction.pedal_number for direction in pedal_marks] == ["5", "5"]
    assert [direction.pedal_line for direction in pedal_marks] == [False, False]
    assert [direction.pedal_sign for direction in pedal_marks] == [True, True]
    assert "5" not in spans
    assert package_from_json(package_to_json(package)) == package


@pytest.mark.parametrize("line_end", ("up", "down", "both", "arrow", "none"))
def test_all_bracket_line_end_values_map(line_end: str) -> None:
    """TEST-MXML-ANNOTATION-062: every native bracket endpoint remains distinct."""

    source = _partwise(
        '<measure number="1"><attributes><divisions>1</divisions></attributes>'
        f'<direction><direction-type><bracket type="start" line-end="{line_end}"/>'
        "</direction-type></direction><note><rest/><duration>1</duration><type>quarter</type>"
        '</note><direction><direction-type><bracket type="stop" line-end="none"/>'
        "</direction-type></direction></measure>"
    )
    marker = parse_musicxml_timeline(source).score.annotations.time_spans[0].endpoints[0]
    assert marker.line_end == line_end


def test_direction_span_semantic_tampering_fails_closed() -> None:
    """TEST-MXML-ANNOTATION-063: invalid family-specific span data is rejected."""

    source = _partwise(
        '<measure number="1"><attributes><divisions>1</divisions></attributes>'
        '<direction><direction-type><wedge type="crescendo" spread="10"/>'
        "</direction-type></direction><note><rest/><duration>1</duration><type>quarter</type>"
        '</note><direction><direction-type><wedge type="stop"/></direction-type>'
        "</direction></measure>"
    )
    modified = package_to_dict(parse_musicxml_timeline_package(source))
    marker = modified["documents"][0]["content"]["score"]["parts"][0]["measures"][0][
        "time_span_markers"
    ][0]
    marker["octave_size"] = 8
    with pytest.raises(CanonicalSerializationError, match="ANNOTATION_TIME_SPAN"):
        package_from_dict(modified)


def test_tie_and_slur_semantics_round_trip() -> None:
    """TEST-MXML-ANNOTATION-064: tie playback scope and slur geometry semantics survive."""

    source = _partwise(
        '<measure number="1"><attributes><divisions>1</divisions></attributes>'
        "<note><pitch><step>C</step><octave>4</octave></pitch><duration>1</duration>"
        '<tie type="start" time-only="1, 3"/><type>quarter</type><notations>'
        '<tied number="1" type="start" placement="above" orientation="over" '
        'line-type="dashed" dash-length="2" space-length="1" id="tied-start"/>'
        '<slur number="2" type="start" placement="below" orientation="under" '
        'line-type="dotted" dash-length="3" space-length="2" id="slur-start"/>'
        "</notations></note>"
        "<note><pitch><step>C</step><octave>4</octave></pitch><duration>1</duration>"
        '<tie type="stop" time-only="1, 3"/><type>quarter</type><notations>'
        '<tied number="1" type="stop" placement="above" orientation="over" '
        'line-type="dashed" dash-length="2" space-length="1" id="tied-stop"/>'
        '<slur number="2" type="continue" placement="below" orientation="under" '
        'line-type="dotted" dash-length="3" space-length="2" id="slur-continue"/>'
        "</notations></note>"
        "<note><pitch><step>D</step><octave>4</octave></pitch><duration>1</duration>"
        '<type>quarter</type><notations><slur number="2" type="stop" placement="below" '
        'orientation="under" line-type="dotted" dash-length="3" space-length="2" '
        'id="slur-stop"/></notations></note></measure>'
    )
    package = parse_musicxml_timeline_package(source)
    spans = {span.kind: span for span in package.documents[0].content.score.annotations.spans}
    assert [endpoint.time_only for endpoint in spans["sounding-tie"].endpoints] == [
        "1, 3",
        "1, 3",
    ]
    tied = spans["notated-tie"].endpoints[0]
    assert (
        tied.placement,
        tied.orientation,
        tied.line_type,
        tied.dash_length,
        tied.space_length,
        tied.source_id,
    ) == ("above", "over", "dashed", 2, 1, "tied-start")
    assert [endpoint.action for endpoint in spans["slur"].endpoints] == [
        "start",
        "continue",
        "stop",
    ]
    assert all(endpoint.orientation == "under" for endpoint in spans["slur"].endpoints)
    assert package_from_json(package_to_json(package)) == package


def test_note_span_semantic_tampering_fails_closed() -> None:
    """TEST-MXML-ANNOTATION-065: family-incoherent tie data is rejected."""

    original = package_to_dict(parse_musicxml_timeline_package(_spanned_score()))
    marker = original["documents"][0]["content"]["score"]["parts"][0]["measures"][0]["events"][0][
        "span_markers"
    ][0]
    marker["orientation"] = "over"
    with pytest.raises(CanonicalSerializationError, match="ANNOTATION_SPAN_MARKER"):
        package_from_dict(original)


def test_full_figured_bass_semantics_round_trip() -> None:
    """TEST-MXML-ANNOTATION-066: figures, extensions, controls, and duration survive."""

    source = _partwise(
        '<measure number="1"><attributes><divisions>2</divisions></attributes>'
        '<figured-bass parentheses="yes" print-object="no" print-dot="yes" '
        'print-spacing="no" placement="above" id="bass-1">'
        "<figure><prefix>sharp</prefix><figure-number>6</figure-number>"
        '<suffix>natural</suffix><extend type="start"/></figure>'
        '<figure><figure-number>4</figure-number><extend type="continue"/></figure>'
        '<figure><figure-number>3</figure-number><extend type="stop"/></figure>'
        "<duration>3</duration></figured-bass>"
        "<note><pitch><step>C</step><octave>4</octave></pitch><duration>2</duration>"
        "<type>quarter</type></note></measure>"
    )
    package = parse_musicxml_timeline_package(source)
    bass = package.documents[0].content.score.annotations.figured_bass[0]
    assert bass.duration == Fraction(3, 2)
    assert (
        bass.parentheses,
        bass.print_object,
        bass.print_dot,
        bass.print_spacing,
        bass.placement,
        bass.source_id,
    ) == (True, False, True, False, "above", "bass-1")
    assert [figure.extend for figure in bass.figures] == ["start", "continue", "stop"]
    assert all(figure.extend_present for figure in bass.figures)
    assert package_from_json(package_to_json(package)) == package


def test_figured_bass_semantic_tampering_fails_closed() -> None:
    """TEST-MXML-ANNOTATION-067: incoherent figured-bass extensions are rejected."""

    source = _partwise(
        '<measure number="1"><attributes><divisions>1</divisions></attributes>'
        '<figured-bass><figure><figure-number>6</figure-number><extend type="start"/>'
        "</figure></figured-bass><note><rest/><duration>1</duration><type>quarter</type>"
        "</note></measure>"
    )
    modified = package_to_dict(parse_musicxml_timeline_package(source))
    figure = modified["documents"][0]["content"]["score"]["parts"][0]["measures"][0][
        "figured_bass"
    ][0]["figures"][0]
    figure["extend_present"] = False
    with pytest.raises(CanonicalSerializationError, match="ANNOTATION_FIGURED_BASS"):
        package_from_dict(modified)


def test_barline_navigation_repeat_and_ending_semantics_round_trip() -> None:
    """TEST-MXML-ANNOTATION-068: barline navigation and repeat semantics survive."""

    source = _partwise(
        '<measure number="1"><attributes><divisions>1</divisions></attributes>'
        "<note><rest/><duration>1</duration><type>quarter</type></note>"
        '<barline location="right" divisions="2" segno="legacy-segno" '
        'coda="legacy-coda" id="barline-1"><bar-style>heavy-light</bar-style>'
        '<segno smufl="segno" id="segno-1"/><coda smufl="coda" id="coda-1"/>'
        '<ending number="1,2" type="start" print-object="no" system="also-top">'
        '1.–2.</ending><repeat direction="backward" times="3" '
        'winged="double-curved" after-jump="yes"/></barline></measure>',
        version="4.1-draft",
    )
    package = parse_musicxml_timeline_package(source)
    barline = package.documents[0].content.score.parts[0].measures[0].barlines[0]
    assert (barline.location, barline.style, barline.divisions, barline.source_id) == (
        "right",
        "heavy-light",
        2,
        "barline-1",
    )
    assert (barline.repeat_direction, barline.repeat_times) == ("backward", "3")
    assert (barline.repeat_winged, barline.repeat_after_jump) == ("double-curved", True)
    assert (
        barline.ending_number,
        barline.ending_type,
        barline.ending_text,
        barline.ending_print_object,
        barline.ending_system_relation,
    ) == ("1,2", "start", "1.–2.", False, "also-top")
    assert [(mark.kind, mark.token, mark.source_id, mark.smufl) for mark in barline.navigation] == [
        ("segno", "legacy-segno", None, None),
        ("segno", None, "segno-1", "segno"),
        ("coda", "legacy-coda", None, None),
        ("coda", None, "coda-1", "coda"),
    ]
    assert package_from_json(package_to_json(package)) == package


def test_all_measure_style_semantics_round_trip() -> None:
    """TEST-MXML-ANNOTATION-069: measure, beat, slash, and multirest notation survive."""

    source = _partwise(
        '<measure number="1"><attributes><divisions>4</divisions>'
        '<measure-style number="1" id="multi"><multiple-rest use-symbols="yes">4'
        "</multiple-rest></measure-style>"
        '<measure-style number="1" id="measure"><measure-repeat type="start" slashes="2">2'
        "</measure-repeat></measure-style>"
        '<measure-style number="1" id="beat"><beat-repeat type="start" slashes="1" '
        'use-dots="yes"><slash-type>quarter</slash-type><slash-dot/></beat-repeat>'
        "</measure-style>"
        '<measure-style number="1" id="slash"><slash type="start" use-dots="yes" '
        'use-stems="no"><slash-type>eighth</slash-type><slash-dot/><slash-dot/>'
        "</slash></measure-style></attributes>"
        "<note><rest/><duration>4</duration><type>quarter</type></note></measure>"
    )
    package = parse_musicxml_timeline_package(source)
    styles = package.documents[0].content.score.parts[0].measures[0].attributes[0].measure_styles
    assert [(style.kind, style.value, style.action) for style in styles] == [
        ("multiple-rest", 4, None),
        ("measure-repeat", 2, "start"),
        ("beat-repeat", None, "start"),
        ("slash", None, "start"),
    ]
    assert (styles[0].use_symbols, styles[1].slashes) == (True, 2)
    assert (styles[2].slashes, styles[2].use_dots, styles[2].slash_type) == (
        1,
        True,
        "quarter",
    )
    assert (styles[3].use_stems, styles[3].slash_type, styles[3].slash_dots) == (
        False,
        "eighth",
        2,
    )
    assert package_from_json(package_to_json(package)) == package


@pytest.mark.parametrize("version", ("2.0", "3.0", "3.1", "4.0", "4.1-draft"))
def test_all_native_bar_styles_map(version: str) -> None:
    """TEST-MXML-ANNOTATION-070: every native bar style remains distinct."""

    styles = _enum_values(version, "bar-style")
    barlines = "".join(
        f'<barline location="middle"><bar-style>{style}</bar-style></barline>' for style in styles
    )
    source = _partwise(
        '<measure number="1"><attributes><divisions>1</divisions></attributes>'
        "<note><rest/><duration>1</duration><type>quarter</type></note>"
        f"{barlines}</measure>",
        version=version,
    )
    result = parse_musicxml_timeline(source)
    assert [barline.style for barline in result.score.parts[0].measures[0].barlines] == list(styles)


def test_barline_and_measure_style_tampering_fails_closed() -> None:
    """TEST-MXML-ANNOTATION-071: invalid repeat notation is rejected."""

    source = _partwise(
        '<measure number="1"><attributes><divisions>1</divisions>'
        "<measure-style><multiple-rest>2</multiple-rest></measure-style></attributes>"
        "<note><rest/><duration>1</duration><type>quarter</type></note>"
        "<barline><bar-style>regular</bar-style></barline></measure>"
    )
    original = package_to_dict(parse_musicxml_timeline_package(source))
    modified = deepcopy(original)
    modified["documents"][0]["content"]["score"]["parts"][0]["measures"][0]["barlines"][0][
        "repeat_winged"
    ] = "invalid"
    with pytest.raises(CanonicalSerializationError, match="TEMPORAL_BARLINE"):
        package_from_dict(modified)

    modified = deepcopy(original)
    modified["documents"][0]["content"]["score"]["parts"][0]["measures"][0]["attributes"][0][
        "measure_styles"
    ][0]["value"] = 0
    with pytest.raises(CanonicalSerializationError, match="TEMPORAL_MEASURE_STYLE"):
        package_from_dict(modified)


def test_rich_written_note_and_tuplet_semantics_round_trip() -> None:
    """TEST-MXML-ANNOTATION-072: accidentals, beams, stems, and tuplets survive."""

    source = _partwise(
        '<measure number="1"><attributes><divisions>2</divisions></attributes>'
        "<note><pitch><step>F</step><alter>0.5</alter><octave>4</octave></pitch>"
        '<duration>1</duration><type size="cue">eighth</type><dot/>'
        '<accidental cautionary="yes" editorial="no" parentheses="yes" bracket="no" '
        'size="large" smufl="accidentalSharp">quarter-sharp</accidental>'
        "<time-modification><actual-notes>3</actual-notes><normal-notes>2</normal-notes>"
        "<normal-type>eighth</normal-type><normal-dot/></time-modification><stem>double</stem>"
        '<beam number="1" repeater="yes" fan="accel" id="beam-1">begin</beam>'
        '<notations><tuplet number="2" type="start" bracket="yes" show-number="both" '
        'show-type="actual" line-shape="curved" placement="above" id="tuplet-1">'
        "<tuplet-actual><tuplet-number>3</tuplet-number><tuplet-type>eighth</tuplet-type>"
        "<tuplet-dot/></tuplet-actual><tuplet-normal><tuplet-number>2</tuplet-number>"
        "<tuplet-type>quarter</tuplet-type></tuplet-normal></tuplet></notations></note>"
        "<note><pitch><step>G</step><octave>4</octave></pitch><duration>1</duration>"
        '<type>eighth</type><beam number="1" fan="none">end</beam>'
        '<notations><tuplet number="2" type="stop"/></notations></note></measure>'
    )
    package = parse_musicxml_timeline_package(source)
    event = package.documents[0].content.score.parts[0].measures[0].events[0]
    assert event.accidental is not None
    assert (
        event.accidental.value,
        event.accidental.cautionary,
        event.accidental.editorial,
        event.accidental.parentheses,
        event.accidental.bracket,
        event.accidental.size,
        event.accidental.smufl,
    ) == ("quarter-sharp", True, False, True, False, "large", "accidentalSharp")
    assert (event.stem, event.written_size) == ("double", "cue")
    assert (event.beams[0].repeater, event.beams[0].fan, event.beams[0].source_id) == (
        True,
        "accel",
        "beam-1",
    )
    tuplet = event.tuplets[0]
    assert (
        tuplet.bracket,
        tuplet.show_number,
        tuplet.show_type,
        tuplet.line_shape,
        tuplet.placement,
        tuplet.source_id,
    ) == (True, "both", "actual", "curved", "above", "tuplet-1")
    assert tuplet.actual is not None and (
        tuplet.actual.number,
        tuplet.actual.note_type,
        tuplet.actual.dots,
    ) == (3, "eighth", 1)
    assert tuplet.normal is not None and (
        tuplet.normal.number,
        tuplet.normal.note_type,
        tuplet.normal.dots,
    ) == (2, "quarter", 0)
    assert package_from_json(package_to_json(package)) == package


@pytest.mark.parametrize("version", ("2.0", "3.0", "3.1", "4.0", "4.1-draft"))
def test_all_native_written_accidentals_map(version: str) -> None:
    """TEST-MXML-ANNOTATION-073: every native written accidental remains distinct."""

    values = _enum_values(version, "accidental-value")
    notes = "".join(
        "<note><pitch><step>C</step><octave>4</octave></pitch><duration>1</duration>"
        f"<type>quarter</type><accidental>{value}</accidental></note>"
        for value in values
    )
    source = _partwise(
        f'<measure number="1"><attributes><divisions>1</divisions></attributes>{notes}</measure>',
        version=version,
    )
    events = parse_musicxml_timeline(source).score.parts[0].measures[0].events
    assert [event.accidental.value for event in events if event.accidental is not None] == list(
        values
    )


def test_written_note_semantic_tampering_fails_closed() -> None:
    """TEST-MXML-ANNOTATION-074: malformed written-note semantics are rejected."""

    source = _partwise(
        '<measure number="1"><attributes><divisions>1</divisions></attributes>'
        "<note><pitch><step>C</step><octave>4</octave></pitch><duration>1</duration>"
        "<type>quarter</type><accidental>natural</accidental><stem>up</stem></note></measure>"
    )
    modified = package_to_dict(parse_musicxml_timeline_package(source))
    event = modified["documents"][0]["content"]["score"]["parts"][0]["measures"][0]["events"][0]
    event["stem"] = "sideways"
    with pytest.raises(CanonicalSerializationError, match="TEMPORAL_WRITTEN_NOTATION"):
        package_from_dict(modified)


def test_rich_key_time_clef_and_staff_state_round_trip() -> None:
    """TEST-MXML-ANNOTATION-075: full semantic attributes state survives."""

    source = _partwise(
        '<measure number="1"><attributes><divisions>2</divisions>'
        '<key number="1" print-object="no" id="key-traditional">'
        '<cancel location="before-barline">2</cancel><fifths>3</fifths><mode>major</mode>'
        '<key-octave number="1" cancel="yes">5</key-octave></key>'
        '<key number="2" id="key-nontraditional"><key-step>F</key-step>'
        '<key-alter>0.5</key-alter><key-accidental smufl="accidentalSharp">'
        'quarter-sharp</key-accidental><key-octave number="1">4</key-octave></key>'
        '<time number="1" symbol="normal" separator="diagonal" print-object="no" id="time-1">'
        '<beats>3</beats><beat-type>4</beat-type><interchangeable symbol="cut" '
        'separator="horizontal"><time-relation>equals</time-relation><beats>6</beats>'
        "<beat-type>8</beat-type></interchangeable></time>"
        '<time number="2" id="time-2"><senza-misura>X</senza-misura></time>'
        '<staves>2</staves><part-symbol top-staff="1" bottom-staff="2">brace</part-symbol>'
        '<instruments>1</instruments><clef number="1" additional="yes" size="cue" '
        'after-barline="yes" print-object="no" id="clef-1"><sign>G</sign><line>2</line>'
        "<clef-octave-change>1</clef-octave-change></clef>"
        '<staff-details number="2" show-frets="letters" print-object="no">'
        "<staff-type>alternate</staff-type><staff-lines>6</staff-lines>"
        '<staff-tuning line="1"><tuning-step>E</tuning-step><tuning-alter>-0.5</tuning-alter>'
        "<tuning-octave>2</tuning-octave></staff-tuning><capo>2</capo>"
        "<staff-size>85.5</staff-size></staff-details></attributes>"
        "<note><rest/><duration>2</duration><type>quarter</type></note></measure>"
    )
    package = parse_musicxml_timeline_package(source)
    attributes = package.documents[0].content.score.parts[0].measures[0].attributes[0]
    traditional, nontraditional = attributes.keys
    assert (
        traditional.fifths,
        traditional.mode,
        traditional.cancel,
        traditional.cancel_location,
        traditional.print_object,
        traditional.source_id,
    ) == (3, "major", 2, "before-barline", False, "key-traditional")
    assert traditional.octaves[0].cancel is True
    assert (
        nontraditional.alterations[0].step,
        nontraditional.alterations[0].alter,
        nontraditional.alterations[0].accidental,
        nontraditional.alterations[0].accidental_smufl,
    ) == ("F", Fraction(1, 2), "quarter-sharp", "accidentalSharp")
    measured, senza = attributes.times
    assert (measured.symbol, measured.separator, measured.print_object) == (
        "normal",
        "diagonal",
        False,
    )
    assert measured.interchangeable is not None and (
        measured.interchangeable.beats,
        measured.interchangeable.beat_types,
        measured.interchangeable.relation,
    ) == (("6",), (8,), "equals")
    assert senza.senza_misura == "X"
    assert attributes.part_symbol is not None and attributes.part_symbol.value == "brace"
    clef = attributes.clefs[0]
    assert (clef.additional, clef.size, clef.after_barline, clef.print_object, clef.source_id) == (
        True,
        "cue",
        True,
        False,
        "clef-1",
    )
    details = attributes.staff_details[0]
    assert (
        details.staff,
        details.staff_type,
        details.lines,
        details.capo,
        details.size,
        details.show_frets,
        details.print_object,
    ) == ("2", "alternate", 6, 2, Fraction(171, 2), "letters", False)
    assert (
        details.tunings[0].line,
        details.tunings[0].step,
        details.tunings[0].alter,
        details.tunings[0].octave,
    ) == (1, "E", Fraction(-1, 2), 2)
    assert package_from_json(package_to_json(package)) == package


def test_attribute_semantic_vocabularies_map() -> None:
    """TEST-MXML-ANNOTATION-076: native clef, time, and staff vocabularies survive."""

    clefs = "".join(
        f"<clef><sign>{sign}</sign></clef>" for sign in _enum_values("4.0", "clef-sign")
    )
    times = "".join(
        f'<time symbol="{symbol}"><beats>4</beats><beat-type>4</beat-type></time>'
        for symbol in _enum_values("4.0", "time-symbol")
    )
    details = "".join(
        f"<staff-details><staff-type>{staff_type}</staff-type><staff-lines>5</staff-lines>"
        "</staff-details>"
        for staff_type in _enum_values("4.0", "staff-type")
    )
    source = _partwise(
        '<measure number="1"><attributes><divisions>1</divisions>'
        f"{times}<staves>1</staves>{clefs}{details}</attributes>"
        "<note><rest/><duration>1</duration><type>quarter</type></note></measure>"
    )
    attributes = parse_musicxml_timeline(source).score.parts[0].measures[0].attributes[0]
    assert [item.sign for item in attributes.clefs] == list(_enum_values("4.0", "clef-sign"))
    assert [item.symbol for item in attributes.times] == list(_enum_values("4.0", "time-symbol"))
    assert [item.staff_type for item in attributes.staff_details] == list(
        _enum_values("4.0", "staff-type")
    )


def test_attribute_semantic_tampering_fails_closed() -> None:
    """TEST-MXML-ANNOTATION-077: incoherent key/staff state is rejected."""

    source = _partwise(
        '<measure number="1"><attributes><divisions>1</divisions>'
        "<key><fifths>0</fifths></key><time><beats>4</beats><beat-type>4</beat-type>"
        "</time><clef><sign>G</sign><line>2</line></clef></attributes>"
        "<note><rest/><duration>1</duration><type>quarter</type></note></measure>"
    )
    modified = package_to_dict(parse_musicxml_timeline_package(source))
    attributes = modified["documents"][0]["content"]["score"]["parts"][0]["measures"][0][
        "attributes"
    ][0]
    attributes["clefs"][0]["sign"] = "invalid"
    with pytest.raises(CanonicalSerializationError, match="TEMPORAL_ATTRIBUTES"):
        package_from_dict(modified)


def test_score_structure_identity_and_metadata_round_trip() -> None:
    """TEST-MXML-ANNOTATION-078: score, group, part, instrument, and measure identity survive."""

    source = (
        b'<?xml version="1.0" encoding="utf-8"?>'
        b'<!DOCTYPE score-partwise PUBLIC "-//Recordare//DTD MusicXML 4.0 Partwise//EN" '
        b'"http://www.musicxml.org/dtds/partwise.dtd"><score-partwise version="4.0">'
        b"<work><work-title>Structured Work</work-title></work>"
        b"<movement-number>II</movement-number><movement-title>Movement</movement-title>"
        b'<identification><creator type="composer">Example Composer</creator></identification>'
        b'<part-list><part-group number="2" type="start"><group-name>Winds</group-name>'
        b"<group-abbreviation>W.</group-abbreviation><group-symbol>bracket</group-symbol>"
        b"<group-barline>Mensurstrich</group-barline></part-group>"
        b'<score-part id="P1"><part-name>Flute</part-name>'
        b"<part-abbreviation>Fl.</part-abbreviation>"
        b'<score-instrument id="P1-I1"><instrument-name>Concert Flute</instrument-name>'
        b"<instrument-abbreviation>Fl.</instrument-abbreviation></score-instrument>"
        b'</score-part><part-group number="2" type="stop"/></part-list><part id="P1">'
        b'<measure number="A" implicit="yes" non-controlling="yes">'
        b"<attributes><divisions>1</divisions></attributes>"
        b"<note><pitch><step>C</step><octave>5</octave></pitch><duration>1</duration>"
        b'<instrument id="P1-I1"/><type>quarter</type></note></measure></part></score-partwise>'
    )
    package = parse_musicxml_timeline_package(source)
    score = package.documents[0].content.score
    assert (score.work_title, score.movement_number, score.movement_title) == (
        "Structured Work",
        "II",
        "Movement",
    )
    assert score.creators == (("composer", "Example Composer"),)
    groups = [(group.number, group.action, group.symbol, group.barline) for group in score.groups]
    assert groups == [
        ("2", "start", "bracket", "Mensurstrich"),
        ("2", "stop", None, None),
    ]
    part = score.parts[0]
    assert (part.id, part.name, part.abbreviation) == ("P1", "Flute", "Fl.")
    assert (part.instruments[0].id, part.instruments[0].name) == (
        "P1-I1",
        "Concert Flute",
    )
    measure = part.measures[0]
    assert (measure.number, measure.implicit, measure.non_controlling) == (
        "A",
        True,
        True,
    )
    assert package_from_json(package_to_json(package)) == package


@pytest.mark.parametrize("version", ("1.0", "1.1", "2.0", "3.0", "3.1", "4.0", "4.1-draft"))
def test_pitch_rest_and_unpitched_kinds_map_across_versions(version: str) -> None:
    """TEST-MXML-ANNOTATION-079: all three temporal event kinds retain pitch/display data."""

    source = _partwise(
        '<measure number="1"><attributes><divisions>1</divisions></attributes>'
        "<note><pitch><step>D</step><alter>-0.5</alter><octave>4</octave></pitch>"
        "<duration>1</duration><type>quarter</type></note>"
        "<note><rest><display-step>B</display-step><display-octave>3</display-octave></rest>"
        "<duration>1</duration><type>quarter</type></note>"
        "<note><unpitched><display-step>F</display-step><display-octave>5</display-octave>"
        "</unpitched><duration>1</duration><type>quarter</type></note></measure>",
        version=version,
    )
    events = parse_musicxml_timeline(source).score.parts[0].measures[0].events
    assert [event.kind for event in events] == ["pitched", "rest", "unpitched"]
    assert events[0].pitch is not None and events[0].pitch.alter == Fraction(-1, 2)
    assert events[1].display_position is not None and (
        events[1].display_position.step,
        events[1].display_position.octave,
    ) == ("B", 3)
    assert events[2].display_position is not None and (
        events[2].display_position.step,
        events[2].display_position.octave,
    ) == ("F", 5)


def test_score_structure_tampering_fails_closed() -> None:
    """TEST-MXML-ANNOTATION-080: invalid group structure is rejected."""

    source = _partwise(
        '<measure number="1"><attributes><divisions>1</divisions></attributes>'
        "<note><rest/><duration>1</duration><type>quarter</type></note></measure>"
    )
    modified = package_to_dict(parse_musicxml_timeline_package(source))
    modified["documents"][0]["content"]["score"]["groups"] = [
        {
            "number": "1",
            "action": "invalid",
            "name": None,
            "abbreviation": None,
            "symbol": None,
            "barline": None,
            "source_order": 1,
            "group_time": False,
            "source_id": None,
            "editorial": None,
            "name_display": None,
            "abbreviation_display": None,
        }
    ]
    with pytest.raises(CanonicalSerializationError, match="TEMPORAL_PART_GROUP"):
        package_from_dict(modified)


def test_overlapping_part_groups_validate_and_round_trip() -> None:
    """TEST-MXML-CORPUS-015: independently numbered part groups may overlap."""

    source = _partwise(
        '<measure number="1"><attributes><divisions>1</divisions></attributes>'
        "<note><rest/><duration>1</duration><type>quarter</type></note></measure>",
        part_list=(
            '<part-group number="1" type="start"><group-name>First</group-name></part-group>'
            '<score-part id="P1"><part-name>Piano</part-name></score-part>'
            '<part-group number="2" type="start"><group-name>Second</group-name></part-group>'
            '<part-group number="1" type="stop"/>'
            '<part-group number="2" type="stop"/>'
        ),
    )
    package = parse_musicxml_timeline_package(source)
    assert [
        (group.number, group.action) for group in package.documents[0].content.score.groups
    ] == [
        ("1", "start"),
        ("2", "start"),
        ("1", "stop"),
        ("2", "stop"),
    ]
    assert package_from_json(package_to_json(package)) == package


def test_empty_accordion_registration_is_explicit_and_valid() -> None:
    """TEST-MXML-CORPUS-016: schema-valid empty registration remains explicit."""

    source = _partwise(
        '<measure number="1"><attributes><divisions>1</divisions></attributes>'
        "<direction><direction-type><accordion-registration/>"
        "</direction-type></direction>"
        "<note><rest/><duration>1</duration><type>quarter</type></note></measure>"
    )
    package = parse_musicxml_timeline_package(source)
    mark = package.documents[0].content.score.parts[0].measures[0].directions[0]
    assert mark.data is not None
    assert mark.data.accordion is not None
    assert (
        mark.data.accordion.high,
        mark.data.accordion.middle,
        mark.data.accordion.low,
    ) == (False, None, False)
    assert package_from_json(package_to_json(package)) == package


def test_source_metadata_round_trip() -> None:
    """TEST-MXML-ANNOTATION-081: source and encoding metadata remain typed and ordered."""

    source = (
        b'<?xml version="1.0" encoding="utf-8"?>'
        b'<!DOCTYPE score-partwise PUBLIC "-//Recordare//DTD MusicXML 4.0 Partwise//EN" '
        b'"http://www.musicxml.org/dtds/partwise.dtd"><score-partwise version="4.0">'
        b"<work><work-number>Op. 1</work-number><work-title>Metadata Work</work-title></work>"
        b'<identification><creator type="composer">Composer</creator>'
        b'<rights type="music">Copyright</rights><encoding><encoding-date>2026-09-22'
        b'</encoding-date><encoder type="music">Encoder</encoder><software>TeachMeMusic'
        b"</software><encoding-description>Exact test</encoding-description>"
        b'<supports type="yes" element="beam" attribute="number" value="1"/></encoding>'
        b'<source>Source edition</source><relation type="music">Related score</relation>'
        b'<miscellaneous><miscellaneous-field name="catalogue">TMM-1</miscellaneous-field>'
        b'</miscellaneous></identification><part-list><score-part id="P1">'
        b'<part-name>Piano</part-name></score-part></part-list><part id="P1">'
        b'<measure number="1"><attributes><divisions>1</divisions></attributes>'
        b"<note><rest/><duration>1</duration><type>quarter</type></note></measure>"
        b"</part></score-partwise>"
    )
    package = parse_musicxml_timeline_package(source)
    metadata = package.documents[0].content.score.metadata
    assert (metadata.work_number, metadata.source) == ("Op. 1", "Source edition")
    assert [(item.text_type, item.value) for item in metadata.rights] == [("music", "Copyright")]
    assert [(item.text_type, item.value) for item in metadata.relations] == [
        ("music", "Related score")
    ]
    assert metadata.encoding is not None
    assert metadata.encoding.dates == ("2026-09-22",)
    assert metadata.encoding.software == ("TeachMeMusic",)
    assert metadata.encoding.supports[0].supported is True
    assert (metadata.miscellaneous[0].name, metadata.miscellaneous[0].value) == (
        "catalogue",
        "TMM-1",
    )
    assert package_from_json(package_to_json(package)) == package


def test_editorial_directive_and_concert_part_state_round_trip() -> None:
    """TEST-MXML-ANNOTATION-082: editorial, directive, and for-part semantics survive."""

    source = _partwise(
        '<measure number="1"><attributes><divisions>2</divisions>'
        '<for-part number="1" id="for-part-1"><part-clef><sign>F</sign><line>4</line>'
        "<clef-octave-change>-1</clef-octave-change></part-clef><part-transpose>"
        "<diatonic>-1</diatonic><chromatic>-2</chromatic><octave-change>-1</octave-change>"
        '</part-transpose></for-part><directive xml:lang="en">Allegro</directive></attributes>'
        '<note id="note-1"><pitch><step>C</step><octave>4</octave></pitch><duration>2</duration>'
        '<footnote xml:lang="en">Editorial note</footnote><level reference="yes" type="single" '
        'parentheses="yes" bracket="no" size="cue">Original source</level>'
        "<type>quarter</type></note><forward><duration>2</duration>"
        '<footnote>Forward note</footnote><level type="single">Edition</level>'
        "<voice>2</voice><staff>1</staff></forward></measure>"
    )
    package = parse_musicxml_timeline_package(source)
    measure = package.documents[0].content.score.parts[0].measures[0]
    attributes = measure.attributes[0]
    assert (attributes.directives[0].value, attributes.directives[0].language) == (
        "Allegro",
        "en",
    )
    for_part = attributes.for_parts[0]
    assert (for_part.staff, for_part.source_id) == ("1", "for-part-1")
    assert for_part.clef is not None and (
        for_part.clef.sign,
        for_part.clef.line,
        for_part.clef.octave_change,
    ) == ("F", 4, -1)
    assert (
        for_part.transposition.diatonic,
        for_part.transposition.chromatic,
        for_part.transposition.octave_change,
    ) == (-1, Fraction(-2), -1)
    event = measure.events[0]
    assert event.source_id == "note-1"
    assert event.editorial is not None and (
        event.editorial.footnote,
        event.editorial.level,
        event.editorial.level_reference,
        event.editorial.level_type,
    ) == ("Editorial note", "Original source", True, "single")
    assert measure.cursor_moves[0].editorial is not None
    assert measure.cursor_moves[0].editorial.footnote == "Forward note"
    assert package_from_json(package_to_json(package)) == package


@pytest.mark.parametrize("version", ("2.0", "3.0", "3.1", "4.0", "4.1-draft"))
def test_analytical_grouping_maps_across_xsd_versions(version: str) -> None:
    """TEST-MXML-ANNOTATION-083: analytical grouping features retain anchors and hierarchy."""

    source_id = None if version in {"2.0", "3.0"} else "group-1"
    id_attribute = "" if source_id is None else f' id="{source_id}"'
    source = _partwise(
        '<measure number="1"><attributes><divisions>1</divisions></attributes>'
        f'<grouping type="single" number="A" member-of="phrase"{id_attribute}>'
        '<feature type="analysis">opening motif</feature></grouping>'
        "<note><rest/><duration>1</duration><type>quarter</type></note></measure>",
        version=version,
    )
    package = parse_musicxml_timeline_package(source)
    grouping = package.documents[0].content.score.parts[0].measures[0].groupings[0]
    assert (
        grouping.grouping_type,
        grouping.number,
        grouping.member_of,
        grouping.source_id,
    ) == ("single", "A", "phrase", source_id)
    assert (grouping.features[0].feature_type, grouping.features[0].value) == (
        "analysis",
        "opening motif",
    )
    assert package_from_json(package_to_json(package)) == package


def test_metadata_editorial_and_grouping_tampering_fails_closed() -> None:
    """TEST-MXML-ANNOTATION-084: new semantic records reject incoherent JSON."""

    source = _partwise(
        '<measure number="1"><attributes><divisions>1</divisions></attributes>'
        '<grouping type="single"><feature>motif</feature></grouping>'
        '<note><rest/><duration>1</duration><level type="single">edition</level>'
        "<type>quarter</type></note></measure>"
    )
    original = package_to_dict(parse_musicxml_timeline_package(source))
    modified = deepcopy(original)
    modified["documents"][0]["content"]["score"]["parts"][0]["measures"][0]["groupings"][0][
        "grouping_type"
    ] = "invalid"
    with pytest.raises(CanonicalSerializationError, match="TEMPORAL_GROUPING"):
        package_from_dict(modified)

    modified = deepcopy(original)
    modified["documents"][0]["content"]["score"]["parts"][0]["measures"][0]["events"][0][
        "editorial"
    ]["level_type"] = "invalid"
    with pytest.raises(CanonicalSerializationError, match="TEMPORAL_EDITORIAL"):
        package_from_dict(modified)


def test_invalid_metadata_fails_closed() -> None:
    """TEST-MXML-ANNOTATION-085: malformed source metadata cannot deserialize."""

    source = _partwise(
        '<measure number="1"><attributes><divisions>1</divisions></attributes>'
        "<note><rest/><duration>1</duration><type>quarter</type></note></measure>"
    )
    modified = package_to_dict(parse_musicxml_timeline_package(source))
    modified["documents"][0]["content"]["score"]["metadata"]["miscellaneous"] = [
        {"name": "", "value": "invalid"}
    ]
    with pytest.raises(CanonicalSerializationError, match="TEMPORAL_METADATA"):
        package_from_dict(modified)


@pytest.mark.parametrize("version", ("1.0", "1.1"))
def test_legacy_dtd_character_entities_normalize_to_unicode(version: str) -> None:
    """TEST-MXML-ANNOTATION-086: declared legacy entities preserve their Unicode meaning."""

    version_attribute = "" if version == "1.0" else f' version="{version}"'
    source = (
        '<?xml version="1.0" encoding="utf-8"?>'
        f'<!DOCTYPE score-partwise PUBLIC "-//Recordare//DTD MusicXML {version} Partwise//EN" '
        '"http://www.musicxml.org/dtds/partwise.dtd">'
        f"<score-partwise{version_attribute}><identification>"
        "<rights>M&Aacute;laga</rights></identification><part-list>"
        '<score-part id="P1"><part-name>Piano</part-name></score-part></part-list>'
        '<part id="P1"><measure number="1"><attributes><divisions>1</divisions></attributes>'
        "<note><rest/><duration>1</duration><type>quarter</type></note></measure>"
        "</part></score-partwise>"
    ).encode()
    package = parse_musicxml_timeline_package(source)
    assert package.documents[0].content.score.metadata.rights[0].value == "MÁlaga"
    assert package_from_json(package_to_json(package)) == package


def test_multiple_note_instruments_remain_ordered() -> None:
    """TEST-MXML-ANNOTATION-087: multi-instrument notes preserve every reference."""

    source = (
        b'<?xml version="1.0" encoding="utf-8"?>'
        b'<!DOCTYPE score-partwise PUBLIC "-//Recordare//DTD MusicXML 4.0 Partwise//EN" '
        b'"http://www.musicxml.org/dtds/partwise.dtd"><score-partwise version="4.0">'
        b'<part-list><score-part id="P1"><part-name>Percussion</part-name>'
        b'<score-instrument id="P1-I1"><instrument-name>Snare</instrument-name>'
        b'</score-instrument><score-instrument id="P1-I2"><instrument-name>Cymbal</instrument-name>'
        b'</score-instrument></score-part></part-list><part id="P1"><measure number="1">'
        b"<attributes><divisions>1</divisions></attributes><note><unpitched>"
        b"<display-step>C</display-step><display-octave>5</display-octave></unpitched>"
        b'<duration>1</duration><instrument id="P1-I1"/><instrument id="P1-I2"/>'
        b"<type>quarter</type></note></measure></part></score-partwise>"
    )
    package = parse_musicxml_timeline_package(source)
    event = package.documents[0].content.score.parts[0].measures[0].events[0]
    assert event.instrument_id == "P1-I1"
    assert event.instrument_ids == ("P1-I1", "P1-I2")
    assert package_from_json(package_to_json(package)) == package


def test_extended_part_and_instrument_metadata_round_trip() -> None:
    """TEST-MXML-ANNOTATION-088: concert, group, and instrument semantics survive."""

    source = (
        b'<?xml version="1.0" encoding="utf-8"?>'
        b'<!DOCTYPE score-partwise PUBLIC "-//Recordare//DTD MusicXML 4.0 Partwise//EN" '
        b'"http://www.musicxml.org/dtds/partwise.dtd"><score-partwise version="4.0">'
        b"<defaults><concert-score/></defaults><part-list>"
        b'<part-group type="start" number="1"><group-name>Winds</group-name>'
        b"<group-time/><footnote>Editorial grouping</footnote>"
        b'<level type="single">source</level></part-group><score-part id="P1">'
        b'<identification><rights type="music">Part rights</rights></identification>'
        b"<part-name>Winds</part-name><group>score</group><group>parts</group>"
        b'<score-instrument id="P1-I1"><instrument-name>Flute</instrument-name>'
        b"<instrument-sound>wind.flutes.flute</instrument-sound><solo/></score-instrument>"
        b'<score-instrument id="P1-I2"><instrument-name>Flutes</instrument-name>'
        b"<instrument-sound>wind.flutes.flute</instrument-sound><ensemble>2</ensemble>"
        b'</score-instrument></score-part><part-group type="stop" number="1"/>'
        b'</part-list><part id="P1"><measure number="1"><attributes><divisions>1</divisions>'
        b"</attributes><note><rest/><duration>1</duration><type>quarter</type></note>"
        b"</measure></part></score-partwise>"
    )
    package = parse_musicxml_timeline_package(source)
    score = package.documents[0].content.score
    assert score.metadata.concert_score is True
    group = score.groups[0]
    assert (group.group_time, group.source_id) == (True, None)
    assert group.editorial is not None and group.editorial.footnote == "Editorial grouping"
    part = score.parts[0]
    assert part.groups == ("score", "parts")
    assert part.metadata.rights[0].value == "Part rights"
    assert (part.instruments[0].sound, part.instruments[0].solo) == (
        "wind.flutes.flute",
        True,
    )
    assert (
        part.instruments[1].ensemble,
        part.instruments[1].ensemble_size,
    ) == (True, 2)
    assert package_from_json(package_to_json(package)) == package
