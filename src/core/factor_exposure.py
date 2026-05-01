from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from src.core.models.enums import Side


MAX_GROSS_EXPOSURE_PCT = 1.0
MIN_FACTOR_CONFIDENCE = 0.35
DEFAULT_FACTOR_LIMIT_PCT = 0.40


FACTOR_ALIASES = {
    "gold": "gold_beta",
    "gold_beta": "gold_beta",
    "gold miners": "miners_equity",
    "gold_miners": "miners_equity",
    "silver": "silver_beta",
    "silver_beta": "silver_beta",
    "precious metals": "precious_metals",
    "precious_metals": "precious_metals",
    "oil": "oil",
    "crude": "oil",
    "crude_oil": "oil",
    "oil_beta": "oil",
    "natural gas": "natural_gas",
    "natgas": "natural_gas",
    "natural_gas": "natural_gas",
    "energy": "energy_equities",
    "energy_equities": "energy_equities",
    "agriculture": "agriculture",
    "agricultural": "agriculture",
    "softs": "agriculture",
    "industrial metals": "industrial_metals",
    "industrial_metals": "industrial_metals",
    "copper": "copper",
    "uranium": "uranium",
    "battery metals": "battery_metals",
    "battery_metals": "battery_metals",
    "miners": "miners_equity",
    "mining": "miners_equity",
    "miners_equity": "miners_equity",
    "broad commodities": "broad_commodities",
    "broad_commodities": "broad_commodities",
    "usd": "usd_inverse",
    "usd_inverse": "usd_inverse",
    "real rates": "real_rates",
    "real_rates": "real_rates",
    "equity": "equity_beta",
    "equity_beta": "equity_beta",
}


FACTOR_LIMITS_PCT = {
    # Shared drivers
    "gold_beta": 0.35,
    "precious_metals": 0.45,
    "miners_equity": 0.35,
    "silver_beta": 0.30,
    # Energy
    "oil": 0.45,
    "natural_gas": 0.35,
    "energy_equities": 0.45,
    # Other commodity complexes
    "agriculture": 0.45,
    "industrial_metals": 0.45,
    "copper": 0.35,
    "uranium": 0.30,
    "battery_metals": 0.35,
    "broad_commodities": 0.60,
    # Cross-asset macro overlays
    "usd_inverse": 0.60,
    "real_rates": 0.60,
    "equity_beta": 0.45,
}


@dataclass(frozen=True)
class RiskFactorProfile:
    symbol: str
    primary_factor: str
    exposures: dict[str, float]
    confidence: float = 1.0
    source: str = "static"
    reasoning: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "primary_factor": self.primary_factor,
            "exposures": dict(self.exposures),
            "confidence": self.confidence,
            "source": self.source,
            "reasoning": self.reasoning,
        }


def _norm_symbol(symbol: str) -> str:
    return str(symbol or "").strip().upper()


def canonical_factor(name: str) -> str | None:
    raw = str(name or "").strip().lower().replace("-", "_")
    raw = " ".join(raw.replace("_", " ").split())
    return FACTOR_ALIASES.get(raw) or FACTOR_ALIASES.get(raw.replace(" ", "_"))


def factor_limit_pct(factor: str) -> float:
    return FACTOR_LIMITS_PCT.get(factor, DEFAULT_FACTOR_LIMIT_PCT)


def _profile(symbol: str, primary: str, exposures: dict[str, float], source: str = "static") -> RiskFactorProfile:
    canonical = {canonical_factor(k) or k: max(0.0, min(1.0, float(v))) for k, v in exposures.items()}
    canonical = {k: v for k, v in canonical.items() if v > 0}
    primary_factor = canonical_factor(primary) or primary
    return RiskFactorProfile(
        symbol=_norm_symbol(symbol),
        primary_factor=primary_factor,
        exposures=canonical,
        confidence=1.0,
        source=source,
    )


STATIC_FACTOR_PROFILES: dict[str, RiskFactorProfile] = {
    # Gold and precious metals. Gold miners are intentionally gold-beta instruments.
    "GLD": _profile("GLD", "gold_beta", {"gold_beta": 1.0, "precious_metals": 1.0, "real_rates": 0.45, "usd_inverse": 0.30}),
    "IAU": _profile("IAU", "gold_beta", {"gold_beta": 1.0, "precious_metals": 1.0, "real_rates": 0.45, "usd_inverse": 0.30}),
    "SGOL": _profile("SGOL", "gold_beta", {"gold_beta": 1.0, "precious_metals": 1.0, "real_rates": 0.45, "usd_inverse": 0.30}),
    "PAXG": _profile("PAXG", "gold_beta", {"gold_beta": 1.0, "precious_metals": 1.0, "real_rates": 0.45, "usd_inverse": 0.30}),
    "GDX": _profile("GDX", "miners_equity", {"gold_beta": 0.85, "precious_metals": 0.90, "miners_equity": 1.0, "equity_beta": 0.35}),
    "GDXJ": _profile("GDXJ", "miners_equity", {"gold_beta": 0.90, "precious_metals": 0.90, "miners_equity": 1.0, "equity_beta": 0.45}),
    "NEM": _profile("NEM", "miners_equity", {"gold_beta": 0.80, "precious_metals": 0.80, "miners_equity": 1.0, "equity_beta": 0.35}),
    "GOLD": _profile("GOLD", "miners_equity", {"gold_beta": 0.80, "precious_metals": 0.80, "miners_equity": 1.0, "equity_beta": 0.35}),
    "SLV": _profile("SLV", "silver_beta", {"silver_beta": 1.0, "precious_metals": 0.80, "usd_inverse": 0.25}),
    "PSLV": _profile("PSLV", "silver_beta", {"silver_beta": 1.0, "precious_metals": 0.80, "usd_inverse": 0.25}),
    "SIL": _profile("SIL", "miners_equity", {"silver_beta": 0.85, "precious_metals": 0.75, "miners_equity": 0.75, "equity_beta": 0.35}),
    # Energy.
    "USO": _profile("USO", "oil", {"oil": 1.0, "usd_inverse": 0.20}),
    "BNO": _profile("BNO", "oil", {"oil": 1.0, "usd_inverse": 0.20}),
    "XLE": _profile("XLE", "energy_equities", {"oil": 0.70, "energy_equities": 1.0, "equity_beta": 0.45}),
    "XOP": _profile("XOP", "energy_equities", {"oil": 0.80, "energy_equities": 1.0, "equity_beta": 0.55}),
    "OIH": _profile("OIH", "energy_equities", {"oil": 0.75, "energy_equities": 1.0, "equity_beta": 0.50}),
    "AMLP": _profile("AMLP", "energy_equities", {"oil": 0.45, "natural_gas": 0.35, "energy_equities": 0.85, "equity_beta": 0.35}),
    "UNG": _profile("UNG", "natural_gas", {"natural_gas": 1.0, "usd_inverse": 0.15}),
    # Agriculture.
    "DBA": _profile("DBA", "agriculture", {"agriculture": 1.0, "usd_inverse": 0.20}),
    "CORN": _profile("CORN", "agriculture", {"agriculture": 1.0, "usd_inverse": 0.20}),
    "WEAT": _profile("WEAT", "agriculture", {"agriculture": 1.0, "usd_inverse": 0.20}),
    "SOYB": _profile("SOYB", "agriculture", {"agriculture": 1.0, "usd_inverse": 0.20}),
    "MOO": _profile("MOO", "agriculture", {"agriculture": 0.70, "equity_beta": 0.50}),
    "COW": _profile("COW", "agriculture", {"agriculture": 1.0}),
    "MOS": _profile("MOS", "agriculture", {"agriculture": 0.75, "equity_beta": 0.45}),
    "NTR": _profile("NTR", "agriculture", {"agriculture": 0.75, "equity_beta": 0.45}),
    # Broad and industrial commodities.
    "GSG": _profile("GSG", "broad_commodities", {"broad_commodities": 1.0, "oil": 0.50, "agriculture": 0.20, "industrial_metals": 0.20}),
    "PDBC": _profile("PDBC", "broad_commodities", {"broad_commodities": 1.0, "oil": 0.35, "agriculture": 0.25, "industrial_metals": 0.20}),
    "COM": _profile("COM", "broad_commodities", {"broad_commodities": 1.0}),
    "DJP": _profile("DJP", "broad_commodities", {"broad_commodities": 1.0}),
    "COMT": _profile("COMT", "broad_commodities", {"broad_commodities": 1.0}),
    "CPER": _profile("CPER", "copper", {"copper": 1.0, "industrial_metals": 0.85, "usd_inverse": 0.20}),
    "COPX": _profile("COPX", "miners_equity", {"copper": 0.85, "industrial_metals": 0.80, "miners_equity": 0.70, "equity_beta": 0.45}),
    "DBB": _profile("DBB", "industrial_metals", {"industrial_metals": 1.0, "copper": 0.35, "usd_inverse": 0.20}),
    "PICK": _profile("PICK", "miners_equity", {"industrial_metals": 0.75, "miners_equity": 0.80, "equity_beta": 0.45}),
    "XME": _profile("XME", "miners_equity", {"industrial_metals": 0.65, "miners_equity": 0.85, "equity_beta": 0.55}),
    "REMX": _profile("REMX", "battery_metals", {"battery_metals": 0.80, "industrial_metals": 0.50, "miners_equity": 0.70, "equity_beta": 0.45}),
    "FCX": _profile("FCX", "copper", {"copper": 0.85, "industrial_metals": 0.75, "miners_equity": 0.55, "equity_beta": 0.45}),
    "BHP": _profile("BHP", "miners_equity", {"industrial_metals": 0.70, "miners_equity": 0.75, "equity_beta": 0.45}),
    "RIO": _profile("RIO", "miners_equity", {"industrial_metals": 0.70, "miners_equity": 0.75, "equity_beta": 0.45}),
    "VALE": _profile("VALE", "miners_equity", {"industrial_metals": 0.70, "miners_equity": 0.75, "equity_beta": 0.50}),
    "AA": _profile("AA", "industrial_metals", {"industrial_metals": 0.80, "miners_equity": 0.50, "equity_beta": 0.45}),
    "CLF": _profile("CLF", "industrial_metals", {"industrial_metals": 0.80, "miners_equity": 0.50, "equity_beta": 0.55}),
    # Uranium and battery metals.
    "URA": _profile("URA", "uranium", {"uranium": 1.0, "miners_equity": 0.65, "equity_beta": 0.45}),
    "URNM": _profile("URNM", "uranium", {"uranium": 1.0, "miners_equity": 0.65, "equity_beta": 0.45}),
    "LIT": _profile("LIT", "battery_metals", {"battery_metals": 0.85, "equity_beta": 0.50}),
    "BATT": _profile("BATT", "battery_metals", {"battery_metals": 0.85, "equity_beta": 0.50}),
}


def unclassified_profile(symbol: str, source: str = "unclassified") -> RiskFactorProfile:
    return RiskFactorProfile(
        symbol=_norm_symbol(symbol),
        primary_factor="unclassified",
        exposures={},
        confidence=0.0,
        source=source,
        reasoning="No validated factor classification available",
    )


def validate_dynamic_profile(symbol: str, raw: Mapping[str, Any], source: str = "llm") -> RiskFactorProfile:
    sym = _norm_symbol(raw.get("symbol") or symbol)
    raw_exposures = raw.get("exposures") or {}
    if not isinstance(raw_exposures, Mapping):
        raw_exposures = {}

    exposures: dict[str, float] = {}
    for factor, weight in raw_exposures.items():
        canonical = canonical_factor(str(factor))
        if canonical is None:
            continue
        try:
            val = max(0.0, min(1.0, float(weight)))
        except (TypeError, ValueError):
            continue
        if val > 0:
            exposures[canonical] = max(exposures.get(canonical, 0.0), val)

    primary = canonical_factor(str(raw.get("primary_factor", "")))
    if primary is None and exposures:
        primary = max(exposures.items(), key=lambda item: item[1])[0]
    if primary and primary not in exposures:
        exposures[primary] = 1.0

    if not exposures or primary is None:
        return unclassified_profile(sym, source=source)

    try:
        confidence = max(0.0, min(1.0, float(raw.get("confidence", 0.5))))
    except (TypeError, ValueError):
        confidence = 0.5

    return RiskFactorProfile(
        symbol=sym,
        primary_factor=primary,
        exposures=exposures,
        confidence=confidence,
        source=source,
        reasoning=str(raw.get("reasoning", ""))[:500],
    )


def normalize_dynamic_profiles(dynamic_profiles: Any) -> dict[str, RiskFactorProfile]:
    if not dynamic_profiles:
        return {}
    items: list[Any]
    if isinstance(dynamic_profiles, Mapping):
        items = []
        for symbol, raw in dynamic_profiles.items():
            if isinstance(raw, RiskFactorProfile):
                items.append(raw)
            elif isinstance(raw, Mapping):
                enriched = dict(raw)
                enriched.setdefault("symbol", symbol)
                items.append(enriched)
    elif isinstance(dynamic_profiles, list):
        items = dynamic_profiles
    else:
        return {}

    profiles: dict[str, RiskFactorProfile] = {}
    for item in items:
        if isinstance(item, RiskFactorProfile):
            profiles[item.symbol] = item
        elif isinstance(item, Mapping):
            prof = validate_dynamic_profile(str(item.get("symbol", "")), item)
            profiles[prof.symbol] = prof
    return profiles


def classify_symbol(symbol: str, dynamic_profiles: Any = None) -> RiskFactorProfile:
    sym = _norm_symbol(symbol)
    dynamic = normalize_dynamic_profiles(dynamic_profiles)
    if sym in dynamic and dynamic[sym].confidence >= MIN_FACTOR_CONFIDENCE:
        return dynamic[sym]
    return STATIC_FACTOR_PROFILES.get(sym) or unclassified_profile(sym)


def _position_qty_price(position: Any) -> tuple[float, float]:
    if isinstance(position, Mapping):
        qty = float(position.get("qty", position.get("quantity", 0.0)) or 0.0)
        price = float(position.get("current_price", position.get("price", position.get("avg_entry", 0.0))) or 0.0)
        return qty, price
    qty = float(getattr(position, "qty", getattr(position, "quantity", 0.0)) or 0.0)
    price = float(getattr(position, "current_price", getattr(position, "price", 0.0)) or 0.0)
    return qty, price


def compute_factor_report(
    positions: Mapping[str, Any],
    nav: float,
    dynamic_profiles: Any = None,
    cash: float | None = None,
) -> dict[str, Any]:
    factor_notional: dict[str, float] = {}
    factor_symbols: dict[str, list[str]] = {}
    symbols: dict[str, dict[str, Any]] = {}
    unclassified: list[str] = []
    gross = 0.0

    for symbol, position in positions.items():
        qty, price = _position_qty_price(position)
        notional = abs(qty * price)
        if notional <= 0:
            continue
        gross += notional
        profile = classify_symbol(symbol, dynamic_profiles)
        if profile.primary_factor == "unclassified" or profile.confidence < MIN_FACTOR_CONFIDENCE:
            unclassified.append(_norm_symbol(symbol))
        for factor, weight in profile.exposures.items():
            factor_notional[factor] = factor_notional.get(factor, 0.0) + notional * weight
            factor_symbols.setdefault(factor, []).append(_norm_symbol(symbol))
        symbols[_norm_symbol(symbol)] = {
            "notional": round(notional, 4),
            "primary_factor": profile.primary_factor,
            "confidence": round(profile.confidence, 3),
            "source": profile.source,
            "exposures": dict(profile.exposures),
        }

    factor_rows: dict[str, dict[str, Any]] = {}
    breaches: list[str] = []
    for factor, notional in sorted(factor_notional.items(), key=lambda item: -item[1]):
        pct = notional / nav if nav > 0 else 0.0
        limit = factor_limit_pct(factor)
        breach = pct > limit
        if breach:
            breaches.append(f"{factor} {pct:.0%}>{limit:.0%}")
        factor_rows[factor] = {
            "notional": round(notional, 4),
            "pct_nav": round(pct, 4),
            "limit_pct": limit,
            "breach": breach,
            "symbols": sorted(set(factor_symbols.get(factor, []))),
        }

    gross_pct = gross / nav if nav > 0 else 0.0
    if gross_pct > MAX_GROSS_EXPOSURE_PCT:
        breaches.append(f"gross_exposure {gross_pct:.0%}>{MAX_GROSS_EXPOSURE_PCT:.0%}")
    if cash is not None and cash < -0.01:
        breaches.append(f"negative_cash ${cash:.2f}")

    return {
        "nav": round(nav, 4),
        "cash": round(cash, 4) if cash is not None else None,
        "gross_notional": round(gross, 4),
        "gross_exposure_pct": round(gross_pct, 4),
        "max_gross_exposure_pct": MAX_GROSS_EXPOSURE_PCT,
        "risk_mode": "reduce_only" if breaches and (gross_pct > MAX_GROSS_EXPOSURE_PCT or (cash is not None and cash < -0.01)) else "normal",
        "factors": factor_rows,
        "symbols": symbols,
        "unclassified_symbols": unclassified,
        "breaches": breaches,
    }


def projected_gross_notional(
    positions: Mapping[str, Any],
    symbol: str,
    side: Side,
    quantity: float,
    price: float,
) -> float:
    sym = _norm_symbol(symbol)
    current_total = 0.0
    existing_qty = 0.0
    for pos_symbol, position in positions.items():
        qty, px = _position_qty_price(position)
        if _norm_symbol(pos_symbol) == sym:
            existing_qty = qty
            px = price or px
        current_total += abs(qty * px)

    signed = quantity if side == Side.BUY else -quantity
    new_qty = existing_qty + signed
    old_notional = abs(existing_qty * price)
    new_notional = abs(new_qty * price)
    return current_total - old_notional + new_notional


def format_factor_report(report: Mapping[str, Any], max_rows: int = 8) -> str:
    factors = report.get("factors") or {}
    if not factors:
        return "No current factor exposure."
    lines = [
        f"Risk mode: {report.get('risk_mode', 'normal')}",
        f"Gross exposure: {float(report.get('gross_exposure_pct', 0.0)):.0%} of NAV",
    ]
    for factor, row in list(factors.items())[:max_rows]:
        status = "BREACH" if row.get("breach") else "ok"
        symbols = ", ".join(row.get("symbols", [])[:5])
        lines.append(
            f"- {factor}: {float(row.get('pct_nav', 0.0)):.0%} / {float(row.get('limit_pct', 0.0)):.0%} {status}"
            + (f" ({symbols})" if symbols else "")
        )
    if report.get("unclassified_symbols"):
        lines.append("Unclassified: " + ", ".join(report["unclassified_symbols"]))
    if report.get("breaches"):
        lines.append("Breaches: " + "; ".join(report["breaches"]))
    return "\n".join(lines)
