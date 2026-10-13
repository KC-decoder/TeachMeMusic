"""Executable DEV-009 Task 9H.4 reward-to-authority isolation evidence."""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import replace
from typing import cast

import pytest

from teachmemusic.performance import Observation, align_layer_attempt
from teachmemusic.score import CanonicalMusicPackage
from teachmemusic.teaching import (
    CurriculumEvidenceError,
    CurriculumEvidenceRecord,
    CurriculumLearningOutcomeError,
    CurriculumPolicyError,
    CurriculumResearchRewardError,
    CurriculumSerializationError,
    EvidenceContext,
    GameRewardSignal,
    build_curriculum_evidence_records,
    build_curriculum_fundamental_practice,
    build_curriculum_game_reward,
    build_curriculum_learning_outcome,
    build_curriculum_research_reward,
    curriculum_evidence_record_from_json,
    curriculum_evidence_record_to_json,
    curriculum_learning_outcome_from_json,
    curriculum_learning_outcome_to_json,
    curriculum_mastery_projection_from_json,
    curriculum_mastery_projection_to_json,
    curriculum_research_reward_from_json,
    curriculum_research_reward_to_json,
    curriculum_unlock_decision_from_json,
    curriculum_unlock_decision_to_json,
    decide_curriculum_unlock,
    require_compatible_curriculum_evidence,
)
from tests.teaching.test_curriculum_fundamental_practice import (
    _calibration,
    _resolved_fundamental,
)
from tests.teaching.test_curriculum_fundamental_returns import (
    _return_fixture,
)
from tests.teaching.test_curriculum_fundamental_returns import (
    _support as _return_support,
)
from tests.teaching.test_curriculum_learning_outcomes import (
    _attempt,
    _support,
)


def _reward_fixture(package: CanonicalMusicPackage):
    inputs = _resolved_fundamental(package, primitive_id="PRIM-KEY-001")
    practice = build_curriculum_fundamental_practice(package, *inputs)
    calibration = _calibration()
    support = _support()
    attempt = _attempt(practice.expected)
    observations = align_layer_attempt(practice.expected, attempt, calibration)
    outcome = build_curriculum_learning_outcome(
        practice.binding,
        practice.expected,
        attempt,
        calibration,
        support,
        observations,
    )
    research_reward = build_curriculum_research_reward(
        outcome,
        practice.expected,
        observations,
    )
    game_reward = build_curriculum_game_reward(outcome, research_reward)
    return (
        inputs[0],
        practice,
        calibration,
        support,
        attempt,
        observations,
        outcome,
        research_reward,
        game_reward,
    )


def test_game_reward_cannot_enter_outcome_research_or_evidence_inputs(
    hot_cross_buns_package: CanonicalMusicPackage,
) -> None:
    """TEST-CURR-ROBUSTNESS-034: game feedback cannot become a factual input."""

    (
        requirements,
        practice,
        calibration,
        support,
        attempt,
        _,
        outcome,
        _,
        game_reward,
    ) = _reward_fixture(hot_cross_buns_package)
    leaked = cast(tuple[Observation, ...], (game_reward,))

    with pytest.raises(CurriculumLearningOutcomeError, match="TMM-OUTCOME-OBSERVATION-TYPE"):
        build_curriculum_learning_outcome(
            practice.binding,
            practice.expected,
            attempt,
            calibration,
            support,
            leaked,
        )
    with pytest.raises(CurriculumResearchRewardError, match="TMM-REWARD-OBSERVATION-TYPE"):
        build_curriculum_research_reward(outcome, practice.expected, leaked)
    with pytest.raises(CurriculumEvidenceError, match="TMM-EVIDENCE-OBSERVATION-TYPE"):
        build_curriculum_evidence_records(
            requirements,
            practice.expected,
            attempt,
            support,
            leaked,
            EvidenceContext.ACQUISITION,
        )
    leaked_records = cast(tuple[CurriculumEvidenceRecord, ...], (game_reward,))
    with pytest.raises(CurriculumEvidenceError, match="TMM-EVIDENCE-RECORD-TYPE"):
        require_compatible_curriculum_evidence(
            leaked_records,
            requirements,
            practice.expected,
            attempt,
            support,
            (),
            EvidenceContext.ACQUISITION,
        )


def test_game_reward_cannot_change_mastery_or_unlock_policy(
    hot_cross_buns_package: CanonicalMusicPackage,
) -> None:
    """TEST-CURR-POLICY-010: game feedback is absent from policy authority."""

    route = _return_fixture(hot_cross_buns_package)
    reward_fixture = _reward_fixture(hot_cross_buns_package)
    game_reward = reward_fixture[-1]
    upstream_before = (
        curriculum_learning_outcome_to_json(reward_fixture[6]),
        curriculum_research_reward_to_json(reward_fixture[7]),
        tuple(curriculum_evidence_record_to_json(item) for item in route[9]),
        curriculum_mastery_projection_to_json(route[7]),
        curriculum_unlock_decision_to_json(route[8]),
    )

    changed_feedback = replace(
        game_reward,
        signal=GameRewardSignal.RESULT_UNAVAILABLE,
        message_code="GAME_RESULT_UNAVAILABLE",
        source_component_ids=(),
    )
    assert changed_feedback != game_reward
    replayed = decide_curriculum_unlock(
        route[2],
        route[4].prerequisite_node_id,
        _return_support(),
        route[9],
        attempt_sequence=route[7].evaluated_attempt_ids,
    )
    assert replayed == (route[7], route[8])
    assert upstream_before == (
        curriculum_learning_outcome_to_json(reward_fixture[6]),
        curriculum_research_reward_to_json(reward_fixture[7]),
        tuple(curriculum_evidence_record_to_json(item) for item in route[9]),
        curriculum_mastery_projection_to_json(route[7]),
        curriculum_unlock_decision_to_json(route[8]),
    )

    leaked = cast(tuple[CurriculumEvidenceRecord, ...], (game_reward,))
    with pytest.raises(CurriculumPolicyError, match="TMM-POLICY-EVIDENCE-TYPE"):
        decide_curriculum_unlock(
            route[2],
            route[4].prerequisite_node_id,
            _return_support(),
            leaked,
        )


def test_authoritative_wire_contracts_reject_game_reward_injection(
    hot_cross_buns_package: CanonicalMusicPackage,
) -> None:
    """TEST-CURR-CONTRACT-016: authority records reject game fields strictly."""

    reward_fixture = _reward_fixture(hot_cross_buns_package)
    route = _return_fixture(hot_cross_buns_package)
    decoders: tuple[tuple[str, Callable[[str], object]], ...] = (
        (
            curriculum_learning_outcome_to_json(reward_fixture[6]),
            curriculum_learning_outcome_from_json,
        ),
        (
            curriculum_research_reward_to_json(reward_fixture[7]),
            curriculum_research_reward_from_json,
        ),
        (curriculum_evidence_record_to_json(route[9][0]), curriculum_evidence_record_from_json),
        (curriculum_mastery_projection_to_json(route[7]), curriculum_mastery_projection_from_json),
        (curriculum_unlock_decision_to_json(route[8]), curriculum_unlock_decision_from_json),
    )

    for payload, decoder in decoders:
        injected = json.loads(payload)
        injected["game_reward_ref"] = {
            "type": "curriculum-game-reward",
            "id": reward_fixture[8].id,
            "semantic_fingerprint": reward_fixture[8].semantic_fingerprint,
        }
        with pytest.raises(CurriculumSerializationError, match="unexpected"):
            decoder(json.dumps(injected))
