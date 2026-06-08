from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

from packages.normalization.models import MarketEvent


@dataclass(frozen=True)
class Partition:
    exchange: str
    date: str
    market_type: str
    symbol: str
    event_type: str

    @classmethod
    def from_event(cls, event: MarketEvent) -> Partition:
        return cls(
            exchange=event.exchange.value,
            date=event.partition_date,
            market_type=event.market_type.value,
            symbol=event.symbol,
            event_type=event.event_type.value,
        )

    def path_under(self, root: Path) -> Path:
        return (
            root
            / f"exchange={self.exchange}"
            / f"date={self.date}"
            / f"market_type={self.market_type}"
            / f"symbol={self.symbol}"
            / f"event_type={self.event_type}"
        )


class DataLakeWriter:
    def __init__(self, root: str | Path, preferred_format: str = "parquet") -> None:
        self.root = Path(root)
        self.preferred_format = preferred_format

    def write_events(self, events: list[MarketEvent]) -> list[Path]:
        grouped: dict[Partition, list[MarketEvent]] = {}
        for event in events:
            grouped.setdefault(Partition.from_event(event), []).append(event)

        written: list[Path] = []
        for partition, partition_events in grouped.items():
            target_dir = partition.path_under(self.root)
            target_dir.mkdir(parents=True, exist_ok=True)
            if self.preferred_format == "parquet" and _pyarrow_available():
                written.append(_write_parquet(target_dir, partition_events))
            else:
                written.append(_write_jsonl(target_dir, partition_events))
        return written


class DataLakeReader:
    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)

    def iter_events(
        self,
        *,
        exchange: str | None = None,
        market_type: str | None = None,
        symbol: str | None = None,
        event_type: str | None = None,
    ):
        filters = {
            "exchange": exchange,
            "market_type": market_type,
            "symbol": symbol,
            "event_type": event_type,
        }
        files = sorted(self.root.rglob("*.jsonl")) + sorted(self.root.rglob("*.parquet"))
        for path in files:
            if not _path_matches_filters(path, filters):
                continue
            if path.suffix == ".jsonl":
                yield from _read_jsonl(path)
            elif path.suffix == ".parquet":
                yield from _read_parquet(path)


def _write_jsonl(target_dir: Path, events: list[MarketEvent]) -> Path:
    path = target_dir / f"part-{uuid4().hex}.jsonl"
    with path.open("w", encoding="utf-8") as handle:
        for event in events:
            handle.write(json.dumps(event.to_dict(), sort_keys=True) + "\n")
    return path


def _read_jsonl(path: Path):
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                yield MarketEvent.from_dict(json.loads(line))


def _pyarrow_available() -> bool:
    try:
        import pyarrow  # noqa: F401
        import pyarrow.parquet  # noqa: F401
    except ImportError:
        return False
    return True


def _write_parquet(target_dir: Path, events: list[MarketEvent]) -> Path:
    import pyarrow as pa
    import pyarrow.parquet as pq

    path = target_dir / f"part-{uuid4().hex}.parquet"
    rows = [event.to_dict() for event in events]
    for row in rows:
        row["payload"] = json.dumps(row["payload"], sort_keys=True)
    table = pa.Table.from_pylist(rows)
    pq.write_table(table, path, compression="zstd")
    return path


def _read_parquet(path: Path):
    import pyarrow.parquet as pq

    table = pq.read_table(path)
    for row in table.to_pylist():
        if isinstance(row.get("payload"), str):
            row["payload"] = json.loads(row["payload"])
        yield MarketEvent.from_dict(row)


def _path_matches_filters(path: Path, filters: dict[str, str | None]) -> bool:
    parts = set(path.parts)
    for key, value in filters.items():
        if value is None:
            continue
        if f"{key}={value}" not in parts:
            return False
    return True
