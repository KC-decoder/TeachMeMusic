"""Validated canonical-only notation-bundle orchestration."""

from __future__ import annotations

from teachmemusic.score import (
    CanonicalMusicPackage,
    CanonicalScoreContent,
    ScoreDocument,
    parse_musicxml_package,
    require_valid_package,
)
from teachmemusic.score.v2.temporal import TemporalScore

from .contracts import (
    DiagnosticSeverity,
    RendererPayload,
    ViewerBundle,
    ViewerDiagnostic,
    require_valid_viewer_bundle,
)
from .musicxml_renderer import NotationProjectionError, render_score_document
from .render_equivalence import RenderEquivalenceError, require_render_equivalent


def build_notation_bundle(
    package: CanonicalMusicPackage,
    *,
    score_id: str | None = None,
) -> ViewerBundle:
    """Build and verify one notation-only viewer bundle.

    The generated MusicXML is parsed through the public DEV-004 boundary,
    which performs local MusicXML 4.0 validation before canonical mapping.
    Only canonical objects are accepted as input; uploaded source bytes are
    not an argument and cannot be used as a fallback.
    """

    require_valid_package(package)
    document = _select_score_document(package, score_id=score_id)
    rendered = render_score_document(document)
    try:
        reparsed = parse_musicxml_package(
            rendered.content,
            logical_name="teachmemusic-renderer-projection.musicxml",
        )
    except ValueError as error:
        raise NotationProjectionError(
            "VIEWER_NOTATION_REPARSE_FAILED",
            "generated MusicXML could not be reconstructed as a canonical score",
            canonical_id=document.id.value,
        ) from error
    try:
        require_render_equivalent(document, reparsed)
    except RenderEquivalenceError as error:
        raise NotationProjectionError(
            "VIEWER_NOTATION_EQUIVALENCE_FAILED",
            "generated MusicXML changed one or more represented canonical facts",
            canonical_id=document.id.value,
        ) from error
    payload = RendererPayload.from_musicxml(
        rendered.content,
        anchors=rendered.anchors,
        represented_features=rendered.represented_features,
    )
    assert isinstance(document.content, CanonicalScoreContent)
    score = document.content.score
    bundle = ViewerBundle(
        package_id=package.id.value,
        score_id=document.id.value,
        canonical_schema_id=package.schema_id,
        canonical_schema_version=package.schema_version,
        title=_display_title(score),
        renderer=payload,
        diagnostics=(
            *rendered.diagnostics,
            ViewerDiagnostic(
                code="VIEWER_NOTATION_REPARSE_VERIFIED",
                severity=DiagnosticSeverity.INFO,
                message=(
                    "generated MusicXML passed local schema validation, canonical "
                    "re-ingestion, and render-equivalence comparison"
                ),
                canonical_ids=(document.id.value,),
            ),
        ),
    )
    require_valid_viewer_bundle(bundle)
    return bundle


def _display_title(score: TemporalScore) -> str | None:
    """Choose a faithful viewer label without inventing score metadata.

    Some exporters encode a visible title only as a centered page credit. In
    that case the viewer may reuse the exact credit text as its display label;
    the canonical work and movement title fields remain unchanged.
    """

    semantic_title = score.work_title or score.movement_title
    if semantic_title is not None:
        return semantic_title
    if score.layout is None:
        return None
    for credit in score.layout.credits:
        if "title" in credit.types:
            return next(
                (item.value for item in credit.items if item.kind == "words" and item.value),
                None,
            )
    for credit in score.layout.credits:
        if credit.page != 1:
            continue
        centered = next(
            (
                item.value
                for item in credit.items
                if item.kind == "words"
                and item.value
                and item.style is not None
                and item.style.justify == "center"
            ),
            None,
        )
        if centered is not None:
            return centered
    return None


def _select_score_document(
    package: CanonicalMusicPackage,
    *,
    score_id: str | None,
) -> ScoreDocument:
    documents = [item for item in package.documents if isinstance(item, ScoreDocument)]
    if score_id is not None:
        matches = [item for item in documents if item.id.value == score_id]
        if len(matches) != 1:
            raise NotationProjectionError(
                "VIEWER_SCORE_NOT_FOUND",
                "the requested canonical score does not occur exactly once in the package",
                canonical_id=score_id,
            )
        return matches[0]
    root_ids = {item.target_id for item in package.root_documents}
    root_scores = [item for item in documents if item.id.value in root_ids]
    if len(root_scores) == 1:
        return root_scores[0]
    if len(documents) == 1:
        return documents[0]
    raise NotationProjectionError(
        "VIEWER_SCORE_SELECTION_REQUIRED",
        "the package contains multiple score documents; score_id is required",
    )
