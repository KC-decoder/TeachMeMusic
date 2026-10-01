"""Deterministic canonical-to-MusicXML notation projection.

This is a renderer interchange projection, not an archival MusicXML exporter.
It starts from public canonical objects and fails closed when the Task 5B.1
notation subset cannot represent a semantic fact.
"""

from __future__ import annotations

import math
import re
import xml.etree.ElementTree as ET
from collections.abc import Iterable
from dataclasses import dataclass
from fractions import Fraction
from typing import NoReturn

from teachmemusic.score.v2.annotations import (
    SIMPLE_EVENT_MARKS,
    DirectionMark,
    DirectionPitch,
    EventMarkMarker,
    HarmonySymbol,
    LyricMarker,
    MetronomeMark,
    NoteheadMarker,
    OrnamentAccidental,
    SpanMarker,
    TimeSpanMarker,
    TrillPlayback,
)
from teachmemusic.score.v2.documents import CanonicalScoreContent, ScoreDocument
from teachmemusic.score.v2.presentation import PresentationNumber, PresentationStyle
from teachmemusic.score.v2.temporal import (
    TemporalAttributes,
    TemporalBarline,
    TemporalEvent,
    TemporalMeasure,
    TemporalPart,
    TemporalScore,
    TemporalTuplet,
    TemporalTupletPortion,
)

from .contracts import DiagnosticSeverity, RenderAnchor, ViewerDiagnostic

_PART_ID_PATTERN = re.compile(r"[^A-Za-z0-9_.-]")
_INLINE_DYNAMIC_SYMBOL_PATTERN = re.compile(
    r"<sym>dynamic(?:Piano|Forte|Mezzo|Sforzando|Rinforzando|Niente|Z)</sym>"
)

REPRESENTED_FEATURES = (
    "accidentals",
    "barlines",
    "beams",
    "clefs",
    "chord-membership",
    "harmony-symbols",
    "key-signatures",
    "lyrics",
    "measure-order",
    "measure-system-breaks",
    "mid-measure-attributes",
    "note-attached-marks",
    "note-attached-span-topology",
    "noteheads",
    "point-directions",
    "note-and-rest-events",
    "part-order-and-names",
    "polyphonic-cursor-reconstruction",
    "polyphonic-staff-and-voice-placement",
    "repeat-ending-and-navigation-barlines",
    "grace-note-notation",
    "score-creators",
    "score-credits",
    "score-title",
    "stems",
    "sound-directives",
    "time-anchored-direction-spans",
    "time-signatures",
    "tuplets-and-time-modification",
    "written-pitch-and-rhythm",
)


class NotationProjectionError(ValueError):
    """Raised when canonical content is outside the approved notation slice."""

    def __init__(self, code: str, message: str, *, canonical_id: str | None = None) -> None:
        self.code = code
        self.canonical_id = canonical_id
        super().__init__(f"{code}: {message}")


@dataclass(frozen=True, slots=True)
class RenderedNotation:
    """Deterministic MusicXML plus its identity crosswalk and diagnostics."""

    content: bytes
    anchors: tuple[RenderAnchor, ...]
    diagnostics: tuple[ViewerDiagnostic, ...]
    represented_features: tuple[str, ...] = REPRESENTED_FEATURES


def render_score_document(document: ScoreDocument) -> RenderedNotation:
    """Project one complete canonical score document to MusicXML 4.0."""

    if not isinstance(document.content, CanonicalScoreContent):
        raise NotationProjectionError(
            "VIEWER_SCORE_INCOMPLETE",
            "notation projection requires complete canonical score content",
            canonical_id=document.id.value,
        )
    score = document.content.score
    _require_supported_score(score)
    divisions = _score_divisions(score)
    root = ET.Element("score-partwise", {"version": "4.0"})
    _write_title(root, score)
    _write_identification(root, score)
    _write_credits(root, score)
    part_ids = _write_part_list(root, score)
    anchors: list[RenderAnchor] = [
        RenderAnchor(
            canonical_id=document.id.value,
            canonical_kind="score",
            renderer_anchor="score",
        )
    ]
    for part_index, (part, renderer_part_id) in enumerate(zip(score.parts, part_ids, strict=True)):
        _write_part(
            root,
            part,
            renderer_part_id=renderer_part_id,
            part_index=part_index,
            divisions=divisions,
            anchors=anchors,
        )
    ET.indent(root, space="  ")
    content = ET.tostring(root, encoding="utf-8", xml_declaration=True)
    if not content.endswith(b"\n"):
        content += b"\n"
    return RenderedNotation(
        content=content,
        anchors=tuple(anchors),
        diagnostics=_normalization_diagnostics(document, score),
    )


def _require_supported_score(score: TemporalScore) -> None:
    if score.groups:
        _unsupported("part groups")
    if score.annotations.figured_bass:
        _unsupported("figured-bass annotations")
    _require_supported_recovery_provenance(score)
    if score.layout is not None and any(
        item.kind != "words" or item.mime_type is not None
        for credit in score.layout.credits
        for item in credit.items
    ):
        _unsupported("non-text score credits")
    for part in score.parts:
        _require_supported_part(part)


def _require_supported_part(part: TemporalPart) -> None:
    if not part.staves or not part.voices:
        _unsupported("parts without staff and voice identities", canonical_id=part.id)
    if part.groups or part.players or part.part_links:
        _unsupported("part groups, players, or linked parts", canonical_id=part.id)
    for measure in part.measures:
        if measure.figured_bass:
            _unsupported("figured bass", canonical_id=measure.id)
        if measure.groupings:
            _unsupported("measure groupings", canonical_id=measure.id)
        if measure.links or measure.bookmarks:
            _unsupported("measure links or bookmarks", canonical_id=measure.id)
        for attributes in measure.attributes:
            _require_supported_attributes(attributes, canonical_id=measure.id)
        _require_supported_sounds(measure)
        chord_counts: dict[str, int] = {}
        for event in measure.events:
            if event.chord_id is not None:
                chord_counts[event.chord_id] = chord_counts.get(event.chord_id, 0) + 1
        if any(count < 2 for count in chord_counts.values()):
            _unsupported("incomplete chord membership", canonical_id=measure.id)
        for harmony in measure.harmonies:
            _require_supported_harmony(harmony, canonical_id=measure.id)
        for event in measure.events:
            _require_supported_event(event)
        for direction in measure.directions:
            _require_supported_direction(direction, canonical_id=measure.id)
        for marker in measure.time_span_markers:
            _require_supported_time_span_marker(marker, canonical_id=measure.id)


def _require_supported_sounds(measure: TemporalMeasure) -> None:
    for sound in measure.sounds:
        unsupported_values = (
            sound.divisions,
            sound.pizzicato,
            sound.pan,
            sound.elevation,
            sound.damper_pedal,
            sound.soft_pedal,
            sound.sostenuto_pedal,
            sound.swing,
        )
        if (
            any(item is not None for item in unsupported_values)
            or sound.instrument_changes
            or sound.devices
            or sound.midi
            or sound.techniques
        ):
            _unsupported("instrument-specific sound directives", canonical_id=measure.id)
        if not 0 <= sound.onset <= measure.extent:
            _unsupported("out-of-range sound directive", canonical_id=measure.id)


def _require_supported_event(event: TemporalEvent) -> None:
    if event.kind not in {"pitched", "rest"}:
        _unsupported(f"event kind {event.kind!r}", canonical_id=event.id)
    if event.kind == "pitched" and event.pitch is None:
        raise NotationProjectionError(
            "VIEWER_NOTATION_PITCH_MISSING",
            "a pitched event has no written pitch",
            canonical_id=event.id,
        )
    if event.cue:
        _unsupported("cue notes", canonical_id=event.id)
    if event.grace != (event.grace_timing is not None):
        _unsupported("inconsistent grace-note timing", canonical_id=event.id)
    for span_marker in event.span_markers:
        _require_supported_span_marker(span_marker, canonical_id=event.id)
    for event_marker in event.event_markers:
        _require_supported_event_mark(event_marker, canonical_id=event.id)
    if event.accidentals and (
        event.accidental is None
        or len(event.accidentals) != 1
        or event.accidentals[0] != event.accidental
    ):
        _unsupported("multiple explicit accidentals", canonical_id=event.id)
    if event.instrument_id is not None or event.instrument_ids:
        _unsupported("per-note instrument changes", canonical_id=event.id)
    for lyric in event.lyric_markers:
        _require_supported_lyric(event, lyric)


def _require_supported_recovery_provenance(score: TemporalScore) -> None:
    inferred = tuple(
        endpoint
        for span in score.annotations.time_spans
        for endpoint in span.endpoints
        if endpoint.inferred
    )
    if any(
        endpoint.inference_reason != "musescore-2-adjacent-wedge-recovery" for endpoint in inferred
    ):
        _unsupported("unknown direction-span recovery provenance")
    if not (_has_stop_only_wavy_line(score) or inferred):
        return
    encoding = score.metadata.encoding
    if encoding is None or not any(
        item.strip().casefold().startswith("musescore 2.") for item in encoding.software
    ):
        _unsupported("stop-only wavy-line recovery without MuseScore 2 provenance")


def _require_supported_span_marker(marker: SpanMarker, *, canonical_id: str) -> None:
    supported = {
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
    }
    if marker.kind not in supported:
        _unsupported(f"note span {marker.kind!r}", canonical_id=canonical_id)


def _require_supported_event_mark(marker: EventMarkMarker, *, canonical_id: str) -> None:
    if marker.family not in {"articulation", "ornament", "technical", "dynamic", "notation"}:
        _unsupported(f"note mark family {marker.family!r}", canonical_id=canonical_id)
    if marker.technical is not None:
        _unsupported("structured technical note marks", canonical_id=canonical_id)


def _require_supported_direction(direction: DirectionMark, *, canonical_id: str) -> None:
    supported = {
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
        "dynamic",
        "metronome",
        "harp-pedals",
        "scordatura",
        "accordion-registration",
        "principal-voice",
        "percussion",
        "image",
        "pedal",
    }
    if direction.family not in supported:
        _unsupported(f"direction kind {direction.family!r}", canonical_id=canonical_id)
    complex_families = {
        "metronome",
        "harp-pedals",
        "scordatura",
        "accordion-registration",
        "principal-voice",
        "percussion",
        "image",
    }
    if (direction.data is not None) != (direction.family in complex_families):
        _unsupported("inconsistent complex direction payload", canonical_id=canonical_id)


def _require_supported_time_span_marker(marker: TimeSpanMarker, *, canonical_id: str) -> None:
    if marker.kind not in {"wedge", "dashes", "bracket", "pedal", "octave-shift"}:
        _unsupported(f"direction span {marker.kind!r}", canonical_id=canonical_id)
    if marker.inferred:
        _unsupported("inferred endpoint stored as a source marker", canonical_id=canonical_id)


def _require_supported_attributes(attributes: TemporalAttributes, *, canonical_id: str) -> None:
    if (
        attributes.transpositions
        or attributes.instrument_count is not None
        or attributes.measure_styles
        or attributes.staff_details
        or attributes.part_symbol is not None
        or attributes.for_parts
        or attributes.directives
        or attributes.part_symbols
    ):
        _unsupported("extended attribute state", canonical_id=canonical_id)
    if any(
        key.fifths is None
        or key.cancel_location is not None
        or key.alterations
        or key.octaves
        or key.print_object is not None
        for key in attributes.keys
    ):
        _unsupported("complex key signatures", canonical_id=canonical_id)
    if any(
        time.separator is not None
        or time.interchangeable is not None
        or time.print_object is not None
        for time in attributes.times
    ):
        _unsupported("complex time signatures", canonical_id=canonical_id)
    if any(
        clef.additional is not None
        or clef.size is not None
        or clef.after_barline is not None
        or clef.print_object is not None
        for clef in attributes.clefs
    ):
        _unsupported("extended clef presentation", canonical_id=canonical_id)


def _require_supported_harmony(harmony: HarmonySymbol, *, canonical_id: str) -> None:
    if len(harmony.chords) != 1:
        _unsupported("polychord or empty harmony symbols", canonical_id=canonical_id)
    chord = harmony.chords[0]
    if (
        harmony.root_step is None
        or chord.root_step != harmony.root_step
        or chord.root_alter != harmony.root_alter
        or chord.kind != harmony.kind
        or chord.kind_text != harmony.kind_text
        or chord.numeral is not None
        or chord.function is not None
        or chord.inversion is not None
        or chord.bass is not None
        or chord.degrees
        or harmony.frame is not None
        or harmony.harmony_type is not None
        or harmony.arrangement is not None
        or harmony.system_relation is not None
    ):
        _unsupported("complex harmony symbols", canonical_id=canonical_id)


def _require_supported_lyric(event: TemporalEvent, lyric: LyricMarker) -> None:
    if (
        len(lyric.segments) > 1
        or lyric.extend_present
        or lyric.laughing
        or lyric.humming
        or lyric.end_line
        or lyric.end_paragraph
        or lyric.time_only is not None
        or lyric.name is not None
    ):
        _unsupported("extended lyric semantics", canonical_id=event.id)


def _unsupported(feature: str, *, canonical_id: str | None = None) -> NoReturn:
    raise NotationProjectionError(
        "VIEWER_NOTATION_UNSUPPORTED_FACT",
        f"the current canonical notation projection cannot represent {feature}",
        canonical_id=canonical_id,
    )


def _score_divisions(score: TemporalScore) -> int:
    divisions = 1
    for part in score.parts:
        for measure in part.measures:
            values = [measure.extent]
            values.extend(event.onset for event in measure.events)
            values.extend(event.duration for event in measure.events)
            values.extend(attributes.onset for attributes in measure.attributes)
            values.extend(harmony.anchor.onset for harmony in measure.harmonies)
            values.extend(barline.onset for barline in measure.barlines)
            values.extend(direction.anchor.onset for direction in measure.directions)
            values.extend(marker.anchor.onset for marker in measure.time_span_markers)
            values.extend(sound.onset for sound in measure.sounds)
            divisions = math.lcm(divisions, *(item.denominator for item in values))
    return divisions


def _write_title(root: ET.Element, score: TemporalScore) -> None:
    if score.work_title is not None:
        work = ET.SubElement(root, "work")
        ET.SubElement(work, "work-title").text = score.work_title
    if score.movement_number is not None:
        ET.SubElement(root, "movement-number").text = score.movement_number
    if score.movement_title is not None:
        ET.SubElement(root, "movement-title").text = score.movement_title


def _has_stop_only_wavy_line(score: TemporalScore) -> bool:
    return any(
        span.kind == "wavy-line"
        and span.endpoints
        and all(endpoint.action == "stop" for endpoint in span.endpoints)
        for span in score.annotations.spans
    )


def _has_inferred_time_span_endpoint(score: TemporalScore) -> bool:
    return any(
        endpoint.inferred for span in score.annotations.time_spans for endpoint in span.endpoints
    )


def _write_identification(root: ET.Element, score: TemporalScore) -> None:
    """Write represented creator facts and narrowly required recovery provenance."""

    retain_recovery = _has_stop_only_wavy_line(score) or _has_inferred_time_span_endpoint(score)
    if not score.creators and not retain_recovery:
        return
    identification = ET.SubElement(root, "identification")
    for creator_type, text in score.creators:
        attributes = {"type": creator_type} if creator_type is not None else {}
        ET.SubElement(identification, "creator", attributes).text = text
    if not retain_recovery:
        return
    assert score.metadata.encoding is not None
    software = next(
        item
        for item in score.metadata.encoding.software
        if item.strip().casefold().startswith("musescore 2.")
    )
    encoding = ET.SubElement(identification, "encoding")
    ET.SubElement(encoding, "software").text = software


def _write_credits(root: ET.Element, score: TemporalScore) -> None:
    """Preserve canonical text credits needed for visual score comparison."""

    if score.layout is None:
        return
    for credit in score.layout.credits:
        credit_element = ET.SubElement(root, "credit", {"page": str(credit.page)})
        for credit_type in credit.types:
            ET.SubElement(credit_element, "credit-type").text = credit_type
        for item in credit.items:
            ET.SubElement(
                credit_element,
                "credit-words",
                _presentation_attributes(item.style),
            ).text = item.value


def _write_part_list(root: ET.Element, score: TemporalScore) -> tuple[str, ...]:
    part_list = ET.SubElement(root, "part-list")
    part_ids: list[str] = []
    used: set[str] = set()
    for index, part in enumerate(score.parts, start=1):
        candidate = _PART_ID_PATTERN.sub("-", part.id.rsplit(":", 1)[-1]) or f"P{index}"
        if not candidate[0].isalpha() and candidate[0] != "_":
            candidate = f"P{index}-{candidate}"
        renderer_id = candidate
        suffix = 2
        while renderer_id in used:
            renderer_id = f"{candidate}-{suffix}"
            suffix += 1
        used.add(renderer_id)
        part_ids.append(renderer_id)
        score_part = ET.SubElement(part_list, "score-part", {"id": renderer_id})
        ET.SubElement(score_part, "part-name").text = part.name or None
        if part.abbreviation is not None:
            ET.SubElement(score_part, "part-abbreviation").text = part.abbreviation
        for instrument_index, instrument in enumerate(part.instruments, start=1):
            instrument_id = f"{renderer_id}-I{instrument_index}"
            score_instrument = ET.SubElement(score_part, "score-instrument", {"id": instrument_id})
            ET.SubElement(score_instrument, "instrument-name").text = instrument.name or None
            if instrument.abbreviation is not None:
                ET.SubElement(
                    score_instrument, "instrument-abbreviation"
                ).text = instrument.abbreviation
            if instrument.sound is not None:
                ET.SubElement(score_instrument, "instrument-sound").text = instrument.sound
    return tuple(part_ids)


def _write_part(
    root: ET.Element,
    part: TemporalPart,
    *,
    renderer_part_id: str,
    part_index: int,
    divisions: int,
    anchors: list[RenderAnchor],
) -> None:
    part_element = ET.SubElement(root, "part", {"id": renderer_part_id})
    anchors.append(
        RenderAnchor(
            canonical_id=part.id,
            canonical_kind="part",
            renderer_anchor=f"part[{part_index}]",
            renderer_part_id=renderer_part_id,
            part_index=part_index,
        )
    )
    for measure_index, measure in enumerate(part.measures):
        attributes = {"number": measure.number}
        if measure.implicit:
            attributes["implicit"] = "yes"
        measure_element = ET.SubElement(part_element, "measure", attributes)
        anchors.append(
            RenderAnchor(
                canonical_id=measure.id,
                canonical_kind="measure",
                renderer_anchor=f"part[{part_index}]/measure[{measure_index}]",
                renderer_part_id=renderer_part_id,
                part_index=part_index,
                measure_index=measure_index,
            )
        )
        _write_measure_layout(measure_element, measure)
        initial_attributes = tuple(
            sorted(
                (item for item in measure.attributes if item.onset == 0),
                key=lambda item: item.source_order,
            )
        )
        if initial_attributes:
            for item in initial_attributes:
                _write_attributes(measure_element, item, divisions=divisions)
        elif measure_index == 0:
            _write_attributes(
                measure_element,
                None,
                divisions=divisions,
            )
        for barline in sorted(
            (item for item in measure.barlines if item.onset == 0),
            key=lambda item: item.source_order,
        ):
            _write_barline(measure_element, barline)
        _write_sounds(measure_element, measure, divisions=divisions)
        _write_directions(measure_element, measure, divisions=divisions)
        _write_events(
            measure_element,
            measure,
            divisions=divisions,
            renderer_part_id=renderer_part_id,
            part_index=part_index,
            measure_index=measure_index,
            anchors=anchors,
        )
        for barline in sorted(
            (item for item in measure.barlines if item.onset != 0),
            key=lambda item: item.source_order,
        ):
            _write_barline(measure_element, barline)


def _write_measure_layout(parent: ET.Element, measure: TemporalMeasure) -> None:
    if measure.layout is None:
        return
    attributes: dict[str, str] = {}
    if measure.layout.new_system is not None:
        attributes["new-system"] = _yes_no(measure.layout.new_system)
    if measure.layout.new_page is not None:
        attributes["new-page"] = _yes_no(measure.layout.new_page)
    if attributes:
        ET.SubElement(parent, "print", attributes)


def _write_attributes(
    parent: ET.Element,
    attributes: TemporalAttributes | None,
    *,
    divisions: int,
) -> None:
    element = ET.SubElement(parent, "attributes")
    ET.SubElement(element, "divisions").text = str(divisions)
    if attributes is None:
        return
    for key in attributes.keys:
        key_attributes = {"number": key.staff} if key.staff not in {None, "1"} else {}
        key_element = ET.SubElement(element, "key", key_attributes)
        if key.cancel is not None:
            ET.SubElement(key_element, "cancel").text = str(key.cancel)
        if key.fifths is None:
            _unsupported("non-fifths key signatures")
        ET.SubElement(key_element, "fifths").text = str(key.fifths)
        if key.mode is not None:
            ET.SubElement(key_element, "mode").text = key.mode
    for time in attributes.times:
        time_attributes = {"number": time.staff} if time.staff not in {None, "1"} else {}
        if time.symbol is not None:
            time_attributes["symbol"] = time.symbol
        time_element = ET.SubElement(element, "time", time_attributes)
        if time.senza_misura is not None:
            ET.SubElement(time_element, "senza-misura").text = time.senza_misura
        else:
            if len(time.beats) != len(time.beat_types):
                _unsupported("unpaired time-signature components")
            for beats, beat_type in zip(time.beats, time.beat_types, strict=True):
                ET.SubElement(time_element, "beats").text = beats
                ET.SubElement(time_element, "beat-type").text = str(beat_type)
    if attributes.staves is not None:
        ET.SubElement(element, "staves").text = str(attributes.staves)
    number_all_clefs = len(attributes.clefs) > 1 or any(
        clef.staff != "1" for clef in attributes.clefs
    )
    for clef in attributes.clefs:
        clef_attributes = {"number": clef.staff} if number_all_clefs else {}
        clef_element = ET.SubElement(element, "clef", clef_attributes)
        ET.SubElement(clef_element, "sign").text = clef.sign
        if clef.line is not None:
            ET.SubElement(clef_element, "line").text = str(clef.line)
        if clef.octave_change is not None:
            ET.SubElement(clef_element, "clef-octave-change").text = str(clef.octave_change)


def _write_sounds(parent: ET.Element, measure: TemporalMeasure, *, divisions: int) -> None:
    for sound in sorted(measure.sounds, key=lambda item: item.source_order):
        attributes: dict[str, str] = {}
        decimal_attributes: tuple[tuple[str, Fraction | None], ...] = (
            ("tempo", sound.tempo),
            ("dynamics", sound.dynamics),
        )
        for name, decimal_value in decimal_attributes:
            if decimal_value is not None:
                attributes[name] = _fraction_decimal(decimal_value)
        if sound.dacapo is not None:
            attributes["dacapo"] = _yes_no(sound.dacapo)
        text_attributes: tuple[tuple[str, str | None], ...] = (
            ("segno", sound.segno),
            ("dalsegno", sound.dalsegno),
            ("coda", sound.coda),
            ("tocoda", sound.tocoda),
            ("fine", sound.fine),
            ("time-only", sound.time_only),
        )
        for name, text_value in text_attributes:
            if text_value is not None:
                attributes[name] = text_value
        if sound.forward_repeat is not None:
            attributes["forward-repeat"] = _yes_no(sound.forward_repeat)
        if sound.source_id is not None:
            attributes["id"] = sound.source_id
        element = ET.SubElement(parent, "sound", attributes)
        if sound.onset:
            ET.SubElement(element, "offset").text = str(_offset_units(sound.onset, divisions))


def _write_directions(parent: ET.Element, measure: TemporalMeasure, *, divisions: int) -> None:
    components: list[DirectionMark | TimeSpanMarker] = [
        *measure.directions,
        *measure.time_span_markers,
    ]
    components.sort(key=lambda item: (item.source_order, item.component_order))
    index = 0
    while index < len(components):
        source_order = components[index].source_order
        group: list[DirectionMark | TimeSpanMarker] = []
        while index < len(components) and components[index].source_order == source_order:
            group.append(components[index])
            index += 1
        _write_direction_group(parent, group, divisions=divisions, canonical_id=measure.id)


def _write_direction_group(
    parent: ET.Element,
    components: list[DirectionMark | TimeSpanMarker],
    *,
    divisions: int,
    canonical_id: str,
) -> None:
    anchors = {item.anchor for item in components}
    if len(anchors) != 1:
        _unsupported("one source direction with multiple anchors", canonical_id=canonical_id)
    anchor = next(iter(anchors))
    point_components = [item for item in components if isinstance(item, DirectionMark)]
    placement = _one_value(
        (item.placement for item in point_components),
        feature="direction placement",
        canonical_id=canonical_id,
    )
    if placement is None and any(isinstance(item, TimeSpanMarker) for item in components):
        placement = (
            "above"
            if all(
                isinstance(item, TimeSpanMarker) and item.kind == "octave-shift"
                for item in components
            )
            else "below"
        )
    direction_id = _one_value(
        (item.direction_id for item in components),
        feature="direction identity",
        canonical_id=canonical_id,
    )
    system_relation = _one_value(
        (item.system_relation for item in components),
        feature="direction system relation",
        canonical_id=canonical_id,
    )
    directive = _one_value(
        (item.directive for item in components),
        feature="direction directive state",
        canonical_id=canonical_id,
    )
    attributes: dict[str, str] = {}
    if placement is not None:
        attributes["placement"] = placement
    if direction_id is not None:
        attributes["id"] = direction_id
    if system_relation is not None:
        attributes["system"] = system_relation
    if directive is not None:
        attributes["directive"] = _yes_no(directive)
    direction = ET.SubElement(parent, "direction", attributes)

    component_index = 0
    while component_index < len(components):
        component = components[component_index]
        direction_type_id = component.direction_type_id
        type_group: list[DirectionMark | TimeSpanMarker] = [component]
        component_index += 1
        if isinstance(component, DirectionMark) and component.family == "dynamic":
            while component_index < len(components):
                candidate = components[component_index]
                if (
                    not isinstance(candidate, DirectionMark)
                    or candidate.family != "dynamic"
                    or candidate.group_id != component.group_id
                    or candidate.direction_type_id != direction_type_id
                ):
                    break
                type_group.append(candidate)
                component_index += 1
        type_attributes = {"id": direction_type_id} if direction_type_id is not None else {}
        direction_type = ET.SubElement(direction, "direction-type", type_attributes)
        _write_direction_type_components(direction_type, type_group)

    if anchor.onset:
        ET.SubElement(direction, "offset").text = str(_offset_units(anchor.onset, divisions))
    if anchor.voice is not None:
        ET.SubElement(direction, "voice").text = anchor.voice
    ET.SubElement(direction, "staff").text = anchor.staff or "1"


def _one_value[T](
    values: Iterable[T | None],
    *,
    feature: str,
    canonical_id: str,
) -> T | None:
    present = {item for item in values if item is not None}
    if len(present) > 1:
        _unsupported(f"inconsistent {feature}", canonical_id=canonical_id)
    return next(iter(present)) if present else None


def _write_direction_type_components(
    parent: ET.Element, components: list[DirectionMark | TimeSpanMarker]
) -> None:
    index = 0
    while index < len(components):
        component = components[index]
        if isinstance(component, TimeSpanMarker):
            _write_time_span_marker(parent, component)
            index += 1
            continue
        if component.family != "dynamic":
            _write_direction_mark(parent, component)
            index += 1
            continue
        dynamic_group = [component]
        index += 1
        while index < len(components):
            candidate = components[index]
            if (
                not isinstance(candidate, DirectionMark)
                or candidate.family != "dynamic"
                or candidate.group_id != component.group_id
                or candidate.presentation != component.presentation
            ):
                break
            dynamic_group.append(candidate)
            index += 1
        attributes = _presentation_attributes(component.presentation)
        if component.group_id is not None:
            attributes["id"] = component.group_id
        dynamics = ET.SubElement(parent, "dynamics", attributes)
        for dynamic in dynamic_group:
            dynamic_attributes = {"smufl": dynamic.smufl} if dynamic.smufl is not None else {}
            if dynamic.value in SIMPLE_EVENT_MARKS["dynamic"] - {"other-dynamics"}:
                ET.SubElement(dynamics, dynamic.value, dynamic_attributes)
            else:
                ET.SubElement(dynamics, "other-dynamics", dynamic_attributes).text = dynamic.value


def _write_direction_mark(parent: ET.Element, marker: DirectionMark) -> None:
    attributes = _presentation_attributes(marker.presentation)
    if marker.source_id is not None:
        attributes["id"] = marker.source_id
    if marker.smufl is not None:
        attributes["smufl"] = marker.smufl
    if marker.print_object is not None:
        attributes["print-object"] = _yes_no(marker.print_object)
    if marker.family in {"string-mute", "staff-divide"}:
        attributes["type"] = marker.value
        ET.SubElement(parent, marker.family, attributes)
        return
    if marker.family == "pedal":
        attributes["type"] = marker.value
        if marker.pedal_number is not None:
            attributes["number"] = marker.pedal_number
        _add_pedal_attributes(attributes, marker)
        ET.SubElement(parent, "pedal", attributes)
        return
    if marker.data is not None:
        _write_complex_direction(parent, marker, attributes)
        return
    element = ET.SubElement(parent, marker.family, attributes)
    if marker.family not in {"segno", "coda", "damp", "damp-all", "eyeglasses"}:
        element.text = marker.value


def _write_complex_direction(
    parent: ET.Element, marker: DirectionMark, attributes: dict[str, str]
) -> None:
    assert marker.data is not None
    data = marker.data
    element = ET.SubElement(parent, marker.family, attributes)
    if marker.family == "metronome":
        assert data.metronome is not None
        _write_metronome(element, data.metronome)
    elif marker.family == "harp-pedals":
        for pitch in data.harp_pedals:
            tuning = ET.SubElement(element, "pedal-tuning")
            _write_direction_pitch(tuning, pitch, prefix="pedal", include_octave=False)
    elif marker.family == "scordatura":
        for pitch in data.scordatura:
            accord_attributes = {"string": str(pitch.string)} if pitch.string is not None else {}
            accord = ET.SubElement(element, "accord", accord_attributes)
            _write_direction_pitch(accord, pitch, prefix="tuning", include_octave=True)
    elif marker.family == "accordion-registration":
        assert data.accordion is not None
        if data.accordion.high:
            ET.SubElement(element, "accordion-high")
        if data.accordion.middle is not None:
            ET.SubElement(element, "accordion-middle").text = str(data.accordion.middle)
        if data.accordion.low:
            ET.SubElement(element, "accordion-low")
    elif marker.family == "principal-voice":
        assert data.principal_voice is not None
        element.set("type", data.principal_voice.action)
        element.set("symbol", data.principal_voice.symbol)
        element.text = data.principal_voice.text
    elif marker.family == "percussion":
        assert data.percussion is not None
        pictogram = data.percussion
        pictogram_attributes: dict[str, str] = {}
        if pictogram.smufl is not None:
            pictogram_attributes["smufl"] = pictogram.smufl
        if pictogram.tip is not None:
            pictogram_attributes["tip"] = pictogram.tip
        if pictogram.parentheses is not None:
            pictogram_attributes["parentheses"] = _yes_no(pictogram.parentheses)
        if pictogram.dashed_circle is not None:
            pictogram_attributes["dashed-circle"] = _yes_no(pictogram.dashed_circle)
        pictogram_element = ET.SubElement(element, pictogram.kind, pictogram_attributes)
        if pictogram.kind == "stick":
            if pictogram.stick_type is not None:
                ET.SubElement(pictogram_element, "stick-type").text = pictogram.stick_type
            if pictogram.stick_material is not None:
                ET.SubElement(pictogram_element, "stick-material").text = pictogram.stick_material
        else:
            pictogram_element.text = pictogram.value
    elif marker.family == "image":
        assert data.image is not None
        element.set("source", data.image.source)
        element.set("type", data.image.mime_type)
        if data.image.width is not None:
            element.set("width", _fraction_decimal(data.image.width))
        if data.image.height is not None:
            element.set("height", _fraction_decimal(data.image.height))


def _write_direction_pitch(
    parent: ET.Element,
    pitch: DirectionPitch,
    *,
    prefix: str,
    include_octave: bool,
) -> None:
    ET.SubElement(parent, f"{prefix}-step").text = pitch.step
    if pitch.alter:
        ET.SubElement(parent, f"{prefix}-alter").text = _fraction_decimal(pitch.alter)
    if include_octave:
        assert pitch.octave is not None
        ET.SubElement(parent, f"{prefix}-octave").text = str(pitch.octave)


def _write_metronome(parent: ET.Element, mark: MetronomeMark) -> None:
    if mark.parentheses is not None:
        parent.set("parentheses", _yes_no(mark.parentheses))
    for beat in mark.beats:
        if beat.tied_to_previous:
            tied = ET.SubElement(parent, "beat-unit-tied")
            ET.SubElement(tied, "beat-unit").text = beat.note_type
            for _ in range(beat.dots):
                ET.SubElement(tied, "beat-unit-dot")
        else:
            ET.SubElement(parent, "beat-unit").text = beat.note_type
            for _ in range(beat.dots):
                ET.SubElement(parent, "beat-unit-dot")
    if mark.per_minute is not None:
        ET.SubElement(parent, "per-minute").text = mark.per_minute
    if mark.arrows:
        ET.SubElement(parent, "metronome-arrows")
    for note in mark.notes:
        note_element = ET.SubElement(parent, "metronome-note")
        ET.SubElement(note_element, "metronome-type").text = note.note_type
        for _ in range(note.dots):
            ET.SubElement(note_element, "metronome-dot")
        for beam in note.beams:
            ET.SubElement(
                note_element, "metronome-beam", {"number": str(beam.number)}
            ).text = beam.value
        if note.tie is not None:
            ET.SubElement(note_element, "metronome-tied", {"type": note.tie})
        if note.tuplet is not None:
            tuplet = note.tuplet
            tuplet_attributes = {"type": tuplet.action}
            if tuplet.bracket is not None:
                tuplet_attributes["bracket"] = _yes_no(tuplet.bracket)
            if tuplet.show_number is not None:
                tuplet_attributes["show-number"] = tuplet.show_number
            tuplet_element = ET.SubElement(note_element, "metronome-tuplet", tuplet_attributes)
            ET.SubElement(tuplet_element, "actual-notes").text = str(tuplet.actual_notes)
            ET.SubElement(tuplet_element, "normal-notes").text = str(tuplet.normal_notes)
            if tuplet.normal_type is not None:
                ET.SubElement(tuplet_element, "normal-type").text = tuplet.normal_type
            for _ in range(tuplet.normal_dots):
                ET.SubElement(tuplet_element, "normal-dot")
    if mark.relation is not None:
        ET.SubElement(parent, "metronome-relation").text = mark.relation


def _write_time_span_marker(parent: ET.Element, marker: TimeSpanMarker) -> None:
    source_type = marker.source_type
    if source_type is None:
        source_type = marker.opening if marker.action == "start" else marker.action
    assert source_type is not None
    attributes: dict[str, str] = {"type": source_type, "number": marker.number}
    text_values: tuple[tuple[str, str | None], ...] = (
        ("id", marker.source_id),
        ("line-type", marker.line_type),
        ("line-end", marker.line_end),
    )
    for attribute_name, text_value in text_values:
        if text_value is not None:
            attributes[attribute_name] = text_value
    decimal_values: tuple[tuple[str, Fraction | None], ...] = (
        ("dash-length", marker.dash_length),
        ("space-length", marker.space_length),
        ("spread", marker.spread),
        ("end-length", marker.end_length),
    )
    for attribute_name, decimal_value in decimal_values:
        if decimal_value is not None:
            attributes[attribute_name] = _fraction_decimal(decimal_value)
    if marker.niente is not None:
        attributes["niente"] = _yes_no(marker.niente)
    if marker.kind == "pedal":
        _add_pedal_attributes(attributes, marker)
    if marker.octave_size is not None:
        attributes["size"] = str(marker.octave_size)
    ET.SubElement(parent, marker.kind, attributes)


def _add_pedal_attributes(
    attributes: dict[str, str], marker: DirectionMark | TimeSpanMarker
) -> None:
    if marker.pedal_line is not None:
        attributes["line"] = _yes_no(marker.pedal_line)
    if marker.pedal_sign is not None:
        attributes["sign"] = _yes_no(marker.pedal_sign)
    if marker.pedal_abbreviated is not None:
        attributes["abbreviated"] = _yes_no(marker.pedal_abbreviated)


def _presentation_attributes(style: PresentationStyle | None) -> dict[str, str]:
    if style is None:
        return {}
    attributes: dict[str, str] = {}
    decimal_values: tuple[tuple[str, Fraction | None], ...] = (
        ("default-x", style.default_x),
        ("default-y", style.default_y),
        ("relative-x", style.relative_x),
        ("relative-y", style.relative_y),
        ("rotation", style.rotation),
    )
    for attribute_name, decimal_value in decimal_values:
        if decimal_value is not None:
            attributes[attribute_name] = _fraction_decimal(decimal_value)
    text_values: tuple[tuple[str, str | None], ...] = (
        ("color", style.color),
        ("font-family", style.font_family),
        ("font-style", style.font_style),
        ("font-weight", style.font_weight),
        ("justify", style.justify),
        ("halign", style.halign),
        ("valign", style.valign),
        ("enclosure", style.enclosure),
        ("dir", style.text_direction),
        ("{http://www.w3.org/XML/1998/namespace}lang", style.language),
        ("{http://www.w3.org/XML/1998/namespace}space", style.space),
    )
    for attribute_name, text_value in text_values:
        if text_value is not None:
            attributes[attribute_name] = text_value
    presentation_values: tuple[tuple[str, PresentationNumber | None], ...] = (
        ("font-size", style.font_size),
        ("letter-spacing", style.letter_spacing),
        ("line-height", style.line_height),
    )
    for attribute_name, presentation_value in presentation_values:
        if presentation_value is not None:
            attributes[attribute_name] = _presentation_number(presentation_value)
    line_values: tuple[tuple[str, int | None], ...] = (
        ("underline", style.underline),
        ("overline", style.overline),
        ("line-through", style.line_through),
    )
    for attribute_name, line_value in line_values:
        if line_value is not None:
            attributes[attribute_name] = str(line_value)
    return attributes


def _presentation_number(value: PresentationNumber) -> str:
    if value.keyword is not None:
        return value.keyword
    assert value.number is not None
    return _fraction_decimal(value.number)


def _write_events(
    parent: ET.Element,
    measure: TemporalMeasure,
    *,
    divisions: int,
    renderer_part_id: str,
    part_index: int,
    measure_index: int,
    anchors: list[RenderAnchor],
) -> None:
    _write_midmeasure_attributes(parent, measure, divisions=divisions)
    if not measure.events and not measure.harmonies:
        _move_cursor(parent, Fraction(0), measure.extent, divisions, measure.id)
        return
    stream: list[tuple[int, int, TemporalEvent | HarmonySymbol]] = [
        (event.source_order, 1, event) for event in measure.events
    ]
    stream.extend((harmony.source_order, 0, harmony) for harmony in measure.harmonies)
    stream.sort(key=lambda item: (item[0], item[1]))
    cursor = Fraction(0)
    chord_leaders = _chord_leaders(list(measure.events))
    event_index = 0
    for _source_order, _kind_order, item in stream:
        if isinstance(item, HarmonySymbol):
            cursor = _move_cursor(parent, cursor, item.anchor.onset, divisions, measure.id)
            _write_harmony(parent, item)
            continue
        event = item
        leader = chord_leaders.get(event.chord_id) if event.chord_id is not None else None
        chord_follower = leader is not None and leader.id != event.id
        if not chord_follower:
            cursor = _move_cursor(parent, cursor, event.onset, divisions, event.id)
        elif (
            leader is None
            or event.onset != leader.onset
            or event.duration != leader.duration
            or event.staff != leader.staff
            or event.voice != leader.voice
        ):
            _unsupported("non-simultaneous chord membership", canonical_id=event.id)

        note = ET.SubElement(parent, "note")
        _write_note(note, event, divisions=divisions, chord_follower=chord_follower)
        anchors.append(
            RenderAnchor(
                canonical_id=event.id,
                canonical_kind="event",
                renderer_anchor=(
                    f"part[{part_index}]/measure[{measure_index}]/event[{event_index}]"
                ),
                renderer_part_id=renderer_part_id,
                part_index=part_index,
                measure_index=measure_index,
                event_index=event_index,
                measure_onset_quarters=str(event.onset),
            )
        )
        event_index += 1
        if not chord_follower and not event.grace:
            cursor = event.onset + event.duration
    _move_cursor(parent, cursor, measure.extent, divisions, measure.id)


def _write_midmeasure_attributes(
    parent: ET.Element,
    measure: TemporalMeasure,
    *,
    divisions: int,
) -> None:
    cursor = Fraction(0)
    for attributes in sorted(
        (item for item in measure.attributes if item.onset > 0),
        key=lambda item: (item.onset, item.source_order),
    ):
        cursor = _move_cursor(parent, cursor, attributes.onset, divisions, measure.id)
        _write_attributes(parent, attributes, divisions=divisions)
    if cursor:
        backup = ET.SubElement(parent, "backup")
        ET.SubElement(backup, "duration").text = str(_duration_units(cursor, divisions))


def _move_cursor(
    parent: ET.Element,
    cursor: Fraction,
    target: Fraction,
    divisions: int,
    canonical_id: str,
) -> Fraction:
    if target < cursor:
        backup = ET.SubElement(parent, "backup")
        ET.SubElement(backup, "duration").text = str(_duration_units(cursor - target, divisions))
    elif target > cursor:
        forward = ET.SubElement(parent, "forward")
        ET.SubElement(forward, "duration").text = str(_duration_units(target - cursor, divisions))
    return target


def _chord_leaders(events: list[TemporalEvent]) -> dict[str, TemporalEvent]:
    leaders: dict[str, TemporalEvent] = {}
    for event in events:
        if event.chord_id is not None:
            leaders.setdefault(event.chord_id, event)
    return leaders


def _write_note(
    parent: ET.Element,
    event: TemporalEvent,
    *,
    divisions: int,
    chord_follower: bool,
) -> None:
    if event.grace:
        assert event.grace_timing is not None
        grace_attributes: dict[str, str] = {}
        timing = event.grace_timing
        if timing.slash is not None:
            grace_attributes["slash"] = _yes_no(timing.slash)
        if timing.make_time is not None:
            grace_attributes["make-time"] = _fraction_decimal(timing.make_time * divisions)
        if timing.steal_previous_percent is not None:
            grace_attributes["steal-time-previous"] = _fraction_decimal(
                timing.steal_previous_percent
            )
        if timing.steal_following_percent is not None:
            grace_attributes["steal-time-following"] = _fraction_decimal(
                timing.steal_following_percent
            )
        ET.SubElement(parent, "grace", grace_attributes)
    if chord_follower:
        ET.SubElement(parent, "chord")
    if event.kind == "pitched":
        assert event.pitch is not None
        pitch = ET.SubElement(parent, "pitch")
        ET.SubElement(pitch, "step").text = event.pitch.step
        if event.pitch.alter:
            ET.SubElement(pitch, "alter").text = _fraction_decimal(event.pitch.alter)
        ET.SubElement(pitch, "octave").text = str(event.pitch.octave)
    else:
        rest_attributes = (
            {"measure": _yes_no(event.measure_rest)} if event.measure_rest is not None else {}
        )
        ET.SubElement(parent, "rest", rest_attributes)
    if not event.grace:
        ET.SubElement(parent, "duration").text = str(_duration_units(event.duration, divisions))
    for marker in sorted(event.span_markers, key=lambda item: item.source_order):
        if marker.kind == "sounding-tie":
            attributes = {"type": marker.action}
            if marker.time_only is not None:
                attributes["time-only"] = marker.time_only
            ET.SubElement(parent, "tie", attributes)
    ET.SubElement(parent, "voice").text = event.voice
    if event.written_type is not None:
        ET.SubElement(parent, "type").text = event.written_type
    for _ in range(event.dots):
        ET.SubElement(parent, "dot")
    if event.accidental is not None:
        _write_accidental(parent, event)
    if event.time_modification is not None:
        actual, normal = event.time_modification
        time_modification = ET.SubElement(parent, "time-modification")
        ET.SubElement(time_modification, "actual-notes").text = str(actual)
        ET.SubElement(time_modification, "normal-notes").text = str(normal)
        if event.normal_type is not None:
            ET.SubElement(time_modification, "normal-type").text = event.normal_type
        for _ in range(event.normal_dots):
            ET.SubElement(time_modification, "normal-dot")
    if event.stem is not None:
        ET.SubElement(parent, "stem").text = event.stem
    if event.notehead_marker is not None:
        _write_notehead(parent, event.notehead_marker)
    ET.SubElement(parent, "staff").text = event.staff
    for beam in event.beams:
        beam_attributes = {"number": str(beam.number)}
        if beam.repeater is not None:
            beam_attributes["repeater"] = _yes_no(beam.repeater)
        if beam.fan is not None:
            beam_attributes["fan"] = beam.fan
        ET.SubElement(parent, "beam", beam_attributes).text = beam.value
    if (
        event.tuplets
        or any(marker.kind != "sounding-tie" for marker in event.span_markers)
        or event.event_markers
    ):
        notations = ET.SubElement(parent, "notations")
        for marker in sorted(event.span_markers, key=lambda item: item.source_order):
            if marker.kind != "sounding-tie":
                _write_span_marker(notations, marker)
        for tuplet in event.tuplets:
            _write_tuplet(notations, tuplet)
        _write_event_marks(notations, event.event_markers)
    for lyric in sorted(event.lyric_markers, key=lambda item: item.source_order):
        _write_lyric(parent, lyric)


def _write_notehead(parent: ET.Element, marker: NoteheadMarker) -> None:
    if marker.value is not None:
        attributes: dict[str, str] = {}
        if marker.filled is not None:
            attributes["filled"] = _yes_no(marker.filled)
        if marker.parentheses is not None:
            attributes["parentheses"] = _yes_no(marker.parentheses)
        if marker.smufl is not None:
            attributes["smufl"] = marker.smufl
        ET.SubElement(parent, "notehead", attributes).text = marker.value
    if marker.text:
        notehead_text = ET.SubElement(parent, "notehead-text")
        for segment in marker.text:
            ET.SubElement(notehead_text, segment.kind).text = segment.text


def _write_span_marker(parent: ET.Element, marker: SpanMarker) -> None:
    if marker.kind in {"notated-tie", "slur"}:
        element = ET.SubElement(
            parent,
            "tied" if marker.kind == "notated-tie" else "slur",
            _span_attributes(marker),
        )
    elif marker.kind in {"glissando", "slide", "other-notation"}:
        element = ET.SubElement(parent, marker.kind, _span_attributes(marker))
        element.text = marker.text
    elif marker.kind in {"wavy-line", "tremolo"}:
        ornaments = ET.SubElement(parent, "ornaments")
        attributes = _span_attributes(marker)
        if marker.kind == "wavy-line":
            _add_trill_attributes(attributes, marker.playback)
        element = ET.SubElement(ornaments, marker.kind, attributes)
        if marker.kind == "tremolo":
            assert marker.tremolo_marks is not None
            element.text = str(marker.tremolo_marks)
        for accidental in marker.accidentals:
            _write_ornament_accidental(ornaments, accidental)
    elif marker.kind in {"hammer-on", "pull-off"}:
        technical = ET.SubElement(parent, "technical")
        element = ET.SubElement(technical, marker.kind, _span_attributes(marker))
        element.text = marker.text
    else:  # guarded by _require_supported_span_marker
        raise AssertionError(f"unsupported note span: {marker.kind}")
    if marker.kind == "slide" and marker.bend_sound is not None:
        sound = marker.bend_sound
        if sound.accelerate is not None:
            element.set("accelerate", _yes_no(sound.accelerate))
        for name, value in (
            ("beats", sound.beats),
            ("first-beat", sound.first_beat),
            ("last-beat", sound.last_beat),
        ):
            if value is not None:
                element.set(name, _fraction_decimal(value))


def _span_attributes(marker: SpanMarker) -> dict[str, str]:
    attributes = {"type": marker.action}
    if marker.kind != "tremolo":
        attributes["number"] = marker.number
    for name, value in (
        ("placement", marker.placement),
        ("smufl", marker.smufl),
        ("id", marker.source_id),
        ("line-type", marker.line_type),
        ("orientation", marker.orientation),
        ("time-only", marker.time_only),
    ):
        if value is not None:
            attributes[name] = value
    if marker.dash_length is not None:
        attributes["dash-length"] = _fraction_decimal(marker.dash_length)
    if marker.space_length is not None:
        attributes["space-length"] = _fraction_decimal(marker.space_length)
    if marker.print_object is not None:
        attributes["print-object"] = _yes_no(marker.print_object)
    return attributes


def _write_event_marks(parent: ET.Element, markers: tuple[EventMarkMarker, ...]) -> None:
    ordered = sorted(markers, key=lambda item: item.source_order)
    index = 0
    while index < len(ordered):
        marker = ordered[index]
        if marker.family == "notation":
            _write_direct_event_mark(parent, marker)
            index += 1
            continue
        if marker.family == "ornament" and marker.kind == "accidental-mark":
            _write_standalone_accidental_mark(parent, marker)
            index += 1
            continue
        container_name = {
            "articulation": "articulations",
            "ornament": "ornaments",
            "technical": "technical",
            "dynamic": "dynamics",
        }[marker.family]
        container_attributes: dict[str, str] = {}
        if marker.group_id is not None:
            container_attributes["id"] = marker.group_id
        if marker.family == "dynamic" and marker.placement is not None:
            container_attributes["placement"] = marker.placement
        container = ET.SubElement(parent, container_name, container_attributes)
        group_key = (
            marker.family,
            marker.group_id,
            marker.placement if marker.family == "dynamic" else None,
        )
        while index < len(ordered):
            candidate = ordered[index]
            candidate_key = (
                candidate.family,
                candidate.group_id,
                candidate.placement if candidate.family == "dynamic" else None,
            )
            if (
                candidate.family == "notation"
                or candidate.kind == "accidental-mark"
                or candidate_key != group_key
            ):
                break
            _write_grouped_event_mark(container, candidate)
            index += 1


def _write_standalone_accidental_mark(parent: ET.Element, marker: EventMarkMarker) -> None:
    accidental = OrnamentAccidental(
        value=marker.text or "",
        placement=marker.placement,
        bracket=marker.bracket,
        parentheses=marker.parentheses,
        smufl=marker.smufl,
    )
    _write_ornament_accidental(parent, accidental)


def _write_direct_event_mark(parent: ET.Element, marker: EventMarkMarker) -> None:
    attributes = _event_mark_attributes(marker)
    if marker.group_id is not None:
        attributes["id"] = marker.group_id
    if marker.kind == "fermata" and marker.mark_type is not None:
        attributes["type"] = marker.mark_type
    elif marker.kind == "arpeggiate" and marker.mark_type is not None:
        attributes["direction"] = marker.mark_type
    elif marker.kind == "non-arpeggiate" and marker.mark_type is not None:
        attributes["type"] = marker.mark_type
    elif marker.kind == "other-notation":
        attributes["type"] = marker.mark_type or "single"
    if marker.number is not None:
        attributes["number"] = marker.number
    if marker.unbroken is not None:
        attributes["unbroken"] = _yes_no(marker.unbroken)
    element = ET.SubElement(parent, marker.kind, attributes)
    element.text = marker.text


def _write_grouped_event_mark(parent: ET.Element, marker: EventMarkMarker) -> None:
    attributes = _event_mark_attributes(marker, include_placement=marker.family != "dynamic")
    if marker.mark_type is not None:
        attributes["type"] = marker.mark_type
    if marker.family == "ornament":
        _add_trill_attributes(attributes, marker.playback)
        if marker.slash is not None:
            attributes["slash"] = _yes_no(marker.slash)
        if marker.long is not None:
            attributes["long"] = _yes_no(marker.long)
        if marker.approach is not None:
            attributes["approach"] = marker.approach
        if marker.departure is not None:
            attributes["departure"] = marker.departure
    element = ET.SubElement(parent, marker.kind, attributes)
    if marker.kind == "tremolo":
        assert marker.tremolo_marks is not None
        element.text = str(marker.tremolo_marks)
    else:
        element.text = marker.text
    for accidental in marker.accidentals:
        _write_ornament_accidental(parent, accidental)


def _event_mark_attributes(
    marker: EventMarkMarker, *, include_placement: bool = True
) -> dict[str, str]:
    attributes: dict[str, str] = {}
    if include_placement and marker.placement is not None:
        attributes["placement"] = marker.placement
    for name, value in (
        ("smufl", marker.smufl),
        ("line-shape", marker.line_shape),
        ("line-type", marker.line_type),
    ):
        if value is not None:
            attributes[name] = value
    if marker.bracket is not None:
        attributes["bracket"] = _yes_no(marker.bracket)
    if marker.parentheses is not None:
        attributes["parentheses"] = _yes_no(marker.parentheses)
    if marker.print_object is not None:
        attributes["print-object"] = _yes_no(marker.print_object)
    return attributes


def _add_trill_attributes(attributes: dict[str, str], playback: TrillPlayback | None) -> None:
    if playback is None:
        return
    for name, value in (
        ("start-note", playback.start_note),
        ("trill-step", playback.trill_step),
        ("two-note-turn", playback.two_note_turn),
    ):
        if value is not None:
            attributes[name] = value
    if playback.accelerate is not None:
        attributes["accelerate"] = _yes_no(playback.accelerate)
    if playback.beats is not None:
        attributes["beats"] = _fraction_decimal(playback.beats)
    if playback.second_beat is not None:
        attributes["second-beat"] = _fraction_decimal(playback.second_beat)
    if playback.last_beat is not None:
        attributes["last-beat"] = _fraction_decimal(playback.last_beat)


def _write_ornament_accidental(parent: ET.Element, accidental: OrnamentAccidental) -> None:
    attributes: dict[str, str] = {}
    if accidental.placement is not None:
        attributes["placement"] = accidental.placement
    if accidental.smufl is not None:
        attributes["smufl"] = accidental.smufl
    for name, value in (
        ("bracket", accidental.bracket),
        ("parentheses", accidental.parentheses),
    ):
        if value is not None:
            attributes[name] = _yes_no(value)
    ET.SubElement(parent, "accidental-mark", attributes).text = accidental.value


def _write_tuplet(parent: ET.Element, tuplet: TemporalTuplet) -> None:
    attributes = {"type": tuplet.action, "number": tuplet.number}
    if tuplet.bracket is not None:
        attributes["bracket"] = _yes_no(tuplet.bracket)
    if tuplet.placement is not None:
        attributes["placement"] = tuplet.placement
    if tuplet.show_number is not None:
        attributes["show-number"] = tuplet.show_number
    if tuplet.show_type is not None:
        attributes["show-type"] = tuplet.show_type
    if tuplet.line_shape is not None:
        attributes["line-shape"] = tuplet.line_shape
    element = ET.SubElement(parent, "tuplet", attributes)
    _write_tuplet_portion(element, "tuplet-actual", tuplet.actual)
    _write_tuplet_portion(element, "tuplet-normal", tuplet.normal)


def _write_tuplet_portion(
    parent: ET.Element,
    name: str,
    portion: TemporalTupletPortion | None,
) -> None:
    if portion is None:
        return
    element = ET.SubElement(parent, name)
    if portion.number is not None:
        ET.SubElement(element, "tuplet-number").text = str(portion.number)
    if portion.note_type is not None:
        ET.SubElement(element, "tuplet-type").text = portion.note_type
    for _ in range(portion.dots):
        ET.SubElement(element, "tuplet-dot")


def _write_accidental(parent: ET.Element, event: TemporalEvent) -> None:
    assert event.accidental is not None
    accidental = event.accidental
    attributes: dict[str, str] = {}
    for name, value in (
        ("cautionary", accidental.cautionary),
        ("editorial", accidental.editorial),
        ("parentheses", accidental.parentheses),
        ("bracket", accidental.bracket),
    ):
        if value is not None:
            attributes[name] = _yes_no(value)
    if accidental.size is not None:
        attributes["size"] = accidental.size
    if accidental.smufl is not None:
        attributes["smufl"] = accidental.smufl
    ET.SubElement(parent, "accidental", attributes).text = accidental.value


def _write_harmony(parent: ET.Element, harmony: HarmonySymbol) -> None:
    attributes: dict[str, str] = {}
    if harmony.print_object is not None:
        attributes["print-object"] = _yes_no(harmony.print_object)
    if harmony.print_frame is not None:
        attributes["print-frame"] = _yes_no(harmony.print_frame)
    element = ET.SubElement(parent, "harmony", attributes)
    root = ET.SubElement(element, "root")
    assert harmony.root_step is not None
    ET.SubElement(root, "root-step").text = harmony.root_step
    if harmony.root_alter:
        ET.SubElement(root, "root-alter").text = _fraction_decimal(harmony.root_alter)
    chord = harmony.chords[0]
    kind_attributes: dict[str, str] = {}
    if chord.kind_text is not None:
        kind_attributes["text"] = chord.kind_text
    if chord.use_symbols is not None:
        kind_attributes["use-symbols"] = _yes_no(chord.use_symbols)
    if chord.stack_degrees is not None:
        kind_attributes["stack-degrees"] = _yes_no(chord.stack_degrees)
    if chord.parentheses_degrees is not None:
        kind_attributes["parentheses-degrees"] = _yes_no(chord.parentheses_degrees)
    if chord.bracket_degrees is not None:
        kind_attributes["bracket-degrees"] = _yes_no(chord.bracket_degrees)
    ET.SubElement(element, "kind", kind_attributes).text = harmony.kind
    if harmony.anchor.staff is not None:
        ET.SubElement(element, "staff").text = harmony.anchor.staff


def _write_lyric(parent: ET.Element, lyric: LyricMarker) -> None:
    attributes: dict[str, str] = {}
    if lyric.number is not None:
        attributes["number"] = lyric.number
    if lyric.print_object is not None:
        attributes["print-object"] = _yes_no(lyric.print_object)
    lyric_element = ET.SubElement(parent, "lyric", attributes)
    if lyric.syllabic is not None:
        ET.SubElement(lyric_element, "syllabic").text = lyric.syllabic
    ET.SubElement(lyric_element, "text").text = lyric.text


def _write_barline(parent: ET.Element, barline: TemporalBarline) -> None:
    attributes: dict[str, str] = {}
    if barline.location is not None:
        attributes["location"] = barline.location
    if barline.divisions is not None:
        attributes["divisions"] = _fraction_decimal(barline.divisions)
    if barline.source_id is not None:
        attributes["id"] = barline.source_id
    element = ET.SubElement(parent, "barline", attributes)
    if barline.style is not None:
        ET.SubElement(element, "bar-style").text = barline.style
    for marker in barline.navigation:
        marker_attributes: dict[str, str] = {}
        if marker.source_id is not None:
            marker_attributes["id"] = marker.source_id
        if marker.smufl is not None:
            marker_attributes["smufl"] = marker.smufl
        ET.SubElement(element, marker.kind, marker_attributes).text = marker.token
    for fermata in barline.fermatas:
        fermata_attributes: dict[str, str] = {}
        if fermata.orientation is not None:
            fermata_attributes["type"] = fermata.orientation
        if fermata.source_id is not None:
            fermata_attributes["id"] = fermata.source_id
        ET.SubElement(element, "fermata", fermata_attributes).text = fermata.shape
    if barline.ending_type is not None:
        ending_attributes = {"type": barline.ending_type}
        if barline.ending_number is not None:
            ending_attributes["number"] = barline.ending_number
        if barline.ending_print_object is not None:
            ending_attributes["print-object"] = _yes_no(barline.ending_print_object)
        if barline.ending_system_relation is not None:
            ending_attributes["system"] = barline.ending_system_relation
        ET.SubElement(element, "ending", ending_attributes).text = barline.ending_text
    if barline.repeat_direction is not None:
        repeat_attributes = {"direction": barline.repeat_direction}
        if barline.repeat_times is not None:
            repeat_attributes["times"] = barline.repeat_times
        if barline.repeat_winged is not None:
            repeat_attributes["winged"] = barline.repeat_winged
        if barline.repeat_after_jump is not None:
            repeat_attributes["after-jump"] = _yes_no(barline.repeat_after_jump)
        ET.SubElement(element, "repeat", repeat_attributes)


def _duration_units(value: Fraction, divisions: int) -> int:
    units = value * divisions
    if units.denominator != 1 or units <= 0:
        raise NotationProjectionError(
            "VIEWER_NOTATION_DURATION",
            "canonical duration cannot be represented by the selected divisions",
        )
    return units.numerator


def _offset_units(value: Fraction, divisions: int) -> int:
    units = value * divisions
    if units.denominator != 1:
        raise NotationProjectionError(
            "VIEWER_NOTATION_OFFSET",
            "canonical offset cannot be represented by the selected divisions",
        )
    return units.numerator


def _fraction_decimal(value: Fraction) -> str:
    denominator = value.denominator
    while denominator % 2 == 0:
        denominator //= 2
    while denominator % 5 == 0:
        denominator //= 5
    if denominator != 1:
        raise NotationProjectionError(
            "VIEWER_NOTATION_DECIMAL",
            "a canonical rational is not exactly representable as a MusicXML decimal",
        )
    sign = "-" if value < 0 else ""
    numerator = abs(value.numerator)
    denominator = value.denominator
    scale = max(_factor_count(denominator, 2), _factor_count(denominator, 5))
    scaled = numerator * (10**scale // denominator)
    if scale == 0:
        return f"{sign}{scaled}"
    digits = str(scaled).zfill(scale + 1)
    text = f"{digits[:-scale]}.{digits[-scale:]}".rstrip("0").rstrip(".")
    return f"{sign}{text}"


def _factor_count(value: int, factor: int) -> int:
    count = 0
    while value % factor == 0:
        value //= factor
        count += 1
    return count


def _yes_no(value: bool) -> str:
    return "yes" if value else "no"


def _normalization_diagnostics(
    document: ScoreDocument, score: TemporalScore
) -> tuple[ViewerDiagnostic, ...]:
    diagnostics: list[ViewerDiagnostic] = []
    has_layout = score.layout is not None or any(
        measure.layout is not None
        and any(
            item is not None
            for item in (
                measure.layout.width,
                measure.layout.page,
                measure.layout.system,
                measure.layout.measure_distance,
                measure.layout.staff_spacing,
            )
        )
        for part in score.parts
        for measure in part.measures
    )
    has_source_positioning = bool(score.source_presentations) or any(
        event.presentation is not None
        for part in score.parts
        for measure in part.measures
        for event in measure.events
    )
    if has_layout or has_source_positioning:
        diagnostics.append(
            ViewerDiagnostic(
                code="VIEWER_NOTATION_LAYOUT_NORMALIZED",
                severity=DiagnosticSeverity.INFO,
                message=(
                    "OSMD owns engraving geometry; exact source coordinates, widths, fonts, "
                    "and page geometry are not asserted by this renderer projection"
                ),
                canonical_ids=(document.id.value,),
            )
        )
    if score.metadata.encoding is not None or score.metadata.miscellaneous:
        diagnostics.append(
            ViewerDiagnostic(
                code="VIEWER_NOTATION_EXPORT_METADATA_EXCLUDED",
                severity=DiagnosticSeverity.INFO,
                message=(
                    "source-application encoding and miscellaneous metadata are canonical "
                    "evidence but are not notation-renderer input"
                ),
                canonical_ids=(document.id.value,),
            )
        )
    if _has_stop_only_wavy_line(score) or _has_inferred_time_span_endpoint(score):
        diagnostics.append(
            ViewerDiagnostic(
                code="VIEWER_NOTATION_RECOVERY_PROVENANCE_RETAINED",
                severity=DiagnosticSeverity.INFO,
                message=(
                    "the MuseScore 2 software signature required to preserve validated "
                    "wavy-line or adjacent-wedge recovery was retained in renderer "
                    "interchange"
                ),
                canonical_ids=(document.id.value,),
            )
        )
    if any(measure.cursor_moves for part in score.parts for measure in part.measures):
        diagnostics.append(
            ViewerDiagnostic(
                code="VIEWER_NOTATION_CURSOR_RECONSTRUCTED",
                severity=DiagnosticSeverity.INFO,
                message=(
                    "source backup/forward operations were deterministically reconstructed "
                    "from canonical staff, voice, onset, duration, and chord facts"
                ),
                canonical_ids=(document.id.value,),
            )
        )
    selected_divisions = _score_divisions(score)
    if any(
        attributes.divisions is not None and attributes.divisions != selected_divisions
        for part in score.parts
        for measure in part.measures
        for attributes in measure.attributes
    ):
        diagnostics.append(
            ViewerDiagnostic(
                code="VIEWER_NOTATION_DIVISIONS_NORMALIZED",
                severity=DiagnosticSeverity.INFO,
                message=(
                    "source divisions changes were normalized to one exact renderer "
                    f"division value ({selected_divisions}) without changing musical time"
                ),
                canonical_ids=(document.id.value,),
            )
        )
    if any(
        attributes.onset > 0
        for part in score.parts
        for measure in part.measures
        for attributes in measure.attributes
    ):
        diagnostics.append(
            ViewerDiagnostic(
                code="VIEWER_NOTATION_ATTRIBUTE_CURSOR_RECONSTRUCTED",
                severity=DiagnosticSeverity.INFO,
                message=(
                    "mid-measure attribute changes were placed from their exact canonical "
                    "onsets on the reconstructed renderer cursor"
                ),
                canonical_ids=(document.id.value,),
            )
        )
    if any(measure.time_span_markers for part in score.parts for measure in part.measures):
        diagnostics.append(
            ViewerDiagnostic(
                code="VIEWER_NOTATION_DIRECTION_PLACEMENT_NORMALIZED",
                severity=DiagnosticSeverity.INFO,
                message=(
                    "canonical direction-span markers do not retain source placement; "
                    "the renderer applies conventional above/below placement for stable "
                    "OSMD display"
                ),
                canonical_ids=(document.id.value,),
            )
        )
    inline_symbol_directions = tuple(
        (measure.id, direction.value)
        for part in score.parts
        for measure in part.measures
        for direction in measure.directions
        if "<sym>" in direction.value
    )
    if inline_symbol_directions:
        fully_mapped = all(
            "<sym>" not in _INLINE_DYNAMIC_SYMBOL_PATTERN.sub("", value)
            for _, value in inline_symbol_directions
        )
        diagnostics.append(
            ViewerDiagnostic(
                code=(
                    "VIEWER_NOTATION_INLINE_DYNAMIC_SYMBOL_NORMALIZED"
                    if fully_mapped
                    else "VIEWER_NOTATION_INLINE_SYMBOL_TEXT_UNSUPPORTED"
                ),
                severity=(DiagnosticSeverity.INFO if fully_mapped else DiagnosticSeverity.WARNING),
                message=(
                    "the source stores one or more exporter-specific <sym> tokens inside "
                    "direction text; their exact canonical text is retained while the "
                    "browser applies only its bounded, declared dynamic-symbol mapping"
                ),
                canonical_ids=tuple(measure_id for measure_id, _ in inline_symbol_directions),
            )
        )
    return tuple(diagnostics)
