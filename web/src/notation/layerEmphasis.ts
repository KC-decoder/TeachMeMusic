import type { RenderAnchor } from "../contracts/viewer";

export interface NotationRendererTarget {
  canonical_id: string;
  canonical_kind: "event";
  renderer_anchor: string;
}

export interface NotationLayerEmphasis {
  label: string;
  activeTargets: readonly NotationRendererTarget[];
  inactiveTargets: readonly NotationRendererTarget[];
}

export interface ResolvedNotationLayerEmphasis {
  label: string;
  activeEventIds: string[];
  inactiveEventIds: string[];
}

export class NotationLayerEmphasisError extends Error {
  constructor(readonly code: string, message: string) {
    super(message);
  }
}

export function resolveNotationLayerEmphasis(
  anchors: readonly RenderAnchor[],
  emphasis: NotationLayerEmphasis,
  allowedEventIds?: readonly string[],
): ResolvedNotationLayerEmphasis {
  const label = emphasis.label.trim();
  if (label.length === 0 || emphasis.activeTargets.length === 0) {
    throw new NotationLayerEmphasisError(
      "TMM_PRESENTATION_LAYER_EMPTY",
      "Layer emphasis requires a readable label and at least one active event.",
    );
  }

  const activeEventIds = emphasis.activeTargets.map((target) => target.canonical_id);
  const inactiveEventIds = emphasis.inactiveTargets.map((target) => target.canonical_id);
  if (
    new Set(activeEventIds).size !== activeEventIds.length ||
    new Set(inactiveEventIds).size !== inactiveEventIds.length
  ) {
    throw new NotationLayerEmphasisError(
      "TMM_PRESENTATION_LAYER_DUPLICATE",
      "A canonical event may occur only once in each visual role.",
    );
  }
  const active = new Set(activeEventIds);
  if (inactiveEventIds.some((id) => active.has(id))) {
    throw new NotationLayerEmphasisError(
      "TMM_PRESENTATION_LAYER_OVERLAP",
      "Active material and inactive context must be disjoint.",
    );
  }

  const anchorsById = new Map(
    anchors
      .filter((anchor) => anchor.canonical_kind === "event")
      .map((anchor) => [anchor.canonical_id, anchor]),
  );
  for (const target of [...emphasis.activeTargets, ...emphasis.inactiveTargets]) {
    const anchor = anchorsById.get(target.canonical_id);
    if (
      target.canonical_kind !== "event" ||
      !anchor ||
      anchor.renderer_anchor !== target.renderer_anchor
    ) {
      throw new NotationLayerEmphasisError(
        "TMM_PRESENTATION_LAYER_CROSSWALK",
        "A curriculum renderer target does not match the verified notation bundle.",
      );
    }
  }

  if (allowedEventIds) {
    const expected = new Set(allowedEventIds);
    const represented = new Set([...activeEventIds, ...inactiveEventIds]);
    if (
      expected.size !== represented.size ||
      [...expected].some((id) => !represented.has(id))
    ) {
      throw new NotationLayerEmphasisError(
        "TMM_PRESENTATION_LAYER_PARTITION",
        "Active material and inactive context must cover the complete visible passage.",
      );
    }
  }

  return { label, activeEventIds, inactiveEventIds };
}
