"""Deterministically classify MusicXML declarations by semantic responsibility."""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from typing import cast

from .standards import resource_root

FEATURE_FAMILIES = frozenset(
    {
        "articulations and ornaments",
        "attributes and staff state",
        "barlines and navigation",
        "credits and defaults",
        "document identity and versions",
        "directions, text, and tempo",
        "dynamics",
        "figured bass",
        "harmony and fret diagrams",
        "header and identification",
        "instruments and performers",
        "layout and appearance",
        "links, bookmarks, and grouping",
        "lyrics",
        "measures, voices, and time cursor",
        "mxl packaging",
        "noteheads and notations",
        "notes and rests",
        "opus and sounds documents",
        "parts and groups",
        "playback, midi, listening, and assessment",
        "presentation text and shared formatting",
        "rhythm, beams, and tuplets",
        "technical and instrument-specific notation",
        "ties and spanners",
        "written pitch and accidentals",
    }
)

DISPOSITIONS = frozenset(
    {
        "canonical",
        "package",
        "boundary-control",
        "standard-deprecated",
        "extension-policy",
    }
)

_DIRECT_FAMILIES = {
    "analytical groupings": "links, bookmarks, and grouping",
    "annotation containers": "noteheads and notations",
    "articulations": "articulations and ornaments",
    "attribute state": "attributes and staff state",
    "barline": "barlines and navigation",
    "barline and measure styles": "barlines and navigation",
    "complex directions": "directions, text, and tempo",
    "concert-score directives": "attributes and staff state",
    "core temporal declarations": "measures, voices, and time cursor",
    "direction spans": "ties and spanners",
    "directions": "directions, text, and tempo",
    "dynamics": "dynamics",
    "editorial annotations": "presentation text and shared formatting",
    "figured bass": "figured bass",
    "general notations": "noteheads and notations",
    "harmony": "harmony and fret diagrams",
    "legacy semantic entities": "presentation text and shared formatting",
    "lyrics": "lyrics",
    "mapped semantic type closure": "measures, voices, and time cursor",
    "notation spans": "ties and spanners",
    "noteheads": "noteheads and notations",
    "ornaments": "articulations and ornaments",
    "pitch": "written pitch and accidentals",
    "score structure": "parts and groups",
    "semantic primitive values": "measures, voices, and time cursor",
    "semantic structural groups": "parts and groups",
    "semantic text containers": "header and identification",
    "shared semantic attributes": "measures, voices, and time cursor",
    "simple directions": "directions, text, and tempo",
    "source metadata": "header and identification",
    "task 7g semantic closure": "measures, voices, and time cursor",
    "task 7h musicxml sound catalogs": "opus and sounds documents",
    "task 7h notation engraving geometry": "presentation text and shared formatting",
    "task 7h playback and performer interaction": ("playback, midi, listening, and assessment"),
    "task 7h presentation integration": "layout and appearance",
    "task 7h remaining presentation and legacy integration": (
        "presentation text and shared formatting"
    ),
    "task 7h shared font and text formatting": "presentation text and shared formatting",
    "task 7h shared presentation values": "presentation text and shared formatting",
    "technical marks": "technical and instrument-specific notation",
    "temporal attributes": "attributes and staff state",
    "temporal cursor": "measures, voices, and time cursor",
    "temporal event": "notes and rests",
    "ties and slurs": "ties and spanners",
    "transposition": "attributes and staff state",
}

_CREDIT_TERMS = frozenset(
    {
        "appearance",
        "credit",
        "defaults",
        "glyph",
        "lyric-font",
        "lyric-language",
        "music-font",
        "note-size",
        "scaling",
        "word-font",
    }
)
_INSTRUMENT_TERMS = frozenset(
    {
        "ensemble",
        "instrument",
        "midi-device",
        "midi-instrument",
        "performer",
        "player",
        "score-instrument",
        "virtual-instrument",
    }
)
_NOTE_TERMS = frozenset(
    {
        "chord",
        "cue",
        "grace",
        "note",
        "rest",
        "unpitched",
    }
)
_PITCH_TERMS = frozenset(
    {
        "accidental",
        "alter",
        "display-octave",
        "display-step",
        "octave",
        "pitch",
        "step",
    }
)
_RHYTHM_TERMS = frozenset(
    {
        "beam",
        "dot",
        "duration",
        "normal-dot",
        "normal-note",
        "time-modification",
        "tremolo",
        "tuplet",
    }
)

_BOUNDARY_CREDIT_TERMS = frozenset({"credit", "credits", "defaults", "scaling"})
_BOUNDARY_INSTRUMENT_TERMS = frozenset(
    {
        "ensemble",
        "instrument",
        "instrument-link",
        "midi",
        "performer",
        "player",
        "virtual-instrument",
        "virtual-instrument-data",
    }
)
_BOUNDARY_LAYOUT_TERMS = frozenset({"appearance", "distance", "layout", "line-width", "note-size"})
_BOUNDARY_LINK_TERMS = frozenset({"actuate", "bookmark", "href", "link", "role", "show", "xlink"})
_BOUNDARY_PART_TERMS = frozenset({"group-name", "part-attributes", "part-name"})
_BOUNDARY_PRESENTATION_TERMS = frozenset(
    {
        "bezier",
        "color",
        "enclosure",
        "font",
        "image",
        "millimeters",
        "placement",
        "position",
        "rotation",
        "smufl",
        "symbol-formatting",
        "tenths",
        "text-formatting",
    }
)


@dataclass(frozen=True, slots=True)
class TaxonomyAssignment:
    """One declaration's principal family and storage disposition."""

    family: str
    disposition: str


def _source_names(component: dict[str, object]) -> frozenset[str]:
    names: set[str] = set()
    source_file = component.get("source_file")
    if isinstance(source_file, str):
        names.add(Path(source_file).name.casefold())
    source_files = component.get("source_files")
    if isinstance(source_files, list):
        names.update(
            Path(value).name.casefold() for value in source_files if isinstance(value, str)
        )
    return frozenset(names)


def _semantic_terms(component: dict[str, object]) -> frozenset[str]:
    fragments: list[str] = []
    for field in ("name", "path"):
        value = component.get(field)
        if isinstance(value, str):
            fragments.append(value.casefold())
    attributes = component.get("attributes")
    if isinstance(attributes, dict):
        fragments.extend(str(value).casefold() for value in attributes.values())
    text = " ".join(fragments)
    terms = set(re.findall(r"[a-z0-9]+(?:-[a-z0-9]+)*", text))
    return frozenset(terms)


def _has_any(terms: frozenset[str], candidates: frozenset[str]) -> bool:
    return not terms.isdisjoint(candidates)


def _semantic_family(old_family: str, terms: frozenset[str]) -> str:
    if old_family == "task 7h structural layout and credits":
        if _has_any(terms, _CREDIT_TERMS):
            return "credits and defaults"
        return "layout and appearance"

    if old_family == "part and instrument metadata":
        if _has_any(terms, _INSTRUMENT_TERMS):
            return "instruments and performers"
        return "parts and groups"

    if old_family in {"score structure and pitch kinds", "written note and rhythm"}:
        if _has_any(terms, _PITCH_TERMS) and "unpitched" not in terms:
            return "written pitch and accidentals"
        if _has_any(terms, _RHYTHM_TERMS):
            return "rhythm, beams, and tuplets"
        if _has_any(terms, _INSTRUMENT_TERMS):
            return "instruments and performers"
        if _has_any(terms, _NOTE_TERMS):
            return "notes and rests"
        if old_family == "written note and rhythm":
            return "notes and rests"
        return "parts and groups"

    return _DIRECT_FAMILIES.get(old_family, "measures, voices, and time cursor")


def _boundary_family(
    component: dict[str, object], sources: frozenset[str], terms: frozenset[str]
) -> str:
    """Assign validation-only declarations to their semantic responsibility."""

    if "xlink.xsd" in sources:
        return "links, bookmarks, and grouping"
    if "xml.xsd" in sources:
        return "presentation text and shared formatting"
    if component.get("kind") == "xsd-import":
        return "document identity and versions"
    if _has_any(terms, _BOUNDARY_CREDIT_TERMS):
        return "credits and defaults"
    if _has_any(terms, _BOUNDARY_INSTRUMENT_TERMS):
        return "instruments and performers"
    if _has_any(terms, _BOUNDARY_LINK_TERMS):
        return "links, bookmarks, and grouping"
    if _has_any(terms, _BOUNDARY_PART_TERMS):
        return "parts and groups"
    if _has_any(terms, _BOUNDARY_LAYOUT_TERMS):
        return "layout and appearance"
    if _has_any(terms, _BOUNDARY_PRESENTATION_TERMS):
        return "presentation text and shared formatting"
    if "measure-attributes" in terms:
        return "measures, voices, and time cursor"
    return "document identity and versions"


def classify_declaration(
    component: dict[str, object], entry: dict[str, object]
) -> TaxonomyAssignment:
    """Classify one inventory declaration using source, handler, and semantic context."""

    sources = _source_names(component)
    terms = _semantic_terms(component)
    handler_value = entry.get("handler")
    handler = handler_value.casefold() if isinstance(handler_value, str) else ""
    old_family_value = entry.get("family")
    old_family = old_family_value.casefold() if isinstance(old_family_value, str) else ""
    version = component.get("version")

    if "container.xsd" in sources or "container.dtd" in sources:
        return TaxonomyAssignment("mxl packaging", "package")
    if sources.intersection({"opus.xsd", "opus.dtd", "sounds.xsd", "sounds.dtd"}):
        return TaxonomyAssignment("opus and sounds documents", "package")
    if version == "4.1-draft" and "score-timewise" in terms:
        return TaxonomyAssignment("document identity and versions", "standard-deprecated")
    if component.get("kind") in {"dtd-entity", "xsd-import"}:
        family = (
            old_family if old_family in FEATURE_FAMILIES else _semantic_family(old_family, terms)
        )
        if "boundary:validate_musicxml_source" in handler:
            family = "document identity and versions"
        return TaxonomyAssignment(family, "boundary-control")
    if "boundary:validate_musicxml_source" in handler:
        return TaxonomyAssignment(
            _boundary_family(component, sources, terms),
            "boundary-control",
        )
    targets = entry.get("canonical_targets")
    if isinstance(targets, list) and not targets:
        family = (
            old_family if old_family in FEATURE_FAMILIES else _semantic_family(old_family, terms)
        )
        return TaxonomyAssignment(family, "boundary-control")
    if "auxiliary_mapping:map_auxiliary_document" in handler:
        return TaxonomyAssignment("opus and sounds documents", "package")
    if "links_mapping:map_link" in handler:
        return TaxonomyAssignment("links, bookmarks, and grouping", "canonical")
    if old_family in FEATURE_FAMILIES:
        return TaxonomyAssignment(old_family, "canonical")
    return TaxonomyAssignment(_semantic_family(old_family, terms), "canonical")


def reclassify_registry(
    inventory: dict[str, object], registry: dict[str, object]
) -> dict[str, object]:
    """Return a registry copy with only family and disposition reclassified."""

    component_values = inventory.get("components")
    entry_values = registry.get("entries")
    if not isinstance(component_values, list) or not isinstance(entry_values, list):
        raise ValueError("inventory and registry must contain declaration lists")
    components = {
        component["key"]: component
        for component in component_values
        if isinstance(component, dict) and isinstance(component.get("key"), str)
    }
    result = deepcopy(registry)
    result_entries = result.get("entries")
    if not isinstance(result_entries, list):
        raise ValueError("registry entries are invalid")
    for raw_entry in result_entries:
        if not isinstance(raw_entry, dict):
            raise ValueError("registry entry is invalid")
        key = raw_entry.get("component_key")
        if not isinstance(key, str) or key not in components:
            raise ValueError(f"registry entry has no inventory declaration: {key}")
        assignment = classify_declaration(components[key], raw_entry)
        raw_entry["family"] = assignment.family
        raw_entry["disposition"] = assignment.disposition
    return result


def _load_object(path: Path) -> dict[str, object]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object in {path}")
    return cast(dict[str, object], value)


def _build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inventory", type=Path)
    parser.add_argument("--registry", type=Path)
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--check", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    """Report or apply the deterministic taxonomy classification."""

    arguments = _build_argument_parser().parse_args(argv)
    resources = resource_root()
    inventory_path = cast(Path | None, arguments.inventory) or resources / "inventory.json"
    registry_path = cast(Path | None, arguments.registry) or resources / "mapping-registry.json"
    original = _load_object(registry_path)
    result = reclassify_registry(_load_object(inventory_path), original)
    entries = result.get("entries")
    if not isinstance(entries, list):
        raise ValueError("registry entries are invalid")
    families = Counter(entry.get("family") for entry in entries if isinstance(entry, dict))
    dispositions = Counter(entry.get("disposition") for entry in entries if isinstance(entry, dict))
    changed = result != original
    print(f"changed: {changed}")
    print("families:")
    for family, count in sorted(families.items()):
        print(f"  {family}: {count}")
    print("dispositions:")
    for disposition, count in sorted(dispositions.items()):
        print(f"  {disposition}: {count}")
    if arguments.write:
        registry_path.write_text(
            json.dumps(result, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
    if arguments.check and changed:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
