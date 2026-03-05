import pytest, asyncio, tempfile, os
from src.core.bus.event_bus import EventBus
from src.core.bus.exceptions import TopicAccessError
from src.core.bus.audit_log import AuditLog
from src.core.models.messages import AgentMessage
from datetime import datetime

@pytest.fixture
def bus():
    return EventBus()

@pytest.mark.asyncio
async def test_publish_and_receive(bus):
    received = []
    await bus.subscribe("test.topic", lambda msg: received.append(msg))
    msg = AgentMessage(timestamp=datetime.now(), sender="cio",
                       recipient="broadcast", topic="test.topic", payload={"x": 1})
    await bus.publish("test.topic", msg, publisher_id="cio")
    await asyncio.sleep(0.01)
    assert len(received) == 1

@pytest.mark.asyncio
async def test_pod_cannot_publish_to_sibling_gateway(bus):
    msg = AgentMessage(timestamp=datetime.now(), sender="pod.alpha",
                       recipient="pod.beta", topic="pod.beta.gateway", payload={})
    with pytest.raises(TopicAccessError):
        await bus.publish("pod.beta.gateway", msg, publisher_id="pod.alpha")

@pytest.mark.asyncio
async def test_governance_only_published_by_authorized(bus):
    msg = AgentMessage(timestamp=datetime.now(), sender="pod.alpha",
                       recipient="pod.alpha", topic="governance.alpha", payload={})
    with pytest.raises(TopicAccessError):
        await bus.publish("governance.alpha", msg, publisher_id="pod.alpha")

@pytest.mark.asyncio
async def test_pod_can_publish_to_own_gateway(bus):
    received = []
    await bus.subscribe("pod.alpha.gateway", lambda m: received.append(m))
    msg = AgentMessage(timestamp=datetime.now(), sender="pod.alpha",
                       recipient="broadcast", topic="pod.alpha.gateway", payload={})
    await bus.publish("pod.alpha.gateway", msg, publisher_id="pod.alpha")
    await asyncio.sleep(0.01)
    assert len(received) == 1

@pytest.mark.asyncio
async def test_audit_log_records_every_message():
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "audit.duckdb")
        log = AuditLog(db_path)
        bus = EventBus(audit_log=log)
        msg = AgentMessage(timestamp=datetime.now(), sender="cio",
                           recipient="broadcast", topic="test.topic",
                           payload={"val": 42})
        await bus.subscribe("test.topic", lambda m: None)
        await bus.publish("test.topic", msg, publisher_id="cio")
        await asyncio.sleep(0.01)
        records = log.query("SELECT * FROM messages")
        assert len(records) == 1
        assert records[0]["sender"] == "cio"
        log.close()  # Release DuckDB file lock before tmpdir cleanup
