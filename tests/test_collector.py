from datetime import date
import io
import zipfile

import pytest

from apps.collector import main as collector_main
from packages.normalization import Exchange, MarketType


def test_ingest_open_interest_writes_data_lake_partition(tmp_path, monkeypatch) -> None:
    def fake_download_json(endpoint):
        assert endpoint.params["symbol"] == "BTCUSDT"
        return [
            {
                "symbol": "BTCUSDT",
                "sumOpenInterest": "20403.123",
                "sumOpenInterestValue": "884000000.5",
                "timestamp": 1704067200000,
            }
        ]

    monkeypatch.setattr(collector_main, "download_json", fake_download_json)

    written = collector_main.ingest_open_interest(
        exchange=Exchange.BINANCE,
        market_type=MarketType.PERP,
        symbol="BTCUSDT",
        day=date(2024, 1, 1),
        data_lake_root=tmp_path,
        interval="5m",
        limit=288,
        allow_stale_window=True,
    )

    assert len(written) == 1
    assert written[0].exists()
    assert "exchange=binance" in written[0].parts
    assert "date=2024-01-01" in written[0].parts
    assert "market_type=perp" in written[0].parts
    assert "symbol=BTC-USDT" in written[0].parts
    assert "event_type=open_interest" in written[0].parts


def test_ingest_open_interest_rejects_stale_binance_history_window(tmp_path) -> None:
    with pytest.raises(ValueError, match="最近约 1 个月"):
        collector_main.ingest_open_interest(
            exchange=Exchange.BINANCE,
            market_type=MarketType.PERP,
            symbol="BTCUSDT",
            day=date(2024, 1, 1),
            data_lake_root=tmp_path,
        )


def test_ingest_funding_writes_data_lake_partition(tmp_path, monkeypatch) -> None:
    def fake_download_json(endpoint):
        assert endpoint.params["symbol"] == "BTCUSDT"
        return [
            {
                "symbol": "BTCUSDT",
                "fundingRate": "0.00010000",
                "fundingTime": 1704067200000,
                "markPrice": "42283.58",
            }
        ]

    monkeypatch.setattr(collector_main, "download_json", fake_download_json)

    written = collector_main.ingest_funding(
        exchange=Exchange.BINANCE,
        market_type=MarketType.PERP,
        symbol="BTCUSDT",
        day=date(2024, 1, 1),
        data_lake_root=tmp_path,
    )

    assert len(written) == 1
    assert written[0].exists()
    assert "exchange=binance" in written[0].parts
    assert "date=2024-01-01" in written[0].parts
    assert "market_type=perp" in written[0].parts
    assert "symbol=BTC-USDT" in written[0].parts
    assert "event_type=funding" in written[0].parts


def test_ingest_historical_mark_writes_data_lake_partition(tmp_path, monkeypatch) -> None:
    def fake_download_file(file, target_dir):
        assert file.request.event_type.value == "mark"
        target = tmp_path / "mark.zip"
        target.write_bytes(
            _zip_csv(
                "BTCUSDT-1m-2024-01-01.csv",
                "1704067200000,42000.1,42100.2,41900.3,42050.4,0,1704067259999,0,0,0,0,0",
            )
        )
        return target

    monkeypatch.setattr(collector_main, "download_file", fake_download_file)

    written = collector_main.ingest_historical_mark(
        exchange=Exchange.BINANCE,
        market_type=MarketType.PERP,
        symbol="BTCUSDT",
        day=date(2024, 1, 1),
        download_dir=tmp_path / "downloads",
        data_lake_root=tmp_path,
    )

    assert len(written) == 1
    assert written[0].exists()
    assert "exchange=binance" in written[0].parts
    assert "date=2024-01-01" in written[0].parts
    assert "market_type=perp" in written[0].parts
    assert "symbol=BTC-USDT" in written[0].parts
    assert "event_type=mark" in written[0].parts


def test_ingest_bybit_open_interest_writes_data_lake_partition(tmp_path, monkeypatch) -> None:
    def fake_download_json(endpoint):
        assert endpoint.url == "https://api.bybit.com/v5/market/open-interest"
        return {"result": {"list": [{"openInterest": "12345.67", "timestamp": "1780876800000"}]}}

    monkeypatch.setattr(collector_main, "download_json", fake_download_json)

    written = collector_main.ingest_open_interest(
        exchange=Exchange.BYBIT,
        market_type=MarketType.PERP,
        symbol="BTCUSDT",
        day=date(2026, 6, 8),
        data_lake_root=tmp_path,
    )

    assert len(written) == 1
    assert "exchange=bybit" in written[0].parts
    assert "event_type=open_interest" in written[0].parts


def test_ingest_bybit_funding_writes_data_lake_partition(tmp_path, monkeypatch) -> None:
    def fake_download_json(endpoint):
        assert endpoint.url == "https://api.bybit.com/v5/market/funding/history"
        return {
            "result": {
                "list": [
                    {
                        "symbol": "BTCUSDT",
                        "fundingRate": "0.00010000",
                        "fundingRateTimestamp": "1780876800000",
                    }
                ]
            }
        }

    monkeypatch.setattr(collector_main, "download_json", fake_download_json)

    written = collector_main.ingest_funding(
        exchange=Exchange.BYBIT,
        market_type=MarketType.PERP,
        symbol="BTCUSDT",
        day=date(2026, 6, 8),
        data_lake_root=tmp_path,
    )

    assert len(written) == 1
    assert "exchange=bybit" in written[0].parts
    assert "event_type=funding" in written[0].parts


def test_ingest_bybit_mark_writes_data_lake_partition(tmp_path, monkeypatch) -> None:
    def fake_download_json(endpoint):
        assert endpoint.url == "https://api.bybit.com/v5/market/mark-price-kline"
        return {"result": {"list": [["1780876800000", "100", "110", "90", "105"]]}}

    monkeypatch.setattr(collector_main, "download_json", fake_download_json)

    written = collector_main.ingest_historical_mark(
        exchange=Exchange.BYBIT,
        market_type=MarketType.PERP,
        symbol="BTCUSDT",
        day=date(2026, 6, 8),
        download_dir=tmp_path / "downloads",
        data_lake_root=tmp_path,
    )

    assert len(written) == 1
    assert "exchange=bybit" in written[0].parts
    assert "event_type=mark" in written[0].parts


def test_ingest_binance_orderbook_snapshot_writes_data_lake_partition(
    tmp_path,
    monkeypatch,
) -> None:
    def fake_download_json(endpoint):
        assert endpoint.url == "https://fapi.binance.com/fapi/v1/depth"
        assert endpoint.params == {"symbol": "BTCUSDT", "limit": "20"}
        return {
            "lastUpdateId": 123,
            "T": 1780966800000,
            "bids": [["100", "1"]],
            "asks": [["101", "2"]],
        }

    monkeypatch.setattr(collector_main, "download_json", fake_download_json)

    written = collector_main.ingest_orderbook_snapshot(
        exchange=Exchange.BINANCE,
        market_type=MarketType.PERP,
        symbol="BTCUSDT",
        data_lake_root=tmp_path,
        limit=20,
    )

    assert len(written) == 1
    assert "exchange=binance" in written[0].parts
    assert "date=2026-06-09" in written[0].parts
    assert "market_type=perp" in written[0].parts
    assert "symbol=BTC-USDT" in written[0].parts
    assert "event_type=orderbook" in written[0].parts


def _zip_csv(name: str, content: str) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr(name, content)
    return buffer.getvalue()
