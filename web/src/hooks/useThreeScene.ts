import { useRef, useEffect } from 'react'
import * as THREE from 'three'

export interface UseThreeSceneOptions {
  width: number
  height: number
  backgroundColor?: number
  cameraPosition?: [number, number, number]
  cameraLookAt?: [number, number, number]
  antialias?: boolean
  alpha?: boolean
}

export interface UseThreeSceneReturn {
  scene: THREE.Scene
  camera: THREE.Camera
  renderer: THREE.WebGLRenderer
  containerRef: React.RefObject<HTMLDivElement>
}

export function useThreeScene(options: UseThreeSceneOptions): UseThreeSceneReturn {
  const containerRef = useRef<HTMLDivElement>(null)
  const sceneRef = useRef<THREE.Scene>(new THREE.Scene())
  const cameraRef = useRef<THREE.Camera | null>(null)
  const rendererRef = useRef<THREE.WebGLRenderer | null>(null)
  const animationRef = useRef<number | null>(null)

  const {
    width,
    height,
    backgroundColor = 0x0b0f14,
    cameraPosition = [0, 10, 20],
    cameraLookAt = [0, 0, 0],
    antialias = true,
    alpha = true,
  } = options

  useEffect(() => {
    if (!containerRef.current) return

    // Scene setup
    const scene = sceneRef.current
    scene.background = new THREE.Color(backgroundColor)
    scene.fog = new THREE.Fog(backgroundColor, 100, 1000)

    // Camera setup
    const camera = new THREE.PerspectiveCamera(75, width / height, 0.1, 1000)
    camera.position.set(...cameraPosition)
    camera.lookAt(...cameraLookAt)
    cameraRef.current = camera

    // Renderer setup
    const renderer = new THREE.WebGLRenderer({
      antialias,
      alpha,
      powerPreference: 'high-performance',
    })
    renderer.setSize(width, height)
    renderer.setPixelRatio(window.devicePixelRatio)
    renderer.shadowMap.enabled = true
    renderer.shadowMap.type = THREE.PCFShadowShadowMap
    rendererRef.current = renderer

    containerRef.current.appendChild(renderer.domElement)

    // Lighting
    const ambientLight = new THREE.AmbientLight(0xffffff, 0.5)
    scene.add(ambientLight)

    const directionalLight = new THREE.DirectionalLight(0xffffff, 0.8)
    directionalLight.position.set(10, 20, 10)
    directionalLight.castShadow = true
    directionalLight.shadow.mapSize.width = 2048
    directionalLight.shadow.mapSize.height = 2048
    scene.add(directionalLight)

    // Animation loop
    const animate = () => {
      animationRef.current = requestAnimationFrame(animate)
      renderer.render(scene, camera)
    }
    animate()

    // Handle window resize
    const handleResize = () => {
      const newWidth = containerRef.current?.clientWidth || width
      const newHeight = containerRef.current?.clientHeight || height

      if (camera instanceof THREE.PerspectiveCamera) {
        camera.aspect = newWidth / newHeight
        camera.updateProjectionMatrix()
      }

      renderer.setSize(newWidth, newHeight)
    }

    window.addEventListener('resize', handleResize)

    // Cleanup
    return () => {
      window.removeEventListener('resize', handleResize)

      if (animationRef.current) {
        cancelAnimationFrame(animationRef.current)
      }

      if (rendererRef.current && containerRef.current?.contains(renderer.domElement)) {
        containerRef.current.removeChild(renderer.domElement)
      }

      renderer.dispose()
    }
  }, [width, height, backgroundColor, cameraPosition, cameraLookAt])

  return {
    scene: sceneRef.current,
    camera: cameraRef.current!,
    renderer: rendererRef.current!,
    containerRef,
  }
}
