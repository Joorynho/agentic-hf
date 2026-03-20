"""Fetch 52-week high/low and 200-day MA for held positions."""
from __future__ import annotations
import logging
from typing import Callable, Any

logger = logging.getLogger(__name__)

_LOOKBACK_DAYS = 380   # > 1 year to ensure full 200-day MA window


def compute_multiframe(symbols: list[str], fetch_fn: Callable[[str, int], list[Any]]) -> dict[str, dict]:
    """
    fetch_fn(symbol, days) -> list[Bar]  (Bar has .close attribute)
    Returns {symbol: {high_52w, low_52w, ma_200, current, pct_from_ma}}
    """
    result = {}
    for sym in symbols:
        try:
            bars = fetch_fn(sym, _LOOKBACK_DAYS)
            if not bars or len(bars) < 20:
                continue
            closes = [float(b.close) for b in bars]
            current = closes[-1]
            window_252 = closes[-252:] if len(closes) >= 252 else closes
            high_52w = max(window_252)
            low_52w  = min(window_252)
            window_200 = closes[-200:] if len(closes) >= 200 else closes
            ma_200 = sum(window_200) / len(window_200)
            pct_from_ma = (current - ma_200) / ma_200 * 100 if ma_200 else 0.0
            result[sym] = {
                "high_52w":    round(high_52w, 2),
                "low_52w":     round(low_52w, 2),
                "ma_200":      round(ma_200, 2),
                "current":     round(current, 2),
                "pct_from_ma": round(pct_from_ma, 1),
            }
        except Exception as e:
            logger.debug("[multiframe] %s: %s", sym, e)
    return result


def format_multiframe_block(mf: dict[str, dict]) -> str:
    """Format for PM prompt injection."""
    if not mf:
        return ""
    lines = ["MULTI-TIMEFRAME CONTEXT (52-week range | 200-day MA):"]
    for sym, d in sorted(mf.items()):
        arrow = "▲" if d["pct_from_ma"] >= 0 else "▼"
        direction = "above" if d["pct_from_ma"] >= 0 else "below"
        lines.append(
            f"  {sym:<8} 52wH=${d['high_52w']}  52wL=${d['low_52w']}  "
            f"200dMA=${d['ma_200']}  Now=${d['current']}  "
            f"{arrow}{abs(d['pct_from_ma']):.1f}% {direction} MA"
        )
    return "\n".join(lines)
