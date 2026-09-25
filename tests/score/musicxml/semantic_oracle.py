"""Independent MusicXML semantic oracle used only for conformance tests.

This module intentionally does not import the production MusicXML boundary or
mapper.  It reads the fixture bytes with the Python standard library and
derives bounded, independently implemented semantic projections. Agreement
with the canonical projection is therefore useful evidence rather than a
comparison of the mapper with itself.
"""

from __future__ import annotations

import hashlib
import re
import xml.etree.ElementTree as element_tree
from dataclasses import dataclass, replace
from fractions import Fraction
from io import BytesIO
from zipfile import ZipFile

from teachmemusic.score.v2.auxiliary import AuxiliaryDocument, OpusCatalog, OpusItem, SoundCatalog
from teachmemusic.score.v2.documents import (
    CanonicalMusicPackage,
    ScoreDocument,
    TemporalScoreContent,
)
from teachmemusic.score.v2.temporal import TemporalReadResult

type OracleValue = str | int | bool | Fraction | None | tuple[OracleValue, ...]


@dataclass(frozen=True, slots=True)
class OracleSemanticRecord:
    """One ordered semantic fact set compared independently of the mapper."""

    scope: tuple[str, ...]
    kind: str
    facts: tuple[tuple[str, OracleValue], ...]


@dataclass(frozen=True, slots=True)
class OracleEvent:
    part_id: str
    measure_ordinal: int
    measure_number: str
    event_ordinal: int
    kind: str
    onset: Fraction
    duration: Fraction
    staff: str
    voice: str
    pitch: tuple[str, Fraction, int] | None
    chord_group: int | None
    grace: bool
    cue: bool
    written_type: str | None
    dots: int
    time_modification: tuple[int, int] | None


@dataclass(frozen=True, slots=True)
class OracleMeasure:
    part_id: str
    ordinal: int
    number: str
    extent: Fraction
    event_count: int


@dataclass(frozen=True, slots=True)
class OracleReadProvenance:
    """Source identity facts exposed by the public temporal read result."""

    source_sha256: str
    source_format: str
    musicxml_version: str
    document_form: str


@dataclass(frozen=True, slots=True)
class OraclePackageFacts:
    """Existing public temporal-package facts, without claiming R4 integration."""

    schema_id: str
    schema_version: str
    package_id: tuple[str, str]
    document_id: tuple[str, str]
    source_documents: tuple[tuple[str, str], ...]
    root_documents: tuple[tuple[str, str], ...]
    completeness: str
    source: tuple[OracleValue, ...]
    source_map: tuple[OracleValue, ...]


@dataclass(frozen=True, slots=True)
class OracleAuxiliary:
    """Independent primitive projection of an opus or sound catalog."""

    kind: str
    version: str
    title: str | None
    items: tuple[OracleValue, ...]


@dataclass(frozen=True, slots=True)
class OracleScore:
    part_ids: tuple[str, ...]
    measures: tuple[OracleMeasure, ...]
    events: tuple[OracleEvent, ...]
    metadata: tuple[OracleSemanticRecord, ...]
    attributes: tuple[OracleSemanticRecord, ...]
    barlines: tuple[OracleSemanticRecord, ...]
    span_endpoints: tuple[OracleSemanticRecord, ...]
    event_marks: tuple[OracleSemanticRecord, ...]
    directions: tuple[OracleSemanticRecord, ...]
    time_span_endpoints: tuple[OracleSemanticRecord, ...]
    notation_spans: tuple[OracleSemanticRecord, ...]
    time_spans: tuple[OracleSemanticRecord, ...]
    lyrics: tuple[OracleSemanticRecord, ...]
    harmonies: tuple[OracleSemanticRecord, ...]
    figured_bass: tuple[OracleSemanticRecord, ...]
    layouts: tuple[OracleSemanticRecord, ...]
    presentations: tuple[OracleSemanticRecord, ...]
    playback: tuple[OracleSemanticRecord, ...]
    links: tuple[OracleSemanticRecord, ...]
    provenance: OracleReadProvenance


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _children(element: element_tree.Element, name: str) -> tuple[element_tree.Element, ...]:
    return tuple(child for child in element if _local_name(child.tag) == name)


def _child(element: element_tree.Element, name: str) -> element_tree.Element | None:
    return next((child for child in element if _local_name(child.tag) == name), None)


def _text(element: element_tree.Element, name: str) -> str | None:
    child = _child(element, name)
    return child.text.strip() if child is not None and child.text is not None else None


def _value(element: element_tree.Element | None) -> str | None:
    """Return present element text, preserving the present-empty distinction."""

    if element is None:
        return None
    return element.text if element.text is not None else ""


def _child_value(element: element_tree.Element | None, name: str) -> str | None:
    return _value(_child(element, name)) if element is not None else None


def _yes_no(value: str | None) -> bool | None:
    if value is None:
        return None
    if value not in {"yes", "no"}:
        raise ValueError(f"oracle expected yes/no, got {value}")
    return value == "yes"


def _integer(value: str | None, *, default: int | None = None) -> int | None:
    return default if value is None else int(value)


def _fraction(value: str | None, *, default: Fraction | None = None) -> Fraction | None:
    return default if value is None else Fraction(value)


def _record(scope: tuple[str, ...], kind: str, **facts: OracleValue) -> OracleSemanticRecord:
    return OracleSemanticRecord(scope, kind, tuple(facts.items()))


_STYLE_ATTRIBUTES = (
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
    "{http://www.w3.org/XML/1998/namespace}lang",
    "{http://www.w3.org/XML/1998/namespace}space",
)
_PRESENTATION_KEYWORDS = {
    "normal",
    "xx-small",
    "x-small",
    "small",
    "medium",
    "large",
    "x-large",
    "xx-large",
}


def _presentation_number(value: str | None) -> OracleValue:
    if value is None:
        return None
    return (None, value) if value in _PRESENTATION_KEYWORDS else (Fraction(value), None)


def _source_presentation(element: element_tree.Element | None) -> OracleValue:
    if element is None or not any(element.get(name) is not None for name in _STYLE_ATTRIBUTES):
        return None
    return (
        _fraction(element.get("default-x")),
        _fraction(element.get("default-y")),
        _fraction(element.get("relative-x")),
        _fraction(element.get("relative-y")),
        element.get("color"),
        element.get("font-family"),
        element.get("font-style"),
        _presentation_number(element.get("font-size")),
        element.get("font-weight"),
        element.get("justify"),
        element.get("halign"),
        element.get("valign"),
        element.get("enclosure"),
        _presentation_number(element.get("letter-spacing")),
        _presentation_number(element.get("line-height")),
        _integer(element.get("underline")),
        _integer(element.get("overline")),
        _integer(element.get("line-through")),
        _fraction(element.get("rotation")),
        element.get("dir"),
        element.get("{http://www.w3.org/XML/1998/namespace}lang"),
        element.get("{http://www.w3.org/XML/1998/namespace}space"),
    )


def _canonical_presentation(value: object | None) -> OracleValue:
    if value is None:
        return None

    def number(item: object | None) -> OracleValue:
        return None if item is None else (item.number, item.keyword)  # type: ignore[attr-defined]

    return (
        value.default_x,  # type: ignore[attr-defined]
        value.default_y,  # type: ignore[attr-defined]
        value.relative_x,  # type: ignore[attr-defined]
        value.relative_y,  # type: ignore[attr-defined]
        value.color,  # type: ignore[attr-defined]
        value.font_family,  # type: ignore[attr-defined]
        value.font_style,  # type: ignore[attr-defined]
        number(value.font_size),  # type: ignore[attr-defined]
        value.font_weight,  # type: ignore[attr-defined]
        value.justify,  # type: ignore[attr-defined]
        value.halign,  # type: ignore[attr-defined]
        value.valign,  # type: ignore[attr-defined]
        value.enclosure,  # type: ignore[attr-defined]
        number(value.letter_spacing),  # type: ignore[attr-defined]
        number(value.line_height),  # type: ignore[attr-defined]
        value.underline,  # type: ignore[attr-defined]
        value.overline,  # type: ignore[attr-defined]
        value.line_through,  # type: ignore[attr-defined]
        value.rotation,  # type: ignore[attr-defined]
        value.text_direction,  # type: ignore[attr-defined]
        value.language,  # type: ignore[attr-defined]
        value.space,  # type: ignore[attr-defined]
    )


def _source_event_presentations(
    note: element_tree.Element,
    *,
    part_id: str,
    measure_ordinal: int,
    source_order: int,
) -> tuple[OracleSemanticRecord, ...]:
    event_id = f"{part_id}:m{measure_ordinal}:n{source_order}"
    scope = ("part", part_id, "measure", str(measure_ordinal), "event", event_id)
    records: list[OracleSemanticRecord] = []
    style = _source_presentation(note)
    if style is not None:
        records.append(_record(scope, "presentation", owner="note", source_order=0, style=style))
    for index, accidental in enumerate(_children(note, "accidental"), start=1):
        style = _source_presentation(accidental)
        if style is not None:
            records.append(
                _record(
                    scope,
                    "presentation",
                    owner="accidental",
                    source_order=index,
                    style=style,
                )
            )
    return tuple(records)


def _canonical_event_presentations(
    event: object, *, part_id: str, measure_ordinal: int
) -> tuple[OracleSemanticRecord, ...]:
    scope = (
        "part",
        part_id,
        "measure",
        str(measure_ordinal),
        "event",
        event.id,  # type: ignore[attr-defined]
    )
    records: list[OracleSemanticRecord] = []
    style = _canonical_presentation(event.presentation)  # type: ignore[attr-defined]
    if style is not None:
        records.append(_record(scope, "presentation", owner="note", source_order=0, style=style))
    for index, accidental in enumerate(event.accidentals, start=1):  # type: ignore[attr-defined]
        style = _canonical_presentation(accidental.presentation)
        if style is not None:
            records.append(
                _record(
                    scope,
                    "presentation",
                    owner="accidental",
                    source_order=index,
                    style=style,
                )
            )
    return tuple(records)


def _source_paths(
    root: element_tree.Element,
) -> tuple[tuple[element_tree.Element, element_tree.Element | None, str], ...]:
    records: list[tuple[element_tree.Element, element_tree.Element | None, str]] = []

    def visit(
        element: element_tree.Element, parent: element_tree.Element | None, path: str
    ) -> None:
        records.append((element, parent, path))
        children = [child for child in element if isinstance(child.tag, str)]
        totals: dict[str, int] = {}
        for child in children:
            name = _local_name(child.tag)
            totals[name] = totals.get(name, 0) + 1
        seen: dict[str, int] = {}
        for child in children:
            name = _local_name(child.tag)
            seen[name] = seen.get(name, 0) + 1
            suffix = f"[{seen[name]}]" if totals[name] > 1 else ""
            visit(child, element, f"{path}/{name}{suffix}")

    visit(root, None, f"/{_local_name(root.tag)}")
    return tuple(records)


def _semantic_source_path(path: str) -> str:
    if path.startswith("/score-partwise/part/measure"):
        return path.replace("/score-partwise/part/measure", "/score/part/measure", 1)
    prefix = "/score-timewise/"
    if not path.startswith(prefix):
        return path
    measure, separator, remainder = path[len(prefix) :].partition("/part")
    if not separator:
        return path.replace("/score-timewise", "/score", 1)
    return f"/score/part/{measure}{remainder}"


def _style_is_owned(element: element_tree.Element, parent: element_tree.Element | None) -> bool:
    kind = _local_name(element.tag)
    if kind in {
        "note",
        "accidental",
        "line-detail",
        "part-symbol",
        "music-font",
        "word-font",
        "lyric-font",
        "credit-words",
        "credit-symbol",
        "credit-image",
        "link",
        "display-text",
        "accidental-text",
    }:
        return True
    if kind == "dynamics":
        return True
    if parent is None or _local_name(parent.tag) != "direction-type":
        return False
    if kind in {
        "words",
        "rehearsal",
        "segno",
        "coda",
        "symbol",
        "damp",
        "damp-all",
        "eyeglasses",
        "string-mute",
        "staff-divide",
        "other-direction",
        "metronome",
        "harp-pedals",
        "scordatura",
        "accordion-registration",
        "principal-voice",
        "percussion",
        "image",
    }:
        return True
    if kind != "pedal":
        return False
    return (
        element.get("type") in {"start", "sostenuto", "stop"}
        and element.get("line") != "yes"
        and element.get("sign") != "no"
    )


def _source_residual_presentations(
    root: element_tree.Element,
) -> tuple[OracleSemanticRecord, ...]:
    records = []
    for element, parent, path in _source_paths(root):
        style = _source_presentation(element)
        if style is None or _style_is_owned(element, parent):
            continue
        records.append(
            _record(
                ("source", _semantic_source_path(path)),
                "source-presentation",
                element_name=_local_name(element.tag),
                style=style,
            )
        )
    return tuple(sorted(records, key=lambda item: item.scope[1]))


def _canonical_residual_presentations(
    result: TemporalReadResult,
) -> tuple[OracleSemanticRecord, ...]:
    return tuple(
        _record(
            ("source", _semantic_source_path(item.source_path)),
            "source-presentation",
            element_name=item.element_name,
            style=_canonical_presentation(item.style),
        )
        for item in result.score.source_presentations
    )


def _source_margins(element: element_tree.Element, *, page: bool) -> OracleValue:
    return (
        element.get("type") if page else None,
        _fraction(_child_value(element, "left-margin"), default=Fraction(0)),
        _fraction(_child_value(element, "right-margin"), default=Fraction(0)),
        _fraction(_child_value(element, "top-margin")) if page else None,
        _fraction(_child_value(element, "bottom-margin")) if page else None,
    )


def _source_page_layout(element: element_tree.Element | None) -> OracleValue:
    if element is None:
        return None
    return (
        _fraction(_child_value(element, "page-height")),
        _fraction(_child_value(element, "page-width")),
        tuple(_source_margins(item, page=True) for item in _children(element, "page-margins")),
    )


def _source_system_layout(element: element_tree.Element | None) -> OracleValue:
    if element is None:
        return None
    margins = _child(element, "system-margins")
    return (
        _source_margins(margins, page=False) if margins is not None else None,
        _fraction(_child_value(element, "system-distance")),
        _fraction(_child_value(element, "top-system-distance")),
    )


def _source_staff_layout(element: element_tree.Element) -> OracleValue:
    return (element.get("number"), _fraction(_child_value(element, "staff-distance")))


def _source_name_display(element: element_tree.Element | None) -> OracleValue:
    if element is None:
        return None
    return tuple(
        (_local_name(item.tag), _value(item) or "", _source_presentation(item))
        for item in element
        if isinstance(item.tag, str)
        and _local_name(item.tag) in {"display-text", "accidental-text"}
    )


def _source_score_layout(root: element_tree.Element) -> tuple[OracleSemanticRecord, ...]:
    defaults = _child(root, "defaults")
    credits = _children(root, "credit")
    if defaults is None and not credits:
        return ()
    defaults_value: OracleValue = None
    if defaults is not None:
        scaling = _child(defaults, "scaling")
        appearance = _child(defaults, "appearance")
        defaults_value = (
            (
                _fraction(_child_value(scaling, "millimeters")),
                _fraction(_child_value(scaling, "tenths")),
            )
            if scaling is not None
            else None,
            _source_page_layout(_child(defaults, "page-layout")),
            _source_system_layout(_child(defaults, "system-layout")),
            tuple(_source_staff_layout(item) for item in _children(defaults, "staff-layout")),
            tuple(
                (
                    _local_name(item.tag),
                    item.get("type") or "",
                    _fraction(_value(item))
                    if _local_name(item.tag) != "other-appearance"
                    else None,
                    _value(item) if _local_name(item.tag) == "other-appearance" else None,
                )
                for item in (appearance if appearance is not None else ())
                if isinstance(item.tag, str)
            ),
            _source_presentation(_child(defaults, "music-font")),
            _source_presentation(_child(defaults, "word-font")),
            tuple(
                (item.get("number"), item.get("name"), _source_presentation(item))
                for item in _children(defaults, "lyric-font")
                if _source_presentation(item) is not None
            ),
            tuple(
                (
                    item.get("number"),
                    item.get("name"),
                    item.get("{http://www.w3.org/XML/1998/namespace}lang") or "",
                )
                for item in _children(defaults, "lyric-language")
            ),
        )
    credit_values: list[OracleValue] = []
    for credit in credits:
        items: list[OracleValue] = []
        for item in credit:
            kind = _local_name(item.tag)
            if kind in {"credit-words", "credit-symbol"}:
                items.append(
                    (
                        "words" if kind == "credit-words" else "symbol",
                        _value(item) or "",
                        _source_presentation(item),
                        None,
                        None,
                        None,
                        item.get("id"),
                    )
                )
            elif kind == "credit-image":
                items.append(
                    (
                        "image",
                        item.get("source") or "",
                        _source_presentation(item),
                        item.get("type"),
                        _fraction(item.get("width")),
                        _fraction(item.get("height")),
                        item.get("id"),
                    )
                )
        credit_values.append(
            (
                _integer(credit.get("page"), default=1),
                tuple(_value(item) or "" for item in _children(credit, "credit-type")),
                tuple(items),
                credit.get("id"),
            )
        )
    return (
        _record(("score",), "score-layout", defaults=defaults_value, credits=tuple(credit_values)),
    )


def _source_measure_layout(
    header: element_tree.Element,
    body: element_tree.Element,
    *,
    part_id: str,
    measure_ordinal: int,
) -> OracleSemanticRecord | None:
    width = _fraction(header.get("width"))
    print_element = _child(body, "print")
    if print_element is None and width is None:
        return None
    measure_layout = _child(print_element, "measure-layout") if print_element is not None else None
    return _record(
        ("part", part_id, "measure", str(measure_ordinal)),
        "measure-layout",
        width=width,
        new_page=_yes_no(print_element.get("new-page")) if print_element is not None else None,
        new_system=(
            _yes_no(print_element.get("new-system")) if print_element is not None else None
        ),
        page_number=print_element.get("page-number") if print_element is not None else None,
        blank_page=(
            _integer(print_element.get("blank-page")) if print_element is not None else None
        ),
        page=(
            _source_page_layout(_child(print_element, "page-layout"))
            if print_element is not None
            else None
        ),
        system=(
            _source_system_layout(_child(print_element, "system-layout"))
            if print_element is not None
            else None
        ),
        staves=(
            tuple(_source_staff_layout(item) for item in _children(print_element, "staff-layout"))
            if print_element is not None
            else ()
        ),
        measure_distance=(
            _fraction(_child_value(measure_layout, "measure-distance"))
            if measure_layout is not None
            else None
        ),
        measure_numbering=(
            _child_value(print_element, "measure-numbering") if print_element is not None else None
        ),
        staff_spacing=(
            _fraction(print_element.get("staff-spacing")) if print_element is not None else None
        ),
        part_name_display=(
            _source_name_display(_child(print_element, "part-name-display"))
            if print_element is not None
            else None
        ),
        part_abbreviation_display=(
            _source_name_display(_child(print_element, "part-abbreviation-display"))
            if print_element is not None
            else None
        ),
    )


def _metadata_facts(
    work: element_tree.Element | None,
    identification: element_tree.Element | None,
    *,
    concert_score: bool = False,
    schema_location: str | None = None,
) -> tuple[tuple[str, OracleValue], ...]:
    encoding = _child(identification, "encoding") if identification is not None else None
    miscellaneous = _child(identification, "miscellaneous") if identification is not None else None
    encoding_value: OracleValue = None
    if encoding is not None:
        encoding_value = (
            tuple(_value(item) or "" for item in _children(encoding, "encoding-date")),
            tuple(
                (_value(item) or "", item.get("type")) for item in _children(encoding, "encoder")
            ),
            tuple(_value(item) or "" for item in _children(encoding, "software")),
            tuple(_value(item) or "" for item in _children(encoding, "encoding-description")),
            tuple(
                (
                    _yes_no(item.get("type")) is True,
                    item.get("element") or "",
                    item.get("attribute"),
                    item.get("value"),
                )
                for item in _children(encoding, "supports")
            ),
        )
    return (
        ("concert_score", concert_score),
        ("work_number", _child_value(work, "work-number")),
        (
            "rights",
            tuple(
                (_value(item) or "", item.get("type"))
                for item in (
                    _children(identification, "rights") if identification is not None else ()
                )
            ),
        ),
        ("source", _child_value(identification, "source")),
        (
            "relations",
            tuple(
                (_value(item) or "", item.get("type"))
                for item in (
                    _children(identification, "relation") if identification is not None else ()
                )
            ),
        ),
        ("encoding", encoding_value),
        (
            "miscellaneous",
            tuple(
                (item.get("name") or "", _value(item) or "")
                for item in (
                    _children(miscellaneous, "miscellaneous-field")
                    if miscellaneous is not None
                    else ()
                )
            ),
        ),
        ("schema_location", schema_location),
    )


def _source_metadata(root: element_tree.Element) -> tuple[OracleSemanticRecord, ...]:
    work = _child(root, "work")
    identification = _child(root, "identification")
    defaults = _child(root, "defaults")
    xsi_schema_location = root.get(
        "{http://www.w3.org/2001/XMLSchema-instance}noNamespaceSchemaLocation"
    )
    records = [
        _record(
            ("score",),
            "score-header",
            work_title=_child_value(work, "work-title"),
            movement_title=_child_value(root, "movement-title"),
            movement_number=_child_value(root, "movement-number"),
            creators=tuple(
                (item.get("type"), _value(item) or "")
                for item in (
                    _children(identification, "creator") if identification is not None else ()
                )
            ),
        ),
        OracleSemanticRecord(
            ("score",),
            "identification",
            _metadata_facts(
                work,
                identification,
                concert_score=defaults is not None
                and _child(defaults, "concert-score") is not None,
                schema_location=xsi_schema_location,
            ),
        ),
    ]
    part_list = _child(root, "part-list")
    definitions = {
        item.get("id", ""): item
        for item in (_children(part_list, "score-part") if part_list is not None else ())
    }
    for part_id, _ in _part_measure_bodies(root):
        definition = definitions.get(part_id)
        part_identification = (
            _child(definition, "identification") if definition is not None else None
        )
        records.append(
            _record(
                ("part", part_id),
                "part-header",
                name=_child_value(definition, "part-name"),
                abbreviation=_child_value(definition, "part-abbreviation"),
            )
        )
        records.append(
            OracleSemanticRecord(
                ("part", part_id),
                "identification",
                _metadata_facts(None, part_identification),
            )
        )
    return tuple(records)


def _transposition_value(element: element_tree.Element, staff: str | None = None) -> OracleValue:
    doubling = _child(element, "double")
    return (
        element.get("number") if staff is None else staff,
        _integer(_child_value(element, "diatonic")),
        _fraction(_child_value(element, "chromatic")),
        _integer(_child_value(element, "octave-change"), default=0),
        _yes_no(doubling.get("above")) if doubling is not None else None,
    )


def _source_attribute_record(
    element: element_tree.Element,
    *,
    part_id: str,
    measure_ordinal: int,
    onset: Fraction,
    source_order: int,
) -> OracleSemanticRecord:
    clefs: OracleValue = tuple(
        (
            clef.get("number") or "1",
            _child_value(clef, "sign") or "",
            _integer(_child_value(clef, "line")),
            _integer(_child_value(clef, "clef-octave-change")),
            _yes_no(clef.get("additional")),
            clef.get("size"),
            _yes_no(clef.get("after-barline")),
            _yes_no(clef.get("print-object")),
            clef.get("id"),
        )
        for clef in _children(element, "clef")
    )
    keys: list[OracleValue] = []
    for key in _children(element, "key"):
        alterations: list[OracleValue] = []
        children = tuple(child for child in key if isinstance(child.tag, str))
        for index, step in enumerate(children):
            if _local_name(step.tag) != "key-step":
                continue
            alter = children[index + 1]
            accidental_items: list[element_tree.Element] = []
            for following in children[index + 2 :]:
                if _local_name(following.tag) != "key-accidental":
                    break
                accidental_items.append(following)
            alterations.append(
                (
                    _value(step) or "",
                    _fraction(_value(alter)),
                    _value(accidental_items[0]) if accidental_items else None,
                    accidental_items[0].get("smufl") if accidental_items else None,
                    tuple((_value(item) or "", item.get("smufl")) for item in accidental_items),
                )
            )
        cancel = _child(key, "cancel")
        keys.append(
            (
                _integer(_child_value(key, "fifths")),
                _child_value(key, "mode"),
                key.get("number"),
                _integer(_value(cancel)),
                cancel.get("location") if cancel is not None else None,
                tuple(alterations),
                tuple(
                    (
                        int(item.get("number", "")),
                        int(_value(item) or ""),
                        _yes_no(item.get("cancel")),
                    )
                    for item in _children(key, "key-octave")
                ),
                _yes_no(key.get("print-object")),
                key.get("id"),
            )
        )
    times: OracleValue = tuple(
        (
            tuple(_value(item) or "" for item in _children(time, "beats")),
            tuple(int(_value(item) or "") for item in _children(time, "beat-type")),
            time.get("symbol"),
            time.get("number"),
            _child_value(time, "senza-misura"),
            time.get("separator"),
            (
                tuple(_value(item) or "" for item in _children(interchangeable, "beats")),
                tuple(int(_value(item) or "") for item in _children(interchangeable, "beat-type")),
                _child_value(interchangeable, "time-relation"),
                interchangeable.get("symbol"),
                interchangeable.get("separator"),
            )
            if (interchangeable := _child(time, "interchangeable")) is not None
            else None,
            _yes_no(time.get("print-object")),
            time.get("id"),
        )
        for time in _children(element, "time")
    )
    measure_styles: list[OracleValue] = []
    for wrapper in _children(element, "measure-style"):
        style = next(child for child in wrapper if isinstance(child.tag, str))
        kind = _local_name(style.tag)
        measure_styles.append(
            (
                wrapper.get("number"),
                kind,
                int(_value(style) or "") if kind in {"multiple-rest", "measure-repeat"} else None,
                style.get("type"),
                _integer(style.get("slashes")),
                _yes_no(style.get("use-symbols")),
                _yes_no(style.get("use-dots")),
                _yes_no(style.get("use-stems")),
                _child_value(style, "slash-type"),
                len(_children(style, "slash-dot")),
                wrapper.get("id"),
            )
        )
    staff_details: OracleValue = tuple(
        (
            details.get("number"),
            _child_value(details, "staff-type"),
            _integer(_child_value(details, "staff-lines")),
            tuple(
                (
                    int(tuning.get("line", "")),
                    _child_value(tuning, "tuning-step") or "",
                    _fraction(_child_value(tuning, "tuning-alter"), default=Fraction(0)),
                    int(_child_value(tuning, "tuning-octave") or ""),
                )
                for tuning in _children(details, "staff-tuning")
            ),
            _integer(_child_value(details, "capo")),
            _fraction(_child_value(details, "staff-size")),
            details.get("show-frets"),
            _yes_no(details.get("print-object")),
            tuple(
                (
                    int(line.get("line", "")),
                    _yes_no(line.get("print-object")),
                    _source_presentation(line),
                )
                for line in _children(details, "line-detail")
            ),
        )
        for details in _children(element, "staff-details")
    )
    part_symbols: OracleValue = tuple(
        (
            _value(item) or "",
            item.get("top-staff"),
            item.get("bottom-staff"),
            _source_presentation(item),
        )
        for item in _children(element, "part-symbol")
    )
    for_parts: list[OracleValue] = []
    for item in _children(element, "for-part"):
        part_clef = _child(item, "part-clef")
        transpose = _child(item, "part-transpose")
        assert transpose is not None
        for_parts.append(
            (
                item.get("number"),
                (
                    _child_value(part_clef, "sign") or "",
                    _integer(_child_value(part_clef, "line")),
                    _integer(_child_value(part_clef, "clef-octave-change")),
                )
                if part_clef is not None
                else None,
                _transposition_value(transpose, item.get("number")),
                item.get("id"),
            )
        )
    directives: OracleValue = tuple(
        (
            _value(item) or "",
            item.get("{http://www.w3.org/XML/1998/namespace}lang"),
            index,
        )
        for index, item in enumerate(element, start=1)
        if isinstance(item.tag, str) and _local_name(item.tag) == "directive"
    )
    return _record(
        ("part", part_id, "measure", str(measure_ordinal)),
        "attributes",
        onset=onset,
        source_order=source_order,
        divisions=_integer(_child_value(element, "divisions")),
        staves=_integer(_child_value(element, "staves")),
        clefs=clefs,
        keys=tuple(keys),
        times=times,
        transpositions=tuple(
            _transposition_value(item) for item in _children(element, "transpose")
        ),
        instrument_count=_integer(_child_value(element, "instruments")),
        measure_styles=tuple(measure_styles),
        staff_details=staff_details,
        part_symbols=part_symbols,
        for_parts=tuple(for_parts),
        directives=directives,
    )


def _source_barline_record(
    element: element_tree.Element,
    *,
    part_id: str,
    measure_ordinal: int,
    onset: Fraction,
    source_order: int,
) -> OracleSemanticRecord:
    repeat = _child(element, "repeat")
    ending = _child(element, "ending")
    navigation: list[OracleValue] = []
    for kind in ("segno", "coda"):
        token = element.get(kind)
        if token is not None:
            navigation.append((kind, token, None, None))
        navigation.extend(
            (kind, _value(item), item.get("id"), item.get("smufl"))
            for item in _children(element, kind)
        )
    return _record(
        ("part", part_id, "measure", str(measure_ordinal)),
        "barline",
        onset=onset,
        source_order=source_order,
        location=element.get("location"),
        style=_child_value(element, "bar-style"),
        repeat_direction=repeat.get("direction") if repeat is not None else None,
        repeat_times=repeat.get("times") if repeat is not None else None,
        ending_number=ending.get("number") if ending is not None else None,
        ending_type=ending.get("type") if ending is not None else None,
        fermatas=tuple(
            (_value(item), item.get("type"), item.get("id"))
            for item in _children(element, "fermata")
        ),
        navigation=tuple(navigation),
        repeat_winged=repeat.get("winged") if repeat is not None else None,
        repeat_after_jump=(_yes_no(repeat.get("after-jump")) if repeat is not None else None),
        ending_text=_value(ending),
        ending_print_object=(_yes_no(ending.get("print-object")) if ending is not None else None),
        ending_system_relation=ending.get("system") if ending is not None else None,
        divisions=_fraction(element.get("divisions")),
        source_id=element.get("id"),
    )


def _trill_playback_value(element: element_tree.Element) -> OracleValue:
    values = (
        element.get("start-note"),
        element.get("trill-step"),
        element.get("two-note-turn"),
        element.get("accelerate"),
        element.get("beats"),
        element.get("second-beat"),
        element.get("last-beat"),
    )
    if all(value is None for value in values):
        return None
    return (
        values[0],
        values[1],
        values[2],
        _yes_no(values[3]),
        _fraction(values[4]),
        _fraction(values[5]),
        _fraction(values[6]),
    )


def _bend_sound_value(element: element_tree.Element) -> OracleValue:
    values = (
        element.get("accelerate"),
        element.get("beats"),
        element.get("first-beat"),
        element.get("last-beat"),
    )
    if all(value is None for value in values):
        return None
    return (
        _yes_no(values[0]),
        _fraction(values[1]),
        _fraction(values[2]),
        _fraction(values[3]),
    )


def _source_span_record(
    scope: tuple[str, ...],
    anchor: OracleValue,
    *,
    kind: str,
    number: str,
    action: str,
    source_order: int,
    element: element_tree.Element,
    pitch: OracleValue,
    playback: OracleValue = None,
    tremolo_marks: int | None = None,
    text: str | None = None,
    line_type: str | None = None,
    bend_sound: OracleValue = None,
    time_only: str | None = None,
) -> OracleSemanticRecord:
    return _record(
        scope,
        "span-endpoint",
        anchor=anchor,
        pitch=pitch,
        span_kind=kind,
        number=number,
        action=action,
        source_order=source_order,
        placement=element.get("placement"),
        smufl=element.get("smufl"),
        playback=playback,
        tremolo_marks=tremolo_marks,
        accidentals=(),
        text=text,
        source_id=element.get("id"),
        line_type=line_type,
        bend_sound=bend_sound,
        print_object=_yes_no(element.get("print-object")),
        orientation=element.get("orientation"),
        dash_length=_fraction(element.get("dash-length")),
        space_length=_fraction(element.get("space-length")),
        time_only=time_only,
    )


def _source_event_mark_record(
    scope: tuple[str, ...],
    anchor: OracleValue,
    *,
    family: str,
    kind: str,
    source_order: int,
    element: element_tree.Element,
    group_id: str | None = None,
    group_placement: str | None = None,
) -> OracleSemanticRecord:
    is_fermata = kind == "fermata"
    is_arpeggiation = kind in {"arpeggiate", "non-arpeggiate"}
    return _record(
        scope,
        "event-mark",
        anchor=anchor,
        family=family,
        mark_kind=kind,
        text=element.text if is_fermata or not len(element) else None,
        source_order=source_order,
        group_id=group_id if not is_arpeggiation else element.get("id"),
        placement=group_placement or element.get("placement"),
        mark_type=(
            element.get("type")
            if kind in {"fermata", "non-arpeggiate"}
            else element.get("direction")
            if kind == "arpeggiate"
            else None
        ),
        smufl=element.get("smufl"),
        line_shape=element.get("line-shape"),
        line_type=element.get("line-type"),
        playback=None,
        slash=None,
        long=None,
        approach=None,
        departure=None,
        tremolo_marks=None,
        bracket=None,
        parentheses=None,
        accidentals=(),
        technical=None,
        number=element.get("number") if is_arpeggiation else None,
        print_object=None,
        unbroken=_yes_no(element.get("unbroken")) if kind == "arpeggiate" else None,
    )


def _source_note_annotations(
    note: element_tree.Element,
    *,
    part_id: str,
    measure_ordinal: int,
    source_order: int,
    onset: Fraction,
    score_onset: Fraction,
    staff: str,
    voice: str,
    pitch: OracleValue,
) -> tuple[tuple[OracleSemanticRecord, ...], tuple[OracleSemanticRecord, ...]]:
    event_id = f"{part_id}:m{measure_ordinal}:n{source_order}"
    scope = ("part", part_id, "measure", str(measure_ordinal), "event", event_id)
    anchor: OracleValue = (
        part_id,
        f"{part_id}:m{measure_ordinal}",
        event_id,
        staff,
        voice,
        score_onset + onset,
    )
    spans: list[OracleSemanticRecord] = []
    marks: list[OracleSemanticRecord] = []
    for tie in _children(note, "tie"):
        spans.append(
            _source_span_record(
                scope,
                anchor,
                kind="sounding-tie",
                number="1",
                action=tie.get("type") or "",
                source_order=len(spans) + 1,
                element=tie,
                pitch=pitch,
                time_only=tie.get("time-only"),
            )
        )
    notations_elements = _children(note, "notations")
    for notations in notations_elements:
        for child in notations:
            kind = _local_name(child.tag)
            if kind not in {"tied", "slur"}:
                continue
            action = child.get("type")
            if action not in {"start", "continue", "stop", "let-ring"}:
                continue
            spans.append(
                _source_span_record(
                    scope,
                    anchor,
                    kind="notated-tie" if kind == "tied" else "slur",
                    number=child.get("number") or "1",
                    action=action,
                    source_order=len(spans) + 1,
                    element=child,
                    pitch=pitch,
                    line_type=child.get("line-type"),
                )
            )
    for notations in notations_elements:
        for group in notations:
            group_kind = _local_name(group.tag)
            if group_kind in {"glissando", "slide"} and group.get("type") in {
                "start",
                "stop",
            }:
                spans.append(
                    _source_span_record(
                        scope,
                        anchor,
                        kind=group_kind,
                        number=group.get("number") or "1",
                        action=group.get("type") or "",
                        source_order=len(spans) + 1,
                        element=group,
                        pitch=pitch,
                        text=group.text,
                        line_type=group.get("line-type"),
                        bend_sound=(_bend_sound_value(group) if group_kind == "slide" else None),
                    )
                )
                continue
            if group_kind in {"fermata", "arpeggiate", "non-arpeggiate"}:
                marks.append(
                    _source_event_mark_record(
                        scope,
                        anchor,
                        family="notation",
                        kind=group_kind,
                        source_order=len(marks) + 1,
                        element=group,
                    )
                )
                continue
            family = {
                "articulations": "articulation",
                "ornaments": "ornament",
                "technical": "technical",
                "dynamics": "dynamic",
            }.get(group_kind)
            if family is None:
                continue
            group_id = group.get("id")
            group_placement = group.get("placement") if family == "dynamic" else None
            for child in group:
                kind = _local_name(child.tag)
                if family == "ornament" and kind == "wavy-line":
                    action = child.get("type")
                    if action in {"start", "continue", "stop"}:
                        spans.append(
                            _source_span_record(
                                scope,
                                anchor,
                                kind="wavy-line",
                                number=child.get("number") or "1",
                                action=action,
                                source_order=len(spans) + 1,
                                element=child,
                                pitch=pitch,
                                playback=_trill_playback_value(child),
                            )
                        )
                    continue
                if family == "ornament" and kind == "tremolo":
                    tremolo_type = child.get("type") or "single"
                    if tremolo_type in {"start", "stop"}:
                        spans.append(
                            _source_span_record(
                                scope,
                                anchor,
                                kind="tremolo",
                                number="1",
                                action=tremolo_type,
                                source_order=len(spans) + 1,
                                element=child,
                                pitch=pitch,
                                tremolo_marks=int(_value(child) or ""),
                            )
                        )
                    continue
                if family == "articulation":
                    marks.append(
                        _source_event_mark_record(
                            scope,
                            anchor,
                            family=family,
                            kind=kind,
                            source_order=len(marks) + 1,
                            element=child,
                            group_id=group_id,
                            group_placement=group_placement,
                        )
                    )
    return tuple(spans), tuple(marks)


def _source_lyrics(
    note: element_tree.Element,
    *,
    part_id: str,
    measure_ordinal: int,
    source_order: int,
    score_onset: Fraction,
    staff: str,
    voice: str,
) -> tuple[OracleSemanticRecord, ...]:
    event_id = f"{part_id}:m{measure_ordinal}:n{source_order}"
    scope = ("part", part_id, "measure", str(measure_ordinal), "event", event_id)
    anchor: OracleValue = (
        part_id,
        f"{part_id}:m{measure_ordinal}",
        event_id,
        staff,
        voice,
        score_onset,
    )
    records: list[OracleSemanticRecord] = []
    for lyric_order, lyric in enumerate(_children(note, "lyric"), start=1):
        segments: list[OracleValue] = []
        pending_syllabic: str | None = None
        pending_elision: str | None = None
        pending_elision_smufl: str | None = None
        extend_present = False
        extend: str | None = None
        laughing = False
        humming = False
        end_line = False
        end_paragraph = False
        for child in lyric:
            kind = _local_name(child.tag)
            if kind == "syllabic":
                pending_syllabic = child.text
            elif kind == "elision":
                pending_elision = child.text or ""
                pending_elision_smufl = child.get("smufl")
            elif kind == "text":
                segments.append(
                    (
                        child.text or "",
                        pending_syllabic,
                        pending_elision,
                        pending_elision_smufl,
                    )
                )
                pending_syllabic = None
                pending_elision = None
                pending_elision_smufl = None
            elif kind == "extend":
                extend_present = True
                extend = child.get("type")
            elif kind == "laughing":
                laughing = True
            elif kind == "humming":
                humming = True
            elif kind == "end-line":
                end_line = True
            elif kind == "end-paragraph":
                end_paragraph = True
        text = "".join(f"{item[2] or ''}{item[0]}" for item in segments)  # type: ignore[index]
        records.append(
            _record(
                scope,
                "lyric",
                anchor=anchor,
                number=lyric.get("number"),
                name=lyric.get("name"),
                syllabic=segments[0][1] if segments else None,  # type: ignore[index]
                text=text,
                source_order=lyric_order,
                segments=tuple(segments),
                extend_present=extend_present,
                extend=extend,
                laughing=laughing,
                humming=humming,
                end_line=end_line,
                end_paragraph=end_paragraph,
                print_object=_yes_no(lyric.get("print-object")),
                time_only=lyric.get("time-only"),
                source_id=lyric.get("id"),
                placement=lyric.get("placement"),
            )
        )
    return tuple(records)


def _source_harmony_record(
    element: element_tree.Element,
    *,
    part_id: str,
    measure_ordinal: int,
    onset: Fraction,
    score_onset: Fraction,
    divisions: int | None,
    source_order: int,
) -> OracleSemanticRecord:
    offset_text = _child_value(element, "offset")
    offset = Fraction(0) if offset_text is None else Fraction(offset_text) / (divisions or 1)
    root = _child(element, "root")
    kind = _child(element, "kind")
    if root is None or kind is None:
        raise ValueError("oracle fixture harmony is not a root/kind chord")
    root_alter = _fraction(_child_value(root, "root-alter"), default=Fraction(0))
    chord: OracleValue = (
        _child_value(root, "root-step"),
        root_alter,
        None,
        None,
        _value(kind) or "",
        kind.get("text"),
        _yes_no(kind.get("use-symbols")),
        _yes_no(kind.get("stack-degrees")),
        _yes_no(kind.get("parentheses-degrees")),
        _yes_no(kind.get("bracket-degrees")),
        _integer(_child_value(element, "inversion")),
        None,
        (),
    )
    staff = _child_value(element, "staff") or "1"
    anchor = _time_anchor_value(
        part_id=part_id,
        measure_ordinal=measure_ordinal,
        onset=onset + offset,
        score_onset=score_onset,
        staff=staff,
        voice=None,
    )
    return _record(
        ("part", part_id, "measure", str(measure_ordinal)),
        "harmony",
        anchor=anchor,
        root_step=_child_value(root, "root-step"),
        root_alter=root_alter,
        harmony_kind=_value(kind) or "",
        kind_text=kind.get("text"),
        source_order=source_order,
        chords=(chord,),
        frame=None,
        harmony_type=element.get("type"),
        print_object=_yes_no(element.get("print-object")),
        print_frame=_yes_no(element.get("print-frame")),
        arrangement=element.get("arrangement"),
        source_id=element.get("id"),
        system_relation=element.get("system"),
    )


def _source_figured_bass_record(
    element: element_tree.Element,
    *,
    part_id: str,
    measure_ordinal: int,
    event_id: str,
    event: OracleEvent,
    score_onset: Fraction,
    divisions: int | None,
    source_order: int,
) -> OracleSemanticRecord:
    figures: list[OracleValue] = []
    for figure in _children(element, "figure"):
        extend = _child(figure, "extend")
        figures.append(
            (
                _child_value(figure, "prefix"),
                _child_value(figure, "figure-number"),
                _child_value(figure, "suffix"),
                extend is not None,
                extend.get("type") if extend is not None else None,
            )
        )
    duration_text = _child_value(element, "duration")
    duration = (
        Fraction(duration_text) / divisions
        if duration_text is not None and divisions is not None
        else None
    )
    return _record(
        ("part", part_id, "measure", str(measure_ordinal)),
        "figured-bass",
        anchor=(
            part_id,
            f"{part_id}:m{measure_ordinal}",
            event_id,
            event.staff,
            event.voice,
            score_onset,
        ),
        figures=tuple(figures),
        duration=duration,
        source_order=source_order,
        parentheses=_yes_no(element.get("parentheses")),
        print_object=_yes_no(element.get("print-object")),
        print_dot=_yes_no(element.get("print-dot")),
        print_spacing=_yes_no(element.get("print-spacing")),
        placement=element.get("placement"),
        source_id=element.get("id"),
    )


def _source_midi_device(element: element_tree.Element) -> OracleValue:
    return (
        element.get("id"),
        _integer(element.get("port")),
        _value(element) or "",
    )


def _source_midi_instrument(element: element_tree.Element) -> OracleValue:
    return (
        element.get("id") or "",
        _integer(_child_value(element, "midi-channel")),
        _child_value(element, "midi-name"),
        _integer(_child_value(element, "midi-bank")),
        _integer(_child_value(element, "midi-program")),
        _integer(_child_value(element, "midi-unpitched")),
        _fraction(_child_value(element, "volume")),
        _fraction(_child_value(element, "pan")),
        _fraction(_child_value(element, "elevation")),
    )


def _source_virtual_instrument(element: element_tree.Element | None) -> OracleValue:
    if element is None:
        return None
    return (
        _child_value(element, "virtual-library"),
        _child_value(element, "virtual-name"),
    )


def _source_part_playback(root: element_tree.Element) -> tuple[OracleSemanticRecord, ...]:
    part_list = _child(root, "part-list")
    if part_list is None:
        return ()
    records: list[OracleSemanticRecord] = []
    for part in _children(part_list, "score-part"):
        part_id = part.get("id") or ""
        devices = _children(part, "midi-device")
        midi = _children(part, "midi-instrument")
        instruments: list[OracleValue] = []
        for instrument in _children(part, "score-instrument"):
            instrument_id = instrument.get("id") or ""
            ensemble = _child(instrument, "ensemble")
            ensemble_text = _value(ensemble)
            instruments.append(
                (
                    instrument_id,
                    _child_value(instrument, "instrument-name"),
                    _child_value(instrument, "instrument-abbreviation"),
                    _child_value(instrument, "instrument-sound"),
                    _child(instrument, "solo") is not None,
                    ensemble is not None,
                    int(ensemble_text) if ensemble_text else None,
                    tuple(
                        _source_midi_device(item)
                        for item in devices
                        if item.get("id") in {None, instrument_id}
                    ),
                    tuple(
                        _source_midi_instrument(item)
                        for item in midi
                        if item.get("id") == instrument_id
                    ),
                    _source_virtual_instrument(_child(instrument, "virtual-instrument")),
                )
            )
        records.append(
            _record(
                ("part", part_id),
                "part-playback",
                instruments=tuple(instruments),
                players=tuple(
                    (item.get("id") or "", _child_value(item, "player-name") or "")
                    for item in _children(part, "player")
                ),
            )
        )
    return tuple(records)


def _source_pedal_playback(value: str | None) -> OracleValue:
    if value is None:
        return None
    return (value == "yes", None) if value in {"yes", "no"} else (None, Fraction(value))


def _source_sound_record(
    element: element_tree.Element,
    *,
    part_id: str,
    measure_ordinal: int,
    onset: Fraction,
    score_onset: Fraction,
    divisions: int | None,
    source_order: int,
) -> OracleSemanticRecord:
    offset_text = _child_value(element, "offset")
    offset = Fraction(0) if offset_text is None else Fraction(offset_text) / (divisions or 1)
    location = onset + offset
    changes: list[OracleValue] = []
    devices: list[OracleValue] = []
    midi: list[OracleValue] = []
    techniques: list[OracleValue] = []
    for child in element:
        kind = _local_name(child.tag)
        if kind == "instrument-change":
            ensemble = _child(child, "ensemble")
            ensemble_text = _value(ensemble)
            changes.append(
                (
                    child.get("id") or "",
                    _child_value(child, "instrument-sound"),
                    _child(child, "solo") is not None,
                    ensemble is not None,
                    int(ensemble_text) if ensemble_text else None,
                    _source_virtual_instrument(_child(child, "virtual-instrument")),
                )
            )
        elif kind == "midi-device":
            devices.append(_source_midi_device(child))
        elif kind == "midi-instrument":
            midi.append(_source_midi_instrument(child))
        elif kind == "play":
            techniques.extend(
                (
                    child.get("id"),
                    _local_name(item.tag),
                    _value(item) or "",
                    item.get("type") if _local_name(item.tag) == "other-play" else None,
                )
                for item in child
                if isinstance(item.tag, str)
            )
    swing = _child(element, "swing")
    swing_value: OracleValue = None
    if swing is not None:
        straight = _child(swing, "straight") is not None
        swing_value = (
            straight,
            None if straight else _integer(_child_value(swing, "first")),
            None if straight else _integer(_child_value(swing, "second")),
            None if straight else _child_value(swing, "swing-type"),
            _child_value(swing, "swing-style"),
        )
    return _record(
        ("part", part_id, "measure", str(measure_ordinal)),
        "sound",
        onset=location,
        score_onset=score_onset + location,
        source_order=source_order,
        tempo=_fraction(element.get("tempo")),
        dynamics=_fraction(element.get("dynamics")),
        dacapo=_yes_no(element.get("dacapo")),
        segno=element.get("segno"),
        dalsegno=element.get("dalsegno"),
        coda=element.get("coda"),
        tocoda=element.get("tocoda"),
        divisions=_fraction(element.get("divisions")),
        forward_repeat=_yes_no(element.get("forward-repeat")),
        fine=element.get("fine"),
        time_only=element.get("time-only"),
        pizzicato=_yes_no(element.get("pizzicato")),
        pan=_fraction(element.get("pan")),
        elevation=_fraction(element.get("elevation")),
        damper_pedal=_source_pedal_playback(element.get("damper-pedal")),
        soft_pedal=_source_pedal_playback(element.get("soft-pedal")),
        sostenuto_pedal=_source_pedal_playback(element.get("sostenuto-pedal")),
        instrument_changes=tuple(changes),
        devices=tuple(devices),
        midi=tuple(midi),
        techniques=tuple(techniques),
        swing=swing_value,
        source_id=element.get("id"),
    )


def _source_note_playback(
    note: element_tree.Element,
    event: OracleEvent,
    *,
    divisions: int | None,
    source_order: int,
) -> OracleSemanticRecord:
    grace = _child(note, "grace")
    grace_value: OracleValue = None
    if grace is not None:
        make_time = grace.get("make-time")
        grace_value = (
            _yes_no(grace.get("slash")),
            Fraction(make_time) / (divisions or 1) if make_time is not None else None,
            _fraction(grace.get("steal-time-previous")),
            _fraction(grace.get("steal-time-following")),
        )
    performed_duration = grace_value[1] if grace_value is not None else event.duration  # type: ignore[index]
    return _record(
        (
            "part",
            event.part_id,
            "measure",
            str(event.measure_ordinal),
            "event",
            f"{event.part_id}:m{event.measure_ordinal}:n{source_order}",
        ),
        "note-playback",
        performed_duration=performed_duration,
        grace_timing=grace_value,
        instrument_ids=tuple(item.get("id") or "" for item in _children(note, "instrument")),
        dynamics=_fraction(note.get("dynamics")),
    )


_XLINK = "{http://www.w3.org/1999/xlink}"


def _source_link_value(element: element_tree.Element) -> OracleValue:
    return (
        element.get(f"{_XLINK}href") or "",
        element.get(f"{_XLINK}type"),
        element.get(f"{_XLINK}role"),
        element.get(f"{_XLINK}title"),
        element.get(f"{_XLINK}show"),
        element.get(f"{_XLINK}actuate"),
        element.get("name"),
        element.get("element"),
        _integer(element.get("position")),
        _source_presentation(element),
    )


def _source_bookmark_value(element: element_tree.Element) -> OracleValue:
    return (
        element.get("id") or "",
        element.get("name"),
        element.get("element"),
        _integer(element.get("position")),
    )


def _source_score_links(root: element_tree.Element) -> tuple[OracleSemanticRecord, ...]:
    records: list[OracleSemanticRecord] = []
    work = _child(root, "work")
    opus = _child(work, "opus") if work is not None else None
    if opus is not None:
        records.append(_record(("score",), "work-opus", link=_source_link_value(opus)))
    for credit_index, credit in enumerate(_children(root, "credit"), start=1):
        for source_order, item in enumerate(credit, start=1):
            kind = _local_name(item.tag)
            if kind == "link":
                records.append(
                    _record(
                        ("score", "credit", str(credit_index)),
                        "link",
                        source_order=source_order,
                        link=_source_link_value(item),
                    )
                )
            elif kind == "bookmark":
                records.append(
                    _record(
                        ("score", "credit", str(credit_index)),
                        "bookmark",
                        source_order=source_order,
                        bookmark=_source_bookmark_value(item),
                    )
                )
    part_list = _child(root, "part-list")
    if part_list is not None:
        for part in _children(part_list, "score-part"):
            part_id = part.get("id") or ""
            for order, item in enumerate(_children(part, "part-link"), start=1):
                records.append(
                    _record(
                        ("part", part_id),
                        "part-link",
                        source_order=order,
                        link=_source_link_value(item),
                        instrument_ids=tuple(
                            child.get("id") or "" for child in _children(item, "instrument-link")
                        ),
                        group_links=tuple(
                            _value(child) or "" for child in _children(item, "group-link")
                        ),
                    )
                )
    return tuple(records)


def _source_measure_link_record(
    element: element_tree.Element,
    *,
    part_id: str,
    measure_ordinal: int,
    kind_order: int,
) -> OracleSemanticRecord:
    kind = _local_name(element.tag)
    return _record(
        ("part", part_id, "measure", str(measure_ordinal)),
        kind,
        source_order=kind_order,
        **(
            {"link": _source_link_value(element)}
            if kind == "link"
            else {"bookmark": _source_bookmark_value(element)}
        ),
    )


def _time_anchor_value(
    *,
    part_id: str,
    measure_ordinal: int,
    onset: Fraction,
    score_onset: Fraction,
    staff: str | None,
    voice: str | None,
) -> OracleValue:
    return (
        part_id,
        f"{part_id}:m{measure_ordinal}",
        onset,
        score_onset + onset,
        staff,
        voice,
    )


def _source_direction_records(
    element: element_tree.Element,
    *,
    part_id: str,
    measure_ordinal: int,
    onset: Fraction,
    score_onset: Fraction,
    divisions: int | None,
    source_order: int,
) -> tuple[tuple[OracleSemanticRecord, ...], tuple[OracleSemanticRecord, ...]]:
    offset_text = _child_value(element, "offset")
    offset = Fraction(0) if offset_text is None else Fraction(offset_text) / (divisions or 1)
    location = onset + offset
    staff = _child_value(element, "staff") or "1"
    voice = _child_value(element, "voice")
    anchor = _time_anchor_value(
        part_id=part_id,
        measure_ordinal=measure_ordinal,
        onset=location,
        score_onset=score_onset,
        staff=staff,
        voice=voice,
    )
    scope = ("part", part_id, "measure", str(measure_ordinal))
    placement = element.get("placement")
    directive = _yes_no(element.get("directive"))
    directions: list[OracleSemanticRecord] = []
    spans: list[OracleSemanticRecord] = []
    component_order = 0
    for direction_type in _children(element, "direction-type"):
        for child in direction_type:
            kind = _local_name(child.tag)
            if kind in {
                "words",
                "rehearsal",
                "segno",
                "coda",
                "symbol",
                "damp",
                "damp-all",
                "eyeglasses",
                "string-mute",
                "staff-divide",
                "other-direction",
            }:
                component_order += 1
                value = (
                    child.get("type")
                    if kind in {"string-mute", "staff-divide"}
                    else _value(child) or ""
                )
                directions.append(
                    _record(
                        scope,
                        "direction",
                        anchor=anchor,
                        family=kind,
                        value=value or "",
                        placement=placement,
                        source_order=source_order,
                        component_order=component_order,
                        group_id=None,
                        smufl=(
                            child.get("smufl")
                            if kind in {"segno", "coda", "other-direction"}
                            else None
                        ),
                        direction_id=element.get("id"),
                        direction_type_id=direction_type.get("id"),
                        source_id=child.get("id"),
                        print_object=(
                            _yes_no(child.get("print-object"))
                            if kind == "other-direction"
                            else None
                        ),
                        system_relation=element.get("system"),
                        data=None,
                        presentation=_source_presentation(child),
                        directive=directive,
                        pedal_number=None,
                        pedal_line=None,
                        pedal_sign=None,
                        pedal_abbreviated=None,
                    )
                )
                continue
            if kind == "dynamics":
                for dynamic in child:
                    if len(dynamic):
                        continue
                    component_order += 1
                    directions.append(
                        _record(
                            scope,
                            "direction",
                            anchor=anchor,
                            family="dynamic",
                            value=_value(dynamic) or _local_name(dynamic.tag),
                            placement=placement,
                            source_order=source_order,
                            component_order=component_order,
                            group_id=child.get("id"),
                            smufl=dynamic.get("smufl"),
                            direction_id=element.get("id"),
                            direction_type_id=direction_type.get("id"),
                            source_id=None,
                            print_object=None,
                            system_relation=element.get("system"),
                            data=None,
                            presentation=_source_presentation(child),
                            directive=directive,
                            pedal_number=None,
                            pedal_line=None,
                            pedal_sign=None,
                            pedal_abbreviated=None,
                        )
                    )
                continue
            if kind not in {"wedge", "dashes", "bracket", "pedal", "octave-shift"}:
                continue
            span_type = child.get("type")
            starts = {
                "wedge": {"crescendo", "diminuendo"},
                "dashes": {"start"},
                "bracket": {"start"},
                "pedal": {"start", "sostenuto"},
                "octave-shift": {"up", "down"},
            }[kind]
            continuations = (
                {"continue", "change", "discontinue", "resume"} if kind == "pedal" else {"continue"}
            )
            if span_type not in starts | continuations | {"stop"}:
                continue
            component_order += 1
            pedal_line = _yes_no(child.get("line")) if kind == "pedal" else None
            pedal_sign = _yes_no(child.get("sign")) if kind == "pedal" else None
            pedal_abbreviated = _yes_no(child.get("abbreviated")) if kind == "pedal" else None
            if (
                kind == "pedal"
                and span_type in {"start", "sostenuto", "stop"}
                and pedal_line is not True
                and pedal_sign is not False
            ):
                directions.append(
                    _record(
                        scope,
                        "direction",
                        anchor=anchor,
                        family="pedal",
                        value=span_type or "",
                        placement=placement,
                        source_order=source_order,
                        component_order=component_order,
                        group_id=None,
                        smufl=None,
                        direction_id=element.get("id"),
                        direction_type_id=direction_type.get("id"),
                        source_id=child.get("id"),
                        print_object=None,
                        system_relation=element.get("system"),
                        data=None,
                        presentation=_source_presentation(child),
                        directive=directive,
                        pedal_number=child.get("number") or "1",
                        pedal_line=pedal_line,
                        pedal_sign=pedal_sign,
                        pedal_abbreviated=pedal_abbreviated,
                    )
                )
                if span_type == "stop":
                    continue
            spans.append(
                _record(
                    scope,
                    "time-span-endpoint",
                    anchor=anchor,
                    span_kind=kind,
                    number=child.get("number") or "1",
                    action=(
                        "start"
                        if span_type in starts
                        else "continue"
                        if span_type in continuations
                        else "stop"
                    ),
                    opening=span_type if span_type in starts else None,
                    source_order=source_order,
                    component_order=component_order,
                    direction_id=element.get("id"),
                    direction_type_id=direction_type.get("id"),
                    source_id=child.get("id"),
                    system_relation=element.get("system"),
                    source_type=span_type,
                    line_type=child.get("line-type"),
                    dash_length=_fraction(child.get("dash-length")),
                    space_length=_fraction(child.get("space-length")),
                    spread=_fraction(child.get("spread")),
                    niente=_yes_no(child.get("niente")),
                    line_end=child.get("line-end"),
                    end_length=_fraction(child.get("end-length")),
                    pedal_line=pedal_line,
                    pedal_sign=pedal_sign,
                    pedal_abbreviated=pedal_abbreviated,
                    octave_size=(int(child.get("size", "")) if child.get("size") else None),
                    directive=directive,
                )
            )
    return tuple(directions), tuple(spans)


def _canonical_metadata(result: TemporalReadResult) -> tuple[OracleSemanticRecord, ...]:
    score = result.score

    def metadata_facts(value: object) -> tuple[tuple[str, OracleValue], ...]:
        metadata = value
        encoding = metadata.encoding  # type: ignore[attr-defined]
        encoding_value: OracleValue = None
        if encoding is not None:
            encoding_value = (
                encoding.dates,
                tuple((item.value, item.text_type) for item in encoding.encoders),
                encoding.software,
                encoding.descriptions,
                tuple(
                    (item.supported, item.element, item.attribute, item.value)
                    for item in encoding.supports
                ),
            )
        return (
            ("concert_score", metadata.concert_score),  # type: ignore[attr-defined]
            ("work_number", metadata.work_number),  # type: ignore[attr-defined]
            (
                "rights",
                tuple(
                    (item.value, item.text_type)
                    for item in metadata.rights  # type: ignore[attr-defined]
                ),
            ),
            ("source", metadata.source),  # type: ignore[attr-defined]
            (
                "relations",
                tuple(
                    (item.value, item.text_type)
                    for item in metadata.relations  # type: ignore[attr-defined]
                ),
            ),
            ("encoding", encoding_value),
            (
                "miscellaneous",
                tuple(
                    (item.name, item.value)
                    for item in metadata.miscellaneous  # type: ignore[attr-defined]
                ),
            ),
            ("schema_location", metadata.schema_location),  # type: ignore[attr-defined]
        )

    records = [
        _record(
            ("score",),
            "score-header",
            work_title=score.work_title,
            movement_title=score.movement_title,
            movement_number=score.movement_number,
            creators=tuple(score.creators),
        ),
        OracleSemanticRecord(("score",), "identification", metadata_facts(score.metadata)),
    ]
    for part in score.parts:
        records.append(
            _record(
                ("part", part.id),
                "part-header",
                name=part.name,
                abbreviation=part.abbreviation,
            )
        )
        records.append(
            OracleSemanticRecord(("part", part.id), "identification", metadata_facts(part.metadata))
        )
    return tuple(records)


def _canonical_margins(value: object | None) -> OracleValue:
    if value is None:
        return None
    return (
        value.kind,  # type: ignore[attr-defined]
        value.left,  # type: ignore[attr-defined]
        value.right,  # type: ignore[attr-defined]
        value.top,  # type: ignore[attr-defined]
        value.bottom,  # type: ignore[attr-defined]
    )


def _canonical_page_layout(value: object | None) -> OracleValue:
    if value is None:
        return None
    return (
        value.height,  # type: ignore[attr-defined]
        value.width,  # type: ignore[attr-defined]
        tuple(_canonical_margins(item) for item in value.margins),  # type: ignore[attr-defined]
    )


def _canonical_system_layout(value: object | None) -> OracleValue:
    if value is None:
        return None
    return (
        _canonical_margins(value.margins),  # type: ignore[attr-defined]
        value.system_distance,  # type: ignore[attr-defined]
        value.top_system_distance,  # type: ignore[attr-defined]
    )


def _canonical_name_display(value: object | None) -> OracleValue:
    if value is None:
        return None
    return tuple(
        (item.kind, item.value, _canonical_presentation(item.style))
        for item in value.segments  # type: ignore[attr-defined]
    )


def _canonical_score_layout(result: TemporalReadResult) -> tuple[OracleSemanticRecord, ...]:
    layout = result.score.layout
    if layout is None:
        return ()
    defaults = layout.defaults
    defaults_value: OracleValue = None
    if defaults is not None:
        defaults_value = (
            (
                defaults.scaling.millimeters,
                defaults.scaling.tenths,
            )
            if defaults.scaling is not None
            else None,
            _canonical_page_layout(defaults.page),
            _canonical_system_layout(defaults.system),
            tuple((item.number, item.distance) for item in defaults.staves),
            tuple(
                (item.kind, item.value_type, item.number, item.text) for item in defaults.appearance
            ),
            _canonical_presentation(defaults.music_font),
            _canonical_presentation(defaults.word_font),
            tuple(
                (item.number, item.name, _canonical_presentation(item.style))
                for item in defaults.lyric_fonts
            ),
            tuple((item.number, item.name, item.language) for item in defaults.lyric_languages),
        )
    credits: OracleValue = tuple(
        (
            credit.page,
            credit.types,
            tuple(
                (
                    item.kind,
                    item.value,
                    _canonical_presentation(item.style),
                    item.mime_type,
                    item.width,
                    item.height,
                    item.source_id,
                )
                for item in credit.items
            ),
            credit.source_id,
        )
        for credit in layout.credits
    )
    return (_record(("score",), "score-layout", defaults=defaults_value, credits=credits),)


def _canonical_measure_layout(
    value: object, *, part_id: str, measure_ordinal: int
) -> OracleSemanticRecord:
    return _record(
        ("part", part_id, "measure", str(measure_ordinal)),
        "measure-layout",
        width=value.width,  # type: ignore[attr-defined]
        new_page=value.new_page,  # type: ignore[attr-defined]
        new_system=value.new_system,  # type: ignore[attr-defined]
        page_number=value.page_number,  # type: ignore[attr-defined]
        blank_page=value.blank_page,  # type: ignore[attr-defined]
        page=_canonical_page_layout(value.page),  # type: ignore[attr-defined]
        system=_canonical_system_layout(value.system),  # type: ignore[attr-defined]
        staves=tuple(
            (item.number, item.distance)
            for item in value.staves  # type: ignore[attr-defined]
        ),
        measure_distance=value.measure_distance,  # type: ignore[attr-defined]
        measure_numbering=value.measure_numbering,  # type: ignore[attr-defined]
        staff_spacing=value.staff_spacing,  # type: ignore[attr-defined]
        part_name_display=_canonical_name_display(value.part_name_display),  # type: ignore[attr-defined]
        part_abbreviation_display=_canonical_name_display(  # type: ignore[attr-defined]
            value.part_abbreviation_display  # type: ignore[attr-defined]
        ),
    )


def _canonical_midi_device(value: object) -> OracleValue:
    return (value.instrument_id, value.port, value.name)  # type: ignore[attr-defined]


def _canonical_midi_instrument(value: object) -> OracleValue:
    return (
        value.instrument_id,  # type: ignore[attr-defined]
        value.channel,  # type: ignore[attr-defined]
        value.name,  # type: ignore[attr-defined]
        value.bank,  # type: ignore[attr-defined]
        value.program,  # type: ignore[attr-defined]
        value.unpitched,  # type: ignore[attr-defined]
        value.volume,  # type: ignore[attr-defined]
        value.pan,  # type: ignore[attr-defined]
        value.elevation,  # type: ignore[attr-defined]
    )


def _canonical_virtual_instrument(value: object | None) -> OracleValue:
    if value is None:
        return None
    return (value.library, value.name)  # type: ignore[attr-defined]


def _canonical_part_playback(result: TemporalReadResult) -> tuple[OracleSemanticRecord, ...]:
    return tuple(
        _record(
            ("part", part.id),
            "part-playback",
            instruments=tuple(
                (
                    instrument.id,
                    instrument.name,
                    instrument.abbreviation,
                    instrument.sound,
                    instrument.solo,
                    instrument.ensemble,
                    instrument.ensemble_size,
                    tuple(_canonical_midi_device(item) for item in instrument.playback.devices),
                    tuple(_canonical_midi_instrument(item) for item in instrument.playback.midi),
                    _canonical_virtual_instrument(instrument.playback.virtual),
                )
                for instrument in part.instruments
            ),
            players=tuple((item.id, item.name) for item in part.players),
        )
        for part in result.score.parts
    )


def _canonical_pedal_playback(value: object | None) -> OracleValue:
    if value is None:
        return None
    return (value.enabled, value.percent)  # type: ignore[attr-defined]


def _canonical_sound_record(
    value: object, *, part_id: str, measure_ordinal: int
) -> OracleSemanticRecord:
    swing = value.swing  # type: ignore[attr-defined]
    return _record(
        ("part", part_id, "measure", str(measure_ordinal)),
        "sound",
        onset=value.onset,  # type: ignore[attr-defined]
        score_onset=value.score_onset,  # type: ignore[attr-defined]
        source_order=value.source_order,  # type: ignore[attr-defined]
        tempo=value.tempo,  # type: ignore[attr-defined]
        dynamics=value.dynamics,  # type: ignore[attr-defined]
        dacapo=value.dacapo,  # type: ignore[attr-defined]
        segno=value.segno,  # type: ignore[attr-defined]
        dalsegno=value.dalsegno,  # type: ignore[attr-defined]
        coda=value.coda,  # type: ignore[attr-defined]
        tocoda=value.tocoda,  # type: ignore[attr-defined]
        divisions=value.divisions,  # type: ignore[attr-defined]
        forward_repeat=value.forward_repeat,  # type: ignore[attr-defined]
        fine=value.fine,  # type: ignore[attr-defined]
        time_only=value.time_only,  # type: ignore[attr-defined]
        pizzicato=value.pizzicato,  # type: ignore[attr-defined]
        pan=value.pan,  # type: ignore[attr-defined]
        elevation=value.elevation,  # type: ignore[attr-defined]
        damper_pedal=_canonical_pedal_playback(value.damper_pedal),  # type: ignore[attr-defined]
        soft_pedal=_canonical_pedal_playback(value.soft_pedal),  # type: ignore[attr-defined]
        sostenuto_pedal=_canonical_pedal_playback(value.sostenuto_pedal),  # type: ignore[attr-defined]
        instrument_changes=tuple(
            (
                item.instrument_id,
                item.sound,
                item.solo,
                item.ensemble,
                item.ensemble_size,
                _canonical_virtual_instrument(item.virtual),
            )
            for item in value.instrument_changes  # type: ignore[attr-defined]
        ),
        devices=tuple(
            _canonical_midi_device(item)
            for item in value.devices  # type: ignore[attr-defined]
        ),
        midi=tuple(
            _canonical_midi_instrument(item)
            for item in value.midi  # type: ignore[attr-defined]
        ),
        techniques=tuple(
            (item.instrument_id, item.kind, item.value, item.technique_type)
            for item in value.techniques  # type: ignore[attr-defined]
        ),
        swing=(swing.straight, swing.first, swing.second, swing.note_type, swing.style)
        if swing is not None
        else None,
        source_id=value.source_id,  # type: ignore[attr-defined]
    )


def _canonical_note_playback(
    event: object, *, part_id: str, measure_ordinal: int
) -> OracleSemanticRecord:
    timing = event.grace_timing  # type: ignore[attr-defined]
    return _record(
        (
            "part",
            part_id,
            "measure",
            str(measure_ordinal),
            "event",
            event.id,  # type: ignore[attr-defined]
        ),
        "note-playback",
        performed_duration=event.performed_duration,  # type: ignore[attr-defined]
        grace_timing=(
            (
                timing.slash,
                timing.make_time,
                timing.steal_previous_percent,
                timing.steal_following_percent,
            )
            if timing is not None
            else None
        ),
        instrument_ids=event.instrument_ids,  # type: ignore[attr-defined]
        dynamics=event.dynamics,  # type: ignore[attr-defined]
    )


def _canonical_link_value(value: object) -> OracleValue:
    return (
        value.href,  # type: ignore[attr-defined]
        value.link_type,  # type: ignore[attr-defined]
        value.role,  # type: ignore[attr-defined]
        value.title,  # type: ignore[attr-defined]
        value.show,  # type: ignore[attr-defined]
        value.actuate,  # type: ignore[attr-defined]
        value.name,  # type: ignore[attr-defined]
        value.element,  # type: ignore[attr-defined]
        value.position,  # type: ignore[attr-defined]
        _canonical_presentation(value.presentation),  # type: ignore[attr-defined]
    )


def _canonical_bookmark_value(value: object) -> OracleValue:
    return (
        value.id,  # type: ignore[attr-defined]
        value.name,  # type: ignore[attr-defined]
        value.element,  # type: ignore[attr-defined]
        value.position,  # type: ignore[attr-defined]
    )


def _canonical_score_links(result: TemporalReadResult) -> tuple[OracleSemanticRecord, ...]:
    score = result.score
    records: list[OracleSemanticRecord] = []
    if score.work_opus is not None:
        records.append(
            _record(("score",), "work-opus", link=_canonical_link_value(score.work_opus))
        )
    records.extend(
        _record(
            ("score", *item.context.split(":")),
            "link",
            source_order=item.source_order,
            link=_canonical_link_value(item.link),
        )
        for item in score.links
    )
    records.extend(
        _record(
            ("score", *item.context.split(":")),
            "bookmark",
            source_order=item.source_order,
            bookmark=_canonical_bookmark_value(item.bookmark),
        )
        for item in score.bookmarks
    )
    for part in score.parts:
        records.extend(
            _record(
                ("part", part.id),
                "part-link",
                source_order=order,
                link=_canonical_link_value(item.link),
                instrument_ids=item.instrument_ids,
                group_links=item.group_links,
            )
            for order, item in enumerate(part.part_links, start=1)
        )
        for measure in part.measures:
            records.extend(
                _record(
                    ("part", part.id, "measure", str(measure.ordinal)),
                    "link",
                    source_order=order,
                    link=_canonical_link_value(item),
                )
                for order, item in enumerate(measure.links, start=1)
            )
            records.extend(
                _record(
                    ("part", part.id, "measure", str(measure.ordinal)),
                    "bookmark",
                    source_order=order,
                    bookmark=_canonical_bookmark_value(item),
                )
                for order, item in enumerate(measure.bookmarks, start=1)
            )
    return tuple(records)


def _canonical_attribute_record(
    item: object, *, part_id: str, measure_ordinal: int
) -> OracleSemanticRecord:
    attribute = item
    clefs: OracleValue = tuple(
        (
            value.staff,
            value.sign,
            value.line,
            value.octave_change,
            value.additional,
            value.size,
            value.after_barline,
            value.print_object,
            value.source_id,
        )
        for value in attribute.clefs  # type: ignore[attr-defined]
    )
    keys: OracleValue = tuple(
        (
            value.fifths,
            value.mode,
            value.staff,
            value.cancel,
            value.cancel_location,
            tuple(
                (
                    change.step,
                    change.alter,
                    change.accidental,
                    change.accidental_smufl,
                    tuple((mark.value, mark.smufl) for mark in change.accidentals),
                )
                for change in value.alterations
            ),
            tuple((octave.number, octave.octave, octave.cancel) for octave in value.octaves),
            value.print_object,
            value.source_id,
        )
        for value in attribute.keys  # type: ignore[attr-defined]
    )
    times: OracleValue = tuple(
        (
            value.beats,
            value.beat_types,
            value.symbol,
            value.staff,
            value.senza_misura,
            value.separator,
            (
                value.interchangeable.beats,
                value.interchangeable.beat_types,
                value.interchangeable.relation,
                value.interchangeable.symbol,
                value.interchangeable.separator,
            )
            if value.interchangeable is not None
            else None,
            value.print_object,
            value.source_id,
        )
        for value in attribute.times  # type: ignore[attr-defined]
    )
    transpositions: OracleValue = tuple(
        (
            value.staff,
            value.diatonic,
            value.chromatic,
            value.octave_change,
            value.doubling_above,
        )
        for value in attribute.transpositions  # type: ignore[attr-defined]
    )
    styles: OracleValue = tuple(
        (
            value.staff,
            value.kind,
            value.value,
            value.action,
            value.slashes,
            value.use_symbols,
            value.use_dots,
            value.use_stems,
            value.slash_type,
            value.slash_dots,
            value.source_id,
        )
        for value in attribute.measure_styles  # type: ignore[attr-defined]
    )
    details: OracleValue = tuple(
        (
            value.staff,
            value.staff_type,
            value.lines,
            tuple(
                (tuning.line, tuning.step, tuning.alter, tuning.octave) for tuning in value.tunings
            ),
            value.capo,
            value.size,
            value.show_frets,
            value.print_object,
            tuple(
                (line.line, line.print_object, _canonical_presentation(line.presentation))
                for line in value.line_details
            ),
        )
        for value in attribute.staff_details  # type: ignore[attr-defined]
    )
    symbols: OracleValue = tuple(
        (
            value.value,
            value.top_staff,
            value.bottom_staff,
            _canonical_presentation(value.presentation),
        )
        for value in attribute.part_symbols  # type: ignore[attr-defined]
    )
    for_parts: OracleValue = tuple(
        (
            value.staff,
            (
                value.clef.sign,
                value.clef.line,
                value.clef.octave_change,
            )
            if value.clef is not None
            else None,
            (
                value.transposition.staff,
                value.transposition.diatonic,
                value.transposition.chromatic,
                value.transposition.octave_change,
                value.transposition.doubling_above,
            ),
            value.source_id,
        )
        for value in attribute.for_parts  # type: ignore[attr-defined]
    )
    directives: OracleValue = tuple(
        (value.value, value.language, value.source_order)
        for value in attribute.directives  # type: ignore[attr-defined]
    )
    return _record(
        ("part", part_id, "measure", str(measure_ordinal)),
        "attributes",
        onset=attribute.onset,  # type: ignore[attr-defined]
        source_order=attribute.source_order,  # type: ignore[attr-defined]
        divisions=attribute.divisions,  # type: ignore[attr-defined]
        staves=attribute.staves,  # type: ignore[attr-defined]
        clefs=clefs,
        keys=keys,
        times=times,
        transpositions=transpositions,
        instrument_count=attribute.instrument_count,  # type: ignore[attr-defined]
        measure_styles=styles,
        staff_details=details,
        part_symbols=symbols,
        for_parts=for_parts,
        directives=directives,
    )


def _canonical_barline_record(
    item: object, *, part_id: str, measure_ordinal: int
) -> OracleSemanticRecord:
    barline = item
    return _record(
        ("part", part_id, "measure", str(measure_ordinal)),
        "barline",
        onset=barline.onset,  # type: ignore[attr-defined]
        source_order=barline.source_order,  # type: ignore[attr-defined]
        location=barline.location,  # type: ignore[attr-defined]
        style=barline.style,  # type: ignore[attr-defined]
        repeat_direction=barline.repeat_direction,  # type: ignore[attr-defined]
        repeat_times=barline.repeat_times,  # type: ignore[attr-defined]
        ending_number=barline.ending_number,  # type: ignore[attr-defined]
        ending_type=barline.ending_type,  # type: ignore[attr-defined]
        fermatas=tuple(
            (value.shape, value.orientation, value.source_id)
            for value in barline.fermatas  # type: ignore[attr-defined]
        ),
        navigation=tuple(
            (value.kind, value.token, value.source_id, value.smufl)
            for value in barline.navigation  # type: ignore[attr-defined]
        ),
        repeat_winged=barline.repeat_winged,  # type: ignore[attr-defined]
        repeat_after_jump=barline.repeat_after_jump,  # type: ignore[attr-defined]
        ending_text=barline.ending_text,  # type: ignore[attr-defined]
        ending_print_object=barline.ending_print_object,  # type: ignore[attr-defined]
        ending_system_relation=barline.ending_system_relation,  # type: ignore[attr-defined]
        divisions=barline.divisions,  # type: ignore[attr-defined]
        source_id=barline.source_id,  # type: ignore[attr-defined]
    )


def _canonical_trill_playback(value: object | None) -> OracleValue:
    if value is None:
        return None
    return (
        value.start_note,  # type: ignore[attr-defined]
        value.trill_step,  # type: ignore[attr-defined]
        value.two_note_turn,  # type: ignore[attr-defined]
        value.accelerate,  # type: ignore[attr-defined]
        value.beats,  # type: ignore[attr-defined]
        value.second_beat,  # type: ignore[attr-defined]
        value.last_beat,  # type: ignore[attr-defined]
    )


def _canonical_bend_sound(value: object | None) -> OracleValue:
    if value is None:
        return None
    return (
        value.accelerate,  # type: ignore[attr-defined]
        value.beats,  # type: ignore[attr-defined]
        value.first_beat,  # type: ignore[attr-defined]
        value.last_beat,  # type: ignore[attr-defined]
    )


def _event_anchor_value(part_id: str, measure_id: str, event: object) -> OracleValue:
    return (
        part_id,
        measure_id,
        event.id,  # type: ignore[attr-defined]
        event.staff,  # type: ignore[attr-defined]
        event.voice,  # type: ignore[attr-defined]
        event.score_onset,  # type: ignore[attr-defined]
    )


def _canonical_span_record(
    marker: object,
    *,
    part_id: str,
    measure_ordinal: int,
    measure_id: str,
    event: object,
) -> OracleSemanticRecord:
    return _record(
        ("part", part_id, "measure", str(measure_ordinal), "event", event.id),  # type: ignore[attr-defined]
        "span-endpoint",
        anchor=_event_anchor_value(part_id, measure_id, event),
        pitch=(
            (event.pitch.step, event.pitch.alter, event.pitch.octave)  # type: ignore[attr-defined]
            if event.pitch is not None  # type: ignore[attr-defined]
            else None
        ),
        span_kind=marker.kind,  # type: ignore[attr-defined]
        number=marker.number,  # type: ignore[attr-defined]
        action=marker.action,  # type: ignore[attr-defined]
        source_order=marker.source_order,  # type: ignore[attr-defined]
        placement=marker.placement,  # type: ignore[attr-defined]
        smufl=marker.smufl,  # type: ignore[attr-defined]
        playback=_canonical_trill_playback(marker.playback),  # type: ignore[attr-defined]
        tremolo_marks=marker.tremolo_marks,  # type: ignore[attr-defined]
        accidentals=tuple(
            (item.value, item.placement, item.bracket, item.parentheses, item.smufl)
            for item in marker.accidentals  # type: ignore[attr-defined]
        ),
        text=marker.text,  # type: ignore[attr-defined]
        source_id=marker.source_id,  # type: ignore[attr-defined]
        line_type=marker.line_type,  # type: ignore[attr-defined]
        bend_sound=_canonical_bend_sound(marker.bend_sound),  # type: ignore[attr-defined]
        print_object=marker.print_object,  # type: ignore[attr-defined]
        orientation=marker.orientation,  # type: ignore[attr-defined]
        dash_length=marker.dash_length,  # type: ignore[attr-defined]
        space_length=marker.space_length,  # type: ignore[attr-defined]
        time_only=marker.time_only,  # type: ignore[attr-defined]
    )


def _canonical_event_mark_record(
    marker: object,
    *,
    part_id: str,
    measure_ordinal: int,
    measure_id: str,
    event: object,
) -> OracleSemanticRecord:
    return _record(
        ("part", part_id, "measure", str(measure_ordinal), "event", event.id),  # type: ignore[attr-defined]
        "event-mark",
        anchor=_event_anchor_value(part_id, measure_id, event),
        family=marker.family,  # type: ignore[attr-defined]
        mark_kind=marker.kind,  # type: ignore[attr-defined]
        text=marker.text,  # type: ignore[attr-defined]
        source_order=marker.source_order,  # type: ignore[attr-defined]
        group_id=marker.group_id,  # type: ignore[attr-defined]
        placement=marker.placement,  # type: ignore[attr-defined]
        mark_type=marker.mark_type,  # type: ignore[attr-defined]
        smufl=marker.smufl,  # type: ignore[attr-defined]
        line_shape=marker.line_shape,  # type: ignore[attr-defined]
        line_type=marker.line_type,  # type: ignore[attr-defined]
        playback=_canonical_trill_playback(marker.playback),  # type: ignore[attr-defined]
        slash=marker.slash,  # type: ignore[attr-defined]
        long=marker.long,  # type: ignore[attr-defined]
        approach=marker.approach,  # type: ignore[attr-defined]
        departure=marker.departure,  # type: ignore[attr-defined]
        tremolo_marks=marker.tremolo_marks,  # type: ignore[attr-defined]
        bracket=marker.bracket,  # type: ignore[attr-defined]
        parentheses=marker.parentheses,  # type: ignore[attr-defined]
        accidentals=tuple(
            (item.value, item.placement, item.bracket, item.parentheses, item.smufl)
            for item in marker.accidentals  # type: ignore[attr-defined]
        ),
        technical=None,
        number=marker.number,  # type: ignore[attr-defined]
        print_object=marker.print_object,  # type: ignore[attr-defined]
        unbroken=marker.unbroken,  # type: ignore[attr-defined]
    )


def _canonical_time_anchor(anchor: object) -> OracleValue:
    return (
        anchor.part_id,  # type: ignore[attr-defined]
        anchor.measure_id,  # type: ignore[attr-defined]
        anchor.onset,  # type: ignore[attr-defined]
        anchor.score_onset,  # type: ignore[attr-defined]
        anchor.staff,  # type: ignore[attr-defined]
        anchor.voice,  # type: ignore[attr-defined]
    )


def _canonical_direction_record(
    direction: object, *, part_id: str, measure_ordinal: int
) -> OracleSemanticRecord:
    return _record(
        ("part", part_id, "measure", str(measure_ordinal)),
        "direction",
        anchor=_canonical_time_anchor(direction.anchor),  # type: ignore[attr-defined]
        family=direction.family,  # type: ignore[attr-defined]
        value=direction.value,  # type: ignore[attr-defined]
        placement=direction.placement,  # type: ignore[attr-defined]
        source_order=direction.source_order,  # type: ignore[attr-defined]
        component_order=direction.component_order,  # type: ignore[attr-defined]
        group_id=direction.group_id,  # type: ignore[attr-defined]
        smufl=direction.smufl,  # type: ignore[attr-defined]
        direction_id=direction.direction_id,  # type: ignore[attr-defined]
        direction_type_id=direction.direction_type_id,  # type: ignore[attr-defined]
        source_id=direction.source_id,  # type: ignore[attr-defined]
        print_object=direction.print_object,  # type: ignore[attr-defined]
        system_relation=direction.system_relation,  # type: ignore[attr-defined]
        data=None,
        presentation=_canonical_presentation(direction.presentation),  # type: ignore[attr-defined]
        directive=direction.directive,  # type: ignore[attr-defined]
        pedal_number=direction.pedal_number,  # type: ignore[attr-defined]
        pedal_line=direction.pedal_line,  # type: ignore[attr-defined]
        pedal_sign=direction.pedal_sign,  # type: ignore[attr-defined]
        pedal_abbreviated=direction.pedal_abbreviated,  # type: ignore[attr-defined]
    )


def _canonical_time_span_record(
    marker: object, *, part_id: str, measure_ordinal: int
) -> OracleSemanticRecord:
    return _record(
        ("part", part_id, "measure", str(measure_ordinal)),
        "time-span-endpoint",
        anchor=_canonical_time_anchor(marker.anchor),  # type: ignore[attr-defined]
        span_kind=marker.kind,  # type: ignore[attr-defined]
        number=marker.number,  # type: ignore[attr-defined]
        action=marker.action,  # type: ignore[attr-defined]
        opening=marker.opening,  # type: ignore[attr-defined]
        source_order=marker.source_order,  # type: ignore[attr-defined]
        component_order=marker.component_order,  # type: ignore[attr-defined]
        direction_id=marker.direction_id,  # type: ignore[attr-defined]
        direction_type_id=marker.direction_type_id,  # type: ignore[attr-defined]
        source_id=marker.source_id,  # type: ignore[attr-defined]
        system_relation=marker.system_relation,  # type: ignore[attr-defined]
        source_type=marker.source_type,  # type: ignore[attr-defined]
        line_type=marker.line_type,  # type: ignore[attr-defined]
        dash_length=marker.dash_length,  # type: ignore[attr-defined]
        space_length=marker.space_length,  # type: ignore[attr-defined]
        spread=marker.spread,  # type: ignore[attr-defined]
        niente=marker.niente,  # type: ignore[attr-defined]
        line_end=marker.line_end,  # type: ignore[attr-defined]
        end_length=marker.end_length,  # type: ignore[attr-defined]
        pedal_line=marker.pedal_line,  # type: ignore[attr-defined]
        pedal_sign=marker.pedal_sign,  # type: ignore[attr-defined]
        pedal_abbreviated=marker.pedal_abbreviated,  # type: ignore[attr-defined]
        octave_size=marker.octave_size,  # type: ignore[attr-defined]
        directive=marker.directive,  # type: ignore[attr-defined]
    )


def _record_fact(record: OracleSemanticRecord, name: str) -> OracleValue:
    return dict(record.facts)[name]


def _notation_endpoint_signature(record: OracleSemanticRecord) -> OracleValue:
    facts = dict(record.facts)
    return tuple(
        facts[name]
        for name in (
            "anchor",
            "action",
            "source_order",
            "placement",
            "smufl",
            "playback",
            "tremolo_marks",
            "accidentals",
            "text",
            "source_id",
            "line_type",
            "bend_sound",
            "print_object",
            "orientation",
            "dash_length",
            "space_length",
            "time_only",
        )
    )


def _ordered_notation_records(
    records: tuple[OracleSemanticRecord, ...],
) -> tuple[OracleSemanticRecord, ...]:
    action_order = {"start": 0, "continue": 1, "stop": 2, "let-ring": 3}
    return tuple(
        sorted(
            records,
            key=lambda record: (
                action_order[str(_record_fact(record, "action"))],
                _record_fact(record, "anchor")[5],  # type: ignore[index]
                int(_record_fact(record, "source_order")),
            ),
        )
    )


def _notation_base(record: OracleSemanticRecord) -> tuple[str, str, str, str]:
    part_id = record.scope[1]
    kind = str(_record_fact(record, "span_kind"))
    number = str(_record_fact(record, "number"))
    discriminator = ""
    if kind in {"sounding-tie", "notated-tie"}:
        pitch = _record_fact(record, "pitch")
        if not isinstance(pitch, tuple):
            raise ValueError("oracle tie endpoint has no pitch")
        step, alter, octave = pitch
        step_semitones = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}
        discriminator = str(12 * int(octave) + step_semitones[str(step)] + Fraction(alter))
    return part_id, kind, number, discriminator


def _resolve_notation_spans(
    records: tuple[OracleSemanticRecord, ...],
) -> tuple[OracleSemanticRecord, ...]:
    open_spans: dict[tuple[str, str, str, str, str], list[OracleSemanticRecord]] = {}
    pending: dict[tuple[str, str, str, str], list[OracleSemanticRecord]] = {}
    completed: list[OracleSemanticRecord] = []

    def append_span(
        base: tuple[str, str, str, str], endpoints: tuple[OracleSemanticRecord, ...]
    ) -> None:
        ordered = _ordered_notation_records(endpoints)
        completed.append(
            _record(
                ("part", base[0]),
                "notation-span",
                span_kind=base[1],
                number=base[2],
                endpoints=tuple(_notation_endpoint_signature(item) for item in ordered),
            )
        )

    index = 0
    while index < len(records):
        scope = records[index].scope
        group: list[OracleSemanticRecord] = []
        while index < len(records) and records[index].scope == scope:
            group.append(records[index])
            index += 1
        group.sort(
            key=lambda record: (
                0
                if _record_fact(record, "span_kind") in {"sounding-tie", "notated-tie"}
                and _record_fact(record, "action") == "stop"
                else 1,
                int(_record_fact(record, "source_order")),
            )
        )
        for record in group:
            base = _notation_base(record)
            anchor = _record_fact(record, "anchor")
            assert isinstance(anchor, tuple)
            key = (*base, str(anchor[4]))
            action = _record_fact(record, "action")
            if action == "let-ring":
                append_span(base, (record,))
            elif action == "start":
                if key in open_spans:
                    append_span(base, tuple(open_spans.pop(key)))
                pending_items = pending.pop(base, [])
                if any(_record_fact(item, "action") == "stop" for item in pending_items):
                    append_span(base, (record, *pending_items))
                else:
                    open_spans[key] = [record, *pending_items]
            elif action in {"continue", "stop"}:
                if key not in open_spans:
                    candidates = [candidate for candidate in open_spans if candidate[:4] == base]
                    if len(candidates) == 1:
                        key = candidates[0]
                if key not in open_spans:
                    pending.setdefault(base, []).append(record)
                elif action == "continue":
                    open_spans[key].append(record)
                else:
                    append_span(base, (*open_spans.pop(key), record))

    for key, endpoints in open_spans.items():
        if key[1] not in {"sounding-tie", "notated-tie"}:
            raise ValueError(f"oracle unclosed notation span: {key}")
        append_span(key[:4], tuple(endpoints))
    for key, endpoints in pending.items():
        if key[1] not in {"sounding-tie", "notated-tie", "wavy-line"}:
            raise ValueError(f"oracle unmatched notation endpoint: {key}")
        append_span(key, tuple(endpoints))
    return tuple(completed)


def _canonical_notation_spans(result: TemporalReadResult) -> tuple[OracleSemanticRecord, ...]:
    records: list[OracleSemanticRecord] = []
    for span in result.score.annotations.spans:
        endpoints: list[OracleValue] = []
        for endpoint in span.endpoints:
            endpoints.append(
                (
                    (
                        endpoint.anchor.part_id,
                        endpoint.anchor.measure_id,
                        endpoint.anchor.event_id,
                        endpoint.anchor.staff,
                        endpoint.anchor.voice,
                        endpoint.anchor.score_onset,
                    ),
                    endpoint.action,
                    endpoint.source_order,
                    endpoint.placement,
                    endpoint.smufl,
                    _canonical_trill_playback(endpoint.playback),
                    endpoint.tremolo_marks,
                    tuple(
                        (
                            item.value,
                            item.placement,
                            item.bracket,
                            item.parentheses,
                            item.smufl,
                        )
                        for item in endpoint.accidentals
                    ),
                    endpoint.text,
                    endpoint.source_id,
                    endpoint.line_type,
                    _canonical_bend_sound(endpoint.bend_sound),
                    endpoint.print_object,
                    endpoint.orientation,
                    endpoint.dash_length,
                    endpoint.space_length,
                    endpoint.time_only,
                )
            )
        records.append(
            _record(
                ("part", span.endpoints[0].anchor.part_id),
                "notation-span",
                span_kind=span.kind,
                number=span.number,
                endpoints=tuple(endpoints),
            )
        )
    return tuple(records)


def _time_endpoint_signature(record: OracleSemanticRecord) -> OracleValue:
    facts = dict(record.facts)
    return tuple(
        facts[name]
        for name in (
            "anchor",
            "action",
            "opening",
            "source_order",
            "component_order",
            "direction_id",
            "direction_type_id",
            "source_id",
            "system_relation",
            "source_type",
            "line_type",
            "dash_length",
            "space_length",
            "spread",
            "niente",
            "line_end",
            "end_length",
            "pedal_line",
            "pedal_sign",
            "pedal_abbreviated",
            "octave_size",
            "directive",
        )
    ) + (False, None)


def _ordered_time_records(
    records: tuple[OracleSemanticRecord, ...],
) -> tuple[OracleSemanticRecord, ...]:
    action_order = {"start": 0, "continue": 1, "stop": 2}
    return tuple(
        sorted(
            records,
            key=lambda record: (
                action_order[str(_record_fact(record, "action"))],
                _record_fact(record, "anchor")[3],  # type: ignore[index]
                int(_record_fact(record, "source_order")),
                int(_record_fact(record, "component_order")),
            ),
        )
    )


def _is_point_pedal_record(record: OracleSemanticRecord) -> bool:
    return (
        _record_fact(record, "span_kind") == "pedal"
        and _record_fact(record, "source_type") in {"start", "sostenuto", "stop"}
        and _record_fact(record, "pedal_line") is not True
        and _record_fact(record, "pedal_sign") is not False
    )


def _is_musescore_2_metadata(metadata: tuple[OracleSemanticRecord, ...]) -> bool:
    for record in metadata:
        if record.kind != "identification":
            continue
        encoding = _record_fact(record, "encoding")
        if not isinstance(encoding, tuple):
            continue
        software = encoding[2]
        if isinstance(software, tuple) and any(
            isinstance(item, str) and item.strip().casefold().startswith("musescore 2.")
            for item in software
        ):
            return True
    return False


def _resolve_time_spans(
    records: tuple[OracleSemanticRecord, ...],
    metadata: tuple[OracleSemanticRecord, ...],
    measures: tuple[OracleMeasure, ...],
) -> tuple[OracleSemanticRecord, ...]:
    completed: list[OracleSemanticRecord] = []
    completed_details: list[tuple[str, str, str | None, tuple[OracleSemanticRecord, ...]]] = []
    measure_map = {
        (measure.part_id, f"{measure.part_id}:m{measure.ordinal}"): measure for measure in measures
    }
    measure_starts: dict[tuple[str, str], Fraction] = {}
    running: dict[str, Fraction] = {}
    for measure in measures:
        start = running.get(measure.part_id, Fraction(0))
        measure_starts[(measure.part_id, f"{measure.part_id}:m{measure.ordinal}")] = start
        running[measure.part_id] = start + measure.extent

    def append_span(
        part_id: str,
        kind: str,
        number: str,
        opening: str | None,
        endpoints: tuple[OracleSemanticRecord, ...],
        extra_signatures: tuple[OracleValue, ...] = (),
    ) -> None:
        ordered = _ordered_time_records(endpoints)
        signatures = tuple(_time_endpoint_signature(item) for item in ordered) + extra_signatures
        completed.append(
            _record(
                ("part", part_id),
                "time-span",
                span_kind=kind,
                number=number,
                opening=opening,
                endpoints=signatures,
            )
        )
        completed_details.append((kind, number, opening, ordered))

    by_part: dict[str, list[OracleSemanticRecord]] = {}
    for record in records:
        by_part.setdefault(record.scope[1], []).append(record)
    for part_id, part_records in by_part.items():
        active: dict[tuple[str, str], list[OracleSemanticRecord]] = {}
        pending: dict[tuple[str, str], list[OracleSemanticRecord]] = {}
        for record in part_records:
            key = (
                str(_record_fact(record, "span_kind")),
                str(_record_fact(record, "number")),
            )
            action = _record_fact(record, "action")
            if action == "start":
                pending_items = pending.pop(key, [])
                if any(_record_fact(item, "action") == "stop" for item in pending_items):
                    append_span(
                        part_id,
                        key[0],
                        key[1],
                        str(_record_fact(record, "opening")),
                        (record, *pending_items),
                    )
                else:
                    active[key] = [record, *pending_items]
            elif action == "continue":
                if key in active:
                    active[key].append(record)
                else:
                    pending.setdefault(key, []).append(record)
            elif action == "stop":
                if key in active:
                    endpoints = (*active.pop(key), record)
                    opening = _record_fact(endpoints[0], "opening")
                    append_span(
                        part_id,
                        key[0],
                        key[1],
                        str(opening) if opening is not None else None,
                        endpoints,
                    )
                else:
                    pending.setdefault(key, []).append(record)

        if active and _is_musescore_2_metadata(metadata):
            grouped: dict[
                tuple[str, str | None],
                list[tuple[tuple[str, str], OracleSemanticRecord]],
            ] = {}
            for key, endpoints in active.items():
                if key[0] != "wedge" or len(endpoints) != 1:
                    continue
                start = endpoints[0]
                if _record_fact(start, "action") != "start" or _record_fact(
                    start, "opening"
                ) not in {"crescendo", "diminuendo"}:
                    continue
                anchor = _record_fact(start, "anchor")
                assert isinstance(anchor, tuple)
                grouped.setdefault((str(anchor[1]), anchor[4]), []).append((key, start))
            for (measure_id, staff), entries in grouped.items():
                entries.sort(
                    key=lambda item: (
                        _record_fact(item[1], "anchor")[2],  # type: ignore[index]
                        int(_record_fact(item[1], "source_order")),
                        int(_record_fact(item[1], "component_order")),
                    )
                )
                source_markers = tuple(
                    record
                    for record in part_records
                    if _record_fact(record, "span_kind") == "wedge"
                    and _record_fact(record, "anchor")[1] == measure_id  # type: ignore[index]
                    and _record_fact(record, "anchor")[4] == staff  # type: ignore[index]
                )
                recoveries: list[
                    tuple[tuple[str, str], OracleSemanticRecord, OracleValue, int, int]
                ] = []
                measure = measure_map[(part_id, measure_id)]
                measure_start = measure_starts[(part_id, measure_id)]
                if len(entries) == 1 and len(source_markers) == 3:
                    key, start = entries[0]
                    start_anchor = _record_fact(start, "anchor")
                    assert isinstance(start_anchor, tuple)
                    matches = [
                        detail
                        for detail in completed_details
                        if detail[0] == "wedge"
                        and detail[1] == key[1]
                        and detail[2] in {"crescendo", "diminuendo"}
                        and detail[2] != _record_fact(start, "opening")
                        and _record_fact(detail[3][-1], "action") == "stop"
                        and _record_fact(detail[3][-1], "anchor")[1] == measure_id  # type: ignore[index]
                        and _record_fact(detail[3][-1], "anchor")[4] == staff  # type: ignore[index]
                        and _record_fact(detail[3][-1], "anchor")[2] == start_anchor[2]  # type: ignore[index]
                    ]
                    if len(matches) == 1 and start_anchor[2] < measure.extent:
                        recoveries.append(
                            (
                                key,
                                start,
                                (
                                    part_id,
                                    measure_id,
                                    measure.extent,
                                    measure_start + measure.extent,
                                    staff,
                                    start_anchor[5],
                                ),
                                max(
                                    int(_record_fact(item, "source_order"))
                                    for item in source_markers
                                )
                                + 1,
                                0,
                            )
                        )
                elif len(entries) == 2 and len(source_markers) == 2:
                    (first_key, first), (second_key, second) = entries
                    first_anchor = _record_fact(first, "anchor")
                    second_anchor = _record_fact(second, "anchor")
                    assert isinstance(first_anchor, tuple) and isinstance(second_anchor, tuple)
                    if (
                        first_key[1] != second_key[1]
                        and first_anchor[2] == 0
                        and 0 < second_anchor[2] < measure.extent
                        and {
                            _record_fact(first, "opening"),
                            _record_fact(second, "opening"),
                        }
                        == {"crescendo", "diminuendo"}
                    ):
                        recoveries.extend(
                            (
                                (
                                    first_key,
                                    first,
                                    second_anchor,
                                    int(_record_fact(second, "source_order")),
                                    int(_record_fact(second, "component_order")),
                                ),
                                (
                                    second_key,
                                    second,
                                    (
                                        part_id,
                                        measure_id,
                                        measure.extent,
                                        measure_start + measure.extent,
                                        staff,
                                        second_anchor[5],
                                    ),
                                    max(
                                        int(_record_fact(item, "source_order"))
                                        for item in source_markers
                                    )
                                    + 1,
                                    0,
                                ),
                            )
                        )
                for key, start, anchor, source_order, component_order in recoveries:
                    inferred: OracleValue = (
                        anchor,
                        "stop",
                        None,
                        source_order,
                        component_order,
                        None,
                        None,
                        None,
                        None,
                        None,
                        None,
                        None,
                        None,
                        None,
                        None,
                        None,
                        None,
                        None,
                        None,
                        None,
                        None,
                        None,
                        True,
                        "musescore-2-adjacent-wedge-recovery",
                    )
                    append_span(
                        part_id,
                        key[0],
                        key[1],
                        str(_record_fact(start, "opening")),
                        (start,),
                        (inferred,),
                    )
                    active.pop(key, None)

        active = {
            key: endpoints
            for key, endpoints in active.items()
            if not all(_is_point_pedal_record(item) for item in endpoints)
        }
        pending = {
            key: endpoints
            for key, endpoints in pending.items()
            if not all(_is_point_pedal_record(item) for item in endpoints)
        }
        if active or pending:
            raise ValueError(f"oracle unresolved time spans: {active or pending}")
    return tuple(completed)


def _canonical_time_spans(result: TemporalReadResult) -> tuple[OracleSemanticRecord, ...]:
    records: list[OracleSemanticRecord] = []
    for span in result.score.annotations.time_spans:
        endpoints: list[OracleValue] = []
        for marker in span.endpoints:
            endpoints.append(
                (
                    _canonical_time_anchor(marker.anchor),
                    marker.action,
                    marker.opening,
                    marker.source_order,
                    marker.component_order,
                    marker.direction_id,
                    marker.direction_type_id,
                    marker.source_id,
                    marker.system_relation,
                    marker.source_type,
                    marker.line_type,
                    marker.dash_length,
                    marker.space_length,
                    marker.spread,
                    marker.niente,
                    marker.line_end,
                    marker.end_length,
                    marker.pedal_line,
                    marker.pedal_sign,
                    marker.pedal_abbreviated,
                    marker.octave_size,
                    marker.directive,
                    marker.inferred,
                    marker.inference_reason,
                )
            )
        records.append(
            _record(
                ("part", span.endpoints[0].anchor.part_id),
                "time-span",
                span_kind=span.kind,
                number=span.number,
                opening=span.opening,
                endpoints=tuple(endpoints),
            )
        )
    return tuple(records)


def _canonical_lyric_record(lyric: object) -> OracleSemanticRecord:
    anchor = lyric.anchor  # type: ignore[attr-defined]
    return _record(
        (
            "part",
            anchor.part_id,
            "measure",
            anchor.measure_id.rsplit(":m", 1)[-1],
            "event",
            anchor.event_id,
        ),
        "lyric",
        anchor=(
            anchor.part_id,
            anchor.measure_id,
            anchor.event_id,
            anchor.staff,
            anchor.voice,
            anchor.score_onset,
        ),
        number=lyric.number,  # type: ignore[attr-defined]
        name=lyric.name,  # type: ignore[attr-defined]
        syllabic=lyric.syllabic,  # type: ignore[attr-defined]
        text=lyric.text,  # type: ignore[attr-defined]
        source_order=lyric.source_order,  # type: ignore[attr-defined]
        segments=tuple(
            (item.text, item.syllabic, item.elision_before, item.elision_smufl)
            for item in lyric.segments  # type: ignore[attr-defined]
        ),
        extend_present=lyric.extend_present,  # type: ignore[attr-defined]
        extend=lyric.extend,  # type: ignore[attr-defined]
        laughing=lyric.laughing,  # type: ignore[attr-defined]
        humming=lyric.humming,  # type: ignore[attr-defined]
        end_line=lyric.end_line,  # type: ignore[attr-defined]
        end_paragraph=lyric.end_paragraph,  # type: ignore[attr-defined]
        print_object=lyric.print_object,  # type: ignore[attr-defined]
        time_only=lyric.time_only,  # type: ignore[attr-defined]
        source_id=lyric.source_id,  # type: ignore[attr-defined]
        placement=lyric.placement,  # type: ignore[attr-defined]
    )


def _canonical_harmony_record(harmony: object) -> OracleSemanticRecord:
    anchor = harmony.anchor  # type: ignore[attr-defined]
    chords: list[OracleValue] = []
    for chord in harmony.chords:  # type: ignore[attr-defined]
        numeral = chord.numeral
        bass = chord.bass
        chords.append(
            (
                chord.root_step,
                chord.root_alter,
                (
                    numeral.root,
                    numeral.alter,
                    numeral.key_fifths,
                    numeral.key_mode,
                )
                if numeral is not None
                else None,
                chord.function,
                chord.kind,
                chord.kind_text,
                chord.use_symbols,
                chord.stack_degrees,
                chord.parentheses_degrees,
                chord.bracket_degrees,
                chord.inversion,
                (bass.step, bass.alter) if bass is not None else None,
                tuple(
                    (
                        degree.value,
                        degree.alter,
                        degree.degree_type,
                        degree.print_object,
                        degree.symbol,
                        degree.value_text,
                        degree.type_text,
                        degree.plus_minus,
                    )
                    for degree in chord.degrees
                ),
            )
        )
    frame = harmony.frame  # type: ignore[attr-defined]
    frame_value: OracleValue = None
    if frame is not None:
        frame_value = (
            frame.strings,
            frame.frets,
            frame.first_fret,
            frame.first_fret_text,
            frame.first_fret_location,
            tuple((item.string, item.fret, item.fingering, item.barre) for item in frame.notes),
            frame.unplayed,
        )
    return _record(
        ("part", anchor.part_id, "measure", anchor.measure_id.rsplit(":m", 1)[-1]),
        "harmony",
        anchor=_canonical_time_anchor(anchor),
        root_step=harmony.root_step,  # type: ignore[attr-defined]
        root_alter=harmony.root_alter,  # type: ignore[attr-defined]
        harmony_kind=harmony.kind,  # type: ignore[attr-defined]
        kind_text=harmony.kind_text,  # type: ignore[attr-defined]
        source_order=harmony.source_order,  # type: ignore[attr-defined]
        chords=tuple(chords),
        frame=frame_value,
        harmony_type=harmony.harmony_type,  # type: ignore[attr-defined]
        print_object=harmony.print_object,  # type: ignore[attr-defined]
        print_frame=harmony.print_frame,  # type: ignore[attr-defined]
        arrangement=harmony.arrangement,  # type: ignore[attr-defined]
        source_id=harmony.source_id,  # type: ignore[attr-defined]
        system_relation=harmony.system_relation,  # type: ignore[attr-defined]
    )


def _canonical_figured_bass_record(value: object) -> OracleSemanticRecord:
    anchor = value.anchor  # type: ignore[attr-defined]
    return _record(
        ("part", anchor.part_id, "measure", anchor.measure_id.rsplit(":m", 1)[-1]),
        "figured-bass",
        anchor=(
            anchor.part_id,
            anchor.measure_id,
            anchor.event_id,
            anchor.staff,
            anchor.voice,
            anchor.score_onset,
        ),
        figures=tuple(
            (
                item.prefix,
                item.number,
                item.suffix,
                item.extend_present,
                item.extend,
            )
            for item in value.figures  # type: ignore[attr-defined]
        ),
        duration=value.duration,  # type: ignore[attr-defined]
        source_order=value.source_order,  # type: ignore[attr-defined]
        parentheses=value.parentheses,  # type: ignore[attr-defined]
        print_object=value.print_object,  # type: ignore[attr-defined]
        print_dot=value.print_dot,  # type: ignore[attr-defined]
        print_spacing=value.print_spacing,  # type: ignore[attr-defined]
        placement=value.placement,  # type: ignore[attr-defined]
        source_id=value.source_id,  # type: ignore[attr-defined]
    )


def _root_xml(source: bytes) -> bytes:
    if not source.startswith(b"PK"):
        return source
    with ZipFile(BytesIO(source)) as archive:
        container = element_tree.fromstring(archive.read("META-INF/container.xml"))
        rootfile = next(
            (
                item
                for item in container.iter()
                if _local_name(item.tag) == "rootfile" and item.get("full-path")
            ),
            None,
        )
        if rootfile is None:
            raise ValueError("oracle MXL container has no rootfile")
        return archive.read(rootfile.get("full-path", ""))


_DOCTYPE_VERSION = re.compile(rb"<!DOCTYPE\s+\S+\s+PUBLIC\s+[^>]*MusicXML\s+([0-9.]+)")
_ZIP_SIGNATURES = (b"PK\x03\x04", b"PK\x05\x06", b"PK\x07\x08")


def _standard_version(xml: bytes, root: element_tree.Element) -> str:
    value = root.get("version")
    if value is None:
        match = _DOCTYPE_VERSION.search(xml)
        if match is None:
            raise ValueError("oracle source has no MusicXML version evidence")
        value = match.group(1).decode("ascii")
    return "4.1-draft" if value == "4.1" else value


def _source_read_provenance(
    source: bytes,
    xml: bytes,
    root: element_tree.Element,
) -> OracleReadProvenance:
    return OracleReadProvenance(
        source_sha256=hashlib.sha256(source).hexdigest(),
        source_format=(
            "application/vnd.recordare.musicxml"
            if source.startswith(_ZIP_SIGNATURES)
            else "application/vnd.recordare.musicxml+xml"
        ),
        musicxml_version=_standard_version(xml, root),
        document_form=_local_name(root.tag),
    )


def _identity(value: object) -> tuple[str, str]:
    return (str(value.kind), value.value)  # type: ignore[attr-defined]


def _reference(value: object) -> tuple[str, str]:
    return (str(value.target_kind), value.target_id)  # type: ignore[attr-defined]


def _specified(value: object) -> OracleValue:
    item = value.value  # type: ignore[attr-defined]
    return (
        str(value.state),  # type: ignore[attr-defined]
        str(item) if hasattr(item, "value") else item,
    )


def source_package_oracle(source: bytes, logical_name: str | None) -> OraclePackageFacts:
    """Derive the facts promised by the current temporal package from raw bytes."""

    xml = _root_xml(source)
    root = element_tree.fromstring(xml)
    digest = hashlib.sha256(source).hexdigest()
    source_id = ("source-document", f"source:{digest}")
    score_id = ("score", f"score:{digest}")
    source_format = "mxl" if source.startswith(_ZIP_SIGNATURES) else "musicxml"
    declared_version = root.get("version")
    document_form = _local_name(root.tag)
    return OraclePackageFacts(
        schema_id="org.teachmemusic.canonical-music-package",
        schema_version="2.0.0",
        package_id=("package", f"package:{digest}"),
        document_id=score_id,
        source_documents=(source_id,),
        root_documents=(score_id,),
        completeness="temporal-only",
        source=(
            source_id,
            ("explicit-value", source_format),
            (("explicit-value", logical_name) if logical_name is not None else ("unknown", None)),
            ("explicit-value", digest),
            ("explicit-value", len(source)),
            (
                ("explicit-value", declared_version)
                if declared_version is not None
                else ("unknown", None)
            ),
            ("explicit-value", _standard_version(xml, root)),
            ("explicit-value", document_form),
        ),
        source_map=(
            (
                score_id,
                ((source_id, f"/{document_form}", None, None, None),),
            ),
        ),
    )


def canonical_package_oracle(package: CanonicalMusicPackage) -> OraclePackageFacts:
    """Project the existing public temporal package into independent primitives."""

    if len(package.documents) != 1 or len(package.provenance.sources) != 1:
        raise ValueError("oracle expected one-document temporal package")
    document = package.documents[0]
    if not isinstance(document, ScoreDocument) or not isinstance(
        document.content, TemporalScoreContent
    ):
        raise ValueError("oracle expected temporal score content")
    source = package.provenance.sources[0]
    return OraclePackageFacts(
        schema_id=package.schema_id,
        schema_version=package.schema_version,
        package_id=_identity(package.id),
        document_id=_identity(document.id),
        source_documents=tuple(_reference(item) for item in document.source_documents),
        root_documents=tuple(_reference(item) for item in package.root_documents),
        completeness=document.content.completeness,
        source=(
            _identity(source.id),
            _specified(source.source_format),
            _specified(source.logical_name),
            _specified(source.sha256),
            _specified(source.byte_length),
            _specified(source.declared_musicxml_version),
            _specified(source.validated_musicxml_version),
            _specified(source.document_form),
        ),
        source_map=tuple(
            (
                _reference(entry.entity),
                tuple(
                    (
                        _reference(location.source_document),
                        location.logical_path,
                        location.line,
                        location.column,
                        location.source_ordinal,
                    )
                    for location in entry.locations
                ),
            )
            for entry in package.provenance.source_map
        ),
    )


def _source_link(element: element_tree.Element) -> OracleValue:
    xlink = "{http://www.w3.org/1999/xlink}"
    return tuple(
        element.get(f"{xlink}{name}")
        for name in ("href", "type", "role", "title", "show", "actuate")
    )


def _source_opus_item(element: element_tree.Element) -> OracleValue:
    kind = _local_name(element.tag)
    if kind == "opus":
        return (
            kind,
            None,
            None,
            _child_value(element, "title"),
            tuple(
                _source_opus_item(child) for child in element if _local_name(child.tag) != "title"
            ),
        )
    return (
        kind,
        _source_link(element),
        _yes_no(element.get("new-page")) if kind == "score" else None,
        None,
        (),
    )


def source_auxiliary_oracle(source: bytes) -> OracleAuxiliary:
    """Read opus/sounds semantics without the production boundary or mapper."""

    xml = _root_xml(source)
    root = element_tree.fromstring(xml)
    kind = _local_name(root.tag)
    version = _standard_version(xml, root)
    if kind == "opus":
        return OracleAuxiliary(
            kind=kind,
            version=version,
            title=_child_value(root, "title"),
            items=tuple(
                _source_opus_item(child) for child in root if _local_name(child.tag) != "title"
            ),
        )
    if kind == "sounds":
        return OracleAuxiliary(
            kind=kind,
            version=version,
            title=None,
            items=tuple(
                (
                    sound.get("id") or "",
                    _yes_no(sound.get("primary")),
                    tuple(
                        (
                            _local_name(mapping.tag),
                            mapping.text or "",
                            _yes_no(mapping.get("primary")),
                            mapping.get("number"),
                        )
                        for mapping in sound
                    ),
                )
                for sound in _children(root, "sound")
            ),
        )
    raise ValueError(f"oracle expected auxiliary root, got {kind}")


def _canonical_link(value: object) -> OracleValue:
    return tuple(
        getattr(value, name) for name in ("href", "link_type", "role", "title", "show", "actuate")
    )


def _canonical_opus_item(item: OpusItem) -> OracleValue:
    return (
        item.kind,
        _canonical_link(item.link) if item.link is not None else None,
        item.new_page,
        item.title,
        tuple(_canonical_opus_item(child) for child in item.children),
    )


def canonical_auxiliary_oracle(document: AuxiliaryDocument) -> OracleAuxiliary:
    """Project canonical auxiliary content into independent primitives."""

    if isinstance(document, OpusCatalog):
        return OracleAuxiliary(
            kind="opus",
            version=document.version,
            title=document.title,
            items=tuple(_canonical_opus_item(item) for item in document.items),
        )
    if isinstance(document, SoundCatalog):
        return OracleAuxiliary(
            kind="sounds",
            version=document.version,
            title=None,
            items=tuple(
                (
                    entry.id,
                    entry.primary,
                    tuple(
                        (mapping.kind, mapping.value, mapping.primary, mapping.ensemble_size)
                        for mapping in entry.mappings
                    ),
                )
                for entry in document.entries
            ),
        )
    raise TypeError(f"unsupported auxiliary document: {type(document)!r}")


def _part_measure_bodies(
    root: element_tree.Element,
) -> tuple[tuple[str, tuple[tuple[element_tree.Element, element_tree.Element], ...]], ...]:
    root_name = _local_name(root.tag)
    if root_name == "score-partwise":
        return tuple(
            (
                part.get("id", ""),
                tuple((measure, measure) for measure in _children(part, "measure")),
            )
            for part in _children(root, "part")
        )
    if root_name != "score-timewise":
        raise ValueError(f"oracle expected a MusicXML score root, got {root_name}")

    ordered_ids = [
        item.get("id", "")
        for part_list in _children(root, "part-list")
        for item in _children(part_list, "score-part")
    ]
    by_part: dict[str, list[tuple[element_tree.Element, element_tree.Element]]] = {
        part_id: [] for part_id in ordered_ids
    }
    for measure in _children(root, "measure"):
        for part in _children(measure, "part"):
            part_id = part.get("id", "")
            by_part.setdefault(part_id, []).append((measure, part))
    return tuple((part_id, tuple(by_part[part_id])) for part_id in by_part)


def source_oracle(source: bytes) -> OracleScore:
    """Extract exact temporal note facts without using production parsing code."""

    xml = _root_xml(source)
    root = element_tree.fromstring(xml)
    measures: list[OracleMeasure] = []
    events: list[OracleEvent] = []
    attributes: list[OracleSemanticRecord] = []
    barlines: list[OracleSemanticRecord] = []
    span_endpoints: list[OracleSemanticRecord] = []
    event_marks: list[OracleSemanticRecord] = []
    directions: list[OracleSemanticRecord] = []
    time_span_endpoints: list[OracleSemanticRecord] = []
    lyrics: list[OracleSemanticRecord] = []
    harmonies: list[OracleSemanticRecord] = []
    figured_bass: list[OracleSemanticRecord] = []
    layouts = list(_source_score_layout(root))
    presentations = list(_source_residual_presentations(root))
    note_playback: list[OracleSemanticRecord] = []
    sounds: list[OracleSemanticRecord] = []
    links = list(_source_score_links(root))
    parts = _part_measure_bodies(root)
    for part_id, bodies in parts:
        divisions: int | None = None
        part_score_onset = Fraction(0)
        for measure_ordinal, (header, body) in enumerate(bodies, start=1):
            number = header.get("number") or str(measure_ordinal)
            cursor = Fraction(0)
            extent = Fraction(0)
            measure_events: list[OracleEvent] = []
            measure_event_source_orders: list[int] = []
            pending_figured_bass: list[tuple[element_tree.Element, int, Fraction, int | None]] = []
            measure_layout = _source_measure_layout(
                header,
                body,
                part_id=part_id,
                measure_ordinal=measure_ordinal,
            )
            if measure_layout is not None:
                layouts.append(measure_layout)
            link_order = 0
            bookmark_order = 0
            last_event_index: int | None = None
            next_chord_group = 1
            for source_order, child in enumerate(body, start=1):
                tag = _local_name(child.tag)
                if tag == "attributes":
                    attributes.append(
                        _source_attribute_record(
                            child,
                            part_id=part_id,
                            measure_ordinal=measure_ordinal,
                            onset=cursor,
                            source_order=source_order,
                        )
                    )
                    value = _text(child, "divisions")
                    if value is not None:
                        divisions = int(value)
                    continue
                if tag in {"backup", "forward"}:
                    raw_duration = int(_text(child, "duration") or "0")
                    delta = Fraction(raw_duration, divisions or 1)
                    source_after = cursor + (delta if tag == "forward" else -delta)
                    cursor = Fraction(0) if tag == "backup" and source_after < 0 else source_after
                    extent = max(extent, cursor)
                    last_event_index = None
                    continue
                if tag == "barline":
                    barlines.append(
                        _source_barline_record(
                            child,
                            part_id=part_id,
                            measure_ordinal=measure_ordinal,
                            onset=cursor,
                            source_order=source_order,
                        )
                    )
                    continue
                if tag == "direction":
                    sound = _child(child, "sound")
                    if sound is not None:
                        sound_onset = cursor
                        if _child(sound, "offset") is None:
                            direction_offset = _child_value(child, "offset")
                            if direction_offset is not None:
                                sound_onset += Fraction(direction_offset) / (divisions or 1)
                        sounds.append(
                            _source_sound_record(
                                sound,
                                part_id=part_id,
                                measure_ordinal=measure_ordinal,
                                onset=sound_onset,
                                score_onset=part_score_onset,
                                divisions=divisions,
                                source_order=source_order,
                            )
                        )
                    mapped_directions, mapped_spans = _source_direction_records(
                        child,
                        part_id=part_id,
                        measure_ordinal=measure_ordinal,
                        onset=cursor,
                        score_onset=part_score_onset,
                        divisions=divisions,
                        source_order=source_order,
                    )
                    directions.extend(mapped_directions)
                    time_span_endpoints.extend(mapped_spans)
                    continue
                if tag == "sound":
                    sounds.append(
                        _source_sound_record(
                            child,
                            part_id=part_id,
                            measure_ordinal=measure_ordinal,
                            onset=cursor,
                            score_onset=part_score_onset,
                            divisions=divisions,
                            source_order=source_order,
                        )
                    )
                    continue
                if tag == "link":
                    link_order += 1
                    links.append(
                        _source_measure_link_record(
                            child,
                            part_id=part_id,
                            measure_ordinal=measure_ordinal,
                            kind_order=link_order,
                        )
                    )
                    continue
                if tag == "bookmark":
                    bookmark_order += 1
                    links.append(
                        _source_measure_link_record(
                            child,
                            part_id=part_id,
                            measure_ordinal=measure_ordinal,
                            kind_order=bookmark_order,
                        )
                    )
                    continue
                if tag == "harmony":
                    harmonies.append(
                        _source_harmony_record(
                            child,
                            part_id=part_id,
                            measure_ordinal=measure_ordinal,
                            onset=cursor,
                            score_onset=part_score_onset,
                            divisions=divisions,
                            source_order=source_order,
                        )
                    )
                    continue
                if tag == "figured-bass":
                    pending_figured_bass.append((child, source_order, cursor, divisions))
                    continue
                if tag != "note":
                    continue

                chord = _child(child, "chord") is not None
                grace = _child(child, "grace") is not None
                cue = _child(child, "cue") is not None
                rest = _child(child, "rest")
                pitch_element = _child(child, "pitch")
                unpitched = _child(child, "unpitched")
                if rest is not None:
                    kind = "rest"
                    pitch = None
                elif pitch_element is not None:
                    kind = "pitched"
                    pitch = (
                        _text(pitch_element, "step") or "",
                        Fraction(_text(pitch_element, "alter") or "0"),
                        int(_text(pitch_element, "octave") or "0"),
                    )
                elif unpitched is not None:
                    kind = "unpitched"
                    pitch = None
                else:
                    raise ValueError("oracle note has no pitch, rest, or unpitched value")

                raw_duration = int(_text(child, "duration") or "0")
                duration = Fraction(raw_duration, divisions or 1)
                onset = (
                    measure_events[last_event_index].onset
                    if chord and last_event_index is not None
                    else cursor
                )
                chord_group = None
                if chord:
                    if last_event_index is None or measure_events[last_event_index].kind == "rest":
                        raise ValueError("oracle chord follower has no preceding pitched event")
                    previous = measure_events[last_event_index]
                    chord_group = previous.chord_group
                    if chord_group is None:
                        chord_group = next_chord_group
                        next_chord_group += 1
                        measure_events[last_event_index] = replace(
                            previous, chord_group=chord_group
                        )
                time_modification_element = _child(child, "time-modification")
                time_modification = (
                    (
                        int(_text(time_modification_element, "actual-notes") or "0"),
                        int(_text(time_modification_element, "normal-notes") or "0"),
                    )
                    if time_modification_element is not None
                    else None
                )
                event = OracleEvent(
                    part_id=part_id,
                    measure_ordinal=measure_ordinal,
                    measure_number=number,
                    event_ordinal=len(measure_events) + 1,
                    kind=kind,
                    onset=onset,
                    duration=duration,
                    staff=_text(child, "staff") or "1",
                    voice=_text(child, "voice") or "1",
                    pitch=pitch,
                    chord_group=chord_group,
                    grace=grace,
                    cue=cue,
                    written_type=_text(child, "type"),
                    dots=len(_children(child, "dot")),
                    time_modification=time_modification,
                )
                measure_events.append(event)
                measure_event_source_orders.append(source_order)
                note_playback.append(
                    _source_note_playback(
                        child,
                        event,
                        divisions=divisions,
                        source_order=source_order,
                    )
                )
                presentations.extend(
                    _source_event_presentations(
                        child,
                        part_id=part_id,
                        measure_ordinal=measure_ordinal,
                        source_order=source_order,
                    )
                )
                mapped_spans, mapped_marks = _source_note_annotations(
                    child,
                    part_id=part_id,
                    measure_ordinal=measure_ordinal,
                    source_order=source_order,
                    onset=onset,
                    score_onset=part_score_onset,
                    staff=event.staff,
                    voice=event.voice,
                    pitch=event.pitch,
                )
                span_endpoints.extend(mapped_spans)
                event_marks.extend(mapped_marks)
                lyrics.extend(
                    _source_lyrics(
                        child,
                        part_id=part_id,
                        measure_ordinal=measure_ordinal,
                        source_order=source_order,
                        score_onset=part_score_onset + onset,
                        staff=event.staff,
                        voice=event.voice,
                    )
                )
                last_event_index = len(measure_events) - 1
                if not chord:
                    cursor += duration
                extent = max(extent, cursor, onset + duration)

            for bass, bass_order, location, bass_divisions in pending_figured_bass:
                candidate_indices = [
                    index
                    for index, event in enumerate(measure_events)
                    if event.onset >= location
                    and not event.grace
                    and (
                        event.chord_group is None
                        or not any(
                            previous.chord_group == event.chord_group
                            for previous in measure_events[:index]
                        )
                    )
                ]
                if not candidate_indices:
                    continue
                earliest = min(measure_events[index].onset for index in candidate_indices)
                first = [
                    index for index in candidate_indices if measure_events[index].onset == earliest
                ]
                if len(first) != 1:
                    continue
                event_index = first[0]
                figured_bass.append(
                    _source_figured_bass_record(
                        bass,
                        part_id=part_id,
                        measure_ordinal=measure_ordinal,
                        event_id=(
                            f"{part_id}:m{measure_ordinal}:"
                            f"n{measure_event_source_orders[event_index]}"
                        ),
                        event=measure_events[event_index],
                        score_onset=part_score_onset + measure_events[event_index].onset,
                        divisions=bass_divisions,
                        source_order=bass_order,
                    )
                )

            measures.append(
                OracleMeasure(part_id, measure_ordinal, number, extent, len(measure_events))
            )
            events.extend(measure_events)
            part_score_onset += extent
    source_metadata = _source_metadata(root)
    oracle_measures = tuple(measures)
    return OracleScore(
        tuple(part_id for part_id, _ in parts),
        oracle_measures,
        tuple(events),
        source_metadata,
        tuple(attributes),
        tuple(barlines),
        tuple(span_endpoints),
        tuple(event_marks),
        tuple(directions),
        tuple(time_span_endpoints),
        _resolve_notation_spans(tuple(span_endpoints)),
        _resolve_time_spans(tuple(time_span_endpoints), source_metadata, oracle_measures),
        tuple(lyrics),
        tuple(harmonies),
        tuple(figured_bass),
        tuple(layouts),
        tuple(presentations),
        (*_source_part_playback(root), *note_playback, *sounds),
        tuple(links),
        _source_read_provenance(source, xml, root),
    )


def canonical_oracle(result: TemporalReadResult) -> OracleScore:
    """Project the canonical score into the independently defined oracle shape."""

    measures: list[OracleMeasure] = []
    events: list[OracleEvent] = []
    attributes: list[OracleSemanticRecord] = []
    barlines: list[OracleSemanticRecord] = []
    span_endpoints: list[OracleSemanticRecord] = []
    event_marks: list[OracleSemanticRecord] = []
    directions: list[OracleSemanticRecord] = []
    time_span_endpoints: list[OracleSemanticRecord] = []
    layouts = list(_canonical_score_layout(result))
    presentations = list(_canonical_residual_presentations(result))
    note_playback: list[OracleSemanticRecord] = []
    sounds: list[OracleSemanticRecord] = []
    for part in result.score.parts:
        for measure in part.measures:
            if measure.layout is not None:
                layouts.append(
                    _canonical_measure_layout(
                        measure.layout,
                        part_id=part.id,
                        measure_ordinal=measure.ordinal,
                    )
                )
            attributes.extend(
                _canonical_attribute_record(item, part_id=part.id, measure_ordinal=measure.ordinal)
                for item in measure.attributes
            )
            barlines.extend(
                _canonical_barline_record(item, part_id=part.id, measure_ordinal=measure.ordinal)
                for item in measure.barlines
            )
            directions.extend(
                _canonical_direction_record(item, part_id=part.id, measure_ordinal=measure.ordinal)
                for item in measure.directions
            )
            time_span_endpoints.extend(
                _canonical_time_span_record(item, part_id=part.id, measure_ordinal=measure.ordinal)
                for item in measure.time_span_markers
            )
            sounds.extend(
                _canonical_sound_record(
                    item,
                    part_id=part.id,
                    measure_ordinal=measure.ordinal,
                )
                for item in measure.sounds
            )
            chord_numbers: dict[str, int] = {}
            next_chord_number = 1
            for event_ordinal, event in enumerate(measure.events, start=1):
                note_playback.append(
                    _canonical_note_playback(
                        event,
                        part_id=part.id,
                        measure_ordinal=measure.ordinal,
                    )
                )
                presentations.extend(
                    _canonical_event_presentations(
                        event,
                        part_id=part.id,
                        measure_ordinal=measure.ordinal,
                    )
                )
                span_endpoints.extend(
                    _canonical_span_record(
                        item,
                        part_id=part.id,
                        measure_ordinal=measure.ordinal,
                        measure_id=measure.id,
                        event=event,
                    )
                    for item in event.span_markers
                )
                event_marks.extend(
                    _canonical_event_mark_record(
                        item,
                        part_id=part.id,
                        measure_ordinal=measure.ordinal,
                        measure_id=measure.id,
                        event=event,
                    )
                    for item in event.event_markers
                )
                chord_group = None
                if event.chord_id is not None:
                    if event.chord_id not in chord_numbers:
                        chord_numbers[event.chord_id] = next_chord_number
                        next_chord_number += 1
                    chord_group = chord_numbers[event.chord_id]
                pitch = (
                    (event.pitch.step, event.pitch.alter, event.pitch.octave)
                    if event.pitch is not None and event.kind == "pitched"
                    else None
                )
                events.append(
                    OracleEvent(
                        part_id=part.id,
                        measure_ordinal=measure.ordinal,
                        measure_number=measure.number,
                        event_ordinal=event_ordinal,
                        kind=event.kind,
                        onset=event.onset,
                        duration=event.duration,
                        staff=event.staff,
                        voice=event.voice,
                        pitch=pitch,
                        chord_group=chord_group,
                        grace=event.grace,
                        cue=event.cue,
                        written_type=event.written_type,
                        dots=event.dots,
                        time_modification=event.time_modification,
                    )
                )
            measures.append(
                OracleMeasure(
                    part.id,
                    measure.ordinal,
                    measure.number,
                    measure.extent,
                    len(measure.events),
                )
            )
    return OracleScore(
        tuple(part.id for part in result.score.parts),
        tuple(measures),
        tuple(events),
        _canonical_metadata(result),
        tuple(attributes),
        tuple(barlines),
        tuple(span_endpoints),
        tuple(event_marks),
        tuple(directions),
        tuple(time_span_endpoints),
        _canonical_notation_spans(result),
        _canonical_time_spans(result),
        tuple(_canonical_lyric_record(item) for item in result.score.annotations.lyrics),
        tuple(_canonical_harmony_record(item) for item in result.score.annotations.harmonies),
        tuple(
            _canonical_figured_bass_record(item) for item in result.score.annotations.figured_bass
        ),
        tuple(layouts),
        tuple(presentations),
        (*_canonical_part_playback(result), *note_playback, *sounds),
        _canonical_score_links(result),
        OracleReadProvenance(
            result.source_sha256,
            result.source_format,
            result.musicxml_version,
            result.document_form,
        ),
    )
