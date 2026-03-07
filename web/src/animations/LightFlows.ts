/**
 * LightFlows: Animated light flows between floors
 * Visualizes capital movement, data flow, and event propagation through the building
 */

import * as THREE from 'three'
import gsap from 'gsap'

export interface LightFlowConfig {
  fromFloorY: number
  toFloorY: number
  color?: THREE.ColorRepresentation
  duration?: number
  intensity?: number
  type?: 'beam' | 'particle' | 'line'
}

/**
 * Creates and animates a light beam flow between two floors
 */
export function createLightBeamFlow(
  scene: THREE.Scene,
  config: LightFlowConfig & { fromFloorY: number; toFloorY: number }
): THREE.Mesh {
  const { fromFloorY, toFloorY, color = 0x00d9ff, duration = 2, intensity = 0.8 } = config

  const startPos = new THREE.Vector3(0, fromFloorY, 5)
  const endPos = new THREE.Vector3(0, toFloorY, 5)

  // Create beam using TubeGeometry
  const curve = new THREE.LineCurve3(startPos, endPos)
  const tubeGeometry = new THREE.TubeGeometry(curve, 12, 0.3, 8, false)

  const material = new THREE.MeshBasicMaterial({
    color: color,
    transparent: true,
    opacity: intensity,
  })

  const beam = new THREE.Mesh(tubeGeometry, material)
  scene.add(beam)

  // Animate opacity fade-out
  gsap.to(material, {
    opacity: 0,
    duration: duration,
    ease: 'power2.out',
    onComplete: () => {
      scene.remove(beam)
      tubeGeometry.dispose()
      material.dispose()
    },
  })

  return beam
}

/**
 * Creates particle-based flow effect
 */
export function createParticleFlow(
  scene: THREE.Scene,
  config: LightFlowConfig & { fromFloorY: number; toFloorY: number }
): THREE.Points {
  const { fromFloorY, toFloorY, color = 0x00d9ff, duration = 2 } = config

  const particleCount = 50
  const particles = new THREE.BufferGeometry()
  const positions = new Float32Array(particleCount * 3)

  // Initialize particles at start position
  for (let i = 0; i < particleCount; i++) {
    positions[i * 3] = (Math.random() - 0.5) * 2 // x
    positions[i * 3 + 1] = fromFloorY // y
    positions[i * 3 + 2] = 5 + (Math.random() - 0.5) * 2 // z
  }

  particles.setAttribute('position', new THREE.BufferAttribute(positions, 3))

  const material = new THREE.PointsMaterial({
    color: color,
    size: 0.3,
    transparent: true,
    opacity: 0.8,
  })

  const points = new THREE.Points(particles, material)
  scene.add(points)

  // Animate particles moving from start to end
  const particlePositions = particles.attributes.position.array as Float32Array

  gsap.to(particlePositions, {
    duration: duration,
    ease: 'power2.in',
    onUpdate: () => {
      particles.attributes.position.needsUpdate = true
    },
    onComplete: () => {
      scene.remove(points)
      particles.dispose()
      material.dispose()
    },
  })

  // Move particles upward
  gsap.to(
    Array.from({ length: particleCount }, (_, i) => i),
    {
      duration: duration,
      ease: 'power2.in',
      onUpdate: function () {
        for (let i = 0; i < particleCount; i++) {
          const y = fromFloorY + (this.progress() * (toFloorY - fromFloorY))
          particlePositions[i * 3 + 1] = y
        }
        particles.attributes.position.needsUpdate = true
      },
    }
  )

  return points
}

/**
 * Creates a pulsing light indicator (heartbeat) at a floor
 */
export function createPulsingLight(
  scene: THREE.Scene,
  floorY: number,
  color: THREE.ColorRepresentation,
  intensity: number = 1
): THREE.Light {
  const light = new THREE.PointLight(color, intensity)
  light.position.set(0, floorY, 10)
  light.distance = 25
  light.decay = 1.5

  scene.add(light)

  return light
}

/**
 * Animate a light with pulsing effect
 */
export function animateLightPulse(
  light: THREE.Light,
  options?: {
    minIntensity?: number
    maxIntensity?: number
    duration?: number
    count?: number
  }
): gsap.core.Tween {
  const { minIntensity = 0.3, maxIntensity = 1, duration = 0.8, count = -1 } = options || {}

  return gsap.to(light, {
    intensity: minIntensity,
    duration: duration,
    ease: 'sine.inOut',
    repeat: count,
    yoyo: true,
  })
}

/**
 * Create a visual alert pulse (flash effect)
 */
export function createAlertFlash(
  scene: THREE.Scene,
  position: THREE.Vector3,
  color: THREE.ColorRepresentation,
  duration: number = 0.5
): THREE.Mesh {
  const geometry = new THREE.SphereGeometry(2, 16, 16)
  const material = new THREE.MeshBasicMaterial({
    color: color,
    transparent: true,
    opacity: 0.8,
  })

  const sphere = new THREE.Mesh(geometry, material)
  sphere.position.copy(position)
  scene.add(sphere)

  // Expand and fade out
  gsap.to(sphere.scale, {
    x: 3,
    y: 3,
    z: 3,
    duration: duration,
    ease: 'power2.out',
  })

  gsap.to(material, {
    opacity: 0,
    duration: duration,
    ease: 'power2.out',
    onComplete: () => {
      scene.remove(sphere)
      geometry.dispose()
      material.dispose()
    },
  })

  return sphere
}

/**
 * Batch create multiple light flows for complex events
 */
export function createMultiFlowEvent(
  scene: THREE.Scene,
  flows: Array<LightFlowConfig & { fromFloorY: number; toFloorY: number }>,
  staggerDelay: number = 0.1
) {
  flows.forEach((flow, index) => {
    gsap.delayedCall(index * staggerDelay, () => {
      createLightBeamFlow(scene, flow)
    })
  })
}
