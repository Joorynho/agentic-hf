import asyncio
import time

import pytest

from src.agents.governance import position_reviewer as reviewer_module
from src.agents.governance.position_reviewer import PositionReviewer


@pytest.mark.asyncio
async def test_position_review_llm_call_does_not_block_event_loop(monkeypatch):
    def slow_llm_chat(*args, **kwargs):
        time.sleep(0.15)
        return "review-ok"

    monkeypatch.setattr(reviewer_module, "llm_chat", slow_llm_chat)
    reviewer = PositionReviewer(event_bus=None)

    async def marker():
        await asyncio.sleep(0.02)
        return "event-loop-yielded"

    review_task = asyncio.create_task(
        reviewer._cio_review("equities", "AAPL: qty=1, P&L=$0", 1000.0)
    )
    marker_task = asyncio.create_task(marker())

    done, _pending = await asyncio.wait(
        {review_task, marker_task},
        timeout=0.08,
        return_when=asyncio.FIRST_COMPLETED,
    )

    assert marker_task in done
    assert marker_task.result() == "event-loop-yielded"
    assert not review_task.done()
    assert await review_task == "review-ok"
