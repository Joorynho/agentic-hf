"""Theme-Aware Universe Scanner.

Runs once per day inside the equities researcher. Discovers new tickers
by scanning financial news sources and web search results for emerging
investment themes.
"""
from __future__ import annotations

import json
import logging
import re
from datetime import date, timedelta

try:
    from src.core.llm import llm_chat, has_llm_key
except Exception:  # pragma: no cover
    def llm_chat(messages, max_tokens=300):  # type: ignore[misc]
        return ""
    def has_llm_key():  # type: ignore[misc]
        return False

from src.core.config.universes import THEME_SCANNER_SOURCES as CURATED_SOURCES

logger = logging.getLogger(__name__)

_SEARCH_QUERIES = [
    "top performing stock market sectors this week {month} {year}",
    "emerging investment themes {month} {year} wall street",
    "most bought stocks by institutions this month {year}",
    "stocks breaking out highest momentum this week {month} {year}",
]

_MAX_DAILY_ADDS = 3


class ThemeScanner:
    """Discovers new equity tickers by detecting emerging investment themes."""

    def __init__(self, web_searcher=None):
        self._web_searcher = web_searcher

    async def _run_web_searches(self, month: str, year: str) -> list[dict]:
        """Run 4 targeted web searches. Returns list of {query, content} dicts."""
        summaries = []
        for query_template in _SEARCH_QUERIES:
            query = query_template.format(month=month, year=year)
            try:
                if not self._web_searcher:
                    summaries.append({"query": query, "content": ""})
                    continue
                results = await self._web_searcher.search(query, max_results=3)
                content_parts = [r.get("snippet", "") for r in results[:3]]
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

    async def synthesize_themes(
        self,
        web_results: list[dict],
        site_results: list[dict],
        headlines: list[dict],
        poly_signals: list[dict],
        fred_snapshot: dict,
        existing_universe: list[str],
    ) -> list[dict]:
        """Call LLM to synthesize themes. Returns list of theme dicts."""
        web_text = "\n".join(f"- [{r['query']}]: {r['content'][:200]}" for r in web_results if r.get("content"))
        site_text = "\n".join(f"- [{r['url']}]: {r['content'][:150]}" for r in site_results if r.get("content"))
        hl_text = "\n".join(f"- {h.get('title','')}" for h in headlines[:15])
        poly_text = "\n".join(f"- {p.get('question','')}" for p in poly_signals[:5])
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
{{"themes": [{{"name": "Theme Name", "thesis": "Why this theme has momentum...", "confidence": 0.8, "tickers": [{{"symbol": "TICK", "reason": "Why this ticker benefits"}}]}}]}}"""

        try:
            if not has_llm_key():
                return []
            raw = llm_chat([{"role": "user", "content": prompt}], max_tokens=600)
            m = re.search(r'\{[\s\S]*\}', raw)
            if not m:
                return []
            data = json.loads(m.group())
            return data.get("themes", [])
        except Exception as e:
            logger.warning("[theme_scanner] LLM synthesis failed: %s", e)
            return []

    async def validate_tickers(self, candidates: list[dict], month: str, year: str) -> list[dict]:
        """Validate candidate tickers via web search + LLM check."""
        validated = []
        for candidate in candidates:
            symbol = candidate.get("symbol", "")
            reason = candidate.get("reason", "")
            if not symbol:
                continue
            search_content = ""
            if self._web_searcher:
                try:
                    results = await self._web_searcher.search(f"{symbol} stock analysis {month} {year}", max_results=3)
                    search_content = " | ".join(r.get("snippet", "") for r in results[:3])
                except Exception as e:
                    logger.debug("[theme_scanner] Validation search failed for %s: %s", symbol, e)
            prompt = f"""Is "{symbol}" a real, US-listed stock tradeable on Alpaca?
Search evidence: {search_content or 'No results found.'}
Reason for consideration: {reason}
Output ONLY valid JSON: {{"valid": true/false, "reason": "brief explanation"}}"""
            try:
                if not has_llm_key():
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

    async def review_ticker(self, ticker_data: dict, month: str, year: str) -> dict:
        """Re-evaluate a discovered ticker's thesis. Returns updated ticker dict."""
        symbol = ticker_data.get("symbol", "")
        original_thesis = ticker_data.get("thesis", "")
        search_content = ""
        if self._web_searcher:
            try:
                results = await self._web_searcher.search(f"{symbol} stock news {month} {year}", max_results=3)
                search_content = " | ".join(r.get("snippet", "") for r in results[:3])
            except Exception as e:
                logger.debug("[theme_scanner] Review search failed for %s: %s", symbol, e)
        prompt = f"""Does this investment thesis still hold for {symbol}?
Original thesis: {original_thesis}
Recent news: {search_content or 'No recent news found.'}
Output ONLY valid JSON: {{"still_valid": true/false, "reason": "brief explanation"}}"""
        try:
            if not has_llm_key():
                next_review = (date.today() + timedelta(days=7)).isoformat()
                return {**ticker_data, "next_review_date": next_review}
            raw = llm_chat([{"role": "user", "content": prompt}], max_tokens=100)
            m = re.search(r'\{[^}]+\}', raw)
            if m:
                data = json.loads(m.group())
                if data.get("still_valid"):
                    next_review = (date.today() + timedelta(days=7)).isoformat()
                    return {**ticker_data, "next_review_date": next_review}
                else:
                    return {**ticker_data, "status": "inactive", "invalidation_reason": data.get("reason", "Thesis invalidated")}
        except Exception as e:
            logger.debug("[theme_scanner] Review LLM failed for %s: %s", symbol, e)
        next_review = (date.today() + timedelta(days=7)).isoformat()
        return {**ticker_data, "next_review_date": next_review}

    async def scan(
        self,
        headlines: list[dict],
        poly_signals: list[dict],
        fred_snapshot: dict,
        existing_discovered: dict,
        existing_universe: list[str],
        month: str,
        year: str,
    ) -> list:
        """Run full daily theme scan. Returns list of new DiscoveredTicker objects."""
        from src.core.models.execution import DiscoveredTicker

        web_results = await self._run_web_searches(month=month, year=year)
        site_results = await self._scrape_curated_sites()

        themes = await self.synthesize_themes(
            web_results=web_results, site_results=site_results, headlines=headlines,
            poly_signals=poly_signals, fred_snapshot=fred_snapshot,
            existing_universe=existing_universe,
        )
        if not themes:
            logger.info("[theme_scanner] No themes identified this cycle.")
            return []

        candidates = []
        for theme in themes:
            for t in theme.get("tickers", []):
                sym = (t.get("symbol") or "").upper().strip()
                if not sym or sym in existing_universe or sym in existing_discovered:
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

        validated = await self.validate_tickers(candidates, month=month, year=year)
        today = date.today().isoformat()
        review_date = (date.today() + timedelta(days=7)).isoformat()
        new_tickers = []
        for v in validated[:_MAX_DAILY_ADDS]:
            new_tickers.append(DiscoveredTicker(
                symbol=v["symbol"], theme=v["theme"], thesis=v["thesis"],
                discovered_date=today, next_review_date=review_date,
                status="active", source_headlines=v.get("source_headlines", []),
            ))

        logger.info("[theme_scanner] Discovered %d new tickers: %s", len(new_tickers), [t.symbol for t in new_tickers])
        return new_tickers
