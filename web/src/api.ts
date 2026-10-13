import type { PlaybackPlan } from "./contracts/playback";
import type { ViewerBundle } from "./contracts/viewer";
import type {
  CalibrationRecord,
  NormalizedMidiEvent,
  RawMidiMessage,
} from "./midi/contracts";

export interface AppConfig {
  app_contract_version: string;
  launch_token: string;
  accepted_extensions: string[];
  max_upload_bytes: number;
  mobile?: {
    pairing_id: string;
    phone_token: string;
  };
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
    id: string;
    tempo_bpm: ExactFraction | null;
    notation_visible: boolean;
    cursor_visible: boolean;
    note_names_visible: boolean;
    keyboard_highlighting: boolean;
    fingering_visible: boolean;
    demonstration_available: boolean;
    follow_mode: boolean;
    metronome: boolean;
    tempo_percent: number;
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
  contract_id: "org.teachmemusic.exercise-presentation" | "org.teachmemusic.curriculum-presentation";
  contract_version: "0.1.0" | "0.4.0";
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

export interface EvidenceInspection {
  run_id: string;
  score_digest_sha256: string;
  evidence_sha256: string;
  plan_count: number;
  audit_count: number;
  support_count: number;
  calibration_count: number;
  attempt_count: number;
  observation_count: number;
  evidence_record_count: number;
  feedback_count: number;
  policy_decision_count: number;
  journal_entry_count: number;
  gate_decision_count: number;
  event_count: number;
  latest_sequence_number: number | null;
  has_pedagogical_intervention: boolean;
  omissions: string[];
}

export interface TeachingRunResponse {
  app_contract_version: string;
  run_id: string;
  inspection: EvidenceInspection;
}

export interface TeachingRunAuthorization {
  captureSelfReport: boolean;
  allowExport: boolean;
}

export interface AttemptResult {
  app_contract_version: string;
  attempt_id: string;
  observations: Array<{
    id: string;
    dimension: string;
    status: string;
    blocking: boolean;
    expected_canonical_ids: string[];
    observed_event_ids: string[];
    expected_value: string | null;
    observed_value: string | null;
  }>;
  evidence_records: Array<{ id: string; dimension: string; state: string }>;
  feedback: {
    id: string;
    timing: "immediate" | "end-of-attempt";
    target: string;
    observation: string;
    boundary: string | null;
    action: string;
    reason: string;
  };
  decision: {
    id: string;
    action: string;
    next_node_id: string | null;
    reason: string;
  };
  mastery: {
    correct_note_count: number;
    expected_note_count: number;
    extra_note_count: number;
    green_percent: number;
    threshold_percent: number;
    action: "retry" | "slow-down" | "return-to-normal" | "exercise-complete";
    next_node_id: string | null;
    reduced_tempo: boolean;
  } | null;
  next_support: LessonExercise["initial_support"] | null;
  inspection: EvidenceInspection;
  plan?: TeachingPlan;
  presentation?: ExercisePresentation;
  curriculum?: object;
}

export interface AttemptSubmission {
  score_id: string;
  plan_id: string;
  exercise_id: string;
  practice_mode: string;
  support_state_id: string;
  tempo_bpm: number;
  count_in_enabled: boolean;
  started_at_utc: string;
  start_microseconds: number;
  end_microseconds: number;
  completion: "completed" | "interrupted" | "cancelled" | "input-failure" | "safe-stop";
  calibration: Omit<CalibrationRecord, "contract_id" | "contract_version" | "id" |
    "created_at_utc" | "raw_message_count" | "normalized_event_count" | "note_on_count" |
    "first_note">;
  raw_messages: RawMidiMessage[];
  normalized_events: NormalizedMidiEvent[];
  diagnostics: string[];
  unsafe_condition?: string;
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

function appHeaders(config: AppConfig, values: Record<string, string> = {}): Record<string, string> {
  const headers: Record<string, string> = {
    ...values,
    "X-TeachMeMusic-Token": config.launch_token,
  };
  if (config.mobile) {
    headers.Authorization = `Bearer ${config.mobile.phone_token}`;
    headers["X-TeachMeMusic-Mobile-Pairing"] = config.mobile.pairing_id;
  }
  return headers;
}

export async function getConfig(
  mobile?: NonNullable<AppConfig["mobile"]>,
): Promise<AppConfig> {
  const response = await fetch("/api/v1/config", {
    headers: mobile
      ? {
          Authorization: `Bearer ${mobile.phone_token}`,
          "X-TeachMeMusic-Mobile-Pairing": mobile.pairing_id,
        }
      : undefined,
  });
  return { ...(await checkedJson<AppConfig>(response)), ...(mobile ? { mobile } : {}) };
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
      headers: appHeaders(config),
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
      headers: appHeaders(config, {
        "Content-Type": "application/json",
      }),
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
    await fetch(`/api/v1/viewer-sessions/${encodeURIComponent(sessionId)}/curriculum-plans`, {
      method: "POST",
      headers: appHeaders(config, {
        "Content-Type": "application/json",
      }),
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
  runId?: string,
): Promise<ExercisePresentationResponse> {
  const path = runId
    ? `/api/v1/curriculum-runs/${encodeURIComponent(runId)}` +
      `/exercises/${encodeURIComponent(exerciseId)}`
    : `/api/v1/viewer-sessions/${encodeURIComponent(sessionId)}` +
      `/curriculum-plans/${encodeURIComponent(planId)}` +
      `/exercises/${encodeURIComponent(exerciseId)}`;
  return checkedJson<ExercisePresentationResponse>(
    await fetch(path, {
        method: "POST",
        headers: appHeaders(config, {
          "Content-Type": "application/json",
        }),
        body: JSON.stringify({
          score_id: scoreId,
          tempo_bpm: options.tempoBpm,
          count_in_enabled: options.countInEnabled ?? true,
        }),
      },
    ),
  );
}

export async function startTeachingRun(
  sessionId: string,
  scoreId: string,
  planId: string,
  config: AppConfig,
  authorization: TeachingRunAuthorization,
): Promise<TeachingRunResponse> {
  return checkedJson<TeachingRunResponse>(
    await fetch(`/api/v1/viewer-sessions/${encodeURIComponent(sessionId)}/curriculum-runs`, {
      method: "POST",
      headers: appHeaders(config, {
        "Content-Type": "application/json",
      }),
      body: JSON.stringify({
        score_id: scoreId,
        plan_id: planId,
        authorization_approved: true,
        capture_midi: true,
        capture_self_report: authorization.captureSelfReport,
        allow_export: authorization.allowExport,
        audit_outcome: "pass-no-change",
        source_faithful: true,
        musically_coherent: true,
        safe: true,
        executable: true,
        reviewer: "project-owner",
      }),
    }),
  );
}

export async function submitTeachingAttempt(
  runId: string,
  submission: AttemptSubmission,
  config: AppConfig,
): Promise<AttemptResult> {
  return checkedJson<AttemptResult>(
    await fetch(`/api/v1/curriculum-runs/${encodeURIComponent(runId)}/attempts`, {
      method: "POST",
      headers: appHeaders(config, {
        "Content-Type": "application/json",
      }),
      body: JSON.stringify(submission),
    }),
  );
}

export async function exportTeachingRun(runId: string, config: AppConfig): Promise<Blob> {
  const response = await fetch(`/api/v1/curriculum-runs/${encodeURIComponent(runId)}/exports`, {
    method: "POST",
    headers: appHeaders(config),
  });
  if (!response.ok) await checkedJson(response);
  return response.blob();
}

export async function importTeachingRun(
  sessionId: string,
  scoreId: string,
  archive: object,
  config: AppConfig,
): Promise<TeachingRunResponse> {
  return checkedJson<TeachingRunResponse>(
    await fetch(
      `/api/v1/viewer-sessions/${encodeURIComponent(sessionId)}/teaching-runs/import`,
      {
        method: "POST",
        headers: appHeaders(config, {
          "Content-Type": "application/json",
        }),
        body: JSON.stringify({ score_id: scoreId, archive }),
      },
    ),
  );
}

export async function deleteTeachingRun(runId: string, config: AppConfig): Promise<void> {
  const response = await fetch(`/api/v1/curriculum-runs/${encodeURIComponent(runId)}`, {
    method: "DELETE",
    headers: appHeaders(config),
  });
  if (!response.ok) await checkedJson(response);
}

export async function deleteSession(sessionId: string, config: AppConfig): Promise<void> {
  await fetch(`/api/v1/viewer-sessions/${encodeURIComponent(sessionId)}`, {
    method: "DELETE",
    headers: appHeaders(config),
  });
}
