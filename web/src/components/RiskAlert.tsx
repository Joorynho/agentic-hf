import React from 'react'
import type { RiskAlert as RiskAlertType } from '@/types'

interface RiskAlertProps {
  alert: RiskAlertType
}

export function RiskAlert({ alert }: RiskAlertProps) {
  const isWarning = alert.severity === 'WARNING'
  const bgColor = isWarning ? 'bg-bg-secondary border-accent-orange' : 'bg-red-900/20 border-accent-red'
  const iconColor = isWarning ? 'text-accent-orange' : 'text-accent-red'

  return (
    <div className={`glass-strong p-4 rounded border ${bgColor} space-y-2 animate-slide-in`}>
      <div className="flex justify-between items-start">
        <div className="flex items-start space-x-2">
          <div className={`text-xl mt-0.5 ${iconColor}`}>⚠</div>
          <div>
            <h4 className={`font-bold text-sm ${iconColor}`}>{alert.severity}</h4>
            <p className="text-text-primary text-sm font-semibold">{alert.message}</p>
          </div>
        </div>
        <div className="text-right text-xs text-text-tertiary">{new Date(alert.timestamp).toLocaleTimeString()}</div>
      </div>

      <div className="grid grid-cols-3 gap-2 text-xs">
        <div className="bg-bg-primary p-2 rounded">
          <div className="text-text-tertiary">POD</div>
          <div className="font-bold text-text-primary uppercase">{alert.pod_id}</div>
        </div>
        <div className="bg-bg-primary p-2 rounded">
          <div className="text-text-tertiary">METRIC</div>
          <div className="font-bold text-text-primary">{alert.metric}</div>
        </div>
        <div className="bg-bg-primary p-2 rounded">
          <div className="text-text-tertiary">VALUE</div>
          <div className={`font-bold ${alert.current_value > alert.threshold ? 'text-accent-red' : 'text-text-primary'}`}>
            {typeof alert.current_value === 'number' ? alert.current_value.toFixed(3) : alert.current_value}
          </div>
        </div>
      </div>

      <div className="flex justify-between items-center pt-2 border-t border-border-color">
        <div className="text-xs text-text-tertiary">
          Threshold: {alert.threshold.toFixed(3)}
        </div>
        <div className="text-xs font-bold text-accent-red">
          {((((alert.current_value - alert.threshold) / alert.threshold) * 100)).toFixed(1)}% over
        </div>
      </div>
    </div>
  )
}
