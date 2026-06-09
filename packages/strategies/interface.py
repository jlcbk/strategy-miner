from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Any, Protocol

from packages.normalization.models import EventType, MarketEvent, MarketType, ensure_utc
from packages.scoring.engine import OpportunityGrade


@dataclass(frozen=True)
class OpportunityLeg:
    exchange: str
    market_type: str
    symbol: str
    side: str
    price: Decimal
    qty: Decimal
    role: str = "taker"

    def to_dict(self) -> dict[str, Any]:
        return {
            "exchange": self.exchange,
            "market_type": self.market_type,
            "symbol": self.symbol,
            "side": self.side,
            "price": str(self.price),
            "qty": str(self.qty),
            "role": self.role,
        }


@dataclass
class Opportunity:
    strategy: str
    version: str
    legs: list[OpportunityLeg]
    gross_edge_usd: Decimal
    fees_usd: Decimal
    slippage_est_usd: Decimal
    net_edge_usd: Decimal
    capacity_usd: Decimal
    confidence: Decimal
    risk_score: Decimal
    failure_modes: list[str]
    data_window_start: datetime
    data_window_end: datetime
    grade: OpportunityGrade = OpportunityGrade.C
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.data_window_start = ensure_utc(self.data_window_start)
        self.data_window_end = ensure_utc(self.data_window_end)

    def to_dict(self) -> dict[str, Any]:
        return {
            "strategy": self.strategy,
            "version": self.version,
            "legs": [leg.to_dict() for leg in self.legs],
            "gross_edge_usd": str(self.gross_edge_usd),
            "fees_usd": str(self.fees_usd),
            "slippage_est_usd": str(self.slippage_est_usd),
            "net_edge_usd": str(self.net_edge_usd),
            "capacity_usd": str(self.capacity_usd),
            "confidence": str(self.confidence),
            "risk_score": str(self.risk_score),
            "grade": self.grade.value,
            "failure_modes": list(self.failure_modes),
            "data_window": {
                "start_ts": self.data_window_start.isoformat(),
                "end_ts": self.data_window_end.isoformat(),
            },
            "metadata": self.metadata,
        }


@dataclass
class MarketState:
    events: list[MarketEvent] = field(default_factory=list)

    def add(self, event: MarketEvent) -> None:
        self.events.append(event)

    @property
    def latest_ts(self) -> datetime | None:
        if not self.events:
            return None
        return max(event.exchange_ts for event in self.events)

    @property
    def earliest_ts(self) -> datetime | None:
        if not self.events:
            return None
        return min(event.exchange_ts for event in self.events)

    def orderbooks(self, *, symbol: str | None = None) -> list[MarketEvent]:
        books = [
            event
            for event in self.events
            if event.event_type == EventType.ORDERBOOK
            and (symbol is None or event.symbol == symbol.upper())
        ]
        return _latest_by_key(
            books,
            key=lambda event: (event.exchange.value, event.market_type.value, event.symbol),
        )

    def funding(self, *, symbol: str | None = None) -> list[MarketEvent]:
        rates = [
            event
            for event in self.events
            if event.event_type == EventType.FUNDING
            and event.market_type == MarketType.PERP
            and (symbol is None or event.symbol == symbol.upper())
        ]
        return _latest_by_key(
            rates,
            key=lambda event: (event.exchange.value, event.market_type.value, event.symbol),
        )

    def marks(self, *, symbol: str | None = None) -> list[MarketEvent]:
        marks = [
            event
            for event in self.events
            if event.event_type in {EventType.MARK, EventType.INDEX}
            and (symbol is None or event.symbol == symbol.upper())
        ]
        return _latest_by_key(
            marks,
            key=lambda event: (
                event.exchange.value,
                event.market_type.value,
                event.symbol,
                event.event_type.value,
            ),
        )

    def trades(self, *, symbol: str | None = None) -> list[MarketEvent]:
        return [
            event
            for event in self.events
            if event.event_type == EventType.TRADE
            and (symbol is None or event.symbol == symbol.upper())
        ]

    def open_interest(self, *, symbol: str | None = None) -> list[MarketEvent]:
        open_interest = [
            event
            for event in self.events
            if event.event_type == EventType.OPEN_INTEREST
            and event.market_type == MarketType.PERP
            and (symbol is None or event.symbol == symbol.upper())
        ]
        return _latest_by_key(
            open_interest,
            key=lambda event: (event.exchange.value, event.market_type.value, event.symbol),
        )


class StrategyPlugin(Protocol):
    name: str
    version: str

    def required_data(self) -> set[EventType]:
        ...

    def evaluate(self, market_state: MarketState) -> list[Opportunity]:
        ...

    def explain(self, opportunity: Opportunity) -> str:
        ...

    def risk_checks(self, opportunity: Opportunity) -> list[str]:
        ...


class StrategyRegistry:
    def __init__(self) -> None:
        self._plugins: dict[str, StrategyPlugin] = {}

    def register(self, plugin: StrategyPlugin) -> None:
        key = f"{plugin.name}:{plugin.version}"
        self._plugins[key] = plugin

    def get(self, name: str, version: str | None = None) -> StrategyPlugin:
        if version is not None:
            return self._plugins[f"{name}:{version}"]
        matches = [plugin for plugin in self._plugins.values() if plugin.name == name]
        if not matches:
            raise KeyError(name)
        return sorted(matches, key=lambda plugin: plugin.version)[-1]

    def all(self) -> list[StrategyPlugin]:
        return list(self._plugins.values())


def _latest_by_key(events: list[MarketEvent], key) -> list[MarketEvent]:
    latest: dict[tuple[Any, ...], MarketEvent] = {}
    for event in events:
        event_key = key(event)
        current = latest.get(event_key)
        if current is None or event.exchange_ts >= current.exchange_ts:
            latest[event_key] = event
    return list(latest.values())
