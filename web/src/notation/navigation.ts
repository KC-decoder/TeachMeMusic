import type { RenderAnchor } from "../contracts/viewer";

export interface ExactRational {
  numerator: number;
  denominator: number;
}

export interface HighlightPosition {
  measureIndex: number;
  onsetQuarters: ExactRational;
  onsetLabel: string;
  canonicalIds: string[];
}

export function parseExactRational(value: string): ExactRational {
  const match = /^(-?\d+)(?:\/(\d+))?$/.exec(value);
  if (!match) throw new Error("invalid exact rational");
  const numerator = Number(match[1]);
  const denominator = Number(match[2] ?? "1");
  if (!Number.isSafeInteger(numerator) || !Number.isSafeInteger(denominator) || denominator <= 0) {
    throw new Error("invalid exact rational");
  }
  let left = Math.abs(numerator);
  let right = denominator;
  while (right !== 0) {
    [left, right] = [right, left % right];
  }
  const divisor = left || 1;
  return { numerator: numerator / divisor, denominator: denominator / divisor };
}

function compareRational(left: ExactRational, right: ExactRational): number {
  return left.numerator * right.denominator - right.numerator * left.denominator;
}

export function buildHighlightPositions(anchors: RenderAnchor[]): HighlightPosition[] {
  const positions = new Map<string, HighlightPosition>();
  for (const anchor of anchors) {
    if (
      anchor.canonical_kind !== "event" ||
      anchor.measure_index === null ||
      anchor.measure_onset_quarters === null
    ) {
      continue;
    }
    const onset = parseExactRational(anchor.measure_onset_quarters);
    if (onset.numerator < 0) throw new Error("event onset cannot be negative");
    const key = `${anchor.measure_index}:${onset.numerator}/${onset.denominator}`;
    const existing = positions.get(key);
    if (existing) {
      existing.canonicalIds.push(anchor.canonical_id);
    } else {
      positions.set(key, {
        measureIndex: anchor.measure_index,
        onsetQuarters: onset,
        onsetLabel: anchor.measure_onset_quarters,
        canonicalIds: [anchor.canonical_id],
      });
    }
  }
  return [...positions.values()].sort((left, right) =>
    left.measureIndex === right.measureIndex
      ? compareRational(left.onsetQuarters, right.onsetQuarters)
      : left.measureIndex - right.measureIndex,
  );
}
