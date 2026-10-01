import { fireEvent, render, screen, waitFor } from "@testing-library/react";

import { App } from "./App";

vi.mock("./notation/NotationSurface", () => ({
  NotationSurface: ({ bundle }: { bundle: { title: string | null } }) => (
    <div data-testid="notation-surface">Notation: {bundle.title}</div>
  ),
}));

vi.mock("./playback/PlaybackSurface", () => ({
  PlaybackSurface: ({ plan }: { plan: { notes: unknown[] } }) => (
    <div data-testid="playback-surface">Playback: {plan.notes.length} notes</div>
  ),
}));

vi.mock("./teaching/ExerciseLessonSurface", () => ({
  ExerciseLessonSurface: ({ plan, presentation }: {
    plan: { exercises: unknown[] };
    presentation: { exercise_id: string };
  }) => (
    <div data-testid="lesson-surface">
      Lesson: {plan.exercises.length} steps · {presentation.exercise_id}
    </div>
  ),
}));

const config = {
  app_contract_version: "0.1.0",
  launch_token: "token",
  accepted_extensions: [".mxl", ".musicxml", ".xml"],
  max_upload_bytes: 8_388_608,
};

afterEach(() => {
  vi.restoreAllMocks();
});

test("TEST-APP-UI-001 shows idle, loading, and canonical-ready states", async () => {
  let finishUpload: ((response: Response) => void) | undefined;
  vi.spyOn(globalThis, "fetch")
    .mockResolvedValueOnce(new Response(JSON.stringify(config), { status: 200 }))
    .mockImplementationOnce(() => new Promise((resolve) => { finishUpload = resolve; }))
    .mockResolvedValueOnce(new Response(JSON.stringify({
      app_contract_version: "0.1.0",
      notation: { title: "Hot Cross Buns", renderer: { anchors: Array(30) } },
      playback: { notes: Array(17), duration_microseconds: 4_000_000 },
    }), { status: 200 }))
    .mockResolvedValueOnce(new Response(JSON.stringify({
      app_contract_version: "0.1.0",
      plan: {
        id: "lesson-plan:one",
        exercises: [{ id: "exercise:one" }],
        nodes: [{ id: "node:one", exercise_id: "exercise:one" }],
      },
    }), { status: 200 }))
    .mockResolvedValueOnce(new Response(JSON.stringify({
      app_contract_version: "0.1.0",
      presentation: { exercise_id: "exercise:one" },
    }), { status: 200 }));

  const { container } = render(<App />);
  await screen.findByText("Choose a score");
  const input = container.querySelector("input[type=file]");
  expect(input).not.toBeNull();
  expect(input).toBeEnabled();
  fireEvent.change(input!, { target: { files: [new File(["score"], "hot-cross-buns.mxl")] } });
  expect(await screen.findByText("Reading your score…")).toBeInTheDocument();
  finishUpload!(new Response(JSON.stringify({
    session_id: "one",
    package_id: "package:one",
    expires_in_seconds: 1800,
    scores: [{ score_id: "score:one", title: "Hot Cross Buns" }],
    diagnostics: [],
  }), { status: 201 }));
  expect(await screen.findByRole("heading", { name: "Hot Cross Buns" })).toBeInTheDocument();
  expect(screen.getByText(/17 sounding notes/)).toBeInTheDocument();
  expect(screen.getByTestId("lesson-surface")).toHaveTextContent("1 steps · exercise:one");
});

test("TEST-APP-UI-002 reports a stable validation failure without losing the shell", async () => {
  vi.spyOn(globalThis, "fetch")
    .mockResolvedValueOnce(new Response(JSON.stringify(config), { status: 200 }))
    .mockResolvedValueOnce(new Response(JSON.stringify({ diagnostics: [{
      code: "APP_SCORE_INGESTION_REJECTED",
      stage: "application",
      message: "The file is not a supported, valid MusicXML score.",
    }] }), { status: 422 }));

  const { container } = render(<App />);
  await screen.findByText("Choose a score");
  fireEvent.change(container.querySelector("input[type=file]")!, {
    target: { files: [new File(["bad"], "bad.musicxml")] },
  });
  expect(await screen.findByRole("alert")).toHaveTextContent("valid MusicXML score");
  expect(screen.getByText("APP_SCORE_INGESTION_REJECTED")).toBeInTheDocument();
  await waitFor(() => expect(container.querySelector("input[type=file]")).toBeEnabled());
});

test("TEST-APP-UI-003 requires an explicit choice for a multi-score package", async () => {
  vi.spyOn(globalThis, "fetch")
    .mockResolvedValueOnce(new Response(JSON.stringify(config), { status: 200 }))
    .mockResolvedValueOnce(new Response(JSON.stringify({
      session_id: "opus",
      package_id: "package:opus",
      expires_in_seconds: 1800,
      scores: [
        { score_id: "score:one", title: "First movement" },
        { score_id: "score:two", title: "Second movement" },
      ],
      diagnostics: [],
    }), { status: 201 }));

  const { container } = render(<App />);
  await screen.findByText("Choose a score");
  fireEvent.change(container.querySelector("input[type=file]")!, {
    target: { files: [new File(["opus"], "collection.mxl")] },
  });
  expect(await screen.findByLabelText(/more than one score/)).toHaveValue("score:one");
  expect(screen.getByRole("button", { name: "Prepare score" })).toBeInTheDocument();
});
