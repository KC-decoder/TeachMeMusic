"""Invariants for the typed temporal subset of canonical schema v2."""

from __future__ import annotations

import re
from dataclasses import dataclass
from fractions import Fraction

from .annotation_graph import AnnotationGraphError, resolve_annotation_graph
from .annotations import (
    SIMPLE_EVENT_MARKS,
    BendSound,
    ComplexDirectionData,
    EventMarkMarker,
    HarmonySymbol,
    LyricMarker,
    OrnamentAccidental,
    TechnicalData,
    TrillPlayback,
)
from .layout import (
    LayoutMargins,
    MeasurePrintLayout,
    PageLayout,
    ScoreLayout,
    StaffLayout,
    SystemLayout,
)
from .links import Bookmark, ExternalLink, PartLink
from .playback import (
    InstrumentPlayback,
    MidiInstrument,
    PedalPlayback,
    SoundDirective,
    VirtualInstrument,
)
from .presentation import NameDisplay, PresentationNumber, PresentationStyle, SourcePresentation
from .temporal import (
    DeferredConstruct,
    TemporalAttributes,
    TemporalCursorMove,
    TemporalEditorial,
    TemporalEvent,
    TemporalMeasureStyle,
    TemporalScore,
    TemporalScoreMetadata,
    TemporalTransposition,
    resolve_sounding_pitches,
)


def _valid_editorial(value: TemporalEditorial | None) -> bool:
    if value is None:
        return True
    return (
        (value.footnote is not None or value.level is not None)
        and value.footnote_language != ""
        and value.level_type in {None, "start", "stop", "single"}
        and value.level_size in {None, "full", "cue", "grace-cue", "large"}
        and all(
            item is None or isinstance(item, bool)
            for item in (value.level_reference, value.level_parentheses, value.level_bracket)
        )
    )


def _valid_presentation(value: PresentationStyle | None) -> bool:
    if value is None:
        return True
    font_sizes = {
        "xx-small",
        "x-small",
        "small",
        "medium",
        "large",
        "x-large",
        "xx-large",
    }
    enclosures = {
        "rectangle",
        "square",
        "oval",
        "circle",
        "bracket",
        "inverted-bracket",
        "triangle",
        "diamond",
        "pentagon",
        "hexagon",
        "heptagon",
        "octagon",
        "nonagon",
        "decagon",
        "none",
    }

    def number_or_keyword(
        item: PresentationNumber | None, keywords: set[str], *, positive: bool = False
    ) -> bool:
        if item is None:
            return True
        if (item.number is None) == (item.keyword is None):
            return False
        return (
            item.number is not None
            and (not positive or item.number > 0)
            or item.keyword in keywords
        )

    return (
        (
            value.color is None
            or re.fullmatch(r"#[0-9A-Fa-f]{6}(?:[0-9A-Fa-f]{2})?", value.color) is not None
        )
        and value.font_family not in {""}
        and value.font_style in {None, "normal", "italic"}
        and number_or_keyword(value.font_size, font_sizes, positive=True)
        and value.font_weight in {None, "normal", "bold"}
        and value.justify in {None, "left", "center", "right"}
        and value.halign in {None, "left", "center", "right"}
        and value.valign in {None, "top", "middle", "bottom", "baseline"}
        and value.enclosure in enclosures | {None}
        and number_or_keyword(value.letter_spacing, {"normal"})
        and number_or_keyword(value.line_height, {"normal"})
        and all(
            item is None or isinstance(item, int) and not isinstance(item, bool) and 0 <= item <= 3
            for item in (value.underline, value.overline, value.line_through)
        )
        and (value.rotation is None or -180 <= value.rotation <= 180)
        and value.text_direction in {None, "ltr", "rtl", "lro", "rlo"}
        and value.language not in {""}
        and value.space in {None, "default", "preserve"}
    )


def _valid_source_presentation(value: SourcePresentation) -> bool:
    return (
        value.source_path.startswith("/")
        and bool(value.element_name)
        and _valid_presentation(value.style)
    )


def _valid_name_display(value: NameDisplay | None) -> bool:
    return value is None or (
        bool(value.segments)
        and all(
            item.kind in {"display-text", "accidental-text"} and _valid_presentation(item.style)
            for item in value.segments
        )
    )


def _valid_margins(value: LayoutMargins) -> bool:
    return (
        value.kind in {None, "odd", "even", "both"}
        and value.left >= 0
        and value.right >= 0
        and (value.top is None or value.top >= 0)
        and (value.bottom is None or value.bottom >= 0)
    )


def _valid_page_layout(value: PageLayout | None) -> bool:
    return value is None or (
        (value.height is None or value.height > 0)
        and (value.width is None or value.width > 0)
        and all(_valid_margins(item) for item in value.margins)
        and len({item.kind for item in value.margins}) == len(value.margins)
    )


def _valid_system_layout(value: SystemLayout | None) -> bool:
    return value is None or (
        (value.margins is None or _valid_margins(value.margins))
        and (value.system_distance is None or value.system_distance >= 0)
        and (value.top_system_distance is None or value.top_system_distance >= 0)
    )


def _valid_staff_layout(value: StaffLayout) -> bool:
    return value.number != "" and (value.distance is None or value.distance >= 0)


def _valid_score_layout(value: ScoreLayout | None) -> bool:
    if value is None:
        return True
    defaults = value.defaults
    if defaults is not None and (
        defaults.scaling is not None
        and (defaults.scaling.millimeters <= 0 or defaults.scaling.tenths <= 0)
        or not _valid_page_layout(defaults.page)
        or not _valid_system_layout(defaults.system)
        or any(not _valid_staff_layout(item) for item in defaults.staves)
        or defaults.music_font is not None
        and not _valid_presentation(defaults.music_font)
        or defaults.word_font is not None
        and not _valid_presentation(defaults.word_font)
        or any(
            not _valid_presentation(item.style) or item.number == "" or item.name == ""
            for item in defaults.lyric_fonts
        )
        or any(
            not item.language or item.number == "" or item.name == ""
            for item in defaults.lyric_languages
        )
        or any(
            item.kind not in {"line-width", "note-size", "distance", "other-appearance"}
            or not item.value_type
            or (item.number is None) == (item.text is None)
            for item in defaults.appearance
        )
    ):
        return False
    return all(
        credit.page > 0
        and credit.source_id != ""
        and all(item for item in credit.types)
        and bool(credit.items)
        and all(
            item.kind in {"words", "symbol", "image"}
            and item.source_id != ""
            and (item.style is None or _valid_presentation(item.style))
            and (
                item.kind in {"words", "symbol"}
                and item.mime_type is None
                and item.width is None
                and item.height is None
                or item.kind == "image"
                and bool(item.value)
                and bool(item.mime_type)
                and (item.width is None or item.width > 0)
                and (item.height is None or item.height > 0)
            )
            for item in credit.items
        )
        for credit in value.credits
    )


def _valid_measure_layout(value: MeasurePrintLayout | None) -> bool:
    return value is None or (
        (value.width is None or value.width >= 0)
        and all(
            item is None or isinstance(item, bool) for item in (value.new_page, value.new_system)
        )
        and value.page_number != ""
        and (value.blank_page is None or value.blank_page > 0)
        and _valid_page_layout(value.page)
        and _valid_system_layout(value.system)
        and all(_valid_staff_layout(item) for item in value.staves)
        and (value.measure_distance is None or value.measure_distance >= 0)
        and (value.staff_spacing is None or value.staff_spacing >= 0)
        and value.measure_numbering in {None, "none", "measure", "system", "page", "multiple-rest"}
        and _valid_name_display(value.part_name_display)
        and _valid_name_display(value.part_abbreviation_display)
    )


def _valid_metadata(value: TemporalScoreMetadata) -> bool:
    encoding = value.encoding
    return (
        isinstance(value.concert_score, bool)
        and value.schema_location != ""
        and not any(
            item.text_type == "" for item in (*value.creators, *value.rights, *value.relations)
        )
        and not any(item.name == "" for item in value.miscellaneous)
        and (
            encoding is None
            or (
                not any(not date for date in encoding.dates)
                and not any(item.text_type == "" for item in encoding.encoders)
                and not any(
                    not item.element or item.attribute == "" or item.value == ""
                    for item in encoding.supports
                )
            )
        )
    )


def _valid_virtual(value: VirtualInstrument | None) -> bool:
    return value is None or (
        value.library != ""
        and value.name != ""
        and (value.library is not None or value.name is not None)
    )


def _valid_midi(value: MidiInstrument) -> bool:
    return (
        bool(value.instrument_id)
        and (value.channel is None or 1 <= value.channel <= 16)
        and value.name != ""
        and (value.bank is None or 1 <= value.bank <= 16384)
        and (value.program is None or 1 <= value.program <= 128)
        and (value.unpitched is None or 1 <= value.unpitched <= 128)
        and (value.volume is None or 0 <= value.volume <= 100)
        and (value.pan is None or -180 <= value.pan <= 180)
        and (value.elevation is None or -180 <= value.elevation <= 180)
    )


def _valid_playback(value: InstrumentPlayback, instrument_id: str) -> bool:
    return (
        all(
            device.instrument_id in {None, instrument_id}
            and (device.port is None or 1 <= device.port <= 16)
            for device in value.devices
        )
        and all(item.instrument_id == instrument_id and _valid_midi(item) for item in value.midi)
        and _valid_virtual(value.virtual)
    )


def _valid_pedal(value: PedalPlayback | None) -> bool:
    return value is None or (
        (value.enabled is None) != (value.percent is None)
        and (value.enabled is None or isinstance(value.enabled, bool))
        and (value.percent is None or 0 <= value.percent <= 100)
    )


def _valid_sound(value: SoundDirective, instrument_ids: set[str]) -> bool:
    return (
        value.onset >= 0
        and value.score_onset >= 0
        and value.source_order > 0
        and (value.tempo is None or value.tempo >= 0)
        and (value.dynamics is None or value.dynamics >= 0)
        and (value.divisions is None or value.divisions > 0)
        and (value.pan is None or -180 <= value.pan <= 180)
        and (value.elevation is None or -180 <= value.elevation <= 180)
        and all(
            item is None or isinstance(item, bool)
            for item in (value.dacapo, value.forward_repeat, value.pizzicato)
        )
        and all(
            _valid_pedal(item)
            for item in (
                value.damper_pedal,
                value.soft_pedal,
                value.sostenuto_pedal,
            )
        )
        and all(
            change.instrument_id in instrument_ids
            and not (change.solo and change.ensemble)
            and (change.ensemble_size is None or change.ensemble and change.ensemble_size > 0)
            and _valid_virtual(change.virtual)
            for change in value.instrument_changes
        )
        and all(
            device.instrument_id in instrument_ids | {None}
            and (device.port is None or 1 <= device.port <= 16)
            for device in value.devices
        )
        and all(item.instrument_id in instrument_ids and _valid_midi(item) for item in value.midi)
        and all(
            technique.instrument_id in instrument_ids | {None}
            and technique.kind in {"ipa", "mute", "semi-pitched", "other-play"}
            and (technique.kind == "other-play") == (technique.technique_type is not None)
            for technique in value.techniques
        )
        and (
            value.swing is None
            or value.swing.straight
            and value.swing.first is None
            and value.swing.second is None
            or not value.swing.straight
            and value.swing.first is not None
            and value.swing.first > 0
            and value.swing.second is not None
            and value.swing.second > 0
            and value.swing.note_type in {None, "eighth", "16th"}
        )
    )


def _valid_link(value: ExternalLink) -> bool:
    return (
        bool(value.href)
        and value.link_type in {None, "simple"}
        and value.role != ""
        and value.title != ""
        and value.show in {None, "new", "replace", "embed", "other", "none"}
        and value.actuate in {None, "onLoad", "onRequest", "other", "none"}
        and value.name != ""
        and value.element != ""
        and (value.position is None or value.position > 0)
        and _valid_presentation(value.presentation)
    )


def _valid_bookmark(value: Bookmark) -> bool:
    return (
        bool(value.id)
        and value.name != ""
        and value.element != ""
        and (value.position is None or value.position > 0)
    )


def _valid_part_link(value: PartLink, instrument_ids: set[str]) -> bool:
    return (
        _valid_link(value.link)
        and all(item in instrument_ids for item in value.instrument_ids)
        and all(bool(item) for item in value.group_links)
    )


def _valid_measure_style(value: TemporalMeasureStyle) -> bool:
    if (
        value.kind not in {"multiple-rest", "measure-repeat", "beat-repeat", "slash"}
        or value.staff == ""
        or value.source_id == ""
        or (value.value is not None and value.value <= 0)
        or (value.slashes is not None and value.slashes <= 0)
        or value.action not in {None, "start", "stop"}
        or value.slash_type not in _NOTE_TYPES | {None}
        or value.slash_dots < 0
        or any(
            item is not None and not isinstance(item, bool)
            for item in (value.use_symbols, value.use_dots, value.use_stems)
        )
    ):
        return False
    if value.kind == "multiple-rest":
        return (
            value.value is not None
            and value.action is None
            and value.slashes is None
            and value.use_dots is None
            and value.use_stems is None
            and value.slash_type is None
            and value.slash_dots == 0
        )
    if value.kind == "measure-repeat":
        return (
            value.action is not None
            and value.use_symbols is None
            and value.use_dots is None
            and value.use_stems is None
            and value.slash_type is None
            and value.slash_dots == 0
        )
    if value.kind == "beat-repeat":
        return value.action is not None and value.use_symbols is None and value.use_stems is None
    return (
        value.action is not None
        and value.value is None
        and value.slashes is None
        and value.use_symbols is None
    )


def _valid_attributes(value: TemporalAttributes) -> bool:
    if value.staves is not None and value.staves <= 0:
        return False
    if value.instrument_count is not None and value.instrument_count <= 0:
        return False
    for clef in value.clefs:
        if (
            clef.staff == ""
            or clef.sign not in {"G", "F", "C", "percussion", "TAB", "jianpu", "none"}
            or clef.size not in {None, "full", "cue", "grace-cue", "large"}
            or clef.source_id == ""
            or any(
                item is not None and not isinstance(item, bool)
                for item in (clef.additional, clef.after_barline, clef.print_object)
            )
        ):
            return False
    for key in value.keys:
        if (
            key.staff == ""
            or key.source_id == ""
            or key.cancel_location not in {None, "left", "right", "before-barline"}
            or key.print_object is not None
            and not isinstance(key.print_object, bool)
            or (key.fifths is None) == (not key.alterations)
            or any(
                alteration.step not in {"A", "B", "C", "D", "E", "F", "G"}
                or alteration.accidental not in _ACCIDENTAL_VALUES | {None}
                or alteration.accidental_smufl == ""
                or bool(alteration.accidentals) != (alteration.accidental is not None)
                or (
                    bool(alteration.accidentals)
                    and (
                        alteration.accidentals[0].value != alteration.accidental
                        or alteration.accidentals[0].smufl != alteration.accidental_smufl
                    )
                )
                or any(
                    item.value not in _ACCIDENTAL_VALUES or item.smufl == ""
                    for item in alteration.accidentals
                )
                for alteration in key.alterations
            )
            or any(
                octave.number <= 0
                or not 0 <= octave.octave <= 9
                or (octave.cancel is not None and not isinstance(octave.cancel, bool))
                for octave in key.octaves
            )
        ):
            return False
    time_symbols = {None, "common", "cut", "single-number", "note", "dotted-note", "normal"}
    separators = {None, "none", "horizontal", "diagonal", "vertical", "adjacent"}
    for time in value.times:
        if (
            time.staff == ""
            or time.source_id == ""
            or time.symbol not in time_symbols
            or time.separator not in separators
            or (time.print_object is not None and not isinstance(time.print_object, bool))
            or len(time.beats) != len(time.beat_types)
            or any(
                not beat or beat_type <= 0
                for beat, beat_type in zip(time.beats, time.beat_types, strict=True)
            )
            or (time.senza_misura is not None and (time.beats or time.interchangeable is not None))
        ):
            return False
        alternate = time.interchangeable
        if alternate is not None and (
            len(alternate.beats) != len(alternate.beat_types)
            or not alternate.beats
            or any(
                not beat or beat_type <= 0
                for beat, beat_type in zip(alternate.beats, alternate.beat_types, strict=True)
            )
            or alternate.relation
            not in {None, "parentheses", "bracket", "equals", "slash", "space", "hyphen"}
            or alternate.symbol not in time_symbols
            or alternate.separator not in separators
        ):
            return False
    for details in value.staff_details:
        if (
            details.staff == ""
            or details.staff_type not in {None, "ossia", "editorial", "cue", "alternate", "regular"}
            or details.show_frets not in {None, "numbers", "letters"}
            or (details.lines is not None and details.lines < 0)
            or (details.capo is not None and details.capo < 0)
            or (details.size is not None and details.size <= 0)
            or (details.scaling is not None and details.scaling < 0)
            or (details.print_object is not None and not isinstance(details.print_object, bool))
            or any(
                tuning.line <= 0
                or tuning.step not in {"A", "B", "C", "D", "E", "F", "G"}
                or not 0 <= tuning.octave <= 9
                for tuning in details.tunings
            )
            or len({line.line for line in details.line_details}) != len(details.line_details)
            or any(
                line.line <= 0
                or (details.lines is not None and line.line > details.lines)
                or (line.print_object is not None and not isinstance(line.print_object, bool))
                or not _valid_presentation(line.presentation)
                for line in details.line_details
            )
        ):
            return False
    if value.part_symbols and value.part_symbol != value.part_symbols[0]:
        return False
    symbols = value.part_symbols or ((value.part_symbol,) if value.part_symbol is not None else ())
    for symbol in symbols:
        if not (
            symbol.value in {"none", "brace", "line", "bracket", "square"}
            and symbol.top_staff != ""
            and symbol.bottom_staff != ""
            and _valid_presentation(symbol.presentation)
        ):
            return False
    if any(
        item.staff == ""
        or item.source_id == ""
        or item.clef is not None
        and (
            item.clef.sign not in {"G", "F", "C", "percussion", "TAB", "jianpu", "none"}
            or item.clef.line is not None
            and item.clef.line <= 0
        )
        for item in value.for_parts
    ):
        return False
    return all(
        directive.value != "" and directive.language != "" and directive.source_order > 0
        for directive in value.directives
    )


@dataclass(frozen=True, slots=True)
class TemporalValidationIssue:
    code: str
    path: str
    message: str


_NOTE_TYPES = {
    "1024th",
    "512th",
    "256th",
    "128th",
    "64th",
    "32nd",
    "16th",
    "eighth",
    "quarter",
    "half",
    "whole",
    "breve",
    "long",
    "maxima",
}

_ACCIDENTAL_VALUES = {
    "arrow-down",
    "arrow-up",
    "double-sharp-down",
    "double-sharp-up",
    "double-sharp",
    "double-slash-flat",
    "flat-1",
    "flat-2",
    "flat-3",
    "flat-4",
    "flat-down",
    "flat-flat-down",
    "flat-flat-up",
    "flat-flat",
    "flat-up",
    "flat",
    "koron",
    "natural-down",
    "natural-flat",
    "natural-sharp",
    "natural-up",
    "natural",
    "other",
    "quarter-flat",
    "quarter-sharp",
    "sharp-1",
    "sharp-2",
    "sharp-3",
    "sharp-5",
    "sharp-down",
    "sharp-sharp",
    "sharp-up",
    "sharp",
    "slash-flat",
    "slash-quarter-sharp",
    "slash-sharp",
    "sori",
    "three-quarters-flat",
    "three-quarters-sharp",
    "triple-flat",
    "triple-sharp",
}

_PERCUSSION_VALUES = {
    "glass": {"glass harmonica", "glass harp", "wind chimes"},
    "metal": {
        "agogo",
        "almglocken",
        "bell",
        "bell plate",
        "bell tree",
        "brake drum",
        "cencerro",
        "chain rattle",
        "Chinese cymbal",
        "cowbell",
        "crash cymbals",
        "crotale",
        "cymbal tongs",
        "domed gong",
        "finger cymbals",
        "flexatone",
        "gong",
        "handbell",
        "hi-hat",
        "high-hat cymbals",
        "jaw harp",
        "jingle bells",
        "musical saw",
        "shell bells",
        "sistrum",
        "sizzle cymbal",
        "sleigh bells",
        "suspended cymbal",
        "tam tam",
        "tam tam with beater",
        "triangle",
        "Vietnamese hat",
    },
    "wood": {
        "bamboo scraper",
        "board clapper",
        "cabasa",
        "castanets",
        "castanets with handle",
        "claves",
        "football rattle",
        "guiro",
        "log drum",
        "maraca",
        "maracas",
        "quijada",
        "rainstick",
        "ratchet",
        "reco-reco",
        "sandpaper blocks",
        "slit drum",
        "temple block",
        "vibraslap",
        "whip",
        "wood block",
    },
    "pitched": {
        "celesta",
        "chimes",
        "glockenspiel",
        "lithophone",
        "mallet",
        "marimba",
        "steel drums",
        "tubaphone",
        "tubular chimes",
        "vibraphone",
        "xylophone",
    },
    "membrane": {
        "bass drum",
        "bass drum on side",
        "bongos",
        "Chinese tomtom",
        "conga drum",
        "cuica",
        "goblet drum",
        "Indo-American tomtom",
        "Japanese tomtom",
        "military drum",
        "snare drum",
        "snare drum snares off",
        "tabla",
        "tambourine",
        "tenor drum",
        "timbales",
        "tomtom",
    },
    "effect": {
        "anvil",
        "auto horn",
        "bird whistle",
        "cannon",
        "duck call",
        "gun shot",
        "klaxon horn",
        "lions roar",
        "lotus flute",
        "megaphone",
        "police whistle",
        "siren",
        "slide whistle",
        "thunder sheet",
        "wind machine",
        "wind whistle",
    },
    "beater": {
        "bow",
        "chime hammer",
        "coin",
        "drum stick",
        "finger",
        "fingernail",
        "fist",
        "guiro scraper",
        "hammer",
        "hand",
        "jazz stick",
        "knitting needle",
        "metal hammer",
        "slide brush on gong",
        "snare stick",
        "spoon mallet",
        "superball",
        "triangle beater",
        "triangle beater plain",
        "wire brush",
    },
    "stick-location": {"center", "rim", "cymbal bell", "cymbal edge"},
}

_HARMONY_KINDS = {
    "major",
    "minor",
    "augmented",
    "diminished",
    "dominant",
    "major-seventh",
    "minor-seventh",
    "diminished-seventh",
    "augmented-seventh",
    "half-diminished",
    "major-minor",
    "major-sixth",
    "minor-sixth",
    "dominant-ninth",
    "major-ninth",
    "minor-ninth",
    "dominant-11th",
    "major-11th",
    "minor-11th",
    "dominant-13th",
    "major-13th",
    "minor-13th",
    "suspended-second",
    "suspended-fourth",
    "Neapolitan",
    "Italian",
    "French",
    "German",
    "pedal",
    "power",
    "Tristan",
    "other",
    "none",
}


def _valid_complex_direction(family: str, data: ComplexDirectionData | None) -> bool:
    if data is None:
        return False
    payloads = (
        data.metronome is not None,
        bool(data.harp_pedals),
        bool(data.scordatura),
        data.accordion is not None,
        data.principal_voice is not None,
        data.percussion is not None,
        data.image is not None,
    )
    if sum(payloads) != 1:
        return False
    if data.metronome is not None:
        mark = data.metronome
        if bool(mark.beats) == bool(mark.notes):
            return False
        if mark.parentheses is not None and not isinstance(mark.parentheses, bool):
            return False
        if mark.beats:
            if mark.arrows or mark.relation is not None:
                return False
            if mark.per_minute is None and len(mark.beats) < 2:
                return False
            return all(beat.note_type in _NOTE_TYPES and beat.dots >= 0 for beat in mark.beats)
        if mark.per_minute is not None or not mark.notes:
            return False
        for note in mark.notes:
            if (
                note.note_type not in _NOTE_TYPES
                or note.dots < 0
                or note.tie not in {None, "start", "stop"}
                or any(
                    beam.value not in {"begin", "continue", "end", "forward hook", "backward hook"}
                    or not 1 <= beam.number <= 8
                    for beam in note.beams
                )
            ):
                return False
            tuplet = note.tuplet
            if tuplet is not None and (
                tuplet.actual_notes < 1
                or tuplet.normal_notes < 1
                or tuplet.normal_type not in _NOTE_TYPES | {None}
                or tuplet.normal_dots < 0
                or tuplet.action not in {"start", "stop"}
                or tuplet.show_number not in {None, "actual", "both", "none"}
            ):
                return False
        return True
    pitches = data.harp_pedals or data.scordatura
    if pitches:
        if family == "harp-pedals" and len(pitches) > 7:
            return False
        return all(
            pitch.step in {"A", "B", "C", "D", "E", "F", "G"}
            and (family != "harp-pedals" or pitch.octave is None)
            and (family != "scordatura" or pitch.octave is not None)
            and (pitch.octave is None or 0 <= pitch.octave <= 9)
            and (pitch.string is None or pitch.string >= 1)
            for pitch in pitches
        )
    if data.accordion is not None:
        accordion = data.accordion
        # The schema permits an explicit empty accordion-registration even
        # though its prose recommends at least one register region. Preserve
        # that explicit source construct instead of making the canonical
        # package invalid.
        return accordion.middle in {
            None,
            1,
            2,
            3,
        }
    if data.principal_voice is not None:
        principal = data.principal_voice
        return principal.action in {"start", "stop"} and principal.symbol in {
            "Hauptstimme",
            "Nebenstimme",
            "plain",
            "none",
        }
    if data.image is not None:
        return (
            bool(data.image.source)
            and bool(data.image.mime_type)
            and (data.image.width is None or data.image.width > 0)
            and (data.image.height is None or data.image.height > 0)
        )
    pictogram = data.percussion
    if pictogram is None or pictogram.smufl == "":
        return False
    if pictogram.kind == "stick":
        return (
            pictogram.value is None
            and pictogram.tip
            in {
                None,
                "up",
                "down",
                "left",
                "right",
                "northwest",
                "northeast",
                "southeast",
                "southwest",
            }
            and pictogram.stick_type
            in {
                "bass drum",
                "double bass drum",
                "glockenspiel",
                "gum",
                "hammer",
                "superball",
                "timpani",
                "wound",
                "xylophone",
                "yarn",
            }
            and pictogram.stick_material in {"soft", "medium", "hard", "shaded", "x"}
        )
    if pictogram.kind in {"timpani", "other-percussion"}:
        return pictogram.value is not None
    return pictogram.value in _PERCUSSION_VALUES.get(pictogram.kind, set())


def _valid_lyric(value: LyricMarker) -> bool:
    primary_count = sum(
        (
            bool(value.segments),
            value.extend_present and not value.segments,
            value.laughing,
            value.humming,
        )
    )
    if primary_count != 1:
        return False
    if value.syllabic != (value.segments[0].syllabic if value.segments else None):
        return False
    if value.text != "".join(
        f"{segment.elision_before or ''}{segment.text}" for segment in value.segments
    ):
        return False
    if value.extend not in {None, "start", "continue", "stop"}:
        return False
    if value.extend is not None and not value.extend_present:
        return False
    if value.print_object is not None and not isinstance(value.print_object, bool):
        return False
    if (
        value.time_only == ""
        or value.source_id == ""
        or value.placement not in {None, "above", "below"}
    ):
        return False
    for index, segment in enumerate(value.segments):
        if (
            segment.syllabic not in {None, "single", "begin", "end", "middle"}
            or segment.elision_smufl == ""
            or (index == 0 and segment.elision_before is not None)
            or (segment.elision_before is None and segment.elision_smufl is not None)
        ):
            return False
    return True


def _valid_harmony(value: HarmonySymbol) -> bool:
    if not value.chords:
        return False
    first = value.chords[0]
    if (
        value.root_step != first.root_step
        or value.root_alter != first.root_alter
        or value.kind != first.kind
        or value.kind_text != first.kind_text
        or value.harmony_type not in {None, "explicit", "implied", "alternate"}
        or value.arrangement not in {None, "vertical", "horizontal", "diagonal"}
        or value.system_relation not in {None, "only-top", "also-top", "none"}
        or value.source_id == ""
        or any(
            item is not None and not isinstance(item, bool)
            for item in (value.print_object, value.print_frame)
        )
    ):
        return False
    for chord in value.chords:
        sources = sum(
            (chord.root_step is not None, chord.numeral is not None, chord.function is not None)
        )
        if sources != 1 or chord.kind not in _HARMONY_KINDS:
            return False
        if chord.root_step not in {None, "A", "B", "C", "D", "E", "F", "G"}:
            return False
        if chord.numeral is not None and (
            not 1 <= chord.numeral.root <= 7
            or chord.numeral.key_mode
            not in {None, "major", "minor", "natural minor", "melodic minor", "harmonic minor"}
        ):
            return False
        if chord.inversion is not None and chord.inversion < 0:
            return False
        if chord.bass is not None and chord.bass.step not in {"A", "B", "C", "D", "E", "F", "G"}:
            return False
        if any(
            degree.value < 1
            or degree.degree_type not in {"add", "alter", "subtract"}
            or degree.symbol
            not in {None, "major", "minor", "augmented", "diminished", "half-diminished"}
            or degree.print_object is not None
            and not isinstance(degree.print_object, bool)
            or degree.plus_minus is not None
            and not isinstance(degree.plus_minus, bool)
            for degree in chord.degrees
        ):
            return False
    frame = value.frame
    return frame is None or not (
        frame.strings < 1
        or frame.frets < 1
        or (frame.first_fret is not None and frame.first_fret < 1)
        or frame.first_fret_location not in {None, "left", "right"}
        or not frame.notes
        or any(
            note.string < 1
            or note.string > frame.strings
            or note.fret < 0
            or note.barre not in {None, "start", "stop"}
            for note in frame.notes
        )
    )


def _valid_trill_playback(value: TrillPlayback | None) -> bool:
    return value is None or (
        value.start_note in {None, "upper", "main", "below"}
        and value.trill_step in {None, "whole", "half", "unison"}
        and value.two_note_turn in {None, "whole", "half", "none"}
        and (value.beats is None or value.beats >= 2)
        and (value.second_beat is None or 0 <= value.second_beat <= 100)
        and (value.last_beat is None or 0 <= value.last_beat <= 100)
    )


def _valid_bend_sound(value: BendSound | None) -> bool:
    return value is None or (
        (value.accelerate is None or isinstance(value.accelerate, bool))
        and (value.beats is None or value.beats >= 2)
        and (value.first_beat is None or 0 <= value.first_beat <= 100)
        and (value.last_beat is None or 0 <= value.last_beat <= 100)
    )


def _valid_notation_mark(mark: EventMarkMarker) -> bool:
    common_clear = (
        all(
            value is None
            for value in (
                mark.line_shape,
                mark.line_type,
                mark.playback,
                mark.slash,
                mark.long,
                mark.approach,
                mark.departure,
                mark.tremolo_marks,
                mark.bracket,
                mark.parentheses,
                mark.technical,
            )
        )
        and not mark.accidentals
    )
    if not common_clear:
        return False
    if mark.kind == "fermata":
        return (
            mark.mark_type in {None, "upright", "inverted"}
            and mark.text
            in {
                None,
                "normal",
                "angled",
                "square",
                "double-angled",
                "double-square",
                "double-dot",
                "half-curve",
                "curlew",
            }
            and mark.smufl is None
            and mark.number is None
            and mark.print_object is None
            and mark.unbroken is None
        )
    if mark.kind == "arpeggiate":
        return (
            mark.text is None
            and mark.mark_type in {None, "up", "down"}
            and mark.smufl is None
            and mark.print_object is None
            and (mark.unbroken is None or isinstance(mark.unbroken, bool))
        )
    if mark.kind == "non-arpeggiate":
        return (
            mark.text is None
            and mark.mark_type in {"top", "bottom"}
            and mark.smufl is None
            and mark.print_object is None
            and mark.unbroken is None
        )
    return (
        mark.kind == "other-notation"
        and mark.mark_type == "single"
        and (mark.print_object is None or isinstance(mark.print_object, bool))
        and mark.unbroken is None
    )


def _valid_ornament_accidental(value: OrnamentAccidental) -> bool:
    return (
        bool(value.value)
        and value.placement in {None, "above", "below"}
        and all(item != "" for item in (value.smufl,))
    )


def _valid_technical_data(kind: str, value: TechnicalData | None) -> bool:
    nested = {"harmonic", "bend", "hole", "arrow", "harmon-mute"}
    attributed = {"fingering", "heel", "toe", "tap"}
    if value is None:
        return kind not in nested
    payloads = (
        value.harmonic,
        value.bend,
        value.hole,
        value.arrow,
        value.harmon_mute,
    )
    expected_payload = {
        "harmonic": value.harmonic,
        "bend": value.bend,
        "hole": value.hole,
        "arrow": value.arrow,
        "harmon-mute": value.harmon_mute,
    }.get(kind)
    if kind in nested and (
        expected_payload is None or sum(item is not None for item in payloads) != 1
    ):
        return False
    if kind not in nested and any(item is not None for item in payloads):
        return False
    if kind not in attributed and any(
        item is not None for item in (value.substitution, value.alternate, value.hand)
    ):
        return False
    if kind != "fingering" and value.alternate is not None:
        return False
    if kind not in {"fingering", "heel", "toe"} and value.substitution is not None:
        return False
    if kind != "tap" and value.hand is not None:
        return False
    if value.hand not in {None, "left", "right"}:
        return False
    if value.harmonic is not None and (
        value.harmonic.harmonic_type not in {None, "natural", "artificial"}
        or value.harmonic.pitch_type not in {None, "base-pitch", "touching-pitch", "sounding-pitch"}
        or value.harmonic.number == ""
    ):
        return False
    if value.bend is not None and (
        value.bend.action not in {None, "pre-bend", "release"}
        or (value.bend.action != "release" and value.bend.release_offset is not None)
        or value.bend.with_bar_placement not in {None, "above", "below"}
        or value.bend.shape not in {None, "angled", "curved"}
        or (value.bend.beats is not None and value.bend.beats < 2)
        or (value.bend.first_beat is not None and not 0 <= value.bend.first_beat <= 100)
        or (value.bend.last_beat is not None and not 0 <= value.bend.last_beat <= 100)
    ):
        return False
    if value.hole is not None and (
        value.hole.closed not in {"yes", "no", "half"}
        or value.hole.closed_location not in {None, "right", "bottom", "left", "top"}
    ):
        return False
    if value.arrow is not None and (
        (value.arrow.direction is None) == (value.arrow.circular is None)
        or value.arrow.direction
        not in {
            None,
            "left",
            "up",
            "right",
            "down",
            "northwest",
            "northeast",
            "southeast",
            "southwest",
            "left right",
            "up down",
            "northwest southeast",
            "northeast southwest",
            "other",
        }
        or value.arrow.style
        not in {None, "single", "double", "filled", "hollow", "paired", "combined", "other"}
        or value.arrow.circular not in {None, "clockwise", "anticlockwise"}
        or (
            value.arrow.circular is not None
            and (value.arrow.style is not None or value.arrow.arrowhead_only)
        )
    ):
        return False
    return value.harmon_mute is None or (
        value.harmon_mute.closed in {"yes", "no", "half"}
        and value.harmon_mute.closed_location in {None, "right", "bottom", "left", "top"}
    )


def validate_temporal_score(score: TemporalScore) -> tuple[TemporalValidationIssue, ...]:
    """Check exact timing, source trace, references, and derived sound/alignment."""

    issues: list[TemporalValidationIssue] = []
    if not _valid_metadata(score.metadata):
        issues.append(
            TemporalValidationIssue(
                "TEMPORAL_METADATA", "score.metadata", "invalid source metadata"
            )
        )
    if not _valid_score_layout(score.layout):
        issues.append(
            TemporalValidationIssue("TEMPORAL_SCORE_LAYOUT", "score.layout", "invalid layout")
        )
    if score.work_opus is not None and not _valid_link(score.work_opus):
        issues.append(
            TemporalValidationIssue("TEMPORAL_WORK_OPUS", "score.work_opus", "invalid opus link")
        )
    if (
        any(not _valid_source_presentation(item) for item in score.source_presentations)
        or tuple(item.source_path for item in score.source_presentations)
        != tuple(sorted(item.source_path for item in score.source_presentations))
        or len({item.source_path for item in score.source_presentations})
        != len(score.source_presentations)
    ):
        issues.append(
            TemporalValidationIssue(
                "TEMPORAL_SOURCE_PRESENTATION",
                "score.source_presentations",
                "invalid source presentation records",
            )
        )
    if any(
        not item.context or item.source_order <= 0 or not _valid_link(item.link)
        for item in score.links
    ):
        issues.append(
            TemporalValidationIssue("TEMPORAL_LINK", "score.links", "invalid scoped link")
        )
    if any(
        not item.context or item.source_order <= 0 or not _valid_bookmark(item.bookmark)
        for item in score.bookmarks
    ):
        issues.append(
            TemporalValidationIssue(
                "TEMPORAL_BOOKMARK", "score.bookmarks", "invalid scoped bookmark"
            )
        )
    if not score.parts:
        issues.append(TemporalValidationIssue("TEMPORAL_PARTS_EMPTY", "score.parts", "no parts"))
    active_groups: set[str] = set()
    for index, group in enumerate(score.groups):
        if (
            not group.number
            or group.symbol not in {None, "none", "brace", "line", "bracket", "square"}
            or group.barline not in {None, "yes", "no", "Mensurstrich"}
            or not isinstance(group.group_time, bool)
            or group.source_id == ""
            or not _valid_editorial(group.editorial)
            or not _valid_name_display(group.name_display)
            or not _valid_name_display(group.abbreviation_display)
        ):
            issues.append(
                TemporalValidationIssue(
                    "TEMPORAL_PART_GROUP", f"score.groups[{index}]", "invalid group semantics"
                )
            )
        if group.action == "start" and group.number not in active_groups:
            active_groups.add(group.number)
        elif group.action == "stop" and group.number in active_groups:
            active_groups.remove(group.number)
        else:
            issues.append(
                TemporalValidationIssue(
                    "TEMPORAL_PART_GROUP", f"score.groups[{index}]", "unmatched group endpoint"
                )
            )
    if active_groups:
        issues.append(
            TemporalValidationIssue("TEMPORAL_PART_GROUP", "score.groups", "unclosed part group")
        )
    seen_parts: set[str] = set()
    alignment_members: dict[Fraction, list[tuple[str, int]]] = {}
    for part_index, part in enumerate(score.parts):
        part_path = f"score.parts[{part_index}]"
        if not part.id or part.id in seen_parts:
            issues.append(TemporalValidationIssue("TEMPORAL_PART_ID", part_path, "invalid part ID"))
        seen_parts.add(part.id)
        if any(
            value is not None and not isinstance(value, bool)
            for value in (part.name_print_object, part.abbreviation_print_object)
        ):
            issues.append(
                TemporalValidationIssue(
                    "TEMPORAL_PART_DISPLAY", part_path, "invalid part display policy"
                )
            )
        if not _valid_name_display(part.name_display) or not _valid_name_display(
            part.abbreviation_display
        ):
            issues.append(
                TemporalValidationIssue(
                    "TEMPORAL_PART_DISPLAY", part_path, "invalid part display override"
                )
            )
        instrument_ids = {instrument.id for instrument in part.instruments}
        if (
            len(instrument_ids) != len(part.instruments)
            or "" in instrument_ids
            or any(
                instrument.sound == ""
                or instrument.solo
                and instrument.ensemble
                or instrument.ensemble_size is not None
                and (not instrument.ensemble or instrument.ensemble_size <= 0)
                or not _valid_playback(instrument.playback, instrument.id)
                for instrument in part.instruments
            )
        ):
            issues.append(
                TemporalValidationIssue("TEMPORAL_INSTRUMENT_ID", part_path, "duplicate/empty ID")
            )
        if len({player.id for player in part.players}) != len(part.players) or any(
            not player.id or not player.name for player in part.players
        ):
            issues.append(
                TemporalValidationIssue("TEMPORAL_PLAYER", part_path, "invalid player declarations")
            )
        if any(not _valid_part_link(link, instrument_ids) for link in part.part_links):
            issues.append(
                TemporalValidationIssue("TEMPORAL_PART_LINK", part_path, "invalid part link")
            )
        if any(not group for group in part.groups) or not _valid_metadata(part.metadata):
            issues.append(
                TemporalValidationIssue(
                    "TEMPORAL_PART_METADATA", part_path, "invalid part metadata"
                )
            )
        expected_staves = {staff for measure in part.measures for staff in measure.staves}
        expected_voices = {voice for measure in part.measures for voice in measure.voices}
        if (
            {staff.source_number for staff in part.staves} != expected_staves
            or len({staff.id for staff in part.staves}) != len(part.staves)
            or any(staff.id != f"{part.id}:staff:{staff.source_number}" for staff in part.staves)
        ):
            issues.append(
                TemporalValidationIssue("TEMPORAL_STAFF_STRUCTURE", part_path, "staff mismatch")
            )
        if (
            {voice.source_id for voice in part.voices} != expected_voices
            or len({voice.id for voice in part.voices}) != len(part.voices)
            or any(voice.id != f"{part.id}:voice:{voice.source_id}" for voice in part.voices)
        ):
            issues.append(
                TemporalValidationIssue("TEMPORAL_VOICE_STRUCTURE", part_path, "voice mismatch")
            )
        score_cursor = Fraction(0)
        divisions: int | None = None
        transpositions: dict[str | None, TemporalTransposition] = {}
        event_ids: set[str] = set()
        for measure_index, measure in enumerate(part.measures):
            path = f"{part_path}.measures[{measure_index}]"
            if measure.ordinal != measure_index + 1:
                issues.append(
                    TemporalValidationIssue("TEMPORAL_MEASURE_ORDER", path, "ordinal mismatch")
                )
            if measure.id != f"{part.id}:m{measure.ordinal}":
                issues.append(
                    TemporalValidationIssue("TEMPORAL_MEASURE_ID", path, "measure ID mismatch")
                )
            if measure.score_onset != score_cursor or measure.extent < 0:
                issues.append(
                    TemporalValidationIssue(
                        "TEMPORAL_SCORE_TIME", path, "invalid score onset/extent"
                    )
                )
            if not _valid_measure_layout(measure.layout):
                issues.append(
                    TemporalValidationIssue("TEMPORAL_MEASURE_LAYOUT", path, "invalid print layout")
                )
            for sound_index, sound in enumerate(measure.sounds):
                if sound.score_onset != measure.score_onset + sound.onset or not _valid_sound(
                    sound, instrument_ids
                ):
                    issues.append(
                        TemporalValidationIssue(
                            "TEMPORAL_SOUND",
                            f"{path}.sounds[{sound_index}]",
                            "invalid playback directive",
                        )
                    )
            if any(not _valid_link(link) for link in measure.links):
                issues.append(
                    TemporalValidationIssue("TEMPORAL_LINK", path, "invalid measure link")
                )
            if any(not _valid_bookmark(item) for item in measure.bookmarks):
                issues.append(
                    TemporalValidationIssue("TEMPORAL_BOOKMARK", path, "invalid bookmark")
                )
            if not measure.non_controlling:
                alignment_members.setdefault(measure.score_onset, []).append(
                    (part.id, measure.ordinal)
                )
            if len(set(measure.staves)) != len(measure.staves) or len(set(measure.voices)) != len(
                measure.voices
            ):
                issues.append(
                    TemporalValidationIssue("TEMPORAL_STAFF_VOICE", path, "duplicate identities")
                )
            ordered = sorted(
                measure.events,
                key=lambda event: (event.onset, event.staff, event.voice, event.source_order),
            )
            semantic_orders = {event.id: index for index, event in enumerate(ordered, start=1)}
            chord_groups: dict[str, list[TemporalEvent]] = {}
            for event_index, event in enumerate(measure.events):
                event_path = f"{path}.events[{event_index}]"
                if not event.id or event.id in event_ids:
                    issues.append(
                        TemporalValidationIssue(
                            "TEMPORAL_EVENT_ID", event_path, "duplicate/empty ID"
                        )
                    )
                event_ids.add(event.id)
                if (
                    event.onset < 0
                    or event.duration < 0
                    or event.onset + event.duration > measure.extent
                ):
                    issues.append(
                        TemporalValidationIssue(
                            "TEMPORAL_EVENT_TIME", event_path, "outside measure"
                        )
                    )
                if event.score_onset != measure.score_onset + event.onset:
                    issues.append(
                        TemporalValidationIssue(
                            "TEMPORAL_EVENT_SCORE_TIME", event_path, "wrong onset"
                        )
                    )
                if event.semantic_order != semantic_orders[event.id]:
                    issues.append(
                        TemporalValidationIssue(
                            "TEMPORAL_SEMANTIC_ORDER", event_path, "wrong order"
                        )
                    )
                if event.staff not in measure.staves or event.voice not in measure.voices:
                    issues.append(
                        TemporalValidationIssue(
                            "TEMPORAL_EVENT_SCOPE", event_path, "unknown staff/voice"
                        )
                    )
                if event.instrument_id != (
                    event.instrument_ids[0] if event.instrument_ids else None
                ) or any(not item or item not in instrument_ids for item in event.instrument_ids):
                    issues.append(
                        TemporalValidationIssue("TEMPORAL_INSTRUMENT_REF", event_path, "unknown ID")
                    )
                if event.kind == "pitched":
                    if event.pitch is None or not event.sounding_pitches:
                        issues.append(
                            TemporalValidationIssue("TEMPORAL_PITCH", event_path, "missing pitch")
                        )
                    elif event.pitch.step not in {"A", "B", "C", "D", "E", "F", "G"}:
                        issues.append(
                            TemporalValidationIssue("TEMPORAL_PITCH", event_path, "invalid step")
                        )
                elif event.kind in {"rest", "unpitched"}:
                    if event.sounding_pitches or event.pitch is not None:
                        issues.append(
                            TemporalValidationIssue(
                                "TEMPORAL_PITCH", event_path, "unexpected sound"
                            )
                        )
                else:
                    issues.append(
                        TemporalValidationIssue("TEMPORAL_EVENT_KIND", event_path, "unknown kind")
                    )
                if event.written_duration is not None and event.written_duration <= 0:
                    issues.append(
                        TemporalValidationIssue(
                            "TEMPORAL_WRITTEN_TIME", event_path, "invalid value"
                        )
                    )
                if event.display_position is not None and event.display_position.step not in {
                    "A",
                    "B",
                    "C",
                    "D",
                    "E",
                    "F",
                    "G",
                }:
                    issues.append(
                        TemporalValidationIssue(
                            "TEMPORAL_DISPLAY_POSITION", event_path, "invalid step"
                        )
                    )
                if event.normal_dots < 0 or (event.normal_type is None and event.normal_dots):
                    issues.append(
                        TemporalValidationIssue(
                            "TEMPORAL_TIME_MOD", event_path, "invalid normal type"
                        )
                    )
                if event.source_id == "":
                    issues.append(
                        TemporalValidationIssue(
                            "TEMPORAL_SOURCE_ID", event_path, "empty source identity"
                        )
                    )
                if not _valid_editorial(event.editorial):
                    issues.append(
                        TemporalValidationIssue(
                            "TEMPORAL_EDITORIAL", event_path, "invalid editorial information"
                        )
                    )
                if not _valid_presentation(event.presentation):
                    issues.append(
                        TemporalValidationIssue(
                            "TEMPORAL_PRESENTATION", event_path, "invalid presentation style"
                        )
                    )
                if (
                    any(
                        value is not None and not isinstance(value, bool)
                        for value in (
                            event.measure_rest,
                            event.print_object,
                            event.print_leger,
                            event.print_dot,
                            event.print_lyric,
                        )
                    )
                    or event.measure_rest is not None
                    and event.kind != "rest"
                    or event.dynamics is not None
                    and event.dynamics < 0
                ):
                    issues.append(
                        TemporalValidationIssue(
                            "TEMPORAL_EVENT_SOURCE_POLICY",
                            event_path,
                            "invalid event source policy",
                        )
                    )
                if (
                    event.stem not in {None, "down", "up", "double", "none"}
                    or event.written_size not in {None, "full", "cue", "grace-cue", "large"}
                    or any(
                        beam.value
                        not in {"begin", "continue", "end", "forward hook", "backward hook"}
                        or not 1 <= beam.number <= 8
                        or (beam.repeater is not None and not isinstance(beam.repeater, bool))
                        or beam.fan not in {None, "accel", "rit", "none"}
                        or beam.source_id == ""
                        for beam in event.beams
                    )
                    or any(
                        tuplet.action not in {"start", "stop"}
                        or tuplet.number == ""
                        or (tuplet.bracket is not None and not isinstance(tuplet.bracket, bool))
                        or tuplet.placement not in {None, "above", "below"}
                        or tuplet.show_number not in {None, "actual", "both", "none"}
                        or tuplet.show_type not in {None, "actual", "both", "none"}
                        or tuplet.line_shape not in {None, "straight", "curved"}
                        or tuplet.source_id == ""
                        or any(
                            portion is not None
                            and (
                                (portion.number is not None and portion.number < 0)
                                or portion.note_type not in _NOTE_TYPES | {None}
                                or portion.dots < 0
                            )
                            for portion in (tuplet.actual, tuplet.normal)
                        )
                        for tuplet in event.tuplets
                    )
                    or bool(event.accidentals)
                    and event.accidental != event.accidentals[0]
                    or any(
                        accidental.value not in _ACCIDENTAL_VALUES
                        or accidental.size not in {None, "full", "cue", "grace-cue", "large"}
                        or accidental.smufl == ""
                        or not _valid_presentation(accidental.presentation)
                        or any(
                            item is not None and not isinstance(item, bool)
                            for item in (
                                accidental.cautionary,
                                accidental.editorial,
                                accidental.parentheses,
                                accidental.bracket,
                            )
                        )
                        for accidental in event.accidentals
                    )
                    or (
                        event.accidental is not None
                        and (
                            event.accidental.value not in _ACCIDENTAL_VALUES
                            or event.accidental.size
                            not in {None, "full", "cue", "grace-cue", "large"}
                            or event.accidental.smufl == ""
                            or any(
                                item is not None and not isinstance(item, bool)
                                for item in (
                                    event.accidental.cautionary,
                                    event.accidental.editorial,
                                    event.accidental.parentheses,
                                    event.accidental.bracket,
                                )
                            )
                        )
                    )
                ):
                    issues.append(
                        TemporalValidationIssue(
                            "TEMPORAL_WRITTEN_NOTATION", event_path, "invalid written-note detail"
                        )
                    )
                if event.performed_duration is not None and event.performed_duration < 0:
                    issues.append(
                        TemporalValidationIssue(
                            "TEMPORAL_PERFORMED_TIME", event_path, "invalid value"
                        )
                    )
                if event.grace != (event.grace_timing is not None):
                    issues.append(
                        TemporalValidationIssue("TEMPORAL_GRACE", event_path, "timing mismatch")
                    )
                if event.grace:
                    if event.duration != 0 or event.source_duration is not None:
                        issues.append(
                            TemporalValidationIssue("TEMPORAL_GRACE", event_path, "wrong duration")
                        )
                    if (
                        event.grace_timing is not None
                        and event.performed_duration != event.grace_timing.make_time
                    ):
                        issues.append(
                            TemporalValidationIssue(
                                "TEMPORAL_GRACE", event_path, "wrong playback time"
                            )
                        )
                elif (
                    event.source_duration is None
                    or event.source_duration <= 0
                    or event.performed_duration != event.duration
                ):
                    issues.append(
                        TemporalValidationIssue(
                            "TEMPORAL_PERFORMED_TIME", event_path, "wrong duration"
                        )
                    )
                if len({lyric.source_order for lyric in event.lyric_markers}) != len(
                    event.lyric_markers
                ) or any(not _valid_lyric(lyric) for lyric in event.lyric_markers):
                    issues.append(
                        TemporalValidationIssue(
                            "ANNOTATION_LYRIC", event_path, "invalid lyric content"
                        )
                    )
                if event.chord_id is not None:
                    chord_groups.setdefault(event.chord_id, []).append(event)
                notehead = event.notehead_marker
                if notehead is not None and (
                    (notehead.value is None and not notehead.text)
                    or notehead.value == ""
                    or any(
                        segment.kind not in {"display-text", "accidental-text"}
                        for segment in notehead.text
                    )
                ):
                    issues.append(
                        TemporalValidationIssue(
                            "ANNOTATION_NOTEHEAD", event_path, "invalid notehead content"
                        )
                    )
                if len({mark.source_order for mark in event.event_markers}) != len(
                    event.event_markers
                ) or any(
                    mark.kind not in SIMPLE_EVENT_MARKS.get(mark.family, frozenset())
                    or mark.placement not in {None, "above", "below"}
                    or any(
                        value == ""
                        for value in (
                            mark.group_id,
                            mark.mark_type,
                            mark.smufl,
                            mark.line_shape,
                            mark.line_type,
                            mark.number,
                        )
                    )
                    or not _valid_trill_playback(mark.playback)
                    or mark.approach not in {None, "above", "below"}
                    or mark.departure not in {None, "above", "below"}
                    or (mark.tremolo_marks is not None and not 0 <= mark.tremolo_marks <= 8)
                    or (mark.kind == "tremolo" and mark.mark_type not in {"single", "unmeasured"})
                    or (mark.kind == "tremolo" and mark.tremolo_marks is None)
                    or (
                        mark.kind == "tremolo"
                        and mark.mark_type == "unmeasured"
                        and mark.tremolo_marks != 0
                    )
                    or (
                        mark.family != "ornament"
                        and any(
                            value is not None
                            for value in (
                                mark.playback,
                                mark.slash,
                                mark.long,
                                mark.approach,
                                mark.departure,
                                mark.tremolo_marks,
                                mark.bracket,
                                mark.parentheses,
                            )
                        )
                    )
                    or (mark.family != "ornament" and bool(mark.accidentals))
                    or (mark.family != "technical" and mark.technical is not None)
                    or (
                        mark.family != "notation"
                        and any(
                            value is not None
                            for value in (mark.number, mark.print_object, mark.unbroken)
                        )
                    )
                    or (mark.family == "notation" and not _valid_notation_mark(mark))
                    or (
                        mark.family == "dynamic"
                        and any(
                            value is not None
                            for value in (
                                mark.mark_type,
                                mark.line_shape,
                                mark.line_type,
                            )
                        )
                    )
                    or (
                        mark.family == "technical"
                        and not _valid_technical_data(mark.kind, mark.technical)
                    )
                    or (
                        mark.family == "technical"
                        and mark.kind == "handbell"
                        and mark.text
                        not in {
                            "belltree",
                            "damp",
                            "echo",
                            "gyro",
                            "hand martellato",
                            "mallet lift",
                            "mallet table",
                            "martellato",
                            "martellato lift",
                            "muted martellato",
                            "pluck lift",
                            "swing",
                        }
                    )
                    or any(
                        not _valid_ornament_accidental(accidental)
                        for accidental in mark.accidentals
                    )
                    for mark in event.event_markers
                ):
                    issues.append(
                        TemporalValidationIssue(
                            "ANNOTATION_EVENT_MARK", event_path, "invalid event mark"
                        )
                    )
                if any(
                    marker.placement not in {None, "above", "below"}
                    or marker.smufl == ""
                    or marker.source_id == ""
                    or marker.line_type not in {None, "solid", "dashed", "dotted", "wavy"}
                    or marker.orientation not in {None, "over", "under"}
                    or any(
                        value is not None and value < 0
                        for value in (marker.dash_length, marker.space_length)
                    )
                    or marker.time_only == ""
                    or not _valid_trill_playback(marker.playback)
                    or not _valid_bend_sound(marker.bend_sound)
                    or (marker.tremolo_marks is not None and not 0 <= marker.tremolo_marks <= 8)
                    or (marker.kind == "tremolo" and marker.tremolo_marks is None)
                    or (marker.kind != "tremolo" and marker.tremolo_marks is not None)
                    or (
                        marker.kind
                        not in {"hammer-on", "pull-off", "glissando", "slide", "other-notation"}
                        and marker.text is not None
                    )
                    or (
                        marker.kind not in {"notated-tie", "slur", "glissando", "slide"}
                        and marker.line_type is not None
                    )
                    or (
                        marker.kind not in {"notated-tie", "slur"}
                        and any(
                            value is not None
                            for value in (
                                marker.orientation,
                                marker.dash_length,
                                marker.space_length,
                            )
                        )
                    )
                    or (marker.kind != "sounding-tie" and marker.time_only is not None)
                    or (marker.kind != "slide" and marker.bend_sound is not None)
                    or (marker.kind != "other-notation" and marker.print_object is not None)
                    or (
                        marker.kind
                        not in {
                            "notated-tie",
                            "slur",
                            "glissando",
                            "slide",
                            "other-notation",
                        }
                        and marker.source_id is not None
                    )
                    or (
                        marker.kind in {"hammer-on", "pull-off"}
                        and (
                            marker.smufl is not None
                            or marker.playback is not None
                            or bool(marker.accidentals)
                        )
                    )
                    or (
                        marker.kind in {"glissando", "slide"}
                        and (
                            marker.placement is not None
                            or marker.smufl is not None
                            or marker.playback is not None
                            or bool(marker.accidentals)
                        )
                    )
                    or (
                        marker.kind == "other-notation"
                        and (marker.playback is not None or bool(marker.accidentals))
                    )
                    or any(
                        not _valid_ornament_accidental(accidental)
                        for accidental in marker.accidentals
                    )
                    for marker in event.span_markers
                ):
                    issues.append(
                        TemporalValidationIssue(
                            "ANNOTATION_SPAN_MARKER", event_path, "invalid span marker"
                        )
                    )
            for grouping_index, grouping in enumerate(measure.groupings):
                grouping_path = f"{path}.groupings[{grouping_index}]"
                if (
                    grouping.grouping_type not in {"start", "stop", "single"}
                    or not grouping.number
                    or grouping.member_of == ""
                    or grouping.source_id == ""
                    or grouping.source_order <= 0
                    or not Fraction(0) <= grouping.onset <= measure.extent
                    or grouping.score_onset != measure.score_onset + grouping.onset
                    or any(feature.feature_type == "" for feature in grouping.features)
                ):
                    issues.append(
                        TemporalValidationIssue(
                            "TEMPORAL_GROUPING", grouping_path, "invalid analytical grouping"
                        )
                    )
            for chord_id, members in chord_groups.items():
                if len(members) < 2 or not any(member.id == chord_id for member in members):
                    issues.append(
                        TemporalValidationIssue("TEMPORAL_CHORD", path, "incomplete chord group")
                    )
                if len({m.onset for m in members}) != 1:
                    issues.append(
                        TemporalValidationIssue("TEMPORAL_CHORD", path, "chord onset mismatch")
                    )
            divisions, actual_extent = _validate_source_trace(
                measure.attributes, measure.events, measure.cursor_moves, divisions, path, issues
            )
            if measure.extent != actual_extent:
                issues.append(
                    TemporalValidationIssue(
                        "TEMPORAL_MEASURE_EXTENT", path, "trace/extent mismatch"
                    )
                )
            for barline in measure.barlines:
                if not Fraction(0) <= barline.onset <= measure.extent:
                    issues.append(
                        TemporalValidationIssue("TEMPORAL_BARLINE_TIME", path, "outside measure")
                    )
                if (
                    barline.location not in {None, "right", "left", "middle"}
                    or barline.style
                    not in {
                        None,
                        "short",
                        "none",
                        "regular",
                        "dotted",
                        "dashed",
                        "heavy",
                        "light-light",
                        "light-heavy",
                        "heavy-light",
                        "heavy-heavy",
                        "tick",
                    }
                    or barline.repeat_direction not in {None, "backward", "forward"}
                    or barline.repeat_winged
                    not in {
                        None,
                        "none",
                        "straight",
                        "curved",
                        "double-straight",
                        "double-curved",
                    }
                    or (
                        barline.repeat_after_jump is not None
                        and not isinstance(barline.repeat_after_jump, bool)
                    )
                    or barline.ending_type not in {None, "start", "stop", "discontinue"}
                    or (
                        barline.ending_print_object is not None
                        and not isinstance(barline.ending_print_object, bool)
                    )
                    or barline.ending_system_relation not in {None, "only-top", "also-top", "none"}
                    or (barline.divisions is not None and barline.divisions <= 0)
                    or barline.source_id == ""
                    or any(
                        mark.kind not in {"segno", "coda"}
                        or mark.token == ""
                        or mark.source_id == ""
                        or mark.smufl == ""
                        for mark in barline.navigation
                    )
                ):
                    issues.append(
                        TemporalValidationIssue(
                            "TEMPORAL_BARLINE", path, "invalid barline semantics"
                        )
                    )
                if len(barline.fermatas) > 2 or any(
                    fermata.shape
                    not in {
                        None,
                        "normal",
                        "angled",
                        "square",
                        "double-angled",
                        "double-square",
                        "double-dot",
                        "half-curve",
                        "curlew",
                    }
                    or fermata.orientation not in {None, "upright", "inverted"}
                    or fermata.source_id == ""
                    for fermata in barline.fermatas
                ):
                    issues.append(
                        TemporalValidationIssue(
                            "TEMPORAL_BARLINE_FERMATA", path, "invalid barline fermata"
                        )
                    )
            for harmony in measure.harmonies:
                anchor = harmony.anchor
                if (
                    anchor.part_id != part.id
                    or anchor.measure_id != measure.id
                    or anchor.onset < 0
                    or anchor.onset > measure.extent
                    or anchor.score_onset != measure.score_onset + anchor.onset
                    or anchor.staff not in measure.staves
                    or not _valid_harmony(harmony)
                ):
                    issues.append(
                        TemporalValidationIssue(
                            "ANNOTATION_HARMONY", path, "invalid harmony anchor or value"
                        )
                    )
            for direction in measure.directions:
                anchor = direction.anchor
                identifiers = (
                    direction.group_id,
                    direction.direction_id,
                    direction.direction_type_id,
                    direction.source_id,
                )
                if (
                    anchor.part_id != part.id
                    or anchor.measure_id != measure.id
                    or anchor.onset < 0
                    or anchor.onset > measure.extent
                    or anchor.score_onset != measure.score_onset + anchor.onset
                    or anchor.staff not in measure.staves
                    or (anchor.voice is not None and anchor.voice not in measure.voices)
                    or direction.family
                    not in {
                        "words",
                        "rehearsal",
                        "dynamic",
                        "segno",
                        "coda",
                        "symbol",
                        "damp",
                        "damp-all",
                        "eyeglasses",
                        "string-mute",
                        "staff-divide",
                        "other-direction",
                        "metronome",
                        "harp-pedals",
                        "scordatura",
                        "accordion-registration",
                        "principal-voice",
                        "percussion",
                        "image",
                        "pedal",
                    }
                    or (direction.family in {"dynamic", "symbol"} and not direction.value)
                    or (direction.family == "string-mute" and direction.value not in {"on", "off"})
                    or (
                        direction.family == "pedal"
                        and (
                            direction.value not in {"start", "sostenuto", "stop"}
                            or not direction.pedal_number
                            or direction.pedal_line is True
                            or direction.pedal_sign is False
                        )
                    )
                    or (
                        direction.family == "staff-divide"
                        and direction.value not in {"down", "up", "up-down"}
                    )
                    or any(value == "" for value in identifiers)
                    or direction.smufl == ""
                    or direction.system_relation not in {None, "only-top", "also-top", "none"}
                    or (
                        direction.print_object is not None
                        and not isinstance(direction.print_object, bool)
                    )
                    or (direction.family != "dynamic" and direction.group_id is not None)
                    or (
                        direction.family not in {"dynamic", "segno", "coda", "other-direction"}
                        and direction.smufl is not None
                    )
                    or (
                        direction.family not in {"other-direction", "metronome"}
                        and direction.print_object is not None
                    )
                    or (
                        direction.family
                        in {
                            "metronome",
                            "harp-pedals",
                            "scordatura",
                            "accordion-registration",
                            "principal-voice",
                            "percussion",
                            "image",
                        }
                        and not _valid_complex_direction(direction.family, direction.data)
                    )
                    or (
                        direction.family
                        not in {
                            "metronome",
                            "harp-pedals",
                            "scordatura",
                            "accordion-registration",
                            "principal-voice",
                            "percussion",
                            "image",
                        }
                        and direction.data is not None
                    )
                    or any(
                        value is not None and not isinstance(value, bool)
                        for value in (
                            direction.pedal_line,
                            direction.pedal_sign,
                            direction.pedal_abbreviated,
                        )
                    )
                    or (
                        direction.family != "pedal"
                        and any(
                            value is not None
                            for value in (
                                direction.pedal_number,
                                direction.pedal_line,
                                direction.pedal_sign,
                                direction.pedal_abbreviated,
                            )
                        )
                    )
                    or not _valid_presentation(direction.presentation)
                    or (
                        direction.directive is not None
                        and not isinstance(direction.directive, bool)
                    )
                ):
                    issues.append(
                        TemporalValidationIssue(
                            "ANNOTATION_DIRECTION", path, "invalid direction anchor or value"
                        )
                    )
            for marker in measure.time_span_markers:
                span_anchor = marker.anchor
                expected_source_types = {
                    "wedge": {"crescendo", "diminuendo", "continue", "stop"},
                    "dashes": {"start", "continue", "stop"},
                    "bracket": {"start", "continue", "stop"},
                    "pedal": {
                        "start",
                        "stop",
                        "sostenuto",
                        "change",
                        "continue",
                        "discontinue",
                        "resume",
                    },
                    "octave-shift": {"up", "down", "continue", "stop"},
                }
                if (
                    marker.kind not in {"wedge", "dashes", "bracket", "pedal", "octave-shift"}
                    or marker.action not in {"start", "continue", "stop"}
                    or (marker.action == "start") != (marker.opening is not None)
                    or marker.source_type not in expected_source_types.get(marker.kind, set())
                    or marker.inferred
                    or marker.inference_reason is not None
                    or (marker.opening is not None and marker.opening != marker.source_type)
                    or span_anchor.part_id != part.id
                    or span_anchor.measure_id != measure.id
                    or span_anchor.onset < 0
                    or span_anchor.onset > measure.extent
                    or span_anchor.score_onset != measure.score_onset + span_anchor.onset
                    or span_anchor.staff not in measure.staves
                    or (span_anchor.voice is not None and span_anchor.voice not in measure.voices)
                    or any(
                        value == ""
                        for value in (
                            marker.direction_id,
                            marker.direction_type_id,
                            marker.source_id,
                        )
                    )
                    or marker.system_relation not in {None, "only-top", "also-top", "none"}
                    or marker.line_type not in {None, "solid", "dashed", "dotted", "wavy"}
                    or any(
                        value is not None and value < 0
                        for value in (
                            marker.dash_length,
                            marker.space_length,
                            marker.spread,
                            marker.end_length,
                        )
                    )
                    or marker.line_end not in {None, "up", "down", "both", "arrow", "none"}
                    or any(
                        value is not None and not isinstance(value, bool)
                        for value in (
                            marker.niente,
                            marker.pedal_line,
                            marker.pedal_sign,
                            marker.pedal_abbreviated,
                        )
                    )
                    or (marker.octave_size is not None and marker.octave_size < 1)
                    or (
                        marker.kind != "wedge"
                        and (marker.spread is not None or marker.niente is not None)
                    )
                    or (
                        marker.kind != "bracket"
                        and (marker.line_end is not None or marker.end_length is not None)
                    )
                    or (
                        marker.kind != "pedal"
                        and any(
                            value is not None
                            for value in (
                                marker.pedal_line,
                                marker.pedal_sign,
                                marker.pedal_abbreviated,
                            )
                        )
                    )
                    or (marker.kind != "octave-shift" and marker.octave_size is not None)
                    or (marker.directive is not None and not isinstance(marker.directive, bool))
                ):
                    issues.append(
                        TemporalValidationIssue(
                            "ANNOTATION_TIME_SPAN", path, "invalid time-span marker"
                        )
                    )
            measure_events = {event.id: event for event in measure.events}
            for bass in measure.figured_bass:
                bass_anchor = bass.anchor
                target = measure_events.get(bass_anchor.event_id)
                if (
                    bass_anchor.part_id != part.id
                    or bass_anchor.measure_id != measure.id
                    or target is None
                    or target.grace
                    or (target.chord_id is not None and target.chord_id != target.id)
                    or bass_anchor.staff != target.staff
                    or bass_anchor.voice != target.voice
                    or bass_anchor.score_onset != target.score_onset
                    or not bass.figures
                    or (bass.duration is not None and bass.duration <= 0)
                    or bass.placement not in {None, "above", "below"}
                    or bass.source_id == ""
                    or not _valid_presentation(bass.presentation)
                    or any(
                        value is not None and not isinstance(value, bool)
                        for value in (
                            bass.parentheses,
                            bass.print_object,
                            bass.print_dot,
                            bass.print_spacing,
                        )
                    )
                    or any(
                        figure.extend not in {None, "start", "continue", "stop"}
                        or (figure.extend is not None and not figure.extend_present)
                        or (
                            not figure.extend_present
                            and figure.prefix is None
                            and figure.number is None
                            and figure.suffix is None
                        )
                        for figure in bass.figures
                    )
                ):
                    issues.append(
                        TemporalValidationIssue(
                            "ANNOTATION_FIGURED_BASS", path, "invalid figured-bass anchor or value"
                        )
                    )
            transpositions = _validate_sounding(
                measure.attributes, measure.events, transpositions, path, issues
            )
            score_cursor += measure.extent
    expected = tuple(
        (onset, tuple(members)) for onset, members in sorted(alignment_members.items())
    )
    actual = tuple((alignment.onset, alignment.measures) for alignment in score.alignments)
    if actual != expected:
        issues.append(
            TemporalValidationIssue("TEMPORAL_ALIGNMENT", "score.alignments", "alignment mismatch")
        )
    try:
        expected_graph = resolve_annotation_graph(score.parts, score.metadata)
    except AnnotationGraphError as error:
        issues.append(
            TemporalValidationIssue("ANNOTATION_SPAN_STATE", "score.annotations", str(error))
        )
    else:
        if score.annotations != expected_graph:
            issues.append(
                TemporalValidationIssue(
                    "ANNOTATION_SPAN_GRAPH", "score.annotations", "span graph mismatch"
                )
            )
    return tuple(issues)


def validate_deferred_constructs(
    deferred: tuple[DeferredConstruct, ...],
) -> tuple[TemporalValidationIssue, ...]:
    issues: list[TemporalValidationIssue] = []
    seen: set[tuple[str, str]] = set()
    for index, item in enumerate(deferred):
        path = f"deferred[{index}]"
        key = (item.path, item.tag)
        if not item.path or not item.tag or item.occurrences <= 0 or key in seen:
            issues.append(
                TemporalValidationIssue("TEMPORAL_DEFERRED", path, "invalid/duplicate audit item")
            )
        seen.add(key)
    return tuple(issues)


def _validate_source_trace(
    attributes: tuple[TemporalAttributes, ...],
    events: tuple[TemporalEvent, ...],
    moves: tuple[TemporalCursorMove, ...],
    initial_divisions: int | None,
    path: str,
    issues: list[TemporalValidationIssue],
) -> tuple[int | None, Fraction]:
    cursor = Fraction(0)
    extent = Fraction(0)
    divisions = initial_divisions
    sequence: list[tuple[int, TemporalAttributes | TemporalEvent | TemporalCursorMove]] = []
    sequence.extend((item.source_order, item) for item in attributes)
    sequence.extend((item.source_order, item) for item in events)
    sequence.extend((item.source_order, item) for item in moves)
    if len({order for order, _item in sequence}) != len(sequence):
        issues.append(
            TemporalValidationIssue("TEMPORAL_SOURCE_ORDER", path, "duplicate source order")
        )
    for _order, item in sorted(sequence, key=lambda row: row[0]):
        if isinstance(item, TemporalAttributes):
            if item.onset != cursor:
                issues.append(
                    TemporalValidationIssue("TEMPORAL_ATTRIBUTE_TIME", path, "cursor mismatch")
                )
            if item.divisions is not None:
                if item.divisions <= 0:
                    issues.append(
                        TemporalValidationIssue("TEMPORAL_DIVISIONS", path, "nonpositive divisions")
                    )
                divisions = item.divisions
            if any(not _valid_measure_style(style) for style in item.measure_styles):
                issues.append(
                    TemporalValidationIssue(
                        "TEMPORAL_MEASURE_STYLE", path, "invalid repeat/slash notation"
                    )
                )
            if not _valid_attributes(item):
                issues.append(
                    TemporalValidationIssue(
                        "TEMPORAL_ATTRIBUTES", path, "invalid key/time/clef or staff state"
                    )
                )
        elif isinstance(item, TemporalCursorMove):
            if item.before != cursor or item.kind not in {"backup", "forward"}:
                issues.append(TemporalValidationIssue("TEMPORAL_CURSOR", path, "cursor mismatch"))
            if not _valid_editorial(item.editorial):
                issues.append(
                    TemporalValidationIssue(
                        "TEMPORAL_EDITORIAL", path, "invalid cursor editorial information"
                    )
                )
            effective_divisions = divisions or 1
            delta = Fraction(item.source_duration, effective_divisions)
            expected = cursor + (-delta if item.kind == "backup" else delta)
            recovered = item.kind == "backup" and expected < 0 and cursor > 0
            if item.underflow_recovered != recovered or item.after != (
                Fraction(0) if recovered else expected
            ):
                issues.append(TemporalValidationIssue("TEMPORAL_CURSOR", path, "wrong cursor move"))
            cursor = item.after
            extent = max(extent, cursor)
        else:
            follower = item.chord_id is not None and item.id != item.chord_id
            if not follower and item.onset != cursor:
                issues.append(
                    TemporalValidationIssue("TEMPORAL_CURSOR", path, "note onset mismatch")
                )
            effective_divisions = divisions or 1
            if item.source_duration is not None and item.duration != Fraction(
                item.source_duration, effective_divisions
            ):
                issues.append(
                    TemporalValidationIssue("TEMPORAL_SOURCE_DURATION", path, "wrong duration")
                )
            if not follower:
                cursor = item.onset + item.duration
            extent = max(extent, cursor, item.onset + item.duration)
    return divisions, extent


def _validate_sounding(
    attributes: tuple[TemporalAttributes, ...],
    events: tuple[TemporalEvent, ...],
    initial: dict[str | None, TemporalTransposition],
    path: str,
    issues: list[TemporalValidationIssue],
) -> dict[str | None, TemporalTransposition]:
    changes = sorted(
        (
            (attribute.onset, attribute.source_order, transposition)
            for attribute in attributes
            for transposition in attribute.transpositions
        ),
        key=lambda item: (item[0], item[1]),
    )

    def apply(
        state: dict[str | None, TemporalTransposition], change: TemporalTransposition
    ) -> None:
        if change.staff is None:
            state.clear()
        state[change.staff] = change

    for event in events:
        if event.pitch is None or event.kind != "pitched":
            continue
        if event.pitch.step not in {"A", "B", "C", "D", "E", "F", "G"}:
            continue
        state = initial.copy()
        for onset, _order, change in changes:
            if onset > event.onset:
                break
            apply(state, change)
        expected = resolve_sounding_pitches(event.pitch, state.get(event.staff, state.get(None)))
        if event.sounding_pitches != expected:
            issues.append(
                TemporalValidationIssue("TEMPORAL_SOUNDING_PITCH", path, "derived pitch mismatch")
            )
    final = initial.copy()
    for _onset, _order, change in changes:
        apply(final, change)
    return final
