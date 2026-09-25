"""Package and transformation provenance for canonical schema version 2."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from .identity import CanonicalId, SourceMapEntry
from .values import SpecifiedValue


class SourceDocumentFormat(StrEnum):
    """Formats that can contribute evidence to a canonical package."""

    MUSICXML = "musicxml"
    COMPRESSED_MUSICXML = "mxl"
    PDF = "pdf"
    PACKAGE_RESOURCE = "package-resource"


@dataclass(frozen=True, slots=True)
class SourceDocument:
    """Typed identity and known facts for one source artifact."""

    id: CanonicalId
    source_format: SpecifiedValue[SourceDocumentFormat]
    logical_name: SpecifiedValue[str]
    sha256: SpecifiedValue[str]
    byte_length: SpecifiedValue[int]
    declared_musicxml_version: SpecifiedValue[str]
    validated_musicxml_version: SpecifiedValue[str]
    document_form: SpecifiedValue[str]


class TransformationKind(StrEnum):
    """Recorded canonical transformations."""

    MIGRATED_FROM_V1 = "migrated-from-v1"


@dataclass(frozen=True, slots=True)
class Transformation:
    """One deterministic transformation in the package's history."""

    kind: TransformationKind
    source_schema: str
    target_schema: str
    input_sha256: str


@dataclass(frozen=True, slots=True)
class PackageProvenance:
    """Source documents, source maps, and transformations for a package."""

    sources: tuple[SourceDocument, ...] = ()
    source_map: tuple[SourceMapEntry, ...] = ()
    transformations: tuple[Transformation, ...] = ()
    diagnostic_codes: tuple[str, ...] = ()
