import asyncio
import uvicorn
from dotenv import load_dotenv
from pathlib import Path

load_dotenv(Path(__file__).parent / ".env")

from src.core.bus.audit_log import AuditLog
from src.core.bus.event_bus import EventBus
from src.mission_control.session_manager import SessionManager
from src.web.server import create_app


async def main():
    audit_log = AuditLog()
    event_bus = EventBus(audit_log=audit_log)

    app = create_app(event_bus=event_bus)
    manager = SessionManager(event_bus=event_bus, audit_log=audit_log)

    config = uvicorn.Config(app, host="127.0.0.1", port=8000, log_level="info")
    server = uvicorn.Server(config)

    await asyncio.gather(
        server.serve(),
        manager.start_live_session(),
    )


if __name__ == "__main__":
    asyncio.run(main())
