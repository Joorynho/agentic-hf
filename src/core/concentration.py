"""Firm-wide sector concentration checker — blocks buys at 40% firm NAV."""
from __future__ import annotations
from collections import defaultdict
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.core.models.pod_summary import PodSummary

MAX_SECTOR_PCT = 0.40   # 40% of firm NAV hard limit


def aggregate_exposure(summaries: dict[str, "PodSummary"]) -> dict[str, float]:
    """
    Returns {sector: fraction_of_firm_nav} aggregated across all pods.
    sector is the asset_class field from PodExposureBucket.
    """
    firm_nav = 0.0
    for s in summaries.values():
        if s.risk_metrics and s.risk_metrics.nav:
            firm_nav += s.risk_metrics.nav

    if firm_nav <= 0:
        return {}

    sector_notional: dict[str, float] = defaultdict(float)
    for summary in summaries.values():
        pod_nav = summary.risk_metrics.nav if (summary.risk_metrics and summary.risk_metrics.nav) else 0.0
        for bucket in (summary.exposure_buckets or []):
            # bucket.notional_pct_nav is the fraction of THIS pod's NAV
            abs_notional = bucket.notional_pct_nav * pod_nav
            sector_notional[bucket.asset_class] += abs_notional

    return {sector: notional / firm_nav for sector, notional in sector_notional.items()}


def check_concentration(sector: str, firm_exposure: dict[str, float]) -> tuple[bool, str]:
    """
    Returns (allowed, reason). allowed=False means block the buy.
    """
    current = firm_exposure.get(sector, 0.0)
    if current >= MAX_SECTOR_PCT:
        return False, (
            f"Firm-wide '{sector}' exposure is {current:.0%} — exceeds {MAX_SECTOR_PCT:.0%} limit. "
            f"No new buys in this sector until existing positions reduce."
        )
    return True, ""
