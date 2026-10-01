import type { PlaybackPlan } from "../contracts/playback";
import {
  PlaybackTransport,
  type PlaybackAudioEngine,
  type PlaybackRuntime,
  type PlaybackSnapshot,
} from "./PlaybackTransport";

function plan(): PlaybackPlan {
  const source = (eventId: string) => ({
    event_id: eventId,
    part_id: "part:one",
    measure_id: "measure:one",
    staff: "1",
    voice: "1",
    score_onset: { numerator: 0, denominator: 1 },
    clef_group_id: "clef:one",
    clef: { sign: "G", line: 2, octave_change: null },
  });
  return {
    contract_id: "org.teachmemusic.playback-plan",
    contract_version: "0.2.0",
    package_id: "package:one",
    score_id: "score:one",
    canonical_schema_id: "org.teachmemusic.canonical-music-package",
    canonical_schema_version: "2.0.0",
    duration_microseconds: 4_000_000,
    navigation_section_starts: [0],
    notes: [
      {
        id: "note:c4",
        start_microseconds: 0,
        end_microseconds: 1_000_000,
        midi_pitch: 60,
        chord_id: "chord:one",
        dynamic_percent: null,
        source_events: [source("event:c4")],
      },
      {
        id: "note:e4",
        start_microseconds: 0,
        end_microseconds: 2_000_000,
        midi_pitch: 64,
        chord_id: "chord:one",
        dynamic_percent: { numerator: 50, denominator: 1 },
        source_events: [source("event:e4")],
      },
      {
        id: "note:g4",
        start_microseconds: 3_000_000,
        end_microseconds: 4_000_000,
        midi_pitch: 67,
        chord_id: null,
        dynamic_percent: null,
        source_events: [source("event:g4")],
      },
    ],
    tempo_controls: [{
      id: "tempo:one",
      at_microseconds: 0,
      quarter_notes_per_minute: { numerator: 120, denominator: 1 },
      source_score_onset: { numerator: 0, denominator: 1 },
      origin: "canonical",
      source_part_id: "part:one",
      source_measure_id: "measure:one",
      source_order: 0,
    }],
    grace_realizations: [],
    measure_visits: [{
      visit_index: 0,
      source_measure_index: 0,
      source_measure_number: "1",
      source_measure_ids: ["measure:one"],
      source_score_onset: { numerator: 0, denominator: 1 },
      start_microseconds: 0,
      end_microseconds: 4_000_000,
      entry_reason: "initial",
    }],
    diagnostics: [],
  };
}

class FakeEngine implements PlaybackAudioEngine {
  now = 10;
  fail = false;
  scheduled: Array<[number, number, number, number]> = [];
  clicks: Array<[number, boolean]> = [];
  releases = 0;
  disposed = false;

  async activate() {
    if (this.fail) throw new Error("load failed");
  }
  nowSeconds() { return this.now; }
  schedule(pitch: number, at: number, duration: number, velocity: number) {
    this.scheduled.push([pitch, at, duration, velocity]);
  }
  scheduleClick(at: number, accented: boolean) { this.clicks.push([at, accented]); }
  releaseAll() { this.releases += 1; }
  dispose() { this.disposed = true; }
}

class FakeRuntime implements PlaybackRuntime {
  interval: (() => void) | null = null;
  frame: (() => void) | null = null;
  setInterval(callback: () => void) { this.interval = callback; return 1; }
  clearInterval() { this.interval = null; }
  requestFrame(callback: () => void) { this.frame = callback; return 2; }
  cancelFrame() { this.frame = null; }
  runFrame() { const callback = this.frame; this.frame = null; callback?.(); }
}

test("TEST-APP-PLAYBACK-001 schedules bounded chord windows and follows the audio clock", async () => {
  const engine = new FakeEngine();
  const runtime = new FakeRuntime();
  const snapshots: PlaybackSnapshot[] = [];
  const transport = new PlaybackTransport(plan(), engine, (value) => snapshots.push(value), runtime);

  await transport.play();
  expect(engine.scheduled).toHaveLength(2);
  expect(engine.scheduled.map(([pitch]) => pitch)).toEqual([60, 64]);
  expect(engine.scheduled[0]).toEqual([60, 10.05, 1, 0.72]);
  expect(engine.scheduled[1]).toEqual([64, 10.05, 2, 0.5]);

  engine.now = 10.55;
  runtime.runFrame();
  expect(snapshots.at(-1)).toMatchObject({
    status: "playing",
    positionMicroseconds: 500_000,
    activeMidiPitches: [60, 64],
    activeNotes: [
      { noteId: "note:c4", midiPitch: 60, contributions: [{ eventId: "event:c4" }] },
      { noteId: "note:e4", midiPitch: 64, contributions: [{ eventId: "event:e4" }] },
    ],
    focusEventIds: ["event:c4", "event:e4"],
  });
  expect(engine.scheduled.map(([pitch]) => pitch)).not.toContain(67);

  engine.now = 11.1;
  runtime.interval?.();
  expect(engine.scheduled.map(([pitch]) => pitch)).toContain(67);
  transport.dispose();
  expect(engine.disposed).toBe(true);
});

test("TEST-APP-PLAYBACK-002 pause, seek, resume, stop, and completion release notes", async () => {
  const engine = new FakeEngine();
  const runtime = new FakeRuntime();
  const snapshots: PlaybackSnapshot[] = [];
  const transport = new PlaybackTransport(plan(), engine, (value) => snapshots.push(value), runtime);

  await transport.play();
  engine.now = 10.55;
  transport.pause();
  expect(snapshots.at(-1)).toMatchObject({
    status: "paused",
    positionMicroseconds: 500_000,
    activeNotes: [],
  });

  transport.seek(3_500_000);
  expect(snapshots.at(-1)).toMatchObject({ status: "paused", focusEventIds: ["event:g4"] });
  await transport.play();
  expect(engine.scheduled.at(-1)).toEqual([67, 10.600000000000001, 0.5, 0.72]);

  engine.now = 11.11;
  runtime.runFrame();
  expect(snapshots.at(-1)).toMatchObject({ status: "complete", positionMicroseconds: 4_000_000 });
  transport.stop();
  expect(snapshots.at(-1)).toMatchObject({ status: "idle", positionMicroseconds: 0 });
  expect(engine.releases).toBeGreaterThanOrEqual(4);
});

test("TEST-APP-PLAYBACK-003 reports local sample activation failure without scheduling", async () => {
  const engine = new FakeEngine();
  engine.fail = true;
  const snapshots: PlaybackSnapshot[] = [];
  const transport = new PlaybackTransport(
    plan(),
    engine,
    (value) => snapshots.push(value),
    new FakeRuntime(),
  );

  await transport.play();
  expect(engine.scheduled).toHaveLength(0);
  expect(snapshots.at(-1)).toMatchObject({
    status: "error",
    errorCode: "AUDIO_SAMPLE_LOAD_FAILED",
  });
});

test("TEST-APP-PLAYBACK-008 schedules an audible count-in before expected notes", async () => {
  const engine = new FakeEngine();
  const runtime = new FakeRuntime();
  const snapshots: PlaybackSnapshot[] = [];
  const transport = new PlaybackTransport(
    plan(),
    engine,
    (value) => snapshots.push(value),
    runtime,
    { beats: 4, beatMicroseconds: 500_000 },
  );

  await transport.play();
  expect(engine.clicks).toEqual([
    [10.05, true],
    [10.55, false],
    [11.05, false],
    [11.55, false],
  ]);
  expect(engine.scheduled[0]?.[1]).toBe(12.05);
  expect(snapshots.at(-1)?.countInBeatsRemaining).toBe(4);
});
