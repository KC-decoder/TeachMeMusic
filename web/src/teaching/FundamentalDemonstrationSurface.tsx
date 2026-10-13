import { useMemo } from "react";

import type { ExactFraction, PlaybackPlan } from "../contracts/playback";
import type { ViewerBundle } from "../contracts/viewer";
import {
  CurriculumDemonstrationSurface,
  type CurriculumPassageGuidanceView,
  type CurriculumPassagePresentationView,
  type SemanticReferenceView,
} from "./CurriculumDemonstrationSurface";

export interface CurriculumFundamentalExplanationView {
  id: string;
  semantic_fingerprint: string;
  analysis_id: string;
  package_id: string;
  score_id: string;
  requirement_ref: SemanticReferenceView;
  primitive_ref: SemanticReferenceView;
  practice_scope_ref: SemanticReferenceView;
  presentation_ref: SemanticReferenceView;
  prerequisite_exercise_ref: SemanticReferenceView;
  application_exercise_ref: SemanticReferenceView;
  prerequisite_node_id: string;
  return_node_id: string;
  heading: string;
  explanation: string;
  why_it_matters: string;
  action_prompt: string;
  return_prompt: string;
  focus_event_ids: string[];
  diagnostics: unknown[];
  resolution: "resolved" | "review-required" | "unsupported" | "fatal";
}

export interface CurriculumFundamentalDemonstrationView {
  id: string;
  semantic_fingerprint: string;
  analysis_id: string;
  package_id: string;
  score_id: string;
  explanation_ref: SemanticReferenceView;
  requirement_ref: SemanticReferenceView;
  primitive_ref: SemanticReferenceView;
  practice_scope_ref: SemanticReferenceView;
  presentation_ref: SemanticReferenceView;
  prerequisite_exercise_ref: SemanticReferenceView;
  prerequisite_node_id: string;
  return_node_id: string;
  demonstration_activity_id: string;
  focus_event_ids: string[];
  playback_source_event_ids: string[];
  silent_active_event_ids: string[];
  playback_plan_sha256: string;
  tempo_bpm: ExactFraction;
  diagnostics: unknown[];
  resolution: "resolved" | "review-required" | "unsupported" | "fatal";
}

interface FundamentalDemonstrationSurfaceProps {
  demonstration: CurriculumFundamentalDemonstrationView;
  explanation: CurriculumFundamentalExplanationView;
  presentation: CurriculumPassagePresentationView;
  notation: ViewerBundle;
  playback: PlaybackPlan;
}

class FundamentalDemonstrationError extends Error {
  constructor(readonly code: string, message: string) {
    super(message);
  }
}

function sameReference(left: SemanticReferenceView, right: SemanticReferenceView): boolean {
  return left.type === right.type &&
    left.id === right.id &&
    left.semantic_fingerprint === right.semantic_fingerprint;
}

function sameMembers(left: ReadonlySet<string>, right: ReadonlySet<string>): boolean {
  return left.size === right.size && [...left].every((id) => right.has(id));
}

function sameSequence(left: readonly string[], right: readonly string[]): boolean {
  return left.length === right.length && left.every((id, index) => id === right[index]);
}

function requireValidFundamentalBinding(
  demonstration: CurriculumFundamentalDemonstrationView,
  explanation: CurriculumFundamentalExplanationView,
  presentation: CurriculumPassagePresentationView,
  playback: PlaybackPlan,
): void {
  const expectedExplanationRef: SemanticReferenceView = {
    type: "curriculum-fundamental-explanation",
    id: explanation.id,
    semantic_fingerprint: explanation.semantic_fingerprint,
  };
  const playbackSources = new Set(
    playback.notes.flatMap((note) => note.source_events.map((source) => source.event_id)),
  );
  const declaredSources = new Set(demonstration.playback_source_event_ids);
  const silentActive = new Set(demonstration.silent_active_event_ids);
  const active = new Set(presentation.active_target_ids);
  const combinedActive = new Set([...declaredSources, ...silentActive]);
  const playbackTempo = playback.tempo_controls[0]?.quarter_notes_per_minute;
  const tempoMatches = playbackTempo !== undefined &&
    playbackTempo.numerator * demonstration.tempo_bpm.denominator ===
      demonstration.tempo_bpm.numerator * playbackTempo.denominator;
  const expectedPresentationRef: SemanticReferenceView = {
    type: "curriculum-passage-presentation",
    id: presentation.id,
    semantic_fingerprint: presentation.semantic_fingerprint,
  };
  const invalid =
    demonstration.resolution !== "resolved" ||
    explanation.resolution !== "resolved" ||
    demonstration.diagnostics.length > 0 ||
    explanation.diagnostics.length > 0 ||
    !sameReference(demonstration.explanation_ref, expectedExplanationRef) ||
    !sameReference(demonstration.requirement_ref, explanation.requirement_ref) ||
    !sameReference(demonstration.primitive_ref, explanation.primitive_ref) ||
    !sameReference(demonstration.practice_scope_ref, explanation.practice_scope_ref) ||
    !sameReference(demonstration.presentation_ref, explanation.presentation_ref) ||
    !sameReference(explanation.presentation_ref, expectedPresentationRef) ||
    !sameReference(explanation.practice_scope_ref, presentation.practice_scope_ref) ||
    !sameReference(
      demonstration.prerequisite_exercise_ref,
      explanation.prerequisite_exercise_ref,
    ) ||
    demonstration.analysis_id !== explanation.analysis_id ||
    demonstration.package_id !== explanation.package_id ||
    demonstration.score_id !== explanation.score_id ||
    demonstration.analysis_id !== presentation.analysis_id ||
    demonstration.package_id !== presentation.package_id ||
    demonstration.score_id !== presentation.score_id ||
    demonstration.prerequisite_node_id !== explanation.prerequisite_node_id ||
    demonstration.return_node_id !== explanation.return_node_id ||
    explanation.presentation_ref.id !== presentation.id ||
    explanation.presentation_ref.semantic_fingerprint !== presentation.semantic_fingerprint ||
    !sameSequence(demonstration.focus_event_ids, explanation.focus_event_ids) ||
    !sameMembers(declaredSources, playbackSources) ||
    !sameMembers(combinedActive, active) ||
    [...declaredSources].some((id) => silentActive.has(id)) ||
    demonstration.focus_event_ids.length === 0 ||
    demonstration.focus_event_ids.some((id) => !active.has(id)) ||
    !demonstration.demonstration_activity_id.trim() ||
    !/^[0-9a-f]{64}$/.test(demonstration.playback_plan_sha256) ||
    demonstration.tempo_bpm.denominator <= 0 ||
    demonstration.tempo_bpm.numerator <= 0 ||
    !tempoMatches;
  if (invalid) {
    throw new FundamentalDemonstrationError(
      "TMM_FUNDAMENTAL_DEMONSTRATION_MISMATCH",
      "The fundamental demonstration is not bound to this exact prerequisite and active score layer.",
    );
  }
}

function guidanceFromExplanation(
  demonstration: CurriculumFundamentalDemonstrationView,
  explanation: CurriculumFundamentalExplanationView,
  presentation: CurriculumPassagePresentationView,
): CurriculumPassageGuidanceView {
  return {
    id: `curriculum-passage-guidance:${demonstration.semantic_fingerprint}`,
    semantic_fingerprint: demonstration.semantic_fingerprint,
    analysis_id: demonstration.analysis_id,
    package_id: demonstration.package_id,
    score_id: demonstration.score_id,
    presentation_ref: demonstration.presentation_ref,
    practice_scope_ref: demonstration.practice_scope_ref,
    notation_condition: presentation.notation_condition,
    items: [{
      id: explanation.id,
      requirement_ref: explanation.requirement_ref,
      primitive_ref: explanation.primitive_ref,
      primitive_family: "fundamental",
      heading: explanation.heading,
      explanation: `${explanation.explanation} ${explanation.why_it_matters}`,
      action_prompt: explanation.action_prompt,
      reconnect_prompt: explanation.return_prompt,
      focus_event_ids: explanation.focus_event_ids,
      canonical_evidence_refs: explanation.focus_event_ids,
      analysis_evidence_refs: [],
    }],
  };
}

export function FundamentalDemonstrationSurface({
  demonstration,
  explanation,
  presentation,
  notation,
  playback,
}: FundamentalDemonstrationSurfaceProps) {
  const validationError = useMemo(() => {
    try {
      requireValidFundamentalBinding(demonstration, explanation, presentation, playback);
      return null;
    } catch (reason: unknown) {
      return reason instanceof FundamentalDemonstrationError
        ? reason
        : new FundamentalDemonstrationError(
            "TMM_FUNDAMENTAL_DEMONSTRATION_INVALID",
            "The prerequisite demonstration was rejected.",
          );
    }
  }, [demonstration, explanation, playback, presentation]);
  const guidance = useMemo(
    () => guidanceFromExplanation(demonstration, explanation, presentation),
    [demonstration, explanation, presentation],
  );

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
      className="fundamental-demonstration"
      aria-labelledby="fundamental-demonstration-heading"
      data-demonstration-id={demonstration.id}
      data-prerequisite-node-id={demonstration.prerequisite_node_id}
      data-return-node-id={demonstration.return_node_id}
    >
      <header className="fundamental-demonstration-header">
        <p className="eyebrow">FUNDAMENTAL DEMONSTRATION</p>
        <h2 id="fundamental-demonstration-heading">{explanation.heading}</h2>
        <p>Listen and watch first. This demonstration does not count as a learner attempt.</p>
      </header>
      <CurriculumDemonstrationSurface
        presentation={presentation}
        guidance={guidance}
        notation={notation}
        playback={playback}
      />
    </section>
  );
}
