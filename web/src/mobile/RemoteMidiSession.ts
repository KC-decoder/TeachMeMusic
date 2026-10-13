import type { AttemptResult } from "../api";
import type {
  AttemptMidiSession,
  CalibrationRecord,
  MidiDiagnostic,
  MidiSnapshot,
} from "../midi/contracts";
import type { MobileAttemptContext, MobileCompanionState } from "./transport";
import { MobileCompanionSession, type MobileCommand, type MobileCommandKind } from "./transport";

const remoteCalibration: CalibrationRecord = {
  contract_id: "org.teachmemusic.midi-calibration",
  contract_version: "0.1.0",
  id: "calibration:paired-desktop",
  version: "casio-browser-calibration-v1",
  created_at_utc: "",
  device_id: "paired-desktop-midi",
  input_name: "Paired desktop MIDI",
  timestamp_origin: "desktop-browser",
  pitch_numbering_confirmed: true,
  sustain_available: null,
  clock_offset_microseconds: null,
  clock_jitter_microseconds: null,
  timing_window_microseconds: null,
  chord_window_microseconds: null,
  raw_message_count: 0,
  normalized_event_count: 0,
  note_on_count: 0,
  first_note: null,
  limitations: ["Complete performance evidence remains on the paired desktop."],
  approved: true,
  approved_at_utc: "paired-desktop",
};

function emptySnapshot(): MidiSnapshot {
  return {
    permission: "granted",
    connection: "disconnected",
    capture: "idle",
    capture_purpose: null,
    capture_started_at_utc: null,
    capture_start_microseconds: null,
    capture_end_microseconds: null,
    inputs: [],
    selected_input_id: null,
    raw_messages: [],
    normalized_events: [],
    diagnostics: [],
    active_notes: [],
    calibration: null,
  };
}

export class RemoteMidiSession implements AttemptMidiSession {
  private snapshot = emptySnapshot();
  private listeners = new Set<(snapshot: MidiSnapshot) => void>();
  private timer: ReturnType<typeof setInterval> | null = null;
  private commandError: MidiDiagnostic | null = null;

  constructor(
    private readonly companion: MobileCompanionSession,
    private readonly pollMilliseconds = 200,
  ) {}

  current(): MidiSnapshot {
    return this.snapshot;
  }

  subscribe(listener: (snapshot: MidiSnapshot) => void): () => void {
    this.listeners.add(listener);
    listener(this.snapshot);
    if (this.timer === null) {
      void this.refresh();
      this.timer = setInterval(() => void this.refresh(), this.pollMilliseconds);
    }
    return () => {
      this.listeners.delete(listener);
      if (this.listeners.size === 0 && this.timer !== null) {
        clearInterval(this.timer);
        this.timer = null;
      }
    };
  }

  startAttempt(): void {
    this.send("start-attempt");
  }

  stopAttempt(): void {
    this.send("finish-attempt");
  }

  pauseAttempt(): void {
    this.send("pause-attempt");
  }

  resumeAttempt(): void {
    this.send("resume-attempt");
  }

  abortAttempt(): void {
    this.send("abort-attempt");
  }

  stopAttemptForDiscomfort(): void {
    this.send("safe-stop");
  }

  async submitAttempt(context: MobileAttemptContext): Promise<AttemptResult> {
    const command = await this.companion.requestAndWait("submit-attempt", context, {
      attempts: 150,
      intervalMilliseconds: this.pollMilliseconds,
    });
    if (command.status === "failed") {
      throw new Error(command.error ?? "The paired desktop could not submit the attempt.");
    }
    if (!command.result || typeof command.result !== "object") {
      throw new Error("The paired desktop returned no authoritative attempt result.");
    }
    await this.refresh();
    return command.result as AttemptResult;
  }

  async refresh(): Promise<void> {
    try {
      const state = await this.companion.read();
      this.applyState(state);
    } catch (error) {
      this.commandError = {
        code: "MOBILE_BRIDGE_UNAVAILABLE",
        message: error instanceof Error ? error.message : "The paired desktop is unavailable.",
        blocking: true,
        timestamp_microseconds: Math.round(performance.now() * 1000),
      };
      this.snapshot = {
        ...this.snapshot,
        connection: "disconnected",
        active_notes: [],
        diagnostics: [this.commandError],
      };
      this.emit();
    }
  }

  dispose(): void {
    if (this.timer !== null) clearInterval(this.timer);
    this.timer = null;
    this.listeners.clear();
  }

  private send(kind: Exclude<MobileCommandKind, "submit-attempt">): void {
    this.commandError = null;
    void this.companion.requestAndWait(kind).then(
      async (command) => {
        if (command.status === "failed") {
          throw new Error(command.error ?? "The paired desktop rejected the command.");
        }
        await this.refresh();
        this.applyCommandResult(command);
      },
      (error: unknown) => {
        this.applyCommandError(error);
      },
    ).catch((error: unknown) => this.applyCommandError(error));
  }

  private applyCommandResult(command: MobileCommand): void {
    if (!command.result || typeof command.result !== "object") return;
    const result = command.result as {
      capture?: MidiSnapshot["capture"];
      capture_purpose?: MidiSnapshot["capture_purpose"];
      calibration_approved?: boolean;
    };
    const captureStates: MidiSnapshot["capture"][] = [
      "idle", "recording", "paused", "stopped", "aborted",
    ];
    if (!result.capture || !captureStates.includes(result.capture)) return;
    this.commandError = null;
    this.snapshot = {
      ...this.snapshot,
      capture: result.capture,
      capture_purpose: result.capture_purpose === "attempt"
        ? "attempt"
        : this.snapshot.capture_purpose,
      calibration: result.calibration_approved === true
        ? remoteCalibration
        : this.snapshot.calibration,
      diagnostics: [],
    };
    this.emit();
  }

  private applyCommandError(error: unknown): void {
    this.commandError = {
      code: "MOBILE_COMMAND_FAILED",
      message: error instanceof Error ? error.message : "The desktop command failed.",
      blocking: true,
      timestamp_microseconds: Math.round(performance.now() * 1000),
    };
    this.snapshot = { ...this.snapshot, diagnostics: [this.commandError] };
    this.emit();
  }

  private applyState(state: MobileCompanionState): void {
    const connected = state.availability === "live";
    this.snapshot = {
      ...this.snapshot,
      connection: connected ? "connected" : "disconnected",
      capture: connected ? state.capture : "idle",
      capture_purpose: connected ? state.capture_purpose : null,
      active_notes: connected ? state.active_notes : [],
      calibration: connected && state.calibration_approved ? remoteCalibration : null,
      diagnostics: this.commandError ? [this.commandError] : [],
    };
    this.emit();
  }

  private emit(): void {
    for (const listener of this.listeners) listener(this.snapshot);
  }
}
