"""Validation for TeachMeMusic's canonical score representation."""

import re
from collections.abc import Callable
from dataclasses import dataclass
from fractions import Fraction
from pathlib import PurePath

from teachmemusic.score.models import (
    CURRENT_SCHEMA_VERSION,
    AttributeChange,
    Clef,
    HarmonySymbol,
    NoteEvent,
    PitchStep,
    RestEvent,
    RhythmicValue,
    ScoreRepresentation,
    WrittenRhythm,
)

_BASE_DURATIONS = {
    RhythmicValue.BREVE: Fraction(8),
    RhythmicValue.WHOLE: Fraction(4),
    RhythmicValue.HALF: Fraction(2),
    RhythmicValue.QUARTER: Fraction(1),
    RhythmicValue.EIGHTH: Fraction(1, 2),
    RhythmicValue.SIXTEENTH: Fraction(1, 4),
    RhythmicValue.THIRTY_SECOND: Fraction(1, 8),
    RhythmicValue.SIXTY_FOURTH: Fraction(1, 16),
}
_SHA256_PATTERN = re.compile(r"[0-9a-f]{64}")
_HARMONY_KIND_PATTERN = re.compile(r"[a-z][a-z0-9-]*")


@dataclass(frozen=True, slots=True)
class ValidationIssue:
    """One machine-readable canonical-score validation failure."""

    code: str
    path: str
    message: str


class ScoreValidationError(ValueError):
    """Raised when a canonical score contains validation failures."""

    def __init__(self, issues: tuple[ValidationIssue, ...]) -> None:
        self.issues = issues
        details = "; ".join(f"{issue.code} at {issue.path}: {issue.message}" for issue in issues)
        super().__init__(details)


def written_duration(rhythm: WrittenRhythm) -> Fraction:
    """Return the exact quarter-note duration implied by a written rhythm."""

    base = _BASE_DURATIONS[rhythm.value]
    duration = base
    addition = base
    for _ in range(rhythm.dots):
        addition /= 2
        duration += addition
    return duration


def validate_score(score: ScoreRepresentation) -> tuple[ValidationIssue, ...]:
    """Return every detected structural or semantic validation issue."""

    issues: list[ValidationIssue] = []
    registered_ids: dict[str, str] = {}

    def add(code: str, path: str, message: str) -> None:
        issues.append(ValidationIssue(code=code, path=path, message=message))

    def require_id(value: object, path: str) -> None:
        if not isinstance(value, str) or not value.strip():
            add("INVALID_ID", path, "ID must be a non-empty string")
            return
        previous_path = registered_ids.get(value)
        if previous_path is not None:
            add("DUPLICATE_ID", path, f"ID is already used at {previous_path}")
            return
        registered_ids[value] = path

    def require_fraction(value: object, path: str) -> bool:
        if not isinstance(value, Fraction):
            add("INEXACT_TIME", path, "musical time must be fractions.Fraction")
            return False
        return True

    require_id(score.id, "score.id")
    if score.schema_version != CURRENT_SCHEMA_VERSION:
        add(
            "UNSUPPORTED_SCHEMA_VERSION",
            "score.schema_version",
            f"expected {CURRENT_SCHEMA_VERSION}, got {score.schema_version}",
        )
    if score.metadata.title is not None and not isinstance(score.metadata.title, str):
        add("INVALID_TEXT", "score.metadata.title", "title must be text or None")
    if not isinstance(score.metadata.creators, tuple):
        add("MUTABLE_COLLECTION", "score.metadata.creators", "creators must be a tuple")
    for creator_index, creator in enumerate(score.metadata.creators):
        creator_path = f"score.metadata.creators[{creator_index}]"
        if not creator.role.strip():
            add("EMPTY_CREATOR_ROLE", f"{creator_path}.role", "creator role must not be empty")
        if not creator.name.strip():
            add("EMPTY_CREATOR_NAME", f"{creator_path}.name", "creator name must not be empty")

    if not isinstance(score.parts, tuple):
        add("MUTABLE_COLLECTION", "score.parts", "parts must be a tuple")
    if not score.parts:
        add("EMPTY_SCORE", "score.parts", "a score must contain at least one part")

    all_measure_ids: set[str] = set()
    for part_index, part in enumerate(score.parts):
        part_path = f"score.parts[{part_index}]"
        require_id(part.id, f"{part_path}.id")
        if part.source_id is not None and not isinstance(part.source_id, str):
            add("INVALID_TEXT", f"{part_path}.source_id", "source ID must be text or None")
        if part.display_name is not None and not isinstance(part.display_name, str):
            add("INVALID_TEXT", f"{part_path}.display_name", "display name must be text or None")
        if not isinstance(part.staves, tuple):
            add("MUTABLE_COLLECTION", f"{part_path}.staves", "staves must be a tuple")
        if not isinstance(part.voices, tuple):
            add("MUTABLE_COLLECTION", f"{part_path}.voices", "voices must be a tuple")
        if not isinstance(part.measures, tuple):
            add("MUTABLE_COLLECTION", f"{part_path}.measures", "measures must be a tuple")
        if not part.staves:
            add("EMPTY_PART", f"{part_path}.staves", "a part must contain at least one staff")
        if not part.voices:
            add("EMPTY_PART", f"{part_path}.voices", "a part must contain at least one voice")
        if not part.measures:
            add("EMPTY_PART", f"{part_path}.measures", "a part must contain at least one measure")

        staff_ids: set[str] = set()
        for staff_index, staff in enumerate(part.staves):
            staff_path = f"{part_path}.staves[{staff_index}]"
            require_id(staff.id, f"{staff_path}.id")
            staff_ids.add(staff.id)
            if staff.source_number is not None and staff.source_number <= 0:
                add(
                    "INVALID_STAFF_NUMBER",
                    f"{staff_path}.source_number",
                    "source staff number must be positive",
                )

        voice_ids: set[str] = set()
        for voice_index, voice in enumerate(part.voices):
            voice_path = f"{part_path}.voices[{voice_index}]"
            require_id(voice.id, f"{voice_path}.id")
            voice_ids.add(voice.id)

        for measure_index, measure in enumerate(part.measures):
            measure_path = f"{part_path}.measures[{measure_index}]"
            require_id(measure.id, f"{measure_path}.id")
            all_measure_ids.add(measure.id)
            expected_ordinal = measure_index + 1
            if measure.ordinal != expected_ordinal:
                add(
                    "INVALID_MEASURE_ORDER",
                    f"{measure_path}.ordinal",
                    f"expected ordinal {expected_ordinal}, got {measure.ordinal}",
                )
            valid_extent = require_fraction(measure.extent, f"{measure_path}.extent")
            if valid_extent and measure.extent <= 0:
                add("INVALID_MEASURE_EXTENT", f"{measure_path}.extent", "extent must be positive")
            if not isinstance(measure.attribute_changes, tuple):
                add(
                    "MUTABLE_COLLECTION",
                    f"{measure_path}.attribute_changes",
                    "attribute changes must be a tuple",
                )
            if not isinstance(measure.events, tuple):
                add("MUTABLE_COLLECTION", f"{measure_path}.events", "events must be a tuple")
            if not isinstance(measure.harmonies, tuple):
                add(
                    "MUTABLE_COLLECTION",
                    f"{measure_path}.harmonies",
                    "harmonies must be a tuple",
                )
            if not isinstance(measure.barlines, tuple):
                add("MUTABLE_COLLECTION", f"{measure_path}.barlines", "barlines must be a tuple")

            _validate_attribute_changes(
                measure.attribute_changes,
                measure.extent,
                staff_ids,
                measure_path,
                issues,
            )
            _validate_events(
                measure.events,
                measure.extent,
                staff_ids,
                voice_ids,
                measure_path,
                issues,
                require_id,
            )
            _validate_harmonies(
                measure.harmonies,
                measure.extent,
                staff_ids,
                measure_path,
                issues,
                require_id,
            )
            for barline_index, barline in enumerate(measure.barlines):
                if barline.terminates_score and measure_index != len(part.measures) - 1:
                    add(
                        "EARLY_SCORE_TERMINATION",
                        f"{measure_path}.barlines[{barline_index}]",
                        "a terminating barline must be on the final measure of its part",
                    )

    if not isinstance(score.presentation.breaks, tuple):
        add(
            "MUTABLE_COLLECTION",
            "score.presentation.breaks",
            "presentation breaks must be a tuple",
        )
    for break_index, presentation_break in enumerate(score.presentation.breaks):
        break_path = f"score.presentation.breaks[{break_index}]"
        if presentation_break.before_measure_id not in all_measure_ids:
            add(
                "UNKNOWN_MEASURE_REFERENCE",
                f"{break_path}.before_measure_id",
                "presentation break references an unknown measure",
            )

    if score.playback is not None:
        playback = score.playback
        if playback.tempo_quarter_bpm is not None:
            tempo_path = "score.playback.tempo_quarter_bpm"
            if (
                require_fraction(playback.tempo_quarter_bpm, tempo_path)
                and playback.tempo_quarter_bpm <= 0
            ):
                add("INVALID_TEMPO", tempo_path, "tempo must be positive")
        if playback.midi_channel is not None and not 1 <= playback.midi_channel <= 16:
            add("INVALID_MIDI_CHANNEL", "score.playback.midi_channel", "expected 1 through 16")
        if playback.midi_program is not None and not 1 <= playback.midi_program <= 128:
            add("INVALID_MIDI_PROGRAM", "score.playback.midi_program", "expected 1 through 128")

    if not isinstance(score.provenance, tuple):
        add("MUTABLE_COLLECTION", "score.provenance", "provenance must be a tuple")
    for source_index, source in enumerate(score.provenance):
        source_path = f"score.provenance[{source_index}]"
        if not source.logical_name.strip():
            add(
                "EMPTY_SOURCE_NAME", f"{source_path}.logical_name", "logical name must not be empty"
            )
        if PurePath(source.logical_name).is_absolute():
            add(
                "ABSOLUTE_SOURCE_PATH",
                f"{source_path}.logical_name",
                "source identity must not be a machine-specific absolute path",
            )
        if source.sha256 is not None and _SHA256_PATTERN.fullmatch(source.sha256) is None:
            add("INVALID_SHA256", f"{source_path}.sha256", "expected 64 lowercase hex characters")

    return tuple(issues)


def require_valid_score(score: ScoreRepresentation) -> None:
    """Raise :class:`ScoreValidationError` if ``score`` is invalid."""

    issues = validate_score(score)
    if issues:
        raise ScoreValidationError(issues)


def _validate_attribute_changes(
    changes: tuple[AttributeChange, ...],
    extent: Fraction,
    staff_ids: set[str],
    measure_path: str,
    issues: list[ValidationIssue],
) -> None:
    previous_onset: Fraction | None = None
    for change_index, change in enumerate(changes):
        change_path = f"{measure_path}.attribute_changes[{change_index}]"
        if not isinstance(change.onset, Fraction):
            issues.append(
                ValidationIssue("INEXACT_TIME", f"{change_path}.onset", "onset must be Fraction")
            )
            continue
        if change.onset < 0 or change.onset >= extent:
            issues.append(
                ValidationIssue(
                    "ATTRIBUTE_OUTSIDE_MEASURE",
                    f"{change_path}.onset",
                    "attribute onset must be within the measure",
                )
            )
        if change.onset != 0:
            issues.append(
                ValidationIssue(
                    "UNSUPPORTED_MID_MEASURE_ATTRIBUTE",
                    f"{change_path}.onset",
                    "DEV-004 supports attribute changes only at measure onset",
                )
            )
        if previous_onset is not None and change.onset < previous_onset:
            issues.append(
                ValidationIssue(
                    "UNSORTED_ATTRIBUTES",
                    f"{change_path}.onset",
                    "attribute changes must be ordered by onset",
                )
            )
        previous_onset = change.onset
        if not change.clefs and change.key_signature is None and change.time_signature is None:
            issues.append(
                ValidationIssue(
                    "EMPTY_ATTRIBUTE_CHANGE",
                    change_path,
                    "attribute change must change at least one attribute",
                )
            )
        for clef_index, clef in enumerate(change.clefs):
            _validate_clef(clef, staff_ids, f"{change_path}.clefs[{clef_index}]", issues)
        if change.key_signature is not None:
            key = change.key_signature
            if not -7 <= key.fifths <= 7:
                issues.append(
                    ValidationIssue(
                        "INVALID_KEY_SIGNATURE",
                        f"{change_path}.key_signature.fifths",
                        "traditional fifths value must be between -7 and 7",
                    )
                )
        if change.time_signature is not None:
            meter = change.time_signature
            if not meter.beat_groups or any(group <= 0 for group in meter.beat_groups):
                issues.append(
                    ValidationIssue(
                        "INVALID_TIME_SIGNATURE",
                        f"{change_path}.time_signature.beat_groups",
                        "beat groups must contain positive integers",
                    )
                )
            if meter.beat_type <= 0:
                issues.append(
                    ValidationIssue(
                        "INVALID_TIME_SIGNATURE",
                        f"{change_path}.time_signature.beat_type",
                        "beat type must be positive",
                    )
                )


def _validate_clef(
    clef: Clef,
    staff_ids: set[str],
    path: str,
    issues: list[ValidationIssue],
) -> None:
    if clef.staff_id not in staff_ids:
        issues.append(
            ValidationIssue("UNKNOWN_STAFF_REFERENCE", f"{path}.staff_id", "unknown staff ID")
        )
    if clef.line <= 0:
        issues.append(ValidationIssue("INVALID_CLEF_LINE", f"{path}.line", "line must be positive"))


def _validate_events(
    events: tuple[NoteEvent | RestEvent, ...],
    extent: Fraction,
    staff_ids: set[str],
    voice_ids: set[str],
    measure_path: str,
    issues: list[ValidationIssue],
    require_id: Callable[[object, str], None],
) -> None:
    previous_key: tuple[Fraction, int] | None = None
    source_orders: set[int] = set()
    chord_groups: dict[str, list[tuple[NoteEvent, str]]] = {}
    for event_index, event in enumerate(events):
        event_path = f"{measure_path}.events[{event_index}]"
        if not isinstance(event, (NoteEvent, RestEvent)):
            issues.append(
                ValidationIssue("UNSUPPORTED_EVENT", event_path, "event type is not supported")
            )
            continue
        require_id(event.id, f"{event_path}.id")
        if event.staff_id not in staff_ids:
            issues.append(
                ValidationIssue(
                    "UNKNOWN_STAFF_REFERENCE", f"{event_path}.staff_id", "unknown staff ID"
                )
            )
        if event.voice_id not in voice_ids:
            issues.append(
                ValidationIssue(
                    "UNKNOWN_VOICE_REFERENCE", f"{event_path}.voice_id", "unknown voice ID"
                )
            )
        if not isinstance(event.onset, Fraction):
            issues.append(
                ValidationIssue("INEXACT_TIME", f"{event_path}.onset", "onset must be Fraction")
            )
            continue
        if not isinstance(event.duration, Fraction):
            issues.append(
                ValidationIssue(
                    "INEXACT_TIME", f"{event_path}.duration", "duration must be Fraction"
                )
            )
            continue
        if event.onset < 0:
            issues.append(
                ValidationIssue(
                    "NEGATIVE_ONSET", f"{event_path}.onset", "onset must not be negative"
                )
            )
        if event.duration <= 0:
            issues.append(
                ValidationIssue(
                    "NON_POSITIVE_DURATION",
                    f"{event_path}.duration",
                    "duration must be positive",
                )
            )
        if event.onset + event.duration > extent:
            issues.append(
                ValidationIssue(
                    "EVENT_OUTSIDE_MEASURE",
                    event_path,
                    "event ends after the measure extent",
                )
            )
        if event.source_order < 0:
            issues.append(
                ValidationIssue(
                    "INVALID_SOURCE_ORDER",
                    f"{event_path}.source_order",
                    "source order must not be negative",
                )
            )
        if event.source_order in source_orders:
            issues.append(
                ValidationIssue(
                    "DUPLICATE_SOURCE_ORDER",
                    f"{event_path}.source_order",
                    "source order must be unique within a measure",
                )
            )
        source_orders.add(event.source_order)
        order_key = (event.onset, event.source_order)
        if previous_key is not None and order_key < previous_key:
            issues.append(
                ValidationIssue(
                    "UNSORTED_EVENTS",
                    event_path,
                    "events must be ordered by onset and source order",
                )
            )
        previous_key = order_key
        _validate_rhythm(event.rhythm, event.duration, f"{event_path}.rhythm", issues)
        if isinstance(event, NoteEvent):
            if event.chord_id is not None:
                chord_path = f"{event_path}.chord_id"
                if not isinstance(event.chord_id, str) or not event.chord_id.strip():
                    issues.append(
                        ValidationIssue(
                            "INVALID_CHORD_ID",
                            chord_path,
                            "chord ID must be a non-empty string or None",
                        )
                    )
                else:
                    chord_groups.setdefault(event.chord_id, []).append((event, chord_path))
            if not isinstance(event.pitch.alter, Fraction):
                issues.append(
                    ValidationIssue(
                        "INVALID_PITCH_ALTER",
                        f"{event_path}.pitch.alter",
                        "pitch alteration must be Fraction",
                    )
                )
            if not -1 <= event.pitch.octave <= 9:
                issues.append(
                    ValidationIssue(
                        "INVALID_OCTAVE",
                        f"{event_path}.pitch.octave",
                        "octave must be between -1 and 9",
                    )
                )
            if not isinstance(event.lyrics, tuple):
                issues.append(
                    ValidationIssue(
                        "MUTABLE_COLLECTION",
                        f"{event_path}.lyrics",
                        "lyrics must be a tuple",
                    )
                )
            lyric_lines: set[str] = set()
            for lyric_index, lyric in enumerate(event.lyrics):
                lyric_path = f"{event_path}.lyrics[{lyric_index}]"
                if not lyric.line:
                    issues.append(
                        ValidationIssue(
                            "EMPTY_LYRIC_LINE", f"{lyric_path}.line", "lyric line must not be empty"
                        )
                    )
                if lyric.line in lyric_lines:
                    issues.append(
                        ValidationIssue(
                            "DUPLICATE_LYRIC_LINE",
                            f"{lyric_path}.line",
                            "a note may have at most one lyric per line",
                        )
                    )
                lyric_lines.add(lyric.line)

    for chord_id, members in chord_groups.items():
        require_id(chord_id, members[0][1])
        if len(members) < 2:
            issues.append(
                ValidationIssue(
                    "SINGLE_NOTE_CHORD",
                    members[0][1],
                    "a chord must contain at least two notes",
                )
            )
            continue
        first = members[0][0]
        for member, member_path in members[1:]:
            if (
                member.onset != first.onset
                or member.duration != first.duration
                or member.staff_id != first.staff_id
                or member.voice_id != first.voice_id
                or member.rhythm != first.rhythm
            ):
                issues.append(
                    ValidationIssue(
                        "INCONSISTENT_CHORD",
                        member_path,
                        "chord members must share onset, duration, staff, voice, and rhythm",
                    )
                )


def _validate_harmonies(
    harmonies: tuple[HarmonySymbol, ...],
    extent: Fraction,
    staff_ids: set[str],
    measure_path: str,
    issues: list[ValidationIssue],
    require_id: Callable[[object, str], None],
) -> None:
    previous_key: tuple[Fraction, int] | None = None
    source_orders: set[int] = set()
    for harmony_index, harmony in enumerate(harmonies):
        harmony_path = f"{measure_path}.harmonies[{harmony_index}]"
        require_id(harmony.id, f"{harmony_path}.id")
        if harmony.staff_id not in staff_ids:
            issues.append(
                ValidationIssue(
                    "UNKNOWN_STAFF_REFERENCE",
                    f"{harmony_path}.staff_id",
                    "unknown staff ID",
                )
            )
        if not isinstance(harmony.onset, Fraction):
            issues.append(
                ValidationIssue(
                    "INEXACT_TIME",
                    f"{harmony_path}.onset",
                    "onset must be Fraction",
                )
            )
            continue
        if harmony.onset < 0 or harmony.onset >= extent:
            issues.append(
                ValidationIssue(
                    "HARMONY_OUTSIDE_MEASURE",
                    f"{harmony_path}.onset",
                    "harmony onset must be within the measure",
                )
            )
        if harmony.source_order < 0:
            issues.append(
                ValidationIssue(
                    "INVALID_SOURCE_ORDER",
                    f"{harmony_path}.source_order",
                    "source order must not be negative",
                )
            )
        if harmony.source_order in source_orders:
            issues.append(
                ValidationIssue(
                    "DUPLICATE_SOURCE_ORDER",
                    f"{harmony_path}.source_order",
                    "harmony source order must be unique within a measure",
                )
            )
        source_orders.add(harmony.source_order)
        order_key = (harmony.onset, harmony.source_order)
        if previous_key is not None and order_key < previous_key:
            issues.append(
                ValidationIssue(
                    "UNSORTED_HARMONIES",
                    harmony_path,
                    "harmonies must be ordered by onset and source order",
                )
            )
        previous_key = order_key
        if not isinstance(harmony.root.step, PitchStep):
            issues.append(
                ValidationIssue(
                    "INVALID_PITCH_STEP",
                    f"{harmony_path}.root.step",
                    "harmony root step is not supported",
                )
            )
        if not isinstance(harmony.root.alter, Fraction):
            issues.append(
                ValidationIssue(
                    "INVALID_PITCH_ALTER",
                    f"{harmony_path}.root.alter",
                    "harmony root alteration must be Fraction",
                )
            )
        if (
            not isinstance(harmony.kind, str)
            or _HARMONY_KIND_PATTERN.fullmatch(harmony.kind) is None
        ):
            issues.append(
                ValidationIssue(
                    "INVALID_HARMONY_KIND",
                    f"{harmony_path}.kind",
                    "harmony kind must be a lowercase canonical token",
                )
            )
        if harmony.display_text is not None and not isinstance(harmony.display_text, str):
            issues.append(
                ValidationIssue(
                    "INVALID_TEXT",
                    f"{harmony_path}.display_text",
                    "display text must be text or None",
                )
            )


def _validate_rhythm(
    rhythm: WrittenRhythm,
    duration: Fraction,
    path: str,
    issues: list[ValidationIssue],
) -> None:
    if rhythm.dots < 0:
        issues.append(
            ValidationIssue("INVALID_DOT_COUNT", f"{path}.dots", "dots must not be negative")
        )
        return
    expected = written_duration(rhythm)
    if duration != expected:
        issues.append(
            ValidationIssue(
                "RHYTHM_DURATION_MISMATCH",
                path,
                f"written rhythm implies {expected}, but duration is {duration}",
            )
        )
