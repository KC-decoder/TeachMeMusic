"""DEV-005 Task 5B.1 viewer-contract tests."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from teachmemusic.score import parse_musicxml_package
from teachmemusic.viewer import (
    VIEWER_CONTRACT_ID,
    VIEWER_CONTRACT_VERSION,
    ViewerBundle,
    build_notation_bundle,
    validate_viewer_bundle,
    viewer_bundle_to_json,
)

_FIXTURE = (
    Path(__file__).parents[1]
    / "fixtures"
    / "scores"
    / "TMM-REF-CANDIDATE-001-Hot-Cross-Buns"
    / "musicxml-17-hot-cross-buns-final-shelbygtdrew.mxl"
)


def _bundle() -> ViewerBundle:
    package = parse_musicxml_package(_FIXTURE.read_bytes(), logical_name=_FIXTURE.name)
    return build_notation_bundle(package)


def test_viewer_bundle_is_versioned_valid_and_deterministic() -> None:
    """TEST-VIEWER-CONTRACT-001: the first wire contract is deterministic."""

    first = _bundle()
    second = _bundle()

    assert first.contract_id == VIEWER_CONTRACT_ID
    assert first.contract_version == VIEWER_CONTRACT_VERSION
    assert first == second
    assert viewer_bundle_to_json(first) == viewer_bundle_to_json(second)
    assert validate_viewer_bundle(first) == ()


def test_renderer_content_and_crosswalk_integrity_fail_closed() -> None:
    """TEST-VIEWER-CONTRACT-002: tampering and missing identities are rejected."""

    bundle = _bundle()
    tampered = replace(
        bundle,
        renderer=replace(bundle.renderer, content=bundle.renderer.content + "<!-- changed -->"),
    )
    assert "VIEWER_RENDERER_DIGEST" in {issue.code for issue in validate_viewer_bundle(tampered)}

    missing_score = replace(
        bundle,
        renderer=replace(
            bundle.renderer,
            anchors=tuple(
                anchor
                for anchor in bundle.renderer.anchors
                if anchor.canonical_id != bundle.score_id
            ),
        ),
    )
    assert "VIEWER_SCORE_ANCHOR_MISSING" in {
        issue.code for issue in validate_viewer_bundle(missing_score)
    }


def test_crosswalk_covers_every_hot_cross_buns_render_entity_once() -> None:
    """TEST-VIEWER-CONTRACT-003: the sidecar maps score, part, measures, and events."""

    bundle = _bundle()
    anchors = bundle.renderer.anchors

    assert len(anchors) == 30
    assert {anchor.canonical_kind for anchor in anchors} == {
        "score",
        "part",
        "measure",
        "event",
    }
    assert len({anchor.canonical_id for anchor in anchors}) == len(anchors)
    assert len({anchor.renderer_anchor for anchor in anchors}) == len(anchors)
    assert all(
        anchor.measure_onset_quarters is not None
        for anchor in anchors
        if anchor.canonical_kind == "event"
    )


def test_event_anchor_onsets_fail_closed_when_missing_or_invalid() -> None:
    """TEST-VIEWER-CONTRACT-004: event highlight positions remain exact."""

    bundle = _bundle()
    event_index = next(
        index
        for index, anchor in enumerate(bundle.renderer.anchors)
        if anchor.canonical_kind == "event"
    )
    anchors = list(bundle.renderer.anchors)
    anchors[event_index] = replace(anchors[event_index], measure_onset_quarters=None)
    missing = replace(bundle, renderer=replace(bundle.renderer, anchors=tuple(anchors)))
    assert "VIEWER_ANCHOR_ONSET" in {issue.code for issue in validate_viewer_bundle(missing)}

    anchors[event_index] = replace(anchors[event_index], measure_onset_quarters="-1/4")
    negative = replace(bundle, renderer=replace(bundle.renderer, anchors=tuple(anchors)))
    assert "VIEWER_ANCHOR_ONSET" in {issue.code for issue in validate_viewer_bundle(negative)}
