from __future__ import annotations

import argparse
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path

from packages.connectors.base import HistoricalDataRequest, download_file, download_json
from packages.connectors.binance import BinanceConnector
from packages.connectors.bybit import BybitConnector
from packages.data_lake.store import DataLakeWriter
from packages.normalization.models import EventType, Exchange, MarketType


CONNECTORS = {
    Exchange.BINANCE: BinanceConnector(),
    Exchange.BYBIT: BybitConnector(),
}


def ingest_historical_trades(
    *,
    exchange: Exchange,
    market_type: MarketType,
    symbol: str,
    day: date,
    download_dir: Path,
    data_lake_root: Path,
) -> list[Path]:
    connector = CONNECTORS[exchange]
    request = HistoricalDataRequest(
        exchange=exchange,
        market_type=market_type,
        symbol=symbol,
        event_type=EventType.TRADE,
        day=day,
    )
    archive = download_file(connector.historical_file(request), download_dir)
    events = connector.parse_trades(request, archive.read_bytes())
    return DataLakeWriter(data_lake_root).write_events(events)


def ingest_open_interest(
    *,
    exchange: Exchange,
    market_type: MarketType,
    symbol: str,
    day: date,
    data_lake_root: Path,
    interval: str = "5m",
    limit: int = 500,
    allow_stale_window: bool = False,
) -> list[Path]:
    if exchange != Exchange.BINANCE:
        raise NotImplementedError("open-interest collector 当前先支持 Binance")
    if not allow_stale_window:
        latest_supported_start = datetime.now(timezone.utc).date() - timedelta(days=31)
        if day < latest_supported_start:
            raise ValueError(
                "Binance open-interest history REST 仅支持最近约 1 个月数据；"
                "更早窗口需要外部归档源或调整验证日期"
            )
    connector = BinanceConnector()
    start_ts = datetime.combine(day, time.min, tzinfo=timezone.utc)
    end_ts = datetime.combine(day, time.max, tzinfo=timezone.utc)
    endpoint = connector.open_interest_history_endpoint(
        market_type=market_type,
        symbol=symbol,
        start_ts=start_ts,
        end_ts=end_ts,
        interval=interval,
        limit=limit,
    )
    rows = download_json(endpoint)
    events = connector.parse_open_interest_history(
        market_type=market_type,
        symbol=symbol,
        rows=rows,
        interval=interval,
    )
    return DataLakeWriter(data_lake_root).write_events(events)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Strategy Miner collector 工具")
    parser.add_argument("command", choices=["historical-trades", "open-interest", "show-ws"])
    parser.add_argument("--exchange", choices=["binance", "bybit"], default="binance")
    parser.add_argument("--market-type", choices=["spot", "perp", "future"], default="spot")
    parser.add_argument("--symbol", default="BTCUSDT")
    parser.add_argument("--day", default=date.today().isoformat())
    parser.add_argument("--download-dir", default="var/downloads")
    parser.add_argument("--data-lake-root", default="var/market-data")
    parser.add_argument("--interval", default="5m")
    parser.add_argument("--limit", type=int, default=500)
    args = parser.parse_args(argv)

    exchange = Exchange(args.exchange)
    market_type = MarketType(args.market_type)
    connector = CONNECTORS[exchange]

    if args.command == "show-ws":
        subscription = connector.websocket_subscription(
            market_type=market_type,
            symbol=args.symbol,
            event_types=[EventType.TRADE, EventType.ORDERBOOK, EventType.MARK],
        )
        print(subscription)
        return 0

    if args.command == "open-interest":
        written = ingest_open_interest(
            exchange=exchange,
            market_type=market_type,
            symbol=args.symbol,
            day=date.fromisoformat(args.day),
            data_lake_root=Path(args.data_lake_root),
            interval=args.interval,
            limit=args.limit,
        )
        for path in written:
            print(path)
        return 0

    written = ingest_historical_trades(
        exchange=exchange,
        market_type=market_type,
        symbol=args.symbol,
        day=date.fromisoformat(args.day),
        download_dir=Path(args.download_dir),
        data_lake_root=Path(args.data_lake_root),
    )
    for path in written:
        print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
