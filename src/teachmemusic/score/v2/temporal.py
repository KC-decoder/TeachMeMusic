"""Typed, exact-time temporal projection of a validated MusicXML score.

This is deliberately a partial score view. Deferred source constructs are
reported, not silently represented as canonical musical information.
"""

from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction

from .annotations import (
    AnnotationGraph,
    DirectionMark,
    EventMarkMarker,
    FiguredBassAnnotation,
    HarmonySymbol,
    LyricMarker,
    NoteheadMarker,
    SpanMarker,
    TimeSpanMarker,
)
from .layout import MeasurePrintLayout, ScoreLayout
from .links import Bookmark, ExternalLink, PartLink, ScopedBookmark, ScopedLink
from .playback import InstrumentPlayback, Player, SoundDirective
from .presentation import NameDisplay, PresentationStyle, SourcePresentation


@dataclass(frozen=True, slots=True)
class TemporalPitch:
    """A written pitched or unpitched display position."""

    step: str
    alter: Fraction
    octave: int


@dataclass(frozen=True, slots=True)
class TemporalInstrument:
    id: str
    name: str | None
    abbreviation: str | None
    sound: str | None = None
    solo: bool = False
    ensemble: bool = False
    ensemble_size: int | None = None
    playback: InstrumentPlayback = InstrumentPlayback()


@dataclass(frozen=True, slots=True)
class TemporalStaff:
    id: str
    source_number: str


@dataclass(frozen=True, slots=True)
class TemporalVoice:
    id: str
    source_id: str


@dataclass(frozen=True, slots=True)
class TemporalTypedText:
    value: str
    text_type: str | None


@dataclass(frozen=True, slots=True)
class TemporalEncodingSupport:
    supported: bool
    element: str
    attribute: str | None
    value: str | None


@dataclass(frozen=True, slots=True)
class TemporalEncoding:
    dates: tuple[str, ...]
    encoders: tuple[TemporalTypedText, ...]
    software: tuple[str, ...]
    descriptions: tuple[str, ...]
    supports: tuple[TemporalEncodingSupport, ...]


@dataclass(frozen=True, slots=True)
class TemporalMiscellaneousField:
    name: str
    value: str


@dataclass(frozen=True, slots=True)
class TemporalScoreMetadata:
    concert_score: bool = False
    work_number: str | None = None
    creators: tuple[TemporalTypedText, ...] = ()
    rights: tuple[TemporalTypedText, ...] = ()
    source: str | None = None
    relations: tuple[TemporalTypedText, ...] = ()
    encoding: TemporalEncoding | None = None
    miscellaneous: tuple[TemporalMiscellaneousField, ...] = ()
    schema_location: str | None = None


@dataclass(frozen=True, slots=True)
class TemporalEditorial:
    footnote: str | None
    footnote_language: str | None
    level: str | None
    level_reference: bool | None
    level_type: str | None
    level_parentheses: bool | None
    level_bracket: bool | None
    level_size: str | None


@dataclass(frozen=True, slots=True)
class TemporalPartGroup:
    number: str
    action: str
    name: str | None
    abbreviation: str | None
    symbol: str | None
    barline: str | None
    source_order: int
    group_time: bool = False
    source_id: str | None = None
    editorial: TemporalEditorial | None = None
    name_display: NameDisplay | None = None
    abbreviation_display: NameDisplay | None = None


@dataclass(frozen=True, slots=True)
class TemporalClef:
    staff: str
    sign: str
    line: int | None
    octave_change: int | None
    additional: bool | None = None
    size: str | None = None
    after_barline: bool | None = None
    print_object: bool | None = None
    source_id: str | None = None


@dataclass(frozen=True, slots=True)
class TemporalKeyAlteration:
    step: str
    alter: Fraction
    accidental: str | None
    accidental_smufl: str | None
    accidentals: tuple[TemporalKeyAccidental, ...] = ()


@dataclass(frozen=True, slots=True)
class TemporalKeyAccidental:
    value: str
    smufl: str | None = None


@dataclass(frozen=True, slots=True)
class TemporalKeyOctave:
    number: int
    octave: int
    cancel: bool | None


@dataclass(frozen=True, slots=True)
class TemporalKey:
    fifths: int | None
    mode: str | None
    staff: str | None
    cancel: int | None = None
    cancel_location: str | None = None
    alterations: tuple[TemporalKeyAlteration, ...] = ()
    octaves: tuple[TemporalKeyOctave, ...] = ()
    print_object: bool | None = None
    source_id: str | None = None


@dataclass(frozen=True, slots=True)
class TemporalInterchangeableTime:
    beats: tuple[str, ...]
    beat_types: tuple[int, ...]
    relation: str | None
    symbol: str | None
    separator: str | None


@dataclass(frozen=True, slots=True)
class TemporalTime:
    beats: tuple[str, ...]
    beat_types: tuple[int, ...]
    symbol: str | None
    staff: str | None
    senza_misura: str | None = None
    separator: str | None = None
    interchangeable: TemporalInterchangeableTime | None = None
    print_object: bool | None = None
    source_id: str | None = None


@dataclass(frozen=True, slots=True)
class TemporalStaffTuning:
    line: int
    step: str
    alter: Fraction
    octave: int


@dataclass(frozen=True, slots=True)
class TemporalStaffDetails:
    staff: str | None
    staff_type: str | None
    lines: int | None
    tunings: tuple[TemporalStaffTuning, ...]
    capo: int | None
    size: Fraction | None
    scaling: Fraction | None
    show_frets: str | None
    print_object: bool | None
    line_details: tuple[TemporalStaffLineDetail, ...] = ()


@dataclass(frozen=True, slots=True)
class TemporalStaffLineDetail:
    line: int
    print_object: bool | None = None
    presentation: PresentationStyle | None = None


@dataclass(frozen=True, slots=True)
class TemporalPartSymbol:
    value: str
    top_staff: str | None
    bottom_staff: str | None
    presentation: PresentationStyle | None = None


@dataclass(frozen=True, slots=True)
class TemporalPartClef:
    sign: str
    line: int | None
    octave_change: int | None


@dataclass(frozen=True, slots=True)
class TemporalForPart:
    staff: str | None
    clef: TemporalPartClef | None
    transposition: TemporalTransposition
    source_id: str | None


@dataclass(frozen=True, slots=True)
class TemporalDirective:
    value: str
    language: str | None
    source_order: int


@dataclass(frozen=True, slots=True)
class TemporalMeasureStyle:
    """Semantic repeat/slash notation declared inside an attributes change."""

    staff: str | None
    kind: str
    value: int | None
    action: str | None
    slashes: int | None
    use_symbols: bool | None
    use_dots: bool | None
    use_stems: bool | None
    slash_type: str | None
    slash_dots: int
    source_id: str | None = None


@dataclass(frozen=True, slots=True)
class TemporalTransposition:
    """MusicXML written-to-sounding interval, scoped to a staff or whole part."""

    staff: str | None
    diatonic: int | None
    chromatic: Fraction
    octave_change: int
    doubling_above: bool | None


@dataclass(frozen=True, slots=True)
class TemporalSoundingPitch:
    """Resolved sounding semitone and spelling when the source determines it."""

    semitone: Fraction
    step: str | None
    alter: Fraction | None
    octave: int | None


@dataclass(frozen=True, slots=True)
class TemporalGraceTiming:
    slash: bool | None
    make_time: Fraction | None
    steal_previous_percent: Fraction | None
    steal_following_percent: Fraction | None


@dataclass(frozen=True, slots=True)
class TemporalAttributes:
    onset: Fraction
    divisions: int | None
    staves: int | None
    clefs: tuple[TemporalClef, ...]
    keys: tuple[TemporalKey, ...]
    times: tuple[TemporalTime, ...]
    source_order: int
    transpositions: tuple[TemporalTransposition, ...] = ()
    instrument_count: int | None = None
    measure_styles: tuple[TemporalMeasureStyle, ...] = ()
    staff_details: tuple[TemporalStaffDetails, ...] = ()
    part_symbol: TemporalPartSymbol | None = None
    for_parts: tuple[TemporalForPart, ...] = ()
    directives: tuple[TemporalDirective, ...] = ()
    part_symbols: tuple[TemporalPartSymbol, ...] = ()


@dataclass(frozen=True, slots=True)
class TemporalBeam:
    number: int
    value: str
    repeater: bool | None = None
    fan: str | None = None
    source_id: str | None = None


@dataclass(frozen=True, slots=True)
class TemporalTupletPortion:
    number: int | None
    note_type: str | None
    dots: int


@dataclass(frozen=True, slots=True)
class TemporalTuplet:
    number: str
    action: str
    bracket: bool | None
    placement: str | None
    show_number: str | None = None
    show_type: str | None = None
    line_shape: str | None = None
    actual: TemporalTupletPortion | None = None
    normal: TemporalTupletPortion | None = None
    source_id: str | None = None


@dataclass(frozen=True, slots=True)
class TemporalAccidental:
    value: str
    cautionary: bool | None
    editorial: bool | None
    parentheses: bool | None
    bracket: bool | None
    size: str | None
    smufl: str | None
    presentation: PresentationStyle | None = None


@dataclass(frozen=True, slots=True)
class TemporalEvent:
    """One source note element, including chord followers and rests."""

    id: str
    kind: str
    onset: Fraction
    duration: Fraction
    source_duration: int | None
    staff: str
    voice: str
    pitch: TemporalPitch | None
    chord_id: str | None
    written_type: str | None
    dots: int
    time_modification: tuple[int, int] | None
    beams: tuple[TemporalBeam, ...]
    tuplets: tuple[TemporalTuplet, ...]
    grace: bool
    cue: bool
    source_order: int
    score_onset: Fraction = Fraction(0)
    written_duration: Fraction | None = None
    performed_duration: Fraction | None = None
    sounding_pitches: tuple[TemporalSoundingPitch, ...] = ()
    grace_timing: TemporalGraceTiming | None = None
    instrument_id: str | None = None
    instrument_ids: tuple[str, ...] = ()
    semantic_order: int = 0
    normal_type: str | None = None
    normal_dots: int = 0
    display_position: TemporalPitch | None = None
    span_markers: tuple[SpanMarker, ...] = ()
    lyric_markers: tuple[LyricMarker, ...] = ()
    notehead_marker: NoteheadMarker | None = None
    event_markers: tuple[EventMarkMarker, ...] = ()
    accidental: TemporalAccidental | None = None
    stem: str | None = None
    written_size: str | None = None
    source_id: str | None = None
    editorial: TemporalEditorial | None = None
    presentation: PresentationStyle | None = None
    measure_rest: bool | None = None
    print_object: bool | None = None
    print_leger: bool | None = None
    print_dot: bool | None = None
    print_lyric: bool | None = None
    dynamics: Fraction | None = None
    accidentals: tuple[TemporalAccidental, ...] = ()


@dataclass(frozen=True, slots=True)
class TemporalCursorMove:
    kind: str
    before: Fraction
    after: Fraction
    source_duration: int
    staff: str | None
    voice: str | None
    source_order: int
    editorial: TemporalEditorial | None = None
    underflow_recovered: bool = False


@dataclass(frozen=True, slots=True)
class TemporalFeature:
    value: str
    feature_type: str | None


@dataclass(frozen=True, slots=True)
class TemporalGrouping:
    onset: Fraction
    score_onset: Fraction
    grouping_type: str
    number: str
    member_of: str | None
    features: tuple[TemporalFeature, ...]
    source_order: int
    source_id: str | None = None


@dataclass(frozen=True, slots=True)
class TemporalFermata:
    """A fermata attached to a barline rather than a note event."""

    shape: str | None
    orientation: str | None
    source_id: str | None = None


@dataclass(frozen=True, slots=True)
class TemporalNavigationMark:
    """A segno or coda token attached directly to a barline."""

    kind: str
    token: str | None
    source_id: str | None
    smufl: str | None


@dataclass(frozen=True, slots=True)
class TemporalBarline:
    onset: Fraction
    location: str | None
    style: str | None
    repeat_direction: str | None
    repeat_times: str | None
    ending_number: str | None
    ending_type: str | None
    source_order: int
    fermatas: tuple[TemporalFermata, ...] = ()
    navigation: tuple[TemporalNavigationMark, ...] = ()
    repeat_winged: str | None = None
    repeat_after_jump: bool | None = None
    ending_text: str | None = None
    ending_print_object: bool | None = None
    ending_system_relation: str | None = None
    divisions: Fraction | None = None
    source_id: str | None = None


@dataclass(frozen=True, slots=True)
class TemporalMeasure:
    number: str
    ordinal: int
    implicit: bool
    extent: Fraction
    staves: tuple[str, ...]
    voices: tuple[str, ...]
    attributes: tuple[TemporalAttributes, ...]
    events: tuple[TemporalEvent, ...]
    cursor_moves: tuple[TemporalCursorMove, ...]
    barlines: tuple[TemporalBarline, ...]
    score_onset: Fraction = Fraction(0)
    non_controlling: bool = False
    id: str = ""
    harmonies: tuple[HarmonySymbol, ...] = ()
    directions: tuple[DirectionMark, ...] = ()
    figured_bass: tuple[FiguredBassAnnotation, ...] = ()
    time_span_markers: tuple[TimeSpanMarker, ...] = ()
    groupings: tuple[TemporalGrouping, ...] = ()
    layout: MeasurePrintLayout | None = None
    sounds: tuple[SoundDirective, ...] = ()
    links: tuple[ExternalLink, ...] = ()
    bookmarks: tuple[Bookmark, ...] = ()


@dataclass(frozen=True, slots=True)
class TemporalPart:
    id: str
    name: str | None
    abbreviation: str | None
    instruments: tuple[TemporalInstrument, ...]
    measures: tuple[TemporalMeasure, ...]
    staves: tuple[TemporalStaff, ...] = ()
    voices: tuple[TemporalVoice, ...] = ()
    groups: tuple[str, ...] = ()
    metadata: TemporalScoreMetadata = TemporalScoreMetadata()
    players: tuple[Player, ...] = ()
    part_links: tuple[PartLink, ...] = ()
    name_print_object: bool | None = None
    abbreviation_print_object: bool | None = None
    name_display: NameDisplay | None = None
    abbreviation_display: NameDisplay | None = None


@dataclass(frozen=True, slots=True)
class TemporalAlignment:
    """Controlling measure starts shared at an exact score-relative time."""

    onset: Fraction
    measures: tuple[tuple[str, int], ...]


@dataclass(frozen=True, slots=True)
class TemporalScore:
    work_title: str | None
    movement_title: str | None
    movement_number: str | None
    creators: tuple[tuple[str | None, str], ...]
    groups: tuple[TemporalPartGroup, ...]
    parts: tuple[TemporalPart, ...]
    alignments: tuple[TemporalAlignment, ...] = ()
    annotations: AnnotationGraph = AnnotationGraph()
    metadata: TemporalScoreMetadata = TemporalScoreMetadata()
    layout: ScoreLayout | None = None
    links: tuple[ScopedLink, ...] = ()
    bookmarks: tuple[ScopedBookmark, ...] = ()
    work_opus: ExternalLink | None = None
    source_presentations: tuple[SourcePresentation, ...] = ()


@dataclass(frozen=True, slots=True)
class DeferredConstruct:
    """Source construct not yet represented in this temporal-only view."""

    path: str
    tag: str
    occurrences: int


@dataclass(frozen=True, slots=True)
class TemporalReadResult:
    """Public partial read; never a lossless canonical-ingestion claim."""

    source_sha256: str
    source_format: str
    musicxml_version: str
    document_form: str
    score: TemporalScore
    deferred: tuple[DeferredConstruct, ...]
    completeness: str = "temporal-only"


def resolve_sounding_pitches(
    pitch: TemporalPitch, transposition: TemporalTransposition | None
) -> tuple[TemporalSoundingPitch, ...]:
    """Resolve written pitch and an optional MusicXML sounding transposition."""

    steps = ("C", "D", "E", "F", "G", "A", "B")
    semitones = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}
    written = Fraction(12 * (pitch.octave + 1) + semitones[pitch.step]) + pitch.alter
    if transposition is None:
        return (TemporalSoundingPitch(written, pitch.step, pitch.alter, pitch.octave),)
    sounding = written + transposition.chromatic + 12 * transposition.octave_change
    if transposition.diatonic is not None:
        octave_delta, step_index = divmod(
            steps.index(pitch.step) + transposition.diatonic, len(steps)
        )
        step = steps[step_index]
        octave = pitch.octave + octave_delta + transposition.octave_change
        alter = sounding - (12 * (octave + 1) + semitones[step])
    elif transposition.chromatic == 0:
        step, alter, octave = (
            pitch.step,
            pitch.alter,
            pitch.octave + transposition.octave_change,
        )
    else:
        step, alter, octave = None, None, None
    primary = TemporalSoundingPitch(sounding, step, alter, octave)
    if transposition.doubling_above is None:
        return (primary,)
    direction = 1 if transposition.doubling_above else -1
    doubled = TemporalSoundingPitch(
        sounding + 12 * direction,
        step,
        alter,
        octave + direction if octave is not None else None,
    )
    return (primary, doubled)
