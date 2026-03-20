from src.core.source_attribution import SourceAttributor, compute_dynamic_weights, MIN_WEIGHT

def test_floor_enforced():
    rates = {"fred": 0.95, "poly": 0.02, "news": 0.50}
    weights = compute_dynamic_weights(rates)
    assert all(w >= MIN_WEIGHT for w in weights.values())
    assert abs(sum(weights.values()) - 1.0) < 0.001

def test_equal_rates_equal_weights():
    rates = {"fred": 0.5, "poly": 0.5, "news": 0.5}
    weights = compute_dynamic_weights(rates)
    assert abs(weights["fred"] - weights["poly"]) < 0.01
    assert abs(weights["poly"] - weights["news"]) < 0.01

def test_better_source_gets_higher_weight():
    rates = {"fred": 0.80, "poly": 0.30, "news": 0.50}
    weights = compute_dynamic_weights(rates)
    assert weights["fred"] > weights["poly"]

def test_ingest_fred_key():
    attr = SourceAttributor()
    attr.ingest_closed_trade({"signal_snapshot": {"fred_score": 0.7}, "realized_pnl": 100.0})
    attr.ingest_closed_trade({"signal_snapshot": {"fred_score": 0.2}, "realized_pnl": -50.0})
    rates = attr.win_rates()
    assert rates["fred"] == 0.5    # 1 win / 2 trades

def test_ingest_poly_key():
    attr = SourceAttributor()
    attr.ingest_closed_trade({"signal_snapshot": {"poly_score": 0.9}, "realized_pnl": 200.0})
    rates = attr.win_rates()
    assert rates["poly"] == 1.0

def test_no_signal_source_untouched():
    attr = SourceAttributor()
    attr.ingest_closed_trade({"signal_snapshot": {}, "realized_pnl": 50.0})
    assert attr.sample_counts()["fred"] == 0

def test_empty_attribution_defaults_to_equal():
    attr = SourceAttributor()
    weights = attr.weights()
    assert abs(weights["fred"] - weights["poly"]) < 0.01
