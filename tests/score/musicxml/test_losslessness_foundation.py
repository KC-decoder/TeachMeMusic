"""Tests for the declaration-aware losslessness evidence foundation."""

from __future__ import annotations

import ast
import json
from collections import Counter
from pathlib import Path

import pytest

from teachmemusic.score.musicxml.losslessness_contract import (
    LosslessnessEvidenceError,
    load_losslessness_links,
    render_index,
)
from teachmemusic.score.musicxml.losslessness_evidence import (
    articulations_witness_canonical_facts,
    attributes_witness_canonical_facts,
    auxiliary_witness_canonical_facts,
    barlines_witness_canonical_facts,
    build_articulations_family_evidence,
    build_attributes_family_evidence,
    build_auxiliary_family_evidence,
    build_barlines_family_evidence,
    build_credits_family_evidence,
    build_directions_family_evidence,
    build_document_identity_family_evidence,
    build_dynamics_family_evidence,
    build_figured_bass_family_evidence,
    build_harmony_family_evidence,
    build_header_family_evidence,
    build_instrument_family_evidence,
    build_layout_family_evidence,
    build_links_family_evidence,
    build_losslessness_evidence,
    build_lyrics_family_evidence,
    build_measures_family_evidence,
    build_mxl_packaging_pilot,
    build_noteheads_family_evidence,
    build_notes_family_evidence,
    build_parts_family_evidence,
    build_pitch_family_evidence,
    build_playback_family_evidence,
    build_presentation_family_evidence,
    build_rhythm_family_evidence,
    build_technical_family_evidence,
    build_ties_family_evidence,
    credits_witness_canonical_facts,
    directions_witness_canonical_facts,
    document_identity_witness_canonical_facts,
    dynamics_witness_canonical_facts,
    figured_bass_witness_canonical_facts,
    harmony_witness_canonical_facts,
    header_witness_canonical_facts,
    instrument_witness_canonical_facts,
    layout_witness_canonical_facts,
    links_witness_canonical_facts,
    lyrics_witness_canonical_facts,
    measures_witness_canonical_facts,
    mutated_fact_digest,
    noteheads_witness_canonical_facts,
    notes_witness_canonical_facts,
    parts_witness_canonical_facts,
    pitch_witness_canonical_facts,
    playback_witness_canonical_facts,
    presentation_witness_canonical_facts,
    rhythm_witness_canonical_facts,
    technical_witness_canonical_facts,
    ties_witness_canonical_facts,
    witness_canonical_facts,
)
from teachmemusic.score.musicxml.losslessness_oracle import (
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
from teachmemusic.score.musicxml.losslessness_witness import (
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


def _root() -> Path:
    return Path(__file__).resolve().parents[3]


def test_generated_mxl_witnesses_have_independent_matching_facts() -> None:
    """TEST-MXML-LOSSLESS-001: five versioned witnesses prove all 35 MXL rows."""

    first = generate_mxl_packaging_witnesses()
    second = generate_mxl_packaging_witnesses()
    index = build_mxl_packaging_pilot()

    assert first == second
    assert len({item.sha256 for item in first}) == 5
    assert tuple(item.standard_version for item in first) == (
        "2.0",
        "3.0",
        "3.1",
        "4.0",
        "4.1-draft",
    )
    assert all(
        read_mxl_packaging_facts(item.data).standard_version == item.standard_version
        for item in first
    )
    assert len(index.witnesses) == 5
    assert len(index.declarations) == 35
    assert Counter(item.standard_version for item in index.declarations) == {
        "2.0": 5,
        "3.0": 5,
        "3.1": 5,
        "4.0": 10,
        "4.1-draft": 10,
    }
    assert all(item.source_fact_sha256 == item.canonical_fact_sha256 for item in index.declarations)


def test_every_pilot_proof_detects_a_canonical_mutation() -> None:
    """TEST-MXML-LOSSLESS-002: each declaration link observes a changed fact."""

    index = build_mxl_packaging_pilot()
    canonical = witness_canonical_facts()

    assert all(
        mutated_fact_digest(proof, canonical[proof.witness_id]) != proof.source_fact_sha256
        for proof in index.declarations
    )


def test_generated_instrument_witnesses_prove_all_family_rows() -> None:
    """TEST-MXML-LOSSLESS-006: seven witnesses prove all 28 instrument rows."""

    first = generate_instrument_witnesses()
    second = generate_instrument_witnesses()
    index = build_instrument_family_evidence()

    assert first == second
    assert len({item.sha256 for item in first}) == 7
    assert tuple(item.standard_version for item in first) == (
        "1.0",
        "1.1",
        "2.0",
        "3.0",
        "3.1",
        "4.0",
        "4.1-draft",
    )
    assert all(
        read_instrument_facts(item.data).standard_version == item.standard_version for item in first
    )
    assert len(index.witnesses) == 7
    assert len(index.declarations) == 28
    assert Counter(item.standard_version for item in index.declarations) == {
        "1.0": 3,
        "1.1": 3,
        "2.0": 2,
        "3.0": 3,
        "3.1": 3,
        "4.0": 7,
        "4.1-draft": 7,
    }
    assert all(item.source_fact_sha256 == item.canonical_fact_sha256 for item in index.declarations)


def test_every_instrument_proof_detects_a_canonical_mutation() -> None:
    """TEST-MXML-LOSSLESS-007: all 28 instrument links detect changed facts."""

    index = build_instrument_family_evidence()
    canonical = instrument_witness_canonical_facts()

    assert all(
        mutated_fact_digest(proof, canonical[proof.witness_id]) != proof.source_fact_sha256
        for proof in index.declarations
    )


def test_generated_pitch_witnesses_prove_all_family_rows() -> None:
    """TEST-MXML-LOSSLESS-008: seven witnesses prove all 73 pitch rows."""

    first = generate_pitch_witnesses()
    index = build_pitch_family_evidence()

    assert first == generate_pitch_witnesses()
    assert len({item.sha256 for item in first}) == 7
    assert all(
        read_pitch_facts(item.data).standard_version == item.standard_version for item in first
    )
    assert len(index.witnesses) == 7
    assert len(index.declarations) == 73
    assert Counter(item.standard_version for item in index.declarations) == {
        "1.0": 17,
        "1.1": 24,
        "2.0": 7,
        "3.0": 6,
        "3.1": 6,
        "4.0": 7,
        "4.1-draft": 6,
    }
    assert all(item.source_fact_sha256 == item.canonical_fact_sha256 for item in index.declarations)


def test_every_pitch_proof_detects_a_canonical_mutation() -> None:
    """TEST-MXML-LOSSLESS-009: all 73 written-pitch links detect mutations."""

    index = build_pitch_family_evidence()
    canonical = pitch_witness_canonical_facts()
    assert all(
        mutated_fact_digest(proof, canonical[proof.witness_id]) != proof.source_fact_sha256
        for proof in index.declarations
    )


def test_generated_figured_bass_witnesses_prove_all_family_rows() -> None:
    """TEST-MXML-LOSSLESS-010: seven witnesses prove all 93 figured-bass rows."""

    first = generate_figured_bass_witnesses()
    index = build_figured_bass_family_evidence()

    assert first == generate_figured_bass_witnesses()
    assert len({item.sha256 for item in first}) == 7
    assert all(
        read_figured_bass_facts(item.data).standard_version == item.standard_version
        for item in first
    )
    assert len(index.witnesses) == 7
    assert len(index.declarations) == 93
    assert Counter(item.standard_version for item in index.declarations) == {
        "1.0": 15,
        "1.1": 18,
        "2.0": 11,
        "3.0": 11,
        "3.1": 12,
        "4.0": 13,
        "4.1-draft": 13,
    }
    assert all(item.source_fact_sha256 == item.canonical_fact_sha256 for item in index.declarations)


def test_every_figured_bass_proof_detects_a_canonical_mutation() -> None:
    """TEST-MXML-LOSSLESS-011: all 93 figured-bass links detect mutations."""

    index = build_figured_bass_family_evidence()
    canonical = figured_bass_witness_canonical_facts()
    assert all(
        mutated_fact_digest(proof, canonical[proof.witness_id]) != proof.source_fact_sha256
        for proof in index.declarations
    )


def test_generated_credits_witnesses_prove_all_family_rows() -> None:
    """TEST-MXML-LOSSLESS-012: six witnesses prove all 94 credit/default rows."""

    first = generate_credits_witnesses()
    index = build_credits_family_evidence()

    assert first == generate_credits_witnesses()
    assert len({item.sha256 for item in first}) == 6
    assert all(
        read_credits_facts(item.data).standard_version == item.standard_version for item in first
    )
    assert len(index.witnesses) == 6
    assert len(index.declarations) == 94
    assert Counter(item.standard_version for item in index.declarations) == {
        "1.1": 11,
        "2.0": 15,
        "3.0": 15,
        "3.1": 17,
        "4.0": 18,
        "4.1-draft": 18,
    }
    assert all(item.source_fact_sha256 == item.canonical_fact_sha256 for item in index.declarations)


def test_every_credits_proof_detects_a_canonical_mutation() -> None:
    """TEST-MXML-LOSSLESS-013: all 94 credit/default links detect mutations."""

    index = build_credits_family_evidence()
    canonical = credits_witness_canonical_facts()
    assert all(
        mutated_fact_digest(proof, canonical[proof.witness_id]) != proof.source_fact_sha256
        for proof in index.declarations
    )


def test_generated_document_identity_witnesses_prove_all_family_rows() -> None:
    """TEST-MXML-LOSSLESS-014: five witnesses prove all 210 identity rows."""

    first = generate_document_identity_witnesses()
    index = build_document_identity_family_evidence()

    assert first == generate_document_identity_witnesses()
    assert len({item.sha256 for item in first}) == 5
    assert all(
        read_document_identity_facts(item.data).standard_version == item.standard_version
        for item in first
    )
    assert len(index.witnesses) == 5
    assert len(index.declarations) == 210
    assert Counter(item.standard_version for item in index.declarations) == {
        "2.0": 41,
        "3.0": 37,
        "3.1": 39,
        "4.0": 46,
        "4.1-draft": 47,
    }
    assert all(item.source_fact_sha256 == item.canonical_fact_sha256 for item in index.declarations)


def test_every_document_identity_proof_detects_a_mutation() -> None:
    """TEST-MXML-LOSSLESS-015: all 210 identity links detect mutations."""

    index = build_document_identity_family_evidence()
    canonical = document_identity_witness_canonical_facts()
    assert all(
        mutated_fact_digest(proof, canonical[proof.witness_id]) != proof.source_fact_sha256
        for proof in index.declarations
    )


def test_generated_header_witnesses_prove_all_family_rows() -> None:
    """TEST-MXML-LOSSLESS-016: seven witnesses prove all 180 header rows."""

    first = generate_header_witnesses()
    index = build_header_family_evidence()

    assert first == generate_header_witnesses()
    assert len({item.sha256 for item in first}) == 7
    assert all(read_header_facts(item.data).fact_map() for item in first)
    assert len(index.witnesses) == 7
    assert len(index.declarations) == 180
    assert Counter(item.standard_version for item in index.declarations) == {
        "1.0": 18,
        "1.1": 18,
        "2.0": 27,
        "3.0": 27,
        "3.1": 28,
        "4.0": 28,
        "4.1-draft": 34,
    }
    assert all(item.source_fact_sha256 == item.canonical_fact_sha256 for item in index.declarations)


def test_every_header_proof_detects_a_canonical_mutation() -> None:
    """TEST-MXML-LOSSLESS-017: all 180 header links detect mutations."""

    index = build_header_family_evidence()
    canonical = header_witness_canonical_facts()
    assert all(
        mutated_fact_digest(proof, canonical[proof.witness_id]) != proof.source_fact_sha256
        for proof in index.declarations
    )


def test_generated_parts_witnesses_prove_all_family_rows() -> None:
    """TEST-MXML-LOSSLESS-018: 14 form/version witnesses prove 397 rows."""

    first = generate_parts_witnesses()
    index = build_parts_family_evidence()

    assert first == generate_parts_witnesses()
    assert len({item.sha256 for item in first}) == 14
    assert all(read_parts_facts(item.data).fact_map() for item in first)
    assert len(index.witnesses) == 14
    assert len(index.declarations) == 397
    assert Counter(item.standard_version for item in index.declarations) == {
        "1.0": 33,
        "1.1": 34,
        "2.0": 57,
        "3.0": 66,
        "3.1": 66,
        "4.0": 70,
        "4.1-draft": 71,
    }
    assert all(item.source_fact_sha256 == item.canonical_fact_sha256 for item in index.declarations)


def test_every_parts_proof_detects_a_canonical_mutation() -> None:
    """TEST-MXML-LOSSLESS-019: all 397 part/group links detect mutations."""

    index = build_parts_family_evidence()
    canonical = parts_witness_canonical_facts()
    assert all(
        mutated_fact_digest(proof, canonical[proof.witness_id]) != proof.source_fact_sha256
        for proof in index.declarations
    )


def test_generated_measure_witnesses_prove_all_family_rows() -> None:
    """TEST-MXML-LOSSLESS-020: 14 form/version witnesses prove 1,971 rows."""

    first = generate_measures_witnesses()
    index = build_measures_family_evidence()
    assert first == generate_measures_witnesses()
    assert len({item.sha256 for item in first}) == 14
    assert all(read_measures_facts(item.data).fact_map() for item in first)
    assert len(index.witnesses) == 14
    assert len(index.declarations) == 1_971
    assert Counter(item.standard_version for item in index.declarations) == {
        "1.0": 38,
        "1.1": 46,
        "2.0": 270,
        "3.0": 387,
        "3.1": 455,
        "4.0": 384,
        "4.1-draft": 391,
    }


def test_every_measure_proof_detects_a_canonical_mutation() -> None:
    """TEST-MXML-LOSSLESS-021: all 1,971 measure/cursor links detect mutations."""

    index = build_measures_family_evidence()
    canonical = measures_witness_canonical_facts()
    assert all(
        mutated_fact_digest(proof, canonical[proof.witness_id]) != proof.source_fact_sha256
        for proof in index.declarations
    )


def test_generated_attribute_witnesses_prove_all_family_rows() -> None:
    """TEST-MXML-LOSSLESS-022: seven witnesses prove all 862 attribute rows."""

    first = generate_attributes_witnesses()
    index = build_attributes_family_evidence()
    assert first == generate_attributes_witnesses()
    assert len({item.sha256 for item in first}) == 7
    assert all(read_attributes_facts(item.data).fact_map() for item in first)
    assert len(index.witnesses) == 7
    assert len(index.declarations) == 862
    assert Counter(item.standard_version for item in index.declarations) == {
        "1.0": 41,
        "1.1": 50,
        "2.0": 114,
        "3.0": 149,
        "3.1": 155,
        "4.0": 176,
        "4.1-draft": 177,
    }


def test_every_attribute_proof_detects_a_canonical_mutation() -> None:
    """TEST-MXML-LOSSLESS-023: all 862 attribute/staff links detect mutations."""

    index = build_attributes_family_evidence()
    canonical = attributes_witness_canonical_facts()
    assert all(
        mutated_fact_digest(proof, canonical[proof.witness_id]) != proof.source_fact_sha256
        for proof in index.declarations
    )


def test_generated_note_witnesses_prove_all_family_rows() -> None:
    """TEST-MXML-LOSSLESS-024: seven witnesses prove all 595 note/rest rows."""

    first = generate_notes_witnesses()
    index = build_notes_family_evidence()
    assert first == generate_notes_witnesses()
    assert len({item.sha256 for item in first}) == 7
    assert all(read_notes_facts(item.data).fact_map() for item in first)
    assert len(index.witnesses) == 7
    assert len(index.declarations) == 595
    assert Counter(item.standard_version for item in index.declarations) == {
        "1.0": 13,
        "1.1": 14,
        "2.0": 86,
        "3.0": 112,
        "3.1": 123,
        "4.0": 124,
        "4.1-draft": 123,
    }


def test_every_note_proof_detects_a_canonical_mutation() -> None:
    """TEST-MXML-LOSSLESS-025: all 595 note/rest links detect mutations."""

    index = build_notes_family_evidence()
    canonical = notes_witness_canonical_facts()
    assert all(
        mutated_fact_digest(proof, canonical[proof.witness_id]) != proof.source_fact_sha256
        for proof in index.declarations
    )


def test_generated_rhythm_witnesses_prove_all_family_rows() -> None:
    """TEST-MXML-LOSSLESS-026: seven witnesses prove all 123 rhythm rows."""

    first = generate_rhythm_witnesses()
    index = build_rhythm_family_evidence()
    assert first == generate_rhythm_witnesses()
    assert len({item.sha256 for item in first}) == 7
    assert all(read_rhythm_facts(item.data).fact_map() for item in first)
    assert len(index.witnesses) == 7
    assert len(index.declarations) == 123
    assert Counter(item.standard_version for item in index.declarations) == {
        "1.0": 38,
        "1.1": 45,
        "2.0": 8,
        "3.0": 8,
        "3.1": 8,
        "4.0": 8,
        "4.1-draft": 8,
    }


def test_every_rhythm_proof_detects_a_canonical_mutation() -> None:
    """TEST-MXML-LOSSLESS-027: all 123 rhythm/beam/tuplet links detect mutations."""

    index = build_rhythm_family_evidence()
    canonical = rhythm_witness_canonical_facts()
    assert all(
        mutated_fact_digest(proof, canonical[proof.witness_id]) != proof.source_fact_sha256
        for proof in index.declarations
    )


def test_generated_tie_witnesses_prove_all_family_rows() -> None:
    """TEST-MXML-LOSSLESS-028: seven witnesses prove all 701 span rows."""

    first = generate_ties_witnesses()
    index = build_ties_family_evidence()
    assert first == generate_ties_witnesses()
    assert len({item.sha256 for item in first}) == 7
    assert all(read_ties_facts(item.data).fact_map() for item in first)
    assert len(index.witnesses) == 7
    assert len(index.declarations) == 701
    assert Counter(item.standard_version for item in index.declarations) == {
        "1.0": 116,
        "1.1": 117,
        "2.0": 71,
        "3.0": 87,
        "3.1": 102,
        "4.0": 104,
        "4.1-draft": 104,
    }


def test_every_tie_proof_detects_a_canonical_mutation() -> None:
    """TEST-MXML-LOSSLESS-029: all 701 span links detect mutations."""

    index = build_ties_family_evidence()
    canonical = ties_witness_canonical_facts()
    assert all(
        mutated_fact_digest(proof, canonical[proof.witness_id]) != proof.source_fact_sha256
        for proof in index.declarations
    )


def test_generated_notehead_witnesses_prove_all_family_rows() -> None:
    """TEST-MXML-LOSSLESS-030: seven witnesses prove all 479 notation rows."""

    first = generate_noteheads_witnesses()
    index = build_noteheads_family_evidence()
    assert first == generate_noteheads_witnesses()
    assert len({item.sha256 for item in first}) == 7
    assert all(read_noteheads_facts(item.data).fact_map() for item in first)
    assert len(index.witnesses) == 7
    assert len(index.declarations) == 479
    assert Counter(item.standard_version for item in index.declarations) == {
        "1.0": 94,
        "1.1": 94,
        "2.0": 47,
        "3.0": 51,
        "3.1": 64,
        "4.0": 64,
        "4.1-draft": 65,
    }


def test_every_notehead_proof_detects_a_canonical_mutation() -> None:
    """TEST-MXML-LOSSLESS-031: all 479 notehead/notation links detect mutations."""

    index = build_noteheads_family_evidence()
    canonical = noteheads_witness_canonical_facts()
    assert all(
        mutated_fact_digest(proof, canonical[proof.witness_id]) != proof.source_fact_sha256
        for proof in index.declarations
    )


def test_generated_articulation_witnesses_prove_all_family_rows() -> None:
    """TEST-MXML-LOSSLESS-032: seven witnesses prove all 802 mark rows."""

    first = generate_articulations_witnesses()
    index = build_articulations_family_evidence()
    assert first == generate_articulations_witnesses()
    assert len({item.sha256 for item in first}) == 7
    assert all(read_articulations_facts(item.data).fact_map() for item in first)
    assert len(index.witnesses) == 7
    assert len(index.declarations) == 802
    assert Counter(item.standard_version for item in index.declarations) == {
        "1.0": 277,
        "1.1": 281,
        "2.0": 42,
        "3.0": 46,
        "3.1": 52,
        "4.0": 52,
        "4.1-draft": 52,
    }


def test_every_articulation_proof_detects_a_canonical_mutation() -> None:
    """TEST-MXML-LOSSLESS-033: all 802 articulation links detect mutations."""

    index = build_articulations_family_evidence()
    canonical = articulations_witness_canonical_facts()
    assert all(
        mutated_fact_digest(proof, canonical[proof.witness_id]) != proof.source_fact_sha256
        for proof in index.declarations
    )


def test_generated_technical_witnesses_prove_all_family_rows() -> None:
    """TEST-MXML-LOSSLESS-034: seven witnesses prove all 880 technical rows."""

    first = generate_technical_witnesses()
    index = build_technical_family_evidence()
    assert first == generate_technical_witnesses()
    assert len({item.sha256 for item in first}) == 7
    assert all(read_technical_facts(item.data).fact_map() for item in first)
    assert len(index.witnesses) == 7
    assert len(index.declarations) == 880
    assert Counter(item.standard_version for item in index.declarations) == {
        "1.0": 116,
        "1.1": 129,
        "2.0": 56,
        "3.0": 119,
        "3.1": 148,
        "4.0": 154,
        "4.1-draft": 158,
    }


def test_every_technical_proof_detects_a_canonical_mutation() -> None:
    """TEST-MXML-LOSSLESS-035: all 880 technical links detect mutations."""

    index = build_technical_family_evidence()
    canonical = technical_witness_canonical_facts()
    assert all(
        mutated_fact_digest(proof, canonical[proof.witness_id]) != proof.source_fact_sha256
        for proof in index.declarations
    )


def test_generated_barline_witnesses_prove_all_family_rows() -> None:
    """TEST-MXML-LOSSLESS-036: seven witnesses prove all 464 barline rows."""

    first = generate_barlines_witnesses()
    index = build_barlines_family_evidence()
    assert first == generate_barlines_witnesses()
    assert len({item.sha256 for item in first}) == 7
    assert all(read_barlines_facts(item.data).fact_map() for item in first)
    assert len(index.witnesses) == 7
    assert len(index.declarations) == 464
    assert Counter(item.standard_version for item in index.declarations) == {
        "1.0": 46,
        "1.1": 46,
        "2.0": 65,
        "3.0": 72,
        "3.1": 77,
        "4.0": 79,
        "4.1-draft": 79,
    }


def test_every_barline_proof_detects_a_canonical_mutation() -> None:
    """TEST-MXML-LOSSLESS-037: all 464 barline links detect mutations."""

    index = build_barlines_family_evidence()
    canonical = barlines_witness_canonical_facts()
    assert all(
        mutated_fact_digest(proof, canonical[proof.witness_id]) != proof.source_fact_sha256
        for proof in index.declarations
    )


def test_generated_direction_witnesses_prove_all_family_rows() -> None:
    """TEST-MXML-LOSSLESS-038: seven witnesses prove all 1,024 direction rows."""

    first = generate_directions_witnesses()
    index = build_directions_family_evidence()
    assert first == generate_directions_witnesses()
    assert len({item.sha256 for item in first}) == 7
    assert all(read_directions_facts(item.data).fact_map() for item in first)
    assert len(index.witnesses) == 7
    assert len(index.declarations) == 1_024
    assert Counter(item.standard_version for item in index.declarations) == {
        "1.0": 22,
        "1.1": 29,
        "2.0": 52,
        "3.0": 136,
        "3.1": 196,
        "4.0": 295,
        "4.1-draft": 294,
    }


def test_every_direction_proof_detects_a_canonical_mutation() -> None:
    """TEST-MXML-LOSSLESS-039: all 1,024 direction links detect mutations."""

    index = build_directions_family_evidence()
    canonical = directions_witness_canonical_facts()
    assert all(
        mutated_fact_digest(proof, canonical[proof.witness_id]) != proof.source_fact_sha256
        for proof in index.declarations
    )


def test_generated_dynamic_witnesses_prove_all_family_rows() -> None:
    """TEST-MXML-LOSSLESS-040: seven witnesses prove all 213 dynamic rows."""

    first = generate_dynamics_witnesses()
    index = build_dynamics_family_evidence()
    assert first == generate_dynamics_witnesses()
    assert len({item.sha256 for item in first}) == 7
    assert all(read_dynamics_facts(item.data).fact_map() for item in first)
    assert len(index.witnesses) == 7
    assert len(index.declarations) == 213
    assert Counter(item.standard_version for item in index.declarations) == {
        "1.0": 28,
        "1.1": 28,
        "2.0": 29,
        "3.0": 29,
        "3.1": 33,
        "4.0": 33,
        "4.1-draft": 33,
    }


def test_every_dynamic_proof_detects_a_canonical_mutation() -> None:
    """TEST-MXML-LOSSLESS-041: all 213 dynamic links detect mutations."""

    index = build_dynamics_family_evidence()
    canonical = dynamics_witness_canonical_facts()
    assert all(
        mutated_fact_digest(proof, canonical[proof.witness_id]) != proof.source_fact_sha256
        for proof in index.declarations
    )


def test_generated_lyric_witnesses_prove_all_family_rows() -> None:
    """TEST-MXML-LOSSLESS-042: seven witnesses prove all 148 lyric rows."""

    first = generate_lyrics_witnesses()
    index = build_lyrics_family_evidence()
    assert first == generate_lyrics_witnesses()
    assert len({item.sha256 for item in first}) == 7
    assert all(read_lyrics_facts(item.data).fact_map() for item in first)
    assert len(index.witnesses) == 7
    assert len(index.declarations) == 148
    assert Counter(item.standard_version for item in index.declarations) == {
        "1.0": 11,
        "1.1": 11,
        "2.0": 22,
        "3.0": 23,
        "3.1": 27,
        "4.0": 27,
        "4.1-draft": 27,
    }


def test_every_lyric_proof_detects_a_canonical_mutation() -> None:
    """TEST-MXML-LOSSLESS-043: all 148 lyric links detect mutations."""

    index = build_lyrics_family_evidence()
    canonical = lyrics_witness_canonical_facts()
    assert all(
        mutated_fact_digest(proof, canonical[proof.witness_id]) != proof.source_fact_sha256
        for proof in index.declarations
    )


def test_generated_harmony_witnesses_prove_all_family_rows() -> None:
    """TEST-MXML-LOSSLESS-044: seven witnesses prove all 649 harmony rows."""

    first = generate_harmony_witnesses()
    index = build_harmony_family_evidence()
    assert first == generate_harmony_witnesses()
    assert len({item.sha256 for item in first}) == 7
    assert all(read_harmony_facts(item.data).fact_map() for item in first)
    assert len(index.witnesses) == 7
    assert len(index.declarations) == 649
    assert Counter(item.standard_version for item in index.declarations) == {
        "1.0": 31,
        "1.1": 51,
        "2.0": 97,
        "3.0": 105,
        "3.1": 107,
        "4.0": 129,
        "4.1-draft": 129,
    }


def test_every_harmony_proof_detects_a_canonical_mutation() -> None:
    """TEST-MXML-LOSSLESS-045: all 649 harmony links detect mutations."""

    index = build_harmony_family_evidence()
    canonical = harmony_witness_canonical_facts()
    assert all(
        mutated_fact_digest(proof, canonical[proof.witness_id]) != proof.source_fact_sha256
        for proof in index.declarations
    )


def test_generated_link_witnesses_prove_all_family_rows() -> None:
    """TEST-MXML-LOSSLESS-046: seven witnesses prove all 235 link rows."""

    first = generate_links_witnesses()
    index = build_links_family_evidence()
    assert first == generate_links_witnesses()
    assert len({item.sha256 for item in first}) == 7
    assert all(read_links_facts(item.data).fact_map() for item in first)
    assert len(index.witnesses) == 7
    assert len(index.declarations) == 235
    assert Counter(item.standard_version for item in index.declarations) == {
        "1.0": 26,
        "1.1": 26,
        "2.0": 36,
        "3.0": 36,
        "3.1": 37,
        "4.0": 37,
        "4.1-draft": 37,
    }


def test_every_link_proof_detects_a_canonical_mutation() -> None:
    """TEST-MXML-LOSSLESS-047: all 235 link/grouping links detect mutations."""

    index = build_links_family_evidence()
    canonical = links_witness_canonical_facts()
    assert all(
        mutated_fact_digest(proof, canonical[proof.witness_id]) != proof.source_fact_sha256
        for proof in index.declarations
    )


def test_generated_auxiliary_witnesses_prove_all_family_rows() -> None:
    """TEST-MXML-LOSSLESS-048: 18 witnesses prove all 348 auxiliary rows."""

    first = generate_auxiliary_witnesses()
    index = build_auxiliary_family_evidence()
    assert first == generate_auxiliary_witnesses()
    assert len({item.sha256 for item in first}) == 18
    assert all(read_auxiliary_facts(item.data).fact_map() for item in first)
    assert len(index.witnesses) == 18
    assert len(index.declarations) == 348
    assert Counter(item.standard_version for item in index.declarations) == {
        "1.0": 63,
        "1.1": 63,
        "2.0": 28,
        "3.0": 47,
        "3.1": 47,
        "4.0": 50,
        "4.1-draft": 50,
    }


def test_every_auxiliary_proof_detects_a_canonical_mutation() -> None:
    """TEST-MXML-LOSSLESS-049: all 348 opus/sounds links detect mutations."""

    index = build_auxiliary_family_evidence()
    canonical = auxiliary_witness_canonical_facts()
    assert all(
        mutated_fact_digest(proof, canonical[proof.witness_id]) != proof.source_fact_sha256
        for proof in index.declarations
    )


def test_generated_playback_witnesses_prove_all_family_rows() -> None:
    """TEST-MXML-LOSSLESS-050: seven witnesses prove all 540 playback rows."""

    first = generate_playback_witnesses()
    index = build_playback_family_evidence()
    assert first == generate_playback_witnesses()
    assert len({item.sha256 for item in first}) == 7
    assert all(read_playback_facts(item.data).fact_map() for item in first)
    assert len(index.witnesses) == 7
    assert len(index.declarations) == 540
    assert Counter(item.standard_version for item in index.declarations) == {
        "1.0": 34,
        "1.1": 34,
        "2.0": 54,
        "3.0": 73,
        "3.1": 75,
        "4.0": 135,
        "4.1-draft": 135,
    }


def test_every_playback_proof_detects_a_canonical_mutation() -> None:
    """TEST-MXML-LOSSLESS-051: all 540 playback/MIDI links detect mutations."""

    index = build_playback_family_evidence()
    canonical = playback_witness_canonical_facts()
    assert all(
        mutated_fact_digest(proof, canonical[proof.witness_id]) != proof.source_fact_sha256
        for proof in index.declarations
    )


def test_generated_layout_witnesses_prove_all_family_rows() -> None:
    """TEST-MXML-LOSSLESS-052: seven witnesses prove all 1,388 layout rows."""

    first = generate_layout_witnesses()
    index = build_layout_family_evidence()
    assert first == generate_layout_witnesses()
    assert len({item.sha256 for item in first}) == 7
    assert all(read_layout_facts(item.data).fact_map() for item in first)
    assert len(index.witnesses) == 7
    assert len(index.declarations) == 1_388
    assert Counter(item.standard_version for item in index.declarations) == {
        "1.0": 24,
        "1.1": 122,
        "2.0": 205,
        "3.0": 226,
        "3.1": 263,
        "4.0": 274,
        "4.1-draft": 274,
    }


def test_every_layout_proof_detects_a_canonical_mutation() -> None:
    """TEST-MXML-LOSSLESS-053: all 1,388 layout links detect mutations."""

    index = build_layout_family_evidence()
    canonical = layout_witness_canonical_facts()
    assert all(
        mutated_fact_digest(proof, canonical[proof.witness_id]) != proof.source_fact_sha256
        for proof in index.declarations
    )


def test_generated_presentation_witnesses_prove_all_family_rows() -> None:
    """TEST-MXML-LOSSLESS-054: seven witnesses prove all 2,771 style rows."""

    first = generate_presentation_witnesses()
    index = build_presentation_family_evidence()
    assert first == generate_presentation_witnesses()
    assert len({item.sha256 for item in first}) == 7
    assert all(read_presentation_facts(item.data).fact_map() for item in first)
    assert len(index.witnesses) == 7
    assert len(index.declarations) == 2_771
    assert Counter(item.standard_version for item in index.declarations) == {
        "1.0": 563,
        "1.1": 1_101,
        "2.0": 197,
        "3.0": 214,
        "3.1": 231,
        "4.0": 232,
        "4.1-draft": 233,
    }


def test_every_presentation_proof_detects_a_canonical_mutation() -> None:
    """TEST-MXML-LOSSLESS-055: all 2,771 presentation links detect mutations."""

    index = build_presentation_family_evidence()
    canonical = presentation_witness_canonical_facts()
    assert all(
        mutated_fact_digest(proof, canonical[proof.witness_id]) != proof.source_fact_sha256
        for proof in index.declarations
    )


def test_losslessness_contract_rejects_stale_or_incomplete_evidence(tmp_path: Path) -> None:
    """TEST-MXML-LOSSLESS-003: stale hashes and missing test links fail closed."""

    root = _root()
    inventory_path = root / "src/teachmemusic/score/musicxml/resources/inventory.json"
    registry_path = root / "src/teachmemusic/score/musicxml/resources/mapping-registry.json"
    payload = json.loads(render_index(build_mxl_packaging_pilot()))
    payload["inventory_sha256"] = "0" * 64
    evidence_path = tmp_path / "stale.json"
    evidence_path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(LosslessnessEvidenceError, match="inventory_sha256"):
        load_losslessness_links(
            evidence_path,
            inventory_path,
            registry_path,
            known_test_ids=frozenset({"TEST-MXML-LOSSLESS-001", "TEST-MXML-LOSSLESS-002"}),
        )

    payload = json.loads(render_index(build_mxl_packaging_pilot()))
    payload["declarations"][0]["mutation_test_ids"] = []
    evidence_path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(LosslessnessEvidenceError, match="mutation_test_ids"):
        load_losslessness_links(
            evidence_path,
            inventory_path,
            registry_path,
            known_test_ids=frozenset({"TEST-MXML-LOSSLESS-001", "TEST-MXML-LOSSLESS-002"}),
        )

    payload = json.loads(render_index(build_mxl_packaging_pilot()))
    payload["witnesses"][0]["oracle_facts"][0][1] = False
    evidence_path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(LosslessnessEvidenceError, match="digest is not reproducible"):
        load_losslessness_links(
            evidence_path,
            inventory_path,
            registry_path,
            known_test_ids=frozenset({"TEST-MXML-LOSSLESS-001", "TEST-MXML-LOSSLESS-002"}),
        )


def test_generated_losslessness_artifact_is_current_and_deterministic() -> None:
    """TEST-MXML-LOSSLESS-004: checked-in pilot evidence matches its generator."""

    root = _root()
    evidence_path = root / "docs/generated/musicxml-losslessness-evidence.json"
    inventory_path = root / "src/teachmemusic/score/musicxml/resources/inventory.json"
    registry_path = root / "src/teachmemusic/score/musicxml/resources/mapping-registry.json"
    rendered = render_index(build_losslessness_evidence())
    links = load_losslessness_links(
        evidence_path,
        inventory_path,
        registry_path,
        known_test_ids=frozenset(
            {
                "TEST-MXML-LOSSLESS-001",
                "TEST-MXML-LOSSLESS-002",
                "TEST-MXML-LOSSLESS-006",
                "TEST-MXML-LOSSLESS-007",
                "TEST-MXML-LOSSLESS-008",
                "TEST-MXML-LOSSLESS-009",
                "TEST-MXML-LOSSLESS-010",
                "TEST-MXML-LOSSLESS-011",
                "TEST-MXML-LOSSLESS-012",
                "TEST-MXML-LOSSLESS-013",
                "TEST-MXML-LOSSLESS-014",
                "TEST-MXML-LOSSLESS-015",
                "TEST-MXML-LOSSLESS-016",
                "TEST-MXML-LOSSLESS-017",
                "TEST-MXML-LOSSLESS-018",
                "TEST-MXML-LOSSLESS-019",
                "TEST-MXML-LOSSLESS-020",
                "TEST-MXML-LOSSLESS-021",
                "TEST-MXML-LOSSLESS-022",
                "TEST-MXML-LOSSLESS-023",
                "TEST-MXML-LOSSLESS-024",
                "TEST-MXML-LOSSLESS-025",
                "TEST-MXML-LOSSLESS-026",
                "TEST-MXML-LOSSLESS-027",
                "TEST-MXML-LOSSLESS-028",
                "TEST-MXML-LOSSLESS-029",
                "TEST-MXML-LOSSLESS-030",
                "TEST-MXML-LOSSLESS-031",
                "TEST-MXML-LOSSLESS-032",
                "TEST-MXML-LOSSLESS-033",
                "TEST-MXML-LOSSLESS-034",
                "TEST-MXML-LOSSLESS-035",
                "TEST-MXML-LOSSLESS-036",
                "TEST-MXML-LOSSLESS-037",
                "TEST-MXML-LOSSLESS-038",
                "TEST-MXML-LOSSLESS-039",
                "TEST-MXML-LOSSLESS-040",
                "TEST-MXML-LOSSLESS-041",
                "TEST-MXML-LOSSLESS-042",
                "TEST-MXML-LOSSLESS-043",
                "TEST-MXML-LOSSLESS-044",
                "TEST-MXML-LOSSLESS-045",
                "TEST-MXML-LOSSLESS-046",
                "TEST-MXML-LOSSLESS-047",
                "TEST-MXML-LOSSLESS-048",
                "TEST-MXML-LOSSLESS-049",
                "TEST-MXML-LOSSLESS-050",
                "TEST-MXML-LOSSLESS-051",
                "TEST-MXML-LOSSLESS-052",
                "TEST-MXML-LOSSLESS-053",
                "TEST-MXML-LOSSLESS-054",
                "TEST-MXML-LOSSLESS-055",
            }
        ),
    )

    assert evidence_path.read_text(encoding="utf-8") == rendered
    assert len(links) == 15_303
    assert set().union(*links.values()) == {
        "TEST-MXML-LOSSLESS-001",
        "TEST-MXML-LOSSLESS-002",
        "TEST-MXML-LOSSLESS-006",
        "TEST-MXML-LOSSLESS-007",
        "TEST-MXML-LOSSLESS-008",
        "TEST-MXML-LOSSLESS-009",
        "TEST-MXML-LOSSLESS-010",
        "TEST-MXML-LOSSLESS-011",
        "TEST-MXML-LOSSLESS-012",
        "TEST-MXML-LOSSLESS-013",
        "TEST-MXML-LOSSLESS-014",
        "TEST-MXML-LOSSLESS-015",
        "TEST-MXML-LOSSLESS-016",
        "TEST-MXML-LOSSLESS-017",
        "TEST-MXML-LOSSLESS-018",
        "TEST-MXML-LOSSLESS-019",
        "TEST-MXML-LOSSLESS-020",
        "TEST-MXML-LOSSLESS-021",
        "TEST-MXML-LOSSLESS-022",
        "TEST-MXML-LOSSLESS-023",
        "TEST-MXML-LOSSLESS-024",
        "TEST-MXML-LOSSLESS-025",
        "TEST-MXML-LOSSLESS-026",
        "TEST-MXML-LOSSLESS-027",
        "TEST-MXML-LOSSLESS-028",
        "TEST-MXML-LOSSLESS-029",
        "TEST-MXML-LOSSLESS-030",
        "TEST-MXML-LOSSLESS-031",
        "TEST-MXML-LOSSLESS-032",
        "TEST-MXML-LOSSLESS-033",
        "TEST-MXML-LOSSLESS-034",
        "TEST-MXML-LOSSLESS-035",
        "TEST-MXML-LOSSLESS-036",
        "TEST-MXML-LOSSLESS-037",
        "TEST-MXML-LOSSLESS-038",
        "TEST-MXML-LOSSLESS-039",
        "TEST-MXML-LOSSLESS-040",
        "TEST-MXML-LOSSLESS-041",
        "TEST-MXML-LOSSLESS-042",
        "TEST-MXML-LOSSLESS-043",
        "TEST-MXML-LOSSLESS-044",
        "TEST-MXML-LOSSLESS-045",
        "TEST-MXML-LOSSLESS-046",
        "TEST-MXML-LOSSLESS-047",
        "TEST-MXML-LOSSLESS-048",
        "TEST-MXML-LOSSLESS-049",
        "TEST-MXML-LOSSLESS-050",
        "TEST-MXML-LOSSLESS-051",
        "TEST-MXML-LOSSLESS-052",
        "TEST-MXML-LOSSLESS-053",
        "TEST-MXML-LOSSLESS-054",
        "TEST-MXML-LOSSLESS-055",
    }


def test_independent_oracle_has_no_production_parser_dependency() -> None:
    """TEST-MXML-LOSSLESS-005: the source oracle cannot reuse production mapping."""

    root = _root()
    path = root / "src/teachmemusic/score/musicxml/losslessness_oracle.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    imported = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    }
    imported.update(
        node.module or "" for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)
    )

    assert not any(
        name.startswith("lxml")
        or name.endswith("boundary")
        or name.endswith("temporal")
        or name.endswith("canonical_package")
        for name in imported
    )
