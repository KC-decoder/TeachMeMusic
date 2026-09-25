"""Deterministically inventory the pinned MusicXML XSD and DTD declarations."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any, cast

from lxml import etree

from .standards import resource_root, secure_xml_parser, source_versions, verify_manifest

INVENTORY_FORMAT = "teachmemusic.musicxml.inventory/1"
XSD_NAMESPACE = "http://www.w3.org/2001/XMLSchema"
XSD_COMPONENTS = frozenset(
    {
        "all",
        "any",
        "anyAttribute",
        "attribute",
        "attributeGroup",
        "choice",
        "complexType",
        "element",
        "enumeration",
        "group",
        "import",
        "include",
        "sequence",
        "simpleType",
    }
)


def _canonical_json(value: object) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n").encode()


def _normalized_attributes(element: etree._Element) -> dict[str, str]:
    attributes: dict[str, str] = {}
    for raw_name, value in sorted(element.attrib.items()):
        decoded_name = raw_name.decode("utf-8") if isinstance(raw_name, bytes) else raw_name
        decoded_value = value.decode("utf-8") if isinstance(value, bytes) else value
        if decoded_name.startswith("{"):
            name = etree.QName(decoded_name)
            normalized = f"{{{name.namespace}}}{name.localname}"
        else:
            normalized = decoded_name
        attributes[normalized] = decoded_value
    return attributes


def _xsd_components(version: str, bundle_root: Path) -> list[dict[str, object]]:
    components: list[dict[str, object]] = []
    for path in sorted((bundle_root / "schema").glob("*.xsd")):
        document = etree.parse(str(path), secure_xml_parser(bundle_root))
        relative = path.relative_to(bundle_root).as_posix()
        tree = document
        for element in document.iter():
            if not isinstance(element.tag, str):
                continue
            name = etree.QName(element)
            if name.namespace != XSD_NAMESPACE or name.localname not in XSD_COMPONENTS:
                continue
            parent = element.getparent()
            scope = (
                "global"
                if parent is not None and etree.QName(parent).localname == "schema"
                else "local"
            )
            xpath = tree.getpath(element)
            attributes = _normalized_attributes(element)
            display_name = (
                attributes.get("name")
                or attributes.get("ref")
                or attributes.get("value")
                or "<anonymous>"
            )
            key = f"musicxml:{version}:xsd:{relative}:{name.localname}:{xpath}"
            components.append(
                {
                    "key": key,
                    "version": version,
                    "schema_language": "xsd",
                    "source_file": relative,
                    "source_line": element.sourceline,
                    "kind": f"xsd-{_kebab(name.localname)}",
                    "name": display_name,
                    "scope": scope,
                    "path": xpath,
                    "attributes": attributes,
                }
            )
    return components


def _dtd_components(
    version: str,
    bundle_root: Path,
    entrypoints: tuple[str, ...],
) -> list[dict[str, object]]:
    aggregated: dict[tuple[str, str, str], dict[str, object]] = {}
    for relative in entrypoints:
        dtd = etree.DTD(str(bundle_root / relative))
        dynamic_dtd = cast(Any, dtd)
        for element in sorted(dynamic_dtd.iterelements(), key=lambda item: item.name):
            element_attributes: dict[str, object] = {
                "content_type": element.type,
                "content_model": _dtd_content_model(element.content),
            }
            _add_dtd_component(
                aggregated,
                version,
                relative,
                {
                    "kind": "dtd-element",
                    "name": element.name,
                    "scope": "resolved-entrypoint",
                    "path": element.name,
                    "attributes": element_attributes,
                },
            )
            for attribute in sorted(element.iterattributes(), key=lambda item: item.name):
                attribute_path = f"{element.name}@{attribute.name}"
                _add_dtd_component(
                    aggregated,
                    version,
                    relative,
                    {
                        "kind": "dtd-attribute",
                        "name": attribute.name,
                        "scope": "resolved-entrypoint",
                        "path": attribute_path,
                        "attributes": {
                            "attribute_type": attribute.type,
                            "default": attribute.default,
                            "default_value": attribute.default_value,
                        },
                    },
                )
                for value in sorted(attribute.values()):
                    _add_dtd_component(
                        aggregated,
                        version,
                        relative,
                        {
                            "kind": "dtd-enumeration",
                            "name": value,
                            "scope": "resolved-entrypoint",
                            "path": f"{attribute_path}/{value}",
                            "attributes": {},
                        },
                    )
        for entity in sorted(dynamic_dtd.iterentities(), key=lambda item: item.name):
            _add_dtd_component(
                aggregated,
                version,
                relative,
                {
                    "kind": "dtd-entity",
                    "name": entity.name,
                    "scope": "resolved-entrypoint",
                    "path": entity.name,
                    "attributes": {
                        "content_sha256": hashlib.sha256(
                            (entity.content or "").encode("utf-8")
                        ).hexdigest()
                    },
                },
            )
    return list(aggregated.values())


def _dtd_content_model(content: etree._DTDElementContentDecl | None) -> object:
    if content is None:
        return None
    return {
        "name": content.name,
        "type": content.type,
        "occur": content.occur,
        "left": _dtd_content_model(content.left),
        "right": _dtd_content_model(content.right),
    }


def _add_dtd_component(
    aggregated: dict[tuple[str, str, str], dict[str, object]],
    version: str,
    entrypoint: str,
    component: dict[str, object],
) -> None:
    kind = cast(str, component["kind"])
    path = cast(str, component["path"])
    attributes = component["attributes"]
    signature = hashlib.sha256(_canonical_json(attributes)).hexdigest()[:16]
    identity = (kind, path, signature)
    existing = aggregated.get(identity)
    if existing is not None:
        source_files = cast(list[str], existing["source_files"])
        if entrypoint not in source_files:
            source_files.append(entrypoint)
            source_files.sort()
        return
    component.update(
        {
            "key": f"musicxml:{version}:dtd:{kind}:{path}:{signature}",
            "version": version,
            "schema_language": "dtd",
            "source_files": [entrypoint],
            "source_line": None,
        }
    )
    aggregated[identity] = component


def _kebab(value: str) -> str:
    output: list[str] = []
    for character in value:
        if character.isupper():
            output.extend(("-", character.lower()))
        else:
            output.append(character)
    return "".join(output)


def _text_list(document: dict[str, object], key: str) -> tuple[str, ...]:
    value = document.get(key)
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise ValueError(f"invalid source version field: {key}")
    return tuple(cast(list[str], value))


def generate_inventory(root: Path | None = None) -> dict[str, object]:
    """Generate the complete deterministic declaration inventory."""

    selected_root = (root or resource_root()).resolve()
    problems = verify_manifest(selected_root)
    if problems:
        summary = "; ".join(f"{item.code}:{item.path}" for item in problems[:5])
        raise ValueError(f"standards resource manifest verification failed: {summary}")

    manifest_value = json.loads((selected_root / "manifest.json").read_text(encoding="utf-8"))
    if not isinstance(manifest_value, dict):
        raise ValueError("resource manifest must be a JSON object")
    manifest = cast(dict[str, object], manifest_value)
    components: list[dict[str, object]] = []
    version_counts: dict[str, dict[str, int]] = {}

    for source in source_versions(selected_root):
        version = source.get("version")
        directory = source.get("directory")
        if not isinstance(version, str) or not isinstance(directory, str):
            raise ValueError("source version requires text version and directory")
        bundle_root = selected_root / directory
        version_components = _xsd_components(version, bundle_root)
        version_components.extend(
            _dtd_components(
                version,
                bundle_root,
                _text_list(source, "dtd_entrypoints"),
            )
        )
        version_components.sort(key=lambda item: cast(str, item["key"]))
        duplicate_keys = [
            key
            for key, count in Counter(
                cast(str, component["key"]) for component in version_components
            ).items()
            if count > 1
        ]
        if duplicate_keys:
            raise ValueError(f"duplicate inventory component key: {duplicate_keys[0]}")
        counts = Counter(cast(str, component["kind"]) for component in version_components)
        version_counts[version] = dict(sorted(counts.items()))
        components.extend(version_components)

    components.sort(key=lambda item: cast(str, item["key"]))
    kind_counts = Counter(cast(str, component["kind"]) for component in components)
    unsigned: dict[str, object] = {
        "format": INVENTORY_FORMAT,
        "resource_manifest_sha256": manifest.get("content_sha256"),
        "component_count": len(components),
        "counts_by_kind": dict(sorted(kind_counts.items())),
        "counts_by_version": version_counts,
        "components": components,
    }
    return {
        **unsigned,
        "content_sha256": hashlib.sha256(_canonical_json(unsigned)).hexdigest(),
    }


def write_inventory(output: Path, root: Path | None = None) -> None:
    """Write the deterministic declaration inventory."""

    output.write_bytes(_canonical_json(generate_inventory(root)))


def _build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=resource_root())
    parser.add_argument("--output", type=Path)
    parser.add_argument("--check", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    """Generate or verify the checked-in declaration inventory."""

    arguments = _build_argument_parser().parse_args(argv)
    root = cast(Path, arguments.root)
    output = cast(Path | None, arguments.output) or root / "inventory.json"
    generated = _canonical_json(generate_inventory(root))
    if arguments.check:
        if not output.is_file() or output.read_bytes() != generated:
            print(f"inventory is missing or stale: {output}")
            return 1
        print(f"inventory is current: {output}")
        return 0
    output.write_bytes(generated)
    print(f"wrote {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
