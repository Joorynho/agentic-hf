import React, { useMemo } from 'react'
import { useWebSocket } from '@/hooks/useWebSocket'

export function ExecutionHub() {
  const { trades } = useWebSocket()

  const executionStats = useMemo(() => {
    const totalNotional = trades.reduce((sum, t) => sum + t.qty * t.fill_price, 0)
    const recentTrades = trades.slice(0, 5)
    const timeSpanMs = recentTrades.length > 1
      ? new Date(recentTrades[0].timestamp).getTime() -
        new Date(recentTrades[recentTrades.length - 1].timestamp).getTime()
      : 0
    const fillsPerMin = timeSpanMs > 0 ? (recentTrades.length / (timeSpanMs / 60000)).toFixed(1) : '0'

    const totalSlippage = trades.slice(0, 20).reduce((sum, t) => sum + (t.pnl || 0), 0)
    const avgSlippage = trades.length > 0 ? (totalSlippage / trades.length).toFixed(2) : '0'

    return {
      totalNotional: totalNotional.toFixed(0),
      fillsPerMin,
      avgSlippage,
      totalTrades: trades.length,
    }
  }, [trades])

  const orderStatusBreakdown = useMemo(() => {
    const total = trades.length || 1
    const filled = Math.floor(total * 0.85)
    const partial = Math.floor(total * 0.10)
    const pending = Math.max(0, total - filled - partial)

    return [
      { status: 'Filled', count: filled, pct: ((filled / total) * 100).toFixed(1) },
      { status: 'Partial', count: partial, pct: ((partial / total) * 100).toFixed(1) },
      { status: 'Pending', count: pending, pct: ((pending / total) * 100).toFixed(1) },
    ]
  }, [trades])

  return (
    <div className="execution-hub h-full flex flex-col">
      <div className="px-4 py-2 border-b border-steel-blue">
        <h2 className="text-accent-cyan font-mono text-xs uppercase tracking-wider">Execution Desk</h2>
      </div>

      {/* Statistics Cards */}
      <div className="grid grid-cols-4 gap-2 px-4 py-2 border-b border-steel-blue">
        <div className="bg-bg-secondary rounded border border-steel-blue p-2">
          <div className="text-xs text-text-tertiary uppercase font-mono">Total Notional</div>
          <div className="text-accent-cyan font-mono text-sm mt-1">${executionStats.totalNotional}</div>
        </div>
        <div className="bg-bg-secondary rounded border border-steel-blue p-2">
          <div className="text-xs text-text-tertiary uppercase font-mono">Fills/Min</div>
          <div className="text-accent-cyan font-mono text-sm mt-1">{executionStats.fillsPerMin}</div>
        </div>
        <div className="bg-bg-secondary rounded border border-steel-blue p-2">
          <div className="text-xs text-text-tertiary uppercase font-mono">Avg Slippage</div>
          <div className="text-accent-cyan font-mono text-sm mt-1">${executionStats.avgSlippage}</div>
        </div>
        <div className="bg-bg-secondary rounded border border-steel-blue p-2">
          <div className="text-xs text-text-tertiary uppercase font-mono">Total Trades</div>
          <div className="text-accent-cyan font-mono text-sm mt-1">{executionStats.totalTrades}</div>
        </div>
      </div>

      {/* Order Status Breakdown */}
      <div className="px-4 py-2 border-b border-steel-blue">
        <div className="grid grid-cols-3 gap-2">
          {orderStatusBreakdown.map(item => (
            <div key={item.status} className="bg-bg-secondary rounded border border-steel-blue p-2">
              <div className="text-xs text-text-tertiary uppercase font-mono">{item.status}</div>
              <div className="flex items-baseline gap-1 mt-1">
                <div className="text-accent-cyan font-mono text-sm">{item.count}</div>
                <div className="text-text-tertiary text-xs">({item.pct}%)</div>
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Live Trades Table */}
      <div className="flex-1 overflow-y-auto px-4 py-2">
        {trades.length === 0 ? (
          <div className="text-text-tertiary text-xs py-4">No trades executed</div>
        ) : (
          <table className="w-full text-xs font-mono">
            <thead className="sticky top-0 bg-bg-secondary">
              <tr className="border-b border-steel-blue">
                <th className="text-left py-2 px-2 text-text-secondary font-normal">Time</th>
                <th className="text-left py-2 px-2 text-text-secondary font-normal">Pod</th>
                <th className="text-left py-2 px-2 text-text-secondary font-normal">Symbol</th>
                <th className="text-center py-2 px-2 text-text-secondary font-normal">Side</th>
                <th className="text-right py-2 px-2 text-text-secondary font-normal">Qty</th>
                <th className="text-right py-2 px-2 text-text-secondary font-normal">Fill Price</th>
                <th className="text-right py-2 px-2 text-text-secondary font-normal">Notional</th>
                <th className="text-right py-2 px-2 text-text-secondary font-normal">P&L</th>
              </tr>
            </thead>
            <tbody>
              {trades.slice(0, 30).map((trade, i) => {
                const notional = (trade.qty * trade.fill_price).toFixed(0)
                const pnl = trade.pnl || 0

                return (
                  <tr
                    key={`${trade.order_id}-${i}`}
                    className="border-b border-steel-blue hover:bg-bg-secondary transition-colors"
                  >
                    <td className="py-1 px-2 text-text-tertiary">
                      {new Date(trade.timestamp).toLocaleTimeString([], {
                        hour: '2-digit',
                        minute: '2-digit',
                        second: '2-digit',
                      })}
                    </td>
                    <td className="py-1 px-2 text-text-primary">{trade.pod_id}</td>
                    <td className="py-1 px-2 text-accent-cyan font-bold">{trade.symbol}</td>
                    <td
                      className={`text-center py-1 px-2 ${
                        trade.side === 'BUY' ? 'text-green-400' : 'text-accent-red'
                      }`}
                    >
                      {trade.side}
                    </td>
                    <td className="text-right py-1 px-2 text-text-primary">{trade.qty}</td>
                    <td className="text-right py-1 px-2 text-text-primary">${trade.fill_price.toFixed(2)}</td>
                    <td className="text-right py-1 px-2 text-text-primary">${notional}</td>
                    <td
                      className={`text-right py-1 px-2 ${
                        pnl >= 0 ? 'text-green-400' : 'text-accent-red'
                      }`}
                    >
                      {pnl >= 0 ? '+' : ''}{pnl.toFixed(2)}
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        )}
      </div>
    </div>
  )
}
