"""Title-blind DEV-009 practice-scope and passage-requirement derivation."""

from __future__ import annotations

from dataclasses import replace
from fractions import Fraction

from teachmemusic.analysis import (
    AnalysisFactKind,
    BoundaryReason,
    LayerProfile,
    ScoreAnalysis,
    require_valid_score_analysis,
)
from teachmemusic.score import (
    CanonicalMusicPackage,
    CanonicalScoreContent,
    ScoreDocument,
    require_valid_package,
)
from teachmemusic.score.v2.temporal import TemporalEvent, TemporalMeasure, TemporalPart

from .contracts import CanonicalAnchor, CanonicalAnchorKind, CanonicalAnchorSet
from .curriculum_contracts import (
    CURRICULUM_CONTRACT_VERSION,
    PRIMITIVE_CATALOGUE_ID,
    REQUIREMENT_RULE_VERSION,
    ArtifactResolution,
    CurriculumDiagnostic,
    DiagnosticSeverity,
    ExecutionAssignment,
    InterpretationProducer,
    LearningPrimitive,
    NotationCondition,
    ParameterDefinition,
    PassageRequirementSet,
    PassageSkillRequirement,
    PracticeInterpretation,
    PracticeLayerGroup,
    PracticeScopeAssignment,
    PrimitiveFamily,
    RequirementNecessity,
    RequirementProducer,
    RequirementRole,
    ReviewState,
    RuleReference,
    ScoreRange,
    SemanticReference,
    TypedParameter,
)
from .curriculum_fingerprint import derived_id, semantic_fingerprint
from .curriculum_validation import require_valid_requirement_set

_CATALOGUE_VERSION = "0.1"
_SCOPE_RULE_ID = "SCOPE-RULE-001"
_PARAMETERS: dict[str, tuple[tuple[str, str], ...]] = {
    "PRIM-AUR-001": (("return-scope", "stable-id"),),
    "PRIM-AUR-002": (("return-scope", "stable-id"),),
    "PRIM-KEY-001": (("target-pitches", "pitch-list"),),
    "PRIM-KEY-002": (("movement-pairs", "ordered-pair-list"),),
    "PRIM-READ-001": (("target-pitches", "pitch-list"),),
    "PRIM-READ-002": (("practice-scope", "stable-id"),),
    "PRIM-RHY-001": (("duration-vocabulary", "fraction-list"), ("meter", "string")),
    "PRIM-RHY-002": (("duration-vocabulary", "fraction-list"), ("meter", "string")),
    "PRIM-RHY-003": (("rhythm-cell-events", "stable-id-list"),),
    "PRIM-RHY-004": (("metric-entry", "fraction"),),
    "PRIM-PAT-001": (("pattern-id", "stable-id"),),
    "PRIM-HAR-001": (("chord-events", "stable-id-list"),),
    "PRIM-HAR-002": (("accompaniment-events", "stable-id-list"),),
    "PRIM-LAY-001": (("practice-scope", "stable-id"),),
    "PRIM-COORD-001": (("component-scopes", "stable-id-list"),),
    "PRIM-COORD-002": (("component-scopes", "stable-id-list"),),
    "PRIM-TECH-001": (("repeated-note-events", "stable-id-list"),),
    "PRIM-TECH-002": (("continuity-events", "stable-id-list"),),
    "PRIM-EXP-001": (("dynamic-events", "stable-id-list"),),
    "PRIM-EXP-002": (("pedal-events", "stable-id-list"),),
    "PRIM-MEM-001": (("start-landmark", "stable-id"),),
    "PRIM-PRAC-001": (("discrepancy-ref", "stable-id"),),
}


class RequirementDerivationError(ValueError):
    """Raised when score and analysis inputs cannot support bounded derivation."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(f"{code}: {message}")


def learning_primitive_catalogue() -> tuple[LearningPrimitive, ...]:
    """Return the immutable first TeachMeMusic learning-primitive catalogue."""

    specs = (
        (
            "PRIM-AUR-001",
            PrimitiveFamily.LISTENING,
            "recognize melodic contour",
            (),
            ("selection-response",),
            ("internal hearing",),
        ),
        (
            "PRIM-AUR-002",
            PrimitiveFamily.LISTENING,
            "hear, retain, and echo a short pattern",
            ("PRIM-AUR-001", "PRIM-KEY-001"),
            ("pitch", "order", "onset", "duration"),
            ("internal audiation",),
        ),
        (
            "PRIM-KEY-001",
            PrimitiveFamily.KEYBOARD,
            "locate a named pitch in the required register",
            (),
            ("pitch",),
            ("posture", "finger choice"),
        ),
        (
            "PRIM-KEY-002",
            PrimitiveFamily.KEYBOARD,
            "execute a directed step, repeat, or leap",
            ("PRIM-KEY-001",),
            ("pitch", "order", "continuity"),
            ("movement quality", "tension"),
        ),
        (
            "PRIM-READ-001",
            PrimitiveFamily.SCORE_LITERACY,
            "map notated pitch to the keyboard",
            ("PRIM-KEY-001",),
            ("pitch", "order", "selection-response"),
            ("visual attention",),
        ),
        (
            "PRIM-READ-002",
            PrimitiveFamily.SCORE_LITERACY,
            "follow one declared notation layer",
            ("PRIM-READ-001",),
            ("pitch", "order"),
            ("visual attention",),
        ),
        (
            "PRIM-RHY-001",
            PrimitiveFamily.RHYTHM,
            "maintain a declared steady pulse",
            (),
            ("onset",),
            ("pulse without timing calibration",),
        ),
        (
            "PRIM-RHY-002",
            PrimitiveFamily.RHYTHM,
            "realize written durations and rests in sequence",
            ("PRIM-RHY-001",),
            ("onset", "duration", "release", "continuity"),
            ("silent-rest intent",),
        ),
        (
            "PRIM-RHY-003",
            PrimitiveFamily.RHYTHM,
            "realize a declared subdivision or duration cell",
            ("PRIM-RHY-001", "PRIM-RHY-002"),
            ("onset", "duration"),
            (),
        ),
        (
            "PRIM-RHY-004",
            PrimitiveFamily.RHYTHM,
            "enter at the declared metric location",
            ("PRIM-RHY-001",),
            ("onset", "order"),
            (),
        ),
        (
            "PRIM-PAT-001",
            PrimitiveFamily.PATTERN,
            "recognize and reproduce a recurring gesture",
            ("PRIM-AUR-001", "PRIM-KEY-002", "PRIM-RHY-002"),
            ("selection-response", "pitch", "order", "onset"),
            (),
        ),
        (
            "PRIM-HAR-001",
            PrimitiveFamily.HARMONY,
            "construct and release a simultaneous target pitch set",
            ("PRIM-KEY-001",),
            ("chord-set", "onset", "release"),
            ("harmonic naming",),
        ),
        (
            "PRIM-HAR-002",
            PrimitiveFamily.HARMONY,
            "realize a recurring accompaniment pattern",
            ("PRIM-HAR-001", "PRIM-RHY-003", "PRIM-PAT-001"),
            ("pitch", "order", "onset", "continuity"),
            ("harmonic function",),
        ),
        (
            "PRIM-LAY-001",
            PrimitiveFamily.LAYER_CONTROL,
            "perform one declared active layer",
            ("PRIM-READ-002", "PRIM-RHY-002"),
            ("pitch", "order", "onset", "duration"),
            (),
        ),
        (
            "PRIM-COORD-001",
            PrimitiveFamily.COORDINATION,
            "align events from resolved component layers",
            ("PRIM-LAY-001", "PRIM-HAR-001"),
            ("chord-set", "onset"),
            (),
        ),
        (
            "PRIM-COORD-002",
            PrimitiveFamily.COORDINATION,
            "sustain independent simultaneous layer patterns",
            ("PRIM-LAY-001", "PRIM-COORD-001"),
            ("pitch", "order", "onset", "duration", "continuity"),
            ("physical hand identity",),
        ),
        (
            "PRIM-TECH-001",
            PrimitiveFamily.TECHNIQUE,
            "control a written repeated-note gesture",
            ("PRIM-KEY-002", "PRIM-RHY-002"),
            ("pitch", "onset", "duration", "release"),
            ("fingering", "relaxation", "injury risk"),
        ),
        (
            "PRIM-TECH-002",
            PrimitiveFamily.TECHNIQUE,
            "connect a written gesture without unintended interruption",
            ("PRIM-KEY-002", "PRIM-RHY-002"),
            ("continuity", "release"),
            ("legato touch quality",),
        ),
        (
            "PRIM-EXP-001",
            PrimitiveFamily.EXPRESSION,
            "realize a declared dynamic contrast",
            ("PRIM-LAY-001",),
            ("velocity",),
            ("tone quality", "interpretive maturity"),
        ),
        (
            "PRIM-EXP-002",
            PrimitiveFamily.EXPRESSION,
            "apply and release sustain pedal at declared targets",
            ("PRIM-RHY-002",),
            ("pedal", "onset", "release"),
            ("acoustic clarity",),
        ),
        (
            "PRIM-MEM-001",
            PrimitiveFamily.MEMORY,
            "restart accurately from a meaningful landmark",
            ("PRIM-PAT-001",),
            ("pitch", "order", "onset"),
            ("long-term memory",),
        ),
        (
            "PRIM-PRAC-001",
            PrimitiveFamily.SELF_REGULATION,
            "identify a discrepancy and complete a corrective action",
            (),
            ("selection-response", "human-review"),
            ("reflection inferred from retry",),
        ),
    )
    result: list[LearningPrimitive] = []
    for identifier, family, capability, prerequisites, dimensions, unobservable in specs:
        parameter_schema = tuple(
            ParameterDefinition(name, value_type, True)
            for name, value_type in _PARAMETERS[identifier]
        )
        provisional = LearningPrimitive(
            schema_version=CURRICULUM_CONTRACT_VERSION,
            id=identifier,
            semantic_fingerprint="",
            diagnostics=(),
            catalogue_id=PRIMITIVE_CATALOGUE_ID,
            catalogue_version=_CATALOGUE_VERSION,
            family=family,
            capability=capability,
            definition=f"Learner can {capability} under a declared practice condition.",
            parameter_schema=parameter_schema,
            prerequisite_ids=prerequisites,
            observable_dimensions=dimensions,
            unobservable_dimensions=unobservable,
            evidence_contexts=("canonical-passage", "versioned-analysis", "graded-activity"),
            resolution=ArtifactResolution.RESOLVED,
        )
        result.append(replace(provisional, semantic_fingerprint=semantic_fingerprint(provisional)))
    return tuple(result)


def derive_passage_requirements(
    package: CanonicalMusicPackage,
    analysis: ScoreAnalysis,
) -> PassageRequirementSet:
    """Derive title-blind scopes and learner-independent passage requirements."""

    require_valid_package(package)
    require_valid_score_analysis(analysis, package)
    document = _score_document(package, analysis.scope.score_id)
    score = document.content.score
    if len(analysis.scope.part_ids) != 1:
        raise RequirementDerivationError(
            "TMM-SCOPE-FOREIGN-REFERENCE", "9B.1 requires exactly one selected part"
        )
    selected_part = next(
        (item for item in score.parts if item.id == analysis.scope.part_ids[0]), None
    )
    if selected_part is None or not isinstance(selected_part, TemporalPart):
        raise RequirementDerivationError("TMM-SCOPE-FOREIGN-REFERENCE", "part is absent")
    part = selected_part
    measures = tuple(
        item
        for item in part.measures
        if isinstance(item, TemporalMeasure)
        if analysis.scope.start_measure_ordinal
        <= item.ordinal
        <= analysis.scope.end_measure_ordinal
    )
    events = tuple(event for measure in measures for event in measure.events)
    event_universe = tuple(event.id for event in events)
    if not event_universe:
        raise RequirementDerivationError("TMM-SCOPE-INCOMPLETE-PARTITION", "scope has no events")
    anchor_sets: list[CanonicalAnchorSet] = []
    scopes: list[PracticeScopeAssignment] = []
    diagnostics: tuple[CurriculumDiagnostic, ...] = ()

    layers = analysis.layers
    if len(layers) == 1:
        scope, anchors = _scope(
            package,
            analysis,
            part,
            measures,
            event_universe,
            (layers[0],),
            NotationCondition.SINGLE_LAYER,
            (),
        )
        scopes.append(scope)
        anchor_sets.append(anchors)
    elif len(layers) == 2 and len({item.staff_id for item in layers}) == 2:
        staff_order = {staff.id: index for index, staff in enumerate(part.staves)}
        ordered = tuple(
            sorted(layers, key=lambda item: (staff_order.get(item.staff_id, 999), item.id))
        )
        conditions = (NotationCondition.UPPER_LAYER, NotationCondition.LOWER_LAYER)
        for layer, condition in zip(ordered, conditions, strict=True):
            scope, anchors = _scope(
                package,
                analysis,
                part,
                measures,
                event_universe,
                (layer,),
                condition,
                (),
            )
            scopes.append(scope)
            anchor_sets.append(anchors)
        combined, anchors = _scope(
            package,
            analysis,
            part,
            measures,
            event_universe,
            ordered,
            NotationCondition.COMBINED,
            tuple(item.id for item in scopes),
        )
        scopes.append(combined)
        anchor_sets.append(anchors)
    else:
        diagnostic = CurriculumDiagnostic(
            code="TMM-HAND-INTERPRETATION-REQUIRED",
            severity=DiagnosticSeverity.REVIEW,
            outcome=ArtifactResolution.REVIEW_REQUIRED,
            path="practice-scope.layer-groups",
            related_ids=tuple(item.id for item in layers),
        )
        scope, anchors = _scope(
            package,
            analysis,
            part,
            measures,
            event_universe,
            (),
            NotationCondition.COMBINED,
            (),
            resolution=ArtifactResolution.REVIEW_REQUIRED,
            diagnostics=(diagnostic,),
        )
        scopes.append(scope)
        anchor_sets.append(anchors)
        diagnostics = (diagnostic,)

    primitives = learning_primitive_catalogue()
    unlinked_requirements = tuple(
        requirement
        for scope in scopes
        if scope.resolution is ArtifactResolution.RESOLVED
        for requirement in _requirements(scope, primitives, analysis, measures, events)
    )
    requirements = _link_prerequisite_requirements(tuple(scopes), primitives, unlinked_requirements)
    result = PassageRequirementSet(
        analysis_id=analysis.id,
        anchor_sets=tuple(anchor_sets),
        scopes=tuple(scopes),
        primitives=primitives,
        requirements=requirements,
        diagnostics=diagnostics,
    )
    require_valid_requirement_set(result, package, analysis)
    return result


def _link_prerequisite_requirements(
    scopes: tuple[PracticeScopeAssignment, ...],
    primitives: tuple[LearningPrimitive, ...],
    requirements: tuple[PassageSkillRequirement, ...],
) -> tuple[PassageSkillRequirement, ...]:
    """Resolve catalogue dependencies to exact passage requirements.

    A combined scope may depend on matching requirements in each resolved
    component scope.  Missing catalogue dependencies remain catalogue facts;
    they are never fabricated as passage requirements without source evidence.
    """

    primitive_by_id = {item.id: item for item in primitives}
    scope_by_id = {item.id: item for item in scopes}
    rank: dict[str, int] = {}

    def primitive_rank(identifier: str) -> int:
        if identifier not in rank:
            dependencies = primitive_by_id[identifier].prerequisite_ids
            rank[identifier] = (
                0 if not dependencies else 1 + max(primitive_rank(item) for item in dependencies)
            )
        return rank[identifier]

    ordered = sorted(
        requirements,
        key=lambda item: (
            primitive_rank(item.primitive_ref.id),
            item.practice_scope_ref.id,
            item.id,
        ),
    )
    completed_by_old_id: dict[str, PassageSkillRequirement] = {}
    for requirement in ordered:
        primitive = primitive_by_id[requirement.primitive_ref.id]
        scope = scope_by_id[requirement.practice_scope_ref.id]
        dependency_ids: list[str] = []
        for prerequisite_primitive_id in primitive.prerequisite_ids:
            candidates = tuple(
                item
                for item in requirements
                if item.practice_scope_ref.id == scope.id
                and item.primitive_ref.id == prerequisite_primitive_id
            )
            if not candidates and scope.notation_condition is NotationCondition.COMBINED:
                candidates = tuple(
                    item
                    for component_scope_id in scope.component_scope_ids
                    for item in requirements
                    if item.practice_scope_ref.id == component_scope_id
                    and item.primitive_ref.id == prerequisite_primitive_id
                )
            dependency_ids.extend(
                completed_by_old_id[item.id].id
                for item in sorted(candidates, key=lambda value: value.id)
            )
        provisional = replace(
            requirement,
            id="passage-requirement:pending",
            semantic_fingerprint="",
            prerequisite_requirement_ids=tuple(sorted(set(dependency_ids))),
        )
        fingerprint = semantic_fingerprint(provisional)
        completed_by_old_id[requirement.id] = replace(
            provisional,
            id=f"passage-requirement:{fingerprint}",
            semantic_fingerprint=fingerprint,
        )
    return tuple(sorted(completed_by_old_id.values(), key=lambda item: item.id))


def _score_document(package: CanonicalMusicPackage, score_id: str) -> ScoreDocument:
    matches = tuple(
        item
        for item in package.documents
        if isinstance(item, ScoreDocument) and item.id.value == score_id
    )
    if len(matches) != 1 or not isinstance(matches[0].content, CanonicalScoreContent):
        raise RequirementDerivationError(
            "TMM-SCOPE-FOREIGN-REFERENCE", "exactly one complete score is required"
        )
    return matches[0]


def _scope(
    package: CanonicalMusicPackage,
    analysis: ScoreAnalysis,
    part: TemporalPart,
    measures: tuple[TemporalMeasure, ...],
    event_universe: tuple[str, ...],
    layers: tuple[LayerProfile, ...],
    condition: NotationCondition,
    component_scope_ids: tuple[str, ...],
    *,
    resolution: ArtifactResolution = ArtifactResolution.RESOLVED,
    diagnostics: tuple[CurriculumDiagnostic, ...] = (),
) -> tuple[PracticeScopeAssignment, CanonicalAnchorSet]:
    selected_layers = tuple(item for item in analysis.layers if item in layers)
    active = (
        tuple(identifier for item in selected_layers for identifier in item.event_ids)
        if selected_layers
        else event_universe
    )
    active_set = set(active)
    active = tuple(identifier for identifier in event_universe if identifier in active_set)
    inactive = tuple(identifier for identifier in event_universe if identifier not in active_set)
    start = min(item.score_onset for item in measures)
    end = max(item.score_onset + item.extent for item in measures)
    anchors = _anchor_set(package, analysis, part, measures, selected_layers, active, start, end)
    rule = _rule(_SCOPE_RULE_ID)
    groups = tuple(
        PracticeLayerGroup(
            id=derived_id("practice-layer-group", (item.id, item.event_ids)),
            analysis_layer_ids=(item.id,),
            staff_ids=(item.staff_id,),
            voice_ids=(item.voice_id,),
            measure_ids=item.measure_ids,
            event_ids=tuple(
                identifier for identifier in active if identifier in set(item.event_ids)
            ),
        )
        for item in selected_layers
    )
    interpretation = PracticeInterpretation(
        producer=InterpretationProducer.DETERMINISTIC_RULE,
        rule_ref=rule,
        source_evidence_refs=tuple(item.id for item in measures),
        analysis_evidence_refs=tuple(item.id for item in selected_layers),
        rationale_code=(
            "distinct-staff-layer-membership"
            if len(analysis.layers) == 2
            else "single-analysis-layer"
        ),
        uncertainty=None
        if resolution is ArtifactResolution.RESOLVED
        else "human-interpretation-required",
    )
    provisional = PracticeScopeAssignment(
        schema_version=CURRICULUM_CONTRACT_VERSION,
        id="practice-scope:pending",
        semantic_fingerprint="",
        diagnostics=diagnostics,
        score_package_digest=analysis.canonical_digest_sha256,
        score_id=analysis.scope.score_id,
        part_id=part.id,
        score_range=ScoreRange(start, end),
        canonical_anchor_set_id=anchors.id,
        analysis_version=analysis.analysis_version,
        derivation_rule=rule,
        notation_condition=condition,
        layer_groups=groups,
        event_universe_ids=event_universe,
        active_target_ids=active,
        inactive_context_ids=inactive,
        omissions=(),
        component_scope_ids=component_scope_ids,
        execution_assignment=ExecutionAssignment.UNASSIGNED,
        interpretation=interpretation,
        review_state=(
            ReviewState.NOT_REQUIRED
            if resolution is ArtifactResolution.RESOLVED
            else ReviewState.PENDING
        ),
        review_ref=None,
        resolution=resolution,
    )
    fingerprint = semantic_fingerprint(provisional)
    return replace(
        provisional, id=f"practice-scope:{fingerprint}", semantic_fingerprint=fingerprint
    ), anchors


def _anchor_set(
    package: CanonicalMusicPackage,
    analysis: ScoreAnalysis,
    part: TemporalPart,
    measures: tuple[TemporalMeasure, ...],
    layers: tuple[LayerProfile, ...],
    event_ids: tuple[str, ...],
    start: Fraction,
    end: Fraction,
) -> CanonicalAnchorSet:
    anchors = [
        CanonicalAnchor(CanonicalAnchorKind.PACKAGE, package.id.value),
        CanonicalAnchor(CanonicalAnchorKind.SCORE, analysis.scope.score_id),
        CanonicalAnchor(CanonicalAnchorKind.PART, part.id),
    ]
    anchors.extend(CanonicalAnchor(CanonicalAnchorKind.MEASURE, item.id) for item in measures)
    for layer in layers:
        anchors.extend(
            (
                CanonicalAnchor(CanonicalAnchorKind.STAFF, layer.staff_id),
                CanonicalAnchor(CanonicalAnchorKind.VOICE, layer.voice_id),
            )
        )
    anchors.extend(CanonicalAnchor(CanonicalAnchorKind.EVENT, item) for item in event_ids)
    unique = tuple(dict.fromkeys(anchors))
    identifier = derived_id(
        "anchor-set", (package.id.value, analysis.scope.score_id, unique, start, end)
    )
    return CanonicalAnchorSet(
        identifier, package.id.value, analysis.scope.score_id, unique, start, end
    )


def _requirements(
    scope: PracticeScopeAssignment,
    primitives: tuple[LearningPrimitive, ...],
    analysis: ScoreAnalysis,
    measures: tuple[TemporalMeasure, ...],
    events: tuple[TemporalEvent, ...],
) -> tuple[PassageSkillRequirement, ...]:
    primitive_by_id = {item.id: item for item in primitives}
    active_set = set(scope.active_target_ids)
    active = tuple(item for item in events if item.id in active_set)
    pitched = tuple(item for item in active if item.kind == "pitched" and item.pitch is not None)
    result: list[PassageSkillRequirement] = []

    def emit(
        primitive_id: str,
        rule_id: str,
        evidence: tuple[str, ...],
        *,
        analysis_refs: tuple[str, ...] = (),
        parameters: tuple[TypedParameter, ...] = (),
        producer: RequirementProducer = RequirementProducer.DETERMINISTIC_SCORE_RULE,
        role: RequirementRole = RequirementRole.PASSAGE_APPLICATION,
        necessity: RequirementNecessity = RequirementNecessity.REQUIRED,
    ) -> None:
        primitive = primitive_by_id[primitive_id]
        rule = _rule(rule_id)
        ordered_parameters = tuple(sorted(parameters, key=lambda item: item.name))
        provisional = PassageSkillRequirement(
            schema_version=CURRICULUM_CONTRACT_VERSION,
            id="passage-requirement:pending",
            semantic_fingerprint="",
            diagnostics=(),
            primitive_ref=SemanticReference(
                "learning-primitive", primitive.id, primitive.semantic_fingerprint
            ),
            practice_scope_ref=SemanticReference(
                "practice-scope-assignment", scope.id, scope.semantic_fingerprint
            ),
            target_parameters=ordered_parameters,
            canonical_evidence_refs=tuple(dict.fromkeys(evidence)),
            analysis_evidence_refs=tuple(dict.fromkeys(analysis_refs)),
            derivation_rule=rule,
            producer=producer,
            role=role,
            necessity=necessity,
            prerequisite_requirement_ids=(),
            required_dimensions=primitive.observable_dimensions,
            unobservable_dimensions=primitive.unobservable_dimensions,
            resolution=ArtifactResolution.RESOLVED,
            review_ref=None,
        )
        fingerprint = semantic_fingerprint(provisional)
        completed = replace(
            provisional,
            id=f"passage-requirement:{fingerprint}",
            semantic_fingerprint=fingerprint,
        )
        if completed.id not in {item.id for item in result}:
            result.append(completed)

    if pitched:
        pitch_values = tuple(sorted({_pitch_name(item) for item in pitched}))
        params = (TypedParameter("target-pitches", "pitch-list", ",".join(pitch_values)),)
        evidence = tuple(item.id for item in pitched)
        emit(
            "PRIM-KEY-001",
            "REQ-RULE-001",
            evidence,
            parameters=params,
            role=RequirementRole.FOUNDATION,
        )
        emit(
            "PRIM-READ-001",
            "REQ-RULE-001",
            evidence,
            parameters=params,
            role=RequirementRole.FOUNDATION,
        )

    movements: list[str] = []
    movement_events: list[str] = []
    repeated_events: list[str] = []
    for first, second in zip(pitched, pitched[1:], strict=False):
        difference = abs(_semitone(second) - _semitone(first))
        movement = "repeat" if difference == 0 else "step" if difference <= 2 else "leap"
        movements.append(f"{first.id}>{second.id}:{movement}")
        movement_events.extend((first.id, second.id))
        if difference == 0:
            repeated_events.extend((first.id, second.id))
    if movements:
        emit(
            "PRIM-KEY-002",
            "REQ-RULE-002",
            tuple(dict.fromkeys(movement_events)),
            parameters=(
                TypedParameter("movement-pairs", "ordered-pair-list", "|".join(movements)),
            ),
            role=RequirementRole.FOUNDATION,
        )

    meter_fact = next(
        (item for item in analysis.facts if item.kind is AnalysisFactKind.METER_VOCABULARY), None
    )
    if active and meter_fact is not None:
        durations = ",".join(sorted({str(item.duration) for item in active}))
        rhythm_parameters = (
            TypedParameter("duration-vocabulary", "fraction-list", durations),
            TypedParameter("meter", "string", meter_fact.value),
        )
        evidence = tuple(item.id for item in active)
        emit(
            "PRIM-RHY-001",
            "REQ-RULE-003",
            evidence,
            analysis_refs=(meter_fact.id,),
            parameters=rhythm_parameters,
            role=RequirementRole.FOUNDATION,
        )
        emit(
            "PRIM-RHY-002",
            "REQ-RULE-003",
            evidence,
            analysis_refs=(meter_fact.id,),
            parameters=rhythm_parameters,
        )

    subdivision = tuple(item for item in active if item.dots or item.time_modification is not None)
    if subdivision:
        emit(
            "PRIM-RHY-003",
            "REQ-RULE-004",
            tuple(item.id for item in subdivision),
            parameters=(
                TypedParameter(
                    "rhythm-cell-events",
                    "stable-id-list",
                    ",".join(item.id for item in subdivision),
                ),
            ),
        )

    first_active = active[0] if active else None
    measure_by_event = {event.id: measure for measure in measures for event in measure.events}
    if first_active is not None and first_active.onset > 0:
        emit(
            "PRIM-RHY-004",
            "REQ-RULE-005",
            (measure_by_event[first_active.id].id, first_active.id),
            parameters=(TypedParameter("metric-entry", "fraction", str(first_active.onset)),),
        )

    for group in analysis.repetitions:
        group_evidence = tuple(item for item in group.evidence_event_ids if item in active_set)
        if group_evidence:
            emit(
                "PRIM-PAT-001",
                "REQ-RULE-006",
                group_evidence,
                analysis_refs=(group.id,),
                parameters=(TypedParameter("pattern-id", "stable-id", group.id),),
            )

    chord_events = tuple(item for item in pitched if item.chord_id is not None)
    if chord_events:
        emit(
            "PRIM-HAR-001",
            "REQ-RULE-007",
            tuple(item.id for item in chord_events),
            parameters=(
                TypedParameter(
                    "chord-events", "stable-id-list", ",".join(item.id for item in chord_events)
                ),
            ),
        )
        if any(
            set(group.evidence_event_ids) & {item.id for item in chord_events}
            for group in analysis.repetitions
        ):
            emit(
                "PRIM-HAR-002",
                "REQ-RULE-008",
                tuple(item.id for item in chord_events),
                analysis_refs=tuple(
                    group.id
                    for group in analysis.repetitions
                    if set(group.evidence_event_ids) & {item.id for item in chord_events}
                ),
                parameters=(
                    TypedParameter(
                        "accompaniment-events",
                        "stable-id-list",
                        ",".join(item.id for item in chord_events),
                    ),
                ),
            )

    if scope.notation_condition is not NotationCondition.COMBINED:
        params = (TypedParameter("practice-scope", "stable-id", scope.id),)
        emit("PRIM-READ-002", "REQ-RULE-009", scope.active_target_ids, parameters=params)
        emit(
            "PRIM-LAY-001",
            "REQ-RULE-009",
            scope.active_target_ids,
            parameters=params,
            role=RequirementRole.LAYER_INTEGRATION,
        )
    elif len(scope.layer_groups) >= 2:
        layer_by_event = {
            event_id: group.id for group in scope.layer_groups for event_id in group.event_ids
        }
        at_onset: dict[Fraction, set[str]] = {}
        onset_events: dict[Fraction, list[str]] = {}
        for event in active:
            if event.kind != "pitched":
                continue
            at_onset.setdefault(event.score_onset, set()).add(layer_by_event[event.id])
            onset_events.setdefault(event.score_onset, []).append(event.id)
        simultaneous = tuple(
            identifier
            for onset, identifiers in sorted(onset_events.items())
            if len(at_onset[onset]) > 1
            for identifier in identifiers
        )
        if simultaneous:
            params = (
                TypedParameter(
                    "component-scopes", "stable-id-list", ",".join(scope.component_scope_ids)
                ),
            )
            emit(
                "PRIM-COORD-001",
                "REQ-RULE-010",
                simultaneous,
                parameters=params,
                role=RequirementRole.LAYER_INTEGRATION,
            )
            if len({event.score_onset for event in active if event.id in simultaneous}) > 1:
                emit(
                    "PRIM-COORD-002",
                    "REQ-RULE-011",
                    simultaneous,
                    parameters=params,
                    role=RequirementRole.LAYER_INTEGRATION,
                )

    if repeated_events:
        emit(
            "PRIM-TECH-001",
            "REQ-RULE-012",
            tuple(dict.fromkeys(repeated_events)),
            parameters=(
                TypedParameter(
                    "repeated-note-events",
                    "stable-id-list",
                    ",".join(dict.fromkeys(repeated_events)),
                ),
            ),
        )

    start_boundary = next(
        (
            item
            for item in analysis.boundaries
            if item.score_onset == scope.score_range.start
            and BoundaryReason.SCOPE_START in item.reasons
        ),
        None,
    )
    if start_boundary is not None:
        evidence = tuple(dict.fromkeys((*start_boundary.measure_ids, *start_boundary.evidence_ids)))
        emit(
            "PRIM-MEM-001",
            "REQ-RULE-015",
            evidence,
            analysis_refs=(start_boundary.id,),
            parameters=(TypedParameter("start-landmark", "stable-id", start_boundary.id),),
            role=RequirementRole.RECOVERY,
            necessity=RequirementNecessity.SUPPORTING,
        )

    if active:
        params = (TypedParameter("return-scope", "stable-id", scope.id),)
        emit(
            "PRIM-AUR-001",
            "REQ-RULE-016",
            scope.active_target_ids,
            parameters=params,
            producer=RequirementProducer.METHODOLOGY_RULE,
            role=RequirementRole.FOUNDATION,
            necessity=RequirementNecessity.SUPPORTING,
        )
        emit(
            "PRIM-AUR-002",
            "REQ-RULE-016",
            scope.active_target_ids,
            parameters=params,
            producer=RequirementProducer.METHODOLOGY_RULE,
            role=RequirementRole.PASSAGE_APPLICATION,
            necessity=RequirementNecessity.SUPPORTING,
        )
    return tuple(sorted(result, key=lambda item: item.id))


def _rule(identifier: str) -> RuleReference:
    fingerprint = semantic_fingerprint((identifier, REQUIREMENT_RULE_VERSION))
    return RuleReference(identifier, REQUIREMENT_RULE_VERSION, fingerprint)


def _semitone(event: TemporalEvent) -> Fraction:
    if event.pitch is None:
        raise ValueError("pitched event has no pitch")
    base = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}
    return Fraction(12 * (event.pitch.octave + 1) + base[event.pitch.step]) + event.pitch.alter


def _pitch_name(event: TemporalEvent) -> str:
    if event.pitch is None:
        raise ValueError("pitched event has no pitch")
    alteration = "" if event.pitch.alter == 0 else f"{event.pitch.alter:+}"
    return f"{event.pitch.step}{alteration}{event.pitch.octave}"
