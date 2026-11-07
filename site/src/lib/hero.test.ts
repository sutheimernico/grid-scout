import { describe, expect, it } from "vitest";
import { negativeSpans, pickHeroWindow, type RecentSeries } from "./hero";

function hours(startIso: string, n: number): string[] {
  const t0 = new Date(startIso).getTime();
  return Array.from({ length: n }, (_, i) => new Date(t0 + i * 3_600_000).toISOString());
}

function series(startIso: string, n: number, fill = (i: number) => i): RecentSeries {
  return {
    timestamps: hours(startIso, n),
    actual: Array.from({ length: n }, (_, i) => fill(i)),
    predicted: Array.from({ length: n }, (_, i) => fill(i) + 2),
    q10: Array.from({ length: n }, (_, i) => fill(i) - 5),
    q90: Array.from({ length: n }, (_, i) => fill(i) + 5),
  };
}

describe("negativeSpans", () => {
  it("returns runs of sub-zero hours as half-open ranges", () => {
    expect(negativeSpans([5, -1, -2, 3, null, -1])).toEqual([
      [1, 3],
      [5, 6],
    ]);
  });
  it("closes a run that lasts until the end", () => {
    expect(negativeSpans([1, -1, -1])).toEqual([[1, 3]]);
  });
  it("treats a gap as the end of a run, not as a negative price", () => {
    expect(negativeSpans([-1, null, -1])).toEqual([
      [0, 1],
      [2, 3],
    ]);
  });
});

describe("pickHeroWindow", () => {
  it("takes the last complete Berlin days and drops a partial first day", () => {
    // starts 2026-10-20 12:00 Berlin (CEST); 10 days of data
    const w = pickHeroWindow(series("2026-10-20T10:00:00Z", 240))!;
    expect(w.days).toHaveLength(3);
    expect(w.stats.nHours).toBe(72);
    expect(w.days.map((d) => d.to - d.from)).toEqual([24, 24, 24]);
    expect(w.days[0].from).toBe(0);
    expect(w.days[2].to).toBe(72);
  });

  it("counts a 25-hour DST day as one day", () => {
    // fall-back is 2026-10-25; the series covers 24-27 Oct fully
    const w = pickHeroWindow(series("2026-10-23T22:00:00Z", 24 * 4 + 1), 3)!;
    expect(w.days.map((d) => d.date)).toEqual(["2026-10-25", "2026-10-26", "2026-10-27"]);
    expect(w.days[0].to - w.days[0].from).toBe(25);
  });

  it("keeps only the latest unbroken run when a day has prices but no forecast", () => {
    const s = series("2026-10-23T22:00:00Z", 24 * 4 + 1);
    // 25 Oct (hours 24 to 48 of the series, 25 h) has no forecast at all
    const predicted = s.predicted.map((v, i) => (i >= 24 && i < 49 ? null : v));
    const w = pickHeroWindow({ ...s, predicted }, 3)!;
    // 24 Oct is complete but not adjacent to 26 Oct: it is not glued onto the axis
    expect(w.days.map((d) => d.date)).toEqual(["2026-10-26", "2026-10-27"]);
    expect(w.stats.nHours).toBe(w.timestamps.length);
    expect(w.predicted.every((v) => v != null)).toBe(true);
  });

  it("returns null when no day is complete", () => {
    expect(pickHeroWindow(series("2026-10-20T10:00:00Z", 10))).toBeNull();
  });

  it("measures mae and band coverage from the window only", () => {
    const base = series("2026-10-26T23:00:00Z", 24); // exactly 2026-10-27 Berlin
    base.actual[0] = 100; // outside band [q10, q90] = [-5+0.., ...]
    const w = pickHeroWindow(base)!;
    expect(w.stats.mae).toBeCloseTo((98 + 2 * 23) / 24, 5);
    expect(w.stats.coverage).toBeCloseTo(23 / 24, 5);
  });

  it("keeps gaps as null and does not count them", () => {
    const base = series("2026-10-26T23:00:00Z", 24);
    base.actual[3] = null;
    const w = pickHeroWindow(base)!;
    expect(w.actual[3]).toBeNull();
    expect(w.stats.mae).toBeCloseTo(2, 5);
  });
});
