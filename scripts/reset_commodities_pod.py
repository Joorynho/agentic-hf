"""Reset the commodities pod after the factor-correlation risk fix.

By default this script performs a dry run. Use --apply to write changes.
Use --close-alpaca to close the current commodities symbols in the Alpaca
paper account before clearing local state.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import shutil
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
BACKUP_DIR = DATA_DIR / "backups"
MEMORY_JSON = DATA_DIR / "memory.json"
MEMORY_MD = DATA_DIR / "memory.md"
STATE_DB = DATA_DIR / "state.db"
POD_ID = "commodities"


def now_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")


def load_memory() -> dict[str, Any]:
    if not MEMORY_JSON.exists():
        raise FileNotFoundError(f"Missing {MEMORY_JSON}")
    return json.loads(MEMORY_JSON.read_text(encoding="utf-8"))


def is_commodities_trade(trade: dict[str, Any]) -> bool:
    return str(trade.get("pod_id") or trade.get("pod") or "").lower() == POD_ID


def commodities_symbols(memory: dict[str, Any]) -> set[str]:
    symbols: set[str] = set()
    pod_state = (memory.get("pods") or {}).get(POD_ID) or {}
    for pos in pod_state.get("positions") or []:
        sym = pos.get("symbol")
        if sym:
            symbols.add(str(sym).upper())
    return symbols


def fresh_pod_state() -> dict[str, Any]:
    return {
        "pod_id": POD_ID,
        "nav": 1000.0,
        "starting_capital": 1000.0,
        "daily_pnl": 0.0,
        "realized_pnl": 0.0,
        "cash": 1000.0,
        "positions": [],
        "fills": 0,
        "entry_theses": {},
        "entry_dates": {},
        "entry_metadata": {},
    }


def recompute_firm(memory: dict[str, Any]) -> None:
    pods = memory.get("pods") or {}
    total_nav = sum(float((state or {}).get("nav") or 0.0) for state in pods.values())
    initial_capital = sum(
        float((state or {}).get("starting_capital") or 0.0) for state in pods.values()
    )
    if initial_capital <= 0:
        initial_capital = float((memory.get("firm") or {}).get("initial_capital") or 0.0)

    realized_pnl = sum(
        float((state or {}).get("realized_pnl") or 0.0) for state in pods.values()
    )
    firm = memory.setdefault("firm", {})
    firm["total_nav"] = round(total_nav, 4)
    firm["total_pnl"] = round(total_nav - initial_capital, 4)
    firm["initial_capital"] = round(initial_capital, 4)
    firm["inception_pnl"] = round(realized_pnl, 4)
    firm["peak_nav"] = round(max(float(firm.get("peak_nav") or 0.0), total_nav), 4)


def reset_memory(memory: dict[str, Any]) -> dict[str, Any]:
    before_pod = ((memory.get("pods") or {}).get(POD_ID) or {}).copy()
    before_symbols = commodities_symbols(memory)
    before_trades = [t for t in memory.get("trades", []) if is_commodities_trade(t)]
    before_closed = ((memory.get("closed_trades_state") or {}).get(POD_ID) or [])

    memory.setdefault("pods", {})[POD_ID] = fresh_pod_state()
    memory["trades"] = [t for t in memory.get("trades", []) if not is_commodities_trade(t)]

    removed_sections: dict[str, bool] = {}
    for section in (
        "enrichment",
        "trade_outcomes",
        "signal_scores",
        "closed_trades_state",
        "discovered_universe",
    ):
        value = memory.get(section)
        if isinstance(value, dict):
            removed_sections[section] = POD_ID in value
            value.pop(POD_ID, None)

    memory["last_updated"] = datetime.now(timezone.utc).isoformat()
    recompute_firm(memory)

    return {
        "previous_nav": before_pod.get("nav"),
        "previous_cash": before_pod.get("cash"),
        "previous_realized_pnl": before_pod.get("realized_pnl"),
        "open_symbols": sorted(before_symbols),
        "removed_trade_count": len(before_trades),
        "removed_closed_trade_count": len(before_closed),
        "removed_sections": removed_sections,
        "new_firm_nav": (memory.get("firm") or {}).get("total_nav"),
        "new_firm_pnl": (memory.get("firm") or {}).get("total_pnl"),
    }


def write_memory_markdown(memory: dict[str, Any]) -> None:
    lines = [
        "# Session Memory",
        "",
        f"Last updated: {memory.get('last_updated', '')}",
        "",
    ]
    firm = memory.get("firm") or {}
    lines.extend(
        [
            "## Firm",
            "",
            f"Total NAV: ${float(firm.get('total_nav') or 0):.2f}",
            f"Total P&L: ${float(firm.get('total_pnl') or 0):+.2f}",
            "",
            "## Pod Positions",
            "",
        ]
    )
    for pod_id, pod_state in (memory.get("pods") or {}).items():
        lines.append(f"### {pod_id.upper()}")
        lines.append("")
        lines.append(
            f"NAV: ${float(pod_state.get('nav') or 0):.2f} | "
            f"P&L: ${float(pod_state.get('daily_pnl') or 0):+.2f}"
        )
        lines.append("")
        positions = pod_state.get("positions") or []
        if positions:
            lines.append("| Symbol | Qty | Avg Entry | Current | Unrl P&L |")
            lines.append("|--------|-----|-----------|---------|----------|")
            for pos in positions:
                qty = float(pos.get("qty") or 0)
                avg = float(pos.get("avg_entry") or 0)
                current = float(pos.get("current_price") or avg)
                pnl = qty * (current - avg)
                lines.append(
                    f"| {pos.get('symbol', '')} | {qty:.2f} | ${avg:.2f} "
                    f"| ${current:.2f} | ${pnl:+.2f} |"
                )
        else:
            lines.append("_No open positions_")
        lines.append("")

    recent = memory.get("trades") or []
    if recent:
        lines.append("## Recent Trades (last 20)")
        lines.append("")
        lines.append("| Time | Pod | Symbol | Side | Qty | Price |")
        lines.append("|------|-----|--------|------|-----|-------|")
        for trade in recent[-20:]:
            price = float(trade.get("filled_price") or trade.get("fill_price") or 0)
            lines.append(
                f"| {str(trade.get('timestamp', '-'))[:19]} | "
                f"{trade.get('pod_id', '-')} | {trade.get('symbol', '-')} | "
                f"{trade.get('side', '-')} | {trade.get('qty', '-')} | ${price:.2f} |"
            )
        lines.append("")

    MEMORY_MD.write_text("\n".join(lines), encoding="utf-8")


def backup_files() -> dict[str, str]:
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    stamp = now_stamp()
    backups: dict[str, str] = {}
    for path in (MEMORY_JSON, MEMORY_MD, STATE_DB):
        if path.exists():
            dest = BACKUP_DIR / f"{path.stem}_before_{POD_ID}_reset_{stamp}{path.suffix}"
            shutil.copy2(path, dest)
            backups[str(path.relative_to(ROOT))] = str(dest.relative_to(ROOT))
    return backups


def reset_nav_history(apply: bool) -> dict[str, Any]:
    if not STATE_DB.exists():
        return {"state_db": "missing", "removed_nav_rows": 0}

    con = sqlite3.connect(str(STATE_DB), timeout=10)
    try:
        count = con.execute(
            "SELECT count(*) FROM nav_snapshots WHERE pod_id = ?", (POD_ID,)
        ).fetchone()[0]
        if apply and count:
            con.execute("DELETE FROM nav_snapshots WHERE pod_id = ?", (POD_ID,))
        inserted_reset_row = False
        if apply:
            con.execute(
                """
                INSERT INTO nav_snapshots (pod_id, ts, nav, cash, invested, realized)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (POD_ID, datetime.now(timezone.utc).isoformat(), 1000.0, 1000.0, 0.0, 0.0),
            )
            inserted_reset_row = True
        con.commit()
        return {
            "state_db": "ok",
            "removed_nav_rows": int(count),
            "inserted_reset_row": inserted_reset_row,
        }
    finally:
        con.close()


async def close_alpaca_positions(symbols: set[str], apply: bool) -> dict[str, Any]:
    if not symbols:
        return {"alpaca_targets": [], "orders": []}

    sys.path.insert(0, str(ROOT))
    from src.execution.paper.alpaca_adapter import AlpacaAdapter

    adapter = AlpacaAdapter()
    positions = await adapter.get_open_positions()
    targets = sorted(sym for sym in symbols if sym in positions)
    if not apply:
        return {"alpaca_targets": targets, "orders": []}

    orders = []
    for symbol in targets:
        orders.append(await adapter.close_position(symbol))
    return {"alpaca_targets": targets, "orders": orders}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="Write the reset to disk.")
    parser.add_argument(
        "--close-alpaca",
        action="store_true",
        help="Close current commodities symbols in the Alpaca paper account.",
    )
    parser.add_argument(
        "--symbols",
        nargs="*",
        default=None,
        help="Explicit symbols to close in Alpaca instead of symbols found in commodities memory.",
    )
    args = parser.parse_args()

    memory = load_memory()
    symbols = {s.upper() for s in args.symbols} if args.symbols else commodities_symbols(memory)
    summary = reset_memory(memory)
    backups: dict[str, str] = {}
    if args.apply:
        backups = backup_files()

    alpaca_result = None
    if args.close_alpaca:
        alpaca_result = asyncio.run(close_alpaca_positions(symbols, apply=args.apply))

    nav_result = reset_nav_history(apply=args.apply)

    if args.apply:
        MEMORY_JSON.write_text(json.dumps(memory, indent=2), encoding="utf-8")
        write_memory_markdown(memory)

    result = {
        "mode": "apply" if args.apply else "dry-run",
        "memory_reset": summary,
        "nav_history": nav_result,
        "alpaca": alpaca_result,
        "backups": backups,
    }
    print(json.dumps(result, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
