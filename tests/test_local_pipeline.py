import sys
from datetime import datetime, timezone
from decimal import Decimal

from apps.local_pipeline.main import (
    build_local_plan,
    build_daily_ingest_plan,
    build_validation_report,
    execute_command_plan,
    plan_retention,
    seed_fixture_data,
)
from packages.data_lake import DataLakeWriter
from packages.normalization import FundingPayload, MarketEvent, MarkPricePayload, TradePayload


def _event(
    *,
    event_type: str,
    market_type: str,
    payload: object,
    ts: datetime,
) -> MarketEvent:
    return MarketEvent(
        exchange="binance",
        market_type=market_type,
        symbol="BTC-USDT",
        base_asset="BTC",
        quote_asset="USDT",
        event_type=event_type,
        exchange_ts=ts,
        local_ts=ts,
        source="unit-test",
        sequence_id=f"{event_type}-{market_type}-{ts.isoformat()}",
        payload=payload,
    )


def test_local_plan_uses_current_python_executable_and_windows_safe_paths(tmp_path) -> None:
    proposal = {
        "strategy_name": "oi_confirmed_momentum",
        "data_requirements": ["open_interest", "funding"],
    }

    plan = build_local_plan(
        proposal=proposal,
        data_lake_root=tmp_path / "lake",
        download_dir=tmp_path / "downloads",
        exchanges=["binance"],
        market_types=["perp"],
        symbols=["BTCUSDT"],
        start_date=datetime(2026, 6, 9, tzinfo=timezone.utc).date(),
        end_date=datetime(2026, 6, 9, tzinfo=timezone.utc).date(),
        python_bin="py",
        current_date=datetime(2026, 6, 10, tzinfo=timezone.utc).date(),
    ).to_dict()

    assert plan["coverage"]["ready"] is False
    assert plan["job_plan"]["coverage"]["required_count"] == 2
    commands = plan["command_plan"]["commands"]
    assert plan["command_plan"]["supported_count"] == 2
    assert {command["event_type"] for command in commands} == {"funding", "open_interest"}
    assert all(command["command"][0] == "py" for command in commands)
    assert all(str(tmp_path / "lake") in command["command"] for command in commands)


def test_execute_command_plan_skips_high_risk_by_default() -> None:
    command_plan = {
        "commands": [
            {
                "job_id": "trade-job",
                "event_type": "trade",
                "supported": True,
                "risk_tier": "high",
                "requires_confirmation": True,
                "command": ["python", "-c", "raise SystemExit(99)"],
            },
            {
                "job_id": "blocked-job",
                "event_type": "instrument",
                "supported": False,
                "risk_tier": "low",
                "requires_confirmation": False,
                "reason": "unsupported fixture",
                "command": [],
            },
        ]
    }

    result = execute_command_plan(command_plan)

    assert result["executed_count"] == 0
    assert result["skipped_count"] == 2
    assert result["failed_count"] == 0
    assert result["results"][0]["skipped_reason"] == "requires_confirmation"
    assert result["results"][1]["skipped_reason"] == "unsupported fixture"


def test_execute_command_plan_persists_job_state_and_skips_succeeded(tmp_path) -> None:
    state_path = tmp_path / "jobs.json"
    command_plan = {
        "commands": [
            {
                "job_id": "ok-job",
                "event_type": "funding",
                "supported": True,
                "risk_tier": "low",
                "requires_confirmation": False,
                "command": [sys.executable, "-c", "print('ok')"],
            }
        ]
    }

    first = execute_command_plan(command_plan, state_path=state_path)
    second = execute_command_plan(command_plan, state_path=state_path)
    forced = execute_command_plan(command_plan, state_path=state_path, force=True)

    assert first["executed_count"] == 1
    assert first["results"][0]["status"] == "succeeded"
    assert second["executed_count"] == 0
    assert second["results"][0]["skipped_reason"] == "already_succeeded"
    assert forced["executed_count"] == 1


def test_execute_command_plan_records_failed_jobs_for_retry(tmp_path) -> None:
    state_path = tmp_path / "jobs.json"
    command_plan = {
        "commands": [
            {
                "job_id": "fail-job",
                "event_type": "funding",
                "supported": True,
                "risk_tier": "low",
                "requires_confirmation": False,
                "command": [sys.executable, "-c", "raise SystemExit(7)"],
            }
        ]
    }

    result = execute_command_plan(command_plan, state_path=state_path)

    assert result["executed_count"] == 1
    assert result["failed_count"] == 1
    assert result["results"][0]["status"] == "failed"
    assert result["results"][0]["returncode"] == 7
    assert "fail-job" in state_path.read_text(encoding="utf-8")


def test_build_validation_report_reads_jsonl_lake_and_hashes_result(tmp_path) -> None:
    base_ts = datetime(2024, 1, 1, 0, 0, tzinfo=timezone.utc)
    later_ts = datetime(2024, 1, 1, 0, 1, tzinfo=timezone.utc)
    events = [
        _event(
            event_type="funding",
            market_type="perp",
            payload=FundingPayload(rate="0.003"),
            ts=base_ts,
        ),
        _event(
            event_type="mark",
            market_type="spot",
            payload=MarkPricePayload(mark_price="100"),
            ts=base_ts,
        ),
        _event(
            event_type="mark",
            market_type="perp",
            payload=MarkPricePayload(mark_price="100"),
            ts=base_ts,
        ),
        _event(
            event_type="index",
            market_type="perp",
            payload={"index_price": "100"},
            ts=base_ts,
        ),
        _event(
            event_type="trade",
            market_type="spot",
            payload=TradePayload("spot-1", "100", "0.1"),
            ts=base_ts,
        ),
        _event(
            event_type="trade",
            market_type="spot",
            payload=TradePayload("spot-2", "101", "0.1"),
            ts=later_ts,
        ),
    ]
    DataLakeWriter(tmp_path, preferred_format="jsonl").write_events(events)

    report = build_validation_report(
        data_lake_root=tmp_path,
        strategy_name="funding_carry_vol_filter",
    )

    assert report["kind"] == "opportunity_report"
    assert report["created_by"] == "local_pipeline"
    assert report["strategy_name"] == "funding_carry_vol_filter"
    assert report["opportunity_count"] == 1
    assert report["metadata"]["event_count"] == 6
    assert report["result_hash"]
    assert Decimal(report["opportunities"][0]["net_edge_usd"]) == Decimal("0.600")


def test_build_validation_report_uses_event_window_without_opportunities(tmp_path) -> None:
    base_ts = datetime(2024, 1, 1, 0, 0, tzinfo=timezone.utc)
    later_ts = datetime(2024, 1, 1, 0, 5, tzinfo=timezone.utc)
    DataLakeWriter(tmp_path, preferred_format="jsonl").write_events(
        [
            _event(
                event_type="mark",
                market_type="perp",
                payload=MarkPricePayload(mark_price="100"),
                ts=base_ts,
            ),
            _event(
                event_type="mark",
                market_type="perp",
                payload=MarkPricePayload(mark_price="101"),
                ts=later_ts,
            ),
        ]
    )

    report = build_validation_report(
        data_lake_root=tmp_path,
        strategy_name="funding_carry_vol_filter",
    )

    assert report["opportunity_count"] == 0
    assert report["metadata"]["event_count"] == 2
    assert report["data_window"] == {
        "start_ts": "2024-01-01T00:00:00+00:00",
        "end_ts": "2024-01-01T00:05:00+00:00",
    }


def test_seed_fixture_data_enables_offline_validation_smoke(tmp_path) -> None:
    seed_result = seed_fixture_data(
        data_lake_root=tmp_path,
        fixture="oi-momentum",
    )

    report = build_validation_report(
        data_lake_root=tmp_path,
        strategy_name="oi_confirmed_momentum",
    )

    assert seed_result["kind"] == "local_fixture_seed_result"
    assert seed_result["event_count"] == 5
    assert len(seed_result["written_paths"]) == 3
    assert report["opportunity_count"] == 1
    assert report["metadata"]["event_count"] == 5
    assert report["opportunities"][0]["metadata"]["oi_change_pct"] == "6.00"


def test_plan_retention_dry_run_marks_expired_partitions(tmp_path) -> None:
    old_file = (
        tmp_path
        / "exchange=binance"
        / "date=2024-01-01"
        / "market_type=perp"
        / "symbol=BTC-USDT"
        / "event_type=funding"
        / "part-old.jsonl"
    )
    fresh_file = (
        tmp_path
        / "exchange=binance"
        / "date=2026-06-01"
        / "market_type=perp"
        / "symbol=BTC-USDT"
        / "event_type=funding"
        / "part-fresh.jsonl"
    )
    old_file.parent.mkdir(parents=True)
    fresh_file.parent.mkdir(parents=True)
    old_file.write_text("{}\n", encoding="utf-8")
    fresh_file.write_text("{}\n", encoding="utf-8")

    result = plan_retention(
        data_lake_root=tmp_path,
        keep_days=180,
        current_date=datetime(2026, 6, 10, tzinfo=timezone.utc).date(),
    )

    assert result["expired_partition_count"] == 1
    assert result["expired_file_count"] == 1
    assert result["would_delete_files"] == [str(old_file)]
    assert old_file.exists()
    assert fresh_file.exists()


def test_plan_retention_apply_removes_expired_files_and_empty_dirs(tmp_path) -> None:
    old_file = (
        tmp_path
        / "exchange=binance"
        / "date=2024-01-01"
        / "market_type=perp"
        / "symbol=BTC-USDT"
        / "event_type=funding"
        / "part-old.jsonl"
    )
    old_file.parent.mkdir(parents=True)
    old_file.write_text("{}\n", encoding="utf-8")

    result = plan_retention(
        data_lake_root=tmp_path,
        keep_days=180,
        current_date=datetime(2026, 6, 10, tzinfo=timezone.utc).date(),
        apply=True,
    )

    assert result["deleted_file_count"] == 1
    assert not old_file.exists()


def test_build_daily_ingest_plan_reads_toml_config(tmp_path) -> None:
    proposal = tmp_path / "proposal.json"
    proposal.write_text(
        """
{
  "strategy_name": "oi_confirmed_momentum",
  "data_requirements": ["funding", "open_interest"]
}
""".strip(),
        encoding="utf-8",
    )
    config = tmp_path / "local.toml"
    config.write_text(
        f"""
data_lake_root = "{tmp_path / 'lake'}"
download_dir = "{tmp_path / 'downloads'}"
proposal = "{proposal}"
exchanges = ["binance"]
market_types = ["perp"]
symbols = ["BTCUSDT"]
lookback_days = 1
retention_days = 180
""".strip(),
        encoding="utf-8",
    )

    plan = build_daily_ingest_plan(
        config_path=config,
        current_date=datetime(2026, 6, 10, tzinfo=timezone.utc).date(),
        python_bin="py",
    )

    assert plan["config"]["retention_days"] == 180
    assert plan["ingest_window"] == {
        "start_date": "2026-06-09",
        "end_date": "2026-06-09",
    }
    assert plan["local_plan"]["command_plan"]["supported_count"] == 2
    assert all(
        command["command"][0] == "py"
        for command in plan["local_plan"]["command_plan"]["commands"]
    )


def test_execute_command_plan_accepts_daily_ingest_plan_wrapper(tmp_path) -> None:
    state_path = tmp_path / "jobs.json"
    daily_plan = {
        "kind": "daily_ingest_plan",
        "local_plan": {
            "command_plan": {
                "commands": [
                    {
                        "job_id": "ok-job",
                        "event_type": "funding",
                        "supported": True,
                        "risk_tier": "low",
                        "requires_confirmation": False,
                        "command": [sys.executable, "-c", "print('ok')"],
                    }
                ]
            }
        },
    }

    result = execute_command_plan(daily_plan, state_path=state_path)

    assert result["executed_count"] == 1
    assert result["failed_count"] == 0
    assert result["results"][0]["status"] == "succeeded"
