import type { ForwardLedgerData } from "../types";

export type Outcome = "win" | "loss" | "tie" | "pending";

export interface LedgerRow {
  date: string;
  outcome: Outcome;
  maeModel: number | null;
  maeNaive: number | null;
  /** naive minus model; positive = the forecast was closer */
  gain: number | null;
}

/** Newest delivery day first. A day without a score is "pending", never a win. */
export function ledgerRows(days: ForwardLedgerData["days"]): LedgerRow[] {
  return [...days]
    .sort((a, b) => b.target_date.localeCompare(a.target_date))
    .map((d) => {
      if (!d.scored || d.mae_model == null || d.mae_naive == null)
        return { date: d.target_date, outcome: "pending", maeModel: null, maeNaive: null, gain: null };
      const gain = d.mae_naive - d.mae_model;
      const outcome: Outcome = gain > 0 ? "win" : gain < 0 ? "loss" : "tie";
      return { date: d.target_date, outcome, maeModel: d.mae_model, maeNaive: d.mae_naive, gain };
    });
}

/** Upper end of the dumbbell scale: largest scored MAE rounded up to 10. */
export function ledgerScaleMax(rows: LedgerRow[]): number {
  const worst = Math.max(0, ...rows.flatMap((r) => [r.maeModel ?? 0, r.maeNaive ?? 0]));
  return Math.max(10, Math.ceil(worst / 10) * 10);
}
