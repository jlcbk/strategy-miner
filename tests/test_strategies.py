from datetime import datetime, timezone
from decimal import Decimal

from packages.normalization import (
    FundingPayload,
    MarketEvent,
    MarkPricePayload,
    OpenInterestPayload,
)
from packages.strategies import (
    FundingCarryStrategy,
    FuturesBasisStrategy,
    MarketState,
    OpenInterestMomentumStrategy,
)


TS = datetime(2024, 1, 1, tzinfo=timezone.utc)


def _event(event_type: str, market_type: str, payload: object) -> MarketEvent:
    return MarketEvent(
        exchange="binance",
        market_type=market_type,
        symbol="BTC-USDT",
        base_asset="BTC",
        quote_asset="USDT",
        event_type=event_type,
        exchange_ts=TS,
        local_ts=TS,
        source="unit-test",
        sequence_id=f"{event_type}-{market_type}",
        payload=payload,
    )


def _timed_event(
    event_type: str,
    market_type: str,
    payload: object,
    ts: datetime,
) -> MarketEvent:
    return MarketEvent(
        exchange="binance",
        market_type=market_type,
        symbol="BTC-USDT",
        base_asset="BTC",
        quote_asset="USDT",
        event_type=event_type,
        exchange_ts=ts,
        local_ts=ts,
        source="unit-test",
        sequence_id=f"{event_type}-{market_type}-{ts.isoformat()}",
        payload=payload,
    )


def test_funding_carry_outputs_failure_for_unhedged_positive_edge() -> None:
    state = MarketState(
        [
            _event("funding", "perp", FundingPayload(rate="0.003")),
            _event("mark", "perp", MarkPricePayload(mark_price="100")),
        ]
    )

    opportunities = FundingCarryStrategy(
        notional_usd=Decimal("1000"),
        hedge_fee_bps=Decimal("0"),
    ).evaluate(state)

    assert len(opportunities) == 1
    assert opportunities[0].net_edge_usd == Decimal("3.000")
    assert "requires_spot_or_correlated_hedge_before_execution" in opportunities[0].failure_modes


def test_futures_basis_detects_spot_future_gap() -> None:
    state = MarketState(
        [
            _event("mark", "spot", MarkPricePayload(mark_price="100")),
            _event("mark", "future", MarkPricePayload(mark_price="103")),
        ]
    )

    opportunities = FuturesBasisStrategy(
        notional_usd=Decimal("1000"),
        taker_fee_bps=Decimal("0"),
        slippage_bps=Decimal("0"),
        min_basis_bps=Decimal("10"),
    ).evaluate(state)

    assert len(opportunities) == 1
    assert opportunities[0].legs[0].side == "buy"
    assert opportunities[0].legs[1].side == "sell"
    assert opportunities[0].metadata["basis_bps"] == "300.00"


def test_open_interest_momentum_detects_confirmed_breakout() -> None:
    later = datetime(2024, 1, 1, 1, tzinfo=timezone.utc)
    state = MarketState(
        [
            _timed_event("mark", "perp", MarkPricePayload(mark_price="100"), TS),
            _timed_event("mark", "perp", MarkPricePayload(mark_price="102"), later),
            _timed_event(
                "open_interest",
                "perp",
                OpenInterestPayload(open_interest="1000"),
                TS,
            ),
            _timed_event(
                "open_interest",
                "perp",
                OpenInterestPayload(open_interest="1060"),
                later,
            ),
            _timed_event("funding", "perp", FundingPayload(rate="0.0002"), later),
        ]
    )

    opportunities = OpenInterestMomentumStrategy(
        notional_usd=Decimal("1000"),
        min_price_move_bps=Decimal("100"),
        min_oi_change_pct=Decimal("3"),
        taker_fee_bps=Decimal("0"),
        slippage_bps=Decimal("0"),
    ).evaluate(state)

    assert len(opportunities) == 1
    assert opportunities[0].strategy == "oi_confirmed_momentum"
    assert opportunities[0].legs[0].side == "buy"
    assert opportunities[0].metadata["oi_change_pct"] == "6.00"
    assert "requires_oi_venue_definition_before_validation" in opportunities[0].failure_modes


def test_open_interest_momentum_filters_crowded_funding() -> None:
    later = datetime(2024, 1, 1, 1, tzinfo=timezone.utc)
    state = MarketState(
        [
            _timed_event("mark", "perp", MarkPricePayload(mark_price="100"), TS),
            _timed_event("mark", "perp", MarkPricePayload(mark_price="102"), later),
            _timed_event(
                "open_interest",
                "perp",
                OpenInterestPayload(open_interest="1000"),
                TS,
            ),
            _timed_event(
                "open_interest",
                "perp",
                OpenInterestPayload(open_interest="1060"),
                later,
            ),
            _timed_event("funding", "perp", FundingPayload(rate="0.003"), later),
        ]
    )

    opportunities = OpenInterestMomentumStrategy(
        min_price_move_bps=Decimal("100"),
        min_oi_change_pct=Decimal("3"),
        max_abs_funding_rate=Decimal("0.001"),
    ).evaluate(state)

    assert opportunities == []
