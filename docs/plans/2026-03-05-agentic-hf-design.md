# Agentic Hedge Fund Platform — Design Document
**Date:** 2026-03-05
**Status:** Approved
**Author:** Claude (claude-sonnet-4-6)

---

## 1. Overview

A modular, agent-based hedge fund "operating system" — a multi-agent system that runs an end-to-end investment process with strict pod isolation. Agents communicate via a structured event bus. Pods are isolated tenants; only a central governance layer sees aggregated outputs.

### Core Decisions
| Decision | Choice | Rationale |
|---|---|---|
| Primary mode | Backtest-first | Validates architecture without live dependencies |
| Agent intelligence | Hybrid (rule-based + LLM) | Determinism where it matters, reasoning where it adds value |
| Market data | yfinance primary, Alpha Vantage backup | Zero-friction, free, deep history |
| News/events | GDELT (historical) + Reuters RSS + EDGAR + FRED + StockTwits + Reddit + X (best-effort) | Free stack with graceful degradation |
| Isolation mechanism | Thread-based, serialized-message gateway (process-ready) | Fast to build, architecturally honest, trivial to upgrade |
| Mission Control UI | Textual TUI | Keyboard-driven, ops-focused, no web server |

---

## 2. Repository Structure

```
agentic-hf/
├── core/
│   ├── models/          # All Pydantic v2 schemas
│   ├── bus/             # Event bus: pub/sub, topic routing, audit log
│   ├── clock/           # Simulation clock (backtest replay vs wall clock)
│   └── logging/         # Structured logging + immutable audit trail
│
├── agents/              # Firm-level agents
│   ├── ceo/             # LLM: objectives, constraints, mandate approval
│   ├── cio/             # LLM: capital allocation, rebalancing
│   ├── risk/            # Rule-based: limit enforcement, kill-switches
│   ├── quant/           # Hybrid: shared factor libs + strategy templates
│   └── news/            # Hybrid: scraping/dedup + LLM NLP tagging
│
├── pods/
│   ├── base/            # PodGateway, PodNamespace, BasePodAgent, PodRuntime
│   ├── runtime/         # Pod lifecycle manager (start/stop/pause/kill)
│   └── templates/       # Pod config examples + strategy plugin templates
│
├── data/
│   ├── adapters/        # DataAdapter ABC + yfinance impl + Alpha Vantage impl
│   ├── cache/           # Parquet file cache layer with completeness scoring
│   └── feeds/           # Market data router → pods (filtered per universe)
│
├── backtest/
│   ├── engine/          # Event-driven replay loop, latency model, TCM
│   └── accounting/      # PnL engine, drawdown tracker, exposure calc
│
├── execution/
│   ├── base/            # ExecutionAdapter ABC
│   └── paper/           # Paper trading adapter (simulated fills)
│
├── mission_control/
│   ├── tui/             # Textual app: all screens and widgets
│   ├── control/         # Control plane: kill-switch, allocation, lifecycle
│   └── alerts/          # Alert engine + configurable routing
│
├── config/
│   └── schemas/         # PodConfig YAML schema, RiskBudget, firm config
│
└── tests/
    ├── isolation/        # Prove pod A cannot read pod B state
    ├── risk/             # Kill-switch, drawdown, VaR enforcement
    ├── backtest/         # Deterministic replay + accounting correctness
    └── integration/      # Full end-to-end N-pod runs
```

### Module Boundary Rules
- `pods/` never imports from another pod's directory (import linter test enforces this)
- `agents/` (firm-level) only imports from `core/models/` — never pod internals
- `mission_control/` reads only from `core/bus/` and firm-level state — never pod-local state
- `data/feeds/` routes market data to pods but strips pod-identifying metadata

---

## 3. The Five Pods

| Pod | Strategy | Universe | Horizon | Target Vol | Max DD | Max Leverage | PM Type |
|---|---|---|---|---|---|---|---|
| **Alpha** | Momentum / Trend | US large-cap equities (S&P 500) | Swing (3–10d) | 12% | 10% | 1.5x | Rule-based |
| **Beta** | Stat Arb / Pairs | US sector ETF pairs | Intraday–2d | 8% | 7% | 2.0x | Rule-based |
| **Gamma** | Global Macro | Multi-asset ETFs (SPY, TLT, GLD, UUP, EEM) | Weekly–monthly | 10% | 8% | 1.2x | LLM-assisted |
| **Delta** | Event-Driven | US equities (earnings + news) | Event window (1–5d) | 15% | 12% | 1.0x | LLM-assisted |
| **Epsilon** | Volatility Regime | VIX ETFs + equity indices | Daily–weekly | 10% | 9% | 1.5x | Rule-based |

### Pod Internal Agent Structure (all pods)
```
PodRuntime
├── Pod Researcher Agent    (pod-specific scrapers + central feed consumer)
├── Pod Signal/Quant Agent  (feature engineering + alpha generation)
├── Pod PM Agent            (decision maker: rule-based or LLM)
├── Pod Risk Agent          (pre-trade checks, issues RiskApprovalToken)
├── Pod Execution Trader    (final validation gate — ONLY agent touching adapter)
└── Pod Ops Agent           (logging, reconciliation, heartbeat)
```

**Two-agent sign-off:** Every order requires a `RiskApprovalToken` from the Pod Risk Agent before the Execution Trader will submit it. Tokens expire in milliseconds.

---

## 4. Core Data Models

All models are Pydantic v2. All cross-boundary objects serialize to JSON.

### Messages & Events
```python
class AgentMessage(BaseModel):
    id: UUID
    timestamp: datetime
    sender: str
    recipient: str
    topic: str
    payload: dict
    correlation_id: UUID | None

class Event(BaseModel):
    id: UUID
    timestamp: datetime
    event_type: EventType  # MARKET_DATA | NEWS | RISK_BREACH | KILL_SWITCH | ...
    source: str
    data: dict
    tags: list[str]
```

### Pod Configuration
```python
class RiskBudget(BaseModel):
    target_vol: float
    max_leverage: float
    max_drawdown: float
    max_concentration: float
    max_sector_exposure: float
    liquidity_min_adv_pct: float
    var_limit_95: float
    es_limit_95: float

class PodConfig(BaseModel):
    pod_id: str
    name: str
    strategy_family: str
    universe: list[str]
    time_horizon: Literal["intraday", "swing", "weekly", "monthly"]
    risk_budget: RiskBudget
    execution: ExecutionConfig
    backtest: BacktestConfig
    pm_agent_type: Literal["rule_based", "llm_assisted"]
    enabled: bool = True
```

### Execution
```python
class Order(BaseModel):
    id: UUID
    pod_id: str
    symbol: str
    side: Literal["buy", "sell"]
    order_type: Literal["market", "limit", "VWAP"]
    quantity: float
    limit_price: float | None
    timestamp: datetime
    strategy_tag: str  # pod-internal, never exposed cross-boundary

class Fill(BaseModel):
    id: UUID; order_id: UUID; pod_id: str
    symbol: str; side: Literal["buy", "sell"]
    quantity: float; price: float; commission: float; timestamp: datetime

class Position(BaseModel):
    pod_id: str; symbol: str; quantity: float
    avg_cost: float; market_value: float
    unrealised_pnl: float; last_updated: datetime
```

### Sanitized Pod Output (ONLY object that crosses pod boundary)
```python
class PodSummary(BaseModel):
    pod_id: str
    timestamp: datetime
    status: Literal["active", "paused", "halted", "error"]
    risk_metrics: PodRiskMetrics      # NAV, PnL, DD, vol, leverage, VaR, ES
    exposure_buckets: list[PodExposureBucket]  # coarse asset class buckets only
    expected_return_estimate: float   # no model details
    turnover_daily_pct: float
    heartbeat_ok: bool
    error_message: str | None
```

### News
```python
class NewsItem(BaseModel):
    id: UUID; timestamp: datetime; source: str
    headline: str; body_snippet: str  # max 500 chars
    entities: list[str]               # tickers, countries, sectors
    sentiment: float                  # -1.0 to 1.0
    event_tags: list[str]
    reliability_score: float
    dedupe_hash: str
```

---

## 5. Isolation Mechanism

### PodNamespace
```python
class PodNamespace:
    def __init__(self, pod_id: str):
        self._pod_id = pod_id
        self._store: dict = {}
    # Keys namespaced internally: f"{pod_id}::{key}"
    # A pod cannot address another pod's keys
```

### PodGateway
```python
class PodGateway:
    # Serializes ALL outbound data
    # Validates ALL inbound data
    # Only exit/entry point for a pod
    def emit_summary(self, summary: PodSummary) -> None: ...
    def receive_mandate(self) -> GovernanceMessage | None: ...
    def subscribe_market_data(self, symbols: list[str]) -> AsyncIterator[Bar]: ...
    def subscribe_news(self) -> AsyncIterator[NewsItem]: ...
```

### Event Bus Topic Ownership
```
"pod.{pod_id}.gateway"  → only PodGateway(pod_id) can publish
"governance.{pod_id}"   → only CEO/CIO/Risk agents can publish
"market.data"           → only DataFeed can publish
"news.feed"             → only NewsAgent can publish
"risk.alert"            → only RiskManager can publish
```

Every message is written to an immutable append-only audit log (DuckDB).

### Isolation Tests (ship with MVP1)
```python
def test_pod_cannot_read_sibling_namespace()
def test_pod_cannot_publish_to_sibling_gateway()
def test_pod_summary_strips_internal_fields()
def test_governance_channel_is_one_way_per_pod()
def test_import_boundary_no_cross_pod_imports()
```

---

## 6. Firm-Level Agents

| Agent | Type | Key Responsibility |
|---|---|---|
| CEO | LLM (Claude) | Firm narrative, mandate approval, pod onboarding |
| CIO | LLM (Claude) | Capital allocation, rebalancing, allocation rationale |
| Risk Manager | Rule-based | Hard limit enforcement, kill-switches — never delegated to LLM |
| Quant/Research | Hybrid | Shared factor libs (rule-based) + strategy template generation (LLM) |
| News Agent | Hybrid | Scraping/dedup (rule-based) + entity extraction/sentiment (LLM) |

**Rule:** Risk enforcement is always rule-based. LLMs can recommend; kill-switches are code.

### LLM Agent Pattern (CEO / CIO)
Uses Anthropic Claude SDK. Structured tool use for all decisions:
```python
# CIO Agent example tool
allocate_capital(
    pod_id: str,
    new_allocation_pct: float,
    rationale: str,           # required — written to audit log
    risk_budget_changes: dict | None
)
```
All LLM outputs pass through a schema validator before any action is taken.

---

## 7. Data Stack

### Market Data
| Source | Library | Role | Reliability |
|---|---|---|---|
| Yahoo Finance | `yfinance` | Primary OHLCV | Medium |
| Alpha Vantage | `alpha_vantage` | Backup OHLCV | Medium |
| CBOE / Yahoo | `yfinance` | VIX + options | High |
| Binance/CoinGecko | `ccxt` / `pycoingecko` | Crypto (Epsilon) | High |

### News & Events
| Source | Library | Backtest? | Notes |
|---|---|---|---|
| GDELT | `gdeltdoc` | ✓ 2015+ | Historical news backbone |
| FRED | `fredapi` | ✓ Full history | Economic releases |
| SEC EDGAR | `requests` | ✓ 1993+ | 8-K, 10-Q filings |
| Reuters RSS | `feedparser` | ✗ Live only | General news |
| StockTwits | REST API | ✗ Live only | Financial social |
| Reddit | `praw` | ✓ Limited | r/investing, r/wallstreetbets |
| X/Twitter | `snscrape` | ✗ Fragile | Best-effort; circuit breaker |

### Data Quality Safeguards
- Every ingested bar gets a **completeness score** (expected vs received)
- Missing data triggers `DataQualityAlert` on event bus
- Backtest engine **halts** (never silently skips) if completeness < configurable threshold
- X/snscrape failure is `INFO` level only — never blocks system

### Pod Researcher Data Sources
| Pod | Primary | Secondary |
|---|---|---|
| Alpha | yfinance earnings calendar, FRED economic calendar | Reuters RSS |
| Beta | yfinance sector ETF flows, Alpha Vantage | yfinance only |
| Gamma | FRED (CPI, GDP, rates, yield curve) | EDGAR, Reuters |
| Delta | GDELT + Reuters RSS + EDGAR 8-K | StockTwits |
| Epsilon | CBOE VIX term structure, FRED credit spreads | yfinance VIX |
| All pods | X via snscrape (best-effort, non-critical), Reddit | Disabled gracefully |

---

## 8. Backtest Engine

- **Event-driven replay** — simulation clock drives all agents; no look-ahead
- **Latency model** — configurable news-to-signal and signal-to-order latency (ms)
- **Transaction cost model** — fixed bps, sqrt market impact, or linear slippage
- **Corporate actions** — splits/dividends via adjusted close + corporate action event log
- **Completeness halting** — stops replay on data gaps above threshold
- **Parallel pods** — N pods run in isolation with shared clock, separate state
- **Deterministic** — seeded UUIDs and RNG for reproducibility

---

## 9. Mission Control (Textual TUI)

### Screen Map
| Key | Screen | Highlights |
|---|---|---|
| `F1` | Firm dashboard | NAV, PnL, drawdown, vol, VaR/ES, leverage |
| `F2` | Pod table | All pods, inline sparklines, status indicators |
| `F3` | Pod drill-down | Exposure buckets, risk metrics, researcher status |
| `F4` | Event timeline | Filterable unified log |
| `F5` | Risk limits | Live actuals vs limits, breach history |
| `F6` | Control plane | RBAC-gated actions |
| `F7` | Data feed health | Source status, lag, completeness % |
| `F8` | Audit log | Immutable, searchable |
| `F9` | **Building view** ★ | Animated living building — all agents visible |
| `F10` | **Agent network graph** ★ | Message flow particles between agents |
| `F11` | **PnL waterfall** ★ | Live ASCII charts per pod |
| `F12` | **News cascade** ★ | Event propagation animation |
| `Enter` on pod | **Pod radar** ★ | Risk spider chart, agent health dots |

### Visual Effects
- **Building view (F9):** Each floor = a pod; penthouse = CEO/CIO/Risk; basement = data/bus. Agent dots pulse on activity, floors dim on halt, capital flows up/down elevator shaft during rebalancing.
- **Agent network (F10):** Nodes connected by edges, colored `·` particles flow along edges by message type (green=capital, yellow=risk, red=kill, blue=data).
- **Kill switch animation:** Full-screen dramatic KILL flash, floor dims, agents go hollow `○`.
- **News cascade (F12):** News event animates routing to subscribed pods with progress bars.
- **Ticker tape:** Persistent scrolling fill feed at bottom of every screen.
- **Data feed health (F7):** X/snscrape `DOWN` displayed as info, never triggers escalation.

### RBAC
| Role | Can see | Can act |
|---|---|---|
| CEO | All firm + pod summaries | Firm objectives, pod onboarding, strategy versions |
| CIO | Pod summaries + allocations | Capital allocation, risk budgets |
| RISK_MANAGER | All risk metrics | Kill-switch (pod + firm), risk limits |
| OPS | All dashboards | Pause/resume, acknowledge alerts |
| READ_ONLY | Firm + pod summaries | Nothing |

### Built-in Alert Rules
- Pod drawdown > 80% of limit → warning; > 95% → critical + auto-pause offer
- Data feed quality < 90% → warning
- X scraper down → info only
- Heartbeat missing > 30s → critical
- Firm VaR breach → critical + requires CEO/Risk acknowledgement

---

## 10. MVP Milestones

### MVP1 — Single pod + governance skeleton + event bus + backtest loop
**Deliverables:**
- `core/models/` — all Pydantic schemas
- `core/bus/` — event bus with topic routing + audit log
- `core/clock/` — simulation clock (backtest mode)
- Pod Alpha only: all 6 internal agents (Researcher, Signal, PM, Risk, Execution Trader, Ops)
- CEO / CIO / Risk Manager skeletons (rule-based stubs)
- `data/adapters/yfinance` + Parquet cache
- `backtest/engine/` — event-driven replay loop
- `backtest/accounting/` — PnL, drawdown, positions
- `execution/paper/` — paper trading adapter
- Isolation tests (all 5 pass)
- Basic TUI: F1 (firm) + F2 (pods) + F8 (audit log)

### MVP2 — All 5 pods + enforced isolation + CIO capital allocator
**Deliverables:**
- Pods Beta, Gamma, Delta, Epsilon (all with 6 internal agents)
- Import boundary linter test
- CIO Agent: LLM-powered allocation with structured tool use
- CEO Agent: LLM-powered mandate + narrative
- Risk Manager: full limit enforcement + kill-switch
- Capital allocation engine: allocate, rebalance, record rationale
- TUI: F3 (drill-down) + F5 (risk) + F6 (control plane) + F9 (building view)

### MVP3 — News scraper agent + event tagging + pod subscriptions
**Deliverables:**
- News Agent: GDELT + FRED + EDGAR + Reuters RSS + StockTwits + Reddit + X (circuit breaker)
- Pod Researcher Agents: pod-specific scrapers wired to central feed
- NewsItem dedup + reliability scoring
- GDELT historical replay integrated into backtest clock
- Delta pod: full event-driven signal pipeline
- TUI: F7 (data feeds) + F12 (news cascade)
- Data completeness halting in backtest engine

### MVP4 — Execution adapter abstraction + paper trading hardening
**Deliverables:**
- ExecutionAdapter ABC + Alpaca paper adapter
- Execution Trader Agent: all 7 validation checks
- RiskApprovalToken two-agent sign-off
- Transaction cost model (3 variants)
- Slippage model
- Corporate actions handling
- TUI: F10 (agent network) + F11 (PnL waterfall) + F4 (event timeline) + F8 (audit log)
- Full integration test: 5 pods, 1 year backtest, all isolation proofs passing

---

## 11. Failure Mode Register

| Risk | Mitigation |
|---|---|
| yfinance unreliability | Multi-source validation, completeness scoring, Alpha Vantage fallback |
| No historical news for backtest | GDELT as backbone (2015+, timestamped, entity-extracted) |
| Look-ahead bias | Strict simulation clock — bars only available after their timestamp |
| Survivorship bias | Point-in-time universe list required for Alpha/Beta pods |
| yfinance rate limiting | Mandatory Parquet cache layer |
| Corporate action errors | Adjusted close + corporate action event log |
| Pod scraper fragility | APIs preferred (FRED, EDGAR); HTML scraping in isolated workers with circuit breakers |
| LLM hallucinations (CIO/CEO) | All LLM outputs through schema validator before any action |
| Silent pod crash | Heartbeat monitor + DuckDB audit log |
| Risk limits misconfigured | Validation on startup — system refuses to run with invalid config |
| X scraper down | INFO level only; pods degrade gracefully; never blocks system |
| Simulation clock drift | Single authoritative clock object; all agents receive same tick |
| DuckDB write contention | Single writer per namespace; reads are concurrent |

---

## 12. Tech Stack

| Component | Technology |
|---|---|
| Language | Python 3.12+ |
| Data models | Pydantic v2 |
| Concurrency | asyncio |
| LLM agents | Anthropic Claude SDK (`claude-sonnet-4-6`) |
| Market data | yfinance, alpha_vantage, ccxt, pycoingecko |
| News/events | gdeltdoc, feedparser, fredapi, praw, snscrape |
| Data storage | Parquet (market data cache), DuckDB (event log, audit trail, state) |
| TUI | Textual + Rich |
| Testing | pytest + pytest-asyncio |
| Logging | structlog |
| Config | YAML + Pydantic validation |
