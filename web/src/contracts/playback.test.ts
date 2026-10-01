import type { PlaybackPlan } from "./playback";
import { validatePlaybackPlan } from "./playback";

test("TEST-APP-PLAYBACK-004 rejects unsafe browser playback input", () => {
  const invalid = {
    contract_id: "org.teachmemusic.playback-plan",
    contract_version: "0.2.0",
    duration_microseconds: 1_000,
    notes: [{
      id: "note:bad",
      start_microseconds: 500,
      end_microseconds: 250,
      midi_pitch: 140,
      source_events: [],
      chord_id: null,
      dynamic_percent: null,
    }],
  } as unknown as PlaybackPlan;

  expect(validatePlaybackPlan(invalid).map((issue) => issue.code)).toEqual([
    "AUDIO_NOTE_TIME",
    "AUDIO_MIDI_PITCH",
    "AUDIO_NOTE_SOURCE",
  ]);
});
