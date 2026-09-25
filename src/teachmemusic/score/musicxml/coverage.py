"""Evaluate MusicXML declaration mappings against executable evidence."""

from __future__ import annotations

import argparse
import hashlib
import importlib
import json
import re
from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import cast

from .corpus import load_corpus_definitions
from .corpus_occurrence import OCCURRENCE_INDEX_FORMAT
from .inventory import INVENTORY_FORMAT
from .losslessness_contract import load_losslessness_links
from .standards import resource_root
from .taxonomy import DISPOSITIONS, FEATURE_FAMILIES

REGISTRY_FORMAT = "teachmemusic.musicxml.mapping-registry/1"
STATUS_ORDER = (
    "inventoried",
    "mapped",
    "implemented",
    "corpus-verified",
    "losslessness-verified",
)
TEST_ID_PATTERN = re.compile(r"\bTEST-MXML-[A-Z0-9-]+\b")


@dataclass(frozen=True, slots=True)
class CoverageIssue:
    """One reproducible mismatch between declarations, mappings, and evidence."""

    code: str
    component_key: str
    detail: str


@dataclass(frozen=True, slots=True)
class CoverageResult:
    """Complete result for one inventory/registry comparison."""

    component_count: int
    registered_count: int
    status_counts: tuple[tuple[str, int], ...]
    issues: tuple[CoverageIssue, ...]

    @property
    def complete(self) -> bool:
        """Return whether every declaration has losslessness evidence and no errors."""

        return not self.issues and dict(self.status_counts).get("losslessness-verified", 0) == (
            self.component_count
        )


def _load_json(path: Path) -> dict[str, object]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object in {path}")
    return cast(dict[str, object], value)


def discover_test_ids(test_root: Path) -> frozenset[str]:
    """Extract stable MusicXML test IDs from repository Python tests."""

    found: set[str] = set()
    for path in sorted(test_root.rglob("test_*.py")):
        found.update(TEST_ID_PATTERN.findall(path.read_text(encoding="utf-8")))
    return frozenset(found)


def load_corpus_observations(
    occurrence_path: Path,
    registry_path: Path,
) -> dict[str, frozenset[str]]:
    """Load declaration-to-run links only from a current governed index."""

    occurrence = _load_json(occurrence_path)
    if occurrence.get("format") != OCCURRENCE_INDEX_FORMAT:
        raise ValueError(f"unsupported occurrence-index format in {occurrence_path}")
    registry_digest = hashlib.sha256(registry_path.read_bytes()).hexdigest()
    if occurrence.get("registry_sha256") != registry_digest:
        raise ValueError(
            "occurrence index does not describe the current mapping registry; "
            "regenerate it before evaluating promoted evidence"
        )
    registry = _load_json(registry_path)
    registry_keys = {
        entry.get("component_key")
        for entry in _object_list(registry, "entries")
        if isinstance(entry.get("component_key"), str)
    }
    if occurrence.get("declaration_count") != len(registry_keys):
        raise ValueError("occurrence index declaration count is stale")
    run_ids = {
        run.get("run_id")
        for run in _object_list(occurrence, "runs")
        if isinstance(run.get("run_id"), str)
    }
    observations: dict[str, frozenset[str]] = {}
    for declaration in _object_list(occurrence, "observed_declarations"):
        key = declaration.get("component_key")
        linked_runs = _text_list(declaration, "run_ids")
        if not isinstance(key, str) or not key or not linked_runs:
            raise ValueError("occurrence index contains an invalid observed declaration")
        if key in observations:
            raise ValueError(f"occurrence index repeats declaration {key}")
        if key not in registry_keys:
            raise ValueError(f"occurrence index names unknown declaration {key}")
        if not set(linked_runs) <= run_ids:
            raise ValueError(f"occurrence index cites an unknown run for {key}")
        observations[key] = frozenset(linked_runs)
    return observations


def _object_list(document: dict[str, object], key: str) -> tuple[dict[str, object], ...]:
    value = document.get(key)
    if not isinstance(value, list):
        return ()
    return tuple(cast(dict[str, object], item) for item in value if isinstance(item, dict))


def _text_list(document: dict[str, object], key: str) -> tuple[str, ...]:
    value = document.get(key)
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        return ()
    return tuple(cast(list[str], value))


def _import_path_exists(path: str) -> bool:
    module_name, separator, attribute_path = path.partition(":")
    if not separator or not module_name or not attribute_path:
        return False
    try:
        value: object = importlib.import_module(module_name)
        for name in attribute_path.split("."):
            value = getattr(value, name)
    except (AttributeError, ImportError):
        return False
    return True


def evaluate_coverage(
    inventory: dict[str, object],
    registry: dict[str, object],
    *,
    known_test_ids: frozenset[str] = frozenset(),
    known_corpus_ids: frozenset[str] = frozenset(),
    observed_corpus_evidence: Mapping[str, frozenset[str]] | None = None,
    linked_losslessness_evidence: Mapping[str, frozenset[str]] | None = None,
    existing_imports: frozenset[str] | None = None,
) -> CoverageResult:
    """Join standards declarations to mappings and enforce evidence status rules."""

    issues: list[CoverageIssue] = []
    if inventory.get("format") != INVENTORY_FORMAT:
        issues.append(CoverageIssue("inventory-format", "<inventory>", "unsupported format"))
    if registry.get("format") != REGISTRY_FORMAT:
        issues.append(CoverageIssue("registry-format", "<registry>", "unsupported format"))
    if registry.get("inventory_format") != INVENTORY_FORMAT:
        issues.append(
            CoverageIssue(
                "registry-inventory-format",
                "<registry>",
                "registry targets a different inventory format",
            )
        )

    components = _object_list(inventory, "components")
    inventory_index: dict[str, dict[str, object]] = {}
    for component in components:
        key = component.get("key")
        if not isinstance(key, str) or not key:
            issues.append(
                CoverageIssue("component-key", "<inventory>", "component has no stable key")
            )
            continue
        if key in inventory_index:
            issues.append(CoverageIssue("component-duplicate", key, "inventory key is duplicated"))
        inventory_index[key] = component

    entries = _object_list(registry, "entries")
    registry_index: dict[str, dict[str, object]] = {}
    status_counts: Counter[str] = Counter()
    for entry in entries:
        key = entry.get("component_key")
        if not isinstance(key, str) or not key:
            issues.append(CoverageIssue("registry-key", "<registry>", "entry has no component key"))
            continue
        if key in registry_index:
            issues.append(CoverageIssue("registry-duplicate", key, "registry key is duplicated"))
        registry_index[key] = entry
        status = entry.get("status")
        if isinstance(status, str):
            status_counts[status] += 1

    for key in sorted(inventory_index.keys() - registry_index.keys()):
        issues.append(CoverageIssue("mapping-missing", key, "standard declaration is unregistered"))
    for key in sorted(registry_index.keys() - inventory_index.keys()):
        issues.append(
            CoverageIssue("mapping-stale", key, "registry declaration is not in inventory")
        )

    for key in sorted(registry_index.keys() & inventory_index.keys()):
        _evaluate_entry(
            key,
            inventory_index[key],
            registry_index[key],
            known_test_ids,
            known_corpus_ids,
            observed_corpus_evidence or {},
            linked_losslessness_evidence or {},
            existing_imports,
            issues,
        )

    return CoverageResult(
        component_count=len(inventory_index),
        registered_count=len(registry_index),
        status_counts=tuple(sorted(status_counts.items())),
        issues=tuple(sorted(issues, key=lambda item: (item.code, item.component_key, item.detail))),
    )


def _evaluate_entry(
    key: str,
    component: dict[str, object],
    entry: dict[str, object],
    known_test_ids: frozenset[str],
    known_corpus_ids: frozenset[str],
    observed_corpus_evidence: Mapping[str, frozenset[str]],
    linked_losslessness_evidence: Mapping[str, frozenset[str]],
    existing_imports: frozenset[str] | None,
    issues: list[CoverageIssue],
) -> None:
    status = entry.get("status")
    if not isinstance(status, str) or status not in STATUS_ORDER:
        issues.append(CoverageIssue("status-invalid", key, "unknown evidence status"))
        return
    rank = STATUS_ORDER.index(status)
    component_version = component.get("version")
    if component_version not in _text_list(entry, "versions"):
        issues.append(CoverageIssue("version-missing", key, "component version is not registered"))

    if rank >= STATUS_ORDER.index("mapped"):
        family = entry.get("family")
        if not isinstance(family, str) or not family or family == "unclassified":
            issues.append(CoverageIssue("family-unclassified", key, "mapped item needs a family"))
        elif family.casefold() not in FEATURE_FAMILIES:
            issues.append(
                CoverageIssue(
                    "family-invalid",
                    key,
                    f"family is outside the approved 26-family taxonomy: {family}",
                )
            )
        disposition = entry.get("disposition")
        if disposition not in DISPOSITIONS:
            issues.append(
                CoverageIssue("disposition-invalid", key, "mapped item needs a disposition")
            )
        source_policy = entry.get("source_policy")
        if not isinstance(source_policy, str) or not source_policy.strip():
            issues.append(
                CoverageIssue("source-policy-missing", key, "mapped item needs source policy")
            )
        targets = _text_list(entry, "canonical_targets")
        if disposition in {"canonical", "package"} and not targets:
            issues.append(
                CoverageIssue("target-missing", key, "mapped item needs canonical target")
            )

    if rank >= STATUS_ORDER.index("implemented"):
        handler = entry.get("handler")
        if not isinstance(handler, str) or not _path_exists(handler, existing_imports):
            issues.append(
                CoverageIssue("handler-missing", key, "implemented handler does not exist")
            )
        for target in _text_list(entry, "canonical_targets"):
            if not _path_exists(target, existing_imports):
                issues.append(
                    CoverageIssue(
                        "target-missing",
                        key,
                        f"canonical target does not exist: {target}",
                    )
                )
        _require_tests(key, "positive_tests", entry, known_test_ids, issues)
        _require_tests(key, "negative_tests", entry, known_test_ids, issues)

    corpus_evidence = _text_list(entry, "corpus_evidence")
    if status == "corpus-verified" or (status == "losslessness-verified" and corpus_evidence):
        if status == "corpus-verified" and not corpus_evidence:
            issues.append(CoverageIssue("corpus-evidence-missing", key, "no corpus evidence"))
        for corpus_id in corpus_evidence:
            if corpus_id not in known_corpus_ids:
                issues.append(
                    CoverageIssue(
                        "corpus-id-unknown",
                        key,
                        f"unknown governed corpus run ID: {corpus_id}",
                    )
                )
        observed_runs = observed_corpus_evidence.get(key, frozenset())
        for corpus_id in corpus_evidence:
            if corpus_id not in observed_runs:
                issues.append(
                    CoverageIssue(
                        "corpus-evidence-unlinked",
                        key,
                        f"occurrence index does not link run {corpus_id}",
                    )
                )
        for corpus_id in sorted(observed_runs.difference(corpus_evidence)):
            issues.append(
                CoverageIssue(
                    "corpus-evidence-omitted",
                    key,
                    f"registry omits directly observed run {corpus_id}",
                )
            )
    if rank >= STATUS_ORDER.index("losslessness-verified"):
        losslessness_evidence = _text_list(entry, "losslessness_evidence")
        if not losslessness_evidence:
            issues.append(
                CoverageIssue("losslessness-evidence-missing", key, "no lossless evidence")
            )
        for test_id in losslessness_evidence:
            if test_id not in known_test_ids:
                issues.append(
                    CoverageIssue(
                        "test-id-unknown",
                        key,
                        f"unknown losslessness test ID: {test_id}",
                    )
                )
        linked_tests = linked_losslessness_evidence.get(key, frozenset())
        for test_id in losslessness_evidence:
            if test_id not in linked_tests:
                issues.append(
                    CoverageIssue(
                        "losslessness-evidence-unlinked",
                        key,
                        f"independent evidence does not link test {test_id}",
                    )
                )


def _path_exists(path: str, existing_imports: frozenset[str] | None) -> bool:
    return path in existing_imports if existing_imports is not None else _import_path_exists(path)


def _require_tests(
    key: str,
    field: str,
    entry: dict[str, object],
    known_test_ids: frozenset[str],
    issues: list[CoverageIssue],
) -> None:
    test_ids = _text_list(entry, field)
    if not test_ids:
        issues.append(CoverageIssue("test-evidence-missing", key, f"{field} is empty"))
    for test_id in test_ids:
        if test_id not in known_test_ids:
            issues.append(CoverageIssue("test-id-unknown", key, f"unknown test ID: {test_id}"))


def render_markdown(result: CoverageResult, *, issue_limit: int = 50) -> str:
    """Render a compact, deterministic human-readable coverage report."""

    issue_counts = Counter(issue.code for issue in result.issues)
    lines = [
        "# MusicXML Conformance Coverage",
        "",
        "> Generated artifact. Sources of truth are the pinned standards manifest,",
        "> declaration inventory, mapping registry, and executable tests.",
        "",
        f"**Readiness:** {'COMPLETE' if result.complete else 'INCOMPLETE'}",
        "",
        "## Summary",
        "",
        f"- Standards declarations: {result.component_count}",
        f"- Registry entries: {result.registered_count}",
        f"- Coverage issues: {len(result.issues)}",
        "",
        "## Mapping Status",
        "",
        "| Status | Entries |",
        "|---|---:|",
    ]
    status_values = dict(result.status_counts)
    lines.extend(f"| {status} | {status_values.get(status, 0)} |" for status in STATUS_ORDER)
    lines.extend(
        [
            "",
            "## Issue Summary",
            "",
            "| Code | Count |",
            "|---|---:|",
        ]
    )
    lines.extend(f"| `{code}` | {count} |" for code, count in sorted(issue_counts.items()))
    lines.extend(["", f"## First {min(issue_limit, len(result.issues))} Issues", ""])
    for issue in result.issues[:issue_limit]:
        lines.append(f"- `{issue.code}` — `{issue.component_key}` — {issue.detail}")
    if len(result.issues) > issue_limit:
        lines.append(f"- … {len(result.issues) - issue_limit} additional issues omitted")
    interpretation = (
        [
            "Every inventoried declaration has directly linked losslessness evidence.",
            "This satisfies the declaration-coverage gate; increment closure still follows "
            "governance.",
        ]
        if result.complete
        else [
            "An incomplete result is expected during staged MusicXML implementation.",
            "Mapped entries do not by themselves prove full parser or canonical-schema support.",
        ]
    )
    lines.extend(["", "## Interpretation", "", *interpretation, ""])
    return "\n".join(lines)


def _build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inventory", type=Path)
    parser.add_argument("--registry", type=Path)
    parser.add_argument("--tests", type=Path)
    parser.add_argument("--occurrences", type=Path)
    parser.add_argument("--losslessness-evidence", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--allow-incomplete", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    """Generate the report and fail strict mode while evidence remains incomplete."""

    arguments = _build_argument_parser().parse_args(argv)
    resources = resource_root()
    inventory_path = cast(Path | None, arguments.inventory) or resources / "inventory.json"
    registry_path = cast(Path | None, arguments.registry) or resources / "mapping-registry.json"
    repository_root = Path(__file__).resolve().parents[4]
    test_root = cast(Path | None, arguments.tests) or repository_root / "tests"
    occurrence_path = (
        cast(Path | None, arguments.occurrences)
        or repository_root / "docs/generated/musicxml-declaration-occurrences.json"
    )
    losslessness_path = (
        cast(Path | None, arguments.losslessness_evidence)
        or repository_root / "docs/generated/musicxml-losslessness-evidence.json"
    )
    known_test_ids = discover_test_ids(test_root)
    result = evaluate_coverage(
        _load_json(inventory_path),
        _load_json(registry_path),
        known_test_ids=known_test_ids,
        known_corpus_ids=frozenset(definition.run_id for definition in load_corpus_definitions()),
        observed_corpus_evidence=load_corpus_observations(
            occurrence_path,
            registry_path,
        ),
        linked_losslessness_evidence=load_losslessness_links(
            losslessness_path,
            inventory_path,
            registry_path,
            known_test_ids=known_test_ids,
        ),
    )
    rendered = render_markdown(result)
    output = cast(Path | None, arguments.output)
    if output is None:
        print(rendered, end="")
    else:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(rendered, encoding="utf-8")
        print(f"wrote {output}")
    return 0 if result.complete or arguments.allow_incomplete else 1


if __name__ == "__main__":
    raise SystemExit(main())
