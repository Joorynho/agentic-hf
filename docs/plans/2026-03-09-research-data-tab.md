# Research Data Tab — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add a 6th "Research" tab to the dashboard right panel with 3 sub-tabs displaying Polymarket signals (Current Markets, Historical, Contributing Markets).

**Architecture:** Extend SessionManager to inject polymarket namespace data into pod_summary WebSocket messages. Dashboard JavaScript renders three Chart.js + table views from incoming data. No changes to PodSummary Pydantic model — inject fields into the serialized dict directly.

**Tech Stack:** Python 3.12 (SessionManager), JavaScript (dashboard), Chart.js (history chart), Three.js dashboard at `web/dist/index.html`.

---

## Critical Code References

- **SessionManager `_update_web_state()`:** `src/mission_control/session_manager.py` lines ~384-410 — where `summary.model_dump(mode="json")` happens
- **WebSocket broadcast:** `src/web/server.py` lines ~118-135 — `_on_pod_update` sends `{"type":"pod_summary","pod_id":...,"data":...}`
- **Dashboard tab bar:** `web/dist/index.html` lines ~543-549 — 5 existing `<button class="tab-btn">` elements
- **Tab switching JS:** `web/dist/index.html` lines ~1670-1677 — `querySelectorAll('.tab-btn')` click handler
- **Message handler:** `web/dist/index.html` lines ~1702-1707 — `handleMessage()` function, `pods[pod_id] = data` pattern
- **CSS variables:** `:root` block — `--cyan`, `--green`, `--amber`, `--bg-surface`, `--border-dim`, `--font-mono`, `--text-muted`

---

## Task 1: Inject Polymarket Data into SessionManager Pod Summary

**Files:**
- Modify: `src/mission_control/session_manager.py` (lines ~384-410, `_update_web_state`)

**Goal:** When serializing pod summaries for the WebSocket, add polymarket_signals, polymarket_confidence, and macro_score from the Gamma pod's namespace into the dict.

**Step 1: Find the exact serialization block**

Read `src/mission_control/session_manager.py` and find `_update_web_state`. Look for the line:
```python
pod_dicts[pod_id] = summary.model_dump(mode="json")
```

**Step 2: Add Polymarket injection after that line**

Directly after `pod_dicts[pod_id] = summary.model_dump(mode="json")`, add:

```python
# Inject Polymarket research data for Gamma pod
if pod_id == "gamma" and pod_id in self._pod_runtimes:
    runtime = self._pod_runtimes[pod_id]
    ns = runtime.namespace
    pod_dicts[pod_id]["polymarket_signals"] = ns.get("polymarket_signals") or []
    pod_dicts[pod_id]["polymarket_confidence"] = ns.get("polymarket_confidence") or 0.5
    pod_dicts[pod_id]["macro_score"] = ns.get("macro_score")
```

**Note:** `self._pod_runtimes` is the dict of pod runtimes. Verify this attribute name exists — search for `_pod_runtimes` in the file. If the name is different (e.g., `_runtimes`, `pod_runtimes`), adjust accordingly.

**Step 3: Verify runtime has a `namespace` attribute**

Check what `runtime` is (likely a `PodRuntime` or similar class). The namespace should be accessible as `runtime.namespace` (a `PodNamespace` instance). If it's accessed differently, read the runtime class to find the right attribute name.

**Step 4: Manual verification**

Run the server and check WebSocket output:
```bash
cd "C:\Users\PW1868\Agentic HF"
python run.py
```

Open browser console (`F12`) → Network tab → WS connection → look for `pod_summary` messages for pod_id="gamma". Verify the message's `data` field now contains `polymarket_signals`, `polymarket_confidence`, `macro_score`.

**Step 5: Commit**

```bash
git add src/mission_control/session_manager.py
git commit -m "feat: inject Polymarket signals into Gamma pod_summary WebSocket message"
```

---

## Task 2: Add Research Tab HTML

**Files:**
- Modify: `web/dist/index.html` (tab bar + new pane)

**Goal:** Add the Research tab button to the tab bar and create the tab pane HTML with 3 sub-tabs.

**Step 1: Read the current tab bar**

Find lines ~543-549 in `web/dist/index.html`:
```html
<nav class="tab-bar">
  <button class="tab-btn active" data-tab="operations">Operations</button>
  <button class="tab-btn" data-tab="performance">Performance</button>
  <button class="tab-btn" data-tab="risk">Risk</button>
  <button class="tab-btn" data-tab="execution">Execution</button>
  <button class="tab-btn" data-tab="governance">Governance</button>
</nav>
```

**Step 2: Add Research tab button**

Add after the Governance button:
```html
  <button class="tab-btn" data-tab="research">Research</button>
```

**Step 3: Find where the Governance tab pane ends**

Search for `id="tab-governance"` — find the closing `</div>` of that pane.

**Step 4: Add Research tab pane HTML after Governance pane**

```html
<!-- RESEARCH -->
<div class="tab-pane" id="tab-research">
  <!-- KPI strip -->
  <div class="kpi-row" id="research-kpi">
    <div class="kpi-card">
      <div class="kpi-label">MARKETS</div>
      <div class="kpi-value" id="kpi-market-count">—</div>
    </div>
    <div class="kpi-card">
      <div class="kpi-label">AVG PROB</div>
      <div class="kpi-value" id="kpi-avg-prob">—</div>
    </div>
    <div class="kpi-card">
      <div class="kpi-label">MACRO CONF</div>
      <div class="kpi-value" id="kpi-macro-conf">—</div>
    </div>
    <div class="kpi-card">
      <div class="kpi-label">MACRO SCORE</div>
      <div class="kpi-value" id="kpi-macro-score">—</div>
    </div>
  </div>

  <!-- Sub-tab bar -->
  <div class="sub-tab-bar">
    <button class="sub-tab-btn active" data-subtab="current">Current</button>
    <button class="sub-tab-btn" data-subtab="historical">Historical</button>
    <button class="sub-tab-btn" data-subtab="contributing">Contributing</button>
  </div>

  <!-- Sub-tab: Current Markets -->
  <div class="sub-tab-pane active" id="subtab-current">
    <div class="research-header" id="current-header">
      POLYMARKET SNAPSHOT · <span id="market-count">0</span> MARKETS
      · Last fetch: <span id="last-fetch-time" class="mono">—</span>
    </div>
    <div class="table-wrap">
      <table class="data-table" id="current-markets-table">
        <thead>
          <tr>
            <th>Question</th>
            <th class="num">Yes</th>
            <th class="num">No</th>
            <th class="num accent">Prob</th>
            <th class="num">Spread</th>
            <th class="num">24h Vol</th>
            <th class="num">Open Int</th>
            <th class="num">Fetched</th>
            <th>Tags</th>
          </tr>
        </thead>
        <tbody id="current-markets-body">
          <tr class="empty-row"><td colspan="9">No Polymarket data — check POLYMARKET_API_KEY in .env</td></tr>
        </tbody>
      </table>
    </div>
  </div>

  <!-- Sub-tab: Historical -->
  <div class="sub-tab-pane" id="subtab-historical">
    <div class="research-header">IMPLIED PROBABILITY TRENDS · Last 20 Cycles</div>
    <div class="chart-wrap" style="height:200px;">
      <canvas id="research-history-chart"></canvas>
    </div>
    <div class="table-wrap">
      <table class="data-table" id="history-table">
        <thead>
          <tr>
            <th>Time</th>
            <th>Market</th>
            <th class="num accent">Implied Prob</th>
          </tr>
        </thead>
        <tbody id="history-body">
          <tr class="empty-row"><td colspan="3">No history yet — waiting for first cycle</td></tr>
        </tbody>
      </table>
    </div>
  </div>

  <!-- Sub-tab: Contributing -->
  <div class="sub-tab-pane" id="subtab-contributing">
    <div class="research-header">MACRO SCORE CONTRIBUTORS</div>
    <div class="calc-display" id="calc-display">
      <span class="calc-label">macro_score</span>
      <span class="calc-op">=</span>
      <span class="calc-val" id="calc-momentum">—</span>
      <span class="calc-label">momentum</span>
      <span class="calc-op">×</span>
      <span class="calc-val cyan" id="calc-confidence">—</span>
      <span class="calc-label">confidence</span>
      <span class="calc-op">=</span>
      <span class="calc-val green" id="calc-result">—</span>
    </div>
    <div class="table-wrap">
      <table class="data-table" id="contributors-table">
        <thead>
          <tr>
            <th>Market Question</th>
            <th class="num accent">Implied Prob</th>
            <th>Weight</th>
          </tr>
        </thead>
        <tbody id="contributors-body">
          <tr class="empty-row"><td colspan="3">No Polymarket signals this cycle — macro_confidence defaulted to 0.50</td></tr>
        </tbody>
      </table>
    </div>
    <div class="calc-footer" id="calc-footer">
      Average of <span id="contrib-count">0</span> markets = <span id="contrib-avg" class="cyan">—</span> confidence
    </div>
  </div>
</div>
```

**Step 5: Verify HTML is well-formed**

Open browser (`python run.py` → `http://localhost:8000`), click Research tab — verify it appears in tab bar and the pane is visible (even if empty).

**Step 6: Commit**

```bash
git add web/dist/index.html
git commit -m "feat: add Research tab HTML with Current/Historical/Contributing sub-tabs"
```

---

## Task 3: Add Research Tab CSS

**Files:**
- Modify: `web/dist/index.html` (style block)

**Goal:** Style the Research tab consistently with existing M1 design tokens.

**Step 1: Find the CSS `<style>` block**

It's near the top of `web/dist/index.html`. Find where other tab styles are defined (search for `.tab-btn`).

**Step 2: Add these styles to the existing `<style>` block**

```css
/* ─── Research Sub-tabs ─── */
.sub-tab-bar {
  display: flex;
  gap: 2px;
  padding: 8px 16px 0;
  border-bottom: 1px solid var(--border-dim);
  margin-bottom: 0;
}

.sub-tab-btn {
  background: none;
  border: none;
  border-bottom: 2px solid transparent;
  color: var(--text-muted);
  font-family: var(--font-ui);
  font-size: 11px;
  font-weight: 600;
  letter-spacing: 1px;
  text-transform: uppercase;
  padding: 6px 12px;
  cursor: pointer;
  transition: color 0.2s, border-color 0.2s;
  margin-bottom: -1px;
}

.sub-tab-btn:hover {
  color: var(--text-primary);
}

.sub-tab-btn.active {
  color: var(--cyan);
  border-bottom-color: var(--cyan);
}

.sub-tab-pane {
  display: none;
  overflow-y: auto;
  flex: 1;
}

.sub-tab-pane.active {
  display: flex;
  flex-direction: column;
}

/* ─── Research Headers ─── */
.research-header {
  font-family: var(--font-mono);
  font-size: 10px;
  letter-spacing: 1.5px;
  color: var(--text-muted);
  padding: 8px 16px;
  border-bottom: 1px solid var(--border-dim);
  text-transform: uppercase;
}

/* ─── Table tweaks for research ─── */
.data-table th.accent,
.data-table td.accent {
  color: var(--cyan);
}

.data-table td.num,
.data-table th.num {
  text-align: right;
  font-family: var(--font-mono);
  font-size: 11px;
}

.data-table .empty-row td {
  text-align: center;
  color: var(--text-dim);
  font-style: italic;
  padding: 20px;
}

.data-table tr.top-contributor {
  background: rgba(0, 200, 136, 0.06);
}

/* ─── Contribution bar ─── */
.contrib-bar-wrap {
  width: 100%;
  height: 6px;
  background: var(--bg-elevated);
  border-radius: 3px;
  overflow: hidden;
  min-width: 60px;
}

.contrib-bar {
  height: 100%;
  background: var(--cyan);
  border-radius: 3px;
  transition: width 0.4s ease;
}

.top-contributor .contrib-bar {
  background: var(--green);
}

/* ─── Tag pills ─── */
.tag-pill {
  display: inline-block;
  background: var(--bg-elevated);
  border: 1px solid var(--border-dim);
  border-radius: 3px;
  font-family: var(--font-mono);
  font-size: 9px;
  padding: 1px 5px;
  color: var(--text-muted);
  margin-right: 2px;
}

/* ─── Macro score calc display ─── */
.calc-display {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 12px 16px;
  background: var(--bg-surface);
  border-bottom: 1px solid var(--border-dim);
  font-family: var(--font-mono);
  font-size: 13px;
  flex-wrap: wrap;
}

.calc-label {
  font-size: 10px;
  color: var(--text-dim);
  letter-spacing: 1px;
  text-transform: uppercase;
}

.calc-op {
  color: var(--text-muted);
  font-size: 14px;
}

.calc-val {
  font-size: 18px;
  font-weight: 700;
  color: var(--text-primary);
}

.calc-val.cyan { color: var(--cyan); }
.calc-val.green { color: var(--green); }

.calc-footer {
  font-family: var(--font-mono);
  font-size: 10px;
  color: var(--text-muted);
  padding: 8px 16px;
  border-top: 1px solid var(--border-dim);
  margin-top: auto;
}

/* ─── Chart container ─── */
.chart-wrap {
  padding: 8px 16px;
  border-bottom: 1px solid var(--border-dim);
}
```

**Step 3: Verify styling**

Open `http://localhost:8000`, click Research tab, then each sub-tab — verify sub-tab bar renders correctly, active underline is cyan, tables look consistent with existing tabs.

**Step 4: Commit**

```bash
git add web/dist/index.html
git commit -m "feat: add Research tab CSS — sub-tabs, contribution bars, calc display"
```

---

## Task 4: Add Research Tab JavaScript — State + Sub-Tab Switching

**Files:**
- Modify: `web/dist/index.html` (script block)

**Goal:** Add state variables and sub-tab switcher. Wire to existing tab switching pattern.

**Step 1: Find the globals section**

Search for `let currentFloor` or `let pods = {}` in `web/dist/index.html`. Add new globals near existing ones:

```javascript
// Research tab state
let researchSignals = [];           // Latest Polymarket snapshot
let signalHistory = [];             // [{ts, signals}] last 20 cycles
let researchPolyConf = 0.5;        // Latest polymarket_confidence
let researchMacroScore = null;     // Latest macro_score
let researchMomentum = null;       // Latest momentum (from signals)
let researchHistoryChart = null;   // Chart.js instance
```

**Step 2: Add sub-tab switcher function**

Add after the existing `scrollToFloor()` function or near other UI helpers:

```javascript
function switchResearchSubTab(name) {
  document.querySelectorAll('.sub-tab-btn').forEach(b => {
    b.classList.toggle('active', b.dataset.subtab === name);
  });
  document.querySelectorAll('.sub-tab-pane').forEach(p => {
    p.classList.toggle('active', p.id === 'subtab-' + name);
  });
  // Re-render historical chart when switching to that tab (sizing fix)
  if (name === 'historical' && researchHistoryChart) {
    researchHistoryChart.resize();
  }
}
```

**Step 3: Wire sub-tab buttons after DOM loads**

Find where the main tab-btn click listener is set up (lines ~1670-1677). Right after it, add:

```javascript
// Research sub-tab switching
document.querySelectorAll('.sub-tab-btn').forEach(btn => {
  btn.addEventListener('click', () => {
    switchResearchSubTab(btn.dataset.subtab);
  });
});
```

**Step 4: Verify sub-tab switching works**

Open browser, click Research tab, click "Historical" sub-tab → pane switches. Click "Contributing" → pane switches. Click "Current" → back to current. No console errors.

**Step 5: Commit**

```bash
git add web/dist/index.html
git commit -m "feat: add Research sub-tab switching JavaScript"
```

---

## Task 5: Implement Current Markets Rendering

**Files:**
- Modify: `web/dist/index.html` (script block)

**Goal:** Render the Current Markets sub-tab table from incoming polymarket_signals data.

**Step 1: Add helper functions**

Add these helpers near other formatting functions (search for existing `formatCurrency` or similar):

```javascript
function formatPct(v) {
  if (v == null) return '—';
  return (v * 100).toFixed(1) + '%';
}

function formatVol(v) {
  if (v == null || v === 0) return '—';
  return '$' + (v / 1_000_000).toFixed(1) + 'M';
}

function formatTime(ts) {
  if (!ts) return '—';
  const d = new Date(ts);
  return d.toLocaleTimeString('en-GB', { hour12: false });
}

function truncate(str, n) {
  if (!str) return '—';
  return str.length > n ? str.slice(0, n) + '…' : str;
}
```

**Step 2: Add renderCurrentMarkets() function**

```javascript
function renderCurrentMarkets(signals) {
  const tbody = document.getElementById('current-markets-body');
  const countEl = document.getElementById('market-count');
  const timeEl = document.getElementById('last-fetch-time');
  if (!tbody) return;

  // Update KPI strip
  document.getElementById('kpi-market-count').textContent = signals.length || '—';
  const avgProb = signals.length
    ? (signals.reduce((s, x) => s + (x.implied_prob || 0), 0) / signals.length)
    : null;
  document.getElementById('kpi-avg-prob').textContent = formatPct(avgProb);

  if (countEl) countEl.textContent = signals.length;
  if (timeEl && signals.length) {
    timeEl.textContent = formatTime(signals[0].timestamp);
  }

  if (!signals.length) {
    tbody.innerHTML = '<tr class="empty-row"><td colspan="9">No Polymarket data — check POLYMARKET_API_KEY in .env</td></tr>';
    return;
  }

  tbody.innerHTML = signals.map(s => {
    const tags = (s.tags || []).map(t => `<span class="tag-pill">${t}</span>`).join('');
    return `<tr title="${(s.question || '').replace(/"/g, '&quot;')}">
      <td>${truncate(s.question, 40)}</td>
      <td class="num">${(s.yes_price || 0).toFixed(2)}</td>
      <td class="num">${(s.no_price || 0).toFixed(2)}</td>
      <td class="num accent">${formatPct(s.implied_prob)}</td>
      <td class="num">${(s.spread || 0).toFixed(2)}</td>
      <td class="num">${formatVol(s.volume_24h)}</td>
      <td class="num">${formatVol(s.open_interest)}</td>
      <td class="num">${formatTime(s.timestamp)}</td>
      <td>${tags}</td>
    </tr>`;
  }).join('');
}
```

**Step 3: Verify (call manually from browser console)**

Open `http://localhost:8000` → Research tab → Current sub-tab. In browser console:
```javascript
renderCurrentMarkets([{
  market_id: 'test', question: 'Will Fed raise rates in March 2026?',
  yes_price: 0.68, no_price: 0.32, implied_prob: 0.68, spread: 0.36,
  volume_24h: 1500000, open_interest: 800000,
  timestamp: new Date().toISOString(), tags: ['macro', 'fed']
}]);
```
Verify table row appears with correct values.

**Step 4: Commit**

```bash
git add web/dist/index.html
git commit -m "feat: implement Current Markets sub-tab rendering"
```

---

## Task 6: Implement Historical Sub-Tab (Chart + Table)

**Files:**
- Modify: `web/dist/index.html` (script block)

**Goal:** Build Chart.js line chart and history table for the Historical sub-tab.

**Step 1: Initialize the history chart**

Find where other Chart.js charts are initialized (search for `new Chart(`). Add after that block:

```javascript
function initResearchHistoryChart() {
  const ctx = document.getElementById('research-history-chart');
  if (!ctx || researchHistoryChart) return;

  const COLORS = [
    getComputedStyle(document.documentElement).getPropertyValue('--cyan').trim(),
    getComputedStyle(document.documentElement).getPropertyValue('--amber').trim(),
    getComputedStyle(document.documentElement).getPropertyValue('--green').trim(),
    getComputedStyle(document.documentElement).getPropertyValue('--purple').trim(),
    getComputedStyle(document.documentElement).getPropertyValue('--red').trim(),
  ];

  researchHistoryChart = new Chart(ctx, {
    type: 'line',
    data: { labels: [], datasets: [] },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      animation: false,
      plugins: {
        legend: {
          labels: {
            color: '#6a90aa',
            font: { family: 'IBM Plex Mono', size: 9 },
            boxWidth: 12,
          }
        }
      },
      scales: {
        x: {
          ticks: { color: '#3a556a', font: { size: 9 } },
          grid: { color: '#1c2c3c' }
        },
        y: {
          min: 0, max: 100,
          ticks: {
            color: '#3a556a',
            font: { size: 9 },
            callback: v => v + '%'
          },
          grid: { color: '#1c2c3c' }
        }
      }
    }
  });
  return COLORS;
}
```

**Step 2: Add updateHistoricalChart() function**

```javascript
function updateHistoricalChart() {
  if (!researchHistoryChart) initResearchHistoryChart();
  if (!researchHistoryChart) return;

  const COLORS = ['#00cfe8','#f0a030','#00c888','#7c5cfc','#e84040'];
  const MAX_HISTORY = 20;
  const MAX_MARKETS = 5;

  // Build set of top 5 markets by latest implied_prob
  const latestSignals = signalHistory.length
    ? [...signalHistory[signalHistory.length - 1].signals]
        .sort((a, b) => (b.implied_prob || 0) - (a.implied_prob || 0))
        .slice(0, MAX_MARKETS)
    : [];

  const topIds = latestSignals.map(s => s.market_id);

  // X axis labels = cycle numbers
  const labels = signalHistory.slice(-MAX_HISTORY).map((_, i) => `C${i + 1}`);

  // Build dataset per market
  const datasets = topIds.map((id, i) => {
    const market = latestSignals[i];
    const data = signalHistory.slice(-MAX_HISTORY).map(entry => {
      const sig = entry.signals.find(s => s.market_id === id);
      return sig ? (sig.implied_prob * 100).toFixed(1) : null;
    });
    return {
      label: truncate(market.question, 25),
      data,
      borderColor: COLORS[i % COLORS.length],
      backgroundColor: 'transparent',
      borderWidth: 1.5,
      pointRadius: 2,
      tension: 0.3,
      spanGaps: true,
    };
  });

  researchHistoryChart.data.labels = labels;
  researchHistoryChart.data.datasets = datasets;
  researchHistoryChart.update();
}

function renderHistoryTable() {
  const tbody = document.getElementById('history-body');
  if (!tbody) return;

  if (!signalHistory.length) {
    tbody.innerHTML = '<tr class="empty-row"><td colspan="3">No history yet — waiting for first cycle</td></tr>';
    return;
  }

  const rows = [];
  const recent = signalHistory.slice(-10).reverse();
  recent.forEach(entry => {
    const top5 = [...entry.signals]
      .sort((a, b) => (b.implied_prob || 0) - (a.implied_prob || 0))
      .slice(0, 5);
    top5.forEach((sig, i) => {
      rows.push(`<tr>
        <td class="num">${i === 0 ? formatTime(entry.ts) : ''}</td>
        <td>${truncate(sig.question, 35)}</td>
        <td class="num accent">${formatPct(sig.implied_prob)}</td>
      </tr>`);
    });
    rows.push(`<tr style="height:4px"><td colspan="3" style="border-bottom:1px solid var(--border-dim)"></td></tr>`);
  });

  tbody.innerHTML = rows.join('');
}
```

**Step 3: Verify (call manually from browser console)**

In browser console, add a dummy history entry then render:
```javascript
signalHistory.push({ ts: new Date().toISOString(), signals: [
  { market_id: 'a', question: 'Fed hike?', implied_prob: 0.68, tags: ['fed'] },
  { market_id: 'b', question: 'CPI > 3%?', implied_prob: 0.55, tags: ['inflation'] }
]});
initResearchHistoryChart();
updateHistoricalChart();
renderHistoryTable();
```

Click "Historical" sub-tab — verify chart renders with a line and table shows rows.

**Step 4: Commit**

```bash
git add web/dist/index.html
git commit -m "feat: implement Historical sub-tab with Chart.js trend + cycle table"
```

---

## Task 7: Implement Contributing Markets Sub-Tab

**Files:**
- Modify: `web/dist/index.html` (script block)

**Goal:** Render the Contributing Markets sub-tab with calculation display and weighted bar table.

**Step 1: Add renderContributors() function**

```javascript
function renderContributors(signals, confidence, macroScore, momentum) {
  // KPI strip updates
  const confEl = document.getElementById('kpi-macro-conf');
  const scoreEl = document.getElementById('kpi-macro-score');
  if (confEl) confEl.textContent = formatPct(confidence);
  if (scoreEl) scoreEl.textContent = macroScore != null ? macroScore.toFixed(3) : '—';

  // Calc display
  const momEl = document.getElementById('calc-momentum');
  const confValEl = document.getElementById('calc-confidence');
  const resultEl = document.getElementById('calc-result');
  if (momEl) momEl.textContent = momentum != null ? momentum.toFixed(3) : '—';
  if (confValEl) confValEl.textContent = formatPct(confidence);
  if (resultEl) resultEl.textContent = macroScore != null ? macroScore.toFixed(3) : '—';

  // Footer
  const countEl = document.getElementById('contrib-count');
  const avgEl = document.getElementById('contrib-avg');
  if (countEl) countEl.textContent = signals.length;
  if (avgEl) avgEl.textContent = formatPct(confidence);

  // Contributors table
  const tbody = document.getElementById('contributors-body');
  if (!tbody) return;

  if (!signals.length) {
    tbody.innerHTML = '<tr class="empty-row"><td colspan="3">No Polymarket signals this cycle — macro_confidence defaulted to 0.50</td></tr>';
    return;
  }

  // Sort by implied_prob descending to identify top contributors
  const sorted = [...signals].sort((a, b) => (b.implied_prob || 0) - (a.implied_prob || 0));

  tbody.innerHTML = sorted.map((sig, i) => {
    const prob = sig.implied_prob || 0;
    const barPct = (prob * 100).toFixed(1);
    const isTop = i < 3;
    return `<tr class="${isTop ? 'top-contributor' : ''}">
      <td title="${(sig.question || '').replace(/"/g, '&quot;')}">${truncate(sig.question, 42)}</td>
      <td class="num accent">${formatPct(prob)}</td>
      <td>
        <div class="contrib-bar-wrap">
          <div class="contrib-bar" style="width:${barPct}%"></div>
        </div>
      </td>
    </tr>`;
  }).join('');
}
```

**Step 2: Verify (call manually from browser console)**

```javascript
renderContributors(
  [
    { market_id: 'a', question: 'Fed rate hike March 2026?', implied_prob: 0.72 },
    { market_id: 'b', question: 'CPI above 3.5% next month?', implied_prob: 0.58 },
    { market_id: 'c', question: 'GDP growth > 2% Q1?', implied_prob: 0.45 },
  ],
  0.583, 0.437, 0.75
);
```

Click "Contributing" sub-tab — verify equation shows, bars render with correct widths, top 3 rows have green tint.

**Step 3: Commit**

```bash
git add web/dist/index.html
git commit -m "feat: implement Contributing Markets sub-tab with weighted bar chart"
```

---

## Task 8: Wire handleMessage() to Update Research Tab

**Files:**
- Modify: `web/dist/index.html` (handleMessage function)

**Goal:** Extract Polymarket fields from Gamma pod_summary messages and update all three Research sub-tabs.

**Step 1: Add master updateResearchTab() orchestrator**

Add this function near the other render functions:

```javascript
function updateResearchTab(signals, confidence, macroScore) {
  researchSignals = signals || [];
  researchPolyConf = confidence != null ? confidence : 0.5;
  researchMacroScore = macroScore;

  // Append to history (max 20 cycles)
  if (researchSignals.length > 0) {
    signalHistory.push({ ts: new Date().toISOString(), signals: researchSignals });
    if (signalHistory.length > 20) signalHistory.shift();
  }

  // Render all three sub-tabs
  renderCurrentMarkets(researchSignals);
  updateHistoricalChart();
  renderHistoryTable();
  renderContributors(researchSignals, researchPolyConf, researchMacroScore, researchMomentum);
}
```

**Step 2: Hook into handleMessage()**

Find the `handleMessage(msg)` function (lines ~1702). Inside the `if (msg.type === 'pod_summary')` block, after `pods[pod_id] = data`, add:

```javascript
// Update Research tab when Gamma pod summary arrives
if (pod_id === 'gamma' && data.polymarket_signals !== undefined) {
  updateResearchTab(
    data.polymarket_signals || [],
    data.polymarket_confidence,
    data.macro_score,
  );
}
```

**Step 3: Initialize history chart on page load**

Find the `window.addEventListener('load', ...)` block or the initialization code that runs after page load. Add:

```javascript
initResearchHistoryChart();
```

**Step 4: End-to-end verification**

```bash
cd "C:\Users\PW1868\Agentic HF"
python run.py
```

1. Open `http://localhost:8000`
2. Click **Research** tab — appears in tab bar, pane visible
3. KPI strip shows dashes (no data yet)
4. Click **Current** sub-tab → empty state message visible
5. Click **Historical** sub-tab → chart renders (empty, no data)
6. Click **Contributing** sub-tab → empty state message
7. Wait ~60 seconds for first Gamma pod cycle
8. **Current tab:** Table populates with Polymarket markets (implied probs in cyan)
9. **Historical tab:** Chart starts building; table shows first cycle
10. **Contributing tab:** Equation shows values; bars render; top 3 highlighted green
11. Click a table row → tooltip shows full question text
12. Switch main tabs and back → Research sub-tab state preserved
13. No console errors

**Step 5: Commit**

```bash
git add web/dist/index.html
git commit -m "feat: wire handleMessage() to update Research tab from Gamma pod_summary"
```

---

## Final Verification Checklist

```bash
# 1. Backend: verify pod_summary includes polymarket fields
python run.py
# Open http://localhost:8000, F12 → Network → WS → look for pod_summary where pod_id=gamma
# data.polymarket_signals should be an array

# 2. Frontend: all 3 sub-tabs render correctly
# Current → table of markets
# Historical → chart + cycle table
# Contributing → equation + weighted bars

# 3. No regressions
# All other tabs (Operations, Performance, Risk, Execution, Governance) still work
# 3D building animations still work
# WebSocket reconnect still works

# 4. Edge cases
# Refresh page: Research tab goes back to empty state (correct — history is in-memory)
# No API key: empty state messages appear
# API failure: previous data retained (empty on first load)
```

---

## Files Modified

1. `src/mission_control/session_manager.py` — inject polymarket namespace data into pod_summary dict
2. `web/dist/index.html` — Research tab HTML, CSS, JavaScript (6 commits)
