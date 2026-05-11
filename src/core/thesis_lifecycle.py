"""Lifecycle review for open-position entry theses.

The entry thesis is treated as a live contract.  A position can remain open
only while the assumptions behind the original trade still survive current
macro, price, and risk context.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

ThesisStatus = Literal["valid", "watch", "challenged", "broken", "needs_pm_rewrite"]

BLOCKING_STATUSES: set[str] = {"challenged", "broken", "needs_pm_rewrite"}
_PRECIOUS_METALS = {"GLD", "GDX", "GDXJ", "SLV", "IAU", "SGOL", "SIL", "SILJ", "PAXG"}
_ENERGY = {"USO", "UCO", "SCO", "BNO", "UNG", "BOIL", "KOLD", "DBO", "UGA"}
_INDUSTRIAL_METALS = {"CPER", "COPX", "DBB", "PICK", "JJCTF"}
_AGRICULTURE = {"DBA", "CORN", "WEAT", "SOYB", "CANE", "JO", "BAL", "NIB"}
_BROAD_COMMODITIES = {"DBC", "PDBC", "GSG", "COMT"}


_ASSET_MONITOR_PROFILES: dict[str, dict[str, Any]] = {
    "equities": {
        "monitors": [
            "earnings_fundamentals",
            "valuation",
            "sector_market_beta",
            "rates_macro",
            "catalyst_flow",
        ],
        "keyword_groups": [
            ("earnings/fundamentals", ("earnings", "eps", "revenue", "margin", "cash flow", "profit", "fundamental")),
            ("valuation", ("valuation", "multiple", "p/e", "cheap", "expensive", "discount", "rerating")),
            ("sector/market beta", ("sector", "breadth", "beta", "index", "market", "relative strength")),
            ("rates/macro", ("rate", "yield", "fed", "inflation", "macro", "growth")),
            ("catalyst/flow", ("catalyst", "guidance", "news", "breakout", "flows", "positioning")),
        ],
        "min_hits": 2,
        "issue": "Equity thesis lacks enough explicit monitors across fundamentals, valuation, sector beta, rates/macro, and catalyst/flows.",
    },
    "fx": {
        "monitors": [
            "rate_differential",
            "central_bank_policy",
            "inflation_growth",
            "usd_cross_currency",
            "risk_sentiment",
        ],
        "keyword_groups": [
            ("rate differential/carry", ("rate differential", "carry", "yield differential", "interest rate", "rate gap")),
            ("central-bank policy", ("fed", "ecb", "boj", "boe", "central bank", "policy", "meeting")),
            ("inflation/growth", ("inflation", "growth", "cpi", "pmi", "employment", "recession")),
            ("USD/cross-currency driver", ("usd", "dollar", "dxy", "euro", "yen", "sterling", "cross")),
            ("risk sentiment", ("risk-on", "risk-off", "safe haven", "volatility", "credit")),
        ],
        "min_hits": 2,
        "issue": "FX thesis lacks enough explicit monitors across rate differentials, central-bank policy, inflation/growth, currency driver, and risk sentiment.",
    },
    "crypto": {
        "monitors": [
            "liquidity",
            "rates_real_yields",
            "risk_sentiment",
            "regulation_security",
            "flows_network",
        ],
        "keyword_groups": [
            ("liquidity", ("liquidity", "m2", "stablecoin", "global liquidity", "liquidity impulse")),
            ("rates/real yields", ("rate", "real yield", "real-rate", "tips", "fed", "yield")),
            ("risk sentiment", ("risk-on", "risk-off", "volatility", "nasdaq", "equities", "credit")),
            ("regulation/security", ("regulation", "sec", "etf", "lawsuit", "hack", "security")),
            ("flows/network", ("flow", "etf flow", "on-chain", "wallet", "hash", "developer", "adoption", "volume")),
        ],
        "min_hits": 2,
        "issue": "Crypto thesis lacks enough explicit monitors across liquidity, rates/real yields, risk sentiment, regulation/security, and flows/network activity.",
    },
    "commodities_precious_metals": {
        "monitors": [
            "real_yields",
            "breakevens",
            "fed_reaction",
            "usd",
            "positioning_flows",
            "central_bank_demand",
        ],
        "keyword_groups": [
            ("real yields", ("real yield", "real-rate", "real rate", "tips", "dfii")),
            ("breakevens/inflation expectations", ("breakeven", "inflation expectation", "inflation expectations", "t10yie")),
            ("Fed reaction", ("fed", "fomc", "higher for longer", "policy", "central bank")),
            ("USD/dollar", ("usd", "dollar", "dxy")),
            ("positioning/flows", ("positioning", "flow", "etf", "crowded")),
            ("central-bank demand", ("central bank demand", "reserve", "de-dollar", "dedollar")),
        ],
        "min_hits": 3,
        "issue": "Precious-metals thesis lacks enough explicit monitors across real yields, breakevens, Fed reaction, USD, positioning/flows, and central-bank demand.",
    },
    "commodities_energy": {
        "monitors": [
            "energy_supply_demand",
            "inventories",
            "opec_geopolitics",
            "usd",
            "growth_demand",
        ],
        "keyword_groups": [
            ("supply/demand", ("supply", "demand", "deficit", "surplus", "production", "consumption")),
            ("inventories", ("inventory", "inventories", "stockpile", "eia", "storage")),
            ("OPEC/geopolitics/weather", ("opec", "geopolitical", "hormuz", "sanction", "weather", "pipeline", "shipping")),
            ("USD/dollar", ("usd", "dollar", "dxy")),
            ("growth demand", ("growth", "recession", "pmi", "industrial", "travel", "china")),
        ],
        "min_hits": 2,
        "issue": "Energy thesis lacks enough explicit monitors across supply/demand, inventories, geopolitics/OPEC/weather, USD, and growth demand.",
    },
    "commodities_industrial_metals": {
        "monitors": [
            "industrial_demand",
            "inventories",
            "china_growth",
            "usd",
            "manufacturing_cycle",
        ],
        "keyword_groups": [
            ("industrial demand", ("industrial", "demand", "construction", "power grid", "electrification")),
            ("inventories", ("inventory", "inventories", "warehouse", "lme", "stockpile")),
            ("China/global growth", ("china", "growth", "stimulus", "property", "global")),
            ("USD/dollar", ("usd", "dollar", "dxy")),
            ("manufacturing cycle", ("manufacturing", "pmi", "capex", "cycle")),
        ],
        "min_hits": 2,
        "issue": "Industrial-metals thesis lacks enough explicit monitors across demand, inventories, China/global growth, USD, and manufacturing cycle.",
    },
    "commodities_agriculture": {
        "monitors": [
            "weather_crop",
            "inventories",
            "usd",
            "export_demand",
            "seasonality",
        ],
        "keyword_groups": [
            ("weather/crop", ("weather", "crop", "harvest", "planting", "drought", "flood")),
            ("inventories", ("inventory", "inventories", "stock", "stockpile", "usda")),
            ("USD/dollar", ("usd", "dollar", "dxy")),
            ("export demand", ("export", "demand", "china", "imports")),
            ("seasonality", ("seasonal", "seasonality", "season")),
        ],
        "min_hits": 2,
        "issue": "Agriculture thesis lacks enough explicit monitors across weather/crop conditions, inventories, USD, export demand, and seasonality.",
    },
    "commodities_broad": {
        "monitors": [
            "inflation_regime",
            "usd",
            "growth_cycle",
            "supply_demand_mix",
            "curve_roll",
        ],
        "keyword_groups": [
            ("inflation regime", ("inflation", "cpi", "breakeven", "inflation expectation")),
            ("USD/dollar", ("usd", "dollar", "dxy")),
            ("growth cycle", ("growth", "recession", "pmi", "cycle")),
            ("supply/demand mix", ("supply", "demand", "inventory", "inventories")),
            ("curve/roll", ("curve", "contango", "backwardation", "roll")),
        ],
        "min_hits": 2,
        "issue": "Broad-commodities thesis lacks enough explicit monitors across inflation, USD, growth, supply/demand mix, and curve/roll risk.",
    },
}


def _float_or_none(value: Any) -> float | None:
    try:
        if value is None or value == "":
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _normalise_regime(value: Any) -> str:
    text = str(value or "").strip().lower()
    if not text:
        return ""
    text = text.replace("_", "-")
    if "crisis" in text:
        return "crisis"
    if "risk-off" in text or "risk off" in text:
        return "risk-off"
    if "risk-on" in text or "risk on" in text:
        return "risk-on"
    if "neutral" in text:
        return "neutral"
    if "bull" in text:
        return "risk-on"
    if "bear" in text:
        return "risk-off"
    return text


def _contains_any(text: str, keywords: tuple[str, ...]) -> bool:
    return any(keyword in text for keyword in keywords)


def infer_asset_profile(symbol: str, pod_id: str, thesis_text: str) -> tuple[str, str, dict[str, Any] | None]:
    pod = str(pod_id or "").strip().lower()
    symbol_u = symbol.upper()

    if pod == "equities":
        return "equities", "equities", _ASSET_MONITOR_PROFILES["equities"]
    if pod == "fx":
        return "fx", "fx", _ASSET_MONITOR_PROFILES["fx"]
    if pod == "crypto":
        return "crypto", "crypto", _ASSET_MONITOR_PROFILES["crypto"]

    if pod == "commodities":
        if symbol_u in _PRECIOUS_METALS or "gold" in thesis_text or "silver" in thesis_text:
            return "commodities", "precious_metals", _ASSET_MONITOR_PROFILES["commodities_precious_metals"]
        if symbol_u in _ENERGY or any(token in thesis_text for token in ("oil", "crude", "gas", "lng", "energy")):
            return "commodities", "energy", _ASSET_MONITOR_PROFILES["commodities_energy"]
        if symbol_u in _INDUSTRIAL_METALS or any(token in thesis_text for token in ("copper", "industrial metal", "aluminum")):
            return "commodities", "industrial_metals", _ASSET_MONITOR_PROFILES["commodities_industrial_metals"]
        if symbol_u in _AGRICULTURE or any(token in thesis_text for token in ("corn", "wheat", "soy", "coffee", "cocoa", "crop")):
            return "commodities", "agriculture", _ASSET_MONITOR_PROFILES["commodities_agriculture"]
        if symbol_u in _BROAD_COMMODITIES:
            return "commodities", "broad", _ASSET_MONITOR_PROFILES["commodities_broad"]
        return "commodities", "broad", _ASSET_MONITOR_PROFILES["commodities_broad"]

    if symbol_u in _PRECIOUS_METALS:
        return "commodities", "precious_metals", _ASSET_MONITOR_PROFILES["commodities_precious_metals"]
    return pod or "unknown", "unknown", None


def profile_coverage(text: str, profile: dict[str, Any] | None) -> tuple[int, list[str], list[str]]:
    if not profile:
        return 0, [], []
    hit_labels: list[str] = []
    missing_labels: list[str] = []
    for label, keywords in profile.get("keyword_groups", []):
        if _contains_any(text, tuple(keywords)):
            hit_labels.append(label)
        else:
            missing_labels.append(label)
    return len(hit_labels), hit_labels, missing_labels


def current_regime(features: dict | None) -> str:
    features = features or {}
    regime = features.get("regime") or {}
    if isinstance(regime, dict):
        raw = regime.get("regime") or regime.get("label") or regime.get("name")
    else:
        raw = regime
    return _normalise_regime(raw or features.get("macro_outlook"))


def _fred(features: dict | None) -> dict:
    data = (features or {}).get("fred_indicators") or {}
    return data if isinstance(data, dict) else {}


def current_real_yield(features: dict | None) -> float | None:
    """Best-effort real-yield estimate from FRED-style features."""
    fred = _fred(features)

    for key in ("DFII10", "DFII5", "TIPS10", "TIPS_10Y", "REAL10Y"):
        value = _float_or_none(fred.get(key))
        if value is not None:
            return value

    nominal = _float_or_none(fred.get("DGS10"))
    breakeven = _float_or_none(fred.get("T10YIE"))
    if nominal is not None and breakeven is not None:
        return nominal - breakeven
    return None


def _entry_days(entry_date: str | None) -> int:
    if not entry_date:
        return 0
    try:
        d = datetime.fromisoformat(str(entry_date).split("T", 1)[0]).date()
        return max(0, (datetime.now(timezone.utc).date() - d).days)
    except Exception:
        return 0


def _status_from_score(score: float, forced: ThesisStatus | None = None) -> ThesisStatus:
    if forced:
        return forced
    if score <= 0.25:
        return "broken"
    if score <= 0.50:
        return "challenged"
    if score <= 0.75:
        return "watch"
    return "valid"


def review_position_thesis(
    *,
    symbol: str,
    entry_thesis: str,
    entry_metadata: dict | None,
    position: Any,
    features: dict | None,
    pod_id: str = "",
) -> dict:
    """Review an open position's thesis against current context.

    Returns a JSON-safe dict that can be stored on the accountant metadata,
    surfaced in the dashboard, and used by risk/PM gates.
    """
    meta = entry_metadata or {}
    thesis = str(entry_thesis or meta.get("entry_thesis") or meta.get("reasoning") or "").strip()
    text = thesis.lower()
    symbol_u = symbol.upper()
    issues: list[str] = []
    monitors: list[str] = []
    score = 1.0
    forced: ThesisStatus | None = None

    if not thesis or "metadata did not include" in text:
        issues.append("No usable entry thesis is stored; PM must rewrite before adding risk.")
        score -= 0.55
        forced = "needs_pm_rewrite"

    entry_regime = _normalise_regime(meta.get("entry_macro_regime") or meta.get("macro_regime"))
    regime_now = current_regime(features)
    if entry_regime and regime_now and entry_regime != regime_now:
        issues.append(f"Macro regime changed from {entry_regime} to {regime_now}.")
        monitors.append("macro_regime")
        score -= 0.25

    cost_basis = _float_or_none(getattr(position, "cost_basis", None)) or _float_or_none(meta.get("entry_price")) or 0.0
    current_price = _float_or_none(getattr(position, "current_price", None)) or cost_basis
    if cost_basis > 0 and current_price is not None:
        pnl_pct = (current_price - cost_basis) / cost_basis
        if getattr(position, "qty", 0) < 0:
            pnl_pct = -pnl_pct
        stop_loss = _float_or_none(meta.get("stop_loss_pct")) or _float_or_none(getattr(position, "stop_loss_pct", None)) or 0.05
        if pnl_pct <= -stop_loss:
            issues.append(f"Position is beyond thesis stop-loss ({pnl_pct:+.1%} vs -{stop_loss:.1%}).")
            monitors.append("price_action")
            score -= 0.35
        elif pnl_pct <= -0.75 * stop_loss:
            issues.append(f"Position is close to thesis stop-loss ({pnl_pct:+.1%} vs -{stop_loss:.1%}).")
            monitors.append("price_action")
            score -= 0.20

    max_hold_days = int(_float_or_none(meta.get("max_hold_days") or getattr(position, "max_hold_days", 0)) or 0)
    entry_date = getattr(position, "entry_date", "") or meta.get("entry_time") or ""
    held_days = _entry_days(entry_date)
    if max_hold_days > 0 and held_days > max_hold_days:
        issues.append(f"Time-bound thesis expired: held {held_days}d vs max {max_hold_days}d.")
        monitors.append("time_stop")
        score -= 0.30

    real_yield = current_real_yield(features)
    if "negative real rates" in text and real_yield is not None and real_yield > 0:
        issues.append(
            f"Original thesis claims negative real rates, but current real-yield proxy is positive ({real_yield:.2f}%)."
        )
        score -= 0.45
        forced = "challenged"

    asset_class, asset_theme, profile = infer_asset_profile(symbol_u, pod_id, text)
    if profile:
        monitors.extend(profile.get("monitors", []))
        hits, hit_labels, missing_labels = profile_coverage(text, profile)
        min_hits = int(profile.get("min_hits", 2))
        if hits < min_hits:
            issues.append(str(profile.get("issue") or "Thesis lacks enough explicit asset-class monitors."))
            score -= 0.27
        if asset_theme == "precious_metals":
            if all(token not in text for token in ("real yield", "tips", "real-rate", "real rate")):
                issues.append("Precious-metals thesis lacks an explicit real-yield monitor.")
                score -= 0.15
            if all(token not in text for token in ("usd", "dollar", "dxy")):
                issues.append("Precious-metals thesis lacks an explicit USD/dollar monitor.")
                score -= 0.10
    else:
        hits, hit_labels, missing_labels = 0, [], []

    status = _status_from_score(max(0.0, score), forced)
    unique_monitors = []
    for item in monitors:
        if item not in unique_monitors:
            unique_monitors.append(item)

    return {
        "symbol": symbol_u,
        "pod_id": pod_id,
        "asset_class": asset_class,
        "asset_theme": asset_theme,
        "status": status,
        "score": round(max(0.0, min(1.0, score)), 3),
        "issues": issues,
        "monitors": unique_monitors,
        "monitor_coverage": {
            "hits": hit_labels,
            "missing": missing_labels,
        },
        "entry_macro_regime": entry_regime,
        "current_macro_regime": regime_now,
        "current_real_yield": real_yield,
        "block_adds": status in BLOCKING_STATUSES,
        "requires_pm_rewrite": status in {"broken", "needs_pm_rewrite"},
        "reviewed_at": datetime.now(timezone.utc).isoformat(),
    }


def format_thesis_reviews_for_prompt(reviews: dict[str, dict] | None) -> str:
    if not reviews:
        return ""
    lines = []
    for symbol, review in sorted(reviews.items()):
        status = str(review.get("status", "unknown")).upper()
        score = float(review.get("score", 0.0) or 0.0)
        issues = review.get("issues") or []
        issue_text = "; ".join(str(i) for i in issues[:3]) if issues else "no issues detected"
        block = " ADD BLOCKED" if review.get("block_adds") else ""
        lines.append(f"  {symbol}: {status} score={score:.2f}{block} - {issue_text}")
    return "\n".join(lines)


def expansion_thesis_is_fresh(reasoning: str, review: dict | None) -> tuple[bool, str]:
    """Validate that an add/scale-up includes a fresh expansion thesis."""
    text = str(reasoning or "").strip().lower()
    if not text:
        return False, "Expansion/add has no PM reasoning."

    expansion_terms = ("expansion", "add", "scale", "increase", "add-on", "adding")
    if not any(term in text for term in expansion_terms):
        return False, "Expansion/add must explicitly explain why more risk is justified now."

    required_terms = ("thesis", "entry", "invalidation", "risk")
    missing = [term for term in required_terms if term not in text]
    if len(missing) >= 2:
        return False, "Expansion thesis must include thesis, entry, invalidation, and risk."

    if review and review.get("block_adds"):
        revalidation_terms = (
            "updated", "fresh", "revalidated", "still valid", "regime",
            "new catalyst", "changed", "news", "invalidated",
        )
        if not any(term in text for term in revalidation_terms):
            return (
                False,
                "Existing thesis is challenged/broken; PM must rewrite or revalidate against current regime/news.",
            )
    return True, ""
