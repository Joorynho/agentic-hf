from src.core.factor_exposure import (
    classify_symbol,
    compute_factor_report,
    validate_dynamic_profile,
)


def test_gold_and_gold_miners_share_gold_beta():
    gld = classify_symbol("GLD")
    gdx = classify_symbol("GDX")

    assert gld.exposures["gold_beta"] == 1.0
    assert gdx.exposures["gold_beta"] > 0.75
    assert gdx.exposures["precious_metals"] > 0.75


def test_gold_miner_stack_breaches_shared_factor_limit():
    positions = {
        "GLD": {"qty": 3, "current_price": 100},
        "GDXJ": {"qty": 3, "current_price": 100},
    }

    report = compute_factor_report(positions, nav=1000.0, cash=400.0)

    assert report["factors"]["gold_beta"]["pct_nav"] > 0.50
    assert report["factors"]["gold_beta"]["breach"] is True
    assert any("gold_beta" in b for b in report["breaches"])


def test_dynamic_llm_factor_profile_is_validated_to_known_factors():
    raw = {
        "symbol": "OILX",
        "primary_factor": "crude oil",
        "exposures": {"crude": 1.0, "energy": 0.5, "mystery": 0.9},
        "confidence": 0.8,
        "reasoning": "Tracks oil supply disruption.",
    }

    profile = validate_dynamic_profile("OILX", raw)

    assert profile.symbol == "OILX"
    assert profile.primary_factor == "oil"
    assert profile.exposures["oil"] == 1.0
    assert profile.exposures["energy_equities"] == 0.5
    assert "mystery" not in profile.exposures


def test_unknown_symbol_requires_classification():
    profile = classify_symbol("NEWOIL")

    assert profile.primary_factor == "unclassified"
    assert profile.confidence == 0.0
