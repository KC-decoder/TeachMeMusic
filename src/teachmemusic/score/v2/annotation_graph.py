"""Resolve and validate the currently mapped MusicXML notation spans."""

from __future__ import annotations

from collections import Counter

from .annotations import (
    AnnotationGraph,
    DirectionMark,
    EventAnchor,
    EventMark,
    FiguredBassAnnotation,
    HarmonySymbol,
    LyricSyllable,
    NotationSpan,
    NoteheadMark,
    SpanEndpoint,
    TimeAnchor,
    TimeSpan,
    TimeSpanMarker,
)
from .temporal import TemporalPart, TemporalPitch, TemporalScoreMetadata


class AnnotationGraphError(ValueError):
    """A mapped notation span has an invalid endpoint sequence."""


_MUSESCORE_2_WEDGE_RECOVERY = "musescore-2-adjacent-wedge-recovery"


def _span_key(
    part_id: str, kind: str, number: str, pitch: TemporalPitch | None
) -> tuple[str, str, str, str]:
    if kind in {"sounding-tie", "notated-tie"}:
        if pitch is None:
            raise AnnotationGraphError(f"{kind} requires a pitched note")
        step_semitones = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}
        discriminator = str(12 * pitch.octave + step_semitones[pitch.step] + pitch.alter)
    else:
        discriminator = ""
    return part_id, kind, number, discriminator


def _ordered_span_endpoints(endpoints: tuple[SpanEndpoint, ...]) -> tuple[SpanEndpoint, ...]:
    """Return endpoints in musical action order when XML document order differs."""

    action_order = {"start": 0, "continue": 1, "stop": 2, "let-ring": 3}
    return tuple(
        sorted(
            endpoints,
            key=lambda endpoint: (
                action_order[endpoint.action],
                endpoint.anchor.score_onset,
                endpoint.source_order,
            ),
        )
    )


def _ordered_time_markers(
    markers: tuple[TimeSpanMarker, ...],
) -> tuple[TimeSpanMarker, ...]:
    """Return time markers in musical action order rather than document order."""

    action_order = {"start": 0, "continue": 1, "stop": 2}
    return tuple(
        sorted(
            markers,
            key=lambda marker: (
                action_order[marker.action],
                marker.anchor.score_onset,
                marker.source_order,
                marker.component_order,
            ),
        )
    )


def _is_musescore_2_export(part: TemporalPart, score_metadata: TemporalScoreMetadata) -> bool:
    encodings = tuple(
        encoding
        for encoding in (score_metadata.encoding, part.metadata.encoding)
        if encoding is not None
    )
    return any(
        software.strip().casefold().startswith("musescore 2.")
        for encoding in encodings
        for software in encoding.software
    )


def _is_point_pedal_marker(marker: TimeSpanMarker) -> bool:
    """Return whether the marker is already preserved as a printed pedal sign."""

    return (
        marker.kind == "pedal"
        and marker.source_type in {"start", "sostenuto", "stop"}
        and marker.pedal_line is not True
        and marker.pedal_sign is not False
    )


def _opposite_wedges(left: TimeSpanMarker, right: TimeSpanMarker) -> bool:
    return {left.opening, right.opening} == {"crescendo", "diminuendo"}


def _inferred_wedge_stop(
    start: TimeSpanMarker,
    anchor: TimeAnchor,
    *,
    source_order: int,
    component_order: int,
) -> TimeSpanMarker:
    return TimeSpanMarker(
        kind="wedge",
        number=start.number,
        action="stop",
        opening=None,
        anchor=anchor,
        source_order=source_order,
        component_order=component_order,
        inferred=True,
        inference_reason=_MUSESCORE_2_WEDGE_RECOVERY,
    )


def _recover_musescore_2_adjacent_wedges(
    part: TemporalPart,
    score_metadata: TemporalScoreMetadata,
    active_time: dict[tuple[str, str], list[TimeSpanMarker]],
    time_occurrences: Counter[tuple[str, str]],
    time_spans: list[TimeSpan],
) -> None:
    """Close two exact MuseScore 2.x same-measure wedge omission patterns.

    This is deliberately narrower than a general dangling-hairpin policy. It
    recognizes only alternating wedges on one staff where either an explicitly
    stopped wedge is immediately restarted with the same number, or exactly
    two unclosed wedges divide one measure. Every inferred endpoint remains
    explicit in the public graph; all other incomplete spans still fail.
    """

    if not active_time or not _is_musescore_2_export(part, score_metadata):
        return
    measures = {measure.id: measure for measure in part.measures}
    grouped: dict[tuple[str, str | None], list[tuple[tuple[str, str], TimeSpanMarker]]] = {}
    for key, endpoints in active_time.items():
        if (
            key[0] != "wedge"
            or len(endpoints) != 1
            or endpoints[0].action != "start"
            or endpoints[0].opening not in {"crescendo", "diminuendo"}
        ):
            continue
        start = endpoints[0]
        grouped.setdefault((start.anchor.measure_id, start.anchor.staff), []).append((key, start))

    for (measure_id, staff), entries in grouped.items():
        measure = measures[measure_id]
        entries.sort(
            key=lambda item: (
                item[1].anchor.onset,
                item[1].source_order,
                item[1].component_order,
            )
        )
        source_markers = tuple(
            marker
            for marker in measure.time_span_markers
            if marker.kind == "wedge" and marker.anchor.staff == staff
        )
        recoveries: tuple[tuple[tuple[str, str], TimeSpanMarker, TimeAnchor, int, int], ...] = ()

        if len(entries) == 1 and len(source_markers) == 3:
            key, start = entries[0]
            matching_prior = tuple(
                span
                for span in time_spans
                if span.kind == "wedge"
                and span.number == start.number
                and span.opening in {"crescendo", "diminuendo"}
                and span.opening != start.opening
                and span.endpoints[-1].action == "stop"
                and span.endpoints[-1].anchor.measure_id == measure_id
                and span.endpoints[-1].anchor.staff == staff
                and span.endpoints[-1].anchor.onset == start.anchor.onset
            )
            if len(matching_prior) == 1 and start.anchor.onset < measure.extent:
                recoveries = (
                    (
                        key,
                        start,
                        TimeAnchor(
                            part.id,
                            measure.id,
                            measure.extent,
                            measure.score_onset + measure.extent,
                            staff,
                            start.anchor.voice,
                        ),
                        max(marker.source_order for marker in source_markers) + 1,
                        0,
                    ),
                )
        elif len(entries) == 2 and len(source_markers) == 2:
            (first_key, first), (second_key, second) = entries
            if (
                first.number != second.number
                and first.anchor.onset == 0
                and 0 < second.anchor.onset < measure.extent
                and _opposite_wedges(first, second)
            ):
                recoveries = (
                    (
                        first_key,
                        first,
                        second.anchor,
                        second.source_order,
                        second.component_order,
                    ),
                    (
                        second_key,
                        second,
                        TimeAnchor(
                            part.id,
                            measure.id,
                            measure.extent,
                            measure.score_onset + measure.extent,
                            staff,
                            second.anchor.voice,
                        ),
                        max(marker.source_order for marker in source_markers) + 1,
                        0,
                    ),
                )

        for key, start, anchor, source_order, component_order in recoveries:
            stop = _inferred_wedge_stop(
                start,
                anchor,
                source_order=source_order,
                component_order=component_order,
            )
            time_occurrences[key] += 1
            time_spans.append(
                TimeSpan(
                    f"{part.id}:time-span:{start.kind}:{start.number}:{time_occurrences[key]}",
                    start.kind,
                    start.number,
                    start.opening,
                    (start, stop),
                )
            )
            active_time.pop(key)


def resolve_annotation_graph(
    parts: tuple[TemporalPart, ...],
    score_metadata: TemporalScoreMetadata | None = None,
) -> AnnotationGraph:
    """Pair start/continue/stop markers without losing individual endpoints."""

    effective_metadata = score_metadata or TemporalScoreMetadata()
    open_spans: dict[tuple[str, str, str, str, str], list[SpanEndpoint]] = {}
    pending_span_endpoints: dict[tuple[str, str, str, str], list[SpanEndpoint]] = {}
    completed: list[NotationSpan] = []
    lyrics: list[LyricSyllable] = []
    harmonies: list[HarmonySymbol] = []
    noteheads: list[NoteheadMark] = []
    event_marks: list[EventMark] = []
    directions: list[DirectionMark] = []
    figured_bass: list[FiguredBassAnnotation] = []
    time_spans: list[TimeSpan] = []
    occurrences: Counter[tuple[str, str, str, str]] = Counter()

    def append_span(base: tuple[str, str, str, str], endpoints: tuple[SpanEndpoint, ...]) -> None:
        occurrences[base] += 1
        completed.append(
            NotationSpan(
                id=f"{base[0]}:span:{base[1]}:{base[2]}:{occurrences[base]}",
                kind=base[1],
                number=base[2],
                endpoints=_ordered_span_endpoints(endpoints),
            )
        )

    for part in parts:
        active_time: dict[tuple[str, str], list[TimeSpanMarker]] = {}
        pending_time_markers: dict[tuple[str, str], list[TimeSpanMarker]] = {}
        time_occurrences: Counter[tuple[str, str]] = Counter()
        for measure in part.measures:
            harmonies.extend(measure.harmonies)
            directions.extend(measure.directions)
            figured_bass.extend(measure.figured_bass)
            for marker in sorted(
                measure.time_span_markers,
                key=lambda item: (item.source_order, item.component_order),
            ):
                time_key = (marker.kind, marker.number)
                if marker.action == "start":
                    if time_key in active_time:
                        raise AnnotationGraphError(f"duplicate time-span start: {time_key}")
                    pending_time = pending_time_markers.pop(time_key, [])
                    if any(item.action == "stop" for item in pending_time):
                        time_endpoints = _ordered_time_markers((marker, *pending_time))
                        time_occurrences[time_key] += 1
                        time_spans.append(
                            TimeSpan(
                                f"{part.id}:time-span:{marker.kind}:{marker.number}:"
                                f"{time_occurrences[time_key]}",
                                marker.kind,
                                marker.number,
                                marker.opening,
                                time_endpoints,
                            )
                        )
                    else:
                        active_time[time_key] = [marker, *pending_time]
                elif marker.action == "continue":
                    if time_key not in active_time:
                        pending_time_markers.setdefault(time_key, []).append(marker)
                    else:
                        active_time[time_key].append(marker)
                elif marker.action == "stop":
                    if time_key not in active_time:
                        pending_time = pending_time_markers.setdefault(time_key, [])
                        if any(item.action == "stop" for item in pending_time):
                            raise AnnotationGraphError(
                                f"duplicate pending time-span stop: {time_key}"
                            )
                        pending_time.append(marker)
                    else:
                        time_endpoints = _ordered_time_markers((*active_time.pop(time_key), marker))
                        time_occurrences[time_key] += 1
                        time_spans.append(
                            TimeSpan(
                                f"{part.id}:time-span:{marker.kind}:{marker.number}:"
                                f"{time_occurrences[time_key]}",
                                marker.kind,
                                marker.number,
                                time_endpoints[0].opening,
                                time_endpoints,
                            )
                        )
                else:
                    raise AnnotationGraphError(f"unsupported time-span action: {marker.action}")
        events = sorted(
            (
                (measure, event)
                for measure in part.measures
                for event in measure.events
                if event.span_markers
                or event.lyric_markers
                or event.notehead_marker is not None
                or event.event_markers
            ),
            # MusicXML number-level spans are paired in document order, not
            # score-time order: backup/forward can reorder concurrent voices.
            key=lambda pair: (pair[0].ordinal, pair[1].source_order),
        )
        for measure, event in events:
            anchor = EventAnchor(
                part.id,
                measure.id,
                event.id,
                event.staff,
                event.voice,
                event.score_onset,
            )
            if event.notehead_marker is not None:
                notehead_marker = event.notehead_marker
                noteheads.append(
                    NoteheadMark(
                        anchor,
                        notehead_marker.value,
                        notehead_marker.filled,
                        notehead_marker.parentheses,
                        notehead_marker.smufl,
                        notehead_marker.text,
                    )
                )
            for mark_marker in event.event_markers:
                event_marks.append(
                    EventMark(
                        anchor,
                        mark_marker.family,
                        mark_marker.kind,
                        mark_marker.text,
                        mark_marker.source_order,
                        mark_marker.group_id,
                        mark_marker.placement,
                        mark_marker.mark_type,
                        mark_marker.smufl,
                        mark_marker.line_shape,
                        mark_marker.line_type,
                        mark_marker.playback,
                        mark_marker.slash,
                        mark_marker.long,
                        mark_marker.approach,
                        mark_marker.departure,
                        mark_marker.tremolo_marks,
                        mark_marker.bracket,
                        mark_marker.parentheses,
                        mark_marker.accidentals,
                        mark_marker.technical,
                        mark_marker.number,
                        mark_marker.print_object,
                        mark_marker.unbroken,
                    )
                )
            for lyric in event.lyric_markers:
                lyrics.append(
                    LyricSyllable(
                        anchor=anchor,
                        number=lyric.number,
                        name=lyric.name,
                        syllabic=lyric.syllabic,
                        text=lyric.text,
                        source_order=lyric.source_order,
                        segments=lyric.segments,
                        extend_present=lyric.extend_present,
                        extend=lyric.extend,
                        laughing=lyric.laughing,
                        humming=lyric.humming,
                        end_line=lyric.end_line,
                        end_paragraph=lyric.end_paragraph,
                        print_object=lyric.print_object,
                        time_only=lyric.time_only,
                        source_id=lyric.source_id,
                        placement=lyric.placement,
                    )
                )
            span_markers = sorted(
                event.span_markers,
                key=lambda marker: (
                    0
                    if marker.kind in {"sounding-tie", "notated-tie"} and marker.action == "stop"
                    else 1,
                    marker.source_order,
                ),
            )
            for span_marker in span_markers:
                if span_marker.kind not in {
                    "sounding-tie",
                    "notated-tie",
                    "slur",
                    "wavy-line",
                    "tremolo",
                    "hammer-on",
                    "pull-off",
                    "glissando",
                    "slide",
                    "other-notation",
                }:
                    raise AnnotationGraphError(f"unsupported span kind: {span_marker.kind}")
                if span_marker.action not in {"start", "continue", "stop", "let-ring"}:
                    raise AnnotationGraphError(f"unsupported span action: {span_marker.action}")
                if span_marker.action == "let-ring" and span_marker.kind != "notated-tie":
                    raise AnnotationGraphError("let-ring is only valid for notated ties")
                if span_marker.kind == "tremolo" and span_marker.action == "continue":
                    raise AnnotationGraphError("double tremolo cannot continue")
                if (
                    span_marker.kind
                    in {"hammer-on", "pull-off", "glissando", "slide", "other-notation"}
                    and span_marker.action == "continue"
                ):
                    raise AnnotationGraphError(f"{span_marker.kind} cannot continue")
                base = _span_key(part.id, span_marker.kind, span_marker.number, event.pitch)
                key = (*base, event.voice)
                endpoint = SpanEndpoint(
                    action=span_marker.action,
                    anchor=anchor,
                    source_order=span_marker.source_order,
                    placement=span_marker.placement,
                    smufl=span_marker.smufl,
                    playback=span_marker.playback,
                    tremolo_marks=span_marker.tremolo_marks,
                    accidentals=span_marker.accidentals,
                    text=span_marker.text,
                    source_id=span_marker.source_id,
                    line_type=span_marker.line_type,
                    bend_sound=span_marker.bend_sound,
                    print_object=span_marker.print_object,
                    orientation=span_marker.orientation,
                    dash_length=span_marker.dash_length,
                    space_length=span_marker.space_length,
                    time_only=span_marker.time_only,
                )
                if span_marker.action == "let-ring":
                    append_span(base, (endpoint,))
                elif span_marker.action == "start":
                    if key in open_spans:
                        if span_marker.kind not in {"sounding-tie", "notated-tie"}:
                            raise AnnotationGraphError(f"duplicate span start: {key}")
                        append_span(base, tuple(open_spans.pop(key)))
                    pending_notation = pending_span_endpoints.pop(base, [])
                    if any(item.action == "stop" for item in pending_notation):
                        append_span(base, (endpoint, *pending_notation))
                    else:
                        open_spans[key] = [endpoint, *pending_notation]
                elif span_marker.action == "continue":
                    if key not in open_spans:
                        candidates = [
                            candidate for candidate in open_spans if candidate[:4] == base
                        ]
                        if len(candidates) == 1:
                            key = candidates[0]
                    if key not in open_spans:
                        pending_span_endpoints.setdefault(base, []).append(endpoint)
                    else:
                        open_spans[key].append(endpoint)
                else:
                    if key not in open_spans:
                        candidates = [
                            candidate for candidate in open_spans if candidate[:4] == base
                        ]
                        if len(candidates) == 1:
                            key = candidates[0]
                    if key not in open_spans:
                        pending_notation = pending_span_endpoints.setdefault(base, [])
                        if any(item.action == "stop" for item in pending_notation):
                            raise AnnotationGraphError(f"duplicate pending span stop: {base}")
                        pending_notation.append(endpoint)
                    else:
                        append_span(base, (*open_spans.pop(key), endpoint))
        _recover_musescore_2_adjacent_wedges(
            part, effective_metadata, active_time, time_occurrences, time_spans
        )
        active_time = {
            key: markers
            for key, markers in active_time.items()
            if not all(_is_point_pedal_marker(marker) for marker in markers)
        }
        pending_time_markers = {
            key: markers
            for key, markers in pending_time_markers.items()
            if not all(_is_point_pedal_marker(marker) for marker in markers)
        }
        if active_time:
            raise AnnotationGraphError(f"unclosed time spans: {tuple(active_time)}")
        if pending_time_markers:
            pending_time_key, markers = next(iter(pending_time_markers.items()))
            action = markers[0].action
            raise AnnotationGraphError(f"time-span {action} without start: {pending_time_key}")
    unclosed = {
        key: endpoints
        for key, endpoints in open_spans.items()
        if key[1] not in {"sounding-tie", "notated-tie"}
    }
    if unclosed:
        raise AnnotationGraphError(f"unclosed notation spans: {tuple(unclosed)}")
    for open_key, endpoints in open_spans.items():
        append_span(open_key[:4], tuple(endpoints))
    unmatched = {
        key: endpoints
        for key, endpoints in pending_span_endpoints.items()
        if key[1] not in {"sounding-tie", "notated-tie"}
        and not (
            key[1] == "wavy-line"
            and any(
                part.id == key[0] and _is_musescore_2_export(part, effective_metadata)
                for part in parts
            )
            and endpoints
            and all(endpoint.action == "stop" for endpoint in endpoints)
        )
    }
    if unmatched:
        pending_span_key, pending_endpoints = next(iter(unmatched.items()))
        action = pending_endpoints[0].action
        raise AnnotationGraphError(f"span {action} without start: {pending_span_key}")
    for pending_key, endpoints in pending_span_endpoints.items():
        append_span(pending_key, tuple(endpoints))
    return AnnotationGraph(
        tuple(completed),
        tuple(lyrics),
        tuple(harmonies),
        tuple(noteheads),
        tuple(event_marks),
        tuple(directions),
        tuple(figured_bass),
        tuple(time_spans),
    )
