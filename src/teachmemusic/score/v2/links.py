"""Typed links and bookmarks shared by scores, opuses, and packages."""

from __future__ import annotations

from dataclasses import dataclass

from .presentation import PresentationStyle


@dataclass(frozen=True, slots=True)
class ExternalLink:
    href: str
    link_type: str | None = None
    role: str | None = None
    title: str | None = None
    show: str | None = None
    actuate: str | None = None
    name: str | None = None
    element: str | None = None
    position: int | None = None
    presentation: PresentationStyle | None = None


@dataclass(frozen=True, slots=True)
class Bookmark:
    id: str
    name: str | None = None
    element: str | None = None
    position: int | None = None


@dataclass(frozen=True, slots=True)
class ScopedLink:
    context: str
    source_order: int
    link: ExternalLink


@dataclass(frozen=True, slots=True)
class ScopedBookmark:
    context: str
    source_order: int
    bookmark: Bookmark


@dataclass(frozen=True, slots=True)
class PartLink:
    link: ExternalLink
    instrument_ids: tuple[str, ...] = ()
    group_links: tuple[str, ...] = ()
