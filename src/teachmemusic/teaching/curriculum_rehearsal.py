"""Export, graph, reconciliation, and replay for bounded curriculum rehearsals."""

from __future__ import annotations

from dataclasses import dataclass, replace

from teachmemusic._contract_codec import (
    ContractCodecError,
    contract_from_json,
    contract_to_json,
)

from .contracts import SupportState
from .curriculum_assembly import CurriculumRemediationAssembly
from .curriculum_contracts import (
    AcquisitionGraphSlice,
    ArtifactResolution,
    CurriculumMasteryProjection,
    CurriculumMasteryStatus,
    CurriculumPolicyAction,
    CurriculumUnlockDecision,
    SemanticReference,
)
from .curriculum_fingerprint import derived_id, semantic_fingerprint
from .curriculum_policy import (
    CurriculumPolicyError,
    CurriculumSupportDecision,
    decide_curriculum_support,
    require_valid_curriculum_support_decision,
)
from .curriculum_validation import (
    CurriculumValidationError,
    require_valid_acquisition_graph_slice,
    require_valid_curriculum_mastery_projection,
    require_valid_curriculum_unlock_decision,
)

CURRICULUM_REHEARSAL_EXPORT_VERSION = "0.1.0"
CURRICULUM_REHEARSAL_GRAPH_VERSION = "0.1.0"
CURRICULUM_REHEARSAL_REPLAY_VERSION = "0.1.0"


class CurriculumRehearsalError(ValueError):
    """Raised when a rehearsal export, projection, or replay is inconsistent."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(f"{code}: {message}")


@dataclass(frozen=True, slots=True)
class NamedCurriculumSupportState:
    """One named support condition retained for deterministic policy replay."""

    condition: str
    support_state: SupportState


@dataclass(frozen=True, slots=True)
class CurriculumRehearsalDecisionInput:
    """The exact factual projections consumed by one recorded decision."""

    decision_sequence: int
    mastery_projection: CurriculumMasteryProjection
    unlock_decision: CurriculumUnlockDecision


@dataclass(frozen=True, slots=True)
class CurriculumRehearsalExport:
    """Self-contained non-human decision evidence with graph content by reference."""

    schema_version: str
    id: str
    semantic_fingerprint: str
    remediation_assembly_ref: SemanticReference
    graph_ref: SemanticReference
    support_states: tuple[NamedCurriculumSupportState, ...]
    decision_inputs: tuple[CurriculumRehearsalDecisionInput, ...]
    decisions: tuple[CurriculumSupportDecision, ...]
    verification_authority: str
    human_evidence_eligible: bool
    resolution: ArtifactResolution


@dataclass(frozen=True, slots=True)
class CurriculumRehearsalGraphPoint:
    """One graphable, source-linked policy decision."""

    decision_sequence: int
    decision_ref: SemanticReference
    current_node_id: str
    target_node_id: str
    action: CurriculumPolicyAction
    mastery_status: CurriculumMasteryStatus
    support_condition_before: str
    support_condition_after: str | None
    retry_count: int
    remediation_count: int
    reason_code: str


@dataclass(frozen=True, slots=True)
class CurriculumRehearsalGraph:
    """Non-authoritative graph projection over one exact rehearsal export."""

    schema_version: str
    id: str
    semantic_fingerprint: str
    export_ref: SemanticReference
    points: tuple[CurriculumRehearsalGraphPoint, ...]
    terminal_target_node_id: str
    verification_authority: str
    human_evidence_eligible: bool


@dataclass(frozen=True, slots=True)
class CurriculumRehearsalReplayReceipt:
    """Proof that production policy reconstruction matched every decision."""

    schema_version: str
    id: str
    semantic_fingerprint: str
    export_ref: SemanticReference
    decision_refs: tuple[SemanticReference, ...]
    action_sequence: tuple[CurriculumPolicyAction, ...]
    exact_match_count: int
    verification_authority: str
    human_evidence_eligible: bool


@dataclass(frozen=True, slots=True)
class CurriculumRehearsalReconciliationReceipt:
    """Proof that export, graph projection, source assembly, and replay agree."""

    schema_version: str
    id: str
    semantic_fingerprint: str
    remediation_assembly_ref: SemanticReference
    export_ref: SemanticReference
    graph_ref: SemanticReference
    replay_ref: SemanticReference
    decision_count: int
    verification_authority: str
    human_evidence_eligible: bool


def build_curriculum_rehearsal_export(
    remediation_assembly: CurriculumRemediationAssembly,
    graph: AcquisitionGraphSlice,
    support_states: tuple[tuple[str, SupportState], ...],
    mastery_projections: tuple[CurriculumMasteryProjection, ...],
    unlock_decisions: tuple[CurriculumUnlockDecision, ...],
) -> CurriculumRehearsalExport:
    """Export exact replay inputs without score bytes, MIDI events, or learner identity."""

    manifest = remediation_assembly.manifest
    decisions = remediation_assembly.decisions
    if len(decisions) != len(mastery_projections) or len(decisions) != len(unlock_decisions):
        raise CurriculumRehearsalError(
            "TMM-REHEARSAL-COVERAGE",
            "every recorded decision requires one mastery and unlock input",
        )
    provisional = CurriculumRehearsalExport(
        schema_version=CURRICULUM_REHEARSAL_EXPORT_VERSION,
        id="curriculum-rehearsal-export:pending",
        semantic_fingerprint="",
        remediation_assembly_ref=_ref("curriculum-remediation-assembly", manifest),
        graph_ref=_graph_ref(graph),
        support_states=tuple(
            NamedCurriculumSupportState(condition, support) for condition, support in support_states
        ),
        decision_inputs=tuple(
            CurriculumRehearsalDecisionInput(sequence, mastery, unlock)
            for sequence, (mastery, unlock) in enumerate(
                zip(mastery_projections, unlock_decisions, strict=True)
            )
        ),
        decisions=decisions,
        verification_authority="synthetic-simulation",
        human_evidence_eligible=False,
        resolution=ArtifactResolution.RESOLVED,
    )
    exported = replace(
        provisional,
        id=derived_id("curriculum-rehearsal-export", provisional),
        semantic_fingerprint=semantic_fingerprint(provisional),
    )
    require_valid_curriculum_rehearsal_export(exported)
    _require_export_sources(exported, remediation_assembly, graph)
    return exported


def require_valid_curriculum_rehearsal_export(value: CurriculumRehearsalExport) -> None:
    """Validate the export's self-contained identity and evidence boundary."""

    if (
        value.schema_version != CURRICULUM_REHEARSAL_EXPORT_VERSION
        or value.verification_authority != "synthetic-simulation"
        or value.human_evidence_eligible
        or value.resolution is not ArtifactResolution.RESOLVED
        or value.remediation_assembly_ref.artifact_type != "curriculum-remediation-assembly"
        or value.graph_ref.artifact_type != "acquisition-graph-slice"
        or not value.support_states
        or not value.decisions
        or len(value.decision_inputs) != len(value.decisions)
    ):
        raise CurriculumRehearsalError(
            "TMM-REHEARSAL-EXPORT",
            "rehearsal export version, authority, references, or coverage is invalid",
        )
    conditions = tuple(item.condition for item in value.support_states)
    if any(not item for item in conditions) or len(conditions) != len(set(conditions)):
        raise CurriculumRehearsalError(
            "TMM-REHEARSAL-SUPPORT",
            "support conditions must be non-empty and unique",
        )
    sequences = tuple(item.decision_sequence for item in value.decision_inputs)
    decision_sequences = tuple(item.decision_sequence for item in value.decisions)
    if sequences != tuple(range(len(value.decisions))) or sequences != decision_sequences:
        raise CurriculumRehearsalError(
            "TMM-REHEARSAL-SEQUENCE",
            "decision inputs and outputs must preserve one contiguous sequence",
        )
    for replay_input, decision in zip(value.decision_inputs, value.decisions, strict=True):
        try:
            require_valid_curriculum_mastery_projection(replay_input.mastery_projection)
        except CurriculumValidationError as error:
            raise CurriculumRehearsalError(
                "TMM-REHEARSAL-INPUT",
                "a mastery projection is invalid",
            ) from error
        if (
            decision.graph_ref != value.graph_ref
            or decision.projection_ref
            != _ref(
                "curriculum-mastery-projection",
                replay_input.mastery_projection,
            )
            or decision.unlock_ref
            != _ref("curriculum-unlock-decision", replay_input.unlock_decision)
            or decision.support_condition_before not in conditions
            or decision.semantic_fingerprint != semantic_fingerprint(decision)
            or decision.id != f"curriculum-support-decision:{decision.semantic_fingerprint}"
        ):
            raise CurriculumRehearsalError(
                "TMM-REHEARSAL-INPUT",
                "a decision is detached from its exact replay inputs",
            )
    _require_content_identity(value, "curriculum-rehearsal-export")


def curriculum_rehearsal_export_to_json(value: CurriculumRehearsalExport) -> str:
    """Serialize one validated rehearsal export deterministically."""

    require_valid_curriculum_rehearsal_export(value)
    try:
        return contract_to_json(value)
    except ContractCodecError as error:
        raise CurriculumRehearsalError("TMM-REHEARSAL-SERIALIZATION", str(error)) from error


def curriculum_rehearsal_export_from_json(payload: str) -> CurriculumRehearsalExport:
    """Decode one strict rehearsal export and reject unknown or changed content."""

    try:
        value = contract_from_json(payload, CurriculumRehearsalExport)
    except ContractCodecError as error:
        raise CurriculumRehearsalError("TMM-REHEARSAL-SERIALIZATION", str(error)) from error
    require_valid_curriculum_rehearsal_export(value)
    return value


def build_curriculum_rehearsal_graph(
    exported: CurriculumRehearsalExport,
) -> CurriculumRehearsalGraph:
    """Project the exact policy route into a compact graph-ready sequence."""

    require_valid_curriculum_rehearsal_export(exported)
    provisional = CurriculumRehearsalGraph(
        schema_version=CURRICULUM_REHEARSAL_GRAPH_VERSION,
        id="curriculum-rehearsal-graph:pending",
        semantic_fingerprint="",
        export_ref=_ref("curriculum-rehearsal-export", exported),
        points=tuple(
            CurriculumRehearsalGraphPoint(
                decision_sequence=item.decision_sequence,
                decision_ref=_ref("curriculum-support-decision", item),
                current_node_id=item.node_id,
                target_node_id=item.target_node_id,
                action=item.action,
                mastery_status=item.mastery_status,
                support_condition_before=item.support_condition_before,
                support_condition_after=item.support_condition_after,
                retry_count=item.retry_count,
                remediation_count=item.remediation_count,
                reason_code=item.reason_code,
            )
            for item in exported.decisions
        ),
        terminal_target_node_id=exported.decisions[-1].target_node_id,
        verification_authority=exported.verification_authority,
        human_evidence_eligible=False,
    )
    graph = replace(
        provisional,
        id=derived_id("curriculum-rehearsal-graph", provisional),
        semantic_fingerprint=semantic_fingerprint(provisional),
    )
    require_valid_curriculum_rehearsal_graph(graph, exported)
    return graph


def require_valid_curriculum_rehearsal_graph(
    graph: CurriculumRehearsalGraph,
    exported: CurriculumRehearsalExport,
) -> None:
    """Require every plotted point to be an exact projection of one decision."""

    require_valid_curriculum_rehearsal_export(exported)
    expected_points = tuple(
        CurriculumRehearsalGraphPoint(
            decision_sequence=item.decision_sequence,
            decision_ref=_ref("curriculum-support-decision", item),
            current_node_id=item.node_id,
            target_node_id=item.target_node_id,
            action=item.action,
            mastery_status=item.mastery_status,
            support_condition_before=item.support_condition_before,
            support_condition_after=item.support_condition_after,
            retry_count=item.retry_count,
            remediation_count=item.remediation_count,
            reason_code=item.reason_code,
        )
        for item in exported.decisions
    )
    if (
        graph.schema_version != CURRICULUM_REHEARSAL_GRAPH_VERSION
        or graph.export_ref != _ref("curriculum-rehearsal-export", exported)
        or graph.points != expected_points
        or graph.terminal_target_node_id != exported.decisions[-1].target_node_id
        or graph.verification_authority != exported.verification_authority
        or graph.human_evidence_eligible
    ):
        raise CurriculumRehearsalError(
            "TMM-REHEARSAL-GRAPH",
            "graph projection differs from the governed rehearsal export",
        )
    _require_content_identity(graph, "curriculum-rehearsal-graph")


def replay_curriculum_rehearsal(
    exported: CurriculumRehearsalExport,
    remediation_assembly: CurriculumRemediationAssembly,
    graph: AcquisitionGraphSlice,
) -> CurriculumRehearsalReplayReceipt:
    """Re-run the production support policy and require exact decision equality."""

    _require_export_sources(exported, remediation_assembly, graph)
    support_states = tuple((item.condition, item.support_state) for item in exported.support_states)
    history: tuple[CurriculumSupportDecision, ...] = ()
    replayed: list[CurriculumSupportDecision] = []
    for replay_input, recorded in zip(
        exported.decision_inputs,
        exported.decisions,
        strict=True,
    ):
        try:
            reconstructed = decide_curriculum_support(
                graph,
                recorded.node_id,
                recorded.support_condition_before,
                support_states,
                replay_input.mastery_projection,
                replay_input.unlock_decision,
                decision_sequence=replay_input.decision_sequence,
                history=history,
            )
        except (CurriculumPolicyError, CurriculumValidationError) as error:
            raise CurriculumRehearsalError(
                "TMM-REHEARSAL-REPLAY",
                "the production policy could not reconstruct a recorded decision",
            ) from error
        if reconstructed != recorded:
            raise CurriculumRehearsalError(
                "TMM-REHEARSAL-REPLAY",
                "a reconstructed decision differs from the recorded decision",
            )
        replayed.append(reconstructed)
        history = (*history, reconstructed)
    provisional = CurriculumRehearsalReplayReceipt(
        schema_version=CURRICULUM_REHEARSAL_REPLAY_VERSION,
        id="curriculum-rehearsal-replay:pending",
        semantic_fingerprint="",
        export_ref=_ref("curriculum-rehearsal-export", exported),
        decision_refs=tuple(_ref("curriculum-support-decision", item) for item in replayed),
        action_sequence=tuple(item.action for item in replayed),
        exact_match_count=len(replayed),
        verification_authority=exported.verification_authority,
        human_evidence_eligible=False,
    )
    receipt = replace(
        provisional,
        id=derived_id("curriculum-rehearsal-replay", provisional),
        semantic_fingerprint=semantic_fingerprint(provisional),
    )
    _require_content_identity(receipt, "curriculum-rehearsal-replay")
    return receipt


def reconcile_curriculum_rehearsal(
    exported: CurriculumRehearsalExport,
    projected_graph: CurriculumRehearsalGraph,
    remediation_assembly: CurriculumRemediationAssembly,
    graph: AcquisitionGraphSlice,
) -> CurriculumRehearsalReconciliationReceipt:
    """Reconcile the source assembly, export, graph projection, and exact replay."""

    _require_export_sources(exported, remediation_assembly, graph)
    expected_graph = build_curriculum_rehearsal_graph(exported)
    if projected_graph != expected_graph:
        raise CurriculumRehearsalError(
            "TMM-REHEARSAL-RECONCILIATION",
            "supplied graph projection differs from the exact export projection",
        )
    replay = replay_curriculum_rehearsal(exported, remediation_assembly, graph)
    manifest = remediation_assembly.manifest
    decisions = remediation_assembly.decisions
    provisional = CurriculumRehearsalReconciliationReceipt(
        schema_version=CURRICULUM_REHEARSAL_REPLAY_VERSION,
        id="curriculum-rehearsal-reconciliation:pending",
        semantic_fingerprint="",
        remediation_assembly_ref=_ref("curriculum-remediation-assembly", manifest),
        export_ref=_ref("curriculum-rehearsal-export", exported),
        graph_ref=_ref("curriculum-rehearsal-graph", projected_graph),
        replay_ref=_ref("curriculum-rehearsal-replay", replay),
        decision_count=len(decisions),
        verification_authority=exported.verification_authority,
        human_evidence_eligible=False,
    )
    receipt = replace(
        provisional,
        id=derived_id("curriculum-rehearsal-reconciliation", provisional),
        semantic_fingerprint=semantic_fingerprint(provisional),
    )
    _require_content_identity(receipt, "curriculum-rehearsal-reconciliation")
    return receipt


def _require_export_sources(
    exported: CurriculumRehearsalExport,
    remediation_assembly: CurriculumRemediationAssembly,
    graph: AcquisitionGraphSlice,
) -> None:
    require_valid_curriculum_rehearsal_export(exported)
    require_valid_acquisition_graph_slice(graph)
    manifest = remediation_assembly.manifest
    decisions = remediation_assembly.decisions
    if (
        not decisions
        or manifest.semantic_fingerprint != semantic_fingerprint(manifest)
        or manifest.id != f"curriculum-remediation-assembly:{manifest.semantic_fingerprint}"
        or exported.remediation_assembly_ref != _ref("curriculum-remediation-assembly", manifest)
        or exported.graph_ref != _graph_ref(graph)
        or exported.decisions != decisions
    ):
        raise CurriculumRehearsalError(
            "TMM-REHEARSAL-SOURCE",
            "export is detached from its remediation assembly or acquisition graph",
        )
    support_states = tuple((item.condition, item.support_state) for item in exported.support_states)
    node = next((item for item in graph.nodes if item.id == decisions[0].node_id), None)
    exercise = (
        next((item for item in graph.exercises if item.id == node.exercise_ref.id), None)
        if node is not None and node.exercise_ref is not None
        else None
    )
    if exercise is None or tuple(item[0] for item in support_states) != (
        exercise.support_envelope.permitted_conditions
    ):
        raise CurriculumRehearsalError(
            "TMM-REHEARSAL-SUPPORT",
            "export support states do not cover the recorded exercise envelope",
        )
    for replay_input, decision in zip(
        exported.decision_inputs,
        decisions,
        strict=True,
    ):
        try:
            require_valid_curriculum_unlock_decision(
                replay_input.unlock_decision,
                replay_input.mastery_projection,
                graph,
            )
            require_valid_curriculum_support_decision(
                decision,
                graph,
                replay_input.mastery_projection,
                replay_input.unlock_decision,
            )
        except (CurriculumPolicyError, CurriculumValidationError) as error:
            raise CurriculumRehearsalError(
                "TMM-REHEARSAL-INPUT",
                "a replay input or recorded decision is invalid for the source graph",
            ) from error


def _graph_ref(graph: AcquisitionGraphSlice) -> SemanticReference:
    return SemanticReference("acquisition-graph-slice", graph.id, graph.semantic_fingerprint)


def _ref(artifact_type: str, value: object) -> SemanticReference:
    identifier = getattr(value, "id", None)
    fingerprint = getattr(value, "semantic_fingerprint", None)
    if not isinstance(identifier, str) or not isinstance(fingerprint, str):
        raise CurriculumRehearsalError(
            "TMM-REHEARSAL-REFERENCE",
            f"{artifact_type} lacks a semantic identity",
        )
    return SemanticReference(artifact_type, identifier, fingerprint)


def _require_content_identity(value: object, kind: str) -> None:
    identifier = getattr(value, "id", None)
    fingerprint = getattr(value, "semantic_fingerprint", None)
    expected = semantic_fingerprint(value)
    if fingerprint != expected or identifier != f"{kind}:{expected}":
        raise CurriculumRehearsalError(
            "TMM-REHEARSAL-FINGERPRINT",
            f"{kind} content identity has drifted",
        )
