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
    Instrument,
    MarkPricePayload,
    MarketEvent,
    MarketType,
    OpenInterestPayload,
    OrderBookPayload,
    PriceLevel,
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

    def parse_mark_price_klines(
        self,
        request: HistoricalDataRequest,
        raw: bytes,
    ) -> list[MarketEvent]:
        if request.event_type != EventType.MARK:
            raise ValueError("parse_mark_price_klines 只接受 MARK 请求")
        normalized = normalize_symbol(self.exchange, request.symbol, request.market_type)
        events: list[MarketEvent] = []
        for row in csv_rows_from_archive(raw, "zip"):
            open_time = row.get("open_time") or row.get("open time") or row.get("0")
            close = row.get("close") or row.get("4")
            if open_time is None or close is None:
                continue
            events.append(
                MarketEvent(
                    exchange=self.exchange,
                    market_type=request.market_type,
                    symbol=normalized.symbol,
                    base_asset=normalized.base_asset,
                    quote_asset=normalized.quote_asset,
                    event_type=EventType.MARK,
                    exchange_ts=_binance_ts(open_time),
                    local_ts=utc_now(),
                    source="binance_public_mark_price_klines",
                    sequence_id=f"{request.symbol.upper()}:{open_time}",
                    payload=MarkPricePayload(mark_price=close),
                )
            )
        return events

    def index_price_kline_endpoint(
        self,
        *,
        market_type: MarketType,
        symbol: str,
        start_ts,
        end_ts,
        interval: str = "1m",
        limit: int = 1500,
    ) -> RestMarketDataEndpoint:
        if market_type not in {MarketType.PERP, MarketType.FUTURE}:
            raise NotImplementedError("Binance index price kline 只适用于衍生品市场")
        pair = symbol.replace("-", "").upper()
        return RestMarketDataEndpoint(
            url="https://fapi.binance.com/fapi/v1/indexPriceKlines",
            params={
                "pair": pair,
                "interval": interval,
                "startTime": str(_to_millis(start_ts)),
                "endTime": str(_to_millis(end_ts)),
                "limit": str(limit),
            },
            notes="USD-M futures index price klines",
        )

    def parse_index_price_klines(
        self,
        *,
        market_type: MarketType,
        symbol: str,
        rows: list[list],
        interval: str = "1m",
    ) -> list[MarketEvent]:
        normalized = normalize_symbol(self.exchange, symbol, market_type)
        events: list[MarketEvent] = []
        for row in rows:
            if len(row) < 5:
                continue
            open_time = row[0]
            close = row[4]
            events.append(
                MarketEvent(
                    exchange=self.exchange,
                    market_type=market_type,
                    symbol=normalized.symbol,
                    base_asset=normalized.base_asset,
                    quote_asset=normalized.quote_asset,
                    event_type=EventType.INDEX,
                    exchange_ts=open_time,
                    local_ts=utc_now(),
                    source="binance_index_price_klines",
                    sequence_id=f"{symbol.upper()}:{open_time}",
                    payload={
                        "index_price": str(close),
                        "interval": interval,
                    },
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

    def open_interest_history_endpoint(
        self,
        *,
        market_type: MarketType,
        symbol: str,
        start_ts,
        end_ts,
        interval: str = "5m",
        limit: int = 500,
    ) -> RestMarketDataEndpoint:
        if market_type not in {MarketType.PERP, MarketType.FUTURE}:
            raise NotImplementedError("Binance open interest 历史序列只适用于衍生品市场")
        clean_symbol = symbol.replace("-", "").upper()
        return RestMarketDataEndpoint(
            url="https://fapi.binance.com/futures/data/openInterestHist",
            params={
                "symbol": clean_symbol,
                "period": interval,
                "startTime": str(_to_millis(start_ts)),
                "endTime": str(_to_millis(end_ts)),
                "limit": str(limit),
            },
            notes="USD-M futures open interest statistics history；官方 REST 仅保留最近约 1 个月",
        )

    def parse_open_interest_history(
        self,
        *,
        market_type: MarketType,
        symbol: str,
        rows: list[dict],
        interval: str = "5m",
    ) -> list[MarketEvent]:
        normalized = normalize_symbol(self.exchange, symbol, market_type)
        events: list[MarketEvent] = []
        for row in rows:
            timestamp = row.get("timestamp")
            open_interest = row.get("sumOpenInterest")
            if timestamp is None or open_interest is None:
                continue
            open_interest_value = row.get("sumOpenInterestValue")
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
                    source="binance_open_interest_hist",
                    sequence_id=f"{symbol.upper()}:{timestamp}",
                    payload=OpenInterestPayload(
                        open_interest=open_interest,
                        open_interest_value_usd=open_interest_value,
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
        limit: int = 1000,
    ) -> RestMarketDataEndpoint:
        if market_type not in {MarketType.PERP, MarketType.FUTURE}:
            raise NotImplementedError("Binance funding rate 历史序列只适用于衍生品市场")
        clean_symbol = symbol.replace("-", "").upper()
        return RestMarketDataEndpoint(
            url="https://fapi.binance.com/fapi/v1/fundingRate",
            params={
                "symbol": clean_symbol,
                "startTime": str(_to_millis(start_ts)),
                "endTime": str(_to_millis(end_ts)),
                "limit": str(limit),
            },
            notes="USD-M futures funding rate history",
        )

    def orderbook_snapshot_endpoint(
        self,
        *,
        market_type: MarketType,
        symbol: str,
        limit: int = 20,
    ) -> RestMarketDataEndpoint:
        if limit > 20:
            raise ValueError("Strategy Miner MVP 只采 top20 orderbook snapshot")
        clean_symbol = symbol.replace("-", "").upper()
        if market_type == MarketType.SPOT:
            return RestMarketDataEndpoint(
                url="https://api.binance.com/api/v3/depth",
                params={"symbol": clean_symbol, "limit": str(limit)},
                notes="Spot order book snapshot；MVP 只保存 top20",
            )
        if market_type in {MarketType.PERP, MarketType.FUTURE}:
            return RestMarketDataEndpoint(
                url="https://fapi.binance.com/fapi/v1/depth",
                params={"symbol": clean_symbol, "limit": str(limit)},
                notes="USD-M futures order book snapshot；MVP 只保存 top20",
            )
        raise NotImplementedError("Binance orderbook snapshot 当前支持 spot/perp/future")

    def instrument_snapshot_endpoint(
        self,
        *,
        market_type: MarketType,
    ) -> RestMarketDataEndpoint:
        if market_type == MarketType.SPOT:
            return RestMarketDataEndpoint(
                url="https://api.binance.com/api/v3/exchangeInfo",
                params={},
                notes="Spot exchange information snapshot",
            )
        if market_type in {MarketType.PERP, MarketType.FUTURE}:
            return RestMarketDataEndpoint(
                url="https://fapi.binance.com/fapi/v1/exchangeInfo",
                params={},
                notes="USD-M futures exchange information snapshot",
            )
        raise NotImplementedError("Binance instrument snapshot 当前支持 spot/perp/future")

    def parse_instrument_snapshot(
        self,
        *,
        market_type: MarketType,
        symbol: str,
        row: dict,
        observed_at=None,
    ) -> list[MarketEvent]:
        observed = utc_now() if observed_at is None else observed_at
        clean_symbol = symbol.replace("-", "").upper()
        events: list[MarketEvent] = []
        for raw_symbol in row.get("symbols", []):
            if raw_symbol.get("symbol") != clean_symbol:
                continue
            normalized = normalize_symbol(
                self.exchange,
                raw_symbol["symbol"],
                market_type,
            )
            instrument = _instrument_from_exchange_info(
                raw_symbol,
                market_type=market_type,
                normalized_symbol=normalized.symbol,
            )
            events.append(
                MarketEvent(
                    exchange=self.exchange,
                    market_type=market_type,
                    symbol=normalized.symbol,
                    base_asset=normalized.base_asset,
                    quote_asset=normalized.quote_asset,
                    event_type=EventType.INSTRUMENT,
                    exchange_ts=observed,
                    local_ts=observed,
                    source="binance_exchange_info",
                    sequence_id=f"{raw_symbol['symbol']}:exchangeInfo",
                    payload=instrument,
                )
            )
        return events

    def parse_orderbook_snapshot(
        self,
        *,
        market_type: MarketType,
        symbol: str,
        row: dict,
        observed_at=None,
        limit: int = 20,
    ) -> list[MarketEvent]:
        normalized = normalize_symbol(self.exchange, symbol, market_type)
        observed = utc_now() if observed_at is None else observed_at
        exchange_ts = row.get("T") or row.get("E") or observed
        update_id = row.get("lastUpdateId")
        bids = _price_levels(row.get("bids", []), limit)
        asks = _price_levels(row.get("asks", []), limit)
        if not bids or not asks:
            return []
        sequence_id = (
            f"{symbol.upper()}:{update_id}" if update_id is not None else symbol.upper()
        )
        return [
            MarketEvent(
                exchange=self.exchange,
                market_type=market_type,
                symbol=normalized.symbol,
                base_asset=normalized.base_asset,
                quote_asset=normalized.quote_asset,
                event_type=EventType.ORDERBOOK,
                exchange_ts=exchange_ts,
                local_ts=observed,
                source="binance_orderbook_snapshot",
                sequence_id=sequence_id,
                payload=OrderBookPayload(
                    bids=tuple(bids),
                    asks=tuple(asks),
                    update_id=update_id,
                    is_snapshot=True,
                ),
            )
        ]

    def parse_funding_rate_history(
        self,
        *,
        market_type: MarketType,
        symbol: str,
        rows: list[dict],
        interval_hours: str = "8",
    ) -> list[MarketEvent]:
        normalized = normalize_symbol(self.exchange, symbol, market_type)
        events: list[MarketEvent] = []
        for row in rows:
            timestamp = row.get("fundingTime")
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
                    source="binance_funding_rate_history",
                    sequence_id=f"{symbol.upper()}:{timestamp}",
                    payload=FundingPayload(
                        rate=rate,
                        interval_hours=interval_hours,
                    ),
                )
            )
        return events


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


def _price_levels(rows, limit: int) -> list[PriceLevel]:
    levels: list[PriceLevel] = []
    for raw in rows[:limit]:
        if len(raw) < 2:
            continue
        levels.append(PriceLevel(raw[0], raw[1]))
    return levels


def _instrument_from_exchange_info(
    row: dict,
    *,
    market_type: MarketType,
    normalized_symbol: str,
) -> Instrument:
    price_precision = row.get("pricePrecision") or row.get("quotePrecision")
    qty_precision = row.get("quantityPrecision") or row.get("baseAssetPrecision")
    contract_size = "1" if market_type in {MarketType.PERP, MarketType.FUTURE} else None
    expiry_ts = row.get("deliveryDate")
    if expiry_ts in {None, 0, "0", 4133404800000}:
        expiry_ts = None
    return Instrument(
        exchange=Exchange.BINANCE,
        market_type=market_type,
        symbol=normalized_symbol,
        base_asset=row["baseAsset"],
        quote_asset=row["quoteAsset"],
        price_precision=None if price_precision is None else int(price_precision),
        qty_precision=None if qty_precision is None else int(qty_precision),
        contract_size=contract_size,
        expiry_ts=expiry_ts,
        raw=row,
    )


def _bool(value: str | bool | None) -> bool | None:
    if value is None or isinstance(value, bool):
        return value
    return value.lower() == "true"
