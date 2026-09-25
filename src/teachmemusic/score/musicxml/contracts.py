"""Private contracts for secure MusicXML source validation."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from lxml import etree


class SourceMediaType(StrEnum):
    """Media type selected by inspecting source bytes."""

    PLAIN_XML = "application/vnd.recordare.musicxml+xml"
    COMPRESSED_MXL = "application/vnd.recordare.musicxml"


class DocumentKind(StrEnum):
    """Supported MusicXML top-level document kinds."""

    SCORE_PARTWISE = "score-partwise"
    SCORE_TIMEWISE = "score-timewise"
    OPUS = "opus"
    SOUNDS = "sounds"


@dataclass(frozen=True, slots=True)
class IngestionLimits:
    """Central limits applied before a source may reach musical mapping."""

    max_input_bytes: int = 16 * 1024 * 1024
    max_archive_entries: int = 256
    max_archive_entry_bytes: int = 16 * 1024 * 1024
    max_archive_total_bytes: int = 64 * 1024 * 1024
    max_compression_ratio: int = 100
    max_xml_depth: int = 256
    max_xml_attributes_per_element: int = 128
    max_xml_scalar_bytes: int = 1024 * 1024
    max_xml_nodes: int = 1_000_000
    max_validation_diagnostics: int = 20
    policy_id: str = "teachmemusic.musicxml.strict/1"

    def __post_init__(self) -> None:
        numeric_limits = (
            self.max_input_bytes,
            self.max_archive_entries,
            self.max_archive_entry_bytes,
            self.max_archive_total_bytes,
            self.max_compression_ratio,
            self.max_xml_depth,
            self.max_xml_attributes_per_element,
            self.max_xml_scalar_bytes,
            self.max_xml_nodes,
            self.max_validation_diagnostics,
        )
        if any(value <= 0 for value in numeric_limits):
            raise ValueError("all ingestion limits must be positive")
        if not self.policy_id:
            raise ValueError("ingestion policy_id must be non-empty")


@dataclass(frozen=True, slots=True)
class SourceArtifact:
    """Immutable identity of the submitted bytes."""

    media_type: SourceMediaType
    sha256: str
    byte_length: int
    policy_id: str
    logical_name: str | None = None


@dataclass(frozen=True, slots=True)
class PackageRootfile:
    """One rootfile declaration retained from an MXL container."""

    full_path: str
    media_type: str | None


@dataclass(frozen=True, slots=True)
class PackageResource:
    """One safely bounded regular-file entry retained from an MXL archive."""

    logical_path: str
    data: bytes
    declared_media_type: str | None
    is_rootfile: bool


@dataclass(frozen=True, slots=True)
class PackageContext:
    """Validated package facts needed by later private mapping work."""

    selected_rootfile: str
    selected_rootfile_sha256: str
    rootfiles: tuple[PackageRootfile, ...]
    entries: tuple[str, ...]
    container_standard_version: str
    resources: tuple[PackageResource, ...] = ()


@dataclass(frozen=True, slots=True)
class ValidationEvidence:
    """Pinned standard resource used to validate a source document."""

    standard_version: str
    validation_kind: str
    resource_path: str


@dataclass(frozen=True, slots=True)
class ValidatedMusicXmlDocument:
    """Private validated MusicXML source view; never a public score result."""

    tree: etree._ElementTree
    kind: DocumentKind
    standard_version: str
    declared_version: str | None
    artifact: SourceArtifact
    evidence: ValidationEvidence
    package: PackageContext | None = None

    @property
    def root(self) -> etree._Element:
        """Return the private XML root for future ingestion-only mapping."""

        return self.tree.getroot()
