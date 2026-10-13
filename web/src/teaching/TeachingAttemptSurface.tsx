import { useEffect, useMemo, useState } from "react";

import type {
  AttemptResult,
  AttemptSubmission,
  ExercisePresentation,
  LessonExercise,
  TeachingRunResponse,
} from "../api";
import type { AttemptMidiSession, MidiSnapshot } from "../midi/contracts";
import { midiNoteName } from "../piano/model";
import { buildAttemptSubmission } from "./attemptSubmission";

interface TeachingAttemptSurfaceProps {
  session: AttemptMidiSession;
  run: TeachingRunResponse;
  exercise: LessonExercise;
  presentation: ExercisePresentation;
  tempo: number;
  countInEnabled: boolean;
  onSubmit: (submission: AttemptSubmission) => Promise<AttemptResult>;
  onRemoteSubmit?: (context: {
    run_id: string;
    score_id: string;
    plan_id: string;
    exercise_id: string;
    practice_mode: string;
    support_state_id: string;
    tempo_bpm: number;
    count_in_enabled: boolean;
  }) => Promise<AttemptResult>;
  onSupportChange: (support: LessonExercise["initial_support"]) => void;
  onSelectExercise: (exerciseId: string) => void;
  nodeExercise: (nodeId: string) => string | null;
  compact?: boolean;
  autoSubmit?: boolean;
  onResult?: (result: AttemptResult) => void;
}

export function TeachingAttemptSurface({
  session,
  run,
  exercise,
  presentation,
  tempo,
  countInEnabled,
  onSubmit,
  onRemoteSubmit,
  onSupportChange,
  onSelectExercise,
  nodeExercise,
  compact = false,
  autoSubmit = false,
  onResult,
}: TeachingAttemptSurfaceProps) {
  const [snapshot, setSnapshot] = useState(() => session.current());
  const [practiceMode, setPracticeMode] = useState(
    () => exercise.practice_modes.find((item) => item !== "listen") ?? "",
  );
  const [supportStateId, setSupportStateId] = useState(exercise.initial_support.id);
  const [result, setResult] = useState<AttemptResult | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [startRequested, setStartRequested] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => session.subscribe(setSnapshot), [session]);
  useEffect(() => {
    setPracticeMode(exercise.practice_modes.find((item) => item !== "listen") ?? "");
    setSupportStateId(exercise.initial_support.id);
    setResult(null);
    setStartRequested(false);
    setError(null);
  }, [exercise.id, exercise.initial_support.id, exercise.practice_modes]);
  useEffect(() => {
    if (
      snapshot.capture === "recording" ||
      snapshot.connection !== "connected" ||
      snapshot.diagnostics.some((item) => item.blocking)
    ) {
      setStartRequested(false);
    }
  }, [snapshot.capture, snapshot.connection, snapshot.diagnostics]);

  const noteOns = useMemo(
    () => snapshot.normalized_events.filter((item) => item.kind === "note-on"),
    [snapshot.normalized_events],
  );
  const isAttempt = snapshot.capture_purpose === "attempt";
  const canStart = practiceMode !== "" && snapshot.connection === "connected" &&
    snapshot.calibration?.approved === true &&
    (!isAttempt || snapshot.capture === "stopped" || snapshot.capture === "aborted");
  const canSubmit = isAttempt && (snapshot.capture === "stopped" || snapshot.capture === "aborted") &&
    snapshot.calibration?.approved === true && (
      onRemoteSubmit !== undefined || (
        snapshot.capture_start_microseconds !== null && snapshot.capture_started_at_utc !== null
      )
    );
  const activeCapture = isAttempt && (snapshot.capture === "recording" || snapshot.capture === "paused");
  const readinessMessage = snapshot.connection !== "connected"
    ? "Mac MIDI bridge unavailable — keep the paired TeachMeMusic tab open."
    : snapshot.calibration?.approved !== true
      ? "Approve the PX-770 calibration on the Mac before starting."
      : activeCapture
        ? snapshot.capture === "paused" ? "Attempt paused." : "Recording your attempt."
        : canSubmit
          ? "Attempt finished — compare it for feedback."
          : startRequested
            ? "Starting the attempt on the Mac…"
            : "Ready to record.";
  const commandDiagnostic = snapshot.diagnostics.find((item) => item.blocking);

  async function submit() {
    if (!canSubmit || !snapshot.calibration) return;
    setSubmitting(true);
    setError(null);
    try {
      const context = {
        run_id: run.run_id,
        score_id: presentation.score_id,
        plan_id: presentation.plan_id,
        exercise_id: exercise.id,
        practice_mode: practiceMode,
        support_state_id: supportStateId,
        tempo_bpm: tempo,
        count_in_enabled: countInEnabled,
      };
      const response = onRemoteSubmit
        ? await onRemoteSubmit(context)
        : await onSubmit(buildAttemptSubmission(snapshot, context));
      setResult(response);
      onResult?.(response);
      if (response.next_support) {
        setSupportStateId(response.next_support.id);
        onSupportChange(response.next_support);
      }
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "The attempt could not be evaluated.");
    } finally {
      setSubmitting(false);
    }
  }

  useEffect(() => {
    if (!autoSubmit || !canSubmit || result !== null || submitting) return;
    void submit();
  }, [autoSubmit, canSubmit, result, submitting]);

  const nextExerciseId = result?.decision.next_node_id
    ? nodeExercise(result.decision.next_node_id)
    : null;
  const effectiveSupportStateId = result?.next_support?.id ?? supportStateId;
  const progressionStatus = !result
    ? null
    : result.decision.action === "human-review"
      ? "Held for human review — forward progression is unavailable."
      : nextExerciseId && nextExerciseId !== exercise.id
        ? "The recommended next exercise is available."
        : nextExerciseId === exercise.id
          ? "Held on this exercise."
          : "No next exercise is currently authorized.";

  useEffect(() => {
    if (
      result?.mastery?.action !== "exercise-complete" ||
      nextExerciseId === null ||
      nextExerciseId === exercise.id
    ) return;
    const handle = window.setTimeout(() => onSelectExercise(nextExerciseId), 1_400);
    return () => window.clearTimeout(handle);
  }, [exercise.id, nextExerciseId, onSelectExercise, result?.mastery?.action]);

  const retryLabel = result?.mastery?.action === "slow-down"
    ? "Play slower"
    : result?.mastery?.action === "return-to-normal"
      ? "Play at normal speed"
      : result ? "Try again" : "Start attempt";

  if (practiceMode === "") {
    return (
      <section
        className={`attempt-panel${compact ? " attempt-panel-compact" : ""}`}
        aria-labelledby="attempt-title"
      >
        <p className="eyebrow">PRACTICE LOOP</p>
        <h3 id="attempt-title">Listen before playing</h3>
        <p>This node is demonstration-only. It creates no learner-performance claim.</p>
      </section>
    );
  }

  return (
    <section
      className={`attempt-panel${compact ? " attempt-panel-compact" : ""}`}
      aria-labelledby="attempt-title"
      data-run-id={run.run_id}
    >
      <div className="attempt-heading">
        <div>
          <p className="eyebrow">CLOSED TEACHING LOOP</p>
          <h3 id="attempt-title">Play this exercise</h3>
        </div>
        <span>{run.inspection.attempt_count} recorded attempt{run.inspection.attempt_count === 1 ? "" : "s"}</span>
      </div>

      <label>
        Practice mode
        <select
          aria-label="Practice mode"
          value={practiceMode}
          disabled={isAttempt && snapshot.capture === "recording"}
          onChange={(event) => setPracticeMode(event.target.value)}
        >
          {exercise.practice_modes.filter((item) => item !== "listen").map((item) => (
            <option key={item} value={item}>{item}</option>
          ))}
        </select>
      </label>

      <p className="attempt-condition">
        Evidence condition: <code>{supportStateId}</code>. Demonstration and visible aids are
        recorded separately from the expected notes.
      </p>

      <div className="attempt-actions">
        {!activeCapture && (!canSubmit || result !== null) && (
          <button type="button" className="midi-primary" disabled={!canStart || startRequested} onClick={() => {
            setResult(null);
            setStartRequested(true);
            session.startAttempt();
          }}>
            {startRequested ? "Starting attempt…" : retryLabel}
          </button>
        )}
        {isAttempt && snapshot.capture === "recording" && (
          <>
            <button type="button" className="midi-primary" onClick={() => session.stopAttempt()}>
              Finish attempt
            </button>
            <button type="button" onClick={() => session.pauseAttempt()}>Pause</button>
            <button type="button" onClick={() => session.abortAttempt()}>Abort without penalty</button>
            <button type="button" onClick={() => session.stopAttemptForDiscomfort()}>
              Stop — discomfort
            </button>
          </>
        )}
        {isAttempt && snapshot.capture === "paused" && (
          <>
            <button type="button" className="midi-primary" onClick={() => session.resumeAttempt()}>
              Resume
            </button>
            <button type="button" onClick={() => session.stopAttempt()}>Finish attempt</button>
            <button type="button" onClick={() => session.abortAttempt()}>Abort without penalty</button>
            <button type="button" onClick={() => session.stopAttemptForDiscomfort()}>
              Stop — discomfort
            </button>
          </>
        )}
        {canSubmit && result === null && (
          <button type="button" className="midi-primary" disabled={submitting} onClick={() => void submit()}>
            {submitting ? "Evaluating…" : "Compare and give feedback"}
          </button>
        )}
      </div>

      <p className="attempt-readiness" role="status">{readinessMessage}</p>

      {isAttempt && snapshot.capture !== "idle" && (
        <div className="attempt-live" aria-live="polite">
          <strong>{noteOns.length} note-on events captured</strong>
          <span>{snapshot.active_notes.map(midiNoteName).join(" · ") || "No keys currently held"}</span>
        </div>
      )}

      {error && <p className="midi-alert" role="alert">{error}</p>}
      {commandDiagnostic && <p className="midi-alert" role="alert">{commandDiagnostic.message}</p>}

      {result && (
        <section
          className={`learner-result learner-result-${result.mastery?.action ?? "retry"}`}
          aria-live="assertive"
          data-mastery-action={result.mastery?.action ?? "unresolved"}
        >
          {result.mastery?.action === "exercise-complete" ? (
            <>
              <h4>Exercise complete</h4>
              <p>{nextExerciseId && nextExerciseId !== exercise.id ? "Moving to the next exercise…" : "You completed this exercise."}</p>
            </>
          ) : result.mastery?.action === "slow-down" ? (
            <>
              <h4>Let’s slow it down</h4>
              <p>The next attempt will use a slower tempo.</p>
            </>
          ) : result.mastery?.action === "return-to-normal" ? (
            <>
              <h4>Now play it at normal speed</h4>
              <p>Reach the goal once more to complete the exercise.</p>
            </>
          ) : result.decision.action === "safe-stop" ? (
            <>
              <h4>Stop practice</h4>
              <p>Resume only when it is safe and comfortable to continue.</p>
            </>
          ) : (
            <h4>Try again</h4>
          )}
          {!compact && (
            <details className="research-result">
              <summary>Attempt details</summary>
              <dl className="feedback-summary" aria-label="Attempt result status">
                <div>
                  <dt>Attempt count</dt>
                  <dd>{result.inspection.attempt_count} recorded attempt{result.inspection.attempt_count === 1 ? "" : "s"}</dd>
                </div>
                <div>
                  <dt>Support state</dt>
                  <dd><code>{effectiveSupportStateId}</code></dd>
                </div>
                <div>
                  <dt>Progression</dt>
                  <dd>{progressionStatus}</dd>
                </div>
              </dl>
              <p>{result.feedback.observation}</p>
              <p>{result.feedback.action}</p>
            </details>
          )}
        </section>
      )}
    </section>
  );
}
