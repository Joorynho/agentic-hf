# ThreeDCanvas Quick Reference

## Component Location
`web/src/components/ThreeDCanvas.tsx` (516 lines)

## What It Does
Renders an interactive 3D building with 6 operational floors, scroll-driven camera, hover interactions, and real-time data displays.

---

## Props & State

### Props
*None* - Component uses WebSocket context directly

### State
```typescript
const [selectedFloor, setSelectedFloor] = useState<number | null>(null)
const [hoveredFloor, setHoveredFloor] = useState<number | null>(null)
```

### Context
```typescript
const { pods, trades, isConnected } = useWebSocket()
```

---

## Key Functions

### `animate()`
Main animation loop (called via requestAnimationFrame)
- Updates light intensities (pulsing)
- Updates floor emissive colors (hover effects)
- Renders scene
- Runs at ~60fps

### `setupScrollTriggers()`
Creates scroll-linked animations
- Creates 6 scroll sections (one per floor)
- Each section triggers camera animation
- Uses GSAP ScrollTrigger plugin

### `animateLightFlow(fromFloorIdx, toFloorIdx)`
Creates animated beam between floors
- Uses `createLightBeamFlow()` from LightFlows utility
- Triggered when trades occur
- Auto-cleans up after 2 seconds

### `FloorDataOverlay(floorIndex)`
Renders hover data panel
- Shows metrics based on floor system type
- Uses `getMockFloorData()` from HQFloors
- Displays real data when available from pods

### Handlers
- `handleResize()` - Updates camera aspect on window resize
- `handleMouseMove()` - Raycasts to detect floor hover
- `handleMouseLeave()` - Clears hover state
- `handleClick()` - Sets selected floor

---

## Key Constants

### `FLOOR_DEFINITIONS` (imported as `HQ_FLOORS`)
Array of 6 floor objects from `scenes/HQFloors.ts`

```typescript
interface FloorDefinition {
  index: number
  name: string
  description: string
  color: number
  emissiveColor: number
  yPosition: number
  height: number
  systemType: 'risk' | 'execution' | 'research' | 'ai' | 'treasury' | 'governance'
}
```

---

## Three.js Objects

### Scene
```typescript
scene.background = new THREE.Color(0x0b0f14)  // Dark blue-black
scene.fog = new THREE.Fog(0x0b0f14, 200, 1000)
```

### Camera
```typescript
camera.position.set(30, 12, 35)  // Angled side view
// Moves during scroll via GSAP
```

### Lights
- 1 Ambient Light (0xffffff, intensity 0.6)
- 1 Directional Light (sun, shadows enabled)
- 6 Point Lights (one per floor, pulsing)

### Meshes
- 6 Floor planes (PlaneGeometry)
- 6 Wireframe edges (for each floor)
- N Light flows (created on demand)

---

## Refs

```typescript
const containerRef          // DOM element for canvas
const sceneRef              // THREE.Scene
const cameraRef             // THREE.Camera
const rendererRef           // THREE.WebGLRenderer
const buildingRef           // THREE.Group (6 floors)
const floorsRef             // THREE.Mesh[] (floor array)
const pointLightsRef        // THREE.PointLight[] (pulse lights)
const raycasterRef          // THREE.Raycaster (hover detection)
const mouseRef              // THREE.Vector2 (mouse position)
const scrollProgressRef     // number (0-1)
```

---

## Styling & CSS Classes

### Tailwind Classes Used
- `relative w-full h-full` - Container sizing
- `absolute inset-0` - Positioning overlays
- `pointer-events-none/auto` - Control interactivity
- `bg-gray-900 border-l-4` - Data panel styling
- `text-blue-400` - Metric color coding
- `flex justify-between` - Data layout
- `text-xs text-gray-500` - HUD styling

### No CSS files (uses Tailwind utility classes)

---

## Event Listeners

```typescript
window.addEventListener('resize', handleResize)
containerRef.addEventListener('mousemove', handleMouseMove)
containerRef.addEventListener('mouseleave', handleMouseLeave)
containerRef.addEventListener('click', handleClick)

// GSAP ScrollTrigger also listens to scroll (global)
```

---

## Performance Considerations

### What's Optimized
- ✅ Pixel ratio capped at 2x
- ✅ Shadow map 2048x2048 (balanced quality)
- ✅ Single raycaster shared across all interactions
- ✅ Geometry/material disposal after animations
- ✅ Refs prevent unnecessary React re-renders
- ✅ Fog reduces draw distance

### What Could Be Optimized Further
- Instance merging for floor meshes
- Frustum culling (currently disabled)
- LOD (level of detail) for lights
- Texture atlasing for better batching

---

## Common Customizations

### Change Floor Color
Edit `HQFloors.ts`:
```typescript
{
  index: 0,
  color: 0xff4757,         // ← Change here
  emissiveColor: 0xff4757, // ← And here
}
```

### Add New Metric to Overlay
Edit `FloorDataOverlay()` in `ThreeDCanvas.tsx`:
```typescript
{floor.systemType === 'risk' && (
  <>
    {/* Existing metrics */}
    <div className="flex justify-between">
      <span>New Field:</span>
      <span className="text-blue-400">{mockData.newField}</span>
    </div>
  </>
)}
```

### Change Light Pulse Speed
Edit animation loop:
```typescript
const basePulse = Math.sin(elapsed * 3 + index * 0.5) * 0.3 + 0.5
//                                    ↑ faster
```

### Change Camera Speed
Edit `setupScrollTriggers()`:
```typescript
gsap.to(camera.position, {
  duration: 1.5,  // ← Adjust (seconds)
  // ...
})
```

### Trigger Light Flow Manually
```typescript
animateLightFlow(0, 5)  // Risk to Governance
```

---

## Dependencies

### Required Packages
- `three` - 3D rendering
- `gsap` - Animations
- `react`, `react-dom` - Component framework

### No External Dependencies for Utilities
- All Three.js/GSAP code is self-contained
- No Three.js libraries (r3f, Babylon, etc.)

---

## Known Issues & Workarounds

### Issue: Lights don't pulse
**Check**: Point lights in scene, elapsed time calculation

### Issue: Hover doesn't work
**Check**: Raycaster near/far planes, mouse event coordinates

### Issue: Scroll camera doesn't move
**Check**: ScrollTrigger initialization, scroll container height

### Issue: Low FPS
**Check**: Shadow map size, point light count, WebGL renderer settings

---

## Testing Checklist

```
[ ] Building renders (no WebGL errors)
[ ] 6 floors visible
[ ] Hover shows overlay
[ ] Lights pulse
[ ] Scroll moves camera
[ ] Resize works
[ ] WebSocket displays data
[ ] 60 FPS maintained
```

---

## Files That Import This Component

- `App.tsx` - Imports and renders `<ThreeDCanvas />`
- `__tests__/ThreeDCanvas.test.tsx` - Test suite

## Files This Component Imports

- `@/hooks/useWebSocket` - Data provider
- `@/scenes/HQFloors` - Floor definitions
- `@/animations/LightFlows` - Animation utilities
- `three` - 3D engine
- `gsap` - Animation library

---

## Debug Tips

### Check Console
```javascript
// In DevTools console:
document.querySelector('.three-canvas')  // Should exist
window.innerWidth / window.innerHeight   // Aspect ratio
navigator.hardwareConcurrency           // CPU cores
```

### Profile Rendering
```javascript
// DevTools > Performance > Record
// Look for:
// - requestAnimationFrame spikes
// - PointLight updates
// - Raycaster calculations
```

### Inspect Three.js Scene
```javascript
// Browser extension: Three.js Inspector
// Or use:
const scene = document.querySelector('.three-canvas').__reactInternalInstance
// (Requires React DevTools)
```

---

## What to Know Before Editing

1. **Three.js Context**: This component uses `requestAnimationFrame` heavily
2. **GSAP Conflicts**: Only one ScrollTrigger instance (shared globally)
3. **WebGL State**: Canvas context is created once and persists
4. **Memory**: Properly dispose geometries/materials or you'll leak memory
5. **Refs**: Don't render Three.js objects (keep them in refs)

---

## Related Files

- `HQFloors.ts` - Floor configuration
- `ScrollDrive.ts` - Scroll animation class
- `LightFlows.ts` - Light effect utilities
- `HQFloors.ts` (types) - Type definitions
- `WebSocketContext.tsx` - Data provider

---

**Last Updated:** March 7, 2026
**Version:** 1.0
