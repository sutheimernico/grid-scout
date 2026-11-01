import { describe, expect, it } from "vitest";
import type { ForwardLedgerData } from "../types";
import { hasRecordedForecasts, lastScoredDay, liveTomorrow } from "./live";

const latest = (scored: boolean) => ({
  target_date: "2026-10-29",
  generated_at_utc: "2026-10-28T08:40:00Z",
  scored,
  hours_local: [0],
  pred_model: [1],
  pred_naive: [1],
  actual: scored ? [1] : null,
});
const ledger = (scored: boolean, n_records = 2): ForwardLedgerData => ({
  generated_at: "x",
  method: "m",
  summary: {
    n_records,
    n_scored: 1,
    n_pending: 1,
    first_target_date: "2026-10-28",
    last_target_date: "2026-10-29",
    feature_set: "pre_auction",
    cumulative: null,
    last_7_days: null,
  },
  days: [
    { target_date: "2026-10-28", generated_at_utc: "x", scored: true, mae_model: 10, mae_naive: 20, mae_snaive7: 25 },
    { target_date: "2026-10-29", generated_at_utc: "x", scored: false, mae_model: null, mae_naive: null, mae_snaive7: null },
  ],
  latest: latest(scored),
});

describe("liveTomorrow", () => {
  it("is the open forecast and nothing else", () => {
    expect(liveTomorrow(ledger(false))?.target_date).toBe("2026-10-29");
    expect(liveTomorrow(ledger(true))).toBeNull();
    expect(liveTomorrow(null)).toBeNull();
  });
});

describe("lastScoredDay", () => {
  it("skips the pending day", () => {
    expect(lastScoredDay(ledger(false))?.date).toBe("2026-10-28");
    expect(lastScoredDay(null)).toBeNull();
  });
});

describe("hasRecordedForecasts", () => {
  it("is false for a missing or empty ledger", () => {
    expect(hasRecordedForecasts(null)).toBe(false);
    expect(hasRecordedForecasts(ledger(false, 0))).toBe(false);
    expect(hasRecordedForecasts(ledger(false, 3))).toBe(true);
  });
});
