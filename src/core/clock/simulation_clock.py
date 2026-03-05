from __future__ import annotations
from datetime import datetime, timedelta
from typing import Iterator, Literal

class SimulationClock:
    def __init__(self, start: datetime, end: datetime,
                 mode: Literal["backtest", "live"] = "backtest",
                 step: timedelta = timedelta(days=1)):
        self._start = start
        self._end = end
        self._mode = mode
        self._step = step
        self._current = start

    def now(self) -> datetime:
        return self._current

    def advance(self) -> datetime | None:
        nxt = self._current + self._step
        if nxt > self._end:
            self._current = nxt
            return None
        self._current = nxt
        return self._current

    def peek_future(self, dt: datetime) -> None:
        if dt > self._current:
            raise ValueError(
                f"Look-ahead bias: cannot access {dt} when clock is at {self._current}"
            )

    def is_done(self) -> bool:
        return self._current > self._end

    def __iter__(self) -> Iterator[datetime]:
        current = self._start
        while current <= self._end:
            yield current
            current += self._step
