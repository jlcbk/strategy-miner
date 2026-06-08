from __future__ import annotations

from typing import Iterable

from packages.connectors.base import HistoricalDataRequest, HistoricalFile, WebSocketSubscription
from packages.normalization.models import EventType, Exchange, MarketType


class OKXConnector:
    exchange = Exchange.OKX
    historical_data_page = "https://www.okx.com/en-us/historical-data"

    def historical_file(self, request: HistoricalDataRequest) -> HistoricalFile:
        raise NotImplementedError(
            "OKX 历史下载通过官方 historical-data 页面提供；"
            "运行 ingestion 前，需要先从选定下载清单中接入精确文件 URL。"
        )

    def parse_trades(self, request: HistoricalDataRequest, raw: bytes):
        raise NotImplementedError("OKX trade parser 会在确定归档格式后接入")

    def websocket_subscription(
        self,
        *,
        market_type: MarketType,
        symbol: str,
        event_types: Iterable[EventType],
        depth: int = 20,
    ) -> WebSocketSubscription:
        instrument_id = _okx_inst_id(symbol, market_type)
        args: list[dict[str, str]] = []
        for event_type in event_types:
            if event_type == EventType.TRADE:
                args.append({"channel": "trades", "instId": instrument_id})
            elif event_type == EventType.ORDERBOOK:
                args.append({"channel": "books", "instId": instrument_id})
            elif event_type == EventType.FUNDING:
                args.append({"channel": "funding-rate", "instId": instrument_id})
            elif event_type == EventType.MARK:
                args.append({"channel": "mark-price", "instId": instrument_id})
            elif event_type == EventType.INDEX:
                args.append({"channel": "index-tickers", "instId": symbol.upper()})
        return WebSocketSubscription(
            url="wss://ws.okx.com:8443/ws/v5/public",
            payload={"op": "subscribe", "args": args},
            stream_names=tuple(f"{item['channel']}:{item['instId']}" for item in args),
        )


def _okx_inst_id(symbol: str, market_type: MarketType) -> str:
    raw = symbol.upper()
    if "-" in raw:
        return raw
    if raw.endswith("USDT"):
        base = raw[: -len("USDT")]
        quote = "USDT"
    elif raw.endswith("USD"):
        base = raw[: -len("USD")]
        quote = "USD"
    else:
        raise ValueError(f"无法从 symbol 推断 OKX instrument id：{symbol!r}")
    if market_type == MarketType.PERP:
        return f"{base}-{quote}-SWAP"
    return f"{base}-{quote}"
