"""Tests proving the MusicXML coverage harness fails closed."""

from __future__ import annotations

import json
from pathlib import Path
from typing import cast

from teachmemusic.score.musicxml.coverage import (
    discover_test_ids,
    evaluate_coverage,
    load_corpus_observations,
    render_markdown,
)
from teachmemusic.score.musicxml.losslessness_contract import load_losslessness_links
from teachmemusic.score.musicxml.standards import resource_root

COMPONENT_KEY = "musicxml:test:xsd:schema/example.xsd:xsd-element:/schema/element"


def _inventory() -> dict[str, object]:
    return {
        "format": "teachmemusic.musicxml.inventory/1",
        "components": [
            {
                "key": COMPONENT_KEY,
                "version": "test",
                "kind": "xsd-element",
            }
        ],
    }


def _entry(status: str = "inventoried") -> dict[str, object]:
    return {
        "component_key": COMPONENT_KEY,
        "versions": ["test"],
        "family": "document identity and versions",
        "disposition": "canonical",
        "canonical_targets": ["example.models:Example"],
        "handler": "example.handlers:map_example",
        "source_policy": "Preserve explicit source state.",
        "positive_tests": ["TEST-MXML-MAP-001"],
        "negative_tests": ["TEST-MXML-MAP-002"],
        "corpus_evidence": ["CORPUS-EXAMPLE"],
        "losslessness_evidence": ["TEST-MXML-ROUNDTRIP-001"],
        "status": status,
    }


def _registry(*entries: dict[str, object]) -> dict[str, object]:
    return {
        "format": "teachmemusic.musicxml.mapping-registry/1",
        "inventory_format": "teachmemusic.musicxml.inventory/1",
        "entries": list(entries),
    }


def test_empty_registry_exposes_every_missing_declaration() -> None:
    """TEST-MXML-INVENTORY-009: empty coverage fails instead of appearing green."""

    result = evaluate_coverage(_inventory(), _registry())
    assert not result.complete
    assert [(issue.code, issue.component_key) for issue in result.issues] == [
        ("mapping-missing", COMPONENT_KEY)
    ]


def test_stale_registry_entry_is_rejected() -> None:
    """TEST-MXML-INVENTORY-010: registry entries cannot outlive declarations."""

    stale = _entry()
    stale["component_key"] = "musicxml:test:stale"
    result = evaluate_coverage(_inventory(), _registry(stale))
    assert {issue.code for issue in result.issues} == {"mapping-missing", "mapping-stale"}


def test_implemented_status_requires_real_handler_targets_and_tests() -> None:
    """TEST-MXML-INVENTORY-011: unsupported evidence cannot inflate status."""

    result = evaluate_coverage(
        _inventory(),
        _registry(_entry("implemented")),
        known_test_ids=frozenset(),
        existing_imports=frozenset(),
    )
    assert {issue.code for issue in result.issues} == {
        "handler-missing",
        "target-missing",
        "test-id-unknown",
    }


def test_verified_status_requires_direct_losslessness_evidence() -> None:
    """TEST-MXML-INVENTORY-012: final evidence cannot be asserted empty."""

    entry = _entry("losslessness-verified")
    entry["corpus_evidence"] = []
    entry["losslessness_evidence"] = []
    result = evaluate_coverage(
        _inventory(),
        _registry(entry),
        known_test_ids=frozenset({"TEST-MXML-MAP-001", "TEST-MXML-MAP-002"}),
        known_corpus_ids=frozenset({"CORPUS-EXAMPLE"}),
        existing_imports=frozenset({"example.models:Example", "example.handlers:map_example"}),
    )
    assert {issue.code for issue in result.issues} == {"losslessness-evidence-missing"}


def test_fully_evidenced_synthetic_component_can_close() -> None:
    """TEST-MXML-INVENTORY-013: the harness has a genuine complete state."""

    result = evaluate_coverage(
        _inventory(),
        _registry(_entry("losslessness-verified")),
        known_test_ids=frozenset(
            {"TEST-MXML-MAP-001", "TEST-MXML-MAP-002", "TEST-MXML-ROUNDTRIP-001"}
        ),
        known_corpus_ids=frozenset({"CORPUS-EXAMPLE"}),
        observed_corpus_evidence={COMPONENT_KEY: frozenset({"CORPUS-EXAMPLE"})},
        linked_losslessness_evidence={COMPONENT_KEY: frozenset({"TEST-MXML-ROUNDTRIP-001"})},
        existing_imports=frozenset({"example.models:Example", "example.handlers:map_example"}),
    )
    assert result.complete
    assert result.issues == ()

    direct = _entry("losslessness-verified")
    direct["corpus_evidence"] = []
    result = evaluate_coverage(
        _inventory(),
        _registry(direct),
        known_test_ids=frozenset(
            {"TEST-MXML-MAP-001", "TEST-MXML-MAP-002", "TEST-MXML-ROUNDTRIP-001"}
        ),
        linked_losslessness_evidence={COMPONENT_KEY: frozenset({"TEST-MXML-ROUNDTRIP-001"})},
        existing_imports=frozenset({"example.models:Example", "example.handlers:map_example"}),
    )
    assert result.complete
    assert result.issues == ()


def test_losslessness_status_rejects_unknown_evidence_id() -> None:
    """TEST-MXML-INVENTORY-016: losslessness evidence must name a real test."""

    entry = _entry("losslessness-verified")
    entry["losslessness_evidence"] = ["TEST-MXML-NOT-REAL"]
    result = evaluate_coverage(
        _inventory(),
        _registry(entry),
        known_test_ids=frozenset({"TEST-MXML-MAP-001", "TEST-MXML-MAP-002"}),
        known_corpus_ids=frozenset({"CORPUS-EXAMPLE"}),
        observed_corpus_evidence={COMPONENT_KEY: frozenset({"CORPUS-EXAMPLE"})},
        linked_losslessness_evidence={COMPONENT_KEY: frozenset({"TEST-MXML-NOT-REAL"})},
        existing_imports=frozenset({"example.models:Example", "example.handlers:map_example"}),
    )
    assert [(issue.code, issue.detail) for issue in result.issues] == [
        ("test-id-unknown", "unknown losslessness test ID: TEST-MXML-NOT-REAL")
    ]


def test_corpus_status_rejects_unknown_run_id() -> None:
    """TEST-MXML-INVENTORY-017: corpus evidence must name a governed run."""

    entry = _entry("corpus-verified")
    entry["corpus_evidence"] = ["CORPUS-NOT-GOVERNED"]
    result = evaluate_coverage(
        _inventory(),
        _registry(entry),
        known_test_ids=frozenset({"TEST-MXML-MAP-001", "TEST-MXML-MAP-002"}),
        known_corpus_ids=frozenset({"CORPUS-EXAMPLE"}),
        observed_corpus_evidence={COMPONENT_KEY: frozenset({"CORPUS-NOT-GOVERNED"})},
        existing_imports=frozenset({"example.models:Example", "example.handlers:map_example"}),
    )
    assert [(issue.code, issue.detail) for issue in result.issues] == [
        ("corpus-id-unknown", "unknown governed corpus run ID: CORPUS-NOT-GOVERNED")
    ]


def test_real_mapping_report_uses_approved_taxonomy_without_inflating_status() -> None:
    """TEST-MXML-INVENTORY-014: valid taxonomy does not imply losslessness."""

    root = resource_root()
    inventory_value = json.loads((root / "inventory.json").read_text(encoding="utf-8"))
    registry_value = json.loads((root / "mapping-registry.json").read_text(encoding="utf-8"))
    occurrence_path = Path("docs/generated/musicxml-declaration-occurrences.json")
    assert isinstance(inventory_value, dict)
    assert isinstance(registry_value, dict)
    result = evaluate_coverage(
        cast(dict[str, object], inventory_value),
        cast(dict[str, object], registry_value),
        known_test_ids=discover_test_ids(Path("tests")),
        known_corpus_ids=frozenset({"CORPUS-MXML-001", "CORPUS-MXML-002"}),
        observed_corpus_evidence=load_corpus_observations(
            occurrence_path,
            root / "mapping-registry.json",
        ),
        linked_losslessness_evidence=load_losslessness_links(
            Path("docs/generated/musicxml-losslessness-evidence.json"),
            root / "inventory.json",
            root / "mapping-registry.json",
            known_test_ids=discover_test_ids(Path("tests")),
        ),
    )
    assert result.complete
    assert result.component_count == 15_303
    assert result.registered_count == 15_303
    assert dict(result.status_counts) == {"losslessness-verified": 15_303}
    assert result.issues == ()
    assert "Every inventoried declaration has directly linked losslessness evidence." in (
        render_markdown(result)
    )


def test_verified_status_rejects_evidence_not_linked_to_declaration() -> None:
    """TEST-MXML-INVENTORY-018: known IDs alone cannot support promotion."""

    result = evaluate_coverage(
        _inventory(),
        _registry(_entry("losslessness-verified")),
        known_test_ids=frozenset(
            {"TEST-MXML-MAP-001", "TEST-MXML-MAP-002", "TEST-MXML-ROUNDTRIP-001"}
        ),
        known_corpus_ids=frozenset({"CORPUS-EXAMPLE"}),
        existing_imports=frozenset({"example.models:Example", "example.handlers:map_example"}),
    )
    assert {issue.code for issue in result.issues} == {
        "corpus-evidence-unlinked",
        "losslessness-evidence-unlinked",
    }


def test_markdown_report_is_deterministic() -> None:
    """TEST-MXML-INVENTORY-015: repeated reports are byte-for-byte stable."""

    result = evaluate_coverage(_inventory(), _registry())
    first = render_markdown(result)
    second = render_markdown(result)
    assert first == second
    assert "**Readiness:** INCOMPLETE" in first
    assert "mapping-missing" in first
    assert "Mapped entries do not by themselves prove" in first
    assert Path(__file__).is_file()
