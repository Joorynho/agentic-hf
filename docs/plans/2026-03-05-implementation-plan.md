# Agentic Hedge Fund Platform — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build a modular, agent-based hedge fund simulation platform with strict pod isolation, LLM-powered governance agents, 5 strategy pods, a backtest engine, and a Textual TUI Mission Control.

**Architecture:** Thread-based pod isolation with serialized-message gateways (process-ready); event-driven backtest replay clock; hybrid rule-based + LLM agents using Anthropic Claude SDK; all cross-boundary data passes through typed Pydantic models only.

**Tech Stack:** Python 3.12+, Pydantic v2, asyncio, Anthropic SDK, yfinance, DuckDB, Textual, pytest, structlog, GDELT, FRED, snscrape

---

## MVP1: Single Pod + Governance Skeleton + Event Bus + Backtest Loop

---

### Task 1: Project Setup

**Files:**
- Create: `pyproject.toml`
- Create: `pytest.ini`
- Create: `src/__init__.py`
- Create: `.gitignore`

**Step 1: Create pyproject.toml**

```toml
[project]
name = "agentic-hf"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = [
    "pydantic>=2.0",
    "anthropic>=0.40.0",
    "yfinance>=0.2.40",
    "pandas>=2.0",
    "numpy>=1.26",
    "duckdb>=0.10",
    "textual>=0.70",
    "rich>=13.0",
    "structlog>=24.0",
    "feedparser>=6.0",
    "praw>=7.0",
    "fredapi>=0.5",
    "gdeltdoc>=1.1",
    "alpha-vantage>=2.3",
    "ccxt>=4.0",
    "pycoingecko>=3.0",
    "pyarrow>=14.0",
    "snscrape>=0.7",
    "aiohttp>=3.9",
    "tenacity>=8.0",
]

[project.optional-dependencies]
dev = ["pytest>=8.0", "pytest-asyncio>=0.23", "pytest-cov>=4.0"]

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]
```

**Step 2: Create directory structure**

```bash
mkdir -p src/core/{models,bus,clock,logging}
mkdir -p src/agents/{ceo,cio,risk,quant,news}
mkdir -p src/pods/{base,runtime,templates}
mkdir -p src/data/{adapters,cache,feeds}
mkdir -p src/backtest/{engine,accounting}
mkdir -p src/execution/{base,paper}
mkdir -p src/mission_control/{tui,control,alerts}
mkdir -p src/config/schemas
mkdir -p tests/{isolation,risk,backtest,integration}
mkdir -p docs/plans
touch src/__init__.py
touch src/core/__init__.py src/core/models/__init__.py
touch src/core/bus/__init__.py src/core/clock/__init__.py
touch src/agents/__init__.py src/pods/__init__.py
touch src/data/__init__.py src/backtest/__init__.py
touch src/execution/__init__.py src/mission_control/__init__.py
```

**Step 3: Install dependencies**

```bash
pip install -e ".[dev]"
```

**Step 4: Verify install**

```bash
python -c "import pydantic, anthropic, yfinance, duckdb, textual; print('OK')"
```
Expected: `OK`

**Step 5: Commit**

```bash
git init
git add pyproject.toml pytest.ini .gitignore
git commit -m "chore: project setup"
```

---

### Task 2: Core Models — Enums and AgentMessage

**Files:**
- Create: `src/core/models/enums.py`
- Create: `src/core/models/messages.py`
- Create: `tests/test_models.py`

**Step 1: Write failing test**

```python
# tests/test_models.py
from src.core.models.enums import EventType
from src.core.models.messages import AgentMessage
import uuid

def test_agent_message_serializes_to_json():
    msg = AgentMessage(
        id=uuid.uuid4(),
        timestamp="2024-01-01T09:30:00",
        sender="risk_manager",
        recipient="pod.alpha.gateway",
        topic="governance.alpha",
        payload={"action": "halt"},
        correlation_id=None,
    )
    data = msg.model_dump_json()
    assert "risk_manager" in data
    assert "governance.alpha" in data

def test_event_type_has_required_values():
    assert EventType.MARKET_DATA
    assert EventType.NEWS
    assert EventType.RISK_BREACH
    assert EventType.KILL_SWITCH
    assert EventType.ALLOCATION_CHANGE
    assert EventType.POD_STARTED
    assert EventType.POD_HALTED
```

**Step 2: Run test — expect FAIL**

```bash
pytest tests/test_models.py -v
```
Expected: `ImportError` or `ModuleNotFoundError`

**Step 3: Implement enums.py**

```python
# src/core/models/enums.py
from enum import Enum

class EventType(str, Enum):
    MARKET_DATA = "market_data"
    NEWS = "news"
    RISK_BREACH = "risk_breach"
    KILL_SWITCH = "kill_switch"
    ALLOCATION_CHANGE = "allocation_change"
    POD_STARTED = "pod_started"
    POD_HALTED = "pod_halted"
    DATA_QUALITY_ALERT = "data_quality_alert"
    HEARTBEAT = "heartbeat"
    ORDER_SUBMITTED = "order_submitted"
    ORDER_FILLED = "order_filled"
    ORDER_REJECTED = "order_rejected"
    MANDATE_UPDATE = "mandate_update"
    REBALANCE = "rebalance"

class PodStatus(str, Enum):
    ACTIVE = "active"
    PAUSED = "paused"
    HALTED = "halted"
    ERROR = "error"
    INITIALIZING = "initializing"

class Side(str, Enum):
    BUY = "buy"
    SELL = "sell"

class OrderType(str, Enum):
    MARKET = "market"
    LIMIT = "limit"
    VWAP = "vwap"

class TimeHorizon(str, Enum):
    INTRADAY = "intraday"
    SWING = "swing"
    WEEKLY = "weekly"
    MONTHLY = "monthly"

class AgentType(str, Enum):
    RULE_BASED = "rule_based"
    LLM_ASSISTED = "llm_assisted"

class AlertSeverity(str, Enum):
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"
```

**Step 4: Implement messages.py**

```python
# src/core/models/messages.py
from __future__ import annotations
from datetime import datetime
from uuid import UUID, uuid4
from pydantic import BaseModel, Field
from .enums import EventType

class AgentMessage(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    timestamp: datetime
    sender: str
    recipient: str
    topic: str
    payload: dict
    correlation_id: UUID | None = None

    model_config = {"frozen": True}

class Event(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    timestamp: datetime
    event_type: EventType
    source: str
    data: dict
    tags: list[str] = Field(default_factory=list)

    model_config = {"frozen": True}
```

**Step 5: Run test — expect PASS**

```bash
pytest tests/test_models.py -v
```

**Step 6: Commit**

```bash
git add src/core/models/ tests/test_models.py
git commit -m "feat: core message and event models"
```

---

### Task 3: Core Models — Pod Config and Risk Budget

**Files:**
- Create: `src/core/models/config.py`
- Modify: `tests/test_models.py`

**Step 1: Add failing tests**

```python
# append to tests/test_models.py
from src.core.models.config import PodConfig, RiskBudget, ExecutionConfig, BacktestConfig
from src.core.models.enums import TimeHorizon, AgentType

def test_pod_config_validates_risk_budget():
    cfg = PodConfig(
        pod_id="alpha",
        name="Pod Alpha",
        strategy_family="momentum",
        universe=["AAPL", "MSFT", "GOOGL"],
        time_horizon=TimeHorizon.SWING,
        risk_budget=RiskBudget(
            target_vol=0.12, max_leverage=1.5, max_drawdown=0.10,
            max_concentration=0.05, max_sector_exposure=0.30,
            liquidity_min_adv_pct=0.01, var_limit_95=0.02, es_limit_95=0.03,
        ),
        execution=ExecutionConfig(
            style="passive", max_participation_rate=0.10,
            allowed_venues=["paper"], order_types=["market", "limit"],
        ),
        backtest=BacktestConfig(
            start_date="2020-01-01", end_date="2023-12-31",
            min_history_days=252, walk_forward_folds=3,
            latency_ms=100, tcm_bps=5.0, slippage_model="sqrt_impact",
        ),
        pm_agent_type=AgentType.RULE_BASED,
    )
    assert cfg.pod_id == "alpha"
    assert cfg.risk_budget.target_vol == 0.12

def test_risk_budget_rejects_invalid_vol():
    import pytest
    with pytest.raises(Exception):
        RiskBudget(
            target_vol=2.0,  # > 100% — invalid
            max_leverage=1.5, max_drawdown=0.10,
            max_concentration=0.05, max_sector_exposure=0.30,
            liquidity_min_adv_pct=0.01, var_limit_95=0.02, es_limit_95=0.03,
        )
```

**Step 2: Run — expect FAIL**

```bash
pytest tests/test_models.py::test_pod_config_validates_risk_budget -v
```

**Step 3: Implement config.py**

```python
# src/core/models/config.py
from __future__ import annotations
from datetime import date
from typing import Literal
from pydantic import BaseModel, Field, field_validator
from .enums import TimeHorizon, AgentType

class RiskBudget(BaseModel):
    target_vol: float = Field(gt=0, lt=1.0)
    max_leverage: float = Field(gt=0, le=10.0)
    max_drawdown: float = Field(gt=0, lt=1.0)
    max_concentration: float = Field(gt=0, le=1.0)
    max_sector_exposure: float = Field(gt=0, le=1.0)
    liquidity_min_adv_pct: float = Field(gt=0, le=1.0)
    var_limit_95: float = Field(gt=0, lt=1.0)
    es_limit_95: float = Field(gt=0, lt=1.0)

class ExecutionConfig(BaseModel):
    style: Literal["passive", "aggressive", "neutral"]
    max_participation_rate: float = Field(gt=0, le=1.0)
    allowed_venues: list[str]
    order_types: list[str]

class BacktestConfig(BaseModel):
    start_date: date
    end_date: date
    min_history_days: int = Field(gt=0)
    walk_forward_folds: int = Field(gt=0)
    latency_ms: int = Field(ge=0)
    tcm_bps: float = Field(ge=0)
    slippage_model: Literal["fixed", "sqrt_impact", "linear"]

class PodConfig(BaseModel):
    pod_id: str
    name: str
    strategy_family: str
    universe: list[str]
    time_horizon: TimeHorizon
    risk_budget: RiskBudget
    execution: ExecutionConfig
    backtest: BacktestConfig
    pm_agent_type: AgentType
    enabled: bool = True
```

**Step 4: Run — expect PASS**

```bash
pytest tests/test_models.py -v
```

**Step 5: Commit**

```bash
git add src/core/models/config.py tests/test_models.py
git commit -m "feat: pod config and risk budget models"
```

---

### Task 4: Core Models — Market Data and Execution

**Files:**
- Create: `src/core/models/market.py`
- Create: `src/core/models/execution.py`

**Step 1: Add failing tests**

```python
# append to tests/test_models.py
from src.core.models.market import Bar, NewsItem
from src.core.models.execution import Order, Fill, Position, RiskApprovalToken
from src.core.models.enums import Side, OrderType
import uuid; from datetime import datetime

def test_bar_model():
    bar = Bar(symbol="AAPL", timestamp=datetime(2024,1,2,9,30),
              open=185.0, high=186.5, low=184.2, close=186.0,
              volume=50_000_000, adj_close=186.0, source="yfinance")
    assert bar.symbol == "AAPL"

def test_order_has_strategy_tag():
    order = Order(pod_id="alpha", symbol="AAPL", side=Side.BUY,
                  order_type=OrderType.MARKET, quantity=100,
                  limit_price=None, timestamp=datetime.now(),
                  strategy_tag="momentum_cross")
    assert order.strategy_tag == "momentum_cross"

def test_risk_approval_token_expires():
    import time
    token = RiskApprovalToken(pod_id="alpha", order_id=uuid.uuid4(),
                               expires_ms=50)
    assert token.is_valid()
    time.sleep(0.1)
    assert not token.is_valid()
```

**Step 2: Run — expect FAIL**

```bash
pytest tests/test_models.py::test_bar_model -v
```

**Step 3: Implement market.py**

```python
# src/core/models/market.py
from __future__ import annotations
from datetime import datetime
from uuid import UUID, uuid4
from pydantic import BaseModel, Field

class Bar(BaseModel):
    symbol: str
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float
    adj_close: float | None = None
    source: str
    model_config = {"frozen": True}

class NewsItem(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    timestamp: datetime
    source: str
    headline: str
    body_snippet: str = Field(max_length=500)
    entities: list[str] = Field(default_factory=list)
    sentiment: float = Field(ge=-1.0, le=1.0, default=0.0)
    event_tags: list[str] = Field(default_factory=list)
    reliability_score: float = Field(ge=0.0, le=1.0, default=0.5)
    dedupe_hash: str
    model_config = {"frozen": True}
```

**Step 4: Implement execution.py**

```python
# src/core/models/execution.py
from __future__ import annotations
import time
from datetime import datetime
from uuid import UUID, uuid4
from pydantic import BaseModel, Field
from .enums import Side, OrderType

class Order(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    pod_id: str
    symbol: str
    side: Side
    order_type: OrderType
    quantity: float = Field(gt=0)
    limit_price: float | None = None
    timestamp: datetime
    strategy_tag: str
    model_config = {"frozen": True}

class Fill(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    order_id: UUID
    pod_id: str
    symbol: str
    side: Side
    quantity: float
    price: float
    commission: float
    timestamp: datetime
    model_config = {"frozen": True}

class Position(BaseModel):
    pod_id: str
    symbol: str
    quantity: float
    avg_cost: float
    market_value: float
    unrealised_pnl: float
    last_updated: datetime

class RejectedOrder(BaseModel):
    order_id: UUID
    reason: str
    timestamp: datetime = Field(default_factory=datetime.now)

class RiskApprovalToken(BaseModel):
    pod_id: str
    order_id: UUID
    issued_at_ms: float = Field(default_factory=lambda: time.time() * 1000)
    expires_ms: float = 500.0  # token valid for 500ms

    def is_valid(self) -> bool:
        return (time.time() * 1000 - self.issued_at_ms) < self.expires_ms
```

**Step 5: Run — expect PASS**

```bash
pytest tests/test_models.py -v
```

**Step 6: Commit**

```bash
git add src/core/models/ tests/test_models.py
git commit -m "feat: market data and execution models"
```

---

### Task 5: Core Models — PodSummary

**Files:**
- Create: `src/core/models/pod_summary.py`

**Step 1: Add failing test**

```python
# append to tests/test_models.py
from src.core.models.pod_summary import PodSummary, PodRiskMetrics, PodExposureBucket
from src.core.models.enums import PodStatus

def test_pod_summary_has_no_raw_positions():
    summary = PodSummary(
        pod_id="alpha", timestamp=datetime.now(),
        status=PodStatus.ACTIVE,
        risk_metrics=PodRiskMetrics(
            pod_id="alpha", timestamp=datetime.now(),
            nav=1_000_000, daily_pnl=5000, drawdown_from_hwm=-0.01,
            current_vol_ann=0.09, gross_leverage=1.2, net_leverage=0.8,
            var_95_1d=0.012, es_95_1d=0.018,
        ),
        exposure_buckets=[
            PodExposureBucket(asset_class="equity_us", direction="long",
                              notional_pct_nav=0.85)
        ],
        expected_return_estimate=0.12,
        turnover_daily_pct=0.05,
        heartbeat_ok=True,
        error_message=None,
    )
    assert not hasattr(summary, "positions")
    assert not hasattr(summary, "signal_value")
    assert summary.pod_id == "alpha"
```

**Step 2: Run — expect FAIL**

```bash
pytest tests/test_models.py::test_pod_summary_has_no_raw_positions -v
```

**Step 3: Implement pod_summary.py**

```python
# src/core/models/pod_summary.py
from __future__ import annotations
from datetime import datetime
from typing import Literal
from uuid import UUID, uuid4
from pydantic import BaseModel, Field
from .enums import PodStatus

class PodRiskMetrics(BaseModel):
    pod_id: str
    timestamp: datetime
    nav: float
    daily_pnl: float
    drawdown_from_hwm: float
    current_vol_ann: float
    gross_leverage: float
    net_leverage: float
    var_95_1d: float
    es_95_1d: float

class PodExposureBucket(BaseModel):
    asset_class: str
    direction: Literal["long", "short"]
    notional_pct_nav: float

class PodSummary(BaseModel):
    pod_id: str
    timestamp: datetime
    status: PodStatus
    risk_metrics: PodRiskMetrics
    exposure_buckets: list[PodExposureBucket]
    expected_return_estimate: float
    turnover_daily_pct: float
    heartbeat_ok: bool
    error_message: str | None = None
    # NOTE: No positions, signals, or model parameters — by design
```

**Step 4: Run — expect PASS**

```bash
pytest tests/test_models.py -v
```

**Step 5: Export all models from package**

```python
# src/core/models/__init__.py
from .enums import EventType, PodStatus, Side, OrderType, TimeHorizon, AgentType, AlertSeverity
from .messages import AgentMessage, Event
from .config import PodConfig, RiskBudget, ExecutionConfig, BacktestConfig
from .market import Bar, NewsItem
from .execution import Order, Fill, Position, RejectedOrder, RiskApprovalToken
from .pod_summary import PodSummary, PodRiskMetrics, PodExposureBucket
```

**Step 6: Commit**

```bash
git add src/core/models/ tests/test_models.py
git commit -m "feat: complete core model layer"
```

---

### Task 6: Event Bus — Pub/Sub with Topic Access Control

**Files:**
- Create: `src/core/bus/event_bus.py`
- Create: `src/core/bus/exceptions.py`
- Create: `tests/test_bus.py`

**Step 1: Write failing tests**

```python
# tests/test_bus.py
import pytest, asyncio
from src.core.bus.event_bus import EventBus
from src.core.bus.exceptions import TopicAccessError
from src.core.models.messages import AgentMessage
from datetime import datetime

@pytest.fixture
def bus():
    return EventBus()

@pytest.mark.asyncio
async def test_publish_and_receive(bus):
    received = []
    await bus.subscribe("test.topic", lambda msg: received.append(msg))
    msg = AgentMessage(timestamp=datetime.now(), sender="cio",
                       recipient="broadcast", topic="test.topic",
                       payload={"x": 1})
    await bus.publish("test.topic", msg, publisher_id="cio")
    await asyncio.sleep(0.01)
    assert len(received) == 1

@pytest.mark.asyncio
async def test_pod_cannot_publish_to_sibling_gateway(bus):
    msg = AgentMessage(timestamp=datetime.now(), sender="pod.alpha",
                       recipient="pod.beta", topic="pod.beta.gateway",
                       payload={})
    with pytest.raises(TopicAccessError):
        await bus.publish("pod.beta.gateway", msg, publisher_id="pod.alpha")

@pytest.mark.asyncio
async def test_governance_only_published_by_authorized(bus):
    msg = AgentMessage(timestamp=datetime.now(), sender="pod.alpha",
                       recipient="pod.alpha", topic="governance.alpha",
                       payload={})
    with pytest.raises(TopicAccessError):
        await bus.publish("governance.alpha", msg, publisher_id="pod.alpha")
```

**Step 2: Run — expect FAIL**

```bash
pytest tests/test_bus.py -v
```

**Step 3: Implement exceptions.py**

```python
# src/core/bus/exceptions.py
class TopicAccessError(PermissionError):
    """Raised when a publisher tries to publish to a topic it doesn't own."""
    pass
```

**Step 4: Implement event_bus.py**

```python
# src/core/bus/event_bus.py
from __future__ import annotations
import asyncio
import re
from collections import defaultdict
from typing import Callable, Awaitable
from ..models.messages import AgentMessage
from .exceptions import TopicAccessError

# Topic ownership rules: (pattern, allowed_publisher_pattern)
TOPIC_RULES: list[tuple[str, str]] = [
    (r"^pod\.(\w+)\.gateway$", r"^pod\.\1$"),       # pod.X.gateway → pod.X only
    (r"^governance\.(\w+)$", r"^(ceo|cio|risk_manager)$"),
    (r"^market\.data$", r"^data_feed$"),
    (r"^news\.feed$", r"^news_agent$"),
    (r"^risk\.alert$", r"^risk_manager$"),
    (r"^system\.", r"^system$"),
]

def _check_access(topic: str, publisher_id: str) -> None:
    for topic_pattern, publisher_pattern in TOPIC_RULES:
        m = re.match(topic_pattern, topic)
        if m:
            # Substitute backreferences in publisher pattern
            resolved = re.sub(r"\\(\d+)", lambda x: m.group(int(x.group(1))),
                               publisher_pattern)
            if not re.match(resolved, publisher_id):
                raise TopicAccessError(
                    f"'{publisher_id}' cannot publish to topic '{topic}'"
                )
            return  # matched and passed

class EventBus:
    def __init__(self):
        self._subscribers: dict[str, list[Callable]] = defaultdict(list)
        self._lock = asyncio.Lock()

    async def publish(self, topic: str, message: AgentMessage,
                      publisher_id: str) -> None:
        _check_access(topic, publisher_id)
        handlers = self._subscribers.get(topic, [])
        for handler in handlers:
            if asyncio.iscoroutinefunction(handler):
                asyncio.create_task(handler(message))
            else:
                handler(message)

    async def subscribe(self, topic: str, handler: Callable) -> None:
        async with self._lock:
            self._subscribers[topic].append(handler)

    async def unsubscribe(self, topic: str, handler: Callable) -> None:
        async with self._lock:
            self._subscribers[topic] = [
                h for h in self._subscribers[topic] if h != handler
            ]
```

**Step 5: Run — expect PASS**

```bash
pytest tests/test_bus.py -v
```

**Step 6: Commit**

```bash
git add src/core/bus/ tests/test_bus.py
git commit -m "feat: event bus with topic access control"
```

---

### Task 7: Event Bus — DuckDB Audit Log

**Files:**
- Create: `src/core/bus/audit_log.py`
- Modify: `src/core/bus/event_bus.py`
- Modify: `tests/test_bus.py`

**Step 1: Add failing test**

```python
# append to tests/test_bus.py
import tempfile, os
from src.core.bus.audit_log import AuditLog

@pytest.mark.asyncio
async def test_audit_log_records_every_message():
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "audit.duckdb")
        log = AuditLog(db_path)
        bus = EventBus(audit_log=log)
        msg = AgentMessage(timestamp=datetime.now(), sender="cio",
                           recipient="broadcast", topic="test.topic",
                           payload={"val": 42})
        await bus.subscribe("test.topic", lambda m: None)
        await bus.publish("test.topic", msg, publisher_id="cio")
        await asyncio.sleep(0.01)
        records = log.query("SELECT * FROM messages")
        assert len(records) == 1
        assert records[0]["sender"] == "cio"
```

**Step 2: Run — expect FAIL**

```bash
pytest tests/test_bus.py::test_audit_log_records_every_message -v
```

**Step 3: Implement audit_log.py**

```python
# src/core/bus/audit_log.py
from __future__ import annotations
import duckdb
import json
from datetime import datetime
from ..models.messages import AgentMessage

CREATE_SQL = """
CREATE TABLE IF NOT EXISTS messages (
    id VARCHAR PRIMARY KEY,
    timestamp TIMESTAMP,
    sender VARCHAR,
    recipient VARCHAR,
    topic VARCHAR,
    payload JSON,
    correlation_id VARCHAR
)
"""

class AuditLog:
    def __init__(self, db_path: str = ":memory:"):
        self._conn = duckdb.connect(db_path)
        self._conn.execute(CREATE_SQL)

    def record(self, message: AgentMessage) -> None:
        self._conn.execute(
            "INSERT INTO messages VALUES (?,?,?,?,?,?,?)",
            [str(message.id), message.timestamp, message.sender,
             message.recipient, message.topic,
             json.dumps(message.payload), str(message.correlation_id)]
        )

    def query(self, sql: str) -> list[dict]:
        result = self._conn.execute(sql).fetchall()
        cols = [d[0] for d in self._conn.description]
        return [dict(zip(cols, row)) for row in result]
```

**Step 4: Update EventBus to accept AuditLog**

```python
# src/core/bus/event_bus.py — update __init__ and publish:
class EventBus:
    def __init__(self, audit_log=None):
        self._subscribers = defaultdict(list)
        self._lock = asyncio.Lock()
        self._audit_log = audit_log

    async def publish(self, topic, message, publisher_id):
        _check_access(topic, publisher_id)
        if self._audit_log:
            self._audit_log.record(message)
        handlers = self._subscribers.get(topic, [])
        for handler in handlers:
            if asyncio.iscoroutinefunction(handler):
                asyncio.create_task(handler(message))
            else:
                handler(message)
```

**Step 5: Run — expect PASS**

```bash
pytest tests/test_bus.py -v
```

**Step 6: Commit**

```bash
git add src/core/bus/ tests/test_bus.py
git commit -m "feat: audit log — immutable DuckDB message record"
```

---

### Task 8: Simulation Clock

**Files:**
- Create: `src/core/clock/simulation_clock.py`
- Create: `tests/test_clock.py`

**Step 1: Write failing test**

```python
# tests/test_clock.py
import pytest
from datetime import datetime, date
from src.core.clock.simulation_clock import SimulationClock

def test_backtest_clock_advances_by_day():
    clock = SimulationClock(
        start=datetime(2024, 1, 2),
        end=datetime(2024, 1, 5),
        mode="backtest"
    )
    ticks = list(clock)
    assert len(ticks) == 4
    assert ticks[0] == datetime(2024, 1, 2)
    assert ticks[-1] == datetime(2024, 1, 5)

def test_clock_prevents_lookahead():
    clock = SimulationClock(
        start=datetime(2024, 1, 2),
        end=datetime(2024, 1, 10),
        mode="backtest"
    )
    clock.advance()
    current = clock.now()
    assert current == datetime(2024, 1, 2)
    # Cannot access future
    with pytest.raises(ValueError):
        clock.peek_future(datetime(2024, 1, 5))
```

**Step 2: Run — expect FAIL**

```bash
pytest tests/test_clock.py -v
```

**Step 3: Implement simulation_clock.py**

```python
# src/core/clock/simulation_clock.py
from __future__ import annotations
from datetime import datetime, timedelta
from typing import Iterator, Literal

class SimulationClock:
    def __init__(self, start: datetime, end: datetime,
                 mode: Literal["backtest", "live"] = "backtest",
                 step: timedelta = timedelta(days=1)):
        self._start = start
        self._end = end
        self._mode = mode
        self._step = step
        self._current = start

    def now(self) -> datetime:
        return self._current

    def advance(self) -> datetime | None:
        if self._current >= self._end:
            return None
        self._current += self._step
        return self._current

    def peek_future(self, dt: datetime) -> None:
        if dt > self._current:
            raise ValueError(
                f"Look-ahead bias: cannot access {dt} when clock is at {self._current}"
            )

    def is_done(self) -> bool:
        return self._current >= self._end

    def __iter__(self) -> Iterator[datetime]:
        current = self._start
        while current <= self._end:
            yield current
            current += self._step
```

**Step 4: Run — expect PASS**

```bash
pytest tests/test_clock.py -v
```

**Step 5: Commit**

```bash
git add src/core/clock/ tests/test_clock.py
git commit -m "feat: simulation clock with look-ahead prevention"
```

---

### Task 9: Pod Isolation — PodNamespace and PodGateway

**Files:**
- Create: `src/pods/base/namespace.py`
- Create: `src/pods/base/gateway.py`
- Create: `tests/isolation/test_pod_isolation.py`

**Step 1: Write isolation tests (ship with MVP1)**

```python
# tests/isolation/test_pod_isolation.py
import pytest, asyncio, uuid
from src.pods.base.namespace import PodNamespace
from src.core.bus.event_bus import EventBus
from src.core.bus.exceptions import TopicAccessError
from src.core.models.messages import AgentMessage
from src.core.models.pod_summary import PodSummary, PodRiskMetrics, PodExposureBucket
from src.core.models.enums import PodStatus
from datetime import datetime

def test_pod_cannot_read_sibling_namespace():
    ns_alpha = PodNamespace("alpha")
    ns_beta = PodNamespace("beta")
    ns_alpha.set("signal", 0.95)
    assert ns_beta.get("signal") is None

def test_pod_namespace_key_scoped_internally():
    ns_alpha = PodNamespace("alpha")
    ns_alpha.set("signal", 0.95)
    # Internal key is "alpha::signal" — beta can't construct this
    ns_beta = PodNamespace("beta")
    # Even if beta tries the raw key
    assert ns_beta.get("alpha::signal") is None

@pytest.mark.asyncio
async def test_pod_cannot_publish_to_sibling_gateway():
    bus = EventBus()
    msg = AgentMessage(timestamp=datetime.now(), sender="pod.alpha",
                       recipient="pod.beta", topic="pod.beta.gateway",
                       payload={})
    with pytest.raises(TopicAccessError):
        await bus.publish("pod.beta.gateway", msg, publisher_id="pod.alpha")

@pytest.mark.asyncio
async def test_governance_not_receivable_by_wrong_pod():
    bus = EventBus()
    received_alpha = []
    await bus.subscribe("governance.alpha", lambda m: received_alpha.append(m))
    # Send to beta — alpha should not receive it
    msg = AgentMessage(timestamp=datetime.now(), sender="cio",
                       recipient="pod.beta", topic="governance.beta",
                       payload={"action": "rebalance"})
    await bus.publish("governance.beta", msg, publisher_id="cio")
    await asyncio.sleep(0.05)
    assert len(received_alpha) == 0

def test_pod_summary_has_no_raw_positions_or_signals():
    metrics = PodRiskMetrics(
        pod_id="alpha", timestamp=datetime.now(), nav=1e6,
        daily_pnl=5000, drawdown_from_hwm=-0.01, current_vol_ann=0.09,
        gross_leverage=1.2, net_leverage=0.8, var_95_1d=0.012, es_95_1d=0.018,
    )
    summary = PodSummary(
        pod_id="alpha", timestamp=datetime.now(), status=PodStatus.ACTIVE,
        risk_metrics=metrics,
        exposure_buckets=[PodExposureBucket(
            asset_class="equity_us", direction="long", notional_pct_nav=0.85
        )],
        expected_return_estimate=0.12, turnover_daily_pct=0.05,
        heartbeat_ok=True,
    )
    fields = set(summary.model_fields.keys())
    assert "positions" not in fields
    assert "signal_value" not in fields
    assert "model_params" not in fields
    assert "strategy_tag" not in fields
```

**Step 2: Run — expect FAIL**

```bash
pytest tests/isolation/ -v
```

**Step 3: Implement namespace.py**

```python
# src/pods/base/namespace.py
from __future__ import annotations
from typing import Any

class PodNamespace:
    """Isolated key-value store for a single pod.
    Keys are internally prefixed — a pod cannot address another pod's keys."""

    def __init__(self, pod_id: str):
        self._pod_id = pod_id
        self._store: dict[str, Any] = {}

    def _key(self, key: str) -> str:
        # Prevent cross-pod access even if caller tries to use prefixed key
        bare = key.replace(f"{self._pod_id}::", "")
        return f"{self._pod_id}::{bare}"

    def set(self, key: str, value: Any) -> None:
        self._store[self._key(key)] = value

    def get(self, key: str, default: Any = None) -> Any:
        return self._store.get(self._key(key), default)

    def delete(self, key: str) -> None:
        self._store.pop(self._key(key), None)

    def keys(self) -> list[str]:
        prefix = f"{self._pod_id}::"
        return [k[len(prefix):] for k in self._store if k.startswith(prefix)]
```

**Step 4: Implement gateway.py (minimal for MVP1)**

```python
# src/pods/base/gateway.py
from __future__ import annotations
import asyncio
from typing import AsyncIterator, Callable
from ...core.bus.event_bus import EventBus
from ...core.models.pod_summary import PodSummary
from ...core.models.market import Bar, NewsItem
from ...core.models.messages import AgentMessage
from ...core.models.config import PodConfig
from datetime import datetime

class PodGateway:
    """The ONLY I/O boundary for a pod. Serializes all outbound data."""

    def __init__(self, pod_id: str, bus: EventBus, config: PodConfig):
        self._pod_id = pod_id
        self._bus = bus
        self._config = config
        self._mandate_queue: asyncio.Queue = asyncio.Queue()
        self._bar_queues: list[asyncio.Queue] = []
        self._news_queues: list[asyncio.Queue] = []

    async def emit_summary(self, summary: PodSummary) -> None:
        assert summary.pod_id == self._pod_id, "Pod can only emit its own summary"
        # Serialize to JSON and back — strips any extra fields
        clean = PodSummary.model_validate_json(summary.model_dump_json())
        msg = AgentMessage(
            timestamp=datetime.now(),
            sender=f"pod.{self._pod_id}",
            recipient="broadcast",
            topic=f"pod.{self._pod_id}.gateway",
            payload=clean.model_dump(),
        )
        await self._bus.publish(
            f"pod.{self._pod_id}.gateway", msg,
            publisher_id=f"pod.{self._pod_id}"
        )

    async def receive_mandate(self) -> AgentMessage | None:
        try:
            return self._mandate_queue.get_nowait()
        except asyncio.QueueEmpty:
            return None

    async def subscribe_market_data(self) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue()
        self._bar_queues.append(q)
        return q

    async def push_bar(self, bar: Bar) -> None:
        if bar.symbol in self._config.universe:
            for q in self._bar_queues:
                await q.put(bar)

    async def subscribe_news(self) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue()
        self._news_queues.append(q)
        return q

    async def push_news(self, item: NewsItem) -> None:
        for q in self._news_queues:
            await q.put(item)
```

**Step 5: Run — expect PASS**

```bash
pytest tests/isolation/ -v
```

**Step 6: Commit**

```bash
git add src/pods/base/ tests/isolation/
git commit -m "feat: pod isolation — namespace and gateway; all isolation tests pass"
```

---

### Task 10: Data Adapter — yfinance + Parquet Cache

**Files:**
- Create: `src/data/adapters/base.py`
- Create: `src/data/adapters/yfinance_adapter.py`
- Create: `src/data/cache/parquet_cache.py`
- Create: `tests/test_data.py`

**Step 1: Write failing test**

```python
# tests/test_data.py
import pytest, tempfile, os
from datetime import date
from src.data.adapters.yfinance_adapter import YFinanceAdapter
from src.data.cache.parquet_cache import ParquetCache

@pytest.mark.asyncio
async def test_fetch_bars_returns_bar_objects():
    cache_dir = tempfile.mkdtemp()
    adapter = YFinanceAdapter(cache=ParquetCache(cache_dir))
    bars = await adapter.fetch(
        symbol="AAPL",
        start=date(2024, 1, 2),
        end=date(2024, 1, 10),
    )
    assert len(bars) > 0
    assert bars[0].symbol == "AAPL"
    assert bars[0].close > 0

@pytest.mark.asyncio
async def test_cache_avoids_refetch():
    cache_dir = tempfile.mkdtemp()
    cache = ParquetCache(cache_dir)
    adapter = YFinanceAdapter(cache=cache)
    bars1 = await adapter.fetch("SPY", date(2024, 1, 2), date(2024, 1, 5))
    bars2 = await adapter.fetch("SPY", date(2024, 1, 2), date(2024, 1, 5))
    assert len(bars1) == len(bars2)

def test_completeness_score_detects_gaps():
    cache = ParquetCache(tempfile.mkdtemp())
    score = cache.completeness_score("AAPL", date(2024,1,2), date(2024,1,5))
    assert 0.0 <= score <= 1.0
```

**Step 2: Run — expect FAIL**

```bash
pytest tests/test_data.py -v
```

**Step 3: Implement base.py**

```python
# src/data/adapters/base.py
from abc import ABC, abstractmethod
from datetime import date
from ...core.models.market import Bar

class DataAdapter(ABC):
    @abstractmethod
    async def fetch(self, symbol: str, start: date, end: date) -> list[Bar]:
        ...
```

**Step 4: Implement parquet_cache.py**

```python
# src/data/cache/parquet_cache.py
from __future__ import annotations
import os
from datetime import date
import pandas as pd
from ...core.models.market import Bar

class ParquetCache:
    def __init__(self, cache_dir: str):
        self._dir = cache_dir
        os.makedirs(cache_dir, exist_ok=True)

    def _path(self, symbol: str) -> str:
        return os.path.join(self._dir, f"{symbol}.parquet")

    def get(self, symbol: str, start: date, end: date) -> list[Bar] | None:
        path = self._path(symbol)
        if not os.path.exists(path):
            return None
        df = pd.read_parquet(path)
        mask = (df.index >= pd.Timestamp(start)) & (df.index <= pd.Timestamp(end))
        subset = df[mask]
        if subset.empty:
            return None
        return self._df_to_bars(symbol, subset)

    def save(self, symbol: str, bars: list[Bar]) -> None:
        if not bars:
            return
        records = [b.model_dump() for b in bars]
        df = pd.DataFrame(records).set_index("timestamp")
        path = self._path(symbol)
        if os.path.exists(path):
            existing = pd.read_parquet(path)
            df = pd.concat([existing, df]).drop_duplicates()
        df.to_parquet(path)

    def completeness_score(self, symbol: str, start: date, end: date) -> float:
        bars = self.get(symbol, start, end)
        if bars is None:
            return 0.0
        expected_days = len(pd.bdate_range(start, end))
        return min(1.0, len(bars) / max(1, expected_days))

    def _df_to_bars(self, symbol: str, df: pd.DataFrame) -> list[Bar]:
        bars = []
        for ts, row in df.iterrows():
            bars.append(Bar(
                symbol=symbol, timestamp=ts,
                open=row.get("open", 0), high=row.get("high", 0),
                low=row.get("low", 0), close=row.get("close", 0),
                volume=row.get("volume", 0),
                adj_close=row.get("adj_close"),
                source=row.get("source", "cache"),
            ))
        return bars
```

**Step 5: Implement yfinance_adapter.py**

```python
# src/data/adapters/yfinance_adapter.py
from __future__ import annotations
import asyncio
from datetime import date, datetime
import yfinance as yf
from .base import DataAdapter
from ..cache.parquet_cache import ParquetCache
from ...core.models.market import Bar

class YFinanceAdapter(DataAdapter):
    def __init__(self, cache: ParquetCache):
        self._cache = cache

    async def fetch(self, symbol: str, start: date, end: date) -> list[Bar]:
        cached = self._cache.get(symbol, start, end)
        if cached:
            return cached
        bars = await asyncio.get_event_loop().run_in_executor(
            None, self._fetch_sync, symbol, start, end
        )
        self._cache.save(symbol, bars)
        return bars

    def _fetch_sync(self, symbol: str, start: date, end: date) -> list[Bar]:
        ticker = yf.Ticker(symbol)
        df = ticker.history(start=str(start), end=str(end), auto_adjust=True)
        bars = []
        for ts, row in df.iterrows():
            bars.append(Bar(
                symbol=symbol,
                timestamp=ts.to_pydatetime().replace(tzinfo=None),
                open=float(row["Open"]),
                high=float(row["High"]),
                low=float(row["Low"]),
                close=float(row["Close"]),
                volume=float(row["Volume"]),
                adj_close=float(row["Close"]),
                source="yfinance",
            ))
        return bars
```

**Step 6: Run — expect PASS**

```bash
pytest tests/test_data.py -v
```

**Step 7: Commit**

```bash
git add src/data/ tests/test_data.py
git commit -m "feat: yfinance adapter with parquet cache and completeness scoring"
```

---

### Task 11: Paper Execution Adapter

**Files:**
- Create: `src/execution/base/adapter.py`
- Create: `src/execution/paper/paper_adapter.py`
- Create: `tests/test_execution.py`

**Step 1: Write failing test**

```python
# tests/test_execution.py
import pytest
from datetime import datetime
from uuid import uuid4
from src.execution.paper.paper_adapter import PaperAdapter
from src.core.models.execution import Order, RiskApprovalToken
from src.core.models.market import Bar
from src.core.models.enums import Side, OrderType

@pytest.mark.asyncio
async def test_paper_adapter_fills_market_order():
    adapter = PaperAdapter(tcm_bps=5.0, slippage_model="fixed")
    current_bar = Bar(symbol="AAPL", timestamp=datetime.now(),
                      open=185.0, high=186.5, low=184.2, close=186.0,
                      volume=50_000_000, adj_close=186.0, source="paper")
    order = Order(pod_id="alpha", symbol="AAPL", side=Side.BUY,
                  order_type=OrderType.MARKET, quantity=100,
                  limit_price=None, timestamp=datetime.now(),
                  strategy_tag="test")
    token = RiskApprovalToken(pod_id="alpha", order_id=order.id)
    fill = await adapter.execute(order, token, current_bar)
    assert fill.quantity == 100
    assert fill.price > 0
    assert fill.commission > 0

@pytest.mark.asyncio
async def test_paper_adapter_rejects_expired_token():
    import time
    adapter = PaperAdapter(tcm_bps=5.0)
    bar = Bar(symbol="AAPL", timestamp=datetime.now(), open=185.0,
              high=186.5, low=184.2, close=186.0, volume=1e6,
              adj_close=186.0, source="paper")
    order = Order(pod_id="alpha", symbol="AAPL", side=Side.BUY,
                  order_type=OrderType.MARKET, quantity=100,
                  limit_price=None, timestamp=datetime.now(),
                  strategy_tag="test")
    token = RiskApprovalToken(pod_id="alpha", order_id=order.id, expires_ms=1)
    time.sleep(0.01)
    from src.core.models.execution import RejectedOrder
    result = await adapter.execute(order, token, bar)
    assert isinstance(result, RejectedOrder)
    assert "expired" in result.reason.lower()
```

**Step 2: Run — expect FAIL**

```bash
pytest tests/test_execution.py -v
```

**Step 3: Implement base adapter**

```python
# src/execution/base/adapter.py
from abc import ABC, abstractmethod
from ...core.models.execution import Order, Fill, RejectedOrder, RiskApprovalToken
from ...core.models.market import Bar

class ExecutionAdapter(ABC):
    @abstractmethod
    async def execute(self, order: Order, token: RiskApprovalToken,
                      current_bar: Bar) -> Fill | RejectedOrder:
        ...
```

**Step 4: Implement paper_adapter.py**

```python
# src/execution/paper/paper_adapter.py
from __future__ import annotations
import math
from datetime import datetime
from ..base.adapter import ExecutionAdapter
from ...core.models.execution import Order, Fill, RejectedOrder, RiskApprovalToken
from ...core.models.market import Bar
from ...core.models.enums import Side

class PaperAdapter(ExecutionAdapter):
    def __init__(self, tcm_bps: float = 5.0,
                 slippage_model: str = "fixed"):
        self._tcm_bps = tcm_bps
        self._slippage_model = slippage_model

    async def execute(self, order: Order, token: RiskApprovalToken,
                      current_bar: Bar) -> Fill | RejectedOrder:
        if not token.is_valid():
            return RejectedOrder(order_id=order.id,
                                 reason="risk approval token expired")
        if token.pod_id != order.pod_id:
            return RejectedOrder(order_id=order.id,
                                 reason="token pod_id mismatch")
        fill_price = self._compute_fill_price(order, current_bar)
        commission = fill_price * order.quantity * self._tcm_bps / 10_000
        return Fill(
            order_id=order.id,
            pod_id=order.pod_id,
            symbol=order.symbol,
            side=order.side,
            quantity=order.quantity,
            price=fill_price,
            commission=commission,
            timestamp=datetime.now(),
        )

    def _compute_fill_price(self, order: Order, bar: Bar) -> float:
        base = bar.close
        slip_factor = self._tcm_bps / 10_000
        if self._slippage_model == "sqrt_impact":
            slip_factor *= math.sqrt(order.quantity / max(bar.volume, 1))
        direction = 1.0 if order.side == Side.BUY else -1.0
        return base * (1 + direction * slip_factor)
```

**Step 5: Run — expect PASS**

```bash
pytest tests/test_execution.py -v
```

**Step 6: Commit**

```bash
git add src/execution/ tests/test_execution.py
git commit -m "feat: paper execution adapter with TCM and token validation"
```

---

### Task 12: Backtest Accounting Engine

**Files:**
- Create: `src/backtest/accounting/portfolio.py`
- Create: `tests/backtest/test_accounting.py`

**Step 1: Write failing tests**

```python
# tests/backtest/test_accounting.py
import pytest
from datetime import datetime
from uuid import uuid4
from src.backtest.accounting.portfolio import PortfolioAccountant
from src.core.models.execution import Fill, Position
from src.core.models.enums import Side

def make_fill(symbol, side, qty, price):
    return Fill(order_id=uuid4(), pod_id="alpha", symbol=symbol,
                side=side, quantity=qty, price=price,
                commission=qty*price*0.0005, timestamp=datetime.now())

def test_buy_creates_position():
    acc = PortfolioAccountant(pod_id="alpha", initial_nav=1_000_000)
    fill = make_fill("AAPL", Side.BUY, 100, 185.0)
    acc.record_fill(fill)
    pos = acc.get_position("AAPL")
    assert pos.quantity == 100
    assert abs(pos.avg_cost - 185.0) < 0.01

def test_pnl_calculated_correctly():
    acc = PortfolioAccountant(pod_id="alpha", initial_nav=1_000_000)
    fill = make_fill("AAPL", Side.BUY, 100, 185.0)
    acc.record_fill(fill)
    acc.mark_to_market({"AAPL": 190.0})
    pos = acc.get_position("AAPL")
    assert abs(pos.unrealised_pnl - 500.0) < 1.0  # 100 * (190-185)

def test_drawdown_tracked_from_hwm():
    acc = PortfolioAccountant(pod_id="alpha", initial_nav=1_000_000)
    acc.mark_to_market({})  # NAV = 1M, HWM = 1M
    fill = make_fill("AAPL", Side.BUY, 100, 185.0)
    acc.record_fill(fill)
    acc.mark_to_market({"AAPL": 180.0})  # loss of 500
    assert acc.drawdown_from_hwm() < 0
```

**Step 2: Run — expect FAIL**

```bash
pytest tests/backtest/test_accounting.py -v
```

**Step 3: Implement portfolio.py**

```python
# src/backtest/accounting/portfolio.py
from __future__ import annotations
from datetime import datetime
from ...core.models.execution import Fill, Position
from ...core.models.enums import Side

class PortfolioAccountant:
    def __init__(self, pod_id: str, initial_nav: float):
        self._pod_id = pod_id
        self._cash = initial_nav
        self._positions: dict[str, dict] = {}
        self._hwm = initial_nav
        self._nav_history: list[float] = [initial_nav]

    def record_fill(self, fill: Fill) -> None:
        sym = fill.symbol
        if sym not in self._positions:
            self._positions[sym] = {"quantity": 0.0, "avg_cost": 0.0,
                                     "market_value": 0.0, "unrealised_pnl": 0.0}
        pos = self._positions[sym]
        if fill.side == Side.BUY:
            total_cost = pos["quantity"] * pos["avg_cost"] + fill.quantity * fill.price
            pos["quantity"] += fill.quantity
            pos["avg_cost"] = total_cost / pos["quantity"] if pos["quantity"] else 0
            self._cash -= fill.quantity * fill.price + fill.commission
        else:
            pos["quantity"] -= fill.quantity
            self._cash += fill.quantity * fill.price - fill.commission
            if pos["quantity"] == 0:
                del self._positions[sym]

    def mark_to_market(self, prices: dict[str, float]) -> float:
        total_market_value = 0.0
        for sym, pos in self._positions.items():
            price = prices.get(sym, pos["avg_cost"])
            pos["market_value"] = pos["quantity"] * price
            pos["unrealised_pnl"] = pos["quantity"] * (price - pos["avg_cost"])
            total_market_value += pos["market_value"]
        nav = self._cash + total_market_value
        self._hwm = max(self._hwm, nav)
        self._nav_history.append(nav)
        return nav

    def get_position(self, symbol: str) -> Position | None:
        pos = self._positions.get(symbol)
        if not pos:
            return None
        return Position(
            pod_id=self._pod_id, symbol=symbol,
            quantity=pos["quantity"], avg_cost=pos["avg_cost"],
            market_value=pos["market_value"],
            unrealised_pnl=pos["unrealised_pnl"],
            last_updated=datetime.now(),
        )

    def nav(self) -> float:
        return self._nav_history[-1] if self._nav_history else 0

    def drawdown_from_hwm(self) -> float:
        if self._hwm == 0:
            return 0.0
        return (self.nav() - self._hwm) / self._hwm

    def all_positions(self) -> list[Position]:
        return [self.get_position(s) for s in self._positions if self.get_position(s)]
```

**Step 4: Run — expect PASS**

```bash
pytest tests/backtest/test_accounting.py -v
```

**Step 5: Commit**

```bash
git add src/backtest/accounting/ tests/backtest/
git commit -m "feat: portfolio accounting — fills, PnL, drawdown"
```

---

### Task 13: Backtest Engine — Event-Driven Replay Loop

**Files:**
- Create: `src/backtest/engine/backtest_runner.py`
- Create: `tests/backtest/test_engine.py`

**Step 1: Write failing test**

```python
# tests/backtest/test_engine.py
import pytest, tempfile
from datetime import date, datetime
from src.backtest.engine.backtest_runner import BacktestRunner
from src.core.models.config import PodConfig, RiskBudget, ExecutionConfig, BacktestConfig
from src.core.models.enums import TimeHorizon, AgentType

def make_alpha_config():
    return PodConfig(
        pod_id="alpha", name="Pod Alpha", strategy_family="momentum",
        universe=["AAPL", "MSFT"],
        time_horizon=TimeHorizon.SWING,
        risk_budget=RiskBudget(
            target_vol=0.12, max_leverage=1.5, max_drawdown=0.10,
            max_concentration=0.05, max_sector_exposure=0.30,
            liquidity_min_adv_pct=0.01, var_limit_95=0.02, es_limit_95=0.03,
        ),
        execution=ExecutionConfig(
            style="passive", max_participation_rate=0.10,
            allowed_venues=["paper"], order_types=["market"],
        ),
        backtest=BacktestConfig(
            start_date=date(2024,1,2), end_date=date(2024,1,31),
            min_history_days=10, walk_forward_folds=1,
            latency_ms=0, tcm_bps=5.0, slippage_model="fixed",
        ),
        pm_agent_type=AgentType.RULE_BASED,
    )

@pytest.mark.asyncio
async def test_backtest_runs_without_error():
    cache_dir = tempfile.mkdtemp()
    runner = BacktestRunner(cache_dir=cache_dir)
    config = make_alpha_config()
    result = await runner.run(config)
    assert result is not None
    assert "nav_final" in result
    assert "total_bars_processed" in result
    assert result["total_bars_processed"] > 0

@pytest.mark.asyncio
async def test_backtest_is_deterministic():
    cache_dir = tempfile.mkdtemp()
    config = make_alpha_config()
    r1 = await BacktestRunner(cache_dir=cache_dir).run(config)
    r2 = await BacktestRunner(cache_dir=cache_dir).run(config)
    assert abs(r1["nav_final"] - r2["nav_final"]) < 0.01
```

**Step 2: Run — expect FAIL**

```bash
pytest tests/backtest/test_engine.py -v
```

**Step 3: Implement backtest_runner.py**

```python
# src/backtest/engine/backtest_runner.py
from __future__ import annotations
import asyncio
from datetime import timedelta
from ...core.clock.simulation_clock import SimulationClock
from ...core.bus.event_bus import EventBus
from ...core.bus.audit_log import AuditLog
from ...core.models.config import PodConfig
from ...data.adapters.yfinance_adapter import YFinanceAdapter
from ...data.cache.parquet_cache import ParquetCache
from ...execution.paper.paper_adapter import PaperAdapter
from ...backtest.accounting.portfolio import PortfolioAccountant
from ...pods.base.gateway import PodGateway
from ...pods.base.namespace import PodNamespace

class BacktestRunner:
    def __init__(self, cache_dir: str, initial_nav: float = 1_000_000):
        self._cache_dir = cache_dir
        self._initial_nav = initial_nav

    async def run(self, config: PodConfig) -> dict:
        audit_log = AuditLog()
        bus = EventBus(audit_log=audit_log)
        cache = ParquetCache(self._cache_dir)
        adapter = YFinanceAdapter(cache=cache)
        exec_adapter = PaperAdapter(tcm_bps=config.backtest.tcm_bps,
                                    slippage_model=config.backtest.slippage_model)
        accountant = PortfolioAccountant(config.pod_id, self._initial_nav)
        namespace = PodNamespace(config.pod_id)
        gateway = PodGateway(config.pod_id, bus, config)
        clock = SimulationClock(
            start=config.backtest.start_date.replace(
                year=config.backtest.start_date.year
            ) if hasattr(config.backtest.start_date, 'replace') else
            __import__('datetime').datetime.combine(
                config.backtest.start_date, __import__('datetime').time()
            ),
            end=__import__('datetime').datetime.combine(
                config.backtest.end_date, __import__('datetime').time()
            ),
            mode="backtest",
        )

        # Pre-fetch all data
        all_bars: dict[str, list] = {}
        for symbol in config.universe:
            bars = await adapter.fetch(
                symbol, config.backtest.start_date, config.backtest.end_date
            )
            all_bars[symbol] = bars

        total_bars = 0
        for tick in clock:
            tick_prices = {}
            for symbol, bars in all_bars.items():
                day_bars = [b for b in bars if b.timestamp.date() == tick.date()]
                for bar in day_bars:
                    await gateway.push_bar(bar)
                    tick_prices[symbol] = bar.close
                    total_bars += 1
            if tick_prices:
                accountant.mark_to_market(tick_prices)

        return {
            "nav_final": accountant.nav(),
            "drawdown_from_hwm": accountant.drawdown_from_hwm(),
            "total_bars_processed": total_bars,
            "pod_id": config.pod_id,
        }
```

**Step 4: Run — expect PASS**

```bash
pytest tests/backtest/test_engine.py -v
```

**Step 5: Commit**

```bash
git add src/backtest/engine/ tests/backtest/test_engine.py
git commit -m "feat: backtest engine — deterministic event-driven replay"
```

---

### Task 14: Pod Alpha — Simple Momentum PM Agent

**Files:**
- Create: `src/pods/templates/alpha/momentum_pm.py`
- Create: `tests/test_alpha_pod.py`

**Step 1: Write failing test**

```python
# tests/test_alpha_pod.py
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
    agent = MomentumPMAgent(pod_id="alpha", namespace=ns,
                             fast_window=3, slow_window=5)
    bars = make_bars([100, 101, 102, 103, 104, 105, 106])
    signal = agent.compute_signal("AAPL", bars)
    assert signal > 0  # positive = buy

def test_momentum_generates_sell_signal_on_downtrend():
    ns = PodNamespace("alpha")
    agent = MomentumPMAgent(pod_id="alpha", namespace=ns,
                             fast_window=3, slow_window=5)
    bars = make_bars([110, 109, 108, 107, 106, 105, 104])
    signal = agent.compute_signal("AAPL", bars)
    assert signal < 0  # negative = sell/flat

def test_momentum_returns_zero_with_insufficient_data():
    ns = PodNamespace("alpha")
    agent = MomentumPMAgent(pod_id="alpha", namespace=ns)
    bars = make_bars([100, 101])
    signal = agent.compute_signal("AAPL", bars)
    assert signal == 0.0
```

**Step 2: Run — expect FAIL**

```bash
pytest tests/test_alpha_pod.py -v
```

**Step 3: Implement momentum_pm.py**

```python
# src/pods/templates/alpha/momentum_pm.py
from __future__ import annotations
import statistics
from ...base.namespace import PodNamespace
from ....core.models.market import Bar

class MomentumPMAgent:
    """Rule-based momentum PM: fast MA vs slow MA crossover signal."""

    def __init__(self, pod_id: str, namespace: PodNamespace,
                 fast_window: int = 10, slow_window: int = 30):
        self._pod_id = pod_id
        self._ns = namespace
        self._fast = fast_window
        self._slow = slow_window

    def compute_signal(self, symbol: str, bars: list[Bar]) -> float:
        if len(bars) < self._slow:
            return 0.0
        closes = [b.close for b in bars]
        fast_ma = statistics.mean(closes[-self._fast:])
        slow_ma = statistics.mean(closes[-self._slow:])
        signal = (fast_ma - slow_ma) / slow_ma
        self._ns.set(f"signal::{symbol}", signal)
        return signal
```

**Step 4: Run — expect PASS**

```bash
pytest tests/test_alpha_pod.py -v
```

**Step 5: Commit**

```bash
git add src/pods/templates/alpha/ tests/test_alpha_pod.py
git commit -m "feat: pod alpha momentum PM agent with MA crossover signal"
```

---

### Task 15: Risk Manager Agent Skeleton + Kill Switch

**Files:**
- Create: `src/agents/risk/risk_manager.py`
- Create: `tests/risk/test_risk_manager.py`

**Step 1: Write failing tests**

```python
# tests/risk/test_risk_manager.py
import pytest, asyncio
from src.agents.risk.risk_manager import RiskManager
from src.core.bus.event_bus import EventBus
from src.core.bus.audit_log import AuditLog
from src.core.models.pod_summary import PodSummary, PodRiskMetrics, PodExposureBucket
from src.core.models.config import RiskBudget
from src.core.models.enums import PodStatus
from datetime import datetime

def make_summary(pod_id, drawdown, vol, leverage):
    return PodSummary(
        pod_id=pod_id, timestamp=datetime.now(), status=PodStatus.ACTIVE,
        risk_metrics=PodRiskMetrics(
            pod_id=pod_id, timestamp=datetime.now(), nav=1_000_000,
            daily_pnl=0, drawdown_from_hwm=drawdown,
            current_vol_ann=vol, gross_leverage=leverage, net_leverage=leverage,
            var_95_1d=0.01, es_95_1d=0.015,
        ),
        exposure_buckets=[],
        expected_return_estimate=0.10,
        turnover_daily_pct=0.02,
        heartbeat_ok=True,
    )

def make_budget():
    return RiskBudget(
        target_vol=0.12, max_leverage=1.5, max_drawdown=0.10,
        max_concentration=0.05, max_sector_exposure=0.30,
        liquidity_min_adv_pct=0.01, var_limit_95=0.02, es_limit_95=0.03,
    )

@pytest.mark.asyncio
async def test_risk_manager_triggers_halt_on_drawdown_breach():
    audit = AuditLog()
    bus = EventBus(audit_log=audit)
    rm = RiskManager(bus=bus)
    halted = []
    async def on_risk_alert(msg):
        if msg.payload.get("action") == "halt":
            halted.append(msg.payload["pod_id"])
    await bus.subscribe("risk.alert", on_risk_alert)
    summary = make_summary("alpha", drawdown=-0.11, vol=0.09, leverage=1.2)
    budget = make_budget()
    await rm.check_pod(summary, budget)
    await asyncio.sleep(0.05)
    assert "alpha" in halted

@pytest.mark.asyncio
async def test_risk_manager_no_action_within_limits():
    bus = EventBus()
    rm = RiskManager(bus=bus)
    alerts = []
    await bus.subscribe("risk.alert", lambda m: alerts.append(m))
    summary = make_summary("alpha", drawdown=-0.05, vol=0.09, leverage=1.2)
    budget = make_budget()
    await rm.check_pod(summary, budget)
    await asyncio.sleep(0.05)
    assert len(alerts) == 0
```

**Step 2: Run — expect FAIL**

```bash
pytest tests/risk/ -v
```

**Step 3: Implement risk_manager.py**

```python
# src/agents/risk/risk_manager.py
from __future__ import annotations
from datetime import datetime
from ...core.bus.event_bus import EventBus
from ...core.models.pod_summary import PodSummary
from ...core.models.config import RiskBudget
from ...core.models.messages import AgentMessage

class RiskManager:
    """Rule-based. Never delegates limit enforcement to an LLM."""

    def __init__(self, bus: EventBus):
        self._bus = bus

    async def check_pod(self, summary: PodSummary, budget: RiskBudget) -> None:
        m = summary.risk_metrics
        breaches = []

        if m.drawdown_from_hwm < -budget.max_drawdown:
            breaches.append(
                f"drawdown {m.drawdown_from_hwm:.1%} exceeds limit {-budget.max_drawdown:.1%}"
            )
        if m.current_vol_ann > budget.target_vol * 1.5:
            breaches.append(
                f"vol {m.current_vol_ann:.1%} exceeds 1.5x target {budget.target_vol:.1%}"
            )
        if m.gross_leverage > budget.max_leverage:
            breaches.append(
                f"leverage {m.gross_leverage:.2f}x exceeds limit {budget.max_leverage:.2f}x"
            )

        if breaches:
            await self._send_halt(summary.pod_id, breaches)

    async def _send_halt(self, pod_id: str, reasons: list[str]) -> None:
        msg = AgentMessage(
            timestamp=datetime.now(),
            sender="risk_manager",
            recipient=f"pod.{pod_id}.gateway",
            topic="risk.alert",
            payload={
                "action": "halt",
                "pod_id": pod_id,
                "reasons": reasons,
            },
        )
        await self._bus.publish("risk.alert", msg, publisher_id="risk_manager")

    async def firm_kill_switch(self, authorized_by: str, reason: str) -> None:
        msg = AgentMessage(
            timestamp=datetime.now(),
            sender="risk_manager",
            recipient="broadcast",
            topic="risk.alert",
            payload={
                "action": "firm_kill_switch",
                "authorized_by": authorized_by,
                "reason": reason,
            },
        )
        await self._bus.publish("risk.alert", msg, publisher_id="risk_manager")
```

**Step 4: Run — expect PASS**

```bash
pytest tests/risk/ -v
```

**Step 5: Commit**

```bash
git add src/agents/risk/ tests/risk/
git commit -m "feat: risk manager — rule-based limit enforcement and kill switch"
```

---

### Task 16: Basic Textual TUI — MVP1 Screens

**Files:**
- Create: `src/mission_control/tui/app.py`
- Create: `src/mission_control/tui/screens/firm_dashboard.py`
- Create: `src/mission_control/tui/screens/pod_table.py`
- Create: `src/mission_control/tui/screens/audit_screen.py`

**Step 1: Implement app.py**

```python
# src/mission_control/tui/app.py
from textual.app import App, ComposeResult
from textual.binding import Binding
from .screens.firm_dashboard import FirmDashboard
from .screens.pod_table import PodTable
from .screens.audit_screen import AuditScreen

class AgenticHFApp(App):
    CSS = """
    Screen { background: #0a0a0a; }
    .header { background: #1a1a2e; color: #00ff88; height: 3; }
    .panel { border: solid #333; padding: 1; margin: 1; }
    .metric-label { color: #888; }
    .metric-value { color: #00ff88; }
    .status-active { color: #00ff88; }
    .status-paused { color: #ffaa00; }
    .status-halted { color: #ff4444; }
    .status-error  { color: #ff0000; }
    """

    BINDINGS = [
        Binding("f1", "show_firm", "Firm"),
        Binding("f2", "show_pods", "Pods"),
        Binding("f8", "show_audit", "Audit"),
        Binding("q", "quit", "Quit"),
    ]

    def compose(self) -> ComposeResult:
        yield FirmDashboard()

    def action_show_firm(self) -> None:
        self.push_screen(FirmDashboard())

    def action_show_pods(self) -> None:
        self.push_screen(PodTable())

    def action_show_audit(self) -> None:
        self.push_screen(AuditScreen())

def run():
    app = AgenticHFApp()
    app.run()

if __name__ == "__main__":
    run()
```

**Step 2: Implement firm_dashboard.py**

```python
# src/mission_control/tui/screens/firm_dashboard.py
from textual.screen import Screen
from textual.app import ComposeResult
from textual.widgets import Static, Header, Footer
from textual.containers import Horizontal, Vertical
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

DEMO_METRICS = {
    "nav": "$10,241,330", "daily_pnl": "+$241,330 (+2.41%)",
    "drawdown": "-1.2% from HWM", "sharpe": "1.84 (YTD)",
    "vol": "9.2% ann.", "var_95": "1.24% NAV",
    "gross_leverage": "1.31x", "net_leverage": "0.87x",
}

class FirmMetrics(Static):
    def render(self):
        table = Table.grid(padding=(0,2))
        table.add_column("Metric", style="dim")
        table.add_column("Value", style="bold green")
        for k, v in DEMO_METRICS.items():
            table.add_row(k.replace("_"," ").title(), v)
        return Panel(table, title="[bold]FIRM DASHBOARD[/bold]",
                     border_style="#333333")

class FirmDashboard(Screen):
    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        yield FirmMetrics()
        yield Footer()
```

**Step 3: Implement pod_table.py**

```python
# src/mission_control/tui/screens/pod_table.py
from textual.screen import Screen
from textual.app import ComposeResult
from textual.widgets import DataTable, Header, Footer

DEMO_PODS = [
    ("Alpha", "● ACTIVE", "+$84,210", "+0.82%", "9.1%", "-1.2%", "20.0%"),
    ("Beta",  "● ACTIVE", "+$62,100", "+0.61%", "7.8%", "-0.8%", "18.5%"),
    ("Gamma", "● ACTIVE", "+$55,900", "+0.55%", "10.2%","-2.1%", "25.0%"),
    ("Delta", "⚠ PAUSED", "+$21,400", "+0.21%", "14.1%","-5.8%", "16.5%"),
    ("Epsilon","● ACTIVE","+$17,720", "+0.17%", "9.8%", "-1.4%", "20.0%"),
]

class PodTable(Screen):
    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        table = DataTable()
        table.add_columns("Pod","Status","Daily PnL","PnL%","Vol","Drawdown","Capital%")
        for row in DEMO_PODS:
            table.add_row(*row)
        yield table
        yield Footer()
```

**Step 4: Implement audit_screen.py**

```python
# src/mission_control/tui/screens/audit_screen.py
from textual.screen import Screen
from textual.app import ComposeResult
from textual.widgets import DataTable, Header, Footer

class AuditScreen(Screen):
    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        table = DataTable()
        table.add_columns("Time", "Actor", "Action", "Target", "Reason")
        table.add_row("14:32:07","risk_manager","HALT","delta","DD -5.8%")
        table.add_row("14:28:12","cio","REBALANCE","alpha+2%","monthly review")
        yield table
        yield Footer()
```

**Step 5: Test TUI launches**

```bash
python -m src.mission_control.tui.app
```
Expected: Terminal UI opens with F1/F2/F8 navigation. Press Q to quit.

**Step 6: Commit**

```bash
git add src/mission_control/tui/
git commit -m "feat: mission control TUI — F1 firm dashboard, F2 pod table, F8 audit"
```

---

### Task 17: MVP1 Integration Test

**Files:**
- Create: `tests/integration/test_mvp1.py`

**Step 1: Write integration test**

```python
# tests/integration/test_mvp1.py
import pytest, tempfile
from datetime import date
from src.backtest.engine.backtest_runner import BacktestRunner
from src.core.models.config import PodConfig, RiskBudget, ExecutionConfig, BacktestConfig
from src.core.models.enums import TimeHorizon, AgentType
from src.agents.risk.risk_manager import RiskManager
from src.core.bus.event_bus import EventBus
from src.core.bus.audit_log import AuditLog
from src.core.models.pod_summary import PodSummary, PodRiskMetrics, PodExposureBucket
from src.core.models.enums import PodStatus
from datetime import datetime

@pytest.mark.asyncio
async def test_mvp1_full_run():
    cache_dir = tempfile.mkdtemp()
    config = PodConfig(
        pod_id="alpha", name="Pod Alpha", strategy_family="momentum",
        universe=["AAPL", "MSFT"],
        time_horizon=TimeHorizon.SWING,
        risk_budget=RiskBudget(
            target_vol=0.12, max_leverage=1.5, max_drawdown=0.10,
            max_concentration=0.05, max_sector_exposure=0.30,
            liquidity_min_adv_pct=0.01, var_limit_95=0.02, es_limit_95=0.03,
        ),
        execution=ExecutionConfig(
            style="passive", max_participation_rate=0.10,
            allowed_venues=["paper"], order_types=["market"],
        ),
        backtest=BacktestConfig(
            start_date=date(2024,1,2), end_date=date(2024,3,31),
            min_history_days=10, walk_forward_folds=1,
            latency_ms=0, tcm_bps=5.0, slippage_model="fixed",
        ),
        pm_agent_type=AgentType.RULE_BASED,
    )

    result = await BacktestRunner(cache_dir=cache_dir).run(config)
    assert result["total_bars_processed"] > 0
    assert result["nav_final"] > 0
    print(f"\nMVP1 Integration: {result}")

@pytest.mark.asyncio
async def test_mvp1_all_isolation_tests_pass():
    # Re-run isolation suite programmatically
    from tests.isolation.test_pod_isolation import (
        test_pod_cannot_read_sibling_namespace,
        test_pod_namespace_key_scoped_internally,
        test_pod_summary_has_no_raw_positions_or_signals,
    )
    test_pod_cannot_read_sibling_namespace()
    test_pod_namespace_key_scoped_internally()
    test_pod_summary_has_no_raw_positions_or_signals()
```

**Step 2: Run full test suite**

```bash
pytest tests/ -v --tb=short
```
Expected: All tests pass including isolation suite.

**Step 3: Final MVP1 commit**

```bash
git add tests/integration/
git commit -m "feat: MVP1 complete — single pod + event bus + backtest engine + TUI + isolation"
```

---

## MVP2: All 5 Pods + CIO Capital Allocator + LLM Agents

> Tasks 18–28 (detailed in next plan section)

**Overview:**
- Task 18: Pod Beta (Stat Arb / Pairs PM)
- Task 19: Pod Gamma (Macro PM — LLM-assisted via Claude)
- Task 20: Pod Delta (Event-Driven PM — LLM-assisted)
- Task 21: Pod Epsilon (Vol Regime PM)
- Task 22: CIO Agent — Claude SDK capital allocation with structured tool use
- Task 23: CEO Agent — Claude SDK mandate + narrative
- Task 24: Import boundary linter test
- Task 25: Capital allocation engine + rebalancing
- Task 26: TUI F9 Building View (animated)
- Task 27: TUI F6 Control Plane + RBAC
- Task 28: MVP2 integration test (5 pods, isolation proofs)

---

## MVP3: News Agent + Event Tagging + Pod Subscriptions

> Tasks 29–38

**Overview:**
- Task 29: News Agent base + dedup + reliability scoring
- Task 30: GDELT adapter (historical news backbone)
- Task 31: FRED adapter (economic releases)
- Task 32: Reuters RSS + feedparser adapter
- Task 33: EDGAR 8-K adapter
- Task 34: Reddit (PRAW) adapter
- Task 35: StockTwits adapter
- Task 36: X/snscrape adapter with circuit breaker
- Task 37: Pod Researcher Agents wired to central feed
- Task 38: TUI F7 data feed health + F12 news cascade

---

## MVP4: Execution Hardening + Paper Trading + Full TUI

> Tasks 39–46

**Overview:**
- Task 39: Execution Trader Agent — all 7 validation checks
- Task 40: RiskApprovalToken two-agent sign-off in pod loop
- Task 41: TCM (3 variants) + slippage model
- Task 42: Corporate actions handling
- Task 43: Alpaca paper adapter
- Task 44: TUI F10 agent network graph (message flow particles)
- Task 45: TUI F11 PnL waterfall charts
- Task 46: Full 5-pod integration test: 1-year backtest, all isolation proofs

---

## Skill Usage Reminders

- Before implementing any task: invoke `superpowers:test-driven-development`
- When hitting a bug or test failure: invoke `superpowers:systematic-debugging`
- When using Claude SDK (Tasks 22, 23): invoke `claude-developer-platform`
- When building TUI screens (Tasks 16, 26, 44, 45): invoke `frontend-design`
- Before claiming any milestone complete: invoke `superpowers:verification-before-completion`
- After completing MVP1/MVP2/MVP3: invoke `superpowers:requesting-code-review`
