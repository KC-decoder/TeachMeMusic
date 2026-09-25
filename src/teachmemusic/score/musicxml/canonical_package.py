"""Complete canonical package assembly after private MusicXML validation."""

from __future__ import annotations

import hashlib
import posixpath
from dataclasses import dataclass, replace
from pathlib import PurePosixPath
from urllib.parse import unquote, urlsplit

from teachmemusic.score.v2.auxiliary import OpusCatalog, OpusItem, SoundCatalog
from teachmemusic.score.v2.documents import (
    CanonicalDocument,
    CanonicalMusicPackage,
    CanonicalScoreContent,
    MediaDocument,
    OpusDocument,
    PackageRelationship,
    PackageRelationshipKind,
    ScoreDocument,
    SoundsDocument,
)
from teachmemusic.score.v2.identity import (
    CanonicalId,
    EntityKind,
    EntityReference,
    SourceLocation,
    SourceMapEntry,
)
from teachmemusic.score.v2.links import ExternalLink
from teachmemusic.score.v2.provenance import (
    PackageProvenance,
    SourceDocument,
    SourceDocumentFormat,
)
from teachmemusic.score.v2.validation import require_valid_package
from teachmemusic.score.v2.values import SpecifiedValue

from .auxiliary_mapping import map_auxiliary_document
from .boundary import validate_musicxml_source
from .contracts import (
    DocumentKind,
    IngestionLimits,
    PackageResource,
    PackageRootfile,
    SourceMediaType,
    ValidatedMusicXmlDocument,
)
from .diagnostics import MusicXmlBoundaryError
from .temporal import map_temporal_score

_ADMINISTRATIVE_PATHS = frozenset({"mimetype", "META-INF/container.xml"})
_MUSICXML_MEDIA_TYPES = frozenset(
    {"application/vnd.recordare.musicxml+xml", "application/xml", "text/xml"}
)
_MEDIA_TYPES = {
    ".css": "text/css",
    ".gif": "image/gif",
    ".jpeg": "image/jpeg",
    ".jpg": "image/jpeg",
    ".json": "application/json",
    ".mid": "audio/midi",
    ".midi": "audio/midi",
    ".mp3": "audio/mpeg",
    ".ogg": "audio/ogg",
    ".pdf": "application/pdf",
    ".png": "image/png",
    ".svg": "image/svg+xml",
    ".txt": "text/plain",
    ".wav": "audio/wav",
    ".xml": "application/xml",
}


class CanonicalPackageError(ValueError):
    """Raised when validated sources cannot form one complete package."""

    def __init__(self, code: str, message: str, *, logical_path: str | None = None) -> None:
        self.code = code
        self.logical_path = logical_path
        super().__init__(f"{code}: {message}")


@dataclass(frozen=True, slots=True)
class _MappedDocument:
    path: str
    document: CanonicalDocument
    source: SourceDocument
    source_map: SourceMapEntry


def build_canonical_package(
    validated: ValidatedMusicXmlDocument,
    *,
    limits: IngestionLimits,
) -> CanonicalMusicPackage:
    """Build the complete public package from one private validated source."""

    outer_digest = validated.artifact.sha256
    package_id = CanonicalId(EntityKind.PACKAGE, f"package:{outer_digest}")
    outer_source = _outer_source(validated)
    outer_ref = EntityReference.to(outer_source.id)

    if validated.package is None:
        path = validated.artifact.logical_name or _default_name(validated.kind)
        mapped = _map_validated_document(
            validated,
            path=path,
            source_references=(outer_ref,),
            source=outer_source,
        )
        package = CanonicalMusicPackage(
            id=package_id,
            documents=(mapped.document,),
            root_documents=(EntityReference.to(mapped.document.id),),
            provenance=PackageProvenance(
                sources=(outer_source,),
                source_map=(mapped.source_map,),
            ),
        )
        require_valid_package(package)
        return package

    context = validated.package
    resources = {
        item.logical_path: item
        for item in context.resources
        if item.logical_path not in _ADMINISTRATIVE_PATHS
    }
    ordered_paths = tuple(
        dict.fromkeys(
            (
                *(item.full_path for item in context.rootfiles),
                *sorted(resources),
            )
        )
    )
    mapped_documents: list[_MappedDocument] = []
    for path in ordered_paths:
        resource = resources.get(path)
        if resource is None:
            raise CanonicalPackageError(
                "MXML_PACKAGE_RESOURCE_MISSING",
                "a declared package resource is missing",
                logical_path=path,
            )
        entry_source = _entry_source(
            resource,
            validated=(validated if path == context.selected_rootfile else None),
            limits=limits,
        )
        entry_ref = EntityReference.to(entry_source.id)
        if path == context.selected_rootfile:
            mapped = _map_validated_document(
                validated,
                path=path,
                source_references=(outer_ref, entry_ref),
                source=entry_source,
            )
        else:
            mapped = _map_resource(
                resource,
                source_references=(outer_ref, entry_ref),
                source=entry_source,
                limits=limits,
            )
        mapped_documents.append(mapped)

    by_path = {item.path: item.document for item in mapped_documents}
    root_documents = tuple(
        EntityReference.to(by_path[item.full_path].id) for item in context.rootfiles
    )
    relationships = list(
        _alternate_root_relationships(context.rootfiles, by_path, root_documents[0])
    )
    relationship_updates = _resolve_document_relationships(mapped_documents, by_path)
    relationships.extend(relationship_updates.relationships)
    if relationship_updates.opus_members:
        mapped_documents = [
            replace(
                item,
                document=replace(
                    item.document,
                    members=relationship_updates.opus_members.get(item.path, ()),
                ),
            )
            if isinstance(item.document, OpusDocument)
            else item
            for item in mapped_documents
        ]

    package = CanonicalMusicPackage(
        id=package_id,
        documents=tuple(item.document for item in mapped_documents),
        root_documents=root_documents,
        provenance=PackageProvenance(
            sources=(outer_source, *(item.source for item in mapped_documents)),
            source_map=tuple(item.source_map for item in mapped_documents),
        ),
        relationships=tuple(relationships),
    )
    require_valid_package(package)
    return package


def _outer_source(validated: ValidatedMusicXmlDocument) -> SourceDocument:
    artifact = validated.artifact
    source_id = CanonicalId(EntityKind.SOURCE_DOCUMENT, f"source:{artifact.sha256}")
    return SourceDocument(
        id=source_id,
        source_format=SpecifiedValue.explicit(
            SourceDocumentFormat.COMPRESSED_MUSICXML
            if artifact.media_type is SourceMediaType.COMPRESSED_MXL
            else SourceDocumentFormat.MUSICXML
        ),
        logical_name=(
            SpecifiedValue.explicit(artifact.logical_name)
            if artifact.logical_name is not None
            else SpecifiedValue.unknown()
        ),
        sha256=SpecifiedValue.explicit(artifact.sha256),
        byte_length=SpecifiedValue.explicit(artifact.byte_length),
        declared_musicxml_version=(
            SpecifiedValue.explicit(validated.declared_version)
            if validated.declared_version is not None
            else SpecifiedValue.unknown()
        ),
        validated_musicxml_version=SpecifiedValue.explicit(validated.standard_version),
        document_form=SpecifiedValue.explicit(
            "mxl-package" if validated.package is not None else validated.kind.value
        ),
    )


def _entry_source(
    resource: PackageResource,
    *,
    validated: ValidatedMusicXmlDocument | None,
    limits: IngestionLimits,
) -> SourceDocument:
    entry_validated = validated
    if entry_validated is None and _may_be_musicxml(resource):
        try:
            entry_validated = validate_musicxml_source(
                resource.data,
                logical_name=resource.logical_path,
                limits=limits,
            )
        except MusicXmlBoundaryError:
            entry_validated = None
    content_digest = hashlib.sha256(resource.data).hexdigest()
    identity_digest = _path_digest(resource.logical_path, resource.data)
    media_type = _media_type(resource)
    source_format = (
        SourceDocumentFormat.MUSICXML
        if entry_validated is not None
        else (
            SourceDocumentFormat.PDF
            if media_type == "application/pdf"
            else SourceDocumentFormat.PACKAGE_RESOURCE
        )
    )
    return SourceDocument(
        id=CanonicalId(EntityKind.SOURCE_DOCUMENT, f"source-entry:{identity_digest}"),
        source_format=SpecifiedValue.explicit(source_format),
        logical_name=SpecifiedValue.explicit(resource.logical_path),
        sha256=SpecifiedValue.explicit(content_digest),
        byte_length=SpecifiedValue.explicit(len(resource.data)),
        declared_musicxml_version=(
            SpecifiedValue.explicit(entry_validated.declared_version)
            if entry_validated is not None and entry_validated.declared_version is not None
            else SpecifiedValue.unknown()
        ),
        validated_musicxml_version=(
            SpecifiedValue.explicit(entry_validated.standard_version)
            if entry_validated is not None
            else SpecifiedValue.unknown()
        ),
        document_form=(
            SpecifiedValue.explicit(entry_validated.kind.value)
            if entry_validated is not None
            else SpecifiedValue.explicit("media")
        ),
    )


def _map_resource(
    resource: PackageResource,
    *,
    source_references: tuple[EntityReference, ...],
    source: SourceDocument,
    limits: IngestionLimits,
) -> _MappedDocument:
    if _may_be_musicxml(resource):
        try:
            validated = validate_musicxml_source(
                resource.data,
                logical_name=resource.logical_path,
                limits=limits,
            )
        except MusicXmlBoundaryError:
            if resource.is_rootfile and resource.declared_media_type in _MUSICXML_MEDIA_TYPES:
                raise
        else:
            return _map_validated_document(
                validated,
                path=resource.logical_path,
                source_references=source_references,
                source=source,
            )
    document_id = CanonicalId(
        EntityKind.MEDIA,
        f"media:{_path_digest(resource.logical_path, resource.data)}",
    )
    document = MediaDocument(
        id=document_id,
        source_documents=source_references,
        logical_path=resource.logical_path,
        media_type=SpecifiedValue.explicit(_media_type(resource)),
        sha256=SpecifiedValue.explicit(hashlib.sha256(resource.data).hexdigest()),
    )
    return _MappedDocument(
        resource.logical_path,
        document,
        source,
        _source_map(document_id, source.id, "/media"),
    )


def _map_validated_document(
    validated: ValidatedMusicXmlDocument,
    *,
    path: str,
    source_references: tuple[EntityReference, ...],
    source: SourceDocument,
) -> _MappedDocument:
    # Content identity is combined with the validated artifact digest so paths
    # remain distinct even when an archive contains byte-identical documents.
    source_digest = source.sha256.value or validated.artifact.sha256
    digest = hashlib.sha256(f"{path}\0{source_digest}".encode()).hexdigest()
    if validated.kind in {DocumentKind.SCORE_PARTWISE, DocumentKind.SCORE_TIMEWISE}:
        result = map_temporal_score(validated, id_namespace=f"document:{digest}")
        if result.deferred:
            raise CanonicalPackageError(
                "MXML_PACKAGE_INCOMPLETE",
                "complete package ingestion cannot retain deferred source constructs",
                logical_path=path,
            )
        document_id = CanonicalId(EntityKind.SCORE, f"score:{digest}")
        document: CanonicalDocument = ScoreDocument(
            id=document_id,
            source_documents=source_references,
            content=CanonicalScoreContent(result.score),
        )
    elif validated.kind is DocumentKind.OPUS:
        content = map_auxiliary_document(validated)
        if not isinstance(content, OpusCatalog):
            raise AssertionError("validated opus mapped to the wrong auxiliary type")
        document_id = CanonicalId(EntityKind.OPUS, f"opus:{digest}")
        document = OpusDocument(
            id=document_id,
            source_documents=source_references,
            title=_optional_text(content.title),
            members=(),
            content=content,
        )
    elif validated.kind is DocumentKind.SOUNDS:
        content = map_auxiliary_document(validated)
        if not isinstance(content, SoundCatalog):
            raise AssertionError("validated sounds mapped to the wrong auxiliary type")
        document_id = CanonicalId(EntityKind.SOUNDS, f"sounds:{digest}")
        document = SoundsDocument(
            id=document_id,
            source_documents=source_references,
            name=SpecifiedValue.explicit(PurePosixPath(path).name),
            content=content,
        )
    else:
        raise CanonicalPackageError(
            "MXML_PACKAGE_DOCUMENT_UNSUPPORTED",
            f"unsupported document kind {validated.kind.value}",
            logical_path=path,
        )
    return _MappedDocument(
        path,
        document,
        source,
        _source_map(document_id, source.id, f"/{validated.kind.value}"),
    )


def _source_map(
    document_id: CanonicalId,
    source_id: CanonicalId,
    logical_path: str,
) -> SourceMapEntry:
    return SourceMapEntry(
        entity=EntityReference.to(document_id),
        locations=(
            SourceLocation(
                source_document=EntityReference.to(source_id),
                logical_path=logical_path,
            ),
        ),
    )


def _optional_text(value: str | None) -> SpecifiedValue[str]:
    if value is None:
        return SpecifiedValue.unknown()
    if value == "":
        return SpecifiedValue.explicit_empty()
    return SpecifiedValue.explicit(value)


def _default_name(kind: DocumentKind) -> str:
    return {
        DocumentKind.SCORE_PARTWISE: "score.musicxml",
        DocumentKind.SCORE_TIMEWISE: "score.musicxml",
        DocumentKind.OPUS: "opus.xml",
        DocumentKind.SOUNDS: "sounds.xml",
    }[kind]


def _path_digest(path: str, data: bytes) -> str:
    return hashlib.sha256(path.encode("utf-8") + b"\0" + data).hexdigest()


def _may_be_musicxml(resource: PackageResource) -> bool:
    if resource.declared_media_type in _MUSICXML_MEDIA_TYPES:
        return True
    suffix = PurePosixPath(resource.logical_path).suffix.casefold()
    return suffix in {".musicxml", ".xml"} or resource.data.lstrip().startswith(b"<")


def _media_type(resource: PackageResource) -> str:
    if resource.declared_media_type:
        return resource.declared_media_type
    return _MEDIA_TYPES.get(
        PurePosixPath(resource.logical_path).suffix.casefold(),
        "application/octet-stream",
    )


def _alternate_root_relationships(
    rootfiles: tuple[PackageRootfile, ...],
    by_path: dict[str, CanonicalDocument],
    primary: EntityReference,
) -> tuple[PackageRelationship, ...]:
    return tuple(
        PackageRelationship(
            kind=PackageRelationshipKind.ALTERNATE_ROOTFILE,
            source=primary,
            target=EntityReference.to(by_path[rootfile.full_path].id),
            href=rootfile.full_path,
            source_order=index,
        )
        for index, rootfile in enumerate(rootfiles[1:], start=1)
    )


@dataclass(frozen=True, slots=True)
class _RelationshipUpdates:
    relationships: tuple[PackageRelationship, ...]
    opus_members: dict[str, tuple[EntityReference, ...]]


def _resolve_document_relationships(
    mapped: list[_MappedDocument],
    by_path: dict[str, CanonicalDocument],
) -> _RelationshipUpdates:
    relationships: list[PackageRelationship] = []
    opus_members: dict[str, tuple[EntityReference, ...]] = {}
    for item in mapped:
        document = item.document
        if isinstance(document, ScoreDocument) and isinstance(
            document.content, CanonicalScoreContent
        ):
            relationships.extend(_score_relationships(item.path, document, by_path))
        elif isinstance(document, OpusDocument) and document.content is not None:
            resolved, members = _opus_relationships(
                item.path,
                EntityReference.to(document.id),
                document.content.items,
                by_path,
            )
            relationships.extend(resolved)
            opus_members[item.path] = members
    return _RelationshipUpdates(tuple(relationships), opus_members)


def _score_relationships(
    source_path: str,
    document: ScoreDocument,
    by_path: dict[str, CanonicalDocument],
) -> tuple[PackageRelationship, ...]:
    content = document.content
    if not isinstance(content, CanonicalScoreContent):
        return ()
    score = content.score
    source_ref = EntityReference.to(document.id)
    candidates: list[tuple[PackageRelationshipKind, ExternalLink | str, EntityKind | None]] = []
    if score.work_opus is not None:
        candidates.append((PackageRelationshipKind.WORK_OPUS, score.work_opus, EntityKind.OPUS))
    for part in score.parts:
        candidates.extend(
            (PackageRelationshipKind.LINKED_PART, link.link, EntityKind.SCORE)
            for link in part.part_links
        )
    candidates.extend(
        (PackageRelationshipKind.RESOURCE_LINK, item.link, None) for item in score.links
    )
    for part in score.parts:
        for measure in part.measures:
            candidates.extend(
                (PackageRelationshipKind.RESOURCE_LINK, link, None) for link in measure.links
            )
            for direction in measure.directions:
                if direction.data is not None and direction.data.image is not None:
                    candidates.append(
                        (
                            PackageRelationshipKind.MEDIA_RESOURCE,
                            direction.data.image.source,
                            EntityKind.MEDIA,
                        )
                    )
    relationships: list[PackageRelationship] = []
    for order, (kind, value, expected_kind) in enumerate(candidates, start=1):
        href = value.href if isinstance(value, ExternalLink) else value
        target_path = _package_target(source_path, href)
        if target_path is None or target_path not in by_path:
            continue
        target = by_path[target_path]
        if expected_kind is not None and target.id.kind is not expected_kind:
            raise CanonicalPackageError(
                "MXML_PACKAGE_RELATIONSHIP_KIND",
                f"{kind.value} target has kind {target.id.kind.value}, "
                f"expected {expected_kind.value}",
                logical_path=target_path,
            )
        relationships.append(
            PackageRelationship(
                kind=kind,
                source=source_ref,
                target=EntityReference.to(target.id),
                href=href,
                source_order=order,
            )
        )
    return tuple(relationships)


def _opus_relationships(
    source_path: str,
    source_ref: EntityReference,
    items: tuple[OpusItem, ...],
    by_path: dict[str, CanonicalDocument],
) -> tuple[tuple[PackageRelationship, ...], tuple[EntityReference, ...]]:
    relationships: list[PackageRelationship] = []
    members: list[EntityReference] = []
    order = 0

    def visit(values: tuple[OpusItem, ...]) -> None:
        nonlocal order
        for value in values:
            if value.kind == "opus":
                visit(value.children)
                continue
            if value.link is None:
                continue
            order += 1
            target_path = _package_target(source_path, value.link.href)
            if target_path is None or target_path not in by_path:
                continue
            target = by_path[target_path]
            expected = EntityKind.SCORE if value.kind == "score" else EntityKind.OPUS
            if target.id.kind is not expected:
                raise CanonicalPackageError(
                    "MXML_PACKAGE_RELATIONSHIP_KIND",
                    f"opus member has kind {target.id.kind.value}, expected {expected.value}",
                    logical_path=target_path,
                )
            target_ref = EntityReference.to(target.id)
            members.append(target_ref)
            relationships.append(
                PackageRelationship(
                    kind=PackageRelationshipKind.OPUS_MEMBER,
                    source=source_ref,
                    target=target_ref,
                    href=value.link.href,
                    source_order=order,
                )
            )

    visit(items)
    return tuple(relationships), tuple(members)


def _package_target(source_path: str, href: str) -> str | None:
    parsed = urlsplit(href)
    if parsed.scheme or parsed.netloc or not parsed.path:
        return None
    decoded = unquote(parsed.path)
    if "\x00" in decoded or "\\" in decoded or decoded.startswith("/"):
        return None
    combined = posixpath.normpath(str(PurePosixPath(source_path).parent / decoded))
    if combined in {"", ".", ".."} or combined.startswith("../"):
        return None
    return combined
