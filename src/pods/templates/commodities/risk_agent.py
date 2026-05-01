from __future__ import annotations
import logging
import uuid
from datetime import datetime, timezone
from src.core.factor_exposure import (
    MAX_GROSS_EXPOSURE_PCT,
    MIN_FACTOR_CONFIDENCE,
    classify_symbol,
    compute_factor_report,
    factor_limit_pct,
    format_factor_report,
    projected_gross_notional,
)
from src.core.models.enums import Side, OrderType
from src.core.models.execution import Order, RiskApprovalToken
from src.core.models.messages import AgentMessage
from src.pods.base.agent import BasePodAgent

logger = logging.getLogger(__name__)

MAX_LEVERAGE = MAX_GROSS_EXPOSURE_PCT
MIN_FRACTIONAL_QTY = 0.01
STOP_LOSS_PCT = 0.05
TAKE_PROFIT_PCT = 0.15


def _conviction_limit(conviction: float) -> float:
    """Position limit as % of NAV, scaled by conviction (10% at 0.0, 25% at 1.0)."""
    return 0.10 + 0.15 * max(0.0, min(1.0, conviction))


class CommoditiesRiskAgent(BasePodAgent):
    """Position-level risk checks for commodities."""

    def _dynamic_profiles(self) -> dict:
        profiles = self._ns.get("factor_profiles") or {}
        return profiles if isinstance(profiles, dict) else {}

    def _refresh_factor_report(self, accountant) -> dict:
        report = compute_factor_report(
            accountant.current_positions,
            accountant.nav,
            dynamic_profiles=self._dynamic_profiles(),
            cash=accountant.cash,
        )
        self._ns.set("factor_exposure_report", report)
        self._ns.set("factor_exposure_text", format_factor_report(report))
        return report

    def _risk_reducing_order(self, order: Order, existing_qty: float) -> bool:
        if existing_qty > 0 and order.side == Side.SELL:
            return True
        if existing_qty < 0 and order.side == Side.BUY:
            return True
        return False

    def _copy_order(self, order: Order, quantity: float) -> Order:
        return Order(
            id=order.id,
            pod_id=order.pod_id,
            symbol=order.symbol,
            side=order.side,
            order_type=order.order_type,
            quantity=round(quantity, 4),
            limit_price=order.limit_price,
            timestamp=order.timestamp,
            strategy_tag=order.strategy_tag,
            conviction=getattr(order, "conviction", 0.5),
        )

    def _current_factor_notional(self, report: dict, factor: str) -> float:
        row = (report.get("factors") or {}).get(factor, {})
        return float(row.get("notional", 0.0) or 0.0)

    def _factor_capacity_qty(self, report: dict, order: Order, est_price: float, nav: float) -> tuple[float | None, str]:
        profile = classify_symbol(order.symbol, self._dynamic_profiles())
        if profile.primary_factor == "unclassified" or profile.confidence < MIN_FACTOR_CONFIDENCE:
            return 0.0, (
                f"{order.symbol} has no validated commodities factor map. "
                "Researcher must classify the symbol before new buys are allowed."
            )

        if order.side != Side.BUY:
            return None, ""

        max_notional = None
        limiting_factor = ""
        for factor, weight in profile.exposures.items():
            if weight <= 0:
                continue
            limit_notional = factor_limit_pct(factor) * nav
            current = self._current_factor_notional(report, factor)
            room = limit_notional - current
            factor_room_notional = room / weight
            if max_notional is None or factor_room_notional < max_notional:
                max_notional = factor_room_notional
                limiting_factor = factor

        if max_notional is None:
            return None, ""

        requested_notional = order.quantity * est_price
        if requested_notional <= max_notional:
            return None, ""

        max_qty = max_notional / est_price if est_price > 0 else 0.0
        current_pct = self._current_factor_notional(report, limiting_factor) / nav if nav > 0 else 0.0
        reason = (
            f"Factor concentration: {limiting_factor} is {current_pct:.0%} of NAV "
            f"before trade; limit is {factor_limit_pct(limiting_factor):.0%}. "
            f"{order.symbol} adds {profile.exposures.get(limiting_factor, 0.0):.0%} exposure to that same driver."
        )
        return max_qty, reason

    def _check_stop_loss_take_profit(self, accountant) -> list[Order]:
        exit_orders: list[Order] = []
        regime = self._ns.get("market_regime") or {}
        regime_label = regime.get("label", "").lower()
        sl_pct = 0.03 if "crisis" in regime_label else STOP_LOSS_PCT

        for sym, snap in accountant.current_positions.items():
            if snap.cost_basis <= 0 or snap.qty == 0:
                continue
            meta = accountant._entry_metadata.get(sym, {})
            pos_sl = meta.get("stop_loss_pct", sl_pct)
            pos_tp = meta.get("take_profit_pct", TAKE_PROFIT_PCT)
            pnl_pct = (snap.current_price - snap.cost_basis) / snap.cost_basis

            reason = ""
            if pnl_pct < -pos_sl:
                reason = f"Stop-loss triggered: {sym} at {pnl_pct:+.2%} (limit -{pos_sl:.0%})"
            elif pnl_pct > pos_tp:
                reason = f"Take-profit triggered: {sym} at {pnl_pct:+.2%} (limit +{pos_tp:.0%})"

            if reason:
                side = Side.SELL if snap.qty > 0 else Side.BUY
                order = Order(
                    id=uuid.uuid4(), pod_id=self._pod_id, symbol=sym,
                    side=side, order_type=OrderType.MARKET,
                    quantity=abs(snap.qty), timestamp=datetime.now(timezone.utc),
                    strategy_tag="risk_auto_exit", conviction=1.0,
                )
                exit_orders.append(order)
                logger.info("[commodities.risk] %s", reason)
        return exit_orders

    async def run_cycle(self, context: dict) -> dict:
        order: Order | None = context.get("order")
        if order is None:
            return {}

        accountant = self._ns.get("accountant")
        if not accountant:
            token = RiskApprovalToken(order_id=order.id, pod_id=self._pod_id, expires_ms=500)
            await self._broadcast("risk_approval", order, f"Approved {order.side.value} {order.quantity:.2f} {order.symbol} (no accountant)")
            return {"token": token}

        exit_orders = self._check_stop_loss_take_profit(accountant)
        for eo in exit_orders:
            await self._broadcast("risk_auto_exit", eo, f"Auto-exit {eo.side.value} {eo.quantity:.2f} {eo.symbol}")

        nav = accountant.nav
        existing = accountant.current_positions.get(order.symbol)
        existing_qty = existing.qty if existing else 0.0
        est_price = (
            existing.current_price if existing
            else accountant.get_last_price(order.symbol, 100.0)
        )
        total_notional = sum(abs(s.qty * s.current_price) for s in accountant.current_positions.values())
        factor_report = self._refresh_factor_report(accountant)
        is_reducing = self._risk_reducing_order(order, existing_qty)

        # --- Reduce-only gate for inherited breaches / negative cash ---
        reduce_only_reasons = []
        gross_pct = total_notional / nav if nav > 0 else 0.0
        if accountant.cash < -0.01:
            reduce_only_reasons.append(f"cash is negative (${accountant.cash:.2f})")
        if gross_pct > MAX_GROSS_EXPOSURE_PCT:
            reduce_only_reasons.append(f"gross exposure is {gross_pct:.0%} of NAV")
        if reduce_only_reasons:
            self._ns.set("commodities_reduce_only", True)
            if not is_reducing:
                reason = (
                    "Reduce-only mode: " + "; ".join(reduce_only_reasons) + ". "
                    "New buys or risk-increasing trades are blocked until exposure is back inside NAV."
                )
                logger.info("[commodities.risk] %s", reason)
                await self._broadcast("risk_rejection", order, reason)
                return {"reason": reason}
            if abs(order.quantity) > abs(existing_qty):
                revised = self._copy_order(order, abs(existing_qty))
                reason = (
                    f"Reduce-only mode: capped {order.side.value} {order.symbol} "
                    f"{order.quantity:.2f} -> {revised.quantity:.2f} to avoid flipping exposure."
                )
                logger.info("[commodities.risk] %s", reason)
                await self._broadcast("risk_revision", order, reason, revised_qty=revised.quantity)
                return {"revised_order": revised, "reason": reason}
        else:
            self._ns.set("commodities_reduce_only", False)

        # Risk-reducing exits must not be blocked by concentration checks.
        if is_reducing:
            if abs(order.quantity) > abs(existing_qty):
                revised = self._copy_order(order, abs(existing_qty))
                reason = (
                    f"Risk-reducing order capped: {order.side.value} {order.symbol} "
                    f"{order.quantity:.2f} -> {revised.quantity:.2f} to avoid flipping exposure."
                )
                logger.info("[commodities.risk] %s", reason)
                await self._broadcast("risk_revision", order, reason, revised_qty=revised.quantity)
                return {"revised_order": revised, "reason": reason}
            token = RiskApprovalToken(order_id=order.id, pod_id=self._pod_id, expires_ms=500)
            await self._broadcast("risk_approval", order, f"Approved risk-reducing {order.side.value} {order.quantity:.2f} {order.symbol}")
            result: dict = {"token": token}
            if exit_orders:
                result["exit_orders"] = exit_orders
            return result

        if order.side == Side.SELL and existing_qty <= 0:
            reason = f"Short-opening SELL blocked for {order.symbol}; commodities pod supports reduce-only sells."
            logger.info("[commodities.risk] %s", reason)
            await self._broadcast("risk_rejection", order, reason)
            return {"reason": reason}

        # --- New symbols must have a validated factor map before any buy ---
        profile = classify_symbol(order.symbol, self._dynamic_profiles())
        if order.side == Side.BUY and (
            profile.primary_factor == "unclassified" or profile.confidence < MIN_FACTOR_CONFIDENCE
        ):
            reason = (
                f"{order.symbol} has no validated commodities factor map. "
                "Researcher must classify the symbol before new buys are allowed."
            )
            logger.info("[commodities.risk] %s", reason)
            await self._broadcast("risk_rejection", order, reason)
            return {"reason": reason}

        # --- Hard cash / gross exposure check: commodities cannot exceed realized NAV ---
        if order.side == Side.BUY:
            max_qty_cash = accountant.cash / est_price if est_price > 0 else 0.0
            projected_gross = projected_gross_notional(
                accountant.current_positions,
                order.symbol,
                order.side,
                order.quantity,
                est_price,
            )
            max_qty_gross = max(0.0, (MAX_GROSS_EXPOSURE_PCT * nav - total_notional) / est_price) if est_price > 0 else 0.0
            max_qty_capital = min(order.quantity, max_qty_cash, max_qty_gross)
            if projected_gross / nav > MAX_GROSS_EXPOSURE_PCT if nav > 0 else False:
                max_qty_capital = min(max_qty_capital, max_qty_gross)
            if max_qty_capital < order.quantity:
                if max_qty_capital < MIN_FRACTIONAL_QTY:
                    reason = (
                        f"Capital limit: no room for {order.symbol}. "
                        f"cash=${accountant.cash:.2f}, gross={gross_pct:.0%}, max gross={MAX_GROSS_EXPOSURE_PCT:.0%} NAV."
                    )
                    logger.info("[commodities.risk] %s", reason)
                    await self._broadcast("risk_rejection", order, reason)
                    return {"reason": reason}
                revised = self._copy_order(order, max_qty_capital)
                reason = (
                    f"Capital limit: {order.side.value} {order.symbol} {order.quantity:.2f} -> "
                    f"{revised.quantity:.2f} (cash=${accountant.cash:.2f}, gross cap={MAX_GROSS_EXPOSURE_PCT:.0%} NAV)"
                )
                logger.info("[commodities.risk] %s", reason)
                await self._broadcast("risk_revision", order, reason, revised_qty=revised.quantity)
                return {"revised_order": revised, "reason": reason}

        # --- Factor concentration check: GLD/GDX/GDXJ share gold/precious-metals risk ---
        max_factor_qty, factor_reason = self._factor_capacity_qty(factor_report, order, est_price, nav)
        if max_factor_qty is not None and max_factor_qty < order.quantity:
            if max_factor_qty < MIN_FRACTIONAL_QTY:
                logger.info("[commodities.risk] %s", factor_reason)
                await self._broadcast("risk_rejection", order, factor_reason)
                return {"reason": factor_reason}
            revised = self._copy_order(order, max_factor_qty)
            reason = f"{factor_reason} Revised {order.quantity:.2f} -> {revised.quantity:.2f}."
            logger.info("[commodities.risk] %s", reason)
            await self._broadcast("risk_revision", order, reason, revised_qty=revised.quantity)
            return {"revised_order": revised, "reason": reason}

        # --- Position limit check (conviction-scaled) ---
        conviction = getattr(order, "conviction", 0.5)
        regime = self._ns.get("market_regime") or {}
        regime_scale = regime.get("scale", 1.0)
        max_position_pct = min(0.30, _conviction_limit(conviction) * regime_scale)
        signed_qty = order.quantity if order.side == Side.BUY else -order.quantity
        new_qty = existing_qty + signed_qty
        new_notional = abs(new_qty) * est_price
        if nav > 0 and new_notional / nav > max_position_pct:
            max_notional = max_position_pct * nav
            max_qty = max_notional / est_price if est_price > 0 else 0
            if order.side == Side.BUY:
                max_qty = max(0, max_qty - existing_qty)
            else:
                max_qty = max(0, existing_qty - max_qty)
            if max_qty < MIN_FRACTIONAL_QTY:
                reason = f"Position limit ({max_position_pct*100:.0f}% NAV=${nav:.2f}, conv={conviction:.1f}). No feasible size for {order.symbol}."
                logger.info("[commodities.risk] %s", reason)
                await self._broadcast("risk_rejection", order, reason)
                return {"reason": reason}
            revised = self._copy_order(order, max_qty)
            reason = f"Position limit: {order.side.value} {order.symbol} {order.quantity:.2f} -> {revised.quantity:.2f} ({max_position_pct*100:.0f}% of NAV=${nav:.2f}, conv={conviction:.1f})"
            logger.info("[commodities.risk] %s", reason)
            await self._broadcast("risk_revision", order, reason, revised_qty=revised.quantity)
            return {"revised_order": revised, "reason": reason}

        # --- Gross exposure check ---
        order_notional = order.quantity * est_price
        projected_notional = projected_gross_notional(
            accountant.current_positions,
            order.symbol,
            order.side,
            order.quantity,
            est_price,
        )
        if nav > 0 and projected_notional / nav > MAX_LEVERAGE:
            max_add = MAX_LEVERAGE * nav - total_notional
            if max_add < MIN_FRACTIONAL_QTY * est_price:
                reason = f"Gross exposure limit ({MAX_LEVERAGE:.0%} NAV=${nav:.2f}). No room for {order.symbol}."
                logger.info("[commodities.risk] %s", reason)
                await self._broadcast("risk_rejection", order, reason)
                return {"reason": reason}
            max_qty_lev = max_add / est_price if est_price > 0 else 0
            revised = self._copy_order(order, max(MIN_FRACTIONAL_QTY, max_qty_lev))
            reason = f"Gross exposure limit: {order.side.value} {order.symbol} {order.quantity:.2f} -> {revised.quantity:.2f} ({MAX_LEVERAGE:.0%} NAV max)"
            logger.info("[commodities.risk] %s", reason)
            await self._broadcast("risk_revision", order, reason, revised_qty=revised.quantity)
            return {"revised_order": revised, "reason": reason}

        # --- Approved ---
        token = RiskApprovalToken(order_id=order.id, pod_id=self._pod_id, expires_ms=500)
        await self._broadcast("risk_approval", order, f"Approved {order.side.value} {order.quantity:.2f} {order.symbol}")
        result: dict = {"token": token}
        if exit_orders:
            result["exit_orders"] = exit_orders
        return result

    async def _broadcast(self, action: str, order: Order, summary: str, revised_qty: float | None = None) -> None:
        try:
            msg = AgentMessage(
                timestamp=datetime.now(timezone.utc),
                sender=self._agent_id,
                recipient="dashboard",
                topic="agent.activity",
                payload={
                    "agent_id": self._agent_id,
                    "agent_role": "Risk",
                    "pod_id": self._pod_id,
                    "action": action,
                    "summary": summary,
                    "detail": f"symbol={order.symbol} side={order.side.value} original_qty={order.quantity:.2f}" + (f" revised_qty={revised_qty:.2f}" if revised_qty else ""),
                },
            )
            await self._bus.publish("agent.activity", msg, publisher_id=self._agent_id)
        except Exception:
            pass
