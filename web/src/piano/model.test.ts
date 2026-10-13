import type { ActivePlaybackNote } from "../audio/PlaybackTransport";
import { buildPianoState, classifyClef, midiNoteName } from "./model";

function activeNote(
  noteId: string,
  midiPitch: number,
  eventId: string,
  sign: string | null,
  line: number | null = null,
): ActivePlaybackNote {
  return {
    noteId,
    midiPitch,
    contributions: [{
      eventId,
      clefGroupId: sign ? `clef:${sign}:${line}` : null,
      clef: sign ? { sign, line, octave_change: null } : null,
      staff: "1",
      voice: "1",
    }],
  };
}

test("TEST-APP-PIANO-001 builds the standard 88-key range and names its boundaries", () => {
  const state = buildPianoState([]);
  expect(state.keys).toHaveLength(88);
  expect(state.keys[0]).toMatchObject({ midiPitch: 21, noteName: "A0", black: false });
  expect(state.keys.at(-1)).toMatchObject({ midiPitch: 108, noteName: "C8", black: false });
  expect(midiNoteName(61)).toBe("C♯4");
});

test("TEST-APP-PIANO-002 retains simultaneous canonical and multi-clef contributions", () => {
  const state = buildPianoState([
    activeNote("note:treble", 60, "event:treble", "G", 2),
    activeNote("note:bass", 60, "event:bass", "F", 4),
    activeNote("note:unknown", 64, "event:unknown", null),
    activeNote("note:outside", 10, "event:outside", "F", 4),
  ]);
  const middleC = state.keys.find((key) => key.midiPitch === 60);
  expect(middleC).toMatchObject({
    active: true,
    clefs: ["treble", "bass"],
    noteIds: ["note:treble", "note:bass"],
    canonicalEventIds: ["event:treble", "event:bass"],
  });
  expect(state.keys.find((key) => key.midiPitch === 64)?.clefs).toEqual(["unknown"]);
  expect(state.outOfRange.map((note) => note.noteId)).toEqual(["note:outside"]);
});

test("TEST-APP-PIANO-003 classifies written clefs without inventing hands", () => {
  expect(classifyClef({ sign: "G", line: 2, octave_change: null })).toBe("treble");
  expect(classifyClef({ sign: "F", line: 4, octave_change: null })).toBe("bass");
  expect(classifyClef({ sign: "C", line: 3, octave_change: null })).toBe("alto");
  expect(classifyClef({ sign: "C", line: 4, octave_change: null })).toBe("tenor");
  expect(classifyClef(null)).toBe("unknown");
});

test("TEST-APP-PIANO-007 combines expected and played pitches without replacing the target", () => {
  const state = buildPianoState(
    [
      activeNote("note:c", 60, "event:c", "G", 2),
      activeNote("note:e", 64, "event:e", "G", 2),
    ],
    [60, 62, 62, 10, 127, -1, 60.5],
  );

  expect(state.keys.find((key) => key.midiPitch === 60)).toMatchObject({
    active: true,
    played: true,
    match: true,
    differentFromTarget: false,
  });
  expect(state.keys.find((key) => key.midiPitch === 62)).toMatchObject({
    active: false,
    played: true,
    match: false,
    differentFromTarget: true,
  });
  expect(state.keys.find((key) => key.midiPitch === 64)).toMatchObject({
    active: true,
    played: false,
    match: false,
    differentFromTarget: false,
  });
  expect(state.playedOutOfRange).toEqual([10, 127]);

  const untargeted = buildPianoState([], [62]);
  expect(untargeted.keys.find((key) => key.midiPitch === 62)).toMatchObject({
    played: true,
    differentFromTarget: false,
  });
});
