import { describe, expect, it } from "vitest";
import { COUNT_FROM, countAt, easeOutCubic, settleAt } from "./motion";

describe("easeOutCubic", () => {
  it("runs from 0 to 1, fast first", () => {
    expect(easeOutCubic(0)).toBe(0);
    expect(easeOutCubic(1)).toBe(1);
    expect(easeOutCubic(0.5)).toBeGreaterThan(0.5);
  });
  it("clamps outside the range", () => {
    expect(easeOutCubic(-1)).toBe(0);
    expect(easeOutCubic(3)).toBe(1);
  });
});

describe("countAt", () => {
  it("lands exactly on the target", () => {
    expect(countAt(19.65, 900, 900)).toBeCloseTo(19.65, 10);
    expect(countAt(19.65, 5000, 900)).toBeCloseTo(19.65, 10);
  });
  it("starts at zero and handles a zero duration", () => {
    expect(countAt(10, 0, 900)).toBe(0);
    expect(countAt(10, 0, 0)).toBe(10);
  });
});

describe("settleAt", () => {
  it("never starts at zero and ends exactly on the target", () => {
    expect(settleAt(17.6, 0, 650)).toBeCloseTo(17.6 * COUNT_FROM, 5);
    expect(settleAt(17.6, 650, 650)).toBeCloseTo(17.6, 5);
    expect(settleAt(17.6, 9999, 650)).toBeCloseTo(17.6, 5);
    expect(settleAt(17.6, 100, 650)).toBeGreaterThan(17.6 * COUNT_FROM);
  });
});
