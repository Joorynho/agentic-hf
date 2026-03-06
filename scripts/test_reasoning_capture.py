"""Manual test to verify reasoning capture in live governance cycle.

This script:
1. Initializes SessionLogger
2. Creates CEO and CIO agents with session logging enabled
3. Creates mock pod summaries
4. Runs a simplified governance cycle (without full EventBus complexity)
5. Prints session directory path and file summaries
6. Displays reasoning.jsonl entries
"""
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

import asyncio
import json
import logging
from datetime import datetime, timezone

from src.backtest.accounting.capital_allocator import CapitalAllocator
from src.core.bus.event_bus import EventBus
from src.core.bus.audit_log import AuditLog
from src.core.models.pod_summary import PodSummary, PodRiskMetrics, PodExposureBucket
from src.core.models.enums import PodStatus
from src.agents.ceo.ceo_agent import CEOAgent
from src.agents.cio.cio_agent import CIOAgent
from src.agents.risk.cro_agent import CROAgent
from src.agents.governance.governance_orchestrator import GovernanceOrchestrator
from src.mission_control.session_logger import SessionLogger

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def create_mock_pod_summaries() -> list[PodSummary]:
    """Create mock pod summaries for testing."""
    pod_ids = ["alpha", "beta", "gamma", "delta", "epsilon"]
    summaries = []

    for pod_id in pod_ids:
        risk_metrics = PodRiskMetrics(
            pod_id=pod_id,
            timestamp=datetime.now(timezone.utc),
            nav=1000000.0,
            daily_pnl=1500.0,
            drawdown_from_hwm=0.03,
            current_vol_ann=0.18,
            gross_leverage=1.2,
            net_leverage=0.8,
            var_95_1d=5000.0,
            es_95_1d=6500.0,
        )

        exposure_buckets = [
            PodExposureBucket(
                asset_class="equity",
                direction="long",
                notional_pct_nav=0.6,
            ),
            PodExposureBucket(
                asset_class="fixed_income",
                direction="long",
                notional_pct_nav=0.3,
            ),
        ]

        summary = PodSummary(
            pod_id=pod_id,
            timestamp=datetime.now(timezone.utc),
            status=PodStatus.ACTIVE,
            risk_metrics=risk_metrics,
            exposure_buckets=exposure_buckets,
            expected_return_estimate=0.12,
            turnover_daily_pct=2.5,
            heartbeat_ok=True,
        )
        summaries.append(summary)

    return summaries


async def main():
    """Run the test."""
    print("=" * 70)
    print("MANUAL REASONING CAPTURE TEST")
    print("=" * 70)

    # Initialize infrastructure
    audit_log = AuditLog()
    bus = EventBus(audit_log=audit_log)
    allocator = CapitalAllocator(
        pod_ids=["alpha", "beta", "gamma", "delta", "epsilon"],
        bus=bus,
    )
    session_logger = SessionLogger()

    print(f"\nSession logs directory: {session_logger.session_dir}")

    # Create agents with session logging
    ceo = CEOAgent(bus=bus, session_logger=session_logger)
    cio = CIOAgent(bus=bus, allocator=allocator, session_logger=session_logger)
    cro = CROAgent(bus=bus)

    # Create orchestrator
    orchestrator = GovernanceOrchestrator(
        ceo=ceo,
        cio=cio,
        cro=cro,
        session_logger=session_logger,
    )

    print("\nAgents created:")
    print(f"  - CEOAgent (session_logger={ceo._session_logger is not None})")
    print(f"  - CIOAgent (session_logger={cio._session_logger is not None})")
    print(f"  - CROAgent")
    print(f"  - GovernanceOrchestrator (session_logger={orchestrator._session_logger is not None})")

    # Create mock pod summaries
    pod_summaries = create_mock_pod_summaries()
    print(f"\nCreated mock pod summaries: {[s.pod_id for s in pod_summaries]}")

    # Run a simple governance cycle
    print("\n" + "=" * 70)
    print("Running governance cycle...")
    print("=" * 70)

    try:
        # Run the full governance cycle
        result = await orchestrator.run_full_cycle(pod_summaries)

        print(f"\nGovernance cycle complete:")
        print(f"  - Breached pods: {result['breached_pods']}")
        print(f"  - Loop 6 consensus: {result['loop6_consensus']}")
        print(f"  - Loop 7 consensus: {result['loop7_consensus']}")
        print(f"  - Mandate authorized by: {result['mandate'].authorized_by}")
    except Exception as exc:
        logger.error("Governance cycle failed: %s", exc, exc_info=True)
        # Continue to inspection phase even if cycle failed
        print(f"\nWarning: Governance cycle encountered error: {exc}")
        print("Continuing to file inspection...")

    # Inspect generated files
    print("\n" + "=" * 70)
    print("GENERATED FILES")
    print("=" * 70)

    session_path = Path(session_logger.session_dir)
    files_created = list(session_path.glob("*.jsonl")) + list(session_path.glob("*.md"))

    print(f"\nFiles created in {session_path}:")
    for file in files_created:
        size = file.stat().st_size
        print(f"  - {file.name} ({size} bytes)")

    # Display reasoning.jsonl content
    reasoning_file = session_path / "reasoning.jsonl"
    if reasoning_file.exists():
        print("\n" + "=" * 70)
        print("REASONING.JSONL ENTRIES")
        print("=" * 70)

        with open(reasoning_file) as f:
            lines = f.readlines()

        print(f"\nTotal entries: {len(lines)}")
        if lines:
            print("\nEntry summary:")
            for i, line in enumerate(lines, 1):
                entry = json.loads(line)
                timestamp = entry.get("timestamp", "?")
                agent = entry.get("agent", "?")
                event = entry.get("event", "?")
                content_preview = entry.get("content", "?")[:50]
                print(f"  {i}. [{timestamp}] {agent.upper()}: {event}")
                print(f"     Content: {content_preview}...")
        else:
            print("\n(No reasoning entries logged)")
    else:
        print("\nreasoning.jsonl not found")

    # Display conversations.jsonl content
    conversations_file = session_path / "conversations.jsonl"
    if conversations_file.exists():
        print("\n" + "=" * 70)
        print("CONVERSATIONS.JSONL ENTRIES")
        print("=" * 70)

        with open(conversations_file) as f:
            lines = f.readlines()

        print(f"\nTotal entries: {len(lines)}")
        if lines:
            print("\nConversation summary:")
            for i, line in enumerate(lines, 1):
                entry = json.loads(line)
                topic = entry.get("topic", "?")
                participants = entry.get("participants", [])
                consensus = entry.get("consensus_reached", False)
                iterations = entry.get("iterations", 0)
                print(f"  {i}. Topic: {topic}")
                print(f"     Participants: {participants}")
                print(f"     Consensus: {consensus}, Iterations: {iterations}")
        else:
            print("\n(No conversation entries logged)")
    else:
        print("\nconversations.jsonl not found")

    # Display session.md preview
    session_md = session_path / "session.md"
    if session_md.exists():
        print("\n" + "=" * 70)
        print("SESSION.MD PREVIEW (first 50 lines)")
        print("=" * 70)

        with open(session_md) as f:
            lines = f.readlines()

        print("\n".join(lines[:50]))
        if len(lines) > 50:
            print(f"\n... (truncated, {len(lines)} total lines)")
    else:
        print("\nsession.md not found")

    # Close resources
    print("\n" + "=" * 70)
    print("CLEANUP")
    print("=" * 70)

    session_logger.close()
    audit_log.close()

    print("\nResources closed.")
    print(f"\nSession logs saved to: {session_logger.session_dir}")
    print("You can inspect the files manually:")
    print(f"  - cat {session_path}/reasoning.jsonl")
    print(f"  - cat {session_path}/conversations.jsonl")
    print(f"  - cat {session_path}/session.md")


if __name__ == "__main__":
    asyncio.run(main())
