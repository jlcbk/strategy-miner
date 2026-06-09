from datetime import datetime, timezone
from decimal import Decimal

from packages.data_lake import (
    DataLakeReader,
    DataLakeWriter,
    check_data_coverage,
    generate_data_collection_jobs,
)
from packages.data_lake.collection_commands import plan_data_collection_commands
from packages.normalization import (
    FundingPayload,
    MarketEvent,
    MarkPricePayload,
    OrderBookPayload,
    PriceLevel,
)
from packages.replay import ReplayEngine
from packages.strategies import CrossExchangeSpreadStrategy


def _book(exchange: str, bid: str, ask: str) -> MarketEvent:
    return MarketEvent(
        exchange=exchange,
        market_type="spot",
        symbol="BTC-USDT",
        base_asset="BTC",
        quote_asset="USDT",
        event_type="orderbook",
        exchange_ts=datetime(2024, 1, 1, 0, 0, 0, tzinfo=timezone.utc),
        local_ts=datetime(2024, 1, 1, 0, 0, 1, tzinfo=timezone.utc),
        source="unit-test",
        sequence_id=f"{exchange}-1",
        payload=OrderBookPayload(
            bids=(PriceLevel(bid, "1"),),
            asks=(PriceLevel(ask, "1"),),
        ),
    )


def test_data_lake_round_trip_and_replay(tmp_path) -> None:
    events = [_book("binance", bid="100", ask="101"), _book("bybit", bid="104", ask="105")]
    writer = DataLakeWriter(tmp_path, preferred_format="jsonl")
    paths = writer.write_events(events)

    assert len(paths) == 2
    assert all(path.exists() for path in paths)

    replay = ReplayEngine(DataLakeReader(tmp_path)).replay(
        CrossExchangeSpreadStrategy(
            notional_usd=Decimal("100"),
            taker_fee_bps=Decimal("0"),
            slippage_bps=Decimal("0"),
        )
    )

    assert replay.event_count == 2
    assert replay.opportunity_count == 1
    opportunity = replay.opportunities[0]
    assert opportunity.legs[0].exchange == "binance"
    assert opportunity.legs[1].exchange == "bybit"
    assert opportunity.net_edge_usd > 0


def test_data_coverage_reports_missing_and_present_partitions(tmp_path) -> None:
    proposal = {
        "strategy_name": "funding_carry_vol_filter",
        "data_requirements": ["funding", "mark_price"],
    }
    missing = check_data_coverage(
        root=tmp_path,
        proposal=proposal,
        exchanges=["binance"],
        market_types=["perp"],
        symbols=["BTCUSDT"],
        start_date=datetime(2024, 1, 1, tzinfo=timezone.utc).date(),
        end_date=datetime(2024, 1, 1, tzinfo=timezone.utc).date(),
    )

    assert not missing.ready
    assert missing.covered_count == 0
    assert missing.required_count == 2
    assert {item.event_type for item in missing.missing_items} == {"funding", "mark"}

    DataLakeWriter(tmp_path, preferred_format="jsonl").write_events(
        [
            MarketEvent(
                exchange="binance",
                market_type="perp",
                symbol="BTC-USDT",
                base_asset="BTC",
                quote_asset="USDT",
                event_type="funding",
                exchange_ts=datetime(2024, 1, 1, tzinfo=timezone.utc),
                local_ts=datetime(2024, 1, 1, tzinfo=timezone.utc),
                source="unit-test",
                sequence_id="funding-1",
                payload=FundingPayload(rate="0.001"),
            ),
            MarketEvent(
                exchange="binance",
                market_type="perp",
                symbol="BTC-USDT",
                base_asset="BTC",
                quote_asset="USDT",
                event_type="mark",
                exchange_ts=datetime(2024, 1, 1, tzinfo=timezone.utc),
                local_ts=datetime(2024, 1, 1, tzinfo=timezone.utc),
                source="unit-test",
                sequence_id="mark-1",
                payload=MarkPricePayload(mark_price="100"),
            ),
        ]
    )
    covered = check_data_coverage(
        root=tmp_path,
        proposal=proposal,
        exchanges=["binance"],
        market_types=["perp"],
        symbols=["BTCUSDT"],
        start_date=datetime(2024, 1, 1, tzinfo=timezone.utc).date(),
        end_date=datetime(2024, 1, 1, tzinfo=timezone.utc).date(),
    )

    assert covered.ready
    assert covered.covered_count == 2
    assert covered.missing_items == []


def test_data_coverage_scopes_spot_candles_to_spot_market(tmp_path) -> None:
    proposal = {
        "strategy_name": "funding_carry_vol_filter",
        "data_requirements": ["funding", "spot_candles"],
    }

    report = check_data_coverage(
        root=tmp_path,
        proposal=proposal,
        exchanges=["binance"],
        market_types=["spot", "perp"],
        symbols=["BTCUSDT"],
        start_date=datetime(2024, 1, 1, tzinfo=timezone.utc).date(),
        end_date=datetime(2024, 1, 1, tzinfo=timezone.utc).date(),
    )

    requirements = {
        (item.normalized_requirement, item.market_type, item.event_type)
        for item in report.missing_items
    }

    assert ("spot_candles", "spot", "trade") in requirements
    assert ("spot_candles", "perp", "trade") not in requirements
    assert ("funding", "perp", "funding") in requirements
    assert ("funding", "spot", "funding") not in requirements


def test_data_coverage_scopes_mark_index_price_to_derivatives(tmp_path) -> None:
    proposal = {
        "strategy_name": "funding_carry_vol_filter",
        "data_requirements": ["mark_index_price"],
    }

    report = check_data_coverage(
        root=tmp_path,
        proposal=proposal,
        exchanges=["binance"],
        market_types=["spot", "perp", "future"],
        symbols=["BTCUSDT"],
        start_date=datetime(2024, 1, 1, tzinfo=timezone.utc).date(),
        end_date=datetime(2024, 1, 1, tzinfo=timezone.utc).date(),
    )

    requirements = {
        (item.market_type, item.event_type)
        for item in report.missing_items
    }

    assert requirements == {
        ("perp", "mark"),
        ("perp", "index"),
        ("future", "mark"),
        ("future", "index"),
    }


def test_data_coverage_expands_depth_volume_to_orderbook_and_trade(tmp_path) -> None:
    proposal = {
        "strategy_name": "cross_exchange_funding_dispersion",
        "data_requirements": ["depth_volume"],
    }

    report = check_data_coverage(
        root=tmp_path,
        proposal=proposal,
        exchanges=["binance"],
        market_types=["perp"],
        symbols=["BTCUSDT"],
        start_date=datetime(2024, 1, 1, tzinfo=timezone.utc).date(),
        end_date=datetime(2024, 1, 1, tzinfo=timezone.utc).date(),
    )

    assert not report.ready
    assert report.unsupported_requirements == []
    assert report.required_count == 2
    assert {
        (item.normalized_requirement, item.event_type)
        for item in report.missing_items
    } == {
        ("depth_volume", "orderbook"),
        ("depth_volume", "trade"),
    }


def test_generate_data_collection_jobs_from_missing_partitions(tmp_path) -> None:
    proposal = {
        "strategy_name": "oi_confirmed_momentum",
        "data_requirements": ["open_interest", "funding"],
    }

    plan = generate_data_collection_jobs(
        root=tmp_path,
        proposal=proposal,
        exchanges=["binance"],
        market_types=["perp"],
        symbols=["BTCUSDT"],
        start_date=datetime(2024, 1, 1, tzinfo=timezone.utc).date(),
        end_date=datetime(2024, 1, 1, tzinfo=timezone.utc).date(),
    )
    repeated = generate_data_collection_jobs(
        root=tmp_path,
        proposal=proposal,
        exchanges=["binance"],
        market_types=["perp"],
        symbols=["BTCUSDT"],
        start_date=datetime(2024, 1, 1, tzinfo=timezone.utc).date(),
        end_date=datetime(2024, 1, 1, tzinfo=timezone.utc).date(),
    )

    assert len(plan.jobs) == 2
    assert [job.id for job in plan.jobs] == [job.id for job in repeated.jobs]
    assert {job.event_type for job in plan.jobs} == {"funding", "open_interest"}
    assert plan.jobs[0].start_ts == "2024-01-01T00:00:00+00:00"
    assert plan.jobs[0].end_ts == "2024-01-02T00:00:00+00:00"
    assert plan.jobs[0].status == "queued"


def test_generate_data_collection_jobs_deduplicates_physical_partitions(tmp_path) -> None:
    proposal = {
        "strategy_name": "oi_confirmed_momentum",
        "data_requirements": ["perp_mark_price", "perp_candles"],
    }

    plan = generate_data_collection_jobs(
        root=tmp_path,
        proposal=proposal,
        exchanges=["binance"],
        market_types=["perp"],
        symbols=["BTCUSDT"],
        start_date=datetime(2024, 1, 1, tzinfo=timezone.utc).date(),
        end_date=datetime(2024, 1, 1, tzinfo=timezone.utc).date(),
    )

    assert [job.event_type for job in plan.jobs] == ["mark", "trade"]
    mark_job = plan.jobs[0]
    assert mark_job.details["normalized_requirements"] == ["perp_mark_price"]
    trade_job = plan.jobs[1]
    assert trade_job.details["normalized_requirements"] == ["perp_candles"]


def test_plan_data_collection_commands_marks_supported_and_blocked_jobs() -> None:
    plan = plan_data_collection_commands(
        current_date=datetime(2026, 6, 9, tzinfo=timezone.utc).date(),
        jobs=[
            {
                "id": "trade-job",
                "exchange": "bybit",
                "market_type": "perp",
                "symbol": "BTCUSDT",
                "event_type": "trade",
                "start_ts": "2026-06-08T00:00:00+00:00",
                "end_ts": "2026-06-09T00:00:00+00:00",
            },
            {
                "id": "funding-job",
                "exchange": "okx",
                "market_type": "perp",
                "symbol": "BTCUSDT",
                "event_type": "funding",
                "start_ts": "2026-06-08T00:00:00+00:00",
                "end_ts": "2026-06-09T00:00:00+00:00",
            },
        ],
    )

    assert plan.supported_count == 1
    assert plan.blocked_count == 1
    assert plan.risk_counts == {"high": 1, "low": 1}
    assert plan.commands[0].command[:4] == [
        "python3",
        "-m",
        "apps.collector.main",
        "historical-trades",
    ]
    assert plan.commands[0].risk_tier == "high"
    assert plan.commands[0].requires_confirmation is True
    assert plan.commands[0].execution_group == "archive_trade"
    assert plan.commands[1].supported is False
    assert plan.commands[1].risk_tier == "low"
    assert plan.commands[1].requires_confirmation is False
    assert plan.commands[1].reason == "okx funding collector 尚未接入"


def test_plan_data_collection_commands_marks_orderbook_as_high_risk_blocked_job() -> None:
    plan = plan_data_collection_commands(
        current_date=datetime(2026, 6, 9, tzinfo=timezone.utc).date(),
        jobs=[
            {
                "id": "orderbook-job",
                "exchange": "binance",
                "market_type": "perp",
                "symbol": "BTCUSDT",
                "event_type": "orderbook",
                "start_ts": "2026-06-08T00:00:00+00:00",
                "end_ts": "2026-06-09T00:00:00+00:00",
            },
        ],
    )

    assert plan.supported_count == 0
    assert plan.blocked_count == 1
    assert plan.risk_counts == {"high": 1}
    assert plan.commands[0].supported is False
    assert plan.commands[0].risk_tier == "high"
    assert plan.commands[0].requires_confirmation is True
    assert plan.commands[0].execution_group == "stream_orderbook"
    assert "不能回补历史 orderbook 分区" in plan.commands[0].reason


def test_plan_data_collection_commands_supports_current_binance_orderbook_snapshot() -> None:
    plan = plan_data_collection_commands(
        current_date=datetime(2026, 6, 9, tzinfo=timezone.utc).date(),
        jobs=[
            {
                "id": "orderbook-job",
                "exchange": "binance",
                "market_type": "perp",
                "symbol": "BTCUSDT",
                "event_type": "orderbook",
                "start_ts": "2026-06-09T00:00:00+00:00",
                "end_ts": "2026-06-10T00:00:00+00:00",
            },
        ],
    )

    assert plan.supported_count == 1
    assert plan.blocked_count == 0
    assert plan.risk_counts == {"high": 1}
    assert plan.commands[0].command == [
        "python3",
        "-m",
        "apps.collector.main",
        "orderbook-snapshot",
        "--exchange",
        "binance",
        "--market-type",
        "perp",
        "--symbol",
        "BTCUSDT",
        "--day",
        "2026-06-09",
        "--data-lake-root",
        ".data/lake",
        "--limit",
        "20",
    ]
    assert plan.commands[0].risk_tier == "high"
    assert plan.commands[0].requires_confirmation is True
    assert plan.commands[0].execution_group == "stream_orderbook"


def test_plan_data_collection_commands_supports_current_binance_instrument_snapshot() -> None:
    plan = plan_data_collection_commands(
        current_date=datetime(2026, 6, 9, tzinfo=timezone.utc).date(),
        jobs=[
            {
                "id": "instrument-job",
                "exchange": "binance",
                "market_type": "perp",
                "symbol": "BTCUSDT",
                "event_type": "instrument",
                "start_ts": "2026-06-09T00:00:00+00:00",
                "end_ts": "2026-06-10T00:00:00+00:00",
            },
        ],
    )

    assert plan.supported_count == 1
    assert plan.blocked_count == 0
    assert plan.risk_counts == {"low": 1}
    assert plan.commands[0].command == [
        "python3",
        "-m",
        "apps.collector.main",
        "instrument-snapshot",
        "--exchange",
        "binance",
        "--market-type",
        "perp",
        "--symbol",
        "BTCUSDT",
        "--day",
        "2026-06-09",
        "--data-lake-root",
        ".data/lake",
    ]
    assert plan.commands[0].requires_confirmation is False
    assert plan.commands[0].execution_group == "metadata_snapshot"


def test_plan_data_collection_commands_supports_binance_index_jobs() -> None:
    plan = plan_data_collection_commands(
        current_date=datetime(2026, 6, 9, tzinfo=timezone.utc).date(),
        jobs=[
            {
                "id": "index-job",
                "exchange": "binance",
                "market_type": "perp",
                "symbol": "BTCUSDT",
                "event_type": "index",
                "start_ts": "2026-06-08T00:00:00+00:00",
                "end_ts": "2026-06-09T00:00:00+00:00",
            },
        ],
    )

    assert plan.supported_count == 1
    assert plan.blocked_count == 0
    assert plan.risk_counts == {"medium": 1}
    assert plan.commands[0].command == [
        "python3",
        "-m",
        "apps.collector.main",
        "historical-index",
        "--exchange",
        "binance",
        "--market-type",
        "perp",
        "--symbol",
        "BTCUSDT",
        "--day",
        "2026-06-08",
        "--data-lake-root",
        ".data/lake",
        "--interval",
        "1m",
        "--limit",
        "1500",
    ]
    assert plan.commands[0].requires_confirmation is False
    assert plan.commands[0].execution_group == "archive_index"


def test_plan_data_collection_commands_supports_fee_assumption_jobs() -> None:
    plan = plan_data_collection_commands(
        current_date=datetime(2026, 6, 9, tzinfo=timezone.utc).date(),
        jobs=[
            {
                "id": "fee-job",
                "exchange": "binance",
                "market_type": "perp",
                "symbol": "BTCUSDT",
                "event_type": "fee",
                "start_ts": "2026-06-08T00:00:00+00:00",
                "end_ts": "2026-06-09T00:00:00+00:00",
            },
        ],
    )

    assert plan.supported_count == 1
    assert plan.blocked_count == 0
    assert plan.risk_counts == {"low": 1}
    assert plan.commands[0].command == [
        "python3",
        "-m",
        "apps.collector.main",
        "fee-assumption",
        "--exchange",
        "binance",
        "--market-type",
        "perp",
        "--symbol",
        "BTCUSDT",
        "--day",
        "2026-06-08",
        "--data-lake-root",
        ".data/lake",
        "--maker-bps",
        "10",
        "--taker-bps",
        "10",
        "--fee-tier",
        "conservative_manual",
    ]
    assert plan.commands[0].requires_confirmation is False
    assert plan.commands[0].execution_group == "manual_assumption"


def test_plan_data_collection_commands_blocks_historical_instrument_snapshot() -> None:
    plan = plan_data_collection_commands(
        current_date=datetime(2026, 6, 9, tzinfo=timezone.utc).date(),
        jobs=[
            {
                "id": "instrument-job",
                "exchange": "binance",
                "market_type": "perp",
                "symbol": "BTCUSDT",
                "event_type": "instrument",
                "start_ts": "2026-06-08T00:00:00+00:00",
                "end_ts": "2026-06-09T00:00:00+00:00",
            },
        ],
    )

    assert plan.supported_count == 0
    assert plan.blocked_count == 1
    assert plan.risk_counts == {"low": 1}
    assert plan.commands[0].requires_confirmation is False
    assert "不能回补历史 instrument 分区" in plan.commands[0].reason


def test_plan_data_collection_commands_supports_bybit_low_and_medium_risk_jobs() -> None:
    plan = plan_data_collection_commands(
        current_date=datetime(2026, 6, 9, tzinfo=timezone.utc).date(),
        jobs=[
            {
                "id": "oi-job",
                "exchange": "bybit",
                "market_type": "perp",
                "symbol": "BTCUSDT",
                "event_type": "open_interest",
                "start_ts": "2026-06-08T00:00:00+00:00",
                "end_ts": "2026-06-09T00:00:00+00:00",
            },
            {
                "id": "funding-job",
                "exchange": "bybit",
                "market_type": "perp",
                "symbol": "BTCUSDT",
                "event_type": "funding",
                "start_ts": "2026-06-08T00:00:00+00:00",
                "end_ts": "2026-06-09T00:00:00+00:00",
            },
            {
                "id": "mark-job",
                "exchange": "bybit",
                "market_type": "perp",
                "symbol": "BTCUSDT",
                "event_type": "mark",
                "start_ts": "2026-06-08T00:00:00+00:00",
                "end_ts": "2026-06-09T00:00:00+00:00",
            },
        ],
    )

    assert plan.supported_count == 3
    assert plan.blocked_count == 0
    assert plan.risk_counts == {"low": 2, "medium": 1}
    assert [command.command[3] for command in plan.commands] == [
        "open-interest",
        "funding",
        "historical-mark",
    ]
