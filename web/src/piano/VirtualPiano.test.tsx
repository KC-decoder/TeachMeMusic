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
      name: "C4, sounding, treble clef and bass clef, 2 canonical events",
    }),
  ).toHaveAttribute("data-clefs", "treble,bass");
  expect(
    screen.getByRole("img", {
      name: "E4, sounding, clef not specified, 1 canonical event",
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
