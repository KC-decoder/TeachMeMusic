"""Exercise display and expected-piano demonstration projections.

This boundary combines an immutable teaching exercise with existing canonical
viewer contracts.  It never changes the exercise's expected musical content:
tempo, count-in, notation visibility, and keyboard visibility are presentation
aids whose state is recorded separately.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, replace
from fractions import Fraction

from teachmemusic.score import (
    CanonicalMusicPackage,
    CanonicalScoreContent,
    ScoreDocument,
    package_to_json,
)
from teachmemusic.score.v2.temporal import TemporalScore
from teachmemusic.viewer import (
    PlaybackMeasureVisit,
    PlaybackNote,
    PlaybackPlan,
    PlaybackSourceEvent,
    RenderAnchor,
    TempoControl,
    ViewerDiagnostic,
    build_notation_bundle,
    build_playback_plan,
    playback_plan_to_dict,
    require_valid_playback_plan,
)
from teachmemusic.viewer.contracts import DiagnosticSeverity

from .contracts import (
    CanonicalAnchorKind,
    Exercise,
    LessonPlan,
    SupportState,
)
from .curriculum_contracts import (
    CURRICULUM_CONTRACT_VERSION,
    ArtifactResolution,
    CurriculumGuidanceItem,
    CurriculumPassageGuidance,
    CurriculumPassagePresentation,
    CurriculumRendererTarget,
    PassageRequirementSet,
    PrimitiveFamily,
    SemanticReference,
)
from .curriculum_fingerprint import semantic_fingerprint
from .curriculum_validation import (
    require_valid_curriculum_passage_guidance,
    require_valid_curriculum_passage_presentation,
    require_valid_requirement_set,
)
from .validation import require_valid_lesson_plan

EXERCISE_PRESENTATION_CONTRACT_ID = "org.teachmemusic.exercise-presentation"
EXERCISE_PRESENTATION_CONTRACT_VERSION = "0.1.0"
_MICROSECONDS_PER_MINUTE = 60_000_000

_GUIDANCE_ACTIONS: dict[PrimitiveFamily, str] = {
    PrimitiveFamily.LISTENING: (
        "Listen to the highlighted material, then sing or echo its shape before playing."
    ),
    PrimitiveFamily.KEYBOARD: (
        "Locate the highlighted pitches on the keyboard, then play them in written order."
    ),
    PrimitiveFamily.SCORE_LITERACY: (
        "Follow each highlighted symbol in the score and connect it to the matching key."
    ),
    PrimitiveFamily.RHYTHM: (
        "Tap the highlighted rhythm evenly, then play it without changing the written lengths."
    ),
    PrimitiveFamily.PATTERN: (
        "Find where the highlighted pattern repeats, then play each occurrence with the same shape."
    ),
    PrimitiveFamily.HARMONY: (
        "Play highlighted notes together where written and listen to how they support the passage."
    ),
    PrimitiveFamily.LAYER_CONTROL: (
        "Play only the highlighted layer; keep the dimmed layer visible but silent."
    ),
    PrimitiveFamily.COORDINATION: (
        "Keep each highlighted layer distinct, then align the notes that begin together."
    ),
    PrimitiveFamily.TECHNIQUE: (
        "Repeat the highlighted gesture evenly and release each note without adding tension."
    ),
    PrimitiveFamily.EXPRESSION: (
        "Apply the written expressive action only at the highlighted musical target."
    ),
    PrimitiveFamily.MEMORY: (
        "Use the highlighted landmark to stop, reset, and restart the passage accurately."
    ),
    PrimitiveFamily.SELF_REGULATION: (
        "Name one mismatch you notice, make one correction, and try the same target again."
    ),
}


class ExercisePresentationError(ValueError):
    """Raised when an exercise cannot be projected without inventing content."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(f"{code}: {message}")


class CurriculumPresentationError(ValueError):
    """Raised when a practice scope cannot be projected without invention."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(f"{code}: {message}")


@dataclass(frozen=True, slots=True)
class ExerciseAidState:
    """Presentation-only aids that cannot change expected exercise content."""

    tempo_bpm: Fraction
    count_in_enabled: bool
    count_in_beats: int
    count_in_beat_microseconds: int
    notation_visible: bool
    keyboard_visible: bool
    pitch_prompts_visible: bool


@dataclass(frozen=True, slots=True)
class ExercisePresentation:
    """One exact exercise range and its bounded expected-piano demonstration."""

    plan_id: str
    exercise_id: str
    package_id: str
    score_id: str
    expected_content_sha256: str
    material_kind: str
    measure_ids: tuple[str, ...]
    event_ids: tuple[str, ...]
    provenance_ids: tuple[str, ...]
    measure_numbers: tuple[str, ...]
    primary_skill: str
    practice_modes: tuple[str, ...]
    boundary_reason: str
    aid_state: ExerciseAidState
    notation_renderer_sha256: str | None
    demonstration: PlaybackPlan
    diagnostics: tuple[str, ...] = ()
    contract_id: str = EXERCISE_PRESENTATION_CONTRACT_ID
    contract_version: str = EXERCISE_PRESENTATION_CONTRACT_VERSION


def build_exercise_presentation(
    package: CanonicalMusicPackage,
    plan: LessonPlan,
    exercise_id: str,
    *,
    tempo_bpm: Fraction | int | None = None,
    count_in_enabled: bool = True,
) -> ExercisePresentation:
    """Project one generated exercise without changing its expected content."""

    require_valid_lesson_plan(plan, package)
    exercise = next((item for item in plan.exercises if item.id == exercise_id), None)
    if exercise is None:
        raise ExercisePresentationError(
            "TEACH_PRESENTATION_EXERCISE",
            "the requested exercise does not belong to the lesson plan",
        )
    document = _score_document(package, exercise)
    assert isinstance(document.content, CanonicalScoreContent)
    score = document.content.score
    requested_tempo = _presentation_tempo(exercise.initial_support, tempo_bpm)
    expected_digest = expected_content_digest(exercise)

    if exercise.anchor_set is not None:
        measure_ids = _anchor_ids(exercise, CanonicalAnchorKind.MEASURE)
        event_ids = _anchor_ids(exercise, CanonicalAnchorKind.EVENT)
        if not measure_ids or not event_ids:
            raise ExercisePresentationError(
                "TEACH_PRESENTATION_CANONICAL_RANGE",
                "a canonical exercise requires measure and event anchors",
            )
        notation = build_notation_bundle(package, score_id=document.id.value)
        full_playback = build_playback_plan(
            package,
            score_id=document.id.value,
            fallback_tempo_qpm=requested_tempo,
            grace_fallback_percent=Fraction(25),
        )
        demonstration = _canonical_demonstration(
            full_playback,
            exercise,
            measure_ids=measure_ids,
            event_ids=event_ids,
            tempo_bpm=requested_tempo,
        )
        material_kind = "canonical"
        provenance_ids = event_ids
        notation_digest: str | None = notation.renderer.sha256
        diagnostics: tuple[str, ...] = ()
    else:
        material = exercise.synthetic_material
        if material is None:
            raise ExercisePresentationError(
                "TEACH_PRESENTATION_MATERIAL",
                "the exercise has neither canonical nor synthetic material",
            )
        measure_ids = ()
        event_ids = tuple(item.id for item in material.events)
        provenance_ids = material.source_canonical_ids
        demonstration = _synthetic_demonstration(
            package,
            document.id.value,
            exercise,
            tempo_bpm=requested_tempo,
        )
        material_kind = "synthetic-transfer"
        notation_digest = None
        diagnostics = (
            "Synthetic transfer material is displayed as an expected piano sequence; "
            "its source provenance remains separate from canonical score facts.",
        )

    count_beats = _count_in_beats(score, measure_ids) if count_in_enabled else 0
    beat_microseconds = _round_fraction(Fraction(_MICROSECONDS_PER_MINUTE, 1) / requested_tempo)
    aid_state = ExerciseAidState(
        tempo_bpm=requested_tempo,
        count_in_enabled=count_in_enabled and count_beats > 0,
        count_in_beats=count_beats,
        count_in_beat_microseconds=beat_microseconds,
        notation_visible=exercise.initial_support.notation_visible,
        keyboard_visible=exercise.initial_support.keyboard_highlighting,
        pitch_prompts_visible=exercise.initial_support.prompts_visible,
    )
    measure_numbers = _measure_numbers(score, measure_ids)
    result = ExercisePresentation(
        plan_id=plan.id,
        exercise_id=exercise.id,
        package_id=package.id.value,
        score_id=document.id.value,
        expected_content_sha256=expected_digest,
        material_kind=material_kind,
        measure_ids=measure_ids,
        event_ids=event_ids,
        provenance_ids=provenance_ids,
        measure_numbers=measure_numbers,
        primary_skill=exercise.primary_skill.value,
        practice_modes=tuple(item.value for item in exercise.practice_modes),
        boundary_reason=exercise.boundary_reason,
        aid_state=aid_state,
        notation_renderer_sha256=notation_digest,
        demonstration=demonstration,
        diagnostics=diagnostics,
    )
    require_valid_exercise_presentation(result)
    return result


def build_curriculum_passage_presentation(
    package: CanonicalMusicPackage,
    requirements: PassageRequirementSet,
    scope_id: str,
) -> CurriculumPassagePresentation:
    """Project one resolved curriculum scope onto the verified full notation."""

    require_valid_requirement_set(requirements)
    scope = next((item for item in requirements.scopes if item.id == scope_id), None)
    if scope is None:
        raise CurriculumPresentationError(
            "TMM-PRESENTATION-SCOPE-MISSING",
            "the requested practice scope is absent from the requirement set",
        )
    if scope.resolution is not ArtifactResolution.RESOLVED:
        raise CurriculumPresentationError(
            "TMM-PRESENTATION-SCOPE-UNRESOLVED",
            "an unresolved practice scope cannot produce learner-facing notation",
        )
    digest = hashlib.sha256(package_to_json(package).encode("utf-8")).hexdigest()
    if digest != scope.score_package_digest:
        raise CurriculumPresentationError(
            "TMM-PRESENTATION-PACKAGE-MISMATCH",
            "the canonical package differs from the scope derivation input",
        )
    anchor_set = next(
        (item for item in requirements.anchor_sets if item.id == scope.canonical_anchor_set_id),
        None,
    )
    if anchor_set is None or anchor_set.score_id != scope.score_id:
        raise CurriculumPresentationError(
            "TMM-PRESENTATION-ANCHOR-SET-MISSING",
            "the practice scope does not resolve to its canonical anchor set",
        )
    notation = build_notation_bundle(package, score_id=scope.score_id)
    renderer_by_id = {item.canonical_id: item for item in notation.renderer.anchors}
    measure_ids = tuple(
        item.canonical_id for item in anchor_set.anchors if item.kind is CanonicalAnchorKind.MEASURE
    )
    omitted_ids = tuple(item.event_id for item in scope.omissions)
    visible_omitted_ids = tuple(
        item.event_id for item in scope.omissions if item.visible_as_context
    )
    visible_set = (
        set(scope.active_target_ids) | set(scope.inactive_context_ids) | set(visible_omitted_ids)
    )
    visible_ids = tuple(item for item in scope.event_universe_ids if item in visible_set)
    provisional = CurriculumPassagePresentation(
        schema_version=CURRICULUM_CONTRACT_VERSION,
        id="curriculum-passage-presentation:pending",
        semantic_fingerprint="",
        analysis_id=requirements.analysis_id,
        package_id=package.id.value,
        score_id=scope.score_id,
        part_id=scope.part_id,
        practice_scope_ref=SemanticReference(
            "practice-scope-assignment",
            scope.id,
            scope.semantic_fingerprint,
        ),
        score_range=scope.score_range,
        notation_condition=scope.notation_condition,
        execution_assignment=scope.execution_assignment,
        measure_ids=measure_ids,
        event_universe_ids=scope.event_universe_ids,
        visible_event_ids=visible_ids,
        active_target_ids=scope.active_target_ids,
        inactive_context_ids=scope.inactive_context_ids,
        omitted_event_ids=omitted_ids,
        visible_omitted_event_ids=visible_omitted_ids,
        measure_renderer_targets=_renderer_targets(
            measure_ids,
            "measure",
            renderer_by_id,
        ),
        active_renderer_targets=_renderer_targets(
            scope.active_target_ids,
            "event",
            renderer_by_id,
        ),
        inactive_renderer_targets=_renderer_targets(
            scope.inactive_context_ids,
            "event",
            renderer_by_id,
        ),
        visible_omitted_renderer_targets=_renderer_targets(
            visible_omitted_ids,
            "event",
            renderer_by_id,
        ),
        notation_renderer_sha256=notation.renderer.sha256,
        diagnostics=(),
        resolution=ArtifactResolution.RESOLVED,
    )
    fingerprint = semantic_fingerprint(provisional)
    result = replace(
        provisional,
        id=f"curriculum-passage-presentation:{fingerprint}",
        semantic_fingerprint=fingerprint,
    )
    require_valid_curriculum_passage_presentation(result, scope)
    return result


def build_curriculum_expected_playback(
    package: CanonicalMusicPackage,
    presentation: CurriculumPassagePresentation,
    *,
    tempo_bpm: Fraction | int = Fraction(60),
) -> PlaybackPlan:
    """Project only one curriculum presentation's active layer into playback.

    The complete visible passage remains a notation concern.  Sound and
    expected virtual-piano keys are derived exclusively from active canonical
    target identities so inactive context cannot leak into learner guidance.
    """

    require_valid_curriculum_passage_presentation(presentation)
    if package.id.value != presentation.package_id:
        raise CurriculumPresentationError(
            "TMM-PRESENTATION-PLAYBACK-PACKAGE-MISMATCH",
            "the playback package differs from the curriculum presentation",
        )
    tempo = _validated_curriculum_tempo(tempo_bpm)
    full = build_playback_plan(
        package,
        score_id=presentation.score_id,
        fallback_tempo_qpm=tempo,
    )
    result = _bounded_canonical_playback(
        full,
        projection_id=presentation.id,
        measure_ids=presentation.measure_ids,
        event_ids=presentation.active_target_ids,
        tempo_bpm=tempo,
        diagnostic_code="TMM-CURRICULUM-ACTIVE-PLAYBACK",
        diagnostic_message=(
            "playback and expected piano keys contain only the curriculum "
            "presentation's active canonical layer"
        ),
    )
    active = set(presentation.active_target_ids)
    inactive = set(presentation.inactive_context_ids)
    source_ids = {source.event_id for note in result.notes for source in note.source_events}
    expected_source_ids = {
        source.event_id
        for note in full.notes
        for source in note.source_events
        if source.event_id in active
    }
    if not source_ids <= active or source_ids & inactive:
        raise CurriculumPresentationError(
            "TMM-PRESENTATION-PLAYBACK-LAYER-LEAK",
            "inactive canonical context entered expected playback",
        )
    if source_ids != expected_source_ids:
        raise CurriculumPresentationError(
            "TMM-PRESENTATION-PLAYBACK-INCOMPLETE",
            "expected playback omitted an audible active canonical source",
        )
    return result


def build_curriculum_passage_guidance(
    requirements: PassageRequirementSet,
    presentation: CurriculumPassagePresentation,
) -> CurriculumPassageGuidance:
    """Explain and prompt one passage using only resolved curriculum facts."""

    require_valid_requirement_set(requirements)
    scope = next(
        (item for item in requirements.scopes if item.id == presentation.practice_scope_ref.id),
        None,
    )
    if scope is None:
        raise CurriculumPresentationError(
            "TMM-GUIDANCE-SCOPE-MISMATCH",
            "the presentation scope is absent from the requirement set",
        )
    require_valid_curriculum_passage_presentation(presentation, scope)
    if requirements.analysis_id != presentation.analysis_id:
        raise CurriculumPresentationError(
            "TMM-GUIDANCE-ANALYSIS-MISMATCH",
            "the presentation and requirements use different analysis inputs",
        )
    primitive_by_id = {item.id: item for item in requirements.primitives}
    primitive_order = {item.id: index for index, item in enumerate(requirements.primitives)}
    selected = sorted(
        (
            item
            for item in requirements.requirements
            if item.practice_scope_ref.id == scope.id
            and item.resolution is ArtifactResolution.RESOLVED
        ),
        key=lambda item: (primitive_order[item.primitive_ref.id], item.id),
    )
    if not selected:
        raise CurriculumPresentationError(
            "TMM-GUIDANCE-REQUIREMENT-MISSING",
            "the active presentation has no resolved skill requirement",
        )
    items: list[CurriculumGuidanceItem] = []
    layer = _guidance_layer_name(presentation.notation_condition.value)
    for requirement in selected:
        primitive = primitive_by_id[requirement.primitive_ref.id]
        evidence = set(requirement.canonical_evidence_refs)
        focus_event_ids = tuple(
            identifier for identifier in presentation.active_target_ids if identifier in evidence
        )
        if (
            not focus_event_ids
            and primitive.family is PrimitiveFamily.MEMORY
            and evidence & set(presentation.measure_ids)
        ):
            focus_event_ids = presentation.active_target_ids[:1]
        if not focus_event_ids:
            raise CurriculumPresentationError(
                "TMM-GUIDANCE-ACTIVE-EVIDENCE-MISSING",
                "a learner-facing requirement has no active canonical event evidence",
            )
        explanation = (
            f"In the {layer}, the goal is to {primitive.capability}. "
            "The highlighted score events show exactly where to apply this skill."
        )
        reconnect = (
            f"Then play the highlighted material in the {layer} and connect it to "
            "the surrounding visible score."
        )
        item_fingerprint = semantic_fingerprint(
            (
                presentation.id,
                requirement.id,
                primitive.id,
                explanation,
                _GUIDANCE_ACTIONS[primitive.family],
                reconnect,
                focus_event_ids,
            )
        )
        items.append(
            CurriculumGuidanceItem(
                id=f"curriculum-guidance-item:{item_fingerprint}",
                requirement_ref=SemanticReference(
                    "passage-skill-requirement",
                    requirement.id,
                    requirement.semantic_fingerprint,
                ),
                primitive_ref=SemanticReference(
                    "learning-primitive",
                    primitive.id,
                    primitive.semantic_fingerprint,
                ),
                primitive_family=primitive.family,
                heading=f"{primitive.family.value.replace('-', ' ').title()} focus",
                explanation=explanation,
                action_prompt=_GUIDANCE_ACTIONS[primitive.family],
                reconnect_prompt=reconnect,
                target_parameters=requirement.target_parameters,
                focus_event_ids=focus_event_ids,
                canonical_evidence_refs=requirement.canonical_evidence_refs,
                analysis_evidence_refs=requirement.analysis_evidence_refs,
                derivation_rule=requirement.derivation_rule,
            )
        )
    provisional = CurriculumPassageGuidance(
        schema_version=CURRICULUM_CONTRACT_VERSION,
        id="curriculum-passage-guidance:pending",
        semantic_fingerprint="",
        analysis_id=requirements.analysis_id,
        package_id=presentation.package_id,
        score_id=presentation.score_id,
        presentation_ref=SemanticReference(
            "curriculum-passage-presentation",
            presentation.id,
            presentation.semantic_fingerprint,
        ),
        practice_scope_ref=presentation.practice_scope_ref,
        notation_condition=presentation.notation_condition,
        execution_assignment=presentation.execution_assignment,
        items=tuple(items),
        diagnostics=(),
        resolution=ArtifactResolution.RESOLVED,
    )
    fingerprint = semantic_fingerprint(provisional)
    result = replace(
        provisional,
        id=f"curriculum-passage-guidance:{fingerprint}",
        semantic_fingerprint=fingerprint,
    )
    require_valid_curriculum_passage_guidance(
        result,
        requirements=requirements,
        presentation=presentation,
    )
    return result


def _guidance_layer_name(notation_condition: str) -> str:
    return {
        "single-layer": "selected passage",
        "upper-layer": "upper written layer",
        "lower-layer": "lower written layer",
        "combined": "combined written layers",
    }[notation_condition]


def _renderer_targets(
    canonical_ids: tuple[str, ...],
    canonical_kind: str,
    renderer_by_id: dict[str, RenderAnchor],
) -> tuple[CurriculumRendererTarget, ...]:
    result: list[CurriculumRendererTarget] = []
    for canonical_id in canonical_ids:
        renderer = renderer_by_id.get(canonical_id)
        if renderer is None or renderer.canonical_kind != canonical_kind:
            raise CurriculumPresentationError(
                "TMM-PRESENTATION-RENDERER-CROSSWALK",
                f"canonical {canonical_kind} {canonical_id!r} has no renderer target",
            )
        result.append(
            CurriculumRendererTarget(
                canonical_id,
                canonical_kind,
                renderer.renderer_anchor,
            )
        )
    return tuple(result)


def expected_content_digest(exercise: Exercise) -> str:
    """Fingerprint only immutable expected content, excluding presentation aids."""

    anchors = (
        [
            {"kind": item.kind.value, "canonical_id": item.canonical_id}
            for item in exercise.anchor_set.anchors
        ]
        if exercise.anchor_set is not None
        else None
    )
    synthetic = (
        {
            "id": exercise.synthetic_material.id,
            "source_canonical_ids": list(exercise.synthetic_material.source_canonical_ids),
            "events": [
                {
                    "id": item.id,
                    "onset": str(item.onset_quarters),
                    "duration": str(item.duration_quarters),
                    "midi": item.midi_note,
                    "source_canonical_ids": list(item.source_canonical_ids),
                }
                for item in exercise.synthetic_material.events
            ],
        }
        if exercise.synthetic_material is not None
        else None
    )
    payload = {
        "exercise_id": exercise.id,
        "anchors": anchors,
        "synthetic": synthetic,
        "expected_facts": [
            {
                "id": item.id,
                "dimension": item.dimension.value,
                "canonical_ids": list(item.canonical_ids),
                "synthetic_event_ids": list(item.synthetic_event_ids),
                "expected_value": item.expected_value,
            }
            for item in exercise.expected_facts
        ],
    }
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode()).hexdigest()


def validate_exercise_presentation(value: ExercisePresentation) -> tuple[str, ...]:
    """Return stable issue codes for a presentation-boundary value."""

    issues: list[str] = []
    if value.contract_id != EXERCISE_PRESENTATION_CONTRACT_ID:
        issues.append("TEACH_PRESENTATION_CONTRACT_ID")
    if value.contract_version != EXERCISE_PRESENTATION_CONTRACT_VERSION:
        issues.append("TEACH_PRESENTATION_CONTRACT_VERSION")
    if not all((value.plan_id, value.exercise_id, value.package_id, value.score_id)):
        issues.append("TEACH_PRESENTATION_ID")
    if len(value.expected_content_sha256) != 64:
        issues.append("TEACH_PRESENTATION_DIGEST")
    if value.material_kind == "canonical":
        if not value.measure_ids or not value.event_ids or value.notation_renderer_sha256 is None:
            issues.append("TEACH_PRESENTATION_CANONICAL_RANGE")
    elif value.material_kind == "synthetic-transfer":
        if value.measure_ids or not value.event_ids or value.notation_renderer_sha256 is not None:
            issues.append("TEACH_PRESENTATION_SYNTHETIC_RANGE")
    else:
        issues.append("TEACH_PRESENTATION_MATERIAL_KIND")
    if value.aid_state.tempo_bpm <= 0:
        issues.append("TEACH_PRESENTATION_TEMPO")
    if value.aid_state.count_in_beats < 0 or value.aid_state.count_in_beat_microseconds <= 0:
        issues.append("TEACH_PRESENTATION_COUNT_IN")
    if len(set(value.event_ids)) != len(value.event_ids):
        issues.append("TEACH_PRESENTATION_EVENT_IDS")
    if value.demonstration.package_id != value.package_id:
        issues.append("TEACH_PRESENTATION_PLAYBACK_PACKAGE")
    if value.demonstration.score_id != value.score_id:
        issues.append("TEACH_PRESENTATION_PLAYBACK_SCORE")
    if any(
        source.event_id not in value.event_ids
        for note in value.demonstration.notes
        for source in note.source_events
    ):
        issues.append("TEACH_PRESENTATION_PLAYBACK_TRACE")
    if value.material_kind == "canonical" and any(
        source.measure_id not in value.measure_ids
        for note in value.demonstration.notes
        for source in note.source_events
    ):
        issues.append("TEACH_PRESENTATION_PLAYBACK_RANGE")
    if value.demonstration.notes:
        try:
            require_valid_playback_plan(value.demonstration)
        except ValueError:
            issues.append("TEACH_PRESENTATION_PLAYBACK")
    else:
        issues.append("TEACH_PRESENTATION_PLAYBACK_EMPTY")
    return tuple(issues)


def require_valid_exercise_presentation(value: ExercisePresentation) -> None:
    """Raise when a presentation cannot safely cross the application boundary."""

    issues = validate_exercise_presentation(value)
    if issues:
        raise ExercisePresentationError(issues[0], "exercise presentation is invalid")


def exercise_presentation_to_dict(value: ExercisePresentation) -> dict[str, object]:
    """Return deterministic JSON-ready presentation data."""

    require_valid_exercise_presentation(value)
    return {
        "contract_id": value.contract_id,
        "contract_version": value.contract_version,
        "plan_id": value.plan_id,
        "exercise_id": value.exercise_id,
        "package_id": value.package_id,
        "score_id": value.score_id,
        "expected_content_sha256": value.expected_content_sha256,
        "material_kind": value.material_kind,
        "measure_ids": list(value.measure_ids),
        "event_ids": list(value.event_ids),
        "provenance_ids": list(value.provenance_ids),
        "measure_numbers": list(value.measure_numbers),
        "primary_skill": value.primary_skill,
        "practice_modes": list(value.practice_modes),
        "boundary_reason": value.boundary_reason,
        "aid_state": {
            "tempo_bpm": _fraction_dict(value.aid_state.tempo_bpm),
            "count_in_enabled": value.aid_state.count_in_enabled,
            "count_in_beats": value.aid_state.count_in_beats,
            "count_in_beat_microseconds": value.aid_state.count_in_beat_microseconds,
            "notation_visible": value.aid_state.notation_visible,
            "keyboard_visible": value.aid_state.keyboard_visible,
            "pitch_prompts_visible": value.aid_state.pitch_prompts_visible,
        },
        "notation_renderer_sha256": value.notation_renderer_sha256,
        "demonstration": playback_plan_to_dict(value.demonstration),
        "diagnostics": list(value.diagnostics),
    }


def _score_document(package: CanonicalMusicPackage, exercise: Exercise) -> ScoreDocument:
    score_id = exercise.anchor_set.score_id if exercise.anchor_set is not None else None
    documents = [
        item
        for item in package.documents
        if isinstance(item, ScoreDocument)
        and isinstance(item.content, CanonicalScoreContent)
        and (score_id is None or item.id.value == score_id)
    ]
    if len(documents) != 1:
        raise ExercisePresentationError(
            "TEACH_PRESENTATION_SCORE",
            "the exercise does not resolve to exactly one complete score",
        )
    return documents[0]


def _anchor_ids(exercise: Exercise, kind: CanonicalAnchorKind) -> tuple[str, ...]:
    assert exercise.anchor_set is not None
    return tuple(item.canonical_id for item in exercise.anchor_set.anchors if item.kind is kind)


def _presentation_tempo(support: SupportState, override: Fraction | int | None) -> Fraction:
    value = Fraction(override) if override is not None else support.tempo_bpm
    if value is None:
        value = Fraction(60)
    if value <= 0 or value > 400:
        raise ExercisePresentationError(
            "TEACH_PRESENTATION_TEMPO",
            "presentation tempo must be greater than zero and at most 400 BPM",
        )
    return value


def _canonical_demonstration(
    full: PlaybackPlan,
    exercise: Exercise,
    *,
    measure_ids: tuple[str, ...],
    event_ids: tuple[str, ...],
    tempo_bpm: Fraction,
) -> PlaybackPlan:
    return _bounded_canonical_playback(
        full,
        projection_id=exercise.id,
        measure_ids=measure_ids,
        event_ids=event_ids,
        tempo_bpm=tempo_bpm,
        diagnostic_code="TEACH_EXERCISE_PLAYBACK_RANGE",
        diagnostic_message="playback is bounded to the exercise's exact canonical range",
    )


def _bounded_canonical_playback(
    full: PlaybackPlan,
    *,
    projection_id: str,
    measure_ids: tuple[str, ...],
    event_ids: tuple[str, ...],
    tempo_bpm: Fraction,
    diagnostic_code: str,
    diagnostic_message: str,
) -> PlaybackPlan:
    target_measures = set(measure_ids)
    target_events = set(event_ids)
    selected_visits = [
        item
        for item in full.measure_visits
        if target_measures.intersection(item.source_measure_ids)
    ]
    if not selected_visits:
        raise ExercisePresentationError(
            "TEACH_PRESENTATION_PLAYBACK_RANGE",
            "no playback visits match the exercise measures",
        )
    first_visit = selected_visits[0]
    contiguous: list[PlaybackMeasureVisit] = []
    expected_index = first_visit.visit_index
    for visit in selected_visits:
        if visit.visit_index != expected_index:
            break
        contiguous.append(visit)
        expected_index += 1
    start = contiguous[0].start_microseconds
    end = contiguous[-1].end_microseconds
    initial_qpm = full.tempo_controls[0].quarter_notes_per_minute
    scale = initial_qpm / tempo_bpm

    notes: list[PlaybackNote] = []
    for note in full.notes:
        sources = tuple(item for item in note.source_events if item.event_id in target_events)
        if not sources or note.end_microseconds <= start or note.start_microseconds >= end:
            continue
        note_start = _scale_microseconds(max(note.start_microseconds, start) - start, scale)
        note_end = _scale_microseconds(min(note.end_microseconds, end) - start, scale)
        if note_end <= note_start:
            continue
        notes.append(
            replace(
                note,
                id=f"bounded-note:{projection_id}:{len(notes)}",
                start_microseconds=note_start,
                end_microseconds=note_end,
                source_events=sources,
            )
        )
    visits = tuple(
        replace(
            visit,
            visit_index=index,
            start_microseconds=_scale_microseconds(visit.start_microseconds - start, scale),
            end_microseconds=_scale_microseconds(visit.end_microseconds - start, scale),
            entry_reason="initial" if index == 0 else "sequential",
        )
        for index, visit in enumerate(contiguous)
    )
    duration = visits[-1].end_microseconds
    result = PlaybackPlan(
        package_id=full.package_id,
        score_id=full.score_id,
        canonical_schema_id=full.canonical_schema_id,
        canonical_schema_version=full.canonical_schema_version,
        duration_microseconds=duration,
        notes=tuple(
            sorted(notes, key=lambda item: (item.start_microseconds, item.midi_pitch, item.id))
        ),
        tempo_controls=(
            TempoControl(
                id=f"bounded-tempo:{projection_id}",
                at_microseconds=0,
                quarter_notes_per_minute=tempo_bpm,
                source_score_onset=contiguous[0].source_score_onset,
                origin="caller-fallback",
            ),
        ),
        measure_visits=visits,
        navigation_section_starts=(0,),
        diagnostics=(
            ViewerDiagnostic(
                code=diagnostic_code,
                severity=DiagnosticSeverity.INFO,
                message=diagnostic_message,
                canonical_ids=(*measure_ids, *event_ids),
            ),
        ),
    )
    require_valid_playback_plan(result)
    return result


def _validated_curriculum_tempo(value: Fraction | int) -> Fraction:
    tempo = Fraction(value)
    if tempo <= 0 or tempo > 400:
        raise CurriculumPresentationError(
            "TMM-PRESENTATION-PLAYBACK-TEMPO",
            "curriculum playback tempo must be greater than zero and at most 400 BPM",
        )
    return tempo


def _synthetic_demonstration(
    package: CanonicalMusicPackage,
    score_id: str,
    exercise: Exercise,
    *,
    tempo_bpm: Fraction,
) -> PlaybackPlan:
    material = exercise.synthetic_material
    assert material is not None
    beat = Fraction(_MICROSECONDS_PER_MINUTE, 1) / tempo_bpm
    notes: list[PlaybackNote] = []
    for index, event in enumerate(material.events):
        start = _round_fraction(event.onset_quarters * beat)
        end = _round_fraction((event.onset_quarters + event.duration_quarters) * beat)
        notes.append(
            PlaybackNote(
                id=f"exercise-note:{exercise.id}:{index}",
                start_microseconds=start,
                end_microseconds=end,
                midi_pitch=event.midi_note,
                source_events=(
                    PlaybackSourceEvent(
                        event_id=event.id,
                        part_id=material.id,
                        measure_id=material.id,
                        staff="synthetic",
                        voice="transfer",
                        score_onset=event.onset_quarters,
                        clef_group_id=None,
                        clef=None,
                    ),
                ),
            )
        )
    duration = max(item.end_microseconds for item in notes)
    return PlaybackPlan(
        package_id=package.id.value,
        score_id=score_id,
        canonical_schema_id=package.schema_id,
        canonical_schema_version=package.schema_version,
        duration_microseconds=duration,
        notes=tuple(notes),
        tempo_controls=(
            TempoControl(
                id=f"exercise-tempo:{exercise.id}",
                at_microseconds=0,
                quarter_notes_per_minute=tempo_bpm,
                source_score_onset=Fraction(0),
                origin="caller-fallback",
            ),
        ),
        measure_visits=(
            PlaybackMeasureVisit(
                visit_index=0,
                source_measure_index=0,
                source_measure_number="transfer",
                source_measure_ids=(material.id,),
                source_score_onset=Fraction(0),
                start_microseconds=0,
                end_microseconds=duration,
                entry_reason="initial",
            ),
        ),
        navigation_section_starts=(0,),
        diagnostics=(
            ViewerDiagnostic(
                code="TEACH_SYNTHETIC_TRANSFER_PLAYBACK",
                severity=DiagnosticSeverity.INFO,
                message="playback realizes explicit non-canonical transfer material",
                canonical_ids=material.source_canonical_ids,
            ),
        ),
    )


def _count_in_beats(score: TemporalScore, measure_ids: tuple[str, ...]) -> int:
    if not measure_ids:
        return 4
    first_target = measure_ids[0]
    for part in score.parts:
        active: int | None = None
        for measure in part.measures:
            for attributes in sorted(measure.attributes, key=lambda item: item.source_order):
                for time in attributes.times:
                    if time.senza_misura is None and time.beats:
                        try:
                            active = sum(int(item) for item in time.beats)
                        except ValueError:
                            active = None
            if measure.id == first_target:
                return active if active is not None and active > 0 else 0
    return 0


def _measure_numbers(score: TemporalScore, measure_ids: tuple[str, ...]) -> tuple[str, ...]:
    wanted = set(measure_ids)
    result: list[str] = []
    for measure in score.parts[0].measures:
        if measure.id in wanted and measure.number not in result:
            result.append(measure.number)
    return tuple(result)


def _scale_microseconds(value: int, scale: Fraction) -> int:
    return _round_fraction(Fraction(value) * scale)


def _round_fraction(value: Fraction) -> int:
    quotient, remainder = divmod(value.numerator, value.denominator)
    return quotient + (1 if remainder * 2 >= value.denominator else 0)


def _fraction_dict(value: Fraction) -> dict[str, int]:
    return {"numerator": value.numerator, "denominator": value.denominator}
