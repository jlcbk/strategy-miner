from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from packages.agent_interface.validation_plan import (
    RequirementStatus,
    plan_strategy_validation,
)


@dataclass(frozen=True)
class CoverageItem:
    normalized_requirement: str
    exchange: str
    market_type: str
    symbol: str
    event_type: str
    date: str
    present: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "normalized_requirement": self.normalized_requirement,
            "exchange": self.exchange,
            "market_type": self.market_type,
            "symbol": self.symbol,
            "event_type": self.event_type,
            "date": self.date,
            "present": self.present,
        }


@dataclass(frozen=True)
class DataCoverageReport:
    root: str
    strategy_name: str
    ready: bool
    covered_count: int
    required_count: int
    coverage_ratio: str
    missing_items: list[CoverageItem]
    unsupported_requirements: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "root": self.root,
            "strategy_name": self.strategy_name,
            "ready": self.ready,
            "covered_count": self.covered_count,
            "required_count": self.required_count,
            "coverage_ratio": self.coverage_ratio,
            "missing_items": [item.to_dict() for item in self.missing_items],
            "unsupported_requirements": self.unsupported_requirements,
        }


def check_data_coverage(
    *,
    root: str | Path,
    proposal: dict[str, Any],
    exchanges: list[str],
    market_types: list[str],
    symbols: list[str],
    start_date: date,
    end_date: date,
) -> DataCoverageReport:
    if start_date > end_date:
        raise ValueError("start_date 不能晚于 end_date")

    lake_root = Path(root)
    validation_plan = plan_strategy_validation(
        proposal,
        symbols=symbols,
        exchanges=exchanges,
    )
    unsupported = [
        plan.normalized_requirement
        for plan in validation_plan.requirement_plans
        if plan.status in {
            RequirementStatus.UNSUPPORTED,
            RequirementStatus.NEEDS_COLLECTION_POLICY,
        }
    ]

    required_items = [
        CoverageItem(
            normalized_requirement=coverage_requirement.normalized_requirement,
            exchange=exchange,
            market_type=market_type,
            symbol=symbol,
            event_type=coverage_requirement.event_type,
            date=day.isoformat(),
            present=_partition_has_data(
                lake_root,
                exchange=exchange,
                market_type=market_type,
                symbol=symbol,
                event_type=coverage_requirement.event_type,
                day=day,
            ),
        )
        for coverage_requirement in _coverage_requirements(
            validation_plan.requirement_plans,
            market_types,
        )
        for exchange in exchanges
        for market_type in coverage_requirement.market_types
        for symbol in symbols
        for day in _date_range(start_date, end_date)
    ]
    covered_count = sum(1 for item in required_items if item.present)
    required_count = len(required_items)
    missing_items = [item for item in required_items if not item.present]
    ready = not unsupported and required_count > 0 and covered_count == required_count
    ratio = "1.00" if required_count == 0 else f"{covered_count / required_count:.2f}"
    return DataCoverageReport(
        root=str(lake_root),
        strategy_name=validation_plan.strategy_name,
        ready=ready,
        covered_count=covered_count,
        required_count=required_count,
        coverage_ratio=ratio,
        missing_items=missing_items,
        unsupported_requirements=unsupported,
    )


@dataclass(frozen=True)
class _CoverageRequirement:
    normalized_requirement: str
    event_type: str
    market_types: list[str]


def _coverage_requirements(
    requirement_plans,
    market_types: list[str],
) -> list[_CoverageRequirement]:
    requirements: list[_CoverageRequirement] = []
    for plan in requirement_plans:
        if plan.status in {
            RequirementStatus.UNSUPPORTED,
            RequirementStatus.NEEDS_COLLECTION_POLICY,
        }:
            continue
        scoped_market_types = _market_types_for_requirement(
            plan.normalized_requirement,
            market_types,
        )
        for event_type in plan.event_types:
            requirements.append(
                _CoverageRequirement(
                    normalized_requirement=plan.normalized_requirement,
                    event_type=event_type,
                    market_types=scoped_market_types,
                )
            )
    unique: dict[tuple[str, str, tuple[str, ...]], _CoverageRequirement] = {}
    for requirement in requirements:
        key = (
            requirement.normalized_requirement,
            requirement.event_type,
            tuple(requirement.market_types),
        )
        unique[key] = requirement
    return list(unique.values())


def _market_types_for_requirement(requirement: str, market_types: list[str]) -> list[str]:
    if requirement == "spot_candles":
        return [market_type for market_type in market_types if market_type == "spot"]
    if requirement in {"perp_candles", "funding", "open_interest", "perp_mark_price"}:
        return [market_type for market_type in market_types if market_type == "perp"]
    if requirement == "future_mark_price":
        return [market_type for market_type in market_types if market_type == "future"]
    return market_types


def _partition_has_data(
    root: Path,
    *,
    exchange: str,
    market_type: str,
    symbol: str,
    event_type: str,
    day: date,
) -> bool:
    for symbol_variant in _symbol_variants(symbol):
        partition = (
            root
            / f"exchange={exchange}"
            / f"date={day.isoformat()}"
            / f"market_type={market_type}"
            / f"symbol={symbol_variant}"
            / f"event_type={event_type}"
        )
        if any(partition.glob("*.jsonl")) or any(partition.glob("*.parquet")):
            return True
    return False


def _date_range(start_date: date, end_date: date):
    current = start_date
    while current <= end_date:
        yield current
        current += timedelta(days=1)


def _symbol_variants(symbol: str) -> set[str]:
    raw = symbol.upper()
    variants = {raw}
    if "-" not in raw:
        for quote in ("USDT", "USD", "BTC", "ETH"):
            if raw.endswith(quote) and raw != quote:
                variants.add(f"{raw[:-len(quote)]}-{quote}")
                break
    return variants
