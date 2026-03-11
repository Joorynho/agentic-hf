"""Article fetcher — extracts readable text from news article URLs.

Used by PM agents when they want to deep-dive into a headline before
making a trading decision. Caches results for 30 minutes.
"""
from __future__ import annotations

import asyncio
import html
import logging
import re
import time

logger = logging.getLogger(__name__)

CACHE_TTL = 1800.0
REQUEST_TIMEOUT = 10
MAX_ARTICLE_CHARS = 1500
MAX_ARTICLES_PER_CYCLE = 3

_SCRIPT_STYLE_RE = re.compile(r"<(script|style|noscript)[^>]*>.*?</\1>", re.DOTALL | re.IGNORECASE)
_TAG_RE = re.compile(r"<[^>]+>")
_WHITESPACE_RE = re.compile(r"\s+")

_PARAGRAPH_RE = re.compile(r"<p[^>]*>(.*?)</p>", re.DOTALL | re.IGNORECASE)
_ARTICLE_RE = re.compile(r"<article[^>]*>(.*?)</article>", re.DOTALL | re.IGNORECASE)


class ArticleFetcher:
    """Fetches and extracts readable text from news article URLs."""

    def __init__(self) -> None:
        self._cache: dict[str, tuple[float, str]] = {}

    async def fetch_article(self, url: str) -> str:
        """Fetch and extract article text. Returns empty string on failure."""
        if not url or not url.startswith("http"):
            return ""

        now = time.time()
        cached = self._cache.get(url)
        if cached and (now - cached[0]) < CACHE_TTL:
            return cached[1]

        try:
            text = await asyncio.wait_for(
                asyncio.to_thread(self._fetch_sync, url), timeout=REQUEST_TIMEOUT
            )
            if text:
                self._cache[url] = (now, text)
            return text
        except asyncio.TimeoutError:
            logger.debug("[article_fetcher] Timeout fetching %s", url[:80])
            return cached[1] if cached else ""
        except Exception as exc:
            logger.debug("[article_fetcher] Failed to fetch %s: %s", url[:80], exc)
            return cached[1] if cached else ""

    async def fetch_articles(self, urls: list[str]) -> dict[str, str]:
        """Fetch multiple articles (capped at MAX_ARTICLES_PER_CYCLE)."""
        results: dict[str, str] = {}
        for url in urls[:MAX_ARTICLES_PER_CYCLE]:
            text = await self.fetch_article(url)
            if text:
                results[url] = text
        return results

    def _fetch_sync(self, url: str) -> str:
        import requests

        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "text/html,application/xhtml+xml,*/*",
        }
        resp = requests.get(url, headers=headers, timeout=REQUEST_TIMEOUT, allow_redirects=True)
        if resp.status_code != 200:
            return ""

        raw_html = resp.text
        return self._extract_text(raw_html)

    def _extract_text(self, raw_html: str) -> str:
        """Extract readable article text from HTML."""
        cleaned = _SCRIPT_STYLE_RE.sub("", raw_html)

        # Try to find <article> block first (most news sites use it)
        article_match = _ARTICLE_RE.search(cleaned)
        if article_match:
            cleaned = article_match.group(1)

        # Extract text from <p> tags (main article body)
        paragraphs = _PARAGRAPH_RE.findall(cleaned)
        if paragraphs:
            texts = []
            for p in paragraphs:
                p_text = _TAG_RE.sub("", p)
                p_text = html.unescape(p_text)
                p_text = _WHITESPACE_RE.sub(" ", p_text).strip()
                if len(p_text) > 30:
                    texts.append(p_text)
            body = "\n\n".join(texts)
        else:
            body = _TAG_RE.sub(" ", cleaned)
            body = html.unescape(body)
            body = _WHITESPACE_RE.sub(" ", body).strip()

        if len(body) > MAX_ARTICLE_CHARS:
            body = body[:MAX_ARTICLE_CHARS] + "..."

        return body
