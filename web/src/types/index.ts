export interface RiskMetrics {
  leverage: number
  vol_ann: number
  var_95: number
  drawdown: number
  max_loss: number
}

export interface Position {
  symbol: string
  qty: number
  current_price: number
  unrealized_pnl: number
  pnl_percent: number
}

export interface PodSummary {
  pod_id: string
  nav: number
  daily_pnl: number
  status: 'ACTIVE' | 'HALTED' | 'RISK'
  risk_metrics: RiskMetrics
  positions: Position[]
  timestamp: string
}

export interface TradeEvent {
  order_id: string
  pod_id: string
  symbol: string
  side: 'BUY' | 'SELL'
  qty: number
  fill_price: number
  timestamp: string
  pnl?: number
}

export interface RiskAlert {
  alert_id: string
  pod_id: string
  severity: 'WARNING' | 'CRITICAL'
  message: string
  metric: string
  threshold: number
  current_value: number
  timestamp: string
}

export interface GovernanceEvent {
  event_id: string
  event_type: 'CIO_MANDATE' | 'CRO_CONSTRAINT' | 'CEO_OVERRIDE' | 'AUDIT'
  description: string
  affected_pods: string[]
  timestamp: string
}

export interface WebSocketMessage {
  type: string
  data: any
  timestamp?: string
}

export interface ThreeSceneConfig {
  width: number
  height: number
  backgroundColor: number
  cameraPosition: [number, number, number]
}
