# Research Data Tab — Design

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add a 6th "Research" tab to the dashboard right panel displaying Polymarket signal data across three clearly separated sub-tabs.

**Architecture:** Extend pod_summary WebSocket message to include polymarket_signals field. Dashboard JavaScript renders three sub-tab views from incoming data. No backend changes beyond pod_summary extension.

**Design Session:** 2026-03-09

---

## Layout & Structure

- **New tab:** "Research" added as 6th tab in right panel tab bar
- **Tab accent:** Cyan (`var(--cyan)`) — consistent with Execution tab
- **Sub-tab bar:** 3 horizontal sub-tabs inside Research tab pane: `Current | Historical | Contributing`
- **Active sub-tab:** Underline indicator (same pattern as main tabs)
- **Panel width:** 38% of viewport (unchanged from M1)

---

## Sub-Tab 1: Current Markets

**Purpose:** Latest Polymarket snapshot — all fetched markets in current cycle.

**Components:**
- Header: "POLYMARKET SNAPSHOT · {N} MARKETS · Last fetch: {timestamp}"
- Dense table (monospace fonts for numeric values)

**Columns:**
| Column | Source Field | Format |
|--------|-------------|--------|
| Question | `question` | Text, truncate at 40 chars, full text on hover |
| Yes | `yes_price` | `0.00` mono |
| No | `no_price` | `0.00` mono |
| Implied Prob | `implied_prob` | `00.0%` cyan accent |
| Spread | `spread` | `0.00` mono |
| 24h Vol | `volume_24h` | `$0.0M` amber |
| Open Int | `open_interest` | `$0.0M` mono |
| Fetched | `timestamp` | `HH:MM:SS` dim |
| Tags | `tags` | Pill badges |

**Behavior:**
- Click row → tooltip overlay showing full market question
- Empty state: "No Polymarket data — check POLYMARKET_API_KEY in .env"
- Updates on every pod_summary message where `polymarket_signals` present

---

## Sub-Tab 2: Historical Signals

**Purpose:** Evolution of market probabilities over recent cycles.

**Components:**

**Top — Line Chart (Chart.js):**
- X-axis: Cycle number (last 20 fetches)
- Y-axis: Implied Probability 0–100%
- Lines: Top 5 markets by average implied_prob (unique colors)
- Legend: Truncated market questions
- Grid: Dim lines (`var(--border-dim)`)
- Colors: Cycle through cyan, amber, green, purple, red

**Bottom — Recent Cycles Table:**
- Columns: Timestamp | Market (truncated) | Implied Prob
- Rows: Last 10 cycles × top 5 markets
- Grouped by cycle with subtle separator
- Monospace numbers, dim timestamps

**Behavior:**
- Chart updates incrementally (append new point, shift oldest off)
- Max 20 data points per market in chart history
- History persists for session duration (cleared on page reload)

---

## Sub-Tab 3: Contributing Markets

**Purpose:** Transparency into how Polymarket signals influenced current macro_score.

**Components:**

**Header — Calculation Display:**
```
macro_score = momentum × macro_confidence
0.51 = 0.75 × 0.68
```
Styled as large monospace equation with labels.

**Confidence Breakdown:**
- Text: `Polymarket confidence = average of {N} markets → {X}%`

**Contributors Table:**
| Column | Description |
|--------|-------------|
| Question | Market question (truncated 40 chars) |
| Implied Prob | Raw probability (`00.0%`) |
| Weight | Visual bar showing contribution (bar width = prob %) |

**Visual Weight:**
- Bar chart column: filled bar, width proportional to implied_prob
- Top 3 markets: green row highlight (`var(--green)` at 10% opacity)
- Bottom 3: dimmer styling (`var(--text-dim)`)

**Footer:**
- `Average of {N} markets = {X}% confidence`
- `Momentum score: {Y}` (from namespace)
- `Final macro_score: {Z}` (cyan, prominent)

**Empty State:** "No Polymarket signals this cycle — macro_confidence defaulted to 0.50"

---

## Data Flow

```
GammaResearcher.run_cycle()
    → fetch_signals() → poly_signals list
    → self.store("polymarket_signals", poly_signals)
    → returns {"poly_signals": [...]}

SessionManager
    → builds pod_summary for Gamma pod
    → adds polymarket_signals field from namespace

EventBus → WebSocket → Dashboard
    → handleMessage(pod_summary)
    → if msg.polymarket_signals: updateResearchTab(signals)

Dashboard JS State:
    currentSignals = []          // Latest snapshot
    signalHistory = []           // Last 20 cycles [{ts, signals}]
    macroScore = null            // Current macro_score
    polymarketConfidence = null  // Current confidence
    momentum = null              // Current momentum
```

---

## Backend Changes Required

### 1. Extend pod_summary EventBus message

File: `src/mission_control/session_manager.py`

Add `polymarket_signals` to the pod summary data emitted to EventBus:
```python
summary = PodSummary(
    pod_id=pod.pod_id,
    nav=...,
    daily_pnl=...,
    polymarket_signals=pod.runtime.namespace.get("polymarket_signals", []),
    polymarket_confidence=pod.runtime.namespace.get("polymarket_confidence", 0.5),
    macro_score=pod.runtime.namespace.get("macro_score"),
)
```

### 2. Extend PodSummary model (if needed)

File: `src/core/models/pod.py`

Check if PodSummary already has extensible fields. If not, add:
```python
polymarket_signals: list[dict] = []
polymarket_confidence: float = 0.5
macro_score: float | None = None
```

### 3. WebSocket server passes through to dashboard

File: `src/web/server.py`

Verify `pod_summary` message serialization includes new fields (should auto-include via Pydantic dict serialization).

---

## Frontend Changes

### File: `web/dist/index.html`

**HTML additions:**
- 6th tab button in tab bar: `<button class="tab-btn" data-tab="research">Research</button>`
- Research tab pane with sub-tab bar and 3 sub-panes

**CSS additions:**
- `.sub-tab-bar` — inner tab bar styling
- `.sub-tab-btn` — sub-tab button styling (smaller than main tabs)
- `.sub-tab-pane` — sub-tab content pane
- `.signal-bar` — contribution bar chart element
- `.contributor-top` — green highlight class for top contributors
- `.calc-display` — macro_score equation display styling

**JavaScript additions:**
- `researchSubTab = 'current'` — sub-tab state variable
- `signalHistory = []` — circular buffer (max 20 entries)
- `switchResearchSubTab(name)` — sub-tab switcher
- `updateResearchTab(signals, confidence, macroScore, momentum)` — main update function
- `renderCurrentMarkets(signals)` — render snapshot table
- `renderHistoricalChart()` — update Chart.js history chart
- `renderContributors(signals, confidence, macroScore, momentum)` — render contributors view
- `historyChart` — Chart.js instance for historical sub-tab
- Hook into existing `handleMessage()` to extract polymarket data from pod_summary

---

## Styling Notes

Consistent with M1 design tokens:
- Background: `var(--bg-surface)` for table rows
- Border: `var(--border-dim)` for row separators
- Text: `var(--text-primary)` labels, `var(--font-mono)` for numbers
- Accent: `var(--cyan)` for implied_prob, active states
- Volume: `var(--amber)`
- Contributors: `var(--green)` top 3 highlight
- Tags: Pill badges with `var(--bg-elevated)` background

---

## Empty & Error States

| Scenario | Display |
|----------|---------|
| No API key | "No Polymarket data — check POLYMARKET_API_KEY in .env" |
| API fetch failed | "Last fetch failed — showing previous data" |
| No markets for tags | "No markets found for tags: macro, fed, inflation, gdp" |
| Non-Gamma pod selected | "Polymarket signals available for Gamma pod only" |
| First load (no data yet) | Skeleton loader (3 dim rows) |

---

## Verification

1. Start dashboard: `python run.py` → `http://localhost:8000`
2. Click "Research" tab — sub-tabs appear: Current | Historical | Contributing
3. Wait 60s for first Gamma pod cycle
4. **Current tab:** Table populates with Polymarket markets (implied probs visible)
5. **Historical tab:** Chart starts building as more cycles run; table shows cycle history
6. **Contributing tab:** Calculation equation displays; bars show contribution weight; top 3 highlighted green
7. Click market row → full question text appears
8. Switch main tabs and back — Research tab state preserved
9. No console errors; smooth 60fps maintained
