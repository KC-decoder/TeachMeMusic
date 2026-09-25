"""Shared canonical-score fixtures built from approved ground truth."""

from fractions import Fraction

import pytest

from teachmemusic.score.models import (
    AttributeChange,
    Barline,
    BarlineLocation,
    BarlineStyle,
    BreakKind,
    Clef,
    ClefSign,
    Creator,
    HarmonySymbol,
    KeySignature,
    Lyric,
    Measure,
    NoteEvent,
    Part,
    PitchStep,
    PlaybackData,
    PresentationBreak,
    PresentationData,
    RestEvent,
    RhythmicValue,
    ScoreMetadata,
    ScoreRepresentation,
    SourceFormat,
    SourceReference,
    Staff,
    StemDirection,
    Syllabic,
    TimeSignature,
    Voice,
    WrittenPitch,
    WrittenPitchClass,
    WrittenRhythm,
)

_STAFF_ID = "staff-p1-1"
_VOICE_ID = "voice-p1-1"


def _lyrics(
    english: str,
    solfege: str,
    english_syllabic: Syllabic = Syllabic.SINGLE,
) -> tuple[Lyric, Lyric]:
    return (
        Lyric(line="1", text=english, syllabic=english_syllabic),
        Lyric(line="2", text=solfege, syllabic=Syllabic.SINGLE),
    )


def _note(
    measure: int,
    order: int,
    onset: int,
    duration: int,
    step: PitchStep,
    rhythm: RhythmicValue,
    english: str,
    solfege: str,
    stem: StemDirection,
    *,
    dots: int = 0,
    english_syllabic: Syllabic = Syllabic.SINGLE,
) -> NoteEvent:
    return NoteEvent(
        id=f"event-p1-m{measure}-{order + 1}",
        staff_id=_STAFF_ID,
        voice_id=_VOICE_ID,
        onset=Fraction(onset),
        duration=Fraction(duration),
        source_order=order,
        pitch=WrittenPitch(step=step, alter=Fraction(0), octave=4),
        rhythm=WrittenRhythm(value=rhythm, dots=dots),
        lyrics=_lyrics(english, solfege, english_syllabic),
        stem_direction=stem,
    )


def _rest(measure: int, order: int, onset: int) -> RestEvent:
    return RestEvent(
        id=f"event-p1-m{measure}-{order + 1}",
        staff_id=_STAFF_ID,
        voice_id=_VOICE_ID,
        onset=Fraction(onset),
        duration=Fraction(1),
        source_order=order,
        rhythm=WrittenRhythm(value=RhythmicValue.QUARTER),
    )


def _measure(number: int, events: tuple[NoteEvent | RestEvent, ...]) -> Measure:
    attributes = ()
    if number == 1:
        attributes = (
            AttributeChange(
                onset=Fraction(0),
                clefs=(Clef(staff_id=_STAFF_ID, sign=ClefSign.G, line=2),),
                key_signature=KeySignature(fifths=1, mode="major"),
                time_signature=TimeSignature(beat_groups=(4,), beat_type=4),
            ),
        )
    barlines = ()
    if number == 8:
        barlines = (
            Barline(
                location=BarlineLocation.RIGHT,
                style=BarlineStyle.LIGHT_HEAVY,
                terminates_score=True,
            ),
        )
    return Measure(
        id=f"measure-p1-{number}",
        source_label=str(number),
        ordinal=number,
        extent=Fraction(4),
        attribute_changes=attributes,
        events=events,
        barlines=barlines,
    )


def build_hot_cross_buns_score() -> ScoreRepresentation:
    """Build the DEV-003 reference score without reading MusicXML or PDF."""

    measures = (
        _measure(
            1,
            (
                _note(
                    1,
                    0,
                    0,
                    2,
                    PitchStep.B,
                    RhythmicValue.HALF,
                    "Hot",
                    "Mi",
                    StemDirection.DOWN,
                ),
                _note(
                    1,
                    1,
                    2,
                    2,
                    PitchStep.A,
                    RhythmicValue.HALF,
                    "cross",
                    "Re",
                    StemDirection.UP,
                ),
            ),
        ),
        _measure(
            2,
            (
                _note(
                    2,
                    0,
                    0,
                    3,
                    PitchStep.G,
                    RhythmicValue.HALF,
                    "buns,",
                    "Do",
                    StemDirection.UP,
                    dots=1,
                ),
                _rest(2, 1, 3),
            ),
        ),
        _measure(
            3,
            (
                _note(
                    3,
                    0,
                    0,
                    2,
                    PitchStep.B,
                    RhythmicValue.HALF,
                    "hot",
                    "Mi",
                    StemDirection.DOWN,
                ),
                _note(
                    3,
                    1,
                    2,
                    2,
                    PitchStep.A,
                    RhythmicValue.HALF,
                    "cross",
                    "Re",
                    StemDirection.UP,
                ),
            ),
        ),
        _measure(
            4,
            (
                _note(
                    4,
                    0,
                    0,
                    3,
                    PitchStep.G,
                    RhythmicValue.HALF,
                    "buns.",
                    "Do",
                    StemDirection.UP,
                    dots=1,
                ),
                _rest(4, 1, 3),
            ),
        ),
        _measure(
            5,
            (
                _note(
                    5,
                    0,
                    0,
                    1,
                    PitchStep.G,
                    RhythmicValue.QUARTER,
                    "One",
                    "Do",
                    StemDirection.UP,
                ),
                _note(
                    5,
                    1,
                    1,
                    1,
                    PitchStep.G,
                    RhythmicValue.QUARTER,
                    "a",
                    "Do",
                    StemDirection.UP,
                ),
                _note(
                    5,
                    2,
                    2,
                    1,
                    PitchStep.G,
                    RhythmicValue.QUARTER,
                    "pen-",
                    "Do",
                    StemDirection.UP,
                    english_syllabic=Syllabic.BEGIN,
                ),
                _note(
                    5,
                    3,
                    3,
                    1,
                    PitchStep.G,
                    RhythmicValue.QUARTER,
                    "ny",
                    "Do",
                    StemDirection.UP,
                    english_syllabic=Syllabic.END,
                ),
            ),
        ),
        _measure(
            6,
            (
                _note(
                    6,
                    0,
                    0,
                    1,
                    PitchStep.A,
                    RhythmicValue.QUARTER,
                    "two",
                    "Re",
                    StemDirection.UP,
                ),
                _note(
                    6,
                    1,
                    1,
                    1,
                    PitchStep.A,
                    RhythmicValue.QUARTER,
                    "a",
                    "Re",
                    StemDirection.UP,
                ),
                _note(
                    6,
                    2,
                    2,
                    1,
                    PitchStep.A,
                    RhythmicValue.QUARTER,
                    "pen-",
                    "Re",
                    StemDirection.UP,
                    english_syllabic=Syllabic.BEGIN,
                ),
                _note(
                    6,
                    3,
                    3,
                    1,
                    PitchStep.A,
                    RhythmicValue.QUARTER,
                    "ny",
                    "Re",
                    StemDirection.UP,
                    english_syllabic=Syllabic.END,
                ),
            ),
        ),
        _measure(
            7,
            (
                _note(
                    7,
                    0,
                    0,
                    2,
                    PitchStep.B,
                    RhythmicValue.HALF,
                    "hot",
                    "Mi",
                    StemDirection.DOWN,
                ),
                _note(
                    7,
                    1,
                    2,
                    2,
                    PitchStep.A,
                    RhythmicValue.HALF,
                    "cross",
                    "Re",
                    StemDirection.UP,
                ),
            ),
        ),
        _measure(
            8,
            (
                _note(
                    8,
                    0,
                    0,
                    3,
                    PitchStep.G,
                    RhythmicValue.HALF,
                    "buns.",
                    "Do",
                    StemDirection.UP,
                    dots=1,
                ),
                _rest(8, 1, 3),
            ),
        ),
    )
    return ScoreRepresentation(
        id="score-hot-cross-buns",
        metadata=ScoreMetadata(title="Hot Cross Buns"),
        parts=(
            Part(
                id="part-p1",
                source_id="P1",
                display_name="",
                staves=(Staff(id=_STAFF_ID, source_number=None),),
                voices=(Voice(id=_VOICE_ID, source_id="1"),),
                measures=measures,
            ),
        ),
        presentation=PresentationData(
            breaks=(PresentationBreak(kind=BreakKind.SYSTEM, before_measure_id="measure-p1-7"),)
        ),
        playback=PlaybackData(
            tempo_quarter_bpm=Fraction(96),
            instrument_sound="keyboard.piano.grand",
            midi_channel=1,
            midi_program=1,
        ),
        provenance=(
            SourceReference(
                source_format=SourceFormat.COMPRESSED_MUSICXML,
                logical_name="musicxml-17-hot-cross-buns-final-shelbygtdrew.mxl",
                sha256="2e48621ad69af56297fb015cd036e62f582b1f3dd8c48239f1f84c7e17d6471e",
            ),
            SourceReference(
                source_format=SourceFormat.PDF,
                logical_name="print-full.pdf",
                sha256="91e66bc30aab933707a64e108e8ea18d7f89ea8a7d455a1e81497e08d90d0594",
            ),
        ),
    )


@pytest.fixture
def hot_cross_buns_score() -> ScoreRepresentation:
    """Return a fresh immutable reference representation."""

    return build_hot_cross_buns_score()


_HAPPY_UPPER_STAFF_ID = "staff-happy-p1-1"
_HAPPY_LOWER_STAFF_ID = "staff-happy-p1-2"
_HAPPY_UPPER_VOICE_ID = "voice-happy-p1-1"
_HAPPY_LOWER_VOICE_ID = "voice-happy-p1-5"


def _happy_note(
    measure: int,
    order: int,
    staff_id: str,
    voice_id: str,
    onset: Fraction,
    duration: Fraction,
    step: PitchStep,
    octave: int,
    rhythm: RhythmicValue,
    stem: StemDirection,
    *,
    alter: int = 0,
    chord_id: str | None = None,
) -> NoteEvent:
    return NoteEvent(
        id=f"event-happy-p1-m{measure}-{order + 1}",
        staff_id=staff_id,
        voice_id=voice_id,
        onset=onset,
        duration=duration,
        source_order=order,
        pitch=WrittenPitch(step=step, alter=Fraction(alter), octave=octave),
        rhythm=WrittenRhythm(value=rhythm),
        chord_id=chord_id,
        stem_direction=stem,
    )


def _happy_rest(measure: int, order: int) -> RestEvent:
    return RestEvent(
        id=f"event-happy-p1-m{measure}-{order + 1}",
        staff_id=_HAPPY_LOWER_STAFF_ID,
        voice_id=_HAPPY_LOWER_VOICE_ID,
        onset=Fraction(0),
        duration=Fraction(1),
        source_order=order,
        rhythm=WrittenRhythm(value=RhythmicValue.QUARTER),
    )


def _happy_chord(
    measure: int,
    first_order: int,
    onset: int,
    duration: int,
    rhythm: RhythmicValue,
    pitches: tuple[tuple[PitchStep, int, int], ...],
) -> tuple[NoteEvent, ...]:
    chord_id = f"chord-happy-p1-m{measure}-{first_order + 1}"
    return tuple(
        _happy_note(
            measure,
            first_order + index,
            _HAPPY_LOWER_STAFF_ID,
            _HAPPY_LOWER_VOICE_ID,
            Fraction(onset),
            Fraction(duration),
            step,
            octave,
            rhythm,
            StemDirection.DOWN,
            alter=alter,
            chord_id=chord_id,
        )
        for index, (step, alter, octave) in enumerate(pitches)
    )


def _happy_harmony(
    measure: int,
    step: PitchStep,
    kind: str,
    display_text: str,
) -> HarmonySymbol:
    return HarmonySymbol(
        id=f"harmony-happy-p1-m{measure}-1",
        staff_id=_HAPPY_UPPER_STAFF_ID,
        onset=Fraction(1),
        source_order=0,
        root=WrittenPitchClass(step=step, alter=Fraction(0)),
        kind=kind,
        display_text=display_text,
    )


def _happy_measure(
    number: int,
    events: tuple[NoteEvent | RestEvent, ...],
    harmonies: tuple[HarmonySymbol, ...] = (),
) -> Measure:
    attributes = ()
    if number == 1:
        attributes = (
            AttributeChange(
                onset=Fraction(0),
                clefs=(
                    Clef(staff_id=_HAPPY_UPPER_STAFF_ID, sign=ClefSign.G, line=2),
                    Clef(staff_id=_HAPPY_LOWER_STAFF_ID, sign=ClefSign.F, line=4),
                ),
                key_signature=KeySignature(fifths=0, mode="major"),
                time_signature=TimeSignature(beat_groups=(3,), beat_type=4),
            ),
        )
    barlines = ()
    if number == 8:
        barlines = (
            Barline(
                location=BarlineLocation.RIGHT,
                style=BarlineStyle.LIGHT_HEAVY,
                terminates_score=True,
            ),
        )
    return Measure(
        id=f"measure-happy-p1-{number}",
        source_label=str(number),
        ordinal=number,
        extent=Fraction(3),
        attribute_changes=attributes,
        events=tuple(sorted(events, key=lambda event: (event.onset, event.source_order))),
        harmonies=harmonies,
        barlines=barlines,
    )


def build_happy_birthday_score() -> ScoreRepresentation:
    """Build Happy Birthday manually from its established fixture ground truth."""

    upper = _HAPPY_UPPER_STAFF_ID
    upper_voice = _HAPPY_UPPER_VOICE_ID
    eighth = Fraction(1, 2)
    quarter = Fraction(1)
    half = Fraction(2)
    measures = (
        _happy_measure(
            1,
            (
                _happy_note(
                    1,
                    0,
                    upper,
                    upper_voice,
                    Fraction(0),
                    eighth,
                    PitchStep.G,
                    4,
                    RhythmicValue.EIGHTH,
                    StemDirection.UP,
                ),
                _happy_note(
                    1,
                    1,
                    upper,
                    upper_voice,
                    eighth,
                    eighth,
                    PitchStep.G,
                    4,
                    RhythmicValue.EIGHTH,
                    StemDirection.UP,
                ),
                _happy_note(
                    1,
                    2,
                    upper,
                    upper_voice,
                    quarter,
                    quarter,
                    PitchStep.A,
                    4,
                    RhythmicValue.QUARTER,
                    StemDirection.UP,
                ),
                _happy_note(
                    1,
                    3,
                    upper,
                    upper_voice,
                    half,
                    quarter,
                    PitchStep.G,
                    4,
                    RhythmicValue.QUARTER,
                    StemDirection.UP,
                ),
                _happy_rest(1, 4),
                *_happy_chord(
                    1,
                    5,
                    1,
                    2,
                    RhythmicValue.HALF,
                    ((PitchStep.C, 0, 3), (PitchStep.E, 0, 3), (PitchStep.G, 0, 3)),
                ),
            ),
            (_happy_harmony(1, PitchStep.C, "major", ""),),
        ),
        _happy_measure(
            2,
            (
                _happy_note(
                    2,
                    0,
                    upper,
                    upper_voice,
                    Fraction(0),
                    quarter,
                    PitchStep.C,
                    5,
                    RhythmicValue.QUARTER,
                    StemDirection.DOWN,
                ),
                _happy_note(
                    2,
                    1,
                    upper,
                    upper_voice,
                    quarter,
                    half,
                    PitchStep.B,
                    4,
                    RhythmicValue.HALF,
                    StemDirection.DOWN,
                ),
                _happy_rest(2, 2),
                *_happy_chord(
                    2,
                    3,
                    1,
                    2,
                    RhythmicValue.HALF,
                    ((PitchStep.D, 0, 3), (PitchStep.F, 0, 3), (PitchStep.G, 0, 3)),
                ),
            ),
            (_happy_harmony(2, PitchStep.G, "dominant", "7"),),
        ),
        _happy_measure(
            3,
            (
                _happy_note(
                    3,
                    0,
                    upper,
                    upper_voice,
                    Fraction(0),
                    eighth,
                    PitchStep.G,
                    4,
                    RhythmicValue.EIGHTH,
                    StemDirection.UP,
                ),
                _happy_note(
                    3,
                    1,
                    upper,
                    upper_voice,
                    eighth,
                    eighth,
                    PitchStep.G,
                    4,
                    RhythmicValue.EIGHTH,
                    StemDirection.UP,
                ),
                _happy_note(
                    3,
                    2,
                    upper,
                    upper_voice,
                    quarter,
                    quarter,
                    PitchStep.A,
                    4,
                    RhythmicValue.QUARTER,
                    StemDirection.UP,
                ),
                _happy_note(
                    3,
                    3,
                    upper,
                    upper_voice,
                    half,
                    quarter,
                    PitchStep.G,
                    4,
                    RhythmicValue.QUARTER,
                    StemDirection.UP,
                ),
                _happy_rest(3, 4),
                *_happy_chord(
                    3,
                    5,
                    1,
                    2,
                    RhythmicValue.HALF,
                    ((PitchStep.B, 0, 2), (PitchStep.F, 0, 3), (PitchStep.G, 0, 3)),
                ),
            ),
        ),
        _happy_measure(
            4,
            (
                _happy_note(
                    4,
                    0,
                    upper,
                    upper_voice,
                    Fraction(0),
                    quarter,
                    PitchStep.D,
                    5,
                    RhythmicValue.QUARTER,
                    StemDirection.DOWN,
                ),
                _happy_note(
                    4,
                    1,
                    upper,
                    upper_voice,
                    quarter,
                    half,
                    PitchStep.C,
                    5,
                    RhythmicValue.HALF,
                    StemDirection.DOWN,
                ),
                _happy_rest(4, 2),
                *_happy_chord(
                    4,
                    3,
                    1,
                    2,
                    RhythmicValue.HALF,
                    ((PitchStep.C, 0, 3), (PitchStep.E, 0, 3), (PitchStep.G, 0, 3)),
                ),
            ),
            (_happy_harmony(4, PitchStep.C, "major", ""),),
        ),
        _happy_measure(
            5,
            (
                _happy_note(
                    5,
                    0,
                    upper,
                    upper_voice,
                    Fraction(0),
                    eighth,
                    PitchStep.G,
                    4,
                    RhythmicValue.EIGHTH,
                    StemDirection.UP,
                ),
                _happy_note(
                    5,
                    1,
                    upper,
                    upper_voice,
                    eighth,
                    eighth,
                    PitchStep.G,
                    4,
                    RhythmicValue.EIGHTH,
                    StemDirection.UP,
                ),
                _happy_note(
                    5,
                    2,
                    upper,
                    upper_voice,
                    quarter,
                    quarter,
                    PitchStep.G,
                    5,
                    RhythmicValue.QUARTER,
                    StemDirection.DOWN,
                ),
                _happy_note(
                    5,
                    3,
                    upper,
                    upper_voice,
                    half,
                    quarter,
                    PitchStep.E,
                    5,
                    RhythmicValue.QUARTER,
                    StemDirection.DOWN,
                ),
                _happy_rest(5, 4),
                *_happy_chord(
                    5,
                    5,
                    1,
                    2,
                    RhythmicValue.HALF,
                    ((PitchStep.E, 0, 3), (PitchStep.A, 1, 3), (PitchStep.C, 0, 4)),
                ),
            ),
        ),
        _happy_measure(
            6,
            (
                _happy_note(
                    6,
                    0,
                    upper,
                    upper_voice,
                    Fraction(0),
                    quarter,
                    PitchStep.C,
                    5,
                    RhythmicValue.QUARTER,
                    StemDirection.DOWN,
                ),
                _happy_note(
                    6,
                    1,
                    upper,
                    upper_voice,
                    quarter,
                    quarter,
                    PitchStep.B,
                    4,
                    RhythmicValue.QUARTER,
                    StemDirection.DOWN,
                ),
                _happy_note(
                    6,
                    2,
                    upper,
                    upper_voice,
                    half,
                    quarter,
                    PitchStep.A,
                    4,
                    RhythmicValue.QUARTER,
                    StemDirection.UP,
                ),
                _happy_rest(6, 3),
                *_happy_chord(
                    6,
                    4,
                    1,
                    2,
                    RhythmicValue.HALF,
                    ((PitchStep.F, 0, 3), (PitchStep.A, 0, 3), (PitchStep.C, 0, 4)),
                ),
            ),
        ),
        _happy_measure(
            7,
            (
                _happy_note(
                    7,
                    0,
                    upper,
                    upper_voice,
                    Fraction(0),
                    eighth,
                    PitchStep.F,
                    5,
                    RhythmicValue.EIGHTH,
                    StemDirection.DOWN,
                ),
                _happy_note(
                    7,
                    1,
                    upper,
                    upper_voice,
                    eighth,
                    eighth,
                    PitchStep.F,
                    5,
                    RhythmicValue.EIGHTH,
                    StemDirection.DOWN,
                ),
                _happy_note(
                    7,
                    2,
                    upper,
                    upper_voice,
                    quarter,
                    quarter,
                    PitchStep.E,
                    5,
                    RhythmicValue.QUARTER,
                    StemDirection.DOWN,
                ),
                _happy_note(
                    7,
                    3,
                    upper,
                    upper_voice,
                    half,
                    quarter,
                    PitchStep.C,
                    5,
                    RhythmicValue.QUARTER,
                    StemDirection.DOWN,
                ),
                _happy_rest(7, 4),
                *_happy_chord(
                    7,
                    5,
                    1,
                    2,
                    RhythmicValue.HALF,
                    ((PitchStep.E, 0, 3), (PitchStep.G, 0, 3), (PitchStep.C, 0, 4)),
                ),
            ),
        ),
        _happy_measure(
            8,
            (
                _happy_note(
                    8,
                    0,
                    upper,
                    upper_voice,
                    Fraction(0),
                    quarter,
                    PitchStep.D,
                    5,
                    RhythmicValue.QUARTER,
                    StemDirection.DOWN,
                ),
                _happy_note(
                    8,
                    1,
                    upper,
                    upper_voice,
                    quarter,
                    half,
                    PitchStep.C,
                    5,
                    RhythmicValue.HALF,
                    StemDirection.DOWN,
                ),
                *_happy_chord(
                    8,
                    2,
                    0,
                    1,
                    RhythmicValue.QUARTER,
                    ((PitchStep.D, 0, 3), (PitchStep.F, 0, 3), (PitchStep.G, 0, 3)),
                ),
                *_happy_chord(
                    8,
                    5,
                    1,
                    2,
                    RhythmicValue.HALF,
                    ((PitchStep.C, 0, 3), (PitchStep.E, 0, 3), (PitchStep.G, 0, 3)),
                ),
            ),
        ),
    )
    return ScoreRepresentation(
        id="score-happy-birthday",
        metadata=ScoreMetadata(
            title="Happy Birthday to You",
            creators=(Creator(role="credit", name="Patty Hill  Mildred J. Hill"),),
        ),
        parts=(
            Part(
                id="part-happy-p1",
                source_id="P1",
                display_name="Piano",
                staves=(
                    Staff(id=_HAPPY_UPPER_STAFF_ID, source_number=1),
                    Staff(id=_HAPPY_LOWER_STAFF_ID, source_number=2),
                ),
                voices=(
                    Voice(id=_HAPPY_UPPER_VOICE_ID, source_id="1"),
                    Voice(id=_HAPPY_LOWER_VOICE_ID, source_id="5"),
                ),
                measures=measures,
            ),
        ),
        presentation=PresentationData(
            breaks=(
                PresentationBreak(kind=BreakKind.SYSTEM, before_measure_id="measure-happy-p1-6"),
            )
        ),
        playback=PlaybackData(midi_channel=1, midi_program=1),
        provenance=(
            SourceReference(
                source_format=SourceFormat.COMPRESSED_MUSICXML,
                logical_name="happy-birthday-to-you-c-major.mxl",
                sha256="32cd97167d5c3dcef483c9d3e81a9e94b81e58f504416710c38524cd48b7eacf",
            ),
            SourceReference(
                source_format=SourceFormat.PDF,
                logical_name="happy-birthday-to-you-c-major.pdf",
                sha256="340cdaf4b4ce58a48b3b06d2ce5c829e42be963cddb5c2d300b3c0c9d499c892",
            ),
        ),
    )


@pytest.fixture
def happy_birthday_score() -> ScoreRepresentation:
    """Return a fresh manual representation of the second reference score."""

    return build_happy_birthday_score()
