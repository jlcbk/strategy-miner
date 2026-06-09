from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP

from packages.normalization.models import EventType, MarketEvent, MarketType
from packages.scoring.engine import ScoreInput, score_opportunity
from packages.strategies.interface import MarketState, Opportunity, OpportunityLeg


@dataclass
class FundingCarryStrategy:
    name: str = "funding_carry_vol_filter"
    version: str = "0.1.0"
    notional_usd: Decimal = Decimal("1000")
    hedge_fee_bps: Decimal = Decimal("12")
    min_abs_funding_rate: Decimal = Decimal("0.0001")
    max_spot_perp_basis_bps: Decimal = Decimal("200")
    max_mark_index_divergence_bps: Decimal = Decimal("100")
    max_recent_price_move_bps: Decimal = Decimal("500")

    def required_data(self) -> set[EventType]:
        return {EventType.FUNDING, EventType.MARK, EventType.INDEX, EventType.TRADE}

    def evaluate(self, market_state: MarketState) -> list[Opportunity]:
        perp_marks_by_key = {
            (event.exchange.value, event.market_type.value, event.symbol): event
            for event in market_state.marks()
            if event.event_type == EventType.MARK and event.market_type == MarketType.PERP
        }
        spot_marks_by_key = {
            (event.exchange.value, event.symbol): event
            for event in market_state.marks()
            if event.event_type == EventType.MARK and event.market_type == MarketType.SPOT
        }
        indexes_by_key = {
            (event.exchange.value, event.symbol): event
            for event in market_state.marks()
            if event.event_type == EventType.INDEX and event.market_type == MarketType.PERP
        }
        opportunities: list[Opportunity] = []
        for funding in market_state.funding():
            rate = Decimal(str(funding.payload["rate"]))
            if rate < self.min_abs_funding_rate:
                continue
            perp_mark = perp_marks_by_key.get(
                (funding.exchange.value, funding.market_type.value, funding.symbol)
            )
            if perp_mark is None:
                continue
            spot_mark = spot_marks_by_key.get((funding.exchange.value, funding.symbol))
            index = indexes_by_key.get((funding.exchange.value, funding.symbol))
            if self._filtered_by_basis_or_index(perp_mark, spot_mark, index):
                continue
            recent_move_bps, recent_move_source = self._recent_price_move_bps(
                market_state,
                funding,
                spot_mark,
            )
            if (
                recent_move_bps is not None
                and recent_move_bps > self.max_recent_price_move_bps
            ):
                continue

            perp_price = Decimal(str(perp_mark.payload["mark_price"]))
            spot_price = (
                Decimal(str(spot_mark.payload["mark_price"]))
                if spot_mark is not None
                else perp_price
            )
            qty = self.notional_usd / spot_price
            perp_notional = qty * perp_price
            combined_notional = self.notional_usd + (
                self.notional_usd if spot_mark is None else perp_notional
            )
            expected_funding = perp_notional * rate
            fees = combined_notional * self.hedge_fee_bps / Decimal("10000")
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
            legs = []
            if spot_mark is not None:
                legs.append(
                    OpportunityLeg(
                        exchange=spot_mark.exchange.value,
                        market_type=spot_mark.market_type.value,
                        symbol=spot_mark.symbol,
                        side="buy",
                        price=spot_price,
                        qty=qty,
                    )
                )
            legs.append(
                OpportunityLeg(
                    exchange=funding.exchange.value,
                    market_type=funding.market_type.value,
                    symbol=funding.symbol,
                    side="sell",
                    price=perp_price,
                    qty=qty,
                )
            )
            opportunity = Opportunity(
                strategy=self.name,
                version=self.version,
                legs=legs,
                gross_edge_usd=expected_funding,
                fees_usd=fees,
                slippage_est_usd=Decimal("0"),
                net_edge_usd=score.net_edge_usd,
                capacity_usd=self.notional_usd,
                confidence=score.confidence,
                risk_score=score.risk_score,
                grade=score.grade,
                failure_modes=[],
                data_window_start=min(
                    event.exchange_ts
                    for event in (funding, perp_mark, spot_mark, index)
                    if event is not None
                ),
                data_window_end=max(
                    event.exchange_ts
                    for event in (funding, perp_mark, spot_mark, index)
                    if event is not None
                ),
                metadata=self._metadata(
                    rate=rate,
                    perp_mark=perp_mark,
                    spot_mark=spot_mark,
                    index=index,
                    recent_move_bps=recent_move_bps,
                    recent_move_source=recent_move_source,
                ),
            )
            opportunity.failure_modes = self.risk_checks(opportunity)
            opportunities.append(opportunity)
        return opportunities

    def explain(self, opportunity: Opportunity) -> str:
        symbol = opportunity.legs[-1].symbol
        return (
            f"对 {symbol} 执行 spot 多头 + perp 空头以捕获正 funding；"
            f"净 edge 为 {opportunity.net_edge_usd} USD。"
        )

    def risk_checks(self, opportunity: Opportunity) -> list[str]:
        checks: list[str] = []
        if opportunity.net_edge_usd <= 0:
            checks.append("funding_not_enough_after_costs")
        if len(opportunity.legs) < 2:
            checks.append("requires_spot_or_correlated_hedge_before_execution")
        if opportunity.metadata.get("index_price") is None:
            checks.append("missing_index_price_for_depeg_filter")
        return checks

    def _filtered_by_basis_or_index(
        self,
        perp_mark: MarketEvent,
        spot_mark: MarketEvent | None,
        index: MarketEvent | None,
    ) -> bool:
        if spot_mark is not None:
            basis_bps = self._spot_perp_basis_bps(perp_mark, spot_mark)
            if abs(basis_bps) > self.max_spot_perp_basis_bps:
                return True
        if index is not None:
            divergence_bps = self._mark_index_divergence_bps(perp_mark, index)
            if abs(divergence_bps) > self.max_mark_index_divergence_bps:
                return True
        return False

    def _metadata(
        self,
        *,
        rate: Decimal,
        perp_mark: MarketEvent,
        spot_mark: MarketEvent | None,
        index: MarketEvent | None,
        recent_move_bps: Decimal | None,
        recent_move_source: str | None,
    ) -> dict[str, str | None]:
        return {
            "funding_rate": str(rate),
            "hedge_direction": "spot_long_perp_short",
            "spot_perp_basis_bps": (
                None
                if spot_mark is None
                else _format_bps(self._spot_perp_basis_bps(perp_mark, spot_mark))
            ),
            "mark_index_divergence_bps": (
                None
                if index is None
                else _format_bps(self._mark_index_divergence_bps(perp_mark, index))
            ),
            "recent_price_move_bps": (
                None if recent_move_bps is None else _format_bps(recent_move_bps)
            ),
            "recent_price_move_source": recent_move_source,
            "index_price": None if index is None else str(_price(index)),
        }

    def _spot_perp_basis_bps(self, perp_mark: MarketEvent, spot_mark: MarketEvent) -> Decimal:
        spot_price = _price(spot_mark)
        return (_price(perp_mark) - spot_price) / spot_price * Decimal("10000")

    def _mark_index_divergence_bps(self, perp_mark: MarketEvent, index: MarketEvent) -> Decimal:
        index_price = _price(index)
        return (_price(perp_mark) - index_price) / index_price * Decimal("10000")

    def _recent_price_move_bps(
        self,
        market_state: MarketState,
        funding: MarketEvent,
        spot_mark: MarketEvent | None,
    ) -> tuple[Decimal | None, str | None]:
        market_type = MarketType.SPOT if spot_mark is not None else MarketType.PERP
        trade_move = _max_sequential_move_bps(
            [
                event
                for event in market_state.trades(symbol=funding.symbol)
                if event.exchange == funding.exchange
                and event.market_type == market_type
            ]
        )
        if trade_move is not None:
            return trade_move, "trade"

        mark_move = _max_sequential_move_bps(
            [
                event
                for event in market_state.events
                if event.exchange == funding.exchange
                and event.symbol == funding.symbol
                and event.market_type == market_type
                and event.event_type == EventType.MARK
            ]
        )
        if mark_move is not None:
            return mark_move, "mark"
        return None, None


def _max_sequential_move_bps(events: list[MarketEvent]) -> Decimal | None:
    prices = sorted(events, key=lambda event: event.exchange_ts)
    if len(prices) < 2:
        return None
    moves = [
        abs((_price(current) - _price(previous)) / _price(previous) * Decimal("10000"))
        for previous, current in zip(prices, prices[1:])
        if _price(previous) > 0
    ]
    return max(moves, default=None)


def _price(event: MarketEvent) -> Decimal:
    if event.event_type == EventType.INDEX:
        payload_key = "index_price"
    elif event.event_type == EventType.TRADE:
        payload_key = "price"
    else:
        payload_key = "mark_price"
    return Decimal(str(event.payload[payload_key]))


def _format_bps(value: Decimal) -> str:
    return str(value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))
