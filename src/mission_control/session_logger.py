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
        order_id: str,
        symbol: str,
        side: str,
        qty: float,
        filled_price: float | None = None,
        status: str = "submitted",
    ) -> None:
        """Log a trade execution.

        Args:
            pod_id: Pod that placed order
            order_id: Alpaca order ID
            symbol: Ticker
            side: 'buy' or 'sell'
            qty: Quantity
            filled_price: Fill price (None if not filled yet)
            status: 'submitted', 'filled', 'cancelled', etc.
        """
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

        # Markdown entry
        price_str = f"{filled_price:.2f}" if filled_price else "?"
        self._markdown_file.write(
            f"\n**TRADE [{pod_id}]:** {side.upper()} {qty} {symbol} @ ${price_str} (order_id={order_id}, status={status})\n"
        )
        self._markdown_file.flush()

    def close(self) -> None:
        """Close all open file handles."""
        self._markdown_file.write(f"\n\nSession ended at {datetime.now().isoformat()}\n")
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
