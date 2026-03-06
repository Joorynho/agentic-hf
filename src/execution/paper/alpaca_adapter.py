"""Alpaca paper trading adapter — fetches real-time data and executes orders."""
from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import Optional

from alpaca_trade_api import REST, TimeFrame
from alpaca_trade_api.rest import TimeFrameUnit
import pandas as pd

from src.core.models.market import Bar

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

        # REST client for trading + historical data
        self._client = REST(
            key_id=api_key,
            secret_key=secret_key,
            base_url=ALPACA_PAPER_URL if paper else "https://api.alpaca.markets",
            api_version="v2",
        )
        logger.info("[alpaca] Connected to %s", "paper" if paper else "live")

    async def fetch_account(self) -> dict:
        """Fetch account info (NAV, buying power, positions).

        Returns:
            dict with keys: equity, cash, buying_power, etc.
        """
        try:
            account = self._client.get_account()
            return {
                "equity": float(account.equity),
                "cash": float(account.cash),
                "buying_power": float(account.buying_power),
                "position_count": len(self._client.list_positions()),
            }
        except Exception as exc:
            logger.error("[alpaca] fetch_account failed: %s", exc)
            raise

    async def fetch_bars(
        self,
        symbols: list[str],
        timeframe: str = "1Min",
        limit: int = 1000,
    ) -> dict[str, list[Bar]]:
        """Fetch latest bars for symbols.

        Args:
            symbols: List of tickers (e.g., ['AAPL', 'MSFT'])
            timeframe: '1Min', '5Min', '15Min', '1H', '1D' (default '1Min')
            limit: Max bars per symbol (default 1000, max 10000)

        Returns:
            dict[symbol] -> list[Bar] ordered by timestamp ascending
        """
        results = {}
        try:
            # Map string timeframe to alpaca TimeFrame objects
            tf_map = {
                "1Min": TimeFrame.Minute,
                "5Min": TimeFrame(5, TimeFrameUnit.Minute),
                "15Min": TimeFrame(15, TimeFrameUnit.Minute),
                "1H": TimeFrame.Hour,
                "1D": TimeFrame.Day,
            }
            tf = tf_map.get(timeframe, TimeFrame.Minute)

            # Fetch bars for all symbols
            barset = self._client.get_bars(
                symbols,
                timeframe=tf,
                limit=limit,
            )

            # Convert to Bar objects (compatible with BacktestRunner)
            for symbol in symbols:
                bars = []
                if symbol in barset:
                    df = barset[symbol]
                    for idx, row in df.iterrows():
                        bar = Bar(
                            symbol=symbol,
                            timestamp=pd.Timestamp(idx).to_pydatetime() if hasattr(idx, 'to_pydatetime') else idx,
                            open=float(row["open"]),
                            high=float(row["high"]),
                            low=float(row["low"]),
                            close=float(row["close"]),
                            volume=int(row["volume"]),
                            source="alpaca",
                        )
                        bars.append(bar)
                results[symbol] = bars

            logger.debug(
                "[alpaca] fetch_bars: %d symbols, %s timeframe",
                len(symbols),
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
    ) -> dict:
        """Place an order.

        Args:
            symbol: Ticker (e.g., 'AAPL')
            qty: Quantity (positive float)
            side: 'buy' or 'sell'
            order_type: 'market' or 'limit' (default 'market')
            limit_price: Required if order_type='limit'

        Returns:
            dict with keys: order_id, symbol, qty, side, status, filled_qty, filled_avg_price
        """
        try:
            order = self._client.submit_order(
                symbol=symbol,
                qty=qty,
                side=side,
                type=order_type,
                time_in_force="day",
                limit_price=limit_price if order_type == "limit" else None,
            )
            result = {
                "order_id": order.id,
                "symbol": order.symbol,
                "qty": float(order.qty),
                "side": order.side,
                "status": order.status,
                "filled_qty": float(order.filled_qty) if order.filled_qty else 0.0,
                "filled_avg_price": float(order.filled_avg_price)
                if order.filled_avg_price
                else None,
                "submitted_at": order.submitted_at,
            }
            logger.info(
                "[alpaca] Order placed: %s %s %s@%s (id=%s)",
                side,
                qty,
                symbol,
                "market" if order_type == "market" else f"${limit_price}",
                order.id,
            )
            return result
        except Exception as exc:
            logger.error("[alpaca] place_order failed: %s", exc)
            raise

    async def get_open_positions(self) -> dict[str, dict]:
        """Get all open positions.

        Returns:
            dict[symbol] -> {qty, entry_price, current_price, unrealized_pl}
        """
        try:
            positions = self._client.list_positions()
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
            order = self._client.get_order(order_id)
            return {
                "status": order.status,
                "filled_qty": float(order.filled_qty) if order.filled_qty else 0.0,
                "filled_avg_price": float(order.filled_avg_price)
                if order.filled_avg_price
                else None,
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
            qty = float(position.qty)
            return await self.place_order(symbol, qty, side, order_type="market")
        except Exception as exc:
            logger.error("[alpaca] close_position failed for %s: %s", symbol, exc)
            raise

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
