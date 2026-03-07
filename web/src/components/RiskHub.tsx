import React, { useMemo } from 'react'
import { useWebSocket } from '@/hooks/useWebSocket'

export function RiskHub() {
  const { pods, riskAlerts } = useWebSocket()

  const riskMetrics = useMemo(() => {
    return Array.from(pods.values()).map(pod => {
      const isBreach = pod.risk_metrics.drawdown > 0.05 || pod.risk_metrics.leverage > 2
      return {
        pod_id: pod.pod_id,
        vol: (pod.risk_metrics.vol_ann * 100).toFixed(2),
        var: pod.risk_metrics.var_95.toFixed(4),
        leverage: pod.risk_metrics.leverage.toFixed(2),
        drawdown: (pod.risk_metrics.drawdown * 100).toFixed(2),
        max_loss: (pod.risk_metrics.max_loss * 100).toFixed(2),
        status: isBreach ? 'BREACH' : 'OK',
        severity: isBreach ? 'high' : 'low',
      }
    })
  }, [pods])

  const riskHeatmapData = useMemo(() => {
    const sectors = ['TECH', 'FINANCE', 'ENERGY', 'HEALTH', 'CONSUMER']
    return Array.from(pods.values()).map(pod => {
      const exposures: Record<string, number> = {}
      sectors.forEach(sector => {
        exposures[sector] = Math.random()
      })
      return {
        pod_id: pod.pod_id,
        ...exposures,
      }
    })
  }, [pods])

  return (
    <div className="risk-hub h-full flex flex-col">
      <div className="px-4 py-2 border-b border-steel-blue">
        <h2 className="text-accent-cyan font-mono text-xs uppercase tracking-wider">Risk Dashboard</h2>
      </div>

      {/* Risk Metrics Table */}
      <div className="flex-1 overflow-y-auto px-4 py-2">
        <table className="w-full text-xs font-mono mb-4">
          <thead className="sticky top-0 bg-bg-secondary">
            <tr className="border-b border-steel-blue">
              <th className="text-left py-2 px-2 text-text-secondary font-normal">Pod</th>
              <th className="text-right py-2 px-2 text-text-secondary font-normal">Vol %</th>
              <th className="text-right py-2 px-2 text-text-secondary font-normal">VaR 95%</th>
              <th className="text-right py-2 px-2 text-text-secondary font-normal">Leverage</th>
              <th className="text-right py-2 px-2 text-text-secondary font-normal">Drawdown %</th>
              <th className="text-right py-2 px-2 text-text-secondary font-normal">Max Loss %</th>
              <th className="text-center py-2 px-2 text-text-secondary font-normal">Status</th>
            </tr>
          </thead>
          <tbody>
            {riskMetrics.map(row => (
              <tr
                key={row.pod_id}
                className={`border-b border-steel-blue transition-colors ${
                  row.status === 'BREACH'
                    ? 'bg-accent-red/20 hover:bg-accent-red/30'
                    : 'hover:bg-bg-secondary'
                }`}
              >
                <td className="py-1 px-2 text-text-primary">{row.pod_id}</td>
                <td className="text-right py-1 px-2 text-text-primary">{row.vol}%</td>
                <td className="text-right py-1 px-2 text-text-primary">{row.var}</td>
                <td
                  className={`text-right py-1 px-2 ${
                    parseFloat(row.leverage) > 2 ? 'text-accent-red font-bold' : 'text-text-primary'
                  }`}
                >
                  {row.leverage}x
                </td>
                <td
                  className={`text-right py-1 px-2 ${
                    parseFloat(row.drawdown) > 5 ? 'text-accent-red font-bold' : 'text-text-primary'
                  }`}
                >
                  {row.drawdown}%
                </td>
                <td className="text-right py-1 px-2 text-text-primary">{row.max_loss}%</td>
                <td className="text-center py-1 px-2">
                  <span
                    className={`px-2 py-0.5 rounded text-xs inline-block ${
                      row.status === 'BREACH'
                        ? 'bg-accent-red/40 text-accent-red border border-accent-red'
                        : 'bg-green-900/40 text-green-400 border border-green-700'
                    }`}
                  >
                    {row.status}
                  </span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>

        {/* Sector Exposure Heatmap */}
        <div className="mb-4">
          <div className="text-xs text-text-secondary mb-2 font-mono uppercase">Sector Exposure</div>
          <div className="bg-bg-secondary rounded border border-steel-blue p-3 space-y-2">
            {riskHeatmapData.map(row => (
              <div key={row.pod_id} className="flex items-center gap-3">
                <div className="w-12 text-xs font-mono text-text-secondary">{row.pod_id}</div>
                <div className="flex gap-1 flex-1">
                  {(['TECH', 'FINANCE', 'ENERGY', 'HEALTH', 'CONSUMER'] as const).map(sector => {
                    const value = (row as any)[sector] || 0
                    const intensity = Math.min(value * 255, 255)
                    return (
                      <div
                        key={sector}
                        title={`${sector}: ${(value * 100).toFixed(0)}%`}
                        className="flex-1 h-6 rounded border border-steel-blue transition-all"
                        style={{
                          backgroundColor: `rgba(0, 217, 255, ${value})`,
                          minHeight: '20px',
                        }}
                      />
                    )
                  })}
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* Risk Alerts */}
        <div className="mt-4">
          <div className="text-xs text-text-secondary mb-2 font-mono uppercase">Recent Alerts</div>
          <div className="bg-bg-secondary rounded border border-steel-blue p-3 space-y-1 max-h-48 overflow-y-auto">
            {riskAlerts.length === 0 ? (
              <div className="text-xs text-text-tertiary py-2">No active alerts</div>
            ) : (
              riskAlerts.map((alert, i) => (
                <div
                  key={i}
                  className={`text-xs font-mono py-1 px-2 rounded border ${
                    alert.severity === 'CRITICAL'
                      ? 'bg-accent-red/20 border-accent-red text-accent-red'
                      : 'bg-yellow-900/20 border-yellow-700 text-yellow-300'
                  }`}
                >
                  <div className="flex justify-between items-start gap-2">
                    <span className="flex-shrink-0">{alert.pod_id}</span>
                    <span className="flex-1 text-left text-xs">{alert.message}</span>
                    <span className="text-text-tertiary text-xs flex-shrink-0">
                      {new Date(alert.timestamp).toLocaleTimeString([], {
                        hour: '2-digit',
                        minute: '2-digit',
                        second: '2-digit',
                      })}
                    </span>
                  </div>
                  <div className="text-text-tertiary mt-0.5">
                    {alert.metric}: {alert.current_value.toFixed(4)} (limit: {alert.threshold})
                  </div>
                </div>
              ))
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
