from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP

from packages.normalization.models import EventType, MarketEvent, MarketType, ensure_utc
from packages.scoring.engine import ScoreInput, score_opportunity
from packages.strategies.interface import MarketState, Opportunity, OpportunityLeg


@dataclass
class FuturesBasisStrategy:
    name: str = "quarterly_basis_convergence"
    version: str = "0.1.0"
    notional_usd: Decimal = Decimal("1000")
    taker_fee_bps: Decimal = Decimal("12")
    slippage_bps: Decimal = Decimal("3")
    min_basis_bps: Decimal = Decimal("10")

    def required_data(self) -> set[EventType]:
        return {EventType.MARK, EventType.INSTRUMENT}

    def evaluate(self, market_state: MarketState) -> list[Opportunity]:
        marks = market_state.marks()
        spot_marks = {
            (event.exchange.value, event.symbol): event
            for event in marks
            if event.market_type == MarketType.SPOT and event.event_type == EventType.MARK
        }
        future_instruments = {
            (event.exchange.value, event.symbol): event
            for event in market_state.instruments()
            if event.market_type == MarketType.FUTURE
        }
        opportunities: list[Opportunity] = []
        for future in marks:
            if future.market_type != MarketType.FUTURE or future.event_type != EventType.MARK:
                continue
            spot = spot_marks.get((future.exchange.value, future.symbol))
            if spot is None:
                continue
            instrument = future_instruments.get((future.exchange.value, future.symbol))
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
                metadata=self._metadata(
                    basis_bps=basis_bps,
                    future=future,
                    instrument=instrument,
                ),
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
        if opportunity.metadata.get("expiry_ts") is None:
            checks.append("requires_expiry_and_borrow_checks_before_execution")
        return checks

    def _metadata(
        self,
        *,
        basis_bps: Decimal,
        future: MarketEvent,
        instrument: MarketEvent | None,
    ) -> dict[str, str | None]:
        expiry_ts = None
        contract_size = None
        days_to_expiry = None
        annualized_basis = None
        if instrument is not None:
            contract_size = _optional_decimal(instrument.payload.get("contract_size"))
            raw_expiry = instrument.payload.get("expiry_ts")
            if raw_expiry is not None:
                expiry = ensure_utc(raw_expiry)
                expiry_ts = expiry.isoformat()
                days = Decimal(str((expiry - future.exchange_ts).total_seconds())) / Decimal("86400")
                if days > 0:
                    days_to_expiry = _format_decimal(days, places="0.01")
                    annualized_basis = _format_decimal(
                        (basis_bps / Decimal("10000")) * Decimal("365") / days,
                        places="0.0001",
                    )
        return {
            "basis_bps": _format_decimal(basis_bps, places="0.01"),
            "expiry_ts": expiry_ts,
            "days_to_expiry": days_to_expiry,
            "annualized_basis": annualized_basis,
            "contract_size": None if contract_size is None else str(contract_size),
        }


def _optional_decimal(value) -> Decimal | None:
    if value is None:
        return None
    return Decimal(str(value))


def _format_decimal(value: Decimal, *, places: str) -> str:
    return str(value.quantize(Decimal(places), rounding=ROUND_HALF_UP))
