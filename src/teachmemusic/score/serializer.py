"""Deterministic JSON serialization for canonical score models."""

import json
from enum import StrEnum
from fractions import Fraction
from typing import cast

from teachmemusic.score.models import (
    CURRENT_SCHEMA_VERSION,
    AttributeChange,
    Barline,
    BarlineLocation,
    BarlineStyle,
    BreakKind,
    Clef,
    ClefSign,
    Creator,
    HarmonySymbol,
    KeySignature,
    Lyric,
    Measure,
    NoteEvent,
    Part,
    PitchStep,
    PlaybackData,
    PresentationBreak,
    PresentationData,
    RestEvent,
    RhythmicValue,
    ScoreEvent,
    ScoreMetadata,
    ScoreRepresentation,
    SourceFormat,
    SourceReference,
    Staff,
    StemDirection,
    Syllabic,
    TimeSignature,
    Voice,
    WrittenPitch,
    WrittenPitchClass,
    WrittenRhythm,
)
from teachmemusic.score.validation import ScoreValidationError, require_valid_score


class ScoreSerializationError(ValueError):
    """Raised when serialized score data is malformed or unsupported."""


def score_to_dict(score: ScoreRepresentation) -> dict[str, object]:
    """Convert a valid canonical score to JSON-compatible data."""

    require_valid_score(score)
    return {
        "id": score.id,
        "metadata": _metadata_to_dict(score.metadata),
        "parts": [_part_to_dict(part) for part in score.parts],
        "playback": _playback_to_dict(score.playback) if score.playback is not None else None,
        "presentation": {
            "breaks": [
                {
                    "before_measure_id": item.before_measure_id,
                    "kind": item.kind.value,
                }
                for item in score.presentation.breaks
            ]
        },
        "provenance": [
            {
                "logical_name": source.logical_name,
                "sha256": source.sha256,
                "source_format": source.source_format.value,
            }
            for source in score.provenance
        ],
        "schema_version": score.schema_version,
    }


def score_to_json(score: ScoreRepresentation) -> str:
    """Serialize a score to stable, human-readable JSON."""

    return json.dumps(score_to_dict(score), ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def score_from_dict(data: object) -> ScoreRepresentation:
    """Deserialize JSON-compatible data into a validated canonical score."""

    root = _mapping(data, "score")
    _expect_keys(
        root,
        {
            "id",
            "metadata",
            "parts",
            "playback",
            "presentation",
            "provenance",
            "schema_version",
        },
        "score",
    )
    schema_version = _integer(root["schema_version"], "score.schema_version")
    if schema_version != CURRENT_SCHEMA_VERSION:
        raise ScoreSerializationError(
            f"score.schema_version: unsupported version {schema_version}; "
            f"expected {CURRENT_SCHEMA_VERSION}"
        )
    score = ScoreRepresentation(
        id=_string(root["id"], "score.id"),
        metadata=_metadata_from_dict(root["metadata"], "score.metadata"),
        parts=tuple(
            _part_from_dict(item, f"score.parts[{index}]")
            for index, item in enumerate(_sequence(root["parts"], "score.parts"))
        ),
        presentation=_presentation_from_dict(root["presentation"], "score.presentation"),
        playback=(
            None
            if root["playback"] is None
            else _playback_from_dict(root["playback"], "score.playback")
        ),
        provenance=tuple(
            _source_from_dict(item, f"score.provenance[{index}]")
            for index, item in enumerate(_sequence(root["provenance"], "score.provenance"))
        ),
        schema_version=schema_version,
    )
    try:
        require_valid_score(score)
    except ScoreValidationError as error:
        raise ScoreSerializationError(f"deserialized score is invalid: {error}") from error
    return score


def score_from_json(payload: str) -> ScoreRepresentation:
    """Deserialize a canonical score from JSON text."""

    try:
        data = json.loads(payload)
    except json.JSONDecodeError as error:
        raise ScoreSerializationError(f"invalid JSON: {error.msg}") from error
    return score_from_dict(data)


def _metadata_to_dict(metadata: ScoreMetadata) -> dict[str, object]:
    return {
        "creators": [{"name": item.name, "role": item.role} for item in metadata.creators],
        "title": metadata.title,
    }


def _part_to_dict(part: Part) -> dict[str, object]:
    return {
        "display_name": part.display_name,
        "id": part.id,
        "measures": [_measure_to_dict(measure) for measure in part.measures],
        "source_id": part.source_id,
        "staves": [{"id": staff.id, "source_number": staff.source_number} for staff in part.staves],
        "voices": [{"id": voice.id, "source_id": voice.source_id} for voice in part.voices],
    }


def _measure_to_dict(measure: Measure) -> dict[str, object]:
    return {
        "attribute_changes": [_attribute_to_dict(item) for item in measure.attribute_changes],
        "barlines": [
            {
                "location": item.location.value,
                "style": item.style.value,
                "terminates_score": item.terminates_score,
            }
            for item in measure.barlines
        ],
        "events": [_event_to_dict(event) for event in measure.events],
        "extent": _fraction_to_dict(measure.extent),
        "harmonies": [_harmony_to_dict(harmony) for harmony in measure.harmonies],
        "id": measure.id,
        "ordinal": measure.ordinal,
        "source_label": measure.source_label,
    }


def _attribute_to_dict(change: AttributeChange) -> dict[str, object]:
    return {
        "clefs": [
            {
                "line": clef.line,
                "octave_change": clef.octave_change,
                "sign": clef.sign.value,
                "staff_id": clef.staff_id,
            }
            for clef in change.clefs
        ],
        "key_signature": (
            None
            if change.key_signature is None
            else {"fifths": change.key_signature.fifths, "mode": change.key_signature.mode}
        ),
        "onset": _fraction_to_dict(change.onset),
        "time_signature": (
            None
            if change.time_signature is None
            else {
                "beat_groups": list(change.time_signature.beat_groups),
                "beat_type": change.time_signature.beat_type,
            }
        ),
    }


def _event_to_dict(event: ScoreEvent) -> dict[str, object]:
    common: dict[str, object] = {
        "duration": _fraction_to_dict(event.duration),
        "id": event.id,
        "onset": _fraction_to_dict(event.onset),
        "rhythm": {"dots": event.rhythm.dots, "value": event.rhythm.value.value},
        "source_order": event.source_order,
        "staff_id": event.staff_id,
        "voice_id": event.voice_id,
    }
    if isinstance(event, NoteEvent):
        common.update(
            {
                "kind": "note",
                "chord_id": event.chord_id,
                "lyrics": [
                    {
                        "line": lyric.line,
                        "syllabic": lyric.syllabic.value,
                        "text": lyric.text,
                    }
                    for lyric in event.lyrics
                ],
                "pitch": {
                    "alter": _fraction_to_dict(event.pitch.alter),
                    "octave": event.pitch.octave,
                    "step": event.pitch.step.value,
                },
                "stem_direction": (
                    event.stem_direction.value if event.stem_direction is not None else None
                ),
            }
        )
    else:
        common["kind"] = "rest"
    return common


def _harmony_to_dict(harmony: HarmonySymbol) -> dict[str, object]:
    return {
        "display_text": harmony.display_text,
        "id": harmony.id,
        "kind": harmony.kind,
        "onset": _fraction_to_dict(harmony.onset),
        "root": {
            "alter": _fraction_to_dict(harmony.root.alter),
            "step": harmony.root.step.value,
        },
        "source_order": harmony.source_order,
        "staff_id": harmony.staff_id,
    }


def _playback_to_dict(playback: PlaybackData) -> dict[str, object]:
    return {
        "instrument_sound": playback.instrument_sound,
        "midi_channel": playback.midi_channel,
        "midi_program": playback.midi_program,
        "tempo_quarter_bpm": (
            _fraction_to_dict(playback.tempo_quarter_bpm)
            if playback.tempo_quarter_bpm is not None
            else None
        ),
    }


def _fraction_to_dict(value: Fraction) -> dict[str, int]:
    return {"denominator": value.denominator, "numerator": value.numerator}


def _metadata_from_dict(data: object, path: str) -> ScoreMetadata:
    mapping = _mapping(data, path)
    _expect_keys(mapping, {"creators", "title"}, path)
    creators = []
    for index, item in enumerate(_sequence(mapping["creators"], f"{path}.creators")):
        creator_path = f"{path}.creators[{index}]"
        creator = _mapping(item, creator_path)
        _expect_keys(creator, {"name", "role"}, creator_path)
        creators.append(
            Creator(
                role=_string(creator["role"], f"{creator_path}.role"),
                name=_string(creator["name"], f"{creator_path}.name"),
            )
        )
    return ScoreMetadata(
        title=_optional_string(mapping["title"], f"{path}.title"),
        creators=tuple(creators),
    )


def _part_from_dict(data: object, path: str) -> Part:
    mapping = _mapping(data, path)
    _expect_keys(
        mapping,
        {"display_name", "id", "measures", "source_id", "staves", "voices"},
        path,
    )
    staves = []
    for index, item in enumerate(_sequence(mapping["staves"], f"{path}.staves")):
        item_path = f"{path}.staves[{index}]"
        staff = _mapping(item, item_path)
        _expect_keys(staff, {"id", "source_number"}, item_path)
        source_number = staff["source_number"]
        staves.append(
            Staff(
                id=_string(staff["id"], f"{item_path}.id"),
                source_number=(
                    None
                    if source_number is None
                    else _integer(source_number, f"{item_path}.source_number")
                ),
            )
        )
    voices = []
    for index, item in enumerate(_sequence(mapping["voices"], f"{path}.voices")):
        item_path = f"{path}.voices[{index}]"
        voice = _mapping(item, item_path)
        _expect_keys(voice, {"id", "source_id"}, item_path)
        voices.append(
            Voice(
                id=_string(voice["id"], f"{item_path}.id"),
                source_id=_optional_string(voice["source_id"], f"{item_path}.source_id"),
            )
        )
    return Part(
        id=_string(mapping["id"], f"{path}.id"),
        source_id=_optional_string(mapping["source_id"], f"{path}.source_id"),
        display_name=_optional_string(mapping["display_name"], f"{path}.display_name"),
        staves=tuple(staves),
        voices=tuple(voices),
        measures=tuple(
            _measure_from_dict(item, f"{path}.measures[{index}]")
            for index, item in enumerate(_sequence(mapping["measures"], f"{path}.measures"))
        ),
    )


def _measure_from_dict(data: object, path: str) -> Measure:
    mapping = _mapping(data, path)
    _expect_keys(
        mapping,
        {
            "attribute_changes",
            "barlines",
            "events",
            "extent",
            "harmonies",
            "id",
            "ordinal",
            "source_label",
        },
        path,
    )
    return Measure(
        id=_string(mapping["id"], f"{path}.id"),
        source_label=_optional_string(mapping["source_label"], f"{path}.source_label"),
        ordinal=_integer(mapping["ordinal"], f"{path}.ordinal"),
        extent=_fraction_from_dict(mapping["extent"], f"{path}.extent"),
        attribute_changes=tuple(
            _attribute_from_dict(item, f"{path}.attribute_changes[{index}]")
            for index, item in enumerate(
                _sequence(mapping["attribute_changes"], f"{path}.attribute_changes")
            )
        ),
        events=tuple(
            _event_from_dict(item, f"{path}.events[{index}]")
            for index, item in enumerate(_sequence(mapping["events"], f"{path}.events"))
        ),
        harmonies=tuple(
            _harmony_from_dict(item, f"{path}.harmonies[{index}]")
            for index, item in enumerate(_sequence(mapping["harmonies"], f"{path}.harmonies"))
        ),
        barlines=tuple(
            _barline_from_dict(item, f"{path}.barlines[{index}]")
            for index, item in enumerate(_sequence(mapping["barlines"], f"{path}.barlines"))
        ),
    )


def _attribute_from_dict(data: object, path: str) -> AttributeChange:
    mapping = _mapping(data, path)
    _expect_keys(mapping, {"clefs", "key_signature", "onset", "time_signature"}, path)
    clefs = []
    for index, item in enumerate(_sequence(mapping["clefs"], f"{path}.clefs")):
        item_path = f"{path}.clefs[{index}]"
        clef = _mapping(item, item_path)
        _expect_keys(clef, {"line", "octave_change", "sign", "staff_id"}, item_path)
        clefs.append(
            Clef(
                staff_id=_string(clef["staff_id"], f"{item_path}.staff_id"),
                sign=_enum(ClefSign, clef["sign"], f"{item_path}.sign"),
                line=_integer(clef["line"], f"{item_path}.line"),
                octave_change=_integer(clef["octave_change"], f"{item_path}.octave_change"),
            )
        )
    key_data = mapping["key_signature"]
    key_signature = None
    if key_data is not None:
        key = _mapping(key_data, f"{path}.key_signature")
        _expect_keys(key, {"fifths", "mode"}, f"{path}.key_signature")
        key_signature = KeySignature(
            fifths=_integer(key["fifths"], f"{path}.key_signature.fifths"),
            mode=_optional_string(key["mode"], f"{path}.key_signature.mode"),
        )
    time_data = mapping["time_signature"]
    time_signature = None
    if time_data is not None:
        meter = _mapping(time_data, f"{path}.time_signature")
        _expect_keys(meter, {"beat_groups", "beat_type"}, f"{path}.time_signature")
        time_signature = TimeSignature(
            beat_groups=tuple(
                _integer(group, f"{path}.time_signature.beat_groups[{index}]")
                for index, group in enumerate(
                    _sequence(meter["beat_groups"], f"{path}.time_signature.beat_groups")
                )
            ),
            beat_type=_integer(meter["beat_type"], f"{path}.time_signature.beat_type"),
        )
    return AttributeChange(
        onset=_fraction_from_dict(mapping["onset"], f"{path}.onset"),
        clefs=tuple(clefs),
        key_signature=key_signature,
        time_signature=time_signature,
    )


def _event_from_dict(data: object, path: str) -> ScoreEvent:
    mapping = _mapping(data, path)
    kind = _string(mapping.get("kind"), f"{path}.kind")
    common_keys = {
        "duration",
        "id",
        "kind",
        "onset",
        "rhythm",
        "source_order",
        "staff_id",
        "voice_id",
    }
    event_id = _string(mapping.get("id"), f"{path}.id")
    staff_id = _string(mapping.get("staff_id"), f"{path}.staff_id")
    voice_id = _string(mapping.get("voice_id"), f"{path}.voice_id")
    onset = _fraction_from_dict(mapping.get("onset"), f"{path}.onset")
    duration = _fraction_from_dict(mapping.get("duration"), f"{path}.duration")
    source_order = _integer(mapping.get("source_order"), f"{path}.source_order")
    rhythm = _rhythm_from_dict(mapping.get("rhythm"), f"{path}.rhythm")
    if kind == "rest":
        _expect_keys(mapping, common_keys, path)
        return RestEvent(
            id=event_id,
            staff_id=staff_id,
            voice_id=voice_id,
            onset=onset,
            duration=duration,
            source_order=source_order,
            rhythm=rhythm,
        )
    if kind != "note":
        raise ScoreSerializationError(f"{path}.kind: unsupported event kind {kind!r}")
    _expect_keys(
        mapping,
        common_keys | {"chord_id", "lyrics", "pitch", "stem_direction"},
        path,
    )
    pitch_data = _mapping(mapping["pitch"], f"{path}.pitch")
    _expect_keys(pitch_data, {"alter", "octave", "step"}, f"{path}.pitch")
    lyrics = []
    for index, item in enumerate(_sequence(mapping["lyrics"], f"{path}.lyrics")):
        item_path = f"{path}.lyrics[{index}]"
        lyric = _mapping(item, item_path)
        _expect_keys(lyric, {"line", "syllabic", "text"}, item_path)
        lyrics.append(
            Lyric(
                line=_string(lyric["line"], f"{item_path}.line"),
                text=_string(lyric["text"], f"{item_path}.text"),
                syllabic=_enum(Syllabic, lyric["syllabic"], f"{item_path}.syllabic"),
            )
        )
    stem_data = mapping["stem_direction"]
    return NoteEvent(
        id=event_id,
        staff_id=staff_id,
        voice_id=voice_id,
        onset=onset,
        duration=duration,
        source_order=source_order,
        rhythm=rhythm,
        chord_id=_optional_string(mapping["chord_id"], f"{path}.chord_id"),
        pitch=WrittenPitch(
            step=_enum(PitchStep, pitch_data["step"], f"{path}.pitch.step"),
            alter=_fraction_from_dict(pitch_data["alter"], f"{path}.pitch.alter"),
            octave=_integer(pitch_data["octave"], f"{path}.pitch.octave"),
        ),
        lyrics=tuple(lyrics),
        stem_direction=(
            None if stem_data is None else _enum(StemDirection, stem_data, f"{path}.stem_direction")
        ),
    )


def _harmony_from_dict(data: object, path: str) -> HarmonySymbol:
    mapping = _mapping(data, path)
    _expect_keys(
        mapping,
        {"display_text", "id", "kind", "onset", "root", "source_order", "staff_id"},
        path,
    )
    root = _mapping(mapping["root"], f"{path}.root")
    _expect_keys(root, {"alter", "step"}, f"{path}.root")
    return HarmonySymbol(
        id=_string(mapping["id"], f"{path}.id"),
        staff_id=_string(mapping["staff_id"], f"{path}.staff_id"),
        onset=_fraction_from_dict(mapping["onset"], f"{path}.onset"),
        source_order=_integer(mapping["source_order"], f"{path}.source_order"),
        root=WrittenPitchClass(
            step=_enum(PitchStep, root["step"], f"{path}.root.step"),
            alter=_fraction_from_dict(root["alter"], f"{path}.root.alter"),
        ),
        kind=_string(mapping["kind"], f"{path}.kind"),
        display_text=_optional_string(mapping["display_text"], f"{path}.display_text"),
    )


def _rhythm_from_dict(data: object, path: str) -> WrittenRhythm:
    mapping = _mapping(data, path)
    _expect_keys(mapping, {"dots", "value"}, path)
    return WrittenRhythm(
        value=_enum(RhythmicValue, mapping["value"], f"{path}.value"),
        dots=_integer(mapping["dots"], f"{path}.dots"),
    )


def _barline_from_dict(data: object, path: str) -> Barline:
    mapping = _mapping(data, path)
    _expect_keys(mapping, {"location", "style", "terminates_score"}, path)
    return Barline(
        location=_enum(BarlineLocation, mapping["location"], f"{path}.location"),
        style=_enum(BarlineStyle, mapping["style"], f"{path}.style"),
        terminates_score=_boolean(mapping["terminates_score"], f"{path}.terminates_score"),
    )


def _presentation_from_dict(data: object, path: str) -> PresentationData:
    mapping = _mapping(data, path)
    _expect_keys(mapping, {"breaks"}, path)
    breaks = []
    for index, item in enumerate(_sequence(mapping["breaks"], f"{path}.breaks")):
        item_path = f"{path}.breaks[{index}]"
        item_data = _mapping(item, item_path)
        _expect_keys(item_data, {"before_measure_id", "kind"}, item_path)
        breaks.append(
            PresentationBreak(
                kind=_enum(BreakKind, item_data["kind"], f"{item_path}.kind"),
                before_measure_id=_string(
                    item_data["before_measure_id"], f"{item_path}.before_measure_id"
                ),
            )
        )
    return PresentationData(breaks=tuple(breaks))


def _playback_from_dict(data: object, path: str) -> PlaybackData:
    mapping = _mapping(data, path)
    _expect_keys(
        mapping,
        {"instrument_sound", "midi_channel", "midi_program", "tempo_quarter_bpm"},
        path,
    )
    tempo = mapping["tempo_quarter_bpm"]
    channel = mapping["midi_channel"]
    program = mapping["midi_program"]
    return PlaybackData(
        tempo_quarter_bpm=(None if tempo is None else _fraction_from_dict(tempo, f"{path}.tempo")),
        instrument_sound=_optional_string(mapping["instrument_sound"], f"{path}.instrument_sound"),
        midi_channel=None if channel is None else _integer(channel, f"{path}.midi_channel"),
        midi_program=None if program is None else _integer(program, f"{path}.midi_program"),
    )


def _source_from_dict(data: object, path: str) -> SourceReference:
    mapping = _mapping(data, path)
    _expect_keys(mapping, {"logical_name", "sha256", "source_format"}, path)
    return SourceReference(
        source_format=_enum(SourceFormat, mapping["source_format"], f"{path}.source_format"),
        logical_name=_string(mapping["logical_name"], f"{path}.logical_name"),
        sha256=_optional_string(mapping["sha256"], f"{path}.sha256"),
    )


def _fraction_from_dict(data: object, path: str) -> Fraction:
    mapping = _mapping(data, path)
    _expect_keys(mapping, {"denominator", "numerator"}, path)
    numerator = _integer(mapping["numerator"], f"{path}.numerator")
    denominator = _integer(mapping["denominator"], f"{path}.denominator")
    if denominator <= 0:
        raise ScoreSerializationError(f"{path}.denominator: must be positive")
    return Fraction(numerator, denominator)


def _mapping(data: object, path: str) -> dict[str, object]:
    if not isinstance(data, dict) or not all(isinstance(key, str) for key in data):
        raise ScoreSerializationError(f"{path}: expected an object")
    return cast(dict[str, object], data)


def _sequence(data: object, path: str) -> list[object]:
    if not isinstance(data, list):
        raise ScoreSerializationError(f"{path}: expected an array")
    return cast(list[object], data)


def _expect_keys(data: dict[str, object], expected: set[str], path: str) -> None:
    actual = set(data)
    missing = sorted(expected - actual)
    unexpected = sorted(actual - expected)
    if missing or unexpected:
        details = []
        if missing:
            details.append(f"missing {missing}")
        if unexpected:
            details.append(f"unexpected {unexpected}")
        raise ScoreSerializationError(f"{path}: {'; '.join(details)}")


def _string(data: object, path: str) -> str:
    if not isinstance(data, str):
        raise ScoreSerializationError(f"{path}: expected text")
    return data


def _optional_string(data: object, path: str) -> str | None:
    if data is None:
        return None
    return _string(data, path)


def _integer(data: object, path: str) -> int:
    if not isinstance(data, int) or isinstance(data, bool):
        raise ScoreSerializationError(f"{path}: expected an integer")
    return data


def _boolean(data: object, path: str) -> bool:
    if not isinstance(data, bool):
        raise ScoreSerializationError(f"{path}: expected a boolean")
    return data


def _enum[EnumT: StrEnum](enum_type: type[EnumT], data: object, path: str) -> EnumT:
    value = _string(data, path)
    try:
        return enum_type(value)
    except ValueError as error:
        raise ScoreSerializationError(f"{path}: unsupported value {value!r}") from error
