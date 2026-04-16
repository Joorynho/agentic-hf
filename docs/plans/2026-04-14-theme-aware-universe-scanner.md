# Theme-Aware Universe Scanner

**Date:** 2026-04-14
**Status:** Approved
**Scope:** Equities pod only

## Problem

The equities pod trades from a fixed seed universe of ~80 symbols. It cannot discover new tickers based on emerging investment themes. A stock like NBIS (Nebius) — which partnered with NVIDIA and Microsoft during an AI infrastructure boom — would never be considered because it's not in the seed list and there's no mechanism to find it.

The existing `_review_universe()` is reactive (swaps symbols based on headlines about tickers it already knows) rather than proactive (spots trending themes, then finds the tickers).

## Solution

A **Theme-Aware Universe Scanner** that runs daily inside the equities researcher:

1. **Scans** — 4 targeted web searches + 7 curated financial site scrapes to detect trending sectors, themes, institutional flows, and breakout stocks
2. **Synthesizes** — LLM combines web results + existing headlines + Polymarket signals + FRED macro context into 2-3 actionable themes, each with 3-5 candidate tickers
3. **Validates** — Per-ticker confirmation web search to verify thesis
4. **Adds** — Validated tickers join the universe with thesis, discovery date, and 7-day review date
5. **Reviews** — Every 7 days, re-evaluates discovered tickers. Invalid thesis -> moved to inactive
6. **Persists** — All discovered tickers saved in `memory.json`. Seed list is never modified.

## Key Rules

- Seed list is permanent and untouchable
- Discovered tickers are additive (universe = seed + active discovered)
- Each discovered ticker has a thesis; if thesis is invalidated, ticker goes inactive
- Inactive tickers stay in memory for history but are excluded from active universe
- Target: 10-15 new tickers per week (~2-3 per day)

## Architecture

### Daily Cycle Flow

```
1. ResearchIngestionService fetches headlines/FRED/Poly (shared, already exists)
2. Researcher scores headlines via LLM sentiment (already exists)
3. NEW -> ThemeScanner.scan_themes():
   |-- 4 web searches (sector momentum, trending themes, institutional flow, breakouts)
   |-- 7 curated site scrapes (TradingKey, Calcalistech, Investing.com, etc.)
   |-- LLM synthesis: all sources -> 2-3 themes with candidate tickers
   |-- Validation web search per candidate -> confirmed or rejected
4. ThemeScanner.review_stale_tickers():
   |-- Any ticker past next_review_date gets web search + LLM check
   |-- Thesis still valid -> extend review date 7 days
   |-- Thesis invalid -> mark inactive with reason
5. Build universe: EQUITIES_SEED + all active discovered tickers
6. Gateway.set_universe(combined)
7. PM gets price context for all symbols next cycle
```

### Web Search Queries (4 per day)

```
1. "top performing stock market sectors this week {month} {year}"
2. "emerging investment themes {month} {year} wall street"
3. "most bought stocks by institutions this month {year}"
4. "stocks breaking out highest momentum this week {month} {year}"
```

Each returns top 3 results. Top result page content fetched for each.

### Curated Source URLs (7 per day)

```
1. https://www.tradingkey.com/news
2. https://www.calcalistech.com/ctechnews
3. https://www.investing.com/news
4. https://www.thestreet.com/markets
5. https://simplywall.st/discover/gb/investing-ideas
6. https://simplywall.st/stocks
7. https://simplywall.st/markets/us
```

Scraped via `WebSearchAdapter.fetch_page()`. Graceful fallback if blocked/empty.

### LLM Theme Synthesis Prompt

```
You are an equity research analyst identifying emerging investment themes.

Given:
- Web research: {4 search result summaries}
- Curated financial sites: {7 site scrape summaries}
- Recent headlines: {top 15 scored headlines}
- Polymarket signals: {top 5 signals}
- Macro context: VIX={x}, 10Y={x}, regime={x}

Identify 2-3 emerging investment themes with real momentum.
For each theme, suggest 3-5 specific US-listed stock tickers that benefit.
Only suggest tickers NOT in this existing universe: {seed_list}

Output JSON:
{
  "themes": [
    {
      "name": "AI Infrastructure Buildout",
      "thesis": "Hyperscaler capex surging 40% YoY...",
      "confidence": 0.8,
      "tickers": [
        {"symbol": "NBIS", "reason": "Cloud AI partnership with NVIDIA/MSFT"},
        {"symbol": "VRT", "reason": "Data center power/cooling provider"}
      ]
    }
  ]
}
```

### Ticker Validation

Per candidate: web search `"{symbol} stock analysis {month} {year}"`
LLM confirms: is it US-listed? Does search confirm thesis? Accept or reject.

### Thesis Review (7-day cycle)

Per stale ticker: web search `"{symbol} stock news {month} {year}"`
LLM checks: does original thesis still hold? If yes -> extend 7 days. If no -> inactive.

## Data Model

### DiscoveredTicker (stored in memory.json)

```json
{
  "symbol": "NBIS",
  "theme": "AI Infrastructure",
  "thesis": "Cloud AI infra provider, NVIDIA/MSFT partnerships...",
  "discovered_date": "2026-04-14",
  "next_review_date": "2026-04-21",
  "status": "active",
  "invalidation_reason": null,
  "source_headlines": ["Nebius partners with NVIDIA..."]
}
```

### Memory.json Structure

```json
{
  "discovered_universe": {
    "equities": {
      "tickers": { "NBIS": {...}, "VRT": {...} },
      "themes_log": [
        {
          "name": "AI Infrastructure",
          "thesis": "Hyperscaler capex surging...",
          "detected_date": "2026-04-14",
          "tickers_added": ["NBIS", "VRT"]
        }
      ],
      "last_scan_date": "2026-04-14"
    }
  }
}
```

### Startup Flow

1. SessionManager loads `memory.json`
2. Equities researcher reads `discovered_universe.equities.tickers`
3. Filters to `status == "active"`
4. Universe = `EQUITIES_SEED` + active discovered tickers
5. `gateway.set_universe(combined)`

## Files

### Create
- `src/data/services/theme_scanner.py` — ThemeScanner class

### Modify
- `src/pods/templates/equities/researcher.py` — call scanner daily, load/save discovered tickers
- `src/mission_control/session_manager.py` — persist `discovered_universe` in `_save_memory()`, restore on startup
- `src/core/config/universes.py` — add scanner source URLs constant

### No Changes
- `src/pods/base/gateway.py` — already supports dynamic `set_universe()`
- Other pod researchers (FX, crypto, commodities)
- PM agents — already trade whatever's in universe
- `src/data/adapters/web_search.py` — already has `search()` and `fetch_page()`

## Daily Resource Budget

- ~8 web searches (free, DuckDuckGo)
- ~7 page scrapes (free)
- ~2 LLM calls (theme synthesis + thesis review)
- Fits within existing free-tier rate limits

## Testing Strategy

- Mock `WebSearchAdapter` and `llm_chat` in all tests
- Test theme extraction with synthetic search results
- Test ticker validation (accept real, reject fake)
- Test thesis review (active -> inactive flow)
- Test persistence round-trip (save to memory.json, restore, verify universe)
- Test seed list is never modified
- Test graceful fallback when curated sites are blocked
