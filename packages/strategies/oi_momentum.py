from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from packages.normalization.models import EventType
from packages.scoring.engine import ScoreInput, score_opportunity
from packages.strategies.interface import MarketState, Opportunity, OpportunityLeg


@dataclass
class OpenInterestMomentumStrategy:
    name: str = "oi_confirmed_momentum"
    version: str = "0.1.0"
    notional_usd: Decimal = Decimal("1000")
    min_price_move_bps: Decimal = Decimal("50")
    min_oi_change_pct: Decimal = Decimal("3")
    max_abs_funding_rate: Decimal = Decimal("0.001")
    taker_fee_bps: Decimal = Decimal("12")
    slippage_bps: Decimal = Decimal("5")

    def required_data(self) -> set[EventType]:
        return {EventType.OPEN_INTEREST, EventType.MARK, EventType.FUNDING}

    def evaluate(self, market_state: MarketState) -> list[Opportunity]:
        funding_by_key = {
            (event.exchange.value, event.market_type.value, event.symbol): event
            for event in market_state.funding()
        }
        opportunities: list[Opportunity] = []
        for key, marks in _series_by_key(market_state, EventType.MARK).items():
            oi_series = _series_by_key(market_state, EventType.OPEN_INTEREST).get(key)
            if oi_series is None or len(marks) < 2 or len(oi_series) < 2:
                continue

            previous_mark, latest_mark = marks[-2], marks[-1]
            previous_oi, latest_oi = oi_series[-2], oi_series[-1]
            price_return_bps = _pct_change_bps(
                previous_mark.payload["mark_price"],
                latest_mark.payload["mark_price"],
            )
            oi_change_pct = _pct_change_pct(
                previous_oi.payload["open_interest"],
                latest_oi.payload["open_interest"],
            )
            if abs(price_return_bps) < self.min_price_move_bps:
                continue
            if oi_change_pct < self.min_oi_change_pct:
                continue

            funding = funding_by_key.get(key)
            funding_rate = Decimal("0")
            if funding is not None:
                funding_rate = Decimal(str(funding.payload["rate"]))
            if abs(funding_rate) > self.max_abs_funding_rate:
                continue

            mark_price = Decimal(str(latest_mark.payload["mark_price"]))
            qty = self.notional_usd / mark_price
            gross_edge = abs(price_return_bps) / Decimal("10000") * self.notional_usd
            fees = self.notional_usd * self.taker_fee_bps / Decimal("10000")
            slippage = self.notional_usd * self.slippage_bps / Decimal("10000")
            score = score_opportunity(
                ScoreInput(
                    gross_edge_usd=gross_edge,
                    fees_usd=fees,
                    slippage_est_usd=slippage,
                    capacity_usd=self.notional_usd,
                    latency_sensitivity=Decimal("0.35"),
                    funding_exposure=Decimal("0.45"),
                    execution_complexity=Decimal("0.35"),
                )
            )
            side = "buy" if price_return_bps > 0 else "sell"
            opportunity = Opportunity(
                strategy=self.name,
                version=self.version,
                legs=[
                    OpportunityLeg(
                        exchange=latest_mark.exchange.value,
                        market_type=latest_mark.market_type.value,
                        symbol=latest_mark.symbol,
                        side=side,
                        price=mark_price,
                        qty=qty,
                    )
                ],
                gross_edge_usd=gross_edge,
                fees_usd=fees,
                slippage_est_usd=slippage,
                net_edge_usd=score.net_edge_usd,
                capacity_usd=self.notional_usd,
                confidence=score.confidence,
                risk_score=score.risk_score,
                grade=score.grade,
                failure_modes=[],
                data_window_start=min(previous_mark.exchange_ts, previous_oi.exchange_ts),
                data_window_end=max(latest_mark.exchange_ts, latest_oi.exchange_ts),
                metadata={
                    "price_return_bps": str(price_return_bps),
                    "oi_change_pct": str(oi_change_pct),
                    "funding_rate": str(funding_rate),
                    "direction": side,
                },
            )
            opportunity.failure_modes = self.risk_checks(opportunity)
            opportunities.append(opportunity)
        return opportunities

    def explain(self, opportunity: Opportunity) -> str:
        return (
            f"{opportunity.legs[0].symbol} 价格动量获得 OI 同向确认；"
            f"方向为 {opportunity.metadata['direction']}，净 edge 为 "
            f"{opportunity.net_edge_usd} USD。"
        )

    def risk_checks(self, opportunity: Opportunity) -> list[str]:
        checks: list[str] = []
        if opportunity.net_edge_usd <= 0:
            checks.append("momentum_edge_not_enough_after_costs")
        if abs(Decimal(opportunity.metadata["funding_rate"])) > self.max_abs_funding_rate:
            checks.append("funding_too_crowded")
        checks.append("requires_oi_venue_definition_before_validation")
        return checks


def _series_by_key(
    market_state: MarketState,
    event_type: EventType,
) -> dict[tuple[str, str, str], list]:
    series: dict[tuple[str, str, str], list] = {}
    for event in market_state.events:
        if event.event_type != event_type:
            continue
        key = (event.exchange.value, event.market_type.value, event.symbol)
        series.setdefault(key, []).append(event)
    for events in series.values():
        events.sort(key=lambda event: event.exchange_ts)
    return series


def _pct_change_bps(previous: str, latest: str) -> Decimal:
    previous_value = Decimal(str(previous))
    latest_value = Decimal(str(latest))
    if previous_value == 0:
        return Decimal("0")
    return (latest_value - previous_value) / previous_value * Decimal("10000")


def _pct_change_pct(previous: str, latest: str) -> Decimal:
    previous_value = Decimal(str(previous))
    latest_value = Decimal(str(latest))
    if previous_value == 0:
        return Decimal("0")
    return (latest_value - previous_value) / previous_value * Decimal("100")
