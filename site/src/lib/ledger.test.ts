import { describe, expect, it } from "vitest";
import { ledgerRows, ledgerScaleMax } from "./ledger";

const day = (target_date: string, model: number | null, naive: number | null, scored = true) => ({
  target_date,
  generated_at_utc: "2026-10-01T09:00:00Z",
  scored,
  mae_model: model,
  mae_naive: naive,
  mae_snaive7: null,
});

describe("ledgerRows", () => {
  it("sorts newest first and judges each day against naive", () => {
    const rows = ledgerRows([day("2026-10-01", 10, 20), day("2026-10-03", 30, 20), day("2026-10-02", 5, 5)]);
    expect(rows.map((r) => [r.date, r.outcome])).toEqual([
      ["2026-10-03", "loss"],
      ["2026-10-02", "tie"],
      ["2026-10-01", "win"],
    ]);
    expect(rows[2].gain).toBe(10);
  });

  it("never counts an unscored day as a win", () => {
    const [row] = ledgerRows([day("2026-10-04", null, null, false)]);
    expect(row).toMatchObject({ outcome: "pending", gain: null });
  });

  it("treats a scored flag without numbers as pending", () => {
    expect(ledgerRows([day("2026-10-04", null, 3, true)])[0].outcome).toBe("pending");
  });
});

describe("ledgerScaleMax", () => {
  it("rounds up and has a floor", () => {
    expect(ledgerScaleMax(ledgerRows([day("2026-10-01", 12, 31)]))).toBe(40);
    expect(ledgerScaleMax([])).toBe(10);
  });
});
