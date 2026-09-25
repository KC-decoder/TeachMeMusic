"""Map MusicXML simple links, bookmarks, and linked-part declarations."""

from __future__ import annotations

from typing import Protocol

from lxml import etree

from teachmemusic.score.v2.links import Bookmark, ExternalLink, PartLink

from .presentation_mapping import map_presentation_style

_XLINK = "{http://www.w3.org/1999/xlink}"


class LinkAudit(Protocol):
    def take(self, element: etree._Element | None) -> etree._Element | None: ...
    def attr(self, element: etree._Element, name: str) -> str | None: ...
    def value(self, element: etree._Element | None) -> str | None: ...
    def children(self, element: etree._Element, name: str) -> tuple[etree._Element, ...]: ...


def _integer(value: str | None, label: str) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except ValueError as error:
        raise ValueError(f"invalid {label}") from error


def map_link(element: etree._Element, audit: LinkAudit) -> ExternalLink:
    audit.take(element)
    return ExternalLink(
        href=audit.attr(element, f"{_XLINK}href") or "",
        link_type=audit.attr(element, f"{_XLINK}type"),
        role=audit.attr(element, f"{_XLINK}role"),
        title=audit.attr(element, f"{_XLINK}title"),
        show=audit.attr(element, f"{_XLINK}show"),
        actuate=audit.attr(element, f"{_XLINK}actuate"),
        name=audit.attr(element, "name"),
        element=audit.attr(element, "element"),
        position=_integer(audit.attr(element, "position"), "link position"),
        presentation=map_presentation_style(element, audit),
    )


def map_bookmark(element: etree._Element, audit: LinkAudit) -> Bookmark:
    audit.take(element)
    return Bookmark(
        id=audit.attr(element, "id") or "",
        name=audit.attr(element, "name"),
        element=audit.attr(element, "element"),
        position=_integer(audit.attr(element, "position"), "bookmark position"),
    )


def map_part_link(element: etree._Element, audit: LinkAudit) -> PartLink:
    audit.take(element)
    return PartLink(
        link=map_link(element, audit),
        instrument_ids=tuple(
            audit.attr(item, "id") or "" for item in audit.children(element, "instrument-link")
        ),
        group_links=tuple(
            audit.value(item) or "" for item in audit.children(element, "group-link")
        ),
    )
