"""Document and package contracts for canonical schema version 2."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from teachmemusic.score.models import ScoreRepresentation

from .auxiliary import OpusCatalog, SoundCatalog
from .identity import CanonicalId, EntityReference
from .provenance import PackageProvenance
from .temporal import DeferredConstruct, TemporalScore
from .values import SpecifiedValue

CANONICAL_SCHEMA_ID = "org.teachmemusic.canonical-music-package"
CANONICAL_SCHEMA_VERSION = "2.0.0"


@dataclass(frozen=True, slots=True)
class V1CompatibilityContent:
    """Validated v1 score evidence retained beside partial v2 temporal content.

    This is an explicit compatibility payload, not a claim that the v1 model
    covers MusicXML. It keeps every validated v1 field available during the
    one-way migration without inventing source facts or claiming comprehensive
    MusicXML coverage.
    """

    score: ScoreRepresentation


@dataclass(frozen=True, slots=True)
class TemporalScoreContent:
    """Validated temporal subset; deferred constructs prohibit readiness claims."""

    score: TemporalScore
    deferred: tuple[DeferredConstruct, ...]
    completeness: str = "temporal-only"


@dataclass(frozen=True, slots=True)
class CanonicalScoreContent:
    """Fully mapped and validated MusicXML score content."""

    score: TemporalScore
    completeness: str = "complete"


@dataclass(frozen=True, slots=True)
class ScoreDocument:
    """One canonical score document in a v2 package."""

    id: CanonicalId
    source_documents: tuple[EntityReference, ...]
    content: V1CompatibilityContent | TemporalScoreContent | CanonicalScoreContent


@dataclass(frozen=True, slots=True)
class OpusDocument:
    """Foundational typed opus relationship document."""

    id: CanonicalId
    source_documents: tuple[EntityReference, ...]
    title: SpecifiedValue[str]
    members: tuple[EntityReference, ...]
    content: OpusCatalog | None = None


@dataclass(frozen=True, slots=True)
class SoundsDocument:
    """Foundational typed sound-catalog document."""

    id: CanonicalId
    source_documents: tuple[EntityReference, ...]
    name: SpecifiedValue[str]
    content: SoundCatalog | None = None


@dataclass(frozen=True, slots=True)
class MediaDocument:
    """A typed referenced package resource."""

    id: CanonicalId
    source_documents: tuple[EntityReference, ...]
    logical_path: str
    media_type: SpecifiedValue[str]
    sha256: SpecifiedValue[str]


type CanonicalDocument = ScoreDocument | OpusDocument | SoundsDocument | MediaDocument


class PackageRelationshipKind(StrEnum):
    """Resolved relationships between documents contained in one package."""

    ALTERNATE_ROOTFILE = "alternate-rootfile"
    LINKED_PART = "linked-part"
    OPUS_MEMBER = "opus-member"
    WORK_OPUS = "work-opus"
    MEDIA_RESOURCE = "media-resource"
    RESOURCE_LINK = "resource-link"


@dataclass(frozen=True, slots=True)
class PackageRelationship:
    """One package-local relationship resolved from a source reference."""

    kind: PackageRelationshipKind
    source: EntityReference
    target: EntityReference
    href: str
    source_order: int


@dataclass(frozen=True, slots=True)
class CanonicalMusicPackage:
    """The version-2 public package boundary for canonical music documents."""

    id: CanonicalId
    documents: tuple[CanonicalDocument, ...]
    root_documents: tuple[EntityReference, ...]
    provenance: PackageProvenance = PackageProvenance()
    relationships: tuple[PackageRelationship, ...] = ()
    schema_id: str = CANONICAL_SCHEMA_ID
    schema_version: str = CANONICAL_SCHEMA_VERSION
