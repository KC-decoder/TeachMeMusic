"""Executable DEV-009 Task 9J deterministic trajectory replay evidence."""

from __future__ import annotations

from dataclasses import replace
from typing import cast

import pytest

from teachmemusic.performance import MidiEventKind
from teachmemusic.score import CanonicalMusicPackage
from teachmemusic.teaching import (
    CurriculumReplayError,
    CurriculumResearchReward,
    EvidenceContext,
    build_curriculum_experiment_manifest,
    build_curriculum_game_reward,
    reconstruct_curriculum_action_decision,
    reconstruct_curriculum_mastery_projection,
    reconstruct_curriculum_observations,
    reconstruct_curriculum_research_reward,
)
from tests.teaching.test_curriculum_trajectory import _happy_birthday_transition


def _replay_fixture(package: CanonicalMusicPackage):
    (
        inventory,
        selection,
        prior,
        outcome,
        reward,
        next_state,
        transition,
        expected,
        attempt,
        calibration,
        observations,
        *_,
    ) = _happy_birthday_transition(package)
    manifest = build_curriculum_experiment_manifest(
        (prior, next_state),
        (inventory,),
        (selection,),
        (outcome,),
        (reward,),
        (transition,),
    )
    return manifest, outcome, expected, attempt, calibration, observations


def _mastery_replay_fixture(package: CanonicalMusicPackage):
    (
        inventory,
        selection,
        prior,
        outcome,
        reward,
        next_state,
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
        _,
    ) = _happy_birthday_transition(package)
    manifest = build_curriculum_experiment_manifest(
        (prior, next_state),
        (inventory,),
        (selection,),
        (outcome,),
        (reward,),
        (transition,),
    )
    return (
        manifest,
        outcome,
        next_state,
        graph,
        requirements,
        expected,
        attempt,
        calibration,
        support,
        EvidenceContext.INDEPENDENT,
        observations,
        records,
        next_mastery,
    )


def _action_replay_fixture(package: CanonicalMusicPackage):
    (
        inventory,
        selection,
        prior,
        outcome,
        reward,
        next_state,
        transition,
        _expected,
        _attempt,
        _calibration,
        _observations,
        graph,
        _requirements,
        _support,
        _records,
        _next_mastery,
        mastery,
    ) = _happy_birthday_transition(package)
    manifest = build_curriculum_experiment_manifest(
        (prior, next_state),
        (inventory,),
        (selection,),
        (outcome,),
        (reward,),
        (transition,),
    )
    return manifest, prior, graph, mastery, inventory, selection


def _reward_replay_fixture(package: CanonicalMusicPackage):
    (
        inventory,
        selection,
        prior,
        outcome,
        reward,
        next_state,
        transition,
        expected,
        attempt,
        calibration,
        observations,
        *_,
    ) = _happy_birthday_transition(package)
    manifest = build_curriculum_experiment_manifest(
        (prior, next_state),
        (inventory,),
        (selection,),
        (outcome,),
        (reward,),
        (transition,),
    )
    return manifest, outcome, expected, attempt, calibration, observations, reward


def test_happy_birthday_observations_reconstruct_exactly(
    happy_birthday_package: CanonicalMusicPackage,
) -> None:
    """TEST-CURR-REPLAY-001: governed attempt inputs reproduce exact facts."""

    fixture = _replay_fixture(happy_birthday_package)
    first = reconstruct_curriculum_observations(*fixture)
    second = reconstruct_curriculum_observations(*fixture)

    assert first == fixture[-1]
    assert second == first
    assert tuple(item.id for item in first) == tuple(item.id for item in fixture[-1])


def test_observation_replay_rejects_outcome_absent_from_manifest(
    happy_birthday_package: CanonicalMusicPackage,
) -> None:
    """TEST-CURR-VALIDATION-034: an unreferenced outcome cannot be replayed."""

    manifest, outcome, expected, attempt, calibration, observations = _replay_fixture(
        happy_birthday_package
    )
    foreign_outcome = replace(outcome, id="curriculum-learning-outcome:foreign")

    with pytest.raises(CurriculumReplayError, match="TMM-STORE-REFERENCE-MISSING"):
        reconstruct_curriculum_observations(
            manifest,
            foreign_outcome,
            expected,
            attempt,
            calibration,
            observations,
        )


def test_observation_replay_rejects_mutated_attempt_or_recorded_facts(
    happy_birthday_package: CanonicalMusicPackage,
) -> None:
    """TEST-CURR-ROBUSTNESS-040: input or observation drift fails closed."""

    manifest, outcome, expected, attempt, calibration, observations = _replay_fixture(
        happy_birthday_package
    )
    first_note_on = next(
        index
        for index, event in enumerate(attempt.normalized_events)
        if event.kind is MidiEventKind.NOTE_ON
    )
    changed_event = replace(
        attempt.normalized_events[first_note_on],
        note=attempt.normalized_events[first_note_on].note + 1,
    )
    changed_attempt = replace(
        attempt,
        normalized_events=(
            *attempt.normalized_events[:first_note_on],
            changed_event,
            *attempt.normalized_events[first_note_on + 1 :],
        ),
    )
    with pytest.raises(CurriculumReplayError, match="TMM-POLICY-REPLAY-MISMATCH"):
        reconstruct_curriculum_observations(
            manifest,
            outcome,
            expected,
            changed_attempt,
            calibration,
            observations,
        )

    with pytest.raises(CurriculumReplayError, match="TMM-POLICY-REPLAY-MISMATCH"):
        reconstruct_curriculum_observations(
            manifest,
            outcome,
            expected,
            attempt,
            calibration,
            observations[:-1],
        )


def test_happy_birthday_mastery_projection_reconstructs_exactly(
    happy_birthday_package: CanonicalMusicPackage,
) -> None:
    """TEST-CURR-REPLAY-002: replayed facts reproduce exact learner state."""

    fixture = _mastery_replay_fixture(happy_birthday_package)
    first = reconstruct_curriculum_mastery_projection(*fixture)
    second = reconstruct_curriculum_mastery_projection(*fixture)

    assert first == fixture[-1]
    assert second == first
    assert fixture[2].mastery_projection_ref.id == first.id


def test_mastery_replay_rejects_detached_next_state_projection(
    happy_birthday_package: CanonicalMusicPackage,
) -> None:
    """TEST-CURR-VALIDATION-035: next-state projection drift fails closed."""

    fixture = _mastery_replay_fixture(happy_birthday_package)
    changed_state = replace(
        fixture[2],
        mastery_projection_ref=replace(
            fixture[2].mastery_projection_ref,
            id="curriculum-mastery-projection:foreign",
        ),
    )

    with pytest.raises(CurriculumReplayError, match="TMM-POLICY-REPLAY-MISMATCH"):
        reconstruct_curriculum_mastery_projection(
            fixture[0],
            fixture[1],
            changed_state,
            *fixture[3:],
        )


def test_mastery_replay_rejects_evidence_order_or_support_drift(
    happy_birthday_package: CanonicalMusicPackage,
) -> None:
    """TEST-CURR-ROBUSTNESS-041: evidence and support identity fail closed."""

    fixture = _mastery_replay_fixture(happy_birthday_package)
    reordered = (*fixture[:11], tuple(reversed(fixture[11])), fixture[12])
    with pytest.raises(CurriculumReplayError, match="TMM-POLICY-REPLAY-MISMATCH"):
        reconstruct_curriculum_mastery_projection(*reordered)

    changed_support = replace(fixture[8], tempo_percent=fixture[8].tempo_percent - 5)
    changed = (*fixture[:8], changed_support, *fixture[9:])
    with pytest.raises(CurriculumReplayError, match="TMM-POLICY-REPLAY-MISMATCH"):
        reconstruct_curriculum_mastery_projection(*changed)


def test_happy_birthday_action_decision_reconstructs_exactly(
    happy_birthday_package: CanonicalMusicPackage,
) -> None:
    """TEST-CURR-REPLAY-003: replay reproduces all guards and one action."""

    fixture = _action_replay_fixture(happy_birthday_package)
    first = reconstruct_curriculum_action_decision(*fixture)
    second = reconstruct_curriculum_action_decision(*fixture)

    assert first == fixture[-2:]
    assert second == first
    assert first[1].selected_candidate in first[0].candidates


def test_action_replay_rejects_detached_selection(
    happy_birthday_package: CanonicalMusicPackage,
) -> None:
    """TEST-CURR-VALIDATION-036: detached selection identity fails closed."""

    fixture = _action_replay_fixture(happy_birthday_package)
    changed_selection = replace(
        fixture[-1],
        inventory_ref=replace(
            fixture[-1].inventory_ref,
            id="curriculum-action-inventory:foreign",
        ),
    )

    with pytest.raises(CurriculumReplayError, match="TMM-POLICY-REPLAY-MISMATCH"):
        reconstruct_curriculum_action_decision(*fixture[:-1], changed_selection)


def test_action_replay_rejects_candidate_order_or_snapshot_drift(
    happy_birthday_package: CanonicalMusicPackage,
) -> None:
    """TEST-CURR-ROBUSTNESS-042: inventory and decision-state drift fail closed."""

    fixture = _action_replay_fixture(happy_birthday_package)
    changed_inventory = replace(
        fixture[-2],
        candidates=tuple(reversed(fixture[-2].candidates)),
    )
    with pytest.raises(CurriculumReplayError, match="TMM-POLICY-REPLAY-MISMATCH"):
        reconstruct_curriculum_action_decision(
            *fixture[:-2],
            changed_inventory,
            fixture[-1],
        )

    changed_snapshot = replace(
        fixture[1],
        decision_sequence=fixture[1].decision_sequence + 1,
    )
    with pytest.raises(CurriculumReplayError, match="TMM-POLICY-REPLAY-MISMATCH"):
        reconstruct_curriculum_action_decision(
            fixture[0],
            changed_snapshot,
            *fixture[2:],
        )


def test_happy_birthday_research_reward_reconstructs_exactly(
    happy_birthday_package: CanonicalMusicPackage,
) -> None:
    """TEST-CURR-REPLAY-004: replay reproduces exact separate components."""

    fixture = _reward_replay_fixture(happy_birthday_package)
    first = reconstruct_curriculum_research_reward(*fixture)
    second = reconstruct_curriculum_research_reward(*fixture)

    assert first == fixture[-1]
    assert second == first
    assert not hasattr(first, "aggregate_value")


def test_reward_replay_rejects_detached_outcome_identity(
    happy_birthday_package: CanonicalMusicPackage,
) -> None:
    """TEST-CURR-VALIDATION-037: reward/outcome detachment fails closed."""

    fixture = _reward_replay_fixture(happy_birthday_package)
    changed_reward = replace(
        fixture[-1],
        outcome_ref=replace(
            fixture[-1].outcome_ref,
            id="curriculum-learning-outcome:foreign",
        ),
    )

    with pytest.raises(CurriculumReplayError, match="TMM-POLICY-REPLAY-MISMATCH"):
        reconstruct_curriculum_research_reward(*fixture[:-1], changed_reward)


def test_reward_replay_rejects_component_drift_or_game_feedback(
    happy_birthday_package: CanonicalMusicPackage,
) -> None:
    """TEST-CURR-ROBUSTNESS-043: components and game feedback fail closed."""

    fixture = _reward_replay_fixture(happy_birthday_package)
    changed_reward = replace(
        fixture[-1],
        components=tuple(reversed(fixture[-1].components)),
    )
    with pytest.raises(CurriculumReplayError, match="TMM-POLICY-REPLAY-MISMATCH"):
        reconstruct_curriculum_research_reward(*fixture[:-1], changed_reward)

    game_reward = build_curriculum_game_reward(fixture[1], fixture[-1])
    with pytest.raises(CurriculumReplayError, match="TMM-REWARD-REPLAY-TYPE"):
        reconstruct_curriculum_research_reward(
            *fixture[:-1],
            cast(CurriculumResearchReward, game_reward),
        )


def test_every_replay_boundary_rejects_unknown_manifest_version(
    happy_birthday_package: CanonicalMusicPackage,
) -> None:
    """TEST-CURR-REPLAY-005: every replay path shares one version gate."""

    replay_cases = (
        (reconstruct_curriculum_observations, _replay_fixture(happy_birthday_package)),
        (
            reconstruct_curriculum_mastery_projection,
            _mastery_replay_fixture(happy_birthday_package),
        ),
        (
            reconstruct_curriculum_action_decision,
            _action_replay_fixture(happy_birthday_package),
        ),
        (
            reconstruct_curriculum_research_reward,
            _reward_replay_fixture(happy_birthday_package),
        ),
    )
    for replay, fixture in replay_cases:
        unknown_manifest = replace(fixture[0], manifest_version="unsupported-999")
        with pytest.raises(CurriculumReplayError, match="TMM-REPLAY-VERSION-MISMATCH"):
            replay(unknown_manifest, *fixture[1:])
        assert unknown_manifest.manifest_version == "unsupported-999"


def test_replay_rejects_each_governing_manifest_version(
    happy_birthday_package: CanonicalMusicPackage,
) -> None:
    """TEST-CURR-VALIDATION-038: contract and policy versions fail explicitly."""

    fixture = _replay_fixture(happy_birthday_package)
    incompatible_manifests = (
        replace(fixture[0], curriculum_contract_version="unsupported-curriculum"),
        replace(fixture[0], performance_contract_version="unsupported-performance"),
        replace(fixture[0], evidence_archive_contract_version="unsupported-evidence"),
        replace(fixture[0], policy_identity="unsupported-policy"),
    )
    for manifest in incompatible_manifests:
        with pytest.raises(
            CurriculumReplayError,
            match="TMM-REPLAY-VERSION-MISMATCH.*explicit tested migration",
        ):
            reconstruct_curriculum_observations(manifest, *fixture[1:])


def test_replay_rejects_nested_artifact_and_rule_version_drift(
    happy_birthday_package: CanonicalMusicPackage,
) -> None:
    """TEST-CURR-ROBUSTNESS-044: artifacts never silently migrate."""

    action_fixture = _action_replay_fixture(happy_birthday_package)
    unknown_snapshot = replace(action_fixture[1], snapshot_version="unsupported-snapshot")
    with pytest.raises(CurriculumReplayError, match="TMM-REPLAY-VERSION-MISMATCH"):
        reconstruct_curriculum_action_decision(
            action_fixture[0],
            unknown_snapshot,
            *action_fixture[2:],
        )

    unknown_inventory = replace(action_fixture[4], inventory_version="unsupported-inventory")
    with pytest.raises(CurriculumReplayError, match="TMM-REPLAY-VERSION-MISMATCH"):
        reconstruct_curriculum_action_decision(
            *action_fixture[:4],
            unknown_inventory,
            action_fixture[5],
        )

    unknown_selection = replace(action_fixture[5], selection_version="unsupported-selection")
    with pytest.raises(CurriculumReplayError, match="TMM-REPLAY-VERSION-MISMATCH"):
        reconstruct_curriculum_action_decision(*action_fixture[:5], unknown_selection)

    reward_fixture = _reward_replay_fixture(happy_birthday_package)
    unknown_reward = replace(
        reward_fixture[-1],
        generation_rule=replace(
            reward_fixture[-1].generation_rule,
            rule_version="unsupported-reward",
        ),
    )
    with pytest.raises(CurriculumReplayError, match="TMM-REPLAY-VERSION-MISMATCH"):
        reconstruct_curriculum_research_reward(*reward_fixture[:-1], unknown_reward)

    assert unknown_snapshot.snapshot_version == "unsupported-snapshot"
    assert unknown_inventory.inventory_version == "unsupported-inventory"
    assert unknown_selection.selection_version == "unsupported-selection"
    assert unknown_reward.generation_rule.rule_version == "unsupported-reward"
