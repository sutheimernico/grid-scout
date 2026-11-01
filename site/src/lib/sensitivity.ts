import type { SensitivityCell } from "../types";

export interface SensitivityMatrix {
  efficiencies: number[];
  durations: number[];
  at: (efficiency: number, duration: number) => SensitivityCell | undefined;
  edgeMin: number;
  edgeMax: number;
  /** true when the model beats naive in every cell */
  beatsEverywhere: boolean;
}

/** Efficiency x duration grid for the battery sweep; null for an empty sweep. */
export function sensitivityMatrix(cells: SensitivityCell[]): SensitivityMatrix | null {
  if (!cells.length) return null;
  const efficiencies = [...new Set(cells.map((c) => c.round_trip_efficiency))].sort((a, b) => a - b);
  const durations = [...new Set(cells.map((c) => c.duration_h))].sort((a, b) => a - b);
  const edges = cells.map((c) => c.model_edge_over_naive_eur_per_mw_year);
  const edgeMin = Math.min(...edges);
  return {
    efficiencies,
    durations,
    at: (e, d) => cells.find((c) => c.round_trip_efficiency === e && c.duration_h === d),
    edgeMin,
    edgeMax: Math.max(...edges),
    beatsEverywhere: edgeMin > 0,
  };
}
