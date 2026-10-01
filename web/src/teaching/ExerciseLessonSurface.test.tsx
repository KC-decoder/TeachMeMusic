import { fireEvent, render, screen } from "@testing-library/react";

import type { ExercisePresentation, TeachingPlan } from "../api";
import type { ViewerBundle } from "../contracts/viewer";
import { ExerciseLessonSurface } from "./ExerciseLessonSurface";

vi.mock("../playback/PlaybackSurface", () => ({
  PlaybackSurface: ({ heading, countIn }: { heading: string; countIn: { beats: number } | null }) => (
    <div data-testid="exercise-playback">{heading} · {countIn?.beats ?? 0} beats</div>
  ),
}));
vi.mock("../piano/VirtualPiano", () => ({
  VirtualPiano: () => <div data-testid="exercise-piano">Piano</div>,
}));
vi.mock("../notation/NotationSurface", () => ({
  NotationSurface: ({ allowedEventIds }: { allowedEventIds: string[] }) => (
    <div data-testid="exercise-notation">{allowedEventIds.join(",")}</div>
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
} as TeachingPlan;

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

test("TEST-APP-TEACHING-001 presents exact range and reversible practice aids", () => {
  const selectExercise = vi.fn();
  const changeTempo = vi.fn();
  const { container } = render(
    <ExerciseLessonSurface
      plan={plan}
      presentation={presentation}
      notation={notation}
      onSelectExercise={selectExercise}
      onTempoChange={changeTempo}
    />,
  );

  expect(screen.getByRole("heading", { name: "Measures 1–2" })).toBeInTheDocument();
  expect(screen.getByTestId("exercise-playback")).toHaveTextContent("4 beats");
  expect(screen.getByTestId("exercise-notation")).toHaveTextContent("event:one,event:two");
  expect(screen.getByTestId("exercise-piano")).toBeInTheDocument();
  expect(container.querySelector(".lesson-panel")).toHaveAttribute(
    "data-expected-content",
    "a".repeat(64),
  );

  fireEvent.click(screen.getByLabelText("Show notation"));
  fireEvent.click(screen.getByLabelText("Light piano keys"));
  expect(screen.queryByTestId("exercise-notation")).not.toBeInTheDocument();
  expect(screen.queryByTestId("exercise-piano")).not.toBeInTheDocument();
  expect(container.querySelector(".lesson-panel")).toHaveAttribute(
    "data-expected-content",
    "a".repeat(64),
  );

  fireEvent.change(screen.getByLabelText("Demonstration tempo"), { target: { value: "72" } });
  expect(changeTempo).toHaveBeenCalledWith(72);
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
      onTempoChange={vi.fn()}
    />,
  );
  fireEvent.click(screen.getByLabelText("Count in"));
  expect(screen.getByTestId("exercise-playback")).toHaveTextContent("0 beats");
  expect(container.querySelector(".lesson-panel")).toHaveAttribute(
    "data-expected-content",
    "a".repeat(64),
  );
});
