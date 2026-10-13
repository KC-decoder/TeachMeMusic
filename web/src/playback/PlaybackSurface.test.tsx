import { fireEvent, render, screen } from "@testing-library/react";

import type { PlaybackController, PlaybackSnapshot } from "../audio/PlaybackTransport";
import type { PlaybackPlan } from "../contracts/playback";
import { PlaybackSurface } from "./PlaybackSurface";

const plan = {
  duration_microseconds: 4_000_000,
  diagnostics: [{
    code: "PLAYBACK_TEMPO_FALLBACK",
    severity: "warning",
    message: "A declared caller fallback supplies the initial tempo.",
    canonical_ids: [],
  }],
  notes: [],
} as unknown as PlaybackPlan;

test("TEST-APP-PLAYBACK-005 exposes transport controls, diagnostics, and score focus", () => {
  const focus: string[][] = [];
  let observer: ((snapshot: PlaybackSnapshot) => void) | null = null;
  const controller: PlaybackController = {
    play: vi.fn(async () => {
      observer?.({
        status: "playing",
        positionMicroseconds: 1_000_000,
        durationMicroseconds: 4_000_000,
        activeNoteIds: ["note:one"],
        activeMidiPitches: [60],
        activeNotes: [{
          noteId: "note:one",
          midiPitch: 60,
          contributions: [{
            eventId: "event:one",
            clefGroupId: "clef:one",
            clef: { sign: "G", line: 2, octave_change: null },
            staff: "1",
            voice: "1",
          }],
        }],
        focusEventIds: ["event:one"],
        countInBeatsRemaining: 0,
        errorCode: null,
        errorMessage: null,
      });
    }),
    pause: vi.fn(),
    restart: vi.fn(async () => undefined),
    stop: vi.fn(),
    seek: vi.fn(),
    dispose: vi.fn(),
  };
  const factory = vi.fn((_plan: PlaybackPlan, nextObserver: (snapshot: PlaybackSnapshot) => void) => {
    observer = nextObserver;
    return controller;
  });

  const { unmount } = render(
    <PlaybackSurface plan={plan} controllerFactory={factory} onFocusEventIds={(ids) => focus.push(ids)} />,
  );
  fireEvent.click(screen.getByRole("button", { name: "Play" }));
  expect(controller.play).toHaveBeenCalledOnce();
  expect(screen.getByText("Playing · 1 active key")).toBeInTheDocument();
  expect(screen.getByText("0:01 / 0:04")).toBeInTheDocument();
  expect(focus.at(-1)).toEqual(["event:one"]);

  fireEvent.change(screen.getByLabelText("Playback position"), { target: { value: "2500000" } });
  expect(controller.seek).toHaveBeenCalledWith(2_500_000);
  fireEvent.click(screen.getByRole("button", { name: "Pause" }));
  expect(controller.pause).toHaveBeenCalledOnce();
  expect(screen.getByText("Playback notes (1)")).toBeInTheDocument();

  unmount();
  expect(controller.dispose).toHaveBeenCalledOnce();
});

test("TEST-APP-PLAYBACK-009 announces demonstration completion once", () => {
  let observer: ((snapshot: PlaybackSnapshot) => void) | null = null;
  const onComplete = vi.fn();
  const controller: PlaybackController = {
    play: vi.fn(async () => undefined),
    pause: vi.fn(),
    restart: vi.fn(async () => undefined),
    stop: vi.fn(),
    seek: vi.fn(),
    dispose: vi.fn(),
  };
  const factory = vi.fn((_plan: PlaybackPlan, nextObserver: (snapshot: PlaybackSnapshot) => void) => {
    observer = nextObserver;
    return controller;
  });
  render(<PlaybackSurface plan={plan} controllerFactory={factory} onComplete={onComplete} />);

  const complete = {
    status: "complete",
    positionMicroseconds: 4_000_000,
    durationMicroseconds: 4_000_000,
    activeNoteIds: [],
    activeMidiPitches: [],
    activeNotes: [],
    focusEventIds: [],
    countInBeatsRemaining: 0,
    errorCode: null,
    errorMessage: null,
  } as PlaybackSnapshot;
  expect(observer).not.toBeNull();
  const emit = observer as unknown as (snapshot: PlaybackSnapshot) => void;
  emit(complete);
  emit(complete);

  expect(onComplete).toHaveBeenCalledOnce();
});
