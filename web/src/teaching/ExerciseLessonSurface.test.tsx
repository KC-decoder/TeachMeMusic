import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";

import type {
  AttemptResult,
  ExercisePresentation,
  TeachingPlan,
  TeachingRunResponse,
} from "../api";
import type { ViewerBundle } from "../contracts/viewer";
import type { AttemptMidiSession, MidiSnapshot } from "../midi/contracts";
import { ExerciseLessonSurface } from "./ExerciseLessonSurface";

vi.mock("../playback/PlaybackSurface", () => ({
  PlaybackSurface: ({ heading, countIn, onComplete }: { heading: string; countIn: { beats: number } | null; onComplete?: () => void }) => (
    <div data-testid="exercise-playback">
      {heading} · {countIn?.beats ?? 0} beats
      {onComplete && <button type="button" onClick={onComplete}>Complete demonstration</button>}
    </div>
  ),
}));
vi.mock("../piano/VirtualPiano", () => ({
  VirtualPiano: ({ activeNotes, guidanceMode }: { activeNotes: Array<{ midiPitch: number }>; guidanceMode: string }) => (
    <div data-testid="exercise-piano">Piano · {guidanceMode} · {activeNotes.map((note) => note.midiPitch).join(",")}</div>
  ),
}));
vi.mock("../notation/NotationSurface", () => ({
  NotationSurface: ({ allowedEventIds, focusEventIds }: { allowedEventIds: string[]; focusEventIds: string[] }) => (
    <div data-testid="exercise-notation">{allowedEventIds.join(",")} · focus {focusEventIds.join(",")}</div>
  ),
}));

const plan = {
  id: "lesson-plan:one",
  exercises: [
    {
      id: "exercise:one",
      primary_skill: "pitch",
      secondary_skills: [],
      practice_modes: ["follow-pitch"],
      boundary_reason: "First bounded phrase.",
      initial_support: {
        tempo_bpm: { numerator: 60, denominator: 1 },
        notation_visible: true,
        keyboard_highlighting: true,
        prompts_visible: true,
      },
    },
    {
      id: "exercise:two",
      primary_skill: "rhythm",
      secondary_skills: [],
      practice_modes: ["pulse-guided"],
      boundary_reason: "Second bounded phrase.",
      initial_support: {
        tempo_bpm: { numerator: 72, denominator: 1 },
        notation_visible: true,
        keyboard_highlighting: true,
        prompts_visible: false,
      },
    },
  ],
  nodes: [
    { id: "node:one", kind: "exercise", exercise_id: "exercise:one", prerequisites: [], successors: ["node:two"] },
    { id: "node:two", kind: "integration", exercise_id: "exercise:two", prerequisites: ["node:one"], successors: [] },
  ],
  root_node_ids: ["node:one"],
  diagnostics: [],
  run_id: "run:one",
  track: "beginner",
} as unknown as TeachingPlan;

const presentation = {
  contract_id: "org.teachmemusic.exercise-presentation",
  contract_version: "0.1.0",
  plan_id: "lesson-plan:one",
  exercise_id: "exercise:one",
  package_id: "package:one",
  score_id: "score:one",
  expected_content_sha256: "a".repeat(64),
  material_kind: "canonical",
  measure_ids: ["measure:one", "measure:two"],
  event_ids: ["event:one", "event:two"],
  provenance_ids: ["event:one", "event:two"],
  measure_numbers: ["1", "2"],
  primary_skill: "pitch",
  practice_modes: ["follow-pitch"],
  boundary_reason: "First bounded phrase.",
  aid_state: {
    tempo_bpm: { numerator: 60, denominator: 1 },
    count_in_enabled: true,
    count_in_beats: 4,
    count_in_beat_microseconds: 1_000_000,
    notation_visible: true,
    keyboard_visible: true,
    pitch_prompts_visible: true,
  },
  notation_renderer_sha256: "b".repeat(64),
  demonstration: { notes: [{ midi_pitch: 71 }], diagnostics: [] },
  diagnostics: [],
} as unknown as ExercisePresentation;

const notation = { renderer: { anchors: [] } } as unknown as ViewerBundle;

const teachingRun = {
  app_contract_version: "0.3.0",
  run_id: "teaching-run:one",
  inspection: {
    event_count: 4,
    attempt_count: 0,
  },
} as TeachingRunResponse;

function continueFromPracticeSetup() {
  fireEvent.click(screen.getByRole("button", { name: /Continue (to exercise|without recording)/ }));
}

test("TEST-APP-TEACHING-001 presents exact range and reversible practice aids", () => {
  const selectExercise = vi.fn();
  const changeTempo = vi.fn();
  const { container } = render(
    <ExerciseLessonSurface
      plan={plan}
      presentation={presentation}
      notation={notation}
      onSelectExercise={selectExercise}
      onTempoChange={async (tempo) => { changeTempo(tempo); }}
      teachingRun={null}
      onStartRun={async () => undefined}
      onSubmitAttempt={async () => { throw new Error("not used"); }}
      onExportRun={async () => undefined}
      onImportRun={async () => undefined}
      onDeleteRun={async () => undefined}
    />,
  );

  expect(screen.getByRole("heading", { name: "Measures 1–2" })).toBeInTheDocument();
  expect(screen.queryByRole("dialog", { name: "Measures 1–2" })).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Open practice screen" }));
  expect(screen.getByRole("dialog", { name: "Setup, calibration, and evidence" })).toBeInTheDocument();
  continueFromPracticeSetup();
  expect(screen.getByTestId("exercise-playback")).toHaveTextContent("4 beats");
  expect(screen.getByTestId("exercise-notation")).toHaveTextContent("event:one,event:two");
  expect(screen.getByTestId("exercise-piano")).toBeInTheDocument();
  expect(container.querySelector(".lesson-panel")).toHaveAttribute(
    "data-expected-content",
    "a".repeat(64),
  );

  fireEvent.click(screen.getByRole("button", { name: "Back to practice setup" }));
  fireEvent.click(screen.getByLabelText("Show notation"));
  fireEvent.click(screen.getByLabelText("Light piano keys"));
  continueFromPracticeSetup();
  expect(screen.queryByTestId("exercise-notation")).not.toBeInTheDocument();
  expect(screen.queryByTestId("exercise-piano")).not.toBeInTheDocument();
  expect(container.querySelector(".lesson-panel")).toHaveAttribute(
    "data-expected-content",
    "a".repeat(64),
  );

  fireEvent.click(screen.getByRole("button", { name: "Back to practice setup" }));
  fireEvent.change(screen.getByLabelText("Demonstration tempo"), { target: { value: "72" } });
  expect(changeTempo).toHaveBeenCalledWith(72);
  fireEvent.click(screen.getByRole("button", { name: "Close practice setup" }));
  fireEvent.click(screen.getByRole("button", { name: "Next exercise" }));
  expect(selectExercise).toHaveBeenCalledWith("exercise:two");
});

test("TEST-APP-TEACHING-002 count-in can be removed without changing expected notes", () => {
  const { container } = render(
    <ExerciseLessonSurface
      plan={plan}
      presentation={presentation}
      notation={notation}
      onSelectExercise={vi.fn()}
      onTempoChange={async () => undefined}
      teachingRun={null}
      onStartRun={async () => undefined}
      onSubmitAttempt={async () => { throw new Error("not used"); }}
      onExportRun={async () => undefined}
      onImportRun={async () => undefined}
      onDeleteRun={async () => undefined}
    />,
  );
  fireEvent.click(screen.getByRole("button", { name: "Open practice screen" }));
  fireEvent.click(screen.getByLabelText("Count in"));
  continueFromPracticeSetup();
  expect(screen.getByTestId("exercise-playback")).toHaveTextContent("0 beats");
  expect(container.querySelector(".lesson-panel")).toHaveAttribute(
    "data-expected-content",
    "a".repeat(64),
  );
});

test("TEST-APP-TEACHING-003 records independent plan, capture, and export choices", () => {
  const startRun = vi.fn(async () => undefined);
  render(
    <ExerciseLessonSurface
      plan={plan}
      presentation={presentation}
      notation={notation}
      onSelectExercise={vi.fn()}
      onTempoChange={async () => undefined}
      teachingRun={null}
      onStartRun={startRun}
      onSubmitAttempt={async () => { throw new Error("not used"); }}
      onExportRun={async () => undefined}
      onImportRun={async () => undefined}
      onDeleteRun={async () => undefined}
    />,
  );

  fireEvent.click(screen.getByRole("button", { name: "Open practice screen" }));
  const start = screen.getByRole("button", { name: "Start local teaching run" });
  expect(start).toBeDisabled();
  fireEvent.click(screen.getByLabelText(/reviewed the untouched plan/i));
  fireEvent.click(screen.getByLabelText(/approve local MIDI/i));
  expect(start).toBeEnabled();
  fireEvent.click(screen.getByLabelText(/optionally approve self-report/i));
  fireEvent.click(screen.getByLabelText(/approve local evidence export/i));
  fireEvent.click(start);
  expect(startRun).toHaveBeenCalledWith({ captureSelfReport: true, allowExport: true });
});

test("TEST-APP-TEACHING-024 permits local MIDI capture without export approval", () => {
  const startRun = vi.fn(async () => undefined);
  render(
    <ExerciseLessonSurface
      plan={plan}
      presentation={presentation}
      notation={notation}
      onSelectExercise={vi.fn()}
      onTempoChange={async () => undefined}
      teachingRun={null}
      onStartRun={startRun}
      onSubmitAttempt={async () => { throw new Error("not used"); }}
      onExportRun={async () => undefined}
      onImportRun={async () => undefined}
      onDeleteRun={async () => undefined}
    />,
  );

  fireEvent.click(screen.getByRole("button", { name: "Open practice screen" }));
  fireEvent.click(screen.getByLabelText(/reviewed the untouched plan/i));
  fireEvent.click(screen.getByLabelText(/approve local MIDI/i));
  fireEvent.click(screen.getByRole("button", { name: "Start local teaching run" }));
  expect(startRun).toHaveBeenCalledWith({ captureSelfReport: false, allowExport: false });
});

test("TEST-APP-TEACHING-004 freezes recorded aids and policy-controls progression", () => {
  render(
    <ExerciseLessonSurface
      plan={plan}
      presentation={presentation}
      notation={notation}
      onSelectExercise={vi.fn()}
      onTempoChange={async () => undefined}
      teachingRun={teachingRun}
      onStartRun={async () => undefined}
      onSubmitAttempt={async () => { throw new Error("not used"); }}
      onExportRun={async () => undefined}
      onImportRun={async () => undefined}
      onDeleteRun={async () => undefined}
    />,
  );

  expect(screen.getByRole("button", { name: "Next exercise" })).toBeDisabled();
  expect(screen.getByText(/Policy feedback unlocks the next performance exercise/i)).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Open practice screen" }));
  expect(screen.getByLabelText("Count in")).toBeDisabled();
  expect(screen.getByLabelText("Show notation")).toBeDisabled();
  expect(screen.getByLabelText("Light piano keys")).toBeDisabled();
  expect(screen.getByLabelText("Demonstration tempo")).toBeDisabled();
});

test("TEST-APP-MOBILE-001 opens a dedicated practice stage outside secondary setup", () => {
  const { container } = render(
    <ExerciseLessonSurface
      plan={plan}
      presentation={presentation}
      notation={notation}
      onSelectExercise={vi.fn()}
      onTempoChange={async () => undefined}
      teachingRun={null}
      onStartRun={async () => undefined}
      onSubmitAttempt={async () => { throw new Error("not used"); }}
      onExportRun={async () => undefined}
      onImportRun={async () => undefined}
      onDeleteRun={async () => undefined}
    />,
  );

  expect(screen.queryByRole("dialog", { name: "Measures 1–2" })).not.toBeInTheDocument();
  expect(screen.queryByTestId("exercise-notation")).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Open practice screen" }));

  const setup = screen.getByRole("dialog", { name: "Setup, calibration, and evidence" });
  expect(setup).toBeInTheDocument();
  expect(screen.queryByTestId("exercise-notation")).not.toBeInTheDocument();
  continueFromPracticeSetup();

  const stage = screen.getByRole("dialog", { name: "Measures 1–2" });
  const notationRegion = container.querySelector('[data-mobile-region="notation"]');
  const controlsRegion = container.querySelector('[data-mobile-region="controls"]');
  const pianoRegion = container.querySelector('[data-mobile-region="piano"]');

  expect(stage).toHaveClass("practice-stage", "has-piano");
  expect(notationRegion).toContainElement(screen.getByTestId("exercise-notation"));
  expect(controlsRegion).toContainElement(screen.getByTestId("exercise-playback"));
  expect(pianoRegion).toContainElement(screen.getByTestId("exercise-piano"));
  expect(controlsRegion?.compareDocumentPosition(notationRegion as Node)).toBe(
    Node.DOCUMENT_POSITION_FOLLOWING,
  );
  expect(notationRegion?.compareDocumentPosition(pianoRegion as Node)).toBe(
    Node.DOCUMENT_POSITION_FOLLOWING,
  );
  expect(screen.queryByRole("dialog", { name: "Setup, calibration, and evidence" })).not.toBeInTheDocument();
  expect(document.body).toHaveClass("practice-stage-open");
  expect(screen.getByRole("navigation", { name: "Practice exercise navigation" })).toBeInTheDocument();
});

test("TEST-APP-MOBILE-022 closes the viewport-locked practice stage without losing the lesson", () => {
  render(
    <ExerciseLessonSurface
      plan={plan}
      presentation={presentation}
      notation={notation}
      onSelectExercise={vi.fn()}
      onTempoChange={async () => undefined}
      teachingRun={null}
      onStartRun={async () => undefined}
      onSubmitAttempt={async () => { throw new Error("not used"); }}
      onExportRun={async () => undefined}
      onImportRun={async () => undefined}
      onDeleteRun={async () => undefined}
    />,
  );

  fireEvent.click(screen.getByRole("button", { name: "Open practice screen" }));
  fireEvent.keyDown(window, { key: "Escape" });

  expect(screen.queryByRole("dialog", { name: "Measures 1–2" })).not.toBeInTheDocument();
  expect(document.body).not.toHaveClass("practice-stage-open");
  expect(screen.getByRole("button", { name: "Open practice screen" })).toBeInTheDocument();
});

test("TEST-APP-MOBILE-023 submits a stopped remote attempt from the practice stage", async () => {
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
  const result = {
    attempt_id: "attempt:mobile-stage",
    observations: [],
    evidence_records: [],
    feedback: {
      id: "feedback:mobile-stage",
      timing: "end-of-attempt",
      target: "Repeat the first measure",
      observation: "The paired desktop evaluated the completed attempt.",
      boundary: null,
      action: "Repeat once.",
      reason: "One stable repetition is required.",
    },
    decision: {
      id: "decision:mobile-stage",
      action: "repeat",
      next_node_id: null,
      reason: "One stable repetition is required.",
    },
    mastery: {
      correct_note_count: 1,
      expected_note_count: 2,
      extra_note_count: 0,
      green_percent: 50,
      threshold_percent: 95,
      action: "retry",
      next_node_id: null,
      reduced_tempo: false,
    },
    next_support: null,
    inspection: { attempt_count: 1 },
  } as unknown as AttemptResult;
  const remoteSubmit = vi.fn(async () => result);

  render(
    <ExerciseLessonSurface
      plan={plan}
      presentation={presentation}
      notation={notation}
      onSelectExercise={vi.fn()}
      onTempoChange={async () => undefined}
      teachingRun={teachingRun}
      onStartRun={async () => undefined}
      onSubmitAttempt={async () => { throw new Error("phone must not submit local evidence"); }}
      onRemoteSubmit={remoteSubmit}
      onExportRun={async () => undefined}
      onImportRun={async () => undefined}
      onDeleteRun={async () => undefined}
      midiSession={remote}
    />,
  );

  fireEvent.click(screen.getByRole("button", { name: "Open practice screen" }));
  continueFromPracticeSetup();
  const stage = screen.getByRole("dialog", { name: "Measures 1–2" });
  fireEvent.click(within(stage).getByRole("button", { name: "Start attempt" }));
  fireEvent.click(within(stage).getByRole("button", { name: "Finish attempt" }));
  fireEvent.click(within(stage).getByRole("button", { name: "Compare and give feedback" }));

  await waitFor(() => expect(remoteSubmit).toHaveBeenCalledOnce());
  expect(within(stage).getByRole("heading", { name: "Try again" })).toBeInTheDocument();
});

test("TEST-APP-MOBILE-030 hands off from listening to note-by-note practice and submits", async () => {
  const guidedPlan = {
    ...plan,
    exercises: [
      {
        ...plan.exercises[0],
        initial_support: {
          ...plan.exercises[0]!.initial_support,
          cursor_visible: true,
          note_names_visible: true,
          demonstration_available: true,
        },
      },
      plan.exercises[1],
    ],
  } as TeachingPlan;
  const guidedPresentation = {
    ...presentation,
    demonstration: {
      ...presentation.demonstration,
      notes: [
        {
          id: "playback-note:one",
          start_microseconds: 0,
          end_microseconds: 500_000,
          midi_pitch: 60,
          chord_id: null,
          dynamic_percent: null,
          source_events: [{
            event_id: "event:one",
            part_id: "part:one",
            measure_id: "measure:one",
            staff: "1",
            voice: "1",
            score_onset: { numerator: 0, denominator: 1 },
            clef_group_id: "clef:one",
            clef: { sign: "G", line: 2, octave_change: null },
          }],
        },
        {
          id: "playback-note:two",
          start_microseconds: 500_000,
          end_microseconds: 1_000_000,
          midi_pitch: 62,
          chord_id: null,
          dynamic_percent: null,
          source_events: [{
            event_id: "event:two",
            part_id: "part:one",
            measure_id: "measure:one",
            staff: "1",
            voice: "1",
            score_onset: { numerator: 1, denominator: 1 },
            clef_group_id: "clef:one",
            clef: { sign: "G", line: 2, octave_change: null },
          }],
        },
      ],
    },
  } as ExercisePresentation;
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
  const patchSnapshot = (value: Partial<MidiSnapshot>) => {
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
    startAttempt: vi.fn(() => patchSnapshot({ capture: "recording", capture_purpose: "attempt" })),
    stopAttempt: vi.fn(() => patchSnapshot({ capture: "stopped", capture_purpose: "attempt" })),
    pauseAttempt: vi.fn(),
    resumeAttempt: vi.fn(),
    abortAttempt: vi.fn(),
    stopAttemptForDiscomfort: vi.fn(),
  };
  const result = {
    attempt_id: "attempt:guided",
    observations: [
      {
        id: "observation:missing-second-note",
        dimension: "pitch",
        status: "discrepancy",
        blocking: true,
        expected_canonical_ids: ["event:two"],
        observed_event_ids: [],
        expected_value: "midi:62",
        observed_value: "missing",
      },
    ],
    evidence_records: [],
    feedback: {
      id: "feedback:guided",
      timing: "end-of-attempt",
      target: "Complete the exercise",
      observation: "One of two notes matched.",
      boundary: null,
      action: "Repeat.",
      reason: "Below threshold.",
    },
    decision: {
      id: "decision:guided",
      action: "correct",
      next_node_id: "node:one",
      reason: "Below threshold.",
    },
    mastery: {
      correct_note_count: 1,
      expected_note_count: 2,
      extra_note_count: 0,
      green_percent: 50,
      threshold_percent: 95,
      action: "retry",
      next_node_id: null,
      reduced_tempo: false,
    },
    next_support: null,
    inspection: { attempt_count: 1 },
  } as unknown as AttemptResult;
  const remoteSubmit = vi.fn(async () => result);

  render(
    <ExerciseLessonSurface
      plan={guidedPlan}
      presentation={guidedPresentation}
      notation={notation}
      onSelectExercise={vi.fn()}
      onTempoChange={async () => undefined}
      teachingRun={teachingRun}
      onStartRun={async () => undefined}
      onSubmitAttempt={async () => { throw new Error("phone must not submit local evidence"); }}
      onRemoteSubmit={remoteSubmit}
      onExportRun={async () => undefined}
      onImportRun={async () => undefined}
      onDeleteRun={async () => undefined}
      midiSession={remote}
    />,
  );

  fireEvent.click(screen.getByRole("button", { name: "Open practice screen" }));
  continueFromPracticeSetup();
  fireEvent.click(screen.getByRole("button", { name: "Complete demonstration" }));
  expect(await screen.findByText("Your turn")).toBeInTheDocument();
  expect(screen.getByTestId("exercise-piano")).toHaveTextContent("practice · 60");
  expect(screen.getByTestId("exercise-notation")).toHaveTextContent("focus event:one");

  patchSnapshot({ active_notes: [60] });
  await waitFor(() => expect(screen.getByTestId("exercise-piano")).toHaveTextContent("practice · 62"));
  patchSnapshot({ active_notes: [] });
  patchSnapshot({ active_notes: [62] });

  await waitFor(() => expect(remote.stopAttempt).toHaveBeenCalledOnce());
  await waitFor(() => expect(remoteSubmit).toHaveBeenCalledOnce());
  expect(await screen.findByRole("heading", { name: "Try again" })).toBeInTheDocument();
  expect(screen.getByTestId("exercise-piano")).toHaveTextContent("missed · 62");
  expect(screen.getByTestId("exercise-notation")).toHaveTextContent("focus event:two");
  expect(screen.getByRole("dialog", { name: "Measures 1–2" })).toHaveClass("has-missed-notes");
});
