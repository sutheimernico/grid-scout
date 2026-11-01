import { describe, expect, it } from "vitest";
import type { Segment } from "../types";
import { losingSlices, segmentExtremes } from "./segments";

const seg = (segment: string, skill: number | null, best = "model"): Segment => ({
  segment,
  n: 100,
  mae_model: 10,
  mae_naive: 20,
  mae_snaive7: 25,
  skill_vs_naive_pct: skill,
  best,
});

describe("segmentExtremes", () => {
  it("finds the best and the worst slice", () => {
    const { best, worst } = segmentExtremes([seg("04:00", 34), seg("20:00", 9), seg("12:00", 20)]);
    expect([best!.segment, worst!.segment]).toEqual(["04:00", "20:00"]);
  });

  it("ignores slices without a skill figure and copes with none at all", () => {
    expect(segmentExtremes([seg("a", null)])).toEqual({ best: null, worst: null });
    expect(segmentExtremes([seg("a", null), seg("b", 5)]).best!.segment).toBe("b");
  });
});

describe("losingSlices", () => {
  it("lists slices the model did not win", () => {
    expect(losingSlices([seg("a", 5), seg("b", -2, "naive")]).map((s) => s.segment)).toEqual(["b"]);
  });
});
