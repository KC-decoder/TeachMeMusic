"""Tests for conservative declaration-evidence promotion."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from teachmemusic.score.musicxml.evidence_promotion import (
    EvidencePromotionError,
    promote_registry_evidence,
    render_registry,
)


def _registry() -> bytes:
    return json.dumps(
        {
            "format": "teachmemusic.musicxml.mapping-registry/1",
            "inventory_format": "teachmemusic.musicxml.inventory/1",
            "entries": [
                {
                    "component_key": "observed",
                    "corpus_evidence": [],
                    "losslessness_evidence": [],
                    "status": "implemented",
                },
                {
                    "component_key": "unobserved",
                    "corpus_evidence": [],
                    "losslessness_evidence": [],
                    "status": "implemented",
                },
            ],
        },
        indent=2,
    ).encode()


def _occurrence(registry: bytes) -> bytes:
    return json.dumps(
        {
            "format": "teachmemusic.musicxml.declaration-occurrences/1",
            "registry_sha256": hashlib.sha256(registry).hexdigest(),
            "declaration_count": 2,
            "runs": [{"run_id": "CORPUS-MXML-001"}],
            "observed_declarations": [
                {"component_key": "observed", "run_ids": ["CORPUS-MXML-001"]}
            ],
        }
    ).encode()


def test_promotion_uses_only_exact_occurrence_links() -> None:
    """TEST-MXML-PROMOTION-001: observation promotes only its exact declaration."""

    registry = _registry()
    result = promote_registry_evidence(registry, _occurrence(registry))
    entries = result.registry["entries"]

    assert result.corpus_promotions == 1
    assert result.losslessness_promotions == 0
    assert isinstance(entries, list)
    assert entries[0]["status"] == "corpus-verified"
    assert entries[0]["corpus_evidence"] == ["CORPUS-MXML-001"]
    assert entries[1]["status"] == "implemented"
    assert entries[1]["corpus_evidence"] == []

    lossless = promote_registry_evidence(
        registry,
        _occurrence(registry),
        linked_losslessness_evidence={
            "unobserved": frozenset({"TEST-MXML-LOSSLESS-001", "TEST-MXML-LOSSLESS-002"})
        },
    )
    lossless_entries = lossless.registry["entries"]
    assert lossless.losslessness_promotions == 1
    assert isinstance(lossless_entries, list)
    assert lossless_entries[1]["status"] == "losslessness-verified"
    assert lossless_entries[1]["corpus_evidence"] == []
    assert lossless_entries[1]["losslessness_evidence"] == [
        "TEST-MXML-LOSSLESS-001",
        "TEST-MXML-LOSSLESS-002",
    ]


def test_promotion_rejects_stale_or_ambiguous_claims() -> None:
    """TEST-MXML-PROMOTION-002: stale and noncanonical evidence fails closed."""

    registry = _registry()
    stale = json.loads(_occurrence(registry))
    stale["registry_sha256"] = "0" * 64
    with pytest.raises(EvidencePromotionError, match="does not match"):
        promote_registry_evidence(registry, json.dumps(stale).encode())

    duplicate_runs = json.loads(_occurrence(registry))
    duplicate_runs["observed_declarations"][0]["run_ids"] = [
        "CORPUS-MXML-001",
        "CORPUS-MXML-001",
    ]
    with pytest.raises(EvidencePromotionError, match="not canonical"):
        promote_registry_evidence(registry, json.dumps(duplicate_runs).encode())

    unsupported = json.loads(registry)
    unsupported["entries"][0]["status"] = "losslessness-verified"
    unsupported["entries"][0]["losslessness_evidence"] = ["TEST-MXML-EQUIVALENCE-001"]
    unsupported_bytes = json.dumps(unsupported).encode()
    with pytest.raises(EvidencePromotionError, match="independent declaration link"):
        promote_registry_evidence(unsupported_bytes, _occurrence(unsupported_bytes))

    unknown = {"not-a-declaration": frozenset({"TEST-MXML-LOSSLESS-001"})}
    with pytest.raises(EvidencePromotionError, match="unknown declaration"):
        promote_registry_evidence(
            registry,
            _occurrence(registry),
            linked_losslessness_evidence=unknown,
        )

    with pytest.raises(EvidencePromotionError, match="has no tests"):
        promote_registry_evidence(
            registry,
            _occurrence(registry),
            linked_losslessness_evidence={"unobserved": frozenset()},
        )


def test_real_promotion_is_exact_and_deterministic() -> None:
    """TEST-MXML-PROMOTION-003: governed evidence promotion is idempotent."""

    root = Path(__file__).resolve().parents[3]
    registry_path = root / "src/teachmemusic/score/musicxml/resources/mapping-registry.json"
    occurrence_path = root / "docs/generated/musicxml-declaration-occurrences.json"
    registry = registry_path.read_bytes()
    occurrence = occurrence_path.read_bytes()
    evidence_path = root / "docs/generated/musicxml-losslessness-evidence.json"
    evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
    links = {
        proof["component_key"]: frozenset(proof["positive_test_ids"] + proof["mutation_test_ids"])
        for proof in evidence["declarations"]
    }
    result = promote_registry_evidence(
        registry,
        occurrence,
        linked_losslessness_evidence=links,
    )
    rerendered = render_registry(result.registry).encode()

    assert result.corpus_promotions == 0
    assert result.losslessness_promotions == 0
    assert rerendered == registry
    entries = result.registry["entries"]
    assert isinstance(entries, list)
    assert sum(entry["status"] == "corpus-verified" for entry in entries) == 0
    assert sum(entry["status"] == "implemented" for entry in entries) == 0
    assert sum(entry["status"] == "losslessness-verified" for entry in entries) == 15_303
    assert all(
        entry["losslessness_evidence"]
        in (
            ["TEST-MXML-LOSSLESS-001", "TEST-MXML-LOSSLESS-002"],
            ["TEST-MXML-LOSSLESS-006", "TEST-MXML-LOSSLESS-007"],
            ["TEST-MXML-LOSSLESS-008", "TEST-MXML-LOSSLESS-009"],
            ["TEST-MXML-LOSSLESS-010", "TEST-MXML-LOSSLESS-011"],
            ["TEST-MXML-LOSSLESS-012", "TEST-MXML-LOSSLESS-013"],
            ["TEST-MXML-LOSSLESS-014", "TEST-MXML-LOSSLESS-015"],
            ["TEST-MXML-LOSSLESS-016", "TEST-MXML-LOSSLESS-017"],
            ["TEST-MXML-LOSSLESS-018", "TEST-MXML-LOSSLESS-019"],
            ["TEST-MXML-LOSSLESS-020", "TEST-MXML-LOSSLESS-021"],
            ["TEST-MXML-LOSSLESS-022", "TEST-MXML-LOSSLESS-023"],
            ["TEST-MXML-LOSSLESS-024", "TEST-MXML-LOSSLESS-025"],
            ["TEST-MXML-LOSSLESS-026", "TEST-MXML-LOSSLESS-027"],
            ["TEST-MXML-LOSSLESS-028", "TEST-MXML-LOSSLESS-029"],
            ["TEST-MXML-LOSSLESS-030", "TEST-MXML-LOSSLESS-031"],
            ["TEST-MXML-LOSSLESS-032", "TEST-MXML-LOSSLESS-033"],
            ["TEST-MXML-LOSSLESS-034", "TEST-MXML-LOSSLESS-035"],
            ["TEST-MXML-LOSSLESS-036", "TEST-MXML-LOSSLESS-037"],
            ["TEST-MXML-LOSSLESS-038", "TEST-MXML-LOSSLESS-039"],
            ["TEST-MXML-LOSSLESS-040", "TEST-MXML-LOSSLESS-041"],
            ["TEST-MXML-LOSSLESS-042", "TEST-MXML-LOSSLESS-043"],
            ["TEST-MXML-LOSSLESS-044", "TEST-MXML-LOSSLESS-045"],
            ["TEST-MXML-LOSSLESS-046", "TEST-MXML-LOSSLESS-047"],
            ["TEST-MXML-LOSSLESS-048", "TEST-MXML-LOSSLESS-049"],
            ["TEST-MXML-LOSSLESS-050", "TEST-MXML-LOSSLESS-051"],
            ["TEST-MXML-LOSSLESS-052", "TEST-MXML-LOSSLESS-053"],
            ["TEST-MXML-LOSSLESS-054", "TEST-MXML-LOSSLESS-055"],
        )
        for entry in entries
        if entry["status"] == "losslessness-verified"
    )
