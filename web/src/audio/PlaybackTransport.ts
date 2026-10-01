import type { PlaybackClef, PlaybackNote, PlaybackPlan } from "../contracts/playback";
import { requireValidPlaybackPlan } from "../contracts/playback";

const LOOKAHEAD_MICROSECONDS = 2_000_000;
const SCHEDULER_INTERVAL_MILLISECONDS = 250;
const START_DELAY_SECONDS = 0.05;
const DEFAULT_VELOCITY = 0.72;

export type PlaybackStatus =
  | "idle"
  | "loading"
  | "playing"
  | "paused"
  | "complete"
  | "error";

export interface PlaybackSnapshot {
  status: PlaybackStatus;
  positionMicroseconds: number;
  durationMicroseconds: number;
  activeNoteIds: string[];
  activeMidiPitches: number[];
  activeNotes: ActivePlaybackNote[];
  focusEventIds: string[];
  countInBeatsRemaining: number;
  errorCode: string | null;
  errorMessage: string | null;
}

export interface ActivePlaybackContribution {
  eventId: string;
  clefGroupId: string | null;
  clef: PlaybackClef | null;
  staff: string;
  voice: string;
}

export interface ActivePlaybackNote {
  noteId: string;
  midiPitch: number;
  contributions: ActivePlaybackContribution[];
}

export interface PlaybackAudioEngine {
  activate(): Promise<void>;
  nowSeconds(): number;
  schedule(
    midiPitch: number,
    atSeconds: number,
    durationSeconds: number,
    velocity: number,
  ): void;
  scheduleClick(atSeconds: number, accented: boolean): void;
  releaseAll(): void;
  dispose(): void;
}

export interface PlaybackRuntime {
  setInterval(callback: () => void, milliseconds: number): number;
  clearInterval(handle: number): void;
  requestFrame(callback: () => void): number;
  cancelFrame(handle: number): void;
}

export interface PlaybackController {
  play(): Promise<void>;
  pause(): void;
  restart(): Promise<void>;
  stop(): void;
  seek(positionMicroseconds: number): void;
  dispose(): void;
}

export interface CountInSpec {
  beats: number;
  beatMicroseconds: number;
}

const browserRuntime: PlaybackRuntime = {
  setInterval: (callback, milliseconds) => globalThis.setInterval(callback, milliseconds),
  clearInterval: (handle) => globalThis.clearInterval(handle),
  requestFrame: (callback) => globalThis.requestAnimationFrame(callback),
  cancelFrame: (handle) => globalThis.cancelAnimationFrame(handle),
};

function velocityFor(note: PlaybackNote): number {
  const dynamic = note.dynamic_percent;
  if (!dynamic) return DEFAULT_VELOCITY;
  return Math.max(0.05, Math.min(1, dynamic.numerator / dynamic.denominator / 100));
}

function unique<T>(values: T[]): T[] {
  return [...new Set(values)];
}

export class PlaybackTransport implements PlaybackController {
  private status: PlaybackStatus = "idle";
  private positionMicroseconds = 0;
  private positionAnchorMicroseconds = 0;
  private audioAnchorSeconds = 0;
  private nextNoteIndex = 0;
  private schedulerHandle: number | null = null;
  private frameHandle: number | null = null;
  private actionGeneration = 0;
  private disposed = false;

  constructor(
    private readonly plan: PlaybackPlan,
    private readonly engine: PlaybackAudioEngine,
    private readonly onSnapshot: (snapshot: PlaybackSnapshot) => void,
    private readonly runtime: PlaybackRuntime = browserRuntime,
    private readonly countIn: CountInSpec | null = null,
  ) {
    requireValidPlaybackPlan(plan);
    this.emit();
  }

  async play(): Promise<void> {
    if (this.disposed || this.status === "playing" || this.status === "loading") return;
    if (this.positionMicroseconds >= this.plan.duration_microseconds) {
      this.positionMicroseconds = 0;
    }
    const generation = ++this.actionGeneration;
    this.status = "loading";
    this.emit();
    try {
      await this.engine.activate();
    } catch {
      if (generation !== this.actionGeneration || this.disposed) return;
      this.status = "error";
      this.emit(
        "AUDIO_SAMPLE_LOAD_FAILED",
        "The local piano samples could not be loaded. Playback did not start.",
      );
      return;
    }
    if (generation !== this.actionGeneration || this.disposed) return;
    this.startClock();
  }

  pause(): void {
    if (this.disposed || (this.status !== "playing" && this.status !== "loading")) return;
    ++this.actionGeneration;
    if (this.status === "playing") this.positionMicroseconds = this.currentPosition();
    this.cancelScheduledAudio();
    this.status = "paused";
    this.emit();
  }

  async restart(): Promise<void> {
    if (this.disposed) return;
    ++this.actionGeneration;
    this.cancelScheduledAudio();
    this.positionMicroseconds = 0;
    this.status = "idle";
    this.emit();
    await this.play();
  }

  stop(): void {
    if (this.disposed) return;
    ++this.actionGeneration;
    this.cancelScheduledAudio();
    this.positionMicroseconds = 0;
    this.status = "idle";
    this.emit();
  }

  seek(positionMicroseconds: number): void {
    if (this.disposed || !Number.isFinite(positionMicroseconds)) return;
    const wasPlaying = this.status === "playing";
    ++this.actionGeneration;
    this.cancelScheduledAudio();
    this.positionMicroseconds = Math.round(
      Math.max(0, Math.min(this.plan.duration_microseconds, positionMicroseconds)),
    );
    if (this.positionMicroseconds === this.plan.duration_microseconds) {
      this.status = "complete";
    } else if (wasPlaying) {
      this.startClock();
      return;
    } else {
      this.status = this.positionMicroseconds === 0 ? "idle" : "paused";
    }
    this.emit();
  }

  dispose(): void {
    if (this.disposed) return;
    ++this.actionGeneration;
    this.cancelScheduledAudio();
    this.engine.dispose();
    this.disposed = true;
  }

  private startClock(): void {
    this.positionAnchorMicroseconds = this.positionMicroseconds;
    const countInStart = this.engine.nowSeconds() + START_DELAY_SECONDS;
    const countInSeconds = this.countIn
      ? (this.countIn.beats * this.countIn.beatMicroseconds) / 1_000_000
      : 0;
    this.audioAnchorSeconds = countInStart + countInSeconds;
    if (this.countIn && this.positionMicroseconds === 0) {
      for (let beat = 0; beat < this.countIn.beats; beat += 1) {
        this.engine.scheduleClick(
          countInStart + (beat * this.countIn.beatMicroseconds) / 1_000_000,
          beat === 0,
        );
      }
    }
    this.nextNoteIndex = this.plan.notes.findIndex(
      (note) => note.end_microseconds > this.positionMicroseconds,
    );
    if (this.nextNoteIndex < 0) this.nextNoteIndex = this.plan.notes.length;
    this.status = "playing";
    this.scheduleWindow();
    this.schedulerHandle = this.runtime.setInterval(
      () => this.scheduleWindow(),
      SCHEDULER_INTERVAL_MILLISECONDS,
    );
    this.scheduleFrame();
    this.emit();
  }

  private scheduleWindow(): void {
    if (this.status !== "playing") return;
    const nowSeconds = this.engine.nowSeconds();
    const position = this.currentPosition();
    const horizon = Math.min(
      this.plan.duration_microseconds,
      position + LOOKAHEAD_MICROSECONDS,
    );
    while (this.nextNoteIndex < this.plan.notes.length) {
      const note = this.plan.notes[this.nextNoteIndex];
      if (!note || note.start_microseconds > horizon) break;
      this.nextNoteIndex += 1;
      if (note.end_microseconds <= position) continue;
      const audibleStart = Math.max(note.start_microseconds, position);
      const scheduledStart =
        this.audioAnchorSeconds +
        (audibleStart - this.positionAnchorMicroseconds) / 1_000_000;
      this.engine.schedule(
        note.midi_pitch,
        Math.max(nowSeconds + 0.01, scheduledStart),
        (note.end_microseconds - audibleStart) / 1_000_000,
        velocityFor(note),
      );
    }
  }

  private scheduleFrame(): void {
    this.frameHandle = this.runtime.requestFrame(() => {
      this.frameHandle = null;
      if (this.status !== "playing") return;
      this.positionMicroseconds = this.currentPosition();
      if (this.positionMicroseconds >= this.plan.duration_microseconds) {
        this.positionMicroseconds = this.plan.duration_microseconds;
        this.cancelScheduledAudio();
        this.status = "complete";
        this.emit();
        return;
      }
      this.emit();
      this.scheduleFrame();
    });
  }

  private currentPosition(): number {
    if (this.status !== "playing") return this.positionMicroseconds;
    const elapsed = Math.max(0, this.engine.nowSeconds() - this.audioAnchorSeconds);
    return Math.min(
      this.plan.duration_microseconds,
      Math.round(this.positionAnchorMicroseconds + elapsed * 1_000_000),
    );
  }

  private cancelScheduledAudio(): void {
    if (this.schedulerHandle !== null) this.runtime.clearInterval(this.schedulerHandle);
    if (this.frameHandle !== null) this.runtime.cancelFrame(this.frameHandle);
    this.schedulerHandle = null;
    this.frameHandle = null;
    this.engine.releaseAll();
  }

  private emit(errorCode: string | null = null, errorMessage: string | null = null): void {
    const position = this.positionMicroseconds;
    const clockHasStarted =
      this.status === "playing" && this.engine.nowSeconds() >= this.audioAnchorSeconds;
    const active = clockHasStarted
      ? this.plan.notes.filter(
          (note) => note.start_microseconds <= position && position < note.end_microseconds,
        )
      : [];
    let focus = this.plan.notes.filter(
      (note) => note.start_microseconds <= position && position < note.end_microseconds,
    );
    if (focus.length === 0) {
      let latestStart = -1;
      for (const note of this.plan.notes) {
        if (note.start_microseconds > position) break;
        latestStart = Math.max(latestStart, note.start_microseconds);
      }
      if (latestStart >= 0) {
        focus = this.plan.notes.filter((note) => note.start_microseconds === latestStart);
      }
    }
    this.onSnapshot({
      status: this.status,
      positionMicroseconds: position,
      durationMicroseconds: this.plan.duration_microseconds,
      activeNoteIds: active.map((note) => note.id),
      activeMidiPitches: unique(active.map((note) => note.midi_pitch)),
      activeNotes: active.map((note) => ({
        noteId: note.id,
        midiPitch: note.midi_pitch,
        contributions: note.source_events.map((source) => ({
          eventId: source.event_id,
          clefGroupId: source.clef_group_id,
          clef: source.clef,
          staff: source.staff,
          voice: source.voice,
        })),
      })),
      focusEventIds: unique(
        focus.flatMap((note) => note.source_events.map((source) => source.event_id)),
      ),
      countInBeatsRemaining:
        this.status === "playing" && this.countIn && this.engine.nowSeconds() < this.audioAnchorSeconds
          ? Math.min(
              this.countIn.beats,
              Math.ceil(
                ((this.audioAnchorSeconds - this.engine.nowSeconds()) * 1_000_000) /
                  this.countIn.beatMicroseconds,
              ),
            )
          : 0,
      errorCode,
      errorMessage,
    });
  }
}
