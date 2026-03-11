from __future__ import annotations
import json
import logging
from datetime import datetime, timezone
import uuid

from src.core.models.enums import Side, OrderType
from src.core.models.execution import Order
from src.core.llm import has_llm_key, llm_chat, extract_json
from src.pods.base.agent import BasePodAgent

logger = logging.getLogger(__name__)

_FX_SYSTEM = """You are an FX portfolio manager at a macro hedge fund.
You receive real macro data, prediction market odds, and news headlines every cycle.
Your job is to synthesize ALL of this information into disciplined FX trading decisions.

Decision framework:
1. RATE DIFFERENTIALS: Fed funds rate, 10Y yields, 2Y yields drive currency flows.
   - Higher rates attract capital → currency strengthens.
   - Rate cut expectations → currency weakens.
2. USD STRENGTH: DXY / trade-weighted USD index.
   - Strong USD pressures EM and commodity currencies.
   - Weak USD benefits non-USD assets.
3. PREDICTION MARKETS: Polymarket odds on rate cuts, elections, geopolitics.
   - Rate cut probability directly impacts FX carry.
   - Political/geopolitical events can cause rapid FX moves.
4. CENTRAL BANK DIVERGENCE: Compare Fed vs ECB/BoJ/BoE policy.
5. CARRY TRADES: High-yield vs low-yield currency pairs.

Implementation uses currency/country ETFs: UUP, UDN, FXE, FXY, FXB, EWJ, EWG, etc.

Rules:
- HOLD is the right call most of the time. FX moves slowly unless there's a catalyst.
- Max 3 trades per cycle. Reasoning must cite specific data points.

ARTICLE DEEP-DIVE:
Headlines include article URLs. If a headline is particularly relevant and you need the
full article to make a decision, include "read_articles": ["url1", "url2"] (max 3) in your
JSON. You will then receive the article text and make a final decision.
Only request articles when the headline suggests a material catalyst you need detail on.

Output JSON: {"trades": [{"action": "BUY"|"SELL", "symbol": "TICKER", "qty": N, "reasoning": "..."}], "read_articles": ["url1"]}
Omit read_articles if you don't need to read any articles."""


class FXPMAgent(BasePodAgent):
    """LLM-powered portfolio manager for FX. Falls back to rule-based HOLD."""

    def __init__(
        self,
        agent_id: str,
        pod_id: str,
        namespace,
        bus,
        session_logger=None,
    ):
        super().__init__(agent_id=agent_id, pod_id=pod_id, namespace=namespace, bus=bus)
        self._session_logger = session_logger

    async def run_cycle(self, context: dict) -> dict:
        if context.get("risk_revision"):
            return {"order": context.get("order")}

        features = context.get("features") or self.recall("features", {})
        if not features:
            return {}

        if has_llm_key():
            return await self._llm_decision(features)
        return self._rule_based_decision(features)

    async def _llm_decision(self, features: dict) -> dict:
        positions = self.recall("current_positions_summary", "none")

        sections = []
        sections.append("## Macro Indicators (FRED)")
        fred = features.get("fred_indicators", {})
        if fred:
            for k, v in fred.items():
                if v is not None:
                    sections.append(f"  {k}: {v}")
        sections.append(f"  Macro outlook: {features.get('macro_outlook', 'unknown')}")

        sections.append("\n## Prediction Market Odds (Polymarket)")
        poly = features.get("polymarket_predictions", [])
        if poly:
            for p in poly:
                sections.append(f"  - {p['question']} → {p['probability']*100:.0f}% (vol: ${p['volume_24h']:,.0f})")
        else:
            sections.append("  No active predictions available")

        sections.append("\n## News Headlines")
        headlines = features.get("news_headlines", [])
        if headlines:
            for h in headlines[:15]:
                line = f"  - [{h.get('source','')}] {h.get('title','')}"
                if h.get("url"):
                    line += f"  ({h['url']})"
                sections.append(line)
        else:
            sections.append("  No headlines available")

        sections.append(f"\n## Current Positions\n  {positions}")

        user_content = "\n".join(sections)
        user_content += '\n\nBased on ALL the above data, propose 0-3 FX ETF trades or HOLD.\nOutput JSON: {"trades": [...], "read_articles": ["url1"]} (omit read_articles if not needed)'

        try:
            raw = llm_chat(
                [
                    {"role": "system", "content": _FX_SYSTEM},
                    {"role": "user", "content": user_content},
                ],
                max_tokens=800,
            )
            decision = extract_json(raw)

            if self._session_logger:
                self._session_logger.log_reasoning(f"pm:{self._pod_id}", "prompt", user_content)
                self._session_logger.log_reasoning(f"pm:{self._pod_id}", "response", raw or "")

            read_urls = decision.get("read_articles", [])
            if read_urls and isinstance(read_urls, list):
                decision, raw_second = await self._read_articles_and_decide(
                    read_urls, user_content, _FX_SYSTEM, decision
                )
                response_text = raw_second or raw
            else:
                response_text = raw

            parsed_trades = decision.get("trades", [])
            if isinstance(parsed_trades, dict):
                parsed_trades = [parsed_trades]
            action_parts = []
            for t in parsed_trades:
                action_parts.append(f"{t.get('action','')} {t.get('qty',0)} {t.get('symbol','')}")
            action_summary = ", ".join(action_parts) if action_parts else "holding"
            self.store("last_pm_decision", {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "trades": parsed_trades[:10],
                "reasoning": (response_text or "")[:500],
                "action_summary": action_summary[:200],
            })

            trades = parsed_trades
            if not trades:
                return {}

            orders = []
            for t in trades[:3]:
                action = str(t.get("action", "HOLD")).upper()
                if action == "HOLD":
                    continue
                symbol = str(t.get("symbol", "UUP")).strip()
                qty = float(t.get("qty", 1))
                if qty <= 0:
                    continue
                side = Side.BUY if action == "BUY" else Side.SELL
                reasoning = t.get("reasoning", "")
                order = Order(
                    id=uuid.uuid4(), pod_id=self._pod_id, symbol=symbol,
                    side=side, order_type=OrderType.MARKET, quantity=qty,
                    limit_price=None, timestamp=datetime.now(timezone.utc),
                    strategy_tag=f"llm_fx_{action.lower()}",
                )
                orders.append(order)
                logger.info("[fx.pm] LLM: %s %s %.0f (%s)", action, symbol, qty, reasoning)

            if not orders:
                return {}
            first, rest = orders[0], orders[1:]
            if rest:
                self.store("pm_additional_orders", [o.model_dump(mode="json") for o in rest])
            return {"order": first}
        except Exception as e:
            logger.warning("[fx.pm] LLM failed, falling back: %s", e)
            return self._rule_based_decision(features)

    async def _read_articles_and_decide(
        self, urls: list[str], base_prompt: str, system: str, first_decision: dict
    ) -> tuple[dict, str | None]:
        from src.data.adapters.article_fetcher import ArticleFetcher

        if not hasattr(self, "_article_fetcher"):
            self._article_fetcher = ArticleFetcher()

        articles = await self._article_fetcher.fetch_articles(urls[:3])
        if not articles:
            logger.info("[fx.pm] No articles fetched, using first decision")
            return (first_decision, None)

        article_section = "\n\n## Article Deep-Dives (requested by you)\n"
        for url, text in articles.items():
            article_section += f"\n### Source: {url}\n{text}\n"

        enriched = base_prompt + article_section
        enriched += '\n\nYou have read the articles. Make your FINAL trading decision.\nOutput JSON only: {"trades": [{"action": "BUY|SELL", "symbol": "TICKER", "qty": N, "reasoning": "..."}]}'

        try:
            raw = llm_chat(
                [{"role": "system", "content": system}, {"role": "user", "content": enriched}],
                max_tokens=800,
            )
            logger.info("[fx.pm] Article deep-dive complete (%d articles read)", len(articles))
            if self._session_logger:
                self._session_logger.log_reasoning(f"pm:{self._pod_id}", "prompt", enriched)
                self._session_logger.log_reasoning(f"pm:{self._pod_id}", "response", raw or "")
            return (extract_json(raw), raw)
        except Exception as e:
            logger.warning("[fx.pm] Article deep-dive LLM failed: %s", e)
            return (first_decision, None)

    def _rule_based_decision(self, features: dict) -> dict:
        logger.debug("[fx.pm] Rule-based: HOLD (no LLM key)")
        self.store("last_pm_decision", {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "trades": [],
            "reasoning": "Rule-based: no LLM available",
            "action_summary": "holding (rule-based)",
        })
        return {}
