# Agentic Hedge Fund — Project TODO

## Completed Milestones

### MVP1 — Core Infrastructure
- [x] EventBus + AuditLog (DuckDB)
- [x] PodNamespace + PodGateway (isolation boundary)
- [x] SimulationClock (backtest replay)
- [x] PortfolioAccountant + BacktestRunner
- [x] RiskManager (rule-based)
- [x] Textual TUI (Firm, Pods, Audit screens)
- [x] 46 tests passing

### MVP2 — Multi-Pod + Governance
- [x] All 5 pods: Alpha (placeholder/Beta), Beta (pairs), Gamma (macro), Delta (event), Epsilon (tail)
- [x] CEO agent (mandate approval via LLM)
- [x] CIO agent (capital allocation via LLM)
- [x] GovernanceOrchestrator (Loop 4/6/7)
- [x] CRO agent (risk constraints)
- [x] Polymarket integration (Gamma Markets API)
- [x] Web dashboard (FastAPI + WebSocket)
- [x] LLM agents switched from OpenAI/Anthropic to OpenRouter (src/core/llm.py)

### MVP3 — Research & Data
- [x] FRED adapter (23 macro indicators)
- [x] GDELT adapter (finance articles)
- [x] RSS adapter (financial news feeds)
- [x] Social feed adapter (news RSS — replaced failed Nitter approach)
- [x] Gamma researcher (Polymarket + FRED + social blend)
- [x] Delta researcher (GDELT + RSS + social)
- [x] Epsilon researcher (VIX + credit spreads from FRED)
- [x] Dashboard: Research tab with 5 sub-tabs (Current, Historical, Contributing, Macro, Social)
- [x] Polymarket macro-relevance filtering
- [x] Historical probability trends (rolling 7-day, 4h intervals, localStorage persistence)
- [x] Tech debt cleanup + test fixes (324/324 passing)
- [ ] EDGAR adapter (skipped — may revisit)
- [ ] Reddit adapter (skipped)
- [ ] Alpha pod researcher (not implemented)

---

## MVP4 — Execution Hardening + Paper Trading

### Priority 1: Accountant Sync (Critical Gap)
- [ ] After Alpaca fill, call `accountant.record_fill(...)` in ExecutionTrader
- [ ] After pushing bars, call `accountant.mark_to_market(prices)` per pod
- [ ] Verify NAV/positions/PnL update correctly in pod summaries

### Priority 2: Execution Hardening
- [ ] Add retry logic to `AlpacaAdapter.place_order()` (timeout, network errors)
- [ ] Add order status polling with configurable timeout
- [ ] Position reconciliation (Alpaca positions vs accountant positions)

### Priority 3: Dashboard Integration
- [ ] Wire fill events to web dashboard (real-time trade display)
- [ ] Add Execution tab: recent fills, open orders, P&L
- [ ] Show live positions per pod

### Priority 4: TUI Visual Effects (Stretch)
- [ ] Building view animations (heartbeat, pod status)
- [ ] Bridge TUI to live session EventBus (currently disconnected)

---

## Backlog
- [ ] Alpha pod: implement dedicated strategy (AI/momentum using LLM)
- [ ] Switch LLM to local Qwen via Ollama (remove OpenRouter dependency)
- [ ] EDGAR adapter for SEC filings (8-K, 10-Q)
- [ ] Deployment packaging (Docker or similar)
