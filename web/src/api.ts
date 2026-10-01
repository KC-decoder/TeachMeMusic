import type { PlaybackPlan } from "./contracts/playback";
import type { ViewerBundle } from "./contracts/viewer";

export interface AppConfig {
  app_contract_version: string;
  launch_token: string;
  accepted_extensions: string[];
  max_upload_bytes: number;
}

export interface ScoreChoice {
  score_id: string;
  title: string | null;
}

export interface SessionManifest {
  session_id: string;
  package_id: string;
  expires_in_seconds: number;
  scores: ScoreChoice[];
  diagnostics: Diagnostic[];
}

export interface Diagnostic {
  code: string;
  stage: string;
  message: string;
}

export interface PreparedBundle {
  app_contract_version: string;
  notation: ViewerBundle;
  playback: PlaybackPlan;
}

export interface ExactFraction {
  numerator: number;
  denominator: number;
}

export interface LessonExercise {
  id: string;
  primary_skill: string;
  secondary_skills: string[];
  practice_modes: string[];
  boundary_reason: string;
  initial_support: {
    tempo_bpm: ExactFraction | null;
    notation_visible: boolean;
    keyboard_highlighting: boolean;
    prompts_visible: boolean;
  };
}

export interface LessonNode {
  id: string;
  kind: "exercise" | "integration" | "retention" | "transfer";
  exercise_id: string;
  prerequisites: string[];
  successors: string[];
}

export interface TeachingPlan {
  id: string;
  run_id: string;
  track: "beginner";
  exercises: LessonExercise[];
  nodes: LessonNode[];
  root_node_ids: string[];
  diagnostics: string[];
}

export interface TeachingPlanResponse {
  app_contract_version: string;
  plan: TeachingPlan;
}

export interface ExercisePresentation {
  contract_id: "org.teachmemusic.exercise-presentation";
  contract_version: "0.1.0";
  plan_id: string;
  exercise_id: string;
  package_id: string;
  score_id: string;
  expected_content_sha256: string;
  material_kind: "canonical" | "synthetic-transfer";
  measure_ids: string[];
  event_ids: string[];
  provenance_ids: string[];
  measure_numbers: string[];
  primary_skill: string;
  practice_modes: string[];
  boundary_reason: string;
  aid_state: {
    tempo_bpm: ExactFraction;
    count_in_enabled: boolean;
    count_in_beats: number;
    count_in_beat_microseconds: number;
    notation_visible: boolean;
    keyboard_visible: boolean;
    pitch_prompts_visible: boolean;
  };
  notation_renderer_sha256: string | null;
  demonstration: PlaybackPlan;
  diagnostics: string[];
}

export interface ExercisePresentationResponse {
  app_contract_version: string;
  presentation: ExercisePresentation;
}

export class ApiError extends Error {
  readonly diagnostic: Diagnostic;

  constructor(diagnostic: Diagnostic) {
    super(diagnostic.message);
    this.diagnostic = diagnostic;
  }
}

async function checkedJson<T>(response: Response): Promise<T> {
  const data = (await response.json()) as T & { diagnostics?: Diagnostic[] };
  if (!response.ok) {
    throw new ApiError(
      data.diagnostics?.[0] ?? {
        code: "APP_REQUEST_FAILED",
        stage: "application",
        message: "TeachMeMusic could not complete the request.",
      },
    );
  }
  return data;
}

export async function getConfig(): Promise<AppConfig> {
  return checkedJson<AppConfig>(await fetch("/api/v1/config"));
}

export async function uploadScore(
  file: File,
  config: AppConfig,
): Promise<SessionManifest> {
  const body = new FormData();
  body.append("score", file);
  return checkedJson<SessionManifest>(
    await fetch("/api/v1/viewer-sessions", {
      method: "POST",
      headers: { "X-TeachMeMusic-Token": config.launch_token },
      body,
    }),
  );
}

export async function prepareScore(
  sessionId: string,
  scoreId: string,
  config: AppConfig,
): Promise<PreparedBundle> {
  return checkedJson<PreparedBundle>(
    await fetch(`/api/v1/viewer-sessions/${encodeURIComponent(sessionId)}/bundles`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-TeachMeMusic-Token": config.launch_token,
      },
      body: JSON.stringify({
        score_id: scoreId,
        fallback_tempo_qpm: 120,
        grace_fallback_percent: 25,
      }),
    }),
  );
}

export async function prepareTeachingPlan(
  sessionId: string,
  scoreId: string,
  config: AppConfig,
): Promise<TeachingPlanResponse> {
  return checkedJson<TeachingPlanResponse>(
    await fetch(`/api/v1/viewer-sessions/${encodeURIComponent(sessionId)}/teaching-plans`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-TeachMeMusic-Token": config.launch_token,
      },
      body: JSON.stringify({ score_id: scoreId }),
    }),
  );
}

export async function prepareExercise(
  sessionId: string,
  scoreId: string,
  planId: string,
  exerciseId: string,
  config: AppConfig,
  options: { tempoBpm?: number; countInEnabled?: boolean } = {},
): Promise<ExercisePresentationResponse> {
  return checkedJson<ExercisePresentationResponse>(
    await fetch(
      `/api/v1/viewer-sessions/${encodeURIComponent(sessionId)}` +
        `/teaching-plans/${encodeURIComponent(planId)}` +
        `/exercises/${encodeURIComponent(exerciseId)}`,
      {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-TeachMeMusic-Token": config.launch_token,
        },
        body: JSON.stringify({
          score_id: scoreId,
          tempo_bpm: options.tempoBpm,
          count_in_enabled: options.countInEnabled ?? true,
        }),
      },
    ),
  );
}

export async function deleteSession(sessionId: string, config: AppConfig): Promise<void> {
  await fetch(`/api/v1/viewer-sessions/${encodeURIComponent(sessionId)}`, {
    method: "DELETE",
    headers: { "X-TeachMeMusic-Token": config.launch_token },
  });
}
