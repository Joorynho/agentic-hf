# Agent Intelligence Upgrade — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Close the feedback loop so agents learn from trade outcomes, size positions by conviction, adapt to market regimes, and share intelligence across pods — all to improve PnL.

**Architecture:** Seven capabilities built in four phases. Phase 1 enriches data capture. Phase 2 feeds outcomes back to PMs. Phase 3 makes sizing regime- and conviction-aware. Phase 4 upgrades CIO with attribution and cross-pod memos. Each phase is independently valuable but they compound.

**Tech Stack:** Python 3.12, Pydantic v2, asyncio, OpenRouter/OpenAI LLM, FRED macro data, PortfolioAccountant

---

## Phase 1: Data Enrichment & Persistence Foundation

### Task 1: Enrich TradeProposal with conviction and entry thesis

**Files:**
- Modify: `src/core/models/execution.py` (TradeProposal, lines 78-83)
- Modify: `src/core/models/execution.py` (PositionSnapshot, lines 86-105)
- Test: `tests/test_trade_proposal.py` (create)

**Step 1: Write the failing test**

```python
# tests/test_trade_proposal.py
"""Tests for enriched TradeProposal and PositionSnapshot models."""
import pytest
from src.core.models.execution import TradeProposal, PositionSnapshot


def test_trade_proposal_has_conviction():
    tp = TradeProposal(action="BUY", symbol="AAPL", qty=10, reasoning="Strong thesis",
                       conviction=0.85)
    assert tp.conviction == 0.85

def test_trade_proposal_conviction_default():
    tp = TradeProposal(action="BUY", symbol="AAPL", qty=10)
    assert tp.conviction == 0.5

def test_trade_proposal_conviction_clamped():
    tp = TradeProposal(action="BUY", symbol="AAPL", qty=10, conviction=1.5)
    assert tp.conviction == 1.0
    tp2 = TradeProposal(action="BUY", symbol="AAPL", qty=10, conviction=-0.3)
    assert tp2.conviction == 0.0

def test_trade_proposal_has_strategy_tag():
    tp = TradeProposal(action="BUY", symbol="AAPL", qty=10, strategy_tag="macro_momentum")
    assert tp.strategy_tag == "macro_momentum"

def test_trade_proposal_has_signal_snapshot():
    snap = {"vix": 18.5, "yield_curve": 0.3, "poly_top": "Election 65%"}
    tp = TradeProposal(action="BUY", symbol="AAPL", qty=10, signal_snapshot=snap)
    assert tp.signal_snapshot["vix"] == 18.5

def test_position_snapshot_has_entry_thesis():
    ps = PositionSnapshot(symbol="AAPL", qty=10, cost_basis=150.0,
                          current_price=155.0, unrealized_pnl=50.0,
                          entry_thesis="Strong iPhone cycle", entry_date="2026-03-10")
    assert ps.entry_thesis == "Strong iPhone cycle"
    assert ps.entry_date == "2026-03-10"
```

**Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_trade_proposal.py -v`
Expected: FAIL — fields don't exist yet

**Step 3: Write minimal implementation**

Add to `TradeProposal` in `src/core/models/execution.py`:

```python
class TradeProposal(BaseModel):
    """Validated trade proposal from LLM output. Rejects malformed trades."""
    action: Literal["BUY", "SELL"]
    symbol: str
    qty: float = Field(gt=0)
    reasoning: str = ""
    conviction: float = Field(default=0.5, ge=0.0, le=1.0)
    strategy_tag: str = ""
    signal_snapshot: dict = Field(default_factory=dict)

    @model_validator(mode="after")
    def clamp_conviction(self):
        self.conviction = max(0.0, min(1.0, self.conviction))
        return self
```

Add to `PositionSnapshot`:

```python
class PositionSnapshot(BaseModel):
    symbol: str
    qty: float
    cost_basis: float
    current_price: float
    unrealized_pnl: float
    entry_thesis: str = ""
    entry_date: str = ""
    # ... existing properties unchanged
```

**Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_trade_proposal.py -v`
Expected: PASS

**Step 5: Run full test suite**

Run: `python -m pytest tests/ -v --tb=short`
Expected: All 352+ tests pass (new fields have defaults, so backwards-compatible)

**Step 6: Commit**

```
git add src/core/models/execution.py tests/test_trade_proposal.py
git commit -m "feat: add conviction, strategy_tag, signal_snapshot to TradeProposal; entry_thesis to PositionSnapshot"
```

---

### Task 2: Enrich trade logging with reasoning and signal context

**Files:**
- Modify: `src/backtest/accounting/portfolio.py` (record_fill_direct, lines 51-134)
- Modify: `src/pods/runtime/pod_runtime.py` (trade execution flow)
- Modify: `src/mission_control/session_logger.py` (log_trade)

**Step 1: Extend `record_fill_direct` to accept optional metadata**

Add optional kwargs to `record_fill_direct` in `src/backtest/accounting/portfolio.py`:

```python
def record_fill_direct(
    self,
    order_id: str,
    symbol: str,
    qty: float,
    fill_price: float,
    filled_at: datetime | None = None,
    reasoning: str = "",
    strategy_tag: str = "",
    signal_snapshot: dict | None = None,
    conviction: float = 0.5,
    entry_thesis: str = "",
) -> None:
```

Store these in the `_fill_log` entry:

```python
self._fill_log.append({
    "timestamp": filled_at,
    "order_id": order_id,
    "symbol": symbol,
    "qty": qty,
    "fill_price": fill_price,
    "notional": qty * fill_price,
    "reasoning": reasoning,
    "strategy_tag": strategy_tag,
    "signal_snapshot": signal_snapshot or {},
    "conviction": conviction,
})
```

Also store `entry_thesis` in `self._entry_theses[symbol]` (new dict attribute) when opening a position (qty goes from 0 to non-zero):

```python
if symbol not in self._positions or self._positions[symbol]["quantity"] == 0:
    self._entry_theses[symbol] = entry_thesis or reasoning
```

**Step 2: Wire entry thesis into `current_positions`**

Modify `current_positions` property to include `entry_thesis` and `entry_date` from stored metadata.

**Step 3: Wire reasoning through pod_runtime**

In `src/pods/runtime/pod_runtime.py`, when `record_fill_direct` is called after order execution, pass the PM's reasoning from `last_pm_decision` namespace:

```python
pm_decision = self._ns.get("last_pm_decision") or {}
trades = pm_decision.get("trades", [])
matched = next((t for t in trades if t.get("symbol") == order.symbol), {})

accountant.record_fill_direct(
    order_id=str(result.order_id or order.id),
    symbol=order.symbol,
    qty=signed_qty,
    fill_price=result.fill_price or 0,
    reasoning=matched.get("reasoning", ""),
    strategy_tag=order.strategy_tag or "",
    signal_snapshot=pm_decision.get("signal_snapshot", {}),
    conviction=matched.get("conviction", 0.5),
    entry_thesis=matched.get("reasoning", ""),
)
```

**Step 4: Update `log_trade` in session_logger**

Add `reasoning`, `strategy_tag`, `conviction` to the trade entry dict in `session_logger.py`.

**Step 5: Run full test suite**

Run: `python -m pytest tests/ -v --tb=short`
Expected: All tests pass (all new params are optional with defaults)

**Step 6: Commit**

```
git commit -am "feat: enrich trade logs with reasoning, conviction, strategy_tag, signal_snapshot"
```

---

### Task 3: Compute and store realized PnL per closed trade

**Files:**
- Modify: `src/backtest/accounting/portfolio.py` (record_fill_direct)
- Test: `tests/test_trade_outcomes.py` (create)

**Step 1: Write failing test**

```python
# tests/test_trade_outcomes.py
"""Tests for realized PnL tracking per closed trade."""
import pytest
from datetime import datetime
from src.backtest.accounting.portfolio import PortfolioAccountant


def test_realized_pnl_on_close():
    acct = PortfolioAccountant(pod_id="test", starting_capital=10000)
    # Buy 10 shares at $100
    acct.record_fill_direct("o1", "AAPL", 10, 100.0, datetime(2026, 1, 1),
                            reasoning="Strong thesis", conviction=0.8)
    # Sell 10 shares at $110 → $100 realized PnL
    acct.record_fill_direct("o2", "AAPL", -10, 110.0, datetime(2026, 1, 5))
    
    closed = acct.closed_trades
    assert len(closed) == 1
    assert closed[0]["symbol"] == "AAPL"
    assert closed[0]["realized_pnl"] == pytest.approx(100.0)
    assert closed[0]["entry_price"] == pytest.approx(100.0)
    assert closed[0]["exit_price"] == pytest.approx(110.0)
    assert closed[0]["pnl_pct"] == pytest.approx(10.0)
    assert closed[0]["entry_reasoning"] == "Strong thesis"
    assert closed[0]["hold_days"] == 4


def test_partial_close():
    acct = PortfolioAccountant(pod_id="test", starting_capital=10000)
    acct.record_fill_direct("o1", "AAPL", 10, 100.0, datetime(2026, 1, 1), reasoning="Thesis A")
    # Sell 5 at $105 → $25 realized PnL
    acct.record_fill_direct("o2", "AAPL", -5, 105.0, datetime(2026, 1, 3))
    
    closed = acct.closed_trades
    assert len(closed) == 1
    assert closed[0]["qty_closed"] == 5
    assert closed[0]["realized_pnl"] == pytest.approx(25.0)
    # Position still open with 5 shares
    assert acct.current_positions["AAPL"].qty == 5


def test_no_closed_trades_when_only_open():
    acct = PortfolioAccountant(pod_id="test", starting_capital=10000)
    acct.record_fill_direct("o1", "AAPL", 10, 100.0, datetime(2026, 1, 1))
    assert len(acct.closed_trades) == 0
```

**Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_trade_outcomes.py -v`
Expected: FAIL — `closed_trades` attribute doesn't exist

**Step 3: Implement closed trade tracking**

In `PortfolioAccountant.__init__`, add:

```python
self._closed_trades: list[dict] = []
self._entry_metadata: dict[str, dict] = {}  # symbol → {entry_price, entry_time, reasoning, conviction, signal_snapshot}
```

In `record_fill_direct`, when opening a new position (qty was 0):
```python
if old_qty == 0 and qty != 0:
    self._entry_metadata[symbol] = {
        "entry_price": fill_price,
        "entry_time": filled_at,
        "entry_reasoning": reasoning,
        "conviction": conviction,
        "signal_snapshot": signal_snapshot or {},
    }
```

When closing/reducing a position (qty changes toward zero):
```python
if old_qty != 0 and abs(new_qty) < abs(old_qty):
    closed_qty = abs(old_qty) - abs(new_qty)
    meta = self._entry_metadata.get(symbol, {})
    entry_price = meta.get("entry_price", self._cost_basis.get(symbol, fill_price))
    entry_time = meta.get("entry_time")
    hold_days = (filled_at - entry_time).days if filled_at and entry_time else 0
    pnl = closed_qty * (fill_price - entry_price) * (1 if old_qty > 0 else -1)
    self._closed_trades.append({
        "symbol": symbol,
        "side": "LONG" if old_qty > 0 else "SHORT",
        "qty_closed": closed_qty,
        "entry_price": entry_price,
        "exit_price": fill_price,
        "realized_pnl": round(pnl, 4),
        "pnl_pct": round((fill_price - entry_price) / entry_price * 100, 2) if entry_price else 0,
        "hold_days": hold_days,
        "entry_reasoning": meta.get("entry_reasoning", ""),
        "conviction": meta.get("conviction", 0.5),
        "signal_snapshot": meta.get("signal_snapshot", {}),
        "closed_at": filled_at.isoformat() if filled_at else "",
    })
    if new_qty == 0:
        self._entry_metadata.pop(symbol, None)
```

Add property:
```python
@property
def closed_trades(self) -> list[dict]:
    return list(self._closed_trades)
```

**Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_trade_outcomes.py -v`
Expected: PASS

**Step 5: Run full suite**

Run: `python -m pytest tests/ -v --tb=short`
Expected: All tests pass

**Step 6: Commit**

```
git commit -am "feat: track realized PnL per closed trade with entry reasoning and signal snapshot"
```

---

## Phase 2: Trade Outcome Feedback Loop

### Task 4: Build TradeOutcomeTracker

**Files:**
- Create: `src/core/trade_outcomes.py`
- Test: `tests/test_outcome_tracker.py` (create)

**Step 1: Write failing test**

```python
# tests/test_outcome_tracker.py
"""Tests for TradeOutcomeTracker — aggregates and scores trade history."""
import pytest
from src.core.trade_outcomes import TradeOutcomeTracker


def test_add_and_retrieve_outcomes():
    tracker = TradeOutcomeTracker()
    tracker.add_outcome({
        "symbol": "AAPL", "realized_pnl": 50.0, "pnl_pct": 5.0,
        "entry_reasoning": "iPhone cycle", "conviction": 0.8,
        "hold_days": 5, "side": "LONG",
    })
    tracker.add_outcome({
        "symbol": "TSLA", "realized_pnl": -30.0, "pnl_pct": -3.0,
        "entry_reasoning": "EV hype", "conviction": 0.6,
        "hold_days": 2, "side": "LONG",
    })
    assert tracker.total_trades == 2
    assert tracker.win_rate == pytest.approx(0.5)
    assert tracker.avg_pnl == pytest.approx(10.0)


def test_recent_outcomes_for_prompt():
    tracker = TradeOutcomeTracker()
    for i in range(25):
        tracker.add_outcome({
            "symbol": f"SYM{i}", "realized_pnl": 10 * (1 if i % 2 == 0 else -1),
            "pnl_pct": 1.0, "entry_reasoning": f"thesis {i}",
            "conviction": 0.7, "hold_days": 3, "side": "LONG",
        })
    prompt_text = tracker.format_for_pm_prompt(max_recent=10)
    assert "SYM24" in prompt_text  # most recent included
    assert "Win rate:" in prompt_text
    assert "SYM0" not in prompt_text  # oldest excluded


def test_per_symbol_stats():
    tracker = TradeOutcomeTracker()
    tracker.add_outcome({"symbol": "AAPL", "realized_pnl": 50, "pnl_pct": 5.0, "side": "LONG",
                         "entry_reasoning": "", "conviction": 0.8, "hold_days": 5})
    tracker.add_outcome({"symbol": "AAPL", "realized_pnl": -20, "pnl_pct": -2.0, "side": "LONG",
                         "entry_reasoning": "", "conviction": 0.6, "hold_days": 3})
    stats = tracker.symbol_stats("AAPL")
    assert stats["trades"] == 2
    assert stats["win_rate"] == pytest.approx(0.5)
    assert stats["total_pnl"] == pytest.approx(30.0)
```

**Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_outcome_tracker.py -v`
Expected: FAIL — module doesn't exist

**Step 3: Implement TradeOutcomeTracker**

```python
# src/core/trade_outcomes.py
"""Trade outcome tracker — aggregates closed-trade results for PM feedback."""
from __future__ import annotations
import logging

logger = logging.getLogger(__name__)


class TradeOutcomeTracker:
    """Aggregates closed-trade outcomes and formats them for PM context."""

    def __init__(self, max_history: int = 100) -> None:
        self._outcomes: list[dict] = []
        self._max_history = max_history

    def add_outcome(self, outcome: dict) -> None:
        self._outcomes.append(outcome)
        if len(self._outcomes) > self._max_history:
            self._outcomes = self._outcomes[-self._max_history:]

    @property
    def total_trades(self) -> int:
        return len(self._outcomes)

    @property
    def win_rate(self) -> float:
        if not self._outcomes:
            return 0.0
        wins = sum(1 for o in self._outcomes if o.get("realized_pnl", 0) > 0)
        return wins / len(self._outcomes)

    @property
    def avg_pnl(self) -> float:
        if not self._outcomes:
            return 0.0
        return sum(o.get("realized_pnl", 0) for o in self._outcomes) / len(self._outcomes)

    def symbol_stats(self, symbol: str) -> dict:
        sym_trades = [o for o in self._outcomes if o.get("symbol") == symbol]
        if not sym_trades:
            return {"trades": 0, "win_rate": 0, "total_pnl": 0, "avg_pnl": 0}
        wins = sum(1 for o in sym_trades if o.get("realized_pnl", 0) > 0)
        total = sum(o.get("realized_pnl", 0) for o in sym_trades)
        return {
            "trades": len(sym_trades),
            "win_rate": wins / len(sym_trades),
            "total_pnl": total,
            "avg_pnl": total / len(sym_trades),
        }

    def format_for_pm_prompt(self, max_recent: int = 10) -> str:
        if not self._outcomes:
            return ""
        recent = self._outcomes[-max_recent:]
        lines = [
            f"## Trade Track Record (last {len(self._outcomes)} trades)",
            f"Win rate: {self.win_rate:.0%} | Avg PnL: ${self.avg_pnl:+.2f}",
            "",
            "Recent outcomes (newest first):",
        ]
        for o in reversed(recent):
            pnl = o.get("realized_pnl", 0)
            symbol = o.get("symbol", "?")
            side = o.get("side", "?")
            pct = o.get("pnl_pct", 0)
            days = o.get("hold_days", "?")
            thesis = (o.get("entry_reasoning", "") or "")[:80]
            result = "WIN" if pnl > 0 else "LOSS"
            lines.append(
                f"  {result}: {side} {symbol} → ${pnl:+.2f} ({pct:+.1f}%) held {days}d | thesis: {thesis}"
            )
        return "\n".join(lines)

    def to_state_dict(self) -> list[dict]:
        return list(self._outcomes)

    def load_from_state(self, outcomes: list[dict]) -> None:
        self._outcomes = outcomes[-self._max_history:]
```

**Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_outcome_tracker.py -v`
Expected: PASS

**Step 5: Commit**

```
git commit -am "feat: add TradeOutcomeTracker for aggregating closed-trade feedback"
```

---

### Task 5: Feed trade outcomes into PM decision context

**Files:**
- Modify: `src/pods/runtime/pod_runtime.py` (integrate TradeOutcomeTracker)
- Modify: `src/pods/templates/equities/pm_agent.py` (and fx, crypto, commodities variants)
- Modify: `src/mission_control/session_manager.py` (persist outcomes in memory)

**Step 1: Integrate TradeOutcomeTracker into PodRuntime**

In `PodRuntime.__init__`, create a `TradeOutcomeTracker` per pod:
```python
from src.core.trade_outcomes import TradeOutcomeTracker
self._outcome_tracker = TradeOutcomeTracker()
```

After a fill is recorded in `record_fill_direct`, check the accountant's `closed_trades` for new entries and feed them to the tracker.

Store the tracker in the namespace so the PM can access it:
```python
self._ns.set("outcome_tracker", self._outcome_tracker)
```

**Step 2: Inject trade track record into PM prompt**

In each PM agent's `_llm_decision` method, add a new section after "Recent Decision History":

```python
outcome_tracker = self.recall("outcome_tracker")
if outcome_tracker:
    track_record = outcome_tracker.format_for_pm_prompt(max_recent=10)
    if track_record:
        user_content += f"\n\n{track_record}\n"
```

Also inject the signal snapshot so the PM's reasoning references it:
```python
# Before returning trades, capture the signal snapshot from features
features = context.get("features", {})
signal_snap = {
    "vix": features.get("fred_indicators", {}).get("vix"),
    "yield_curve": features.get("fred_indicators", {}).get("yield_curve_10y2y"),
    "macro_outlook": features.get("macro_outlook"),
    "top_poly": [p.get("question", "?")[:50] for p in features.get("polymarket_predictions", [])[:3]],
}
```

**Step 3: Persist outcomes in session memory**

In `session_manager.py`, extend `_save_memory` to include per-pod outcome trackers:
```python
for pod_id, runtime in self._pod_runtimes.items():
    tracker = runtime._outcome_tracker
    state["outcomes"][pod_id] = tracker.to_state_dict()
```

And in `_load_memory`, restore them:
```python
outcomes = memory.get("outcomes", {})
for pod_id, outcome_list in outcomes.items():
    if pod_id in self._pod_runtimes:
        self._pod_runtimes[pod_id]._outcome_tracker.load_from_state(outcome_list)
```

**Step 4: Run full test suite**

Run: `python -m pytest tests/ -v --tb=short`
Expected: All tests pass

**Step 5: Commit**

```
git commit -am "feat: feed trade outcome track record into PM decision prompts"
```

---

### Task 6: Signal quality scoring

**Files:**
- Create: `src/core/signal_scorer.py`
- Modify: `src/core/trade_outcomes.py` (add signal attribution)
- Modify: PM agents (inject signal scores into context)
- Test: `tests/test_signal_scorer.py` (create)

**Step 1: Write failing test**

```python
# tests/test_signal_scorer.py
"""Tests for signal quality scoring — tracks which signals precede wins vs losses."""
import pytest
from src.core.signal_scorer import SignalScorer


def test_record_and_score():
    scorer = SignalScorer()
    scorer.record_outcome({"macro_outlook": "bullish", "vix": 18}, pnl=50.0)
    scorer.record_outcome({"macro_outlook": "bullish", "vix": 22}, pnl=-20.0)
    scorer.record_outcome({"macro_outlook": "bearish", "vix": 30}, pnl=-40.0)

    scores = scorer.signal_scores()
    assert scores["macro_outlook:bullish"]["trades"] == 2
    assert scores["macro_outlook:bullish"]["win_rate"] == pytest.approx(0.5)
    assert scores["macro_outlook:bearish"]["trades"] == 1
    assert scores["macro_outlook:bearish"]["win_rate"] == pytest.approx(0.0)


def test_format_for_prompt():
    scorer = SignalScorer()
    for _ in range(5):
        scorer.record_outcome({"macro_outlook": "bullish"}, pnl=10.0)
    for _ in range(3):
        scorer.record_outcome({"macro_outlook": "bullish"}, pnl=-5.0)
    text = scorer.format_for_prompt()
    assert "macro_outlook:bullish" in text
    assert "62%" in text  # 5/8 win rate
```

**Step 2: Implement SignalScorer**

```python
# src/core/signal_scorer.py
"""Signal scorer — tracks which signal conditions precede winning vs losing trades."""
from __future__ import annotations


class SignalScorer:
    """Tracks signal→outcome association for quality scoring."""

    def __init__(self) -> None:
        self._records: dict[str, dict] = {}  # signal_key → {wins, losses, total_pnl}

    def record_outcome(self, signal_snapshot: dict, pnl: float) -> None:
        for key, value in signal_snapshot.items():
            if value is None:
                continue
            # Discretize continuous values
            if isinstance(value, (int, float)):
                if key == "vix":
                    bucket = "low" if value < 20 else "medium" if value < 30 else "high"
                elif key == "yield_curve":
                    bucket = "positive" if value > 0 else "inverted"
                else:
                    continue
                signal_key = f"{key}:{bucket}"
            else:
                signal_key = f"{key}:{value}"

            if signal_key not in self._records:
                self._records[signal_key] = {"wins": 0, "losses": 0, "total_pnl": 0.0, "trades": 0}
            rec = self._records[signal_key]
            rec["trades"] += 1
            rec["total_pnl"] += pnl
            if pnl > 0:
                rec["wins"] += 1
            else:
                rec["losses"] += 1

    def signal_scores(self) -> dict[str, dict]:
        result = {}
        for key, rec in self._records.items():
            result[key] = {
                "trades": rec["trades"],
                "win_rate": rec["wins"] / rec["trades"] if rec["trades"] else 0,
                "avg_pnl": rec["total_pnl"] / rec["trades"] if rec["trades"] else 0,
            }
        return result

    def format_for_prompt(self, min_trades: int = 3) -> str:
        scores = self.signal_scores()
        relevant = {k: v for k, v in scores.items() if v["trades"] >= min_trades}
        if not relevant:
            return ""
        lines = ["## Signal Quality (based on past trade outcomes)"]
        for key, s in sorted(relevant.items(), key=lambda x: -x[1]["trades"]):
            lines.append(f"  {key}: {s['win_rate']:.0%} win rate ({s['trades']} trades, avg ${s['avg_pnl']:+.2f})")
        return "\n".join(lines)

    def to_state_dict(self) -> dict:
        return dict(self._records)

    def load_from_state(self, state: dict) -> None:
        self._records = state
```

**Step 3: Wire into TradeOutcomeTracker**

When a new outcome is added, also feed it to the SignalScorer if a signal_snapshot is present.

**Step 4: Inject into PM prompts**

After trade track record, add signal quality section:
```python
signal_scorer = self.recall("signal_scorer")
if signal_scorer:
    sig_text = signal_scorer.format_for_prompt()
    if sig_text:
        user_content += f"\n\n{sig_text}\n"
```

**Step 5: Run tests, commit**

```
git commit -am "feat: add signal quality scoring — track which signals precede wins vs losses"
```

---

## Phase 3: Conviction-Aware Sizing & Market Regime

### Task 7: PM outputs conviction score

**Files:**
- Modify: `src/pods/templates/equities/pm_agent.py` (and fx, crypto, commodities)
- Modify: System prompts to request conviction

**Step 1: Update PM system prompt**

Add to the JSON output format in `_EQUITIES_SYSTEM`:
```
Each trade MUST include:
- "conviction": float 0.0-1.0 (0.3=speculative, 0.5=moderate, 0.7=high, 0.9=very high)
```

**Step 2: Parse conviction from LLM output**

When parsing `TradeProposal` from LLM response, include `conviction`:
```python
proposal = TradeProposal(
    action=t["action"],
    symbol=t["symbol"],
    qty=t.get("qty", 1),
    reasoning=t.get("reasoning", ""),
    conviction=float(t.get("conviction", 0.5)),
    strategy_tag=t.get("strategy_tag", ""),
)
```

**Step 3: Pass conviction through to Order**

When creating `Order` from `TradeProposal`, store conviction as metadata so the risk agent can access it.

Add optional field to `Order` in `src/core/models/execution.py`:
```python
class Order(BaseModel):
    # ... existing fields ...
    conviction: float = 0.5
```

**Step 4: Run tests, commit**

```
git commit -am "feat: PM agents output conviction score (0-1) with each trade proposal"
```

---

### Task 8: Conviction-aware risk agent

**Files:**
- Modify: `src/pods/templates/equities/risk_agent.py` (and fx, crypto, commodities)

**Step 1: Adjust position limit based on conviction**

Replace the flat `MAX_POSITION_PCT = 0.20` with a conviction-scaled limit:

```python
BASE_POSITION_PCT = 0.10
MAX_POSITION_PCT = 0.25

def _conviction_limit(conviction: float) -> float:
    """Scale position limit by conviction: 10% at conv=0.3, 25% at conv=1.0."""
    return BASE_POSITION_PCT + (MAX_POSITION_PCT - BASE_POSITION_PCT) * max(0, conviction - 0.3) / 0.7
```

In the position limit check:
```python
conv = order.conviction if hasattr(order, 'conviction') else 0.5
limit_pct = _conviction_limit(conv)
if new_notional / nav > limit_pct:
    max_qty = (nav * limit_pct - existing_notional) / price
    ...
```

Log the conviction-adjusted limit:
```python
logger.info("[%s.risk] Conviction %.2f → position limit %.1f%% of NAV", pod_id, conv, limit_pct * 100)
```

**Step 2: Run tests, commit**

```
git commit -am "feat: risk agent scales position limits by PM conviction (10-25% of NAV)"
```

---

### Task 9: Market regime classifier

**Files:**
- Create: `src/core/regime.py`
- Test: `tests/test_regime.py` (create)

**Step 1: Write failing test**

```python
# tests/test_regime.py
"""Tests for market regime classifier."""
import pytest
from src.core.regime import classify_regime, RegimeConfig


def test_risk_on_regime():
    regime = classify_regime(vix=14, yield_curve=0.8, credit_spread=3.0)
    assert regime.name == "risk_on"
    assert regime.position_scale > 1.0

def test_risk_off_regime():
    regime = classify_regime(vix=35, yield_curve=-0.5, credit_spread=6.0)
    assert regime.name == "risk_off"
    assert regime.position_scale < 1.0

def test_neutral_regime():
    regime = classify_regime(vix=22, yield_curve=0.1, credit_spread=4.5)
    assert regime.name == "neutral"
    assert regime.position_scale == pytest.approx(1.0)

def test_missing_data_defaults_neutral():
    regime = classify_regime(vix=None, yield_curve=None, credit_spread=None)
    assert regime.name == "neutral"
```

**Step 2: Implement regime classifier**

```python
# src/core/regime.py
"""Market regime classifier — uses FRED macro data to determine risk environment."""
from __future__ import annotations
from dataclasses import dataclass


@dataclass
class RegimeConfig:
    name: str           # risk_on, neutral, risk_off, crisis
    position_scale: float  # multiplier for position limits (0.5x to 1.5x)
    leverage_cap: float    # max leverage override
    description: str


def classify_regime(
    vix: float | None = None,
    yield_curve: float | None = None,
    credit_spread: float | None = None,
) -> RegimeConfig:
    """Classify market regime from macro indicators.
    
    Returns a RegimeConfig with sizing adjustments.
    """
    score = 0  # -3 (crisis) to +3 (risk-on)

    if vix is not None:
        if vix < 15:
            score += 2
        elif vix < 20:
            score += 1
        elif vix > 30:
            score -= 2
        elif vix > 25:
            score -= 1

    if yield_curve is not None:
        if yield_curve > 0.5:
            score += 1
        elif yield_curve < -0.2:
            score -= 1

    if credit_spread is not None:
        if credit_spread < 3.5:
            score += 1
        elif credit_spread > 5.0:
            score -= 1

    if score >= 2:
        return RegimeConfig("risk_on", 1.3, 2.5, "Low vol, positive curve — favorable conditions")
    elif score <= -2:
        return RegimeConfig("risk_off", 0.5, 1.0, "High vol or inverted curve — defensive posture")
    elif score <= -3:
        return RegimeConfig("crisis", 0.3, 0.5, "Crisis conditions — minimal exposure")
    else:
        return RegimeConfig("neutral", 1.0, 2.0, "Mixed signals — standard sizing")
```

**Step 3: Run test, commit**

```
git commit -am "feat: add market regime classifier using VIX, yield curve, credit spread"
```

---

### Task 10: Dynamic position limits based on regime

**Files:**
- Modify: `src/pods/runtime/pod_runtime.py` (inject regime into namespace)
- Modify: `src/pods/templates/equities/risk_agent.py` (scale limits by regime)
- Modify: `src/pods/templates/equities/signal_agent.py` (compute and store regime)

**Step 1: Compute regime in signal agent**

In each signal agent's `run_cycle`, after computing features:
```python
from src.core.regime import classify_regime
regime = classify_regime(
    vix=vix,
    yield_curve=yield_curve,
    credit_spread=credit_spread,
)
features["regime"] = {"name": regime.name, "position_scale": regime.position_scale,
                       "leverage_cap": regime.leverage_cap, "description": regime.description}
```

**Step 2: Use regime in risk agent**

```python
features = context.get("features") or self.recall("features") or {}
regime = features.get("regime", {})
regime_scale = regime.get("position_scale", 1.0)

# Apply conviction AND regime scaling
conv = order.conviction if hasattr(order, 'conviction') else 0.5
base_limit = _conviction_limit(conv)
effective_limit = min(base_limit * regime_scale, 0.30)  # Hard cap at 30%

logger.info("[%s.risk] Regime=%s (%.1fx) + conviction=%.2f → limit %.1f%%",
            self._pod_id, regime.get("name", "neutral"), regime_scale, conv, effective_limit * 100)
```

**Step 3: Log regime in PM prompt**

Add to PM context:
```python
regime = features.get("regime", {})
if regime:
    user_content += f"\n## Market Regime: {regime.get('name', 'neutral').upper()}\n"
    user_content += f"{regime.get('description', '')}\n"
    user_content += f"Position sizing multiplier: {regime.get('position_scale', 1.0):.1f}x\n"
```

**Step 4: Run tests, commit**

```
git commit -am "feat: dynamic position limits scaled by market regime and conviction"
```

---

## Phase 4: Cross-Pod Intelligence & CIO Attribution

### Task 11: Pod macro view memos

**Files:**
- Modify: `src/pods/runtime/pod_runtime.py` (emit macro view after each cycle)
- Modify: `src/mission_control/session_manager.py` (aggregate views into firm memo)
- Modify: PM system prompts (inject firm memo)

**Step 1: After each pod cycle, extract a one-line macro view**

In `PodRuntime`, after the PM decision, store a macro view in the namespace:
```python
pm_decision = self._ns.get("last_pm_decision") or {}
features = self._ns.get("features") or {}
macro_view = {
    "pod_id": self._pod_id,
    "outlook": features.get("macro_outlook", "neutral"),
    "regime": features.get("regime", {}).get("name", "neutral"),
    "action_summary": pm_decision.get("action_summary", "HOLD"),
    "top_conviction": max([t.get("conviction", 0.5) for t in pm_decision.get("trades", [{"conviction": 0.5}])]),
}
self._ns.set("macro_view", macro_view)
```

**Step 2: Aggregate in session_manager**

Before each pod's cycle, build a firm-wide intelligence memo from other pods' macro_views:
```python
def _build_firm_memo(self, exclude_pod: str) -> str:
    lines = ["## Firm Intelligence Memo (from other pods)"]
    for pod_id, runtime in self._pod_runtimes.items():
        if pod_id == exclude_pod:
            continue
        view = runtime._ns.get("macro_view")
        if view:
            lines.append(f"  {pod_id.upper()}: {view['outlook']} regime={view['regime']} | last action: {view['action_summary']}")
    return "\n".join(lines) if len(lines) > 1 else ""
```

Inject into each pod's namespace before the cycle:
```python
memo = self._build_firm_memo(exclude_pod=pod_id)
runtime._ns.set("firm_memo", memo)
```

**Step 3: PM reads firm memo**

In PM agent `_llm_decision`:
```python
firm_memo = self.recall("firm_memo")
if firm_memo:
    user_content += f"\n\n{firm_memo}\n"
```

**Step 4: Run tests, commit**

```
git commit -am "feat: cross-pod intelligence memos — each PM sees other pods' macro views"
```

---

### Task 12: CIO performance attribution

**Files:**
- Modify: `src/mission_control/session_manager.py` (build attribution data)
- Modify: `src/agents/cio/cio_agent.py` (inject attribution into allocation prompt)

**Step 1: Build attribution data**

In `session_manager._build_pod_intelligence_briefs`, add performance attribution:

```python
# Per-pod attribution
acct = pod_accountants.get(pod_id)
if acct:
    tracker = runtime._outcome_tracker
    brief["performance"] = {
        "total_trades": tracker.total_trades,
        "win_rate": f"{tracker.win_rate:.0%}",
        "avg_pnl": f"${tracker.avg_pnl:+.2f}",
        "realized_pnl": f"${acct._realized_pnl:+.2f}",
        "unrealized_pnl": f"${sum(p.unrealized_pnl for p in acct.current_positions.values()):+.2f}",
    }
```

**Step 2: Include attribution in CIO intelligence brief**

In `cio_agent._format_intelligence_brief`, add:
```python
if brief.get("performance"):
    perf = brief["performance"]
    lines.append(f"  Performance: {perf['total_trades']} trades, {perf['win_rate']} win rate, "
                 f"realized={perf['realized_pnl']}, unrealized={perf['unrealized_pnl']}")
```

**Step 3: Update CIO allocation prompt**

In the LLM allocation prompt, add:
```
Consider performance attribution when rebalancing: allocate more capital to pods 
with higher risk-adjusted returns and better win rates. Reduce allocation to 
underperforming pods unless they have strong signal environments.
```

**Step 4: Run tests, commit**

```
git commit -am "feat: CIO performance attribution — allocation decisions informed by pod track records"
```

---

### Task 13: Position reviewer gets entry thesis

**Files:**
- Modify: `src/agents/governance/position_reviewer.py` (_review_pod, _cio_review, _pm_defend)

**Step 1: Include entry thesis in position text**

In `_review_pod`, when building `pos_lines`:
```python
for sym, snap in positions.items():
    pnl_pct = ((snap.current_price - snap.cost_basis) / snap.cost_basis * 100) if snap.cost_basis else 0
    thesis_note = f" | entry thesis: {snap.entry_thesis}" if snap.entry_thesis else ""
    date_note = f" | held since {snap.entry_date}" if snap.entry_date else ""
    pos_lines.append(
        f"  {sym}: qty={snap.qty:.4f}, cost=${snap.cost_basis:.2f}, "
        f"current=${snap.current_price:.2f}, P&L=${snap.unrealized_pnl:+.2f} ({pnl_pct:+.1f}%)"
        f"{thesis_note}{date_note}"
    )
```

**Step 2: Update CIO review prompt**

Add to the CIO challenge prompt:
```
For each position, specifically evaluate:
- Is the ORIGINAL ENTRY THESIS still valid given what has changed since entry?
- Has the thesis played out (exit target reached)?
- Have conditions changed that invalidate the thesis?
```

**Step 3: Run tests, commit**

```
git commit -am "feat: position reviewer references original entry thesis for each position"
```

---

## Summary Checklist

| # | Task | Phase | Status |
|---|------|-------|--------|
| 1 | Enrich TradeProposal (conviction, strategy_tag, signal_snapshot) | 1 | ☐ |
| 2 | Enrich trade logging (reasoning, signal context) | 1 | ☐ |
| 3 | Realized PnL per closed trade | 1 | ☐ |
| 4 | TradeOutcomeTracker | 2 | ☐ |
| 5 | Feed outcomes into PM prompts | 2 | ☐ |
| 6 | Signal quality scoring | 2 | ☐ |
| 7 | PM outputs conviction score | 3 | ☐ |
| 8 | Conviction-aware risk agent | 3 | ☐ |
| 9 | Market regime classifier | 3 | ☐ |
| 10 | Dynamic limits (regime + conviction) | 3 | ☐ |
| 11 | Cross-pod intelligence memos | 4 | ☐ |
| 12 | CIO performance attribution | 4 | ☐ |
| 13 | Position reviewer gets entry thesis | 4 | ☐ |

**Expected outcome:** Agents that learn from mistakes, size bets by conviction, adapt to market conditions, and share intelligence — directly improving PnL through better decision quality at every level of the system.
# Current Sprint: Stabilization And Hardening

Goal: make the existing platform easier to install, verify, operate, and trust before adding more trading intelligence.

Checklist:
- [x] Align repo documentation with the current product: 4 active pods, static dashboard served from `web/dist`, `python run.py` on port 8001, and correct test commands.
- [x] Make dependency metadata installable from a fresh checkout by completing `pyproject.toml` and adding `requirements.txt`.
- [x] Harden test isolation so normal pytest runs do not use `.env` live credentials and do not rely on blocked Windows temp directories.
- [x] Replace the placeholder `/api/audit` route with real recent audit-log data.
- [x] Add production controls around dashboard session start/stop and document the deployment switches.
- [x] Verify the focused backend, web, and test-isolation suites.

Review:
- Rewrote `README.md` around the active 4-pod Python/static-dashboard product.
- Added complete install metadata in `pyproject.toml` and `requirements.txt`.
- Updated Docker to serve the checked-in `web/dist` dashboard without requiring a missing package lock.
- Hardened pytest isolation: no live Alpaca unless `RUN_LIVE_ALPACA_TESTS=1`; workspace-local temp fixtures avoid Windows ACL failures.
- Implemented `/api/audit` from DuckDB `AuditLog.recent_messages`.
- Guarded session start/stop in production unless `MISSION_CONTROL_ENABLE_SESSION_CONTROL=true`.
- Verification: `python -m pytest tests -q --tb=short --disable-warnings -o cache_dir="C:\Users\PW1868\Agentic HF\tmp_pytest_cache_full3"` passed with 529 passed, 2 skipped.

Product-readiness audit:
- Ready enough for continued backend/product work: dependency metadata is installable, the static dashboard entrypoint matches Docker/uvicorn, normal tests are isolated from live LLM and Alpaca credentials, `/api/audit` now returns real data, and production session controls fail closed.
- Demo caveat: manual browser smoke was intentionally skipped in this pass. Before showing the product externally, run the dashboard locally and click through Command, Intelligence, Research, Performance, Execution, Operations, Risk, Attribution, Macro Indicators, and Reports.
- Remaining readiness gaps: `/api/nav-history`, `/api/execution-quality`, `/api/benchmarks`, and `/api/correlation` need explicit REST tests if they are part of the shipped dashboard contract; the dashboard still uses browser alerts for disabled session controls instead of an in-app status banner; `/health` does not yet expose broker/research/LLM dependency readiness; production deployment docs should include the admin PowerShell `PATH` repair note for this workstation only, not as a product requirement.
- Recommended next implementation pass: add a system health panel with Alpaca/FRED/Polymarket/LLM status, replace start/stop alerts with an inline operational banner, and add endpoint tests for the remaining dashboard data APIs.

---

# Current Task - Empty Diagnostics Dashboards

Goal: Operations Health, Execution Broker, Execution Quality, and Decision Audit should always show useful local/session data quickly. Slow Alpaca or reconciliation calls must not leave the dashboard blank or stuck at UNKNOWN.

- [x] Stop Operations Health from blocking on live broker/network reconciliation.
- [x] Make broker reconciliation bounded by timeouts and return local position rows even when Alpaca is slow.
- [x] Keep execution reconciliation from blocking the Broker tab.
- [x] Make Execution Quality show fill coverage, including when slippage was not captured yet.
- [x] Make Decision Audit fall back to available order/trade activity instead of showing zero events.
- [x] Add focused regression tests and run frontend/backend checks.

Review:
- Operations Health now uses local accountant/NAV state plus cached broker status, so a slow Alpaca call cannot blank the whole panel. Broker reconciliation now runs account, position, and open-order reads with bounded timeouts and still returns local-only rows when broker data is unavailable. Execution reconciliation is also bounded from the web route and frontend fetches abort instead of hanging. Execution Quality now shows fill coverage even when slippage was not captured, and Decision Audit falls back to local order/fill/activity events when the server audit endpoint is empty or unavailable. Verified with `pytest tests\unit\test_reconciliation.py tests\integration\test_web_service.py -q`, `pytest tests\integration\test_web_dashboard_e2e.py -q`, `pytest tests\unit\test_crypto_price_refresh.py tests\unit\test_nav_store.py -q`, `node --check web\dist\dashboard.js`, and Python `py_compile`.

# Reliability Sprint: State Health, Broker Truth, Decision Audit

**Goal:** Make the dashboard tell the truth about capital/NAV health, broker execution blockers, and every trade decision path before adding more strategy intelligence.

## Plan

- [x] Add a backend state-health summary: pod starting capital, current NAV, broker/local match state, NAV history repair counts, and last valid NAV timestamps.
- [x] Extend broker/execution diagnostics so rejected orders explain symbol support, time-in-force/order format, buying power/account state, and exact broker/preflight reason where available.
- [x] Add a backend decision-audit endpoint that turns recent PM/risk/governance/order events into an explainable decision trail.
- [x] Add dashboard views for System Health, Broker Truth, and Decision Audit without cluttering the existing workflow.
- [x] Add focused tests for the new API payloads and run frontend/backend verification.

## Review

Added `NavStore.health_summary()` plus `SessionManager.get_state_health()` and `/api/state-health`, so the dashboard can show pod starting capital, current NAV, cash/invested, position counts, NAV history repair counts, and broker/local mismatch status. Added `/api/decision-audit`, which combines recent PM activity, governance events, and order lifecycle updates into a single decision trail. The Operations tab now has a `Health` subtab, the Execution tab now has a `Decision Audit` subtab, and the Broker panel now includes recent rejected/pending execution diagnostics with next-action hints. Verification passed: `node --check web\dist\dashboard.js`, Python compile for the edited backend modules, `pytest tests\unit\test_nav_store.py -q`, `pytest tests\integration\test_web_service.py -q`, and `pytest tests\integration\test_web_dashboard_e2e.py -q`.

---

# Performance NAV Seed Baseline Fix

**Goal:** Stop the all-time Performance chart from showing pods as if they started at `$100` when the intended pod allocation is `$1000`.

## Plan

- [x] Inspect raw NAV history to confirm whether `$100` is a data issue or a chart issue.
- [x] Repair leading all-cash `$100` seed snapshots to the inferred funded baseline before history is returned.
- [x] Add a frontend safety pass so already-running servers do not plot bad seed rows after a refresh.
- [x] Change the remaining `start_live_session()` product default from `$100` to `$1000`.
- [x] Add regression tests and run focused dashboard/backend checks.

## Review

- Confirmed `data/state.db` had historical all-cash seed rows at `$100` for equities, FX, and crypto before the first real funded snapshots around `$1000`.
- Added `NavStore` repair logic that rebases only leading low all-cash seed placeholders to the inferred funded baseline; true later drawdowns are still preserved.
- Extended startup repair so those seed rows are rewritten on the next Python restart, and added a frontend fallback that repairs the plotted API history immediately after a static refresh.
- Changed `SessionManager.start_live_session()` default and Alpaca hydration fallback from `$100` to `$1000`.
- Verification passed: `pytest tests\unit\test_nav_store.py -q`, `pytest tests\integration\test_web_dashboard_e2e.py -q`, `pytest tests\integration\test_web_service.py -q`, `node --check web\dist\dashboard.js`, Python compile, and startup import check.

---

# Performance Graph Visibility Fix

**Goal:** Restore visible, readable NAV and drawdown graphs in the Performance tab after the chart containers collapsed into short strips.

## Plan

- [x] Inspect Performance chart CSS and Chart.js render/update paths.
- [x] Prevent chart containers from shrinking inside the scrollable dashboard column.
- [x] Force NAV/drawdown charts to resize after tab activation, period changes, and benchmark/firm toggles.
- [x] Cache-bust the static assets so refreshes pick up the layout fix.
- [x] Run frontend syntax and dashboard integration checks.

## Review

- Fixed `.chart-wrap` so it has a real minimum height and does not flex-shrink inside the Performance tab.
- Gave the NAV and drawdown charts explicit Performance-tab heights, with a smaller fallback for short viewports.
- Added a chart resize/refresh helper so Chart.js recalculates canvas size after the Performance tab becomes visible or a chart option changes.
- Cache-busted `styles.css`, `tower.js`, `motion.js`, and `dashboard.js`.
- Verification passed: `node --check web\dist\dashboard.js` and `pytest tests\integration\test_web_dashboard_e2e.py -q`.

---

# Current Sprint: Holding Detail Expandability + Frozen NAV Charts

**Goal:** Make holding detail drilldowns readable for long fill/PM reasoning histories, and prevent Performance NAV/drawdown charts from collapsing to zero when the backend/server stops or sends empty NAV snapshots.

- [x] Trace current holding detail modal rendering and chart history update paths
- [x] Make fill timeline and PM reasoning entries clearly expandable/collapsible with readable full text
- [x] Keep the modal usable when opening another holding while a previous API request is still returning
- [x] Preserve last valid pod/firm NAV values instead of writing zero chart points during inactive/disconnected states
- [x] Run focused frontend checks and update review notes

**Review:** The open-holding modal now uses a wider, stable layout with full-row collapsed cards, readable scrollable text areas inside each expanded fill/PM reasoning item, and explicit Expand all / Collapse all controls for the fill timeline and PM reasoning history. Modal API responses are token-guarded, so a late response from one holding cannot overwrite another holding after the user clicks elsewhere; Escape also closes the modal. NAV history ingestion and live pod-summary merging now preserve the last positive pod/firm NAV snapshot when inactive/disconnected/empty updates report zero, so Performance and Drawdown charts pause at the last valid values instead of collapsing to a zero baseline. Verification passed: `node --check web\dist\dashboard.js`, `pytest tests\integration\test_web_dashboard_e2e.py -q`, and `pytest tests\integration\test_web_service.py -q`. Browser session reloaded the live dashboard and confirmed the updated cache-busted assets loaded, but the in-app browser click bridge could not reliably dispatch a click into the holdings table for a final modal screenshot.

---

# Current Sprint: Broker Preflight Layer

**Goal:** Catch non-executable broker orders before they hit Alpaca, explain the exact reason in logs/dashboard, and feed a clean failure stage back through the execution contract.

- [x] Add Alpaca asset capability lookup with an in-memory cache
- [x] Validate tradability, symbol support, crypto time-in-force, quantity, buying power, and short/fractional constraints before submit
- [x] Return structured preflight rejection payloads with `stage=preflight`
- [x] Surface rejection stage and reason in the Execution trade log
- [x] Add focused tests for unsupported assets, non-tradable assets, crypto TIF, buying power, and stage propagation
- [x] Run focused verification

**Review:** Added an Alpaca broker-preflight layer that looks up and caches asset capabilities before order submission, rejects unsupported/non-tradable/inactive symbols early, blocks invalid quantity/fractional/short constraints, and checks buying power when the execution path has an estimated price. Rejections now return structured payloads with `stage=preflight`, `reason`, `rejection_detail`, and `reason_code`; later broker status and submit failures keep their own stages. Execution traders preserve the stage through `OrderResult`, WebSocket order updates, and recent execution feedback, and PM prompts now include recent broker/preflight failures so they can adapt instead of repeatedly proposing dead orders. The dashboard Execution table now includes Stage plus Reason. Verification passed with `pytest tests\integration\test_alpaca_retry.py tests\integration\test_accountant_sync.py -q`, `pytest tests\integration\test_web_dashboard_e2e.py -q`, `node --check web\dist\dashboard.js`, and Python compile checks for the edited adapter, execution traders, PM agents, and execution model.

---

# Current Sprint: Alpaca Rejection Visibility

**Goal:** Make rejected broker orders explain themselves in the execution log/dashboard, avoid presenting missing mandate allocation as 0%, and verify whether Alpaca supports crypto trading.

- [x] Preserve Alpaca submit/order-status rejection messages in adapter results
- [x] Propagate broker rejection reasons through execution traders and dashboard order updates
- [x] Show rejection reasons in the Execution trade log
- [x] Replace missing mandate allocation logging with unknown/unavailable wording
- [x] Use crypto-compatible Alpaca time-in-force for crypto pairs
- [x] Run focused verification

**Review:** Alpaca adapter rejections now carry the broker/error text through `reason`, `rejection_reason`, and `rejection_detail`; submitted orders that later move to rejected/canceled/expired also return the broker status and reason instead of timing out as generic pending. Pod execution traders now preserve that reason in `OrderResult`, WebSocket order updates, and agent activity details. The Execution trade log now has a Reason column for rejected/pending order diagnostics. Missing mandate allocation now logs as unknown/unavailable rather than 0%. Crypto-looking Alpaca pairs now submit with `gtc` time-in-force, which matches Alpaca crypto order requirements. Verification passed with adapter/accountant integration tests, dashboard integration tests, JS syntax check, and Python compile of the edited execution modules.

---

# Current Sprint: Performance Chart Controls

**Goal:** Let the first Performance chart show/hide firm NAV and filter the displayed period to all time, 6M, 3M, 30D, 7D, or 24H.

- [x] Replace the minute-based chart buttons with product-facing period controls
- [x] Add a firm NAV visibility toggle that updates the chart and expanded modal
- [x] Keep drawdown and CSV export behavior compatible with the selected history state
- [x] Load enough NAV history on startup for longer period selections
- [x] Run focused dashboard verification

**Review:** The first Performance NAV chart now has period controls for ALL, 6M, 3M, 30D, 7D, and 24H plus a Firm NAV checkbox that also refreshes the expanded chart modal. The chart, drawdown chart, and NAV CSV export all respect the selected period. Startup now requests a larger NAV history window, downsampling protects chart performance, and the stored NAV history API now includes per-pod NAV values so longer windows can show pod lines after the app restarts. The history query now uses an indexed timestamp lookup rather than loading the full table before trimming, and unit coverage locks that each selected timestamp keeps all pod NAVs. Verification passed with JS syntax checks, Python compile, focused NavStore unit tests, and the focused web dashboard/service integration tests.

---

# Current Sprint: Position Detail Thesis Auditability

**Goal:** Make open-position detail usable for trade review: no clipped thesis text, every fill/expansion has its own visible reasoning, and future PM decisions produce tradeable, data-consistent entry theses.

- [x] Document the requested position-detail and PM-thesis fixes
- [x] Inspect current position modal, fill metadata, and PM thesis generation
- [x] Make fill timeline entries collapsible with full per-fill thesis/reasoning
- [x] Remove UI history caps and make long thesis/reasoning blocks scrollable
- [x] Backfill all buy fills for hydrated current positions, not just the earliest buy
- [x] Strengthen PM thesis instructions and token budget for complete tradeable theses
- [x] Add focused tests for fill-detail metadata and thesis quality guardrails
- [x] Run focused verification

**Review:** Position detail now renders each fill/expansion as a collapsible entry with its own full thesis/reasoning, long thesis blocks scroll instead of being clipped, and PM reasoning history no longer caps at 10 visible entries. The backend now exposes all historical BUY fills for a current holding, including recovered thesis/reasoning metadata where available. PM prompts and thesis verification now require tradeable sections covering drivers, entry trigger, invalidation, risk, instrument fit, and asset-specific checks such as real yields, breakevens, Fed reaction, USD, positioning/flows, central-bank demand, and geopolitical risk as a conditional catalyst rather than a standalone reason. Verification passed with JS syntax checks, Python compile, focused unit tests, web-service tests, dashboard integration tests, and direct served-asset checks from the running dashboard.

---

# Current Sprint: Thesis Quality Gate + Lifecycle Monitor

**Goal:** Treat every entry thesis as a live contract: reject weak new BUY theses before execution, continuously review open-position theses against current macro/news/regime conditions, and block expansions unless the PM explicitly revalidates or rewrites the thesis.

- [x] Add a reusable thesis lifecycle reviewer with health statuses (`valid`, `watch`, `challenged`, `broken`, `needs_pm_rewrite`)
- [x] Store entry-time macro/thesis context with fills and open-position metadata
- [x] Run lifecycle review before PM decisions and inject thesis health into PM prompts
- [x] Convert thesis verification into a hard BUY gate after revision attempts fail
- [x] Block adds to existing positions when thesis health is challenged/broken unless the PM provides a fresh expansion thesis
- [x] Expose thesis health/monitoring context in position detail and open-position APIs
- [x] Add focused tests for lifecycle review, hard gate behavior, and API/dashboard visibility
- [x] Run focused verification

**Review:** Added `src/core/thesis_lifecycle.py` to score open-position theses against stored entry assumptions, current macro regime, price action, time-bound max-hold limits, and precious-metals-specific real-yield/USD monitors. `PodRuntime` now reviews open theses before PM decisions, injects lifecycle health into PM prompts, stores lifecycle state on accountant metadata, blocks BUYs when the thesis verifier still fails after revision attempts, and blocks adds to existing positions unless the PM writes a fresh expansion thesis. Execution metadata now stores entry macro regime and thesis review context with fills. Position APIs and the detail modal expose thesis health, issues, monitor points, and add-block status. Verification passed: Python compile checks, `node --check web/dist/dashboard.js`, focused unit tests for thesis lifecycle/verifier/runtime/accountant APIs, and dashboard/web integration tests.

---

# Current Sprint: Cross-Asset Thesis Lifecycle Coverage

**Goal:** Make thesis lifecycle review apply across all four active pods, not just the GLD/precious-metals failure that triggered the work.

- [x] Add asset-class thesis monitor profiles for equities, FX, crypto, and commodity sub-themes
- [x] Keep GLD as a regression example, but add tests for all four pods
- [x] Ensure missing asset-class monitors creates a review/watch signal instead of silently passing
- [x] Run focused lifecycle/runtime verification

**Review:** GLD is now only the regression example for the original false real-rate failure. The lifecycle reviewer now classifies open theses by pod/theme and adds monitors for equities, FX, crypto, and commodity sub-themes including energy, industrial metals, agriculture, broad commodities, and precious metals. The PM thesis standard now lists the required asset-class disciplines for all active pods. The thesis verifier now treats missing asset-class coverage as a hard failure for new active trades, so a vague FX/crypto/equity/commodity trade cannot pass just because it has THESIS/ENTRY/RISK labels. Verification passed with Python compile checks and focused lifecycle/verifier/runtime unit tests.

---

# Current Sprint: Factor-Aware Commodities Risk Controls

Goal: prevent the commodities pod from stacking multiple instruments that share the same economic driver, while preserving the ability for researchers to discover new opportunities from news and market context.

Checklist:
- [x] Add a factor exposure model that can represent dynamic themes such as gold beta, oil supply shock, natural gas, industrial metals, soft commodities, rates sensitivity, and broad risk-off hedges.
- [x] Let researchers/LLM enrichment propose or classify newly discovered tickers into factors, but require deterministic validation and fallback classification before any symbol becomes tradeable.
- [x] Compute effective factor exposure from current positions plus proposed orders, including correlated instruments like GLD, GDX, GDXJ, SLV, and miners under shared precious-metals stress exposure.
- [x] Enforce commodities pod risk rules before execution: no new buys when gross exposure exceeds pod NAV, no new buys when cash is negative, resize or reject trades that breach factor concentration limits, and always allow risk-reducing sells.
- [x] Add CRO-level aggregation so shared factors are visible across pods, not only inside commodities.
- [x] Add PM/risk context so the PM sees current factor exposure and "reduce-only" states before proposing trades, while rule-based risk remains the final authority.
- [x] Add dashboard visibility for factor exposure, breaches, rejected/resized orders, and reduce-only status.
- [x] Add tests proving correlated gold/gold-miner exposure is blocked, sells are allowed, newly discovered symbols require classification, and pod gross exposure cannot exceed realized NAV.

Review:
- Added `src/core/factor_exposure.py` with static and LLM-validated dynamic factor profiles, effective exposure weights, factor limits, gross exposure checks, and PM-readable formatting.
- Commodities researcher now asks LLM universe reviews for factor classifications on newly discovered symbols and stores validated profiles in pod namespace.
- Commodities risk now blocks unclassified buys, blocks all risk-increasing trades in reduce-only mode, caps sells to avoid flipping exposure, enforces gross exposure <= current pod NAV, and rejects/resizes trades that would breach shared factor limits such as gold beta or precious metals.
- PodRuntime injects commodity factor exposure and risk mode into PM sizing context and PodSummary risk metrics.
- CRO now alerts on pod-level factor breaches and firm-wide factor concentration.
- Dashboard Risk tab now includes a Commodity Factor Exposure table sourced from live pod summaries.
- Verification: focused factor/risk tests passed, web service tests passed, dashboard integration tests passed, MVP4 trading-cycle tests passed, and full pytest output reported `539 passed, 2 skipped` before the shell wrapper timed out after the long run.

---

# Current Sprint: UI P&L Percent Normalization

**Goal:** Whenever the dashboard shows a dollar P&L, also show the percentage return relative to the relevant notional/capital base when that base is available.

- [x] Add shared frontend helpers for P&L percent formatting against position notional, entry notional, or pod capital
- [x] Update open-position, closed-trade, performance, attribution, risk/report, and detail-modal P&L displays
- [x] Keep existing color/sign behavior and avoid showing misleading percentages when the denominator is missing or zero
- [x] Run dashboard syntax/integration verification

**Review:** Added shared dashboard helpers so dollar P&L can render as `$ P&L (return %)`. Open positions use entry notional, closed trades/closed positions use entry notional, pod/firm daily P&L uses current NAV, and cumulative NAV P&L uses starting/allocated capital. Updated the main dashboard tables/cards, position and closed-position modals, outcome stats, attribution, review holdings snapshot, and the 3D tooltip. Cache-busted `dashboard.js` and `motion.js`. Verification passed: `node --check web/dist/dashboard.js`, `node --check web/dist/motion.js`, `tests/integration/test_web_dashboard_e2e.py`, and `tests/integration/test_web_service.py`.

---

# Current Sprint: Governance Allocation Display + Closed Trade Dates

Goal: make the dashboard distinguish assigned capital from current NAV, and make closed-position timing visible without relying on timestamp slicing in the browser.

Checklist:
- [x] Confirm governance Capital Allocations was mixing current NAV dollars with allocation percentages.
- [x] Change allocation tiles to show mandate/start-capital allocation dollars and percentages.
- [x] Add current NAV as secondary context on each allocation tile so losses/profits remain visible without being mislabeled as allocation.
- [x] Add explicit `entry_date` and `exit_date` fields to closed-trade API rows.
- [x] Update closed-trade and closed-position table rendering to use date aliases with timestamp fallback.
- [x] Run focused verification.

Review:
- Governance allocation tiles now show allocation dollars and allocation percent from complete mandate weights when present, otherwise from starting-capital shares. For four `$1000` starting pods with no complete mandate override, the tiles show `$1000 / 25%` each, with current NAV shown separately.
- Closed-trade API rows now include `entry_date` and `exit_date`; closed trade and closed position tables render those columns from aliases with timestamp fallback.
- Verification passed: `node --check web/dist/dashboard.js`, Python compile for `src/mission_control/session_manager.py`, `tests/unit/mission_control/test_closed_trades_api.py`, `tests/integration/test_web_service.py`, and `tests/integration/test_web_dashboard_e2e.py`.

---

# Current Sprint: Performance/Risk Dashboard Reconciliation

Goal: make Performance numbers reconcile with the right ledger and keep Commodity Factor Exposure visible even when the backend factor report is absent from the WebSocket payload.

Checklist:
- [x] Trace Performance tab sources: Pod Returns uses current NAV including open/unrealized P&L; Trade Outcomes used the partial in-memory outcome tracker.
- [x] Trace Risk tab sources: Commodity Factor Exposure expected `factor_exposures`, but the live WebSocket snapshot did not include that report.
- [x] Change Performance outcome cards to compute closed-trade stats from `/api/trades/closed`, the same complete source used by the closed-trades table.
- [x] Rename the section to Closed Trade Outcomes and show NAV P&L beside Closed P&L so users can reconcile it with Pod Returns.
- [x] Add a dashboard fallback that maps open commodity positions into risk factors when backend factor exposure is missing.
- [x] Run focused verification.

Review:
- Performance closed-trade stats now build from `/api/trades/closed`, so counts and closed P&L use the same complete source as the execution closed-trades table.
- Closed P&L is explicitly separate from NAV P&L, which includes open positions and reconciles with Pod Returns.
- Risk Commodity Factor Exposure now prefers backend `factor_exposures`, but falls back to mapping open commodity positions such as GLD, GDX, GDXJ, and SLV into shared factors if the WebSocket payload is missing the report.
- Verification passed: `node --check web/dist/dashboard.js`, served `dashboard.js` contains the new fallback code, `tests/integration/test_web_dashboard_e2e.py`, and `tests/integration/test_web_service.py`.

---

# Current Sprint: LLM Runtime Default

Goal: make LLM-backed PM/CIO/CEO decisions the default runtime behavior again.

Checklist:
- [x] Correct the product assumption: LLM calls are core behavior, not an optional local demo feature.
- [x] Change `run.py` so `MISSION_CONTROL_USE_LLM` defaults to enabled.
- [x] Keep `MISSION_CONTROL_USE_LLM=false` as an explicit tests/debugging opt-out only.
- [x] Verify runtime environment behavior.

Review:
- Verified behavior: with `.env` keys present and `MISSION_CONTROL_USE_LLM` unset, runtime would not disable LLM calls and both OpenRouter/OpenAI keys remain available.
- Verification passed: `python -m py_compile run.py src/core/llm.py` and an environment check confirming `would_disable_llm=False`.

---

# Current Sprint: Closed Positions Table Scrolling

**Goal:** The Closed Positions table should scroll horizontally and vertically inside its own panel.

- [x] Put the Closed Positions table inside a two-axis scroll wrapper
- [x] Give the table a minimum width so horizontal scrolling is available on narrow panels
- [x] Bound the table height so long closed-position histories scroll vertically without pushing the tab layout

**Review:** Added `tbl-wrap-biaxial` and `closed-pos-scroll` styling for the Closed Positions tab only. The header remains in the tab while the table body area can scroll independently in both axes.

---

# Current Sprint: Entry Thesis Reliability

**Goal:** Every newly entered trade must carry a non-empty entry thesis from the PM decision into the accountant, APIs, and dashboard.

- [x] Trace PM proposal -> execution metadata -> accountant -> positions API
- [x] Make entry thesis an explicit fill/accountant field, while preserving existing reasoning audit fields
- [x] Add resilient fallbacks from stored reasoning for older positions with missing `entry_thesis`
- [x] Add focused tests for thesis persistence and API visibility
- [x] Run targeted verification and document the result

**Review:** Fixed the PM thesis handoff so active execution templates pass `entry_thesis` to the accountant/session log. The accountant now stores explicit thesis metadata, falls back to PM reasoning for old state, and exposes the same fallback through open-position and closed-trade APIs. Verified with syntax checks plus focused portfolio/runtime/API/web-service tests.

---

# Current Sprint: Governance NAV Display + Commodities Fresh Start

**Goal:** Make Governance capital cards match the operational NAV view, and prepare a commodities-only reset after the factor-correlation risk fix.

- [x] Inspect current Governance rendering and confirm the card headline is mandate allocation while NAV is only secondary text
- [x] Inspect commodities persisted state and quantify the legacy damage/history to reset
- [x] Change Governance cards so current NAV is the headline and allocation is context
- [x] Prepare a commodities-only reset that backs up state, clears local commodities holdings/trade history, and resets NAV/cash to `$1000`
- [x] Confirm whether to also close the related Alpaca paper commodities positions before running the destructive reset
- [x] Verify dashboard/static checks after the UI patch

**Notes:** Local memory currently shows commodities NAV around `$857.50`, realized P&L around `-$138`, open GLD/SLV dust plus a near-zero GDXJ artifact, and 44 commodities trade records. A true fresh start will not stick across restarts if Alpaca still contains commodity positions that the session hydrates back into the pod.

**Review:** Governance now labels the section as Capital Status and uses current NAV as the primary card value, with mandate allocation shown below as context. The commodities reset was applied with backups in `data/backups/`: local commodities NAV/cash is `$1000`, local commodities positions/trades/closed trades/outcomes/signal history were removed, legacy commodities NAV-history rows were deleted, and a fresh `$1000` reset NAV row was inserted. The Alpaca paper close initially exposed a `close_position` quantity-sign bug for short/negative holdings; fixed `AlpacaAdapter.close_position()` to send positive quantities, then verified GLD/SLV/GDXJ have no open Alpaca target positions. Verification passed: `node --check web/dist/dashboard.js`, `py_compile` for the reset script and adapter, memory/state checks, Alpaca dry-run verification, and startup logs showing commodities reconciled at `$1000` cash / `$0` invested.

---
# 2026-05-07 Sprint - Performance Chart + Crypto Rejections + Trade Log Cleanup

## Goal
Fix three live dashboard defects: performance charts going blank, crypto orders still showing only generic rejections, and the rejected trade-log view redundantly showing the closed-trades table.

## Plan
- [x] Make the performance chart resilient when `/api/nav-history` returns firm-only history with no per-pod series.
- [x] Keep drawdown/performance charts readable instead of plotting zero-value pod lines.
- [x] Remove the closed-trades panel from the execution trade-log rejected sub-filter; closed trades remain in the dedicated Closed tab.
- [x] Verify crypto order rejection payloads preserve broker stage/reason and add tests around the critical path.
- [x] Run focused frontend/backend tests.

## Review
- The Performance chart now skips unavailable pod series instead of plotting them at `$0`, automatically falls back to a firm-NAV line when the backend only has firm-level history, and freezes outage snapshots that collapse from normal firm NAV to the `$400` placeholder, including explicit placeholder pod NAVs such as `$100` per pod. The drawdown chart also falls back to available history instead of staying empty. The Execution trade log no longer embeds the duplicate Closed Trades table, so the Rejected filter only shows order lifecycle rows. Crypto rejection diagnostics now prefer specific broker/API messages over generic `Order rejected`; I confirmed Alpaca returns `invalid crypto time_in_force` for the old crypto order format and the checked-in adapter uses crypto `gtc` time-in-force. Verification passed: `node --check web\dist\dashboard.js`, `pytest tests\test_execution.py tests\integration\test_alpaca_retry.py -q`, `pytest tests\integration\test_web_dashboard_e2e.py -q`, `pytest tests\integration\test_web_service.py -q`, and a startup import check for `SessionManager` plus `AlpacaAdapter`.
# Performance Benchmark Toggle Fix

**Goal:** Keep pod NAV performance readable by preventing the S&P 500 benchmark from forcing the chart onto the firm/index scale when the user is looking at pod-level NAV.

## Plan

- [x] Confirm how the S&P 500 benchmark is added to the first performance chart.
- [x] Add a dedicated S&P 500 visibility toggle, default off.
- [x] Rebase the benchmark to the visible chart basis when enabled so it does not distort pod NAV lines.
- [x] Update cache-busting and run frontend checks plus relevant dashboard tests.

## Review

- Fixed the benchmark scaling bug: S&P 500 was always rendered and was using firm NAV scale even when Firm NAV was hidden.
- Added a separate `S&P 500` checkbox. It defaults off.
- When enabled, S&P 500 is shown as `S&P 500 (rebased)` and uses firm scale only if Firm NAV is visible; otherwise it uses the visible pod-level scale.
- Verified with `node --check web/dist/dashboard.js` and `pytest tests/integration/test_web_dashboard_e2e.py -q`.

---

# NAV, Broker Reconciliation, And Execution State Hardening

**Goal:** Make performance charts truthful after restarts, make broker/order failures diagnosable without guesswork, and reconcile stale execution state against Alpaca instead of leaving the dashboard in an ambiguous pending/rejected state.

## Plan

- [x] Map the current NAV write/read path, execution event path, and Alpaca read capabilities.
- [x] Add a server-side NAV quality gate so collapsed placeholder snapshots are not persisted as real losses.
- [x] Add a NAV history repair/read guard so existing bad restart rows are flattened or skipped for charts.
- [x] Add a broker reconciliation API/payload showing Alpaca account, broker positions, local positions, and differences.
- [x] Add a dashboard reconciliation panel so broker/local mismatches and rejection details are visible in plain English.
- [x] Add execution state reconciliation for stale pending orders using broker status where possible.
- [x] Preserve specific Alpaca rejection reasons in reconciled order rows.
- [x] Add focused regression tests for NAV collapse filtering, broker reconciliation shape, and order status reconciliation.
- [x] Run relevant backend and frontend checks.

## Review

- Implemented `NavStore` collapse detection, write-time freezing, read-time flattening, and explicit repair for existing restart artifacts.
- Added `SessionManager.get_broker_reconciliation()` plus REST endpoints for broker reconciliation and execution reconciliation.
- Added an Execution > Broker subtab that shows Alpaca account state, local-vs-broker position mismatches, open broker orders, and order reconciliation updates.
- Added tests for NAV placeholder freezing/repair, broker quantity mismatches, stale pending order updates, stale broker order cancellation, and the new web endpoints.
- Verified with `pytest tests/unit/test_nav_store.py tests/unit/test_reconciliation.py -q`, `pytest tests/integration/test_web_service.py -q`, `pytest tests/integration/test_web_dashboard_e2e.py -q`, and `node --check web/dist/dashboard.js`.

---
# Current Task - Crypto Position Price Staleness

Goal: Crypto fills should not appear as live holdings with frozen entry prices. Held crypto positions must refresh from a reliable quote source, broker/local symbol variants must match (`ETH/USD`, `ETHUSD`, `ETH-USD`), and stale prices should be visible in the UI/API.

- [x] Trace crypto order fill, quote, and position refresh paths.
- [x] Normalize crypto broker/feed/accountant symbols consistently.
- [x] Add quote fallback for held crypto prices when Alpaca position prices are stale or keyed differently.
- [x] Preserve last known mark-to-market prices on partial updates.
- [x] Expose quote source/staleness on open positions.
- [x] Add focused tests for crypto price refresh and stale handling.
- [x] Run syntax/unit/integration validation.

Review:
- Added crypto alias matching for `ETH/USD`, `ETHUSD`, `ETH-USD`, and base tickers so broker positions reconcile with local accountant positions.
- Added Yahoo Finance crypto fallback through `PriceService`, using normalized dashed symbols like `ETH-USD`.
- Changed `PortfolioAccountant.mark_to_market()` to preserve last prices for symbols absent from a partial refresh.
- Added quote source/staleness fields to open-position payloads and dashboard cells.
- Verified with focused crypto price tests, reconciliation tests, portfolio accountant tests, web service integration tests, JS syntax check, and Python compile check.

---

# Current Task - Crypto Holdings Live Mark Follow-Up

Goal: fix the remaining live issue where filled crypto holdings show `current_price == cost_basis` and `$0.00` P&L after ETH/SOL orders fill.

- [x] Confirm whether the positions API is serving stale crypto marks or the browser is only formatting them incorrectly.
- [x] Add a broker-native Alpaca crypto market-data quote path for open crypto holdings.
- [x] Make position price refresh independent from broker position reconciliation so a slow Alpaca positions call cannot freeze crypto marks.
- [x] Let `/api/positions` perform a short throttled refresh before returning holdings, while falling back immediately to cached local positions on timeout.
- [x] Add regression tests for broker-position failure plus positions endpoint refresh.
- [x] Expose separate entry and current notionals, and make the UI display current notional from `qty × current_price`.
- [x] Run focused backend verification and document the result.

Review:
- Confirmed the UI was not the root cause: the positions API itself was returning ETH/SOL `current_price == cost_basis`.
- Added Alpaca crypto snapshot/trade quote support using slash symbols such as `ETH/USD` and `SOL/USD`; a live Alpaca check returned real snapshot prices for both.
- Changed live position refresh so crypto quote fetching still runs even if broker position reconciliation is slow or unavailable.
- Added a throttled `/api/positions` refresh hook that returns cached local positions if the refresh times out, keeping Top Holdings responsive.
- Added `entry_notional`, `current_notional`, and `notional_basis` to position payloads. The Top Holdings table now prioritizes current notional rather than trusting a stale `notional` field.
- Verification passed: crypto price refresh unit tests, Alpaca retry/market-data tests, web service integration tests, reconciliation tests, and Python compile checks.

---

# Current Task - Execution Truth Layer

Goal: connect the already-existing PM decisions, gates, broker preflight, order updates, fills, and reconciliation into one explainable view per pod.

- [x] Audit existing execution/reconciliation/decision-audit coverage before adding new code.
- [x] Add runtime block records for thesis, lifecycle, data-quality, concentration, and risk rejections.
- [x] Preserve stable local order IDs alongside broker order IDs in execution events.
- [x] Add a backend execution-truth summary endpoint.
- [x] Surface execution truth in the Execution > Decision Audit tab.
- [x] Add focused tests for blocked trades, ID preservation, and endpoint shape.
- [x] Run verification and document results.

Review:
- Added `last_trade_block` / `trade_blocks` runtime records for universe, thesis, lifecycle, data-quality, concentration, and risk gates.
- Execution events now carry `local_order_id` and `broker_order_id` separately; reconciliation skips local-only pre-submit pending rows until a broker ID exists.
- Added `/api/execution-truth` and embedded the same payload in `/api/decision-audit`.
- Decision Audit now shows an Execution Truth table before the raw event trail.
- Verified with targeted pytest, dashboard JS syntax check, and Python compile check.

---

# Current Task - Research Feed Clarity

Goal: keep the LLM scoring cap as a cost/control guard, but make the dashboard feed feel live and stop implying the whole feed is limited to 25 sources.

- [x] Confirm whether the `25` limit is a display/source cap or a scoring-window cap.
- [x] Rename misleading feed counters and add display/source/freshness metadata.
- [x] Sort and dedupe feed items by actual publish/refresh time so new items surface immediately.
- [x] Make feed cards visually distinguish fresh/sentiment/source state without changing the research loop.
- [x] Run frontend verification and document results.

Review:
- The News Feed no longer labels the `25` cap as sources. It now shows total headlines, unique sources, and a separate `LLM Window` of 25 items per scoring cycle.
- Feed items are normalized, timestamp-sorted, deduped, and capped to the latest 100 displayed items while retaining up to 200 in the browser cache.
- The feed subbar now shows fresh item count and the top source mix, and fresh cards get a visible `NEW` treatment.
- Card badges now say `sentiment` or `raw`, avoiding an inaccurate claim that the dashboard can identify LLM-scored versus keyword-scored feed payloads.
- Static asset cache keys were bumped to `research-feed-20260508` so a browser refresh picks up the changed JS/CSS.
- Verification passed with `node --check web\dist\dashboard.js`.

---

# Current Task - Data Freshness Guardrails

Goal: prevent the dashboard, PM agents, risk checks, and execution path from treating stale/missing market data as reliable live state.

- [x] Map the current price freshness fields, order execution path, and diagnostics endpoints.
- [x] Add a reusable position data-quality report that flags stale prices, missing quote source, missing notionals, and unresolved broker/local mismatches.
- [x] Add a pre-trade data-quality gate so new BUY orders are blocked when the symbol has no fresh live price or current exposure data.
- [x] Surface the data-quality report in the dashboard health/diagnostics view.
- [x] Add a startup/live smoke-check endpoint or payload using the same diagnostics so failures are visible immediately.
- [x] Add focused tests for stale-price blocking and diagnostics shape.
- [x] Run backend/frontend verification and document the result.

Review:
- Added a pod-runtime data gate that blocks new BUY orders when the proposed symbol lacks a fresh positive price, quote source, or timestamp, while allowing SELL orders to reduce risk even when data is stale.
- Added `SessionManager.get_data_quality_report()` plus `/api/data-quality`, and included the same report inside `/api/state-health` so startup/health panels show market-data problems immediately.
- Updated Operations > Health to show market-data quality rows and recent data-gate blocks.
- Verification: `python -m pytest tests\unit\test_pod_runtime_entry_thesis.py tests\unit\test_reconciliation.py tests\integration\test_web_service.py -q` passed with 54 tests; `node --check web\dist\dashboard.js` passed; `python -m py_compile src\pods\runtime\pod_runtime.py src\mission_control\session_manager.py src\web\server.py` passed.
# Current Task - Research Feed v2

Goal: make the news/research feed durable and auditable so we can see source health, item relevance, affected pods/factors/tickers, and whether important items were acted on or ignored.

- [x] Map current research ingestion, dashboard feed, and state storage paths.
- [x] Add a DuckDB-backed research feed store with source-health tracking.
- [x] Normalize, dedupe, route, and persist RSS/news feed items centrally.
- [x] Expose a backend research-feed endpoint with source health, routing, and action-audit fields.
- [x] Add a dashboard view that shows the feed/system health without cluttering the existing News Feed.
- [x] Add focused tests and run frontend/backend verification.

---

## Review - 2026-05-08

- Added `ResearchFeedStore` for durable feed items, source health, routing metadata, and dedupe.
- Expanded the direct news feed list from 25 to 35 configured sources while keeping the LLM scoring window at 25 items per cycle for cost/latency control.
- Added `/api/research-feed`, including held-symbol matching, affected-pod routing, and action-audit status.
- Added Research > Feed Audit UI with source-health and routed-item panels.
- Verification passed: `python -m py_compile src\core\research_feed.py src\data\services\research_ingestion.py src\data\adapters\x_adapter.py src\mission_control\session_manager.py src\web\server.py`; `node --check web\dist\dashboard.js`; `python -m pytest tests\unit\test_research_feed_store.py tests\integration\test_web_service.py -q` with 45 passed. Pytest reported a non-blocking `.pytest_cache` permission warning.

---

# Current Task - Performance Attribution Clarity

Goal: make daily losses explainable from the dashboard by using one consistent NAV baseline and splitting P&L into realized closed-trade impact versus open-position impact.

- [x] Trace the current dashboard P&L calculations and available API data.
- [x] Replace stale pod-summary daily P&L displays with NAV-history based daily changes.
- [x] Correct firm cumulative P&L to use current firm NAV versus allocated starting capital.
- [x] Add realized-today and open unrealized P&L columns to Pod Returns.
- [x] Add top contributor attribution so losses can be traced to symbols and pods.
- [x] Run focused frontend/API verification and document the result.

Review:
- Operations and Performance now use the same NAV-history baseline for "today": latest valid NAV minus the first valid NAV snapshot for the current UTC day.
- Firm cumulative P&L now uses current firm NAV minus allocated starting capital, instead of the realized-only `firm_inception_pnl` counter.
- Pod Returns now shows `Today P&L`, `Realized Today`, and `Open P&L`, each with a percentage where the relevant notional/capital base is available.
- Pod Attribution now shows today's pod-level contribution plus top symbol contributors from open positions and today's closed trades.
- Cache keys were bumped to `perf-attribution-20260508`.
- Verification passed: `node --check web\dist\dashboard.js`; `python -m pytest tests\integration\test_web_dashboard_e2e.py -q` with 28 passed and one non-blocking `.pytest_cache` permission warning; live API sanity check showed firm today at about `-$5.65` with crypto open P&L the main current drag.

# Current Task - Task-Adaptive LLM Routing

Goal: replace the old single fallback model (`gpt-4o-mini`) with task-aware routing. The default should be GPT-5 mini, while higher-stakes reasoning paths can use stronger models through a central, configurable policy.

## Implementation Checklist

- [x] Add a central LLM task router in `src/core/llm.py`.
- [x] Default direct OpenAI calls to `gpt-5-mini` and prefer OpenAI when an OpenAI key is available.
- [x] Add stronger model tiers for PM decisions, thesis verification, governance, and position/loss reviews.
- [x] Keep OpenRouter as a fallback/provider option and preserve environment overrides.
- [x] Mark current LLM call sites with the right task labels.
- [x] Add focused tests proving default, strong, and task-specific model selection.
- [x] Run targeted verification and document results here.

## Review Notes

- Implemented task-aware routing in `src/core/llm.py`: default OpenAI calls now use `gpt-5-mini`, stronger reasoning tasks use `gpt-5`, and position/loss review tasks use `gpt-5.2` with automatic fallback to lower tiers if a model is unavailable.
- LLM call sites now pass task labels for PM decisions/revisions, thesis verification, theme scanning, sentiment scoring, research, CEO/CIO governance, allocation, and position review.
- Kept OpenRouter support as fallback/provider option. Runtime overrides are available through `LLM_PROVIDER_ORDER`, `OPENAI_MODEL_DEFAULT`, `OPENAI_MODEL_STRONG`, `OPENAI_MODEL_FRONTIER`, and task-specific variables like `OPENAI_MODEL_PM_DECISION`.
- Verification: `py_compile` passed for modified Python files; `tests/unit/test_llm_controls.py` passed (7 tests); `tests/unit/test_llm_controls.py tests/test_sentiment_pipeline.py tests/unit/test_theme_scanner.py` passed (60 tests); `tests/agents/test_ceo_cio_agents.py tests/agents/test_cro_governance.py` passed (23 tests). Pytest still reports the existing `.pytest_cache` access warning on Windows.

---

# Current Task: Pod Loss Review / Risk Intervention Loop

**Goal:** When a pod has a meaningfully bad day or one position drives an outsized loss, the system should explain what happened, ask for a PM/CRO/CIO style review, and block new risk until the review state clears.

## Implementation Checklist

- [x] Add a reusable loss-review evaluator for all four pods and all asset classes.
- [x] Trigger the evaluator after mark-to-market and before pod PM decisions, so restrictions can affect the same iteration.
- [x] Store each pod's active review and restriction in its namespace.
- [x] Block risk-increasing orders in `PodRuntime` when a pod is in reduce-only / paused mode, while still allowing sells or other risk-reducing orders.
- [x] Expose active and historical loss reviews through REST/WebSocket state.
- [x] Add a Risk tab panel showing daily loss, top contributors, PM defense prompt, CRO action, CIO decision, and current restriction.
- [x] Add focused tests for all-pod loss detection and runtime trade blocking.
- [x] Run targeted verification and document results here.

## Review Notes

- Added an asset-class-agnostic loss-review evaluator in `src/core/loss_review.py` that flags watch/restricted/paused states from daily NAV loss and single-position NAV impact. The session manager now evaluates it after mark-to-market and before PM decisions, stores the active review/restriction in each pod namespace, persists the history in memory, and broadcasts it through the web snapshot/API.
- `PodRuntime` now honors the active loss-review restriction: reduce-only/pause mode blocks new risk-increasing orders but still allows risk reductions. PM prompts for equities, FX, crypto, and commodities now receive the active loss-review text so the LLM is explicitly asked to defend, trim, exit, or wait rather than blindly add risk.
- The Risk tab now has a Loss Review / Risk Intervention panel with pod status, daily P&L, open/realized impact, top contributors, CRO action, CIO decision, and the PM defense prompt.
- Verification passed: `python -m pytest tests\unit\test_loss_review.py -v`, `python -m pytest tests\unit\test_pod_runtime_entry_thesis.py -v`, `python -m pytest tests\integration\test_web_service.py -v` with 44 passing tests, `node --check web\dist\dashboard.js`, and targeted `py_compile` for the backend/runtime/PM prompt files. Pytest emitted a non-blocking `.pytest_cache` permission warning.

---
