"""Alpaca paper trading adapter — fetches real-time data and executes orders."""
from __future__ import annotations

import asyncio
import ast
import json
import logging
import math
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
from alpaca_trade_api import REST, TimeFrame
from alpaca_trade_api.rest import TimeFrameUnit
import pandas as pd

from src.core.models.market import Bar

# Always load .env from project root, regardless of working directory
load_dotenv(Path(__file__).resolve().parent.parent.parent.parent / ".env")

logger = logging.getLogger(__name__)

# Alpaca endpoints
ALPACA_PAPER_URL = "https://paper-api.alpaca.markets"  # Paper trading
ALPACA_DATA_URL = "https://data.alpaca.markets"  # Market data (free tier)


class AlpacaAdapter:
    """Connect to Alpaca paper trading for real-time data and order execution."""

    def __init__(
        self,
        api_key: str | None = None,
        secret_key: str | None = None,
        paper: bool = True,
    ):
        """Initialize Alpaca adapter.

        Args:
            api_key: Alpaca API key (defaults to ALPACA_API_KEY env var)
            secret_key: Alpaca secret key (defaults to ALPACA_SECRET_KEY env var)
            paper: Use paper trading endpoint (default True)
        """
        api_key = api_key or os.getenv("ALPACA_API_KEY", "")
        secret_key = secret_key or os.getenv("ALPACA_SECRET_KEY", "")

        if not api_key or not secret_key:
            raise ValueError("ALPACA_API_KEY and ALPACA_SECRET_KEY required in .env")

        self._api_key = api_key
        self._secret_key = secret_key
        self._paper = paper
        self._asset_cache: dict[str, dict] = {}

        # REST client for trading + historical data
        self._client = REST(
            key_id=api_key,
            secret_key=secret_key,
            base_url=ALPACA_PAPER_URL if paper else "https://api.alpaca.markets",
            api_version="v2",
        )
        logger.info("[alpaca] Connected to %s", "paper" if paper else "live")

    def _sync_fetch_account(self) -> dict:
        """Synchronous account fetch — called via to_thread."""
        account = self._client.get_account()
        return {
            "equity": float(account.equity),
            "cash": float(account.cash),
            "buying_power": float(account.buying_power),
            "position_count": len(self._client.list_positions()),
        }

    async def fetch_account(self) -> dict:
        """Fetch account info (NAV, buying power, positions).

        Returns:
            dict with keys: equity, cash, buying_power, etc.
        """
        try:
            return await asyncio.to_thread(self._sync_fetch_account)
        except Exception as exc:
            logger.error("[alpaca] fetch_account failed: %s", exc)
            raise

    @staticmethod
    def _is_crypto_symbol(symbol: str) -> bool:
        """Return True if symbol looks like an Alpaca crypto pair."""
        if "/" not in symbol:
            return False
        quote = symbol.upper().rsplit("/", 1)[-1]
        return quote in {"USD", "USDT", "USDC", "BTC"}

    @staticmethod
    def _clean_error_message(exc: Exception) -> str:
        """Return a readable broker error string for logs and dashboard display."""
        message = str(exc).strip()
        if message.lower() in {"", "order rejected", "rejected"}:
            response = getattr(exc, "response", None)
            response_text = getattr(response, "text", None)
            if response_text:
                try:
                    payload = json.loads(response_text)
                    if payload.get("message"):
                        return str(payload["message"])
                except Exception:
                    pass
            raw_error = getattr(exc, "_error", None)
            if isinstance(raw_error, dict) and raw_error.get("message"):
                return str(raw_error["message"])
            if isinstance(raw_error, str):
                try:
                    payload = ast.literal_eval(raw_error)
                    if isinstance(payload, dict) and payload.get("message"):
                        return str(payload["message"])
                except Exception:
                    pass
        if not message:
            message = exc.__class__.__name__
        return " ".join(message.split())

    @staticmethod
    def _order_rejection_reason(order_status) -> str | None:
        """Extract the best available rejection detail from an Alpaca order object."""
        for attr in ("reason", "reject_reason", "rejected_reason", "failed_reason"):
            value = getattr(order_status, attr, None)
            if value:
                return str(value)
        status = getattr(order_status, "status", None)
        if status:
            return f"Alpaca order status: {status}"
        return None

    @staticmethod
    def _asset_value(asset, *names: str):
        """Read an Alpaca asset attribute across object/dict/raw payload forms."""
        if isinstance(asset, dict):
            for name in names:
                if name in asset:
                    return asset[name]
        raw = getattr(asset, "_raw", None)
        if isinstance(raw, dict):
            for name in names:
                if name in raw:
                    return raw[name]
        for name in names:
            value = getattr(asset, name, None)
            if value is not None:
                return value
        return None

    @staticmethod
    def _as_bool(value, default: bool = False) -> bool:
        if value is None:
            return default
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            return value.strip().lower() in {"true", "1", "yes", "y"}
        return bool(value)

    @staticmethod
    def _rejected_order_result(
        symbol: str,
        qty: float,
        side: str,
        reason: str,
        order_id: str | None = None,
        broker_status: str | None = None,
        stage: str = "broker_submit",
        reason_code: str | None = None,
    ) -> dict:
        """Build a rejected order payload while preserving the broker reason."""
        return {
            "order_id": order_id,
            "symbol": symbol,
            "qty": qty,
            "side": side,
            "status": "REJECTED",
            "filled_qty": 0.0,
            "filled_avg_price": None,
            "filled_at": None,
            "reason": reason,
            "rejection_reason": reason,
            "rejection_detail": reason,
            "broker_status": broker_status,
            "stage": stage,
            "reason_code": reason_code,
        }

    def _asset_capability_from_asset(self, symbol: str, asset) -> dict:
        """Normalize Alpaca asset metadata into a stable preflight shape."""
        asset_class = self._asset_value(asset, "asset_class", "class") or ""
        status = self._asset_value(asset, "status") or ""
        is_crypto = self._is_crypto_symbol(symbol) or str(asset_class).lower() == "crypto"
        return {
            "symbol": str(self._asset_value(asset, "symbol") or symbol).upper(),
            "asset_class": str(asset_class).lower(),
            "status": str(status).lower(),
            "tradable": self._as_bool(self._asset_value(asset, "tradable"), default=True),
            "fractionable": self._as_bool(
                self._asset_value(asset, "fractionable"),
                default=is_crypto,
            ),
            "shortable": self._as_bool(self._asset_value(asset, "shortable"), default=False),
            "is_crypto": is_crypto,
        }

    async def get_asset_capability(self, symbol: str) -> dict:
        """Return cached Alpaca tradability metadata for a symbol."""
        key = symbol.upper()
        cached = self._asset_cache.get(key)
        if cached:
            return dict(cached)
        asset = await asyncio.to_thread(self._client.get_asset, key)
        capability = self._asset_capability_from_asset(key, asset)
        self._asset_cache[key] = capability
        return dict(capability)

    def _sync_position_qty(self, symbol: str) -> float:
        """Return signed held quantity if Alpaca has a position, else 0."""
        try:
            pos = self._client.get_position(symbol)
            qty = abs(float(getattr(pos, "qty", 0.0) or 0.0))
            return qty if getattr(pos, "side", "long") == "long" else -qty
        except Exception:
            return 0.0

    async def _preflight_order(
        self,
        symbol: str,
        qty: float,
        side: str,
        order_type: str,
        limit_price: float | None = None,
        estimated_price: float | None = None,
    ) -> dict | None:
        """Return a rejected payload when an order is non-executable before submit."""
        symbol_key = symbol.upper()
        side = side.lower()
        order_type = order_type.lower()

        def reject(reason: str, reason_code: str) -> dict:
            logger.warning("[alpaca] Preflight rejected %s %s %s: %s", side, qty, symbol, reason)
            return self._rejected_order_result(
                symbol,
                qty,
                side,
                reason,
                stage="preflight",
                reason_code=reason_code,
            )

        if qty <= 0:
            return reject("Quantity must be greater than zero", "invalid_quantity")
        if side not in {"buy", "sell"}:
            return reject(f"Unsupported side '{side}'", "invalid_side")
        if order_type not in {"market", "limit"}:
            return reject(f"Unsupported order type '{order_type}'", "invalid_order_type")
        if order_type == "limit" and (limit_price is None or limit_price <= 0):
            return reject("Limit orders require a positive limit price", "invalid_limit_price")

        try:
            asset = await self.get_asset_capability(symbol_key)
        except Exception as exc:
            return reject(
                f"Asset capability lookup failed for {symbol}: {self._clean_error_message(exc)}",
                "asset_lookup_failed",
            )

        status = asset.get("status")
        if status and status != "active":
            return reject(f"Asset {symbol} is not active in Alpaca (status={status})", "asset_not_active")
        if asset.get("tradable") is False:
            return reject(f"Asset {symbol} is not tradable in Alpaca", "asset_not_tradable")

        is_crypto = bool(asset.get("is_crypto"))
        time_in_force = "gtc" if is_crypto else "day"
        if is_crypto and time_in_force not in {"gtc", "ioc"}:
            return reject("Crypto orders must use GTC or IOC time-in-force", "invalid_crypto_tif")

        if side == "buy" and not is_crypto and qty != int(qty) and not asset.get("fractionable"):
            return reject(f"Asset {symbol} does not support fractional buying", "asset_not_fractionable")

        if side == "sell":
            held_qty = self._sync_position_qty(symbol)
            long_qty = max(held_qty, 0.0)
            excess_short_qty = max(qty - long_qty, 0.0)
            if excess_short_qty > 0:
                if is_crypto:
                    return reject("Alpaca crypto short selling is not supported", "crypto_short_not_supported")
                if not asset.get("shortable"):
                    return reject(f"Asset {symbol} is not shortable in Alpaca", "asset_not_shortable")
                if excess_short_qty != int(excess_short_qty):
                    return reject("Fractional short selling is not supported", "fractional_short_not_supported")

        price = limit_price if limit_price and limit_price > 0 else estimated_price
        if side == "buy" and price and price > 0:
            required_notional = float(qty) * float(price)
            try:
                account = await asyncio.to_thread(self._client.get_account)
                buying_power = float(getattr(account, "buying_power", 0.0) or 0.0)
                if required_notional > buying_power + 1e-6:
                    return reject(
                        f"Insufficient Alpaca buying power (${buying_power:.2f} available, ${required_notional:.2f} required)",
                        "insufficient_buying_power",
                    )
            except Exception as exc:
                return reject(
                    f"Buying power check failed: {self._clean_error_message(exc)}",
                    "buying_power_lookup_failed",
                )

        return None

    def _barset_to_bar_list(
        self, barset, symbols: list[str], source: str = "alpaca"
    ) -> dict[str, list[Bar]]:
        """Convert Alpaca BarsV2 or dict mock to dict[symbol] -> list[Bar]."""
        results = {s: [] for s in symbols}
        if hasattr(barset, "df") and not barset.df.empty:
            df = barset.df
            for symbol in symbols:
                if "symbol" in df.columns:
                    sym_df = df[df["symbol"] == symbol]
                else:
                    sym_df = df
                for idx, row in sym_df.iterrows():
                    ts = idx.to_pydatetime() if hasattr(idx, "to_pydatetime") else idx
                    vol = row.get("volume", 0)
                    results[symbol].append(
                        Bar(
                            symbol=symbol,
                            timestamp=ts,
                            open=float(row["open"]),
                            high=float(row["high"]),
                            low=float(row["low"]),
                            close=float(row["close"]),
                            volume=float(vol) if vol is not None else 0.0,
                            source=source,
                        )
                    )
        elif isinstance(barset, dict):
            for symbol in symbols:
                if symbol in barset:
                    df = barset[symbol]
                    for idx, row in df.iterrows():
                        ts = idx.to_pydatetime() if hasattr(idx, "to_pydatetime") else idx
                        vol = row.get("volume", row.get("v", 0))
                        results[symbol].append(
                            Bar(
                                symbol=symbol,
                                timestamp=ts,
                                open=float(row["open"]),
                                high=float(row["high"]),
                                low=float(row["low"]),
                                close=float(row["close"]),
                                volume=float(vol) if vol is not None else 0.0,
                                source=source,
                            )
                        )
        return results

    @staticmethod
    def _positive_float(value) -> float | None:
        try:
            price = float(value)
        except Exception:
            return None
        return price if math.isfinite(price) and price > 0 else None

    @staticmethod
    def _entity_for_symbol(rows, symbol: str):
        if not rows:
            return None
        aliases = {
            symbol,
            symbol.upper(),
            symbol.replace("/", ""),
            symbol.replace("/", "").upper(),
            symbol.replace("/", "-"),
            symbol.replace("/", "-").upper(),
        }
        for alias in aliases:
            try:
                if alias in rows:
                    return rows[alias]
            except Exception:
                pass
        return None

    @classmethod
    def _price_from_crypto_snapshot(cls, snapshot) -> float | None:
        if not snapshot:
            return None

        latest_trade = getattr(snapshot, "latest_trade", None)
        price = cls._positive_float(getattr(latest_trade, "price", None))
        if price is not None:
            return price

        latest_quote = getattr(snapshot, "latest_quote", None)
        bid = cls._positive_float(getattr(latest_quote, "bid_price", None))
        ask = cls._positive_float(getattr(latest_quote, "ask_price", None))
        if bid is not None and ask is not None:
            return (bid + ask) / 2.0

        for attr in ("minute_bar", "daily_bar", "prev_daily_bar"):
            bar = getattr(snapshot, attr, None)
            price = cls._positive_float(getattr(bar, "close", None))
            if price is not None:
                return price
        return None

    async def fetch_crypto_quotes(self, symbols: list[str]) -> dict[str, dict]:
        """Fetch latest crypto marks from Alpaca market data."""
        crypto_symbols = [s for s in symbols if self._is_crypto_symbol(s)]
        if not crypto_symbols:
            return {}

        results: dict[str, dict] = {}
        try:
            snapshots = await asyncio.to_thread(
                self._client.get_crypto_snapshots, crypto_symbols, loc="us"
            )
        except Exception as exc:
            logger.debug("[alpaca] get_crypto_snapshots failed: %s", exc)
            snapshots = {}

        for symbol in crypto_symbols:
            snapshot = self._entity_for_symbol(snapshots, symbol)
            price = self._price_from_crypto_snapshot(snapshot)
            if price is not None:
                results[symbol] = {
                    "symbol": symbol,
                    "name": symbol.split("/", 1)[0],
                    "price": price,
                    "change_amount": 0.0,
                    "change_pct": 0.0,
                    "source": "alpaca_crypto_snapshot",
                }

        missing = [s for s in crypto_symbols if s not in results]
        if missing:
            try:
                trades = await asyncio.to_thread(
                    self._client.get_latest_crypto_trades, missing, loc="us"
                )
            except Exception as exc:
                logger.debug("[alpaca] get_latest_crypto_trades failed: %s", exc)
                trades = {}
            for symbol in missing:
                trade = self._entity_for_symbol(trades, symbol)
                price = self._positive_float(getattr(trade, "price", None))
                if price is not None:
                    results[symbol] = {
                        "symbol": symbol,
                        "name": symbol.split("/", 1)[0],
                        "price": price,
                        "change_amount": 0.0,
                        "change_pct": 0.0,
                        "source": "alpaca_crypto_trade",
                    }

        logger.debug("[alpaca] fetch_crypto_quotes: %d/%d symbols", len(results), len(crypto_symbols))
        return results

    async def fetch_bars(
        self,
        symbols: list[str],
        timeframe: str = "1Min",
        limit: int = 1000,
    ) -> dict[str, list[Bar]]:
        """Fetch latest bars for symbols.

        Supports both equity tickers (e.g., AAPL, SPY) and crypto pairs (e.g., BTC/USD).
        Routes crypto symbols to get_crypto_bars and equities to get_bars.

        Args:
            symbols: List of tickers (e.g., ['AAPL', 'MSFT', 'BTC/USD'])
            timeframe: '1Min', '5Min', '15Min', '1H', '1D' (default '1Min')
            limit: Max bars per symbol (default 1000, max 10000)

        Returns:
            dict[symbol] -> list[Bar] ordered by timestamp ascending
        """
        results: dict[str, list[Bar]] = {s: [] for s in symbols}
        if not symbols:
            return results

        try:
            tf_map = {
                "1Min": TimeFrame.Minute,
                "5Min": TimeFrame(5, TimeFrameUnit.Minute),
                "15Min": TimeFrame(15, TimeFrameUnit.Minute),
                "1H": TimeFrame.Hour,
                "1D": TimeFrame.Day,
            }
            tf = tf_map.get(timeframe, TimeFrame.Minute)

            stock_symbols = [s for s in symbols if not self._is_crypto_symbol(s)]
            crypto_symbols = [s for s in symbols if self._is_crypto_symbol(s)]

            if stock_symbols:
                barset = await asyncio.to_thread(
                    self._client.get_bars, stock_symbols, timeframe=tf, limit=limit
                )
                stock_bars = self._barset_to_bar_list(barset, stock_symbols, source="alpaca")
                for k, v in stock_bars.items():
                    results[k] = v

            if crypto_symbols:
                crypto_barset = await asyncio.to_thread(
                    self._client.get_crypto_bars, crypto_symbols, timeframe=tf, limit=limit, loc="us"
                )
                crypto_bars = self._barset_to_bar_list(
                    crypto_barset, crypto_symbols, source="alpaca"
                )
                for k, v in crypto_bars.items():
                    results[k] = v

            logger.debug(
                "[alpaca] fetch_bars: %d symbols (%d equity, %d crypto), %s timeframe",
                len(symbols),
                len(stock_symbols),
                len(crypto_symbols),
                timeframe,
            )
            return results

        except Exception as exc:
            logger.error("[alpaca] fetch_bars failed: %s", exc)
            raise

    async def place_order(
        self,
        symbol: str,
        qty: float,
        side: str,  # "buy" or "sell"
        order_type: str = "market",
        limit_price: Optional[float] = None,
        estimated_price: Optional[float] = None,
        timeout_seconds: int = 30,
        max_retries: int = 3,
    ) -> dict:
        """Place an order with fill polling and retry on transient errors.

        Args:
            symbol: Ticker (e.g., 'AAPL')
            qty: Quantity (positive float)
            side: 'buy' or 'sell'
            order_type: 'market' or 'limit' (default 'market')
            limit_price: Required if order_type='limit'
            timeout_seconds: Max seconds to wait for fill (default 30)
            max_retries: Max submit attempts on transient errors (default 3)

        Returns:
            dict with keys: order_id, symbol, qty, side, status, filled_qty, filled_avg_price, filled_at
            - status: "FILLED" | "PARTIAL" | "PENDING" | "REJECTED"
            - filled_at: timestamp if filled, else None
        """
        try:
            side = side.lower()
            order_type = order_type.lower()
            preflight_rejection = await self._preflight_order(
                symbol,
                qty,
                side,
                order_type,
                limit_price=limit_price,
                estimated_price=estimated_price,
            )
            if preflight_rejection:
                return preflight_rejection

            # Alpaca does not support fractional short sells -- round to whole shares
            if side == "sell" and qty != int(qty):
                try:
                    pos = self._client.get_position(symbol)
                    held_qty = float(pos.qty) if pos.side == "long" else 0.0
                except Exception:
                    held_qty = 0.0
                if held_qty <= 0:
                    import math
                    whole_qty = math.floor(qty)
                    if whole_qty < 1:
                        reason = f"Fractional short sell quantity {qty:.4f} rounds to 0 whole shares"
                        logger.info("[alpaca] Skipping short sell %s: %s", symbol, reason)
                        return self._rejected_order_result(
                            symbol,
                            qty,
                            side,
                            reason,
                            stage="preflight",
                            reason_code="fractional_short_rounds_to_zero",
                        )
                    logger.info("[alpaca] Rounded short sell %s: %.4f -> %d (whole shares required)", symbol, qty, whole_qty)
                    qty = float(whole_qty)

            # Submit order with retry on transient network errors
            order = None
            last_submit_err = None
            time_in_force = "gtc" if self._is_crypto_symbol(symbol) else "day"
            for attempt in range(max_retries):
                try:
                    order = self._client.submit_order(
                        symbol=symbol,
                        qty=qty,
                        side=side,
                        type=order_type,
                        time_in_force=time_in_force,
                        limit_price=limit_price if order_type == "limit" else None,
                    )
                    break
                except Exception as exc:
                    err_msg = str(exc).lower()
                    if "insufficient" in err_msg or "invalid" in err_msg or "forbidden" in err_msg:
                        raise
                    last_submit_err = exc
                    if attempt < max_retries - 1:
                        wait = 2 ** attempt
                        logger.warning(
                            "[alpaca] Order submit attempt %d/%d failed, retrying in %ds: %s",
                            attempt + 1, max_retries, wait, exc,
                        )
                        await asyncio.sleep(wait)
                    else:
                        raise last_submit_err

            logger.info(
                "[alpaca] Order placed: %s %s %s@%s (id=%s)",
                side,
                qty,
                symbol,
                "market" if order_type == "market" else f"${limit_price}",
                order.id,
            )

            # Poll for fill (up to timeout_seconds)
            filled_at = None
            for i in range(timeout_seconds):
                # Check current order status
                order_status = self._client.get_order(order.id)
                broker_status = str(getattr(order_status, "status", "") or "").lower()
                if broker_status in {"rejected", "canceled", "expired"}:
                    reason = self._order_rejection_reason(order_status) or f"Alpaca order status: {broker_status}"
                    logger.warning(
                        "[alpaca] Order rejected: %s %s %s (id=%s, reason=%s)",
                        side,
                        qty,
                        symbol,
                        order.id,
                        reason,
                    )
                    return self._rejected_order_result(
                        symbol,
                        qty,
                        side,
                        reason,
                        order_id=order.id,
                        broker_status=broker_status.upper(),
                        stage="broker_status",
                    )

                if order_status.filled_qty and float(order_status.filled_qty) > 0:
                    filled_at = datetime.now(timezone.utc)
                    fill_price = (
                        float(order_status.filled_avg_price)
                        if order_status.filled_avg_price
                        else float(order_status.limit_price) if order_status.limit_price else None
                    )
                    filled_qty = float(order_status.filled_qty)

                    result_status = (
                        "FILLED" if filled_qty >= qty
                        else "PARTIAL"
                    )

                    result = {
                        "order_id": order.id,
                        "symbol": order.symbol,
                        "qty": qty,
                        "side": side,
                        "status": result_status,
                        "filled_qty": filled_qty,
                        "filled_avg_price": fill_price,
                        "filled_at": filled_at,
                        "stage": "broker_fill",
                    }

                    logger.info(
                        "[alpaca] Order %s: %s %.2f @ $%.2f (id=%s)",
                        result_status,
                        symbol,
                        filled_qty,
                        fill_price or 0.0,
                        order.id,
                    )
                    return result

                # Wait before next poll (except on last iteration)
                if i < timeout_seconds - 1:
                    await asyncio.sleep(1)

            # Timeout reached — return PENDING with current status
            logger.warning(
                "[alpaca] Order %s did not fill within %d seconds (id=%s)",
                symbol,
                timeout_seconds,
                order.id,
            )
            result = {
                "order_id": order.id,
                "symbol": symbol,
                "qty": qty,
                "side": side,
                "status": "PENDING",
                "filled_qty": float(order.filled_qty) if order.filled_qty else 0.0,
                "filled_avg_price": None,
                "filled_at": None,
                "stage": "broker_poll",
            }
            return result

        except Exception as exc:
            reason = self._clean_error_message(exc)
            logger.error("[alpaca] place_order failed: %s", reason)
            return self._rejected_order_result(symbol, qty, side, reason, stage="broker_submit")

    def _sync_list_positions(self) -> list:
        """Synchronous call to Alpaca list_positions — called via to_thread."""
        return self._client.list_positions()

    async def get_open_positions(self) -> dict[str, dict]:
        """Get all open positions.

        Returns:
            dict[symbol] -> {qty, entry_price, current_price, unrealized_pl}
        """
        try:
            positions = await asyncio.to_thread(self._sync_list_positions)
            result = {}
            for pos in positions:
                result[pos.symbol] = {
                    "qty": float(pos.qty),
                    "side": pos.side,  # "long" or "short"
                    "entry_price": float(pos.avg_entry_price),
                    "current_price": float(pos.current_price),
                    "unrealized_pl": float(pos.unrealized_pl),
                    "unrealized_pl_pct": float(pos.unrealized_plpc),
                }
            logger.debug("[alpaca] get_open_positions: %d positions", len(result))
            return result
        except Exception as exc:
            logger.error("[alpaca] get_open_positions failed: %s", exc)
            raise

    async def get_order_status(self, order_id: str) -> dict:
        """Check status of an order.

        Returns:
            dict with keys: status, filled_qty, filled_avg_price
        """
        try:
            order = await asyncio.to_thread(self._client.get_order, order_id)
            return {
                "status": order.status,
                "symbol": getattr(order, "symbol", None),
                "side": getattr(order, "side", None),
                "qty": float(order.qty) if getattr(order, "qty", None) else 0.0,
                "filled_qty": float(order.filled_qty) if order.filled_qty else 0.0,
                "filled_avg_price": float(order.filled_avg_price)
                if order.filled_avg_price
                else None,
                "submitted_at": getattr(order, "submitted_at", None),
                "reason": self._order_rejection_reason(order),
            }
        except Exception as exc:
            logger.error("[alpaca] get_order_status failed for %s: %s", order_id, exc)
            raise

    async def close_position(self, symbol: str) -> dict:
        """Liquidate entire position in symbol.

        Returns:
            dict with order info from place_order
        """
        try:
            position = self._client.get_position(symbol)
            side = "sell" if position.side == "long" else "buy"
            qty = abs(float(position.qty))
            return await self.place_order(symbol, qty, side, order_type="market")
        except Exception as exc:
            logger.error("[alpaca] close_position failed for %s: %s", symbol, exc)
            raise

    async def get_earliest_buy_dates(self) -> dict[str, str]:
        """Fetch order history and return earliest fill date per symbol.

        Returns:
            dict[symbol] -> ISO date string of earliest filled BUY order.
        """
        try:
            orders = self._client.list_orders(status="closed", limit=500, direction="asc")
            earliest: dict[str, str] = {}
            for o in orders:
                if o.side != "buy" or not o.filled_at:
                    continue
                sym = o.symbol
                fill_ts = str(o.filled_at)
                if sym not in earliest or fill_ts < earliest[sym]:
                    earliest[sym] = fill_ts
            logger.info("[alpaca] Found earliest buy dates for %d symbols", len(earliest))
            return earliest
        except Exception as exc:
            logger.warning("[alpaca] get_earliest_buy_dates failed (non-fatal): %s", exc)
            return {}

    async def close_all_positions(self) -> list[dict]:
        """Liquidate all positions.

        Returns:
            list of order dicts from place_order
        """
        try:
            positions = self._client.list_positions()
            orders = []
            for pos in positions:
                order = await self.close_position(pos.symbol)
                orders.append(order)
            logger.info("[alpaca] Closed %d positions", len(orders))
            return orders
        except Exception as exc:
            logger.error("[alpaca] close_all_positions failed: %s", exc)
            raise

    async def cancel_order(self, order_id: str) -> bool:
        """Cancel an open order by ID. Returns True if cancelled successfully."""
        try:
            self._client.cancel_order(order_id)
            logger.info("[alpaca] Cancelled order %s", order_id)
            return True
        except Exception as exc:
            logger.warning("[alpaca] cancel_order failed for %s: %s", order_id, exc)
            return False

    async def get_all_open_orders(self) -> list[dict]:
        """Get all open/pending orders.

        Returns:
            list of dicts with order_id, symbol, side, qty, status, submitted_at
        """
        try:
            orders = await asyncio.to_thread(self._client.list_orders, status="open")
            return [
                {
                    "order_id": o.id,
                    "symbol": o.symbol,
                    "side": o.side,
                    "qty": float(o.qty),
                    "status": o.status,
                    "submitted_at": o.submitted_at,
                }
                for o in orders
            ]
        except Exception as exc:
            logger.error("[alpaca] get_all_open_orders failed: %s", exc)
            return []
