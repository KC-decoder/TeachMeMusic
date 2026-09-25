"""Negative and resource-limit tests for the XML validation boundary."""

from __future__ import annotations

from dataclasses import replace
from typing import Any, cast

import pytest

from teachmemusic.score.musicxml.boundary import validate_musicxml_source
from teachmemusic.score.musicxml.contracts import IngestionLimits
from teachmemusic.score.musicxml.diagnostics import (
    DiagnosticStage,
    MusicXmlBoundaryError,
)


def _valid_score(*, version: str = "4.0", extra_root_attribute: str = "") -> bytes:
    return (
        f'<score-partwise version="{version}"{extra_root_attribute}>'
        '<part-list><score-part id="P1"><part-name>Music</part-name>'
        '</score-part></part-list><part id="P1"><measure number="1"/></part>'
        "</score-partwise>"
    ).encode()


def _failure(source: bytes, **kwargs: object) -> MusicXmlBoundaryError:
    with pytest.raises(MusicXmlBoundaryError) as captured:
        validate_musicxml_source(source, **kwargs)  # type: ignore[arg-type]
    return captured.value


@pytest.mark.parametrize(
    ("source", "code"),
    (
        (b"", "MXML_INPUT_EMPTY"),
        (b"not music or XML", "MXML_INPUT_FORMAT_UNSUPPORTED"),
        (b"<score-partwise>", "MXML_XML_MALFORMED"),
        (b"<document/>", "MXML_DOCUMENT_KIND_UNSUPPORTED"),
        (
            b'<score-partwise xmlns="urn:example" version="4.0"/>',
            "MXML_NAMESPACE_UNSUPPORTED",
        ),
        (_valid_score(version="9.0"), "MXML_VERSION_UNSUPPORTED"),
        (b'<sounds><sound id="piano"/></sounds>', "MXML_VERSION_AMBIGUOUS"),
    ),
)
def test_invalid_input_fails_with_stable_primary_code(source: bytes, code: str) -> None:
    """TEST-MXML-SECURITY-003: unsupported and malformed inputs fail explicitly."""

    error = _failure(source, logical_name="upload.bin")

    assert error.primary.code == code
    assert error.primary.logical_path == "upload.bin"


def test_input_requires_immutable_bounded_bytes() -> None:
    """TEST-MXML-SECURITY-004: type and upload-size limits are applied first."""

    wrong_type = cast(Any, bytearray(b"<score-partwise/>"))
    type_error = _failure(wrong_type)
    size_error = _failure(_valid_score(), limits=IngestionLimits(max_input_bytes=20))

    assert type_error.primary.code == "MXML_INPUT_TYPE_INVALID"
    assert size_error.primary.code == "MXML_INPUT_SIZE_LIMIT"
    assert size_error.primary.stage is DiagnosticStage.LIMIT


def test_schema_invalid_musicxml_is_not_returned_as_a_document() -> None:
    """TEST-MXML-VERSION-006: root recognition cannot bypass native validation."""

    error = _failure(b'<score-partwise version="4.0"><part-list/></score-partwise>')

    assert error.primary.code == "MXML_XSD_INVALID"
    assert error.primary.stage is DiagnosticStage.VALIDATION


def test_version_and_doctype_disagreement_is_rejected() -> None:
    """TEST-MXML-VERSION-007: conflicting source version evidence fails closed."""

    source = (
        b'<!DOCTYPE score-partwise PUBLIC "-//Recordare//DTD MusicXML 3.1 Partwise//EN" '
        b'"http://www.musicxml.org/dtds/partwise.dtd">' + _valid_score(version="4.0")
    )

    assert _failure(source).primary.code == "MXML_VERSION_CONFLICT"


def test_doctype_kind_disagreement_is_rejected() -> None:
    """TEST-MXML-VERSION-008: a misleading standard identifier is rejected."""

    source = (
        b'<!DOCTYPE score-partwise PUBLIC "-//Recordare//DTD MusicXML 4.0 Timewise//EN" '
        b'"http://www.musicxml.org/dtds/partwise.dtd">' + _valid_score(version="4.0")
    )

    assert _failure(source).primary.code == "MXML_DOCTYPE_KIND_CONFLICT"


def test_unknown_external_resource_is_rejected_without_network_access() -> None:
    """TEST-MXML-SECURITY-005: document-controlled external URLs are forbidden."""

    source = (
        b'<!DOCTYPE score-partwise SYSTEM "https://attacker.invalid/evil.dtd">' + _valid_score()
    )

    assert _failure(source).primary.code == "MXML_EXTERNAL_RESOURCE_REJECTED"


def test_internal_entity_declarations_are_rejected() -> None:
    """TEST-MXML-SECURITY-006: internal entity expansion is never accepted."""

    source = (
        b'<!DOCTYPE score-partwise [<!ENTITY payload "expanded">]>'
        b'<score-partwise version="4.0"><part-list><score-part id="P1">'
        b"<part-name>&payload;</part-name></score-part></part-list>"
        b'<part id="P1"><measure number="1"/></part></score-partwise>'
    )

    assert _failure(source).primary.code == "MXML_INTERNAL_ENTITY_REJECTED"


@pytest.mark.parametrize(
    ("limits", "source", "code"),
    (
        (
            replace(IngestionLimits(), max_xml_nodes=1),
            _valid_score(),
            "MXML_XML_NODE_LIMIT",
        ),
        (
            replace(IngestionLimits(), max_xml_depth=1),
            _valid_score(),
            "MXML_XML_DEPTH_LIMIT",
        ),
        (
            replace(IngestionLimits(), max_xml_attributes_per_element=1),
            _valid_score(extra_root_attribute=' id="score"'),
            "MXML_XML_ATTRIBUTE_LIMIT",
        ),
        (
            replace(IngestionLimits(), max_xml_scalar_bytes=4),
            _valid_score(),
            "MXML_XML_SCALAR_LIMIT",
        ),
    ),
)
def test_application_xml_limits_precede_schema_mapping(
    limits: IngestionLimits,
    source: bytes,
    code: str,
) -> None:
    """TEST-MXML-SECURITY-007: depth, nodes, attributes, and scalars are bounded."""

    error = _failure(source, limits=limits)

    assert error.primary.code == code
    assert error.primary.stage is DiagnosticStage.LIMIT


def test_failure_diagnostics_are_deterministic() -> None:
    """TEST-MXML-SECURITY-008: identical invalid input gives identical diagnostics."""

    source = b'<score-partwise version="4.0"><invalid/></score-partwise>'

    assert _failure(source).diagnostics == _failure(source).diagnostics


def test_common_utf16_xml_is_classified_by_content() -> None:
    """TEST-MXML-INPUT-001: XML encoding signatures work independently of suffixes."""

    source = (
        _valid_score()
        .decode()
        .replace(
            '<score-partwise version="4.0">',
            '<?xml version="1.0" encoding="UTF-16"?><score-partwise version="4.0">',
        )
    )
    result = validate_musicxml_source(source.encode("utf-16"), logical_name="score.data")

    assert result.standard_version == "4.0"
    assert result.artifact.logical_name == "score.data"
