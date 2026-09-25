"""Deterministic standards-derived MusicXML witness generation."""

from __future__ import annotations

import hashlib
import io
import zipfile
from dataclasses import dataclass

MXL_WITNESS_GENERATOR_ID = "teachmemusic.musicxml.witness.mxl-packaging/1"
MXL_PACKAGING_VERSIONS = ("2.0", "3.0", "3.1", "4.0", "4.1-draft")
INSTRUMENT_WITNESS_GENERATOR_ID = "teachmemusic.musicxml.witness.instruments-and-performers/1"
INSTRUMENT_VERSIONS = ("1.0", "1.1", *MXL_PACKAGING_VERSIONS)
PITCH_WITNESS_GENERATOR_ID = "teachmemusic.musicxml.witness.written-pitch/1"
FIGURED_BASS_WITNESS_GENERATOR_ID = "teachmemusic.musicxml.witness.figured-bass/1"
CREDITS_WITNESS_GENERATOR_ID = "teachmemusic.musicxml.witness.credits-defaults/1"
DOCUMENT_IDENTITY_WITNESS_GENERATOR_ID = (
    "teachmemusic.musicxml.witness.document-identity-versions/1"
)
HEADER_WITNESS_GENERATOR_ID = "teachmemusic.musicxml.witness.header-identification/1"
PARTS_WITNESS_GENERATOR_ID = "teachmemusic.musicxml.witness.parts-groups/1"
MEASURES_WITNESS_GENERATOR_ID = "teachmemusic.musicxml.witness.measures-cursor/1"
ATTRIBUTES_WITNESS_GENERATOR_ID = "teachmemusic.musicxml.witness.attributes-staff-state/1"
NOTES_WITNESS_GENERATOR_ID = "teachmemusic.musicxml.witness.notes-rests/1"
RHYTHM_WITNESS_GENERATOR_ID = "teachmemusic.musicxml.witness.rhythm-beams-tuplets/1"
TIES_WITNESS_GENERATOR_ID = "teachmemusic.musicxml.witness.ties-spanners/1"
NOTEHEADS_WITNESS_GENERATOR_ID = "teachmemusic.musicxml.witness.noteheads-notations/1"
ARTICULATIONS_WITNESS_GENERATOR_ID = "teachmemusic.musicxml.witness.articulations-ornaments/1"
TECHNICAL_WITNESS_GENERATOR_ID = "teachmemusic.musicxml.witness.technical-notation/1"
BARLINES_WITNESS_GENERATOR_ID = "teachmemusic.musicxml.witness.barlines-navigation/1"
DIRECTIONS_WITNESS_GENERATOR_ID = "teachmemusic.musicxml.witness.directions-text-tempo/1"
DYNAMICS_WITNESS_GENERATOR_ID = "teachmemusic.musicxml.witness.dynamics/1"
LYRICS_WITNESS_GENERATOR_ID = "teachmemusic.musicxml.witness.lyrics/1"
HARMONY_WITNESS_GENERATOR_ID = "teachmemusic.musicxml.witness.harmony-fret-diagrams/1"
LINKS_WITNESS_GENERATOR_ID = "teachmemusic.musicxml.witness.links-bookmarks-grouping/1"
AUXILIARY_WITNESS_GENERATOR_ID = "teachmemusic.musicxml.witness.opus-sounds-documents/1"
PLAYBACK_WITNESS_GENERATOR_ID = "teachmemusic.musicxml.witness.playback-midi/1"
LAYOUT_WITNESS_GENERATOR_ID = "teachmemusic.musicxml.witness.layout-appearance/1"
PRESENTATION_WITNESS_GENERATOR_ID = "teachmemusic.musicxml.witness.presentation-formatting/1"
SCORE_VERSIONS = INSTRUMENT_VERSIONS
CREDITS_VERSIONS = SCORE_VERSIONS[1:]
DOCUMENT_IDENTITY_VERSIONS = SCORE_VERSIONS[2:]
SOUNDS_VERSIONS = ("3.0", "3.1", "4.0", "4.1-draft")


@dataclass(frozen=True, slots=True)
class GeneratedWitness:
    """One deterministic generated source and its stable identity."""

    witness_id: str
    family: str
    standard_version: str
    source_format: str
    data: bytes

    @property
    def sha256(self) -> str:
        return hashlib.sha256(self.data).hexdigest()


def generate_mxl_packaging_witnesses() -> tuple[GeneratedWitness, ...]:
    """Generate one complete container witness for each applicable version."""

    return tuple(_mxl_witness(version) for version in MXL_PACKAGING_VERSIONS)


def generate_instrument_witnesses() -> tuple[GeneratedWitness, ...]:
    """Generate one score witness for every supported MusicXML version."""

    return tuple(_instrument_witness(version) for version in INSTRUMENT_VERSIONS)


def generate_pitch_witnesses() -> tuple[GeneratedWitness, ...]:
    """Generate exact written-pitch and accidental witnesses."""

    return tuple(_pitch_witness(version) for version in SCORE_VERSIONS)


def generate_figured_bass_witnesses() -> tuple[GeneratedWitness, ...]:
    """Generate exact figured-bass witnesses for every supported version."""

    return tuple(_figured_bass_witness(version) for version in SCORE_VERSIONS)


def generate_credits_witnesses() -> tuple[GeneratedWitness, ...]:
    """Generate defaults and credit witnesses for every applicable version."""

    return tuple(_credits_witness(version) for version in CREDITS_VERSIONS)


def generate_document_identity_witnesses() -> tuple[GeneratedWitness, ...]:
    """Generate one timewise boundary-identity witness per XSD version."""

    return tuple(_document_identity_witness(version) for version in DOCUMENT_IDENTITY_VERSIONS)


def generate_header_witnesses() -> tuple[GeneratedWitness, ...]:
    """Generate rich score-header witnesses for every supported version."""

    return tuple(_header_witness(version) for version in SCORE_VERSIONS)


def generate_parts_witnesses() -> tuple[GeneratedWitness, ...]:
    """Generate partwise and timewise score-structure witnesses."""

    return tuple(
        _parts_witness(version, form)
        for version in SCORE_VERSIONS
        for form in ("partwise", "timewise")
    )


def generate_measures_witnesses() -> tuple[GeneratedWitness, ...]:
    """Generate partwise and timewise temporal-core witnesses."""

    return tuple(
        _temporal_core_witness(version, form, "measures, voices, and time cursor", "MEASURES")
        for version in SCORE_VERSIONS
        for form in ("partwise", "timewise")
    )


def generate_attributes_witnesses() -> tuple[GeneratedWitness, ...]:
    """Generate versioned attribute and staff-state witnesses."""

    return tuple(
        _temporal_core_witness(version, "partwise", "attributes and staff state", "ATTRIBUTES")
        for version in SCORE_VERSIONS
    )


def generate_notes_witnesses() -> tuple[GeneratedWitness, ...]:
    """Generate versioned note and rest witnesses."""

    return tuple(
        _temporal_core_witness(version, "partwise", "notes and rests", "NOTES")
        for version in SCORE_VERSIONS
    )


def generate_rhythm_witnesses() -> tuple[GeneratedWitness, ...]:
    """Generate versioned rhythm, beam, and tuplet witnesses."""

    return tuple(
        _temporal_core_witness(version, "partwise", "rhythm, beams, and tuplets", "RHYTHM")
        for version in SCORE_VERSIONS
    )


def generate_ties_witnesses() -> tuple[GeneratedWitness, ...]:
    """Generate versioned note- and time-span topology witnesses."""

    return tuple(_ties_witness(version) for version in SCORE_VERSIONS)


def generate_noteheads_witnesses() -> tuple[GeneratedWitness, ...]:
    """Generate versioned notehead and general-notation witnesses."""

    return tuple(_noteheads_witness(version) for version in SCORE_VERSIONS)


def generate_articulations_witnesses() -> tuple[GeneratedWitness, ...]:
    """Generate versioned articulation and ornament witnesses."""

    return tuple(_articulations_witness(version) for version in SCORE_VERSIONS)


def generate_technical_witnesses() -> tuple[GeneratedWitness, ...]:
    """Generate versioned instrument-specific technical witnesses."""

    return tuple(_technical_witness(version) for version in SCORE_VERSIONS)


def generate_barlines_witnesses() -> tuple[GeneratedWitness, ...]:
    """Generate versioned barline and navigation witnesses."""

    return tuple(_barlines_witness(version) for version in SCORE_VERSIONS)


def generate_directions_witnesses() -> tuple[GeneratedWitness, ...]:
    """Generate versioned ordered text and tempo direction witnesses."""

    return tuple(_directions_witness(version) for version in SCORE_VERSIONS)


def generate_dynamics_witnesses() -> tuple[GeneratedWitness, ...]:
    """Generate versioned direction- and note-attached dynamic witnesses."""

    return tuple(_dynamics_witness(version) for version in SCORE_VERSIONS)


def generate_lyrics_witnesses() -> tuple[GeneratedWitness, ...]:
    """Generate versioned ordered lyric-content witnesses."""

    return tuple(_lyrics_witness(version) for version in SCORE_VERSIONS)


def generate_harmony_witnesses() -> tuple[GeneratedWitness, ...]:
    """Generate versioned harmony and fret-diagram witnesses."""

    return tuple(_harmony_witness(version) for version in SCORE_VERSIONS)


def generate_links_witnesses() -> tuple[GeneratedWitness, ...]:
    """Generate versioned score link, bookmark, and grouping witnesses."""

    return tuple(_links_witness(version) for version in SCORE_VERSIONS)


def generate_auxiliary_witnesses() -> tuple[GeneratedWitness, ...]:
    """Generate every applicable native opus and sound-catalog witness."""

    return (
        tuple(_opus_witness(version) for version in SCORE_VERSIONS)
        + tuple(_work_opus_witness(version) for version in SCORE_VERSIONS)
        + tuple(_sounds_witness(version) for version in SOUNDS_VERSIONS)
    )


def generate_playback_witnesses() -> tuple[GeneratedWitness, ...]:
    """Generate versioned score playback and MIDI witnesses."""

    return tuple(_playback_witness(version) for version in SCORE_VERSIONS)


def generate_layout_witnesses() -> tuple[GeneratedWitness, ...]:
    """Generate versioned page, system, staff, and measure-layout witnesses."""

    return tuple(_layout_witness(version) for version in SCORE_VERSIONS)


def generate_presentation_witnesses() -> tuple[GeneratedWitness, ...]:
    """Generate versioned shared text-presentation witnesses."""

    return tuple(_presentation_witness(version) for version in SCORE_VERSIONS)


def _mxl_witness(version: str) -> GeneratedWitness:
    declared_version = "4.1" if version == "4.1-draft" else version
    score = (
        f'<score-partwise version="{declared_version}">'
        '<part-list><score-part id="P1"><part-name>Evidence</part-name>'
        '</score-part></part-list><part id="P1"><measure number="1"/></part>'
        "</score-partwise>"
    ).encode()
    container = (
        b"<container><rootfiles>"
        b'<rootfile full-path="score.musicxml" '
        b'media-type="application/vnd.recordare.musicxml+xml"/>'
        b'<rootfile full-path="preview.pdf" media-type="application/pdf"/>'
        b"</rootfiles></container>"
    )
    entries = (
        ("mimetype", b"application/vnd.recordare.musicxml", zipfile.ZIP_STORED),
        ("META-INF/container.xml", container, zipfile.ZIP_DEFLATED),
        ("score.musicxml", score, zipfile.ZIP_DEFLATED),
        ("preview.pdf", b"%PDF-losslessness-pilot", zipfile.ZIP_DEFLATED),
    )
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w") as archive:
        for name, data, compression in entries:
            info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = compression
            info.external_attr = 0o100644 << 16
            archive.writestr(info, data)
    return GeneratedWitness(
        witness_id=f"WITNESS-MXML-MXL-{version}",
        family="mxl packaging",
        standard_version=version,
        source_format="mxl",
        data=stream.getvalue(),
    )


def _instrument_witness(version: str) -> GeneratedWitness:
    declared_version = "4.1" if version == "4.1-draft" else version
    version_attribute = "" if version == "1.0" else f' version="{declared_version}"'
    namespace = (
        ' xmlns:xlink="http://www.w3.org/1999/xlink"' if version in {"4.0", "4.1-draft"} else ""
    )
    part_link = (
        '<part-link xlink:href="parts/P1.musicxml">'
        '<instrument-link id="P1-I1"/><instrument-link id="P1-I2"/>'
        "</part-link>"
        if version in {"4.0", "4.1-draft"}
        else ""
    )
    if version in {"1.0", "1.1"}:
        first_detail = second_detail = ""
    elif version == "2.0":
        first_detail = "<solo/>"
        second_detail = "<ensemble>3</ensemble>"
    else:
        first_detail = (
            "<instrument-sound>keyboard.piano.grand</instrument-sound><solo/>"
            "<virtual-instrument><virtual-library>Evidence Library</virtual-library>"
            "<virtual-name>Evidence Piano</virtual-name></virtual-instrument>"
        )
        second_detail = (
            "<instrument-sound>strings.violin</instrument-sound><ensemble>3</ensemble>"
            "<virtual-instrument><virtual-library>Evidence Library</virtual-library>"
            "<virtual-name>Evidence Strings</virtual-name></virtual-instrument>"
        )
    score = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        f'<!DOCTYPE score-partwise PUBLIC "-//Recordare//DTD MusicXML {declared_version} '
        'Partwise//EN" "http://www.musicxml.org/dtds/partwise.dtd">'
        f"<score-partwise{namespace}{version_attribute}><part-list>"
        f'<score-part id="P1">{part_link}<part-name>Evidence Ensemble</part-name>'
        '<score-instrument id="P1-I1"><instrument-name>Evidence Piano</instrument-name>'
        f"<instrument-abbreviation>Pno.</instrument-abbreviation>{first_detail}"
        "</score-instrument>"
        '<score-instrument id="P1-I2"><instrument-name>Evidence Violin</instrument-name>'
        f"<instrument-abbreviation>Vln.</instrument-abbreviation>{second_detail}"
        "</score-instrument></score-part></part-list>"
        '<part id="P1"><measure number="1"/></part></score-partwise>'
    ).encode()
    return GeneratedWitness(
        witness_id=f"WITNESS-MXML-INSTRUMENTS-{version}",
        family="instruments and performers",
        standard_version=version,
        source_format="musicxml",
        data=score,
    )


def _score_document(version: str, *, header: str = "", measure: str = "") -> bytes:
    declared_version = "4.1" if version == "4.1-draft" else version
    version_attribute = "" if version == "1.0" else f' version="{declared_version}"'
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        f'<!DOCTYPE score-partwise PUBLIC "-//Recordare//DTD MusicXML {declared_version} '
        'Partwise//EN" "http://www.musicxml.org/dtds/partwise.dtd">'
        f"<score-partwise{version_attribute}>{header}<part-list>"
        '<score-part id="P1"><part-name>Evidence</part-name></score-part>'
        '</part-list><part id="P1"><measure number="1">'
        f"{measure}</measure></part></score-partwise>"
    ).encode()


def _score_bytes(
    version: str,
    *,
    form: str,
    header: str,
    part_list: str,
    bodies: str,
) -> bytes:
    declared_version = "4.1" if version == "4.1-draft" else version
    title_form = "Partwise" if form == "partwise" else "Timewise"
    root = f"score-{form}"
    version_attribute = "" if version == "1.0" else f' version="{declared_version}"'
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        f'<!DOCTYPE {root} PUBLIC "-//Recordare//DTD MusicXML {declared_version} '
        f'{title_form}//EN" "http://www.musicxml.org/dtds/{form}.dtd">'
        f"<{root}{version_attribute}>{header}<part-list>{part_list}</part-list>"
        f"{bodies}</{root}>"
    ).encode()


def _document_identity_witness(version: str) -> GeneratedWitness:
    part_list = '<score-part id="P1"><part-name>Identity</part-name></score-part>'
    bodies = '<measure number="1"><part id="P1"/></measure>'
    data = _score_bytes(
        version,
        form="timewise",
        header="",
        part_list=part_list,
        bodies=bodies,
    )
    return GeneratedWitness(
        witness_id=f"WITNESS-MXML-DOCUMENT-IDENTITY-{version}",
        family="document identity and versions",
        standard_version=version,
        source_format="musicxml",
        data=data,
    )


def _header_markup(version: str) -> str:
    supports = '<supports element="print" type="yes"/>'
    relation = ""
    if version not in {"1.0", "1.1"}:
        supports = '<supports element="print" type="yes" attribute="new-system" value="yes"/>'
        relation = '<relation type="isPartOf">Evidence Collection</relation>'
    return (
        "<work><work-number>Op. 1</work-number><work-title>Evidence Work</work-title></work>"
        "<movement-number>I</movement-number><movement-title>Evidence Movement</movement-title>"
        '<identification><creator type="composer">Evidence Composer</creator>'
        '<rights type="copyright">Evidence Rights</rights>'
        "<encoding><encoding-date>2026-09-25</encoding-date>"
        '<encoder type="person">Evidence Encoder</encoder>'
        "<software>TeachMeMusic</software>"
        "<encoding-description>Losslessness evidence</encoding-description>"
        f"{supports}</encoding><source>Evidence Source</source>{relation}"
        '<miscellaneous><miscellaneous-field name="evidence">retained</miscellaneous-field>'
        "</miscellaneous></identification>"
    )


def _header_witness(version: str) -> GeneratedWitness:
    data = _score_bytes(
        version,
        form="partwise",
        header=_header_markup(version),
        part_list='<score-part id="P1"><part-name>Header</part-name></score-part>',
        bodies='<part id="P1"><measure number="1"/></part>',
    )
    return GeneratedWitness(
        witness_id=f"WITNESS-MXML-HEADER-{version}",
        family="header and identification",
        standard_version=version,
        source_format="musicxml",
        data=data,
    )


def _parts_witness(version: str, form: str) -> GeneratedWitness:
    group_time = "<group-time/>" if version not in {"1.0", "1.1"} else ""
    concert_score = (
        "<defaults><concert-score/></defaults>" if version in {"4.0", "4.1-draft"} else ""
    )
    part_identification = (
        '<identification><creator type="arranger">Part Creator</creator></identification>'
        if version in {"4.0", "4.1-draft"}
        else ""
    )
    part_membership = "<group>ensemble</group>" if version in {"4.0", "4.1-draft"} else ""
    instrument_detail = ""
    if version == "2.0":
        instrument_detail = "<solo/>"
    elif version not in {"1.0", "1.1"}:
        instrument_detail = (
            "<instrument-sound>keyboard.piano.grand</instrument-sound><solo/>"
            "<virtual-instrument><virtual-library>Evidence Library</virtual-library>"
            "<virtual-name>Evidence Piano</virtual-name></virtual-instrument>"
        )
    instrument = (
        '<score-instrument id="P1-I1"><instrument-name>Evidence Piano</instrument-name>'
        f"<instrument-abbreviation>Pno.</instrument-abbreviation>{instrument_detail}"
        "</score-instrument>"
    )
    part_list = (
        '<part-group type="start" number="1">'
        "<group-name>Evidence Group</group-name>"
        "<group-abbreviation>EG</group-abbreviation><group-symbol>brace</group-symbol>"
        f"<group-barline>yes</group-barline>{group_time}</part-group>"
        f'<score-part id="P1">{part_identification}<part-name>Evidence Piano</part-name>'
        f"<part-abbreviation>Pno.</part-abbreviation>{part_membership}{instrument}</score-part>"
        '<score-part id="P2"><part-name>Evidence Voice</part-name>'
        "<part-abbreviation>V.</part-abbreviation></score-part>"
        '<part-group type="stop" number="1"/>'
    )
    header = (
        "<work><work-number>Structure 1</work-number>"
        "<work-title>Structure Evidence</work-title></work>"
        "<movement-number>1</movement-number><movement-title>Opening</movement-title>"
        '<identification><creator type="composer">Structure Composer</creator>'
        f"</identification>{concert_score}"
    )
    note = (
        "<attributes><divisions>1</divisions></attributes>"
        "<note><rest><display-step>C</display-step><display-octave>4</display-octave></rest>"
        "<duration>1</duration><voice>1</voice><type>quarter</type></note>"
    )
    if form == "partwise":
        bodies = (
            f'<part id="P1"><measure number="1">{note}</measure></part>'
            f'<part id="P2"><measure number="1">{note}</measure></part>'
        )
    else:
        bodies = (
            f'<measure number="1"><part id="P1">{note}</part><part id="P2">{note}</part></measure>'
        )
    data = _score_bytes(
        version,
        form=form,
        header=header,
        part_list=part_list,
        bodies=bodies,
    )
    return GeneratedWitness(
        witness_id=f"WITNESS-MXML-PARTS-{form.upper()}-{version}",
        family="parts and groups",
        standard_version=version,
        source_format="musicxml",
        data=data,
    )


def _temporal_core_measure(version: str) -> str:
    scoped_number = "" if version == "1.0" else ' number="1"'
    return (
        "<attributes><divisions>6</divisions>"
        f"<key{scoped_number}><fifths>-1</fifths><mode>major</mode></key>"
        f'<time symbol="common"{scoped_number}><beats>4</beats>'
        "<beat-type>4</beat-type></time><staves>2</staves>"
        '<clef number="1"><sign>G</sign><line>2</line></clef>'
        '<clef number="2"><sign>F</sign><line>4</line></clef>'
        '<staff-details number="2"><staff-type>regular</staff-type>'
        "<staff-lines>5</staff-lines></staff-details>"
        "<transpose><diatonic>-1</diatonic><chromatic>-2</chromatic>"
        "<octave-change>0</octave-change></transpose></attributes>"
        "<note><pitch><step>C</step><octave>4</octave></pitch><duration>2</duration>"
        "<voice>1</voice><type>eighth</type><dot/><time-modification>"
        "<actual-notes>3</actual-notes><normal-notes>2</normal-notes>"
        "<normal-type>eighth</normal-type><normal-dot/></time-modification><staff>1</staff>"
        '<beam number="1">begin</beam><notations><tuplet type="start" number="1" '
        'bracket="yes" placement="above" show-number="both">'
        "<tuplet-actual><tuplet-number>3</tuplet-number><tuplet-type>eighth</tuplet-type>"
        "<tuplet-dot/></tuplet-actual><tuplet-normal><tuplet-number>2</tuplet-number>"
        "<tuplet-type>eighth</tuplet-type></tuplet-normal></tuplet></notations></note>"
        "<note><chord/><pitch><step>E</step><octave>4</octave></pitch>"
        "<duration>2</duration><voice>1</voice><type>eighth</type><staff>1</staff>"
        '<beam number="1">continue</beam></note>'
        "<note><rest><display-step>B</display-step><display-octave>4</display-octave></rest>"
        "<duration>2</duration><voice>1</voice><type>eighth</type><staff>1</staff>"
        '<beam number="1">end</beam><notations><tuplet type="stop" number="1"/>'
        "</notations></note><backup><duration>4</duration></backup>"
        "<note><unpitched><display-step>G</display-step><display-octave>5</display-octave>"
        "</unpitched><duration>6</duration><voice>2</voice><type>quarter</type>"
        "<staff>2</staff></note><forward><duration>6</duration></forward>"
        '<note><grace slash="yes" make-time="1" steal-time-following="10"/>'
        "<pitch><step>D</step><octave>5</octave></pitch><voice>2</voice>"
        "<type>16th</type><staff>2</staff></note>"
        "<note><cue/><pitch><step>E</step><octave>5</octave></pitch><duration>6</duration>"
        "<voice>2</voice><type>quarter</type><staff>2</staff></note>"
    )


def _temporal_core_witness(
    version: str, form: str, family: str, identifier: str
) -> GeneratedWitness:
    part_list = '<score-part id="P1"><part-name>Temporal Evidence</part-name></score-part>'
    measure = _temporal_core_measure(version)
    if form == "partwise":
        bodies = (
            f'<part id="P1"><measure number="7" implicit="yes" non-controlling="no">'
            f"{measure}</measure></part>"
        )
    else:
        bodies = (
            '<measure number="7" implicit="yes" non-controlling="no"><part id="P1">'
            f"{measure}</part></measure>"
        )
    return GeneratedWitness(
        witness_id=f"WITNESS-MXML-{identifier}-{form.upper()}-{version}",
        family=family,
        standard_version=version,
        source_format="musicxml",
        data=_score_bytes(
            version,
            form=form,
            header="",
            part_list=part_list,
            bodies=bodies,
        ),
    )


def _notation_note(
    step: str,
    notations: str,
    *,
    prefix: str = "",
    after_duration: str = "",
    suffix: str = "",
) -> str:
    return (
        f"<note>{prefix}<pitch><step>{step}</step><octave>4</octave></pitch>"
        f"<duration>1</duration>{after_duration}<type>quarter</type>{suffix}"
        f"<notations>{notations}</notations></note>"
    )


def _span_direction(action: str) -> str:
    wedge_type = "crescendo" if action == "start" else "stop"
    octave_type = "up" if action == "start" else "stop"
    line_end = "up" if action == "start" else "down"
    components = (
        f'<wedge type="{wedge_type}" number="1"/>',
        f'<dashes type="{action}" number="2"/>',
        f'<bracket type="{action}" number="3" line-end="{line_end}"/>',
        f'<pedal type="{action}" line="yes"/>',
        f'<octave-shift type="{octave_type}" number="5" size="8"/>',
    )
    return (
        '<direction placement="above">'
        + "".join(f"<direction-type>{item}</direction-type>" for item in components)
        + "<staff>1</staff></direction>"
    )


def _ties_witness(version: str) -> GeneratedWitness:
    first = _notation_note(
        "C",
        '<tied type="start"/><slur type="start" number="1"/>',
        after_duration='<tie type="start"/>',
    )
    second = _notation_note(
        "C",
        '<tied type="stop"/><slur type="stop" number="1"/>',
        after_duration='<tie type="stop"/>',
    )
    measure = (
        "<attributes><divisions>1</divisions></attributes>"
        + _span_direction("start")
        + first
        + _span_direction("stop")
        + second
    )
    return GeneratedWitness(
        witness_id=f"WITNESS-MXML-TIES-{version}",
        family="ties and spanners",
        standard_version=version,
        source_format="musicxml",
        data=_score_document(version, measure=measure),
    )


def _noteheads_witness(version: str) -> GeneratedWitness:
    point_marks = (
        '<fermata type="upright"/><arpeggiate direction="up" number="4"/>'
        '<non-arpeggiate type="top" number="5"/>'
    )
    start_spans = (
        '<glissando type="start" number="1" line-type="solid"/>'
        '<slide type="start" number="2" line-type="dashed"/>'
        '<other-notation type="start" number="3">custom</other-notation>'
    )
    stop_spans = (
        '<glissando type="stop" number="1" line-type="solid"/>'
        '<slide type="stop" number="2" line-type="dashed"/>'
        '<other-notation type="stop" number="3">custom</other-notation>'
    )
    notehead_text = (
        "<notehead-text><display-text>X</display-text>"
        "<accidental-text>sharp</accidental-text></notehead-text>"
        if version not in {"1.0", "1.1", "2.0"}
        else ""
    )
    notehead = '<notehead filled="yes" parentheses="no">diamond</notehead>' + notehead_text
    measure = (
        "<attributes><divisions>1</divisions></attributes>"
        + _notation_note("C", point_marks + start_spans, suffix=notehead)
        + _notation_note("D", stop_spans, suffix=notehead)
    )
    return GeneratedWitness(
        witness_id=f"WITNESS-MXML-NOTEHEADS-{version}",
        family="noteheads and notations",
        standard_version=version,
        source_format="musicxml",
        data=_score_document(version, measure=measure),
    )


def _articulations_witness(version: str) -> GeneratedWitness:
    tremolo_start = '<tremolo type="start">3</tremolo>'
    tremolo_stop = '<tremolo type="stop">3</tremolo>'
    if version in {"1.0", "1.1"}:
        tremolo_start = tremolo_stop = ""
    first = (
        '<articulations><accent placement="above"/><staccato placement="below"/>'
        '<strong-accent type="up"/></articulations><ornaments><trill-mark/>'
        '<accidental-mark placement="above">sharp</accidental-mark><turn/>'
        f'<wavy-line type="start" number="1"/>{tremolo_start}</ornaments>'
    )
    second = f'<ornaments><wavy-line type="stop" number="1"/>{tremolo_stop}</ornaments>'
    measure = (
        "<attributes><divisions>1</divisions></attributes>"
        + _notation_note("C", first)
        + _notation_note("D", second)
    )
    return GeneratedWitness(
        witness_id=f"WITNESS-MXML-ARTICULATIONS-{version}",
        family="articulations and ornaments",
        standard_version=version,
        source_format="musicxml",
        data=_score_document(version, measure=measure),
    )


def _technical_witness(version: str) -> GeneratedWitness:
    extra = ""
    if version == "3.0":
        extra = (
            '<hole><hole-type>A</hole-type><hole-closed location="bottom">half'
            "</hole-closed><hole-shape>round</hole-shape></hole>"
            "<arrow><arrow-direction>up</arrow-direction>"
            "<arrow-style>single</arrow-style></arrow>"
        )
    elif version not in {"1.0", "1.1", "2.0"}:
        extra = (
            '<hole><hole-type>A</hole-type><hole-closed location="bottom">half'
            "</hole-closed><hole-shape>round</hole-shape></hole>"
            "<arrow><arrow-direction>up</arrow-direction>"
            "<arrow-style>single</arrow-style><arrowhead/></arrow>"
            '<harmon-mute><harmon-closed location="bottom">half</harmon-closed>'
            "</harmon-mute>"
        )
    first = (
        "<technical><up-bow/><harmonic><natural/><touching-pitch/></harmonic>"
        '<fingering substitution="yes" alternate="no">2</fingering>'
        "<string>3</string><fret>5</fret><bend><bend-alter>1</bend-alter>"
        '<pre-bend/><with-bar placement="above">scoop</with-bar></bend>'
        '<hammer-on type="start" number="1">H</hammer-on>'
        '<pull-off type="start" number="2">P</pull-off>'
        f"{extra}</technical>"
    )
    second = (
        '<technical><hammer-on type="stop" number="1">H</hammer-on>'
        '<pull-off type="stop" number="2">P</pull-off></technical>'
    )
    measure = (
        "<attributes><divisions>1</divisions></attributes>"
        + _notation_note("C", first)
        + _notation_note("D", second)
    )
    return GeneratedWitness(
        witness_id=f"WITNESS-MXML-TECHNICAL-{version}",
        family="technical and instrument-specific notation",
        standard_version=version,
        source_format="musicxml",
        data=_score_document(version, measure=measure),
    )


def _barlines_witness(version: str) -> GeneratedWitness:
    navigation = "<segno/><coda/>" if version in {"4.0", "4.1-draft"} else ""
    measure = (
        '<barline location="left"><bar-style>heavy-light</bar-style>'
        '<ending number="1" type="start"/>'
        '<repeat direction="forward"/></barline>'
        "<attributes><divisions>1</divisions></attributes>"
        "<note><pitch><step>C</step><octave>4</octave></pitch><duration>1</duration>"
        "<type>quarter</type></note>"
        '<barline location="right"><bar-style>light-heavy</bar-style>'
        + navigation
        + '<fermata type="upright"/>'
        '<ending number="1" type="stop"/>'
        '<repeat direction="backward" times="2"/></barline>'
    )
    return GeneratedWitness(
        witness_id=f"WITNESS-MXML-BARLINES-{version}",
        family="barlines and navigation",
        standard_version=version,
        source_format="musicxml",
        data=_score_document(version, measure=measure),
    )


def _directions_witness(version: str) -> GeneratedWitness:
    direction = (
        '<direction placement="above"><direction-type><rehearsal>A</rehearsal>'
        "</direction-type><direction-type><words>Allegro</words></direction-type>"
        '<direction-type><metronome parentheses="yes"><beat-unit>quarter</beat-unit>'
        "<per-minute>96</per-minute></metronome></direction-type>"
        "<direction-type><segno/></direction-type><direction-type><coda/>"
        "</direction-type><direction-type><damp/></direction-type>"
        "<direction-type><damp-all/></direction-type>"
        "<direction-type><eyeglasses/></direction-type><staff>1</staff></direction>"
    )
    measure = (
        "<attributes><divisions>1</divisions></attributes>"
        + direction
        + "<note><rest/><duration>1</duration><type>quarter</type></note>"
    )
    return GeneratedWitness(
        witness_id=f"WITNESS-MXML-DIRECTIONS-{version}",
        family="directions, text, and tempo",
        standard_version=version,
        source_format="musicxml",
        data=_score_document(version, measure=measure),
    )


def _dynamics_witness(version: str) -> GeneratedWitness:
    direction = (
        '<direction placement="below"><direction-type><dynamics><p/><mf/>'
        "<other-dynamics>subito</other-dynamics></dynamics></direction-type>"
        "<staff>1</staff></direction>"
    )
    note = (
        "<note><pitch><step>C</step><octave>4</octave></pitch><duration>1</duration>"
        '<type>quarter</type><notations><dynamics placement="above"><f/>'
        "<other-dynamics>dolce</other-dynamics></dynamics></notations></note>"
    )
    return GeneratedWitness(
        witness_id=f"WITNESS-MXML-DYNAMICS-{version}",
        family="dynamics",
        standard_version=version,
        source_format="musicxml",
        data=_score_document(
            version,
            measure="<attributes><divisions>1</divisions></attributes>" + direction + note,
        ),
    )


def _lyrics_witness(version: str) -> GeneratedWitness:
    lyric_attributes = ' number="1" name="Verse"'
    elision = "<elision/>" if version in {"1.0", "1.1"} else "<elision>‿</elision>"
    legacy_extend = version in {"1.0", "1.1", "2.0"}
    extend_start = "<extend/>" if legacy_extend else '<extend type="start"/>'
    extend_stop = "<extend/>" if legacy_extend else '<extend type="stop"/>'
    first = (
        "<note><pitch><step>C</step><octave>4</octave></pitch><duration>1</duration>"
        "<type>quarter</type><lyric"
        + lyric_attributes
        + "><syllabic>begin</syllabic><text>Hel</text>"
        + elision
        + "<syllabic>end</syllabic><text>lo</text>"
        + extend_start
        + "<end-line/></lyric></note>"
    )
    second = (
        "<note><pitch><step>D</step><octave>4</octave></pitch><duration>1</duration>"
        "<type>quarter</type><lyric"
        + lyric_attributes
        + ">"
        + extend_stop
        + "<end-paragraph/></lyric></note>"
    )
    return GeneratedWitness(
        witness_id=f"WITNESS-MXML-LYRICS-{version}",
        family="lyrics",
        standard_version=version,
        source_format="musicxml",
        data=_score_document(
            version,
            measure="<attributes><divisions>1</divisions></attributes>" + first + second,
        ),
    )


def _harmony_witness(version: str) -> GeneratedWitness:
    frame = (
        "<frame><frame-strings>6</frame-strings><frame-frets>4</frame-frets>"
        "<first-fret>1</first-fret>"
        "<frame-note><string>6</string><fret>3</fret><fingering>2</fingering>"
        "</frame-note><frame-note><string>1</string><fret>3</fret>"
        "</frame-note></frame>"
    )
    placement = "" if version in {"1.0", "1.1"} else "<offset>1</offset><staff>1</staff>"
    harmony = (
        "<harmony><root><root-step>C</root-step><root-alter>1</root-alter></root>"
        "<kind>major-seventh</kind><inversion>1</inversion>"
        "<bass><bass-step>G</bass-step><bass-alter>-1</bass-alter></bass>"
        "<degree><degree-value>9</degree-value><degree-alter>1</degree-alter>"
        "<degree-type>add</degree-type></degree>" + frame + placement + "</harmony>"
    )
    measure = (
        "<attributes><divisions>2</divisions></attributes>"
        + harmony
        + "<note><rest/><duration>2</duration><type>quarter</type></note>"
    )
    return GeneratedWitness(
        witness_id=f"WITNESS-MXML-HARMONY-{version}",
        family="harmony and fret diagrams",
        standard_version=version,
        source_format="musicxml",
        data=_score_document(version, measure=measure),
    )


def _links_witness(version: str) -> GeneratedWitness:
    declared_version = "4.1" if version == "4.1-draft" else version
    version_attribute = "" if version == "1.0" else f' version="{declared_version}"'
    position = "" if version in {"1.0", "1.1"} else ' element="credit" position="1"'
    data = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        f'<!DOCTYPE score-partwise PUBLIC "-//Recordare//DTD MusicXML {declared_version} '
        'Partwise//EN" "http://www.musicxml.org/dtds/partwise.dtd">'
        f"<score-partwise{version_attribute}>"
        '<part-list><score-part id="P1"><part-name>Links</part-name>'
        '</score-part></part-list><part id="P1"><measure number="1">'
        '<link xmlns:xlink="http://www.w3.org/1999/xlink" '
        f'xlink:href="#measure-target" name="measure-link"{position}/>'
        '<bookmark id="measure-target" name="Measure"/>'
        '<grouping type="start" number="1"><feature type="motif">A</feature></grouping>'
        "</measure></part></score-partwise>"
    ).encode()
    return GeneratedWitness(
        witness_id=f"WITNESS-MXML-LINKS-{version}",
        family="links, bookmarks, and grouping",
        standard_version=version,
        source_format="musicxml",
        data=data,
    )


def _opus_witness(version: str) -> GeneratedWitness:
    declared_version = "4.1" if version == "4.1-draft" else version
    version_attribute = "" if version in {"1.0", "1.1"} else f' version="{declared_version}"'
    new_page = "" if version in {"1.0", "1.1"} else ' new-page="yes"'
    data = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        f'<!DOCTYPE opus PUBLIC "-//Recordare//DTD MusicXML {declared_version} Opus//EN" '
        '"http://www.musicxml.org/dtds/opus.dtd">'
        f"<opus{version_attribute}>"
        '<title>Evidence Collection</title><score xmlns:xlink="http://www.w3.org/1999/xlink" '
        f'xlink:href="score.musicxml"{new_page}/>'
        '<opus><title>Nested</title><opus-link xmlns:xlink="http://www.w3.org/1999/xlink" '
        'xlink:href="nested.xml"/></opus></opus>'
    ).encode()
    return GeneratedWitness(
        witness_id=f"WITNESS-MXML-AUXILIARY-OPUS-{version}",
        family="opus and sounds documents",
        standard_version=version,
        source_format="musicxml",
        data=data,
    )


def _sounds_witness(version: str) -> GeneratedWitness:
    declared_version = "4.1" if version == "4.1-draft" else version
    data = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        f'<!DOCTYPE sounds PUBLIC "-//Recordare//DTD MusicXML {declared_version} Sounds//EN" '
        '"http://www.musicxml.org/dtds/sounds.dtd">'
        '<sounds><sound id="keyboard.piano" primary="yes"/>'
        '<sound id="strings.violin" primary="no"/></sounds>'
    ).encode()
    return GeneratedWitness(
        witness_id=f"WITNESS-MXML-AUXILIARY-SOUNDS-{version}",
        family="opus and sounds documents",
        standard_version=version,
        source_format="musicxml",
        data=data,
    )


def _work_opus_witness(version: str) -> GeneratedWitness:
    declared_version = "4.1" if version == "4.1-draft" else version
    version_attribute = "" if version == "1.0" else f' version="{declared_version}"'
    data = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        f'<!DOCTYPE score-partwise PUBLIC "-//Recordare//DTD MusicXML {declared_version} '
        'Partwise//EN" "http://www.musicxml.org/dtds/partwise.dtd">'
        f"<score-partwise{version_attribute}><work><work-title>Evidence Work</work-title>"
        '<opus xmlns:xlink="http://www.w3.org/1999/xlink" '
        'xlink:href="collection.xml"/></work><part-list><score-part id="P1">'
        "<part-name>Evidence</part-name></score-part></part-list>"
        '<part id="P1"><measure number="1"/></part></score-partwise>'
    ).encode()
    return GeneratedWitness(
        witness_id=f"WITNESS-MXML-AUXILIARY-SCORE-{version}",
        family="opus and sounds documents",
        standard_version=version,
        source_format="musicxml",
        data=data,
    )


def _playback_witness(version: str) -> GeneratedWitness:
    declared_version = "4.1" if version == "4.1-draft" else version
    version_attribute = "" if version == "1.0" else f' version="{declared_version}"'
    modern = version not in {"1.0", "1.1"}
    device_id = ' id="P1-I1"' if version not in {"1.0", "1.1", "2.0"} else ""
    spatial = "<volume>80</volume><pan>0</pan>" if modern else ""
    pizzicato = ' pizzicato="no"' if modern else ""
    data = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        f'<!DOCTYPE score-partwise PUBLIC "-//Recordare//DTD MusicXML {declared_version} '
        'Partwise//EN" "http://www.musicxml.org/dtds/partwise.dtd">'
        f'<score-partwise{version_attribute}><part-list><score-part id="P1">'
        '<part-name>Playback</part-name><score-instrument id="P1-I1">'
        "<instrument-name>Piano</instrument-name></score-instrument>"
        f"<midi-device{device_id}>Evidence Device</midi-device>"
        '<midi-instrument id="P1-I1"><midi-channel>1</midi-channel>'
        "<midi-name>Evidence Piano</midi-name><midi-bank>1</midi-bank>"
        f"<midi-program>1</midi-program>{spatial}"
        '</midi-instrument></score-part></part-list><part id="P1"><measure number="1">'
        "<attributes><divisions>1</divisions></attributes>"
        f'<sound tempo="96" dynamics="80" dacapo="no"{pizzicato}/>'
        "<note><rest/><duration>1</duration><type>quarter</type></note>"
        "</measure></part></score-partwise>"
    ).encode()
    return GeneratedWitness(
        witness_id=f"WITNESS-MXML-PLAYBACK-{version}",
        family="playback, midi, listening, and assessment",
        standard_version=version,
        source_format="musicxml",
        data=data,
    )


def _layout_witness(version: str) -> GeneratedWitness:
    defaults = ""
    print_children = ""
    if version != "1.0":
        appearance = ""
        if version != "1.1":
            distance = (
                '<distance type="hyphen">10</distance>' if version not in {"1.1", "2.0"} else ""
            )
            appearance = (
                '<appearance><line-width type="staff">1.25</line-width>'
                '<note-size type="cue">75</note-size>'
                f"{distance}"
                '<other-appearance type="evidence">retained</other-appearance>'
                "</appearance>"
            )
        page_defaults = (
            "<page-layout><page-height>1600</page-height>"
            '<page-width>1200</page-width><page-margins type="both">'
            "<left-margin>60</left-margin><right-margin>50</right-margin>"
            "<top-margin>40</top-margin><bottom-margin>30</bottom-margin>"
            "</page-margins></page-layout>"
            if version != "1.1"
            else ""
        )
        defaults = (
            "<defaults><scaling><millimeters>7</millimeters><tenths>40</tenths>"
            f"</scaling>{page_defaults}<system-layout><system-margins>"
            "<left-margin>10</left-margin><right-margin>5</right-margin>"
            "</system-margins><system-distance>90</system-distance>"
            "<top-system-distance>70</top-system-distance></system-layout>"
            '<staff-layout number="1"><staff-distance>65</staff-distance></staff-layout>'
            f"{appearance}</defaults>"
        )
        print_page = (
            "<page-layout><page-height>1500</page-height><page-width>1100</page-width>"
            '<page-margins type="odd"><left-margin>55</left-margin>'
            "<right-margin>45</right-margin><top-margin>35</top-margin>"
            "<bottom-margin>25</bottom-margin></page-margins></page-layout>"
            if version != "1.1"
            else ""
        )
        print_children = (
            f"{print_page}"
            "<system-layout><system-margins><left-margin>8</left-margin>"
            "<right-margin>4</right-margin></system-margins>"
            "<system-distance>85</system-distance><top-system-distance>60"
            '</top-system-distance></system-layout><staff-layout number="1">'
            "<staff-distance>60</staff-distance></staff-layout>"
        )
    measure_numbering = (
        "<measure-numbering>system</measure-numbering>" if version not in {"1.0", "1.1"} else ""
    )
    measure = (
        '<print new-page="yes" new-system="no" staff-spacing="12">'
        f"{print_children}{measure_numbering}</print>"
        "<attributes><divisions>1</divisions></attributes>"
        "<note><rest/><duration>1</duration><type>quarter</type></note>"
    )
    return GeneratedWitness(
        witness_id=f"WITNESS-MXML-LAYOUT-{version}",
        family="layout and appearance",
        standard_version=version,
        source_format="musicxml",
        data=_score_document(version, header=defaults, measure=measure),
    )


def _presentation_witness(version: str) -> GeneratedWitness:
    attributes = (
        'default-x="10.5" default-y="20.5" relative-x="1.5" relative-y="-2.5" '
        'font-family="Evidence Serif" font-style="italic" font-size="12.5" '
        'font-weight="bold" justify="center" xml:lang="en-US"'
    )
    if version != "1.0":
        attributes += ' color="#112233" halign="right" valign="middle" enclosure="rectangle"'
    if version not in {"1.0", "1.1"}:
        attributes += (
            ' underline="1" overline="2" line-through="1" rotation="15"'
            ' letter-spacing="normal" line-height="18" dir="ltr"'
        )
    if version not in {"1.0", "1.1", "2.0"}:
        attributes += ' xml:space="preserve"'
    measure = (
        "<attributes><divisions>1</divisions></attributes><direction>"
        f"<direction-type><words {attributes}>Evidence Text</words></direction-type>"
        "</direction><note><rest/><duration>1</duration><type>quarter</type></note>"
    )
    return GeneratedWitness(
        witness_id=f"WITNESS-MXML-PRESENTATION-{version}",
        family="presentation text and shared formatting",
        standard_version=version,
        source_format="musicxml",
        data=_score_document(version, measure=measure),
    )


def _pitch_witness(version: str) -> GeneratedWitness:
    level_one = 'cautionary="yes" editorial="no" size="full"'
    level_two = 'cautionary="no" editorial="yes" size="cue"'
    if version != "1.0":
        level_one += ' parentheses="yes" bracket="no"'
        level_two += ' parentheses="no" bracket="yes"'
    style = ' default-x="1.5" color="#112233"' if version != "1.0" else ' default-x="1.5"'
    smufl = ' smufl="accidentalSharp"' if version in {"4.0", "4.1-draft"} else ""
    third = ""
    if version != "1.0":
        third = (
            "<note><pitch><step>F</step><alter>1</alter><octave>5</octave></pitch>"
            "<duration>1</duration><type>quarter</type>"
            '<accidental size="large">sharp</accidental></note>'
        )
    measure = (
        "<attributes><divisions>1</divisions></attributes>"
        "<note><pitch><step>C</step><alter>-0.5</alter><octave>4</octave></pitch>"
        "<duration>1</duration><type>quarter</type>"
        f"<accidental {level_one}{style}{smufl}>flat</accidental></note>"
        "<note><pitch><step>D</step><alter>0.5</alter><octave>4</octave></pitch>"
        "<duration>1</duration><type>quarter</type>"
        f"<accidental {level_two}>quarter-sharp</accidental></note>"
        f"{third}"
        "<note><rest><display-step>G</display-step><display-octave>4</display-octave></rest>"
        "<duration>1</duration><type>quarter</type></note>"
    )
    data = _score_document(version, measure=measure)
    return GeneratedWitness(
        witness_id=f"WITNESS-MXML-PITCH-{version}",
        family="written pitch and accidentals",
        standard_version=version,
        source_format="musicxml",
        data=data,
    )


def _figured_bass_witness(version: str) -> GeneratedWitness:
    first_attributes = 'print-object="no" print-dot="yes" print-spacing="no"'
    second_attributes = 'print-object="yes" print-dot="no" print-spacing="yes"'
    if version != "1.0":
        first_attributes += ' parentheses="yes"'
        second_attributes += ' parentheses="no"'
    if version not in {"1.0", "1.1"}:
        first_attributes += ' default-x="2.5" color="#224466" font-style="italic"'
    if version in {"4.0", "4.1-draft"}:
        first_attributes += ' placement="above"'
        second_attributes += ' placement="below"'
    if version in {"3.1", "4.0", "4.1-draft"}:
        first_attributes += ' id="bass-1"'
        second_attributes += ' id="bass-2"'
    first_extend = (
        "<extend/>"
        if version == "2.0"
        else ('<extend type="start"/>' if version not in {"1.0", "1.1"} else "")
    )
    second_extend = (
        "<extend/>"
        if version == "2.0"
        else ('<extend type="stop"/>' if version not in {"1.0", "1.1"} else "")
    )
    measure = (
        "<attributes><divisions>2</divisions></attributes>"
        f"<figured-bass {first_attributes}><figure><prefix>sharp</prefix>"
        f"<figure-number>6</figure-number><suffix>natural</suffix>{first_extend}</figure>"
        "<duration>3</duration></figured-bass>"
        "<note><pitch><step>C</step><octave>4</octave></pitch><duration>2</duration>"
        "<type>quarter</type></note>"
        f"<figured-bass {second_attributes}><figure><prefix>flat</prefix>"
        f"<figure-number>4</figure-number><suffix>slash</suffix>{second_extend}</figure>"
        "<duration>2</duration></figured-bass>"
        "<note><pitch><step>D</step><octave>4</octave></pitch><duration>2</duration>"
        "<type>quarter</type></note>"
    )
    data = _score_document(version, measure=measure)
    return GeneratedWitness(
        witness_id=f"WITNESS-MXML-FIGURED-BASS-{version}",
        family="figured bass",
        standard_version=version,
        source_format="musicxml",
        data=data,
    )


def _credits_witness(version: str) -> GeneratedWitness:
    appearance = ""
    if version != "1.1":
        glyph = (
            '<glyph type="quarter-rest">restQuarter</glyph>'
            if version in {"3.1", "4.0", "4.1-draft"}
            else ""
        )
        appearance = (
            '<appearance><note-size type="cue">75</note-size>'
            f'{glyph}<other-appearance type="evidence">retained</other-appearance>'
            "</appearance>"
        )
    defaults = (
        "<defaults><scaling><millimeters>7</millimeters><tenths>40</tenths></scaling>"
        f"{appearance}"
        '<music-font font-family="Bravura" font-size="20" font-weight="bold"/>'
        '<word-font font-family="Evidence Serif" font-size="12" font-style="italic"/>'
        '<lyric-font number="1" name="Verse" font-family="Evidence Sans" font-size="11"/>'
        '<lyric-language number="1" name="Verse" xml:lang="en-US"/>'
        "</defaults>"
    )
    credit_type = "<credit-type>title</credit-type>" if version not in {"1.1", "2.0"} else ""
    page = ' page="2"' if version != "1.1" else ""
    identifiers = ' id="credit-1"' if version in {"4.0", "4.1-draft"} else ""
    word_id = ' id="credit-word-1"' if version in {"4.0", "4.1-draft"} else ""
    credit = (
        f"<credit{page}{identifiers}>{credit_type}"
        f'<credit-words{word_id} default-x="10" default-y="20" '
        'font-family="Evidence Serif">Evidence Score</credit-words></credit>'
    )
    staff_size = (
        "<attributes><divisions>1</divisions><staff-details>"
        '<staff-size scaling="80">75</staff-size></staff-details></attributes>'
        if version in {"4.0", "4.1-draft"}
        else ""
    )
    data = _score_document(version, header=defaults + credit, measure=staff_size)
    return GeneratedWitness(
        witness_id=f"WITNESS-MXML-CREDITS-{version}",
        family="credits and defaults",
        standard_version=version,
        source_format="musicxml",
        data=data,
    )
