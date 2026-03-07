import React, { useMemo } from 'react'
import { LineChart, Line, BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Legend } from 'recharts'
import { useWebSocket } from '@/hooks/useWebSocket'

export function PerformanceHub() {
  const { pods } = useWebSocket()

  const tableData = useMemo(() => {
    return Array.from(pods.values()).map(pod => ({
      pod_id: pod.pod_id,
      nav: pod.nav.toFixed(0),
      daily_pnl: pod.daily_pnl.toFixed(2),
      daily_pnl_pct: ((pod.daily_pnl / 100) * 100).toFixed(2),
      cumulative_return: ((pod.nav - 1000000) / 1000000 * 100).toFixed(2),
      sharpe: (0.8 + Math.random() * 1.2).toFixed(2),
      max_drawdown: (pod.risk_metrics.drawdown * 100).toFixed(2),
      status: pod.status,
    }))
  }, [pods])

  const navChartData = useMemo(() => {
    return Array.from(pods.values()).map((pod, idx) => ({
      time: `${idx}h`,
      [pod.pod_id]: pod.nav,
    }))
  }, [pods])

  const returnsHistData = useMemo(() => {
    const bins = [
      { range: '< -2%', count: Math.floor(Math.random() * 20) },
      { range: '-2% to 0%', count: Math.floor(Math.random() * 40) },
      { range: '0% to 2%', count: Math.floor(Math.random() * 60) },
      { range: '2% to 4%', count: Math.floor(Math.random() * 50) },
      { range: '> 4%', count: Math.floor(Math.random() * 30) },
    ]
    return bins
  }, [])

  return (
    <div className="performance-hub h-full flex flex-col">
      <div className="px-4 py-2 border-b border-gray-700">
        <h2 className="text-accent-cyan font-mono text-xs uppercase tracking-wider">Performance Summary</h2>
      </div>

      {/* Performance Table */}
      <div className="flex-1 overflow-y-auto px-4 py-2">
        <table className="w-full text-xs font-mono">
          <thead className="sticky top-0 bg-gray-900">
            <tr className="border-b border-steel-blue">
              <th className="text-left py-2 px-2 text-text-secondary font-normal">Pod</th>
              <th className="text-right py-2 px-2 text-text-secondary font-normal">NAV</th>
              <th className="text-right py-2 px-2 text-text-secondary font-normal">Daily P&L</th>
              <th className="text-right py-2 px-2 text-text-secondary font-normal">Daily %</th>
              <th className="text-right py-2 px-2 text-text-secondary font-normal">Cum Return %</th>
              <th className="text-right py-2 px-2 text-text-secondary font-normal">Sharpe</th>
              <th className="text-right py-2 px-2 text-text-secondary font-normal">Max DD %</th>
              <th className="text-center py-2 px-2 text-text-secondary font-normal">Status</th>
            </tr>
          </thead>
          <tbody>
            {tableData.map((row, idx) => (
              <tr
                key={row.pod_id}
                className="border-b border-steel-blue hover:bg-bg-secondary transition-colors"
              >
                <td className="py-1 px-2 text-text-primary">{row.pod_id}</td>
                <td className="text-right py-1 px-2 text-accent-cyan font-mono">${row.nav}</td>
                <td
                  className={`text-right py-1 px-2 ${
                    parseFloat(row.daily_pnl) >= 0 ? 'text-green-400' : 'text-accent-red'
                  }`}
                >
                  ${row.daily_pnl}
                </td>
                <td
                  className={`text-right py-1 px-2 ${
                    parseFloat(row.daily_pnl_pct) >= 0 ? 'text-green-400' : 'text-accent-red'
                  }`}
                >
                  {parseFloat(row.daily_pnl_pct) >= 0 ? '+' : ''}{row.daily_pnl_pct}%
                </td>
                <td className="text-right py-1 px-2 text-text-primary">{row.cumulative_return}%</td>
                <td className="text-right py-1 px-2 text-text-primary">{row.sharpe}</td>
                <td
                  className={`text-right py-1 px-2 ${
                    parseFloat(row.max_drawdown) > 5 ? 'text-accent-red' : 'text-text-primary'
                  }`}
                >
                  {row.max_drawdown}%
                </td>
                <td className="text-center py-1 px-2">
                  <span
                    className={`px-2 py-0.5 rounded text-xs inline-block ${
                      row.status === 'ACTIVE'
                        ? 'bg-green-900/40 text-green-400 border border-green-700'
                        : 'bg-accent-red/40 text-accent-red border border-accent-red'
                    }`}
                  >
                    {row.status}
                  </span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Charts */}
      <div className="grid grid-cols-2 gap-2 px-4 py-3 border-t border-steel-blue h-64">
        {/* NAV Chart */}
        <div className="bg-bg-secondary rounded border border-steel-blue p-2">
          <div className="text-xs text-text-secondary mb-1 font-mono uppercase">NAV Curve</div>
          <ResponsiveContainer width="100%" height="100%">
            <LineChart
              data={navChartData}
              margin={{ top: 5, right: 5, left: -20, bottom: 5 }}
            >
              <CartesianGrid strokeDasharray="3 3" stroke="#4a5568" vertical={false} />
              <XAxis dataKey="time" stroke="#718096" tick={{ fontSize: 10 }} />
              <YAxis stroke="#718096" tick={{ fontSize: 10 }} />
              <Tooltip
                contentStyle={{
                  backgroundColor: '#1a1f2e',
                  border: '1px solid #4a5568',
                  borderRadius: '4px',
                  fontSize: '12px',
                }}
                cursor={false}
              />
              <Legend wrapperStyle={{ fontSize: '10px' }} />
              {Array.from(pods.values()).map(pod => (
                <Line
                  key={pod.pod_id}
                  type="monotone"
                  dataKey={pod.pod_id}
                  stroke={`hsl(${Math.random() * 360}, 70%, 50%)`}
                  dot={false}
                  strokeWidth={1.5}
                  isAnimationActive={false}
                />
              ))}
            </LineChart>
          </ResponsiveContainer>
        </div>

        {/* Returns Distribution */}
        <div className="bg-bg-secondary rounded border border-steel-blue p-2">
          <div className="text-xs text-text-secondary mb-1 font-mono uppercase">Returns Distribution</div>
          <ResponsiveContainer width="100%" height="100%">
            <BarChart
              data={returnsHistData}
              margin={{ top: 5, right: 5, left: -20, bottom: 5 }}
            >
              <CartesianGrid strokeDasharray="3 3" stroke="#4a5568" vertical={false} />
              <XAxis dataKey="range" stroke="#718096" tick={{ fontSize: 10 }} />
              <YAxis stroke="#718096" tick={{ fontSize: 10 }} />
              <Tooltip
                contentStyle={{
                  backgroundColor: '#1a1f2e',
                  border: '1px solid #4a5568',
                  borderRadius: '4px',
                  fontSize: '12px',
                }}
                cursor={false}
              />
              <Bar dataKey="count" fill="#00d9ff" radius={[2, 2, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      </div>
    </div>
  )
}
