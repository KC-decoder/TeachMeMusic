"""Non-human verification helpers for DEV-009 Tasks 9L and 9M.

This module exercises the production analysis and curriculum generators while
keeping golden-oracle and synthetic-simulation results outside learner
evidence.  It is verification infrastructure, not a second teaching policy.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from enum import StrEnum
from fractions import Fraction

from teachmemusic.analysis import ScoreAnalysis, analyze_canonical_score
from teachmemusic.score import CanonicalMusicPackage, CanonicalScoreContent, ScoreDocument

from .acquisition import generate_acquisition_graph
from .branches import generate_prerequisite_branches
from .curriculum_contracts import (
    AcquisitionGraphSlice,
    ArtifactResolution,
    CompatibleTempoEvidence,
    PassageRequirementSet,
    SemanticReference,
    TempoReferenceAuthority,
)
from .curriculum_fingerprint import derived_id, semantic_fingerprint
from .requirements import derive_passage_requirements

CURRICULUM_VERIFICATION_VERSION = "0.1.0"
NON_HUMAN_VERIFICATION_LIMITATION = "TMM-VERIFY-NON-HUMAN-EVIDENCE"


class VerificationAuthority(StrEnum):
    """Evidence authority admitted by this verification-only boundary."""

    GOLDEN_ORACLE = "golden-oracle"
    SYNTHETIC_SIMULATION = "synthetic-simulation"


class SyntheticLearnerProfileKind(StrEnum):
    """Bounded synthetic conditions required by ADR-0012."""

    DIAGNOSTIC_REQUIRED = "diagnostic-required"
    REDUCED_TEMPO = "reduced-tempo"
    RHYTHM_READY = "rhythm-ready"


@dataclass(frozen=True, slots=True)
class SyntheticLearnerProfile:
    """One fixed non-human condition for deterministic-policy verification."""

    schema_version: str
    id: str
    semantic_fingerprint: str
    kind: SyntheticLearnerProfileKind
    controlled_percentage: int | None
    supported_ceiling_percentage: int | None
    required_non_tempo_gates_passed: bool
    pulse_gate_passed: bool
    decision_budget: int
    authority: VerificationAuthority
    human_evidence_eligible: bool


@dataclass(frozen=True, slots=True)
class CurriculumVerificationLimitation:
    """One explicit boundary on what a verification report establishes."""

    code: str
    detail: str


@dataclass(frozen=True, slots=True)
class CurriculumRouteStructuralSignature:
    """Title- and path-free structural projection of one generated route."""

    resolution: ArtifactResolution
    measure_count: int
    layer_count: int
    staff_count: int
    voice_count: int
    chord_count: int
    scope_shapes: tuple[tuple[str, str, int, int, int, int], ...]
    primitive_ids: tuple[str, ...]
    stage_kinds: tuple[str, ...]
    controlled_percentages: tuple[int | None, ...]
    diagnostic_codes: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class CurriculumVerificationReport:
    """Content-addressed report that can never qualify as learner evidence."""

    schema_version: str
    id: str
    semantic_fingerprint: str
    authority: VerificationAuthority
    profile_ref: SemanticReference
    score_package_digest: str
    score_id: str
    analysis_id: str
    graph_ref: SemanticReference
    start_measure_ordinal: int
    end_measure_ordinal: int
    structural_signature: CurriculumRouteStructuralSignature
    limitations: tuple[CurriculumVerificationLimitation, ...]
    human_evidence_eligible: bool


class CurriculumVerificationError(ValueError):
    """Raised when synthetic or golden verification crosses its boundary."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(f"{code}: {message}")


def default_synthetic_learner_profiles() -> tuple[SyntheticLearnerProfile, ...]:
    """Return the finite profiles used to verify both ADR-0012 entry paths."""

    specifications = (
        (
            SyntheticLearnerProfileKind.DIAGNOSTIC_REQUIRED,
            None,
            None,
            False,
            False,
            4,
        ),
        (SyntheticLearnerProfileKind.REDUCED_TEMPO, 55, 55, True, True, 16),
        (SyntheticLearnerProfileKind.RHYTHM_READY, 100, 100, True, True, 16),
    )
    profiles: list[SyntheticLearnerProfile] = []
    for kind, controlled, ceiling, non_tempo, pulse, budget in specifications:
        provisional = SyntheticLearnerProfile(
            schema_version=CURRICULUM_VERIFICATION_VERSION,
            id="synthetic-learner-profile:pending",
            semantic_fingerprint="",
            kind=kind,
            controlled_percentage=controlled,
            supported_ceiling_percentage=ceiling,
            required_non_tempo_gates_passed=non_tempo,
            pulse_gate_passed=pulse,
            decision_budget=budget,
            authority=VerificationAuthority.SYNTHETIC_SIMULATION,
            human_evidence_eligible=False,
        )
        profile = replace(
            provisional,
            id=derived_id("synthetic-learner-profile", provisional),
            semantic_fingerprint=semantic_fingerprint(provisional),
        )
        require_valid_synthetic_learner_profile(profile)
        profiles.append(profile)
    return tuple(profiles)


def require_valid_synthetic_learner_profile(profile: SyntheticLearnerProfile) -> None:
    """Fail closed if a synthetic profile is unbounded or claims human status."""

    if profile.schema_version != CURRICULUM_VERIFICATION_VERSION:
        raise CurriculumVerificationError(
            "TMM-VERIFY-PROFILE-VERSION", "unsupported synthetic-profile version"
        )
    if (
        profile.authority is not VerificationAuthority.SYNTHETIC_SIMULATION
        or profile.human_evidence_eligible
    ):
        raise CurriculumVerificationError(
            "TMM-VERIFY-AUTHORITY", "synthetic profiles cannot become learner evidence"
        )
    if not 1 <= profile.decision_budget <= 64:
        raise CurriculumVerificationError(
            "TMM-VERIFY-PROFILE-BOUNDS", "decision budget must be between 1 and 64"
        )
    percentages = (profile.controlled_percentage, profile.supported_ceiling_percentage)
    if profile.kind is SyntheticLearnerProfileKind.DIAGNOSTIC_REQUIRED:
        if percentages != (None, None) or any(
            (profile.required_non_tempo_gates_passed, profile.pulse_gate_passed)
        ):
            raise CurriculumVerificationError(
                "TMM-VERIFY-PROFILE-BOUNDS",
                "diagnostic-required profile cannot fabricate compatible tempo evidence",
            )
    elif (
        profile.controlled_percentage is None
        or profile.supported_ceiling_percentage is None
        or not 1 <= profile.controlled_percentage <= profile.supported_ceiling_percentage <= 100
        or not profile.required_non_tempo_gates_passed
        or not profile.pulse_gate_passed
    ):
        raise CurriculumVerificationError(
            "TMM-VERIFY-PROFILE-BOUNDS",
            "resolved synthetic tempo must be compatible and between 1 and 100 percent",
        )
    if profile.semantic_fingerprint != semantic_fingerprint(profile):
        raise CurriculumVerificationError(
            "TMM-VERIFY-FINGERPRINT", "synthetic-profile fingerprint has drifted"
        )
    if profile.id != f"synthetic-learner-profile:{profile.semantic_fingerprint}":
        raise CurriculumVerificationError(
            "TMM-VERIFY-FINGERPRINT", "synthetic-profile identifier has drifted"
        )


def build_synthetic_tempo_evidence(
    requirements: PassageRequirementSet,
    profile: SyntheticLearnerProfile,
) -> tuple[CompatibleTempoEvidence, ...]:
    """Project a synthetic condition without creating learner evidence records."""

    require_valid_synthetic_learner_profile(profile)
    if profile.kind is SyntheticLearnerProfileKind.DIAGNOSTIC_REQUIRED:
        return ()
    assert profile.controlled_percentage is not None
    assert profile.supported_ceiling_percentage is not None
    return tuple(
        CompatibleTempoEvidence(
            practice_scope_ref=SemanticReference(
                "practice-scope-assignment", scope.id, scope.semantic_fingerprint
            ),
            support_condition="independent-piece",
            controlled_percentage=profile.controlled_percentage,
            supported_ceiling_percentage=profile.supported_ceiling_percentage,
            required_non_tempo_gates_passed=profile.required_non_tempo_gates_passed,
            pulse_gate_passed=profile.pulse_gate_passed,
            evidence_refs=(f"synthetic-verification-signal:{profile.id}:{scope.id}",),
        )
        for scope in requirements.scopes
        if scope.resolution is ArtifactResolution.RESOLVED
    )


def build_curriculum_verification_report(
    package: CanonicalMusicPackage,
    profile: SyntheticLearnerProfile,
    *,
    start_measure_ordinal: int = 1,
    end_measure_ordinal: int | None = None,
    part_ids: tuple[str, ...] = (),
    reference_tempo_bpm: Fraction = Fraction(60),
    reference_authority: TempoReferenceAuthority = TempoReferenceAuthority.CALLER,
) -> CurriculumVerificationReport:
    """Exercise production generators and emit a non-human structural report."""

    require_valid_synthetic_learner_profile(profile)
    analysis = analyze_canonical_score(
        package,
        part_ids=part_ids,
        start_measure_ordinal=start_measure_ordinal,
        end_measure_ordinal=end_measure_ordinal,
    )
    requirements = derive_passage_requirements(package, analysis)
    branches = generate_prerequisite_branches(requirements)
    graph = generate_acquisition_graph(
        requirements,
        branches,
        reference_tempo_bpm=reference_tempo_bpm,
        reference_authority=reference_authority,
        tempo_evidence=build_synthetic_tempo_evidence(requirements, profile),
    )
    signature = _structural_signature(analysis, requirements, graph)
    limitations = _limitations(package, analysis, requirements, graph)
    provisional = CurriculumVerificationReport(
        schema_version=CURRICULUM_VERIFICATION_VERSION,
        id="curriculum-verification-report:pending",
        semantic_fingerprint="",
        authority=VerificationAuthority.SYNTHETIC_SIMULATION,
        profile_ref=SemanticReference(
            "synthetic-learner-profile", profile.id, profile.semantic_fingerprint
        ),
        score_package_digest=analysis.canonical_digest_sha256,
        score_id=analysis.scope.score_id,
        analysis_id=analysis.id,
        graph_ref=SemanticReference(
            "acquisition-graph-slice", graph.id, graph.semantic_fingerprint
        ),
        start_measure_ordinal=analysis.scope.start_measure_ordinal,
        end_measure_ordinal=analysis.scope.end_measure_ordinal,
        structural_signature=signature,
        limitations=limitations,
        human_evidence_eligible=False,
    )
    report = replace(
        provisional,
        id=derived_id("curriculum-verification-report", provisional),
        semantic_fingerprint=semantic_fingerprint(provisional),
    )
    require_valid_curriculum_verification_report(report)
    return report


def require_valid_curriculum_verification_report(report: CurriculumVerificationReport) -> None:
    """Protect the explicit non-human authority and content-addressed identity."""

    if report.schema_version != CURRICULUM_VERIFICATION_VERSION:
        raise CurriculumVerificationError(
            "TMM-VERIFY-REPORT-VERSION", "unsupported verification-report version"
        )
    if (
        report.authority
        not in {
            VerificationAuthority.GOLDEN_ORACLE,
            VerificationAuthority.SYNTHETIC_SIMULATION,
        }
        or report.human_evidence_eligible
    ):
        raise CurriculumVerificationError(
            "TMM-VERIFY-AUTHORITY", "verification reports cannot become learner evidence"
        )
    if (
        report.start_measure_ordinal < 1
        or report.end_measure_ordinal < report.start_measure_ordinal
    ):
        raise CurriculumVerificationError(
            "TMM-VERIFY-SCOPE", "verification-report measure scope is invalid"
        )
    if not any(item.code == NON_HUMAN_VERIFICATION_LIMITATION for item in report.limitations):
        raise CurriculumVerificationError("TMM-VERIFY-AUTHORITY", "non-human limitation is missing")
    if report.semantic_fingerprint != semantic_fingerprint(report):
        raise CurriculumVerificationError(
            "TMM-VERIFY-FINGERPRINT", "verification-report fingerprint has drifted"
        )
    if report.id != f"curriculum-verification-report:{report.semantic_fingerprint}":
        raise CurriculumVerificationError(
            "TMM-VERIFY-FINGERPRINT", "verification-report identifier has drifted"
        )


def curriculum_route_structural_dict(
    report: CurriculumVerificationReport,
) -> dict[str, object]:
    """Return the small title-free projection stored in reviewed golden fixtures."""

    require_valid_curriculum_verification_report(report)
    signature = report.structural_signature
    return {
        "resolution": signature.resolution.value,
        "measure_count": signature.measure_count,
        "layer_count": signature.layer_count,
        "staff_count": signature.staff_count,
        "voice_count": signature.voice_count,
        "chord_count": signature.chord_count,
        "scope_shapes": [list(item) for item in signature.scope_shapes],
        "primitive_ids": list(signature.primitive_ids),
        "stage_kinds": list(signature.stage_kinds),
        "controlled_percentages": list(signature.controlled_percentages),
        "diagnostic_codes": list(signature.diagnostic_codes),
    }


def _structural_signature(
    analysis: ScoreAnalysis,
    requirements: PassageRequirementSet,
    graph: AcquisitionGraphSlice,
) -> CurriculumRouteStructuralSignature:
    return CurriculumRouteStructuralSignature(
        resolution=graph.resolution,
        measure_count=(
            analysis.scope.end_measure_ordinal - analysis.scope.start_measure_ordinal + 1
        ),
        layer_count=analysis.texture.layer_count,
        staff_count=analysis.texture.staff_count,
        voice_count=analysis.texture.voice_count,
        chord_count=analysis.texture.chord_count,
        scope_shapes=tuple(
            (
                scope.notation_condition.value,
                scope.resolution.value,
                len(scope.active_target_ids),
                len(scope.inactive_context_ids),
                len(scope.component_scope_ids),
                len(scope.layer_groups),
            )
            for scope in requirements.scopes
        ),
        primitive_ids=tuple(sorted({item.primitive_ref.id for item in requirements.requirements})),
        stage_kinds=tuple(item.kind.value for item in graph.stages),
        controlled_percentages=tuple(
            item.current_controlled_percentage for item in graph.tempo_plans
        ),
        diagnostic_codes=tuple(item.code for item in graph.diagnostics),
    )


def _limitations(
    package: CanonicalMusicPackage,
    analysis: ScoreAnalysis,
    requirements: PassageRequirementSet,
    graph: AcquisitionGraphSlice,
) -> tuple[CurriculumVerificationLimitation, ...]:
    limitations = [
        CurriculumVerificationLimitation(
            NON_HUMAN_VERIFICATION_LIMITATION,
            "Golden and synthetic results verify software behavior, not human learning.",
        ),
        CurriculumVerificationLimitation(
            "TMM-VERIFY-PHYSICAL-TECHNIQUE-UNOBSERVED",
            "Notation and simulated conditions do not establish fingering, posture, tension, "
            "tone quality, or physical safety.",
        ),
    ]
    total_parts, available_end = _score_extent(package, analysis)
    if (
        analysis.scope.start_measure_ordinal != 1
        or analysis.scope.end_measure_ordinal != available_end
    ):
        limitations.append(
            CurriculumVerificationLimitation(
                "TMM-VERIFY-REPRESENTATIVE-PASSAGE",
                "The report covers a bounded representative passage, not the complete score.",
            )
        )
    if len(analysis.scope.part_ids) != total_parts:
        limitations.append(
            CurriculumVerificationLimitation(
                "TMM-VERIFY-PART-SELECTION",
                "The report covers selected score parts; cross-part coordination is unverified.",
            )
        )
    if any(scope.execution_assignment.value == "unassigned" for scope in requirements.scopes):
        limitations.append(
            CurriculumVerificationLimitation(
                "TMM-VERIFY-EXECUTION-ASSIGNMENT-UNREVIEWED",
                "Notation-layer grouping does not independently prove a hand assignment.",
            )
        )
    if graph.resolution is not ArtifactResolution.RESOLVED:
        limitations.append(
            CurriculumVerificationLimitation(
                "TMM-VERIFY-UNRESOLVED-PEDAGOGY",
                "No playable route is claimed while review diagnostics remain unresolved: "
                + ", ".join(item.code for item in graph.diagnostics),
            )
        )
    return tuple(limitations)


def _score_extent(package: CanonicalMusicPackage, analysis: ScoreAnalysis) -> tuple[int, int]:
    document = next(
        item
        for item in package.documents
        if isinstance(item, ScoreDocument)
        and item.id.value == analysis.scope.score_id
        and isinstance(item.content, CanonicalScoreContent)
    )
    assert isinstance(document.content, CanonicalScoreContent)
    parts = document.content.score.parts
    selected = tuple(part for part in parts if part.id in analysis.scope.part_ids)
    return len(parts), max(measure.ordinal for part in selected for measure in part.measures)
