"""Independent semantic comparison for canonical notation projections."""

from __future__ import annotations

from dataclasses import dataclass, fields, is_dataclass
from fractions import Fraction
from typing import Any

from teachmemusic.score.v2.annotations import (
    BendSound,
    ComplexDirectionData,
    DirectionMark,
    EventMarkMarker,
    NoteheadMarker,
    OrnamentAccidental,
    SpanMarker,
    TimeAnchor,
    TimeSpanMarker,
    TrillPlayback,
)
from teachmemusic.score.v2.documents import (
    CanonicalMusicPackage,
    CanonicalScoreContent,
    ScoreDocument,
)
from teachmemusic.score.v2.playback import SoundDirective
from teachmemusic.score.v2.presentation import PresentationStyle
from teachmemusic.score.v2.temporal import TemporalEvent, TemporalScore


@dataclass(frozen=True, slots=True)
class RenderEquivalenceIssue:
    """One semantic mismatch after generated MusicXML is re-ingested."""

    code: str
    path: str
    expected: str
    actual: str


class RenderEquivalenceError(ValueError):
    """Raised when generated renderer input changes represented score facts."""

    def __init__(self, issues: tuple[RenderEquivalenceIssue, ...]) -> None:
        self.issues = issues
        first = issues[0]
        super().__init__(
            f"{first.code} at {first.path}: expected {first.expected}, got {first.actual}"
        )


@dataclass(frozen=True, slots=True)
class _LyricFact:
    number: str | None
    syllabic: str | None
    text: str
    print_object: bool | None


@dataclass(frozen=True, slots=True)
class _AccidentalFact:
    value: str
    cautionary: bool | None
    editorial: bool | None
    parentheses: bool | None
    bracket: bool | None
    size: str | None
    smufl: str | None


@dataclass(frozen=True, slots=True)
class _TupletPortionFact:
    number: int | None
    note_type: str | None
    dots: int


@dataclass(frozen=True, slots=True)
class _TupletFact:
    number: str
    action: str
    bracket: bool | None
    placement: str | None
    show_number: str | None
    show_type: str | None
    line_shape: str | None
    actual: _TupletPortionFact | None
    normal: _TupletPortionFact | None


@dataclass(frozen=True, slots=True)
class _GraceFact:
    slash: bool | None
    make_time: Fraction | None
    steal_previous_percent: Fraction | None
    steal_following_percent: Fraction | None


@dataclass(frozen=True, slots=True)
class _SpanEndpointFact:
    anchor: tuple[int, int, int]
    action: str
    source_order: int
    placement: str | None
    smufl: str | None
    playback: TrillPlayback | None
    tremolo_marks: int | None
    accidentals: tuple[OrnamentAccidental, ...]
    text: str | None
    source_id: str | None
    line_type: str | None
    bend_sound: BendSound | None
    print_object: bool | None
    orientation: str | None
    dash_length: Fraction | None
    space_length: Fraction | None
    time_only: str | None


@dataclass(frozen=True, slots=True)
class _SpanFact:
    kind: str
    number: str
    endpoints: tuple[_SpanEndpointFact, ...]


@dataclass(frozen=True, slots=True)
class _EventFact:
    kind: str
    onset: Fraction
    duration: Fraction
    staff: str
    voice: str
    chord_group: int | None
    pitch: tuple[str, Fraction, int] | None
    written_type: str | None
    dots: int
    stem: str | None
    measure_rest: bool | None
    beams: tuple[tuple[int, str, bool | None, str | None], ...]
    time_modification: tuple[int, int] | None
    normal_type: str | None
    normal_dots: int
    tuplets: tuple[_TupletFact, ...]
    grace: _GraceFact | None
    accidental: _AccidentalFact | None
    notehead: NoteheadMarker | None
    span_markers: tuple[SpanMarker, ...]
    event_markers: tuple[EventMarkMarker, ...]
    lyrics: tuple[_LyricFact, ...]


@dataclass(frozen=True, slots=True)
class _AttributeFact:
    onset: Fraction
    staves: int | None
    keys: tuple[tuple[int | None, str | None, str | None, int | None], ...]
    times: tuple[tuple[tuple[str, ...], tuple[int, ...], str | None, str | None], ...]
    clefs: tuple[tuple[str, str, int | None, int | None], ...]


@dataclass(frozen=True, slots=True)
class _BarlineFact:
    onset: Fraction
    location: str | None
    style: str | None
    repeat_direction: str | None
    repeat_times: str | None
    repeat_winged: str | None
    repeat_after_jump: bool | None
    ending_number: str | None
    ending_type: str | None
    ending_text: str | None
    ending_print_object: bool | None
    ending_system_relation: str | None
    fermatas: tuple[tuple[str | None, str | None, str | None], ...]
    navigation: tuple[tuple[str, str | None, str | None, str | None], ...]
    divisions: Fraction | None
    source_id: str | None


@dataclass(frozen=True, slots=True)
class _HarmonyFact:
    onset: Fraction
    staff: str | None
    root_step: str | None
    root_alter: Fraction
    kind: str
    kind_text: str | None
    print_object: bool | None
    print_frame: bool | None


@dataclass(frozen=True, slots=True)
class _TimeAnchorFact:
    part: int
    measure: int
    onset: Fraction
    staff: str | None
    voice: str | None


@dataclass(frozen=True, slots=True)
class _DirectionFact:
    anchor: _TimeAnchorFact
    family: str
    value: str
    placement: str | None
    source_group: int
    component_order: int
    group_id: str | None
    smufl: str | None
    direction_id: str | None
    direction_type_id: str | None
    source_id: str | None
    print_object: bool | None
    system_relation: str | None
    data: ComplexDirectionData | None
    presentation: PresentationStyle | None
    directive: bool | None
    pedal_number: str | None
    pedal_line: bool | None
    pedal_sign: bool | None
    pedal_abbreviated: bool | None


@dataclass(frozen=True, slots=True)
class _TimeSpanMarkerFact:
    anchor: _TimeAnchorFact
    kind: str
    number: str
    action: str
    opening: str | None
    source_group: int
    component_order: int
    direction_id: str | None
    direction_type_id: str | None
    source_id: str | None
    system_relation: str | None
    source_type: str | None
    line_type: str | None
    dash_length: Fraction | None
    space_length: Fraction | None
    spread: Fraction | None
    niente: bool | None
    line_end: str | None
    end_length: Fraction | None
    pedal_line: bool | None
    pedal_sign: bool | None
    pedal_abbreviated: bool | None
    octave_size: int | None
    directive: bool | None
    inferred: bool
    inference_reason: str | None


@dataclass(frozen=True, slots=True)
class _TimeSpanFact:
    kind: str
    number: str
    opening: str | None
    endpoints: tuple[_TimeSpanMarkerFact, ...]


@dataclass(frozen=True, slots=True)
class _SoundFact:
    onset: Fraction
    source_group: int
    tempo: Fraction | None
    dynamics: Fraction | None
    dacapo: bool | None
    segno: str | None
    dalsegno: str | None
    coda: str | None
    tocoda: str | None
    forward_repeat: bool | None
    fine: str | None
    time_only: str | None
    source_id: str | None


@dataclass(frozen=True, slots=True)
class _MeasureFact:
    number: str
    ordinal: int
    implicit: bool
    extent: Fraction
    attributes: tuple[_AttributeFact, ...]
    events: tuple[_EventFact, ...]
    harmonies: tuple[_HarmonyFact, ...]
    directions: tuple[_DirectionFact, ...]
    time_span_markers: tuple[_TimeSpanMarkerFact, ...]
    barlines: tuple[_BarlineFact, ...]
    sounds: tuple[_SoundFact, ...]
    new_system: bool | None
    new_page: bool | None


@dataclass(frozen=True, slots=True)
class _PartFact:
    name: str | None
    abbreviation: str | None
    instruments: tuple[tuple[str | None, str | None, str | None], ...]
    staves: tuple[str, ...]
    voices: tuple[str, ...]
    measures: tuple[_MeasureFact, ...]


@dataclass(frozen=True, slots=True)
class _ScoreFact:
    work_title: str | None
    movement_title: str | None
    movement_number: str | None
    creators: tuple[tuple[str | None, str], ...]
    parts: tuple[_PartFact, ...]
    spans: tuple[_SpanFact, ...]
    time_spans: tuple[_TimeSpanFact, ...]


def compare_render_equivalence(
    source_document: ScoreDocument,
    reparsed_package: CanonicalMusicPackage,
) -> tuple[RenderEquivalenceIssue, ...]:
    """Compare all facts represented by the Task 5B.1 MusicXML projection."""

    source_score = _complete_score(source_document)
    generated_documents = [
        item for item in reparsed_package.documents if isinstance(item, ScoreDocument)
    ]
    if len(generated_documents) != 1:
        return (
            RenderEquivalenceIssue(
                "VIEWER_RENDER_REPARSE_DOCUMENTS",
                "documents",
                "one generated score document",
                f"{len(generated_documents)} generated score documents",
            ),
        )
    generated_score = _complete_score(generated_documents[0])
    issues: list[RenderEquivalenceIssue] = []
    _diff(_project(source_score), _project(generated_score), "score", issues)
    return tuple(issues)


def require_render_equivalent(
    source_document: ScoreDocument,
    reparsed_package: CanonicalMusicPackage,
) -> None:
    """Raise if renderer interchange changes any represented canonical fact."""

    issues = compare_render_equivalence(source_document, reparsed_package)
    if issues:
        raise RenderEquivalenceError(issues)


def _complete_score(document: ScoreDocument) -> TemporalScore:
    if not isinstance(document.content, CanonicalScoreContent):
        raise ValueError("render equivalence requires complete canonical score content")
    return document.content.score


def _project(score: TemporalScore) -> _ScoreFact:
    event_locations = {
        event.id: (part_index, measure_index, event_index)
        for part_index, part in enumerate(score.parts)
        for measure_index, measure in enumerate(part.measures)
        for event_index, event in enumerate(measure.events)
    }
    measure_locations = {
        measure.id: (part_index, measure_index)
        for part_index, part in enumerate(score.parts)
        for measure_index, measure in enumerate(part.measures)
    }
    source_orders: dict[str, set[int]] = {
        measure.id: {item.source_order for item in measure.directions}
        | {item.source_order for item in measure.time_span_markers}
        for part in score.parts
        for measure in part.measures
    }
    for span in score.annotations.time_spans:
        for endpoint in span.endpoints:
            source_orders[endpoint.anchor.measure_id].add(endpoint.source_order)
    source_ranks = {
        measure_id: {
            source_order: rank for rank, source_order in enumerate(sorted(orders), start=1)
        }
        for measure_id, orders in source_orders.items()
    }
    return _ScoreFact(
        work_title=score.work_title,
        movement_title=score.movement_title,
        movement_number=score.movement_number,
        creators=score.creators,
        parts=tuple(
            _PartFact(
                name=part.name,
                abbreviation=part.abbreviation,
                instruments=tuple(
                    (instrument.name, instrument.abbreviation, instrument.sound)
                    for instrument in part.instruments
                ),
                staves=tuple(staff.source_number for staff in part.staves),
                voices=tuple(voice.source_id for voice in part.voices),
                measures=tuple(
                    _MeasureFact(
                        number=measure.number,
                        ordinal=measure.ordinal,
                        implicit=measure.implicit,
                        extent=measure.extent,
                        attributes=tuple(
                            _AttributeFact(
                                onset=attributes.onset,
                                staves=attributes.staves,
                                keys=tuple(
                                    (key.fifths, key.mode, key.staff, key.cancel)
                                    for key in attributes.keys
                                ),
                                times=tuple(
                                    (time.beats, time.beat_types, time.symbol, time.staff)
                                    for time in attributes.times
                                ),
                                clefs=tuple(
                                    (clef.staff, clef.sign, clef.line, clef.octave_change)
                                    for clef in attributes.clefs
                                ),
                            )
                            for attributes in measure.attributes
                        ),
                        events=_event_facts(measure.events),
                        harmonies=tuple(
                            _HarmonyFact(
                                onset=harmony.anchor.onset,
                                staff=harmony.anchor.staff,
                                root_step=harmony.root_step,
                                root_alter=harmony.root_alter,
                                kind=harmony.kind,
                                kind_text=harmony.kind_text,
                                print_object=harmony.print_object,
                                print_frame=harmony.print_frame,
                            )
                            for harmony in measure.harmonies
                        ),
                        directions=tuple(
                            _direction_fact(
                                direction,
                                measure_locations,
                                source_ranks[measure.id],
                            )
                            for direction in measure.directions
                        ),
                        time_span_markers=tuple(
                            _time_span_marker_fact(
                                marker,
                                measure_locations,
                                source_ranks[measure.id],
                            )
                            for marker in measure.time_span_markers
                        ),
                        barlines=tuple(
                            _BarlineFact(
                                onset=barline.onset,
                                location=barline.location,
                                style=barline.style,
                                repeat_direction=barline.repeat_direction,
                                repeat_times=barline.repeat_times,
                                repeat_winged=barline.repeat_winged,
                                repeat_after_jump=barline.repeat_after_jump,
                                ending_number=barline.ending_number,
                                ending_type=barline.ending_type,
                                ending_text=barline.ending_text,
                                ending_print_object=barline.ending_print_object,
                                ending_system_relation=barline.ending_system_relation,
                                fermatas=tuple(
                                    (item.shape, item.orientation, item.source_id)
                                    for item in barline.fermatas
                                ),
                                navigation=tuple(
                                    (item.kind, item.token, item.source_id, item.smufl)
                                    for item in barline.navigation
                                ),
                                divisions=barline.divisions,
                                source_id=barline.source_id,
                            )
                            for barline in measure.barlines
                        ),
                        sounds=tuple(
                            _sound_fact(sound, measure.sounds) for sound in measure.sounds
                        ),
                        new_system=(
                            measure.layout.new_system if measure.layout is not None else None
                        ),
                        new_page=measure.layout.new_page if measure.layout is not None else None,
                    )
                    for measure in part.measures
                ),
            )
            for part in score.parts
        ),
        spans=tuple(
            _SpanFact(
                kind=span.kind,
                number=span.number,
                endpoints=tuple(
                    _SpanEndpointFact(
                        anchor=event_locations[endpoint.anchor.event_id],
                        action=endpoint.action,
                        source_order=endpoint.source_order,
                        placement=endpoint.placement,
                        smufl=endpoint.smufl,
                        playback=endpoint.playback,
                        tremolo_marks=endpoint.tremolo_marks,
                        accidentals=endpoint.accidentals,
                        text=endpoint.text,
                        source_id=endpoint.source_id,
                        line_type=endpoint.line_type,
                        bend_sound=endpoint.bend_sound,
                        print_object=endpoint.print_object,
                        orientation=endpoint.orientation,
                        dash_length=endpoint.dash_length,
                        space_length=endpoint.space_length,
                        time_only=endpoint.time_only,
                    )
                    for endpoint in span.endpoints
                ),
            )
            for span in score.annotations.spans
        ),
        time_spans=tuple(
            _TimeSpanFact(
                kind=span.kind,
                number=span.number,
                opening=span.opening,
                endpoints=tuple(
                    _time_span_marker_fact(
                        endpoint,
                        measure_locations,
                        source_ranks[endpoint.anchor.measure_id],
                    )
                    for endpoint in span.endpoints
                ),
            )
            for span in score.annotations.time_spans
        ),
    )


def _time_anchor_fact(
    anchor: TimeAnchor,
    measure_locations: dict[str, tuple[int, int]],
) -> _TimeAnchorFact:
    part_index, measure_index = measure_locations[anchor.measure_id]
    return _TimeAnchorFact(
        part=part_index,
        measure=measure_index,
        onset=anchor.onset,
        staff=anchor.staff,
        voice=anchor.voice,
    )


def _direction_fact(
    direction: DirectionMark,
    measure_locations: dict[str, tuple[int, int]],
    source_ranks: dict[int, int],
) -> _DirectionFact:
    return _DirectionFact(
        anchor=_time_anchor_fact(direction.anchor, measure_locations),
        family=direction.family,
        value=direction.value,
        placement=direction.placement,
        source_group=source_ranks[direction.source_order],
        component_order=direction.component_order,
        group_id=direction.group_id,
        smufl=direction.smufl,
        direction_id=direction.direction_id,
        direction_type_id=direction.direction_type_id,
        source_id=direction.source_id,
        print_object=direction.print_object,
        system_relation=direction.system_relation,
        data=direction.data,
        presentation=direction.presentation,
        directive=direction.directive,
        pedal_number=direction.pedal_number,
        pedal_line=direction.pedal_line,
        pedal_sign=direction.pedal_sign,
        pedal_abbreviated=direction.pedal_abbreviated,
    )


def _time_span_marker_fact(
    marker: TimeSpanMarker,
    measure_locations: dict[str, tuple[int, int]],
    source_ranks: dict[int, int],
) -> _TimeSpanMarkerFact:
    return _TimeSpanMarkerFact(
        anchor=_time_anchor_fact(marker.anchor, measure_locations),
        kind=marker.kind,
        number=marker.number,
        action=marker.action,
        opening=marker.opening,
        source_group=source_ranks[marker.source_order],
        component_order=marker.component_order,
        direction_id=marker.direction_id,
        direction_type_id=marker.direction_type_id,
        source_id=marker.source_id,
        system_relation=marker.system_relation,
        source_type=marker.source_type,
        line_type=marker.line_type,
        dash_length=marker.dash_length,
        space_length=marker.space_length,
        spread=marker.spread,
        niente=marker.niente,
        line_end=marker.line_end,
        end_length=marker.end_length,
        pedal_line=marker.pedal_line,
        pedal_sign=marker.pedal_sign,
        pedal_abbreviated=marker.pedal_abbreviated,
        octave_size=marker.octave_size,
        directive=marker.directive,
        inferred=marker.inferred,
        inference_reason=marker.inference_reason,
    )


def _sound_fact(
    sound: SoundDirective,
    measure_sounds: tuple[SoundDirective, ...],
) -> _SoundFact:
    order_ranks = {
        source_order: rank
        for rank, source_order in enumerate(
            sorted({item.source_order for item in measure_sounds}), start=1
        )
    }
    return _SoundFact(
        onset=sound.onset,
        source_group=order_ranks[sound.source_order],
        tempo=sound.tempo,
        dynamics=sound.dynamics,
        dacapo=sound.dacapo,
        segno=sound.segno,
        dalsegno=sound.dalsegno,
        coda=sound.coda,
        tocoda=sound.tocoda,
        forward_repeat=sound.forward_repeat,
        fine=sound.fine,
        time_only=sound.time_only,
        source_id=sound.source_id,
    )


def _event_facts(events: tuple[TemporalEvent, ...]) -> tuple[_EventFact, ...]:
    chord_groups: dict[str, int] = {}
    for event in events:
        if event.chord_id is not None and event.chord_id not in chord_groups:
            chord_groups[event.chord_id] = len(chord_groups)
    return tuple(
        _EventFact(
            kind=event.kind,
            onset=event.onset,
            duration=event.duration,
            staff=event.staff,
            voice=event.voice,
            chord_group=(chord_groups[event.chord_id] if event.chord_id is not None else None),
            pitch=(
                (event.pitch.step, event.pitch.alter, event.pitch.octave)
                if event.pitch is not None
                else None
            ),
            written_type=event.written_type,
            dots=event.dots,
            stem=event.stem,
            measure_rest=event.measure_rest,
            beams=tuple((beam.number, beam.value, beam.repeater, beam.fan) for beam in event.beams),
            time_modification=event.time_modification,
            normal_type=event.normal_type,
            normal_dots=event.normal_dots,
            tuplets=tuple(
                _TupletFact(
                    number=tuplet.number,
                    action=tuplet.action,
                    bracket=tuplet.bracket,
                    placement=tuplet.placement,
                    show_number=tuplet.show_number,
                    show_type=tuplet.show_type,
                    line_shape=tuplet.line_shape,
                    actual=(
                        _TupletPortionFact(
                            number=tuplet.actual.number,
                            note_type=tuplet.actual.note_type,
                            dots=tuplet.actual.dots,
                        )
                        if tuplet.actual is not None
                        else None
                    ),
                    normal=(
                        _TupletPortionFact(
                            number=tuplet.normal.number,
                            note_type=tuplet.normal.note_type,
                            dots=tuplet.normal.dots,
                        )
                        if tuplet.normal is not None
                        else None
                    ),
                )
                for tuplet in event.tuplets
            ),
            grace=(
                _GraceFact(
                    slash=event.grace_timing.slash,
                    make_time=event.grace_timing.make_time,
                    steal_previous_percent=event.grace_timing.steal_previous_percent,
                    steal_following_percent=event.grace_timing.steal_following_percent,
                )
                if event.grace_timing is not None
                else None
            ),
            accidental=(
                _AccidentalFact(
                    value=event.accidental.value,
                    cautionary=event.accidental.cautionary,
                    editorial=event.accidental.editorial,
                    parentheses=event.accidental.parentheses,
                    bracket=event.accidental.bracket,
                    size=event.accidental.size,
                    smufl=event.accidental.smufl,
                )
                if event.accidental is not None
                else None
            ),
            notehead=event.notehead_marker,
            span_markers=event.span_markers,
            event_markers=event.event_markers,
            lyrics=tuple(
                _LyricFact(
                    number=lyric.number,
                    syllabic=lyric.syllabic,
                    text=lyric.text,
                    print_object=lyric.print_object,
                )
                for lyric in event.lyric_markers
            ),
        )
        for event in events
    )


def _diff(
    expected: Any,
    actual: Any,
    path: str,
    issues: list[RenderEquivalenceIssue],
) -> None:
    if type(expected) is not type(actual):
        issues.append(
            RenderEquivalenceIssue(
                "VIEWER_RENDER_EQUIVALENCE_TYPE",
                path,
                repr(expected),
                repr(actual),
            )
        )
        return
    if is_dataclass(expected):
        for field in fields(expected):
            _diff(
                getattr(expected, field.name),
                getattr(actual, field.name),
                f"{path}.{field.name}",
                issues,
            )
        return
    if isinstance(expected, tuple):
        if len(expected) != len(actual):
            issues.append(
                RenderEquivalenceIssue(
                    "VIEWER_RENDER_EQUIVALENCE_LENGTH",
                    path,
                    str(len(expected)),
                    str(len(actual)),
                )
            )
        for index, (expected_item, actual_item) in enumerate(zip(expected, actual, strict=False)):
            _diff(expected_item, actual_item, f"{path}[{index}]", issues)
        return
    if expected != actual:
        issues.append(
            RenderEquivalenceIssue(
                "VIEWER_RENDER_EQUIVALENCE_VALUE",
                path,
                repr(expected),
                repr(actual),
            )
        )
