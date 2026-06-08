from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from packages.normalization.models import EventType, MarketType, ensure_utc
from packages.scoring.engine import ScoreInput, score_opportunity
from packages.strategies.interface import MarketState, Opportunity, OpportunityLeg


@dataclass
class CrossExchangeSpreadStrategy:
    name: str = "cross_exchange_spread"
    version: str = "0.1.0"
    min_net_edge_usd: Decimal = Decimal("0")
    notional_usd: Decimal = Decimal("1000")
    taker_fee_bps: Decimal = Decimal("6")
    slippage_bps: Decimal = Decimal("2")

    def required_data(self) -> set[EventType]:
        return {EventType.ORDERBOOK}

    def evaluate(self, market_state: MarketState) -> list[Opportunity]:
        orderbooks = [
            event
            for event in market_state.orderbooks()
            if event.market_type in {MarketType.SPOT, MarketType.PERP}
        ]
        opportunities: list[Opportunity] = []

        symbols = sorted({event.symbol for event in orderbooks})
        for symbol in symbols:
            books = [event for event in orderbooks if event.symbol == symbol]
            for buy_book in books:
                ask = _level(buy_book.payload, "best_ask")
                if ask is None:
                    continue
                for sell_book in books:
                    if sell_book.exchange == buy_book.exchange:
                        continue
                    bid = _level(sell_book.payload, "best_bid")
                    if bid is None or bid["price"] <= ask["price"]:
                        continue
                    opportunities.append(
                        self._build_opportunity(
                            buy_book=buy_book,
                            sell_book=sell_book,
                            ask_price=ask["price"],
                            ask_qty=ask["qty"],
                            bid_price=bid["price"],
                            bid_qty=bid["qty"],
                        )
                    )

        return [
            opportunity
            for opportunity in opportunities
            if opportunity.net_edge_usd >= self.min_net_edge_usd
        ]

    def explain(self, opportunity: Opportunity) -> str:
        return (
            f"在 {opportunity.legs[0].exchange} 买入 {opportunity.legs[0].symbol}，"
            f"在 {opportunity.legs[1].exchange} 卖出；净 edge 为 "
            f"{opportunity.net_edge_usd} USD。"
        )

    def risk_checks(self, opportunity: Opportunity) -> list[str]:
        checks: list[str] = []
        if opportunity.capacity_usd < self.notional_usd:
            checks.append("capacity_below_target_notional")
        if opportunity.net_edge_usd <= 0:
            checks.append("non_positive_after_fees_and_slippage")
        return checks

    def _build_opportunity(
        self,
        *,
        buy_book,
        sell_book,
        ask_price: Decimal,
        ask_qty: Decimal,
        bid_price: Decimal,
        bid_qty: Decimal,
    ) -> Opportunity:
        max_qty_by_notional = self.notional_usd / ask_price
        qty = min(ask_qty, bid_qty, max_qty_by_notional)
        gross_edge = (bid_price - ask_price) * qty
        buy_notional = ask_price * qty
        sell_notional = bid_price * qty
        fees = (buy_notional + sell_notional) * self.taker_fee_bps / Decimal("10000")
        slippage = (buy_notional + sell_notional) * self.slippage_bps / Decimal("10000")
        score = score_opportunity(
            ScoreInput(
                gross_edge_usd=gross_edge,
                fees_usd=fees,
                slippage_est_usd=slippage,
                capacity_usd=min(ask_qty * ask_price, bid_qty * bid_price),
                latency_sensitivity=Decimal("0.75"),
                funding_exposure=Decimal("0.2")
                if MarketType.PERP in {buy_book.market_type, sell_book.market_type}
                else Decimal("0"),
                execution_complexity=Decimal("0.45"),
            )
        )
        start = min(buy_book.exchange_ts, sell_book.exchange_ts)
        end = max(buy_book.exchange_ts, sell_book.exchange_ts)
        opportunity = Opportunity(
            strategy=self.name,
            version=self.version,
            legs=[
                OpportunityLeg(
                    exchange=buy_book.exchange.value,
                    market_type=buy_book.market_type.value,
                    symbol=buy_book.symbol,
                    side="buy",
                    price=ask_price,
                    qty=qty,
                ),
                OpportunityLeg(
                    exchange=sell_book.exchange.value,
                    market_type=sell_book.market_type.value,
                    symbol=sell_book.symbol,
                    side="sell",
                    price=bid_price,
                    qty=qty,
                ),
            ],
            gross_edge_usd=gross_edge,
            fees_usd=fees,
            slippage_est_usd=slippage,
            net_edge_usd=score.net_edge_usd,
            capacity_usd=min(ask_qty * ask_price, bid_qty * bid_price),
            confidence=score.confidence,
            risk_score=score.risk_score,
            grade=score.grade,
            failure_modes=[],
            data_window_start=start,
            data_window_end=end,
            metadata={"spread_usd": str(bid_price - ask_price)},
        )
        opportunity.failure_modes = self.risk_checks(opportunity)
        return opportunity


def _level(payload: dict, side: str) -> dict[str, Decimal] | None:
    if side == "best_ask":
        asks = payload.get("asks", [])
        if not asks:
            return None
        raw = min(asks, key=lambda level: Decimal(str(level["price"])))
    elif side == "best_bid":
        bids = payload.get("bids", [])
        if not bids:
            return None
        raw = max(bids, key=lambda level: Decimal(str(level["price"])))
    else:
        raise ValueError(side)
    return {"price": Decimal(str(raw["price"])), "qty": Decimal(str(raw["qty"]))}
