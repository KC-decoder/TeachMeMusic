import { fireEvent, render, screen } from "@testing-library/react";

import type { ViewerBundle } from "../contracts/viewer";
import type { CurriculumPassagePresentationView } from "./CurriculumDemonstrationSurface";
import type { CurriculumFundamentalExplanationView } from "./FundamentalDemonstrationSurface";
import type { CurriculumFundamentalPracticeView } from "./FundamentalPracticeSurface";
import {
  FundamentalReturnSurface,
  type CurriculumMasteryProjectionView,
  type CurriculumPieceReturnView,
  type CurriculumUnlockDecisionView,
} from "./FundamentalReturnSurface";

vi.mock("../notation/NotationSurface", () => ({
  NotationSurface: ({ focusEventIds }: { focusEventIds: string[] }) => (
    <div data-testid="return-notation">{focusEventIds.join(",")}</div>
  ),
}));

const reference = (type: string, id: string, fingerprint: string) => ({
  type,
  id,
  semantic_fingerprint: fingerprint,
});

const requirementRef = reference("passage-skill-requirement", "requirement:one", "a".repeat(64));
const primitiveRef = reference("learning-primitive", "PRIM-KEY-001", "b".repeat(64));
const scopeRef = reference("practice-scope-assignment", "scope:one", "c".repeat(64));
const presentationRef = reference(
  "curriculum-passage-presentation",
  "presentation:one",
  "d".repeat(64),
);
const prerequisiteExerciseRef = reference("exercise-instance", "exercise:prerequisite", "e".repeat(64));
const applicationExerciseRef = reference("exercise-instance", "exercise:application", "f".repeat(64));
const graphRef = reference("acquisition-graph-slice", "graph:one", "1".repeat(64));
const supportRef = reference("support-state", "support:guided", "2".repeat(64));

const explanation = {
  id: "curriculum-fundamental-explanation:one",
  semantic_fingerprint: "3".repeat(64),
  analysis_id: "analysis:one",
  package_id: "package:one",
  score_id: "score:one",
  requirement_ref: requirementRef,
  primitive_ref: primitiveRef,
  practice_scope_ref: scopeRef,
  presentation_ref: presentationRef,
  prerequisite_exercise_ref: prerequisiteExerciseRef,
  application_exercise_ref: applicationExerciseRef,
  prerequisite_node_id: "node:prerequisite",
  return_node_id: "node:application",
  heading: "Keyboard geography",
  explanation: "Connect the note to its key.",
  why_it_matters: "The chosen piece uses this skill.",
  action_prompt: "Play the target.",
  return_prompt: "Now use the same skill in the highlighted passage.",
  focus_event_ids: ["event:one"],
  diagnostics: [],
  resolution: "resolved",
} as CurriculumFundamentalExplanationView;

const presentation = {
  id: presentationRef.id,
  semantic_fingerprint: presentationRef.semantic_fingerprint,
  analysis_id: explanation.analysis_id,
  package_id: explanation.package_id,
  score_id: explanation.score_id,
  practice_scope_ref: scopeRef,
  notation_condition: "single-layer",
  visible_event_ids: ["event:one", "event:context"],
  active_target_ids: ["event:one"],
  inactive_context_ids: ["event:context"],
  active_renderer_targets: [
    { canonical_id: "event:one", canonical_kind: "event", renderer_anchor: "note:one" },
  ],
  inactive_renderer_targets: [
    { canonical_id: "event:context", canonical_kind: "event", renderer_anchor: "note:context" },
  ],
  visible_omitted_renderer_targets: [],
  notation_renderer_sha256: "4".repeat(64),
} as CurriculumPassagePresentationView;

const practice = {
  id: "curriculum-fundamental-practice:one",
  semantic_fingerprint: "5".repeat(64),
  analysis_id: explanation.analysis_id,
  package_id: explanation.package_id,
  score_id: explanation.score_id,
  explanation_ref: reference(
    "curriculum-fundamental-explanation",
    explanation.id,
    explanation.semantic_fingerprint,
  ),
  demonstration_ref: reference("curriculum-fundamental-demonstration", "demonstration:one", "6".repeat(64)),
  requirement_ref: requirementRef,
  primitive_ref: primitiveRef,
  practice_scope_ref: scopeRef,
  presentation_ref: presentationRef,
  prerequisite_exercise_ref: prerequisiteExerciseRef,
  prerequisite_node_id: explanation.prerequisite_node_id,
  return_node_id: explanation.return_node_id,
  performance_activity_id: "activity:perform",
  practice_mode: "supported-performance",
  support_envelope: {
    initial_condition: "guided",
    permitted_conditions: ["guided", "independent"],
    independent_condition: "independent",
  },
  required_evidence_exits: [
    { dimension: "pitch", evidence_context: "acquisition", minimum_state: "stable-supported" },
  ],
  expected_performance_id: "expected:one",
  expected_target_fingerprint: "7".repeat(64),
  expected_active_event_ids: ["event:one"],
  expected_note_ids: ["note:one"],
  target_dimensions: ["pitch"],
  expected_performance_sha256: "8".repeat(64),
  diagnostics: [],
  resolution: "resolved",
} as CurriculumFundamentalPracticeView;

const mastery = {
  id: "curriculum-mastery-projection:one",
  semantic_fingerprint: "9".repeat(64),
  graph_ref: graphRef,
  node_id: practice.prerequisite_node_id,
  exercise_ref: prerequisiteExerciseRef,
  requirement_ref: requirementRef,
  primitive_ref: primitiveRef,
  practice_scope_ref: scopeRef,
  support_state_ref: supportRef,
  dimension_decisions: [{ evidence_record_ids: ["evidence:pitch"] }],
  complete_passing_attempt_ids: ["attempt:one", "attempt:two"],
  status: "mastered",
} as CurriculumMasteryProjectionView;

const decision = {
  id: "curriculum-unlock-decision:one",
  semantic_fingerprint: "0".repeat(64),
  graph_ref: graphRef,
  current_node_id: practice.prerequisite_node_id,
  projection_ref: reference(
    "curriculum-mastery-projection",
    mastery.id,
    mastery.semantic_fingerprint,
  ),
  selected_edge_id: "edge:return",
  next_node_id: practice.return_node_id,
  action: "unlock-successor",
} as CurriculumUnlockDecisionView;

const handoff = {
  id: "curriculum-piece-return:one",
  semantic_fingerprint: "a".repeat(64),
  analysis_id: practice.analysis_id,
  package_id: practice.package_id,
  score_id: practice.score_id,
  practice_ref: reference("curriculum-fundamental-practice", practice.id, practice.semantic_fingerprint),
  requirement_ref: requirementRef,
  primitive_ref: primitiveRef,
  practice_scope_ref: scopeRef,
  presentation_ref: presentationRef,
  prerequisite_exercise_ref: prerequisiteExerciseRef,
  application_exercise_ref: applicationExerciseRef,
  graph_ref: graphRef,
  mastery_projection_ref: decision.projection_ref,
  unlock_decision_ref: reference("curriculum-unlock-decision", decision.id, decision.semantic_fingerprint),
  support_state_ref: supportRef,
  prerequisite_node_id: practice.prerequisite_node_id,
  return_node_id: practice.return_node_id,
  return_edge_id: decision.selected_edge_id,
  reconnect_activity_id: "activity:reconnect",
  completed_attempt_ids: mastery.complete_passing_attempt_ids,
  evidence_record_ids: ["evidence:pitch"],
  active_event_ids: presentation.active_target_ids,
  diagnostics: [],
  resolution: "resolved",
} as CurriculumPieceReturnView;

const notation = { package_id: "package:one", score_id: "score:one" } as ViewerBundle;

test("TEST-APP-TEACHING-022 returns to the exact piece application and passage", () => {
  const onReturn = vi.fn();
  render(
    <FundamentalReturnSurface
      handoff={handoff}
      practice={practice}
      explanation={explanation}
      presentation={presentation}
      mastery={mastery}
      decision={decision}
      notation={notation}
      onReturn={onReturn}
    />,
  );

  expect(screen.getByRole("heading", { name: "Apply Keyboard geography" })).toBeVisible();
  expect(screen.getByTestId("return-notation")).toHaveTextContent("event:one");
  fireEvent.click(screen.getByRole("button", { name: "Continue with the piece" }));

  expect(onReturn).toHaveBeenCalledWith({
    return_id: handoff.id,
    return_node_id: handoff.return_node_id,
    application_exercise_id: applicationExerciseRef.id,
    presentation_id: presentation.id,
    active_event_ids: ["event:one"],
    completed_attempt_ids: mastery.complete_passing_attempt_ids,
    evidence_record_ids: ["evidence:pitch"],
  });
});

test("TEST-APP-TEACHING-023 rejects policy, evidence, or passage drift", () => {
  render(
    <FundamentalReturnSurface
      handoff={{ ...handoff, return_node_id: "node:foreign", evidence_record_ids: [] }}
      practice={practice}
      explanation={explanation}
      presentation={presentation}
      mastery={mastery}
      decision={decision}
      notation={notation}
      onReturn={vi.fn()}
    />,
  );

  expect(screen.getByRole("alert")).toHaveTextContent(
    "The piece return is not authorized for this exact practice evidence and passage.",
  );
  expect(screen.queryByRole("button", { name: "Continue with the piece" })).not.toBeInTheDocument();
});
