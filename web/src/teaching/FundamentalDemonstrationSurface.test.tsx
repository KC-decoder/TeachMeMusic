import { render, screen } from "@testing-library/react";

import type { PlaybackPlan } from "../contracts/playback";
import type { ViewerBundle } from "../contracts/viewer";
import type {
  CurriculumPassageGuidanceView,
  CurriculumPassagePresentationView,
} from "./CurriculumDemonstrationSurface";
import {
  FundamentalDemonstrationSurface,
  type CurriculumFundamentalDemonstrationView,
  type CurriculumFundamentalExplanationView,
} from "./FundamentalDemonstrationSurface";

vi.mock("./CurriculumDemonstrationSurface", async () => {
  const actual = await vi.importActual<typeof import("./CurriculumDemonstrationSurface")>(
    "./CurriculumDemonstrationSurface",
  );
  return {
    ...actual,
    CurriculumDemonstrationSurface: ({
      presentation,
      guidance,
      playback,
    }: {
      presentation: CurriculumPassagePresentationView;
      guidance: CurriculumPassageGuidanceView;
      playback: PlaybackPlan;
    }) => (
      <div data-testid="existing-demonstration-boundary">
        {presentation.active_target_ids.join(",")} ·
        {guidance.items[0]?.heading} ·
        {guidance.items[0]?.focus_event_ids.join(",")} ·
        {playback.notes[0]?.source_events[0]?.event_id}
      </div>
    ),
  };
});

const reference = (type: string, id: string, fingerprint: string) => ({
  type,
  id,
  semantic_fingerprint: fingerprint,
});

const explanation: CurriculumFundamentalExplanationView = {
  id: "curriculum-fundamental-explanation:one",
  semantic_fingerprint: "a".repeat(64),
  analysis_id: "analysis:one",
  package_id: "package:one",
  score_id: "score:one",
  requirement_ref: reference("passage-skill-requirement", "requirement:one", "b".repeat(64)),
  primitive_ref: reference("learning-primitive", "PRIM-KEY-001", "c".repeat(64)),
  practice_scope_ref: reference(
    "practice-scope-assignment",
    "practice-scope-assignment:one",
    "d".repeat(64),
  ),
  presentation_ref: reference(
    "curriculum-passage-presentation",
    "curriculum-passage-presentation:one",
    "e".repeat(64),
  ),
  prerequisite_exercise_ref: reference(
    "exercise-instance",
    "exercise-instance:prerequisite",
    "f".repeat(64),
  ),
  application_exercise_ref: reference(
    "exercise-instance",
    "exercise-instance:application",
    "1".repeat(64),
  ),
  prerequisite_node_id: "curriculum-node:prerequisite",
  return_node_id: "curriculum-node:application",
  heading: "Keyboard focus",
  explanation: "Connect the highlighted score event to its key.",
  why_it_matters: "This prepares the chosen passage.",
  action_prompt: "Watch and listen to the highlighted note.",
  return_prompt: "Return to the chosen passage.",
  focus_event_ids: ["event:upper"],
  diagnostics: [],
  resolution: "resolved",
};

const presentation: CurriculumPassagePresentationView = {
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
};

const demonstration: CurriculumFundamentalDemonstrationView = {
  id: "curriculum-fundamental-demonstration:one",
  semantic_fingerprint: "3".repeat(64),
  analysis_id: explanation.analysis_id,
  package_id: explanation.package_id,
  score_id: explanation.score_id,
  explanation_ref: reference(
    "curriculum-fundamental-explanation",
    explanation.id,
    explanation.semantic_fingerprint,
  ),
  requirement_ref: explanation.requirement_ref,
  primitive_ref: explanation.primitive_ref,
  practice_scope_ref: explanation.practice_scope_ref,
  presentation_ref: explanation.presentation_ref,
  prerequisite_exercise_ref: explanation.prerequisite_exercise_ref,
  prerequisite_node_id: explanation.prerequisite_node_id,
  return_node_id: explanation.return_node_id,
  demonstration_activity_id: "exercise-activity:demonstrate",
  focus_event_ids: explanation.focus_event_ids,
  playback_source_event_ids: ["event:upper"],
  silent_active_event_ids: ["event:rest"],
  playback_plan_sha256: "4".repeat(64),
  tempo_bpm: { numerator: 60, denominator: 1 },
  diagnostics: [],
  resolution: "resolved",
};

const playback: PlaybackPlan = {
  contract_id: "org.teachmemusic.playback-plan",
  contract_version: "0.2.0",
  package_id: "package:one",
  score_id: "score:one",
  canonical_schema_id: "org.teachmemusic.canonical-music-package",
  canonical_schema_version: "2.0.0",
  duration_microseconds: 1_000_000,
  navigation_section_starts: [0],
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
  tempo_controls: [{
    id: "tempo:one",
    at_microseconds: 0,
    quarter_notes_per_minute: { numerator: 60, denominator: 1 },
    source_score_onset: { numerator: 0, denominator: 1 },
    origin: "caller-fallback",
    source_part_id: null,
    source_measure_id: null,
    source_order: null,
  }],
  grace_realizations: [],
  measure_visits: [],
  diagnostics: [],
};

const notation = {
  package_id: "package:one",
  score_id: "score:one",
} as ViewerBundle;

test("TEST-APP-TEACHING-018 binds one prerequisite to the existing demonstration path", () => {
  render(
    <FundamentalDemonstrationSurface
      demonstration={demonstration}
      explanation={explanation}
      presentation={presentation}
      notation={notation}
      playback={playback}
    />,
  );

  expect(screen.getByRole("heading", { name: "Keyboard focus" })).toBeVisible();
  expect(screen.getByText(/does not count as a learner attempt/)).toBeVisible();
  expect(screen.getByTestId("existing-demonstration-boundary")).toHaveTextContent(
    "event:upper,event:rest ·Keyboard focus ·event:upper ·event:upper",
  );
  expect(screen.getByLabelText("Keyboard focus")).toHaveAttribute(
    "data-return-node-id",
    "curriculum-node:application",
  );
});

test("TEST-APP-TEACHING-019 rejects a detached playback or return route", () => {
  render(
    <FundamentalDemonstrationSurface
      demonstration={{
        ...demonstration,
        return_node_id: "curriculum-node:foreign",
        playback_source_event_ids: ["event:lower"],
      }}
      explanation={explanation}
      presentation={presentation}
      notation={notation}
      playback={playback}
    />,
  );

  expect(screen.getByRole("alert")).toHaveTextContent(
    "The fundamental demonstration is not bound to this exact prerequisite",
  );
  expect(screen.getByRole("alert")).toHaveTextContent(
    "TMM_FUNDAMENTAL_DEMONSTRATION_MISMATCH",
  );
  expect(screen.queryByTestId("existing-demonstration-boundary")).not.toBeInTheDocument();
});
