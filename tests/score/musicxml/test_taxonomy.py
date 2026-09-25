"""Tests for deterministic MusicXML feature-family classification."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import cast

from teachmemusic.score.musicxml.standards import resource_root
from teachmemusic.score.musicxml.taxonomy import (
    DISPOSITIONS,
    FEATURE_FAMILIES,
    TaxonomyAssignment,
    classify_declaration,
    reclassify_registry,
)


def _load(path: Path) -> dict[str, object]:
    value = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return cast(dict[str, object], value)


def test_source_context_separates_package_and_boundary_declarations() -> None:
    """TEST-MXML-TAXONOMY-001: source context controls non-canonical storage."""

    container = {
        "version": "4.0",
        "source_file": "schema/container.xsd",
        "kind": "xsd-element",
        "name": "rootfile",
        "path": "/xs:schema/xs:element",
    }
    imported_schema = {
        "version": "4.0",
        "source_file": "schema/musicxml.xsd",
        "kind": "xsd-import",
        "name": "<anonymous>",
        "path": "/xs:schema/xs:import",
    }
    entry = {
        "family": "Task 7H package and XML auxiliary infrastructure",
        "handler": "teachmemusic.score.musicxml.boundary:validate_musicxml_source",
    }

    assert classify_declaration(container, entry) == TaxonomyAssignment(
        family="mxl packaging",
        disposition="package",
    )
    assert classify_declaration(imported_schema, entry) == TaxonomyAssignment(
        family="document identity and versions",
        disposition="boundary-control",
    )


def test_timewise_41_root_is_supported_deprecated_standard() -> None:
    """TEST-MXML-TAXONOMY-002: 4.1 timewise is not mistaken for an extension."""

    component = {
        "version": "4.1-draft",
        "source_file": "schema/musicxml.xsd",
        "kind": "xsd-element",
        "name": "score-timewise",
        "path": "/xs:schema/xs:element[2]",
    }
    entry = {
        "family": "score structure",
        "handler": "teachmemusic.score.musicxml.temporal:map_temporal_score",
    }
    assert classify_declaration(component, entry) == TaxonomyAssignment(
        family="document identity and versions",
        disposition="standard-deprecated",
    )


def test_real_registry_uses_exact_taxonomy_and_audited_dispositions() -> None:
    """TEST-MXML-TAXONOMY-003: every declaration has one approved classification."""

    root = resource_root()
    inventory = _load(root / "inventory.json")
    registry = _load(root / "mapping-registry.json")
    result = reclassify_registry(inventory, registry)
    assert result == registry
    entries = result.get("entries")
    assert isinstance(entries, list)
    families = Counter(entry.get("family") for entry in entries if isinstance(entry, dict))
    dispositions = Counter(entry.get("disposition") for entry in entries if isinstance(entry, dict))

    assert set(families) == FEATURE_FAMILIES
    assert sum(families.values()) == 15_303
    assert dispositions == {
        "boundary-control": 922,
        "canonical": 13_997,
        "package": 383,
        "standard-deprecated": 1,
    }
    assert set(dispositions) <= DISPOSITIONS


def test_reclassification_changes_only_family_and_disposition_and_is_idempotent() -> None:
    """TEST-MXML-TAXONOMY-004: R1 cannot alter implementation evidence."""

    component = {
        "key": "musicxml:test:xsd:schema/musicxml.xsd:element:/note",
        "version": "test",
        "source_file": "schema/musicxml.xsd",
        "kind": "xsd-element",
        "name": "note",
        "path": "/note",
        "attributes": {"name": "note"},
    }
    original_entry = {
        "component_key": component["key"],
        "versions": ["test"],
        "family": "written note and rhythm",
        "disposition": "canonical",
        "canonical_targets": ["example.models:Note"],
        "handler": "example.mapping:map_note",
        "source_policy": "Preserve the source note.",
        "positive_tests": ["TEST-MXML-EXAMPLE-001"],
        "negative_tests": ["TEST-MXML-EXAMPLE-002"],
        "corpus_evidence": [],
        "losslessness_evidence": [],
        "status": "implemented",
    }
    inventory: dict[str, object] = {"components": [component]}
    registry: dict[str, object] = {"entries": [original_entry]}
    first = reclassify_registry(inventory, registry)
    second = reclassify_registry(inventory, first)
    assert second == first

    original_entries = registry.get("entries")
    result_entries = first.get("entries")
    assert isinstance(original_entries, list)
    assert isinstance(result_entries, list)
    assert len(original_entries) == len(result_entries)
    for original, result in zip(original_entries, result_entries, strict=True):
        assert isinstance(original, dict)
        assert isinstance(result, dict)
        original_without_classification = {
            key: value for key, value in original.items() if key not in {"family", "disposition"}
        }
        result_without_classification = {
            key: value for key, value in result.items() if key not in {"family", "disposition"}
        }
        assert result_without_classification == original_without_classification
        assert result["family"] == "notes and rests"
        assert result["disposition"] == "canonical"
