"""DEV-009 Task 9L non-human curriculum verification."""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest

from teachmemusic.score import CanonicalMusicPackage
from teachmemusic.teaching import (
    CurriculumActionEligibility,
    CurriculumVerificationError,
    SyntheticLearnerProfile,
    SyntheticLearnerProfileKind,
    VerificationAuthority,
    build_curriculum_verification_report,
    curriculum_route_structural_dict,
    default_synthetic_learner_profiles,
    require_valid_curriculum_verification_report,
    require_valid_synthetic_learner_profile,
    validate_curriculum_action_selection,
)
from teachmemusic.teaching.curriculum_fingerprint import derived_id, semantic_fingerprint
from tests.teaching.test_curriculum_trajectory import _happy_birthday_transition

_GOLDEN = Path(__file__).parents[1] / "fixtures" / "teaching" / "dev-009-golden-trajectories.json"


def _profiles() -> dict[SyntheticLearnerProfileKind, SyntheticLearnerProfile]:
    return {item.kind: item for item in default_synthetic_learner_profiles()}


def _profile_at_percentage(percentage: int) -> SyntheticLearnerProfile:
    original = _profiles()[SyntheticLearnerProfileKind.REDUCED_TEMPO]
    provisional = replace(
        original,
        id="synthetic-learner-profile:pending",
        semantic_fingerprint="",
        controlled_percentage=percentage,
        supported_ceiling_percentage=percentage,
    )
    return replace(
        provisional,
        id=derived_id("synthetic-learner-profile", provisional),
        semantic_fingerprint=semantic_fingerprint(provisional),
    )


def test_reviewed_golden_trajectories_match_exact_structural_oracles(
    hot_cross_buns_package: CanonicalMusicPackage,
    happy_birthday_package: CanonicalMusicPackage,
) -> None:
    """TEST-CURR-GOLDEN-001: reviewed title-free routes remain exact."""

    expected = json.loads(_GOLDEN.read_text(encoding="utf-8"))
    assert expected["_meta"] == {
        "authority": "golden-oracle",
        "human_evidence_eligible": False,
        "purpose": "Reviewed structural expectations for deterministic software verification only.",
        "schema_version": "0.1.0",
    }
    profiles = _profiles()
    cases = {
        "hot-cross-buns-reduced": (
            hot_cross_buns_package,
            profiles[SyntheticLearnerProfileKind.REDUCED_TEMPO],
        ),
        "happy-birthday-rhythm-ready": (
            happy_birthday_package,
            profiles[SyntheticLearnerProfileKind.RHYTHM_READY],
        ),
    }

    for name, (package, profile) in cases.items():
        report = build_curriculum_verification_report(package, profile)
        assert report.semantic_fingerprint == expected[name]["report_fingerprint"]
        assert profile.kind.value == expected[name]["profile_kind"]
        assert curriculum_route_structural_dict(report) == expected[name]["structure"]


def test_synthetic_profiles_are_finite_deterministic_and_cover_both_tempo_entries(
    hot_cross_buns_package: CanonicalMusicPackage,
) -> None:
    """TEST-CURR-SYNTHETIC-001: three bounded profiles cover ADR-0012."""

    first = default_synthetic_learner_profiles()
    second = default_synthetic_learner_profiles()
    assert first == second
    assert tuple(item.kind for item in first) == (
        SyntheticLearnerProfileKind.DIAGNOSTIC_REQUIRED,
        SyntheticLearnerProfileKind.REDUCED_TEMPO,
        SyntheticLearnerProfileKind.RHYTHM_READY,
    )
    assert all(item.decision_budget <= 64 for item in first)
    assert all(item.human_evidence_eligible is False for item in first)

    reports = {
        item.kind: build_curriculum_verification_report(hot_cross_buns_package, item)
        for item in first
    }
    diagnostic = reports[SyntheticLearnerProfileKind.DIAGNOSTIC_REQUIRED].structural_signature
    assert diagnostic.resolution.value == "resolved"
    assert diagnostic.stage_kinds == ("tempo-diagnostic",)
    assert diagnostic.controlled_percentages == (None,)
    assert reports[
        SyntheticLearnerProfileKind.REDUCED_TEMPO
    ].structural_signature.controlled_percentages == (55,)
    assert reports[
        SyntheticLearnerProfileKind.RHYTHM_READY
    ].structural_signature.controlled_percentages == (100,)


def test_action_masks_and_deterministic_selection_fail_closed_on_mutation(
    happy_birthday_package: CanonicalMusicPackage,
) -> None:
    """TEST-CURR-POLICY-012: excluded actions cannot become selections."""

    inventory, selection, snapshot, *_ = _happy_birthday_transition(happy_birthday_package)
    allowed = tuple(
        item
        for item in inventory.candidates
        if item.eligibility is CurriculumActionEligibility.ALLOWED
    )
    assert selection.selected_candidate == allowed[0]
    assert selection.behavior_probability == 1

    mutated = replace(
        selection,
        selected_candidate=replace(
            selection.selected_candidate,
            eligibility=CurriculumActionEligibility.EXCLUDED,
        ),
    )
    codes = {
        item.code for item in validate_curriculum_action_selection(mutated, inventory, snapshot)
    }
    assert "TMM-POLICY-SELECTION-MISMATCH" in codes
    assert "TMM-CONTRACT-FINGERPRINT-MISMATCH" in codes


@pytest.mark.parametrize("percentage", (1, 25, 55, 70, 85, 100))
def test_controlled_tempo_property_preserves_route_topology(
    hot_cross_buns_package: CanonicalMusicPackage,
    percentage: int,
) -> None:
    """TEST-CURR-ROBUSTNESS-050: valid tempo values change tempo, not topology."""

    profile = _profile_at_percentage(percentage)
    require_valid_synthetic_learner_profile(profile)
    report = build_curriculum_verification_report(hot_cross_buns_package, profile)

    assert report.structural_signature.resolution.value == "resolved"
    assert report.structural_signature.layer_count == 1
    assert report.structural_signature.scope_shapes == (("single-layer", "resolved", 20, 0, 0, 1),)
    assert report.structural_signature.controlled_percentages == (percentage,)


def test_profile_and_report_mutations_cannot_cross_evidence_boundary(
    hot_cross_buns_package: CanonicalMusicPackage,
) -> None:
    """TEST-CURR-VALIDATION-044: malformed simulation evidence fails closed."""

    profile = _profiles()[SyntheticLearnerProfileKind.REDUCED_TEMPO]
    with pytest.raises(CurriculumVerificationError, match="TMM-VERIFY-PROFILE-BOUNDS"):
        require_valid_synthetic_learner_profile(
            replace(profile, controlled_percentage=101, supported_ceiling_percentage=101)
        )

    report = build_curriculum_verification_report(hot_cross_buns_package, profile)
    assert report.authority is VerificationAuthority.SYNTHETIC_SIMULATION
    assert report.human_evidence_eligible is False
    assert any(item.code == "TMM-VERIFY-NON-HUMAN-EVIDENCE" for item in report.limitations)
    assert not {
        "learner_id",
        "attempt_id",
        "observation_id",
        "raw_midi",
    }.intersection(curriculum_route_structural_dict(report))

    with pytest.raises(CurriculumVerificationError, match="TMM-VERIFY-AUTHORITY"):
        require_valid_curriculum_verification_report(replace(report, human_evidence_eligible=True))
