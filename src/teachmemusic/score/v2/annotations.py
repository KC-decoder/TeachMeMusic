"""Typed event-anchored notation spans, separate from temporal score facts."""

from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction

from .presentation import PresentationStyle

SIMPLE_EVENT_MARKS = {
    "articulation": frozenset(
        {
            "accent",
            "strong-accent",
            "staccato",
            "tenuto",
            "detached-legato",
            "staccatissimo",
            "spiccato",
            "scoop",
            "plop",
            "doit",
            "falloff",
            "breath-mark",
            "caesura",
            "stress",
            "unstress",
            "soft-accent",
            "other-articulation",
        }
    ),
    "ornament": frozenset(
        {
            "accidental-mark",
            "trill-mark",
            "turn",
            "delayed-turn",
            "inverted-turn",
            "delayed-inverted-turn",
            "vertical-turn",
            "inverted-vertical-turn",
            "shake",
            "mordent",
            "inverted-mordent",
            "schleifer",
            "haydn",
            "other-ornament",
            "tremolo",
        }
    ),
    "technical": frozenset(
        {
            "up-bow",
            "down-bow",
            "harmonic",
            "open-string",
            "thumb-position",
            "fingering",
            "pluck",
            "double-tongue",
            "triple-tongue",
            "stopped",
            "snap-pizzicato",
            "string",
            "fret",
            "bend",
            "tap",
            "heel",
            "toe",
            "fingernails",
            "hole",
            "arrow",
            "handbell",
            "brass-bend",
            "flip",
            "smear",
            "open",
            "half-muted",
            "harmon-mute",
            "golpe",
            "other-technical",
        }
    ),
    "dynamic": frozenset(
        {
            "p",
            "pp",
            "ppp",
            "pppp",
            "ppppp",
            "pppppp",
            "f",
            "ff",
            "fff",
            "ffff",
            "fffff",
            "ffffff",
            "mp",
            "mf",
            "sf",
            "sfp",
            "sfpp",
            "fp",
            "rf",
            "rfz",
            "sfz",
            "sffz",
            "fz",
            "n",
            "pf",
            "sfzp",
            "other-dynamics",
        }
    ),
    "notation": frozenset({"fermata", "arpeggiate", "non-arpeggiate", "other-notation"}),
}


@dataclass(frozen=True, slots=True)
class TrillPlayback:
    """Explicit MusicXML trill-sound attributes, without materialising defaults."""

    start_note: str | None = None
    trill_step: str | None = None
    two_note_turn: str | None = None
    accelerate: bool | None = None
    beats: Fraction | None = None
    second_beat: Fraction | None = None
    last_beat: Fraction | None = None


@dataclass(frozen=True, slots=True)
class OrnamentAccidental:
    """An accidental scoped to the preceding ornament in source order."""

    value: str
    placement: str | None = None
    bracket: bool | None = None
    parentheses: bool | None = None
    smufl: str | None = None


@dataclass(frozen=True, slots=True)
class TechnicalHarmonic:
    """Natural/artificial and written/sounding role of a harmonic mark."""

    harmonic_type: str | None = None
    pitch_type: str | None = None
    print_object: bool | None = None
    number: str | None = None


@dataclass(frozen=True, slots=True)
class TechnicalBend:
    """Exact guitar-bend semantics, including optional playback shaping."""

    alter: Fraction
    action: str | None = None
    release_offset: Fraction | None = None
    with_bar: str | None = None
    with_bar_placement: str | None = None
    shape: str | None = None
    accelerate: bool | None = None
    beats: Fraction | None = None
    first_beat: Fraction | None = None
    last_beat: Fraction | None = None


@dataclass(frozen=True, slots=True)
class TechnicalHole:
    """Woodwind/brass fingering-hole state and its descriptive symbol."""

    hole_type: str | None
    closed: str
    closed_location: str | None
    shape: str | None


@dataclass(frozen=True, slots=True)
class TechnicalArrow:
    """Straight or circular technical arrow without collapsing its notation."""

    direction: str | None = None
    style: str | None = None
    arrowhead_only: bool = False
    circular: str | None = None


@dataclass(frozen=True, slots=True)
class TechnicalHarmonMute:
    """Harmon-mute closure state and optional half-closed location."""

    closed: str
    closed_location: str | None = None


@dataclass(frozen=True, slots=True)
class TechnicalData:
    """Typed payload for technical marks whose meaning exceeds text/placement."""

    harmonic: TechnicalHarmonic | None = None
    bend: TechnicalBend | None = None
    hole: TechnicalHole | None = None
    arrow: TechnicalArrow | None = None
    harmon_mute: TechnicalHarmonMute | None = None
    substitution: bool | None = None
    alternate: bool | None = None
    hand: str | None = None


@dataclass(frozen=True, slots=True)
class BendSound:
    """Explicit MusicXML bend-sound playback values used by slide endpoints."""

    accelerate: bool | None = None
    beats: Fraction | None = None
    first_beat: Fraction | None = None
    last_beat: Fraction | None = None


@dataclass(frozen=True, slots=True)
class SpanMarker:
    """One MusicXML span endpoint as expressed on a note element."""

    kind: str  # tie/slur, ornament span, or fretted-technique span
    number: str
    action: str  # start, continue, or stop
    source_order: int
    placement: str | None = None
    smufl: str | None = None
    playback: TrillPlayback | None = None
    tremolo_marks: int | None = None
    accidentals: tuple[OrnamentAccidental, ...] = ()
    text: str | None = None
    source_id: str | None = None
    line_type: str | None = None
    bend_sound: BendSound | None = None
    print_object: bool | None = None
    orientation: str | None = None
    dash_length: Fraction | None = None
    space_length: Fraction | None = None
    time_only: str | None = None


@dataclass(frozen=True, slots=True)
class EventAnchor:
    """Stable reference to one written event, including its score position."""

    part_id: str
    measure_id: str
    event_id: str
    staff: str
    voice: str
    score_onset: Fraction


@dataclass(frozen=True, slots=True)
class SpanEndpoint:
    action: str
    anchor: EventAnchor
    source_order: int
    placement: str | None = None
    smufl: str | None = None
    playback: TrillPlayback | None = None
    tremolo_marks: int | None = None
    accidentals: tuple[OrnamentAccidental, ...] = ()
    text: str | None = None
    source_id: str | None = None
    line_type: str | None = None
    bend_sound: BendSound | None = None
    print_object: bool | None = None
    orientation: str | None = None
    dash_length: Fraction | None = None
    space_length: Fraction | None = None
    time_only: str | None = None


@dataclass(frozen=True, slots=True)
class NotationSpan:
    id: str
    kind: str
    number: str
    endpoints: tuple[SpanEndpoint, ...]


@dataclass(frozen=True, slots=True)
class LyricTextSegment:
    text: str
    syllabic: str | None = None
    elision_before: str | None = None
    elision_smufl: str | None = None


@dataclass(frozen=True, slots=True)
class LyricMarker:
    number: str | None
    name: str | None
    syllabic: str | None
    text: str
    source_order: int
    segments: tuple[LyricTextSegment, ...] = ()
    extend_present: bool = False
    extend: str | None = None
    laughing: bool = False
    humming: bool = False
    end_line: bool = False
    end_paragraph: bool = False
    print_object: bool | None = None
    time_only: str | None = None
    source_id: str | None = None
    placement: str | None = None


@dataclass(frozen=True, slots=True)
class LyricSyllable:
    anchor: EventAnchor
    number: str | None
    name: str | None
    syllabic: str | None
    text: str
    source_order: int
    segments: tuple[LyricTextSegment, ...] = ()
    extend_present: bool = False
    extend: str | None = None
    laughing: bool = False
    humming: bool = False
    end_line: bool = False
    end_paragraph: bool = False
    print_object: bool | None = None
    time_only: str | None = None
    source_id: str | None = None
    placement: str | None = None


@dataclass(frozen=True, slots=True)
class TimeAnchor:
    part_id: str
    measure_id: str
    onset: Fraction
    score_onset: Fraction
    staff: str | None
    voice: str | None


@dataclass(frozen=True, slots=True)
class HarmonyNumeral:
    root: int
    alter: Fraction
    key_fifths: int | None = None
    key_mode: str | None = None


@dataclass(frozen=True, slots=True)
class HarmonyBass:
    step: str
    alter: Fraction


@dataclass(frozen=True, slots=True)
class HarmonyDegree:
    value: int
    alter: Fraction
    degree_type: str
    print_object: bool | None = None
    symbol: str | None = None
    value_text: str | None = None
    type_text: str | None = None
    plus_minus: bool | None = None


@dataclass(frozen=True, slots=True)
class HarmonyChord:
    root_step: str | None
    root_alter: Fraction
    numeral: HarmonyNumeral | None
    function: str | None
    kind: str
    kind_text: str | None
    use_symbols: bool | None = None
    stack_degrees: bool | None = None
    parentheses_degrees: bool | None = None
    bracket_degrees: bool | None = None
    inversion: int | None = None
    bass: HarmonyBass | None = None
    degrees: tuple[HarmonyDegree, ...] = ()


@dataclass(frozen=True, slots=True)
class HarmonyFrameNote:
    string: int
    fret: int
    fingering: str | None = None
    barre: str | None = None


@dataclass(frozen=True, slots=True)
class HarmonyFrame:
    strings: int
    frets: int
    first_fret: int | None
    first_fret_text: str | None
    first_fret_location: str | None
    notes: tuple[HarmonyFrameNote, ...]
    unplayed: str | None = None


@dataclass(frozen=True, slots=True)
class HarmonySymbol:
    anchor: TimeAnchor
    root_step: str | None
    root_alter: Fraction
    kind: str
    kind_text: str | None
    source_order: int
    chords: tuple[HarmonyChord, ...] = ()
    frame: HarmonyFrame | None = None
    harmony_type: str | None = None
    print_object: bool | None = None
    print_frame: bool | None = None
    arrangement: str | None = None
    source_id: str | None = None
    system_relation: str | None = None


@dataclass(frozen=True, slots=True)
class NoteheadTextSegment:
    kind: str  # display-text or accidental-text
    text: str


@dataclass(frozen=True, slots=True)
class NoteheadMarker:
    value: str | None
    filled: bool | None
    parentheses: bool | None
    smufl: str | None
    text: tuple[NoteheadTextSegment, ...] = ()


@dataclass(frozen=True, slots=True)
class NoteheadMark:
    anchor: EventAnchor
    value: str | None
    filled: bool | None
    parentheses: bool | None
    smufl: str | None
    text: tuple[NoteheadTextSegment, ...] = ()


@dataclass(frozen=True, slots=True)
class EventMarkMarker:
    family: str  # articulation, ornament, or technical
    kind: str
    text: str | None
    source_order: int
    group_id: str | None = None
    placement: str | None = None
    mark_type: str | None = None
    smufl: str | None = None
    line_shape: str | None = None
    line_type: str | None = None
    playback: TrillPlayback | None = None
    slash: bool | None = None
    long: bool | None = None
    approach: str | None = None
    departure: str | None = None
    tremolo_marks: int | None = None
    bracket: bool | None = None
    parentheses: bool | None = None
    accidentals: tuple[OrnamentAccidental, ...] = ()
    technical: TechnicalData | None = None
    number: str | None = None
    print_object: bool | None = None
    unbroken: bool | None = None


@dataclass(frozen=True, slots=True)
class EventMark:
    anchor: EventAnchor
    family: str
    kind: str
    text: str | None
    source_order: int
    group_id: str | None = None
    placement: str | None = None
    mark_type: str | None = None
    smufl: str | None = None
    line_shape: str | None = None
    line_type: str | None = None
    playback: TrillPlayback | None = None
    slash: bool | None = None
    long: bool | None = None
    approach: str | None = None
    departure: str | None = None
    tremolo_marks: int | None = None
    bracket: bool | None = None
    parentheses: bool | None = None
    accidentals: tuple[OrnamentAccidental, ...] = ()
    technical: TechnicalData | None = None
    number: str | None = None
    print_object: bool | None = None
    unbroken: bool | None = None


@dataclass(frozen=True, slots=True)
class DirectionPitch:
    """One explicit tuning pitch used by harp pedals or scordatura."""

    step: str
    alter: Fraction
    octave: int | None = None
    string: int | None = None


@dataclass(frozen=True, slots=True)
class AccordionRegistration:
    """Presence and dot count for the three accordion register regions."""

    high: bool
    middle: int | None
    low: bool


@dataclass(frozen=True, slots=True)
class DirectionImage:
    """Image direction resource and explicit dimensions."""

    source: str
    mime_type: str
    width: Fraction | None = None
    height: Fraction | None = None


@dataclass(frozen=True, slots=True)
class PrincipalVoice:
    """Principal/secondary voice analysis and bracket endpoint."""

    action: str
    symbol: str
    text: str


@dataclass(frozen=True, slots=True)
class PercussionPictogram:
    """A semantic percussion pictogram, including structured stick detail."""

    kind: str
    value: str | None = None
    smufl: str | None = None
    tip: str | None = None
    stick_type: str | None = None
    stick_material: str | None = None
    parentheses: bool | None = None
    dashed_circle: bool | None = None


@dataclass(frozen=True, slots=True)
class MetronomeBeat:
    """One note value within a regular metronome relation."""

    note_type: str
    dots: int = 0
    tied_to_previous: bool = False


@dataclass(frozen=True, slots=True)
class MetronomeBeam:
    value: str
    number: int


@dataclass(frozen=True, slots=True)
class MetronomeTuplet:
    actual_notes: int
    normal_notes: int
    normal_type: str | None
    normal_dots: int
    action: str
    bracket: bool | None
    show_number: str | None


@dataclass(frozen=True, slots=True)
class MetronomeNote:
    """One fully notated note in a metric-modulation direction."""

    note_type: str
    dots: int
    beams: tuple[MetronomeBeam, ...]
    tie: str | None
    tuplet: MetronomeTuplet | None


@dataclass(frozen=True, slots=True)
class MetronomeMark:
    """Regular tempo or metric-modulation content without presentation style."""

    beats: tuple[MetronomeBeat, ...] = ()
    per_minute: str | None = None
    arrows: bool = False
    notes: tuple[MetronomeNote, ...] = ()
    relation: str | None = None
    parentheses: bool | None = None


@dataclass(frozen=True, slots=True)
class ComplexDirectionData:
    """Closed payload union for supported nested semantic direction families."""

    metronome: MetronomeMark | None = None
    harp_pedals: tuple[DirectionPitch, ...] = ()
    scordatura: tuple[DirectionPitch, ...] = ()
    accordion: AccordionRegistration | None = None
    principal_voice: PrincipalVoice | None = None
    percussion: PercussionPictogram | None = None
    image: DirectionImage | None = None


@dataclass(frozen=True, slots=True)
class DirectionMark:
    anchor: TimeAnchor
    family: str  # semantic direction element name; dynamics use "dynamic"
    value: str
    placement: str | None
    source_order: int
    component_order: int
    group_id: str | None = None
    smufl: str | None = None
    direction_id: str | None = None
    direction_type_id: str | None = None
    source_id: str | None = None
    print_object: bool | None = None
    system_relation: str | None = None
    data: ComplexDirectionData | None = None
    presentation: PresentationStyle | None = None
    directive: bool | None = None
    pedal_number: str | None = None
    pedal_line: bool | None = None
    pedal_sign: bool | None = None
    pedal_abbreviated: bool | None = None


@dataclass(frozen=True, slots=True)
class BassFigure:
    prefix: str | None
    number: str | None
    suffix: str | None
    extend_present: bool = False
    extend: str | None = None


@dataclass(frozen=True, slots=True)
class FiguredBassAnnotation:
    anchor: EventAnchor
    figures: tuple[BassFigure, ...]
    duration: Fraction | None
    source_order: int
    parentheses: bool | None = None
    print_object: bool | None = None
    print_dot: bool | None = None
    print_spacing: bool | None = None
    placement: str | None = None
    source_id: str | None = None
    presentation: PresentationStyle | None = None


@dataclass(frozen=True, slots=True)
class TimeSpanMarker:
    kind: str
    number: str
    action: str
    opening: str | None
    anchor: TimeAnchor
    source_order: int
    component_order: int
    direction_id: str | None = None
    direction_type_id: str | None = None
    source_id: str | None = None
    system_relation: str | None = None
    source_type: str | None = None
    line_type: str | None = None
    dash_length: Fraction | None = None
    space_length: Fraction | None = None
    spread: Fraction | None = None
    niente: bool | None = None
    line_end: str | None = None
    end_length: Fraction | None = None
    pedal_line: bool | None = None
    pedal_sign: bool | None = None
    pedal_abbreviated: bool | None = None
    octave_size: int | None = None
    directive: bool | None = None
    inferred: bool = False
    inference_reason: str | None = None


@dataclass(frozen=True, slots=True)
class TimeSpan:
    id: str
    kind: str
    number: str
    opening: str | None
    endpoints: tuple[TimeSpanMarker, ...]


@dataclass(frozen=True, slots=True)
class AnnotationGraph:
    """Partial notation graph; later 7G slices add typed point families."""

    spans: tuple[NotationSpan, ...] = ()
    lyrics: tuple[LyricSyllable, ...] = ()
    harmonies: tuple[HarmonySymbol, ...] = ()
    noteheads: tuple[NoteheadMark, ...] = ()
    event_marks: tuple[EventMark, ...] = ()
    directions: tuple[DirectionMark, ...] = ()
    figured_bass: tuple[FiguredBassAnnotation, ...] = ()
    time_spans: tuple[TimeSpan, ...] = ()
