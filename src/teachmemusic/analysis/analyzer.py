"""Deterministic analysis of complete canonical score content."""

from __future__ import annotations

import hashlib
from collections import defaultdict
from collections.abc import Iterable
from fractions import Fraction

from teachmemusic.score import (
    CanonicalMusicPackage,
    CanonicalScoreContent,
    ScoreDocument,
    package_to_json,
    require_valid_package,
)
from teachmemusic.score.v2.temporal import TemporalEvent, TemporalMeasure, TemporalPart

from .contracts import (
    ANALYSIS_VERSION,
    AnalysisConfidence,
    AnalysisDemandDimension,
    AnalysisDerivation,
    AnalysisFact,
    AnalysisFactKind,
    AnalysisScope,
    BoundaryCandidate,
    BoundaryReason,
    DemandEstimate,
    LayerProfile,
    RepetitionGroup,
    RepetitionKind,
    RhythmProfile,
    ScoreAnalysis,
    TextureProfile,
)
from .validation import require_valid_score_analysis


class AnalysisError(ValueError):
    """Raised when canonical content cannot be analyzed without invention."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(f"{code}: {message}")


def analyze_canonical_score(
    package: CanonicalMusicPackage,
    *,
    score_id: str | None = None,
    part_ids: tuple[str, ...] = (),
    start_measure_ordinal: int = 1,
    end_measure_ordinal: int | None = None,
) -> ScoreAnalysis:
    """Analyze one canonical score slice with deterministic public rules."""

    require_valid_package(package)
    document = _select_score_document(package, score_id)
    if not isinstance(document.content, CanonicalScoreContent):
        raise AnalysisError("ANALYSIS_INCOMPLETE_SCORE", "score content is not complete")
    score = document.content.score
    selected_parts = _select_parts(score.parts, part_ids)
    if start_measure_ordinal < 1:
        raise AnalysisError("ANALYSIS_SCOPE", "start measure ordinal must be positive")
    available_end = max(
        (measure.ordinal for part in selected_parts for measure in part.measures),
        default=0,
    )
    selected_end = available_end if end_measure_ordinal is None else end_measure_ordinal
    if end_measure_ordinal is not None and end_measure_ordinal > available_end:
        raise AnalysisError(
            "ANALYSIS_SCOPE",
            f"end measure ordinal {end_measure_ordinal} exceeds available {available_end}",
        )
    if selected_end < start_measure_ordinal:
        raise AnalysisError("ANALYSIS_SCOPE", "end measure ordinal precedes start")
    scoped_parts = tuple(
        (
            part,
            tuple(
                measure
                for measure in part.measures
                if start_measure_ordinal <= measure.ordinal <= selected_end
            ),
        )
        for part in selected_parts
    )
    if not any(measures for _, measures in scoped_parts):
        raise AnalysisError("ANALYSIS_SCOPE_EMPTY", "scope contains no measures")

    digest = hashlib.sha256(package_to_json(package).encode("utf-8")).hexdigest()
    scope = AnalysisScope(
        package_id=package.id.value,
        score_id=document.id.value,
        part_ids=tuple(part.id for part, _ in scoped_parts),
        start_measure_ordinal=start_measure_ordinal,
        end_measure_ordinal=selected_end,
    )
    token = hashlib.sha256(
        (
            f"{ANALYSIS_VERSION}|{digest}|{scope.score_id}|"
            f"{','.join(scope.part_ids)}|{start_measure_ordinal}|{selected_end}"
        ).encode()
    ).hexdigest()[:24]
    analysis_id = f"analysis:{token}"
    layers = _build_layers(scoped_parts, token)
    events = tuple(
        event for _, measures in scoped_parts for measure in measures for event in measure.events
    )
    rhythm = _build_rhythm(events)
    texture = _build_texture(scoped_parts, layers)
    repetitions = _build_repetitions(scoped_parts, layers, token)
    boundaries = _build_boundaries(scoped_parts, repetitions, token)
    facts = _build_facts(scoped_parts, events, rhythm, texture, token)
    demands = _build_demands(
        scoped_parts,
        layers,
        events,
        rhythm,
        texture,
        repetitions,
        token,
    )
    limitations = (
        "Candidate boundaries are deterministic proposals, not phrase labels or lesson decisions.",
        "Task-demand levels use transparent structural thresholds and are not learner "
        "ability labels.",
        "Fingering, posture, tension, tone quality, and physical safety are not "
        "inferred from notation.",
    )
    result = ScoreAnalysis(
        id=analysis_id,
        canonical_digest_sha256=digest,
        analysis_version=ANALYSIS_VERSION,
        scope=scope,
        facts=facts,
        layers=layers,
        rhythm=rhythm,
        texture=texture,
        repetitions=repetitions,
        boundaries=boundaries,
        demands=demands,
        limitations=limitations,
    )
    require_valid_score_analysis(result, package)
    return result


def _select_score_document(
    package: CanonicalMusicPackage,
    score_id: str | None,
) -> ScoreDocument:
    scores = tuple(item for item in package.documents if isinstance(item, ScoreDocument))
    if score_id is not None:
        scores = tuple(item for item in scores if item.id.value == score_id)
    if len(scores) != 1:
        raise AnalysisError(
            "ANALYSIS_SCORE_SELECTION",
            "exactly one complete score document must be selected",
        )
    return scores[0]


def _select_parts(
    parts: tuple[TemporalPart, ...],
    part_ids: tuple[str, ...],
) -> tuple[TemporalPart, ...]:
    if not part_ids:
        return parts
    if len(set(part_ids)) != len(part_ids):
        raise AnalysisError("ANALYSIS_SCOPE", "part selection contains duplicates")
    by_id = {part.id: part for part in parts}
    missing = tuple(identifier for identifier in part_ids if identifier not in by_id)
    if missing:
        raise AnalysisError("ANALYSIS_PART_REFERENCE", f"unknown part IDs: {missing!r}")
    return tuple(by_id[identifier] for identifier in part_ids)


def _build_layers(
    scoped_parts: tuple[tuple[TemporalPart, tuple[TemporalMeasure, ...]], ...],
    token: str,
) -> tuple[LayerProfile, ...]:
    collected: dict[tuple[str, str, str], list[tuple[TemporalMeasure, TemporalEvent]]] = (
        defaultdict(list)
    )
    for part, measures in scoped_parts:
        for measure in measures:
            for event in measure.events:
                collected[(part.id, event.staff, event.voice)].append((measure, event))
    result: list[LayerProfile] = []
    for key in sorted(collected):
        part_id, source_staff, source_voice = key
        part = next(item for item, _ in scoped_parts if item.id == part_id)
        staff_id = next(
            (staff.id for staff in part.staves if staff.source_number == source_staff),
            None,
        )
        voice_id = next(
            (voice.id for voice in part.voices if voice.source_id == source_voice),
            None,
        )
        if staff_id is None or voice_id is None:
            raise AnalysisError(
                "ANALYSIS_LAYER_REFERENCE",
                f"event layer {source_staff!r}/{source_voice!r} has no canonical identity",
            )
        entries = collected[key]
        pitches = tuple(
            _written_semitone(event)
            for _, event in entries
            if event.kind == "pitched" and event.pitch is not None and not event.grace
        )
        layer_token = hashlib.sha256("|".join((part_id, staff_id, voice_id)).encode()).hexdigest()[
            :16
        ]
        result.append(
            LayerProfile(
                id=f"analysis-layer:{token}:{layer_token}",
                part_id=part_id,
                staff_id=staff_id,
                voice_id=voice_id,
                measure_ids=tuple(dict.fromkeys(measure.id for measure, _ in entries)),
                event_ids=tuple(event.id for _, event in entries),
                pitched_event_count=sum(event.kind == "pitched" for _, event in entries),
                unpitched_event_count=sum(event.kind == "unpitched" for _, event in entries),
                rest_event_count=sum(event.kind == "rest" for _, event in entries),
                distinct_onset_count=len(
                    {
                        measure.score_onset + event.onset
                        for measure, event in entries
                        if not event.grace
                    }
                ),
                lowest_written_semitone=min(pitches, default=None),
                highest_written_semitone=max(pitches, default=None),
            )
        )
    return tuple(result)


def _build_rhythm(events: tuple[TemporalEvent, ...]) -> RhythmProfile:
    nongrace = tuple(event for event in events if not event.grace)
    durations = tuple(sorted({event.duration for event in nongrace}))
    return RhythmProfile(
        written_durations=durations,
        shortest_duration=min((event.duration for event in nongrace), default=None),
        longest_duration=max((event.duration for event in nongrace), default=None),
        dotted_event_count=sum(event.dots > 0 for event in events),
        tuplet_event_count=sum(bool(event.tuplets or event.time_modification) for event in events),
        grace_event_count=sum(event.grace for event in events),
        distinct_onset_count=len({event.score_onset for event in nongrace}),
        evidence_event_ids=tuple(event.id for event in events),
    )


def _build_texture(
    scoped_parts: tuple[tuple[TemporalPart, tuple[TemporalMeasure, ...]], ...],
    layers: tuple[LayerProfile, ...],
) -> TextureProfile:
    pitched_by_onset: dict[Fraction, list[TemporalEvent]] = defaultdict(list)
    active_layers_by_onset: dict[Fraction, set[tuple[str, str, str]]] = defaultdict(set)
    chord_ids: set[str] = set()
    evidence: list[str] = []
    staffs: set[tuple[str, str]] = set()
    voices: set[tuple[str, str]] = set()
    for part, measures in scoped_parts:
        for measure in measures:
            for event in measure.events:
                evidence.append(event.id)
                onset = measure.score_onset + event.onset
                if event.kind != "rest" and not event.grace:
                    active_layers_by_onset[onset].add((part.id, event.staff, event.voice))
                if event.kind == "pitched" and event.pitch is not None and not event.grace:
                    pitched_by_onset[onset].append(event)
                if event.chord_id is not None:
                    chord_ids.add(event.chord_id)
                staffs.add((part.id, event.staff))
                voices.add((part.id, event.voice))
    return TextureProfile(
        layer_count=len(layers),
        staff_count=len(staffs),
        voice_count=len(voices),
        chord_count=len(chord_ids),
        max_simultaneous_pitches=max(map(len, pitched_by_onset.values()), default=0),
        max_active_layers=max(map(len, active_layers_by_onset.values()), default=0),
        evidence_ids=tuple(evidence),
    )


def _build_repetitions(
    scoped_parts: tuple[tuple[TemporalPart, tuple[TemporalMeasure, ...]], ...],
    layers: tuple[LayerProfile, ...],
    token: str,
) -> tuple[RepetitionGroup, ...]:
    layer_ids: dict[tuple[str, str, str], str] = {}
    for part, _ in scoped_parts:
        canonical_staff = {staff.source_number: staff.id for staff in part.staves}
        canonical_voice = {voice.source_id: voice.id for voice in part.voices}
        for layer in layers:
            if layer.part_id != part.id:
                continue
            source_staff = next(
                source
                for source, identifier in canonical_staff.items()
                if identifier == layer.staff_id
            )
            source_voice = next(
                source
                for source, identifier in canonical_voice.items()
                if identifier == layer.voice_id
            )
            layer_ids[(part.id, source_staff, source_voice)] = layer.id
    exact: dict[tuple[str, tuple[object, ...]], list[tuple[str, tuple[str, ...]]]] = defaultdict(
        list
    )
    rhythm: dict[tuple[str, tuple[object, ...]], list[tuple[str, tuple[str, ...]]]] = defaultdict(
        list
    )
    for part, measures in scoped_parts:
        for measure in measures:
            grouped: dict[tuple[str, str], list[TemporalEvent]] = defaultdict(list)
            for event in measure.events:
                grouped[(event.staff, event.voice)].append(event)
            for (staff, voice), events in grouped.items():
                layer_id = layer_ids[(part.id, staff, voice)]
                ordered = tuple(
                    sorted(events, key=lambda item: (item.onset, item.source_order, item.id))
                )
                event_ids = tuple(event.id for event in ordered)
                exact[(layer_id, _measure_signature(ordered, include_pitch=True))].append(
                    (measure.id, event_ids)
                )
                rhythm[(layer_id, _measure_signature(ordered, include_pitch=False))].append(
                    (measure.id, event_ids)
                )
    result: list[RepetitionGroup] = []
    for kind, groups in (
        (RepetitionKind.EXACT_PITCH_AND_RHYTHM, exact),
        (RepetitionKind.RHYTHM_ONLY, rhythm),
    ):
        for (layer_id, _), occurrences in sorted(groups.items(), key=lambda item: str(item[0])):
            if len(occurrences) < 2:
                continue
            measure_ids = tuple(item[0] for item in occurrences)
            identity = hashlib.sha256(
                f"{kind.value}|{layer_id}|{'|'.join(measure_ids)}".encode()
            ).hexdigest()[:16]
            result.append(
                RepetitionGroup(
                    id=f"analysis-repetition:{token}:{identity}",
                    kind=kind,
                    layer_id=layer_id,
                    occurrence_measure_ids=measure_ids,
                    evidence_event_ids=tuple(
                        event_id for _, event_ids in occurrences for event_id in event_ids
                    ),
                )
            )
    return tuple(sorted(result, key=lambda item: (item.kind.value, item.layer_id, item.id)))


def _measure_signature(
    events: tuple[TemporalEvent, ...],
    *,
    include_pitch: bool,
) -> tuple[object, ...]:
    return tuple(
        (
            event.kind,
            event.onset,
            event.duration,
            None
            if not include_pitch or event.pitch is None
            else (event.pitch.step, event.pitch.alter, event.pitch.octave),
            event.chord_id is not None,
            event.grace,
        )
        for event in events
    )


def _build_boundaries(
    scoped_parts: tuple[tuple[TemporalPart, tuple[TemporalMeasure, ...]], ...],
    repetitions: tuple[RepetitionGroup, ...],
    token: str,
) -> tuple[BoundaryCandidate, ...]:
    by_ordinal: dict[int, list[TemporalMeasure]] = defaultdict(list)
    for _, measures in scoped_parts:
        for measure in measures:
            by_ordinal[measure.ordinal].append(measure)
    ordinals = sorted(by_ordinal)
    repeated_entries = {
        identifier for group in repetitions for identifier in group.occurrence_measure_ids[1:]
    }
    result: list[BoundaryCandidate] = []
    previous: list[TemporalMeasure] | None = None
    for ordinal in ordinals:
        current = sorted(by_ordinal[ordinal], key=lambda item: item.id)
        reasons: list[BoundaryReason] = []
        evidence: list[str] = [measure.id for measure in current]
        if previous is None:
            reasons.append(BoundaryReason.SCOPE_START)
        else:
            evidence.extend(measure.id for measure in previous)
            if any(_has_terminal_rest(measure) for measure in previous):
                reasons.append(BoundaryReason.PRECEDING_TERMINAL_REST)
            if any(measure.id in repeated_entries for measure in current):
                reasons.append(BoundaryReason.REPETITION_ENTRY)
            if _texture_signature(previous) != _texture_signature(current):
                reasons.append(BoundaryReason.TEXTURE_CHANGE)
            if _rhythm_signature(previous) != _rhythm_signature(current):
                reasons.append(BoundaryReason.RHYTHM_CHANGE)
            if not reasons:
                reasons.append(BoundaryReason.MEASURE_FALLBACK)
        fallback = reasons == [BoundaryReason.MEASURE_FALLBACK]
        confidence = (
            AnalysisConfidence.LOW
            if fallback
            else AnalysisConfidence.HIGH
            if BoundaryReason.PRECEDING_TERMINAL_REST in reasons
            or BoundaryReason.SCOPE_START in reasons
            else AnalysisConfidence.MEDIUM
        )
        result.append(
            BoundaryCandidate(
                id=f"analysis-boundary:{token}:{ordinal}",
                score_onset=min(measure.score_onset for measure in current),
                measure_ids=tuple(measure.id for measure in current),
                reasons=tuple(reasons),
                evidence_ids=tuple(dict.fromkeys(evidence)),
                confidence=confidence,
                fallback=fallback,
            )
        )
        previous = current
    final_measures = sorted(by_ordinal[ordinals[-1]], key=lambda item: item.id)
    final_onset = max(measure.score_onset + measure.extent for measure in final_measures)
    result.append(
        BoundaryCandidate(
            id=f"analysis-boundary:{token}:end",
            score_onset=final_onset,
            measure_ids=tuple(measure.id for measure in final_measures),
            reasons=(BoundaryReason.SCOPE_END,),
            evidence_ids=tuple(measure.id for measure in final_measures),
            confidence=AnalysisConfidence.HIGH,
            fallback=False,
        )
    )
    return tuple(result)


def _has_terminal_rest(measure: TemporalMeasure) -> bool:
    return any(
        event.kind == "rest" and not event.grace and event.onset + event.duration == measure.extent
        for event in measure.events
    )


def _texture_signature(measures: Iterable[TemporalMeasure]) -> tuple[int, int]:
    events = tuple(
        event for measure in measures for event in measure.events if event.kind != "rest"
    )
    layers = {(event.staff, event.voice) for event in events}
    counts: dict[Fraction, int] = defaultdict(int)
    for event in events:
        counts[event.score_onset] += 1
    return len(layers), max(counts.values(), default=0)


def _rhythm_signature(measures: Iterable[TemporalMeasure]) -> tuple[Fraction, ...]:
    return tuple(
        sorted(
            event.duration for measure in measures for event in measure.events if not event.grace
        )
    )


def _build_facts(
    scoped_parts: tuple[tuple[TemporalPart, tuple[TemporalMeasure, ...]], ...],
    events: tuple[TemporalEvent, ...],
    rhythm: RhythmProfile,
    texture: TextureProfile,
    token: str,
) -> tuple[AnalysisFact, ...]:
    measures = tuple(measure for _, selected in scoped_parts for measure in selected)
    measure_positions = len({measure.ordinal for measure in measures})
    pitched = tuple(event for event in events if event.kind == "pitched")
    unpitched = tuple(event for event in events if event.kind == "unpitched")
    rests = tuple(event for event in events if event.kind == "rest")
    pitches = tuple(_written_semitone(event) for event in pitched)
    scope_evidence = tuple(measure.id for measure in measures)
    meters, clefs = _effective_notation_context(scoped_parts)
    meter_values = tuple(
        sorted(
            f"{'+'.join(beats)}/{'/'.join(map(str, beat_types))}" for beats, beat_types in meters
        )
    )
    clef_values = tuple(
        sorted(f"{sign}:{line}:{octave_change or 0}" for _, sign, line, octave_change in clefs)
    )
    definitions = (
        (
            AnalysisFactKind.PART_COUNT,
            str(len(scoped_parts)),
            tuple(part.id for part, _ in scoped_parts),
        ),
        (
            AnalysisFactKind.MEASURE_POSITION_COUNT,
            str(measure_positions),
            tuple(measure.id for measure in measures),
        ),
        (AnalysisFactKind.EVENT_COUNT, str(len(events)), tuple(event.id for event in events)),
        (
            AnalysisFactKind.PITCHED_EVENT_COUNT,
            str(len(pitched)),
            tuple(event.id for event in pitched) or scope_evidence,
        ),
        (
            AnalysisFactKind.UNPITCHED_EVENT_COUNT,
            str(len(unpitched)),
            tuple(event.id for event in unpitched) or scope_evidence,
        ),
        (
            AnalysisFactKind.REST_EVENT_COUNT,
            str(len(rests)),
            tuple(event.id for event in rests) or scope_evidence,
        ),
        (AnalysisFactKind.STAFF_COUNT, str(texture.staff_count), texture.evidence_ids),
        (AnalysisFactKind.VOICE_COUNT, str(texture.voice_count), texture.evidence_ids),
        (AnalysisFactKind.CHORD_COUNT, str(texture.chord_count), texture.evidence_ids),
        (
            AnalysisFactKind.PITCH_RANGE,
            "none" if not pitches else f"{min(pitches)}..{max(pitches)}",
            tuple(event.id for event in pitched) or scope_evidence,
        ),
        (
            AnalysisFactKind.WRITTEN_DURATION_VOCABULARY,
            ",".join(map(str, rhythm.written_durations)),
            rhythm.evidence_event_ids,
        ),
        (
            AnalysisFactKind.METER_VOCABULARY,
            ",".join(meter_values) if meter_values else "unknown",
            tuple(measure.id for measure in measures),
        ),
        (
            AnalysisFactKind.CLEF_VOCABULARY,
            ",".join(clef_values) if clef_values else "unknown",
            tuple(measure.id for measure in measures),
        ),
    )
    return tuple(
        AnalysisFact(
            id=f"analysis-fact:{token}:{kind.value}",
            kind=kind,
            value=value,
            evidence_ids=tuple(dict.fromkeys(evidence)),
            derivation=(
                AnalysisDerivation.SOURCE_SUMMARY
                if kind
                in {
                    AnalysisFactKind.WRITTEN_DURATION_VOCABULARY,
                    AnalysisFactKind.METER_VOCABULARY,
                    AnalysisFactKind.CLEF_VOCABULARY,
                }
                else AnalysisDerivation.DETERMINISTIC_DERIVATION
            ),
            algorithm="canonical-count-or-exact-set/v1",
        )
        for kind, value, evidence in definitions
    )


def _build_demands(
    scoped_parts: tuple[tuple[TemporalPart, tuple[TemporalMeasure, ...]], ...],
    layers: tuple[LayerProfile, ...],
    events: tuple[TemporalEvent, ...],
    rhythm: RhythmProfile,
    texture: TextureProfile,
    repetitions: tuple[RepetitionGroup, ...],
    token: str,
) -> tuple[DemandEstimate, ...]:
    measures = tuple(measure for _, selected in scoped_parts for measure in selected)
    measure_positions = len({measure.ordinal for measure in measures})
    pitches = tuple(
        _written_semitone(event)
        for event in events
        if event.kind == "pitched" and event.pitch is not None
    )
    pitch_span = max(pitches) - min(pitches) if pitches else Fraction(0)
    max_leap = _max_layer_leap(scoped_parts)
    max_density = max(
        (
            Fraction(
                len({event.onset for event in measure.events if not event.grace}),
                1,
            )
            / measure.extent
            for measure in measures
            if measure.extent > 0
        ),
        default=Fraction(0),
    )
    meters, clefs = _effective_notation_context(scoped_parts)
    max_run = _max_continuous_pitched_run(scoped_parts)
    all_ids = tuple(event.id for event in events)
    measure_ids = tuple(measure.id for measure in measures)
    definitions = (
        (
            AnalysisDemandDimension.SCORE_LITERACY,
            min(5, max(0, texture.staff_count - 1) + max(0, len(clefs) - 1)),
            f"staves={texture.staff_count};clefs={len(clefs)}",
            measure_ids,
            "More concurrent staves and clef forms increase decoding demands.",
        ),
        (
            AnalysisDemandDimension.RANGE,
            _bucket(pitch_span, (4, 12, 24, 36, 48)),
            f"written-semitone-span={pitch_span}",
            all_ids,
            "Written pitch span is bucketed without assigning fingering or hand use.",
        ),
        (
            AnalysisDemandDimension.TEXTURE,
            min(5, max(texture.layer_count - 1, texture.max_simultaneous_pitches - 1)),
            f"layers={texture.layer_count};max-simultaneous={texture.max_simultaneous_pitches}",
            texture.evidence_ids,
            "Independent layers and vertical density are retained separately.",
        ),
        (
            AnalysisDemandDimension.SIMULTANEITY,
            _bucket(Fraction(texture.max_simultaneous_pitches), (1, 2, 3, 4, 6)),
            f"max-simultaneous-pitches={texture.max_simultaneous_pitches}",
            texture.evidence_ids,
            "Maximum written pitch-set size is an observable coordination demand.",
        ),
        (
            AnalysisDemandDimension.LEAPS,
            _bucket(max_leap, (2, 5, 8, 12, 19)),
            f"max-layer-written-semitone-leap={max_leap}",
            all_ids,
            "Consecutive written pitches are compared only within the same layer.",
        ),
        (
            AnalysisDemandDimension.RHYTHMIC_DENSITY,
            _bucket(max_density, (1, 2, 3, 4, 6)),
            f"max-distinct-onsets-per-quarter={max_density}",
            rhythm.evidence_event_ids,
            "Density counts distinct non-grace onsets per quarter-note unit.",
        ),
        (
            AnalysisDemandDimension.METER,
            min(
                5,
                max(0, len(meters) - 1) + sum("+" in beat for beats, _ in meters for beat in beats),
            ),
            f"distinct-explicit-meters={len(meters)}",
            measure_ids,
            "Meter changes and additive beat groups increase the structural count.",
        ),
        (
            AnalysisDemandDimension.COORDINATION,
            _bucket(Fraction(texture.max_active_layers), (1, 1, 2, 3, 4)),
            f"max-active-layers={texture.max_active_layers}",
            texture.evidence_ids,
            "Concurrent active layers are counted without assigning hands.",
        ),
        (
            AnalysisDemandDimension.CONTINUITY,
            _bucket(Fraction(max_run), (4, 8, 16, 32, 64)),
            f"max-pitched-events-between-rests={max_run}",
            all_ids,
            "The longest layer-local pitched run is used as a continuity proxy.",
        ),
        (
            AnalysisDemandDimension.STRUCTURE,
            _bucket(Fraction(measure_positions), (2, 8, 16, 32, 64)),
            f"measure-positions={measure_positions};repetition-groups={len(repetitions)}",
            measure_ids,
            "Length and exact repetition inventory provide a bounded structural proxy.",
        ),
        (
            AnalysisDemandDimension.PASSAGE_LENGTH,
            _bucket(Fraction(measure_positions), (2, 8, 16, 32, 64)),
            f"measure-positions={measure_positions}",
            measure_ids,
            "Scope length is measured in aligned canonical measure positions.",
        ),
    )
    return tuple(
        DemandEstimate(
            id=f"analysis-demand:{token}:{dimension.value}",
            dimension=dimension,
            level=level,
            metric=metric,
            evidence_ids=tuple(dict.fromkeys(evidence)),
            rationale=rationale,
            uncertainty=(
                "Structural level only; learner-specific difficulty requires teaching "
                "policy and evidence."
            ),
        )
        for dimension, level, metric, evidence, rationale in definitions
    )


def _max_layer_leap(
    scoped_parts: tuple[tuple[TemporalPart, tuple[TemporalMeasure, ...]], ...],
) -> Fraction:
    by_layer: dict[tuple[str, str, str], list[tuple[Fraction, int, Fraction]]] = defaultdict(list)
    for part, measures in scoped_parts:
        for measure in measures:
            for event in measure.events:
                if event.kind == "pitched" and event.pitch is not None and not event.grace:
                    by_layer[(part.id, event.staff, event.voice)].append(
                        (
                            measure.score_onset + event.onset,
                            event.source_order,
                            _written_semitone(event),
                        )
                    )
    maximum = Fraction(0)
    for values in by_layer.values():
        ordered = [item[2] for item in sorted(values)]
        maximum = max(
            (
                abs(current - previous)
                for previous, current in zip(ordered, ordered[1:], strict=False)
            ),
            default=maximum,
        )
    return maximum


def _effective_notation_context(
    scoped_parts: tuple[tuple[TemporalPart, tuple[TemporalMeasure, ...]], ...],
) -> tuple[
    set[tuple[tuple[str, ...], tuple[int, ...]]],
    set[tuple[str, str, int | None, int | None]],
]:
    meters: set[tuple[tuple[str, ...], tuple[int, ...]]] = set()
    clefs: set[tuple[str, str, int | None, int | None]] = set()
    for part, selected in scoped_parts:
        selected_ordinals = {measure.ordinal for measure in selected}
        if not selected_ordinals:
            continue
        last_ordinal = max(selected_ordinals)
        current_meters: dict[str | None, tuple[tuple[str, ...], tuple[int, ...]]] = {}
        current_clefs: dict[str, tuple[str, str, int | None, int | None]] = {}
        for measure in part.measures:
            if measure.ordinal > last_ordinal:
                break
            for attributes in sorted(
                measure.attributes,
                key=lambda item: (item.onset, item.source_order),
            ):
                for time in attributes.times:
                    current_meters[time.staff] = (time.beats, time.beat_types)
                for clef in attributes.clefs:
                    current_clefs[clef.staff] = (
                        clef.staff,
                        clef.sign,
                        clef.line,
                        clef.octave_change,
                    )
            if measure.ordinal in selected_ordinals:
                meters.update(current_meters.values())
                clefs.update(current_clefs.values())
    return meters, clefs


def _max_continuous_pitched_run(
    scoped_parts: tuple[tuple[TemporalPart, tuple[TemporalMeasure, ...]], ...],
) -> int:
    by_layer: dict[tuple[str, str, str], list[tuple[Fraction, int, TemporalEvent]]] = defaultdict(
        list
    )
    for part, measures in scoped_parts:
        for measure in measures:
            for event in measure.events:
                by_layer[(part.id, event.staff, event.voice)].append(
                    (measure.score_onset + event.onset, event.source_order, event)
                )
    maximum = 0
    for values in by_layer.values():
        current = 0
        for _, _, event in sorted(values):
            if event.kind == "rest":
                current = 0
            elif event.kind == "pitched" and event.pitch is not None:
                current += 1
                maximum = max(maximum, current)
    return maximum


def _written_semitone(event: TemporalEvent) -> Fraction:
    if event.pitch is None:
        raise AnalysisError("ANALYSIS_PITCH", "rest has no written pitch")
    semitones = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}
    try:
        base = semitones[event.pitch.step]
    except KeyError as error:
        raise AnalysisError("ANALYSIS_PITCH", f"unknown pitch step {event.pitch.step!r}") from error
    return Fraction(12 * (event.pitch.octave + 1) + base) + event.pitch.alter


def _bucket(value: Fraction, thresholds: tuple[int, int, int, int, int]) -> int:
    for level, threshold in enumerate(thresholds):
        if value <= threshold:
            return level
    return 5
