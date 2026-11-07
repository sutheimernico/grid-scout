import type { ForecastData } from "../types";

export interface Headline {
  /** error reduction against yesterday's prices, percent */
  pct: number;
  mae: number;
  naiveMae: number;
}

/** The number the page opens with: the model that only sees what exists before
 *  the 12:00 auction. Null when the export carries no pre-auction run, so the
 *  page never substitutes the flattering full-model figure for it. */
export function headlineFigure(evalData: ForecastData["eval"]): Headline | null {
  const pre = evalData.pre_auction;
  const model = pre?.models.lgbm_pre_auction;
  const naive = pre?.models.naive_yesterday;
  if (!pre || !model || !naive) return null;
  return { pct: pre.skill_vs_naive_pct, mae: model.mae, naiveMae: naive.mae };
}
