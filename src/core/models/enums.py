from enum import Enum


class EventType(str, Enum):
    MARKET_DATA = "market_data"
    NEWS = "news"
    RISK_BREACH = "risk_breach"
    KILL_SWITCH = "kill_switch"
    ALLOCATION_CHANGE = "allocation_change"
    POD_STARTED = "pod_started"
    POD_HALTED = "pod_halted"
    DATA_QUALITY_ALERT = "data_quality_alert"
    HEARTBEAT = "heartbeat"
    ORDER_SUBMITTED = "order_submitted"
    ORDER_FILLED = "order_filled"
    ORDER_REJECTED = "order_rejected"
    MANDATE_UPDATE = "mandate_update"
    REBALANCE = "rebalance"
    POLYMARKET_SIGNAL = "polymarket_signal"
    COLLABORATION_START = "collaboration_start"
    COLLABORATION_END = "collaboration_end"
    GOVERNANCE_QUERY = "governance_query"
    GOVERNANCE_RESPONSE = "governance_response"
    RISK_ALERT = "risk_alert"


class PodStatus(str, Enum):
    ACTIVE = "active"
    PAUSED = "paused"
    HALTED = "halted"
    ERROR = "error"
    INITIALIZING = "initializing"


class Side(str, Enum):
    BUY = "buy"
    SELL = "sell"


class OrderType(str, Enum):
    MARKET = "market"
    LIMIT = "limit"
    VWAP = "vwap"


class TimeHorizon(str, Enum):
    INTRADAY = "intraday"
    SWING = "swing"
    WEEKLY = "weekly"
    MONTHLY = "monthly"


class AgentType(str, Enum):
    RULE_BASED = "rule_based"
    LLM_ASSISTED = "llm_assisted"


class AlertSeverity(str, Enum):
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"
