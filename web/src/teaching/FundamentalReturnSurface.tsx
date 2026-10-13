import { useMemo } from "react";

import type { ViewerBundle } from "../contracts/viewer";
import { NotationSurface } from "../notation/NotationSurface";
import type { CurriculumPassagePresentationView } from "./CurriculumDemonstrationSurface";
import type { CurriculumFundamentalExplanationView } from "./FundamentalDemonstrationSurface";
import type { CurriculumFundamentalPracticeView } from "./FundamentalPracticeSurface";

interface SemanticReferenceView {
  type: string;
  id: string;
  semantic_fingerprint: string;
}

export interface CurriculumMasteryProjectionView {
  id: string;
  semantic_fingerprint: string;
  graph_ref: SemanticReferenceView;
  node_id: string;
  exercise_ref: SemanticReferenceView;
  requirement_ref: SemanticReferenceView;
  primitive_ref: SemanticReferenceView;
  practice_scope_ref: SemanticReferenceView;
  support_state_ref: SemanticReferenceView;
  dimension_decisions: Array<{ evidence_record_ids: string[] }>;
  complete_passing_attempt_ids: string[];
  status: "mastered" | "not-mastered" | "inconclusive";
}

export interface CurriculumUnlockDecisionView {
  id: string;
  semantic_fingerprint: string;
  graph_ref: SemanticReferenceView;
  current_node_id: string;
  projection_ref: SemanticReferenceView;
  selected_edge_id: string | null;
  next_node_id: string | null;
  action: "unlock-successor" | "complete-node" | "retry-current" | "hold-for-evidence";
}

export interface CurriculumPieceReturnView {
  id: string;
  semantic_fingerprint: string;
  analysis_id: string;
  package_id: string;
  score_id: string;
  practice_ref: SemanticReferenceView;
  requirement_ref: SemanticReferenceView;
  primitive_ref: SemanticReferenceView;
  practice_scope_ref: SemanticReferenceView;
  presentation_ref: SemanticReferenceView;
  prerequisite_exercise_ref: SemanticReferenceView;
  application_exercise_ref: SemanticReferenceView;
  graph_ref: SemanticReferenceView;
  mastery_projection_ref: SemanticReferenceView;
  unlock_decision_ref: SemanticReferenceView;
  support_state_ref: SemanticReferenceView;
  prerequisite_node_id: string;
  return_node_id: string;
  return_edge_id: string;
  reconnect_activity_id: string;
  completed_attempt_ids: string[];
  evidence_record_ids: string[];
  active_event_ids: string[];
  diagnostics: unknown[];
  resolution: "resolved" | "review-required" | "unsupported" | "fatal";
}

export interface CurriculumPieceReturnContext {
  return_id: string;
  return_node_id: string;
  application_exercise_id: string;
  presentation_id: string;
  active_event_ids: string[];
  completed_attempt_ids: string[];
  evidence_record_ids: string[];
}

interface FundamentalReturnSurfaceProps {
  handoff: CurriculumPieceReturnView;
  practice: CurriculumFundamentalPracticeView;
  explanation: CurriculumFundamentalExplanationView;
  presentation: CurriculumPassagePresentationView;
  mastery: CurriculumMasteryProjectionView;
  decision: CurriculumUnlockDecisionView;
  notation: ViewerBundle;
  onReturn: (context: CurriculumPieceReturnContext) => void;
}

class FundamentalReturnError extends Error {
  constructor(readonly code: string, message: string) {
    super(message);
  }
}

function sameSequence(left: readonly string[], right: readonly string[]): boolean {
  return left.length === right.length && left.every((item, index) => item === right[index]);
}

function sameReference(left: SemanticReferenceView, right: SemanticReferenceView): boolean {
  return left.type === right.type && left.id === right.id &&
    left.semantic_fingerprint === right.semantic_fingerprint;
}

function requireValidReturn(
  handoff: CurriculumPieceReturnView,
  practice: CurriculumFundamentalPracticeView,
  explanation: CurriculumFundamentalExplanationView,
  presentation: CurriculumPassagePresentationView,
  mastery: CurriculumMasteryProjectionView,
  decision: CurriculumUnlockDecisionView,
): void {
  const evidenceRecordIds = mastery.dimension_decisions.flatMap(
    (item) => item.evidence_record_ids,
  ).filter((item, index, values) => values.indexOf(item) === index);
  const invalid =
    handoff.resolution !== "resolved" ||
    handoff.diagnostics.length > 0 ||
    handoff.analysis_id !== practice.analysis_id ||
    handoff.package_id !== practice.package_id ||
    handoff.score_id !== practice.score_id ||
    handoff.practice_ref.id !== practice.id ||
    handoff.practice_ref.semantic_fingerprint !== practice.semantic_fingerprint ||
    !sameReference(handoff.requirement_ref, practice.requirement_ref) ||
    !sameReference(handoff.primitive_ref, practice.primitive_ref) ||
    !sameReference(handoff.practice_scope_ref, practice.practice_scope_ref) ||
    handoff.presentation_ref.id !== presentation.id ||
    handoff.presentation_ref.semantic_fingerprint !== presentation.semantic_fingerprint ||
    !sameReference(handoff.prerequisite_exercise_ref, practice.prerequisite_exercise_ref) ||
    !sameReference(handoff.application_exercise_ref, explanation.application_exercise_ref) ||
    !sameReference(handoff.graph_ref, mastery.graph_ref) ||
    handoff.mastery_projection_ref.id !== mastery.id ||
    handoff.mastery_projection_ref.semantic_fingerprint !== mastery.semantic_fingerprint ||
    handoff.unlock_decision_ref.id !== decision.id ||
    handoff.unlock_decision_ref.semantic_fingerprint !== decision.semantic_fingerprint ||
    !sameReference(handoff.support_state_ref, mastery.support_state_ref) ||
    handoff.prerequisite_node_id !== practice.prerequisite_node_id ||
    handoff.prerequisite_node_id !== mastery.node_id ||
    handoff.return_node_id !== practice.return_node_id ||
    handoff.return_node_id !== decision.next_node_id ||
    handoff.return_edge_id !== decision.selected_edge_id ||
    decision.current_node_id !== practice.prerequisite_node_id ||
    decision.action !== "unlock-successor" ||
    decision.projection_ref.id !== mastery.id ||
    decision.projection_ref.semantic_fingerprint !== mastery.semantic_fingerprint ||
    mastery.status !== "mastered" ||
    !sameSequence(handoff.completed_attempt_ids, mastery.complete_passing_attempt_ids) ||
    !sameSequence(handoff.evidence_record_ids, evidenceRecordIds) ||
    !sameSequence(handoff.active_event_ids, presentation.active_target_ids) ||
    handoff.completed_attempt_ids.length === 0 ||
    handoff.evidence_record_ids.length === 0 ||
    handoff.active_event_ids.length === 0 ||
    !handoff.reconnect_activity_id.trim();
  if (invalid) {
    throw new FundamentalReturnError(
      "TMM_FUNDAMENTAL_RETURN_MISMATCH",
      "The piece return is not authorized for this exact practice evidence and passage.",
    );
  }
}

export function FundamentalReturnSurface({
  handoff,
  practice,
  explanation,
  presentation,
  mastery,
  decision,
  notation,
  onReturn,
}: FundamentalReturnSurfaceProps) {
  const validationError = useMemo(() => {
    try {
      requireValidReturn(handoff, practice, explanation, presentation, mastery, decision);
      return null;
    } catch (reason: unknown) {
      return reason instanceof FundamentalReturnError
        ? reason
        : new FundamentalReturnError(
            "TMM_FUNDAMENTAL_RETURN_INVALID",
            "The return to the piece was rejected.",
          );
    }
  }, [decision, explanation, handoff, mastery, practice, presentation]);

  if (validationError) {
    return (
      <div className="playback-error" role="alert">
        <strong>{validationError.message}</strong>
        <code>{validationError.code}</code>
      </div>
    );
  }

  return (
    <section
      className="fundamental-return"
      aria-labelledby="fundamental-return-heading"
      data-return-node-id={handoff.return_node_id}
      data-application-exercise-id={handoff.application_exercise_ref.id}
    >
      <header className="fundamental-demonstration-header">
        <p className="eyebrow">BACK TO YOUR PIECE</p>
        <h2 id="fundamental-return-heading">Apply {explanation.heading}</h2>
        <p>{explanation.return_prompt}</p>
      </header>
      <NotationSurface
        bundle={notation}
        focusEventIds={handoff.active_event_ids}
        allowedEventIds={presentation.visible_event_ids}
        layerEmphasis={{
          label: "Piece application target",
          activeTargets: presentation.active_renderer_targets,
          inactiveTargets: [
            ...presentation.inactive_renderer_targets,
            ...presentation.visible_omitted_renderer_targets,
          ],
        }}
      />
      <button
        type="button"
        className="midi-primary"
        onClick={() => onReturn({
          return_id: handoff.id,
          return_node_id: handoff.return_node_id,
          application_exercise_id: handoff.application_exercise_ref.id,
          presentation_id: handoff.presentation_ref.id,
          active_event_ids: handoff.active_event_ids,
          completed_attempt_ids: handoff.completed_attempt_ids,
          evidence_record_ids: handoff.evidence_record_ids,
        })}
      >
        Continue with the piece
      </button>
    </section>
  );
}
