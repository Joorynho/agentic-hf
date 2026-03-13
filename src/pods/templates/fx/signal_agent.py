from __future__ import annotations
import logging
from src.data.adapters.fred_adapter import FredAdapter
from src.pods.base.agent import BasePodAgent

logger = logging.getLogger(__name__)

_MAX_HEADLINES = 15
_MAX_POLY = 10


class FXSignalAgent(BasePodAgent):
    """Transforms raw research data into FX-focused features for the PM.

    Passes through actual data so the LLM can reason over real content.
    """

    async def run_cycle(self, context: dict) -> dict:
        fred = self.recall("fred_snapshot", {})
        poly = self.recall("polymarket_signals", [])
        news = self.recall("news_items", [])
        x_feed = self.recall("x_feed", [])
        live_quotes = self.recall("live_quotes", {})

        fed_rate = fred.get("FEDFUNDS")
        dgs10 = fred.get("DGS10")
        dgs2 = fred.get("DGS2")
        yield_curve = fred.get("T10Y2Y")
        vix = fred.get("VIXCLS")
        dxy = fred.get("DTWEXBGS")
        m2 = fred.get("M2SL")
        cpi = fred.get("CPIAUCSL")

        macro_outlook = "neutral"
        if fed_rate is not None and yield_curve is not None:
            if fed_rate > 4.0 and yield_curve > 0:
                macro_outlook = "usd_bullish"
            elif fed_rate < 3.0 or yield_curve < -0.3:
                macro_outlook = "usd_bearish"

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
            handle = tweet.get("handle", "") if isinstance(tweet, dict) else getattr(tweet, "handle", "")
            url = tweet.get("url", "") if isinstance(tweet, dict) else getattr(tweet, "url", "")
            if text:
                headlines.append({"title": text, "source": f"@{handle}" if handle else "news", "url": url})

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
            "macro_outlook": macro_outlook,
            "fred_indicators": {
                "fed_funds_rate": fed_rate,
                "treasury_10y": dgs10,
                "treasury_2y": dgs2,
                "yield_curve_10y2y": yield_curve,
                "vix": vix,
                "usd_index_dxy": dxy,
                "m2_money_supply": m2,
                "cpi": cpi,
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

        self.store("features", features)
        logger.debug("[fx.signal] features assembled: %d FRED, %d poly, %d headlines",
                     len(fred), len(poly_summary), len(headlines))
        return {"features": features}
