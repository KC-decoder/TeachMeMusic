"""Playable learner responses for graph-declared missing fundamentals."""

from __future__ import annotations

from dataclasses import dataclass, replace
from fractions import Fraction

from teachmemusic.performance import ExpectedPerformance, ObservationDimension
from teachmemusic.score import CanonicalMusicPackage

from .contracts import PracticeMode
from .curriculum_contracts import (
    CURRICULUM_CONTRACT_VERSION,
    FUNDAMENTAL_PRACTICE_VERSION,
    ActivityForm,
    ArtifactResolution,
    CurriculumFundamentalDemonstration,
    CurriculumFundamentalExplanation,
    CurriculumFundamentalPractice,
    CurriculumPassagePresentation,
    NotationCondition,
    PassageRequirementSet,
    PrerequisiteBranchSet,
    RuleReference,
    SemanticReference,
)
from .curriculum_fingerprint import semantic_fingerprint
from .curriculum_validation import (
    require_valid_curriculum_fundamental_demonstration,
    require_valid_curriculum_fundamental_explanation,
    require_valid_curriculum_fundamental_practice,
    require_valid_curriculum_passage_presentation,
    require_valid_prerequisite_branch_set,
    require_valid_requirement_set,
)
from .performance_projection import (
    build_curriculum_combined_expected_performance,
    build_curriculum_layer_expected_performance,
)

_PRACTICE_RULE_ID = "FUNDAMENTAL-PRACTICE-RULE-001"


class CurriculumFundamentalPracticeError(ValueError):
    """Raised when a prerequisite cannot become an exact learner attempt."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(f"{code}: {message}")


@dataclass(frozen=True, slots=True)
class CurriculumFundamentalPracticeProjection:
    """One governed practice binding and its factual comparison target."""

    binding: CurriculumFundamentalPractice
    expected: ExpectedPerformance


def build_curriculum_fundamental_practice(
    package: CanonicalMusicPackage,
    requirements: PassageRequirementSet,
    branches: PrerequisiteBranchSet,
    presentation: CurriculumPassagePresentation,
    explanation: CurriculumFundamentalExplanation,
    demonstration: CurriculumFundamentalDemonstration,
    *,
    component_presentations: tuple[CurriculumPassagePresentation, ...] = (),
    tempo_bpm: Fraction | int = Fraction(60),
) -> CurriculumFundamentalPracticeProjection:
    """Bind one declared ``perform`` activity to the existing attempt boundary.

    The projection contains expected facts, not learner observations.  The
    preceding demonstration remains non-evidence, and progression remains a
    downstream policy decision.
    """

    require_valid_requirement_set(requirements)
    if branches.resolution is not ArtifactResolution.RESOLVED:
        raise CurriculumFundamentalPracticeError(
            "TMM-PRACTICE-BRANCH-UNRESOLVED",
            "a playable prerequisite requires a resolved prerequisite graph",
        )
    require_valid_prerequisite_branch_set(branches, requirements)
    require_valid_curriculum_passage_presentation(presentation)
    require_valid_curriculum_fundamental_explanation(
        explanation,
        requirements,
        branches,
        presentation,
    )
    require_valid_curriculum_fundamental_demonstration(
        demonstration,
        explanation,
        requirements,
        branches,
        presentation,
    )

    exercise = next(
        (
            item
            for item in branches.exercises
            if item.id == explanation.prerequisite_exercise_ref.id
        ),
        None,
    )
    if exercise is None:
        raise CurriculumFundamentalPracticeError(
            "TMM-PRACTICE-EXERCISE-MISMATCH",
            "the selected prerequisite exercise is absent",
        )
    activities = tuple(
        item for item in exercise.activity_sequence if item.form is ActivityForm.PERFORM
    )
    if len(activities) != 1 or not activities[0].evidence_producing:
        raise CurriculumFundamentalPracticeError(
            "TMM-PRACTICE-ACTIVITY-MISMATCH",
            "the prerequisite must declare one evidence-producing perform activity",
        )
    if (
        demonstration.prerequisite_exercise_ref != explanation.prerequisite_exercise_ref
        or demonstration.demonstration_activity_id == activities[0].id
    ):
        raise CurriculumFundamentalPracticeError(
            "TMM-PRACTICE-DEMONSTRATION-MISMATCH",
            "demonstration and performance activities must stay distinct",
        )
    if not exercise.required_evidence_exits:
        raise CurriculumFundamentalPracticeError(
            "TMM-PRACTICE-EVIDENCE-EXIT-MISSING",
            "the prerequisite declares no evidence exit",
        )

    practice_mode = PracticeMode.SUPPORTED_PERFORMANCE
    if presentation.notation_condition is NotationCondition.COMBINED:
        expected = build_curriculum_combined_expected_performance(
            package,
            requirements,
            presentation,
            component_presentations,
            practice_mode,
            tempo_bpm=tempo_bpm,
        )
    else:
        if component_presentations:
            raise CurriculumFundamentalPracticeError(
                "TMM-PRACTICE-COMPONENT-MISMATCH",
                "isolated practice cannot accept combined component presentations",
            )
        expected = build_curriculum_layer_expected_performance(
            package,
            presentation,
            practice_mode,
            tempo_bpm=tempo_bpm,
        )
    try:
        evidence_dimensions = tuple(
            ObservationDimension(item.dimension) for item in exercise.required_evidence_exits
        )
    except ValueError as error:
        raise CurriculumFundamentalPracticeError(
            "TMM-PRACTICE-EVIDENCE-DIMENSION",
            "the prerequisite declares an unsupported performance dimension",
        ) from error
    expected = replace(
        expected,
        target_dimensions=tuple(dict.fromkeys((*expected.target_dimensions, *evidence_dimensions))),
    )
    target = expected.layer_target
    if target is None or target.active_event_ids != exercise.material.active_target_ids:
        raise CurriculumFundamentalPracticeError(
            "TMM-PRACTICE-TARGET-MISMATCH",
            "the factual comparison target differs from prerequisite material",
        )
    if not expected.notes:
        raise CurriculumFundamentalPracticeError(
            "TMM-PRACTICE-AUDIBLE-TARGET-MISSING",
            "the prerequisite has no audible learner-performance target",
        )

    tempo = Fraction(tempo_bpm)
    rule = RuleReference(
        _PRACTICE_RULE_ID,
        FUNDAMENTAL_PRACTICE_VERSION,
        semantic_fingerprint((_PRACTICE_RULE_ID, FUNDAMENTAL_PRACTICE_VERSION)),
    )
    provisional = CurriculumFundamentalPractice(
        schema_version=CURRICULUM_CONTRACT_VERSION,
        id="curriculum-fundamental-practice:pending",
        semantic_fingerprint="",
        analysis_id=explanation.analysis_id,
        package_id=explanation.package_id,
        score_id=explanation.score_id,
        explanation_ref=SemanticReference(
            "curriculum-fundamental-explanation",
            explanation.id,
            explanation.semantic_fingerprint,
        ),
        demonstration_ref=SemanticReference(
            "curriculum-fundamental-demonstration",
            demonstration.id,
            demonstration.semantic_fingerprint,
        ),
        requirement_ref=explanation.requirement_ref,
        primitive_ref=explanation.primitive_ref,
        practice_scope_ref=explanation.practice_scope_ref,
        presentation_ref=explanation.presentation_ref,
        prerequisite_exercise_ref=explanation.prerequisite_exercise_ref,
        prerequisite_node_id=explanation.prerequisite_node_id,
        return_node_id=explanation.return_node_id,
        performance_activity_id=activities[0].id,
        practice_mode=practice_mode,
        support_envelope=exercise.support_envelope,
        required_evidence_exits=exercise.required_evidence_exits,
        expected_performance_id=expected.exercise_id,
        expected_target_fingerprint=target.semantic_fingerprint,
        expected_active_event_ids=target.active_event_ids,
        expected_note_ids=tuple(item.id for item in expected.notes),
        target_dimensions=expected.target_dimensions,
        expected_performance_sha256=semantic_fingerprint(expected),
        tempo_bpm=tempo,
        generation_rule=rule,
        diagnostics=(),
        resolution=ArtifactResolution.RESOLVED,
    )
    fingerprint = semantic_fingerprint(provisional)
    binding = replace(
        provisional,
        id=f"curriculum-fundamental-practice:{fingerprint}",
        semantic_fingerprint=fingerprint,
    )
    require_valid_curriculum_fundamental_practice(
        binding,
        explanation,
        demonstration,
        requirements,
        branches,
        presentation,
        expected,
    )
    return CurriculumFundamentalPracticeProjection(binding, expected)
