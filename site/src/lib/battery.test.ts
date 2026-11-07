import { describe, expect, it } from "vitest";
import { fullModelEdge, revenueSplit, splitWidths } from "./battery";

const summary = (naive: number, model: number, perfect: number) =>
  ({ revenue_eur: { naive, model, perfect } }) as never;

describe("revenueSplit", () => {
  it("separates the forecast's edge from the revenue any forecast earns", () => {
    const s = revenueSplit(summary(76493.57, 80831.62, 85860.97));
    expect(s.edge).toBeCloseTo(4338.05, 1);
    expect(s.edgePct).toBeCloseTo(5.67, 1);
    expect(s.gap).toBeCloseTo(5029.35, 1);
  });
  it("copes with zero naive revenue", () => {
    expect(revenueSplit(summary(0, 10, 20)).edgePct).toBeNull();
  });
});

describe("annualised units", () => {
  const annual = {
    battery: { power_mw: 1 },
    revenue_eur: { naive: 76493.57, model: 78208.4, perfect: 85860.97 },
    revenue_eur_per_mw_year: { naive: 76915.02, model: 78639.3, perfect: 86334.03 },
    full_model: { model_edge_over_naive_eur_per_mw_year: 4361.95 },
  } as never;
  it("uses the per-year figures, the unit the sensitivity grid is in", () => {
    expect(revenueSplit(annual).edge).toBeCloseTo(1724.28, 1);
    expect(fullModelEdge(annual)).toBeCloseTo(4361.95, 2);
  });
  it("scales with the battery's power and tolerates an export without the full-model figure", () => {
    const two = { ...(annual as object), battery: { power_mw: 2 }, full_model: undefined } as never;
    expect(revenueSplit(two).edge).toBeCloseTo(3448.56, 1);
    expect(fullModelEdge(two)).toBeNull();
  });
});

describe("splitWidths", () => {
  it("adds up to the full bar", () => {
    const w = splitWidths(revenueSplit(summary(76493.57, 80831.62, 85860.97)));
    expect(w.naive + w.edge + w.gap).toBeCloseTo(100, 5);
    expect(w.edge).toBeCloseTo(5.05, 1);
  });
  it("draws no edge when the model loses to naive", () => {
    const w = splitWidths(revenueSplit(summary(80, 70, 100)));
    expect(w.edge).toBe(0);
    expect(w.naive + w.gap).toBeCloseTo(100, 5);
  });
});
