import asyncio
import logging
import os
from collections.abc import Mapping
import uvicorn
from dotenv import load_dotenv
from pathlib import Path

load_dotenv(Path(__file__).parent / ".env")
logging.basicConfig(level=logging.INFO, format="%(levelname)s:%(name)s:%(message)s")

if os.name == "nt":
    try:
        # The default Proactor loop can emit scary but transient accept errors
        # when localhost clients disconnect. Selector is quieter for this local
        # FastAPI/WebSocket dashboard workload.
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
        logging.info("[run] Windows selector event loop policy enabled")
    except Exception as exc:
        logging.debug("[run] Could not switch Windows event loop policy: %s", exc)

_YFINANCE_LOG_LEVEL = os.getenv("YFINANCE_LOG_LEVEL", "CRITICAL").upper()
logging.getLogger("yfinance").setLevel(getattr(logging, _YFINANCE_LOG_LEVEL, logging.CRITICAL))


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _env_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return float(raw)
    except ValueError:
        logging.warning("[run] Invalid %s=%r; using %.2f", name, raw, default)
        return default


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return int(raw)
    except ValueError:
        logging.warning("[run] Invalid %s=%r; using %d", name, raw, default)
        return default


def _install_loop_exception_handler() -> None:
    """Suppress transient Windows localhost socket accept noise; delegate everything else."""
    loop = asyncio.get_running_loop()
    default_handler = loop.default_exception_handler

    def handler(loop, context):
        exc = context.get("exception") if isinstance(context, Mapping) else None
        message = str(context.get("message", "")) if isinstance(context, Mapping) else ""
        winerror = getattr(exc, "winerror", None)
        if isinstance(exc, OSError) and winerror in {64, 995, 10053, 10054}:
            if "Accept failed" in message or "accept" in repr(context.get("future", "")).lower():
                logging.debug("[run] Suppressed transient localhost socket accept error: %s", exc)
                return
        default_handler(context)

    loop.set_exception_handler(handler)


if not _env_bool("MISSION_CONTROL_USE_LLM", default=True):
    # Explicit opt-out for tests/debugging only. In normal product runs, LLM
    # calls are part of the agent decision loop and should stay enabled.
    os.environ["OPENROUTER_API_KEY"] = ""
    os.environ["OPENAI_API_KEY"] = ""
    logging.info("[run] LLM calls disabled for this local run via MISSION_CONTROL_USE_LLM=false")
else:
    logging.info("[run] LLM calls enabled for this local run")

from src.core.bus.audit_log import AuditLog
from src.core.bus.event_bus import EventBus
from src.mission_control.session_manager import SessionManager
from src.web.server import create_app


async def run_trading_session(manager: SessionManager):
    """Initialize pods, then run the event loop that fetches bars and emits summaries."""
    await asyncio.sleep(1.0)  # Let Uvicorn finish startup so the dashboard can load first.
    capital_per_pod = _env_float("MISSION_CONTROL_CAPITAL_PER_POD", 1000.0)
    interval_seconds = _env_float("MISSION_CONTROL_INTERVAL_SECONDS", 60.0)
    governance_freq = _env_int("MISSION_CONTROL_GOVERNANCE_FREQ", 5)
    await manager.start_live_session(capital_per_pod=capital_per_pod)
    await manager.run_event_loop(interval_seconds=interval_seconds, governance_freq=governance_freq)


async def main():
    _install_loop_exception_handler()
    audit_log = AuditLog()
    event_bus = EventBus(audit_log=audit_log)
    enable_news_adapters = _env_bool("MISSION_CONTROL_ENABLE_NEWS", default=True)
    auto_start = _env_bool("MISSION_CONTROL_AUTO_START", default=True)

    manager = SessionManager(
        event_bus=event_bus, audit_log=audit_log, enable_news_adapters=enable_news_adapters
    )
    app = create_app(event_bus=event_bus, session_manager=manager)
    manager.set_web_app(app)

    host = os.getenv("FASTAPI_HOST", "127.0.0.1")
    port = _env_int("FASTAPI_PORT", 8001)
    config = uvicorn.Config(app, host=host, port=port, log_level="info")
    server = uvicorn.Server(config)

    tasks = [server.serve()]
    if auto_start:
        tasks.append(run_trading_session(manager))
    else:
        logging.info("[run] Auto-start disabled; use the dashboard Start button when ready")

    await asyncio.gather(*tasks)


if __name__ == "__main__":
    asyncio.run(main())
