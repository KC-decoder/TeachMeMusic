"""Canonical content contracts for MusicXML opus and sound-catalog documents."""

from __future__ import annotations

from dataclasses import dataclass

from .links import ExternalLink


@dataclass(frozen=True, slots=True)
class OpusItem:
    kind: str
    link: ExternalLink | None = None
    new_page: bool | None = None
    title: str | None = None
    children: tuple[OpusItem, ...] = ()


@dataclass(frozen=True, slots=True)
class OpusCatalog:
    version: str
    title: str | None
    items: tuple[OpusItem, ...]


@dataclass(frozen=True, slots=True)
class SoundCatalogMapping:
    kind: str
    value: str
    primary: bool | None
    ensemble_size: str | None = None


@dataclass(frozen=True, slots=True)
class SoundCatalogEntry:
    id: str
    primary: bool | None
    mappings: tuple[SoundCatalogMapping, ...]


@dataclass(frozen=True, slots=True)
class SoundCatalog:
    version: str
    entries: tuple[SoundCatalogEntry, ...]


type AuxiliaryDocument = OpusCatalog | SoundCatalog
