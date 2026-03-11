from __future__ import annotations

import logging
from typing import Optional

from src.core.bus.event_bus import EventBus
from src.data.adapters.fred_adapter import FredAdapter
from src.data.adapters.market_tracker import MarketTracker
from src.data.adapters.polymarket_adapter import PolymarketAdapter
from src.data.adapters.rss_adapter import RssAdapter
from src.data.adapters.x_adapter import XAdapter
from src.pods.base.agent import BasePodAgent
from src.pods.base.namespace import PodNamespace

logger = logging.getLogger(__name__)
UNIVERSE = ["SPY", "TLT", "GLD", "UUP", "EEM"]
POLY_TAGS: list[str] = []

POLY_WEIGHT = 0.5
FRED_WEIGHT = 0.3
SOCIAL_WEIGHT = 0.2


class GammaResearcher(BasePodAgent):
    """Fetches FRED macro indicators, Polymarket odds, RSS news, and news feed.

    Blends three signal sources into a composite macro_score:
      macro_score = 0.5 * polymarket_sentiment + 0.3 * fred_score + 0.2 * news_score
    """

    def __init__(
        self,
        agent_id: str,
        pod_id: str,
        namespace: PodNamespace,
        bus: EventBus,
        polymarket_adapter: Optional[PolymarketAdapter] = None,
        market_tracker: Optional[MarketTracker] = None,
        fred_adapter: Optional[FredAdapter] = None,
        rss_adapter: Optional[RssAdapter] = None,
        x_adapter: Optional[XAdapter] = None,
    ) -> None:
        super().__init__(agent_id, pod_id, namespace, bus)
        self.polymarket_adapter = polymarket_adapter
        self.market_tracker = market_tracker
        self.fred_adapter = fred_adapter
        self.rss_adapter = rss_adapter
        self.x_adapter = x_adapter

    async def run_cycle(self, context: dict) -> dict:
        self.store("universe", UNIVERSE)

        poly_signals = await self._fetch_polymarket()
        fred_snapshot = await self._fetch_fred()
        macro_news = await self._fetch_rss()
        x_feed, x_news = await self._fetch_x()

        self.store("polymarket_signals", poly_signals)
        self.store("fred_snapshot", fred_snapshot)
        self.store("macro_news", [n.model_dump(mode="json") for n in macro_news])
        self.store("macro_news_count", len(macro_news))
        self.store("x_feed", x_feed)
        self.store("x_tweet_count", len(x_feed))

        poly_sentiment = self._compute_poly_sentiment(poly_signals)
        fred_score = self._compute_fred_score(fred_snapshot)
        social_score = self._compute_social_score(x_news)

        sources = []
        weights = []
        scores = []
        if poly_signals:
            sources.append("poly")
            weights.append(POLY_WEIGHT)
            scores.append(poly_sentiment)
        if fred_snapshot:
            sources.append("fred")
            weights.append(FRED_WEIGHT)
            scores.append(fred_score)
        if x_feed:
            sources.append("news")
            weights.append(SOCIAL_WEIGHT)
            scores.append(social_score)

        if weights:
            total_weight = sum(weights)
            macro_score = sum(w * s for w, s in zip(weights, scores)) / total_weight
        else:
            macro_score = 0.0

        confidence = (macro_score / 2.0) + 0.5
        self.store("polymarket_confidence", round(confidence, 6))
        self.store("macro_score", round(macro_score, 6))
        self.store("fred_score", round(fred_score, 6))
        self.store("poly_sentiment", round(poly_sentiment, 6))
        self.store("social_score", round(social_score, 6))
        self.store("researcher_ok", True)

        logger.info(
            "[gamma.researcher] poly=%.3f fred=%.3f news=%.3f → macro=%.3f | rss=%d feed=%d",
            poly_sentiment, fred_score, social_score, macro_score,
            len(macro_news), len(x_feed),
        )
        return {"universe": UNIVERSE, "poly_signals": poly_signals}

    async def _fetch_polymarket(self) -> list:
        if not self.polymarket_adapter:
            return []
        try:
            if self.market_tracker and self.market_tracker.should_deep_refresh():
                raw = await self.polymarket_adapter.fetch_signals_deep(POLY_TAGS)
                self.market_tracker.mark_deep_refresh_done()
                logger.info("[gamma.researcher] Deep refresh: %d raw signals", len(raw))
            else:
                raw = await self.polymarket_adapter.fetch_signals(POLY_TAGS)
                logger.info("[gamma.researcher] Fetched %d raw signals", len(raw))

            if self.market_tracker:
                signals = self.market_tracker.update(raw)
                logger.info("[gamma.researcher] Tracker: %d markets", self.market_tracker.watchlist_size)
            else:
                signals = [s.model_dump(mode="json") for s in raw]
            return signals
        except Exception as exc:
            logger.info("[gamma.researcher] Polymarket failed: %s", exc)
            return []

    async def _fetch_fred(self) -> dict[str, float]:
        if not self.fred_adapter:
            return {}
        try:
            snapshot = await self.fred_adapter.fetch_snapshot()
            logger.info("[gamma.researcher] FRED: %d series", len(snapshot))
            return snapshot
        except Exception as exc:
            logger.info("[gamma.researcher] FRED failed: %s", exc)
            return {}

    async def _fetch_rss(self) -> list:
        if not self.rss_adapter:
            return []
        try:
            items = await self.rss_adapter.fetch_news()
            logger.info("[gamma.researcher] RSS: %d articles", len(items))
            return items
        except Exception as exc:
            logger.info("[gamma.researcher] RSS failed: %s", exc)
            return []

    async def _fetch_x(self) -> tuple[list[dict], list]:
        """Fetch news RSS feed. Returns (raw_headline_dicts, NewsItem_list)."""
        if not self.x_adapter:
            return [], []
        try:
            raw_tweets, news_items = await self.x_adapter.fetch_tweets()
            logger.info("[gamma.researcher] News feed: %d headlines", len(raw_tweets))
            return raw_tweets, news_items
        except Exception as exc:
            logger.info("[gamma.researcher] News feed failed: %s", exc)
            return [], []

    @staticmethod
    def _compute_poly_sentiment(signals: list) -> float:
        if not signals:
            return 0.0
        total_vol = sum(s.get("volume_24h", 0) for s in signals)
        if total_vol > 0:
            confidence = sum(
                (s.get("volume_24h", 0) / total_vol) * s.get("implied_prob", 0.5)
                for s in signals
            )
        else:
            confidence = sum(s.get("implied_prob", 0.5) for s in signals) / len(signals)
        return (confidence - 0.5) * 2

    @staticmethod
    def _compute_social_score(x_news: list) -> float:
        """Average sentiment from news feed, scaled to [-1, +1]."""
        if not x_news:
            return 0.0
        sentiments = [getattr(item, "sentiment", 0.0) for item in x_news]
        return sum(sentiments) / len(sentiments)

    @staticmethod
    def _compute_fred_score(snapshot: dict[str, float]) -> float:
        """Composite score from FRED indicators, scaled to [-1, +1].

        Components:
        - Yield curve slope (T10Y2Y): positive = expansion, negative = inversion risk
        - VIX level (VIXCLS): low = calm, high = stress
        - Credit spread (BAMLH0A0HYM2): tight = risk-on, wide = risk-off
        """
        if not snapshot:
            return 0.0

        score = 0.0
        components = 0

        slope = snapshot.get("T10Y2Y")
        if slope is not None:
            slope_score = max(-1.0, min(1.0, slope / 2.0))
            score += slope_score
            components += 1

        vix = snapshot.get("VIXCLS")
        if vix is not None:
            # VIX 12 → +1.0 (calm), VIX 20 → 0.0 (neutral), VIX 35 → -1.0 (stress)
            vix_score = max(-1.0, min(1.0, (20.0 - vix) / 15.0))
            score += vix_score
            components += 1

        spread = snapshot.get("BAMLH0A0HYM2")
        if spread is not None:
            # Spread 3% → +0.5 (normal), 5% → 0.0, 8% → -1.0 (stress)
            spread_score = max(-1.0, min(1.0, (5.0 - spread) / 3.0))
            score += spread_score
            components += 1

        return score / max(components, 1)
