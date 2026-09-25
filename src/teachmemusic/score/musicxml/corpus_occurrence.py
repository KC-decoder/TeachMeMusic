"""Build declaration-aware occurrence evidence from the governed MusicXML corpora."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import cast

from lxml import etree

from .boundary import validate_musicxml_source
from .contracts import DocumentKind, ValidatedMusicXmlDocument
from .corpus import (
    CorpusAudit,
    _corpus_paths,
    audit_corpora,
    load_corpus_definitions,
)
from .standards import resource_root
from .taxonomy import FEATURE_FAMILIES

OCCURRENCE_INDEX_FORMAT = "teachmemusic.musicxml.declaration-occurrences/1"
_XML_NAMESPACE = "http://www.w3.org/XML/1998/namespace"
_XLINK_NAMESPACE = "http://www.w3.org/1999/xlink"
_XSI_NAMESPACE = "http://www.w3.org/2001/XMLSchema-instance"
_XSD_NAMESPACE = "http://www.w3.org/2001/XMLSchema"


@dataclass(frozen=True, slots=True)
class DeclarationMatch:
    """Resolution of one source construct against versioned declarations."""

    resolution: str
    declaration_keys: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class SourceConstruct:
    """One aggregated source construct and its declaration resolution."""

    run_id: str
    corpus_id: str
    standard_version: str
    kind: str
    selector: str
    name: str
    value: str | None
    occurrences: int
    files: tuple[str, ...]
    resolution: str
    declaration_keys: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ObservedDeclaration:
    """One declaration directly exercised by exact source occurrences."""

    component_key: str
    family: str
    disposition: str
    run_ids: tuple[str, ...]
    occurrences: int
    files: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class CorpusRunOccurrence:
    """Identity and eligible-file counts for one governed corpus execution."""

    run_id: str
    corpus_id: str
    repository: str
    revision: str
    eligible_files: int
    versions: tuple[tuple[str, int], ...]


@dataclass(frozen=True, slots=True)
class DeclarationOccurrenceIndex:
    """Complete deterministic R2 occurrence evidence."""

    inventory_sha256: str
    registry_sha256: str
    declaration_count: int
    runs: tuple[CorpusRunOccurrence, ...]
    constructs: tuple[SourceConstruct, ...]
    observed_declarations: tuple[ObservedDeclaration, ...]


@dataclass(frozen=True, slots=True)
class _SchemaContext:
    owner_names: frozenset[str] = frozenset()
    enum_owner_type: str | None = None
    inline_declaration_path: str | None = None


@dataclass(frozen=True, slots=True)
class _Component:
    key: str
    version: str
    kind: str
    name: str
    path: str
    source_names: frozenset[str]
    declared_type: str | None
    context: _SchemaContext


@dataclass(slots=True)
class _Aggregate:
    occurrences: int
    files: set[str]


class DeclarationCatalog:
    """Resolve concrete XML constructs conservatively against the inventory."""

    def __init__(
        self,
        inventory: dict[str, object],
        *,
        standards_root: Path | None = None,
    ) -> None:
        values = inventory.get("components")
        if not isinstance(values, list):
            raise ValueError("inventory has no component list")
        contexts = _load_schema_contexts(values, standards_root)
        components: list[_Component] = []
        for value in values:
            if not isinstance(value, dict):
                continue
            key = value.get("key")
            version = value.get("version")
            kind = value.get("kind")
            name = value.get("name")
            path = value.get("path")
            if not all(isinstance(item, str) for item in (key, version, kind, name, path)):
                continue
            attributes = value.get("attributes")
            declared_type: str | None = None
            if isinstance(attributes, dict):
                raw_type = attributes.get("type")
                if isinstance(raw_type, str):
                    declared_type = raw_type.rsplit(":", 1)[-1]
            component = _Component(
                key=cast(str, key),
                version=cast(str, version),
                kind=cast(str, kind),
                name=cast(str, name),
                path=cast(str, path),
                source_names=_component_source_names(value),
                declared_type=declared_type,
                context=contexts.get(cast(str, key), _SchemaContext()),
            )
            components.append(component)
        self.components = tuple(components)
        self._by_identity: dict[tuple[str, str, str], tuple[_Component, ...]] = {}
        grouped: dict[tuple[str, str, str], list[_Component]] = defaultdict(list)
        for component in components:
            grouped[(component.version, component.kind, component.name)].append(component)
        self._by_identity = {
            identity: tuple(sorted(items, key=lambda item: item.key))
            for identity, items in grouped.items()
        }

    def resolve_element(
        self,
        version: str,
        name: str,
        parent_name: str | None,
        document_kind: DocumentKind,
    ) -> DeclarationMatch:
        """Resolve an element occurrence without guessing across tied contexts."""

        kind = "dtd-element" if version in {"1.0", "1.1"} else "xsd-element"
        candidates = self._filter_document_sources(
            self._by_identity.get((version, kind, name), ()), document_kind, None
        )
        return _resolve_candidates(candidates, parent_name)

    def resolve_attribute(
        self,
        version: str,
        element_name: str,
        name: str,
        namespace: str | None,
        document_kind: DocumentKind,
    ) -> DeclarationMatch:
        """Resolve an attribute using DTD element context or XSD ownership."""

        if namespace == _XSI_NAMESPACE:
            return DeclarationMatch("external-standard", ())
        if version in {"1.0", "1.1"}:
            candidates = tuple(
                component
                for component in self._by_identity.get((version, "dtd-attribute", name), ())
                if component.path.split("@", 1)[0] == element_name
            )
        else:
            candidates = self._filter_document_sources(
                self._by_identity.get((version, "xsd-attribute", name), ()),
                document_kind,
                namespace,
            )
        return _resolve_candidates(candidates, element_name)

    def resolve_enumeration(
        self,
        version: str,
        value: str,
        declaration_keys: tuple[str, ...],
        document_kind: DocumentKind,
        namespace: str | None,
    ) -> DeclarationMatch | None:
        """Resolve a value only when its declaration type identifies the enum."""

        enum_kind = "dtd-enumeration" if version in {"1.0", "1.1"} else "xsd-enumeration"
        all_candidates = self._filter_document_sources(
            self._by_identity.get((version, enum_kind, value), ()),
            document_kind,
            namespace,
        )
        if not all_candidates:
            return None
        declarations = {
            component.key: component
            for component in self.components
            if component.key in declaration_keys
        }
        applicable: list[_Component] = []
        for candidate in all_candidates:
            for declaration in declarations.values():
                if version in {"1.0", "1.1"}:
                    if candidate.path.startswith(f"{declaration.path}/"):
                        applicable.append(candidate)
                elif (
                    declaration.declared_type is not None
                    and candidate.context.enum_owner_type == declaration.declared_type
                ) or (
                    candidate.context.inline_declaration_path is not None
                    and candidate.context.inline_declaration_path == declaration.path
                ):
                    applicable.append(candidate)
        applicable = list({component.key: component for component in applicable}.values())
        if len(applicable) == 1:
            return DeclarationMatch("exact", (applicable[0].key,))
        candidates = applicable or list(all_candidates)
        return DeclarationMatch(
            "ambiguous",
            tuple(sorted(component.key for component in candidates)),
        )

    @staticmethod
    def _filter_document_sources(
        candidates: tuple[_Component, ...],
        document_kind: DocumentKind,
        namespace: str | None,
    ) -> tuple[_Component, ...]:
        if namespace == _XLINK_NAMESPACE:
            allowed = {"xlink.xsd"}
        elif namespace == _XML_NAMESPACE:
            allowed = {"xml.xsd"}
        elif any(component.kind.startswith("xsd-") for component in candidates):
            allowed = {"musicxml.xsd"}
        else:
            dtd_source = {
                DocumentKind.SCORE_PARTWISE: "partwise.dtd",
                DocumentKind.SCORE_TIMEWISE: "timewise.dtd",
                DocumentKind.OPUS: "opus.dtd",
                DocumentKind.SOUNDS: "sounds.dtd",
            }.get(document_kind)
            allowed = {dtd_source} if dtd_source is not None else set()
        return tuple(
            component for component in candidates if component.source_names.intersection(allowed)
        )


def _component_source_names(component: dict[str, object]) -> frozenset[str]:
    names: set[str] = set()
    source_file = component.get("source_file")
    if isinstance(source_file, str):
        names.add(Path(source_file).name)
    source_files = component.get("source_files")
    if isinstance(source_files, list):
        names.update(Path(value).name for value in source_files if isinstance(value, str))
    return frozenset(names)


def _load_schema_contexts(
    values: list[object], standards_root: Path | None
) -> dict[str, _SchemaContext]:
    if standards_root is None:
        return {}
    grouped: dict[tuple[str, str], list[dict[str, object]]] = defaultdict(list)
    for value in values:
        if not isinstance(value, dict) or value.get("schema_language") != "xsd":
            continue
        version = value.get("version")
        source_file = value.get("source_file")
        if isinstance(version, str) and isinstance(source_file, str):
            grouped[(version, source_file)].append(value)
    output: dict[str, _SchemaContext] = {}
    parser = etree.XMLParser(resolve_entities=False, no_network=True, recover=False)
    for (version, source_file), components in grouped.items():
        tree = etree.parse(str(standards_root / version / source_file), parser)
        by_path = {tree.getpath(node): node for node in tree.iter() if isinstance(node.tag, str)}
        for component in components:
            key = component.get("key")
            path = component.get("path")
            if not isinstance(key, str) or not isinstance(path, str):
                continue
            node = by_path.get(path)
            if node is None:
                continue
            owner_names: set[str] = set()
            enum_owner_type: str | None = None
            inline_declaration_path: str | None = None
            for ancestor in node.iterancestors():
                if not isinstance(ancestor.tag, str):
                    continue
                local_name = etree.QName(ancestor).localname
                if local_name in {"complexType", "element", "group", "attributeGroup"}:
                    owner = ancestor.get("name") or ancestor.get("ref")
                    if owner:
                        owner_names.add(owner.rsplit(":", 1)[-1])
                if enum_owner_type is None and local_name == "simpleType":
                    enum_owner_type = ancestor.get("name")
                if inline_declaration_path is None and local_name in {"element", "attribute"}:
                    inline_declaration_path = tree.getpath(ancestor)
            output[key] = _SchemaContext(
                owner_names=frozenset(owner_names),
                enum_owner_type=enum_owner_type,
                inline_declaration_path=inline_declaration_path,
            )
    return output


def _resolve_candidates(
    candidates: tuple[_Component, ...], owner_name: str | None
) -> DeclarationMatch:
    if len(candidates) == 1:
        return DeclarationMatch("exact", (candidates[0].key,))
    if owner_name is not None:
        contextual = tuple(
            component for component in candidates if owner_name in component.context.owner_names
        )
        if len(contextual) == 1:
            return DeclarationMatch("exact", (contextual[0].key,))
        if contextual:
            candidates = contextual
    return DeclarationMatch(
        "ambiguous" if candidates else "unmatched",
        tuple(sorted(component.key for component in candidates)),
    )


def _xml_text(value: str | bytes) -> str:
    return value.decode("utf-8") if isinstance(value, bytes) else value


def _local_name(value: str | bytes) -> str:
    value = _xml_text(value)
    return etree.QName(value).localname


def _namespace(value: str | bytes) -> str | None:
    value = _xml_text(value)
    return etree.QName(value).namespace


def _selector(element: etree._Element) -> str:
    names = [_local_name(node.tag) for node in element.iterancestors()][::-1]
    names.append(_local_name(element.tag))
    return "/" + "/".join(names)


def _record(
    aggregates: dict[
        tuple[str, str, str, str, str, str, str | None, str, tuple[str, ...]], _Aggregate
    ],
    *,
    run_id: str,
    corpus_id: str,
    version: str,
    kind: str,
    selector: str,
    name: str,
    value: str | None,
    path: str,
    match: DeclarationMatch,
) -> None:
    key = (
        run_id,
        corpus_id,
        version,
        kind,
        selector,
        name,
        value,
        match.resolution,
        match.declaration_keys,
    )
    aggregate = aggregates.setdefault(key, _Aggregate(0, set()))
    aggregate.occurrences += 1
    aggregate.files.add(path)


def _index_document(
    catalog: DeclarationCatalog,
    document: ValidatedMusicXmlDocument,
    *,
    run_id: str,
    corpus_id: str,
    path: str,
    aggregates: dict[
        tuple[str, str, str, str, str, str, str | None, str, tuple[str, ...]], _Aggregate
    ],
) -> None:
    version = document.standard_version
    for element in document.root.iter():
        if not isinstance(element.tag, str):
            continue
        name = _local_name(element.tag)
        parent = element.getparent()
        parent_name = _local_name(parent.tag) if parent is not None else None
        selector = _selector(element)
        element_match = catalog.resolve_element(version, name, parent_name, document.kind)
        _record(
            aggregates,
            run_id=run_id,
            corpus_id=corpus_id,
            version=version,
            kind="element",
            selector=selector,
            name=name,
            value=None,
            path=path,
            match=element_match,
        )
        if len(element) == 0 and (text := (element.text or "").strip()):
            enum_match = catalog.resolve_enumeration(
                version,
                text,
                element_match.declaration_keys if element_match.resolution == "exact" else (),
                document.kind,
                None,
            )
            if enum_match is not None:
                _record(
                    aggregates,
                    run_id=run_id,
                    corpus_id=corpus_id,
                    version=version,
                    kind="enumeration-value",
                    selector=selector,
                    name=name,
                    value=text,
                    path=path,
                    match=enum_match,
                )
        for raw_name, raw_value in sorted(element.attrib.items()):
            attribute_value = _xml_text(raw_value)
            attribute_name = _local_name(raw_name)
            namespace = _namespace(raw_name)
            attribute_selector = f"{selector}/@{attribute_name}"
            attribute_match = catalog.resolve_attribute(
                version,
                name,
                attribute_name,
                namespace,
                document.kind,
            )
            _record(
                aggregates,
                run_id=run_id,
                corpus_id=corpus_id,
                version=version,
                kind="attribute",
                selector=attribute_selector,
                name=attribute_name,
                value=None,
                path=path,
                match=attribute_match,
            )
            enum_match = catalog.resolve_enumeration(
                version,
                attribute_value,
                attribute_match.declaration_keys if attribute_match.resolution == "exact" else (),
                document.kind,
                namespace,
            )
            if enum_match is not None:
                _record(
                    aggregates,
                    run_id=run_id,
                    corpus_id=corpus_id,
                    version=version,
                    kind="enumeration-value",
                    selector=attribute_selector,
                    name=attribute_name,
                    value=attribute_value,
                    path=path,
                    match=enum_match,
                )


def build_occurrence_index(
    w3c_checkout: Path,
    community_checkout: Path,
    *,
    inventory_path: Path | None = None,
    registry_path: Path | None = None,
    audit: CorpusAudit | None = None,
) -> DeclarationOccurrenceIndex:
    """Build exact and explicitly unresolved occurrence evidence for both runs."""

    resources = resource_root()
    selected_inventory = inventory_path or resources / "inventory.json"
    inventory_bytes = selected_inventory.read_bytes()
    inventory_value = json.loads(inventory_bytes)
    if not isinstance(inventory_value, dict):
        raise ValueError("inventory must be a JSON object")
    inventory = cast(dict[str, object], inventory_value)
    selected_registry = registry_path or resources / "mapping-registry.json"
    registry_bytes = selected_registry.read_bytes()
    registry_value = json.loads(registry_bytes)
    if not isinstance(registry_value, dict):
        raise ValueError("registry must be a JSON object")
    raw_registry_entries = registry_value.get("entries")
    if not isinstance(raw_registry_entries, list):
        raise ValueError("registry has no entry list")
    registry_entries = {
        entry["component_key"]: entry
        for entry in raw_registry_entries
        if isinstance(entry, dict) and isinstance(entry.get("component_key"), str)
    }
    catalog = DeclarationCatalog(inventory, standards_root=resources)
    selected_audit = audit or audit_corpora(w3c_checkout, community_checkout)
    definitions = {item.id: item for item in load_corpus_definitions()}
    checkouts = {
        "w3c-maintained-validation": w3c_checkout,
        "w3c-community-feature-suite": community_checkout,
    }
    aggregates: dict[
        tuple[str, str, str, str, str, str, str | None, str, tuple[str, ...]], _Aggregate
    ] = {}
    run_versions: dict[str, Counter[str]] = defaultdict(Counter)
    run_file_counts: Counter[str] = Counter()
    for corpus in selected_audit.corpora:
        definition = definitions[corpus.id]
        eligible = {
            item.path
            for item in corpus.files
            if item.expected_validation == "pass"
            and item.actual_validation == "pass"
            and item.mapping == "mapped-zero-deferred"
        }
        for path in _corpus_paths(checkouts[corpus.id], definition):
            if path.name not in eligible:
                continue
            document = validate_musicxml_source(path.read_bytes(), logical_name=path.name)
            run_file_counts[corpus.run_id] += 1
            run_versions[corpus.run_id][document.standard_version] += 1
            _index_document(
                catalog,
                document,
                run_id=corpus.run_id,
                corpus_id=corpus.id,
                path=path.name,
                aggregates=aggregates,
            )
    constructs = tuple(
        SourceConstruct(
            run_id=key[0],
            corpus_id=key[1],
            standard_version=key[2],
            kind=key[3],
            selector=key[4],
            name=key[5],
            value=key[6],
            resolution=key[7],
            declaration_keys=key[8],
            occurrences=aggregate.occurrences,
            files=tuple(sorted(aggregate.files)),
        )
        for key, aggregate in sorted(aggregates.items())
    )
    observed_counts: Counter[str] = Counter()
    observed_runs: dict[str, set[str]] = defaultdict(set)
    observed_files: dict[str, set[str]] = defaultdict(set)
    for construct in constructs:
        if construct.resolution != "exact" or len(construct.declaration_keys) != 1:
            continue
        component_key = construct.declaration_keys[0]
        observed_counts[component_key] += construct.occurrences
        observed_runs[component_key].add(construct.run_id)
        observed_files[component_key].update(
            f"{construct.run_id}:{path}" for path in construct.files
        )
    observed = tuple(
        ObservedDeclaration(
            component_key=key,
            family=cast(str, registry_entries[key]["family"]),
            disposition=cast(str, registry_entries[key]["disposition"]),
            run_ids=tuple(sorted(observed_runs[key])),
            occurrences=observed_counts[key],
            files=tuple(sorted(observed_files[key])),
        )
        for key in sorted(observed_counts)
    )
    audit_by_id = {item.id: item for item in selected_audit.corpora}
    runs = tuple(
        CorpusRunOccurrence(
            run_id=definition.run_id,
            corpus_id=definition.id,
            repository=definition.repository,
            revision=definition.revision,
            eligible_files=run_file_counts[definition.run_id],
            versions=tuple(sorted(run_versions[definition.run_id].items())),
        )
        for definition in load_corpus_definitions()
        if definition.id in audit_by_id
    )
    component_values = inventory.get("components")
    declaration_count = len(component_values) if isinstance(component_values, list) else 0
    return DeclarationOccurrenceIndex(
        inventory_sha256=hashlib.sha256(inventory_bytes).hexdigest(),
        registry_sha256=hashlib.sha256(registry_bytes).hexdigest(),
        declaration_count=declaration_count,
        runs=runs,
        constructs=constructs,
        observed_declarations=observed,
    )


def render_json(index: DeclarationOccurrenceIndex) -> str:
    """Serialize the occurrence index without checkout paths."""

    payload = {
        "format": OCCURRENCE_INDEX_FORMAT,
        "inventory_sha256": index.inventory_sha256,
        "registry_sha256": index.registry_sha256,
        "declaration_count": index.declaration_count,
        "runs": [
            {
                "run_id": run.run_id,
                "corpus_id": run.corpus_id,
                "repository": run.repository,
                "revision": run.revision,
                "eligible_files": run.eligible_files,
                "versions": dict(run.versions),
            }
            for run in index.runs
        ],
        "summary": _summary(index),
        "observed_declarations": [
            {
                "component_key": item.component_key,
                "family": item.family,
                "disposition": item.disposition,
                "run_ids": list(item.run_ids),
                "occurrences": item.occurrences,
                "files": list(item.files),
            }
            for item in index.observed_declarations
        ],
        "constructs": [
            {
                "run_id": item.run_id,
                "corpus_id": item.corpus_id,
                "standard_version": item.standard_version,
                "kind": item.kind,
                "selector": item.selector,
                "name": item.name,
                "value": item.value,
                "occurrences": item.occurrences,
                "files": list(item.files),
                "resolution": item.resolution,
                "declaration_keys": list(item.declaration_keys),
            }
            for item in index.constructs
        ],
    }
    return json.dumps(payload, indent=2, sort_keys=True) + "\n"


def _summary(index: DeclarationOccurrenceIndex) -> dict[str, object]:
    resolution_counts = Counter(item.resolution for item in index.constructs)
    occurrence_counts: Counter[str] = Counter()
    for item in index.constructs:
        occurrence_counts[item.resolution] += item.occurrences
    family_counts = Counter(item.family for item in index.observed_declarations)
    disposition_counts = Counter(item.disposition for item in index.observed_declarations)
    return {
        "eligible_files": sum(run.eligible_files for run in index.runs),
        "distinct_constructs": len(index.constructs),
        "source_occurrences": sum(item.occurrences for item in index.constructs),
        "construct_resolutions": dict(sorted(resolution_counts.items())),
        "occurrence_resolutions": dict(sorted(occurrence_counts.items())),
        "observed_declarations": len(index.observed_declarations),
        "unobserved_declarations": index.declaration_count - len(index.observed_declarations),
        "observed_families": {
            family: family_counts.get(family, 0) for family in sorted(FEATURE_FAMILIES)
        },
        "observed_dispositions": dict(sorted(disposition_counts.items())),
    }


def render_markdown(index: DeclarationOccurrenceIndex) -> str:
    """Render a concise governed summary of the machine-readable index."""

    summary = _summary(index)
    resolution_counts = cast(dict[str, int], summary["construct_resolutions"])
    occurrence_counts = cast(dict[str, int], summary["occurrence_resolutions"])
    family_counts = cast(dict[str, int], summary["observed_families"])
    lines = [
        "# MusicXML Declaration-Occurrence Index",
        "",
        "> Generated DEV-004 Task 7J-R2 evidence. Only schema-valid files that",
        "> map with zero deferred facts participate. Ambiguous declaration matches",
        "> remain unresolved and cannot support evidence promotion.",
        "",
        "## Governed Runs",
        "",
        "| Run ID | Corpus | Revision | Eligible files | Versions |",
        "|---|---|---|---:|---|",
    ]
    for run in index.runs:
        versions = ", ".join(f"{version}: {count}" for version, count in run.versions)
        lines.append(
            f"| `{run.run_id}` | {run.corpus_id} | `{run.revision}` | "
            f"{run.eligible_files} | {versions} |"
        )
    lines.extend(
        [
            "",
            "## Summary",
            "",
            f"- Inventory declarations: {index.declaration_count}",
            f"- Eligible source files: {summary['eligible_files']}",
            f"- Distinct aggregated constructs: {summary['distinct_constructs']}",
            f"- Source occurrences represented: {summary['source_occurrences']}",
            f"- Directly observed declarations: {summary['observed_declarations']}",
            f"- Declarations not directly observed: {summary['unobserved_declarations']}",
            "",
            "| Resolution | Constructs | Source occurrences |",
            "|---|---:|---:|",
        ]
    )
    for resolution in sorted(set(resolution_counts) | set(occurrence_counts)):
        lines.append(
            f"| {resolution} | {resolution_counts.get(resolution, 0)} | "
            f"{occurrence_counts.get(resolution, 0)} |"
        )
    lines.extend(
        [
            "",
            "## Direct Observation by Feature Family",
            "",
            "| Family | Observed declarations |",
            "|---|---:|",
        ]
    )
    for family, count in family_counts.items():
        lines.append(f"| {family} | {count} |")
    lines.extend(
        [
            "",
            "## Interpretation",
            "",
            "An `exact` construct has one conservatively resolved declaration key.",
            "An `ambiguous` construct retains every tied candidate and proves none",
            "of them individually. An `unmatched` construct is visible evidence of",
            "an indexing gap and must not be promoted. `external-standard` identifies",
            "XML Schema-instance hints outside the declared MusicXML inventory.",
            "",
            "This index records observation only. It does not prove semantic",
            "losslessness and Task 7J-R2 does not change registry evidence status.",
            "The complete construct and declaration links are in the JSON artifact.",
            "",
        ]
    )
    return "\n".join(lines)


def _build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--w3c-checkout", type=Path, required=True)
    parser.add_argument("--community-checkout", type=Path, required=True)
    parser.add_argument("--inventory", type=Path)
    parser.add_argument("--registry", type=Path)
    parser.add_argument("--json-output", type=Path)
    parser.add_argument("--markdown-output", type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    """Build and optionally write the governed declaration-occurrence evidence."""

    arguments = _build_argument_parser().parse_args(argv)
    index = build_occurrence_index(
        arguments.w3c_checkout,
        arguments.community_checkout,
        inventory_path=cast(Path | None, arguments.inventory),
        registry_path=cast(Path | None, arguments.registry),
    )
    json_text = render_json(index)
    markdown_text = render_markdown(index)
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
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
