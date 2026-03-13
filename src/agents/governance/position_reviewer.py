"""Daily position review — CIO challenges each pod's PM to justify holdings."""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any

from src.core.bus.event_bus import EventBus
from src.core.llm import llm_chat, extract_json, has_llm_key
from src.core.models.enums import OrderType, Side
from src.core.models.execution import Order
from src.core.models.messages import AgentMessage

logger = logging.getLogger(__name__)

_CIO_REVIEW_SYSTEM = """You are the Chief Investment Officer at an institutional hedge fund.
You are conducting a DAILY POSITION REVIEW for the {pod_id} pod.

Your job is to critically evaluate every open position. For each position, challenge the PM:
- Is the ORIGINAL ENTRY THESIS (shown below each position) still valid?
- Has the risk/reward changed since entry? What specific data points invalidate the thesis?
- Are there signs of thesis deterioration (adverse price action, changed macro, broken technicals)?
- Should size be adjusted given conviction level and portfolio context?

PAY ATTENTION to the entry thesis — the PM must defend WHY the original reason for the trade
is still valid, not just that the position is profitable.

Be specific and demanding. Reference the actual P&L, cost basis, and current price.
Do NOT rubber-stamp positions. A good CIO kills bad ideas early."""

_PM_DEFEND_SYSTEM = """You are the Portfolio Manager for the {pod_id} pod.
The CIO is conducting a daily position review and challenging your holdings.

For EACH position, you must respond with one of:
- HOLD: The ORIGINAL ENTRY THESIS is still valid. Explain WHY with current data.
- ADD: Thesis is strengthening. State the qty to add and the new catalyst.
- TRIM: Thesis is weakening or risk/reward changed. State the qty to sell.
- EXIT: Original thesis is invalidated. Explain what changed since entry.

Reference your original entry thesis (shown with each position) and explain
whether it is still valid or has been invalidated by new information.

Be honest. If a position has deteriorated, admit it and recommend EXIT or TRIM.
Do NOT defend losers out of ego. A good PM cuts losses and lets winners run.

Respond with JSON:
{"positions": [{"symbol": "X", "action": "HOLD|ADD|TRIM|EXIT", "qty": N_or_null, "reasoning": "..."}]}
qty is required for ADD and TRIM (number of shares/units to add or remove). null for HOLD and EXIT."""

_CIO_DECISION_SYSTEM = """You are the CIO reviewing the PM's position recommendations for the {pod_id} pod.

For each position, decide whether to ACCEPT or OVERRIDE the PM's recommendation.
- If the PM's reasoning is sound and data-backed, ACCEPT.
- If the PM is rationalizing a bad position or being too aggressive, OVERRIDE with your decision.
- You may change HOLD to TRIM/EXIT if you see deterioration the PM is ignoring.
- You may change ADD to HOLD if conviction isn't strong enough.

Respond with JSON:
{"decisions": [{"symbol": "X", "action": "HOLD|ADD|TRIM|EXIT", "qty": N_or_null, "reasoning": "...", "pm_overridden": true|false}]}"""


class PositionReviewer:
    """Runs a daily CIO-PM position review for all pods with open positions."""

    def __init__(self, event_bus: EventBus, session_logger: Any = None) -> None:
        self._bus = event_bus
        self._session_logger = session_logger

    async def run_review(
        self,
        pod_runtimes: dict,
        pod_accountants: dict,
    ) -> dict:
        """Run the daily position review across all pods.

        Returns a structured result with per-pod dialogues and actions.
        """
        if not has_llm_key():
            logger.info("[position_review] No LLM key — skipping review")
            return {"reviewed": False, "reason": "no_llm_key", "pods": {}}

        await self._broadcast("firm", "CIO", "review_started",
                              "Daily position review started", "")

        results: dict[str, dict] = {}
        for pod_id, runtime in pod_runtimes.items():
            accountant = pod_accountants.get(pod_id)
            if accountant is None:
                continue
            positions = accountant.current_positions
            if not positions:
                logger.info("[position_review] %s: no open positions, skipping", pod_id)
                continue

            try:
                pod_result = await self._review_pod(pod_id, runtime, accountant)
                results[pod_id] = pod_result
            except Exception as e:
                logger.warning("[position_review] %s review failed: %s", pod_id, e)
                results[pod_id] = {"error": str(e), "dialogue": [], "actions": []}

        await self._broadcast("firm", "CIO", "review_completed",
                              f"Daily review complete — {len(results)} pod(s) reviewed",
                              json.dumps({pid: r.get("summary", "") for pid, r in results.items()}, indent=2))

        return {"reviewed": True, "pods": results}

    async def _review_pod(self, pod_id: str, runtime, accountant) -> dict:
        """Review all positions for a single pod. Returns dialogue and agreed actions."""
        positions = accountant.current_positions
        nav = accountant.nav

        pos_lines = []
        for sym, snap in positions.items():
            pnl_pct = ((snap.current_price - snap.cost_basis) / snap.cost_basis * 100) if snap.cost_basis else 0
            line = (
                f"  {sym}: qty={snap.qty:.4f}, cost=${snap.cost_basis:.2f}, "
                f"current=${snap.current_price:.2f}, P&L=${snap.unrealized_pnl:+.2f} ({pnl_pct:+.1f}%)"
            )
            if snap.entry_thesis:
                line += f"\n    Entry thesis ({snap.entry_date}): {snap.entry_thesis}"
            pos_lines.append(line)
        positions_text = "\n".join(pos_lines)

        # --- Step 1: CIO challenges PM ---
        cio_challenge = await self._cio_review(pod_id, positions_text, nav)
        await self._broadcast(pod_id, "CIO", "position_review",
                              f"CIO reviewing {pod_id.upper()} positions ({len(positions)} held)",
                              cio_challenge)

        # --- Step 2: PM defends positions ---
        features = runtime._ns.get("features") if hasattr(runtime, '_ns') else {}
        pm_response, pm_raw = await self._pm_defend(pod_id, positions_text, cio_challenge, features)
        pm_response_text = json.dumps(pm_response, indent=2) if isinstance(pm_response, (dict, list)) else str(pm_response)
        pm_display = pm_raw if pm_raw else pm_response_text
        await self._broadcast(pod_id, "PM", "position_review",
                              f"{pod_id.upper()} PM position defense",
                              pm_display)

        # --- Step 3: CIO final decision ---
        decisions, cio_raw = await self._cio_decide(pod_id, pm_response_text, positions_text)
        decisions_text = json.dumps(decisions, indent=2) if isinstance(decisions, (dict, list)) else str(decisions)
        cio_display = cio_raw if cio_raw else decisions_text
        await self._broadcast(pod_id, "CIO", "position_review_decision",
                              f"CIO final decisions for {pod_id.upper()}",
                              cio_display)

        # --- Step 3.5: Challenge round — PM gets one more chance on overrides ---
        overridden = [d for d in decisions if isinstance(d, dict) and d.get("pm_overridden")]
        if overridden:
            await self._broadcast(pod_id, "CIO", "position_review_override",
                                  f"CIO overrode PM on {len(overridden)} position(s) — PM may counter-argue",
                                  json.dumps(overridden, indent=2))

            pm_counter, counter_raw = await self._pm_counter_argument(pod_id, overridden, positions_text, features)
            pm_counter_text = json.dumps(pm_counter, indent=2) if isinstance(pm_counter, (dict, list)) else str(pm_counter)
            counter_display = counter_raw if counter_raw else pm_counter_text
            await self._broadcast(pod_id, "PM", "position_review_counter",
                                  f"{pod_id.upper()} PM counter-argument on overridden positions",
                                  counter_display)

            final_decisions, final_raw = await self._cio_final_ruling(pod_id, pm_counter_text, decisions_text, positions_text)
            final_text = json.dumps(final_decisions, indent=2) if isinstance(final_decisions, (dict, list)) else str(final_decisions)
            final_display = final_raw if final_raw else final_text
            await self._broadcast(pod_id, "CIO", "position_review_final",
                                  f"CIO final ruling for {pod_id.upper()} after PM counter",
                                  final_display)
            decisions = final_decisions
            decisions_text = final_text

        # --- Step 4: Build orders for non-HOLD actions ---
        actions = self._extract_actions(decisions, positions)

        action_summary = ", ".join(
            f"{a['action']} {a.get('qty', 'all')} {a['symbol']}" for a in actions
        ) if actions else "all positions held"

        if self._session_logger:
            try:
                self._session_logger.log_reasoning(
                    agent_id=f"{pod_id}.position_review",
                    reasoning=f"CIO challenge:\n{cio_challenge}\n\nPM defense:\n{pm_display}\n\nCIO decisions:\n{cio_display}",
                    context={"pod_id": pod_id, "positions": len(positions), "actions": len(actions)},
                )
            except Exception:
                pass

        return {
            "cio_challenge": cio_challenge,
            "pm_response": pm_display,
            "cio_decisions": cio_display,
            "actions": actions,
            "summary": action_summary,
            "positions_reviewed": len(positions),
        }

    async def _cio_review(self, pod_id: str, positions_text: str, nav: float) -> str:
        """CIO evaluates positions and produces a challenge for the PM."""
        prompt = (
            f"Pod: {pod_id.upper()}\nPod NAV: ${nav:,.2f}\n\n"
            f"Current positions:\n{positions_text}\n\n"
            f"For each position above, provide your critical assessment:\n"
            f"1. Is the thesis still valid?\n"
            f"2. Should size be adjusted?\n"
            f"3. Any positions that should be exited immediately?\n"
            f"Be specific — reference actual P&L and price levels."
        )
        try:
            return llm_chat(
                [{"role": "system", "content": _CIO_REVIEW_SYSTEM.format(pod_id=pod_id.upper())},
                 {"role": "user", "content": prompt}],
                max_tokens=1200,
            )
        except Exception as e:
            logger.warning("[position_review] CIO review LLM failed: %s", e)
            return f"CIO review unavailable (LLM error). Positions:\n{positions_text}"

    async def _pm_defend(self, pod_id: str, positions_text: str,
                         cio_challenge: str, features: dict | None) -> tuple[list[dict], str]:
        """PM responds to CIO's challenge with per-position recommendation.

        Returns (parsed_positions, raw_llm_text) so the report can show the
        raw response even if JSON parsing fails.
        """
        macro_context = ""
        if features:
            fred = features.get("fred_indicators", {})
            if fred:
                macro_context = "\n## Current Macro Data\n" + "\n".join(
                    f"  {k}: {v}" for k, v in fred.items() if v is not None
                )
            rate_table = features.get("global_rate_table", {})
            if rate_table:
                macro_context += "\n## Global Central Bank Rates\n" + "\n".join(
                    f"  {bank}: {info['value']:.2f}% ({info['rate_name']})"
                    for bank, info in rate_table.items()
                )

        prompt = (
            f"CIO's challenge:\n{cio_challenge}\n\n"
            f"Your current positions:\n{positions_text}\n"
            f"{macro_context}\n\n"
            f"Respond for EACH position with your recommendation.\n"
            f"You MUST respond ONLY with valid JSON, no prose. Example:\n"
            f'{{"positions": [{{"symbol": "AAPL", "action": "HOLD", "qty": null, "reasoning": "..."}}]}}'
        )
        try:
            raw = llm_chat(
                [{"role": "system", "content": _PM_DEFEND_SYSTEM.format(pod_id=pod_id.upper())},
                 {"role": "user", "content": prompt}],
                max_tokens=1200,
            )
        except Exception as e:
            logger.warning("[position_review] PM defend LLM call failed: %s", e)
            return [{"symbol": "all", "action": "HOLD", "reasoning": f"Auto-hold (LLM error: {e})"}], ""

        try:
            parsed = extract_json(raw)
            positions = (
                parsed.get("positions")
                or parsed.get("items")
                or ([parsed] if "symbol" in parsed else [])
            )
            return positions, raw
        except Exception as e:
            logger.warning("[position_review] PM defend JSON parse failed: %s — raw: %.300s", e, raw)
            return [{"symbol": "all", "action": "HOLD", "reasoning": f"Auto-hold (parse error)"}], raw

    async def _cio_decide(self, pod_id: str, pm_response: str, positions_text: str) -> tuple[list[dict], str]:
        """CIO makes final decision on each position.

        Returns (decisions, raw_llm_text).
        """
        prompt = (
            f"PM's recommendations:\n{pm_response}\n\n"
            f"Current positions:\n{positions_text}\n\n"
            f"Make your final decision for each position.\n"
            f"You MUST respond ONLY with valid JSON, no prose. Example:\n"
            f'{{"decisions": [{{"symbol": "AAPL", "action": "HOLD", "qty": null, "reasoning": "...", "pm_overridden": false}}]}}'
        )
        try:
            raw = llm_chat(
                [{"role": "system", "content": _CIO_DECISION_SYSTEM.format(pod_id=pod_id.upper())},
                 {"role": "user", "content": prompt}],
                max_tokens=1200,
            )
        except Exception as e:
            logger.warning("[position_review] CIO decision LLM call failed: %s", e)
            return [], ""

        try:
            parsed = extract_json(raw)
            decisions = (
                parsed.get("decisions")
                or parsed.get("items")
                or ([parsed] if "symbol" in parsed else [])
            )
            return decisions, raw
        except Exception as e:
            logger.warning("[position_review] CIO decision JSON parse failed: %s — raw: %.300s", e, raw)
            return [], raw

    async def _pm_counter_argument(self, pod_id: str, overridden: list[dict],
                                     positions_text: str, features: dict | None) -> tuple[list[dict], str]:
        """PM gets one more chance to defend positions the CIO overrode.

        Returns (counters, raw_llm_text).
        """
        override_summary = "\n".join(
            f"  {d.get('symbol', '?')}: CIO changed to {d.get('action', '?')} — {d.get('reasoning', '')}"
            for d in overridden
        )
        macro_context = ""
        if features:
            fred = features.get("fred_indicators", {})
            if fred:
                macro_context = "\nRecent macro: " + ", ".join(
                    f"{k}={v}" for k, v in list(fred.items())[:8] if v is not None
                )

        prompt = (
            f"The CIO has OVERRIDDEN your recommendations on these positions:\n{override_summary}\n\n"
            f"Your current positions:\n{positions_text}\n{macro_context}\n\n"
            f"This is your FINAL chance to counter-argue. For each overridden position, either:\n"
            f"- ACCEPT the CIO's decision (if they're right)\n"
            f"- COUNTER with new evidence the CIO may have missed\n\n"
            f"You MUST respond ONLY with valid JSON:\n"
            f'{{\"counters\": [{{\"symbol\": \"X\", \"accept_override\": true, \"counter_reasoning\": \"...\"}}]}}'
        )
        try:
            raw = llm_chat(
                [{"role": "system", "content": _PM_DEFEND_SYSTEM.format(pod_id=pod_id.upper())},
                 {"role": "user", "content": prompt}],
                max_tokens=800,
            )
        except Exception as e:
            logger.warning("[position_review] PM counter-argument LLM call failed: %s", e)
            return [{"symbol": d.get("symbol", "?"), "accept_override": True,
                      "counter_reasoning": "Auto-accept (LLM error)"} for d in overridden], ""

        try:
            parsed = extract_json(raw)
            counters = (
                parsed.get("counters")
                or parsed.get("items")
                or ([parsed] if "symbol" in parsed else [])
            )
            return counters, raw
        except Exception as e:
            logger.warning("[position_review] PM counter JSON parse failed: %s — raw: %.300s", e, raw)
            return [{"symbol": d.get("symbol", "?"), "accept_override": True,
                      "counter_reasoning": "Auto-accept (parse error)"} for d in overridden], raw

    async def _cio_final_ruling(self, pod_id: str, pm_counter: str,
                                 original_decisions: str, positions_text: str) -> tuple[list[dict], str]:
        """CIO makes truly final decision after hearing PM's counter-argument.

        Returns (decisions, raw_llm_text).
        """
        prompt = (
            f"The PM has counter-argued on positions you overrode.\n\n"
            f"PM counter-arguments:\n{pm_counter}\n\n"
            f"Your original decisions:\n{original_decisions}\n\n"
            f"Current positions:\n{positions_text}\n\n"
            f"Make your FINAL decision. If the PM raised valid points, you may reverse your override.\n"
            f"You MUST respond ONLY with valid JSON:\n"
            f'{{\"decisions\": [{{\"symbol\": \"X\", \"action\": \"HOLD\", \"qty\": null, \"reasoning\": \"...\", \"pm_overridden\": false}}]}}'
        )
        try:
            raw = llm_chat(
                [{"role": "system", "content": _CIO_DECISION_SYSTEM.format(pod_id=pod_id.upper())},
                 {"role": "user", "content": prompt}],
                max_tokens=800,
            )
        except Exception as e:
            logger.warning("[position_review] CIO final ruling LLM call failed: %s", e)
            return [], ""

        try:
            parsed = extract_json(raw)
            decisions = (
                parsed.get("decisions")
                or parsed.get("items")
                or ([parsed] if "symbol" in parsed else [])
            )
            return decisions, raw
        except Exception as e:
            logger.warning("[position_review] CIO final ruling parse failed: %s — raw: %.300s", e, raw)
            return [], raw

    def _extract_actions(self, decisions: list[dict], positions: dict) -> list[dict]:
        """Convert CIO decisions into actionable trade instructions."""
        actions = []
        for d in decisions:
            if not isinstance(d, dict):
                continue
            action = str(d.get("action", "HOLD")).upper()
            symbol = d.get("symbol", "")
            if action == "HOLD" or not symbol:
                continue

            snap = positions.get(symbol)
            if snap is None:
                continue

            if action == "EXIT":
                actions.append({
                    "symbol": symbol,
                    "action": "EXIT",
                    "side": "SELL" if snap.qty > 0 else "BUY",
                    "qty": abs(snap.qty),
                    "reasoning": d.get("reasoning", "CIO exit decision"),
                })
            elif action == "TRIM":
                qty = d.get("qty")
                if qty is None or qty <= 0:
                    qty = abs(snap.qty) * 0.5
                actions.append({
                    "symbol": symbol,
                    "action": "TRIM",
                    "side": "SELL" if snap.qty > 0 else "BUY",
                    "qty": min(float(qty), abs(snap.qty)),
                    "reasoning": d.get("reasoning", "CIO trim decision"),
                })
            elif action == "ADD":
                qty = d.get("qty")
                if qty is None or qty <= 0:
                    qty = max(1, abs(snap.qty) * 0.25)
                actions.append({
                    "symbol": symbol,
                    "action": "ADD",
                    "side": "BUY" if snap.qty > 0 else "SELL",
                    "qty": float(qty),
                    "reasoning": d.get("reasoning", "CIO add decision"),
                })
        return actions

    def build_orders(self, actions: list[dict], pod_id: str) -> list[Order]:
        """Convert action dicts into Order objects for the risk pipeline."""
        orders = []
        for a in actions:
            try:
                orders.append(Order(
                    symbol=a["symbol"],
                    side=Side.BUY if a["side"] == "BUY" else Side.SELL,
                    quantity=a["qty"],
                    order_type=OrderType.MARKET,
                    pod_id=pod_id,
                    timestamp=datetime.now(timezone.utc),
                    strategy_tag="position_review",
                ))
            except Exception as e:
                logger.warning("[position_review] Failed to build order for %s: %s", a.get("symbol"), e)
        return orders

    async def _broadcast(self, pod_id: str, role: str, action: str,
                         summary: str, detail: str) -> None:
        try:
            msg = AgentMessage(
                timestamp=datetime.now(timezone.utc),
                sender=f"position_review.{role.lower()}",
                recipient="dashboard",
                topic="agent.activity",
                payload={
                    "agent_id": f"position_review.{role.lower()}",
                    "agent_role": role,
                    "pod_id": pod_id,
                    "action": action,
                    "summary": summary[:500],
                    "detail": detail,
                },
            )
            await self._bus.publish("agent.activity", msg, publisher_id=f"position_review.{role.lower()}")
        except Exception:
            pass
