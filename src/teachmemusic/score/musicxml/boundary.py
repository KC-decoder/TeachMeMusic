"""Secure entry point for validating untrusted MusicXML and MXL bytes."""

from __future__ import annotations

import hashlib

from .contracts import (
    DocumentKind,
    IngestionLimits,
    PackageContext,
    SourceArtifact,
    SourceMediaType,
    ValidatedMusicXmlDocument,
)
from .diagnostics import DiagnosticStage, boundary_failure
from .package import resolve_mxl
from .validation import parse_and_validate_document, validate_container_native

_ZIP_SIGNATURES = (b"PK\x03\x04", b"PK\x05\x06", b"PK\x07\x08")
_XML_BINARY_PREFIXES = (
    b"\xef\xbb\xbf",
    b"\xff\xfe",
    b"\xfe\xff",
    b"\x00\x00\xfe\xff",
    b"\xff\xfe\x00\x00",
    b"\x00\x00\x00<",
    b"<\x00\x00\x00",
    b"\x00<\x00?",
    b"<\x00?\x00",
)


def validate_musicxml_source(
    source: bytes,
    *,
    logical_name: str | None = None,
    limits: IngestionLimits | None = None,
) -> ValidatedMusicXmlDocument:
    """Safely classify and natively validate MusicXML without musical mapping."""

    selected_limits = limits or IngestionLimits()
    if not isinstance(source, bytes):
        raise boundary_failure(
            "MXML_INPUT_TYPE_INVALID",
            DiagnosticStage.INPUT,
            "the source must be immutable bytes",
            logical_path=logical_name,
        )
    if not source:
        raise boundary_failure(
            "MXML_INPUT_EMPTY",
            DiagnosticStage.INPUT,
            "the source is empty",
            logical_path=logical_name,
        )
    if len(source) > selected_limits.max_input_bytes:
        raise boundary_failure(
            "MXML_INPUT_SIZE_LIMIT",
            DiagnosticStage.LIMIT,
            "the source exceeds the configured input-byte limit",
            logical_path=logical_name,
        )

    media_type = _classify_source(source, logical_name)
    artifact = SourceArtifact(
        media_type=media_type,
        sha256=hashlib.sha256(source).hexdigest(),
        byte_length=len(source),
        policy_id=selected_limits.policy_id,
        logical_name=logical_name,
    )

    if media_type is SourceMediaType.PLAIN_XML:
        tree, kind, standard_version, declared_version, evidence = parse_and_validate_document(
            source, selected_limits, logical_path=logical_name
        )
        return ValidatedMusicXmlDocument(
            tree=tree,
            kind=kind,
            standard_version=standard_version,
            declared_version=declared_version,
            artifact=artifact,
            evidence=evidence,
        )

    resolved = resolve_mxl(source, selected_limits)
    tree, kind, standard_version, declared_version, evidence = parse_and_validate_document(
        resolved.document_bytes,
        selected_limits,
        logical_path=resolved.selected_rootfile,
    )
    if kind is DocumentKind.SOUNDS:
        raise boundary_failure(
            "MXL_ROOT_KIND_UNSUPPORTED",
            DiagnosticStage.CONTAINER,
            "an MXL rootfile must be a score or opus document",
            logical_path=resolved.selected_rootfile,
        )
    container_evidence = validate_container_native(
        resolved.container_tree,
        standard_version,
        selected_limits,
    )
    package = PackageContext(
        selected_rootfile=resolved.selected_rootfile,
        selected_rootfile_sha256=resolved.selected_rootfile_sha256,
        rootfiles=resolved.rootfiles,
        entries=resolved.entries,
        container_standard_version=container_evidence.standard_version,
        resources=resolved.resources,
    )
    return ValidatedMusicXmlDocument(
        tree=tree,
        kind=kind,
        standard_version=standard_version,
        declared_version=declared_version,
        artifact=artifact,
        evidence=evidence,
        package=package,
    )


def _classify_source(source: bytes, logical_name: str | None) -> SourceMediaType:
    if source.startswith(_ZIP_SIGNATURES):
        return SourceMediaType.COMPRESSED_MXL
    if _looks_like_xml(source):
        return SourceMediaType.PLAIN_XML
    raise boundary_failure(
        "MXML_INPUT_FORMAT_UNSUPPORTED",
        DiagnosticStage.INPUT,
        "the source is neither recognizable XML nor a ZIP-based MXL package",
        logical_path=logical_name,
    )


def _looks_like_xml(source: bytes) -> bool:
    if source.startswith(_XML_BINARY_PREFIXES):
        return True
    return source.lstrip(b" \t\r\n").startswith(b"<")
