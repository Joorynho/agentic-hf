import pytest
from datetime import datetime
from src.pods.templates.alpha.momentum_pm import MomentumPMAgent
from src.pods.base.namespace import PodNamespace
from src.core.models.market import Bar

def make_bars(prices: list[float]) -> list[Bar]:
    return [Bar(symbol="AAPL", timestamp=datetime(2024,1,i+1),
                open=p, high=p*1.01, low=p*0.99, close=p,
                volume=1_000_000, source="test")
            for i, p in enumerate(prices)]

def test_momentum_generates_buy_signal_on_uptrend():
    ns = PodNamespace("alpha")
    agent = MomentumPMAgent(pod_id="alpha", namespace=ns, fast_window=3, slow_window=5)
    bars = make_bars([100, 101, 102, 103, 104, 105, 106])
    signal = agent.compute_signal("AAPL", bars)
    assert signal > 0

def test_momentum_generates_sell_signal_on_downtrend():
    ns = PodNamespace("alpha")
    agent = MomentumPMAgent(pod_id="alpha", namespace=ns, fast_window=3, slow_window=5)
    bars = make_bars([110, 109, 108, 107, 106, 105, 104])
    signal = agent.compute_signal("AAPL", bars)
    assert signal < 0

def test_momentum_returns_zero_with_insufficient_data():
    ns = PodNamespace("alpha")
    agent = MomentumPMAgent(pod_id="alpha", namespace=ns)
    bars = make_bars([100, 101])
    signal = agent.compute_signal("AAPL", bars)
    assert signal == 0.0

def test_signal_stored_in_namespace():
    ns = PodNamespace("alpha")
    agent = MomentumPMAgent(pod_id="alpha", namespace=ns, fast_window=3, slow_window=5)
    bars = make_bars([100, 101, 102, 103, 104, 105, 106])
    agent.compute_signal("AAPL", bars)
    assert ns.get("signal::AAPL") is not None
