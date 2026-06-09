from datetime import date

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
