"""Bounded orchestration for one local deterministic teaching run."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, replace
from threading import RLock
from typing import Never

from teachmemusic import __version__
from teachmemusic.analysis import ANALYSIS_VERSION
from teachmemusic.performance import (
    ALIGNMENT_POLICY_VERSION,
    CalibrationProfile,
    LearnerAttempt,
    Observation,
    ObservationStatus,
    PerformanceBundle,
    align_attempt,
)
from teachmemusic.score import CanonicalMusicPackage, package_to_json
from teachmemusic.teaching import (
    BEGINNER_PLAN_POLICY_VERSION,
    PLANNER_VERSION,
    TEACHING_CONTRACT_VERSION,
    TEACHING_POLICY_VERSION,
    ContractVersionSet,
    DataAuthorization,
    EvidenceArchive,
    EvidenceExport,
    EvidenceInspection,
    Exercise,
    LearnerContextSnapshot,
    LessonPlan,
    PlanAudit,
    RunEventKind,
    SupportState,
    TeachingPolicyResult,
    TeachingRunManifest,
    append_evidence_payload,
    append_run_event,
    apply_teaching_policy,
    build_expected_performance,
    create_evidence_archive,
    evidence_export_to_json,
    inspect_evidence_archive,
    resume_evidence_archive,
    summarize_guided_mastery,
)
from teachmemusic.teaching.evidence import EvidencePayload
from teachmemusic.teaching.presentation import ExercisePresentation

FEEDBACK_VERSION = "deterministic-feedback-template-v1"
CALIBRATION_VERSION = "casio-browser-calibration-v1"
PARSER_VERSION = "musicxml-canonical-package-v1"


class TeachingRunStoreError(ValueError):
    """Stable failure at the local teaching-run orchestration boundary."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(f"{code}: {message}")


@dataclass(frozen=True, slots=True)
class TeachingCycle:
    """One result returned to the local owner UI."""

    result: TeachingPolicyResult
    inspection: EvidenceInspection


@dataclass(slots=True)
class _ActiveRun:
    session_id: str
    evidence: EvidenceExport
    history: tuple[TeachingPolicyResult, ...] = ()


class TeachingRunStore:
    """Keep a bounded set of local runs while preserving immutable evidence."""

    def __init__(self, *, max_runs: int = 4) -> None:
        if max_runs <= 0:
            raise ValueError("max_runs must be positive")
        self._max_runs = max_runs
        self._runs: dict[str, _ActiveRun] = {}
        self._lock = RLock()

    def create(
        self,
        *,
        session_id: str,
        package: CanonicalMusicPackage,
        score_id: str,
        plan: LessonPlan,
        learner: LearnerContextSnapshot,
        authorization: DataAuthorization,
        audit: PlanAudit,
        created_at_utc: str,
    ) -> EvidenceInspection:
        """Create one explicitly authorized, audited run from an untouched plan."""

        with self._lock:
            existing = self._runs.get(plan.run_id)
            if existing is not None:
                if existing.session_id != session_id or existing.evidence.plans != (plan,):
                    raise TeachingRunStoreError(
                        "APP_TEACHING_RUN_CONFLICT", "the run identity is already in use"
                    )
                return self.inspect(plan.run_id)
            if len(self._runs) >= self._max_runs:
                raise TeachingRunStoreError(
                    "APP_TEACHING_RUN_CAPACITY", "no additional teaching run is available"
                )
            if plan.input_digest_sha256 == "" or audit.plan_id != plan.id:
                raise TeachingRunStoreError(
                    "APP_TEACHING_RUN_PLAN", "the audit does not identify the untouched plan"
                )
            if not authorization.approved:
                raise TeachingRunStoreError(
                    "APP_TEACHING_RUN_AUTHORIZATION", "local evidence capture was not approved"
                )
            manifest = TeachingRunManifest(
                id=plan.run_id,
                created_at_utc=created_at_utc,
                score_digest_sha256=plan.input_digest_sha256,
                package_id=package.id.value,
                score_id=score_id,
                scope_label="Owner-selected Beginner teaching run",
                learner_context_id=learner.id,
                data_authorization_id=authorization.id,
                versions=_versions(package),
            )
            token = _token(plan.run_id)
            evidence = EvidenceExport(
                id=f"evidence-export:{token}",
                exported_at_utc=created_at_utc,
                manifest=manifest,
                learner_context=learner,
                data_authorization=authorization,
                plans=(plan,),
                audits=(audit,),
                performance=PerformanceBundle(),
                omissions=(
                    "No microphone audio, video, biometric, cloud, posture, fingering, "
                    "acoustic-tone, or interpretive inference is captured.",
                ),
            )
            for kind, payload_id in (
                (RunEventKind.RUN_CREATED, manifest.id),
                (RunEventKind.DATA_AUTHORIZED, authorization.id),
                (RunEventKind.PLAN_GENERATED, plan.id),
                (RunEventKind.PLAN_AUDITED, audit.id),
            ):
                evidence = _append_event(evidence, kind, payload_id, created_at_utc)
            self._runs[plan.run_id] = _ActiveRun(session_id=session_id, evidence=evidence)
            return _inspection(evidence)

    def submit_attempt(
        self,
        *,
        run_id: str,
        presentation: ExercisePresentation,
        calibration: CalibrationProfile,
        attempt: LearnerAttempt,
        support: SupportState,
        created_at_utc: str,
        unsafe_condition: str | None = None,
    ) -> TeachingCycle:
        """Align, decide, and append one complete attempt as one locked operation."""

        with self._lock:
            active = self._require(run_id)
            plan = active.evidence.plans[0]
            exercise = next(
                (item for item in plan.exercises if item.id == attempt.exercise_id),
                None,
            )
            if exercise is None:
                raise TeachingRunStoreError(
                    "APP_TEACHING_EXERCISE", "the attempt exercise is absent from the plan"
                )
            if attempt.run_id != run_id or presentation.plan_id != plan.id:
                raise TeachingRunStoreError(
                    "APP_TEACHING_RUN_REFERENCE", "the submitted evidence belongs to another run"
                )
            if attempt.support_state_id != support.id:
                raise TeachingRunStoreError(
                    "APP_TEACHING_SUPPORT", "the attempt and support identities differ"
                )
            try:
                mode = next(
                    item for item in exercise.practice_modes if item.value == attempt.practice_mode
                )
            except StopIteration as error:
                raise TeachingRunStoreError(
                    "APP_TEACHING_MODE", "the practice mode is not allowed for this exercise"
                ) from error
            expected = build_expected_performance(exercise, presentation, mode)
            observations = align_attempt(expected, attempt, calibration)
            result = apply_teaching_policy(
                plan,
                attempt,
                support,
                observations,
                created_at_utc=created_at_utc,
                history=active.history,
                unsafe_condition=unsafe_condition,
            )
            evidence = active.evidence
            known_calibrations = {item.id: item for item in evidence.performance.calibrations}
            previous_calibration = known_calibrations.get(calibration.id)
            if previous_calibration is not None and previous_calibration != calibration:
                raise TeachingRunStoreError(
                    "APP_TEACHING_CALIBRATION_CHANGED",
                    "an existing calibration identity changed",
                )
            if previous_calibration is None:
                evidence = _append_payload(evidence, calibration, created_at_utc)
            initial_support_ids = {item.initial_support.id for item in plan.exercises}
            known_support_ids = {item.id for item in evidence.support_states} | initial_support_ids
            if support.id not in known_support_ids:
                evidence = _append_payload(evidence, support, created_at_utc)
                known_support_ids.add(support.id)
            evidence = _append_payload(evidence, attempt, created_at_utc)
            for observation in observations:
                evidence = _append_payload(evidence, observation, created_at_utc)
            for record in result.evidence_records:
                evidence = _append_payload(evidence, record, created_at_utc)
            evidence = _append_payload(evidence, result.feedback, created_at_utc)
            evidence = _append_payload(evidence, result.decision, created_at_utc)
            if result.next_support is not None and result.next_support.id not in known_support_ids:
                evidence = _append_payload(evidence, result.next_support, created_at_utc)
            active.evidence = evidence
            active.history = (*active.history, result)
            return TeachingCycle(result=result, inspection=_inspection(evidence))

    def archive(self, run_id: str, *, exported_at_utc: str) -> EvidenceArchive:
        """Append an export event when needed and create a deterministic archive."""

        with self._lock:
            active = self._require(run_id)
            evidence = active.evidence
            latest_export_sequence = max(
                (
                    event.sequence_number
                    for event in evidence.run_events
                    if event.kind is RunEventKind.EXPORTED
                ),
                default=-1,
            )
            if latest_export_sequence != len(evidence.run_events) - 1:
                evidence = _append_event(
                    replace(evidence, exported_at_utc=exported_at_utc),
                    RunEventKind.EXPORTED,
                    evidence.id,
                    exported_at_utc,
                )
                active.evidence = evidence
            return create_evidence_archive(evidence)

    def resume(
        self,
        *,
        session_id: str,
        package: CanonicalMusicPackage,
        score_id: str,
        archive: EvidenceArchive,
    ) -> EvidenceInspection:
        """Restore one verified archive against the exact current score and versions."""

        with self._lock:
            evidence = resume_evidence_archive(
                archive,
                score_digest_sha256=hashlib.sha256(
                    package_to_json(package).encode("utf-8")
                ).hexdigest(),
                package_id=package.id.value,
                score_id=score_id,
                compatible_versions=_versions(package),
            )
            run_id = evidence.manifest.id
            existing = self._runs.get(run_id)
            if existing is None and len(self._runs) >= self._max_runs:
                raise TeachingRunStoreError(
                    "APP_TEACHING_RUN_CAPACITY", "no additional teaching run is available"
                )
            self._runs[run_id] = _ActiveRun(
                session_id=session_id,
                evidence=evidence,
                history=_restore_history(evidence),
            )
            return inspect_evidence_archive(archive)

    def inspect(self, run_id: str) -> EvidenceInspection:
        """Inspect a live run without inventing the archive export event."""

        with self._lock:
            return _inspection(self._require(run_id).evidence)

    def evidence(self, run_id: str) -> EvidenceExport:
        """Return the current immutable evidence snapshot."""

        with self._lock:
            return self._require(run_id).evidence

    def session_id(self, run_id: str) -> str:
        """Return the canonical score-session identity bound to a run."""

        with self._lock:
            return self._require(run_id).session_id

    def support(self, run_id: str, exercise_id: str, support_id: str) -> SupportState:
        """Resolve one server-issued support state for an exercise attempt."""

        with self._lock:
            evidence = self._require(run_id).evidence
            plan = evidence.plans[0]
            exercise = next((item for item in plan.exercises if item.id == exercise_id), None)
            if exercise is None:
                raise TeachingRunStoreError(
                    "APP_TEACHING_EXERCISE", "the exercise is absent from the run"
                )
            candidates = (exercise.initial_support, *evidence.support_states)
            support = next((item for item in candidates if item.id == support_id), None)
            if support is None:
                raise TeachingRunStoreError(
                    "APP_TEACHING_SUPPORT", "the support state is absent from the run"
                )
            return support

    def delete(self, run_id: str) -> bool:
        """Delete one exact active run."""

        with self._lock:
            return self._runs.pop(run_id, None) is not None

    def delete_session(self, session_id: str) -> None:
        """Delete every teaching run owned by one expiring score session."""

        with self._lock:
            for run_id in tuple(
                key for key, value in self._runs.items() if value.session_id == session_id
            ):
                del self._runs[run_id]

    def clear(self) -> None:
        with self._lock:
            self._runs.clear()

    def _require(self, run_id: str) -> _ActiveRun:
        active = self._runs.get(run_id)
        if active is None:
            raise TeachingRunStoreError(
                "APP_TEACHING_RUN_NOT_FOUND", "the local teaching run is unavailable"
            )
        return active


def _versions(package: CanonicalMusicPackage) -> ContractVersionSet:
    return ContractVersionSet(
        application_version=__version__,
        canonical_schema_id=package.schema_id,
        canonical_schema_version=package.schema_version,
        parser_version=PARSER_VERSION,
        analysis_version=ANALYSIS_VERSION,
        planner_version=f"{PLANNER_VERSION};{BEGINNER_PLAN_POLICY_VERSION}",
        policy_version=f"{ALIGNMENT_POLICY_VERSION};{TEACHING_POLICY_VERSION}",
        feedback_version=FEEDBACK_VERSION,
        calibration_version=CALIBRATION_VERSION,
        teaching_contract_version=TEACHING_CONTRACT_VERSION,
    )


def _append_event(
    evidence: EvidenceExport,
    kind: RunEventKind,
    payload_id: str,
    occurred_at_utc: str,
) -> EvidenceExport:
    return append_run_event(
        evidence,
        kind=kind,
        payload_id=payload_id,
        event_id=f"run-event:{_token(evidence.manifest.id)}:{len(evidence.run_events)}",
        occurred_at_utc=occurred_at_utc,
    )


def _append_payload(
    evidence: EvidenceExport,
    payload: EvidencePayload,
    occurred_at_utc: str,
) -> EvidenceExport:
    return append_evidence_payload(
        evidence,
        payload,
        event_id=f"run-event:{_token(evidence.manifest.id)}:{len(evidence.run_events)}",
        occurred_at_utc=occurred_at_utc,
    )


def _inspection(evidence: EvidenceExport) -> EvidenceInspection:
    return EvidenceInspection(
        run_id=evidence.manifest.id,
        score_digest_sha256=evidence.manifest.score_digest_sha256,
        evidence_sha256=hashlib.sha256(
            evidence_export_to_json(evidence).encode("utf-8")
        ).hexdigest(),
        plan_count=len(evidence.plans),
        audit_count=len(evidence.audits),
        support_count=(
            len(evidence.support_states) + sum(len(plan.exercises) for plan in evidence.plans)
        ),
        calibration_count=len(evidence.performance.calibrations),
        attempt_count=len(evidence.performance.attempts),
        observation_count=len(evidence.performance.observations),
        evidence_record_count=len(evidence.evidence_records),
        feedback_count=len(evidence.feedback_actions),
        policy_decision_count=len(evidence.policy_decisions),
        journal_entry_count=len(evidence.journal_entries),
        gate_decision_count=len(evidence.gate_decisions),
        event_count=len(evidence.run_events),
        latest_sequence_number=(
            evidence.run_events[-1].sequence_number if evidence.run_events else None
        ),
        has_pedagogical_intervention=any(
            intervention.pedagogical
            for audit in evidence.audits
            for intervention in audit.interventions
        ),
        omissions=evidence.omissions,
    )


def _restore_history(evidence: EvidenceExport) -> tuple[TeachingPolicyResult, ...]:
    """Restore the pure-policy history needed to continue an imported run."""

    plan = evidence.plans[0]
    exercises = {item.id: item for item in plan.exercises}
    attempts = {item.id: item for item in evidence.performance.attempts}
    observations = evidence.performance.observations
    records = {item.id: item for item in evidence.evidence_records}
    feedback = {item.id: item for item in evidence.feedback_actions}
    supports = {item.initial_support.id: item.initial_support for item in plan.exercises} | {
        item.id: item for item in evidence.support_states
    }
    event_positions = {item.payload_id: index for index, item in enumerate(evidence.run_events)}
    support_events = tuple(
        (index, item.payload_id)
        for index, item in enumerate(evidence.run_events)
        if item.kind is RunEventKind.SUPPORT_RECORDED
    )
    history: list[TeachingPolicyResult] = []
    for decision in evidence.policy_decisions:
        decision_records = tuple(records[item] for item in decision.evidence_record_ids)
        if not decision_records:
            raise TeachingRunStoreError(
                "APP_TEACHING_RESUME_HISTORY", "a policy decision has no evidence records"
            )
        attempt = attempts[decision_records[0].attempt_id]
        attempt_observations = tuple(item for item in observations if item.attempt_id == attempt.id)
        exercise = exercises[attempt.exercise_id]
        next_support = None
        position = event_positions[decision.id]
        later_supports = tuple(
            supports[payload_id]
            for event_position, payload_id in support_events
            if event_position == position + 1
        )
        if later_supports:
            next_support = later_supports[0]
        history.append(
            TeachingPolicyResult(
                attempt_id=attempt.id,
                exercise_id=attempt.exercise_id,
                support=supports[attempt.support_state_id],
                observations=attempt_observations,
                evidence_records=decision_records,
                feedback=feedback[decision.feedback_id]
                if decision.feedback_id
                else _missing_feedback(),
                decision=decision,
                discrepancy_signature=_discrepancy_signature(attempt_observations, exercise),
                next_support=next_support,
                mastery=summarize_guided_mastery(
                    plan.track,
                    exercise,
                    supports[attempt.support_state_id],
                    attempt_observations,
                    tuple(history),
                ),
            )
        )
    return tuple(history)


def _discrepancy_signature(
    observations: tuple[Observation, ...], exercise: Exercise
) -> tuple[str, ...]:
    required = {item.dimension for item in exercise.exit_evidence}
    return tuple(
        sorted(
            "|".join(
                (
                    item.dimension.value,
                    item.expected_value or "",
                    item.observed_value or "",
                    ",".join(item.expected_canonical_ids),
                )
            )
            for item in observations
            if item.dimension in required and item.status is ObservationStatus.DISCREPANCY
        )
    )


def _missing_feedback() -> Never:
    raise TeachingRunStoreError("APP_TEACHING_RESUME_HISTORY", "a policy decision has no feedback")


def _token(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:20]
