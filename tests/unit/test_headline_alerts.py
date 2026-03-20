from src.data.adapters.sentiment import find_position_alerts


def test_high_relevancy_match():
    items = [{"text": "AAPL faces antitrust probe from DOJ", "relevancy": 0.85, "sentiment": -0.6}]
    alerts = find_position_alerts(items, {"AAPL", "MSFT"})
    assert len(alerts) == 1
    assert alerts[0]["matched_symbol"] == "AAPL"


def test_low_relevancy_ignored():
    items = [{"text": "AAPL faces antitrust probe", "relevancy": 0.30, "sentiment": -0.6}]
    alerts = find_position_alerts(items, {"AAPL"})
    assert alerts == []


def test_no_position_match():
    items = [{"text": "Oil prices surge on supply fears", "relevancy": 0.90, "sentiment": 0.7}]
    alerts = find_position_alerts(items, {"AAPL", "MSFT"})
    assert alerts == []


def test_empty_positions():
    items = [{"text": "AAPL beats earnings", "relevancy": 0.95, "sentiment": 0.8}]
    alerts = find_position_alerts(items, set())
    assert alerts == []


def test_crypto_ticker_cleaned():
    items = [{"text": "BTC surges past $100k resistance level", "relevancy": 0.80, "sentiment": 0.9}]
    alerts = find_position_alerts(items, {"BTC-USD"})
    assert len(alerts) == 1


def test_exact_threshold():
    items = [{"text": "MSFT acquires startup", "relevancy": 0.70, "sentiment": 0.5}]
    alerts = find_position_alerts(items, {"MSFT"})
    assert len(alerts) == 1  # 0.70 >= 0.70, should match


def test_matched_symbol_in_result():
    items = [{"text": "NVDA stock hits all time high", "relevancy": 0.88, "sentiment": 0.9}]
    alerts = find_position_alerts(items, {"NVDA", "AMD"})
    assert alerts[0]["matched_symbol"] == "NVDA"
    # Original fields preserved
    assert "sentiment" in alerts[0]
