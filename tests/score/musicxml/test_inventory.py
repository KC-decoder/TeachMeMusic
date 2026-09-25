"""Tests for deterministic declaration inventory generation."""

from __future__ import annotations

import json
from pathlib import Path
from typing import cast

from teachmemusic.score.musicxml.inventory import generate_inventory
from teachmemusic.score.musicxml.standards import resource_root


def _checked_inventory() -> dict[str, object]:
    value = json.loads((resource_root() / "inventory.json").read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return cast(dict[str, object], value)


def test_checked_inventory_matches_fresh_generation() -> None:
    """TEST-MXML-INVENTORY-004: checked inventory is deterministic and current."""

    assert _checked_inventory() == generate_inventory()


def test_inventory_covers_every_declared_version_and_component_kind() -> None:
    """TEST-MXML-INVENTORY-005: the baseline includes all seven native versions."""

    inventory = _checked_inventory()
    counts = inventory["counts_by_version"]
    assert isinstance(counts, dict)
    assert tuple(counts) == ("1.0", "1.1", "2.0", "3.0", "3.1", "4.0", "4.1-draft")
    assert inventory["component_count"] == 15_303
    assert all(sum(version_counts.values()) > 0 for version_counts in counts.values())


def test_inventory_keys_are_unique_and_stably_sorted() -> None:
    """TEST-MXML-INVENTORY-006: local declarations have collision-free stable keys."""

    components = _checked_inventory()["components"]
    assert isinstance(components, list)
    keys = [component["key"] for component in components]
    assert len(keys) == len(set(keys))
    assert keys == sorted(keys)


def test_pinned_draft_inventory_contains_the_recorded_41_delta() -> None:
    """TEST-MXML-INVENTORY-007: the pinned 4.1 additions remain visible."""

    components = _checked_inventory()["components"]
    assert isinstance(components, list)
    draft_names = {
        component["name"]
        for component in components
        if component["version"] == "4.1-draft" and component["kind"] == "xsd-element"
    }
    assert {"voice-direction", "voice-directions"} <= draft_names


def test_inventory_is_packaged_beside_the_version_bundles() -> None:
    """TEST-MXML-INVENTORY-008: installed-package data includes generated evidence."""

    root = resource_root()
    assert (root / "manifest.json").is_file()
    assert (root / "inventory.json").is_file()
    assert (root / "mapping-registry.json").is_file()
    assert all((root / version / "schema").is_dir() for version in ("1.0", "4.1-draft"))
    assert Path(__file__).is_file()
