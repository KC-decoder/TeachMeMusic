"""Production assembly boundaries for deterministic curriculum generation."""

from __future__ import annotations

import re
from dataclasses import dataclass, replace
from fractions import Fraction

from teachmemusic.analysis import ScoreAnalysis, analyze_canonical_score
from teachmemusic.score import CanonicalMusicPackage

from .acquisition import generate_acquisition_graph
from .branches import generate_prerequisite_branches
from .curriculum_contracts import (
    AcquisitionGraphSlice,
    ArtifactResolution,
    CompatibleTempoEvidence,
    CurriculumPassagePresentation,
    CurriculumPolicyAction,
    ExerciseInstance,
    PassageRequirementSet,
    PrerequisiteBranchSet,
    SemanticReference,
    TempoReferenceAuthority,
)
from .curriculum_fingerprint import derived_id, semantic_fingerprint
from .curriculum_policy import CurriculumSupportDecision
from .curriculum_validation import (
    require_valid_acquisition_graph_slice,
    require_valid_curriculum_passage_presentation,
    require_valid_prerequisite_branch_set,
)
from .presentation import build_curriculum_passage_presentation
from .requirements import derive_passage_requirements

CURRICULUM_ANALYSIS_ASSEMBLY_VERSION = "0.1.0"
CURRICULUM_FUNDAMENTAL_ASSEMBLY_VERSION = "0.1.0"
CURRICULUM_PRACTICE_ASSEMBLY_VERSION = "0.1.0"
CURRICULUM_REMEDIATION_ASSEMBLY_VERSION = "0.1.0"
_SHA256 = re.compile(r"[0-9a-f]{64}")
_DIAGNOSTIC_TEMPLATE_ID = "TEMPLATE-DIAGNOSTIC-001"
_PREREQUISITE_TEMPLATE_ID = "TEMPLATE-PREREQUISITE-001"
_APPLICATION_TEMPLATE_ID = "TEMPLATE-PIECE-APPLICATION-001"


class CurriculumAnalysisAssemblyError(ValueError):
    """Raised when the upload-to-requirements identity chain is inconsistent."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(f"{code}: {message}")


@dataclass(frozen=True, slots=True)
class CurriculumSourceIdentity:
    """One exact source artifact retained by canonical package provenance."""

    source_id: str
    logical_name: str
    source_format: str
    sha256: str


@dataclass(frozen=True, slots=True)
class CurriculumAnalysisManifest:
    """Compact identity chain from uploaded source to derived requirements."""

    schema_version: str
    id: str
    semantic_fingerprint: str
    sources: tuple[CurriculumSourceIdentity, ...]
    package_id: str
    canonical_digest_sha256: str
    score_id: str
    part_ids: tuple[str, ...]
    start_measure_ordinal: int
    end_measure_ordinal: int
    analysis_id: str
    practice_scope_refs: tuple[SemanticReference, ...]
    requirement_refs: tuple[SemanticReference, ...]
    diagnostic_codes: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class CurriculumAnalysisAssembly:
    """Validated production objects needed by later full-route assembly."""

    manifest: CurriculumAnalysisManifest
    analysis: ScoreAnalysis
    requirements: PassageRequirementSet


@dataclass(frozen=True, slots=True)
class CurriculumFundamentalDiagnosticManifest:
    """Compact identity chain for generated fundamental and diagnostic routes."""

    schema_version: str
    id: str
    semantic_fingerprint: str
    analysis_assembly_ref: SemanticReference
    graph_identity: str
    branch_set_fingerprint: str
    resolution: ArtifactResolution
    primitive_refs: tuple[SemanticReference, ...]
    branch_requirement_refs: tuple[SemanticReference, ...]
    diagnostic_exercise_refs: tuple[SemanticReference, ...]
    prerequisite_exercise_refs: tuple[SemanticReference, ...]
    application_exercise_refs: tuple[SemanticReference, ...]
    diagnostic_codes: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class CurriculumFundamentalDiagnosticAssembly:
    """Validated Task 9N.2 artifacts consumed by later full-route assembly."""

    manifest: CurriculumFundamentalDiagnosticManifest
    branches: PrerequisiteBranchSet


@dataclass(frozen=True, slots=True)
class CurriculumPracticeAssemblyManifest:
    """Compact identity chain for layered acquisition and presentation."""

    schema_version: str
    id: str
    semantic_fingerprint: str
    fundamental_assembly_ref: SemanticReference
    acquisition_graph_ref: SemanticReference
    presentation_refs: tuple[SemanticReference, ...]
    stage_ids: tuple[str, ...]
    tempo_plan_refs: tuple[SemanticReference, ...]
    reference_tempo_bpm: Fraction
    reference_authority: TempoReferenceAuthority
    tempo_evidence_refs: tuple[str, ...]
    diagnostic_codes: tuple[str, ...]
    resolution: ArtifactResolution


@dataclass(frozen=True, slots=True)
class CurriculumPracticeAssembly:
    """Validated Task 9N.3 layered practice artifacts."""

    manifest: CurriculumPracticeAssemblyManifest
    acquisition: AcquisitionGraphSlice
    presentations: tuple[CurriculumPassagePresentation, ...]


@dataclass(frozen=True, slots=True)
class CurriculumRemediationAssemblyManifest:
    """Non-human 9N.4 retry, remediation, fade, and progression evidence."""

    schema_version: str
    id: str
    semantic_fingerprint: str
    practice_assembly_ref: SemanticReference
    decision_refs: tuple[SemanticReference, ...]
    action_sequence: tuple[CurriculumPolicyAction, ...]
    support_condition_path: tuple[str, ...]
    remediation_target_node_ids: tuple[str, ...]
    progression_target_node_id: str
    verification_authority: str
    human_evidence_eligible: bool
    resolution: ArtifactResolution


@dataclass(frozen=True, slots=True)
class CurriculumRemediationAssembly:
    """Validated Task 9N.4 synthetic policy rehearsal."""

    manifest: CurriculumRemediationAssemblyManifest
    decisions: tuple[CurriculumSupportDecision, ...]


def assemble_curriculum_analysis(
    package: CanonicalMusicPackage,
    *,
    score_id: str,
    part_ids: tuple[str, ...] = (),
    start_measure_ordinal: int = 1,
    end_measure_ordinal: int | None = None,
) -> CurriculumAnalysisAssembly:
    """Join canonical ingestion, analysis, and requirements without copying truth."""

    analysis = analyze_canonical_score(
        package,
        score_id=score_id,
        part_ids=part_ids,
        start_measure_ordinal=start_measure_ordinal,
        end_measure_ordinal=end_measure_ordinal,
    )
    requirements = derive_passage_requirements(package, analysis)
    sources = _source_identities(package)
    provisional = CurriculumAnalysisManifest(
        schema_version=CURRICULUM_ANALYSIS_ASSEMBLY_VERSION,
        id="curriculum-analysis-assembly:pending",
        semantic_fingerprint="",
        sources=sources,
        package_id=package.id.value,
        canonical_digest_sha256=analysis.canonical_digest_sha256,
        score_id=analysis.scope.score_id,
        part_ids=analysis.scope.part_ids,
        start_measure_ordinal=analysis.scope.start_measure_ordinal,
        end_measure_ordinal=analysis.scope.end_measure_ordinal,
        analysis_id=analysis.id,
        practice_scope_refs=tuple(
            SemanticReference("practice-scope-assignment", item.id, item.semantic_fingerprint)
            for item in requirements.scopes
        ),
        requirement_refs=tuple(
            SemanticReference("passage-skill-requirement", item.id, item.semantic_fingerprint)
            for item in requirements.requirements
        ),
        diagnostic_codes=tuple(item.code for item in requirements.diagnostics),
    )
    manifest = replace(
        provisional,
        id=derived_id("curriculum-analysis-assembly", provisional),
        semantic_fingerprint=semantic_fingerprint(provisional),
    )
    require_valid_curriculum_analysis_manifest(manifest, package, analysis, requirements)
    return CurriculumAnalysisAssembly(manifest, analysis, requirements)


def require_valid_curriculum_analysis_manifest(
    manifest: CurriculumAnalysisManifest,
    package: CanonicalMusicPackage,
    analysis: ScoreAnalysis,
    requirements: PassageRequirementSet,
) -> None:
    """Require exact agreement with every upstream production identity."""

    if manifest.schema_version != CURRICULUM_ANALYSIS_ASSEMBLY_VERSION:
        raise CurriculumAnalysisAssemblyError(
            "TMM-ASSEMBLY-VERSION", "unsupported curriculum-analysis assembly version"
        )
    expected_sources = _source_identities(package)
    if manifest.sources != expected_sources or not manifest.sources:
        raise CurriculumAnalysisAssemblyError(
            "TMM-ASSEMBLY-SOURCE", "source provenance does not match the canonical package"
        )
    if any(_SHA256.fullmatch(item.sha256) is None for item in manifest.sources):
        raise CurriculumAnalysisAssemblyError(
            "TMM-ASSEMBLY-SOURCE", "every source requires an exact SHA-256 identity"
        )
    if (
        manifest.package_id != package.id.value
        or manifest.canonical_digest_sha256 != analysis.canonical_digest_sha256
        or manifest.score_id != analysis.scope.score_id
        or manifest.part_ids != analysis.scope.part_ids
        or manifest.start_measure_ordinal != analysis.scope.start_measure_ordinal
        or manifest.end_measure_ordinal != analysis.scope.end_measure_ordinal
        or manifest.analysis_id != analysis.id
        or requirements.analysis_id != analysis.id
    ):
        raise CurriculumAnalysisAssemblyError(
            "TMM-ASSEMBLY-IDENTITY", "package, score, passage, or analysis identity drifted"
        )
    expected_scopes = tuple(
        SemanticReference("practice-scope-assignment", item.id, item.semantic_fingerprint)
        for item in requirements.scopes
    )
    expected_requirements = tuple(
        SemanticReference("passage-skill-requirement", item.id, item.semantic_fingerprint)
        for item in requirements.requirements
    )
    if (
        manifest.practice_scope_refs != expected_scopes
        or manifest.requirement_refs != expected_requirements
        or manifest.diagnostic_codes != tuple(item.code for item in requirements.diagnostics)
    ):
        raise CurriculumAnalysisAssemblyError(
            "TMM-ASSEMBLY-REQUIREMENTS", "scope or requirement identity drifted"
        )
    if manifest.semantic_fingerprint != semantic_fingerprint(manifest):
        raise CurriculumAnalysisAssemblyError(
            "TMM-ASSEMBLY-FINGERPRINT", "assembly fingerprint has drifted"
        )
    if manifest.id != f"curriculum-analysis-assembly:{manifest.semantic_fingerprint}":
        raise CurriculumAnalysisAssemblyError(
            "TMM-ASSEMBLY-FINGERPRINT", "assembly identifier has drifted"
        )


def assemble_curriculum_fundamentals(
    package: CanonicalMusicPackage,
    analysis_assembly: CurriculumAnalysisAssembly,
) -> CurriculumFundamentalDiagnosticAssembly:
    """Generate exact diagnostic and prerequisite routes from a 9N.1 assembly."""

    require_valid_curriculum_analysis_manifest(
        analysis_assembly.manifest,
        package,
        analysis_assembly.analysis,
        analysis_assembly.requirements,
    )
    branches = generate_prerequisite_branches(analysis_assembly.requirements)
    references = _fundamental_manifest_references(
        analysis_assembly.requirements,
        branches,
    )
    provisional = CurriculumFundamentalDiagnosticManifest(
        schema_version=CURRICULUM_FUNDAMENTAL_ASSEMBLY_VERSION,
        id="curriculum-fundamental-assembly:pending",
        semantic_fingerprint="",
        analysis_assembly_ref=SemanticReference(
            "curriculum-analysis-assembly",
            analysis_assembly.manifest.id,
            analysis_assembly.manifest.semantic_fingerprint,
        ),
        graph_identity=branches.graph_identity,
        branch_set_fingerprint=semantic_fingerprint(branches),
        resolution=branches.resolution,
        primitive_refs=references[0],
        branch_requirement_refs=references[1],
        diagnostic_exercise_refs=references[2],
        prerequisite_exercise_refs=references[3],
        application_exercise_refs=references[4],
        diagnostic_codes=tuple(item.code for item in branches.diagnostics),
    )
    manifest = replace(
        provisional,
        id=derived_id("curriculum-fundamental-assembly", provisional),
        semantic_fingerprint=semantic_fingerprint(provisional),
    )
    require_valid_curriculum_fundamental_manifest(
        manifest,
        package,
        analysis_assembly,
        branches,
    )
    return CurriculumFundamentalDiagnosticAssembly(manifest, branches)


def require_valid_curriculum_fundamental_manifest(
    manifest: CurriculumFundamentalDiagnosticManifest,
    package: CanonicalMusicPackage,
    analysis_assembly: CurriculumAnalysisAssembly,
    branches: PrerequisiteBranchSet,
) -> None:
    """Require exact agreement between 9N.1 and every generated 9N.2 route."""

    require_valid_curriculum_analysis_manifest(
        analysis_assembly.manifest,
        package,
        analysis_assembly.analysis,
        analysis_assembly.requirements,
    )
    require_valid_prerequisite_branch_set(branches, analysis_assembly.requirements)
    if manifest.schema_version != CURRICULUM_FUNDAMENTAL_ASSEMBLY_VERSION:
        raise CurriculumAnalysisAssemblyError(
            "TMM-ASSEMBLY-VERSION", "unsupported curriculum-fundamental assembly version"
        )
    expected_analysis_ref = SemanticReference(
        "curriculum-analysis-assembly",
        analysis_assembly.manifest.id,
        analysis_assembly.manifest.semantic_fingerprint,
    )
    if manifest.analysis_assembly_ref != expected_analysis_ref:
        raise CurriculumAnalysisAssemblyError(
            "TMM-ASSEMBLY-IDENTITY", "analysis-assembly identity drifted"
        )
    if (
        manifest.graph_identity != branches.graph_identity
        or manifest.branch_set_fingerprint != semantic_fingerprint(branches)
        or manifest.resolution != branches.resolution
    ):
        raise CurriculumAnalysisAssemblyError(
            "TMM-ASSEMBLY-BRANCH", "generated branch-set identity drifted"
        )
    expected = _fundamental_manifest_references(
        analysis_assembly.requirements,
        branches,
    )
    if (
        manifest.primitive_refs != expected[0]
        or manifest.branch_requirement_refs != expected[1]
        or manifest.diagnostic_exercise_refs != expected[2]
        or manifest.prerequisite_exercise_refs != expected[3]
        or manifest.application_exercise_refs != expected[4]
        or manifest.diagnostic_codes != tuple(item.code for item in branches.diagnostics)
    ):
        raise CurriculumAnalysisAssemblyError(
            "TMM-ASSEMBLY-BRANCH", "fundamental or diagnostic references drifted"
        )
    if manifest.semantic_fingerprint != semantic_fingerprint(manifest):
        raise CurriculumAnalysisAssemblyError(
            "TMM-ASSEMBLY-FINGERPRINT", "fundamental assembly fingerprint has drifted"
        )
    if manifest.id != f"curriculum-fundamental-assembly:{manifest.semantic_fingerprint}":
        raise CurriculumAnalysisAssemblyError(
            "TMM-ASSEMBLY-FINGERPRINT", "fundamental assembly identifier has drifted"
        )


def assemble_curriculum_practice(
    package: CanonicalMusicPackage,
    analysis_assembly: CurriculumAnalysisAssembly,
    fundamental_assembly: CurriculumFundamentalDiagnosticAssembly,
    *,
    reference_tempo_bpm: Fraction,
    reference_authority: TempoReferenceAuthority,
    tempo_evidence: tuple[CompatibleTempoEvidence, ...] = (),
) -> CurriculumPracticeAssembly:
    """Compose exact layered practice from validated analysis and branches."""

    require_valid_curriculum_fundamental_manifest(
        fundamental_assembly.manifest,
        package,
        analysis_assembly,
        fundamental_assembly.branches,
    )
    acquisition = generate_acquisition_graph(
        analysis_assembly.requirements,
        fundamental_assembly.branches,
        reference_tempo_bpm=reference_tempo_bpm,
        reference_authority=reference_authority,
        tempo_evidence=tempo_evidence,
    )
    presentations = tuple(
        build_curriculum_passage_presentation(
            package,
            analysis_assembly.requirements,
            scope.id,
        )
        for scope in analysis_assembly.requirements.scopes
    )
    provisional = CurriculumPracticeAssemblyManifest(
        schema_version=CURRICULUM_PRACTICE_ASSEMBLY_VERSION,
        id="curriculum-practice-assembly:pending",
        semantic_fingerprint="",
        fundamental_assembly_ref=SemanticReference(
            "curriculum-fundamental-assembly",
            fundamental_assembly.manifest.id,
            fundamental_assembly.manifest.semantic_fingerprint,
        ),
        acquisition_graph_ref=SemanticReference(
            "acquisition-graph-slice",
            acquisition.id,
            acquisition.semantic_fingerprint,
        ),
        presentation_refs=tuple(
            SemanticReference(
                "curriculum-passage-presentation",
                item.id,
                item.semantic_fingerprint,
            )
            for item in presentations
        ),
        stage_ids=tuple(item.id for item in acquisition.stages),
        tempo_plan_refs=tuple(
            SemanticReference(
                "controlled-tempo-plan",
                item.id,
                item.semantic_fingerprint,
            )
            for item in acquisition.tempo_plans
        ),
        reference_tempo_bpm=reference_tempo_bpm,
        reference_authority=reference_authority,
        tempo_evidence_refs=tuple(
            sorted({ref for item in acquisition.tempo_plans for ref in item.evidence_refs})
        ),
        diagnostic_codes=tuple(item.code for item in acquisition.diagnostics),
        resolution=acquisition.resolution,
    )
    manifest = replace(
        provisional,
        id=derived_id("curriculum-practice-assembly", provisional),
        semantic_fingerprint=semantic_fingerprint(provisional),
    )
    require_valid_curriculum_practice_manifest(
        manifest,
        package,
        analysis_assembly,
        fundamental_assembly,
        acquisition,
        presentations,
    )
    return CurriculumPracticeAssembly(manifest, acquisition, presentations)


def require_valid_curriculum_practice_manifest(
    manifest: CurriculumPracticeAssemblyManifest,
    package: CanonicalMusicPackage,
    analysis_assembly: CurriculumAnalysisAssembly,
    fundamental_assembly: CurriculumFundamentalDiagnosticAssembly,
    acquisition: AcquisitionGraphSlice,
    presentations: tuple[CurriculumPassagePresentation, ...],
) -> None:
    """Require exact 9N.2-to-layered-practice identity continuity."""

    require_valid_curriculum_fundamental_manifest(
        fundamental_assembly.manifest,
        package,
        analysis_assembly,
        fundamental_assembly.branches,
    )
    require_valid_acquisition_graph_slice(acquisition)
    if manifest.schema_version != CURRICULUM_PRACTICE_ASSEMBLY_VERSION:
        raise CurriculumAnalysisAssemblyError(
            "TMM-ASSEMBLY-VERSION", "unsupported curriculum-practice assembly version"
        )
    expected_fundamental_ref = SemanticReference(
        "curriculum-fundamental-assembly",
        fundamental_assembly.manifest.id,
        fundamental_assembly.manifest.semantic_fingerprint,
    )
    if manifest.fundamental_assembly_ref != expected_fundamental_ref:
        raise CurriculumAnalysisAssemblyError(
            "TMM-ASSEMBLY-IDENTITY", "fundamental-assembly identity drifted"
        )
    if (
        acquisition.analysis_id != analysis_assembly.requirements.analysis_id
        or acquisition.branches != fundamental_assembly.branches.branches
    ):
        raise CurriculumAnalysisAssemblyError(
            "TMM-ASSEMBLY-PRACTICE", "acquisition graph detached from upstream branches"
        )
    if len(presentations) != len(analysis_assembly.requirements.scopes):
        raise CurriculumAnalysisAssemblyError(
            "TMM-ASSEMBLY-PRACTICE", "practice presentation coverage is incomplete"
        )
    for presentation, scope in zip(
        presentations,
        analysis_assembly.requirements.scopes,
        strict=True,
    ):
        require_valid_curriculum_passage_presentation(presentation, scope)
    expected_graph_ref = SemanticReference(
        "acquisition-graph-slice",
        acquisition.id,
        acquisition.semantic_fingerprint,
    )
    expected_presentation_refs = tuple(
        SemanticReference(
            "curriculum-passage-presentation",
            item.id,
            item.semantic_fingerprint,
        )
        for item in presentations
    )
    expected_tempo_refs = tuple(
        SemanticReference(
            "controlled-tempo-plan",
            item.id,
            item.semantic_fingerprint,
        )
        for item in acquisition.tempo_plans
    )
    reference_tempos = {item.reference_tempo_bpm for item in acquisition.tempo_plans}
    reference_authorities = {item.reference_authority for item in acquisition.tempo_plans}
    expected_evidence_refs = tuple(
        sorted({ref for item in acquisition.tempo_plans for ref in item.evidence_refs})
    )
    if (
        manifest.acquisition_graph_ref != expected_graph_ref
        or manifest.presentation_refs != expected_presentation_refs
        or manifest.stage_ids != tuple(item.id for item in acquisition.stages)
        or manifest.tempo_plan_refs != expected_tempo_refs
        or reference_tempos != {manifest.reference_tempo_bpm}
        or reference_authorities != {manifest.reference_authority}
        or manifest.tempo_evidence_refs != expected_evidence_refs
        or manifest.diagnostic_codes != tuple(item.code for item in acquisition.diagnostics)
        or manifest.resolution != acquisition.resolution
    ):
        raise CurriculumAnalysisAssemblyError(
            "TMM-ASSEMBLY-PRACTICE", "layered practice identities drifted"
        )
    if manifest.semantic_fingerprint != semantic_fingerprint(manifest):
        raise CurriculumAnalysisAssemblyError(
            "TMM-ASSEMBLY-FINGERPRINT", "practice assembly fingerprint has drifted"
        )
    if manifest.id != f"curriculum-practice-assembly:{manifest.semantic_fingerprint}":
        raise CurriculumAnalysisAssemblyError(
            "TMM-ASSEMBLY-FINGERPRINT", "practice assembly identifier has drifted"
        )


def assemble_curriculum_remediation_rehearsal(
    package: CanonicalMusicPackage,
    analysis_assembly: CurriculumAnalysisAssembly,
    fundamental_assembly: CurriculumFundamentalDiagnosticAssembly,
    practice_assembly: CurriculumPracticeAssembly,
    decisions: tuple[CurriculumSupportDecision, ...],
) -> CurriculumRemediationAssembly:
    """Freeze one bounded non-human remediation and support-fading rehearsal."""

    require_valid_curriculum_practice_manifest(
        practice_assembly.manifest,
        package,
        analysis_assembly,
        fundamental_assembly,
        practice_assembly.acquisition,
        practice_assembly.presentations,
    )
    if not decisions:
        raise CurriculumAnalysisAssemblyError(
            "TMM-ASSEMBLY-REMEDIATION", "remediation rehearsal requires policy decisions"
        )
    support_path = tuple(
        item for decision in decisions for item in (decision.support_condition_before,)
    ) + (decisions[-1].support_condition_after or decisions[-1].support_condition_before,)
    remediation_targets = tuple(
        item.target_node_id for item in decisions if item.action is CurriculumPolicyAction.REMEDIATE
    )
    provisional = CurriculumRemediationAssemblyManifest(
        schema_version=CURRICULUM_REMEDIATION_ASSEMBLY_VERSION,
        id="curriculum-remediation-assembly:pending",
        semantic_fingerprint="",
        practice_assembly_ref=SemanticReference(
            "curriculum-practice-assembly",
            practice_assembly.manifest.id,
            practice_assembly.manifest.semantic_fingerprint,
        ),
        decision_refs=tuple(
            SemanticReference(
                "curriculum-support-decision",
                item.id,
                item.semantic_fingerprint,
            )
            for item in decisions
        ),
        action_sequence=tuple(item.action for item in decisions),
        support_condition_path=support_path,
        remediation_target_node_ids=remediation_targets,
        progression_target_node_id=decisions[-1].target_node_id,
        verification_authority="synthetic-simulation",
        human_evidence_eligible=False,
        resolution=ArtifactResolution.RESOLVED,
    )
    manifest = replace(
        provisional,
        id=derived_id("curriculum-remediation-assembly", provisional),
        semantic_fingerprint=semantic_fingerprint(provisional),
    )
    require_valid_curriculum_remediation_manifest(
        manifest,
        package,
        analysis_assembly,
        fundamental_assembly,
        practice_assembly,
        decisions,
    )
    return CurriculumRemediationAssembly(manifest, decisions)


def require_valid_curriculum_remediation_manifest(
    manifest: CurriculumRemediationAssemblyManifest,
    package: CanonicalMusicPackage,
    analysis_assembly: CurriculumAnalysisAssembly,
    fundamental_assembly: CurriculumFundamentalDiagnosticAssembly,
    practice_assembly: CurriculumPracticeAssembly,
    decisions: tuple[CurriculumSupportDecision, ...],
) -> None:
    """Require exact 9N.3-to-9N.4 identity and bounded policy behavior."""

    require_valid_curriculum_practice_manifest(
        practice_assembly.manifest,
        package,
        analysis_assembly,
        fundamental_assembly,
        practice_assembly.acquisition,
        practice_assembly.presentations,
    )
    expected_practice_ref = SemanticReference(
        "curriculum-practice-assembly",
        practice_assembly.manifest.id,
        practice_assembly.manifest.semantic_fingerprint,
    )
    expected_decision_refs = tuple(
        SemanticReference(
            "curriculum-support-decision",
            item.id,
            item.semantic_fingerprint,
        )
        for item in decisions
    )
    graph_ref = SemanticReference(
        "acquisition-graph-slice",
        practice_assembly.acquisition.id,
        practice_assembly.acquisition.semantic_fingerprint,
    )
    graph_node_ids = {item.id for item in practice_assembly.acquisition.nodes}
    configuration = practice_assembly.acquisition.tempo_configuration
    if (
        manifest.schema_version != CURRICULUM_REMEDIATION_ASSEMBLY_VERSION
        or manifest.practice_assembly_ref != expected_practice_ref
        or manifest.decision_refs != expected_decision_refs
        or not decisions
        or tuple(item.decision_sequence for item in decisions) != tuple(range(len(decisions)))
        or any(item.graph_ref != graph_ref for item in decisions)
        or len({item.node_id for item in decisions}) != 1
        or any(
            item.semantic_fingerprint != semantic_fingerprint(item)
            or item.id != f"curriculum-support-decision:{item.semantic_fingerprint}"
            or item.node_id not in graph_node_ids
            or item.target_node_id not in graph_node_ids
            or item.retry_limit != configuration.acquisition_retry_budget
            or item.remediation_limit != configuration.remediation_budget
            or item.retry_count > item.retry_limit
            or item.remediation_count > item.remediation_limit
            for item in decisions
        )
    ):
        raise CurriculumAnalysisAssemblyError(
            "TMM-ASSEMBLY-REMEDIATION", "remediation decision chain is incomplete or detached"
        )
    actions = tuple(item.action for item in decisions)
    required_actions = (
        CurriculumPolicyAction.RETRY,
        CurriculumPolicyAction.REMEDIATE,
        CurriculumPolicyAction.FADE_SUPPORT,
        CurriculumPolicyAction.PROGRESS,
    )
    try:
        positions = tuple(actions.index(item) for item in required_actions)
    except ValueError as error:
        raise CurriculumAnalysisAssemblyError(
            "TMM-ASSEMBLY-REMEDIATION",
            "rehearsal must prove retry, remediation, support fading, and progression",
        ) from error
    remediation_targets = tuple(
        item.target_node_id for item in decisions if item.action is CurriculumPolicyAction.REMEDIATE
    )
    support_path = tuple(item.support_condition_before for item in decisions) + (
        decisions[-1].support_condition_after or decisions[-1].support_condition_before,
    )
    if (
        positions != tuple(sorted(positions))
        or actions[-1] is not CurriculumPolicyAction.PROGRESS
        or not remediation_targets
        or manifest.action_sequence != actions
        or manifest.support_condition_path != support_path
        or manifest.remediation_target_node_ids != remediation_targets
        or manifest.progression_target_node_id != decisions[-1].target_node_id
        or manifest.verification_authority != "synthetic-simulation"
        or manifest.human_evidence_eligible
        or manifest.resolution is not ArtifactResolution.RESOLVED
    ):
        raise CurriculumAnalysisAssemblyError(
            "TMM-ASSEMBLY-REMEDIATION", "rehearsal behavior or evidence authority drifted"
        )
    expected_fingerprint = semantic_fingerprint(manifest)
    if (
        manifest.semantic_fingerprint != expected_fingerprint
        or manifest.id != f"curriculum-remediation-assembly:{expected_fingerprint}"
    ):
        raise CurriculumAnalysisAssemblyError(
            "TMM-ASSEMBLY-FINGERPRINT", "remediation assembly identity has drifted"
        )


def _fundamental_manifest_references(
    requirements: PassageRequirementSet,
    branches: PrerequisiteBranchSet,
) -> tuple[
    tuple[SemanticReference, ...],
    tuple[SemanticReference, ...],
    tuple[SemanticReference, ...],
    tuple[SemanticReference, ...],
    tuple[SemanticReference, ...],
]:
    primitive_by_id = {item.id: item for item in requirements.primitives}
    primitive_refs = tuple(
        SemanticReference(
            "learning-primitive",
            primitive_by_id[item].id,
            primitive_by_id[item].semantic_fingerprint,
        )
        for item in sorted(
            {requirement.primitive_ref.id for requirement in requirements.requirements}
        )
    )
    exercise_refs = {
        template_id: tuple(
            _exercise_reference(item)
            for item in branches.exercises
            if item.template_ref.id == template_id
        )
        for template_id in (
            _DIAGNOSTIC_TEMPLATE_ID,
            _PREREQUISITE_TEMPLATE_ID,
            _APPLICATION_TEMPLATE_ID,
        )
    }
    return (
        primitive_refs,
        tuple(item.requirement_ref for item in branches.branches),
        exercise_refs[_DIAGNOSTIC_TEMPLATE_ID],
        exercise_refs[_PREREQUISITE_TEMPLATE_ID],
        exercise_refs[_APPLICATION_TEMPLATE_ID],
    )


def _exercise_reference(exercise: ExerciseInstance) -> SemanticReference:
    return SemanticReference(
        "exercise-instance",
        exercise.id,
        exercise.semantic_fingerprint,
    )


def _source_identities(
    package: CanonicalMusicPackage,
) -> tuple[CurriculumSourceIdentity, ...]:
    result: list[CurriculumSourceIdentity] = []
    for item in package.provenance.sources:
        logical_name = item.logical_name.value
        source_format = item.source_format.value
        digest = item.sha256.value
        if (
            not isinstance(logical_name, str)
            or source_format is None
            or not isinstance(digest, str)
        ):
            raise CurriculumAnalysisAssemblyError(
                "TMM-ASSEMBLY-SOURCE",
                "curriculum assembly requires explicit source name, format, and digest",
            )
        result.append(
            CurriculumSourceIdentity(
                source_id=item.id.value,
                logical_name=logical_name,
                source_format=source_format.value,
                sha256=digest,
            )
        )
    return tuple(result)
