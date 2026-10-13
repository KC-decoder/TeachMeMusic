import type { ActivePlaybackNote } from "../audio/PlaybackTransport";
import type { PlaybackClef } from "../contracts/playback";

export const PIANO_MIN_MIDI = 21;
export const PIANO_MAX_MIDI = 108;

export type ClefCategory =
  | "treble"
  | "bass"
  | "alto"
  | "tenor"
  | "percussion"
  | "tab"
  | "other"
  | "unknown";

export interface PianoKeyState {
  midiPitch: number;
  noteName: string;
  black: boolean;
  active: boolean;
  played: boolean;
  match: boolean;
  differentFromTarget: boolean;
  clefs: ClefCategory[];
  noteIds: string[];
  canonicalEventIds: string[];
}

export interface PianoState {
  keys: PianoKeyState[];
  outOfRange: ActivePlaybackNote[];
  playedOutOfRange: number[];
}

const PITCH_NAMES = ["C", "C♯", "D", "E♭", "E", "F", "F♯", "G", "A♭", "A", "B♭", "B"];
const BLACK_PITCH_CLASSES = new Set([1, 3, 6, 8, 10]);
const CLEF_ORDER: ClefCategory[] = [
  "treble",
  "bass",
  "alto",
  "tenor",
  "percussion",
  "tab",
  "other",
  "unknown",
];

export const CLEF_LABELS: Record<ClefCategory, string> = {
  treble: "treble clef",
  bass: "bass clef",
  alto: "alto clef",
  tenor: "tenor clef",
  percussion: "percussion clef",
  tab: "tablature clef",
  other: "other clef",
  unknown: "clef not specified",
};

export function midiNoteName(midiPitch: number): string {
  const pitchClass = PITCH_NAMES[midiPitch % 12];
  if (!pitchClass || !Number.isInteger(midiPitch) || midiPitch < 0 || midiPitch > 127) {
    throw new Error("MIDI pitch is outside 0–127");
  }
  return `${pitchClass}${Math.floor(midiPitch / 12) - 1}`;
}

export function classifyClef(clef: PlaybackClef | null): ClefCategory {
  if (!clef) return "unknown";
  const sign = clef.sign.trim().toUpperCase();
  if (sign === "G") return "treble";
  if (sign === "F") return "bass";
  if (sign === "C" && clef.line === 3) return "alto";
  if (sign === "C" && clef.line === 4) return "tenor";
  if (sign === "PERCUSSION") return "percussion";
  if (sign === "TAB") return "tab";
  return "other";
}

function orderedClefs(clefs: Set<ClefCategory>): ClefCategory[] {
  return CLEF_ORDER.filter((clef) => clefs.has(clef));
}

export function buildPianoState(
  activeNotes: ActivePlaybackNote[],
  playedMidiPitches: readonly number[] = [],
): PianoState {
  const byPitch = new Map<
    number,
    { noteIds: Set<string>; eventIds: Set<string>; clefs: Set<ClefCategory> }
  >();
  const outOfRange: ActivePlaybackNote[] = [];
  for (const note of activeNotes) {
    if (note.midiPitch < PIANO_MIN_MIDI || note.midiPitch > PIANO_MAX_MIDI) {
      outOfRange.push(note);
      continue;
    }
    const value = byPitch.get(note.midiPitch) ?? {
      noteIds: new Set<string>(),
      eventIds: new Set<string>(),
      clefs: new Set<ClefCategory>(),
    };
    value.noteIds.add(note.noteId);
    for (const contribution of note.contributions) {
      value.eventIds.add(contribution.eventId);
      value.clefs.add(classifyClef(contribution.clef));
    }
    if (note.contributions.length === 0) value.clefs.add("unknown");
    byPitch.set(note.midiPitch, value);
  }

  const playedByPitch = new Set<number>();
  const playedOutOfRange = new Set<number>();
  for (const midiPitch of playedMidiPitches) {
    if (!Number.isInteger(midiPitch) || midiPitch < 0 || midiPitch > 127) continue;
    if (midiPitch < PIANO_MIN_MIDI || midiPitch > PIANO_MAX_MIDI) {
      playedOutOfRange.add(midiPitch);
    } else {
      playedByPitch.add(midiPitch);
    }
  }
  const hasExpectedTarget = byPitch.size > 0;

  const keys: PianoKeyState[] = [];
  for (let midiPitch = PIANO_MIN_MIDI; midiPitch <= PIANO_MAX_MIDI; midiPitch += 1) {
    const active = byPitch.get(midiPitch);
    const played = playedByPitch.has(midiPitch);
    keys.push({
      midiPitch,
      noteName: midiNoteName(midiPitch),
      black: BLACK_PITCH_CLASSES.has(midiPitch % 12),
      active: active !== undefined,
      played,
      match: active !== undefined && played,
      differentFromTarget: hasExpectedTarget && active === undefined && played,
      clefs: active ? orderedClefs(active.clefs) : [],
      noteIds: active ? [...active.noteIds] : [],
      canonicalEventIds: active ? [...active.eventIds] : [],
    });
  }
  return { keys, outOfRange, playedOutOfRange: [...playedOutOfRange].sort((a, b) => a - b) };
}
