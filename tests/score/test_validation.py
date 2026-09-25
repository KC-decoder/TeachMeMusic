"""Negative and boundary tests for canonical-score validation."""

from dataclasses import replace
from fractions import Fraction

import pytest

from teachmemusic.score.models import NoteEvent, PresentationData, ScoreRepresentation
from teachmemusic.score.validation import ScoreValidationError, require_valid_score, validate_score


def _replace_first_measure(
    score: ScoreRepresentation,
    **changes: object,
) -> ScoreRepresentation:
    part = score.parts[0]
    measure = replace(part.measures[0], **changes)
    return replace(score, parts=(replace(part, measures=(measure, *part.measures[1:])),))


def _issue_codes(score: ScoreRepresentation) -> set[str]:
    return {issue.code for issue in validate_score(score)}


def test_duplicate_ids_are_rejected(hot_cross_buns_score: ScoreRepresentation) -> None:
    """TEST-SCORE-009 — verifies REQ-SCORE-002 duplicate-ID rejection."""

    first = hot_cross_buns_score.parts[0].measures[0]
    duplicate = replace(first.events[1], id=first.events[0].id)
    invalid = _replace_first_measure(hot_cross_buns_score, events=(first.events[0], duplicate))

    assert "DUPLICATE_ID" in _issue_codes(invalid)


def test_unknown_voice_reference_is_rejected(hot_cross_buns_score: ScoreRepresentation) -> None:
    """TEST-SCORE-010 — verifies REQ-SCORE-002 reference integrity."""

    first = hot_cross_buns_score.parts[0].measures[0]
    invalid_event = replace(first.events[0], voice_id="missing-voice")
    invalid = _replace_first_measure(
        hot_cross_buns_score,
        events=(invalid_event, first.events[1]),
    )

    assert "UNKNOWN_VOICE_REFERENCE" in _issue_codes(invalid)


@pytest.mark.parametrize(
    ("changes", "expected_code"),
    [
        ({"duration": Fraction(-1)}, "NON_POSITIVE_DURATION"),
        ({"onset": Fraction(4)}, "EVENT_OUTSIDE_MEASURE"),
        ({"duration": Fraction(1)}, "RHYTHM_DURATION_MISMATCH"),
    ],
)
def test_invalid_event_time_is_rejected(
    hot_cross_buns_score: ScoreRepresentation,
    changes: dict[str, object],
    expected_code: str,
) -> None:
    """TEST-SCORE-011 — verifies REQ-SCORE-003 and REQ-SCORE-005 time checks."""

    first = hot_cross_buns_score.parts[0].measures[0]
    invalid_event = replace(first.events[0], **changes)
    invalid = _replace_first_measure(
        hot_cross_buns_score,
        events=(invalid_event, first.events[1]),
    )

    assert expected_code in _issue_codes(invalid)


def test_unsorted_events_are_rejected(hot_cross_buns_score: ScoreRepresentation) -> None:
    """TEST-SCORE-012 — verifies REQ-SCORE-002 deterministic ordering."""

    first = hot_cross_buns_score.parts[0].measures[0]
    invalid = _replace_first_measure(hot_cross_buns_score, events=tuple(reversed(first.events)))

    assert "UNSORTED_EVENTS" in _issue_codes(invalid)


def test_pickup_measure_is_valid_even_when_it_does_not_fill_meter(
    hot_cross_buns_score: ScoreRepresentation,
) -> None:
    """TEST-SCORE-013 — verifies REQ-SCORE-005 permits pickup measures."""

    part = hot_cross_buns_score.parts[0]
    quarter_note = part.measures[4].events[0]
    assert isinstance(quarter_note, NoteEvent)
    pickup_event = replace(quarter_note, id="event-pickup", source_order=0)
    pickup = replace(
        part.measures[0],
        extent=Fraction(1),
        events=(pickup_event,),
    )
    score = replace(
        hot_cross_buns_score,
        parts=(replace(part, measures=(pickup,)),),
        presentation=PresentationData(),
    )

    assert validate_score(score) == ()


def test_require_valid_score_raises_structured_error(
    hot_cross_buns_score: ScoreRepresentation,
) -> None:
    """TEST-SCORE-014 — verifies REQ-SCORE-005 structured failures."""

    invalid = replace(hot_cross_buns_score, schema_version=999)

    with pytest.raises(ScoreValidationError) as error:
        require_valid_score(invalid)

    assert error.value.issues[0].code == "UNSUPPORTED_SCHEMA_VERSION"


def test_mid_measure_attribute_change_is_explicitly_unsupported(
    hot_cross_buns_score: ScoreRepresentation,
) -> None:
    """TEST-SCORE-015 — records DEV-004's explicit notation boundary."""

    first = hot_cross_buns_score.parts[0].measures[0]
    change = replace(first.attribute_changes[0], onset=Fraction(1))
    invalid = _replace_first_measure(
        hot_cross_buns_score,
        attribute_changes=(change,),
    )

    assert "UNSUPPORTED_MID_MEASURE_ATTRIBUTE" in _issue_codes(invalid)


def test_single_note_chord_is_rejected(happy_birthday_score: ScoreRepresentation) -> None:
    """TEST-SCORE-025 — verifies malformed chord membership is rejected."""

    first = happy_birthday_score.parts[0].measures[0]
    chord_members = [
        event
        for event in first.events
        if isinstance(event, NoteEvent) and event.chord_id is not None
    ]
    chord_id = chord_members[0].chord_id
    events = tuple(
        replace(event, chord_id=None)
        if isinstance(event, NoteEvent) and event.chord_id == chord_id and event != chord_members[0]
        else event
        for event in first.events
    )
    invalid = _replace_first_measure(happy_birthday_score, events=events)

    assert "SINGLE_NOTE_CHORD" in _issue_codes(invalid)


def test_inconsistent_chord_members_are_rejected(
    happy_birthday_score: ScoreRepresentation,
) -> None:
    """TEST-SCORE-026 — verifies chord members share notation and timing."""

    first = happy_birthday_score.parts[0].measures[0]
    chord_members = [
        event
        for event in first.events
        if isinstance(event, NoteEvent) and event.chord_id is not None
    ]
    changed_id = chord_members[1].id
    events = tuple(
        replace(event, staff_id=happy_birthday_score.parts[0].staves[0].id)
        if event.id == changed_id
        else event
        for event in first.events
    )
    invalid = _replace_first_measure(happy_birthday_score, events=events)

    assert "INCONSISTENT_CHORD" in _issue_codes(invalid)


@pytest.mark.parametrize(
    ("changes", "expected_code"),
    [
        ({"staff_id": "missing-staff"}, "UNKNOWN_STAFF_REFERENCE"),
        ({"onset": Fraction(3)}, "HARMONY_OUTSIDE_MEASURE"),
        ({"kind": ""}, "INVALID_HARMONY_KIND"),
    ],
)
def test_invalid_harmony_is_rejected(
    happy_birthday_score: ScoreRepresentation,
    changes: dict[str, object],
    expected_code: str,
) -> None:
    """TEST-SCORE-027 — verifies harmony reference and value constraints."""

    first = happy_birthday_score.parts[0].measures[0]
    harmony = replace(first.harmonies[0], **changes)
    invalid = _replace_first_measure(happy_birthday_score, harmonies=(harmony,))

    assert expected_code in _issue_codes(invalid)
