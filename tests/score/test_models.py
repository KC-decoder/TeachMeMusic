"""Tests for the canonical score-domain contract."""

from collections import Counter
from dataclasses import FrozenInstanceError, fields
from fractions import Fraction

import pytest

import teachmemusic.score.models as score_models
from teachmemusic.score.models import (
    BarlineLocation,
    BarlineStyle,
    BreakKind,
    NoteEvent,
    PitchStep,
    RestEvent,
    RhythmicValue,
    ScoreRepresentation,
    StemDirection,
    Syllabic,
)
from teachmemusic.score.validation import validate_score, written_duration


def test_hot_cross_buns_matches_approved_ground_truth(
    hot_cross_buns_score: ScoreRepresentation,
) -> None:
    """TEST-SCORE-002 — verifies REQ-SCORE-002 through REQ-SCORE-004."""

    score = hot_cross_buns_score
    part = score.parts[0]
    events = tuple(score.iter_events())
    notes = tuple(event for event in events if isinstance(event, NoteEvent))
    rests = tuple(event for event in events if isinstance(event, RestEvent))

    assert score.metadata.title == "Hot Cross Buns"
    assert score.metadata.creators == ()
    assert len(score.parts) == 1
    assert part.display_name == ""
    assert len(part.staves) == 1
    assert part.staves[0].source_number is None
    assert len(part.voices) == 1
    assert part.voices[0].source_id == "1"
    assert [measure.source_label for measure in part.measures] == [str(i) for i in range(1, 9)]
    assert all(measure.extent == Fraction(4) for measure in part.measures)

    assert len(events) == 20
    assert len(notes) == 17
    assert len(rests) == 3
    assert sum((event.duration for event in events), start=Fraction(0)) == Fraction(32)
    assert Counter(note.pitch.step for note in notes) == {
        PitchStep.G: 7,
        PitchStep.A: 7,
        PitchStep.B: 3,
    }
    assert all(note.pitch.octave == 4 for note in notes)
    assert sum(len(note.lyrics) for note in notes) == 34
    assert all(len(note.lyrics) == 2 for note in notes)

    first_change = part.measures[0].attribute_changes[0]
    assert first_change.clefs[0].staff_id == part.staves[0].id
    assert first_change.clefs[0].sign.value == "G"
    assert first_change.clefs[0].line == 2
    assert first_change.key_signature is not None
    assert first_change.key_signature.fifths == 1
    assert first_change.key_signature.mode == "major"
    assert first_change.time_signature is not None
    assert first_change.time_signature.beat_groups == (4,)
    assert first_change.time_signature.beat_type == 4

    assert score.presentation.breaks[0].kind is BreakKind.SYSTEM
    assert score.presentation.breaks[0].before_measure_id == "measure-p1-7"
    final_barline = part.measures[-1].barlines[0]
    assert final_barline.location is BarlineLocation.RIGHT
    assert final_barline.style is BarlineStyle.LIGHT_HEAVY
    assert final_barline.terminates_score is True
    assert score.playback is not None
    assert score.playback.tempo_quarter_bpm == Fraction(96)
    assert score.playback.instrument_sound == "keyboard.piano.grand"


def test_hot_cross_buns_preserves_exact_event_sequence(
    hot_cross_buns_score: ScoreRepresentation,
) -> None:
    """TEST-SCORE-003 — verifies exact REQ-SCORE-003 event ordering and time."""

    actual = []
    for event in hot_cross_buns_score.iter_events():
        if isinstance(event, NoteEvent):
            actual.append((event.pitch.step.value, event.onset, event.duration))
        else:
            actual.append(("rest", event.onset, event.duration))

    assert actual == [
        ("B", Fraction(0), Fraction(2)),
        ("A", Fraction(2), Fraction(2)),
        ("G", Fraction(0), Fraction(3)),
        ("rest", Fraction(3), Fraction(1)),
        ("B", Fraction(0), Fraction(2)),
        ("A", Fraction(2), Fraction(2)),
        ("G", Fraction(0), Fraction(3)),
        ("rest", Fraction(3), Fraction(1)),
        ("G", Fraction(0), Fraction(1)),
        ("G", Fraction(1), Fraction(1)),
        ("G", Fraction(2), Fraction(1)),
        ("G", Fraction(3), Fraction(1)),
        ("A", Fraction(0), Fraction(1)),
        ("A", Fraction(1), Fraction(1)),
        ("A", Fraction(2), Fraction(1)),
        ("A", Fraction(3), Fraction(1)),
        ("B", Fraction(0), Fraction(2)),
        ("A", Fraction(2), Fraction(2)),
        ("G", Fraction(0), Fraction(3)),
        ("rest", Fraction(3), Fraction(1)),
    ]


def test_hot_cross_buns_preserves_lyrics_and_stems(
    hot_cross_buns_score: ScoreRepresentation,
) -> None:
    """TEST-SCORE-004 — verifies REQ-SCORE-004 note-level notation."""

    notes = tuple(
        event for event in hot_cross_buns_score.iter_events() if isinstance(event, NoteEvent)
    )
    english = [note.lyrics[0].text for note in notes]
    solfege = [note.lyrics[1].text for note in notes]

    assert english == [
        "Hot",
        "cross",
        "buns,",
        "hot",
        "cross",
        "buns.",
        "One",
        "a",
        "pen-",
        "ny",
        "two",
        "a",
        "pen-",
        "ny",
        "hot",
        "cross",
        "buns.",
    ]
    assert solfege == [
        "Mi",
        "Re",
        "Do",
        "Mi",
        "Re",
        "Do",
        "Do",
        "Do",
        "Do",
        "Do",
        "Re",
        "Re",
        "Re",
        "Re",
        "Mi",
        "Re",
        "Do",
    ]
    assert [note.lyrics[0].syllabic for note in notes[8:10]] == [
        Syllabic.BEGIN,
        Syllabic.END,
    ]
    assert [note.lyrics[0].syllabic for note in notes[12:14]] == [
        Syllabic.BEGIN,
        Syllabic.END,
    ]
    assert Counter(note.stem_direction for note in notes) == {
        StemDirection.UP: 14,
        StemDirection.DOWN: 3,
    }


def test_models_are_immutable_and_support_stable_lookup(
    hot_cross_buns_score: ScoreRepresentation,
) -> None:
    """TEST-SCORE-005 — verifies REQ-SCORE-001 and REQ-SCORE-002."""

    with pytest.raises(FrozenInstanceError):
        hot_cross_buns_score.id = "changed"  # type: ignore[misc]

    assert isinstance(hot_cross_buns_score.parts, tuple)
    assert isinstance(hot_cross_buns_score.parts[0].measures, tuple)
    assert hot_cross_buns_score.find_measure("measure-p1-7") is not None
    event = hot_cross_buns_score.find_event("event-p1-m5-3")
    assert isinstance(event, NoteEvent)
    assert event.pitch.step is PitchStep.G
    assert hot_cross_buns_score.find_event("missing") is None


def test_written_rhythm_uses_exact_arithmetic() -> None:
    """TEST-SCORE-006 — verifies REQ-SCORE-003 rational rhythm arithmetic."""

    from teachmemusic.score.models import WrittenRhythm

    assert written_duration(WrittenRhythm(RhythmicValue.QUARTER)) == Fraction(1)
    assert written_duration(WrittenRhythm(RhythmicValue.HALF, dots=1)) == Fraction(3)
    assert written_duration(WrittenRhythm(RhythmicValue.EIGHTH, dots=2)) == Fraction(7, 8)


def test_reference_score_is_valid(hot_cross_buns_score: ScoreRepresentation) -> None:
    """TEST-SCORE-007 — verifies the positive REQ-SCORE-005 validation path."""

    assert validate_score(hot_cross_buns_score) == ()


def test_attributes_carry_forward_without_duplication(
    hot_cross_buns_score: ScoreRepresentation,
) -> None:
    """TEST-SCORE-008 — verifies REQ-SCORE-004 attribute carry-forward."""

    part = hot_cross_buns_score.parts[0]
    resolved = part.measure_attributes()

    assert len(part.measures[0].attribute_changes) == 1
    assert all(not measure.attribute_changes for measure in part.measures[1:])
    assert len(resolved) == 8
    assert all(attributes.clefs[0].sign.value == "G" for attributes in resolved)
    assert all(attributes.key_signature is not None for attributes in resolved)
    assert all(
        attributes.key_signature.fifths == 1 for attributes in resolved if attributes.key_signature
    )
    assert all(attributes.time_signature is not None for attributes in resolved)
    assert all(
        attributes.time_signature.beat_groups == (4,)
        for attributes in resolved
        if attributes.time_signature
    )


def test_model_module_has_only_owned_or_standard_library_types() -> None:
    """TEST-SCORE-001 — verifies the REQ-SCORE-001 ownership boundary."""

    exported_modules = {
        value.__module__.split(".")[0]
        for name, value in vars(score_models).items()
        if not name.startswith("_") and hasattr(value, "__module__")
    }
    field_names = {
        field.name
        for model_type in (
            score_models.ScoreRepresentation,
            score_models.Part,
            score_models.Measure,
            score_models.NoteEvent,
            score_models.RestEvent,
        )
        for field in fields(model_type)
    }

    assert exported_modules <= {
        "builtins",
        "collections",
        "dataclasses",
        "enum",
        "fractions",
        "teachmemusic",
        "typing",
    }
    assert field_names.isdisjoint({"learner", "lesson", "grading", "progression"})


def test_happy_birthday_matches_established_ground_truth(
    happy_birthday_score: ScoreRepresentation,
) -> None:
    """TEST-SCORE-023 — verifies the expanded REQ-SCORE-002 through 004 proof."""

    score = happy_birthday_score
    part = score.parts[0]
    events = tuple(score.iter_events())
    notes = tuple(event for event in events if isinstance(event, NoteEvent))
    rests = tuple(event for event in events if isinstance(event, RestEvent))
    pitch_counts = Counter((note.pitch.step, note.pitch.alter, note.pitch.octave) for note in notes)

    assert score.metadata.title == "Happy Birthday to You"
    assert [(creator.role, creator.name) for creator in score.metadata.creators] == [
        ("credit", "Patty Hill  Mildred J. Hill")
    ]
    assert part.display_name == "Piano"
    assert [staff.source_number for staff in part.staves] == [1, 2]
    assert [voice.source_id for voice in part.voices] == ["1", "5"]
    assert len(part.measures) == 8
    assert all(measure.extent == Fraction(3) for measure in part.measures)
    assert [len(measure.events) for measure in part.measures] == [8, 6, 8, 6, 8, 7, 8, 8]
    assert len(events) == 59
    assert len(notes) == 52
    assert len(rests) == 7
    assert pitch_counts == {
        (PitchStep.A, Fraction(0), 3): 1,
        (PitchStep.A, Fraction(0), 4): 3,
        (PitchStep.A, Fraction(1), 3): 1,
        (PitchStep.B, Fraction(0), 2): 1,
        (PitchStep.B, Fraction(0), 4): 2,
        (PitchStep.C, Fraction(0), 3): 3,
        (PitchStep.C, Fraction(0), 4): 3,
        (PitchStep.C, Fraction(0), 5): 5,
        (PitchStep.D, Fraction(0), 3): 2,
        (PitchStep.D, Fraction(0), 5): 2,
        (PitchStep.E, Fraction(0), 3): 5,
        (PitchStep.E, Fraction(0), 5): 2,
        (PitchStep.F, Fraction(0), 3): 4,
        (PitchStep.F, Fraction(0), 5): 2,
        (PitchStep.G, Fraction(0), 3): 7,
        (PitchStep.G, Fraction(0), 4): 8,
        (PitchStep.G, Fraction(0), 5): 1,
    }

    first_change = part.measures[0].attribute_changes[0]
    assert [(clef.sign.value, clef.line) for clef in first_change.clefs] == [
        ("G", 2),
        ("F", 4),
    ]
    assert first_change.key_signature is not None
    assert (first_change.key_signature.fifths, first_change.key_signature.mode) == (0, "major")
    assert first_change.time_signature is not None
    assert first_change.time_signature.beat_groups == (3,)
    assert first_change.time_signature.beat_type == 4
    assert score.presentation.breaks[0].before_measure_id == "measure-happy-p1-6"
    assert part.measures[-1].barlines[0].terminates_score is True
    assert sum(len(measure.harmonies) for measure in part.measures) == 3
    assert [
        (measure.ordinal, harmony.onset, harmony.root.step, harmony.kind, harmony.display_text)
        for measure in part.measures
        for harmony in measure.harmonies
    ] == [
        (1, Fraction(1), PitchStep.C, "major", ""),
        (2, Fraction(1), PitchStep.G, "dominant", "7"),
        (4, Fraction(1), PitchStep.C, "major", ""),
    ]


def test_happy_birthday_chords_preserve_written_membership(
    happy_birthday_score: ScoreRepresentation,
) -> None:
    """TEST-SCORE-024 — verifies explicit REQ-SCORE-003 chord relations."""

    groups: dict[str, list[NoteEvent]] = {}
    for event in happy_birthday_score.iter_events():
        if isinstance(event, NoteEvent) and event.chord_id is not None:
            groups.setdefault(event.chord_id, []).append(event)

    assert len(groups) == 9
    assert all(len(members) == 3 for members in groups.values())
    assert sum(len(members) - 1 for members in groups.values()) == 18
    assert all(
        len(
            {
                (member.onset, member.duration, member.staff_id, member.voice_id, member.rhythm)
                for member in members
            }
        )
        == 1
        for members in groups.values()
    )
    assert validate_score(happy_birthday_score) == ()
