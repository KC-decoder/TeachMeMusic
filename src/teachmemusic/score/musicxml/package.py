"""Bounded, traversal-safe handling of compressed MusicXML packages."""

from __future__ import annotations

import hashlib
import io
import re
import stat
import zipfile
from dataclasses import dataclass
from pathlib import PurePosixPath

from lxml import etree

from .contracts import IngestionLimits, PackageResource, PackageRootfile
from .diagnostics import DiagnosticStage, boundary_failure
from .validation import parse_container_document

MXL_MEDIA_TYPE = b"application/vnd.recordare.musicxml"
MUSICXML_ROOT_MEDIA_TYPES = frozenset(
    {
        "application/vnd.recordare.musicxml+xml",
        "application/xml",
        "text/xml",
    }
)
_ALLOWED_COMPRESSION = frozenset({zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED})
_DRIVE_PREFIX = re.compile(r"^[A-Za-z]:")
_WINDOWS_DEVICES = frozenset(
    {
        "aux",
        "con",
        "nul",
        "prn",
        *(f"com{number}" for number in range(1, 10)),
        *(f"lpt{number}" for number in range(1, 10)),
    }
)


@dataclass(frozen=True, slots=True)
class ResolvedPackage:
    """Safely selected MusicXML root bytes plus retained package facts."""

    document_bytes: bytes
    container_tree: etree._ElementTree
    selected_rootfile: str
    selected_rootfile_sha256: str
    rootfiles: tuple[PackageRootfile, ...]
    entries: tuple[str, ...]
    resources: tuple[PackageResource, ...]


def resolve_mxl(data: bytes, limits: IngestionLimits) -> ResolvedPackage:
    """Inspect one MXL archive and return its deterministic MusicXML rootfile."""

    try:
        archive = zipfile.ZipFile(io.BytesIO(data))
    except (zipfile.BadZipFile, OSError) as error:
        raise boundary_failure(
            "MXL_ARCHIVE_INVALID",
            DiagnosticStage.ARCHIVE,
            "the compressed source is not a readable ZIP archive",
        ) from error

    with archive:
        infos = tuple(archive.infolist())
        if not infos:
            raise boundary_failure(
                "MXL_ARCHIVE_EMPTY",
                DiagnosticStage.ARCHIVE,
                "the compressed source contains no entries",
            )
        if len(infos) > limits.max_archive_entries:
            raise boundary_failure(
                "MXL_ARCHIVE_ENTRY_LIMIT",
                DiagnosticStage.LIMIT,
                "the archive entry count exceeds the configured limit",
            )
        index = _validate_archive_entries(infos, limits)
        _validate_mimetype(archive, index, limits)

        container_info = index.get("META-INF/container.xml")
        if container_info is None or container_info.is_dir():
            raise boundary_failure(
                "MXL_CONTAINER_MISSING",
                DiagnosticStage.CONTAINER,
                "the archive does not contain META-INF/container.xml",
            )
        container_bytes = _read_bounded(archive, container_info, limits)
        container_tree = parse_container_document(container_bytes, limits)
        rootfiles = _read_rootfiles(container_tree)
        selected = _select_rootfile(rootfiles)
        selected_info = index.get(selected.full_path)
        if selected_info is None or selected_info.is_dir():
            raise boundary_failure(
                "MXL_ROOTFILE_MISSING",
                DiagnosticStage.CONTAINER,
                "the selected MusicXML rootfile is absent from the archive",
                logical_path=selected.full_path,
            )
        for rootfile in rootfiles:
            entry = index.get(rootfile.full_path)
            if entry is None or entry.is_dir():
                raise boundary_failure(
                    "MXL_DECLARED_ROOTFILE_MISSING",
                    DiagnosticStage.CONTAINER,
                    "a rootfile declared by the container is absent from the archive",
                    logical_path=rootfile.full_path,
                )
        document_bytes = _read_bounded(archive, selected_info, limits)
        rootfile_types = {item.full_path: item.media_type for item in rootfiles}
        resources = tuple(
            PackageResource(
                logical_path=name,
                data=_read_bounded(archive, info, limits),
                declared_media_type=rootfile_types.get(name),
                is_rootfile=name in rootfile_types,
            )
            for name, info in sorted(index.items())
            if not info.is_dir()
        )
        return ResolvedPackage(
            document_bytes=document_bytes,
            container_tree=container_tree,
            selected_rootfile=selected.full_path,
            selected_rootfile_sha256=hashlib.sha256(document_bytes).hexdigest(),
            rootfiles=rootfiles,
            entries=tuple(sorted(index)),
            resources=resources,
        )


def _validate_archive_entries(
    infos: tuple[zipfile.ZipInfo, ...],
    limits: IngestionLimits,
) -> dict[str, zipfile.ZipInfo]:
    index: dict[str, zipfile.ZipInfo] = {}
    casefolded: dict[str, str] = {}
    total_expanded = 0
    for info in infos:
        name = _validated_archive_path(info.filename)
        if name in index:
            raise boundary_failure(
                "MXL_ARCHIVE_DUPLICATE_PATH",
                DiagnosticStage.ARCHIVE,
                "the archive contains a duplicate logical path",
                logical_path=name,
            )
        folded = name.casefold()
        if folded in casefolded:
            raise boundary_failure(
                "MXL_ARCHIVE_CASE_COLLISION",
                DiagnosticStage.ARCHIVE,
                "archive paths are ambiguous under case-insensitive comparison",
                logical_path=name,
            )
        casefolded[folded] = name
        index[name] = info

        if info.flag_bits & 0x1:
            raise boundary_failure(
                "MXL_ARCHIVE_ENCRYPTED",
                DiagnosticStage.ARCHIVE,
                "encrypted archive entries are not permitted",
                logical_path=name,
            )
        mode = (info.external_attr >> 16) & 0xFFFF
        file_type = stat.S_IFMT(mode)
        if file_type not in {0, stat.S_IFREG, stat.S_IFDIR}:
            raise boundary_failure(
                "MXL_ARCHIVE_SPECIAL_FILE",
                DiagnosticStage.ARCHIVE,
                "symbolic links and special archive entries are not permitted",
                logical_path=name,
            )
        if info.compress_type not in _ALLOWED_COMPRESSION:
            raise boundary_failure(
                "MXL_ARCHIVE_COMPRESSION_UNSUPPORTED",
                DiagnosticStage.ARCHIVE,
                "only stored and DEFLATE-compressed entries are permitted",
                logical_path=name,
            )
        if info.file_size > limits.max_archive_entry_bytes:
            raise boundary_failure(
                "MXL_ARCHIVE_ENTRY_SIZE_LIMIT",
                DiagnosticStage.LIMIT,
                "an expanded archive entry exceeds the configured limit",
                logical_path=name,
            )
        total_expanded += info.file_size
        if total_expanded > limits.max_archive_total_bytes:
            raise boundary_failure(
                "MXL_ARCHIVE_TOTAL_SIZE_LIMIT",
                DiagnosticStage.LIMIT,
                "the total expanded archive size exceeds the configured limit",
            )
        if info.file_size:
            if info.compress_size == 0:
                ratio = float(limits.max_compression_ratio + 1)
            else:
                ratio = info.file_size / info.compress_size
            if ratio > limits.max_compression_ratio:
                raise boundary_failure(
                    "MXL_ARCHIVE_COMPRESSION_RATIO_LIMIT",
                    DiagnosticStage.LIMIT,
                    "an archive entry exceeds the configured compression ratio",
                    logical_path=name,
                )
    return index


def _validated_archive_path(name: str) -> str:
    if not name or "\x00" in name or "\\" in name or any(ord(char) < 32 for char in name):
        raise boundary_failure(
            "MXL_ARCHIVE_PATH_INVALID",
            DiagnosticStage.ARCHIVE,
            "an archive entry has an invalid logical path",
            logical_path=name or None,
        )
    if name.startswith("/") or _DRIVE_PREFIX.match(name):
        raise boundary_failure(
            "MXL_ARCHIVE_PATH_ABSOLUTE",
            DiagnosticStage.ARCHIVE,
            "absolute archive paths are not permitted",
            logical_path=name,
        )
    path = PurePosixPath(name)
    parts = path.parts
    if not parts or any(part in {"", ".", ".."} for part in parts):
        raise boundary_failure(
            "MXL_ARCHIVE_PATH_TRAVERSAL",
            DiagnosticStage.ARCHIVE,
            "archive paths may not traverse or contain empty components",
            logical_path=name,
        )
    for part in parts:
        device_name = part.split(".", 1)[0].casefold()
        if ":" in part or device_name in _WINDOWS_DEVICES:
            raise boundary_failure(
                "MXL_ARCHIVE_DEVICE_PATH",
                DiagnosticStage.ARCHIVE,
                "device-like archive paths are not permitted",
                logical_path=name,
            )
    canonical = "/".join(parts)
    if name.endswith("/"):
        canonical += "/"
    if canonical != name:
        raise boundary_failure(
            "MXL_ARCHIVE_PATH_NONCANONICAL",
            DiagnosticStage.ARCHIVE,
            "archive paths must use canonical POSIX form",
            logical_path=name,
        )
    return name.rstrip("/") if name.endswith("/") else name


def _validate_mimetype(
    archive: zipfile.ZipFile,
    index: dict[str, zipfile.ZipInfo],
    limits: IngestionLimits,
) -> None:
    info = index.get("mimetype")
    if info is None:
        return
    if info.compress_type != zipfile.ZIP_STORED or info.extra:
        raise boundary_failure(
            "MXL_MIMETYPE_ENCODING_INVALID",
            DiagnosticStage.ARCHIVE,
            "the optional mimetype entry must be stored and have no extra field",
            logical_path="mimetype",
        )
    if _read_bounded(archive, info, limits) != MXL_MEDIA_TYPE:
        raise boundary_failure(
            "MXL_MIMETYPE_INVALID",
            DiagnosticStage.ARCHIVE,
            "the optional mimetype entry has the wrong value",
            logical_path="mimetype",
        )


def _read_bounded(
    archive: zipfile.ZipFile,
    info: zipfile.ZipInfo,
    limits: IngestionLimits,
) -> bytes:
    maximum = min(limits.max_archive_entry_bytes, info.file_size)
    try:
        with archive.open(info, "r") as stream:
            value = stream.read(maximum + 1)
    except (OSError, RuntimeError, zipfile.BadZipFile) as error:
        raise boundary_failure(
            "MXL_ARCHIVE_ENTRY_UNREADABLE",
            DiagnosticStage.ARCHIVE,
            "an archive entry could not be read safely",
            logical_path=info.filename,
        ) from error
    if len(value) > maximum or len(value) != info.file_size:
        raise boundary_failure(
            "MXL_ARCHIVE_ENTRY_SIZE_MISMATCH",
            DiagnosticStage.ARCHIVE,
            "an archive entry does not match its declared expanded size",
            logical_path=info.filename,
        )
    return value


def _read_rootfiles(tree: etree._ElementTree) -> tuple[PackageRootfile, ...]:
    rootfiles_element = tree.getroot().find("rootfiles")
    if rootfiles_element is None:
        raise boundary_failure(
            "MXL_ROOTFILES_MISSING",
            DiagnosticStage.CONTAINER,
            "the container does not declare a rootfiles element",
            logical_path="META-INF/container.xml",
        )
    result: list[PackageRootfile] = []
    seen: set[str] = set()
    for element in rootfiles_element.findall("rootfile"):
        raw_path = element.get("full-path")
        if raw_path is None:
            raise boundary_failure(
                "MXL_ROOTFILE_PATH_MISSING",
                DiagnosticStage.CONTAINER,
                "a rootfile declaration has no full-path",
                logical_path="META-INF/container.xml",
                line=element.sourceline if isinstance(element.sourceline, int) else None,
            )
        full_path = _validated_archive_path(raw_path)
        if full_path in seen:
            raise boundary_failure(
                "MXL_ROOTFILE_DUPLICATE",
                DiagnosticStage.CONTAINER,
                "the container declares the same rootfile more than once",
                logical_path=full_path,
            )
        seen.add(full_path)
        media_type = element.get("media-type")
        result.append(PackageRootfile(full_path=full_path, media_type=media_type))
    if not result:
        raise boundary_failure(
            "MXL_ROOTFILE_MISSING",
            DiagnosticStage.CONTAINER,
            "the container declares no MusicXML rootfile",
            logical_path="META-INF/container.xml",
        )
    return tuple(result)


def _select_rootfile(rootfiles: tuple[PackageRootfile, ...]) -> PackageRootfile:
    selected = rootfiles[0]
    if selected.media_type is not None and selected.media_type not in MUSICXML_ROOT_MEDIA_TYPES:
        raise boundary_failure(
            "MXL_PRIMARY_ROOTFILE_MEDIA_TYPE_INVALID",
            DiagnosticStage.CONTAINER,
            "the first rootfile is not declared as MusicXML",
            logical_path=selected.full_path,
        )
    return selected
