"""Map a validated score to a typed, explicitly partial temporal projection."""

from __future__ import annotations

from collections import Counter
from dataclasses import replace
from fractions import Fraction

from lxml import etree

from teachmemusic.score.v2.annotation_graph import AnnotationGraphError, resolve_annotation_graph
from teachmemusic.score.v2.annotations import (
    DirectionMark,
    EventAnchor,
    EventMarkMarker,
    FiguredBassAnnotation,
    HarmonySymbol,
    LyricMarker,
    SpanMarker,
    TimeSpanMarker,
)
from teachmemusic.score.v2.links import PartLink, ScopedBookmark, ScopedLink
from teachmemusic.score.v2.playback import InstrumentPlayback, Player
from teachmemusic.score.v2.presentation import NameDisplay, SourcePresentation
from teachmemusic.score.v2.temporal import (
    DeferredConstruct,
    TemporalAccidental,
    TemporalAlignment,
    TemporalAttributes,
    TemporalBarline,
    TemporalBeam,
    TemporalClef,
    TemporalCursorMove,
    TemporalDirective,
    TemporalEditorial,
    TemporalEncoding,
    TemporalEncodingSupport,
    TemporalEvent,
    TemporalFeature,
    TemporalFermata,
    TemporalForPart,
    TemporalGraceTiming,
    TemporalGrouping,
    TemporalInstrument,
    TemporalInterchangeableTime,
    TemporalKey,
    TemporalKeyAccidental,
    TemporalKeyAlteration,
    TemporalKeyOctave,
    TemporalMeasure,
    TemporalMeasureStyle,
    TemporalMiscellaneousField,
    TemporalNavigationMark,
    TemporalPart,
    TemporalPartClef,
    TemporalPartGroup,
    TemporalPartSymbol,
    TemporalPitch,
    TemporalReadResult,
    TemporalScore,
    TemporalScoreMetadata,
    TemporalStaff,
    TemporalStaffDetails,
    TemporalStaffLineDetail,
    TemporalStaffTuning,
    TemporalTime,
    TemporalTransposition,
    TemporalTuplet,
    TemporalTupletPortion,
    TemporalTypedText,
    TemporalVoice,
    resolve_sounding_pitches,
)

from .annotation_mapping import (
    map_direction,
    map_event_marks,
    map_figured_bass,
    map_harmony,
    map_lyric,
    map_notehead,
)
from .contracts import DocumentKind, ValidatedMusicXmlDocument
from .layout_mapping import map_measure_layout, map_score_layout
from .links_mapping import map_bookmark, map_link, map_part_link
from .playback_mapping import (
    map_midi_device,
    map_midi_instrument,
    map_sound,
    map_virtual_instrument,
)
from .presentation_mapping import map_name_display, map_presentation_style


class TemporalMappingError(ValueError):
    """Validated XML contains a temporal construct not safely mappable here."""


_XML_LANG = "{http://www.w3.org/XML/1998/namespace}lang"


class _Audit:
    def __init__(self) -> None:
        self.elements: set[etree._Element] = set()
        self.attributes: dict[etree._Element, set[str]] = {}
        self.text: set[etree._Element] = set()

    def take(self, element: etree._Element | None) -> etree._Element | None:
        if element is not None:
            self.elements.add(element)
        return element

    def attr(self, element: etree._Element, name: str) -> str | None:
        self.take(element)
        self.attributes.setdefault(element, set()).add(name)
        return element.get(name)

    def child(self, element: etree._Element, name: str) -> etree._Element | None:
        return self.take(element.find(name))

    def children(self, element: etree._Element, name: str) -> tuple[etree._Element, ...]:
        found = tuple(element.findall(name))
        for child in found:
            self.take(child)
        return found

    def value(self, element: etree._Element | None) -> str | None:
        if element is None:
            return None
        self.take(element)
        self.text.add(element)
        return element.text

    def child_value(self, element: etree._Element, name: str) -> str | None:
        return self.value(self.child(element, name))

    def deferred(self, root: etree._Element) -> tuple[DeferredConstruct, ...]:
        tree = root.getroottree()
        counts: Counter[tuple[str, str]] = Counter()

        def walk(element: etree._Element) -> None:
            path = tree.getpath(element)
            if element not in self.elements:
                counts[(path, etree.QName(element).localname)] += 1
                return
            for key in element.attrib:
                if key not in self.attributes.get(element, set()):
                    counts[
                        (f"{path}/@{etree.QName(key).localname}", f"@{etree.QName(key).localname}")
                    ] += 1
            if element.text and element.text.strip() and element not in self.text:
                counts[(f"{path}/text()", "#text")] += 1
            for child in element:
                if isinstance(child.tag, str):
                    walk(child)

        walk(root)
        return tuple(
            DeferredConstruct(path, tag, count) for (path, tag), count in sorted(counts.items())
        )

    def presentation_records(self, root: etree._Element) -> tuple[SourcePresentation, ...]:
        """Preserve shared style on mapped nodes without a narrower style field."""

        tree = root.getroottree()
        style_attributes = {
            "default-x",
            "default-y",
            "relative-x",
            "relative-y",
            "color",
            "font-family",
            "font-style",
            "font-size",
            "font-weight",
            "justify",
            "halign",
            "valign",
            "enclosure",
            "letter-spacing",
            "line-height",
            "underline",
            "overline",
            "line-through",
            "rotation",
            "dir",
            _XML_LANG,
            "{http://www.w3.org/XML/1998/namespace}space",
        }
        records = []
        for element in sorted(self.elements, key=tree.getpath):
            consumed = self.attributes.get(element, set())
            if not any(key in element.attrib and key not in consumed for key in style_attributes):
                continue
            style = map_presentation_style(element, self)
            if style is not None:
                records.append(
                    SourcePresentation(tree.getpath(element), etree.QName(element).localname, style)
                )
        return tuple(records)


def _integer(value: str | None, context: str) -> int:
    if value is None:
        raise TemporalMappingError(f"missing {context}")
    try:
        return int(value)
    except ValueError as error:
        raise TemporalMappingError(f"invalid integer for {context}: {value}") from error


def _positive(value: int, context: str) -> int:
    if value <= 0:
        raise TemporalMappingError(f"{context} must be positive")
    return value


def _decimal_fraction(value: str | None, context: str) -> Fraction:
    if value is None:
        raise TemporalMappingError(f"missing {context}")
    try:
        return Fraction(value)
    except (ValueError, ZeroDivisionError) as error:
        raise TemporalMappingError(f"invalid exact number for {context}: {value}") from error


def _yes_no(value: str | None, context: str) -> bool | None:
    if value is None:
        return None
    if value not in {"yes", "no"}:
        raise TemporalMappingError(f"invalid yes-no value for {context}: {value}")
    return value == "yes"


def _present_text(element: etree._Element | None, audit: _Audit) -> str | None:
    """Preserve the distinction between an absent and present-empty element."""

    if element is None:
        return None
    value = audit.value(element)
    return value if value is not None else ""


def _optional_child_text(element: etree._Element | None, name: str, audit: _Audit) -> str | None:
    return _present_text(audit.child(element, name), audit) if element is not None else None


_WRITTEN_QUARTERS = {
    "maxima": Fraction(32),
    "long": Fraction(16),
    "breve": Fraction(8),
    "whole": Fraction(4),
    "half": Fraction(2),
    "quarter": Fraction(1),
    "eighth": Fraction(1, 2),
    "16th": Fraction(1, 4),
    "32nd": Fraction(1, 8),
    "64th": Fraction(1, 16),
    "128th": Fraction(1, 32),
    "256th": Fraction(1, 64),
    "512th": Fraction(1, 128),
    "1024th": Fraction(1, 256),
}


def _written_duration(value: str | None, dots: int) -> Fraction | None:
    if value is None:
        return None
    if value not in _WRITTEN_QUARTERS:
        raise TemporalMappingError(f"unsupported written note type: {value}")
    return _WRITTEN_QUARTERS[value] * sum(Fraction(1, 2**index) for index in range(dots + 1))


def _pitch(element: etree._Element, audit: _Audit) -> TemporalPitch:
    step = audit.child_value(element, "step")
    octave = _integer(audit.child_value(element, "octave"), "pitch octave")
    alter = Fraction(audit.child_value(element, "alter") or "0")
    if step not in {"A", "B", "C", "D", "E", "F", "G"}:
        raise TemporalMappingError(f"unsupported pitch step: {step}")
    return TemporalPitch(step, alter, octave)


def _transposition(
    element: etree._Element, audit: _Audit, *, staff: str | None = None
) -> TemporalTransposition:
    diatonic_text = audit.child_value(element, "diatonic")
    octave_text = audit.child_value(element, "octave-change")
    doubling = audit.child(element, "double")
    double_above = audit.attr(doubling, "above") if doubling is not None else None
    return TemporalTransposition(
        staff=audit.attr(element, "number") if staff is None else staff,
        diatonic=_integer(diatonic_text, "diatonic") if diatonic_text is not None else None,
        chromatic=_decimal_fraction(audit.child_value(element, "chromatic"), "chromatic"),
        octave_change=_integer(octave_text, "octave-change") if octave_text is not None else 0,
        doubling_above=(double_above == "yes" if doubling is not None else None),
    )


def _editorial(element: etree._Element, audit: _Audit) -> TemporalEditorial | None:
    footnote = audit.child(element, "footnote")
    level = audit.child(element, "level")
    if footnote is None and level is None:
        return None
    return TemporalEditorial(
        footnote=audit.value(footnote),
        footnote_language=audit.attr(footnote, _XML_LANG) if footnote is not None else None,
        level=audit.value(level),
        level_reference=(
            _yes_no(audit.attr(level, "reference"), "editorial level reference")
            if level is not None
            else None
        ),
        level_type=audit.attr(level, "type") if level is not None else None,
        level_parentheses=(
            _yes_no(audit.attr(level, "parentheses"), "editorial level parentheses")
            if level is not None
            else None
        ),
        level_bracket=(
            _yes_no(audit.attr(level, "bracket"), "editorial level bracket")
            if level is not None
            else None
        ),
        level_size=audit.attr(level, "size") if level is not None else None,
    )


def _score_metadata(
    work: etree._Element | None,
    identification: etree._Element | None,
    audit: _Audit,
    *,
    concert_score: bool = False,
) -> TemporalScoreMetadata:
    work_number = _optional_child_text(work, "work-number", audit)
    if identification is None:
        return TemporalScoreMetadata(concert_score=concert_score, work_number=work_number)
    creators = tuple(
        TemporalTypedText(audit.value(item) or "", audit.attr(item, "type"))
        for item in audit.children(identification, "creator")
    )
    rights = tuple(
        TemporalTypedText(audit.value(item) or "", audit.attr(item, "type"))
        for item in audit.children(identification, "rights")
    )
    relations = tuple(
        TemporalTypedText(audit.value(item) or "", audit.attr(item, "type"))
        for item in audit.children(identification, "relation")
    )
    source_element = audit.child(identification, "source")
    source = _present_text(source_element, audit)
    encoding_element = audit.child(identification, "encoding")
    encoding = None
    if encoding_element is not None:
        encoding = TemporalEncoding(
            dates=tuple(
                audit.value(item) or ""
                for item in audit.children(encoding_element, "encoding-date")
            ),
            encoders=tuple(
                TemporalTypedText(audit.value(item) or "", audit.attr(item, "type"))
                for item in audit.children(encoding_element, "encoder")
            ),
            software=tuple(
                audit.value(item) or "" for item in audit.children(encoding_element, "software")
            ),
            descriptions=tuple(
                audit.value(item) or ""
                for item in audit.children(encoding_element, "encoding-description")
            ),
            supports=tuple(
                TemporalEncodingSupport(
                    supported=_yes_no(audit.attr(item, "type"), "encoding supports") is True,
                    element=audit.attr(item, "element") or "",
                    attribute=audit.attr(item, "attribute"),
                    value=audit.attr(item, "value"),
                )
                for item in audit.children(encoding_element, "supports")
            ),
        )
    miscellaneous_element = audit.child(identification, "miscellaneous")
    miscellaneous = tuple(
        TemporalMiscellaneousField(
            name=audit.attr(item, "name") or "",
            value=audit.value(item) or "",
        )
        for item in (
            audit.children(miscellaneous_element, "miscellaneous-field")
            if miscellaneous_element is not None
            else ()
        )
    )
    return TemporalScoreMetadata(
        concert_score=concert_score,
        work_number=work_number,
        creators=creators,
        rights=rights,
        source=source,
        relations=relations,
        encoding=encoding,
        miscellaneous=miscellaneous,
    )


def _attributes(
    element: etree._Element, audit: _Audit, onset: Fraction, order: int
) -> TemporalAttributes:
    divisions_text = audit.child_value(element, "divisions")
    staves_text = audit.child_value(element, "staves")
    divisions = (
        _positive(_integer(divisions_text, "divisions"), "divisions") if divisions_text else None
    )
    staves = _positive(_integer(staves_text, "staves"), "staves") if staves_text else None
    clefs = tuple(
        TemporalClef(
            staff=audit.attr(clef, "number") or "1",
            sign=audit.child_value(clef, "sign") or "",
            line=(int(value) if (value := audit.child_value(clef, "line")) else None),
            octave_change=(
                int(value) if (value := audit.child_value(clef, "clef-octave-change")) else None
            ),
            additional=_yes_no(audit.attr(clef, "additional"), "clef additional"),
            size=audit.attr(clef, "size"),
            after_barline=_yes_no(audit.attr(clef, "after-barline"), "clef after-barline"),
            print_object=_yes_no(audit.attr(clef, "print-object"), "clef print-object"),
            source_id=audit.attr(clef, "id"),
        )
        for clef in audit.children(element, "clef")
    )
    keys: list[TemporalKey] = []
    for key in audit.children(element, "key"):
        alterations_list: list[TemporalKeyAlteration] = []
        for step in audit.children(key, "key-step"):
            alter = step.getnext()
            if alter is None or etree.QName(alter).localname != "key-alter":
                raise TemporalMappingError("incomplete non-traditional key")
            audit.take(alter)
            accidental_elements: list[etree._Element] = []
            accidental = alter.getnext()
            while accidental is not None and etree.QName(accidental).localname == "key-accidental":
                audit.take(accidental)
                accidental_elements.append(accidental)
                accidental = accidental.getnext()
            alterations_list.append(
                TemporalKeyAlteration(
                    step=audit.value(step) or "",
                    alter=_decimal_fraction(audit.value(alter), "key alter"),
                    accidental=(
                        audit.value(accidental_elements[0]) if accidental_elements else None
                    ),
                    accidental_smufl=(
                        audit.attr(accidental_elements[0], "smufl") if accidental_elements else None
                    ),
                    accidentals=tuple(
                        TemporalKeyAccidental(audit.value(item) or "", audit.attr(item, "smufl"))
                        for item in accidental_elements
                    ),
                )
            )
        alterations = tuple(alterations_list)
        cancel = audit.child(key, "cancel")
        octaves = tuple(
            TemporalKeyOctave(
                number=_positive(
                    _integer(audit.attr(item, "number"), "key-octave number"),
                    "key-octave number",
                ),
                octave=_integer(audit.value(item), "key octave"),
                cancel=_yes_no(audit.attr(item, "cancel"), "key-octave cancel"),
            )
            for item in audit.children(key, "key-octave")
        )
        keys.append(
            TemporalKey(
                fifths=(int(value) if (value := audit.child_value(key, "fifths")) else None),
                mode=audit.child_value(key, "mode"),
                staff=audit.attr(key, "number"),
                cancel=_integer(audit.value(cancel), "key cancel") if cancel is not None else None,
                cancel_location=audit.attr(cancel, "location") if cancel is not None else None,
                alterations=alterations,
                octaves=octaves,
                print_object=_yes_no(audit.attr(key, "print-object"), "key print-object"),
                source_id=audit.attr(key, "id"),
            )
        )
    times: list[TemporalTime] = []
    for time in audit.children(element, "time"):
        interchangeable = audit.child(time, "interchangeable")
        times.append(
            TemporalTime(
                beats=tuple(audit.value(beat) or "" for beat in audit.children(time, "beats")),
                beat_types=tuple(
                    _integer(audit.value(beat_type), "beat-type")
                    for beat_type in audit.children(time, "beat-type")
                ),
                symbol=audit.attr(time, "symbol"),
                staff=audit.attr(time, "number"),
                senza_misura=audit.child_value(time, "senza-misura"),
                separator=audit.attr(time, "separator"),
                interchangeable=(
                    TemporalInterchangeableTime(
                        beats=tuple(
                            audit.value(beat) or ""
                            for beat in audit.children(interchangeable, "beats")
                        ),
                        beat_types=tuple(
                            _integer(audit.value(beat_type), "interchangeable beat-type")
                            for beat_type in audit.children(interchangeable, "beat-type")
                        ),
                        relation=audit.child_value(interchangeable, "time-relation"),
                        symbol=audit.attr(interchangeable, "symbol"),
                        separator=audit.attr(interchangeable, "separator"),
                    )
                    if interchangeable is not None
                    else None
                ),
                print_object=_yes_no(audit.attr(time, "print-object"), "time print-object"),
                source_id=audit.attr(time, "id"),
            )
        )
    transpositions = tuple(
        _transposition(item, audit) for item in audit.children(element, "transpose")
    )
    instrument_count_text = audit.child_value(element, "instruments")
    instrument_count = (
        _positive(_integer(instrument_count_text, "instruments"), "instruments")
        if instrument_count_text is not None
        else None
    )
    measure_styles: list[TemporalMeasureStyle] = []
    for measure_style in audit.children(element, "measure-style"):
        children = [child for child in measure_style if isinstance(child.tag, str)]
        if len(children) != 1:
            raise TemporalMappingError("measure-style must contain exactly one semantic style")
        style = audit.take(children[0])
        assert style is not None
        kind = etree.QName(style).localname
        if kind not in {"multiple-rest", "measure-repeat", "beat-repeat", "slash"}:
            raise TemporalMappingError(f"unsupported measure-style kind: {kind}")
        value_text = audit.value(style) if kind in {"multiple-rest", "measure-repeat"} else None
        slash_type = audit.child_value(style, "slash-type")
        slash_dots = len(audit.children(style, "slash-dot"))
        measure_styles.append(
            TemporalMeasureStyle(
                staff=audit.attr(measure_style, "number"),
                kind=kind,
                value=_integer(value_text, f"{kind} value") if value_text else None,
                action=audit.attr(style, "type"),
                slashes=(
                    _positive(
                        _integer(audit.attr(style, "slashes"), f"{kind} slashes"),
                        f"{kind} slashes",
                    )
                    if style.get("slashes") is not None
                    else None
                ),
                use_symbols=_yes_no(audit.attr(style, "use-symbols"), "multiple-rest symbols"),
                use_dots=_yes_no(audit.attr(style, "use-dots"), f"{kind} dots"),
                use_stems=_yes_no(audit.attr(style, "use-stems"), "slash stems"),
                slash_type=slash_type,
                slash_dots=slash_dots,
                source_id=audit.attr(measure_style, "id"),
            )
        )

    def map_staff_details(details: etree._Element) -> TemporalStaffDetails:
        staff_size = audit.child(details, "staff-size")
        return TemporalStaffDetails(
            staff=audit.attr(details, "number"),
            staff_type=audit.child_value(details, "staff-type"),
            lines=(
                _integer(value, "staff lines")
                if (value := audit.child_value(details, "staff-lines")) is not None
                else None
            ),
            tunings=tuple(
                TemporalStaffTuning(
                    line=_integer(audit.attr(tuning, "line"), "staff tuning line"),
                    step=audit.child_value(tuning, "tuning-step") or "",
                    alter=_decimal_fraction(
                        audit.child_value(tuning, "tuning-alter") or "0", "staff tuning alter"
                    ),
                    octave=_integer(
                        audit.child_value(tuning, "tuning-octave"), "staff tuning octave"
                    ),
                )
                for tuning in audit.children(details, "staff-tuning")
            ),
            capo=(
                _integer(value, "capo")
                if (value := audit.child_value(details, "capo")) is not None
                else None
            ),
            size=(
                _decimal_fraction(value, "staff size")
                if (value := audit.value(staff_size)) is not None
                else None
            ),
            scaling=(
                _decimal_fraction(value, "staff size scaling")
                if staff_size is not None
                and (value := audit.attr(staff_size, "scaling")) is not None
                else None
            ),
            show_frets=audit.attr(details, "show-frets"),
            print_object=_yes_no(audit.attr(details, "print-object"), "staff-details print-object"),
            line_details=tuple(
                TemporalStaffLineDetail(
                    line=_positive(
                        _integer(audit.attr(line, "line"), "staff line-detail line"),
                        "staff line-detail line",
                    ),
                    print_object=_yes_no(
                        audit.attr(line, "print-object"), "staff line-detail print-object"
                    ),
                    presentation=map_presentation_style(line, audit),
                )
                for line in audit.children(details, "line-detail")
            ),
        )

    staff_details = tuple(
        map_staff_details(details) for details in audit.children(element, "staff-details")
    )
    part_symbol_elements = audit.children(element, "part-symbol")
    part_symbols = tuple(
        TemporalPartSymbol(
            value=audit.value(item) or "",
            top_staff=audit.attr(item, "top-staff"),
            bottom_staff=audit.attr(item, "bottom-staff"),
            presentation=map_presentation_style(item, audit),
        )
        for item in part_symbol_elements
    )
    part_symbol = part_symbols[0] if part_symbols else None
    for_parts: list[TemporalForPart] = []
    for item in audit.children(element, "for-part"):
        staff = audit.attr(item, "number")
        part_clef = audit.child(item, "part-clef")
        clef = (
            TemporalPartClef(
                sign=audit.child_value(part_clef, "sign") or "",
                line=(
                    _integer(value, "part clef line")
                    if (value := audit.child_value(part_clef, "line")) is not None
                    else None
                ),
                octave_change=(
                    _integer(value, "part clef octave change")
                    if (value := audit.child_value(part_clef, "clef-octave-change")) is not None
                    else None
                ),
            )
            if part_clef is not None
            else None
        )
        part_transpose = audit.child(item, "part-transpose")
        if part_transpose is None:
            raise TemporalMappingError("for-part has no part-transpose")
        for_parts.append(
            TemporalForPart(
                staff=staff,
                clef=clef,
                transposition=_transposition(part_transpose, audit, staff=staff),
                source_id=audit.attr(item, "id"),
            )
        )
    directives = tuple(
        TemporalDirective(
            value=audit.value(item) or "",
            language=audit.attr(item, _XML_LANG),
            source_order=index,
        )
        for index, item in enumerate(element, start=1)
        if isinstance(item.tag, str) and etree.QName(item).localname == "directive"
    )
    return TemporalAttributes(
        onset=onset,
        divisions=divisions,
        staves=staves,
        clefs=clefs,
        keys=tuple(keys),
        times=tuple(times),
        source_order=order,
        transpositions=transpositions,
        instrument_count=instrument_count,
        measure_styles=tuple(measure_styles),
        staff_details=staff_details,
        part_symbol=part_symbol,
        for_parts=tuple(for_parts),
        directives=directives,
        part_symbols=part_symbols,
    )


def _note(
    element: etree._Element,
    audit: _Audit,
    *,
    part_id: str,
    measure_ordinal: int,
    order: int,
    cursor: Fraction,
    divisions: int,
    last_note: TemporalEvent | None,
) -> tuple[TemporalEvent, Fraction]:
    chord = audit.child(element, "chord") is not None
    grace_element = audit.child(element, "grace")
    grace = grace_element is not None
    cue = audit.child(element, "cue") is not None
    rest = audit.child(element, "rest")
    pitched = audit.child(element, "pitch")
    unpitched = audit.child(element, "unpitched")
    if sum(item is not None for item in (rest, pitched, unpitched)) != 1:
        raise TemporalMappingError("note must have exactly one pitch/rest/unpitched kind")
    kind = "rest" if rest is not None else ("unpitched" if unpitched is not None else "pitched")
    pitch = _pitch(pitched, audit) if pitched is not None else None
    display_position = None
    if rest is not None:
        step = audit.child_value(rest, "display-step")
        octave = audit.child_value(rest, "display-octave")
        if step is not None and octave is not None:
            display_position = TemporalPitch(step, Fraction(0), _integer(octave, "display-octave"))
    if unpitched is not None:
        step = audit.child_value(unpitched, "display-step")
        octave = audit.child_value(unpitched, "display-octave")
        if step is not None and octave is not None:
            display_position = TemporalPitch(step, Fraction(0), _integer(octave, "display-octave"))
    duration_text = audit.child_value(element, "duration")
    source_duration = _integer(duration_text, "note duration") if duration_text else None
    if source_duration is None and not grace:
        raise TemporalMappingError("non-grace note has no duration")
    if source_duration is not None and source_duration < 0:
        raise TemporalMappingError("negative note duration")
    duration = Fraction(source_duration or 0, divisions)
    grace_timing = None
    if grace_element is not None:
        slash = audit.attr(grace_element, "slash")
        make_time = audit.attr(grace_element, "make-time")
        previous = audit.attr(grace_element, "steal-time-previous")
        following = audit.attr(grace_element, "steal-time-following")
        grace_timing = TemporalGraceTiming(
            slash=None if slash is None else slash == "yes",
            make_time=(
                _decimal_fraction(make_time, "grace make-time") / divisions
                if make_time is not None
                else None
            ),
            steal_previous_percent=(
                _decimal_fraction(previous, "grace steal-time-previous")
                if previous is not None
                else None
            ),
            steal_following_percent=(
                _decimal_fraction(following, "grace steal-time-following")
                if following is not None
                else None
            ),
        )
    staff = audit.child_value(element, "staff") or "1"
    voice = audit.child_value(element, "voice") or "1"
    if chord and (last_note is None or last_note.kind == "rest"):
        raise TemporalMappingError("chord follower has no preceding note")
    onset = last_note.onset if chord and last_note is not None else cursor
    event_id = f"{part_id}:m{measure_ordinal}:n{order}"
    chord_id = last_note.chord_id or last_note.id if chord and last_note is not None else None
    time_mod = audit.child(element, "time-modification")
    time_modification = None
    normal_type = None
    normal_dots = 0
    if time_mod is not None:
        time_modification = (
            _positive(
                _integer(audit.child_value(time_mod, "actual-notes"), "actual-notes"),
                "actual-notes",
            ),
            _positive(
                _integer(audit.child_value(time_mod, "normal-notes"), "normal-notes"),
                "normal-notes",
            ),
        )
        normal_type = audit.child_value(time_mod, "normal-type")
        normal_dots = len(audit.children(time_mod, "normal-dot"))
    beams = tuple(
        TemporalBeam(
            number=_integer(audit.attr(beam, "number") or "1", "beam number"),
            value=audit.value(beam) or "",
            repeater=_yes_no(audit.attr(beam, "repeater"), "beam repeater"),
            fan=audit.attr(beam, "fan"),
            source_id=audit.attr(beam, "id"),
        )
        for beam in audit.children(element, "beam")
    )
    instruments = audit.children(element, "instrument")
    instrument_ids = tuple(audit.attr(instrument, "id") or "" for instrument in instruments)
    instrument_id = instrument_ids[0] if instrument_ids else None
    tuplets: list[TemporalTuplet] = []
    span_markers: list[SpanMarker] = []
    lyric_markers: list[LyricMarker] = []
    for tie in audit.children(element, "tie"):
        audit.take(tie)
        span_markers.append(
            SpanMarker(
                kind="sounding-tie",
                number="1",
                action=audit.attr(tie, "type") or "",
                source_order=len(span_markers) + 1,
                time_only=audit.attr(tie, "time-only"),
            )
        )
    notations_elements = audit.children(element, "notations")

    def portion(container: etree._Element, name: str) -> TemporalTupletPortion | None:
        item = audit.child(container, name)
        if item is None:
            return None
        number = audit.child_value(item, "tuplet-number")
        return TemporalTupletPortion(
            number=_integer(number, f"{name} number") if number else None,
            note_type=audit.child_value(item, "tuplet-type"),
            dots=len(audit.children(item, "tuplet-dot")),
        )

    for notations in notations_elements:
        for child in notations:
            if not isinstance(child.tag, str):
                continue
            notation_kind = etree.QName(child).localname
            if notation_kind in {"tied", "slur"}:
                allowed_actions = (
                    {"start", "continue", "stop", "let-ring"}
                    if notation_kind == "tied"
                    else {"start", "continue", "stop"}
                )
                if child.get("type") not in allowed_actions:
                    continue
                audit.take(child)
                span_markers.append(
                    SpanMarker(
                        kind="notated-tie" if notation_kind == "tied" else "slur",
                        number=audit.attr(child, "number") or "1",
                        action=audit.attr(child, "type") or "",
                        source_order=len(span_markers) + 1,
                        placement=audit.attr(child, "placement"),
                        source_id=audit.attr(child, "id"),
                        line_type=audit.attr(child, "line-type"),
                        orientation=audit.attr(child, "orientation"),
                        dash_length=(
                            _decimal_fraction(audit.attr(child, "dash-length"), "span dash-length")
                            if child.get("dash-length") is not None
                            else None
                        ),
                        space_length=(
                            _decimal_fraction(
                                audit.attr(child, "space-length"), "span space-length"
                            )
                            if child.get("space-length") is not None
                            else None
                        ),
                    )
                )
        for tuplet in audit.children(notations, "tuplet"):
            tuplets.append(
                TemporalTuplet(
                    number=audit.attr(tuplet, "number") or "1",
                    action=audit.attr(tuplet, "type") or "",
                    bracket=_yes_no(audit.attr(tuplet, "bracket"), "tuplet bracket"),
                    placement=audit.attr(tuplet, "placement"),
                    show_number=audit.attr(tuplet, "show-number"),
                    show_type=audit.attr(tuplet, "show-type"),
                    line_shape=audit.attr(tuplet, "line-shape"),
                    actual=portion(tuplet, "tuplet-actual"),
                    normal=portion(tuplet, "tuplet-normal"),
                    source_id=audit.attr(tuplet, "id"),
                )
            )
    type_element = audit.child(element, "type")
    written_type = audit.value(type_element)
    written_size = audit.attr(type_element, "size") if type_element is not None else None
    dots = len(audit.children(element, "dot"))
    accidental_elements = audit.children(element, "accidental")
    accidentals = tuple(
        TemporalAccidental(
            value=audit.value(item) or "",
            cautionary=_yes_no(audit.attr(item, "cautionary"), "accidental cautionary"),
            editorial=_yes_no(audit.attr(item, "editorial"), "accidental editorial"),
            parentheses=_yes_no(audit.attr(item, "parentheses"), "accidental parentheses"),
            bracket=_yes_no(audit.attr(item, "bracket"), "accidental bracket"),
            size=audit.attr(item, "size"),
            smufl=audit.attr(item, "smufl"),
            presentation=map_presentation_style(item, audit),
        )
        for item in accidental_elements
    )
    accidental = accidentals[0] if accidentals else None
    stem = audit.child_value(element, "stem")
    notehead_marker = map_notehead(element, audit)
    event_markers_list: list[EventMarkMarker] = []
    for notations in notations_elements:
        mapped_markers, ornament_spans = map_event_marks(
            notations,
            audit,
            span_order_offset=len(span_markers),
            mark_order_offset=len(event_markers_list),
        )
        event_markers_list.extend(mapped_markers)
        span_markers.extend(ornament_spans)
    event_markers = tuple(event_markers_list)
    for lyric in audit.children(element, "lyric"):
        lyric_markers.append(map_lyric(lyric, audit, source_order=len(lyric_markers) + 1))
    event = TemporalEvent(
        id=event_id,
        kind=kind,
        onset=onset,
        duration=duration,
        source_duration=source_duration,
        staff=staff,
        voice=voice,
        pitch=pitch,
        chord_id=chord_id,
        written_type=written_type,
        dots=dots,
        time_modification=time_modification,
        beams=beams,
        tuplets=tuple(tuplets),
        grace=grace,
        cue=cue,
        source_order=order,
        written_duration=_written_duration(written_type, dots),
        performed_duration=(grace_timing.make_time if grace_timing else duration),
        grace_timing=grace_timing,
        instrument_id=instrument_id,
        instrument_ids=instrument_ids,
        normal_type=normal_type,
        normal_dots=normal_dots,
        display_position=display_position,
        span_markers=tuple(span_markers),
        lyric_markers=tuple(lyric_markers),
        notehead_marker=notehead_marker,
        event_markers=event_markers,
        accidental=accidental,
        stem=stem,
        written_size=written_size,
        source_id=audit.attr(element, "id"),
        editorial=_editorial(element, audit),
        presentation=map_presentation_style(element, audit),
        measure_rest=(
            _yes_no(audit.attr(rest, "measure"), "measure rest") if rest is not None else None
        ),
        print_object=_yes_no(audit.attr(element, "print-object"), "note print-object"),
        print_leger=_yes_no(audit.attr(element, "print-leger"), "note print-leger"),
        print_dot=_yes_no(audit.attr(element, "print-dot"), "note print-dot"),
        print_lyric=_yes_no(audit.attr(element, "print-lyric"), "note print-lyric"),
        dynamics=(
            _decimal_fraction(value, "note dynamics")
            if (value := audit.attr(element, "dynamics")) is not None
            else None
        ),
        accidentals=accidentals,
    )
    return event, cursor if chord else cursor + duration


def _measure(
    element: etree._Element,
    audit: _Audit,
    part_id: str,
    ordinal: int,
    initial_divisions: int | None,
    score_onset: Fraction,
    initial_transpositions: dict[str | None, TemporalTransposition],
    instrument_ids: frozenset[str],
) -> tuple[TemporalMeasure, int | None, dict[str | None, TemporalTransposition]]:
    header = element.getparent() if etree.QName(element).localname == "part" else element
    if header is None:
        raise TemporalMappingError("measure has no header")
    number = audit.attr(header, "number") or str(ordinal)
    implicit = audit.attr(header, "implicit") == "yes"
    non_controlling = audit.attr(header, "non-controlling") == "yes"
    cursor = Fraction(0)
    extent = Fraction(0)
    divisions = initial_divisions
    last_note: TemporalEvent | None = None
    events: list[TemporalEvent] = []
    attributes: list[TemporalAttributes] = []
    moves: list[TemporalCursorMove] = []
    barlines: list[TemporalBarline] = []
    harmonies: list[HarmonySymbol] = []
    directions: list[DirectionMark] = []
    time_span_markers: list[TimeSpanMarker] = []
    groupings: list[TemporalGrouping] = []
    sounds = []
    links = []
    bookmarks = []
    layout = map_measure_layout(header, element, audit)
    pending_bass: list[tuple[etree._Element, int, Fraction, int | None]] = []
    staves: set[str] = set()
    voices: set[str] = set()
    for order, child in enumerate(element, start=1):
        if not isinstance(child.tag, str):
            continue
        tag = etree.QName(child).localname
        if tag == "attributes":
            audit.take(child)
            value = _attributes(child, audit, cursor, order)
            attributes.append(value)
            if value.divisions is not None:
                divisions = value.divisions
            if value.staves is not None:
                staves.update(str(index) for index in range(1, value.staves + 1))
            staves.update(clef.staff for clef in value.clefs)
        elif tag == "note":
            audit.take(child)
            # MusicXML 4.1 documents the long-standing default of 1 when no
            # divisions value has appeared. The absent source declaration
            # remains absent from TemporalAttributes; only arithmetic uses
            # the standard default.
            effective_divisions = divisions or 1
            note, cursor = _note(
                child,
                audit,
                part_id=part_id,
                measure_ordinal=ordinal,
                order=order,
                cursor=cursor,
                divisions=effective_divisions,
                last_note=last_note,
            )
            if note.chord_id is not None and last_note is not None and last_note.chord_id is None:
                events[-1] = replace(last_note, chord_id=last_note.id)
            events.append(note)
            unknown_instruments = set(note.instrument_ids) - instrument_ids
            if unknown_instruments:
                raise TemporalMappingError(
                    f"unknown instrument id: {sorted(unknown_instruments)[0]}"
                )
            last_note = note
            staves.add(note.staff)
            voices.add(note.voice)
            extent = max(extent, cursor, note.onset + note.duration)
        elif tag in {"backup", "forward"}:
            audit.take(child)
            raw_duration = _positive(
                _integer(audit.child_value(child, "duration"), f"{tag} duration"),
                f"{tag} duration",
            )
            before = cursor
            effective_divisions = divisions or 1
            source_after = cursor + Fraction(raw_duration, effective_divisions) * (
                -1 if tag == "backup" else 1
            )
            underflow_recovered = tag == "backup" and source_after < 0 and cursor > 0
            if source_after < 0 and not underflow_recovered:
                raise TemporalMappingError(
                    f"backup precedes measure start in {part_id} measure {number}"
                )
            cursor = Fraction(0) if underflow_recovered else source_after
            voice = audit.child_value(child, "voice")
            staff = audit.child_value(child, "staff")
            moves.append(
                TemporalCursorMove(
                    tag,
                    before,
                    cursor,
                    raw_duration,
                    staff,
                    voice,
                    order,
                    _editorial(child, audit),
                    underflow_recovered,
                )
            )
            extent = max(extent, cursor)
            last_note = None
            if staff is not None:
                staves.add(staff)
            if voice is not None:
                voices.add(voice)
        elif tag == "barline":
            audit.take(child)
            repeat = audit.child(child, "repeat")
            ending = audit.child(child, "ending")
            fermatas = tuple(
                TemporalFermata(
                    audit.value(fermata),
                    audit.attr(fermata, "type"),
                    audit.attr(fermata, "id"),
                )
                for fermata in audit.children(child, "fermata")
            )
            navigation = []
            for kind in ("segno", "coda"):
                token = audit.attr(child, kind)
                if token is not None:
                    navigation.append(TemporalNavigationMark(kind, token, None, None))
                navigation.extend(
                    TemporalNavigationMark(
                        kind,
                        audit.value(mark),
                        audit.attr(mark, "id"),
                        audit.attr(mark, "smufl"),
                    )
                    for mark in audit.children(child, kind)
                )
            barlines.append(
                TemporalBarline(
                    onset=cursor,
                    location=audit.attr(child, "location"),
                    style=audit.child_value(child, "bar-style"),
                    repeat_direction=audit.attr(repeat, "direction")
                    if repeat is not None
                    else None,
                    repeat_times=audit.attr(repeat, "times") if repeat is not None else None,
                    ending_number=audit.attr(ending, "number") if ending is not None else None,
                    ending_type=audit.attr(ending, "type") if ending is not None else None,
                    source_order=order,
                    fermatas=fermatas,
                    navigation=tuple(navigation),
                    repeat_winged=audit.attr(repeat, "winged") if repeat is not None else None,
                    repeat_after_jump=(
                        _yes_no(audit.attr(repeat, "after-jump"), "repeat after-jump")
                        if repeat is not None
                        else None
                    ),
                    ending_text=_present_text(ending, audit),
                    ending_print_object=(
                        _yes_no(audit.attr(ending, "print-object"), "ending print-object")
                        if ending is not None
                        else None
                    ),
                    ending_system_relation=(
                        audit.attr(ending, "system") if ending is not None else None
                    ),
                    divisions=(
                        _decimal_fraction(audit.attr(child, "divisions"), "barline divisions")
                        if child.get("divisions") is not None
                        else None
                    ),
                    source_id=audit.attr(child, "id"),
                )
            )
        elif tag == "grouping":
            audit.take(child)
            groupings.append(
                TemporalGrouping(
                    onset=cursor,
                    score_onset=score_onset + cursor,
                    grouping_type=audit.attr(child, "type") or "",
                    number=audit.attr(child, "number") or "1",
                    member_of=audit.attr(child, "member-of"),
                    features=tuple(
                        TemporalFeature(
                            value=audit.value(feature) or "",
                            feature_type=audit.attr(feature, "type"),
                        )
                        for feature in audit.children(child, "feature")
                    ),
                    source_order=order,
                    source_id=audit.attr(child, "id"),
                )
            )
        elif tag == "print":
            audit.take(child)
        elif tag == "direction":
            sound = audit.child(child, "sound")
            if sound is not None:
                sound_has_offset = audit.child(sound, "offset") is not None
                direction_onset = cursor
                if not sound_has_offset:
                    direction_offset = audit.child_value(child, "offset")
                    if direction_offset is not None:
                        if divisions is None or divisions <= 0:
                            raise TemporalMappingError("direction sound offset before divisions")
                        direction_onset += (
                            _decimal_fraction(direction_offset, "direction sound offset")
                            / divisions
                        )
                sounds.append(
                    map_sound(
                        sound,
                        audit,
                        onset=direction_onset,
                        score_onset=score_onset,
                        divisions=divisions,
                        source_order=order,
                    )
                )
            mapped_directions, mapped_spans = map_direction(
                child,
                audit,
                part_id=part_id,
                measure_id=f"{part_id}:m{ordinal}",
                onset=cursor,
                score_onset=score_onset,
                divisions=divisions,
                source_order=order,
            )
            directions.extend(mapped_directions)
            time_span_markers.extend(mapped_spans)
            staves.update(
                item.anchor.staff for item in mapped_directions if item.anchor.staff is not None
            )
            voices.update(
                item.anchor.voice for item in mapped_directions if item.anchor.voice is not None
            )
            staves.update(
                item.anchor.staff for item in mapped_spans if item.anchor.staff is not None
            )
            voices.update(
                item.anchor.voice for item in mapped_spans if item.anchor.voice is not None
            )
        elif tag == "sound":
            sounds.append(
                map_sound(
                    child,
                    audit,
                    onset=cursor,
                    score_onset=score_onset,
                    divisions=divisions,
                    source_order=order,
                )
            )
        elif tag == "link":
            links.append(map_link(child, audit))
        elif tag == "bookmark":
            bookmarks.append(map_bookmark(child, audit))
        elif tag == "harmony":
            harmony = map_harmony(
                child,
                audit,
                part_id=part_id,
                measure_id=f"{part_id}:m{ordinal}",
                onset=cursor,
                score_onset=score_onset,
                divisions=divisions,
                source_order=order,
            )
            harmonies.append(harmony)
            if harmony.anchor.staff is not None:
                staves.add(harmony.anchor.staff)
        elif tag == "figured-bass":
            pending_bass.append((child, order, cursor, divisions))
    changes = sorted(
        (
            (attribute.onset, attribute.source_order, transposition)
            for attribute in attributes
            for transposition in attribute.transpositions
        ),
        key=lambda item: (item[0], item[1]),
    )

    def apply_change(
        state: dict[str | None, TemporalTransposition], change: TemporalTransposition
    ) -> None:
        if change.staff is None:
            state.clear()
        state[change.staff] = change

    resolved: list[TemporalEvent] = []
    for event in events:
        state = initial_transpositions.copy()
        for onset, _order, change in changes:
            if onset > event.onset:
                break
            apply_change(state, change)
        transposition = state.get(event.staff, state.get(None))
        sounding = (
            resolve_sounding_pitches(event.pitch, transposition)
            if event.kind == "pitched" and event.pitch is not None
            else ()
        )
        resolved.append(
            replace(
                event,
                score_onset=score_onset + event.onset,
                sounding_pitches=sounding,
            )
        )
    semantic_indices = sorted(
        range(len(resolved)),
        key=lambda index: (
            resolved[index].onset,
            resolved[index].staff,
            resolved[index].voice,
            resolved[index].source_order,
        ),
    )
    for semantic_order, index in enumerate(semantic_indices, start=1):
        resolved[index] = replace(resolved[index], semantic_order=semantic_order)

    figured_bass: list[FiguredBassAnnotation] = []
    for source, source_order, location, source_divisions in pending_bass:
        candidates = [
            event
            for event in resolved
            if event.onset >= location
            and not event.grace
            and (event.chord_id is None or event.chord_id == event.id)
        ]
        if not candidates:
            continue
        earliest = min(event.onset for event in candidates)
        first = [event for event in candidates if event.onset == earliest]
        if len(first) != 1:
            continue
        event = first[0]
        mapped_bass = map_figured_bass(
            source,
            audit,
            anchor=EventAnchor(
                part_id,
                f"{part_id}:m{ordinal}",
                event.id,
                event.staff,
                event.voice,
                event.score_onset,
            ),
            divisions=source_divisions,
            source_order=source_order,
        )
        if mapped_bass is not None:
            figured_bass.append(mapped_bass)

    final_transpositions = initial_transpositions.copy()
    for _onset, _order, change in changes:
        apply_change(final_transpositions, change)
    return (
        TemporalMeasure(
            number,
            ordinal,
            implicit,
            extent,
            tuple(sorted(staves)),
            tuple(sorted(voices)),
            tuple(attributes),
            tuple(resolved),
            tuple(moves),
            tuple(barlines),
            score_onset,
            non_controlling,
            f"{part_id}:m{ordinal}",
            tuple(harmonies),
            tuple(directions),
            tuple(figured_bass),
            tuple(time_span_markers),
            tuple(groupings),
            layout,
            tuple(sounds),
            tuple(links),
            tuple(bookmarks),
        ),
        divisions,
        final_transpositions,
    )


def map_temporal_score(
    document: ValidatedMusicXmlDocument,
    *,
    id_namespace: str | None = None,
) -> TemporalReadResult:
    """Map temporal score facts; retain an audit of every deferred subtree/attribute."""

    if document.kind not in {DocumentKind.SCORE_PARTWISE, DocumentKind.SCORE_TIMEWISE}:
        raise TemporalMappingError(f"{document.kind.value} is not a score document")
    root = document.root
    audit = _Audit()
    audit.take(root)
    audit.attr(root, "version")
    schema_location = audit.attr(
        root,
        "{http://www.w3.org/2001/XMLSchema-instance}noNamespaceSchemaLocation",
    )
    work = audit.child(root, "work")
    work_opus_element = audit.child(work, "opus") if work is not None else None
    work_opus = map_link(work_opus_element, audit) if work_opus_element is not None else None
    work_title = _optional_child_text(work, "work-title", audit)
    movement_title = _optional_child_text(root, "movement-title", audit)
    movement_number = _optional_child_text(root, "movement-number", audit)
    identification = audit.child(root, "identification")
    defaults = audit.child(root, "defaults")
    concert_score = (
        audit.child(defaults, "concert-score") is not None if defaults is not None else False
    )
    metadata = replace(
        _score_metadata(work, identification, audit, concert_score=concert_score),
        schema_location=schema_location,
    )
    score_layout = map_score_layout(root, audit)
    score_links: list[ScopedLink] = []
    score_bookmarks: list[ScopedBookmark] = []
    for credit_index, credit in enumerate(audit.children(root, "credit"), start=1):
        for source_order, item in enumerate(credit, start=1):
            if not isinstance(item.tag, str):
                continue
            tag = etree.QName(item).localname
            if tag == "link":
                score_links.append(
                    ScopedLink(f"credit:{credit_index}", source_order, map_link(item, audit))
                )
            elif tag == "bookmark":
                score_bookmarks.append(
                    ScopedBookmark(
                        f"credit:{credit_index}", source_order, map_bookmark(item, audit)
                    )
                )
    creators = tuple(
        (audit.attr(creator, "type"), audit.value(creator) or "")
        for creator in (
            audit.children(identification, "creator") if identification is not None else ()
        )
    )
    part_list = audit.child(root, "part-list")
    if part_list is None:
        raise TemporalMappingError("score has no part-list")
    groups: list[TemporalPartGroup] = []
    definitions: dict[
        str,
        tuple[
            str | None,
            str | None,
            tuple[TemporalInstrument, ...],
            tuple[str, ...],
            TemporalScoreMetadata,
            tuple[Player, ...],
            tuple[PartLink, ...],
            bool | None,
            bool | None,
            NameDisplay | None,
            NameDisplay | None,
        ],
    ] = {}
    for index, item in enumerate(part_list, start=1):
        tag = etree.QName(item).localname
        if tag == "part-group":
            audit.take(item)
            groups.append(
                TemporalPartGroup(
                    number=audit.attr(item, "number") or "1",
                    action=audit.attr(item, "type") or "",
                    name=audit.child_value(item, "group-name"),
                    abbreviation=audit.child_value(item, "group-abbreviation"),
                    symbol=audit.child_value(item, "group-symbol"),
                    barline=audit.child_value(item, "group-barline"),
                    source_order=index,
                    group_time=audit.child(item, "group-time") is not None,
                    source_id=audit.attr(item, "id"),
                    editorial=_editorial(item, audit),
                    name_display=map_name_display(audit.child(item, "group-name-display"), audit),
                    abbreviation_display=map_name_display(
                        audit.child(item, "group-abbreviation-display"), audit
                    ),
                )
            )
        elif tag == "score-part":
            audit.take(item)
            part_id = audit.attr(item, "id")
            if not part_id or part_id in definitions:
                raise TemporalMappingError("missing or duplicate score-part id")
            devices = tuple(
                map_midi_device(device, audit) for device in audit.children(item, "midi-device")
            )
            midi = tuple(
                map_midi_instrument(instrument, audit)
                for instrument in audit.children(item, "midi-instrument")
            )
            players = tuple(
                Player(
                    id=audit.attr(player, "id") or "",
                    name=audit.child_value(player, "player-name") or "",
                )
                for player in audit.children(item, "player")
            )
            part_links = tuple(
                map_part_link(link, audit) for link in audit.children(item, "part-link")
            )
            name_element = audit.child(item, "part-name")
            abbreviation_element = audit.child(item, "part-abbreviation")
            name_display = map_name_display(audit.child(item, "part-name-display"), audit)
            abbreviation_display = map_name_display(
                audit.child(item, "part-abbreviation-display"), audit
            )
            instruments_list: list[TemporalInstrument] = []
            for instrument in audit.children(item, "score-instrument"):
                solo = audit.child(instrument, "solo") is not None
                ensemble_element = audit.child(instrument, "ensemble")
                ensemble_text = audit.value(ensemble_element)
                instruments_list.append(
                    TemporalInstrument(
                        id=audit.attr(instrument, "id") or "",
                        name=_optional_child_text(instrument, "instrument-name", audit),
                        abbreviation=_optional_child_text(
                            instrument, "instrument-abbreviation", audit
                        ),
                        sound=audit.child_value(instrument, "instrument-sound"),
                        solo=solo,
                        ensemble=ensemble_element is not None,
                        ensemble_size=(
                            _positive(_integer(ensemble_text, "ensemble size"), "ensemble size")
                            if ensemble_text
                            else None
                        ),
                        playback=InstrumentPlayback(
                            devices=tuple(
                                device
                                for device in devices
                                if device.instrument_id in {None, audit.attr(instrument, "id")}
                            ),
                            midi=tuple(
                                value
                                for value in midi
                                if value.instrument_id == audit.attr(instrument, "id")
                            ),
                            virtual=map_virtual_instrument(
                                audit.child(instrument, "virtual-instrument"), audit
                            ),
                        ),
                    )
                )
            instruments = tuple(instruments_list)
            part_identification = audit.child(item, "identification")
            part_groups = tuple(audit.value(group) or "" for group in audit.children(item, "group"))
            definitions[part_id] = (
                _present_text(name_element, audit),
                _present_text(abbreviation_element, audit),
                instruments,
                part_groups,
                _score_metadata(None, part_identification, audit),
                players,
                part_links,
                (
                    _yes_no(audit.attr(name_element, "print-object"), "part-name print-object")
                    if name_element is not None
                    else None
                ),
                (
                    _yes_no(
                        audit.attr(abbreviation_element, "print-object"),
                        "part-abbreviation print-object",
                    )
                    if abbreviation_element is not None
                    else None
                ),
                name_display,
                abbreviation_display,
            )
    frames: dict[str, list[etree._Element]] = {part_id: [] for part_id in definitions}
    if document.kind is DocumentKind.SCORE_PARTWISE:
        encountered_parts: set[str] = set()
        for part in audit.children(root, "part"):
            part_id = audit.attr(part, "id")
            if not part_id:
                raise TemporalMappingError("part body has no id")
            if part_id not in frames:
                # XSD-valid historical files may contain body parts omitted
                # from part-list. Preserve them with explicitly absent list
                # metadata instead of silently dropping their music.
                definitions[part_id] = (
                    None,
                    None,
                    (),
                    (),
                    TemporalScoreMetadata(),
                    (),
                    (),
                    None,
                    None,
                    None,
                    None,
                )
                frames[part_id] = []
            if part_id in encountered_parts:
                raise TemporalMappingError(f"duplicate part body: {part_id}")
            encountered_parts.add(part_id)
            frames[part_id].extend(audit.children(part, "measure"))
    else:
        for measure in audit.children(root, "measure"):
            audit.attr(measure, "number")
            audit.attr(measure, "implicit")
            audit.attr(measure, "non-controlling")
            seen_in_measure: set[str] = set()
            for part in audit.children(measure, "part"):
                part_id = audit.attr(part, "id")
                if part_id not in frames:
                    raise TemporalMappingError(f"undeclared part: {part_id}")
                if part_id in seen_in_measure:
                    raise TemporalMappingError(f"duplicate part in timewise measure: {part_id}")
                seen_in_measure.add(part_id)
                frames[part_id].append(part)
    if any(not measures for measures in frames.values()):
        raise TemporalMappingError("declared score-part has no measure body")
    parts: list[TemporalPart] = []
    for source_part_id, (
        name,
        abbreviation,
        instruments,
        part_groups,
        part_metadata,
        players,
        part_links,
        name_print_object,
        abbreviation_print_object,
        name_display,
        abbreviation_display,
    ) in definitions.items():
        part_id = f"{id_namespace}:{source_part_id}" if id_namespace is not None else source_part_id
        measures_list: list[TemporalMeasure] = []
        divisions: int | None = None
        transpositions: dict[str | None, TemporalTransposition] = {}
        score_onset = Fraction(0)
        for ordinal, measure in enumerate(frames[source_part_id], start=1):
            mapped, divisions, transpositions = _measure(
                measure,
                audit,
                part_id,
                ordinal,
                divisions,
                score_onset,
                transpositions,
                frozenset(instrument.id for instrument in instruments),
            )
            measures_list.append(mapped)
            score_onset += mapped.extent
        measures = tuple(measures_list)
        staff_numbers = sorted({staff for measure in measures for staff in measure.staves})
        voice_numbers = sorted({voice for measure in measures for voice in measure.voices})
        parts.append(
            TemporalPart(
                part_id,
                name,
                abbreviation,
                instruments,
                measures,
                tuple(
                    TemporalStaff(f"{part_id}:staff:{number}", number) for number in staff_numbers
                ),
                tuple(
                    TemporalVoice(f"{part_id}:voice:{number}", number) for number in voice_numbers
                ),
                part_groups,
                part_metadata,
                players,
                part_links,
                name_print_object,
                abbreviation_print_object,
                name_display,
                abbreviation_display,
            )
        )
    alignment_members: dict[Fraction, list[tuple[str, int]]] = {}
    for temporal_part in parts:
        for temporal_measure in temporal_part.measures:
            if not temporal_measure.non_controlling:
                alignment_members.setdefault(temporal_measure.score_onset, []).append(
                    (temporal_part.id, temporal_measure.ordinal)
                )
    alignments = tuple(
        TemporalAlignment(onset, tuple(members))
        for onset, members in sorted(alignment_members.items())
    )
    try:
        annotation_graph = resolve_annotation_graph(tuple(parts), metadata)
    except AnnotationGraphError as error:
        raise TemporalMappingError(str(error)) from error
    source_presentations = audit.presentation_records(root)
    return TemporalReadResult(
        source_sha256=document.artifact.sha256,
        source_format=document.artifact.media_type.value,
        musicxml_version=document.standard_version,
        document_form=document.kind.value,
        score=TemporalScore(
            work_title,
            movement_title,
            movement_number,
            creators,
            tuple(groups),
            tuple(parts),
            alignments,
            annotation_graph,
            metadata,
            score_layout,
            tuple(score_links),
            tuple(score_bookmarks),
            work_opus,
            source_presentations,
        ),
        deferred=audit.deferred(root),
    )
