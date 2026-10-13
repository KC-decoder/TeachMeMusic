"""Deterministic DEV-009 Task 9B.4 retention and transfer composition."""

from __future__ import annotations

from dataclasses import replace

from .curriculum_contracts import (
    CURRICULUM_CONTRACT_VERSION,
    EXERCISE_TEMPLATE_CATALOGUE_ID,
    LASTING_SKILL_GENERATOR_VERSION,
    LASTING_SKILL_GRAPH_ID,
    AcquisitionGraphSlice,
    AcquisitionStageKind,
    ActivityForm,
    ArtifactResolution,
    CanonicalExcerptMaterial,
    CurriculumDiagnostic,
    CurriculumEdgeKind,
    CurriculumGraphEdge,
    CurriculumGraphNode,
    CurriculumNodeKind,
    DiagnosticParameter,
    DiagnosticSeverity,
    ExerciseActivity,
    ExerciseEvidenceExit,
    ExerciseInstance,
    ExerciseSupportEnvelope,
    LastingSkillGraphSlice,
    LastingSkillStage,
    LastingSkillStageKind,
    PassageRequirementSet,
    PassageSkillRequirement,
    PracticeScopeAssignment,
    RetentionAnchorKind,
    RetentionCheckpointKind,
    RetentionSchedule,
    RetentionWindow,
    RuleReference,
    SemanticReference,
    TransferTargetAssignment,
    TransferTargetRequest,
)
from .curriculum_fingerprint import derived_id, semantic_fingerprint
from .curriculum_validation import (
    require_valid_acquisition_graph_slice,
    require_valid_lasting_skill_graph_slice,
    require_valid_requirement_set,
)

_TRANSFER_DIFFERENCE_DIMENSIONS = frozenset(
    {
        "score",
        "passage",
        "material",
        "parameters",
        "notation-condition",
        "register",
        "meter",
        "rhythm",
        "harmony",
        "layer-topology",
    }
)


def default_retention_windows() -> tuple[RetentionWindow, ...]:
    """Return the frozen R1/R2 relative schedule from policy design 9A.7."""

    definitions = (
        (RetentionCheckpointKind.R1, RetentionAnchorKind.ACQUISITION, 24, 20, 72),
        (RetentionCheckpointKind.R2, RetentionAnchorKind.PASSING_R1, 168, 120, 240),
    )
    windows: list[RetentionWindow] = []
    for checkpoint, anchor, due, valid_after, valid_before in definitions:
        rule = _rule(f"RETENTION-WINDOW-{checkpoint.value}")
        provisional = RetentionWindow(
            CURRICULUM_CONTRACT_VERSION,
            "retention-window:pending",
            "",
            checkpoint,
            anchor,
            due,
            valid_after,
            valid_before,
            rule,
        )
        fingerprint = semantic_fingerprint(provisional)
        windows.append(
            replace(
                provisional,
                id=f"retention-window:{fingerprint}",
                semantic_fingerprint=fingerprint,
            )
        )
    return tuple(windows)


def generate_lasting_skill_graph(
    source_requirements: PassageRequirementSet,
    acquisition: AcquisitionGraphSlice,
    transfer_requirements: PassageRequirementSet,
    *,
    transfer_requests: tuple[TransferTargetRequest, ...],
    retention_windows: tuple[RetentionWindow, ...] | None = None,
) -> LastingSkillGraphSlice:
    """Add exact delayed retention and different-target transfer routes.

    Target selection is explicit because choosing a pedagogically suitable
    transfer passage is not a score-title heuristic.  Invalid or incomplete
    scheduling/target evidence returns a non-playable review result.
    """

    require_valid_requirement_set(source_requirements)
    require_valid_requirement_set(transfer_requirements)
    require_valid_acquisition_graph_slice(acquisition)
    windows = default_retention_windows() if retention_windows is None else retention_windows
    diagnostics = _input_diagnostics(
        source_requirements,
        acquisition,
        transfer_requirements,
        transfer_requests,
        windows,
    )
    if diagnostics:
        return _review_stop(
            source_requirements,
            acquisition,
            transfer_requirements,
            diagnostics,
        )

    source_requirement_by_id = {item.id: item for item in source_requirements.requirements}
    source_scope_by_id = {item.id: item for item in source_requirements.scopes}
    target_requirement_by_id = {item.id: item for item in transfer_requirements.requirements}
    target_scope_by_id = {item.id: item for item in transfer_requirements.scopes}
    branch_by_requirement = {item.requirement_ref.id: item for item in acquisition.branches}
    source_node_by_requirement = _retention_source_nodes(acquisition)

    nodes = list(acquisition.nodes)
    edges = list(acquisition.edges)
    exercises = list(acquisition.exercises)
    schedules: list[RetentionSchedule] = []
    assignments: list[TransferTargetAssignment] = []
    stages: list[LastingSkillStage] = []
    r1_node_by_requirement: dict[str, str] = {}

    for requirement_id in sorted(source_node_by_requirement):
        requirement = source_requirement_by_id[requirement_id]
        scope = source_scope_by_id[requirement.practice_scope_ref.id]
        source_node_id = source_node_by_requirement[requirement_id]
        return_node_id = branch_by_requirement[requirement_id].application_node_id
        schedule = _retention_schedule(
            requirement,
            scope,
            source_node_id,
            return_node_id,
            windows,
        )
        schedules.append(schedule)
        previous_node_id = source_node_id
        for window in schedule.windows:
            node, exercise = _retention_node(
                requirement,
                scope,
                schedule,
                window,
                return_node_id,
            )
            nodes.append(node)
            exercises.append(exercise)
            if window.checkpoint is RetentionCheckpointKind.R1:
                r1_node_by_requirement[requirement.id] = node.id
                guard = "independent-source-evidence-supported;R1-due"
            else:
                guard = "passing-R1-evidence-supported;R2-due"
            edges.append(
                _edge(
                    CurriculumEdgeKind.SCHEDULE_RETENTION,
                    previous_node_id,
                    node.id,
                    guard,
                    precedence=7,
                )
            )
            edges.append(
                _edge(
                    CurriculumEdgeKind.RETURN_TO,
                    node.id,
                    return_node_id,
                    "retention-result-recorded",
                    precedence=5,
                    return_node_id=return_node_id,
                )
            )
            stages.append(
                LastingSkillStage(
                    derived_id(
                        "lasting-skill-stage",
                        (len(stages), "retention", schedule.id, window.id, node.id),
                    ),
                    LastingSkillStageKind.RETENTION,
                    len(stages),
                    node.id,
                    _requirement_ref(requirement),
                    _scope_ref(scope),
                    _requirement_ref(requirement),
                    source_node_id,
                    return_node_id,
                    _schedule_ref(schedule),
                    None,
                    "retention",
                )
            )
            previous_node_id = node.id

    for request in sorted(
        transfer_requests,
        key=lambda item: (item.source_requirement_id, item.target_requirement_id),
    ):
        source_requirement = source_requirement_by_id[request.source_requirement_id]
        source_scope = source_scope_by_id[source_requirement.practice_scope_ref.id]
        target_requirement = target_requirement_by_id[request.target_requirement_id]
        target_scope = target_scope_by_id[target_requirement.practice_scope_ref.id]
        source_node_id = source_node_by_requirement[source_requirement.id]
        return_node_id = branch_by_requirement[source_requirement.id].application_node_id
        assignment = _transfer_assignment(
            source_requirement,
            source_scope,
            target_requirement,
            target_scope,
            request,
            return_node_id,
        )
        assignments.append(assignment)
        node, exercise = _transfer_node(
            source_requirement,
            target_requirement,
            target_scope,
            assignment,
            return_node_id,
        )
        nodes.append(node)
        exercises.append(exercise)
        r1_node_id = r1_node_by_requirement[source_requirement.id]
        edges.append(
            _edge(
                CurriculumEdgeKind.SCHEDULE_TRANSFER,
                r1_node_id,
                node.id,
                "R1-passed;target-previously-untrained;difference-proven",
                precedence=10,
            )
        )
        edges.append(
            _edge(
                CurriculumEdgeKind.RETURN_TO,
                node.id,
                return_node_id,
                "single-transfer-result-recorded",
                precedence=5,
                return_node_id=return_node_id,
            )
        )
        stages.append(
            LastingSkillStage(
                derived_id(
                    "lasting-skill-stage",
                    (len(stages), "transfer", assignment.id, node.id),
                ),
                LastingSkillStageKind.TRANSFER,
                len(stages),
                node.id,
                _requirement_ref(target_requirement),
                _scope_ref(target_scope),
                _requirement_ref(source_requirement),
                source_node_id,
                return_node_id,
                None,
                _transfer_ref(assignment),
                "transfer",
            )
        )

    provisional = LastingSkillGraphSlice(
        CURRICULUM_CONTRACT_VERSION,
        "lasting-skill-graph-slice:pending",
        "",
        LASTING_SKILL_GRAPH_ID,
        source_requirements.analysis_id,
        transfer_requirements.analysis_id,
        _acquisition_ref(acquisition),
        tuple(nodes),
        tuple(edges),
        tuple(exercises),
        tuple(schedules),
        tuple(assignments),
        tuple(stages),
        (),
        ArtifactResolution.RESOLVED,
    )
    fingerprint = semantic_fingerprint(provisional)
    result = replace(
        provisional,
        id=f"lasting-skill-graph-slice:{fingerprint}",
        semantic_fingerprint=fingerprint,
    )
    require_valid_lasting_skill_graph_slice(
        result,
        source_requirements,
        acquisition,
        transfer_requirements,
    )
    return result


def _input_diagnostics(
    source_requirements: PassageRequirementSet,
    acquisition: AcquisitionGraphSlice,
    transfer_requirements: PassageRequirementSet,
    requests: tuple[TransferTargetRequest, ...],
    windows: tuple[RetentionWindow, ...],
) -> tuple[CurriculumDiagnostic, ...]:
    diagnostics: list[CurriculumDiagnostic] = []
    if acquisition.resolution is not ArtifactResolution.RESOLVED:
        diagnostics.append(
            _diagnostic(
                "TMM-REQUIREMENT-AMBIGUOUS",
                "lasting_skills.acquisition",
                (acquisition.id,),
            )
        )
    if not _valid_window_shape(windows):
        diagnostics.append(
            _diagnostic(
                "TMM-RETENTION-SCHEDULE-INVALID",
                "lasting_skills.retention_windows",
                tuple(item.id for item in windows),
            )
        )
    source_by_id = {item.id: item for item in source_requirements.requirements}
    target_by_id = {item.id: item for item in transfer_requirements.requirements}
    source_scopes = {item.id: item for item in source_requirements.scopes}
    target_scopes = {item.id: item for item in transfer_requirements.scopes}
    eligible = _retention_source_nodes(acquisition)
    if not requests:
        diagnostics.append(
            _diagnostic(
                "TMM-TRANSFER-TARGET-UNRESOLVED",
                "lasting_skills.transfer_requests",
                (),
            )
        )
    seen: set[tuple[str, str]] = set()
    for index, request in enumerate(requests):
        pair = (request.source_requirement_id, request.target_requirement_id)
        source = source_by_id.get(request.source_requirement_id)
        target = target_by_id.get(request.target_requirement_id)
        if pair in seen or source is None or target is None or source.id not in eligible:
            diagnostics.append(
                _diagnostic(
                    "TMM-TRANSFER-TARGET-UNRESOLVED",
                    f"lasting_skills.transfer_requests[{index}]",
                    tuple(item for item in pair if item),
                )
            )
            continue
        seen.add(pair)
        source_scope = source_scopes[source.practice_scope_ref.id]
        target_scope = target_scopes[target.practice_scope_ref.id]
        known_evidence = set(target.canonical_evidence_refs)
        known_evidence.update(target.analysis_evidence_refs)
        known_evidence.update(target_scope.active_target_ids)
        materially_different = (
            source_scope.id != target_scope.id
            and source_scope.active_target_ids != target_scope.active_target_ids
            and (
                source_scope.score_package_digest != target_scope.score_package_digest
                or source_scope.score_range != target_scope.score_range
                or source.target_parameters != target.target_parameters
                or source.canonical_evidence_refs != target.canonical_evidence_refs
            )
        )
        if (
            source.primitive_ref != target.primitive_ref
            or not materially_different
            or not request.difference_dimensions
            or request.difference_dimensions != tuple(sorted(set(request.difference_dimensions)))
            or not set(request.difference_dimensions) <= _TRANSFER_DIFFERENCE_DIMENSIONS
            or not request.difference_evidence_refs
            or request.difference_evidence_refs
            != tuple(sorted(set(request.difference_evidence_refs)))
            or not set(request.difference_evidence_refs) <= known_evidence
        ):
            diagnostics.append(
                _diagnostic(
                    "TMM-TRANSFER-TARGET-UNRESOLVED",
                    f"lasting_skills.transfer_requests[{index}]",
                    pair,
                    (DiagnosticParameter("primitive", "stable-id", source.primitive_ref.id),),
                )
            )
    return tuple(diagnostics)


def _valid_window_shape(windows: tuple[RetentionWindow, ...]) -> bool:
    if tuple(item.checkpoint for item in windows) != (
        RetentionCheckpointKind.R1,
        RetentionCheckpointKind.R2,
    ):
        return False
    expected = (
        (RetentionAnchorKind.ACQUISITION, 24, 20, 72),
        (RetentionAnchorKind.PASSING_R1, 168, 120, 240),
    )
    for item, definition in zip(windows, expected, strict=True):
        if (
            (item.anchor, item.due_after_hours, item.valid_after_hours, item.valid_before_hours)
            != definition
            or item.valid_after_hours > item.due_after_hours
            or item.due_after_hours > item.valid_before_hours
            or item.semantic_fingerprint != semantic_fingerprint(item)
        ):
            return False
    return True


def _retention_source_nodes(acquisition: AcquisitionGraphSlice) -> dict[str, str]:
    node_by_id = {item.id: item for item in acquisition.nodes}
    result: dict[str, str] = {}
    excluded = {
        AcquisitionStageKind.TEMPO_DIAGNOSTIC,
        AcquisitionStageKind.SELF_PACED_COORDINATION,
    }
    for stage in acquisition.stages:
        node = node_by_id.get(stage.node_id)
        if stage.kind not in excluded and node is not None and node.requirement_ref is not None:
            result[node.requirement_ref.id] = node.id
    return result


def _retention_schedule(
    requirement: PassageSkillRequirement,
    scope: PracticeScopeAssignment,
    source_node_id: str,
    return_node_id: str,
    windows: tuple[RetentionWindow, ...],
) -> RetentionSchedule:
    provisional = RetentionSchedule(
        CURRICULUM_CONTRACT_VERSION,
        "retention-schedule:pending",
        "",
        _requirement_ref(requirement),
        _scope_ref(scope),
        source_node_id,
        return_node_id,
        windows,
    )
    fingerprint = semantic_fingerprint(provisional)
    return replace(
        provisional,
        id=f"retention-schedule:{fingerprint}",
        semantic_fingerprint=fingerprint,
    )


def _transfer_assignment(
    source_requirement: PassageSkillRequirement,
    source_scope: PracticeScopeAssignment,
    target_requirement: PassageSkillRequirement,
    target_scope: PracticeScopeAssignment,
    request: TransferTargetRequest,
    return_node_id: str,
) -> TransferTargetAssignment:
    rule = _rule("TRANSFER-SIMILARITY-001")
    provisional = TransferTargetAssignment(
        CURRICULUM_CONTRACT_VERSION,
        "transfer-target-assignment:pending",
        "",
        _requirement_ref(source_requirement),
        _scope_ref(source_scope),
        _requirement_ref(target_requirement),
        _scope_ref(target_scope),
        source_requirement.primitive_ref,
        request.difference_dimensions,
        request.difference_evidence_refs,
        "previously-untrained-at-attempt-open",
        rule,
        return_node_id,
        ArtifactResolution.RESOLVED,
    )
    fingerprint = semantic_fingerprint(provisional)
    return replace(
        provisional,
        id=f"transfer-target-assignment:{fingerprint}",
        semantic_fingerprint=fingerprint,
    )


def _retention_node(
    requirement: PassageSkillRequirement,
    scope: PracticeScopeAssignment,
    schedule: RetentionSchedule,
    window: RetentionWindow,
    return_node_id: str,
) -> tuple[CurriculumGraphNode, ExerciseInstance]:
    node_id = derived_id(
        "curriculum-node",
        ("9B.4", "retention", requirement.id, schedule.id, window.id),
    )
    exercise = _exercise(
        "TEMPLATE-RETENTION-001",
        requirement,
        scope,
        node_id,
        return_node_id,
        "retention",
        f"retention-independent-{window.checkpoint.value}",
        (_schedule_ref(schedule), _window_ref(window)),
    )
    return (
        CurriculumGraphNode(
            node_id,
            CurriculumNodeKind.RETENTION,
            _scope_ref(scope),
            requirement.primitive_ref,
            _requirement_ref(requirement),
            _exercise_ref(exercise),
            (),
            f"retention-{window.checkpoint.value}",
            None,
        ),
        exercise,
    )


def _transfer_node(
    source_requirement: PassageSkillRequirement,
    target_requirement: PassageSkillRequirement,
    target_scope: PracticeScopeAssignment,
    assignment: TransferTargetAssignment,
    return_node_id: str,
) -> tuple[CurriculumGraphNode, ExerciseInstance]:
    node_id = derived_id(
        "curriculum-node",
        ("9B.4", "transfer", source_requirement.id, target_requirement.id, assignment.id),
    )
    exercise = _exercise(
        "TEMPLATE-TRANSFER-001",
        target_requirement,
        target_scope,
        node_id,
        return_node_id,
        "transfer",
        "transfer-independent",
        (_transfer_ref(assignment), _requirement_ref(source_requirement)),
    )
    return (
        CurriculumGraphNode(
            node_id,
            CurriculumNodeKind.TRANSFER,
            _scope_ref(target_scope),
            target_requirement.primitive_ref,
            _requirement_ref(target_requirement),
            _exercise_ref(exercise),
            (),
            "single-transfer-attempt",
            None,
        ),
        exercise,
    )


def _exercise(
    template_id: str,
    requirement: PassageSkillRequirement,
    scope: PracticeScopeAssignment,
    node_id: str,
    return_node_id: str,
    evidence_context: str,
    condition: str,
    extra_inputs: tuple[SemanticReference, ...],
) -> ExerciseInstance:
    template_ref = SemanticReference(
        "exercise-template",
        template_id,
        semantic_fingerprint((EXERCISE_TEMPLATE_CATALOGUE_ID, template_id)),
    )
    activities = tuple(
        ExerciseActivity(
            derived_id(
                "exercise-activity",
                (template_id, requirement.id, index, form.value),
            ),
            form,
            form is ActivityForm.PERFORM,
        )
        for index, form in enumerate((ActivityForm.ORIENT, ActivityForm.PERFORM))
    )
    material = CanonicalExcerptMaterial(
        "canonical-excerpt",
        scope.score_package_digest,
        scope.score_id,
        _scope_ref(scope),
        scope.canonical_anchor_set_id,
        scope.active_target_ids,
        scope.inactive_context_ids,
    )
    provisional = ExerciseInstance(
        CURRICULUM_CONTRACT_VERSION,
        "exercise-instance:pending",
        "",
        (),
        template_ref,
        _requirement_ref(requirement),
        _scope_ref(scope),
        material,
        activities,
        ExerciseSupportEnvelope(condition, (condition,), condition),
        tuple(
            ExerciseEvidenceExit(dimension, evidence_context, "supported")
            for dimension in requirement.required_dimensions
        ),
        return_node_id,
        (_requirement_ref(requirement), _scope_ref(scope), *extra_inputs),
        _rule("LASTING-SKILL-EXERCISE-001"),
        ArtifactResolution.RESOLVED,
    )
    fingerprint = semantic_fingerprint(provisional)
    return replace(
        provisional,
        id=f"exercise-instance:{fingerprint}",
        semantic_fingerprint=fingerprint,
    )


def _review_stop(
    source_requirements: PassageRequirementSet,
    acquisition: AcquisitionGraphSlice,
    transfer_requirements: PassageRequirementSet,
    diagnostics: tuple[CurriculumDiagnostic, ...],
) -> LastingSkillGraphSlice:
    provisional = LastingSkillGraphSlice(
        CURRICULUM_CONTRACT_VERSION,
        "lasting-skill-graph-slice:pending",
        "",
        LASTING_SKILL_GRAPH_ID,
        source_requirements.analysis_id,
        transfer_requirements.analysis_id,
        _acquisition_ref(acquisition),
        (),
        (),
        (),
        (),
        (),
        (),
        diagnostics,
        ArtifactResolution.REVIEW_REQUIRED,
    )
    fingerprint = semantic_fingerprint(provisional)
    result = replace(
        provisional,
        id=f"lasting-skill-graph-slice:{fingerprint}",
        semantic_fingerprint=fingerprint,
    )
    require_valid_lasting_skill_graph_slice(result)
    return result


def _diagnostic(
    code: str,
    path: str,
    related_ids: tuple[str, ...],
    parameters: tuple[DiagnosticParameter, ...] = (),
) -> CurriculumDiagnostic:
    return CurriculumDiagnostic(
        code,
        DiagnosticSeverity.REVIEW,
        ArtifactResolution.REVIEW_REQUIRED,
        path,
        related_ids,
        parameters,
    )


def _edge(
    kind: CurriculumEdgeKind,
    source: str,
    target: str,
    guard: str,
    *,
    precedence: int,
    return_node_id: str | None = None,
) -> CurriculumGraphEdge:
    return CurriculumGraphEdge(
        derived_id(
            "curriculum-edge",
            (kind.value, source, target, guard, precedence, return_node_id or "none"),
        ),
        kind,
        source,
        target,
        None,
        guard,
        None,
        return_node_id,
        precedence,
    )


def _requirement_ref(requirement: PassageSkillRequirement) -> SemanticReference:
    return SemanticReference(
        "passage-skill-requirement", requirement.id, requirement.semantic_fingerprint
    )


def _scope_ref(scope: PracticeScopeAssignment) -> SemanticReference:
    return SemanticReference("practice-scope-assignment", scope.id, scope.semantic_fingerprint)


def _exercise_ref(exercise: ExerciseInstance) -> SemanticReference:
    return SemanticReference("exercise-instance", exercise.id, exercise.semantic_fingerprint)


def _schedule_ref(schedule: RetentionSchedule) -> SemanticReference:
    return SemanticReference("retention-schedule", schedule.id, schedule.semantic_fingerprint)


def _window_ref(window: RetentionWindow) -> SemanticReference:
    return SemanticReference("retention-window", window.id, window.semantic_fingerprint)


def _transfer_ref(assignment: TransferTargetAssignment) -> SemanticReference:
    return SemanticReference(
        "transfer-target-assignment", assignment.id, assignment.semantic_fingerprint
    )


def _acquisition_ref(acquisition: AcquisitionGraphSlice) -> SemanticReference:
    return SemanticReference(
        "acquisition-graph-slice", acquisition.id, acquisition.semantic_fingerprint
    )


def _rule(identifier: str) -> RuleReference:
    return RuleReference(
        identifier,
        LASTING_SKILL_GENERATOR_VERSION,
        semantic_fingerprint((identifier, LASTING_SKILL_GENERATOR_VERSION)),
    )
