import { act, cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import App, { SETTLE_TIMEOUT_MS, sumMembers } from "./App";
import type {
  AgentData,
  BatteryData,
  ForecastData,
  ForwardLedgerData,
  HealthData,
  MarketData,
  UptimeData,
} from "./types";

/* useArtifact is the only IO in the app. vi.hoisted lets the mock factory — which
   vitest hoists above the imports — share the map the tests drive states from. */
const { artifacts } = vi.hoisted(() => ({ artifacts: new Map<string, unknown>() }));
vi.mock("./lib/useData", () => ({
  useArtifact: (name: string) => artifacts.get(name) ?? { state: "loading" },
}));

const market: MarketData = {
  explanation: {
    day: "2026-09-19",
    caption: "Cheapest hour 13:00 at -1.68 EUR/MWh with 26.8 GW of solar.",
    n_hours: 24,
    mean_price: 61.2,
    min_price: -1.68,
    max_price: 120.78,
    spread: 122.46,
    negative_hours: 6,
    solar_peak_mwh: 26800,
    wind_mean_mwh: 9000,
    correlation_price_vs_residual_load: 0.87,
    cheapest_hours: [{ hour: 13, price: -1.68, residual_load_mwh: -4600 }],
    priciest_hours: [{ hour: 17, price: 120.78, residual_load_mwh: 17900 }],
    is_spike: false,
  },
  kpis: {
    latest_price_eur_mwh: 82.5,
    latest_price_at: "2026-09-20T10:00:00+00:00",
    negative_price_hours_ytd: 123,
    renewables_share_last_24h: 0.62,
  },
  hourly: {
    timestamps: [
      "2026-09-20T08:00:00+00:00",
      "2026-09-20T09:00:00+00:00",
      "2026-09-20T10:00:00+00:00",
    ],
    price: [10, 20, 30],
    load: [40000, 41000, 42000],
    generation: { gen_solar: [1000, 2000, 3000], gen_wind_onshore: [500, 600, 700] },
  },
  generation_labels: { gen_solar: "photovoltaics" },
  renewable_keys: ["gen_solar", "gen_wind_onshore"],
};

const modelMetrics = { mae: 15.25, rmse: 25.1, mae_by_hour: { "0": 12 }, n: 8760 };
const seg = (segment: string, skill: number | null, best = "model") => ({
  segment,
  n: 365,
  mae_model: 17.6,
  mae_naive: 28.5,
  mae_snaive7: 36.1,
  skill_vs_naive_pct: skill,
  best,
});
const forecast: ForecastData = {
  segments: {
    n_hours: 8760,
    overall: seg("overall", 38.1),
    by_hour: [seg("00:00", 40.2), seg("20:00", -4.5, "naive")],
    by_weekday: [seg("Mon", 54.3), seg("Sun", 19.1)],
    by_regime: [seg("negative prices", 51.4), seg("volatile days", 21.1)],
    definitions: { "negative prices": "hours that cleared below 0 EUR/MWh" },
  },
  eval: {
    generated_utc: "2026-09-14T07:56:19+00:00",
    eval_period: { start: "2025-09-13", end: "2026-09-12", n_days: 365, refit_every_days: 7 },
    models: {
      lgbm_point: modelMetrics,
      naive_yesterday: { ...modelMetrics, mae: 27.22 },
      seasonal_naive_7d: { ...modelMetrics, mae: 26.1 },
    },
    quantiles: { pinball_q10: 1, pinball_q90: 2, coverage_p10_p90: 0.67, target_coverage: 0.8 },
    skill: { lgbm_vs_naive_pct: 44.0, lgbm_vs_seasonal_naive_pct: 41.5 },
    finding: "LightGBM beats the naive baseline by +44.0%.",
  },
  recent: {
    timestamps: market.hourly.timestamps,
    actual: [10, 20, 30],
    predicted: [11, 19, 32],
    q10: [5, 15, 25],
    q90: [15, 25, 35],
  },
};

const battery: BatteryData = {
  summary: {
    battery: { power_mw: 1, capacity_mwh: 2, round_trip_efficiency: 0.86 },
    n_days: 364,
    revenue_eur: { perfect: 81822, model: 76217, naive: 72933 },
    revenue_eur_per_mw_year: { perfect: 82047, model: 76426, naive: 73133 },
    capture_rate_model: 0.9315,
    capture_rate_naive: 0.8914,
    model_edge_over_naive_eur: 3284,
    skipped_days: 1,
  },
  daily: {
    days: ["2026-09-18", "2026-09-19", "2026-09-20"],
    cumulative_perfect: [10, 20, 30],
    cumulative_model: [9, 18, 27],
    cumulative_naive: [8, 16, 24],
  },
};

const agent: AgentData = {
  model: "qwen2.5:7b",
  n: 28,
  pass_rate: 0.96,
  by_type: { factual: { n: 10, passed: 10, pass_rate: 1 } },
  grading: "programmatic",
  examples: [
    {
      type: "factual",
      question: "What was the mean price yesterday?",
      answer: "82.5 EUR/MWh",
      gold: "82.5",
      passed: true,
      tools_used: ["get_price_day"],
    },
  ],
};

const health: HealthData = {
  generated_at: "2026-09-20T11:51:52+00:00",
  series: {
    price_day_ahead: { status: "ok", age_hours: 1.9, rows: 50063 },
    gen_nuclear: {
      status: "discontinued",
      age_hours: 23137.9,
      rows: 540,
      note: "German nuclear phase-out",
    },
    gen_solar: { status: "stale", age_hours: 120.0, rows: 100 },
    forecast_wind_onshore: {
      status: "ok",
      label: "Forecast: wind onshore",
      age_hours: -21.2,
      rows: 50,
    },
    forecast_solar: { status: "missing" },
  },
  reports: {
    "forecast_eval.json": {
      label: "Forecast walk-forward eval",
      status: "overdue",
      cadence_days: 7,
      age_days: 21.4,
    },
    "battery_backtest.json": {
      label: "Battery backtest",
      status: "ok",
      cadence_days: 7,
      age_days: 3.1,
    },
    "agent_eval.json": { label: "Agent eval (local Ollama)", status: "manual", cadence_days: null },
  },
};

const pendingLedger: ForwardLedgerData = {
  generated_at: "2026-09-20T14:45:44+00:00",
  method: "One forecast per delivery day, recorded before the auction closes.",
  summary: {
    n_records: 1,
    n_scored: 0,
    n_pending: 1,
    first_target_date: "2026-09-21",
    last_target_date: "2026-09-21",
    feature_set: "pre_auction",
    cumulative: null,
    last_7_days: null,
  },
  days: [
    {
      target_date: "2026-09-21",
      generated_at_utc: "2026-09-20T09:23:00+00:00",
      scored: false,
      mae_model: null,
      mae_naive: null,
      mae_snaive7: null,
    },
  ],
  latest: {
    target_date: "2026-09-21",
    generated_at_utc: "2026-09-20T09:23:00+00:00",
    scored: false,
    hours_local: [0, 1, 2],
    pred_model: [100, 90, 80],
    pred_naive: [95, 85, 75],
    actual: null,
  },
};

const scoredLedger: ForwardLedgerData = {
  ...pendingLedger,
  summary: {
    ...pendingLedger.summary,
    n_records: 5,
    n_scored: 4,
    n_pending: 1,
    cumulative: {
      n_days: 4,
      n_hours: 96,
      mae_model: 12.34,
      mae_naive: 19.5,
      mae_snaive7: 24.1,
      skill_vs_naive_pct: 36.7,
      days_model_beat_naive: 3,
    },
    last_7_days: {
      n_days: 4,
      n_hours: 96,
      mae_model: 12.34,
      mae_naive: 19.5,
      mae_snaive7: 24.1,
      skill_vs_naive_pct: 36.7,
      days_model_beat_naive: 3,
    },
  },
  latest: { ...pendingLedger.latest!, scored: true, actual: [99, 91, 84] },
};

const uptime: UptimeData = {
  generated_at: "2026-09-20T14:52:34+00:00",
  source: "commit history",
  scheduled_runs_per_day: 10,
  reference_runs_per_day: 7,
  first_day: "2026-09-14",
  days: [
    { date: "2026-09-14", runs: 7 },
    { date: "2026-09-15", runs: 0 },
    { date: "2026-09-16", runs: 5 },
  ],
  totals: {
    days: 3,
    runs: 12,
    days_with_a_run: 2,
    days_with_zero_runs: 1,
    longest_silent_streak_days: 1,
    median_runs_per_active_day: 7,
  },
};

const ARTIFACTS = [
  "market.json",
  "forecast.json",
  "battery.json",
  "agent.json",
  "health.json",
  "forward_ledger.json",
  "uptime.json",
];

function setAll(state: "loading" | "missing") {
  for (const name of ARTIFACTS) artifacts.set(name, { state });
}

function setReady() {
  artifacts.set("market.json", { state: "ready", data: market });
  artifacts.set("forecast.json", { state: "ready", data: forecast });
  artifacts.set("battery.json", { state: "ready", data: battery });
  artifacts.set("agent.json", { state: "ready", data: agent });
  artifacts.set("health.json", { state: "ready", data: health });
  artifacts.set("forward_ledger.json", { state: "ready", data: scoredLedger });
  artifacts.set("uptime.json", { state: "ready", data: uptime });
}

beforeEach(() => artifacts.clear());
afterEach(cleanup);

describe("App states", () => {
  it("holds the body back until every artifact has settled", () => {
    // sections filling in one by one pushed each other down (CLS ~0.5)
    setAll("loading");
    artifacts.set("market.json", { state: "ready", data: market });
    render(<App />);
    expect(screen.getByText(/Loading pipeline artifacts/)).toBeTruthy();
    expect(screen.queryByText(/Generation mix/)).toBeNull();
    expect(screen.queryByText(/loading forecast evaluation/)).toBeNull();
  });

  it("falls back to a loading note per section when a request hangs", () => {
    vi.useFakeTimers();
    try {
      setAll("loading");
      render(<App />);
      act(() => vi.advanceTimersByTime(SETTLE_TIMEOUT_MS));
      expect(screen.queryByText(/Loading pipeline artifacts/)).toBeNull();
      expect(screen.getByText(/loading market data/)).toBeTruthy();
      expect(screen.getByText(/loading forecast evaluation/)).toBeTruthy();
      expect(screen.getByText(/loading battery backtest/)).toBeTruthy();
    } finally {
      vi.useRealTimers();
    }
  });

  it("degrades to a pending panel when an artifact was never produced", () => {
    setAll("missing");
    render(<App />);
    expect(screen.getByText(/market data not produced yet/)).toBeTruthy();
    expect(screen.getByText(/agent evaluation not produced yet/)).toBeTruthy();
    // no headline tiles without market/forecast/battery
    expect(screen.queryByText("Battery capture rate")).toBeNull();
  });

  it("renders every section once the artifacts are there", () => {
    setReady();
    render(<App />);
    expect(screen.getByText("Battery capture rate")).toBeTruthy();
    expect(screen.getByText("93.2")).toBeTruthy(); // capture rate tile
    expect(screen.getByText("+44.0")).toBeTruthy(); // forecast skill tile
    expect(screen.getByText(/Generation mix/)).toBeTruthy();
    expect(screen.getByText(forecast.eval.finding)).toBeTruthy();
    expect(screen.getByText(/Sample transcripts/)).toBeTruthy();
    expect(screen.queryByText(/not produced yet/)).toBeNull();
  });
});

describe("live forward test", () => {
  it("says there is no ledger instead of showing an empty one", () => {
    setAll("missing");
    render(<App />);
    expect(screen.getByText(/No forward ledger yet/)).toBeTruthy();
  });

  it("claims nothing while every entry is still pending", () => {
    setReady();
    artifacts.set("forward_ledger.json", { state: "ready", data: pendingLedger });
    render(<App />);
    expect(screen.getByText(/No scored day yet/)).toBeTruthy();
    expect(screen.getByText(/outcome still open/)).toBeTruthy();
    expect(screen.queryByText("MAE model (cumulative)")).toBeNull();
  });

  it("shows the track record once days are scored", () => {
    setReady();
    render(<App />);
    expect(screen.getByText("MAE model (cumulative)")).toBeTruthy();
    expect(screen.getByText("12.34")).toBeTruthy();
    expect(screen.getByText(/model beat naive on 3\/4 days/)).toBeTruthy();
    expect(screen.getByText(/cleared prices overlaid/)).toBeTruthy();
    expect(screen.queryByText(/No scored day yet/)).toBeNull();
  });
});

describe("segment analysis", () => {
  it("names the slices where the naive baseline still wins", () => {
    setReady();
    render(<App />);
    expect(screen.getByText(/Where the model wins — and where it does not/)).toBeTruthy();
    expect(screen.getByText(/A baseline still beats the model in: 20:00\./)).toBeTruthy();
    expect(screen.getByText("negative prices")).toBeTruthy();
  });

  it("does not claim a clean sweep it cannot back", () => {
    setReady();
    const clean = {
      ...forecast,
      segments: {
        ...forecast.segments,
        by_hour: [seg("00:00", 40.2), seg("20:00", 3.1)],
      },
    };
    artifacts.set("forecast.json", { state: "ready", data: clean });
    render(<App />);
    // the weakest slices come from the numbers, not from a hard-coded sentence
    expect(
      screen.getByText(/No slice where a baseline beats the model .* weakest are 20:00 \(3\.1%\) and Sun \(19\.1%\)\./),
    ).toBeTruthy();
  });
});

describe("battery sensitivity", () => {
  const cell = (eff: number, h: number, edge: number) => ({
    round_trip_efficiency: eff,
    duration_h: h,
    capacity_mwh: h,
    revenue_eur_per_mw_year: { perfect: 90000, model: 85000, naive: 85000 - edge },
    capture_rate_model: 0.944,
    capture_rate_naive: 0.9,
    model_edge_over_naive_eur_per_mw_year: edge,
  });
  const sweep = (edges: number[]) => ({
    generated_utc: "2026-09-28T02:30:00+00:00",
    power_mw: 1,
    n_days: 364,
    cells: [0.85, 0.9, 0.95].flatMap((e, i) => [cell(e, 2, edges[2 * i]), cell(e, 4, edges[2 * i + 1])]),
  });

  it("stays out of the page until the weekly sweep has run", () => {
    setReady();
    render(<App />);
    expect(screen.queryByText(/does the edge depend on the battery/)).toBeNull();
  });

  it("renders the six-cell grid and the range of the edge", () => {
    setReady();
    artifacts.set("battery.json", {
      state: "ready",
      data: { ...battery, sensitivity: sweep([4363, 8584, 4491, 8477, 4513, 8453]) },
    });
    const { container } = render(<App />);
    expect(screen.getByText(/beats naive in all 6 configurations, by 4,363–8,584 €\/MW\/yr/)).toBeTruthy();
    const panel = screen.getByText(/does the edge depend on the battery/).closest(".panel")!;
    expect(panel.querySelectorAll("tbody tr").length).toBe(6);
    expect(container.textContent).toContain("+8,584");
  });

  it("says so when the model loses to naive somewhere", () => {
    setReady();
    artifacts.set("battery.json", {
      state: "ready",
      data: { ...battery, sensitivity: sweep([-120, 800, 300, 900, 400, 1000]) },
    });
    render(<App />);
    expect(screen.getByText(/does not beat naive in every configuration \(edge -120 to 1,000/)).toBeTruthy();
  });
});

describe("market caption", () => {
  it("shows the rule-written summary of the last complete day", () => {
    setReady();
    render(<App />);
    expect(screen.getByText(/What happened on 2026-09-19/)).toBeTruthy();
    expect(screen.getByText(/Cheapest hour 13:00/)).toBeTruthy();
    expect(screen.getByText(/no model, nothing that can invent a driver/)).toBeTruthy();
  });

  it("says nothing at all when the day is not complete yet", () => {
    setReady();
    artifacts.set("market.json", { state: "ready", data: { ...market, explanation: null } });
    render(<App />);
    expect(screen.queryByText(/What happened on/)).toBeNull();
  });
});

describe("uptime calendar", () => {
  it("leads with the streak and names the silent days instead of hiding them", () => {
    setReady();
    const { container } = render(<App />);
    expect(screen.getByText(/3 days live · 12 published refreshes/)).toBeTruthy();
    expect(screen.getByText(/1 silent days \(longest streak 1\)/)).toBeTruthy();
    const cells = container.querySelectorAll("svg.heatmap rect");
    expect(cells.length).toBe(3);
    // the silent day renders as an empty cell, not as a faint green one
    expect(Array.from(cells).map((c) => c.getAttribute("fill"))).toContain(
      "var(--grid-hairline)",
    );
  });

  it("degrades to a pending panel before the first export", () => {
    setAll("missing");
    render(<App />);
    expect(screen.getByText(/uptime calendar not produced yet/)).toBeTruthy();
  });
});

describe("health panel", () => {
  it("shows human labels and never a negative age for forecast series", () => {
    setReady();
    const { container } = render(<App />);
    const rows = Array.from(container.querySelectorAll(".health-item")) as HTMLElement[];
    const wind = rows.find((r) => within(r).queryByText("Forecast: wind onshore"))!;
    expect(within(wind).getByText("reaches +21 h")).toBeTruthy();
    expect(container.textContent).not.toContain("-21.2h");
  });

  it("never paints a discontinued series as a fault", () => {
    setReady();
    const { container } = render(<App />);
    const rows = Array.from(container.querySelectorAll(".health-item")) as HTMLElement[];
    const byName = (name: string) => rows.find((r) => within(r).queryByText(name))!;

    const nuclear = byName("gen_nuclear");
    expect(within(nuclear).getByText("retired")).toBeTruthy();
    expect(nuclear.querySelector(".dot")!.getAttribute("style")).toContain("--ink-muted");
    expect(nuclear.getAttribute("title")).toContain("phase-out");

    // a series that is supposed to update still alarms
    expect(byName("gen_solar").querySelector(".dot")!.getAttribute("style")).toContain("--warning");
    expect(byName("price_day_ahead").querySelector(".dot")!.getAttribute("style")).toContain(
      "--good",
    );
    expect(byName("forecast_solar").querySelector(".dot")!.getAttribute("style")).toContain(
      "--critical",
    );
  });
});

describe("derived report freshness", () => {
  it("alarms on a missed weekly cadence but never on the manual eval", () => {
    setReady();
    const { container } = render(<App />);
    const rows = Array.from(container.querySelectorAll(".health-item")) as HTMLElement[];
    const byLabel = (label: string) => rows.find((r) => within(r).queryByText(label))!;

    const forecastRow = byLabel("Forecast walk-forward eval");
    expect(forecastRow.querySelector(".dot")!.getAttribute("style")).toContain("--critical");
    expect(within(forecastRow).getByText("21d")).toBeTruthy();
    expect(byLabel("Battery backtest").querySelector(".dot")!.getAttribute("style")).toContain(
      "--good",
    );
    const agentRow = byLabel("Agent eval (local Ollama)");
    expect(agentRow.querySelector(".dot")!.getAttribute("style")).toContain("--ink-muted");
    expect(within(agentRow).getByText("manual")).toBeTruthy();
  });

  it("omits the report block entirely on an artifact that predates it", () => {
    setReady();
    artifacts.set("health.json", { state: "ready", data: { ...health, reports: undefined } });
    const { container } = render(<App />);
    expect(container.textContent).not.toContain("Derived reports");
    expect(container.querySelectorAll(".health-item").length).toBe(5);
  });
});

describe("sumMembers", () => {
  it("adds the members of a generation group hour by hour", () => {
    expect(sumMembers({ a: [1, 2], b: [10, 20] }, ["a", "b"])).toEqual([11, 22]);
  });

  it("ignores members the export did not ship", () => {
    expect(sumMembers({ a: [1, 2] }, ["a", "missing"])).toEqual([1, 2]);
    expect(sumMembers({ a: [1, 2] }, ["missing"])).toEqual([]);
  });

  it("keeps a null hour null only when every member is null", () => {
    expect(sumMembers({ a: [null, 2], b: [null, null] }, ["a", "b"])).toEqual([null, 2]);
  });
});
