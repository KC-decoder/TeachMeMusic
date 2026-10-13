import { useEffect, useRef, useState } from "react";

import type { PlaybackPlan } from "../contracts/playback";
import type {
  ActivePlaybackNote,
  CountInSpec,
  PlaybackController,
  PlaybackSnapshot,
} from "../audio/PlaybackTransport";
import {
  createTonePlaybackController,
  type PlaybackControllerFactory,
} from "../audio/TonePlaybackAdapter";

interface PlaybackSurfaceProps {
  plan: PlaybackPlan;
  onFocusEventIds?: (eventIds: string[]) => void;
  onActiveNotes?: (notes: ActivePlaybackNote[]) => void;
  controllerFactory?: PlaybackControllerFactory;
  countIn?: CountInSpec | null;
  heading?: string;
  eyebrow?: string;
  onComplete?: () => void;
}

const initialSnapshot = (durationMicroseconds: number): PlaybackSnapshot => ({
  status: "idle",
  positionMicroseconds: 0,
  durationMicroseconds,
  activeNoteIds: [],
  activeMidiPitches: [],
  activeNotes: [],
  focusEventIds: [],
  countInBeatsRemaining: 0,
  errorCode: null,
  errorMessage: null,
});

function formatTime(microseconds: number): string {
  const seconds = Math.max(0, Math.floor(microseconds / 1_000_000));
  return `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, "0")}`;
}

export function PlaybackSurface({
  plan,
  onFocusEventIds,
  onActiveNotes,
  controllerFactory = createTonePlaybackController,
  countIn = null,
  heading = "Listen to this score",
  eyebrow = "CANONICAL PIANO PLAYBACK",
  onComplete,
}: PlaybackSurfaceProps) {
  const controller = useRef<PlaybackController | null>(null);
  const completionNotified = useRef(false);
  const [snapshot, setSnapshot] = useState(() => initialSnapshot(plan.duration_microseconds));

  useEffect(() => {
    setSnapshot(initialSnapshot(plan.duration_microseconds));
    onFocusEventIds?.([]);
    onActiveNotes?.([]);
    try {
      const nextController = controllerFactory(plan, (nextSnapshot) => {
        setSnapshot(nextSnapshot);
        onFocusEventIds?.(nextSnapshot.focusEventIds);
        onActiveNotes?.(nextSnapshot.activeNotes);
        if (nextSnapshot.status === "complete") {
          if (!completionNotified.current) {
            completionNotified.current = true;
            onComplete?.();
          }
        } else {
          completionNotified.current = false;
        }
      }, countIn);
      controller.current = nextController;
      return () => {
        nextController.dispose();
        if (controller.current === nextController) controller.current = null;
      };
    } catch {
      setSnapshot({
        ...initialSnapshot(plan.duration_microseconds),
        status: "error",
        errorCode: "AUDIO_CONTRACT_REJECTED",
        errorMessage: "The canonical playback plan could not be used safely.",
      });
      return undefined;
    }
  }, [controllerFactory, countIn, onActiveNotes, onComplete, onFocusEventIds, plan]);

  const playLabel =
    snapshot.status === "paused"
      ? "Resume"
      : snapshot.status === "complete"
        ? "Play again"
        : "Play";
  const statusLabel =
    snapshot.countInBeatsRemaining > 0
      ? `Count in · ${snapshot.countInBeatsRemaining}`
      : snapshot.status === "loading"
      ? "Loading the local piano…"
      : snapshot.status === "playing"
        ? `Playing · ${snapshot.activeMidiPitches.length} active ${snapshot.activeMidiPitches.length === 1 ? "key" : "keys"}`
        : snapshot.status === "paused"
          ? "Paused"
          : snapshot.status === "complete"
            ? "Playback complete"
            : snapshot.status === "error"
              ? "Playback unavailable"
              : "Ready to play";

  return (
    <section className="playback-panel" aria-labelledby="playback-title">
      <div className="playback-heading">
        <div>
          <p className="eyebrow">{eyebrow}</p>
          <h2 id="playback-title">{heading}</h2>
        </div>
        <p className="playback-state" aria-live="polite">{statusLabel}</p>
      </div>

      <div className="playback-controls">
        <button
          className="playback-primary"
          type="button"
          disabled={snapshot.status === "loading" || snapshot.status === "playing" || snapshot.status === "error"}
          onClick={() => void controller.current?.play()}
        >
          <span aria-hidden="true">▶</span> {playLabel}
        </button>
        <button
          type="button"
          disabled={snapshot.status !== "playing" && snapshot.status !== "loading"}
          onClick={() => controller.current?.pause()}
        >
          Pause
        </button>
        <button
          type="button"
          disabled={snapshot.status === "loading" || snapshot.status === "error"}
          onClick={() => void controller.current?.restart()}
        >
          Restart
        </button>
        <button
          type="button"
          disabled={snapshot.status === "idle" || snapshot.status === "error"}
          onClick={() => controller.current?.stop()}
        >
          Stop
        </button>
      </div>

      <div className="playback-timeline">
        <label htmlFor="playback-position">Playback position</label>
        <input
          id="playback-position"
          type="range"
          min="0"
          max={Math.max(1, plan.duration_microseconds)}
          step="10000"
          value={snapshot.positionMicroseconds}
          disabled={snapshot.status === "loading" || snapshot.status === "error"}
          onChange={(event) => controller.current?.seek(Number(event.target.value))}
        />
        <output htmlFor="playback-position">
          {formatTime(snapshot.positionMicroseconds)} / {formatTime(plan.duration_microseconds)}
        </output>
      </div>

      {snapshot.status === "error" && (
        <div className="playback-error" role="alert">
          <strong>{snapshot.errorMessage}</strong>
          <code>{snapshot.errorCode}</code>
        </div>
      )}

      <p className="playback-note">
        Piano samples stay on this device. Where the score has no dynamic marking, a consistent
        neutral piano touch is used.
      </p>

      {plan.diagnostics.length > 0 && (
        <details className="playback-diagnostics">
          <summary>Playback notes ({plan.diagnostics.length})</summary>
          <ul>
            {plan.diagnostics.map((diagnostic, index) => (
              <li key={`${diagnostic.code}-${index}`} data-severity={diagnostic.severity}>
                <code>{diagnostic.code}</code> — {diagnostic.message}
              </li>
            ))}
          </ul>
        </details>
      )}
    </section>
  );
}
