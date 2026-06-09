from datetime import date, datetime, timezone

from packages.connectors.base import HistoricalDataRequest
from packages.connectors.binance import BinanceConnector
from packages.connectors.bybit import BybitConnector
from packages.connectors.okx import OKXConnector
from packages.connectors.bitget import BitgetConnector
from packages.normalization import EventType, Exchange, MarketType


def test_binance_public_trade_archive_url() -> None:
    request = HistoricalDataRequest(
        exchange=Exchange.BINANCE,
        market_type=MarketType.SPOT,
        symbol="BTCUSDT",
        event_type=EventType.TRADE,
        day=date(2024, 1, 2),
    )
    file = BinanceConnector().historical_file(request)

    assert file.url == (
        "https://data.binance.vision/data/spot/daily/trades/"
        "BTCUSDT/BTCUSDT-trades-2024-01-02.zip"
    )
    assert file.compression == "zip"


def test_bybit_public_trade_archive_url() -> None:
    request = HistoricalDataRequest(
        exchange=Exchange.BYBIT,
        market_type=MarketType.PERP,
        symbol="BTCUSDT",
        event_type=EventType.TRADE,
        day=date(2024, 1, 2),
    )
    file = BybitConnector().historical_file(request)

    assert file.url == "https://public.bybit.com/trading/BTCUSDT/BTCUSDT2024-01-02.csv.gz"
    assert file.compression == "gzip"


def test_websocket_subscriptions_cover_core_event_types() -> None:
    assert "btcusdt@trade" in BinanceConnector().websocket_subscription(
        market_type=MarketType.SPOT,
        symbol="BTCUSDT",
        event_types=[EventType.TRADE],
    ).url

    okx = OKXConnector().websocket_subscription(
        market_type=MarketType.PERP,
        symbol="BTCUSDT",
        event_types=[EventType.ORDERBOOK, EventType.MARK],
    )
    assert okx.url == "wss://ws.okx.com:8443/ws/v5/public"
    assert {"channel": "books", "instId": "BTC-USDT-SWAP"} in okx.payload["args"]

    bitget = BitgetConnector().websocket_subscription(
        market_type=MarketType.SPOT,
        symbol="BTCUSDT",
        event_types=[EventType.ORDERBOOK],
    )
    assert bitget.payload["args"][0]["channel"] == "books20"


def test_open_interest_rest_endpoints_cover_core_derivatives_exchanges() -> None:
    binance = BinanceConnector().open_interest_endpoint(
        market_type=MarketType.PERP,
        symbol="BTCUSDT",
    )
    assert binance.url == "https://fapi.binance.com/fapi/v1/openInterest"
    assert binance.params == {"symbol": "BTCUSDT"}

    bybit = BybitConnector().open_interest_endpoint(
        market_type=MarketType.PERP,
        symbol="BTCUSDT",
    )
    assert bybit.params["category"] == "linear"
    assert bybit.params["intervalTime"] == "5min"

    okx = OKXConnector().open_interest_endpoint(
        market_type=MarketType.PERP,
        symbol="BTCUSDT",
    )
    assert okx.params == {"instType": "SWAP", "instId": "BTC-USDT-SWAP"}

    bitget = BitgetConnector().open_interest_endpoint(
        market_type=MarketType.PERP,
        symbol="BTCUSDT",
    )
    assert bitget.params == {"symbol": "BTCUSDT", "productType": "USDT-FUTURES"}


def test_binance_open_interest_history_endpoint_uses_day_window_params() -> None:
    endpoint = BinanceConnector().open_interest_history_endpoint(
        market_type=MarketType.PERP,
        symbol="BTC-USDT",
        start_ts=datetime(2024, 1, 1, tzinfo=timezone.utc),
        end_ts=datetime(2024, 1, 2, tzinfo=timezone.utc),
        interval="5m",
        limit=288,
    )

    assert endpoint.url == "https://fapi.binance.com/futures/data/openInterestHist"
    assert endpoint.params == {
        "symbol": "BTCUSDT",
        "period": "5m",
        "startTime": "1704067200000",
        "endTime": "1704153600000",
        "limit": "288",
    }


def test_binance_open_interest_history_parser_normalizes_events() -> None:
    events = BinanceConnector().parse_open_interest_history(
        market_type=MarketType.PERP,
        symbol="BTCUSDT",
        interval="5m",
        rows=[
            {
                "symbol": "BTCUSDT",
                "sumOpenInterest": "20403.123",
                "sumOpenInterestValue": "884000000.5",
                "timestamp": 1704067200000,
            },
            {"symbol": "BTCUSDT", "timestamp": 1704067500000},
        ],
    )

    assert len(events) == 1
    event = events[0]
    assert event.exchange == Exchange.BINANCE
    assert event.market_type == MarketType.PERP
    assert event.symbol == "BTC-USDT"
    assert event.event_type == EventType.OPEN_INTEREST
    assert event.partition_date == "2024-01-01"
    assert event.sequence_id == "BTCUSDT:1704067200000"
    assert event.payload == {
        "open_interest": "20403.123",
        "open_interest_value_usd": "884000000.5",
        "unit": "contracts",
        "interval": "5m",
    }


def test_binance_funding_rate_history_endpoint_uses_day_window_params() -> None:
    endpoint = BinanceConnector().funding_rate_history_endpoint(
        market_type=MarketType.PERP,
        symbol="BTC-USDT",
        start_ts=datetime(2024, 1, 1, tzinfo=timezone.utc),
        end_ts=datetime(2024, 1, 2, tzinfo=timezone.utc),
        limit=1000,
    )

    assert endpoint.url == "https://fapi.binance.com/fapi/v1/fundingRate"
    assert endpoint.params == {
        "symbol": "BTCUSDT",
        "startTime": "1704067200000",
        "endTime": "1704153600000",
        "limit": "1000",
    }


def test_binance_funding_rate_history_parser_normalizes_events() -> None:
    events = BinanceConnector().parse_funding_rate_history(
        market_type=MarketType.PERP,
        symbol="BTCUSDT",
        rows=[
            {
                "symbol": "BTCUSDT",
                "fundingRate": "0.00010000",
                "fundingTime": 1704067200000,
                "markPrice": "42283.58",
            },
            {"symbol": "BTCUSDT", "fundingTime": 1704096000000},
        ],
    )

    assert len(events) == 1
    event = events[0]
    assert event.exchange == Exchange.BINANCE
    assert event.market_type == MarketType.PERP
    assert event.symbol == "BTC-USDT"
    assert event.event_type == EventType.FUNDING
    assert event.partition_date == "2024-01-01"
    assert event.sequence_id == "BTCUSDT:1704067200000"
    assert event.payload == {
        "rate": "0.00010000",
        "next_funding_ts": None,
        "interval_hours": "8",
    }
