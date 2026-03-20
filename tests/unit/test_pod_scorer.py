from src.agents.cio.pod_scorer import score_pod, format_scorecard, PodScore

def test_score_pod_high_performer():
    perf = {"sharpe": 3.0, "max_drawdown": -0.02, "total_return_pct": 0.25}
    stats = {"win_rate": 0.75}
    s = score_pod("equities", perf, stats)
    assert s.score > 0.70
    assert s.pod_id == "equities"

def test_score_pod_poor_performer():
    perf = {"sharpe": -1.5, "max_drawdown": -0.40, "total_return_pct": -0.20}
    stats = {"win_rate": 0.25}
    s = score_pod("equities", perf, stats)
    assert s.score < 0.30

def test_score_pod_missing_data():
    s = score_pod("equities", {}, {})
    assert 0.0 <= s.score <= 1.0  # no crash, sensible default

def test_format_scorecard_all_pods():
    scores = [
        score_pod("equities",   {"sharpe": 1.5, "max_drawdown": -0.05, "total_return_pct": 0.10}, {"win_rate": 0.60}),
        score_pod("crypto",     {"sharpe": 0.5, "max_drawdown": -0.20, "total_return_pct": -0.05}, {"win_rate": 0.40}),
        score_pod("fx",         {"sharpe": 1.0, "max_drawdown": -0.10, "total_return_pct": 0.05}, {"win_rate": 0.55}),
        score_pod("commodities",{"sharpe": 0.8, "max_drawdown": -0.15, "total_return_pct": 0.02}, {"win_rate": 0.50}),
    ]
    card = format_scorecard(scores)
    for pod in ["equities", "crypto", "fx", "commodities"]:
        assert pod in card
    assert "QUANTITATIVE SCORECARD" in card
    assert "75%" in card

def test_ranking_order():
    scores = [
        score_pod("bad",  {"sharpe": -1.0, "max_drawdown": -0.30, "total_return_pct": -0.10}, {"win_rate": 0.30}),
        score_pod("good", {"sharpe": 2.0,  "max_drawdown": -0.05, "total_return_pct": 0.20},  {"win_rate": 0.70}),
    ]
    card = format_scorecard(scores)
    # "good" should appear before "bad" in the output (sorted descending)
    assert card.index("good") < card.index("bad")
