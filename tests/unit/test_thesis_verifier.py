"""Tests for PM thesis quality guardrails."""

import pytest

from src.agents.thesis_verifier import ThesisVerifier


def test_verifier_flags_gold_negative_real_rate_claim():
    decision = {
        "trades": [
            {
                "action": "BUY",
                "symbol": "GLD",
                "qty": 1,
                "conviction": 0.8,
                "reasoning": (
                    "THESIS: Buy gold because inflation is high and negative real rates are still in play. "
                    "RISK: dollar rally."
                ),
            }
        ],
        "reasoning": "",
    }

    result = ThesisVerifier().verify(decision, "commodities")

    assert not result.passed
    assert "negative real rates" in result.feedback


def test_verifier_accepts_tradeable_gold_thesis_shape():
    decision = {
        "trades": [
            {
                "action": "BUY",
                "symbol": "GLD",
                "qty": 1,
                "conviction": 0.8,
                "reasoning": (
                    "THESIS: GLD can work if sticky inflation and geopolitical energy risk keep safe-haven "
                    "demand firm while real yields stabilize. DRIVERS: breakeven inflation is elevated, "
                    "TIPS real yields are positive but no longer rising, the Fed reaction function is the "
                    "main offset, and USD/DXY strength is the key headwind. CATALYST: unresolved Hormuz risk "
                    "can lift oil and inflation expectations. ENTRY: buy only after GLD holds support and "
                    "outperforms despite a firm dollar. INVALIDATION: exit if real yields rise, USD breaks "
                    "higher, or de-escalation drives oil lower. RISK: size is limited because positive real "
                    "yields can pressure non-income gold. INSTRUMENT FIT: GLD is liquid bullion exposure."
                ),
            }
        ],
        "reasoning": "",
    }

    result = ThesisVerifier().verify(decision, "commodities")

    assert result.passed


@pytest.mark.parametrize(
    ("asset_class", "symbol", "reasoning"),
    [
        (
            "equities",
            "AAPL",
            (
                "THESIS: AAPL can rerate as earnings and revenue growth improve. DRIVERS: valuation "
                "is no longer stretched versus sector peers, sector breadth is improving, and rates are "
                "stable. CATALYST: guidance revision. ENTRY: buy on breakout. INVALIDATION: earnings "
                "miss or breadth rolls over. RISK: higher yields. INSTRUMENT FIT: AAPL gives direct equity exposure."
            ),
        ),
        (
            "fx",
            "FXE",
            (
                "THESIS: EUR exposure can work as the ECB/Fed rate differential narrows. DRIVERS: central-bank "
                "policy divergence, inflation/growth data, USD/DXY trend, and risk sentiment. CATALYST: next "
                "policy meeting. ENTRY: buy confirmation. INVALIDATION: dollar squeeze. RISK: risk-off shock. "
                "INSTRUMENT FIT: FXE provides liquid EUR/USD exposure."
            ),
        ),
        (
            "crypto",
            "BTC",
            (
                "THESIS: BTC can benefit if liquidity improves and real yields stop rising. DRIVERS: stablecoin "
                "flows, ETF flow demand, risk-on sentiment, regulation path, and on-chain volume. CATALYST: "
                "liquidity impulse. ENTRY: buy breakout. INVALIDATION: regulatory shock. RISK: high volatility. "
                "INSTRUMENT FIT: BTC is the most liquid crypto beta."
            ),
        ),
        (
            "commodities",
            "USO",
            (
                "THESIS: USO can rise if oil supply/demand tightens. DRIVERS: inventory draws, OPEC discipline, "
                "geopolitical shipping risk, USD trend, and growth demand. CATALYST: EIA inventory report. "
                "ENTRY: buy breakout. INVALIDATION: inventories rebuild. RISK: stronger dollar. "
                "INSTRUMENT FIT: USO is liquid crude exposure."
            ),
        ),
    ],
)
def test_verifier_accepts_tradeable_thesis_for_each_pod(asset_class, symbol, reasoning):
    decision = {
        "trades": [{"action": "BUY", "symbol": symbol, "qty": 1, "conviction": 0.75, "reasoning": reasoning}],
        "reasoning": "",
    }

    result = ThesisVerifier().verify(decision, asset_class)

    assert result.passed, result.feedback


def test_verifier_rejects_fx_trade_without_fx_specific_drivers():
    decision = {
        "trades": [
            {
                "action": "BUY",
                "symbol": "FXE",
                "qty": 1,
                "conviction": 0.75,
                "reasoning": (
                    "THESIS: FXE looks strong on the chart. ENTRY: buy now. "
                    "INVALIDATION: price falls. RISK: volatility."
                ),
            }
        ],
        "reasoning": "",
    }

    result = ThesisVerifier().verify(decision, "fx")

    assert not result.passed
    assert "FX thesis" in result.feedback
