"""Hardened native-version validation for private MusicXML source trees."""

from __future__ import annotations

import re
from functools import cache
from typing import Any, cast

from lxml import etree

from .contracts import (
    DocumentKind,
    IngestionLimits,
    ValidationEvidence,
)
from .diagnostics import (
    DiagnosticStage,
    IngestionDiagnostic,
    MusicXmlBoundaryError,
    boundary_failure,
)
from .standards import ALLOWED_REMOTE_RESOURCES, LocalOnlyResolver, resource_root

SUPPORTED_STANDARD_VERSIONS = (
    "1.0",
    "1.1",
    "2.0",
    "3.0",
    "3.1",
    "4.0",
    "4.1-draft",
)
_DOCUMENT_KINDS = {kind.value: kind for kind in DocumentKind}
_DTD_FILENAMES = {
    DocumentKind.SCORE_PARTWISE: "partwise.dtd",
    DocumentKind.SCORE_TIMEWISE: "timewise.dtd",
    DocumentKind.OPUS: "opus.dtd",
    DocumentKind.SOUNDS: "sounds.dtd",
}
_XSD_FILENAMES = {
    DocumentKind.SCORE_PARTWISE: "musicxml.xsd",
    DocumentKind.SCORE_TIMEWISE: "musicxml.xsd",
    DocumentKind.OPUS: "opus.xsd",
    DocumentKind.SOUNDS: "sounds.xsd",
}
_PUBLIC_ID_PATTERN = re.compile(
    r"MusicXML\s+(?P<version>\d+\.\d+)\s+"
    r"(?P<kind>Partwise|Timewise|Opus|Sounds)",
    re.IGNORECASE,
)
_PUBLIC_KIND = {
    "partwise": DocumentKind.SCORE_PARTWISE,
    "timewise": DocumentKind.SCORE_TIMEWISE,
    "opus": DocumentKind.OPUS,
    "sounds": DocumentKind.SOUNDS,
}


def parse_and_validate_document(
    data: bytes,
    limits: IngestionLimits,
    *,
    logical_path: str | None = None,
) -> tuple[etree._ElementTree, DocumentKind, str, str | None, ValidationEvidence]:
    """Parse untrusted XML and validate it against its exact native standard."""

    initial_tree = _parse_xml(data, limits, logical_path=logical_path)
    root = initial_tree.getroot()
    kind = _detect_document_kind(root, logical_path)
    document_info = initial_tree.docinfo
    _reject_internal_entities(document_info, logical_path)
    public_version, public_kind = _doctype_identity(document_info.public_id)
    if public_kind is not None and public_kind is not kind:
        raise boundary_failure(
            "MXML_DOCTYPE_KIND_CONFLICT",
            DiagnosticStage.VERSION,
            "the document type declaration does not match the XML root",
            logical_path=logical_path,
        )
    standard_version, declared_version = _detect_standard_version(
        root,
        kind,
        public_version,
        logical_path,
    )
    system_url = _document_system_url(document_info)
    _check_external_identifier(system_url, kind, logical_path)

    tree = initial_tree
    if system_url and _contains_entity_reference(initial_tree):
        tree = _parse_xml(
            data,
            limits,
            logical_path=logical_path,
            bundle_version=standard_version,
            load_standard_dtd=True,
        )
        _reject_internal_entities(tree.docinfo, logical_path)
    _enforce_xml_limits(tree, limits, logical_path=logical_path)
    evidence = _validate_native(tree, kind, standard_version, limits, logical_path)
    return tree, kind, standard_version, declared_version, evidence


def parse_container_document(
    data: bytes,
    limits: IngestionLimits,
    *,
    logical_path: str = "META-INF/container.xml",
) -> etree._ElementTree:
    """Safely parse an MXL container before the root score version is known."""

    tree = _parse_xml(data, limits, logical_path=logical_path)
    _reject_internal_entities(tree.docinfo, logical_path)
    root = tree.getroot()
    qname = etree.QName(root)
    if qname.namespace is not None or qname.localname != "container":
        raise boundary_failure(
            "MXL_CONTAINER_ROOT_INVALID",
            DiagnosticStage.CONTAINER,
            "META-INF/container.xml must have an unnamespaced container root",
            logical_path=logical_path,
            line=_source_line(root),
        )
    system_url = _document_system_url(tree.docinfo)
    if system_url and ALLOWED_REMOTE_RESOURCES.get(system_url) != "container.dtd":
        raise boundary_failure(
            "MXML_EXTERNAL_RESOURCE_REJECTED",
            DiagnosticStage.CONTAINER,
            "the container references an unapproved external resource",
            logical_path=logical_path,
        )
    _enforce_xml_limits(tree, limits, logical_path=logical_path)
    _strip_container_indentation(tree)
    return tree


def validate_container_native(
    tree: etree._ElementTree,
    standard_version: str,
    limits: IngestionLimits,
) -> ValidationEvidence:
    """Validate a parsed MXL container using the root document's native era."""

    logical_path = "META-INF/container.xml"
    if standard_version in {"1.0", "1.1"}:
        raise boundary_failure(
            "MXL_UNAVAILABLE_FOR_VERSION",
            DiagnosticStage.CONTAINER,
            "compressed MXL packaging was introduced in MusicXML 2.0",
            logical_path=logical_path,
        )
    if standard_version in {"2.0", "3.0", "3.1"}:
        return _validate_dtd(
            tree,
            standard_version,
            "container.dtd",
            limits,
            logical_path,
        )
    return _validate_xsd(
        tree,
        standard_version,
        "container.xsd",
        limits,
        logical_path,
    )


def _parse_xml(
    data: bytes,
    limits: IngestionLimits,
    *,
    logical_path: str | None,
    bundle_version: str | None = None,
    load_standard_dtd: bool = False,
) -> etree._ElementTree:
    parser = etree.XMLParser(
        load_dtd=load_standard_dtd,
        no_network=True,
        recover=False,
        resolve_entities=load_standard_dtd,
        huge_tree=False,
        remove_blank_text=False,
        remove_comments=False,
        remove_pis=False,
        strip_cdata=False,
    )
    if bundle_version is not None:
        parser.resolvers.add(LocalOnlyResolver(resource_root() / bundle_version))
    try:
        root = etree.fromstring(data, parser=parser)
    except (etree.XMLSyntaxError, OSError) as error:
        raise _xml_parse_error(error, limits, logical_path) from error
    return root.getroottree()


def _xml_parse_error(
    error: etree.XMLSyntaxError | OSError,
    limits: IngestionLimits,
    logical_path: str | None,
) -> MusicXmlBoundaryError:
    if isinstance(error, etree.XMLSyntaxError):
        entries = tuple(cast(Any, error.error_log))[: limits.max_validation_diagnostics]
        if entries:
            diagnostics = tuple(
                IngestionDiagnostic(
                    code="MXML_XML_MALFORMED",
                    stage=DiagnosticStage.XML,
                    message=_stable_error_message(entry.message),
                    logical_path=logical_path,
                    line=entry.line or None,
                    column=entry.column or None,
                )
                for entry in entries
            )
            return MusicXmlBoundaryError(*diagnostics)
    return boundary_failure(
        "MXML_XML_MALFORMED",
        DiagnosticStage.XML,
        "the XML document is malformed or references a rejected resource",
        logical_path=logical_path,
    )


def _detect_document_kind(
    root: etree._Element,
    logical_path: str | None,
) -> DocumentKind:
    qname = etree.QName(root)
    if qname.namespace is not None:
        raise boundary_failure(
            "MXML_NAMESPACE_UNSUPPORTED",
            DiagnosticStage.VERSION,
            "MusicXML document roots must use the standard empty namespace",
            logical_path=logical_path,
            line=_source_line(root),
        )
    kind = _DOCUMENT_KINDS.get(qname.localname)
    if kind is None:
        raise boundary_failure(
            "MXML_DOCUMENT_KIND_UNSUPPORTED",
            DiagnosticStage.VERSION,
            "the XML root is not a supported MusicXML document kind",
            logical_path=logical_path,
            line=_source_line(root),
        )
    return kind


def _detect_standard_version(
    root: etree._Element,
    kind: DocumentKind,
    public_version: str | None,
    logical_path: str | None,
) -> tuple[str, str | None]:
    raw_version = root.get("version")
    declared_version = _normalize_version(raw_version) if raw_version is not None else None
    if raw_version is not None and declared_version is None:
        raise boundary_failure(
            "MXML_VERSION_INVALID",
            DiagnosticStage.VERSION,
            "the MusicXML version attribute is empty or malformed",
            logical_path=logical_path,
            line=_source_line(root),
        )
    if declared_version and public_version and declared_version != public_version:
        raise boundary_failure(
            "MXML_VERSION_CONFLICT",
            DiagnosticStage.VERSION,
            "the version attribute conflicts with the document type declaration",
            logical_path=logical_path,
            line=_source_line(root),
        )

    selected = declared_version or public_version
    if kind is DocumentKind.SOUNDS and selected is None:
        raise boundary_failure(
            "MXML_VERSION_AMBIGUOUS",
            DiagnosticStage.VERSION,
            "a sounds document requires a recognized versioned document type declaration",
            logical_path=logical_path,
            line=_source_line(root),
        )
    selected = selected or "1.0"
    standard_version = "4.1-draft" if selected == "4.1" else selected
    if standard_version not in SUPPORTED_STANDARD_VERSIONS:
        raise boundary_failure(
            "MXML_VERSION_UNSUPPORTED",
            DiagnosticStage.VERSION,
            "the declared MusicXML version is not in the pinned baseline",
            logical_path=logical_path,
            line=_source_line(root),
        )
    if kind is DocumentKind.SOUNDS and standard_version not in {
        "3.0",
        "3.1",
        "4.0",
        "4.1-draft",
    }:
        raise boundary_failure(
            "MXML_DOCUMENT_VERSION_UNSUPPORTED",
            DiagnosticStage.VERSION,
            "sounds documents begin with MusicXML 3.0",
            logical_path=logical_path,
            line=_source_line(root),
        )
    return standard_version, declared_version


def _normalize_version(value: str) -> str | None:
    normalized = " ".join(value.split())
    if not normalized or " " in normalized:
        return None
    return normalized


def _doctype_identity(public_id: str | None) -> tuple[str | None, DocumentKind | None]:
    if not public_id:
        return None, None
    match = _PUBLIC_ID_PATTERN.search(public_id)
    if match is None:
        return None, None
    return match.group("version"), _PUBLIC_KIND[match.group("kind").lower()]


def _check_external_identifier(
    system_url: str | None,
    kind: DocumentKind,
    logical_path: str | None,
) -> None:
    if not system_url:
        return
    expected_filename = _DTD_FILENAMES[kind]
    if ALLOWED_REMOTE_RESOURCES.get(system_url) != expected_filename:
        raise boundary_failure(
            "MXML_EXTERNAL_RESOURCE_REJECTED",
            DiagnosticStage.XML,
            "the document references an unapproved external resource",
            logical_path=logical_path,
        )


def _reject_internal_entities(
    document_info: etree.DocInfo,
    logical_path: str | None,
) -> None:
    internal_dtd = document_info.internalDTD
    if internal_dtd is not None and tuple(cast(Any, internal_dtd).iterentities()):
        raise boundary_failure(
            "MXML_INTERNAL_ENTITY_REJECTED",
            DiagnosticStage.XML,
            "internal entity declarations are not permitted",
            logical_path=logical_path,
        )


def _contains_entity_reference(tree: etree._ElementTree) -> bool:
    return any(isinstance(node, etree._Entity) for node in tree.iter())


def _enforce_xml_limits(
    tree: etree._ElementTree,
    limits: IngestionLimits,
    *,
    logical_path: str | None,
) -> None:
    node_count = 0
    stack: list[tuple[etree._Element, int]] = [(tree.getroot(), 1)]
    while stack:
        node, depth = stack.pop()
        node_count += 1
        if node_count > limits.max_xml_nodes:
            raise boundary_failure(
                "MXML_XML_NODE_LIMIT",
                DiagnosticStage.LIMIT,
                "the XML node count exceeds the configured limit",
                logical_path=logical_path,
                line=_source_line(node),
            )
        if depth > limits.max_xml_depth:
            raise boundary_failure(
                "MXML_XML_DEPTH_LIMIT",
                DiagnosticStage.LIMIT,
                "the XML nesting depth exceeds the configured limit",
                logical_path=logical_path,
                line=_source_line(node),
            )
        if len(node.attrib) > limits.max_xml_attributes_per_element:
            raise boundary_failure(
                "MXML_XML_ATTRIBUTE_LIMIT",
                DiagnosticStage.LIMIT,
                "an XML element exceeds the configured attribute limit",
                logical_path=logical_path,
                line=_source_line(node),
            )
        scalar_values = (node.text, node.tail, *node.attrib.values())
        if any(
            value is not None and len(value.encode("utf-8")) > limits.max_xml_scalar_bytes
            for value in scalar_values
        ):
            raise boundary_failure(
                "MXML_XML_SCALAR_LIMIT",
                DiagnosticStage.LIMIT,
                "an XML text or attribute value exceeds the configured limit",
                logical_path=logical_path,
                line=_source_line(node),
            )
        stack.extend((child, depth + 1) for child in reversed(node))


def _strip_container_indentation(tree: etree._ElementTree) -> None:
    """Remove non-information indentation before strict container validation."""

    for element in tree.iter():
        if element.text is not None and not element.text.strip():
            element.text = None
        if element.tail is not None and not element.tail.strip():
            element.tail = None


def _validate_native(
    tree: etree._ElementTree,
    kind: DocumentKind,
    standard_version: str,
    limits: IngestionLimits,
    logical_path: str | None,
) -> ValidationEvidence:
    if standard_version in {"1.0", "1.1"}:
        return _validate_dtd(
            tree,
            standard_version,
            _DTD_FILENAMES[kind],
            limits,
            logical_path,
        )
    if kind is DocumentKind.SOUNDS and standard_version in {"3.0", "3.1"}:
        return _validate_dtd(
            tree,
            standard_version,
            _DTD_FILENAMES[kind],
            limits,
            logical_path,
        )
    return _validate_xsd(
        tree,
        standard_version,
        _XSD_FILENAMES[kind],
        limits,
        logical_path,
    )


def _validate_xsd(
    tree: etree._ElementTree,
    standard_version: str,
    filename: str,
    limits: IngestionLimits,
    logical_path: str | None,
) -> ValidationEvidence:
    schema = _compiled_xsd(standard_version, filename)
    if not schema.validate(tree):
        raise _validation_error(
            "MXML_XSD_INVALID",
            schema.error_log,
            limits,
            logical_path,
        )
    return ValidationEvidence(
        standard_version=standard_version,
        validation_kind="xsd",
        resource_path=f"{standard_version}/schema/{filename}",
    )


def _validate_dtd(
    tree: etree._ElementTree,
    standard_version: str,
    filename: str,
    limits: IngestionLimits,
    logical_path: str | None,
) -> ValidationEvidence:
    dtd = _compiled_dtd(standard_version, filename)
    if not dtd.validate(tree):
        raise _validation_error(
            "MXML_DTD_INVALID",
            dtd.error_log,
            limits,
            logical_path,
        )
    return ValidationEvidence(
        standard_version=standard_version,
        validation_kind="dtd",
        resource_path=f"{standard_version}/schema/{filename}",
    )


@cache
def _compiled_xsd(standard_version: str, filename: str) -> etree.XMLSchema:
    bundle = resource_root() / standard_version
    path = bundle / "schema" / filename
    parser = etree.XMLParser(
        load_dtd=False,
        no_network=True,
        recover=False,
        resolve_entities=False,
        huge_tree=False,
    )
    parser.resolvers.add(LocalOnlyResolver(bundle))
    document = etree.parse(str(path), parser)
    return etree.XMLSchema(document)


@cache
def _compiled_dtd(standard_version: str, filename: str) -> etree.DTD:
    path = resource_root() / standard_version / "schema" / filename
    return etree.DTD(str(path))


def _validation_error(
    code: str,
    error_log: etree._ListErrorLog,
    limits: IngestionLimits,
    logical_path: str | None,
) -> MusicXmlBoundaryError:
    entries = tuple(cast(Any, error_log))[: limits.max_validation_diagnostics]
    if not entries:
        return boundary_failure(
            code,
            DiagnosticStage.VALIDATION,
            "the document does not satisfy its pinned native standard",
            logical_path=logical_path,
        )
    return MusicXmlBoundaryError(
        *(
            IngestionDiagnostic(
                code=code,
                stage=DiagnosticStage.VALIDATION,
                message=_stable_error_message(entry.message),
                logical_path=logical_path,
                line=entry.line or None,
                column=entry.column or None,
            )
            for entry in entries
        )
    )


def _stable_error_message(message: str) -> str:
    return " ".join(message.split())


def _document_system_url(document_info: etree.DocInfo) -> str | None:
    value = getattr(document_info, "system_url", None)
    return value if isinstance(value, str) and value else None


def _source_line(element: etree._Element) -> int | None:
    value = element.sourceline
    return value if isinstance(value, int) and value > 0 else None
