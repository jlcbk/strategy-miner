from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from packages.normalization.models import EventType
from packages.scoring.engine import ScoreInput, score_opportunity
from packages.strategies.interface import MarketState, Opportunity, OpportunityLeg


@dataclass
class FundingCarryStrategy:
    name: str = "funding_carry"
    version: str = "0.1.0"
    notional_usd: Decimal = Decimal("1000")
    hedge_fee_bps: Decimal = Decimal("12")
    min_abs_funding_rate: Decimal = Decimal("0.0001")

    def required_data(self) -> set[EventType]:
        return {EventType.FUNDING, EventType.MARK}

    def evaluate(self, market_state: MarketState) -> list[Opportunity]:
        marks_by_key = {
            (event.exchange.value, event.market_type.value, event.symbol): event
            for event in market_state.marks()
            if event.event_type == EventType.MARK
        }
        opportunities: list[Opportunity] = []
        for funding in market_state.funding():
            rate = Decimal(str(funding.payload["rate"]))
            if abs(rate) < self.min_abs_funding_rate:
                continue
            mark = marks_by_key.get(
                (funding.exchange.value, funding.market_type.value, funding.symbol)
            )
            if mark is None:
                continue
            mark_price = Decimal(str(mark.payload["mark_price"]))
            qty = self.notional_usd / mark_price
            expected_funding = self.notional_usd * abs(rate)
            fees = self.notional_usd * self.hedge_fee_bps / Decimal("10000")
            score = score_opportunity(
                ScoreInput(
                    gross_edge_usd=expected_funding,
                    fees_usd=fees,
                    slippage_est_usd=Decimal("0"),
                    capacity_usd=self.notional_usd,
                    latency_sensitivity=Decimal("0.25"),
                    funding_exposure=Decimal("0.65"),
                    execution_complexity=Decimal("0.35"),
                )
            )
            side = "sell" if rate > 0 else "buy"
            opportunity = Opportunity(
                strategy=self.name,
                version=self.version,
                legs=[
                    OpportunityLeg(
                        exchange=funding.exchange.value,
                        market_type=funding.market_type.value,
                        symbol=funding.symbol,
                        side=side,
                        price=mark_price,
                        qty=qty,
                    )
                ],
                gross_edge_usd=expected_funding,
                fees_usd=fees,
                slippage_est_usd=Decimal("0"),
                net_edge_usd=score.net_edge_usd,
                capacity_usd=self.notional_usd,
                confidence=score.confidence,
                risk_score=score.risk_score,
                grade=score.grade,
                failure_modes=[],
                data_window_start=min(funding.exchange_ts, mark.exchange_ts),
                data_window_end=max(funding.exchange_ts, mark.exchange_ts),
                metadata={"funding_rate": str(rate), "hedge_direction": side},
            )
            opportunity.failure_modes = self.risk_checks(opportunity)
            opportunities.append(opportunity)
        return opportunities

    def explain(self, opportunity: Opportunity) -> str:
        direction = opportunity.metadata.get("hedge_direction", opportunity.legs[0].side)
        return (
            f"对 {opportunity.legs[0].symbol} 永续执行 {direction} 方向以捕获 funding；"
            f"净 edge 为 {opportunity.net_edge_usd} USD。"
        )

    def risk_checks(self, opportunity: Opportunity) -> list[str]:
        checks: list[str] = []
        if opportunity.net_edge_usd <= 0:
            checks.append("funding_not_enough_after_costs")
        if len(opportunity.legs) < 2:
            checks.append("requires_spot_or_correlated_hedge_before_execution")
        return checks
