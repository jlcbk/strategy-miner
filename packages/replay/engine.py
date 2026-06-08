from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from packages.data_lake.store import DataLakeReader
from packages.normalization.models import MarketEvent, ensure_utc
from packages.strategies.interface import MarketState, Opportunity, StrategyPlugin


@dataclass(frozen=True)
class ReplayResult:
    strategy: str
    version: str
    event_count: int
    opportunity_count: int
    opportunities: list[Opportunity]

    def to_dict(self) -> dict:
        return {
            "strategy": self.strategy,
            "version": self.version,
            "event_count": self.event_count,
            "opportunity_count": self.opportunity_count,
            "opportunities": [opportunity.to_dict() for opportunity in self.opportunities],
        }


class ReplayEngine:
    def __init__(self, reader: DataLakeReader) -> None:
        self.reader = reader

    def replay(
        self,
        strategy: StrategyPlugin,
        *,
        start_ts: datetime | int | float | str | None = None,
        end_ts: datetime | int | float | str | None = None,
        exchange: str | None = None,
        market_type: str | None = None,
        symbol: str | None = None,
    ) -> ReplayResult:
        start = ensure_utc(start_ts) if start_ts is not None else None
        end = ensure_utc(end_ts) if end_ts is not None else None
        state = MarketState()
        event_count = 0
        for event in self._events_sorted(exchange=exchange, market_type=market_type, symbol=symbol):
            if start is not None and event.exchange_ts < start:
                continue
            if end is not None and event.exchange_ts > end:
                continue
            if event.event_type not in strategy.required_data():
                continue
            state.add(event)
            event_count += 1
        opportunities = strategy.evaluate(state)
        return ReplayResult(
            strategy=strategy.name,
            version=strategy.version,
            event_count=event_count,
            opportunity_count=len(opportunities),
            opportunities=opportunities,
        )

    def _events_sorted(
        self,
        *,
        exchange: str | None,
        market_type: str | None,
        symbol: str | None,
    ) -> list[MarketEvent]:
        return sorted(
            self.reader.iter_events(exchange=exchange, market_type=market_type, symbol=symbol),
            key=lambda event: (event.exchange_ts, event.sequence_id or ""),
        )
