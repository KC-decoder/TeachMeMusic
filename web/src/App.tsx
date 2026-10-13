import { ChangeEvent, useCallback, useEffect, useRef, useState } from "react";

import {
  ApiError,
  AppConfig,
  AttemptResult,
  AttemptSubmission,
  Diagnostic,
  PreparedBundle,
  SessionManifest,
  TeachingPlan,
  TeachingRunResponse,
  ExercisePresentation,
  deleteSession,
  deleteTeachingRun,
  exportTeachingRun,
  getConfig,
  importTeachingRun,
  prepareExercise,
  prepareScore,
  prepareTeachingPlan,
  startTeachingRun,
  submitTeachingAttempt,
  uploadScore,
} from "./api";
import { NotationSurface } from "./notation/NotationSurface";
import { PlaybackSurface } from "./playback/PlaybackSurface";
import type { ActivePlaybackNote } from "./audio/PlaybackTransport";
import { VirtualPiano } from "./piano/VirtualPiano";
import { ExerciseLessonSurface } from "./teaching/ExerciseLessonSurface";
import { BrowserMidiSession } from "./midi/BrowserMidiSession";
import { MobileCompanionSession, claimPhonePairing } from "./mobile/transport";
import { MobileBridgeSetup } from "./mobile/MobileBridgeSetup";
import { RemoteMidiSession } from "./mobile/RemoteMidiSession";

type Status = "starting" | "idle" | "loading" | "selecting" | "ready" | "error";

const fallbackDiagnostic: Diagnostic = {
  code: "APP_CONNECTION_FAILED",
  stage: "application",
  message: "The local TeachMeMusic service is unavailable.",
};

export function App() {
  const [desktopMidiSession] = useState(() => new BrowserMidiSession());
  const [remoteMidiSession, setRemoteMidiSession] = useState<RemoteMidiSession | null>(null);
  const [config, setConfig] = useState<AppConfig | null>(null);
  const [status, setStatus] = useState<Status>("starting");
  const [manifest, setManifest] = useState<SessionManifest | null>(null);
  const [bundle, setBundle] = useState<PreparedBundle | null>(null);
  const [selectedScoreId, setSelectedScoreId] = useState("");
  const [teachingPlan, setTeachingPlan] = useState<TeachingPlan | null>(null);
  const [presentation, setPresentation] = useState<ExercisePresentation | null>(null);
  const [teachingRun, setTeachingRun] = useState<TeachingRunResponse | null>(null);
  const [teachingLoading, setTeachingLoading] = useState(false);
  const [diagnostic, setDiagnostic] = useState<Diagnostic | null>(null);
  const [playbackFocusEventIds, setPlaybackFocusEventIds] = useState<string[]>([]);
  const [activePlaybackNotes, setActivePlaybackNotes] = useState<ActivePlaybackNote[]>([]);
  const activeSession = useRef<string | null>(null);

  const updatePlaybackFocus = useCallback((eventIds: string[]) => {
    setPlaybackFocusEventIds((current) =>
      current.length === eventIds.length && current.every((id, index) => id === eventIds[index])
        ? current
        : eventIds,
    );
  }, []);

  async function prepareTeaching(
    sessionId: string,
    scoreId: string,
    currentConfig: AppConfig,
  ): Promise<{ plan: TeachingPlan; presentation: ExercisePresentation }> {
    const planResponse = await prepareTeachingPlan(sessionId, scoreId, currentConfig);
    const first = planResponse.plan.exercises[0];
    if (!first) throw new Error("No lesson exercise returned");
    const projected = await prepareExercise(
      sessionId,
      scoreId,
      planResponse.plan.id,
      first.id,
      currentConfig,
    );
    return { plan: planResponse.plan, presentation: projected.presentation };
  }

  const updateActivePlaybackNotes = useCallback((notes: ActivePlaybackNote[]) => {
    setActivePlaybackNotes((current) =>
      current.length === notes.length && current.every((note, index) => note.noteId === notes[index]?.noteId)
        ? current
        : notes,
    );
  }, []);

  useEffect(() => {
    let mounted = true;
    const query = new URLSearchParams(window.location.search);
    const fragment = new URLSearchParams(window.location.hash.replace(/^#/, ""));
    const pairingId = query.get("pairing_id");
    const phoneCapability = fragment.get("phone_capability");
    const mobile = pairingId && phoneCapability
      ? claimPhonePairing(pairingId, phoneCapability).then((phoneToken) => {
          window.history.replaceState(null, "", `${window.location.pathname}?pairing_id=${encodeURIComponent(pairingId)}`);
          const companion = new MobileCompanionSession(pairingId, phoneToken);
          const remote = new RemoteMidiSession(companion);
          if (mounted) setRemoteMidiSession(remote);
          return getConfig({ pairing_id: pairingId, phone_token: phoneToken });
        })
      : getConfig();
    void mobile
      .then((value) => {
        if (mounted) {
          setConfig(value);
          setStatus("idle");
        }
      })
      .catch(() => {
        if (mounted) {
          setDiagnostic(fallbackDiagnostic);
          setStatus("error");
        }
      });
    return () => {
      mounted = false;
      desktopMidiSession.dispose();
    };
  }, [desktopMidiSession]);
  useEffect(() => () => remoteMidiSession?.dispose(), [remoteMidiSession]);

  async function chooseFile(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    if (!file || !config) return;
    setStatus("loading");
    setDiagnostic(null);
    let pendingSession: string | null = null;
    try {
      const nextManifest = await uploadScore(file, config);
      pendingSession = nextManifest.session_id;
      const score = nextManifest.scores[0];
      if (!score) throw new Error("No score document returned");
      if (nextManifest.scores.length > 1) {
        const previous = activeSession.current;
        activeSession.current = nextManifest.session_id;
        pendingSession = null;
        setManifest(nextManifest);
        setBundle(null);
        setTeachingPlan(null);
        setPresentation(null);
        setTeachingRun(null);
        setSelectedScoreId(score.score_id);
        setStatus("selecting");
        if (previous && previous !== nextManifest.session_id) {
          void deleteSession(previous, config);
        }
        return;
      }
      const nextBundle = await prepareScore(nextManifest.session_id, score.score_id, config);
      const teaching = await prepareTeaching(nextManifest.session_id, score.score_id, config);
      const previous = activeSession.current;
      activeSession.current = nextManifest.session_id;
      pendingSession = null;
      setManifest(nextManifest);
      setBundle(nextBundle);
      setTeachingPlan(teaching.plan);
      setPresentation(teaching.presentation);
      setTeachingRun(null);
      setSelectedScoreId(score.score_id);
      setStatus("ready");
      if (previous && previous !== nextManifest.session_id) {
        void deleteSession(previous, config);
      }
    } catch (error) {
      if (pendingSession) void deleteSession(pendingSession, config);
      setDiagnostic(error instanceof ApiError ? error.diagnostic : fallbackDiagnostic);
      setStatus("error");
    } finally {
      event.target.value = "";
    }
  }

  async function prepareSelectedScore() {
    if (!config || !manifest || !selectedScoreId) return;
    setStatus("loading");
    setDiagnostic(null);
    try {
      const [nextBundle, teaching] = await Promise.all([
        prepareScore(manifest.session_id, selectedScoreId, config),
        prepareTeaching(manifest.session_id, selectedScoreId, config),
      ]);
      setBundle(nextBundle);
      setTeachingPlan(teaching.plan);
      setPresentation(teaching.presentation);
      setTeachingRun(null);
      setStatus("ready");
    } catch (error) {
      setDiagnostic(error instanceof ApiError ? error.diagnostic : fallbackDiagnostic);
      setStatus("error");
    }
  }

  async function selectExercise(exerciseId: string, tempoBpm?: number) {
    if (!config || !manifest || !teachingPlan || !selectedScoreId) return;
    setTeachingLoading(true);
    setDiagnostic(null);
    try {
      const result = await prepareExercise(
        manifest.session_id,
        selectedScoreId,
        teachingPlan.id,
        exerciseId,
        config,
        { tempoBpm },
        teachingRun?.run_id,
      );
      setPresentation(result.presentation);
    } catch (error) {
      setDiagnostic(error instanceof ApiError ? error.diagnostic : fallbackDiagnostic);
    } finally {
      setTeachingLoading(false);
    }
  }

  async function beginTeachingRun(authorization: {
    captureSelfReport: boolean;
    allowExport: boolean;
  }) {
    if (!config || !manifest || !teachingPlan || !selectedScoreId) return;
    const run = await startTeachingRun(
      manifest.session_id,
      selectedScoreId,
      teachingPlan.id,
      config,
      authorization,
    );
    setTeachingRun(run);
  }

  async function submitAttempt(submission: AttemptSubmission): Promise<AttemptResult> {
    if (!config || !teachingRun) throw new Error("Start the local teaching run first.");
    const result = await submitTeachingAttempt(teachingRun.run_id, submission, config);
    setTeachingRun((current) => current ? { ...current, inspection: result.inspection } : current);
    if (result.plan) setTeachingPlan(result.plan);
    if (result.presentation) setPresentation(result.presentation);
    return result;
  }

  async function downloadEvidence() {
    if (!config || !teachingRun) return;
    const blob = await exportTeachingRun(teachingRun.run_id, config);
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = `teachmemusic-run-${new Date().toISOString().replaceAll(":", "-")}.json`;
    link.click();
    URL.revokeObjectURL(url);
  }

  async function resumeEvidence(file: File) {
    if (!config || !manifest || !selectedScoreId) return;
    const archive = JSON.parse(await file.text()) as object;
    const run = await importTeachingRun(
      manifest.session_id,
      selectedScoreId,
      archive,
      config,
    );
    setTeachingRun(run);
  }

  async function removeTeachingRun() {
    if (!config || !teachingRun) return;
    await deleteTeachingRun(teachingRun.run_id, config);
    setTeachingRun(null);
  }

  return (
    <>
      <section
        className="landscape-orientation-gate"
        role="dialog"
        aria-modal="true"
        aria-labelledby="landscape-orientation-title"
      >
        <span className="landscape-orientation-icon" aria-hidden="true">↻</span>
        <div>
          <p className="eyebrow">LANDSCAPE PRACTICE</p>
          <h1 id="landscape-orientation-title">Rotate your iPhone</h1>
          <p>TeachMeMusic lessons are designed for landscape orientation.</p>
        </div>
      </section>
      <main className="app-shell">
      <header className="masthead">
        <a className="wordmark" href="/" aria-label="TeachMeMusic home">
          <span aria-hidden="true">♪</span> TeachMeMusic
        </a>
        <span className="phase">Local beginner teaching loop</span>
      </header>

      <section className="hero" aria-labelledby="page-title">
        <p className="eyebrow">DEV-008 · BEGINNER TEACHING</p>
        <h1 id="page-title">Bring a score.<br />Learn it step by step.</h1>
        <p className="lede">
          Load MusicXML from your computer. TeachMeMusic validates it, creates a traceable
          Beginner lesson, and demonstrates each bounded exercise.
        </p>

        {config && !config.mobile && (
          <MobileBridgeSetup config={config} session={desktopMidiSession} />
        )}

        <label className={`upload-card ${status === "loading" ? "is-loading" : ""}`}>
          <input
            type="file"
            disabled={!config || status === "loading"}
            onChange={(event) => void chooseFile(event)}
          />
          <span className="upload-icon" aria-hidden="true">↥</span>
          <span className="upload-copy">
            <strong>{status === "loading" ? "Reading your score…" : "Choose a score"}</strong>
            <small>MusicXML or compressed MXL · stays on this device</small>
          </span>
          <span className="upload-action">Browse</span>
        </label>

        <div aria-live="polite">
          {status === "starting" && <p className="status">Starting the local score service…</p>}
          {status === "error" && diagnostic && (
            <section className="message error" role="alert">
              <span className="message-mark" aria-hidden="true">!</span>
              <div>
                <strong>We couldn’t prepare that score.</strong>
                <p>{diagnostic.message}</p>
                <code>{diagnostic.code}</code>
              </div>
            </section>
          )}
          {status === "selecting" && manifest && (
            <section className="message selection">
              <span className="message-mark" aria-hidden="true">→</span>
              <div className="selection-controls">
                <label htmlFor="score-choice">This package contains more than one score.</label>
                <select
                  id="score-choice"
                  value={selectedScoreId}
                  onChange={(event) => setSelectedScoreId(event.target.value)}
                >
                  {manifest.scores.map((score, index) => (
                    <option value={score.score_id} key={score.score_id}>
                      {score.title ?? `Untitled score ${index + 1}`}
                    </option>
                  ))}
                </select>
                <button type="button" onClick={() => void prepareSelectedScore()}>
                  Prepare score
                </button>
              </div>
            </section>
          )}
          {manifest && bundle && (
            <section className="message success">
              <span className="message-mark" aria-hidden="true">✓</span>
              <div>
                <p className="eyebrow">SCORE READY</p>
                <h2>{bundle.notation.title ?? manifest.scores[0]?.title ?? "Untitled score"}</h2>
                <p>
                  {bundle.playback.notes.length.toLocaleString()} sounding notes ·{" "}
                  {bundle.notation.renderer.anchors.length.toLocaleString()} notation anchors
                </p>
                <small>Your automatically generated Beginner lesson is ready below.</small>
              </div>
            </section>
          )}
        </div>
        {bundle && teachingPlan && presentation ? (
          <ExerciseLessonSurface
            plan={teachingPlan}
            presentation={presentation}
            notation={bundle.notation}
            loading={teachingLoading}
            onSelectExercise={(exerciseId) => void selectExercise(exerciseId)}
            onTempoChange={(tempoBpm) => selectExercise(presentation.exercise_id, tempoBpm)}
            teachingRun={teachingRun}
            onStartRun={beginTeachingRun}
            onSubmitAttempt={submitAttempt}
            onExportRun={downloadEvidence}
            onImportRun={resumeEvidence}
            onDeleteRun={removeTeachingRun}
            midiSession={config?.mobile ? remoteMidiSession ?? undefined : desktopMidiSession}
            localMidiSession={config?.mobile ? null : desktopMidiSession}
            onRemoteSubmit={remoteMidiSession
              ? (context) => remoteMidiSession.submitAttempt(context)
              : undefined}
          />
        ) : bundle ? (
          <>
            <PlaybackSurface
              plan={bundle.playback}
              onFocusEventIds={updatePlaybackFocus}
              onActiveNotes={updateActivePlaybackNotes}
            />
            <VirtualPiano activeNotes={activePlaybackNotes} />
            <NotationSurface
              bundle={bundle.notation}
              focusEventIds={playbackFocusEventIds}
            />
          </>
        ) : null}
      </section>

      <footer>
        <span>Local-first Beginner lesson</span>
        <span>Original uploads are not retained</span>
      </footer>
      </main>
    </>
  );
}
