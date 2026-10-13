import { useEffect, useMemo, useRef, useState } from "react";

import type { ActivePlaybackNote } from "../audio/PlaybackTransport";
import type { PlaybackPlan } from "../contracts/playback";
import type { ViewerBundle } from "../contracts/viewer";
import type { AttemptMidiSession, MidiSnapshot } from "../midi/contracts";
import { NotationSurface } from "../notation/NotationSurface";
import { VirtualPiano } from "../piano/VirtualPiano";
import type { CurriculumPassagePresentationView } from "./CurriculumDemonstrationSurface";
import type {
  CurriculumFundamentalDemonstrationView,
  CurriculumFundamentalExplanationView,
} from "./FundamentalDemonstrationSurface";

interface ExerciseEvidenceExitView {
  dimension: string;
  evidence_context: string;
  minimum_state: string;
}

export interface CurriculumExpectedPerformanceView {
  exercise_id: string;
  practice_mode: string;
  notes: Array<{
    id: string;
    midi_pitch: number;
    expected_ids: string[];
    start_microseconds: number;
  }>;
  target_dimensions: string[];
  layer_target: {
    semantic_fingerprint: string;
    active_event_ids: string[];
  };
}

export interface CurriculumFundamentalPracticeView {
  id: string;
  semantic_fingerprint: string;
  analysis_id: string;
  package_id: string;
  score_id: string;
  explanation_ref: CurriculumFundamentalDemonstrationView["explanation_ref"];
  demonstration_ref: CurriculumFundamentalDemonstrationView["explanation_ref"];
  requirement_ref: CurriculumFundamentalDemonstrationView["requirement_ref"];
  primitive_ref: CurriculumFundamentalDemonstrationView["primitive_ref"];
  practice_scope_ref: CurriculumFundamentalDemonstrationView["practice_scope_ref"];
  presentation_ref: CurriculumFundamentalDemonstrationView["presentation_ref"];
  prerequisite_exercise_ref: CurriculumFundamentalDemonstrationView["prerequisite_exercise_ref"];
  prerequisite_node_id: string;
  return_node_id: string;
  performance_activity_id: string;
  practice_mode: "supported-performance";
  support_envelope: {
    initial_condition: string;
    permitted_conditions: string[];
    independent_condition: string | null;
  };
  required_evidence_exits: ExerciseEvidenceExitView[];
  expected_performance_id: string;
  expected_target_fingerprint: string;
  expected_active_event_ids: string[];
  expected_note_ids: string[];
  target_dimensions: string[];
  expected_performance_sha256: string;
  diagnostics: unknown[];
  resolution: "resolved" | "review-required" | "unsupported" | "fatal";
}

export interface CurriculumAttemptReadyContext {
  practice_id: string;
  expected_performance_id: string;
  practice_mode: string;
  support_condition: string;
  evidence_exits: ExerciseEvidenceExitView[];
}

interface FundamentalPracticeSurfaceProps {
  practice: CurriculumFundamentalPracticeView;
  expected: CurriculumExpectedPerformanceView;
  explanation: CurriculumFundamentalExplanationView;
  demonstration: CurriculumFundamentalDemonstrationView;
  presentation: CurriculumPassagePresentationView;
  notation: ViewerBundle;
  playback: PlaybackPlan;
  session: AttemptMidiSession;
  onAttemptReady: (
    snapshot: MidiSnapshot,
    context: CurriculumAttemptReadyContext,
  ) => void;
}

class FundamentalPracticeError extends Error {
  constructor(readonly code: string, message: string) {
    super(message);
  }
}

function sameSequence(left: readonly string[], right: readonly string[]): boolean {
  return left.length === right.length && left.every((id, index) => id === right[index]);
}

function requireValidPracticeBinding(
  practice: CurriculumFundamentalPracticeView,
  expected: CurriculumExpectedPerformanceView,
  explanation: CurriculumFundamentalExplanationView,
  demonstration: CurriculumFundamentalDemonstrationView,
  presentation: CurriculumPassagePresentationView,
  playback: PlaybackPlan,
): void {
  const expectedSources = playback.notes.flatMap((note) =>
    note.source_events.map((source) => source.event_id)
  );
  const invalid =
    practice.resolution !== "resolved" ||
    practice.diagnostics.length > 0 ||
    practice.analysis_id !== explanation.analysis_id ||
    practice.package_id !== explanation.package_id ||
    practice.score_id !== explanation.score_id ||
    practice.explanation_ref.id !== explanation.id ||
    practice.explanation_ref.semantic_fingerprint !== explanation.semantic_fingerprint ||
    practice.demonstration_ref.id !== demonstration.id ||
    practice.demonstration_ref.semantic_fingerprint !== demonstration.semantic_fingerprint ||
    practice.requirement_ref.id !== explanation.requirement_ref.id ||
    practice.primitive_ref.id !== explanation.primitive_ref.id ||
    practice.practice_scope_ref.id !== presentation.practice_scope_ref.id ||
    practice.presentation_ref.id !== presentation.id ||
    practice.prerequisite_exercise_ref.id !== explanation.prerequisite_exercise_ref.id ||
    practice.prerequisite_node_id !== explanation.prerequisite_node_id ||
    practice.return_node_id !== explanation.return_node_id ||
    practice.return_node_id !== demonstration.return_node_id ||
    practice.performance_activity_id === demonstration.demonstration_activity_id ||
    !practice.performance_activity_id.trim() ||
    practice.practice_mode !== "supported-performance" ||
    practice.expected_performance_id !== expected.exercise_id ||
    expected.practice_mode !== practice.practice_mode ||
    practice.expected_target_fingerprint !== expected.layer_target.semantic_fingerprint ||
    !sameSequence(practice.expected_active_event_ids, presentation.active_target_ids) ||
    !sameSequence(practice.expected_active_event_ids, expected.layer_target.active_event_ids) ||
    !sameSequence(practice.expected_note_ids, expected.notes.map((note) => note.id)) ||
    !sameSequence(practice.expected_note_ids, playback.notes.map((note) => note.id)) ||
    !sameSequence(practice.target_dimensions, expected.target_dimensions) ||
    expectedSources.some((id) => !practice.expected_active_event_ids.includes(id)) ||
    expected.notes.some((note) =>
      note.expected_ids.some((id) => !practice.expected_active_event_ids.includes(id))
    ) ||
    !/^[0-9a-f]{64}$/.test(practice.expected_performance_sha256) ||
    practice.support_envelope.permitted_conditions.length === 0 ||
    !practice.support_envelope.permitted_conditions.includes(
      practice.support_envelope.initial_condition,
    ) ||
    practice.required_evidence_exits.length === 0 ||
    practice.required_evidence_exits.some((item) =>
      item.evidence_context !== "acquisition" || !item.dimension || !item.minimum_state
    );
  if (invalid) {
    throw new FundamentalPracticeError(
      "TMM_FUNDAMENTAL_PRACTICE_MISMATCH",
      "The learner exercise is not bound to this exact prerequisite and expected performance.",
    );
  }
}

function noteGroups(playback: PlaybackPlan): ActivePlaybackNote[][] {
  const grouped = new Map<number, PlaybackPlan["notes"]>();
  for (const note of playback.notes) {
    grouped.set(note.start_microseconds, [...(grouped.get(note.start_microseconds) ?? []), note]);
  }
  return [...grouped.entries()]
    .sort(([left], [right]) => left - right)
    .map(([, notes]) => notes.map((note) => ({
      noteId: note.id,
      midiPitch: note.midi_pitch,
      contributions: note.source_events.map((source) => ({
        eventId: source.event_id,
        clefGroupId: source.clef_group_id,
        clef: source.clef,
        staff: source.staff,
        voice: source.voice,
      })),
    })));
}

export function FundamentalPracticeSurface({
  practice,
  expected,
  explanation,
  demonstration,
  presentation,
  notation,
  playback,
  session,
  onAttemptReady,
}: FundamentalPracticeSurfaceProps) {
  const validationError = useMemo(() => {
    try {
      requireValidPracticeBinding(
        practice,
        expected,
        explanation,
        demonstration,
        presentation,
        playback,
      );
      return null;
    } catch (reason: unknown) {
      return reason instanceof FundamentalPracticeError
        ? reason
        : new FundamentalPracticeError(
            "TMM_FUNDAMENTAL_PRACTICE_INVALID",
            "The prerequisite learner exercise was rejected.",
          );
    }
  }, [demonstration, expected, explanation, playback, practice, presentation]);
  const [snapshot, setSnapshot] = useState(() => session.current());
  const [promptIndex, setPromptIndex] = useState(0);
  const groups = useMemo(() => noteGroups(playback), [playback]);
  const prompt = groups[promptIndex] ?? [];
  const previousHeld = useRef<Set<number>>(new Set());
  const matched = useRef<Set<number>>(new Set());
  const submittedCaptureEnd = useRef<number | null>(null);

  useEffect(() => session.subscribe(setSnapshot), [session]);
  useEffect(() => {
    if (snapshot.capture !== "recording" || prompt.length === 0) {
      previousHeld.current = new Set(snapshot.active_notes);
      return;
    }
    const held = new Set(snapshot.active_notes);
    const newlyPressed = [...held].filter((pitch) => !previousHeld.current.has(pitch));
    previousHeld.current = held;
    const target = new Set(prompt.map((note) => note.midiPitch));
    newlyPressed.filter((pitch) => target.has(pitch)).forEach((pitch) => matched.current.add(pitch));
    if (![...target].every((pitch) => matched.current.has(pitch))) return;
    matched.current.clear();
    setPromptIndex((index) => Math.min(index + 1, groups.length - 1));
  }, [groups.length, prompt, snapshot.active_notes, snapshot.capture]);
  useEffect(() => {
    if (
      snapshot.capture_purpose !== "attempt" ||
      snapshot.capture !== "stopped" ||
      snapshot.capture_end_microseconds === null ||
      submittedCaptureEnd.current === snapshot.capture_end_microseconds
    ) return;
    submittedCaptureEnd.current = snapshot.capture_end_microseconds;
    onAttemptReady(snapshot, {
      practice_id: practice.id,
      expected_performance_id: practice.expected_performance_id,
      practice_mode: practice.practice_mode,
      support_condition: practice.support_envelope.initial_condition,
      evidence_exits: practice.required_evidence_exits,
    });
  }, [onAttemptReady, practice, snapshot]);

  if (validationError) {
    return (
      <div className="playback-error" role="alert">
        <strong>{validationError.message}</strong>
        <code>{validationError.code}</code>
      </div>
    );
  }

  const ready = snapshot.connection === "connected" && snapshot.calibration?.approved === true;
  const active = snapshot.capture_purpose === "attempt" &&
    (snapshot.capture === "recording" || snapshot.capture === "paused");
  const focusEventIds = prompt.flatMap((note) => note.contributions.map((item) => item.eventId));

  return (
    <section
      className="fundamental-practice"
      aria-labelledby="fundamental-practice-heading"
      data-practice-id={practice.id}
      data-prerequisite-node-id={practice.prerequisite_node_id}
      data-return-node-id={practice.return_node_id}
    >
      <header className="fundamental-demonstration-header">
        <p className="eyebrow">YOUR TURN</p>
        <h2 id="fundamental-practice-heading">Play {explanation.heading}</h2>
        <p>{explanation.action_prompt}</p>
        <p>
          Start with <strong>{practice.support_envelope.initial_condition}</strong> support.
          This attempt is measured separately from the demonstration.
        </p>
      </header>
      <NotationSurface
        bundle={notation}
        focusEventIds={focusEventIds}
        allowedEventIds={presentation.visible_event_ids}
        layerEmphasis={{
          label: "Prerequisite practice target",
          activeTargets: presentation.active_renderer_targets,
          inactiveTargets: [
            ...presentation.inactive_renderer_targets,
            ...presentation.visible_omitted_renderer_targets,
          ],
        }}
      />
      <VirtualPiano
        activeNotes={prompt}
        playedMidiPitches={snapshot.active_notes}
        learnerInputStatus={!ready ? "unavailable" : active ? "capturing" : "connected"}
        guidanceMode="practice"
      />
      <div className="attempt-actions">
        {!active && (
          <button type="button" className="midi-primary" disabled={!ready} onClick={() => {
            setPromptIndex(0);
            matched.current.clear();
            session.startAttempt();
          }}>
            Start attempt
          </button>
        )}
        {snapshot.capture === "recording" && (
          <>
            <button type="button" className="midi-primary" onClick={() => session.stopAttempt()}>
              Finish attempt
            </button>
            <button type="button" onClick={() => session.pauseAttempt()}>Pause</button>
          </>
        )}
        {snapshot.capture === "paused" && (
          <>
            <button type="button" className="midi-primary" onClick={() => session.resumeAttempt()}>
              Resume
            </button>
            <button type="button" onClick={() => session.stopAttempt()}>Finish attempt</button>
          </>
        )}
        {active && (
          <>
            <button type="button" onClick={() => session.abortAttempt()}>Abort without penalty</button>
            <button type="button" onClick={() => session.stopAttemptForDiscomfort()}>
              Stop — discomfort
            </button>
          </>
        )}
      </div>
      <p role="status">
        {!ready
          ? "Connect and approve the calibrated piano before playing."
          : snapshot.capture === "recording"
            ? `Playing target ${promptIndex + 1} of ${groups.length}.`
            : snapshot.capture === "stopped"
              ? "Attempt captured and ready for factual comparison."
              : "Ready to play."}
      </p>
      <details>
        <summary>What this attempt measures</summary>
        <ul>
          {practice.required_evidence_exits.map((item) => (
            <li key={item.dimension}>{item.dimension}: {item.minimum_state}</li>
          ))}
        </ul>
      </details>
    </section>
  );
}
