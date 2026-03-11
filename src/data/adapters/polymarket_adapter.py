from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone

import aiohttp
from tenacity import retry, stop_after_attempt, wait_exponential

from src.core.models.polymarket import PolymarketSignal
from src.data.cache.parquet_cache import ParquetCache

logger = logging.getLogger(__name__)

GAMMA_BASE = "https://gamma-api.polymarket.com"
CLOB_BASE = "https://clob.polymarket.com"

DEFAULT_LIMIT = 20
DEEP_LIMIT = 40

# Fetch more from API since many will be filtered out
FETCH_MULTIPLIER = 5

# Series slugs to always exclude (sports, esports, entertainment)
BLOCKED_SERIES = {
    "nba-2026", "nba-2025", "nfl-2025", "nfl-2026", "nhl-2025", "nhl-2026",
    "mlb-2025", "mlb-2026", "counter-strike", "dota-2", "league-of-legends",
    "valorant", "elon-tweets-48h", "elon-tweets-24h", "jesus-christ-return",
    "btc-multi-strikes-weekly",
}

# Keywords in question/slug that disqualify a market
BLOCKED_KEYWORDS = [
    "premier league", "la liga", "champions league", "serie a", "bundesliga",
    "world cup", "fifa", "nba", "nfl", "nhl", "mlb", "ufc", "mma",
    "boxing", "tennis", "formula 1", "f1 grand prix", "cricket",
    "counter-strike", "dota", "valorant", "overwatch", "esport",
    "oscar", "grammy", "emmy", "golden globe", "academy award",
    "bachelor", "bachelorette", "love island", "survivor",
    "tiktok", "youtube", "twitch", "streamer",
    "elon musk post", "elon musk tweet",
    "jesus christ", "alien", "ufo",
    "map pool", "overpass",
]

# Keywords that indicate macro relevance (at least one must match)
MACRO_KEYWORDS = [
    # Central banking & monetary policy
    "fed ", "federal reserve", "fomc", "interest rate", "rate cut", "rate hike",
    "basis points", "bps", "monetary policy", "quantitative", "central bank",
    "ecb", "bank of england", "bank of japan", "pboc",
    # Inflation & prices
    "inflation", "cpi", "pce", "deflation", "price index",
    "oil price", "crude oil", "gold price", "commodity",
    "bitcoin", "crypto", "ethereum",
    # Economy & growth
    "gdp", "recession", "economic growth", "unemployment", "jobs report",
    "nonfarm", "payroll", "consumer confidence", "retail sales",
    "housing", "manufacturing",
    # Fiscal & government
    "debt ceiling", "government shutdown", "deficit", "fiscal",
    "stimulus", "infrastructure bill", "spending bill",
    # Trade & geopolitics
    "tariff", "trade war", "sanctions", "embargo", "trade deal",
    "nato", "war", "invasion", "ceasefire", "military",
    "nuclear", "missile", "strait of hormuz",
    # Politics (elections & leadership)
    "president", "election", "senate", "congress", "parliament",
    "prime minister", "chancellor", "impeach", "resign",
    "regime", "coup",
    # Markets & regulation
    "s&p 500", "s&p500", "nasdaq", "dow jones", "stock market",
    "bear market", "bull market", "correction",
    "sec ", "regulation", "antitrust",
    # Country/region risks
    "iran", "china", "russia", "ukraine", "taiwan", "israel",
    "gaza", "north korea", "syria", "venezuela",
]


class PolymarketAdapter:
    """Fetches trending Polymarket markets via the Gamma Markets API.

    Uses the Gamma API for market discovery (sorted by 24h volume) and
    extracts inline outcome prices — no extra CLOB orderbook calls needed.

    Gracefully degrades: returns [] when API key is absent or any request fails.
    """

    def __init__(
        self,
        api_key: str | None = None,
        cache: ParquetCache | None = None,
    ) -> None:
        self._api_key = api_key if api_key is not None else os.getenv("POLYMARKET_API_KEY", "")
        self._cache = cache
        self._has_key = bool(self._api_key)

    async def fetch_signals(self, tags: list[str]) -> list[PolymarketSignal]:
        """Return PolymarketSignal objects for the most active markets."""
        if not self._has_key:
            logger.info("POLYMARKET_API_KEY not set — returning empty signal list")
            return []
        try:
            return await self._fetch_from_gamma_api(tags, limit=DEFAULT_LIMIT)
        except Exception as exc:
            logger.info("Polymarket fetch failed (non-critical): %s", exc)
            return []

    async def fetch_signals_deep(self, tags: list[str]) -> list[PolymarketSignal]:
        """Wider scan for the daily deep refresh — returns up to DEEP_LIMIT markets."""
        if not self._has_key:
            return []
        try:
            return await self._fetch_from_gamma_api(tags, limit=DEEP_LIMIT)
        except Exception as exc:
            logger.info("Polymarket deep fetch failed (non-critical): %s", exc)
            return []

    async def _fetch_from_gamma_api(
        self, tags: list[str], limit: int = DEFAULT_LIMIT
    ) -> list[PolymarketSignal]:
        timeout = aiohttp.ClientTimeout(total=15, connect=5)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            markets = await self._get_trending_markets(session, tags, limit)
            signals = []
            for market in markets:
                sig = self._market_to_signal(market)
                if sig is not None:
                    signals.append(sig)
            return signals

    @retry(stop=stop_after_attempt(2), wait=wait_exponential(multiplier=1, min=1, max=5))
    async def _get_trending_markets(
        self, session: aiohttp.ClientSession, tags: list[str], limit: int = DEFAULT_LIMIT
    ) -> list[dict]:
        """Fetch top macro-relevant markets by 24h volume from the Gamma Markets API."""
        params = {
            "active": "true",
            "closed": "false",
            "limit": str(limit * FETCH_MULTIPLIER),
            "order": "volume24hr",
            "ascending": "false",
        }
        async with session.get(f"{GAMMA_BASE}/markets", params=params) as resp:
            resp.raise_for_status()
            data = await resp.json()

        markets = data if isinstance(data, list) else data.get("data", [])
        now = datetime.now(timezone.utc)
        filtered = []
        for m in markets:
            if not m.get("active") or m.get("closed"):
                continue
            if float(m.get("volume24hr", 0) or 0) <= 0:
                continue
            end_raw = m.get("endDate") or m.get("end_date")
            if end_raw:
                try:
                    end_dt = datetime.fromisoformat(end_raw.replace("Z", "+00:00"))
                    if end_dt < now:
                        continue
                except (ValueError, TypeError):
                    pass
            if not self._is_macro_relevant(m):
                continue
            filtered.append(m)
        markets = filtered
        if tags:
            markets = [
                m for m in markets
                if any(t.lower() in (m.get("question", "") + " ".join(m.get("outcomes", []))).lower() for t in tags)
            ]
        return markets[:limit]

    @staticmethod
    def _is_macro_relevant(market: dict) -> bool:
        """Filter market for macro hedge fund relevance.

        Excludes sports, esports, entertainment, and meme markets.
        Requires at least one macro-relevant keyword in the question or slug.
        """
        series_slugs = set()
        for ev in (market.get("events") or []):
            for sr in (ev.get("series") or []):
                slug = sr.get("slug", "")
                if slug:
                    series_slugs.add(slug)

        if series_slugs & BLOCKED_SERIES:
            return False

        question = market.get("question", "")
        slug = market.get("slug", "")
        text = (question + " " + slug).lower()

        for bk in BLOCKED_KEYWORDS:
            if bk in text:
                return False

        for mk in MACRO_KEYWORDS:
            if mk in text:
                return True

        return False

    @staticmethod
    def _parse_end_date(market: dict) -> datetime | None:
        """Extract and parse the market end date."""
        end_raw = market.get("endDate") or market.get("end_date")
        if not end_raw:
            return None
        try:
            return datetime.fromisoformat(end_raw.replace("Z", "+00:00"))
        except (ValueError, TypeError):
            return None

    @staticmethod
    def _market_to_signal(market: dict) -> PolymarketSignal | None:
        """Convert a Gamma API market dict into a PolymarketSignal."""
        outcome_prices = market.get("outcomePrices")
        if not outcome_prices:
            return None

        if isinstance(outcome_prices, str):
            try:
                outcome_prices = json.loads(outcome_prices)
            except (json.JSONDecodeError, TypeError):
                return None
        if len(outcome_prices) < 2:
            return None

        yes_price = float(outcome_prices[0])
        no_price = float(outcome_prices[1])

        total = yes_price + no_price
        implied_prob = yes_price / total if total > 0 else 0.5

        implied_prob = max(0.0, min(1.0, implied_prob))
        yes_price = max(0.0, min(1.0, yes_price))
        no_price = max(0.0, min(1.0, no_price))

        spread_val = float(market.get("spread", 0) or 0) or abs(yes_price - no_price)

        event_tags: list[str] = []
        events = market.get("events") or []
        for ev in events:
            if isinstance(ev, dict):
                slug = ev.get("slug", "")
                if slug:
                    event_tags.append(slug)

        end_date = PolymarketAdapter._parse_end_date(market)

        return PolymarketSignal(
            market_id=market.get("conditionId", market.get("condition_id", "")),
            question=market.get("question", ""),
            yes_price=round(yes_price, 6),
            no_price=round(no_price, 6),
            implied_prob=round(implied_prob, 6),
            spread=round(spread_val, 6),
            volume_24h=float(market.get("volume24hr", 0) or 0),
            open_interest=float(market.get("liquidityNum", 0) or market.get("liquidity", 0) or 0),
            timestamp=datetime.now(timezone.utc),
            end_date=end_date,
            tags=event_tags,
        )
