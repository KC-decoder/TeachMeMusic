"""Strict JSON-compatible encoding of the closed temporal dataclass graph."""

from __future__ import annotations

import math
from dataclasses import fields, is_dataclass
from fractions import Fraction
from types import UnionType
from typing import Any, Union, cast, get_args, get_origin, get_type_hints

from .annotations import (
    AccordionRegistration,
    AnnotationGraph,
    BassFigure,
    BendSound,
    ComplexDirectionData,
    DirectionImage,
    DirectionMark,
    DirectionPitch,
    EventAnchor,
    EventMark,
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
    LyricSyllable,
    LyricTextSegment,
    MetronomeBeam,
    MetronomeBeat,
    MetronomeMark,
    MetronomeNote,
    MetronomeTuplet,
    NotationSpan,
    NoteheadMark,
    NoteheadMarker,
    NoteheadTextSegment,
    OrnamentAccidental,
    PercussionPictogram,
    PrincipalVoice,
    SpanEndpoint,
    SpanMarker,
    TechnicalArrow,
    TechnicalBend,
    TechnicalData,
    TechnicalHarmonic,
    TechnicalHarmonMute,
    TechnicalHole,
    TimeAnchor,
    TimeSpan,
    TimeSpanMarker,
    TrillPlayback,
)
from .layout import (
    AppearanceValue,
    Credit,
    CreditItem,
    LayoutDefaults,
    LayoutMargins,
    LayoutScaling,
    LyricFont,
    LyricLanguage,
    MeasurePrintLayout,
    PageLayout,
    ScoreLayout,
    StaffLayout,
    SystemLayout,
)
from .links import Bookmark, ExternalLink, PartLink, ScopedBookmark, ScopedLink
from .playback import (
    InstrumentChange,
    InstrumentPlayback,
    MidiDevice,
    MidiInstrument,
    PedalPlayback,
    PlaybackTechnique,
    Player,
    SoundDirective,
    SwingPlayback,
    VirtualInstrument,
)
from .presentation import (
    DisplayTextSegment,
    NameDisplay,
    PresentationNumber,
    PresentationStyle,
    SourcePresentation,
)
from .temporal import (
    DeferredConstruct,
    TemporalAccidental,
    TemporalAlignment,
    TemporalAttributes,
    TemporalBarline,
    TemporalBeam,
    TemporalClef,
    TemporalCursorMove,
    TemporalDirective,
    TemporalEditorial,
    TemporalEncoding,
    TemporalEncodingSupport,
    TemporalEvent,
    TemporalFeature,
    TemporalFermata,
    TemporalForPart,
    TemporalGraceTiming,
    TemporalGrouping,
    TemporalInstrument,
    TemporalInterchangeableTime,
    TemporalKey,
    TemporalKeyAccidental,
    TemporalKeyAlteration,
    TemporalKeyOctave,
    TemporalMeasure,
    TemporalMeasureStyle,
    TemporalMiscellaneousField,
    TemporalNavigationMark,
    TemporalPart,
    TemporalPartClef,
    TemporalPartGroup,
    TemporalPartSymbol,
    TemporalPitch,
    TemporalScore,
    TemporalScoreMetadata,
    TemporalSoundingPitch,
    TemporalStaff,
    TemporalStaffDetails,
    TemporalStaffLineDetail,
    TemporalStaffTuning,
    TemporalTime,
    TemporalTransposition,
    TemporalTuplet,
    TemporalTupletPortion,
    TemporalTypedText,
    TemporalVoice,
)

_TYPES = frozenset(
    {
        AccordionRegistration,
        AnnotationGraph,
        ComplexDirectionData,
        DirectionMark,
        DirectionImage,
        DirectionPitch,
        EventAnchor,
        EventMark,
        EventMarkMarker,
        BassFigure,
        BendSound,
        FiguredBassAnnotation,
        HarmonyBass,
        HarmonyChord,
        HarmonyDegree,
        HarmonyFrame,
        HarmonyFrameNote,
        HarmonyNumeral,
        HarmonySymbol,
        LyricMarker,
        LyricSyllable,
        LyricTextSegment,
        MetronomeBeam,
        MetronomeBeat,
        MetronomeMark,
        MetronomeNote,
        MetronomeTuplet,
        NotationSpan,
        NoteheadMark,
        NoteheadMarker,
        NoteheadTextSegment,
        OrnamentAccidental,
        PercussionPictogram,
        PrincipalVoice,
        SpanEndpoint,
        SpanMarker,
        TechnicalArrow,
        TechnicalBend,
        TechnicalData,
        TechnicalHarmonic,
        TechnicalHarmonMute,
        TechnicalHole,
        TimeAnchor,
        TimeSpan,
        TimeSpanMarker,
        TrillPlayback,
        PresentationNumber,
        PresentationStyle,
        SourcePresentation,
        DisplayTextSegment,
        NameDisplay,
        InstrumentChange,
        InstrumentPlayback,
        MidiDevice,
        MidiInstrument,
        PedalPlayback,
        PlaybackTechnique,
        Player,
        SoundDirective,
        SwingPlayback,
        VirtualInstrument,
        AppearanceValue,
        Credit,
        CreditItem,
        LayoutDefaults,
        LayoutMargins,
        LayoutScaling,
        LyricFont,
        LyricLanguage,
        MeasurePrintLayout,
        PageLayout,
        ScoreLayout,
        StaffLayout,
        SystemLayout,
        Bookmark,
        ExternalLink,
        PartLink,
        ScopedBookmark,
        ScopedLink,
        DeferredConstruct,
        TemporalAlignment,
        TemporalAccidental,
        TemporalAttributes,
        TemporalBarline,
        TemporalBeam,
        TemporalClef,
        TemporalCursorMove,
        TemporalDirective,
        TemporalEditorial,
        TemporalEncoding,
        TemporalEncodingSupport,
        TemporalEvent,
        TemporalFeature,
        TemporalFermata,
        TemporalForPart,
        TemporalGraceTiming,
        TemporalGrouping,
        TemporalInstrument,
        TemporalInterchangeableTime,
        TemporalKey,
        TemporalKeyAccidental,
        TemporalKeyAlteration,
        TemporalKeyOctave,
        TemporalMeasure,
        TemporalMeasureStyle,
        TemporalMiscellaneousField,
        TemporalNavigationMark,
        TemporalPart,
        TemporalPartClef,
        TemporalPartGroup,
        TemporalPartSymbol,
        TemporalPitch,
        TemporalScore,
        TemporalScoreMetadata,
        TemporalSoundingPitch,
        TemporalStaff,
        TemporalStaffDetails,
        TemporalStaffLineDetail,
        TemporalStaffTuning,
        TemporalTime,
        TemporalTransposition,
        TemporalTuplet,
        TemporalTupletPortion,
        TemporalTypedText,
        TemporalVoice,
    }
)


class TemporalCodecError(ValueError):
    """Malformed or unknown temporal JSON field or value."""


def temporal_to_dict(value: TemporalScore) -> dict[str, object]:
    """Encode a validated temporal score into exact JSON-compatible values."""

    result = _encode(TemporalScore, value, "temporal")
    if not isinstance(result, dict):
        raise TemporalCodecError("temporal: expected score object")
    return result


def temporal_from_dict(data: object) -> TemporalScore:
    """Decode only the declared temporal type graph, rejecting extra fields."""

    result = _decode(TemporalScore, data, "temporal")
    if not isinstance(result, TemporalScore):
        raise TemporalCodecError("temporal: expected score object")
    return result


def deferred_to_dict(value: DeferredConstruct) -> dict[str, object]:
    result = _encode(DeferredConstruct, value, "deferred")
    if not isinstance(result, dict):
        raise TemporalCodecError("deferred: expected object")
    return result


def deferred_from_dict(data: object) -> DeferredConstruct:
    result = _decode(DeferredConstruct, data, "deferred")
    if not isinstance(result, DeferredConstruct):
        raise TemporalCodecError("deferred: expected object")
    return result


def _optional_type(expected: Any) -> Any | None:
    if get_origin(expected) in {UnionType, Union}:
        arguments = get_args(expected)
        if len(arguments) == 2 and type(None) in arguments:
            return next(item for item in arguments if item is not type(None))
    return None


def _encode(expected: Any, value: object, path: str) -> object:
    optional = _optional_type(expected)
    if optional is not None:
        return None if value is None else _encode(optional, value, path)
    if expected is Fraction:
        if not isinstance(value, Fraction):
            raise TemporalCodecError(f"{path}: expected Fraction")
        return {"numerator": value.numerator, "denominator": value.denominator}
    if expected is str:
        if not isinstance(value, str):
            raise TemporalCodecError(f"{path}: expected string")
        return value
    if expected is int:
        if not isinstance(value, int) or isinstance(value, bool):
            raise TemporalCodecError(f"{path}: expected integer")
        return value
    if expected is bool:
        if not isinstance(value, bool):
            raise TemporalCodecError(f"{path}: expected boolean")
        return value
    if get_origin(expected) is tuple:
        if not isinstance(value, tuple):
            raise TemporalCodecError(f"{path}: expected tuple")
        arguments = get_args(expected)
        if len(arguments) == 2 and arguments[1] is Ellipsis:
            return [
                _encode(arguments[0], item, f"{path}[{index}]") for index, item in enumerate(value)
            ]
        if len(arguments) != len(value):
            raise TemporalCodecError(f"{path}: tuple length mismatch")
        return [
            _encode(kind, item, f"{path}[{index}]")
            for index, (kind, item) in enumerate(zip(arguments, value, strict=True))
        ]
    if expected in _TYPES:
        if type(value) is not expected or not is_dataclass(value):
            raise TemporalCodecError(f"{path}: expected {expected.__name__}")
        annotations = get_type_hints(expected)
        return {
            field.name: _encode(
                annotations[field.name], getattr(value, field.name), f"{path}.{field.name}"
            )
            for field in fields(cast(Any, expected))
        }
    raise TemporalCodecError(f"{path}: unsupported temporal type {expected!r}")


def _decode(expected: Any, data: object, path: str) -> Any:
    optional = _optional_type(expected)
    if optional is not None:
        return None if data is None else _decode(optional, data, path)
    if expected is Fraction:
        root = _mapping(data, path)
        _keys(root, {"numerator", "denominator"}, path)
        numerator = _integer(root["numerator"], f"{path}.numerator")
        denominator = _integer(root["denominator"], f"{path}.denominator")
        if denominator <= 0 or math.gcd(numerator, denominator) != 1:
            raise TemporalCodecError(f"{path}: rational must be reduced and positive-denominator")
        return Fraction(numerator, denominator)
    if expected is str:
        if not isinstance(data, str):
            raise TemporalCodecError(f"{path}: expected string")
        return data
    if expected is int:
        return _integer(data, path)
    if expected is bool:
        if not isinstance(data, bool):
            raise TemporalCodecError(f"{path}: expected boolean")
        return data
    if get_origin(expected) is tuple:
        if not isinstance(data, list):
            raise TemporalCodecError(f"{path}: expected array")
        arguments = get_args(expected)
        if len(arguments) == 2 and arguments[1] is Ellipsis:
            return tuple(
                _decode(arguments[0], item, f"{path}[{index}]") for index, item in enumerate(data)
            )
        if len(arguments) != len(data):
            raise TemporalCodecError(f"{path}: tuple length mismatch")
        return tuple(
            _decode(kind, item, f"{path}[{index}]")
            for index, (kind, item) in enumerate(zip(arguments, data, strict=True))
        )
    if expected in _TYPES:
        root = _mapping(data, path)
        declared = {field.name for field in fields(cast(Any, expected))}
        _keys(root, declared, path)
        annotations = get_type_hints(expected)
        values = {
            field.name: _decode(annotations[field.name], root[field.name], f"{path}.{field.name}")
            for field in fields(cast(Any, expected))
        }
        return expected(**values)
    raise TemporalCodecError(f"{path}: unsupported temporal type {expected!r}")


def _mapping(data: object, path: str) -> dict[str, object]:
    if not isinstance(data, dict) or not all(isinstance(key, str) for key in data):
        raise TemporalCodecError(f"{path}: expected object")
    return data


def _keys(data: dict[str, object], expected: set[str], path: str) -> None:
    missing = sorted(expected - data.keys())
    extra = sorted(data.keys() - expected)
    if missing or extra:
        raise TemporalCodecError(f"{path}: missing {missing}; unexpected {extra}")


def _integer(data: object, path: str) -> int:
    if not isinstance(data, int) or isinstance(data, bool):
        raise TemporalCodecError(f"{path}: expected integer")
    return data
