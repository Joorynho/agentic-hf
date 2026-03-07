# Mission Control Web - React SPA for Agentic Hedge Fund

A sophisticated React + Three.js 3D visualization dashboard for real-time monitoring of an institutional hedge fund platform with 5 isolated strategy pods and firm-level governance.

## Architecture Overview

### Technology Stack
- **React 18** with TypeScript 5
- **Three.js** (r158) for 3D building viewport
- **Vite** for rapid development and optimized builds
- **Tailwind CSS** with custom dark theme (#0B0F14 background, cyan/red accents)
- **WebSocket** for real-time pod data and event streaming
- **GSAP + Lenis** for smooth animations and scroll interactions

### Project Structure

```
web/
├── public/
│   └── index.html                 # Entry point
├── src/
│   ├── index.tsx                  # React root mount
│   ├── App.tsx                    # Main app layout (3-column grid)
│   ├── App.css                    # Global app styles + animations
│   │
│   ├── contexts/
│   │   └── WebSocketContext.tsx   # Real-time data state management
│   │
│   ├── components/
│   │   ├── ThreeDCanvas.tsx       # 3D building viewport (2/3 width)
│   │   ├── DataPanel.tsx          # Right sidebar panel (1/3 width)
│   │   ├── PodMetrics.tsx         # Individual pod stats card
│   │   ├── RiskAlert.tsx          # Risk violation notification
│   │   └── Toolbar.tsx            # Top nav with view tabs
│   │
│   ├── hooks/
│   │   ├── useWebSocket.ts        # Hook for WebSocket context
│   │   ├── useThreeScene.ts       # Three.js setup utility
│   │   └── useScrollTrigger.ts    # Scroll event handler
│   │
│   ├── types/
│   │   └── index.ts               # TypeScript interfaces (PodSummary, TradeEvent, etc.)
│   │
│   └── styles/
│       └── globals.css            # Tailwind imports + CSS variables
│
├── package.json                   # npm dependencies
├── tsconfig.json                  # TypeScript configuration
├── vite.config.ts                 # Vite build configuration
├── tailwind.config.js             # Tailwind color + theme config
└── postcss.config.js              # PostCSS with Tailwind + Autoprefixer
```

## Setup & Installation

### Prerequisites
- Node.js 18+ (LTS)
- npm 9+ or yarn 3+

### Development Server

```bash
cd web

# Install dependencies
npm install

# Start Vite dev server (localhost:3000)
npm run dev

# Type checking
npm run type-check
```

The app will connect to WebSocket at `ws://localhost:8000/ws` by default. Update `src/App.tsx` if your FastAPI backend is on a different host.

### Production Build

```bash
npm run build      # Compile TypeScript + bundle with Vite
npm run preview    # Preview production build locally
```

## Component Overview

### ThreeDCanvas (2/3 viewport)
- **6 semantic floors** representing operational domains:
  1. Risk Management (CRO constraints)
  2. Execution Engine (order routing)
  3. Research Lab (market signals)
  4. AI Systems (pod strategy agents)
  5. Treasury (capital allocation)
  6. Governance (CEO/CIO policy layer)
- **Interactive hover/click**: Floors highlight on mouseover; click to expand details
- **Real-time coloring**: Green (ACTIVE), Red (RISK), Orange (HALTED) based on pod status
- **3D lighting**: Directional + ambient lighting with shadow maps for depth
- **Subtle animations**: Gentle building rotation, dynamic point lights per floor

### DataPanel (1/3 sidebar)
- **Toolbar tabs**: PODS | TRADES | ALERTS | GOVERNANCE
- **WebSocket status indicator**: Green (connected), Orange (connecting), Red (error)
- **Pod metrics view**: 5 pod summary cards with NAV, daily P&L, leverage, VaR, drawdown
- **Expandable pod details**: Click to view live positions, unrealized P&L, return %
- **Trade history**: Last 20 executed trades with fills, qty, prices
- **Risk alerts**: Live risk constraint violations with severity badges
- **Governance events**: CIO mandates, CRO constraints, CEO overrides (MVP2)

### WebSocketContext
**Real-time state management** for all firm and pod data:
```typescript
interface WebSocketContextType {
  pods: Map<string, PodSummary>           // 5 strategy pods indexed by id
  trades: TradeEvent[]                    // Last 100 trades (FIFO)
  riskAlerts: RiskAlert[]                 // Last 50 active alerts
  governanceEvents: GovernanceEvent[]     // Last 50 governance actions
  isConnected: boolean                    // WebSocket connection status
  wsStatus: 'connected' | 'connecting' | 'disconnected' | 'error'
  lastUpdate: number                      // Timestamp of last data update
  error: string | null                    // Connection error message
}
```

**Message Types** received from FastAPI backend:
- `pod_summary`: Update a single pod's metrics and positions
- `trade`: New trade execution notification
- `risk_alert`: Risk constraint violation
- `governance_event`: Firm-level governance action
- `batch_update`: Multiple data types in one message (for efficiency)

### Data Types (src/types/index.ts)

```typescript
// Pod operational summary (ONLY thing crossing pod isolation boundary)
interface PodSummary {
  pod_id: string                    // 'alpha' | 'beta' | 'gamma' | 'delta' | 'epsilon'
  nav: number                       // Net asset value in USD
  daily_pnl: number                 // Today's P&L
  status: 'ACTIVE' | 'HALTED' | 'RISK'
  risk_metrics: {
    leverage: number                // Current leverage ratio
    vol_ann: number                 // Annualized volatility
    var_95: number                  // 95% VaR (daily % loss)
    drawdown: number                // Current drawdown from peak
    max_loss: number                // Max historical loss
  }
  positions: Position[]              // Current open positions
  timestamp: string                 // ISO-8601 update time
}

// Individual security holding
interface Position {
  symbol: string                    // Ticker (AAPL, MSFT, etc.)
  qty: number                       // Quantity held
  current_price: number             // Market price
  unrealized_pnl: number            // Unrealized profit/loss
  pnl_percent: number               // Return % on position
}

// Trade execution record
interface TradeEvent {
  order_id: string
  pod_id: string
  symbol: string
  side: 'BUY' | 'SELL'
  qty: number
  fill_price: number
  timestamp: string
}

// Risk constraint violation
interface RiskAlert {
  alert_id: string
  pod_id: string
  severity: 'WARNING' | 'CRITICAL'
  message: string
  metric: string                    // e.g., 'leverage', 'drawdown', 'var'
  threshold: number                 // Limit that was breached
  current_value: number             // Actual value
  timestamp: string
}

// Governance action (CEO/CIO/CRO)
interface GovernanceEvent {
  event_id: string
  event_type: 'CIO_MANDATE' | 'CRO_CONSTRAINT' | 'CEO_OVERRIDE' | 'AUDIT'
  description: string
  affected_pods: string[]
  timestamp: string
}
```

## Styling & Theme

### Dark Theme CSS Variables
```css
--bg-primary: #0b0f14         /* Main background */
--bg-secondary: #1a1f2e       /* Card/panel backgrounds */
--bg-tertiary: #2d3748        /* Hover/elevated states */
--text-primary: #ffffff        /* Main text */
--text-secondary: #a0aec0     /* Secondary text */
--text-tertiary: #718096      /* Tertiary/disabled text */
--accent-cyan: #00d9ff        /* Primary interactive color */
--accent-red: #ff4757         /* Error/risk color */
--accent-green: #2ed573       /* Success/active color */
--border-color: #2d3748       /* Border colors */
```

### Utility Classes
- `.glass` / `.glass-strong`: Frosted glass effect with backdrop blur
- `.glow-cyan` / `.glow-red` / `.glow-green`: Color-specific glow effects
- `.animate-fade-in` / `.animate-slide-in`: Transition animations
- `.btn-primary` / `.btn-secondary`: Styled buttons

## WebSocket Integration

### Connection Setup (Auto-Reconnect)
```typescript
// Configured in WebSocketProvider
- URL: ws://localhost:8000/ws  (override in App.tsx)
- Auto-reconnect: Enabled (3-second intervals, max 5 attempts)
- Fallback: Shows "DISCONNECTED" / "ERROR" status in toolbar
```

### Example Message Flow
```
1. Page loads → WebSocketProvider connects to ws://localhost:8000/ws
2. Server sends: { type: 'batch_update', data: { pods: [...], trades: [...] } }
3. Context updates state → Components re-render
4. ThreeDCanvas recolors floors based on pod.status
5. DataPanel displays tabs with live data
```

### Sending Data from FastAPI
```python
# Python (FastAPI)
import json
from starlette.websockets import WebSocket

async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()

    # Send pod summary
    await websocket.send_json({
        "type": "pod_summary",
        "data": {
            "pod_id": "alpha",
            "nav": 1000000.00,
            "daily_pnl": 15000.00,
            "status": "ACTIVE",
            "risk_metrics": {...},
            "positions": [...],
            "timestamp": "2026-03-07T14:30:00Z"
        }
    })
```

## Performance Notes

### Three.js Optimization
- **Shadow maps**: 2048x2048 resolution (balance quality vs. performance)
- **Pixel ratio**: Capped at 2x (high DPI devices don't overkill rendering)
- **Fog**: Reduces draw distance for far objects
- **Point lights**: One per floor, limited distance/decay

### React Optimization
- **Context memo**: WebSocketContext only triggers re-renders on actual data changes
- **PodMetrics expandable**: Positions are in virtual scroll within card
- **Lazy trades/alerts**: Sliced to last 20/50 items, not rendering 1000s
- **Tailwind**: Pure CSS, no runtime overhead

### Network Optimization
- **Batch messages**: Prefer `batch_update` over individual messages when possible
- **Throttle updates**: Pod data updates maybe 1-2Hz max (not per tick)
- **Gzip compression**: Enabled by default in WebSocket + HTTP

## Debugging

### Console Logs
```javascript
// WebSocket connection events logged to console
[WebSocket] Connected to ws://localhost:8000/ws
[WebSocket] Unknown message type: foobar
[WebSocket] Failed to parse message: SyntaxError: ...
```

### Dev Tools
- **React DevTools**: Inspect component tree, prop changes
- **Network tab**: View WebSocket messages in real time (Chrome DevTools → Network → WS)
- **Three.js Inspector**: Browser extension for inspecting Three.js objects

### Vite HMR
- Hot Module Replacement enabled: Change `.tsx` files, see updates instantly (no refresh)
- CSS changes: Reflected immediately without JS reload

## Deployment

### Build Artifacts
```bash
npm run build
# Creates dist/ folder with:
# - index.html (optimized, assets inlined)
# - js/main.*.js (production bundle)
# - css/style.*.css (Tailwind optimized)
```

### Serving from FastAPI
```python
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

app = FastAPI()

# Serve built React app
app.mount("/", StaticFiles(directory="web/dist", html=True), name="static")
```

Then access at `http://localhost:8000` (same origin as WebSocket).

### Environment Variables
Update `wsUrl` in `App.tsx` for production:
```typescript
// Development
wsUrl={`ws://localhost:8000/ws`}

// Production
wsUrl={`wss://${window.location.hostname}/ws`}  // HTTPS + WSS
```

## Roadmap (MVP2+)

- **GSAP animations**: Floor transitions, data panel slide-ins
- **Lenis smooth scroll**: Full-page scroll with 3D parallax
- **Recharts integration**: Embed mini charts in pod detail view
- **Pod floor details**: Click floor → overlay with detailed metrics, position ladder, P&L curve
- **Governance timeline**: Visual history of CEO/CIO/CRO actions
- **Performance heatmap**: 3D color gradient showing pod performance over time
- **Export/reporting**: Download pod summaries, trade logs as CSV/JSON

## Troubleshooting

### "WebSocket is DISCONNECTED"
- Verify FastAPI server is running on port 8000
- Check browser console for network errors
- Confirm CORS headers if running on different domains

### "Module not found" errors
- Run `npm install` again
- Check that all imports use `./` (relative) or `@/` (path alias)
- Verify file extensions (`.ts`, `.tsx`)

### 3D viewport is blank / black
- Check that browser supports WebGL (most modern browsers do)
- Verify GPU drivers are up-to-date
- Check browser console for Three.js errors

### Styles not applying
- Ensure Tailwind CSS is compiled (`npm run build`)
- Check that color names match tailwind.config.js
- Clear browser cache (Cmd+Shift+Delete / Ctrl+Shift+Delete)

## License

Internal use only - Agentic Hedge Fund Platform
