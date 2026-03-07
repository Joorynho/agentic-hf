# 3D Scrollytelling Building - Developer Guide

## Quick Start

The 3D building is integrated into the main `App.tsx` as the `<ThreeDCanvas />` component. It displays live data from your hedge fund operations as an interactive 3D scene.

### Running the Web App

```bash
cd web
npm install  # First time only
npm run dev  # Start dev server (usually http://localhost:5173)
```

The building should appear in the left 2/3 of the viewport, with data panels on the right 1/3.

---

## Understanding the Building

### The 6 Floors

The building has 6 semantic floors representing operational systems:

```
Level 5: Governance      (Blue)      - CEO, CIO, Policy
Level 4: Treasury        (Orange)    - Capital, Settlement
Level 3: AI Systems      (Purple)    - Pod Agents
Level 2: Research Lab    (Green)     - Signals, Market Data
Level 1: Execution Engine(Cyan)      - Orders, Fills
Level 0: Risk Management (Red)       - VaR, Leverage, Drawdown
```

### Interacting with the Building

1. **Hover over a floor** → See live metrics in overlay panel
2. **Scroll down** → Camera descends through building
3. **Watch the lights** → Colors pulse to show activity
4. **Light flows** → Animated beams show capital movement (on trades)

---

## Customizing the Building

### Changing Floor Colors

Edit `/web/src/scenes/HQFloors.ts`:

```typescript
{
  index: 0,
  name: 'Risk Management',
  color: 0xff4757,         // ← Change this hex color
  emissiveColor: 0xff4757, // ← And this one
  // ...
}
```

### Adding New Floors

1. Add entry to `HQ_FLOORS` array in `HQFloors.ts`
2. Update `getMockFloorData()` for new metrics
3. Add JSX case in `ThreeDCanvas.tsx` FloorDataOverlay

### Customizing Metrics Display

The data overlay is generated in `ThreeDCanvas.tsx`:

```typescript
{floor.systemType === 'risk' && (
  <>
    <div className="flex justify-between">
      <span>Max Leverage:</span>
      <span className="text-blue-400">{mockData.maxLeverage}x</span>
    </div>
    {/* Add more metrics here */}
  </>
)}
```

Add new metric rows and update corresponding mock data in `HQFloors.ts`.

### Changing Light Behavior

Edit animation loop in `ThreeDCanvas.tsx`:

```typescript
// Modify pulse frequency
const basePulse = Math.sin(elapsed * 2 + index * 0.5) * 0.3 + 0.5
//                                  ↑ frequency      ↑ phase

// Modify pulse amplitude
light.intensity = 0.6 * basePulse  // Change 0.6 for brighter/dimmer
```

### Triggering Light Flows

In `ThreeDCanvas.tsx` `useEffect` for trades:

```typescript
useEffect(() => {
  if (trades.length === 0) return

  const latestTrade = trades[0]

  // Add custom logic
  if (latestTrade.symbol === 'SPY') {
    animateLightFlow(2, 1)  // Flow from Research to Execution
  }
}, [trades])
```

---

## Live Data Integration

The component automatically reads from WebSocket context:

```typescript
const { pods, trades, riskAlerts, isConnected } = useWebSocket()
```

### What Data Is Used

- **pods**: Pod count displayed in HUD, NAV calculations
- **trades**: Triggers light flow animations
- **isConnected**: Shows "Connected/Offline" status in HUD
- **riskAlerts**: (Ready for integration) Could trigger floor highlights

### Fallback: Mock Data

If WebSocket is disconnected, the building displays mock data from `getMockFloorData()`. This allows development/testing without a backend.

---

## Performance Tuning

### For Low-End Devices

In `ThreeDCanvas.tsx`:

```typescript
// Reduce shadow map quality
directionalLight.shadow.mapSize.width = 1024   // ← Lower
directionalLight.shadow.mapSize.height = 1024

// Reduce light count
// Comment out some point light creation

// Reduce particle count in light flows
const particleCount = 25  // ← Lower (was 50)
```

### For High-End Devices

```typescript
// Increase shadow resolution
directionalLight.shadow.mapSize.width = 4096

// Add more lights or effects
// Increase bloom effect intensity
```

### Profiling

1. Open Chrome DevTools → Performance tab
2. Record while scrolling/hovering
3. Check for:
   - FPS (target: 60)
   - Main thread blocking
   - Memory leaks (keep watching allocation over time)

---

## Debugging

### Console Errors

Check browser console (F12) for:
- Three.js warnings
- GSAP warnings
- WebSocket connection errors

### Visual Issues

- **Floors not showing**: Check `FLOOR_DEFINITIONS` array
- **Colors wrong**: Verify hex color codes in `HQFloors.ts`
- **Camera stuck**: Check `setupScrollTriggers()` logic
- **Lights not pulsing**: Check animation loop elapsed time

### State Inspection

Add logging to React component:

```typescript
useEffect(() => {
  console.log('Hovered floor:', hoveredFloor)
  console.log('Selected floor:', selectedFloor)
  console.log('Pods connected:', pods.size)
}, [hoveredFloor, selectedFloor, pods])
```

---

## Advanced: Custom Animations

### Add a Floor Glow Effect

Edit `ThreeDCanvas.tsx` after floor creation:

```typescript
FLOOR_DEFINITIONS.forEach((floorDef) => {
  // ... existing floor creation code ...

  // Add bloom effect
  const glowGeometry = new THREE.PlaneGeometry(15, 5)
  const glowMaterial = new THREE.MeshBasicMaterial({
    color: floorDef.emissiveColor,
    transparent: true,
    opacity: 0.1,
  })
  const glow = new THREE.Mesh(glowGeometry, glowMaterial)
  glow.position.copy(floorMesh.position)
  glow.position.z -= 0.1  // Behind the floor
  building.add(glow)
})
```

### Add Sound Effects

When light flows trigger:

```typescript
const animateLightFlow = (fromFloorIdx: number, toFloorIdx: number) => {
  // Play sound
  const audio = new Audio('/sounds/capital-flow.mp3')
  audio.play()

  // Then create light flow
  createLightBeamFlow(...)
}
```

### Connect to External Data API

Replace mock data with real API:

```typescript
useEffect(() => {
  fetch('/api/floor-metrics')
    .then(r => r.json())
    .then(data => {
      // Update display with real metrics
      setRealMetrics(data)
    })
}, [])
```

---

## Architecture Overview

```
App.tsx
  ├─ WebSocketProvider (provides pods, trades, alerts)
  └─ ThreeDCanvas
      ├─ Three.js Scene
      │  ├─ 6 Floor Meshes
      │  ├─ 6 Point Lights
      │  ├─ Directional Light
      │  └─ Ambient Light
      ├─ GSAP ScrollTrigger
      │  └─ Camera animations
      ├─ Raycast Hover Detection
      └─ FloorDataOverlay
          └─ Mock data from HQFloors.ts
```

---

## FAQ

**Q: Can I use this on mobile?**
A: Currently not optimized. Future work planned for touch gestures and responsive layout.

**Q: How do I hide the data overlay?**
A: Remove the conditional render:
```typescript
{/* {hoveredFloor !== null && <FloorDataOverlay ... />} */}
```

**Q: Can I change camera speed?**
A: Edit GSAP `duration` in `animateCameraToFloor()`:
```typescript
gsap.to(this.camera.position, {
  duration: 1.5,  // ← Change this (seconds)
  // ...
})
```

**Q: The building looks flat/2D**
A: Increase camera z position in setup:
```typescript
camera.position.set(50, 12, 50)  // ← More dramatic angle
```

**Q: How do I change which floor highlights on hover?**
A: Edit raycasting logic in `handleMouseMove()`:
```typescript
if (intersects.length > 0) {
  const floor = intersects[0].object as THREE.Mesh
  const floorIndex = floor.userData.floorIndex

  // Custom logic here
  if (floorIndex === 0) {
    // Only allow highlighting Risk floor
    setHoveredFloor(floorIndex)
  }
}
```

---

## Resources

- Three.js Docs: https://threejs.org/docs/
- GSAP Docs: https://gsap.com/docs/
- ScrollTrigger: https://gsap.com/docs/v3/Plugins/ScrollTrigger/
- React + Three.js: Consider react-three-fiber for future versions

---

## Support

For questions or issues:
1. Check console errors (F12)
2. Review this guide for similar problems
3. Check CLAUDE.md for project-level context
4. Review code comments in component files
