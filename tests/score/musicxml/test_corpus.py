"""Tests for the fail-closed Task 7I corpus evidence runner."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

import teachmemusic.score.musicxml.corpus as corpus_module
from teachmemusic.score.musicxml.corpus import (
    CorpusAudit,
    CorpusAuditError,
    CorpusFileResult,
    CorpusResult,
    SchematronFileResult,
    _audit_file,
    _audit_schematron_file,
    audit_corpora,
    load_corpus_definitions,
    render_json,
    render_markdown,
)
from teachmemusic.score.v2.temporal_codec import TemporalCodecError
from teachmemusic.score.v2.temporal_validation import TemporalValidationIssue


def _fixture(name: str) -> Path:
    return Path(__file__).resolve().parents[2] / "fixtures" / "scores" / name


def test_governed_corpus_manifest_pins_both_sources() -> None:
    """TEST-MXML-CORPUS-001: both required corpora have immutable pins."""

    definitions = load_corpus_definitions()
    assert [(item.id, item.expected_files) for item in definitions] == [
        ("w3c-maintained-validation", 7),
        ("w3c-community-feature-suite", 183),
    ]
    assert [item.run_id for item in definitions] == [
        "CORPUS-MXML-001",
        "CORPUS-MXML-002",
    ]
    assert all(len(item.revision) == 40 for item in definitions)


def test_missing_corpus_checkout_fails_closed(tmp_path: Path) -> None:
    """TEST-MXML-CORPUS-002: unavailable evidence cannot become a pass."""

    with pytest.raises(CorpusAuditError, match="assertions.json"):
        audit_corpora(tmp_path / "missing-w3c", tmp_path / "missing-community")


def test_audit_file_distinguishes_lossless_and_deferred_mapping() -> None:
    """TEST-MXML-CORPUS-003: mapper success does not imply losslessness."""

    result = _audit_file(
        _fixture(
            "TMM-REF-CANDIDATE-001-Hot-Cross-Buns/musicxml-17-hot-cross-buns-final-shelbygtdrew.mxl"
        ),
        "pass",
    )
    assert result.actual_validation == "pass"
    assert result.mapping in {"mapped-zero-deferred", "mapped-with-deferred"}
    assert result.validation_matches


def test_audit_file_records_expected_validation_failure(tmp_path: Path) -> None:
    """TEST-MXML-CORPUS-004: expected invalid input is evidence, not an error."""

    invalid = tmp_path / "invalid.musicxml"
    invalid.write_bytes(b"<score-partwise version='4.0'/>")
    result = _audit_file(invalid, "fail")
    assert result.validation_matches
    assert result.mapping == "not-applicable"
    assert result.diagnostic == "MXML_XSD_INVALID"


def test_audit_file_rejects_invalid_canonical_mapping(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """TEST-MXML-CORPUS-017: object construction alone is not a mapping pass."""

    monkeypatch.setattr(
        corpus_module,
        "validate_temporal_score",
        lambda _score: (TemporalValidationIssue("TEST_INVALID", "score", "test issue"),),
    )
    result = _audit_file(
        _fixture(
            "TMM-REF-CANDIDATE-001-Hot-Cross-Buns/musicxml-17-hot-cross-buns-final-shelbygtdrew.mxl"
        ),
        "pass",
    )
    assert result.mapping == "failed"
    assert result.diagnostic == "TEST_INVALID: score"


def test_audit_file_requires_exact_canonical_round_trip(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """TEST-MXML-CORPUS-018: mapped corpus evidence includes strict JSON survival."""

    def reject_encoding(_score: object) -> dict[str, object]:
        raise TemporalCodecError("synthetic codec failure")

    monkeypatch.setattr(corpus_module, "temporal_to_dict", reject_encoding)
    result = _audit_file(
        _fixture(
            "TMM-REF-CANDIDATE-001-Hot-Cross-Buns/musicxml-17-hot-cross-buns-final-shelbygtdrew.mxl"
        ),
        "pass",
    )
    assert result.mapping == "failed"
    assert result.diagnostic == "TemporalCodecError: synthetic codec failure"


def test_upstream_xpath3_schematron_distinguishes_valid_and_invalid() -> None:
    """TEST-MXML-CORPUS-019: pinned XPath 3 rules produce declared outcomes."""

    checkout = Path("/private/tmp/teachmemusic-task7i-musicxml")
    if not checkout.is_dir():
        pytest.skip("exact pinned maintained-corpus checkout is not available")
    tests = checkout / "tests"
    stylesheet = tests / "validations" / "beams-ties.xsl"
    valid = _audit_schematron_file(tests / "files" / "beams-ties.musicxml", stylesheet, "pass")
    invalid = _audit_schematron_file(
        tests / "files" / "beams-ties.invalid.musicxml", stylesheet, "fail"
    )
    assert valid.validation_matches
    assert invalid.validation_matches
    assert invalid.diagnostic == "1 failed assertion(s)"


def test_pinned_corpora_record_independent_exporter_evidence() -> None:
    """TEST-MXML-EXPORTER-001: MuseScore and Sibelius/Dolet inputs map."""

    maintained = Path("/private/tmp/teachmemusic-task7i-musicxml")
    community = Path("/private/tmp/teachmemusic-task7i-suite")
    if not maintained.is_dir() or not community.is_dir():
        pytest.skip("exact pinned corpus checkouts are not available")

    musescore = _audit_file(maintained / "tests/files/accidentals.musicxml", "pass")
    sibelius = _audit_file(community / "xmlFiles/99a-Sibelius5-IgnoreBeaming.musicxml", "pass")

    assert musescore.mapping == "mapped-zero-deferred"
    assert musescore.software == ("MuseScore 4.5.2",)
    assert sibelius.mapping == "mapped-zero-deferred"
    assert sibelius.software == ("Sibelius 5.1", "Dolet 3.4 for Sibelius")


def test_corpus_report_is_deterministic_and_does_not_overclaim() -> None:
    """TEST-MXML-CORPUS-005: reports retain gaps and exclude checkout paths."""

    corpus = CorpusResult(
        id="example",
        run_id="CORPUS-MXML-TEST",
        repository="https://example.invalid/corpus.git",
        revision="a" * 40,
        files=(
            CorpusFileResult("valid.musicxml", "pass", "pass", "mapped-with-deferred", 2),
            CorpusFileResult(
                "invalid.musicxml",
                "fail",
                "fail",
                "not-applicable",
                diagnostic="MXML_XSD_INVALID",
            ),
        ),
        schematron=(SchematronFileResult("valid.musicxml", "example.sch", "pass", "pass"),),
    )
    audit = CorpusAudit((corpus,))
    assert audit.validation_complete
    assert not audit.mapping_complete
    assert not audit.corpus_mapping_complete
    first_json = render_json(audit)
    assert first_json == render_json(audit)
    assert json.loads(first_json)["corpus_mapping_complete"] is False
    markdown = render_markdown(audit)
    assert "**Corpus audit readiness:** INCOMPLETE" in markdown
    assert "**Bounded corpus mapping gate:** INCOMPLETE" in markdown
    assert "mapped-with-deferred" in markdown
    assert "/private/" not in markdown
