import { ChangeEvent, useCallback, useEffect, useRef, useState } from "react";

import {
  ApiError,
  AppConfig,
  Diagnostic,
  PreparedBundle,
  SessionManifest,
  TeachingPlan,
  ExercisePresentation,
  deleteSession,
  getConfig,
  prepareExercise,
  prepareScore,
  prepareTeachingPlan,
  uploadScore,
} from "./api";
import { NotationSurface } from "./notation/NotationSurface";
import { PlaybackSurface } from "./playback/PlaybackSurface";
import type { ActivePlaybackNote } from "./audio/PlaybackTransport";
import { VirtualPiano } from "./piano/VirtualPiano";
import { ExerciseLessonSurface } from "./teaching/ExerciseLessonSurface";

type Status = "starting" | "idle" | "loading" | "selecting" | "ready" | "error";

const fallbackDiagnostic: Diagnostic = {
  code: "APP_CONNECTION_FAILED",
  stage: "application",
  message: "The local TeachMeMusic service is unavailable.",
};

export function App() {
  const [config, setConfig] = useState<AppConfig | null>(null);
  const [status, setStatus] = useState<Status>("starting");
  const [manifest, setManifest] = useState<SessionManifest | null>(null);
  const [bundle, setBundle] = useState<PreparedBundle | null>(null);
  const [selectedScoreId, setSelectedScoreId] = useState("");
  const [teachingPlan, setTeachingPlan] = useState<TeachingPlan | null>(null);
  const [presentation, setPresentation] = useState<ExercisePresentation | null>(null);
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
    void getConfig()
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
    };
  }, []);

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
      );
      setPresentation(result.presentation);
    } catch (error) {
      setDiagnostic(error instanceof ApiError ? error.diagnostic : fallbackDiagnostic);
    } finally {
      setTeachingLoading(false);
    }
  }

  return (
    <main className="app-shell">
      <header className="masthead">
        <a className="wordmark" href="/" aria-label="TeachMeMusic home">
          <span aria-hidden="true">♪</span> TeachMeMusic
        </a>
        <span className="phase">Beginner lesson preview</span>
      </header>

      <section className="hero" aria-labelledby="page-title">
        <p className="eyebrow">DEV-008 · BEGINNER TEACHING</p>
        <h1 id="page-title">Bring a score.<br />Learn it step by step.</h1>
        <p className="lede">
          Load MusicXML from your computer. TeachMeMusic validates it, creates a traceable
          Beginner lesson, and demonstrates each bounded exercise.
        </p>

        <label className={`upload-card ${status === "loading" ? "is-loading" : ""}`}>
          <input
            type="file"
            accept=".xml,.musicxml,.mxl"
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
            onTempoChange={(tempoBpm) => void selectExercise(presentation.exercise_id, tempoBpm)}
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
  );
}
