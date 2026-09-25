"""Task 7J-R4 complete package and public API evidence."""

from __future__ import annotations

import io
import zipfile
from dataclasses import replace
from pathlib import Path

import pytest

from teachmemusic.score import (
    CanonicalMusicPackage,
    CanonicalPackageError,
    CanonicalScoreContent,
    MediaDocument,
    OpusDocument,
    PackageRelationship,
    PackageRelationshipKind,
    ScoreDocument,
    SoundsDocument,
    package_from_json,
    package_to_json,
    parse_musicxml_package,
    validate_package,
)
from teachmemusic.score.musicxml.standards import resource_root
from teachmemusic.score.v2.identity import EntityKind, EntityReference


def _score(*, part_link: str | None = None, title: str = "Package score") -> bytes:
    linked = (
        f'<part-link xmlns:xlink="http://www.w3.org/1999/xlink" xlink:href="{part_link}"/>'
        if part_link is not None
        else ""
    )
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<score-partwise version="4.0"><work><work-title>'
        f'{title}</work-title></work><part-list><score-part id="P1">{linked}'
        "<part-name>Piano</part-name></score-part></part-list>"
        '<part id="P1"><measure number="1"><attributes><divisions>1</divisions>'
        "<time><beats>4</beats><beat-type>4</beat-type></time>"
        "<clef><sign>G</sign><line>2</line></clef></attributes>"
        "<note><pitch><step>C</step><octave>4</octave></pitch>"
        "<duration>4</duration><type>whole</type></note></measure></part>"
        "</score-partwise>"
    ).encode()


def _opus(href: str) -> bytes:
    return (
        '<?xml version="1.0"?>'
        '<!DOCTYPE opus PUBLIC "-//Recordare//DTD MusicXML 4.0 Opus//EN" '
        '"http://www.musicxml.org/dtds/opus.dtd">'
        '<opus version="4.0" xmlns:xlink="http://www.w3.org/1999/xlink">'
        f'<title>Collection</title><score xlink:href="{href}" new-page="yes"/>'
        "</opus>"
    ).encode()


def _container(*rootfiles: tuple[str, str | None]) -> bytes:
    values = "".join(
        f'<rootfile full-path="{path}"'
        + (f' media-type="{media_type}"' if media_type is not None else "")
        + "/>"
        for path, media_type in rootfiles
    )
    return f"<container><rootfiles>{values}</rootfiles></container>".encode()


def _mxl(
    *,
    rootfiles: tuple[tuple[str, str | None], ...],
    entries: tuple[tuple[str, bytes], ...],
) -> bytes:
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w") as archive:
        archive.writestr(
            "mimetype",
            b"application/vnd.recordare.musicxml",
            compress_type=zipfile.ZIP_STORED,
        )
        archive.writestr("META-INF/container.xml", _container(*rootfiles))
        for path, data in entries:
            archive.writestr(path, data)
    return stream.getvalue()


def test_public_plain_score_returns_complete_canonical_content() -> None:
    """TEST-MXML-PUBLIC-001: the public edge returns validated complete content."""

    package = parse_musicxml_package(_score(), logical_name="score.musicxml")

    assert isinstance(package, CanonicalMusicPackage)
    assert len(package.documents) == 1
    score = package.documents[0]
    assert isinstance(score, ScoreDocument)
    assert isinstance(score.content, CanonicalScoreContent)
    assert score.content.completeness == "complete"
    assert validate_package(package) == ()
    assert package_from_json(package_to_json(package)) == package


def test_mxl_integrates_alternate_media_and_linked_score() -> None:
    """TEST-MXML-PUBLIC-002: package-local roots, media, and linked parts resolve."""

    source = _mxl(
        rootfiles=(
            ("scores/main.musicxml", "application/vnd.recordare.musicxml+xml"),
            ("preview.pdf", "application/pdf"),
        ),
        entries=(
            ("scores/main.musicxml", _score(part_link="../parts/piano.musicxml")),
            ("parts/piano.musicxml", _score(title="Linked piano part")),
            ("preview.pdf", b"%PDF-1.7\nfixture\n"),
        ),
    )
    package = parse_musicxml_package(source, logical_name="collection.mxl")

    assert [type(item) for item in package.documents] == [
        ScoreDocument,
        MediaDocument,
        ScoreDocument,
    ]
    assert [item.target_kind for item in package.root_documents] == [
        EntityKind.SCORE,
        EntityKind.MEDIA,
    ]
    assert [item.kind for item in package.relationships] == [
        PackageRelationshipKind.ALTERNATE_ROOTFILE,
        PackageRelationshipKind.LINKED_PART,
    ]
    assert package.relationships[1].href == "../parts/piano.musicxml"
    assert len(package.provenance.sources) == 4
    assert validate_package(package) == ()
    assert package_from_json(package_to_json(package)) == package


def test_mxl_opus_resolves_packaged_score_member() -> None:
    """TEST-MXML-PUBLIC-003: opus membership becomes a typed package reference."""

    source = _mxl(
        rootfiles=(("collection.xml", "application/vnd.recordare.musicxml+xml"),),
        entries=(
            ("collection.xml", _opus("scores/one.musicxml")),
            ("scores/one.musicxml", _score(title="Opus member")),
        ),
    )
    package = parse_musicxml_package(source)

    opus = package.documents[0]
    assert isinstance(opus, OpusDocument)
    assert opus.content is not None
    assert opus.content.title == "Collection"
    assert len(opus.members) == 1
    assert opus.members[0].target_kind is EntityKind.SCORE
    assert package.relationships[0].kind is PackageRelationshipKind.OPUS_MEMBER
    assert validate_package(package) == ()
    assert package_from_json(package_to_json(package)) == package


def test_public_sounds_document_retains_complete_catalog() -> None:
    """TEST-MXML-PUBLIC-004: auxiliary roots use the same package/API boundary."""

    path = resource_root() / "4.0" / "schema" / "sounds.xml"
    package = parse_musicxml_package(path.read_bytes(), logical_name="sounds.xml")

    sounds = package.documents[0]
    assert isinstance(sounds, SoundsDocument)
    assert sounds.content is not None
    assert len(sounds.content.entries) == 894
    assert package_from_json(package_to_json(package)) == package


def test_wrong_kind_package_link_fails_closed() -> None:
    """TEST-MXML-PUBLIC-005: a packaged linked part cannot resolve to media."""

    source = _mxl(
        rootfiles=(("main.musicxml", "application/vnd.recordare.musicxml+xml"),),
        entries=(
            ("main.musicxml", _score(part_link="parts/not-a-score.xml")),
            ("parts/not-a-score.xml", b"not MusicXML"),
        ),
    )

    with pytest.raises(CanonicalPackageError) as captured:
        parse_musicxml_package(source)
    assert captured.value.code == "MXML_PACKAGE_RELATIONSHIP_KIND"
    assert captured.value.logical_path == "parts/not-a-score.xml"


def test_complete_content_and_relationship_mutations_are_rejected() -> None:
    """TEST-MXML-PUBLIC-006: public completeness and graph invariants fail closed."""

    package = parse_musicxml_package(_score())
    score = package.documents[0]
    assert isinstance(score, ScoreDocument)
    assert isinstance(score.content, CanonicalScoreContent)
    incomplete = replace(
        package,
        documents=(replace(score, content=replace(score.content, completeness="partial")),),
    )
    assert "V2_SCORE_COMPLETENESS" in {issue.code for issue in validate_package(incomplete)}

    dangling = replace(
        package,
        relationships=(
            PackageRelationship(
                kind=PackageRelationshipKind.RESOURCE_LINK,
                source=EntityReference.to(score.id),
                target=EntityReference(EntityKind.MEDIA, "media:missing"),
                href="missing.png",
                source_order=1,
            ),
        ),
    )
    assert "V2_REFERENCE_BROKEN" in {issue.code for issue in validate_package(dangling)}

    wrong_kind = replace(
        package,
        relationships=(
            PackageRelationship(
                kind=PackageRelationshipKind.MEDIA_RESOURCE,
                source=EntityReference.to(score.id),
                target=EntityReference.to(score.id),
                href="score.musicxml",
                source_order=1,
            ),
        ),
    )
    assert "V2_RELATIONSHIP_TARGET_KIND" in {issue.code for issue in validate_package(wrong_kind)}


@pytest.mark.parametrize(
    "directory",
    (
        "TMM-REF-CANDIDATE-001-Hot-Cross-Buns",
        "TMM-REF-CANDIDATE-002-Happy-Birthday",
        "TMM-REF-CANDIDATE-003-Clair-de-Lune",
        "TMM-REF-CANDIDATE-004-Moonlight-Sonata",
        "TMM-REF-CANDIDATE-005-Deux-Arabesques",
    ),
)
def test_all_governed_fixtures_use_complete_public_package(directory: str) -> None:
    """TEST-MXML-PUBLIC-007: every governed score clears the complete public edge."""

    path = next((Path("tests/fixtures/scores") / directory).glob("*.mxl"))
    package = parse_musicxml_package(path.read_bytes(), logical_name=path.name)
    score = package.documents[0]

    assert isinstance(score, ScoreDocument)
    assert isinstance(score.content, CanonicalScoreContent)
    assert validate_package(package) == ()
