from __future__ import annotations
import json
import logging
from datetime import datetime, timezone
from typing import Optional, TYPE_CHECKING
from src.core.bus.event_bus import EventBus
from src.core.config.universes import EQUITIES_SEED
from src.core.models.messages import AgentMessage
from src.core.scoring import compute_macro_score
from src.data.adapters.fred_adapter import FredAdapter
from src.data.adapters.sentiment import score_items, find_position_alerts
from src.data.adapters.polymarket_adapter import PolymarketAdapter
from src.data.adapters.market_tracker import MarketTracker
from src.data.adapters.rss_adapter import RssAdapter
from src.data.adapters.x_adapter import XAdapter
from src.pods.base.agent import BasePodAgent
from src.pods.base.namespace import PodNamespace
from src.data.services.theme_scanner import ThemeScanner

if TYPE_CHECKING:
    from src.data.adapters.price_service import PriceService

logger = logging.getLogger(__name__)

_PRICE_SAMPLE_SIZE = 10
_MIN_SEED_RETENTION = 0.6


class EquitiesResearcher(BasePodAgent):
    """Fetches macro data, Polymarket odds, news, and live prices for equity universe."""

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
        self._last_theme_scan_date: str | None = None

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
        combined = list(dict.fromkeys(list(EQUITIES_SEED) + active))
        return combined

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
            headlines=headlines, poly_signals=poly_signals, fred_snapshot=fred_snapshot,
            existing_discovered=discovered, existing_universe=current_universe,
            month=month, year=year,
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
            try:
                bus = self._ns.get("event_bus")
                if bus:
                    import asyncio
                    asyncio.create_task(bus.publish("agent.activity", {
                        "pod_id": "equities",
                        "role": "researcher",
                        "action": "universe_expanded",
                        "content": f"Theme scanner added {len(themes_added)} tickers: {', '.join(themes_added)}",
                        "timestamp": today,
                    }))
            except Exception:
                pass

        # 4. Save back to namespace
        self._ns.set("discovered_tickers", updated_discovered)
        self._last_theme_scan_date = today
        return updated_discovered

    async def _review_universe(self, fred_snapshot, poly_signals, news_items, live_quotes) -> list[str]:
        """Use LLM to review and potentially update the tradeable universe daily."""
        try:
            from src.core.llm import llm_chat
        except Exception:
            return list(EQUITIES_SEED)

        current = self.recall("universe") or list(EQUITIES_SEED)
        headlines = [n.get("title", n.get("text", ""))[:80] for n in (news_items or [])[:15]]
        movers = [f"{s}: ${q.get('price', 0):.2f} ({q.get('change_pct', 0):+.1f}%)"
                  for s, q in (live_quotes or {}).items() if q.get("change_pct")][:10]
        poly_top = [s.get("question", "")[:60] for s in (poly_signals or [])[:5]]

        prompt = (
            f"You are the equities researcher for a macro hedge fund.\n"
            f"Current universe ({len(current)} symbols): {', '.join(current[:30])}{'...' if len(current) > 30 else ''}\n"
            f"Seed universe has {len(EQUITIES_SEED)} symbols.\n\n"
            f"Today's context:\n"
            f"- Top headlines: {'; '.join(headlines[:8]) if headlines else 'none'}\n"
            f"- Price movers: {'; '.join(movers[:6]) if movers else 'none'}\n"
            f"- Polymarket signals: {'; '.join(poly_top) if poly_top else 'none'}\n"
            f"- FRED macro: VIX={fred_snapshot.get('VIXCLS', '?')}, 10Y={fred_snapshot.get('DGS10', '?')}\n\n"
            f"Review the universe. You may ADD up to 5 symbols or REMOVE up to 5 symbols "
            f"based on current macro conditions and news. At least {int(_MIN_SEED_RETENTION*100)}% of the seed must remain.\n"
            f"Respond with JSON: {{\"add\": [\"SYM1\"], \"remove\": [\"SYM2\"], \"reasoning\": \"...\"}}\n"
            f"If no changes needed, return {{\"add\": [], \"remove\": [], \"reasoning\": \"Universe is appropriate\"}}"
        )

        try:
            resp = llm_chat([{"role": "user", "content": prompt}], max_tokens=300)
            start = resp.find("{")
            end = resp.rfind("}") + 1
            if start >= 0 and end > start:
                parsed = json.loads(resp[start:end])
                add_syms = [s.upper().strip() for s in parsed.get("add", []) if s.strip()][:5]
                rm_syms = [s.upper().strip() for s in parsed.get("remove", []) if s.strip()][:5]
                new_universe = [s for s in current if s not in rm_syms] + add_syms
                # Enforce minimum seed retention
                seed_kept = len([s for s in EQUITIES_SEED if s in new_universe])
                if seed_kept < len(EQUITIES_SEED) * _MIN_SEED_RETENTION:
                    logger.warning("[equities.researcher] Universe review would drop too many seed symbols, skipping")
                    return current
                # Publish universe change activity
                if add_syms or rm_syms:
                    reasoning = parsed.get("reasoning", "")[:300]
                    await self._bus.publish("agent.activity", AgentMessage(
                        timestamp=datetime.now(timezone.utc),
                        sender=f"{self._pod_id}.researcher",
                        recipient="dashboard",
                        topic="agent.activity",
                        payload={
                            "agent_id": f"{self._pod_id}_researcher",
                            "agent_role": "Researcher",
                            "pod_id": self._pod_id,
                            "action": "universe_update",
                            "summary": f"Universe updated: +{len(add_syms)} -{len(rm_syms)} symbols ({', '.join(add_syms + rm_syms)})",
                            "detail": reasoning,
                        },
                    ), publisher_id=f"{self._pod_id}.researcher")
                    logger.info("[equities.researcher] Universe updated: +%s -%s", add_syms, rm_syms)
                return new_universe
        except Exception as e:
            logger.info("[equities.researcher] Universe review LLM failed: %s", e)
        return current

    async def run_cycle(self, context: dict) -> dict:
        current_universe = self.recall("universe") or list(EQUITIES_SEED)
        self.store("universe", current_universe)

        # FRED — use shared ingestion data if available, else fetch directly
        fred_snapshot = self._ns.get("shared_fred_snapshot") or {}
        if not fred_snapshot and self.fred_adapter:
            try:
                fred_snapshot = await self.fred_adapter.fetch_snapshot()
            except Exception as e:
                logger.info("[equities.researcher] FRED failed: %s", e)
        self.store("fred_snapshot", fred_snapshot)

        # Polymarket — use shared data if available, else fetch directly
        shared_poly = self._ns.get("shared_poly_signals")
        poly_signals: list = []
        if shared_poly is not None:
            poly_signals = shared_poly
        elif self.polymarket_adapter:
            try:
                raw = await self.polymarket_adapter.fetch_signals([])
                if self.market_tracker:
                    poly_signals = self.market_tracker.update(raw)
                else:
                    poly_signals = [s.model_dump(mode="json") for s in raw]
            except Exception as e:
                logger.info("[equities.researcher] Polymarket failed: %s", e)
        self.store("polymarket_signals", poly_signals)

        # News — use shared data if available (already dicts), else fetch directly
        shared_news = self._ns.get("shared_news_items")
        news_items: list = []
        if shared_news is not None:
            news_items = shared_news
        elif self.rss_adapter:
            try:
                raw_news = await self.rss_adapter.fetch_news()
                news_items = [n.model_dump(mode="json") if hasattr(n, "model_dump") else n for n in raw_news]
            except Exception as e:
                logger.info("[equities.researcher] RSS failed: %s", e)
        self.store("news_items", news_items)

        # X feed — use shared data if available, else fetch directly
        shared_x = self._ns.get("shared_x_feed")
        x_feed: list = []
        if shared_x is not None:
            x_feed = shared_x
        elif self.x_adapter:
            try:
                x_feed, _ = await self.x_adapter.fetch_tweets()
            except Exception as e:
                logger.info("[equities.researcher] News feed failed: %s", e)
        self.store("x_feed", x_feed)
        self.store("x_tweet_count", len(x_feed))

        # Live price quotes for top equities
        live_quotes: dict = {}
        if self.price_service:
            try:
                sample = EQUITIES_SEED[:_PRICE_SAMPLE_SIZE]
                live_quotes = await self.price_service.get_quotes(sample)
                logger.info("[equities.researcher] Live quotes: %d/%d symbols", len(live_quotes), len(sample))
            except Exception as e:
                logger.info("[equities.researcher] Live price fetch failed: %s", e)
        self.store("live_quotes", live_quotes)

        # LLM-score headlines and predictions for accurate sentiment
        headline_dicts = []
        for n in news_items[:15]:
            title = getattr(n, "title", "") if hasattr(n, "title") else (n.get("title", "") if isinstance(n, dict) else "")
            source = getattr(n, "source", "") if hasattr(n, "source") else (n.get("source", "") if isinstance(n, dict) else "")
            if title:
                headline_dicts.append({"title": title, "source": source, "url": ""})
        for t in x_feed[:15 - len(headline_dicts)]:
            text = t.get("text", t.get("title", "")) if isinstance(t, dict) else getattr(t, "text", "")
            if text:
                headline_dicts.append({"title": text, "source": "news", "url": ""})

        pred_dicts = [{"question": s.get("question", s.get("market", "?")), "probability": s.get("implied_prob", 0.5)} for s in poly_signals[:10]]
        scored_headlines, scored_preds = score_items(headline_dicts, pred_dicts, "equities")

        # Headline alerts: cross-check scored headlines against held positions
        try:
            accountant = self._ns.get("accountant")
            held_symbols = set(accountant._positions.keys()) if accountant else set()
        except Exception:
            held_symbols = set()
        if held_symbols and scored_headlines:
            alert_items = [{**h, "text": h.get("title", "")} for h in scored_headlines]
            alerts = find_position_alerts(alert_items, held_symbols)
            for alert in alerts:
                try:
                    await self._bus.publish(
                        topic=f"pod.{self._pod_id}.gateway",
                        payload={
                            "type": "headline_alert",
                            "action": "headline_alert",
                            "pod_id": self._pod_id,
                            "symbol": alert["matched_symbol"],
                            "headline": (alert.get("text") or alert.get("title") or "")[:200],
                            "sentiment": round(alert.get("sentiment") or 0.0, 2),
                            "relevancy": round(alert.get("relevancy") or 0.0, 2),
                            "detail": f"[ALERT] {alert['matched_symbol']}: {(alert.get('text') or alert.get('title') or '')[:150]}",
                            "summary": f"Headline alert: {alert['matched_symbol']}",
                        }
                    )
                except Exception as e:
                    logger.debug("[%s] headline alert publish error: %s", self._pod_id, e)

        news_sents = [h.get("sentiment", 0.0) for h in scored_headlines]
        social_sents = []
        poly_sents = [p.get("sentiment", 0.0) for p in scored_preds]
        poly_override = sum(poly_sents) / len(poly_sents) if poly_sents else None

        source_weights = self.recall("source_weights")
        regime = compute_macro_score(
            fred_snapshot, poly_signals, news_sents, social_sents,
            poly_sentiment_override=poly_override,
            source_weights=source_weights,
        )
        for key, val in regime.items():
            self.store(key, val)
        self.store("researcher_ok", True)

        logger.info("[equities.researcher] fred=%.3f poly=%.3f sentiment=%.3f -> macro=%.3f | news=%d x=%d prices=%d",
                    regime["fred_score"], regime["poly_sentiment"], regime["social_score"],
                    regime["macro_score"], len(news_items), len(x_feed), len(live_quotes))

        now = datetime.now(timezone.utc)

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
            gateway = self._ns.get("gateway")
            if gateway:
                gateway.set_universe(universe)
            current_universe = universe

        try:
            from src.data.adapters.web_search import WebSearchAdapter
            if not hasattr(self, "_web_searcher"):
                self._web_searcher = WebSearchAdapter()
            self._web_searcher.reset_cycle()

            # Deep-dive: fetch article content for high-relevancy scored headlines
            deep_dives = []
            candidates = [
                h for h in scored_headlines
                if h.get("relevancy", 0.0) >= 0.7 and h.get("impact", 0.0) >= 0.5
            ]
            for h in candidates[:2]:  # cap at 2, keep 1 search credit for macro
                title = h.get("title", "")
                if not title:
                    continue
                results = await self._web_searcher.search(
                    f"{title} stock market analysis {now.strftime('%B %Y')}", max_results=3
                )
                if results:
                    top = results[0]
                    content = await self._web_searcher.fetch_page(top["url"]) if top.get("url") else ""
                    deep_dives.append({
                        "title": title,
                        "url": top.get("url", ""),
                        "snippet": top.get("snippet", ""),
                        "content": content,
                        "sentiment": h.get("sentiment", 0.0),
                        "relevancy": h.get("relevancy", 0.0),
                        "impact": h.get("impact", 0.0),
                    })
            if deep_dives:
                self._ns.set("headline_deep_dives", deep_dives)
                logger.info("[equities.researcher] %d headline deep-dives fetched", len(deep_dives))

            # Macro outlook search
            macro_outlook = self._ns.get("features", {}).get("macro_outlook", "") if self._ns.get("features") else ""
            if macro_outlook:
                results = await self._web_searcher.search(f"financial markets {macro_outlook} equities outlook {now.strftime('%B %Y')}")
                self._ns.set("web_search_results", results)
        except Exception as e:
            logger.debug("[equities.researcher] Web search skipped: %s", e)

        try:
            from src.data.adapters.events_calendar import EventsCalendarAdapter
            if not hasattr(self, "_events_calendar"):
                self._events_calendar = EventsCalendarAdapter()
            events = await self._events_calendar.fetch_upcoming_events(current_universe)
            self._ns.set("upcoming_events", events)
        except Exception as e:
            logger.debug("[equities.researcher] Events calendar skipped: %s", e)

        return {"universe": current_universe, "poly_signals": poly_signals}
