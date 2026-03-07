import React, { useMemo } from 'react'
import { PieChart, Pie, Cell, ResponsiveContainer, BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip } from 'recharts'
import { useWebSocket } from '@/hooks/useWebSocket'

export function GovernanceHub() {
  const { governanceEvents, pods } = useWebSocket()

  const allocationData = useMemo(() => {
    const podArray = Array.from(pods.values())
    if (podArray.length === 0) {
      return []
    }
    return podArray.map(pod => ({
      name: pod.pod_id,
      value: pod.nav,
    }))
  }, [pods])

  const mandateTimeline = useMemo(() => {
    return governanceEvents
      .sort((a, b) => new Date(b.timestamp).getTime() - new Date(a.timestamp).getTime())
      .slice(0, 10)
  }, [governanceEvents])

  const constraintStats = useMemo(() => {
    const eventTypes = {
      CIO_MANDATE: 0,
      CRO_CONSTRAINT: 0,
      CEO_OVERRIDE: 0,
      AUDIT: 0,
    }

    governanceEvents.forEach(event => {
      eventTypes[event.event_type]++
    })

    return Object.entries(eventTypes).map(([type, count]) => ({
      type: type.replace(/_/g, ' '),
      count,
    }))
  }, [governanceEvents])

  const COLORS = [
    '#00d9ff',
    '#2ed573',
    '#ff4757',
    '#ffa502',
    '#a4de6c',
    '#fd79a8',
  ]

  return (
    <div className="governance-hub h-full flex flex-col">
      <div className="px-4 py-2 border-b border-steel-blue">
        <h2 className="text-accent-cyan font-mono text-xs uppercase tracking-wider">Governance Control</h2>
      </div>

      {/* Constraint Stats */}
      <div className="px-4 py-2 border-b border-steel-blue">
        <div className="grid grid-cols-4 gap-2">
          {constraintStats.map(stat => (
            <div key={stat.type} className="bg-bg-secondary rounded border border-steel-blue p-2">
              <div className="text-xs text-text-tertiary uppercase font-mono">{stat.type}</div>
              <div className="text-accent-cyan font-mono text-sm mt-1">{stat.count}</div>
            </div>
          ))}
        </div>
      </div>

      {/* Content Area: Allocations and Events */}
      <div className="flex-1 overflow-hidden flex flex-col px-4 py-2">
        <div className="grid grid-cols-2 gap-2 flex-1 min-h-0">
          {/* Current Allocations Chart */}
          <div className="bg-bg-secondary rounded border border-steel-blue p-2 flex flex-col">
            <div className="text-xs text-text-secondary mb-2 font-mono uppercase">Pod Allocations</div>
            <div className="flex-1 min-h-0">
              {allocationData.length === 0 ? (
                <div className="text-text-tertiary text-xs py-4">Waiting for pod data...</div>
              ) : (
                <ResponsiveContainer width="100%" height="100%">
                  <PieChart>
                    <Pie
                      data={allocationData}
                      cx="50%"
                      cy="50%"
                      labelLine={false}
                      label={({ name }) => `${name}`}
                      outerRadius={40}
                      fill="#8884d8"
                      dataKey="value"
                    >
                      {allocationData.map((entry, index) => (
                        <Cell key={`cell-${index}`} fill={COLORS[index % COLORS.length]} />
                      ))}
                    </Pie>
                    <Tooltip
                      contentStyle={{
                        backgroundColor: '#1a1f2e',
                        border: '1px solid #4a5568',
                        borderRadius: '4px',
                        fontSize: '12px',
                      }}
                    />
                  </PieChart>
                </ResponsiveContainer>
              )}
            </div>
          </div>

          {/* Event Type Distribution */}
          <div className="bg-bg-secondary rounded border border-steel-blue p-2 flex flex-col">
            <div className="text-xs text-text-secondary mb-2 font-mono uppercase">Event Distribution</div>
            <div className="flex-1 min-h-0">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart
                  data={constraintStats}
                  margin={{ top: 5, right: 5, left: -20, bottom: 5 }}
                >
                  <CartesianGrid strokeDasharray="3 3" stroke="#4a5568" vertical={false} />
                  <XAxis dataKey="type" stroke="#718096" tick={{ fontSize: 10 }} />
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
      </div>

      {/* Governance Events Timeline */}
      <div className="px-4 py-2 border-t border-steel-blue max-h-48 overflow-y-auto">
        <div className="text-xs text-text-secondary mb-2 font-mono uppercase">Governance Events</div>
        <div className="space-y-1.5">
          {mandateTimeline.length === 0 ? (
            <div className="text-xs text-text-tertiary py-2">No governance events</div>
          ) : (
            mandateTimeline.map((event, idx) => {
              const typeColor =
                event.event_type === 'CIO_MANDATE'
                  ? 'text-accent-cyan'
                  : event.event_type === 'CRO_CONSTRAINT'
                    ? 'text-yellow-400'
                    : event.event_type === 'CEO_OVERRIDE'
                      ? 'text-accent-red'
                      : 'text-green-400'

              const bgColor =
                event.event_type === 'CIO_MANDATE'
                  ? 'bg-accent-cyan/20 border-accent-cyan'
                  : event.event_type === 'CRO_CONSTRAINT'
                    ? 'bg-yellow-900/20 border-yellow-700'
                    : event.event_type === 'CEO_OVERRIDE'
                      ? 'bg-accent-red/20 border-accent-red'
                      : 'bg-green-900/20 border-green-700'

              return (
                <div
                  key={event.event_id}
                  className={`bg-bg-secondary rounded border ${bgColor} p-2 text-xs font-mono`}
                >
                  <div className="flex justify-between items-start gap-2">
                    <span className={`flex-shrink-0 font-bold ${typeColor}`}>
                      {event.event_type.replace(/_/g, ' ')}
                    </span>
                    <span className="text-text-tertiary">
                      {new Date(event.timestamp).toLocaleTimeString([], {
                        hour: '2-digit',
                        minute: '2-digit',
                        second: '2-digit',
                      })}
                    </span>
                  </div>
                  <div className="text-text-primary mt-1">{event.description}</div>
                  <div className="text-text-tertiary text-xs mt-1">
                    Pods: {event.affected_pods.join(', ')}
                  </div>
                </div>
              )
            })
          )}
        </div>
      </div>
    </div>
  )
}
