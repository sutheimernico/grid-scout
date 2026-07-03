import { describe, expect, it } from "vitest";
import { bandPath, extent, linePath, linearScale, ticks } from "./scale";

describe("linearScale", () => {
  it("maps domain to range linearly", () => {
    const s = linearScale([0, 10], [0, 100]);
    expect(s(0)).toBe(0);
    expect(s(5)).toBe(50);
    expect(s(10)).toBe(100);
  });

  it("supports inverted ranges (SVG y-axis)", () => {
    const s = linearScale([0, 10], [200, 0]);
    expect(s(0)).toBe(200);
    expect(s(10)).toBe(0);
  });

  it("does not divide by zero on a flat domain", () => {
    const s = linearScale([5, 5], [0, 100]);
    expect(Number.isFinite(s(5))).toBe(true);
  });
});

describe("ticks", () => {
  it("produces nicely rounded steps covering the domain", () => {
    const t = ticks([0, 700], 5);
    expect(t[0]).toBe(0);
    expect(t).toContain(200);
    expect(t[t.length - 1]).toBeLessThanOrEqual(700);
  });

  it("handles negative domains", () => {
    const t = ticks([-120, 80], 5);
    expect(t.some((v) => v < 0)).toBe(true);
    expect(t).toContain(0);
  });
});

describe("extent", () => {
  it("spans all series and ignores nulls", () => {
    expect(
      extent([
        [1, null, 5],
        [-2, 3],
      ]),
    ).toEqual([-2, 5]);
  });

  it("falls back to [0,1] for all-null input", () => {
    expect(extent([[null, null]])).toEqual([0, 1]);
  });
});

describe("linePath", () => {
  const x = (i: number) => i * 10;
  const y = (v: number) => 100 - v;

  it("breaks the line at null gaps", () => {
    const d = linePath([1, null, 3], x, y);
    expect(d).toBe("M0.0,99.0M20.0,97.0");
  });

  it("connects consecutive points", () => {
    const d = linePath([1, 2], x, y);
    expect(d).toBe("M0.0,99.0L10.0,98.0");
  });
});

describe("bandPath", () => {
  it("closes the polygon between upper and lower", () => {
    const x = (i: number) => i;
    const y = (v: number) => v;
    const d = bandPath([10, 10], [0, 0], x, y);
    expect(d.startsWith("M")).toBe(true);
    expect(d.endsWith("Z")).toBe(true);
  });

  it("skips indices where either side is null", () => {
    const d = bandPath([10, null], [0, 0], (i) => i, (v) => v);
    expect(d).toBe("M0.0,10.0L0.0,0.0Z");
  });
});
