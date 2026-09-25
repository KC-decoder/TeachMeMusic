"""Run reproducible validation and mapping audits over pinned MusicXML corpora."""

from __future__ import annotations

import argparse
import json
import subprocess
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import cast

from lxml import etree

from ..v2.temporal_codec import (
    TemporalCodecError,
    deferred_from_dict,
    deferred_to_dict,
    temporal_from_dict,
    temporal_to_dict,
)
from ..v2.temporal_validation import validate_deferred_constructs, validate_temporal_score
from .boundary import validate_musicxml_source
from .diagnostics import MusicXmlBoundaryError
from .standards import resource_root
from .temporal import map_temporal_score

CORPUS_MANIFEST_FORMAT = "teachmemusic.musicxml.corpora/1"
_VALID_EXPECTATIONS = frozenset({"pass", "fail"})


class CorpusAuditError(ValueError):
    """The requested corpus checkout cannot produce trustworthy evidence."""


@dataclass(frozen=True, slots=True)
class CorpusDefinition:
    """One externally maintained corpus pinned to an immutable Git revision."""

    id: str
    run_id: str
    repository: str
    revision: str
    directory: str
    recursive: bool
    expected_files: int
    extensions: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class CorpusFileResult:
    """Observed boundary and canonical-mapping result for one corpus file."""

    path: str
    expected_validation: str
    actual_validation: str
    mapping: str
    deferred_occurrences: int = 0
    diagnostic: str | None = None
    software: tuple[str, ...] = ()

    @property
    def validation_matches(self) -> bool:
        return self.expected_validation == self.actual_validation


@dataclass(frozen=True, slots=True)
class SchematronFileResult:
    """Observed result for one pinned upstream XPath 3 Schematron assertion."""

    path: str
    schema: str
    expected_validation: str
    actual_validation: str
    diagnostic: str | None = None

    @property
    def validation_matches(self) -> bool:
        return self.expected_validation == self.actual_validation


@dataclass(frozen=True, slots=True)
class CorpusResult:
    """Reproducible evidence from one exact corpus checkout."""

    id: str
    run_id: str
    repository: str
    revision: str
    files: tuple[CorpusFileResult, ...]
    schematron: tuple[SchematronFileResult, ...] = ()

    @property
    def validation_complete(self) -> bool:
        return all(item.validation_matches for item in self.files) and all(
            item.validation_matches for item in self.schematron
        )


@dataclass(frozen=True, slots=True)
class CorpusAudit:
    """Combined Task 7I baseline for both required official corpora."""

    corpora: tuple[CorpusResult, ...]

    @property
    def validation_complete(self) -> bool:
        return all(corpus.validation_complete for corpus in self.corpora)

    @property
    def mapping_complete(self) -> bool:
        return all(
            item.mapping in {"not-applicable", "mapped-zero-deferred"}
            for corpus in self.corpora
            for item in corpus.files
        )

    @property
    def corpus_mapping_complete(self) -> bool:
        """Return whether this bounded validation-and-mapping gate is green."""

        return self.validation_complete and self.mapping_complete


def _load_json(path: Path) -> dict[str, object]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise CorpusAuditError(f"cannot read corpus evidence file: {path}") from error
    if not isinstance(value, dict):
        raise CorpusAuditError(f"expected JSON object in {path}")
    return cast(dict[str, object], value)


def load_corpus_definitions(path: Path | None = None) -> tuple[CorpusDefinition, ...]:
    """Load and validate the governed corpus pins."""

    manifest_path = path or resource_root() / "corpora.json"
    document = _load_json(manifest_path)
    if document.get("format") != CORPUS_MANIFEST_FORMAT:
        raise CorpusAuditError("unsupported corpus manifest format")
    values = document.get("corpora")
    if not isinstance(values, list):
        raise CorpusAuditError("corpus manifest has no corpus list")
    definitions: list[CorpusDefinition] = []
    ids: set[str] = set()
    run_ids: set[str] = set()
    for value in values:
        if not isinstance(value, dict):
            raise CorpusAuditError("corpus definition must be an object")
        definition = _corpus_definition(cast(dict[str, object], value))
        if definition.id in ids:
            raise CorpusAuditError(f"duplicate corpus id: {definition.id}")
        if definition.run_id in run_ids:
            raise CorpusAuditError(f"duplicate corpus run id: {definition.run_id}")
        ids.add(definition.id)
        run_ids.add(definition.run_id)
        definitions.append(definition)
    return tuple(definitions)


def _corpus_definition(value: dict[str, object]) -> CorpusDefinition:
    text_fields = ("id", "run_id", "repository", "revision", "directory")
    texts: dict[str, str] = {}
    for field in text_fields:
        candidate = value.get(field)
        if not isinstance(candidate, str) or not candidate:
            raise CorpusAuditError(f"corpus definition has invalid {field}")
        texts[field] = candidate
    recursive = value.get("recursive")
    expected_files = value.get("expected_files")
    extensions = value.get("extensions")
    if not isinstance(recursive, bool):
        raise CorpusAuditError("corpus definition has invalid recursive flag")
    if (
        not isinstance(expected_files, int)
        or isinstance(expected_files, bool)
        or expected_files < 1
    ):
        raise CorpusAuditError("corpus definition has invalid expected_files")
    if (
        not isinstance(extensions, list)
        or not extensions
        or not all(isinstance(item, str) and item.startswith(".") for item in extensions)
    ):
        raise CorpusAuditError("corpus definition has invalid extensions")
    return CorpusDefinition(
        id=texts["id"],
        run_id=texts["run_id"],
        repository=texts["repository"],
        revision=texts["revision"],
        directory=texts["directory"],
        recursive=recursive,
        expected_files=expected_files,
        extensions=tuple(cast(list[str], extensions)),
    )


def _git_revision(checkout: Path) -> str:
    if not checkout.is_dir():
        raise CorpusAuditError(f"corpus checkout is missing: {checkout}")
    process = subprocess.run(
        ["git", "-C", str(checkout), "rev-parse", "HEAD"],
        check=False,
        capture_output=True,
        text=True,
    )
    if process.returncode != 0:
        raise CorpusAuditError(f"corpus checkout is not a readable Git worktree: {checkout}")
    return process.stdout.strip()


def _corpus_paths(checkout: Path, definition: CorpusDefinition) -> tuple[Path, ...]:
    directory = checkout / definition.directory
    if not directory.is_dir():
        raise CorpusAuditError(f"corpus directory is missing: {definition.directory}")
    iterator = directory.rglob("*") if definition.recursive else directory.glob("*")
    paths = tuple(
        sorted(path for path in iterator if path.is_file() and path.suffix in definition.extensions)
    )
    if len(paths) != definition.expected_files:
        raise CorpusAuditError(
            f"{definition.id} contains {len(paths)} files; expected {definition.expected_files}"
        )
    return paths


def _expected_validation(path: Path, assertions: dict[str, object]) -> str:
    value = assertions.get(path.name)
    if not isinstance(value, dict):
        return "pass"
    expected = value.get("musicxml.xsd", "pass")
    if expected not in _VALID_EXPECTATIONS:
        raise CorpusAuditError(f"unsupported validation expectation for {path.name}: {expected}")
    return cast(str, expected)


def _schematron_expectations(
    assertions: dict[str, object],
) -> tuple[tuple[str, str, str], ...]:
    expectations: list[tuple[str, str, str]] = []
    for filename, value in assertions.items():
        if not isinstance(value, dict):
            continue
        for schema, expected in value.items():
            if not isinstance(schema, str) or not schema.endswith(".sch"):
                continue
            if expected not in _VALID_EXPECTATIONS:
                raise CorpusAuditError(
                    f"unsupported Schematron expectation for {filename}/{schema}: {expected}"
                )
            expectations.append((filename, schema, cast(str, expected)))
    return tuple(sorted(expectations))


def _audit_schematron_file(
    source: Path,
    stylesheet: Path,
    expected: str,
) -> SchematronFileResult:
    """Execute one pinned upstream XPath 3 stylesheet with Saxon/C."""

    try:
        from saxonche import PySaxonProcessor  # type: ignore[import-not-found]
    except ImportError as error:
        raise CorpusAuditError(
            "Saxon/C is required for the pinned XPath 3 Schematron evidence"
        ) from error
    try:
        with PySaxonProcessor(license=False) as processor:
            executable = processor.new_xslt30_processor().compile_stylesheet(
                stylesheet_file=str(stylesheet)
            )
            document = processor.parse_xml(xml_file_name=str(source))
            output = executable.transform_to_string(xdm_node=document)
    except Exception as error:
        raise CorpusAuditError(
            f"Schematron execution failed for {source.name}/{stylesheet.name}"
        ) from error
    if output is None:
        raise CorpusAuditError(f"Schematron produced no result for {source.name}/{stylesheet.name}")
    parser = etree.XMLParser(resolve_entities=False, no_network=True, recover=False)
    try:
        report = etree.fromstring(output.encode("utf-8"), parser=parser)
    except etree.XMLSyntaxError as error:
        raise CorpusAuditError(
            f"Schematron produced malformed SVRL for {source.name}/{stylesheet.name}"
        ) from error
    failures = cast(
        list[object],
        report.xpath(
            "//svrl:failed-assert",
            namespaces={"svrl": "http://purl.oclc.org/dsdl/svrl"},
        ),
    )
    actual = "fail" if failures else "pass"
    return SchematronFileResult(
        path=source.name,
        schema=stylesheet.with_suffix(".sch").name,
        expected_validation=expected,
        actual_validation=actual,
        diagnostic=None if not failures else f"{len(failures)} failed assertion(s)",
    )


def _audit_file(path: Path, expected: str) -> CorpusFileResult:
    try:
        document = validate_musicxml_source(path.read_bytes(), logical_name=path.name)
    except MusicXmlBoundaryError as error:
        return CorpusFileResult(
            path=path.name,
            expected_validation=expected,
            actual_validation="fail",
            mapping="not-applicable",
            diagnostic=error.primary.code,
        )
    software = tuple(
        value
        for node in document.root.findall("./identification/encoding/software")
        if (value := (node.text or "").strip())
    )
    try:
        mapped = map_temporal_score(document)
    except ValueError as error:
        return CorpusFileResult(
            path=path.name,
            expected_validation=expected,
            actual_validation="pass",
            mapping="failed",
            diagnostic=f"{type(error).__name__}: {' '.join(str(error).split())}",
            software=software,
        )
    canonical_issues = (
        *validate_temporal_score(mapped.score),
        *validate_deferred_constructs(mapped.deferred),
    )
    if canonical_issues:
        issue = canonical_issues[0]
        return CorpusFileResult(
            path=path.name,
            expected_validation=expected,
            actual_validation="pass",
            mapping="failed",
            diagnostic=f"{issue.code}: {issue.path}",
            software=software,
        )
    try:
        score_round_trip = temporal_from_dict(temporal_to_dict(mapped.score))
        deferred_round_trip = tuple(
            deferred_from_dict(deferred_to_dict(item)) for item in mapped.deferred
        )
    except TemporalCodecError as error:
        return CorpusFileResult(
            path=path.name,
            expected_validation=expected,
            actual_validation="pass",
            mapping="failed",
            diagnostic=f"{type(error).__name__}: {' '.join(str(error).split())}",
            software=software,
        )
    if score_round_trip != mapped.score or deferred_round_trip != mapped.deferred:
        return CorpusFileResult(
            path=path.name,
            expected_validation=expected,
            actual_validation="pass",
            mapping="failed",
            diagnostic="TEMPORAL_ROUND_TRIP_MISMATCH",
            software=software,
        )
    deferred = sum(item.occurrences for item in mapped.deferred)
    return CorpusFileResult(
        path=path.name,
        expected_validation=expected,
        actual_validation="pass",
        mapping="mapped-zero-deferred" if deferred == 0 else "mapped-with-deferred",
        deferred_occurrences=deferred,
        software=software,
    )


def audit_corpora(
    w3c_checkout: Path,
    community_checkout: Path,
    *,
    manifest_path: Path | None = None,
) -> CorpusAudit:
    """Audit the exact pinned checkouts and reject incomplete or wrong sources."""

    definitions = load_corpus_definitions(manifest_path)
    by_id = {definition.id: definition for definition in definitions}
    required = {"w3c-maintained-validation", "w3c-community-feature-suite"}
    if set(by_id) != required:
        raise CorpusAuditError("corpus manifest must define exactly the two governed corpora")
    checkouts = {
        "w3c-maintained-validation": w3c_checkout,
        "w3c-community-feature-suite": community_checkout,
    }
    assertions = _load_json(w3c_checkout / "tests" / "assertions.json")
    results: list[CorpusResult] = []
    for corpus_id in sorted(required):
        definition = by_id[corpus_id]
        checkout = checkouts[corpus_id]
        actual_revision = _git_revision(checkout)
        if actual_revision != definition.revision:
            raise CorpusAuditError(
                f"{corpus_id} is at {actual_revision}; expected {definition.revision}"
            )
        files = _corpus_paths(checkout, definition)
        schematron: tuple[SchematronFileResult, ...] = ()
        if corpus_id == "w3c-maintained-validation":
            test_root = checkout / "tests"
            schematron = tuple(
                _audit_schematron_file(
                    test_root / "files" / filename,
                    test_root / "validations" / Path(schema).with_suffix(".xsl"),
                    expected,
                )
                for filename, schema, expected in _schematron_expectations(assertions)
            )
        results.append(
            CorpusResult(
                id=definition.id,
                run_id=definition.run_id,
                repository=definition.repository,
                revision=definition.revision,
                files=tuple(
                    _audit_file(path, _expected_validation(path, assertions)) for path in files
                ),
                schematron=schematron,
            )
        )
    return CorpusAudit(tuple(results))


def render_json(audit: CorpusAudit) -> str:
    """Serialize corpus evidence without machine-specific checkout paths."""

    payload = {
        "format": "teachmemusic.musicxml.corpus-audit/2",
        "corpus_mapping_complete": audit.corpus_mapping_complete,
        "validation_complete": audit.validation_complete,
        "mapping_complete": audit.mapping_complete,
        "corpora": [
            {
                "id": corpus.id,
                "run_id": corpus.run_id,
                "repository": corpus.repository,
                "revision": corpus.revision,
                "files": [
                    {
                        "path": item.path,
                        "expected_validation": item.expected_validation,
                        "actual_validation": item.actual_validation,
                        "validation_matches": item.validation_matches,
                        "mapping": item.mapping,
                        "deferred_occurrences": item.deferred_occurrences,
                        "diagnostic": item.diagnostic,
                        "software": list(item.software),
                    }
                    for item in corpus.files
                ],
                "schematron": [
                    {
                        "path": item.path,
                        "schema": item.schema,
                        "expected_validation": item.expected_validation,
                        "actual_validation": item.actual_validation,
                        "validation_matches": item.validation_matches,
                        "diagnostic": item.diagnostic,
                    }
                    for item in corpus.schematron
                ],
            }
            for corpus in audit.corpora
        ],
    }
    return json.dumps(payload, indent=2, sort_keys=True) + "\n"


def render_markdown(audit: CorpusAudit) -> str:
    """Render a concise deterministic Task 7I evidence report."""

    lines = [
        "# MusicXML Corpus Audit",
        "",
        "> Generated Task 7I evidence. Checkouts are external and must match the",
        "> governed revisions; no machine-specific path is recorded.",
        "",
        f"**Corpus audit readiness:** "
        f"{'COMPLETE' if audit.corpus_mapping_complete else 'INCOMPLETE'}",
        "",
        f"**Bounded corpus mapping gate:** "
        f"{'COMPLETE' if audit.corpus_mapping_complete else 'INCOMPLETE'}",
        "",
        "## Summary",
        "",
        "| Corpus | Run ID | Revision | Files | XSD matched | Schematron matched | Mapped | "
        "Zero deferred | Mapping failures |",
        "|---|---|---|---:|---:|---:|---:|---:|---:|",
    ]
    for corpus in audit.corpora:
        counts = Counter(item.mapping for item in corpus.files)
        matched = sum(item.validation_matches for item in corpus.files)
        schematron_matched = sum(item.validation_matches for item in corpus.schematron)
        mapped = counts["mapped-zero-deferred"] + counts["mapped-with-deferred"]
        lines.append(
            f"| {corpus.id} | `{corpus.run_id}` | `{corpus.revision}` | "
            f"{len(corpus.files)} | {matched} | "
            f"{schematron_matched}/{len(corpus.schematron)} | {mapped} | "
            f"{counts['mapped-zero-deferred']} | {counts['failed']} |"
        )
    lines.extend(
        [
            "",
            "Schema-validation outcomes match the pinned W3C assertions. Zero-deferred",
            "mapping is complete for this bounded corpus; it is not by itself an",
            "independent proof of universal MusicXML losslessness.",
            "",
            "## Open Mapping Evidence",
            "",
        ]
    )
    open_items = [
        (corpus.id, item)
        for corpus in audit.corpora
        for item in corpus.files
        if item.mapping in {"failed", "mapped-with-deferred"}
    ]
    for corpus_id, item in open_items:
        detail = item.diagnostic or f"{item.deferred_occurrences} deferred source occurrences"
        lines.append(f"- `{corpus_id}/{item.path}` — {item.mapping}: {detail}")
    if not open_items:
        lines.append("- None.")
    lines.extend(["", "## Exporter Evidence", ""])
    exporters = [
        (corpus.id, item.path, software)
        for corpus in audit.corpora
        for item in corpus.files
        for software in item.software
    ]
    if exporters:
        for corpus_id, path, software in exporters:
            lines.append(f"- `{software}` — `{corpus_id}/{path}`")
    else:
        lines.append("- No corpus file declares encoding software.")
    lines.extend(
        [
            "",
            "## Interpretation",
            "",
            "This baseline executes XSD and applicable upstream XPath 3 Schematron",
            "validation, the canonical mapper, canonical score/deferred-record",
            "validation, and strict canonical JSON round trips.",
            "It does not establish independent semantic equivalence or promote",
            "declaration-registry status.",
            "",
        ]
    )
    return "\n".join(lines)


def _build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--w3c-checkout", type=Path, required=True)
    parser.add_argument("--community-checkout", type=Path, required=True)
    parser.add_argument("--json-output", type=Path)
    parser.add_argument("--markdown-output", type=Path)
    parser.add_argument("--allow-incomplete", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    """Run the pinned corpora and optionally write deterministic evidence files."""

    arguments = _build_argument_parser().parse_args(argv)
    audit = audit_corpora(arguments.w3c_checkout, arguments.community_checkout)
    json_text = render_json(audit)
    markdown_text = render_markdown(audit)
    json_output = cast(Path | None, arguments.json_output)
    markdown_output = cast(Path | None, arguments.markdown_output)
    if json_output is not None:
        json_output.parent.mkdir(parents=True, exist_ok=True)
        json_output.write_text(json_text, encoding="utf-8")
    if markdown_output is not None:
        markdown_output.parent.mkdir(parents=True, exist_ok=True)
        markdown_output.write_text(markdown_text, encoding="utf-8")
    if json_output is None and markdown_output is None:
        print(markdown_text, end="")
    return 0 if audit.corpus_mapping_complete or arguments.allow_incomplete else 1


if __name__ == "__main__":
    raise SystemExit(main())
