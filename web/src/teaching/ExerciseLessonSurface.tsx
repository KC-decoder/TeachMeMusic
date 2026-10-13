import { type ChangeEvent, useCallback, useEffect, useMemo, useRef, useState } from "react";

import type { ActivePlaybackNote } from "../audio/PlaybackTransport";
import type {
  AttemptResult,
  AttemptSubmission,
  ExercisePresentation,
  TeachingPlan,
  TeachingRunResponse,
} from "../api";
import type { ViewerBundle } from "../contracts/viewer";
import { MidiCalibrationSurface } from "../midi/MidiCalibrationSurface";
import { BrowserMidiSession } from "../midi/BrowserMidiSession";
import type { AttemptMidiSession, MidiSnapshot } from "../midi/contracts";
import type { MobileAttemptContext } from "../mobile/transport";
import { NotationSurface } from "../notation/NotationSurface";
import { VirtualPiano } from "../piano/VirtualPiano";
import { PlaybackSurface } from "../playback/PlaybackSurface";
import { TeachingAttemptSurface } from "./TeachingAttemptSurface";

interface ExerciseLessonSurfaceProps {
  plan: TeachingPlan;
  presentation: ExercisePresentation;
  notation: ViewerBundle;
  loading?: boolean;
  onSelectExercise: (exerciseId: string) => void;
  onTempoChange: (tempoBpm: number) => Promise<void>;
  teachingRun: TeachingRunResponse | null;
  onStartRun: (authorization: {
    captureSelfReport: boolean;
    allowExport: boolean;
  }) => Promise<void>;
  onSubmitAttempt: (submission: AttemptSubmission) => Promise<AttemptResult>;
  onExportRun: () => Promise<void>;
  onImportRun: (file: File) => Promise<void>;
  onDeleteRun: () => Promise<void>;
  midiSession?: AttemptMidiSession;
  localMidiSession?: BrowserMidiSession | null;
  onRemoteSubmit?: (context: MobileAttemptContext) => Promise<AttemptResult>;
}

function fractionValue(value: { numerator: number; denominator: number }): number {
  return value.numerator / value.denominator;
}

function rangeLabel(presentation: ExercisePresentation): string {
  if (presentation.material_kind === "synthetic-transfer") return "New transfer pattern";
  if (presentation.measure_numbers.length === 1) {
    return `Measure ${presentation.measure_numbers[0]}`;
  }
  return `Measures ${presentation.measure_numbers[0]}–${presentation.measure_numbers.at(-1)}`;
}

function pitchName(midi: number): string {
  const names = ["C", "C♯", "D", "E♭", "E", "F", "F♯", "G", "A♭", "A", "B♭", "B"];
  return `${names[midi % 12]}${Math.floor(midi / 12) - 1}`;
}

export function ExerciseLessonSurface({
  plan,
  presentation,
  notation,
  loading = false,
  onSelectExercise,
  onTempoChange,
  teachingRun,
  onStartRun,
  onSubmitAttempt,
  onExportRun,
  onImportRun,
  onDeleteRun,
  midiSession: providedMidiSession,
  localMidiSession = null,
  onRemoteSubmit,
}: ExerciseLessonSurfaceProps) {
  const [ownedMidiSession] = useState(() => new BrowserMidiSession());
  const midiSession = providedMidiSession ?? ownedMidiSession;
  const [midiSnapshot, setMidiSnapshot] = useState<MidiSnapshot>(() => midiSession.current());
  const index = plan.exercises.findIndex((item) => item.id === presentation.exercise_id);
  const node = plan.nodes.find((item) => item.exercise_id === presentation.exercise_id);
  const exercise = plan.exercises[index];
  const [showNotation, setShowNotation] = useState(presentation.aid_state.notation_visible);
  const [showKeyboard, setShowKeyboard] = useState(presentation.aid_state.keyboard_visible);
  const [showNoteNames, setShowNoteNames] = useState(
    presentation.aid_state.pitch_prompts_visible,
  );
  const [showPrompts, setShowPrompts] = useState(presentation.aid_state.pitch_prompts_visible);
  const [showCursor, setShowCursor] = useState(true);
  const [demonstrationAvailable, setDemonstrationAvailable] = useState(true);
  const [countInEnabled, setCountInEnabled] = useState(presentation.aid_state.count_in_enabled);
  const [focusEventIds, setFocusEventIds] = useState<string[]>([]);
  const [activeNotes, setActiveNotes] = useState<ActivePlaybackNote[]>([]);
  const [promptIndex, setPromptIndex] = useState(0);
  const [guidedComplete, setGuidedComplete] = useState(false);
  const [attemptResult, setAttemptResult] = useState<AttemptResult | null>(null);
  const previousHeldPitches = useRef<Set<number>>(new Set());
  const matchedPromptPitches = useRef<Set<number>>(new Set());
  const previousCapture = useRef(midiSnapshot.capture);
  const [dataApproved, setDataApproved] = useState(false);
  const [selfReportApproved, setSelfReportApproved] = useState(false);
  const [planApproved, setPlanApproved] = useState(false);
  const [exportApproved, setExportApproved] = useState(false);
  const [runBusy, setRunBusy] = useState(false);
  const [runError, setRunError] = useState<string | null>(null);
  const [practiceStage, setPracticeStage] = useState<"closed" | "setup" | "exercise">("closed");
  const practiceStageOpen = practiceStage !== "closed";
  const practiceLaunchButton = useRef<HTMLButtonElement | null>(null);
  const practiceCloseButton = useRef<HTMLButtonElement | null>(null);
  const tempo = fractionValue(presentation.aid_state.tempo_bpm);
  const syntheticPitches = useMemo(
    () => presentation.demonstration.notes.map((note) => pitchName(note.midi_pitch)),
    [presentation.demonstration.notes],
  );
  const promptGroups = useMemo(() => {
    const groups = new Map<number, typeof presentation.demonstration.notes>();
    for (const note of presentation.demonstration.notes) {
      groups.set(note.start_microseconds, [...(groups.get(note.start_microseconds) ?? []), note]);
    }
    return [...groups.entries()]
      .sort(([left], [right]) => left - right)
      .map(([, notes]) => notes);
  }, [presentation.demonstration.notes]);
  const promptNotes = promptGroups[promptIndex] ?? [];
  const promptActiveNotes = useMemo<ActivePlaybackNote[]>(
    () => promptNotes.map((note) => ({
      noteId: note.id,
      midiPitch: note.midi_pitch,
      contributions: (note.source_events ?? []).map((source) => ({
        eventId: source.event_id,
        clefGroupId: source.clef_group_id,
        clef: source.clef,
        staff: source.staff,
        voice: source.voice,
      })),
    })),
    [promptNotes],
  );
  const promptEventIds = useMemo(
    () => promptNotes.flatMap((note) => (note.source_events ?? []).map((source) => source.event_id)),
    [promptNotes],
  );
  const missedEventIds = useMemo(
    () => attemptResult?.observations
      .filter((item) =>
        item.dimension === "pitch" &&
        item.status === "discrepancy" &&
        item.observed_value === "missing")
      .flatMap((item) => item.expected_canonical_ids) ?? [],
    [attemptResult],
  );
  const missedActiveNotes = useMemo<ActivePlaybackNote[]>(
    () => presentation.demonstration.notes
      .filter((note) => (note.source_events ?? []).some(
        (source) => missedEventIds.includes(source.event_id),
      ))
      .map((note) => ({
        noteId: note.id,
        midiPitch: note.midi_pitch,
        contributions: (note.source_events ?? []).map((source) => ({
          eventId: source.event_id,
          clefGroupId: source.clef_group_id,
          clef: source.clef,
          staff: source.staff,
          voice: source.voice,
        })),
      })),
    [missedEventIds, presentation.demonstration.notes],
  );
  const requiresAttempt = exercise?.practice_modes.some((item) => item !== "listen") ?? false;
  const midiReady = midiSnapshot.connection === "connected" &&
    midiSnapshot.calibration?.approved === true;
  const startGuidedAttempt = useCallback(() => {
    if (!teachingRun || !requiresAttempt || !midiReady) return;
    if (midiSession.current().capture === "recording" || midiSession.current().capture === "paused") {
      return;
    }
    midiSession.startAttempt();
  }, [midiReady, midiSession, requiresAttempt, teachingRun]);

  useEffect(() => {
    setShowNotation(presentation.aid_state.notation_visible);
    setShowKeyboard(presentation.aid_state.keyboard_visible);
    setShowNoteNames(presentation.aid_state.pitch_prompts_visible);
    setShowPrompts(presentation.aid_state.pitch_prompts_visible);
    setShowCursor(true);
    setDemonstrationAvailable(true);
    setCountInEnabled(presentation.aid_state.count_in_enabled);
    setFocusEventIds([]);
    setActiveNotes([]);
    setPromptIndex(0);
    setGuidedComplete(false);
    setAttemptResult(null);
    previousHeldPitches.current.clear();
    matchedPromptPitches.current.clear();
  }, [presentation.exercise_id, presentation.aid_state]);
  useEffect(() => {
    if (!teachingRun) return;
    setShowNotation(exercise?.initial_support.notation_visible ?? false);
    setShowKeyboard(exercise?.initial_support.keyboard_highlighting ?? false);
    setShowNoteNames(exercise?.initial_support.note_names_visible ?? false);
    setShowPrompts(exercise?.initial_support.prompts_visible ?? false);
    setShowCursor(exercise?.initial_support.cursor_visible ?? false);
    setDemonstrationAvailable(exercise?.initial_support.demonstration_available ?? false);
  }, [exercise?.id, teachingRun?.run_id]);
  useEffect(() => {
    const unsubscribe = midiSession.subscribe(setMidiSnapshot);
    return () => {
      unsubscribe();
      if (!providedMidiSession) ownedMidiSession.dispose();
    };
  }, [midiSession, ownedMidiSession, providedMidiSession]);
  useEffect(() => {
    const wasActive = previousCapture.current === "recording" || previousCapture.current === "paused";
    const isStarting = midiSnapshot.capture === "recording" && !wasActive;
    if (isStarting) {
      setPromptIndex(0);
      setGuidedComplete(false);
      setAttemptResult(null);
      previousHeldPitches.current = new Set(midiSnapshot.active_notes);
      matchedPromptPitches.current.clear();
    }
    previousCapture.current = midiSnapshot.capture;
  }, [midiSnapshot.active_notes, midiSnapshot.capture]);
  useEffect(() => {
    const held = new Set(midiSnapshot.active_notes);
    const newlyPressed = [...held].filter((pitch) => !previousHeldPitches.current.has(pitch));
    previousHeldPitches.current = held;
    if (midiSnapshot.capture !== "recording" || promptNotes.length === 0) return;
    const expected = new Set(promptNotes.map((note) => note.midi_pitch));
    for (const pitch of newlyPressed) {
      if (expected.has(pitch)) matchedPromptPitches.current.add(pitch);
    }
    if (![...expected].every((pitch) => matchedPromptPitches.current.has(pitch))) return;
    matchedPromptPitches.current.clear();
    if (promptIndex + 1 >= promptGroups.length) {
      setGuidedComplete(true);
      midiSession.stopAttempt();
    } else {
      setPromptIndex((value) => value + 1);
    }
  }, [midiSession, midiSnapshot.active_notes, midiSnapshot.capture, promptGroups.length, promptIndex, promptNotes]);
  useEffect(() => {
    if (!practiceStageOpen) return;
    document.body.classList.add("practice-stage-open");
    const focusFrame = window.requestAnimationFrame(() => practiceCloseButton.current?.focus());
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape") closePracticeStage();
    };
    window.addEventListener("keydown", closeOnEscape);
    return () => {
      window.cancelAnimationFrame(focusFrame);
      document.body.classList.remove("practice-stage-open");
      window.removeEventListener("keydown", closeOnEscape);
    };
  }, [practiceStageOpen]);

  const countIn = useMemo(
    () =>
      countInEnabled && presentation.aid_state.count_in_beats > 0
        ? {
            beats: presentation.aid_state.count_in_beats,
            beatMicroseconds: presentation.aid_state.count_in_beat_microseconds,
          }
        : null,
    [
      countInEnabled,
      presentation.aid_state.count_in_beats,
      presentation.aid_state.count_in_beat_microseconds,
    ],
  );

  if (!exercise || index < 0) return null;

  const guidedPhase = midiSnapshot.capture === "recording" || midiSnapshot.capture === "paused";
  const promptMatched = guidedPhase && promptNotes.length > 0 && promptNotes.every(
    (note) => midiSnapshot.active_notes.includes(note.midi_pitch),
  );
  const hasMissedNotes = !guidedPhase && missedEventIds.length > 0;
  const displayedNotes = guidedPhase
    ? promptActiveNotes
    : hasMissedNotes ? missedActiveNotes : activeNotes;
  const displayedFocusEventIds = guidedPhase
    ? promptEventIds
    : hasMissedNotes ? missedEventIds : focusEventIds;

  async function startRun() {
    setRunBusy(true);
    setRunError(null);
    try {
      const supportTempo = exercise.initial_support.tempo_bpm === null
        ? tempo
        : fractionValue(exercise.initial_support.tempo_bpm);
      if (tempo !== supportTempo) await onTempoChange(supportTempo);
      await onStartRun({
        captureSelfReport: selfReportApproved,
        allowExport: exportApproved,
      });
    } catch (error) {
      setRunError(error instanceof Error ? error.message : "The local run could not start.");
    } finally {
      setRunBusy(false);
    }
  }

  async function importRun(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    if (!file) return;
    setRunBusy(true);
    setRunError(null);
    try {
      await onImportRun(file);
    } catch (error) {
      setRunError(error instanceof Error ? error.message : "The archive could not be resumed.");
    } finally {
      event.target.value = "";
      setRunBusy(false);
    }
  }

  async function exportRun() {
    setRunBusy(true);
    setRunError(null);
    try {
      await onExportRun();
    } catch (error) {
      setRunError(error instanceof Error ? error.message : "The archive could not be exported.");
    } finally {
      setRunBusy(false);
    }
  }

  async function deleteRun() {
    setRunBusy(true);
    setRunError(null);
    try {
      await onDeleteRun();
    } catch (error) {
      setRunError(error instanceof Error ? error.message : "The active run could not be deleted.");
    } finally {
      setRunBusy(false);
    }
  }

  function closePracticeStage() {
    setPracticeStage("closed");
    setFocusEventIds([]);
    setActiveNotes([]);
    window.requestAnimationFrame(() => practiceLaunchButton.current?.focus());
  }

  function returnToPracticeSetup() {
    setPracticeStage("setup");
    setFocusEventIds([]);
    setActiveNotes([]);
  }

  function attemptSurface(compact = false) {
    if (!teachingRun) return null;
    return (
      <TeachingAttemptSurface
        session={midiSession}
        run={teachingRun}
        exercise={exercise}
        presentation={presentation}
        tempo={tempo}
        countInEnabled={countInEnabled}
        onSubmit={onSubmitAttempt}
        onRemoteSubmit={onRemoteSubmit}
        onSupportChange={(support) => {
          setShowNotation(support.notation_visible);
          setShowKeyboard(support.keyboard_highlighting);
          setShowNoteNames(support.note_names_visible);
          setShowPrompts(support.prompts_visible);
          setShowCursor(support.cursor_visible);
          setDemonstrationAvailable(support.demonstration_available);
          if (support.tempo_bpm !== null) {
            void onTempoChange(fractionValue(support.tempo_bpm));
          }
        }}
        onSelectExercise={onSelectExercise}
        nodeExercise={(nodeId) =>
          plan.nodes.find((item) => item.id === nodeId)?.exercise_id ?? null}
        compact={compact}
        autoSubmit={guidedComplete}
        onResult={setAttemptResult}
      />
    );
  }

  const setupReady = !requiresAttempt || (teachingRun !== null && midiReady);
  const setupStatus = !requiresAttempt
    ? "This is a demonstration-only exercise. No learner capture is required."
    : teachingRun === null
      ? "Authorize the teaching run below before entering this recordable exercise."
      : midiSnapshot.connection !== "connected"
        ? "The Mac MIDI bridge is unavailable. Keep the paired TeachMeMusic tab open."
        : midiSnapshot.calibration?.approved !== true
          ? "Approve the PX-770 calibration on the Mac before continuing."
          : "Teaching run, Mac bridge, and PX-770 calibration are ready.";

  function setupContent() {
    return (
      <div className="lesson-setup-content">
        <fieldset className="lesson-aids" disabled={loading || teachingRun !== null}>
          <legend>Practice aids</legend>
          <label>
            <input
              type="checkbox"
              checked={countInEnabled}
              onChange={(event) => setCountInEnabled(event.target.checked)}
            />
            Count in
          </label>
          <label>
            <input
              type="checkbox"
              checked={showNotation}
              disabled={presentation.material_kind !== "canonical"}
              onChange={(event) => setShowNotation(event.target.checked)}
            />
            Show notation
          </label>
          <label>
            <input
              type="checkbox"
              checked={showKeyboard}
              onChange={(event) => setShowKeyboard(event.target.checked)}
            />
            Light piano keys
          </label>
          <label>
            Demonstration tempo
            <select
              aria-label="Demonstration tempo"
              value={tempo}
              onChange={(event) => void onTempoChange(Number(event.target.value))}
            >
              {[...new Set([48, 60, 72, 84, 96, 120, tempo])]
                .sort((left, right) => left - right)
                .map((value) => (
                <option value={value} key={value}>{value} BPM</option>
                ))}
            </select>
          </label>
        </fieldset>

        <section className="run-gate" aria-labelledby="run-gate-title">
          <p className="eyebrow">LOCAL EVIDENCE APPROVAL</p>
          <h3 id="run-gate-title">Authorize the closed teaching loop</h3>
          {!teachingRun ? (
            <>
              <label>
                <input
                  type="checkbox"
                  checked={planApproved}
                  onChange={(event) => setPlanApproved(event.target.checked)}
                />
                I reviewed the untouched plan as source-faithful, coherent, safe, and executable.
              </label>
              <label>
                <input
                  type="checkbox"
                  checked={dataApproved}
                  onChange={(event) => setDataApproved(event.target.checked)}
                />
                I approve local MIDI capture for this run.
              </label>
              <label>
                <input
                  type="checkbox"
                  checked={selfReportApproved}
                  onChange={(event) => setSelfReportApproved(event.target.checked)}
                />
                I optionally approve self-report capture if a later exercise requests it.
              </label>
              <label>
                <input
                  type="checkbox"
                  checked={exportApproved}
                  onChange={(event) => setExportApproved(event.target.checked)}
                />
                I approve local evidence export; no score bytes, audio, video, or cloud data.
              </label>
              <button
                type="button"
                className="midi-primary"
                disabled={!planApproved || !dataApproved || runBusy}
                onClick={() => void startRun()}
              >
                {runBusy ? "Starting…" : "Start local teaching run"}
              </button>
              <label className="archive-import">
                Resume an evidence archive for this exact score
                <input
                  type="file"
                  accept="application/json,.json"
                  disabled={runBusy}
                  onChange={(event) => void importRun(event)}
                />
              </label>
            </>
          ) : (
            <div className="run-active">
              <p><strong>Authorized run:</strong> <code>{teachingRun.run_id}</code></p>
              <p>{teachingRun.inspection.event_count} append-only events · {teachingRun.inspection.attempt_count} attempts</p>
              <div>
                <button type="button" disabled={runBusy} onClick={() => void exportRun()}>
                  Export evidence
                </button>
                <button type="button" disabled={runBusy} onClick={() => void deleteRun()}>
                  Delete active run
                </button>
              </div>
            </div>
          )}
          {runError && <p className="midi-alert" role="alert">{runError}</p>}
        </section>

        {localMidiSession ? (
          <MidiCalibrationSurface session={localMidiSession} />
        ) : providedMidiSession ? (
          <section className="remote-midi-readiness" aria-labelledby="remote-midi-title">
            <p className="eyebrow">PAIRED PIANO</p>
            <h3 id="remote-midi-title">Mac and PX-770 readiness</h3>
            <p>{setupStatus}</p>
            <p className="support-boundary">
              MIDI permission, device selection, calibration, and complete evidence remain on
              the paired desktop.
            </p>
          </section>
        ) : (
          <MidiCalibrationSurface session={ownedMidiSession} />
        )}
      </div>
    );
  }

  return (
    <section
      className="lesson-panel"
      aria-labelledby="lesson-title"
      data-expected-content={presentation.expected_content_sha256}
    >
      <div className="lesson-dashboard" aria-hidden={practiceStageOpen || undefined}>
      <div className="lesson-heading">
        <div>
          <p className="eyebrow">
            BEGINNER LESSON · STEP {index + 1} OF {plan.exercises.length}
          </p>
          <h2 id="lesson-title">{rangeLabel(presentation)}</h2>
        </div>
        <span className={`lesson-kind kind-${node?.kind ?? "exercise"}`}>
          {node?.kind ?? "exercise"}
        </span>
      </div>

      <div className="lesson-summary">
        <div><small>Focus</small><strong>{presentation.primary_skill}</strong></div>
        <div><small>Practice</small><strong>{presentation.practice_modes.join(" · ")}</strong></div>
        <div><small>Tempo</small><strong>{tempo} BPM</strong></div>
        <div><small>Expected notes</small><strong>{presentation.demonstration.notes.length}</strong></div>
      </div>

      <p className="lesson-reason">{presentation.boundary_reason}</p>

      <nav className="lesson-navigation lesson-navigation-primary" aria-label="Lesson navigation">
        <button
          ref={practiceLaunchButton}
          type="button"
          disabled={loading || index === 0}
          onClick={() => onSelectExercise(plan.exercises[index - 1]!.id)}
        >
          Previous exercise
        </button>
        <span>{loading ? "Preparing exercise…" : `${index + 1} / ${plan.exercises.length}`}</span>
        <button
          type="button"
          disabled={
            loading || index + 1 >= plan.exercises.length ||
            (teachingRun !== null && exercise.practice_modes.some((item) => item !== "listen"))
          }
          onClick={() => onSelectExercise(plan.exercises[index + 1]!.id)}
        >
          Next exercise
        </button>
      </nav>
      {teachingRun && exercise.practice_modes.some((item) => item !== "listen") && (
        <p className="policy-navigation-note">
          Policy feedback unlocks the next performance exercise; preview navigation is paused.
        </p>
      )}

      <section className="practice-launch" aria-labelledby="practice-launch-title">
        <div>
          <p className="eyebrow">LANDSCAPE PRACTICE</p>
          <h3 id="practice-launch-title">Open this exercise on its own screen</h3>
          <p>
            The practice screen shows only this bounded score passage, its demonstration
            controls, and the live piano.
          </p>
        </div>
        <button
          type="button"
          className="midi-primary"
          disabled={loading}
          onClick={() => setPracticeStage("setup")}
        >
          Open practice screen
        </button>
      </section>

      <p className="practice-setup-summary">
        Setup, calibration, and evidence are the first step after opening the practice screen.
      </p>

      <details className="lesson-trace">
        <summary>Why this exercise is traceable</summary>
        <p>Expected-content fingerprint: <code>{presentation.expected_content_sha256}</code></p>
        <p>{presentation.event_ids.length} exact expected event identities.</p>
        {presentation.diagnostics.map((item) => <p key={item}>{item}</p>)}
      </details>
      </div>

      {practiceStage === "setup" && (
        <section
          className="practice-setup-stage"
          role="dialog"
          aria-modal="true"
          aria-labelledby="practice-setup-title"
        >
          <header className="practice-setup-header">
            <button
              ref={practiceCloseButton}
              type="button"
              className="practice-stage-close"
              aria-label="Close practice setup"
              onClick={closePracticeStage}
            >
              ← Lesson
            </button>
            <div>
              <p className="eyebrow">STEP 1 OF 2</p>
              <h2 id="practice-setup-title">Setup, calibration, and evidence</h2>
              <p>{rangeLabel(presentation)} · confirm readiness before opening the exercise.</p>
            </div>
            <button
              type="button"
              className="midi-primary"
              disabled={loading || runBusy}
              onClick={() => setPracticeStage("exercise")}
            >
              {setupReady ? "Continue to exercise →" : "Continue without recording →"}
            </button>
          </header>
          <p className={`practice-setup-status ${setupReady ? "is-ready" : "is-blocked"}`} role="status">
            {setupStatus}
          </p>
          <main className="practice-setup-body">
            {setupContent()}
          </main>
        </section>
      )}

      {practiceStage === "exercise" && (
        <section
          className={`practice-stage ${showKeyboard ? "has-piano" : ""} ${teachingRun ? "has-attempt" : ""} ${guidedPhase ? "is-learner-practice" : "is-demonstration"} ${promptMatched ? "is-practice-match" : ""} ${hasMissedNotes ? "has-missed-notes" : ""}`}
          role="dialog"
          aria-modal="true"
          aria-labelledby="practice-stage-title"
        >
          <header className="practice-stage-header">
            <button
              ref={practiceCloseButton}
              type="button"
              className="practice-stage-close"
              aria-label="Back to practice setup"
              onClick={returnToPracticeSetup}
            >
              ← Setup
            </button>
            <div className="practice-stage-identity">
              <p>STEP {index + 1} OF {plan.exercises.length}</p>
              <h2 id="practice-stage-title">{rangeLabel(presentation)}</h2>
            </div>
            <nav className="practice-stage-navigation" aria-label="Practice exercise navigation">
              <button
                type="button"
                aria-label="Previous practice exercise"
                disabled={loading || index === 0}
                onClick={() => onSelectExercise(plan.exercises[index - 1]!.id)}
              >
                ←
              </button>
              <span>{index + 1} / {plan.exercises.length}</span>
              <button
                type="button"
                aria-label="Next practice exercise"
                disabled={
                  loading || index + 1 >= plan.exercises.length ||
                  (teachingRun !== null && exercise.practice_modes.some((item) => item !== "listen"))
                }
                onClick={() => onSelectExercise(plan.exercises[index + 1]!.id)}
              >
                →
              </button>
            </nav>
            <div className="practice-stage-transport" data-mobile-region="controls">
              {demonstrationAvailable ? (
                <PlaybackSurface
                  key={`${presentation.exercise_id}:${tempo}`}
                  plan={presentation.demonstration}
                  countIn={countIn}
                  eyebrow="EXPECTED PIANO DEMONSTRATION"
                  heading="Listen to this exercise"
                  onFocusEventIds={setFocusEventIds}
                  onActiveNotes={setActiveNotes}
                  onComplete={startGuidedAttempt}
                />
              ) : (
                <p className="support-boundary">
                  Demonstration is removed for this recorded attempt condition.
                </p>
              )}
            </div>
          </header>

          {teachingRun && (
            <div className="practice-stage-attempt" data-mobile-region="attempt">
              <p className="practice-phase" aria-live="polite">
                {guidedPhase ? "Your turn" : guidedComplete ? "Checking your attempt…" : "Listen"}
              </p>
              {attemptSurface(true)}
            </div>
          )}

          <main className="practice-stage-score" data-mobile-region="notation">
            {presentation.material_kind === "synthetic-transfer" && (
              <div className="transfer-pattern" aria-label="Expected transfer notes">
                {syntheticPitches.map((pitch, pitchIndex) => (
                  <span key={`${pitch}-${pitchIndex}`}>{pitch}</span>
                ))}
              </div>
            )}
            {showNotation && presentation.material_kind === "canonical" && (
              <NotationSurface
                bundle={notation}
                allowedEventIds={presentation.event_ids}
                focusEventIds={showCursor ? displayedFocusEventIds : []}
              />
            )}
            {!showNotation && (
              <p className="practice-stage-empty">Notation is hidden for this exercise.</p>
            )}
            {showPrompts && (
              <p className="practice-stage-prompt">
                Follow the highlighted expected keys and the exact score range.
              </p>
            )}
          </main>

          {showKeyboard && (
            <div className="practice-piano-dock" data-mobile-region="piano">
              <VirtualPiano
                activeNotes={displayedNotes}
                playedMidiPitches={midiSnapshot.active_notes}
                learnerInputStatus={
                  midiSnapshot.connection !== "connected"
                    ? "unavailable"
                    : midiSnapshot.capture === "recording"
                      ? "capturing"
                      : "connected"
                }
                showNoteNames={showNoteNames}
                guidanceMode={guidedPhase ? "practice" : hasMissedNotes ? "missed" : "demonstration"}
              />
            </div>
          )}
        </section>
      )}
    </section>
  );
}
