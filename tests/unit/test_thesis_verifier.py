"""Tests for PM thesis quality guardrails."""

import pytest

from src.agents.thesis_verifier import ThesisVerifier
from src.core.thesis_quality import tradeable_entry_thesis_instruction


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
                    "FACTS: prompt data shows elevated breakeven inflation, positive TIPS real yields, "
                    "and a firm USD/DXY. ASSUMPTIONS: geopolitical risk must persist without a hawkish "
                    "real-yield shock. THESIS: GLD can work if sticky inflation and geopolitical energy "
                    "risk keep safe-haven demand firm while real yields stabilize. DRIVERS: breakevens, "
                    "Fed reaction function, USD trend, positioning/ETF flows, and central-bank reserve "
                    "demand matter. VALUATION/EVIDENCE: no cheap claim is made; evidence is macro and "
                    "flow-based. CATALYST: unresolved Hormuz risk can lift oil and inflation expectations. "
                    "WHY NOW: buy only if GLD holds support and outperforms despite a firm dollar. ENTRY: "
                    "buy on support hold. TIMEFRAME: thesis-driven swing with stop and TP sized for gold ETF "
                    "volatility. INVALIDATION: exit if real yields rise, USD breaks higher, or de-escalation "
                    "drives oil lower. RISK: positive real yields can pressure non-income gold. "
                    "INSTRUMENT FIT: GLD is liquid bullion exposure."
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
                "FACTS: current price and sector breadth come from the prompt. ASSUMPTIONS: earnings "
                "revision momentum persists. THESIS: AAPL can rerate as earnings and revenue growth improve. "
                "DRIVERS: valuation, earnings, revenue, sector breadth, and rates are stable enough to help. "
                "VALUATION/EVIDENCE: multiple and earnings setup are no longer stretched versus sector peers. "
                "CATALYST: guidance revision. WHY NOW: breakout would force near-term repricing. ENTRY: buy "
                "on breakout. TIMEFRAME: medium-term earnings/guidance window. INVALIDATION: earnings miss "
                "or breadth rolls over. RISK: higher yields. INSTRUMENT FIT: AAPL gives direct equity exposure."
            ),
        ),
        (
            "fx",
            "FXE",
            (
                "FACTS: prompt data shows current FXE price, USD/DXY context, and central-bank calendar risk. "
                "ASSUMPTIONS: policy expectations continue to move toward a narrower rate differential. "
                "THESIS: EUR exposure can work as the ECB/Fed rate differential narrows. DRIVERS: central-bank "
                "policy divergence, inflation/growth data, USD/DXY trend, carry, and risk sentiment. "
                "VALUATION/EVIDENCE: rate differential and carry are the relative-value evidence. "
                "CATALYST: next policy meeting. WHY NOW: confirmation before the policy window can reprice EUR. "
                "ENTRY: buy confirmation. TIMEFRAME: policy-meeting swing. INVALIDATION: dollar squeeze. "
                "RISK: risk-off shock. INSTRUMENT FIT: FXE provides liquid EUR/USD exposure."
            ),
        ),
        (
            "crypto",
            "BTC",
            (
                "FACTS: current price, BTC relative strength, stablecoin flows, ETF flows, and on-chain volume "
                "come from the prompt. ASSUMPTIONS: liquidity improves and real yields stop rising. THESIS: "
                "BTC can benefit if liquidity improves and real yields stop rising. DRIVERS: stablecoin flows, "
                "ETF flow demand, risk-on sentiment, regulation path, rates, and on-chain volume. "
                "VALUATION/EVIDENCE: no undervaluation claim; evidence is flow, volume, funding, and open "
                "interest. CATALYST: liquidity impulse. WHY NOW: breakout would show fresh demand. ENTRY: buy "
                "breakout. TIMEFRAME: short-to-medium swing. INVALIDATION: regulatory shock. RISK: high "
                "volatility. INSTRUMENT FIT: BTC is the most liquid crypto beta."
            ),
        ),
        (
            "commodities",
            "USO",
            (
                "FACTS: prompt data shows current USO price, inventory trend, USD context, and oil headlines. "
                "ASSUMPTIONS: OPEC discipline persists and demand does not weaken. THESIS: USO can rise if "
                "oil supply/demand tightens. DRIVERS: inventory draws, supply/demand, OPEC discipline, "
                "geopolitical shipping risk, USD trend, and growth demand. VALUATION/EVIDENCE: inventory and "
                "curve/supply-demand data are the commodity evidence. CATALYST: EIA inventory report. WHY NOW: "
                "fresh inventory draw can reprice prompt crude exposure. ENTRY: buy breakout. TIMEFRAME: "
                "inventory-report swing. INVALIDATION: inventories rebuild. RISK: stronger dollar. "
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


def test_verifier_rejects_sol_thesis_with_unsupported_valuation_fee_and_event_claims():
    decision = {
        "trades": [
            {
                "action": "BUY",
                "symbol": "SOL/USD",
                "qty": 1,
                "conviction": 0.8,
                "reasoning": (
                    "THESIS: SOL is undervalued versus ETH because ETH rallied more, and SOL will benefit "
                    "as high Ethereum gas fees push users toward Solana. CATALYST: the June DeFi summit. "
                    "ENTRY: buy now. INVALIDATION: price falls. RISK: crypto volatility."
                ),
            }
        ],
        "reasoning": "",
    }

    result = ThesisVerifier().verify(decision, "crypto")

    assert not result.passed
    assert "valuation/relative-value claim is unsupported" in result.feedback
    assert "Ethereum gas-fee migration claim" in result.feedback
    assert "event catalyst is speculative" in result.feedback


def test_verifier_accepts_cautious_evidence_backed_sol_thesis():
    decision = {
        "trades": [
            {
                "action": "BUY",
                "symbol": "SOL/USD",
                "qty": 1,
                "conviction": 0.78,
                "reasoning": (
                    "FACTS: SOL current price is in the prompt, ETH has led the latest crypto move, Solana "
                    "TVL, DEX volume, stablecoin supply, active users, funding, and open interest are the "
                    "metrics to verify before calling it cheap. ASSUMPTIONS: altcoin momentum broadens and "
                    "Solana on-chain activity keeps strengthening. THESIS: SOL could benefit if ETH-led "
                    "altcoin momentum broadens and Solana network activity confirms improving demand. "
                    "DRIVERS: liquidity, real yields, risk sentiment, TVL, fees/revenue, DEX volume, stablecoin "
                    "supply, active addresses, and funding rates. VALUATION/EVIDENCE: relative-value evidence "
                    "must be market cap/TVL, FDV/TVL, fees, revenue, and relative performance versus BTC/ETH "
                    "over 1w, 1m, and 3m, not only ETH outperforming for a few days. CATALYST: the DeFi summit "
                    "is narrative support unless confirmed announcements appear. WHY NOW: buy only on a "
                    "confirmed breakout or relative-strength turn while funding remains uncrowded. ENTRY: buy "
                    "breakout. TIMEFRAME: short-term momentum trade, not a long-term ecosystem thesis. "
                    "INVALIDATION: exit if ETH leadership narrows without SOL follow-through, gas-fee data is "
                    "low, funding turns crowded, or TVL/DEX volume weakens. RISK: crypto beta and event risk. "
                    "INSTRUMENT FIT: SOL/USD is direct liquid exposure."
                ),
            }
        ],
        "reasoning": "",
    }

    result = ThesisVerifier().verify(decision, "crypto")

    assert result.passed, result.feedback


def test_crypto_thesis_instruction_requires_evidence_and_assumptions():
    instruction = tradeable_entry_thesis_instruction("crypto")

    assert "FACTS" in instruction
    assert "ASSUMPTIONS" in instruction
    assert "WHY NOW" in instruction
    assert "market cap/TVL" in instruction
    assert "funding rates" in instruction
    assert "search_queries" in instruction
