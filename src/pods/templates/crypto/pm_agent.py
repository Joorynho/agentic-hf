from __future__ import annotations
import json
import logging
import math
from datetime import datetime, timezone
import uuid

from src.core.llm import has_llm_key, llm_chat, extract_json
from src.core.models.enums import Side, OrderType
from src.core.models.execution import Order, TradeProposal
from src.core.models.messages import AgentMessage
from src.pods.base.agent import BasePodAgent

logger = logging.getLogger(__name__)

PM_MAX_SINGLE_TRADE_PCT = 0.15  # tighter for crypto due to higher vol
PM_MAX_CYCLE_ALLOCATION_PCT = 0.30

_CRYPTO_SYSTEM = """You are a senior crypto portfolio manager at an institutional macro hedge fund.
You receive real macro data, prediction market odds, and news headlines every cycle.
Your job is to produce institutional-quality crypto trade ideas with deep, differentiated reasoning.

ANALYTICAL FRAMEWORK:
1. LIQUIDITY REGIME: M2 money supply and fed funds rate are the primary drivers.
   - Expanding M2 + low rates = bullish (more liquidity seeking yield).
   - Tightening + high rates = bearish (capital to safer assets).
   - Focus on the DIRECTION of change, not absolute levels.
2. USD STRENGTH: DXY inversely correlates with crypto.
   - Weak USD = tailwind. Strong USD = headwind.
3. RISK APPETITE: VIX and credit spreads signal risk-on/risk-off.
   - Low VIX + tight spreads = crypto benefits.
   - High VIX + wide spreads = crypto sells off.
4. PREDICTION MARKETS: Polymarket odds on regulation, ETF approvals, rate cuts.
5. BTC DOMINANCE: Rising = favor BTC. Falling = look at alts.

NEWS — THINK DEEPER, NOT SURFACE-LEVEL:
- Do NOT chase pumps. If a coin already moved 10%+ on news, the easy money is gone.
- Instead: WHY did it pump? What narrative/catalyst drove it? Which OTHER tokens in the
  same ecosystem, L1, or sector haven't moved yet but benefit from the same dynamic?
- Example: "SOL rallied on new DeFi TVL inflows" → look at SOL ecosystem tokens
  (JUP, PYTH, ORCA) that haven't repriced yet for the same liquidity wave.
- Regulatory news: think about which tokens are MOST/LEAST exposed. A favorable SEC
  ruling on one token has implications for the entire sector.
- Do NOT restate headlines. Explain what the headline IMPLIES for crypto broadly.

REASONING STANDARD — every trade MUST include:
- THESIS: The macro/crypto-specific setup and why it favors this token now
- EDGE: What is the market not pricing? Why hasn't this moved yet?
- SECOND-ORDER: What's the non-obvious connection? (ecosystem, L1 vs L2, narrative rotation)
- RISK: What would invalidate this thesis? (regulatory, hack, macro reversal)
- TIMING: Why enter now? Is there a catalyst window?

ANTI-PATTERNS (will get your trades rejected):
- "BTC is pumping so buy BTC" — chasing is not investing
- Restating a headline as reasoning — go deeper
- No edge: if you can't say what the market is missing, don't trade
- Ignoring macro regime when it contradicts your crypto thesis

Use XXX/USD format (BTC/USD, ETH/USD, SOL/USD, etc.).

Rules:
- HOLD is appropriate when macro is unclear or signals conflict.
- Max 3 trades per cycle. Size conservatively given crypto volatility.

ARTICLE DEEP-DIVE:
If a headline suggests a material catalyst worth investigating, include "read_articles": ["url1", "url2"]
(max 3). You will receive the full article text.

Output JSON:
{"trades": [{"action": "BUY"|"SELL", "symbol": "XXX/USD", "qty": N, "reasoning": "THESIS: ... | EDGE: ... | RISK: ..."}], "read_articles": ["url1"]}
Omit read_articles if not needed.

POSITION SIZING:
- Standard conviction: 3-8% of NAV
- High conviction (with full THESIS/EDGE/RISK): up to 15% of NAV
- Hard cap: 15% of NAV per position, 30% of cash per cycle (tighter due to crypto vol)
- Scale down in high-vol regimes. The Risk agent enforces hard limits.
Output qty as a specific number of units (can be fractional), not a percentage."""


class CryptoPMAgent(BasePodAgent):
    """LLM-powered PM for crypto. Focuses on liquidity, sentiment, Polymarket, DXY."""

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
        self._decision_history: list[dict] = []

    async def run_cycle(self, context: dict) -> dict:
        if context.get("risk_revision") and context.get("order"):
            return await self._evaluate_risk_revision(context)

        features = context.get("features") or self.recall("features", {})
        if not features:
            return {}

        sizing = context.get("sizing_context", {})

        if has_llm_key():
            return await self._llm_decision(features, sizing)
        return self._rule_based_decision(features)

    async def _evaluate_risk_revision(self, context: dict) -> dict:
        """Evaluate whether a Risk-revised order is still worth trading."""
        revised_order = context.get("order")
        if not revised_order:
            return {}
        risk_reason = context.get("risk_reason", "unknown")
        original_qty = context.get("original_qty", revised_order.quantity)

        if not has_llm_key():
            await self._broadcast_revision_decision(revised_order, True, "Auto-accepted (no LLM)", original_qty)
            return {"order": revised_order}

        try:
            prompt = (
                f"Risk reduced your proposed {revised_order.side.value} {revised_order.symbol} "
                f"from {original_qty} to {revised_order.quantity} units.\n"
                f"Reason: {risk_reason}\n\n"
                f"Is this reduced size still a worthwhile trade? Consider:\n"
                f"- Does the thesis still hold at this smaller size?\n"
                f"- Is the position too small to matter?\n"
                f"- Would you rather skip and wait for a better entry?\n\n"
                f'Reply JSON: {{"accept": true/false, "reasoning": "brief explanation"}}'
            )
            raw = llm_chat(
                [{"role": "system", "content": "You are a crypto PM evaluating a risk-adjusted trade size. Be concise."},
                 {"role": "user", "content": prompt}],
                max_tokens=150,
            )
            decision = extract_json(raw)
            accept = decision.get("accept", True)
            reasoning = decision.get("reasoning", "")

            if self._session_logger:
                self._session_logger.log_reasoning(
                    f"pm:{self._pod_id}", "risk_revision_eval",
                    f"Risk: {risk_reason} | PM: {'ACCEPT' if accept else 'REJECT'} — {reasoning}",
                )

            await self._broadcast_revision_decision(revised_order, accept, reasoning, original_qty)

            if accept:
                logger.info("[crypto.pm] Accepted revision: %s %s %s (%s)", revised_order.side.value, revised_order.symbol, revised_order.quantity, reasoning)
                return {"order": revised_order}
            else:
                logger.info("[crypto.pm] Rejected revision: %s %s (%s)", revised_order.side.value, revised_order.symbol, reasoning)
                return {}
        except Exception as e:
            logger.warning("[crypto.pm] Revision eval failed, accepting: %s", e)
            await self._broadcast_revision_decision(revised_order, True, f"Auto-accepted (eval error: {e})", original_qty)
            return {"order": revised_order}

    async def _broadcast_revision_decision(self, order, accepted: bool, reasoning: str, original_qty: float) -> None:
        try:
            action = "pm_accept_revision" if accepted else "pm_reject_revision"
            summary = (
                f"{'Accepted' if accepted else 'Rejected'} revision: {order.side.value} {order.symbol} "
                f"{original_qty} -> {order.quantity}. {reasoning}"
            )
            msg = AgentMessage(
                timestamp=datetime.now(timezone.utc),
                sender=self._agent_id,
                recipient="dashboard",
                topic="agent.activity",
                payload={
                    "agent_id": self._agent_id,
                    "agent_role": "PM",
                    "pod_id": self._pod_id,
                    "action": action,
                    "summary": summary[:500],
                    "detail": reasoning,
                },
            )
            await self._bus.publish("agent.activity", msg, publisher_id=self._agent_id)
        except Exception:
            pass

    async def _read_articles_and_decide(
        self, urls: list[str], base_prompt: str, system: str, first_decision: dict
    ) -> tuple[dict, str | None]:
        from src.data.adapters.article_fetcher import ArticleFetcher

        if not hasattr(self, "_article_fetcher"):
            self._article_fetcher = ArticleFetcher()

        articles = await self._article_fetcher.fetch_articles(urls[:3])
        if not articles:
            logger.info("[crypto.pm] No articles fetched, using first decision")
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
                    "detail": "\n".join(f"[{url}]: {text[:500]}..." for url, text in articles.items()),
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
        enriched += '\n\nYou have read the articles. Make your FINAL trading decision.\nOutput JSON only: {"trades": [{"action": "BUY|SELL", "symbol": "XXX/USD", "qty": N, "reasoning": "..."}]}'

        try:
            raw = llm_chat(
                [{"role": "system", "content": system}, {"role": "user", "content": enriched}],
                max_tokens=1200,
            )
            logger.info("[crypto.pm] Article deep-dive complete (%d articles read)", len(articles))
            if self._session_logger:
                self._session_logger.log_reasoning(f"pm:{self._pod_id}", "prompt", enriched)
                self._session_logger.log_reasoning(f"pm:{self._pod_id}", "response", raw or "")
            return (extract_json(raw), raw)
        except Exception as e:
            logger.warning("[crypto.pm] Article deep-dive LLM failed: %s", e)
            return (first_decision, None)

    def _apply_sizing_discipline(
        self, qty: float, symbol: str, side: Side,
        sizing: dict, cycle_notional_used: float,
    ) -> tuple[float, str]:
        """Clamp trade qty to PM-level budget limits before sending to Risk."""
        nav = sizing.get("pod_nav", 0)
        cash = sizing.get("available_cash", 0)
        if nav <= 0:
            return (qty, "")

        est_price = self._estimate_price(symbol)
        if est_price <= 0:
            return (qty, "")
        proposed_notional = qty * est_price

        notes = []

        max_single_notional = nav * PM_MAX_SINGLE_TRADE_PCT
        if proposed_notional > max_single_notional:
            clamped_qty = max_single_notional / est_price
            notes.append(f"capped {qty}->{clamped_qty:.6f} (max {PM_MAX_SINGLE_TRADE_PCT*100:.0f}% NAV)")
            qty = clamped_qty

        if side == Side.BUY:
            max_cycle_notional = cash * PM_MAX_CYCLE_ALLOCATION_PCT
            remaining = max_cycle_notional - cycle_notional_used
            if remaining <= 0:
                return (0, "cycle budget exhausted")
            trade_notional = qty * est_price
            if trade_notional > remaining:
                clamped_qty = remaining / est_price
                notes.append(f"capped to cycle budget ({PM_MAX_CYCLE_ALLOCATION_PCT*100:.0f}% cash)")
                qty = clamped_qty

        if qty * est_price < 1.0:
            return (0, "trade too small (<$1 notional)")

        return (round(qty, 6), "; ".join(notes))

    def _estimate_price(self, symbol: str) -> float:
        """Best-effort price estimate from accountant bar data, positions, or fallback."""
        accountant = self._ns.get("accountant")
        if accountant:
            bar_price = accountant.get_last_price(symbol, 0.0)
            if bar_price > 0:
                return bar_price
            pos = accountant.current_positions.get(symbol)
            if pos and pos.current_price > 0:
                return pos.current_price
        if "BTC" in symbol.upper():
            return 60000.0
        if "ETH" in symbol.upper():
            return 3000.0
        if "SOL" in symbol.upper():
            return 150.0
        return 100.0

    def _rule_based_decision(self, features: dict) -> dict:
        logger.debug("[crypto.pm] Rule-based: HOLD (no LLM key)")
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

        sections.append("## Current Date & Time")
        sections.append(f"  {datetime.now(timezone.utc).strftime('%A, %B %d, %Y %H:%M UTC')}")

        live_prices = features.get("live_prices", [])
        if live_prices:
            sections.append("\n## Live Price Snapshot")
            for p in live_prices[:20]:
                if isinstance(p, dict):
                    chg = p.get("change_pct", 0)
                    sections.append(f"  {p.get('symbol','?')}: ${p.get('price',0):.2f} ({chg:+.1f}%)")

        if self._decision_history:
            sections.append("\n## Recent Decision History (last 5)")
            for dh in self._decision_history[-5:]:
                sections.append(f"  [{dh.get('timestamp','')}] {dh.get('action_summary','hold')}")
                if dh.get("reasoning_snippet"):
                    sections.append(f"    Reasoning: {dh['reasoning_snippet']}")

        if sizing:
            sections.append("\n## Position Sizing Context")
            sections.append(f"  Pod NAV: ${sizing.get('pod_nav', 0):,.2f}")
            sections.append(f"  Available cash: ${sizing.get('available_cash', 0):,.2f}")
            sections.append(f"  Current leverage: {sizing.get('current_leverage', 0):.2f}x")
            sections.append(f"  Max leverage: {sizing.get('max_leverage', 2.0):.1f}x")
            sections.append(f"  Max position size: ${sizing.get('position_limit_notional', 0):,.2f} (15% of NAV — above 8% requires max conviction)")
            for p in sizing.get("positions_summary", []):
                sections.append(f"  Position: {p['symbol']} qty={p['qty']:.1f} notional=${p['notional']:,.0f} pnl=${p['unrealized_pnl']:,.2f}")

        sections.append("\n## Macro Indicators (FRED)")
        fred = features.get("fred_indicators", {})
        if fred:
            for k, v in fred.items():
                if v is not None:
                    sections.append(f"  {k}: {v}")
        sections.append(f"  Liquidity outlook: {features.get('liquidity_outlook', 'unknown')}")

        rate_table = features.get("global_rate_table", {})
        if rate_table:
            sections.append("\n## Global Central Bank Policy Rates")
            for bank, info in rate_table.items():
                sections.append(f"  {bank}: {info['value']:.2f}% ({info['rate_name']})")

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
        sections.append(f"\n## Universe (use XXX/USD format)\n  {universe[:20]}")

        user_content = "\n".join(sections)
        user_content += '\n\nBased on ALL the above data, propose 0-3 crypto trades or HOLD.\nOutput JSON: {"trades": [...], "read_articles": ["url1"]} (omit read_articles if not needed)'

        try:
            raw = llm_chat(
                [
                    {"role": "system", "content": _CRYPTO_SYSTEM},
                    {"role": "user", "content": user_content},
                ],
                max_tokens=1200,
            )
            decision = extract_json(raw)

            if self._session_logger:
                self._session_logger.log_reasoning(f"pm:{self._pod_id}", "prompt", user_content)
                self._session_logger.log_reasoning(f"pm:{self._pod_id}", "response", raw or "")

            read_urls = decision.get("read_articles", [])
            if read_urls and isinstance(read_urls, list):
                decision, raw_second = await self._read_articles_and_decide(
                    read_urls, user_content, _CRYPTO_SYSTEM, decision
                )
                response_text = raw_second or raw
            else:
                response_text = raw

            parsed_trades = decision.get("trades", [])
            if isinstance(parsed_trades, dict):
                parsed_trades = [parsed_trades]

            validated_trades = []
            for t in parsed_trades:
                action = str(t.get("action", "HOLD")).upper()
                if action == "HOLD":
                    validated_trades.append(t)
                    continue
                try:
                    TradeProposal(action=action, symbol=str(t.get("symbol", "")),
                                  qty=float(t.get("qty", 0)), reasoning=t.get("reasoning", ""))
                    validated_trades.append(t)
                except Exception as ve:
                    logger.warning("[crypto.pm] Invalid trade proposal skipped: %s — %s", t, ve)
            parsed_trades = validated_trades

            action_parts = []
            for t in parsed_trades:
                action_parts.append(f"{t.get('action','')} {t.get('qty',0)} {t.get('symbol','')}")
            action_summary = ", ".join(action_parts) if action_parts else "holding"
            self.store("last_pm_decision", {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "trades": parsed_trades[:10],
                "reasoning": response_text or "",
                "action_summary": action_summary[:500],
            })

            self._decision_history.append({
                "timestamp": datetime.now(timezone.utc).strftime("%H:%M"),
                "action_summary": action_summary[:200],
                "reasoning_snippet": (response_text or "")[:150],
                "symbols": [t.get("symbol", "") for t in parsed_trades if t.get("action", "HOLD") != "HOLD"],
            })
            if len(self._decision_history) > 5:
                self._decision_history = self._decision_history[-5:]

            trades = parsed_trades
            if not trades:
                return {}

            orders = []
            cycle_notional_used = 0.0
            for t in trades[:3]:
                action = str(t.get("action", "HOLD")).upper()
                if action == "HOLD":
                    continue
                symbol = str(t.get("symbol", "BTC/USD")).strip()
                qty = float(t.get("qty", 1))
                if qty <= 0:
                    continue
                side = Side.BUY if action == "BUY" else Side.SELL
                reasoning = t.get("reasoning", "")
                qty, clamp_note = self._apply_sizing_discipline(
                    qty, symbol, side, sizing, cycle_notional_used,
                )
                if qty <= 0:
                    logger.info("[crypto.pm] Skipped %s %s: %s", action, symbol, clamp_note)
                    continue
                est_price = self._estimate_price(symbol)
                cycle_notional_used += qty * est_price
                order = Order(
                    id=uuid.uuid4(), pod_id=self._pod_id, symbol=symbol,
                    side=side, order_type=OrderType.MARKET, quantity=qty,
                    limit_price=None, timestamp=datetime.now(timezone.utc),
                    strategy_tag=f"llm_crypto_{action.lower()}",
                )
                orders.append(order)
                log_suffix = f" [{clamp_note}]" if clamp_note else ""
                logger.info("[crypto.pm] LLM: %s %s %s (%s)%s", action, symbol, qty, reasoning, log_suffix)

            if not orders:
                return {}
            first, rest = orders[0], orders[1:]
            if rest:
                self.store("pm_additional_orders", [o.model_dump(mode="json") for o in rest])
            return {"order": first}
        except Exception as e:
            logger.warning("[crypto.pm] LLM failed, falling back: %s", e)
            return self._rule_based_decision(features)
