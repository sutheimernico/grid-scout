import { describe, expect, it } from "vitest";
import type { ForecastData } from "../types";
import { buildScoreboard, rulerMax } from "./scoreboard";

const m = (mae: number) => ({ mae, rmse: mae * 1.5, mae_by_hour: {}, n: 8760 });
const base: ForecastData["eval"] = {
  generated_utc: "2026-10-28T00:00:00Z",
  eval_period: { start: "2025-10-26", end: "2026-10-27", n_days: 366, refit_every_days: 7 },
  models: {
    naive_yesterday: m(30),
    seasonal_naive_7d: m(40),
    ridge_per_hour: m(24),
    lgbm_point: m(18),
  },
  quantiles: { pinball_q10: 1, pinball_q90: 1, coverage_p10_p90: 0.6, target_coverage: 0.8 },
  skill: { lgbm_vs_naive_pct: 40, lgbm_vs_seasonal_naive_pct: 55 },
  finding: "",
};

describe("buildScoreboard", () => {
  it("orders worst first and ends on the headline model", () => {
    const rows = buildScoreboard(base);
    expect(rows.map((r) => r.key)).toEqual([
      "seasonal_naive_7d",
      "naive_yesterday",
      "ridge_per_hour",
      "lgbm_point",
    ]);
  });

  it("computes skill against yesterday's prices", () => {
    const rows = buildScoreboard(base);
    expect(rows.find((r) => r.key === "lgbm_point")!.skillVsNaive).toBeCloseTo(40, 5);
    expect(rows.find((r) => r.key === "seasonal_naive_7d")!.skillVsNaive).toBeCloseTo(-33.33, 1);
  });

  it("adds the pre-auction model only when the export has it", () => {
    expect(buildScoreboard(base).some((r) => r.key === "lgbm_pre_auction")).toBe(false);
    const withPre = {
      ...base,
      pre_auction: { skill_vs_naive_pct: 17, models: { lgbm_pre_auction: { mae: 25, rmse: 38 } } },
    };
    const rows = buildScoreboard(withPre);
    expect(rows.map((r) => r.key)).toContain("lgbm_pre_auction");
    expect(rows.find((r) => r.key === "lgbm_pre_auction")!.kind).toBe("model");
    // its skill is the pipeline's own figure, not recomputed against the full run's naive error
    expect(rows.find((r) => r.key === "lgbm_pre_auction")!.skillVsNaive).toBe(17);
  });

  it("drops rows the export does not carry instead of inventing them", () => {
    const { ridge_per_hour: _r, ...models } = base.models;
    expect(buildScoreboard({ ...base, models }).map((r) => r.key)).not.toContain("ridge_per_hour");
  });
});

describe("rulerMax", () => {
  it("leaves room for the value label after the longest bar", () => {
    expect(rulerMax(buildScoreboard(base))).toBe(50);
    expect(rulerMax([])).toBe(10);
  });
});
