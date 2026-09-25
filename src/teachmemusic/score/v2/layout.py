"""Canonical page, system, staff, credit, and measure-layout values."""

from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction

from .presentation import NameDisplay, PresentationStyle


@dataclass(frozen=True, slots=True)
class LayoutScaling:
    millimeters: Fraction
    tenths: Fraction


@dataclass(frozen=True, slots=True)
class LayoutMargins:
    kind: str | None
    left: Fraction
    right: Fraction
    top: Fraction | None = None
    bottom: Fraction | None = None


@dataclass(frozen=True, slots=True)
class PageLayout:
    height: Fraction | None = None
    width: Fraction | None = None
    margins: tuple[LayoutMargins, ...] = ()


@dataclass(frozen=True, slots=True)
class SystemLayout:
    margins: LayoutMargins | None = None
    system_distance: Fraction | None = None
    top_system_distance: Fraction | None = None


@dataclass(frozen=True, slots=True)
class StaffLayout:
    number: str | None
    distance: Fraction | None


@dataclass(frozen=True, slots=True)
class AppearanceValue:
    kind: str
    value_type: str
    number: Fraction | None = None
    text: str | None = None


@dataclass(frozen=True, slots=True)
class LyricFont:
    number: str | None
    name: str | None
    style: PresentationStyle


@dataclass(frozen=True, slots=True)
class LyricLanguage:
    number: str | None
    name: str | None
    language: str


@dataclass(frozen=True, slots=True)
class LayoutDefaults:
    scaling: LayoutScaling | None = None
    page: PageLayout | None = None
    system: SystemLayout | None = None
    staves: tuple[StaffLayout, ...] = ()
    appearance: tuple[AppearanceValue, ...] = ()
    music_font: PresentationStyle | None = None
    word_font: PresentationStyle | None = None
    lyric_fonts: tuple[LyricFont, ...] = ()
    lyric_languages: tuple[LyricLanguage, ...] = ()


@dataclass(frozen=True, slots=True)
class CreditItem:
    kind: str
    value: str
    style: PresentationStyle | None = None
    mime_type: str | None = None
    width: Fraction | None = None
    height: Fraction | None = None
    source_id: str | None = None


@dataclass(frozen=True, slots=True)
class Credit:
    page: int
    types: tuple[str, ...]
    items: tuple[CreditItem, ...]
    source_id: str | None = None


@dataclass(frozen=True, slots=True)
class ScoreLayout:
    defaults: LayoutDefaults | None = None
    credits: tuple[Credit, ...] = ()


@dataclass(frozen=True, slots=True)
class MeasurePrintLayout:
    width: Fraction | None = None
    new_page: bool | None = None
    new_system: bool | None = None
    page_number: str | None = None
    blank_page: int | None = None
    page: PageLayout | None = None
    system: SystemLayout | None = None
    staves: tuple[StaffLayout, ...] = ()
    measure_distance: Fraction | None = None
    measure_numbering: str | None = None
    staff_spacing: Fraction | None = None
    part_name_display: NameDisplay | None = None
    part_abbreviation_display: NameDisplay | None = None
