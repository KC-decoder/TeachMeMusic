"""Map MusicXML playback declarations into canonical schema-v2 values."""

from __future__ import annotations

from fractions import Fraction
from typing import Protocol

from lxml import etree

from teachmemusic.score.v2.playback import (
    InstrumentChange,
    MidiDevice,
    MidiInstrument,
    PedalPlayback,
    PlaybackTechnique,
    SoundDirective,
    SwingPlayback,
    VirtualInstrument,
)


class PlaybackAudit(Protocol):
    def take(self, element: etree._Element | None) -> etree._Element | None: ...
    def attr(self, element: etree._Element, name: str) -> str | None: ...
    def value(self, element: etree._Element | None) -> str | None: ...
    def child(self, element: etree._Element, name: str) -> etree._Element | None: ...
    def children(self, element: etree._Element, name: str) -> tuple[etree._Element, ...]: ...
    def child_value(self, element: etree._Element, name: str) -> str | None: ...


def _fraction(value: str | None, label: str) -> Fraction | None:
    if value is None:
        return None
    try:
        return Fraction(value)
    except (ValueError, ZeroDivisionError) as error:
        raise ValueError(f"invalid {label}") from error


def _integer(value: str | None, label: str) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except ValueError as error:
        raise ValueError(f"invalid {label}") from error


def _yes_no(value: str | None, label: str) -> bool | None:
    if value is None:
        return None
    if value not in {"yes", "no"}:
        raise ValueError(f"invalid {label}")
    return value == "yes"


def _pedal(value: str | None, label: str) -> PedalPlayback | None:
    if value is None:
        return None
    if value in {"yes", "no"}:
        return PedalPlayback(enabled=value == "yes")
    return PedalPlayback(percent=_fraction(value, label))


def map_midi_device(element: etree._Element, audit: PlaybackAudit) -> MidiDevice:
    audit.take(element)
    return MidiDevice(
        instrument_id=audit.attr(element, "id"),
        port=_integer(audit.attr(element, "port"), "MIDI port"),
        name=audit.value(element) or "",
    )


def map_midi_instrument(element: etree._Element, audit: PlaybackAudit) -> MidiInstrument:
    audit.take(element)
    return MidiInstrument(
        instrument_id=audit.attr(element, "id") or "",
        channel=_integer(audit.child_value(element, "midi-channel"), "MIDI channel"),
        name=audit.child_value(element, "midi-name"),
        bank=_integer(audit.child_value(element, "midi-bank"), "MIDI bank"),
        program=_integer(audit.child_value(element, "midi-program"), "MIDI program"),
        unpitched=_integer(audit.child_value(element, "midi-unpitched"), "MIDI unpitched"),
        volume=_fraction(audit.child_value(element, "volume"), "MIDI volume"),
        pan=_fraction(audit.child_value(element, "pan"), "MIDI pan"),
        elevation=_fraction(audit.child_value(element, "elevation"), "MIDI elevation"),
    )


def map_virtual_instrument(
    element: etree._Element | None, audit: PlaybackAudit
) -> VirtualInstrument | None:
    if element is None:
        return None
    audit.take(element)
    return VirtualInstrument(
        library=audit.child_value(element, "virtual-library"),
        name=audit.child_value(element, "virtual-name"),
    )


def _techniques(element: etree._Element, audit: PlaybackAudit) -> tuple[PlaybackTechnique, ...]:
    audit.take(element)
    instrument_id = audit.attr(element, "id")
    values: list[PlaybackTechnique] = []
    for child in element:
        if not isinstance(child.tag, str):
            continue
        audit.take(child)
        kind = etree.QName(child).localname
        values.append(
            PlaybackTechnique(
                instrument_id=instrument_id,
                kind=kind,
                value=audit.value(child) or "",
                technique_type=audit.attr(child, "type") if kind == "other-play" else None,
            )
        )
    return tuple(values)


def _swing(element: etree._Element | None, audit: PlaybackAudit) -> SwingPlayback | None:
    if element is None:
        return None
    audit.take(element)
    straight = audit.child(element, "straight")
    if straight is not None:
        return SwingPlayback(
            straight=True,
            style=audit.child_value(element, "swing-style"),
        )
    return SwingPlayback(
        straight=False,
        first=_integer(audit.child_value(element, "first"), "swing first"),
        second=_integer(audit.child_value(element, "second"), "swing second"),
        note_type=audit.child_value(element, "swing-type"),
        style=audit.child_value(element, "swing-style"),
    )


def map_sound(
    element: etree._Element,
    audit: PlaybackAudit,
    *,
    onset: Fraction,
    score_onset: Fraction,
    divisions: int | None,
    source_order: int,
) -> SoundDirective:
    """Map one standalone or direction-owned sound at its effective position."""

    audit.take(element)
    offset_text = audit.child_value(element, "offset")
    offset = Fraction(0)
    if offset_text is not None:
        if divisions is None or divisions <= 0:
            raise ValueError("sound offset before divisions")
        offset = (_fraction(offset_text, "sound offset") or Fraction(0)) / divisions
    location = onset + offset
    changes: list[InstrumentChange] = []
    devices: list[MidiDevice] = []
    midi: list[MidiInstrument] = []
    techniques: list[PlaybackTechnique] = []
    for child in element:
        if not isinstance(child.tag, str):
            continue
        kind = etree.QName(child).localname
        if kind == "instrument-change":
            audit.take(child)
            ensemble = audit.child(child, "ensemble")
            ensemble_text = audit.value(ensemble)
            changes.append(
                InstrumentChange(
                    instrument_id=audit.attr(child, "id") or "",
                    sound=audit.child_value(child, "instrument-sound"),
                    solo=audit.child(child, "solo") is not None,
                    ensemble=ensemble is not None,
                    ensemble_size=_integer(ensemble_text, "ensemble size")
                    if ensemble_text
                    else None,
                    virtual=map_virtual_instrument(audit.child(child, "virtual-instrument"), audit),
                )
            )
        elif kind == "midi-device":
            devices.append(map_midi_device(child, audit))
        elif kind == "midi-instrument":
            midi.append(map_midi_instrument(child, audit))
        elif kind == "play":
            techniques.extend(_techniques(child, audit))
    return SoundDirective(
        onset=location,
        score_onset=score_onset + location,
        source_order=source_order,
        tempo=_fraction(audit.attr(element, "tempo"), "sound tempo"),
        dynamics=_fraction(audit.attr(element, "dynamics"), "sound dynamics"),
        dacapo=_yes_no(audit.attr(element, "dacapo"), "sound dacapo"),
        segno=audit.attr(element, "segno"),
        dalsegno=audit.attr(element, "dalsegno"),
        coda=audit.attr(element, "coda"),
        tocoda=audit.attr(element, "tocoda"),
        divisions=_fraction(audit.attr(element, "divisions"), "sound divisions"),
        forward_repeat=_yes_no(audit.attr(element, "forward-repeat"), "sound forward-repeat"),
        fine=audit.attr(element, "fine"),
        time_only=audit.attr(element, "time-only"),
        pizzicato=_yes_no(audit.attr(element, "pizzicato"), "sound pizzicato"),
        pan=_fraction(audit.attr(element, "pan"), "sound pan"),
        elevation=_fraction(audit.attr(element, "elevation"), "sound elevation"),
        damper_pedal=_pedal(audit.attr(element, "damper-pedal"), "damper pedal"),
        soft_pedal=_pedal(audit.attr(element, "soft-pedal"), "soft pedal"),
        sostenuto_pedal=_pedal(audit.attr(element, "sostenuto-pedal"), "sostenuto pedal"),
        instrument_changes=tuple(changes),
        devices=tuple(devices),
        midi=tuple(midi),
        techniques=tuple(techniques),
        swing=_swing(audit.child(element, "swing"), audit),
        source_id=audit.attr(element, "id"),
    )
