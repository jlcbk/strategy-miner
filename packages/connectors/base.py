from __future__ import annotations

import csv
import gzip
import io
import zipfile
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Iterable, Protocol
from urllib.request import urlopen

from packages.normalization.models import EventType, Exchange, MarketEvent, MarketType


@dataclass(frozen=True)
class HistoricalDataRequest:
    exchange: Exchange
    market_type: MarketType
    symbol: str
    event_type: EventType
    day: date
    interval: str | None = None


@dataclass(frozen=True)
class HistoricalFile:
    request: HistoricalDataRequest
    url: str
    compression: str


@dataclass(frozen=True)
class WebSocketSubscription:
    url: str
    payload: dict | None = None
    stream_names: tuple[str, ...] = ()


class PublicDataConnector(Protocol):
    exchange: Exchange

    def historical_file(self, request: HistoricalDataRequest) -> HistoricalFile:
        ...

    def parse_trades(self, request: HistoricalDataRequest, raw: bytes) -> list[MarketEvent]:
        ...

    def websocket_subscription(
        self,
        *,
        market_type: MarketType,
        symbol: str,
        event_types: Iterable[EventType],
        depth: int = 20,
    ) -> WebSocketSubscription:
        ...


def download_file(file: HistoricalFile, target_dir: str | Path) -> Path:
    target = Path(target_dir)
    target.mkdir(parents=True, exist_ok=True)
    file_name = file.url.rstrip("/").split("/")[-1]
    output = target / file_name
    with urlopen(file.url, timeout=30) as response:
        output.write_bytes(response.read())
    return output


def csv_rows_from_archive(raw: bytes, compression: str) -> list[dict[str, str]]:
    data = _decompress(raw, compression)
    text = data.decode("utf-8")
    sample = text[:1024]
    has_header = csv.Sniffer().has_header(sample)
    reader = csv.reader(io.StringIO(text))
    rows = list(reader)
    if not rows:
        return []
    if has_header:
        header = [column.strip() for column in rows[0]]
        body = rows[1:]
    else:
        header = [str(index) for index in range(len(rows[0]))]
        body = rows
    return [dict(zip(header, row, strict=False)) for row in body if row]


def _decompress(raw: bytes, compression: str) -> bytes:
    if compression == "zip":
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            name = next(item for item in archive.namelist() if item.endswith(".csv"))
            return archive.read(name)
    if compression == "gzip":
        return gzip.decompress(raw)
    if compression == "none":
        return raw
    raise ValueError(f"不支持的压缩格式：{compression}")
