import { describe, expect, it } from "vitest";
import { revenueSplit, splitWidths } from "./battery";

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
