import { describe, expect, it } from "vitest";
import { healthTone } from "./freshness";

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
