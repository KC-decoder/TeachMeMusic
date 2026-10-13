import type { RenderAnchor } from "../contracts/viewer";
import {
  NotationLayerEmphasisError,
  resolveNotationLayerEmphasis,
} from "./layerEmphasis";

function anchor(id: string, eventIndex: number): RenderAnchor {
  return {
    canonical_id: id,
    canonical_kind: "event",
    renderer_anchor: `part[0]/measure[0]/event[${eventIndex}]`,
    renderer_part_id: "P1",
    part_index: 0,
    measure_index: 0,
    event_index: eventIndex,
    measure_onset_quarters: `${eventIndex}`,
  };
}

function target(value: RenderAnchor) {
  return {
    canonical_id: value.canonical_id,
    canonical_kind: "event" as const,
    renderer_anchor: value.renderer_anchor,
  };
}

const anchors = [
  anchor("event:upper-one", 0),
  anchor("event:upper-two", 1),
  anchor("event:lower-one", 2),
  anchor("event:lower-two", 3),
];
const allIds = anchors.map((item) => item.canonical_id);

test("TEST-CURR-VALIDATION-015 resolves single and polyphonic visual roles", () => {
  const single = resolveNotationLayerEmphasis(
    anchors,
    {
      label: "Single layer",
      activeTargets: anchors.map(target),
      inactiveTargets: [],
    },
    allIds,
  );
  const upper = resolveNotationLayerEmphasis(
    anchors,
    {
      label: "Upper layer",
      activeTargets: anchors.slice(0, 2).map(target),
      inactiveTargets: anchors.slice(2).map(target),
    },
    allIds,
  );
  const lower = resolveNotationLayerEmphasis(
    anchors,
    {
      label: "Lower layer",
      activeTargets: anchors.slice(2).map(target),
      inactiveTargets: anchors.slice(0, 2).map(target),
    },
    allIds,
  );

  expect(single.activeEventIds).toEqual(allIds);
  expect(single.inactiveEventIds).toEqual([]);
  expect(upper.activeEventIds).toEqual(["event:upper-one", "event:upper-two"]);
  expect(upper.inactiveEventIds).toEqual(["event:lower-one", "event:lower-two"]);
  expect(lower.activeEventIds).toEqual(upper.inactiveEventIds);
  expect(lower.inactiveEventIds).toEqual(upper.activeEventIds);
});

test("TEST-CURR-ROBUSTNESS-010 rejects crosswalk drift and overlapping roles", () => {
  expect(() =>
    resolveNotationLayerEmphasis(
      anchors,
      {
        label: "Upper layer",
        activeTargets: [{ ...target(anchors[0]), renderer_anchor: "changed" }],
        inactiveTargets: anchors.slice(1).map(target),
      },
      allIds,
    ),
  ).toThrowError(
    expect.objectContaining<Partial<NotationLayerEmphasisError>>({
      code: "TMM_PRESENTATION_LAYER_CROSSWALK",
    }),
  );
  expect(() =>
    resolveNotationLayerEmphasis(
      anchors,
      {
        label: "Upper layer",
        activeTargets: [target(anchors[0])],
        inactiveTargets: [target(anchors[0]), ...anchors.slice(1).map(target)],
      },
      allIds,
    ),
  ).toThrowError(
    expect.objectContaining<Partial<NotationLayerEmphasisError>>({
      code: "TMM_PRESENTATION_LAYER_OVERLAP",
    }),
  );
});
