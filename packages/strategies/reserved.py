from __future__ import annotations

from dataclasses import dataclass

from packages.normalization.models import EventType
from packages.strategies.interface import MarketState, Opportunity


@dataclass
class TriangularSpreadStrategy:
    name: str = "triangular_spread"
    version: str = "0.1.0"

    def required_data(self) -> set[EventType]:
        return {EventType.ORDERBOOK}

    def evaluate(self, market_state: MarketState) -> list[Opportunity]:
        return []

    def explain(self, opportunity: Opportunity) -> str:
        return "三角和多腿换币价差 evaluator 已预留，将在 v1 扩展中实现。"

    def risk_checks(self, opportunity: Opportunity) -> list[str]:
        return ["reserved_strategy_not_implemented"]


@dataclass
class TermStructureAnomalyStrategy:
    name: str = "term_structure_anomaly"
    version: str = "0.1.0"

    def required_data(self) -> set[EventType]:
        return {EventType.MARK, EventType.INSTRUMENT}

    def evaluate(self, market_state: MarketState) -> list[Opportunity]:
        return []

    def explain(self, opportunity: Opportunity) -> str:
        return "期限结构异常 evaluator 已预留，将在 v1 扩展中实现。"

    def risk_checks(self, opportunity: Opportunity) -> list[str]:
        return ["reserved_strategy_not_implemented"]


@dataclass
class OptionsStaticArbitrageStrategy:
    name: str = "options_static_arbitrage"
    version: str = "0.1.0"

    def required_data(self) -> set[EventType]:
        return {EventType.ORDERBOOK, EventType.MARK, EventType.INSTRUMENT}

    def evaluate(self, market_state: MarketState) -> list[Opportunity]:
        return []

    def explain(self, opportunity: Opportunity) -> str:
        return "期权 put-call parity、box、calendar 和 butterfly 接口已预留。"

    def risk_checks(self, opportunity: Opportunity) -> list[str]:
        return ["reserved_strategy_not_implemented"]
