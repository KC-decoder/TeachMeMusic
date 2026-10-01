import { buildHighlightPositions, parseExactRational } from "./navigation";
import type { RenderAnchor } from "../contracts/viewer";

function anchor(id: string, measure: number, event: number, onset: string): RenderAnchor {
  return {
    canonical_id: id,
    canonical_kind: "event",
    renderer_anchor: `measure[${measure}]/event[${event}]`,
    renderer_part_id: "P1",
    part_index: 0,
    measure_index: measure,
    event_index: event,
    measure_onset_quarters: onset,
  };
}

test("TEST-APP-NOTATION-001 groups simultaneous canonical events exactly", () => {
  const positions = buildHighlightPositions([
    anchor("event:later", 1, 0, "1/2"),
    anchor("event:chord-a", 0, 0, "0"),
    anchor("event:chord-b", 0, 1, "0/2"),
  ]);

  expect(positions).toHaveLength(2);
  expect(positions[0]?.canonicalIds).toEqual(["event:chord-a", "event:chord-b"]);
  expect(positions[1]).toMatchObject({ measureIndex: 1, onsetLabel: "1/2" });
});

test("TEST-APP-NOTATION-002 rejects inexact or unsafe position values", () => {
  expect(parseExactRational("3/2")).toEqual({ numerator: 3, denominator: 2 });
  expect(() => parseExactRational("0.5")).toThrow("invalid exact rational");
  expect(() => parseExactRational("1/0")).toThrow("invalid exact rational");
  expect(() => buildHighlightPositions([anchor("event:bad", 0, 0, "-1")])).toThrow(
    "event onset cannot be negative",
  );
});
