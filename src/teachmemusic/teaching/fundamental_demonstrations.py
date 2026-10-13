"""Functional demonstrations for graph-declared missing fundamentals."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, replace
from fractions import Fraction

from teachmemusic.score import CanonicalMusicPackage
from teachmemusic.viewer import PlaybackPlan, playback_plan_to_dict

from .curriculum_contracts import (
    CURRICULUM_CONTRACT_VERSION,
    FUNDAMENTAL_DEMONSTRATION_VERSION,
    ActivityForm,
    ArtifactResolution,
    CurriculumFundamentalDemonstration,
    CurriculumFundamentalExplanation,
    CurriculumPassagePresentation,
    PassageRequirementSet,
    PrerequisiteBranchSet,
    RuleReference,
    SemanticReference,
)
from .curriculum_fingerprint import semantic_fingerprint
from .curriculum_validation import (
    require_valid_curriculum_fundamental_demonstration,
    require_valid_curriculum_fundamental_explanation,
    require_valid_curriculum_passage_presentation,
    require_valid_prerequisite_branch_set,
    require_valid_requirement_set,
)
from .presentation import build_curriculum_expected_playback

_DEMONSTRATION_RULE_ID = "DEMONSTRATION-RULE-001"


class CurriculumFundamentalDemonstrationError(ValueError):
    """Raised when a prerequisite cannot use the verified demonstration path."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(f"{code}: {message}")


@dataclass(frozen=True, slots=True)
class CurriculumFundamentalDemonstrationProjection:
    """One governed binding plus its existing viewer playback contract."""

    binding: CurriculumFundamentalDemonstration
    playback: PlaybackPlan


def build_curriculum_fundamental_demonstration(
    package: CanonicalMusicPackage,
    requirements: PassageRequirementSet,
    branches: PrerequisiteBranchSet,
    presentation: CurriculumPassagePresentation,
    explanation: CurriculumFundamentalExplanation,
    *,
    tempo_bpm: Fraction | int = Fraction(60),
) -> CurriculumFundamentalDemonstrationProjection:
    """Bind one declared prerequisite to existing notation/playback/piano.

    This function does not select a prerequisite and cannot create learner
    evidence. It only makes the already selected ``demonstrate-listen``
    activity executable through the verified Task 9C presentation boundary.
    """

    require_valid_requirement_set(requirements)
    if branches.resolution is not ArtifactResolution.RESOLVED:
        raise CurriculumFundamentalDemonstrationError(
            "TMM-DEMONSTRATION-BRANCH-UNRESOLVED",
            "a functional demonstration requires a resolved prerequisite graph",
        )
    require_valid_prerequisite_branch_set(branches, requirements)
    require_valid_curriculum_passage_presentation(presentation)
    require_valid_curriculum_fundamental_explanation(
        explanation,
        requirements,
        branches,
        presentation,
    )

    node = next(
        (item for item in branches.nodes if item.id == explanation.prerequisite_node_id),
        None,
    )
    exercise = next(
        (
            item
            for item in branches.exercises
            if item.id == explanation.prerequisite_exercise_ref.id
        ),
        None,
    )
    if (
        node is None
        or exercise is None
        or node.exercise_ref != explanation.prerequisite_exercise_ref
        or exercise.semantic_fingerprint
        != explanation.prerequisite_exercise_ref.semantic_fingerprint
    ):
        raise CurriculumFundamentalDemonstrationError(
            "TMM-DEMONSTRATION-EXERCISE-MISMATCH",
            "the selected explanation is detached from its prerequisite exercise",
        )
    activities = tuple(
        item for item in exercise.activity_sequence if item.form is ActivityForm.DEMONSTRATE_LISTEN
    )
    if len(activities) != 1 or activities[0].evidence_producing:
        raise CurriculumFundamentalDemonstrationError(
            "TMM-DEMONSTRATION-ACTIVITY-MISMATCH",
            "the prerequisite must declare one non-evidence demonstrate-listen activity",
        )
    if (
        exercise.material.practice_scope_ref != presentation.practice_scope_ref
        or exercise.material.active_target_ids != presentation.active_target_ids
        or exercise.material.inactive_context_ids != presentation.inactive_context_ids
    ):
        raise CurriculumFundamentalDemonstrationError(
            "TMM-DEMONSTRATION-MATERIAL-MISMATCH",
            "the prerequisite material differs from the active passage presentation",
        )

    playback = build_curriculum_expected_playback(
        package,
        presentation,
        tempo_bpm=tempo_bpm,
    )
    source_set = {source.event_id for note in playback.notes for source in note.source_events}
    playback_source_ids = tuple(
        identifier for identifier in presentation.active_target_ids if identifier in source_set
    )
    silent_active_ids = tuple(
        identifier for identifier in presentation.active_target_ids if identifier not in source_set
    )
    if not playback_source_ids:
        raise CurriculumFundamentalDemonstrationError(
            "TMM-DEMONSTRATION-AUDIBLE-TARGET-MISSING",
            "the active prerequisite material has no audible canonical source",
        )
    tempo = Fraction(tempo_bpm)
    rule = RuleReference(
        _DEMONSTRATION_RULE_ID,
        FUNDAMENTAL_DEMONSTRATION_VERSION,
        semantic_fingerprint((_DEMONSTRATION_RULE_ID, FUNDAMENTAL_DEMONSTRATION_VERSION)),
    )
    provisional = CurriculumFundamentalDemonstration(
        schema_version=CURRICULUM_CONTRACT_VERSION,
        id="curriculum-fundamental-demonstration:pending",
        semantic_fingerprint="",
        analysis_id=explanation.analysis_id,
        package_id=explanation.package_id,
        score_id=explanation.score_id,
        explanation_ref=SemanticReference(
            "curriculum-fundamental-explanation",
            explanation.id,
            explanation.semantic_fingerprint,
        ),
        requirement_ref=explanation.requirement_ref,
        primitive_ref=explanation.primitive_ref,
        practice_scope_ref=explanation.practice_scope_ref,
        presentation_ref=explanation.presentation_ref,
        prerequisite_exercise_ref=explanation.prerequisite_exercise_ref,
        prerequisite_node_id=explanation.prerequisite_node_id,
        return_node_id=explanation.return_node_id,
        demonstration_activity_id=activities[0].id,
        focus_event_ids=explanation.focus_event_ids,
        playback_source_event_ids=playback_source_ids,
        silent_active_event_ids=silent_active_ids,
        playback_plan_sha256=_playback_plan_sha256(playback),
        tempo_bpm=tempo,
        generation_rule=rule,
        diagnostics=(),
        resolution=ArtifactResolution.RESOLVED,
    )
    fingerprint = semantic_fingerprint(provisional)
    binding = replace(
        provisional,
        id=f"curriculum-fundamental-demonstration:{fingerprint}",
        semantic_fingerprint=fingerprint,
    )
    require_valid_curriculum_fundamental_demonstration(
        binding,
        explanation,
        requirements,
        branches,
        presentation,
        playback,
    )
    return CurriculumFundamentalDemonstrationProjection(binding, playback)


def _playback_plan_sha256(value: PlaybackPlan) -> str:
    payload = json.dumps(
        playback_plan_to_dict(value),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()
