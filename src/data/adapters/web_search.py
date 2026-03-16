"""DuckDuckGo web search adapter — gives agents access to real-time web information."""
from __future__ import annotations

import asyncio
import logging
import time

logger = logging.getLogger(__name__)

_SEARCH_TIMEOUT = 8
_MAX_SEARCHES_PER_CYCLE = 3
_INTER_SEARCH_DELAY = 2.0
_MAX_FETCH_CHARS = 3000


class WebSearchAdapter:
    """Async DuckDuckGo search + URL text extraction with rate limiting."""

    def __init__(self):
        self._cycle_search_count = 0
        self._last_search_time = 0.0

    def reset_cycle(self) -> None:
        self._cycle_search_count = 0

    async def search(self, query: str, max_results: int = 5) -> list[dict]:
        """Search DuckDuckGo. Returns [{"title", "snippet", "url"}]."""
        if self._cycle_search_count >= _MAX_SEARCHES_PER_CYCLE:
            logger.info("[web_search] Rate limit: %d searches this cycle", self._cycle_search_count)
            return []

        now = time.time()
        delay = _INTER_SEARCH_DELAY - (now - self._last_search_time)
        if delay > 0:
            await asyncio.sleep(delay)

        self._cycle_search_count += 1
        self._last_search_time = time.time()

        try:
            results = await asyncio.wait_for(
                asyncio.get_event_loop().run_in_executor(
                    None, self._sync_search, query, max_results
                ),
                timeout=_SEARCH_TIMEOUT,
            )
            logger.info("[web_search] Query '%s': %d results", query[:60], len(results))
            return results
        except asyncio.TimeoutError:
            logger.warning("[web_search] Timeout searching: %s", query[:60])
            return []
        except Exception as e:
            logger.warning("[web_search] Search failed: %s — %s", query[:60], e)
            return []

    @staticmethod
    def _sync_search(query: str, max_results: int) -> list[dict]:
        from duckduckgo_search import DDGS
        with DDGS() as ddgs:
            raw = list(ddgs.text(query, max_results=max_results))
        return [
            {"title": r.get("title", ""), "snippet": r.get("body", ""), "url": r.get("href", "")}
            for r in raw
        ]

    async def fetch_page(self, url: str, max_chars: int = _MAX_FETCH_CHARS) -> str:
        """Fetch and extract text from a URL."""
        try:
            text = await asyncio.wait_for(
                asyncio.get_event_loop().run_in_executor(
                    None, self._sync_fetch, url, max_chars
                ),
                timeout=_SEARCH_TIMEOUT,
            )
            return text
        except asyncio.TimeoutError:
            logger.warning("[web_search] Timeout fetching: %s", url[:80])
            return ""
        except Exception as e:
            logger.warning("[web_search] Fetch failed: %s — %s", url[:80], e)
            return ""

    @staticmethod
    def _sync_fetch(url: str, max_chars: int) -> str:
        import urllib.request
        from html.parser import HTMLParser

        class TextExtractor(HTMLParser):
            def __init__(self):
                super().__init__()
                self.text_parts: list[str] = []
                self._skip = False

            def handle_starttag(self, tag, attrs):
                if tag in ("script", "style", "nav", "footer", "header"):
                    self._skip = True

            def handle_endtag(self, tag):
                if tag in ("script", "style", "nav", "footer", "header"):
                    self._skip = False

            def handle_data(self, data):
                if not self._skip:
                    stripped = data.strip()
                    if stripped:
                        self.text_parts.append(stripped)

        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=6) as resp:
            html = resp.read().decode("utf-8", errors="ignore")

        extractor = TextExtractor()
        extractor.feed(html)
        full_text = " ".join(extractor.text_parts)
        return full_text[:max_chars]
