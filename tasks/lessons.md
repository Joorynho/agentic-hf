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

### OpenAI GPT-5 chat completions token parameter
- GPT-5 family chat-completions calls reject `max_tokens` and require `max_completion_tokens`.
- Legacy OpenAI chat models such as `gpt-4o-mini` still use `max_tokens`; OpenRouter also expects `max_tokens`.
- Keep token-limit parameter selection centralized in `src/core/llm.py` so model routing changes do not create repeated 400 failures before fallback.

### OpenAI 200 OK can still be unusable
- A `200 OK` OpenAI response does not guarantee `choices[0].message.content` contains visible text; reasoning-heavy GPT-5 calls can return empty content when the completion budget is too tight.
- Record those attempts as `empty_response` telemetry instead of silently falling through, so the dashboard/logs explain why another model was tried.
- For GPT-5 family calls, use task-aware `max_completion_tokens` floors for reasoning-heavy tasks such as position reviews and loss reviews.

### Synchronous LLM calls must not run on the web event loop
- `llm_chat()` is synchronous because the OpenAI/OpenRouter SDK call path is blocking.
- Any async dashboard/session path that calls LLMs, especially startup daily position reviews, must use `asyncio.to_thread(...)` or an async client wrapper.
- If the server is listening but `/api/session/status` and `/ws` time out while logs show an LLM review running, suspect an event-loop block before blaming the frontend.

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

### Windows localhost accept errors can be transient
- On Windows, the default asyncio proactor loop can emit `Accept failed on a socket` / `WinError 64` when a local browser connection disappears. If `/api/session/status` continues returning `200 OK`, treat it as noisy socket handling, not proof the server died.
- For the local FastAPI/WebSocket dashboard, prefer `WindowsSelectorEventLoopPolicy` and keep a narrow loop exception handler for transient localhost accept errors only.

### Yahoo symbols differ from internal/broker symbols
- Internal crypto positions use Alpaca/dashboard format such as `ETH/USD`, but Yahoo history expects `ETH-USD`. Normalize only at the adapter boundary and keep returned bars tagged with the original internal symbol.
- yfinance can log huge quote-summary HTML/404 errors for unsupported fundamentals on ETFs or crypto. Do not let those optional library logs dominate the server console; rely on adapter return values and app-level diagnostics instead.

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
- Add explicit tests for crypto symbol normalization so `ETH/USD` does not regress back to raw Yahoo calls.

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

### Dashboard connectivity needs an HTTP fallback
- A working backend/WebSocket endpoint does not guarantee the browser UI will reflect connection state; cached JS, browser WebSocket issues, or message-handler errors can leave the status bar stale.
- Expose the same recoverable `session_snapshot` over HTTP and let the dashboard poll `/api/session/status` plus hydrate from `/api/session/snapshot` when WebSocket is unavailable.
- Bump static script query strings after frontend connectivity fixes so a normal refresh loads the new dashboard code.

### Classic scripts share top-level lexical declarations
- `tower.js`, `motion.js`, and `dashboard.js` are loaded as classic scripts, not ES modules.
- Top-level `const`/`let` names must be unique across all of them; a duplicate such as `const MAX_HISTORY` aborts the later script before any event listeners or WebSocket logic runs.
- Keep the static duplicate-declaration regression test in place for dashboard changes.

### localStorage for rolling data
- `signalHistory` stored in localStorage with 7-day max age
- Always validate entries on load (`e && e.ts && Array.isArray(e.signals)`)
- Prune stale entries on each update cycle

### Research feed labels must separate display, sources, and scoring
- Do not label an LLM scoring window as a source count or display limit. A cap such as 25 may mean "items scored per cycle," while the dashboard can still show more headlines from fewer or more sources.
- Sort and dedupe research feed items by publish timestamp plus URL/text identity before rendering; append order makes an active feed look static.
- If the feed payload does not explicitly say "LLM-scored," do not claim it in the UI. Use neutral labels like `sentiment` or `raw`, and reserve `LLM Window` for the scoring-budget cap.

### Prediction-market charts need true market history
- Do not build historical Polymarket charts from dashboard refresh timestamps alone; that makes the current day look like day one.
- Persist or expose per-market probability history from the backend tracker, then merge frontend history by market ID and time bucket.
- Prediction-market tables need enough width for full questions plus probability, delta, volume, status, and expiry context; thin tables hide the reason the signal matters.
- Give historical odds tables their own minimum vertical viewport. If the chart consumes the subtab height, a technically scrollable table can still become unreadable by showing only one row.

### Main feed panes should hydrate from durable sources
- Do not rely only on WebSocket pod summary enrichment for feed-style panes. If there is a persistent audit/feed endpoint, the primary user-facing pane should hydrate from it directly and reuse it as a fallback in session snapshots.
- Manual refresh actions in an audit subtab should update the main display too; otherwise users see contradictory empty and populated versions of the same data.

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
- Treat concrete failures like GLD as regression examples, not as the full product scope. Thesis quality and lifecycle checks must cover all four active pods: equities, FX, crypto, and commodities, with asset-class-specific monitors for each.
- A thesis must separate verified facts from assumptions. Do not let the PM present "SOL is undervalued versus ETH" as fact unless it cites crypto-native metrics such as market cap/TVL, FDV/TVL, fees/revenue, stablecoin supply, DEX volume, active users/addresses, funding, open interest, and relative performance across multiple windows.
- Current-state causal claims need current-state data. If a crypto thesis says high Ethereum gas fees are pushing users to Solana, it must verify current gas/base-fee data or label that as an assumption.
- Events and summits are not automatically catalysts. Treat them as narrative support unless there is a confirmed announcement, release, flow, policy decision, or other repricing trigger.
- Every entry thesis needs a timeframe and a why-now. "The asset/ecosystem is good" is not a trade; the PM must explain why the market should reprice during the intended holding window and match stop/TP/max-hold logic to that timeframe.
- Never let an LLM assert "negative real rates" unless the real-yield data in the prompt is actually below zero. If the data is missing or mixed, the PM should say that instead of inventing certainty.
- Geopolitical risk belongs in the thesis, but only as a catalyst/risk-premium argument with second-order effects; it can be bullish or bearish depending on the dominant market response in real yields and the dollar.
- Open-position detail must preserve the reasoning attached to each fill/expansion so the user can audit why size was added, not only why the first entry happened.
- Entry theses are live contracts, not static notes. Open positions must be re-reviewed when macro regime, real yields, USD, relevant news, price action, or time-based catalysts change; challenged/broken theses should block adds until the PM writes a fresh expansion thesis or reduces/exits.

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

### Shared helper renames need startup import checks
- After renaming helpers used across runtime modules, run a startup-level import check such as importing `SessionManager`, not only narrow unit tests.
- Unit tests can pass while `run.py` still fails if a stale cross-module import remains in the startup path.

### Live dashboard fixes must account for stale running processes
- When a UI or execution fix changes Python runtime behavior, verify the live audit payload includes the new fields after restart; a browser refresh alone cannot reload server-side Python modules.
- Generic execution messages like "Order rejected" are not acceptable as the final diagnostic. Preserve broker `stage`, structured `reason`, and any API payload `message`, and add tests that reject generic reasons when specific broker details exist.
- If historical performance APIs return firm-level data without pod breakdowns, do not plot missing pod values as zero. Either show firm NAV or skip unavailable pod series so charts remain truthful and readable.
- If a server restart writes all-cash placeholder NAV rows after a valid pod NAV, fix it in the persistence/read layer, not only in Chart.js. Store/read the last valid NAV so performance pauses instead of showing fake drawdowns.
- Benchmark series must never silently share a NAV axis at an incompatible scale. If a benchmark is shown on a NAV chart, make it user-toggleable and explicitly rebase it to the visible comparison basis.
- Chart.js canvases inside flex-column tabs need non-shrinking parent containers and an explicit resize after the hidden tab becomes visible. Otherwise the data can be correct while the graph renders as a tiny unreadable strip.
- Historical all-cash seed rows can be wrong even when they are at the start of the series, so previous-row collapse detection is not enough. NAV history repair must also detect leading low seed baselines and rebase them to the actual funded pod allocation.
- Product defaults must match the live run defaults. If `run.py` starts pods with `$1000`, `SessionManager.start_live_session()` and dashboard start endpoints cannot still default to `$100`.
- Reliability panels should reuse the system of record rather than recomputing their own truth. State health comes from accountants/NavStore/broker reconciliation; decision audit comes from the same event stream that feeds the live dashboard.

### Risk concentration must be factor-aware, not fixed-bucket
- Do not treat "gold" and "gold miners" as independent risk buckets with separate full limits; miner ETFs often carry strong gold beta and can amplify the same factor loss.
- Commodities risk should reason in dynamic exposure themes/factors such as gold beta, oil supply shock, natural gas, industrial metals, rates-sensitive metals, and geopolitical energy risk, not deterministic per-asset quotas.
- LLM/research agents may discover new tradeable instruments from news, but rule-based risk must normalize them into factors/clusters and enforce capital, gross exposure, and correlation limits before execution.
- A pod with `$1000` allocated cannot carry more than `$1000` gross exposure unless realized profit increased pod NAV; negative cash from hydration or execution must trigger reduce-only behavior for new buys.

### Exit plans can scale out without replacing the simple fallback
- A single take-profit cap can cut winners too early when a thesis is working.
- Support optional tiered take-profit levels as trade metadata, but keep the old single TP behavior for trades without tiers.
- Tiered exits should close only the configured fraction at each unhit level and leave the rest of the position governed by later targets, stops, thesis reviews, or time exits.

---

## Market Data Integrity

### Crypto symbols need cross-provider normalization
- Alpaca, Yahoo Finance, and the dashboard can refer to the same crypto pair as `ETH/USD`, `ETHUSD`, `ETH-USD`, or `ETH`.
- Always normalize and alias-match crypto symbols before reconciling broker positions, price feeds, and local accountants.
- For Yahoo Finance crypto quotes, use dashed symbols like `ETH-USD`; slash symbols such as `ETH/USD` can fail or return stale/no data.
- UI should expose quote source/staleness instead of silently showing entry price as current price.
- Alpaca crypto market data expects slash symbols such as `ETH/USD`; compact or dashed symbols (`ETHUSD`, `ETH-USD`) are invalid for snapshot/latest-trade endpoints.
- Crypto mark-to-market must not depend on broker position reconciliation succeeding. Fetch crypto market-data quotes independently and let `/api/positions` do a short throttled refresh while returning cached positions on timeout.
- Position APIs should expose `entry_notional` and `current_notional` separately. UI tables must display current exposure from `qty × current_price`, not blindly trust a generic `notional` field that may represent entry cost in older payloads.
- New BUY orders should require a fresh, positive price with a source and timestamp before risk/execution. SELL orders can remain reduce-risk even if the quote feed is stale.
- Pod namespaces need the same last-price/freshness map that accountants use for mark-to-market; otherwise PM/runtime checks and execution can disagree about whether a symbol has live data.

### Diagnostic dashboards must be non-blocking
- Dashboard health/quality/audit panels should show cached local session state immediately and treat live broker/API reads as an enrichment, not as a prerequisite.
- Never let a live broker reconciliation call block Operations Health; slow account/position/order reads should time out and return partial diagnostics.
- Empty diagnostic panels are worse than partial data. If the server endpoint is slow, empty, or unavailable, the frontend should fall back to the local WebSocket/order/position state and clearly label it as a local snapshot.
- Order lifecycle events need both `local_order_id` and `broker_order_id`; do not overwrite one with the other, because pre-submit pending rows and broker responses have different identities.
- A decision audit is not enough by itself. Expose the current per-pod stage and reason from PM decision through runtime gates and broker execution so a missing trade has an immediate explanation.
- Broker diagnostics must feed runtime gates, not only dashboard panels. If local and broker positions disagree, block new risk for that symbol until reconciled; if an open broker order already exists, block further orders for that symbol to avoid duplicate reservations. Repeated execution rejections should trigger a temporary reduce-only cooldown so agents stop retrying the same broken order pattern.
- Trade evidence must live with the fill, not only with the latest PM namespace state. Each entry or expansion needs its own persisted evidence packet so the dashboard can explain why the position was opened or added to after restarts and later regime changes.
- Evidence capture is only useful if it becomes an action queue. Surface missing/stale evidence, challenged theses, warning checks, and thin source coverage in Operations Health so weak positions are visible without manually opening every holding.
- Evidence review warnings must feed runtime trading controls, not only dashboard labels. URGENT evidence states should make a symbol reduce-only, REVIEW states should block add/scale-up orders until the PM supplies a fresh expansion thesis, and reductions should remain allowed so the system can lower risk.
