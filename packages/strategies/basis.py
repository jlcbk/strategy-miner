from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from packages.normalization.models import EventType, MarketType
from packages.scoring.engine import ScoreInput, score_opportunity
from packages.strategies.interface import MarketState, Opportunity, OpportunityLeg


@dataclass
class FuturesBasisStrategy:
    name: str = "futures_basis"
    version: str = "0.1.0"
    notional_usd: Decimal = Decimal("1000")
    taker_fee_bps: Decimal = Decimal("12")
    slippage_bps: Decimal = Decimal("3")
    min_basis_bps: Decimal = Decimal("10")

    def required_data(self) -> set[EventType]:
        return {EventType.MARK}

    def evaluate(self, market_state: MarketState) -> list[Opportunity]:
        marks = market_state.marks()
        spot_marks = {
            (event.exchange.value, event.symbol): event
            for event in marks
            if event.market_type == MarketType.SPOT and event.event_type == EventType.MARK
        }
        opportunities: list[Opportunity] = []
        for future in marks:
            if future.market_type != MarketType.FUTURE or future.event_type != EventType.MARK:
                continue
            spot = spot_marks.get((future.exchange.value, future.symbol))
            if spot is None:
                continue
            future_price = Decimal(str(future.payload["mark_price"]))
            spot_price = Decimal(str(spot.payload["mark_price"]))
            basis_bps = (future_price - spot_price) / spot_price * Decimal("10000")
            if abs(basis_bps) < self.min_basis_bps:
                continue
            qty = self.notional_usd / spot_price
            gross_edge = abs(future_price - spot_price) * qty
            fees = self.notional_usd * self.taker_fee_bps / Decimal("10000")
            slippage = self.notional_usd * self.slippage_bps / Decimal("10000")
            score = score_opportunity(
                ScoreInput(
                    gross_edge_usd=gross_edge,
                    fees_usd=fees,
                    slippage_est_usd=slippage,
                    capacity_usd=self.notional_usd,
                    latency_sensitivity=Decimal("0.35"),
                    funding_exposure=Decimal("0.15"),
                    execution_complexity=Decimal("0.5"),
                )
            )
            future_side = "sell" if basis_bps > 0 else "buy"
            spot_side = "buy" if basis_bps > 0 else "sell"
            opportunity = Opportunity(
                strategy=self.name,
                version=self.version,
                legs=[
                    OpportunityLeg(
                        exchange=spot.exchange.value,
                        market_type=spot.market_type.value,
                        symbol=spot.symbol,
                        side=spot_side,
                        price=spot_price,
                        qty=qty,
                    ),
                    OpportunityLeg(
                        exchange=future.exchange.value,
                        market_type=future.market_type.value,
                        symbol=future.symbol,
                        side=future_side,
                        price=future_price,
                        qty=qty,
                    ),
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
                data_window_start=min(spot.exchange_ts, future.exchange_ts),
                data_window_end=max(spot.exchange_ts, future.exchange_ts),
                metadata={"basis_bps": str(basis_bps)},
            )
            opportunity.failure_modes = self.risk_checks(opportunity)
            opportunities.append(opportunity)
        return opportunities

    def explain(self, opportunity: Opportunity) -> str:
        return (
            f"交易 {opportunity.legs[0].symbol} 的现货/交割合约 basis；"
            f"净 edge 为 {opportunity.net_edge_usd} USD。"
        )

    def risk_checks(self, opportunity: Opportunity) -> list[str]:
        checks: list[str] = []
        if opportunity.net_edge_usd <= 0:
            checks.append("basis_not_enough_after_costs")
        checks.append("requires_expiry_and_borrow_checks_before_execution")
        return checks
