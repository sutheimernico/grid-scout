import type { BatteryData } from "../types";

export interface RevenueSplit {
  naive: number;
  model: number;
  perfect: number;
  /** model minus naive: what the forecast adds */
  edge: number;
  /** edge as a share of the naive revenue, in percent */
  edgePct: number | null;
  /** perfect foresight minus model: what is still on the table */
  gap: number;
}

/** Revenue split in € per year for the configured battery, annualised from the
 *  backtest's n days (the sweep below is in the same unit, so the two compare). */
export function revenueSplit(summary: BatteryData["summary"]): RevenueSplit {
  const mw = summary.battery?.power_mw ?? 1;
  const perYear = summary.revenue_eur_per_mw_year;
  const { naive, model, perfect } = perYear
    ? { naive: perYear.naive * mw, model: perYear.model * mw, perfect: perYear.perfect * mw }
    : summary.revenue_eur;
  const edge = model - naive;
  return { naive, model, perfect, edge, edgePct: naive > 0 ? (edge / naive) * 100 : null, gap: perfect - model };
}

/** Widths in percent of the perfect-foresight revenue for the three segments of
 *  the bar: naive | edge | gap. A negative edge draws no edge segment; the
 *  caller says so in words. */
export function splitWidths(s: RevenueSplit): { naive: number; edge: number; gap: number } {
  const total = s.perfect > 0 ? s.perfect : 1;
  const base = Math.min(s.naive, s.model);
  const edge = Math.max(s.edge, 0);
  return {
    naive: (base / total) * 100,
    edge: (edge / total) * 100,
    gap: Math.max(0, ((s.perfect - base - edge) / total) * 100),
  };
}

/** What the full model would add instead, per year, or null when the export has no such figure. */
export function fullModelEdge(summary: BatteryData["summary"]): number | null {
  const e = summary.full_model?.model_edge_over_naive_eur_per_mw_year;
  return e == null ? null : e * (summary.battery?.power_mw ?? 1);
}
