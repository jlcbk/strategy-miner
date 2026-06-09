from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Any


@dataclass(frozen=True)
class CollectorCommand:
    job_id: str
    exchange: str
    market_type: str
    symbol: str
    event_type: str
    day: str
    supported: bool
    command: list[str]
    reason: str = ""
    risk_tier: str = "unknown"
    requires_confirmation: bool = True
    execution_group: str = "unknown"

    def to_dict(self) -> dict[str, Any]:
        return {
            "job_id": self.job_id,
            "exchange": self.exchange,
            "market_type": self.market_type,
            "symbol": self.symbol,
            "event_type": self.event_type,
            "day": self.day,
            "supported": self.supported,
            "command": self.command,
            "reason": self.reason,
            "risk_tier": self.risk_tier,
            "requires_confirmation": self.requires_confirmation,
            "execution_group": self.execution_group,
        }


@dataclass(frozen=True)
class CollectorCommandPlan:
    supported_count: int
    blocked_count: int
    risk_counts: dict[str, int]
    commands: list[CollectorCommand]

    def to_dict(self) -> dict[str, Any]:
        return {
            "supported_count": self.supported_count,
            "blocked_count": self.blocked_count,
            "risk_counts": self.risk_counts,
            "commands": [command.to_dict() for command in self.commands],
        }


def plan_data_collection_commands(
    *,
    jobs: list[dict[str, Any]],
    data_lake_root: str = ".data/lake",
    download_dir: str = "var/downloads",
    python_bin: str = "python3",
    current_date: date | None = None,
) -> CollectorCommandPlan:
    current_date = current_date or datetime.now(timezone.utc).date()
    commands = [
        _command_for_job(
            job,
            data_lake_root=data_lake_root,
            download_dir=download_dir,
            python_bin=python_bin,
            current_date=current_date,
        )
        for job in jobs
    ]
    return CollectorCommandPlan(
        supported_count=sum(1 for command in commands if command.supported),
        blocked_count=sum(1 for command in commands if not command.supported),
        risk_counts=_risk_counts(commands),
        commands=commands,
    )


def _command_for_job(
    job: dict[str, Any],
    *,
    data_lake_root: str,
    download_dir: str,
    python_bin: str,
    current_date: date,
) -> CollectorCommand:
    job_id = str(job.get("id", ""))
    exchange = str(job["exchange"])
    market_type = str(job["market_type"])
    symbol = str(job["symbol"])
    event_type = str(job["event_type"])
    day = _job_day(job)

    reason = _unsupported_reason(
        exchange=exchange,
        market_type=market_type,
        event_type=event_type,
        day=day,
        current_date=current_date,
    )
    if reason:
        risk_tier = _risk_tier(event_type)
        return CollectorCommand(
            job_id=job_id,
            exchange=exchange,
            market_type=market_type,
            symbol=symbol,
            event_type=event_type,
            day=day.isoformat(),
            supported=False,
            command=[],
            reason=reason,
            risk_tier=risk_tier,
            requires_confirmation=_requires_confirmation(risk_tier),
            execution_group=_execution_group(event_type),
        )

    risk_tier = _risk_tier(event_type)
    command = [
        python_bin,
        "-m",
        "apps.collector.main",
        _collector_subcommand(event_type),
        "--exchange",
        exchange,
        "--market-type",
        market_type,
        "--symbol",
        symbol,
        "--day",
        day.isoformat(),
        "--data-lake-root",
        data_lake_root,
    ]
    if event_type in {"trade", "mark"}:
        command.extend(["--download-dir", download_dir])
    if event_type == "orderbook":
        command.extend(["--limit", "20"])
    return CollectorCommand(
        job_id=job_id,
        exchange=exchange,
        market_type=market_type,
        symbol=symbol,
        event_type=event_type,
        day=day.isoformat(),
        supported=True,
        command=command,
        risk_tier=risk_tier,
        requires_confirmation=_requires_confirmation(risk_tier),
        execution_group=_execution_group(event_type),
    )


def _job_day(job: dict[str, Any]) -> date:
    start_ts = str(job["start_ts"])
    return datetime.fromisoformat(start_ts.replace("Z", "+00:00")).date()


def _unsupported_reason(
    *,
    exchange: str,
    market_type: str,
    event_type: str,
    day: date,
    current_date: date,
) -> str:
    if event_type == "orderbook" and day != current_date:
        return "orderbook-snapshot collector 只能采当前盘口，不能回补历史 orderbook 分区"
    if event_type == "orderbook" and exchange != "binance":
        return f"{exchange} orderbook snapshot collector 尚未接入"
    if event_type == "orderbook":
        return ""
    if event_type not in {"trade", "mark", "funding", "open_interest"}:
        return f"collector 暂未支持事件类型：{event_type}"
    if event_type in {"mark", "funding", "open_interest"} and market_type not in {
        "perp",
        "future",
    }:
        return f"{event_type} collector 只支持衍生品市场"
    if exchange == "binance":
        if event_type == "open_interest" and day < current_date - timedelta(days=31):
            return "Binance open_interest 历史 REST 仅支持最近约 1 个月"
        return ""
    if exchange == "bybit" and event_type in {"trade", "mark", "funding", "open_interest"}:
        return ""
    return f"{exchange} {event_type} collector 尚未接入"


def _collector_subcommand(event_type: str) -> str:
    return {
        "trade": "historical-trades",
        "mark": "historical-mark",
        "funding": "funding",
        "open_interest": "open-interest",
        "orderbook": "orderbook-snapshot",
    }[event_type]


def _risk_tier(event_type: str) -> str:
    if event_type in {"funding", "open_interest"}:
        return "low"
    if event_type == "mark":
        return "medium"
    if event_type in {"trade", "orderbook"}:
        return "high"
    return "unknown"


def _requires_confirmation(risk_tier: str) -> bool:
    return risk_tier in {"high", "unknown"}


def _execution_group(event_type: str) -> str:
    return {
        "funding": "small_rest",
        "open_interest": "small_rest",
        "mark": "archive_mark",
        "trade": "archive_trade",
        "orderbook": "stream_orderbook",
    }.get(event_type, "unknown")


def _risk_counts(commands: list[CollectorCommand]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for command in commands:
        counts[command.risk_tier] = counts.get(command.risk_tier, 0) + 1
    return counts
