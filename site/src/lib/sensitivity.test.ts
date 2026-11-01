import { describe, expect, it } from "vitest";
import type { SensitivityCell } from "../types";
import { sensitivityMatrix } from "./sensitivity";

const cell = (eff: number, h: number, edge: number): SensitivityCell => ({
  round_trip_efficiency: eff,
  duration_h: h,
  capacity_mwh: h,
  revenue_eur_per_mw_year: { perfect: 90000, model: 85000, naive: 85000 - edge },
  capture_rate_model: 0.94,
  capture_rate_naive: 0.9,
  model_edge_over_naive_eur_per_mw_year: edge,
});

describe("sensitivityMatrix", () => {
  const cells = [cell(0.95, 4, 8), cell(0.85, 2, 3), cell(0.85, 4, 7), cell(0.95, 2, 4)];

  it("sorts the axes and finds cells", () => {
    const m = sensitivityMatrix(cells)!;
    expect(m.efficiencies).toEqual([0.85, 0.95]);
    expect(m.durations).toEqual([2, 4]);
    expect(m.at(0.95, 4)!.model_edge_over_naive_eur_per_mw_year).toBe(8);
    expect(m.at(0.9, 2)).toBeUndefined();
  });

  it("reports the edge range and whether it holds everywhere", () => {
    const m = sensitivityMatrix(cells)!;
    expect([m.edgeMin, m.edgeMax]).toEqual([3, 8]);
    expect(m.beatsEverywhere).toBe(true);
    expect(sensitivityMatrix([cell(0.9, 2, -1), cell(0.9, 4, 5)])!.beatsEverywhere).toBe(false);
  });

  it("is null for an empty sweep", () => {
    expect(sensitivityMatrix([])).toBeNull();
  });
});
