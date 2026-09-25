"""Tests for declaration-aware official-corpus occurrence evidence."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from teachmemusic.score.musicxml.contracts import DocumentKind
from teachmemusic.score.musicxml.corpus_occurrence import (
    CorpusRunOccurrence,
    DeclarationCatalog,
    DeclarationOccurrenceIndex,
    ObservedDeclaration,
    SourceConstruct,
    render_json,
    render_markdown,
)

XSD_NAMESPACE = "http://www.w3.org/2001/XMLSchema"


def _xsd_component(
    key: str,
    kind: str,
    name: str,
    path: str,
    attributes: dict[str, str],
) -> dict[str, object]:
    return {
        "key": key,
        "version": "4.0",
        "schema_language": "xsd",
        "source_file": "schema/musicxml.xsd",
        "kind": kind,
        "name": name,
        "path": path,
        "attributes": attributes,
    }


def test_catalog_resolves_only_unique_or_contextual_declarations(tmp_path: Path) -> None:
    """TEST-MXML-OCCURRENCE-001: tied declarations remain explicitly ambiguous."""

    schema = tmp_path / "4.0/schema/musicxml.xsd"
    schema.parent.mkdir(parents=True)
    schema.write_text(
        f"""<xs:schema xmlns:xs=\"{XSD_NAMESPACE}\">
  <xs:element name=\"note\" type=\"note-value\"/>
  <xs:attribute name=\"type\" type=\"note-value\"/>
  <xs:attribute name=\"type\" type=\"xs:string\"/>
  <xs:simpleType name=\"note-value\">
    <xs:restriction base=\"xs:string\"><xs:enumeration value=\"quarter\"/></xs:restriction>
  </xs:simpleType>
</xs:schema>""",
        encoding="utf-8",
    )
    note_key = "musicxml:4.0:xsd:note"
    enum_key = "musicxml:4.0:xsd:quarter"
    inventory: dict[str, object] = {
        "components": [
            _xsd_component(
                note_key,
                "xsd-element",
                "note",
                "/xs:schema/xs:element",
                {"name": "note", "type": "note-value"},
            ),
            _xsd_component(
                "musicxml:4.0:xsd:type-1",
                "xsd-attribute",
                "type",
                "/xs:schema/xs:attribute[1]",
                {"name": "type", "type": "note-value"},
            ),
            _xsd_component(
                "musicxml:4.0:xsd:type-2",
                "xsd-attribute",
                "type",
                "/xs:schema/xs:attribute[2]",
                {"name": "type", "type": "xs:string"},
            ),
            _xsd_component(
                enum_key,
                "xsd-enumeration",
                "quarter",
                "/xs:schema/xs:simpleType/xs:restriction/xs:enumeration",
                {"value": "quarter"},
            ),
        ]
    }
    catalog = DeclarationCatalog(inventory, standards_root=tmp_path)

    note = catalog.resolve_element("4.0", "note", "measure", DocumentKind.SCORE_PARTWISE)
    attribute = catalog.resolve_attribute("4.0", "note", "type", None, DocumentKind.SCORE_PARTWISE)
    value = catalog.resolve_enumeration(
        "4.0", "quarter", note.declaration_keys, DocumentKind.SCORE_PARTWISE, None
    )

    assert note.resolution == "exact"
    assert note.declaration_keys == (note_key,)
    assert attribute.resolution == "ambiguous"
    assert value is not None
    assert value.resolution == "exact"
    assert value.declaration_keys == (enum_key,)


def test_dtd_enumeration_requires_its_element_attribute_context() -> None:
    """TEST-MXML-OCCURRENCE-002: DTD enum evidence follows the exact attribute."""

    attribute_key = "musicxml:1.0:dtd:note-print"
    enum_key = "musicxml:1.0:dtd:note-print-no"
    inventory: dict[str, object] = {
        "components": [
            {
                "key": attribute_key,
                "version": "1.0",
                "schema_language": "dtd",
                "source_files": ["schema/partwise.dtd"],
                "kind": "dtd-attribute",
                "name": "print-object",
                "path": "note@print-object",
                "attributes": {},
            },
            {
                "key": enum_key,
                "version": "1.0",
                "schema_language": "dtd",
                "source_files": ["schema/partwise.dtd"],
                "kind": "dtd-enumeration",
                "name": "no",
                "path": "note@print-object/no",
                "attributes": {},
            },
        ]
    }
    catalog = DeclarationCatalog(inventory)
    attribute = catalog.resolve_attribute(
        "1.0", "note", "print-object", None, DocumentKind.SCORE_PARTWISE
    )
    value = catalog.resolve_enumeration(
        "1.0", "no", attribute.declaration_keys, DocumentKind.SCORE_PARTWISE, None
    )

    assert attribute.declaration_keys == (attribute_key,)
    assert value is not None
    assert value.declaration_keys == (enum_key,)


def test_occurrence_reports_are_deterministic_and_do_not_promote() -> None:
    """TEST-MXML-OCCURRENCE-003: the artifact records observation, not status."""

    index = DeclarationOccurrenceIndex(
        inventory_sha256="a" * 64,
        registry_sha256="c" * 64,
        declaration_count=2,
        runs=(
            CorpusRunOccurrence(
                run_id="CORPUS-MXML-001",
                corpus_id="example",
                repository="https://example.invalid/repository.git",
                revision="b" * 40,
                eligible_files=1,
                versions=(("4.0", 1),),
            ),
        ),
        constructs=(
            SourceConstruct(
                run_id="CORPUS-MXML-001",
                corpus_id="example",
                standard_version="4.0",
                kind="element",
                selector="/score-partwise/part",
                name="part",
                value=None,
                occurrences=1,
                files=("example.musicxml",),
                resolution="exact",
                declaration_keys=("musicxml:4.0:part",),
            ),
        ),
        observed_declarations=(
            ObservedDeclaration(
                component_key="musicxml:4.0:part",
                family="parts and groups",
                disposition="canonical",
                run_ids=("CORPUS-MXML-001",),
                occurrences=1,
                files=("CORPUS-MXML-001:example.musicxml",),
            ),
        ),
    )

    assert render_json(index) == render_json(index)
    markdown = render_markdown(index)
    assert "Directly observed declarations: 1" in markdown
    assert "does not change registry evidence status" in markdown
    assert "corpus-verified" not in render_json(index)


def test_governed_occurrence_artifact_is_consistent_with_current_ledger() -> None:
    """TEST-MXML-OCCURRENCE-004: generated observation evidence is auditable."""

    root = Path(__file__).resolve().parents[3]
    resource_root = root / "src/teachmemusic/score/musicxml/resources"
    artifact_path = root / "docs/generated/musicxml-declaration-occurrences.json"
    artifact_bytes = artifact_path.read_bytes()
    artifact = json.loads(artifact_bytes)
    inventory_bytes = (resource_root / "inventory.json").read_bytes()
    registry_bytes = (resource_root / "mapping-registry.json").read_bytes()
    registry = json.loads(registry_bytes)

    assert artifact["format"] == "teachmemusic.musicxml.declaration-occurrences/1"
    assert artifact["inventory_sha256"] == hashlib.sha256(inventory_bytes).hexdigest()
    assert artifact["registry_sha256"] == hashlib.sha256(registry_bytes).hexdigest()
    assert [(run["run_id"], run["eligible_files"]) for run in artifact["runs"]] == [
        ("CORPUS-MXML-001", 7),
        ("CORPUS-MXML-002", 180),
    ]
    assert artifact["summary"]["source_occurrences"] == 58_458
    assert artifact["summary"]["observed_declarations"] == 939
    assert artifact["summary"]["unobserved_declarations"] == 14_364
    assert artifact["summary"]["construct_resolutions"] == {
        "ambiguous": 497,
        "exact": 1_268,
        "external-standard": 1,
    }

    exact_keys = {
        construct["declaration_keys"][0]
        for construct in artifact["constructs"]
        if construct["resolution"] == "exact"
    }
    observed_keys = {
        declaration["component_key"] for declaration in artifact["observed_declarations"]
    }
    assert exact_keys == observed_keys
    observed_keys = {
        declaration["component_key"] for declaration in artifact["observed_declarations"]
    }
    assert sum(entry["status"] == "corpus-verified" for entry in registry["entries"]) == 0
    assert all(
        (
            entry["status"] == "corpus-verified"
            and entry["corpus_evidence"]
            and entry["component_key"] in observed_keys
        )
        or (
            entry["status"] == "implemented"
            and entry["corpus_evidence"] == []
            and entry["component_key"] not in observed_keys
        )
        or (
            entry["status"] == "losslessness-verified"
            and (
                (entry["corpus_evidence"] and entry["component_key"] in observed_keys)
                or (entry["corpus_evidence"] == [] and entry["component_key"] not in observed_keys)
            )
        )
        for entry in registry["entries"]
    )
    assert (
        sum(entry["status"] == "losslessness-verified" for entry in registry["entries"]) == 15_303
    )
    assert b"/private/" not in artifact_bytes
