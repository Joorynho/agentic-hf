# Mission Control — Agentic Hedge Fund Platform

A multi-agent hedge fund simulation platform with real-time trading dashboard, governance enforcement, and comprehensive risk management. Built with Python async agents, FastAPI, React + Three.js, and paper trading via Alpaca.

## Quick Start (5 minutes)

### Prerequisites
- Python 3.12+
- Node.js 18+
- `.env` file with Alpaca credentials (see `.env.example`)

### Development Mode

#### Terminal 1: Python Backend
```bash
# Install dependencies
pip install -r requirements.txt

# Start FastAPI server
python -m uvicorn src.web.server:app --reload --port 8000
```

#### Terminal 2: React Development Server
```bash
cd web
npm install
npm run dev
```

Open http://localhost:3000 in your browser.

### Production Mode

#### Build Everything
```bash
# Build React frontend
cd web
npm run build
cd ..

# Start full-stack (Python + served React static files)
python -m uvicorn src.web.server:app --host 0.0.0.0 --port 8000
```

Navigate to http://localhost:8000.

---

## Architecture

### Backend (Python)
- **EventBus**: Central async event broker for inter-pod communication
- **SessionManager**: Orchestrates live trading sessions with 5 isolated strategy pods
- **Pod Runtimes**: Each pod has isolated state (PodNamespace) and 6 specialized agents:
  - Researcher (market data + signals)
  - Signal Agent (alpha generation)
  - PM Agent (portfolio construction)
  - Risk Agent (per-pod constraints)
  - Execution Trader (order placement)
  - Ops Agent (monitoring)
- **Governance Agents** (firm-level):
  - CEO: Session oversight and reporting
  - CIO: Capital allocation mandates
  - CRO: Risk enforcement (never LLM-based)
- **FastAPI Web Server**: REST API + WebSocket for real-time dashboard updates
- **SessionLogger**: Structured logging of trades, reasoning, and governance decisions

### Frontend (React + Three.js)
- **3D Building Visualization**: 6-floor building representing pods and governance
- **Real-time Data Panel**: Live metrics (NAV, positions, risk)
- **Governance Hub**: Capital allocation, breach alerts, CRO halts
- **Performance Dashboard**: Cumulative returns, Sharpe, max drawdown
- **Execution Hub**: Live trade feed with timestamps

### Data Flow
```
Alpaca (market data)
    ↓
SessionManager (fetch bars every 60s)
    ↓
Pod Runtimes (process signals, construct portfolios)
    ↓
EventBus (publish pod summaries, trade events, governance)
    ↓
FastAPI (REST API + WebSocket)
    ↓
React (3D visualization + charts)
```

---

## Configuration

### Environment Variables

Create a `.env` file from `.env.example`:

```bash
# Alpaca Paper Trading
ALPACA_API_KEY=your_alpaca_api_key
ALPACA_SECRET_KEY=your_alpaca_secret_key

# Web Service
FASTAPI_HOST=127.0.0.1
FASTAPI_PORT=8000
ENVIRONMENT=development

# Optional: Polymarket (MVP2+)
POLYMARKET_API_KEY=your_polymarket_key

# Optional: News APIs (MVP3+)
GDELT_API_KEY=your_gdelt_key
FRED_API_KEY=your_fred_key
EDGAR_API_KEY=your_edgar_key
```

### React Environment Variables

Create a `web/.env.local` file from `web/.env.example`:

```bash
VITE_API_URL=http://localhost:8000
VITE_WS_URL=ws://localhost:8000/ws
```

---

## Running a Live Trading Session

### Option A: Direct Python

```python
import asyncio
from src.execution.paper.alpaca_adapter import AlpacaAdapter
from src.mission_control.session_manager import SessionManager

async def main():
    alpaca = AlpacaAdapter()  # Uses ALPACA_API_KEY from .env
    manager = SessionManager(
        alpaca_adapter=alpaca,
        enable_web_server=True  # Enable dashboard
    )

    # Start session: 5 pods × $100 each
    await manager.start_live_session(
        capital_per_pod=100.0,
        initial_symbols=["AAPL", "MSFT", "GOOGL", "TSLA", "AMZN"]
    )

    # Run event loop: fetch bars, run governance every 5 iterations
    await manager.run_event_loop(
        interval_seconds=60.0,  # 60s between iterations
        governance_freq=5       # Governance every 5 min
    )

asyncio.run(main())
```

### Option B: Docker Compose

```bash
docker-compose up --build
```

Navigate to http://localhost:8000.

### Option C: Command Line

```bash
# Start trading session with web dashboard
python -c "
import asyncio
from src.execution.paper.alpaca_adapter import AlpacaAdapter
from src.mission_control.session_manager import SessionManager

async def main():
    mgr = SessionManager(
        enable_web_server=True
    )
    await mgr.start_live_session(capital_per_pod=100.0)
    await mgr.run_event_loop(interval_seconds=60.0)

asyncio.run(main())
"
```

Then open http://localhost:8000 in your browser.

---

## API Endpoints

### REST API

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/health` | GET | Health check |
| `/api/session` | GET | Session info (capital, iteration, uptime) |
| `/api/pods` | GET | List all pods + current metrics |
| `/api/pods/{pod_id}` | GET | Pod detail (positions, risk metrics) |
| `/api/risk` | GET | Risk status (halt, breached pods) |
| `/api/audit` | GET | Audit log entries (future) |

### WebSocket

**Endpoint**: `ws://localhost:8000/ws`

**Message Types**:
- `pod_summary`: Pod metrics update (every iteration)
- `governance_event`: Governance cycle results (every N iterations)
- `risk_alert`: Risk constraint breach (asynchronous)

**Example Client**:
```javascript
const ws = new WebSocket('ws://localhost:8000/ws');

ws.onmessage = (event) => {
  const message = JSON.parse(event.data);
  console.log(message.type, message);
};

ws.send(JSON.stringify({action: 'get_status'}));
```

---

## Testing

### Run All Tests
```bash
python -m pytest tests/ -v
```

### Run Web Service Tests Only
```bash
python -m pytest tests/integration/test_web_dashboard_e2e.py -v
```

### Run with Coverage
```bash
python -m pytest tests/ --cov=src --cov-report=html
```

### Key Test Suites
- **Isolation Tests** (`tests/isolation/`): Pod isolation boundaries
- **Integration Tests** (`tests/integration/`):
  - MVP1: Single pod + backtest + TUI
  - MVP2: All 5 pods + LLM governance
  - MVP3: News scrapers + researchers
  - MVP4: Execution + paper trading + web dashboard
- **Web Tests** (`tests/integration/test_web_dashboard_e2e.py`): 26+ tests covering:
  - REST endpoints
  - WebSocket connections
  - State persistence
  - Error handling
  - Performance (100 concurrent connections)

---

## Deployment

### Local Deployment (Recommended for MVP)

```bash
# 1. Build React
cd web && npm run build && cd ..

# 2. Start FastAPI (serves static files)
python -m uvicorn src.web.server:app --port 8000
```

Navigate to http://localhost:8000.

### Docker Deployment

```bash
# Build and run
docker-compose up --build

# Or manually
docker build -t mission-control:latest .
docker run -p 8000:8000 \
  -e ALPACA_API_KEY=$ALPACA_API_KEY \
  -e ALPACA_SECRET_KEY=$ALPACA_SECRET_KEY \
  mission-control:latest
```

### Cloud Deployment

The project is containerized and can be deployed to:
- **Heroku**: `git push heroku main`
- **Railway**: Connected via git
- **AWS ECS/Fargate**: Use Dockerfile + docker-compose.yml
- **Google Cloud Run**: Deploy with Dockerfile
- **Azure Container Instances**: Use Dockerfile

Example for Railway/Heroku:
```bash
# Set environment variables
heroku config:set ALPACA_API_KEY=...
heroku config:set ALPACA_SECRET_KEY=...

# Deploy
git push heroku main
```

---

## Monitoring & Logging

### Session Logs

All session activity is logged to `logs/session_<timestamp>/`:

```
logs/session_2025-03-07_143022/
├── session.md           # Markdown summary
├── trades.jsonl         # Trade executions
├── reasoning/           # Agent reasoning logs
├── governance.md        # CIO/CEO/CRO decisions
└── audit.db            # DuckDB audit log
```

### Real-time Monitoring

**Option 1: Tail Session Log**
```bash
tail -f logs/session_*/session.md
```

**Option 2: Dashboard WebSocket**
Open http://localhost:8000 and watch real-time updates.

**Option 3: API Polling**
```bash
# Poll session status every 5 seconds
watch -n 5 'curl -s http://localhost:8000/api/session | jq'
```

---

## Development Workflow

### Adding a New Feature

1. **Create Feature Branch**
   ```bash
   git checkout -b feature/your-feature
   ```

2. **Write Tests First** (TDD)
   ```bash
   # Create test in tests/integration/test_your_feature.py
   python -m pytest tests/integration/test_your_feature.py -v
   ```

3. **Implement Feature**
   ```bash
   # Implement in src/
   ```

4. **Run Full Test Suite**
   ```bash
   python -m pytest tests/ -v
   ```

5. **Commit & Push**
   ```bash
   git add .
   git commit -m "feat: add your feature"
   git push origin feature/your-feature
   ```

6. **Create Pull Request** on GitHub

### Project Structure

```
.
├── src/
│   ├── core/              # EventBus, models, clock
│   ├── agents/            # CEO, CIO, CRO
│   ├── pods/              # Pod templates (Alpha, Beta, Gamma, Delta, Epsilon)
│   ├── backtest/          # Portfolio accounting, backtesting
│   ├── execution/         # Alpaca adapter, execution logic
│   ├── mission_control/   # SessionManager, SessionLogger, TUI
│   └── web/               # FastAPI server, WebSocket, REST API
├── web/                   # React + Three.js frontend
├── tests/
│   ├── isolation/         # Pod isolation proofs
│   └── integration/       # End-to-end tests
├── Dockerfile             # Multi-stage build
├── docker-compose.yml     # Local dev + cloud deployment
├── requirements.txt       # Python dependencies
└── README.md             # This file
```

---

## Troubleshooting

### "ALPACA_API_KEY not found"
- Copy `.env.example` to `.env`
- Add your Alpaca paper trading credentials

### "Module not found" errors
- Install dependencies: `pip install -r requirements.txt`
- Ensure Python 3.12+: `python --version`

### React build fails
- Clear node_modules: `rm -rf web/node_modules`
- Reinstall: `cd web && npm ci && cd ..`

### WebSocket connection fails
- Verify FastAPI is running: `curl http://localhost:8000/health`
- Check browser console for CORS errors
- Ensure `VITE_WS_URL` is set correctly in `web/.env.local`

### Tests fail
- Run with more verbose output: `pytest -vv --tb=long`
- Check `.env` is configured: `grep ALPACA_API_KEY .env`
- Ensure DuckDB is not locked: `rm -rf logs/` and retry

---

## MVP Milestones

- **MVP1** ✅ Single pod + backtest engine + TUI
- **MVP2** 🔜 All 5 pods + LLM governance (CEO, CIO, CRO)
- **MVP3** 🔜 News scrapers (GDELT, FRED, EDGAR, Reddit, X)
- **MVP4** ✅ Paper trading (Alpaca) + web dashboard + execution

---

## Performance Targets

| Metric | Target | Current |
|--------|--------|---------|
| Event loop latency | <100ms | ~50ms |
| WebSocket broadcast | <50ms | ~20ms |
| React 3D frame rate | 60fps | 60fps (Vite dev), 60fps (prod) |
| Concurrent WebSocket clients | 1000+ | Tested to 100+ |
| API response time | <200ms | ~20-50ms |
| Pod isolation | Complete | ✅ Verified |
| Risk enforcement | No breaches | ✅ CRO rule-based |

---

## Roadmap (Post-MVP4)

- [ ] Multi-broker support (Alpaca, Interactive Brokers, etc.)
- [ ] ML-based signal agents (using Claude SDK)
- [ ] Live market connectivity (FIX protocol)
- [ ] Advanced risk models (VaR, CVaR, stress testing)
- [ ] Backtesting dashboard with parameter sweeps
- [ ] Paper → Live trading mode switch
- [ ] REST API documentation (OpenAPI/Swagger)
- [ ] Mobile responsiveness (iPad, mobile trading)
- [ ] Real-time audio alerts
- [ ] Plugin system for custom agents

---

## Support & Contributions

For issues, questions, or contributions:
1. Check the [GitHub Issues](https://github.com/your-org/agentic-hf/issues)
2. Review [CLAUDE.md](./CLAUDE.md) for development guidelines
3. Submit PRs following the branching workflow above

---

## License

[Your License Here]

---

## Acknowledgments

Built as part of the Anthropic Claude Agent SDK initiative. Inspired by real hedge fund operations: multi-agent decision-making, governance enforcement, risk management, and execution.

---

Last updated: March 7, 2025
