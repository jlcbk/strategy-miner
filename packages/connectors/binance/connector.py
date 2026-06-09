from __future__ import annotations

from datetime import timezone
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


class BinanceConnector:
    exchange = Exchange.BINANCE
    base_url = "https://data.binance.vision"

    def historical_file(self, request: HistoricalDataRequest) -> HistoricalFile:
        symbol = request.symbol.upper().replace("-", "")
        day = request.day.isoformat()
        data_type = _binance_data_type(request.market_type)
        if request.event_type == EventType.TRADE:
            path = f"/data/{data_type}/daily/trades/{symbol}/{symbol}-trades-{day}.zip"
        elif request.event_type == EventType.ORDERBOOK:
            path = f"/data/{data_type}/daily/bookDepth/{symbol}/{symbol}-bookDepth-{day}.zip"
        elif request.event_type == EventType.MARK:
            path = f"/data/{data_type}/daily/markPriceKlines/{symbol}/1m/{symbol}-1m-{day}.zip"
        else:
            raise NotImplementedError(
                f"Binance 归档路径映射暂未支持：{request.event_type.value}"
            )
        return HistoricalFile(request=request, url=f"{self.base_url}{path}", compression="zip")

    def parse_trades(self, request: HistoricalDataRequest, raw: bytes) -> list[MarketEvent]:
        normalized = normalize_symbol(self.exchange, request.symbol, request.market_type)
        events: list[MarketEvent] = []
        for row in csv_rows_from_archive(raw, "zip"):
            trade_id = row.get("trade Id") or row.get("id") or row.get("0")
            price = row.get("price") or row.get("1")
            qty = row.get("qty") or row.get("2")
            ts = row.get("time") or row.get("4")
            if trade_id is None or price is None or qty is None or ts is None:
                continue
            event = MarketEvent(
                exchange=self.exchange,
                market_type=request.market_type,
                symbol=normalized.symbol,
                base_asset=normalized.base_asset,
                quote_asset=normalized.quote_asset,
                event_type=EventType.TRADE,
                exchange_ts=_binance_ts(ts),
                local_ts=utc_now(),
                source="binance_public_data",
                sequence_id=trade_id,
                payload=TradePayload(
                    trade_id=trade_id,
                    price=price,
                    qty=qty,
                    is_buyer_maker=_bool(row.get("isBuyerMaker") or row.get("5")),
                ),
            )
            events.append(event)
        return events

    def websocket_subscription(
        self,
        *,
        market_type: MarketType,
        symbol: str,
        event_types: Iterable[EventType],
        depth: int = 20,
    ) -> WebSocketSubscription:
        symbol_lower = symbol.replace("-", "").lower()
        streams: list[str] = []
        for event_type in event_types:
            if event_type == EventType.TRADE:
                streams.append(f"{symbol_lower}@trade")
            elif event_type == EventType.ORDERBOOK:
                streams.append(f"{symbol_lower}@depth{depth}@100ms")
            elif event_type == EventType.MARK:
                streams.append(f"{symbol_lower}@markPrice@1s")
            elif event_type == EventType.FUNDING:
                streams.append(f"{symbol_lower}@markPrice@1s")
        if market_type == MarketType.SPOT:
            base = "wss://stream.binance.com:9443/stream"
        else:
            base = "wss://fstream.binance.com/stream"
        return WebSocketSubscription(
            url=f"{base}?streams={'/'.join(streams)}",
            stream_names=tuple(streams),
        )

    def open_interest_endpoint(
        self,
        *,
        market_type: MarketType,
        symbol: str,
        interval: str = "5m",
    ) -> RestMarketDataEndpoint:
        if market_type not in {MarketType.PERP, MarketType.FUTURE}:
            raise NotImplementedError("Binance open interest 只适用于衍生品市场")
        clean_symbol = symbol.replace("-", "").upper()
        return RestMarketDataEndpoint(
            url="https://fapi.binance.com/fapi/v1/openInterest",
            params={"symbol": clean_symbol},
            notes="当前 open interest；历史序列后续接 /futures/data/openInterestHist",
        )


def _binance_data_type(market_type: MarketType) -> str:
    if market_type == MarketType.SPOT:
        return "spot"
    if market_type in {MarketType.PERP, MarketType.FUTURE}:
        return "futures/um"
    raise NotImplementedError("Binance 期权归档会在后续里程碑接入")


def _binance_ts(value: str):
    number = int(value)
    if number >= 1_000_000_000_000_000:
        seconds = number / 1_000_000
    else:
        seconds = number / 1000
    from datetime import datetime

    return datetime.fromtimestamp(seconds, tz=timezone.utc)


def _bool(value: str | bool | None) -> bool | None:
    if value is None or isinstance(value, bool):
        return value
    return value.lower() == "true"
