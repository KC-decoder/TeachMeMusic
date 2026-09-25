"""Map reusable MusicXML presentation attributes without musical semantics."""

from __future__ import annotations

from fractions import Fraction
from typing import Protocol

from lxml import etree

from teachmemusic.score.v2.presentation import (
    DisplayTextSegment,
    NameDisplay,
    PresentationNumber,
    PresentationStyle,
)

_XML_LANG = "{http://www.w3.org/XML/1998/namespace}lang"
_XML_SPACE = "{http://www.w3.org/XML/1998/namespace}space"


class PresentationAudit(Protocol):
    def take(self, element: etree._Element | None) -> etree._Element | None: ...

    def attr(self, element: etree._Element, name: str) -> str | None: ...

    def value(self, element: etree._Element | None) -> str | None: ...


def _fraction(value: str | None, name: str) -> Fraction | None:
    if value is None:
        return None
    try:
        return Fraction(value)
    except (ValueError, ZeroDivisionError) as error:
        raise ValueError(f"invalid {name}") from error


def _number_or_keyword(value: str | None, name: str) -> PresentationNumber | None:
    if value is None:
        return None
    if value in {
        "normal",
        "xx-small",
        "x-small",
        "small",
        "medium",
        "large",
        "x-large",
        "xx-large",
    }:
        return PresentationNumber(keyword=value)
    return PresentationNumber(number=_fraction(value, name))


def _integer(value: str | None, name: str) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except ValueError as error:
        raise ValueError(f"invalid {name}") from error


def map_presentation_style(
    element: etree._Element, audit: PresentationAudit
) -> PresentationStyle | None:
    """Preserve the shared position, font, alignment, and text-style surface."""

    attributes = {
        name: audit.attr(element, source)
        for name, source in (
            ("default_x", "default-x"),
            ("default_y", "default-y"),
            ("relative_x", "relative-x"),
            ("relative_y", "relative-y"),
            ("color", "color"),
            ("font_family", "font-family"),
            ("font_style", "font-style"),
            ("font_size", "font-size"),
            ("font_weight", "font-weight"),
            ("justify", "justify"),
            ("halign", "halign"),
            ("valign", "valign"),
            ("enclosure", "enclosure"),
            ("letter_spacing", "letter-spacing"),
            ("line_height", "line-height"),
            ("underline", "underline"),
            ("overline", "overline"),
            ("line_through", "line-through"),
            ("rotation", "rotation"),
            ("text_direction", "dir"),
            ("language", _XML_LANG),
            ("space", _XML_SPACE),
        )
    }
    if not any(value is not None for value in attributes.values()):
        return None
    return PresentationStyle(
        default_x=_fraction(attributes["default_x"], "default-x"),
        default_y=_fraction(attributes["default_y"], "default-y"),
        relative_x=_fraction(attributes["relative_x"], "relative-x"),
        relative_y=_fraction(attributes["relative_y"], "relative-y"),
        color=attributes["color"],
        font_family=attributes["font_family"],
        font_style=attributes["font_style"],
        font_size=_number_or_keyword(attributes["font_size"], "font-size"),
        font_weight=attributes["font_weight"],
        justify=attributes["justify"],
        halign=attributes["halign"],
        valign=attributes["valign"],
        enclosure=attributes["enclosure"],
        letter_spacing=_number_or_keyword(attributes["letter_spacing"], "letter-spacing"),
        line_height=_number_or_keyword(attributes["line_height"], "line-height"),
        underline=_integer(attributes["underline"], "underline"),
        overline=_integer(attributes["overline"], "overline"),
        line_through=_integer(attributes["line_through"], "line-through"),
        rotation=_fraction(attributes["rotation"], "rotation"),
        text_direction=attributes["text_direction"],
        language=attributes["language"],
        space=attributes["space"],
    )


def map_name_display(
    element: etree._Element | None, audit: PresentationAudit
) -> NameDisplay | None:
    """Map an ordered part/group display without flattening accidentals."""

    if element is None:
        return None
    audit.take(element)
    segments = []
    for child in element:
        if not isinstance(child.tag, str):
            continue
        kind = etree.QName(child).localname
        if kind in {"display-text", "accidental-text"}:
            segments.append(
                DisplayTextSegment(
                    kind,
                    audit.value(child) or "",
                    map_presentation_style(child, audit),
                )
            )
    return NameDisplay(tuple(segments))
