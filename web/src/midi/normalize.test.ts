import type { RawMidiMessage } from "./contracts";
import { normalizeMidiMessage } from "./normalize";

function raw(data: number[]): RawMidiMessage {
  return {
    id: "raw-midi:1",
    sequence_number: 1,
    timestamp_microseconds: 12_345,
    data,
  };
}

test("TEST-MIDI-001 normalizes note-on and explicit note-off with one-based channels", () => {
  expect(normalizeMidiMessage(raw([0x92, 60, 87]))).toMatchObject({
    kind: "note-on",
    channel: 3,
    note: 60,
    velocity: 87,
  });
  expect(normalizeMidiMessage(raw([0x82, 60, 31]))).toMatchObject({
    kind: "note-off",
    channel: 3,
    note: 60,
    velocity: 31,
    detail: "explicit-note-off",
  });
});

test("TEST-MIDI-002 preserves velocity-zero and sustain interpretations explicitly", () => {
  expect(normalizeMidiMessage(raw([0x90, 64, 0]))).toMatchObject({
    kind: "note-off",
    note: 64,
    velocity: 0,
    detail: "velocity-zero-note-on",
  });
  expect(normalizeMidiMessage(raw([0xb0, 64, 127]))).toMatchObject({
    kind: "control-change",
    controller: 64,
    value: 127,
    detail: "sustain-down",
  });
  expect(normalizeMidiMessage(raw([0xb0, 64, 0]))).toMatchObject({ detail: "sustain-up" });
});

test("TEST-MIDI-003 retains unsupported and malformed messages as diagnostics", () => {
  expect(normalizeMidiMessage(raw([0xe0, 0, 64]))).toMatchObject({
    kind: "diagnostic",
    detail: "MIDI_UNSUPPORTED_STATUS_0xe0",
  });
  expect(normalizeMidiMessage(raw([0x90, 60]))).toMatchObject({
    kind: "diagnostic",
    detail: "MIDI_TRUNCATED_CHANNEL_MESSAGE",
  });
  expect(normalizeMidiMessage(raw([60, 90, 10]))).toMatchObject({
    kind: "diagnostic",
    detail: "MIDI_MALFORMED_STATUS",
  });
  expect(normalizeMidiMessage(raw([0x90, 200, 10]))).toMatchObject({
    kind: "diagnostic",
    detail: "MIDI_INVALID_DATA_BYTE",
  });
});
