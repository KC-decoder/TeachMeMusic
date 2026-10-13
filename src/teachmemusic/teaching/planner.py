"""Deterministic beginner lesson planning from canonical analysis."""

from __future__ import annotations

import hashlib
from collections import defaultdict
from dataclasses import dataclass, replace
from fractions import Fraction

from teachmemusic._contract_codec import contract_to_json
from teachmemusic.analysis import (
    ANALYSIS_VERSION,
    BoundaryReason,
    ScoreAnalysis,
    require_valid_score_analysis,
    score_analysis_to_json,
)
from teachmemusic.performance import ObservationDimension, ObservationSource
from teachmemusic.performance.validation import is_stable_id
from teachmemusic.score import (
    CanonicalMusicPackage,
    CanonicalScoreContent,
    ScoreDocument,
    require_valid_package,
)
from teachmemusic.score.v2.temporal import (
    TemporalEvent,
    TemporalMeasure,
    TemporalPart,
    TemporalScore,
)

from .contracts import (
    CanonicalAnchor,
    CanonicalAnchorKind,
    CanonicalAnchorSet,
    DemandDimension,
    EvidenceContext,
    EvidenceRequirement,
    EvidenceState,
    Exercise,
    ExpectedFact,
    LearnerContextSnapshot,
    LearnerTrack,
    LessonNode,
    LessonNodeKind,
    LessonPlan,
    PracticeMode,
    SkillDomain,
    SupportState,
    SyntheticExerciseMaterial,
    SyntheticExpectedEvent,
    TaskDemand,
)
from .validation import require_valid_lesson_plan

PLANNER_VERSION = "deterministic-beginner-planner/0.1.2"
BEGINNER_PLAN_POLICY_VERSION = "beginner-plan-policy/0.1.2"
_DEFAULT_START_TEMPO_PERCENT = 70


class PlannerError(ValueError):
    """Raised when a lesson cannot be planned without inventing evidence."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(f"{code}: {message}")


@dataclass(frozen=True, slots=True)
class _Scope:
    package: CanonicalMusicPackage
    score_id: str
    score: TemporalScore
    parts: tuple[TemporalPart, ...]
    measures_by_ordinal: dict[int, tuple[TemporalMeasure, ...]]
    analysis: ScoreAnalysis
    token: str
    source_tempo: Fraction | None


@dataclass(frozen=True, slots=True)
class _Segment:
    ordinals: tuple[int, ...]
    boundary_reason: str


@dataclass(frozen=True, slots=True)
class _PlannedExercise:
    exercise: Exercise
    kind: LessonNodeKind


def generate_beginner_lesson_plan(
    package: CanonicalMusicPackage,
    analysis: ScoreAnalysis,
    learner_context: LearnerContextSnapshot,
    *,
    run_id: str,
    generated_at_utc: str,
) -> LessonPlan:
    """Generate one untouched, deterministic Beginner plan.

    ``run_id`` and ``generated_at_utc`` are caller-owned provenance. Reusing
    them with identical inputs produces byte-identical plan JSON.
    """

    require_valid_package(package)
    require_valid_score_analysis(analysis, package)
    if learner_context.track is not LearnerTrack.BEGINNER:
        raise PlannerError("PLANNER_TRACK", "only the approved Beginner policy is implemented")
    if not is_stable_id(learner_context.id):
        raise PlannerError("PLANNER_LEARNER_CONTEXT", "learner context ID is not stable")
    if not is_stable_id(run_id):
        raise PlannerError("PLANNER_RUN", "run ID is not stable")
    if not generated_at_utc.strip():
        raise PlannerError("PLANNER_TIMESTAMP", "generation timestamp is required")

    scope = _build_scope(package, analysis, learner_context)
    groups = _candidate_groups(scope)
    segments_by_group = tuple(_segments_for_group(scope, group) for group in groups)
    all_segments = tuple(segment for group in segments_by_group for segment in group)
    if not all_segments:
        raise PlannerError("PLANNER_SEGMENTS", "analysis produced no teachable measure segment")

    core: list[_PlannedExercise] = []
    whole_ordinals = tuple(sorted(scope.measures_by_ordinal))
    core.append(
        _PlannedExercise(
            _canonical_exercise(
                scope,
                label="orientation",
                ordinals=whole_ordinals,
                primary=SkillDomain.STRUCTURE,
                secondary=(SkillDomain.AURAL, SkillDomain.READING),
                modes=(PracticeMode.LISTEN,),
                support=_support(scope, "listen"),
                dimensions=(ObservationDimension.SELF_REPORT,),
                evidence_state=EvidenceState.EXPOSED,
                evidence_context=EvidenceContext.ACQUISITION,
                boundary_reason=(
                    "Orient to the complete selected score before isolated practice; "
                    "this is exposure, not performance evidence."
                ),
            ),
            LessonNodeKind.EXERCISE,
        )
    )
    first_segment = all_segments[0]
    first_measure = (first_segment.ordinals[0],)
    core.append(
        _PlannedExercise(
            _canonical_exercise(
                scope,
                label="first-measure-rehearsal",
                ordinals=first_measure,
                primary=SkillDomain.PITCH,
                secondary=(SkillDomain.READING, SkillDomain.AURAL),
                modes=(PracticeMode.FOLLOW_PITCH,),
                support=_support(scope, "follow"),
                dimensions=(ObservationDimension.PITCH, ObservationDimension.ORDER),
                evidence_state=EvidenceState.STABLE_SUPPORTED,
                evidence_context=EvidenceContext.ACQUISITION,
                boundary_reason=(
                    "Rehearse only the first measure after whole-score orientation so "
                    "the learner can verify the complete supported performance loop."
                ),
            ),
            LessonNodeKind.EXERCISE,
        )
    )

    global_segment_index = 0
    for group_segments in segments_by_group:
        group_start = group_segments[0].ordinals[0]
        group_end = group_segments[-1].ordinals[-1]
        integrated_end: int | None = None
        for local_index, segment in enumerate(group_segments):
            if global_segment_index == 0:
                core.append(
                    _PlannedExercise(
                        _canonical_exercise(
                            scope,
                            label="first-pitch-map",
                            ordinals=segment.ordinals,
                            primary=SkillDomain.PITCH,
                            secondary=(SkillDomain.READING,),
                            modes=(PracticeMode.FOLLOW_PITCH,),
                            support=_support(scope, "follow"),
                            dimensions=(ObservationDimension.PITCH, ObservationDimension.ORDER),
                            evidence_state=EvidenceState.STABLE_SUPPORTED,
                            evidence_context=EvidenceContext.ACQUISITION,
                            boundary_reason=segment.boundary_reason,
                        ),
                        LessonNodeKind.EXERCISE,
                    )
                )
                core.append(
                    _PlannedExercise(
                        _canonical_exercise(
                            scope,
                            label="first-rhythm-map",
                            ordinals=segment.ordinals,
                            primary=SkillDomain.RHYTHM,
                            secondary=(SkillDomain.PITCH, SkillDomain.CONTINUITY),
                            modes=(PracticeMode.PULSE_GUIDED,),
                            support=_support(scope, "guided-slow"),
                            dimensions=(
                                ObservationDimension.PITCH,
                                ObservationDimension.ONSET,
                                ObservationDimension.DURATION,
                            ),
                            evidence_state=EvidenceState.HUMAN_REVIEWED,
                            evidence_context=EvidenceContext.ACQUISITION,
                            boundary_reason=(
                                f"{segment.boundary_reason} Pitch mapping precedes "
                                "human-reviewed pulse and duration work."
                            ),
                        ),
                        LessonNodeKind.EXERCISE,
                    )
                )
            else:
                core.append(
                    _PlannedExercise(
                        _canonical_exercise(
                            scope,
                            label=f"acquisition-{global_segment_index + 1}",
                            ordinals=segment.ordinals,
                            primary=SkillDomain.PITCH,
                            secondary=(SkillDomain.RHYTHM, SkillDomain.CONTINUITY),
                            modes=(
                                PracticeMode.PULSE_GUIDED,
                                PracticeMode.SUPPORTED_PERFORMANCE,
                            ),
                            support=_support(scope, "guided-reduced"),
                            dimensions=(
                                ObservationDimension.PITCH,
                                ObservationDimension.ORDER,
                                ObservationDimension.ONSET,
                            ),
                            evidence_state=EvidenceState.STABLE_SUPPORTED,
                            evidence_context=EvidenceContext.ACQUISITION,
                            boundary_reason=segment.boundary_reason,
                        ),
                        LessonNodeKind.EXERCISE,
                    )
                )
            global_segment_index += 1
            if local_index == 1:
                integrated_end = segment.ordinals[-1]
                core.append(
                    _integration_exercise(scope, group_start, integrated_end, "pair-integration")
                )
            elif local_index > 1:
                integrated_end = segment.ordinals[-1]
                core.append(
                    _integration_exercise(
                        scope, group_start, integrated_end, "extended-integration"
                    )
                )

        if len(group_segments) == 1:
            integrated_end = group_end

        completed_groups = len(
            [group for group in segments_by_group if group[-1].ordinals[-1] <= group_end]
        )
        if completed_groups % 2 == 0:
            pair_start = groups[completed_groups - 2][0]
            pair_end = groups[completed_groups - 1][-1]
            core.append(_integration_exercise(scope, pair_start, pair_end, "section-integration"))

    if core[-1].exercise.anchor_set is None or not _covers_ordinals(
        core[-1].exercise.anchor_set,
        scope,
        whole_ordinals,
    ):
        core.append(
            _integration_exercise(
                scope,
                whole_ordinals[0],
                whole_ordinals[-1],
                "whole-score-independence",
                independent=True,
            )
        )
    else:
        current = core[-1]
        core[-1] = _PlannedExercise(
            replace(
                current.exercise,
                practice_modes=(PracticeMode.INDEPENDENT_PERFORMANCE,),
                initial_support=_support(scope, "independent"),
                exit_evidence=_requirements(
                    current.exercise.id,
                    (ObservationDimension.PITCH, ObservationDimension.CONTINUITY),
                    EvidenceState.INDEPENDENT_IN_SESSION,
                    EvidenceContext.INDEPENDENT,
                ),
            ),
            LessonNodeKind.INTEGRATION,
        )

    whole_exercise = core[-1].exercise
    short_retention = _retention_exercise(scope, whole_ordinals, "short-retention")
    long_retention = _retention_exercise(scope, whole_ordinals, "next-session-retention")
    transfers = _transfer_exercises(scope)

    planned = [*core, short_retention, long_retention, *transfers]
    node_ids = tuple(_id("lesson-node", scope.token, str(index)) for index in range(len(planned)))
    core_count = len(core)
    short_index = core_count
    long_index = core_count + 1
    transfer_start = core_count + 2
    edges: dict[int, list[int]] = defaultdict(list)
    for index in range(core_count - 1):
        edges[index].append(index + 1)
    edges[core_count - 1].extend((short_index, long_index))
    if transfers:
        edges[short_index].append(transfer_start)
        for index in range(transfer_start, len(planned) - 1):
            edges[index].append(index + 1)
    prerequisites: dict[int, list[int]] = defaultdict(list)
    for source, targets in edges.items():
        for target in targets:
            prerequisites[target].append(source)

    nodes = tuple(
        LessonNode(
            id=node_ids[index],
            kind=item.kind,
            exercise_id=item.exercise.id,
            prerequisites=tuple(node_ids[value] for value in prerequisites[index]),
            successors=tuple(node_ids[value] for value in edges[index]),
        )
        for index, item in enumerate(planned)
    )
    exercises = [item.exercise for item in planned]
    for index, exercise in enumerate(exercises):
        integration_successors = tuple(
            node_ids[target]
            for target in edges[index]
            if planned[target].kind is LessonNodeKind.INTEGRATION
        )
        retention_successors = tuple(
            node_ids[target]
            for target in edges[index]
            if planned[target].kind is LessonNodeKind.RETENTION
        )
        transfer_successors = tuple(
            node_ids[target]
            for target in edges[index]
            if planned[target].kind is LessonNodeKind.TRANSFER
        )
        exercises[index] = replace(
            exercise,
            integration_successors=integration_successors,
            retention_successors=retention_successors,
            transfer_successors=transfer_successors,
        )

    diagnostics = [
        f"analysis-version={ANALYSIS_VERSION}",
        "untouched automatic plan; human audit not yet applied",
        "candidate chunks use terminal rests, bounded two-measure windows, and "
        "same-rhythm pitch-change isolation",
        "timing exits require human review until Task 8B.7 validates alignment tolerances",
        "synthetic transfer events are explicitly outside the canonical namespace",
    ]
    fallback_count = sum(boundary.fallback for boundary in analysis.boundaries)
    if fallback_count:
        diagnostics.append(f"candidate-boundary-fallback-count={fallback_count}")
    if any(demand.level is not None and demand.level >= 4 for demand in analysis.demands):
        diagnostics.append("high structural demand present; pedagogical suitability requires audit")

    target_skills = [
        SkillDomain.AURAL,
        SkillDomain.READING,
        SkillDomain.PITCH,
        SkillDomain.RHYTHM,
        SkillDomain.CONTINUITY,
        SkillDomain.STRUCTURE,
    ]
    if analysis.texture.max_active_layers > 1:
        target_skills.insert(4, SkillDomain.COORDINATION)
    plan = LessonPlan(
        id=_id("lesson-plan", scope.token),
        run_id=run_id,
        input_digest_sha256=analysis.canonical_digest_sha256,
        generated_at_utc=generated_at_utc,
        planner_version=PLANNER_VERSION,
        policy_version=BEGINNER_PLAN_POLICY_VERSION,
        track=LearnerTrack.BEGINNER,
        target_skills=tuple(target_skills),
        exercises=tuple(exercises),
        nodes=nodes,
        root_node_ids=(node_ids[0],),
        diagnostics=tuple(diagnostics),
    )
    require_valid_lesson_plan(plan, package)
    if whole_exercise.id not in {exercise.id for exercise in plan.exercises}:
        raise PlannerError("PLANNER_INTERNAL", "whole-score exercise was lost")
    return plan


def _build_scope(
    package: CanonicalMusicPackage,
    analysis: ScoreAnalysis,
    learner_context: LearnerContextSnapshot,
) -> _Scope:
    document = next(
        (
            item
            for item in package.documents
            if isinstance(item, ScoreDocument) and item.id.value == analysis.scope.score_id
        ),
        None,
    )
    if document is None or not isinstance(document.content, CanonicalScoreContent):
        raise PlannerError("PLANNER_SCORE", "analysis score is unavailable or incomplete")
    score = document.content.score
    by_id = {part.id: part for part in score.parts}
    try:
        parts = tuple(by_id[identifier] for identifier in analysis.scope.part_ids)
    except KeyError as error:
        raise PlannerError("PLANNER_PART", f"analysis part is missing: {error.args[0]}") from error
    measures_by_ordinal: dict[int, tuple[TemporalMeasure, ...]] = {}
    ordinals = sorted(
        {
            measure.ordinal
            for part in parts
            for measure in part.measures
            if analysis.scope.start_measure_ordinal
            <= measure.ordinal
            <= analysis.scope.end_measure_ordinal
        }
    )
    for ordinal in ordinals:
        measures_by_ordinal[ordinal] = tuple(
            measure for part in parts for measure in part.measures if measure.ordinal == ordinal
        )
    seed = (
        score_analysis_to_json(analysis)
        + contract_to_json(learner_context)
        + PLANNER_VERSION
        + BEGINNER_PLAN_POLICY_VERSION
    )
    token = hashlib.sha256(seed.encode()).hexdigest()[:24]
    tempos = tuple(
        sound.tempo
        for part in parts
        for measure in part.measures
        if measure.ordinal <= analysis.scope.end_measure_ordinal
        for sound in measure.sounds
        if sound.tempo is not None
    )
    return _Scope(
        package=package,
        score_id=document.id.value,
        score=score,
        parts=parts,
        measures_by_ordinal=measures_by_ordinal,
        analysis=analysis,
        token=token,
        source_tempo=tempos[0] if tempos else None,
    )


def _candidate_groups(scope: _Scope) -> tuple[tuple[int, ...], ...]:
    boundary_by_ordinal = {
        min(_measure_ordinal(scope, identifier) for identifier in boundary.measure_ids): boundary
        for boundary in scope.analysis.boundaries
        if BoundaryReason.SCOPE_END not in boundary.reasons
    }
    groups: list[list[int]] = []
    current: list[int] = []
    for ordinal in sorted(scope.measures_by_ordinal):
        boundary = boundary_by_ordinal.get(ordinal)
        if (
            current
            and boundary is not None
            and BoundaryReason.PRECEDING_TERMINAL_REST in boundary.reasons
        ):
            groups.append(current)
            current = []
        current.append(ordinal)
    if current:
        groups.append(current)
    return tuple(tuple(group) for group in groups)


def _segments_for_group(scope: _Scope, group: tuple[int, ...]) -> tuple[_Segment, ...]:
    result: list[_Segment] = []
    for index in range(0, len(group), 2):
        candidate = group[index : index + 2]
        if len(candidate) == 2 and _same_rhythm_different_pitch(scope, *candidate):
            for ordinal in candidate:
                result.append(_segment(scope, (ordinal,)))
        else:
            result.append(_segment(scope, candidate))
    return tuple(result)


def _segment(scope: _Scope, ordinals: tuple[int, ...]) -> _Segment:
    start = ordinals[0]
    boundary = next(
        (
            item
            for item in scope.analysis.boundaries
            if item.measure_ids
            and start in {_measure_ordinal(scope, identifier) for identifier in item.measure_ids}
        ),
        None,
    )
    reasons = (
        ", ".join(reason.value for reason in boundary.reasons)
        if boundary is not None
        else "bounded measure fallback"
    )
    boundary_reason = f"Candidate range selected from {reasons}; "
    boundary_reason += "policy window is at most two measures."
    return _Segment(ordinals=ordinals, boundary_reason=boundary_reason)


def _same_rhythm_different_pitch(scope: _Scope, first: int, second: int) -> bool:
    first_events = _events(scope, (first,))
    second_events = _events(scope, (second,))
    first_rhythm = tuple(
        (event.kind, event.onset, event.duration, event.staff, event.voice)
        for event in first_events
    )
    second_rhythm = tuple(
        (event.kind, event.onset, event.duration, event.staff, event.voice)
        for event in second_events
    )
    first_pitch = tuple(_written_midi(event) for event in first_events if event.pitch is not None)
    second_pitch = tuple(_written_midi(event) for event in second_events if event.pitch is not None)
    return first_rhythm == second_rhythm and first_pitch != second_pitch


def _integration_exercise(
    scope: _Scope,
    start: int,
    end: int,
    label: str,
    *,
    independent: bool = False,
) -> _PlannedExercise:
    return _PlannedExercise(
        _canonical_exercise(
            scope,
            label=label,
            ordinals=tuple(range(start, end + 1)),
            primary=SkillDomain.CONTINUITY,
            secondary=(SkillDomain.PITCH, SkillDomain.RHYTHM, SkillDomain.STRUCTURE),
            modes=(
                PracticeMode.INDEPENDENT_PERFORMANCE
                if independent
                else PracticeMode.SUPPORTED_PERFORMANCE,
            ),
            support=_support(scope, "independent" if independent else "guided-reduced"),
            dimensions=(
                ObservationDimension.PITCH,
                ObservationDimension.ONSET,
                ObservationDimension.CONTINUITY,
            ),
            evidence_state=(
                EvidenceState.INDEPENDENT_IN_SESSION
                if independent
                else EvidenceState.STABLE_SUPPORTED
            ),
            evidence_context=(
                EvidenceContext.INDEPENDENT if independent else EvidenceContext.INTEGRATION
            ),
            boundary_reason=(
                "Reconnect adjacent canonical chunks and preserve transitions; "
                "isolated success is not whole-passage evidence."
            ),
        ),
        LessonNodeKind.INTEGRATION,
    )


def _retention_exercise(
    scope: _Scope,
    ordinals: tuple[int, ...],
    label: str,
) -> _PlannedExercise:
    return _PlannedExercise(
        _canonical_exercise(
            scope,
            label=label,
            ordinals=ordinals,
            primary=SkillDomain.MEMORY,
            secondary=(SkillDomain.PITCH, SkillDomain.RHYTHM, SkillDomain.CONTINUITY),
            modes=(PracticeMode.RETENTION,),
            support=_support(scope, "retention"),
            dimensions=(
                ObservationDimension.PITCH,
                ObservationDimension.ONSET,
                ObservationDimension.CONTINUITY,
            ),
            evidence_state=EvidenceState.RETAINED,
            evidence_context=EvidenceContext.RETENTION,
            boundary_reason=(
                "Revisit the complete canonical range after a declared delay before "
                "renewed demonstration or correction."
            ),
        ),
        LessonNodeKind.RETENTION,
    )


def _transfer_exercises(scope: _Scope) -> tuple[_PlannedExercise, ...]:
    pitched = tuple(
        event for event in _events(scope, tuple(scope.measures_by_ordinal)) if event.pitch
    )
    by_midi: dict[int, TemporalEvent] = {}
    for event in pitched:
        midi = _written_midi(event)
        if midi.denominator == 1 and 0 <= midi <= 127:
            by_midi.setdefault(int(midi), event)
    notes = sorted(by_midi)
    if not notes:
        return ()
    result: list[_PlannedExercise] = []
    if len(notes) >= 3:
        selected: tuple[int, ...] = (notes[1], notes[0], notes[1])
        result.append(
            _synthetic_transfer_exercise(
                scope,
                "aural-contour-transfer",
                selected,
                tuple(Fraction(index) for index in range(3)),
                SkillDomain.AURAL,
                (ObservationDimension.PITCH, ObservationDimension.ORDER),
                by_midi,
                "Create a new three-note contour from already encountered canonical pitches.",
                _support(scope, "ear"),
            )
        )
    selected = (notes[-1],) * 4
    result.append(
        _synthetic_transfer_exercise(
            scope,
            "pulse-transfer",
            selected,
            tuple(Fraction(index) for index in range(4)),
            SkillDomain.RHYTHM,
            (ObservationDimension.PITCH, ObservationDimension.ONSET),
            by_midi,
            "Apply an encountered pitch to an untrained four-quarter pulse pattern.",
            _support(scope, "guided-reduced"),
        )
    )
    return tuple(result)


def _synthetic_transfer_exercise(
    scope: _Scope,
    label: str,
    notes: tuple[int, ...],
    onsets: tuple[Fraction, ...],
    primary: SkillDomain,
    dimensions: tuple[ObservationDimension, ...],
    by_midi: dict[int, TemporalEvent],
    rationale: str,
    support: SupportState,
) -> _PlannedExercise:
    token = _token(scope.token, label)
    source_ids = tuple(dict.fromkeys(by_midi[note].id for note in notes))
    events = tuple(
        SyntheticExpectedEvent(
            id=f"synthetic-event:{token}:{index}",
            onset_quarters=onsets[index],
            duration_quarters=Fraction(1),
            midi_note=note,
            source_canonical_ids=(by_midi[note].id,),
        )
        for index, note in enumerate(notes)
    )
    material = SyntheticExerciseMaterial(
        id=f"synthetic-material:{token}",
        source_canonical_ids=source_ids,
        events=events,
        rationale=rationale,
    )
    exercise_id = f"exercise:{token}"
    facts = tuple(
        ExpectedFact(
            id=f"expected-fact:{token}:{dimension.value}",
            dimension=dimension,
            canonical_ids=(),
            synthetic_event_ids=tuple(event.id for event in events),
            expected_value=(
                "midi-sequence:" + ",".join(map(str, notes))
                if dimension in {ObservationDimension.PITCH, ObservationDimension.ORDER}
                else "onsets-quarter:" + ",".join(map(str, onsets))
            ),
            observable_sources=(ObservationSource.MIDI,),
        )
        for dimension in dimensions
    )
    return _PlannedExercise(
        Exercise(
            id=exercise_id,
            anchor_set=None,
            synthetic_material=material,
            boundary_reason=(
                "Explicit synthetic transfer probe; events are not canonical score content. "
                + rationale
            ),
            layer_scope=(),
            primary_skill=primary,
            secondary_skills=(SkillDomain.PITCH,) if primary is not SkillDomain.PITCH else (),
            task_demands=(
                TaskDemand(
                    id=f"task-demand:{token}:transfer",
                    dimension=(
                        DemandDimension.AURAL
                        if primary is SkillDomain.AURAL
                        else DemandDimension.RHYTHMIC_DENSITY
                    ),
                    level=1,
                    evidence_canonical_ids=source_ids,
                    rationale=rationale,
                    uncertainty=(
                        "Transfer difficulty is a policy hypothesis pending learner evidence."
                    ),
                ),
            ),
            expected_facts=facts,
            practice_modes=(PracticeMode.TRANSFER,),
            initial_support=replace(support, id=f"support:{token}"),
            exit_evidence=_requirements(
                exercise_id,
                dimensions,
                EvidenceState.TRANSFERRED,
                EvidenceContext.TRANSFER,
            ),
        ),
        LessonNodeKind.TRANSFER,
    )


def _canonical_exercise(
    scope: _Scope,
    *,
    label: str,
    ordinals: tuple[int, ...],
    primary: SkillDomain,
    secondary: tuple[SkillDomain, ...],
    modes: tuple[PracticeMode, ...],
    support: SupportState,
    dimensions: tuple[ObservationDimension, ...],
    evidence_state: EvidenceState,
    evidence_context: EvidenceContext,
    boundary_reason: str,
    pitched_event_limit: int | None = None,
) -> Exercise:
    token = _token(scope.token, label, ",".join(map(str, ordinals)))
    measures = tuple(
        measure for ordinal in ordinals for measure in scope.measures_by_ordinal[ordinal]
    )
    events = tuple(
        sorted(
            (event for measure in measures for event in measure.events),
            key=lambda event: (event.score_onset, event.source_order, event.id),
        )
    )
    if pitched_event_limit is not None:
        selected_pitched = tuple(event for event in events if event.pitch is not None)[
            :pitched_event_limit
        ]
        selected_ids = {event.id for event in selected_pitched}
        events = tuple(event for event in events if event.id in selected_ids)
    anchor_set = _anchor_set(scope, token, measures, events)
    layer_scope = tuple(
        layer.id
        for layer in scope.analysis.layers
        if set(layer.event_ids) & {event.id for event in events}
    )
    facts = _expected_facts(token, events, measures, dimensions)
    return Exercise(
        id=f"exercise:{token}",
        anchor_set=anchor_set,
        boundary_reason=boundary_reason,
        layer_scope=layer_scope,
        primary_skill=primary,
        secondary_skills=secondary,
        task_demands=_task_demands(scope, token, anchor_set),
        expected_facts=facts,
        practice_modes=modes,
        initial_support=replace(support, id=f"support:{token}"),
        exit_evidence=_requirements(
            f"exercise:{token}",
            tuple(fact.dimension for fact in facts),
            evidence_state,
            evidence_context,
        ),
    )


def _anchor_set(
    scope: _Scope,
    token: str,
    measures: tuple[TemporalMeasure, ...],
    events: tuple[TemporalEvent, ...],
) -> CanonicalAnchorSet:
    event_ids = {event.id for event in events}
    measure_ids = {measure.id for measure in measures}
    relevant_parts = tuple(
        part for part in scope.parts if any(measure.id in measure_ids for measure in part.measures)
    )
    anchors: list[CanonicalAnchor] = [
        CanonicalAnchor(CanonicalAnchorKind.PACKAGE, scope.package.id.value),
        CanonicalAnchor(CanonicalAnchorKind.SCORE, scope.score_id),
    ]
    for part in relevant_parts:
        anchors.append(CanonicalAnchor(CanonicalAnchorKind.PART, part.id))
        source_staffs = {
            event.staff
            for measure in part.measures
            for event in measure.events
            if event.id in event_ids
        }
        source_voices = {
            event.voice
            for measure in part.measures
            for event in measure.events
            if event.id in event_ids
        }
        anchors.extend(
            CanonicalAnchor(CanonicalAnchorKind.STAFF, staff.id)
            for staff in part.staves
            if staff.source_number in source_staffs
        )
        anchors.extend(
            CanonicalAnchor(CanonicalAnchorKind.VOICE, voice.id)
            for voice in part.voices
            if voice.source_id in source_voices
        )
    anchors.extend(
        CanonicalAnchor(CanonicalAnchorKind.MEASURE, measure.id)
        for measure in sorted(measures, key=lambda item: (item.ordinal, item.id))
    )
    anchors.extend(CanonicalAnchor(CanonicalAnchorKind.EVENT, event.id) for event in events)
    anchors.extend(
        CanonicalAnchor(CanonicalAnchorKind.CHORD, chord_id)
        for chord_id in dict.fromkeys(
            event.chord_id for event in events if event.chord_id is not None
        )
    )
    unique: dict[str, CanonicalAnchor] = {}
    for anchor in anchors:
        unique.setdefault(anchor.canonical_id, anchor)
    start = min(
        (event.score_onset for event in events), default=min(m.score_onset for m in measures)
    )
    end = max(
        (event.score_onset + event.duration for event in events if not event.grace),
        default=max(measure.score_onset + measure.extent for measure in measures),
    )
    if end <= start:
        end = max(measure.score_onset + measure.extent for measure in measures)
    return CanonicalAnchorSet(
        id=f"anchor-set:{token}",
        package_id=scope.package.id.value,
        score_id=scope.score_id,
        anchors=tuple(unique.values()),
        start_quarters=start,
        end_quarters=end,
    )


def _expected_facts(
    token: str,
    events: tuple[TemporalEvent, ...],
    measures: tuple[TemporalMeasure, ...],
    dimensions: tuple[ObservationDimension, ...],
) -> tuple[ExpectedFact, ...]:
    pitched = tuple(
        event for event in events if event.kind == "pitched" and event.pitch is not None
    )
    event_ids = tuple(event.id for event in events)
    measure_ids = tuple(dict.fromkeys(measure.id for measure in measures))
    result: list[ExpectedFact] = []
    for dimension in dict.fromkeys(dimensions):
        sources: tuple[ObservationSource, ...]
        if dimension in {ObservationDimension.PITCH, ObservationDimension.ORDER}:
            if not pitched:
                continue
            pitches = tuple(_written_midi(event) for event in pitched)
            sources = (
                (ObservationSource.MIDI,)
                if all(pitch.denominator == 1 and 0 <= pitch <= 127 for pitch in pitches)
                else (ObservationSource.HUMAN_REVIEW,)
            )
            value = "written-semitone-sequence:" + ",".join(map(str, pitches))
            references = tuple(event.id for event in pitched)
        elif dimension is ObservationDimension.ONSET:
            value = "score-onsets-quarter:" + ",".join(str(event.score_onset) for event in events)
            references = event_ids
            sources = (ObservationSource.MIDI, ObservationSource.HUMAN_REVIEW)
        elif dimension is ObservationDimension.DURATION:
            value = "written-durations-quarter:" + ",".join(str(event.duration) for event in events)
            references = event_ids
            sources = (ObservationSource.MIDI, ObservationSource.HUMAN_REVIEW)
        elif dimension is ObservationDimension.CONTINUITY:
            value = "complete-half-open-score-range"
            references = event_ids or measure_ids
            sources = (ObservationSource.MIDI,)
        elif dimension is ObservationDimension.SELF_REPORT:
            value = "learner-orientation-response-requested"
            references = measure_ids
            sources = (ObservationSource.LEARNER_REPORT,)
        else:
            continue
        result.append(
            ExpectedFact(
                id=f"expected-fact:{token}:{dimension.value}",
                dimension=dimension,
                canonical_ids=references,
                expected_value=value,
                observable_sources=sources,
            )
        )
    if not result:
        raise PlannerError("PLANNER_EXPECTED_FACT", "exercise has no observable expected fact")
    return tuple(result)


def _requirements(
    exercise_id: str,
    dimensions: tuple[ObservationDimension, ...],
    state: EvidenceState,
    context: EvidenceContext,
) -> tuple[EvidenceRequirement, ...]:
    suffix = exercise_id.split(":", 1)[1]
    return tuple(
        EvidenceRequirement(
            id=f"evidence-requirement:{suffix}:{dimension.value}",
            dimension=dimension,
            minimum_state=state,
            context=context,
        )
        for dimension in dict.fromkeys(dimensions)
    )


def _task_demands(
    scope: _Scope,
    token: str,
    anchor_set: CanonicalAnchorSet,
) -> tuple[TaskDemand, ...]:
    anchor_ids = {anchor.canonical_id for anchor in anchor_set.anchors}
    fallback = tuple(
        anchor.canonical_id
        for anchor in anchor_set.anchors
        if anchor.kind in {CanonicalAnchorKind.MEASURE, CanonicalAnchorKind.EVENT}
    )
    result: list[TaskDemand] = []
    for demand in scope.analysis.demands:
        try:
            dimension = DemandDimension(demand.dimension.value)
        except ValueError:
            continue
        evidence = tuple(
            identifier for identifier in demand.evidence_ids if identifier in anchor_ids
        )
        result.append(
            TaskDemand(
                id=f"task-demand:{token}:{dimension.value}",
                dimension=dimension,
                level=0 if demand.level is None else demand.level,
                evidence_canonical_ids=evidence or fallback,
                rationale=demand.rationale,
                uncertainty=demand.uncertainty,
            )
        )
    return tuple(result)


def _support(scope: _Scope, kind: str) -> SupportState:
    tempo = scope.source_tempo
    if kind == "listen":
        return SupportState(
            id="support:pending",
            notation_visible=True,
            cursor_visible=True,
            note_names_visible=False,
            keyboard_highlighting=True,
            fingering_visible=False,
            demonstration_available=True,
            follow_mode=False,
            metronome=False,
            tempo_percent=_DEFAULT_START_TEMPO_PERCENT,
            max_replays=1,
            prompts_visible=True,
            tempo_bpm=_tempo_at_percent(tempo, _DEFAULT_START_TEMPO_PERCENT),
        )
    if kind == "ear":
        return SupportState(
            id="support:pending",
            notation_visible=False,
            cursor_visible=False,
            note_names_visible=False,
            keyboard_highlighting=False,
            fingering_visible=False,
            demonstration_available=True,
            follow_mode=False,
            metronome=False,
            tempo_percent=_DEFAULT_START_TEMPO_PERCENT,
            max_replays=1,
            prompts_visible=True,
            tempo_bpm=_tempo_at_percent(tempo, _DEFAULT_START_TEMPO_PERCENT),
        )
    if kind == "follow":
        return SupportState(
            id="support:pending",
            notation_visible=True,
            cursor_visible=True,
            note_names_visible=True,
            keyboard_highlighting=True,
            fingering_visible=False,
            demonstration_available=True,
            follow_mode=True,
            metronome=False,
            tempo_percent=63,
            max_replays=1,
            prompts_visible=True,
            tempo_bpm=Fraction(60),
        )
    if kind == "guided-slow":
        return SupportState(
            id="support:pending",
            notation_visible=True,
            cursor_visible=True,
            note_names_visible=False,
            keyboard_highlighting=True,
            fingering_visible=False,
            demonstration_available=True,
            follow_mode=False,
            metronome=True,
            tempo_percent=63,
            max_replays=1,
            prompts_visible=True,
            tempo_bpm=Fraction(60),
        )
    if kind == "guided-reduced":
        return SupportState(
            id="support:pending",
            notation_visible=True,
            cursor_visible=True,
            note_names_visible=False,
            keyboard_highlighting=False,
            fingering_visible=False,
            demonstration_available=False,
            follow_mode=False,
            metronome=True,
            tempo_percent=75,
            max_replays=0,
            prompts_visible=True,
            tempo_bpm=Fraction(72),
        )
    if kind in {"independent", "retention"}:
        return SupportState(
            id="support:pending",
            notation_visible=True,
            cursor_visible=False,
            note_names_visible=False,
            keyboard_highlighting=False,
            fingering_visible=False,
            demonstration_available=False,
            follow_mode=False,
            metronome=kind == "independent",
            tempo_percent=100,
            max_replays=0,
            prompts_visible=False,
            tempo_bpm=tempo,
        )
    raise PlannerError("PLANNER_SUPPORT", f"unknown support policy {kind!r}")


def _tempo_at_percent(tempo: Fraction | None, percentage: int) -> Fraction | None:
    if tempo is None:
        return None
    return tempo * Fraction(percentage, 100)


def _events(scope: _Scope, ordinals: tuple[int, ...]) -> tuple[TemporalEvent, ...]:
    return tuple(
        sorted(
            (
                event
                for ordinal in ordinals
                for measure in scope.measures_by_ordinal[ordinal]
                for event in measure.events
            ),
            key=lambda event: (event.score_onset, event.source_order, event.id),
        )
    )


def _written_midi(event: TemporalEvent) -> Fraction:
    if event.pitch is None:
        raise PlannerError("PLANNER_PITCH", "pitched event has no written pitch")
    semitones = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}
    try:
        base = semitones[event.pitch.step]
    except KeyError as error:
        raise PlannerError("PLANNER_PITCH", f"unknown pitch step {event.pitch.step!r}") from error
    return Fraction(12 * (event.pitch.octave + 1) + base) + event.pitch.alter


def _measure_ordinal(scope: _Scope, measure_id: str) -> int:
    for ordinal, measures in scope.measures_by_ordinal.items():
        if any(measure.id == measure_id for measure in measures):
            return ordinal
    raise PlannerError("PLANNER_MEASURE_REFERENCE", f"measure is outside scope: {measure_id}")


def _covers_ordinals(
    anchor_set: CanonicalAnchorSet,
    scope: _Scope,
    ordinals: tuple[int, ...],
) -> bool:
    expected = {
        measure.id for ordinal in ordinals for measure in scope.measures_by_ordinal[ordinal]
    }
    actual = {
        anchor.canonical_id
        for anchor in anchor_set.anchors
        if anchor.kind is CanonicalAnchorKind.MEASURE
    }
    return actual == expected


def _token(*values: str) -> str:
    return hashlib.sha256("|".join(values).encode()).hexdigest()[:24]


def _id(namespace: str, *values: str) -> str:
    return f"{namespace}:{_token(*values)}"
