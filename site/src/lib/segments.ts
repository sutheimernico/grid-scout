import type { Segment } from "../types";

export interface SegmentExtremes {
  best: Segment | null;
  worst: Segment | null;
}

/** Strongest and weakest slice by skill over the naive baseline. Slices without
 *  a skill figure (no naive error to compare with) are ignored. */
export function segmentExtremes(slices: Segment[]): SegmentExtremes {
  const scored = slices.filter((s) => s.skill_vs_naive_pct != null);
  if (!scored.length) return { best: null, worst: null };
  const sorted = [...scored].sort((a, b) => b.skill_vs_naive_pct! - a.skill_vs_naive_pct!);
  return { best: sorted[0], worst: sorted[sorted.length - 1] };
}

/** Slices where something other than the model had the lowest error. */
export function losingSlices(slices: Segment[]): Segment[] {
  return slices.filter((s) => s.best !== "model");
}
