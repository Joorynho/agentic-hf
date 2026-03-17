import asyncio
import logging
import uvicorn
from dotenv import load_dotenv
from pathlib import Path

load_dotenv(Path(__file__).parent / ".env")
logging.basicConfig(level=logging.INFO, format="%(levelname)s:%(name)s:%(message)s")

from src.core.bus.audit_log import AuditLog
from src.core.bus.event_bus import EventBus
from src.mission_control.session_manager import SessionManager
from src.web.server import create_app


async def run_trading_session(manager: SessionManager):
    """Initialize pods, then run the event loop that fetches bars and emits summaries."""
    await manager.start_live_session()
    await manager.run_event_loop(interval_seconds=60.0, governance_freq=5)


async def main():
    audit_log = AuditLog()
    event_bus = EventBus(audit_log=audit_log)

    manager = SessionManager(
        event_bus=event_bus, audit_log=audit_log, enable_news_adapters=True
    )
    app = create_app(event_bus=event_bus, session_manager=manager)
    manager.set_web_app(app)

    config = uvicorn.Config(app, host="127.0.0.1", port=8000, log_level="info")
    server = uvicorn.Server(config)

    await asyncio.gather(
        server.serve(),
        run_trading_session(manager),
    )


if __name__ == "__main__":
    asyncio.run(main())
