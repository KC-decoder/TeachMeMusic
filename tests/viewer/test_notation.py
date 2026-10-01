"""DEV-005 Task 5B.1 canonical-to-notation proof."""

from __future__ import annotations

import inspect
from dataclasses import replace
from pathlib import Path

import pytest

from teachmemusic.score import (
    CanonicalMusicPackage,
    CanonicalScoreContent,
    ScoreDocument,
    parse_musicxml_package,
)
from teachmemusic.viewer import (
    NotationProjectionError,
    build_notation_bundle,
    compare_render_equivalence,
    musicxml_renderer,
    notation,
)
from teachmemusic.viewer.musicxml_renderer import render_score_document

_FIXTURE = (
    Path(__file__).parents[1]
    / "fixtures"
    / "scores"
    / "TMM-REF-CANDIDATE-001-Hot-Cross-Buns"
    / "musicxml-17-hot-cross-buns-final-shelbygtdrew.mxl"
)
_HAPPY_BIRTHDAY_FIXTURE = (
    Path(__file__).parents[1]
    / "fixtures"
    / "scores"
    / "TMM-REF-CANDIDATE-002-Happy-Birthday"
    / "happy-birthday-to-you-c-major.mxl"
)


def _package() -> CanonicalMusicPackage:
    return parse_musicxml_package(_FIXTURE.read_bytes(), logical_name=_FIXTURE.name)


def _score_document(package: CanonicalMusicPackage) -> ScoreDocument:
    return next(item for item in package.documents if isinstance(item, ScoreDocument))


def _score(body: str) -> bytes:
    return (
        '<?xml version="1.0" encoding="utf-8"?>'
        '<score-partwise version="4.0"><part-list><score-part id="P1">'
        "<part-name>Piano</part-name></score-part></part-list>"
        f'<part id="P1">{body}</part></score-partwise>'
    ).encode()


def _rhythmic_notation_package() -> CanonicalMusicPackage:
    body = (
        '<measure number="1"><attributes><divisions>6</divisions>'
        "<time><beats>2</beats><beat-type>4</beat-type></time>"
        "<clef><sign>G</sign><line>2</line></clef></attributes>"
        '<sound tempo="60"/><note><pitch><step>C</step><octave>5</octave></pitch>'
        "<duration>2</duration><voice>1</voice><type>eighth</type>"
        "<time-modification><actual-notes>3</actual-notes><normal-notes>2</normal-notes>"
        "<normal-type>eighth</normal-type><normal-dot/></time-modification><staff>1</staff>"
        '<notations><tuplet type="start" number="2" bracket="yes" placement="above" '
        'show-number="both" show-type="actual" line-shape="curved">'
        "<tuplet-actual><tuplet-number>3</tuplet-number><tuplet-type>eighth</tuplet-type>"
        "<tuplet-dot/></tuplet-actual><tuplet-normal><tuplet-number>2</tuplet-number>"
        "<tuplet-type>quarter</tuplet-type></tuplet-normal></tuplet></notations></note>"
        "<note><pitch><step>D</step><octave>5</octave></pitch><duration>2</duration>"
        "<voice>1</voice><type>eighth</type><time-modification>"
        "<actual-notes>3</actual-notes><normal-notes>2</normal-notes>"
        "</time-modification><staff>1</staff></note>"
        "<note><pitch><step>E</step><octave>5</octave></pitch><duration>2</duration>"
        "<voice>1</voice><type>eighth</type><time-modification>"
        "<actual-notes>3</actual-notes><normal-notes>2</normal-notes>"
        '</time-modification><staff>1</staff><notations><tuplet type="stop" number="2"/>'
        "</notations></note><attributes><divisions>12</divisions>"
        "<clef><sign>F</sign><line>4</line></clef></attributes>"
        '<note><grace slash="yes" steal-time-following="25"/>'
        "<pitch><step>F</step><octave>4</octave></pitch><voice>1</voice>"
        "<type>16th</type><staff>1</staff></note><note>"
        "<pitch><step>G</step><octave>3</octave></pitch><duration>12</duration>"
        "<voice>1</voice><type>quarter</type><staff>1</staff></note></measure>"
    )
    return parse_musicxml_package(_score(body), logical_name="rhythmic-notation.musicxml")


def _note_attached_notation_package() -> CanonicalMusicPackage:
    body = (
        '<measure number="1"><attributes><divisions>1</divisions></attributes>'
        "<note><pitch><step>C</step><octave>4</octave></pitch><duration>1</duration>"
        '<tie type="start"/><voice>1</voice><type>quarter</type>'
        '<notehead filled="yes" parentheses="no">diamond</notehead><notations>'
        '<tied type="start" number="1"/><slur type="start" number="2" '
        'placement="above"/><articulations><staccato/><accent/></articulations>'
        '<ornaments><trill-mark/><accidental-mark placement="above">sharp</accidental-mark>'
        '</ornaments><fermata type="upright">normal</fermata>'
        '<arpeggiate number="2" direction="up"/>'
        '<accidental-mark bracket="yes">flat</accidental-mark></notations></note>'
        "<note><pitch><step>C</step><octave>4</octave></pitch><duration>1</duration>"
        '<tie type="stop"/><voice>1</voice><type>quarter</type><notations>'
        '<tied type="stop" number="1"/><slur type="stop" number="2"/>'
        '<ornaments><tremolo type="start">2</tremolo></ornaments>'
        '<slide type="start" number="1" line-type="solid">slide</slide>'
        "</notations></note><note><pitch><step>D</step><octave>4</octave></pitch>"
        "<duration>1</duration><voice>1</voice><type>quarter</type><notations>"
        '<ornaments><tremolo type="stop">2</tremolo>'
        '<wavy-line type="start" number="1"/></ornaments>'
        '<slide type="stop" number="1" line-type="solid">slide</slide>'
        "</notations></note><note><pitch><step>E</step><octave>4</octave></pitch>"
        "<duration>1</duration><voice>1</voice><type>quarter</type><notations>"
        '<ornaments><wavy-line type="stop" number="1"/></ornaments>'
        "</notations></note></measure>"
    )
    return parse_musicxml_package(_score(body), logical_name="note-attached.musicxml")


def _stop_only_wavy_line_package() -> CanonicalMusicPackage:
    source = (
        b'<?xml version="1.0" encoding="utf-8"?><score-partwise version="4.0">'
        b"<identification><encoding><software>MuseScore 2.3.2</software></encoding>"
        b'</identification><part-list><score-part id="P1"><part-name>Piano</part-name>'
        b'</score-part></part-list><part id="P1"><measure number="1"><attributes>'
        b"<divisions>1</divisions></attributes><note><pitch><step>C</step><octave>4</octave>"
        b"</pitch><duration>1</duration><type>quarter</type><notations><ornaments>"
        b'<wavy-line type="stop" number="1"/></ornaments></notations></note>'
        b"</measure></part></score-partwise>"
    )
    return parse_musicxml_package(source, logical_name="stop-only-wavy-line.musicxml")


def _direction_notation_package() -> CanonicalMusicPackage:
    body = (
        '<measure number="1"><attributes><divisions>4</divisions>'
        "<time><beats>4</beats><beat-type>4</beat-type></time></attributes>"
        '<direction placement="above" directive="yes" id="direction-1">'
        '<direction-type id="direction-type-1"><words font-style="italic" '
        'default-y="12">dolce</words></direction-type>'
        '<direction-type><dynamics id="dynamics-1" default-y="-10">'
        "<p/></dynamics></direction-type><offset>2</offset><staff>1</staff></direction>"
        '<direction placement="above"><direction-type><metronome parentheses="yes">'
        "<beat-unit>quarter</beat-unit><per-minute>72</per-minute>"
        "</metronome></direction-type><staff>1</staff></direction>"
        '<direction placement="below"><direction-type>'
        '<wedge type="crescendo" number="1" spread="10"/></direction-type>'
        '<direction-type><dashes type="start" number="1" dash-length="4" '
        'space-length="2"/></direction-type><direction-type><bracket type="start" '
        'number="1" line-type="dashed" line-end="up" end-length="5"/>'
        '</direction-type><direction-type><pedal type="start" number="1" line="yes"/>'
        '</direction-type><direction-type><octave-shift type="down" number="1" '
        'size="8"/></direction-type><offset>4</offset><staff>1</staff></direction>'
        "<note><pitch><step>C</step><octave>4</octave></pitch><duration>16</duration>"
        "<voice>1</voice><type>whole</type><staff>1</staff></note></measure>"
        '<measure number="2"><direction placement="below"><direction-type>'
        '<wedge type="stop" number="1" spread="2"/></direction-type>'
        '<direction-type><dashes type="stop" number="1"/></direction-type>'
        '<direction-type><bracket type="stop" number="1" line-end="down" '
        'end-length="3"/></direction-type><direction-type><pedal type="stop" '
        'number="1" line="yes"/></direction-type><direction-type><octave-shift '
        'type="stop" number="1" size="8"/></direction-type><offset>4</offset>'
        "<staff>1</staff></direction>"
        "<note><pitch><step>D</step><octave>4</octave></pitch><duration>16</duration>"
        "<voice>1</voice><type>whole</type><staff>1</staff></note></measure>"
    )
    return parse_musicxml_package(_score(body), logical_name="directions.musicxml")


def _recovered_wedge_package() -> CanonicalMusicPackage:
    source = (
        b'<?xml version="1.0" encoding="utf-8"?><score-partwise version="3.1">'
        b"<identification><encoding><software>MuseScore 2.3.2</software></encoding>"
        b'</identification><part-list><score-part id="P1"><part-name>Piano</part-name>'
        b'</score-part></part-list><part id="P1"><measure number="1"><attributes>'
        b"<divisions>1</divisions></attributes>"
        b'<direction><direction-type><wedge number="2" type="crescendo"/>'
        b"</direction-type><staff>1</staff></direction>"
        b"<note><rest/><duration>2</duration><type>half</type></note>"
        b'<direction><direction-type><wedge number="3" type="diminuendo"/>'
        b"</direction-type><staff>1</staff></direction>"
        b"<note><rest/><duration>2</duration><type>half</type></note>"
        b"</measure></part></score-partwise>"
    )
    return parse_musicxml_package(source, logical_name="recovered-wedges.musicxml")


def _sound_directive_package() -> CanonicalMusicPackage:
    body = (
        '<measure number="1"><attributes><divisions>1</divisions></attributes>'
        '<sound tempo="60"/><note><pitch><step>C</step><octave>4</octave></pitch>'
        "<duration>2</duration><voice>1</voice><type>half</type></note>"
        '<sound id="sound-change" tempo="120" dynamics="80"/>'
        "<note><pitch><step>D</step><octave>4</octave></pitch><duration>2</duration>"
        '<voice>1</voice><type>half</type></note><sound dacapo="yes" fine="yes"/>'
        "</measure>"
    )
    return parse_musicxml_package(_score(body), logical_name="sounds.musicxml")


def _creator_barline_package() -> CanonicalMusicPackage:
    source = (
        '<?xml version="1.0" encoding="utf-8"?>'
        '<score-partwise version="4.0"><movement-title>Navigation</movement-title>'
        '<identification><creator type="composer">Example Composer</creator>'
        '</identification><part-list><score-part id="P1"><part-name>Piano</part-name>'
        '</score-part></part-list><part id="P1">'
        '<measure number="1"><attributes><divisions>1</divisions></attributes>'
        '<barline location="left" id="left-repeat"><repeat direction="forward"/></barline>'
        "<note><pitch><step>C</step><octave>4</octave></pitch><duration>4</duration>"
        '<voice>1</voice><type>whole</type></note><barline location="right">'
        '<ending number="1" type="start" print-object="yes">first</ending>'
        '<repeat direction="backward" times="2" winged="straight"/></barline></measure>'
        '<measure number="2"><barline location="left"><ending number="1" '
        'type="stop"/></barline><note><pitch><step>D</step><octave>4</octave></pitch>'
        "<duration>4</duration><voice>1</voice><type>whole</type></note></measure>"
        "</part></score-partwise>"
    )
    return parse_musicxml_package(source.encode(), logical_name="creator-barline.musicxml")


def _cross_staff_slur_package() -> CanonicalMusicPackage:
    body = (
        '<measure number="1"><attributes><divisions>1</divisions><staves>2</staves>'
        '<clef number="1"><sign>G</sign><line>2</line></clef>'
        '<clef number="2"><sign>F</sign><line>4</line></clef></attributes>'
        "<note><pitch><step>C</step><octave>3</octave></pitch><duration>1</duration>"
        "<voice>5</voice><type>quarter</type><staff>2</staff><notations>"
        '<slur number="1" type="start"/></notations></note>'
        "<note><pitch><step>D</step><octave>5</octave></pitch><duration>1</duration>"
        "<voice>5</voice><type>quarter</type><staff>1</staff><notations>"
        '<slur number="1" type="stop"/></notations></note>'
        "<note><pitch><step>E</step><octave>3</octave></pitch><duration>1</duration>"
        "<voice>5</voice><type>quarter</type><staff>2</staff><notations>"
        '<slur number="1" type="start"/></notations></note>'
        "<note><pitch><step>F</step><octave>5</octave></pitch><duration>1</duration>"
        "<voice>5</voice><type>quarter</type><staff>1</staff><notations>"
        '<slur number="1" type="stop"/></notations></note></measure>'
    )
    return parse_musicxml_package(_score(body), logical_name="cross-staff-slurs.musicxml")


def _replace_first_event(
    package: CanonicalMusicPackage, **changes: object
) -> CanonicalMusicPackage:
    document = _score_document(package)
    assert isinstance(document.content, CanonicalScoreContent)
    score = document.content.score
    part = score.parts[0]
    measure = part.measures[0]
    event = replace(measure.events[0], **changes)
    changed_measure = replace(measure, events=(event, *measure.events[1:]))
    changed_part = replace(part, measures=(changed_measure, *part.measures[1:]))
    changed_score = replace(score, parts=(changed_part, *score.parts[1:]))
    changed_document = replace(document, content=replace(document.content, score=changed_score))
    return replace(
        package,
        documents=tuple(
            changed_document if item is document else item for item in package.documents
        ),
    )


def test_hot_cross_buns_projection_validates_reparses_and_compares_equal() -> None:
    """TEST-VIEWER-NOTATION-001: the governed simple score proves the full bridge."""

    package = _package()
    source_document = _score_document(package)
    bundle = build_notation_bundle(package)
    reparsed = parse_musicxml_package(
        bundle.renderer.content.encode("utf-8"),
        logical_name="generated.musicxml",
    )

    assert compare_render_equivalence(source_document, reparsed) == ()
    assert "<work-title>Hot Cross Buns</work-title>" in bundle.renderer.content
    assert bundle.renderer.content.count("<measure number=") == 8
    assert bundle.renderer.content.count("<note>") == 20
    assert '<print new-system="yes"' in bundle.renderer.content
    assert "<bar-style>light-heavy</bar-style>" in bundle.renderer.content
    assert [item.code for item in bundle.diagnostics] == [
        "VIEWER_NOTATION_LAYOUT_NORMALIZED",
        "VIEWER_NOTATION_EXPORT_METADATA_EXCLUDED",
        "VIEWER_NOTATION_REPARSE_VERIFIED",
    ]


def test_notation_projection_has_no_private_xml_or_source_byte_fallback() -> None:
    """TEST-VIEWER-NOTATION-002: viewer code can consume only public canonical data."""

    sources = inspect.getsource(notation) + inspect.getsource(musicxml_renderer)

    assert "teachmemusic.score.musicxml" not in sources
    assert "lxml" not in sources
    assert "source: bytes" not in sources
    assert "original_musicxml" not in sources


def test_canonical_mutation_controls_generated_notation() -> None:
    """TEST-VIEWER-NOTATION-003: output follows canonical state, not the upload."""

    package = _package()
    changed = _replace_first_event(package, stem="up")

    original_bundle = build_notation_bundle(package)
    changed_bundle = build_notation_bundle(changed)

    assert original_bundle.renderer.sha256 != changed_bundle.renderer.sha256
    assert original_bundle.renderer.content.count("<stem>down</stem>") == 3
    assert changed_bundle.renderer.content.count("<stem>down</stem>") == 2


def test_independent_equivalence_detects_changed_generated_pitch() -> None:
    """TEST-VIEWER-NOTATION-004: a valid but changed renderer payload is rejected."""

    package = _package()
    document = _score_document(package)
    bundle = build_notation_bundle(package)
    changed_xml = bundle.renderer.content.replace(
        "<step>B</step>",
        "<step>C</step>",
        1,
    )
    changed_package = parse_musicxml_package(
        changed_xml.encode("utf-8"),
        logical_name="changed.musicxml",
    )

    issues = compare_render_equivalence(document, changed_package)

    assert issues
    assert any(issue.path.endswith("pitch[0]") for issue in issues)


def test_unsupported_semantics_fail_instead_of_disappearing() -> None:
    """TEST-VIEWER-NOTATION-005: the bounded projection never silently drops a chord."""

    package = _package()
    changed = _replace_first_event(package, chord_id="canonical-chord")
    document = _score_document(changed)

    with pytest.raises(NotationProjectionError) as captured:
        render_score_document(document)

    assert captured.value.code == "VIEWER_NOTATION_UNSUPPORTED_FACT"
    assert captured.value.canonical_id is not None


def test_happy_birthday_polyphonic_piano_projection_is_equivalent() -> None:
    """TEST-VIEWER-NOTATION-006: the second beginner fixture crosses the bridge."""

    package = parse_musicxml_package(
        _HAPPY_BIRTHDAY_FIXTURE.read_bytes(),
        logical_name=_HAPPY_BIRTHDAY_FIXTURE.name,
    )
    source_document = _score_document(package)

    bundle = build_notation_bundle(package)
    reparsed = parse_musicxml_package(
        bundle.renderer.content.encode("utf-8"),
        logical_name="happy-birthday-generated.musicxml",
    )

    assert compare_render_equivalence(source_document, reparsed) == ()
    assert bundle.title == "Happy Birthday to You"
    assert len(bundle.renderer.anchors) == 69
    assert bundle.renderer.content.count("<note>") == 59
    assert bundle.renderer.content.count("<chord") == 18
    assert bundle.renderer.content.count("<harmony") == 3
    assert bundle.renderer.content.count("<backup>") == 8
    assert bundle.renderer.content.count("<beam") == 8
    assert bundle.renderer.content.count("<accidental") == 1
    assert "<staves>2</staves>" in bundle.renderer.content
    assert '<clef number="1">' in bundle.renderer.content
    assert ">Happy Birthday to You</credit-words>" in bundle.renderer.content
    assert ">Patty Hill  Mildred J. Hill</credit-words>" in bundle.renderer.content
    assert [item.code for item in bundle.diagnostics] == [
        "VIEWER_NOTATION_LAYOUT_NORMALIZED",
        "VIEWER_NOTATION_EXPORT_METADATA_EXCLUDED",
        "VIEWER_NOTATION_CURSOR_RECONSTRUCTED",
        "VIEWER_NOTATION_REPARSE_VERIFIED",
    ]


def test_happy_birthday_harmony_mutation_is_detected() -> None:
    """TEST-VIEWER-NOTATION-007: expanded equivalence covers chord symbols."""

    package = parse_musicxml_package(
        _HAPPY_BIRTHDAY_FIXTURE.read_bytes(),
        logical_name=_HAPPY_BIRTHDAY_FIXTURE.name,
    )
    source_document = _score_document(package)
    bundle = build_notation_bundle(package)
    changed_xml = bundle.renderer.content.replace(
        "<root-step>C</root-step>",
        "<root-step>D</root-step>",
        1,
    )
    changed_package = parse_musicxml_package(
        changed_xml.encode("utf-8"),
        logical_name="changed-harmony.musicxml",
    )

    issues = compare_render_equivalence(source_document, changed_package)

    assert any("harmonies" in issue.path for issue in issues)


def test_rhythm_grace_and_midmeasure_attributes_cross_the_bridge() -> None:
    """TEST-VIEWER-NOTATION-008: rhythmic notation survives verified projection."""

    package = _rhythmic_notation_package()
    source_document = _score_document(package)

    bundle = build_notation_bundle(package)
    reparsed = parse_musicxml_package(
        bundle.renderer.content.encode("utf-8"),
        logical_name="rhythmic-notation-generated.musicxml",
    )

    assert compare_render_equivalence(source_document, reparsed) == ()
    assert bundle.renderer.content.count("<attributes>") == 2
    assert bundle.renderer.content.count("<time-modification>") == 3
    assert bundle.renderer.content.count("<tuplet ") == 2
    assert bundle.renderer.content.count("<grace ") == 1
    assert '<grace slash="yes" steal-time-following="25"' in bundle.renderer.content
    assert [item.code for item in bundle.diagnostics] == [
        "VIEWER_NOTATION_DIVISIONS_NORMALIZED",
        "VIEWER_NOTATION_ATTRIBUTE_CURSOR_RECONSTRUCTED",
        "VIEWER_NOTATION_REPARSE_VERIFIED",
    ]


def test_expanded_rhythm_equivalence_detects_semantic_mutations() -> None:
    """TEST-VIEWER-NOTATION-009: rhythm, grace, and attribute checks are sensitive."""

    package = _rhythmic_notation_package()
    source_document = _score_document(package)
    generated = build_notation_bundle(package).renderer.content
    mutations = (
        (
            "<actual-notes>3</actual-notes>",
            "<actual-notes>5</actual-notes>",
            "time_modification",
        ),
        ("<sign>F</sign>", "<sign>C</sign>", "attributes"),
        ('slash="yes"', 'slash="no"', "grace"),
    )

    for old, new, expected_path in mutations:
        changed = parse_musicxml_package(
            generated.replace(old, new, 1).encode("utf-8"),
            logical_name=f"changed-{expected_path}.musicxml",
        )
        issues = compare_render_equivalence(source_document, changed)
        assert any(expected_path in issue.path for issue in issues)


def test_midmeasure_attribute_can_cross_a_sustained_voice_event() -> None:
    """TEST-VIEWER-NOTATION-010: attribute timing is independent of voice gaps."""

    package = parse_musicxml_package(
        _score(
            '<measure number="1"><attributes><divisions>1</divisions>'
            "<time><beats>4</beats><beat-type>4</beat-type></time>"
            "<clef><sign>G</sign><line>2</line></clef></attributes>"
            "<note><pitch><step>C</step><octave>4</octave></pitch>"
            "<duration>4</duration><voice>1</voice><type>whole</type></note>"
            "<backup><duration>3</duration></backup><attributes>"
            "<clef><sign>F</sign><line>4</line></clef></attributes>"
            "<forward><duration>3</duration></forward></measure>"
        ),
        logical_name="sustained-clef-change.musicxml",
    )
    source_document = _score_document(package)

    bundle = build_notation_bundle(package)
    reparsed = parse_musicxml_package(
        bundle.renderer.content.encode("utf-8"),
        logical_name="sustained-clef-change-generated.musicxml",
    )

    assert compare_render_equivalence(source_document, reparsed) == ()
    assert bundle.renderer.content.index("<sign>F</sign>") < bundle.renderer.content.index(
        "<step>C</step>"
    )
    assert "<backup>" in bundle.renderer.content


def test_note_attached_marks_and_resolved_spans_cross_the_bridge() -> None:
    """TEST-VIEWER-NOTATION-011: attached marks retain endpoint topology."""

    package = _note_attached_notation_package()
    source_document = _score_document(package)

    bundle = build_notation_bundle(package)
    reparsed = parse_musicxml_package(
        bundle.renderer.content.encode("utf-8"),
        logical_name="note-attached-generated.musicxml",
    )

    assert compare_render_equivalence(source_document, reparsed) == ()
    assert bundle.renderer.content.count("<tie ") == 2
    assert bundle.renderer.content.count("<tied ") == 2
    assert bundle.renderer.content.count("<slur ") == 2
    assert bundle.renderer.content.count("<tremolo ") == 2
    assert bundle.renderer.content.count("<wavy-line ") == 2
    assert bundle.renderer.content.count("<slide ") == 2
    assert '<notehead filled="yes" parentheses="no">diamond</notehead>' in (bundle.renderer.content)
    assert [
        (span.kind, len(span.endpoints)) for span in source_document.content.score.annotations.spans
    ] == [
        ("sounding-tie", 2),
        ("notated-tie", 2),
        ("slur", 2),
        ("tremolo", 2),
        ("slide", 2),
        ("wavy-line", 2),
    ]


def test_note_attachment_equivalence_detects_semantic_mutations() -> None:
    """TEST-VIEWER-NOTATION-012: marks, noteheads, and endpoints are compared."""

    package = _note_attached_notation_package()
    source_document = _score_document(package)
    generated = build_notation_bundle(package).renderer.content
    mutations = (
        ("<staccato", "<tenuto", "event_markers"),
        ('placement="above"', 'placement="below"', "span_markers"),
        (">diamond</notehead>", ">triangle</notehead>", "notehead"),
    )

    for old, new, expected_path in mutations:
        changed = parse_musicxml_package(
            generated.replace(old, new, 1).encode("utf-8"),
            logical_name=f"changed-{expected_path}.musicxml",
        )
        issues = compare_render_equivalence(source_document, changed)
        assert any(expected_path in issue.path for issue in issues)


def test_stop_only_wavy_line_recovery_provenance_crosses_the_bridge() -> None:
    """TEST-VIEWER-NOTATION-013: bounded exporter recovery is not erased."""

    package = _stop_only_wavy_line_package()
    source_document = _score_document(package)

    bundle = build_notation_bundle(package)
    reparsed = parse_musicxml_package(
        bundle.renderer.content.encode("utf-8"),
        logical_name="stop-only-wavy-line-generated.musicxml",
    )

    assert compare_render_equivalence(source_document, reparsed) == ()
    assert "<software>MuseScore 2.3.2</software>" in bundle.renderer.content
    assert [item.code for item in bundle.diagnostics] == [
        "VIEWER_NOTATION_EXPORT_METADATA_EXCLUDED",
        "VIEWER_NOTATION_RECOVERY_PROVENANCE_RETAINED",
        "VIEWER_NOTATION_REPARSE_VERIFIED",
    ]
    spans = source_document.content.score.annotations.spans
    assert len(spans) == 1
    assert [
        (item.kind, tuple(endpoint.action for endpoint in item.endpoints)) for item in spans
    ] == [("wavy-line", ("stop",))]


def test_structured_technical_mark_remains_an_explicit_boundary() -> None:
    """TEST-VIEWER-NOTATION-014: an unimplemented rich mark is never dropped."""

    package = parse_musicxml_package(
        _score(
            '<measure number="1"><attributes><divisions>1</divisions></attributes>'
            "<note><pitch><step>C</step><octave>4</octave></pitch><duration>1</duration>"
            "<type>quarter</type><notations><technical><harmonic><natural/>"
            "<base-pitch/></harmonic></technical></notations></note></measure>"
        ),
        logical_name="structured-technical.musicxml",
    )

    with pytest.raises(NotationProjectionError) as captured:
        build_notation_bundle(package)

    assert captured.value.code == "VIEWER_NOTATION_UNSUPPORTED_FACT"
    assert captured.value.canonical_id is not None


def test_point_directions_and_direction_spans_cross_the_bridge() -> None:
    """TEST-VIEWER-NOTATION-015: directions retain content, timing, and topology."""

    package = _direction_notation_package()
    source_document = _score_document(package)

    bundle = build_notation_bundle(package)
    reparsed = parse_musicxml_package(
        bundle.renderer.content.encode("utf-8"),
        logical_name="directions-generated.musicxml",
    )

    assert compare_render_equivalence(source_document, reparsed) == ()
    assert (
        bundle.renderer.content.count("<direction>") + bundle.renderer.content.count("<direction ")
        == 4
    )
    assert "<words" in bundle.renderer.content
    assert "<dynamics" in bundle.renderer.content
    assert "<metronome" in bundle.renderer.content
    assert bundle.renderer.content.count("<wedge ") == 2
    assert bundle.renderer.content.count("<dashes ") == 2
    assert bundle.renderer.content.count("<bracket ") == 2
    assert bundle.renderer.content.count("<pedal ") == 2
    assert bundle.renderer.content.count("<octave-shift ") == 2
    assert len(source_document.content.score.annotations.time_spans) == 5


def test_direction_equivalence_detects_point_and_span_mutations() -> None:
    """TEST-VIEWER-NOTATION-016: direction comparison rejects semantic changes."""

    package = _direction_notation_package()
    source_document = _score_document(package)
    generated = build_notation_bundle(package).renderer.content
    mutations = (
        (">dolce</words>", ">cantabile</words>", "directions"),
        ("<p />", "<f />", "directions"),
        ('type="crescendo"', 'type="diminuendo"', "time_span_markers"),
    )

    for old, new, expected_path in mutations:
        changed = parse_musicxml_package(
            generated.replace(old, new, 1).encode("utf-8"),
            logical_name=f"changed-{expected_path}.musicxml",
        )
        issues = compare_render_equivalence(source_document, changed)
        assert any(expected_path in issue.path for issue in issues)


def test_musescore_wedge_recovery_provenance_crosses_the_bridge() -> None:
    """TEST-VIEWER-NOTATION-017: inferred direction endpoints remain reproducible."""

    package = _recovered_wedge_package()
    source_document = _score_document(package)

    bundle = build_notation_bundle(package)
    reparsed = parse_musicxml_package(
        bundle.renderer.content.encode("utf-8"),
        logical_name="recovered-wedges-generated.musicxml",
    )

    assert compare_render_equivalence(source_document, reparsed) == ()
    assert bundle.renderer.content.count("<wedge ") == 2
    assert "<software>MuseScore 2.3.2</software>" in bundle.renderer.content
    inferred = tuple(
        endpoint
        for span in source_document.content.score.annotations.time_spans
        for endpoint in span.endpoints
        if endpoint.inferred
    )
    assert len(inferred) == 2
    assert {item.inference_reason for item in inferred} == {"musescore-2-adjacent-wedge-recovery"}
    assert "VIEWER_NOTATION_RECOVERY_PROVENANCE_RETAINED" in {
        item.code for item in bundle.diagnostics
    }


def test_sound_directives_cross_the_notation_bridge() -> None:
    """TEST-VIEWER-NOTATION-018: supported sound controls retain onset and meaning."""

    package = _sound_directive_package()
    source_document = _score_document(package)

    bundle = build_notation_bundle(package)
    reparsed = parse_musicxml_package(
        bundle.renderer.content.encode("utf-8"),
        logical_name="sounds-generated.musicxml",
    )

    assert compare_render_equivalence(source_document, reparsed) == ()
    assert '<sound tempo="60"' in bundle.renderer.content
    assert '<sound tempo="120" dynamics="80" id="sound-change"' in bundle.renderer.content
    assert '<sound dacapo="yes" fine="yes"' in bundle.renderer.content
    assert "<offset>2</offset>" in bundle.renderer.content
    assert "<offset>4</offset>" in bundle.renderer.content


def test_sound_equivalence_detects_a_semantic_mutation() -> None:
    """TEST-VIEWER-NOTATION-019: sound comparison rejects a dynamics change."""

    package = _sound_directive_package()
    source_document = _score_document(package)
    generated = build_notation_bundle(package).renderer.content
    changed = parse_musicxml_package(
        generated.replace('dynamics="80"', 'dynamics="81"', 1).encode("utf-8"),
        logical_name="changed-sounds.musicxml",
    )

    issues = compare_render_equivalence(source_document, changed)

    assert any("sounds" in issue.path for issue in issues)


def test_creator_and_complete_barline_facts_cross_the_bridge() -> None:
    """TEST-VIEWER-NOTATION-020: identity and navigation barlines round-trip."""

    package = _creator_barline_package()
    source_document = _score_document(package)

    bundle = build_notation_bundle(package)
    reparsed = parse_musicxml_package(
        bundle.renderer.content.encode("utf-8"),
        logical_name="creator-barline-generated.musicxml",
    )

    assert compare_render_equivalence(source_document, reparsed) == ()
    assert '<creator type="composer">Example Composer</creator>' in bundle.renderer.content
    assert '<barline location="left" id="left-repeat">' in bundle.renderer.content
    assert '<ending type="start" number="1" print-object="yes">first</ending>' in (
        bundle.renderer.content
    )
    assert '<repeat direction="backward" times="2" winged="straight"' in (bundle.renderer.content)


def test_creator_and_barline_mutations_are_observable() -> None:
    """TEST-VIEWER-NOTATION-021: identity and ending mutations fail equivalence."""

    package = _creator_barline_package()
    source_document = _score_document(package)
    generated = build_notation_bundle(package).renderer.content
    mutations = (
        ("Example Composer", "Changed Composer", "creators"),
        ('type="start" number="1"', 'type="start" number="2"', "barlines"),
    )

    for old, new, expected_path in mutations:
        changed = parse_musicxml_package(
            generated.replace(old, new, 1).encode("utf-8"),
            logical_name=f"changed-{expected_path}.musicxml",
        )
        issues = compare_render_equivalence(source_document, changed)
        assert any(expected_path in issue.path for issue in issues)


def test_cross_staff_voice_order_preserves_reused_slur_topology() -> None:
    """TEST-VIEWER-NOTATION-022: cursor reconstruction keeps canonical source order."""

    package = _cross_staff_slur_package()
    source_document = _score_document(package)

    bundle = build_notation_bundle(package)
    reparsed = parse_musicxml_package(
        bundle.renderer.content.encode("utf-8"),
        logical_name="cross-staff-slurs-generated.musicxml",
    )

    assert compare_render_equivalence(source_document, reparsed) == ()
    actions = [
        fragment.split('type="', 1)[1].split('"', 1)[0]
        for fragment in bundle.renderer.content.split("<slur ")[1:]
    ]
    assert actions == ["start", "stop", "start", "stop"]
