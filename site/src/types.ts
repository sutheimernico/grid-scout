/* Shapes mirror gridscout/export.py — the pipeline is the source of truth. */

export interface MarketData {
  kpis: {
    latest_price_eur_mwh: number;
    latest_price_at: string;
    negative_price_hours_ytd: number;
    renewables_share_last_24h: number;
  };
  hourly: {
    timestamps: string[];
    price: (number | null)[];
    load: (number | null)[];
    generation: Record<string, (number | null)[]>;
  };
  generation_labels: Record<string, string>;
  renewable_keys: string[];
}

export interface ForecastData {
  eval: {
    generated_utc: string;
    eval_period: { start: string; end: string; n_days: number; refit_every_days: number };
    models: Record<string, { mae: number; rmse: number; mae_by_hour: Record<string, number>; n: number }>;
    quantiles: {
      pinball_q10: number;
      pinball_q90: number;
      coverage_p10_p90: number;
      target_coverage: number;
    };
    skill: { lgbm_vs_naive_pct: number; lgbm_vs_seasonal_naive_pct: number };
    finding: string;
  };
  recent: {
    timestamps: string[];
    actual: (number | null)[];
    predicted: (number | null)[];
    q10: (number | null)[];
    q90: (number | null)[];
  };
}

export interface BatteryData {
  summary: {
    battery: { power_mw: number; capacity_mwh: number; round_trip_efficiency: number };
    n_days: number;
    revenue_eur: { perfect: number; model: number; naive: number };
    revenue_eur_per_mw_year: { perfect: number; model: number; naive: number };
    capture_rate_model: number;
    capture_rate_naive: number;
    model_edge_over_naive_eur: number;
    skipped_days: number;
  };
  daily: {
    days: string[];
    cumulative_perfect: number[];
    cumulative_model: number[];
    cumulative_naive: number[];
  };
}

export interface AgentData {
  model: string;
  n: number;
  pass_rate: number;
  by_type: Record<string, { n: number; passed: number; pass_rate: number }>;
  grading: string;
  examples: {
    type: string;
    question: string;
    answer: string;
    gold: string;
    passed: boolean;
    tools_used: string[];
  }[];
}

export interface HealthData {
  generated_at: string;
  series: Record<
    string,
    { status: "ok" | "stale" | "missing"; last_value_at?: string; age_hours?: number; rows?: number }
  >;
}
