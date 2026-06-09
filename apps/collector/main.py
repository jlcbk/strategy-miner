from __future__ import annotations

import argparse
import sys
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path

from packages.connectors.base import (
    DownloadError,
    HistoricalDataRequest,
    download_file,
    download_json,
)
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


def ingest_historical_mark(
    *,
    exchange: Exchange,
    market_type: MarketType,
    symbol: str,
    day: date,
    download_dir: Path,
    data_lake_root: Path,
) -> list[Path]:
    connector = CONNECTORS[exchange]
    if exchange == Exchange.BYBIT:
        start_ts, end_ts = _day_window(day)
        endpoint = connector.mark_price_kline_endpoint(
            market_type=market_type,
            symbol=symbol,
            start_ts=start_ts,
            end_ts=end_ts,
            interval="5",
            limit=1000,
        )
        rows = download_json(endpoint)
        events = connector.parse_mark_price_klines(
            market_type=market_type,
            symbol=symbol,
            rows=rows,
            interval="5",
        )
        return DataLakeWriter(data_lake_root).write_events(events)
    if exchange != Exchange.BINANCE:
        raise NotImplementedError("historical-mark collector 当前支持 Binance 和 Bybit")
    request = HistoricalDataRequest(
        exchange=exchange,
        market_type=market_type,
        symbol=symbol,
        event_type=EventType.MARK,
        day=day,
        interval="1m",
    )
    archive = download_file(connector.historical_file(request), download_dir)
    events = connector.parse_mark_price_klines(request, archive.read_bytes())
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
    connector = CONNECTORS[exchange]
    if exchange == Exchange.BINANCE and not allow_stale_window:
        latest_supported_start = datetime.now(timezone.utc).date() - timedelta(days=31)
        if day < latest_supported_start:
            raise ValueError(
                "Binance open-interest history REST 仅支持最近约 1 个月数据；"
                "更早窗口需要外部归档源或调整验证日期"
            )
    start_ts, end_ts = _day_window(day)
    if exchange == Exchange.BINANCE:
        endpoint = connector.open_interest_history_endpoint(
            market_type=market_type,
            symbol=symbol,
            start_ts=start_ts,
            end_ts=end_ts,
            interval=interval,
            limit=limit,
        )
    elif exchange == Exchange.BYBIT:
        endpoint = connector.open_interest_history_endpoint(
            market_type=market_type,
            symbol=symbol,
            start_ts=start_ts,
            end_ts=end_ts,
            interval="5min",
            limit=min(limit, 200),
        )
    else:
        raise NotImplementedError("open-interest collector 当前支持 Binance 和 Bybit")
    rows = download_json(endpoint)
    events = connector.parse_open_interest_history(
        market_type=market_type,
        symbol=symbol,
        interval=interval,
        rows=rows,
    )
    return DataLakeWriter(data_lake_root).write_events(events)


def ingest_funding(
    *,
    exchange: Exchange,
    market_type: MarketType,
    symbol: str,
    day: date,
    data_lake_root: Path,
    limit: int = 1000,
) -> list[Path]:
    connector = CONNECTORS[exchange]
    start_ts, end_ts = _day_window(day)
    endpoint = connector.funding_rate_history_endpoint(
        market_type=market_type,
        symbol=symbol,
        start_ts=start_ts,
        end_ts=end_ts,
        limit=limit if exchange == Exchange.BINANCE else min(limit, 200),
    )
    rows = download_json(endpoint)
    events = connector.parse_funding_rate_history(
        market_type=market_type,
        symbol=symbol,
        rows=rows,
    )
    return DataLakeWriter(data_lake_root).write_events(events)


def ingest_orderbook_snapshot(
    *,
    exchange: Exchange,
    market_type: MarketType,
    symbol: str,
    data_lake_root: Path,
    limit: int = 20,
) -> list[Path]:
    if exchange != Exchange.BINANCE:
        raise NotImplementedError("orderbook-snapshot collector 当前仅支持 Binance")
    connector = CONNECTORS[exchange]
    observed_at = datetime.now(timezone.utc)
    endpoint = connector.orderbook_snapshot_endpoint(
        market_type=market_type,
        symbol=symbol,
        limit=limit,
    )
    row = download_json(endpoint)
    events = connector.parse_orderbook_snapshot(
        market_type=market_type,
        symbol=symbol,
        row=row,
        observed_at=observed_at,
        limit=limit,
    )
    return DataLakeWriter(data_lake_root).write_events(events)


def ingest_instrument_snapshot(
    *,
    exchange: Exchange,
    market_type: MarketType,
    symbol: str,
    data_lake_root: Path,
) -> list[Path]:
    if exchange != Exchange.BINANCE:
        raise NotImplementedError("instrument-snapshot collector 当前仅支持 Binance")
    connector = CONNECTORS[exchange]
    observed_at = datetime.now(timezone.utc)
    endpoint = connector.instrument_snapshot_endpoint(market_type=market_type)
    row = download_json(endpoint)
    events = connector.parse_instrument_snapshot(
        market_type=market_type,
        symbol=symbol,
        row=row,
        observed_at=observed_at,
    )
    return DataLakeWriter(data_lake_root).write_events(events)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Strategy Miner collector 工具")
    parser.add_argument(
        "command",
        choices=[
            "historical-trades",
            "historical-mark",
            "open-interest",
            "funding",
            "orderbook-snapshot",
            "instrument-snapshot",
            "show-ws",
        ],
    )
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

    if args.command == "funding":
        written = ingest_funding(
            exchange=exchange,
            market_type=market_type,
            symbol=args.symbol,
            day=date.fromisoformat(args.day),
            data_lake_root=Path(args.data_lake_root),
            limit=args.limit,
        )
        for path in written:
            print(path)
        return 0

    if args.command == "orderbook-snapshot":
        depth_limit = 20 if args.limit == 500 else args.limit
        written = ingest_orderbook_snapshot(
            exchange=exchange,
            market_type=market_type,
            symbol=args.symbol,
            data_lake_root=Path(args.data_lake_root),
            limit=depth_limit,
        )
        for path in written:
            print(path)
        return 0

    if args.command == "instrument-snapshot":
        written = ingest_instrument_snapshot(
            exchange=exchange,
            market_type=market_type,
            symbol=args.symbol,
            data_lake_root=Path(args.data_lake_root),
        )
        for path in written:
            print(path)
        return 0

    if args.command == "historical-mark":
        written = ingest_historical_mark(
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


def _day_window(day: date) -> tuple[datetime, datetime]:
    return (
        datetime.combine(day, time.min, tzinfo=timezone.utc),
        datetime.combine(day, time.max, tzinfo=timezone.utc),
    )


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except DownloadError as exc:
        print(f"下载失败：{exc}", file=sys.stderr)
        raise SystemExit(2) from exc
