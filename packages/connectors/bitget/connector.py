from __future__ import annotations

from typing import Iterable

from packages.connectors.base import (
    HistoricalDataRequest,
    HistoricalFile,
    RestMarketDataEndpoint,
    WebSocketSubscription,
)
from packages.normalization.models import EventType, Exchange, MarketType


class BitgetConnector:
    exchange = Exchange.BITGET
    historical_data_page = "https://www.bitget.com/data-download"

    def historical_file(self, request: HistoricalDataRequest) -> HistoricalFile:
        raise NotImplementedError(
            "Bitget 下载链接需要从官方 data-download 页面选择；"
            "请先为选定的数据集接入精确文件 URL。"
        )

    def parse_trades(self, request: HistoricalDataRequest, raw: bytes):
        raise NotImplementedError("Bitget trade parser 会在确定归档格式后接入")

    def websocket_subscription(
        self,
        *,
        market_type: MarketType,
        symbol: str,
        event_types: Iterable[EventType],
        depth: int = 20,
    ) -> WebSocketSubscription:
        inst_type = {
            MarketType.SPOT: "SPOT",
            MarketType.PERP: "USDT-FUTURES",
            MarketType.FUTURE: "USDT-FUTURES",
            MarketType.OPTION: "USDT-FUTURES",
        }[market_type]
        inst_id = symbol.upper().replace("-", "")
        args: list[dict[str, str]] = []
        for event_type in event_types:
            if event_type == EventType.TRADE:
                args.append({"instType": inst_type, "channel": "trade", "instId": inst_id})
            elif event_type == EventType.ORDERBOOK:
                args.append({"instType": inst_type, "channel": f"books{depth}", "instId": inst_id})
            elif event_type in {EventType.FUNDING, EventType.MARK, EventType.INDEX}:
                args.append({"instType": inst_type, "channel": "ticker", "instId": inst_id})
        return WebSocketSubscription(
            url="wss://ws.bitget.com/v2/ws/public",
            payload={"op": "subscribe", "args": args},
            stream_names=tuple(f"{item['channel']}:{item['instId']}" for item in args),
        )

    def open_interest_endpoint(
        self,
        *,
        market_type: MarketType,
        symbol: str,
        interval: str = "5m",
    ) -> RestMarketDataEndpoint:
        if market_type not in {MarketType.PERP, MarketType.FUTURE}:
            raise NotImplementedError("Bitget open interest 只适用于衍生品市场")
        product_type = "USDT-FUTURES"
        inst_id = symbol.upper().replace("-", "")
        return RestMarketDataEndpoint(
            url="https://api.bitget.com/api/v2/mix/market/open-interest",
            params={"symbol": inst_id, "productType": product_type},
            notes="Bitget contract market open-interest REST",
        )
