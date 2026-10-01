"""Canonical-only projection into the deterministic DEV-005 playback plan."""

from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction

from teachmemusic.score import (
    CanonicalMusicPackage,
    CanonicalScoreContent,
    ScoreDocument,
    require_valid_package,
)
from teachmemusic.score.v2.annotations import NotationSpan
from teachmemusic.score.v2.temporal import (
    TemporalBarline,
    TemporalClef,
    TemporalEvent,
    TemporalMeasure,
    TemporalPart,
    TemporalScore,
)

from .contracts import DiagnosticSeverity, ViewerDiagnostic
from .playback_contracts import (
    GraceRealization,
    PlaybackClef,
    PlaybackMeasureVisit,
    PlaybackNote,
    PlaybackPlan,
    PlaybackSourceEvent,
    TempoControl,
    require_valid_playback_plan,
)

_MICROSECONDS_PER_MINUTE = 60_000_000
_MAX_MEASURE_VISITS = 100_000


class PlaybackProjectionError(ValueError):
    """Raised when canonical facts cannot be projected without guessing."""

    def __init__(self, code: str, message: str, *, canonical_id: str | None = None) -> None:
        self.code = code
        self.canonical_id = canonical_id
        super().__init__(f"{code}: {message}")


@dataclass(frozen=True, slots=True)
class _TempoSource:
    part_id: str
    measure_id: str
    local_onset: Fraction
    score_onset: Fraction
    source_order: int
    qpm: Fraction


@dataclass(frozen=True, slots=True)
class _Candidate:
    id: str
    start: Fraction
    end: Fraction
    midi_pitch: int
    source: PlaybackSourceEvent
    chord_id: str | None
    dynamic_percent: Fraction | None
    tie_group: str | None


@dataclass(frozen=True, slots=True)
class _MeasureStep:
    index: int
    entry_reason: str


@dataclass(frozen=True, slots=True)
class _EventWindow:
    start: Fraction
    end: Fraction


@dataclass(frozen=True, slots=True)
class _GraceSchedule:
    windows: dict[str, _EventWindow]
    realizations: tuple[GraceRealization, ...]
    fallback_used: bool


@dataclass(frozen=True, slots=True)
class _NavigationAction:
    dacapo: bool
    dalsegno: str | None
    tocoda: str | None
    fine: bool


def build_playback_plan(
    package: CanonicalMusicPackage,
    *,
    score_id: str | None = None,
    fallback_tempo_qpm: Fraction | int | None = None,
    grace_fallback_percent: Fraction | int | None = None,
    navigation_section_starts: tuple[int, ...] | None = None,
) -> PlaybackPlan:
    """Build an exact repeat-expanded plan from one complete canonical score.

    A score without an initial canonical tempo requires an explicit caller
    fallback. The selected fallback is retained as a control and diagnostic;
    it is never silently inferred from notation or exporter conventions.
    """

    require_valid_package(package)
    document = _select_score_document(package, score_id=score_id)
    if not isinstance(document.content, CanonicalScoreContent):
        raise PlaybackProjectionError(
            "VIEWER_PLAYBACK_INCOMPLETE_SCORE",
            "playback requires complete canonical score content",
            canonical_id=document.id.value,
        )
    score = document.content.score
    fallback = _normalize_fallback_tempo(fallback_tempo_qpm)
    grace_fallback = _normalize_grace_fallback(grace_fallback_percent)
    section_starts = _normalize_navigation_sections(score, navigation_section_starts)
    measure_steps = _expanded_measure_steps(score, section_starts=section_starts)
    clefs, missing_clef_keys = _active_clefs(score)
    tie_groups = _sounding_tie_groups(score.annotations.spans)

    diagnostics: list[ViewerDiagnostic] = []
    if any(step.entry_reason == "repeat" for step in measure_steps):
        diagnostics.append(
            ViewerDiagnostic(
                code="VIEWER_PLAYBACK_REPEATS_EXPANDED",
                severity=DiagnosticSeverity.INFO,
                message="canonical repeat barlines were expanded into playback order",
                canonical_ids=(document.id.value,),
            )
        )
    if any(
        barline.ending_number is not None or barline.ending_type is not None
        for measure in score.parts[0].measures
        for barline in measure.barlines
    ):
        diagnostics.append(
            ViewerDiagnostic(
                code="VIEWER_PLAYBACK_ENDINGS_EXPANDED",
                severity=DiagnosticSeverity.INFO,
                message="canonical volta endings were selected by repeat pass",
                canonical_ids=(document.id.value,),
            )
        )
    if any(step.entry_reason in {"jump", "coda"} for step in measure_steps):
        diagnostics.append(
            ViewerDiagnostic(
                code="VIEWER_PLAYBACK_NAVIGATION_EXPANDED",
                severity=DiagnosticSeverity.INFO,
                message="canonical jump navigation was expanded into playback order",
                canonical_ids=(document.id.value,),
            )
        )
    if len(section_starts) > 1:
        diagnostics.append(
            ViewerDiagnostic(
                code="VIEWER_PLAYBACK_NAVIGATION_SECTIONS",
                severity=DiagnosticSeverity.INFO,
                message=(
                    "caller-supplied section boundaries scope Da Capo/Dal Segno and "
                    "resume later embedded movements after Fine"
                ),
                canonical_ids=(document.id.value,),
            )
        )
    if missing_clef_keys:
        diagnostics.append(
            ViewerDiagnostic(
                code="VIEWER_PLAYBACK_CLEF_UNSPECIFIED",
                severity=DiagnosticSeverity.WARNING,
                message=(
                    "one or more events have no active canonical clef; their piano "
                    "contributions remain playable but have no clef color group"
                ),
                canonical_ids=tuple(sorted(missing_clef_keys)),
            )
        )

    current_tempo: Fraction | None = None
    current_dynamics: dict[str, Fraction | None] = {part.id: None for part in score.parts}
    exact_clock = Fraction(0)
    candidates: list[_Candidate] = []
    tempo_controls: list[TempoControl] = []
    visits: list[PlaybackMeasureVisit] = []
    fallback_used = False
    grace_fallback_used = False
    grace_realizations: dict[str, GraceRealization] = {}

    for visit_index, step in enumerate(measure_steps):
        measure_index = step.index
        controlling = score.parts[0].measures[measure_index]
        visit_start = exact_clock
        tempo_sources = _measure_tempos(score.parts, measure_index)
        tempos_by_onset = _unique_tempos_by_onset(tempo_sources)
        boundaries = {Fraction(0), controlling.extent}
        boundaries.update(tempos_by_onset)
        schedules: dict[str, _GraceSchedule] = {}
        for part in score.parts:
            measure = part.measures[measure_index]
            schedule = _grace_schedule(measure, grace_fallback)
            schedules[part.id] = schedule
            grace_fallback_used = grace_fallback_used or schedule.fallback_used
            for realization in schedule.realizations:
                previous_realization = grace_realizations.setdefault(
                    realization.event_id, realization
                )
                if previous_realization != realization:
                    raise PlaybackProjectionError(
                        "VIEWER_PLAYBACK_GRACE_REPEAT_CONFLICT",
                        "a repeated grace event acquired inconsistent timing",
                        canonical_id=realization.event_id,
                    )
            for event in measure.events:
                window = schedule.windows[event.id]
                if window.start < 0 or window.end > controlling.extent:
                    raise PlaybackProjectionError(
                        "VIEWER_PLAYBACK_EVENT_RANGE",
                        "an event extends outside its controlling measure",
                        canonical_id=event.id,
                    )
                boundaries.add(window.start)
                boundaries.add(window.end)

        if current_tempo is None and Fraction(0) not in tempos_by_onset:
            if fallback is None:
                raise PlaybackProjectionError(
                    "VIEWER_PLAYBACK_TEMPO_REQUIRED",
                    "the score has no initial canonical tempo; provide fallback_tempo_qpm",
                    canonical_id=document.id.value,
                )
            current_tempo = fallback
            fallback_used = True
            tempo_controls.append(
                TempoControl(
                    id="playback-tempo:fallback:0",
                    at_microseconds=0,
                    quarter_notes_per_minute=fallback,
                    source_score_onset=Fraction(0),
                    origin="caller-fallback",
                )
            )

        times: dict[Fraction, Fraction] = {}
        previous = Fraction(0)
        for boundary in sorted(boundaries):
            if boundary < previous or boundary > controlling.extent:
                raise PlaybackProjectionError(
                    "VIEWER_PLAYBACK_BOUNDARY",
                    "a playback boundary is outside its controlling measure",
                    canonical_id=controlling.id,
                )
            if boundary > previous:
                if current_tempo is None:
                    raise PlaybackProjectionError(
                        "VIEWER_PLAYBACK_TEMPO_REQUIRED",
                        "playback time occurs before any canonical or caller tempo",
                        canonical_id=controlling.id,
                    )
                exact_clock += (boundary - previous) * _MICROSECONDS_PER_MINUTE / current_tempo
            times[boundary] = exact_clock
            sources = tempos_by_onset.get(boundary, ())
            if sources:
                source = sources[0]
                current_tempo = source.qpm
                tempo_controls.append(
                    TempoControl(
                        id=f"playback-tempo:{visit_index}:{source.part_id}:{source.source_order}",
                        at_microseconds=_round_microseconds(exact_clock),
                        quarter_notes_per_minute=source.qpm,
                        source_score_onset=source.score_onset,
                        origin="canonical",
                        source_part_id=source.part_id,
                        source_measure_id=source.measure_id,
                        source_order=source.source_order,
                    )
                )
            previous = boundary

        for part in score.parts:
            measure = part.measures[measure_index]
            schedule = schedules[part.id]
            dynamics = _event_dynamics(measure, current_dynamics[part.id])
            current_dynamics[part.id] = _ending_dynamics(measure, current_dynamics[part.id])
            for event in measure.events:
                if event.kind == "rest":
                    continue
                if event.kind != "pitched":
                    raise PlaybackProjectionError(
                        "VIEWER_PLAYBACK_UNSUPPORTED_EVENT",
                        f"event kind {event.kind!r} is not supported by the piano plan",
                        canonical_id=event.id,
                    )
                if not event.sounding_pitches:
                    raise PlaybackProjectionError(
                        "VIEWER_PLAYBACK_SOUNDING_PITCH",
                        "pitched event has no canonical sounding pitch",
                        canonical_id=event.id,
                    )
                event_source = _playback_source(
                    part, measure, event, clefs.get((part.id, event.id))
                )
                window = schedule.windows[event.id]
                for pitch_index, sounding in enumerate(event.sounding_pitches):
                    if sounding.semitone.denominator != 1:
                        raise PlaybackProjectionError(
                            "VIEWER_PLAYBACK_MICROTONAL_PITCH",
                            "the piano plan currently requires integral MIDI pitches",
                            canonical_id=event.id,
                        )
                    midi_pitch = int(sounding.semitone)
                    if not 0 <= midi_pitch <= 127:
                        raise PlaybackProjectionError(
                            "VIEWER_PLAYBACK_MIDI_RANGE",
                            "canonical sounding pitch lies outside MIDI range",
                            canonical_id=event.id,
                        )
                    candidates.append(
                        _Candidate(
                            id=f"playback-note:{visit_index}:{event.id}:{pitch_index}",
                            start=times[window.start],
                            end=times[window.end],
                            midi_pitch=midi_pitch,
                            source=event_source,
                            chord_id=event.chord_id,
                            dynamic_percent=(
                                event.dynamics if event.dynamics is not None else dynamics[event.id]
                            ),
                            tie_group=tie_groups.get(event.id),
                        )
                    )

        visit_end = times[controlling.extent]
        visits.append(
            PlaybackMeasureVisit(
                visit_index=visit_index,
                source_measure_index=measure_index,
                source_measure_number=controlling.number,
                source_measure_ids=tuple(part.measures[measure_index].id for part in score.parts),
                source_score_onset=controlling.score_onset,
                start_microseconds=_round_microseconds(visit_start),
                end_microseconds=_round_microseconds(visit_end),
                entry_reason=step.entry_reason,
            )
        )

    if fallback_used:
        diagnostics.append(
            ViewerDiagnostic(
                code="VIEWER_PLAYBACK_TEMPO_FALLBACK",
                severity=DiagnosticSeverity.WARNING,
                message=(
                    "the canonical score has no initial tempo; the explicitly supplied "
                    f"{fallback} QPM fallback establishes playback time"
                ),
                canonical_ids=(document.id.value,),
            )
        )
    if grace_realizations:
        diagnostics.append(
            ViewerDiagnostic(
                code="VIEWER_PLAYBACK_GRACE_REALIZED",
                severity=DiagnosticSeverity.INFO,
                message=(
                    "canonical grace events were assigned deterministic audible timing "
                    "without changing the measure timeline"
                ),
                canonical_ids=tuple(sorted(grace_realizations)),
            )
        )
    if grace_fallback_used:
        assert grace_fallback is not None
        diagnostics.append(
            ViewerDiagnostic(
                code="VIEWER_PLAYBACK_GRACE_FALLBACK",
                severity=DiagnosticSeverity.WARNING,
                message=(
                    "one or more grace clusters had no source timing hint; the "
                    f"explicitly supplied {grace_fallback}% allocation was used"
                ),
                canonical_ids=tuple(
                    sorted(
                        item.event_id
                        for item in grace_realizations.values()
                        if item.origin == "caller-fallback"
                    )
                ),
            )
        )

    notes = _resolve_ties(candidates)
    plan = PlaybackPlan(
        package_id=package.id.value,
        score_id=document.id.value,
        canonical_schema_id=package.schema_id,
        canonical_schema_version=package.schema_version,
        duration_microseconds=_round_microseconds(exact_clock),
        notes=tuple(
            sorted(notes, key=lambda item: (item.start_microseconds, item.midi_pitch, item.id))
        ),
        tempo_controls=tuple(
            sorted(tempo_controls, key=lambda item: (item.at_microseconds, item.id))
        ),
        measure_visits=tuple(visits),
        grace_realizations=tuple(
            grace_realizations[event_id] for event_id in sorted(grace_realizations)
        ),
        navigation_section_starts=section_starts,
        diagnostics=tuple(diagnostics),
    )
    require_valid_playback_plan(plan)
    return plan


def _select_score_document(
    package: CanonicalMusicPackage, *, score_id: str | None
) -> ScoreDocument:
    documents = [item for item in package.documents if isinstance(item, ScoreDocument)]
    if score_id is not None:
        matches = [item for item in documents if item.id.value == score_id]
        if len(matches) != 1:
            raise PlaybackProjectionError(
                "VIEWER_PLAYBACK_SCORE_NOT_FOUND",
                "requested canonical score does not occur exactly once in the package",
                canonical_id=score_id,
            )
        return matches[0]
    root_ids = {item.target_id for item in package.root_documents}
    root_scores = [item for item in documents if item.id.value in root_ids]
    if len(root_scores) == 1:
        return root_scores[0]
    if len(documents) == 1:
        return documents[0]
    raise PlaybackProjectionError(
        "VIEWER_PLAYBACK_SCORE_SELECTION_REQUIRED",
        "package contains multiple score documents; score_id is required",
    )


def _normalize_fallback_tempo(value: Fraction | int | None) -> Fraction | None:
    if value is None:
        return None
    if isinstance(value, bool):
        raise PlaybackProjectionError(
            "VIEWER_PLAYBACK_TEMPO_VALUE", "fallback tempo must be a positive number"
        )
    tempo = Fraction(value)
    if tempo <= 0:
        raise PlaybackProjectionError(
            "VIEWER_PLAYBACK_TEMPO_VALUE", "fallback tempo must be positive"
        )
    return tempo


def _normalize_grace_fallback(value: Fraction | int | None) -> Fraction | None:
    if value is None:
        return None
    if isinstance(value, bool):
        raise PlaybackProjectionError(
            "VIEWER_PLAYBACK_GRACE_VALUE",
            "grace fallback must be a percentage strictly between 0 and 100",
        )
    percent = Fraction(value)
    if not 0 < percent < 100:
        raise PlaybackProjectionError(
            "VIEWER_PLAYBACK_GRACE_VALUE",
            "grace fallback must be a percentage strictly between 0 and 100",
        )
    return percent


def _normalize_navigation_sections(
    score: TemporalScore,
    value: tuple[int, ...] | None,
) -> tuple[int, ...]:
    section_starts = (0,) if value is None else value
    measure_count = len(score.parts[0].measures) if score.parts else 0
    if (
        not section_starts
        or section_starts[0] != 0
        or tuple(sorted(set(section_starts))) != section_starts
        or any(index < 0 or index >= measure_count for index in section_starts)
    ):
        raise PlaybackProjectionError(
            "VIEWER_PLAYBACK_NAVIGATION_SECTIONS",
            "navigation section starts must be sorted, unique, in range, and begin at zero",
        )
    return section_starts


def _grace_schedule(
    measure: TemporalMeasure,
    fallback_percent: Fraction | None,
) -> _GraceSchedule:
    windows = {
        event.id: _EventWindow(
            event.onset,
            event.onset + (Fraction(0) if event.grace else _event_playback_duration(event)),
        )
        for event in measure.events
    }
    groups: dict[tuple[str, str, Fraction], list[TemporalEvent]] = {}
    for event in measure.events:
        if event.grace:
            groups.setdefault((event.staff, event.voice, event.onset), []).append(event)
    realizations: list[GraceRealization] = []
    fallback_used = False
    for _, unsorted_cluster in sorted(
        groups.items(), key=lambda item: (item[0][2], item[0][0], item[0][1])
    ):
        cluster = tuple(sorted(unsorted_cluster, key=lambda item: item.source_order))
        if any(event.chord_id is not None for event in cluster):
            raise PlaybackProjectionError(
                "VIEWER_PLAYBACK_GRACE_CHORD",
                "grace-note chords require a later simultaneous-cluster policy",
                canonical_id=cluster[0].id,
            )
        following = _grace_anchor_events(measure, cluster, relation="following")
        previous = _grace_anchor_events(measure, cluster, relation="previous")
        relation, anchors = _select_grace_relation(cluster, following, previous)
        anchor_window = windows[anchors[0].id]
        anchor_duration = anchor_window.end - anchor_window.start
        if any(windows[event.id] != anchor_window for event in anchors):
            raise PlaybackProjectionError(
                "VIEWER_PLAYBACK_GRACE_ANCHOR_CONFLICT",
                "grace anchor chord members do not share one time range",
                canonical_id=cluster[0].id,
            )
        durations, origin = _grace_durations(
            cluster,
            relation=relation,
            anchor_duration=anchor_duration,
            fallback_percent=fallback_percent,
        )
        fallback_used = fallback_used or origin == "caller-fallback"
        budget = sum(durations, Fraction(0))
        if not 0 < budget < anchor_duration:
            raise PlaybackProjectionError(
                "VIEWER_PLAYBACK_GRACE_BUDGET",
                "grace duration must consume less than its principal anchor",
                canonical_id=cluster[0].id,
            )
        if relation == "following":
            cursor = anchor_window.start
            for anchor in anchors:
                windows[anchor.id] = _EventWindow(anchor_window.start + budget, anchor_window.end)
        else:
            cursor = anchor_window.end - budget
            for anchor in anchors:
                windows[anchor.id] = _EventWindow(anchor_window.start, anchor_window.end - budget)
        anchor_ids = tuple(event.id for event in anchors)
        for cluster_index, (event, duration) in enumerate(zip(cluster, durations, strict=True)):
            windows[event.id] = _EventWindow(cursor, cursor + duration)
            cursor += duration
            realizations.append(
                GraceRealization(
                    event_id=event.id,
                    anchor_event_ids=anchor_ids,
                    relation=relation,
                    origin=origin,
                    duration_quarter_notes=duration,
                    cluster_index=cluster_index,
                    cluster_size=len(cluster),
                )
            )
    return _GraceSchedule(windows, tuple(realizations), fallback_used)


def _grace_anchor_events(
    measure: TemporalMeasure,
    cluster: tuple[TemporalEvent, ...],
    *,
    relation: str,
) -> tuple[TemporalEvent, ...]:
    first = cluster[0]
    minimum_order = min(item.source_order for item in cluster)
    maximum_order = max(item.source_order for item in cluster)
    if relation == "following":
        candidates = [
            event
            for event in measure.events
            if not event.grace
            and event.onset == first.onset
            and event.source_order > maximum_order
            and event.staff == first.staff
        ]
    else:
        candidates = [
            event
            for event in measure.events
            if not event.grace
            and event.onset + event.duration == first.onset
            and event.source_order < minimum_order
            and event.staff == first.staff
        ]
    same_voice = [event for event in candidates if event.voice == first.voice]
    candidates = same_voice or candidates
    if not candidates:
        return ()
    selected = (
        min(candidates, key=lambda item: item.source_order)
        if relation == "following"
        else max(candidates, key=lambda item: item.source_order)
    )
    if selected.chord_id is None:
        return (selected,)
    return tuple(
        sorted(
            (
                event
                for event in measure.events
                if not event.grace and event.chord_id == selected.chord_id
            ),
            key=lambda item: item.source_order,
        )
    )


def _select_grace_relation(
    cluster: tuple[TemporalEvent, ...],
    following: tuple[TemporalEvent, ...],
    previous: tuple[TemporalEvent, ...],
) -> tuple[str, tuple[TemporalEvent, ...]]:
    has_following_hint = any(
        event.grace_timing is not None and event.grace_timing.steal_following_percent is not None
        for event in cluster
    )
    has_previous_hint = any(
        event.grace_timing is not None and event.grace_timing.steal_previous_percent is not None
        for event in cluster
    )
    if has_following_hint and has_previous_hint:
        raise PlaybackProjectionError(
            "VIEWER_PLAYBACK_GRACE_HINT_CONFLICT",
            "one grace cluster requests both following and previous anchors",
            canonical_id=cluster[0].id,
        )
    if has_following_hint:
        if not following:
            raise PlaybackProjectionError(
                "VIEWER_PLAYBACK_GRACE_ANCHOR",
                "steal-time-following has no following principal anchor",
                canonical_id=cluster[0].id,
            )
        return "following", following
    if has_previous_hint:
        if not previous:
            raise PlaybackProjectionError(
                "VIEWER_PLAYBACK_GRACE_ANCHOR",
                "steal-time-previous has no previous principal anchor",
                canonical_id=cluster[0].id,
            )
        return "previous", previous
    if following:
        return "following", following
    if previous:
        return "previous", previous
    raise PlaybackProjectionError(
        "VIEWER_PLAYBACK_GRACE_ANCHOR",
        "grace cluster has no unambiguous adjacent principal anchor",
        canonical_id=cluster[0].id,
    )


def _grace_durations(
    cluster: tuple[TemporalEvent, ...],
    *,
    relation: str,
    anchor_duration: Fraction,
    fallback_percent: Fraction | None,
) -> tuple[tuple[Fraction, ...], str]:
    make_times = tuple(
        event.grace_timing.make_time
        for event in cluster
        if event.grace_timing is not None and event.grace_timing.make_time is not None
    )
    following_values = tuple(
        event.grace_timing.steal_following_percent
        for event in cluster
        if event.grace_timing is not None and event.grace_timing.steal_following_percent is not None
    )
    previous_values = tuple(
        event.grace_timing.steal_previous_percent
        for event in cluster
        if event.grace_timing is not None and event.grace_timing.steal_previous_percent is not None
    )
    hint_kinds = sum(bool(values) for values in (make_times, following_values, previous_values))
    if hint_kinds > 1:
        raise PlaybackProjectionError(
            "VIEWER_PLAYBACK_GRACE_HINT_CONFLICT",
            "one grace cluster mixes incompatible source timing hints",
            canonical_id=cluster[0].id,
        )
    if make_times:
        if len(make_times) != len(cluster) or any(value <= 0 for value in make_times):
            raise PlaybackProjectionError(
                "VIEWER_PLAYBACK_GRACE_HINT",
                "make-time must be positive and explicit on every grace in a cluster",
                canonical_id=cluster[0].id,
            )
        return tuple(make_times), "source-make-time"
    percentages = following_values or previous_values
    if percentages:
        if len(set(percentages)) != 1 or not 0 < percentages[0] < 100:
            raise PlaybackProjectionError(
                "VIEWER_PLAYBACK_GRACE_HINT",
                "source steal-time percentage must be one value between 0 and 100",
                canonical_id=cluster[0].id,
            )
        if following_values and relation != "following":
            raise AssertionError("following hint selected a non-following anchor")
        if previous_values and relation != "previous":
            raise AssertionError("previous hint selected a non-previous anchor")
        budget = anchor_duration * percentages[0] / 100
        origin = "source-steal-following" if following_values else "source-steal-previous"
    else:
        if fallback_percent is None:
            raise PlaybackProjectionError(
                "VIEWER_PLAYBACK_GRACE_POLICY_REQUIRED",
                "grace timing is unspecified; provide grace_fallback_percent",
                canonical_id=cluster[0].id,
            )
        budget = anchor_duration * fallback_percent / 100
        origin = "caller-fallback"
    duration = budget / len(cluster)
    return (duration,) * len(cluster), origin


def _expanded_measure_steps(
    score: TemporalScore,
    *,
    section_starts: tuple[int, ...],
) -> tuple[_MeasureStep, ...]:
    if not score.parts or not score.parts[0].measures:
        raise PlaybackProjectionError(
            "VIEWER_PLAYBACK_EMPTY_SCORE", "score contains no playable measures"
        )
    controlling = score.parts[0].measures
    baseline = tuple((measure.score_onset, measure.extent) for measure in controlling)
    for part in score.parts:
        if tuple((measure.score_onset, measure.extent) for measure in part.measures) != baseline:
            raise PlaybackProjectionError(
                "VIEWER_PLAYBACK_UNALIGNED_PARTS",
                "parts do not share one controlling measure timeline",
                canonical_id=part.id,
            )
        if any(measure.non_controlling for measure in part.measures):
            raise PlaybackProjectionError(
                "VIEWER_PLAYBACK_NON_CONTROLLING",
                "non-controlling measures require a later navigation policy",
                canonical_id=part.id,
            )

    signatures = [_playback_control_signature(measure) for measure in controlling]
    for part in score.parts[1:]:
        if [_playback_control_signature(measure) for measure in part.measures] != signatures:
            raise PlaybackProjectionError(
                "VIEWER_PLAYBACK_CONTROL_CONFLICT",
                "parts disagree about repeat, ending, or navigation structure",
                canonical_id=part.id,
            )
    ending_passes, ending_closes = _ending_state(controlling)
    segnos, codas = _navigation_targets(controlling)
    visits: list[_MeasureStep] = []
    repeat_start = 0
    repeat_open = False
    repeat_pass = 1
    primary_jump_taken = False
    coda_jump_taken = False
    after_jump = False
    jump_return_index: int | None = None
    entry_reason = "initial"
    index = 0
    while index < len(controlling):
        if len(visits) >= _MAX_MEASURE_VISITS:
            raise PlaybackProjectionError(
                "VIEWER_PLAYBACK_REPEAT_LIMIT", "repeat expansion exceeded its safety limit"
            )
        measure = controlling[index]
        forwards = _forward_repeat_markers(measure)
        if forwards and (not after_jump or _repeat_after_jump(measure)):
            if repeat_open and repeat_start != index:
                raise PlaybackProjectionError(
                    "VIEWER_PLAYBACK_NESTED_REPEAT",
                    "nested repeats are ambiguous in the bounded playback traversal",
                    canonical_id=measure.id,
                )
            if not repeat_open:
                repeat_start = index
                repeat_open = True
                repeat_pass = 1

        allowed_passes = ending_passes[index]
        if allowed_passes and repeat_pass not in allowed_passes:
            index += 1
            entry_reason = "sequential"
            continue

        visits.append(_MeasureStep(index, entry_reason))

        action = _navigation_action(measure)
        if after_jump and action.fine:
            if jump_return_index is None:
                break
            index = jump_return_index
            primary_jump_taken = False
            coda_jump_taken = False
            after_jump = False
            jump_return_index = None
            repeat_open = False
            repeat_pass = 1
            entry_reason = "jump"
            continue
        if after_jump and not coda_jump_taken and action.tocoda is not None:
            target = _target_index(
                codas,
                action.tocoda,
                feature="coda",
                measure_id=measure.id,
            )
            coda_jump_taken = True
            repeat_open = False
            repeat_pass = 1
            index = target
            entry_reason = "coda"
            continue
        if not primary_jump_taken and (action.dacapo or action.dalsegno is not None):
            target = max(start for start in section_starts if start <= index)
            if action.dalsegno is not None:
                target = _target_index(
                    segnos,
                    action.dalsegno,
                    feature="segno",
                    measure_id=measure.id,
                )
            jump_return_index = next((start for start in section_starts if start > index), None)
            primary_jump_taken = True
            after_jump = True
            repeat_open = False
            repeat_pass = 1
            index = target
            entry_reason = "jump"
            continue

        backwards = _backward_repeat_markers(measure)
        if backwards and (not after_jump or _repeat_after_jump(measure)):
            total = _repeat_total(backwards[0].repeat_times, measure.id)
            if repeat_pass < total:
                repeat_pass += 1
                index = repeat_start
                entry_reason = "repeat"
                continue
            repeat_start = index + 1
            repeat_open = False
        if ending_closes[index] and not backwards:
            repeat_open = False
            repeat_pass = 1
        index += 1
        entry_reason = "sequential"
    return tuple(visits)


def _playback_control_signature(measure: TemporalMeasure) -> tuple[object, ...]:
    barlines = tuple(
        (
            barline.onset,
            barline.repeat_direction,
            barline.repeat_times,
            barline.ending_number,
            barline.ending_type,
            barline.repeat_after_jump,
            tuple((item.kind, item.token) for item in barline.navigation),
        )
        for barline in measure.barlines
        if barline.repeat_direction is not None
        or barline.ending_number is not None
        or barline.ending_type is not None
        or barline.navigation
    )
    sounds = tuple(
        (
            sound.onset,
            sound.dacapo,
            sound.segno,
            sound.dalsegno,
            sound.coda,
            sound.tocoda,
            sound.forward_repeat,
            sound.fine,
            sound.time_only,
        )
        for sound in measure.sounds
        if any(
            item is not None
            for item in (
                sound.dacapo,
                sound.segno,
                sound.dalsegno,
                sound.coda,
                sound.tocoda,
                sound.forward_repeat,
                sound.fine,
                sound.time_only,
            )
        )
    )
    return barlines, sounds


def _forward_repeat_markers(measure: TemporalMeasure) -> bool:
    barlines = [item for item in measure.barlines if item.repeat_direction == "forward"]
    sounds = [item for item in measure.sounds if item.forward_repeat is True]
    if len(barlines) > 1 or len(sounds) > 1:
        raise PlaybackProjectionError(
            "VIEWER_PLAYBACK_REPEAT_AMBIGUOUS",
            "measure contains multiple forward-repeat instructions",
            canonical_id=measure.id,
        )
    if barlines and barlines[0].onset != 0:
        raise PlaybackProjectionError(
            "VIEWER_PLAYBACK_PARTIAL_REPEAT",
            "forward repeat is not at the measure boundary",
            canonical_id=measure.id,
        )
    if sounds and sounds[0].onset != 0:
        raise PlaybackProjectionError(
            "VIEWER_PLAYBACK_PARTIAL_REPEAT",
            "sound forward-repeat is not at the measure boundary",
            canonical_id=measure.id,
        )
    return bool(barlines or sounds)


def _backward_repeat_markers(measure: TemporalMeasure) -> tuple[TemporalBarline, ...]:
    barlines = tuple(item for item in measure.barlines if item.repeat_direction == "backward")
    if len(barlines) > 1:
        raise PlaybackProjectionError(
            "VIEWER_PLAYBACK_REPEAT_AMBIGUOUS",
            "measure contains multiple backward-repeat instructions",
            canonical_id=measure.id,
        )
    if barlines and barlines[0].onset != measure.extent:
        raise PlaybackProjectionError(
            "VIEWER_PLAYBACK_PARTIAL_REPEAT",
            "backward repeat is not at the measure boundary",
            canonical_id=measure.id,
        )
    return barlines


def _repeat_after_jump(measure: TemporalMeasure) -> bool:
    return any(
        barline.repeat_direction is not None and barline.repeat_after_jump is True
        for barline in measure.barlines
    )


def _ending_state(
    measures: tuple[TemporalMeasure, ...],
) -> tuple[tuple[frozenset[int], ...], tuple[bool, ...]]:
    active: frozenset[int] = frozenset()
    passes: list[frozenset[int]] = []
    closes: list[bool] = []
    for measure in measures:
        start_markers = [barline for barline in measure.barlines if barline.ending_type == "start"]
        close_markers = [
            barline
            for barline in measure.barlines
            if barline.ending_type in {"stop", "discontinue"}
        ]
        if len(start_markers) > 1 or len(close_markers) > 1:
            raise PlaybackProjectionError(
                "VIEWER_PLAYBACK_ENDING_AMBIGUOUS",
                "measure contains multiple ending boundaries",
                canonical_id=measure.id,
            )
        if start_markers:
            marker = start_markers[0]
            if marker.onset != 0 or active:
                raise PlaybackProjectionError(
                    "VIEWER_PLAYBACK_ENDING_STRUCTURE",
                    "ending start is nested or not at a measure boundary",
                    canonical_id=measure.id,
                )
            active = _ending_numbers(marker.ending_number, measure.id)
        passes.append(active)
        closes.append(bool(close_markers))
        if close_markers:
            marker = close_markers[0]
            if marker.onset != measure.extent:
                raise PlaybackProjectionError(
                    "VIEWER_PLAYBACK_ENDING_STRUCTURE",
                    "ending close is not at the measure boundary",
                    canonical_id=measure.id,
                )
            if not active:
                active = _ending_numbers(marker.ending_number, measure.id)
                passes[-1] = active
            active = frozenset()
    if active:
        raise PlaybackProjectionError(
            "VIEWER_PLAYBACK_ENDING_STRUCTURE",
            "score ends with an unclosed volta ending",
        )
    return tuple(passes), tuple(closes)


def _ending_numbers(value: str | None, measure_id: str) -> frozenset[int]:
    if value is None:
        raise PlaybackProjectionError(
            "VIEWER_PLAYBACK_ENDING_NUMBER",
            "volta ending has no pass number",
            canonical_id=measure_id,
        )
    result: set[int] = set()
    try:
        for component in value.replace(" ", "").split(","):
            if "-" in component:
                start_text, end_text = component.split("-", 1)
                start, end = int(start_text), int(end_text)
                if start > end:
                    raise ValueError
                result.update(range(start, end + 1))
            else:
                result.add(int(component))
    except ValueError as error:
        raise PlaybackProjectionError(
            "VIEWER_PLAYBACK_ENDING_NUMBER",
            "volta ending pass list is invalid",
            canonical_id=measure_id,
        ) from error
    if not result or min(result) < 1:
        raise PlaybackProjectionError(
            "VIEWER_PLAYBACK_ENDING_NUMBER",
            "volta ending pass numbers must be positive",
            canonical_id=measure_id,
        )
    return frozenset(result)


def _navigation_targets(
    measures: tuple[TemporalMeasure, ...],
) -> tuple[dict[str, int], dict[str, int]]:
    segnos: dict[str, int] = {}
    codas: dict[str, int] = {}
    for index, measure in enumerate(measures):
        for sound in measure.sounds:
            for feature, value, targets in (
                ("segno", sound.segno, segnos),
                ("coda", sound.coda, codas),
            ):
                if value is None:
                    continue
                if sound.onset != 0:
                    raise PlaybackProjectionError(
                        "VIEWER_PLAYBACK_NAVIGATION_POSITION",
                        f"{feature} target is not at a measure boundary",
                        canonical_id=measure.id,
                    )
                _add_navigation_target(targets, value, index, feature, measure.id)
        for barline in measure.barlines:
            for marker in barline.navigation:
                if marker.kind not in {"segno", "coda"}:
                    continue
                if barline.onset != 0:
                    raise PlaybackProjectionError(
                        "VIEWER_PLAYBACK_NAVIGATION_POSITION",
                        f"{marker.kind} target is not at a measure boundary",
                        canonical_id=measure.id,
                    )
                targets = segnos if marker.kind == "segno" else codas
                _add_navigation_target(
                    targets,
                    marker.token,
                    index,
                    marker.kind,
                    measure.id,
                )
    return segnos, codas


def _add_navigation_target(
    targets: dict[str, int],
    token: str | None,
    index: int,
    feature: str,
    measure_id: str,
) -> None:
    key = _navigation_token(token)
    if key in targets and targets[key] != index:
        raise PlaybackProjectionError(
            "VIEWER_PLAYBACK_NAVIGATION_TARGET",
            f"multiple {feature} targets use the same token",
            canonical_id=measure_id,
        )
    targets[key] = index


def _navigation_action(measure: TemporalMeasure) -> _NavigationAction:
    relevant = [
        sound
        for sound in measure.sounds
        if sound.dacapo is True
        or sound.dalsegno is not None
        or sound.tocoda is not None
        or sound.fine is not None
    ]
    if any(sound.time_only is not None for sound in measure.sounds):
        raise PlaybackProjectionError(
            "VIEWER_PLAYBACK_TIME_ONLY",
            "time-only navigation requires an explicit pass-context policy",
            canonical_id=measure.id,
        )
    for sound in relevant:
        if sound.onset != measure.extent:
            raise PlaybackProjectionError(
                "VIEWER_PLAYBACK_NAVIGATION_POSITION",
                "jump or Fine instruction is not at the measure boundary",
                canonical_id=measure.id,
            )
    dacapo = [sound for sound in relevant if sound.dacapo is True]
    dalsegno = [sound.dalsegno for sound in relevant if sound.dalsegno is not None]
    tocoda = [sound.tocoda for sound in relevant if sound.tocoda is not None]
    fine = [sound.fine for sound in relevant if sound.fine is not None]
    if len(dacapo) > 1 or len(dalsegno) > 1 or len(tocoda) > 1 or len(fine) > 1:
        raise PlaybackProjectionError(
            "VIEWER_PLAYBACK_NAVIGATION_AMBIGUOUS",
            "measure contains duplicate jump instructions",
            canonical_id=measure.id,
        )
    if dacapo and dalsegno:
        raise PlaybackProjectionError(
            "VIEWER_PLAYBACK_NAVIGATION_AMBIGUOUS",
            "measure requests both Da Capo and Dal Segno",
            canonical_id=measure.id,
        )
    return _NavigationAction(
        dacapo=bool(dacapo),
        dalsegno=dalsegno[0] if dalsegno else None,
        tocoda=tocoda[0] if tocoda else None,
        fine=bool(fine),
    )


def _target_index(
    targets: dict[str, int],
    token: str,
    *,
    feature: str,
    measure_id: str,
) -> int:
    key = _navigation_token(token)
    if key not in targets:
        raise PlaybackProjectionError(
            "VIEWER_PLAYBACK_NAVIGATION_TARGET",
            f"{feature} target does not exist",
            canonical_id=measure_id,
        )
    return targets[key]


def _navigation_token(value: str | None) -> str:
    normalized = (value or "").strip()
    return "__default__" if normalized.casefold() in {"", "yes"} else normalized


def _repeat_total(value: str | None, measure_id: str) -> int:
    if value is None:
        return 2
    try:
        total = int(value)
    except ValueError as error:
        raise PlaybackProjectionError(
            "VIEWER_PLAYBACK_REPEAT_TIMES",
            "backward-repeat times is not an integer",
            canonical_id=measure_id,
        ) from error
    if total < 1:
        raise PlaybackProjectionError(
            "VIEWER_PLAYBACK_REPEAT_TIMES",
            "backward-repeat times must be positive",
            canonical_id=measure_id,
        )
    return total


def _measure_tempos(parts: tuple[TemporalPart, ...], index: int) -> tuple[_TempoSource, ...]:
    result: list[_TempoSource] = []
    for part in parts:
        measure = part.measures[index]
        for sound in measure.sounds:
            if sound.tempo is not None:
                if sound.tempo <= 0:
                    raise PlaybackProjectionError(
                        "VIEWER_PLAYBACK_TEMPO_VALUE",
                        "canonical tempo must be positive",
                        canonical_id=measure.id,
                    )
                result.append(
                    _TempoSource(
                        part_id=part.id,
                        measure_id=measure.id,
                        local_onset=sound.onset,
                        score_onset=sound.score_onset,
                        source_order=sound.source_order,
                        qpm=sound.tempo,
                    )
                )
    return tuple(
        sorted(result, key=lambda item: (item.local_onset, item.part_id, item.source_order))
    )


def _unique_tempos_by_onset(
    sources: tuple[_TempoSource, ...],
) -> dict[Fraction, tuple[_TempoSource, ...]]:
    grouped: dict[Fraction, list[_TempoSource]] = {}
    for source in sources:
        grouped.setdefault(source.local_onset, []).append(source)
    result: dict[Fraction, tuple[_TempoSource, ...]] = {}
    for onset, group in grouped.items():
        values = {item.qpm for item in group}
        if len(values) != 1:
            raise PlaybackProjectionError(
                "VIEWER_PLAYBACK_TEMPO_CONFLICT",
                "simultaneous canonical tempo directives disagree",
                canonical_id=group[0].measure_id,
            )
        result[onset] = tuple(group)
    return result


def _event_playback_duration(event: TemporalEvent) -> Fraction:
    duration = event.performed_duration if event.performed_duration is not None else event.duration
    if duration <= 0:
        raise PlaybackProjectionError(
            "VIEWER_PLAYBACK_EVENT_DURATION",
            "event has no positive deterministic playback duration",
            canonical_id=event.id,
        )
    return duration


def _event_dynamics(
    measure: TemporalMeasure, initial: Fraction | None
) -> dict[str, Fraction | None]:
    changes = sorted(
        (
            (sound.onset, sound.source_order, sound.dynamics)
            for sound in measure.sounds
            if sound.dynamics is not None
        ),
        key=lambda item: (item[0], item[1]),
    )
    result: dict[str, Fraction | None] = {}
    current = initial
    change_index = 0
    for event in sorted(measure.events, key=lambda item: (item.onset, item.source_order)):
        while change_index < len(changes) and changes[change_index][0] <= event.onset:
            current = changes[change_index][2]
            change_index += 1
        result[event.id] = current
    return result


def _ending_dynamics(measure: TemporalMeasure, initial: Fraction | None) -> Fraction | None:
    current = initial
    for sound in sorted(measure.sounds, key=lambda item: (item.onset, item.source_order)):
        if sound.dynamics is not None:
            current = sound.dynamics
    return current


def _active_clefs(
    score: TemporalScore,
) -> tuple[
    dict[tuple[str, str], tuple[str, PlaybackClef]],
    set[str],
]:
    result: dict[tuple[str, str], tuple[str, PlaybackClef]] = {}
    missing: set[str] = set()
    for part in score.parts:
        active: dict[str, TemporalClef] = {}
        for measure in part.measures:
            changes: list[tuple[Fraction, int, TemporalClef]] = []
            for attributes in measure.attributes:
                changes.extend(
                    (attributes.onset, attributes.source_order, clef) for clef in attributes.clefs
                )
            changes.sort(key=lambda item: (item[0], item[1], item[2].staff))
            change_index = 0
            for event in sorted(measure.events, key=lambda item: (item.onset, item.source_order)):
                while change_index < len(changes) and changes[change_index][0] <= event.onset:
                    clef = changes[change_index][2]
                    active[clef.staff] = clef
                    change_index += 1
                active_clef = active.get(event.staff)
                if active_clef is None:
                    missing.add(event.id)
                    continue
                playback_clef = PlaybackClef(
                    active_clef.sign, active_clef.line, active_clef.octave_change
                )
                octave = (
                    active_clef.octave_change if active_clef.octave_change is not None else "none"
                )
                group_id = (
                    f"{part.id}:staff:{event.staff}:clef:{active_clef.sign}:"
                    f"{active_clef.line if active_clef.line is not None else 'none'}:"
                    f"{octave}"
                )
                result[(part.id, event.id)] = (group_id, playback_clef)
            for _, _, clef in changes[change_index:]:
                active[clef.staff] = clef
    return result, missing


def _playback_source(
    part: TemporalPart,
    measure: TemporalMeasure,
    event: TemporalEvent,
    clef_state: tuple[str, PlaybackClef] | None,
) -> PlaybackSourceEvent:
    return PlaybackSourceEvent(
        event_id=event.id,
        part_id=part.id,
        measure_id=measure.id,
        staff=event.staff,
        voice=event.voice,
        score_onset=event.score_onset,
        clef_group_id=clef_state[0] if clef_state is not None else None,
        clef=clef_state[1] if clef_state is not None else None,
    )


def _sounding_tie_groups(spans: tuple[NotationSpan, ...]) -> dict[str, str]:
    parent: dict[str, str] = {}

    def find(value: str) -> str:
        parent.setdefault(value, value)
        while parent[value] != value:
            parent[value] = parent[parent[value]]
            value = parent[value]
        return value

    def union(left: str, right: str) -> None:
        left_root = find(left)
        right_root = find(right)
        if left_root != right_root:
            parent[max(left_root, right_root)] = min(left_root, right_root)

    for span in spans:
        if span.kind != "sounding-tie":
            continue
        event_ids = [endpoint.anchor.event_id for endpoint in span.endpoints]
        for event_id in event_ids:
            find(event_id)
        for left, right in zip(event_ids, event_ids[1:], strict=False):
            union(left, right)
    return {event_id: find(event_id) for event_id in parent}


def _resolve_ties(candidates: list[_Candidate]) -> list[PlaybackNote]:
    untied = [candidate for candidate in candidates if candidate.tie_group is None]
    groups: dict[tuple[str, int], list[_Candidate]] = {}
    for candidate in candidates:
        if candidate.tie_group is not None:
            groups.setdefault((candidate.tie_group, candidate.midi_pitch), []).append(candidate)

    notes = [_candidate_to_note(candidate, (candidate,)) for candidate in untied]
    for tied_candidates in groups.values():
        ordered = sorted(tied_candidates, key=lambda item: (item.start, item.id))
        run: list[_Candidate] = []
        for candidate in ordered:
            if run and (
                run[-1].end != candidate.start
                or candidate.source.event_id in {item.source.event_id for item in run}
            ):
                notes.append(_candidate_to_note(run[0], tuple(run)))
                run = []
            run.append(candidate)
        if run:
            notes.append(_candidate_to_note(run[0], tuple(run)))
    return notes


def _candidate_to_note(first: _Candidate, run: tuple[_Candidate, ...]) -> PlaybackNote:
    start = _round_microseconds(run[0].start)
    end = _round_microseconds(run[-1].end)
    if end <= start:
        raise PlaybackProjectionError(
            "VIEWER_PLAYBACK_TIME_RESOLUTION",
            "integer-microsecond conversion erased a positive note duration",
            canonical_id=first.source.event_id,
        )
    chord_ids = {item.chord_id for item in run}
    return PlaybackNote(
        id=(first.id if len(run) == 1 else f"playback-tie:{first.id}"),
        start_microseconds=start,
        end_microseconds=end,
        midi_pitch=first.midi_pitch,
        source_events=tuple(item.source for item in run),
        chord_id=next(iter(chord_ids)) if len(chord_ids) == 1 else None,
        dynamic_percent=first.dynamic_percent,
    )


def _round_microseconds(value: Fraction) -> int:
    """Round a non-negative exact time to nearest integer, ties to even."""

    if value < 0:
        raise ValueError("playback time cannot be negative")
    quotient, remainder = divmod(value.numerator, value.denominator)
    doubled = remainder * 2
    if doubled < value.denominator:
        return quotient
    if doubled > value.denominator:
        return quotient + 1
    return quotient if quotient % 2 == 0 else quotient + 1
