from __future__ import annotations

from dataclasses import asdict, dataclass, field, is_dataclass
from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum
from typing import Any, Mapping


class Exchange(str, Enum):
    BINANCE = "binance"
    OKX = "okx"
    BYBIT = "bybit"
    BITGET = "bitget"


class MarketType(str, Enum):
    SPOT = "spot"
    PERP = "perp"
    FUTURE = "future"
    OPTION = "option"


class EventType(str, Enum):
    TRADE = "trade"
    ORDERBOOK = "orderbook"
    FUNDING = "funding"
    OPEN_INTEREST = "open_interest"
    MARK = "mark"
    INDEX = "index"
    INSTRUMENT = "instrument"
    FEE = "fee"


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def ensure_utc(value: datetime | int | float | str | None) -> datetime:
    if value is None:
        return utc_now()
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)
    if isinstance(value, (int, float)):
        seconds = float(value)
        if seconds > 10_000_000_000:
            seconds /= 1000
        return datetime.fromtimestamp(seconds, tz=timezone.utc)
    if isinstance(value, str):
        text = value.strip()
        if text.isdigit():
            return ensure_utc(int(text))
        if text.endswith("Z"):
            text = f"{text[:-1]}+00:00"
        parsed = datetime.fromisoformat(text)
        return ensure_utc(parsed)
    raise TypeError(f"不支持的时间戳值：{value!r}")


def decimalize(value: Decimal | int | float | str) -> Decimal:
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


@dataclass(frozen=True)
class PriceLevel:
    price: Decimal | int | float | str
    qty: Decimal | int | float | str

    def __post_init__(self) -> None:
        object.__setattr__(self, "price", decimalize(self.price))
        object.__setattr__(self, "qty", decimalize(self.qty))

    @property
    def notional_usd(self) -> Decimal:
        return self.price * self.qty

    def to_dict(self) -> dict[str, str]:
        return {"price": str(self.price), "qty": str(self.qty)}


@dataclass(frozen=True)
class Instrument:
    exchange: Exchange | str
    market_type: MarketType | str
    symbol: str
    base_asset: str
    quote_asset: str
    price_precision: int | None = None
    qty_precision: int | None = None
    contract_size: Decimal | int | float | str | None = None
    expiry_ts: datetime | int | float | str | None = None
    option_type: str | None = None
    strike: Decimal | int | float | str | None = None
    raw: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "exchange", Exchange(self.exchange))
        object.__setattr__(self, "market_type", MarketType(self.market_type))
        object.__setattr__(self, "symbol", self.symbol.upper())
        object.__setattr__(self, "base_asset", self.base_asset.upper())
        object.__setattr__(self, "quote_asset", self.quote_asset.upper())
        if self.contract_size is not None:
            object.__setattr__(self, "contract_size", decimalize(self.contract_size))
        if self.strike is not None:
            object.__setattr__(self, "strike", decimalize(self.strike))
        if self.expiry_ts is not None:
            object.__setattr__(self, "expiry_ts", ensure_utc(self.expiry_ts))

    def to_dict(self) -> dict[str, Any]:
        return _json_safe(asdict(self))


@dataclass(frozen=True)
class TradePayload:
    trade_id: str
    price: Decimal | int | float | str
    qty: Decimal | int | float | str
    side: str | None = None
    is_buyer_maker: bool | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "trade_id", str(self.trade_id))
        object.__setattr__(self, "price", decimalize(self.price))
        object.__setattr__(self, "qty", decimalize(self.qty))
        if self.side is not None:
            object.__setattr__(self, "side", self.side.lower())

    def to_dict(self) -> dict[str, Any]:
        return _json_safe(asdict(self))


@dataclass(frozen=True)
class OrderBookPayload:
    bids: tuple[PriceLevel, ...]
    asks: tuple[PriceLevel, ...]
    update_id: str | int | None = None
    sequence_id: str | int | None = None
    is_snapshot: bool = True

    def __post_init__(self) -> None:
        bids = tuple(
            level if isinstance(level, PriceLevel) else PriceLevel(*level)
            for level in self.bids
        )
        asks = tuple(
            level if isinstance(level, PriceLevel) else PriceLevel(*level)
            for level in self.asks
        )
        if len(bids) > 20 or len(asks) > 20:
            raise ValueError("OrderBookPayload 最多只保存 top 20 档订单簿")
        object.__setattr__(self, "bids", bids)
        object.__setattr__(self, "asks", asks)

    @property
    def best_bid(self) -> PriceLevel | None:
        return max(self.bids, key=lambda level: level.price, default=None)

    @property
    def best_ask(self) -> PriceLevel | None:
        return min(self.asks, key=lambda level: level.price, default=None)

    def to_dict(self) -> dict[str, Any]:
        return {
            "bids": [level.to_dict() for level in self.bids],
            "asks": [level.to_dict() for level in self.asks],
            "update_id": None if self.update_id is None else str(self.update_id),
            "sequence_id": None if self.sequence_id is None else str(self.sequence_id),
            "is_snapshot": self.is_snapshot,
        }


@dataclass(frozen=True)
class FundingPayload:
    rate: Decimal | int | float | str
    next_funding_ts: datetime | int | float | str | None = None
    interval_hours: Decimal | int | float | str = 8

    def __post_init__(self) -> None:
        object.__setattr__(self, "rate", decimalize(self.rate))
        object.__setattr__(self, "interval_hours", decimalize(self.interval_hours))
        if self.next_funding_ts is not None:
            object.__setattr__(self, "next_funding_ts", ensure_utc(self.next_funding_ts))

    def to_dict(self) -> dict[str, Any]:
        return _json_safe(asdict(self))


@dataclass(frozen=True)
class OpenInterestPayload:
    open_interest: Decimal | int | float | str
    open_interest_value_usd: Decimal | int | float | str | None = None
    unit: str = "contracts"
    interval: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "open_interest", decimalize(self.open_interest))
        if self.open_interest_value_usd is not None:
            object.__setattr__(
                self,
                "open_interest_value_usd",
                decimalize(self.open_interest_value_usd),
            )

    def to_dict(self) -> dict[str, Any]:
        return _json_safe(asdict(self))


@dataclass(frozen=True)
class MarkPricePayload:
    mark_price: Decimal | int | float | str
    index_price: Decimal | int | float | str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "mark_price", decimalize(self.mark_price))
        if self.index_price is not None:
            object.__setattr__(self, "index_price", decimalize(self.index_price))

    def to_dict(self) -> dict[str, Any]:
        return _json_safe(asdict(self))


@dataclass(frozen=True)
class FeeSchedule:
    maker_bps: Decimal | int | float | str
    taker_bps: Decimal | int | float | str
    tier: str = "default"

    def __post_init__(self) -> None:
        object.__setattr__(self, "maker_bps", decimalize(self.maker_bps))
        object.__setattr__(self, "taker_bps", decimalize(self.taker_bps))

    def to_dict(self) -> dict[str, Any]:
        return _json_safe(asdict(self))


@dataclass
class MarketEvent:
    exchange: Exchange | str
    market_type: MarketType | str
    symbol: str
    base_asset: str
    quote_asset: str
    event_type: EventType | str
    exchange_ts: datetime | int | float | str
    local_ts: datetime | int | float | str | None
    source: str
    sequence_id: str | int | None
    payload: Mapping[str, Any] | object

    def __post_init__(self) -> None:
        self.exchange = Exchange(self.exchange)
        self.market_type = MarketType(self.market_type)
        self.symbol = self.symbol.upper()
        self.base_asset = self.base_asset.upper()
        self.quote_asset = self.quote_asset.upper()
        self.event_type = EventType(self.event_type)
        self.exchange_ts = ensure_utc(self.exchange_ts)
        self.local_ts = ensure_utc(self.local_ts)
        self.sequence_id = None if self.sequence_id is None else str(self.sequence_id)
        self.payload = _payload_to_dict(self.payload)

    @property
    def partition_date(self) -> str:
        return self.exchange_ts.date().isoformat()

    def to_dict(self) -> dict[str, Any]:
        return {
            "exchange": self.exchange.value,
            "market_type": self.market_type.value,
            "symbol": self.symbol,
            "base_asset": self.base_asset,
            "quote_asset": self.quote_asset,
            "event_type": self.event_type.value,
            "exchange_ts": self.exchange_ts.isoformat(),
            "local_ts": self.local_ts.isoformat(),
            "source": self.source,
            "sequence_id": self.sequence_id,
            "payload": _json_safe(self.payload),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> MarketEvent:
        return cls(
            exchange=data["exchange"],
            market_type=data["market_type"],
            symbol=data["symbol"],
            base_asset=data["base_asset"],
            quote_asset=data["quote_asset"],
            event_type=data["event_type"],
            exchange_ts=data["exchange_ts"],
            local_ts=data.get("local_ts"),
            source=data["source"],
            sequence_id=data.get("sequence_id"),
            payload=data.get("payload", {}),
        )


def _payload_to_dict(payload: Mapping[str, Any] | object) -> dict[str, Any]:
    if hasattr(payload, "to_dict"):
        return payload.to_dict()
    if is_dataclass(payload):
        return _json_safe(asdict(payload))
    if isinstance(payload, Mapping):
        return _json_safe(dict(payload))
    raise TypeError(f"不支持的 payload 类型：{type(payload).__name__}")


def _json_safe(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, Mapping):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    return value
