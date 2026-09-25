"""Deterministic one-way migration from canonical schema v1 to v2."""

from __future__ import annotations

import hashlib

from teachmemusic.score.models import ScoreRepresentation, SourceFormat
from teachmemusic.score.serializer import score_to_json
from teachmemusic.score.validation import ScoreValidationError, require_valid_score

from .documents import (
    CANONICAL_SCHEMA_VERSION,
    CanonicalMusicPackage,
    ScoreDocument,
    V1CompatibilityContent,
)
from .identity import CanonicalId, EntityKind, EntityReference
from .provenance import (
    PackageProvenance,
    SourceDocument,
    SourceDocumentFormat,
    Transformation,
    TransformationKind,
)
from .validation import require_valid_package
from .values import SpecifiedValue

V1_SCHEMA_IDENTIFIER = "teachmemusic.score-representation/1"

_SOURCE_FORMATS = {
    SourceFormat.MUSICXML: SourceDocumentFormat.MUSICXML,
    SourceFormat.COMPRESSED_MUSICXML: SourceDocumentFormat.COMPRESSED_MUSICXML,
    SourceFormat.PDF: SourceDocumentFormat.PDF,
}


class CanonicalMigrationError(ValueError):
    """Raised when a source score cannot be migrated without invention."""


def migrate_v1_score(score: ScoreRepresentation) -> CanonicalMusicPackage:
    """Validate and deterministically retain every v1 field in a v2 package.

    Task 7E deliberately uses a typed compatibility payload. It preserves the
    complete v1 value while richer v2 temporal contracts remain Task 7F work.
    Source facts absent from v1 are explicitly ``unknown``.
    """

    try:
        require_valid_score(score)
    except ScoreValidationError as error:
        raise CanonicalMigrationError(f"source schema-v1 score is invalid: {error}") from error

    source_json = score_to_json(score)
    source_digest = hashlib.sha256(source_json.encode("utf-8")).hexdigest()
    package_id = CanonicalId(EntityKind.PACKAGE, f"migrated-v1:{source_digest}")
    score_id = CanonicalId(EntityKind.SCORE, score.id)

    sources = tuple(
        _migrate_source(source, index) for index, source in enumerate(score.provenance, start=1)
    )
    source_references = tuple(EntityReference.to(source.id) for source in sources)
    document = ScoreDocument(
        id=score_id,
        source_documents=source_references,
        content=V1CompatibilityContent(score=score),
    )
    package = CanonicalMusicPackage(
        id=package_id,
        documents=(document,),
        root_documents=(EntityReference.to(score_id),),
        provenance=PackageProvenance(
            sources=sources,
            source_map=(),
            transformations=(
                Transformation(
                    kind=TransformationKind.MIGRATED_FROM_V1,
                    source_schema=V1_SCHEMA_IDENTIFIER,
                    target_schema=CANONICAL_SCHEMA_VERSION,
                    input_sha256=source_digest,
                ),
            ),
        ),
    )
    require_valid_package(package)
    return package


def _migrate_source(source: object, index: int) -> SourceDocument:
    from teachmemusic.score.models import SourceReference

    if not isinstance(source, SourceReference):
        raise CanonicalMigrationError("schema-v1 provenance contains an unsupported source type")
    source_id = CanonicalId(EntityKind.SOURCE_DOCUMENT, f"source:{index}")
    return SourceDocument(
        id=source_id,
        source_format=SpecifiedValue.explicit(_SOURCE_FORMATS[source.source_format]),
        logical_name=SpecifiedValue.explicit(source.logical_name),
        sha256=(
            SpecifiedValue.unknown()
            if source.sha256 is None
            else SpecifiedValue.explicit(source.sha256)
        ),
        byte_length=SpecifiedValue.unknown(),
        declared_musicxml_version=SpecifiedValue.unknown(),
        validated_musicxml_version=SpecifiedValue.unknown(),
        document_form=SpecifiedValue.unknown(),
    )
