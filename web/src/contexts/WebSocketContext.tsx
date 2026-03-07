import React, { createContext, useEffect, useState, useCallback } from 'react'
import type { PodSummary, TradeEvent, RiskAlert, GovernanceEvent, WebSocketMessage } from '@/types'

export interface WebSocketContextType {
  pods: Map<string, PodSummary>
  trades: TradeEvent[]
  riskAlerts: RiskAlert[]
  governanceEvents: GovernanceEvent[]
  isConnected: boolean
  wsStatus: 'connecting' | 'connected' | 'disconnected' | 'error'
  lastUpdate: number
  error: string | null
}

const defaultContext: WebSocketContextType = {
  pods: new Map(),
  trades: [],
  riskAlerts: [],
  governanceEvents: [],
  isConnected: false,
  wsStatus: 'disconnected',
  lastUpdate: 0,
  error: null,
}

export const WebSocketContext = createContext<WebSocketContextType>(defaultContext)

interface WebSocketProviderProps {
  children: React.ReactNode
  wsUrl?: string
  reconnectInterval?: number
  maxReconnectAttempts?: number
}

export function WebSocketProvider({
  children,
  wsUrl = 'ws://localhost:8000/ws',
  reconnectInterval = 3000,
  maxReconnectAttempts = 5,
}: WebSocketProviderProps) {
  const [pods, setPods] = useState<Map<string, PodSummary>>(new Map())
  const [trades, setTrades] = useState<TradeEvent[]>([])
  const [riskAlerts, setRiskAlerts] = useState<RiskAlert[]>([])
  const [governanceEvents, setGovernanceEvents] = useState<GovernanceEvent[]>([])
  const [isConnected, setIsConnected] = useState(false)
  const [wsStatus, setWsStatus] = useState<'connecting' | 'connected' | 'disconnected' | 'error'>('disconnected')
  const [lastUpdate, setLastUpdate] = useState(0)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let ws: WebSocket | null = null
    let reconnectAttempts = 0
    let reconnectTimeout: ReturnType<typeof setTimeout> | null = null

    const connect = () => {
      if (reconnectAttempts >= maxReconnectAttempts) {
        setWsStatus('error')
        setError(`Max reconnect attempts (${maxReconnectAttempts}) reached`)
        return
      }

      setWsStatus('connecting')
      try {
        ws = new WebSocket(wsUrl)

        ws.onopen = () => {
          setIsConnected(true)
          setWsStatus('connected')
          setError(null)
          reconnectAttempts = 0
          console.log('[WebSocket] Connected to', wsUrl)
        }

        ws.onclose = () => {
          setIsConnected(false)
          setWsStatus('disconnected')
          // Attempt reconnect
          reconnectAttempts++
          reconnectTimeout = setTimeout(() => {
            connect()
          }, reconnectInterval)
        }

        ws.onerror = (event) => {
          const errorMsg = `WebSocket error: ${event.type}`
          setError(errorMsg)
          setWsStatus('error')
          console.error('[WebSocket]', errorMsg)
        }

        ws.onmessage = (event) => {
          try {
            const message: WebSocketMessage = JSON.parse(event.data)
            setLastUpdate(Date.now())

            switch (message.type) {
              case 'pod_summary': {
                const podData = message.data as PodSummary
                setPods((prev) => {
                  const updated = new Map(prev)
                  updated.set(podData.pod_id, podData)
                  return updated
                })
                break
              }

              case 'trade': {
                const tradeData = message.data as TradeEvent
                setTrades((prev) => [tradeData, ...prev.slice(0, 99)])
                break
              }

              case 'risk_alert': {
                const alertData = message.data as RiskAlert
                setRiskAlerts((prev) => [alertData, ...prev.slice(0, 49)])
                break
              }

              case 'governance_event': {
                const govData = message.data as GovernanceEvent
                setGovernanceEvents((prev) => [govData, ...prev.slice(0, 49)])
                break
              }

              case 'batch_update': {
                // Handle batch updates with multiple data types
                const batch = message.data as Record<string, any[]>
                if (batch.pods) {
                  setPods((prev) => {
                    const updated = new Map(prev)
                    batch.pods.forEach((pod) => {
                      updated.set(pod.pod_id, pod)
                    })
                    return updated
                  })
                }
                if (batch.trades) {
                  setTrades((prev) => [...batch.trades, ...prev.slice(0, 99 - batch.trades.length)])
                }
                if (batch.risk_alerts) {
                  setRiskAlerts((prev) => [...batch.risk_alerts, ...prev.slice(0, 49 - batch.risk_alerts.length)])
                }
                break
              }

              default:
                console.warn('[WebSocket] Unknown message type:', message.type)
            }
          } catch (err) {
            console.error('[WebSocket] Failed to parse message:', err)
          }
        }
      } catch (err) {
        const errorMsg = err instanceof Error ? err.message : 'Connection failed'
        setError(errorMsg)
        setWsStatus('error')
        console.error('[WebSocket] Connection error:', err)
      }
    }

    // Initial connection
    connect()

    // Cleanup
    return () => {
      if (reconnectTimeout) {
        clearTimeout(reconnectTimeout)
      }
      if (ws) {
        ws.close()
      }
    }
  }, [wsUrl, reconnectInterval, maxReconnectAttempts])

  const value: WebSocketContextType = {
    pods,
    trades,
    riskAlerts,
    governanceEvents,
    isConnected,
    wsStatus,
    lastUpdate,
    error,
  }

  return (
    <WebSocketContext.Provider value={value}>
      {children}
    </WebSocketContext.Provider>
  )
}
