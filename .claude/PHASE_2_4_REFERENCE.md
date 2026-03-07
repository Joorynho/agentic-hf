# Phase 2.4 Quick Reference Card

## Files at a Glance

| File | Type | Size | Purpose |
|------|------|------|---------|
| PerformanceHub.tsx | Component | 7.3 KB | NAV curves, returns, Sharpe |
| RiskHub.tsx | Component | 7.2 KB | Vol, VaR, leverage, alerts |
| ExecutionHub.tsx | Component | 6.7 KB | Fills, slippage, live trades |
| GovernanceHub.tsx | Component | 7.3 KB | Mandates, events, allocations |
| DataPanel.tsx | Component | 4.1 KB | Router for all views |
| Toolbar.tsx | Component | 2.3 KB | Tab navigation |

## Design Cheat Sheet

### Colors (No Gradients!)
```
Primary:   #0b0f14 (bg), #ffffff (text)
Secondary: #1a1f2e (cards), #a0aec0 (labels)
Tertiary:  #718096 (timestamps)
Accent:    #00d9ff (cyan), #ff4757 (red), #2ed573 (green)
Border:    #4a5568 (steel-blue)
```

### Spacing Values
```
Tight:    py-1 px-2     (8px v, 16px h) — table rows
Compact:  p-2           (8px) — cards
Standard: p-3           (12px) — panels
Gap:      gap-2         (8px) — flex items
```

### Component Patterns

**Table Header**
```tsx
<thead className="sticky top-0 bg-bg-secondary">
  <tr className="border-b border-steel-blue">
    <th className="text-left py-2 px-2 text-text-secondary">Label</th>
  </tr>
</thead>
```

**Status Badge**
```tsx
<span className="px-2 py-0.5 rounded text-xs inline-block border
  bg-green-900/40 text-green-400 border-green-700">ACTIVE</span>
```

**Alert**
```tsx
<div className="text-xs font-mono py-1 px-2 rounded border
  bg-accent-red/20 border-accent-red text-accent-red">
  {message}
</div>
```

**Chart Container**
```tsx
<div className="bg-bg-secondary rounded border border-steel-blue p-2">
  <div className="text-xs text-text-secondary mb-1 uppercase">Title</div>
  <ResponsiveContainer width="100%" height={200}>
    {/* Recharts chart */}
  </ResponsiveContainer>
</div>
```

## Data Types Quick Reference

```typescript
PodSummary {
  pod_id: string              // ALPHA, BETA, GAMMA, DELTA, EPSILON
  nav: number                 // Net Asset Value
  daily_pnl: number           // Daily profit/loss
  status: 'ACTIVE'|'HALTED'|'RISK'
  risk_metrics: {
    leverage: number          // e.g., 1.8
    vol_ann: number          // e.g., 0.18 (18%)
    var_95: number           // e.g., 0.03
    drawdown: number         // e.g., 0.05 (5%)
    max_loss: number         // e.g., 0.10 (10%)
  }
  positions: Position[]
  timestamp: string           // ISO 8601
}

TradeEvent {
  order_id, pod_id, symbol, side: 'BUY'|'SELL'
  qty: number, fill_price: number, timestamp, pnl?
}

RiskAlert {
  alert_id, pod_id
  severity: 'WARNING'|'CRITICAL'
  message, metric, threshold, current_value, timestamp
}

GovernanceEvent {
  event_id
  event_type: 'CIO_MANDATE'|'CRO_CONSTRAINT'|'CEO_OVERRIDE'|'AUDIT'
  description, affected_pods: string[], timestamp
}
```

## Using the Hubs

### For Traders
1. **Performance Tab** → Check NAV and Sharpe ratio
2. **Risk Tab** → Monitor leverage (< 2.0x) and drawdown (< 5%)
3. **Execution Tab** → Review today's fills and slippage
4. **Governance Tab** → Verify allocation mandates

### For Risk Managers
1. **Risk Tab** → Primary view for monitoring
2. **Governance Tab** → Track constraint changes
3. **Performance Tab** → Assess returns vs. risk
4. **Execution Tab** → Verify execution quality

### Data Freshness
- Updates: Every 2 seconds
- Latency: < 50ms from WebSocket to UI
- Status: Check bottom bar for "CONNECTED"

## Common Tasks

### Reading Performance Table
```
ALPHA │ NAV: 1.2M │ Daily P&L: +50K │ Daily %: +4.2% │ Sharpe: 0.95 │ Max DD: 5.2% │ ACTIVE
```
→ Good performance (Sharpe > 0.8, DD < 5%)

### Interpreting Risk Heatmap
```
ALPH │ [████░░░░░░][████░░░░░░][██░░░░░░░░] [█░░░░░░░░░] [████░░░░░░]
     │  TECH 80%     FINANCE 80%   ENERGY 20%  HEALTH 10%  CONSUMER 80%
```
→ High TECH and CONSUMER exposure, low diversification in ENERGY

### Understanding Execution Stats
```
Total Notional: $2.1M      | Fills/Min: 5.2    | Slippage: +$12.50
                40 Filled (85%), 5 Partial (10%), 2 Pending (5%)
```
→ Good fill rate, average slippage cost $12.50 per trade

### Governance Event Colors
- 🔵 **CIO_MANDATE** (Cyan) = Allocation decision
- 🟡 **CRO_CONSTRAINT** (Yellow) = Risk limit
- 🔴 **CEO_OVERRIDE** (Red) = Exception approval
- 🟢 **AUDIT** (Green) = Compliance check

## Installation Quick Start

```bash
# Development
cd web
npm install
npm run dev                    # http://localhost:5173

# Production
npm run build
npm run preview
```

## Troubleshooting Quick Fix

| Problem | Solution |
|---------|----------|
| No data showing | Check WebSocket (Network tab) |
| Charts blank | Ensure parent has height (flex-1) |
| Slow rendering | Reduce visible rows, increase update interval |
| Colors wrong | Check CSS load (DevTools), monitor calibration |
| Type errors | Verify useWebSocket() import path (@/hooks) |

## Key Metrics Explained

| Metric | Formula | Good Value | Caution |
|--------|---------|------------|---------|
| Sharpe | (Return - Rf) / Vol | > 1.0 | < 0.5 |
| Max DD | (Peak - Trough) / Peak | < 5% | > 10% |
| VaR 95% | 95% confidence loss | < 0.05 | > 0.10 |
| Leverage | Total Assets / Equity | 1.0-1.5x | > 2.0x |
| Slippage | Mid Price - Fill Price | < $0.10 | > $1.00 |

## WebSocket Message Format

```json
{
  "type": "pod_summary",
  "data": {...},
  "timestamp": "2026-03-07T14:32:15Z"
}
```

Types: `pod_summary`, `trade_executed`, `risk_alert`, `governance_event`

## Important Links

- 📖 User Guide: `PHASE_2_4_QUICKSTART.md`
- 🎨 Design System: `DATA_HUBS_DESIGN_GUIDE.md`
- 🔧 Technical Docs: `PHASE_2_4_TECHNICAL_DETAILS.md`
- ✅ Summary: `PHASE_2_4_DELIVERY_SUMMARY.md`
- 📋 Main: `PHASE_2_4_README.md`

## One-Liner Summary

**Four Bloomberg Terminal-style real-time dashboards (Performance, Risk, Execution, Governance) with monospace fonts, dark theme, and high-density data visualization for institutional traders.**

---

**Status:** ✅ Production Ready | **Date:** 2026-03-07 | **Scope:** Phase 2.4 Complete
