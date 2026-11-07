import { describe, expect, it } from "vitest";
import { fmtPrice, prettyText, unitSpelling, fmtCalendarDate, fmtDateTime, fmtHourLabel, fmtMonthYear, fmtNum, fmtPct, fmtSigned, localParts } from "./format";

describe("fmtNum", () => {
  it("groups thousands and fixes decimals", () => {
    expect(fmtNum(80831.62)).toBe("80,832");
    expect(fmtNum(19.6668, 2)).toBe("19.67");
  });

  it("never prints a negative zero", () => {
    expect(fmtNum(-0)).toBe("0");
    expect(fmtNum(-0.004, 2)).toBe("0.00");
  });
});

describe("fmtSigned", () => {
  it("uses a real minus sign and an explicit plus", () => {
    expect(fmtSigned(4338.04)).toBe("+4,338");
    expect(fmtSigned(-1.68, 2)).toBe("−1.68");
    expect(fmtSigned(0)).toBe("0");
  });
});

describe("fmtPct", () => {
  it("takes a fraction", () => {
    expect(fmtPct(0.9414)).toBe("94.1%");
    expect(fmtPct(0.75, 0)).toBe("75%");
  });
});

describe("localParts", () => {
  it("reads the Berlin clock in winter time", () => {
    const p = localParts("2026-10-27T22:00:00+00:00");
    expect(p).toMatchObject({ date: "2026-10-27", hour: 23, weekday: "Tue", dayLabel: "Tue 27 Oct" });
  });

  it("reads the Berlin clock in summer time and rolls the date over", () => {
    const p = localParts("2026-07-01T22:00:00+00:00");
    expect(p).toMatchObject({ date: "2026-07-02", hour: 0 });
  });
});

describe("dates and hours", () => {
  it("pads the hour", () => {
    expect(fmtHourLabel(7)).toBe("07:00");
  });
  it("formats a calendar date without shifting it", () => {
    expect(fmtCalendarDate("2026-10-28")).toBe("28 Oct 2026");
  });
  it("spells September as Sep whatever the engine's locale data says", () => {
    expect(fmtCalendarDate("2026-09-20")).toBe("20 Sep 2026");
    expect(localParts("2026-09-20T10:00:00Z").dayLabel).toBe("Sun 20 Sep");
    expect(fmtMonthYear("2026-09-20")).toBe("Sep 2026");
  });
  it("shows date-times on the Berlin clock", () => {
    expect(fmtDateTime("2026-10-28T13:50:00+00:00")).toBe("28 Oct, 14:50");
    expect(fmtDateTime("2026-07-01T08:05:00+00:00")).toBe("1 Jul, 10:05");
  });
});

describe("fmtPrice", () => {
  it("has no plus sign and a true minus", () => {
    expect(fmtPrice(226.94)).toBe("226.9");
    expect(fmtPrice(-4)).toBe("\u22124.0");
    expect(fmtPrice(-0.02)).toBe("0.0");
  });
});

describe("unitSpelling", () => {
  it("uses one unit spelling", () => {
    expect(unitSpelling("low of -4.99 EUR/MWh and 100 EUR/MW/yr")).toBe("low of -4.99 €/MWh and 100 €/MW/yr");
  });
});

describe("prettyText", () => {
  it("sets generated sentences in the page's conventions", () => {
    const out = prettyText("2026-10-25: cheapest hour 03:00 at -0.01 EUR/MWh with 0.0 GW of solar and -0.6 GW residual load");
    expect(out).toBe("25 Oct 2026: cheapest hour 03:00 at \u22120.01 €/MWh with 0.0 GW of solar and \u22120.6 GW residual load");
  });
  it("does not touch hyphens inside words or dates it cannot read", () => {
    expect(prettyText("day-ahead and walk-forward, 10-20 MW")).toBe("day-ahead and walk-forward, 10-20 MW");
  });
});

describe("fmtNum negatives", () => {
  it("uses a real minus sign on axes too", () => {
    expect(fmtNum(-50)).toBe("\u221250");
    expect(fmtNum(-1234.5, 1)).toBe("\u22121,234.5");
  });
});
