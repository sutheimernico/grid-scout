import { describe, expect, it } from "vitest";
import { fmtCalendarDate, fmtHourLabel, fmtNum, fmtPct, fmtSigned, localParts } from "./format";

describe("fmtNum", () => {
  it("groups thousands and fixes decimals", () => {
    expect(fmtNum(80831.62)).toBe("80,832");
    expect(fmtNum(19.6668, 2)).toBe("19.67");
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
});
