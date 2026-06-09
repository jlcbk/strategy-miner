from __future__ import annotations

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
    MarketEvent,
    MarketType,
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
