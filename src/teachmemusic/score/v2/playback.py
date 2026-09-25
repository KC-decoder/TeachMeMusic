"""Canonical playback and performer-interaction values for MusicXML ingestion."""

from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction


@dataclass(frozen=True, slots=True)
class MidiDevice:
    instrument_id: str | None
    port: int | None
    name: str


@dataclass(frozen=True, slots=True)
class MidiInstrument:
    instrument_id: str
    channel: int | None
    name: str | None
    bank: int | None
    program: int | None
    unpitched: int | None
    volume: Fraction | None
    pan: Fraction | None
    elevation: Fraction | None


@dataclass(frozen=True, slots=True)
class VirtualInstrument:
    library: str | None
    name: str | None


@dataclass(frozen=True, slots=True)
class InstrumentPlayback:
    devices: tuple[MidiDevice, ...] = ()
    midi: tuple[MidiInstrument, ...] = ()
    virtual: VirtualInstrument | None = None


@dataclass(frozen=True, slots=True)
class Player:
    id: str
    name: str


@dataclass(frozen=True, slots=True)
class PedalPlayback:
    """One explicit pedal state; a percentage preserves half-pedalling exactly."""

    enabled: bool | None = None
    percent: Fraction | None = None


@dataclass(frozen=True, slots=True)
class PlaybackTechnique:
    instrument_id: str | None
    kind: str
    value: str
    technique_type: str | None = None


@dataclass(frozen=True, slots=True)
class SwingPlayback:
    straight: bool
    first: int | None = None
    second: int | None = None
    note_type: str | None = None
    style: str | None = None


@dataclass(frozen=True, slots=True)
class InstrumentChange:
    instrument_id: str
    sound: str | None
    solo: bool
    ensemble: bool
    ensemble_size: int | None
    virtual: VirtualInstrument | None


@dataclass(frozen=True, slots=True)
class SoundDirective:
    """A score-positioned MusicXML ``sound`` state change."""

    onset: Fraction
    score_onset: Fraction
    source_order: int
    tempo: Fraction | None = None
    dynamics: Fraction | None = None
    dacapo: bool | None = None
    segno: str | None = None
    dalsegno: str | None = None
    coda: str | None = None
    tocoda: str | None = None
    divisions: Fraction | None = None
    forward_repeat: bool | None = None
    fine: str | None = None
    time_only: str | None = None
    pizzicato: bool | None = None
    pan: Fraction | None = None
    elevation: Fraction | None = None
    damper_pedal: PedalPlayback | None = None
    soft_pedal: PedalPlayback | None = None
    sostenuto_pedal: PedalPlayback | None = None
    instrument_changes: tuple[InstrumentChange, ...] = ()
    devices: tuple[MidiDevice, ...] = ()
    midi: tuple[MidiInstrument, ...] = ()
    techniques: tuple[PlaybackTechnique, ...] = ()
    swing: SwingPlayback | None = None
    source_id: str | None = None
