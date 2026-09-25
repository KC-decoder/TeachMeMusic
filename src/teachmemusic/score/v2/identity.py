"""Stable identities, typed references, and source-map contracts."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class EntityKind(StrEnum):
    """Addressable entity families in canonical schema version 2."""

    PACKAGE = "package"
    SOURCE_DOCUMENT = "source-document"
    SCORE = "score"
    OPUS = "opus"
    SOUNDS = "sounds"
    MEDIA = "media"
    PART = "part"
    STAFF = "staff"
    VOICE = "voice"
    MEASURE = "measure"
    EVENT = "event"
    CHORD = "chord"
    HARMONY = "harmony"


@dataclass(frozen=True, slots=True)
class CanonicalId:
    """A stable identifier qualified by its canonical entity family."""

    kind: EntityKind
    value: str


@dataclass(frozen=True, slots=True)
class EntityReference:
    """A reference that declares the target family as well as its ID."""

    target_kind: EntityKind
    target_id: str

    @classmethod
    def to(cls, target: CanonicalId) -> EntityReference:
        """Construct a typed reference to an existing canonical ID."""

        return cls(target_kind=target.kind, target_id=target.value)


@dataclass(frozen=True, slots=True)
class SourceLocation:
    """A deterministic location inside one source document."""

    source_document: EntityReference
    logical_path: str
    line: int | None = None
    column: int | None = None
    source_ordinal: int | None = None


@dataclass(frozen=True, slots=True)
class SourceMapEntry:
    """Locations that supplied one canonical entity."""

    entity: EntityReference
    locations: tuple[SourceLocation, ...]
