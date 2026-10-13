import type { AppConfig, AttemptResult } from "../api";
import { submitTeachingAttempt } from "../api";
import { BrowserMidiSession } from "../midi/BrowserMidiSession";
import { buildAttemptSubmission } from "../teaching/attemptSubmission";
import {
  DesktopMidiBridge,
  type MobileAttemptContext,
  type MobileCommand,
} from "./transport";

function attemptContext(value: unknown): MobileAttemptContext {
  if (!value || typeof value !== "object") throw new Error("The attempt context is missing.");
  const context = value as Partial<MobileAttemptContext>;
  for (const field of [
    "run_id",
    "score_id",
    "plan_id",
    "exercise_id",
    "practice_mode",
    "support_state_id",
  ] as const) {
    if (typeof context[field] !== "string" || context[field].length === 0) {
      throw new Error(`The attempt context field ${field} is invalid.`);
    }
  }
  if (!Number.isInteger(context.tempo_bpm) || Number(context.tempo_bpm) <= 0) {
    throw new Error("The attempt tempo is invalid.");
  }
  if (typeof context.count_in_enabled !== "boolean") {
    throw new Error("The attempt count-in state is invalid.");
  }
  return context as MobileAttemptContext;
}

export class DesktopBridgeController {
  private unsubscribe: (() => void) | null = null;
  private heartbeat: ReturnType<typeof setInterval> | null = null;
  private commandTimer: ReturnType<typeof setInterval> | null = null;
  private publishQueue: Promise<void> = Promise.resolve();
  private polling = false;
  private pendingAck: { sequence: number; outcome: { result: unknown } | { error: string } } | null = null;

  constructor(
    private readonly bridge: DesktopMidiBridge,
    private readonly midi: BrowserMidiSession,
    private readonly config: AppConfig,
    private readonly onError: (message: string) => void = () => undefined,
  ) {}

  start(): void {
    if (this.unsubscribe) return;
    this.unsubscribe = this.midi.subscribe(() => void this.publish());
    this.heartbeat = setInterval(() => void this.publish(), 1_000);
    this.commandTimer = setInterval(() => void this.poll(), 150);
    void this.poll();
  }

  stop(): void {
    this.unsubscribe?.();
    this.unsubscribe = null;
    if (this.heartbeat !== null) clearInterval(this.heartbeat);
    if (this.commandTimer !== null) clearInterval(this.commandTimer);
    this.heartbeat = null;
    this.commandTimer = null;
  }

  private publish(): Promise<void> {
    const snapshot = this.midi.current();
    this.publishQueue = this.publishQueue
      .then(() => this.bridge.publish(snapshot))
      .catch((error: unknown) => {
        this.onError(error instanceof Error ? error.message : "The MIDI bridge publish failed.");
      });
    return this.publishQueue;
  }

  private async poll(): Promise<void> {
    if (this.polling) return;
    this.polling = true;
    try {
      if (this.pendingAck) {
        await this.bridge.acknowledge(this.pendingAck.sequence, this.pendingAck.outcome);
        this.pendingAck = null;
      }
      const command = await this.bridge.readCommand();
      if (!command) return;
      const outcome = await this.execute(command).then(
        (result): { result: unknown } => ({ result }),
        (error: unknown): { error: string } => ({
          error: error instanceof Error ? error.message : "The desktop command failed.",
        }),
      );
      this.pendingAck = { sequence: command.sequence, outcome };
      // Publish the resulting capture state before acknowledging the command.
      // Otherwise the phone can observe a completed command followed by the
      // previous idle snapshot and never expose the next lifecycle control.
      await this.publish();
      await this.bridge.acknowledge(command.sequence, outcome);
      this.pendingAck = null;
    } catch (error) {
      this.onError(error instanceof Error ? error.message : "The desktop bridge is unavailable.");
    } finally {
      this.polling = false;
    }
  }

  private async execute(command: MobileCommand): Promise<Record<string, unknown> | AttemptResult> {
    switch (command.kind) {
      case "start-attempt":
        this.midi.startAttempt();
        return this.captureResult("recording");
      case "pause-attempt":
        this.midi.pauseAttempt();
        return this.captureResult("paused");
      case "resume-attempt":
        this.midi.resumeAttempt();
        return this.captureResult("recording");
      case "finish-attempt":
        this.midi.stopAttempt();
        return this.captureResult("stopped");
      case "abort-attempt":
        this.midi.abortAttempt();
        return this.captureResult("aborted");
      case "safe-stop":
        this.midi.stopAttemptForDiscomfort();
        return this.captureResult("aborted");
      case "submit-attempt": {
        const context = attemptContext(command.context);
        const submission = buildAttemptSubmission(this.midi.current(), context);
        return submitTeachingAttempt(context.run_id, submission, this.config);
      }
    }
  }

  private captureResult(expected: "recording" | "paused" | "stopped" | "aborted") {
    const snapshot = this.midi.current();
    if (snapshot.capture !== expected || snapshot.capture_purpose !== "attempt") {
      const diagnostic = snapshot.diagnostics.find((item) => item.blocking);
      throw new Error(
        diagnostic?.message ??
        `The desktop did not enter the expected ${expected} attempt state.`,
      );
    }
    return {
      capture: snapshot.capture,
      capture_purpose: snapshot.capture_purpose,
      calibration_approved: snapshot.calibration?.approved === true,
    };
  }
}
