from __future__ import annotations

import csv
import gzip
import io
import json
import zipfile
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Iterable, Protocol
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
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


@dataclass(frozen=True)
class RestMarketDataEndpoint:
    url: str
    params: dict[str, str]
    method: str = "GET"
    notes: str = ""


class DownloadError(RuntimeError):
    def __init__(self, url: str, reason: str) -> None:
        super().__init__(f"{reason}：{url}")
        self.url = url
        self.reason = reason


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

    def open_interest_endpoint(
        self,
        *,
        market_type: MarketType,
        symbol: str,
        interval: str = "5min",
    ) -> RestMarketDataEndpoint:
        ...


def download_file(file: HistoricalFile, target_dir: str | Path) -> Path:
    target = Path(target_dir)
    target.mkdir(parents=True, exist_ok=True)
    file_name = file.url.rstrip("/").split("/")[-1]
    output = target / file_name
    output.write_bytes(_download_bytes(file.url))
    return output


def download_json(endpoint: RestMarketDataEndpoint):
    url = endpoint.url
    if endpoint.params:
        url = f"{url}?{urlencode(endpoint.params)}"
    return json.loads(_download_bytes(url).decode("utf-8"))


def csv_rows_from_archive(raw: bytes, compression: str) -> list[dict[str, str]]:
    data = _decompress(raw, compression)
    text = data.decode("utf-8")
    sample = text[:1024]
    has_header = csv.Sniffer().has_header(sample)
    reader = csv.reader(io.StringIO(text))
    rows = list(reader)
    if not rows:
        return []
    if has_header and _looks_like_header(rows[0]):
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


def _download_bytes(url: str) -> bytes:
    try:
        with urlopen(url, timeout=30) as response:
            return response.read()
    except HTTPError as exc:
        raise DownloadError(url, f"HTTP {exc.code}") from exc
    except URLError as exc:
        raise DownloadError(url, f"URL error {exc.reason}") from exc
    except OSError as exc:
        raise DownloadError(url, f"network error {exc}") from exc


def _looks_like_header(row: list[str]) -> bool:
    return any(any(char.isalpha() for char in column) for column in row)
