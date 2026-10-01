"""Tests for deterministic source-linked canonical analysis."""

from dataclasses import FrozenInstanceError, replace

import pytest

from teachmemusic.analysis import (
    AnalysisDerivation,
    AnalysisError,
    AnalysisFactKind,
    AnalysisSerializationError,
    RepetitionKind,
    ScoreAnalysis,
    analyze_canonical_score,
    score_analysis_from_dict,
    score_analysis_from_json,
    score_analysis_to_dict,
    score_analysis_to_json,
    validate_score_analysis,
)
from teachmemusic.score import (
    CanonicalMusicPackage,
    CanonicalScoreContent,
    ScoreDocument,
    require_valid_package,
)
from teachmemusic.score.v2.temporal import TemporalPitch, resolve_sounding_pitches


def _fact(analysis: ScoreAnalysis, kind: AnalysisFactKind) -> str:
    return next(fact.value for fact in analysis.facts if fact.kind is kind)


def test_hot_cross_buns_analysis_is_exact_deterministic_and_strict(
    hot_cross_buns_package: CanonicalMusicPackage,
) -> None:
    """TEST-ANALYSIS-001: beginner monophonic facts and JSON are exact."""

    first = analyze_canonical_score(hot_cross_buns_package)
    second = analyze_canonical_score(hot_cross_buns_package)
    payload = score_analysis_to_json(first)

    assert first == second
    assert validate_score_analysis(first, hot_cross_buns_package) == ()
    assert _fact(first, AnalysisFactKind.MEASURE_POSITION_COUNT) == "8"
    assert _fact(first, AnalysisFactKind.PITCHED_EVENT_COUNT) == "17"
    assert _fact(first, AnalysisFactKind.REST_EVENT_COUNT) == "3"
    assert _fact(first, AnalysisFactKind.PITCH_RANGE) == "67..71"
    assert first.texture.layer_count == 1
    assert first.texture.max_simultaneous_pitches == 1
    assert len(first.boundaries) == 9
    assert score_analysis_from_json(payload) == first
    assert score_analysis_from_dict(score_analysis_to_dict(first)) == first
    assert score_analysis_to_json(first) == payload


def test_happy_birthday_analysis_preserves_layers_chords_and_scoped_repetition(
    happy_birthday_package: CanonicalMusicPackage,
) -> None:
    """TEST-ANALYSIS-002: polyphonic structure remains layer scoped."""

    analysis = analyze_canonical_score(happy_birthday_package)
    exact_groups = tuple(
        group
        for group in analysis.repetitions
        if group.kind is RepetitionKind.EXACT_PITCH_AND_RHYTHM
    )

    assert validate_score_analysis(analysis, happy_birthday_package) == ()
    assert _fact(analysis, AnalysisFactKind.EVENT_COUNT) == "59"
    assert _fact(analysis, AnalysisFactKind.PITCHED_EVENT_COUNT) == "52"
    assert _fact(analysis, AnalysisFactKind.REST_EVENT_COUNT) == "7"
    assert _fact(analysis, AnalysisFactKind.CHORD_COUNT) == "9"
    assert _fact(analysis, AnalysisFactKind.PITCH_RANGE) == "47..79"
    assert analysis.texture.staff_count == 2
    assert analysis.texture.layer_count == 2
    assert analysis.texture.max_simultaneous_pitches == 4
    assert any(
        any(identifier.endswith(":m1") for identifier in group.occurrence_measure_ids)
        and any(identifier.endswith(":m3") for identifier in group.occurrence_measure_ids)
        for group in exact_groups
    )


def test_moonlight_first_movement_scope_uses_the_same_generic_analysis(
    moonlight_package: CanonicalMusicPackage,
) -> None:
    """TEST-ANALYSIS-003: Moonlight measures 1–69 use the generic boundary."""

    analysis = analyze_canonical_score(moonlight_package, end_measure_ordinal=69)

    assert validate_score_analysis(analysis, moonlight_package) == ()
    assert analysis.scope.start_measure_ordinal == 1
    assert analysis.scope.end_measure_ordinal == 69
    assert _fact(analysis, AnalysisFactKind.MEASURE_POSITION_COUNT) == "69"
    assert _fact(analysis, AnalysisFactKind.EVENT_COUNT) == "1212"
    assert analysis.texture.layer_count == 6
    assert analysis.texture.max_active_layers == 4
    assert len(analysis.boundaries) == 70
    assert all(demand.evidence_ids for demand in analysis.demands)


def test_analysis_validation_rejects_foreign_evidence_and_contract_drift(
    hot_cross_buns_package: CanonicalMusicPackage,
) -> None:
    """TEST-ANALYSIS-004: mutations cannot cross the public edge silently."""

    analysis = analyze_canonical_score(hot_cross_buns_package)
    bad_fact = replace(analysis.facts[0], evidence_ids=("event:foreign",))
    bad_analysis = replace(analysis, facts=(bad_fact, *analysis.facts[1:]))
    issues = validate_score_analysis(bad_analysis, hot_cross_buns_package)

    assert "ANALYSIS_CANONICAL_REFERENCE" in {issue.code for issue in issues}
    with pytest.raises(FrozenInstanceError):
        analysis.id = "analysis:changed"  # type: ignore[misc]
    with pytest.raises(AnalysisSerializationError, match="ANALYSIS_CONTRACT_VERSION"):
        score_analysis_to_json(replace(analysis, contract_version="unsupported"))

    data = score_analysis_to_dict(analysis)
    data["unknown"] = True
    with pytest.raises(AnalysisSerializationError, match="unexpected"):
        score_analysis_from_dict(data)
    with pytest.raises(AnalysisError, match="ANALYSIS_SCOPE"):
        analyze_canonical_score(hot_cross_buns_package, end_measure_ordinal=999)
    with pytest.raises(AnalysisError, match="ANALYSIS_PART_REFERENCE"):
        analyze_canonical_score(hot_cross_buns_package, part_ids=("part:foreign",))


def test_analysis_changes_when_canonical_music_changes(
    hot_cross_buns_package: CanonicalMusicPackage,
) -> None:
    """TEST-ANALYSIS-005: a canonical pitch mutation changes derived facts."""

    original = analyze_canonical_score(hot_cross_buns_package)
    document_index, document = next(
        (index, item)
        for index, item in enumerate(hot_cross_buns_package.documents)
        if isinstance(item, ScoreDocument)
    )
    assert isinstance(document.content, CanonicalScoreContent)
    score = document.content.score
    part = score.parts[0]
    measure = part.measures[0]
    event = next(item for item in measure.events if item.pitch is not None)
    event_index = measure.events.index(event)
    new_pitch = TemporalPitch(event.pitch.step, event.pitch.alter, event.pitch.octave + 1)
    changed_event = replace(
        event,
        pitch=new_pitch,
        sounding_pitches=resolve_sounding_pitches(new_pitch, None),
    )
    changed_measure = replace(
        measure,
        events=(
            *measure.events[:event_index],
            changed_event,
            *measure.events[event_index + 1 :],
        ),
    )
    changed_part = replace(part, measures=(changed_measure, *part.measures[1:]))
    changed_score = replace(score, parts=(changed_part, *score.parts[1:]))
    changed_document = replace(
        document,
        content=replace(document.content, score=changed_score),
    )
    changed_package = replace(
        hot_cross_buns_package,
        documents=(
            *hot_cross_buns_package.documents[:document_index],
            changed_document,
            *hot_cross_buns_package.documents[document_index + 1 :],
        ),
    )
    require_valid_package(changed_package)
    changed = analyze_canonical_score(changed_package)

    assert changed.canonical_digest_sha256 != original.canonical_digest_sha256
    assert _fact(changed, AnalysisFactKind.PITCH_RANGE) != _fact(
        original, AnalysisFactKind.PITCH_RANGE
    )
    assert changed.layers != original.layers


def test_analysis_source_contains_no_governed_piece_or_fixture_branch() -> None:
    """TEST-ANALYSIS-006: implementation has no title or fixture special case."""

    from pathlib import Path

    import teachmemusic.analysis.analyzer as analyzer_module

    source = Path(analyzer_module.__file__).read_text()
    forbidden = (
        "Hot Cross Buns",
        "Happy Birthday",
        "Moonlight Sonata",
        "TMM-REF-CANDIDATE",
        "tests/fixtures",
    )

    assert not any(value in source for value in forbidden)


def test_later_measure_scope_inherits_effective_notation_context(
    hot_cross_buns_package: CanonicalMusicPackage,
) -> None:
    """TEST-ANALYSIS-007: a later slice retains effective meter and clef facts."""

    analysis = analyze_canonical_score(
        hot_cross_buns_package,
        start_measure_ordinal=3,
        end_measure_ordinal=4,
    )
    meter = next(fact for fact in analysis.facts if fact.kind is AnalysisFactKind.METER_VOCABULARY)
    clef = next(fact for fact in analysis.facts if fact.kind is AnalysisFactKind.CLEF_VOCABULARY)
    pitch_range = next(fact for fact in analysis.facts if fact.kind is AnalysisFactKind.PITCH_RANGE)

    assert validate_score_analysis(analysis, hot_cross_buns_package) == ()
    assert meter.value == "4/4"
    assert clef.value == "G:2:0"
    assert meter.derivation is AnalysisDerivation.SOURCE_SUMMARY
    assert clef.derivation is AnalysisDerivation.SOURCE_SUMMARY
    assert pitch_range.derivation is AnalysisDerivation.DETERMINISTIC_DERIVATION
