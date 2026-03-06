"""Session logger — persist reasoning, conversations, and trades to files."""
from __future__ import annotations

import json
import logging
import os
from datetime import datetime

from src.core.models.collaboration import CollaborationLoop

logger = logging.getLogger(__name__)


class SessionLogger:
    """Log agent reasoning, governance conversations, and trades to disk.

    Writes to logs/session_{timestamp}/ with files:
    - reasoning.jsonl: CEO/CIO LLM prompts, responses, decisions
    - conversations.jsonl: Governance loop transcripts
    - trades.jsonl: Order executions
    - session.md: Markdown summary (human-readable)
    """

    def __init__(self, session_dir: str | None = None):
        """Initialize session logger.

        Args:
            session_dir: Directory to log to. Defaults to logs/session_{timestamp}/
        """
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        if session_dir is None:
            session_dir = f"logs/session_{timestamp}"

        self.session_dir = session_dir
        os.makedirs(session_dir, exist_ok=True)

        # Open file handles
        self._reasoning_file = open(f"{session_dir}/reasoning.jsonl", "a", encoding="utf-8")
        self._conversations_file = open(
            f"{session_dir}/conversations.jsonl", "a", encoding="utf-8"
        )
        self._trades_file = open(f"{session_dir}/trades.jsonl", "a", encoding="utf-8")
        self._markdown_file = open(f"{session_dir}/session.md", "a", encoding="utf-8")

        # In-memory log for trade summary statistics
        self._fill_log: list[dict] = []

        # Write session header to markdown
        self._markdown_file.write(f"# Session Log: {timestamp}\n\n")
        self._markdown_file.write(f"Started at {datetime.now().isoformat()}\n\n")
        self._markdown_file.flush()

        logger.info("[session_logger] Initialized at %s", session_dir)

    def log_reasoning(
        self, agent_name: str, event_type: str, content: str, metadata: dict | None = None
    ) -> None:
        """Log an agent's reasoning step.

        Args:
            agent_name: Agent ID (e.g., 'ceo', 'cio')
            event_type: 'prompt', 'response', 'decision'
            content: The reasoning text
            metadata: Optional extra fields to log
        """
        entry = {
            "timestamp": datetime.now().isoformat(),
            "agent": agent_name,
            "event": event_type,
            "content": content,
            **(metadata or {}),
        }
        self._reasoning_file.write(json.dumps(entry) + "\n")
        self._reasoning_file.flush()

        # Also log to markdown
        if event_type == "prompt":
            self._markdown_file.write(f"\n## {agent_name.upper()} Reasoning\n")
            self._markdown_file.write(f"\n### Prompt\n```\n{content}\n```\n")
        elif event_type == "response":
            self._markdown_file.write(f"\n### Response\n```json\n{content}\n```\n")
        elif event_type == "decision":
            self._markdown_file.write(f"\n### Decision\n{content}\n")
        self._markdown_file.flush()

    def log_collaboration_loop(self, loop: CollaborationLoop) -> None:
        """Log a completed governance loop.

        Args:
            loop: CollaborationLoop object with transcript
        """
        entry = {
            "timestamp": loop.started_at.isoformat() if loop.started_at else datetime.now().isoformat(),
            "loop_id": str(loop.loop_id) if hasattr(loop, "loop_id") else "unknown",
            "topic": loop.topic,
            "participants": loop.participants,
            "iterations": loop.iterations_used,
            "max_iterations": loop.max_iterations,
            "consensus_reached": loop.consensus_reached,
            "outcome": loop.outcome,
            "messages": [m.model_dump(mode="json") for m in loop.messages],
        }
        self._conversations_file.write(json.dumps(entry) + "\n")
        self._conversations_file.flush()

        # Markdown summary
        self._markdown_file.write(f"\n## Governance Loop: {loop.topic}\n")
        self._markdown_file.write(
            f"**Consensus:** {loop.consensus_reached} | **Iterations:** {loop.iterations_used}/{loop.max_iterations}\n"
        )
        self._markdown_file.write(f"**Participants:** {', '.join(loop.participants)}\n\n")

        for i, msg in enumerate(loop.messages, 1):
            self._markdown_file.write(f"\n### Message {i}\n")
            self._markdown_file.write(f"**From:** {msg.sender} → **To:** {msg.recipient}\n")
            self._markdown_file.write(f"**Topic:** {msg.topic}\n")
            self._markdown_file.write(f"```json\n{json.dumps(msg.model_dump(mode='json'), indent=2)}\n```\n")

        self._markdown_file.write(f"\n**Outcome:** {json.dumps(loop.outcome, indent=2)}\n")
        self._markdown_file.flush()

    def log_trade(
        self,
        pod_id: str,
        order_id: str = None,
        symbol: str = None,
        side: str = None,
        qty: float = None,
        filled_price: float | None = None,
        status: str = "submitted",
        order_info: dict | None = None,
    ) -> None:
        """Log a trade execution.

        Args:
            pod_id: Pod that placed order
            order_id: Alpaca order ID (optional, can be in order_info)
            symbol: Ticker (optional, can be in order_info)
            side: 'buy' or 'sell' (optional, can be in order_info)
            qty: Quantity (optional, can be in order_info)
            filled_price: Fill price (None if not filled yet) (optional, can be in order_info)
            status: 'submitted', 'filled', 'cancelled', etc.
            order_info: Dict with order details (legacy method from Task 1.5 spec)
                Can include: order_id, symbol, side, qty, fill_price, notional,
                timestamp, mandate_applied, risk_approved, status
        """
        # Support both old signature (individual args) and new signature (order_info dict)
        if order_info is not None:
            # Use order_info as the base
            entry = {
                "timestamp": order_info.get("timestamp", datetime.now().isoformat()),
                "pod_id": pod_id,
                **order_info,
            }
        else:
            # Build from individual args
            entry = {
                "timestamp": datetime.now().isoformat(),
                "pod_id": pod_id,
                "order_id": order_id,
                "symbol": symbol,
                "side": side,
                "qty": qty,
                "filled_price": filled_price,
                "status": status,
            }

        self._trades_file.write(json.dumps(entry) + "\n")
        self._trades_file.flush()

        # Also store in memory for summary statistics
        self._fill_log.append(entry)

        # Markdown entry
        symbol_str = order_info.get("symbol", symbol) if order_info else symbol
        qty_str = order_info.get("qty", qty) if order_info else qty
        side_str = order_info.get("side", side) if order_info else side
        price_str = None
        if order_info:
            price_str = order_info.get("fill_price") or filled_price
        else:
            price_str = filled_price

        price_display = f"{price_str:.2f}" if price_str else "?"
        self._markdown_file.write(
            f"\n**TRADE [{pod_id}]:** {side_str.upper() if side_str else '?'} {qty_str} {symbol_str} @ ${price_display}\n"
        )
        self._markdown_file.flush()

    def close(self) -> None:
        """Close all open file handles and write summary to markdown."""
        # Count trades and calculate summary stats
        num_trades = len(self._fill_log) if hasattr(self, "_fill_log") else 0
        total_notional = 0.0
        total_volume = 0.0

        if hasattr(self, "_fill_log"):
            for fill in self._fill_log:
                notional = fill.get("notional", 0.0)
                total_notional += notional
                if notional > 0:
                    total_volume += abs(fill.get("qty", 0.0))

        # Write session summary to markdown
        self._markdown_file.write(f"\n\n## Session Summary\n")
        self._markdown_file.write(f"- **Session ended:** {datetime.now().isoformat()}\n")
        self._markdown_file.write(f"- **Total trades executed:** {num_trades}\n")
        self._markdown_file.write(f"- **Total notional volume:** ${total_notional:,.2f}\n")
        if num_trades > 0:
            self._markdown_file.write(f"- **Average order size:** ${total_notional / num_trades:,.2f}\n")

        self._markdown_file.flush()

        # Close all file handles
        self._reasoning_file.close()
        self._conversations_file.close()
        self._trades_file.close()
        self._markdown_file.close()
        logger.info("[session_logger] Closed")

    def __enter__(self):
        """Context manager support."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager cleanup."""
        self.close()
