import { fireEvent, render, screen, waitFor } from "@testing-library/react";

import type { ViewerBundle } from "../contracts/viewer";
import type { NotationAdapter } from "./OsmdNotationAdapter";
import { NotationAdapterError } from "./OsmdNotationAdapter";
import { NotationSurface } from "./NotationSurface";

const bundle: ViewerBundle = {
  contract_id: "org.teachmemusic.viewer-bundle",
  contract_version: "0.2.0",
  capabilities: ["notation"],
  package_id: "package:one",
  score_id: "score:one",
  canonical_schema_id: "org.teachmemusic.canonical-music-package",
  canonical_schema_version: "2.0.0",
  title: "Navigation study",
  renderer: {
    renderer: "opensheetmusicdisplay",
    media_type: "application/vnd.recordare.musicxml+xml",
    encoding: "utf-8",
    content: "<?xml version=\"1.0\"?><score-partwise version=\"4.0\"/>",
    sha256: "digest",
    represented_features: ["events"],
    anchors: [
      {
        canonical_id: "event:one",
        canonical_kind: "event",
        renderer_anchor: "part[0]/measure[0]/event[0]",
        renderer_part_id: "P1",
        part_index: 0,
        measure_index: 0,
        event_index: 0,
        measure_onset_quarters: "0",
      },
      {
        canonical_id: "event:two",
        canonical_kind: "event",
        renderer_anchor: "part[0]/measure[0]/event[1]",
        renderer_part_id: "P1",
        part_index: 0,
        measure_index: 0,
        event_index: 1,
        measure_onset_quarters: "1",
      },
      {
        canonical_id: "event:three",
        canonical_kind: "event",
        renderer_anchor: "part[0]/measure[1]/event[0]",
        renderer_part_id: "P1",
        part_index: 0,
        measure_index: 1,
        event_index: 0,
        measure_onset_quarters: "0",
      },
      {
        canonical_id: "event:four",
        canonical_kind: "event",
        renderer_anchor: "part[0]/measure[2]/event[0]",
        renderer_part_id: "P1",
        part_index: 0,
        measure_index: 2,
        event_index: 0,
        measure_onset_quarters: "0",
      },
    ],
  },
  diagnostics: [
    {
      code: "VIEWER_LAYOUT_NORMALIZED",
      severity: "info",
      message: "Layout geometry is normalized.",
      canonical_ids: [],
    },
  ],
};

test("TEST-APP-NOTATION-003 navigates canonical events, systems, and pages", async () => {
  const highlighted: string[][] = [];
  const fake: NotationAdapter = {
    load: async () => ({
      pageCount: 2,
      complete: true,
      renderedMeasures: 3,
      totalMeasures: 3,
      diagnostics: [],
      systems: [
        { index: 0, pageIndex: 0, measureIndexes: [0] },
        { index: 1, pageIndex: 0, measureIndexes: [1] },
        { index: 2, pageIndex: 1, measureIndexes: [2] },
      ],
    }),
    highlight: (position) => {
      highlighted.push(position.canonicalIds);
      return true;
    },
    dispose: vi.fn(),
  };

  render(<NotationSurface bundle={bundle} adapterFactory={() => fake} />);
  expect(await screen.findByText("Measure 1 · offset 0 quarters")).toBeInTheDocument();
  expect(highlighted).toEqual([["event:one"]]);

  fireEvent.click(screen.getByRole("button", { name: "Next event" }));
  expect(screen.getByText("Measure 1 · offset 1 quarters")).toBeInTheDocument();
  expect(highlighted.at(-1)).toEqual(["event:two"]);

  fireEvent.click(screen.getByRole("button", { name: "Next system" }));
  expect(screen.getByText("Measure 2 · offset 0 quarters")).toBeInTheDocument();
  expect(screen.getByText("System 2 of 3")).toBeInTheDocument();

  fireEvent.click(screen.getByRole("button", { name: "Next page" }));
  expect(screen.getByText("Measure 3 · offset 0 quarters")).toBeInTheDocument();
  expect(screen.getByText("Page 2 of 2")).toBeInTheDocument();
  expect(screen.getByText("Renderer notes (1)")).toBeInTheDocument();
});

test("TEST-APP-NOTATION-004 surfaces renderer failures without partial controls", async () => {
  const fake: NotationAdapter = {
    load: async () => {
      throw new NotationAdapterError("VIEWER_OSMD_RENDER_FAILED", "The score did not render.");
    },
    highlight: () => false,
    dispose: vi.fn(),
  };

  render(<NotationSurface bundle={bundle} adapterFactory={() => fake} />);
  expect(await screen.findByRole("alert")).toHaveTextContent("The score did not render.");
  expect(screen.getByRole("alert")).toHaveTextContent("VIEWER_OSMD_RENDER_FAILED");
  await waitFor(() =>
    expect(screen.queryByRole("navigation", { name: "Score navigation" })).not.toBeInTheDocument(),
  );
});

test("TEST-APP-PLAYBACK-006 moves the notation cursor from canonical audio-clock events", async () => {
  const highlighted: string[][] = [];
  const fake: NotationAdapter = {
    load: async () => ({
      pageCount: 1,
      complete: true,
      renderedMeasures: 3,
      totalMeasures: 3,
      diagnostics: [],
      systems: [{ index: 0, pageIndex: 0, measureIndexes: [0, 1, 2] }],
    }),
    highlight: (position) => {
      highlighted.push(position.canonicalIds);
      return true;
    },
    dispose: vi.fn(),
  };
  const factory = () => fake;

  const { rerender } = render(
    <NotationSurface bundle={bundle} adapterFactory={factory} focusEventIds={[]} />,
  );
  await screen.findByText("Measure 1 · offset 0 quarters");
  rerender(
    <NotationSurface
      bundle={bundle}
      adapterFactory={factory}
      focusEventIds={["event:three"]}
    />,
  );
  expect(await screen.findByText("Measure 2 · offset 0 quarters")).toBeInTheDocument();
  expect(highlighted.at(-1)).toEqual(["event:three"]);
});
