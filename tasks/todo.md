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
