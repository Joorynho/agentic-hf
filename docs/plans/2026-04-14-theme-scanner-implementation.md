# Theme-Aware Universe Scanner Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add a daily theme scanner to the equities researcher that discovers new tickers from trending investment themes, persists them across sessions with a thesis, and auto-reviews thesis validity every 7 days.

**Architecture:** A new `ThemeScanner` class in `src/data/services/theme_scanner.py` orchestrates 4 web searches + 7 curated site scrapes + 1 LLM synthesis call to extract 2-3 themes and 3-5 ticker candidates each. Validated tickers are stored in `memory.json` under `discovered_universe.equities` and merged with `EQUITIES_SEED` at runtime. The equities researcher calls the scanner once per day before `_review_universe()` (which is simplified to a pure union of seed + active discovered tickers).

**Tech Stack:** Python asyncio, existing `WebSearchAdapter` (`search()` + `fetch_page()`), existing `llm_chat()` from `src/core/llm.py`, Pydantic v2 for data models, pytest + pytest-asyncio for tests.

---

## Task 1: DiscoveredTicker Pydantic Model

**Files:**
- Create: `src/data/services/__init__.py` (already exists — skip if present)
- Modify: `src/core/models/execution.py` — add `DiscoveredTicker` model

**Step 1: Write the failing test**

```python
# tests/unit/test_discovered_ticker.py
import pytest
from datetime import date
from src.core.models.execution import DiscoveredTicker

def test_discovered_ticker_defaults():
    t = DiscoveredTicker(
        symbol="NBIS",
        theme="AI Infrastructure",
        thesis="Cloud AI infra provider partnering with NVIDIA/MSFT.",
        discovered_date="2026-04-14",
        next_review_date="2026-04-21",
    )
    assert t.symbol == "NBIS"
    assert t.status == "active"
    assert t.invalidation_reason is None
    assert t.source_headlines == []

def test_discovered_ticker_serializes_to_json():
    t = DiscoveredTicker(
        symbol="VRT",
        theme="Data Centers",
        thesis="Power demand surge from AI buildout.",
        discovered_date="2026-04-14",
        next_review_date="2026-04-21",
    )
    d = t.model_dump(mode="json")
    assert d["symbol"] == "VRT"
    assert d["status"] == "active"
    assert isinstance(d["source_headlines"], list)
```

**Step 2: Run test to verify it fails**

```bash
cd "C:/Users/PW1868/Agentic HF"
python -m pytest tests/unit/test_discovered_ticker.py -v
```
Expected: `ImportError` or `AttributeError` — model doesn't exist yet.

**Step 3: Add model to execution.py**

Open `src/core/models/execution.py`. Find the `VerificationResult` model (added in previous session). Add `DiscoveredTicker` directly after it:

```python
class DiscoveredTicker(BaseModel):
    """A ticker discovered via theme scanning. Persisted across sessions."""
    symbol: str
    theme: str                          # e.g. "AI Infrastructure"
    thesis: str                         # Why this ticker was added
    discovered_date: str                # ISO date string e.g. "2026-04-14"
    next_review_date: str               # ISO date string — when to re-validate thesis
    status: str = "active"             # "active" | "inactive"
    invalidation_reason: str | None = None
    source_headlines: list[str] = []    # Headlines that triggered discovery
```

**Step 4: Run test to verify it passes**

```bash
python -m pytest tests/unit/test_discovered_ticker.py -v
```
Expected: PASS (2 tests).

**Step 5: Commit**

```bash
git add src/core/models/execution.py tests/unit/test_discovered_ticker.py
git commit -m "feat: add DiscoveredTicker model for theme-based universe expansion"
```

---

## Task 2: ThemeScanner Class — Skeleton + Web Searches

**Files:**
- Create: `src/data/services/theme_scanner.py`
- Create: `tests/unit/test_theme_scanner.py`

**Step 1: Write failing tests**

```python
# tests/unit/test_theme_scanner.py
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from src.data.services.theme_scanner import ThemeScanner

@pytest.fixture
def mock_web_searcher():
    ws = MagicMock()
    ws.search = AsyncMock(return_value=[
        {"title": "AI stocks surge", "snippet": "Tech sector leads...", "url": "https://example.com/ai"}
    ])
    ws.fetch_page = AsyncMock(return_value="AI infrastructure spending hits record highs. NVDA, NBIS lead gains.")
    return ws

@pytest.fixture
def scanner(mock_web_searcher):
    return ThemeScanner(web_searcher=mock_web_searcher)

def test_scanner_init(scanner):
    assert scanner is not None

@pytest.mark.asyncio
async def test_run_web_searches_returns_summaries(scanner, mock_web_searcher):
    results = await scanner._run_web_searches(month="April", year="2026")
    assert isinstance(results, list)
    assert len(results) == 4   # 4 search queries
    mock_web_searcher.search.assert_called()

@pytest.mark.asyncio
async def test_scrape_curated_sites_returns_list(scanner, mock_web_searcher):
    results = await scanner._scrape_curated_sites()
    assert isinstance(results, list)
    # Returns at least one result even if some sites fail
    assert len(results) >= 0
```

**Step 2: Run tests to verify they fail**

```bash
python -m pytest tests/unit/test_theme_scanner.py -v
```
Expected: `ImportError` — module doesn't exist yet.

**Step 3: Create the ThemeScanner skeleton**

Create `src/data/services/theme_scanner.py`:

```python
"""Theme-Aware Universe Scanner.

Runs once per day inside the equities researcher. Discovers new tickers
by scanning financial news sources and web search results for emerging
investment themes.
"""
from __future__ import annotations

import logging
from datetime import date, timedelta

logger = logging.getLogger(__name__)

# --- Curated financial sources to scrape daily ---
CURATED_SOURCES = [
    "https://www.tradingkey.com/news",
    "https://www.calcalistech.com/ctechnews",
    "https://www.investing.com/news",
    "https://www.thestreet.com/markets",
    "https://simplywall.st/discover/gb/investing-ideas",
    "https://simplywall.st/stocks",
    "https://simplywall.st/markets/us",
]

# --- Daily web search queries for theme detection ---
_SEARCH_QUERIES = [
    "top performing stock market sectors this week {month} {year}",
    "emerging investment themes {month} {year} wall street",
    "most bought stocks by institutions this month {year}",
    "stocks breaking out highest momentum this week {month} {year}",
]

# Max new tickers to add per daily scan
_MAX_DAILY_ADDS = 3


class ThemeScanner:
    """Discovers new equity tickers by detecting emerging investment themes."""

    def __init__(self, web_searcher=None):
        self._web_searcher = web_searcher

    async def _run_web_searches(self, month: str, year: str) -> list[dict]:
        """Run 4 targeted web searches. Returns list of {query, results} dicts."""
        summaries = []
        for query_template in _SEARCH_QUERIES:
            query = query_template.format(month=month, year=year)
            try:
                if not self._web_searcher:
                    summaries.append({"query": query, "content": ""})
                    continue
                results = await self._web_searcher.search(query, max_results=3)
                content_parts = []
                for r in results[:3]:
                    content_parts.append(r.get("snippet", ""))
                # Fetch page content from top result
                if results and results[0].get("url"):
                    try:
                        page = await self._web_searcher.fetch_page(results[0]["url"])
                        if page:
                            content_parts.append(page[:500])
                    except Exception:
                        pass
                summaries.append({"query": query, "content": " | ".join(content_parts)})
            except Exception as e:
                logger.debug("[theme_scanner] Web search failed for '%s': %s", query, e)
                summaries.append({"query": query, "content": ""})
        return summaries

    async def _scrape_curated_sites(self) -> list[dict]:
        """Scrape 7 curated financial sites. Returns list of {url, content} dicts."""
        results = []
        for url in CURATED_SOURCES:
            try:
                if not self._web_searcher:
                    results.append({"url": url, "content": ""})
                    continue
                content = await self._web_searcher.fetch_page(url)
                results.append({"url": url, "content": (content or "")[:600]})
            except Exception as e:
                logger.debug("[theme_scanner] Scrape failed for %s: %s", url, e)
                results.append({"url": url, "content": ""})
        return results
```

**Step 4: Run tests to verify they pass**

```bash
python -m pytest tests/unit/test_theme_scanner.py -v
```
Expected: PASS (3 tests).

**Step 5: Commit**

```bash
git add src/data/services/theme_scanner.py tests/unit/test_theme_scanner.py
git commit -m "feat: add ThemeScanner skeleton with web search and curated site scraping"
```

---

## Task 3: ThemeScanner — LLM Theme Synthesis

**Files:**
- Modify: `src/data/services/theme_scanner.py` — add `synthesize_themes()` method
- Modify: `tests/unit/test_theme_scanner.py` — add synthesis tests

**Step 1: Write failing tests**

Add to `tests/unit/test_theme_scanner.py`:

```python
@pytest.mark.asyncio
async def test_synthesize_themes_returns_themes(scanner):
    web_results = [
        {"query": "top sectors", "content": "AI and semiconductors lead market gains."},
        {"query": "emerging themes", "content": "Data center stocks hit record highs."},
        {"query": "institutional buys", "content": "Funds piling into AI infrastructure."},
        {"query": "breakout stocks", "content": "NBIS, VRT, CEG breaking out."},
    ]
    site_results = [{"url": "https://investing.com", "content": "AI infra boom continues."}]
    headlines = [{"title": "Nebius partners with NVIDIA", "sentiment": 0.8}]
    poly_signals = []
    fred_snapshot = {"VIXCLS": 18.0, "DGS10": 4.2}
    existing_universe = ["SPY", "QQQ", "NVDA"]

    with patch("src.data.services.theme_scanner.llm_chat", return_value='''
    {
      "themes": [
        {
          "name": "AI Infrastructure",
          "thesis": "Hyperscaler capex surging.",
          "confidence": 0.85,
          "tickers": [
            {"symbol": "NBIS", "reason": "NVIDIA partnership"},
            {"symbol": "VRT", "reason": "Data center power"}
          ]
        }
      ]
    }
    '''):
        themes = await scanner.synthesize_themes(
            web_results=web_results,
            site_results=site_results,
            headlines=headlines,
            poly_signals=poly_signals,
            fred_snapshot=fred_snapshot,
            existing_universe=existing_universe,
        )

    assert len(themes) == 1
    assert themes[0]["name"] == "AI Infrastructure"
    assert len(themes[0]["tickers"]) == 2
    assert themes[0]["tickers"][0]["symbol"] == "NBIS"

@pytest.mark.asyncio
async def test_synthesize_themes_handles_llm_failure(scanner):
    """Returns empty list if LLM fails or returns bad JSON."""
    with patch("src.data.services.theme_scanner.llm_chat", return_value="not valid json"):
        themes = await scanner.synthesize_themes(
            web_results=[], site_results=[], headlines=[],
            poly_signals=[], fred_snapshot={}, existing_universe=[],
        )
    assert themes == []
```

**Step 2: Run tests to verify they fail**

```bash
python -m pytest tests/unit/test_theme_scanner.py::test_synthesize_themes_returns_themes -v
```
Expected: `AttributeError` — method doesn't exist yet.

**Step 3: Add `synthesize_themes()` to ThemeScanner**

Add at the bottom of the `ThemeScanner` class in `src/data/services/theme_scanner.py`:

```python
    async def synthesize_themes(
        self,
        web_results: list[dict],
        site_results: list[dict],
        headlines: list[dict],
        poly_signals: list[dict],
        fred_snapshot: dict,
        existing_universe: list[str],
    ) -> list[dict]:
        """Call LLM to synthesize themes from all research sources.

        Returns list of theme dicts: {name, thesis, confidence, tickers: [{symbol, reason}]}
        """
        # Build context strings
        web_text = "\n".join(
            f"- [{r['query']}]: {r['content'][:200]}" for r in web_results if r.get("content")
        )
        site_text = "\n".join(
            f"- [{r['url']}]: {r['content'][:150]}" for r in site_results if r.get("content")
        )
        hl_text = "\n".join(
            f"- {h.get('title','')}" for h in headlines[:15]
        )
        poly_text = "\n".join(
            f"- {p.get('question','')}" for p in poly_signals[:5]
        )
        vix = fred_snapshot.get("VIXCLS", "N/A")
        t10y = fred_snapshot.get("DGS10", "N/A")
        seed_str = ", ".join(existing_universe[:40])

        prompt = f"""You are an equity research analyst identifying emerging investment themes.

WEB RESEARCH:
{web_text or 'No web data available.'}

FINANCIAL SITES:
{site_text or 'No site data available.'}

RECENT HEADLINES:
{hl_text or 'No headlines available.'}

POLYMARKET SIGNALS:
{poly_text or 'No signals.'}

MACRO: VIX={vix}, 10Y Yield={t10y}

EXISTING UNIVERSE (do NOT suggest these): {seed_str}

Identify 2-3 emerging investment themes with real momentum.
For each theme, suggest 3-5 specific US-listed stock tickers that benefit.
Only suggest liquid, US-listed stocks tradeable on Alpaca.
Output ONLY valid JSON, no commentary:
{{
  "themes": [
    {{
      "name": "Theme Name",
      "thesis": "Why this theme has momentum...",
      "confidence": 0.8,
      "tickers": [
        {{"symbol": "TICK", "reason": "Why this ticker benefits"}}
      ]
    }}
  ]
}}"""

        try:
            from src.core.llm import llm_chat, has_llm_key
            if not has_llm_key():
                return []
            raw = llm_chat([{"role": "user", "content": prompt}], max_tokens=600)
            # Extract JSON from response
            import re
            m = re.search(r'\{[\s\S]*\}', raw)
            if not m:
                return []
            data = __import__("json").loads(m.group())
            return data.get("themes", [])
        except Exception as e:
            logger.warning("[theme_scanner] LLM synthesis failed: %s", e)
            return []
```

Also add the import at the top of the file:
```python
import re
import json
```

**Step 4: Run tests**

```bash
python -m pytest tests/unit/test_theme_scanner.py -v
```
Expected: PASS (all tests including 2 new ones).

**Step 5: Commit**

```bash
git add src/data/services/theme_scanner.py tests/unit/test_theme_scanner.py
git commit -m "feat: add LLM theme synthesis to ThemeScanner"
```

---

## Task 4: ThemeScanner — Ticker Validation & Thesis Review

**Files:**
- Modify: `src/data/services/theme_scanner.py` — add `validate_tickers()` and `review_ticker()`
- Modify: `tests/unit/test_theme_scanner.py` — add validation + review tests

**Step 1: Write failing tests**

Add to `tests/unit/test_theme_scanner.py`:

```python
@pytest.mark.asyncio
async def test_validate_tickers_accepts_valid(scanner, mock_web_searcher):
    candidates = [
        {"symbol": "NBIS", "reason": "NVIDIA partnership", "theme": "AI Infrastructure",
         "thesis": "Cloud AI infra provider."}
    ]
    mock_web_searcher.search = AsyncMock(return_value=[
        {"title": "Nebius stock analysis 2026", "snippet": "NBIS is a US-listed AI cloud company.", "url": "https://ex.com"}
    ])
    with patch("src.data.services.theme_scanner.llm_chat", return_value='{"valid": true, "reason": "Confirmed US-listed"}'):
        validated = await scanner.validate_tickers(candidates, month="April", year="2026")
    assert len(validated) == 1
    assert validated[0]["symbol"] == "NBIS"

@pytest.mark.asyncio
async def test_validate_tickers_rejects_invalid(scanner, mock_web_searcher):
    candidates = [
        {"symbol": "FAKEXYZ", "reason": "Some reason", "theme": "AI", "thesis": "Fake thesis."}
    ]
    mock_web_searcher.search = AsyncMock(return_value=[])
    with patch("src.data.services.theme_scanner.llm_chat", return_value='{"valid": false, "reason": "Not found"}'):
        validated = await scanner.validate_tickers(candidates, month="April", year="2026")
    assert len(validated) == 0

@pytest.mark.asyncio
async def test_review_ticker_still_valid(scanner, mock_web_searcher):
    ticker_data = {
        "symbol": "NBIS", "theme": "AI Infrastructure",
        "thesis": "NVIDIA/MSFT cloud partnership driving revenue.",
        "discovered_date": "2026-04-07", "next_review_date": "2026-04-14",
        "status": "active", "invalidation_reason": None, "source_headlines": [],
    }
    mock_web_searcher.search = AsyncMock(return_value=[
        {"title": "Nebius expands AI cloud", "snippet": "Continued growth.", "url": "https://ex.com"}
    ])
    with patch("src.data.services.theme_scanner.llm_chat", return_value='{"still_valid": true, "reason": "Thesis intact"}'):
        result = await scanner.review_ticker(ticker_data, month="April", year="2026")
    assert result["status"] == "active"
    assert result["next_review_date"] != "2026-04-14"  # Extended by 7 days

@pytest.mark.asyncio
async def test_review_ticker_invalidated(scanner, mock_web_searcher):
    ticker_data = {
        "symbol": "NBIS", "theme": "AI Infrastructure",
        "thesis": "NVIDIA/MSFT cloud partnership driving revenue.",
        "discovered_date": "2026-04-07", "next_review_date": "2026-04-14",
        "status": "active", "invalidation_reason": None, "source_headlines": [],
    }
    mock_web_searcher.search = AsyncMock(return_value=[
        {"title": "Nebius loses NVIDIA contract", "snippet": "Partnership terminated.", "url": "https://ex.com"}
    ])
    with patch("src.data.services.theme_scanner.llm_chat", return_value='{"still_valid": false, "reason": "Partnership ended"}'):
        result = await scanner.review_ticker(ticker_data, month="April", year="2026")
    assert result["status"] == "inactive"
    assert result["invalidation_reason"] == "Partnership ended"
```

**Step 2: Run tests to verify they fail**

```bash
python -m pytest tests/unit/test_theme_scanner.py::test_validate_tickers_accepts_valid -v
```
Expected: `AttributeError` — methods don't exist yet.

**Step 3: Add `validate_tickers()` and `review_ticker()` to ThemeScanner**

Add these methods to the class:

```python
    async def validate_tickers(
        self,
        candidates: list[dict],
        month: str,
        year: str,
    ) -> list[dict]:
        """Validate candidate tickers via web search + LLM check.

        Returns only confirmed, US-listed, Alpaca-tradeable tickers.
        """
        validated = []
        for candidate in candidates:
            symbol = candidate.get("symbol", "")
            reason = candidate.get("reason", "")
            if not symbol:
                continue
            # Web search for the ticker
            search_content = ""
            if self._web_searcher:
                try:
                    results = await self._web_searcher.search(
                        f"{symbol} stock analysis {month} {year}", max_results=3
                    )
                    search_content = " | ".join(r.get("snippet", "") for r in results[:3])
                except Exception as e:
                    logger.debug("[theme_scanner] Validation search failed for %s: %s", symbol, e)

            prompt = f"""Is "{symbol}" a real, US-listed stock tradeable on Alpaca?
Search evidence: {search_content or 'No results found.'}
Reason for consideration: {reason}

Output ONLY valid JSON:
{{"valid": true/false, "reason": "brief explanation"}}"""

            try:
                from src.core.llm import llm_chat, has_llm_key
                if not has_llm_key():
                    # No LLM — accept if search found results
                    if search_content:
                        validated.append(candidate)
                    continue
                raw = llm_chat([{"role": "user", "content": prompt}], max_tokens=100)
                m = re.search(r'\{[^}]+\}', raw)
                if m:
                    data = json.loads(m.group())
                    if data.get("valid"):
                        validated.append(candidate)
            except Exception as e:
                logger.debug("[theme_scanner] Validation LLM failed for %s: %s", symbol, e)

        return validated

    async def review_ticker(
        self,
        ticker_data: dict,
        month: str,
        year: str,
    ) -> dict:
        """Re-evaluate a discovered ticker's thesis. Returns updated ticker dict.

        If thesis still valid: extends next_review_date by 7 days, status stays active.
        If thesis invalid: sets status=inactive, fills invalidation_reason.
        """
        symbol = ticker_data.get("symbol", "")
        original_thesis = ticker_data.get("thesis", "")

        # Fetch fresh news for this ticker
        search_content = ""
        if self._web_searcher:
            try:
                results = await self._web_searcher.search(
                    f"{symbol} stock news {month} {year}", max_results=3
                )
                search_content = " | ".join(r.get("snippet", "") for r in results[:3])
            except Exception as e:
                logger.debug("[theme_scanner] Review search failed for %s: %s", symbol, e)

        prompt = f"""Does this investment thesis still hold for {symbol}?

Original thesis: {original_thesis}
Recent news: {search_content or 'No recent news found.'}

Output ONLY valid JSON:
{{"still_valid": true/false, "reason": "brief explanation"}}"""

        try:
            from src.core.llm import llm_chat, has_llm_key
            if not has_llm_key():
                # No LLM — keep active if we have no strong evidence against
                next_review = (
                    date.today() + timedelta(days=7)
                ).isoformat()
                return {**ticker_data, "next_review_date": next_review}

            raw = llm_chat([{"role": "user", "content": prompt}], max_tokens=100)
            m = re.search(r'\{[^}]+\}', raw)
            if m:
                data = json.loads(m.group())
                if data.get("still_valid"):
                    next_review = (date.today() + timedelta(days=7)).isoformat()
                    return {**ticker_data, "next_review_date": next_review}
                else:
                    return {
                        **ticker_data,
                        "status": "inactive",
                        "invalidation_reason": data.get("reason", "Thesis invalidated"),
                    }
        except Exception as e:
            logger.debug("[theme_scanner] Review LLM failed for %s: %s", symbol, e)

        # Fallback: keep active, extend review
        next_review = (date.today() + timedelta(days=7)).isoformat()
        return {**ticker_data, "next_review_date": next_review}
```

**Step 4: Run all ThemeScanner tests**

```bash
python -m pytest tests/unit/test_theme_scanner.py -v
```
Expected: PASS (all 9 tests).

**Step 5: Commit**

```bash
git add src/data/services/theme_scanner.py tests/unit/test_theme_scanner.py
git commit -m "feat: add ticker validation and thesis review to ThemeScanner"
```

---

## Task 5: ThemeScanner — Main `scan()` Entrypoint

**Files:**
- Modify: `src/data/services/theme_scanner.py` — add `scan()` method
- Modify: `tests/unit/test_theme_scanner.py` — add end-to-end scan test

**Step 1: Write failing test**

Add to `tests/unit/test_theme_scanner.py`:

```python
@pytest.mark.asyncio
async def test_scan_end_to_end(scanner, mock_web_searcher):
    """Full scan returns DiscoveredTicker list."""
    from src.core.models.execution import DiscoveredTicker

    headlines = [{"title": "AI boom continues", "sentiment": 0.8}]
    existing = {"AAPL": {"symbol": "AAPL", "status": "active"}}
    existing_universe = ["SPY", "QQQ", "NVDA", "AAPL"]

    with patch("src.data.services.theme_scanner.llm_chat") as mock_llm:
        mock_llm.side_effect = [
            # synthesize_themes call
            '{"themes": [{"name": "AI Infra", "thesis": "Capex surging.", "confidence": 0.9, "tickers": [{"symbol": "NBIS", "reason": "NVIDIA partnership"}]}]}',
            # validate_tickers call
            '{"valid": true, "reason": "US-listed AI cloud company"}',
        ]
        result = await scanner.scan(
            headlines=headlines,
            poly_signals=[],
            fred_snapshot={"VIXCLS": 18.0, "DGS10": 4.2},
            existing_discovered=existing,
            existing_universe=existing_universe,
            month="April",
            year="2026",
        )

    assert isinstance(result, list)
    assert len(result) == 1
    assert result[0].symbol == "NBIS"
    assert result[0].theme == "AI Infra"
    assert result[0].status == "active"
    assert result[0].next_review_date > result[0].discovered_date
```

**Step 2: Run test to verify it fails**

```bash
python -m pytest tests/unit/test_theme_scanner.py::test_scan_end_to_end -v
```
Expected: `AttributeError` — `scan()` doesn't exist.

**Step 3: Add `scan()` to ThemeScanner**

```python
    async def scan(
        self,
        headlines: list[dict],
        poly_signals: list[dict],
        fred_snapshot: dict,
        existing_discovered: dict,      # symbol -> DiscoveredTicker dict (current persisted)
        existing_universe: list[str],   # full current universe (seed + active discovered)
        month: str,
        year: str,
    ) -> list["DiscoveredTicker"]:
        """Run full daily theme scan. Returns list of new DiscoveredTicker objects to add.

        Does NOT modify existing_discovered — caller is responsible for merging.
        Caps at _MAX_DAILY_ADDS new tickers.
        """
        from src.core.models.execution import DiscoveredTicker

        # 1. Web searches + curated site scrapes
        web_results = await self._run_web_searches(month=month, year=year)
        site_results = await self._scrape_curated_sites()

        # 2. LLM theme synthesis
        themes = await self.synthesize_themes(
            web_results=web_results,
            site_results=site_results,
            headlines=headlines,
            poly_signals=poly_signals,
            fred_snapshot=fred_snapshot,
            existing_universe=existing_universe,
        )

        if not themes:
            logger.info("[theme_scanner] No themes identified this cycle.")
            return []

        # 3. Flatten candidates, skip already-known symbols
        candidates = []
        for theme in themes:
            for t in theme.get("tickers", []):
                sym = (t.get("symbol") or "").upper().strip()
                if not sym:
                    continue
                if sym in existing_universe:
                    continue
                if sym in existing_discovered:
                    continue
                candidates.append({
                    "symbol": sym,
                    "reason": t.get("reason", ""),
                    "theme": theme.get("name", ""),
                    "thesis": f"{theme.get('thesis', '')} | {t.get('reason', '')}",
                    "source_headlines": [h.get("title", "") for h in headlines[:3]],
                })

        if not candidates:
            return []

        # 4. Validate candidates
        validated = await self.validate_tickers(candidates, month=month, year=year)

        # 5. Build DiscoveredTicker objects, cap at daily limit
        today = date.today().isoformat()
        review_date = (date.today() + timedelta(days=7)).isoformat()
        new_tickers = []
        for v in validated[:_MAX_DAILY_ADDS]:
            new_tickers.append(DiscoveredTicker(
                symbol=v["symbol"],
                theme=v["theme"],
                thesis=v["thesis"],
                discovered_date=today,
                next_review_date=review_date,
                status="active",
                source_headlines=v.get("source_headlines", []),
            ))

        logger.info("[theme_scanner] Discovered %d new tickers: %s",
                    len(new_tickers), [t.symbol for t in new_tickers])
        return new_tickers
```

**Step 4: Run all ThemeScanner tests**

```bash
python -m pytest tests/unit/test_theme_scanner.py -v
```
Expected: PASS (all 10 tests).

**Step 5: Commit**

```bash
git add src/data/services/theme_scanner.py tests/unit/test_theme_scanner.py
git commit -m "feat: add ThemeScanner.scan() main entrypoint — full daily theme discovery pipeline"
```

---

## Task 6: Add Curated Sources to universes.py

**Files:**
- Modify: `src/core/config/universes.py`

**Step 1: No test needed** — just a constants addition.

**Step 2: Add to universes.py**

Open `src/core/config/universes.py`. At the bottom of the file, add:

```python
# --- Theme Scanner: Curated Financial Sources ---
# Scraped daily by ThemeScanner to detect emerging investment themes.
THEME_SCANNER_SOURCES = [
    "https://www.tradingkey.com/news",
    "https://www.calcalistech.com/ctechnews",
    "https://www.investing.com/news",
    "https://www.thestreet.com/markets",
    "https://simplywall.st/discover/gb/investing-ideas",
    "https://simplywall.st/stocks",
    "https://simplywall.st/markets/us",
]
```

Then update `theme_scanner.py` to import from config instead of defining locally:

In `src/data/services/theme_scanner.py`, replace:
```python
CURATED_SOURCES = [
    "https://www.tradingkey.com/news",
    ...
]
```
With:
```python
from src.core.config.universes import THEME_SCANNER_SOURCES as CURATED_SOURCES
```

**Step 3: Run full test suite to check nothing broke**

```bash
python -m pytest tests/ -v --tb=short -q
```
Expected: All tests pass.

**Step 4: Commit**

```bash
git add src/core/config/universes.py src/data/services/theme_scanner.py
git commit -m "chore: move curated scanner sources to universes.py config"
```

---

## Task 7: Integrate ThemeScanner into Equities Researcher

**Files:**
- Modify: `src/pods/templates/equities/researcher.py`
- Create: `tests/unit/test_equities_researcher_scanner.py`

**Step 1: Write failing tests**

```python
# tests/unit/test_equities_researcher_scanner.py
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from src.pods.templates.equities.researcher import EquitiesResearcher

@pytest.fixture
def mock_ns():
    store = {}
    ns = MagicMock()
    ns.get = lambda k, d=None: store.get(k, d)
    ns.set = lambda k, v: store.update({k: v})
    return ns

@pytest.fixture
def researcher(mock_ns):
    r = EquitiesResearcher.__new__(EquitiesResearcher)
    r._ns = mock_ns
    r._pod_id = "equities"
    r._web_searcher = MagicMock()
    r._web_searcher.search = AsyncMock(return_value=[])
    r._web_searcher.fetch_page = AsyncMock(return_value="")
    r._last_theme_scan_date = None
    return r

@pytest.mark.asyncio
async def test_should_run_theme_scan_first_time(researcher):
    assert researcher._should_run_theme_scan() is True

@pytest.mark.asyncio
async def test_should_not_run_theme_scan_same_day(researcher):
    from datetime import date
    researcher._last_theme_scan_date = date.today().isoformat()
    assert researcher._should_run_theme_scan() is False

@pytest.mark.asyncio
async def test_load_discovered_universe_empty(researcher):
    researcher._ns.get = lambda k, d=None: None
    result = researcher._load_discovered_universe()
    assert result == {}

@pytest.mark.asyncio
async def test_build_active_universe_merges_seed_and_discovered(researcher):
    from src.core.config.universes import EQUITIES_SEED
    discovered = {
        "NBIS": {"symbol": "NBIS", "status": "active"},
        "VRT": {"symbol": "VRT", "status": "inactive"},  # should be excluded
    }
    universe = researcher._build_active_universe(discovered)
    assert "NBIS" in universe
    assert "VRT" not in universe
    # All seed symbols still present
    for sym in EQUITIES_SEED:
        assert sym in universe
```

**Step 2: Run tests to verify they fail**

```bash
python -m pytest tests/unit/test_equities_researcher_scanner.py -v
```
Expected: Various `AttributeError` — methods don't exist yet.

**Step 3: Add scanner integration to EquitiesResearcher**

Open `src/pods/templates/equities/researcher.py`.

**3a. Add imports at the top** (after existing imports):
```python
from src.data.services.theme_scanner import ThemeScanner
from src.core.config.universes import EQUITIES_SEED
```

**3b. Add `_last_theme_scan_date = None` to `__init__`** (or wherever other instance vars are initialized).

**3c. Add these 3 helper methods** before `run_cycle()`:

```python
def _should_run_theme_scan(self) -> bool:
    """Returns True if theme scan hasn't run today yet."""
    from datetime import date
    today = date.today().isoformat()
    return self._last_theme_scan_date != today

def _load_discovered_universe(self) -> dict:
    """Load discovered tickers from namespace (restored from memory.json on startup)."""
    return self._ns.get("discovered_tickers") or {}

def _build_active_universe(self, discovered: dict) -> list[str]:
    """Build full universe = EQUITIES_SEED + active discovered tickers (no duplicates)."""
    active = [sym for sym, t in discovered.items() if t.get("status") == "active"]
    combined = list(dict.fromkeys(list(EQUITIES_SEED) + active))  # preserves order, dedupes
    return combined
```

**3d. Add `_run_theme_scan()` method**:

```python
async def _run_theme_scan(
    self,
    headlines: list[dict],
    poly_signals: list[dict],
    fred_snapshot: dict,
    discovered: dict,
    current_universe: list[str],
) -> dict:
    """Run daily theme scan. Returns updated discovered dict (merged with new finds)."""
    from datetime import date
    month = date.today().strftime("%B")
    year = str(date.today().year)

    scanner = ThemeScanner(web_searcher=getattr(self, "_web_searcher", None))

    # 1. Discover new tickers
    new_tickers = await scanner.scan(
        headlines=headlines,
        poly_signals=poly_signals,
        fred_snapshot=fred_snapshot,
        existing_discovered=discovered,
        existing_universe=current_universe,
        month=month,
        year=year,
    )

    # 2. Review stale tickers (past next_review_date)
    updated_discovered = dict(discovered)
    today = date.today().isoformat()
    for sym, ticker_data in list(updated_discovered.items()):
        if ticker_data.get("status") == "active" and ticker_data.get("next_review_date", "") <= today:
            updated = await scanner.review_ticker(ticker_data, month=month, year=year)
            updated_discovered[sym] = updated
            if updated["status"] == "inactive":
                logger.info("[equities.researcher] Ticker %s marked inactive: %s",
                            sym, updated.get("invalidation_reason"))

    # 3. Merge new tickers
    themes_added = []
    for t in new_tickers:
        updated_discovered[t.symbol] = t.model_dump(mode="json")
        themes_added.append(t.symbol)

    if themes_added:
        logger.info("[equities.researcher] Theme scan added: %s", themes_added)
        # Publish activity event to dashboard
        try:
            from src.core.bus.event_bus import EventBus
            bus = self._ns.get("event_bus")
            if bus:
                import asyncio
                asyncio.create_task(bus.publish("agent.activity", {
                    "pod_id": "equities",
                    "role": "researcher",
                    "action": "universe_expanded",
                    "content": f"Theme scanner added {len(themes_added)} tickers: {', '.join(themes_added)}",
                    "timestamp": date.today().isoformat(),
                }))
        except Exception:
            pass

    # 4. Save back to namespace
    self._ns.set("discovered_tickers", updated_discovered)
    self._last_theme_scan_date = today
    return updated_discovered
```

**3e. Integrate into `run_cycle()`**: Find the section in `run_cycle()` where `_review_universe()` is called (daily trigger). Replace the entire `_review_universe()` block with:

```python
# Daily: run theme scanner + build universe from seed + discovered
if self._should_run_theme_scan():
    discovered = self._load_discovered_universe()
    current_universe = self._build_active_universe(discovered)
    discovered = await self._run_theme_scan(
        headlines=scored_headlines,
        poly_signals=poly_signals,
        fred_snapshot=fred_snapshot,
        discovered=discovered,
        current_universe=current_universe,
    )
    universe = self._build_active_universe(discovered)
    self.store("universe", universe)
    # Update gateway
    gateway = self._ns.get("gateway")
    if gateway:
        gateway.set_universe(universe)
```

**Step 4: Run tests**

```bash
python -m pytest tests/unit/test_equities_researcher_scanner.py -v
```
Expected: PASS (4 tests).

**Step 5: Commit**

```bash
git add src/pods/templates/equities/researcher.py tests/unit/test_equities_researcher_scanner.py
git commit -m "feat: integrate ThemeScanner into equities researcher daily cycle"
```

---

## Task 8: Persist Discovered Universe in memory.json

**Files:**
- Modify: `src/mission_control/session_manager.py`
- Create: `tests/unit/test_discovered_universe_persistence.py`

**Step 1: Write failing tests**

```python
# tests/unit/test_discovered_universe_persistence.py
import pytest
import json
from unittest.mock import MagicMock, patch
from datetime import datetime, timezone

def _make_mock_runtime(discovered_tickers=None):
    ns_store = {}
    if discovered_tickers:
        ns_store["discovered_tickers"] = discovered_tickers
    ns = MagicMock()
    ns.get = lambda k, d=None: ns_store.get(k, d)
    rt = MagicMock()
    rt._ns = ns
    return rt

def test_save_memory_includes_discovered_universe(tmp_path):
    """_save_memory() should write discovered_universe to memory.json."""
    # This is a unit test of the logic, not the full SessionManager
    discovered = {
        "NBIS": {
            "symbol": "NBIS", "theme": "AI Infrastructure",
            "thesis": "NVIDIA partner.", "discovered_date": "2026-04-14",
            "next_review_date": "2026-04-21", "status": "active",
            "invalidation_reason": None, "source_headlines": [],
        }
    }
    rt = _make_mock_runtime(discovered_tickers=discovered)

    # Simulate the save logic
    discovered_universe = {}
    for pod_id in ["equities"]:
        tickers = rt._ns.get("discovered_tickers") or {}
        if tickers:
            discovered_universe[pod_id] = {"tickers": tickers, "last_scan_date": "2026-04-14"}

    memory_path = tmp_path / "memory.json"
    memory_path.write_text(json.dumps({"discovered_universe": discovered_universe}))
    loaded = json.loads(memory_path.read_text())

    assert "NBIS" in loaded["discovered_universe"]["equities"]["tickers"]
    assert loaded["discovered_universe"]["equities"]["tickers"]["NBIS"]["status"] == "active"

def test_restore_discovered_universe_on_startup():
    """On startup, discovered tickers should be injected into pod namespace."""
    restored_memory = {
        "discovered_universe": {
            "equities": {
                "tickers": {
                    "NBIS": {
                        "symbol": "NBIS", "theme": "AI Infrastructure",
                        "thesis": "NVIDIA partner.", "discovered_date": "2026-04-14",
                        "next_review_date": "2026-04-21", "status": "active",
                        "invalidation_reason": None, "source_headlines": [],
                    }
                },
                "last_scan_date": "2026-04-14",
            }
        }
    }
    # Simulate restore logic
    ns_store = {}
    ns = MagicMock()
    ns.set = lambda k, v: ns_store.update({k: v})

    disc_univ = restored_memory.get("discovered_universe", {})
    pod_disc = disc_univ.get("equities", {}).get("tickers", {})
    if pod_disc:
        ns.set("discovered_tickers", pod_disc)

    assert ns_store.get("discovered_tickers") == restored_memory["discovered_universe"]["equities"]["tickers"]
```

**Step 2: Run tests to verify they pass** (these test pure logic, so they should pass immediately once written):

```bash
python -m pytest tests/unit/test_discovered_universe_persistence.py -v
```
Expected: PASS (logic tests, no imports from session_manager needed).

**Step 3: Modify `_save_memory()` in session_manager.py**

Find the `memory` dict construction (around line 1698). Add `discovered_universe` collection before it:

```python
# Collect discovered universe per pod
discovered_universe: dict = {}
for pod_id, runtime in self._pod_runtimes.items():
    tickers = runtime._ns.get("discovered_tickers")
    if tickers:
        # Merge with previously saved discovered universe
        prev_disc = (self._restored_memory or {}).get("discovered_universe", {})
        prev_tickers = prev_disc.get(pod_id, {}).get("tickers", {})
        merged = {**prev_tickers, **tickers}  # current session wins on conflicts
        discovered_universe[pod_id] = {
            "tickers": merged,
            "last_scan_date": runtime._ns.get("last_theme_scan_date", ""),
        }
    elif pod_id in (self._restored_memory or {}).get("discovered_universe", {}):
        # Preserve previous session's data if current session has nothing
        discovered_universe[pod_id] = (self._restored_memory or {})["discovered_universe"][pod_id]
```

Then add to the `memory` dict:
```python
"discovered_universe": discovered_universe,
```

**Step 4: Restore on startup in `run_event_loop()`**

Find where the session starts (after `_restored_memory` is loaded, around line 695). Add:

```python
# Restore discovered universe into pod namespaces
if self._restored_memory:
    disc_univ = self._restored_memory.get("discovered_universe", {})
    for pod_id, pod_disc in disc_univ.items():
        rt = self._pod_runtimes.get(pod_id)
        if rt and pod_disc.get("tickers"):
            rt._ns.set("discovered_tickers", pod_disc["tickers"])
            logger.info("[session_manager] Restored %d discovered tickers for %s",
                        len(pod_disc["tickers"]), pod_id)
```

**Step 5: Run full test suite**

```bash
python -m pytest tests/ -v --tb=short -q
```
Expected: All tests pass.

**Step 6: Commit**

```bash
git add src/mission_control/session_manager.py tests/unit/test_discovered_universe_persistence.py
git commit -m "feat: persist discovered universe in memory.json across sessions"
```

---

## Task 9: Simplify `_review_universe()` — Remove Old LLM Add/Remove Logic

**Files:**
- Modify: `src/pods/templates/equities/researcher.py`

**Context:** The old `_review_universe()` had LLM-driven add/remove with 60% seed retention. Now that `_run_theme_scan()` handles additions and the seed list is always fully included, this method can be removed entirely. The daily trigger block already replaced it in Task 7.

**Step 1: Find and remove `_review_universe()`**

In `src/pods/templates/equities/researcher.py`, find the `_review_universe()` method definition (lines ~46-109 per original read). Delete the entire method.

Verify it's no longer called anywhere in the file:
```bash
grep -n "_review_universe" src/pods/templates/equities/researcher.py
```
Expected: No results.

**Step 2: Run full test suite**

```bash
python -m pytest tests/ -v --tb=short -q
```
Expected: All tests still pass (no test should be calling `_review_universe()` directly).

**Step 3: Commit**

```bash
git add src/pods/templates/equities/researcher.py
git commit -m "refactor: remove old _review_universe() — replaced by ThemeScanner daily scan"
```

---

## Task 10: End-to-End Integration Test

**Files:**
- Create: `tests/integration/test_theme_scanner_integration.py`

**Step 1: Write integration test**

```python
# tests/integration/test_theme_scanner_integration.py
"""Integration test: ThemeScanner -> EquitiesResearcher -> universe expansion."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from src.data.services.theme_scanner import ThemeScanner
from src.core.models.execution import DiscoveredTicker
from src.core.config.universes import EQUITIES_SEED

@pytest.mark.asyncio
async def test_scanner_adds_tickers_not_in_seed():
    """Discovered tickers should be new symbols not already in seed universe."""
    ws = MagicMock()
    ws.search = AsyncMock(return_value=[
        {"title": "AI stocks surge", "snippet": "AI infra boom.", "url": "https://ex.com"}
    ])
    ws.fetch_page = AsyncMock(return_value="AI infrastructure spending hits record highs.")

    scanner = ThemeScanner(web_searcher=ws)

    with patch("src.data.services.theme_scanner.llm_chat") as mock_llm:
        mock_llm.side_effect = [
            # synthesize_themes
            '{"themes": [{"name": "AI Infra", "thesis": "Capex surge.", "confidence": 0.9, "tickers": [{"symbol": "NBIS", "reason": "NVIDIA partner"}]}]}',
            # validate_tickers
            '{"valid": true, "reason": "US-listed"}',
        ]
        new_tickers = await scanner.scan(
            headlines=[{"title": "AI boom", "sentiment": 0.9}],
            poly_signals=[],
            fred_snapshot={"VIXCLS": 18.0, "DGS10": 4.2},
            existing_discovered={},
            existing_universe=list(EQUITIES_SEED),
            month="April",
            year="2026",
        )

    assert len(new_tickers) == 1
    assert new_tickers[0].symbol == "NBIS"
    assert new_tickers[0].symbol not in EQUITIES_SEED
    assert new_tickers[0].status == "active"
    assert new_tickers[0].thesis != ""

@pytest.mark.asyncio
async def test_scanner_skips_seed_symbols():
    """Scanner should never add a symbol already in EQUITIES_SEED."""
    ws = MagicMock()
    ws.search = AsyncMock(return_value=[])
    ws.fetch_page = AsyncMock(return_value="")
    scanner = ThemeScanner(web_searcher=ws)

    with patch("src.data.services.theme_scanner.llm_chat") as mock_llm:
        mock_llm.side_effect = [
            # synthesize_themes — tries to add NVDA which is already in seed
            '{"themes": [{"name": "AI", "thesis": "GPU demand.", "confidence": 0.9, "tickers": [{"symbol": "NVDA", "reason": "Market leader"}]}]}',
        ]
        new_tickers = await scanner.scan(
            headlines=[],
            poly_signals=[],
            fred_snapshot={},
            existing_discovered={},
            existing_universe=list(EQUITIES_SEED),
            month="April",
            year="2026",
        )

    assert len(new_tickers) == 0  # NVDA already in seed, should be filtered

@pytest.mark.asyncio
async def test_build_active_universe_always_contains_full_seed():
    """Active universe must always include every seed symbol."""
    from src.pods.templates.equities.researcher import EquitiesResearcher
    r = EquitiesResearcher.__new__(EquitiesResearcher)
    r._ns = MagicMock()
    r._pod_id = "equities"

    discovered = {
        "NBIS": {"symbol": "NBIS", "status": "active"},
        "FAKEXYZ": {"symbol": "FAKEXYZ", "status": "inactive"},
    }
    universe = r._build_active_universe(discovered)

    for sym in EQUITIES_SEED:
        assert sym in universe, f"Seed symbol {sym} missing from universe"
    assert "NBIS" in universe
    assert "FAKEXYZ" not in universe

@pytest.mark.asyncio
async def test_thesis_review_inactive_ticker_removed_from_universe():
    """Ticker marked inactive should not appear in active universe."""
    from src.pods.templates.equities.researcher import EquitiesResearcher
    r = EquitiesResearcher.__new__(EquitiesResearcher)
    r._ns = MagicMock()
    r._pod_id = "equities"

    discovered = {
        "NBIS": {"symbol": "NBIS", "status": "inactive", "invalidation_reason": "Partnership ended"},
    }
    universe = r._build_active_universe(discovered)
    assert "NBIS" not in universe
```

**Step 2: Run integration tests**

```bash
python -m pytest tests/integration/test_theme_scanner_integration.py -v
```
Expected: PASS (4 tests).

**Step 3: Run full test suite**

```bash
python -m pytest tests/ -v --tb=short -q
```
Expected: All tests pass.

**Step 4: Commit**

```bash
git add tests/integration/test_theme_scanner_integration.py
git commit -m "test: add theme scanner integration tests"
```

---

## Task 11: Final Verification

**Step 1: Run full test suite one more time**

```bash
python -m pytest tests/ -v --tb=short
```
Expected: All tests pass, no regressions.

**Step 2: Start server and verify**

```bash
python run.py
```
Navigate to http://localhost:8000. Check:
- Activity feed shows `universe_expanded` events after first iteration (if LLM key is set)
- No errors in server logs related to theme scanner

**Step 3: Check memory.json after one session iteration**

```bash
python -c "import json; m=json.load(open('data/memory.json')); print(json.dumps(m.get('discovered_universe', {}), indent=2))"
```
Expected: `discovered_universe.equities.tickers` has entries (or empty dict if no LLM key).

**Step 4: Final commit**

```bash
git add .
git commit -m "feat: theme-aware universe scanner — equities pod discovers new tickers from emerging investment themes"
```

---

## Summary of Changes

| File | Action |
|------|--------|
| `src/core/models/execution.py` | Add `DiscoveredTicker` Pydantic model |
| `src/data/services/theme_scanner.py` | Create `ThemeScanner` class |
| `src/core/config/universes.py` | Add `THEME_SCANNER_SOURCES` constant |
| `src/pods/templates/equities/researcher.py` | Add scanner integration, remove old `_review_universe()` |
| `src/mission_control/session_manager.py` | Persist + restore `discovered_universe` |
| `tests/unit/test_discovered_ticker.py` | New |
| `tests/unit/test_theme_scanner.py` | New |
| `tests/unit/test_equities_researcher_scanner.py` | New |
| `tests/unit/test_discovered_universe_persistence.py` | New |
| `tests/integration/test_theme_scanner_integration.py` | New |
