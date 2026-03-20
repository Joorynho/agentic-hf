# Intelligence Upgrade — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add 8 intelligence features: PM memory persistence, CIO data scorecard, position aging enforcement, multi-timeframe context, source attribution scoring, firm-wide concentration limits, live headline alerts, and CIO-driven capital reallocation.

**Architecture:** Features are ordered by dependency — standalone features first (Tasks 1-4), then features that build on them (Tasks 5-8). All backend changes follow existing patterns: AuditLog for DuckDB persistence, PodSummary for cross-pod data, EventBus for alerts.

**Tech Stack:** Python 3.12, Pydantic v2, DuckDB (via AuditLog), asyncio, FastAPI WebSocket, vanilla JS frontend.

---

## Architecture Notes

- `AuditLog` wraps DuckDB — use `self._conn.execute(DDL)` for new tables, `log_event()` for rows.
- `PortfolioAccountant._entry_metadata[symbol]` stores `signal_snapshot`, `max_hold_days`, `conviction`, `stop_loss_pct`, `take_profit_pct` per open position.
- `PodSummary.exposure_buckets` = `list[PodExposureBucket]` with `asset_class`, `direction`, `notional_pct_nav`. Already broadcast.
- `compute_macro_score()` weights are hardcoded locals at lines ~188-195 in `src/core/scoring.py`.
- All 4 PM agents share the same template in `src/pods/templates/`. Each has `_decision_history: list[dict]` (capped at 5, in-memory).
- `SessionManager._pod_runtimes` holds all pod runtimes. `_pod_accountants` not a separate dict — access via `runtime._accountant`.
- Import pattern: always `from src.X.Y import Z` (absolute).
- Tests: `asyncio_mode = "auto"`, always mock `YFinanceAdapter._fetch_sync`.

---

### Task 1: PM Memory Persistence (DuckDB)

**Files:**
- Modify: `src/core/bus/audit_log.py`
- Modify: `src/pods/templates/equities/pm_agent.py` (and fx, crypto, commodities — same pattern)
- Create: `src/core/pm_memory.py`
- Test: `tests/integration/test_pm_memory.py`

**Step 1: Create `src/core/pm_memory.py`**

```python
"""Persistent PM decision memory backed by DuckDB."""
from __future__ import annotations
import json
import math
from datetime import datetime, timezone
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.core.bus.audit_log import AuditLog

_TABLE_DDL = """
CREATE TABLE IF NOT EXISTS pm_decisions (
    id          INTEGER PRIMARY KEY,
    pod_id      VARCHAR NOT NULL,
    ts          TIMESTAMP NOT NULL,
    action_summary VARCHAR,
    reasoning   VARCHAR,
    symbols     VARCHAR,  -- JSON list
    outcome     VARCHAR   -- 'win'/'loss'/'open'/'unknown', updated on close
)
"""

HALF_LIFE_DAYS = 7.0   # recency decay half-life
WINDOW_DAYS    = 30    # how far back to load
TOP_N          = 10    # max entries injected into PM prompt


class PMMemory:
    """Persist and retrieve PM decisions with recency-weighted recall."""

    def __init__(self, pod_id: str, audit_log: "AuditLog") -> None:
        self._pod_id = pod_id
        self._db = audit_log
        self._db._conn.execute(_TABLE_DDL)

    # ── Write ────────────────────────────────────────────────────────────────

    def record(self, action_summary: str, reasoning: str, symbols: list[str]) -> int:
        """Persist a new decision. Returns the row id."""
        self._db._conn.execute(
            "INSERT INTO pm_decisions (pod_id, ts, action_summary, reasoning, symbols, outcome) "
            "VALUES (?, ?, ?, ?, ?, 'open')",
            [self._pod_id, datetime.now(timezone.utc), action_summary,
             reasoning[:1000], json.dumps(symbols)],
        )
        row = self._db._conn.execute("SELECT last_insert_rowid()").fetchone()
        return row[0] if row else -1

    def mark_outcome(self, symbol: str, outcome: str) -> None:
        """Update outcome for the most recent open decision touching symbol."""
        self._db._conn.execute(
            "UPDATE pm_decisions SET outcome = ? "
            "WHERE pod_id = ? AND outcome = 'open' "
            "  AND symbols LIKE ? "
            "  AND id = (SELECT MAX(id) FROM pm_decisions "
            "             WHERE pod_id = ? AND outcome = 'open' AND symbols LIKE ?)",
            [outcome, self._pod_id, f'%"{symbol}"%', self._pod_id, f'%"{symbol}"%'],
        )

    # ── Read ─────────────────────────────────────────────────────────────────

    def recall(self) -> str:
        """Return a formatted memory block for injection into the PM prompt."""
        rows = self._db._conn.execute(
            "SELECT ts, action_summary, reasoning, symbols, outcome "
            "FROM pm_decisions "
            "WHERE pod_id = ? "
            "  AND ts >= NOW() - INTERVAL ? DAY "
            "ORDER BY ts DESC",
            [self._pod_id, WINDOW_DAYS],
        ).fetchall()

        if not rows:
            return ""

        now = datetime.now(timezone.utc)
        scored: list[tuple[float, str]] = []
        for ts, action, reasoning, syms_json, outcome in rows:
            age_days = (now - ts.replace(tzinfo=timezone.utc)).total_seconds() / 86400
            weight = math.exp(-math.log(2) * age_days / HALF_LIFE_DAYS)
            syms = ", ".join(json.loads(syms_json or "[]"))
            line = f"[{ts.strftime('%Y-%m-%d')}] {action} | {syms} | outcome={outcome} | {reasoning[:120]}"
            scored.append((weight, line))

        scored.sort(reverse=True)
        top = [line for _, line in scored[:TOP_N]]
        return "PAST DECISIONS (recency-weighted, last 30 days):\n" + "\n".join(top)
```

**Step 2: Write the failing test**

```python
# tests/integration/test_pm_memory.py
import pytest
from unittest.mock import MagicMock, AsyncMock
from src.core.pm_memory import PMMemory

@pytest.fixture
def audit_log(tmp_path):
    import duckdb
    conn = duckdb.connect(str(tmp_path / "test.db"))
    log = MagicMock()
    log._conn = conn
    return log

def test_record_and_recall(audit_log):
    mem = PMMemory("equities", audit_log)
    mem.record("BUY AAPL, MSFT", "Tech sector showing strength", ["AAPL", "MSFT"])
    mem.record("HOLD", "No changes — thesis intact", ["AAPL"])
    result = mem.recall()
    assert "BUY AAPL, MSFT" in result
    assert "PAST DECISIONS" in result

def test_outcome_update(audit_log):
    mem = PMMemory("equities", audit_log)
    mem.record("BUY AAPL", "Strong momentum", ["AAPL"])
    mem.mark_outcome("AAPL", "win")
    result = mem.recall()
    assert "win" in result

def test_empty_recall(audit_log):
    mem = PMMemory("equities", audit_log)
    assert mem.recall() == ""
```

**Step 3: Run test to verify it fails**
```bash
cd "C:/Users/PW1868/Agentic HF"
python -m pytest tests/integration/test_pm_memory.py -v
```
Expected: FAIL (module not found)

**Step 4: Create the module, run again**
Expected: PASS

**Step 5: Wire into PM agents**

In each PM agent (`src/pods/templates/equities/pm_agent.py` etc.), in `__init__`:
```python
from src.core.pm_memory import PMMemory
# after audit_log is available:
self._pm_memory: PMMemory | None = None  # lazy-init

def _get_memory(self) -> PMMemory | None:
    try:
        from src.core.bus.audit_log import AuditLog
        # AuditLog singleton via bus — get from namespace or construct
        audit_log = self._ns.get("audit_log")
        if audit_log and self._pm_memory is None:
            self._pm_memory = PMMemory(self._pod_id, audit_log)
        return self._pm_memory
    except Exception:
        return None
```

In `run_cycle()`, after building the PM prompt, prepend memory:
```python
memory_block = ""
mem = self._get_memory()
if mem:
    memory_block = mem.recall()
if memory_block:
    prompt = memory_block + "\n\n" + prompt
```

After a successful trade cycle, persist the decision:
```python
if mem and trades:
    symbols = [t.get("symbol", "") for t in trades]
    mem.record(action_summary, reasoning[:300], symbols)
```

**Step 6: Commit**
```bash
git add src/core/pm_memory.py tests/integration/test_pm_memory.py src/pods/templates/
git commit -m "feat: persist PM decision memory to DuckDB with recency-weighted recall"
```

---

### Task 2: CIO Scoring Model (75% reasoning + 25% data)

**Files:**
- Create: `src/agents/cio/pod_scorer.py`
- Modify: `src/agents/cio/cio_agent.py` (inject scorecard before LLM call)
- Test: `tests/unit/test_pod_scorer.py`

**Step 1: Create `src/agents/cio/pod_scorer.py`**

```python
"""Quantitative pod scoring for CIO governance (25% weight in decision)."""
from __future__ import annotations
from dataclasses import dataclass

WEIGHTS = {"sharpe": 0.40, "max_drawdown": 0.30, "win_rate": 0.20, "total_return": 0.10}

# Normalisation bounds (clamp then scale 0→1)
_SHARPE_RANGE    = (-2.0, 4.0)
_DD_RANGE        = (-0.50, 0.0)   # drawdown is negative; -50% worst, 0% best
_WINRATE_RANGE   = (0.0, 1.0)
_RETURN_RANGE    = (-0.30, 0.30)


def _norm(value: float, lo: float, hi: float) -> float:
    if hi == lo:
        return 0.5
    return max(0.0, min(1.0, (value - lo) / (hi - lo)))


@dataclass
class PodScore:
    pod_id: str
    score: float          # 0–1 composite
    sharpe_norm: float
    drawdown_norm: float
    win_rate_norm: float
    return_norm: float

    def scorecard_row(self) -> str:
        return (
            f"  {self.pod_id:<12} "
            f"score={self.score:.2f}  "
            f"sharpe={self.sharpe_norm:.2f}  "
            f"drawdown={self.drawdown_norm:.2f}  "
            f"winrate={self.win_rate_norm:.2f}  "
            f"return={self.return_norm:.2f}"
        )


def score_pod(pod_id: str, perf: dict, trade_stats: dict) -> PodScore:
    """
    perf:        performance_metrics dict from PodSummary
    trade_stats: trade_outcome_stats dict from PodSummary
    """
    sharpe    = perf.get("sharpe", 0.0) or 0.0
    max_dd    = perf.get("max_drawdown", 0.0) or 0.0
    win_rate  = trade_stats.get("win_rate", 0.5) or 0.5
    ret       = perf.get("total_return_pct", 0.0) or 0.0

    sn = _norm(sharpe,   *_SHARPE_RANGE)
    dn = _norm(max_dd,   *_DD_RANGE)     # higher (less negative) = better
    wn = _norm(win_rate, *_WINRATE_RANGE)
    rn = _norm(ret,      *_RETURN_RANGE)

    composite = (
        WEIGHTS["sharpe"]       * sn +
        WEIGHTS["max_drawdown"] * dn +
        WEIGHTS["win_rate"]     * wn +
        WEIGHTS["total_return"] * rn
    )
    return PodScore(pod_id, composite, sn, dn, wn, rn)


def format_scorecard(scores: list[PodScore]) -> str:
    """Return a formatted scorecard block for injection into the CIO prompt."""
    ranked = sorted(scores, key=lambda s: s.score, reverse=True)
    lines = [
        "─── QUANTITATIVE SCORECARD (25% weight — Sharpe×0.4 | MaxDD×0.3 | WinRate×0.2 | Return×0.1) ───",
        *[s.scorecard_row() for s in ranked],
        "─── Use the above as supporting evidence. Your qualitative reasoning drives the decision (75%). ───",
    ]
    return "\n".join(lines)
```

**Step 2: Write failing test**
```python
# tests/unit/test_pod_scorer.py
from src.agents.cio.pod_scorer import score_pod, format_scorecard

def test_score_pod_perfect():
    perf = {"sharpe": 4.0, "max_drawdown": 0.0, "total_return_pct": 0.30}
    stats = {"win_rate": 1.0}
    s = score_pod("equities", perf, stats)
    assert s.score > 0.95

def test_score_pod_terrible():
    perf = {"sharpe": -2.0, "max_drawdown": -0.50, "total_return_pct": -0.30}
    stats = {"win_rate": 0.0}
    s = score_pod("equities", perf, stats)
    assert s.score < 0.05

def test_format_scorecard_contains_all_pods():
    scores = [
        score_pod("equities",   {"sharpe": 1.5, "max_drawdown": -0.05, "total_return_pct": 0.10}, {"win_rate": 0.6}),
        score_pod("crypto",     {"sharpe": 0.5, "max_drawdown": -0.20, "total_return_pct": -0.05}, {"win_rate": 0.4}),
    ]
    card = format_scorecard(scores)
    assert "equities" in card
    assert "crypto" in card
    assert "QUANTITATIVE SCORECARD" in card
```

**Step 3:** `python -m pytest tests/unit/test_pod_scorer.py -v` — expect FAIL

**Step 4:** Create the module, run again — expect PASS

**Step 5: Inject scorecard into CIO prompt in `cio_agent.py`**

In `_build_governance_prompt()` (or wherever the LLM prompt is built), before the closing instruction:
```python
from src.agents.cio.pod_scorer import score_pod, format_scorecard

scores = []
for pid, summary in pod_summaries.items():
    perf  = getattr(summary, "performance_metrics", {}) or {}
    stats = getattr(summary, "trade_outcome_stats", {}) or {}
    scores.append(score_pod(pid, perf, stats))
scorecard = format_scorecard(scores)

prompt = scorecard + "\n\n" + existing_prompt
```

**Step 6: Commit**
```bash
git add src/agents/cio/pod_scorer.py tests/unit/test_pod_scorer.py src/agents/cio/cio_agent.py
git commit -m "feat: CIO quantitative scorecard — 25% data / 75% reasoning split"
```

---

### Task 3: Position Aging Enforcement

**Files:**
- Create: `src/core/position_aging.py`
- Modify: `src/mission_control/session_manager.py` (call aging check after each iteration)
- Test: `tests/unit/test_position_aging.py`

**Step 1: Create `src/core/position_aging.py`**

```python
"""Detect positions that have exceeded their max_hold_days and emit aging alerts."""
from __future__ import annotations
from datetime import date, datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.backtest.accounting.portfolio import PortfolioAccountant

DEFAULT_MAX_HOLD = 30  # days, used when not set per-position


def check_aging(accountant: "PortfolioAccountant") -> list[dict]:
    """
    Returns list of aging alerts: {symbol, pod_id, days_held, max_hold_days, entry_date}
    """
    alerts = []
    today = date.today()
    for symbol, meta in accountant._entry_metadata.items():
        max_hold = meta.get("max_hold_days") or DEFAULT_MAX_HOLD
        entry_str = accountant._entry_dates.get(symbol, "")
        if not entry_str:
            continue
        try:
            entry = date.fromisoformat(entry_str)
        except ValueError:
            continue
        days_held = (today - entry).days
        if days_held >= max_hold:
            alerts.append({
                "symbol": symbol,
                "pod_id": accountant._pod_id,
                "days_held": days_held,
                "max_hold_days": max_hold,
                "entry_date": entry_str,
            })
    return alerts
```

**Step 2: Write failing test**
```python
# tests/unit/test_position_aging.py
from unittest.mock import MagicMock
from src.core.position_aging import check_aging

def _make_accountant(symbol, entry_date_str, max_hold_days):
    acc = MagicMock()
    acc._pod_id = "equities"
    acc._entry_metadata = {symbol: {"max_hold_days": max_hold_days}}
    acc._entry_dates = {symbol: entry_date_str}
    return acc

def test_overdue_position_flagged():
    acc = _make_accountant("AAPL", "2026-02-01", 30)  # 47 days ago
    alerts = check_aging(acc)
    assert len(alerts) == 1
    assert alerts[0]["symbol"] == "AAPL"
    assert alerts[0]["days_held"] >= 30

def test_fresh_position_not_flagged():
    from datetime import date
    today = date.today().isoformat()
    acc = _make_accountant("AAPL", today, 30)
    alerts = check_aging(acc)
    assert alerts == []
```

**Step 3:** Run → FAIL. Create module → run → PASS.

**Step 4: Wire into session_manager**

In `run_event_loop()`, after each iteration, call aging check per pod and emit events:
```python
from src.core.position_aging import check_aging

for pod_id, runtime in self._pod_runtimes.items():
    aging_alerts = check_aging(runtime._accountant)
    for alert in aging_alerts:
        # Store aging directive in namespace — PM reads it on next cycle
        runtime._ns.set("aging_alerts", aging_alerts)
        # Emit to EventBus for Intelligence Feed
        await self._bus.publish(
            topic=f"pod.{pod_id}.gateway",
            payload={
                "type": "position_aging_alert",
                "pod_id": pod_id,
                "symbol": alert["symbol"],
                "days_held": alert["days_held"],
                "max_hold_days": alert["max_hold_days"],
            }
        )
```

**Step 5: PM reads aging alerts**

In each PM agent's `run_cycle()`, before building prompt:
```python
aging_alerts = self._ns.get("aging_alerts") or []
if aging_alerts:
    aging_text = "\n".join(
        f"  ⚠ {a['symbol']}: held {a['days_held']}d (max {a['max_hold_days']}d) — assess thesis validity, propose exit if stale"
        for a in aging_alerts
        if a["symbol"] in self._current_symbols  # only relevant positions
    )
    if aging_text:
        prompt += f"\n\nAGING ALERTS — these positions need thesis reassessment:\n{aging_text}"
```

**Step 6: Commit**
```bash
git add src/core/position_aging.py tests/unit/test_position_aging.py src/mission_control/session_manager.py
git commit -m "feat: position aging enforcement — PM directed to reassess stale holdings"
```

---

### Task 4: Multi-timeframe Context for PM

**Files:**
- Create: `src/data/adapters/multiframe.py`
- Modify: `src/pods/templates/equities/pm_agent.py` (and other PMs)
- Test: `tests/unit/test_multiframe.py`

**Step 1: Create `src/data/adapters/multiframe.py`**

```python
"""Fetch 52-week high/low and 200-day MA for a list of symbols."""
from __future__ import annotations
import logging
from datetime import date, timedelta

logger = logging.getLogger(__name__)

_LOOKBACK_DAYS = 380   # >1 year to ensure 200d MA has data


def compute_multiframe(symbols: list[str], fetch_fn) -> dict[str, dict]:
    """
    fetch_fn: callable(symbol, period_days) -> list[Bar] (same interface as YFinanceAdapter)
    Returns dict[symbol -> {high_52w, low_52w, ma_200, current_price, pct_from_ma}]
    """
    result = {}
    for sym in symbols:
        try:
            bars = fetch_fn(sym, _LOOKBACK_DAYS)
            if not bars or len(bars) < 20:
                continue
            closes = [b.close for b in bars]
            current = closes[-1]
            high_52w = max(closes[-252:]) if len(closes) >= 252 else max(closes)
            low_52w  = min(closes[-252:]) if len(closes) >= 252 else min(closes)
            ma_200   = sum(closes[-200:]) / min(200, len(closes))
            pct_from_ma = (current - ma_200) / ma_200 * 100 if ma_200 else 0.0
            result[sym] = {
                "high_52w": round(high_52w, 2),
                "low_52w":  round(low_52w, 2),
                "ma_200":   round(ma_200, 2),
                "current":  round(current, 2),
                "pct_from_ma": round(pct_from_ma, 1),
            }
        except Exception as e:
            logger.debug("[multiframe] %s: %s", sym, e)
    return result


def format_multiframe_block(mf: dict[str, dict]) -> str:
    """Format for PM prompt injection."""
    if not mf:
        return ""
    lines = ["MULTI-TIMEFRAME CONTEXT (52wk range | 200dMA):"]
    for sym, d in mf.items():
        ma_arrow = "▲" if d["pct_from_ma"] >= 0 else "▼"
        lines.append(
            f"  {sym:<6} 52wH=${d['high_52w']}  52wL=${d['low_52w']}  "
            f"200dMA=${d['ma_200']}  Now=${d['current']}  "
            f"{ma_arrow}{abs(d['pct_from_ma']):.1f}% {'above' if d['pct_from_ma']>=0 else 'below'} MA"
        )
    return "\n".join(lines)
```

**Step 2: Write failing test**
```python
# tests/unit/test_multiframe.py
from unittest.mock import MagicMock
from src.data.adapters.multiframe import compute_multiframe, format_multiframe_block

def _make_bar(close):
    b = MagicMock()
    b.close = close
    return b

def test_compute_multiframe_basic():
    prices = list(range(100, 480))  # 380 bars
    bars = [_make_bar(float(p)) for p in prices]
    result = compute_multiframe(["AAPL"], lambda sym, days: bars)
    assert "AAPL" in result
    assert result["AAPL"]["high_52w"] >= result["AAPL"]["low_52w"]
    assert result["AAPL"]["ma_200"] > 0

def test_format_multiframe_block():
    mf = {"AAPL": {"high_52w": 237.0, "low_52w": 164.0, "ma_200": 220.0, "current": 215.0, "pct_from_ma": -2.3}}
    block = format_multiframe_block(mf)
    assert "AAPL" in block
    assert "52wH" in block
    assert "200dMA" in block
```

**Step 3:** Run → FAIL. Create module → PASS.

**Step 4: Inject into PM agents**

In each PM's `run_cycle()`, build multiframe context for held positions:
```python
from src.data.adapters.multiframe import compute_multiframe, format_multiframe_block

held_symbols = list(self._accountant.positions.keys())
if held_symbols:
    mf_data = compute_multiframe(held_symbols, self._price_fetch)
    mf_block = format_multiframe_block(mf_data)
    if mf_block:
        prompt += f"\n\n{mf_block}"
```

**Step 5: Commit**
```bash
git add src/data/adapters/multiframe.py tests/unit/test_multiframe.py src/pods/templates/
git commit -m "feat: multi-timeframe context (52wk high/low + 200dMA) injected into PM prompt"
```

---

### Task 5: Source Attribution Scoring

**Files:**
- Modify: `src/core/signal_scorer.py`
- Modify: `src/core/scoring.py` (dynamic weights with 15% floor)
- Create: `src/core/source_attribution.py`
- Test: `tests/unit/test_source_attribution.py`

**Step 1: Create `src/core/source_attribution.py`**

```python
"""Track per-source win rates and compute dynamic macro score weights."""
from __future__ import annotations

MIN_WEIGHT = 0.15
SOURCES    = ("fred", "poly", "news")
_DEFAULT   = {"fred": 0.50, "poly": 0.30, "news": 0.20}


def compute_dynamic_weights(win_rates: dict[str, float]) -> dict[str, float]:
    """
    win_rates: {"fred": 0.65, "poly": 0.38, "news": 0.55}
    Returns weights summing to 1.0, each >= MIN_WEIGHT.
    """
    raw = {s: max(0.01, win_rates.get(s, 0.5)) for s in SOURCES}
    total = sum(raw.values())
    proportional = {s: v / total for s, v in raw.items()}

    # Apply floor
    floored = {s: max(MIN_WEIGHT, v) for s, v in proportional.items()}
    # Re-normalise
    floor_total = sum(floored.values())
    return {s: v / floor_total for s, v in floored.items()}


class SourceAttributor:
    """Track closed trade signal snapshots and derive per-source win rates."""

    def __init__(self) -> None:
        self._counts: dict[str, dict[str, int]] = {s: {"wins": 0, "total": 0} for s in SOURCES}

    def ingest_closed_trade(self, trade: dict) -> None:
        snapshot = trade.get("signal_snapshot") or {}
        outcome  = trade.get("realized_pnl", 0.0)
        is_win   = outcome > 0

        for source in SOURCES:
            score = snapshot.get(f"{source}_score")
            if score is not None:
                self._counts[source]["total"] += 1
                if is_win:
                    self._counts[source]["wins"] += 1

    def win_rates(self) -> dict[str, float]:
        result = {}
        for s in SOURCES:
            total = self._counts[s]["total"]
            result[s] = self._counts[s]["wins"] / total if total > 0 else 0.5
        return result

    def weights(self) -> dict[str, float]:
        return compute_dynamic_weights(self.win_rates())

    def summary(self) -> str:
        rates = self.win_rates()
        weights = self.weights()
        lines = ["SOURCE ATTRIBUTION:"]
        for s in SOURCES:
            total = self._counts[s]["total"]
            lines.append(
                f"  {s:<5} win={rates[s]:.0%}  n={total}  weight={weights[s]:.0%}"
            )
        return "\n".join(lines)
```

**Step 2: Write failing test**
```python
# tests/unit/test_source_attribution.py
from src.core.source_attribution import SourceAttributor, compute_dynamic_weights

def test_dynamic_weights_floor():
    rates = {"fred": 0.90, "poly": 0.10, "news": 0.50}
    weights = compute_dynamic_weights(rates)
    assert all(w >= 0.15 for w in weights.values())
    assert abs(sum(weights.values()) - 1.0) < 0.001

def test_attributor_ingest():
    attr = SourceAttributor()
    attr.ingest_closed_trade({"signal_snapshot": {"fred_score": 0.8, "poly_score": 0.3}, "realized_pnl": 50.0})
    attr.ingest_closed_trade({"signal_snapshot": {"fred_score": 0.2, "poly_score": 0.9}, "realized_pnl": -20.0})
    rates = attr.win_rates()
    assert rates["fred"] == 1.0   # 1/1 win
    assert rates["poly"] == 0.0   # 0/1 win (high score on a loser)

def test_default_weights_when_no_data():
    attr = SourceAttributor()
    weights = attr.weights()
    # With 0.5 win rate for all, weights should be equal
    assert abs(weights["fred"] - weights["poly"]) < 0.01
```

**Step 3:** Run → FAIL. Create module → PASS.

**Step 4: Wire into scoring.py**

In `compute_macro_score()`, replace hardcoded weights:
```python
from src.core.source_attribution import compute_dynamic_weights

# Replace hardcoded 0.50 / 0.30 / 0.20 with:
dynamic_weights = kwargs.get("source_weights") or {"fred": 0.50, "poly": 0.30, "news": 0.20}
w_fred = dynamic_weights.get("fred", 0.50)
w_poly = dynamic_weights.get("poly", 0.30)
w_news = dynamic_weights.get("news", 0.20)
```

In `session_manager.py`, maintain a `SourceAttributor` per pod, ingest closed trades each iteration, pass weights to `compute_macro_score()`.

**Step 5: Surface on dashboard**

Emit `source_attribution` in the pod enrichment broadcast:
```javascript
// dashboard.js — in enrichment message handler:
if (d.source_attribution) {
    // render in Research tab: fred win%, poly win%, news win%, and current weights
}
```

**Step 6: Commit**
```bash
git add src/core/source_attribution.py tests/unit/test_source_attribution.py src/core/scoring.py
git commit -m "feat: dynamic source attribution weights with 15% floor — FRED/Poly/News self-calibrates"
```

---

### Task 6: Firm-wide Concentration Limits

**Files:**
- Create: `src/core/concentration.py`
- Modify: `src/pods/runtime/pod_runtime.py` (check before order execution)
- Modify: `src/mission_control/session_manager.py` (update firm exposure after each iteration)
- Test: `tests/unit/test_concentration.py`

**Step 1: Create `src/core/concentration.py`**

```python
"""Firm-wide sector concentration checker."""
from __future__ import annotations
from collections import defaultdict
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.core.models.pod_summary import PodSummary

MAX_SECTOR_PCT = 0.40   # 40% of firm NAV


def aggregate_exposure(summaries: dict[str, "PodSummary"]) -> dict[str, float]:
    """Returns {sector: total_notional_pct_of_firm_nav} across all pods."""
    firm_nav = sum(
        (s.risk_metrics.nav if s.risk_metrics else 0.0)
        for s in summaries.values()
    )
    if firm_nav <= 0:
        return {}

    sector_notional: dict[str, float] = defaultdict(float)
    for summary in summaries.values():
        pod_nav = summary.risk_metrics.nav if summary.risk_metrics else 0.0
        for bucket in (summary.exposure_buckets or []):
            # bucket.notional_pct_nav is fraction of this pod's NAV
            notional = bucket.notional_pct_nav * pod_nav
            sector_notional[bucket.asset_class] += notional

    return {sector: notional / firm_nav for sector, notional in sector_notional.items()}


def check_concentration(
    sector: str,
    firm_exposure: dict[str, float],
) -> tuple[bool, str]:
    """
    Returns (allowed: bool, reason: str).
    allowed=False means new buy in this sector would breach limit.
    """
    current = firm_exposure.get(sector, 0.0)
    if current >= MAX_SECTOR_PCT:
        return False, f"Firm-wide {sector} exposure {current:.0%} >= {MAX_SECTOR_PCT:.0%} limit"
    return True, ""
```

**Step 2: Write failing test**
```python
# tests/unit/test_concentration.py
from unittest.mock import MagicMock
from src.core.concentration import aggregate_exposure, check_concentration

def _mock_summary(nav, buckets):
    s = MagicMock()
    s.risk_metrics.nav = nav
    s.exposure_buckets = [MagicMock(asset_class=b[0], notional_pct_nav=b[1]) for b in buckets]
    return s

def test_aggregate_exposure():
    summaries = {
        "equities": _mock_summary(100, [("equity", 0.80), ("bonds", 0.10)]),
        "crypto":   _mock_summary(100, [("crypto", 0.60)]),
    }
    exposure = aggregate_exposure(summaries)
    assert abs(exposure["equity"] - 0.40) < 0.01   # 80/200
    assert abs(exposure["crypto"] - 0.30) < 0.01   # 60/200

def test_check_concentration_blocks():
    firm_exposure = {"equity": 0.42}
    allowed, reason = check_concentration("equity", firm_exposure)
    assert not allowed
    assert "equity" in reason

def test_check_concentration_allows():
    firm_exposure = {"equity": 0.30}
    allowed, _ = check_concentration("equity", firm_exposure)
    assert allowed
```

**Step 3:** Run → FAIL. Create module → PASS.

**Step 4: Wire into session_manager**

After each iteration, update a shared `_firm_exposure` dict on the session_manager:
```python
self._firm_exposure = aggregate_exposure(self._last_pod_summaries)
```

Pass `firm_exposure` to each pod's namespace so pod_runtime can check it before execution:
```python
runtime._ns.set("firm_exposure", self._firm_exposure)
```

**Step 5: Enforce in pod_runtime before order execution**

```python
from src.core.concentration import check_concentration

order = ctx.get("order")
if order and order.side == "buy":
    firm_exposure = self._ns.get("firm_exposure") or {}
    pod_asset_class = self._pod_id  # approximate — use pod type as sector proxy
    allowed, reason = check_concentration(pod_asset_class, firm_exposure)
    if not allowed:
        logger.warning("[%s] Concentration limit: %s — blocking %s buy", self._pod_id, reason, order.symbol)
        ctx["order"] = None
```

**Step 6: Commit**
```bash
git add src/core/concentration.py tests/unit/test_concentration.py
git commit -m "feat: firm-wide sector concentration limits — blocks buys at 40% firm NAV"
```

---

### Task 7: Live Headline Alerts

**Files:**
- Modify: `src/data/adapters/sentiment.py` (add position-matching after scoring)
- Modify: `src/pods/templates/equities/researcher.py` (emit alert events)
- Modify: `web/dist/dashboard.js` (badge + feed entry)
- Modify: `web/dist/styles.css` (alert badge style)
- Test: `tests/unit/test_headline_alerts.py`

**Step 1: Create alert-matching logic in sentiment.py**

```python
def find_position_alerts(
    scored_items: list[dict],
    held_symbols: set[str],
    relevancy_threshold: float = 0.70,
) -> list[dict]:
    """
    Return items where relevancy >= threshold AND subject matches a held symbol.
    scored_items: list of {text, sentiment, relevancy, impact, ...}
    """
    alerts = []
    for item in scored_items:
        if item.get("relevancy", 0) < relevancy_threshold:
            continue
        text_upper = (item.get("text") or "").upper()
        for sym in held_symbols:
            if sym in text_upper:
                alerts.append({**item, "matched_symbol": sym})
                break
    return alerts
```

**Step 2: Write failing test**
```python
# tests/unit/test_headline_alerts.py
from src.data.adapters.sentiment import find_position_alerts

def test_alert_matched():
    items = [{"text": "AAPL faces antitrust probe", "relevancy": 0.85, "sentiment": -0.6}]
    alerts = find_position_alerts(items, {"AAPL", "MSFT"})
    assert len(alerts) == 1
    assert alerts[0]["matched_symbol"] == "AAPL"

def test_low_relevancy_ignored():
    items = [{"text": "AAPL faces antitrust probe", "relevancy": 0.30, "sentiment": -0.6}]
    alerts = find_position_alerts(items, {"AAPL"})
    assert alerts == []

def test_no_position_match():
    items = [{"text": "Oil prices surge", "relevancy": 0.90, "sentiment": 0.7}]
    alerts = find_position_alerts(items, {"AAPL", "MSFT"})
    assert alerts == []
```

**Step 3:** Run → FAIL. Create function → PASS.

**Step 4: Emit alerts from researcher agents**

After `score_items()`, call `find_position_alerts()`:
```python
held = set(self._accountant.positions.keys())
alerts = find_position_alerts(scored, held)
for alert in alerts:
    await self._bus.publish(
        topic=f"pod.{self._pod_id}.gateway",
        payload={
            "type": "headline_alert",
            "pod_id": self._pod_id,
            "symbol": alert["matched_symbol"],
            "headline": alert.get("text", "")[:200],
            "sentiment": alert.get("sentiment", 0),
            "relevancy": alert.get("relevancy", 0),
        }
    )
```

**Step 5: Dashboard — badge + Intelligence Feed**

In `dashboard.js`, handle `headline_alert` message type:
```javascript
// Store alerts per symbol
var _symbolAlerts = {};  // symbol -> [{headline, sentiment, ts}]

// In WS message handler:
if (msg.type === 'headline_alert') {
  var sym = msg.symbol;
  if (!_symbolAlerts[sym]) _symbolAlerts[sym] = [];
  _symbolAlerts[sym].unshift({headline: msg.headline, sentiment: msg.sentiment, ts: new Date().toISOString()});
  if (_symbolAlerts[sym].length > 5) _symbolAlerts[sym] = _symbolAlerts[sym].slice(0, 5);
  renderTopHoldings();  // re-render to show badges
  addFeedEntry({type: 'headline_alert', ...msg});
}
```

In holdings row rendering, check `_symbolAlerts[sym]`:
```javascript
var alertBadge = _symbolAlerts[sym] && _symbolAlerts[sym].length > 0
  ? '<span class="alert-badge" title="' + escapeHtml(_symbolAlerts[sym][0].headline) + '">!</span>'
  : '';
// prepend alertBadge to symbol cell
```

In `styles.css`:
```css
.alert-badge {
  display: inline-block;
  background: #e84040;
  color: #fff;
  font-size: 8px;
  font-weight: 700;
  padding: 1px 4px;
  border-radius: 3px;
  margin-left: 4px;
  vertical-align: middle;
  animation: pulse 1.5s ease-in-out 3;
}
```

**Step 6: Commit**
```bash
git add src/data/adapters/sentiment.py tests/unit/test_headline_alerts.py web/dist/dashboard.js web/dist/styles.css
git commit -m "feat: live headline alerts — badge on affected holdings + Intelligence Feed entry"
```

---

### Task 8: Dynamic Capital Reallocation (CIO-driven)

**Files:**
- Modify: `src/agents/cio/cio_agent.py` (trigger reallocation from scoring)
- Modify: `src/backtest/accounting/capital_allocator.py` (add cash transfer method)
- Modify: `src/mission_control/session_manager.py` (execute transfers, set trim targets)
- Test: `tests/unit/test_capital_reallocation.py`

**Step 1: Add cash transfer to CapitalAllocator**

```python
# In capital_allocator.py
def compute_target_capitals(self, firm_nav: float) -> dict[str, float]:
    """Returns {pod_id: target_capital_$} from current allocation percentages."""
    return {pod: pct * firm_nav for pod, pct in self._allocations.items()}

def suggest_reallocation(
    self,
    pod_scores: dict[str, float],  # pod_id -> 0-1 score from pod_scorer
    firm_nav: float,
    min_pct: float = 0.10,         # floor per pod
) -> dict[str, float]:
    """Compute new allocation percentages based on scores."""
    total = sum(pod_scores.values()) or 1.0
    raw = {p: max(min_pct, s / total) for p, s in pod_scores.items()}
    raw_total = sum(raw.values())
    return {p: v / raw_total for p, v in raw.items()}
```

**Step 2: Write failing test**
```python
# tests/unit/test_capital_reallocation.py
from src.backtest.accounting.capital_allocator import CapitalAllocator

def test_suggest_reallocation_respects_floor():
    alloc = CapitalAllocator.__new__(CapitalAllocator)
    alloc._allocations = {"equities": 0.25, "crypto": 0.25, "fx": 0.25, "commodities": 0.25}
    scores = {"equities": 0.80, "crypto": 0.20, "fx": 0.60, "commodities": 0.40}
    new_allocs = alloc.suggest_reallocation(scores, firm_nav=400.0)
    assert all(v >= 0.10 for v in new_allocs.values())
    assert abs(sum(new_allocs.values()) - 1.0) < 0.001
    assert new_allocs["equities"] > new_allocs["crypto"]

def test_compute_target_capitals():
    alloc = CapitalAllocator.__new__(CapitalAllocator)
    alloc._allocations = {"equities": 0.60, "crypto": 0.40}
    targets = alloc.compute_target_capitals(1000.0)
    assert targets["equities"] == 600.0
    assert targets["crypto"] == 400.0
```

**Step 3:** Run → FAIL. Add methods → PASS.

**Step 4: Session manager executes phased transfers**

After CIO governance run:
```python
from src.agents.cio.pod_scorer import score_pod

# Score all pods
pod_scores = {}
for pod_id, summary in pod_summaries.items():
    perf  = getattr(summary, "performance_metrics", {}) or {}
    stats = getattr(summary, "trade_outcome_stats", {}) or {}
    pod_scores[pod_id] = score_pod(pod_id, perf, stats).score

# Get suggested reallocation
firm_nav = sum(s.risk_metrics.nav for s in pod_summaries.values() if s.risk_metrics)
new_allocs = self._capital_allocator.suggest_reallocation(pod_scores, firm_nav)

# Apply: transfer available cash, mark trim targets
for pod_id, target_pct in new_allocs.items():
    target_capital = target_pct * firm_nav
    current_nav = pod_summaries[pod_id].risk_metrics.nav
    delta = target_capital - current_nav
    runtime = self._pod_runtimes[pod_id]

    if delta < -5.0:  # needs to give capital (trim down)
        available_cash = runtime._accountant.cash
        transfer = min(available_cash, abs(delta))
        if transfer > 1.0:
            runtime._accountant._cash -= transfer
            # Credit to highest-scoring pod needing more capital
            # (simplified: add to firm cash pool, redistribute next iteration)
        runtime._ns.set("trim_target_capital", target_capital)

    elif delta > 5.0:  # receives capital
        # Will be topped up from transfers in next iteration
        runtime._ns.set("growth_target_capital", target_capital)
```

**Step 5: Commit**
```bash
git add src/backtest/accounting/capital_allocator.py tests/unit/test_capital_reallocation.py src/mission_control/session_manager.py src/agents/cio/cio_agent.py
git commit -m "feat: CIO-driven capital reallocation — performance-weighted pod funding with phased transfers"
```

---

## Test Commands

```bash
# Run all unit tests for new features
python -m pytest tests/unit/test_pm_memory.py tests/unit/test_pod_scorer.py tests/unit/test_position_aging.py tests/unit/test_multiframe.py tests/unit/test_source_attribution.py tests/unit/test_concentration.py tests/unit/test_headline_alerts.py tests/unit/test_capital_reallocation.py -v

# Full suite (confirm no regressions)
python -m pytest tests/ -v --tb=short
```

## Final Commit (after all tasks pass)
```bash
git add .
git commit -m "feat: intelligence upgrade — PM memory, CIO scorecard, aging enforcement, multi-timeframe, source attribution, concentration limits, headline alerts, capital reallocation"
git push origin master
```
