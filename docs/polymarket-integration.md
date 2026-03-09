# Polymarket Integration

## Overview

Gamma pod (macro/treasury strategy) consumes Polymarket odds for event probability signals during the research and signal computation phases.

**Architecture:**
- GammaResearcher calls PolymarketAdapter.fetch_signals() during each run_cycle()
- Fetches odds tagged: macro, fed, inflation, gdp, etc.
- Stores signals in PodNamespace under key "polymarket_signals"
- GammaSignalAgent retrieves signals + uses implied probabilities in macro_score calculation
- On error or missing API key: gracefully degrades to empty signal list (no pod crash)

## API Setup

### Requirement: POLYMARKET_API_KEY

1. Add to `.env` at project root:
   ```
   POLYMARKET_API_KEY=your_api_key_here
   ```

2. Get API key: https://docs.polymarket.com (register for CLOB API access)

3. Key-less fallback: If not set, PolymarketAdapter returns empty list (pod still operates normally)

## Data Model

**PolymarketSignal (Pydantic model)**
Located at: `src/core/models/polymarket.py`

```python
class PolymarketSignal(BaseModel):
    market_id: str                # Unique market ID
    question: str                 # Market question text
    yes_price: float              # CLOB best bid for YES (0-1)
    no_price: float               # CLOB best bid for NO (0-1)
    implied_prob: float           # yes_price / (yes_price + no_price)
    spread: float                 # yes_price - no_price (liquidity metric)
    volume_24h: float             # 24-hour trading volume
    open_interest: float          # Total open interest
    timestamp: datetime           # Fetch timestamp
    tags: list[str]               # Market tags (e.g., ["macro", "fed"])
```

## Integration Architecture

### Component: PolymarketAdapter
**Location:** `src/data/polymarket.py`

- **Interface:** Async fetch_signals(tags: list[str]) → list[PolymarketSignal]
- **Data Source:** CLOB API (`https://clob.polymarket.com`)
- **Authentication:** `L1-MM-POLYGON` header with API key from `.env`
- **Caching:** None in MVP2 (future Parquet cache in MVP3)
- **Error Handling:** Non-blocking. API failures logged INFO level, returns empty list
- **Rate Limiting:** Check Polymarket API docs; conservative approach: one fetch per pod run_cycle (60s live, variable in backtest)

**Code Signature:**
```python
class PolymarketAdapter:
    async def fetch_signals(self, tags: list[str]) -> list[PolymarketSignal]:
        """Fetch markets matching tags from CLOB API."""
```

### Component: GammaResearcher
**Location:** `src/pods/templates/gamma/researcher.py`

- **Dependency:** PolymarketAdapter (injected via __init__)
- **Method:** `async def run_cycle(context: dict) -> dict`
- **Action:** Fetch signals tagged ["macro", "fed", "inflation", "gdp"]
- **Storage:** `self.store("polymarket_signals", signals)` in PodNamespace
- **Return:** `{"universe": [...], "poly_signals": signals_dict_list}`
- **Error Handling:** Non-blocking. API failures logged INFO level, gracefully returns empty list

**Code Pattern:**
```python
async def run_cycle(self, context: dict) -> dict:
    """Fetch universe + Polymarket signals."""
    poly_signals = []
    if self.polymarket_adapter:
        try:
            signals = await self.polymarket_adapter.fetch_signals(
                tags=["macro", "fed", "inflation", "gdp"]
            )
            poly_signals = [s.model_dump(mode="json") for s in signals]
        except Exception as e:
            logger.info("Polymarket fetch failed (non-critical): %s", e)
            poly_signals = []

    self.store("polymarket_signals", poly_signals)

    return {
        "universe": UNIVERSE,
        "poly_signals": poly_signals,
    }
```

### Component: GammaSignalAgent
**Location:** `src/pods/templates/gamma/signal_agent.py`

- **Source:** `self.recall("polymarket_signals", [])`
- **Processing:**
  ```python
  macro_confidence = mean([s["implied_prob"] for s in poly_signals]) if poly_signals else 0.5
  macro_score = momentum_score * macro_confidence
  ```
- **Storage:** `self.store("macro_score", macro_score)` and `self.store("polymarket_confidence", macro_confidence)`
- **Fallback:** If no signals, macro_confidence defaults to 0.5 (neutral probability)

**Code Pattern:**
```python
def run_cycle(self, context: dict) -> dict:
    """Compute macro score using Polymarket signals."""
    poly_signals = self.recall("polymarket_signals", [])

    # Compute macro confidence from implied probabilities
    macro_confidence = (
        sum(s["implied_prob"] for s in poly_signals) / len(poly_signals)
        if poly_signals else 0.5
    )

    # Blend with momentum signal
    momentum_score = ...  # existing logic
    macro_score = momentum_score * macro_confidence

    self.store("macro_score", macro_score)
    self.store("polymarket_confidence", macro_confidence)

    return {"macro_score": macro_score}
```

### Component: SessionManager
**Location:** `src/mission_control/session_manager.py`

- **Pod Init:** Creates PolymarketAdapter, passes to GammaResearcher
- **Injection Pattern:**
  ```python
  polymarket_adapter = PolymarketAdapter()  # loads POLYMARKET_API_KEY from .env
  gamma_researcher = GammaResearcher(
      adapter=polymarket_adapter,
      ...
  )
  ```
- **Lifecycle:** Adapter shared across all backtest/live runs within session

## Data Flow

```
PolymarketAdapter
    ↓ (fetch_signals via CLOB API)
GammaResearcher.run_cycle()
    ↓ (self.store("polymarket_signals", signals))
PodNamespace
    ↓ (self.recall("polymarket_signals", []))
GammaSignalAgent.run_cycle()
    ↓ (compute macro_score = momentum × confidence)
PodNamespace (macro_score, polymarket_confidence)
    ↓ (self.recall("macro_score", 0))
GammaPMAgent
    ↓ (uses macro_score in position sizing, risk calculations)
Portfolio
```

## Testing

### Unit Tests
**File:** `tests/pods/test_gamma_pod.py`

Run all Gamma pod tests:
```bash
cd "/c/Users/PW1868/Agentic HF"
pytest tests/pods/test_gamma_pod.py -v
```

Tests cover:
1. GammaResearcher accepts PolymarketAdapter dependency
2. GammaResearcher fetches signals from adapter
3. GammaResearcher stores signals in namespace with correct key
4. GammaSignalAgent retrieves and uses signals for macro_score
5. Signal fields preserved through pipeline (market_id, implied_prob, etc.)
6. Empty signal list gracefully handled (macro_confidence defaults to 0.5)
7. API errors logged but don't crash pod

### Integration Tests
**File:** `tests/integration/test_gamma_full.py`

Run end-to-end tests:
```bash
cd "/c/Users/PW1868/Agentic HF"
pytest tests/integration/test_gamma_full.py -v
```

Tests cover:
1. Full Gamma cycle with single Polymarket signal
2. Multiple signals in one cycle
3. Empty response handling (graceful degradation)
4. Signal field preservation through researcher → namespace → signal_agent
5. SessionManager injection of PolymarketAdapter
6. Macro_score correctly blended with momentum signal

### Run Full Test Suite
```bash
cd "/c/Users/PW1868/Agentic HF"
pytest tests/pods/test_gamma_pod.py tests/integration/test_gamma_full.py -v
```

Expected: All tests PASS

### Run Tests with Coverage
```bash
pytest tests/pods/test_gamma_pod.py tests/integration/test_gamma_full.py --cov=src.pods.templates.gamma --cov=src.data.polymarket
```

## Error Handling

### Graceful Degradation
- **If POLYMARKET_API_KEY not set:** PolymarketAdapter returns `[]`, pod continues (no errors)
- **If API call fails:** logs INFO level, returns `[]` (non-critical)
- **If response parsing fails:** logs INFO level, returns `[]` (non-critical)
- **If market tags don't exist:** API returns `[]`, handled gracefully

### No Blocking
- Polymarket fetch is non-blocking; pod doesn't wait indefinitely
- If API slow: cached previous signals used from prior cycle (retrieved from PodNamespace)
- If API down: macro_confidence defaults to 0.5 (neutral market probability)
- Pod continues executing trades at default signal weights

### Logging
- **INFO level:** Non-critical API failures (used in production/backtest, no alerting)
- **ERROR level:** Unexpected exceptions (reserved for serious failures)
- **DEBUG level:** Signal fetch details, field counts, API latency

**Example Log Output:**
```
INFO: Polymarket fetch failed (non-critical): Connection timeout
INFO: Fetched 0 Polymarket signals for tags: ['macro', 'fed', 'inflation', 'gdp']
INFO: Using default macro_confidence=0.5 (no signals available)
```

## Performance

### Current MVP2
- **Fetch Frequency:** One per pod run_cycle (60 seconds in live mode)
- **API Latency:** ~500-1000ms typical (Polymarket CLOB API)
- **Memory:** ~1KB per signal cached in PodNamespace
- **Cache:** None (fetched fresh each cycle)

### Future MVP3: Caching
- Polymarket signals cached in Parquet for 30 minutes
- Reduces API calls, speeds up backtest reruns
- Cache keyed by: (tags, timestamp_bucket)
- Invalidation: 30-minute TTL or manual refresh

### Rate Limiting
Check https://docs.polymarket.com for current API limits (typically 100-300 req/min for CLOB API)

**Conservative Approach:**
- **Backtest:** Fetch every run_cycle (variable interval, not rate-limited)
- **Live:** Fetch every 60 seconds (one pod run_cycle interval)
- **Multiple Pods:** No conflict — only Gamma pod fetches Polymarket signals

### Optimization Notes
- Use circuit breaker pattern if API consistently slow (future MVP3)
- Batch signal fetches across multiple pods (future enhancement, MVP3+)
- Pre-cache high-volume markets at session startup (future, MVP3)

## Future: MVP3 Data Source Pattern

Same architecture pattern for other data sources:

### Example: DeltaResearcher + GDELTAdapter
```python
# src/data/gdelt.py
class GDELTAdapter:
    async def fetch_events(self, keywords: list[str]) -> list[GeopoliticalEvent]:
        """Fetch recent geopolitical events from GDELT."""

# src/pods/templates/delta/researcher.py
class DeltaResearcher:
    def __init__(self, gdelt_adapter: GDELTAdapter):
        self.gdelt_adapter = gdelt_adapter

    async def run_cycle(self, context: dict) -> dict:
        events = await self.gdelt_adapter.fetch_events(["ukraine", "fed", "israel"])
        self.store("gdelt_events", events)
        return {"events": events}

# src/mission_control/session_manager.py
gdelt_adapter = GDELTAdapter()
delta_researcher = DeltaResearcher(gdelt_adapter=gdelt_adapter)
```

### Other Data Sources (MVP3)
- **EDGAR** (SEC filings) → DeltaResearcher
- **FRED** (macro indicators) → GammaResearcher
- **X/Reddit** (sentiment) → Pod researchers
- **Yahoo Finance News** → AlphaResearcher

All follow same architecture:
1. Adapter class with async fetch method
2. Inject into researcher __init__
3. Store in namespace with key "source_name_signals"
4. Consume in signal agent via recall()
5. SessionManager wires injection per pod

## Verification Checklist

After completing integration, run these checks to ensure correctness:

```bash
cd "/c/Users/PW1868/Agentic HF"

# 1. Unit tests pass
pytest tests/pods/test_gamma_pod.py -v
# Expected: All PASS ✓

# 2. Integration tests pass
pytest tests/integration/test_gamma_full.py -v
# Expected: All PASS ✓

# 3. No import errors
python -c "from src.pods.templates.gamma.researcher import GammaResearcher; print('✓ GammaResearcher imports')"
python -c "from src.data.polymarket import PolymarketAdapter; print('✓ PolymarketAdapter imports')"
python -c "from src.core.models.polymarket import PolymarketSignal; print('✓ PolymarketSignal imports')"

# 4. SessionManager builds without errors
python << 'EOF'
import asyncio
from src.mission_control.session_manager import SessionManager
from src.core.bus.event_bus import EventBus
async def test():
    manager = SessionManager(EventBus())
    await manager.start_live_session()
    print("✓ SessionManager initialized 5 pods")
asyncio.run(test())
EOF

# 5. Live session works (optional — requires .env with POLYMARKET_API_KEY)
python run.py
# Open http://localhost:8000, wait 60s for pod data
# Expected: Gamma NAV updates, Polymarket signals logged, no WebSocket errors
```

## Troubleshooting

| Issue | Cause | Solution |
|-------|-------|----------|
| `POLYMARKET_API_KEY not found` | .env missing or key not set | Add `POLYMARKET_API_KEY=...` to `.env` at project root, reload pod |
| `PolymarketSignal validation error` | API response schema changed | Check Polymarket API docs; update PolymarketSignal model fields |
| `Empty poly_signals list` | API returned no results for tags | Check market tags exist on Polymarket, verify tags match API response |
| `macro_score is 0.5` | No signals fetched (default confidence) | Check API key validity, network connectivity, Polymarket API status |
| `Test fails: "polymarket_signals" not in namespace` | Storage key mismatch | Verify key is `"polymarket_signals"` (exact spelling in researcher + signal_agent) |
| `API timeout in tests` | Adapter not mocked | Use `AsyncMock()` to mock `PolymarketAdapter.fetch_signals()` in unit tests |
| `Session crashes on startup` | PolymarketAdapter init error | Check .env file syntax, ensure POLYMARKET_API_KEY is valid |
| `Backtest slow with Polymarket` | API called every cycle | Add caching in MVP3, or adjust backtest frequency |

## References

- **Polymarket Docs:** https://docs.polymarket.com
- **CLOB API Endpoint:** https://clob.polymarket.com
- **Gamma Markets API:** https://gamma-api.polymarket.com
- **Agentic HF Architecture:** See `CLAUDE.md` in project root
- **Pod Isolation Contracts:** See `tests/isolation/` for boundary tests
- **Project Tech Stack:** Python 3.12, Pydantic v2, asyncio, DuckDB
- **Pod Namespace Pattern:** `src/pods/base/namespace.py`

## Integration Checklist for Developers

When adding a new data source (MVP3+), follow this checklist:

- [ ] Create Adapter class in `src/data/<source>.py` with async fetch method
- [ ] Define Pydantic model for signal/event in `src/core/models/<source>.py`
- [ ] Inject adapter into pod researcher via `__init__`
- [ ] Call `self.store(key, signals)` with unique key name
- [ ] Consume in signal agent via `self.recall(key, default=[])`
- [ ] Add unit tests in `tests/pods/test_<pod>_pod.py`
- [ ] Add integration tests in `tests/integration/test_<pod>_full.py`
- [ ] Wire injection in `SessionManager.__init__`
- [ ] Document in this file under "Future: MVP3 Data Source Pattern"
- [ ] Verify no circular imports, all imports absolute from `src.`
- [ ] Run full test suite: `pytest tests/ -v`

---

*Last Updated: 2026-03-09*
*Integration Pattern: Adapter dependency injection into pod researchers*
*Architecture: Non-blocking, graceful degradation, error isolation*
