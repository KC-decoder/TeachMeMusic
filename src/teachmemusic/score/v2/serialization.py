"""Deterministic JSON encoding for canonical schema version 2."""

from __future__ import annotations

import json
from collections.abc import Callable
from decimal import Decimal, InvalidOperation
from enum import StrEnum
from typing import cast

from teachmemusic.score.models import ScoreRepresentation
from teachmemusic.score.serializer import (
    ScoreSerializationError,
    score_from_dict,
    score_to_dict,
)

from .auxiliary import (
    OpusCatalog,
    OpusItem,
    SoundCatalog,
    SoundCatalogEntry,
    SoundCatalogMapping,
)
from .documents import (
    CANONICAL_SCHEMA_ID,
    CANONICAL_SCHEMA_VERSION,
    CanonicalDocument,
    CanonicalMusicPackage,
    CanonicalScoreContent,
    MediaDocument,
    OpusDocument,
    PackageRelationship,
    PackageRelationshipKind,
    ScoreDocument,
    SoundsDocument,
    TemporalScoreContent,
    V1CompatibilityContent,
)
from .identity import (
    CanonicalId,
    EntityKind,
    EntityReference,
    SourceLocation,
    SourceMapEntry,
)
from .links import ExternalLink
from .provenance import (
    PackageProvenance,
    SourceDocument,
    SourceDocumentFormat,
    Transformation,
    TransformationKind,
)
from .temporal_codec import (
    TemporalCodecError,
    deferred_from_dict,
    deferred_to_dict,
    temporal_from_dict,
    temporal_to_dict,
)
from .validation import (
    CanonicalValidationError,
    require_valid_package,
    validate_exact_number,
    validate_measured_value,
)
from .values import (
    CanonicalUnit,
    ExactDecimal,
    ExactInteger,
    ExactNumber,
    ExactRational,
    MeasuredValue,
    SpecifiedValue,
    ValueState,
)


class CanonicalSerializationError(ValueError):
    """Raised when canonical JSON is malformed, unsupported, or invalid."""


def exact_number_to_dict(value: ExactNumber) -> dict[str, object]:
    """Encode an exact canonical number without binary floating point."""

    issues = validate_exact_number(value, "exact_number")
    if issues:
        raise CanonicalSerializationError(issues[0].message)
    if isinstance(value, ExactInteger):
        return {"kind": "integer", "value": value.value}
    if isinstance(value, ExactDecimal):
        return {"kind": "decimal", "value": str(value.value)}
    return {
        "denominator": value.denominator,
        "kind": "rational",
        "numerator": value.numerator,
    }


def exact_number_from_dict(data: object) -> ExactNumber:
    """Decode one strictly tagged exact canonical number."""

    root = _mapping(data, "exact_number")
    kind = _string(root.get("kind"), "exact_number.kind")
    if kind == "integer":
        _expect_keys(root, {"kind", "value"}, "exact_number")
        result: ExactNumber = ExactInteger(_integer(root["value"], "exact_number.value"))
    elif kind == "decimal":
        _expect_keys(root, {"kind", "value"}, "exact_number")
        text = _string(root["value"], "exact_number.value")
        try:
            result = ExactDecimal(Decimal(text))
        except InvalidOperation as error:
            raise CanonicalSerializationError("exact_number.value: invalid decimal") from error
    elif kind == "rational":
        _expect_keys(root, {"denominator", "kind", "numerator"}, "exact_number")
        result = ExactRational(
            numerator=_integer(root["numerator"], "exact_number.numerator"),
            denominator=_integer(root["denominator"], "exact_number.denominator"),
        )
    else:
        raise CanonicalSerializationError(f"exact_number.kind: unsupported kind {kind!r}")
    issues = validate_exact_number(result, "exact_number")
    if issues:
        raise CanonicalSerializationError(f"{issues[0].path}: {issues[0].message}")
    return result


def measured_value_to_dict(value: MeasuredValue) -> dict[str, object]:
    """Encode an exact value together with its unit."""

    issues = validate_measured_value(value, "measured_value")
    if issues:
        raise CanonicalSerializationError(issues[0].message)
    return {"number": exact_number_to_dict(value.number), "unit": value.unit.value}


def measured_value_from_dict(data: object) -> MeasuredValue:
    """Decode one strictly typed exact unit-bearing value."""

    root = _mapping(data, "measured_value")
    _expect_keys(root, {"number", "unit"}, "measured_value")
    result = MeasuredValue(
        number=exact_number_from_dict(root["number"]),
        unit=_enum(CanonicalUnit, root["unit"], "measured_value.unit"),
    )
    issues = validate_measured_value(result, "measured_value")
    if issues:
        raise CanonicalSerializationError(issues[0].message)
    return result


def package_to_dict(package: CanonicalMusicPackage) -> dict[str, object]:
    """Convert a valid canonical package to strict JSON-compatible data."""

    require_valid_package(package)
    result: dict[str, object] = {
        "documents": [_document_to_dict(document) for document in package.documents],
        "id": _id_to_dict(package.id),
        "provenance": _provenance_to_dict(package.provenance),
        "root_documents": [_reference_to_dict(item) for item in package.root_documents],
        "schema_id": package.schema_id,
        "schema_version": package.schema_version,
    }
    if package.relationships:
        result["relationships"] = [_relationship_to_dict(item) for item in package.relationships]
    return result


def package_to_json(package: CanonicalMusicPackage) -> str:
    """Serialize a canonical package reproducibly."""

    return json.dumps(package_to_dict(package), ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def package_from_dict(data: object) -> CanonicalMusicPackage:
    """Decode and validate strict schema-v2 package data."""

    root = _mapping(data, "package")
    required_keys = {
        "documents",
        "id",
        "provenance",
        "root_documents",
        "schema_id",
        "schema_version",
    }
    _expect_keys(
        root,
        required_keys | ({"relationships"} if "relationships" in root else set()),
        "package",
    )
    schema_id = _string(root["schema_id"], "package.schema_id")
    schema_version = _string(root["schema_version"], "package.schema_version")
    if schema_id != CANONICAL_SCHEMA_ID:
        raise CanonicalSerializationError(f"package.schema_id: unsupported schema ID {schema_id!r}")
    if schema_version != CANONICAL_SCHEMA_VERSION:
        raise CanonicalSerializationError(
            f"package.schema_version: unsupported version {schema_version!r}"
        )
    package = CanonicalMusicPackage(
        id=_id_from_dict(root["id"], "package.id"),
        documents=tuple(
            _document_from_dict(item, f"package.documents[{index}]")
            for index, item in enumerate(_sequence(root["documents"], "package.documents"))
        ),
        root_documents=tuple(
            _reference_from_dict(item, f"package.root_documents[{index}]")
            for index, item in enumerate(
                _sequence(root["root_documents"], "package.root_documents")
            )
        ),
        provenance=_provenance_from_dict(root["provenance"], "package.provenance"),
        relationships=tuple(
            _relationship_from_dict(item, f"package.relationships[{index}]")
            for index, item in enumerate(
                _sequence(root.get("relationships", []), "package.relationships")
            )
        ),
        schema_id=schema_id,
        schema_version=schema_version,
    )
    try:
        require_valid_package(package)
    except CanonicalValidationError as error:
        raise CanonicalSerializationError(f"decoded package is invalid: {error}") from error
    return package


def package_from_json(payload: str) -> CanonicalMusicPackage:
    """Decode a canonical schema-v2 JSON document."""

    return package_from_dict(_load_json(payload))


def canonical_from_json(payload: str) -> ScoreRepresentation | CanonicalMusicPackage:
    """Dispatch legacy v1 or identified v2 canonical JSON without upgrading it."""

    data = _load_json(payload)
    root = _mapping(data, "canonical")
    if "schema_id" in root:
        return package_from_dict(root)
    return _v1_score_from_dict(root, "canonical")


def _document_to_dict(document: CanonicalDocument) -> dict[str, object]:
    common: dict[str, object] = {
        "id": _id_to_dict(document.id),
        "source_documents": [_reference_to_dict(item) for item in document.source_documents],
    }
    if isinstance(document, ScoreDocument):
        if isinstance(document.content, CanonicalScoreContent):
            return {
                **common,
                "content": {
                    "kind": "canonical-score",
                    "completeness": document.content.completeness,
                    "score": temporal_to_dict(document.content.score),
                },
                "kind": "score",
            }
        if isinstance(document.content, TemporalScoreContent):
            return {
                **common,
                "content": {
                    "kind": "temporal-partial",
                    "completeness": document.content.completeness,
                    "score": temporal_to_dict(document.content.score),
                    "deferred": [deferred_to_dict(item) for item in document.content.deferred],
                },
                "kind": "score",
            }
        if not isinstance(document.content, V1CompatibilityContent):
            raise CanonicalSerializationError("unsupported score content")
        return {
            **common,
            "content": {
                "kind": "v1-compatibility",
                "score": score_to_dict(document.content.score),
            },
            "kind": "score",
        }
    if isinstance(document, OpusDocument):
        result = {
            **common,
            "kind": "opus",
            "members": [_reference_to_dict(item) for item in document.members],
            "title": _specified_to_dict(document.title, _identity),
        }
        if document.content is not None:
            result["content"] = _opus_to_dict(document.content)
        return result
    if isinstance(document, SoundsDocument):
        result = {
            **common,
            "kind": "sounds",
            "name": _specified_to_dict(document.name, _identity),
        }
        if document.content is not None:
            result["content"] = _sounds_to_dict(document.content)
        return result
    return {
        **common,
        "kind": "media",
        "logical_path": document.logical_path,
        "media_type": _specified_to_dict(document.media_type, _identity),
        "sha256": _specified_to_dict(document.sha256, _identity),
    }


def _document_from_dict(data: object, path: str) -> CanonicalDocument:
    root = _mapping(data, path)
    kind = _string(root.get("kind"), f"{path}.kind")
    if kind == "score":
        _expect_keys(root, {"content", "id", "kind", "source_documents"}, path)
        content = _mapping(root["content"], f"{path}.content")
        content_kind = _string(content.get("kind"), f"{path}.content.kind")
        if content_kind == "canonical-score":
            _expect_keys(content, {"kind", "completeness", "score"}, f"{path}.content")
            try:
                temporal_score = temporal_from_dict(content["score"])
            except TemporalCodecError as error:
                raise CanonicalSerializationError(f"{path}.content: {error}") from error
            return ScoreDocument(
                id=_id_from_dict(root["id"], f"{path}.id"),
                source_documents=_references_from_data(
                    root["source_documents"], f"{path}.source_documents"
                ),
                content=CanonicalScoreContent(
                    score=temporal_score,
                    completeness=_string(content["completeness"], f"{path}.content.completeness"),
                ),
            )
        if content_kind == "temporal-partial":
            _expect_keys(
                content,
                {"kind", "completeness", "score", "deferred"},
                f"{path}.content",
            )
            try:
                temporal_score = temporal_from_dict(content["score"])
                deferred = tuple(
                    deferred_from_dict(item)
                    for item in _sequence(content["deferred"], f"{path}.content.deferred")
                )
            except TemporalCodecError as error:
                raise CanonicalSerializationError(f"{path}.content: {error}") from error
            return ScoreDocument(
                id=_id_from_dict(root["id"], f"{path}.id"),
                source_documents=_references_from_data(
                    root["source_documents"], f"{path}.source_documents"
                ),
                content=TemporalScoreContent(
                    score=temporal_score,
                    deferred=deferred,
                    completeness=_string(content["completeness"], f"{path}.content.completeness"),
                ),
            )
        _expect_keys(content, {"kind", "score"}, f"{path}.content")
        if content_kind != "v1-compatibility":
            raise CanonicalSerializationError(f"{path}.content.kind: unsupported score content")
        return ScoreDocument(
            id=_id_from_dict(root["id"], f"{path}.id"),
            source_documents=_references_from_data(
                root["source_documents"], f"{path}.source_documents"
            ),
            content=V1CompatibilityContent(
                score=_v1_score_from_dict(content["score"], f"{path}.content.score")
            ),
        )
    if kind == "opus":
        expected = {"id", "kind", "members", "source_documents", "title"}
        _expect_keys(root, expected | ({"content"} if "content" in root else set()), path)
        return OpusDocument(
            id=_id_from_dict(root["id"], f"{path}.id"),
            source_documents=_references_from_data(
                root["source_documents"], f"{path}.source_documents"
            ),
            title=_specified_from_dict(root["title"], f"{path}.title", _string_value),
            members=_references_from_data(root["members"], f"{path}.members"),
            content=(
                _opus_from_dict(root["content"], f"{path}.content") if "content" in root else None
            ),
        )
    if kind == "sounds":
        expected = {"id", "kind", "name", "source_documents"}
        _expect_keys(root, expected | ({"content"} if "content" in root else set()), path)
        return SoundsDocument(
            id=_id_from_dict(root["id"], f"{path}.id"),
            source_documents=_references_from_data(
                root["source_documents"], f"{path}.source_documents"
            ),
            name=_specified_from_dict(root["name"], f"{path}.name", _string_value),
            content=(
                _sounds_from_dict(root["content"], f"{path}.content") if "content" in root else None
            ),
        )
    if kind == "media":
        _expect_keys(
            root,
            {"id", "kind", "logical_path", "media_type", "sha256", "source_documents"},
            path,
        )
        return MediaDocument(
            id=_id_from_dict(root["id"], f"{path}.id"),
            source_documents=_references_from_data(
                root["source_documents"], f"{path}.source_documents"
            ),
            logical_path=_string(root["logical_path"], f"{path}.logical_path"),
            media_type=_specified_from_dict(
                root["media_type"], f"{path}.media_type", _string_value
            ),
            sha256=_specified_from_dict(root["sha256"], f"{path}.sha256", _string_value),
        )
    raise CanonicalSerializationError(f"{path}.kind: unsupported document kind {kind!r}")


def _relationship_to_dict(value: PackageRelationship) -> dict[str, object]:
    return {
        "href": value.href,
        "kind": value.kind.value,
        "source": _reference_to_dict(value.source),
        "source_order": value.source_order,
        "target": _reference_to_dict(value.target),
    }


def _relationship_from_dict(data: object, path: str) -> PackageRelationship:
    root = _mapping(data, path)
    _expect_keys(root, {"href", "kind", "source", "source_order", "target"}, path)
    return PackageRelationship(
        kind=_enum(PackageRelationshipKind, root["kind"], f"{path}.kind"),
        source=_reference_from_dict(root["source"], f"{path}.source"),
        target=_reference_from_dict(root["target"], f"{path}.target"),
        href=_string(root["href"], f"{path}.href"),
        source_order=_integer(root["source_order"], f"{path}.source_order"),
    )


def _external_link_to_dict(value: ExternalLink) -> dict[str, object]:
    return {
        "actuate": value.actuate,
        "href": value.href,
        "role": value.role,
        "show": value.show,
        "title": value.title,
        "type": value.link_type,
    }


def _external_link_from_dict(data: object, path: str) -> ExternalLink:
    root = _mapping(data, path)
    _expect_keys(root, {"actuate", "href", "role", "show", "title", "type"}, path)
    return ExternalLink(
        href=_string(root["href"], f"{path}.href"),
        link_type=_optional_string(root["type"], f"{path}.type"),
        role=_optional_string(root["role"], f"{path}.role"),
        title=_optional_string(root["title"], f"{path}.title"),
        show=_optional_string(root["show"], f"{path}.show"),
        actuate=_optional_string(root["actuate"], f"{path}.actuate"),
    )


def _opus_item_to_dict(value: OpusItem) -> dict[str, object]:
    return {
        "children": [_opus_item_to_dict(item) for item in value.children],
        "kind": value.kind,
        "link": _external_link_to_dict(value.link) if value.link is not None else None,
        "new_page": value.new_page,
        "title": value.title,
    }


def _opus_item_from_dict(data: object, path: str) -> OpusItem:
    root = _mapping(data, path)
    _expect_keys(root, {"children", "kind", "link", "new_page", "title"}, path)
    return OpusItem(
        kind=_string(root["kind"], f"{path}.kind"),
        link=(
            _external_link_from_dict(root["link"], f"{path}.link")
            if root["link"] is not None
            else None
        ),
        new_page=_optional_boolean(root["new_page"], f"{path}.new_page"),
        title=_optional_string(root["title"], f"{path}.title"),
        children=tuple(
            _opus_item_from_dict(item, f"{path}.children[{index}]")
            for index, item in enumerate(_sequence(root["children"], f"{path}.children"))
        ),
    )


def _opus_to_dict(value: OpusCatalog) -> dict[str, object]:
    return {
        "items": [_opus_item_to_dict(item) for item in value.items],
        "kind": "opus-catalog",
        "title": value.title,
        "version": value.version,
    }


def _opus_from_dict(data: object, path: str) -> OpusCatalog:
    root = _mapping(data, path)
    _expect_keys(root, {"items", "kind", "title", "version"}, path)
    if _string(root["kind"], f"{path}.kind") != "opus-catalog":
        raise CanonicalSerializationError(f"{path}.kind: expected 'opus-catalog'")
    return OpusCatalog(
        version=_string(root["version"], f"{path}.version"),
        title=_optional_string(root["title"], f"{path}.title"),
        items=tuple(
            _opus_item_from_dict(item, f"{path}.items[{index}]")
            for index, item in enumerate(_sequence(root["items"], f"{path}.items"))
        ),
    )


def _sounds_to_dict(value: SoundCatalog) -> dict[str, object]:
    return {
        "entries": [
            {
                "id": entry.id,
                "mappings": [
                    {
                        "ensemble_size": mapping.ensemble_size,
                        "kind": mapping.kind,
                        "primary": mapping.primary,
                        "value": mapping.value,
                    }
                    for mapping in entry.mappings
                ],
                "primary": entry.primary,
            }
            for entry in value.entries
        ],
        "kind": "sound-catalog",
        "version": value.version,
    }


def _sounds_from_dict(data: object, path: str) -> SoundCatalog:
    root = _mapping(data, path)
    _expect_keys(root, {"entries", "kind", "version"}, path)
    if _string(root["kind"], f"{path}.kind") != "sound-catalog":
        raise CanonicalSerializationError(f"{path}.kind: expected 'sound-catalog'")
    entries: list[SoundCatalogEntry] = []
    for index, item in enumerate(_sequence(root["entries"], f"{path}.entries")):
        entry_path = f"{path}.entries[{index}]"
        entry = _mapping(item, entry_path)
        _expect_keys(entry, {"id", "mappings", "primary"}, entry_path)
        mappings: list[SoundCatalogMapping] = []
        for mapping_index, mapping_item in enumerate(
            _sequence(entry["mappings"], f"{entry_path}.mappings")
        ):
            mapping_path = f"{entry_path}.mappings[{mapping_index}]"
            mapping = _mapping(mapping_item, mapping_path)
            _expect_keys(
                mapping,
                {"ensemble_size", "kind", "primary", "value"},
                mapping_path,
            )
            mappings.append(
                SoundCatalogMapping(
                    kind=_string(mapping["kind"], f"{mapping_path}.kind"),
                    value=_string(mapping["value"], f"{mapping_path}.value"),
                    primary=_optional_boolean(mapping["primary"], f"{mapping_path}.primary"),
                    ensemble_size=_optional_string(
                        mapping["ensemble_size"], f"{mapping_path}.ensemble_size"
                    ),
                )
            )
        entries.append(
            SoundCatalogEntry(
                id=_string(entry["id"], f"{entry_path}.id"),
                primary=_optional_boolean(entry["primary"], f"{entry_path}.primary"),
                mappings=tuple(mappings),
            )
        )
    return SoundCatalog(
        version=_string(root["version"], f"{path}.version"),
        entries=tuple(entries),
    )


def _provenance_to_dict(value: PackageProvenance) -> dict[str, object]:
    return {
        "diagnostic_codes": list(value.diagnostic_codes),
        "source_map": [_source_map_to_dict(item) for item in value.source_map],
        "sources": [_source_to_dict(item) for item in value.sources],
        "transformations": [
            {
                "input_sha256": item.input_sha256,
                "kind": item.kind.value,
                "source_schema": item.source_schema,
                "target_schema": item.target_schema,
            }
            for item in value.transformations
        ],
    }


def _provenance_from_dict(data: object, path: str) -> PackageProvenance:
    root = _mapping(data, path)
    _expect_keys(root, {"diagnostic_codes", "source_map", "sources", "transformations"}, path)
    return PackageProvenance(
        sources=tuple(
            _source_from_dict(item, f"{path}.sources[{index}]")
            for index, item in enumerate(_sequence(root["sources"], f"{path}.sources"))
        ),
        source_map=tuple(
            _source_map_from_dict(item, f"{path}.source_map[{index}]")
            for index, item in enumerate(_sequence(root["source_map"], f"{path}.source_map"))
        ),
        transformations=tuple(
            _transformation_from_dict(item, f"{path}.transformations[{index}]")
            for index, item in enumerate(
                _sequence(root["transformations"], f"{path}.transformations")
            )
        ),
        diagnostic_codes=tuple(
            _string(item, f"{path}.diagnostic_codes[{index}]")
            for index, item in enumerate(
                _sequence(root["diagnostic_codes"], f"{path}.diagnostic_codes")
            )
        ),
    )


def _source_to_dict(source: SourceDocument) -> dict[str, object]:
    return {
        "byte_length": _specified_to_dict(source.byte_length, _identity),
        "declared_musicxml_version": _specified_to_dict(
            source.declared_musicxml_version, _identity
        ),
        "document_form": _specified_to_dict(source.document_form, _identity),
        "id": _id_to_dict(source.id),
        "logical_name": _specified_to_dict(source.logical_name, _identity),
        "sha256": _specified_to_dict(source.sha256, _identity),
        "source_format": _specified_to_dict(source.source_format, lambda item: item.value),
        "validated_musicxml_version": _specified_to_dict(
            source.validated_musicxml_version, _identity
        ),
    }


def _source_from_dict(data: object, path: str) -> SourceDocument:
    root = _mapping(data, path)
    _expect_keys(
        root,
        {
            "byte_length",
            "declared_musicxml_version",
            "document_form",
            "id",
            "logical_name",
            "sha256",
            "source_format",
            "validated_musicxml_version",
        },
        path,
    )
    return SourceDocument(
        id=_id_from_dict(root["id"], f"{path}.id"),
        source_format=_specified_from_dict(
            root["source_format"],
            f"{path}.source_format",
            lambda item, item_path: _enum(SourceDocumentFormat, item, item_path),
        ),
        logical_name=_specified_from_dict(
            root["logical_name"], f"{path}.logical_name", _string_value
        ),
        sha256=_specified_from_dict(root["sha256"], f"{path}.sha256", _string_value),
        byte_length=_specified_from_dict(
            root["byte_length"], f"{path}.byte_length", _integer_value
        ),
        declared_musicxml_version=_specified_from_dict(
            root["declared_musicxml_version"],
            f"{path}.declared_musicxml_version",
            _string_value,
        ),
        validated_musicxml_version=_specified_from_dict(
            root["validated_musicxml_version"],
            f"{path}.validated_musicxml_version",
            _string_value,
        ),
        document_form=_specified_from_dict(
            root["document_form"], f"{path}.document_form", _string_value
        ),
    )


def _transformation_from_dict(data: object, path: str) -> Transformation:
    root = _mapping(data, path)
    _expect_keys(root, {"input_sha256", "kind", "source_schema", "target_schema"}, path)
    return Transformation(
        kind=_enum(TransformationKind, root["kind"], f"{path}.kind"),
        source_schema=_string(root["source_schema"], f"{path}.source_schema"),
        target_schema=_string(root["target_schema"], f"{path}.target_schema"),
        input_sha256=_string(root["input_sha256"], f"{path}.input_sha256"),
    )


def _source_map_to_dict(entry: SourceMapEntry) -> dict[str, object]:
    return {
        "entity": _reference_to_dict(entry.entity),
        "locations": [
            {
                "column": item.column,
                "line": item.line,
                "logical_path": item.logical_path,
                "source_document": _reference_to_dict(item.source_document),
                "source_ordinal": item.source_ordinal,
            }
            for item in entry.locations
        ],
    }


def _source_map_from_dict(data: object, path: str) -> SourceMapEntry:
    root = _mapping(data, path)
    _expect_keys(root, {"entity", "locations"}, path)
    return SourceMapEntry(
        entity=_reference_from_dict(root["entity"], f"{path}.entity"),
        locations=tuple(
            _source_location_from_dict(item, f"{path}.locations[{index}]")
            for index, item in enumerate(_sequence(root["locations"], f"{path}.locations"))
        ),
    )


def _source_location_from_dict(data: object, path: str) -> SourceLocation:
    root = _mapping(data, path)
    _expect_keys(
        root,
        {"column", "line", "logical_path", "source_document", "source_ordinal"},
        path,
    )
    return SourceLocation(
        source_document=_reference_from_dict(root["source_document"], f"{path}.source_document"),
        logical_path=_string(root["logical_path"], f"{path}.logical_path"),
        line=_optional_integer(root["line"], f"{path}.line"),
        column=_optional_integer(root["column"], f"{path}.column"),
        source_ordinal=_optional_integer(root["source_ordinal"], f"{path}.source_ordinal"),
    )


def _specified_to_dict[T](
    value: SpecifiedValue[T], encode: Callable[[T], object]
) -> dict[str, object]:
    result: dict[str, object] = {"state": value.state.value}
    if value.value is not None:
        result["value"] = encode(value.value)
    return result


def _specified_from_dict[T](
    data: object,
    path: str,
    decode: Callable[[object, str], T],
) -> SpecifiedValue[T]:
    root = _mapping(data, path)
    state = _enum(ValueState, root.get("state"), f"{path}.state")
    expects_value = state in {
        ValueState.EXPLICIT_VALUE,
        ValueState.DEFAULTED,
        ValueState.INHERITED,
    }
    _expect_keys(root, {"state", "value"} if expects_value else {"state"}, path)
    value = decode(root["value"], f"{path}.value") if expects_value else None
    return SpecifiedValue(state=state, value=value)


def _id_to_dict(value: CanonicalId) -> dict[str, object]:
    return {"kind": value.kind.value, "value": value.value}


def _id_from_dict(data: object, path: str) -> CanonicalId:
    root = _mapping(data, path)
    _expect_keys(root, {"kind", "value"}, path)
    return CanonicalId(
        kind=_enum(EntityKind, root["kind"], f"{path}.kind"),
        value=_string(root["value"], f"{path}.value"),
    )


def _reference_to_dict(value: EntityReference) -> dict[str, object]:
    return {"target_id": value.target_id, "target_kind": value.target_kind.value}


def _reference_from_dict(data: object, path: str) -> EntityReference:
    root = _mapping(data, path)
    _expect_keys(root, {"target_id", "target_kind"}, path)
    return EntityReference(
        target_kind=_enum(EntityKind, root["target_kind"], f"{path}.target_kind"),
        target_id=_string(root["target_id"], f"{path}.target_id"),
    )


def _references_from_data(data: object, path: str) -> tuple[EntityReference, ...]:
    return tuple(
        _reference_from_dict(item, f"{path}[{index}]")
        for index, item in enumerate(_sequence(data, path))
    )


def _v1_score_from_dict(data: object, path: str) -> ScoreRepresentation:
    try:
        return score_from_dict(data)
    except ScoreSerializationError as error:
        raise CanonicalSerializationError(f"{path}: invalid schema-v1 content: {error}") from error


def _load_json(payload: str) -> object:
    try:
        return json.loads(
            payload,
            object_pairs_hook=_unique_object,
            parse_constant=_reject_nonfinite_json,
        )
    except json.JSONDecodeError as error:
        raise CanonicalSerializationError(f"invalid JSON: {error.msg}") from error


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise CanonicalSerializationError(f"duplicate JSON key {key!r}")
        result[key] = value
    return result


def _reject_nonfinite_json(value: str) -> object:
    raise CanonicalSerializationError(f"non-finite JSON value {value!r} is not supported")


def _mapping(data: object, path: str) -> dict[str, object]:
    if not isinstance(data, dict) or not all(isinstance(key, str) for key in data):
        raise CanonicalSerializationError(f"{path}: expected object")
    return cast(dict[str, object], data)


def _sequence(data: object, path: str) -> list[object]:
    if not isinstance(data, list):
        raise CanonicalSerializationError(f"{path}: expected array")
    return cast(list[object], data)


def _expect_keys(data: dict[str, object], expected: set[str], path: str) -> None:
    missing = sorted(expected - data.keys())
    unexpected = sorted(data.keys() - expected)
    if missing:
        raise CanonicalSerializationError(f"{path}: missing keys {missing}")
    if unexpected:
        raise CanonicalSerializationError(f"{path}: unexpected keys {unexpected}")


def _string(data: object, path: str) -> str:
    if not isinstance(data, str):
        raise CanonicalSerializationError(f"{path}: expected string")
    return data


def _integer(data: object, path: str) -> int:
    if not isinstance(data, int) or isinstance(data, bool):
        raise CanonicalSerializationError(f"{path}: expected integer")
    return data


def _optional_integer(data: object, path: str) -> int | None:
    return None if data is None else _integer(data, path)


def _optional_string(data: object, path: str) -> str | None:
    return None if data is None else _string(data, path)


def _optional_boolean(data: object, path: str) -> bool | None:
    if data is None:
        return None
    if not isinstance(data, bool):
        raise CanonicalSerializationError(f"{path}: expected boolean or null")
    return data


def _enum[E: StrEnum](enum_type: type[E], data: object, path: str) -> E:
    value = _string(data, path)
    try:
        return enum_type(value)
    except ValueError as error:
        raise CanonicalSerializationError(f"{path}: unsupported value {value!r}") from error


def _identity[T](value: T) -> T:
    return value


def _string_value(data: object, path: str) -> str:
    return _string(data, path)


def _integer_value(data: object, path: str) -> int:
    return _integer(data, path)
