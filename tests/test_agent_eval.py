import httpx
import pytest

from gridscout.agent.evaluation import extract_numbers, numeric_match, refusal_like
from gridscout.agent.loop import GridAgent
from gridscout.agent.tools import GridTools


class TestGrading:
    def test_extract_numbers_handles_formats(self):
        text = "The mean was 96.8 EUR/MWh, peaking at 1,024.5 (hour 18), low -12.3."
        assert extract_numbers(text) == [96.8, 1024.5, 18, -12.3]

    @pytest.mark.parametrize(
        ("answer", "gold", "expected"),
        [
            ("about 96.8 EUR/MWh on average", 96.8, True),
            ("roughly 97 EUR/MWh", 96.8, True),  # within abs tolerance 0.51? no -> rel 2%
            ("it was 120 EUR/MWh", 96.8, False),
            ("no idea", 96.8, False),
        ],
    )
    def test_numeric_match(self, answer, gold, expected):
        assert numeric_match(answer, gold) is expected

    def test_refusal_detection(self):
        assert refusal_like("I cannot answer that — my data only covers Germany.")
        assert refusal_like("There is no data for that date.")
        assert not refusal_like("The price was 96.8 EUR/MWh.")

    @pytest.mark.parametrize(
        "answer",
        [
            # real agent phrasings from the first eval run that the initial
            # marker list missed (grader gap found via error analysis)
            "There is no tool available to query French day-ahead power prices.",
            "The tools provided do not include information about Dutch TTF gas prices.",
            "None of the provided tools can answer for a specific time within an hour.",
            "The provided tools do not cover EU ETS carbon certificate prices.",
        ],
    )
    def test_refusal_detection_real_agent_phrasings(self, answer):
        assert refusal_like(answer)


class FakeOllama:
    """Scripted /api/chat responses: first a tool call, then a final answer."""

    def __init__(self):
        self.requests: list[dict] = []

    def handler(self, request: httpx.Request) -> httpx.Response:
        body = request.read().decode()
        import json

        payload = json.loads(body)
        self.requests.append(payload)
        tool_results = [m for m in payload["messages"] if m["role"] == "tool"]
        if not tool_results:
            message = {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {"function": {"name": "get_price_day", "arguments": {"day": "2024-03-02"}}}
                ],
            }
        else:
            message = {"role": "assistant", "content": "The mean was 42.0 EUR/MWh."}
        return httpx.Response(200, json={"message": message})


@pytest.fixture
def agent(tmp_path):
    fake = FakeOllama()
    agent = GridAgent(
        tools=GridTools(data_dir=tmp_path, reports_dir=tmp_path), model="fake"
    )
    agent._http = httpx.Client(
        base_url="http://fake", transport=httpx.MockTransport(fake.handler)
    )
    agent._fake = fake
    return agent


def test_agent_round_trip_records_tool_calls(agent):
    result = agent.ask("What was the mean price on 2024-03-02?")
    assert result.answer == "The mean was 42.0 EUR/MWh."
    assert result.rounds == 2
    assert result.tool_calls[0]["tool"] == "get_price_day"
    # empty tmp data dir -> the tool reports an error payload, not an exception
    assert "error" in result.tool_calls[0]["result"]


def test_agent_rejects_unknown_tool(agent):
    payload = agent._dispatch("rm_rf_everything", {})
    assert "unknown tool" in payload["error"]


def test_a_timeout_costs_one_question_not_the_run(tmp_path):
    def slow(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("timed out", request=request)

    agent = GridAgent(tools=GridTools(data_dir=tmp_path, reports_dir=tmp_path), model="fake")
    agent._http = httpx.Client(base_url="http://fake", transport=httpx.MockTransport(slow))
    result = agent.ask("anything")
    assert result.answer == ""
    assert "ReadTimeout" in result.error


def test_agent_survives_bad_arguments(agent):
    payload = agent._dispatch("get_price_day", {"nonsense": True})
    assert "bad arguments" in payload["error"]


class TestEvalSetDaySelection:
    def test_sparse_data_raises(self, tmp_path):
        import numpy as np

        from gridscout.agent.evaluation import build_eval_set
        from tests.test_export import write_series

        data = tmp_path / "d"
        # only 4 days of data -> offsets 7/30/90 cannot find usable days
        write_series(data, "price_day_ahead", np.ones(96), start_ms=1709247600000)
        for name in ["load", "gen_solar", "gen_wind_onshore", "gen_wind_offshore"]:
            write_series(data, name, np.ones(96), start_ms=1709247600000)
        with pytest.raises(RuntimeError, match="usable eval days"):
            build_eval_set(GridTools(data_dir=data, reports_dir=tmp_path))

    def test_walks_past_holes(self, tmp_path):
        from datetime import date

        import numpy as np

        from gridscout.agent.evaluation import _usable_day
        from gridscout.agent.tools import GridTools as GT
        from tests.test_export import write_series

        data = tmp_path / "d"
        values = np.ones(96 * 2)
        values[96:144] = np.nan  # Mar 5-6 hole in prices
        write_series(data, "price_day_ahead", values, start_ms=1709247600000)
        for name in ["load", "gen_solar", "gen_wind_onshore", "gen_wind_offshore"]:
            write_series(data, name, np.ones(96 * 2), start_ms=1709247600000)
        tools = GT(data_dir=data, reports_dir=tmp_path)
        assert not _usable_day(tools, date(2024, 3, 5))
        assert _usable_day(tools, date(2024, 3, 4))


class TestHoldoutSet:
    @pytest.fixture
    def long_tools(self, tmp_path):
        import numpy as np

        from tests.test_export import write_series

        data = tmp_path / "d"
        n = 24 * 300
        rng = np.random.default_rng(3)
        write_series(data, "price_day_ahead", rng.normal(90, 30, n), start_ms=1704063600000)
        for name in ["load", "gen_solar", "gen_wind_onshore", "gen_wind_offshore", "gen_gas"]:
            write_series(data, name, rng.uniform(100, 20_000, n), start_ms=1704063600000)
        tools = GridTools(data_dir=data, reports_dir=tmp_path)
        models = {"lgbm_point": {"mae": 10.0, "rmse": 14.0}, "naive_yesterday": {"mae": 20.0},
                  "seasonal_naive_7d": {"mae": 25.0}}
        skill = {"lgbm_vs_naive_pct": 50}
        tools.get_forecast_evaluation = lambda: {"models": models, "skill": skill}
        tools.get_battery_results = lambda: {
            "capture_rate_model": 0.9, "model_edge_over_naive_eur": 1.0,
            "revenue_eur": {"perfect": 3.0, "naive": 2.0, "model": 2.5},
        }
        return tools

    def test_holdout_is_disjoint_from_the_tuning_set(self, long_tools):
        import re

        from gridscout.agent.evaluation import build_eval_set, build_holdout_set

        day_re = re.compile(r"\d{4}-\d{2}-\d{2}")
        dev = build_eval_set(long_tools)
        hold = build_holdout_set(long_tools)
        dev_days = {d for q in dev for d in day_re.findall(q.text)}
        hold_days = {d for q in hold for d in day_re.findall(q.text)}
        assert hold_days
        assert not dev_days & hold_days
        assert not {q.text for q in dev} & {q.text for q in hold}
        assert {q.type for q in hold} == {"factual", "analytical", "report", "trap"}

    def test_holdout_gold_answers_pass_their_own_grader(self, long_tools):
        from gridscout.agent.evaluation import build_holdout_set

        for q in build_holdout_set(long_tools):
            if q.type != "trap":
                assert q.grade(q.gold_display), q.id
