from __future__ import annotations
import json
import logging
import math
from datetime import datetime, timezone
import uuid

from src.core.models.enums import Side, OrderType
from src.core.models.execution import Order, TradeProposal
from src.core.models.messages import AgentMessage
from src.core.llm import has_llm_key, llm_chat, extract_json
from src.pods.base.agent import BasePodAgent

logger = logging.getLogger(__name__)

PM_MAX_SINGLE_TRADE_PCT = 0.20
PM_MAX_CYCLE_ALLOCATION_PCT = 0.40

_EQUITIES_SYSTEM = """You are a senior equity portfolio manager at an institutional macro hedge fund.
You receive real macro data, prediction market odds, and news headlines every cycle.
Your job is to produce institutional-quality trade ideas with deep, differentiated reasoning.

ANALYTICAL FRAMEWORK:
1. MACRO REGIME: Read the FRED indicators (VIX, yield curve, credit spreads, rates).
   - Inverted yield curve + high VIX = defensive (bonds, utilities, reduce equity)
   - Steep curve + low VIX = risk-on (growth, cyclicals, increase equity)
2. PREDICTION MARKETS: Polymarket odds on policy, elections, rates, geopolitics.
   - High-probability events should inform positioning (e.g. rate cut likely = long growth).
3. NEWS — THINK DEEPER, NOT SURFACE-LEVEL:
   - Do NOT chase rallies. If a stock already moved on news, the opportunity is gone.
   - Instead: WHY did it rally? What theme/catalyst drove it? Which related companies
     (suppliers, competitors, adjacent sectors) have NOT yet priced in the same catalyst?
   - Example: "CSCO rallied on AI networking demand" → look at ANET, JNPR, CIEN — the
     same demand wave hits them but they haven't moved yet.
   - Do NOT restate headlines as your thesis. Explain what the headline IMPLIES for the
     broader market/sector and where the second-order opportunity lies.
4. POSITIONS: Check what you already hold to avoid doubling down or concentration risk.

REASONING STANDARD — every trade MUST include:
- THESIS: The macro/micro setup and why it favors this specific trade right now
- EDGE: What is the market not pricing? Why is this opportunity still available?
- SECOND-ORDER: What's the non-obvious connection? (supply chain, sector rotation, policy spillover)
- RISK: What would invalidate this thesis? Name the specific downside scenario.
- TIMING: Why enter now and not next cycle?

ANTI-PATTERNS (will get your trades rejected):
- "Stock X rallied so buy stock X" — this is chasing, not investing
- Restating a headline as reasoning — you must go deeper
- No edge articulated — if you can't say why the market is wrong, don't trade
- Generic macro commentary without specific trade implications

Rules:
- HOLD (empty trades) is the right call most of the time. Only trade with conviction.
- Max 3 trades per cycle.
- Use ETFs for broad macro views (SPY, QQQ, XLF, TLT) and single names for targeted ideas.

ARTICLE DEEP-DIVE:
If a headline suggests a material catalyst worth investigating, include "read_articles": ["url1", "url2"]
(max 3) in your JSON. You will receive the full article text and make a final decision.

Output JSON:
{"trades": [{"action": "BUY"|"SELL", "symbol": "TICKER", "qty": N, "conviction": 0.0-1.0, "reasoning": "THESIS: ... | EDGE: ... | RISK: ..."}], "read_articles": ["url1"]}
conviction: 0.0 = no confidence, 0.5 = moderate, 0.8+ = high conviction, 1.0 = maximum.
Only trades with conviction >= 0.7 should be above 10% of NAV.
Omit read_articles if not needed.

POSITION SIZING:
- Low conviction (<0.5): max 5% of NAV
- Medium conviction (0.5-0.7): max 10% of NAV
- High conviction (>0.7): up to 20% of NAV
- Hard cap: 20% of NAV per position, 40% of cash per cycle
- Scale down in high-vol regimes. The Risk agent enforces hard limits.
Output qty as a specific number of shares/units, not a percentage."""


class EquitiesPMAgent(BasePodAgent):
    """LLM-powered portfolio manager for equities. Falls back to rule-based HOLD."""

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
        if context.get("risk_revision"):
            return await self._evaluate_risk_revision(context)

        features = context.get("features") or self.recall("features", {})
        if not features:
            return {}

        sizing = context.get("sizing_context", {})
        track_record = context.get("trade_track_record")

        if has_llm_key():
            return await self._llm_decision(features, sizing, track_record)
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
                f"from {original_qty:.2f} to {revised_order.quantity:.4f} shares.\n"
                f"Reason: {risk_reason}\n\n"
                f"Is this reduced size still a worthwhile trade? Consider:\n"
                f"- Does the thesis still hold at this smaller size?\n"
                f"- Is the position too small to matter?\n"
                f"- Would you rather skip and wait for a better entry?\n\n"
                f'Reply JSON: {{"accept": true/false, "reasoning": "brief explanation"}}'
            )
            raw = llm_chat(
                [{"role": "system", "content": "You are an equity PM evaluating a risk-adjusted trade size. Be concise."},
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
                logger.info("[equities.pm] Accepted revision: %s %s %.4f (%s)", revised_order.side.value, revised_order.symbol, revised_order.quantity, reasoning)
                return {"order": revised_order}
            else:
                logger.info("[equities.pm] Rejected revision: %s %s (%s)", revised_order.side.value, revised_order.symbol, reasoning)
                return {}
        except Exception as e:
            logger.warning("[equities.pm] Revision eval failed, accepting: %s", e)
            await self._broadcast_revision_decision(revised_order, True, f"Auto-accepted (eval error: {e})", original_qty)
            return {"order": revised_order}

    async def _broadcast_revision_decision(self, order, accepted: bool, reasoning: str, original_qty: float) -> None:
        try:
            action = "pm_accept_revision" if accepted else "pm_reject_revision"
            summary = (
                f"{'Accepted' if accepted else 'Rejected'} revision: {order.side.value} {order.symbol} "
                f"{original_qty:.2f} -> {order.quantity:.4f}. {reasoning}"
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

    async def _llm_decision(self, features: dict, sizing_context: dict | None = None,
                             trade_track_record: str | None = None) -> dict:
        positions = self.recall("current_positions_summary", "none")
        sizing = sizing_context or {}

        sections = []

        sections.append("## Current Date & Time")
        sections.append(f"  {datetime.now(timezone.utc).strftime('%A, %B %d, %Y %H:%M UTC')}")

        universe = self.recall("universe", [])
        if universe:
            sections.append("\n## Monitored Universe")
            sections.append(f"  {', '.join(universe[:30])}")

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
            sections.append(f"  Max position size: ${sizing.get('position_limit_notional', 0):,.2f} (20% of NAV — above 10% requires max conviction)")
            for p in sizing.get("positions_summary", []):
                sections.append(f"  Position: {p['symbol']} qty={p['qty']:.1f} notional=${p['notional']:,.0f} pnl=${p['unrealized_pnl']:,.2f}")

        sections.append("\n## Macro Indicators (FRED)")
        fred = features.get("fred_indicators", {})
        if fred:
            for k, v in fred.items():
                if v is not None:
                    sections.append(f"  {k}: {v}")
        sections.append(f"  Macro outlook: {features.get('macro_outlook', 'unknown')}")

        regime = features.get("regime") or self._ns.get("market_regime") or {}
        if regime:
            sections.append(f"\n## Market Regime: {regime.get('label', 'Unknown')}")
            sections.append(f"  {regime.get('description', '')}")
            sections.append(f"  Position sizing multiplier: {regime.get('scale', 1.0):.1f}x")

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

        track_record = trade_track_record or self._ns.get("trade_track_record") or ""
        if track_record and track_record != "No closed trades yet.":
            sections.append(f"\n## Trade Track Record\n{track_record}")

        signal_quality = self._ns.get("signal_quality") or ""
        if signal_quality:
            sections.append(f"\n## Signal Quality\n{signal_quality}")

        firm_memo = self._ns.get("firm_memo") or ""
        if firm_memo:
            sections.append(f"\n## Firm Intelligence\n{firm_memo}")

        sections.append(f"\n## Current Positions\n  {positions}")

        user_content = "\n".join(sections)
        user_content += '\n\nBased on ALL the above data (including your track record if shown), propose 0-3 trades or HOLD. Learn from past wins/losses.\nOutput JSON: {"trades": [...], "read_articles": ["url1"]} (omit read_articles if not needed)'

        try:
            raw = llm_chat(
                [
                    {"role": "system", "content": _EQUITIES_SYSTEM},
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
                    read_urls, user_content, _EQUITIES_SYSTEM, decision
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
                    TradeProposal(
                        action=action,
                        symbol=str(t.get("symbol", "")),
                        qty=float(t.get("qty", 0)),
                        reasoning=t.get("reasoning", ""),
                    )
                    validated_trades.append(t)
                except Exception as ve:
                    logger.warning("[equities.pm] Invalid trade proposal skipped: %s — %s", t, ve)
            parsed_trades = validated_trades

            # Build signal snapshot from current features for trade metadata
            signal_snap = {}
            fred = features.get("fred_indicators", {})
            if fred.get("VIXCLS") is not None:
                signal_snap["vix"] = fred["VIXCLS"]
            if fred.get("T10Y2Y") is not None:
                signal_snap["yield_curve"] = fred["T10Y2Y"]
            if features.get("macro_outlook"):
                signal_snap["macro_outlook"] = features["macro_outlook"]

            action_parts = []
            for t in parsed_trades:
                action_parts.append(f"{t.get('action','')} {t.get('qty',0)} {t.get('symbol','')}")
            action_summary = ", ".join(action_parts) if action_parts else "holding"
            self.store("last_pm_decision", {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "trades": parsed_trades[:10],
                "reasoning": response_text or "",
                "action_summary": action_summary[:500],
                "signal_snapshot": signal_snap,
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
                symbol = str(t.get("symbol", "SPY")).strip()
                qty = float(t.get("qty", 1))
                if qty <= 0:
                    continue
                side = Side.BUY if action == "BUY" else Side.SELL
                reasoning = t.get("reasoning", "")
                conviction = max(0.0, min(1.0, float(t.get("conviction", 0.5))))
                qty, clamp_note = self._apply_sizing_discipline(
                    qty, symbol, side, sizing, cycle_notional_used,
                )
                if qty <= 0:
                    logger.info("[equities.pm] Skipped %s %s: %s", action, symbol, clamp_note)
                    continue
                est_price = self._estimate_price(symbol)
                cycle_notional_used += qty * est_price
                order = Order(
                    id=uuid.uuid4(), pod_id=self._pod_id, symbol=symbol,
                    side=side, order_type=OrderType.MARKET, quantity=qty,
                    limit_price=None, timestamp=datetime.now(timezone.utc),
                    strategy_tag=f"llm_equities_{action.lower()}",
                    conviction=conviction,
                )
                orders.append(order)
                log_suffix = f" [{clamp_note}]" if clamp_note else ""
                logger.info("[equities.pm] LLM: %s %s %.2f conv=%.1f (%s)%s", action, symbol, qty, conviction, reasoning, log_suffix)

            if not orders:
                return {}
            first, rest = orders[0], orders[1:]
            if rest:
                self.store("pm_additional_orders", [o.model_dump(mode="json") for o in rest])
            return {"order": first}
        except Exception as e:
            logger.warning("[equities.pm] LLM failed, falling back: %s", e)
            return self._rule_based_decision(features)

    async def _read_articles_and_decide(
        self, urls: list[str], base_prompt: str, system: str, first_decision: dict
    ) -> tuple[dict, str | None]:
        """Fetch requested articles and make a second LLM call with enriched context.
        Returns (decision, raw_response) - raw_response is None when no second call."""
        from src.data.adapters.article_fetcher import ArticleFetcher

        if not hasattr(self, "_article_fetcher"):
            self._article_fetcher = ArticleFetcher()

        articles = await self._article_fetcher.fetch_articles(urls[:3])
        if not articles:
            logger.info("[equities.pm] No articles fetched, using first decision")
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
        enriched += '\n\nYou have read the articles. Make your FINAL trading decision.\nOutput JSON only: {"trades": [{"action": "BUY|SELL", "symbol": "TICKER", "qty": N, "reasoning": "..."}]}'

        try:
            raw = llm_chat(
                [{"role": "system", "content": system}, {"role": "user", "content": enriched}],
                max_tokens=1200,
            )
            logger.info("[equities.pm] Article deep-dive complete (%d articles read)", len(articles))
            if self._session_logger:
                self._session_logger.log_reasoning(f"pm:{self._pod_id}", "prompt", enriched)
                self._session_logger.log_reasoning(f"pm:{self._pod_id}", "response", raw or "")
            return (extract_json(raw), raw)
        except Exception as e:
            logger.warning("[equities.pm] Article deep-dive LLM failed: %s", e)
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
            clamped_qty = math.floor(max_single_notional / est_price * 100) / 100
            if clamped_qty < 1 and est_price > max_single_notional:
                clamped_qty = max_single_notional / est_price
            notes.append(f"capped {qty:.2f}->{clamped_qty:.2f} (max {PM_MAX_SINGLE_TRADE_PCT*100:.0f}% NAV)")
            qty = clamped_qty

        if side == Side.BUY:
            max_cycle_notional = cash * PM_MAX_CYCLE_ALLOCATION_PCT
            remaining = max_cycle_notional - cycle_notional_used
            if remaining <= 0:
                return (0, "cycle budget exhausted")
            trade_notional = qty * est_price
            if trade_notional > remaining:
                clamped_qty = math.floor(remaining / est_price * 100) / 100
                if clamped_qty < 1 and est_price > remaining:
                    clamped_qty = remaining / est_price
                notes.append(f"capped to cycle budget ({PM_MAX_CYCLE_ALLOCATION_PCT*100:.0f}% cash)")
                qty = clamped_qty

        if qty * est_price < 1.0:
            return (0, "trade too small (<$1 notional)")

        return (round(qty, 4), "; ".join(notes))

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
        return 100.0

    def _rule_based_decision(self, features: dict) -> dict:
        logger.debug("[equities.pm] Rule-based: HOLD (no LLM key)")
        self.store("last_pm_decision", {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "trades": [],
            "reasoning": "Rule-based: no LLM available",
            "action_summary": "holding (rule-based)",
        })
        return {}
