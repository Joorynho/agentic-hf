from __future__ import annotations

from typing import Any, Mapping

from src.core.factor_exposure import compute_factor_report
from src.core.instrument_profile import get_instrument_profile
from src.core.models.enums import Side
from src.core.models.execution import Order, PortfolioConstructionReview
from src.core.managed_runtime import new_id, iso_now


def _position_qty_price(position: Any) -> tuple[float, float]:
    if isinstance(position, Mapping):
        return (
            float(position.get("qty", position.get("quantity", 0.0)) or 0.0),
            float(position.get("current_price", position.get("price", position.get("avg_entry", 0.0))) or 0.0),
        )
    return (
        float(getattr(position, "qty", getattr(position, "quantity", 0.0)) or 0.0),
        float(getattr(position, "current_price", getattr(position, "price", 0.0)) or 0.0),
    )


def _order_price(order: Order, positions: Mapping[str, Any], fallback_price: float | None = None) -> float:
    if order.limit_price:
        return float(order.limit_price)
    if fallback_price and fallback_price > 0:
        return float(fallback_price)
    pos = positions.get(order.symbol) if positions else None
    if pos:
        _, price = _position_qty_price(pos)
        if price > 0:
            return price
    return 0.0


def _risk_increasing(order: Order, positions: Mapping[str, Any]) -> bool:
    pos = positions.get(order.symbol) if positions else None
    qty, _ = _position_qty_price(pos) if pos else (0.0, 0.0)
    side = order.side.value.upper()
    order_qty = abs(float(order.quantity or 0.0))
    if qty > 0:
        return side == "BUY" or (side == "SELL" and order_qty > abs(qty))
    if qty < 0:
        return side == "SELL" or (side == "BUY" and order_qty > abs(qty))
    return True


def review_portfolio_construction(
    *,
    pod_id: str,
    order: Order,
    positions: Mapping[str, Any],
    nav: float,
    cash: float,
    dynamic_profiles: Any = None,
    fallback_price: float | None = None,
) -> PortfolioConstructionReview:
    """Advisory construction gate that can downsize/skip but never increases risk."""

    price = _order_price(order, positions, fallback_price=fallback_price)
    requested_notional = abs(float(order.quantity or 0.0) * price)
    if not _risk_increasing(order, positions):
        return PortfolioConstructionReview(
            review_id=new_id("pc"),
            pod_id=pod_id,
            symbol=order.symbol,
            side=order.side.value.upper(),
            requested_notional=requested_notional,
            recommended_notional=requested_notional,
            action="APPROVE_SIZE",
            reason="Risk-reducing order; portfolio construction records context but does not block reductions.",
            confidence=0.8,
            created_at=iso_now(),
        )

    profile = get_instrument_profile(order.symbol, dynamic_profiles)
    before = compute_factor_report(positions, nav or 1.0, dynamic_profiles=dynamic_profiles, cash=cash)
    duplicate_exposures: list[str] = []
    for factor, weight in profile.factor_loadings.items():
        if weight < 0.35:
            continue
        row = (before.get("factors") or {}).get(factor) or {}
        pct_nav = float(row.get("pct_nav") or 0.0)
        if pct_nav >= 0.20:
            duplicate_exposures.append(f"{factor}:{pct_nav:.0%}")

    action = "APPROVE_SIZE"
    recommended = requested_notional
    reason = "Portfolio construction approved requested size."
    funding = ""
    confidence = 0.65

    if requested_notional <= 0:
        action = "REQUEST_PM_REVISION"
        reason = "Cannot estimate order notional from current price; PM should refresh price/sizing evidence."
        recommended = 0.0
        confidence = 0.8
    elif cash < requested_notional and order.side == Side.BUY:
        action = "TRIM_TO_FUND"
        recommended = max(0.0, min(requested_notional, cash))
        funding = "Pod cash is insufficient for requested notional; trim an existing position or reduce order size."
        reason = funding
        confidence = 0.85
    elif duplicate_exposures:
        if len(duplicate_exposures) >= 2:
            action = "SKIP_DUPLICATIVE"
            recommended = 0.0
            reason = "Trade duplicates already meaningful factor exposures: " + ", ".join(duplicate_exposures)
            confidence = 0.8
        else:
            action = "DOWNSIZE"
            recommended = requested_notional * 0.5
            reason = "Trade overlaps existing factor exposure; downsize unless PM gives a stronger diversification/relative-value reason."
            confidence = 0.7

    expected_factor_change = {
        factor: round(float(weight) * requested_notional / nav, 4) if nav > 0 else 0.0
        for factor, weight in profile.factor_loadings.items()
        if weight >= 0.25
    }
    return PortfolioConstructionReview(
        review_id=new_id("pc"),
        pod_id=pod_id,
        symbol=order.symbol,
        side=order.side.value.upper(),
        requested_notional=round(requested_notional, 4),
        recommended_notional=round(min(recommended, requested_notional), 4),
        action=action,
        reason=reason,
        duplicate_exposures=duplicate_exposures,
        portfolio_impact={
            "primary_factor": profile.primary_factor,
            "instrument_role": profile.instrument_role,
            "gross_exposure_pct_before": before.get("gross_exposure_pct"),
            "cash": cash,
            "nav": nav,
        },
        funding_suggestion=funding,
        expected_factor_change=expected_factor_change,
        confidence=confidence,
        created_at=iso_now(),
    )
