from datetime import datetime, timezone

import pytest

from packages.normalization import (
    EventType,
    Exchange,
    MarketEvent,
    MarketType,
    OrderBookPayload,
    PriceLevel,
    normalize_symbol,
)


def test_market_event_normalizes_required_contract() -> None:
    payload = OrderBookPayload(
        bids=(PriceLevel("100", "2"),),
        asks=(PriceLevel("101", "1.5"),),
        update_id=10,
        sequence_id=11,
    )

    event = MarketEvent(
        exchange="binance",
        market_type="spot",
        symbol="btcusdt",
        base_asset="btc",
        quote_asset="usdt",
        event_type="orderbook",
        exchange_ts=1_700_000_000_000,
        local_ts=datetime(2023, 11, 14, tzinfo=timezone.utc),
        source="unit-test",
        sequence_id=11,
        payload=payload,
    )

    data = event.to_dict()
    assert data["exchange"] == Exchange.BINANCE.value
    assert data["market_type"] == MarketType.SPOT.value
    assert data["event_type"] == EventType.ORDERBOOK.value
    assert data["symbol"] == "BTCUSDT"
    assert data["base_asset"] == "BTC"
    assert data["payload"]["bids"][0] == {"price": "100", "qty": "2"}


def test_orderbook_payload_rejects_more_than_top_20_levels() -> None:
    levels = tuple(PriceLevel("100", "1") for _ in range(21))
    with pytest.raises(ValueError, match="top 20"):
        OrderBookPayload(bids=levels, asks=())


def test_normalize_symbol_across_exchange_styles() -> None:
    assert normalize_symbol("binance", "BTCUSDT", "spot").symbol == "BTC-USDT"
    assert normalize_symbol("okx", "BTC-USDT-SWAP", "perp").symbol == "BTC-USDT"
    assert normalize_symbol("okx", "BTC-USD-240628", "future").symbol == "BTC-USD-240628"
