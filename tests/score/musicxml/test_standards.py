"""Tests for pinned MusicXML resources and the local-only standards boundary."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from lxml import etree

from teachmemusic.score.musicxml.standards import (
    LocalOnlyResolver,
    compile_standard_resources,
    generate_manifest,
    resource_root,
    verify_manifest,
    write_manifest,
)


def test_pinned_manifest_matches_every_vendored_resource() -> None:
    """TEST-MXML-INVENTORY-001: every vendored byte matches the manifest."""

    assert verify_manifest() == ()


def test_manifest_detects_resource_drift(tmp_path: Path) -> None:
    """TEST-MXML-INVENTORY-002: changed resources fail hash verification."""

    root = tmp_path / "resources"
    bundle = root / "test" / "schema"
    bundle.mkdir(parents=True)
    (bundle / "example.xsd").write_text("<schema/>", encoding="utf-8")
    sources = {
        "format": "teachmemusic.musicxml.sources/1",
        "repository": "https://example.invalid/standards.git",
        "versions": [
            {
                "version": "test",
                "directory": "test",
                "status": "test",
                "source_ref": "test",
                "commit": "0" * 40,
                "license_id": "test-only",
                "xsd_entrypoints": [],
                "dtd_entrypoints": [],
            }
        ],
    }
    (root / "source-revisions.json").write_text(
        json.dumps(sources),
        encoding="utf-8",
    )
    write_manifest(root / "manifest.json", root)
    assert verify_manifest(root) == ()

    (bundle / "example.xsd").write_text("<changed/>", encoding="utf-8")
    assert {problem.code for problem in verify_manifest(root)} == {
        "hash-mismatch",
        "size-mismatch",
    }


def test_manifest_generation_is_deterministic() -> None:
    """TEST-MXML-INVENTORY-003: repeated manifests are structurally identical."""

    assert generate_manifest() == generate_manifest()


def test_all_declared_schema_entrypoints_compile_locally() -> None:
    """TEST-MXML-VERSION-001: all seven pinned version bundles compile."""

    results = compile_standard_resources()
    assert tuple(result.version for result in results) == (
        "1.0",
        "1.1",
        "2.0",
        "3.0",
        "3.1",
        "4.0",
        "4.1-draft",
    )
    assert sum(result.xsd_entrypoints for result in results) == 24
    assert sum(result.dtd_entrypoints for result in results) == 11


def test_lxml_runtime_is_the_accepted_exact_pin() -> None:
    """TEST-MXML-VERSION-002: the verified XML runtime is lxml 6.1.3."""

    assert etree.LXML_VERSION[:3] == (6, 1, 3)


@pytest.mark.parametrize(
    "url",
    (
        "https://attacker.invalid/xml.xsd",
        "https://www.musicxml.org/xsd/xml.xsd",
        "http://www.musicxml.org/evil/xml.xsd",
        "../schema/xml.xsd",
    ),
)
def test_local_resolver_rejects_every_unapproved_location(url: str) -> None:
    """TEST-MXML-SECURITY-001: resource resolution is exact and network closed."""

    resolver = LocalOnlyResolver(resource_root() / "4.0")
    with pytest.raises(OSError):
        resolver.resolve(url, None, object())


def test_local_resolver_maps_an_exact_official_url() -> None:
    """TEST-MXML-SECURITY-002: approved URLs resolve to the pinned local file."""

    parser = etree.XMLParser(no_network=True)
    parser.resolvers.add(LocalOnlyResolver(resource_root() / "4.0"))
    document = etree.parse("http://www.musicxml.org/xsd/xml.xsd", parser)
    assert etree.QName(document.getroot()).localname == "schema"
