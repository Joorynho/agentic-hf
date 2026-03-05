from abc import ABC, abstractmethod
from datetime import date

from src.core.models.market import Bar


class DataAdapter(ABC):
    @abstractmethod
    async def fetch(self, symbol: str, start: date, end: date) -> list[Bar]:
        ...
