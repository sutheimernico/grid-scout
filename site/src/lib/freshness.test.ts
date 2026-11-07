import { describe, expect, it } from "vitest";
import { healthTone, hoursSince, liveReport } from "./freshness";

describe("healthTone", () => {
  it("keeps normal lags green", () => {
    expect(healthTone({ status: "ok", age_hours: 30.8 })).toBe("good");
    expect(healthTone({ status: "ok", age_hours: 35.9 })).toBe("good");
  });
  it("turns an old but 'ok' series amber, then red", () => {
    expect(healthTone({ status: "ok", age_hours: 63.8 })).toBe("warning");
    expect(healthTone({ status: "ok", age_hours: 120 })).toBe("critical");
  });
  it("treats forecast series reaching into the future as fine", () => {
    expect(healthTone({ status: "ok", age_hours: -21.2 })).toBe("good");
  });
  it("trusts the pipeline when it is worse than the age rule", () => {
    expect(healthTone({ status: "stale", age_hours: 5 })).toBe("warning");
    expect(healthTone({ status: "missing" })).toBe("critical");
  });
  it("never paints a retired series as a fault", () => {
    expect(healthTone({ status: "discontinued", age_hours: 23000 })).toBe("muted");
  });
});

describe("freshness since the export", () => {
  it("grades the age the page would show now, not the age at export", () => {
    expect(healthTone({ status: "ok", age_hours: 15.8 })).toBe("good");
    expect(healthTone({ status: "ok", age_hours: 15.8 }, 24)).toBe("warning");
    expect(healthTone({ status: "ok", age_hours: 15.8 }, 100)).toBe("critical");
  });
  it("measures hours since the export and never goes negative", () => {
    const t0 = Date.parse("2026-10-28T12:00:00Z");
    expect(hoursSince("2026-10-28T12:00:00Z", t0 + 5 * 3_600_000)).toBe(5);
    expect(hoursSince("2026-10-28T12:00:00Z", t0 - 1000)).toBe(0);
    expect(hoursSince("garbage")).toBe(0);
  });
  it("ages a weekly report past its warn and overdue thresholds", () => {
    const r = { label: "x", status: "ok" as const, cadence_days: 7, age_days: 0, warn_after_days: 8, overdue_after_days: 15 };
    expect(liveReport(r, 24 * 3).status).toBe("ok");
    expect(liveReport(r, 24 * 9).status).toBe("aging");
    expect(liveReport(r, 24 * 16)).toEqual({ ageDays: 16, status: "overdue" });
  });
  it("leaves a manual or unknown report alone", () => {
    const r = { label: "x", status: "manual" as never, cadence_days: null, age_days: 3 };
    expect(liveReport(r, 24 * 100).status).toBe("manual");
  });
});
