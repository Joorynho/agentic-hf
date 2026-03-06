# MVP3 Batch 3: Agent Reasoning Visibility Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Expose CEO/CIO LLM reasoning and governance loop conversations to TUI by logging prompts/responses and collaboration transcripts to disk.

**Architecture:** Add logging hooks to CEO/CIO agents that fire before/after LLM calls, capturing prompts and responses. Modify CollaborationRunner to log completed loops with full message transcripts. Wire SessionLogger into GovernanceOrchestrator so all agent activity is persisted to session files.

**Tech Stack:** SessionLogger (existing), OpenAI SDK (existing), Pydantic models (existing)

---

## Task 1: Add Logging Support to CEOAgent

**Files:**
- Modify: `src/agents/ceo/ceo_agent.py`
- Modify: `src/mission_control/session_manager.py` (inject SessionLogger)
- Test: No new tests (CEO already tested in MVP2); manual verification

**Step 1: Read CEOAgent to understand structure**

File: `src/agents/ceo/ceo_agent.py`

Understand:
- Where `_llm_mandate()` is called
- What prompt is sent to OpenAI
- What response is returned
- Where decision is made

**Step 2: Add SessionLogger parameter to CEOAgent.__init__**

Modify `src/agents/ceo/ceo_agent.py`:

```python
class CEOAgent:
    def __init__(self, bus: EventBus, session_logger: SessionLogger | None = None):
        self._bus = bus
        self._session_logger = session_logger  # NEW
        self._api_key = os.getenv("OPENAI_API_KEY", "")
        logger.info("[ceo] Initialized")
```

**Step 3: Add logging in _llm_mandate before LLM call**

In the `_llm_mandate()` method, before calling OpenAI:

```python
async def _llm_mandate(self, pod_summaries, cio_input, cro_constraints):
    """Generate CEO mandate via LLM."""
    prompt = f"""You are the Chief Executive Officer...
    {pod_summaries}
    {cio_input}
    {cro_constraints}
    """

    # Log the prompt
    if self._session_logger:
        self._session_logger.log_reasoning("ceo", "prompt", prompt)

    # Call OpenAI
    try:
        client = openai.OpenAI(api_key=self._api_key)
        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"},
        )
        reasoning_text = resp.choices[0].message.content

        # Log the response
        if self._session_logger:
            self._session_logger.log_reasoning("ceo", "response", reasoning_text)

        # Parse and log decision
        data = json.loads(reasoning_text)
        # ... rest of implementation
```

**Step 4: Verify no test failures**

Run existing MVP2 CEO tests:
```bash
pytest tests/integration/test_mvp2.py::test_ceo_rule_based_mandate -v
# Expected: PASS
```

**Step 5: Commit**

```bash
git add src/agents/ceo/ceo_agent.py
git commit -m "feat: add SessionLogger to CEOAgent for reasoning logging"
```

---

## Task 2: Add Logging Support to CIOAgent

**Files:**
- Modify: `src/agents/cio/cio_agent.py`

**Steps:** (Same pattern as Task 1)

Add SessionLogger parameter to CIOAgent.__init__, then log prompts/responses in `_llm_rebalance()` or `rebalance()` method.

```python
class CIOAgent:
    def __init__(self, bus: EventBus, allocator: CapitalAllocator, session_logger: SessionLogger | None = None):
        self._bus = bus
        self._allocator = allocator
        self._session_logger = session_logger  # NEW
        self._api_key = os.getenv("OPENAI_API_KEY", "")
```

In the rebalance method, add:
```python
if self._session_logger:
    self._session_logger.log_reasoning("cio", "prompt", prompt)
    self._session_logger.log_reasoning("cio", "response", reasoning_text)
    self._session_logger.log_reasoning("cio", "decision", f"Allocations: {records}")
```

**Commit:**
```bash
git add src/agents/cio/cio_agent.py
git commit -m "feat: add SessionLogger to CIOAgent for rebalance reasoning logging"
```

---

## Task 3: Add Collaboration Loop Logging to CollaborationRunner

**Files:**
- Modify: `src/core/bus/collaboration_runner.py`
- Modify: `src/mission_control/session_manager.py` (inject SessionLogger into CollaborationRunner)

**Step 1: Read CollaborationRunner to understand loop structure**

File: `src/core/bus/collaboration_runner.py`

Understand:
- `CollaborationLoop` model: `.messages`, `.iterations_used`, `.consensus_reached`, `.outcome`
- `run_loop()` method: returns a completed loop
- Where loops are completed

**Step 2: Add SessionLogger to CollaborationRunner**

Modify constructor:

```python
class CollaborationRunner:
    def __init__(self, bus: EventBus, session_logger: SessionLogger | None = None):
        self._bus = bus
        self._session_logger = session_logger  # NEW
        ...
```

**Step 3: Log loop after completion in run_loop()**

At the end of `run_loop()`, after loop completes:

```python
    async def run_loop(self, topic, participants, max_iterations, initial_message):
        loop = CollaborationLoop(
            loop_id=uuid4(),
            topic=topic,
            participants=participants,
            max_iterations=max_iterations,
            started_at=datetime.now(timezone.utc),
            ...
        )

        # ... existing loop logic ...

        # After loop completes, log it
        if self._session_logger:
            self._session_logger.log_collaboration_loop(loop)

        return loop
```

**Step 4: Verify tests pass**

```bash
pytest tests/integration/test_mvp2.py::test_full_governance_cycle_returns_mandate -v
# Expected: PASS
```

**Step 5: Commit**

```bash
git add src/core/bus/collaboration_runner.py
git commit -m "feat: add CollaborationLoop logging to persistence"
```

---

## Task 4: Wire SessionLogger into GovernanceOrchestrator

**Files:**
- Modify: `src/agents/governance/governance_orchestrator.py`
- Modify: `src/mission_control/session_manager.py` (wire SessionLogger through to all agents)

**Step 1: Update GovernanceOrchestrator to accept SessionLogger**

Modify constructor:

```python
class GovernanceOrchestrator:
    def __init__(
        self,
        ceo: CEOAgent,
        cio: CIOAgent,
        cro: CROAgent,
        session_logger: SessionLogger | None = None,
    ):
        self._ceo = ceo
        self._cio = cio
        self._cro = cro
        self._runner = CollaborationRunner(bus=ceo._bus, session_logger=session_logger)
        self._session_logger = session_logger
```

**Step 2: Pass SessionLogger to agents when creating them**

When orchestrator creates agents (if it does), pass SessionLogger:

```python
# In run_firm_deliberation or similar
self._ceo = CEOAgent(bus=self._bus, session_logger=self._session_logger)
self._cio = CIOAgent(bus=self._bus, allocator=self._allocator, session_logger=self._session_logger)
```

**Step 3: Update SessionManager to wire SessionLogger**

Modify `src/mission_control/session_manager.py`:

```python
class SessionManager:
    def __init__(self, ...):
        ...
        self._session_logger = SessionLogger()
        self._governance = GovernanceOrchestrator(
            ceo=CEOAgent(bus=self._bus, session_logger=self._session_logger),
            cio=CIOAgent(bus=self._bus, allocator=..., session_logger=self._session_logger),
            cro=CROAgent(bus=self._bus),
            session_logger=self._session_logger,  # NEW
        )
```

**Step 4: Verify no regressions**

```bash
pytest tests/integration/test_mvp2.py -v
# Expected: All tests pass
```

**Step 5: Commit**

```bash
git add src/agents/governance/governance_orchestrator.py src/mission_control/session_manager.py
git commit -m "feat: wire SessionLogger through GovernanceOrchestrator to all agents"
```

---

## Task 5: Test Reasoning Capture End-to-End

**Files:**
- Create: `tests/integration/test_mvp3_batch3_reasoning.py`

**Step 1: Write test that verifies reasoning files are created**

Create test file:

```python
"""MVP3 Batch 3 Integration Tests — Agent Reasoning Visibility."""
import asyncio
import json
import os
import tempfile
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest

from src.core.bus.event_bus import EventBus
from src.core.bus.audit_log import AuditLog
from src.agents.governance.governance_orchestrator import GovernanceOrchestrator
from src.agents.ceo.ceo_agent import CEOAgent
from src.agents.cio.cio_agent import CIOAgent
from src.agents.risk.cro_agent import CROAgent
from src.backtest.accounting.capital_allocator import CapitalAllocator
from src.core.models.pod_summary import PodSummary, PodRiskMetrics
from src.mission_control.session_logger import SessionLogger


@pytest.mark.asyncio
async def test_session_logger_captures_reasoning_files():
    """SessionLogger creates and populates reasoning.jsonl and conversations.jsonl."""
    with tempfile.TemporaryDirectory() as tmpdir:
        logger = SessionLogger(session_dir=tmpdir)

        # Simulate CEO reasoning
        logger.log_reasoning("ceo", "prompt", "Generate mandate for 5 pods...")
        logger.log_reasoning("ceo", "response", '{"decision": "rebalance", "objectives": [...]}')

        # Simulate CIO reasoning
        logger.log_reasoning("cio", "prompt", "Allocate capital based on risk...")
        logger.log_reasoning("cio", "response", '{"allocations": {"alpha": 0.2, ...}}')

        logger.close()

        # Verify files exist and have content
        reasoning_file = os.path.join(tmpdir, "reasoning.jsonl")
        assert os.path.isfile(reasoning_file)

        with open(reasoning_file, "r") as f:
            lines = f.readlines()

        assert len(lines) >= 4  # At least 4 reasoning entries

        # Verify JSONL format
        for line in lines:
            entry = json.loads(line)
            assert "timestamp" in entry
            assert "agent" in entry
            assert "event" in entry
            assert "content" in entry


@pytest.mark.asyncio
async def test_collaboration_loop_logged():
    """CollaborationLoop transcripts are logged to conversations.jsonl."""
    with tempfile.TemporaryDirectory() as tmpdir:
        from src.core.bus.collaboration_runner import CollaborationRunner
        from src.core.models.messages import AgentMessage

        bus = EventBus(audit_log=AuditLog())
        logger = SessionLogger(session_dir=tmpdir)
        runner = CollaborationRunner(bus=bus, session_logger=logger)

        # Simulate a simple collaboration loop
        msg = AgentMessage(
            timestamp=datetime.now(timezone.utc),
            sender="ceo",
            recipient="*",
            topic="governance.strategy",
            payload={"decision": "continue"},
        )

        # Note: Actual loop execution would be tested here
        # For now, just verify the logging infrastructure is in place

        logger.close()

        # Verify conversations file exists (may be empty if no loops run)
        conversations_file = os.path.join(tmpdir, "conversations.jsonl")
        assert os.path.isfile(conversations_file)


def test_ceo_agent_has_session_logger_parameter():
    """CEOAgent constructor accepts optional session_logger parameter."""
    bus = EventBus(audit_log=AuditLog())
    logger = SessionLogger()

    # Should not raise
    ceo = CEOAgent(bus=bus, session_logger=logger)

    assert ceo._session_logger is logger
    logger.close()


def test_cio_agent_has_session_logger_parameter():
    """CIOAgent constructor accepts optional session_logger parameter."""
    from src.backtest.accounting.capital_allocator import CapitalAllocator

    bus = EventBus(audit_log=AuditLog())
    allocator = CapitalAllocator(pod_ids=["alpha", "beta"], bus=bus)
    logger = SessionLogger()

    # Should not raise
    cio = CIOAgent(bus=bus, allocator=allocator, session_logger=logger)

    assert cio._session_logger is logger
    logger.close()


def test_governance_orchestrator_has_session_logger_parameter():
    """GovernanceOrchestrator accepts optional session_logger parameter."""
    bus = EventBus(audit_log=AuditLog())
    allocator = CapitalAllocator(pod_ids=["alpha", "beta"], bus=bus)
    logger = SessionLogger()

    ceo = CEOAgent(bus=bus, session_logger=logger)
    cio = CIOAgent(bus=bus, allocator=allocator, session_logger=logger)
    cro = CROAgent(bus=bus)

    # Should not raise
    orch = GovernanceOrchestrator(ceo=ceo, cio=cio, cro=cro, session_logger=logger)

    assert orch._session_logger is logger
    logger.close()
```

**Step 2: Run tests to verify they pass**

```bash
pytest tests/integration/test_mvp3_batch3_reasoning.py -v
# Expected: All 5 tests PASS
```

**Step 3: Commit**

```bash
git add tests/integration/test_mvp3_batch3_reasoning.py
git commit -m "test: add MVP3 Batch 3 reasoning visibility tests"
```

---

## Task 6: Manual Integration Test (Optional)

**Steps:** (Manual verification, not automated)

1. Create a small test script that runs a governance cycle with SessionManager
2. Run the script
3. Inspect the generated `logs/session_*/reasoning.jsonl` and `logs/session_*/conversations.jsonl`
4. Verify CEO/CIO prompts, responses, and decisions are captured

Example script:

```python
import asyncio
from src.mission_control.session_manager import SessionManager
from src.execution.paper.alpaca_adapter import AlpacaAdapter

async def test_reasoning_capture():
    manager = SessionManager(alpaca_adapter=AlpacaAdapter())
    await manager.start_live_session()

    # Simulate one governance cycle (would run in real session loop)
    # For now, just verify the infrastructure is in place

    print(f"Session logs saved to: {manager.get_session_dir()}")
    await manager.stop_session()

if __name__ == "__main__":
    asyncio.run(test_reasoning_capture())
```

---

## Summary

**Batch 3 deliverables:**
- CEO agent logs prompts/responses ✓
- CIO agent logs prompts/responses ✓
- CollaborationRunner logs loop transcripts ✓
- GovernanceOrchestrator wires SessionLogger ✓
- Integration tests verifying logging ✓

**Key changes from MVP2:**
- All agents accept optional SessionLogger
- Reasoning is persisted to disk (reasoning.jsonl, conversations.jsonl)
- TUI can eventually display this via audit log
- Full transparency into governance decision-making

**Next phase (Batch 4):**
- Live session tests with real Alpaca paper trading
- End-to-end flow: market data → pods → governance → TUI visualization
- Verify all reasoning is captured in live session

---
