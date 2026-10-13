import { useCallback, useMemo, useState } from "react";

import type { ActivePlaybackNote } from "../audio/PlaybackTransport";
import { requireValidPlaybackPlan, type PlaybackPlan } from "../contracts/playback";
import type { ViewerBundle } from "../contracts/viewer";
import { NotationSurface } from "../notation/NotationSurface";
import type { NotationRendererTarget } from "../notation/layerEmphasis";
import { VirtualPiano } from "../piano/VirtualPiano";
import { PlaybackSurface } from "../playback/PlaybackSurface";

export interface CurriculumPassagePresentationView {
  id: string;
  semantic_fingerprint: string;
  analysis_id: string;
  package_id: string;
  score_id: string;
  practice_scope_ref: SemanticReferenceView;
  notation_condition: "single-layer" | "upper-layer" | "lower-layer" | "combined";
  visible_event_ids: string[];
  active_target_ids: string[];
  inactive_context_ids: string[];
  active_renderer_targets: NotationRendererTarget[];
  inactive_renderer_targets: NotationRendererTarget[];
  visible_omitted_renderer_targets: NotationRendererTarget[];
  notation_renderer_sha256: string;
}

export interface SemanticReferenceView {
  type: string;
  id: string;
  semantic_fingerprint: string;
}

export interface CurriculumGuidanceItemView {
  id: string;
  requirement_ref: SemanticReferenceView;
  primitive_ref: SemanticReferenceView;
  primitive_family: string;
  heading: string;
  explanation: string;
  action_prompt: string;
  reconnect_prompt: string;
  focus_event_ids: string[];
  canonical_evidence_refs: string[];
  analysis_evidence_refs: string[];
}

export interface CurriculumPassageGuidanceView {
  id: string;
  semantic_fingerprint: string;
  analysis_id: string;
  package_id: string;
  score_id: string;
  presentation_ref: SemanticReferenceView;
  practice_scope_ref: SemanticReferenceView;
  notation_condition: CurriculumPassagePresentationView["notation_condition"];
  items: CurriculumGuidanceItemView[];
}

interface CurriculumDemonstrationSurfaceProps {
  presentation: CurriculumPassagePresentationView;
  guidance: CurriculumPassageGuidanceView;
  notation: ViewerBundle;
  playback: PlaybackPlan;
}

class CurriculumDemonstrationError extends Error {
  constructor(readonly code: string, message: string) {
    super(message);
  }
}

function sameMembers(left: ReadonlySet<string>, right: ReadonlySet<string>): boolean {
  return left.size === right.size && [...left].every((id) => right.has(id));
}

function requireSynchronizedContracts(
  presentation: CurriculumPassagePresentationView,
  guidance: CurriculumPassageGuidanceView,
  notation: ViewerBundle,
  playback: PlaybackPlan,
): void {
  requireValidPlaybackPlan(playback);
  if (
    presentation.package_id !== notation.package_id ||
    presentation.package_id !== playback.package_id ||
    presentation.score_id !== notation.score_id ||
    presentation.score_id !== playback.score_id
  ) {
    throw new CurriculumDemonstrationError(
      "TMM_PRESENTATION_CONSUMER_IDENTITY",
      "Notation and playback do not belong to this curriculum presentation.",
    );
  }
  if (presentation.notation_renderer_sha256 !== notation.renderer.sha256) {
    throw new CurriculumDemonstrationError(
      "TMM_PRESENTATION_CONSUMER_NOTATION",
      "The verified notation payload differs from the curriculum presentation.",
    );
  }
  const active = new Set(presentation.active_target_ids);
  const inactive = new Set(presentation.inactive_context_ids);
  const visible = new Set(presentation.visible_event_ids);
  const activeTargets = new Set(
    presentation.active_renderer_targets.map((target) => target.canonical_id),
  );
  const inactiveTargets = new Set(
    presentation.inactive_renderer_targets.map((target) => target.canonical_id),
  );
  const represented = new Set([
    ...activeTargets,
    ...inactiveTargets,
    ...presentation.visible_omitted_renderer_targets.map((target) => target.canonical_id),
  ]);
  if (
    active.size === 0 ||
    !sameMembers(active, activeTargets) ||
    !sameMembers(inactive, inactiveTargets) ||
    !sameMembers(visible, represented)
  ) {
    throw new CurriculumDemonstrationError(
      "TMM_PRESENTATION_CONSUMER_PARTITION",
      "The visible notation partition is incomplete or has no active target.",
    );
  }
  const playbackSources = playback.notes.flatMap((note) =>
    note.source_events.map((source) => source.event_id),
  );
  if (playbackSources.some((id) => !active.has(id))) {
    throw new CurriculumDemonstrationError(
      "TMM_PRESENTATION_CONSUMER_LAYER_LEAK",
      "Expected sound or piano guidance contains inactive notation.",
    );
  }
  const guidanceIds = new Set<string>();
  const requirementIds = new Set<string>();
  const guidanceMismatch =
    guidance.analysis_id !== presentation.analysis_id ||
    guidance.package_id !== presentation.package_id ||
    guidance.score_id !== presentation.score_id ||
    guidance.notation_condition !== presentation.notation_condition ||
    guidance.presentation_ref.type !== "curriculum-passage-presentation" ||
    guidance.presentation_ref.id !== presentation.id ||
    guidance.presentation_ref.semantic_fingerprint !== presentation.semantic_fingerprint ||
    guidance.practice_scope_ref.type !== "practice-scope-assignment" ||
    guidance.practice_scope_ref.id !== presentation.practice_scope_ref.id ||
    guidance.practice_scope_ref.semantic_fingerprint !==
      presentation.practice_scope_ref.semantic_fingerprint ||
    guidance.items.length === 0 ||
    guidance.items.some((item) => {
      const focus = new Set(item.focus_event_ids);
      const duplicateItem = guidanceIds.has(item.id);
      const duplicateRequirement = requirementIds.has(item.requirement_ref.id);
      guidanceIds.add(item.id);
      requirementIds.add(item.requirement_ref.id);
      return duplicateItem ||
        duplicateRequirement ||
        item.requirement_ref.type !== "passage-skill-requirement" ||
        item.primitive_ref.type !== "learning-primitive" ||
        !item.heading.trim() ||
        !item.explanation.trim() ||
        !item.action_prompt.trim() ||
        !item.reconnect_prompt.trim() ||
        focus.size === 0 ||
        [...focus].some((id) => !active.has(id) || inactive.has(id));
    });
  if (guidanceMismatch) {
    throw new CurriculumDemonstrationError(
      "TMM_PRESENTATION_GUIDANCE_MISMATCH",
      "The learner guidance does not belong to this exact active layer.",
    );
  }
}

function layerLabel(value: CurriculumPassagePresentationView["notation_condition"]): string {
  switch (value) {
    case "upper-layer": return "Upper layer active";
    case "lower-layer": return "Lower layer active";
    case "combined": return "Combined layers active";
    default: return "Single layer active";
  }
}

export function CurriculumDemonstrationSurface({
  presentation,
  guidance,
  notation,
  playback,
}: CurriculumDemonstrationSurfaceProps) {
  const validationError = useMemo(() => {
    try {
      requireSynchronizedContracts(presentation, guidance, notation, playback);
      return null;
    } catch (reason: unknown) {
      return reason instanceof CurriculumDemonstrationError
        ? reason
        : new CurriculumDemonstrationError(
            "TMM_PRESENTATION_CONSUMER_INVALID",
            "The synchronized curriculum demonstration was rejected.",
          );
    }
  }, [guidance, notation, playback, presentation]);
  const activeIds = useMemo(
    () => new Set(
      playback.notes.flatMap((note) =>
        note.source_events.map((source) => source.event_id),
      ),
    ),
    [playback.notes],
  );
  const [playbackFocusEventIds, setPlaybackFocusEventIds] = useState<string[]>([]);
  const [guidanceFocusEventIds, setGuidanceFocusEventIds] = useState<string[]>([]);
  const [activeNotes, setActiveNotes] = useState<ActivePlaybackNote[]>([]);
  const acceptFocus = useCallback(
    (ids: string[]) => setPlaybackFocusEventIds(ids.filter((id) => activeIds.has(id))),
    [activeIds],
  );
  const acceptNotes = useCallback(
    (notes: ActivePlaybackNote[]) => {
      const safe = notes.every(
        (note) => note.contributions.length > 0 &&
          note.contributions.every((item) => activeIds.has(item.eventId)),
      );
      setActiveNotes(safe ? notes : []);
    },
    [activeIds],
  );

  if (validationError) {
    return (
      <div className="playback-error" role="alert">
        <strong>{validationError.message}</strong>
        <code>{validationError.code}</code>
      </div>
    );
  }

  const visibleContextTargets = [
    ...presentation.inactive_renderer_targets,
    ...presentation.visible_omitted_renderer_targets,
  ];
  const focusEventIds = playbackFocusEventIds.length > 0
    ? playbackFocusEventIds
    : guidanceFocusEventIds;
  return (
    <section
      className="curriculum-demonstration"
      aria-label="Synchronized curriculum demonstration"
      data-presentation-id={presentation.id}
    >
      <PlaybackSurface
        plan={playback}
        eyebrow="ACTIVE-LAYER DEMONSTRATION"
        heading="Listen to this layer"
        onFocusEventIds={acceptFocus}
        onActiveNotes={acceptNotes}
      />
      <aside className="curriculum-guidance" aria-labelledby="curriculum-guidance-heading">
        <div>
          <p className="eyebrow">ACTIVE MATERIAL</p>
          <h2 id="curriculum-guidance-heading">What to notice and do</h2>
        </div>
        <div className="curriculum-guidance-list">
          {guidance.items.map((item) => (
            <article
              className="curriculum-guidance-item"
              data-guidance-id={item.id}
              data-requirement-id={item.requirement_ref.id}
              key={item.id}
            >
              <p className="curriculum-guidance-family">
                {item.primitive_family.replaceAll("-", " ")}
              </p>
              <h3>{item.heading}</h3>
              <p>{item.explanation}</p>
              <p><strong>Try this:</strong> {item.action_prompt}</p>
              <p>{item.reconnect_prompt}</p>
              <button
                type="button"
                onClick={() => setGuidanceFocusEventIds(item.focus_event_ids)}
              >
                Show this target in the score
              </button>
            </article>
          ))}
        </div>
      </aside>
      <NotationSurface
        bundle={notation}
        allowedEventIds={presentation.visible_event_ids}
        focusEventIds={focusEventIds}
        layerEmphasis={{
          label: layerLabel(presentation.notation_condition),
          activeTargets: presentation.active_renderer_targets,
          inactiveTargets: visibleContextTargets,
        }}
      />
      <VirtualPiano
        activeNotes={activeNotes}
        learnerInputStatus="unavailable"
        guidanceMode="demonstration"
      />
    </section>
  );
}
