/**
 * ScrollDrive: Scroll-driven camera and animation orchestration
 * Uses GSAP ScrollTrigger to drive Three.js camera through building floors
 */

import * as THREE from 'three'
import gsap from 'gsap'
import { ScrollTrigger } from 'gsap/ScrollTrigger'

gsap.registerPlugin(ScrollTrigger)

export interface FloorScrollConfig {
  floorIndex: number
  yPosition: number
  targetCameraY: number
  targetCameraZ: number
  targetLookAtY: number
  description: string
}

export class ScrollDrive {
  private camera: THREE.PerspectiveCamera
  private floorsConfig: FloorScrollConfig[]
  private triggers: ScrollTrigger[] = []
  private scrollProgress = 0

  constructor(camera: THREE.PerspectiveCamera, floorsConfig: FloorScrollConfig[]) {
    this.camera = camera
    this.floorsConfig = floorsConfig
  }

  /**
   * Setup scroll-driven camera movement
   */
  public setupScrollTriggers(onFloorEnter?: (floorIndex: number) => void) {
    // Kill any existing triggers
    this.triggers.forEach((trigger) => trigger.kill())
    this.triggers = []

    const docHeight = document.documentElement.scrollHeight - window.innerHeight

    this.floorsConfig.forEach((floor, idx) => {
      const trigger = ScrollTrigger.create({
        trigger: `#scroll-section-${floor.floorIndex}`,
        start: 'top center',
        end: 'bottom center',
        markers: false,
        onUpdate: (self) => {
          this.scrollProgress = self.progress
        },
        onEnter: () => {
          this.animateCameraToFloor(floor)
          onFloorEnter?.(floor.floorIndex)
        },
      })

      this.triggers.push(trigger)
    })
  }

  /**
   * Animate camera to a specific floor
   */
  private animateCameraToFloor(floor: FloorScrollConfig) {
    gsap.to(this.camera.position, {
      y: floor.targetCameraY,
      z: floor.targetCameraZ,
      duration: 1.5,
      ease: 'power2.inOut',
    })

    gsap.to(this.camera, {
      onUpdate: () => {
        this.camera.lookAt(0, floor.targetLookAtY, 0)
      },
    })
  }

  /**
   * Get current scroll progress (0-1)
   */
  public getScrollProgress(): number {
    return this.scrollProgress
  }

  /**
   * Cleanup triggers
   */
  public dispose() {
    this.triggers.forEach((trigger) => trigger.kill())
    this.triggers = []
  }
}

/**
 * Create smooth scroll animation with Lenis (optional, for UX)
 * Note: Lenis requires separate import and setup in React component
 */
export function setupLenisScroll(options?: {
  duration?: number
  easing?: (t: number) => number
}) {
  // Dynamic import to avoid SSR issues
  if (typeof window === 'undefined') return null

  try {
    // Lenis import handled separately in component due to bundle considerations
    return null
  } catch {
    console.warn('Lenis not available')
    return null
  }
}
