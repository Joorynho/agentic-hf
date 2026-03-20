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

_FX_SYSTEM = """You are a senior FX portfolio manager at an institutional macro hedge fund.
You receive real macro data, prediction market odds, and news headlines every cycle.
Your job is to produce institutional-quality FX trade ideas with deep, differentiated reasoning.

ANALYTICAL FRAMEWORK:
1. RATE DIFFERENTIALS: Fed funds rate, 10Y yields, 2Y yields drive currency flows.
   - Higher rates attract capital → currency strengthens.
   - Rate cut expectations → currency weakens.
   - Focus on CHANGES in rate expectations, not absolute levels.
2. USD STRENGTH: DXY / trade-weighted USD index.
   - Strong USD pressures EM and commodity currencies.
   - Weak USD benefits non-USD assets.
3. PREDICTION MARKETS: Polymarket odds on rate cuts, elections, geopolitics.
   - Rate cut probability directly impacts FX carry.
   - Political/geopolitical events can cause rapid FX moves.
4. CENTRAL BANK DIVERGENCE: Compare Fed vs ECB/BoJ/BoE policy direction.
   - The DELTA in policy expectations matters more than current rates.
5. CARRY TRADES: High-yield vs low-yield currency pairs.

NEWS — THINK DEEPER, NOT SURFACE-LEVEL:
- Do NOT simply state "rates are high so sell/buy X." Explain what is CHANGING.
- If a central bank signals a pivot, think about which currencies have NOT yet repriced
  the spillover — the second-order opportunity is in the pairs that lag.
- Trade wars and tariff headlines: which currencies are directly exposed vs. indirectly
  benefiting as safe havens or alternative trade routes?
- Do NOT restate headlines. Explain the IMPLICATION and where the market is mispricing.

REASONING STANDARD — every trade MUST include:
- THESIS: The macro setup (rate diff, central bank divergence, carry) and why it favors this pair
- EDGE: What is the market not pricing? What change in expectations isn't reflected yet?
- SECOND-ORDER: Which related pairs or crosses benefit from the same dynamic but haven't moved?
- RISK: What would invalidate this thesis? (surprise data, intervention, political event)
- TIMING: Why enter now — is there a catalyst window (meeting, data release, event)?

ANTI-PATTERNS (will get your trades rejected):
- "DXY is high so sell USD" — this is level-based, not flow-based thinking
- Generic rate commentary without specific pair implications
- No edge: if you can't say what the market is mispricing, don't trade
- Chasing a move that already happened

Implementation uses currency/country ETFs: UUP, UDN, FXE, FXY, FXB, EWJ, EWG, etc.

Rules:
- HOLD is the right call most of the time. Only trade when you have a clear edge.
- Max 3 trades per cycle.

ARTICLE DEEP-DIVE:
If a headline suggests a material catalyst worth investigating, include "read_articles": ["url1", "url2"]
(max 3). You will receive the full article text.

WEB SEARCH:
If you need information not provided (e.g. a central bank decision date, policy announcement),
include "search_queries": ["query1", "query2"] (max 2). Results will be provided before your final decision.

Output JSON:
{"trades": [{"action": "BUY"|"SELL", "symbol": "TICKER", "qty": N, "conviction": 0.0-1.0, "reasoning": "THESIS: ... | EDGE: ... | RISK: ...", "stop_loss_pct": 0.05, "take_profit_pct": 0.15, "exit_when": "", "max_hold_days": 0}], "read_articles": ["url1"], "search_queries": ["query1"]}
conviction: 0.0 = no confidence, 0.5 = moderate, 0.8+ = high conviction, 1.0 = maximum.
stop_loss_pct: auto-exit if loss exceeds this % (default 5%). Use tighter stops (3%) in volatile setups.
take_profit_pct: auto-exit if gain exceeds this % (default 15%).
exit_when: free-text condition for exit (e.g. "exit if DXY breaks 105").
max_hold_days: optional. Set to a specific number of days if the thesis is time-bound (e.g. central bank decision in 10 days -> max_hold_days: 15). Set to 0 (default) for thesis-driven holds with no fixed time limit. Only set a limit when the trade thesis has a clear expiration.
Only trades with conviction >= 0.7 should be above 10% of NAV.
Omit read_articles if not needed.

POSITION SIZING:
- Low conviction (<0.5): max 5% of NAV
- Medium conviction (0.5-0.7): max 10% of NAV
- High conviction (>0.7): up to 20% of NAV
- Hard cap: 20% of NAV per position, 40% of cash per cycle
- Scale down in high-vol regimes. The Risk agent enforces hard limits.
Output qty as a specific number of shares/units, not a percentage."""


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
        self._decision_history: list[dict] = []
        self._pm_memory = None

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
                [{"role": "system", "content": "You are an FX PM evaluating a risk-adjusted trade size. Be concise."},
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
                logger.info("[fx.pm] Accepted revision: %s %s %.4f (%s)", revised_order.side.value, revised_order.symbol, revised_order.quantity, reasoning)
                return {"order": revised_order}
            else:
                logger.info("[fx.pm] Rejected revision: %s %s (%s)", revised_order.side.value, revised_order.symbol, reasoning)
                return {}
        except Exception as e:
            logger.warning("[fx.pm] Revision eval failed, accepting: %s", e)
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

        upcoming_events = features.get("upcoming_events", [])
        if upcoming_events:
            sections.append("\n## Upcoming Events (next 14 days)")
            for evt in upcoming_events:
                sections.append(f"  - {evt.get('symbol', '?')} {evt.get('event_type', '')} in {evt.get('days_until', '?')} days ({evt.get('date', '')})")
            sections.append("  WARNING: Binary events (FOMC, earnings) create unpredictable gaps. Reduce size or avoid.")

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
            bull_count = sum(1 for h in headlines if h.get("sentiment_label") == "bullish")
            bear_count = sum(1 for h in headlines if h.get("sentiment_label") == "bearish")
            neut_count = len(headlines) - bull_count - bear_count
            sents = [h.get("sentiment", 0.0) for h in headlines]
            avg_sent = sum(sents) / len(sents) if sents else 0.0
            avg_rel = sum(h.get("relevancy", 0.5) for h in headlines) / len(headlines)
            avg_imp = sum(h.get("impact", 0.3) for h in headlines) / len(headlines)
            sections.append(f"  Summary: sentiment={avg_sent:+.2f} | relevancy={avg_rel:.2f} | impact={avg_imp:.2f} | {bull_count} bullish, {bear_count} bearish, {neut_count} neutral")
            for h in headlines[:15]:
                sl = h.get("sentiment_label", "neutral")
                sv = h.get("sentiment", 0.0)
                rel = h.get("relevancy", 0.5)
                imp = h.get("impact", 0.3)
                line = f"  - [{h.get('source','')} | {sl} {sv:+.2f} | rel:{rel:.1f} imp:{imp:.1f}] {h.get('title','')}"
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

        perf = self._ns.get("performance_summary")
        if perf:
            sections.append("\n## Performance Metrics")
            sections.append(f"  Sharpe ratio: {perf.get('sharpe', 0):.2f}")
            sections.append(f"  Sortino ratio: {perf.get('sortino', 0):.2f}")
            sections.append(f"  Max drawdown: {perf.get('max_drawdown', 0):.2%}")
            sections.append(f"  Current volatility (ann.): {perf.get('current_vol', 0):.2%}")
            sections.append(f"  Total return: {perf.get('total_return_pct', 0):.1f}%")

        firm_memo = self._ns.get("firm_memo") or ""
        if firm_memo:
            sections.append(f"\n## Firm Intelligence\n{firm_memo}")

        sections.append(f"\n## Current Positions\n  {positions}")

        user_content = "\n".join(sections)
        mem = self._get_pm_memory()
        if mem:
            memory_block = mem.recall()
            if memory_block:
                user_content = memory_block + "\n\n" + user_content
        user_content += '\n\nBased on ALL the above data (including your track record if shown), propose 0-3 FX ETF trades or HOLD. Learn from past wins/losses.\nOutput JSON: {"trades": [...], "read_articles": ["url1"]} (omit read_articles if not needed)'

        aging_alerts = self._ns.get("aging_alerts") or []
        if aging_alerts:
            accountant = self._ns.get("accountant")
            held = set(accountant._positions.keys()) if accountant and isinstance(getattr(accountant, "_positions", None), dict) else set()
            relevant = [a for a in aging_alerts if a.get("symbol") in held] if held else aging_alerts
            if relevant:
                aging_lines = "\n".join(
                    f"  \u26a0 {a['symbol']}: held {a['days_held']}d / max {a['max_hold_days']}d"
                    f" \u2014 ASSESS THESIS VALIDITY. Propose exit if thesis is stale."
                    for a in relevant
                )
                user_content = (
                    f"POSITION AGING ALERTS \u2014 mandatory reassessment:\n{aging_lines}\n\n"
                    + user_content
                )

        # Inject CIO capital reallocation directives if present
        trim_target = self._ns.get("trim_target_capital")
        growth_target = self._ns.get("growth_target_capital")
        invested = getattr(self._accountant, "invested", 0.0) if hasattr(self, "_accountant") else 0.0
        if trim_target and invested > 0:
            user_content = (
                f"CAPITAL REALLOCATION DIRECTIVE: CIO has reduced your capital allocation. "
                f"Target capital: ${trim_target:.0f}. Reduce position sizes accordingly — "
                f"prioritize exiting weakest-thesis positions first.\n\n"
            ) + user_content
        elif growth_target:
            user_content = (
                f"CAPITAL REALLOCATION DIRECTIVE: CIO has increased your capital allocation. "
                f"Target capital: ${growth_target:.0f}. Consider deploying additional capital "
                f"into highest-conviction opportunities.\n\n"
            ) + user_content

        try:
            held_symbols = list(self._ns.get("accountant")._positions.keys()) if (
                self._ns.get("accountant") and isinstance(
                    getattr(self._ns.get("accountant"), "_positions", None), dict
                )
            ) else []
        except Exception:
            held_symbols = []

        if held_symbols:
            try:
                from src.data.adapters.multiframe import compute_multiframe, format_multiframe_block
                fetch_fn = self._get_multiframe_fetch_fn()
                if fetch_fn is not None:
                    mf_data = compute_multiframe(held_symbols, fetch_fn)
                    mf_block = format_multiframe_block(mf_data)
                    if mf_block:
                        user_content = mf_block + "\n\n" + user_content
            except Exception as e:
                logger.debug("[%s] multiframe fetch error: %s", self._pod_id, e)

        try:
            raw = llm_chat(
                [
                    {"role": "system", "content": _FX_SYSTEM},
                    {"role": "user", "content": user_content},
                ],
                max_tokens=1200,
            )
            decision = extract_json(raw)

            if self._session_logger:
                self._session_logger.log_reasoning(f"pm:{self._pod_id}", "prompt", user_content)
                self._session_logger.log_reasoning(f"pm:{self._pod_id}", "response", raw or "")

            search_queries = decision.get("search_queries", [])
            if search_queries and isinstance(search_queries, list):
                decision, raw_search = await self._web_search_and_decide(
                    search_queries[:2], user_content, _FX_SYSTEM, decision
                )
                raw = raw_search or raw

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
                    logger.warning("[fx.pm] Invalid trade proposal skipped: %s — %s", t, ve)
            parsed_trades = validated_trades

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

            # Persist to DuckDB for cross-restart memory
            pm_mem = self._get_pm_memory()
            if pm_mem:
                symbols = [t.get("symbol", "") for t in parsed_trades if t.get("symbol") and t.get("action", "HOLD") != "HOLD"]
                if symbols:
                    has_buy = any(t.get("action", "").upper() == "BUY" for t in parsed_trades)
                    action_sum = f"{'BUY' if has_buy else 'SELL'} {', '.join(symbols[:5])}"
                    try:
                        pm_mem.record(action_sum, (response_text or "")[:300], symbols)
                    except Exception:
                        pass

            trades = parsed_trades
            if not trades:
                return {}

            orders = []
            cycle_notional_used = 0.0
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
                conviction = max(0.0, min(1.0, float(t.get("conviction", 0.5))))
                qty, clamp_note = self._apply_sizing_discipline(
                    qty, symbol, side, sizing, cycle_notional_used,
                    conviction=conviction,
                )
                if qty <= 0:
                    logger.info("[fx.pm] Skipped %s %s: %s", action, symbol, clamp_note)
                    continue
                est_price = self._estimate_price(symbol)
                cycle_notional_used += qty * est_price
                order = Order(
                    id=uuid.uuid4(), pod_id=self._pod_id, symbol=symbol,
                    side=side, order_type=OrderType.MARKET, quantity=qty,
                    limit_price=None, timestamp=datetime.now(timezone.utc),
                    strategy_tag=f"llm_fx_{action.lower()}",
                    conviction=conviction,
                )
                orders.append(order)
                log_suffix = f" [{clamp_note}]" if clamp_note else ""
                logger.info("[fx.pm] LLM: %s %s %.2f conv=%.1f (%s)%s", action, symbol, qty, conviction, reasoning, log_suffix)

            if not orders:
                return {}
            first, rest = orders[0], orders[1:]
            if rest:
                self.store("pm_additional_orders", [o.model_dump(mode="json") for o in rest])
            return {"order": first}
        except Exception as e:
            logger.warning("[fx.pm] LLM failed, falling back: %s", e)
            return self._rule_based_decision(features)

    async def _web_search_and_decide(
        self, queries: list[str], base_prompt: str, system: str, first_decision: dict
    ) -> tuple[dict, str | None]:
        from src.data.adapters.web_search import WebSearchAdapter
        if not hasattr(self, "_web_searcher"):
            self._web_searcher = WebSearchAdapter()
        all_results: list[dict] = []
        for q in queries[:2]:
            results = await self._web_searcher.search(q)
            all_results.extend(results)
        if not all_results:
            return (first_decision, None)
        search_section = "\n\n## Web Search Results (requested by you)\n"
        for r in all_results[:10]:
            search_section += f"\n- **{r.get('title', '')}**\n  {r.get('snippet', '')}\n  URL: {r.get('url', '')}\n"
        enriched = base_prompt + search_section
        enriched += '\n\nYou have the search results. Make your FINAL trading decision.\nOutput JSON only: {"trades": [...]}'
        try:
            raw = llm_chat(
                [{"role": "system", "content": system}, {"role": "user", "content": enriched}],
                max_tokens=1200,
            )
            if self._session_logger:
                self._session_logger.log_reasoning(f"pm:{self._pod_id}", "web_search_response", raw or "")
            return (extract_json(raw), raw)
        except Exception as e:
            logger.warning("[fx.pm] Web search re-prompt failed: %s", e)
            return (first_decision, None)

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
            logger.info("[fx.pm] Article deep-dive complete (%d articles read)", len(articles))
            if self._session_logger:
                self._session_logger.log_reasoning(f"pm:{self._pod_id}", "prompt", enriched)
                self._session_logger.log_reasoning(f"pm:{self._pod_id}", "response", raw or "")
            return (extract_json(raw), raw)
        except Exception as e:
            logger.warning("[fx.pm] Article deep-dive LLM failed: %s", e)
            return (first_decision, None)

    def _apply_sizing_discipline(
        self, qty: float, symbol: str, side: Side,
        sizing: dict, cycle_notional_used: float,
        conviction: float = 0.5,
    ) -> tuple[float, str]:
        """Clamp trade qty to PM-level budget limits before sending to Risk.

        Conviction-based position caps (enforced, not advisory):
          conviction < 0.3  → max  5% NAV
          conviction 0.3-0.5 → max 10% NAV
          conviction 0.5-0.7 → max 15% NAV
          conviction > 0.7  → max 20% NAV
        """
        nav = sizing.get("pod_nav", 0)
        cash = sizing.get("available_cash", 0)
        if nav <= 0:
            return (qty, "")

        est_price = self._estimate_price(symbol)
        if est_price <= 0:
            return (qty, "")
        proposed_notional = qty * est_price

        notes = []

        conviction = max(0.0, min(1.0, conviction))
        if conviction < 0.3:
            conv_cap = 0.05
        elif conviction < 0.5:
            conv_cap = 0.10
        elif conviction < 0.7:
            conv_cap = 0.15
        else:
            conv_cap = PM_MAX_SINGLE_TRADE_PCT

        max_single_notional = nav * conv_cap
        if proposed_notional > max_single_notional:
            clamped_qty = math.floor(max_single_notional / est_price * 100) / 100
            if clamped_qty < 1 and est_price > max_single_notional:
                clamped_qty = max_single_notional / est_price
            notes.append(f"capped {qty:.2f}->{clamped_qty:.2f} (conv={conviction:.1f} → max {conv_cap*100:.0f}% NAV)")
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

    def _get_pm_memory(self):
        """Lazily initialize PMMemory from the namespace audit_log. Returns None if unavailable."""
        if self._pm_memory is not None:
            return self._pm_memory
        try:
            from src.core.pm_memory import PMMemory
            audit_log = self._ns.get("audit_log")
            if audit_log is None:
                return None
            self._pm_memory = PMMemory(self._pod_id, audit_log)
            return self._pm_memory
        except Exception:
            return None

    def _get_multiframe_fetch_fn(self):
        """Return a sync fetch_fn(symbol, days) -> list[Bar] using YFinanceAdapter + ParquetCache.
        Returns None if the adapter cannot be initialised."""
        try:
            import os
            from datetime import date, timedelta
            from src.data.adapters.yfinance_adapter import YFinanceAdapter
            from src.data.cache.parquet_cache import ParquetCache
            cache_dir = os.path.join(os.path.dirname(__file__), "../../../../.cache/multiframe")
            cache = ParquetCache(os.path.normpath(cache_dir))
            adapter = YFinanceAdapter(cache)

            def fetch_fn(symbol: str, days: int):
                end = date.today()
                start = end - timedelta(days=days + 10)  # buffer for weekends/holidays
                return adapter._fetch_sync(symbol, start, end)

            return fetch_fn
        except Exception as e:
            logger.debug("[%s] multiframe adapter init failed: %s", self._pod_id, e)
            return None

    def _rule_based_decision(self, features: dict) -> dict:
        logger.debug("[fx.pm] Rule-based: HOLD (no LLM key)")
        self.store("last_pm_decision", {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "trades": [],
            "reasoning": "Rule-based: no LLM available",
            "action_summary": "holding (rule-based)",
        })
        return {}
