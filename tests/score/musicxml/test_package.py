"""Adversarial tests for bounded MXL archive and container handling."""

from __future__ import annotations

import io
import stat
import zipfile
from dataclasses import replace

import pytest

from teachmemusic.score.musicxml.boundary import validate_musicxml_source
from teachmemusic.score.musicxml.contracts import (
    DocumentKind,
    IngestionLimits,
    SourceMediaType,
)
from teachmemusic.score.musicxml.diagnostics import MusicXmlBoundaryError


def _score(version: str = "4.0") -> bytes:
    if version == "1.1":
        prefix = (
            '<!DOCTYPE score-partwise PUBLIC "-//Recordare//DTD MusicXML 1.1 '
            'Partwise//EN" "http://www.musicxml.org/dtds/partwise.dtd">'
        )
    else:
        prefix = ""
    return (
        f'{prefix}<score-partwise version="{version}">'
        '<part-list><score-part id="P1"><part-name>Music</part-name>'
        '</score-part></part-list><part id="P1"><measure number="1"/></part>'
        "</score-partwise>"
    ).encode()


def _container(*rootfiles: tuple[str, str | None], extra: str = "") -> bytes:
    declarations = "".join(
        f'<rootfile full-path="{path}"'
        + (f' media-type="{media_type}"' if media_type is not None else "")
        + "/>"
        for path, media_type in rootfiles
    )
    return f"<container><rootfiles>{declarations}{extra}</rootfiles></container>".encode()


def _archive(
    *,
    score: bytes | None = None,
    container: bytes | None = None,
    extra_entries: tuple[tuple[str, bytes], ...] = (),
    compression: int = zipfile.ZIP_DEFLATED,
    mimetype: bytes | None = None,
    compress_mimetype: bool = False,
) -> bytes:
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w") as archive:
        if mimetype is not None:
            archive.writestr(
                "mimetype",
                mimetype,
                compress_type=compression if compress_mimetype else zipfile.ZIP_STORED,
            )
        if container is not None:
            archive.writestr("META-INF/container.xml", container, compress_type=compression)
        if score is not None:
            archive.writestr("score.xml", score, compress_type=compression)
        for name, value in extra_entries:
            archive.writestr(name, value, compress_type=compression)
    return stream.getvalue()


def _valid_archive(**kwargs: object) -> bytes:
    options: dict[str, object] = {
        "score": _score(),
        "container": _container(("score.xml", None)),
    }
    options.update(kwargs)
    return _archive(**options)  # type: ignore[arg-type]


def _failure(source: bytes, **kwargs: object) -> MusicXmlBoundaryError:
    with pytest.raises(MusicXmlBoundaryError) as captured:
        validate_musicxml_source(source, **kwargs)  # type: ignore[arg-type]
    return captured.value


def _mark_first_entry_encrypted(source: bytes) -> bytes:
    patched = bytearray(source)
    local_offset = patched.find(b"PK\x03\x04")
    central_offset = patched.find(b"PK\x01\x02")
    assert local_offset >= 0 and central_offset >= 0
    local_flags = int.from_bytes(patched[local_offset + 6 : local_offset + 8], "little") | 0x1
    central_flags = (
        int.from_bytes(patched[central_offset + 8 : central_offset + 10], "little") | 0x1
    )
    patched[local_offset + 6 : local_offset + 8] = local_flags.to_bytes(2, "little")
    patched[central_offset + 8 : central_offset + 10] = central_flags.to_bytes(2, "little")
    return bytes(patched)


def test_valid_mxl_is_selected_by_content_not_filename() -> None:
    """TEST-MXML-PACKAGE-002: byte inspection outranks an incorrect suffix."""

    result = validate_musicxml_source(_valid_archive(), logical_name="uploaded.pdf")

    assert result.kind is DocumentKind.SCORE_PARTWISE
    assert result.artifact.media_type is SourceMediaType.COMPRESSED_MXL
    assert result.artifact.logical_name == "uploaded.pdf"
    assert result.package is not None
    assert result.package.selected_rootfile == "score.xml"
    assert result.package.container_standard_version == "4.0"


def test_optional_mimetype_entry_is_verified() -> None:
    """TEST-MXML-PACKAGE-003: a present MXL mimetype must be exact and stored."""

    accepted = _valid_archive(mimetype=b"application/vnd.recordare.musicxml")
    wrong_value = _valid_archive(mimetype=b"application/zip")
    compressed = _valid_archive(
        mimetype=b"application/vnd.recordare.musicxml",
        compress_mimetype=True,
    )

    assert validate_musicxml_source(accepted).standard_version == "4.0"
    assert _failure(wrong_value).primary.code == "MXL_MIMETYPE_INVALID"
    assert _failure(compressed).primary.code == "MXL_MIMETYPE_ENCODING_INVALID"


def test_standard_first_rootfile_selection_retains_alternates() -> None:
    """TEST-MXML-PACKAGE-004: alternate renditions are retained, not selected."""

    container = _container(
        ("score.xml", "application/vnd.recordare.musicxml+xml"),
        ("preview.pdf", "application/pdf"),
    )
    source = _valid_archive(
        container=container,
        extra_entries=(("preview.pdf", b"%PDF-placeholder"),),
    )
    result = validate_musicxml_source(source)

    assert result.package is not None
    assert result.package.selected_rootfile == "score.xml"
    assert tuple(root.full_path for root in result.package.rootfiles) == (
        "score.xml",
        "preview.pdf",
    )


@pytest.mark.parametrize(
    ("source", "code"),
    (
        (b"PK\x03\x04broken", "MXL_ARCHIVE_INVALID"),
        (_archive(score=_score()), "MXL_CONTAINER_MISSING"),
        (
            _archive(
                container=_container(("missing.xml", None)),
                score=_score(),
            ),
            "MXL_ROOTFILE_MISSING",
        ),
        (
            _valid_archive(
                container=_container(
                    ("score.xml", None),
                    ("missing.pdf", "application/pdf"),
                )
            ),
            "MXL_DECLARED_ROOTFILE_MISSING",
        ),
        (
            _valid_archive(
                container=_container(("score.xml", "application/pdf")),
            ),
            "MXL_PRIMARY_ROOTFILE_MEDIA_TYPE_INVALID",
        ),
        (
            _valid_archive(
                container=_container(("score.xml", None), extra="<unexpected/>"),
            ),
            "MXML_XSD_INVALID",
        ),
    ),
)
def test_broken_archives_and_containers_fail_explicitly(source: bytes, code: str) -> None:
    """TEST-MXML-PACKAGE-005: broken package structure never yields a document."""

    assert _failure(source).primary.code == code


@pytest.mark.parametrize(
    ("name", "code"),
    (
        ("../escape.xml", "MXL_ARCHIVE_PATH_TRAVERSAL"),
        ("/absolute.xml", "MXL_ARCHIVE_PATH_ABSOLUTE"),
        ("C:/device.xml", "MXL_ARCHIVE_PATH_ABSOLUTE"),
        ("folder\\score.xml", "MXL_ARCHIVE_PATH_INVALID"),
        ("META-INF//extra.xml", "MXL_ARCHIVE_PATH_NONCANONICAL"),
        ("aux/file.xml", "MXL_ARCHIVE_DEVICE_PATH"),
    ),
)
def test_unsafe_archive_paths_are_rejected(name: str, code: str) -> None:
    """TEST-MXML-SECURITY-009: archive paths cannot escape or target devices."""

    source = _valid_archive(extra_entries=((name, b"content"),))

    assert _failure(source).primary.code == code


def test_duplicate_and_case_equivalent_paths_are_rejected() -> None:
    """TEST-MXML-SECURITY-010: ambiguous archive path identities fail closed."""

    with pytest.warns(UserWarning, match="Duplicate name"):
        duplicate = _valid_archive(extra_entries=(("score.xml", b"duplicate"),))
    collision = _valid_archive(extra_entries=(("SCORE.XML", b"collision"),))

    assert _failure(duplicate).primary.code == "MXL_ARCHIVE_DUPLICATE_PATH"
    assert _failure(collision).primary.code == "MXL_ARCHIVE_CASE_COLLISION"


def test_symlink_and_non_deflate_entries_are_rejected() -> None:
    """TEST-MXML-SECURITY-011: special files and unsupported codecs are forbidden."""

    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w") as archive:
        link = zipfile.ZipInfo("linked-score.xml")
        link.external_attr = (stat.S_IFLNK | 0o777) << 16
        archive.writestr(link, b"score.xml")
    symlink_error = _failure(stream.getvalue())

    bzip = _valid_archive(compression=zipfile.ZIP_BZIP2)
    compression_error = _failure(bzip)

    assert symlink_error.primary.code == "MXL_ARCHIVE_SPECIAL_FILE"
    assert compression_error.primary.code == "MXL_ARCHIVE_COMPRESSION_UNSUPPORTED"


def test_archive_entry_count_size_and_ratio_are_bounded() -> None:
    """TEST-MXML-SECURITY-012: ZIP count, expanded size, and ratio have limits."""

    base = IngestionLimits()
    count_error = _failure(
        _valid_archive(extra_entries=(("extra.txt", b"x"),)),
        limits=replace(base, max_archive_entries=2),
    )
    size_error = _failure(
        _valid_archive(),
        limits=replace(base, max_archive_entry_bytes=100),
    )
    ratio_error = _failure(
        _valid_archive(extra_entries=(("zeros.bin", b"0" * 10_000),)),
        limits=replace(base, max_compression_ratio=2),
    )
    total_error = _failure(
        _valid_archive(),
        limits=replace(base, max_archive_total_bytes=200),
    )

    assert count_error.primary.code == "MXL_ARCHIVE_ENTRY_LIMIT"
    assert size_error.primary.code == "MXL_ARCHIVE_ENTRY_SIZE_LIMIT"
    assert ratio_error.primary.code == "MXL_ARCHIVE_COMPRESSION_RATIO_LIMIT"
    assert total_error.primary.code == "MXL_ARCHIVE_TOTAL_SIZE_LIMIT"


def test_encrypted_entries_are_rejected_before_reading() -> None:
    """TEST-MXML-SECURITY-013: encrypted ZIP entries never reach extraction."""

    source = _mark_first_entry_encrypted(_valid_archive())

    assert _failure(source).primary.code == "MXL_ARCHIVE_ENCRYPTED"


def test_pre_mxl_musicxml_version_is_rejected_inside_archive() -> None:
    """TEST-MXML-PACKAGE-006: compressed packaging begins with MusicXML 2.0."""

    source = _valid_archive(score=_score("1.1"))

    assert _failure(source).primary.code == "MXL_UNAVAILABLE_FOR_VERSION"


def test_sounds_document_cannot_be_an_mxl_rootfile() -> None:
    """TEST-MXML-PACKAGE-007: MXL roots are scores or opus documents."""

    sounds = (
        b'<!DOCTYPE sounds PUBLIC "-//Recordare//DTD MusicXML 4.0 Sounds//EN" '
        b'"http://www.musicxml.org/dtds/sounds.dtd"><sounds><sound id="piano"/></sounds>'
    )
    source = _valid_archive(score=sounds)

    assert _failure(source).primary.code == "MXL_ROOT_KIND_UNSUPPORTED"
