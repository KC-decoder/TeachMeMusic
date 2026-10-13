"""Support-aware factual evidence for exact DEV-009 curriculum targets."""

from __future__ import annotations

from dataclasses import replace

from teachmemusic.performance import (
    COMBINED_LAYER_ALIGNMENT_POLICY_VERSION,
    LAYER_ALIGNMENT_POLICY_VERSION,
    ExpectedLayerTarget,
    ExpectedPerformance,
    LearnerAttempt,
    Observation,
    ObservationDimension,
    ObservationStatus,
    expected_layer_target_fingerprint,
)

from .contracts import EvidenceContext, PracticeMode, SupportState
from .curriculum_contracts import (
    CURRICULUM_CONTRACT_VERSION,
    ArtifactResolution,
    CurriculumEvidenceRecord,
    CurriculumEvidenceResult,
    NotationCondition,
    PassageRequirementSet,
    PracticeScopeAssignment,
    SemanticReference,
)
from .curriculum_fingerprint import derived_id, semantic_fingerprint
from .curriculum_validation import (
    require_valid_curriculum_evidence_record,
    require_valid_requirement_set,
)


class CurriculumEvidenceError(ValueError):
    """Raised when observations cannot support the declared curriculum context."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(f"{code}: {message}")


_CONTEXT_MODES: dict[EvidenceContext, frozenset[PracticeMode]] = {
    EvidenceContext.ACQUISITION: frozenset(
        {
            PracticeMode.EAR_FIRST,
            PracticeMode.FOLLOW_PITCH,
            PracticeMode.PULSE_GUIDED,
            PracticeMode.SUPPORTED_PERFORMANCE,
        }
    ),
    EvidenceContext.INDEPENDENT: frozenset({PracticeMode.INDEPENDENT_PERFORMANCE}),
    EvidenceContext.INTEGRATION: frozenset(
        {PracticeMode.SUPPORTED_PERFORMANCE, PracticeMode.INDEPENDENT_PERFORMANCE}
    ),
    EvidenceContext.RETENTION: frozenset({PracticeMode.RETENTION}),
    EvidenceContext.TRANSFER: frozenset({PracticeMode.TRANSFER}),
}


def build_curriculum_evidence_records(
    requirements: PassageRequirementSet,
    expected: ExpectedPerformance,
    attempt: LearnerAttempt,
    support: SupportState,
    observations: tuple[Observation, ...],
    evidence_context: EvidenceContext,
) -> tuple[CurriculumEvidenceRecord, ...]:
    """Bind factual observations to one exact scope, support state, and context.

    The result deliberately contains no mastery, unlock, or teaching-policy decision.
    Required dimensions for which no observation exists remain absent rather than being
    fabricated as successful or inconclusive evidence.
    """

    if any(not isinstance(item, Observation) for item in observations):
        raise CurriculumEvidenceError(
            "TMM-EVIDENCE-OBSERVATION-TYPE",
            "curriculum evidence accepts factual performance observations only",
        )
    require_valid_requirement_set(requirements)
    target = expected.layer_target
    if target is None:
        raise CurriculumEvidenceError(
            "TMM-EVIDENCE-TARGET-MISSING",
            "curriculum evidence requires an explicit layer target",
        )
    if target.semantic_fingerprint != expected_layer_target_fingerprint(target):
        raise CurriculumEvidenceError(
            "TMM-EVIDENCE-TARGET-FINGERPRINT",
            "expected target semantics differ from its fingerprint",
        )
    if expected.exercise_id != f"curriculum-layer-attempt:{target.semantic_fingerprint}":
        raise CurriculumEvidenceError(
            "TMM-EVIDENCE-TARGET-IDENTITY",
            "expected exercise identity does not name the exact target",
        )
    try:
        practice_mode = PracticeMode(expected.practice_mode)
    except ValueError as error:
        raise CurriculumEvidenceError(
            "TMM-EVIDENCE-PRACTICE-MODE",
            "expected performance has an unsupported practice mode",
        ) from error
    if practice_mode not in _CONTEXT_MODES[evidence_context]:
        raise CurriculumEvidenceError(
            "TMM-EVIDENCE-CONTEXT-MISMATCH",
            "practice mode cannot produce evidence in the requested context",
        )
    if evidence_context is EvidenceContext.INTEGRATION and (
        target.notation_condition != NotationCondition.COMBINED.value
    ):
        raise CurriculumEvidenceError(
            "TMM-EVIDENCE-CONTEXT-MISMATCH",
            "integration evidence requires a combined target",
        )
    if attempt.exercise_id != expected.exercise_id:
        raise CurriculumEvidenceError(
            "TMM-EVIDENCE-ATTEMPT-TARGET",
            "attempt and expected target identities differ",
        )
    if attempt.practice_mode != expected.practice_mode:
        raise CurriculumEvidenceError(
            "TMM-EVIDENCE-PRACTICE-MODE",
            "attempt and expected practice modes differ",
        )
    if attempt.support_state_id != support.id:
        raise CurriculumEvidenceError(
            "TMM-EVIDENCE-SUPPORT-MISMATCH",
            "attempt was not produced under the supplied support state",
        )

    scope_by_id = {item.id: item for item in requirements.scopes}
    scope = scope_by_id.get(target.practice_scope_id)
    if scope is None:
        raise CurriculumEvidenceError(
            "TMM-EVIDENCE-SCOPE-MISSING",
            "target scope is absent from the requirement set",
        )
    if (
        target.practice_scope_fingerprint != scope.semantic_fingerprint
        or target.notation_condition != scope.notation_condition.value
        or target.execution_assignment != scope.execution_assignment.value
        or target.active_event_ids != scope.active_target_ids
        or target.inactive_event_ids != scope.inactive_context_ids
    ):
        raise CurriculumEvidenceError(
            "TMM-EVIDENCE-SCOPE-MISMATCH",
            "target and exact practice scope differ",
        )

    component_refs = _component_references(target, scope_by_id)
    policy = (
        COMBINED_LAYER_ALIGNMENT_POLICY_VERSION
        if scope.notation_condition is NotationCondition.COMBINED
        else LAYER_ALIGNMENT_POLICY_VERSION
    )
    policy_prefix = f"{policy}:{target.semantic_fingerprint}:"
    for observation in observations:
        if observation.attempt_id != attempt.id or observation.exercise_id != expected.exercise_id:
            raise CurriculumEvidenceError(
                "TMM-EVIDENCE-OBSERVATION-FOREIGN",
                "observation belongs to another attempt or target",
            )
        if observation.matching_policy is None or not observation.matching_policy.startswith(
            policy_prefix
        ):
            raise CurriculumEvidenceError(
                "TMM-EVIDENCE-OBSERVATION-POLICY",
                "observation was not produced for this exact layer target",
            )
        if observation.expected_canonical_ids and not set(
            observation.expected_canonical_ids
        ) <= set(scope.active_target_ids):
            raise CurriculumEvidenceError(
                "TMM-EVIDENCE-SCOPE-LEAK",
                "observation references canonical events outside the active scope",
            )

    context_observations = tuple(
        item.id for item in observations if item.dimension is ObservationDimension.HUMAN_REVIEW
    )
    support_ref = SemanticReference(
        artifact_type="support-state",
        id=support.id,
        semantic_fingerprint=semantic_fingerprint(support),
    )
    target_ref = SemanticReference(
        artifact_type="expected-layer-target",
        id=expected.exercise_id,
        semantic_fingerprint=target.semantic_fingerprint,
    )
    primitive_by_id = {item.id: item for item in requirements.primitives}
    records: list[CurriculumEvidenceRecord] = []
    for requirement in requirements.requirements:
        if (
            requirement.resolution is not ArtifactResolution.RESOLVED
            or requirement.practice_scope_ref.id != scope.id
            or requirement.practice_scope_ref.semantic_fingerprint != scope.semantic_fingerprint
        ):
            continue
        primitive = primitive_by_id.get(requirement.primitive_ref.id)
        if (
            primitive is None
            or primitive.semantic_fingerprint != requirement.primitive_ref.semantic_fingerprint
        ):
            raise CurriculumEvidenceError(
                "TMM-EVIDENCE-PRIMITIVE-MISMATCH",
                "requirement primitive is absent or has changed",
            )
        for dimension_name in requirement.required_dimensions:
            try:
                dimension = ObservationDimension(dimension_name)
            except ValueError:
                continue
            selected = tuple(item for item in observations if item.dimension is dimension)
            if not selected:
                continue
            result, limitations = _summarize_observations(selected)
            selected_ids = {item.id for item in selected}
            provisional = CurriculumEvidenceRecord(
                schema_version=CURRICULUM_CONTRACT_VERSION,
                id="curriculum-evidence:pending",
                semantic_fingerprint="",
                attempt_id=attempt.id,
                expected_target_ref=target_ref,
                requirement_ref=SemanticReference(
                    artifact_type="passage-skill-requirement",
                    id=requirement.id,
                    semantic_fingerprint=requirement.semantic_fingerprint,
                ),
                primitive_ref=requirement.primitive_ref,
                practice_scope_ref=requirement.practice_scope_ref,
                component_scope_refs=component_refs,
                notation_condition=scope.notation_condition,
                execution_assignment=scope.execution_assignment,
                dimension=dimension,
                evidence_context=evidence_context,
                result=result,
                observation_ids=tuple(item.id for item in selected),
                context_observation_ids=tuple(
                    item for item in context_observations if item not in selected_ids
                ),
                support_state_ref=support_ref,
                limitations=limitations,
                resolution=ArtifactResolution.RESOLVED,
            )
            record = replace(
                provisional,
                id=derived_id("curriculum-evidence", provisional),
                semantic_fingerprint=semantic_fingerprint(provisional),
            )
            require_valid_curriculum_evidence_record(record)
            records.append(record)
    return tuple(records)


def require_compatible_curriculum_evidence(
    records: tuple[CurriculumEvidenceRecord, ...],
    requirements: PassageRequirementSet,
    expected: ExpectedPerformance,
    attempt: LearnerAttempt,
    support: SupportState,
    observations: tuple[Observation, ...],
    evidence_context: EvidenceContext,
) -> None:
    """Fail closed unless records exactly reconstruct from their declared inputs."""

    if any(not isinstance(item, CurriculumEvidenceRecord) for item in records):
        raise CurriculumEvidenceError(
            "TMM-EVIDENCE-RECORD-TYPE",
            "evidence compatibility accepts curriculum evidence records only",
        )
    for record in records:
        require_valid_curriculum_evidence_record(record)
    rebuilt = build_curriculum_evidence_records(
        requirements,
        expected,
        attempt,
        support,
        observations,
        evidence_context,
    )
    if records != rebuilt:
        raise CurriculumEvidenceError(
            "TMM-EVIDENCE-INCOMPATIBLE",
            "records do not belong to the supplied scope, support state, and context",
        )


def _component_references(
    target: ExpectedLayerTarget,
    scope_by_id: dict[str, PracticeScopeAssignment],
) -> tuple[SemanticReference, ...]:
    if target.notation_condition != NotationCondition.COMBINED.value:
        if target.components:
            raise CurriculumEvidenceError(
                "TMM-EVIDENCE-COMPONENT-MISMATCH",
                "isolated target unexpectedly contains component identities",
            )
        return ()
    if tuple(item.practice_scope_id for item in target.components) != tuple(
        scope_by_id[target.practice_scope_id].component_scope_ids
    ):
        raise CurriculumEvidenceError(
            "TMM-EVIDENCE-COMPONENT-MISMATCH",
            "combined target components differ from the declared scope",
        )
    references: list[SemanticReference] = []
    for component in target.components:
        scope = scope_by_id.get(component.practice_scope_id)
        if scope is None or component.practice_scope_fingerprint != scope.semantic_fingerprint:
            raise CurriculumEvidenceError(
                "TMM-EVIDENCE-COMPONENT-MISMATCH",
                "combined component scope is absent or has changed",
            )
        if (
            component.notation_condition != scope.notation_condition.value
            or component.execution_assignment != scope.execution_assignment.value
            or component.active_event_ids != scope.active_target_ids
        ):
            raise CurriculumEvidenceError(
                "TMM-EVIDENCE-COMPONENT-MISMATCH",
                "combined component topology differs from its exact scope",
            )
        references.append(
            SemanticReference(
                artifact_type="practice-scope-assignment",
                id=scope.id,
                semantic_fingerprint=scope.semantic_fingerprint,
            )
        )
    if set().union(*(set(item.active_event_ids) for item in target.components)) != set(
        target.active_event_ids
    ):
        raise CurriculumEvidenceError(
            "TMM-EVIDENCE-COMPONENT-MISMATCH",
            "combined component events do not exactly cover the target",
        )
    return tuple(references)


def _summarize_observations(
    observations: tuple[Observation, ...],
) -> tuple[CurriculumEvidenceResult, tuple[str, ...]]:
    uncertain = {
        ObservationStatus.AMBIGUOUS,
        ObservationStatus.UNOBSERVABLE,
        ObservationStatus.INVALID_INPUT,
    }
    limitations = tuple(
        dict.fromkeys(
            limitation
            for observation in observations
            for limitation in observation.limitations
            if limitation.strip()
        )
    )
    if any(item.status in uncertain for item in observations):
        if not limitations:
            limitations = tuple(
                dict.fromkeys(
                    f"Observation status was {item.status.value}."
                    for item in observations
                    if item.status in uncertain
                )
            )
        return CurriculumEvidenceResult.INCONCLUSIVE, limitations
    if any(item.status is ObservationStatus.DISCREPANCY for item in observations):
        return CurriculumEvidenceResult.DISCREPANCY, limitations
    return CurriculumEvidenceResult.MATCHED, limitations
