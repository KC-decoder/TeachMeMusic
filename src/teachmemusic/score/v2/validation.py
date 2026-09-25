"""Library-independent invariant validation for canonical schema version 2."""

from __future__ import annotations

import hashlib
import math
import re
from dataclasses import dataclass
from decimal import Decimal
from pathlib import PurePosixPath
from typing import cast

from teachmemusic.score.models import NoteEvent, RestEvent, ScoreRepresentation
from teachmemusic.score.serializer import score_to_json
from teachmemusic.score.validation import validate_score

from .auxiliary_validation import validate_auxiliary_document
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
from .identity import CanonicalId, EntityKind, EntityReference, SourceMapEntry
from .provenance import SourceDocument, SourceDocumentFormat, TransformationKind
from .temporal import TemporalScore
from .temporal_validation import validate_deferred_constructs, validate_temporal_score
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

_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]*$")
_SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")


@dataclass(frozen=True, slots=True)
class CanonicalValidationIssue:
    """One stable schema-v2 invariant failure."""

    code: str
    path: str
    message: str


class CanonicalValidationError(ValueError):
    """Raised when a canonical package violates one or more invariants."""

    def __init__(self, issues: tuple[CanonicalValidationIssue, ...]) -> None:
        if not issues:
            raise ValueError("at least one validation issue is required")
        self.issues = issues
        super().__init__(
            "; ".join(f"{issue.code} at {issue.path}: {issue.message}" for issue in issues)
        )


def validate_specified_value(
    value: SpecifiedValue[object], path: str
) -> tuple[CanonicalValidationIssue, ...]:
    """Validate the reusable explicit/default/inherited/unknown contract."""

    issues: list[CanonicalValidationIssue] = []
    if not isinstance(value, SpecifiedValue):
        return (CanonicalValidationIssue("V2_VALUE_TYPE", path, "expected SpecifiedValue"),)
    if not isinstance(value.state, ValueState):
        issues.append(
            CanonicalValidationIssue("V2_VALUE_STATE", f"{path}.state", "unknown value state")
        )
        return tuple(issues)
    needs_value = value.state in {
        ValueState.EXPLICIT_VALUE,
        ValueState.DEFAULTED,
        ValueState.INHERITED,
    }
    if needs_value and value.value is None:
        issues.append(
            CanonicalValidationIssue(
                "V2_VALUE_MISSING",
                f"{path}.value",
                f"{value.state.value} requires a resolved value",
            )
        )
    if not needs_value and value.value is not None:
        issues.append(
            CanonicalValidationIssue(
                "V2_VALUE_UNEXPECTED",
                f"{path}.value",
                f"{value.state.value} cannot carry a resolved value",
            )
        )
    return tuple(issues)


def validate_exact_number(value: ExactNumber, path: str) -> tuple[CanonicalValidationIssue, ...]:
    """Validate canonical exact-number shape and normalization."""

    if isinstance(value, ExactInteger):
        if not isinstance(value.value, int) or isinstance(value.value, bool):
            return (
                CanonicalValidationIssue(
                    "V2_EXACT_INTEGER", path, "expected a non-boolean integer"
                ),
            )
        return ()
    if isinstance(value, ExactDecimal):
        if not isinstance(value.value, Decimal) or not value.value.is_finite():
            return (
                CanonicalValidationIssue("V2_EXACT_DECIMAL", path, "expected a finite Decimal"),
            )
        return ()
    if isinstance(value, ExactRational):
        if (
            not isinstance(value.numerator, int)
            or isinstance(value.numerator, bool)
            or not isinstance(value.denominator, int)
            or isinstance(value.denominator, bool)
            or value.denominator <= 0
        ):
            return (
                CanonicalValidationIssue(
                    "V2_EXACT_RATIONAL",
                    path,
                    "expected integer numerator and positive integer denominator",
                ),
            )
        if math.gcd(value.numerator, value.denominator) != 1:
            return (
                CanonicalValidationIssue(
                    "V2_EXACT_RATIONAL_NOT_REDUCED",
                    path,
                    "rational values must be in reduced form",
                ),
            )
        return ()
    return (CanonicalValidationIssue("V2_EXACT_NUMBER", path, "unknown exact-number type"),)


def validate_measured_value(
    value: MeasuredValue,
    path: str,
) -> tuple[CanonicalValidationIssue, ...]:
    """Validate an exact number paired with a known canonical unit."""

    if not isinstance(value, MeasuredValue):
        return (CanonicalValidationIssue("V2_MEASURED_VALUE", path, "expected MeasuredValue"),)
    issues = list(validate_exact_number(value.number, f"{path}.number"))
    if not isinstance(value.unit, CanonicalUnit):
        issues.append(
            CanonicalValidationIssue(
                "V2_MEASURED_UNIT",
                f"{path}.unit",
                "unknown canonical unit",
            )
        )
    return tuple(issues)


def validate_package(package: CanonicalMusicPackage) -> tuple[CanonicalValidationIssue, ...]:
    """Return all deterministic core-invariant failures for a v2 package."""

    issues: list[CanonicalValidationIssue] = []
    add = issues.append
    if package.schema_id != CANONICAL_SCHEMA_ID:
        add(CanonicalValidationIssue("V2_SCHEMA_ID", "package.schema_id", "unsupported schema ID"))
    if package.schema_version != CANONICAL_SCHEMA_VERSION:
        add(
            CanonicalValidationIssue(
                "V2_SCHEMA_VERSION",
                "package.schema_version",
                "unsupported schema version",
            )
        )
    _validate_id(package.id, EntityKind.PACKAGE, "package.id", issues)
    for field_name in ("documents", "root_documents", "relationships"):
        if not isinstance(getattr(package, field_name), tuple):
            add(
                CanonicalValidationIssue(
                    "V2_MUTABLE_COLLECTION",
                    f"package.{field_name}",
                    "canonical collections must be tuples",
                )
            )

    known: dict[tuple[EntityKind, str], str] = {}
    _register_id(package.id, "package.id", known, issues)
    source_ids: set[tuple[EntityKind, str]] = set()
    for index, source in enumerate(package.provenance.sources):
        path = f"package.provenance.sources[{index}]"
        _validate_source(source, path, issues)
        _register_id(source.id, f"{path}.id", known, issues)
        source_ids.add((source.id.kind, source.id.value))

    document_ids: set[tuple[EntityKind, str]] = set()
    for index, document in enumerate(package.documents):
        path = f"package.documents[{index}]"
        _validate_document(document, path, issues)
        _register_id(document.id, f"{path}.id", known, issues)
        document_ids.add((document.id.kind, document.id.value))
        if isinstance(document, ScoreDocument):
            if isinstance(document.content, V1CompatibilityContent):
                _register_v1_entities(document.content.score, path, known, issues)
            elif isinstance(document.content, (TemporalScoreContent, CanonicalScoreContent)):
                _register_temporal_entities(document.content.score, path, known, issues)

    for index, document in enumerate(package.documents):
        path = f"package.documents[{index}]"
        for ref_index, reference in enumerate(document.source_documents):
            _validate_reference(
                reference,
                f"{path}.source_documents[{ref_index}]",
                source_ids,
                issues,
            )
        if isinstance(document, OpusDocument):
            for member_index, reference in enumerate(document.members):
                _validate_reference(
                    reference,
                    f"{path}.members[{member_index}]",
                    document_ids,
                    issues,
                )
                if isinstance(reference, EntityReference) and reference.target_kind not in {
                    EntityKind.SCORE,
                    EntityKind.OPUS,
                }:
                    issues.append(
                        CanonicalValidationIssue(
                            "V2_OPUS_MEMBER_KIND",
                            f"{path}.members[{member_index}]",
                            "opus members must reference a score or nested opus",
                        )
                    )

    for index, reference in enumerate(package.root_documents):
        _validate_reference(reference, f"package.root_documents[{index}]", document_ids, issues)

    relationship_keys: set[tuple[object, ...]] = set()
    for index, relationship in enumerate(package.relationships):
        path = f"package.relationships[{index}]"
        _validate_relationship(relationship, path, document_ids, issues)
        if isinstance(relationship, PackageRelationship):
            key = (
                relationship.kind,
                relationship.source.target_kind,
                relationship.source.target_id,
                relationship.target.target_kind,
                relationship.target.target_id,
                relationship.href,
                relationship.source_order,
            )
            if key in relationship_keys:
                issues.append(
                    CanonicalValidationIssue(
                        "V2_RELATIONSHIP_DUPLICATE",
                        path,
                        "package relationships must be unique",
                    )
                )
            relationship_keys.add(key)

    for index, entry in enumerate(package.provenance.source_map):
        _validate_source_map_entry(
            entry,
            f"package.provenance.source_map[{index}]",
            set(known),
            source_ids,
            issues,
        )

    migrated_scores = tuple(
        document.content.score
        for document in package.documents
        if isinstance(document, ScoreDocument)
        and isinstance(document.content, V1CompatibilityContent)
    )
    migration_records = tuple(
        item
        for item in package.provenance.transformations
        if item.kind is TransformationKind.MIGRATED_FROM_V1
    )
    if migrated_scores and not migration_records:
        add(
            CanonicalValidationIssue(
                "V2_MIGRATION_PROVENANCE_MISSING",
                "package.provenance.transformations",
                "v1 compatibility content requires migrated-from-v1 provenance",
            )
        )
    if len(migrated_scores) == 1 and len(migration_records) == 1:
        expected_digest = hashlib.sha256(
            score_to_json(migrated_scores[0]).encode("utf-8")
        ).hexdigest()
        if migration_records[0].input_sha256 != expected_digest:
            add(
                CanonicalValidationIssue(
                    "V2_MIGRATION_DIGEST_MISMATCH",
                    "package.provenance.transformations[0].input_sha256",
                    "migration input digest does not match retained v1 content",
                )
            )
    for index, transformation in enumerate(package.provenance.transformations):
        path = f"package.provenance.transformations[{index}]"
        if _SHA256_PATTERN.fullmatch(transformation.input_sha256) is None:
            add(
                CanonicalValidationIssue(
                    "V2_TRANSFORMATION_DIGEST",
                    f"{path}.input_sha256",
                    "expected 64 lowercase hexadecimal characters",
                )
            )
        if transformation.target_schema != CANONICAL_SCHEMA_VERSION:
            add(
                CanonicalValidationIssue(
                    "V2_TRANSFORMATION_TARGET",
                    f"{path}.target_schema",
                    "transformation target must match the package schema version",
                )
            )

    if not package.documents:
        add(
            CanonicalValidationIssue(
                "V2_PACKAGE_EMPTY", "package.documents", "package has no documents"
            )
        )
    if not package.root_documents:
        add(
            CanonicalValidationIssue(
                "V2_PACKAGE_ROOT_MISSING",
                "package.root_documents",
                "package has no root document",
            )
        )
    return tuple(issues)


def require_valid_package(package: CanonicalMusicPackage) -> None:
    """Raise when a schema-v2 package violates a core invariant."""

    issues = validate_package(package)
    if issues:
        raise CanonicalValidationError(issues)


def _validate_id(
    value: CanonicalId,
    expected_kind: EntityKind,
    path: str,
    issues: list[CanonicalValidationIssue],
) -> None:
    if not isinstance(value, CanonicalId):
        issues.append(CanonicalValidationIssue("V2_ID_TYPE", path, "expected CanonicalId"))
        return
    if value.kind is not expected_kind:
        issues.append(
            CanonicalValidationIssue(
                "V2_ID_KIND",
                f"{path}.kind",
                f"expected {expected_kind.value}",
            )
        )
    if not isinstance(value.value, str) or _ID_PATTERN.fullmatch(value.value) is None:
        issues.append(
            CanonicalValidationIssue(
                "V2_ID_VALUE",
                f"{path}.value",
                "ID must be a non-empty canonical token",
            )
        )


def _register_id(
    value: CanonicalId,
    path: str,
    known: dict[tuple[EntityKind, str], str],
    issues: list[CanonicalValidationIssue],
) -> None:
    if not isinstance(value, CanonicalId) or not isinstance(value.kind, EntityKind):
        return
    key = (value.kind, value.value)
    if key in known:
        issues.append(
            CanonicalValidationIssue(
                "V2_DUPLICATE_ID",
                path,
                f"duplicates {known[key]}",
            )
        )
    else:
        known[key] = path


def _validate_source(
    source: SourceDocument,
    path: str,
    issues: list[CanonicalValidationIssue],
) -> None:
    _validate_id(source.id, EntityKind.SOURCE_DOCUMENT, f"{path}.id", issues)
    fields: tuple[tuple[str, SpecifiedValue[object]], ...] = (
        ("source_format", cast(SpecifiedValue[object], source.source_format)),
        ("logical_name", cast(SpecifiedValue[object], source.logical_name)),
        ("sha256", cast(SpecifiedValue[object], source.sha256)),
        ("byte_length", cast(SpecifiedValue[object], source.byte_length)),
        (
            "declared_musicxml_version",
            cast(SpecifiedValue[object], source.declared_musicxml_version),
        ),
        (
            "validated_musicxml_version",
            cast(SpecifiedValue[object], source.validated_musicxml_version),
        ),
        ("document_form", cast(SpecifiedValue[object], source.document_form)),
    )
    for name, value in fields:
        issues.extend(validate_specified_value(value, f"{path}.{name}"))
    if source.source_format.value is not None and not isinstance(
        source.source_format.value, SourceDocumentFormat
    ):
        issues.append(
            CanonicalValidationIssue(
                "V2_SOURCE_FORMAT",
                f"{path}.source_format.value",
                "unknown source document format",
            )
        )
    if source.logical_name.value is not None:
        name = source.logical_name.value
        if not isinstance(name, str) or not name or PurePosixPath(name).is_absolute():
            issues.append(
                CanonicalValidationIssue(
                    "V2_SOURCE_NAME",
                    f"{path}.logical_name.value",
                    "logical source name must be non-empty and relative",
                )
            )
    if source.sha256.value is not None and (
        not isinstance(source.sha256.value, str)
        or _SHA256_PATTERN.fullmatch(source.sha256.value) is None
    ):
        issues.append(
            CanonicalValidationIssue(
                "V2_SOURCE_DIGEST",
                f"{path}.sha256.value",
                "expected 64 lowercase hexadecimal characters",
            )
        )
    if source.byte_length.value is not None and (
        not isinstance(source.byte_length.value, int)
        or isinstance(source.byte_length.value, bool)
        or source.byte_length.value < 0
    ):
        issues.append(
            CanonicalValidationIssue(
                "V2_SOURCE_LENGTH",
                f"{path}.byte_length.value",
                "byte length must be a non-negative integer",
            )
        )


def _validate_document(
    document: CanonicalDocument,
    path: str,
    issues: list[CanonicalValidationIssue],
) -> None:
    expected = {
        ScoreDocument: EntityKind.SCORE,
        OpusDocument: EntityKind.OPUS,
        SoundsDocument: EntityKind.SOUNDS,
        MediaDocument: EntityKind.MEDIA,
    }
    kind = expected.get(type(document))
    if kind is None:
        issues.append(CanonicalValidationIssue("V2_DOCUMENT_TYPE", path, "unknown document type"))
        return
    _validate_id(document.id, kind, f"{path}.id", issues)
    if not isinstance(document.source_documents, tuple):
        issues.append(
            CanonicalValidationIssue(
                "V2_MUTABLE_COLLECTION",
                f"{path}.source_documents",
                "source references must be a tuple",
            )
        )
    if isinstance(document, ScoreDocument):
        if isinstance(document.content, V1CompatibilityContent):
            if document.id.value != document.content.score.id:
                issues.append(
                    CanonicalValidationIssue(
                        "V2_SCORE_ID_MISMATCH",
                        f"{path}.content.score.id",
                        "migrated score ID must equal the document ID",
                    )
                )
            for issue in validate_score(document.content.score):
                issues.append(
                    CanonicalValidationIssue(
                        "V2_MIGRATED_V1_INVALID",
                        f"{path}.content.{issue.path}",
                        f"{issue.code}: {issue.message}",
                    )
                )
        elif isinstance(document.content, TemporalScoreContent):
            if document.content.completeness != "temporal-only":
                issues.append(
                    CanonicalValidationIssue(
                        "V2_TEMPORAL_COMPLETENESS",
                        f"{path}.content.completeness",
                        "temporal content cannot claim full-score readiness",
                    )
                )
            for temporal_issue in (
                *validate_temporal_score(document.content.score),
                *validate_deferred_constructs(document.content.deferred),
            ):
                issues.append(
                    CanonicalValidationIssue(
                        temporal_issue.code,
                        f"{path}.content.{temporal_issue.path}",
                        temporal_issue.message,
                    )
                )
        elif isinstance(document.content, CanonicalScoreContent):
            if document.content.completeness != "complete":
                issues.append(
                    CanonicalValidationIssue(
                        "V2_SCORE_COMPLETENESS",
                        f"{path}.content.completeness",
                        "canonical score content must be marked complete",
                    )
                )
            for temporal_issue in validate_temporal_score(document.content.score):
                issues.append(
                    CanonicalValidationIssue(
                        temporal_issue.code,
                        f"{path}.content.{temporal_issue.path}",
                        temporal_issue.message,
                    )
                )
        else:
            issues.append(
                CanonicalValidationIssue("V2_SCORE_CONTENT", f"{path}.content", "unknown content")
            )
    elif isinstance(document, OpusDocument):
        issues.extend(
            validate_specified_value(cast(SpecifiedValue[object], document.title), f"{path}.title")
        )
        if document.content is not None:
            for auxiliary_issue in validate_auxiliary_document(document.content):
                issues.append(
                    CanonicalValidationIssue(
                        auxiliary_issue.code,
                        f"{path}.content.{auxiliary_issue.path}",
                        auxiliary_issue.message,
                    )
                )
    elif isinstance(document, SoundsDocument):
        issues.extend(
            validate_specified_value(cast(SpecifiedValue[object], document.name), f"{path}.name")
        )
        if document.content is not None:
            for auxiliary_issue in validate_auxiliary_document(document.content):
                issues.append(
                    CanonicalValidationIssue(
                        auxiliary_issue.code,
                        f"{path}.content.{auxiliary_issue.path}",
                        auxiliary_issue.message,
                    )
                )
    elif isinstance(document, MediaDocument):
        if not document.logical_path or PurePosixPath(document.logical_path).is_absolute():
            issues.append(
                CanonicalValidationIssue(
                    "V2_MEDIA_PATH",
                    f"{path}.logical_path",
                    "media logical path must be non-empty and relative",
                )
            )
        issues.extend(
            validate_specified_value(
                cast(SpecifiedValue[object], document.media_type), f"{path}.media_type"
            )
        )
        issues.extend(
            validate_specified_value(
                cast(SpecifiedValue[object], document.sha256), f"{path}.sha256"
            )
        )
        if "\\" in document.logical_path or ".." in PurePosixPath(document.logical_path).parts:
            issues.append(
                CanonicalValidationIssue(
                    "V2_MEDIA_PATH",
                    f"{path}.logical_path",
                    "media logical path must be canonical and traversal-free",
                )
            )
        if document.media_type.value is not None and (
            not isinstance(document.media_type.value, str) or not document.media_type.value
        ):
            issues.append(
                CanonicalValidationIssue(
                    "V2_MEDIA_TYPE",
                    f"{path}.media_type.value",
                    "media type must be a non-empty string",
                )
            )
        if document.sha256.value is not None and (
            not isinstance(document.sha256.value, str)
            or _SHA256_PATTERN.fullmatch(document.sha256.value) is None
        ):
            issues.append(
                CanonicalValidationIssue(
                    "V2_MEDIA_DIGEST",
                    f"{path}.sha256.value",
                    "expected 64 lowercase hexadecimal characters",
                )
            )


def _validate_relationship(
    relationship: PackageRelationship,
    path: str,
    document_ids: set[tuple[EntityKind, str]],
    issues: list[CanonicalValidationIssue],
) -> None:
    if not isinstance(relationship, PackageRelationship):
        issues.append(
            CanonicalValidationIssue("V2_RELATIONSHIP_TYPE", path, "expected PackageRelationship")
        )
        return
    if not isinstance(relationship.kind, PackageRelationshipKind):
        issues.append(
            CanonicalValidationIssue(
                "V2_RELATIONSHIP_KIND", f"{path}.kind", "unknown relationship kind"
            )
        )
    _validate_reference(relationship.source, f"{path}.source", document_ids, issues)
    _validate_reference(relationship.target, f"{path}.target", document_ids, issues)
    if isinstance(relationship.kind, PackageRelationshipKind) and isinstance(
        relationship.source, EntityReference
    ):
        allowed_sources = {
            PackageRelationshipKind.LINKED_PART: {EntityKind.SCORE},
            PackageRelationshipKind.OPUS_MEMBER: {EntityKind.OPUS},
            PackageRelationshipKind.WORK_OPUS: {EntityKind.SCORE},
            PackageRelationshipKind.MEDIA_RESOURCE: {EntityKind.SCORE},
            PackageRelationshipKind.RESOURCE_LINK: {EntityKind.SCORE},
        }.get(relationship.kind)
        if allowed_sources is not None and relationship.source.target_kind not in allowed_sources:
            issues.append(
                CanonicalValidationIssue(
                    "V2_RELATIONSHIP_SOURCE_KIND",
                    f"{path}.source",
                    f"{relationship.kind.value} has an invalid source document kind",
                )
            )
    if isinstance(relationship.kind, PackageRelationshipKind) and isinstance(
        relationship.target, EntityReference
    ):
        allowed_targets = {
            PackageRelationshipKind.LINKED_PART: {EntityKind.SCORE},
            PackageRelationshipKind.OPUS_MEMBER: {EntityKind.SCORE, EntityKind.OPUS},
            PackageRelationshipKind.WORK_OPUS: {EntityKind.OPUS},
            PackageRelationshipKind.MEDIA_RESOURCE: {EntityKind.MEDIA},
        }.get(relationship.kind)
        if allowed_targets is not None and relationship.target.target_kind not in allowed_targets:
            issues.append(
                CanonicalValidationIssue(
                    "V2_RELATIONSHIP_TARGET_KIND",
                    f"{path}.target",
                    f"{relationship.kind.value} has an invalid target document kind",
                )
            )
    if relationship.source == relationship.target:
        issues.append(
            CanonicalValidationIssue(
                "V2_RELATIONSHIP_SELF", path, "a package relationship cannot target itself"
            )
        )
    if not isinstance(relationship.href, str) or not relationship.href:
        issues.append(
            CanonicalValidationIssue(
                "V2_RELATIONSHIP_HREF", f"{path}.href", "relationship href must be non-empty"
            )
        )
    if (
        not isinstance(relationship.source_order, int)
        or isinstance(relationship.source_order, bool)
        or relationship.source_order <= 0
    ):
        issues.append(
            CanonicalValidationIssue(
                "V2_RELATIONSHIP_ORDER",
                f"{path}.source_order",
                "relationship source order must be a positive integer",
            )
        )


def _register_v1_entities(
    score: ScoreRepresentation,
    path: str,
    known: dict[tuple[EntityKind, str], str],
    issues: list[CanonicalValidationIssue],
) -> None:
    for part_index, part in enumerate(score.parts):
        part_path = f"{path}.content.score.parts[{part_index}]"
        _register_id(CanonicalId(EntityKind.PART, part.id), f"{part_path}.id", known, issues)
        for staff_index, staff in enumerate(part.staves):
            _register_id(
                CanonicalId(EntityKind.STAFF, staff.id),
                f"{part_path}.staves[{staff_index}].id",
                known,
                issues,
            )
        for voice_index, voice in enumerate(part.voices):
            _register_id(
                CanonicalId(EntityKind.VOICE, voice.id),
                f"{part_path}.voices[{voice_index}].id",
                known,
                issues,
            )
        for measure_index, measure in enumerate(part.measures):
            measure_path = f"{part_path}.measures[{measure_index}]"
            _register_id(
                CanonicalId(EntityKind.MEASURE, measure.id),
                f"{measure_path}.id",
                known,
                issues,
            )
            chord_ids: set[str] = set()
            for event_index, event in enumerate(measure.events):
                _register_id(
                    CanonicalId(EntityKind.EVENT, event.id),
                    f"{measure_path}.events[{event_index}].id",
                    known,
                    issues,
                )
                if isinstance(event, NoteEvent) and event.chord_id is not None:
                    chord_ids.add(event.chord_id)
                elif not isinstance(event, RestEvent):
                    continue
            for chord_id in sorted(chord_ids):
                _register_id(
                    CanonicalId(EntityKind.CHORD, chord_id),
                    f"{measure_path}.chord[{chord_id}]",
                    known,
                    issues,
                )
            for harmony_index, harmony in enumerate(measure.harmonies):
                _register_id(
                    CanonicalId(EntityKind.HARMONY, harmony.id),
                    f"{measure_path}.harmonies[{harmony_index}].id",
                    known,
                    issues,
                )


def _register_temporal_entities(
    score: TemporalScore,
    path: str,
    known: dict[tuple[EntityKind, str], str],
    issues: list[CanonicalValidationIssue],
) -> None:
    for part_index, part in enumerate(score.parts):
        part_path = f"{path}.content.score.parts[{part_index}]"
        _register_id(CanonicalId(EntityKind.PART, part.id), f"{part_path}.id", known, issues)
        for staff in part.staves:
            _register_id(
                CanonicalId(EntityKind.STAFF, staff.id),
                f"{part_path}.staff[{staff.source_number}]",
                known,
                issues,
            )
        for voice in part.voices:
            _register_id(
                CanonicalId(EntityKind.VOICE, voice.id),
                f"{part_path}.voice[{voice.source_id}]",
                known,
                issues,
            )
        for measure_index, measure in enumerate(part.measures):
            measure_path = f"{part_path}.measures[{measure_index}]"
            _register_id(
                CanonicalId(EntityKind.MEASURE, measure.id),
                measure_path,
                known,
                issues,
            )
            for event_index, event in enumerate(measure.events):
                _register_id(
                    CanonicalId(EntityKind.EVENT, event.id),
                    f"{measure_path}.events[{event_index}]",
                    known,
                    issues,
                )


def _validate_reference(
    reference: EntityReference,
    path: str,
    allowed: set[tuple[EntityKind, str]],
    issues: list[CanonicalValidationIssue],
) -> None:
    if not isinstance(reference, EntityReference):
        issues.append(
            CanonicalValidationIssue("V2_REFERENCE_TYPE", path, "expected EntityReference")
        )
        return
    key = (reference.target_kind, reference.target_id)
    if key not in allowed:
        issues.append(
            CanonicalValidationIssue(
                "V2_REFERENCE_BROKEN",
                path,
                "typed reference does not resolve in its required scope",
            )
        )


def _validate_source_map_entry(
    entry: SourceMapEntry,
    path: str,
    known: set[tuple[EntityKind, str]],
    sources: set[tuple[EntityKind, str]],
    issues: list[CanonicalValidationIssue],
) -> None:
    _validate_reference(entry.entity, f"{path}.entity", known, issues)
    if not entry.locations:
        issues.append(
            CanonicalValidationIssue(
                "V2_SOURCE_MAP_EMPTY",
                f"{path}.locations",
                "source-map entries require at least one known location",
            )
        )
    for index, location in enumerate(entry.locations):
        location_path = f"{path}.locations[{index}]"
        _validate_reference(
            location.source_document, f"{location_path}.source_document", sources, issues
        )
        if not location.logical_path:
            issues.append(
                CanonicalValidationIssue(
                    "V2_SOURCE_LOCATION_PATH",
                    f"{location_path}.logical_path",
                    "source location requires a logical path",
                )
            )
        for name in ("line", "column", "source_ordinal"):
            value = getattr(location, name)
            if value is not None and (not isinstance(value, int) or value <= 0):
                issues.append(
                    CanonicalValidationIssue(
                        "V2_SOURCE_LOCATION_VALUE",
                        f"{location_path}.{name}",
                        "source location values must be positive integers",
                    )
                )
