from __future__ import annotations
import logging
from src.core.regime import classify_regime
from src.data.adapters.fred_adapter import FredAdapter
from src.data.adapters.sentiment import score_items
from src.pods.base.agent import BasePodAgent

logger = logging.getLogger(__name__)

_MAX_HEADLINES = 15
_MAX_POLY = 10


class CryptoSignalAgent(BasePodAgent):
    """Transforms research data into crypto-specific features.

    Passes through actual data so the LLM can reason over real content.
    """

    async def run_cycle(self, context: dict) -> dict:
        fred = self.recall("fred_snapshot", {})
        poly = self.recall("polymarket_signals", [])
        news = self.recall("news_items", [])
        x_feed = self.recall("x_feed", [])
        live_quotes = self.recall("live_quotes", {})

        fed_rate = fred.get("DFF") or fred.get("FEDFUNDS")
        m2 = fred.get("M2SL")
        dxy = fred.get("DTWEXBGS")
        vix = fred.get("VIXCLS")
        yield_curve = fred.get("T10Y2Y")
        credit_spread = fred.get("BAMLH0A0HYM2")

        liquidity_outlook = "neutral"
        if fed_rate is not None:
            if fed_rate < 3.0:
                liquidity_outlook = "accommodative"
            elif fed_rate > 5.0:
                liquidity_outlook = "tight"

        top_poly = sorted(poly, key=lambda s: s.get("volume_24h", 0), reverse=True)[:_MAX_POLY]
        poly_summary = [
            {
                "question": p.get("question", p.get("market", "?")),
                "probability": round(p.get("implied_prob", 0.5), 3),
                "volume_24h": p.get("volume_24h", 0),
            }
            for p in top_poly
        ]

        headlines = []
        for item in news[:_MAX_HEADLINES]:
            title = item.get("title", "") if isinstance(item, dict) else getattr(item, "title", "")
            source = item.get("source", "") if isinstance(item, dict) else getattr(item, "source", "")
            url = item.get("url", "") if isinstance(item, dict) else getattr(item, "url", "")
            if title:
                headlines.append({"title": title, "source": source, "url": url})
        for tweet in x_feed[:_MAX_HEADLINES - len(headlines)]:
            text = tweet.get("text", tweet.get("title", "")) if isinstance(tweet, dict) else getattr(tweet, "text", "")
            username = tweet.get("username", "") if isinstance(tweet, dict) else getattr(tweet, "username", "")
            url = tweet.get("url", "") if isinstance(tweet, dict) else getattr(tweet, "url", "")
            if text:
                headlines.append({"title": text, "source": username or "news", "url": url})

        headlines, poly_summary = score_items(headlines, poly_summary, "crypto")

        price_snapshot = []
        for sym, q in live_quotes.items():
            if isinstance(q, dict):
                price_snapshot.append({
                    "symbol": q.get("symbol", sym),
                    "price": q.get("price", 0),
                    "change_pct": q.get("change_pct", q.get("change_24h", 0)),
                    "source": q.get("source", ""),
                })

        features = {
            "liquidity_outlook": liquidity_outlook,
            "fred_indicators": {
                "fed_funds_rate": fed_rate,
                "m2_money_supply": m2,
                "usd_index_dxy": dxy,
                "vix": vix,
                "yield_curve_10y2y": yield_curve,
                "credit_spread": credit_spread,
            },
            "global_rate_table": FredAdapter.build_global_rate_table(fred),
            "polymarket_predictions": poly_summary,
            "news_headlines": headlines,
            "live_prices": price_snapshot,
            "data_counts": {
                "fred_series": len(fred),
                "polymarket_markets": len(poly),
                "news_articles": len(news),
                "news_headlines": len(x_feed),
                "live_prices": len(price_snapshot),
            },
        }

        # Classify market regime for risk scaling
        regime = classify_regime(
            vix=float(vix) if vix is not None else None,
            yield_curve=float(yield_curve) if yield_curve is not None else None,
            credit_spread=float(credit_spread) if credit_spread is not None else None,
        )
        features["regime"] = {
            "name": regime.regime,
            "label": regime.label,
            "scale": regime.scale,
            "description": regime.description,
        }
        self._ns.set("market_regime", features["regime"])

        upcoming_events = self._ns.get("upcoming_events") or []
        if upcoming_events:
            features["upcoming_events"] = upcoming_events

        self.store("features", features)
        logger.debug("[crypto.signal] features assembled: %d FRED, %d poly, %d headlines, regime=%s",
                     len(fred), len(poly_summary), len(headlines), regime.regime)
        return {"features": features}
