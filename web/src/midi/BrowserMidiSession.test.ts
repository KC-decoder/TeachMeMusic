import { BrowserMidiSession, type MidiClock } from "./BrowserMidiSession";
import type {
  MidiAccessLike,
  MidiInputLike,
  MidiMessageEventLike,
  MidiSnapshot,
} from "./contracts";

class FakeInput implements MidiInputLike {
  id = "casio-px-770";
  name = "CASIO USB-MIDI";
  manufacturer = "CASIO";
  state = "connected" as const;
  connection: "open" | "closed" | "pending" = "closed";
  type = "input" as const;
  onmidimessage: ((event: MidiMessageEventLike) => void) | null = null;

  async open(): Promise<MidiInputLike> {
    this.connection = "open";
    return this;
  }

  async close(): Promise<MidiInputLike> {
    this.connection = "closed";
    return this;
  }

  emit(data: number[], timeStamp: number) {
    this.onmidimessage?.({ data: new Uint8Array(data), timeStamp });
  }
}

function fixture() {
  const input = new FakeInput();
  const access: MidiAccessLike = {
    inputs: new Map([[input.id, input]]),
    onstatechange: null,
  };
  let now = 100;
  const clock: MidiClock = {
    nowMilliseconds: () => now,
    timeOriginMilliseconds: () => 1_700_000_000_000,
    nowUtc: () => "2026-10-01T20:00:00.000Z",
  };
  const session = new BrowserMidiSession(async () => access, clock);
  return {
    access,
    input,
    session,
    setNow(value: number) { now = value; },
  };
}

test("TEST-MIDI-004 fake Casio capture retains raw evidence and builds bounded calibration", async () => {
  const { input, session, setNow } = fixture();
  let latest: MidiSnapshot = session.current();
  session.subscribe((snapshot) => { latest = snapshot; });
  await session.requestPermission();
  expect(latest.inputs).toEqual([expect.objectContaining({ id: "casio-px-770" })]);
  await session.connect(input.id);
  session.startCalibration();

  const messages = [
    [0x90, 60, 70], [0x80, 60, 20],
    [0x90, 62, 30], [0x90, 64, 80], [0x90, 65, 100], [0x90, 67, 60],
    [0xb0, 64, 127], [0xb0, 64, 0], [0x90, 67, 0],
  ];
  messages.forEach((message, index) => {
    setNow(101 + index);
    input.emit(message, 100.5 + index);
  });
  session.stopCalibration();

  expect(latest.raw_messages).toHaveLength(messages.length);
  expect(latest.normalized_events).toHaveLength(messages.length);
  expect(latest.normalized_events.at(-1)).toMatchObject({
    kind: "note-off",
    detail: "velocity-zero-note-on",
  });
  expect(latest.calibration).toMatchObject({
    device_id: "casio-px-770",
    pitch_numbering_confirmed: true,
    sustain_available: true,
    note_on_count: 5,
    first_note: 60,
    approved: false,
    timing_window_microseconds: null,
  });
  expect(latest.calibration?.limitations).toContain(
    "This browser-only calibration cannot measure physical key-to-sound or acoustic latency.",
  );
  session.approveCalibration();
  expect(latest.calibration?.approved).toBe(true);
});

test("TEST-MIDI-005 unexpected disconnect aborts capture without learner judgment", async () => {
  const { access, input, session } = fixture();
  let latest = session.current();
  session.subscribe((snapshot) => { latest = snapshot; });
  await session.requestPermission();
  await session.connect(input.id);
  session.startCalibration();
  input.emit([0x90, 60, 70], 100);
  Object.defineProperty(input, "state", { value: "disconnected", configurable: true });
  access.onstatechange?.({ port: input });
  expect(latest.capture).toBe("aborted");
  expect(latest.active_notes).toEqual([]);
  expect(latest.diagnostics).toContainEqual(expect.objectContaining({
    code: "MIDI_INPUT_DISCONNECTED",
    blocking: true,
  }));
});

test("TEST-MIDI-006 absent Web MIDI remains explicitly unsupported", async () => {
  const session = new BrowserMidiSession(null);
  expect(session.current().permission).toBe("unsupported");
  await session.requestPermission();
  expect(session.current().permission).toBe("unsupported");
  expect(session.current().inputs).toEqual([]);
});

test("TEST-MIDI-009 pause and discomfort stop capture without learner penalty", async () => {
  const { input, session } = fixture();
  let latest = session.current();
  session.subscribe((snapshot) => { latest = snapshot; });
  await session.requestPermission();
  await session.connect(input.id);
  session.startCalibration();
  session.pauseCalibration();
  input.emit([0x90, 60, 70], 100);
  expect(latest.raw_messages).toHaveLength(0);
  session.resumeCalibration();
  input.emit([0x90, 60, 70], 101);
  expect(latest.raw_messages).toHaveLength(1);
  session.stopForDiscomfort();
  expect(latest.capture).toBe("aborted");
  expect(latest.calibration).toBeNull();
  expect(latest.diagnostics).toContainEqual(expect.objectContaining({
    code: "LEARNER_DISCOMFORT_SAFE_STOP",
    blocking: false,
  }));
});

test("TEST-MIDI-010 disconnect after approval preserves completed evidence", async () => {
  const { access, input, session } = fixture();
  let latest = session.current();
  session.subscribe((snapshot) => { latest = snapshot; });
  await session.requestPermission();
  await session.connect(input.id);
  session.startCalibration();
  [60, 62, 64, 65, 67].forEach((note, index) => input.emit([0x90, note, 70], 100 + index));
  session.stopCalibration();
  session.approveCalibration();
  expect(latest.calibration?.approved).toBe(true);

  Object.defineProperty(input, "state", { value: "disconnected", configurable: true });
  access.onstatechange?.({ port: input });

  expect(latest.connection).toBe("disconnected");
  expect(latest.capture).toBe("stopped");
  expect(latest.calibration?.approved).toBe(true);
  expect(latest.diagnostics).toContainEqual(expect.objectContaining({
    code: "MIDI_INPUT_DISCONNECTED",
    blocking: false,
  }));
});

test("TEST-MIDI-011 approved calibration is preserved across bounded attempt capture", async () => {
  const { input, session, setNow } = fixture();
  let latest = session.current();
  session.subscribe((snapshot) => { latest = snapshot; });
  await session.requestPermission();
  await session.connect(input.id);
  session.startCalibration();
  [60, 62, 64, 65, 67].forEach((note, index) => input.emit([0x90, note, 70], 100 + index));
  session.stopCalibration();
  session.approveCalibration();
  const approvedCalibration = latest.calibration;

  setNow(200);
  session.startAttempt();
  input.emit([0x90, 60, 80], 201);
  input.emit([0x80, 60, 0], 202);
  setNow(203);
  session.stopAttempt();

  expect(latest.capture_purpose).toBe("attempt");
  expect(latest.capture).toBe("stopped");
  expect(latest.capture_started_at_utc).toBe("2026-10-01T20:00:00.000Z");
  expect(latest.capture_start_microseconds).toBe(200_000);
  expect(latest.capture_end_microseconds).toBe(203_000);
  expect(latest.raw_messages).toHaveLength(2);
  expect(latest.normalized_events.map((event) => event.kind)).toEqual(["note-on", "note-off"]);
  expect(latest.calibration).toEqual(approvedCalibration);
  expect(latest.calibration?.approved).toBe(true);
});

test("TEST-MIDI-012 attempt discomfort stop retains calibration and records no penalty", async () => {
  const { input, session } = fixture();
  let latest = session.current();
  session.subscribe((snapshot) => { latest = snapshot; });
  await session.requestPermission();
  await session.connect(input.id);
  session.startCalibration();
  [60, 62, 64, 65, 67].forEach((note, index) => input.emit([0x90, note, 70], 100 + index));
  session.stopCalibration();
  session.approveCalibration();

  session.startAttempt();
  input.emit([0x90, 60, 80], 200);
  session.stopAttemptForDiscomfort();

  expect(latest.capture).toBe("aborted");
  expect(latest.calibration?.approved).toBe(true);
  expect(latest.diagnostics).toContainEqual(expect.objectContaining({
    code: "LEARNER_DISCOMFORT_SAFE_STOP",
    blocking: false,
  }));
});

test("TEST-MIDI-013 exposes held keys without recording evidence outside an authorized capture", async () => {
  const { input, session } = fixture();
  let latest = session.current();
  session.subscribe((snapshot) => { latest = snapshot; });
  await session.requestPermission();
  await session.connect(input.id);

  input.emit([0x90, 60, 80], 100);
  input.emit([0x90, 64, 70], 101);
  expect(latest.active_notes).toEqual([60, 64]);
  expect(latest.raw_messages).toEqual([]);
  expect(latest.normalized_events).toEqual([]);

  input.emit([0x80, 60, 0], 102);
  expect(latest.active_notes).toEqual([64]);
  input.emit([0x90, 64, 0], 103);
  expect(latest.active_notes).toEqual([]);
  expect(latest.raw_messages).toEqual([]);
  expect(latest.normalized_events).toEqual([]);
});
