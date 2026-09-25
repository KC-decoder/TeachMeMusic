"""Apply declaration evidence only from exact governed links."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections.abc import Mapping
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from typing import cast

from .corpus_occurrence import OCCURRENCE_INDEX_FORMAT
from .coverage import REGISTRY_FORMAT, STATUS_ORDER, discover_test_ids
from .losslessness_contract import load_losslessness_links
from .standards import resource_root


class EvidencePromotionError(ValueError):
    """Raised when evidence cannot safely promote the registry."""


@dataclass(frozen=True, slots=True)
class EvidencePromotionResult:
    """Deterministic registry output and its conservative promotion counts."""

    registry: dict[str, object]
    corpus_promotions: int
    losslessness_promotions: int


def promote_registry_evidence(
    registry_bytes: bytes,
    occurrence_bytes: bytes,
    *,
    linked_losslessness_evidence: Mapping[str, frozenset[str]] | None = None,
) -> EvidencePromotionResult:
    """Promote only exact corpus observations and independent proof links."""

    registry = _json_object(registry_bytes, "mapping registry")
    occurrence = _json_object(occurrence_bytes, "occurrence index")
    if registry.get("format") != REGISTRY_FORMAT:
        raise EvidencePromotionError("unsupported mapping-registry format")
    if occurrence.get("format") != OCCURRENCE_INDEX_FORMAT:
        raise EvidencePromotionError("unsupported occurrence-index format")
    registry_digest = hashlib.sha256(registry_bytes).hexdigest()
    if occurrence.get("registry_sha256") != registry_digest:
        raise EvidencePromotionError("occurrence index does not match the input registry")

    raw_runs = occurrence.get("runs")
    if not isinstance(raw_runs, list):
        raise EvidencePromotionError("occurrence index has no governed runs")
    governed_runs = {
        run.get("run_id")
        for run in raw_runs
        if isinstance(run, dict) and isinstance(run.get("run_id"), str)
    }
    if not governed_runs:
        raise EvidencePromotionError("occurrence index has no governed run IDs")

    observed = _observed_links(occurrence, governed_runs)
    promoted = deepcopy(registry)
    raw_entries = promoted.get("entries")
    if not isinstance(raw_entries, list):
        raise EvidencePromotionError("mapping registry has no entries")
    declaration_count = occurrence.get("declaration_count")
    if declaration_count != len(raw_entries):
        raise EvidencePromotionError("occurrence index declaration count is stale")

    registry_keys = {
        entry.get("component_key")
        for entry in raw_entries
        if isinstance(entry, dict) and isinstance(entry.get("component_key"), str)
    }
    unknown = sorted(observed.keys() - registry_keys)
    if unknown:
        raise EvidencePromotionError(f"occurrence index names unknown declaration {unknown[0]}")
    losslessness_links = linked_losslessness_evidence or {}
    unknown = sorted(losslessness_links.keys() - registry_keys)
    if unknown:
        raise EvidencePromotionError(
            f"losslessness evidence names unknown declaration {unknown[0]}"
        )

    corpus_promotions = 0
    losslessness_promotions = 0
    for raw_entry in raw_entries:
        if not isinstance(raw_entry, dict):
            raise EvidencePromotionError("mapping registry contains a non-object entry")
        entry = cast(dict[str, object], raw_entry)
        key = entry.get("component_key")
        status = entry.get("status")
        if not isinstance(key, str) or not isinstance(status, str) or status not in STATUS_ORDER:
            raise EvidencePromotionError("mapping registry contains an invalid entry")
        rank = STATUS_ORDER.index(status)
        if rank < STATUS_ORDER.index("implemented"):
            raise EvidencePromotionError(f"declaration is not implemented: {key}")
        losslessness_ids = losslessness_links.get(key)
        existing_losslessness = entry.get("losslessness_evidence")
        if not isinstance(existing_losslessness, list):
            raise EvidencePromotionError(f"invalid losslessness evidence list: {key}")
        if losslessness_ids is None and (
            status == "losslessness-verified" or existing_losslessness
        ):
            raise EvidencePromotionError(
                f"losslessness requires an independent declaration link: {key}"
            )
        if losslessness_ids is not None:
            if not losslessness_ids:
                raise EvidencePromotionError(f"losslessness link has no tests: {key}")
            expected_losslessness = sorted(losslessness_ids)
            if status == "losslessness-verified":
                if existing_losslessness != expected_losslessness:
                    raise EvidencePromotionError(
                        f"losslessness evidence is not canonical for {key}"
                    )
            else:
                entry["losslessness_evidence"] = expected_losslessness
                entry["status"] = "losslessness-verified"
                status = "losslessness-verified"
                losslessness_promotions += 1
        run_ids = observed.get(key)
        if run_ids is None:
            if status == "corpus-verified" or entry.get("corpus_evidence"):
                raise EvidencePromotionError(
                    f"unobserved declaration claims corpus evidence: {key}"
                )
            continue
        entry["corpus_evidence"] = list(run_ids)
        if status == "implemented":
            entry["status"] = "corpus-verified"
            corpus_promotions += 1

    return EvidencePromotionResult(
        registry=promoted,
        corpus_promotions=corpus_promotions,
        losslessness_promotions=losslessness_promotions,
    )


def render_registry(registry: dict[str, object]) -> str:
    """Serialize a promoted registry deterministically."""

    return json.dumps(registry, indent=2) + "\n"


def _json_object(data: bytes, label: str) -> dict[str, object]:
    value = json.loads(data)
    if not isinstance(value, dict):
        raise EvidencePromotionError(f"{label} is not a JSON object")
    return cast(dict[str, object], value)


def _observed_links(
    occurrence: dict[str, object],
    governed_runs: set[object],
) -> dict[str, tuple[str, ...]]:
    raw_observed = occurrence.get("observed_declarations")
    if not isinstance(raw_observed, list):
        raise EvidencePromotionError("occurrence index has no observed declarations")
    links: dict[str, tuple[str, ...]] = {}
    for raw_item in raw_observed:
        if not isinstance(raw_item, dict):
            raise EvidencePromotionError("occurrence index contains a non-object observation")
        key = raw_item.get("component_key")
        run_ids = raw_item.get("run_ids")
        if (
            not isinstance(key, str)
            or not isinstance(run_ids, list)
            or not run_ids
            or not all(isinstance(run_id, str) for run_id in run_ids)
        ):
            raise EvidencePromotionError("occurrence index contains an invalid observation")
        if key in links:
            raise EvidencePromotionError(f"occurrence index repeats declaration {key}")
        typed_run_ids = tuple(cast(list[str], run_ids))
        if tuple(sorted(set(typed_run_ids))) != typed_run_ids:
            raise EvidencePromotionError(f"observation run IDs are not canonical for {key}")
        if not set(typed_run_ids) <= governed_runs:
            raise EvidencePromotionError(f"observation cites an unknown governed run for {key}")
        links[key] = typed_run_ids
    return links


def _build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--registry", type=Path)
    parser.add_argument("--occurrences", type=Path)
    parser.add_argument("--inventory", type=Path)
    parser.add_argument("--losslessness-evidence", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    """Write a conservatively promoted registry and report exact counts."""

    arguments = _build_argument_parser().parse_args(argv)
    repository_root = Path(__file__).resolve().parents[4]
    registry_path = (
        cast(Path | None, arguments.registry) or resource_root() / "mapping-registry.json"
    )
    occurrence_path = (
        cast(Path | None, arguments.occurrences)
        or repository_root / "docs/generated/musicxml-declaration-occurrences.json"
    )
    inventory_path = cast(Path | None, arguments.inventory) or resource_root() / "inventory.json"
    losslessness_path = (
        cast(Path | None, arguments.losslessness_evidence)
        or repository_root / "docs/generated/musicxml-losslessness-evidence.json"
    )
    result = promote_registry_evidence(
        registry_path.read_bytes(),
        occurrence_path.read_bytes(),
        linked_losslessness_evidence=load_losslessness_links(
            losslessness_path,
            inventory_path,
            registry_path,
            known_test_ids=discover_test_ids(repository_root / "tests"),
        ),
    )
    output = cast(Path, arguments.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(render_registry(result.registry), encoding="utf-8")
    print(
        f"wrote {output}: {result.corpus_promotions} corpus promotions, "
        f"{result.losslessness_promotions} losslessness promotions"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
