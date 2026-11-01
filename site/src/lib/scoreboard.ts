import type { ForecastData } from "../types";

export type RowKind = "baseline" | "model";

export interface ScoreRow {
  key: string;
  label: string;
  detail: string;
  kind: RowKind;
  mae: number;
  rmse: number;
  /** improvement over "yesterday's prices" in percent; negative = worse */
  skillVsNaive: number | null;
}

const ROWS: { key: string; label: string; detail: string; kind: RowKind }[] = [
  { key: "seasonal_naive_7d", label: "Same weekday last week", detail: "seasonal naive", kind: "baseline" },
  { key: "naive_yesterday", label: "Yesterday's prices", detail: "naive", kind: "baseline" },
  { key: "ridge_per_hour", label: "Ridge, one model per hour", detail: "linear baseline", kind: "baseline" },
];

/** Rows for the scoreboard ruler, worst error first so the model closes the
 *  ladder. Models the export does not carry are left out rather than guessed. */
export function buildScoreboard(evalData: ForecastData["eval"]): ScoreRow[] {
  const naive = evalData.models.naive_yesterday?.mae ?? null;
  const skill = (mae: number) => (naive == null || naive === 0 ? null : ((naive - mae) / naive) * 100);
  const rows: ScoreRow[] = [];

  for (const def of ROWS) {
    const m = evalData.models[def.key];
    if (m) rows.push({ ...def, mae: m.mae, rmse: m.rmse, skillVsNaive: skill(m.mae) });
  }
  const pre = evalData.pre_auction?.models.lgbm_pre_auction;
  if (pre)
    rows.push({
      key: "lgbm_pre_auction",
      label: "LightGBM, strictly pre-auction inputs",
      detail: "nothing dated on the delivery day",
      kind: "model",
      mae: pre.mae,
      rmse: pre.rmse,
      skillVsNaive: skill(pre.mae),
    });
  const main = evalData.models.lgbm_point;
  if (main)
    rows.push({
      key: "lgbm_point",
      label: "LightGBM, with the TSOs' generation forecast",
      detail: "assumed known at gate closure",
      kind: "model",
      mae: main.mae,
      rmse: main.rmse,
      skillVsNaive: skill(main.mae),
    });

  return rows.sort((a, b) => b.mae - a.mae);
}

/** Upper end of the ruler: the worst MAE rounded up to the next 10. */
export function rulerMax(rows: ScoreRow[]): number {
  const worst = Math.max(0, ...rows.map((r) => r.mae));
  return Math.max(10, Math.ceil(worst / 10) * 10);
}
