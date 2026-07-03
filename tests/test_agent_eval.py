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


def test_agent_survives_bad_arguments(agent):
    payload = agent._dispatch("get_price_day", {"nonsense": True})
    assert "bad arguments" in payload["error"]
