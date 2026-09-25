"""Reusable typed presentation values for canonical schema v2."""

from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction


@dataclass(frozen=True, slots=True)
class PresentationNumber:
    """A numeric presentation value or one declared keyword, never both."""

    number: Fraction | None = None
    keyword: str | None = None


@dataclass(frozen=True, slots=True)
class PresentationStyle:
    """Shared position, font, alignment, and text-formatting values."""

    default_x: Fraction | None = None
    default_y: Fraction | None = None
    relative_x: Fraction | None = None
    relative_y: Fraction | None = None
    color: str | None = None
    font_family: str | None = None
    font_style: str | None = None
    font_size: PresentationNumber | None = None
    font_weight: str | None = None
    justify: str | None = None
    halign: str | None = None
    valign: str | None = None
    enclosure: str | None = None
    letter_spacing: PresentationNumber | None = None
    line_height: PresentationNumber | None = None
    underline: int | None = None
    overline: int | None = None
    line_through: int | None = None
    rotation: Fraction | None = None
    text_direction: str | None = None
    language: str | None = None
    space: str | None = None


@dataclass(frozen=True, slots=True)
class SourcePresentation:
    """Presentation attached to a mapped source node without a narrower owner."""

    source_path: str
    element_name: str
    style: PresentationStyle


@dataclass(frozen=True, slots=True)
class DisplayTextSegment:
    """One text or accidental token in a name-display override."""

    kind: str
    value: str
    style: PresentationStyle | None = None


@dataclass(frozen=True, slots=True)
class NameDisplay:
    """Ordered display override for a part or part-group name."""

    segments: tuple[DisplayTextSegment, ...]
