import type { ViewerDiagnostic } from "./viewer";

export interface ExactFraction {
  numerator: number;
  denominator: number;
}

export interface PlaybackClef {
  sign: string;
  line: number | null;
  octave_change: number | null;
}

export interface PlaybackSourceEvent {
  event_id: string;
  part_id: string;
  measure_id: string;
  staff: string;
  voice: string;
  score_onset: ExactFraction;
  clef_group_id: string | null;
  clef: PlaybackClef | null;
}

export interface PlaybackNote {
  id: string;
  start_microseconds: number;
  end_microseconds: number;
  midi_pitch: number;
  chord_id: string | null;
  dynamic_percent: ExactFraction | null;
  source_events: PlaybackSourceEvent[];
}

export interface TempoControl {
  id: string;
  at_microseconds: number;
  quarter_notes_per_minute: ExactFraction;
  source_score_onset: ExactFraction;
  origin: "canonical" | "caller-fallback";
  source_part_id: string | null;
  source_measure_id: string | null;
  source_order: number | null;
}

export interface GraceRealization {
  event_id: string;
  anchor_event_ids: string[];
  relation: "following" | "previous";
  origin:
    | "source-make-time"
    | "source-steal-following"
    | "source-steal-previous"
    | "caller-fallback";
  duration_quarter_notes: ExactFraction;
  cluster_index: number;
  cluster_size: number;
}

export interface PlaybackMeasureVisit {
  visit_index: number;
  source_measure_index: number;
  source_measure_number: string;
  source_measure_ids: string[];
  source_score_onset: ExactFraction;
  start_microseconds: number;
  end_microseconds: number;
  entry_reason: "initial" | "sequential" | "repeat" | "jump" | "coda";
}

export interface PlaybackPlan {
  contract_id: "org.teachmemusic.playback-plan";
  contract_version: "0.2.0";
  package_id: string;
  score_id: string;
  canonical_schema_id: string;
  canonical_schema_version: string;
  duration_microseconds: number;
  navigation_section_starts: number[];
  notes: PlaybackNote[];
  tempo_controls: TempoControl[];
  grace_realizations: GraceRealization[];
  measure_visits: PlaybackMeasureVisit[];
  diagnostics: ViewerDiagnostic[];
}

export interface PlaybackContractIssue {
  code: string;
  path: string;
  message: string;
}

function isSafeNonNegativeInteger(value: number): boolean {
  return Number.isSafeInteger(value) && value >= 0;
}

export function validatePlaybackPlan(plan: PlaybackPlan): PlaybackContractIssue[] {
  const issues: PlaybackContractIssue[] = [];
  const add = (code: string, path: string, message: string) => {
    issues.push({ code, path, message });
  };

  if (plan.contract_id !== "org.teachmemusic.playback-plan") {
    add("AUDIO_CONTRACT_ID", "contract_id", "The playback contract ID is unsupported.");
  }
  if (plan.contract_version !== "0.2.0") {
    add("AUDIO_CONTRACT_VERSION", "contract_version", "The playback contract version is unsupported.");
  }
  if (!isSafeNonNegativeInteger(plan.duration_microseconds)) {
    add("AUDIO_DURATION", "duration_microseconds", "The playback duration is invalid.");
  }

  const ids = new Set<string>();
  let previous: [number, number, string] | null = null;
  plan.notes.forEach((note, index) => {
    const path = `notes[${index}]`;
    const key: [number, number, string] = [note.start_microseconds, note.midi_pitch, note.id];
    if (
      previous &&
      (key[0] < previous[0] ||
        (key[0] === previous[0] && key[1] < previous[1]) ||
        (key[0] === previous[0] && key[1] === previous[1] && key[2] < previous[2]))
    ) {
      add("AUDIO_NOTE_ORDER", path, "Playback notes are not deterministically ordered.");
    }
    previous = key;
    if (!note.id || ids.has(note.id)) {
      add("AUDIO_NOTE_ID", `${path}.id`, "The note ID is empty or repeated.");
    }
    ids.add(note.id);
    if (
      !isSafeNonNegativeInteger(note.start_microseconds) ||
      !Number.isSafeInteger(note.end_microseconds) ||
      note.end_microseconds <= note.start_microseconds ||
      note.end_microseconds > plan.duration_microseconds
    ) {
      add("AUDIO_NOTE_TIME", path, "The note time range is invalid.");
    }
    if (!Number.isInteger(note.midi_pitch) || note.midi_pitch < 0 || note.midi_pitch > 127) {
      add("AUDIO_MIDI_PITCH", `${path}.midi_pitch`, "The MIDI pitch is outside 0–127.");
    }
    if (note.source_events.length === 0 || note.source_events.some((source) => !source.event_id)) {
      add("AUDIO_NOTE_SOURCE", `${path}.source_events`, "The note has no canonical source identity.");
    }
    if (
      note.dynamic_percent &&
      (!Number.isSafeInteger(note.dynamic_percent.numerator) ||
        !Number.isSafeInteger(note.dynamic_percent.denominator) ||
        note.dynamic_percent.denominator <= 0 ||
        note.dynamic_percent.numerator < 0)
    ) {
      add("AUDIO_DYNAMICS", `${path}.dynamic_percent`, "The dynamic percentage is invalid.");
    }
  });
  return issues;
}

export function requireValidPlaybackPlan(plan: PlaybackPlan): void {
  const issue = validatePlaybackPlan(plan)[0];
  if (issue) throw new Error(`${issue.code} at ${issue.path}: ${issue.message}`);
}
