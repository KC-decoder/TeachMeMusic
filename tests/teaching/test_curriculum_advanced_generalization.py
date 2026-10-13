"""DEV-009 Task 9M advanced-score generalization evidence."""

from __future__ import annotations

import ast
import hashlib
import re
from importlib import import_module
from pathlib import Path

import pytest

from teachmemusic.score import (
    CanonicalMusicPackage,
    CanonicalScoreContent,
    ScoreDocument,
    parse_musicxml_package,
)
from teachmemusic.teaching import (
    ArtifactResolution,
    RequirementDerivationError,
    SyntheticLearnerProfileKind,
    build_curriculum_verification_report,
    curriculum_route_structural_dict,
    default_synthetic_learner_profiles,
)

_FIXTURES = Path(__file__).parents[1] / "fixtures" / "scores"
_CLAIR = _FIXTURES / "TMM-REF-CANDIDATE-003-Clair-de-Lune" / "clair-de-lune-debussy.mxl"
_DEUX = _FIXTURES / "TMM-REF-CANDIDATE-005-Deux-Arabesques" / "debussy-deux-arabesques.mxl"
_MOONLIGHT = (
    _FIXTURES
    / "TMM-REF-CANDIDATE-004-Moonlight-Sonata"
    / "beethoven-piano-sonata-no-14-moonlight.mxl"
)
_CLEMENTI = (
    _FIXTURES
    / "TMM-GENERALIZATION-001-Clementi-Sonatina"
    / "MuzioClementi_SonatinaOpus36No1_Part1.xml"
)
_GENERATOR_MODULES = (
    "teachmemusic.teaching.requirements",
    "teachmemusic.teaching.branches",
    "teachmemusic.teaching.acquisition",
    "teachmemusic.teaching.curriculum_verification",
)
_FORBIDDEN_SOURCE_FRAGMENTS = (
    "hot cross buns",
    "happy birthday",
    "moonlight sonata",
    "clair de lune",
    "deux arabesques",
    "clementi",
    "tmm-ref-candidate",
    "tmm-generalization",
    "tests/fixtures",
    ".musicxml",
    ".mxl",
)
_FORBIDDEN_ATTRIBUTES = {
    "fixture_path",
    "logical_name",
    "movement_title",
    "source_path",
    "title",
    "work_title",
}


def _load(path: Path, *, logical_name: str | None = None) -> CanonicalMusicPackage:
    return parse_musicxml_package(path.read_bytes(), logical_name=logical_name or path.name)


def _first_part_id(package: CanonicalMusicPackage) -> str:
    document = next(
        item
        for item in package.documents
        if isinstance(item, ScoreDocument) and isinstance(item.content, CanonicalScoreContent)
    )
    assert isinstance(document.content, CanonicalScoreContent)
    return document.content.score.parts[0].id


def _ready_profile():
    return next(
        item
        for item in default_synthetic_learner_profiles()
        if item.kind is SyntheticLearnerProfileKind.RHYTHM_READY
    )


@pytest.fixture(scope="module")
def clair_package() -> CanonicalMusicPackage:
    return _load(_CLAIR)


@pytest.fixture(scope="module")
def deux_package() -> CanonicalMusicPackage:
    return _load(_DEUX)


@pytest.fixture(scope="module")
def clementi_package() -> CanonicalMusicPackage:
    return _load(_CLEMENTI)


@pytest.fixture(scope="module")
def moonlight_package() -> CanonicalMusicPackage:
    return _load(_MOONLIGHT)


def test_clair_de_lune_bounded_route_uses_the_general_pipeline(
    clair_package: CanonicalMusicPackage,
) -> None:
    """TEST-CURR-GENERALIZATION-001: Clair measure 2 resolves generically."""

    report = build_curriculum_verification_report(
        clair_package,
        _ready_profile(),
        start_measure_ordinal=2,
        end_measure_ordinal=2,
    )
    structure = curriculum_route_structural_dict(report)

    assert report.semantic_fingerprint == (
        "50a610846e4aa67d6e8654e10124ec7fe3a5ae780031ec6c2924d7fa400b479d"
    )
    assert structure["resolution"] == "resolved"
    assert structure["measure_count"] == 1
    assert structure["layer_count"] == 2
    assert structure["scope_shapes"] == [
        ["upper-layer", "resolved", 8, 4, 0, 1],
        ["lower-layer", "resolved", 4, 8, 0, 1],
        ["combined", "resolved", 12, 0, 2, 2],
    ]
    assert structure["stage_kinds"] == [
        "component-acquisition",
        "component-acquisition",
        "self-paced-coordination",
        "pulse-integration",
        "phrase-controlled-tempo",
        "learned-to-date",
        "tempo-development",
    ]


def test_deux_arabesques_bounded_route_uses_the_general_pipeline(
    deux_package: CanonicalMusicPackage,
) -> None:
    """TEST-CURR-GENERALIZATION-002: an eight-measure passage resolves."""

    report = build_curriculum_verification_report(
        deux_package,
        _ready_profile(),
        start_measure_ordinal=5,
        end_measure_ordinal=12,
    )
    structure = curriculum_route_structural_dict(report)

    assert report.semantic_fingerprint == (
        "756fa2b5092b4ce344dd208d8c37f5927afbcb15bb2574648c0d23c5c3b95285"
    )
    assert structure["resolution"] == "resolved"
    assert structure["measure_count"] == 8
    assert structure["layer_count"] == 2
    assert structure["scope_shapes"] == [
        ["upper-layer", "resolved", 55, 68, 0, 1],
        ["lower-layer", "resolved", 68, 55, 0, 1],
        ["combined", "resolved", 123, 0, 2, 2],
    ]


def test_unseen_clementi_fixture_is_pinned_and_generates_a_bounded_route(
    clementi_package: CanonicalMusicPackage,
) -> None:
    """TEST-CURR-GENERALIZATION-003: a provenance-pinned unseen score resolves."""

    assert hashlib.sha256(_CLEMENTI.read_bytes()).hexdigest() == (
        "fb2b3feff9e6e26357a30de4a507651023e77c5cc545f5e22effba51b06d56c0"
    )
    report = build_curriculum_verification_report(
        clementi_package,
        _ready_profile(),
        start_measure_ordinal=1,
        end_measure_ordinal=4,
        part_ids=(_first_part_id(clementi_package),),
    )
    structure = curriculum_route_structural_dict(report)

    assert report.semantic_fingerprint == (
        "40dfdcb75cb38931e9668cbc16aec2a8e1c1a65aaf802999e7e8829b7d44b236"
    )
    assert structure["resolution"] == "resolved"
    assert structure["measure_count"] == 4
    assert structure["scope_shapes"] == [["single-layer", "resolved", 24, 0, 0, 1]]
    assert "TMM-VERIFY-PART-SELECTION" in {item.code for item in report.limitations}


def test_moonlight_candidate_is_frozen_without_claiming_hand_review(
    moonlight_package: CanonicalMusicPackage,
) -> None:
    """TEST-CURR-GENERALIZATION-006: freeze the bounded review candidate."""

    report = build_curriculum_verification_report(
        moonlight_package,
        _ready_profile(),
        start_measure_ordinal=1,
        end_measure_ordinal=4,
    )
    structure = curriculum_route_structural_dict(report)

    assert report.semantic_fingerprint == (
        "81c0126b76da6899e37e9888b6dba33b2f1598bc5c24e281e7b43f763a383c02"
    )
    assert structure["resolution"] == "resolved"
    assert structure["measure_count"] == 4
    assert structure["scope_shapes"] == [
        ["upper-layer", "resolved", 48, 12, 0, 1],
        ["lower-layer", "resolved", 12, 48, 0, 1],
        ["combined", "resolved", 60, 0, 2, 2],
    ]
    assert "TMM-VERIFY-EXECUTION-ASSIGNMENT-UNREVIEWED" in {
        item.code for item in report.limitations
    }


def test_complete_generation_path_is_title_upload_and_fixture_blind(
    clementi_package: CanonicalMusicPackage,
) -> None:
    """TEST-CURR-GENERALIZATION-004: metadata cannot select a 9M route."""

    failures: list[str] = []
    for module_name in _GENERATOR_MODULES:
        module = import_module(module_name)
        source = Path(module.__file__).read_text(encoding="utf-8")
        tree = ast.parse(source)
        lowered = source.lower()
        for fragment in _FORBIDDEN_SOURCE_FRAGMENTS:
            if fragment in lowered:
                failures.append(f"{module_name}: forbidden source fragment {fragment!r}")
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute) and node.attr in _FORBIDDEN_ATTRIBUTES:
                failures.append(f"{module_name}:{node.lineno}: reads {node.attr!r}")
    assert failures == []

    changed_source, replacements = re.subn(
        rb"(<work-title(?:\s[^>]*)?>).*?(</work-title>)",
        rb"\1Anonymous Unseen Study\2",
        _CLEMENTI.read_bytes(),
        flags=re.DOTALL,
    )
    assert replacements == 1
    renamed = parse_musicxml_package(changed_source, logical_name="anonymous-upload.xml")
    original_report = build_curriculum_verification_report(
        clementi_package,
        _ready_profile(),
        start_measure_ordinal=1,
        end_measure_ordinal=4,
        part_ids=(_first_part_id(clementi_package),),
    )
    renamed_report = build_curriculum_verification_report(
        renamed,
        _ready_profile(),
        start_measure_ordinal=1,
        end_measure_ordinal=4,
        part_ids=(_first_part_id(renamed),),
    )
    assert curriculum_route_structural_dict(original_report) == curriculum_route_structural_dict(
        renamed_report
    )


def test_unsupported_advanced_interpretations_remain_explicit(
    clair_package: CanonicalMusicPackage,
    deux_package: CanonicalMusicPackage,
    clementi_package: CanonicalMusicPackage,
) -> None:
    """TEST-CURR-GENERALIZATION-005: ambiguity is review, never guessed pedagogy."""

    cases = (
        (clair_package, 2, 4, 3),
        (deux_package, 1, 4, 5),
    )
    for package, start, end, layer_count in cases:
        report = build_curriculum_verification_report(
            package,
            _ready_profile(),
            start_measure_ordinal=start,
            end_measure_ordinal=end,
        )
        assert report.structural_signature.resolution is ArtifactResolution.REVIEW_REQUIRED
        assert report.structural_signature.layer_count == layer_count
        assert report.structural_signature.stage_kinds == ()
        assert report.structural_signature.diagnostic_codes == ("TMM-HAND-INTERPRETATION-REQUIRED",)
        assert "TMM-VERIFY-UNRESOLVED-PEDAGOGY" in {item.code for item in report.limitations}

    with pytest.raises(
        RequirementDerivationError,
        match="TMM-SCOPE-FOREIGN-REFERENCE: 9B.1 requires exactly one selected part",
    ):
        build_curriculum_verification_report(clementi_package, _ready_profile())
