import io
import zipfile
from datetime import date, datetime, timezone
from urllib.error import HTTPError

import pytest

from packages.connectors import base as connector_base
from packages.connectors.base import DownloadError, HistoricalDataRequest, RestMarketDataEndpoint
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


def test_download_json_wraps_http_errors(monkeypatch) -> None:
    def fake_urlopen(url, timeout):
        raise HTTPError(url, 451, "", hdrs=None, fp=None)

    monkeypatch.setattr(connector_base, "urlopen", fake_urlopen)

    with pytest.raises(DownloadError, match="HTTP 451") as exc_info:
        connector_base.download_json(
            RestMarketDataEndpoint(
                url="https://example.test/api",
                params={"symbol": "BTCUSDT"},
            )
        )

    assert "https://example.test/api?symbol=BTCUSDT" in str(exc_info.value)


def test_binance_public_mark_price_archive_url() -> None:
    request = HistoricalDataRequest(
        exchange=Exchange.BINANCE,
        market_type=MarketType.PERP,
        symbol="BTCUSDT",
        event_type=EventType.MARK,
        day=date(2024, 1, 2),
        interval="1m",
    )
    file = BinanceConnector().historical_file(request)

    assert file.url == (
        "https://data.binance.vision/data/futures/um/daily/markPriceKlines/"
        "BTCUSDT/1m/BTCUSDT-1m-2024-01-02.zip"
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


def test_bybit_low_risk_rest_endpoints_use_day_window_params() -> None:
    start = datetime(2026, 6, 8, tzinfo=timezone.utc)
    end = datetime(2026, 6, 9, tzinfo=timezone.utc)

    funding = BybitConnector().funding_rate_history_endpoint(
        market_type=MarketType.PERP,
        symbol="BTCUSDT",
        start_ts=start,
        end_ts=end,
    )
    assert funding.url == "https://api.bybit.com/v5/market/funding/history"
    assert funding.params["category"] == "linear"
    assert funding.params["symbol"] == "BTCUSDT"
    assert funding.params["startTime"] == "1780876800000"

    oi = BybitConnector().open_interest_history_endpoint(
        market_type=MarketType.PERP,
        symbol="BTCUSDT",
        start_ts=start,
        end_ts=end,
        interval="5min",
    )
    assert oi.url == "https://api.bybit.com/v5/market/open-interest"
    assert oi.params["intervalTime"] == "5min"

    mark = BybitConnector().mark_price_kline_endpoint(
        market_type=MarketType.PERP,
        symbol="BTCUSDT",
        start_ts=start,
        end_ts=end,
        interval="5m",
    )
    assert mark.url == "https://api.bybit.com/v5/market/mark-price-kline"
    assert mark.params["interval"] == "5"


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


def test_binance_orderbook_snapshot_endpoint_uses_top20_depth() -> None:
    spot = BinanceConnector().orderbook_snapshot_endpoint(
        market_type=MarketType.SPOT,
        symbol="BTC-USDT",
        limit=20,
    )
    perp = BinanceConnector().orderbook_snapshot_endpoint(
        market_type=MarketType.PERP,
        symbol="BTCUSDT",
        limit=20,
    )

    assert spot.url == "https://api.binance.com/api/v3/depth"
    assert spot.params == {"symbol": "BTCUSDT", "limit": "20"}
    assert perp.url == "https://fapi.binance.com/fapi/v1/depth"
    assert perp.params == {"symbol": "BTCUSDT", "limit": "20"}


def test_binance_orderbook_snapshot_parser_caps_top20_levels() -> None:
    observed_at = datetime(2026, 6, 9, 1, 0, tzinfo=timezone.utc)
    events = BinanceConnector().parse_orderbook_snapshot(
        market_type=MarketType.PERP,
        symbol="BTCUSDT",
        observed_at=observed_at,
        limit=20,
        row={
            "lastUpdateId": 123,
            "T": 1780966800000,
            "bids": [[str(100 - index), "1"] for index in range(25)],
            "asks": [[str(101 + index), "2"] for index in range(25)],
        },
    )

    assert len(events) == 1
    event = events[0]
    assert event.exchange == Exchange.BINANCE
    assert event.market_type == MarketType.PERP
    assert event.event_type == EventType.ORDERBOOK
    assert event.symbol == "BTC-USDT"
    assert event.sequence_id == "BTCUSDT:123"
    assert event.partition_date == "2026-06-09"
    assert len(event.payload["bids"]) == 20
    assert len(event.payload["asks"]) == 20
    assert event.payload["update_id"] == "123"
    assert event.payload["is_snapshot"] is True


def test_binance_instrument_snapshot_endpoint_uses_exchange_info() -> None:
    spot = BinanceConnector().instrument_snapshot_endpoint(market_type=MarketType.SPOT)
    perp = BinanceConnector().instrument_snapshot_endpoint(market_type=MarketType.PERP)

    assert spot.url == "https://api.binance.com/api/v3/exchangeInfo"
    assert spot.params == {}
    assert perp.url == "https://fapi.binance.com/fapi/v1/exchangeInfo"
    assert perp.params == {}


def test_binance_instrument_snapshot_parser_normalizes_symbol_metadata() -> None:
    observed_at = datetime(2026, 6, 9, 1, 0, tzinfo=timezone.utc)
    events = BinanceConnector().parse_instrument_snapshot(
        market_type=MarketType.PERP,
        symbol="BTCUSDT",
        observed_at=observed_at,
        row={
            "symbols": [
                {
                    "symbol": "ETHUSDT",
                    "baseAsset": "ETH",
                    "quoteAsset": "USDT",
                },
                {
                    "symbol": "BTCUSDT",
                    "baseAsset": "BTC",
                    "quoteAsset": "USDT",
                    "pricePrecision": 2,
                    "quantityPrecision": 3,
                    "deliveryDate": 4133404800000,
                    "status": "TRADING",
                },
            ]
        },
    )

    assert len(events) == 1
    event = events[0]
    assert event.exchange == Exchange.BINANCE
    assert event.market_type == MarketType.PERP
    assert event.event_type == EventType.INSTRUMENT
    assert event.symbol == "BTC-USDT"
    assert event.sequence_id == "BTCUSDT:exchangeInfo"
    assert event.payload["symbol"] == "BTC-USDT"
    assert event.payload["base_asset"] == "BTC"
    assert event.payload["quote_asset"] == "USDT"
    assert event.payload["price_precision"] == 2
    assert event.payload["qty_precision"] == 3
    assert event.payload["contract_size"] == "1"
    assert event.payload["expiry_ts"] is None


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


def test_bybit_open_interest_history_parser_normalizes_events() -> None:
    events = BybitConnector().parse_open_interest_history(
        market_type=MarketType.PERP,
        symbol="BTCUSDT",
        interval="5min",
        rows={
            "retCode": 0,
            "result": {
                "list": [
                    {"openInterest": "12345.67", "timestamp": "1780876800000"},
                    {"timestamp": "1780877100000"},
                ]
            },
        },
    )

    assert len(events) == 1
    event = events[0]
    assert event.exchange == Exchange.BYBIT
    assert event.event_type == EventType.OPEN_INTEREST
    assert event.symbol == "BTC-USDT"
    assert event.payload == {
        "open_interest": "12345.67",
        "open_interest_value_usd": None,
        "unit": "contracts",
        "interval": "5min",
    }


def test_binance_mark_price_kline_parser_uses_close_price() -> None:
    request = HistoricalDataRequest(
        exchange=Exchange.BINANCE,
        market_type=MarketType.PERP,
        symbol="BTCUSDT",
        event_type=EventType.MARK,
        day=date(2024, 1, 1),
        interval="1m",
    )
    raw = _zip_csv(
        "BTCUSDT-1m-2024-01-01.csv",
        "\n".join(
            [
                "1704067200000,42000.1,42100.2,41900.3,42050.4,0,1704067259999,0,0,0,0,0",
                "1704067260000,42050.4,42120.0,42040.0,42100.0,0,1704067319999,0,0,0,0,0",
            ]
        ),
    )

    events = BinanceConnector().parse_mark_price_klines(request, raw)

    assert len(events) == 2
    event = events[0]
    assert event.exchange == Exchange.BINANCE
    assert event.market_type == MarketType.PERP
    assert event.symbol == "BTC-USDT"
    assert event.event_type == EventType.MARK
    assert event.partition_date == "2024-01-01"
    assert event.sequence_id == "BTCUSDT:1704067200000"
    assert event.payload == {
        "mark_price": "42050.4",
        "index_price": None,
    }


def test_binance_index_price_kline_endpoint_uses_day_window_params() -> None:
    endpoint = BinanceConnector().index_price_kline_endpoint(
        market_type=MarketType.PERP,
        symbol="BTC-USDT",
        start_ts=datetime(2024, 1, 1, tzinfo=timezone.utc),
        end_ts=datetime(2024, 1, 2, tzinfo=timezone.utc),
        interval="1m",
        limit=1500,
    )

    assert endpoint.url == "https://fapi.binance.com/fapi/v1/indexPriceKlines"
    assert endpoint.params == {
        "pair": "BTCUSDT",
        "interval": "1m",
        "startTime": "1704067200000",
        "endTime": "1704153600000",
        "limit": "1500",
    }


def test_binance_index_price_kline_parser_uses_close_price() -> None:
    events = BinanceConnector().parse_index_price_klines(
        market_type=MarketType.PERP,
        symbol="BTCUSDT",
        rows=[
            [1704067200000, "42000.1", "42100.2", "41900.3", "42050.4"],
            [1704067260000, "42050.4"],
        ],
    )

    assert len(events) == 1
    event = events[0]
    assert event.exchange == Exchange.BINANCE
    assert event.market_type == MarketType.PERP
    assert event.symbol == "BTC-USDT"
    assert event.event_type == EventType.INDEX
    assert event.partition_date == "2024-01-01"
    assert event.sequence_id == "BTCUSDT:1704067200000"
    assert event.payload == {
        "index_price": "42050.4",
        "interval": "1m",
    }


def test_bybit_mark_price_kline_parser_uses_close_price() -> None:
    events = BybitConnector().parse_mark_price_klines(
        market_type=MarketType.PERP,
        symbol="BTCUSDT",
        rows={"result": {"list": [["1780876800000", "100", "110", "90", "105"]]}},
    )

    assert len(events) == 1
    event = events[0]
    assert event.exchange == Exchange.BYBIT
    assert event.event_type == EventType.MARK
    assert event.symbol == "BTC-USDT"
    assert event.payload == {"mark_price": "105", "index_price": None}


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


def test_bybit_funding_rate_history_parser_normalizes_events() -> None:
    events = BybitConnector().parse_funding_rate_history(
        market_type=MarketType.PERP,
        symbol="BTCUSDT",
        rows={
            "result": {
                "list": [
                    {
                        "symbol": "BTCUSDT",
                        "fundingRate": "0.00010000",
                        "fundingRateTimestamp": "1780876800000",
                    },
                    {"symbol": "BTCUSDT", "fundingRateTimestamp": "1780905600000"},
                ]
            }
        },
    )

    assert len(events) == 1
    event = events[0]
    assert event.exchange == Exchange.BYBIT
    assert event.event_type == EventType.FUNDING
    assert event.symbol == "BTC-USDT"
    assert event.payload == {
        "rate": "0.00010000",
        "next_funding_ts": None,
        "interval_hours": "8",
    }


def _zip_csv(name: str, content: str) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr(name, content)
    return buffer.getvalue()
