"""Production orchestration for the DEV-009 deterministic curriculum."""

from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass, field
from fractions import Fraction
from pathlib import Path
from threading import RLock

from teachmemusic._contract_codec import contract_to_data
from teachmemusic.performance import (
    CalibrationProfile,
    ExpectedPerformance,
    LearnerAttempt,
    Observation,
    align_layer_attempt,
)
from teachmemusic.score import CanonicalMusicPackage, package_to_json
from teachmemusic.teaching import (
    AcquisitionStageKind,
    ArtifactResolution,
    CompatibleTempoEvidence,
    CurriculumAnalysisAssembly,
    CurriculumEvidenceRecord,
    CurriculumEvidenceStore,
    CurriculumFundamentalDiagnosticAssembly,
    CurriculumMasteryProjection,
    CurriculumMasteryStatus,
    CurriculumPassagePresentation,
    CurriculumPolicyAction,
    CurriculumPracticeAssembly,
    CurriculumStoragePolicy,
    CurriculumSupportDecision,
    CurriculumUnlockDecision,
    EvidenceContext,
    NotationCondition,
    PracticeMode,
    SemanticReference,
    SupportState,
    TempoProbeResult,
    TempoReferenceAuthority,
    TempoTransition,
    assemble_curriculum_analysis,
    assemble_curriculum_fundamentals,
    assemble_curriculum_practice,
    build_curriculum_combined_expected_performance,
    build_curriculum_evidence_records,
    build_curriculum_exercise_learning_outcome,
    build_curriculum_expected_playback,
    build_curriculum_layer_expected_performance,
    build_curriculum_passage_guidance,
    build_curriculum_research_reward,
    decide_curriculum_support,
    decide_curriculum_unlock,
    decide_tempo_probe,
)
from teachmemusic.teaching.curriculum_contracts import (
    AcquisitionStage,
    ControlledTempoPlan,
    CurriculumGraphNode,
    ExerciseInstance,
)
from teachmemusic.teaching.curriculum_fingerprint import semantic_fingerprint
from teachmemusic.viewer import playback_plan_to_dict


class CurriculumRunStoreError(ValueError):
    """Stable production failure at the DEV-009 orchestration boundary."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(f"{code}: {message}")


@dataclass(frozen=True, slots=True)
class CurriculumStageProjection:
    """One exact graph node projected for the browser."""

    stage: AcquisitionStage
    node: CurriculumGraphNode
    exercise: ExerciseInstance
    presentation: CurriculumPassagePresentation
    expected: ExpectedPerformance
    support_condition: str
    support: SupportState
    tempo_plan: ControlledTempoPlan
    evidence_context: EvidenceContext


@dataclass(frozen=True, slots=True)
class CurriculumDeliveryPlan:
    """Production-ready assembly for one canonical score and tempo state."""

    session_id: str
    run_id: str
    package: CanonicalMusicPackage
    score_id: str
    analysis: CurriculumAnalysisAssembly
    fundamentals: CurriculumFundamentalDiagnosticAssembly
    practice: CurriculumPracticeAssembly
    reference_tempo_bpm: Fraction

    @property
    def id(self) -> str:
        return self.practice.manifest.id


@dataclass(frozen=True, slots=True)
class CurriculumAttemptCycle:
    """Authoritative result of one production curriculum attempt."""

    observations: tuple[Observation, ...]
    evidence_records: tuple[CurriculumEvidenceRecord, ...]
    mastery: CurriculumMasteryProjection
    unlock: CurriculumUnlockDecision
    outcome: object
    research_reward: object
    policy_decision: CurriculumSupportDecision | TempoTransition
    plan: CurriculumDeliveryPlan
    projection: CurriculumStageProjection
    inspection: dict[str, object]


@dataclass(slots=True)
class _ActiveCurriculumRun:
    plan: CurriculumDeliveryPlan
    authorization: dict[str, object]
    learner_context_id: str
    current_node_id: str
    current_condition: str
    tempo_evidence: dict[str, CompatibleTempoEvidence] = field(default_factory=dict)
    attempts_by_condition: dict[tuple[str, str], tuple[str, ...]] = field(default_factory=dict)
    evidence_by_condition: dict[tuple[str, str], tuple[CurriculumEvidenceRecord, ...]] = field(
        default_factory=dict
    )
    observations_by_condition: dict[tuple[str, str], tuple[Observation, ...]] = field(
        default_factory=dict
    )
    satisfied_node_ids: tuple[str, ...] = ()
    support_history: tuple[CurriculumSupportDecision, ...] = ()
    last_evidence_offset_us: int = 0
    attempt_count: int = 0


def assemble_curriculum_delivery(
    package: CanonicalMusicPackage,
    *,
    score_id: str,
    session_id: str,
    reference_tempo_bpm: Fraction = Fraction(120),
    tempo_evidence: tuple[CompatibleTempoEvidence, ...] = (),
) -> CurriculumDeliveryPlan:
    """Assemble the accepted DEV-009 route from a production package."""

    analysis = assemble_curriculum_analysis(package, score_id=score_id)
    fundamentals = assemble_curriculum_fundamentals(package, analysis)
    practice = assemble_curriculum_practice(
        package,
        analysis,
        fundamentals,
        reference_tempo_bpm=reference_tempo_bpm,
        reference_authority=TempoReferenceAuthority.CALLER,
        tempo_evidence=tempo_evidence,
    )
    if practice.manifest.resolution is not ArtifactResolution.RESOLVED:
        raise CurriculumRunStoreError(
            "APP_CURRICULUM_UNRESOLVED",
            "the deterministic curriculum requires bounded human review",
        )
    identity = hashlib.sha256(f"{session_id}|{score_id}".encode()).hexdigest()[:24]
    run_id = f"curriculum-run:{identity}"
    return CurriculumDeliveryPlan(
        session_id=session_id,
        run_id=run_id,
        package=package,
        score_id=score_id,
        analysis=analysis,
        fundamentals=fundamentals,
        practice=practice,
        reference_tempo_bpm=reference_tempo_bpm,
    )


def project_curriculum_stage(
    plan: CurriculumDeliveryPlan,
    node_id: str,
    *,
    support_condition: str | None = None,
) -> CurriculumStageProjection:
    """Project one playable graph node without inventing score material."""

    graph = plan.practice.acquisition
    node = next((item for item in graph.nodes if item.id == node_id), None)
    if node is None or node.exercise_ref is None or node.scope_ref is None:
        raise CurriculumRunStoreError(
            "APP_CURRICULUM_NODE", "the requested curriculum node is not playable"
        )
    exercise = next(
        (item for item in graph.exercises if item.id == node.exercise_ref.id),
        None,
    )
    presentation = next(
        (
            item
            for item in plan.practice.presentations
            if item.practice_scope_ref.id == node.scope_ref.id
        ),
        None,
    )
    stage = next((item for item in graph.stages if item.node_id == node_id), None)
    if exercise is None or presentation is None:
        raise CurriculumRunStoreError(
            "APP_CURRICULUM_NODE", "the graph node lost its exercise or presentation"
        )
    if stage is None:
        stage = AcquisitionStage(
            id=f"runtime-stage:{hashlib.sha256(node_id.encode()).hexdigest()[:24]}",
            kind=AcquisitionStageKind.COMPONENT_ACQUISITION,
            order=-1,
            node_id=node_id,
            practice_scope_ref=node.scope_ref,
            component_node_ids=node.component_node_ids,
            tempo_plan_ref=SemanticReference(
                "controlled-tempo-plan",
                graph.tempo_plans[0].id,
                graph.tempo_plans[0].semantic_fingerprint,
            ),
            evidence_context=exercise.required_evidence_exits[0].evidence_context,
        )
    tempo_plan = next(
        item
        for item in graph.tempo_plans
        if item.practice_scope_ref.id == presentation.practice_scope_ref.id
    )
    condition = support_condition or exercise.support_envelope.initial_condition
    if condition not in exercise.support_envelope.permitted_conditions:
        raise CurriculumRunStoreError(
            "APP_CURRICULUM_SUPPORT", "the requested support condition is not permitted"
        )
    evidence_context = _evidence_context(exercise.required_evidence_exits[0].evidence_context)
    mode = _practice_mode(evidence_context)
    percent = _condition_percent(condition, tempo_plan)
    tempo = plan.reference_tempo_bpm * Fraction(percent, 100)
    support = _support_state(exercise, presentation, condition, percent, tempo)
    if presentation.notation_condition is NotationCondition.COMBINED:
        components = tuple(
            item
            for item in plan.practice.presentations
            if item.practice_scope_ref.id
            in set(
                next(
                    scope
                    for scope in plan.analysis.requirements.scopes
                    if scope.id == presentation.practice_scope_ref.id
                ).component_scope_ids
            )
        )
        expected = build_curriculum_combined_expected_performance(
            plan.package,
            plan.analysis.requirements,
            presentation,
            components,
            mode,
            tempo_bpm=tempo,
        )
    else:
        expected = build_curriculum_layer_expected_performance(
            plan.package,
            presentation,
            mode,
            tempo_bpm=tempo,
        )
    if exercise.material.active_target_ids != presentation.active_target_ids:
        raise CurriculumRunStoreError(
            "APP_CURRICULUM_MATERIAL",
            "the playable exercise does not cover its exact active presentation",
        )
    return CurriculumStageProjection(
        stage=stage,
        node=node,
        exercise=exercise,
        presentation=presentation,
        expected=expected,
        support_condition=condition,
        support=support,
        tempo_plan=tempo_plan,
        evidence_context=evidence_context,
    )


def curriculum_plan_to_dict(plan: CurriculumDeliveryPlan) -> dict[str, object]:
    """Return the small browser plan while preserving authoritative references."""

    graph = plan.practice.acquisition
    stages = tuple(project_curriculum_stage(plan, item.node_id) for item in graph.stages)
    return {
        "id": plan.id,
        "run_id": plan.run_id,
        "track": "beginner",
        "policy_identity": graph.tempo_configuration.policy_identity,
        "graph_id": graph.id,
        "analysis_assembly_id": plan.analysis.manifest.id,
        "fundamental_assembly_id": plan.fundamentals.manifest.id,
        "practice_assembly_id": plan.practice.manifest.id,
        "exercises": [_exercise_view(item) for item in stages],
        "nodes": [
            {
                "id": item.stage.node_id,
                "kind": _lesson_node_kind(item.stage.kind),
                "exercise_id": item.expected.exercise_id,
                "prerequisites": (() if index == 0 else (stages[index - 1].stage.node_id,)),
                "successors": (
                    () if index + 1 == len(stages) else (stages[index + 1].stage.node_id,)
                ),
            }
            for index, item in enumerate(stages)
        ],
        "root_node_ids": (() if not stages else (stages[0].stage.node_id,)),
        "diagnostics": [item.code for item in graph.diagnostics],
    }


def curriculum_presentation_to_dict(
    plan: CurriculumDeliveryPlan,
    projection: CurriculumStageProjection,
) -> dict[str, object]:
    """Adapt a curriculum projection to the established browser presentation edge."""

    presentation = projection.presentation
    playback = build_curriculum_expected_playback(
        plan.package,
        presentation,
        tempo_bpm=projection.support.tempo_bpm or plan.reference_tempo_bpm,
    )
    guidance = build_curriculum_passage_guidance(
        plan.analysis.requirements,
        presentation,
    )
    return {
        "contract_id": "org.teachmemusic.curriculum-presentation",
        "contract_version": "0.4.0",
        "plan_id": plan.id,
        "exercise_id": projection.expected.exercise_id,
        "package_id": presentation.package_id,
        "score_id": presentation.score_id,
        "expected_content_sha256": semantic_fingerprint(projection.expected),
        "material_kind": "canonical",
        "measure_ids": presentation.measure_ids,
        "event_ids": presentation.active_target_ids,
        "provenance_ids": (
            presentation.id,
            projection.exercise.id,
            projection.node.id,
        ),
        "measure_numbers": tuple(str(index + 1) for index in range(len(presentation.measure_ids))),
        "primary_skill": projection.node.primitive_ref.id if projection.node.primitive_ref else "",
        "practice_modes": (projection.expected.practice_mode,),
        "boundary_reason": (
            f"{projection.stage.kind.value} for {presentation.notation_condition.value}"
        ),
        "aid_state": {
            "tempo_bpm": _fraction_data(projection.support.tempo_bpm),
            "count_in_enabled": True,
            "count_in_beats": 4,
            "count_in_beat_microseconds": int(
                60_000_000 / float(projection.support.tempo_bpm or Fraction(60))
            ),
            "notation_visible": projection.support.notation_visible,
            "keyboard_visible": projection.support.keyboard_highlighting,
            "pitch_prompts_visible": projection.support.note_names_visible,
        },
        "notation_renderer_sha256": presentation.notation_renderer_sha256,
        "demonstration": playback_plan_to_dict(playback),
        "diagnostics": tuple(item.code for item in presentation.diagnostics),
        "curriculum": {
            "stage": contract_to_data(projection.stage),
            "node": contract_to_data(projection.node),
            "exercise": contract_to_data(projection.exercise),
            "presentation": contract_to_data(presentation),
            "guidance": contract_to_data(guidance),
            "support_condition": projection.support_condition,
            "support": contract_to_data(projection.support),
            "tempo_plan": contract_to_data(projection.tempo_plan),
        },
    }


class CurriculumRunStore:
    """Evaluate real browser attempts through the DEV-009 policy and store."""

    def __init__(
        self,
        evidence_store: CurriculumEvidenceStore,
        *,
        max_runs: int = 4,
    ) -> None:
        self.evidence_store = evidence_store
        self.max_runs = max_runs
        self._runs: dict[str, _ActiveCurriculumRun] = {}
        self._lock = RLock()

    def create(
        self,
        plan: CurriculumDeliveryPlan,
        *,
        authorization: dict[str, object],
        learner_context_id: str,
    ) -> dict[str, object]:
        """Start one authorized run and persist exact static curriculum identities."""

        with self._lock:
            if plan.run_id in self._runs:
                return self.inspect(plan.run_id)
            if len(self._runs) >= self.max_runs:
                raise CurriculumRunStoreError(
                    "APP_CURRICULUM_RUN_CAPACITY", "no additional curriculum run is available"
                )
            if (
                authorization.get("approved") is not True
                or authorization.get("capture_midi") is not True
            ):
                raise CurriculumRunStoreError(
                    "APP_CURRICULUM_AUTHORIZATION", "MIDI evidence capture was not approved"
                )
            first = plan.practice.acquisition.stages[0]
            projection = project_curriculum_stage(plan, first.node_id)
            content = tuple(
                self.evidence_store.put_content(kind, contract_to_data(value))
                for kind, value in (
                    ("curriculum-analysis-manifest", plan.analysis.manifest),
                    ("curriculum-fundamental-manifest", plan.fundamentals.manifest),
                    ("curriculum-practice-manifest", plan.practice.manifest),
                    ("acquisition-graph-slice", plan.practice.acquisition),
                )
            )
            persisted = self.evidence_store.begin_run(
                plan.run_id,
                authorization=authorization,
                metadata={
                    "score_id": plan.score_id,
                    "package_digest_sha256": hashlib.sha256(
                        package_to_json(plan.package).encode("utf-8")
                    ).hexdigest(),
                    "learner_context_id": learner_context_id,
                    "policy_identity": (
                        plan.practice.acquisition.tempo_configuration.policy_identity
                    ),
                },
                content_refs=content,
            )
            if persisted.record_count > 0:
                raise CurriculumRunStoreError(
                    "APP_CURRICULUM_RESUME_REQUIRED",
                    "durable evidence already exists and must be explicitly resumed or deleted",
                )
            self._runs[plan.run_id] = _ActiveCurriculumRun(
                plan=plan,
                authorization=authorization,
                learner_context_id=learner_context_id,
                current_node_id=first.node_id,
                current_condition=projection.support_condition,
            )
            self.evidence_store.append_event(
                plan.run_id,
                event_type="curriculum-run-started",
                monotonic_offset_us=0,
                payload={
                    "plan_id": plan.id,
                    "node_id": first.node_id,
                    "support_state_id": projection.support.id,
                },
            )
            self.evidence_store.flush(plan.run_id, reason="pause")
            return self.inspect(plan.run_id)

    def submit_attempt(
        self,
        run_id: str,
        *,
        calibration: CalibrationProfile,
        attempt: LearnerAttempt,
    ) -> CurriculumAttemptCycle:
        """Align, evaluate, decide, and durably append one real attempt."""

        with self._lock:
            active = self._require(run_id)
            projection = project_curriculum_stage(
                active.plan,
                active.current_node_id,
                support_condition=active.current_condition,
            )
            if (
                attempt.run_id != run_id
                or attempt.exercise_id != projection.expected.exercise_id
                or attempt.support_state_id != projection.support.id
                or attempt.practice_mode != projection.expected.practice_mode
            ):
                raise CurriculumRunStoreError(
                    "APP_CURRICULUM_ATTEMPT_REFERENCE",
                    "the attempt does not match the active curriculum target",
                )
            observations = align_layer_attempt(projection.expected, attempt, calibration)
            current_records = tuple(
                item
                for item in build_curriculum_evidence_records(
                    active.plan.analysis.requirements,
                    projection.expected,
                    attempt,
                    projection.support,
                    observations,
                    projection.evidence_context,
                )
                if projection.node.requirement_ref is not None
                and item.requirement_ref.id == projection.node.requirement_ref.id
            )
            condition_key = (projection.node.id, projection.support.id)
            attempts = (*active.attempts_by_condition.get(condition_key, ()), attempt.id)
            records = (
                *active.evidence_by_condition.get(condition_key, ()),
                *current_records,
            )
            cumulative_observations = (
                *active.observations_by_condition.get(condition_key, ()),
                *observations,
            )
            mastery, unlock = decide_curriculum_unlock(
                active.plan.practice.acquisition,
                projection.node.id,
                projection.support,
                records,
                attempt_sequence=attempts,
                previously_satisfied_node_ids=active.satisfied_node_ids,
            )
            outcome = build_curriculum_exercise_learning_outcome(
                projection.exercise,
                projection.expected,
                attempt,
                calibration,
                projection.support,
                observations,
            )
            reward = build_curriculum_research_reward(outcome, projection.expected, observations)
            decision: CurriculumSupportDecision | TempoTransition
            if projection.stage.kind is AcquisitionStageKind.TEMPO_DIAGNOSTIC:
                decision = self._apply_tempo_result(active, projection, mastery)
            else:
                states = tuple(
                    (
                        condition,
                        project_curriculum_stage(
                            active.plan,
                            projection.node.id,
                            support_condition=condition,
                        ).support,
                    )
                    for condition in projection.exercise.support_envelope.permitted_conditions
                )
                support_decision = decide_curriculum_support(
                    active.plan.practice.acquisition,
                    projection.node.id,
                    projection.support_condition,
                    states,
                    mastery,
                    unlock,
                    decision_sequence=len(active.support_history),
                    history=tuple(
                        item
                        for item in active.support_history
                        if item.node_id == projection.node.id
                    ),
                )
                decision = support_decision
                active.support_history = (*active.support_history, support_decision)
                active.current_node_id = support_decision.target_node_id
                if support_decision.support_condition_after is not None:
                    active.current_condition = support_decision.support_condition_after
                if support_decision.action is CurriculumPolicyAction.PROGRESS:
                    active.satisfied_node_ids = tuple(
                        dict.fromkeys((*active.satisfied_node_ids, projection.node.id))
                    )
                    active.current_condition = project_curriculum_stage(
                        active.plan, active.current_node_id
                    ).support_condition
            active.attempts_by_condition[condition_key] = attempts
            active.evidence_by_condition[condition_key] = records
            active.observations_by_condition[condition_key] = cumulative_observations
            active.attempt_count += 1
            self._append_attempt_evidence(
                active,
                calibration,
                attempt,
                observations,
                current_records,
                mastery,
                unlock,
                outcome,
                reward,
                decision,
            )
            next_projection = project_curriculum_stage(
                active.plan,
                active.current_node_id,
                support_condition=active.current_condition,
            )
            return CurriculumAttemptCycle(
                observations,
                current_records,
                mastery,
                unlock,
                outcome,
                reward,
                decision,
                active.plan,
                next_projection,
                self.inspect(run_id),
            )

    def plan(self, run_id: str) -> CurriculumDeliveryPlan:
        return self._require(run_id).plan

    def projection(self, run_id: str, exercise_id: str) -> CurriculumStageProjection:
        active = self._require(run_id)
        current = project_curriculum_stage(
            active.plan,
            active.current_node_id,
            support_condition=active.current_condition,
        )
        if current.expected.exercise_id != exercise_id:
            raise CurriculumRunStoreError(
                "APP_CURRICULUM_EXERCISE", "only the active curriculum exercise is available"
            )
        return current

    def inspect(self, run_id: str) -> dict[str, object]:
        active = self._require(run_id)
        durable = self.evidence_store.inspect(run_id)
        projection = project_curriculum_stage(
            active.plan,
            active.current_node_id,
            support_condition=active.current_condition,
        )
        return {
            "run_id": run_id,
            "plan_id": active.plan.id,
            "current_node_id": active.current_node_id,
            "current_exercise_id": projection.expected.exercise_id,
            "support_state_id": projection.support.id,
            "attempt_count": active.attempt_count,
            "satisfied_node_count": len(active.satisfied_node_ids),
            "tempo_diagnostic_count": len(active.tempo_evidence),
            "storage": contract_to_data(durable),
        }

    def export(self, run_id: str) -> bytes:
        self._require(run_id)
        return self.evidence_store.export_run(run_id)

    def delete(self, run_id: str) -> None:
        with self._lock:
            if run_id in self._runs:
                self.evidence_store.delete_run(run_id)
                del self._runs[run_id]

    def delete_session(self, session_id: str) -> None:
        with self._lock:
            for run_id, active in tuple(self._runs.items()):
                if active.plan.session_id == session_id:
                    self.evidence_store.delete_run(run_id)
                    del self._runs[run_id]

    def clear(self) -> None:
        """Release live orchestration state without deleting durable owner evidence."""

        with self._lock:
            self._runs.clear()

    def _apply_tempo_result(
        self,
        active: _ActiveCurriculumRun,
        projection: CurriculumStageProjection,
        mastery: CurriculumMasteryProjection,
    ) -> TempoTransition:
        percent = projection.support.tempo_percent
        passed = mastery.status is CurriculumMasteryStatus.MASTERED
        transition = decide_tempo_probe(
            projection.tempo_plan,
            TempoProbeResult(percent, passed, passed, mastery.id),
        )
        if passed:
            scope_ref = projection.tempo_plan.practice_scope_ref
            active.tempo_evidence[scope_ref.id] = CompatibleTempoEvidence(
                scope_ref,
                "independent-piece",
                percent,
                percent,
                True,
                True,
                (mastery.id,),
            )
            stages = active.plan.practice.acquisition.stages
            index = next(
                index for index, item in enumerate(stages) if item.node_id == projection.node.id
            )
            if index + 1 < len(stages):
                next_node = stages[index + 1].node_id
                active.current_node_id = next_node
                active.current_condition = project_curriculum_stage(
                    active.plan, next_node
                ).support_condition
            else:
                active.plan = assemble_curriculum_delivery(
                    active.plan.package,
                    score_id=active.plan.score_id,
                    session_id=active.plan.session_id,
                    reference_tempo_bpm=active.plan.reference_tempo_bpm,
                    tempo_evidence=tuple(active.tempo_evidence.values()),
                )
                first = active.plan.practice.acquisition.stages[0]
                active.current_node_id = first.node_id
                active.current_condition = project_curriculum_stage(
                    active.plan, first.node_id
                ).support_condition
                for kind, value in (
                    ("curriculum-practice-manifest", active.plan.practice.manifest),
                    ("acquisition-graph-slice", active.plan.practice.acquisition),
                ):
                    reference = self.evidence_store.put_content(kind, contract_to_data(value))
                    self.evidence_store.attach_content(active.plan.run_id, reference)
        elif transition.next_probe_percentage is not None:
            active.current_condition = f"tempo-probe-{transition.next_probe_percentage}"
        return transition

    def _append_attempt_evidence(
        self,
        active: _ActiveCurriculumRun,
        calibration: object,
        attempt: LearnerAttempt,
        observations: tuple[object, ...],
        records: tuple[object, ...],
        mastery: object,
        unlock: object,
        outcome: object,
        reward: object,
        decision: object,
    ) -> None:
        payloads = (
            ("calibration", calibration),
            ("learner-attempt", attempt),
            *(("performance-observation", item) for item in observations),
            *(("curriculum-evidence-record", item) for item in records),
            ("curriculum-mastery-projection", mastery),
            ("curriculum-unlock-decision", unlock),
            ("curriculum-learning-outcome", outcome),
            ("curriculum-research-reward", reward),
            ("curriculum-policy-decision", decision),
        )
        duration = max(0, attempt.end_microseconds - attempt.start_microseconds)
        offset = max(active.last_evidence_offset_us + 1, duration)
        for event_type, payload in payloads:
            self.evidence_store.append_event(
                active.plan.run_id,
                event_type=event_type,
                monotonic_offset_us=offset,
                payload=contract_to_data(payload),
            )
        active.last_evidence_offset_us = offset
        self.evidence_store.flush(active.plan.run_id, reason="attempt-end")

    def _require(self, run_id: str) -> _ActiveCurriculumRun:
        active = self._runs.get(run_id)
        if active is None:
            raise CurriculumRunStoreError(
                "APP_CURRICULUM_RUN_NOT_FOUND", "the curriculum run is unavailable"
            )
        return active


def _practice_mode(context: EvidenceContext) -> PracticeMode:
    if context is EvidenceContext.INDEPENDENT:
        return PracticeMode.INDEPENDENT_PERFORMANCE
    if context is EvidenceContext.RETENTION:
        return PracticeMode.RETENTION
    if context is EvidenceContext.TRANSFER:
        return PracticeMode.TRANSFER
    return PracticeMode.SUPPORTED_PERFORMANCE


def _evidence_context(value: str) -> EvidenceContext:
    if value in {"diagnostic", "tempo-diagnostic", "acquisition", "component-acquisition"}:
        return EvidenceContext.ACQUISITION
    if value in {"passage-application", "connected-learned-to-date", "tempo-development"}:
        return EvidenceContext.INDEPENDENT
    if value in {"coordination-preparation", "integration"}:
        return EvidenceContext.INTEGRATION
    if value == "retention":
        return EvidenceContext.RETENTION
    if value == "transfer":
        return EvidenceContext.TRANSFER
    raise CurriculumRunStoreError(
        "APP_CURRICULUM_EVIDENCE_CONTEXT", "the exercise evidence context is unsupported"
    )


def _condition_percent(condition: str, plan: ControlledTempoPlan) -> int:
    if condition.startswith("tempo-probe-"):
        return int(condition.rsplit("-", 1)[1])
    return plan.current_controlled_percentage or 70


def _support_state(
    exercise: ExerciseInstance,
    presentation: CurriculumPassagePresentation,
    condition: str,
    percent: int,
    tempo: Fraction,
) -> SupportState:
    independent = condition == exercise.support_envelope.independent_condition
    token = hashlib.sha256(f"{exercise.id}|{condition}|{percent}|{tempo}".encode()).hexdigest()[:24]
    return SupportState(
        id=f"support:curriculum:{token}",
        notation_visible=True,
        cursor_visible=not independent,
        note_names_visible=False,
        keyboard_highlighting=not independent,
        fingering_visible=False,
        demonstration_available=not independent,
        follow_mode=False,
        metronome=True,
        tempo_percent=percent,
        isolated_layers=(presentation.notation_condition.value,),
        isolated_dimensions=(),
        prompts_visible=not independent,
        tempo_bpm=tempo,
    )


def _exercise_view(projection: CurriculumStageProjection) -> dict[str, object]:
    support = projection.support
    return {
        "id": projection.expected.exercise_id,
        "primary_skill": (
            projection.node.primitive_ref.id if projection.node.primitive_ref else "curriculum"
        ),
        "secondary_skills": [],
        "practice_modes": [projection.expected.practice_mode],
        "boundary_reason": (
            f"{projection.stage.kind.value} for {projection.presentation.notation_condition.value}"
        ),
        "initial_support": _support_data(support),
        "curriculum_node_id": projection.node.id,
        "support_condition": projection.support_condition,
    }


def _lesson_node_kind(kind: AcquisitionStageKind) -> str:
    if kind in {
        AcquisitionStageKind.SELF_PACED_COORDINATION,
        AcquisitionStageKind.PULSE_INTEGRATION,
        AcquisitionStageKind.LEARNED_TO_DATE,
    }:
        return "integration"
    return "exercise"


def _fraction_data(value: Fraction | None) -> dict[str, int] | None:
    if value is None:
        return None
    return {"numerator": value.numerator, "denominator": value.denominator}


def _support_data(support: SupportState) -> dict[str, object]:
    return {
        "id": support.id,
        "tempo_bpm": _fraction_data(support.tempo_bpm),
        "notation_visible": support.notation_visible,
        "cursor_visible": support.cursor_visible,
        "note_names_visible": support.note_names_visible,
        "keyboard_highlighting": support.keyboard_highlighting,
        "fingering_visible": support.fingering_visible,
        "demonstration_available": support.demonstration_available,
        "follow_mode": support.follow_mode,
        "metronome": support.metronome,
        "tempo_percent": support.tempo_percent,
        "prompts_visible": support.prompts_visible,
    }


def default_curriculum_store(root: str | os.PathLike[str]) -> CurriculumRunStore:
    """Create the production store with the frozen bounded policy."""

    return CurriculumRunStore(CurriculumEvidenceStore(Path(root), policy=CurriculumStoragePolicy()))
