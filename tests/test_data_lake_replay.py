from datetime import datetime, timezone
from decimal import Decimal

from packages.data_lake import DataLakeReader, DataLakeWriter
from packages.normalization import MarketEvent, OrderBookPayload, PriceLevel
from packages.replay import ReplayEngine
from packages.strategies import CrossExchangeSpreadStrategy


def _book(exchange: str, bid: str, ask: str) -> MarketEvent:
    return MarketEvent(
        exchange=exchange,
        market_type="spot",
        symbol="BTC-USDT",
        base_asset="BTC",
        quote_asset="USDT",
        event_type="orderbook",
        exchange_ts=datetime(2024, 1, 1, 0, 0, 0, tzinfo=timezone.utc),
        local_ts=datetime(2024, 1, 1, 0, 0, 1, tzinfo=timezone.utc),
        source="unit-test",
        sequence_id=f"{exchange}-1",
        payload=OrderBookPayload(
            bids=(PriceLevel(bid, "1"),),
            asks=(PriceLevel(ask, "1"),),
        ),
    )


def test_data_lake_round_trip_and_replay(tmp_path) -> None:
    events = [_book("binance", bid="100", ask="101"), _book("bybit", bid="104", ask="105")]
    writer = DataLakeWriter(tmp_path, preferred_format="jsonl")
    paths = writer.write_events(events)

    assert len(paths) == 2
    assert all(path.exists() for path in paths)

    replay = ReplayEngine(DataLakeReader(tmp_path)).replay(
        CrossExchangeSpreadStrategy(notional_usd=Decimal("100"), taker_fee_bps=Decimal("0"), slippage_bps=Decimal("0"))
    )

    assert replay.event_count == 2
    assert replay.opportunity_count == 1
    opportunity = replay.opportunities[0]
    assert opportunity.legs[0].exchange == "binance"
    assert opportunity.legs[1].exchange == "bybit"
    assert opportunity.net_edge_usd > 0
