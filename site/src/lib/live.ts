import type { ForwardLedgerData } from "../types";
import { ledgerRows } from "./ledger";

/** The ledger's newest forecast when its outcome is still open, i.e. a forecast
 *  for a delivery day that has not been scored. This is the only thing the page
 *  may call "tomorrow". */
export function liveTomorrow(ledger: ForwardLedgerData | null): NonNullable<ForwardLedgerData["latest"]> | null {
  const latest = ledger?.latest;
  return latest && !latest.scored ? latest : null;
}

/** The most recent delivery day that already has a score, for context next to
 *  an open forecast. */
export function lastScoredDay(ledger: ForwardLedgerData | null) {
  if (!ledger) return null;
  return ledgerRows(ledger.days).find((r) => r.outcome !== "pending") ?? null;
}

export function hasRecordedForecasts(ledger: ForwardLedgerData | null): boolean {
  return (ledger?.summary.n_records ?? 0) > 0;
}
