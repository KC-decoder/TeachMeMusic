"""TeachMeMusic-owned contracts for canonical score consumers.

The contracts in this module deliberately contain no parser, XML-library,
renderer, browser, or audio-engine objects. They are the only values that a
future application boundary may expose to the notation UI.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from enum import StrEnum
from fractions import Fraction

VIEWER_CONTRACT_ID = "org.teachmemusic.viewer-bundle"
VIEWER_CONTRACT_VERSION = "0.2.0"


class DiagnosticSeverity(StrEnum):
    """Stable severity values exposed by viewer projections."""

    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


@dataclass(frozen=True, slots=True)
class ViewerDiagnostic:
    """A structured, source-independent consumer diagnostic."""

    code: str
    severity: DiagnosticSeverity
    message: str
    canonical_ids: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class RenderAnchor:
    """Map one canonical identity to a deterministic renderer location."""

    canonical_id: str
    canonical_kind: str
    renderer_anchor: str
    renderer_part_id: str | None = None
    part_index: int | None = None
    measure_index: int | None = None
    event_index: int | None = None
    measure_onset_quarters: str | None = None


@dataclass(frozen=True, slots=True)
class RendererPayload:
    """Validated renderer interchange payload and its canonical crosswalk."""

    renderer: str
    media_type: str
    encoding: str
    content: str
    sha256: str
    anchors: tuple[RenderAnchor, ...]
    represented_features: tuple[str, ...]

    @classmethod
    def from_musicxml(
        cls,
        content: bytes,
        *,
        anchors: tuple[RenderAnchor, ...],
        represented_features: tuple[str, ...],
    ) -> RendererPayload:
        """Create an OSMD payload from deterministic UTF-8 MusicXML bytes."""

        return cls(
            renderer="opensheetmusicdisplay",
            media_type="application/vnd.recordare.musicxml+xml",
            encoding="utf-8",
            content=content.decode("utf-8"),
            sha256=hashlib.sha256(content).hexdigest(),
            anchors=anchors,
            represented_features=represented_features,
        )


@dataclass(frozen=True, slots=True)
class ViewerBundle:
    """Versioned canonical-only notation bundle for the first DEV-005 slice."""

    package_id: str
    score_id: str
    canonical_schema_id: str
    canonical_schema_version: str
    title: str | None
    renderer: RendererPayload
    diagnostics: tuple[ViewerDiagnostic, ...] = ()
    capabilities: tuple[str, ...] = ("notation",)
    contract_id: str = VIEWER_CONTRACT_ID
    contract_version: str = VIEWER_CONTRACT_VERSION


@dataclass(frozen=True, slots=True)
class ViewerContractIssue:
    """One stable validation issue in a viewer boundary value."""

    code: str
    path: str
    message: str


class ViewerContractError(ValueError):
    """Raised when an invalid bundle would cross the viewer boundary."""

    def __init__(self, issues: tuple[ViewerContractIssue, ...]) -> None:
        self.issues = issues
        first = issues[0]
        super().__init__(f"{first.code} at {first.path}: {first.message}")


def validate_viewer_bundle(bundle: ViewerBundle) -> tuple[ViewerContractIssue, ...]:
    """Validate identity, integrity, and crosswalk invariants."""

    issues: list[ViewerContractIssue] = []
    if bundle.contract_id != VIEWER_CONTRACT_ID:
        issues.append(
            ViewerContractIssue(
                "VIEWER_CONTRACT_ID",
                "contract_id",
                "the viewer contract identifier is unsupported",
            )
        )
    if bundle.contract_version != VIEWER_CONTRACT_VERSION:
        issues.append(
            ViewerContractIssue(
                "VIEWER_CONTRACT_VERSION",
                "contract_version",
                "the viewer contract version is unsupported",
            )
        )
    for path, value in (
        ("package_id", bundle.package_id),
        ("score_id", bundle.score_id),
        ("canonical_schema_id", bundle.canonical_schema_id),
        ("canonical_schema_version", bundle.canonical_schema_version),
    ):
        if not value:
            issues.append(ViewerContractIssue("VIEWER_REQUIRED_VALUE", path, "value is empty"))

    payload = bundle.renderer
    if payload.renderer != "opensheetmusicdisplay":
        issues.append(
            ViewerContractIssue(
                "VIEWER_RENDERER",
                "renderer.renderer",
                "the first viewer contract supports only OpenSheetMusicDisplay",
            )
        )
    if payload.media_type != "application/vnd.recordare.musicxml+xml":
        issues.append(
            ViewerContractIssue(
                "VIEWER_RENDERER_MEDIA_TYPE",
                "renderer.media_type",
                "renderer content must be MusicXML",
            )
        )
    if payload.encoding.lower() != "utf-8":
        issues.append(
            ViewerContractIssue(
                "VIEWER_RENDERER_ENCODING",
                "renderer.encoding",
                "renderer content must use UTF-8",
            )
        )
    digest = hashlib.sha256(payload.content.encode("utf-8")).hexdigest()
    if payload.sha256 != digest:
        issues.append(
            ViewerContractIssue(
                "VIEWER_RENDERER_DIGEST",
                "renderer.sha256",
                "renderer content does not match its digest",
            )
        )
    if not payload.content.startswith("<?xml"):
        issues.append(
            ViewerContractIssue(
                "VIEWER_RENDERER_CONTENT",
                "renderer.content",
                "renderer content is not an XML document",
            )
        )

    canonical_ids: set[str] = set()
    renderer_anchors: set[str] = set()
    for index, anchor in enumerate(payload.anchors):
        path = f"renderer.anchors[{index}]"
        if not anchor.canonical_id:
            issues.append(
                ViewerContractIssue("VIEWER_ANCHOR_CANONICAL_ID", path, "canonical ID is empty")
            )
        elif anchor.canonical_id in canonical_ids:
            issues.append(
                ViewerContractIssue(
                    "VIEWER_ANCHOR_CANONICAL_DUPLICATE",
                    path,
                    "canonical ID occurs more than once in the crosswalk",
                )
            )
        canonical_ids.add(anchor.canonical_id)
        if not anchor.renderer_anchor:
            issues.append(
                ViewerContractIssue("VIEWER_ANCHOR_RENDERER_ID", path, "renderer anchor is empty")
            )
        elif anchor.renderer_anchor in renderer_anchors:
            issues.append(
                ViewerContractIssue(
                    "VIEWER_ANCHOR_RENDERER_DUPLICATE",
                    path,
                    "renderer anchor occurs more than once in the crosswalk",
                )
            )
        renderer_anchors.add(anchor.renderer_anchor)
        if anchor.part_index is not None and anchor.part_index < 0:
            issues.append(
                ViewerContractIssue(
                    "VIEWER_ANCHOR_INDEX",
                    f"{path}.part_index",
                    "index is negative",
                )
            )
        if anchor.measure_index is not None and anchor.measure_index < 0:
            issues.append(
                ViewerContractIssue(
                    "VIEWER_ANCHOR_INDEX", f"{path}.measure_index", "index is negative"
                )
            )
        if anchor.event_index is not None and anchor.event_index < 0:
            issues.append(
                ViewerContractIssue(
                    "VIEWER_ANCHOR_INDEX",
                    f"{path}.event_index",
                    "index is negative",
                )
            )
        if anchor.canonical_kind == "event":
            if anchor.measure_onset_quarters is None:
                issues.append(
                    ViewerContractIssue(
                        "VIEWER_ANCHOR_ONSET",
                        f"{path}.measure_onset_quarters",
                        "event anchor onset is missing",
                    )
                )
            else:
                try:
                    onset = Fraction(anchor.measure_onset_quarters)
                except (ValueError, ZeroDivisionError):
                    issues.append(
                        ViewerContractIssue(
                            "VIEWER_ANCHOR_ONSET",
                            f"{path}.measure_onset_quarters",
                            "event anchor onset is not an exact rational number",
                        )
                    )
                else:
                    if onset < 0:
                        issues.append(
                            ViewerContractIssue(
                                "VIEWER_ANCHOR_ONSET",
                                f"{path}.measure_onset_quarters",
                                "event anchor onset is negative",
                            )
                        )

    if bundle.score_id not in canonical_ids:
        issues.append(
            ViewerContractIssue(
                "VIEWER_SCORE_ANCHOR_MISSING",
                "renderer.anchors",
                "the selected score has no renderer crosswalk entry",
            )
        )
    return tuple(issues)


def require_valid_viewer_bundle(bundle: ViewerBundle) -> None:
    """Raise when a bundle cannot safely cross the application boundary."""

    issues = validate_viewer_bundle(bundle)
    if issues:
        raise ViewerContractError(issues)


def viewer_bundle_to_dict(bundle: ViewerBundle) -> dict[str, object]:
    """Return a deterministic JSON-ready representation."""

    return {
        "contract_id": bundle.contract_id,
        "contract_version": bundle.contract_version,
        "capabilities": list(bundle.capabilities),
        "package_id": bundle.package_id,
        "score_id": bundle.score_id,
        "canonical_schema_id": bundle.canonical_schema_id,
        "canonical_schema_version": bundle.canonical_schema_version,
        "title": bundle.title,
        "renderer": {
            "renderer": bundle.renderer.renderer,
            "media_type": bundle.renderer.media_type,
            "encoding": bundle.renderer.encoding,
            "sha256": bundle.renderer.sha256,
            "content": bundle.renderer.content,
            "represented_features": list(bundle.renderer.represented_features),
            "anchors": [
                {
                    "canonical_id": anchor.canonical_id,
                    "canonical_kind": anchor.canonical_kind,
                    "renderer_anchor": anchor.renderer_anchor,
                    "renderer_part_id": anchor.renderer_part_id,
                    "part_index": anchor.part_index,
                    "measure_index": anchor.measure_index,
                    "event_index": anchor.event_index,
                    "measure_onset_quarters": anchor.measure_onset_quarters,
                }
                for anchor in bundle.renderer.anchors
            ],
        },
        "diagnostics": [
            {
                "code": item.code,
                "severity": item.severity.value,
                "message": item.message,
                "canonical_ids": list(item.canonical_ids),
            }
            for item in bundle.diagnostics
        ],
    }


def viewer_bundle_to_json(bundle: ViewerBundle) -> str:
    """Serialize a validated viewer bundle deterministically."""

    require_valid_viewer_bundle(bundle)
    return json.dumps(
        viewer_bundle_to_dict(bundle),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
