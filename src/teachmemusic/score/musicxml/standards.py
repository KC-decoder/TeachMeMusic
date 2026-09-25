"""Pinned MusicXML standards resources and local-only validation support."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast
from urllib.parse import unquote, urlsplit

from lxml import etree

SOURCES_FORMAT = "teachmemusic.musicxml.sources/1"
MANIFEST_FORMAT = "teachmemusic.musicxml.resource-manifest/1"
ALLOWED_REMOTE_RESOURCES = {
    "http://www.musicxml.org/dtds/container.dtd": "container.dtd",
    "http://www.musicxml.org/dtds/opus.dtd": "opus.dtd",
    "http://www.musicxml.org/dtds/partwise.dtd": "partwise.dtd",
    "http://www.musicxml.org/dtds/sounds.dtd": "sounds.dtd",
    "http://www.musicxml.org/dtds/timewise.dtd": "timewise.dtd",
    "http://www.musicxml.org/xsd/musicxml.xsd": "musicxml.xsd",
    "http://www.musicxml.org/xsd/opus.xsd": "opus.xsd",
    "http://www.musicxml.org/xsd/sounds.xsd": "sounds.xsd",
    "http://www.musicxml.org/xsd/xlink.xsd": "xlink.xsd",
    "http://www.musicxml.org/xsd/xml.xsd": "xml.xsd",
    "http://www.w3.org/2001/xml.xsd": "xml.xsd",
    "http://www.w3.org/2007/08/xml.xsd": "xml.xsd",
}


@dataclass(frozen=True, slots=True)
class ManifestProblem:
    """One deterministic standards-resource integrity problem."""

    code: str
    path: str
    detail: str


@dataclass(frozen=True, slots=True)
class CompilationResult:
    """Counts of standard resources successfully parsed or compiled."""

    version: str
    xsd_entrypoints: int
    dtd_entrypoints: int
    auxiliary_xml_files: int


class LocalOnlyResolver(etree.Resolver):
    """Resolve imports only to files inside one immutable version bundle."""

    def __init__(self, bundle_root: Path) -> None:
        super().__init__()
        self._bundle_root = bundle_root.resolve()
        self._schema_root = (self._bundle_root / "schema").resolve()

    def resolve(  # type: ignore[override]
        self,
        url: str,
        public_id: str | None,
        context: object,
    ) -> object:
        """Resolve an approved standard URL or reject it without networking."""

        del public_id
        parsed = urlsplit(url)
        if parsed.scheme in {"http", "https"}:
            filename = ALLOWED_REMOTE_RESOURCES.get(url)
            if filename is None:
                raise OSError(f"remote schema URL is not approved: {url}")
            candidate = self._schema_root / filename
        elif parsed.scheme == "file":
            candidate = Path(unquote(parsed.path))
        elif parsed.scheme:
            raise OSError(f"schema URI scheme is not approved: {parsed.scheme}")
        else:
            relative = Path(unquote(parsed.path))
            if relative.is_absolute():
                candidate = relative
            elif len(relative.parts) != 1:
                raise OSError(f"relative schema path is not approved: {url}")
            else:
                candidate = self._schema_root / relative

        resolved = candidate.resolve()
        if not resolved.is_relative_to(self._bundle_root):
            raise OSError(f"schema path escapes the pinned bundle: {url}")
        if not resolved.is_file():
            raise OSError(f"pinned schema resource does not exist: {resolved.name}")
        resolve_filename = cast(Callable[[str, object], object], cast(Any, self).resolve_filename)
        return resolve_filename(str(resolved), context)


def resource_root() -> Path:
    """Return the checked-in standards resource root."""

    return Path(__file__).with_name("resources")


def _load_json(path: Path) -> dict[str, object]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected a JSON object in {path}")
    return cast(dict[str, object], value)


def _canonical_json(value: object) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n").encode()


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load_sources(root: Path | None = None) -> dict[str, object]:
    """Load and minimally validate immutable source revision metadata."""

    selected_root = root or resource_root()
    document = _load_json(selected_root / "source-revisions.json")
    if document.get("format") != SOURCES_FORMAT:
        raise ValueError("unsupported MusicXML source-revisions format")
    versions = document.get("versions")
    if not isinstance(versions, list) or not versions:
        raise ValueError("source-revisions must contain at least one version")
    return document


def source_versions(root: Path | None = None) -> tuple[dict[str, object], ...]:
    """Return source version records in their declared order."""

    versions = load_sources(root)["versions"]
    assert isinstance(versions, list)
    return tuple(cast(dict[str, object], item) for item in versions)


def generate_manifest(root: Path | None = None) -> dict[str, object]:
    """Generate a deterministic hash manifest for every vendored upstream file."""

    selected_root = (root or resource_root()).resolve()
    source_document = load_sources(selected_root)
    manifest_versions: list[dict[str, object]] = []

    for source in source_versions(selected_root):
        directory = _required_text(source, "directory")
        bundle_root = selected_root / directory
        if not bundle_root.is_dir():
            raise FileNotFoundError(f"missing MusicXML resource bundle: {directory}")
        files = [
            {
                "path": path.relative_to(bundle_root).as_posix(),
                "sha256": _sha256_file(path),
                "size": path.stat().st_size,
            }
            for path in sorted(bundle_root.rglob("*"))
            if path.is_file()
        ]
        version_record = {
            key: value
            for key, value in source.items()
            if key not in {"xsd_entrypoints", "dtd_entrypoints"}
        }
        version_record["xsd_entrypoints"] = source.get("xsd_entrypoints", [])
        version_record["dtd_entrypoints"] = source.get("dtd_entrypoints", [])
        version_record["files"] = files
        manifest_versions.append(version_record)

    unsigned: dict[str, object] = {
        "format": MANIFEST_FORMAT,
        "source_format": source_document["format"],
        "repository": source_document["repository"],
        "versions": manifest_versions,
    }
    return {**unsigned, "content_sha256": _sha256_bytes(_canonical_json(unsigned))}


def write_manifest(output: Path, root: Path | None = None) -> None:
    """Write the deterministic vendored-resource manifest."""

    output.write_bytes(_canonical_json(generate_manifest(root)))


def verify_manifest(
    root: Path | None = None,
    manifest_path: Path | None = None,
) -> tuple[ManifestProblem, ...]:
    """Compare checked-in resources with their recorded hashes and membership."""

    selected_root = (root or resource_root()).resolve()
    selected_manifest = manifest_path or selected_root / "manifest.json"
    if not selected_manifest.is_file():
        return (
            ManifestProblem("manifest-missing", "manifest.json", "resource manifest is absent"),
        )

    expected = _load_json(selected_manifest)
    actual = generate_manifest(selected_root)
    problems: list[ManifestProblem] = []
    if expected.get("format") != MANIFEST_FORMAT:
        problems.append(
            ManifestProblem(
                "manifest-format",
                "manifest.json",
                "manifest format is missing or unsupported",
            )
        )

    expected_versions = _version_index(expected)
    actual_versions = _version_index(actual)
    for directory in sorted(actual_versions.keys() - expected_versions.keys()):
        problems.append(
            ManifestProblem("version-unrecorded", directory, "bundle is absent from manifest")
        )
    for directory in sorted(expected_versions.keys() - actual_versions.keys()):
        problems.append(
            ManifestProblem("version-missing", directory, "manifest bundle is absent on disk")
        )

    for directory in sorted(expected_versions.keys() & actual_versions.keys()):
        expected_files = _file_index(expected_versions[directory])
        actual_files = _file_index(actual_versions[directory])
        for path in sorted(actual_files.keys() - expected_files.keys()):
            problems.append(
                ManifestProblem("file-unrecorded", f"{directory}/{path}", "file is unmanifested")
            )
        for path in sorted(expected_files.keys() - actual_files.keys()):
            problems.append(
                ManifestProblem("file-missing", f"{directory}/{path}", "file is absent")
            )
        for path in sorted(expected_files.keys() & actual_files.keys()):
            expected_file = expected_files[path]
            actual_file = actual_files[path]
            if expected_file.get("sha256") != actual_file.get("sha256"):
                problems.append(
                    ManifestProblem(
                        "hash-mismatch",
                        f"{directory}/{path}",
                        "SHA-256 does not match the pinned manifest",
                    )
                )
            if expected_file.get("size") != actual_file.get("size"):
                problems.append(
                    ManifestProblem(
                        "size-mismatch",
                        f"{directory}/{path}",
                        "byte length does not match the pinned manifest",
                    )
                )

    expected_unsigned = {key: value for key, value in expected.items() if key != "content_sha256"}
    expected_digest = _sha256_bytes(_canonical_json(expected_unsigned))
    if expected.get("content_sha256") != expected_digest:
        problems.append(
            ManifestProblem(
                "manifest-digest",
                "manifest.json",
                "manifest content digest is invalid",
            )
        )
    return tuple(sorted(problems, key=lambda item: (item.code, item.path, item.detail)))


def _version_index(document: dict[str, object]) -> dict[str, dict[str, object]]:
    raw_versions = document.get("versions", [])
    if not isinstance(raw_versions, list):
        return {}
    result: dict[str, dict[str, object]] = {}
    for value in raw_versions:
        if isinstance(value, dict) and isinstance(value.get("directory"), str):
            item = cast(dict[str, object], value)
            result[cast(str, item["directory"])] = item
    return result


def _file_index(version: dict[str, object]) -> dict[str, dict[str, object]]:
    raw_files = version.get("files", [])
    if not isinstance(raw_files, list):
        return {}
    result: dict[str, dict[str, object]] = {}
    for value in raw_files:
        if isinstance(value, dict) and isinstance(value.get("path"), str):
            item = cast(dict[str, object], value)
            result[cast(str, item["path"])] = item
    return result


def _required_text(document: dict[str, object], key: str) -> str:
    value = document.get(key)
    if not isinstance(value, str) or not value:
        raise ValueError(f"required non-empty string is missing: {key}")
    return value


def _required_text_list(document: dict[str, object], key: str) -> tuple[str, ...]:
    value = document.get(key)
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise ValueError(f"required string list is missing: {key}")
    return tuple(cast(list[str], value))


def secure_xml_parser(bundle_root: Path) -> etree.XMLParser:
    """Create the local-only parser used to compile pinned standard resources."""

    parser = etree.XMLParser(
        load_dtd=False,
        no_network=True,
        recover=False,
        resolve_entities=False,
        huge_tree=False,
        remove_comments=False,
        remove_pis=False,
    )
    parser.resolvers.add(LocalOnlyResolver(bundle_root))
    return parser


def compile_standard_resources(root: Path | None = None) -> tuple[CompilationResult, ...]:
    """Compile every declared XSD/DTD entrypoint and parse auxiliary XML locally."""

    selected_root = (root or resource_root()).resolve()
    results: list[CompilationResult] = []
    for source in source_versions(selected_root):
        version = _required_text(source, "version")
        directory = _required_text(source, "directory")
        bundle_root = selected_root / directory
        xsd_entrypoints = _required_text_list(source, "xsd_entrypoints")
        dtd_entrypoints = _required_text_list(source, "dtd_entrypoints")

        for relative in xsd_entrypoints:
            parser = secure_xml_parser(bundle_root)
            document = etree.parse(str(bundle_root / relative), parser)
            etree.XMLSchema(document)
        for relative in dtd_entrypoints:
            etree.DTD(str(bundle_root / relative))

        declared = set(xsd_entrypoints) | set(dtd_entrypoints)
        auxiliary_count = 0
        for path in sorted((bundle_root / "schema").iterdir()):
            relative = path.relative_to(bundle_root).as_posix()
            if not path.is_file() or relative in declared:
                continue
            if path.suffix.lower() not in {".xml", ".xsl"}:
                continue
            etree.parse(str(path), secure_xml_parser(bundle_root))
            auxiliary_count += 1

        results.append(
            CompilationResult(
                version=version,
                xsd_entrypoints=len(xsd_entrypoints),
                dtd_entrypoints=len(dtd_entrypoints),
                auxiliary_xml_files=auxiliary_count,
            )
        )
    return tuple(results)


def _build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "command",
        choices=("generate-manifest", "verify", "compile"),
    )
    parser.add_argument("--root", type=Path, default=resource_root())
    parser.add_argument("--output", type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    """Run standards-resource generation and verification commands."""

    arguments = _build_argument_parser().parse_args(argv)
    root = cast(Path, arguments.root)
    if arguments.command == "generate-manifest":
        output = cast(Path | None, arguments.output) or root / "manifest.json"
        write_manifest(output, root)
        print(f"wrote {output}")
        return 0
    if arguments.command == "verify":
        problems = verify_manifest(root)
        for problem in problems:
            print(f"{problem.code}: {problem.path}: {problem.detail}")
        return 1 if problems else 0

    results = compile_standard_resources(root)
    for result in results:
        print(
            f"{result.version}: {result.xsd_entrypoints} XSD, "
            f"{result.dtd_entrypoints} DTD, "
            f"{result.auxiliary_xml_files} auxiliary XML/XSL"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
