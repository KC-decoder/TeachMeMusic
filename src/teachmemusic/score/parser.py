"""Public score-ingestion edge; external XML objects remain private."""

from __future__ import annotations

from pathlib import PurePosixPath

from teachmemusic.score.musicxml.auxiliary_mapping import map_auxiliary_document
from teachmemusic.score.musicxml.boundary import validate_musicxml_source
from teachmemusic.score.musicxml.canonical_package import build_canonical_package
from teachmemusic.score.musicxml.contracts import IngestionLimits, SourceMediaType
from teachmemusic.score.musicxml.temporal import map_temporal_score
from teachmemusic.score.v2.auxiliary import AuxiliaryDocument
from teachmemusic.score.v2.auxiliary_validation import validate_auxiliary_document
from teachmemusic.score.v2.documents import (
    CanonicalMusicPackage,
    ScoreDocument,
    TemporalScoreContent,
)
from teachmemusic.score.v2.identity import (
    CanonicalId,
    EntityKind,
    EntityReference,
    SourceLocation,
    SourceMapEntry,
)
from teachmemusic.score.v2.provenance import PackageProvenance, SourceDocument, SourceDocumentFormat
from teachmemusic.score.v2.temporal import TemporalReadResult
from teachmemusic.score.v2.validation import require_valid_package
from teachmemusic.score.v2.values import SpecifiedValue


def parse_musicxml_timeline(
    source: bytes,
    *,
    logical_name: str | None = None,
    limits: IngestionLimits | None = None,
) -> TemporalReadResult:
    """Read exact score timing from validated XML/MXL.

    This explicitly partial projection audits source constructs not mapped
    yet. It is not a lossless canonical package or a finished teaching score.
    """

    validated = validate_musicxml_source(source, logical_name=logical_name, limits=limits)
    return map_temporal_score(validated)


def parse_musicxml_auxiliary(
    source: bytes,
    *,
    logical_name: str | None = None,
    limits: IngestionLimits | None = None,
) -> AuxiliaryDocument:
    """Read a validated MusicXML opus or standard sound catalog."""

    validated = validate_musicxml_source(source, logical_name=logical_name, limits=limits)
    result = map_auxiliary_document(validated)
    issues = validate_auxiliary_document(result)
    if issues:
        raise ValueError(f"invalid auxiliary mapping: {issues[0].code} at {issues[0].path}")
    return result


def parse_musicxml_timeline_package(
    source: bytes,
    *,
    logical_name: str | None = None,
    limits: IngestionLimits | None = None,
) -> CanonicalMusicPackage:
    """Return the validated, serializable v2 temporal-partial score package.

    The content kind remains explicitly partial until Tasks 7G–7I close the
    remaining notation, presentation, playback, and conformance gates.
    """

    _validate_logical_name(logical_name)
    validated = validate_musicxml_source(source, logical_name=logical_name, limits=limits)
    result = map_temporal_score(validated)
    digest = validated.artifact.sha256
    source_id = CanonicalId(EntityKind.SOURCE_DOCUMENT, f"source:{digest}")
    score_id = CanonicalId(EntityKind.SCORE, f"score:{digest}")
    source_ref = EntityReference.to(source_id)
    score_ref = EntityReference.to(score_id)
    document = ScoreDocument(
        id=score_id,
        source_documents=(source_ref,),
        content=TemporalScoreContent(result.score, result.deferred),
    )
    package = CanonicalMusicPackage(
        id=CanonicalId(EntityKind.PACKAGE, f"package:{digest}"),
        documents=(document,),
        root_documents=(score_ref,),
        provenance=PackageProvenance(
            sources=(
                SourceDocument(
                    id=source_id,
                    source_format=SpecifiedValue.explicit(
                        SourceDocumentFormat.COMPRESSED_MUSICXML
                        if validated.artifact.media_type is SourceMediaType.COMPRESSED_MXL
                        else SourceDocumentFormat.MUSICXML
                    ),
                    logical_name=(
                        SpecifiedValue.explicit(logical_name)
                        if logical_name is not None
                        else SpecifiedValue.unknown()
                    ),
                    sha256=SpecifiedValue.explicit(digest),
                    byte_length=SpecifiedValue.explicit(validated.artifact.byte_length),
                    declared_musicxml_version=(
                        SpecifiedValue.explicit(validated.declared_version)
                        if validated.declared_version is not None
                        else SpecifiedValue.unknown()
                    ),
                    validated_musicxml_version=SpecifiedValue.explicit(validated.standard_version),
                    document_form=SpecifiedValue.explicit(validated.kind.value),
                ),
            ),
            source_map=(
                SourceMapEntry(
                    entity=score_ref,
                    locations=(
                        SourceLocation(
                            source_document=source_ref,
                            logical_path=f"/{validated.kind.value}",
                        ),
                    ),
                ),
            ),
        ),
    )
    require_valid_package(package)
    return package


def parse_musicxml_package(
    source: bytes,
    *,
    logical_name: str | None = None,
    limits: IngestionLimits | None = None,
) -> CanonicalMusicPackage:
    """Return one complete validated canonical package for MusicXML or MXL bytes.

    Unlike the retained timeline-package compatibility function, this public
    boundary rejects deferred score constructs and integrates package-local
    score, opus, sounds, alternate-rootfile, linked-part, and media resources.
    """

    _validate_logical_name(logical_name)
    selected_limits = limits or IngestionLimits()
    validated = validate_musicxml_source(
        source,
        logical_name=logical_name,
        limits=selected_limits,
    )
    return build_canonical_package(validated, limits=selected_limits)


def _validate_logical_name(logical_name: str | None) -> None:
    if logical_name is not None and (not logical_name or PurePosixPath(logical_name).is_absolute()):
        raise ValueError("logical_name must be non-empty and relative")
