import pytest
import tempfile
from datetime import date, datetime
from unittest.mock import patch

from src.backtest.engine.backtest_runner import BacktestRunner
from src.core.models.config import (
    PodConfig,
    RiskBudget,
    ExecutionConfig,
    BacktestConfig,
)
from src.core.models.enums import TimeHorizon, AgentType
from src.core.models.market import Bar


def make_alpha_config():
    return PodConfig(
        pod_id="alpha",
        name="Pod Alpha",
        strategy_family="momentum",
        universe=["AAPL", "MSFT"],
        time_horizon=TimeHorizon.SWING,
        risk_budget=RiskBudget(
            target_vol=0.12,
            max_leverage=1.5,
            max_drawdown=0.10,
            max_concentration=0.05,
            max_sector_exposure=0.30,
            liquidity_min_adv_pct=0.01,
            var_limit_95=0.02,
            es_limit_95=0.03,
        ),
        execution=ExecutionConfig(
            style="passive",
            max_participation_rate=0.10,
            allowed_venues=["paper"],
            order_types=["market"],
        ),
        backtest=BacktestConfig(
            start_date=date(2024, 1, 2),
            end_date=date(2024, 1, 31),
            min_history_days=10,
            walk_forward_folds=1,
            latency_ms=0,
            tcm_bps=5.0,
            slippage_model="fixed",
        ),
        pm_agent_type=AgentType.RULE_BASED,
    )


def _fake_bars(symbol, start, end):
    """Generate deterministic synthetic bars for backtest period."""
    bars = []
    current = datetime.combine(start, datetime.min.time())
    end_dt = datetime.combine(end, datetime.min.time())
    price = 180.0 if symbol == "AAPL" else 350.0
    day = 0
    while current < end_dt:
        if current.weekday() < 5:  # weekdays only
            p = price + day * 0.5
            bars.append(Bar(
                symbol=symbol, timestamp=current,
                open=p, high=p + 2, low=p - 1, close=p + 1,
                volume=1_000_000, source="test",
            ))
            day += 1
        current += __import__("datetime").timedelta(days=1)
    return bars


@pytest.mark.asyncio
async def test_backtest_runs_without_error():
    cache_dir = tempfile.mkdtemp()
    runner = BacktestRunner(cache_dir=cache_dir)
    with patch(
        "src.data.adapters.yfinance_adapter.YFinanceAdapter._fetch_sync",
        side_effect=lambda sym, s, e: _fake_bars(sym, s, e),
    ):
        result = await runner.run(make_alpha_config())
    assert result is not None
    assert "nav_final" in result
    assert "total_bars_processed" in result
    assert result["total_bars_processed"] > 0


@pytest.mark.asyncio
async def test_backtest_is_deterministic():
    cache_dir = tempfile.mkdtemp()
    config = make_alpha_config()
    with patch(
        "src.data.adapters.yfinance_adapter.YFinanceAdapter._fetch_sync",
        side_effect=lambda sym, s, e: _fake_bars(sym, s, e),
    ):
        r1 = await BacktestRunner(cache_dir=cache_dir).run(config)
        r2 = await BacktestRunner(cache_dir=cache_dir).run(config)
    assert abs(r1["nav_final"] - r2["nav_final"]) < 0.01
