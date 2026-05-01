# Agentic Hedge Fund — Lessons Learned

Capture patterns from corrections and debugging to prevent repeat mistakes.

---

## API & External Services

### Nitter is dead
- All public Nitter instances are non-functional (403, empty responses) as of 2026
- Do not attempt Nitter-based X/Twitter scraping
- Solution: use direct news RSS feeds from financial outlets (Yahoo Finance, CNBC, Bloomberg, etc.)

### OpenRouter free-tier rate limits
- Free models on OpenRouter hit 429 errors aggressively (per-minute limits)
- All Venice-provider models rate-limit simultaneously
- Solution: `src/core/llm.py` rotates through 8 free models automatically. Agents fall back to rule-based mode on total failure
- Long-term fix: run Qwen locally via Ollama (no rate limits)

### FRED API is reliable but needs a key
- Free registration, no credit card required
- 23+ macro series available; fetch all at once to reduce calls
- Key stored in `.env` as `FRED_API_KEY`

### Polymarket API
- Use Gamma Markets API (`gamma-api.polymarket.com`) for search/metadata, not the CLOB API
- Filter for macro relevance — exclude sports, entertainment, pop culture
- `BLOCKED_SERIES` and `MACRO_KEYWORDS` in `polymarket_adapter.py` control filtering

---

## Python / Libraries

### Pydantic v2.11 — model_fields
- Access `model_fields` on the **class**, not the instance
- `MyModel.model_fields` (correct) vs `instance.model_fields` (deprecated, triggers warning)

### DuckDB on Windows — file lock
- DuckDB holds an exclusive file lock on the database file
- Always call `audit_log.close()` before `tempfile.TemporaryDirectory` cleanup
- Otherwise: `PermissionError` on Windows

### asyncio + network adapters
- Always wrap external fetches in `asyncio.wait_for(coro, timeout=12)`
- Set `socket.setdefaulttimeout(8)` in adapters that use synchronous HTTP
- News adapters (GDELT, RSS, social) must not block the main event loop

---

## Testing

### Global conftest.py disables LLM keys (critical for speed)
- `tests/conftest.py` clears `OPENROUTER_API_KEY`, `OPENAI_API_KEY`, `ANTHROPIC_API_KEY` via `pytest_configure` (runs before imports)
- This forces all CEO/CIO/PM agents into rule-based mode — no network calls, no 15s timeouts
- Without this, tests that touch governance or PM agents make real API calls (8 models × 15s timeout each)
- Impact: test suite went from 773s → 78s (10x speedup)
- If a test specifically needs LLM behavior, mock `llm_chat` directly instead of using real API keys

### Never cache has_llm_key() at module level
- `_HAS_LLM = has_llm_key()` at module top-level evaluates at import time, before conftest can clear env vars
- Always call `has_llm_key()` at runtime (inside methods) so conftest patching works
- Fixed in gamma/delta PM agents; equities/fx/crypto/commodities already call at runtime

### Tests must not depend on .env secrets
- `tests/conftest.py` handles this globally now — no need for per-test `monkeypatch.delenv()`
- Individual tests can still override if they need specific key behavior

### Mock yfinance in tests
- Real yfinance calls add 5-18s per test and are flaky (rate limits, network)
- Patch `YFinanceAdapter._fetch_sync` with deterministic synthetic bars
- Use midnight timestamps for bars if the ParquetCache will filter by date range

### Log message assertions are fragile
- Tests that assert on log message content break when log formats change
- Use substring matching (`"Failed to process" in msg`) not exact strings
- When updating log messages in production code, grep tests for the old string

### Keep asyncio.sleep short in event loop tests
- `run_event_loop(interval_seconds=0.01)` iterates every 10ms — no need to sleep 2-3s
- Use `asyncio.sleep(0.3)` for event loop tests (gives 30+ iterations)
- Longer sleeps only add wall-clock time without improving coverage

### Timing-sensitive async tests
- Tests using `asyncio.sleep(0.15)` with `governance_freq=1` can miss governance calls if `fetch_bars` runs out of `side_effect` entries
- Use `return_value` (never exhausts) instead of short `side_effect` lists

---

## Frontend / Dashboard

### Browser caching
- `index.html` was being cached by the browser, causing stale UI
- Fix: serve with `Cache-Control: no-cache, no-store, must-revalidate` header
- Applied in `src/web/server.py`

### Error isolation in render functions
- If one render call fails (e.g., `renderHistoricalChart`), it can prevent subsequent renders
- Wrap each render call in its own `try/catch` in `updateResearchTab`
- Pattern: independent UI sections should never cascade-fail

### localStorage for rolling data
- `signalHistory` stored in localStorage with 7-day max age
- Always validate entries on load (`e && e.ts && Array.isArray(e.signals)`)
- Prune stale entries on each update cycle

### Capital allocation displays must not use NAV as allocation
- Assigned capital and current NAV answer different questions. A pod can lose money and still have the same mandate allocation.
- Governance allocation tiles should use mandate weights against starting/allocated capital; show current NAV as secondary performance context.
- If no complete mandate weights are available, fall back to each pod's starting capital share, not the current NAV share.

### Closed trade APIs should expose display dates
- UI tables should not have to infer entry/exit dates by slicing timestamps everywhere.
- Closed-trade API rows should include `entry_date` and `exit_date` aliases, while keeping `entry_time` and `exit_time` for detail views and calculations.

### Performance UI must label closed P&L vs NAV P&L
- Closed-trade outcomes and pod returns are different ledgers. Closed outcomes exclude open/unrealized P&L; pod returns include current open positions through NAV.
- Dashboard labels should say "Closed P&L" when using closed trades, and show NAV P&L separately when users need to reconcile to Pod Returns.
- Prefer the complete closed-trades API for dashboard outcome stats over a partial/restored in-memory tracker.

### Risk dashboards need display fallbacks for missing enriched payloads
- If a WebSocket summary is missing enriched risk reports, the dashboard should still render a transparent fallback from available open positions.
- Fallbacks are for visibility only; rule-based backend risk enforcement remains the authority.

### LLM calls are core product behavior
- Do not default the local trading session into rule-based mode just to avoid quota/rate-limit noise.
- PM/CIO/CEO LLM reasoning is central to the product; use API keys by default when present.
- Keep explicit opt-out switches for tests/debugging, but make disabling LLM calls an intentional choice, not the default.

### Every entered trade needs an entry thesis
- Do not rely on a generic `reasoning` field alone for open-position display. Execution metadata should carry an explicit `entry_thesis` into `PortfolioAccountant`.
- Preserve `reasoning` for audit/closed-trade history, but use `entry_thesis` as the canonical dashboard field.
- For older state, open-position APIs should fall back to stored metadata `reasoning` so positions are not displayed with blank theses.

### Wide operational tables need bounded two-axis scrolling
- Tables with many columns, such as Closed Positions, should not rely on page-level scrolling alone.
- Use a dedicated wrapper with `overflow: auto`, a bounded max height, and a table `min-width` so horizontal and vertical scrolling are both available without stretching the whole dashboard.

### Dashboard capital labels must match the primary number
- If a card headline shows current NAV, label it as NAV and keep mandate allocation as secondary context.
- If a card headline shows mandate allocation, do not put it under a generic capital heading that users will compare to operational NAV.
- For trading dashboards, prefer showing the live economic value first and the allocation policy underneath.

### Pod resets must cover local state, history, and broker hydration
- A pod reset is not complete if only `memory.json` is changed; broker positions will hydrate back into the pod on restart.
- Back up `memory.json`, `memory.md`, and `state.db` before deleting per-pod state.
- Clear per-pod trades, closed-trade state, outcome trackers, signal scores, enrichment, and NAV history together, then add a fresh reset NAV row so charts do not undercount firm NAV.
- Closing broker positions must use positive order quantities even when the broker reports short positions with negative signed `qty`.

### PM entry theses must be tradeable, not just narrative
- A thesis is weak if it only says "inflation/geopolitics are bullish" without a trigger, driver decomposition, invalidation, and instrument fit.
- For gold and precious-metals trades, explicitly check real-yield direction, USD trend, Fed reaction function, positioning/flows, central-bank demand, and geopolitical risk as a conditional catalyst.
- Never let an LLM assert "negative real rates" unless the real-yield data in the prompt is actually below zero. If the data is missing or mixed, the PM should say that instead of inventing certainty.
- Geopolitical risk belongs in the thesis, but only as a catalyst/risk-premium argument with second-order effects; it can be bullish or bearish depending on the dominant market response in real yields and the dollar.
- Open-position detail must preserve the reasoning attached to each fill/expansion so the user can audit why size was added, not only why the first entry happened.

---

## Architecture

### LLM responses need JSON extraction
- Many models wrap JSON in markdown code fences (```json ... ```)
- `extract_json()` in `src/core/llm.py` strips fences and repairs truncated JSON
- Always use `extract_json()` instead of raw `json.loads()` on LLM output

### Pod isolation is non-negotiable
- PodSummary is the ONLY model crossing pod boundaries
- Never expose raw positions, signals, or model parameters
- PodGateway is the single I/O entry/exit point

### Conditional adapter initialization
- News/social adapters should only initialize when `enable_news_adapters=True`
- Prevents test slowdowns from network calls
- `SessionManager.__init__` checks this flag before creating adapters

### Keyword sentiment fails on financial news
- Keyword-based sentiment scores almost every financial headline as -1.0 (bearish)
- Words like "risk", "warning", "decline", "drop" appear in neutral contexts constantly ("risk management", "inflation risk easing", "decline slows")
- Solution: LLM batch scoring via `src/data/adapters/sentiment.py`. One call per pod, scores up to 25 items for sentiment, relevancy, and impact
- Keyword scoring retained as fallback when no LLM key is available, with ambiguous words removed

### Macro score must use LLM-scored sentiment, not adapter-level
- Researchers compute `compute_macro_score` from news/prediction sentiment
- If researchers use raw adapter-level keyword sentiment, the dashboard shows -1.000
- Researchers must call `score_items()` to get LLM-scored sentiment BEFORE calling `compute_macro_score`
- The signal agent's LLM scoring only reaches PM prompts — it does NOT flow back to the macro score unless the researcher also scores

### LLM JSON parsing needs robustness
- Free-tier LLMs often return truncated JSON (hit max_tokens) or wrap responses in markdown fences
- `_parse_scores` must handle: markdown fences, JSON with surrounding text, truncated arrays, dict wrappers
- Set `max_tokens` high enough for the expected output (25 items × ~60 chars each = 1500+ chars; use 2000)
- Always have a keyword fallback path when LLM parsing fails

### Risk concentration must be factor-aware, not fixed-bucket
- Do not treat "gold" and "gold miners" as independent risk buckets with separate full limits; miner ETFs often carry strong gold beta and can amplify the same factor loss.
- Commodities risk should reason in dynamic exposure themes/factors such as gold beta, oil supply shock, natural gas, industrial metals, rates-sensitive metals, and geopolitical energy risk, not deterministic per-asset quotas.
- LLM/research agents may discover new tradeable instruments from news, but rule-based risk must normalize them into factors/clusters and enforce capital, gross exposure, and correlation limits before execution.
- A pod with `$1000` allocated cannot carry more than `$1000` gross exposure unless realized profit increased pod NAV; negative cash from hydration or execution must trigger reduce-only behavior for new buys.
