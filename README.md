# Agentic HF Mission Control

Agentic HF is a local multi-agent hedge fund simulation and paper-trading OS. It runs four isolated strategy pods, firm-level governance, Alpaca paper execution, research ingestion, and a live FastAPI/WebSocket dashboard.

This is a working product, not just a mockup. The active runtime path is Python backend plus the static dashboard in `web/dist`.

## Current Product State

- Active strategy pods: `equities`, `fx`, `crypto`, `commodities`
- Agents per pod: researcher, signal, PM, risk, execution trader, ops
- Firm agents: CEO, CIO, CRO
- Risk enforcement: deterministic/rule-based; no LLM decides hard limits
- Dashboard: served from `web/dist` by `src/web/server.py`
- Live runner: `python run.py`, defaulting to `http://127.0.0.1:8001`
- API-only server: `python -m uvicorn src.web.server:app --host 127.0.0.1 --port 8000`
- Legacy/experimental frontend tree: `web/src` React/Vite. It is not the current served dashboard unless rebuilt into `web/dist`.

## Quick Start

Use Python 3.12.10 where available:

```powershell
cd "C:/Users/PW1868/Agentic HF"
& "C:/Users/PW1868/AppData/Local/Programs/Python/Python312/python.exe" -m pip install -r requirements.txt
```

Create `.env` from `.env.example` and add only the keys you need. Alpaca keys are required for a real paper-trading session.

```powershell
copy .env.example .env
```

Start the full local product:

```powershell
& "C:/Users/PW1868/AppData/Local/Programs/Python/Python312/python.exe" run.py
```

Open:

```text
http://127.0.0.1:8001
```

For a dashboard/API smoke server without auto-starting the trading loop:

```powershell
& "C:/Users/PW1868/AppData/Local/Programs/Python/Python312/python.exe" -m uvicorn src.web.server:app --host 127.0.0.1 --port 8000
```

## Architecture

The core runtime is coordinated by `src/mission_control/session_manager.py`.

Data and decisions flow like this:

```text
Market/research adapters
  -> SessionManager
  -> isolated PodRuntime per asset class
  -> PodGateway emits PodSummary only
  -> EventBus + AuditLog
  -> FastAPI REST/WebSocket server
  -> web/dist dashboard
```

Important boundaries:

- `PodSummary` is the only model intended to cross a pod boundary.
- `PodGateway` is the pod I/O boundary.
- `EventBus` enforces topic ownership for pod gateway topics.
- `CROAgent` and `RiskManager` are rule-based and remain outside LLM discretion.

## Main Components

Backend:

- `src/core/bus`: event bus, DuckDB audit log, collaboration runner
- `src/core/models`: Pydantic schemas for market, execution, allocation, messages, summaries
- `src/pods/templates`: four active asset-class pod implementations plus older template pods
- `src/agents`: CEO, CIO, CRO, governance, thesis review
- `src/backtest`: portfolio accounting, capital allocation, backtest runner
- `src/execution`: paper and Alpaca execution adapters
- `src/data`: FRED, Polymarket, RSS/news, yfinance, live quote, sentiment, benchmark, and theme scanner adapters
- `src/web`: FastAPI REST API, WebSocket bridge, static dashboard serving
- `src/reports`: daily/review report generation and optional SMTP delivery

Frontend:

- `web/dist`: current served dashboard
- `web/src`: React/Vite source tree retained for future frontend work

## Configuration

Common environment variables:

```text
ALPACA_API_KEY=...
ALPACA_SECRET_KEY=...
OPENROUTER_API_KEY=...
OPENAI_API_KEY=...
FRED_API_KEY=...
POLYMARKET_API_KEY=...
FASTAPI_HOST=127.0.0.1
FASTAPI_PORT=8001
ENVIRONMENT=development
```

Production/session-control switches:

```text
ENVIRONMENT=production
DASHBOARD_CORS_ORIGINS=https://your-dashboard.example
MISSION_CONTROL_ENABLE_SESSION_CONTROL=false
```

In production, dashboard start/stop endpoints are disabled unless `MISSION_CONTROL_ENABLE_SESSION_CONTROL=true`.

## API

Core endpoints:

| Endpoint | Method | Purpose |
| --- | --- | --- |
| `/health` | GET | Health check |
| `/api/session` | GET | Session capital, uptime, iteration |
| `/api/session/status` | GET | Active/idle state |
| `/api/session/start` | POST | Start live session, guarded in production |
| `/api/session/stop` | POST | Stop live session, guarded in production |
| `/api/pods` | GET | Pod summaries |
| `/api/pods/{pod_id}` | GET | Detailed pod state |
| `/api/positions` | GET | Open positions across pods |
| `/api/trades/closed` | GET | Closed trades |
| `/api/nav-history` | GET | Stored firm NAV history |
| `/api/execution-quality` | GET | Slippage/execution quality |
| `/api/benchmarks` | GET | Benchmark returns |
| `/api/correlation` | GET | Cross-pod NAV correlations |
| `/api/risk` | GET | Firm risk halt status |
| `/api/audit` | GET | Recent EventBus audit messages |
| `/api/reports` | GET | Recent generated reports |
| `/ws` | WebSocket | Live dashboard updates |

## Testing

Normal tests force LLM keys off and live Alpaca tests are opt-in.

```powershell
& "C:/Users/PW1868/AppData/Local/Programs/Python/Python312/python.exe" -m pytest tests -q --tb=short
```

Focused checks:

```powershell
& "C:/Users/PW1868/AppData/Local/Programs/Python/Python312/python.exe" -m pytest tests/isolation tests/integration/test_web_service.py -q --tb=short
& "C:/Users/PW1868/AppData/Local/Programs/Python/Python312/python.exe" -m pytest tests/test_trade_proposal.py tests/test_trade_outcomes.py -q --tb=short
```

Live Alpaca tests:

```powershell
$env:RUN_LIVE_ALPACA_TESTS="1"
& "C:/Users/PW1868/AppData/Local/Programs/Python/Python312/python.exe" -m pytest tests/integration/test_live_paper_trade.py -q
```

## Deployment

Local container:

```powershell
docker compose up --build
```

The container serves the already-present static dashboard from `web/dist` and runs FastAPI on port 8000. For production, set explicit CORS origins and keep dashboard session controls disabled unless an operator-only network/auth layer protects them.

## Operational Notes

- Do not commit `.env`, credentials, generated reports, logs, or runtime memory.
- DuckDB can hold Windows file locks; always close `AuditLog`/session resources before deleting temp folders.
- yfinance and news/research adapters should be mocked in tests.
- OpenRouter free-tier models rate-limit often; the LLM helper rotates models and falls back when possible.
- The system should be treated as paper trading unless deployment, keys, broker settings, and kill-switch procedures are reviewed.

## Next Product Work

Recommended next priorities:

- Finish a clean full-suite verification pass on Windows.
- Add dashboard authentication or put it behind an authenticated reverse proxy.
- Reconcile or retire the React/Vite tree.
- Add stronger data-quality/completeness alerts in the live dashboard.
- Add a formal paper-trading launch checklist and runbook.

