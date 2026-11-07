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
 *  ladder. Models the export does not carry are left out rather than guessed.
 *
 *  When the export has a pre-auction run, EVERY row comes from it: it covers
 *  slightly fewer hours than the full-model run, and mixing the two would show
 *  two different naive errors (30.62 vs 30.59) for the same baseline. */
export function buildScoreboard(evalData: ForecastData["eval"]): ScoreRow[] {
  const preModels = evalData.pre_auction?.models;
  // only a complete pre-auction run (baselines and both LightGBM runs) can carry the whole ruler
  const pre = preModels?.naive_yesterday && preModels.lgbm_gate_closure ? preModels : undefined;
  const src = (key: string, preKey: string = key) => (pre ? pre[preKey] : evalData.models[key]);
  const naive = src("naive_yesterday")?.mae ?? null;
  const skill = (mae: number) => (naive == null || naive === 0 ? null : ((naive - mae) / naive) * 100);
  const rows: ScoreRow[] = [];

  for (const def of ROWS) {
    const preKey = def.key === "ridge_per_hour" ? "ridge_pre_auction" : def.key;
    const m = src(def.key, preKey);
    if (!m) continue;
    const detail = pre && def.key === "ridge_per_hour" ? "linear baseline, pre-auction inputs" : def.detail;
    const label = pre && def.key === "ridge_per_hour" ? "Ridge, pre-auction inputs" : def.label;
    rows.push({ ...def, label, detail, mae: m.mae, rmse: m.rmse, skillVsNaive: skill(m.mae) });
  }
  const honest = preModels?.lgbm_pre_auction;
  if (honest)
    rows.push({
      key: "lgbm_pre_auction",
      label: "LightGBM, strictly pre-auction inputs",
      detail: "nothing dated on the delivery day",
      kind: "model",
      mae: honest.mae,
      rmse: honest.rmse,
      skillVsNaive: evalData.pre_auction?.skill_vs_naive_pct ?? skill(honest.mae),
    });
  const main = pre ? pre.lgbm_gate_closure : evalData.models.lgbm_point;
  if (main)
    rows.push({
      key: "lgbm_point",
      label: "LightGBM, with the TSOs' generation forecast",
      detail: "uses data SMARD publishes after the auction",
      kind: "model",
      mae: main.mae,
      rmse: main.rmse,
      skillVsNaive: skill(main.mae),
    });

  return rows.sort((a, b) => b.mae - a.mae);
}

/** Upper end of the ruler: the worst MAE plus room for its value label, rounded
 *  up to the next 10. */
export function rulerMax(rows: ScoreRow[]): number {
  const worst = Math.max(0, ...rows.map((r) => r.mae));
  return Math.max(10, Math.ceil((worst * 1.25) / 10) * 10);
}
