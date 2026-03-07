/**
 * HQFloors: Semantic floor definitions for the 3D building
 * Maps operational systems to visual representations and interaction models
 */

import * as THREE from 'three'

export type SystemType = 'risk' | 'execution' | 'research' | 'ai' | 'treasury' | 'governance'

export interface FloorDefinition {
  index: number
  name: string
  shortName: string
  description: string
  systemType: SystemType
  color: THREE.ColorRepresentation
  emissiveColor: THREE.ColorRepresentation
  yPosition: number
  height: number
  primaryMetrics: string[]
  agentNames: string[]
  parentSystem: string
}

/**
 * Complete floor definitions for the 6-level operational hierarchy
 */
export const HQ_FLOORS: FloorDefinition[] = [
  {
    index: 0,
    name: 'Risk Management',
    shortName: 'RISK',
    description: 'CRO risk constraints, VaR limits, drawdown monitoring, stress testing',
    systemType: 'risk',
    color: 0xff4757,
    emissiveColor: 0xff4757,
    yPosition: 0,
    height: 4,
    primaryMetrics: ['VaR (95%)', 'Max Leverage', 'Max Drawdown', 'Sharpe Ratio'],
    agentNames: ['CRO (Chief Risk Officer)', 'Risk Monitor', 'Stress Tester'],
    parentSystem: 'Risk Management System',
  },
  {
    index: 1,
    name: 'Execution Engine',
    shortName: 'EXEC',
    description: 'Order routing, fill tracking, execution quality, latency monitoring',
    systemType: 'execution',
    color: 0x00d9ff,
    emissiveColor: 0x00d9ff,
    yPosition: 5,
    height: 4,
    primaryMetrics: ['Active Orders', 'Fill Rate', 'Slippage (bps)', 'Queue Depth'],
    agentNames: ['Execution Manager', 'Order Router', 'Fill Tracker'],
    parentSystem: 'Trade Execution System',
  },
  {
    index: 2,
    name: 'Research Lab',
    shortName: 'RSCH',
    description: 'Market data aggregation, signal generation, researcher agents, data pipelines',
    systemType: 'research',
    color: 0x2ecc71,
    emissiveColor: 0x2ecc71,
    yPosition: 10,
    height: 4,
    primaryMetrics: ['Active Signals', 'Data Sources', 'Signal Quality', 'Coverage'],
    agentNames: ['Research Lead', 'Data Integrator', 'Signal Generator'],
    parentSystem: 'Research Pipeline',
  },
  {
    index: 3,
    name: 'AI Systems',
    shortName: 'AI',
    description: 'Pod strategy agents, decision making, model inference, learning loops',
    systemType: 'ai',
    color: 0x9b59b6,
    emissiveColor: 0x9b59b6,
    yPosition: 15,
    height: 4,
    primaryMetrics: ['Active Pods', 'Total NAV', 'Avg Daily Return', 'Sharpe Ratio'],
    agentNames: [
      'Alpha Pod Agent',
      'Beta Pod Agent',
      'Gamma Pod Agent',
      'Delta Pod Agent',
      'Epsilon Pod Agent',
    ],
    parentSystem: 'Pod Agent Network',
  },
  {
    index: 4,
    name: 'Treasury',
    shortName: 'TRY',
    description: 'Capital allocation, portfolio accounting, settlement, rebalancing',
    systemType: 'treasury',
    color: 0xf39c12,
    emissiveColor: 0xf39c12,
    yPosition: 20,
    height: 4,
    primaryMetrics: ['Firm Capital', 'Pod Allocations', 'Reserve Buffer', 'Utilization'],
    agentNames: ['Treasury Manager', 'Portfolio Accountant', 'Settlement Agent'],
    parentSystem: 'Capital & Settlement',
  },
  {
    index: 5,
    name: 'Governance',
    shortName: 'GOV',
    description: 'CEO overrides, CIO mandates, firm-level policy, audit trail',
    systemType: 'governance',
    color: 0x3498db,
    emissiveColor: 0x3498db,
    yPosition: 25,
    height: 4,
    primaryMetrics: ['Active Mandates', 'Risk Constraints', 'CEO Overrides', 'Audit Events'],
    agentNames: ['CEO', 'CIO (Chief Investment Officer)', 'Compliance Officer'],
    parentSystem: 'Governance Framework',
  },
]

/**
 * Utility functions for floor-related queries
 */

export function getFloorByIndex(index: number): FloorDefinition | undefined {
  return HQ_FLOORS.find((f) => f.index === index)
}

export function getFloorBySystemType(systemType: SystemType): FloorDefinition | undefined {
  return HQ_FLOORS.find((f) => f.systemType === systemType)
}

export function getFloorColor(floorIndex: number): number {
  const floor = getFloorByIndex(floorIndex)
  return floor ? (floor.color as number) : 0x1a1f2e
}

export function getFloorEmissiveColor(floorIndex: number): number {
  const floor = getFloorByIndex(floorIndex)
  return floor ? (floor.emissiveColor as number) : 0x000000
}

/**
 * Get mock data for a floor based on system type
 * Used for floor data overlays when live data is not yet connected
 */
export function getMockFloorData(systemType: SystemType): Record<string, any> {
  const dataMap = {
    risk: {
      maxLeverage: 3.5,
      currentLeverage: 2.8,
      varRisk95: 2.1,
      maxDrawdown: -12.3,
      sharpeRatio: 1.45,
    },
    execution: {
      activeOrders: Math.floor(Math.random() * 50),
      fillRate: 99.2,
      slippageBps: 1.2,
      queueDepth: Math.floor(Math.random() * 100),
      avgLatencyMs: 15,
    },
    research: {
      activeSignals: Math.floor(Math.random() * 20),
      dataSources: 5,
      signalQuality: 0.78,
      coverage: '95%',
      lastUpdate: '2s ago',
    },
    ai: {
      activePods: 5,
      totalNavM: 42.5,
      avgDailyReturn: 0.23,
      sharpeRatio: 1.32,
      tradesPerDay: Math.floor(Math.random() * 200),
    },
    treasury: {
      firmCapitalM: 42.5,
      allocatedM: 39.2,
      reserveBuffer: 0.15,
      utilization: 0.92,
      rebalanceFreq: 'daily',
    },
    governance: {
      activeMandates: 3,
      riskConstraints: 6,
      ceoOverrides: 0,
      auditEvents: 12,
      complianceStatus: 'PASS',
    },
  }

  return dataMap[systemType] || {}
}

/**
 * Color palette for different metric types
 */
export const METRIC_COLORS = {
  healthy: 0x2ecc71,
  warning: 0xf39c12,
  critical: 0xff4757,
  neutral: 0x3498db,
}
