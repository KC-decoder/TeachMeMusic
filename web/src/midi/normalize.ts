import type { NormalizedMidiEvent, RawMidiMessage } from "./contracts";

function event(
  raw: RawMidiMessage,
  kind: NormalizedMidiEvent["kind"],
  values: Partial<NormalizedMidiEvent>,
): NormalizedMidiEvent {
  return {
    id: `midi-event:${raw.sequence_number}`,
    raw_message_id: raw.id,
    kind,
    timestamp_microseconds: raw.timestamp_microseconds,
    channel: null,
    note: null,
    velocity: null,
    controller: null,
    value: null,
    detail: null,
    ...values,
  };
}

export function normalizeMidiMessage(raw: RawMidiMessage): NormalizedMidiEvent {
  const [status, dataOne, dataTwo] = raw.data;
  if (status === undefined || status < 0x80) {
    return event(raw, "diagnostic", { detail: "MIDI_MALFORMED_STATUS" });
  }
  const family = status & 0xf0;
  const channel = (status & 0x0f) + 1;
  if ((family === 0x80 || family === 0x90 || family === 0xb0) &&
      (dataOne === undefined || dataTwo === undefined)) {
    return event(raw, "diagnostic", {
      channel,
      detail: "MIDI_TRUNCATED_CHANNEL_MESSAGE",
    });
  }
  if ((dataOne !== undefined && dataOne > 0x7f) ||
      (dataTwo !== undefined && dataTwo > 0x7f)) {
    return event(raw, "diagnostic", {
      channel: status < 0xf0 ? channel : null,
      detail: "MIDI_INVALID_DATA_BYTE",
    });
  }
  if (family === 0x80) {
    return event(raw, "note-off", {
      channel,
      note: dataOne!,
      velocity: dataTwo!,
      detail: "explicit-note-off",
    });
  }
  if (family === 0x90) {
    const velocity = dataTwo!;
    return event(raw, velocity === 0 ? "note-off" : "note-on", {
      channel,
      note: dataOne!,
      velocity,
      detail: velocity === 0 ? "velocity-zero-note-on" : null,
    });
  }
  if (family === 0xb0) {
    const controller = dataOne!;
    const value = dataTwo!;
    return event(raw, "control-change", {
      channel,
      controller,
      value,
      detail: controller === 64 ? (value >= 64 ? "sustain-down" : "sustain-up") : null,
    });
  }
  return event(raw, "diagnostic", {
    channel: status < 0xf0 ? channel : null,
    detail: `MIDI_UNSUPPORTED_STATUS_0x${status.toString(16).padStart(2, "0")}`,
  });
}
