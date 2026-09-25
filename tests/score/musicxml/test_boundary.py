"""Tests for native-version MusicXML document validation."""

from __future__ import annotations

from pathlib import Path

import pytest

from teachmemusic.score.musicxml.boundary import validate_musicxml_source
from teachmemusic.score.musicxml.contracts import (
    DocumentKind,
    SourceMediaType,
)
from teachmemusic.score.musicxml.standards import resource_root


def _score_document(version: str, kind: DocumentKind) -> bytes:
    public_kind = "Partwise" if kind is DocumentKind.SCORE_PARTWISE else "Timewise"
    doctype = (
        f'<!DOCTYPE {kind.value} PUBLIC "-//Recordare//DTD MusicXML '
        f'{version} {public_kind}//EN" '
        f'"http://www.musicxml.org/dtds/{public_kind.lower()}.dtd">'
    )
    declared = "4.1" if version == "4.1-draft" else version
    version_attribute = "" if version == "1.0" else f' version="{declared}"'
    part_list = (
        '<part-list><score-part id="P1"><part-name>Music</part-name></score-part></part-list>'
    )
    if kind is DocumentKind.SCORE_PARTWISE:
        body = f'{part_list}<part id="P1"><measure number="1"/></part>'
    else:
        body = f'{part_list}<measure number="1"><part id="P1"/></measure>'
    return (
        f'<?xml version="1.0" encoding="UTF-8"?>{doctype}'
        f"<{kind.value}{version_attribute}>{body}</{kind.value}>"
    ).encode()


def _opus_document(version: str) -> bytes:
    public_version = "4.1" if version == "4.1-draft" else version
    doctype = (
        f'<!DOCTYPE opus PUBLIC "-//Recordare//DTD MusicXML {public_version} Opus//EN" '
        '"http://www.musicxml.org/dtds/opus.dtd">'
    )
    version_attribute = "" if version in {"1.0", "1.1"} else f' version="{public_version}"'
    return (
        f'<?xml version="1.0"?>{doctype}<opus{version_attribute}><title>Collection</title></opus>'
    ).encode()


@pytest.mark.parametrize(
    ("version", "expected"),
    (
        ("1.0", "1.0"),
        ("1.1", "1.1"),
        ("2.0", "2.0"),
        ("3.0", "3.0"),
        ("3.1", "3.1"),
        ("4.0", "4.0"),
        ("4.1-draft", "4.1-draft"),
    ),
)
@pytest.mark.parametrize(
    "kind",
    (DocumentKind.SCORE_PARTWISE, DocumentKind.SCORE_TIMEWISE),
)
def test_every_pinned_score_version_and_form_validates(
    version: str,
    expected: str,
    kind: DocumentKind,
) -> None:
    """TEST-MXML-VERSION-003: every native score root validates locally."""

    result = validate_musicxml_source(
        _score_document(version, kind),
        logical_name=f"minimal-{kind.value}-{version}.musicxml",
    )

    assert result.kind is kind
    assert result.standard_version == expected
    assert result.artifact.media_type is SourceMediaType.PLAIN_XML
    assert result.package is None
    assert result.evidence.validation_kind == ("dtd" if version in {"1.0", "1.1"} else "xsd")


@pytest.mark.parametrize(
    "version",
    ("1.0", "1.1", "2.0", "3.0", "3.1", "4.0", "4.1-draft"),
)
def test_every_pinned_opus_version_validates(version: str) -> None:
    """TEST-MXML-VERSION-004: opus documents use their native pinned version."""

    result = validate_musicxml_source(_opus_document(version))

    assert result.kind is DocumentKind.OPUS
    assert result.standard_version == version


def test_legacy_standard_character_entities_resolve_only_from_pinned_dtd() -> None:
    """TEST-MXML-VERSION-009: valid legacy entities use the local native DTD."""

    source = _score_document("1.1", DocumentKind.SCORE_PARTWISE).replace(
        b">Music<",
        b">Caf&eacute;<",
    )
    result = validate_musicxml_source(source)

    assert result.standard_version == "1.1"
    assert (
        result.root.findtext("part-list/score-part/part-name")
        == "Caf\N{LATIN SMALL LETTER E WITH ACUTE}"
    )


@pytest.mark.parametrize("version", ("3.0", "3.1", "4.0", "4.1-draft"))
def test_every_standard_sounds_document_validates(version: str) -> None:
    """TEST-MXML-VERSION-005: versioned sound catalogs validate natively."""

    source = (resource_root() / version / "schema" / "sounds.xml").read_bytes()
    result = validate_musicxml_source(source, logical_name=f"sounds-{version}.xml")

    assert result.kind is DocumentKind.SOUNDS
    assert result.standard_version == version
    expected_kind = "dtd" if version in {"3.0", "3.1"} else "xsd"
    assert result.evidence.validation_kind == expected_kind


@pytest.mark.parametrize(
    ("directory", "expected_version"),
    (
        ("TMM-REF-CANDIDATE-001-Hot-Cross-Buns", "4.0"),
        ("TMM-REF-CANDIDATE-002-Happy-Birthday", "2.0"),
        ("TMM-REF-CANDIDATE-003-Clair-de-Lune", "3.1"),
        ("TMM-REF-CANDIDATE-004-Moonlight-Sonata", "3.1"),
        ("TMM-REF-CANDIDATE-005-Deux-Arabesques", "3.0"),
    ),
)
def test_existing_project_mxl_fixtures_pass_the_secure_boundary(
    directory: str,
    expected_version: str,
) -> None:
    """TEST-MXML-PACKAGE-001: all established fixtures validate without mapping."""

    fixture_directory = Path("tests/fixtures/scores") / directory
    path = next(fixture_directory.glob("*.mxl"))
    result = validate_musicxml_source(path.read_bytes(), logical_name=path.name)

    assert result.kind is DocumentKind.SCORE_PARTWISE
    assert result.standard_version == expected_version
    assert result.artifact.media_type is SourceMediaType.COMPRESSED_MXL
    assert result.package is not None
    assert result.package.selected_rootfile in result.package.entries
    assert result.root.tag == "score-partwise"
