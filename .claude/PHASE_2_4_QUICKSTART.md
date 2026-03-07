# Phase 2.4 Data Hubs - Quick Start Guide

## Overview
Four Bloomberg Terminal-style data visualization hubs integrated into Mission Control's right sidebar panel.

## Accessing the Hubs

In the Mission Control UI, click the tab buttons in the toolbar:

```
┌─────────────────────────────────────────┐
│ [📈 PERFORMANCE] [⚠️ RISK] [⚡ EXECUTION] [⚙️ GOVERNANCE] │
│ [PODS] [TRADES] [ALERTS] [GOVERNANCE]   │
└─────────────────────────────────────────┘
```

---

## Hub 1: Performance Hub (📈)

**Tab:** Click "PERFORMANCE" button in toolbar

### What It Shows
Real-time performance metrics and attribution for all trading pods.

### Key Sections

#### 1. Performance Summary Table
Shows for each pod:
- **Pod**: Pod ID (ALPHA, BETA, GAMMA, DELTA, EPSILON)
- **NAV**: Net Asset Value ($)
- **Daily P&L**: Daily Profit/Loss ($)
- **Daily %**: Daily return percentage
- **Cum Return %**: Cumulative return since inception
- **Sharpe**: Sharpe ratio (risk-adjusted return)
- **Max DD %**: Maximum drawdown percentage
- **Status**: ACTIVE (green) or HALTED (red)

#### 2. NAV Curve (Line Chart)
- **X-Axis**: Time periods
- **Y-Axis**: NAV values
- **Lines**: One per pod, color-coded
- **Use Case**: Track capital growth trajectory
- **Action**: Hover over line for exact values

#### 3. Returns Distribution (Bar Chart)
- **X-Axis**: Return ranges (-2%, -2% to 0%, 0% to 2%, 2% to 4%, >4%)
- **Y-Axis**: Frequency count
- **Use Case**: Understand return distribution shape
- **Interpretation**: Taller bars = more frequent returns in that range

### Reading the Table
```
Pod  │ NAV    │ Daily P&L │ Daily % │ Cum Return % │ Sharpe │ Max DD % │ Status
─────┼────────┼───────────┼─────────┼──────────────┼────────┼──────────┼────────
ALPH │ 1.2M   │ +50K      │ +4.2%   │ +18.5%       │ 0.95   │ 5.2%     │ ACTIVE
BETA │ 980K   │ -30K      │ -3.1%   │ -2.0%        │ 0.42   │ 8.3%     │ HALTED
```

**Color Coding:**
- Green text: Positive values (+P&L, +returns)
- Red text: Negative values (-P&L, -returns)
- Green badge: ACTIVE status
- Red badge: HALTED status

### Use Cases
- ✅ Monitor which pods are outperforming
- ✅ Spot drawdown warnings (Max DD > 5% = caution)
- ✅ Compare Sharpe ratios (higher = better risk-adjusted)
- ✅ Assess cumulative returns vs. objectives

---

## Hub 2: Risk Hub (⚠️)

**Tab:** Click "RISK" button in toolbar

### What It Shows
Real-time risk metrics, exposure heatmaps, and active risk alerts.

### Key Sections

#### 1. Risk Metrics Table
Shows for each pod:
- **Pod**: Pod ID
- **Vol %**: Annualized volatility (%)
- **VaR 95%**: Value-at-Risk at 95% confidence
- **Leverage**: Current leverage multiple (e.g., 1.8x)
- **Drawdown %**: Current peak-to-trough drawdown
- **Max Loss %**: Maximum historical loss
- **Status**: OK (green) or BREACH (red)

**Thresholds (Highlights Red When Exceeded):**
- Leverage > 2.0x
- Drawdown > 5.0%

#### 2. Sector Exposure Heatmap
Visual intensity map showing sector exposure per pod:
```
ALPH │ [████░░░░░░][████░░░░░░][██░░░░░░░░][█░░░░░░░░░][████░░░░░░]
BETA │ [██░░░░░░░░][█████░░░░░][████░░░░░░][███░░░░░░░][██░░░░░░░░]
GAMM │ [███░░░░░░░][██░░░░░░░░][████░░░░░░][██████░░░░][███░░░░░░░]
```

Sectors: TECH, FINANCE, ENERGY, HEALTH, CONSUMER

**Reading:**
- Darker cyan = higher exposure
- Lighter/empty = lower exposure
- Each bar represents 0-100% scale

#### 3. Recent Alerts (Scrollable)
```
⚠️  BETA Leverage exceeded (2.3x) (limit: 2.0x)                    14:32:45
⚠️  ALPH Drawdown warning (4.8%) (limit: 5.0%)                    14:30:12
🔴 GAMMA VaR breach (0.045) (limit: 0.05)                         14:28:30
```

**Alert Severity:**
- **CRITICAL** (red): Hard limit breach
- **WARNING** (yellow): Approaching limit

### Use Cases
- ✅ Monitor leverage in real-time (avoid over-leveraging)
- ✅ Watch sector exposures (avoid concentration)
- ✅ Track volatility by pod
- ✅ Act on critical alerts immediately
- ✅ Manage drawdown to stay within policy limits

### Key Metrics Explained
- **Vol %**: Higher = more volatile returns (risk)
- **VaR 95%**: Maximum expected loss with 95% confidence
- **Leverage**: 1.0x = fully invested, 2.0x = using margin
- **Drawdown %**: Current decline from all-time high

---

## Hub 3: Execution Hub (⚡)

**Tab:** Click "EXECUTION" button in toolbar

### What It Shows
Real-time trade execution metrics and order status tracking.

### Key Sections

#### 1. Execution Statistics (4-Card Layout)
```
┌──────────────┬──────────────┬──────────────┬──────────────┐
│Total Notional│  Fills/Min   │ Avg Slippage │ Total Trades │
│   $2.1M      │     5.2      │   +$12.50    │      47      │
└──────────────┴──────────────┴──────────────┴──────────────┘
```

**Definitions:**
- **Total Notional**: Aggregate trade volume in dollars
- **Fills/Min**: Trades executed per minute
- **Avg Slippage**: Average execution cost vs. mid-price
- **Total Trades**: Count of all orders

#### 2. Order Status Breakdown (3-Card Layout)
```
┌──────────────┬──────────────┬──────────────┐
│   Filled     │   Partial    │   Pending    │
│  40 (85%)    │   5 (10%)    │   2 (5%)     │
└──────────────┴──────────────┴──────────────┘
```

#### 3. Live Trades Table (Scrollable, Max 30 Rows)
```
Time    │ Pod  │ Symbol │ Side │ Qty  │ Fill Price │ Notional │ P&L
────────┼──────┼────────┼──────┼──────┼────────────┼──────────┼──────
14:32:15│ALPHA │AAPL    │BUY   │ 100  │   $150.45  │ $15,045  │ +$500
14:31:50│BETA  │MSFT    │SELL  │ 200  │   $370.12  │ $74,024  │ -$240
14:31:22│GAMMA │GOOGL   │BUY   │  50  │ $2,845.30  │$142,265  │+$1,200
```

**Color Coding:**
- Green **BUY**: Long position
- Red **SELL**: Short position
- Green P&L: Profitable trade
- Red P&L: Loss-making trade

### Use Cases
- ✅ Monitor execution quality (slippage)
- ✅ Track fill rates vs. market conditions
- ✅ Verify order status (filled vs. pending)
- ✅ Audit recent trades for compliance
- ✅ Measure trading costs

### Key Metrics
- **Slippage**: Difference between intended price and actual. Negative = good, positive = cost
- **Fill Rate**: Percentage of orders filled
- **Notional**: Trade size in dollars
- **P&L**: Realized profit/loss from execution

---

## Hub 4: Governance Hub (⚙️)

**Tab:** Click "GOVERNANCE" button in toolbar

### What It Shows
Governance decision history, mandate allocations, and constraint compliance.

### Key Sections

#### 1. Event Type Statistics (4-Card Layout)
```
┌──────────────┬──────────────┬──────────────┬──────────────┐
│ CIO MANDATE  │CRO CONSTRAINT│ CEO OVERRIDE │    AUDIT     │
│      3       │      2       │      0       │      1       │
└──────────────┴──────────────┴──────────────┴──────────────┘
```

**Event Types:**
- **CIO MANDATE**: Allocation or strategy directive
- **CRO CONSTRAINT**: Risk limit or constraint
- **CEO OVERRIDE**: Executive override of normal rules
- **AUDIT**: Compliance or audit event

#### 2. Pod Allocations (Pie Chart, Left Side)
```
Visual 6-color pie chart showing capital allocation across pods:
- ALPHA: 28% (largest slice, cyan)
- BETA:  22% (yellow)
- GAMMA: 18% (green)
- DELTA: 16% (red)
- EPSILON: 16% (orange)
```

#### 3. Event Distribution (Bar Chart, Right Side)
```
Count
   4 │        ┌──┐
   3 │        │  │  ┌──┐
   2 │        │  │  │  │  ┌──┐
   1 │ ┌──┐   │  │  │  │  │  │
   0 └─┴──┴───┴──┴──┴──┴──┴──┘
     CIO  CRO CEO AUDIT
```

#### 4. Governance Events Timeline (Scrollable, Most Recent First)
```
[CIO_MANDATE] 14:30     +5% TECH, -3% ENERGY
               Pods: ALPHA, BETA, GAMMA

[CRO_CONSTRAINT] 14:20  Leverage cap reduced to 1.5x
                 Pods: DELTA, EPSILON

[AUDIT] 14:10           Monthly compliance audit passed
        Pods: ALPHA, BETA, GAMMA, DELTA, EPSILON
```

**Color Coding:**
- 🔵 **CIO_MANDATE**: Cyan (strategic decisions)
- 🟡 **CRO_CONSTRAINT**: Yellow (risk decisions)
- 🔴 **CEO_OVERRIDE**: Red (exceptional actions)
- 🟢 **AUDIT**: Green (verification)

### Use Cases
- ✅ Track allocation mandates and their implementation
- ✅ Monitor CRO constraints and compliance
- ✅ Audit decision history and reasoning
- ✅ Understand capital allocation mix
- ✅ Verify CEO overrides were necessary and documented

### Key Concepts
- **Mandate**: Authorization to allocate capital to specific pods or strategies
- **Constraint**: Risk limit or requirement (e.g., max leverage)
- **Override**: CEO exception to normal governance rules
- **Audit**: Verification that decisions follow approved policies

---

## Navigation Tips

### Switching Tabs
Click tab buttons in toolbar. Instant view switch (no delay).

### Scrolling Within Hubs
- **Tables**: Scroll down to see more rows (headers stay visible)
- **Alerts/Events**: Scroll to see older entries
- **Charts**: Non-interactive (click/zoom not supported in MVP)

### Understanding Data Freshness
- All data updates **every 2 seconds** via WebSocket
- Latest timestamp shown in data (e.g., trade time, alert time)
- Status bar shows "CONNECTED" when receiving data

### Interpreting Colors
```
Color       │ Meaning
────────────┼─────────────────────────────
🟢 Green    │ Positive, OK, Safe, Active
🔴 Red      │ Negative, Breach, Warning, Halted
🟡 Yellow   │ Caution, Approaching limit
🔵 Cyan     │ Focus, Header, Neutral info
```

---

## Troubleshooting

### No Data Showing
**Problem:** Hub shows "Waiting for pod data..." or empty tables
**Solution:**
1. Check WebSocket status (bottom bar shows CONNECTED)
2. Wait 2-3 seconds for first data push
3. Verify backend is running and sending data

### Charts Not Rendering
**Problem:** Charts show as blank or error
**Solution:**
1. Check browser console for errors (F12)
2. Ensure browser width > 1024px
3. Try refreshing page (Ctrl+R)

### High CPU/Slow Performance
**Problem:** Charts lag or sidebar feels sluggish
**Solution:**
1. Reduce number of pods (hide some via config)
2. Increase data update interval (reduce WebSocket frequency)
3. Use Firefox instead of Chrome (better rendering)

### Numbers Seem Wrong
**Problem:** NAV/P&L values don't match backend
**Solution:**
1. Data is **real-time from WebSocket** (not cached)
2. Allow 2-3 seconds for WebSocket sync
3. Check timestamp - ensure you're looking at latest data
4. Verify pod calculations in backend

---

## Integration with Existing Views

The four hubs **coexist with** existing views:
- **PODS**: Individual pod detail cards (original view)
- **TRADES**: Simple trade log (original view)
- **ALERTS**: Risk alert cards (original view)
- **GOVERNANCE**: Text placeholder (original view)

**Recommendation:** Use hubs for monitoring, use detail cards for deep analysis.

---

## Next Steps

### For Users
1. Explore each hub with live trading data
2. Set up monitoring preferences (if available)
3. Configure risk thresholds
4. Create alerts for key metrics
5. Export data for reporting

### For Developers
1. Replace mock WebSocket with real backend connection
2. Add filtering/search capabilities
3. Implement metric customization
4. Add export functionality (CSV/PDF)
5. Create mobile-responsive version (tablet)

---

## Reference Cards

### Performance Metrics Quick Guide
```
Metric      │ Good Value    │ Caution       │ Critical
────────────┼───────────────┼───────────────┼─────────────
Sharpe      │ > 1.0         │ 0.5 - 1.0     │ < 0.5
Max DD      │ < 5%          │ 5% - 10%      │ > 10%
Vol         │ < 20%         │ 20% - 30%     │ > 30%
Return      │ > 5% annual   │ 0% - 5%       │ < 0% loss
Leverage    │ 1.0x - 1.5x   │ 1.5x - 2.0x   │ > 2.0x
```

### Risk Limits (Institutional Standards)
```
Metric              │ Limit
────────────────────┼─────────
Leverage            │ 2.0x
Drawdown            │ 5.0%
Single Position     │ 5% of AUM
Sector Exposure     │ 15% max
Daily Loss          │ 2% of AUM
VaR 95%             │ 0.05
```

---

## Glossary

- **NAV**: Net Asset Value = Total Assets - Total Liabilities
- **P&L**: Profit/Loss = Realized gain or loss on trade
- **Sharpe**: Risk-adjusted return = (Return - RiskFree) / Volatility
- **VaR 95%**: Maximum loss with 95% confidence in 1 day
- **Drawdown**: Peak-to-trough decline from all-time high
- **Leverage**: Debt/Equity ratio = Total Assets / Equity
- **Vol**: Annualized volatility = Standard deviation of returns
- **Slippage**: Execution cost = Mid-price - Actual price
- **Notional**: Trade value = Quantity × Price
- **Fill Rate**: Percentage of orders that executed
