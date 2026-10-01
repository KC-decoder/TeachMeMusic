"""Invariant validation for teaching and learner-evidence contracts."""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass

from teachmemusic.performance import (
    PERFORMANCE_CONTRACT_VERSION,
    ObservationDimension,
    ObservationSource,
    validate_performance_bundle,
)
from teachmemusic.performance.validation import is_stable_id
from teachmemusic.score import CanonicalMusicPackage, CanonicalScoreContent, ScoreDocument

from .contracts import (
    TEACHING_CONTRACT_ID,
    TEACHING_CONTRACT_VERSION,
    CanonicalAnchorKind,
    DataAuthorization,
    DemandDimension,
    EvidenceContext,
    EvidenceExport,
    EvidenceRecord,
    EvidenceState,
    Exercise,
    FeedbackAction,
    FeedbackTiming,
    LearnerContextSnapshot,
    LearnerTrack,
    LessonNode,
    LessonNodeKind,
    LessonPlan,
    PlanAudit,
    PlanAuditOutcome,
    PolicyAction,
    PolicyDecision,
    PracticeMode,
    RunEvent,
    RunEventKind,
    SkillDomain,
    SupportState,
    SyntheticExerciseMaterial,
    TeachingRunManifest,
)

_SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")


@dataclass(frozen=True, slots=True)
class TeachingValidationIssue:
    """One stable teaching-contract invariant failure."""

    code: str
    path: str
    message: str


class TeachingValidationError(ValueError):
    """Raised when a teaching contract cannot safely cross a boundary."""

    def __init__(self, issues: tuple[TeachingValidationIssue, ...]) -> None:
        if not issues:
            raise ValueError("at least one validation issue is required")
        self.issues = issues
        super().__init__(
            "; ".join(f"{issue.code} at {issue.path}: {issue.message}" for issue in issues)
        )


def validate_lesson_plan(
    plan: LessonPlan,
    package: CanonicalMusicPackage | None = None,
) -> tuple[TeachingValidationIssue, ...]:
    """Validate one untouched automatic lesson-plan contract."""

    issues: list[TeachingValidationIssue] = []
    _id(plan.id, "plan.id", issues)
    _id(plan.run_id, "plan.run_id", issues)
    _sha256(plan.input_digest_sha256, "plan.input_digest_sha256", issues)
    for name in ("generated_at_utc", "planner_version", "policy_version"):
        _nonempty(getattr(plan, name), f"plan.{name}", issues)
    for field_name in ("target_skills", "exercises", "nodes", "root_node_ids", "diagnostics"):
        _tuple(getattr(plan, field_name), f"plan.{field_name}", issues)
    _strings(plan.root_node_ids, "plan.root_node_ids", issues, ids=True)
    _strings(plan.diagnostics, "plan.diagnostics", issues)
    if not plan.exercises:
        _add(issues, "TEACH_PLAN_EXERCISES", "plan.exercises", "plan has no exercises")
    if not plan.nodes:
        _add(issues, "TEACH_PLAN_NODES", "plan.nodes", "plan has no graph nodes")
    if not plan.root_node_ids:
        _add(issues, "TEACH_PLAN_ROOTS", "plan.root_node_ids", "plan has no root nodes")
    if len(set(plan.target_skills)) != len(plan.target_skills):
        _add(issues, "TEACH_SKILL_DUPLICATE", "plan.target_skills", "target skill repeats")
    if not plan.target_skills:
        _add(issues, "TEACH_TARGET_SKILLS", "plan.target_skills", "plan has no target skills")
    if not isinstance(plan.track, LearnerTrack):
        _add(issues, "TEACH_LEARNER_TRACK", "plan.track", "unknown learner track")
    for index, skill in enumerate(plan.target_skills):
        if not isinstance(skill, SkillDomain):
            _add(
                issues,
                "TEACH_SKILL_DOMAIN",
                f"plan.target_skills[{index}]",
                "unknown skill domain",
            )

    exercise_ids = _unique_ids(plan.exercises, "plan.exercises", issues)
    node_ids = _unique_ids(plan.nodes, "plan.nodes", issues)
    all_nested_ids: set[str] = set()
    for index, exercise in enumerate(plan.exercises):
        _validate_exercise(exercise, f"plan.exercises[{index}]", issues)
        nested = _exercise_ids(exercise)
        duplicate = all_nested_ids & nested
        if duplicate:
            _add(
                issues,
                "TEACH_NESTED_ID_DUPLICATE",
                f"plan.exercises[{index}]",
                f"nested IDs repeat across exercises: {sorted(duplicate)!r}",
            )
        all_nested_ids.update(nested)
    if (exercise_ids | node_ids) & all_nested_ids or exercise_ids & node_ids:
        _add(issues, "TEACH_GLOBAL_ID_DUPLICATE", "plan", "plan IDs overlap across families")

    node_by_id = {node.id: node for node in plan.nodes}
    for index, node in enumerate(plan.nodes):
        path = f"plan.nodes[{index}]"
        _id(node.id, f"{path}.id", issues)
        _id(node.exercise_id, f"{path}.exercise_id", issues)
        if node.exercise_id not in exercise_ids:
            _add(issues, "TEACH_EXERCISE_REFERENCE", f"{path}.exercise_id", "exercise is missing")
        for field_name in ("prerequisites", "successors"):
            references = getattr(node, field_name)
            _tuple(references, f"{path}.{field_name}", issues)
            _strings(references, f"{path}.{field_name}", issues, ids=True)
            if len(set(references)) != len(references):
                _add(
                    issues,
                    "TEACH_NODE_REFERENCE_DUPLICATE",
                    f"{path}.{field_name}",
                    "node repeats",
                )
            for ref_index, reference in enumerate(references):
                if reference not in node_ids:
                    _add(
                        issues,
                        "TEACH_NODE_REFERENCE",
                        f"{path}.{field_name}[{ref_index}]",
                        "node does not exist",
                    )
                if reference == node.id:
                    _add(
                        issues,
                        "TEACH_NODE_SELF_REFERENCE",
                        f"{path}.{field_name}[{ref_index}]",
                        "node references itself",
                    )
        if not isinstance(node.kind, LessonNodeKind):
            _add(issues, "TEACH_NODE_KIND", f"{path}.kind", "unknown node kind")
    for node in plan.nodes:
        for successor in node.successors:
            if successor in node_by_id and node.id not in node_by_id[successor].prerequisites:
                _add(
                    issues,
                    "TEACH_GRAPH_RECIPROCITY",
                    f"plan.nodes[{node.id}].successors",
                    "successor does not name the node as a prerequisite",
                )
        for prerequisite in node.prerequisites:
            if prerequisite in node_by_id and node.id not in node_by_id[prerequisite].successors:
                _add(
                    issues,
                    "TEACH_GRAPH_RECIPROCITY",
                    f"plan.nodes[{node.id}].prerequisites",
                    "prerequisite does not name the node as a successor",
                )
    for index, root_id in enumerate(plan.root_node_ids):
        root = node_by_id.get(root_id)
        if root is None:
            _add(issues, "TEACH_ROOT_REFERENCE", f"plan.root_node_ids[{index}]", "root is missing")
        elif root.prerequisites:
            _add(
                issues,
                "TEACH_ROOT_PREREQUISITE",
                f"plan.root_node_ids[{index}]",
                "root node has prerequisites",
            )
    if node_ids:
        reachable = _reachable_nodes(plan.root_node_ids, node_by_id)
        unreachable = node_ids - reachable
        if unreachable:
            _add(
                issues,
                "TEACH_GRAPH_UNREACHABLE",
                "plan.nodes",
                f"nodes are unreachable from roots: {sorted(unreachable)!r}",
            )
    if package is not None:
        _validate_plan_against_package(plan, package, issues)
    return tuple(issues)


def require_valid_lesson_plan(
    plan: LessonPlan,
    package: CanonicalMusicPackage | None = None,
) -> None:
    """Raise if a lesson plan violates any invariant."""

    issues = validate_lesson_plan(plan, package)
    if issues:
        raise TeachingValidationError(issues)


def _validate_plan_against_package(
    plan: LessonPlan,
    package: CanonicalMusicPackage,
    issues: list[TeachingValidationIssue],
) -> None:
    known_by_kind: dict[CanonicalAnchorKind, set[str]] = {
        kind: set() for kind in CanonicalAnchorKind
    }
    known_by_kind[CanonicalAnchorKind.PACKAGE].add(package.id.value)
    known_ids: set[str] = {package.id.value}
    score_ids: set[str] = set()
    for document in package.documents:
        known_ids.add(document.id.value)
        if not isinstance(document, ScoreDocument) or not isinstance(
            document.content, CanonicalScoreContent
        ):
            continue
        score_ids.add(document.id.value)
        known_by_kind[CanonicalAnchorKind.SCORE].add(document.id.value)
        for part in document.content.score.parts:
            known_ids.add(part.id)
            known_by_kind[CanonicalAnchorKind.PART].add(part.id)
            known_ids.update(staff.id for staff in part.staves)
            known_ids.update(voice.id for voice in part.voices)
            known_by_kind[CanonicalAnchorKind.STAFF].update(staff.id for staff in part.staves)
            known_by_kind[CanonicalAnchorKind.VOICE].update(voice.id for voice in part.voices)
            for measure in part.measures:
                known_ids.add(measure.id)
                known_by_kind[CanonicalAnchorKind.MEASURE].add(measure.id)
                known_ids.update(event.id for event in measure.events)
                known_by_kind[CanonicalAnchorKind.EVENT].update(
                    event.id for event in measure.events
                )
                known_ids.update(
                    event.chord_id for event in measure.events if event.chord_id is not None
                )
                known_by_kind[CanonicalAnchorKind.CHORD].update(
                    event.chord_id for event in measure.events if event.chord_id is not None
                )
    for index, exercise in enumerate(plan.exercises):
        path = f"plan.exercises[{index}]"
        if exercise.anchor_set is not None:
            anchors = exercise.anchor_set
            if anchors.package_id != package.id.value:
                _add(
                    issues,
                    "TEACH_PACKAGE_REFERENCE",
                    f"{path}.anchor_set.package_id",
                    "canonical package differs",
                )
            if anchors.score_id not in score_ids:
                _add(
                    issues,
                    "TEACH_SCORE_REFERENCE",
                    f"{path}.anchor_set.score_id",
                    "canonical score is missing",
                )
            references = {anchor.canonical_id for anchor in anchors.anchors}
            for anchor_index, anchor in enumerate(anchors.anchors):
                if not isinstance(anchor.kind, CanonicalAnchorKind):
                    continue
                known_for_kind = known_by_kind[anchor.kind]
                if known_for_kind and anchor.canonical_id not in known_for_kind:
                    _add(
                        issues,
                        "TEACH_ANCHOR_KIND_REFERENCE",
                        f"{path}.anchor_set.anchors[{anchor_index}]",
                        "canonical identity does not match its declared anchor kind",
                    )
        elif exercise.synthetic_material is not None:
            references = set(exercise.synthetic_material.source_canonical_ids)
        else:
            references = set()
        foreign = references - known_ids
        if foreign:
            _add(
                issues,
                "TEACH_CANONICAL_REFERENCE",
                path,
                f"unknown canonical references: {sorted(foreign)!r}",
            )


def validate_evidence_export(value: EvidenceExport) -> tuple[TeachingValidationIssue, ...]:
    """Validate one complete local learner-evidence envelope."""

    issues: list[TeachingValidationIssue] = []
    if value.contract_id != TEACHING_CONTRACT_ID:
        _add(issues, "TEACH_CONTRACT_ID", "export.contract_id", "unsupported contract ID")
    if value.contract_version != TEACHING_CONTRACT_VERSION:
        _add(
            issues,
            "TEACH_CONTRACT_VERSION",
            "export.contract_version",
            "unsupported contract version",
        )
    _id(value.id, "export.id", issues)
    _nonempty(value.exported_at_utc, "export.exported_at_utc", issues)
    for field_name in (
        "plans",
        "audits",
        "evidence_records",
        "feedback_actions",
        "policy_decisions",
        "run_events",
        "omissions",
    ):
        _tuple(getattr(value, field_name), f"export.{field_name}", issues)
    _strings(value.omissions, "export.omissions", issues)
    if not value.plans:
        _add(issues, "TEACH_EXPORT_PLANS", "export.plans", "export has no lesson plan")
    _validate_learner_context(value.learner_context, "export.learner_context", issues)
    _validate_authorization(value.data_authorization, "export.data_authorization", issues)
    _validate_manifest(value.manifest, "export.manifest", issues)
    if value.manifest.learner_context_id != value.learner_context.id:
        _add(
            issues,
            "TEACH_LEARNER_REFERENCE",
            "export.manifest.learner_context_id",
            "learner context does not match",
        )
    if value.manifest.data_authorization_id != value.data_authorization.id:
        _add(
            issues,
            "TEACH_AUTHORIZATION_REFERENCE",
            "export.manifest.data_authorization_id",
            "data authorization does not match",
        )

    plan_ids = _unique_ids(value.plans, "export.plans", issues)
    audit_ids = _unique_ids(value.audits, "export.audits", issues)
    evidence_ids = _unique_ids(value.evidence_records, "export.evidence_records", issues)
    feedback_ids = _unique_ids(value.feedback_actions, "export.feedback_actions", issues)
    decision_ids = _unique_ids(value.policy_decisions, "export.policy_decisions", issues)
    event_ids = _unique_ids(value.run_events, "export.run_events", issues)
    family_ids = [
        {value.id, value.manifest.id, value.learner_context.id, value.data_authorization.id},
        plan_ids,
        audit_ids,
        evidence_ids,
        feedback_ids,
        decision_ids,
        event_ids,
    ]
    seen: set[str] = set()
    for identifiers in family_ids:
        if seen & identifiers:
            _add(issues, "TEACH_GLOBAL_ID_DUPLICATE", "export", "IDs overlap across families")
        seen.update(identifiers)

    plan_by_id = {plan.id: plan for plan in value.plans}
    exercise_by_id: dict[str, Exercise] = {}
    support_ids: set[str] = set()
    requirement_ids: set[str] = set()
    node_ids: set[str] = set()
    for index, plan in enumerate(value.plans):
        for issue in validate_lesson_plan(plan):
            _add(
                issues,
                issue.code,
                f"export.plans[{index}].{issue.path.removeprefix('plan.')}",
                issue.message,
            )
        if plan.run_id != value.manifest.id:
            _add(issues, "TEACH_RUN_REFERENCE", f"export.plans[{index}].run_id", "run differs")
        if plan.input_digest_sha256 != value.manifest.score_digest_sha256:
            _add(
                issues,
                "TEACH_SCORE_DIGEST_REFERENCE",
                f"export.plans[{index}].input_digest_sha256",
                "score digest differs from manifest",
            )
        for exercise in plan.exercises:
            if exercise.id in exercise_by_id:
                _add(issues, "TEACH_EXERCISE_DUPLICATE", "export.plans", "exercise ID repeats")
            exercise_by_id[exercise.id] = exercise
            support_ids.add(exercise.initial_support.id)
            requirement_ids.update(item.id for item in exercise.exit_evidence)
            if (
                exercise.anchor_set is not None
                and exercise.anchor_set.package_id != value.manifest.package_id
            ):
                _add(
                    issues,
                    "TEACH_PACKAGE_REFERENCE",
                    f"export.plans[{index}].exercises[{exercise.id}].anchor_set.package_id",
                    "canonical package differs from manifest",
                )
            if (
                exercise.anchor_set is not None
                and exercise.anchor_set.score_id != value.manifest.score_id
            ):
                _add(
                    issues,
                    "TEACH_SCORE_REFERENCE",
                    f"export.plans[{index}].exercises[{exercise.id}].anchor_set.score_id",
                    "canonical score differs from manifest",
                )
        node_ids.update(node.id for node in plan.nodes)

    for index, audit in enumerate(value.audits):
        _validate_audit(audit, f"export.audits[{index}]", plan_by_id, issues)

    performance_issues = validate_performance_bundle(value.performance)
    for performance_issue in performance_issues:
        _add(
            issues,
            performance_issue.code,
            f"export.performance.{performance_issue.path.removeprefix('bundle.')}",
            performance_issue.message,
        )
    if value.performance.contract_version != value.manifest.versions.performance_contract_version:
        _add(
            issues,
            "TEACH_PERFORMANCE_VERSION_REFERENCE",
            "export.performance.contract_version",
            "performance version differs from manifest",
        )
    calibration_ids = {item.id for item in value.performance.calibrations}
    attempt_by_id = {item.id: item for item in value.performance.attempts}
    observation_by_id = {item.id: item for item in value.performance.observations}
    observation_ids = set(observation_by_id)
    for index, attempt in enumerate(value.performance.attempts):
        path = f"export.performance.attempts[{index}]"
        if attempt.run_id != value.manifest.id:
            _add(issues, "TEACH_RUN_REFERENCE", f"{path}.run_id", "attempt run differs")
        if attempt.exercise_id not in exercise_by_id:
            _add(issues, "TEACH_EXERCISE_REFERENCE", f"{path}.exercise_id", "exercise is missing")
        if attempt.support_state_id not in support_ids:
            _add(
                issues,
                "TEACH_SUPPORT_REFERENCE",
                f"{path}.support_state_id",
                "support is missing",
            )
        if attempt.calibration_id not in calibration_ids:
            _add(
                issues,
                "TEACH_CALIBRATION_REFERENCE",
                f"{path}.calibration_id",
                "calibration is missing",
            )

    evidence_by_id = {item.id: item for item in value.evidence_records}
    for index, record in enumerate(value.evidence_records):
        path = f"export.evidence_records[{index}]"
        for name in ("id", "attempt_id", "exercise_id", "requirement_id", "support_state_id"):
            _id(getattr(record, name), f"{path}.{name}", issues)
        _tuple(record.observation_ids, f"{path}.observation_ids", issues)
        _strings(record.observation_ids, f"{path}.observation_ids", issues, ids=True)
        _tuple(record.limitations, f"{path}.limitations", issues)
        _strings(record.limitations, f"{path}.limitations", issues)
        if not isinstance(record.dimension, ObservationDimension):
            _add(
                issues,
                "TEACH_OBSERVATION_DIMENSION",
                f"{path}.dimension",
                "unknown observation dimension",
            )
        if not isinstance(record.state, EvidenceState):
            _add(
                issues,
                "TEACH_EVIDENCE_STATE",
                f"{path}.state",
                "unknown evidence state",
            )
        if not isinstance(record.context, EvidenceContext):
            _add(
                issues,
                "TEACH_EVIDENCE_CONTEXT",
                f"{path}.context",
                "unknown evidence context",
            )
        record_attempt = attempt_by_id.get(record.attempt_id)
        if record_attempt is None:
            _add(issues, "TEACH_ATTEMPT_REFERENCE", f"{path}.attempt_id", "attempt is missing")
        elif record_attempt.exercise_id != record.exercise_id:
            _add(issues, "TEACH_EXERCISE_REFERENCE", f"{path}.exercise_id", "exercise differs")
        elif record_attempt.support_state_id != record.support_state_id:
            _add(
                issues,
                "TEACH_SUPPORT_REFERENCE",
                f"{path}.support_state_id",
                "evidence support differs from attempt",
            )
        if record.exercise_id not in exercise_by_id:
            _add(issues, "TEACH_EXERCISE_REFERENCE", f"{path}.exercise_id", "exercise is missing")
        if record.requirement_id not in requirement_ids:
            _add(
                issues,
                "TEACH_REQUIREMENT_REFERENCE",
                f"{path}.requirement_id",
                "requirement is missing",
            )
        else:
            requirement = next(
                item
                for plan in value.plans
                for exercise in plan.exercises
                for item in exercise.exit_evidence
                if item.id == record.requirement_id
            )
            if record.dimension is not requirement.dimension:
                _add(
                    issues,
                    "TEACH_EVIDENCE_DIMENSION",
                    f"{path}.dimension",
                    "evidence dimension differs from requirement",
                )
        if record.support_state_id not in support_ids:
            _add(
                issues,
                "TEACH_SUPPORT_REFERENCE",
                f"{path}.support_state_id",
                "support is missing",
            )
        for ref_index, observation_id in enumerate(record.observation_ids):
            if observation_id not in observation_ids:
                _add(
                    issues,
                    "TEACH_OBSERVATION_REFERENCE",
                    f"{path}.observation_ids[{ref_index}]",
                    "observation is missing",
                )
            else:
                observation = observation_by_id[observation_id]
                if observation.attempt_id != record.attempt_id:
                    _add(
                        issues,
                        "TEACH_ATTEMPT_REFERENCE",
                        f"{path}.observation_ids[{ref_index}]",
                        "observation belongs to another attempt",
                    )
                if observation.dimension is not record.dimension:
                    _add(
                        issues,
                        "TEACH_EVIDENCE_DIMENSION",
                        f"{path}.observation_ids[{ref_index}]",
                        "observation dimension differs from evidence",
                    )
        if record.state is EvidenceState.HUMAN_REVIEWED and not record.human_review:
            _add(issues, "TEACH_HUMAN_REVIEW", f"{path}.human_review", "review is missing")

    feedback_by_id = {item.id: item for item in value.feedback_actions}
    for index, feedback in enumerate(value.feedback_actions):
        _validate_feedback(feedback, f"export.feedback_actions[{index}]", evidence_by_id, issues)
    for index, decision in enumerate(value.policy_decisions):
        _validate_decision(
            decision,
            f"export.policy_decisions[{index}]",
            value.manifest,
            exercise_by_id,
            evidence_by_id,
            feedback_by_id,
            node_ids,
            issues,
        )

    payload_ids = {
        value.manifest.id,
        value.learner_context.id,
        value.data_authorization.id,
        *plan_ids,
        *audit_ids,
        *calibration_ids,
        *attempt_by_id,
        *observation_ids,
        *evidence_ids,
        *feedback_ids,
        *decision_ids,
    }
    _validate_events(value.run_events, value.manifest.id, payload_ids, issues)
    return tuple(issues)


def require_valid_evidence_export(value: EvidenceExport) -> None:
    """Raise if an evidence envelope violates any invariant."""

    issues = validate_evidence_export(value)
    if issues:
        raise TeachingValidationError(issues)


def _validate_exercise(
    exercise: Exercise,
    path: str,
    issues: list[TeachingValidationIssue],
) -> None:
    _id(exercise.id, f"{path}.id", issues)
    _nonempty(exercise.boundary_reason, f"{path}.boundary_reason", issues)
    if not isinstance(exercise.primary_skill, SkillDomain):
        _add(issues, "TEACH_SKILL_DOMAIN", f"{path}.primary_skill", "unknown skill domain")
    anchor_set = exercise.anchor_set
    canonical_ids: set[str] = set()
    synthetic_ids: set[str] = set()
    if (anchor_set is None) == (exercise.synthetic_material is None):
        _add(
            issues,
            "TEACH_MATERIAL_EXCLUSIVE",
            path,
            "exercise must contain exactly one canonical or synthetic material source",
        )
    if anchor_set is not None:
        _id(anchor_set.id, f"{path}.anchor_set.id", issues)
        _id(anchor_set.package_id, f"{path}.anchor_set.package_id", issues)
        _id(anchor_set.score_id, f"{path}.anchor_set.score_id", issues)
        _tuple(anchor_set.anchors, f"{path}.anchor_set.anchors", issues)
        if not anchor_set.anchors:
            _add(
                issues,
                "TEACH_ANCHORS_EMPTY",
                f"{path}.anchor_set.anchors",
                "no canonical anchors",
            )
        for index, anchor in enumerate(anchor_set.anchors):
            anchor_path = f"{path}.anchor_set.anchors[{index}]"
            if not isinstance(anchor.kind, CanonicalAnchorKind):
                _add(issues, "TEACH_ANCHOR_KIND", f"{anchor_path}.kind", "unknown anchor kind")
            _id(anchor.canonical_id, f"{anchor_path}.canonical_id", issues)
            if anchor.canonical_id in canonical_ids:
                _add(issues, "TEACH_ANCHOR_DUPLICATE", anchor_path, "canonical anchor repeats")
            canonical_ids.add(anchor.canonical_id)
        if anchor_set.start_quarters < 0 or anchor_set.end_quarters <= anchor_set.start_quarters:
            _add(
                issues,
                "TEACH_ANCHOR_RANGE",
                f"{path}.anchor_set",
                "invalid half-open score range",
            )
    if exercise.synthetic_material is not None:
        synthetic_ids = _validate_synthetic_material(
            exercise.synthetic_material,
            f"{path}.synthetic_material",
            issues,
        )
        canonical_ids.update(exercise.synthetic_material.source_canonical_ids)

    for field_name in (
        "layer_scope",
        "secondary_skills",
        "task_demands",
        "expected_facts",
        "practice_modes",
        "exit_evidence",
        "integration_successors",
        "retention_successors",
        "transfer_successors",
        "review_routes",
    ):
        _tuple(getattr(exercise, field_name), f"{path}.{field_name}", issues)
    _strings(exercise.layer_scope, f"{path}.layer_scope", issues)
    for field_name in ("integration_successors", "retention_successors", "transfer_successors"):
        _strings(getattr(exercise, field_name), f"{path}.{field_name}", issues, ids=True)
    if not exercise.practice_modes:
        _add(issues, "TEACH_PRACTICE_MODE", f"{path}.practice_modes", "no practice mode")
    if not exercise.exit_evidence:
        _add(issues, "TEACH_EXIT_EVIDENCE", f"{path}.exit_evidence", "no exit evidence")
    if len(set(exercise.secondary_skills)) != len(exercise.secondary_skills):
        _add(issues, "TEACH_SKILL_DUPLICATE", f"{path}.secondary_skills", "skill repeats")
    if exercise.primary_skill in exercise.secondary_skills:
        _add(issues, "TEACH_SKILL_DUPLICATE", f"{path}.secondary_skills", "primary skill repeats")
    if len(set(exercise.practice_modes)) != len(exercise.practice_modes):
        _add(issues, "TEACH_MODE_DUPLICATE", f"{path}.practice_modes", "practice mode repeats")
    for index, skill in enumerate(exercise.secondary_skills):
        if not isinstance(skill, SkillDomain):
            _add(
                issues,
                "TEACH_SKILL_DOMAIN",
                f"{path}.secondary_skills[{index}]",
                "unknown skill domain",
            )
    for index, mode in enumerate(exercise.practice_modes):
        if not isinstance(mode, PracticeMode):
            _add(
                issues,
                "TEACH_PRACTICE_MODE",
                f"{path}.practice_modes[{index}]",
                "unknown practice mode",
            )
    for index, route in enumerate(exercise.review_routes):
        if not isinstance(route, PolicyAction):
            _add(
                issues,
                "TEACH_POLICY_ACTION",
                f"{path}.review_routes[{index}]",
                "unknown review route",
            )
    required_routes = {
        PolicyAction.INCONCLUSIVE,
        PolicyAction.HUMAN_REVIEW,
        PolicyAction.SAFE_STOP,
    }
    if not required_routes.issubset(set(exercise.review_routes)):
        _add(issues, "TEACH_REVIEW_ROUTES", f"{path}.review_routes", "safe routes are missing")

    _validate_support(exercise.initial_support, f"{path}.initial_support", issues)
    demand_ids = _unique_ids(exercise.task_demands, f"{path}.task_demands", issues)
    fact_ids = _unique_ids(exercise.expected_facts, f"{path}.expected_facts", issues)
    requirement_ids = _unique_ids(exercise.exit_evidence, f"{path}.exit_evidence", issues)
    if demand_ids & fact_ids or demand_ids & requirement_ids or fact_ids & requirement_ids:
        _add(issues, "TEACH_NESTED_ID_DUPLICATE", path, "nested exercise IDs overlap")
    for index, demand in enumerate(exercise.task_demands):
        demand_path = f"{path}.task_demands[{index}]"
        if not isinstance(demand.dimension, DemandDimension):
            _add(
                issues,
                "TEACH_DEMAND_DIMENSION",
                f"{demand_path}.dimension",
                "unknown demand dimension",
            )
        if not 0 <= demand.level <= 5:
            _add(issues, "TEACH_DEMAND_LEVEL", f"{demand_path}.level", "level is outside 0..5")
        _nonempty(demand.rationale, f"{demand_path}.rationale", issues)
        if demand.uncertainty is not None:
            _nonempty(demand.uncertainty, f"{demand_path}.uncertainty", issues)
        _tuple(demand.evidence_canonical_ids, f"{demand_path}.evidence_canonical_ids", issues)
        _strings(
            demand.evidence_canonical_ids,
            f"{demand_path}.evidence_canonical_ids",
            issues,
            ids=True,
        )
        for ref_index, identifier in enumerate(demand.evidence_canonical_ids):
            if identifier not in canonical_ids:
                _add(
                    issues,
                    "TEACH_ANCHOR_REFERENCE",
                    f"{demand_path}.evidence_canonical_ids[{ref_index}]",
                    "canonical evidence is outside the anchor set",
                )
    fact_dimensions: set[ObservationDimension] = set()
    for index, fact in enumerate(exercise.expected_facts):
        fact_path = f"{path}.expected_facts[{index}]"
        if not isinstance(fact.dimension, ObservationDimension):
            _add(
                issues,
                "TEACH_OBSERVATION_DIMENSION",
                f"{fact_path}.dimension",
                "unknown observation dimension",
            )
        _nonempty(fact.expected_value, f"{fact_path}.expected_value", issues)
        _tuple(fact.canonical_ids, f"{fact_path}.canonical_ids", issues)
        _strings(fact.canonical_ids, f"{fact_path}.canonical_ids", issues, ids=True)
        _tuple(fact.synthetic_event_ids, f"{fact_path}.synthetic_event_ids", issues)
        _strings(
            fact.synthetic_event_ids,
            f"{fact_path}.synthetic_event_ids",
            issues,
            ids=True,
        )
        if bool(fact.canonical_ids) == bool(fact.synthetic_event_ids):
            _add(
                issues,
                "TEACH_EXPECTED_MATERIAL_REFERENCE",
                fact_path,
                "expected fact must reference exactly one material family",
            )
        _tuple(fact.observable_sources, f"{fact_path}.observable_sources", issues)
        if not fact.observable_sources:
            _add(issues, "TEACH_OBSERVATION_SOURCE", fact_path, "fact has no observation source")
        if len(set(fact.observable_sources)) != len(fact.observable_sources):
            _add(issues, "TEACH_SOURCE_DUPLICATE", fact_path, "observation source repeats")
        for source in fact.observable_sources:
            if not isinstance(source, ObservationSource):
                _add(issues, "TEACH_OBSERVATION_SOURCE", fact_path, "unknown observation source")
        for ref_index, identifier in enumerate(fact.canonical_ids):
            if identifier not in canonical_ids:
                _add(
                    issues,
                    "TEACH_ANCHOR_REFERENCE",
                    f"{fact_path}.canonical_ids[{ref_index}]",
                    "expected fact is outside the anchor set",
                )
        for ref_index, identifier in enumerate(fact.synthetic_event_ids):
            if identifier not in synthetic_ids:
                _add(
                    issues,
                    "TEACH_SYNTHETIC_REFERENCE",
                    f"{fact_path}.synthetic_event_ids[{ref_index}]",
                    "expected fact is outside the synthetic material",
                )
        fact_dimensions.add(fact.dimension)
    for index, requirement in enumerate(exercise.exit_evidence):
        requirement_path = f"{path}.exit_evidence[{index}]"
        if not isinstance(requirement.dimension, ObservationDimension):
            _add(
                issues,
                "TEACH_OBSERVATION_DIMENSION",
                f"{requirement_path}.dimension",
                "unknown observation dimension",
            )
        if not isinstance(requirement.minimum_state, EvidenceState):
            _add(
                issues,
                "TEACH_EVIDENCE_STATE",
                f"{requirement_path}.minimum_state",
                "unknown evidence state",
            )
        if not isinstance(requirement.context, EvidenceContext):
            _add(
                issues,
                "TEACH_EVIDENCE_CONTEXT",
                f"{requirement_path}.context",
                "unknown evidence context",
            )
        if requirement.dimension not in fact_dimensions:
            _add(
                issues,
                "TEACH_EXIT_DIMENSION",
                f"{requirement_path}.dimension",
                "exit dimension has no expected fact",
            )


def _validate_support(
    support: SupportState,
    path: str,
    issues: list[TeachingValidationIssue],
) -> None:
    _id(support.id, f"{path}.id", issues)
    for field_name in (
        "notation_visible",
        "cursor_visible",
        "note_names_visible",
        "keyboard_highlighting",
        "fingering_visible",
        "demonstration_available",
        "follow_mode",
        "metronome",
        "prompts_visible",
    ):
        _boolean(getattr(support, field_name), f"{path}.{field_name}", issues)
    if not 1 <= support.tempo_percent <= 400:
        _add(issues, "TEACH_TEMPO_PERCENT", f"{path}.tempo_percent", "tempo is outside 1..400")
    if support.max_replays is not None and support.max_replays < 0:
        _add(issues, "TEACH_MAX_REPLAYS", f"{path}.max_replays", "value is negative")
    if support.tempo_bpm is not None and support.tempo_bpm <= 0:
        _add(issues, "TEACH_TEMPO_BPM", f"{path}.tempo_bpm", "tempo is not positive")
    for field_name in ("isolated_layers", "isolated_dimensions", "accessibility_accommodations"):
        values = getattr(support, field_name)
        _tuple(values, f"{path}.{field_name}", issues)
        _strings(values, f"{path}.{field_name}", issues)
        if len(set(values)) != len(values):
            _add(issues, "TEACH_SUPPORT_DUPLICATE", f"{path}.{field_name}", "value repeats")


def _validate_synthetic_material(
    material: SyntheticExerciseMaterial,
    path: str,
    issues: list[TeachingValidationIssue],
) -> set[str]:
    _id(material.id, f"{path}.id", issues)
    _nonempty(material.rationale, f"{path}.rationale", issues)
    _tuple(material.source_canonical_ids, f"{path}.source_canonical_ids", issues)
    _strings(
        material.source_canonical_ids,
        f"{path}.source_canonical_ids",
        issues,
        ids=True,
    )
    _tuple(material.events, f"{path}.events", issues)
    if not material.source_canonical_ids:
        _add(
            issues,
            "TEACH_SYNTHETIC_PROVENANCE",
            f"{path}.source_canonical_ids",
            "synthetic material has no canonical provenance",
        )
    if not material.events:
        _add(issues, "TEACH_SYNTHETIC_EVENTS", f"{path}.events", "synthetic material is empty")
    event_ids: set[str] = set()
    previous_onset = None
    source_ids = set(material.source_canonical_ids)
    for index, event in enumerate(material.events):
        event_path = f"{path}.events[{index}]"
        _id(event.id, f"{event_path}.id", issues)
        if event.id in event_ids:
            _add(issues, "TEACH_SYNTHETIC_DUPLICATE", f"{event_path}.id", "event ID repeats")
        event_ids.add(event.id)
        if event.onset_quarters < 0:
            _add(issues, "TEACH_SYNTHETIC_ONSET", event_path, "onset is negative")
        if previous_onset is not None and event.onset_quarters < previous_onset:
            _add(issues, "TEACH_SYNTHETIC_ORDER", event_path, "events are not onset ordered")
        previous_onset = event.onset_quarters
        if event.duration_quarters <= 0:
            _add(issues, "TEACH_SYNTHETIC_DURATION", event_path, "duration is not positive")
        if not 0 <= event.midi_note <= 127:
            _add(issues, "TEACH_SYNTHETIC_MIDI", event_path, "MIDI note is outside 0..127")
        _tuple(event.source_canonical_ids, f"{event_path}.source_canonical_ids", issues)
        _strings(
            event.source_canonical_ids,
            f"{event_path}.source_canonical_ids",
            issues,
            ids=True,
        )
        if not event.source_canonical_ids:
            _add(
                issues,
                "TEACH_SYNTHETIC_PROVENANCE",
                f"{event_path}.source_canonical_ids",
                "event has no canonical pitch provenance",
            )
        for reference in event.source_canonical_ids:
            if reference not in source_ids:
                _add(
                    issues,
                    "TEACH_SYNTHETIC_PROVENANCE",
                    f"{event_path}.source_canonical_ids",
                    "event provenance is outside material provenance",
                )
    return event_ids


def _validate_learner_context(
    value: LearnerContextSnapshot,
    path: str,
    issues: list[TeachingValidationIssue],
) -> None:
    _id(value.id, f"{path}.id", issues)
    if not isinstance(value.track, LearnerTrack):
        _add(issues, "TEACH_LEARNER_TRACK", f"{path}.track", "unknown learner track")
    for field_name in ("goals", "prior_experience", "accessibility_choices", "outside_practice"):
        items = getattr(value, field_name)
        _tuple(items, f"{path}.{field_name}", issues)
        _strings(items, f"{path}.{field_name}", issues)


def _validate_authorization(
    value: DataAuthorization,
    path: str,
    issues: list[TeachingValidationIssue],
) -> None:
    _id(value.id, f"{path}.id", issues)
    _tuple(value.excluded_sources, f"{path}.excluded_sources", issues)
    _strings(value.excluded_sources, f"{path}.excluded_sources", issues)
    for field_name in (
        "approved",
        "capture_midi",
        "capture_self_report",
        "capture_environment",
        "allow_export",
    ):
        _boolean(getattr(value, field_name), f"{path}.{field_name}", issues)
    if value.approved and not value.approved_at_utc:
        _add(issues, "TEACH_APPROVAL_TIME", f"{path}.approved_at_utc", "approval time is missing")
    if not value.approved and value.approved_at_utc is not None:
        _add(issues, "TEACH_APPROVAL_STATE", f"{path}.approved_at_utc", "unapproved data has time")
    if value.capture_midi and "midi" in value.excluded_sources:
        _add(
            issues,
            "TEACH_DATA_CONFLICT",
            f"{path}.excluded_sources",
            "MIDI is both included and excluded",
        )


def _validate_manifest(
    value: TeachingRunManifest,
    path: str,
    issues: list[TeachingValidationIssue],
) -> None:
    for name in ("id", "package_id", "score_id", "learner_context_id", "data_authorization_id"):
        _id(getattr(value, name), f"{path}.{name}", issues)
    _nonempty(value.created_at_utc, f"{path}.created_at_utc", issues)
    _nonempty(value.scope_label, f"{path}.scope_label", issues)
    _sha256(value.score_digest_sha256, f"{path}.score_digest_sha256", issues)
    versions = value.versions
    for name in (
        "application_version",
        "canonical_schema_id",
        "canonical_schema_version",
        "parser_version",
        "analysis_version",
        "planner_version",
        "policy_version",
        "feedback_version",
        "calibration_version",
        "teaching_contract_version",
        "performance_contract_version",
    ):
        _nonempty(getattr(versions, name), f"{path}.versions.{name}", issues)
    if versions.teaching_contract_version != TEACHING_CONTRACT_VERSION:
        _add(
            issues,
            "TEACH_VERSION_REFERENCE",
            f"{path}.versions.teaching_contract_version",
            "version differs from envelope",
        )
    if versions.performance_contract_version != PERFORMANCE_CONTRACT_VERSION:
        _add(
            issues,
            "TEACH_PERFORMANCE_VERSION_REFERENCE",
            f"{path}.versions.performance_contract_version",
            "unsupported performance contract version",
        )


def _validate_audit(
    audit: PlanAudit,
    path: str,
    plans: dict[str, LessonPlan],
    issues: list[TeachingValidationIssue],
) -> None:
    for name in ("id", "plan_id"):
        _id(getattr(audit, name), f"{path}.{name}", issues)
    for name in ("reviewer", "reviewed_at_utc"):
        _nonempty(getattr(audit, name), f"{path}.{name}", issues)
    _tuple(audit.interventions, f"{path}.interventions", issues)
    _tuple(audit.notes, f"{path}.notes", issues)
    _strings(audit.notes, f"{path}.notes", issues)
    if not isinstance(audit.outcome, PlanAuditOutcome):
        _add(issues, "TEACH_AUDIT_OUTCOME", f"{path}.outcome", "unknown audit outcome")
    for field_name in ("source_faithful", "musically_coherent", "safe", "executable"):
        _boolean(getattr(audit, field_name), f"{path}.{field_name}", issues)
    if audit.plan_id not in plans:
        _add(issues, "TEACH_PLAN_REFERENCE", f"{path}.plan_id", "plan is missing")
    intervention_ids = _unique_ids(audit.interventions, f"{path}.interventions", issues)
    if len(intervention_ids) != len(audit.interventions):
        return
    for index, intervention in enumerate(audit.interventions):
        item_path = f"{path}.interventions[{index}]"
        if intervention.plan_id != audit.plan_id:
            _add(issues, "TEACH_PLAN_REFERENCE", f"{item_path}.plan_id", "plan differs")
        for name in ("path", "before_json", "after_json", "reason"):
            _nonempty(getattr(intervention, name), f"{item_path}.{name}", issues)
        _boolean(intervention.pedagogical, f"{item_path}.pedagogical", issues)
    has_pedagogical = any(item.pedagogical for item in audit.interventions)
    if has_pedagogical and audit.outcome is not PlanAuditOutcome.QUALIFIED_HUMAN_INTERVENTION:
        _add(issues, "TEACH_AUDIT_QUALIFICATION", path, "pedagogical change is not qualified")
    if audit.outcome is PlanAuditOutcome.PASS_NO_CHANGE and audit.interventions:
        _add(issues, "TEACH_AUDIT_INTERVENTION", path, "no-change audit contains intervention")


def _validate_feedback(
    feedback: FeedbackAction,
    path: str,
    records: Mapping[str, EvidenceRecord],
    issues: list[TeachingValidationIssue],
) -> None:
    _id(feedback.id, f"{path}.id", issues)
    if not isinstance(feedback.timing, FeedbackTiming):
        _add(issues, "TEACH_FEEDBACK_TIMING", f"{path}.timing", "unknown feedback timing")
    _tuple(feedback.evidence_record_ids, f"{path}.evidence_record_ids", issues)
    _strings(feedback.evidence_record_ids, f"{path}.evidence_record_ids", issues, ids=True)
    if not feedback.evidence_record_ids:
        _add(issues, "TEACH_FEEDBACK_EVIDENCE", f"{path}.evidence_record_ids", "evidence is empty")
    for index, identifier in enumerate(feedback.evidence_record_ids):
        if identifier not in records:
            _add(
                issues,
                "TEACH_EVIDENCE_REFERENCE",
                f"{path}.evidence_record_ids[{index}]",
                "evidence is missing",
            )
    for name in ("target", "observation", "action", "reason"):
        _nonempty(getattr(feedback, name), f"{path}.{name}", issues)


def _validate_decision(
    decision: PolicyDecision,
    path: str,
    manifest: TeachingRunManifest,
    exercises: dict[str, Exercise],
    records: Mapping[str, EvidenceRecord],
    feedback: dict[str, FeedbackAction],
    node_ids: set[str],
    issues: list[TeachingValidationIssue],
) -> None:
    for name in ("id", "run_id", "exercise_id"):
        _id(getattr(decision, name), f"{path}.{name}", issues)
    if decision.run_id != manifest.id:
        _add(issues, "TEACH_RUN_REFERENCE", f"{path}.run_id", "run differs")
    if decision.exercise_id not in exercises:
        _add(issues, "TEACH_EXERCISE_REFERENCE", f"{path}.exercise_id", "exercise is missing")
    _tuple(decision.evidence_record_ids, f"{path}.evidence_record_ids", issues)
    _strings(decision.evidence_record_ids, f"{path}.evidence_record_ids", issues, ids=True)
    for index, identifier in enumerate(decision.evidence_record_ids):
        if identifier not in records:
            _add(
                issues,
                "TEACH_EVIDENCE_REFERENCE",
                f"{path}.evidence_record_ids[{index}]",
                "evidence is missing",
            )
    if decision.feedback_id is not None:
        _id(decision.feedback_id, f"{path}.feedback_id", issues)
        if decision.feedback_id not in feedback:
            _add(issues, "TEACH_FEEDBACK_REFERENCE", f"{path}.feedback_id", "feedback is missing")
    if decision.next_node_id is not None:
        _id(decision.next_node_id, f"{path}.next_node_id", issues)
        if decision.next_node_id not in node_ids:
            _add(issues, "TEACH_NODE_REFERENCE", f"{path}.next_node_id", "node is missing")
    for name in ("reason", "policy_version", "created_at_utc"):
        _nonempty(getattr(decision, name), f"{path}.{name}", issues)
    if not isinstance(decision.action, PolicyAction):
        _add(issues, "TEACH_POLICY_ACTION", f"{path}.action", "unknown action")


def _validate_events(
    events: tuple[RunEvent, ...],
    run_id: str,
    payload_ids: set[str],
    issues: list[TeachingValidationIssue],
) -> None:
    event_ids = {event.id for event in events}
    previous_sequence = -1
    seen: set[str] = set()
    for index, event in enumerate(events):
        path = f"export.run_events[{index}]"
        _id(event.id, f"{path}.id", issues)
        _id(event.run_id, f"{path}.run_id", issues)
        _id(event.payload_id, f"{path}.payload_id", issues)
        _nonempty(event.occurred_at_utc, f"{path}.occurred_at_utc", issues)
        if event.run_id != run_id:
            _add(issues, "TEACH_RUN_REFERENCE", f"{path}.run_id", "event run differs")
        if event.sequence_number <= previous_sequence:
            _add(
                issues,
                "TEACH_EVENT_ORDER",
                f"{path}.sequence_number",
                "sequence is not increasing",
            )
        previous_sequence = event.sequence_number
        if event.payload_id not in payload_ids:
            _add(issues, "TEACH_EVENT_PAYLOAD", f"{path}.payload_id", "payload is missing")
        if not isinstance(event.kind, RunEventKind):
            _add(issues, "TEACH_EVENT_KIND", f"{path}.kind", "unknown event kind")
        if event.supersedes_event_id is not None:
            _id(event.supersedes_event_id, f"{path}.supersedes_event_id", issues)
            if event.supersedes_event_id not in event_ids:
                _add(
                    issues,
                    "TEACH_EVENT_SUPERSEDES",
                    f"{path}.supersedes_event_id",
                    "event is missing",
                )
            elif event.supersedes_event_id not in seen:
                _add(
                    issues,
                    "TEACH_EVENT_SUPERSEDES_ORDER",
                    f"{path}.supersedes_event_id",
                    "event is not earlier",
                )
        seen.add(event.id)


def _exercise_ids(exercise: Exercise) -> set[str]:
    result = {
        exercise.initial_support.id,
        *(item.id for item in exercise.task_demands),
        *(item.id for item in exercise.expected_facts),
        *(item.id for item in exercise.exit_evidence),
    }
    if exercise.anchor_set is not None:
        result.add(exercise.anchor_set.id)
    if exercise.synthetic_material is not None:
        result.add(exercise.synthetic_material.id)
        result.update(event.id for event in exercise.synthetic_material.events)
    return result


def _reachable_nodes(
    roots: tuple[str, ...],
    nodes: Mapping[str, LessonNode],
) -> set[str]:
    reached: set[str] = set()
    pending = list(roots)
    while pending:
        identifier = pending.pop()
        if identifier in reached:
            continue
        reached.add(identifier)
        node = nodes.get(identifier)
        if node is not None:
            pending.extend(node.successors)
    return reached


def _unique_ids(
    values: tuple[object, ...],
    path: str,
    issues: list[TeachingValidationIssue],
) -> set[str]:
    result: set[str] = set()
    for index, value in enumerate(values):
        identifier = getattr(value, "id", None)
        _id(identifier, f"{path}[{index}].id", issues)
        if isinstance(identifier, str):
            if identifier in result:
                _add(issues, "TEACH_ID_DUPLICATE", f"{path}[{index}].id", "ID is duplicated")
            result.add(identifier)
    return result


def _id(value: object, path: str, issues: list[TeachingValidationIssue]) -> None:
    if not is_stable_id(value):
        _add(issues, "TEACH_STABLE_ID", path, "expected namespaced stable ID")


def _sha256(value: object, path: str, issues: list[TeachingValidationIssue]) -> None:
    if not isinstance(value, str) or _SHA256_PATTERN.fullmatch(value) is None:
        _add(issues, "TEACH_SHA256", path, "expected lowercase SHA-256 digest")


def _nonempty(value: object, path: str, issues: list[TeachingValidationIssue]) -> None:
    if not isinstance(value, str) or not value.strip():
        _add(issues, "TEACH_REQUIRED_TEXT", path, "value is empty")


def _boolean(value: object, path: str, issues: list[TeachingValidationIssue]) -> None:
    if not isinstance(value, bool):
        _add(issues, "TEACH_BOOLEAN", path, "expected boolean")


def _tuple(value: object, path: str, issues: list[TeachingValidationIssue]) -> None:
    if not isinstance(value, tuple):
        _add(issues, "TEACH_IMMUTABLE_COLLECTION", path, "expected tuple")


def _strings(
    values: object,
    path: str,
    issues: list[TeachingValidationIssue],
    *,
    ids: bool = False,
) -> None:
    if not isinstance(values, tuple):
        return
    for index, value in enumerate(values):
        if ids:
            _id(value, f"{path}[{index}]", issues)
        else:
            _nonempty(value, f"{path}[{index}]", issues)


def _add(
    issues: list[TeachingValidationIssue],
    code: str,
    path: str,
    message: str,
) -> None:
    issues.append(TeachingValidationIssue(code, path, message))
