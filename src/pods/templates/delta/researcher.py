from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from src.core.bus.event_bus import EventBus
from src.data.adapters.gdelt_adapter import GdeltAdapter
from src.data.adapters.rss_adapter import RssAdapter
from src.data.adapters.x_adapter import XAdapter
from src.pods.base.agent import BasePodAgent
from src.pods.base.namespace import PodNamespace

logger = logging.getLogger(__name__)
UNIVERSE = ["AAPL", "MSFT", "AMZN", "GOOGL", "META"]

RECENCY_WINDOW = timedelta(hours=6)


class DeltaResearcher(BasePodAgent):
    """GDELT event scoring + RSS financial news.

    When adapters are provided, computes event_score from real news
    articles: count of relevant articles (matching UNIVERSE tickers)
    weighted by recency. Falls back to synthetic scoring in backtest mode.
    """

    def __init__(
        self,
        agent_id: str,
        pod_id: str,
        namespace: PodNamespace,
        bus: EventBus,
        gdelt_adapter: Optional[GdeltAdapter] = None,
        rss_adapter: Optional[RssAdapter] = None,
        x_adapter: Optional[XAdapter] = None,
    ) -> None:
        super().__init__(agent_id, pod_id, namespace, bus)
        self.gdelt_adapter = gdelt_adapter
        self.rss_adapter = rss_adapter
        self.x_adapter = x_adapter

    async def run_cycle(self, context: dict) -> dict:
        self.store("universe", UNIVERSE)

        has_adapters = self.gdelt_adapter or self.rss_adapter or self.x_adapter
        if has_adapters:
            event_score, news_items, x_count, x_sentiment = await self._score_from_live_news()
        else:
            event_score = self._synthetic_score(context)
            news_items = []
            x_count = 0
            x_sentiment = 0.0

        self.store("event_score", event_score)
        self.store("news_items", [n.model_dump(mode="json") for n in news_items])
        self.store("news_count", len(news_items))
        self.store("x_tweet_count", x_count)
        self.store("social_sentiment", round(x_sentiment, 4))
        self.store("researcher_ok", True)
        return {"event_score": event_score, "universe": UNIVERSE}

    async def _score_from_live_news(self) -> tuple[float, list, int, float]:
        """Returns (event_score, news_items, x_tweet_count, x_avg_sentiment)."""
        all_news = []
        x_sentiments: list[float] = []
        x_count = 0

        if self.gdelt_adapter:
            try:
                gdelt_items = await self.gdelt_adapter.fetch_articles()
                all_news.extend(gdelt_items)
                logger.info("[delta.researcher] GDELT: %d articles", len(gdelt_items))
            except Exception as exc:
                logger.info("[delta.researcher] GDELT fetch failed: %s", exc)

        if self.rss_adapter:
            try:
                rss_items = await self.rss_adapter.fetch_news()
                all_news.extend(rss_items)
                logger.info("[delta.researcher] RSS: %d articles", len(rss_items))
            except Exception as exc:
                logger.info("[delta.researcher] RSS fetch failed: %s", exc)

        if self.x_adapter:
            try:
                _raw_tweets, x_items = await self.x_adapter.fetch_tweets()
                all_news.extend(x_items)
                x_count = len(x_items)
                x_sentiments = [item.sentiment for item in x_items]
                logger.info("[delta.researcher] News feed: %d headlines", x_count)
            except Exception as exc:
                logger.info("[delta.researcher] X fetch failed: %s", exc)

        x_avg_sentiment = (
            sum(x_sentiments) / len(x_sentiments) if x_sentiments else 0.0
        )

        if not all_news:
            return 0.3, [], x_count, x_avg_sentiment

        now = datetime.now(timezone.utc)
        universe_upper = {t.upper() for t in UNIVERSE}
        relevant = []
        for item in all_news:
            item_entities = {e.upper() for e in item.entities}
            if item_entities & universe_upper:
                relevant.append(item)

        if not relevant:
            base_score = min(0.5, len(all_news) / 100.0)
            return round(base_score, 4), all_news[:20], x_count, x_avg_sentiment

        weighted_sum = 0.0
        for item in relevant:
            age = max((now - item.timestamp).total_seconds(), 0)
            recency_weight = max(0.0, 1.0 - age / RECENCY_WINDOW.total_seconds())
            sentiment_boost = 1.0 + abs(item.sentiment)
            weighted_sum += recency_weight * sentiment_boost

        score = min(1.0, 0.3 + weighted_sum * 0.1)
        return round(score, 4), all_news[:30], x_count, x_avg_sentiment

    @staticmethod
    def _synthetic_score(context: dict) -> float:
        """Deterministic synthetic score for backtest mode."""
        bar = context.get("bar")
        if bar is None:
            return 0.0
        bar_ts = int(bar.timestamp.timestamp()) % 100
        return 0.8 if bar_ts < 5 else 0.3
