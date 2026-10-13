import { render, screen } from "@testing-library/react";

import type { ActivePlaybackNote } from "../audio/PlaybackTransport";
import { VirtualPiano } from "./VirtualPiano";

const activeNotes: ActivePlaybackNote[] = [
  {
    noteId: "note:treble",
    midiPitch: 60,
    contributions: [{
      eventId: "event:treble",
      clefGroupId: "clef:treble",
      clef: { sign: "G", line: 2, octave_change: null },
      staff: "1",
      voice: "1",
    }],
  },
  {
    noteId: "note:bass",
    midiPitch: 60,
    contributions: [{
      eventId: "event:bass",
      clefGroupId: "clef:bass",
      clef: { sign: "F", line: 4, octave_change: null },
      staff: "2",
      voice: "1",
    }],
  },
  {
    noteId: "note:e",
    midiPitch: 64,
    contributions: [{
      eventId: "event:e",
      clefGroupId: null,
      clef: null,
      staff: "1",
      voice: "2",
    }],
  },
];

test("TEST-APP-PIANO-004 renders accessible active keys, clef overlap, and trace IDs", () => {
  const { container } = render(<VirtualPiano activeNotes={activeNotes} />);
  expect(container.querySelectorAll("[data-midi]")).toHaveLength(88);
  expect(screen.getByText("2 keys sounding: C4, E4")).toBeInTheDocument();
  expect(
    screen.getByRole("img", {
      name: "C4, expected sounding, treble clef and bass clef, 2 canonical events",
    }),
  ).toHaveAttribute("data-clefs", "treble,bass");
  expect(
    screen.getByRole("img", {
      name: "E4, expected sounding, clef not specified, 1 canonical event",
    }),
  ).toHaveAttribute("data-clefs", "unknown");
  expect(screen.getByText(/not a guessed left or right hand/)).toBeInTheDocument();
  expect(screen.getByText("Active canonical events (3)")).toBeInTheDocument();
});

test("TEST-APP-PIANO-005 clears all keys when audio is not sounding", () => {
  const { container, rerender } = render(<VirtualPiano activeNotes={activeNotes} />);
  rerender(<VirtualPiano activeNotes={[]} />);
  expect(screen.getByText("No piano keys sounding")).toBeInTheDocument();
  expect(container.querySelectorAll('[data-active="true"]')).toHaveLength(0);
});

test("TEST-APP-PIANO-006 removes visual note-name support without reducing accessibility", () => {
  const { container } = render(
    <VirtualPiano activeNotes={activeNotes} showNoteNames={false} />,
  );
  expect(container.querySelectorAll(".piano-note-name")).toHaveLength(0);
  expect(
    screen.getByRole("img", {
      name: "C4, expected sounding, treble clef and bass clef, 2 canonical events",
    }),
  ).toBeInTheDocument();
});

test("TEST-APP-PIANO-008 keeps the correct target visible beside matches and different notes", () => {
  const { container, rerender } = render(
    <VirtualPiano
      activeNotes={activeNotes}
      playedMidiPitches={[60, 62]}
      learnerInputStatus="capturing"
    />,
  );

  const match = container.querySelector('[data-midi="60"]');
  const different = container.querySelector('[data-midi="62"]');
  const untouchedTarget = container.querySelector('[data-midi="64"]');
  expect(match).toHaveAttribute("data-expected", "true");
  expect(match).toHaveAttribute("data-played", "true");
  expect(match).toHaveAttribute("data-match", "true");
  expect(match).toHaveTextContent("✓");
  expect(different).toHaveAttribute("data-expected", "false");
  expect(different).toHaveAttribute("data-played", "true");
  expect(different).toHaveAttribute("data-different-from-target", "true");
  expect(different).toHaveTextContent("!");
  expect(untouchedTarget).toHaveAttribute("data-expected", "true");
  expect(untouchedTarget).toHaveAttribute("data-played", "false");
  expect(untouchedTarget).toHaveTextContent("◇");
  expect(screen.getByText(/Learner playing: C4, D4; 1 match; different from current target: D4/)).toBeInTheDocument();

  rerender(
    <VirtualPiano
      activeNotes={[]}
      playedMidiPitches={[62]}
      learnerInputStatus="connected"
    />,
  );
  const untargetedPlayed = container.querySelector('[data-midi="62"]');
  expect(untargetedPlayed).toHaveAttribute("data-played", "true");
  expect(untargetedPlayed).toHaveAttribute("data-different-from-target", "false");
  expect(untargetedPlayed).toHaveTextContent("●");
  expect(screen.getByRole("img", { name: "D4, learner played, no current target" })).toBeInTheDocument();
});
