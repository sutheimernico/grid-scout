import { describe, expect, it } from "vitest";
import { intensity, layout } from "./Heatmap";

describe("intensity", () => {
  it("keeps a day without a run visibly empty", () => {
    expect(intensity(0, 7)).toBe(0);
  });

  it("saturates at the reference and steps down below it", () => {
    expect(intensity(7, 7)).toBe(1);
    expect(intensity(9, 7)).toBe(1);
    expect(intensity(5, 7)).toBeLessThan(1);
    expect(intensity(1, 7)).toBeLessThan(intensity(5, 7));
    expect(intensity(1, 7)).toBeGreaterThan(0);
  });
});

describe("layout", () => {
  const days = (from: string, n: number) =>
    Array.from({ length: n }, (_, i) => {
      const d = new Date(`${from}T00:00:00Z`);
      d.setUTCDate(d.getUTCDate() + i);
      return { date: d.toISOString().slice(0, 10), runs: 1 };
    });

  it("puts a week in one column, Monday first", () => {
    // 2026-07-06 is a Monday
    const cells = layout(days("2026-07-06", 8));
    expect(cells[0]).toMatchObject({ col: 0, row: 0 });
    expect(cells[6]).toMatchObject({ col: 0, row: 6 });
    expect(cells[7]).toMatchObject({ col: 1, row: 0 });
  });

  it("starts a mid-week series in the right row", () => {
    // 2026-07-04 is a Saturday -> row 5
    const cells = layout(days("2026-07-04", 3));
    expect(cells[0]).toMatchObject({ col: 0, row: 5 });
    expect(cells[2]).toMatchObject({ col: 1, row: 0 });
  });

  it("handles an empty series", () => {
    expect(layout([])).toEqual([]);
  });
});
