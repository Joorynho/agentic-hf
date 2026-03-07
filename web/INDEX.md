# Phase 2.2 - Web Project File Index

Complete file listing and quick reference for the Mission Control React SPA.

## Project Location
```
C:\Users\PW1868\Agentic HF\web\
```

## File Structure

### Documentation (Start Here)
```
web/
├── README.md                      ← Full technical documentation (500+ lines)
├── SETUP.md                       ← Quick start guide with troubleshooting
├── PHASE_2_2_DELIVERY.md         ← Detailed delivery manifest
├── INDEX.md                       ← This file
└── .gitignore                     ← Git exclusions
```

**Reading order:**
1. Start: `SETUP.md` (5-minute setup)
2. Learn: `README.md` (full technical reference)
3. Deep dive: `PHASE_2_2_DELIVERY.md` (feature manifest)

### Configuration Files
```
web/
├── package.json                   ← npm dependencies & scripts
│   └── Scripts: dev, build, preview, type-check
│
├── tsconfig.json                  ← TypeScript strict mode config
├── tsconfig.node.json             ← Vite config TypeScript settings
├── vite.config.ts                 ← Vite dev server & build setup
│   └── HMR enabled, API proxy to localhost:8000
│
├── tailwind.config.js             ← Dark theme colors & typography
│   └── Custom colors: bg-primary, accent-cyan, accent-red, etc.
│
└── postcss.config.js              ← CSS processing (Tailwind + Autoprefixer)
```

**Run from web/ directory:**
```bash
npm install               # Install dependencies (one-time)
npm run dev              # Start dev server (localhost:3000)
npm run build            # Production build (creates dist/)
npm run type-check       # TypeScript type checking
```

### Public Assets
```
web/public/
└── index.html                     ← HTML entry point
    ├── Imports JetBrains Mono font
    ├── Script: /src/index.tsx
    └── Root div: id="root"
```

### Source Code - Entry Points
```
web/src/
├── index.tsx                      ← React DOM render root
│   └── ReactDOM.createRoot(document.getElementById('root'))
│
└── App.tsx                        ← Main app component (3-column layout)
    ├── Imports: WebSocketProvider, ThreeDCanvas, DataPanel
    ├── Layout: grid-cols-3 (2/3 + 1/3)
    └── Props: wsUrl from window.location.hostname:8000
```

### Components
```
web/src/components/
├── ThreeDCanvas.tsx               ← 3D building viewport (2/3 width)
│   ├── 6 semantic floors (Risk → Governance)
│   ├── Three.js scene with lighting & shadows
│   ├── Real-time floor coloring (Green/Red/Orange)
│   ├── Hover/click interactive detection
│   ├── Animation loop (60 FPS target)
│   └── Uses: three.js, useWebSocket
│
├── DataPanel.tsx                  ← Right sidebar container (1/3 width)
│   ├── Wraps Toolbar + View container
│   ├── Manages activeView state
│   ├── Renders 4 view tabs
│   └── Uses: useWebSocket, PodMetrics, RiskAlert
│
├── Toolbar.tsx                    ← Top navigation bar
│   ├── View tabs: PODS | TRADES | ALERTS | GOVERNANCE
│   ├── WebSocket status indicator
│   ├── Tab selection handlers
│   └── Styling: glass-strong, glow-cyan effects
│
├── PodMetrics.tsx                 ← Individual pod summary card
│   ├── Pod ID, status, NAV, daily P&L
│   ├── Risk metrics grid (leverage, vol, VaR, drawdown)
│   ├── Expandable: click to show positions
│   ├── Position breakdown: symbol, qty, price, P&L
│   └── Props: pod (PodSummary), isExpanded (boolean)
│
└── RiskAlert.tsx                  ← Risk violation notification
    ├── Alert severity badge (WARNING/CRITICAL)
    ├── Metric name, current value vs. threshold
    ├── Pod ID and timestamp
    ├── Color-coded by severity
    └── Props: alert (RiskAlert)

Additional components (pre-existing):
├── ExecutionHub.tsx               ← Execution metrics view
├── GovernanceHub.tsx              ← Governance actions view
├── PerformanceHub.tsx             ← Performance analytics view
├── RiskHub.tsx                    ← Risk analysis view
└── DataPanels.tsx                 ← Data panel variant
```

### Contexts
```
web/src/contexts/
└── WebSocketContext.tsx           ← Real-time state management
    ├── Provider component: <WebSocketProvider>
    ├── State: pods, trades, riskAlerts, governanceEvents
    ├── Connection management (auto-reconnect)
    ├── Message handling (4 types + batch)
    ├── Status: connected | connecting | disconnected | error
    ├── Logging: [WebSocket] console messages
    └── Default wsUrl: ws://localhost:8000/ws
```

### Hooks
```
web/src/hooks/
├── useWebSocket.ts                ← Access WebSocket context
│   └── Returns: WebSocketContextType
│       ├── pods, trades, riskAlerts, governanceEvents
│       ├── isConnected, wsStatus, lastUpdate, error
│
├── useThreeScene.ts               ← Three.js scene setup utility
│   ├── Creates scene, camera, renderer
│   ├── Sets up lighting (ambient + directional)
│   ├── Returns: { scene, camera, renderer, containerRef }
│   └── Handles window resize + cleanup
│
└── useScrollTrigger.ts            ← Scroll event handler
    ├── Tracks scrollY position
    ├── Provides isScrolling boolean
    └── Callback: onScroll(scrollY)
```

### Types
```
web/src/types/
└── index.ts                       ← TypeScript interfaces (10 types)
    ├── PodSummary                 ← Pod operational state
    ├── RiskMetrics                ← Risk constraint values
    ├── Position                   ← Individual security holding
    ├── TradeEvent                 ← Executed trade record
    ├── RiskAlert                  ← Constraint violation
    ├── GovernanceEvent            ← Firm-level action
    ├── WebSocketMessage           ← Generic message wrapper
    ├── ThreeSceneConfig           ← 3D setup options
    └── All interfaces strict (no any)
```

### Styles
```
web/src/styles/
└── globals.css                    ← Global styles & animations
    ├── Tailwind imports (@import)
    ├── CSS variables (--bg-primary, --accent-cyan, etc.)
    ├── Utility classes (.glass, .glow-cyan, .animate-fade-in)
    ├── Animations (@keyframes fadeIn, slideIn, pulse-glow)
    ├── Scrollbar styling (::-webkit-scrollbar)
    └── Responsive utilities (@media)

Separate:
└── src/App.css                    ← App-specific styles
    ├── .app layout
    ├── .three-canvas sizing
    ├── .data-panel gradient
    ├── More animations
    └── Glow effects
```

### Animations (Pre-existing)
```
web/src/animations/
├── LightFlows.ts                  ← GSAP light animations
└── ScrollDrive.ts                 ← Lenis scroll integration

web/src/scenes/
└── HQFloors.ts                    ← Floor scene definitions
```

---

## Key File Details

### package.json
- **Main dependencies**: react, react-dom, three, lenis, gsap, recharts
- **Type definitions**: @types/react, @types/three, @types/node
- **Build tools**: vite, typescript, tailwindcss, postcss
- **Scripts**:
  - `npm run dev` → Vite dev server (HMR enabled)
  - `npm run build` → TypeScript + Vite production build
  - `npm run type-check` → TypeScript strict check
  - `npm run preview` → Preview production build

### tsconfig.json
- **Target**: ES2020
- **Module**: ESNext
- **Mode**: Strict (no `any` types)
- **JSX**: react-jsx
- **Path aliases**: @/* → src/*

### vite.config.ts
- **Port**: 3000 (dev server)
- **Proxy**: /api → localhost:8000 (for REST endpoints)
- **Build output**: dist/
- **HMR**: Enabled (hot reload on file change)

### tailwind.config.js
- **Theme colors**:
  - bg-primary: #0b0f14
  - bg-secondary: #1a1f2e
  - text-primary: #ffffff
  - accent-cyan: #00d9ff
  - accent-red: #ff4757
  - accent-green: #2ed573
- **Typography**: JetBrains Mono monospace
- **Plugins**: None (lightweight)

### src/App.tsx
- **Layout**: 3-column grid (col-span-2 + col-span-1)
- **WebSocket URL**: `ws://${window.location.hostname}:8000/ws`
- **Provider**: Wraps children in WebSocketProvider
- **Sections**: ThreeDCanvas (left) + DataPanel (right)

### src/contexts/WebSocketContext.tsx
- **Auto-reconnect**: Yes (3s interval, max 5 attempts)
- **Message types**: pod_summary, trade, risk_alert, governance_event, batch_update
- **State limits**: Last 100 trades, 50 alerts, 50 governance events
- **Console logging**: [WebSocket] prefix for debugging

### src/components/ThreeDCanvas.tsx
- **Floors**: 6 (Risk, Execution, Research, AI, Treasury, Governance)
- **Lighting**: 1 directional + 1 ambient light
- **Shadow maps**: 2048x2048 resolution
- **Camera**: Positioned at (30, 12, 35), looking at (0, 12, 0)
- **Rotation**: Subtle Y-axis rotation (0.0005 rad/frame)
- **Interactivity**: Raycast hover detection on floors

### src/components/DataPanel.tsx
- **Tabs**: 4 views (pods, trades, alerts, governance)
- **Expandable**: Click pod card to show positions
- **Scrollable**: Max height with overflow-auto
- **Data source**: useWebSocket context
- **Updates**: Re-render on pod/trade/alert state changes

### src/types/index.ts
- **Interfaces**: 10 total
- **Pod fields**: pod_id, nav, daily_pnl, status, risk_metrics, positions, timestamp
- **Status enum**: ACTIVE | HALTED | RISK
- **Risk fields**: leverage, vol_ann, var_95, drawdown, max_loss

---

## Quick Reference Commands

```bash
# Navigate to project
cd "/c/Users/PW1868/Agentic HF/web"

# First-time setup
npm install

# Development
npm run dev              # Start dev server (http://localhost:3000)

# Production
npm run build            # Create optimized build (dist/)
npm run preview          # Preview production build locally

# Code quality
npm run type-check       # TypeScript strict type checking
npm run build            # Includes type checking

# Backend (separate terminal)
cd ..
python -m src.mission_control.ws_server:app --reload --port 8000
```

## File Statistics

- **Total files**: 30+
- **Components**: 9 (.tsx files)
- **Configuration files**: 6 (json, js, ts)
- **Documentation**: 4 (.md files)
- **Source lines**: ~2000+ (comments included)

## Integration Points

### FastAPI WebSocket Backend
- **Endpoint**: /ws
- **URL**: ws://localhost:8000/ws (dev)
- **Message format**: JSON with `type` and `data` fields
- **Expected types**: pod_summary, trade, risk_alert, governance_event

### Static File Serving (Production)
```python
from fastapi.staticfiles import StaticFiles
app.mount("/", StaticFiles(directory="web/dist", html=True), name="static")
```

## Next Steps

1. **Setup**: Follow `SETUP.md` (5 minutes)
2. **Learn**: Read `README.md` for technical details
3. **Integrate**: Wire FastAPI /ws endpoint
4. **Deploy**: Run `npm run build` and mount dist/ folder

## Support

All documentation is self-contained in the `web/` directory:
- **README.md** - Technical reference
- **SETUP.md** - Quick start
- **PHASE_2_2_DELIVERY.md** - Feature manifest
- **INDEX.md** - This file

For issues:
1. Check browser console (F12)
2. Check WebSocket messages (Network → WS)
3. Review README.md troubleshooting section
4. Check FastAPI server logs

---

**Status**: ✅ Production-ready
**Last Updated**: 2026-03-07
**Phase**: 2.2 (React SPA with Three.js)
