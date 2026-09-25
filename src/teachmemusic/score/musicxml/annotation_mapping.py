"""Contained MusicXML mapping for the currently supported notation marks."""

from __future__ import annotations

from dataclasses import replace
from fractions import Fraction
from typing import Protocol

from lxml import etree

from teachmemusic.score.v2.annotations import (
    SIMPLE_EVENT_MARKS,
    AccordionRegistration,
    BassFigure,
    BendSound,
    ComplexDirectionData,
    DirectionImage,
    DirectionMark,
    DirectionPitch,
    EventAnchor,
    EventMarkMarker,
    FiguredBassAnnotation,
    HarmonyBass,
    HarmonyChord,
    HarmonyDegree,
    HarmonyFrame,
    HarmonyFrameNote,
    HarmonyNumeral,
    HarmonySymbol,
    LyricMarker,
    LyricTextSegment,
    MetronomeBeam,
    MetronomeBeat,
    MetronomeMark,
    MetronomeNote,
    MetronomeTuplet,
    NoteheadMarker,
    NoteheadTextSegment,
    OrnamentAccidental,
    PercussionPictogram,
    PrincipalVoice,
    SpanMarker,
    TechnicalArrow,
    TechnicalBend,
    TechnicalData,
    TechnicalHarmonic,
    TechnicalHarmonMute,
    TechnicalHole,
    TimeAnchor,
    TimeSpanMarker,
    TrillPlayback,
)

from .presentation_mapping import map_presentation_style


class AnnotationMappingError(ValueError):
    """A supported notation value cannot be mapped exactly."""


class AnnotationAudit(Protocol):
    def take(self, element: etree._Element | None) -> etree._Element | None: ...

    def attr(self, element: etree._Element, name: str) -> str | None: ...

    def child(self, element: etree._Element, name: str) -> etree._Element | None: ...

    def children(self, element: etree._Element, name: str) -> tuple[etree._Element, ...]: ...

    def value(self, element: etree._Element | None) -> str | None: ...

    def child_value(self, element: etree._Element, name: str) -> str | None: ...


def _yes_no(value: str | None, name: str) -> bool | None:
    if value is None:
        return None
    if value not in {"yes", "no"}:
        raise AnnotationMappingError(f"invalid {name}: {value}")
    return value == "yes"


def _fraction(value: str | None, name: str) -> Fraction | None:
    if value is None:
        return None
    try:
        return Fraction(value)
    except (ValueError, ZeroDivisionError) as error:
        raise AnnotationMappingError(f"invalid {name}: {value}") from error


def _integer(value: str | None, name: str, *, minimum: int | None = None) -> int:
    try:
        result = int(value or "")
    except ValueError as error:
        raise AnnotationMappingError(f"invalid {name}: {value}") from error
    if minimum is not None and result < minimum:
        raise AnnotationMappingError(f"invalid {name}: {value}")
    return result


def _direction_pitch(
    element: etree._Element,
    audit: AnnotationAudit,
    *,
    prefix: str,
    octave: bool,
) -> DirectionPitch:
    step = audit.child_value(element, f"{prefix}-step")
    if step is None:
        raise AnnotationMappingError(f"{prefix} has no step")
    alter = _fraction(audit.child_value(element, f"{prefix}-alter"), f"{prefix}-alter")
    if alter is None:
        alter = Fraction(0)
    octave_value = audit.child_value(element, f"{prefix}-octave") if octave else None
    return DirectionPitch(
        step=step,
        alter=alter,
        octave=_integer(octave_value, f"{prefix}-octave") if octave_value is not None else None,
        string=(
            _integer(audit.attr(element, "string"), "accord string", minimum=1)
            if prefix == "tuning" and element.get("string") is not None
            else None
        ),
    )


def _metronome_beat(note_type: str | None, dots: int, tied_to_previous: bool) -> MetronomeBeat:
    if not note_type:
        raise AnnotationMappingError("metronome beat has no note type")
    return MetronomeBeat(note_type, dots, tied_to_previous)


def _metronome_tuplet(element: etree._Element, audit: AnnotationAudit) -> MetronomeTuplet:
    return MetronomeTuplet(
        actual_notes=_integer(
            audit.child_value(element, "actual-notes"), "actual-notes", minimum=1
        ),
        normal_notes=_integer(
            audit.child_value(element, "normal-notes"), "normal-notes", minimum=1
        ),
        normal_type=audit.child_value(element, "normal-type"),
        normal_dots=len(audit.children(element, "normal-dot")),
        action=audit.attr(element, "type") or "",
        bracket=_yes_no(audit.attr(element, "bracket"), "metronome-tuplet bracket"),
        show_number=audit.attr(element, "show-number"),
    )


def _metronome_note(element: etree._Element, audit: AnnotationAudit) -> MetronomeNote:
    note_type = audit.child_value(element, "metronome-type")
    if not note_type:
        raise AnnotationMappingError("metronome-note has no type")
    beams = tuple(
        MetronomeBeam(
            audit.value(beam) or "",
            _integer(audit.attr(beam, "number") or "1", "metronome beam number", minimum=1),
        )
        for beam in audit.children(element, "metronome-beam")
    )
    tied = audit.child(element, "metronome-tied")
    tuplet = audit.child(element, "metronome-tuplet")
    return MetronomeNote(
        note_type=note_type,
        dots=len(audit.children(element, "metronome-dot")),
        beams=beams,
        tie=audit.attr(tied, "type") if tied is not None else None,
        tuplet=_metronome_tuplet(tuplet, audit) if tuplet is not None else None,
    )


def _metronome(element: etree._Element, audit: AnnotationAudit) -> MetronomeMark:
    beats: list[MetronomeBeat] = []
    notes: list[MetronomeNote] = []
    per_minute: str | None = None
    relation: str | None = None
    arrows = False
    for child in element:
        if not isinstance(child.tag, str):
            continue
        kind = etree.QName(child).localname
        if kind == "beat-unit":
            audit.take(child)
            beats.append(_metronome_beat(audit.value(child), 0, False))
        elif kind == "beat-unit-dot":
            audit.take(child)
            if not beats:
                raise AnnotationMappingError("metronome dot has no beat unit")
            beats[-1] = replace(beats[-1], dots=beats[-1].dots + 1)
        elif kind == "beat-unit-tied":
            audit.take(child)
            beats.append(
                _metronome_beat(
                    audit.child_value(child, "beat-unit"),
                    len(audit.children(child, "beat-unit-dot")),
                    True,
                )
            )
        elif kind == "per-minute":
            audit.take(child)
            per_minute = audit.value(child) or ""
        elif kind == "metronome-arrows":
            audit.take(child)
            arrows = True
        elif kind == "metronome-note":
            audit.take(child)
            notes.append(_metronome_note(child, audit))
        elif kind == "metronome-relation":
            audit.take(child)
            relation = audit.value(child) or ""
    return MetronomeMark(
        beats=tuple(beats),
        per_minute=per_minute,
        arrows=arrows,
        notes=tuple(notes),
        relation=relation,
        parentheses=_yes_no(audit.attr(element, "parentheses"), "metronome parentheses"),
    )


def _percussion(element: etree._Element, audit: AnnotationAudit) -> PercussionPictogram:
    children = tuple(child for child in element if isinstance(child.tag, str))
    if len(children) != 1:
        raise AnnotationMappingError("percussion must contain one pictogram")
    child = children[0]
    audit.take(child)
    kind = etree.QName(child).localname
    if kind == "stick":
        return PercussionPictogram(
            kind=kind,
            tip=audit.attr(child, "tip"),
            stick_type=audit.child_value(child, "stick-type"),
            stick_material=audit.child_value(child, "stick-material"),
            parentheses=_yes_no(audit.attr(child, "parentheses"), "stick parentheses"),
            dashed_circle=_yes_no(audit.attr(child, "dashed-circle"), "stick dashed-circle"),
        )
    return PercussionPictogram(
        kind=kind,
        value=audit.value(child) or "",
        smufl=audit.attr(child, "smufl"),
        tip=audit.attr(child, "tip") if kind == "beater" else None,
    )


def _trill_playback(element: etree._Element, audit: AnnotationAudit) -> TrillPlayback | None:
    values = (
        audit.attr(element, "start-note"),
        audit.attr(element, "trill-step"),
        audit.attr(element, "two-note-turn"),
        audit.attr(element, "accelerate"),
        audit.attr(element, "beats"),
        audit.attr(element, "second-beat"),
        audit.attr(element, "last-beat"),
    )
    if all(value is None for value in values):
        return None
    return TrillPlayback(
        values[0],
        values[1],
        values[2],
        _yes_no(values[3], "ornament accelerate"),
        _fraction(values[4], "ornament beats"),
        _fraction(values[5], "ornament second-beat"),
        _fraction(values[6], "ornament last-beat"),
    )


def _bend_sound(element: etree._Element, audit: AnnotationAudit) -> BendSound | None:
    values = (
        audit.attr(element, "accelerate"),
        audit.attr(element, "beats"),
        audit.attr(element, "first-beat"),
        audit.attr(element, "last-beat"),
    )
    if all(value is None for value in values):
        return None
    return BendSound(
        _yes_no(values[0], "slide accelerate"),
        _fraction(values[1], "slide beats"),
        _fraction(values[2], "slide first-beat"),
        _fraction(values[3], "slide last-beat"),
    )


def _ornament_accidental(element: etree._Element, audit: AnnotationAudit) -> OrnamentAccidental:
    value = audit.value(element)
    if value is None or value == "":
        raise AnnotationMappingError("ornament accidental-mark has no value")
    return OrnamentAccidental(
        value,
        audit.attr(element, "placement"),
        _yes_no(audit.attr(element, "bracket"), "accidental-mark bracket"),
        _yes_no(audit.attr(element, "parentheses"), "accidental-mark parentheses"),
        audit.attr(element, "smufl"),
    )


def _tremolo_marks(element: etree._Element, audit: AnnotationAudit) -> int:
    value = audit.value(element)
    try:
        result = int(value or "")
    except ValueError as error:
        raise AnnotationMappingError(f"invalid tremolo marks: {value}") from error
    if not 0 <= result <= 8:
        raise AnnotationMappingError(f"invalid tremolo marks: {value}")
    return result


def _technical_harmonic(element: etree._Element, audit: AnnotationAudit) -> TechnicalHarmonic:
    harmonic_type = next(
        (name for name in ("natural", "artificial") if audit.child(element, name) is not None),
        None,
    )
    pitch_type = next(
        (
            name
            for name in ("base-pitch", "touching-pitch", "sounding-pitch")
            if audit.child(element, name) is not None
        ),
        None,
    )
    return TechnicalHarmonic(
        harmonic_type,
        pitch_type,
        _yes_no(audit.attr(element, "print-object"), "harmonic print-object"),
        audit.attr(element, "number"),
    )


def _technical_bend(element: etree._Element, audit: AnnotationAudit) -> TechnicalBend:
    alter = _fraction(audit.child_value(element, "bend-alter"), "bend-alter")
    if alter is None:
        raise AnnotationMappingError("bend has no bend-alter")
    pre_bend = audit.child(element, "pre-bend")
    release = audit.child(element, "release")
    with_bar = audit.child(element, "with-bar")
    return TechnicalBend(
        alter=alter,
        action="pre-bend" if pre_bend is not None else ("release" if release is not None else None),
        release_offset=(
            _fraction(audit.attr(release, "offset"), "bend release offset")
            if release is not None
            else None
        ),
        with_bar=(audit.value(with_bar) or "") if with_bar is not None else None,
        with_bar_placement=(audit.attr(with_bar, "placement") if with_bar is not None else None),
        shape=audit.attr(element, "shape"),
        accelerate=_yes_no(audit.attr(element, "accelerate"), "bend accelerate"),
        beats=_fraction(audit.attr(element, "beats"), "bend beats"),
        first_beat=_fraction(audit.attr(element, "first-beat"), "bend first-beat"),
        last_beat=_fraction(audit.attr(element, "last-beat"), "bend last-beat"),
    )


def _technical_hole(element: etree._Element, audit: AnnotationAudit) -> TechnicalHole:
    hole_type = audit.child(element, "hole-type")
    closed = audit.child(element, "hole-closed")
    shape = audit.child(element, "hole-shape")
    closed_value = audit.value(closed)
    if closed is None or not closed_value:
        raise AnnotationMappingError("hole has no hole-closed value")
    return TechnicalHole(
        (audit.value(hole_type) or "") if hole_type is not None else None,
        closed_value,
        audit.attr(closed, "location"),
        (audit.value(shape) or "") if shape is not None else None,
    )


def _technical_arrow(element: etree._Element, audit: AnnotationAudit) -> TechnicalArrow:
    direction = audit.child_value(element, "arrow-direction")
    circular = audit.child_value(element, "circular-arrow")
    if (direction is None) == (circular is None):
        raise AnnotationMappingError("arrow must be exactly one of straight or circular")
    return TechnicalArrow(
        direction=direction,
        style=audit.child_value(element, "arrow-style"),
        arrowhead_only=audit.child(element, "arrowhead") is not None,
        circular=circular,
    )


def _technical_harmon_mute(element: etree._Element, audit: AnnotationAudit) -> TechnicalHarmonMute:
    closed = audit.child(element, "harmon-closed")
    closed_value = audit.value(closed)
    if closed is None or not closed_value:
        raise AnnotationMappingError("harmon-mute has no harmon-closed value")
    return TechnicalHarmonMute(closed_value, audit.attr(closed, "location"))


def _technical_data(
    kind: str, element: etree._Element, audit: AnnotationAudit
) -> TechnicalData | None:
    if kind == "harmonic":
        return TechnicalData(harmonic=_technical_harmonic(element, audit))
    if kind == "bend":
        return TechnicalData(bend=_technical_bend(element, audit))
    if kind == "hole":
        return TechnicalData(hole=_technical_hole(element, audit))
    if kind == "arrow":
        return TechnicalData(arrow=_technical_arrow(element, audit))
    if kind == "harmon-mute":
        return TechnicalData(harmon_mute=_technical_harmon_mute(element, audit))
    if kind == "fingering":
        return TechnicalData(
            substitution=_yes_no(audit.attr(element, "substitution"), "fingering substitution"),
            alternate=_yes_no(audit.attr(element, "alternate"), "fingering alternate"),
        )
    if kind in {"heel", "toe"}:
        return TechnicalData(
            substitution=_yes_no(audit.attr(element, "substitution"), f"{kind} substitution")
        )
    if kind == "tap":
        return TechnicalData(hand=audit.attr(element, "hand"))
    return None


def map_notehead(note: etree._Element, audit: AnnotationAudit) -> NoteheadMarker | None:
    """Preserve notehead shape and ordered text; leave styling deferred."""

    element = audit.child(note, "notehead")
    text_element = audit.child(note, "notehead-text")
    if element is None and text_element is None:
        return None
    value = audit.value(element) if element is not None else None
    if element is not None and value is None:
        raise AnnotationMappingError("notehead has no value")
    segments: list[NoteheadTextSegment] = []
    if text_element is not None:
        for child in text_element:
            if isinstance(child.tag, str):
                segments.append(
                    NoteheadTextSegment(etree.QName(child).localname, audit.value(child) or "")
                )
    return NoteheadMarker(
        value,
        _yes_no(audit.attr(element, "filled"), "notehead filled") if element is not None else None,
        _yes_no(audit.attr(element, "parentheses"), "notehead parentheses")
        if element is not None
        else None,
        audit.attr(element, "smufl") if element is not None else None,
        tuple(segments),
    )


def map_lyric(element: etree._Element, audit: AnnotationAudit, *, source_order: int) -> LyricMarker:
    """Preserve ordered lyric text/elision and non-text vocal states."""

    audit.take(element)
    segments: list[LyricTextSegment] = []
    pending_syllabic: str | None = None
    pending_elision: str | None = None
    pending_elision_smufl: str | None = None
    extend_present = False
    extend: str | None = None
    laughing = False
    humming = False
    end_line = False
    end_paragraph = False
    for child in element:
        if not isinstance(child.tag, str):
            continue
        kind = etree.QName(child).localname
        if kind == "syllabic":
            pending_syllabic = audit.value(child)
        elif kind == "elision":
            pending_elision = audit.value(child) or ""
            pending_elision_smufl = audit.attr(child, "smufl")
        elif kind == "text":
            segments.append(
                LyricTextSegment(
                    text=audit.value(child) or "",
                    syllabic=pending_syllabic,
                    elision_before=pending_elision,
                    elision_smufl=pending_elision_smufl,
                )
            )
            pending_syllabic = None
            pending_elision = None
            pending_elision_smufl = None
        elif kind == "extend":
            audit.take(child)
            extend_present = True
            extend = audit.attr(child, "type")
        elif kind == "laughing":
            audit.take(child)
            laughing = True
        elif kind == "humming":
            audit.take(child)
            humming = True
        elif kind == "end-line":
            audit.take(child)
            end_line = True
        elif kind == "end-paragraph":
            audit.take(child)
            end_paragraph = True
    text = "".join(f"{segment.elision_before or ''}{segment.text}" for segment in segments)
    return LyricMarker(
        number=audit.attr(element, "number"),
        name=audit.attr(element, "name"),
        syllabic=segments[0].syllabic if segments else None,
        text=text,
        source_order=source_order,
        segments=tuple(segments),
        extend_present=extend_present,
        extend=extend,
        laughing=laughing,
        humming=humming,
        end_line=end_line,
        end_paragraph=end_paragraph,
        print_object=_yes_no(audit.attr(element, "print-object"), "lyric print-object"),
        time_only=audit.attr(element, "time-only"),
        source_id=audit.attr(element, "id"),
        placement=audit.attr(element, "placement"),
    )


def map_event_marks(
    notations: etree._Element | None,
    audit: AnnotationAudit,
    *,
    span_order_offset: int = 0,
    mark_order_offset: int = 0,
) -> tuple[tuple[EventMarkMarker, ...], tuple[SpanMarker, ...]]:
    """Map point marks and the span ornaments embedded among them."""

    if notations is None:
        return (), ()
    result: list[EventMarkMarker] = []
    spans: list[SpanMarker] = []
    families = {
        "articulations": "articulation",
        "ornaments": "ornament",
        "technical": "technical",
        "dynamics": "dynamic",
    }
    for group in notations:
        if not isinstance(group.tag, str):
            continue
        group_kind = etree.QName(group).localname
        if group_kind in {"glissando", "slide"}:
            action = group.get("type")
            if action not in {"start", "stop"}:
                continue
            audit.take(group)
            spans.append(
                SpanMarker(
                    kind=group_kind,
                    number=audit.attr(group, "number") or "1",
                    action=audit.attr(group, "type") or "",
                    source_order=span_order_offset + len(spans) + 1,
                    text=audit.value(group),
                    source_id=audit.attr(group, "id"),
                    line_type=audit.attr(group, "line-type"),
                    bend_sound=_bend_sound(group, audit) if group_kind == "slide" else None,
                )
            )
            continue
        if group_kind == "other-notation":
            action = group.get("type")
            if action not in {"start", "stop", "single"}:
                continue
            audit.take(group)
            number = audit.attr(group, "number") or "1"
            source_id = audit.attr(group, "id")
            placement = audit.attr(group, "placement")
            smufl = audit.attr(group, "smufl")
            text = audit.value(group)
            print_object = _yes_no(audit.attr(group, "print-object"), "other-notation print-object")
            if action == "single":
                result.append(
                    EventMarkMarker(
                        family="notation",
                        kind="other-notation",
                        text=text,
                        source_order=mark_order_offset + len(result) + 1,
                        group_id=source_id,
                        placement=placement,
                        mark_type="single",
                        smufl=smufl,
                        number=number,
                        print_object=print_object,
                    )
                )
            else:
                spans.append(
                    SpanMarker(
                        kind="other-notation",
                        number=number,
                        action=action,
                        source_order=span_order_offset + len(spans) + 1,
                        placement=placement,
                        smufl=smufl,
                        text=text,
                        source_id=source_id,
                        print_object=print_object,
                    )
                )
            continue
        if group_kind in {"fermata", "arpeggiate", "non-arpeggiate"}:
            audit.take(group)
            result.append(
                EventMarkMarker(
                    family="notation",
                    kind=group_kind,
                    text=audit.value(group) if group_kind == "fermata" else None,
                    source_order=mark_order_offset + len(result) + 1,
                    group_id=audit.attr(group, "id"),
                    placement=audit.attr(group, "placement"),
                    mark_type=audit.attr(group, "type")
                    if group_kind in {"fermata", "non-arpeggiate"}
                    else audit.attr(group, "direction"),
                    number=audit.attr(group, "number")
                    if group_kind in {"arpeggiate", "non-arpeggiate"}
                    else None,
                    unbroken=_yes_no(audit.attr(group, "unbroken"), "arpeggiate unbroken")
                    if group_kind == "arpeggiate"
                    else None,
                )
            )
            continue
        if group_kind == "accidental-mark":
            audit.take(group)
            accidental = _ornament_accidental(group, audit)
            result.append(
                EventMarkMarker(
                    "ornament",
                    "accidental-mark",
                    accidental.value,
                    mark_order_offset + len(result) + 1,
                    placement=accidental.placement,
                    smufl=accidental.smufl,
                    bracket=accidental.bracket,
                    parentheses=accidental.parentheses,
                )
            )
            continue
        family = families.get(group_kind)
        if family is None:
            continue
        audit.take(group)
        group_id = audit.attr(group, "id")
        group_placement = audit.attr(group, "placement") if family == "dynamic" else None
        ornament_target: tuple[str, int] | None = None
        for child in group:
            if not isinstance(child.tag, str):
                continue
            kind = etree.QName(child).localname
            if family == "ornament" and kind == "accidental-mark":
                audit.take(child)
                accidental = _ornament_accidental(child, audit)
                if ornament_target is None:
                    raise AnnotationMappingError("accidental-mark has no preceding ornament")
                target_kind, target_index = ornament_target
                if target_kind == "mark":
                    target = result[target_index]
                    result[target_index] = replace(
                        target, accidentals=(*target.accidentals, accidental)
                    )
                else:
                    target_span = spans[target_index]
                    spans[target_index] = replace(
                        target_span, accidentals=(*target_span.accidentals, accidental)
                    )
                continue
            if family == "ornament" and kind == "wavy-line":
                action = child.get("type")
                if action not in {"start", "continue", "stop"}:
                    continue
                audit.take(child)
                spans.append(
                    SpanMarker(
                        "wavy-line",
                        audit.attr(child, "number") or "1",
                        audit.attr(child, "type") or "",
                        span_order_offset + len(spans) + 1,
                        audit.attr(child, "placement"),
                        audit.attr(child, "smufl"),
                        _trill_playback(child, audit),
                    )
                )
                ornament_target = ("span", len(spans) - 1)
                continue
            if family == "ornament" and kind == "tremolo":
                tremolo_type = child.get("type") or "single"
                if tremolo_type in {"start", "stop"}:
                    audit.take(child)
                    spans.append(
                        SpanMarker(
                            "tremolo",
                            "1",
                            audit.attr(child, "type") or "",
                            span_order_offset + len(spans) + 1,
                            audit.attr(child, "placement"),
                            audit.attr(child, "smufl"),
                            tremolo_marks=_tremolo_marks(child, audit),
                        )
                    )
                    ornament_target = ("span", len(spans) - 1)
                    continue
                if tremolo_type not in {"single", "unmeasured"}:
                    continue
            if family == "technical" and kind in {"hammer-on", "pull-off"}:
                action = child.get("type")
                if action not in {"start", "stop"}:
                    continue
                audit.take(child)
                spans.append(
                    SpanMarker(
                        kind,
                        audit.attr(child, "number") or "1",
                        audit.attr(child, "type") or "",
                        span_order_offset + len(spans) + 1,
                        placement=audit.attr(child, "placement"),
                        text=audit.value(child),
                    )
                )
                continue
            technical = _technical_data(kind, child, audit) if family == "technical" else None
            if kind not in SIMPLE_EVENT_MARKS[family] or (len(child) and technical is None):
                continue
            audit.take(child)
            result.append(
                EventMarkMarker(
                    family=family,
                    kind=kind,
                    text=audit.value(child) if not len(child) else None,
                    source_order=mark_order_offset + len(result) + 1,
                    group_id=group_id,
                    placement=group_placement or audit.attr(child, "placement"),
                    mark_type=audit.attr(child, "type")
                    or ("single" if family == "ornament" and kind == "tremolo" else None),
                    smufl=audit.attr(child, "smufl"),
                    line_shape=audit.attr(child, "line-shape"),
                    line_type=audit.attr(child, "line-type"),
                    playback=_trill_playback(child, audit) if family == "ornament" else None,
                    slash=_yes_no(audit.attr(child, "slash"), "ornament slash")
                    if family == "ornament"
                    else None,
                    long=_yes_no(audit.attr(child, "long"), "ornament long")
                    if family == "ornament"
                    else None,
                    approach=audit.attr(child, "approach") if family == "ornament" else None,
                    departure=audit.attr(child, "departure") if family == "ornament" else None,
                    tremolo_marks=_tremolo_marks(child, audit)
                    if family == "ornament" and kind == "tremolo"
                    else None,
                    technical=technical,
                )
            )
            if family == "ornament":
                ornament_target = ("mark", len(result) - 1)
    return tuple(result), tuple(spans)


def map_direction(
    element: etree._Element,
    audit: AnnotationAudit,
    *,
    part_id: str,
    measure_id: str,
    onset: Fraction,
    score_onset: Fraction,
    divisions: int | None,
    source_order: int,
) -> tuple[tuple[DirectionMark, ...], tuple[TimeSpanMarker, ...]]:
    """Map supported semantic directions, not presentation or playback sound."""

    audit.take(element)
    placement = audit.attr(element, "placement")
    directive = _yes_no(audit.attr(element, "directive"), "direction directive")
    staff = audit.child_value(element, "staff") or "1"
    voice = audit.child_value(element, "voice")
    offset_text = audit.child_value(element, "offset")
    offset = Fraction(0)
    if offset_text is not None:
        if divisions is None or divisions <= 0:
            raise AnnotationMappingError("direction offset before divisions")
        try:
            offset = Fraction(offset_text) / divisions
        except (ValueError, ZeroDivisionError) as error:
            raise AnnotationMappingError("invalid direction offset") from error
    location = onset + offset
    anchor = TimeAnchor(part_id, measure_id, location, score_onset + location, staff, voice)
    result: list[DirectionMark] = []
    spans: list[TimeSpanMarker] = []
    component_order = 0
    for direction_type in audit.children(element, "direction-type"):
        for child in direction_type:
            if not isinstance(child.tag, str):
                continue
            kind = etree.QName(child).localname
            if kind in {
                "words",
                "rehearsal",
                "segno",
                "coda",
                "symbol",
                "damp",
                "damp-all",
                "eyeglasses",
                "string-mute",
                "staff-divide",
                "other-direction",
            }:
                audit.take(child)
                component_order += 1
                value = (
                    audit.attr(child, "type")
                    if kind in {"string-mute", "staff-divide"}
                    else audit.value(child) or ""
                )
                result.append(
                    DirectionMark(
                        anchor=anchor,
                        family=kind,
                        value=value or "",
                        placement=placement,
                        source_order=source_order,
                        component_order=component_order,
                        smufl=(
                            audit.attr(child, "smufl")
                            if kind in {"segno", "coda", "other-direction"}
                            else None
                        ),
                        direction_id=audit.attr(element, "id"),
                        direction_type_id=audit.attr(direction_type, "id"),
                        source_id=audit.attr(child, "id"),
                        print_object=(
                            _yes_no(
                                audit.attr(child, "print-object"),
                                "other-direction print-object",
                            )
                            if kind == "other-direction"
                            else None
                        ),
                        system_relation=audit.attr(element, "system"),
                        presentation=map_presentation_style(child, audit),
                        directive=directive,
                    )
                )
            elif kind == "dynamics":
                audit.take(child)
                group_id = audit.attr(child, "id")
                for dynamic in child:
                    if not isinstance(dynamic.tag, str) or len(dynamic):
                        continue
                    audit.take(dynamic)
                    component_order += 1
                    result.append(
                        DirectionMark(
                            anchor=anchor,
                            family="dynamic",
                            value=audit.value(dynamic) or etree.QName(dynamic).localname,
                            placement=placement,
                            source_order=source_order,
                            component_order=component_order,
                            group_id=group_id,
                            smufl=audit.attr(dynamic, "smufl"),
                            direction_id=audit.attr(element, "id"),
                            direction_type_id=audit.attr(direction_type, "id"),
                            system_relation=audit.attr(element, "system"),
                            presentation=map_presentation_style(child, audit),
                            directive=directive,
                        )
                    )
            elif kind in {
                "metronome",
                "harp-pedals",
                "scordatura",
                "accordion-registration",
                "principal-voice",
                "percussion",
                "image",
            }:
                audit.take(child)
                metronome = _metronome(child, audit) if kind == "metronome" else None
                harp_pedals = (
                    tuple(
                        _direction_pitch(pedal, audit, prefix="pedal", octave=False)
                        for pedal in audit.children(child, "pedal-tuning")
                    )
                    if kind == "harp-pedals"
                    else ()
                )
                scordatura = (
                    tuple(
                        _direction_pitch(accord, audit, prefix="tuning", octave=True)
                        for accord in audit.children(child, "accord")
                    )
                    if kind == "scordatura"
                    else ()
                )
                middle = (
                    audit.child_value(child, "accordion-middle")
                    if kind == "accordion-registration"
                    else None
                )
                accordion = (
                    AccordionRegistration(
                        audit.child(child, "accordion-high") is not None,
                        _integer(middle, "accordion-middle", minimum=1)
                        if middle is not None
                        else None,
                        audit.child(child, "accordion-low") is not None,
                    )
                    if kind == "accordion-registration"
                    else None
                )
                principal = (
                    PrincipalVoice(
                        audit.attr(child, "type") or "",
                        audit.attr(child, "symbol") or "",
                        audit.value(child) or "",
                    )
                    if kind == "principal-voice"
                    else None
                )
                percussion = _percussion(child, audit) if kind == "percussion" else None
                image = (
                    DirectionImage(
                        source=audit.attr(child, "source") or "",
                        mime_type=audit.attr(child, "type") or "",
                        width=_fraction(audit.attr(child, "width"), "image width"),
                        height=_fraction(audit.attr(child, "height"), "image height"),
                    )
                    if kind == "image"
                    else None
                )
                data = ComplexDirectionData(
                    metronome=metronome,
                    harp_pedals=harp_pedals,
                    scordatura=scordatura,
                    accordion=accordion,
                    principal_voice=principal,
                    percussion=percussion,
                    image=image,
                )
                value = ""
                if metronome is not None:
                    value = metronome.per_minute or metronome.relation or ""
                elif principal is not None:
                    value = principal.text
                elif percussion is not None:
                    value = percussion.value or percussion.kind
                elif image is not None:
                    value = image.source
                component_order += 1
                result.append(
                    DirectionMark(
                        anchor=anchor,
                        family=kind,
                        value=value,
                        placement=placement,
                        source_order=source_order,
                        component_order=component_order,
                        direction_id=audit.attr(element, "id"),
                        direction_type_id=audit.attr(direction_type, "id"),
                        source_id=audit.attr(child, "id"),
                        print_object=(
                            _yes_no(audit.attr(child, "print-object"), "metronome print-object")
                            if kind == "metronome"
                            else None
                        ),
                        system_relation=audit.attr(element, "system"),
                        data=data,
                        presentation=map_presentation_style(child, audit),
                        directive=directive,
                    )
                )
            elif kind in {"wedge", "dashes", "bracket", "pedal", "octave-shift"}:
                span_type = audit.attr(child, "type")
                pedal_line = (
                    _yes_no(audit.attr(child, "line"), "pedal line") if kind == "pedal" else None
                )
                pedal_sign = (
                    _yes_no(audit.attr(child, "sign"), "pedal sign") if kind == "pedal" else None
                )
                pedal_abbreviated = (
                    _yes_no(audit.attr(child, "abbreviated"), "pedal abbreviated")
                    if kind == "pedal"
                    else None
                )
                starts = {
                    "wedge": {"crescendo", "diminuendo"},
                    "dashes": {"start"},
                    "bracket": {"start"},
                    "pedal": {"start", "sostenuto"},
                    "octave-shift": {"up", "down"},
                }[kind]
                continuations = (
                    {"continue", "change", "discontinue", "resume"}
                    if kind == "pedal"
                    else {"continue"}
                )
                if span_type not in starts | continuations | {"stop"}:
                    continue
                audit.take(child)
                component_order += 1
                if (
                    kind == "pedal"
                    and span_type in {"start", "sostenuto", "stop"}
                    and pedal_line is not True
                    and pedal_sign is not False
                ):
                    result.append(
                        DirectionMark(
                            anchor=anchor,
                            family="pedal",
                            value=span_type,
                            placement=placement,
                            source_order=source_order,
                            component_order=component_order,
                            direction_id=audit.attr(element, "id"),
                            direction_type_id=audit.attr(direction_type, "id"),
                            source_id=audit.attr(child, "id"),
                            system_relation=audit.attr(element, "system"),
                            presentation=map_presentation_style(child, audit),
                            directive=directive,
                            pedal_number=audit.attr(child, "number") or "1",
                            pedal_line=pedal_line,
                            pedal_sign=pedal_sign,
                            pedal_abbreviated=pedal_abbreviated,
                        )
                    )
                    if span_type == "stop":
                        continue
                spans.append(
                    TimeSpanMarker(
                        kind=kind,
                        number=audit.attr(child, "number") or "1",
                        action=(
                            "start"
                            if span_type in starts
                            else "continue"
                            if span_type in continuations
                            else "stop"
                        ),
                        opening=span_type if span_type in starts else None,
                        anchor=anchor,
                        source_order=source_order,
                        component_order=component_order,
                        direction_id=audit.attr(element, "id"),
                        direction_type_id=audit.attr(direction_type, "id"),
                        source_id=audit.attr(child, "id"),
                        system_relation=audit.attr(element, "system"),
                        source_type=span_type,
                        line_type=audit.attr(child, "line-type"),
                        dash_length=_fraction(audit.attr(child, "dash-length"), "dash-length"),
                        space_length=_fraction(audit.attr(child, "space-length"), "space-length"),
                        spread=_fraction(audit.attr(child, "spread"), "wedge spread"),
                        niente=_yes_no(audit.attr(child, "niente"), "wedge niente"),
                        line_end=audit.attr(child, "line-end"),
                        end_length=_fraction(audit.attr(child, "end-length"), "end-length"),
                        pedal_line=pedal_line,
                        pedal_sign=pedal_sign,
                        pedal_abbreviated=pedal_abbreviated,
                        octave_size=(
                            _integer(audit.attr(child, "size"), "octave-shift size", minimum=1)
                            if audit.attr(child, "size") is not None
                            else None
                        ),
                        directive=directive,
                    )
                )
    return tuple(result), tuple(spans)


def _harmony_degree(element: etree._Element, audit: AnnotationAudit) -> HarmonyDegree:
    value_element = audit.child(element, "degree-value")
    alter_element = audit.child(element, "degree-alter")
    type_element = audit.child(element, "degree-type")
    if value_element is None or alter_element is None or type_element is None:
        raise AnnotationMappingError("incomplete harmony degree")
    return HarmonyDegree(
        value=_integer(audit.value(value_element), "degree-value", minimum=1),
        alter=_fraction(audit.value(alter_element), "degree-alter") or Fraction(0),
        degree_type=audit.value(type_element) or "",
        print_object=_yes_no(audit.attr(element, "print-object"), "degree print-object"),
        symbol=audit.attr(value_element, "symbol"),
        value_text=audit.attr(value_element, "text"),
        type_text=audit.attr(type_element, "text"),
        plus_minus=_yes_no(audit.attr(alter_element, "plus-minus"), "degree plus-minus"),
    )


def _harmony_chord(
    children: tuple[etree._Element, ...], start: int, audit: AnnotationAudit
) -> tuple[HarmonyChord, int]:
    source = children[start]
    source_kind = etree.QName(source).localname
    root_step: str | None = None
    root_alter = Fraction(0)
    numeral: HarmonyNumeral | None = None
    function: str | None = None
    audit.take(source)
    if source_kind == "root":
        root_step = audit.child_value(source, "root-step")
        alter = audit.child(source, "root-alter")
        root_alter = _fraction(audit.value(alter), "root-alter") or Fraction(0)
    elif source_kind == "numeral":
        root = audit.child_value(source, "numeral-root")
        alter = audit.child(source, "numeral-alter")
        key = audit.child(source, "numeral-key")
        numeral = HarmonyNumeral(
            root=_integer(root, "numeral-root", minimum=1),
            alter=_fraction(audit.value(alter), "numeral-alter") or Fraction(0),
            key_fifths=(
                _integer(audit.child_value(key, "numeral-fifths"), "numeral-fifths")
                if key is not None
                else None
            ),
            key_mode=audit.child_value(key, "numeral-mode") if key is not None else None,
        )
    elif source_kind == "function":
        function = audit.value(source) or ""
    else:
        raise AnnotationMappingError(f"invalid harmony chord start: {source_kind}")

    index = start + 1
    if index >= len(children) or etree.QName(children[index]).localname != "kind":
        raise AnnotationMappingError("harmony chord has no kind")
    kind_element = children[index]
    audit.take(kind_element)
    kind = audit.value(kind_element) or ""
    kind_text = audit.attr(kind_element, "text")
    use_symbols = _yes_no(audit.attr(kind_element, "use-symbols"), "kind use-symbols")
    stack_degrees = _yes_no(audit.attr(kind_element, "stack-degrees"), "kind stack-degrees")
    parentheses_degrees = _yes_no(
        audit.attr(kind_element, "parentheses-degrees"), "kind parentheses-degrees"
    )
    bracket_degrees = _yes_no(audit.attr(kind_element, "bracket-degrees"), "kind bracket-degrees")
    index += 1
    inversion: int | None = None
    bass: HarmonyBass | None = None
    degrees: list[HarmonyDegree] = []
    if index < len(children) and etree.QName(children[index]).localname == "inversion":
        inversion = _integer(
            audit.value(audit.take(children[index])), "harmony inversion", minimum=0
        )
        index += 1
    if index < len(children) and etree.QName(children[index]).localname == "bass":
        bass_element = children[index]
        audit.take(bass_element)
        step = audit.child_value(bass_element, "bass-step")
        if step is None:
            raise AnnotationMappingError("harmony bass has no step")
        alter = audit.child(bass_element, "bass-alter")
        bass = HarmonyBass(step, _fraction(audit.value(alter), "bass-alter") or Fraction(0))
        index += 1
    while index < len(children) and etree.QName(children[index]).localname == "degree":
        audit.take(children[index])
        degrees.append(_harmony_degree(children[index], audit))
        index += 1
    return (
        HarmonyChord(
            root_step=root_step,
            root_alter=root_alter,
            numeral=numeral,
            function=function,
            kind=kind,
            kind_text=kind_text,
            use_symbols=use_symbols,
            stack_degrees=stack_degrees,
            parentheses_degrees=parentheses_degrees,
            bracket_degrees=bracket_degrees,
            inversion=inversion,
            bass=bass,
            degrees=tuple(degrees),
        ),
        index,
    )


def _harmony_frame(element: etree._Element, audit: AnnotationAudit) -> HarmonyFrame:
    first = audit.child(element, "first-fret")
    notes: list[HarmonyFrameNote] = []
    for note in audit.children(element, "frame-note"):
        fingering = audit.child(note, "fingering")
        barre = audit.child(note, "barre")
        notes.append(
            HarmonyFrameNote(
                string=_integer(audit.child_value(note, "string"), "frame string", minimum=1),
                fret=_integer(audit.child_value(note, "fret"), "frame fret", minimum=0),
                fingering=audit.value(fingering) if fingering is not None else None,
                barre=audit.attr(barre, "type") if barre is not None else None,
            )
        )
    return HarmonyFrame(
        strings=_integer(audit.child_value(element, "frame-strings"), "frame strings", minimum=1),
        frets=_integer(audit.child_value(element, "frame-frets"), "frame frets", minimum=1),
        first_fret=(
            _integer(audit.value(first), "first fret", minimum=1) if first is not None else None
        ),
        first_fret_text=audit.attr(first, "text") if first is not None else None,
        first_fret_location=audit.attr(first, "location") if first is not None else None,
        notes=tuple(notes),
        unplayed=audit.attr(element, "unplayed"),
    )


def map_harmony(
    element: etree._Element,
    audit: AnnotationAudit,
    *,
    part_id: str,
    measure_id: str,
    onset: Fraction,
    score_onset: Fraction,
    divisions: int | None,
    source_order: int,
) -> HarmonySymbol:
    """Map complete semantic harmony content and its exact temporal offset."""

    audit.take(element)
    children = tuple(child for child in element if isinstance(child.tag, str))
    chords: list[HarmonyChord] = []
    index = 0
    while index < len(children) and etree.QName(children[index]).localname in {
        "root",
        "numeral",
        "function",
    }:
        chord, index = _harmony_chord(children, index, audit)
        chords.append(chord)
    if not chords:
        raise AnnotationMappingError("harmony has no chord")
    frame_element = audit.child(element, "frame")
    frame = _harmony_frame(frame_element, audit) if frame_element is not None else None
    offset_text = audit.child_value(element, "offset")
    offset = Fraction(0)
    if offset_text is not None:
        if divisions is None or divisions <= 0:
            raise AnnotationMappingError("harmony offset before divisions")
        offset = _fraction(offset_text, "harmony offset") or Fraction(0)
        offset /= divisions
    staff = audit.child_value(element, "staff") or "1"
    first = chords[0]
    return HarmonySymbol(
        anchor=TimeAnchor(
            part_id,
            measure_id,
            onset + offset,
            score_onset + onset + offset,
            staff,
            None,
        ),
        root_step=first.root_step,
        root_alter=first.root_alter,
        kind=first.kind,
        kind_text=first.kind_text,
        source_order=source_order,
        chords=tuple(chords),
        frame=frame,
        harmony_type=audit.attr(element, "type"),
        print_object=_yes_no(audit.attr(element, "print-object"), "harmony print-object"),
        print_frame=_yes_no(audit.attr(element, "print-frame"), "harmony print-frame"),
        arrangement=audit.attr(element, "arrangement"),
        source_id=audit.attr(element, "id"),
        system_relation=audit.attr(element, "system"),
    )


def map_figured_bass(
    element: etree._Element,
    audit: AnnotationAudit,
    *,
    anchor: EventAnchor,
    divisions: int | None,
    source_order: int,
) -> FiguredBassAnnotation | None:
    """Map simple figures attached to the next regular note in score order."""

    figures = element.findall("figure")
    if not figures:
        return None
    audit.take(element)
    mapped: list[BassFigure] = []
    for figure in audit.children(element, "figure"):
        extend = audit.child(figure, "extend")
        mapped.append(
            BassFigure(
                audit.child_value(figure, "prefix"),
                audit.child_value(figure, "figure-number"),
                audit.child_value(figure, "suffix"),
                extend_present=extend is not None,
                extend=audit.attr(extend, "type") if extend is not None else None,
            )
        )
    duration_text = audit.child_value(element, "duration")
    duration = None
    if duration_text is not None:
        if divisions is None or divisions <= 0:
            raise AnnotationMappingError("figured-bass duration before divisions")
        try:
            duration = Fraction(duration_text) / divisions
        except (ValueError, ZeroDivisionError) as error:
            raise AnnotationMappingError("invalid figured-bass duration") from error
    return FiguredBassAnnotation(
        anchor=anchor,
        figures=tuple(mapped),
        duration=duration,
        source_order=source_order,
        parentheses=_yes_no(audit.attr(element, "parentheses"), "figured-bass parentheses"),
        print_object=_yes_no(audit.attr(element, "print-object"), "figured-bass print-object"),
        print_dot=_yes_no(audit.attr(element, "print-dot"), "figured-bass print-dot"),
        print_spacing=_yes_no(audit.attr(element, "print-spacing"), "figured-bass print-spacing"),
        placement=audit.attr(element, "placement"),
        source_id=audit.attr(element, "id"),
        presentation=map_presentation_style(element, audit),
    )
