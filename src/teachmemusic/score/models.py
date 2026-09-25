"""Library-independent domain models for written musical scores.

The types in this module form TeachMeMusic's canonical score contract. They
contain no parser, renderer, learner, lesson, or performance objects. Musical
time is exact and measured in quarter-note units.
"""

from collections.abc import Iterator
from dataclasses import dataclass
from enum import StrEnum
from fractions import Fraction

CURRENT_SCHEMA_VERSION = 1


class PitchStep(StrEnum):
    """Diatonic pitch name."""

    A = "A"
    B = "B"
    C = "C"
    D = "D"
    E = "E"
    F = "F"
    G = "G"


class RhythmicValue(StrEnum):
    """Written, undisplaced note or rest value."""

    BREVE = "breve"
    WHOLE = "whole"
    HALF = "half"
    QUARTER = "quarter"
    EIGHTH = "eighth"
    SIXTEENTH = "16th"
    THIRTY_SECOND = "32nd"
    SIXTY_FOURTH = "64th"


class StemDirection(StrEnum):
    """Explicit written stem direction."""

    UP = "up"
    DOWN = "down"


class Syllabic(StrEnum):
    """A lyric unit's position inside a word."""

    SINGLE = "single"
    BEGIN = "begin"
    MIDDLE = "middle"
    END = "end"


class ClefSign(StrEnum):
    """Supported written clef signs."""

    G = "G"
    F = "F"
    C = "C"
    PERCUSSION = "percussion"
    TAB = "TAB"
    NONE = "none"


class BarlineLocation(StrEnum):
    """Position of an explicitly encoded barline in a measure."""

    LEFT = "left"
    MIDDLE = "middle"
    RIGHT = "right"


class BarlineStyle(StrEnum):
    """Supported visual barline styles."""

    REGULAR = "regular"
    LIGHT_HEAVY = "light-heavy"


class BreakKind(StrEnum):
    """Semantic layout break retained without numerical engraving data."""

    SYSTEM = "system"
    PAGE = "page"


class SourceFormat(StrEnum):
    """Source formats that may contribute provenance evidence."""

    MUSICXML = "musicxml"
    COMPRESSED_MUSICXML = "mxl"
    PDF = "pdf"


@dataclass(frozen=True, slots=True)
class Creator:
    """A named creator exactly as identified by the source."""

    role: str
    name: str


@dataclass(frozen=True, slots=True)
class ScoreMetadata:
    """Human-readable score metadata.

    ``None`` means unknown or absent. An empty string is retained when a
    source deliberately contains an empty value.
    """

    title: str | None = None
    creators: tuple[Creator, ...] = ()


@dataclass(frozen=True, slots=True)
class Staff:
    """A stable staff identity within one part."""

    id: str
    source_number: int | None = None


@dataclass(frozen=True, slots=True)
class Voice:
    """A stable voice identity within one part."""

    id: str
    source_id: str | None = None


@dataclass(frozen=True, slots=True)
class WrittenPitch:
    """Written pitch spelling, independent of a MIDI-equivalent pitch."""

    step: PitchStep
    alter: Fraction
    octave: int


@dataclass(frozen=True, slots=True)
class WrittenPitchClass:
    """Written pitch spelling without an octave, such as a chord root."""

    step: PitchStep
    alter: Fraction


@dataclass(frozen=True, slots=True)
class WrittenRhythm:
    """Written rhythmic value and augmentation-dot count."""

    value: RhythmicValue
    dots: int = 0


@dataclass(frozen=True, slots=True)
class Lyric:
    """Exact lyric text associated with a note event."""

    line: str
    text: str
    syllabic: Syllabic


@dataclass(frozen=True, slots=True)
class Clef:
    """A clef applying to a specific staff."""

    staff_id: str
    sign: ClefSign
    line: int
    octave_change: int = 0


@dataclass(frozen=True, slots=True)
class KeySignature:
    """Traditional fifths-based key signature and optional encoded mode."""

    fifths: int
    mode: str | None = None


@dataclass(frozen=True, slots=True)
class TimeSignature:
    """Written meter; multiple beat groups allow additive meters."""

    beat_groups: tuple[int, ...]
    beat_type: int


@dataclass(frozen=True, slots=True)
class AttributeChange:
    """Musical attributes beginning at a measure-local onset."""

    onset: Fraction
    clefs: tuple[Clef, ...] = ()
    key_signature: KeySignature | None = None
    time_signature: TimeSignature | None = None


@dataclass(frozen=True, slots=True)
class MeasureAttributes:
    """Effective musical attributes at the start of one measure."""

    clefs: tuple[Clef, ...] = ()
    key_signature: KeySignature | None = None
    time_signature: TimeSignature | None = None


@dataclass(frozen=True, slots=True)
class NoteEvent:
    """One written pitched event."""

    id: str
    staff_id: str
    voice_id: str
    onset: Fraction
    duration: Fraction
    source_order: int
    pitch: WrittenPitch
    rhythm: WrittenRhythm
    chord_id: str | None = None
    lyrics: tuple[Lyric, ...] = ()
    stem_direction: StemDirection | None = None


@dataclass(frozen=True, slots=True)
class RestEvent:
    """One written rest event."""

    id: str
    staff_id: str
    voice_id: str
    onset: Fraction
    duration: Fraction
    source_order: int
    rhythm: WrittenRhythm


type ScoreEvent = NoteEvent | RestEvent


@dataclass(frozen=True, slots=True)
class HarmonySymbol:
    """One written harmony symbol anchored to a staff and musical onset.

    ``display_text`` preserves source text for the harmony kind. An empty
    string is distinct from an absent value. The root is represented
    semantically rather than duplicated into the display text.
    """

    id: str
    staff_id: str
    onset: Fraction
    source_order: int
    root: WrittenPitchClass
    kind: str
    display_text: str | None = None


@dataclass(frozen=True, slots=True)
class Barline:
    """An explicitly written barline."""

    location: BarlineLocation
    style: BarlineStyle
    terminates_score: bool = False


@dataclass(frozen=True, slots=True)
class Measure:
    """One ordered measure in a part.

    ``extent`` is the measure's actual notated span. It is independent of the
    effective meter so that pickups and intentionally incomplete measures can
    be represented faithfully.
    """

    id: str
    source_label: str | None
    ordinal: int
    extent: Fraction
    attribute_changes: tuple[AttributeChange, ...] = ()
    events: tuple[ScoreEvent, ...] = ()
    harmonies: tuple[HarmonySymbol, ...] = ()
    barlines: tuple[Barline, ...] = ()

    def iter_events(self) -> Iterator[ScoreEvent]:
        """Yield events in canonical written order."""

        return iter(self.events)


@dataclass(frozen=True, slots=True)
class Part:
    """An ordered score part with explicit staff and voice identities."""

    id: str
    source_id: str | None
    display_name: str | None
    staves: tuple[Staff, ...]
    voices: tuple[Voice, ...]
    measures: tuple[Measure, ...]

    def iter_events(self) -> Iterator[ScoreEvent]:
        """Yield all events in measure and event order."""

        for measure in self.measures:
            yield from measure.events

    def measure_attributes(self) -> tuple[MeasureAttributes, ...]:
        """Resolve explicit start-of-measure changes with carry-forward."""

        clefs_by_staff: dict[str, Clef] = {}
        key_signature: KeySignature | None = None
        time_signature: TimeSignature | None = None
        resolved: list[MeasureAttributes] = []
        for measure in self.measures:
            for change in measure.attribute_changes:
                if change.onset != 0:
                    continue
                for clef in change.clefs:
                    clefs_by_staff[clef.staff_id] = clef
                if change.key_signature is not None:
                    key_signature = change.key_signature
                if change.time_signature is not None:
                    time_signature = change.time_signature
            resolved.append(
                MeasureAttributes(
                    clefs=tuple(
                        clefs_by_staff[staff.id]
                        for staff in self.staves
                        if staff.id in clefs_by_staff
                    ),
                    key_signature=key_signature,
                    time_signature=time_signature,
                )
            )
        return tuple(resolved)


@dataclass(frozen=True, slots=True)
class PresentationBreak:
    """A semantic layout break before an identified measure."""

    kind: BreakKind
    before_measure_id: str


@dataclass(frozen=True, slots=True)
class PresentationData:
    """Semantic presentation facts kept outside musical event data."""

    breaks: tuple[PresentationBreak, ...] = ()


@dataclass(frozen=True, slots=True)
class PlaybackData:
    """Unprinted playback hints, separate from written musical directions."""

    tempo_quarter_bpm: Fraction | None = None
    instrument_sound: str | None = None
    midi_channel: int | None = None
    midi_program: int | None = None


@dataclass(frozen=True, slots=True)
class SourceReference:
    """Logical source provenance without machine-specific absolute paths."""

    source_format: SourceFormat
    logical_name: str
    sha256: str | None = None


@dataclass(frozen=True, slots=True)
class ScoreRepresentation:
    """The root canonical representation consumed by TeachMeMusic systems."""

    id: str
    metadata: ScoreMetadata
    parts: tuple[Part, ...]
    presentation: PresentationData = PresentationData()
    playback: PlaybackData | None = None
    provenance: tuple[SourceReference, ...] = ()
    schema_version: int = CURRENT_SCHEMA_VERSION

    def iter_events(self) -> Iterator[ScoreEvent]:
        """Yield every event in deterministic score order."""

        for part in self.parts:
            yield from part.iter_events()

    def find_measure(self, measure_id: str) -> Measure | None:
        """Return a measure by stable ID, or ``None`` when absent."""

        for part in self.parts:
            for measure in part.measures:
                if measure.id == measure_id:
                    return measure
        return None

    def find_event(self, event_id: str) -> ScoreEvent | None:
        """Return an event by stable ID, or ``None`` when absent."""

        for event in self.iter_events():
            if event.id == event_id:
                return event
        return None
