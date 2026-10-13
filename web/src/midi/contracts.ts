export type MidiPermissionState =
  | "idle"
  | "requesting"
  | "granted"
  | "denied"
  | "unsupported"
  | "error";

export type MidiConnectionState = "disconnected" | "connecting" | "connected";

export type MidiCaptureState = "idle" | "recording" | "paused" | "stopped" | "aborted";
export type MidiCapturePurpose = "calibration" | "attempt" | null;

export type NormalizedMidiKind =
  | "note-on"
  | "note-off"
  | "control-change"
  | "connection"
  | "diagnostic";

export interface MidiInputSummary {
  id: string;
  name: string;
  manufacturer: string | null;
  state: "connected" | "disconnected";
  connection: "open" | "closed" | "pending";
}

export interface RawMidiMessage {
  id: string;
  sequence_number: number;
  timestamp_microseconds: number;
  data: number[];
}

export interface NormalizedMidiEvent {
  id: string;
  raw_message_id: string | null;
  kind: NormalizedMidiKind;
  timestamp_microseconds: number;
  channel: number | null;
  note: number | null;
  velocity: number | null;
  controller: number | null;
  value: number | null;
  detail: string | null;
}

export interface MidiDiagnostic {
  code: string;
  message: string;
  blocking: boolean;
  timestamp_microseconds: number;
}

export interface CalibrationRecord {
  contract_id: "org.teachmemusic.midi-calibration";
  contract_version: "0.1.0";
  id: string;
  version: "casio-browser-calibration-v1";
  created_at_utc: string;
  device_id: string;
  input_name: string;
  timestamp_origin: string;
  pitch_numbering_confirmed: boolean;
  sustain_available: boolean | null;
  clock_offset_microseconds: number | null;
  clock_jitter_microseconds: number | null;
  timing_window_microseconds: null;
  chord_window_microseconds: null;
  raw_message_count: number;
  normalized_event_count: number;
  note_on_count: number;
  first_note: number | null;
  limitations: string[];
  approved: boolean;
  approved_at_utc: string | null;
}

export interface MidiSnapshot {
  permission: MidiPermissionState;
  connection: MidiConnectionState;
  capture: MidiCaptureState;
  capture_purpose: MidiCapturePurpose;
  capture_started_at_utc: string | null;
  capture_start_microseconds: number | null;
  capture_end_microseconds: number | null;
  inputs: MidiInputSummary[];
  selected_input_id: string | null;
  raw_messages: RawMidiMessage[];
  normalized_events: NormalizedMidiEvent[];
  diagnostics: MidiDiagnostic[];
  active_notes: number[];
  calibration: CalibrationRecord | null;
}

export interface AttemptMidiSession {
  current(): MidiSnapshot;
  subscribe(listener: (snapshot: MidiSnapshot) => void): () => void;
  startAttempt(): void;
  stopAttempt(): void;
  pauseAttempt(): void;
  resumeAttempt(): void;
  abortAttempt(): void;
  stopAttemptForDiscomfort(): void;
}

export interface MidiMessageEventLike {
  data: Uint8Array | null;
  timeStamp: number;
}

export interface MidiInputLike {
  id: string;
  name: string | null;
  manufacturer: string | null;
  state: "connected" | "disconnected";
  connection: "open" | "closed" | "pending";
  type: "input";
  onmidimessage: ((event: MidiMessageEventLike) => void) | null;
  open(): Promise<MidiInputLike>;
  close(): Promise<MidiInputLike>;
}

export interface MidiAccessLike {
  inputs: ReadonlyMap<string, MidiInputLike>;
  onstatechange: ((event: { port: MidiInputLike }) => void) | null;
}

export type RequestMidiAccess = () => Promise<MidiAccessLike>;
