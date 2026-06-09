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
    assert mark_job.details["normalized_requirements"] == [
        "perp_mark_price",
        "perp_candles",
    ]


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
