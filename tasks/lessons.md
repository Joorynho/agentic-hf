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

### Tests must not depend on .env secrets
- Tests that force rule-based mode must clear `OPENROUTER_API_KEY` (not just `OPENAI_API_KEY`)
- Use `monkeypatch.delenv()` or `patch.dict(os.environ, {...})` in fixtures
- Lesson: when switching LLM providers, update ALL test patches

### Log message assertions are fragile
- Tests that assert on log message content break when log formats change
- Use substring matching (`"Failed to process" in msg`) not exact strings
- When updating log messages in production code, grep tests for the old string

### Timing-sensitive async tests
- Tests using `asyncio.sleep(0.15)` with `governance_freq=1` can miss governance calls if `fetch_bars` runs out of `side_effect` entries
- Use `return_value` (never exhausts) instead of short `side_effect` lists
- Give generous sleep time (0.5s+) for integration tests

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
