"""Build the declaration-aware losslessness foundation and MXL pilot."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections.abc import Callable
from fractions import Fraction
from pathlib import Path
from typing import cast

from teachmemusic.score.v2.annotations import (
    DirectionMark,
    HarmonyChord,
    HarmonySymbol,
    TechnicalData,
)
from teachmemusic.score.v2.auxiliary import OpusCatalog, OpusItem
from teachmemusic.score.v2.layout import PageLayout, SystemLayout
from teachmemusic.score.v2.links import ExternalLink
from teachmemusic.score.v2.presentation import PresentationNumber, PresentationStyle
from teachmemusic.score.v2.temporal import TemporalEncoding

from .auxiliary_mapping import map_auxiliary_document
from .boundary import validate_musicxml_source
from .contracts import PackageContext, ValidatedMusicXmlDocument
from .losslessness_contract import (
    DeclarationEvidence,
    EvidenceValue,
    LosslessnessEvidenceError,
    LosslessnessEvidenceIndex,
    WitnessEvidence,
    fact_digest,
    render_index,
)
from .losslessness_oracle import (
    ARTICULATIONS_ORACLE_ID,
    ATTRIBUTES_ORACLE_ID,
    AUXILIARY_ORACLE_ID,
    BARLINES_ORACLE_ID,
    CREDITS_ORACLE_ID,
    DIRECTIONS_ORACLE_ID,
    DOCUMENT_IDENTITY_ORACLE_ID,
    DYNAMICS_ORACLE_ID,
    FIGURED_BASS_ORACLE_ID,
    HARMONY_ORACLE_ID,
    HEADER_ORACLE_ID,
    INSTRUMENT_ORACLE_ID,
    LAYOUT_ORACLE_ID,
    LINKS_ORACLE_ID,
    LYRICS_ORACLE_ID,
    MEASURES_ORACLE_ID,
    MXL_ORACLE_ID,
    NOTEHEADS_ORACLE_ID,
    NOTES_ORACLE_ID,
    PARTS_ORACLE_ID,
    PITCH_ORACLE_ID,
    PLAYBACK_ORACLE_ID,
    PRESENTATION_ORACLE_ID,
    RHYTHM_ORACLE_ID,
    TECHNICAL_ORACLE_ID,
    TIES_ORACLE_ID,
    read_articulations_facts,
    read_attributes_facts,
    read_auxiliary_facts,
    read_barlines_facts,
    read_credits_facts,
    read_directions_facts,
    read_document_identity_facts,
    read_dynamics_facts,
    read_figured_bass_facts,
    read_harmony_facts,
    read_header_facts,
    read_instrument_facts,
    read_layout_facts,
    read_links_facts,
    read_lyrics_facts,
    read_measures_facts,
    read_mxl_packaging_facts,
    read_noteheads_facts,
    read_notes_facts,
    read_parts_facts,
    read_pitch_facts,
    read_playback_facts,
    read_presentation_facts,
    read_rhythm_facts,
    read_technical_facts,
    read_ties_facts,
)
from .losslessness_witness import (
    ARTICULATIONS_WITNESS_GENERATOR_ID,
    ATTRIBUTES_WITNESS_GENERATOR_ID,
    AUXILIARY_WITNESS_GENERATOR_ID,
    BARLINES_WITNESS_GENERATOR_ID,
    CREDITS_WITNESS_GENERATOR_ID,
    DIRECTIONS_WITNESS_GENERATOR_ID,
    DOCUMENT_IDENTITY_WITNESS_GENERATOR_ID,
    DYNAMICS_WITNESS_GENERATOR_ID,
    FIGURED_BASS_WITNESS_GENERATOR_ID,
    HARMONY_WITNESS_GENERATOR_ID,
    HEADER_WITNESS_GENERATOR_ID,
    INSTRUMENT_WITNESS_GENERATOR_ID,
    LAYOUT_WITNESS_GENERATOR_ID,
    LINKS_WITNESS_GENERATOR_ID,
    LYRICS_WITNESS_GENERATOR_ID,
    MEASURES_WITNESS_GENERATOR_ID,
    MXL_WITNESS_GENERATOR_ID,
    NOTEHEADS_WITNESS_GENERATOR_ID,
    NOTES_WITNESS_GENERATOR_ID,
    PARTS_WITNESS_GENERATOR_ID,
    PITCH_WITNESS_GENERATOR_ID,
    PLAYBACK_WITNESS_GENERATOR_ID,
    PRESENTATION_WITNESS_GENERATOR_ID,
    RHYTHM_WITNESS_GENERATOR_ID,
    TECHNICAL_WITNESS_GENERATOR_ID,
    TIES_WITNESS_GENERATOR_ID,
    GeneratedWitness,
    generate_articulations_witnesses,
    generate_attributes_witnesses,
    generate_auxiliary_witnesses,
    generate_barlines_witnesses,
    generate_credits_witnesses,
    generate_directions_witnesses,
    generate_document_identity_witnesses,
    generate_dynamics_witnesses,
    generate_figured_bass_witnesses,
    generate_harmony_witnesses,
    generate_header_witnesses,
    generate_instrument_witnesses,
    generate_layout_witnesses,
    generate_links_witnesses,
    generate_lyrics_witnesses,
    generate_measures_witnesses,
    generate_mxl_packaging_witnesses,
    generate_noteheads_witnesses,
    generate_notes_witnesses,
    generate_parts_witnesses,
    generate_pitch_witnesses,
    generate_playback_witnesses,
    generate_presentation_witnesses,
    generate_rhythm_witnesses,
    generate_technical_witnesses,
    generate_ties_witnesses,
)
from .standards import resource_root
from .temporal import map_temporal_score

MXL_PACKAGING_FAMILY = "mxl packaging"
INSTRUMENT_FAMILY = "instruments and performers"
PITCH_FAMILY = "written pitch and accidentals"
FIGURED_BASS_FAMILY = "figured bass"
CREDITS_FAMILY = "credits and defaults"
DOCUMENT_IDENTITY_FAMILY = "document identity and versions"
HEADER_FAMILY = "header and identification"
PARTS_FAMILY = "parts and groups"
MEASURES_FAMILY = "measures, voices, and time cursor"
ATTRIBUTES_FAMILY = "attributes and staff state"
NOTES_FAMILY = "notes and rests"
RHYTHM_FAMILY = "rhythm, beams, and tuplets"
TIES_FAMILY = "ties and spanners"
NOTEHEADS_FAMILY = "noteheads and notations"
ARTICULATIONS_FAMILY = "articulations and ornaments"
TECHNICAL_FAMILY = "technical and instrument-specific notation"
BARLINES_FAMILY = "barlines and navigation"
DIRECTIONS_FAMILY = "directions, text, and tempo"
DYNAMICS_FAMILY = "dynamics"
LYRICS_FAMILY = "lyrics"
HARMONY_FAMILY = "harmony and fret diagrams"
LINKS_FAMILY = "links, bookmarks, and grouping"
AUXILIARY_FAMILY = "opus and sounds documents"
PLAYBACK_FAMILY = "playback, midi, listening, and assessment"
LAYOUT_FAMILY = "layout and appearance"
PRESENTATION_FAMILY = "presentation text and shared formatting"
POSITIVE_TEST_ID = "TEST-MXML-LOSSLESS-001"
MUTATION_TEST_ID = "TEST-MXML-LOSSLESS-002"
INSTRUMENT_POSITIVE_TEST_ID = "TEST-MXML-LOSSLESS-006"
INSTRUMENT_MUTATION_TEST_ID = "TEST-MXML-LOSSLESS-007"
PITCH_POSITIVE_TEST_ID = "TEST-MXML-LOSSLESS-008"
PITCH_MUTATION_TEST_ID = "TEST-MXML-LOSSLESS-009"
FIGURED_BASS_POSITIVE_TEST_ID = "TEST-MXML-LOSSLESS-010"
FIGURED_BASS_MUTATION_TEST_ID = "TEST-MXML-LOSSLESS-011"
CREDITS_POSITIVE_TEST_ID = "TEST-MXML-LOSSLESS-012"
CREDITS_MUTATION_TEST_ID = "TEST-MXML-LOSSLESS-013"
DOCUMENT_IDENTITY_POSITIVE_TEST_ID = "TEST-MXML-LOSSLESS-014"
DOCUMENT_IDENTITY_MUTATION_TEST_ID = "TEST-MXML-LOSSLESS-015"
HEADER_POSITIVE_TEST_ID = "TEST-MXML-LOSSLESS-016"
HEADER_MUTATION_TEST_ID = "TEST-MXML-LOSSLESS-017"
PARTS_POSITIVE_TEST_ID = "TEST-MXML-LOSSLESS-018"
PARTS_MUTATION_TEST_ID = "TEST-MXML-LOSSLESS-019"
MEASURES_POSITIVE_TEST_ID = "TEST-MXML-LOSSLESS-020"
MEASURES_MUTATION_TEST_ID = "TEST-MXML-LOSSLESS-021"
ATTRIBUTES_POSITIVE_TEST_ID = "TEST-MXML-LOSSLESS-022"
ATTRIBUTES_MUTATION_TEST_ID = "TEST-MXML-LOSSLESS-023"
NOTES_POSITIVE_TEST_ID = "TEST-MXML-LOSSLESS-024"
NOTES_MUTATION_TEST_ID = "TEST-MXML-LOSSLESS-025"
RHYTHM_POSITIVE_TEST_ID = "TEST-MXML-LOSSLESS-026"
RHYTHM_MUTATION_TEST_ID = "TEST-MXML-LOSSLESS-027"
TIES_POSITIVE_TEST_ID = "TEST-MXML-LOSSLESS-028"
TIES_MUTATION_TEST_ID = "TEST-MXML-LOSSLESS-029"
NOTEHEADS_POSITIVE_TEST_ID = "TEST-MXML-LOSSLESS-030"
NOTEHEADS_MUTATION_TEST_ID = "TEST-MXML-LOSSLESS-031"
ARTICULATIONS_POSITIVE_TEST_ID = "TEST-MXML-LOSSLESS-032"
ARTICULATIONS_MUTATION_TEST_ID = "TEST-MXML-LOSSLESS-033"
TECHNICAL_POSITIVE_TEST_ID = "TEST-MXML-LOSSLESS-034"
TECHNICAL_MUTATION_TEST_ID = "TEST-MXML-LOSSLESS-035"
BARLINES_POSITIVE_TEST_ID = "TEST-MXML-LOSSLESS-036"
BARLINES_MUTATION_TEST_ID = "TEST-MXML-LOSSLESS-037"
DIRECTIONS_POSITIVE_TEST_ID = "TEST-MXML-LOSSLESS-038"
DIRECTIONS_MUTATION_TEST_ID = "TEST-MXML-LOSSLESS-039"
DYNAMICS_POSITIVE_TEST_ID = "TEST-MXML-LOSSLESS-040"
DYNAMICS_MUTATION_TEST_ID = "TEST-MXML-LOSSLESS-041"
LYRICS_POSITIVE_TEST_ID = "TEST-MXML-LOSSLESS-042"
LYRICS_MUTATION_TEST_ID = "TEST-MXML-LOSSLESS-043"
HARMONY_POSITIVE_TEST_ID = "TEST-MXML-LOSSLESS-044"
HARMONY_MUTATION_TEST_ID = "TEST-MXML-LOSSLESS-045"
LINKS_POSITIVE_TEST_ID = "TEST-MXML-LOSSLESS-046"
LINKS_MUTATION_TEST_ID = "TEST-MXML-LOSSLESS-047"
AUXILIARY_POSITIVE_TEST_ID = "TEST-MXML-LOSSLESS-048"
AUXILIARY_MUTATION_TEST_ID = "TEST-MXML-LOSSLESS-049"
PLAYBACK_POSITIVE_TEST_ID = "TEST-MXML-LOSSLESS-050"
PLAYBACK_MUTATION_TEST_ID = "TEST-MXML-LOSSLESS-051"
LAYOUT_POSITIVE_TEST_ID = "TEST-MXML-LOSSLESS-052"
LAYOUT_MUTATION_TEST_ID = "TEST-MXML-LOSSLESS-053"
PRESENTATION_POSITIVE_TEST_ID = "TEST-MXML-LOSSLESS-054"
PRESENTATION_MUTATION_TEST_ID = "TEST-MXML-LOSSLESS-055"
LOSSLESSNESS_SUITE_GENERATOR_ID = "teachmemusic.musicxml.losslessness-suite/1"
LOSSLESSNESS_SUITE_ORACLE_ID = "teachmemusic.musicxml.oracle-suite/1"


def build_mxl_packaging_pilot(
    *,
    inventory_path: Path | None = None,
    registry_path: Path | None = None,
) -> LosslessnessEvidenceIndex:
    """Build direct proof links for the complete 35-declaration MXL family."""

    resources = resource_root()
    selected_inventory = inventory_path or resources / "inventory.json"
    selected_registry = registry_path or resources / "mapping-registry.json"
    inventory_bytes = selected_inventory.read_bytes()
    registry_bytes = selected_registry.read_bytes()
    inventory = _json_object(inventory_bytes, "declaration inventory")
    registry = _json_object(registry_bytes, "mapping registry")
    components = _index_objects(inventory, "components", "key")
    entries = tuple(
        entry
        for entry in _object_list(registry, "entries")
        if entry.get("family") == MXL_PACKAGING_FAMILY
    )
    witnesses = generate_mxl_packaging_witnesses()
    by_version = {item.standard_version: item for item in witnesses}
    source_facts: dict[str, dict[str, EvidenceValue]] = {}
    canonical_facts: dict[str, dict[str, EvidenceValue]] = {}
    witness_evidence: list[WitnessEvidence] = []
    for witness in witnesses:
        oracle = read_mxl_packaging_facts(witness.data)
        document = validate_musicxml_source(
            witness.data,
            logical_name=f"{witness.witness_id}.mxl",
        )
        source = oracle.fact_map()
        canonical = _canonical_package_facts(document)
        if source != canonical:
            raise LosslessnessEvidenceError(
                f"independent MXL facts disagree for {witness.witness_id}"
            )
        source_facts[witness.witness_id] = source
        canonical_facts[witness.witness_id] = canonical
        witness_evidence.append(
            WitnessEvidence(
                witness_id=witness.witness_id,
                family=witness.family,
                standard_version=witness.standard_version,
                source_format=witness.source_format,
                source_sha256=witness.sha256,
                byte_length=len(witness.data),
                generator_id=MXL_WITNESS_GENERATOR_ID,
                oracle_facts=tuple(sorted(source.items())),
            )
        )

    proofs: list[DeclarationEvidence] = []
    for entry in sorted(entries, key=lambda item: cast(str, item["component_key"])):
        key = cast(str, entry["component_key"])
        component = components.get(key)
        if component is None:
            raise LosslessnessEvidenceError(f"registry key is absent from inventory: {key}")
        version = cast(str, component["version"])
        selected_witness = by_version.get(version)
        if selected_witness is None:
            raise LosslessnessEvidenceError(f"MXL pilot has no witness for {version}")
        selector, basis, fact_names, locator = _proof_recipe(component)
        source_digest = fact_digest(source_facts[selected_witness.witness_id], fact_names)
        canonical_digest = fact_digest(canonical_facts[selected_witness.witness_id], fact_names)
        if source_digest != canonical_digest:
            raise LosslessnessEvidenceError(f"proof facts disagree for {key}")
        proofs.append(
            DeclarationEvidence(
                component_key=key,
                family=MXL_PACKAGING_FAMILY,
                disposition=cast(str, entry["disposition"]),
                witness_id=selected_witness.witness_id,
                standard_version=version,
                source_selector=selector,
                proof_basis=basis,
                fact_names=fact_names,
                source_fact_sha256=source_digest,
                canonical_locator=locator,
                canonical_fact_sha256=canonical_digest,
                positive_test_ids=(POSITIVE_TEST_ID,),
                mutation_test_ids=(MUTATION_TEST_ID,),
                result="passed",
            )
        )

    if len(entries) != 35 or len(proofs) != 35:
        raise LosslessnessEvidenceError("MXL pilot must cover exactly 35 declarations")
    return LosslessnessEvidenceIndex(
        scope="foundation-pilot:mxl-packaging",
        inventory_sha256=hashlib.sha256(inventory_bytes).hexdigest(),
        registry_sha256=hashlib.sha256(registry_bytes).hexdigest(),
        generator_id=MXL_WITNESS_GENERATOR_ID,
        oracle_id=MXL_ORACLE_ID,
        witnesses=tuple(witness_evidence),
        declarations=tuple(proofs),
    )


def build_instrument_family_evidence(
    *,
    inventory_path: Path | None = None,
    registry_path: Path | None = None,
) -> LosslessnessEvidenceIndex:
    """Build direct proof links for all 28 instrument-family declarations."""

    resources = resource_root()
    selected_inventory = inventory_path or resources / "inventory.json"
    selected_registry = registry_path or resources / "mapping-registry.json"
    inventory_bytes = selected_inventory.read_bytes()
    registry_bytes = selected_registry.read_bytes()
    inventory = _json_object(inventory_bytes, "declaration inventory")
    registry = _json_object(registry_bytes, "mapping registry")
    components = _index_objects(inventory, "components", "key")
    entries = tuple(
        entry
        for entry in _object_list(registry, "entries")
        if entry.get("family") == INSTRUMENT_FAMILY
    )
    witnesses = generate_instrument_witnesses()
    by_version = {item.standard_version: item for item in witnesses}
    source_facts: dict[str, dict[str, EvidenceValue]] = {}
    canonical_facts: dict[str, dict[str, EvidenceValue]] = {}
    witness_evidence: list[WitnessEvidence] = []
    for witness in witnesses:
        source = read_instrument_facts(witness.data).fact_map()
        canonical = _instrument_canonical_facts(validate_musicxml_source(witness.data))
        if source != canonical:
            raise LosslessnessEvidenceError(
                f"independent instrument facts disagree for {witness.witness_id}"
            )
        source_facts[witness.witness_id] = source
        canonical_facts[witness.witness_id] = canonical
        witness_evidence.append(
            WitnessEvidence(
                witness_id=witness.witness_id,
                family=witness.family,
                standard_version=witness.standard_version,
                source_format=witness.source_format,
                source_sha256=witness.sha256,
                byte_length=len(witness.data),
                generator_id=INSTRUMENT_WITNESS_GENERATOR_ID,
                oracle_facts=tuple(sorted(source.items())),
            )
        )

    proofs: list[DeclarationEvidence] = []
    for entry in sorted(entries, key=lambda item: cast(str, item["component_key"])):
        key = cast(str, entry["component_key"])
        component = components.get(key)
        if component is None:
            raise LosslessnessEvidenceError(f"registry key is absent from inventory: {key}")
        version = cast(str, component["version"])
        selected_witness = by_version.get(version)
        if selected_witness is None:
            raise LosslessnessEvidenceError(f"instrument evidence has no witness for {version}")
        selector, basis, fact_names, locator = _instrument_proof_recipe(component)
        source_digest = fact_digest(source_facts[selected_witness.witness_id], fact_names)
        canonical_digest = fact_digest(canonical_facts[selected_witness.witness_id], fact_names)
        if source_digest != canonical_digest:
            raise LosslessnessEvidenceError(f"instrument proof facts disagree for {key}")
        proofs.append(
            DeclarationEvidence(
                component_key=key,
                family=INSTRUMENT_FAMILY,
                disposition=cast(str, entry["disposition"]),
                witness_id=selected_witness.witness_id,
                standard_version=version,
                source_selector=selector,
                proof_basis=basis,
                fact_names=fact_names,
                source_fact_sha256=source_digest,
                canonical_locator=locator,
                canonical_fact_sha256=canonical_digest,
                positive_test_ids=(INSTRUMENT_POSITIVE_TEST_ID,),
                mutation_test_ids=(INSTRUMENT_MUTATION_TEST_ID,),
                result="passed",
            )
        )
    if len(entries) != 28 or len(proofs) != 28:
        raise LosslessnessEvidenceError("instrument evidence must cover exactly 28 declarations")
    return LosslessnessEvidenceIndex(
        scope="family:instruments-and-performers",
        inventory_sha256=hashlib.sha256(inventory_bytes).hexdigest(),
        registry_sha256=hashlib.sha256(registry_bytes).hexdigest(),
        generator_id=INSTRUMENT_WITNESS_GENERATOR_ID,
        oracle_id=INSTRUMENT_ORACLE_ID,
        witnesses=tuple(witness_evidence),
        declarations=tuple(proofs),
    )


def build_pitch_family_evidence(
    *,
    inventory_path: Path | None = None,
    registry_path: Path | None = None,
) -> LosslessnessEvidenceIndex:
    """Build direct proof links for all 73 written-pitch declarations."""

    return _build_score_family_evidence(
        family=PITCH_FAMILY,
        expected_count=73,
        witnesses=generate_pitch_witnesses(),
        generator_id=PITCH_WITNESS_GENERATOR_ID,
        oracle_id=PITCH_ORACLE_ID,
        source_reader=lambda data: read_pitch_facts(data).fact_map(),
        canonical_projector=_pitch_canonical_facts,
        recipe=_pitch_proof_recipe,
        positive_test_id=PITCH_POSITIVE_TEST_ID,
        mutation_test_id=PITCH_MUTATION_TEST_ID,
        inventory_path=inventory_path,
        registry_path=registry_path,
    )


def build_figured_bass_family_evidence(
    *,
    inventory_path: Path | None = None,
    registry_path: Path | None = None,
) -> LosslessnessEvidenceIndex:
    """Build direct proof links for all 93 figured-bass declarations."""

    return _build_score_family_evidence(
        family=FIGURED_BASS_FAMILY,
        expected_count=93,
        witnesses=generate_figured_bass_witnesses(),
        generator_id=FIGURED_BASS_WITNESS_GENERATOR_ID,
        oracle_id=FIGURED_BASS_ORACLE_ID,
        source_reader=lambda data: read_figured_bass_facts(data).fact_map(),
        canonical_projector=_figured_bass_canonical_facts,
        recipe=_figured_bass_proof_recipe,
        positive_test_id=FIGURED_BASS_POSITIVE_TEST_ID,
        mutation_test_id=FIGURED_BASS_MUTATION_TEST_ID,
        inventory_path=inventory_path,
        registry_path=registry_path,
    )


def build_credits_family_evidence(
    *,
    inventory_path: Path | None = None,
    registry_path: Path | None = None,
) -> LosslessnessEvidenceIndex:
    """Build direct proof links for all 94 credits/defaults declarations."""

    return _build_score_family_evidence(
        family=CREDITS_FAMILY,
        expected_count=94,
        witnesses=generate_credits_witnesses(),
        generator_id=CREDITS_WITNESS_GENERATOR_ID,
        oracle_id=CREDITS_ORACLE_ID,
        source_reader=lambda data: read_credits_facts(data).fact_map(),
        canonical_projector=_credits_canonical_facts,
        recipe=_credits_proof_recipe,
        positive_test_id=CREDITS_POSITIVE_TEST_ID,
        mutation_test_id=CREDITS_MUTATION_TEST_ID,
        inventory_path=inventory_path,
        registry_path=registry_path,
    )


def build_document_identity_family_evidence(
    *,
    inventory_path: Path | None = None,
    registry_path: Path | None = None,
) -> LosslessnessEvidenceIndex:
    """Build direct proof links for all 210 document-identity declarations."""

    return _build_score_family_evidence(
        family=DOCUMENT_IDENTITY_FAMILY,
        expected_count=210,
        witnesses=generate_document_identity_witnesses(),
        generator_id=DOCUMENT_IDENTITY_WITNESS_GENERATOR_ID,
        oracle_id=DOCUMENT_IDENTITY_ORACLE_ID,
        source_reader=lambda data: read_document_identity_facts(data).fact_map(),
        canonical_projector=_document_identity_canonical_facts,
        recipe=_document_identity_proof_recipe,
        positive_test_id=DOCUMENT_IDENTITY_POSITIVE_TEST_ID,
        mutation_test_id=DOCUMENT_IDENTITY_MUTATION_TEST_ID,
        inventory_path=inventory_path,
        registry_path=registry_path,
    )


def build_header_family_evidence(
    *,
    inventory_path: Path | None = None,
    registry_path: Path | None = None,
) -> LosslessnessEvidenceIndex:
    """Build direct proof links for all 180 header declarations."""

    return _build_score_family_evidence(
        family=HEADER_FAMILY,
        expected_count=180,
        witnesses=generate_header_witnesses(),
        generator_id=HEADER_WITNESS_GENERATOR_ID,
        oracle_id=HEADER_ORACLE_ID,
        source_reader=lambda data: read_header_facts(data).fact_map(),
        canonical_projector=_header_canonical_facts,
        recipe=_header_proof_recipe,
        positive_test_id=HEADER_POSITIVE_TEST_ID,
        mutation_test_id=HEADER_MUTATION_TEST_ID,
        inventory_path=inventory_path,
        registry_path=registry_path,
    )


def build_parts_family_evidence(
    *,
    inventory_path: Path | None = None,
    registry_path: Path | None = None,
) -> LosslessnessEvidenceIndex:
    """Build direct proof links for all 397 part/group declarations."""

    return _build_score_family_evidence(
        family=PARTS_FAMILY,
        expected_count=397,
        witnesses=generate_parts_witnesses(),
        generator_id=PARTS_WITNESS_GENERATOR_ID,
        oracle_id=PARTS_ORACLE_ID,
        source_reader=lambda data: read_parts_facts(data).fact_map(),
        canonical_projector=_parts_canonical_facts,
        recipe=_parts_proof_recipe,
        positive_test_id=PARTS_POSITIVE_TEST_ID,
        mutation_test_id=PARTS_MUTATION_TEST_ID,
        witness_selector=_parts_witness_for_component,
        inventory_path=inventory_path,
        registry_path=registry_path,
    )


def build_measures_family_evidence(
    *, inventory_path: Path | None = None, registry_path: Path | None = None
) -> LosslessnessEvidenceIndex:
    """Build direct proof links for all 1,971 measure/cursor declarations."""

    return _build_score_family_evidence(
        family=MEASURES_FAMILY,
        expected_count=1971,
        witnesses=generate_measures_witnesses(),
        generator_id=MEASURES_WITNESS_GENERATOR_ID,
        oracle_id=MEASURES_ORACLE_ID,
        source_reader=lambda data: read_measures_facts(data).fact_map(),
        canonical_projector=_measures_canonical_facts,
        recipe=_measures_proof_recipe,
        positive_test_id=MEASURES_POSITIVE_TEST_ID,
        mutation_test_id=MEASURES_MUTATION_TEST_ID,
        witness_selector=_temporal_witness_for_component,
        inventory_path=inventory_path,
        registry_path=registry_path,
    )


def build_attributes_family_evidence(
    *, inventory_path: Path | None = None, registry_path: Path | None = None
) -> LosslessnessEvidenceIndex:
    """Build direct proof links for all 862 attribute/staff declarations."""

    return _build_score_family_evidence(
        family=ATTRIBUTES_FAMILY,
        expected_count=862,
        witnesses=generate_attributes_witnesses(),
        generator_id=ATTRIBUTES_WITNESS_GENERATOR_ID,
        oracle_id=ATTRIBUTES_ORACLE_ID,
        source_reader=lambda data: read_attributes_facts(data).fact_map(),
        canonical_projector=_attributes_canonical_facts,
        recipe=_attributes_proof_recipe,
        positive_test_id=ATTRIBUTES_POSITIVE_TEST_ID,
        mutation_test_id=ATTRIBUTES_MUTATION_TEST_ID,
        inventory_path=inventory_path,
        registry_path=registry_path,
    )


def build_notes_family_evidence(
    *, inventory_path: Path | None = None, registry_path: Path | None = None
) -> LosslessnessEvidenceIndex:
    """Build direct proof links for all 595 note/rest declarations."""

    return _build_score_family_evidence(
        family=NOTES_FAMILY,
        expected_count=595,
        witnesses=generate_notes_witnesses(),
        generator_id=NOTES_WITNESS_GENERATOR_ID,
        oracle_id=NOTES_ORACLE_ID,
        source_reader=lambda data: read_notes_facts(data).fact_map(),
        canonical_projector=_notes_canonical_facts,
        recipe=_notes_proof_recipe,
        positive_test_id=NOTES_POSITIVE_TEST_ID,
        mutation_test_id=NOTES_MUTATION_TEST_ID,
        inventory_path=inventory_path,
        registry_path=registry_path,
    )


def build_rhythm_family_evidence(
    *, inventory_path: Path | None = None, registry_path: Path | None = None
) -> LosslessnessEvidenceIndex:
    """Build direct proof links for all 123 rhythm/beam/tuplet declarations."""

    return _build_score_family_evidence(
        family=RHYTHM_FAMILY,
        expected_count=123,
        witnesses=generate_rhythm_witnesses(),
        generator_id=RHYTHM_WITNESS_GENERATOR_ID,
        oracle_id=RHYTHM_ORACLE_ID,
        source_reader=lambda data: read_rhythm_facts(data).fact_map(),
        canonical_projector=_rhythm_canonical_facts,
        recipe=_rhythm_proof_recipe,
        positive_test_id=RHYTHM_POSITIVE_TEST_ID,
        mutation_test_id=RHYTHM_MUTATION_TEST_ID,
        inventory_path=inventory_path,
        registry_path=registry_path,
    )


def build_ties_family_evidence(
    *, inventory_path: Path | None = None, registry_path: Path | None = None
) -> LosslessnessEvidenceIndex:
    """Build direct proof links for all 701 tie/spanner declarations."""

    return _build_score_family_evidence(
        family=TIES_FAMILY,
        expected_count=701,
        witnesses=generate_ties_witnesses(),
        generator_id=TIES_WITNESS_GENERATOR_ID,
        oracle_id=TIES_ORACLE_ID,
        source_reader=lambda data: read_ties_facts(data).fact_map(),
        canonical_projector=_ties_canonical_facts,
        recipe=_ties_proof_recipe,
        positive_test_id=TIES_POSITIVE_TEST_ID,
        mutation_test_id=TIES_MUTATION_TEST_ID,
        inventory_path=inventory_path,
        registry_path=registry_path,
    )


def build_noteheads_family_evidence(
    *, inventory_path: Path | None = None, registry_path: Path | None = None
) -> LosslessnessEvidenceIndex:
    """Build direct proof links for all 479 notehead/notation declarations."""

    return _build_score_family_evidence(
        family=NOTEHEADS_FAMILY,
        expected_count=479,
        witnesses=generate_noteheads_witnesses(),
        generator_id=NOTEHEADS_WITNESS_GENERATOR_ID,
        oracle_id=NOTEHEADS_ORACLE_ID,
        source_reader=lambda data: read_noteheads_facts(data).fact_map(),
        canonical_projector=_noteheads_canonical_facts,
        recipe=_noteheads_proof_recipe,
        positive_test_id=NOTEHEADS_POSITIVE_TEST_ID,
        mutation_test_id=NOTEHEADS_MUTATION_TEST_ID,
        inventory_path=inventory_path,
        registry_path=registry_path,
    )


def build_articulations_family_evidence(
    *, inventory_path: Path | None = None, registry_path: Path | None = None
) -> LosslessnessEvidenceIndex:
    """Build direct proof links for all 802 articulation/ornament declarations."""

    return _build_score_family_evidence(
        family=ARTICULATIONS_FAMILY,
        expected_count=802,
        witnesses=generate_articulations_witnesses(),
        generator_id=ARTICULATIONS_WITNESS_GENERATOR_ID,
        oracle_id=ARTICULATIONS_ORACLE_ID,
        source_reader=lambda data: read_articulations_facts(data).fact_map(),
        canonical_projector=_articulations_canonical_facts,
        recipe=_articulations_proof_recipe,
        positive_test_id=ARTICULATIONS_POSITIVE_TEST_ID,
        mutation_test_id=ARTICULATIONS_MUTATION_TEST_ID,
        inventory_path=inventory_path,
        registry_path=registry_path,
    )


def build_technical_family_evidence(
    *, inventory_path: Path | None = None, registry_path: Path | None = None
) -> LosslessnessEvidenceIndex:
    """Build direct proof links for all 880 technical-notation declarations."""

    return _build_score_family_evidence(
        family=TECHNICAL_FAMILY,
        expected_count=880,
        witnesses=generate_technical_witnesses(),
        generator_id=TECHNICAL_WITNESS_GENERATOR_ID,
        oracle_id=TECHNICAL_ORACLE_ID,
        source_reader=lambda data: read_technical_facts(data).fact_map(),
        canonical_projector=_technical_canonical_facts,
        recipe=_technical_proof_recipe,
        positive_test_id=TECHNICAL_POSITIVE_TEST_ID,
        mutation_test_id=TECHNICAL_MUTATION_TEST_ID,
        inventory_path=inventory_path,
        registry_path=registry_path,
    )


def build_barlines_family_evidence(
    *, inventory_path: Path | None = None, registry_path: Path | None = None
) -> LosslessnessEvidenceIndex:
    """Build direct proof links for all 464 barline/navigation declarations."""

    return _build_score_family_evidence(
        family=BARLINES_FAMILY,
        expected_count=464,
        witnesses=generate_barlines_witnesses(),
        generator_id=BARLINES_WITNESS_GENERATOR_ID,
        oracle_id=BARLINES_ORACLE_ID,
        source_reader=lambda data: read_barlines_facts(data).fact_map(),
        canonical_projector=_barlines_canonical_facts,
        recipe=_barlines_proof_recipe,
        positive_test_id=BARLINES_POSITIVE_TEST_ID,
        mutation_test_id=BARLINES_MUTATION_TEST_ID,
        inventory_path=inventory_path,
        registry_path=registry_path,
    )


def build_directions_family_evidence(
    *, inventory_path: Path | None = None, registry_path: Path | None = None
) -> LosslessnessEvidenceIndex:
    """Build direct proof links for all 1,024 text/tempo direction declarations."""

    return _build_score_family_evidence(
        family=DIRECTIONS_FAMILY,
        expected_count=1_024,
        witnesses=generate_directions_witnesses(),
        generator_id=DIRECTIONS_WITNESS_GENERATOR_ID,
        oracle_id=DIRECTIONS_ORACLE_ID,
        source_reader=lambda data: read_directions_facts(data).fact_map(),
        canonical_projector=_directions_canonical_facts,
        recipe=_directions_proof_recipe,
        positive_test_id=DIRECTIONS_POSITIVE_TEST_ID,
        mutation_test_id=DIRECTIONS_MUTATION_TEST_ID,
        inventory_path=inventory_path,
        registry_path=registry_path,
    )


def build_dynamics_family_evidence(
    *, inventory_path: Path | None = None, registry_path: Path | None = None
) -> LosslessnessEvidenceIndex:
    """Build direct proof links for all 213 dynamic declarations."""

    return _build_score_family_evidence(
        family=DYNAMICS_FAMILY,
        expected_count=213,
        witnesses=generate_dynamics_witnesses(),
        generator_id=DYNAMICS_WITNESS_GENERATOR_ID,
        oracle_id=DYNAMICS_ORACLE_ID,
        source_reader=lambda data: read_dynamics_facts(data).fact_map(),
        canonical_projector=_dynamics_canonical_facts,
        recipe=_dynamics_proof_recipe,
        positive_test_id=DYNAMICS_POSITIVE_TEST_ID,
        mutation_test_id=DYNAMICS_MUTATION_TEST_ID,
        inventory_path=inventory_path,
        registry_path=registry_path,
    )


def build_lyrics_family_evidence(
    *, inventory_path: Path | None = None, registry_path: Path | None = None
) -> LosslessnessEvidenceIndex:
    """Build direct proof links for all 148 lyric declarations."""

    return _build_score_family_evidence(
        family=LYRICS_FAMILY,
        expected_count=148,
        witnesses=generate_lyrics_witnesses(),
        generator_id=LYRICS_WITNESS_GENERATOR_ID,
        oracle_id=LYRICS_ORACLE_ID,
        source_reader=lambda data: read_lyrics_facts(data).fact_map(),
        canonical_projector=_lyrics_canonical_facts,
        recipe=_lyrics_proof_recipe,
        positive_test_id=LYRICS_POSITIVE_TEST_ID,
        mutation_test_id=LYRICS_MUTATION_TEST_ID,
        inventory_path=inventory_path,
        registry_path=registry_path,
    )


def build_harmony_family_evidence(
    *, inventory_path: Path | None = None, registry_path: Path | None = None
) -> LosslessnessEvidenceIndex:
    """Build direct proof links for all 649 harmony/fret declarations."""

    return _build_score_family_evidence(
        family=HARMONY_FAMILY,
        expected_count=649,
        witnesses=generate_harmony_witnesses(),
        generator_id=HARMONY_WITNESS_GENERATOR_ID,
        oracle_id=HARMONY_ORACLE_ID,
        source_reader=lambda data: read_harmony_facts(data).fact_map(),
        canonical_projector=_harmony_canonical_facts,
        recipe=_harmony_proof_recipe,
        positive_test_id=HARMONY_POSITIVE_TEST_ID,
        mutation_test_id=HARMONY_MUTATION_TEST_ID,
        inventory_path=inventory_path,
        registry_path=registry_path,
    )


def build_links_family_evidence(
    *, inventory_path: Path | None = None, registry_path: Path | None = None
) -> LosslessnessEvidenceIndex:
    """Build direct proof links for all 235 link/bookmark/grouping declarations."""

    return _build_score_family_evidence(
        family=LINKS_FAMILY,
        expected_count=235,
        witnesses=generate_links_witnesses(),
        generator_id=LINKS_WITNESS_GENERATOR_ID,
        oracle_id=LINKS_ORACLE_ID,
        source_reader=lambda data: read_links_facts(data).fact_map(),
        canonical_projector=_links_canonical_facts,
        recipe=_links_proof_recipe,
        positive_test_id=LINKS_POSITIVE_TEST_ID,
        mutation_test_id=LINKS_MUTATION_TEST_ID,
        inventory_path=inventory_path,
        registry_path=registry_path,
    )


def build_auxiliary_family_evidence(
    *, inventory_path: Path | None = None, registry_path: Path | None = None
) -> LosslessnessEvidenceIndex:
    """Build direct proof links for all 348 opus/sounds declarations."""

    return _build_score_family_evidence(
        family=AUXILIARY_FAMILY,
        expected_count=348,
        witnesses=generate_auxiliary_witnesses(),
        generator_id=AUXILIARY_WITNESS_GENERATOR_ID,
        oracle_id=AUXILIARY_ORACLE_ID,
        source_reader=lambda data: read_auxiliary_facts(data).fact_map(),
        canonical_projector=_auxiliary_canonical_facts,
        recipe=_auxiliary_proof_recipe,
        positive_test_id=AUXILIARY_POSITIVE_TEST_ID,
        mutation_test_id=AUXILIARY_MUTATION_TEST_ID,
        witness_selector=_auxiliary_witness_for_component,
        inventory_path=inventory_path,
        registry_path=registry_path,
    )


def build_playback_family_evidence(
    *, inventory_path: Path | None = None, registry_path: Path | None = None
) -> LosslessnessEvidenceIndex:
    """Build direct proof links for all 540 playback/MIDI declarations."""

    return _build_score_family_evidence(
        family=PLAYBACK_FAMILY,
        expected_count=540,
        witnesses=generate_playback_witnesses(),
        generator_id=PLAYBACK_WITNESS_GENERATOR_ID,
        oracle_id=PLAYBACK_ORACLE_ID,
        source_reader=lambda data: read_playback_facts(data).fact_map(),
        canonical_projector=_playback_canonical_facts,
        recipe=_playback_proof_recipe,
        positive_test_id=PLAYBACK_POSITIVE_TEST_ID,
        mutation_test_id=PLAYBACK_MUTATION_TEST_ID,
        inventory_path=inventory_path,
        registry_path=registry_path,
    )


def build_layout_family_evidence(
    *, inventory_path: Path | None = None, registry_path: Path | None = None
) -> LosslessnessEvidenceIndex:
    """Build direct proof links for all 1,388 layout/appearance declarations."""

    return _build_score_family_evidence(
        family=LAYOUT_FAMILY,
        expected_count=1_388,
        witnesses=generate_layout_witnesses(),
        generator_id=LAYOUT_WITNESS_GENERATOR_ID,
        oracle_id=LAYOUT_ORACLE_ID,
        source_reader=lambda data: read_layout_facts(data).fact_map(),
        canonical_projector=_layout_canonical_facts,
        recipe=_layout_proof_recipe,
        positive_test_id=LAYOUT_POSITIVE_TEST_ID,
        mutation_test_id=LAYOUT_MUTATION_TEST_ID,
        inventory_path=inventory_path,
        registry_path=registry_path,
    )


def build_presentation_family_evidence(
    *, inventory_path: Path | None = None, registry_path: Path | None = None
) -> LosslessnessEvidenceIndex:
    """Build direct proof links for all 2,771 presentation declarations."""

    return _build_score_family_evidence(
        family=PRESENTATION_FAMILY,
        expected_count=2_771,
        witnesses=generate_presentation_witnesses(),
        generator_id=PRESENTATION_WITNESS_GENERATOR_ID,
        oracle_id=PRESENTATION_ORACLE_ID,
        source_reader=lambda data: read_presentation_facts(data).fact_map(),
        canonical_projector=_presentation_canonical_facts,
        recipe=_presentation_proof_recipe,
        positive_test_id=PRESENTATION_POSITIVE_TEST_ID,
        mutation_test_id=PRESENTATION_MUTATION_TEST_ID,
        inventory_path=inventory_path,
        registry_path=registry_path,
    )


def _build_score_family_evidence(
    *,
    family: str,
    expected_count: int,
    witnesses: tuple[GeneratedWitness, ...],
    generator_id: str,
    oracle_id: str,
    source_reader: Callable[[bytes], dict[str, EvidenceValue]],
    canonical_projector: Callable[[ValidatedMusicXmlDocument], dict[str, EvidenceValue]],
    recipe: Callable[[dict[str, object]], tuple[str, str, tuple[str, ...], str]],
    positive_test_id: str,
    mutation_test_id: str,
    witness_selector: Callable[[dict[str, object], tuple[GeneratedWitness, ...]], GeneratedWitness]
    | None = None,
    inventory_path: Path | None,
    registry_path: Path | None,
) -> LosslessnessEvidenceIndex:
    resources = resource_root()
    selected_inventory = inventory_path or resources / "inventory.json"
    selected_registry = registry_path or resources / "mapping-registry.json"
    inventory_bytes = selected_inventory.read_bytes()
    registry_bytes = selected_registry.read_bytes()
    components = _index_objects(
        _json_object(inventory_bytes, "declaration inventory"), "components", "key"
    )
    registry = _json_object(registry_bytes, "mapping registry")
    entries = tuple(
        entry for entry in _object_list(registry, "entries") if entry.get("family") == family
    )
    by_version = {item.standard_version: item for item in witnesses}
    source_facts: dict[str, dict[str, EvidenceValue]] = {}
    canonical_facts: dict[str, dict[str, EvidenceValue]] = {}
    witness_evidence: list[WitnessEvidence] = []
    for witness in witnesses:
        source = source_reader(witness.data)
        canonical = canonical_projector(validate_musicxml_source(witness.data))
        if source != canonical:
            raise LosslessnessEvidenceError(
                f"independent {family} facts disagree for {witness.witness_id}: "
                f"source={source!r}; canonical={canonical!r}"
            )
        source_facts[witness.witness_id] = source
        canonical_facts[witness.witness_id] = canonical
        witness_evidence.append(
            WitnessEvidence(
                witness_id=witness.witness_id,
                family=witness.family,
                standard_version=witness.standard_version,
                source_format=witness.source_format,
                source_sha256=witness.sha256,
                byte_length=len(witness.data),
                generator_id=generator_id,
                oracle_facts=tuple(sorted(source.items())),
            )
        )

    proofs: list[DeclarationEvidence] = []
    for entry in sorted(entries, key=lambda item: cast(str, item["component_key"])):
        key = cast(str, entry["component_key"])
        component = components.get(key)
        if component is None:
            raise LosslessnessEvidenceError(f"registry key is absent from inventory: {key}")
        version = cast(str, component["version"])
        selected_witness = (
            witness_selector(component, witnesses)
            if witness_selector is not None
            else by_version.get(version)
        )
        if selected_witness is None:
            raise LosslessnessEvidenceError(f"{family} evidence has no witness for {version}")
        selector, basis, fact_names, locator = recipe(component)
        source_digest = fact_digest(source_facts[selected_witness.witness_id], fact_names)
        canonical_digest = fact_digest(canonical_facts[selected_witness.witness_id], fact_names)
        if source_digest != canonical_digest:
            raise LosslessnessEvidenceError(f"{family} proof facts disagree for {key}")
        proofs.append(
            DeclarationEvidence(
                component_key=key,
                family=family,
                disposition=cast(str, entry["disposition"]),
                witness_id=selected_witness.witness_id,
                standard_version=version,
                source_selector=selector,
                proof_basis=basis,
                fact_names=fact_names,
                source_fact_sha256=source_digest,
                canonical_locator=locator,
                canonical_fact_sha256=canonical_digest,
                positive_test_ids=(positive_test_id,),
                mutation_test_ids=(mutation_test_id,),
                result="passed",
            )
        )
    if len(entries) != expected_count or len(proofs) != expected_count:
        raise LosslessnessEvidenceError(
            f"{family} evidence must cover exactly {expected_count} declarations"
        )
    return LosslessnessEvidenceIndex(
        scope=f"family:{family.replace(' ', '-')}",
        inventory_sha256=hashlib.sha256(inventory_bytes).hexdigest(),
        registry_sha256=hashlib.sha256(registry_bytes).hexdigest(),
        generator_id=generator_id,
        oracle_id=oracle_id,
        witnesses=tuple(witness_evidence),
        declarations=tuple(proofs),
    )


def build_losslessness_evidence(
    *,
    inventory_path: Path | None = None,
    registry_path: Path | None = None,
) -> LosslessnessEvidenceIndex:
    """Combine every completed declaration-aware family evidence set."""

    packaging = build_mxl_packaging_pilot(
        inventory_path=inventory_path,
        registry_path=registry_path,
    )
    instruments = build_instrument_family_evidence(
        inventory_path=inventory_path,
        registry_path=registry_path,
    )
    pitch = build_pitch_family_evidence(
        inventory_path=inventory_path,
        registry_path=registry_path,
    )
    figured_bass = build_figured_bass_family_evidence(
        inventory_path=inventory_path,
        registry_path=registry_path,
    )
    credits = build_credits_family_evidence(
        inventory_path=inventory_path,
        registry_path=registry_path,
    )
    document_identity = build_document_identity_family_evidence(
        inventory_path=inventory_path,
        registry_path=registry_path,
    )
    header = build_header_family_evidence(
        inventory_path=inventory_path,
        registry_path=registry_path,
    )
    parts = build_parts_family_evidence(
        inventory_path=inventory_path,
        registry_path=registry_path,
    )
    measures = build_measures_family_evidence(
        inventory_path=inventory_path,
        registry_path=registry_path,
    )
    attributes = build_attributes_family_evidence(
        inventory_path=inventory_path,
        registry_path=registry_path,
    )
    notes = build_notes_family_evidence(
        inventory_path=inventory_path,
        registry_path=registry_path,
    )
    rhythm = build_rhythm_family_evidence(
        inventory_path=inventory_path,
        registry_path=registry_path,
    )
    ties = build_ties_family_evidence(
        inventory_path=inventory_path,
        registry_path=registry_path,
    )
    noteheads = build_noteheads_family_evidence(
        inventory_path=inventory_path,
        registry_path=registry_path,
    )
    articulations = build_articulations_family_evidence(
        inventory_path=inventory_path,
        registry_path=registry_path,
    )
    technical = build_technical_family_evidence(
        inventory_path=inventory_path,
        registry_path=registry_path,
    )
    barlines = build_barlines_family_evidence(
        inventory_path=inventory_path,
        registry_path=registry_path,
    )
    directions = build_directions_family_evidence(
        inventory_path=inventory_path,
        registry_path=registry_path,
    )
    dynamics = build_dynamics_family_evidence(
        inventory_path=inventory_path,
        registry_path=registry_path,
    )
    lyrics = build_lyrics_family_evidence(
        inventory_path=inventory_path,
        registry_path=registry_path,
    )
    harmony = build_harmony_family_evidence(
        inventory_path=inventory_path,
        registry_path=registry_path,
    )
    links = build_links_family_evidence(
        inventory_path=inventory_path,
        registry_path=registry_path,
    )
    auxiliary = build_auxiliary_family_evidence(
        inventory_path=inventory_path,
        registry_path=registry_path,
    )
    playback = build_playback_family_evidence(
        inventory_path=inventory_path,
        registry_path=registry_path,
    )
    layout = build_layout_family_evidence(
        inventory_path=inventory_path,
        registry_path=registry_path,
    )
    presentation = build_presentation_family_evidence(
        inventory_path=inventory_path,
        registry_path=registry_path,
    )
    families = (
        packaging,
        instruments,
        pitch,
        figured_bass,
        credits,
        document_identity,
        header,
        parts,
        measures,
        attributes,
        notes,
        rhythm,
        ties,
        noteheads,
        articulations,
        technical,
        barlines,
        directions,
        dynamics,
        lyrics,
        harmony,
        links,
        auxiliary,
        playback,
        layout,
        presentation,
    )
    if (
        len({item.inventory_sha256 for item in families}) != 1
        or len({item.registry_sha256 for item in families}) != 1
    ):
        raise LosslessnessEvidenceError("family evidence inputs disagree")
    return LosslessnessEvidenceIndex(
        scope=(
            "families:articulations-and-ornaments,attributes-and-staff-state,"
            "barlines-and-navigation,credits-and-defaults,directions-text-and-tempo,"
            "document-identity-and-versions,dynamics,figured-bass,harmony-and-fret-diagrams,"
            "header-and-identification,instruments-and-performers,links-bookmarks-and-grouping,"
            "lyrics,measures-voices-and-time-cursor,mxl-packaging,noteheads-and-notations,"
            "layout-and-appearance,notes-and-rests,opus-and-sounds-documents,parts-and-groups,"
            "playback-midi-listening-and-assessment,rhythm-beams-and-tuplets,"
            "presentation-text-and-shared-formatting,technical-and-instrument-specific-notation,"
            "ties-and-spanners,"
            "written-pitch-and-accidentals"
        ),
        inventory_sha256=packaging.inventory_sha256,
        registry_sha256=packaging.registry_sha256,
        generator_id=LOSSLESSNESS_SUITE_GENERATOR_ID,
        oracle_id=LOSSLESSNESS_SUITE_ORACLE_ID,
        witnesses=tuple(
            sorted(
                (item for family in families for item in family.witnesses),
                key=lambda item: item.witness_id,
            )
        ),
        declarations=tuple(
            sorted(
                (item for family in families for item in family.declarations),
                key=lambda item: item.component_key,
            )
        ),
    )


def _canonical_package_facts(document: ValidatedMusicXmlDocument) -> dict[str, EvidenceValue]:
    package = document.package
    if package is None:
        raise LosslessnessEvidenceError("generated MXL did not produce package context")
    return _package_fact_map(package)


def _package_fact_map(package: PackageContext) -> dict[str, EvidenceValue]:
    return {
        "container_present": True,
        "container_standard_version": package.container_standard_version,
        "entries": package.entries,
        "rootfile_count": len(package.rootfiles),
        "rootfile_order": tuple(item.full_path for item in package.rootfiles),
        "rootfile_paths": tuple(item.full_path for item in package.rootfiles),
        "rootfile_media_types": tuple(item.media_type for item in package.rootfiles),
        "selected_rootfile": package.selected_rootfile,
    }


def _instrument_canonical_facts(
    document: ValidatedMusicXmlDocument,
) -> dict[str, EvidenceValue]:
    result = map_temporal_score(document)
    parts = result.score.parts
    instrument_records: list[EvidenceValue] = []
    part_links: list[EvidenceValue] = []
    for part in parts:
        instrument_records.extend(
            (
                part.id,
                instrument.id,
                instrument.name,
                instrument.abbreviation,
                instrument.sound,
                instrument.solo,
                instrument.ensemble,
                instrument.ensemble_size,
                (
                    instrument.playback.virtual.library,
                    instrument.playback.virtual.name,
                )
                if instrument.playback.virtual is not None
                else None,
            )
            for instrument in part.instruments
        )
        part_links.extend(
            (part.id, link.link.href, link.instrument_ids) for link in part.part_links
        )
    return {
        "score_part_count": len(parts),
        "part_ids": tuple(part.id for part in parts),
        "instrument_count": len(instrument_records),
        "instrument_order": tuple(
            cast(tuple[EvidenceValue, ...], item)[1] for item in instrument_records
        ),
        "instrument_records": tuple(instrument_records),
        "part_links": tuple(part_links),
    }


def _pitch_canonical_facts(
    document: ValidatedMusicXmlDocument,
) -> dict[str, EvidenceValue]:
    score = map_temporal_score(document).score
    pitches: list[EvidenceValue] = []
    accidentals: list[EvidenceValue] = []
    rests: list[EvidenceValue] = []
    for part in score.parts:
        for measure in part.measures:
            for event in measure.events:
                if event.pitch is not None:
                    pitches.append(
                        (
                            event.pitch.step,
                            _fraction_fact(event.pitch.alter),
                            event.pitch.octave,
                        )
                    )
                if event.kind == "rest":
                    rests.append(
                        (
                            event.measure_rest,
                            (
                                event.display_position.step,
                                _fraction_fact(event.display_position.alter),
                                event.display_position.octave,
                            )
                            if event.display_position is not None
                            else None,
                        )
                    )
                accidentals.extend(
                    (
                        accidental.value,
                        accidental.cautionary,
                        accidental.editorial,
                        accidental.parentheses,
                        accidental.bracket,
                        accidental.size,
                        accidental.smufl,
                        _presentation_fact(accidental.presentation),
                    )
                    for accidental in event.accidentals
                )
    return {
        "event_count": len(pitches) + len(rests),
        "pitch_records": tuple(pitches),
        "accidental_records": tuple(accidentals),
        "rest_records": tuple(rests),
    }


def _figured_bass_canonical_facts(
    document: ValidatedMusicXmlDocument,
) -> dict[str, EvidenceValue]:
    score = map_temporal_score(document).score
    records: list[tuple[EvidenceValue, ...]] = []
    for part in score.parts:
        for measure in part.measures:
            for bass in measure.figured_bass:
                records.append(
                    (
                        tuple(
                            (
                                figure.prefix,
                                figure.number,
                                figure.suffix,
                                figure.extend_present,
                                figure.extend,
                            )
                            for figure in bass.figures
                        ),
                        _optional_fraction_fact(bass.duration),
                        bass.parentheses,
                        bass.print_object,
                        bass.print_dot,
                        bass.print_spacing,
                        bass.placement,
                        bass.source_id,
                        _presentation_fact(bass.presentation),
                    )
                )
    return {
        "figured_bass_count": len(records),
        "figured_bass_records": tuple(records),
        "figure_records": tuple(item[0] for item in records),
        "duration_records": tuple(item[1] for item in records),
        "control_records": tuple(item[2:9] for item in records),
    }


def _credits_canonical_facts(
    document: ValidatedMusicXmlDocument,
) -> dict[str, EvidenceValue]:
    score = map_temporal_score(document).score
    layout = score.layout
    defaults = layout.defaults if layout is not None else None
    scaling: EvidenceValue = None
    appearance: list[EvidenceValue] = []
    fonts: list[EvidenceValue] = []
    lyric_languages: list[EvidenceValue] = []
    credits: list[EvidenceValue] = []
    if defaults is not None:
        if defaults.scaling is not None:
            scaling = (
                _fraction_fact(defaults.scaling.millimeters),
                _fraction_fact(defaults.scaling.tenths),
            )
        appearance.extend(
            (item.kind, item.value_type, _optional_fraction_fact(item.number), item.text)
            for item in defaults.appearance
        )
        if defaults.music_font is not None:
            fonts.append(("music-font", _presentation_fact(defaults.music_font)))
        if defaults.word_font is not None:
            fonts.append(("word-font", _presentation_fact(defaults.word_font)))
        fonts.extend(
            ("lyric-font", item.number, item.name, _presentation_fact(item.style))
            for item in defaults.lyric_fonts
        )
        lyric_languages.extend(
            (item.number, item.name, item.language) for item in defaults.lyric_languages
        )
    if layout is not None:
        credits.extend(
            (
                credit.page,
                credit.types,
                tuple(
                    (
                        item.kind,
                        item.value,
                        _presentation_fact(item.style),
                        item.mime_type,
                        _optional_fraction_fact(item.width),
                        _optional_fraction_fact(item.height),
                        item.source_id,
                    )
                    for item in credit.items
                ),
                credit.source_id,
            )
            for credit in layout.credits
        )
    staff_sizes = tuple(
        (_optional_fraction_fact(details.size), _optional_fraction_fact(details.scaling))
        for part in score.parts
        for measure in part.measures
        for attributes in measure.attributes
        for details in attributes.staff_details
        if details.size is not None
    )
    return {
        "defaults_present": defaults is not None,
        "scaling": scaling,
        "appearance": tuple(appearance),
        "fonts": tuple(fonts),
        "lyric_languages": tuple(lyric_languages),
        "credits": tuple(credits),
        "staff_sizes": staff_sizes,
    }


def _document_identity_canonical_facts(
    document: ValidatedMusicXmlDocument,
) -> dict[str, EvidenceValue]:
    root = document.root
    part_list = root.find("part-list")
    part_ids = (
        tuple(item.get("id") or "" for item in part_list.findall("score-part"))
        if part_list is not None
        else ()
    )
    measure_count = (
        len(root.findall("measure"))
        if document.kind.value == "score-timewise"
        else sum(len(part.findall("measure")) for part in root.findall("part"))
    )
    return {
        "standard_version": document.standard_version,
        "declared_version": document.declared_version,
        "document_form": document.kind.value,
        "part_ids": part_ids,
        "measure_count": measure_count,
    }


def _header_canonical_facts(
    document: ValidatedMusicXmlDocument,
) -> dict[str, EvidenceValue]:
    score = map_temporal_score(document).score
    metadata = score.metadata
    return {
        "work": (metadata.work_number, score.work_title),
        "movement": (score.movement_number, score.movement_title),
        "creators": score.creators,
        "rights": tuple((item.value, item.text_type) for item in metadata.rights),
        "source": metadata.source,
        "relations": tuple((item.value, item.text_type) for item in metadata.relations),
        "encoding": _encoding_canonical_fact(metadata.encoding),
        "miscellaneous": tuple((item.name, item.value) for item in metadata.miscellaneous),
    }


def _encoding_canonical_fact(value: object) -> EvidenceValue:
    if value is None:
        return None
    encoding = cast(TemporalEncoding, value)
    return (
        encoding.dates,
        tuple((item.value, item.text_type) for item in encoding.encoders),
        encoding.software,
        encoding.descriptions,
        tuple(
            (item.supported, item.element, item.attribute, item.value) for item in encoding.supports
        ),
    )


def _parts_canonical_facts(
    document: ValidatedMusicXmlDocument,
) -> dict[str, EvidenceValue]:
    result = map_temporal_score(document)
    score = result.score
    group_records = tuple(
        (
            item.number,
            item.action,
            item.name,
            item.abbreviation,
            item.symbol,
            item.barline,
            item.source_order,
            item.group_time,
        )
        for item in score.groups
    )
    part_records = tuple(
        (
            part.id,
            part.name,
            part.abbreviation,
            part.groups,
            tuple((item.text_type, item.value) for item in part.metadata.creators),
        )
        for part in score.parts
    )
    instrument_records = tuple(
        (
            part.id,
            instrument.id,
            instrument.name,
            instrument.abbreviation,
            instrument.sound,
            instrument.solo,
            instrument.ensemble,
            instrument.ensemble_size,
            (
                instrument.playback.virtual.library,
                instrument.playback.virtual.name,
            )
            if instrument.playback.virtual is not None
            else None,
        )
        for part in score.parts
        for instrument in part.instruments
    )
    measure_records = tuple(
        (
            part.id,
            measure.number,
            measure.ordinal,
            measure.implicit,
            measure.non_controlling,
            len(measure.events),
        )
        for part in score.parts
        for measure in part.measures
    )
    rest_display_records = tuple(
        (
            part.id,
            event.measure_rest,
            event.display_position.step if event.display_position is not None else None,
            event.display_position.octave if event.display_position is not None else None,
        )
        for part in score.parts
        for measure in part.measures
        for event in measure.events
        if event.kind == "rest"
    )
    return {
        "document_form": result.document_form,
        "score_header": (
            score.metadata.work_number,
            score.work_title,
            score.movement_number,
            score.movement_title,
            score.creators,
            score.metadata.concert_score,
        ),
        "group_records": group_records,
        "part_records": part_records,
        "instrument_records": instrument_records,
        "measure_records": measure_records,
        "rest_display_records": rest_display_records,
    }


def _measures_canonical_facts(
    document: ValidatedMusicXmlDocument,
) -> dict[str, EvidenceValue]:
    score = map_temporal_score(document).score
    return {
        "measure_records": tuple(
            (
                part.id,
                measure.number,
                measure.ordinal,
                measure.implicit,
                measure.non_controlling,
                _fraction_fact(measure.extent),
                measure.staves,
                measure.voices,
                _fraction_fact(measure.score_onset),
            )
            for part in score.parts
            for measure in part.measures
        ),
        "cursor_records": tuple(
            (
                part.id,
                measure.ordinal,
                move.kind,
                _fraction_fact(move.before),
                _fraction_fact(move.after),
                move.source_duration,
                move.staff,
                move.voice,
                move.source_order,
                move.underflow_recovered,
            )
            for part in score.parts
            for measure in part.measures
            for move in measure.cursor_moves
        ),
    }


def _attributes_canonical_facts(
    document: ValidatedMusicXmlDocument,
) -> dict[str, EvidenceValue]:
    score = map_temporal_score(document).score
    records: list[EvidenceValue] = []
    for part in score.parts:
        for measure in part.measures:
            for attributes in measure.attributes:
                records.append(
                    (
                        part.id,
                        measure.ordinal,
                        _fraction_fact(attributes.onset),
                        attributes.divisions,
                        attributes.staves,
                        tuple(
                            (clef.staff, clef.sign, clef.line, clef.octave_change)
                            for clef in attributes.clefs
                        ),
                        tuple((key.fifths, key.mode, key.staff) for key in attributes.keys),
                        tuple(
                            (time.beats, time.beat_types, time.symbol, time.staff)
                            for time in attributes.times
                        ),
                        tuple(
                            (
                                item.staff,
                                item.diatonic,
                                _fraction_fact(item.chromatic),
                                item.octave_change,
                                item.doubling_above,
                            )
                            for item in attributes.transpositions
                        ),
                        tuple(
                            (
                                item.staff,
                                item.staff_type,
                                item.lines,
                                item.show_frets,
                                item.print_object,
                            )
                            for item in attributes.staff_details
                        ),
                        attributes.source_order,
                    )
                )
    return {"attribute_records": tuple(records)}


def _notes_canonical_facts(
    document: ValidatedMusicXmlDocument,
) -> dict[str, EvidenceValue]:
    score = map_temporal_score(document).score
    return {
        "note_records": tuple(
            (
                part.id,
                measure.ordinal,
                event.id,
                event.kind,
                _fraction_fact(event.onset),
                _fraction_fact(event.duration),
                event.source_duration,
                event.staff,
                event.voice,
                event.chord_id,
                event.grace,
                event.cue,
                (
                    event.pitch.step,
                    _fraction_fact(event.pitch.alter),
                    event.pitch.octave,
                )
                if event.pitch is not None
                else None,
                (
                    event.display_position.step,
                    _fraction_fact(event.display_position.alter),
                    event.display_position.octave,
                )
                if event.display_position is not None
                else None,
                event.measure_rest,
                event.source_order,
                (
                    event.grace_timing.slash,
                    _optional_fraction_fact(event.grace_timing.make_time),
                    _optional_fraction_fact(event.grace_timing.steal_previous_percent),
                    _optional_fraction_fact(event.grace_timing.steal_following_percent),
                )
                if event.grace_timing is not None
                else None,
            )
            for part in score.parts
            for measure in part.measures
            for event in measure.events
        )
    }


def _rhythm_canonical_facts(
    document: ValidatedMusicXmlDocument,
) -> dict[str, EvidenceValue]:
    score = map_temporal_score(document).score
    return {
        "rhythm_records": tuple(
            (
                event.id,
                event.written_type,
                event.dots,
                event.time_modification,
                event.normal_type,
                event.normal_dots,
                tuple((beam.number, beam.value, beam.repeater, beam.fan) for beam in event.beams),
                tuple(
                    (
                        tuplet.number,
                        tuplet.action,
                        tuplet.bracket,
                        tuplet.placement,
                        tuplet.show_number,
                        tuplet.show_type,
                        tuplet.line_shape,
                        (
                            tuplet.actual.number,
                            tuplet.actual.note_type,
                            tuplet.actual.dots,
                        )
                        if tuplet.actual is not None
                        else None,
                        (
                            tuplet.normal.number,
                            tuplet.normal.note_type,
                            tuplet.normal.dots,
                        )
                        if tuplet.normal is not None
                        else None,
                    )
                    for tuplet in event.tuplets
                ),
            )
            for part in score.parts
            for measure in part.measures
            for event in measure.events
        )
    }


def _attachment_canonical_facts(
    document: ValidatedMusicXmlDocument,
) -> dict[str, EvidenceValue]:
    score = map_temporal_score(document).score
    noteheads = tuple(
        (
            item.anchor.event_id,
            item.value,
            item.filled,
            item.parentheses,
            item.smufl,
            tuple((segment.kind, segment.text) for segment in item.text),
        )
        for item in score.annotations.noteheads
    )
    marks = tuple(
        (
            item.anchor.event_id,
            item.family,
            item.kind,
            item.text,
            item.source_order,
            item.placement,
            item.mark_type,
            item.smufl,
            item.tremolo_marks,
            tuple(
                (
                    accidental.value,
                    accidental.placement,
                    accidental.bracket,
                    accidental.parentheses,
                    accidental.smufl,
                )
                for accidental in item.accidentals
            ),
            _technical_data_fact(item.kind, item.technical),
            item.number,
        )
        for item in score.annotations.event_marks
    )
    spans = tuple(
        (
            event.id,
            marker.kind,
            marker.number,
            marker.action,
            marker.source_order,
            marker.placement,
            marker.text,
            marker.line_type,
            marker.tremolo_marks,
        )
        for part in score.parts
        for measure in part.measures
        for event in measure.events
        for marker in event.span_markers
    )
    time_spans = tuple(
        (
            marker.kind,
            marker.number,
            marker.action,
            marker.opening,
            _fraction_fact(marker.anchor.score_onset),
            marker.source_order,
            marker.component_order,
            marker.line_type,
            marker.line_end,
            marker.octave_size,
            marker.pedal_line,
        )
        for part in score.parts
        for measure in part.measures
        for marker in measure.time_span_markers
    )

    def mark_family(family: str) -> tuple[EvidenceValue, ...]:
        return tuple(item for item in marks if item[1] == family)

    def span_family(kinds: set[str]) -> tuple[EvidenceValue, ...]:
        return tuple(item for item in spans if str(item[1]) in kinds)

    def topology(kinds: set[str]) -> EvidenceValue:
        return tuple(
            (
                span.kind,
                span.number,
                tuple(
                    (endpoint.action, endpoint.anchor.event_id, endpoint.source_order)
                    for endpoint in span.endpoints
                ),
            )
            for span in score.annotations.spans
            if span.kind in kinds
        )

    tie_kinds = {"sounding-tie", "notated-tie", "slur"}
    notation_kinds = {"glissando", "slide", "other-notation"}
    ornament_kinds = {"wavy-line", "tremolo"}
    technical_kinds = {"hammer-on", "pull-off"}
    return {
        "notehead_records": noteheads,
        "notation_mark_records": mark_family("notation"),
        "articulation_mark_records": mark_family("articulation"),
        "ornament_mark_records": mark_family("ornament"),
        "technical_mark_records": mark_family("technical"),
        "tie_span_records": span_family(tie_kinds),
        "notation_span_records": span_family(notation_kinds),
        "ornament_span_records": span_family(ornament_kinds),
        "technical_span_records": span_family(technical_kinds),
        "tie_topology": topology(tie_kinds),
        "notation_topology": topology(notation_kinds),
        "ornament_topology": topology(ornament_kinds),
        "technical_topology": topology(technical_kinds),
        "time_span_records": time_spans,
        "time_span_topology": tuple(
            (
                span.kind,
                span.number,
                span.opening,
                tuple(
                    (
                        endpoint.action,
                        _fraction_fact(endpoint.anchor.score_onset),
                        endpoint.source_order,
                        endpoint.component_order,
                    )
                    for endpoint in span.endpoints
                ),
            )
            for span in score.annotations.time_spans
        ),
    }


def _technical_data_fact(kind: str, data: TechnicalData | None) -> EvidenceValue:
    if data is None:
        return None
    if data.harmonic is not None:
        harmonic = data.harmonic
        return (
            "harmonic",
            harmonic.harmonic_type,
            harmonic.pitch_type,
            harmonic.print_object,
            harmonic.number,
        )
    if data.bend is not None:
        bend = data.bend
        return (
            "bend",
            _fraction_fact(bend.alter),
            bend.action,
            _optional_fraction_fact(bend.release_offset),
            bend.with_bar,
            bend.with_bar_placement,
        )
    if data.hole is not None:
        hole = data.hole
        return ("hole", hole.hole_type, hole.closed, hole.closed_location, hole.shape)
    if data.arrow is not None:
        arrow = data.arrow
        return (
            "arrow",
            arrow.direction,
            arrow.style,
            arrow.arrowhead_only,
            arrow.circular,
        )
    if data.harmon_mute is not None:
        mute = data.harmon_mute
        return ("harmon-mute", mute.closed, mute.closed_location)
    if kind == "fingering":
        return ("fingering", data.substitution, data.alternate)
    if kind in {"heel", "toe"}:
        return (kind, data.substitution)
    if kind == "tap":
        return ("tap", data.hand)
    return None


def _selected_canonical_attachment_facts(
    document: ValidatedMusicXmlDocument, *names: str
) -> dict[str, EvidenceValue]:
    facts = _attachment_canonical_facts(document)
    return {name: facts[name] for name in names}


def _barlines_canonical_facts(
    document: ValidatedMusicXmlDocument,
) -> dict[str, EvidenceValue]:
    score = map_temporal_score(document).score
    return {
        "barline_records": tuple(
            (
                part.id,
                measure.ordinal,
                _fraction_fact(barline.onset),
                barline.location,
                barline.style,
                barline.repeat_direction,
                barline.repeat_times,
                barline.ending_number,
                barline.ending_type,
                barline.source_order,
                tuple((item.shape, item.orientation, item.source_id) for item in barline.fermatas),
                tuple(
                    (item.kind, item.token, item.source_id, item.smufl)
                    for item in barline.navigation
                ),
                barline.repeat_winged,
                barline.repeat_after_jump,
                barline.ending_text,
                barline.ending_print_object,
                barline.ending_system_relation,
                _optional_fraction_fact(barline.divisions),
                barline.source_id,
            )
            for part in score.parts
            for measure in part.measures
            for barline in measure.barlines
        )
    }


def _canonical_metronome_fact(direction: DirectionMark) -> EvidenceValue:
    data = direction.data
    mark = data.metronome if data is not None else None
    if mark is None:
        return None
    return (
        tuple((item.note_type, item.dots, item.tied_to_previous) for item in mark.beats),
        mark.per_minute,
        mark.arrows,
        tuple(
            (
                item.note_type,
                item.dots,
                tuple((beam.value, beam.number) for beam in item.beams),
                item.tie,
                (
                    item.tuplet.actual_notes,
                    item.tuplet.normal_notes,
                    item.tuplet.normal_type,
                    item.tuplet.normal_dots,
                    item.tuplet.action,
                    item.tuplet.bracket,
                    item.tuplet.show_number,
                )
                if item.tuplet is not None
                else None,
            )
            for item in mark.notes
        ),
        mark.relation,
        mark.parentheses,
    )


def _canonical_direction_record(direction: DirectionMark) -> EvidenceValue:
    anchor = direction.anchor
    return (
        anchor.part_id,
        anchor.measure_id,
        _fraction_fact(anchor.onset),
        _fraction_fact(anchor.score_onset),
        anchor.staff,
        anchor.voice,
        direction.family,
        direction.value,
        direction.placement,
        direction.source_order,
        direction.component_order,
        direction.group_id,
        direction.smufl,
        direction.direction_id,
        direction.direction_type_id,
        direction.source_id,
        direction.print_object,
        direction.system_relation,
        _canonical_metronome_fact(direction),
        direction.directive,
    )


def _directions_canonical_facts(
    document: ValidatedMusicXmlDocument,
) -> dict[str, EvidenceValue]:
    directions = map_temporal_score(document).score.annotations.directions
    return {
        "direction_records": tuple(
            _canonical_direction_record(item) for item in directions if item.family != "dynamic"
        )
    }


def _dynamics_canonical_facts(
    document: ValidatedMusicXmlDocument,
) -> dict[str, EvidenceValue]:
    annotations = map_temporal_score(document).score.annotations
    return {
        "dynamic_direction_records": tuple(
            _canonical_direction_record(item)
            for item in annotations.directions
            if item.family == "dynamic"
        ),
        "dynamic_event_records": tuple(
            (
                item.anchor.event_id,
                item.kind,
                item.text,
                item.source_order,
                item.group_id,
                item.placement,
                item.smufl,
            )
            for item in annotations.event_marks
            if item.family == "dynamic"
        ),
    }


def _lyrics_canonical_facts(
    document: ValidatedMusicXmlDocument,
) -> dict[str, EvidenceValue]:
    lyrics = map_temporal_score(document).score.annotations.lyrics
    return {
        "lyric_records": tuple(
            (
                item.anchor.part_id,
                item.anchor.measure_id,
                item.anchor.event_id,
                item.anchor.staff,
                item.anchor.voice,
                _fraction_fact(item.anchor.score_onset),
                item.number,
                item.name,
                item.syllabic,
                item.text,
                item.source_order,
                tuple(
                    (
                        segment.text,
                        segment.syllabic,
                        segment.elision_before,
                        segment.elision_smufl,
                    )
                    for segment in item.segments
                ),
                item.extend_present,
                item.extend,
                item.laughing,
                item.humming,
                item.end_line,
                item.end_paragraph,
                item.print_object,
                item.time_only,
                item.source_id,
                item.placement,
            )
            for item in lyrics
        )
    }


def _harmony_canonical_facts(
    document: ValidatedMusicXmlDocument,
) -> dict[str, EvidenceValue]:
    score = map_temporal_score(document).score
    records: list[EvidenceValue] = []
    for part in score.parts:
        for measure in part.measures:
            for harmony in measure.harmonies:
                records.append(
                    (
                        part.id,
                        measure.ordinal,
                        _fraction_fact(harmony.anchor.onset),
                        _fraction_fact(harmony.anchor.score_onset),
                        harmony.anchor.staff,
                        harmony.root_step,
                        _fraction_fact(harmony.root_alter),
                        harmony.kind,
                        harmony.kind_text,
                        harmony.source_order,
                        tuple(_harmony_chord_fact(item) for item in harmony.chords),
                        _harmony_frame_fact(harmony),
                        harmony.harmony_type,
                        harmony.print_object,
                        harmony.print_frame,
                        harmony.arrangement,
                        harmony.source_id,
                        harmony.system_relation,
                    )
                )
    return {"harmony_records": tuple(records)}


def _harmony_chord_fact(chord: HarmonyChord) -> EvidenceValue:
    return (
        chord.root_step,
        _fraction_fact(chord.root_alter),
        (
            chord.numeral.root,
            _fraction_fact(chord.numeral.alter),
            chord.numeral.key_fifths,
            chord.numeral.key_mode,
        )
        if chord.numeral is not None
        else None,
        chord.function,
        chord.kind,
        chord.kind_text,
        chord.use_symbols,
        chord.stack_degrees,
        chord.parentheses_degrees,
        chord.bracket_degrees,
        chord.inversion,
        (chord.bass.step, _fraction_fact(chord.bass.alter)) if chord.bass is not None else None,
        tuple(
            (
                degree.value,
                _fraction_fact(degree.alter),
                degree.degree_type,
                degree.print_object,
                degree.symbol,
                degree.value_text,
                degree.type_text,
                degree.plus_minus,
            )
            for degree in chord.degrees
        ),
    )


def _harmony_frame_fact(harmony: HarmonySymbol) -> EvidenceValue:
    frame = harmony.frame
    if frame is None:
        return None
    return (
        frame.strings,
        frame.frets,
        frame.first_fret,
        frame.first_fret_text,
        frame.first_fret_location,
        tuple((note.string, note.fret, note.fingering, note.barre) for note in frame.notes),
        frame.unplayed,
    )


def _link_fact(link: ExternalLink) -> EvidenceValue:
    return (
        link.href,
        link.link_type,
        link.role,
        link.title,
        link.show,
        link.actuate,
        link.name,
        link.element,
        link.position,
    )


def _links_canonical_facts(
    document: ValidatedMusicXmlDocument,
) -> dict[str, EvidenceValue]:
    score = map_temporal_score(document).score
    return {
        "link_grouping_records": tuple(
            (
                part.id,
                measure.ordinal,
                tuple(_link_fact(item) for item in measure.links),
                tuple(
                    (item.id, item.name, item.element, item.position) for item in measure.bookmarks
                ),
                tuple(
                    (
                        item.grouping_type,
                        item.number,
                        item.member_of,
                        tuple((feature.value, feature.feature_type) for feature in item.features),
                    )
                    for item in measure.groupings
                ),
            )
            for part in score.parts
            for measure in part.measures
        )
    }


def _auxiliary_canonical_facts(
    document: ValidatedMusicXmlDocument,
) -> dict[str, EvidenceValue]:
    if document.kind.value in {"opus", "sounds"}:
        auxiliary = map_auxiliary_document(document)
        if isinstance(auxiliary, OpusCatalog):
            record: EvidenceValue = (
                "opus",
                auxiliary.version,
                auxiliary.title,
                tuple(_opus_item_fact(item) for item in auxiliary.items),
            )
        else:
            record = (
                "sounds",
                auxiliary.version,
                tuple(
                    (
                        entry.id,
                        entry.primary,
                        tuple(
                            (
                                mapping.kind,
                                mapping.value,
                                mapping.primary,
                                mapping.ensemble_size,
                            )
                            for mapping in entry.mappings
                        ),
                    )
                    for entry in auxiliary.entries
                ),
            )
    else:
        opus = map_temporal_score(document).score.work_opus
        record = (
            "score-opus",
            document.standard_version,
            _link_fact(opus) if opus is not None else None,
        )
    return {"auxiliary_record": record}


def _opus_item_fact(item: OpusItem) -> EvidenceValue:
    return (
        item.kind,
        _link_fact(item.link) if item.link is not None else None,
        item.new_page,
        item.title,
        tuple(_opus_item_fact(child) for child in item.children),
    )


def _playback_canonical_facts(
    document: ValidatedMusicXmlDocument,
) -> dict[str, EvidenceValue]:
    score = map_temporal_score(document).score
    return {
        "part_playback_records": tuple(
            (
                part.id,
                tuple(
                    (device.instrument_id, device.port, device.name)
                    for instrument in part.instruments
                    for device in instrument.playback.devices
                ),
                tuple(
                    (
                        midi.instrument_id,
                        midi.channel,
                        midi.name,
                        midi.bank,
                        midi.program,
                        midi.unpitched,
                        _optional_fraction_fact(midi.volume),
                        _optional_fraction_fact(midi.pan),
                        _optional_fraction_fact(midi.elevation),
                    )
                    for instrument in part.instruments
                    for midi in instrument.playback.midi
                ),
            )
            for part in score.parts
        ),
        "sound_records": tuple(
            (
                part.id,
                measure.ordinal,
                _fraction_fact(sound.onset),
                _fraction_fact(sound.score_onset),
                sound.source_order,
                _optional_fraction_fact(sound.tempo),
                _optional_fraction_fact(sound.dynamics),
                sound.dacapo,
                sound.pizzicato,
            )
            for part in score.parts
            for measure in part.measures
            for sound in measure.sounds
        ),
    }


def _layout_canonical_facts(
    document: ValidatedMusicXmlDocument,
) -> dict[str, EvidenceValue]:
    score = map_temporal_score(document).score
    defaults = score.layout.defaults if score.layout is not None else None
    score_layout: EvidenceValue = None
    if defaults is not None:
        score_layout = (
            (
                _fraction_fact(defaults.scaling.millimeters),
                _fraction_fact(defaults.scaling.tenths),
            )
            if defaults.scaling is not None
            else None,
            _canonical_page_layout_fact(defaults.page),
            _canonical_system_layout_fact(defaults.system),
            tuple(
                (item.number, _optional_fraction_fact(item.distance)) for item in defaults.staves
            ),
            tuple(
                (
                    item.kind,
                    item.value_type,
                    _optional_fraction_fact(item.number),
                    item.text,
                )
                for item in defaults.appearance
            ),
        )
    return {
        "score_layout_record": score_layout,
        "measure_layout_records": tuple(
            (
                part.id,
                measure.ordinal,
                _optional_fraction_fact(measure.layout.width),
                measure.layout.new_page,
                measure.layout.new_system,
                measure.layout.page_number,
                measure.layout.blank_page,
                _canonical_page_layout_fact(measure.layout.page),
                _canonical_system_layout_fact(measure.layout.system),
                tuple(
                    (item.number, _optional_fraction_fact(item.distance))
                    for item in measure.layout.staves
                ),
                _optional_fraction_fact(measure.layout.measure_distance),
                measure.layout.measure_numbering,
                _optional_fraction_fact(measure.layout.staff_spacing),
            )
            for part in score.parts
            for measure in part.measures
            if measure.layout is not None
        ),
    }


def _canonical_page_layout_fact(value: object | None) -> EvidenceValue:
    if value is None:
        return None
    page = cast(PageLayout, value)
    return (
        _optional_fraction_fact(page.height),
        _optional_fraction_fact(page.width),
        tuple(
            (
                item.kind,
                _fraction_fact(item.left),
                _fraction_fact(item.right),
                _optional_fraction_fact(item.top),
                _optional_fraction_fact(item.bottom),
            )
            for item in page.margins
        ),
    )


def _canonical_system_layout_fact(value: object | None) -> EvidenceValue:
    if value is None:
        return None
    system = cast(SystemLayout, value)
    margins: EvidenceValue = None
    if system.margins is not None:
        margins = (
            system.margins.kind,
            _fraction_fact(system.margins.left),
            _fraction_fact(system.margins.right),
            _optional_fraction_fact(system.margins.top),
            _optional_fraction_fact(system.margins.bottom),
        )
    return (
        margins,
        _optional_fraction_fact(system.system_distance),
        _optional_fraction_fact(system.top_system_distance),
    )


def _presentation_canonical_facts(
    document: ValidatedMusicXmlDocument,
) -> dict[str, EvidenceValue]:
    score = map_temporal_score(document).score
    return {
        "presentation_records": tuple(
            (item.family, item.value, _presentation_fact(item.presentation))
            for item in score.annotations.directions
            if item.family == "words"
        )
    }


def _ties_canonical_facts(
    document: ValidatedMusicXmlDocument,
) -> dict[str, EvidenceValue]:
    return _selected_canonical_attachment_facts(
        document,
        "tie_span_records",
        "tie_topology",
        "time_span_records",
        "time_span_topology",
    )


def _noteheads_canonical_facts(
    document: ValidatedMusicXmlDocument,
) -> dict[str, EvidenceValue]:
    return _selected_canonical_attachment_facts(
        document,
        "notehead_records",
        "notation_mark_records",
        "notation_span_records",
        "notation_topology",
    )


def _articulations_canonical_facts(
    document: ValidatedMusicXmlDocument,
) -> dict[str, EvidenceValue]:
    return _selected_canonical_attachment_facts(
        document,
        "articulation_mark_records",
        "ornament_mark_records",
        "ornament_span_records",
        "ornament_topology",
    )


def _technical_canonical_facts(
    document: ValidatedMusicXmlDocument,
) -> dict[str, EvidenceValue]:
    return _selected_canonical_attachment_facts(
        document,
        "technical_mark_records",
        "technical_span_records",
        "technical_topology",
    )


def _fraction_fact(value: Fraction) -> EvidenceValue:
    return (value.numerator, value.denominator)


def _optional_fraction_fact(value: Fraction | None) -> EvidenceValue:
    return _fraction_fact(value) if value is not None else None


def _presentation_number_fact(value: PresentationNumber | None) -> EvidenceValue:
    if value is None:
        return None
    return (_optional_fraction_fact(value.number), value.keyword)


def _presentation_fact(value: PresentationStyle | None) -> EvidenceValue:
    if value is None:
        return None
    return (
        _optional_fraction_fact(value.default_x),
        _optional_fraction_fact(value.default_y),
        _optional_fraction_fact(value.relative_x),
        _optional_fraction_fact(value.relative_y),
        value.color,
        value.font_family,
        value.font_style,
        _presentation_number_fact(value.font_size),
        value.font_weight,
        value.justify,
        value.halign,
        value.valign,
        value.enclosure,
        _presentation_number_fact(value.letter_spacing),
        _presentation_number_fact(value.line_height),
        value.underline,
        value.overline,
        value.line_through,
        _optional_fraction_fact(value.rotation),
        value.text_direction,
        value.language,
        value.space,
    )


def _proof_recipe(
    component: dict[str, object],
) -> tuple[str, str, tuple[str, ...], str]:
    kind = cast(str, component["kind"])
    name = cast(str, component["name"])
    path = cast(str, component["path"])
    if kind.endswith("attribute") and name == "full-path":
        return (
            "/container/rootfiles/rootfile/@full-path",
            "independent-value-comparison",
            ("rootfile_paths", "selected_rootfile"),
            "PackageContext.rootfiles[*].full_path",
        )
    if kind.endswith("attribute") and name == "media-type":
        return (
            "/container/rootfiles/rootfile/@media-type",
            "independent-value-comparison",
            ("rootfile_media_types",),
            "PackageContext.rootfiles[*].media_type",
        )
    if name == "container":
        return (
            "/container",
            "native-validation-and-independent-structure-comparison",
            ("container_present", "container_standard_version"),
            "PackageContext.container_standard_version",
        )
    if name == "rootfiles":
        return (
            "/container/rootfiles",
            "independent-structure-and-order-comparison",
            ("rootfile_count", "rootfile_order"),
            "PackageContext.rootfiles",
        )
    if name == "rootfile":
        return (
            "/container/rootfiles/rootfile",
            "independent-structure-and-value-comparison",
            ("rootfile_paths", "rootfile_media_types"),
            "PackageContext.rootfiles",
        )
    if kind == "xsd-sequence" and "complexType[1]" in path:
        return (
            "/container/*",
            "native-validation-and-independent-child-sequence-comparison",
            ("container_present", "rootfile_count"),
            "PackageContext.rootfiles",
        )
    if kind == "xsd-sequence" and "complexType[2]" in path:
        return (
            "/container/rootfiles/*",
            "native-validation-and-independent-child-sequence-comparison",
            ("rootfile_count", "rootfile_order"),
            "PackageContext.rootfiles",
        )
    raise LosslessnessEvidenceError(
        f"MXL declaration has no direct proof recipe: {component['key']}"
    )


def _instrument_proof_recipe(
    component: dict[str, object],
) -> tuple[str, str, tuple[str, ...], str]:
    kind = cast(str, component["kind"])
    name = cast(str, component["name"])
    if kind.endswith("attribute") and name == "id":
        return (
            "/score-partwise/part-list/score-part/score-instrument/@id",
            "independent-value-and-identity-comparison",
            ("instrument_order", "instrument_records"),
            "TemporalPart.instruments[*].id",
        )
    if name == "score-part":
        return (
            "/score-partwise/part-list/score-part",
            "native-validation-and-independent-structure-comparison",
            ("score_part_count", "part_ids", "instrument_order"),
            "TemporalScore.parts",
        )
    if name == "score-instrument":
        return (
            "/score-partwise/part-list/score-part/score-instrument",
            "native-validation-and-independent-structure-and-value-comparison",
            ("instrument_count", "instrument_order", "instrument_records"),
            "TemporalPart.instruments",
        )
    if name == "instrument-link":
        return (
            "/score-partwise/part-list/score-part/part-link/instrument-link",
            "native-validation-and-independent-reference-comparison",
            ("part_links",),
            "TemporalPart.part_links[*].instrument_ids",
        )
    if name == "virtual-instrument-data":
        return (
            "schema-group:virtual-instrument-data via "
            "/score-partwise/part-list/score-part/score-instrument/"
            "(instrument-sound|solo|ensemble|virtual-instrument)",
            "native-validation-and-independent-value-comparison",
            ("instrument_records",),
            "TemporalPart.instruments",
        )
    if name in {"virtual-instrument", "ensemble"}:
        return (
            f"/score-partwise/part-list/score-part/score-instrument/{name}",
            "native-validation-and-independent-value-comparison",
            ("instrument_records",),
            "TemporalPart.instruments",
        )
    raise LosslessnessEvidenceError(
        f"instrument declaration has no direct proof recipe: {component['key']}"
    )


def _pitch_proof_recipe(
    component: dict[str, object],
) -> tuple[str, str, tuple[str, ...], str]:
    name = cast(str, component["name"])
    path = cast(str, component["path"])
    if name in {"pitch", "step", "alter", "octave"}:
        return (
            "/score-partwise/part/measure/note/pitch",
            "native-validation-and-independent-pitch-value-comparison",
            ("pitch_records",),
            "TemporalEvent.pitch",
        )
    if name in {"rest", "display-step", "display-octave"}:
        return (
            "/score-partwise/part/measure/note/rest",
            "native-validation-and-independent-rest-display-comparison",
            ("rest_records",),
            "TemporalEvent.measure_rest,display_position",
        )
    if "accidental" in path or name in {
        "accidental",
        "bracket",
        "cautionary",
        "editorial",
        "parentheses",
        "size",
        "yes",
        "no",
        "cue",
        "full",
        "large",
    }:
        return (
            "/score-partwise/part/measure/note/accidental",
            "native-validation-and-independent-accidental-comparison",
            ("accidental_records",),
            "TemporalEvent.accidentals",
        )
    raise LosslessnessEvidenceError(
        f"written-pitch declaration has no direct proof recipe: {component['key']}"
    )


def _figured_bass_proof_recipe(
    component: dict[str, object],
) -> tuple[str, str, tuple[str, ...], str]:
    name = cast(str, component["name"])
    path = cast(str, component["path"])
    if name in {"figure", "prefix", "figure-number", "suffix", "extend"}:
        return (
            "/score-partwise/part/measure/figured-bass/figure",
            "native-validation-and-independent-figure-value-comparison",
            ("figure_records",),
            "FiguredBassAnnotation.figures",
        )
    if name == "duration":
        return (
            "/score-partwise/part/measure/figured-bass/duration",
            "native-validation-and-independent-duration-comparison",
            ("duration_records",),
            "FiguredBassAnnotation.duration",
        )
    if name == "figured-bass":
        return (
            "/score-partwise/part/measure/figured-bass",
            "native-validation-and-independent-structure-and-value-comparison",
            ("figured_bass_count", "figured_bass_records"),
            "TemporalMeasure.figured_bass",
        )
    if (
        name
        in {
            "parentheses",
            "printout",
            "placement",
            "optional-unique-id",
            "yes",
            "no",
        }
        or "figured-bass@" in path
    ):
        return (
            "/score-partwise/part/measure/figured-bass/@*",
            "native-validation-and-independent-control-comparison",
            ("control_records",),
            "FiguredBassAnnotation source controls and presentation",
        )
    raise LosslessnessEvidenceError(
        f"figured-bass declaration has no direct proof recipe: {component['key']}"
    )


def _credits_proof_recipe(
    component: dict[str, object],
) -> tuple[str, str, tuple[str, ...], str]:
    kind = cast(str, component["kind"])
    name = cast(str, component["name"])
    path = cast(str, component["path"])
    if name == "defaults":
        return (
            "/score-partwise/defaults",
            "native-validation-and-independent-defaults-structure-comparison",
            (
                "defaults_present",
                "scaling",
                "appearance",
                "fonts",
                "lyric_languages",
            ),
            "ScoreLayout.defaults",
        )
    if name == "credit":
        return (
            "/score-partwise/credit",
            "native-validation-and-independent-credit-comparison",
            ("credits",),
            "ScoreLayout.credits",
        )
    if name == "scaling" and kind.endswith("attribute"):
        return (
            "/score-partwise/part/measure/attributes/staff-details/staff-size/@scaling",
            "native-validation-and-independent-staff-size-scaling-comparison",
            ("staff_sizes",),
            "TemporalStaffDetails.size,scaling",
        )
    if name == "scaling":
        return (
            "/score-partwise/defaults/scaling",
            "native-validation-and-independent-scaling-comparison",
            ("scaling",),
            "LayoutDefaults.scaling",
        )
    if name in {"appearance", "note-size", "glyph"}:
        selector = "/score-partwise/defaults/appearance"
        if name != "appearance":
            selector = f"{selector}/{name}"
        return (
            selector,
            "native-validation-and-independent-appearance-comparison",
            ("appearance",),
            "LayoutDefaults.appearance",
        )
    if name in {"music-font", "word-font", "lyric-font"} or (
        name in {"name", "number"} and "lyric-font" in path
    ):
        return (
            "/score-partwise/defaults/(music-font|word-font|lyric-font)",
            "native-validation-and-independent-font-comparison",
            ("fonts",),
            "LayoutDefaults music, word, and lyric fonts",
        )
    if (
        name == "lyric-language"
        or name == "lang"
        or (name in {"name", "number"} and "lyric-language" in path)
    ):
        return (
            "/score-partwise/defaults/lyric-language",
            "native-validation-and-independent-language-comparison",
            ("lyric_languages",),
            "LayoutDefaults.lyric_languages",
        )
    raise LosslessnessEvidenceError(
        f"credits/defaults declaration has no direct proof recipe: {component['key']}"
    )


def _document_identity_proof_recipe(
    component: dict[str, object],
) -> tuple[str, str, tuple[str, ...], str]:
    name = cast(str, component["name"])
    if name in {"version", "document-attributes"}:
        return (
            "/score-timewise/@version",
            "native-validation-and-independent-version-comparison",
            ("standard_version", "declared_version"),
            "ValidatedMusicXmlDocument.standard_version,declared_version",
        )
    if name == "score-timewise":
        return (
            "/score-timewise",
            "native-validation-and-independent-document-form-comparison",
            ("document_form", "part_ids", "measure_count"),
            "ValidatedMusicXmlDocument.kind and validated tree structure",
        )
    return (
        "/score-timewise",
        "native-version-validation-and-independent-boundary-comparison",
        ("standard_version", "declared_version", "document_form", "part_ids"),
        "ValidatedMusicXmlDocument validation boundary facts",
    )


def _header_proof_recipe(
    component: dict[str, object],
) -> tuple[str, str, tuple[str, ...], str]:
    name = cast(str, component["name"])
    facts: tuple[str, ...]
    if name in {"work-number"}:
        facts = ("work",)
        selector = "/score-partwise/work/work-number"
    elif name in {"creator"}:
        facts = ("creators",)
        selector = "/score-partwise/identification/creator"
    elif name in {"rights"}:
        facts = ("rights",)
        selector = "/score-partwise/identification/rights"
    elif name in {"source"}:
        facts = ("source",)
        selector = "/score-partwise/identification/source"
    elif name in {"relation"}:
        facts = ("relations",)
        selector = "/score-partwise/identification/relation"
    elif name in {
        "encoding",
        "encoding-date",
        "encoder",
        "software",
        "encoding-description",
        "supports",
        "element",
        "attribute",
        "value",
        "type",
        "yes",
        "no",
    }:
        facts = ("encoding",)
        selector = "/score-partwise/identification/encoding"
    elif name in {"miscellaneous", "miscellaneous-field", "name"}:
        facts = ("miscellaneous",)
        selector = "/score-partwise/identification/miscellaneous"
    else:
        facts = (
            "work",
            "movement",
            "creators",
            "rights",
            "source",
            "relations",
            "encoding",
            "miscellaneous",
        )
        selector = "/score-partwise/(work|movement-number|movement-title|identification)"
    return (
        selector,
        "native-validation-and-independent-header-value-comparison",
        facts,
        "TemporalScore work/movement fields and TemporalScoreMetadata",
    )


def _parts_proof_recipe(
    component: dict[str, object],
) -> tuple[str, str, tuple[str, ...], str]:
    name = cast(str, component["name"])
    facts: tuple[str, ...]
    if name in {
        "part-group",
        "group-name",
        "group-abbreviation",
        "group-symbol",
        "group-barline",
        "group-time",
        "editorial",
        "start",
        "stop",
    }:
        facts = ("group_records",)
        selector = "/score-*/part-list/part-group"
        locator = "TemporalScore.groups"
    elif name in {
        "score-part",
        "part-list",
        "part-name",
        "part-abbreviation",
        "group",
        "part-attributes",
    }:
        facts = ("part_records",)
        selector = "/score-*/part-list/score-part"
        locator = "TemporalScore.parts"
    elif name in {
        "instrument-name",
        "instrument-abbreviation",
        "instrument-sound",
        "solo",
        "virtual-instrument-data",
    }:
        facts = ("instrument_records",)
        selector = "/score-*/part-list/score-part/score-instrument"
        locator = "TemporalPart.instruments"
    elif name in {"display-step-octave", "measure"} and "complexType" in cast(
        str, component["path"]
    ):
        facts = ("rest_display_records",)
        selector = "/score-*/part/measure/note/rest"
        locator = "TemporalEvent.measure_rest,display_position"
    elif name in {
        "score-partwise",
        "score-timewise",
        "part",
        "measure",
        "music-data",
        "note",
        "backup",
        "forward",
    }:
        facts = ("document_form", "part_records", "measure_records")
        selector = "/score-*"
        locator = "TemporalReadResult.document_form and TemporalScore.parts[*].measures"
    elif name in {
        "work",
        "work-title",
        "movement-number",
        "movement-title",
        "identification",
        "creator",
        "defaults",
        "concert-score",
        "score-header",
    }:
        facts = ("score_header",)
        selector = "/score-*/(work|movement-number|movement-title|identification|defaults)"
        locator = "TemporalScore header fields and metadata"
    else:
        facts = (
            "document_form",
            "score_header",
            "group_records",
            "part_records",
            "instrument_records",
            "measure_records",
            "rest_display_records",
        )
        selector = "/score-*"
        locator = "TemporalScore hierarchy"
    return (
        selector,
        "native-validation-and-independent-score-hierarchy-comparison",
        facts,
        locator,
    )


def _parts_witness_for_component(
    component: dict[str, object], witnesses: tuple[GeneratedWitness, ...]
) -> GeneratedWitness:
    version = cast(str, component["version"])
    path = cast(str, component["path"])
    source_files = component.get("source_files")
    timewise_dtd = isinstance(source_files, list) and any(
        isinstance(item, str) and item.endswith("timewise.dtd") for item in source_files
    )
    timewise = (
        cast(str, component["name"]) == "score-timewise"
        or path.startswith("/xs:schema/xs:element[2]")
        or timewise_dtd
    )
    form_token = "TIMEWISE" if timewise else "PARTWISE"
    for witness in witnesses:
        if witness.standard_version == version and form_token in witness.witness_id:
            return witness
    raise LosslessnessEvidenceError(
        f"parts/groups evidence has no {form_token.lower()} witness for {version}"
    )


def _measures_proof_recipe(
    component: dict[str, object],
) -> tuple[str, str, tuple[str, ...], str]:
    return (
        f"{component['kind']}:{component['path']}",
        "native-validation-and-independent-exact-time-comparison",
        ("measure_records", "cursor_records"),
        "TemporalMeasure and TemporalCursorMove",
    )


def _attributes_proof_recipe(
    component: dict[str, object],
) -> tuple[str, str, tuple[str, ...], str]:
    return (
        f"{component['kind']}:{component['path']}",
        "native-validation-and-independent-staff-state-comparison",
        ("attribute_records",),
        "TemporalAttributes",
    )


def _notes_proof_recipe(
    component: dict[str, object],
) -> tuple[str, str, tuple[str, ...], str]:
    return (
        f"{component['kind']}:{component['path']}",
        "native-validation-and-independent-note-identity-comparison",
        ("note_records",),
        "TemporalEvent",
    )


def _rhythm_proof_recipe(
    component: dict[str, object],
) -> tuple[str, str, tuple[str, ...], str]:
    return (
        f"{component['kind']}:{component['path']}",
        "native-validation-and-independent-written-rhythm-comparison",
        ("rhythm_records",),
        "TemporalEvent.beams and TemporalEvent.tuplets",
    )


def _ties_proof_recipe(
    component: dict[str, object],
) -> tuple[str, str, tuple[str, ...], str]:
    return (
        f"{component['kind']}:{component['path']}",
        "native-validation-and-independent-span-topology-comparison",
        ("tie_span_records", "tie_topology", "time_span_records", "time_span_topology"),
        "AnnotationGraph.spans and AnnotationGraph.time_spans",
    )


def _noteheads_proof_recipe(
    component: dict[str, object],
) -> tuple[str, str, tuple[str, ...], str]:
    return (
        f"{component['kind']}:{component['path']}",
        "native-validation-and-independent-notehead-notation-comparison",
        (
            "notehead_records",
            "notation_mark_records",
            "notation_span_records",
            "notation_topology",
        ),
        "AnnotationGraph.noteheads, event_marks, and spans",
    )


def _articulations_proof_recipe(
    component: dict[str, object],
) -> tuple[str, str, tuple[str, ...], str]:
    return (
        f"{component['kind']}:{component['path']}",
        "native-validation-and-independent-articulation-ornament-comparison",
        (
            "articulation_mark_records",
            "ornament_mark_records",
            "ornament_span_records",
            "ornament_topology",
        ),
        "AnnotationGraph.event_marks and ornament spans",
    )


def _technical_proof_recipe(
    component: dict[str, object],
) -> tuple[str, str, tuple[str, ...], str]:
    return (
        f"{component['kind']}:{component['path']}",
        "native-validation-and-independent-technical-notation-comparison",
        ("technical_mark_records", "technical_span_records", "technical_topology"),
        "AnnotationGraph.event_marks and technical spans",
    )


def _barlines_proof_recipe(
    component: dict[str, object],
) -> tuple[str, str, tuple[str, ...], str]:
    return (
        f"{component['kind']}:{component['path']}",
        "native-validation-and-independent-barline-navigation-comparison",
        ("barline_records",),
        "TemporalBarline",
    )


def _directions_proof_recipe(
    component: dict[str, object],
) -> tuple[str, str, tuple[str, ...], str]:
    return (
        f"{component['kind']}:{component['path']}",
        "native-validation-and-independent-ordered-direction-comparison",
        ("direction_records",),
        "AnnotationGraph.directions",
    )


def _dynamics_proof_recipe(
    component: dict[str, object],
) -> tuple[str, str, tuple[str, ...], str]:
    return (
        f"{component['kind']}:{component['path']}",
        "native-validation-and-independent-dynamic-comparison",
        ("dynamic_direction_records", "dynamic_event_records"),
        "AnnotationGraph.directions and AnnotationGraph.event_marks",
    )


def _lyrics_proof_recipe(
    component: dict[str, object],
) -> tuple[str, str, tuple[str, ...], str]:
    return (
        f"{component['kind']}:{component['path']}",
        "native-validation-and-independent-ordered-lyric-comparison",
        ("lyric_records",),
        "AnnotationGraph.lyrics",
    )


def _harmony_proof_recipe(
    component: dict[str, object],
) -> tuple[str, str, tuple[str, ...], str]:
    return (
        f"{component['kind']}:{component['path']}",
        "native-validation-and-independent-harmony-and-frame-comparison",
        ("harmony_records",),
        "TemporalMeasure.harmonies",
    )


def _links_proof_recipe(
    component: dict[str, object],
) -> tuple[str, str, tuple[str, ...], str]:
    return (
        f"{component['kind']}:{component['path']}",
        "native-validation-and-independent-link-bookmark-grouping-comparison",
        ("link_grouping_records",),
        "TemporalMeasure.links,bookmarks,groupings",
    )


def _auxiliary_proof_recipe(
    component: dict[str, object],
) -> tuple[str, str, tuple[str, ...], str]:
    return (
        f"{component['kind']}:{component['path']}",
        "native-validation-and-independent-opus-sounds-package-comparison",
        ("auxiliary_record",),
        "OpusCatalog,SoundCatalog,TemporalScore.work_opus",
    )


def _playback_proof_recipe(
    component: dict[str, object],
) -> tuple[str, str, tuple[str, ...], str]:
    return (
        f"{component['kind']}:{component['path']}",
        "native-validation-and-independent-playback-midi-comparison",
        ("part_playback_records", "sound_records"),
        "TemporalInstrument.playback,TemporalMeasure.sounds",
    )


def _layout_proof_recipe(
    component: dict[str, object],
) -> tuple[str, str, tuple[str, ...], str]:
    return (
        f"{component['kind']}:{component['path']}",
        "native-validation-and-independent-layout-appearance-comparison",
        ("score_layout_record", "measure_layout_records"),
        "ScoreLayout,TemporalMeasure.layout",
    )


def _presentation_proof_recipe(
    component: dict[str, object],
) -> tuple[str, str, tuple[str, ...], str]:
    return (
        f"{component['kind']}:{component['path']}",
        "native-validation-and-independent-presentation-formatting-comparison",
        ("presentation_records",),
        "DirectionMark.presentation",
    )


def _auxiliary_witness_for_component(
    component: dict[str, object], witnesses: tuple[GeneratedWitness, ...]
) -> GeneratedWitness:
    version = cast(str, component["version"])
    key = cast(str, component["key"])
    source_files = component.get("source_files")
    has_sounds_source = isinstance(source_files, list) and any(
        isinstance(item, str) and "sounds" in item for item in source_files
    )
    witness_kind = "SOUNDS" if "sounds" in key or has_sounds_source else "OPUS"
    for witness in witnesses:
        if witness.standard_version == version and witness_kind in witness.witness_id:
            return witness
    raise LosslessnessEvidenceError(
        f"auxiliary evidence has no {witness_kind.lower()} witness for {version}"
    )


def _temporal_witness_for_component(
    component: dict[str, object], witnesses: tuple[GeneratedWitness, ...]
) -> GeneratedWitness:
    version = cast(str, component["version"])
    path = cast(str, component["path"])
    source_files = component.get("source_files")
    timewise_dtd = isinstance(source_files, list) and any(
        isinstance(item, str) and item.endswith("timewise.dtd") for item in source_files
    )
    timewise = path.startswith("/xs:schema/xs:element[2]") or timewise_dtd
    form_token = "TIMEWISE" if timewise else "PARTWISE"
    for witness in witnesses:
        if witness.standard_version == version and form_token in witness.witness_id:
            return witness
    raise LosslessnessEvidenceError(
        f"temporal evidence has no {form_token.lower()} witness for {version}"
    )


def mutated_fact_digest(
    proof: DeclarationEvidence,
    facts: dict[str, EvidenceValue],
) -> str:
    """Return a focused canonical mutation digest for sensitivity tests."""

    mutated = dict(facts)
    name = proof.fact_names[0]
    value = mutated[name]
    if isinstance(value, bool):
        mutated[name] = not value
    elif isinstance(value, int):
        mutated[name] = value + 1
    elif isinstance(value, tuple):
        mutated[name] = tuple(reversed(value)) if len(value) > 1 else value + ("mutation",)
    else:
        mutated[name] = f"{value}-mutation"
    return fact_digest(mutated, proof.fact_names)


def witness_canonical_facts() -> dict[str, dict[str, EvidenceValue]]:
    """Return production fact projections for focused mutation testing."""

    result: dict[str, dict[str, EvidenceValue]] = {}
    for witness in generate_mxl_packaging_witnesses():
        document = validate_musicxml_source(witness.data)
        result[witness.witness_id] = _canonical_package_facts(document)
    return result


def instrument_witness_canonical_facts() -> dict[str, dict[str, EvidenceValue]]:
    """Return canonical instrument projections for mutation testing."""

    return {
        witness.witness_id: _instrument_canonical_facts(validate_musicxml_source(witness.data))
        for witness in generate_instrument_witnesses()
    }


def pitch_witness_canonical_facts() -> dict[str, dict[str, EvidenceValue]]:
    """Return canonical written-pitch projections for mutation testing."""

    return {
        witness.witness_id: _pitch_canonical_facts(validate_musicxml_source(witness.data))
        for witness in generate_pitch_witnesses()
    }


def figured_bass_witness_canonical_facts() -> dict[str, dict[str, EvidenceValue]]:
    """Return canonical figured-bass projections for mutation testing."""

    return {
        witness.witness_id: _figured_bass_canonical_facts(validate_musicxml_source(witness.data))
        for witness in generate_figured_bass_witnesses()
    }


def credits_witness_canonical_facts() -> dict[str, dict[str, EvidenceValue]]:
    """Return canonical credit/default projections for mutation testing."""

    return {
        witness.witness_id: _credits_canonical_facts(validate_musicxml_source(witness.data))
        for witness in generate_credits_witnesses()
    }


def document_identity_witness_canonical_facts() -> dict[str, dict[str, EvidenceValue]]:
    """Return boundary document-identity projections for mutation testing."""

    return {
        witness.witness_id: _document_identity_canonical_facts(
            validate_musicxml_source(witness.data)
        )
        for witness in generate_document_identity_witnesses()
    }


def header_witness_canonical_facts() -> dict[str, dict[str, EvidenceValue]]:
    """Return canonical header projections for mutation testing."""

    return {
        witness.witness_id: _header_canonical_facts(validate_musicxml_source(witness.data))
        for witness in generate_header_witnesses()
    }


def parts_witness_canonical_facts() -> dict[str, dict[str, EvidenceValue]]:
    """Return canonical score-hierarchy projections for mutation testing."""

    return {
        witness.witness_id: _parts_canonical_facts(validate_musicxml_source(witness.data))
        for witness in generate_parts_witnesses()
    }


def measures_witness_canonical_facts() -> dict[str, dict[str, EvidenceValue]]:
    """Return canonical measure/cursor projections for mutation testing."""

    return {
        witness.witness_id: _measures_canonical_facts(validate_musicxml_source(witness.data))
        for witness in generate_measures_witnesses()
    }


def attributes_witness_canonical_facts() -> dict[str, dict[str, EvidenceValue]]:
    """Return canonical attribute projections for mutation testing."""

    return {
        witness.witness_id: _attributes_canonical_facts(validate_musicxml_source(witness.data))
        for witness in generate_attributes_witnesses()
    }


def notes_witness_canonical_facts() -> dict[str, dict[str, EvidenceValue]]:
    """Return canonical note projections for mutation testing."""

    return {
        witness.witness_id: _notes_canonical_facts(validate_musicxml_source(witness.data))
        for witness in generate_notes_witnesses()
    }


def rhythm_witness_canonical_facts() -> dict[str, dict[str, EvidenceValue]]:
    """Return canonical rhythm projections for mutation testing."""

    return {
        witness.witness_id: _rhythm_canonical_facts(validate_musicxml_source(witness.data))
        for witness in generate_rhythm_witnesses()
    }


def ties_witness_canonical_facts() -> dict[str, dict[str, EvidenceValue]]:
    """Return canonical tie/spanner projections for mutation testing."""

    return {
        witness.witness_id: _ties_canonical_facts(validate_musicxml_source(witness.data))
        for witness in generate_ties_witnesses()
    }


def noteheads_witness_canonical_facts() -> dict[str, dict[str, EvidenceValue]]:
    """Return canonical notehead/notation projections for mutation testing."""

    return {
        witness.witness_id: _noteheads_canonical_facts(validate_musicxml_source(witness.data))
        for witness in generate_noteheads_witnesses()
    }


def articulations_witness_canonical_facts() -> dict[str, dict[str, EvidenceValue]]:
    """Return canonical articulation/ornament projections for mutation testing."""

    return {
        witness.witness_id: _articulations_canonical_facts(validate_musicxml_source(witness.data))
        for witness in generate_articulations_witnesses()
    }


def technical_witness_canonical_facts() -> dict[str, dict[str, EvidenceValue]]:
    """Return canonical technical-notation projections for mutation testing."""

    return {
        witness.witness_id: _technical_canonical_facts(validate_musicxml_source(witness.data))
        for witness in generate_technical_witnesses()
    }


def barlines_witness_canonical_facts() -> dict[str, dict[str, EvidenceValue]]:
    """Return canonical barline/navigation projections for mutation testing."""

    return {
        witness.witness_id: _barlines_canonical_facts(validate_musicxml_source(witness.data))
        for witness in generate_barlines_witnesses()
    }


def directions_witness_canonical_facts() -> dict[str, dict[str, EvidenceValue]]:
    """Return canonical text/tempo direction projections for mutation testing."""

    return {
        witness.witness_id: _directions_canonical_facts(validate_musicxml_source(witness.data))
        for witness in generate_directions_witnesses()
    }


def dynamics_witness_canonical_facts() -> dict[str, dict[str, EvidenceValue]]:
    """Return canonical dynamic projections for mutation testing."""

    return {
        witness.witness_id: _dynamics_canonical_facts(validate_musicxml_source(witness.data))
        for witness in generate_dynamics_witnesses()
    }


def lyrics_witness_canonical_facts() -> dict[str, dict[str, EvidenceValue]]:
    """Return canonical lyric projections for mutation testing."""

    return {
        witness.witness_id: _lyrics_canonical_facts(validate_musicxml_source(witness.data))
        for witness in generate_lyrics_witnesses()
    }


def harmony_witness_canonical_facts() -> dict[str, dict[str, EvidenceValue]]:
    """Return canonical harmony/fret-diagram projections for mutation testing."""

    return {
        witness.witness_id: _harmony_canonical_facts(validate_musicxml_source(witness.data))
        for witness in generate_harmony_witnesses()
    }


def links_witness_canonical_facts() -> dict[str, dict[str, EvidenceValue]]:
    """Return canonical link/bookmark/grouping projections for mutation testing."""

    return {
        witness.witness_id: _links_canonical_facts(validate_musicxml_source(witness.data))
        for witness in generate_links_witnesses()
    }


def auxiliary_witness_canonical_facts() -> dict[str, dict[str, EvidenceValue]]:
    """Return canonical opus/sounds projections for mutation testing."""

    return {
        witness.witness_id: _auxiliary_canonical_facts(validate_musicxml_source(witness.data))
        for witness in generate_auxiliary_witnesses()
    }


def playback_witness_canonical_facts() -> dict[str, dict[str, EvidenceValue]]:
    """Return canonical playback/MIDI projections for mutation testing."""

    return {
        witness.witness_id: _playback_canonical_facts(validate_musicxml_source(witness.data))
        for witness in generate_playback_witnesses()
    }


def layout_witness_canonical_facts() -> dict[str, dict[str, EvidenceValue]]:
    """Return canonical layout/appearance projections for mutation testing."""

    return {
        witness.witness_id: _layout_canonical_facts(validate_musicxml_source(witness.data))
        for witness in generate_layout_witnesses()
    }


def presentation_witness_canonical_facts() -> dict[str, dict[str, EvidenceValue]]:
    """Return canonical shared-presentation projections for mutation testing."""

    return {
        witness.witness_id: _presentation_canonical_facts(validate_musicxml_source(witness.data))
        for witness in generate_presentation_witnesses()
    }


def _json_object(data: bytes, label: str) -> dict[str, object]:
    value = json.loads(data)
    if not isinstance(value, dict):
        raise LosslessnessEvidenceError(f"{label} is not a JSON object")
    return cast(dict[str, object], value)


def _object_list(document: dict[str, object], key: str) -> tuple[dict[str, object], ...]:
    value = document.get(key)
    if not isinstance(value, list):
        raise LosslessnessEvidenceError(f"{key} is not a list")
    return tuple(cast(dict[str, object], item) for item in value if isinstance(item, dict))


def _index_objects(
    document: dict[str, object],
    list_key: str,
    key_name: str,
) -> dict[str, dict[str, object]]:
    return {
        cast(str, item[key_name]): item
        for item in _object_list(document, list_key)
        if isinstance(item.get(key_name), str)
    }


def _build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inventory", type=Path)
    parser.add_argument("--registry", type=Path)
    parser.add_argument("--output", type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    """Build and optionally write the deterministic foundation artifact."""

    arguments = _build_argument_parser().parse_args(argv)
    index = build_losslessness_evidence(
        inventory_path=cast(Path | None, arguments.inventory),
        registry_path=cast(Path | None, arguments.registry),
    )
    rendered = render_index(index)
    output = cast(Path | None, arguments.output)
    if output is None:
        print(rendered, end="")
    else:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(rendered, encoding="utf-8")
        print(f"wrote {output}: {len(index.declarations)} declaration proofs")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
