import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";

import type {
  AttemptResult,
  ExercisePresentation,
  LessonExercise,
  TeachingRunResponse,
} from "../api";
import { BrowserMidiSession, type MidiClock } from "../midi/BrowserMidiSession";
import type {
  AttemptMidiSession,
  MidiAccessLike,
  MidiInputLike,
  MidiMessageEventLike,
  MidiSnapshot,
} from "../midi/contracts";
import { TeachingAttemptSurface } from "./TeachingAttemptSurface";

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

async function approvedSession() {
  const input = new FakeInput();
  const access: MidiAccessLike = { inputs: new Map([[input.id, input]]), onstatechange: null };
  let now = 100;
  const clock: MidiClock = {
    nowMilliseconds: () => now,
    timeOriginMilliseconds: () => 1_700_000_000_000,
    nowUtc: () => "2026-10-02T16:00:00.000Z",
  };
  const session = new BrowserMidiSession(async () => access, clock);
  await session.requestPermission();
  await session.connect(input.id);
  session.startCalibration();
  input.emit([0x90, 60, 70], 101);
  session.stopCalibration();
  session.approveCalibration();
  return { input, session, setNow(value: number) { now = value; } };
}

const initialSupport = {
  id: "support:initial",
  tempo_bpm: { numerator: 60, denominator: 1 },
  notation_visible: true,
  cursor_visible: true,
  note_names_visible: true,
  keyboard_highlighting: true,
  fingering_visible: false,
  demonstration_available: true,
  follow_mode: true,
  metronome: false,
  tempo_percent: 60,
  prompts_visible: true,
};

const exercise = {
  id: "exercise:one",
  primary_skill: "pitch",
  secondary_skills: [],
  practice_modes: ["follow-pitch"],
  boundary_reason: "One phrase.",
  initial_support: initialSupport,
} as LessonExercise;

const presentation = {
  plan_id: "plan:one",
  exercise_id: exercise.id,
  score_id: "score:one",
} as ExercisePresentation;

const run = {
  app_contract_version: "0.3.0",
  run_id: "run:one",
  inspection: { attempt_count: 0 },
} as TeachingRunResponse;

test("TEST-APP-TEACHING-005 submits captured MIDI and applies authoritative feedback", async () => {
  const { input, session, setNow } = await approvedSession();
  const nextSupport = { ...initialSupport, id: "support:reduced", note_names_visible: false };
  const response = {
    attempt_id: "attempt:one",
    observations: [],
    evidence_records: [],
    feedback: {
      id: "feedback:one",
      timing: "end-of-attempt",
      target: "Keep the phrase steady",
      observation: "The expected pitch was observed.",
      boundary: "Timing is not judged without an approved timing window.",
      action: "Repeat once with fewer prompts.",
      reason: "One stable repetition is required.",
    },
    decision: {
      id: "decision:one",
      action: "reduce-support",
      next_node_id: "node:two",
      reason: "Pitch evidence is stable.",
    },
    mastery: {
      correct_note_count: 20,
      expected_note_count: 20,
      extra_note_count: 0,
      green_percent: 100,
      threshold_percent: 95,
      action: "exercise-complete",
      next_node_id: "node:two",
      reduced_tempo: false,
    },
    next_support: nextSupport,
    inspection: { attempt_count: 1 },
  } as unknown as AttemptResult;
  const submit = vi.fn(async () => response);
  const supportChange = vi.fn();
  const selectExercise = vi.fn();

  render(
    <TeachingAttemptSurface
      session={session}
      run={run}
      exercise={exercise}
      presentation={presentation}
      tempo={60}
      countInEnabled={true}
      onSubmit={submit}
      onSupportChange={supportChange}
      onSelectExercise={selectExercise}
      nodeExercise={(nodeId) => nodeId === "node:two" ? "exercise:two" : null}
    />,
  );

  fireEvent.click(screen.getByRole("button", { name: "Start attempt" }));
  input.emit([0x90, 60, 80], 201);
  input.emit([0x80, 60, 0], 202);
  setNow(203);
  fireEvent.click(screen.getByRole("button", { name: "Finish attempt" }));
  fireEvent.click(screen.getByRole("button", { name: "Compare and give feedback" }));

  await waitFor(() => expect(submit).toHaveBeenCalledOnce());
  expect(submit).toHaveBeenCalledWith(expect.objectContaining({
    score_id: "score:one",
    exercise_id: "exercise:one",
    practice_mode: "follow-pitch",
    support_state_id: "support:initial",
    completion: "completed",
    raw_messages: expect.arrayContaining([expect.objectContaining({ data: [0x90, 60, 80] })]),
  }));
  expect(await screen.findByRole("heading", { name: "Exercise complete" })).toBeInTheDocument();
  expect(screen.getByText("Attempt details")).toBeInTheDocument();
  expect(supportChange).toHaveBeenCalledWith(nextSupport);
  await waitFor(() => expect(selectExercise).toHaveBeenCalledWith("exercise:two"), {
    timeout: 2_000,
  });
});

test("TEST-APP-MOBILE-016 phone controls paired capture and renders authoritative feedback", async () => {
  let snapshot = {
    permission: "granted",
    connection: "connected",
    capture: "idle",
    capture_purpose: null,
    capture_started_at_utc: null,
    capture_start_microseconds: null,
    capture_end_microseconds: null,
    inputs: [],
    selected_input_id: null,
    raw_messages: [],
    normalized_events: [],
    diagnostics: [],
    active_notes: [],
    calibration: { approved: true },
  } as unknown as MidiSnapshot;
  const listeners = new Set<(value: MidiSnapshot) => void>();
  const patch = (value: Partial<MidiSnapshot>) => {
    snapshot = { ...snapshot, ...value };
    for (const listener of listeners) listener(snapshot);
  };
  const remote: AttemptMidiSession = {
    current: () => snapshot,
    subscribe: (listener) => {
      listeners.add(listener);
      listener(snapshot);
      return () => listeners.delete(listener);
    },
    startAttempt: () => patch({ capture: "recording", capture_purpose: "attempt" }),
    stopAttempt: () => patch({ capture: "stopped", capture_purpose: "attempt" }),
    pauseAttempt: () => patch({ capture: "paused" }),
    resumeAttempt: () => patch({ capture: "recording" }),
    abortAttempt: () => patch({ capture: "aborted" }),
    stopAttemptForDiscomfort: () => patch({ capture: "aborted" }),
  };
  const response = {
    attempt_id: "attempt:mobile",
    observations: [],
    evidence_records: [],
    feedback: {
      id: "feedback:mobile",
      timing: "end-of-attempt",
      target: "Use the paired result",
      observation: "The desktop captured the expected pitch.",
      boundary: null,
      action: "Repeat once.",
      reason: "The authoritative policy requested stabilization.",
    },
    decision: {
      id: "decision:mobile",
      action: "correct",
      next_node_id: "node:one",
      reason: "Two low attempts require a slower tempo.",
    },
    mastery: {
      correct_note_count: 1,
      expected_note_count: 4,
      extra_note_count: 1,
      green_percent: 20,
      threshold_percent: 95,
      action: "slow-down",
      next_node_id: null,
      reduced_tempo: false,
    },
    next_support: { ...initialSupport, id: "support:initial:mastery-slow", tempo_percent: 42 },
    inspection: { attempt_count: 2 },
  } as unknown as AttemptResult;
  const remoteSubmit = vi.fn(async () => response);

  render(
    <TeachingAttemptSurface
      session={remote}
      run={run}
      exercise={exercise}
      presentation={presentation}
      tempo={60}
      countInEnabled={true}
      onSubmit={async () => { throw new Error("phone must not submit local evidence"); }}
      onRemoteSubmit={remoteSubmit}
      onSupportChange={vi.fn()}
      onSelectExercise={vi.fn()}
      nodeExercise={(nodeId) => nodeId === "node:one" ? "exercise:one" : null}
      compact={true}
    />,
  );

  fireEvent.click(screen.getByRole("button", { name: "Start attempt" }));
  fireEvent.click(screen.getByRole("button", { name: "Finish attempt" }));
  fireEvent.click(screen.getByRole("button", { name: "Compare and give feedback" }));
  await waitFor(() => expect(remoteSubmit).toHaveBeenCalledOnce());
  expect(remoteSubmit).toHaveBeenCalledWith(expect.objectContaining({
    run_id: "run:one",
    exercise_id: "exercise:one",
    support_state_id: "support:initial",
  }));
  expect(await screen.findByRole("heading", { name: "Let’s slow it down" })).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Play slower" })).toBeInTheDocument();
  expect(screen.queryByText("Attempt result status")).not.toBeInTheDocument();
  expect(screen.queryByText(/Policy decision:/)).not.toBeInTheDocument();
});

test("TEST-APP-MOBILE-026 keeps attempt readiness visible when the Mac bridge is unavailable", () => {
  const snapshot = {
    permission: "granted",
    connection: "disconnected",
    capture: "idle",
    capture_purpose: null,
    capture_started_at_utc: null,
    capture_start_microseconds: null,
    capture_end_microseconds: null,
    inputs: [],
    selected_input_id: null,
    raw_messages: [],
    normalized_events: [],
    diagnostics: [],
    active_notes: [],
    calibration: null,
  } as MidiSnapshot;
  const remote: AttemptMidiSession = {
    current: () => snapshot,
    subscribe: (listener) => {
      listener(snapshot);
      return () => undefined;
    },
    startAttempt: vi.fn(),
    stopAttempt: vi.fn(),
    pauseAttempt: vi.fn(),
    resumeAttempt: vi.fn(),
    abortAttempt: vi.fn(),
    stopAttemptForDiscomfort: vi.fn(),
  };

  render(
    <TeachingAttemptSurface
      session={remote}
      run={run}
      exercise={exercise}
      presentation={presentation}
      tempo={60}
      countInEnabled={true}
      onSubmit={async () => { throw new Error("not used"); }}
      onRemoteSubmit={async () => { throw new Error("not used"); }}
      onSupportChange={vi.fn()}
      onSelectExercise={vi.fn()}
      nodeExercise={() => null}
    />,
  );

  expect(screen.getByRole("button", { name: "Start attempt" })).toBeDisabled();
  expect(screen.getByRole("status")).toHaveTextContent(
    "Mac MIDI bridge unavailable — keep the paired TeachMeMusic tab open.",
  );
});
