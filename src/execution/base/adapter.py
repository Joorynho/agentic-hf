from abc import ABC, abstractmethod

from src.core.models.execution import Order, Fill, RejectedOrder, RiskApprovalToken
from src.core.models.market import Bar


class ExecutionAdapter(ABC):
    @abstractmethod
    async def execute(
        self, order: Order, token: RiskApprovalToken, current_bar: Bar
    ) -> Fill | RejectedOrder:
        ...
