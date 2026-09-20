/* Shapes mirror gridscout/export.py — the pipeline is the source of truth. */

export interface MarketExplanation {
  day: string;
  caption: string;
  n_hours: number;
  mean_price: number;
  min_price: number;
  max_price: number;
  spread: number;
  negative_hours: number;
  solar_peak_mwh: number;
  wind_mean_mwh: number;
  correlation_price_vs_residual_load: number | null;
  cheapest_hours: { hour: number; price: number; residual_load_mwh: number }[];
  priciest_hours: { hour: number; price: number; residual_load_mwh: number }[];
  is_spike: boolean;
}

export interface MarketData {
  /** rule-written summary of the last fully covered day; null when incomplete */
  explanation: MarketExplanation | null;
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

export interface Segment {
  segment: string;
  n: number;
  mae_model: number;
  mae_naive: number;
  mae_snaive7: number;
  skill_vs_naive_pct: number | null;
  best: string;
}

export interface SegmentAnalysis {
  n_hours: number;
  overall: Segment;
  by_hour: Segment[];
  by_weekday: Segment[];
  by_regime: Segment[];
  definitions: Record<string, string>;
}

export interface ForecastData {
  segments: SegmentAnalysis;
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

export type HealthStatus = "ok" | "stale" | "discontinued" | "missing";

export interface HealthEntry {
  status: HealthStatus;
  last_value_at?: string;
  age_hours?: number;
  rows?: number;
  /** why a series is discontinued — shown instead of an unactionable age */
  note?: string;
}

export type ReportStatus =
  | "ok"
  | "aging"
  | "overdue"
  | "manual"
  | "unknown"
  | "unreadable"
  | "missing";

export interface ReportEntry {
  label: string;
  status: ReportStatus;
  cadence_days: number | null;
  generated_at?: string;
  age_days?: number;
  warn_after_days?: number;
  overdue_after_days?: number;
}

export interface HealthData {
  generated_at: string;
  series: Record<string, HealthEntry>;
  /** derived reports the dashboard quotes numbers from; {} on older artifacts */
  reports?: Record<string, ReportEntry>;
}

export interface LedgerWindow {
  n_days: number;
  n_hours: number;
  mae_model: number;
  mae_naive: number;
  mae_snaive7: number;
  skill_vs_naive_pct: number | null;
  days_model_beat_naive: number;
}

export interface ForwardLedgerData {
  generated_at: string;
  method: string;
  summary: {
    n_records: number;
    n_scored: number;
    n_pending: number;
    first_target_date: string | null;
    last_target_date: string | null;
    feature_set: string | null;
    cumulative: LedgerWindow | null;
    last_7_days: LedgerWindow | null;
  };
  days: {
    target_date: string;
    generated_at_utc: string;
    scored: boolean;
    mae_model: number | null;
    mae_naive: number | null;
    mae_snaive7: number | null;
  }[];
  latest: {
    target_date: string;
    generated_at_utc: string;
    scored: boolean;
    hours_local: number[];
    pred_model: number[];
    pred_naive: number[];
    actual: number[] | null;
  } | null;
}

export interface UptimeData {
  generated_at: string;
  source: string;
  scheduled_runs_per_day: number;
  reference_runs_per_day: number;
  first_day: string;
  days: { date: string; runs: number }[];
  totals: {
    days: number;
    runs: number;
    days_with_a_run: number;
    days_with_zero_runs: number;
    longest_silent_streak_days: number;
    median_runs_per_active_day: number;
  };
}
