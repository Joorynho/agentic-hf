import React from 'react'
import type { PodSummary } from '@/types'

interface PodMetricsProps {
  pod: PodSummary
  isExpanded?: boolean
}

export function PodMetrics({ pod, isExpanded = false }: PodMetricsProps) {
  const statusColor =
    pod.status === 'RISK' ? 'text-accent-red' : pod.status === 'HALTED' ? 'text-accent-orange' : 'text-accent-green'

  return (
    <div className="glass-strong p-4 rounded space-y-3 transition-all duration-200">
      {/* Header */}
      <div className="flex justify-between items-start">
        <div>
          <h3 className="text-lg font-bold text-accent-cyan uppercase">{pod.pod_id}</h3>
          <div className={`text-sm font-semibold ${statusColor}`}>{pod.status}</div>
        </div>
        <div className="text-right space-y-1">
          <div className="text-lg font-bold text-text-primary">${pod.nav.toLocaleString('en-US', { maximumFractionDigits: 0 })}</div>
          <div className={`text-sm font-bold ${pod.daily_pnl >= 0 ? 'text-accent-green' : 'text-accent-red'}`}>
            {pod.daily_pnl >= 0 ? '+' : ''}
            {pod.daily_pnl.toFixed(2)}
          </div>
        </div>
      </div>

      {/* Summary metrics */}
      <div className="grid grid-cols-2 gap-2 text-xs">
        <div className="bg-bg-secondary p-2 rounded">
          <div className="text-text-tertiary">LEVERAGE</div>
          <div className="font-bold text-text-primary">{pod.risk_metrics.leverage.toFixed(2)}x</div>
        </div>
        <div className="bg-bg-secondary p-2 rounded">
          <div className="text-text-tertiary">VOL (Ann)</div>
          <div className="font-bold text-text-primary">{(pod.risk_metrics.vol_ann * 100).toFixed(1)}%</div>
        </div>
        <div className="bg-bg-secondary p-2 rounded">
          <div className="text-text-tertiary">VaR@95</div>
          <div className="font-bold text-text-primary">{(pod.risk_metrics.var_95 * 100).toFixed(2)}%</div>
        </div>
        <div className="bg-bg-secondary p-2 rounded">
          <div className="text-text-tertiary">DRAWDOWN</div>
          <div className={`font-bold ${pod.risk_metrics.drawdown < 0 ? 'text-accent-red' : 'text-accent-green'}`}>
            {(pod.risk_metrics.drawdown * 100).toFixed(2)}%
          </div>
        </div>
      </div>

      {/* Expanded view */}
      {isExpanded && (
        <div className="space-y-3 border-t border-border-color pt-3">
          {/* Positions */}
          {pod.positions.length > 0 && (
            <div>
              <h4 className="text-sm font-bold text-text-secondary mb-2">POSITIONS ({pod.positions.length})</h4>
              <div className="space-y-2 max-h-64 overflow-y-auto">
                {pod.positions.map((pos) => (
                  <div key={pos.symbol} className="bg-bg-secondary p-2 rounded text-xs space-y-1">
                    <div className="flex justify-between">
                      <div className="font-bold text-text-primary">{pos.symbol}</div>
                      <div className={pos.unrealized_pnl >= 0 ? 'text-accent-green' : 'text-accent-red'}>
                        {pos.unrealized_pnl >= 0 ? '+' : ''}${pos.unrealized_pnl.toFixed(2)}
                      </div>
                    </div>
                    <div className="flex justify-between text-text-secondary">
                      <div>Qty: {pos.qty}</div>
                      <div>Price: ${pos.current_price.toFixed(2)}</div>
                    </div>
                    <div className="text-text-tertiary">Return: {(pos.pnl_percent * 100).toFixed(2)}%</div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Timestamp */}
          <div className="text-xs text-text-tertiary italic">{new Date(pod.timestamp).toLocaleString()}</div>
        </div>
      )}
    </div>
  )
}
