import React, { useState } from 'react'
import { useWebSocket } from '@/hooks/useWebSocket'
import { PodMetrics } from './PodMetrics'
import { RiskAlert } from './RiskAlert'
import { Toolbar } from './Toolbar'
import { PerformanceHub } from './PerformanceHub'
import { RiskHub } from './RiskHub'
import { ExecutionHub } from './ExecutionHub'
import { GovernanceHub } from './GovernanceHub'

type PanelView = 'pods' | 'trades' | 'alerts' | 'governance' | 'performance' | 'risk' | 'execution' | 'governance-hub'

export function DataPanel() {
  const [activeView, setActiveView] = useState<PanelView>('performance')
  const [expandedPod, setExpandedPod] = useState<string | null>(null)
  const { pods, trades, riskAlerts, isConnected, wsStatus } = useWebSocket()

  return (
    <div className="data-panel flex flex-col h-full bg-bg-primary">
      {/* Toolbar */}
      <Toolbar activeView={activeView} onViewChange={setActiveView} isConnected={isConnected} wsStatus={wsStatus} />

      {/* Main content area */}
      <div className="flex-1 overflow-hidden flex flex-col">
        {activeView === 'performance' && <PerformanceHub />}
        {activeView === 'risk' && <RiskHub />}
        {activeView === 'execution' && <ExecutionHub />}
        {activeView === 'governance-hub' && <GovernanceHub />}

        {activeView === 'pods' && (
          <div className="pods-view space-y-3 p-4 overflow-auto">
            <h2 className="text-lg font-bold text-accent-cyan">STRATEGY PODS</h2>
            {pods.size === 0 ? (
              <div className="text-text-secondary italic">Waiting for pod data...</div>
            ) : (
              Array.from(pods.values()).map((pod) => (
                <div
                  key={pod.pod_id}
                  className="cursor-pointer transition-all hover:scale-105"
                  onClick={() => setExpandedPod(expandedPod === pod.pod_id ? null : pod.pod_id)}
                >
                  <PodMetrics pod={pod} isExpanded={expandedPod === pod.pod_id} />
                </div>
              ))
            )}
          </div>
        )}

        {activeView === 'trades' && (
          <div className="trades-view space-y-3 p-4 overflow-auto">
            <h2 className="text-lg font-bold text-accent-cyan">RECENT TRADES</h2>
            {trades.length === 0 ? (
              <div className="text-text-secondary italic">No trades yet...</div>
            ) : (
              trades.slice(0, 20).map((trade) => (
                <div key={trade.order_id} className="glass p-3 rounded space-y-1 text-sm">
                  <div className="flex justify-between items-center">
                    <div className="font-bold text-text-primary">{trade.symbol}</div>
                    <div className={trade.side === 'BUY' ? 'text-green-400' : 'text-accent-red'}>
                      {trade.side}
                    </div>
                  </div>
                  <div className="flex justify-between text-text-secondary">
                    <div>Qty: {trade.qty}</div>
                    <div>Price: ${trade.fill_price.toFixed(2)}</div>
                  </div>
                  <div className="text-text-tertiary text-xs">{new Date(trade.timestamp).toLocaleString()}</div>
                </div>
              ))
            )}
          </div>
        )}

        {activeView === 'alerts' && (
          <div className="alerts-view space-y-3 p-4 overflow-auto">
            <h2 className="text-lg font-bold text-accent-red">RISK ALERTS</h2>
            {riskAlerts.length === 0 ? (
              <div className="text-text-secondary italic">No active alerts</div>
            ) : (
              riskAlerts.slice(0, 20).map((alert) => <RiskAlert key={alert.alert_id} alert={alert} />)
            )}
          </div>
        )}

        {activeView === 'governance' && (
          <div className="governance-view space-y-3 p-4 overflow-auto">
            <h2 className="text-lg font-bold text-accent-cyan">GOVERNANCE EVENTS</h2>
            <div className="text-text-secondary italic">Governance events coming in MVP2...</div>
          </div>
        )}
      </div>
    </div>
  )
}
