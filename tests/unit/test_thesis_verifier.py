"""Tests for PM thesis quality guardrails."""

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
