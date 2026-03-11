from __future__ import annotations
import json
import logging
from datetime import datetime, timezone
import uuid

from src.core.llm import has_llm_key, llm_chat, extract_json
from src.core.models.enums import Side, OrderType
from src.core.models.execution import Order
from src.core.models.messages import AgentMessage
from src.pods.base.agent import BasePodAgent

logger = logging.getLogger(__name__)

_COMMODITIES_SYSTEM = """You are a commodities portfolio manager at a macro hedge fund.
You receive real macro data, prediction market odds, and news headlines every cycle.
Your job is to synthesize ALL of this information into disciplined commodity trading decisions.

Decision framework:
1. INFLATION REGIME: CPI, 5Y and 10Y breakeven inflation rates.
   - Rising inflation expectations → bullish commodities (gold, oil, agriculture).
   - Falling inflation → bearish commodities, favor cash/bonds.
2. REAL RATES: 10Y yield minus breakeven inflation.
   - Negative real rates → very bullish gold/precious metals.
   - Rising real rates → headwind for gold, may still favor oil/ags.
3. USD STRENGTH: DXY inversely correlates with most commodities.
   - Commodities are priced in USD; weak dollar = higher commodity prices.
4. ENERGY: WTI crude, natural gas — supply/demand, OPEC, geopolitics.
5. PREDICTION MARKETS: Polymarket odds on conflicts, sanctions, trade policy.
   - Geopolitical risk drives energy and gold.
6. NEWS: Supply disruptions, weather events, trade wars.

Implementation uses commodity ETFs: GLD, SLV, USO, UNG, DBA, CORN, WEAT, GDX, XME, etc.

Rules:
- Commodities are cyclical. Position with the macro trend.
- HOLD is appropriate when signals are mixed.
- Max 3 trades per cycle. Reasoning must cite specific data points.

ARTICLE DEEP-DIVE:
Headlines include article URLs. If a headline is particularly relevant and you need the
full article to make a decision, include "read_articles": ["url1", "url2"] (max 3) in your
JSON. You will then receive the article text and make a final decision.
Only request articles when the headline suggests a material catalyst you need detail on.

Output JSON: {"trades": [{"action": "BUY"|"SELL", "symbol": "TICKER", "qty": N, "reasoning": "..."}], "read_articles": ["url1"]}
Omit read_articles if you don't need to read any articles.

POSITION SIZING:
You receive your pod's NAV, cash, leverage, and position limits every cycle.
Size your trades intentionally:
- Consider the conviction level of your thesis (higher conviction = larger size)
- Never exceed the position limit notional shown
- Account for existing exposure when adding to positions
- Scale size down in high-volatility / uncertain regimes
- The Risk agent will reject orders that breach hard limits
Output qty as a specific number of shares/units, not a percentage."""


class CommoditiesPMAgent(BasePodAgent):
    """LLM-powered PM for commodities. Focuses on inflation, supply/demand, DXY."""

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
        if context.get("risk_revision") and context.get("order"):
            return {"order": context["order"]}

        features = context.get("features") or self.recall("features", {})
        if not features:
            return {}

        sizing = context.get("sizing_context", {})

        if has_llm_key():
            return await self._llm_decision(features, sizing)
        return self._rule_based_decision(features)

    async def _read_articles_and_decide(
        self, urls: list[str], base_prompt: str, system: str, first_decision: dict
    ) -> tuple[dict, str | None]:
        from src.data.adapters.article_fetcher import ArticleFetcher

        if not hasattr(self, "_article_fetcher"):
            self._article_fetcher = ArticleFetcher()

        articles = await self._article_fetcher.fetch_articles(urls[:3])
        if not articles:
            logger.info("[commodities.pm] No articles fetched, using first decision")
            return (first_decision, None)

        try:
            act_msg = AgentMessage(
                timestamp=datetime.now(timezone.utc),
                sender=self._agent_id,
                recipient="dashboard",
                topic="agent.activity",
                payload={
                    "agent_id": self._agent_id,
                    "agent_role": "PM",
                    "pod_id": self._pod_id,
                    "action": "article_deep_dive",
                    "summary": f"Read {len(articles)} article(s)",
                    "detail": "\n".join(f"[{url}]: {text[:200]}..." for url, text in articles.items()),
                    "urls": list(articles.keys())[:3],
                },
            )
            await self._bus.publish("agent.activity", act_msg, publisher_id=self._agent_id)
        except Exception:
            pass

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
            logger.info("[commodities.pm] Article deep-dive complete (%d articles read)", len(articles))
            if self._session_logger:
                self._session_logger.log_reasoning(f"pm:{self._pod_id}", "prompt", enriched)
                self._session_logger.log_reasoning(f"pm:{self._pod_id}", "response", raw or "")
            return (extract_json(raw), raw)
        except Exception as e:
            logger.warning("[commodities.pm] Article deep-dive LLM failed: %s", e)
            return (first_decision, None)

    def _rule_based_decision(self, features: dict) -> dict:
        logger.debug("[commodities.pm] Rule-based: HOLD (no LLM key)")
        self.store("last_pm_decision", {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "trades": [],
            "reasoning": "Rule-based: no LLM available",
            "action_summary": "holding (rule-based)",
        })
        return {}

    async def _llm_decision(self, features: dict, sizing_context: dict | None = None) -> dict:
        positions = self.recall("current_positions_summary", "none")
        universe = self.recall("universe", [])
        sizing = sizing_context or {}

        sections = []
        if sizing:
            sections.append("\n## Position Sizing Context")
            sections.append(f"  Pod NAV: ${sizing.get('pod_nav', 0):,.2f}")
            sections.append(f"  Available cash: ${sizing.get('available_cash', 0):,.2f}")
            sections.append(f"  Current leverage: {sizing.get('current_leverage', 0):.2f}x")
            sections.append(f"  Max leverage: {sizing.get('max_leverage', 2.0):.1f}x")
            sections.append(f"  Max position size: ${sizing.get('position_limit_notional', 0):,.2f} (10% of NAV)")
            for p in sizing.get("positions_summary", []):
                sections.append(f"  Position: {p['symbol']} qty={p['qty']:.1f} notional=${p['notional']:,.0f} pnl=${p['unrealized_pnl']:,.2f}")

        sections.append("\n## Macro Indicators (FRED)")
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
        sections.append(f"\n## Universe (commodity ETFs)\n  {universe[:20]}")

        user_content = "\n".join(sections)
        user_content += '\n\nBased on ALL the above data, propose 0-3 commodity ETF trades or HOLD.\nOutput JSON: {"trades": [...], "read_articles": ["url1"]} (omit read_articles if not needed)'

        try:
            raw = llm_chat(
                [
                    {"role": "system", "content": _COMMODITIES_SYSTEM},
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
                    read_urls, user_content, _COMMODITIES_SYSTEM, decision
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
                symbol = str(t.get("symbol", "GLD")).strip()
                qty = float(t.get("qty", 1))
                if qty <= 0:
                    continue
                side = Side.BUY if action == "BUY" else Side.SELL
                reasoning = t.get("reasoning", "")
                order = Order(
                    id=uuid.uuid4(), pod_id=self._pod_id, symbol=symbol,
                    side=side, order_type=OrderType.MARKET, quantity=qty,
                    limit_price=None, timestamp=datetime.now(timezone.utc),
                    strategy_tag=f"llm_commodities_{action.lower()}",
                )
                orders.append(order)
                logger.info("[commodities.pm] LLM: %s %s %.0f (%s)", action, symbol, qty, reasoning)

            if not orders:
                return {}
            first, rest = orders[0], orders[1:]
            if rest:
                self.store("pm_additional_orders", [o.model_dump(mode="json") for o in rest])
            return {"order": first}
        except Exception as e:
            logger.warning("[commodities.pm] LLM failed, falling back: %s", e)
            return self._rule_based_decision(features)
