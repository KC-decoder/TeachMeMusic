"""Map validated MusicXML opus and sound-catalog documents."""

from __future__ import annotations

from lxml import etree

from teachmemusic.score.v2.auxiliary import (
    AuxiliaryDocument,
    OpusCatalog,
    OpusItem,
    SoundCatalog,
    SoundCatalogEntry,
    SoundCatalogMapping,
)
from teachmemusic.score.v2.links import ExternalLink

from .contracts import DocumentKind, ValidatedMusicXmlDocument

_XLINK = "{http://www.w3.org/1999/xlink}"


def _yes_no(value: str | None, label: str) -> bool | None:
    if value is None:
        return None
    if value not in {"yes", "no"}:
        raise ValueError(f"invalid {label}")
    return value == "yes"


def _link(element: etree._Element) -> ExternalLink:
    return ExternalLink(
        href=element.get(f"{_XLINK}href", ""),
        link_type=element.get(f"{_XLINK}type"),
        role=element.get(f"{_XLINK}role"),
        title=element.get(f"{_XLINK}title"),
        show=element.get(f"{_XLINK}show"),
        actuate=element.get(f"{_XLINK}actuate"),
    )


def _opus_item(element: etree._Element) -> OpusItem:
    kind = etree.QName(element).localname
    if kind == "opus":
        return OpusItem(
            kind=kind,
            title=element.findtext("title"),
            children=tuple(
                _opus_item(child)
                for child in element
                if isinstance(child.tag, str) and etree.QName(child).localname != "title"
            ),
        )
    return OpusItem(
        kind=kind,
        link=_link(element),
        new_page=_yes_no(element.get("new-page"), "opus score new-page")
        if kind == "score"
        else None,
    )


def _opus(document: ValidatedMusicXmlDocument) -> OpusCatalog:
    root = document.root
    return OpusCatalog(
        version=document.standard_version,
        title=root.findtext("title"),
        items=tuple(
            _opus_item(child)
            for child in root
            if isinstance(child.tag, str) and etree.QName(child).localname != "title"
        ),
    )


def _sounds(document: ValidatedMusicXmlDocument) -> SoundCatalog:
    entries: list[SoundCatalogEntry] = []
    for sound in document.root.findall("sound"):
        mappings = tuple(
            SoundCatalogMapping(
                kind=etree.QName(mapping).localname,
                value=mapping.text or "",
                primary=_yes_no(mapping.get("primary"), "sound mapping primary"),
                ensemble_size=mapping.get("number"),
            )
            for mapping in sound
            if isinstance(mapping.tag, str)
        )
        entries.append(
            SoundCatalogEntry(
                id=sound.get("id", ""),
                primary=_yes_no(sound.get("primary"), "sound primary"),
                mappings=mappings,
            )
        )
    return SoundCatalog(version=document.standard_version, entries=tuple(entries))


def map_auxiliary_document(document: ValidatedMusicXmlDocument) -> AuxiliaryDocument:
    """Return a library-independent canonical view of a validated auxiliary root."""

    if document.kind is DocumentKind.OPUS:
        return _opus(document)
    if document.kind is DocumentKind.SOUNDS:
        return _sounds(document)
    raise ValueError(f"not an auxiliary MusicXML document: {document.kind.value}")
