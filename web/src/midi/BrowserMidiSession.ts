import type {
  CalibrationRecord,
  MidiAccessLike,
  MidiDiagnostic,
  MidiInputLike,
  MidiSnapshot,
  NormalizedMidiEvent,
  RawMidiMessage,
  RequestMidiAccess,
} from "./contracts";
import { normalizeMidiMessage } from "./normalize";

export interface MidiClock {
  nowMilliseconds(): number;
  timeOriginMilliseconds(): number;
  nowUtc(): string;
}

const browserClock: MidiClock = {
  nowMilliseconds: () => performance.now(),
  timeOriginMilliseconds: () => performance.timeOrigin,
  nowUtc: () => new Date().toISOString(),
};

function browserRequest(): RequestMidiAccess | null {
  const navigatorWithMidi = navigator as unknown as {
    requestMIDIAccess?: (options?: { sysex?: boolean }) => Promise<MidiAccessLike>;
  };
  if (!navigatorWithMidi.requestMIDIAccess) return null;
  return () => navigatorWithMidi.requestMIDIAccess!({ sysex: false });
}

function emptySnapshot(permission: MidiSnapshot["permission"]): MidiSnapshot {
  return {
    permission,
    connection: "disconnected",
    capture: "idle",
    inputs: [],
    selected_input_id: null,
    raw_messages: [],
    normalized_events: [],
    diagnostics: [],
    active_notes: [],
    calibration: null,
  };
}

function mean(values: number[]): number | null {
  if (values.length === 0) return null;
  return Math.round(values.reduce((sum, value) => sum + value, 0) / values.length);
}

export class BrowserMidiSession {
  private access: MidiAccessLike | null = null;
  private selectedInput: MidiInputLike | null = null;
  private snapshot: MidiSnapshot;
  private listeners = new Set<(snapshot: MidiSnapshot) => void>();
  private sequence = 0;
  private clockOffsets: number[] = [];

  constructor(
    private readonly requestAccess: RequestMidiAccess | null = browserRequest(),
    private readonly clock: MidiClock = browserClock,
  ) {
    this.snapshot = emptySnapshot(requestAccess ? "idle" : "unsupported");
  }

  current(): MidiSnapshot {
    return this.snapshot;
  }

  subscribe(listener: (snapshot: MidiSnapshot) => void): () => void {
    this.listeners.add(listener);
    listener(this.snapshot);
    return () => this.listeners.delete(listener);
  }

  async requestPermission(): Promise<void> {
    if (!this.requestAccess) {
      this.patch({ permission: "unsupported" });
      return;
    }
    this.patch({ permission: "requesting" });
    try {
      this.access = await this.requestAccess();
      this.access.onstatechange = () => this.refreshInputs();
      this.patch({ permission: "granted" });
      this.refreshInputs();
    } catch (error) {
      const denied = error instanceof DOMException && error.name === "SecurityError";
      this.patch({ permission: denied ? "denied" : "error" });
      this.addDiagnostic(
        denied ? "MIDI_PERMISSION_DENIED" : "MIDI_ACCESS_FAILED",
        denied
          ? "MIDI permission was denied. No learner input is being captured."
          : "The browser could not open Web MIDI. No learner input is being captured.",
        true,
      );
    }
  }

  async connect(inputId: string): Promise<void> {
    const input = this.access?.inputs.get(inputId);
    if (!input || input.state !== "connected") {
      this.addDiagnostic("MIDI_INPUT_UNAVAILABLE", "The selected MIDI input is unavailable.", true);
      return;
    }
    if (this.selectedInput && this.selectedInput.id !== inputId) await this.disconnect();
    this.patch({ connection: "connecting", selected_input_id: inputId });
    try {
      this.selectedInput = await input.open();
      this.selectedInput.onmidimessage = (message) => this.receive(message.data, message.timeStamp);
      this.patch({ connection: "connected", selected_input_id: inputId });
      this.addConnectionEvent("connected");
      this.refreshInputs();
    } catch {
      this.selectedInput = null;
      this.patch({ connection: "disconnected", selected_input_id: inputId });
      this.addDiagnostic("MIDI_INPUT_OPEN_FAILED", "The selected MIDI input could not be opened.", true);
    }
  }

  async disconnect(): Promise<void> {
    const input = this.selectedInput;
    if (input) {
      input.onmidimessage = null;
      try {
        await input.close();
      } catch {
        this.addDiagnostic("MIDI_INPUT_CLOSE_FAILED", "The MIDI input did not close cleanly.", false);
      }
    }
    this.selectedInput = null;
    this.addConnectionEvent("disconnected");
    const activeCapture = this.snapshot.capture === "recording" ||
      this.snapshot.capture === "paused";
    this.patch({
      connection: "disconnected",
      capture: activeCapture ? "aborted" : this.snapshot.capture,
      active_notes: [],
    });
    this.refreshInputs();
  }

  startCalibration(): void {
    if (this.snapshot.connection !== "connected" || !this.selectedInput) {
      this.addDiagnostic("MIDI_CALIBRATION_NO_INPUT", "Connect a MIDI input before calibration.", true);
      return;
    }
    this.sequence = 0;
    this.clockOffsets = [];
    this.patch({
      capture: "recording",
      raw_messages: [],
      normalized_events: [],
      diagnostics: [],
      active_notes: [],
      calibration: null,
    });
  }

  stopCalibration(): void {
    if (this.snapshot.capture !== "recording" && this.snapshot.capture !== "paused") return;
    const calibration = this.buildCalibration(false);
    this.patch({ capture: "stopped", active_notes: [], calibration });
  }

  abortCalibration(): void {
    if (this.snapshot.capture !== "recording" && this.snapshot.capture !== "paused") return;
    this.patch({ capture: "aborted", active_notes: [], calibration: null });
  }

  pauseCalibration(): void {
    if (this.snapshot.capture !== "recording") return;
    this.patch({ capture: "paused", active_notes: [] });
  }

  resumeCalibration(): void {
    if (this.snapshot.capture !== "paused") return;
    this.patch({ capture: "recording" });
  }

  stopForDiscomfort(): void {
    if (this.snapshot.capture !== "recording" && this.snapshot.capture !== "paused") return;
    this.addDiagnostic(
      "LEARNER_DISCOMFORT_SAFE_STOP",
      "The learner reported discomfort. Capture stopped without a learner score or penalty.",
      false,
    );
    this.patch({ capture: "aborted", active_notes: [], calibration: null });
  }

  approveCalibration(): void {
    const current = this.snapshot.calibration;
    if (!current || !current.pitch_numbering_confirmed || current.raw_message_count === 0) return;
    this.patch({
      calibration: {
        ...current,
        approved: true,
        approved_at_utc: this.clock.nowUtc(),
      },
    });
  }

  dispose(): void {
    if (this.access) this.access.onstatechange = null;
    if (this.selectedInput) {
      this.selectedInput.onmidimessage = null;
      void this.selectedInput.close().catch(() => undefined);
    }
    this.listeners.clear();
  }

  private receive(data: Uint8Array | null, eventTimestampMilliseconds: number): void {
    if (this.snapshot.capture !== "recording") return;
    const receivedMilliseconds = this.clock.nowMilliseconds();
    if (!data || data.length === 0) {
      this.addDiagnostic("MIDI_EMPTY_MESSAGE", "An empty MIDI message was received.", false);
      return;
    }
    this.sequence += 1;
    const raw: RawMidiMessage = {
      id: `raw-midi:${this.sequence}`,
      sequence_number: this.sequence,
      timestamp_microseconds: Math.round(eventTimestampMilliseconds * 1000),
      data: Array.from(data),
    };
    const normalized = normalizeMidiMessage(raw);
    this.clockOffsets.push(Math.round((receivedMilliseconds - eventTimestampMilliseconds) * 1000));
    const active = new Set(this.snapshot.active_notes);
    const diagnostics = [...this.snapshot.diagnostics];
    if (normalized.kind === "note-on" && normalized.note !== null) {
      if (active.has(normalized.note)) {
        diagnostics.push({
          code: "MIDI_DUPLICATE_NOTE_ON",
          message: `A second note-on arrived for MIDI ${normalized.note} before a note-off.`,
          blocking: false,
          timestamp_microseconds: raw.timestamp_microseconds,
        });
      }
      active.add(normalized.note);
    }
    if (normalized.kind === "note-off" && normalized.note !== null) {
      if (!active.has(normalized.note)) {
        diagnostics.push({
          code: "MIDI_UNMATCHED_NOTE_OFF",
          message: `A note-off arrived for inactive MIDI ${normalized.note}.`,
          blocking: false,
          timestamp_microseconds: raw.timestamp_microseconds,
        });
      }
      active.delete(normalized.note);
    }
    if (normalized.kind === "diagnostic") {
      diagnostics.push({
        code: normalized.detail ?? "MIDI_UNINTERPRETED_MESSAGE",
        message: "A raw MIDI message was retained but could not be interpreted as a supported event.",
        blocking: false,
        timestamp_microseconds: raw.timestamp_microseconds,
      });
    }
    this.patch({
      raw_messages: [...this.snapshot.raw_messages, raw],
      normalized_events: [...this.snapshot.normalized_events, normalized],
      diagnostics,
      active_notes: [...active].sort((left, right) => left - right),
    });
  }

  private refreshInputs(): void {
    if (!this.access) return;
    const inputs = [...this.access.inputs.values()]
      .map((input) => ({
        id: input.id,
        name: input.name?.trim() || "Unnamed MIDI input",
        manufacturer: input.manufacturer?.trim() || null,
        state: input.state,
        connection: input.connection,
      }))
      .sort((left, right) => left.name.localeCompare(right.name));
    const selected = this.selectedInput;
    if (selected && selected.state === "disconnected") {
      const activeCapture = this.snapshot.capture === "recording" ||
        this.snapshot.capture === "paused";
      selected.onmidimessage = null;
      this.selectedInput = null;
      this.addDiagnostic(
        "MIDI_INPUT_DISCONNECTED",
        activeCapture
          ? "The MIDI input disconnected. The current capture is invalid and was stopped."
          : "The MIDI input disconnected after capture ended. Completed evidence was retained.",
        activeCapture,
      );
      this.addConnectionEvent("disconnected-unexpectedly");
      this.patch({
        connection: "disconnected",
        capture: activeCapture ? "aborted" : this.snapshot.capture,
        active_notes: [],
      });
    }
    this.patch({ inputs });
  }

  private addConnectionEvent(detail: string): void {
    if (this.snapshot.capture !== "recording") return;
    const timestamp = Math.round(this.clock.nowMilliseconds() * 1000);
    const connectionEvent: NormalizedMidiEvent = {
      id: `midi-event:connection:${this.sequence + 1}`,
      raw_message_id: null,
      kind: "connection",
      timestamp_microseconds: timestamp,
      channel: null,
      note: null,
      velocity: null,
      controller: null,
      value: null,
      detail,
    };
    this.patch({ normalized_events: [...this.snapshot.normalized_events, connectionEvent] });
  }

  private addDiagnostic(code: string, message: string, blocking: boolean): void {
    const diagnostic: MidiDiagnostic = {
      code,
      message,
      blocking,
      timestamp_microseconds: Math.round(this.clock.nowMilliseconds() * 1000),
    };
    this.patch({ diagnostics: [...this.snapshot.diagnostics, diagnostic] });
  }

  private buildCalibration(approved: boolean): CalibrationRecord {
    const noteOns = this.snapshot.normalized_events.filter((item) => item.kind === "note-on");
    const firstNote = noteOns[0]?.note ?? null;
    const sustainObserved = this.snapshot.normalized_events.some(
      (item) => item.kind === "control-change" && item.controller === 64,
    );
    const averageOffset = mean(this.clockOffsets);
    const jitter = this.clockOffsets.length > 1
      ? Math.max(...this.clockOffsets) - Math.min(...this.clockOffsets)
      : null;
    const device = this.snapshot.inputs.find((item) => item.id === this.snapshot.selected_input_id);
    return {
      contract_id: "org.teachmemusic.midi-calibration",
      contract_version: "0.1.0",
      id: `calibration:${device?.id ?? "unknown"}:${this.clock.nowUtc()}`,
      version: "casio-browser-calibration-v1",
      created_at_utc: this.clock.nowUtc(),
      device_id: device?.id ?? "unknown",
      input_name: device?.name ?? "Unknown MIDI input",
      timestamp_origin: `DOMHighResTimeStamp relative to performance.timeOrigin=${this.clock.timeOriginMilliseconds()}ms`,
      pitch_numbering_confirmed: firstNote === 60,
      sustain_available: sustainObserved ? true : null,
      clock_offset_microseconds: averageOffset,
      clock_jitter_microseconds: jitter,
      timing_window_microseconds: null,
      chord_window_microseconds: null,
      raw_message_count: this.snapshot.raw_messages.length,
      normalized_event_count: this.snapshot.normalized_events.length,
      note_on_count: noteOns.length,
      first_note: firstNote,
      limitations: [
        "This browser-only calibration cannot measure physical key-to-sound or acoustic latency.",
        "No timing or chord comparison window is approved by this calibration.",
        ...(sustainObserved ? [] : ["No sustain-controller message was observed; pedal support is unknown."]),
      ],
      approved,
      approved_at_utc: null,
    };
  }

  private patch(values: Partial<MidiSnapshot>): void {
    this.snapshot = { ...this.snapshot, ...values };
    for (const listener of this.listeners) listener(this.snapshot);
  }
}
