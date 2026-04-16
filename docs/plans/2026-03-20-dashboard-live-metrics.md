# Dashboard Live Metrics Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Surface three categories of real backend data on the dashboard — market regime label, real performance metrics (Sharpe/Sortino/drawdown), and trade outcome stats (win rate, avg P&L) — all of which are already computed but never sent to the frontend.

**Architecture:** All three features follow the same data pipeline: (1) add field to `PodSummary`, (2) populate in `pod_runtime.py::get_summary()`, (3) pass through in `server.py::_on_pod_update()`, (4) render in `dashboard.js`. No new backend logic required — all the computation already exists.

**Tech Stack:** Python/Pydantic v2 (backend models), FastAPI/WebSocket (broadcast), Vanilla JS (dashboard rendering), CSS variables (styling).

---

## Task 1: Add new fields to PodSummary model

**Files:**
- Modify: `src/core/models/pod_summary.py`

**Step 1: Read the current model**

Confirm current state of `PodSummary` (lines 35–50). It currently has no `macro_regime`, `performance_metrics`, or `trade_outcome_stats` fields.

**Step 2: Add three fields**

In `src/core/models/pod_summary.py`, add to the `PodSummary` class after `error_message`:

```python
macro_regime: str | None = None          # "risk_on" | "neutral" | "risk_off" | "crisis"
performance_metrics: dict = Field(default_factory=dict)   # sharpe, sortino, max_drawdown, current_vol, total_return_pct
trade_outcome_stats: dict = Field(default_factory=dict)   # total_trades, win_rate, avg_pnl, total_pnl, avg_winner, avg_loser
```

**Step 3: Verify import**

`Field` is already imported from pydantic at the top of the file. No new imports needed.

**Step 4: Commit**

```bash
git add src/core/models/pod_summary.py
git commit -m "feat: add regime, performance_metrics, trade_outcome_stats to PodSummary"
```

---

## Task 2: Add `to_dict()` to TradeOutcomeTracker

**Files:**
- Modify: `src/core/trade_outcomes.py`

**Step 1: Add structured getter method** after `per_symbol_stats()` (around line 65):

```python
def to_dict(self) -> dict:
    """Return all aggregate stats as a JSON-serialisable dict."""
    return {
        "total_trades": self.total_trades,
        "win_rate": round(self.win_rate, 3),
        "avg_pnl": round(self.avg_pnl, 2),
        "total_pnl": round(self.total_pnl, 2),
        "avg_winner": round(self.avg_winner, 2),
        "avg_loser": round(self.avg_loser, 2),
    }
```

Note: `per_symbol_stats()` is intentionally excluded — too large for a WebSocket broadcast payload.

**Step 2: Commit**

```bash
git add src/core/trade_outcomes.py
git commit -m "feat: add to_dict() structured getter to TradeOutcomeTracker"
```

---

## Task 3: Populate new fields in `pod_runtime.py::get_summary()`

**Files:**
- Modify: `src/pods/runtime/pod_runtime.py` (around line 528–540)

**Step 1: Read the current `get_summary()` return block** (lines 528–547).

Currently builds `PodSummary(...)` with no `macro_regime`, `performance_metrics`, or `trade_outcome_stats`.

**Step 2: Gather data before the PodSummary constructor**

Directly before the `summary = PodSummary(...)` line (line 529), add:

```python
# Regime label from macro_view set during run_cycle
macro_view = self._ns.get("macro_view") or {}
macro_regime = macro_view.get("regime")  # e.g. "Risk-On", "Neutral", "Risk-Off", "Crisis"

# Real performance metrics from accountant (requires >=2 daily snapshots to be meaningful)
try:
    performance_metrics = accountant.performance_summary()
except Exception:
    performance_metrics = {}

# Trade outcome stats from the tracker (only when trades have closed)
try:
    trade_outcome_stats = self._outcome_tracker.to_dict() if self._outcome_tracker.total_trades > 0 else {}
except Exception:
    trade_outcome_stats = {}
```

**Step 3: Pass fields into PodSummary constructor**

Add to the `PodSummary(...)` call:

```python
summary = PodSummary(
    pod_id=self._pod_id,
    timestamp=datetime.now(),
    status=status,
    risk_metrics=risk_metrics,
    exposure_buckets=exposure_buckets,
    expected_return_estimate=0.0,
    turnover_daily_pct=0.0,
    heartbeat_ok=True,
    positions=positions,
    error_message=None,
    macro_regime=macro_regime,
    performance_metrics=performance_metrics,
    trade_outcome_stats=trade_outcome_stats,
)
```

**Step 4: Verify `_outcome_tracker` attribute**

Confirm `self._outcome_tracker` is available at line 52: `self._outcome_tracker = TradeOutcomeTracker(pod_id)`. It is — no change needed.

**Step 5: Commit**

```bash
git add src/pods/runtime/pod_runtime.py
git commit -m "feat: inject regime, perf metrics, trade stats into PodSummary from pod_runtime"
```

---

## Task 4: Pass new fields through server.py broadcast

**Files:**
- Modify: `src/web/server.py` (around lines 142–157)

**Step 1: Read `_on_pod_update()`** (lines 134–193).

The method unpacks `risk_metrics` sub-dict and adds flattened keys to `payload`. New top-level PodSummary fields (`macro_regime`, `performance_metrics`, `trade_outcome_stats`) will be in `payload` automatically when the summary is serialised — but only if they survive the `model_dump(mode="json")` call in the gateway emit.

**Step 2: Explicitly preserve the new fields in the broadcast**

In the `if is_full_summary:` block (after line 157), add alongside the other extracted keys:

```python
payload["macro_regime"] = payload.get("macro_regime")
payload["performance_metrics"] = payload.get("performance_metrics", {})
payload["trade_outcome_stats"] = payload.get("trade_outcome_stats", {})
```

**Step 3: Also preserve through the research-keys merge**

In the `research_keys` tuple (line 173), there's no change needed — these three keys are not research keys, they're full-summary keys, so they get preserved in `payload` directly.

**Step 4: Commit**

```bash
git add src/web/server.py
git commit -m "feat: pass macro_regime, performance_metrics, trade_outcome_stats through WebSocket broadcast"
```

---

## Task 5: Render market regime badge on Operations tab

**Files:**
- Modify: `web/dist/index.html`
- Modify: `web/dist/dashboard.js`
- Modify: `web/dist/styles.css`

### 5a — Add badge div to Operations tab header

In `web/dist/index.html`, find the Operations tab (`id="tab-ops"`) section header. Add a regime badge span next to the firm NAV or in the section header row. Find the firm-level KPI row (search for `kpi-nav` or `firm-nav`) and add:

```html
<div id="regime-badge" class="regime-badge regime-neutral" title="Current market regime">NEUTRAL</div>
```

Place it in the status bar area or at the top of the Operations pane — find the `<div class="sec-hdr">` for the operations tab and add it alongside the other badges.

### 5b — Add regime badge styles to `web/dist/styles.css`

Add before the closing of the file or alongside other badge styles:

```css
/* Market Regime Badge */
.regime-badge {
  display: inline-flex;
  align-items: center;
  padding: 3px 10px;
  border-radius: 3px;
  font-size: 9px;
  font-weight: 700;
  letter-spacing: 1.5px;
  font-family: var(--font-mono);
  border: 1px solid currentColor;
  transition: color 0.3s, background 0.3s, border-color 0.3s;
}
.regime-risk-on  { color: var(--green, #00d68f); background: rgba(0,214,143,0.08); }
.regime-neutral  { color: var(--text-dim, #8899aa); background: rgba(136,153,170,0.08); }
.regime-risk-off { color: #f0a500; background: rgba(240,165,0,0.08); }
.regime-crisis   { color: var(--red, #e84040); background: rgba(232,64,64,0.08); animation: blink 1.5s ease-in-out infinite; }
```

### 5c — Update regime badge in `dashboard.js` when pod_summary arrives

In the `handleMessage` function, in the `pod_summary` branch where pod data is merged (around line 863–878), add:

```javascript
// Update firm-level regime badge (all pods share same market regime — use any non-null)
if (d.macro_regime) {
  var regimeBadge = document.getElementById('regime-badge');
  if (regimeBadge) {
    var raw = d.macro_regime.toLowerCase().replace(/[^a-z_]/g, '').replace('risk_on','risk-on').replace('riskoff','risk-off').replace('risk-off','risk-off');
    // Normalise to css class suffix: "risk_on" -> "risk-on", "risk-off" -> "risk-off" etc.
    var cls = raw.replace('risk_on','risk-on').replace('risk off','risk-off').replace('riskoff','risk-off');
    regimeBadge.className = 'regime-badge regime-' + cls;
    regimeBadge.textContent = d.macro_regime.toUpperCase().replace(/_/g,' ');
    regimeBadge.title = 'Market regime: ' + d.macro_regime;
  }
}
```

Note: `macro_view.regime` is set as `regime.get("label", "Unknown")` in pod_runtime (line 170), where `label` comes from `RegimeClassification.label`. Check `src/core/regime.py` to confirm the exact label strings — they may be "Risk-On", "Risk-Off", "Neutral", "Crisis" (title case). Normalise accordingly in the CSS class mapping.

**Step 5d: Commit**

```bash
git add web/dist/index.html web/dist/dashboard.js web/dist/styles.css
git commit -m "feat: market regime badge on Operations tab (live from backend classifier)"
```

---

## Task 6: Replace fake Sharpe/metrics with real backend values on Performance tab

**Files:**
- Modify: `web/dist/dashboard.js`

**Step 1: Find where pod data is merged from `pod_summary`** (around line 863).

After the existing merge block, add:

```javascript
if (d.performance_metrics && Object.keys(d.performance_metrics).length > 0) {
  pods_state[pid].performance_metrics = d.performance_metrics;
}
```

**Step 2: Find `calculateMetrics()`** — the function that computes firm-level Sharpe/Vol/Drawdown from frontend `navHistory`. It displays results in elements `m-sharpe`, `m-vol`, `m-dd`, `m-wr`.

Add a helper that reads real metrics from pods_state:

```javascript
function getRealPerfMetrics() {
  // Aggregate performance_metrics across all pods (use first non-empty pod's metrics as firm proxy)
  // For Sharpe/Sortino, average across pods. For drawdown, take worst.
  var sharpes = [], sortinos = [], dds = [];
  Object.values(pods_state).forEach(function(p) {
    var pm = p.performance_metrics || {};
    if (pm.sharpe != null) sharpes.push(pm.sharpe);
    if (pm.sortino != null) sortinos.push(pm.sortino);
    if (pm.max_drawdown != null) dds.push(pm.max_drawdown);
  });
  if (sharpes.length === 0) return null;
  var avg = function(arr) { return arr.reduce(function(a,b){return a+b;},0)/arr.length; };
  return {
    sharpe: avg(sharpes).toFixed(2),
    sortino: avg(sortinos).toFixed(2),
    max_drawdown: Math.min.apply(null, dds),  // worst drawdown
  };
}
```

**Step 3: In `calculateMetrics()`**, after computing the existing frontend values, override with real values when available:

```javascript
var realMetrics = getRealPerfMetrics();
if (realMetrics) {
  var sharpeEl = document.getElementById('m-sharpe');
  if (sharpeEl) sharpeEl.textContent = realMetrics.sharpe;
  var sortEl = document.getElementById('m-sortino');
  if (sortEl) sortEl.textContent = realMetrics.sortino;
  // Override drawdown with backend value (already negative fraction)
  var ddVal = (realMetrics.max_drawdown * 100).toFixed(1);
  var ddEl = document.getElementById('m-dd');
  if (ddEl) ddEl.textContent = ddVal + '%';
}
```

Note: Check if `m-sortino` element ID exists in `index.html`. If it doesn't, add it to the Performance tab KPI row alongside `m-sharpe`, `m-vol`, `m-dd`.

**Step 4: Also show per-pod Sharpe in the pod performance table**

In `updatePodsTable()` (search for the function), add a "Sharpe" column to the pod performance table. In `index.html` add `<th>Sharpe</th>` to the thead. In the row render in `dashboard.js`, add:

```javascript
var pm = pods_state[pid] ? (pods_state[pid].performance_metrics || {}) : {};
var sharpeStr = pm.sharpe != null ? pm.sharpe.toFixed(2) : '—';
// Add <td> for sharpe in the row
```

**Step 5: Commit**

```bash
git add web/dist/dashboard.js web/dist/index.html
git commit -m "feat: real Sharpe/Sortino/drawdown from backend on Performance tab"
```

---

## Task 7: Add Trade Outcome Stats card to Performance tab

**Files:**
- Modify: `web/dist/index.html`
- Modify: `web/dist/dashboard.js`
- Modify: `web/dist/styles.css`

### 7a — Add HTML for trade stats

In `web/dist/index.html`, in the Performance tab (`id="tab-perf"`), add a new section after the KPI row:

```html
<div class="sec-hdr" style="margin-top:16px">
  <span class="sec-title">Trade Outcomes</span>
  <span class="sec-badge" id="outcomes-total-badge">— trades</span>
</div>
<div class="outcome-grid" id="outcome-grid">
  <div class="outcome-pod-card" id="outcome-card-placeholder">
    <div class="empty-txt">No closed trades yet</div>
  </div>
</div>
```

### 7b — Add CSS for outcome cards

In `web/dist/styles.css`:

```css
/* Trade Outcome Stats */
.outcome-grid {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.outcome-pod-card {
  background: var(--card);
  border: 1px solid var(--border);
  border-radius: 5px;
  padding: 10px 14px;
}
.outcome-pod-label {
  font-size: 9px;
  font-weight: 700;
  letter-spacing: 1.2px;
  color: var(--cyan);
  text-transform: uppercase;
  margin-bottom: 8px;
}
.outcome-stats-row {
  display: flex;
  gap: 20px;
  flex-wrap: wrap;
}
.outcome-stat {
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.outcome-stat-lbl {
  font-size: 9px;
  color: var(--text-muted);
  letter-spacing: 0.8px;
  text-transform: uppercase;
}
.outcome-stat-val {
  font-family: var(--font-mono);
  font-size: 14px;
  color: #fff;
  font-variant-numeric: tabular-nums;
}
.outcome-stat-val.pos { color: var(--green, #00d68f); }
.outcome-stat-val.neg { color: var(--red, #e84040); }
```

### 7c — Update outcome grid in `dashboard.js`

Add a function `renderOutcomeStats()` that reads `pods_state` and renders one card per pod that has `trade_outcome_stats`:

```javascript
function renderOutcomeStats() {
  var container = document.getElementById('outcome-grid');
  var badge = document.getElementById('outcomes-total-badge');
  if (!container) return;

  var podIds = Object.keys(pods_state).filter(function(pid) {
    var s = pods_state[pid].trade_outcome_stats || {};
    return s.total_trades > 0;
  });

  var totalTrades = podIds.reduce(function(sum, pid) {
    return sum + ((pods_state[pid].trade_outcome_stats || {}).total_trades || 0);
  }, 0);
  if (badge) badge.textContent = totalTrades + ' trade' + (totalTrades !== 1 ? 's' : '');

  if (podIds.length === 0) {
    container.innerHTML = '<div class="outcome-pod-card"><div class="empty-txt">No closed trades yet</div></div>';
    return;
  }

  container.innerHTML = podIds.map(function(pid) {
    var s = pods_state[pid].trade_outcome_stats || {};
    var wrCls = s.win_rate >= 0.5 ? 'pos' : 'neg';
    var avgCls = s.avg_pnl >= 0 ? 'pos' : 'neg';
    var totCls = s.total_pnl >= 0 ? 'pos' : 'neg';
    return '<div class="outcome-pod-card">' +
      '<div class="outcome-pod-label">' + pid.toUpperCase() + '</div>' +
      '<div class="outcome-stats-row">' +
        '<div class="outcome-stat"><div class="outcome-stat-lbl">Trades</div><div class="outcome-stat-val">' + (s.total_trades || 0) + '</div></div>' +
        '<div class="outcome-stat"><div class="outcome-stat-lbl">Win Rate</div><div class="outcome-stat-val ' + wrCls + '">' + ((s.win_rate || 0) * 100).toFixed(0) + '%</div></div>' +
        '<div class="outcome-stat"><div class="outcome-stat-lbl">Avg P&L</div><div class="outcome-stat-val ' + avgCls + '">' + (s.avg_pnl >= 0 ? '+' : '') + '$' + (s.avg_pnl || 0).toFixed(2) + '</div></div>' +
        '<div class="outcome-stat"><div class="outcome-stat-lbl">Total P&L</div><div class="outcome-stat-val ' + totCls + '">' + (s.total_pnl >= 0 ? '+' : '') + '$' + (s.total_pnl || 0).toFixed(2) + '</div></div>' +
        '<div class="outcome-stat"><div class="outcome-stat-lbl">Avg Winner</div><div class="outcome-stat-val pos">+$' + (s.avg_winner || 0).toFixed(2) + '</div></div>' +
        '<div class="outcome-stat"><div class="outcome-stat-lbl">Avg Loser</div><div class="outcome-stat-val neg">$' + (s.avg_loser || 0).toFixed(2) + '</div></div>' +
      '</div>' +
    '</div>';
  }).join('');
}
```

**Step 7d: Call `renderOutcomeStats()` on every pod_summary update**

In `handleMessage()`, in the `pod_summary` branch, after merging `trade_outcome_stats`, call:

```javascript
if (d.trade_outcome_stats) {
  pods_state[pid].trade_outcome_stats = d.trade_outcome_stats;
  renderOutcomeStats();
}
```

**Step 7e: Commit**

```bash
git add web/dist/index.html web/dist/dashboard.js web/dist/styles.css
git commit -m "feat: trade outcome stats card on Performance tab (win rate, avg P&L, avg winner/loser per pod)"
```

---

## Final Verification

After all tasks are committed:

1. Run the dashboard: `python run.py`
2. Open `http://localhost:8000`
3. Check Operations tab — regime badge should appear and update (may show "Unknown" until a full cycle runs)
4. Check Performance tab — after first cycle:
   - Real Sharpe/Sortino/drawdown values replace frontend approximations
   - Trade Outcome Stats section appears once any trade closes
5. Wait for a full iteration cycle (~60s) to see all metrics populate

```bash
git log --oneline -7  # Should show 6 new commits
git push origin master
```

---

## Notes & Gotchas

- **`macro_view.regime` label format**: Set in `pod_runtime.py` line 170 as `regime.get("label", "Unknown")`. The `RegimeClassification.label` comes from `src/core/regime.py` — verify the exact strings before mapping to CSS classes. They are likely title-case: "Risk-On", "Risk-Off", "Neutral", "Crisis".
- **performance_summary() requires snapshots**: Returns `sharpe=0.0` if fewer than 2 daily NAV snapshots exist. Show `"—"` in the UI when sharpe is exactly 0 and nav history is short.
- **Pydantic serialisation**: `PodSummary.model_dump(mode="json")` will serialise `performance_metrics: dict` and `trade_outcome_stats: dict` correctly since all values are primitives (float, int).
- **No new tests needed for this feature**: All computation already has tests. The only new testable logic is `TradeOutcomeTracker.to_dict()` — verify it returns correct keys when `_trades` is empty (should return `total_trades: 0, win_rate: 0.0` etc.).
