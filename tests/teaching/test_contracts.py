"""Tests for lesson, evidence, and run-provenance contracts."""

from dataclasses import FrozenInstanceError, replace
from fractions import Fraction

import pytest

from teachmemusic.performance import ObservationDimension, ObservationSource
from teachmemusic.teaching import (
    CanonicalAnchor,
    CanonicalAnchorKind,
    CanonicalAnchorSet,
    ContractVersionSet,
    DataAuthorization,
    DemandDimension,
    EvidenceContext,
    EvidenceExport,
    EvidenceRecord,
    EvidenceRequirement,
    EvidenceState,
    Exercise,
    ExpectedFact,
    FeedbackAction,
    FeedbackTiming,
    LearnerContextSnapshot,
    LearnerTrack,
    LessonNode,
    LessonNodeKind,
    LessonPlan,
    PlanAudit,
    PlanAuditOutcome,
    PlanIntervention,
    PolicyAction,
    PolicyDecision,
    PracticeMode,
    RunEvent,
    RunEventKind,
    SkillDomain,
    SupportState,
    TaskDemand,
    TeachingRunManifest,
    TeachingSerializationError,
    evidence_export_from_json,
    evidence_export_to_json,
    lesson_plan_from_dict,
    lesson_plan_from_json,
    lesson_plan_to_dict,
    lesson_plan_to_json,
    validate_evidence_export,
    validate_lesson_plan,
)
from tests.performance.test_contracts import valid_performance_bundle

_DIGEST = "a" * 64


def valid_lesson_plan() -> LessonPlan:
    """Return one minimal source-anchored lesson graph."""

    support = SupportState(
        id="support:one",
        notation_visible=True,
        cursor_visible=True,
        note_names_visible=True,
        keyboard_highlighting=True,
        fingering_visible=False,
        demonstration_available=True,
        follow_mode=True,
        metronome=False,
        tempo_percent=60,
        max_replays=5,
        prompts_visible=True,
    )
    exercise = Exercise(
        id="exercise:one",
        anchor_set=CanonicalAnchorSet(
            id="anchor-set:one",
            package_id="package:one",
            score_id="score:one",
            anchors=(
                CanonicalAnchor(CanonicalAnchorKind.SCORE, "score:one"),
                CanonicalAnchor(CanonicalAnchorKind.EVENT, "event:score-note-1"),
            ),
            start_quarters=Fraction(0),
            end_quarters=Fraction(1, 3),
        ),
        boundary_reason="One short, playable pitch target.",
        layer_scope=("part:piano",),
        primary_skill=SkillDomain.PITCH,
        secondary_skills=(SkillDomain.READING,),
        task_demands=(
            TaskDemand(
                id="demand:one",
                dimension=DemandDimension.PASSAGE_LENGTH,
                level=1,
                evidence_canonical_ids=("event:score-note-1",),
                rationale="A single event is a bounded beginner target.",
            ),
        ),
        expected_facts=(
            ExpectedFact(
                id="expected-fact:one",
                dimension=ObservationDimension.PITCH,
                canonical_ids=("event:score-note-1",),
                expected_value="midi:60",
                observable_sources=(ObservationSource.MIDI,),
            ),
        ),
        practice_modes=(PracticeMode.SUPPORTED_PERFORMANCE,),
        initial_support=support,
        exit_evidence=(
            EvidenceRequirement(
                id="evidence-requirement:one",
                dimension=ObservationDimension.PITCH,
                minimum_state=EvidenceState.ATTEMPTED,
                context=EvidenceContext.ACQUISITION,
            ),
        ),
    )
    return LessonPlan(
        id="lesson-plan:one",
        run_id="run:one",
        input_digest_sha256=_DIGEST,
        generated_at_utc="2026-09-30T12:00:00Z",
        planner_version="planner-v1",
        policy_version="policy-v1",
        track=LearnerTrack.BEGINNER,
        target_skills=(SkillDomain.PITCH, SkillDomain.READING),
        exercises=(exercise,),
        nodes=(
            LessonNode(
                id="lesson-node:one",
                kind=LessonNodeKind.EXERCISE,
                exercise_id=exercise.id,
            ),
        ),
        root_node_ids=("lesson-node:one",),
    )


def valid_evidence_export() -> EvidenceExport:
    """Return a complete linked local-first teaching evidence record."""

    plan = valid_lesson_plan()
    performance = valid_performance_bundle()
    learner = LearnerContextSnapshot(
        id="learner-context:one",
        track=LearnerTrack.BEGINNER,
        goals=("Learn the selected score accurately.",),
    )
    authorization = DataAuthorization(
        id="data-authorization:one",
        approved=True,
        approved_at_utc="2026-09-30T11:59:00Z",
        capture_midi=True,
        capture_self_report=True,
        capture_environment=False,
        allow_export=True,
    )
    manifest = TeachingRunManifest(
        id="run:one",
        created_at_utc="2026-09-30T12:00:00Z",
        score_digest_sha256=_DIGEST,
        package_id="package:one",
        score_id="score:one",
        scope_label="one-note contract test",
        learner_context_id=learner.id,
        data_authorization_id=authorization.id,
        versions=ContractVersionSet(
            application_version="0.0.0",
            canonical_schema_id="org.teachmemusic.canonical-score",
            canonical_schema_version="2.0.0",
            parser_version="parser-v1",
            analysis_version="analysis-v1",
            planner_version="planner-v1",
            policy_version="policy-v1",
            feedback_version="feedback-v1",
            calibration_version="calibration-v1",
        ),
    )
    audit = PlanAudit(
        id="plan-audit:one",
        plan_id=plan.id,
        reviewer="owner",
        reviewed_at_utc="2026-09-30T12:00:30Z",
        outcome=PlanAuditOutcome.PASS_NO_CHANGE,
        source_faithful=True,
        musically_coherent=True,
        safe=True,
        executable=True,
    )
    evidence = EvidenceRecord(
        id="evidence-record:one",
        attempt_id="attempt:one",
        exercise_id="exercise:one",
        requirement_id="evidence-requirement:one",
        dimension=ObservationDimension.PITCH,
        state=EvidenceState.ATTEMPTED,
        context=EvidenceContext.ACQUISITION,
        observation_ids=("observation:pitch-one",),
        support_state_id="support:one",
    )
    feedback = FeedbackAction(
        id="feedback:one",
        evidence_record_ids=(evidence.id,),
        timing=FeedbackTiming.END_OF_ATTEMPT,
        target="Pitch C4",
        observation="The expected pitch was played.",
        boundary=None,
        action="Repeat once with the same support.",
        reason="One attempt is not stable evidence.",
    )
    decision = PolicyDecision(
        id="policy-decision:one",
        run_id=manifest.id,
        exercise_id="exercise:one",
        action=PolicyAction.STABILIZE,
        evidence_record_ids=(evidence.id,),
        feedback_id=feedback.id,
        reason="Collect repeated evidence before reducing support.",
        policy_version="policy-v1",
        next_node_id="lesson-node:one",
        created_at_utc="2026-09-30T12:02:00Z",
    )
    event_payloads = (
        (RunEventKind.RUN_CREATED, manifest.id),
        (RunEventKind.DATA_AUTHORIZED, authorization.id),
        (RunEventKind.PLAN_GENERATED, plan.id),
        (RunEventKind.PLAN_AUDITED, audit.id),
        (RunEventKind.CALIBRATION_RECORDED, "calibration:one"),
        (RunEventKind.ATTEMPT_RECORDED, "attempt:one"),
        (RunEventKind.OBSERVATION_RECORDED, "observation:pitch-one"),
        (RunEventKind.EVIDENCE_RECORDED, evidence.id),
        (RunEventKind.FEEDBACK_RECORDED, feedback.id),
        (RunEventKind.POLICY_DECIDED, decision.id),
    )
    events = tuple(
        RunEvent(
            id=f"run-event:{index}",
            run_id=manifest.id,
            sequence_number=index,
            kind=kind,
            payload_id=payload_id,
            occurred_at_utc=f"2026-09-30T12:02:{index:02d}Z",
        )
        for index, (kind, payload_id) in enumerate(event_payloads)
    )
    return EvidenceExport(
        id="evidence-export:one",
        exported_at_utc="2026-09-30T12:03:00Z",
        manifest=manifest,
        learner_context=learner,
        data_authorization=authorization,
        plans=(plan,),
        audits=(audit,),
        performance=performance,
        evidence_records=(evidence,),
        feedback_actions=(feedback,),
        policy_decisions=(decision,),
        run_events=events,
    )


def test_lesson_plan_round_trip_preserves_exact_score_time() -> None:
    """TEST-TEACH-CONTRACT-001: exact score time survives strict round trips."""

    plan = valid_lesson_plan()
    payload = lesson_plan_to_json(plan)

    assert validate_lesson_plan(plan) == ()
    assert lesson_plan_from_json(payload) == plan
    assert lesson_plan_from_dict(lesson_plan_to_dict(plan)) == plan
    assert '"denominator": 3' in payload
    assert lesson_plan_to_json(plan) == payload


def test_evidence_export_round_trips_with_complete_provenance() -> None:
    """TEST-TEACH-CONTRACT-002: linked evidence survives the public boundary."""

    export = valid_evidence_export()
    payload = evidence_export_to_json(export)

    assert validate_evidence_export(export) == ()
    assert evidence_export_from_json(payload) == export
    assert evidence_export_to_json(export) == payload


def test_lesson_plan_is_immutable_and_requires_namespaced_ids() -> None:
    """TEST-TEACH-CONTRACT-003: plans are immutable and use stable identities."""

    plan = valid_lesson_plan()
    with pytest.raises(FrozenInstanceError):
        plan.id = "lesson-plan:changed"  # type: ignore[misc]

    issues = validate_lesson_plan(replace(plan, id="not namespaced"))
    assert "TEACH_STABLE_ID" in {issue.code for issue in issues}
    track_issues = validate_lesson_plan(
        replace(plan, track="expert")  # type: ignore[arg-type]
    )
    assert "TEACH_LEARNER_TRACK" in {issue.code for issue in track_issues}


def test_lesson_plan_rejects_unreachable_graph_nodes() -> None:
    """TEST-TEACH-CONTRACT-004: every lesson node is reachable from a root."""

    plan = valid_lesson_plan()
    extra = LessonNode(
        id="lesson-node:orphan",
        kind=LessonNodeKind.EXERCISE,
        exercise_id="exercise:one",
    )
    issues = validate_lesson_plan(replace(plan, nodes=(*plan.nodes, extra)))

    assert "TEACH_GRAPH_UNREACHABLE" in {issue.code for issue in issues}


def test_pedagogical_plan_edits_must_be_explicitly_qualified() -> None:
    """TEST-TEACH-CONTRACT-005: human pedagogical edits are qualified."""

    export = valid_evidence_export()
    intervention = PlanIntervention(
        id="plan-intervention:one",
        plan_id="lesson-plan:one",
        path="exercises[0].practice_modes",
        before_json='["supported-performance"]',
        after_json='["ear-first"]',
        reason="Human teaching judgment.",
        pedagogical=True,
    )
    bad_audit = replace(export.audits[0], interventions=(intervention,))
    issues = validate_evidence_export(replace(export, audits=(bad_audit,)))

    codes = {issue.code for issue in issues}
    assert "TEACH_AUDIT_QUALIFICATION" in codes
    assert "TEACH_AUDIT_INTERVENTION" in codes


def test_teaching_decoder_rejects_unknown_contract_fields() -> None:
    """TEST-TEACH-CONTRACT-006: strict decoding rejects schema drift."""

    data = lesson_plan_to_dict(valid_lesson_plan())
    data["mystery"] = "value"

    with pytest.raises(TeachingSerializationError, match="unexpected"):
        lesson_plan_from_dict(data)

    with pytest.raises(TeachingSerializationError, match="TEACH_CONTRACT_VERSION"):
        evidence_export_to_json(replace(valid_evidence_export(), contract_version="unsupported"))


def test_export_rejects_cross_boundary_reference_drift() -> None:
    """TEST-TEACH-CONTRACT-007: cross-boundary reference drift is rejected."""

    export = valid_evidence_export()
    attempt = replace(export.performance.attempts[0], exercise_id="exercise:missing")
    performance = replace(export.performance, attempts=(attempt,))
    issues = validate_evidence_export(replace(export, performance=performance))

    assert "TEACH_EXERCISE_REFERENCE" in {issue.code for issue in issues}

    support_attempt = replace(
        export.performance.attempts[0],
        support_state_id="support:missing",
    )
    support_performance = replace(export.performance, attempts=(support_attempt,))
    support_issues = validate_evidence_export(replace(export, performance=support_performance))
    assert "TEACH_SUPPORT_REFERENCE" in {issue.code for issue in support_issues}
