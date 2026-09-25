"""Independent stdlib-only reader for generated losslessness witnesses.

This module must not import the production MusicXML boundary, mapper, lxml, or
canonical model. It reports source facts that a separate comparator checks
against production output.
"""

from __future__ import annotations

import io
import xml.etree.ElementTree as element_tree
import zipfile
from dataclasses import dataclass
from fractions import Fraction

from .losslessness_contract import EvidenceValue

MXL_ORACLE_ID = "teachmemusic.musicxml.oracle.mxl-packaging-stdlib/1"
INSTRUMENT_ORACLE_ID = "teachmemusic.musicxml.oracle.instruments-stdlib/1"
PITCH_ORACLE_ID = "teachmemusic.musicxml.oracle.written-pitch-stdlib/1"
FIGURED_BASS_ORACLE_ID = "teachmemusic.musicxml.oracle.figured-bass-stdlib/1"
CREDITS_ORACLE_ID = "teachmemusic.musicxml.oracle.credits-defaults-stdlib/1"
DOCUMENT_IDENTITY_ORACLE_ID = "teachmemusic.musicxml.oracle.document-identity-stdlib/1"
HEADER_ORACLE_ID = "teachmemusic.musicxml.oracle.header-identification-stdlib/1"
PARTS_ORACLE_ID = "teachmemusic.musicxml.oracle.parts-groups-stdlib/1"
MEASURES_ORACLE_ID = "teachmemusic.musicxml.oracle.measures-cursor-stdlib/1"
ATTRIBUTES_ORACLE_ID = "teachmemusic.musicxml.oracle.attributes-staff-state-stdlib/1"
NOTES_ORACLE_ID = "teachmemusic.musicxml.oracle.notes-rests-stdlib/1"
RHYTHM_ORACLE_ID = "teachmemusic.musicxml.oracle.rhythm-beams-tuplets-stdlib/1"
TIES_ORACLE_ID = "teachmemusic.musicxml.oracle.ties-spanners-stdlib/1"
NOTEHEADS_ORACLE_ID = "teachmemusic.musicxml.oracle.noteheads-notations-stdlib/1"
ARTICULATIONS_ORACLE_ID = "teachmemusic.musicxml.oracle.articulations-ornaments-stdlib/1"
TECHNICAL_ORACLE_ID = "teachmemusic.musicxml.oracle.technical-notation-stdlib/1"
BARLINES_ORACLE_ID = "teachmemusic.musicxml.oracle.barlines-navigation-stdlib/1"
DIRECTIONS_ORACLE_ID = "teachmemusic.musicxml.oracle.directions-text-tempo-stdlib/1"
DYNAMICS_ORACLE_ID = "teachmemusic.musicxml.oracle.dynamics-stdlib/1"
LYRICS_ORACLE_ID = "teachmemusic.musicxml.oracle.lyrics-stdlib/1"
HARMONY_ORACLE_ID = "teachmemusic.musicxml.oracle.harmony-fret-diagrams-stdlib/1"
LINKS_ORACLE_ID = "teachmemusic.musicxml.oracle.links-bookmarks-grouping-stdlib/1"
AUXILIARY_ORACLE_ID = "teachmemusic.musicxml.oracle.opus-sounds-documents-stdlib/1"
PLAYBACK_ORACLE_ID = "teachmemusic.musicxml.oracle.playback-midi-stdlib/1"
LAYOUT_ORACLE_ID = "teachmemusic.musicxml.oracle.layout-appearance-stdlib/1"
PRESENTATION_ORACLE_ID = "teachmemusic.musicxml.oracle.presentation-formatting-stdlib/1"
_XML_LANG = "{http://www.w3.org/XML/1998/namespace}lang"
_XML_SPACE = "{http://www.w3.org/XML/1998/namespace}space"
_XLINK = "{http://www.w3.org/1999/xlink}"


@dataclass(frozen=True, slots=True)
class MxlOracleFacts:
    """Independent source facts for one generated MXL container."""

    standard_version: str
    entries: tuple[str, ...]
    rootfiles: tuple[tuple[str, str | None], ...]

    def fact_map(self) -> dict[str, EvidenceValue]:
        """Return comparison facts shared with the production projection."""

        return {
            "container_present": True,
            "container_standard_version": self.standard_version,
            "entries": self.entries,
            "rootfile_count": len(self.rootfiles),
            "rootfile_order": tuple(path for path, _ in self.rootfiles),
            "rootfile_paths": tuple(path for path, _ in self.rootfiles),
            "rootfile_media_types": tuple(media_type for _, media_type in self.rootfiles),
            "selected_rootfile": self.rootfiles[0][0],
        }


def read_mxl_packaging_facts(data: bytes) -> MxlOracleFacts:
    """Read ZIP and XML facts without calling any production ingestion code."""

    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        names = tuple(sorted(info.filename for info in archive.infolist()))
        if len(names) != len(set(names)):
            raise ValueError("independent oracle rejects duplicate archive names")
        container_bytes = archive.read("META-INF/container.xml")
        container = element_tree.fromstring(container_bytes)
        if container.tag != "container":
            raise ValueError("independent oracle expected a container root")
        rootfiles_element = container.find("rootfiles")
        if rootfiles_element is None:
            raise ValueError("independent oracle expected rootfiles")
        rootfiles = tuple(
            (element.attrib["full-path"], element.attrib.get("media-type"))
            for element in rootfiles_element.findall("rootfile")
        )
        if not rootfiles:
            raise ValueError("independent oracle expected at least one rootfile")
        score = element_tree.fromstring(archive.read(rootfiles[0][0]))
        declared_version = score.attrib.get("version")
        if declared_version is None:
            raise ValueError("independent oracle expected a score version")
        standard_version = "4.1-draft" if declared_version == "4.1" else declared_version
    return MxlOracleFacts(
        standard_version=standard_version,
        entries=names,
        rootfiles=rootfiles,
    )


@dataclass(frozen=True, slots=True)
class InstrumentOracleFacts:
    """Independent score-part and instrument facts from one score witness."""

    standard_version: str
    part_ids: tuple[str, ...]
    instrument_records: tuple[tuple[EvidenceValue, ...], ...]
    part_links: tuple[tuple[EvidenceValue, ...], ...]

    def fact_map(self) -> dict[str, EvidenceValue]:
        """Return exact values shared with the canonical projection."""

        return {
            "score_part_count": len(self.part_ids),
            "part_ids": self.part_ids,
            "instrument_count": len(self.instrument_records),
            "instrument_order": tuple(item[1] for item in self.instrument_records),
            "instrument_records": _evidence_tuple(self.instrument_records),
            "part_links": _evidence_tuple(self.part_links),
        }


def read_instrument_facts(data: bytes) -> InstrumentOracleFacts:
    """Read instrument facts without production parsing or canonical types."""

    root = element_tree.fromstring(data)
    declared = root.attrib.get("version", "1.0")
    standard_version = "4.1-draft" if declared == "4.1" else declared
    part_list = root.find("part-list")
    if part_list is None:
        raise ValueError("independent oracle expected a part-list")
    part_ids: list[str] = []
    instruments: list[tuple[EvidenceValue, ...]] = []
    part_links: list[tuple[EvidenceValue, ...]] = []
    for part in part_list.findall("score-part"):
        part_id = part.attrib["id"]
        part_ids.append(part_id)
        for instrument in part.findall("score-instrument"):
            ensemble = instrument.find("ensemble")
            ensemble_text = ensemble.text if ensemble is not None else None
            virtual = instrument.find("virtual-instrument")
            instruments.append(
                (
                    part_id,
                    instrument.attrib["id"],
                    instrument.findtext("instrument-name"),
                    instrument.findtext("instrument-abbreviation"),
                    instrument.findtext("instrument-sound"),
                    instrument.find("solo") is not None,
                    ensemble is not None,
                    int(ensemble_text) if ensemble_text else None,
                    (
                        virtual.findtext("virtual-library"),
                        virtual.findtext("virtual-name"),
                    )
                    if virtual is not None
                    else None,
                )
            )
        for link in part.findall("part-link"):
            part_links.append(
                (
                    part_id,
                    link.attrib["{http://www.w3.org/1999/xlink}href"],
                    tuple(item.attrib["id"] for item in link.findall("instrument-link")),
                )
            )
    return InstrumentOracleFacts(
        standard_version=standard_version,
        part_ids=tuple(part_ids),
        instrument_records=tuple(instruments),
        part_links=tuple(part_links),
    )


@dataclass(frozen=True, slots=True)
class PitchOracleFacts:
    """Independent written pitch, rest-position, and accidental facts."""

    standard_version: str
    pitch_records: tuple[EvidenceValue, ...]
    accidental_records: tuple[EvidenceValue, ...]
    rest_records: tuple[EvidenceValue, ...]

    def fact_map(self) -> dict[str, EvidenceValue]:
        return {
            "event_count": len(self.pitch_records) + len(self.rest_records),
            "pitch_records": self.pitch_records,
            "accidental_records": self.accidental_records,
            "rest_records": self.rest_records,
        }


def read_pitch_facts(data: bytes) -> PitchOracleFacts:
    """Read written pitch and accidental facts without production mapping."""

    root = element_tree.fromstring(data)
    pitches: list[EvidenceValue] = []
    accidentals: list[EvidenceValue] = []
    rests: list[EvidenceValue] = []
    for note in root.findall(".//note"):
        pitch = note.find("pitch")
        rest = note.find("rest")
        if pitch is not None:
            pitches.append(
                (
                    pitch.findtext("step"),
                    _fraction_fact(pitch.findtext("alter") or "0"),
                    _integer_text(pitch.findtext("octave")),
                )
            )
        if rest is not None:
            display_step = rest.findtext("display-step")
            display_octave = rest.findtext("display-octave")
            rests.append(
                (
                    _yes_no(rest.attrib.get("measure")),
                    (
                        display_step,
                        _fraction_fact("0"),
                        _integer_text(display_octave),
                    )
                    if display_step is not None and display_octave is not None
                    else None,
                )
            )
        for accidental in note.findall("accidental"):
            accidentals.append(
                (
                    accidental.text or "",
                    _yes_no(accidental.attrib.get("cautionary")),
                    _yes_no(accidental.attrib.get("editorial")),
                    _yes_no(accidental.attrib.get("parentheses")),
                    _yes_no(accidental.attrib.get("bracket")),
                    accidental.attrib.get("size"),
                    accidental.attrib.get("smufl"),
                    _style_fact(accidental),
                )
            )
    return PitchOracleFacts(
        standard_version=_standard_version(root),
        pitch_records=tuple(pitches),
        accidental_records=tuple(accidentals),
        rest_records=tuple(rests),
    )


@dataclass(frozen=True, slots=True)
class FiguredBassOracleFacts:
    """Independent semantic and print facts for figured bass."""

    standard_version: str
    records: tuple[tuple[EvidenceValue, ...], ...]

    def fact_map(self) -> dict[str, EvidenceValue]:
        return {
            "figured_bass_count": len(self.records),
            "figured_bass_records": self.records,
            "figure_records": tuple(item[0] for item in self.records),
            "duration_records": tuple(item[1] for item in self.records),
            "control_records": tuple(item[2:9] for item in self.records),
        }


def read_figured_bass_facts(data: bytes) -> FiguredBassOracleFacts:
    """Read figured-bass facts without production parsing or canonical types."""

    root = element_tree.fromstring(data)
    divisions = _integer_text(root.findtext(".//divisions")) or 1
    records: list[tuple[EvidenceValue, ...]] = []
    for element in root.findall(".//figured-bass"):
        figures: list[EvidenceValue] = []
        for figure in element.findall("figure"):
            extend = figure.find("extend")
            figures.append(
                (
                    figure.findtext("prefix"),
                    figure.findtext("figure-number"),
                    figure.findtext("suffix"),
                    extend is not None,
                    extend.attrib.get("type") if extend is not None else None,
                )
            )
        duration = element.findtext("duration")
        records.append(
            (
                tuple(figures),
                _fraction_fact(Fraction(int(duration or "0"), divisions)),
                _yes_no(element.attrib.get("parentheses")),
                _yes_no(element.attrib.get("print-object")),
                _yes_no(element.attrib.get("print-dot")),
                _yes_no(element.attrib.get("print-spacing")),
                element.attrib.get("placement"),
                element.attrib.get("id"),
                _style_fact(element),
            )
        )
    return FiguredBassOracleFacts(
        standard_version=_standard_version(root),
        records=tuple(records),
    )


@dataclass(frozen=True, slots=True)
class CreditsOracleFacts:
    """Independent score-default, credit, and staff-size facts."""

    standard_version: str
    defaults_present: bool
    scaling: EvidenceValue
    appearance: tuple[EvidenceValue, ...]
    fonts: tuple[EvidenceValue, ...]
    lyric_languages: tuple[EvidenceValue, ...]
    credits: tuple[EvidenceValue, ...]
    staff_sizes: tuple[EvidenceValue, ...]

    def fact_map(self) -> dict[str, EvidenceValue]:
        return {
            "defaults_present": self.defaults_present,
            "scaling": self.scaling,
            "appearance": self.appearance,
            "fonts": self.fonts,
            "lyric_languages": self.lyric_languages,
            "credits": self.credits,
            "staff_sizes": self.staff_sizes,
        }


def read_credits_facts(data: bytes) -> CreditsOracleFacts:
    """Read defaults and credits without production mapping or canonical types."""

    root = element_tree.fromstring(data)
    defaults = root.find("defaults")
    scaling: EvidenceValue = None
    appearance: list[EvidenceValue] = []
    fonts: list[EvidenceValue] = []
    lyric_languages: list[EvidenceValue] = []
    if defaults is not None:
        scaling_element = defaults.find("scaling")
        if scaling_element is not None:
            scaling = (
                _fraction_fact(scaling_element.findtext("millimeters") or "0"),
                _fraction_fact(scaling_element.findtext("tenths") or "0"),
            )
        appearance_element = defaults.find("appearance")
        if appearance_element is not None:
            for child in appearance_element:
                kind = child.tag
                value = child.text or ""
                appearance.append(
                    (
                        kind,
                        child.attrib.get("type") or "",
                        _fraction_fact(value)
                        if kind in {"line-width", "note-size", "distance"}
                        else None,
                        value if kind not in {"line-width", "note-size", "distance"} else None,
                    )
                )
        for kind in ("music-font", "word-font"):
            element = defaults.find(kind)
            if element is not None:
                fonts.append((kind, _style_fact(element)))
        for element in defaults.findall("lyric-font"):
            fonts.append(
                (
                    "lyric-font",
                    element.attrib.get("number"),
                    element.attrib.get("name"),
                    _style_fact(element),
                )
            )
        lyric_languages.extend(
            (
                element.attrib.get("number"),
                element.attrib.get("name"),
                element.attrib.get(_XML_LANG) or "",
            )
            for element in defaults.findall("lyric-language")
        )
    credits: list[EvidenceValue] = []
    for credit in root.findall("credit"):
        items: list[EvidenceValue] = []
        for child in credit:
            if child.tag in {"credit-words", "credit-symbol"}:
                items.append(
                    (
                        "words" if child.tag == "credit-words" else "symbol",
                        child.text or "",
                        _style_fact(child),
                        None,
                        None,
                        None,
                        child.attrib.get("id"),
                    )
                )
            elif child.tag == "credit-image":
                items.append(
                    (
                        "image",
                        child.attrib.get("source") or "",
                        _style_fact(child),
                        child.attrib.get("type"),
                        _optional_fraction_fact(child.attrib.get("width")),
                        _optional_fraction_fact(child.attrib.get("height")),
                        child.attrib.get("id"),
                    )
                )
        credits.append(
            (
                int(credit.attrib.get("page", "1")),
                tuple(item.text or "" for item in credit.findall("credit-type")),
                tuple(items),
                credit.attrib.get("id"),
            )
        )
    staff_sizes = tuple(
        (
            _fraction_fact(element.text or "0"),
            _optional_fraction_fact(element.attrib.get("scaling")),
        )
        for element in root.findall(".//staff-size")
    )
    return CreditsOracleFacts(
        standard_version=_standard_version(root),
        defaults_present=defaults is not None,
        scaling=scaling,
        appearance=tuple(appearance),
        fonts=tuple(fonts),
        lyric_languages=tuple(lyric_languages),
        credits=tuple(credits),
        staff_sizes=staff_sizes,
    )


@dataclass(frozen=True, slots=True)
class DocumentIdentityOracleFacts:
    """Independent root, version, and validation-boundary source facts."""

    standard_version: str
    declared_version: str | None
    document_form: str
    part_ids: tuple[str, ...]
    measure_count: int

    def fact_map(self) -> dict[str, EvidenceValue]:
        return {
            "standard_version": self.standard_version,
            "declared_version": self.declared_version,
            "document_form": self.document_form,
            "part_ids": self.part_ids,
            "measure_count": self.measure_count,
        }


def read_document_identity_facts(data: bytes) -> DocumentIdentityOracleFacts:
    """Read document identity without production boundary imports."""

    root = element_tree.fromstring(data)
    part_list = root.find("part-list")
    if part_list is None:
        raise ValueError("independent identity oracle expected part-list")
    return DocumentIdentityOracleFacts(
        standard_version=_standard_version(root),
        declared_version=root.attrib.get("version"),
        document_form=root.tag,
        part_ids=tuple(item.attrib["id"] for item in part_list.findall("score-part")),
        measure_count=len(root.findall("measure"))
        if root.tag == "score-timewise"
        else sum(len(part.findall("measure")) for part in root.findall("part")),
    )


@dataclass(frozen=True, slots=True)
class HeaderOracleFacts:
    """Independent work, movement, identification, and encoding facts."""

    facts: tuple[tuple[str, EvidenceValue], ...]

    def fact_map(self) -> dict[str, EvidenceValue]:
        return dict(self.facts)


def read_header_facts(data: bytes) -> HeaderOracleFacts:
    """Read complete header facts without production mapping imports."""

    root = element_tree.fromstring(data)
    work = root.find("work")
    identification = root.find("identification")
    encoding = identification.find("encoding") if identification is not None else None
    miscellaneous = identification.find("miscellaneous") if identification is not None else None
    facts: dict[str, EvidenceValue] = {
        "work": (
            work.findtext("work-number") if work is not None else None,
            work.findtext("work-title") if work is not None else None,
        ),
        "movement": (root.findtext("movement-number"), root.findtext("movement-title")),
        "creators": tuple(
            (item.attrib.get("type"), item.text or "")
            for item in (identification.findall("creator") if identification is not None else ())
        ),
        "rights": tuple(
            (item.text or "", item.attrib.get("type"))
            for item in (identification.findall("rights") if identification is not None else ())
        ),
        "source": identification.findtext("source") if identification is not None else None,
        "relations": tuple(
            (item.text or "", item.attrib.get("type"))
            for item in (identification.findall("relation") if identification is not None else ())
        ),
        "encoding": _encoding_fact(encoding),
        "miscellaneous": tuple(
            (item.attrib.get("name") or "", item.text or "")
            for item in (
                miscellaneous.findall("miscellaneous-field") if miscellaneous is not None else ()
            )
        ),
    }
    return HeaderOracleFacts(tuple(sorted(facts.items())))


@dataclass(frozen=True, slots=True)
class PartsOracleFacts:
    """Independent score hierarchy, part-group, and body facts."""

    facts: tuple[tuple[str, EvidenceValue], ...]

    def fact_map(self) -> dict[str, EvidenceValue]:
        return dict(self.facts)


def read_parts_facts(data: bytes) -> PartsOracleFacts:
    """Read partwise or timewise score hierarchy without production mapping."""

    root = element_tree.fromstring(data)
    part_list = root.find("part-list")
    if part_list is None:
        raise ValueError("independent parts oracle expected part-list")
    group_records: list[EvidenceValue] = []
    definition_records: list[tuple[EvidenceValue, ...]] = []
    instrument_records: list[EvidenceValue] = []
    for source_order, item in enumerate(part_list, start=1):
        if item.tag == "part-group":
            group_records.append(
                (
                    item.attrib.get("number", "1"),
                    item.attrib.get("type", ""),
                    item.findtext("group-name"),
                    item.findtext("group-abbreviation"),
                    item.findtext("group-symbol"),
                    item.findtext("group-barline"),
                    source_order,
                    item.find("group-time") is not None,
                )
            )
        elif item.tag == "score-part":
            identification = item.find("identification")
            definition_records.append(
                (
                    item.attrib.get("id", ""),
                    item.findtext("part-name"),
                    item.findtext("part-abbreviation"),
                    tuple(group.text or "" for group in item.findall("group")),
                    tuple(
                        (creator.attrib.get("type"), creator.text or "")
                        for creator in (
                            identification.findall("creator") if identification is not None else ()
                        )
                    ),
                )
            )
            for instrument in item.findall("score-instrument"):
                virtual = instrument.find("virtual-instrument")
                ensemble = instrument.find("ensemble")
                instrument_records.append(
                    (
                        item.attrib.get("id", ""),
                        instrument.attrib.get("id", ""),
                        instrument.findtext("instrument-name"),
                        instrument.findtext("instrument-abbreviation"),
                        instrument.findtext("instrument-sound"),
                        instrument.find("solo") is not None,
                        ensemble is not None,
                        int(ensemble.text) if ensemble is not None and ensemble.text else None,
                        (
                            virtual.findtext("virtual-library"),
                            virtual.findtext("virtual-name"),
                        )
                        if virtual is not None
                        else None,
                    )
                )
    body_by_part: dict[str, list[element_tree.Element]] = {
        str(item[0]): [] for item in definition_records
    }
    if root.tag == "score-partwise":
        for part in root.findall("part"):
            body_by_part.setdefault(part.attrib.get("id", ""), []).extend(part.findall("measure"))
    else:
        for measure in root.findall("measure"):
            for part in measure.findall("part"):
                body_by_part.setdefault(part.attrib.get("id", ""), []).append(measure)
    measure_records: list[EvidenceValue] = []
    rest_display_records: list[EvidenceValue] = []
    for part_id, measures in body_by_part.items():
        for ordinal, measure in enumerate(measures, start=1):
            content = (
                measure.find(f"part[@id='{part_id}']") if root.tag == "score-timewise" else measure
            )
            if content is None:
                continue
            notes = content.findall("note")
            measure_records.append(
                (
                    part_id,
                    measure.attrib.get("number", ""),
                    ordinal,
                    _yes_no(measure.attrib.get("implicit")) or False,
                    _yes_no(measure.attrib.get("non-controlling")) or False,
                    len(notes),
                )
            )
            for note in notes:
                rest = note.find("rest")
                if rest is not None:
                    rest_display_records.append(
                        (
                            part_id,
                            _yes_no(rest.attrib.get("measure")),
                            rest.findtext("display-step"),
                            _integer_text(rest.findtext("display-octave")),
                        )
                    )
    defaults = root.find("defaults")
    facts: dict[str, EvidenceValue] = {
        "document_form": root.tag,
        "score_header": (
            root.findtext("work/work-number"),
            root.findtext("work/work-title"),
            root.findtext("movement-number"),
            root.findtext("movement-title"),
            tuple(
                (item.attrib.get("type"), item.text or "")
                for item in root.findall("identification/creator")
            ),
            defaults is not None and defaults.find("concert-score") is not None,
        ),
        "group_records": tuple(group_records),
        "part_records": tuple(definition_records),
        "instrument_records": tuple(instrument_records),
        "measure_records": tuple(measure_records),
        "rest_display_records": tuple(rest_display_records),
    }
    return PartsOracleFacts(tuple(sorted(facts.items())))


@dataclass(frozen=True, slots=True)
class TemporalCoreOracleFacts:
    """Independent exact-time facts for one temporal-core witness."""

    facts: tuple[tuple[str, EvidenceValue], ...]

    def fact_map(self) -> dict[str, EvidenceValue]:
        return dict(self.facts)


def read_measures_facts(data: bytes) -> TemporalCoreOracleFacts:
    """Read measure, voice, and cursor facts independently."""

    facts = _read_temporal_core_facts(data)
    return _selected_temporal_facts(facts, "measure_records", "cursor_records")


def read_attributes_facts(data: bytes) -> TemporalCoreOracleFacts:
    """Read attribute and staff-state facts independently."""

    return _selected_temporal_facts(_read_temporal_core_facts(data), "attribute_records")


def read_notes_facts(data: bytes) -> TemporalCoreOracleFacts:
    """Read note and rest identity facts independently."""

    return _selected_temporal_facts(_read_temporal_core_facts(data), "note_records")


def read_rhythm_facts(data: bytes) -> TemporalCoreOracleFacts:
    """Read written rhythm, beam, and tuplet facts independently."""

    return _selected_temporal_facts(_read_temporal_core_facts(data), "rhythm_records")


def _selected_temporal_facts(
    facts: dict[str, EvidenceValue], *names: str
) -> TemporalCoreOracleFacts:
    return TemporalCoreOracleFacts(tuple((name, facts[name]) for name in names))


def _read_temporal_core_facts(data: bytes) -> dict[str, EvidenceValue]:
    root = element_tree.fromstring(data)
    part_ids = tuple(item.attrib["id"] for item in root.findall("part-list/score-part"))
    bodies: dict[str, list[tuple[element_tree.Element, element_tree.Element]]] = {
        part_id: [] for part_id in part_ids
    }
    if root.tag == "score-partwise":
        for part in root.findall("part"):
            part_id = part.attrib["id"]
            bodies.setdefault(part_id, []).extend(
                (measure, measure) for measure in part.findall("measure")
            )
    else:
        for measure in root.findall("measure"):
            for part in measure.findall("part"):
                bodies.setdefault(part.attrib["id"], []).append((measure, part))

    measure_records: list[EvidenceValue] = []
    cursor_records: list[EvidenceValue] = []
    attribute_records: list[EvidenceValue] = []
    note_records: list[tuple[EvidenceValue, ...]] = []
    rhythm_records: list[EvidenceValue] = []
    for part_id in part_ids:
        score_onset = Fraction(0)
        divisions = 1
        for ordinal, (header, content) in enumerate(bodies.get(part_id, ()), start=1):
            cursor = Fraction(0)
            extent = Fraction(0)
            staves: set[str] = set()
            voices: set[str] = set()
            prior_note_index: int | None = None
            prior_onset: Fraction | None = None
            prior_id: str | None = None
            for order, child in enumerate(content, start=1):
                if child.tag == "attributes":
                    divisions_text = child.findtext("divisions")
                    if divisions_text is not None:
                        divisions = int(divisions_text)
                    staves_text = child.findtext("staves")
                    if staves_text is not None:
                        staves.update(str(number) for number in range(1, int(staves_text) + 1))
                    clefs = tuple(
                        (
                            item.attrib.get("number", "1"),
                            item.findtext("sign") or "",
                            _integer_text(item.findtext("line")),
                            _integer_text(item.findtext("clef-octave-change")),
                        )
                        for item in child.findall("clef")
                    )
                    staves.update(str(item[0]) for item in clefs)
                    keys = tuple(
                        (
                            _integer_text(item.findtext("fifths")),
                            item.findtext("mode"),
                            item.attrib.get("number"),
                        )
                        for item in child.findall("key")
                    )
                    times = tuple(
                        (
                            tuple(item.text or "" for item in time.findall("beats")),
                            tuple(int(item.text or "0") for item in time.findall("beat-type")),
                            time.attrib.get("symbol"),
                            time.attrib.get("number"),
                        )
                        for time in child.findall("time")
                    )
                    transpositions = tuple(
                        (
                            item.attrib.get("number"),
                            _integer_text(item.findtext("diatonic")),
                            _fraction_fact(item.findtext("chromatic") or "0"),
                            int(item.findtext("octave-change") or "0"),
                            _double_above_fact(item),
                        )
                        for item in child.findall("transpose")
                    )
                    staff_details = tuple(
                        (
                            item.attrib.get("number"),
                            item.findtext("staff-type"),
                            _integer_text(item.findtext("staff-lines")),
                            item.attrib.get("show-frets"),
                            _yes_no(item.attrib.get("print-object")),
                        )
                        for item in child.findall("staff-details")
                    )
                    attribute_records.append(
                        (
                            part_id,
                            ordinal,
                            _fraction_fact(cursor),
                            int(divisions_text) if divisions_text is not None else None,
                            int(staves_text) if staves_text is not None else None,
                            clefs,
                            keys,
                            times,
                            transpositions,
                            staff_details,
                            order,
                        )
                    )
                elif child.tag == "note":
                    chord = child.find("chord") is not None
                    grace_element = child.find("grace")
                    grace = grace_element is not None
                    cue = child.find("cue") is not None
                    source_duration_text = child.findtext("duration")
                    source_duration = (
                        int(source_duration_text) if source_duration_text is not None else None
                    )
                    duration = Fraction(source_duration or 0, divisions)
                    onset = prior_onset if chord and prior_onset is not None else cursor
                    event_id = f"{part_id}:m{ordinal}:n{order}"
                    chord_id = prior_id if chord else None
                    if chord and prior_note_index is not None and prior_id is not None:
                        previous = list(note_records[prior_note_index])
                        previous[9] = prior_id
                        note_records[prior_note_index] = tuple(previous)
                    pitch = child.find("pitch")
                    rest = child.find("rest")
                    unpitched = child.find("unpitched")
                    if pitch is not None:
                        kind = "pitched"
                        pitch_fact: EvidenceValue = (
                            pitch.findtext("step") or "",
                            _fraction_fact(pitch.findtext("alter") or "0"),
                            int(pitch.findtext("octave") or "0"),
                        )
                        display_fact: EvidenceValue = None
                    else:
                        kind = "rest" if rest is not None else "unpitched"
                        pitch_fact = None
                        display = rest if rest is not None else unpitched
                        display_fact = (
                            (
                                display.findtext("display-step") or "",
                                _fraction_fact("0"),
                                int(display.findtext("display-octave") or "0"),
                            )
                            if display is not None and display.findtext("display-step") is not None
                            else None
                        )
                    staff = child.findtext("staff") or "1"
                    voice = child.findtext("voice") or "1"
                    staves.add(staff)
                    voices.add(voice)
                    note_records.append(
                        (
                            part_id,
                            ordinal,
                            event_id,
                            kind,
                            _fraction_fact(onset),
                            _fraction_fact(duration),
                            source_duration,
                            staff,
                            voice,
                            chord_id,
                            grace,
                            cue,
                            pitch_fact,
                            display_fact,
                            _yes_no(rest.attrib.get("measure")) if rest is not None else None,
                            order,
                            (
                                _yes_no(grace_element.attrib.get("slash")),
                                _optional_fraction_fact(
                                    Fraction(grace_element.attrib["make-time"]) / divisions
                                    if "make-time" in grace_element.attrib
                                    else None
                                ),
                                _optional_fraction_fact(
                                    grace_element.attrib.get("steal-time-previous")
                                ),
                                _optional_fraction_fact(
                                    grace_element.attrib.get("steal-time-following")
                                ),
                            )
                            if grace_element is not None
                            else None,
                        )
                    )
                    time_mod = child.find("time-modification")
                    tuplets: list[EvidenceValue] = []
                    for notation in child.findall("notations"):
                        for tuplet in notation.findall("tuplet"):
                            tuplets.append(
                                (
                                    tuplet.attrib.get("number", "1"),
                                    tuplet.attrib.get("type", ""),
                                    _yes_no(tuplet.attrib.get("bracket")),
                                    tuplet.attrib.get("placement"),
                                    tuplet.attrib.get("show-number"),
                                    tuplet.attrib.get("show-type"),
                                    tuplet.attrib.get("line-shape"),
                                    _tuplet_portion_fact(tuplet.find("tuplet-actual")),
                                    _tuplet_portion_fact(tuplet.find("tuplet-normal")),
                                )
                            )
                    rhythm_records.append(
                        (
                            event_id,
                            child.findtext("type"),
                            len(child.findall("dot")),
                            (
                                int(time_mod.findtext("actual-notes") or "0"),
                                int(time_mod.findtext("normal-notes") or "0"),
                            )
                            if time_mod is not None
                            else None,
                            time_mod.findtext("normal-type") if time_mod is not None else None,
                            len(time_mod.findall("normal-dot")) if time_mod is not None else 0,
                            tuple(
                                (
                                    int(beam.attrib.get("number", "1")),
                                    beam.text or "",
                                    _yes_no(beam.attrib.get("repeater")),
                                    beam.attrib.get("fan"),
                                )
                                for beam in child.findall("beam")
                            ),
                            tuple(tuplets),
                        )
                    )
                    if not chord:
                        cursor += duration
                    extent = max(extent, cursor, onset + duration)
                    prior_note_index = len(note_records) - 1
                    prior_onset = onset
                    prior_id = event_id
                elif child.tag in {"backup", "forward"}:
                    raw_duration = int(child.findtext("duration") or "0")
                    before = cursor
                    after = cursor + Fraction(raw_duration, divisions) * (
                        -1 if child.tag == "backup" else 1
                    )
                    recovered = child.tag == "backup" and after < 0 and cursor > 0
                    cursor = Fraction(0) if recovered else after
                    cursor_records.append(
                        (
                            part_id,
                            ordinal,
                            child.tag,
                            _fraction_fact(before),
                            _fraction_fact(cursor),
                            raw_duration,
                            child.findtext("staff"),
                            child.findtext("voice"),
                            order,
                            recovered,
                        )
                    )
                    extent = max(extent, cursor)
                    prior_note_index = None
                    prior_onset = None
                    prior_id = None
            measure_records.append(
                (
                    part_id,
                    header.attrib.get("number", str(ordinal)),
                    ordinal,
                    _yes_no(header.attrib.get("implicit")) or False,
                    _yes_no(header.attrib.get("non-controlling")) or False,
                    _fraction_fact(extent),
                    tuple(sorted(staves)),
                    tuple(sorted(voices)),
                    _fraction_fact(score_onset),
                )
            )
            score_onset += extent
    return {
        "measure_records": tuple(measure_records),
        "cursor_records": tuple(cursor_records),
        "attribute_records": tuple(attribute_records),
        "note_records": tuple(note_records),
        "rhythm_records": tuple(rhythm_records),
    }


def _tuplet_portion_fact(element: element_tree.Element | None) -> EvidenceValue:
    if element is None:
        return None
    return (
        _integer_text(element.findtext("tuplet-number")),
        element.findtext("tuplet-type"),
        len(element.findall("tuplet-dot")),
    )


@dataclass(frozen=True, slots=True)
class AttachmentOracleFacts:
    """Independent source facts for note-attached and time-attached notation."""

    facts: tuple[tuple[str, EvidenceValue], ...]

    def fact_map(self) -> dict[str, EvidenceValue]:
        return dict(self.facts)


@dataclass(frozen=True, slots=True)
class OrderedSemanticOracleFacts:
    """Independent ordered facts for barlines, directions, dynamics, or lyrics."""

    facts: tuple[tuple[str, EvidenceValue], ...]

    def fact_map(self) -> dict[str, EvidenceValue]:
        return dict(self.facts)


def read_barlines_facts(data: bytes) -> OrderedSemanticOracleFacts:
    """Read exact barline and navigation facts without production mapping."""

    facts = _read_ordered_semantic_facts(data)
    return OrderedSemanticOracleFacts((("barline_records", facts["barline_records"]),))


def read_directions_facts(data: bytes) -> OrderedSemanticOracleFacts:
    """Read ordered text and tempo direction facts without production mapping."""

    facts = _read_ordered_semantic_facts(data)
    return OrderedSemanticOracleFacts((("direction_records", facts["direction_records"]),))


def read_dynamics_facts(data: bytes) -> OrderedSemanticOracleFacts:
    """Read direction- and event-attached dynamic facts independently."""

    facts = _read_ordered_semantic_facts(data)
    return OrderedSemanticOracleFacts(
        (
            ("dynamic_direction_records", facts["dynamic_direction_records"]),
            ("dynamic_event_records", facts["dynamic_event_records"]),
        )
    )


def read_lyrics_facts(data: bytes) -> OrderedSemanticOracleFacts:
    """Read ordered lyric text, elision, extension, and vocal-state facts."""

    facts = _read_ordered_semantic_facts(data)
    return OrderedSemanticOracleFacts((("lyric_records", facts["lyric_records"]),))


def read_harmony_facts(data: bytes) -> OrderedSemanticOracleFacts:
    """Read harmony chord and fret-diagram facts independently."""

    root = element_tree.fromstring(data)
    records: list[EvidenceValue] = []
    for part in root.findall("part"):
        part_id = part.attrib["id"]
        divisions = 1
        score_onset = Fraction(0)
        for ordinal, measure in enumerate(part.findall("measure"), start=1):
            cursor = Fraction(0)
            for source_order, child in enumerate(measure, start=1):
                if child.tag == "attributes":
                    divisions = int(child.findtext("divisions") or divisions)
                elif child.tag == "harmony":
                    records.append(
                        _source_harmony_fact(
                            child,
                            part_id=part_id,
                            ordinal=ordinal,
                            onset=cursor,
                            score_onset=score_onset,
                            divisions=divisions,
                            source_order=source_order,
                        )
                    )
                elif child.tag == "note" and child.find("chord") is None:
                    cursor += Fraction(int(child.findtext("duration") or "0"), divisions)
            score_onset += cursor
    return OrderedSemanticOracleFacts((("harmony_records", tuple(records)),))


def read_links_facts(data: bytes) -> OrderedSemanticOracleFacts:
    """Read score links, bookmarks, and grouping facts independently."""

    root = element_tree.fromstring(data)
    records: list[EvidenceValue] = []
    for part in root.findall("part"):
        part_id = part.attrib["id"]
        for ordinal, measure in enumerate(part.findall("measure"), start=1):
            links = tuple(_source_link_fact(item) for item in measure.findall("link"))
            bookmarks = tuple(
                (
                    item.attrib.get("id", ""),
                    item.attrib.get("name"),
                    item.attrib.get("element"),
                    _integer_text(item.attrib.get("position")),
                )
                for item in measure.findall("bookmark")
            )
            groupings = tuple(
                (
                    item.attrib.get("type", ""),
                    item.attrib.get("number", "1"),
                    item.attrib.get("member-of"),
                    tuple(
                        (feature.text or "", feature.attrib.get("type"))
                        for feature in item.findall("feature")
                    ),
                )
                for item in measure.findall("grouping")
            )
            records.append((part_id, ordinal, links, bookmarks, groupings))
    return OrderedSemanticOracleFacts((("link_grouping_records", tuple(records)),))


def read_auxiliary_facts(data: bytes) -> OrderedSemanticOracleFacts:
    """Read score-opus, opus-root, and sounds-root package facts independently."""

    root = element_tree.fromstring(data)
    version = _public_musicxml_version(data)
    if root.tag == "opus":
        record: EvidenceValue = (
            "opus",
            version,
            root.findtext("title"),
            tuple(_source_opus_item(child) for child in root if child.tag != "title"),
        )
    elif root.tag == "sounds":
        record = (
            "sounds",
            version,
            tuple(
                (
                    item.attrib.get("id", ""),
                    _yes_no(item.attrib.get("primary")),
                    tuple(
                        (
                            child.tag,
                            child.text or "",
                            _yes_no(child.attrib.get("primary")),
                            child.attrib.get("number"),
                        )
                        for child in item
                    ),
                )
                for item in root.findall("sound")
            ),
        )
    else:
        work = root.find("work")
        opus = work.find("opus") if work is not None else None
        record = (
            "score-opus",
            version,
            _source_link_fact(opus) if opus is not None else None,
        )
    return OrderedSemanticOracleFacts((("auxiliary_record", record),))


def read_playback_facts(data: bytes) -> OrderedSemanticOracleFacts:
    """Read score-part MIDI and positioned sound facts independently."""

    root = element_tree.fromstring(data)
    part_playback: list[EvidenceValue] = []
    part_list = root.find("part-list")
    if part_list is not None:
        for part in part_list.findall("score-part"):
            part_playback.append(
                (
                    part.attrib.get("id", ""),
                    tuple(
                        (
                            item.attrib.get("id"),
                            _integer_text(item.attrib.get("port")),
                            item.text or "",
                        )
                        for item in part.findall("midi-device")
                    ),
                    tuple(_source_midi_fact(item) for item in part.findall("midi-instrument")),
                )
            )
    sounds: list[EvidenceValue] = []
    for part in root.findall("part"):
        part_id = part.attrib["id"]
        divisions = 1
        score_onset = Fraction(0)
        for ordinal, measure in enumerate(part.findall("measure"), start=1):
            cursor = Fraction(0)
            for source_order, child in enumerate(measure, start=1):
                if child.tag == "attributes":
                    divisions = int(child.findtext("divisions") or divisions)
                elif child.tag == "sound":
                    offset = Fraction(child.findtext("offset") or "0") / divisions
                    sounds.append(
                        (
                            part_id,
                            ordinal,
                            _fraction_fact(cursor + offset),
                            _fraction_fact(score_onset + cursor + offset),
                            source_order,
                            _optional_fraction_fact(child.attrib.get("tempo")),
                            _optional_fraction_fact(child.attrib.get("dynamics")),
                            _yes_no(child.attrib.get("dacapo")),
                            _yes_no(child.attrib.get("pizzicato")),
                        )
                    )
                elif child.tag == "note" and child.find("chord") is None:
                    cursor += Fraction(int(child.findtext("duration") or "0"), divisions)
            score_onset += cursor
    return OrderedSemanticOracleFacts(
        (
            ("part_playback_records", tuple(part_playback)),
            ("sound_records", tuple(sounds)),
        )
    )


def read_layout_facts(data: bytes) -> OrderedSemanticOracleFacts:
    """Read score and measure layout facts independently."""

    root = element_tree.fromstring(data)
    defaults = root.find("defaults")
    score_layout: EvidenceValue = None
    if defaults is not None:
        scaling = defaults.find("scaling")
        appearance = defaults.find("appearance")
        score_layout = (
            (
                _fraction_fact(scaling.findtext("millimeters") or "0"),
                _fraction_fact(scaling.findtext("tenths") or "0"),
            )
            if scaling is not None
            else None,
            _source_page_layout_fact(defaults.find("page-layout")),
            _source_system_layout_fact(defaults.find("system-layout")),
            tuple(_source_staff_layout_fact(item) for item in defaults.findall("staff-layout")),
            tuple(
                (
                    item.tag,
                    item.attrib.get("type", ""),
                    _fraction_fact(item.text or "0") if item.tag != "other-appearance" else None,
                    item.text or "" if item.tag == "other-appearance" else None,
                )
                for item in (tuple(appearance) if appearance is not None else ())
            ),
        )
    measures: list[EvidenceValue] = []
    for part in root.findall("part"):
        part_id = part.attrib.get("id", "")
        for ordinal, measure in enumerate(part.findall("measure"), start=1):
            print_element = measure.find("print")
            width = measure.attrib.get("width")
            if print_element is None and width is None:
                continue
            measure_layout = (
                print_element.find("measure-layout") if print_element is not None else None
            )
            measures.append(
                (
                    part_id,
                    ordinal,
                    _optional_fraction_fact(width),
                    _yes_no(print_element.attrib.get("new-page"))
                    if print_element is not None
                    else None,
                    _yes_no(print_element.attrib.get("new-system"))
                    if print_element is not None
                    else None,
                    print_element.attrib.get("page-number") if print_element is not None else None,
                    _integer_text(print_element.attrib.get("blank-page"))
                    if print_element is not None
                    else None,
                    _source_page_layout_fact(print_element.find("page-layout"))
                    if print_element is not None
                    else None,
                    _source_system_layout_fact(print_element.find("system-layout"))
                    if print_element is not None
                    else None,
                    tuple(
                        _source_staff_layout_fact(item)
                        for item in print_element.findall("staff-layout")
                    )
                    if print_element is not None
                    else (),
                    _optional_fraction_fact(measure_layout.findtext("measure-distance"))
                    if measure_layout is not None
                    else None,
                    print_element.findtext("measure-numbering")
                    if print_element is not None
                    else None,
                    _optional_fraction_fact(print_element.attrib.get("staff-spacing"))
                    if print_element is not None
                    else None,
                )
            )
    return OrderedSemanticOracleFacts(
        (
            ("score_layout_record", score_layout),
            ("measure_layout_records", tuple(measures)),
        )
    )


def read_presentation_facts(data: bytes) -> OrderedSemanticOracleFacts:
    """Read shared presentation values from ordered words independently."""

    root = element_tree.fromstring(data)
    records = tuple(
        (item.tag, item.text or "", _source_presentation_fact(item)) for item in root.iter("words")
    )
    return OrderedSemanticOracleFacts((("presentation_records", records),))


def _source_page_layout_fact(element: element_tree.Element | None) -> EvidenceValue:
    if element is None:
        return None
    return (
        _optional_fraction_fact(element.findtext("page-height")),
        _optional_fraction_fact(element.findtext("page-width")),
        tuple(
            (
                item.attrib.get("type"),
                _fraction_fact(item.findtext("left-margin") or "0"),
                _fraction_fact(item.findtext("right-margin") or "0"),
                _optional_fraction_fact(item.findtext("top-margin")),
                _optional_fraction_fact(item.findtext("bottom-margin")),
            )
            for item in element.findall("page-margins")
        ),
    )


def _source_system_layout_fact(element: element_tree.Element | None) -> EvidenceValue:
    if element is None:
        return None
    margins = element.find("system-margins")
    margin_fact: EvidenceValue = None
    if margins is not None:
        margin_fact = (
            None,
            _fraction_fact(margins.findtext("left-margin") or "0"),
            _fraction_fact(margins.findtext("right-margin") or "0"),
            None,
            None,
        )
    return (
        margin_fact,
        _optional_fraction_fact(element.findtext("system-distance")),
        _optional_fraction_fact(element.findtext("top-system-distance")),
    )


def _source_staff_layout_fact(element: element_tree.Element) -> EvidenceValue:
    return (
        element.attrib.get("number"),
        _optional_fraction_fact(element.findtext("staff-distance")),
    )


def _source_presentation_fact(element: element_tree.Element) -> EvidenceValue:
    return (
        _optional_fraction_fact(element.attrib.get("default-x")),
        _optional_fraction_fact(element.attrib.get("default-y")),
        _optional_fraction_fact(element.attrib.get("relative-x")),
        _optional_fraction_fact(element.attrib.get("relative-y")),
        element.attrib.get("color"),
        element.attrib.get("font-family"),
        element.attrib.get("font-style"),
        _source_presentation_number(element.attrib.get("font-size")),
        element.attrib.get("font-weight"),
        element.attrib.get("justify"),
        element.attrib.get("halign"),
        element.attrib.get("valign"),
        element.attrib.get("enclosure"),
        _source_presentation_number(element.attrib.get("letter-spacing")),
        _source_presentation_number(element.attrib.get("line-height")),
        _integer_text(element.attrib.get("underline")),
        _integer_text(element.attrib.get("overline")),
        _integer_text(element.attrib.get("line-through")),
        _optional_fraction_fact(element.attrib.get("rotation")),
        element.attrib.get("dir"),
        element.attrib.get(_XML_LANG),
        element.attrib.get(_XML_SPACE),
    )


def _source_presentation_number(value: str | None) -> EvidenceValue:
    if value is None:
        return None
    keywords = {
        "normal",
        "xx-small",
        "x-small",
        "small",
        "medium",
        "large",
        "x-large",
        "xx-large",
    }
    return (None, value) if value in keywords else (_fraction_fact(value), None)


def _source_harmony_fact(
    element: element_tree.Element,
    *,
    part_id: str,
    ordinal: int,
    onset: Fraction,
    score_onset: Fraction,
    divisions: int,
    source_order: int,
) -> EvidenceValue:
    root = element.find("root")
    kind_element = element.find("kind")
    bass = element.find("bass")
    offset = Fraction(element.findtext("offset") or "0") / divisions
    degrees = tuple(_source_harmony_degree_fact(item) for item in element.findall("degree"))
    chord = (
        root.findtext("root-step") if root is not None else None,
        _fraction_fact(root.findtext("root-alter") or "0")
        if root is not None
        else _fraction_fact("0"),
        None,
        element.findtext("function"),
        kind_element.text or "" if kind_element is not None else "",
        kind_element.attrib.get("text") if kind_element is not None else None,
        _yes_no(kind_element.attrib.get("use-symbols")) if kind_element is not None else None,
        _yes_no(kind_element.attrib.get("stack-degrees")) if kind_element is not None else None,
        _yes_no(kind_element.attrib.get("parentheses-degrees"))
        if kind_element is not None
        else None,
        _yes_no(kind_element.attrib.get("bracket-degrees")) if kind_element is not None else None,
        _integer_text(element.findtext("inversion")),
        (
            bass.findtext("bass-step") or "",
            _fraction_fact(bass.findtext("bass-alter") or "0"),
        )
        if bass is not None
        else None,
        degrees,
    )
    frame = element.find("frame")
    frame_fact: EvidenceValue = None
    if frame is not None:
        first = frame.find("first-fret")
        frame_fact = (
            int(frame.findtext("frame-strings") or "0"),
            int(frame.findtext("frame-frets") or "0"),
            _integer_text(first.text) if first is not None else None,
            first.attrib.get("text") if first is not None else None,
            first.attrib.get("location") if first is not None else None,
            tuple(_source_frame_note_fact(item) for item in frame.findall("frame-note")),
            frame.attrib.get("unplayed"),
        )
    return (
        part_id,
        ordinal,
        _fraction_fact(onset + offset),
        _fraction_fact(score_onset + onset + offset),
        element.findtext("staff") or "1",
        root.findtext("root-step") if root is not None else None,
        _fraction_fact(root.findtext("root-alter") or "0")
        if root is not None
        else _fraction_fact("0"),
        kind_element.text or "" if kind_element is not None else "",
        kind_element.attrib.get("text") if kind_element is not None else None,
        source_order,
        (chord,),
        frame_fact,
        element.attrib.get("type"),
        _yes_no(element.attrib.get("print-object")),
        _yes_no(element.attrib.get("print-frame")),
        element.attrib.get("arrangement"),
        element.attrib.get("id"),
        element.attrib.get("system"),
    )


def _source_harmony_degree_fact(element: element_tree.Element) -> EvidenceValue:
    value = element.find("degree-value")
    degree_type = element.find("degree-type")
    alter = element.find("degree-alter")
    return (
        int(element.findtext("degree-value") or "0"),
        _fraction_fact(element.findtext("degree-alter") or "0"),
        element.findtext("degree-type") or "",
        _yes_no(element.attrib.get("print-object")),
        value.attrib.get("symbol") if value is not None else None,
        value.attrib.get("text") if value is not None else None,
        degree_type.attrib.get("text") if degree_type is not None else None,
        _yes_no(alter.attrib.get("plus-minus")) if alter is not None else None,
    )


def _source_frame_note_fact(element: element_tree.Element) -> EvidenceValue:
    barre = element.find("barre")
    return (
        int(element.findtext("string") or "0"),
        int(element.findtext("fret") or "0"),
        element.findtext("fingering"),
        barre.attrib.get("type") if barre is not None else None,
    )


def _source_link_fact(element: element_tree.Element) -> EvidenceValue:
    return (
        element.attrib.get(f"{_XLINK}href", ""),
        element.attrib.get(f"{_XLINK}type"),
        element.attrib.get(f"{_XLINK}role"),
        element.attrib.get(f"{_XLINK}title"),
        element.attrib.get(f"{_XLINK}show"),
        element.attrib.get(f"{_XLINK}actuate"),
        element.attrib.get("name"),
        element.attrib.get("element"),
        _integer_text(element.attrib.get("position")),
    )


def _source_opus_item(element: element_tree.Element) -> EvidenceValue:
    if element.tag == "opus":
        return (
            "opus",
            None,
            None,
            element.findtext("title"),
            tuple(_source_opus_item(child) for child in element if child.tag != "title"),
        )
    return (
        element.tag,
        _source_link_fact(element),
        _yes_no(element.attrib.get("new-page")) if element.tag == "score" else None,
        None,
        (),
    )


def _source_midi_fact(element: element_tree.Element) -> EvidenceValue:
    return (
        element.attrib.get("id", ""),
        _integer_text(element.findtext("midi-channel")),
        element.findtext("midi-name"),
        _integer_text(element.findtext("midi-bank")),
        _integer_text(element.findtext("midi-program")),
        _integer_text(element.findtext("midi-unpitched")),
        _optional_fraction_fact(element.findtext("volume")),
        _optional_fraction_fact(element.findtext("pan")),
        _optional_fraction_fact(element.findtext("elevation")),
    )


def _public_musicxml_version(data: bytes) -> str:
    marker = b"MusicXML "
    start = data.find(marker)
    if start < 0:
        raise ValueError("independent oracle expected MusicXML public identifier")
    value = data[start + len(marker) :].split(b" ", 1)[0].decode("ascii")
    return "4.1-draft" if value == "4.1" else value


def _read_ordered_semantic_facts(data: bytes) -> dict[str, EvidenceValue]:
    root = element_tree.fromstring(data)
    barlines: list[EvidenceValue] = []
    directions: list[EvidenceValue] = []
    dynamic_events: list[EvidenceValue] = []
    lyrics: list[EvidenceValue] = []
    for part in root.findall("part"):
        part_id = part.attrib["id"]
        divisions = 1
        score_onset = Fraction(0)
        for ordinal, measure in enumerate(part.findall("measure"), start=1):
            cursor = Fraction(0)
            measure_id = f"{part_id}:m{ordinal}"
            for source_order, child in enumerate(measure, start=1):
                if child.tag == "attributes":
                    value = child.findtext("divisions")
                    if value is not None:
                        divisions = int(value)
                elif child.tag == "barline":
                    barlines.append(
                        _source_barline_fact(
                            child,
                            part_id=part_id,
                            ordinal=ordinal,
                            onset=cursor,
                            source_order=source_order,
                        )
                    )
                elif child.tag == "direction":
                    directions.extend(
                        _source_direction_facts(
                            child,
                            part_id=part_id,
                            measure_id=measure_id,
                            onset=cursor,
                            score_onset=score_onset,
                            divisions=divisions,
                            source_order=source_order,
                        )
                    )
                elif child.tag == "note":
                    event_id = f"{part_id}:m{ordinal}:n{source_order}"
                    dynamic_events.extend(_source_dynamic_event_facts(child, event_id=event_id))
                    lyrics.extend(
                        _source_lyric_facts(
                            child,
                            part_id=part_id,
                            measure_id=measure_id,
                            event_id=event_id,
                            score_onset=score_onset + cursor,
                        )
                    )
                    if child.find("chord") is None:
                        cursor += Fraction(int(child.findtext("duration") or "0"), divisions)
            score_onset += cursor
    dynamic_directions = tuple(
        record for record in directions if isinstance(record, tuple) and record[6] == "dynamic"
    )
    non_dynamic_directions = tuple(
        record for record in directions if isinstance(record, tuple) and record[6] != "dynamic"
    )
    return {
        "barline_records": tuple(barlines),
        "direction_records": non_dynamic_directions,
        "dynamic_direction_records": dynamic_directions,
        "dynamic_event_records": tuple(dynamic_events),
        "lyric_records": tuple(lyrics),
    }


def _source_barline_fact(
    element: element_tree.Element,
    *,
    part_id: str,
    ordinal: int,
    onset: Fraction,
    source_order: int,
) -> EvidenceValue:
    repeat = element.find("repeat")
    ending = element.find("ending")
    fermatas = tuple(
        (item.text, item.attrib.get("type"), item.attrib.get("id"))
        for item in element.findall("fermata")
    )
    navigation: list[EvidenceValue] = []
    for kind in ("segno", "coda"):
        token = element.attrib.get(kind)
        if token is not None:
            navigation.append((kind, token, None, None))
        navigation.extend(
            (kind, item.text, item.attrib.get("id"), item.attrib.get("smufl"))
            for item in element.findall(kind)
        )
    return (
        part_id,
        ordinal,
        _fraction_fact(onset),
        element.attrib.get("location"),
        element.findtext("bar-style"),
        repeat.attrib.get("direction") if repeat is not None else None,
        repeat.attrib.get("times") if repeat is not None else None,
        ending.attrib.get("number") if ending is not None else None,
        ending.attrib.get("type") if ending is not None else None,
        source_order,
        fermatas,
        tuple(navigation),
        repeat.attrib.get("winged") if repeat is not None else None,
        _yes_no(repeat.attrib.get("after-jump")) if repeat is not None else None,
        _present_element_text(ending),
        _yes_no(ending.attrib.get("print-object")) if ending is not None else None,
        ending.attrib.get("system") if ending is not None else None,
        _optional_fraction_fact(element.attrib.get("divisions")),
        element.attrib.get("id"),
    )


def _source_direction_facts(
    element: element_tree.Element,
    *,
    part_id: str,
    measure_id: str,
    onset: Fraction,
    score_onset: Fraction,
    divisions: int,
    source_order: int,
) -> list[EvidenceValue]:
    offset = Fraction(element.findtext("offset") or "0") / divisions
    location = onset + offset
    staff = element.findtext("staff") or "1"
    voice = element.findtext("voice")
    placement = element.attrib.get("placement")
    directive = _yes_no(element.attrib.get("directive"))
    records: list[EvidenceValue] = []
    component_order = 0
    for direction_type in element.findall("direction-type"):
        for item in direction_type:
            kind = item.tag
            if kind == "dynamics":
                group_id = item.attrib.get("id")
                for dynamic in item:
                    component_order += 1
                    records.append(
                        _source_direction_record(
                            part_id,
                            measure_id,
                            location,
                            score_onset + location,
                            staff,
                            voice,
                            "dynamic",
                            dynamic.text or dynamic.tag,
                            placement,
                            source_order,
                            component_order,
                            group_id=group_id,
                            smufl=dynamic.attrib.get("smufl"),
                            direction=element,
                            direction_type=direction_type,
                            source_id=None,
                            print_object=None,
                            metronome=None,
                            directive=directive,
                        )
                    )
                continue
            component_order += 1
            metronome = _source_metronome_fact(item) if kind == "metronome" else None
            value = item.text or ""
            if metronome is not None:
                value = item.findtext("per-minute") or item.findtext("metronome-relation") or ""
            records.append(
                _source_direction_record(
                    part_id,
                    measure_id,
                    location,
                    score_onset + location,
                    staff,
                    voice,
                    kind,
                    value,
                    placement,
                    source_order,
                    component_order,
                    group_id=None,
                    smufl=item.attrib.get("smufl")
                    if kind in {"segno", "coda", "other-direction"}
                    else None,
                    direction=element,
                    direction_type=direction_type,
                    source_id=item.attrib.get("id"),
                    print_object=(
                        _yes_no(item.attrib.get("print-object"))
                        if kind in {"other-direction", "metronome"}
                        else None
                    ),
                    metronome=metronome,
                    directive=directive,
                )
            )
    return records


def _source_direction_record(
    part_id: str,
    measure_id: str,
    onset: Fraction,
    score_onset: Fraction,
    staff: str | None,
    voice: str | None,
    family: str,
    value: str,
    placement: str | None,
    source_order: int,
    component_order: int,
    *,
    group_id: str | None,
    smufl: str | None,
    direction: element_tree.Element,
    direction_type: element_tree.Element,
    source_id: str | None,
    print_object: bool | None,
    metronome: EvidenceValue,
    directive: bool | None,
) -> EvidenceValue:
    return (
        part_id,
        measure_id,
        _fraction_fact(onset),
        _fraction_fact(score_onset),
        staff,
        voice,
        family,
        value,
        placement,
        source_order,
        component_order,
        group_id,
        smufl,
        direction.attrib.get("id"),
        direction_type.attrib.get("id"),
        source_id,
        print_object,
        direction.attrib.get("system"),
        metronome,
        directive,
    )


def _source_metronome_fact(element: element_tree.Element) -> EvidenceValue:
    beats: list[tuple[str, int, bool]] = []
    for child in element:
        if child.tag == "beat-unit":
            beats.append((child.text or "", 0, False))
        elif child.tag == "beat-unit-dot" and beats:
            previous = beats[-1]
            beats[-1] = (previous[0], previous[1] + 1, previous[2])
    return (
        tuple(beats),
        element.findtext("per-minute"),
        element.find("metronome-arrows") is not None,
        (),
        element.findtext("metronome-relation"),
        _yes_no(element.attrib.get("parentheses")),
    )


def _source_dynamic_event_facts(
    note: element_tree.Element, *, event_id: str
) -> list[EvidenceValue]:
    records: list[EvidenceValue] = []
    for notations in note.findall("notations"):
        for group in notations.findall("dynamics"):
            placement = group.attrib.get("placement")
            group_id = group.attrib.get("id")
            for item in group:
                records.append(
                    (
                        event_id,
                        item.tag,
                        item.text,
                        len(records) + 1,
                        group_id,
                        placement or item.attrib.get("placement"),
                        item.attrib.get("smufl"),
                    )
                )
    return records


def _source_lyric_facts(
    note: element_tree.Element,
    *,
    part_id: str,
    measure_id: str,
    event_id: str,
    score_onset: Fraction,
) -> list[EvidenceValue]:
    records: list[EvidenceValue] = []
    staff = note.findtext("staff") or "1"
    voice = note.findtext("voice") or "1"
    for source_order, lyric in enumerate(note.findall("lyric"), start=1):
        segments: list[tuple[str, str | None, str | None, str | None]] = []
        pending_syllabic: str | None = None
        pending_elision: str | None = None
        pending_smufl: str | None = None
        extend_present = False
        extend: str | None = None
        laughing = humming = end_line = end_paragraph = False
        for child in lyric:
            if child.tag == "syllabic":
                pending_syllabic = child.text
            elif child.tag == "elision":
                pending_elision = child.text or ""
                pending_smufl = child.attrib.get("smufl")
            elif child.tag == "text":
                segments.append(
                    (child.text or "", pending_syllabic, pending_elision, pending_smufl)
                )
                pending_syllabic = pending_elision = pending_smufl = None
            elif child.tag == "extend":
                extend_present = True
                extend = child.attrib.get("type")
            elif child.tag == "laughing":
                laughing = True
            elif child.tag == "humming":
                humming = True
            elif child.tag == "end-line":
                end_line = True
            elif child.tag == "end-paragraph":
                end_paragraph = True
        text = "".join(f"{segment[2] or ''}{segment[0]}" for segment in segments)
        records.append(
            (
                part_id,
                measure_id,
                event_id,
                staff,
                voice,
                _fraction_fact(score_onset),
                lyric.attrib.get("number"),
                lyric.attrib.get("name"),
                segments[0][1] if segments else None,
                text,
                source_order,
                tuple(segments),
                extend_present,
                extend,
                laughing,
                humming,
                end_line,
                end_paragraph,
                _yes_no(lyric.attrib.get("print-object")),
                lyric.attrib.get("time-only"),
                lyric.attrib.get("id"),
                lyric.attrib.get("placement"),
            )
        )
    return records


def _present_element_text(element: element_tree.Element | None) -> str | None:
    if element is None:
        return None
    return element.text if element.text is not None else ""


def read_ties_facts(data: bytes) -> AttachmentOracleFacts:
    facts = _read_attachment_facts(data)
    return _selected_attachment_facts(
        facts,
        "tie_span_records",
        "tie_topology",
        "time_span_records",
        "time_span_topology",
    )


def read_noteheads_facts(data: bytes) -> AttachmentOracleFacts:
    facts = _read_attachment_facts(data)
    return _selected_attachment_facts(
        facts,
        "notehead_records",
        "notation_mark_records",
        "notation_span_records",
        "notation_topology",
    )


def read_articulations_facts(data: bytes) -> AttachmentOracleFacts:
    facts = _read_attachment_facts(data)
    return _selected_attachment_facts(
        facts,
        "articulation_mark_records",
        "ornament_mark_records",
        "ornament_span_records",
        "ornament_topology",
    )


def read_technical_facts(data: bytes) -> AttachmentOracleFacts:
    facts = _read_attachment_facts(data)
    return _selected_attachment_facts(
        facts,
        "technical_mark_records",
        "technical_span_records",
        "technical_topology",
    )


def _selected_attachment_facts(
    facts: dict[str, EvidenceValue], *names: str
) -> AttachmentOracleFacts:
    return AttachmentOracleFacts(tuple((name, facts[name]) for name in names))


def _read_attachment_facts(data: bytes) -> dict[str, EvidenceValue]:
    root = element_tree.fromstring(data)
    part = root.find("part")
    if part is None:
        raise ValueError("attachment oracle expected a partwise score")
    part_id = part.attrib["id"]
    noteheads: list[tuple[EvidenceValue, ...]] = []
    marks: list[tuple[EvidenceValue, ...]] = []
    spans: list[tuple[EvidenceValue, ...]] = []
    time_spans: list[tuple[EvidenceValue, ...]] = []
    divisions = 1
    score_onset = Fraction(0)
    for ordinal, measure in enumerate(part.findall("measure"), start=1):
        cursor = Fraction(0)
        for source_order, child in enumerate(measure, start=1):
            if child.tag == "attributes":
                divisions = int(child.findtext("divisions") or divisions)
            elif child.tag == "direction":
                component_order = 0
                for direction_type in child.findall("direction-type"):
                    for item in direction_type:
                        if item.tag not in {"wedge", "dashes", "bracket", "pedal", "octave-shift"}:
                            continue
                        component_order += 1
                        source_type = item.attrib.get("type", "")
                        starts = {
                            "wedge": {"crescendo", "diminuendo"},
                            "dashes": {"start"},
                            "bracket": {"start"},
                            "pedal": {"start", "sostenuto"},
                            "octave-shift": {"up", "down"},
                        }[item.tag]
                        continuations = (
                            {"continue", "change", "discontinue", "resume"}
                            if item.tag == "pedal"
                            else {"continue"}
                        )
                        action = (
                            "start"
                            if source_type in starts
                            else "continue"
                            if source_type in continuations
                            else "stop"
                        )
                        time_spans.append(
                            (
                                item.tag,
                                item.attrib.get("number", "1"),
                                action,
                                source_type if action == "start" else None,
                                _fraction_fact(score_onset + cursor),
                                source_order,
                                component_order,
                                item.attrib.get("line-type"),
                                item.attrib.get("line-end"),
                                _integer_text(item.attrib.get("size"))
                                if item.tag == "octave-shift"
                                else None,
                                _yes_no(item.attrib.get("line")) if item.tag == "pedal" else None,
                            )
                        )
            elif child.tag == "note":
                event_id = f"{part_id}:m{ordinal}:n{source_order}"
                _read_notehead_fact(child, event_id, noteheads)
                note_marks, note_spans = _read_note_attachment_facts(child, event_id)
                marks.extend(note_marks)
                spans.extend(note_spans)
                duration = int(child.findtext("duration") or "0")
                if child.find("chord") is None:
                    cursor += Fraction(duration, divisions)
        score_onset += cursor

    def mark_family(family: str) -> tuple[EvidenceValue, ...]:
        return tuple(item for item in marks if item[1] == family)

    def span_family(kinds: set[str]) -> tuple[EvidenceValue, ...]:
        return tuple(item for item in spans if str(item[1]) in kinds)

    tie_spans = span_family({"sounding-tie", "notated-tie", "slur"})
    notation_spans = span_family({"glissando", "slide", "other-notation"})
    ornament_spans = span_family({"wavy-line", "tremolo"})
    technical_spans = span_family({"hammer-on", "pull-off"})
    return {
        "notehead_records": tuple(noteheads),
        "notation_mark_records": mark_family("notation"),
        "articulation_mark_records": mark_family("articulation"),
        "ornament_mark_records": mark_family("ornament"),
        "technical_mark_records": mark_family("technical"),
        "tie_span_records": tie_spans,
        "notation_span_records": notation_spans,
        "ornament_span_records": ornament_spans,
        "technical_span_records": technical_spans,
        "tie_topology": _span_topology(tie_spans),
        "notation_topology": _span_topology(notation_spans),
        "ornament_topology": _span_topology(ornament_spans),
        "technical_topology": _span_topology(technical_spans),
        "time_span_records": tuple(time_spans),
        "time_span_topology": _time_span_topology(tuple(time_spans)),
    }


def _read_notehead_fact(
    note: element_tree.Element,
    event_id: str,
    records: list[tuple[EvidenceValue, ...]],
) -> None:
    notehead = note.find("notehead")
    text = note.find("notehead-text")
    if notehead is None and text is None:
        return
    segments = tuple((item.tag, item.text or "") for item in text) if text is not None else ()
    records.append(
        (
            event_id,
            notehead.text if notehead is not None else None,
            _yes_no(notehead.attrib.get("filled")) if notehead is not None else None,
            _yes_no(notehead.attrib.get("parentheses")) if notehead is not None else None,
            notehead.attrib.get("smufl") if notehead is not None else None,
            segments,
        )
    )


def _read_note_attachment_facts(
    note: element_tree.Element, event_id: str
) -> tuple[list[tuple[EvidenceValue, ...]], list[tuple[EvidenceValue, ...]]]:
    marks: list[tuple[EvidenceValue, ...]] = []
    spans: list[tuple[EvidenceValue, ...]] = []
    for tie in note.findall("tie"):
        spans.append(_source_span_fact(event_id, "sounding-tie", tie, len(spans) + 1, "1"))
    notations_elements = note.findall("notations")
    for notations in notations_elements:
        for item in notations:
            if item.tag in {"tied", "slur"}:
                kind = "notated-tie" if item.tag == "tied" else "slur"
                spans.append(
                    _source_span_fact(
                        event_id, kind, item, len(spans) + 1, item.attrib.get("number", "1")
                    )
                )
    for notations in notations_elements:
        for group in notations:
            if group.tag in {"tied", "slur"}:
                continue
            if group.tag in {"glissando", "slide", "other-notation"}:
                spans.append(
                    _source_span_fact(
                        event_id,
                        group.tag,
                        group,
                        len(spans) + 1,
                        group.attrib.get("number", "1"),
                    )
                )
            elif group.tag in {"fermata", "arpeggiate", "non-arpeggiate"}:
                mark_type = (
                    group.attrib.get("direction")
                    if group.tag == "arpeggiate"
                    else group.attrib.get("type")
                )
                marks.append(
                    _source_mark_fact(
                        event_id,
                        "notation",
                        group.tag,
                        group,
                        len(marks) + 1,
                        mark_type=mark_type,
                        number=group.attrib.get("number")
                        if group.tag in {"arpeggiate", "non-arpeggiate"}
                        else None,
                    )
                )
            elif group.tag in {"articulations", "ornaments", "technical"}:
                family = {
                    "articulations": "articulation",
                    "ornaments": "ornament",
                    "technical": "technical",
                }[group.tag]
                ornament_target: int | None = None
                for item in group:
                    if family == "ornament" and item.tag == "accidental-mark":
                        if ornament_target is None:
                            raise ValueError("attachment oracle found an unbound accidental-mark")
                        current = list(marks[ornament_target])
                        current_accidentals = current[9]
                        if not isinstance(current_accidentals, tuple):
                            raise TypeError("attachment oracle expected ornament accidentals")
                        current[9] = (
                            *current_accidentals,
                            _ornament_accidental_fact(item),
                        )
                        marks[ornament_target] = tuple(current)
                    elif family == "ornament" and item.tag == "wavy-line":
                        spans.append(
                            _source_span_fact(
                                event_id,
                                "wavy-line",
                                item,
                                len(spans) + 1,
                                item.attrib.get("number", "1"),
                            )
                        )
                    elif (
                        family == "ornament"
                        and item.tag == "tremolo"
                        and item.attrib.get("type", "single") in {"start", "stop"}
                    ):
                        spans.append(
                            _source_span_fact(
                                event_id,
                                "tremolo",
                                item,
                                len(spans) + 1,
                                "1",
                                tremolo_marks=int(item.text or "0"),
                            )
                        )
                    elif family == "technical" and item.tag in {"hammer-on", "pull-off"}:
                        spans.append(
                            _source_span_fact(
                                event_id,
                                item.tag,
                                item,
                                len(spans) + 1,
                                item.attrib.get("number", "1"),
                            )
                        )
                    else:
                        marks.append(
                            _source_mark_fact(
                                event_id,
                                family,
                                item.tag,
                                item,
                                len(marks) + 1,
                                mark_type=item.attrib.get("type")
                                or (
                                    "single"
                                    if family == "ornament" and item.tag == "tremolo"
                                    else None
                                ),
                                tremolo_marks=(
                                    int(item.text or "0")
                                    if family == "ornament" and item.tag == "tremolo"
                                    else None
                                ),
                                technical=(
                                    _source_technical_fact(item) if family == "technical" else None
                                ),
                            )
                        )
                        if family == "ornament":
                            ornament_target = len(marks) - 1
    return marks, spans


def _source_mark_fact(
    event_id: str,
    family: str,
    kind: str,
    element: element_tree.Element,
    source_order: int,
    *,
    mark_type: str | None = None,
    number: str | None = None,
    tremolo_marks: int | None = None,
    technical: EvidenceValue = None,
) -> tuple[EvidenceValue, ...]:
    return (
        event_id,
        family,
        kind,
        element.text,
        source_order,
        element.attrib.get("placement"),
        mark_type,
        element.attrib.get("smufl"),
        tremolo_marks,
        (),
        technical,
        number,
    )


def _source_span_fact(
    event_id: str,
    kind: str,
    element: element_tree.Element,
    source_order: int,
    number: str,
    *,
    tremolo_marks: int | None = None,
) -> tuple[EvidenceValue, ...]:
    return (
        event_id,
        kind,
        number,
        element.attrib.get("type", ""),
        source_order,
        element.attrib.get("placement"),
        None if kind == "tremolo" else element.text,
        element.attrib.get("line-type"),
        tremolo_marks,
    )


def _ornament_accidental_fact(element: element_tree.Element) -> EvidenceValue:
    return (
        element.text or "",
        element.attrib.get("placement"),
        _yes_no(element.attrib.get("bracket")),
        _yes_no(element.attrib.get("parentheses")),
        element.attrib.get("smufl"),
    )


def _source_technical_fact(element: element_tree.Element) -> EvidenceValue:
    if element.tag == "harmonic":
        harmonic_type = next(
            (name for name in ("natural", "artificial") if element.find(name) is not None), None
        )
        pitch_type = next(
            (
                name
                for name in ("base-pitch", "touching-pitch", "sounding-pitch")
                if element.find(name) is not None
            ),
            None,
        )
        return (
            "harmonic",
            harmonic_type,
            pitch_type,
            _yes_no(element.attrib.get("print-object")),
            element.attrib.get("number"),
        )
    if element.tag == "bend":
        release = element.find("release")
        with_bar = element.find("with-bar")
        return (
            "bend",
            _fraction_fact(element.findtext("bend-alter") or "0"),
            "pre-bend"
            if element.find("pre-bend") is not None
            else "release"
            if release is not None
            else None,
            _optional_fraction_fact(release.attrib.get("offset")) if release is not None else None,
            with_bar.text if with_bar is not None else None,
            with_bar.attrib.get("placement") if with_bar is not None else None,
        )
    if element.tag == "hole":
        closed = element.find("hole-closed")
        return (
            "hole",
            element.findtext("hole-type"),
            closed.text if closed is not None else "",
            closed.attrib.get("location") if closed is not None else None,
            element.findtext("hole-shape"),
        )
    if element.tag == "arrow":
        return (
            "arrow",
            element.findtext("arrow-direction"),
            element.findtext("arrow-style"),
            element.find("arrowhead") is not None,
            element.findtext("circular-arrow"),
        )
    if element.tag == "harmon-mute":
        closed = element.find("harmon-closed")
        return (
            "harmon-mute",
            closed.text if closed is not None else "",
            closed.attrib.get("location") if closed is not None else None,
        )
    if element.tag == "fingering":
        return (
            "fingering",
            _yes_no(element.attrib.get("substitution")),
            _yes_no(element.attrib.get("alternate")),
        )
    if element.tag in {"heel", "toe"}:
        return (element.tag, _yes_no(element.attrib.get("substitution")))
    if element.tag == "tap":
        return ("tap", element.attrib.get("hand"))
    return None


def _span_topology(records: tuple[EvidenceValue, ...]) -> EvidenceValue:
    grouped: dict[tuple[str, str], list[tuple[EvidenceValue, ...]]] = {}
    for raw in records:
        record = tuple(raw) if isinstance(raw, tuple) else ()
        grouped.setdefault((str(record[1]), str(record[2])), []).append(
            (record[3], record[0], record[4])
        )
    return tuple((kind, number, tuple(endpoints)) for (kind, number), endpoints in grouped.items())


def _time_span_topology(records: tuple[EvidenceValue, ...]) -> EvidenceValue:
    grouped: dict[tuple[str, str], list[tuple[EvidenceValue, ...]]] = {}
    openings: dict[tuple[str, str], EvidenceValue] = {}
    for raw in records:
        record = tuple(raw) if isinstance(raw, tuple) else ()
        key = (str(record[0]), str(record[1]))
        if record[3] is not None:
            openings[key] = record[3]
        grouped.setdefault(key, []).append((record[2], record[4], record[5], record[6]))
    return tuple(
        (kind, number, openings.get((kind, number)), tuple(endpoints))
        for (kind, number), endpoints in grouped.items()
    )


def _encoding_fact(element: element_tree.Element | None) -> EvidenceValue:
    if element is None:
        return None
    return (
        tuple(item.text or "" for item in element.findall("encoding-date")),
        tuple((item.text or "", item.attrib.get("type")) for item in element.findall("encoder")),
        tuple(item.text or "" for item in element.findall("software")),
        tuple(item.text or "" for item in element.findall("encoding-description")),
        tuple(
            (
                item.attrib.get("type") == "yes",
                item.attrib.get("element") or "",
                item.attrib.get("attribute"),
                item.attrib.get("value"),
            )
            for item in element.findall("supports")
        ),
    )


def _standard_version(root: element_tree.Element) -> str:
    declared = root.attrib.get("version", "1.0")
    return "4.1-draft" if declared == "4.1" else declared


def _integer_text(value: str | None) -> int | None:
    return int(value) if value is not None else None


def _yes_no(value: str | None) -> bool | None:
    if value is None:
        return None
    if value not in {"yes", "no"}:
        raise ValueError(f"independent oracle expected yes-no, got {value!r}")
    return value == "yes"


def _fraction_fact(value: str | Fraction) -> EvidenceValue:
    fraction = value if isinstance(value, Fraction) else Fraction(value)
    return (fraction.numerator, fraction.denominator)


def _optional_fraction_fact(value: str | Fraction | None) -> EvidenceValue:
    return _fraction_fact(value) if value is not None else None


def _double_above_fact(element: element_tree.Element) -> bool | None:
    double = element.find("double")
    return _yes_no(double.attrib.get("above")) if double is not None else None


def _style_fact(element: element_tree.Element) -> EvidenceValue:
    font_size = element.attrib.get("font-size")
    letter_spacing = element.attrib.get("letter-spacing")
    line_height = element.attrib.get("line-height")
    result: tuple[EvidenceValue, ...] = (
        _optional_fraction_fact(element.attrib.get("default-x")),
        _optional_fraction_fact(element.attrib.get("default-y")),
        _optional_fraction_fact(element.attrib.get("relative-x")),
        _optional_fraction_fact(element.attrib.get("relative-y")),
        element.attrib.get("color"),
        element.attrib.get("font-family"),
        element.attrib.get("font-style"),
        _number_or_keyword_fact(font_size),
        element.attrib.get("font-weight"),
        element.attrib.get("justify"),
        element.attrib.get("halign"),
        element.attrib.get("valign"),
        element.attrib.get("enclosure"),
        _number_or_keyword_fact(letter_spacing),
        _number_or_keyword_fact(line_height),
        _integer_text(element.attrib.get("underline")),
        _integer_text(element.attrib.get("overline")),
        _integer_text(element.attrib.get("line-through")),
        _optional_fraction_fact(element.attrib.get("rotation")),
        element.attrib.get("dir"),
        element.attrib.get(_XML_LANG),
        element.attrib.get(_XML_SPACE),
    )
    return result if any(item is not None for item in result) else None


def _number_or_keyword_fact(value: str | None) -> EvidenceValue:
    if value is None:
        return None
    try:
        number = Fraction(value)
    except ValueError:
        return (None, value)
    return (_fraction_fact(number), None)


def _evidence_tuple(values: tuple[tuple[object, ...], ...]) -> EvidenceValue:
    return tuple(_evidence_item(item) for item in values)


def _evidence_item(value: object) -> EvidenceValue:
    if value is None or isinstance(value, str | int | bool):
        return value
    if isinstance(value, tuple):
        return tuple(_evidence_item(item) for item in value)
    raise TypeError("independent oracle produced an unsupported fact")
