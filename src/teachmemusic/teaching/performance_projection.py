"""Project a verified exercise demonstration into performance expectations."""

from __future__ import annotations

from dataclasses import replace
from fractions import Fraction

from teachmemusic.performance import (
    ExpectedLayerComponent,
    ExpectedLayerMembership,
    ExpectedLayerTarget,
    ExpectedPerformance,
    ExpectedPerformanceNote,
    ObservationDimension,
    ObservationSource,
    expected_layer_target_fingerprint,
)
from teachmemusic.score import CanonicalMusicPackage

from .contracts import Exercise, PracticeMode
from .curriculum_contracts import (
    CurriculumPassagePresentation,
    NotationCondition,
    PassageRequirementSet,
)
from .curriculum_validation import (
    require_valid_curriculum_passage_presentation,
    require_valid_requirement_set,
)
from .presentation import (
    ExercisePresentation,
    build_curriculum_expected_playback,
    expected_content_digest,
    require_valid_exercise_presentation,
)


class ExpectedPerformanceProjectionError(ValueError):
    """Raised when an exercise cannot become a factual comparison target."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(f"{code}: {message}")


def build_expected_performance(
    exercise: Exercise,
    presentation: ExercisePresentation,
    practice_mode: PracticeMode,
) -> ExpectedPerformance:
    """Build MIDI-neutral expected notes from the verified playback projection."""

    require_valid_exercise_presentation(presentation)
    if presentation.exercise_id != exercise.id:
        raise ExpectedPerformanceProjectionError(
            "TEACH_EXPECTED_EXERCISE", "presentation and exercise differ"
        )
    if presentation.expected_content_sha256 != expected_content_digest(exercise):
        raise ExpectedPerformanceProjectionError(
            "TEACH_EXPECTED_CONTENT", "presentation does not fingerprint this exercise"
        )
    if practice_mode not in exercise.practice_modes:
        raise ExpectedPerformanceProjectionError(
            "TEACH_EXPECTED_MODE", "practice mode is not permitted for this exercise"
        )
    if practice_mode.value not in presentation.practice_modes:
        raise ExpectedPerformanceProjectionError(
            "TEACH_EXPECTED_PRESENTATION_MODE",
            "practice mode is absent from the verified presentation",
        )
    if practice_mode is PracticeMode.LISTEN:
        raise ExpectedPerformanceProjectionError(
            "TEACH_EXPECTED_LISTEN", "listen-only exposure has no learner attempt"
        )
    notes = tuple(
        ExpectedPerformanceNote(
            id=note.id,
            start_microseconds=note.start_microseconds,
            end_microseconds=note.end_microseconds,
            midi_pitch=note.midi_pitch,
            expected_ids=tuple(source.event_id for source in note.source_events),
            chord_id=note.chord_id,
            layers=tuple(
                dict.fromkeys(
                    f"{source.part_id}|staff={source.staff}|voice={source.voice}"
                    for source in note.source_events
                )
            ),
        )
        for note in presentation.demonstration.notes
    )
    dimensions = tuple(
        dict.fromkeys(
            fact.dimension
            for fact in exercise.expected_facts
            if ObservationSource.MIDI in fact.observable_sources
        )
    )
    return ExpectedPerformance(
        exercise_id=exercise.id,
        practice_mode=practice_mode.value,
        notes=notes,
        target_dimensions=dimensions,
        source_contract_version=(
            f"{presentation.contract_id}@{presentation.contract_version};"
            f"{presentation.demonstration.contract_id}@"
            f"{presentation.demonstration.contract_version}"
        ),
    )


def build_curriculum_layer_expected_performance(
    package: CanonicalMusicPackage,
    presentation: CurriculumPassagePresentation,
    practice_mode: PracticeMode,
    *,
    tempo_bpm: Fraction | int = Fraction(60),
) -> ExpectedPerformance:
    """Bind one isolated curriculum layer to a factual MIDI comparison target."""

    if presentation.notation_condition is NotationCondition.COMBINED:
        raise ExpectedPerformanceProjectionError(
            "TEACH_EXPECTED_COMBINED_DEFERRED",
            "combined-layer simultaneity belongs to Task 9D.2",
        )
    if presentation.notation_condition not in {
        NotationCondition.SINGLE_LAYER,
        NotationCondition.UPPER_LAYER,
        NotationCondition.LOWER_LAYER,
    }:
        raise ExpectedPerformanceProjectionError(
            "TEACH_EXPECTED_LAYER_CONDITION",
            "an isolated written layer is required",
        )
    if practice_mode is PracticeMode.LISTEN:
        raise ExpectedPerformanceProjectionError(
            "TEACH_EXPECTED_LISTEN", "listen-only exposure has no learner attempt"
        )
    playback = build_curriculum_expected_playback(
        package,
        presentation,
        tempo_bpm=tempo_bpm,
    )
    provisional = ExpectedLayerTarget(
        presentation_id=presentation.id,
        presentation_fingerprint=presentation.semantic_fingerprint,
        practice_scope_id=presentation.practice_scope_ref.id,
        practice_scope_fingerprint=presentation.practice_scope_ref.semantic_fingerprint,
        notation_condition=presentation.notation_condition.value,
        execution_assignment=presentation.execution_assignment.value,
        active_event_ids=presentation.active_target_ids,
        inactive_event_ids=presentation.inactive_context_ids,
        semantic_fingerprint="",
    )
    target = replace(
        provisional,
        semantic_fingerprint=expected_layer_target_fingerprint(provisional),
    )
    notes = tuple(
        ExpectedPerformanceNote(
            id=note.id,
            start_microseconds=note.start_microseconds,
            end_microseconds=note.end_microseconds,
            midi_pitch=note.midi_pitch,
            expected_ids=tuple(source.event_id for source in note.source_events),
            chord_id=note.chord_id,
            layers=tuple(
                dict.fromkeys(
                    f"{source.part_id}|staff={source.staff}|voice={source.voice}"
                    for source in note.source_events
                )
            ),
        )
        for note in playback.notes
    )
    return ExpectedPerformance(
        exercise_id=f"curriculum-layer-attempt:{target.semantic_fingerprint}",
        practice_mode=practice_mode.value,
        notes=notes,
        target_dimensions=(
            ObservationDimension.PITCH,
            ObservationDimension.ORDER,
            ObservationDimension.ONSET,
            ObservationDimension.DURATION,
            ObservationDimension.CONTINUITY,
        ),
        source_contract_version=(
            f"{presentation.schema_version};"
            f"{playback.contract_id}@{playback.contract_version};"
            f"layer-target:{target.semantic_fingerprint}"
        ),
        layer_target=target,
    )


def build_curriculum_combined_expected_performance(
    package: CanonicalMusicPackage,
    requirements: PassageRequirementSet,
    presentation: CurriculumPassagePresentation,
    component_presentations: tuple[CurriculumPassagePresentation, ...],
    practice_mode: PracticeMode,
    *,
    tempo_bpm: Fraction | int = Fraction(60),
) -> ExpectedPerformance:
    """Build one combined target without flattening its component identities."""

    require_valid_requirement_set(requirements)
    scope_by_id = {item.id: item for item in requirements.scopes}
    scope = scope_by_id.get(presentation.practice_scope_ref.id)
    if scope is None:
        raise ExpectedPerformanceProjectionError(
            "TEACH_EXPECTED_COMBINED_SCOPE",
            "combined presentation scope is absent from the requirement set",
        )
    require_valid_curriculum_passage_presentation(presentation, scope)
    if presentation.notation_condition is not NotationCondition.COMBINED:
        raise ExpectedPerformanceProjectionError(
            "TEACH_EXPECTED_COMBINED_CONDITION",
            "combined matching requires a combined passage presentation",
        )
    if practice_mode is PracticeMode.LISTEN:
        raise ExpectedPerformanceProjectionError(
            "TEACH_EXPECTED_LISTEN", "listen-only exposure has no learner attempt"
        )
    provided = tuple(item.practice_scope_ref.id for item in component_presentations)
    if provided != scope.component_scope_ids:
        raise ExpectedPerformanceProjectionError(
            "TEACH_EXPECTED_COMPONENT_ORDER",
            "component presentations differ from the combined scope",
        )
    components: list[ExpectedLayerComponent] = []
    event_to_component: dict[str, ExpectedLayerComponent] = {}
    for component_presentation in component_presentations:
        component_scope = scope_by_id.get(component_presentation.practice_scope_ref.id)
        if component_scope is None:
            raise ExpectedPerformanceProjectionError(
                "TEACH_EXPECTED_COMPONENT_SCOPE",
                "component presentation scope is absent from the requirement set",
            )
        require_valid_curriculum_passage_presentation(
            component_presentation,
            component_scope,
        )
        if component_presentation.notation_condition is NotationCondition.COMBINED:
            raise ExpectedPerformanceProjectionError(
                "TEACH_EXPECTED_COMPONENT_CONDITION",
                "a combined target cannot contain another combined component",
            )
        if (
            component_presentation.analysis_id != presentation.analysis_id
            or component_presentation.package_id != presentation.package_id
            or component_presentation.score_id != presentation.score_id
            or component_presentation.part_id != presentation.part_id
            or component_presentation.score_range != presentation.score_range
            or component_presentation.measure_ids != presentation.measure_ids
            or component_presentation.event_universe_ids != presentation.event_universe_ids
            or component_presentation.notation_renderer_sha256
            != presentation.notation_renderer_sha256
        ):
            raise ExpectedPerformanceProjectionError(
                "TEACH_EXPECTED_COMPONENT_SOURCE",
                "combined and component presentations do not share one source passage",
            )
        component = ExpectedLayerComponent(
            presentation_id=component_presentation.id,
            presentation_fingerprint=component_presentation.semantic_fingerprint,
            practice_scope_id=component_presentation.practice_scope_ref.id,
            practice_scope_fingerprint=(
                component_presentation.practice_scope_ref.semantic_fingerprint
            ),
            notation_condition=component_presentation.notation_condition.value,
            execution_assignment=component_presentation.execution_assignment.value,
            active_event_ids=component_presentation.active_target_ids,
        )
        components.append(component)
        for event_id in component.active_event_ids:
            if event_id in event_to_component:
                raise ExpectedPerformanceProjectionError(
                    "TEACH_EXPECTED_COMPONENT_OVERLAP",
                    "combined component event memberships overlap",
                )
            event_to_component[event_id] = component
    if set(event_to_component) != set(presentation.active_target_ids):
        raise ExpectedPerformanceProjectionError(
            "TEACH_EXPECTED_COMPONENT_UNION",
            "combined components do not form the exact active target",
        )
    playback = build_curriculum_expected_playback(
        package,
        presentation,
        tempo_bpm=tempo_bpm,
    )
    provisional = ExpectedLayerTarget(
        presentation_id=presentation.id,
        presentation_fingerprint=presentation.semantic_fingerprint,
        practice_scope_id=presentation.practice_scope_ref.id,
        practice_scope_fingerprint=presentation.practice_scope_ref.semantic_fingerprint,
        notation_condition=presentation.notation_condition.value,
        execution_assignment=presentation.execution_assignment.value,
        active_event_ids=presentation.active_target_ids,
        inactive_event_ids=presentation.inactive_context_ids,
        semantic_fingerprint="",
        components=tuple(components),
    )
    target = replace(
        provisional,
        semantic_fingerprint=expected_layer_target_fingerprint(provisional),
    )
    notes = tuple(
        ExpectedPerformanceNote(
            id=note.id,
            start_microseconds=note.start_microseconds,
            end_microseconds=note.end_microseconds,
            midi_pitch=note.midi_pitch,
            expected_ids=tuple(source.event_id for source in note.source_events),
            chord_id=note.chord_id,
            layers=tuple(
                dict.fromkeys(
                    f"{source.part_id}|staff={source.staff}|voice={source.voice}"
                    for source in note.source_events
                )
            ),
            layer_memberships=tuple(
                ExpectedLayerMembership(
                    expected_id=source.event_id,
                    component_scope_id=event_to_component[source.event_id].practice_scope_id,
                    component_scope_fingerprint=(
                        event_to_component[source.event_id].practice_scope_fingerprint
                    ),
                    notation_condition=event_to_component[source.event_id].notation_condition,
                )
                for source in note.source_events
            ),
        )
        for note in playback.notes
    )
    return ExpectedPerformance(
        exercise_id=f"curriculum-layer-attempt:{target.semantic_fingerprint}",
        practice_mode=practice_mode.value,
        notes=notes,
        target_dimensions=(
            ObservationDimension.PITCH,
            ObservationDimension.ORDER,
            ObservationDimension.ONSET,
            ObservationDimension.DURATION,
            ObservationDimension.CONTINUITY,
        ),
        source_contract_version=(
            f"{presentation.schema_version};"
            f"{playback.contract_id}@{playback.contract_version};"
            f"combined-layer-target:{target.semantic_fingerprint}"
        ),
        layer_target=target,
    )
