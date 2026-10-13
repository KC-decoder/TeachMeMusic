"""Executable DEV-009 Task 9I.1 pre-decision snapshot evidence."""

from __future__ import annotations

import json
from dataclasses import replace
from fractions import Fraction

import pytest

from teachmemusic.analysis import analyze_canonical_score
from teachmemusic.performance import align_layer_attempt
from teachmemusic.score import CanonicalMusicPackage
from teachmemusic.teaching import (
    CompatibleTempoEvidence,
    CurriculumActionEligibility,
    CurriculumBudgetCounter,
    CurriculumPolicyAction,
    CurriculumSerializationError,
    CurriculumTrajectoryError,
    EvidenceContext,
    NotationCondition,
    PracticeMode,
    SemanticReference,
    TempoReferenceAuthority,
    build_curriculum_action_inventory,
    build_curriculum_combined_expected_performance,
    build_curriculum_decision_snapshot,
    build_curriculum_evidence_records,
    build_curriculum_exercise_learning_outcome,
    build_curriculum_experiment_manifest,
    build_curriculum_passage_presentation,
    build_curriculum_research_reward,
    build_curriculum_transition_result,
    curriculum_action_inventory_from_json,
    curriculum_action_inventory_to_json,
    curriculum_action_selection_from_json,
    curriculum_action_selection_to_json,
    curriculum_decision_snapshot_from_json,
    curriculum_decision_snapshot_to_json,
    curriculum_experiment_manifest_from_json,
    curriculum_experiment_manifest_to_json,
    curriculum_transition_result_from_json,
    curriculum_transition_result_to_json,
    decide_curriculum_unlock,
    derive_passage_requirements,
    generate_acquisition_graph,
    generate_prerequisite_branches,
    select_curriculum_action,
    validate_curriculum_action_inventory,
    validate_curriculum_action_selection,
    validate_curriculum_decision_snapshot,
    validate_curriculum_experiment_manifest,
    validate_curriculum_transition_result,
)
from tests.teaching.test_curriculum_cross_score_routes import (
    _calibration,
    _exact_attempt,
    _happy_birthday_support,
)
from tests.teaching.test_curriculum_fundamental_returns import (
    _return_fixture,
    _support,
)


def _snapshot(package: CanonicalMusicPackage):
    fixture = _return_fixture(package)
    snapshot = build_curriculum_decision_snapshot(
        fixture[2],
        fixture[4].prerequisite_node_id,
        _support(),
        fixture[7],
        fixture[9],
        fixture[10],
        run_id="run:trajectory-hcb-001",
        learner_context_id="learner-context:owner-beginner-001",
        decision_sequence=1,
        evidence_snapshot_sequence=2,
        budget_state=(CurriculumBudgetCounter("budget:prerequisite-attempts", 2, 4),),
    )
    return fixture, snapshot


def _happy_birthday_action_state(
    package: CanonicalMusicPackage,
    *,
    with_evidence: bool = True,
):
    analysis = analyze_canonical_score(package)
    requirements = derive_passage_requirements(package, analysis)
    scopes = {item.notation_condition: item for item in requirements.scopes}
    percentages = {
        NotationCondition.UPPER_LAYER: 85,
        NotationCondition.LOWER_LAYER: 70,
        NotationCondition.COMBINED: 70,
    }
    tempo_evidence = tuple(
        CompatibleTempoEvidence(
            SemanticReference(
                "practice-scope-assignment",
                scope.id,
                scope.semantic_fingerprint,
            ),
            "independent-piece",
            percentages[condition],
            percentages[condition],
            True,
            True,
            (f"evidence:hb-{condition.value}",),
        )
        for condition, scope in scopes.items()
    )
    graph = generate_acquisition_graph(
        requirements,
        generate_prerequisite_branches(requirements),
        reference_tempo_bpm=Fraction(120),
        reference_authority=TempoReferenceAuthority.SOURCE,
        tempo_evidence=tempo_evidence,
    )
    stage = graph.stages[4]
    node = next(item for item in graph.nodes if item.id == stage.node_id)
    plan = next(item for item in graph.tempo_plans if item.id == stage.tempo_plan_ref.id)
    assert plan.current_controlled_percentage is not None
    tempo_bpm = Fraction(120 * plan.current_controlled_percentage, 100)
    presentations = {
        condition: build_curriculum_passage_presentation(package, requirements, scope.id)
        for condition, scope in scopes.items()
    }
    expected = build_curriculum_combined_expected_performance(
        package,
        requirements,
        presentations[NotationCondition.COMBINED],
        (
            presentations[NotationCondition.UPPER_LAYER],
            presentations[NotationCondition.LOWER_LAYER],
        ),
        PracticeMode.INDEPENDENT_PERFORMANCE,
        tempo_bpm=tempo_bpm,
    )
    support = _happy_birthday_support(
        NotationCondition.COMBINED,
        PracticeMode.INDEPENDENT_PERFORMANCE,
        tempo_percent=plan.current_controlled_percentage,
        tempo_bpm=tempo_bpm,
    )
    observations = ()
    records = ()
    if with_evidence:
        attempt = _exact_attempt(
            expected,
            attempt_id="attempt:hb-action-selection",
            support_state_id=support.id,
        )
        observations = align_layer_attempt(expected, attempt, _calibration())
        records = tuple(
            item
            for item in build_curriculum_evidence_records(
                requirements,
                expected,
                attempt,
                support,
                observations,
                EvidenceContext.INDEPENDENT,
            )
            if item.requirement_ref.id == node.requirement_ref.id
        )
    previously_satisfied = tuple(
        dict.fromkeys(
            (
                *(
                    dependency
                    for prior_stage in graph.stages
                    for dependency in next(
                        item for item in graph.nodes if item.id == prior_stage.node_id
                    ).component_node_ids
                ),
                *(item.node_id for item in graph.stages[:4]),
            )
        )
    )
    mastery, _ = decide_curriculum_unlock(
        graph,
        node.id,
        support,
        records,
        previously_satisfied_node_ids=previously_satisfied,
    )
    snapshot = build_curriculum_decision_snapshot(
        graph,
        node.id,
        support,
        mastery,
        records,
        observations,
        run_id="run:trajectory-happy-birthday-001",
        learner_context_id="learner-context:owner-beginner-001",
        decision_sequence=5,
        evidence_snapshot_sequence=5 if with_evidence else 0,
        previously_satisfied_node_ids=previously_satisfied,
    )
    inventory = build_curriculum_action_inventory(graph, mastery, snapshot)
    return graph, mastery, snapshot, inventory


def _happy_birthday_transition(package: CanonicalMusicPackage):
    graph, mastery, prior_snapshot, inventory = _happy_birthday_action_state(package)
    selection = select_curriculum_action(inventory, prior_snapshot, graph, mastery)
    target_node = next(
        item for item in graph.nodes if item.id == selection.selected_candidate.target_node_id
    )
    exercise = next(item for item in graph.exercises if item.id == target_node.exercise_ref.id)
    target_stage = next(item for item in graph.stages if item.node_id == target_node.id)
    tempo_plan = next(
        item for item in graph.tempo_plans if item.id == target_stage.tempo_plan_ref.id
    )
    assert tempo_plan.current_controlled_percentage is not None
    tempo_bpm = Fraction(120 * tempo_plan.current_controlled_percentage, 100)

    analysis = analyze_canonical_score(package)
    requirements = derive_passage_requirements(package, analysis)
    scopes = {item.notation_condition: item for item in requirements.scopes}
    presentations = {
        condition: build_curriculum_passage_presentation(package, requirements, scope.id)
        for condition, scope in scopes.items()
    }
    expected = build_curriculum_combined_expected_performance(
        package,
        requirements,
        presentations[NotationCondition.COMBINED],
        (
            presentations[NotationCondition.UPPER_LAYER],
            presentations[NotationCondition.LOWER_LAYER],
        ),
        PracticeMode.INDEPENDENT_PERFORMANCE,
        tempo_bpm=tempo_bpm,
    )
    support = _happy_birthday_support(
        NotationCondition.COMBINED,
        PracticeMode.INDEPENDENT_PERFORMANCE,
        tempo_percent=tempo_plan.current_controlled_percentage,
        tempo_bpm=tempo_bpm,
    )
    attempt = replace(
        _exact_attempt(
            expected,
            attempt_id="attempt:hb-transition-outcome",
            support_state_id=support.id,
        ),
        run_id=prior_snapshot.run_id,
    )
    calibration = _calibration()
    observations = align_layer_attempt(expected, attempt, calibration)
    records = tuple(
        item
        for item in build_curriculum_evidence_records(
            requirements,
            expected,
            attempt,
            support,
            observations,
            EvidenceContext.INDEPENDENT,
        )
        if item.requirement_ref.id == target_node.requirement_ref.id
    )
    previously_satisfied = (
        *prior_snapshot.previously_satisfied_node_ids,
        prior_snapshot.current_node_id,
    )
    next_mastery, _ = decide_curriculum_unlock(
        graph,
        target_node.id,
        support,
        records,
        previously_satisfied_node_ids=previously_satisfied,
    )
    next_snapshot = build_curriculum_decision_snapshot(
        graph,
        target_node.id,
        support,
        next_mastery,
        records,
        observations,
        run_id=prior_snapshot.run_id,
        learner_context_id=prior_snapshot.learner_context_id,
        decision_sequence=prior_snapshot.decision_sequence + 1,
        evidence_snapshot_sequence=prior_snapshot.evidence_snapshot_sequence + 1,
        previously_satisfied_node_ids=previously_satisfied,
    )
    outcome = build_curriculum_exercise_learning_outcome(
        exercise,
        expected,
        attempt,
        calibration,
        support,
        observations,
    )
    reward = build_curriculum_research_reward(outcome, expected, observations)
    transition = build_curriculum_transition_result(
        selection,
        prior_snapshot,
        outcome,
        reward,
        next_snapshot,
    )
    return (
        inventory,
        selection,
        prior_snapshot,
        outcome,
        reward,
        next_snapshot,
        transition,
        expected,
        attempt,
        calibration,
        observations,
        graph,
        requirements,
        support,
        records,
        next_mastery,
        mastery,
    )


def test_decision_snapshot_is_versioned_strict_and_deterministic(
    hot_cross_buns_package: CanonicalMusicPackage,
) -> None:
    """TEST-CURR-CONTRACT-017: exact pre-decision knowledge round-trips."""

    fixture, snapshot = _snapshot(hot_cross_buns_package)
    payload = curriculum_decision_snapshot_to_json(snapshot)
    node = next(item for item in fixture[2].nodes if item.id == snapshot.current_node_id)
    exercise = next(item for item in fixture[2].exercises if item.id == node.exercise_ref.id)

    assert snapshot.score_package_digest == exercise.material.score_package_digest
    assert snapshot.score_id == exercise.material.score_id
    assert snapshot.graph_ref.id == fixture[2].id
    assert snapshot.current_node_id == fixture[4].prerequisite_node_id
    assert snapshot.support_state_ref.id == _support().id
    assert snapshot.mastery_projection_ref.id == fixture[7].id
    assert tuple(item.id for item in snapshot.evidence_record_refs) == tuple(
        item.id for item in fixture[9]
    )
    assert tuple(item.id for item in snapshot.observation_refs) == tuple(
        item.id for item in fixture[10]
    )
    assert '"type": "curriculum-decision-snapshot"' in payload
    assert curriculum_decision_snapshot_from_json(payload) == snapshot
    assert (
        curriculum_decision_snapshot_to_json(
            build_curriculum_decision_snapshot(
                fixture[2],
                fixture[4].prerequisite_node_id,
                _support(),
                fixture[7],
                fixture[9],
                fixture[10],
                run_id="run:trajectory-hcb-001",
                learner_context_id="learner-context:owner-beginner-001",
                decision_sequence=1,
                evidence_snapshot_sequence=2,
                budget_state=(CurriculumBudgetCounter("budget:prerequisite-attempts", 2, 4),),
            )
        )
        == payload
    )
    with pytest.raises(CurriculumSerializationError, match="unexpected"):
        curriculum_decision_snapshot_from_json(
            payload.replace('"run_id"', '"unexpected": true, "run_id"')
        )


def test_decision_snapshot_rejects_version_digest_and_budget_drift(
    hot_cross_buns_package: CanonicalMusicPackage,
) -> None:
    """TEST-CURR-VALIDATION-030: state identity and counters fail closed."""

    _, snapshot = _snapshot(hot_cross_buns_package)
    changed = replace(
        snapshot,
        snapshot_version="9.9.9",
        evidence_snapshot_fingerprint="0" * 64,
        budget_state=(CurriculumBudgetCounter("budget:prerequisite-attempts", 5, 4),),
    )
    codes = {item.code for item in validate_curriculum_decision_snapshot(changed)}

    assert "TMM-CONTRACT-UNKNOWN-VERSION" in codes
    assert "TMM-POLICY-SNAPSHOT-MISMATCH" in codes
    assert "TMM-POLICY-BUDGET-EXHAUSTED" in codes
    assert "TMM-CONTRACT-FINGERPRINT-MISMATCH" in codes

    data = json.loads(curriculum_decision_snapshot_to_json(snapshot))
    data["performance_contract_version"] = "9.9.9"
    with pytest.raises(CurriculumSerializationError, match="TMM-CONTRACT-UNKNOWN-VERSION"):
        curriculum_decision_snapshot_from_json(json.dumps(data))


def test_decision_snapshot_rejects_detached_policy_inputs(
    hot_cross_buns_package: CanonicalMusicPackage,
) -> None:
    """TEST-CURR-ROBUSTNESS-035: missing or changed policy knowledge fails closed."""

    fixture, _ = _snapshot(hot_cross_buns_package)
    arguments = (
        fixture[2],
        fixture[4].prerequisite_node_id,
        _support(),
        fixture[7],
        fixture[9],
        fixture[10],
    )
    keywords = {
        "run_id": "run:trajectory-hcb-001",
        "learner_context_id": "learner-context:owner-beginner-001",
        "decision_sequence": 1,
        "evidence_snapshot_sequence": 2,
    }

    with pytest.raises(CurriculumTrajectoryError, match="TMM-POLICY-SNAPSHOT-MISMATCH"):
        build_curriculum_decision_snapshot(
            *arguments[:4],
            fixture[9][:-1],
            fixture[10],
            **keywords,
        )
    referenced_ids = {
        identifier
        for record in fixture[9]
        for identifier in (*record.observation_ids, *record.context_observation_ids)
    }
    missing_id = next(iter(referenced_ids))
    with pytest.raises(CurriculumTrajectoryError, match="TMM-POLICY-SNAPSHOT-MISMATCH"):
        build_curriculum_decision_snapshot(
            *arguments[:5],
            tuple(item for item in fixture[10] if item.id != missing_id),
            **keywords,
        )
    with pytest.raises(CurriculumTrajectoryError, match="TMM-POLICY-SNAPSHOT-MISMATCH"):
        build_curriculum_decision_snapshot(
            fixture[2],
            fixture[4].prerequisite_node_id,
            replace(_support(), tempo_percent=70),
            *arguments[3:],
            **keywords,
        )


def test_action_inventory_round_trips_all_graph_candidates_before_selection(
    hot_cross_buns_package: CanonicalMusicPackage,
) -> None:
    """TEST-CURR-CONTRACT-018: complete candidates round-trip without a choice."""

    fixture, snapshot = _snapshot(hot_cross_buns_package)
    inventory = build_curriculum_action_inventory(fixture[2], fixture[7], snapshot)
    payload = curriculum_action_inventory_to_json(inventory)
    outgoing = tuple(
        item
        for item in fixture[2].edges
        if item.source_node_id == snapshot.current_node_id
        and item.kind.value in {"on-satisfied", "checkpoint-after", "return-to"}
    )

    assert tuple(item.edge_id for item in inventory.candidates) == tuple(
        item.id
        for item in sorted(outgoing, key=lambda item: (item.precedence, item.kind.value, item.id))
    )
    assert inventory.candidates
    assert all(
        item.eligibility is CurriculumActionEligibility.ALLOWED for item in inventory.candidates
    )
    assert curriculum_action_inventory_from_json(payload) == inventory
    assert '"selected_action"' not in payload
    assert '"probability"' not in payload
    assert '"reward"' not in payload
    with pytest.raises(CurriculumSerializationError, match="unexpected"):
        curriculum_action_inventory_from_json(
            payload.replace('"resolution"', '"selected_action": "progress", "resolution"')
        )


def test_action_inventory_validation_rejects_guard_and_candidate_drift(
    hot_cross_buns_package: CanonicalMusicPackage,
) -> None:
    """TEST-CURR-VALIDATION-031: inventory guard and completeness drift fail closed."""

    fixture, snapshot = _snapshot(hot_cross_buns_package)
    inventory = build_curriculum_action_inventory(fixture[2], fixture[7], snapshot)
    changed_candidate = replace(
        inventory.candidates[0],
        eligibility=CurriculumActionEligibility.EXCLUDED,
    )
    changed = replace(inventory, candidates=(changed_candidate, *inventory.candidates[1:]))
    codes = {
        item.code
        for item in validate_curriculum_action_inventory(
            changed,
            snapshot,
            fixture[2],
            fixture[7],
        )
    }
    assert "TMM-POLICY-GUARD-MISMATCH" in codes
    assert "TMM-CONTRACT-FINGERPRINT-MISMATCH" in codes

    missing = replace(inventory, candidates=inventory.candidates[:-1])
    missing_codes = {
        item.code
        for item in validate_curriculum_action_inventory(
            missing,
            snapshot,
            fixture[2],
            fixture[7],
        )
    }
    assert "TMM-POLICY-ACTION-INVENTORY-INCOMPLETE" in missing_codes


def test_action_inventory_preserves_excluded_routes_when_evidence_is_inconclusive(
    hot_cross_buns_package: CanonicalMusicPackage,
) -> None:
    """TEST-CURR-ROBUSTNESS-036: failed guards exclude but never erase routes."""

    fixture = _return_fixture(hot_cross_buns_package)
    graph = fixture[2]
    node_id = fixture[4].prerequisite_node_id
    mastery, _ = decide_curriculum_unlock(graph, node_id, _support(), ())
    snapshot = build_curriculum_decision_snapshot(
        graph,
        node_id,
        _support(),
        mastery,
        (),
        (),
        run_id="run:trajectory-hcb-inconclusive",
        learner_context_id="learner-context:owner-beginner-001",
        decision_sequence=1,
        evidence_snapshot_sequence=0,
    )
    inventory = build_curriculum_action_inventory(graph, mastery, snapshot)

    assert inventory.candidates
    assert all(
        item.eligibility is CurriculumActionEligibility.EXCLUDED for item in inventory.candidates
    )
    assert all(
        item.reason_code == "TMM-POLICY-EVIDENCE-INCOMPLETE" for item in inventory.candidates
    )
    assert all(item.guard_results[0].guard for item in inventory.candidates)


def test_happy_birthday_selection_records_one_deterministic_action_and_probability(
    happy_birthday_package: CanonicalMusicPackage,
) -> None:
    """TEST-CURR-CONTRACT-019: exact Happy Birthday selection round-trips."""

    graph, mastery, snapshot, inventory = _happy_birthday_action_state(happy_birthday_package)
    selection = select_curriculum_action(inventory, snapshot, graph, mastery)
    payload = curriculum_action_selection_to_json(selection)
    allowed = tuple(
        item
        for item in inventory.candidates
        if item.eligibility is CurriculumActionEligibility.ALLOWED
    )

    assert len(allowed) == 2
    assert selection.selected_candidate == allowed[0]
    assert selection.selected_candidate.action is CurriculumPolicyAction.RUN_CUMULATIVE
    assert selection.behavior_probability == Fraction(1)
    assert curriculum_action_selection_from_json(payload) == selection
    assert '"type": "curriculum-action-selection"' in payload
    assert '"outcome"' not in payload
    assert '"reward"' not in payload
    assert '"next_state"' not in payload
    with pytest.raises(CurriculumSerializationError, match="unexpected"):
        curriculum_action_selection_from_json(
            payload.replace('"selection_version"', '"unexpected": true, "selection_version"')
        )


def test_happy_birthday_selection_is_stable_under_frozen_precedence(
    happy_birthday_package: CanonicalMusicPackage,
) -> None:
    """TEST-CURR-POLICY-011: checkpoint wins the stable Happy Birthday tie."""

    graph, mastery, snapshot, inventory = _happy_birthday_action_state(happy_birthday_package)
    first = select_curriculum_action(inventory, snapshot, graph, mastery)
    second = select_curriculum_action(inventory, snapshot, graph, mastery)

    assert first == second
    assert first.selected_candidate.tie_break_values[1] == "edge-kind=checkpoint-after"
    assert first.selected_candidate.precedence == 0


def test_action_selection_rejects_nonfirst_probability_drift_and_empty_choice(
    happy_birthday_package: CanonicalMusicPackage,
) -> None:
    """TEST-CURR-ROBUSTNESS-037: selection drift and empty choice fail closed."""

    graph, mastery, snapshot, inventory = _happy_birthday_action_state(happy_birthday_package)
    selection = select_curriculum_action(inventory, snapshot, graph, mastery)
    allowed = tuple(
        item
        for item in inventory.candidates
        if item.eligibility is CurriculumActionEligibility.ALLOWED
    )
    changed = replace(
        selection,
        selected_candidate=allowed[1],
        behavior_probability=Fraction(1, 2),
    )
    codes = {
        item.code for item in validate_curriculum_action_selection(changed, inventory, snapshot)
    }

    assert "TMM-POLICY-SELECTION-MISMATCH" in codes
    assert "TMM-POLICY-PROBABILITY-MISMATCH" in codes
    assert "TMM-CONTRACT-FINGERPRINT-MISMATCH" in codes

    inconclusive = _happy_birthday_action_state(
        happy_birthday_package,
        with_evidence=False,
    )
    assert all(
        item.eligibility is CurriculumActionEligibility.EXCLUDED
        for item in inconclusive[3].candidates
    )
    with pytest.raises(CurriculumTrajectoryError, match="TMM-POLICY-NO-ALLOWED-ACTION"):
        select_curriculum_action(inconclusive[3], inconclusive[2], *inconclusive[:2])


def test_happy_birthday_transition_records_outcome_reward_and_exact_next_state(
    happy_birthday_package: CanonicalMusicPackage,
) -> None:
    """TEST-CURR-CONTRACT-020: one executed selection round-trips by exact refs."""

    _, selection, prior, outcome, reward, next_state, transition, *_ = _happy_birthday_transition(
        happy_birthday_package
    )
    payload = curriculum_transition_result_to_json(transition)

    assert selection.selected_candidate.action is CurriculumPolicyAction.RUN_CUMULATIVE
    assert outcome.practice_ref.artifact_type == "exercise-instance"
    assert reward.outcome_ref.id == outcome.id
    assert next_state.current_node_id == selection.selected_candidate.target_node_id
    assert next_state.decision_sequence == prior.decision_sequence + 1
    assert next_state.evidence_snapshot_sequence == prior.evidence_snapshot_sequence + 1
    assert next_state.attempt_sequence == (outcome.attempt_ref.id,)
    assert next_state.observation_refs == outcome.observation_refs
    assert curriculum_transition_result_from_json(payload) == transition
    assert '"type": "curriculum-transition-result"' in payload
    assert '"game_reward"' not in payload
    assert '"experiment_manifest"' not in payload


def test_happy_birthday_transition_rejects_sequence_and_target_drift(
    happy_birthday_package: CanonicalMusicPackage,
) -> None:
    """TEST-CURR-VALIDATION-032: transition sequence and target drift fail closed."""

    _, selection, prior, outcome, reward, next_state, transition, *_ = _happy_birthday_transition(
        happy_birthday_package
    )
    changed = replace(
        next_state,
        decision_sequence=prior.decision_sequence,
        current_node_id=prior.current_node_id,
    )
    codes = {
        item.code
        for item in validate_curriculum_transition_result(
            transition,
            selection,
            prior,
            outcome,
            reward,
            changed,
        )
    }

    assert "TMM-POLICY-TRANSITION-MISMATCH" in codes
    assert "TMM-POLICY-TRANSITION-SEQUENCE" in codes


def test_happy_birthday_transition_rejects_detached_reward_and_evidence(
    happy_birthday_package: CanonicalMusicPackage,
) -> None:
    """TEST-CURR-ROBUSTNESS-038: detached reward and evidence fail closed."""

    _, selection, prior, outcome, reward, next_state, transition, *_ = _happy_birthday_transition(
        happy_birthday_package
    )
    detached_reward = replace(reward, run_id="run:foreign")
    detached_state = replace(next_state, observation_refs=())
    codes = {
        item.code
        for item in validate_curriculum_transition_result(
            transition,
            selection,
            prior,
            outcome,
            detached_reward,
            detached_state,
        )
    }

    assert "TMM-POLICY-TRANSITION-REWARD-MISMATCH" in codes
    assert "TMM-POLICY-TRANSITION-EVIDENCE-MISMATCH" in codes


def test_happy_birthday_experiment_manifest_is_complete_compact_and_strict(
    happy_birthday_package: CanonicalMusicPackage,
) -> None:
    """TEST-CURR-CONTRACT-021: the bounded experiment index round-trips by refs."""

    inventory, selection, prior, outcome, reward, next_state, transition, *_ = (
        _happy_birthday_transition(happy_birthday_package)
    )
    manifest = build_curriculum_experiment_manifest(
        (prior, next_state),
        (inventory,),
        (selection,),
        (outcome,),
        (reward,),
        (transition,),
    )
    payload = curriculum_experiment_manifest_to_json(manifest)

    assert manifest.run_id == prior.run_id
    assert manifest.snapshot_refs[0].id == prior.id
    assert manifest.snapshot_refs[-1].id == next_state.id
    assert manifest.action_inventory_refs[0].id == inventory.id
    assert manifest.action_selection_refs[0].id == selection.id
    assert manifest.outcome_refs[0].id == outcome.id
    assert manifest.research_reward_refs[0].id == reward.id
    assert manifest.transition_refs[0].id == transition.id
    assert manifest.first_decision_sequence == prior.decision_sequence
    assert manifest.last_decision_sequence == next_state.decision_sequence
    assert curriculum_experiment_manifest_from_json(payload) == manifest
    assert '"type": "curriculum-experiment-manifest"' in payload
    assert '"candidates"' not in payload
    assert '"normalized_event_ids"' not in payload
    assert '"score_bytes"' not in payload
    with pytest.raises(CurriculumSerializationError, match="unexpected"):
        curriculum_experiment_manifest_from_json(
            payload.replace('"manifest_version"', '"unexpected": true, "manifest_version"')
        )


def test_experiment_manifest_rejects_cardinality_and_sequence_drift(
    happy_birthday_package: CanonicalMusicPackage,
) -> None:
    """TEST-CURR-VALIDATION-033: incomplete references and bounds fail closed."""

    inventory, selection, prior, outcome, reward, next_state, transition, *_ = (
        _happy_birthday_transition(happy_birthday_package)
    )
    manifest = build_curriculum_experiment_manifest(
        (prior, next_state),
        (inventory,),
        (selection,),
        (outcome,),
        (reward,),
        (transition,),
    )
    changed = replace(
        manifest,
        action_selection_refs=(),
        last_decision_sequence=manifest.first_decision_sequence,
    )
    codes = {item.code for item in validate_curriculum_experiment_manifest(changed)}

    assert "TMM-POLICY-MANIFEST-CARDINALITY" in codes
    assert "TMM-POLICY-MANIFEST-SEQUENCE" in codes
    assert "TMM-CONTRACT-FINGERPRINT-MISMATCH" in codes
    contextual_codes = {
        item.code
        for item in validate_curriculum_experiment_manifest(
            manifest,
            (prior, next_state),
            (inventory,),
            (selection,),
            (),
            (reward,),
            (transition,),
        )
    }
    assert "TMM-POLICY-MANIFEST-REFERENCE-MISMATCH" in contextual_codes
    with pytest.raises(CurriculumTrajectoryError, match="TMM-POLICY-MANIFEST-CARDINALITY"):
        build_curriculum_experiment_manifest((), (), (), (), (), ())


def test_experiment_manifest_rejects_reordered_or_foreign_chain(
    happy_birthday_package: CanonicalMusicPackage,
) -> None:
    """TEST-CURR-ROBUSTNESS-039: reordered state and foreign outcomes fail closed."""

    inventory, selection, prior, outcome, reward, next_state, transition, *_ = (
        _happy_birthday_transition(happy_birthday_package)
    )
    manifest = build_curriculum_experiment_manifest(
        (prior, next_state),
        (inventory,),
        (selection,),
        (outcome,),
        (reward,),
        (transition,),
    )
    foreign_outcome = replace(outcome, run_id="run:foreign")
    codes = {
        item.code
        for item in validate_curriculum_experiment_manifest(
            manifest,
            (next_state, prior),
            (inventory,),
            (selection,),
            (foreign_outcome,),
            (reward,),
            (transition,),
        )
    }

    assert "TMM-POLICY-MANIFEST-REFERENCE-MISMATCH" in codes
    assert "TMM-POLICY-MANIFEST-SNAPSHOT-MISMATCH" in codes
    assert "TMM-POLICY-MANIFEST-CHAIN-MISMATCH" in codes
