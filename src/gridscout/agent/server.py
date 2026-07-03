"""MCP server exposing grid-scout's data tools.

Any MCP client (Claude Desktop, an IDE, another agent) gets the same
deterministic tools the local eval agent uses:

    uv run gridscout-mcp        # stdio transport
"""

from pathlib import Path

from mcp.server.fastmcp import FastMCP

from gridscout.agent.tools import GridTools, ToolError

mcp = FastMCP(
    "grid-scout",
    instructions=(
        "Tools over the German electricity market (SMARD data): day-ahead prices, "
        "generation mix, an honestly-evaluated price forecast and a battery arbitrage "
        "backtest. Ground every numeric claim in tool output."
    ),
)
_tools = GridTools(data_dir=Path("data"), reports_dir=Path("reports"))


def _wrap(fn, *args):
    try:
        return fn(*args)
    except ToolError as exc:
        return {"error": str(exc)}


@mcp.tool()
def get_price_day(day: str) -> dict:
    """Hourly German day-ahead electricity prices for one day (EUR/MWh)."""
    return _wrap(_tools.get_price_day, day)


@mcp.tool()
def get_price_range_summary(start_day: str, end_day: str) -> dict:
    """Price statistics (mean/min/max/negative hours) over a day range."""
    return _wrap(_tools.get_price_range_summary, start_day, end_day)


@mcp.tool()
def get_generation_mix_day(day: str) -> dict:
    """Generation per source for one day (MWh) and the renewables share."""
    return _wrap(_tools.get_generation_mix_day, day)


@mcp.tool()
def explain_price_context(day: str) -> dict:
    """Why prices were high or low on a day (residual load vs price)."""
    return _wrap(_tools.explain_price_context, day)


@mcp.tool()
def get_forecast_evaluation() -> dict:
    """Out-of-sample eval of the price forecast vs naive baselines."""
    return _wrap(_tools.get_forecast_evaluation)


@mcp.tool()
def get_battery_results() -> dict:
    """Battery arbitrage backtest results."""
    return _wrap(_tools.get_battery_results)


@mcp.tool()
def get_data_coverage() -> dict:
    """Available data series and their date coverage."""
    return _wrap(_tools.get_data_coverage)


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
