import json
from pathlib import Path


ARTIFACT_ROOTS = {
    "cross_exchange_funding_dispersion": Path(
        "artifacts/strategies/cross_exchange_funding_dispersion"
    ),
    "funding_carry_vol_filter": Path("artifacts/strategies/funding_carry_vol_filter"),
    "oi_confirmed_momentum": Path("artifacts/strategies/oi_confirmed_momentum"),
    "orderbook_imbalance_filter": Path("artifacts/strategies/orderbook_imbalance_filter"),
    "quarterly_basis_convergence": Path("artifacts/strategies/quarterly_basis_convergence"),
    "stablecoin_depeg_mean_reversion": Path(
        "artifacts/strategies/stablecoin_depeg_mean_reversion"
    ),
}
STRATEGY_QUEUE_PATH = Path("artifacts/strategies/strategy_queue.json")
MANUAL_GATE_SCHEMA_PATH = Path("schemas/manual_gate_checklist.schema.json")
DATA_COLLECTION_PLAN_SCHEMA_PATH = Path("schemas/data_collection_plan.schema.json")
METADATA_RESOLUTION_SCHEMA_PATH = Path("schemas/metadata_resolution_plan.schema.json")


def test_cross_exchange_funding_artifacts_are_machine_readable() -> None:
    report, proposal = _read_artifacts("cross_exchange_funding_dispersion")
    opportunity_report = _read_json(
        ARTIFACT_ROOTS["cross_exchange_funding_dispersion"] / "opportunity_report.json"
    )

    assert report["kind"] == "research_report"
    assert proposal["kind"] == "strategy_proposal"
    assert opportunity_report["kind"] == "opportunity_report"
    assert proposal["strategy_name"] == "cross_exchange_funding_dispersion"
    assert opportunity_report["strategy_name"] == "cross_exchange_funding_dispersion"
    assert report["failure_modes"]
    assert proposal["data_requirements"] == report["required_data"]
    assert "depth_volume" in proposal["data_requirements"]
    assert any("Operator fit" in note for note in report["evidence_notes"])
    assert "blocked-data fixture" in opportunity_report["title"]
    assert opportunity_report["opportunity_count"] == 0
    assert opportunity_report["opportunities"] == []
    assert (
        "artifacts/strategies/cross_exchange_funding_dispersion/opportunity_report.json"
        in proposal["candidate_files"]
    )


def test_cross_exchange_funding_artifacts_match_supported_schema_fields() -> None:
    report, proposal = _read_artifacts("cross_exchange_funding_dispersion")

    assert set(report) == {
        "kind",
        "title",
        "created_by",
        "created_at",
        "summary",
        "source_urls",
        "claims",
        "formulas",
        "cost_items",
        "failure_modes",
        "required_data",
        "evidence_notes",
    }
    assert set(proposal) == {
        "kind",
        "title",
        "created_by",
        "created_at",
        "strategy_name",
        "hypothesis",
        "evaluator_contract",
        "data_requirements",
        "test_plan",
        "risk_controls",
        "candidate_files",
    }


def test_cross_exchange_funding_opportunity_report_matches_supported_schema_fields() -> None:
    opportunity_report = _read_json(
        ARTIFACT_ROOTS["cross_exchange_funding_dispersion"] / "opportunity_report.json"
    )

    assert set(opportunity_report) == {
        "kind",
        "title",
        "created_by",
        "created_at",
        "strategy_name",
        "strategy_version",
        "data_window",
        "opportunity_count",
        "opportunities",
        "result_hash",
    }


def test_funding_carry_artifacts_are_machine_readable() -> None:
    report, proposal = _read_artifacts("funding_carry_vol_filter")
    opportunity_report = _read_json(
        ARTIFACT_ROOTS["funding_carry_vol_filter"] / "opportunity_report.json"
    )
    data_collection_plan = _read_json(
        ARTIFACT_ROOTS["funding_carry_vol_filter"] / "data_collection_plan.json"
    )
    metadata_resolution = _read_json(
        ARTIFACT_ROOTS["funding_carry_vol_filter"]
        / "instrument_metadata_resolution.json"
    )

    assert report["kind"] == "research_report"
    assert proposal["kind"] == "strategy_proposal"
    assert opportunity_report["kind"] == "opportunity_report"
    assert proposal["strategy_name"] == "funding_carry_vol_filter"
    assert opportunity_report["strategy_name"] == "funding_carry_vol_filter"
    assert proposal["data_requirements"] == report["required_data"]
    assert "funding" in proposal["data_requirements"]
    assert "mark_index_price" in proposal["data_requirements"]
    assert "spot_candles" in proposal["data_requirements"]
    assert "perp_candles" in proposal["data_requirements"]
    assert "instrument_metadata" in proposal["data_requirements"]
    assert any("Operator fit" in note for note in report["evidence_notes"])
    assert any("Fee boundary" in note for note in report["evidence_notes"])
    assert "deterministic fixture" in opportunity_report["title"]
    assert opportunity_report["opportunity_count"] == 1
    assert opportunity_report["opportunities"][0]["failure_modes"] == []
    assert opportunity_report["opportunities"][0]["metadata"]["recent_price_move_source"] == "trade"
    assert (
        "artifacts/strategies/funding_carry_vol_filter/data_collection_plan.json"
        in proposal["candidate_files"]
    )
    assert (
        "artifacts/strategies/funding_carry_vol_filter/instrument_metadata_resolution.json"
        in proposal["candidate_files"]
    )
    assert (
        "artifacts/strategies/funding_carry_vol_filter/opportunity_report.json"
        in proposal["candidate_files"]
    )
    assert data_collection_plan["kind"] == "data_collection_plan"
    assert data_collection_plan["strategy_name"] == "funding_carry_vol_filter"
    assert data_collection_plan["coverage"]["ready"] is False
    assert data_collection_plan["coverage"]["covered_count"] == 1
    assert data_collection_plan["coverage"]["required_count"] == 33
    assert data_collection_plan["job_summary"]["deduped_job_count"] == 26
    assert data_collection_plan["command_summary"]["supported_count"] == 20
    assert data_collection_plan["command_summary"]["blocked_count"] == 6
    assert data_collection_plan["command_summary"]["blocked_by_event_type"] == {
        "instrument": 6
    }
    assert (
        data_collection_plan["blocked_commands"][0]["resolution_plan"]
        == "artifacts/strategies/funding_carry_vol_filter/instrument_metadata_resolution.json"
    )
    assert "place orders" in data_collection_plan["safety_boundary"]
    assert metadata_resolution["kind"] == "metadata_resolution_plan"
    assert metadata_resolution["blocked_requirement"] == "instrument_metadata"
    assert len(metadata_resolution["blocked_partitions"]) == 6


def test_funding_carry_data_collection_plan_matches_supported_fields() -> None:
    data_collection_plan = _read_json(
        ARTIFACT_ROOTS["funding_carry_vol_filter"] / "data_collection_plan.json"
    )
    schema = _read_json(DATA_COLLECTION_PLAN_SCHEMA_PATH)

    assert set(data_collection_plan) == {
        "kind",
        "title",
        "created_by",
        "created_at",
        "strategy_name",
        "issue_number",
        "scope",
        "generated_from_tools",
        "coverage",
        "job_summary",
        "command_summary",
        "supported_command_templates",
        "blocked_commands",
        "next_actions",
        "safety_boundary",
    }
    assert schema["properties"]["kind"]["const"] == data_collection_plan["kind"]
    assert data_collection_plan["generated_from_tools"] == [
        "generate_data_collection_jobs",
        "plan_data_collection_commands",
    ]
    assert {
        template["execution_group"]
        for template in data_collection_plan["supported_command_templates"]
    } == {
        "small_rest",
        "archive_mark",
        "archive_index",
        "archive_trade",
        "manual_assumption",
    }
    assert data_collection_plan["blocked_commands"][0]["execution_group"] == (
        "metadata_snapshot"
    )


def test_funding_carry_metadata_resolution_plan_matches_supported_fields() -> None:
    metadata_resolution = _read_json(
        ARTIFACT_ROOTS["funding_carry_vol_filter"]
        / "instrument_metadata_resolution.json"
    )
    schema = _read_json(METADATA_RESOLUTION_SCHEMA_PATH)

    assert set(metadata_resolution) == {
        "kind",
        "title",
        "created_by",
        "created_at",
        "strategy_name",
        "issue_number",
        "blocked_requirement",
        "blocked_partitions",
        "blocker_reason",
        "accepted_resolution_paths",
        "manual_assumption_limits",
        "reject_if",
        "output_partition_contract",
        "next_actions",
        "safety_boundary",
    }
    assert schema["properties"]["kind"]["const"] == metadata_resolution["kind"]
    assert {
        path["id"] for path in metadata_resolution["accepted_resolution_paths"]
    } == {
        "official_dated_snapshot",
        "manual_static_metadata_assumption",
    }
    assert metadata_resolution["manual_assumption_limits"]["max_days_between_snapshot_and_replay"] == 1
    assert metadata_resolution["output_partition_contract"]["event_type"] == "instrument"
    assert (
        "instrument-assumption"
        in metadata_resolution["output_partition_contract"][
            "manual_assumption_command_template"
        ]
    )
    assert "production-ready" in metadata_resolution["safety_boundary"]


def test_funding_carry_opportunity_report_matches_supported_schema_fields() -> None:
    opportunity_report = _read_json(
        ARTIFACT_ROOTS["funding_carry_vol_filter"] / "opportunity_report.json"
    )

    assert set(opportunity_report) == {
        "kind",
        "title",
        "created_by",
        "created_at",
        "strategy_name",
        "strategy_version",
        "data_window",
        "opportunity_count",
        "opportunities",
        "result_hash",
    }


def test_quarterly_basis_artifacts_are_machine_readable() -> None:
    report, proposal = _read_artifacts("quarterly_basis_convergence")
    opportunity_report = _read_json(
        ARTIFACT_ROOTS["quarterly_basis_convergence"] / "opportunity_report.json"
    )

    assert report["kind"] == "research_report"
    assert proposal["kind"] == "strategy_proposal"
    assert opportunity_report["kind"] == "opportunity_report"
    assert proposal["strategy_name"] == "quarterly_basis_convergence"
    assert opportunity_report["strategy_name"] == "quarterly_basis_convergence"
    assert proposal["data_requirements"] == report["required_data"]
    assert "future_mark_price" in proposal["data_requirements"]
    assert "spot_candles" in proposal["data_requirements"]
    assert "instrument_metadata" in proposal["data_requirements"]
    assert "depth_volume" in proposal["data_requirements"]
    assert any("Operator fit" in note for note in report["evidence_notes"])
    assert any("Instrument boundary" in note for note in report["evidence_notes"])
    assert "deterministic fixture" in opportunity_report["title"]
    assert opportunity_report["opportunity_count"] == 1
    assert opportunity_report["opportunities"][0]["failure_modes"] == []
    assert opportunity_report["opportunities"][0]["metadata"]["annualized_basis"] == "0.3650"
    assert opportunity_report["opportunities"][0]["metadata"]["days_to_expiry"] == "30.00"
    assert (
        "artifacts/strategies/quarterly_basis_convergence/opportunity_report.json"
        in proposal["candidate_files"]
    )


def test_quarterly_basis_opportunity_report_matches_supported_schema_fields() -> None:
    opportunity_report = _read_json(
        ARTIFACT_ROOTS["quarterly_basis_convergence"] / "opportunity_report.json"
    )

    assert set(opportunity_report) == {
        "kind",
        "title",
        "created_by",
        "created_at",
        "strategy_name",
        "strategy_version",
        "data_window",
        "opportunity_count",
        "opportunities",
        "result_hash",
    }


def test_oi_confirmed_momentum_artifacts_are_machine_readable() -> None:
    report, proposal = _read_artifacts("oi_confirmed_momentum")
    opportunity_report = _read_json(
        ARTIFACT_ROOTS["oi_confirmed_momentum"] / "opportunity_report.json"
    )

    assert report["kind"] == "research_report"
    assert proposal["kind"] == "strategy_proposal"
    assert opportunity_report["kind"] == "opportunity_report"
    assert proposal["strategy_name"] == "oi_confirmed_momentum"
    assert opportunity_report["strategy_name"] == "oi_confirmed_momentum"
    assert proposal["data_requirements"] == report["required_data"]
    assert "open_interest" in proposal["data_requirements"]
    assert "perp_candles" in proposal["data_requirements"]
    assert "funding" in proposal["data_requirements"]
    assert "mark_price" in proposal["data_requirements"]
    assert any("Operator fit" in note for note in report["evidence_notes"])
    assert any("Venue boundary" in note for note in report["evidence_notes"])
    assert "deterministic fixture" in opportunity_report["title"]
    assert opportunity_report["opportunity_count"] == 1
    assert opportunity_report["opportunities"][0]["metadata"]["price_return_bps"] == "200.00"
    assert opportunity_report["opportunities"][0]["metadata"]["oi_change_pct"] == "6.00"
    assert opportunity_report["opportunities"][0]["failure_modes"] == [
        "requires_oi_venue_definition_before_validation"
    ]
    assert "packages/strategies/oi_momentum.py" in proposal["candidate_files"]
    assert (
        "artifacts/strategies/oi_confirmed_momentum/opportunity_report.json"
        in proposal["candidate_files"]
    )


def test_oi_confirmed_momentum_artifacts_match_supported_schema_fields() -> None:
    report, proposal = _read_artifacts("oi_confirmed_momentum")

    assert set(report) == {
        "kind",
        "title",
        "created_by",
        "created_at",
        "summary",
        "source_urls",
        "claims",
        "formulas",
        "cost_items",
        "failure_modes",
        "required_data",
        "evidence_notes",
    }
    assert set(proposal) == {
        "kind",
        "title",
        "created_by",
        "created_at",
        "strategy_name",
        "hypothesis",
        "evaluator_contract",
        "data_requirements",
        "test_plan",
        "risk_controls",
        "candidate_files",
    }


def test_oi_confirmed_momentum_opportunity_report_matches_supported_schema_fields() -> None:
    opportunity_report = _read_json(
        ARTIFACT_ROOTS["oi_confirmed_momentum"] / "opportunity_report.json"
    )

    assert set(opportunity_report) == {
        "kind",
        "title",
        "created_by",
        "created_at",
        "strategy_name",
        "strategy_version",
        "data_window",
        "opportunity_count",
        "opportunities",
        "result_hash",
    }


def test_orderbook_imbalance_filter_artifacts_are_machine_readable() -> None:
    report, proposal = _read_artifacts("orderbook_imbalance_filter")
    opportunity_report = _read_json(
        ARTIFACT_ROOTS["orderbook_imbalance_filter"] / "opportunity_report.json"
    )

    assert report["kind"] == "research_report"
    assert proposal["kind"] == "strategy_proposal"
    assert opportunity_report["kind"] == "opportunity_report"
    assert proposal["strategy_name"] == "orderbook_imbalance_filter"
    assert opportunity_report["strategy_name"] == "orderbook_imbalance_filter"
    assert proposal["data_requirements"] == report["required_data"]
    assert "orderbook" in proposal["data_requirements"]
    assert "trades" in proposal["data_requirements"]
    assert "fees" in proposal["data_requirements"]
    assert any("Operator fit" in note for note in report["evidence_notes"])
    assert any("Sampling policy" in note for note in report["evidence_notes"])
    assert "过滤器" in proposal["hypothesis"]
    assert "blocked-data fixture" in opportunity_report["title"]
    assert opportunity_report["opportunity_count"] == 0
    assert opportunity_report["opportunities"] == []
    assert not any("packages/strategies/" in path for path in proposal["candidate_files"])
    assert (
        "artifacts/strategies/orderbook_imbalance_filter/opportunity_report.json"
        in proposal["candidate_files"]
    )


def test_orderbook_imbalance_filter_artifacts_match_supported_schema_fields() -> None:
    report, proposal = _read_artifacts("orderbook_imbalance_filter")

    assert set(report) == {
        "kind",
        "title",
        "created_by",
        "created_at",
        "summary",
        "source_urls",
        "claims",
        "formulas",
        "cost_items",
        "failure_modes",
        "required_data",
        "evidence_notes",
    }
    assert set(proposal) == {
        "kind",
        "title",
        "created_by",
        "created_at",
        "strategy_name",
        "hypothesis",
        "evaluator_contract",
        "data_requirements",
        "test_plan",
        "risk_controls",
        "candidate_files",
    }


def test_orderbook_imbalance_filter_opportunity_report_matches_supported_schema_fields() -> None:
    opportunity_report = _read_json(
        ARTIFACT_ROOTS["orderbook_imbalance_filter"] / "opportunity_report.json"
    )

    assert set(opportunity_report) == {
        "kind",
        "title",
        "created_by",
        "created_at",
        "strategy_name",
        "strategy_version",
        "data_window",
        "opportunity_count",
        "opportunities",
        "result_hash",
    }


def test_stablecoin_depeg_artifacts_are_machine_readable() -> None:
    report, proposal = _read_artifacts("stablecoin_depeg_mean_reversion")
    opportunity_report = _read_json(
        ARTIFACT_ROOTS["stablecoin_depeg_mean_reversion"] / "opportunity_report.json"
    )
    checklist = _read_json(
        ARTIFACT_ROOTS["stablecoin_depeg_mean_reversion"] / "manual_status_checklist.json"
    )

    assert report["kind"] == "research_report"
    assert proposal["kind"] == "strategy_proposal"
    assert opportunity_report["kind"] == "opportunity_report"
    assert proposal["strategy_name"] == "stablecoin_depeg_mean_reversion"
    assert opportunity_report["strategy_name"] == "stablecoin_depeg_mean_reversion"
    assert proposal["data_requirements"] == report["required_data"]
    assert "spot_candles" in proposal["data_requirements"]
    assert "orderbook" in proposal["data_requirements"]
    assert "stablecoin_issuer_status" in proposal["data_requirements"]
    assert any("Operator fit" in note for note in report["evidence_notes"])
    assert any("Risk boundary" in note for note in report["evidence_notes"])
    assert "blocked-data fixture" in opportunity_report["title"]
    assert opportunity_report["opportunity_count"] == 0
    assert opportunity_report["opportunities"] == []
    assert checklist["kind"] == "manual_gate_checklist"
    assert checklist["gate_name"] == "manual_stablecoin_status_checklist"
    assert checklist["default_decision"] == "unknown"
    assert "pass" in checklist["decision_states"]
    assert "fail" in checklist["decision_states"]
    assert "unknown" in checklist["decision_states"]
    assert len(checklist["required_checks"]) == 5
    assert (
        "artifacts/strategies/stablecoin_depeg_mean_reversion/manual_status_checklist.json"
        in proposal["candidate_files"]
    )


def test_stablecoin_depeg_artifacts_match_supported_schema_fields() -> None:
    report, proposal = _read_artifacts("stablecoin_depeg_mean_reversion")
    opportunity_report = _read_json(
        ARTIFACT_ROOTS["stablecoin_depeg_mean_reversion"] / "opportunity_report.json"
    )

    assert set(report) == {
        "kind",
        "title",
        "created_by",
        "created_at",
        "summary",
        "source_urls",
        "claims",
        "formulas",
        "cost_items",
        "failure_modes",
        "required_data",
        "evidence_notes",
    }
    assert set(proposal) == {
        "kind",
        "title",
        "created_by",
        "created_at",
        "strategy_name",
        "hypothesis",
        "evaluator_contract",
        "data_requirements",
        "test_plan",
        "risk_controls",
        "candidate_files",
    }
    assert set(opportunity_report) == {
        "kind",
        "title",
        "created_by",
        "created_at",
        "strategy_name",
        "strategy_version",
        "data_window",
        "opportunity_count",
        "opportunities",
        "result_hash",
    }


def test_stablecoin_depeg_manual_checklist_matches_supported_fields() -> None:
    checklist = _read_json(
        ARTIFACT_ROOTS["stablecoin_depeg_mean_reversion"] / "manual_status_checklist.json"
    )
    schema = _read_json(MANUAL_GATE_SCHEMA_PATH)

    assert set(checklist) == {
        "kind",
        "title",
        "created_by",
        "created_at",
        "strategy_name",
        "gate_name",
        "decision_states",
        "default_decision",
        "blocking_rule",
        "scope_fields",
        "required_checks",
        "output_contract",
    }
    assert {check["id"] for check in checklist["required_checks"]} == {
        "issuer_public_status",
        "redemption_channel_status",
        "exchange_deposit_withdraw_status",
        "cross_venue_price_consistency",
        "operator_fit_confirmation",
    }
    assert checklist["output_contract"]["allowed_downstream_action"].startswith(
        "blocked_alert_only"
    )
    assert schema["properties"]["kind"]["const"] == checklist["kind"]


def test_strategy_queue_matches_artifact_inventory() -> None:
    queue = _read_json(STRATEGY_QUEUE_PATH)

    assert queue["kind"] == "strategy_queue"
    assert "production-ready" in queue["status_boundary"]
    strategies = queue["strategies"]
    strategy_names = {item["strategy_name"] for item in strategies}

    assert strategy_names == set(ARTIFACT_ROOTS)
    assert all(item["issue_status"] == "strategy:blocked-data" for item in strategies)
    assert all(item["coverage"]["ready"] is False for item in strategies)
    assert all(item["opportunity_count"] >= 0 for item in strategies)

    for item in strategies:
        artifact_root = Path(item["artifact_root"])
        assert artifact_root == ARTIFACT_ROOTS[item["strategy_name"]]
        assert (artifact_root / "research_report.json").exists()
        assert (artifact_root / "strategy_proposal.json").exists()
        assert (artifact_root / "opportunity_report.json").exists()

    funding = [
        item for item in strategies
        if item["strategy_name"] == "funding_carry_vol_filter"
    ][0]
    assert funding["has_data_collection_plan"] is True
    assert "instrument_metadata_resolution.json" in funding["next_action"]
    assert "evidence hash" in funding["next_action"]
    assert (
        ARTIFACT_ROOTS["funding_carry_vol_filter"] / "data_collection_plan.json"
    ).exists()

    stablecoin = [
        item for item in strategies
        if item["strategy_name"] == "stablecoin_depeg_mean_reversion"
    ][0]
    assert stablecoin["coverage"]["unsupported_requirements"] == []
    assert stablecoin["coverage"]["manual_requirements"] == [
        "manual_stablecoin_status_checklist"
    ]


def _read_artifacts(strategy_name: str) -> tuple[dict, dict]:
    root = ARTIFACT_ROOTS[strategy_name]
    return (
        _read_json(root / "research_report.json"),
        _read_json(root / "strategy_proposal.json"),
    )


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))
