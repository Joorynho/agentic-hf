import React from 'react'

type ViewType = 'pods' | 'trades' | 'alerts' | 'governance' | 'performance' | 'risk' | 'execution' | 'governance-hub'

interface ToolbarProps {
  activeView: ViewType
  onViewChange: (view: ViewType) => void
  isConnected: boolean
  wsStatus: 'connecting' | 'connected' | 'disconnected' | 'error'
}

export function Toolbar({ activeView, onViewChange, isConnected, wsStatus }: ToolbarProps) {
  const views = [
    { id: 'performance' as const, label: 'PERFORMANCE', icon: '📈' },
    { id: 'risk' as const, label: 'RISK', icon: '⚠️' },
    { id: 'execution' as const, label: 'EXECUTION', icon: '⚡' },
    { id: 'governance-hub' as const, label: 'GOVERNANCE', icon: '⚙️' },
    { id: 'pods' as const, label: 'PODS', icon: '⬜' },
    { id: 'trades' as const, label: 'TRADES', icon: '📊' },
    { id: 'alerts' as const, label: 'ALERTS', icon: '🔔' },
  ]

  const statusColor =
    wsStatus === 'connected' ? 'text-accent-green' : wsStatus === 'error' ? 'text-accent-red' : 'text-accent-orange'

  const statusDot =
    wsStatus === 'connected' ? '●' : wsStatus === 'error' ? '●' : wsStatus === 'connecting' ? '⟳' : '○'

  return (
    <div className="glass-strong border-b border-border-color p-4 space-y-3">
      {/* Title and status */}
      <div className="flex justify-between items-center">
        <h1 className="text-xl font-bold text-accent-cyan">MISSION CONTROL</h1>
        <div className={`text-sm font-bold ${statusColor} flex items-center space-x-2`}>
          <span className="animate-pulse">{statusDot}</span>
          <span className="uppercase">{wsStatus}</span>
        </div>
      </div>

      {/* View tabs */}
      <div className="flex space-x-2">
        {views.map((view) => (
          <button
            key={view.id}
            onClick={() => onViewChange(view.id)}
            className={`px-3 py-2 rounded text-sm font-bold transition-all duration-200 ${
              activeView === view.id
                ? 'bg-accent-cyan text-bg-primary glow-cyan'
                : 'bg-bg-secondary text-text-secondary hover:text-accent-cyan hover:border-accent-cyan border border-border-color'
            }`}
          >
            <span className="mr-1">{view.icon}</span>
            {view.label}
          </button>
        ))}
      </div>
    </div>
  )
}
