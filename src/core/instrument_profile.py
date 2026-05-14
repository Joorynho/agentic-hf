from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Mapping

from src.core.config.universes import POD_UNIVERSES
from src.core.factor_exposure import STATIC_FACTOR_PROFILES, RiskFactorProfile, classify_symbol
from src.core.models.execution import InstrumentProfile


_NAMES = {
    "GLD": "SPDR Gold Shares ETF",
    "GDX": "VanEck Gold Miners ETF",
    "GDXJ": "VanEck Junior Gold Miners ETF",
    "USO": "United States Oil Fund",
    "XLE": "Energy Select Sector SPDR ETF",
    "TLT": "iShares 20+ Year Treasury Bond ETF",
    "UUP": "Invesco DB US Dollar Index Bullish Fund",
    "USDU": "WisdomTree Bloomberg US Dollar Bullish Fund",
    "FXE": "Invesco CurrencyShares Euro ETF",
    "BTC/USD": "Bitcoin",
    "ETH/USD": "Ethereum",
    "SOL/USD": "Solana",
    "AVAX/USD": "Avalanche",
    "LTC/USD": "Litecoin",
}


_EXTRA_LOADINGS: dict[str, dict[str, float]] = {
    "TLT": {"duration": 1.0, "real_rates": 0.75, "growth_scare": 0.45, "usd": 0.10},
    "IEF": {"duration": 0.75, "real_rates": 0.55, "growth_scare": 0.35},
    "SHY": {"front_end_rates": 0.85, "usd": 0.20},
    "UUP": {"usd": 1.0, "rate_differential": 0.55, "risk_off_usd": 0.35},
    "USDU": {"usd": 1.0, "rate_differential": 0.55, "risk_off_usd": 0.35},
    "FXE": {"eur_usd": 1.0, "usd_inverse": 0.85, "ecb_policy": 0.55},
    "FXY": {"jpy_usd": 1.0, "usd_inverse": 0.75, "boj_policy": 0.55, "risk_off_jpy": 0.35},
    "BTC/USD": {"crypto_beta": 1.0, "liquidity": 0.65, "risk_appetite": 0.55},
    "ETH/USD": {"crypto_beta": 0.90, "liquidity": 0.60, "smart_contracts": 1.0, "onchain_activity": 0.70},
    "SOL/USD": {"crypto_beta": 0.85, "liquidity": 0.55, "altcoin_beta": 0.85, "onchain_activity": 0.75},
    "AVAX/USD": {"crypto_beta": 0.80, "liquidity": 0.50, "altcoin_beta": 0.80, "onchain_activity": 0.65},
    "LTC/USD": {"crypto_beta": 0.55, "liquidity": 0.45, "payment_crypto": 0.70},
    "XLF": {"equity_beta": 0.75, "financials": 1.0, "rates": 0.45, "credit": 0.35},
    "SHEL": {"energy_equities": 0.85, "oil": 0.65, "equity_beta": 0.45},
    "EOG": {"energy_equities": 0.90, "oil": 0.75, "equity_beta": 0.45},
}


_ROLES = {
    "gold_beta": "direct gold exposure / real-yield hedge",
    "miners_equity": "levered metals exposure with equity and operating beta",
    "oil": "direct oil-price exposure",
    "energy_equities": "energy equity exposure with oil beta and broad equity beta",
    "duration": "rates/duration exposure",
    "usd": "US dollar exposure",
    "crypto_beta": "broad crypto risk exposure",
    "altcoin_beta": "higher-beta crypto ecosystem exposure",
}


def _norm(symbol: str) -> str:
    return str(symbol or "").strip().upper()


def _pod_for_symbol(symbol: str) -> str:
    sym = _norm(symbol)
    for pod_id, universe in POD_UNIVERSES.items():
        if sym in {_norm(s) for s in universe}:
            return pod_id
    if "/" in sym:
        return "crypto"
    return "equities"


def _asset_class(symbol: str) -> str:
    pod = _pod_for_symbol(symbol)
    if pod == "fx":
        return "fx"
    if pod == "crypto":
        return "crypto"
    if pod == "commodities":
        return "commodity"
    return "equity"


def _profile_from_risk(symbol: str, risk_profile: RiskFactorProfile) -> InstrumentProfile:
    sym = _norm(symbol)
    loadings = dict(risk_profile.exposures or {})
    loadings.update(_EXTRA_LOADINGS.get(sym, {}))
    primary = risk_profile.primary_factor
    if primary == "unclassified" and sym in _EXTRA_LOADINGS:
        primary = max(_EXTRA_LOADINGS[sym].items(), key=lambda item: item[1])[0]
    role = _ROLES.get(primary, "")
    if not role and loadings:
        role = _ROLES.get(max(loadings.items(), key=lambda item: item[1])[0], "")
    return InstrumentProfile(
        symbol=sym,
        name=_NAMES.get(sym, sym),
        asset_class=_asset_class(sym),
        tradable=True,
        broker_symbol=sym,
        primary_factor=primary,
        factor_loadings=loadings,
        instrument_role=role,
        liquidity_notes="Use live price/broker checks before sizing.",
        cost_notes="Use market order/slippage diagnostics from execution quality.",
        known_risks=_known_risks(primary, loadings),
        substitutes=[],
        preferred_when=_preferred_when(primary, loadings),
        avoid_when=_avoid_when(primary, loadings),
        last_reviewed_at=datetime.now(timezone.utc),
        source=risk_profile.source,
    )


def _known_risks(primary: str, loadings: Mapping[str, float]) -> list[str]:
    risks: list[str] = []
    factors = set(loadings)
    if "real_rates" in factors:
        risks.append("Rising real yields can pressure the thesis.")
    if "usd_inverse" in factors:
        risks.append("A stronger USD can offset commodity or precious-metals upside.")
    if "equity_beta" in factors:
        risks.append("Broad equity drawdowns can dominate asset-specific drivers.")
    if "crypto_beta" in factors:
        risks.append("Liquidity and risk-appetite shocks can dominate token-specific catalysts.")
    if primary == "miners_equity":
        risks.append("Miner equities are not pure metal exposure; margins, equities, and operating risk matter.")
    return risks[:6]


def _preferred_when(primary: str, loadings: Mapping[str, float]) -> list[str]:
    if primary in {"gold_beta", "miners_equity"}:
        return ["gold thesis is supported by stable/falling real yields", "USD is not aggressively strengthening"]
    if primary in {"oil", "energy_equities"}:
        return ["oil supply/demand catalyst is active", "energy beta is desired versus direct commodity exposure"]
    if primary in {"duration", "real_rates"}:
        return ["growth scare or falling yields are part of the thesis"]
    if primary in {"crypto_beta", "altcoin_beta"}:
        return ["liquidity/risk appetite is supportive", "on-chain or flow evidence confirms the catalyst"]
    return []


def _avoid_when(primary: str, loadings: Mapping[str, float]) -> list[str]:
    avoid: list[str] = []
    if "equity_beta" in loadings:
        avoid.append("avoid if the desired expression should be isolated from broad equity beta")
    if "crypto_beta" in loadings:
        avoid.append("avoid if the thesis cannot tolerate broad crypto beta drawdowns")
    if "usd_inverse" in loadings:
        avoid.append("avoid if USD strength is the dominant market response")
    return avoid


def get_instrument_profile(symbol: str, dynamic_profiles: Any = None) -> InstrumentProfile:
    risk_profile = classify_symbol(symbol, dynamic_profiles)
    return _profile_from_risk(symbol, risk_profile)


def all_instrument_profiles(dynamic_profiles: Any = None) -> dict[str, InstrumentProfile]:
    symbols = set(STATIC_FACTOR_PROFILES) | set(_EXTRA_LOADINGS)
    for universe in POD_UNIVERSES.values():
        symbols.update(_norm(symbol) for symbol in universe)
    profiles = {symbol: get_instrument_profile(symbol, dynamic_profiles) for symbol in sorted(symbols)}
    for symbol, profile in list(profiles.items()):
        substitutes = [
            other for other, other_profile in profiles.items()
            if other != symbol and other_profile.primary_factor == profile.primary_factor
        ][:8]
        profiles[symbol] = profile.model_copy(update={"substitutes": substitutes})
    return profiles


def profiles_for_factor(factor: str, dynamic_profiles: Any = None, limit: int = 20) -> list[dict]:
    needle = str(factor or "").strip().lower()
    rows = []
    for profile in all_instrument_profiles(dynamic_profiles).values():
        if profile.primary_factor.lower() == needle or needle in {k.lower() for k in profile.factor_loadings}:
            rows.append(profile.model_dump(mode="json"))
    return rows[: max(1, min(int(limit or 20), 100))]


def profiles_for_pod(pod_id: str, dynamic_profiles: Any = None) -> list[dict]:
    pod = str(pod_id or "").strip().lower()
    universe = {_norm(symbol) for symbol in POD_UNIVERSES.get(pod, [])}
    return [
        profile.model_dump(mode="json")
        for symbol, profile in all_instrument_profiles(dynamic_profiles).items()
        if symbol in universe or _pod_for_symbol(symbol) == pod
    ]


def profiles_for_catalyst(event: Mapping[str, Any], dynamic_profiles: Any = None, limit: int = 20) -> list[dict]:
    symbols = {_norm(s) for s in event.get("affected_symbols") or []}
    factors = {str(f).lower() for f in event.get("factors") or []}
    rows = []
    for profile in all_instrument_profiles(dynamic_profiles).values():
        loadings = {k.lower() for k in profile.factor_loadings}
        if profile.symbol in symbols or factors.intersection(loadings) or profile.primary_factor.lower() in factors:
            rows.append(profile.model_dump(mode="json"))
    return rows[: max(1, min(int(limit or 20), 100))]
