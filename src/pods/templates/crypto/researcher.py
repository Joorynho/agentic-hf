from __future__ import annotations
import json
import logging
from datetime import datetime, timezone
from typing import Optional, TYPE_CHECKING
from src.core.bus.event_bus import EventBus
from src.core.config.universes import CRYPTO_SEED
from src.core.models.messages import AgentMessage
from src.core.scoring import compute_macro_score
from src.data.adapters.fred_adapter import FredAdapter
from src.data.adapters.polymarket_adapter import PolymarketAdapter
from src.data.adapters.market_tracker import MarketTracker
from src.data.adapters.rss_adapter import RssAdapter
from src.data.adapters.x_adapter import XAdapter
from src.pods.base.agent import BasePodAgent
from src.pods.base.namespace import PodNamespace

if TYPE_CHECKING:
    from src.data.adapters.price_service import PriceService

logger = logging.getLogger(__name__)

_PRICE_SAMPLE_SIZE = 10
_MIN_SEED_RETENTION = 0.6


class CryptoResearcher(BasePodAgent):
    """Fetches crypto-relevant data: news sentiment, Polymarket, macro indicators, live prices."""

    def __init__(self, agent_id, pod_id, namespace: PodNamespace, bus: EventBus,
                 polymarket_adapter: Optional[PolymarketAdapter] = None,
                 market_tracker: Optional[MarketTracker] = None,
                 fred_adapter: Optional[FredAdapter] = None,
                 rss_adapter: Optional[RssAdapter] = None,
                 x_adapter: Optional[XAdapter] = None,
                 price_service: Optional[PriceService] = None):
        super().__init__(agent_id, pod_id, namespace, bus)
        self.polymarket_adapter = polymarket_adapter
        self.market_tracker = market_tracker
        self.fred_adapter = fred_adapter
        self.rss_adapter = rss_adapter
        self.x_adapter = x_adapter
        self.price_service = price_service

    async def _review_universe(self, fred_snapshot, poly_signals, news_items, live_quotes) -> list[str]:
        """Use LLM to review and potentially update the crypto universe daily."""
        try:
            from src.core.llm import llm_chat
        except Exception:
            return list(CRYPTO_SEED)

        current = self.recall("universe") or list(CRYPTO_SEED)
        headlines = [n.get("title", n.get("text", ""))[:80] for n in (news_items or [])[:15]]
        movers = [f"{s}: ${q.get('price', 0):.2f} ({q.get('change_pct', 0):+.1f}%)"
                  for s, q in (live_quotes or {}).items() if q.get("change_pct")][:10]

        prompt = (
            f"You are the crypto researcher for a macro hedge fund.\n"
            f"Current universe ({len(current)} symbols): {', '.join(current[:25])}\n"
            f"Seed has {len(CRYPTO_SEED)} crypto pairs.\n\n"
            f"Context:\n- Headlines: {'; '.join(headlines[:8]) if headlines else 'none'}\n"
            f"- Movers: {'; '.join(movers[:6]) if movers else 'none'}\n"
            f"- BTC dominant trend, macro VIX={fred_snapshot.get('VIXCLS', '?')}\n\n"
            f"ADD up to 5 or REMOVE up to 5 symbols. Format: SYMBOL/USD. "
            f"At least {int(_MIN_SEED_RETENTION*100)}% of seed must remain.\n"
            f"JSON: {{\"add\": [], \"remove\": [], \"reasoning\": \"...\"}}"
        )
        try:
            resp = llm_chat([{"role": "user", "content": prompt}], max_tokens=300)
            start, end = resp.find("{"), resp.rfind("}") + 1
            if start >= 0 and end > start:
                parsed = json.loads(resp[start:end])
                add_syms = [s.upper().strip() for s in parsed.get("add", []) if s.strip()][:5]
                rm_syms = [s.upper().strip() for s in parsed.get("remove", []) if s.strip()][:5]
                new_universe = [s for s in current if s not in rm_syms] + add_syms
                seed_kept = len([s for s in CRYPTO_SEED if s in new_universe])
                if seed_kept < len(CRYPTO_SEED) * _MIN_SEED_RETENTION:
                    return current
                if add_syms or rm_syms:
                    await self._bus.publish("agent.activity", AgentMessage(
                        timestamp=datetime.now(timezone.utc), sender=f"{self._pod_id}.researcher",
                        recipient="dashboard", topic="agent.activity",
                        payload={"agent_id": f"{self._pod_id}_researcher", "agent_role": "Researcher",
                                 "pod_id": self._pod_id, "action": "universe_update",
                                 "summary": f"Universe updated: +{len(add_syms)} -{len(rm_syms)} ({', '.join(add_syms + rm_syms)})",
                                 "detail": parsed.get("reasoning", "")[:300]},
                    ), publisher_id=f"{self._pod_id}.researcher")
                return new_universe
        except Exception as e:
            logger.info("[crypto.researcher] Universe review LLM failed: %s", e)
        return current

    async def run_cycle(self, context: dict) -> dict:
        current_universe = self.recall("universe") or list(CRYPTO_SEED)
        self.store("universe", current_universe)

        fred_snapshot = {}
        if self.fred_adapter:
            try:
                fred_snapshot = await self.fred_adapter.fetch_snapshot()
            except Exception as e:
                logger.info("[crypto.researcher] FRED failed: %s", e)
        self.store("fred_snapshot", fred_snapshot)

        poly_signals = []
        if self.polymarket_adapter:
            try:
                raw = await self.polymarket_adapter.fetch_signals([])
                if self.market_tracker:
                    poly_signals = self.market_tracker.update(raw)
                else:
                    poly_signals = [s.model_dump(mode="json") for s in raw]
            except Exception as e:
                logger.info("[crypto.researcher] Polymarket failed: %s", e)
        self.store("polymarket_signals", poly_signals)

        news_items = []
        if self.rss_adapter:
            try:
                news_items = await self.rss_adapter.fetch_news()
            except Exception as e:
                logger.info("[crypto.researcher] RSS failed: %s", e)
        self.store("news_items", [n.model_dump(mode="json") for n in news_items])

        x_feed, x_news = [], []
        if self.x_adapter:
            try:
                x_feed, x_news = await self.x_adapter.fetch_tweets()
            except Exception as e:
                logger.info("[crypto.researcher] News feed failed: %s", e)
        self.store("x_feed", x_feed)
        self.store("x_tweet_count", len(x_feed))

        # Live crypto prices via CoinMarketCap (primary) or Alpha Vantage (fallback)
        live_quotes: dict = {}
        if self.price_service:
            try:
                sample = CRYPTO_SEED[:_PRICE_SAMPLE_SIZE]
                live_quotes = await self.price_service.get_quotes(sample)
                logger.info("[crypto.researcher] Live quotes: %d/%d symbols", len(live_quotes), len(sample))
            except Exception as e:
                logger.info("[crypto.researcher] Live price fetch failed: %s", e)
        self.store("live_quotes", live_quotes)

        news_sents = [getattr(n, "sentiment", 0.0) for n in news_items]
        social_sents = [t.get("sentiment", 0.0) if isinstance(t, dict) else getattr(t, "sentiment", 0.0) for t in x_feed]
        regime = compute_macro_score(fred_snapshot, poly_signals, news_sents, social_sents)
        for key, val in regime.items():
            self.store(key, val)
        self.store("researcher_ok", True)

        logger.info("[crypto.researcher] fred=%.3f poly=%.3f sentiment=%.3f -> macro=%.3f | news=%d x=%d prices=%d",
                    regime["fred_score"], regime["poly_sentiment"], regime["social_score"],
                    regime["macro_score"], len(news_items), len(x_feed), len(live_quotes))

        last_review = self.recall("universe_last_review")
        now = datetime.now(timezone.utc)
        should_review = last_review is None
        if not should_review and last_review:
            try:
                last_dt = datetime.fromisoformat(last_review) if isinstance(last_review, str) else last_review
                should_review = (now - last_dt).total_seconds() > 86400
            except Exception:
                should_review = True
        if should_review:
            news_dicts = [n.model_dump(mode="json") if hasattr(n, "model_dump") else n for n in news_items]
            updated = await self._review_universe(fred_snapshot, poly_signals, news_dicts, live_quotes)
            self.store("universe", updated)
            self.store("universe_last_review", now.isoformat())
            current_universe = updated

        return {"universe": current_universe, "poly_signals": poly_signals}
