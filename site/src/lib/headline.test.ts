import { describe, expect, it } from "vitest";
import type { ForecastData } from "../types";
import { headlineFigure } from "./headline";

const m = (mae: number) => ({ mae, rmse: mae * 1.5 });
const ev = (pre: ForecastData["eval"]["pre_auction"]) =>
  ({ models: { lgbm_point: m(19.65) }, pre_auction: pre }) as unknown as ForecastData["eval"];

describe("headlineFigure", () => {
  it("is the pre-auction model against the naive error of the same run", () => {
    const h = headlineFigure(
      ev({ skill_vs_naive_pct: 17.6, models: { lgbm_pre_auction: m(25.24), naive_yesterday: m(30.62) } }),
    );
    expect(h).toEqual({ pct: 17.6, mae: 25.24, naiveMae: 30.62 });
  });

  it("is null without a pre-auction run, never the full-model figure", () => {
    expect(headlineFigure(ev(undefined))).toBeNull();
    expect(headlineFigure(ev({ skill_vs_naive_pct: 17.6, models: { lgbm_pre_auction: m(25.24) } }))).toBeNull();
  });
});
