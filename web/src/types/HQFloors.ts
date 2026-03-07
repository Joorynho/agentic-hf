/**
 * Type definitions for HQ Building components
 * Exported from scenes/HQFloors.ts for external consumption
 */

import * as THREE from 'three'

export type SystemType = 'risk' | 'execution' | 'research' | 'ai' | 'treasury' | 'governance'

/**
 * Complete definition of a single floor in the HQ building
 */
export interface FloorDefinition {
  /** Unique index (0-5) */
  index: number

  /** Display name (e.g., "Risk Management") */
  name: string

  /** Short name for UI (e.g., "RISK") */
  shortName: string

  /** Detailed description of floor purpose */
  description: string

  /** System category */
  systemType: SystemType

  /** Main color (hex format) */
  color: THREE.ColorRepresentation

  /** Emissive glow color (hex format) */
  emissiveColor: THREE.ColorRepresentation

  /** Y position in 3D space */
  yPosition: number

  /** Height of floor in world units */
  height: number

  /** Primary metrics displayed in overlay */
  primaryMetrics: string[]

  /** Names of AI agents operating on this floor */
  agentNames: string[]

  /** Parent system this floor belongs to */
  parentSystem: string
}

/**
 * Mock data for a single floor
 * Used when live data is unavailable or during development
 */
export interface FloorMockData {
  [key: string]: any
}

/**
 * Risk floor specific metrics
 */
export interface RiskFloorMetrics {
  maxLeverage: number
  currentLeverage: number
  varRisk95: number
  maxDrawdown: number
  sharpeRatio: number
}

/**
 * Execution floor specific metrics
 */
export interface ExecutionFloorMetrics {
  activeOrders: number
  fillRate: number
  slippageBps: number
  queueDepth: number
  avgLatencyMs: number
}

/**
 * Research floor specific metrics
 */
export interface ResearchFloorMetrics {
  activeSignals: number
  dataSources: number
  signalQuality: number
  coverage: string
  lastUpdate: string
}

/**
 * AI systems floor specific metrics
 */
export interface AISystemsFloorMetrics {
  activePods: number
  totalNavM: number
  avgDailyReturn: number
  sharpeRatio: number
  tradesPerDay: number
}

/**
 * Treasury floor specific metrics
 */
export interface TreasuryFloorMetrics {
  firmCapitalM: number
  allocatedM: number
  reserveBuffer: number
  utilization: number
  rebalanceFreq: string
}

/**
 * Governance floor specific metrics
 */
export interface GovernanceFloorMetrics {
  activeMandates: number
  riskConstraints: number
  ceoOverrides: number
  auditEvents: number
  complianceStatus: string
}

/**
 * Union of all floor-specific metrics
 */
export type FloorMetrics =
  | RiskFloorMetrics
  | ExecutionFloorMetrics
  | ResearchFloorMetrics
  | AISystemsFloorMetrics
  | TreasuryFloorMetrics
  | GovernanceFloorMetrics

/**
 * Configuration for light flow animation
 */
export interface LightFlowConfig {
  fromFloorY: number
  toFloorY: number
  color?: THREE.ColorRepresentation
  duration?: number
  intensity?: number
  type?: 'beam' | 'particle' | 'line'
}

/**
 * Configuration for scroll-driven camera movement
 */
export interface FloorScrollConfig {
  floorIndex: number
  yPosition: number
  targetCameraY: number
  targetCameraZ: number
  targetLookAtY: number
  description: string
}

/**
 * Component props for floor data overlay
 */
export interface FloorDataOverlayProps {
  floorIndex: number
  isVisible?: boolean
  onClose?: () => void
}

/**
 * Component props for building scene
 */
export interface BuildingSceneProps {
  onFloorHover?: (floorIndex: number | null) => void
  onFloorClick?: (floorIndex: number) => void
  enableScrollDrive?: boolean
  enableLightFlows?: boolean
}

/**
 * Return type for floor lookup functions
 */
export type FloorLookupResult = FloorDefinition | undefined

/**
 * Color palette for metric status visualization
 */
export interface MetricColors {
  healthy: number
  warning: number
  critical: number
  neutral: number
}
