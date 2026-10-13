"""Deterministic DEV-009 Task 9B.3 acquisition and tempo composition."""

from __future__ import annotations

from dataclasses import replace
from fractions import Fraction

from .curriculum_contracts import (
    CURRICULUM_CONTRACT_VERSION,
    CURRICULUM_GRAPH_ID,
    EXERCISE_TEMPLATE_CATALOGUE_ID,
    TEMPO_CONFIGURATION_VERSION,
    TEMPO_POLICY_ID,
    AcquisitionGraphSlice,
    AcquisitionStage,
    AcquisitionStageKind,
    ActivityForm,
    ArtifactResolution,
    CanonicalExcerptMaterial,
    CompatibleTempoEvidence,
    ControlledTempoPlan,
    CurriculumEdgeKind,
    CurriculumGraphEdge,
    CurriculumGraphNode,
    CurriculumNodeKind,
    ExerciseActivity,
    ExerciseEvidenceExit,
    ExerciseInstance,
    ExerciseSupportEnvelope,
    NotationCondition,
    PassageRequirementSet,
    PassageSkillRequirement,
    PracticeScopeAssignment,
    PrerequisiteBranchSet,
    RuleReference,
    SemanticReference,
    TempoConfiguration,
    TempoPlanState,
    TempoPolicyAction,
    TempoProbeResult,
    TempoReferenceAuthority,
    TempoTransition,
)
from .curriculum_fingerprint import derived_id, semantic_fingerprint
from .curriculum_validation import (
    require_valid_acquisition_graph_slice,
    require_valid_prerequisite_branch_set,
    require_valid_requirement_set,
    require_valid_tempo_configuration,
)


def default_tempo_configuration() -> TempoConfiguration:
    """Return the frozen, versioned first numeric ADR-0012 baseline.

    These values are testable engineering hypotheses, not claims that the
    percentages are optimal for learning.
    """

    provisional = TempoConfiguration(
        schema_version=CURRICULUM_CONTRACT_VERSION,
        id="tempo-configuration:pending",
        semantic_fingerprint="",
        policy_identity=TEMPO_POLICY_ID,
        diagnostic_probe_percentages=(100, 85, 70, 55),
        tempo_increment_percentage=10,
        tempo_tolerance_percentage=5,
        diagnostic_attempt_budget=4,
        acquisition_retry_budget=3,
        tempo_probe_retry_budget=2,
        remediation_budget=2,
        phrase_group_size=2,
        stable_performance_passes=2,
    )
    fingerprint = semantic_fingerprint(provisional)
    result = replace(
        provisional,
        id=f"tempo-configuration:{fingerprint}",
        semantic_fingerprint=fingerprint,
    )
    require_valid_tempo_configuration(result)
    return result


def resolve_controlled_tempo(
    scope: PracticeScopeAssignment,
    evidence: tuple[CompatibleTempoEvidence, ...],
    *,
    reference_tempo_bpm: Fraction,
    reference_authority: TempoReferenceAuthority,
    configuration: TempoConfiguration | None = None,
) -> ControlledTempoPlan:
    """Select the fastest compatible condition or require a bounded probe."""

    configuration = configuration or default_tempo_configuration()
    require_valid_tempo_configuration(configuration)
    if reference_tempo_bpm <= 0:
        raise ValueError("reference_tempo_bpm must be positive")
    scope_ref = _scope_ref(scope)
    compatible = tuple(
        item
        for item in evidence
        if item.practice_scope_ref == scope_ref
        and item.required_non_tempo_gates_passed
        and item.pulse_gate_passed
        and 1 <= item.controlled_percentage <= item.supported_ceiling_percentage <= 100
        and item.evidence_refs
    )
    if compatible:
        selected = max(
            compatible,
            key=lambda item: (
                item.controlled_percentage,
                item.supported_ceiling_percentage,
                item.evidence_refs,
            ),
        )
        state = TempoPlanState.CONTROLLED
        current = selected.controlled_percentage
        ceiling = max(item.supported_ceiling_percentage for item in compatible)
        probes: tuple[int, ...] = ()
        evidence_refs = tuple(sorted({ref for item in compatible for ref in item.evidence_refs}))
        reason = "TMM-TEMPO-COMPATIBLE-EVIDENCE"
    else:
        state = TempoPlanState.DIAGNOSTIC_REQUIRED
        current = None
        ceiling = None
        probes = configuration.diagnostic_probe_percentages
        evidence_refs = ()
        reason = "TMM-TEMPO-DIAGNOSTIC-REQUIRED"
    config_ref = SemanticReference(
        "tempo-configuration", configuration.id, configuration.semantic_fingerprint
    )
    provisional = ControlledTempoPlan(
        schema_version=CURRICULUM_CONTRACT_VERSION,
        id="controlled-tempo-plan:pending",
        semantic_fingerprint="",
        practice_scope_ref=scope_ref,
        configuration_ref=config_ref,
        reference_tempo_bpm=reference_tempo_bpm,
        reference_authority=reference_authority,
        state=state,
        current_controlled_percentage=current,
        tested_percentage=current,
        supported_ceiling_percentage=ceiling,
        diagnostic_probe_percentages=probes,
        evidence_refs=evidence_refs,
        reason_code=reason,
    )
    fingerprint = semantic_fingerprint(provisional)
    return replace(
        provisional,
        id=f"controlled-tempo-plan:{fingerprint}",
        semantic_fingerprint=fingerprint,
    )


def decide_tempo_probe(
    plan: ControlledTempoPlan,
    result: TempoProbeResult,
    *,
    configuration: TempoConfiguration | None = None,
) -> TempoTransition:
    """Return the single deterministic action justified by one probe result."""

    configuration = configuration or default_tempo_configuration()
    require_valid_tempo_configuration(configuration)
    if not 1 <= result.tested_percentage <= 100 or not result.evidence_ref:
        raise ValueError("tempo probe must have a bounded percentage and evidence reference")
    passed = result.required_non_tempo_gates_passed and result.pulse_gate_passed
    previous = plan.current_controlled_percentage
    previous_ceiling = plan.supported_ceiling_percentage
    if passed:
        resulting = max(previous or 0, result.tested_percentage)
        ceiling = max(previous_ceiling or 0, result.tested_percentage)
        if result.tested_percentage >= 100:
            action = TempoPolicyAction.REMOVE_CONSTRAINT
            next_probe = None
            reason = "TMM-TEMPO-PERFORMANCE-CONDITION-SUPPORTED"
        elif previous is not None and result.tested_percentage > previous:
            action = TempoPolicyAction.INCREASE
            next_probe = min(
                100,
                result.tested_percentage + configuration.tempo_increment_percentage,
            )
            reason = "TMM-TEMPO-FASTER-PROBE-SUPPORTED"
        else:
            action = TempoPolicyAction.MAINTAIN
            next_probe = min(
                100,
                result.tested_percentage + configuration.tempo_increment_percentage,
            )
            reason = "TMM-TEMPO-CONTROLLED-CONDITION-SUPPORTED"
        return TempoTransition(
            action,
            previous,
            result.tested_percentage,
            resulting,
            ceiling,
            next_probe,
            result.evidence_ref,
            reason,
        )
    if previous is not None and result.tested_percentage > previous:
        return TempoTransition(
            TempoPolicyAction.MAINTAIN,
            previous,
            result.tested_percentage,
            previous,
            previous_ceiling,
            None,
            result.evidence_ref,
            "TMM-TEMPO-FASTER-PROBE-UNSTABLE",
        )
    lower = _next_lower_probe(result.tested_percentage, configuration)
    return TempoTransition(
        TempoPolicyAction.DECREASE,
        previous,
        result.tested_percentage,
        previous,
        previous_ceiling,
        lower,
        result.evidence_ref,
        "TMM-TEMPO-CONTROL-NOT-SUPPORTED",
    )


def generate_acquisition_graph(
    requirements: PassageRequirementSet,
    branches: PrerequisiteBranchSet,
    *,
    reference_tempo_bpm: Fraction,
    reference_authority: TempoReferenceAuthority,
    tempo_evidence: tuple[CompatibleTempoEvidence, ...] = (),
    configuration: TempoConfiguration | None = None,
) -> AcquisitionGraphSlice:
    """Compose 9B.2 branches into layer, integration, and tempo stages."""

    require_valid_requirement_set(requirements)
    require_valid_prerequisite_branch_set(branches, requirements)
    configuration = configuration or default_tempo_configuration()
    require_valid_tempo_configuration(configuration)
    if branches.resolution is not ArtifactResolution.RESOLVED:
        return _review_stop(requirements, branches, configuration)

    branch_by_requirement = {item.requirement_ref.id: item for item in branches.branches}
    plans = tuple(
        resolve_controlled_tempo(
            scope,
            tempo_evidence,
            reference_tempo_bpm=reference_tempo_bpm,
            reference_authority=reference_authority,
            configuration=configuration,
        )
        for scope in _ordered_scopes(requirements.scopes)
    )
    plans = _apply_highest_common_controlled_tempo(requirements.scopes, plans)
    plan_by_scope = {item.practice_scope_ref.id: item for item in plans}
    nodes = list(branches.nodes)
    edges = list(branches.edges)
    exercises = list(branches.exercises)
    stages: list[AcquisitionStage] = []
    previous_stage_node_id: str | None = None

    component_scopes = tuple(
        scope
        for scope in _ordered_scopes(requirements.scopes)
        if scope.notation_condition is not NotationCondition.COMBINED
    )
    component_stage_nodes: list[str] = []
    for scope in component_scopes:
        requirement = _requirement_for(scope, requirements, "PRIM-LAY-001")
        branch = branch_by_requirement[requirement.id]
        plan = plan_by_scope[scope.id]
        if plan.state is TempoPlanState.DIAGNOSTIC_REQUIRED:
            node, exercise = _new_stage_node(
                AcquisitionStageKind.TEMPO_DIAGNOSTIC,
                requirement,
                scope,
                plan,
                (),
                configuration,
            )
            nodes.append(node)
            exercises.append(exercise)
            stage_node_id = node.id
            evidence_context = "tempo-diagnostic"
        else:
            stage_node_id = branch.application_node_id
            evidence_context = "component-acquisition"
            component_stage_nodes.append(stage_node_id)
        previous_stage_node_id = _append_stage(
            stages,
            edges,
            AcquisitionStageKind.TEMPO_DIAGNOSTIC
            if plan.state is TempoPlanState.DIAGNOSTIC_REQUIRED
            else AcquisitionStageKind.COMPONENT_ACQUISITION,
            stage_node_id,
            scope,
            (),
            plan,
            evidence_context,
            previous_stage_node_id,
        )

    combined = next(
        (
            scope
            for scope in requirements.scopes
            if scope.notation_condition is NotationCondition.COMBINED
        ),
        None,
    )
    target_scope = combined or component_scopes[0]
    target_plan = plan_by_scope[target_scope.id]
    if combined is not None and len(component_stage_nodes) == len(component_scopes):
        coordination = _requirement_for(combined, requirements, "PRIM-COORD-001")
        node, exercise = _new_stage_node(
            AcquisitionStageKind.SELF_PACED_COORDINATION,
            coordination,
            combined,
            target_plan,
            tuple(component_stage_nodes),
            configuration,
        )
        nodes.append(node)
        exercises.append(exercise)
        for component_id in component_stage_nodes:
            edges.append(
                _edge(
                    CurriculumEdgeKind.COMPONENT_OF,
                    component_id,
                    node.id,
                    "component-independent-in-session",
                    0,
                )
            )
        previous_stage_node_id = _append_stage(
            stages,
            edges,
            AcquisitionStageKind.SELF_PACED_COORDINATION,
            node.id,
            combined,
            tuple(component_stage_nodes),
            target_plan,
            "coordination-preparation",
            previous_stage_node_id,
        )

    if target_plan.state is TempoPlanState.DIAGNOSTIC_REQUIRED:
        requirement = _requirement_for(
            target_scope,
            requirements,
            "PRIM-COORD-001" if combined is not None else "PRIM-LAY-001",
        )
        node, exercise = _new_stage_node(
            AcquisitionStageKind.TEMPO_DIAGNOSTIC,
            requirement,
            target_scope,
            target_plan,
            tuple(component_stage_nodes),
            configuration,
        )
        if node.id not in {item.id for item in nodes}:
            nodes.append(node)
            exercises.append(exercise)
            previous_stage_node_id = _append_stage(
                stages,
                edges,
                AcquisitionStageKind.TEMPO_DIAGNOSTIC,
                node.id,
                target_scope,
                tuple(component_stage_nodes),
                target_plan,
                "tempo-diagnostic",
                previous_stage_node_id,
            )
    else:
        pulse_requirement = _requirement_for(
            target_scope,
            requirements,
            "PRIM-RHY-002",
            fallback="PRIM-LAY-001",
        )
        for kind, context in (
            (AcquisitionStageKind.PULSE_INTEGRATION, "pulse-integration"),
            (AcquisitionStageKind.PHRASE_CONTROLLED_TEMPO, "phrase-acquisition"),
            (AcquisitionStageKind.LEARNED_TO_DATE, "connected-learned-to-date"),
            (AcquisitionStageKind.TEMPO_DEVELOPMENT, "tempo-development"),
        ):
            node, exercise = _new_stage_node(
                kind,
                pulse_requirement,
                target_scope,
                target_plan,
                tuple(component_stage_nodes),
                configuration,
            )
            nodes.append(node)
            exercises.append(exercise)
            if kind is AcquisitionStageKind.LEARNED_TO_DATE and previous_stage_node_id:
                edges.append(
                    _edge(
                        CurriculumEdgeKind.CHECKPOINT_AFTER,
                        previous_stage_node_id,
                        node.id,
                        "phrase-controlled-tempo-supported",
                        0,
                    )
                )
            previous_stage_node_id = _append_stage(
                stages,
                edges,
                kind,
                node.id,
                target_scope,
                tuple(component_stage_nodes),
                target_plan,
                context,
                previous_stage_node_id,
            )

    provisional = AcquisitionGraphSlice(
        CURRICULUM_CONTRACT_VERSION,
        "acquisition-graph-slice:pending",
        "",
        CURRICULUM_GRAPH_ID,
        requirements.analysis_id,
        configuration,
        plans,
        tuple(nodes),
        tuple(edges),
        tuple(exercises),
        branches.branches,
        tuple(stages),
        (),
        ArtifactResolution.RESOLVED,
    )
    fingerprint = semantic_fingerprint(provisional)
    result = replace(
        provisional,
        id=f"acquisition-graph-slice:{fingerprint}",
        semantic_fingerprint=fingerprint,
    )
    require_valid_acquisition_graph_slice(result)
    return result


def _review_stop(
    requirements: PassageRequirementSet,
    branches: PrerequisiteBranchSet,
    configuration: TempoConfiguration,
) -> AcquisitionGraphSlice:
    provisional = AcquisitionGraphSlice(
        CURRICULUM_CONTRACT_VERSION,
        "acquisition-graph-slice:pending",
        "",
        CURRICULUM_GRAPH_ID,
        requirements.analysis_id,
        configuration,
        (),
        (),
        (),
        (),
        (),
        (),
        branches.diagnostics,
        ArtifactResolution.REVIEW_REQUIRED,
    )
    fingerprint = semantic_fingerprint(provisional)
    result = replace(
        provisional,
        id=f"acquisition-graph-slice:{fingerprint}",
        semantic_fingerprint=fingerprint,
    )
    require_valid_acquisition_graph_slice(result)
    return result


def _ordered_scopes(
    scopes: tuple[PracticeScopeAssignment, ...],
) -> tuple[PracticeScopeAssignment, ...]:
    order = {
        NotationCondition.SINGLE_LAYER: 0,
        NotationCondition.UPPER_LAYER: 0,
        NotationCondition.LOWER_LAYER: 1,
        NotationCondition.COMBINED: 2,
    }
    return tuple(sorted(scopes, key=lambda item: (order[item.notation_condition], item.id)))


def _apply_highest_common_controlled_tempo(
    scopes: tuple[PracticeScopeAssignment, ...],
    plans: tuple[ControlledTempoPlan, ...],
) -> tuple[ControlledTempoPlan, ...]:
    """Cap combined work at the highest condition supported by every component."""

    combined = next(
        (scope for scope in scopes if scope.notation_condition is NotationCondition.COMBINED),
        None,
    )
    if combined is None:
        return plans
    plan_by_scope = {item.practice_scope_ref.id: item for item in plans}
    combined_plan = plan_by_scope[combined.id]
    component_plans = tuple(
        plan_by_scope[item] for item in combined.component_scope_ids if item in plan_by_scope
    )
    governed = (combined_plan, *component_plans)
    if len(component_plans) != len(combined.component_scope_ids) or any(
        item.state is TempoPlanState.DIAGNOSTIC_REQUIRED for item in governed
    ):
        return plans
    controlled = min(
        item.current_controlled_percentage
        for item in governed
        if item.current_controlled_percentage is not None
    )
    ceiling = min(
        item.supported_ceiling_percentage
        for item in governed
        if item.supported_ceiling_percentage is not None
    )
    evidence_refs = tuple(sorted({ref for item in governed for ref in item.evidence_refs}))
    provisional = replace(
        combined_plan,
        id="controlled-tempo-plan:pending",
        semantic_fingerprint="",
        current_controlled_percentage=controlled,
        tested_percentage=controlled,
        supported_ceiling_percentage=ceiling,
        evidence_refs=evidence_refs,
        reason_code="TMM-TEMPO-HIGHEST-COMMON-CONTROLLED",
    )
    fingerprint = semantic_fingerprint(provisional)
    replacement = replace(
        provisional,
        id=f"controlled-tempo-plan:{fingerprint}",
        semantic_fingerprint=fingerprint,
    )
    return tuple(
        replacement if item.practice_scope_ref.id == combined.id else item for item in plans
    )


def _requirement_for(
    scope: PracticeScopeAssignment,
    requirements: PassageRequirementSet,
    primitive_id: str,
    *,
    fallback: str | None = None,
) -> PassageSkillRequirement:
    for candidate in (primitive_id, fallback):
        if candidate is None:
            continue
        match = next(
            (
                item
                for item in requirements.requirements
                if item.practice_scope_ref.id == scope.id and item.primitive_ref.id == candidate
            ),
            None,
        )
        if match is not None:
            return match
    raise ValueError(f"TMM-REQUIREMENT-EVIDENCE-INCOMPLETE: {scope.id} lacks {primitive_id}")


def _new_stage_node(
    kind: AcquisitionStageKind,
    requirement: PassageSkillRequirement,
    scope: PracticeScopeAssignment,
    plan: ControlledTempoPlan,
    component_node_ids: tuple[str, ...],
    configuration: TempoConfiguration,
) -> tuple[CurriculumGraphNode, ExerciseInstance]:
    node_id = derived_id("curriculum-node", ("9B.3", kind.value, scope.id, plan.id))
    requirement_ref = SemanticReference(
        "passage-skill-requirement", requirement.id, requirement.semantic_fingerprint
    )
    template_id = "TEMPLATE-INTEGRATION-001"
    template_ref = SemanticReference(
        "exercise-template",
        template_id,
        semantic_fingerprint((EXERCISE_TEMPLATE_CATALOGUE_ID, template_id)),
    )
    plan_ref = _plan_ref(plan)
    activity_forms = (
        (ActivityForm.ORIENT, ActivityForm.PERFORM)
        if kind is AcquisitionStageKind.TEMPO_DIAGNOSTIC
        else (ActivityForm.ORIENT, ActivityForm.DEMONSTRATE_LISTEN, ActivityForm.PERFORM)
    )
    activities = tuple(
        ExerciseActivity(
            derived_id("exercise-activity", (kind.value, scope.id, index, form.value)),
            form,
            form is ActivityForm.PERFORM,
        )
        for index, form in enumerate(activity_forms)
    )
    conditions: tuple[str, ...]
    independent: str | None
    if kind is AcquisitionStageKind.SELF_PACED_COORDINATION:
        conditions = ("self-paced-guided", "self-paced-independent")
        initial = conditions[0]
        independent = conditions[1]
    elif kind is AcquisitionStageKind.TEMPO_DIAGNOSTIC:
        conditions = tuple(
            f"tempo-probe-{percentage}" for percentage in plan.diagnostic_probe_percentages
        )
        initial = conditions[0]
        independent = None
    else:
        percentage = plan.current_controlled_percentage
        if percentage is None:
            raise ValueError("controlled-tempo stage requires resolved tempo evidence")
        conditions = (f"controlled-tempo-{percentage}",)
        initial = conditions[0]
        independent = conditions[0]
    context = _exercise_evidence_context(kind, scope)
    material = CanonicalExcerptMaterial(
        "canonical-excerpt",
        scope.score_package_digest,
        scope.score_id,
        _scope_ref(scope),
        scope.canonical_anchor_set_id,
        scope.active_target_ids,
        scope.inactive_context_ids,
    )
    rule = _rule("ACQUISITION-RULE-001")
    provisional = ExerciseInstance(
        CURRICULUM_CONTRACT_VERSION,
        "exercise-instance:pending",
        "",
        (),
        template_ref,
        requirement_ref,
        _scope_ref(scope),
        material,
        activities,
        ExerciseSupportEnvelope(initial, conditions, independent),
        tuple(
            ExerciseEvidenceExit(dimension, context, "supported")
            for dimension in requirement.required_dimensions
        ),
        node_id,
        (
            requirement_ref,
            _scope_ref(scope),
            plan_ref,
            SemanticReference(
                "tempo-configuration", configuration.id, configuration.semantic_fingerprint
            ),
        ),
        rule,
        ArtifactResolution.RESOLVED,
    )
    fingerprint = semantic_fingerprint(provisional)
    exercise = replace(
        provisional,
        id=f"exercise-instance:{fingerprint}",
        semantic_fingerprint=fingerprint,
    )
    exercise_ref = SemanticReference(
        "exercise-instance", exercise.id, exercise.semantic_fingerprint
    )
    return (
        CurriculumGraphNode(
            node_id,
            CurriculumNodeKind.INTEGRATION,
            _scope_ref(scope),
            requirement.primitive_ref,
            requirement_ref,
            exercise_ref,
            component_node_ids,
            "tempo-probe" if kind is AcquisitionStageKind.TEMPO_DIAGNOSTIC else None,
            None,
        ),
        exercise,
    )


def _exercise_evidence_context(
    kind: AcquisitionStageKind,
    scope: PracticeScopeAssignment,
) -> str:
    """Keep monophonic pulse work independent from multi-layer integration.

    A single written layer has no component topology to integrate.  Its pulse
    stage is therefore evidence about applying that same passage independently,
    while an actual combined scope retains the stricter integration context.
    """

    if kind is AcquisitionStageKind.PULSE_INTEGRATION:
        return (
            "integration"
            if scope.notation_condition is NotationCondition.COMBINED
            else "passage-application"
        )
    return {
        AcquisitionStageKind.TEMPO_DIAGNOSTIC: "tempo-diagnostic",
        AcquisitionStageKind.SELF_PACED_COORDINATION: "coordination-preparation",
        AcquisitionStageKind.PHRASE_CONTROLLED_TEMPO: "passage-application",
        AcquisitionStageKind.LEARNED_TO_DATE: "connected-learned-to-date",
        AcquisitionStageKind.TEMPO_DEVELOPMENT: "tempo-development",
        AcquisitionStageKind.COMPONENT_ACQUISITION: "component-acquisition",
    }[kind]


def _append_stage(
    stages: list[AcquisitionStage],
    edges: list[CurriculumGraphEdge],
    kind: AcquisitionStageKind,
    node_id: str,
    scope: PracticeScopeAssignment,
    component_node_ids: tuple[str, ...],
    plan: ControlledTempoPlan,
    evidence_context: str,
    previous_node_id: str | None,
) -> str:
    stage = AcquisitionStage(
        derived_id("acquisition-stage", (len(stages), kind.value, node_id, plan.id)),
        kind,
        len(stages),
        node_id,
        _scope_ref(scope),
        component_node_ids,
        _plan_ref(plan),
        evidence_context,
    )
    stages.append(stage)
    if previous_node_id is not None and previous_node_id != node_id:
        edges.append(
            _edge(
                CurriculumEdgeKind.ON_SATISFIED,
                previous_node_id,
                node_id,
                f"{stages[-2].kind.value}-supported",
                0,
            )
        )
    return node_id


def _edge(
    kind: CurriculumEdgeKind,
    source: str,
    target: str,
    guard: str,
    precedence: int,
) -> CurriculumGraphEdge:
    return CurriculumGraphEdge(
        derived_id("curriculum-edge", (kind.value, source, target, guard, precedence)),
        kind,
        source,
        target,
        None,
        guard,
        None,
        None,
        precedence,
    )


def _scope_ref(scope: PracticeScopeAssignment) -> SemanticReference:
    return SemanticReference("practice-scope-assignment", scope.id, scope.semantic_fingerprint)


def _plan_ref(plan: ControlledTempoPlan) -> SemanticReference:
    return SemanticReference("controlled-tempo-plan", plan.id, plan.semantic_fingerprint)


def _rule(identifier: str) -> RuleReference:
    return RuleReference(
        identifier,
        TEMPO_CONFIGURATION_VERSION,
        semantic_fingerprint((identifier, TEMPO_CONFIGURATION_VERSION)),
    )


def _next_lower_probe(value: int, configuration: TempoConfiguration) -> int | None:
    return next(
        (
            percentage
            for percentage in configuration.diagnostic_probe_percentages
            if percentage < value
        ),
        None,
    )
