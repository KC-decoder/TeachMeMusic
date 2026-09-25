"""Tests for versioned deterministic score serialization."""

import json

import pytest

from teachmemusic.score.models import ScoreRepresentation
from teachmemusic.score.serializer import (
    ScoreSerializationError,
    score_from_json,
    score_to_dict,
    score_to_json,
)


def test_hot_cross_buns_round_trips_without_information_loss(
    hot_cross_buns_score: ScoreRepresentation,
) -> None:
    """TEST-SCORE-016 — verifies the REQ-SCORE-005 reference round trip."""

    payload = score_to_json(hot_cross_buns_score)

    assert score_from_json(payload) == hot_cross_buns_score


def test_json_output_is_deterministic_and_exact(
    hot_cross_buns_score: ScoreRepresentation,
) -> None:
    """TEST-SCORE-017 — verifies deterministic exact REQ-SCORE-005 JSON."""

    first = score_to_json(hot_cross_buns_score)
    second = score_to_json(hot_cross_buns_score)
    data = json.loads(first)

    assert first == second
    assert first.endswith("\n")
    assert data["schema_version"] == 1
    assert data["parts"][0]["measures"][0]["extent"] == {
        "denominator": 1,
        "numerator": 4,
    }
    assert data["parts"][0]["measures"][0]["events"][0]["duration"] == {
        "denominator": 1,
        "numerator": 2,
    }


def test_serialization_preserves_unknown_and_deliberately_empty_values(
    hot_cross_buns_score: ScoreRepresentation,
) -> None:
    """TEST-SCORE-018 — verifies REQ-SCORE-004 metadata distinctions."""

    data = score_to_dict(hot_cross_buns_score)
    restored = score_from_json(json.dumps(data))

    assert restored.metadata.creators == ()
    assert restored.parts[0].display_name == ""
    assert restored.parts[0].staves[0].source_number is None


def test_unknown_schema_version_is_rejected(
    hot_cross_buns_score: ScoreRepresentation,
) -> None:
    """TEST-SCORE-019 — verifies REQ-SCORE-005 schema-version rejection."""

    data = json.loads(score_to_json(hot_cross_buns_score))
    data["schema_version"] = 2

    with pytest.raises(ScoreSerializationError, match="unsupported version"):
        score_from_json(json.dumps(data))


def test_unsupported_event_kind_is_reported(
    hot_cross_buns_score: ScoreRepresentation,
) -> None:
    """TEST-SCORE-020 — verifies unsupported content is not silently lost."""

    data = json.loads(score_to_json(hot_cross_buns_score))
    data["parts"][0]["measures"][0]["events"][0]["kind"] = "chord"

    with pytest.raises(ScoreSerializationError, match="unsupported event kind"):
        score_from_json(json.dumps(data))


def test_lyrics_cannot_be_attached_to_a_rest(
    hot_cross_buns_score: ScoreRepresentation,
) -> None:
    """TEST-SCORE-021 — verifies the REQ-SCORE-004 lyric association."""

    data = json.loads(score_to_json(hot_cross_buns_score))
    rest = data["parts"][0]["measures"][1]["events"][1]
    rest["lyrics"] = []

    with pytest.raises(ScoreSerializationError, match="unexpected.*lyrics"):
        score_from_json(json.dumps(data))


def test_malformed_json_is_rejected() -> None:
    """TEST-SCORE-022 — verifies malformed REQ-SCORE-005 input fails clearly."""

    with pytest.raises(ScoreSerializationError, match="invalid JSON"):
        score_from_json("{not-json}")


def test_happy_birthday_chords_and_harmonies_round_trip(
    happy_birthday_score: ScoreRepresentation,
) -> None:
    """TEST-SCORE-028 — verifies expanded REQ-SCORE-005 lossless JSON."""

    payload = score_to_json(happy_birthday_score)
    data = json.loads(payload)
    first_measure = data["parts"][0]["measures"][0]

    assert score_from_json(payload) == happy_birthday_score
    assert first_measure["harmonies"] == [
        {
            "display_text": "",
            "id": "harmony-happy-p1-m1-1",
            "kind": "major",
            "onset": {"denominator": 1, "numerator": 1},
            "root": {
                "alter": {"denominator": 1, "numerator": 0},
                "step": "C",
            },
            "source_order": 0,
            "staff_id": "staff-happy-p1-1",
        }
    ]
    chord_ids = {
        event["chord_id"]
        for event in first_measure["events"]
        if event["kind"] == "note" and event["chord_id"] is not None
    }
    assert chord_ids == {"chord-happy-p1-m1-6"}
