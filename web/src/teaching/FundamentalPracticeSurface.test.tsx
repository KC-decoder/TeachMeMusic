import { act, fireEvent, render, screen } from "@testing-library/react";

import type { PlaybackPlan } from "../contracts/playback";
import type { ViewerBundle } from "../contracts/viewer";
import type { AttemptMidiSession, MidiSnapshot } from "../midi/contracts";
import type { CurriculumPassagePresentationView } from "./CurriculumDemonstrationSurface";
import type {
  CurriculumFundamentalDemonstrationView,
  CurriculumFundamentalExplanationView,
} from "./FundamentalDemonstrationSurface";
import {
  FundamentalPracticeSurface,
  type CurriculumExpectedPerformanceView,
  type CurriculumFundamentalPracticeView,
} from "./FundamentalPracticeSurface";

vi.mock("../notation/NotationSurface", () => ({
  NotationSurface: ({ focusEventIds }: { focusEventIds: string[] }) => (
    <div data-testid="practice-notation">{focusEventIds.join(",")}</div>
  ),
}));

const reference = (type: string, id: string, fingerprint: string) => ({
  type,
  id,
  semantic_fingerprint: fingerprint,
});

const explanation = {
  id: "curriculum-fundamental-explanation:one",
  semantic_fingerprint: "a".repeat(64),
  analysis_id: "analysis:one",
  package_id: "package:one",
  score_id: "score:one",
  requirement_ref: reference("passage-skill-requirement", "requirement:one", "b".repeat(64)),
  primitive_ref: reference("learning-primitive", "PRIM-KEY-001", "c".repeat(64)),
  practice_scope_ref: reference("practice-scope-assignment", "scope:one", "d".repeat(64)),
  presentation_ref: reference("curriculum-passage-presentation", "presentation:one", "e".repeat(64)),
  prerequisite_exercise_ref: reference("exercise-instance", "exercise:one", "f".repeat(64)),
  application_exercise_ref: reference("exercise-instance", "exercise:application", "1".repeat(64)),
  prerequisite_node_id: "node:prerequisite",
  return_node_id: "node:application",
  heading: "Keyboard focus",
  explanation: "Connect the note to its key.",
  why_it_matters: "It belongs to the chosen piece.",
  action_prompt: "Play the highlighted note.",
  return_prompt: "Return to the piece.",
  focus_event_ids: ["event:upper"],
  diagnostics: [],
  resolution: "resolved",
} as CurriculumFundamentalExplanationView;

const presentation = {
  id: explanation.presentation_ref.id,
  semantic_fingerprint: explanation.presentation_ref.semantic_fingerprint,
  analysis_id: explanation.analysis_id,
  package_id: explanation.package_id,
  score_id: explanation.score_id,
  practice_scope_ref: explanation.practice_scope_ref,
  notation_condition: "upper-layer",
  visible_event_ids: ["event:upper", "event:rest", "event:lower"],
  active_target_ids: ["event:upper", "event:rest"],
  inactive_context_ids: ["event:lower"],
  active_renderer_targets: [
    { canonical_id: "event:upper", canonical_kind: "event", renderer_anchor: "note:upper" },
    { canonical_id: "event:rest", canonical_kind: "event", renderer_anchor: "rest:upper" },
  ],
  inactive_renderer_targets: [
    { canonical_id: "event:lower", canonical_kind: "event", renderer_anchor: "note:lower" },
  ],
  visible_omitted_renderer_targets: [],
  notation_renderer_sha256: "2".repeat(64),
} as CurriculumPassagePresentationView;

const demonstration = {
  id: "curriculum-fundamental-demonstration:one",
  semantic_fingerprint: "3".repeat(64),
  analysis_id: explanation.analysis_id,
  package_id: explanation.package_id,
  score_id: explanation.score_id,
  explanation_ref: reference("curriculum-fundamental-explanation", explanation.id, explanation.semantic_fingerprint),
  requirement_ref: explanation.requirement_ref,
  primitive_ref: explanation.primitive_ref,
  practice_scope_ref: explanation.practice_scope_ref,
  presentation_ref: explanation.presentation_ref,
  prerequisite_exercise_ref: explanation.prerequisite_exercise_ref,
  prerequisite_node_id: explanation.prerequisite_node_id,
  return_node_id: explanation.return_node_id,
  demonstration_activity_id: "activity:demonstrate",
  focus_event_ids: explanation.focus_event_ids,
  playback_source_event_ids: ["event:upper"],
  silent_active_event_ids: ["event:rest"],
  playback_plan_sha256: "4".repeat(64),
  tempo_bpm: { numerator: 60, denominator: 1 },
  diagnostics: [],
  resolution: "resolved",
} as CurriculumFundamentalDemonstrationView;

const expected = {
  exercise_id: "curriculum-layer-attempt:target",
  practice_mode: "supported-performance",
  notes: [{
    id: "note:upper",
    midi_pitch: 72,
    expected_ids: ["event:upper"],
    start_microseconds: 0,
  }],
  target_dimensions: ["pitch", "order"],
  layer_target: {
    semantic_fingerprint: "5".repeat(64),
    active_event_ids: presentation.active_target_ids,
  },
} as CurriculumExpectedPerformanceView;

const practice = {
  id: "curriculum-fundamental-practice:one",
  semantic_fingerprint: "6".repeat(64),
  analysis_id: explanation.analysis_id,
  package_id: explanation.package_id,
  score_id: explanation.score_id,
  explanation_ref: demonstration.explanation_ref,
  demonstration_ref: reference("curriculum-fundamental-demonstration", demonstration.id, demonstration.semantic_fingerprint),
  requirement_ref: explanation.requirement_ref,
  primitive_ref: explanation.primitive_ref,
  practice_scope_ref: explanation.practice_scope_ref,
  presentation_ref: explanation.presentation_ref,
  prerequisite_exercise_ref: explanation.prerequisite_exercise_ref,
  prerequisite_node_id: explanation.prerequisite_node_id,
  return_node_id: explanation.return_node_id,
  performance_activity_id: "activity:perform",
  practice_mode: "supported-performance",
  support_envelope: {
    initial_condition: "guided",
    permitted_conditions: ["guided", "reduced-support", "independent"],
    independent_condition: "independent",
  },
  required_evidence_exits: [{
    dimension: "pitch",
    evidence_context: "acquisition",
    minimum_state: "stable-supported",
  }],
  expected_performance_id: expected.exercise_id,
  expected_target_fingerprint: expected.layer_target.semantic_fingerprint,
  expected_active_event_ids: presentation.active_target_ids,
  expected_note_ids: ["note:upper"],
  target_dimensions: expected.target_dimensions,
  expected_performance_sha256: "7".repeat(64),
  diagnostics: [],
  resolution: "resolved",
} as CurriculumFundamentalPracticeView;

const playback = {
  package_id: explanation.package_id,
  score_id: explanation.score_id,
  notes: [{
    id: "note:upper",
    start_microseconds: 0,
    end_microseconds: 1_000_000,
    midi_pitch: 72,
    chord_id: null,
    dynamic_percent: null,
    source_events: [{
      event_id: "event:upper",
      part_id: "part:one",
      measure_id: "measure:one",
      staff: "1",
      voice: "1",
      score_onset: { numerator: 0, denominator: 1 },
      clef_group_id: "clef:treble",
      clef: { sign: "G", line: 2, octave_change: null },
    }],
  }],
} as PlaybackPlan;

function approvedSnapshot(): MidiSnapshot {
  return {
    permission: "granted",
    connection: "connected",
    capture: "idle",
    capture_purpose: null,
    capture_started_at_utc: null,
    capture_start_microseconds: null,
    capture_end_microseconds: null,
    inputs: [],
    selected_input_id: "casio",
    raw_messages: [],
    normalized_events: [],
    diagnostics: [],
    active_notes: [],
    calibration: { approved: true } as MidiSnapshot["calibration"],
  };
}

class FakeSession implements AttemptMidiSession {
  snapshot = approvedSnapshot();
  listener: ((snapshot: MidiSnapshot) => void) | null = null;

  current() { return this.snapshot; }
  subscribe(listener: (snapshot: MidiSnapshot) => void) {
    this.listener = listener;
    return () => { this.listener = null; };
  }
  update(values: Partial<MidiSnapshot>) {
    this.snapshot = { ...this.snapshot, ...values };
    this.listener?.(this.snapshot);
  }
  startAttempt() {
    this.update({ capture: "recording", capture_purpose: "attempt", capture_start_microseconds: 100 });
  }
  stopAttempt() { this.update({ capture: "stopped", capture_end_microseconds: 200 }); }
  pauseAttempt() { this.update({ capture: "paused" }); }
  resumeAttempt() { this.update({ capture: "recording" }); }
  abortAttempt() { this.update({ capture: "aborted" }); }
  stopAttemptForDiscomfort() { this.update({ capture: "aborted" }); }
}

const notation = { package_id: "package:one", score_id: "score:one" } as ViewerBundle;

test("TEST-APP-TEACHING-020 captures the exact prerequisite perform activity", () => {
  const session = new FakeSession();
  const ready = vi.fn();
  render(
    <FundamentalPracticeSurface
      practice={practice}
      expected={expected}
      explanation={explanation}
      demonstration={demonstration}
      presentation={presentation}
      notation={notation}
      playback={playback}
      session={session}
      onAttemptReady={ready}
    />,
  );

  expect(screen.getByRole("heading", { name: "Play Keyboard focus" })).toBeVisible();
  expect(screen.getByTestId("practice-notation")).toHaveTextContent("event:upper");
  expect(screen.getByText(/measured separately from the demonstration/)).toBeVisible();
  fireEvent.click(screen.getByRole("button", { name: "Start attempt" }));
  act(() => session.update({ active_notes: [72] }));
  expect(screen.getByLabelText(/C5, expected sounding.*learner played, match/)).toBeVisible();
  fireEvent.click(screen.getByRole("button", { name: "Finish attempt" }));

  expect(ready).toHaveBeenCalledWith(
    expect.objectContaining({ capture: "stopped", capture_purpose: "attempt" }),
    expect.objectContaining({
      practice_id: practice.id,
      expected_performance_id: expected.exercise_id,
      support_condition: "guided",
      evidence_exits: practice.required_evidence_exits,
    }),
  );
  expect(screen.getByRole("status")).toHaveTextContent("ready for factual comparison");
});

test("TEST-APP-TEACHING-021 rejects demonstration or expected-target drift", () => {
  render(
    <FundamentalPracticeSurface
      practice={{
        ...practice,
        performance_activity_id: demonstration.demonstration_activity_id,
        expected_active_event_ids: ["event:lower"],
      }}
      expected={expected}
      explanation={explanation}
      demonstration={demonstration}
      presentation={presentation}
      notation={notation}
      playback={playback}
      session={new FakeSession()}
      onAttemptReady={vi.fn()}
    />,
  );

  expect(screen.getByRole("alert")).toHaveTextContent(
    "The learner exercise is not bound to this exact prerequisite",
  );
  expect(screen.queryByRole("button", { name: "Start attempt" })).not.toBeInTheDocument();
});
