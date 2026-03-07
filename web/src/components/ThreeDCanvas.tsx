import React, { useEffect, useRef, useState } from 'react'
import * as THREE from 'three'
import { useWebSocket } from '@/hooks/useWebSocket'
import gsap from 'gsap'
import { ScrollTrigger } from 'gsap/ScrollTrigger'
import { HQ_FLOORS, getMockFloorData } from '@/scenes/HQFloors'
import { createLightBeamFlow, createAlertFlash } from '@/animations/LightFlows'

gsap.registerPlugin(ScrollTrigger)

// Re-export floor definitions from scenes module for clarity
const FLOOR_DEFINITIONS = HQ_FLOORS

interface FloorData {
  index: number
  yPosition: number
  height: number
  podId?: string
}

// Legacy floor definition type (kept for compatibility)
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

// FLOOR_DEFINITIONS now imported from HQ_FLOORS in @/scenes/HQFloors

export function ThreeDCanvas() {
  const containerRef = useRef<HTMLDivElement>(null)
  const sceneRef = useRef<THREE.Scene | null>(null)
  const cameraRef = useRef<THREE.Camera | null>(null)
  const rendererRef = useRef<THREE.WebGLRenderer | null>(null)
  const buildingRef = useRef<THREE.Group | null>(null)
  const floorsRef = useRef<THREE.Mesh[]>([])
  const pointLightsRef = useRef<THREE.PointLight[]>([])
  const [selectedFloor, setSelectedFloor] = useState<number | null>(null)
  const [hoveredFloor, setHoveredFloor] = useState<number | null>(null)
  const raycasterRef = useRef(new THREE.Raycaster())
  const mouseRef = useRef(new THREE.Vector2())
  const scrollProgressRef = useRef(0)

  const { pods, trades, isConnected } = useWebSocket()

  // Initialize Three.js scene with enhanced building
  useEffect(() => {
    if (!containerRef.current) return

    // Scene setup
    const scene = new THREE.Scene()
    scene.background = new THREE.Color(0x0b0f14)
    scene.fog = new THREE.Fog(0x0b0f14, 200, 1000)
    sceneRef.current = scene

    // Camera setup - positioned to look at building from side
    const width = containerRef.current.clientWidth
    const height = containerRef.current.clientHeight
    const camera = new THREE.PerspectiveCamera(75, width / height, 0.1, 1000)
    camera.position.set(30, 12, 35)
    camera.lookAt(0, 12, 0)
    cameraRef.current = camera

    // Renderer setup with better quality
    const renderer = new THREE.WebGLRenderer({
      antialias: true,
      alpha: true,
      powerPreference: 'high-performance',
    })
    renderer.setSize(width, height)
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2))
    renderer.shadowMap.enabled = true
    renderer.shadowMap.type = THREE.PCFShadowShadowMap
    rendererRef.current = renderer
    containerRef.current.appendChild(renderer.domElement)

    // Enhanced lighting with atmosphere
    const ambientLight = new THREE.AmbientLight(0xffffff, 0.6)
    scene.add(ambientLight)

    const directionalLight = new THREE.DirectionalLight(0xffffff, 0.9)
    directionalLight.position.set(20, 40, 30)
    directionalLight.castShadow = true
    directionalLight.shadow.mapSize.width = 2048
    directionalLight.shadow.mapSize.height = 2048
    directionalLight.shadow.camera.far = 100
    directionalLight.shadow.camera.left = -50
    directionalLight.shadow.camera.right = 50
    directionalLight.shadow.camera.top = 50
    directionalLight.shadow.camera.bottom = -50
    scene.add(directionalLight)

    // Create glass building structure
    const building = new THREE.Group()
    buildingRef.current = building
    scene.add(building)

    // Create 6 semantic floors
    FLOOR_DEFINITIONS.forEach((floorDef) => {
      // Floor plane (main visible surface)
      const floorGeometry = new THREE.PlaneGeometry(14, 4)
      const floorMaterial = new THREE.MeshStandardMaterial({
        color: floorDef.color,
        emissive: floorDef.emissiveColor,
        emissiveIntensity: 0.2,
        metalness: 0.5,
        roughness: 0.4,
        side: THREE.DoubleSide,
      })
      const floorMesh = new THREE.Mesh(floorGeometry, floorMaterial)
      floorMesh.position.set(0, floorDef.yPosition, 5)
      floorMesh.rotation.x = -Math.PI / 2.5
      floorMesh.castShadow = true
      floorMesh.receiveShadow = true
      floorMesh.userData = {
        floorIndex: floorDef.index,
        floorName: floorDef.name,
        systemType: floorDef.systemType,
        description: floorDef.description,
      }

      building.add(floorMesh)
      floorsRef.current.push(floorMesh)

      // Add edge highlights (glow effect)
      const edges = new THREE.EdgesGeometry(floorGeometry)
      const wireframe = new THREE.LineSegments(
        edges,
        new THREE.LineBasicMaterial({
          color: floorDef.emissiveColor,
          linewidth: 2,
          transparent: true,
          opacity: 0.5,
        })
      )
      floorMesh.add(wireframe)
    })

    // Add point lights for each floor (pulsing activity indicators)
    FLOOR_DEFINITIONS.forEach((floorDef) => {
      const light = new THREE.PointLight(floorDef.emissiveColor, 0.6)
      light.position.set(0, floorDef.yPosition, 10)
      light.distance = 25
      light.decay = 1.5
      scene.add(light)
      pointLightsRef.current.push(light)
    })

    // Animation loop with light pulsing and scroll-driven camera
    let animationFrameId: number
    const startTime = Date.now()

    const animate = () => {
      animationFrameId = requestAnimationFrame(animate)
      const elapsed = (Date.now() - startTime) * 0.001

      // Subtle ambient rotation of building
      if (buildingRef.current) {
        buildingRef.current.rotation.y = Math.sin(elapsed * 0.3) * 0.1
      }

      // Pulse point lights to indicate activity
      pointLightsRef.current.forEach((light, index) => {
        const basePulse = Math.sin(elapsed * 2 + index * 0.5) * 0.3 + 0.5
        light.intensity = 0.6 * basePulse
      })

      // Animate floor emissive intensity based on hover state
      floorsRef.current.forEach((floor) => {
        const material = floor.material as THREE.MeshStandardMaterial
        const floorDef = FLOOR_DEFINITIONS[floor.userData.floorIndex]

        if (hoveredFloor === floor.userData.floorIndex) {
          // Highlight hovered floor
          material.emissiveIntensity = Math.max(0.4, 0.4 + Math.sin(elapsed * 3) * 0.1)
          material.emissive.setHex(floorDef.emissiveColor)
        } else {
          // Return to normal pulsing
          material.emissiveIntensity = 0.2 + Math.sin(elapsed * 1 + floor.userData.floorIndex * 0.3) * 0.1
          material.emissive.setHex(floorDef.emissiveColor)
        }
      })

      renderer.render(scene, camera)
    }
    animate()

    // Scroll-driven camera descent through building
    // Create scroll sections for each floor
    const setupScrollTriggers = () => {
      const docHeight = document.documentElement.scrollHeight - window.innerHeight

      FLOOR_DEFINITIONS.forEach((floor, idx) => {
        const scrollStart = (idx / FLOOR_DEFINITIONS.length) * docHeight
        const scrollEnd = ((idx + 1) / FLOOR_DEFINITIONS.length) * docHeight

        ScrollTrigger.create({
          trigger: `#scroll-section-${idx}`,
          start: 'top center',
          end: 'bottom center',
          markers: false,
          onEnter: () => {
            // Animate camera to look at this floor
            gsap.to(camera.position, {
              y: floor.yPosition,
              z: 40 - idx * 3,
              duration: 1.5,
              ease: 'power2.inOut',
            })
            gsap.to(camera, {
              onUpdate: () => {
                camera.lookAt(0, floor.yPosition + 2, 0)
              },
            })
          },
        })
      })
    }

    // Handle window resize
    const handleResize = () => {
      const w = containerRef.current?.clientWidth || width
      const h = containerRef.current?.clientHeight || height

      if (camera instanceof THREE.PerspectiveCamera) {
        camera.aspect = w / h
        camera.updateProjectionMatrix()
      }

      renderer.setSize(w, h)
      ScrollTrigger.refresh()
    }

    // Handle mouse hover and click
    const handleMouseMove = (event: MouseEvent) => {
      if (!containerRef.current) return

      const rect = containerRef.current.getBoundingClientRect()
      mouseRef.current.x = ((event.clientX - rect.left) / rect.width) * 2 - 1
      mouseRef.current.y = -((event.clientY - rect.top) / rect.height) * 2 + 1

      raycasterRef.current.setFromCamera(mouseRef.current, camera)
      const intersects = raycasterRef.current.intersectObjects(floorsRef.current)

      if (intersects.length > 0) {
        const floor = intersects[0].object as THREE.Mesh
        const floorIndex = floor.userData.floorIndex
        setHoveredFloor(floorIndex)
      } else {
        setHoveredFloor(null)
      }
    }

    const handleMouseLeave = () => {
      setHoveredFloor(null)
    }

    const handleClick = (event: MouseEvent) => {
      raycasterRef.current.setFromCamera(mouseRef.current, camera)
      const intersects = raycasterRef.current.intersectObjects(floorsRef.current)

      if (intersects.length > 0) {
        const floor = intersects[0].object as THREE.Mesh
        const floorIndex = floor.userData.floorIndex
        setSelectedFloor(floorIndex)
      }
    }

    window.addEventListener('resize', handleResize)
    containerRef.current.addEventListener('mousemove', handleMouseMove)
    containerRef.current.addEventListener('mouseleave', handleMouseLeave)
    containerRef.current.addEventListener('click', handleClick)

    // Setup scroll-driven animations
    setupScrollTriggers()

    // Cleanup
    return () => {
      cancelAnimationFrame(animationFrameId)
      window.removeEventListener('resize', handleResize)
      containerRef.current?.removeEventListener('mousemove', handleMouseMove)
      containerRef.current?.removeEventListener('mouseleave', handleMouseLeave)
      containerRef.current?.removeEventListener('click', handleClick)

      ScrollTrigger.getAll().forEach((trigger) => trigger.kill())
      renderer.dispose()
      if (containerRef.current?.contains(renderer.domElement)) {
        containerRef.current.removeChild(renderer.domElement)
      }
    }
  }, [hoveredFloor, selectedFloor])

  // Animate light flow between floors (for trade execution visualization)
  const animateLightFlow = (fromFloorIdx: number, toFloorIdx: number) => {
    if (!sceneRef.current) return

    const fromFloor = FLOOR_DEFINITIONS[fromFloorIdx]
    const toFloor = FLOOR_DEFINITIONS[toFloorIdx]

    // Use new LightFlows utility for cleaner implementation
    createLightBeamFlow(sceneRef.current, {
      fromFloorY: fromFloor.yPosition,
      toFloorY: toFloor.yPosition,
      color: 0x00d9ff,
      duration: 2,
      intensity: 0.6,
    })
  }

  // Trigger light flow when trades occur
  useEffect(() => {
    if (trades.length === 0) return

    const latestTrade = trades[0]
    if (latestTrade.pod_id === 'execution') {
      // Execution floor receives capital from Treasury
      animateLightFlow(4, 1)
    }
  }, [trades])

  // Floor data panel component
  const FloorDataOverlay = ({ floorIndex }: { floorIndex: number }) => {
    const floor = FLOOR_DEFINITIONS[floorIndex]
    const mockData = getMockFloorData(floor.systemType)
    const colorHex = floor.emissiveColor.toString(16).padStart(6, '0')

    // Calculate real metrics when available
    const totalNav = Array.from(pods.values()).reduce((sum, p) => sum + p.nav, 0)
    const navM = totalNav / 1e6

    return (
      <div
        className="absolute top-0 right-0 m-4 p-4 bg-gray-900 border-l-4 rounded shadow-lg max-w-sm text-sm"
        style={{ borderLeftColor: `#${colorHex}` }}
      >
        <h3 className="text-lg font-bold" style={{ color: `#${colorHex}` }}>
          {floor.name}
        </h3>
        <p className="text-gray-400 text-xs mt-1">{floor.description}</p>

        {/* Primary metrics */}
        <div className="mt-3 space-y-1 text-xs border-t border-gray-700 pt-2">
          {floor.systemType === 'risk' && (
            <>
              <div className="flex justify-between">
                <span>Max Leverage:</span>
                <span className="text-blue-400">{mockData.maxLeverage}x</span>
              </div>
              <div className="flex justify-between">
                <span>Current Leverage:</span>
                <span className="text-green-400">{mockData.currentLeverage}x</span>
              </div>
              <div className="flex justify-between">
                <span>VaR (95%):</span>
                <span className="text-yellow-400">{mockData.varRisk95}%</span>
              </div>
              <div className="flex justify-between">
                <span>Max Drawdown:</span>
                <span className="text-red-400">{mockData.maxDrawdown}%</span>
              </div>
            </>
          )}
          {floor.systemType === 'execution' && (
            <>
              <div className="flex justify-between">
                <span>Active Orders:</span>
                <span className="text-blue-400">{mockData.activeOrders}</span>
              </div>
              <div className="flex justify-between">
                <span>Fill Rate:</span>
                <span className="text-green-400">{mockData.fillRate}%</span>
              </div>
              <div className="flex justify-between">
                <span>Slippage:</span>
                <span className="text-yellow-400">{mockData.slippageBps} bps</span>
              </div>
              <div className="flex justify-between">
                <span>Queue Depth:</span>
                <span className="text-gray-300">{mockData.queueDepth}</span>
              </div>
            </>
          )}
          {floor.systemType === 'research' && (
            <>
              <div className="flex justify-between">
                <span>Active Signals:</span>
                <span className="text-blue-400">{mockData.activeSignals}</span>
              </div>
              <div className="flex justify-between">
                <span>Data Sources:</span>
                <span className="text-green-400">{mockData.dataSources}</span>
              </div>
              <div className="flex justify-between">
                <span>Signal Quality:</span>
                <span className="text-yellow-400">{(mockData.signalQuality * 100).toFixed(0)}%</span>
              </div>
              <div className="flex justify-between">
                <span>Coverage:</span>
                <span className="text-gray-300">{mockData.coverage}</span>
              </div>
            </>
          )}
          {floor.systemType === 'ai' && (
            <>
              <div className="flex justify-between">
                <span>Active Pods:</span>
                <span className="text-blue-400">{pods.size}</span>
              </div>
              <div className="flex justify-between">
                <span>Total NAV:</span>
                <span className="text-green-400">${navM.toFixed(1)}M</span>
              </div>
              <div className="flex justify-between">
                <span>Daily Return:</span>
                <span className="text-yellow-400">{mockData.avgDailyReturn}%</span>
              </div>
              <div className="flex justify-between">
                <span>Sharpe Ratio:</span>
                <span className="text-gray-300">{mockData.sharpeRatio}</span>
              </div>
            </>
          )}
          {floor.systemType === 'treasury' && (
            <>
              <div className="flex justify-between">
                <span>Firm Capital:</span>
                <span className="text-blue-400">${navM.toFixed(1)}M</span>
              </div>
              <div className="flex justify-between">
                <span>Allocated:</span>
                <span className="text-green-400">${mockData.allocatedM.toFixed(1)}M</span>
              </div>
              <div className="flex justify-between">
                <span>Reserve Buffer:</span>
                <span className="text-yellow-400">{(mockData.reserveBuffer * 100).toFixed(0)}%</span>
              </div>
              <div className="flex justify-between">
                <span>Utilization:</span>
                <span className="text-gray-300">{(mockData.utilization * 100).toFixed(0)}%</span>
              </div>
            </>
          )}
          {floor.systemType === 'governance' && (
            <>
              <div className="flex justify-between">
                <span>Active Mandates:</span>
                <span className="text-blue-400">{mockData.activeMandates}</span>
              </div>
              <div className="flex justify-between">
                <span>Risk Constraints:</span>
                <span className="text-green-400">{mockData.riskConstraints}</span>
              </div>
              <div className="flex justify-between">
                <span>CEO Overrides:</span>
                <span className="text-yellow-400">{mockData.ceoOverrides}</span>
              </div>
              <div className="flex justify-between">
                <span>Compliance:</span>
                <span className="text-gray-300">{mockData.complianceStatus}</span>
              </div>
            </>
          )}
        </div>
      </div>
    )
  }

  return (
    <div className="relative w-full h-full">
      {/* Three.js canvas container */}
      <div
        ref={containerRef}
        style={{
          width: '100%',
          height: '100%',
          position: 'absolute',
          top: 0,
          left: 0,
        }}
        className="three-canvas"
      />

      {/* Scroll sections (hidden, used for scroll triggers) */}
      <div className="absolute inset-0 pointer-events-none overflow-hidden">
        {FLOOR_DEFINITIONS.map((floor, idx) => (
          <div
            key={`scroll-section-${idx}`}
            id={`scroll-section-${idx}`}
            style={{
              position: 'absolute',
              height: `${(100 / FLOOR_DEFINITIONS.length) * 1.5}vh`,
              top: `${(idx / FLOOR_DEFINITIONS.length) * 100}vh`,
              width: '100%',
              pointerEvents: 'auto',
            }}
          />
        ))}
      </div>

      {/* Floor data overlay when hovering */}
      {hoveredFloor !== null && <FloorDataOverlay floorIndex={hoveredFloor} />}

      {/* HUD information */}
      <div className="absolute bottom-4 left-4 text-xs text-gray-500 bg-black/50 p-2 rounded font-mono">
        <div>Floors: {FLOOR_DEFINITIONS.length}</div>
        <div>Pods: {pods.size}</div>
        <div>Connection: {isConnected ? 'Connected' : 'Offline'}</div>
      </div>
    </div>
  )
}
