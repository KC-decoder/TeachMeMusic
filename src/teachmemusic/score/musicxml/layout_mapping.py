"""Map MusicXML defaults, credits, and measure print layout."""

from __future__ import annotations

from fractions import Fraction
from typing import Protocol

from lxml import etree

from teachmemusic.score.v2.layout import (
    AppearanceValue,
    Credit,
    CreditItem,
    LayoutDefaults,
    LayoutMargins,
    LayoutScaling,
    LyricFont,
    LyricLanguage,
    MeasurePrintLayout,
    PageLayout,
    ScoreLayout,
    StaffLayout,
    SystemLayout,
)

from .presentation_mapping import map_name_display, map_presentation_style

_XML_LANG = "{http://www.w3.org/XML/1998/namespace}lang"


class LayoutAudit(Protocol):
    def take(self, element: etree._Element | None) -> etree._Element | None: ...

    def attr(self, element: etree._Element, name: str) -> str | None: ...

    def child(self, element: etree._Element, name: str) -> etree._Element | None: ...

    def children(self, element: etree._Element, name: str) -> tuple[etree._Element, ...]: ...

    def value(self, element: etree._Element | None) -> str | None: ...

    def child_value(self, element: etree._Element, name: str) -> str | None: ...


def _fraction(value: str | None, name: str) -> Fraction | None:
    if value is None:
        return None
    try:
        return Fraction(value)
    except (ValueError, ZeroDivisionError) as error:
        raise ValueError(f"invalid {name}") from error


def _integer(value: str | None, name: str) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except ValueError as error:
        raise ValueError(f"invalid {name}") from error


def _yes_no(value: str | None, name: str) -> bool | None:
    if value is None:
        return None
    if value not in {"yes", "no"}:
        raise ValueError(f"invalid {name}")
    return value == "yes"


def _page_layout(element: etree._Element | None, audit: LayoutAudit) -> PageLayout | None:
    if element is None:
        return None
    audit.take(element)
    margins = []
    for item in audit.children(element, "page-margins"):
        margins.append(
            LayoutMargins(
                audit.attr(item, "type"),
                _fraction(audit.child_value(item, "left-margin"), "left-margin") or Fraction(0),
                _fraction(audit.child_value(item, "right-margin"), "right-margin") or Fraction(0),
                _fraction(audit.child_value(item, "top-margin"), "top-margin"),
                _fraction(audit.child_value(item, "bottom-margin"), "bottom-margin"),
            )
        )
    return PageLayout(
        _fraction(audit.child_value(element, "page-height"), "page-height"),
        _fraction(audit.child_value(element, "page-width"), "page-width"),
        tuple(margins),
    )


def _system_layout(element: etree._Element | None, audit: LayoutAudit) -> SystemLayout | None:
    if element is None:
        return None
    audit.take(element)
    margins_element = audit.child(element, "system-margins")
    margins = None
    if margins_element is not None:
        margins = LayoutMargins(
            None,
            _fraction(audit.child_value(margins_element, "left-margin"), "left-margin")
            or Fraction(0),
            _fraction(audit.child_value(margins_element, "right-margin"), "right-margin")
            or Fraction(0),
        )
    return SystemLayout(
        margins,
        _fraction(audit.child_value(element, "system-distance"), "system-distance"),
        _fraction(audit.child_value(element, "top-system-distance"), "top-system-distance"),
    )


def _staff_layout(element: etree._Element, audit: LayoutAudit) -> StaffLayout:
    audit.take(element)
    return StaffLayout(
        audit.attr(element, "number"),
        _fraction(audit.child_value(element, "staff-distance"), "staff-distance"),
    )


def _defaults(element: etree._Element | None, audit: LayoutAudit) -> LayoutDefaults | None:
    if element is None:
        return None
    audit.take(element)
    scaling_element = audit.child(element, "scaling")
    scaling = None
    if scaling_element is not None:
        millimeters = _fraction(audit.child_value(scaling_element, "millimeters"), "millimeters")
        tenths = _fraction(audit.child_value(scaling_element, "tenths"), "tenths")
        if millimeters is None or tenths is None:
            raise ValueError("scaling requires millimeters and tenths")
        scaling = LayoutScaling(millimeters, tenths)
    appearance_element = audit.child(element, "appearance")
    appearance = []
    if appearance_element is not None:
        for child in appearance_element:
            if not isinstance(child.tag, str):
                continue
            audit.take(child)
            kind = etree.QName(child).localname
            text = audit.value(child)
            value_type = audit.attr(child, "type") or ""
            number = (
                _fraction(text, kind) if kind in {"line-width", "note-size", "distance"} else None
            )
            appearance.append(
                AppearanceValue(kind, value_type, number, text if number is None else None)
            )
    lyric_fonts = []
    for child in audit.children(element, "lyric-font"):
        style = map_presentation_style(child, audit)
        if style is not None:
            lyric_fonts.append(
                LyricFont(audit.attr(child, "number"), audit.attr(child, "name"), style)
            )
    lyric_languages = tuple(
        LyricLanguage(
            audit.attr(child, "number"),
            audit.attr(child, "name"),
            audit.attr(child, _XML_LANG) or "",
        )
        for child in audit.children(element, "lyric-language")
    )
    return LayoutDefaults(
        scaling,
        _page_layout(audit.child(element, "page-layout"), audit),
        _system_layout(audit.child(element, "system-layout"), audit),
        tuple(_staff_layout(item, audit) for item in audit.children(element, "staff-layout")),
        tuple(appearance),
        (
            map_presentation_style(music_font, audit)
            if (music_font := audit.child(element, "music-font")) is not None
            else None
        ),
        (
            map_presentation_style(word_font, audit)
            if (word_font := audit.child(element, "word-font")) is not None
            else None
        ),
        tuple(lyric_fonts),
        lyric_languages,
    )


def map_score_layout(root: etree._Element, audit: LayoutAudit) -> ScoreLayout | None:
    defaults = _defaults(audit.child(root, "defaults"), audit)
    credits = []
    for element in audit.children(root, "credit"):
        page = _integer(audit.attr(element, "page"), "credit page") or 1
        types = tuple(audit.value(item) or "" for item in audit.children(element, "credit-type"))
        items = []
        for child in element:
            if not isinstance(child.tag, str):
                continue
            kind = etree.QName(child).localname
            if kind in {"credit-words", "credit-symbol"}:
                audit.take(child)
                items.append(
                    CreditItem(
                        "words" if kind == "credit-words" else "symbol",
                        audit.value(child) or "",
                        map_presentation_style(child, audit),
                        source_id=audit.attr(child, "id"),
                    )
                )
            elif kind == "credit-image":
                audit.take(child)
                items.append(
                    CreditItem(
                        "image",
                        audit.attr(child, "source") or "",
                        map_presentation_style(child, audit),
                        audit.attr(child, "type"),
                        _fraction(audit.attr(child, "width"), "credit image width"),
                        _fraction(audit.attr(child, "height"), "credit image height"),
                        audit.attr(child, "id"),
                    )
                )
        credits.append(Credit(page, types, tuple(items), audit.attr(element, "id")))
    if defaults is None and not credits:
        return None
    return ScoreLayout(defaults, tuple(credits))


def map_measure_layout(
    header: etree._Element, measure: etree._Element, audit: LayoutAudit
) -> MeasurePrintLayout | None:
    width = _fraction(audit.attr(header, "width"), "measure width")
    print_element = audit.child(measure, "print")
    if print_element is None:
        return MeasurePrintLayout(width=width) if width is not None else None
    measure_layout = audit.child(print_element, "measure-layout")
    return MeasurePrintLayout(
        width,
        _yes_no(audit.attr(print_element, "new-page"), "new-page"),
        _yes_no(audit.attr(print_element, "new-system"), "new-system"),
        audit.attr(print_element, "page-number"),
        _integer(audit.attr(print_element, "blank-page"), "blank-page"),
        _page_layout(audit.child(print_element, "page-layout"), audit),
        _system_layout(audit.child(print_element, "system-layout"), audit),
        tuple(_staff_layout(item, audit) for item in audit.children(print_element, "staff-layout")),
        _fraction(
            audit.child_value(measure_layout, "measure-distance")
            if measure_layout is not None
            else None,
            "measure-distance",
        ),
        audit.child_value(print_element, "measure-numbering"),
        _fraction(audit.attr(print_element, "staff-spacing"), "staff-spacing"),
        map_name_display(audit.child(print_element, "part-name-display"), audit),
        map_name_display(audit.child(print_element, "part-abbreviation-display"), audit),
    )
