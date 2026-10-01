"""Fail-closed validation for deterministic analysis contracts."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass

from teachmemusic.performance.validation import is_stable_id
from teachmemusic.score import (
    CanonicalMusicPackage,
    CanonicalScoreContent,
    ScoreDocument,
    package_to_json,
)

from .contracts import (
    ANALYSIS_CONTRACT_ID,
    ANALYSIS_CONTRACT_VERSION,
    ANALYSIS_VERSION,
    AnalysisConfidence,
    AnalysisDemandDimension,
    AnalysisDerivation,
    AnalysisFactKind,
    BoundaryReason,
    RepetitionKind,
    ScoreAnalysis,
)

_SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")


@dataclass(frozen=True, slots=True)
class AnalysisValidationIssue:
    """One stable analysis-contract invariant failure."""

    code: str
    path: str
    message: str


class AnalysisValidationError(ValueError):
    """Raised when analysis cannot safely cross its public boundary."""

    def __init__(self, issues: tuple[AnalysisValidationIssue, ...]) -> None:
        if not issues:
            raise ValueError("at least one validation issue is required")
        self.issues = issues
        super().__init__(
            "; ".join(f"{issue.code} at {issue.path}: {issue.message}" for issue in issues)
        )


def validate_score_analysis(
    value: ScoreAnalysis,
    package: CanonicalMusicPackage | None = None,
) -> tuple[AnalysisValidationIssue, ...]:
    """Return all internal and optional canonical-reference issues."""

    issues: list[AnalysisValidationIssue] = []
    if value.contract_id != ANALYSIS_CONTRACT_ID:
        _add(issues, "ANALYSIS_CONTRACT_ID", "analysis.contract_id", "unsupported contract ID")
    if value.contract_version != ANALYSIS_CONTRACT_VERSION:
        _add(
            issues,
            "ANALYSIS_CONTRACT_VERSION",
            "analysis.contract_version",
            "unsupported contract version",
        )
    if value.analysis_version != ANALYSIS_VERSION:
        _add(
            issues,
            "ANALYSIS_VERSION",
            "analysis.analysis_version",
            "unsupported analysis rules",
        )
    _id(value.id, "analysis.id", issues)
    if _SHA256_PATTERN.fullmatch(value.canonical_digest_sha256) is None:
        _add(issues, "ANALYSIS_DIGEST", "analysis.canonical_digest_sha256", "invalid digest")
    scope = value.scope
    for name in ("package_id", "score_id"):
        _id(getattr(scope, name), f"analysis.scope.{name}", issues)
    _ids(scope.part_ids, "analysis.scope.part_ids", issues)
    if not scope.part_ids:
        _add(issues, "ANALYSIS_SCOPE_PARTS", "analysis.scope.part_ids", "scope has no parts")
    if scope.start_measure_ordinal < 1 or scope.end_measure_ordinal < scope.start_measure_ordinal:
        _add(issues, "ANALYSIS_SCOPE_RANGE", "analysis.scope", "invalid measure range")
    families = (
        ("facts", value.facts),
        ("layers", value.layers),
        ("repetitions", value.repetitions),
        ("boundaries", value.boundaries),
        ("demands", value.demands),
    )
    seen: set[str] = {value.id}
    for field_name, items in families:
        if not isinstance(items, tuple):
            _add(
                issues,
                "ANALYSIS_IMMUTABLE_COLLECTION",
                f"analysis.{field_name}",
                "expected tuple",
            )
            continue
        for index, item in enumerate(items):
            path = f"analysis.{field_name}[{index}].id"
            identifier = getattr(item, "id", None)
            _id(identifier, path, issues)
            if identifier in seen:
                _add(issues, "ANALYSIS_ID_DUPLICATE", path, "ID is duplicated")
            if isinstance(identifier, str):
                seen.add(identifier)
    for index, fact in enumerate(value.facts):
        path = f"analysis.facts[{index}]"
        if not isinstance(fact.kind, AnalysisFactKind):
            _add(issues, "ANALYSIS_FACT_KIND", f"{path}.kind", "unknown fact kind")
        if not isinstance(fact.derivation, AnalysisDerivation):
            _add(issues, "ANALYSIS_DERIVATION", f"{path}.derivation", "unknown derivation")
        _required(fact.value, f"{path}.value", issues)
        _required(fact.algorithm, f"{path}.algorithm", issues)
        _ids(fact.evidence_ids, f"{path}.evidence_ids", issues)
        if not fact.evidence_ids:
            _add(issues, "ANALYSIS_EVIDENCE_EMPTY", f"{path}.evidence_ids", "no evidence")
    layer_ids = {item.id for item in value.layers}
    for index, layer in enumerate(value.layers):
        path = f"analysis.layers[{index}]"
        for name in ("part_id", "staff_id", "voice_id"):
            _id(getattr(layer, name), f"{path}.{name}", issues)
        _ids(layer.measure_ids, f"{path}.measure_ids", issues)
        _ids(layer.event_ids, f"{path}.event_ids", issues)
        if (
            layer.pitched_event_count < 0
            or layer.unpitched_event_count < 0
            or layer.rest_event_count < 0
        ):
            _add(issues, "ANALYSIS_COUNT", path, "event count is negative")
        if layer.pitched_event_count + layer.unpitched_event_count + layer.rest_event_count != len(
            layer.event_ids
        ):
            _add(issues, "ANALYSIS_LAYER_COUNT", path, "layer counts do not cover events")
        if (layer.lowest_written_semitone is None) != (layer.highest_written_semitone is None):
            _add(issues, "ANALYSIS_RANGE", path, "pitch range is incomplete")
        if (
            layer.lowest_written_semitone is not None
            and layer.highest_written_semitone is not None
            and layer.lowest_written_semitone > layer.highest_written_semitone
        ):
            _add(issues, "ANALYSIS_RANGE", path, "pitch range is reversed")
    if tuple(sorted(set(value.rhythm.written_durations))) != value.rhythm.written_durations:
        _add(
            issues,
            "ANALYSIS_RHYTHM_ORDER",
            "analysis.rhythm.written_durations",
            "durations are not unique and sorted",
        )
    _ids(value.rhythm.evidence_event_ids, "analysis.rhythm.evidence_event_ids", issues)
    _ids(value.texture.evidence_ids, "analysis.texture.evidence_ids", issues)
    for name in (
        "layer_count",
        "staff_count",
        "voice_count",
        "chord_count",
        "max_simultaneous_pitches",
        "max_active_layers",
    ):
        if getattr(value.texture, name) < 0:
            _add(issues, "ANALYSIS_COUNT", f"analysis.texture.{name}", "value is negative")
    for index, group in enumerate(value.repetitions):
        path = f"analysis.repetitions[{index}]"
        if not isinstance(group.kind, RepetitionKind):
            _add(issues, "ANALYSIS_REPETITION_KIND", f"{path}.kind", "unknown kind")
        if group.layer_id not in layer_ids:
            _add(issues, "ANALYSIS_LAYER_REFERENCE", f"{path}.layer_id", "layer is missing")
        _ids(group.occurrence_measure_ids, f"{path}.occurrence_measure_ids", issues)
        _ids(group.evidence_event_ids, f"{path}.evidence_event_ids", issues)
        if len(group.occurrence_measure_ids) < 2:
            _add(issues, "ANALYSIS_REPETITION_SIZE", path, "fewer than two occurrences")
    previous_onset = None
    for index, boundary in enumerate(value.boundaries):
        path = f"analysis.boundaries[{index}]"
        _ids(boundary.measure_ids, f"{path}.measure_ids", issues)
        _ids(boundary.evidence_ids, f"{path}.evidence_ids", issues)
        if not boundary.reasons:
            _add(issues, "ANALYSIS_BOUNDARY_REASON", f"{path}.reasons", "no reason")
        for reason in boundary.reasons:
            if not isinstance(reason, BoundaryReason):
                _add(issues, "ANALYSIS_BOUNDARY_REASON", f"{path}.reasons", "unknown reason")
        if not isinstance(boundary.confidence, AnalysisConfidence):
            _add(issues, "ANALYSIS_CONFIDENCE", f"{path}.confidence", "unknown confidence")
        if boundary.fallback != (boundary.reasons == (BoundaryReason.MEASURE_FALLBACK,)):
            _add(issues, "ANALYSIS_BOUNDARY_FALLBACK", path, "fallback flag differs from reasons")
        if previous_onset is not None and boundary.score_onset <= previous_onset:
            _add(issues, "ANALYSIS_BOUNDARY_ORDER", f"{path}.score_onset", "not increasing")
        previous_onset = boundary.score_onset
    for index, demand in enumerate(value.demands):
        path = f"analysis.demands[{index}]"
        if not isinstance(demand.dimension, AnalysisDemandDimension):
            _add(issues, "ANALYSIS_DEMAND_DIMENSION", f"{path}.dimension", "unknown dimension")
        if demand.level is not None and not 0 <= demand.level <= 5:
            _add(issues, "ANALYSIS_DEMAND_LEVEL", f"{path}.level", "level is outside 0..5")
        if demand.level is None and not demand.uncertainty:
            _add(issues, "ANALYSIS_DEMAND_UNCERTAINTY", path, "unknown level has no explanation")
        _required(demand.metric, f"{path}.metric", issues)
        _required(demand.rationale, f"{path}.rationale", issues)
        _ids(demand.evidence_ids, f"{path}.evidence_ids", issues)
    _strings(value.limitations, "analysis.limitations", issues)
    if package is not None:
        _validate_against_package(value, package, issues)
    return tuple(issues)


def require_valid_score_analysis(
    value: ScoreAnalysis,
    package: CanonicalMusicPackage | None = None,
) -> None:
    """Raise when an analysis violates internal or canonical invariants."""

    issues = validate_score_analysis(value, package)
    if issues:
        raise AnalysisValidationError(issues)


def _validate_against_package(
    value: ScoreAnalysis,
    package: CanonicalMusicPackage,
    issues: list[AnalysisValidationIssue],
) -> None:
    digest = hashlib.sha256(package_to_json(package).encode()).hexdigest()
    if value.canonical_digest_sha256 != digest:
        _add(
            issues,
            "ANALYSIS_PACKAGE_DIGEST",
            "analysis.canonical_digest_sha256",
            "digest differs",
        )
    if value.scope.package_id != package.id.value:
        _add(issues, "ANALYSIS_PACKAGE_REFERENCE", "analysis.scope.package_id", "package differs")
    document = next(
        (
            item
            for item in package.documents
            if isinstance(item, ScoreDocument) and item.id.value == value.scope.score_id
        ),
        None,
    )
    if document is None or not isinstance(document.content, CanonicalScoreContent):
        _add(issues, "ANALYSIS_SCORE_REFERENCE", "analysis.scope.score_id", "score is missing")
        return
    score = document.content.score
    canonical_ids = {package.id.value, document.id.value}
    scoped_ids: set[str] = {package.id.value, document.id.value}
    known_parts = {part.id for part in score.parts}
    for part in score.parts:
        canonical_ids.add(part.id)
        canonical_ids.update(staff.id for staff in part.staves)
        canonical_ids.update(voice.id for voice in part.voices)
        for measure in part.measures:
            canonical_ids.add(measure.id)
            canonical_ids.update(event.id for event in measure.events)
            canonical_ids.update(
                event.chord_id for event in measure.events if event.chord_id is not None
            )
            if (
                part.id in value.scope.part_ids
                and value.scope.start_measure_ordinal
                <= measure.ordinal
                <= value.scope.end_measure_ordinal
            ):
                scoped_ids.add(part.id)
                scoped_ids.update(staff.id for staff in part.staves)
                scoped_ids.update(voice.id for voice in part.voices)
                scoped_ids.add(measure.id)
                scoped_ids.update(event.id for event in measure.events)
                scoped_ids.update(
                    event.chord_id for event in measure.events if event.chord_id is not None
                )
    missing_parts = set(value.scope.part_ids) - known_parts
    if missing_parts:
        _add(
            issues,
            "ANALYSIS_PART_REFERENCE",
            "analysis.scope.part_ids",
            f"unknown parts: {sorted(missing_parts)!r}",
        )
    evidence_ids = _analysis_evidence_ids(value)
    foreign = evidence_ids - canonical_ids
    if foreign:
        _add(
            issues,
            "ANALYSIS_CANONICAL_REFERENCE",
            "analysis",
            f"unknown canonical evidence: {sorted(foreign)!r}",
        )
    outside = evidence_ids - scoped_ids
    if outside:
        _add(
            issues,
            "ANALYSIS_SCOPE_REFERENCE",
            "analysis",
            f"evidence lies outside scope: {sorted(outside)!r}",
        )


def _analysis_evidence_ids(value: ScoreAnalysis) -> set[str]:
    result: set[str] = set()
    for fact in value.facts:
        result.update(fact.evidence_ids)
    for layer in value.layers:
        result.update((layer.part_id, layer.staff_id, layer.voice_id))
        result.update(layer.measure_ids)
        result.update(layer.event_ids)
    result.update(value.rhythm.evidence_event_ids)
    result.update(value.texture.evidence_ids)
    for group in value.repetitions:
        result.update(group.occurrence_measure_ids)
        result.update(group.evidence_event_ids)
    for boundary in value.boundaries:
        result.update(boundary.measure_ids)
        result.update(boundary.evidence_ids)
    for demand in value.demands:
        result.update(demand.evidence_ids)
    return result


def _id(value: object, path: str, issues: list[AnalysisValidationIssue]) -> None:
    if not is_stable_id(value):
        _add(issues, "ANALYSIS_STABLE_ID", path, "expected namespaced stable ID")


def _ids(values: object, path: str, issues: list[AnalysisValidationIssue]) -> None:
    if not isinstance(values, tuple):
        _add(issues, "ANALYSIS_IMMUTABLE_COLLECTION", path, "expected tuple")
        return
    if len(set(values)) != len(values):
        _add(issues, "ANALYSIS_REFERENCE_DUPLICATE", path, "reference repeats")
    for index, value in enumerate(values):
        _id(value, f"{path}[{index}]", issues)


def _required(value: object, path: str, issues: list[AnalysisValidationIssue]) -> None:
    if not isinstance(value, str) or not value.strip():
        _add(issues, "ANALYSIS_REQUIRED_TEXT", path, "value is empty")


def _strings(values: object, path: str, issues: list[AnalysisValidationIssue]) -> None:
    if not isinstance(values, tuple):
        _add(issues, "ANALYSIS_IMMUTABLE_COLLECTION", path, "expected tuple")
        return
    for index, value in enumerate(values):
        _required(value, f"{path}[{index}]", issues)


def _add(
    issues: list[AnalysisValidationIssue],
    code: str,
    path: str,
    message: str,
) -> None:
    issues.append(AnalysisValidationIssue(code, path, message))
