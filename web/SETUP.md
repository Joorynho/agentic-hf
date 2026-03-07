# Phase 2.2 Setup Guide - React SPA with Three.js

## Quick Start (5 minutes)

### 1. Install Node.js
Download and install Node.js 18+ LTS from https://nodejs.org

### 2. Install Dependencies
```bash
cd web
npm install
```

### 3. Start Development Server
```bash
npm run dev
```

The app will be available at **http://localhost:3000**

### 4. Start FastAPI Backend (Python)
In a separate terminal:
```bash
cd "C:\Users\PW1868\Agentic HF"
python -m uvicorn src.mission_control.ws_server:app --reload --port 8000
```

The WebSocket will connect to **ws://localhost:8000/ws**

### 5. Verify Connection
- Open browser DevTools (F12)
- Go to Network → WS filter
- You should see an active WebSocket connection to localhost:8000
- Toolbar should show "CONNECTED" in green

## Project Files Created

### Configuration
- `package.json` - npm dependencies + scripts
- `tsconfig.json` - TypeScript compiler options
- `tsconfig.node.json` - TypeScript for Vite config
- `vite.config.ts` - Vite dev server + build settings
- `tailwind.config.js` - Tailwind CSS customizations
- `postcss.config.js` - CSS processing pipeline

### Source Code
- `src/index.tsx` - React entry point
- `src/App.tsx` - Main app layout (3-column grid)
- `src/App.css` - Global styles + animations
- `public/index.html` - HTML template

### React Components
- `src/components/ThreeDCanvas.tsx` - 3D building viewport (2/3 width)
- `src/components/DataPanel.tsx` - Right sidebar (1/3 width)
- `src/components/Toolbar.tsx` - Top navigation bar
- `src/components/PodMetrics.tsx` - Individual pod summary card
- `src/components/RiskAlert.tsx` - Risk violation notification

### Context & Hooks
- `src/contexts/WebSocketContext.tsx` - Real-time state management
- `src/hooks/useWebSocket.ts` - Hook to access WebSocket state
- `src/hooks/useThreeScene.ts` - Three.js setup utility
- `src/hooks/useScrollTrigger.ts` - Scroll event handler

### Types & Styles
- `src/types/index.ts` - TypeScript interfaces for all data models
- `src/styles/globals.css` - Tailwind + CSS variables

## Architecture Overview

### Layout
```
┌─────────────────────────────────────────────────┐
│                    TOOLBAR                      │
│  PODS | TRADES | ALERTS | GOVERNANCE  [STATUS] │
├─────────────────────────────┬───────────────────┤
│                             │                   │
│  3D BUILDING VIEWPORT       │   DATA PANEL      │
│  (2/3 width)                │   (1/3 width)     │
│                             │                   │
│  - 6 semantic floors        │  - Pod metrics    │
│  - Real-time coloring       │  - Trade history  │
│  - Hover/click interaction  │  - Risk alerts    │
│                             │  - Governance log │
│                             │                   │
└─────────────────────────────┴───────────────────┘
```

### Data Flow
```
FastAPI WebSocket Server (port 8000)
           ↓ (broadcast messages)
    WebSocketContext (React)
           ↓ (state updates)
  ThreeDCanvas + DataPanel Components
           ↓ (user interactions)
       Re-render
```

### 3D Building Floors
```
Floor 5: Governance (Blue)       [CIO mandates, CEO overrides]
Floor 4: Treasury (Orange)       [Capital allocation, accounting]
Floor 3: AI Systems (Purple)     [Pod strategy agents]
Floor 2: Research Lab (Green)    [Market signals, researchers]
Floor 1: Execution (Cyan)        [Order routing, fill tracking]
Floor 0: Risk (Red)              [CRO constraints, VaR limits]
```

Each floor glows with its assigned color when active. Hover or click to view details.

## Key Features Implemented

### Real-Time Data Synchronization
✅ WebSocket auto-reconnect with exponential backoff
✅ Batch message support for efficiency
✅ 4 message types: pod_summary, trade, risk_alert, governance_event
✅ Connection status indicator in toolbar

### 3D Visualization
✅ Three.js scene with 6 semantic floors
✅ Dynamic coloring: Green (ACTIVE), Red (RISK), Orange (HALTED)
✅ Interactive hover highlights
✅ Shadow maps for depth perception
✅ Directional + ambient lighting

### Data Dashboard
✅ 4 view tabs: PODS | TRADES | ALERTS | GOVERNANCE
✅ Expandable pod cards with live positions
✅ Trade history (last 100)
✅ Risk alerts with severity badges
✅ Responsive scrolling

### Dark Theme
✅ #0B0F14 background (institutional black)
✅ Steel blue accents (#4A5568)
✅ Cyan primary (#00D9FF)
✅ Red warnings/errors (#FF4757)
✅ Green success/active (#2ED573)

## Common Commands

### Development
```bash
npm run dev              # Start Vite dev server (http://localhost:3000)
npm run type-check      # Run TypeScript type checking (no build)
npm run build           # Production build (creates dist/)
npm run preview         # Preview production build locally
```

### Debugging
```bash
# View WebSocket messages in browser
# F12 → Network → WS → Click connection → Messages tab

# Check console logs
# F12 → Console → Filter "[WebSocket]"
```

## Verifying Everything Works

### Checklist
- [ ] `npm install` completes without errors
- [ ] `npm run dev` starts Vite server
- [ ] Browser loads http://localhost:3000
- [ ] 3D building viewport renders (black background with colored floors)
- [ ] DataPanel is visible on the right side
- [ ] Toolbar shows "CONNECTING" or "CONNECTED" (not ERROR)
- [ ] F12 → Network → WS shows active WebSocket connection
- [ ] Hover over 3D floors highlights them

### If Something Breaks

**"Module not found" errors**
```bash
# Clear node_modules and reinstall
rm -rf node_modules package-lock.json
npm install
```

**"WebSocket is DISCONNECTED"**
- Verify FastAPI backend is running (`python -m src.mission_control.ws_server`)
- Check that it's running on port 8000
- Look for errors in FastAPI logs

**"3D viewport is black/blank"**
- Open F12 → Console, look for WebGL errors
- Try a different browser (Chrome, Firefox, Edge)
- Verify GPU drivers are updated

**Tailwind styles not applying**
```bash
npm run build   # Forces rebuild of all CSS
# Or reload page with Ctrl+Shift+R (hard refresh)
```

## Next Steps (MVP2)

This Phase 2.2 provides the foundation. Upcoming features:

1. **Enhanced 3D interactions**: Click floor → detailed overlay
2. **GSAP animations**: Smooth transitions, floor reveal animations
3. **Lenis scroll**: Full-page parallax scrolling
4. **Recharts integration**: Embedded charts in pod details
5. **Governance timeline**: Visual audit log of CEO/CIO/CRO actions
6. **Export/reporting**: Download pod summaries, trade logs

## File Sizes & Performance

```
Dependencies:
  react, react-dom        ~45 KB (gzipped)
  three.js                ~170 KB
  tailwindcss             ~0 KB (tree-shaken in build)
  vite                    ~10 MB (dev only)

Production Bundle:
  main.js                 ~250 KB (gzipped)
  css/style.css           ~30 KB (gzipped)
  Total                   ~280 KB (gzipped)

3D Rendering:
  60 FPS target
  ~50-70 WebGL draw calls per frame
  Shadow map resolution: 2048x2048
```

## Support

For issues or questions:
1. Check `web/README.md` for detailed documentation
2. Review browser console for error messages
3. Check FastAPI server logs
4. Inspect WebSocket messages (F12 → Network → WS → Messages)

Good luck! 🚀
