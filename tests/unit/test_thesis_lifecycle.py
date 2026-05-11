from types import SimpleNamespace

import pytest

from src.core.thesis_lifecycle import (
    expansion_thesis_is_fresh,
    review_position_thesis,
)


def _position(**kwargs):
    base = {
        "symbol": "GLD",
        "qty": 1.0,
        "cost_basis": 100.0,
        "current_price": 99.0,
        "entry_date": "2026-05-01",
        "stop_loss_pct": 0.05,
        "max_hold_days": 0,
    }
    base.update(kwargs)
    return SimpleNamespace(**base)


def test_precious_metals_regression_breaks_when_negative_real_rate_claim_is_now_positive():
    review = review_position_thesis(
        symbol="GLD",
        entry_thesis=(
            "THESIS: Buy gold because inflation is elevated and negative real rates "
            "are still in play. RISK: USD squeeze."
        ),
        entry_metadata={"entry_macro_regime": "neutral"},
        position=_position(),
        features={
            "regime": {"regime": "neutral"},
            "fred_indicators": {"DFII10": 1.96, "T10YIE": 2.46},
        },
        pod_id="commodities",
    )

    assert review["status"] in {"challenged", "broken"}
    assert review["block_adds"] is True
    assert any("negative real rates" in issue for issue in review["issues"])


@pytest.mark.parametrize(
    ("pod_id", "symbol", "thesis", "expected_monitor"),
    [
        (
            "equities",
            "AAPL",
            (
                "THESIS: earnings and revenue acceleration can support a valuation rerating. "
                "ENTRY: add after breakout. INVALIDATION: sector breadth weakens. RISK: rates."
            ),
            "earnings_fundamentals",
        ),
        (
            "fx",
            "FXE",
            (
                "THESIS: ECB/Fed rate differential and central-bank policy gap favor EUR exposure. "
                "ENTRY: buy on confirmation. INVALIDATION: dollar squeeze. RISK: risk-off."
            ),
            "rate_differential",
        ),
        (
            "crypto",
            "BTC",
            (
                "THESIS: global liquidity and stablecoin flows are improving while real yields stabilize. "
                "ENTRY: add on confirmed risk-on breakout. INVALIDATION: regulation shock. RISK: volatility."
            ),
            "liquidity",
        ),
        (
            "commodities",
            "USO",
            (
                "THESIS: crude oil supply/demand is tightening as inventories draw and OPEC discipline holds. "
                "ENTRY: buy breakout. INVALIDATION: inventories rebuild. RISK: dollar strength."
            ),
            "energy_supply_demand",
        ),
    ],
)
def test_lifecycle_has_asset_specific_monitors_for_each_active_pod(
    pod_id,
    symbol,
    thesis,
    expected_monitor,
):
    review = review_position_thesis(
        symbol=symbol,
        entry_thesis=thesis,
        entry_metadata={"entry_macro_regime": "neutral"},
        position=_position(symbol=symbol, current_price=101.0),
        features={"regime": {"regime": "neutral"}, "fred_indicators": {"DFII10": 1.5}},
        pod_id=pod_id,
    )

    assert expected_monitor in review["monitors"]
    assert review["asset_class"] == pod_id
    assert review["status"] in {"valid", "watch"}


def test_fx_thesis_missing_rate_and_policy_context_moves_to_watch():
    review = review_position_thesis(
        symbol="FXE",
        entry_thesis="THESIS: the chart looks constructive. ENTRY: buy. INVALIDATION: price falls. RISK: volatility.",
        entry_metadata={"entry_macro_regime": "neutral"},
        position=_position(symbol="FXE", current_price=101.0),
        features={"regime": {"regime": "neutral"}},
        pod_id="fx",
    )

    assert review["status"] == "watch"
    assert any("FX thesis" in issue for issue in review["issues"])
    assert "rate_differential" in review["monitors"]


def test_crypto_thesis_missing_liquidity_and_flow_context_moves_to_watch():
    review = review_position_thesis(
        symbol="BTC",
        entry_thesis="THESIS: momentum looks better. ENTRY: buy. INVALIDATION: price fails. RISK: volatility.",
        entry_metadata={"entry_macro_regime": "neutral"},
        position=_position(symbol="BTC", current_price=101.0),
        features={"regime": {"regime": "neutral"}},
        pod_id="crypto",
    )

    assert review["status"] == "watch"
    assert any("Crypto thesis" in issue for issue in review["issues"])
    assert "liquidity" in review["monitors"]


def test_oil_thesis_uses_energy_monitors_not_gold_monitors():
    review = review_position_thesis(
        symbol="USO",
        entry_thesis=(
            "THESIS: crude oil supply/demand is tightening as inventories draw. "
            "ENTRY: buy support. INVALIDATION: EIA inventories rebuild. RISK: USD strength."
        ),
        entry_metadata={"entry_macro_regime": "neutral"},
        position=_position(symbol="USO", current_price=101.0),
        features={"regime": {"regime": "neutral"}, "fred_indicators": {"DFII10": 1.5}},
        pod_id="commodities",
    )

    assert review["asset_theme"] == "energy"
    assert "energy_supply_demand" in review["monitors"]
    assert "real_yields" not in review["monitors"]
    assert not any("Precious-metals" in issue for issue in review["issues"])


def test_regime_change_moves_thesis_to_watch():
    review = review_position_thesis(
        symbol="SPY",
        entry_thesis="THESIS: Risk-on breadth recovery. ENTRY: breakout. INVALIDATION: breadth fails. RISK: recession.",
        entry_metadata={"entry_macro_regime": "risk-on"},
        position=_position(symbol="SPY", current_price=101.0),
        features={"regime": {"regime": "risk_off"}},
        pod_id="equities",
    )

    assert review["status"] in {"watch", "challenged"}
    assert "macro_regime" in review["monitors"]


def test_expansion_requires_fresh_add_reasoning():
    ok, reason = expansion_thesis_is_fresh(
        "THESIS: still bullish. RISK: rates.",
        {"status": "valid", "block_adds": False},
    )

    assert ok is False
    assert "Expansion/add" in reason


def test_challenged_position_requires_revalidation_for_add():
    ok, reason = expansion_thesis_is_fresh(
        (
            "THESIS: expansion add after updated regime data. ENTRY: add on confirmed breakout. "
            "INVALIDATION: exit if real yields rise. RISK: USD squeeze. New catalyst confirms the thesis still valid."
        ),
        {"status": "challenged", "block_adds": True},
    )

    assert ok is True
