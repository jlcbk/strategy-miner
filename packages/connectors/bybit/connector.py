from __future__ import annotations

from datetime import datetime, timezone
from typing import Iterable

from packages.connectors.base import (
    HistoricalDataRequest,
    HistoricalFile,
    RestMarketDataEndpoint,
    WebSocketSubscription,
    csv_rows_from_archive,
)
from packages.normalization.models import (
    EventType,
    Exchange,
    FundingPayload,
    MarkPricePayload,
    MarketEvent,
    MarketType,
    OpenInterestPayload,
    TradePayload,
    utc_now,
)
from packages.normalization.symbols import normalize_symbol


class BybitConnector:
    exchange = Exchange.BYBIT
    base_url = "https://public.bybit.com"

    def historical_file(self, request: HistoricalDataRequest) -> HistoricalFile:
        symbol = request.symbol.upper().replace("-", "")
        if request.event_type != EventType.TRADE:
            raise NotImplementedError("Bybit 公开归档适配器当前只映射 trade 文件")
        day = request.day.isoformat()
        return HistoricalFile(
            request=request,
            url=f"{self.base_url}/trading/{symbol}/{symbol}{day}.csv.gz",
            compression="gzip",
        )

    def parse_trades(self, request: HistoricalDataRequest, raw: bytes) -> list[MarketEvent]:
        normalized = normalize_symbol(self.exchange, request.symbol, request.market_type)
        events: list[MarketEvent] = []
        for row in csv_rows_from_archive(raw, "gzip"):
            ts = row.get("timestamp") or row.get("0")
            side = row.get("side") or row.get("1")
            size = row.get("size") or row.get("2")
            price = row.get("price") or row.get("3")
            trade_id = row.get("trade_id") or row.get("tickDirection") or f"{ts}:{price}:{size}"
            if ts is None or size is None or price is None:
                continue
            events.append(
                MarketEvent(
                    exchange=self.exchange,
                    market_type=request.market_type,
                    symbol=normalized.symbol,
                    base_asset=normalized.base_asset,
                    quote_asset=normalized.quote_asset,
                    event_type=EventType.TRADE,
                    exchange_ts=float(ts),
                    local_ts=utc_now(),
                    source="bybit_public_trading",
                    sequence_id=trade_id,
                    payload=TradePayload(trade_id=trade_id, price=price, qty=size, side=side),
                )
            )
        return events

    def websocket_subscription(
        self,
        *,
        market_type: MarketType,
        symbol: str,
        event_types: Iterable[EventType],
        depth: int = 20,
    ) -> WebSocketSubscription:
        category = {
            MarketType.SPOT: "spot",
            MarketType.PERP: "linear",
            MarketType.FUTURE: "linear",
            MarketType.OPTION: "option",
        }[market_type]
        topics: list[str] = []
        clean_symbol = symbol.replace("-", "").upper()
        for event_type in event_types:
            if event_type == EventType.TRADE:
                topics.append(f"publicTrade.{clean_symbol}")
            elif event_type == EventType.ORDERBOOK:
                topics.append(f"orderbook.{depth}.{clean_symbol}")
            elif event_type in {EventType.FUNDING, EventType.MARK, EventType.INDEX}:
                topics.append(f"tickers.{clean_symbol}")
        return WebSocketSubscription(
            url=f"wss://stream.bybit.com/v5/public/{category}",
            payload={"op": "subscribe", "args": topics},
            stream_names=tuple(topics),
        )

    def open_interest_endpoint(
        self,
        *,
        market_type: MarketType,
        symbol: str,
        interval: str = "5min",
    ) -> RestMarketDataEndpoint:
        if market_type not in {MarketType.PERP, MarketType.FUTURE}:
            raise NotImplementedError("Bybit open interest 只适用于衍生品市场")
        category = "linear" if market_type in {MarketType.PERP, MarketType.FUTURE} else "spot"
        clean_symbol = symbol.replace("-", "").upper()
        return RestMarketDataEndpoint(
            url="https://api.bybit.com/v5/market/open-interest",
            params={"category": category, "symbol": clean_symbol, "intervalTime": interval},
            notes="V5 market open-interest REST；ticker websocket 可作为实时补充源",
        )

    def open_interest_history_endpoint(
        self,
        *,
        market_type: MarketType,
        symbol: str,
        start_ts,
        end_ts,
        interval: str = "5min",
        limit: int = 200,
    ) -> RestMarketDataEndpoint:
        if market_type not in {MarketType.PERP, MarketType.FUTURE}:
            raise NotImplementedError("Bybit open interest 历史序列只适用于衍生品市场")
        category = _bybit_category(market_type)
        clean_symbol = symbol.replace("-", "").upper()
        return RestMarketDataEndpoint(
            url="https://api.bybit.com/v5/market/open-interest",
            params={
                "category": category,
                "symbol": clean_symbol,
                "intervalTime": interval,
                "startTime": str(_to_millis(start_ts)),
                "endTime": str(_to_millis(end_ts)),
                "limit": str(limit),
            },
            notes="Bybit V5 market open-interest history",
        )

    def parse_open_interest_history(
        self,
        *,
        market_type: MarketType,
        symbol: str,
        rows,
        interval: str = "5min",
    ) -> list[MarketEvent]:
        normalized = normalize_symbol(self.exchange, symbol, market_type)
        events: list[MarketEvent] = []
        for row in _bybit_list(rows):
            timestamp = row.get("timestamp")
            open_interest = row.get("openInterest")
            if timestamp is None or open_interest is None:
                continue
            events.append(
                MarketEvent(
                    exchange=self.exchange,
                    market_type=market_type,
                    symbol=normalized.symbol,
                    base_asset=normalized.base_asset,
                    quote_asset=normalized.quote_asset,
                    event_type=EventType.OPEN_INTEREST,
                    exchange_ts=timestamp,
                    local_ts=utc_now(),
                    source="bybit_open_interest_history",
                    sequence_id=f"{symbol.upper()}:{timestamp}",
                    payload=OpenInterestPayload(
                        open_interest=open_interest,
                        unit="contracts",
                        interval=interval,
                    ),
                )
            )
        return events

    def funding_rate_history_endpoint(
        self,
        *,
        market_type: MarketType,
        symbol: str,
        start_ts,
        end_ts,
        limit: int = 200,
    ) -> RestMarketDataEndpoint:
        if market_type not in {MarketType.PERP, MarketType.FUTURE}:
            raise NotImplementedError("Bybit funding rate 历史序列只适用于衍生品市场")
        category = _bybit_category(market_type)
        clean_symbol = symbol.replace("-", "").upper()
        return RestMarketDataEndpoint(
            url="https://api.bybit.com/v5/market/funding/history",
            params={
                "category": category,
                "symbol": clean_symbol,
                "startTime": str(_to_millis(start_ts)),
                "endTime": str(_to_millis(end_ts)),
                "limit": str(limit),
            },
            notes="Bybit V5 market funding history",
        )

    def parse_funding_rate_history(
        self,
        *,
        market_type: MarketType,
        symbol: str,
        rows,
        interval_hours: str = "8",
    ) -> list[MarketEvent]:
        normalized = normalize_symbol(self.exchange, symbol, market_type)
        events: list[MarketEvent] = []
        for row in _bybit_list(rows):
            timestamp = row.get("fundingRateTimestamp")
            rate = row.get("fundingRate")
            if timestamp is None or rate is None:
                continue
            events.append(
                MarketEvent(
                    exchange=self.exchange,
                    market_type=market_type,
                    symbol=normalized.symbol,
                    base_asset=normalized.base_asset,
                    quote_asset=normalized.quote_asset,
                    event_type=EventType.FUNDING,
                    exchange_ts=timestamp,
                    local_ts=utc_now(),
                    source="bybit_funding_rate_history",
                    sequence_id=f"{symbol.upper()}:{timestamp}",
                    payload=FundingPayload(
                        rate=rate,
                        interval_hours=interval_hours,
                    ),
                )
            )
        return events

    def mark_price_kline_endpoint(
        self,
        *,
        market_type: MarketType,
        symbol: str,
        start_ts,
        end_ts,
        interval: str = "5",
        limit: int = 1000,
    ) -> RestMarketDataEndpoint:
        if market_type not in {MarketType.PERP, MarketType.FUTURE}:
            raise NotImplementedError("Bybit mark price kline 只适用于衍生品市场")
        category = _bybit_category(market_type)
        clean_symbol = symbol.replace("-", "").upper()
        return RestMarketDataEndpoint(
            url="https://api.bybit.com/v5/market/mark-price-kline",
            params={
                "category": category,
                "symbol": clean_symbol,
                "interval": _bybit_interval(interval),
                "start": str(_to_millis(start_ts)),
                "end": str(_to_millis(end_ts)),
                "limit": str(limit),
            },
            notes="Bybit V5 market mark price kline",
        )

    def parse_mark_price_klines(
        self,
        *,
        market_type: MarketType,
        symbol: str,
        rows,
        interval: str = "5",
    ) -> list[MarketEvent]:
        normalized = normalize_symbol(self.exchange, symbol, market_type)
        events: list[MarketEvent] = []
        for row in _bybit_list(rows):
            if not isinstance(row, list) or len(row) < 5:
                continue
            timestamp = row[0]
            close = row[4]
            events.append(
                MarketEvent(
                    exchange=self.exchange,
                    market_type=market_type,
                    symbol=normalized.symbol,
                    base_asset=normalized.base_asset,
                    quote_asset=normalized.quote_asset,
                    event_type=EventType.MARK,
                    exchange_ts=timestamp,
                    local_ts=utc_now(),
                    source="bybit_mark_price_kline",
                    sequence_id=f"{symbol.upper()}:{timestamp}",
                    payload=MarkPricePayload(mark_price=close),
                )
            )
        return events


def _bybit_category(market_type: MarketType) -> str:
    return "linear" if market_type in {MarketType.PERP, MarketType.FUTURE} else "spot"


def _bybit_list(payload):
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        result = payload.get("result") or {}
        data = result.get("list")
        if isinstance(data, list):
            return data
    return []


def _bybit_interval(interval: str) -> str:
    return interval[:-1] if interval.endswith("m") else interval


def _to_millis(value) -> int:
    if isinstance(value, datetime):
        parsed = value if value.tzinfo else value.replace(tzinfo=timezone.utc)
        return int(parsed.timestamp() * 1000)
    if isinstance(value, (int, float)):
        number = int(value)
        if number < 10_000_000_000:
            return number * 1000
        return number
    if isinstance(value, str):
        return _to_millis(datetime.fromisoformat(value.replace("Z", "+00:00")))
    raise TypeError(f"不支持的时间戳值：{value!r}")
