from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tomllib
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from hashlib import sha256
from pathlib import Path
from typing import Any

from packages.data_lake import (
    DataLakeReader,
    DataLakeWriter,
    check_data_coverage,
    generate_data_collection_jobs,
)
from packages.data_lake.collection_commands import plan_data_collection_commands
from packages.normalization import (
    FundingPayload,
    Instrument,
    MarketEvent,
    MarkPricePayload,
    OpenInterestPayload,
    TradePayload,
)
from packages.normalization.models import ensure_utc
from packages.replay import ReplayEngine
from packages.strategies import (
    CrossExchangeSpreadStrategy,
    FundingCarryStrategy,
    FuturesBasisStrategy,
    OpenInterestMomentumStrategy,
    StrategyRegistry,
)


def build_registry() -> StrategyRegistry:
    registry = StrategyRegistry()
    registry.register(CrossExchangeSpreadStrategy())
    registry.register(FundingCarryStrategy())
    registry.register(FuturesBasisStrategy())
    registry.register(OpenInterestMomentumStrategy())
    return registry


@dataclass(frozen=True)
class LocalPlan:
    coverage: dict[str, Any]
    job_plan: dict[str, Any]
    command_plan: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "coverage": self.coverage,
            "job_plan": self.job_plan,
            "command_plan": self.command_plan,
        }


def build_local_plan(
    *,
    proposal: dict[str, Any],
    data_lake_root: str | Path,
    download_dir: str | Path,
    exchanges: list[str],
    market_types: list[str],
    symbols: list[str],
    start_date: date,
    end_date: date,
    python_bin: str | None = None,
    current_date: date | None = None,
    limit: int | None = None,
) -> LocalPlan:
    job_plan = generate_data_collection_jobs(
        root=data_lake_root,
        proposal=proposal,
        exchanges=exchanges,
        market_types=market_types,
        symbols=symbols,
        start_date=start_date,
        end_date=end_date,
        limit=limit,
    )
    command_plan = plan_data_collection_commands(
        jobs=[job.to_dict() for job in job_plan.jobs],
        data_lake_root=str(data_lake_root),
        download_dir=str(download_dir),
        python_bin=python_bin or sys.executable,
        current_date=current_date,
    )
    return LocalPlan(
        coverage=job_plan.coverage.to_dict(),
        job_plan=job_plan.to_dict(),
        command_plan=command_plan.to_dict(),
    )


def execute_command_plan(
    command_plan: dict[str, Any],
    *,
    include_high_risk: bool = False,
    dry_run: bool = False,
    state_path: str | Path | None = None,
    force: bool = False,
) -> dict[str, Any]:
    state = _read_job_state(state_path)
    results: list[dict[str, Any]] = []
    normalized_command_plan = _extract_command_plan(command_plan)
    for command in normalized_command_plan.get("commands", []):
        job_id = str(command.get("job_id") or "")
        previous = state.get(job_id, {})
        record = {
            "job_id": job_id,
            "event_type": command.get("event_type"),
            "supported": command.get("supported", False),
            "risk_tier": command.get("risk_tier", "unknown"),
            "executed": False,
            "returncode": None,
            "stdout": "",
            "stderr": "",
            "skipped_reason": "",
            "command": command.get("command", []),
            "status": previous.get("status", "planned"),
        }
        if previous.get("status") == "succeeded" and not force:
            record["skipped_reason"] = "already_succeeded"
            record["status"] = "succeeded"
            results.append(record)
            continue
        if not command.get("supported", False):
            record["skipped_reason"] = command.get("reason", "unsupported")
            record["status"] = "blocked"
            _update_job_state(
                state,
                command=command,
                status="blocked",
                returncode=None,
                stderr=record["skipped_reason"],
            )
            results.append(record)
            continue
        if command.get("requires_confirmation") and not include_high_risk:
            record["skipped_reason"] = "requires_confirmation"
            record["status"] = "skipped"
            results.append(record)
            continue
        if dry_run:
            record["skipped_reason"] = "dry_run"
            record["status"] = "dry_run"
            results.append(record)
            continue
        try:
            completed = subprocess.run(
                command["command"],
                check=False,
                capture_output=True,
                text=True,
            )
        except OSError as exc:
            record["executed"] = True
            record["returncode"] = 127
            record["stderr"] = str(exc)
            record["status"] = "failed"
            _update_job_state(
                state,
                command=command,
                status="failed",
                returncode=127,
                stderr=str(exc),
            )
            results.append(record)
            continue
        record["executed"] = True
        record["returncode"] = completed.returncode
        record["stdout"] = completed.stdout
        record["stderr"] = completed.stderr
        record["status"] = "succeeded" if completed.returncode == 0 else "failed"
        _update_job_state(
            state,
            command=command,
            status=record["status"],
            returncode=completed.returncode,
            stdout=completed.stdout,
            stderr=completed.stderr,
        )
        results.append(record)
    _write_job_state(state_path, state)
    return {
        "executed_count": sum(1 for result in results if result["executed"]),
        "skipped_count": sum(1 for result in results if not result["executed"]),
        "failed_count": sum(
            1
            for result in results
            if result["executed"] and result["returncode"] not in {0, None}
        ),
        "results": results,
    }


def build_validation_report(
    *,
    data_lake_root: str | Path,
    strategy_name: str,
    start_ts: str | None = None,
    end_ts: str | None = None,
    exchange: str | None = None,
    market_type: str | None = None,
    symbol: str | None = None,
) -> dict[str, Any]:
    strategy = build_registry().get(strategy_name)
    replay = ReplayEngine(DataLakeReader(data_lake_root)).replay(
        strategy,
        start_ts=start_ts,
        end_ts=end_ts,
        exchange=exchange,
        market_type=market_type,
        symbol=symbol,
    )
    opportunities = [opportunity.to_dict() for opportunity in replay.opportunities]
    event_window = _event_window(
        data_lake_root=data_lake_root,
        required_data=strategy.required_data(),
        start_ts=start_ts,
        end_ts=end_ts,
        exchange=exchange,
        market_type=market_type,
        symbol=symbol,
    )
    report = {
        "kind": "opportunity_report",
        "title": f"{strategy_name} local validation report",
        "created_by": "local_pipeline",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "strategy_name": strategy_name,
        "strategy_version": replay.version,
        "data_window": {
            "start_ts": start_ts
            or _opportunity_window(opportunities, "start_ts")
            or event_window["start_ts"],
            "end_ts": end_ts
            or _opportunity_window(opportunities, "end_ts")
            or event_window["end_ts"],
        },
        "opportunity_count": replay.opportunity_count,
        "opportunities": opportunities,
        "result_hash": None,
        "metadata": {
            "event_count": replay.event_count,
            "filters": {
                "exchange": exchange,
                "market_type": market_type,
                "symbol": symbol,
            },
        },
    }
    report["result_hash"] = _result_hash(report)
    return report


def seed_fixture_data(
    *,
    data_lake_root: str | Path,
    fixture: str,
    symbol: str = "BTC-USDT",
    start_ts: str = "2024-01-01T00:00:00+00:00",
) -> dict[str, Any]:
    ts = datetime.fromisoformat(start_ts.replace("Z", "+00:00"))
    events = _fixture_events(fixture=fixture, symbol=symbol, ts=ts)
    paths = DataLakeWriter(data_lake_root, preferred_format="jsonl").write_events(events)
    return {
        "kind": "local_fixture_seed_result",
        "fixture": fixture,
        "data_lake_root": str(data_lake_root),
        "event_count": len(events),
        "written_paths": [str(path) for path in paths],
    }


def plan_retention(
    *,
    data_lake_root: str | Path,
    keep_days: int,
    current_date: date | None = None,
    apply: bool = False,
) -> dict[str, Any]:
    if keep_days <= 0:
        raise ValueError("keep_days 必须大于 0")
    root = Path(data_lake_root)
    current = current_date or datetime.now(timezone.utc).date()
    cutoff = current - timedelta(days=keep_days)
    expired_files: list[Path] = []
    expired_partitions: set[Path] = set()
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.suffix not in {".jsonl", ".parquet"}:
            continue
        partition_date = _date_from_partition_path(path)
        if partition_date is None or partition_date >= cutoff:
            continue
        expired_files.append(path)
        expired_partitions.add(_event_partition_dir(path))
    deleted_files: list[str] = []
    if apply:
        for path in expired_files:
            path.unlink(missing_ok=True)
            deleted_files.append(str(path))
        _remove_empty_dirs(root)
    return {
        "kind": "retention_plan",
        "data_lake_root": str(root),
        "keep_days": keep_days,
        "current_date": current.isoformat(),
        "cutoff_date": cutoff.isoformat(),
        "apply": apply,
        "expired_partition_count": len(expired_partitions),
        "expired_file_count": len(expired_files),
        "deleted_file_count": len(deleted_files),
        "would_delete_files": [str(path) for path in expired_files],
        "deleted_files": deleted_files,
    }


def build_daily_ingest_plan(
    *,
    config_path: str | Path,
    current_date: date | None = None,
    python_bin: str | None = None,
) -> dict[str, Any]:
    config = tomllib.loads(Path(config_path).read_text(encoding="utf-8"))
    current = current_date or datetime.now(timezone.utc).date()
    lookback_days = int(config.get("lookback_days", 1))
    if lookback_days <= 0:
        raise ValueError("lookback_days 必须大于 0")
    end_date = current - timedelta(days=1)
    start_date = end_date - timedelta(days=lookback_days - 1)
    proposal_path = Path(str(config["proposal"]))
    local_plan = build_local_plan(
        proposal=_read_json(proposal_path),
        data_lake_root=str(config.get("data_lake_root", ".data/lake")),
        download_dir=str(config.get("download_dir", "var/downloads")),
        exchanges=list(config.get("exchanges", ["binance"])),
        market_types=list(config.get("market_types", ["perp"])),
        symbols=list(config.get("symbols", ["BTCUSDT"])),
        start_date=start_date,
        end_date=end_date,
        python_bin=python_bin,
        current_date=current,
        limit=config.get("limit"),
    ).to_dict()
    return {
        "kind": "daily_ingest_plan",
        "config_path": str(config_path),
        "config": {
            "data_lake_root": str(config.get("data_lake_root", ".data/lake")),
            "download_dir": str(config.get("download_dir", "var/downloads")),
            "proposal": str(proposal_path),
            "exchanges": list(config.get("exchanges", ["binance"])),
            "market_types": list(config.get("market_types", ["perp"])),
            "symbols": list(config.get("symbols", ["BTCUSDT"])),
            "lookback_days": lookback_days,
            "retention_days": int(config.get("retention_days", 180)),
        },
        "ingest_window": {
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
        },
        "local_plan": local_plan,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Strategy Miner 本地数据和验证流水线")
    subparsers = parser.add_subparsers(dest="command", required=True)

    plan_parser = subparsers.add_parser("plan", help="生成本地数据覆盖、采集 job 和命令计划")
    _add_plan_args(plan_parser)
    plan_parser.add_argument("--output")

    collect_parser = subparsers.add_parser("collect", help="执行 plan 中的低/中风险采集命令")
    collect_parser.add_argument("--plan-json", required=True)
    collect_parser.add_argument("--output")
    collect_parser.add_argument("--include-high-risk", action="store_true")
    collect_parser.add_argument("--dry-run", action="store_true")
    collect_parser.add_argument("--state-json")
    collect_parser.add_argument("--force", action="store_true")

    validate_parser = subparsers.add_parser("validate", help="读取 data lake 并跑 replay 验证")
    validate_parser.add_argument("--data-lake-root", default=".data/lake")
    validate_parser.add_argument("--strategy", required=True)
    validate_parser.add_argument("--start-ts")
    validate_parser.add_argument("--end-ts")
    validate_parser.add_argument("--exchange")
    validate_parser.add_argument("--market-type")
    validate_parser.add_argument("--symbol")
    validate_parser.add_argument("--output")

    seed_parser = subparsers.add_parser("seed-fixture", help="写入离线 fixture 数据用于本地冒烟验证")
    seed_parser.add_argument(
        "--fixture",
        choices=["funding-carry", "oi-momentum", "quarterly-basis"],
        required=True,
    )
    seed_parser.add_argument("--data-lake-root", default=".data/lake")
    seed_parser.add_argument("--symbol", default="BTC-USDT")
    seed_parser.add_argument("--start-ts", default="2024-01-01T00:00:00+00:00")
    seed_parser.add_argument("--output")

    coverage_parser = subparsers.add_parser("coverage", help="只检查 data lake 覆盖率")
    _add_plan_args(coverage_parser)
    coverage_parser.add_argument("--output")

    retention_parser = subparsers.add_parser("retention", help="生成或执行 data lake 保留策略")
    retention_parser.add_argument("--data-lake-root", default=".data/lake")
    retention_parser.add_argument("--keep-days", type=int, default=180)
    retention_parser.add_argument("--current-date")
    retention_parser.add_argument("--apply", action="store_true")
    retention_parser.add_argument("--output")

    daily_parser = subparsers.add_parser("daily-ingest", help="按 TOML 配置生成每日采集计划")
    daily_parser.add_argument("--config", required=True)
    daily_parser.add_argument("--current-date")
    daily_parser.add_argument("--output")

    args = parser.parse_args(argv)
    if args.command == "plan":
        proposal = _read_json(args.proposal)
        plan = build_local_plan(
            proposal=proposal,
            data_lake_root=args.data_lake_root,
            download_dir=args.download_dir,
            exchanges=_csv(args.exchanges),
            market_types=_csv(args.market_types),
            symbols=_csv(args.symbols),
            start_date=date.fromisoformat(args.start_date),
            end_date=date.fromisoformat(args.end_date),
            limit=args.limit,
        ).to_dict()
        _write_or_print(plan, args.output)
        return 0
    if args.command == "collect":
        plan = _read_json(args.plan_json)
        result = execute_command_plan(
            plan["command_plan"],
            include_high_risk=args.include_high_risk,
            dry_run=args.dry_run,
            state_path=args.state_json,
            force=args.force,
        )
        _write_or_print(result, args.output)
        return 0 if result["failed_count"] == 0 else 1
    if args.command == "validate":
        report = build_validation_report(
            data_lake_root=args.data_lake_root,
            strategy_name=args.strategy,
            start_ts=args.start_ts,
            end_ts=args.end_ts,
            exchange=args.exchange,
            market_type=args.market_type,
            symbol=args.symbol,
        )
        _write_or_print(report, args.output)
        return 0
    if args.command == "seed-fixture":
        result = seed_fixture_data(
            data_lake_root=args.data_lake_root,
            fixture=args.fixture,
            symbol=args.symbol,
            start_ts=args.start_ts,
        )
        _write_or_print(result, args.output)
        return 0
    if args.command == "retention":
        current_date = (
            None if args.current_date is None else date.fromisoformat(args.current_date)
        )
        result = plan_retention(
            data_lake_root=args.data_lake_root,
            keep_days=args.keep_days,
            current_date=current_date,
            apply=args.apply,
        )
        _write_or_print(result, args.output)
        return 0
    if args.command == "daily-ingest":
        current_date = (
            None if args.current_date is None else date.fromisoformat(args.current_date)
        )
        result = build_daily_ingest_plan(
            config_path=args.config,
            current_date=current_date,
        )
        _write_or_print(result, args.output)
        return 0
    if args.command == "coverage":
        proposal = _read_json(args.proposal)
        report = check_data_coverage(
            root=args.data_lake_root,
            proposal=proposal,
            exchanges=_csv(args.exchanges),
            market_types=_csv(args.market_types),
            symbols=_csv(args.symbols),
            start_date=date.fromisoformat(args.start_date),
            end_date=date.fromisoformat(args.end_date),
        ).to_dict()
        _write_or_print(report, args.output)
        return 0
    return 1


def _add_plan_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--proposal", required=True)
    parser.add_argument("--data-lake-root", default=".data/lake")
    parser.add_argument("--download-dir", default="var/downloads")
    parser.add_argument("--exchanges", default="binance")
    parser.add_argument("--market-types", default="perp")
    parser.add_argument("--symbols", default="BTCUSDT")
    parser.add_argument("--start-date", required=True)
    parser.add_argument("--end-date", required=True)
    parser.add_argument("--limit", type=int)


def _csv(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


def _read_json(path: str | Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _write_or_print(payload: dict[str, Any], output: str | None) -> None:
    text = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True)
    if output:
        Path(output).parent.mkdir(parents=True, exist_ok=True)
        Path(output).write_text(text + "\n", encoding="utf-8")
    else:
        print(text)


def _extract_command_plan(plan: dict[str, Any]) -> dict[str, Any]:
    if "commands" in plan:
        return plan
    if "command_plan" in plan:
        return plan["command_plan"]
    local_plan = plan.get("local_plan")
    if isinstance(local_plan, dict) and "command_plan" in local_plan:
        return local_plan["command_plan"]
    raise ValueError("plan JSON 缺少 command_plan")


def _read_job_state(path: str | Path | None) -> dict[str, Any]:
    if path is None:
        return {}
    state_path = Path(path)
    if not state_path.exists():
        return {}
    return json.loads(state_path.read_text(encoding="utf-8"))


def _write_job_state(path: str | Path | None, state: dict[str, Any]) -> None:
    if path is None:
        return
    state_path = Path(path)
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(
        json.dumps(state, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _update_job_state(
    state: dict[str, Any],
    *,
    command: dict[str, Any],
    status: str,
    returncode: int | None,
    stdout: str = "",
    stderr: str = "",
) -> None:
    job_id = str(command.get("job_id") or "")
    if not job_id:
        return
    previous = state.get(job_id, {})
    state[job_id] = {
        "job_id": job_id,
        "event_type": command.get("event_type"),
        "status": status,
        "attempt_count": int(previous.get("attempt_count", 0))
        + (1 if status in {"succeeded", "failed"} else 0),
        "last_returncode": returncode,
        "last_stdout": stdout,
        "last_error": stderr,
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "command": command.get("command", []),
    }


def _date_from_partition_path(path: Path) -> date | None:
    for part in path.parts:
        if not part.startswith("date="):
            continue
        try:
            return date.fromisoformat(part.removeprefix("date="))
        except ValueError:
            return None
    return None


def _event_partition_dir(path: Path) -> Path:
    current = path.parent
    while current.parent != current:
        if current.name.startswith("event_type="):
            return current
        current = current.parent
    return path.parent


def _remove_empty_dirs(root: Path) -> None:
    for path in sorted(root.rglob("*"), key=lambda item: len(item.parts), reverse=True):
        if not path.is_dir():
            continue
        try:
            path.rmdir()
        except OSError:
            pass


def _fixture_events(*, fixture: str, symbol: str, ts: datetime) -> list[MarketEvent]:
    if fixture == "funding-carry":
        later = ts.replace(minute=ts.minute + 1)
        return [
            _event("funding", "perp", symbol, FundingPayload(rate="0.003"), ts),
            _event("mark", "spot", symbol, MarkPricePayload(mark_price="100"), ts),
            _event("mark", "perp", symbol, MarkPricePayload(mark_price="100"), ts),
            _event("index", "perp", symbol, {"index_price": "100"}, ts),
            _event("trade", "spot", symbol, TradePayload("spot-1", "100", "0.1"), ts),
            _event("trade", "spot", symbol, TradePayload("spot-2", "101", "0.1"), later),
        ]
    if fixture == "oi-momentum":
        later = ts.replace(hour=ts.hour + 1)
        return [
            _event("mark", "perp", symbol, MarkPricePayload(mark_price="100"), ts),
            _event("mark", "perp", symbol, MarkPricePayload(mark_price="102"), later),
            _event(
                "open_interest",
                "perp",
                symbol,
                OpenInterestPayload(open_interest="1000"),
                ts,
            ),
            _event(
                "open_interest",
                "perp",
                symbol,
                OpenInterestPayload(open_interest="1060"),
                later,
            ),
            _event("funding", "perp", symbol, FundingPayload(rate="0.0002"), later),
        ]
    if fixture == "quarterly-basis":
        expiry = ts.replace(day=31)
        return [
            _event("mark", "spot", symbol, MarkPricePayload(mark_price="100"), ts),
            _event("mark", "future", symbol, MarkPricePayload(mark_price="103"), ts),
            _event(
                "instrument",
                "future",
                symbol,
                Instrument(
                    exchange="binance",
                    market_type="future",
                    symbol=symbol,
                    base_asset=symbol.split("-")[0],
                    quote_asset=symbol.split("-")[1],
                    contract_size="1",
                    expiry_ts=expiry,
                ),
                ts,
            ),
        ]
    raise ValueError(f"未知 fixture：{fixture}")


def _event(
    event_type: str,
    market_type: str,
    symbol: str,
    payload: object,
    ts: datetime,
) -> MarketEvent:
    base, quote = symbol.split("-")
    return MarketEvent(
        exchange="binance",
        market_type=market_type,
        symbol=symbol,
        base_asset=base,
        quote_asset=quote,
        event_type=event_type,
        exchange_ts=ts,
        local_ts=ts,
        source="local-fixture",
        sequence_id=f"{event_type}-{market_type}-{symbol}-{ts.isoformat()}",
        payload=payload,
    )


def _opportunity_window(opportunities: list[dict[str, Any]], key: str) -> str:
    if not opportunities:
        return ""
    values = [opportunity["data_window"][key] for opportunity in opportunities]
    return min(values) if key == "start_ts" else max(values)


def _event_window(
    *,
    data_lake_root: str | Path,
    required_data,
    start_ts: str | None,
    end_ts: str | None,
    exchange: str | None,
    market_type: str | None,
    symbol: str | None,
) -> dict[str, str]:
    start = ensure_utc(start_ts) if start_ts is not None else None
    end = ensure_utc(end_ts) if end_ts is not None else None
    events = []
    for event in DataLakeReader(data_lake_root).iter_events(
        exchange=exchange,
        market_type=market_type,
        symbol=symbol,
    ):
        if event.event_type not in required_data:
            continue
        if start is not None and event.exchange_ts < start:
            continue
        if end is not None and event.exchange_ts > end:
            continue
        events.append(event.exchange_ts)
    if not events:
        return {"start_ts": "", "end_ts": ""}
    return {
        "start_ts": min(events).isoformat(),
        "end_ts": max(events).isoformat(),
    }


def _result_hash(report: dict[str, Any]) -> str:
    stable = {
        key: value
        for key, value in report.items()
        if key not in {"created_at", "result_hash"}
    }
    encoded = json.dumps(stable, ensure_ascii=False, sort_keys=True).encode("utf-8")
    return sha256(encoded).hexdigest()


if __name__ == "__main__":
    raise SystemExit(main())
