from datetime import datetime, timezone
from decimal import Decimal

from packages.normalization import (
    FundingPayload,
    Instrument,
    MarketEvent,
    MarkPricePayload,
    OpenInterestPayload,
    TradePayload,
)
from packages.strategies import (
    failure_message_zh,
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
    assert "missing_index_price_for_depeg_filter" in opportunities[0].failure_modes


def test_funding_carry_outputs_spot_perp_hedged_candidate() -> None:
    state = MarketState(
        [
            _event("funding", "perp", FundingPayload(rate="0.003")),
            _event("mark", "spot", MarkPricePayload(mark_price="100")),
            _event("mark", "perp", MarkPricePayload(mark_price="100")),
            _event("index", "perp", {"index_price": "100"}),
        ]
    )

    opportunities = FundingCarryStrategy(
        notional_usd=Decimal("1000"),
        hedge_fee_bps=Decimal("0"),
    ).evaluate(state)

    assert len(opportunities) == 1
    opportunity = opportunities[0]
    assert opportunity.strategy == "funding_carry_vol_filter"
    assert len(opportunity.legs) == 2
    assert opportunity.legs[0].market_type == "spot"
    assert opportunity.legs[0].side == "buy"
    assert opportunity.legs[1].market_type == "perp"
    assert opportunity.legs[1].side == "sell"
    assert opportunity.net_edge_usd == Decimal("3.000")
    assert opportunity.metadata["hedge_direction"] == "spot_long_perp_short"
    assert opportunity.metadata["spot_perp_basis_bps"] == "0.00"
    assert opportunity.metadata["mark_index_divergence_bps"] == "0.00"
    assert opportunity.failure_modes == []


def test_market_state_returns_trade_sequence() -> None:
    state = MarketState(
        [
            _timed_event("trade", "spot", TradePayload("1", "100", "0.1"), TS),
            _timed_event(
                "trade",
                "spot",
                TradePayload("2", "101", "0.2"),
                datetime(2024, 1, 1, 0, 1, tzinfo=timezone.utc),
            ),
        ]
    )

    trades = state.trades(symbol="BTC-USDT")

    assert [trade.payload["trade_id"] for trade in trades] == ["1", "2"]


def test_funding_carry_uses_trade_move_for_volatility_filter() -> None:
    later = datetime(2024, 1, 1, 0, 1, tzinfo=timezone.utc)
    state = MarketState(
        [
            _event("funding", "perp", FundingPayload(rate="0.003")),
            _event("mark", "spot", MarkPricePayload(mark_price="100")),
            _event("mark", "perp", MarkPricePayload(mark_price="100")),
            _event("index", "perp", {"index_price": "100"}),
            _timed_event("trade", "spot", TradePayload("1", "100", "0.1"), TS),
            _timed_event("trade", "spot", TradePayload("2", "101", "0.1"), later),
        ]
    )

    opportunities = FundingCarryStrategy(
        notional_usd=Decimal("1000"),
        hedge_fee_bps=Decimal("0"),
    ).evaluate(state)

    assert len(opportunities) == 1
    assert opportunities[0].metadata["recent_price_move_bps"] == "100.00"
    assert opportunities[0].metadata["recent_price_move_source"] == "trade"


def test_funding_carry_filters_extreme_spot_perp_basis() -> None:
    state = MarketState(
        [
            _event("funding", "perp", FundingPayload(rate="0.003")),
            _event("mark", "spot", MarkPricePayload(mark_price="100")),
            _event("mark", "perp", MarkPricePayload(mark_price="105")),
            _event("index", "perp", {"index_price": "105"}),
        ]
    )

    opportunities = FundingCarryStrategy(
        max_spot_perp_basis_bps=Decimal("200"),
    ).evaluate(state)

    assert opportunities == []


def test_funding_carry_filters_mark_index_depeg() -> None:
    state = MarketState(
        [
            _event("funding", "perp", FundingPayload(rate="0.003")),
            _event("mark", "spot", MarkPricePayload(mark_price="100")),
            _event("mark", "perp", MarkPricePayload(mark_price="100")),
            _event("index", "perp", {"index_price": "98"}),
        ]
    )

    opportunities = FundingCarryStrategy(
        max_mark_index_divergence_bps=Decimal("100"),
    ).evaluate(state)

    assert opportunities == []


def test_funding_carry_filters_recent_trade_move() -> None:
    later = datetime(2024, 1, 1, 1, tzinfo=timezone.utc)
    state = MarketState(
        [
            _event("funding", "perp", FundingPayload(rate="0.003")),
            _event("mark", "spot", MarkPricePayload(mark_price="100")),
            _event("mark", "perp", MarkPricePayload(mark_price="100")),
            _event("index", "perp", {"index_price": "100"}),
            _timed_event("trade", "spot", TradePayload("1", "100", "0.1"), TS),
            _timed_event("trade", "spot", TradePayload("2", "107", "0.1"), later),
        ]
    )

    opportunities = FundingCarryStrategy(
        max_recent_price_move_bps=Decimal("500"),
    ).evaluate(state)

    assert opportunities == []


def test_funding_carry_falls_back_to_mark_move_when_trades_missing() -> None:
    later = datetime(2024, 1, 1, 1, tzinfo=timezone.utc)
    state = MarketState(
        [
            _event("funding", "perp", FundingPayload(rate="0.003")),
            _timed_event("mark", "spot", MarkPricePayload(mark_price="100"), TS),
            _timed_event("mark", "spot", MarkPricePayload(mark_price="101"), later),
            _event("mark", "perp", MarkPricePayload(mark_price="101")),
            _event("index", "perp", {"index_price": "101"}),
        ]
    )

    opportunities = FundingCarryStrategy(
        notional_usd=Decimal("1000"),
        hedge_fee_bps=Decimal("0"),
    ).evaluate(state)

    assert len(opportunities) == 1
    assert opportunities[0].metadata["recent_price_move_bps"] == "100.00"
    assert opportunities[0].metadata["recent_price_move_source"] == "mark"


def test_funding_carry_failure_messages_are_localized() -> None:
    assert "index price" in failure_message_zh("missing_index_price_for_depeg_filter")


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


def test_futures_basis_uses_instrument_expiry_metadata() -> None:
    expiry = datetime(2024, 1, 31, tzinfo=timezone.utc)
    state = MarketState(
        [
            _event("mark", "spot", MarkPricePayload(mark_price="100")),
            _event("mark", "future", MarkPricePayload(mark_price="103")),
            _event(
                "instrument",
                "future",
                Instrument(
                    exchange="binance",
                    market_type="future",
                    symbol="BTC-USDT",
                    base_asset="BTC",
                    quote_asset="USDT",
                    contract_size="1",
                    expiry_ts=expiry,
                ),
            ),
        ]
    )

    opportunities = FuturesBasisStrategy(
        notional_usd=Decimal("1000"),
        taker_fee_bps=Decimal("0"),
        slippage_bps=Decimal("0"),
        min_basis_bps=Decimal("10"),
    ).evaluate(state)

    assert len(opportunities) == 1
    assert opportunities[0].strategy == "quarterly_basis_convergence"
    assert opportunities[0].metadata["basis_bps"] == "300.00"
    assert opportunities[0].metadata["expiry_ts"] == "2024-01-31T00:00:00+00:00"
    assert opportunities[0].metadata["days_to_expiry"] == "30.00"
    assert opportunities[0].metadata["annualized_basis"] == "0.3650"
    assert opportunities[0].metadata["contract_size"] == "1"
    assert "requires_expiry_and_borrow_checks_before_execution" not in opportunities[0].failure_modes


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
