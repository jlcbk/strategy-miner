from packages.agent_interface import (
    AgentAction,
    AgentGuardrails,
    ResearchReport,
    WorkflowStage,
    available_tools,
    next_allowed_stages,
    run_tool,
)


def test_research_report_artifact_is_machine_readable() -> None:
    report = ResearchReport(
        title="Funding 策略观察",
        created_by="codex",
        summary="正 funding 可以构成候选 carry 机会。",
        source_urls=["https://example.com/research"],
        claims=["资金费率显著高于交易成本时可能存在机会"],
        failure_modes=["拥挤交易会压缩收益"],
    )

    data = report.to_dict()

    assert data["kind"] == "research_report"
    assert data["created_by"] == "codex"
    assert data["source_urls"] == ["https://example.com/research"]


def test_agent_guardrails_block_live_trading_surfaces() -> None:
    guardrails = AgentGuardrails()

    order_decision = guardrails.check_action(AgentAction.PLACE_ORDER)
    deploy_decision = guardrails.check_action(AgentAction.AUTO_DEPLOY_STRATEGY)
    report_decision = guardrails.check_action(AgentAction.CREATE_RESEARCH_REPORT)

    assert not order_decision.allowed
    assert "下单" in order_decision.reason
    assert not deploy_decision.allowed
    assert report_decision.allowed


def test_agent_guardrails_detect_blocked_candidate_files() -> None:
    issues = AgentGuardrails().validate_candidate_files(
        ["packages/strategies/candidate.py", "configs/production/strategies.toml"]
    )

    assert issues == ["候选文件触及受限路径：configs/production/strategies.toml"]


def test_workflow_transitions_are_explicit() -> None:
    assert next_allowed_stages(WorkflowStage.RESEARCH) == {WorkflowStage.PROPOSAL}
    assert WorkflowStage.REPLAY in next_allowed_stages("fixture_test")


def test_agent_tools_return_json_ready_payloads() -> None:
    tools = available_tools()
    assert {tool["name"] for tool in tools} == {
        "list_strategies",
        "check_guardrail",
        "rank_strategy_candidates",
        "plan_strategy_validation",
        "check_data_coverage",
        "generate_data_collection_jobs",
        "plan_data_collection_commands",
    }

    result = run_tool("check_guardrail", {"action": "place_order"})
    assert not result.ok
    assert result.payload["allowed"] is False

    strategies = run_tool("list_strategies")
    assert strategies.ok
    assert len(strategies.payload["strategies"]) == 4


def test_plan_data_collection_commands_tool_maps_jobs_to_collector_cli() -> None:
    result = run_tool(
        "plan_data_collection_commands",
        {
            "current_date": "2026-06-09",
            "data_lake_root": ".data/lake",
            "download_dir": "var/downloads",
            "jobs": [
                {
                    "id": "mark-job",
                    "exchange": "binance",
                    "market_type": "perp",
                    "symbol": "BTCUSDT",
                    "event_type": "mark",
                    "start_ts": "2026-06-08T00:00:00+00:00",
                    "end_ts": "2026-06-09T00:00:00+00:00",
                },
                {
                    "id": "oi-old-job",
                    "exchange": "binance",
                    "market_type": "perp",
                    "symbol": "BTCUSDT",
                    "event_type": "open_interest",
                    "start_ts": "2024-01-01T00:00:00+00:00",
                    "end_ts": "2024-01-02T00:00:00+00:00",
                },
            ],
        },
    )

    assert result.ok
    plan = result.payload["command_plan"]
    assert plan["supported_count"] == 1
    assert plan["blocked_count"] == 1
    assert plan["risk_counts"] == {"medium": 1, "low": 1}
    assert plan["commands"][0]["command"] == [
        "python3",
        "-m",
        "apps.collector.main",
        "historical-mark",
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
        "--download-dir",
        "var/downloads",
    ]
    assert plan["commands"][0]["risk_tier"] == "medium"
    assert plan["commands"][0]["requires_confirmation"] is False
    assert plan["commands"][0]["execution_group"] == "archive_mark"
    assert plan["commands"][1]["supported"] is False
    assert plan["commands"][1]["risk_tier"] == "low"
    assert plan["commands"][1]["requires_confirmation"] is False
    assert "最近约 1 个月" in plan["commands"][1]["reason"]


def test_rank_strategy_candidates_tool_prioritizes_validation_ready_candidate() -> None:
    payload = {
        "candidates": [
            {
                "proposal": {
                    "kind": "strategy_proposal",
                    "title": "Funding carry",
                    "created_by": "codex",
                    "strategy_name": "funding_carry_top_perps",
                    "hypothesis": "正 funding 扣除成本后存在 carry 机会。",
                    "data_requirements": ["funding", "mark_price", "trades"],
                    "test_plan": ["按周回放 BTC/ETH/SOL perp"],
                    "risk_controls": ["限制单交易所敞口", "过滤极端波动窗口"],
                },
                "research_report": {
                    "failure_modes": ["拥挤交易压缩收益", "剧烈波动导致对冲失效"],
                },
                "scores": {
                    "verifiability": 5,
                    "data_availability": 5,
                    "capacity_potential": 4,
                    "cost_robustness": 4,
                    "overfit_resilience": 4,
                    "implementation_simplicity": 5,
                },
            },
            {
                "proposal": {
                    "kind": "strategy_proposal",
                    "title": "Narrative rotation",
                    "created_by": "codex",
                    "strategy_name": "narrative_rotation",
                    "hypothesis": "热点叙事可能带来短期动量。",
                    "data_requirements": [],
                    "test_plan": [],
                    "risk_controls": [],
                },
                "scores": {
                    "verifiability": 2,
                    "data_availability": 1,
                    "capacity_potential": 3,
                    "cost_robustness": 2,
                    "overfit_resilience": 1,
                    "implementation_simplicity": 2,
                },
            },
        ]
    }

    result = run_tool("rank_strategy_candidates", payload)

    assert result.ok
    ranked = result.payload["ranked_candidates"]
    assert ranked[0]["strategy_name"] == "funding_carry_top_perps"
    assert ranked[0]["recommended_status"] == "queued_for_validation"
    assert ranked[0]["missing_fields"] == []
    assert ranked[1]["strategy_name"] == "narrative_rotation"
    assert "proposal.data_requirements" in ranked[1]["missing_fields"]


def test_rank_strategy_candidates_tool_keeps_missing_failure_modes_for_review() -> None:
    result = run_tool(
        "rank_strategy_candidates",
        {
            "candidates": [
                {
                    "proposal": {
                        "kind": "strategy_proposal",
                        "title": "Basis",
                        "created_by": "codex",
                        "strategy_name": "calendar_basis",
                        "hypothesis": "交割合约和永续合约价差回归。",
                        "data_requirements": ["future", "perp", "mark_price"],
                        "test_plan": ["跨到期日回放"],
                        "risk_controls": ["限制到期日前窗口"],
                    },
                    "scores": {
                        "verifiability": 5,
                        "data_availability": 5,
                        "capacity_potential": 4,
                        "cost_robustness": 4,
                        "overfit_resilience": 4,
                        "implementation_simplicity": 5,
                    },
                }
            ]
        },
    )

    ranked = result.payload["ranked_candidates"]
    assert result.ok
    assert ranked[0]["recommended_status"] == "needs_human_review"
    assert ranked[0]["missing_fields"] == ["failure_modes"]


def test_plan_strategy_validation_marks_derivable_candles_ready_for_fixture() -> None:
    result = run_tool(
        "plan_strategy_validation",
        {
            "proposal": {
                "strategy_name": "funding_carry_vol_filter",
                "data_requirements": ["funding", "mark_price", "spot_candles", "fees"],
            },
            "symbols": ["BTCUSDT"],
            "exchanges": ["binance"],
        },
    )

    assert result.ok
    plan = result.payload["validation_plan"]
    assert plan["readiness"] == "ready_for_fixture"
    assert plan["fixture_scope"] == {"symbols": ["BTCUSDT"], "exchanges": ["binance"]}
    statuses = {
        item["normalized_requirement"]: item["status"]
        for item in plan["requirement_plans"]
    }
    assert statuses["funding"] == "covered"
    assert statuses["spot_candles"] == "derivable"


def test_plan_strategy_validation_covers_open_interest_model() -> None:
    result = run_tool(
        "plan_strategy_validation",
        {
            "proposal": {
                "strategy_name": "oi_confirmed_momentum",
                "data_requirements": ["open_interest", "candles", "funding"],
            }
        },
    )

    assert result.ok
    plan = result.payload["validation_plan"]
    assert plan["readiness"] == "ready_for_fixture"
    open_interest = [
        item for item in plan["requirement_plans"]
        if item["normalized_requirement"] == "open_interest"
    ]
    assert open_interest[0]["status"] == "covered"
    assert open_interest[0]["event_types"] == ["open_interest"]


def test_plan_strategy_validation_requires_orderbook_collection_policy() -> None:
    result = run_tool(
        "plan_strategy_validation",
        {
            "proposal": {
                "strategy_name": "orderbook_imbalance_filter",
                "data_requirements": ["orderbook", "trades", "fees"],
            }
        },
    )

    assert result.ok
    plan = result.payload["validation_plan"]
    assert plan["readiness"] == "needs_data_collection_plan"
    orderbook = [
        item for item in plan["requirement_plans"]
        if item["normalized_requirement"] == "orderbook"
    ]
    assert orderbook[0]["status"] == "needs_collection_policy"


def test_plan_strategy_validation_normalizes_depth_volume_requirement() -> None:
    result = run_tool(
        "plan_strategy_validation",
        {
            "proposal": {
                "strategy_name": "cross_exchange_funding_dispersion",
                "data_requirements": ["funding", "depth / volume"],
            }
        },
    )

    assert result.ok
    plan = result.payload["validation_plan"]
    assert plan["readiness"] == "needs_data_collection_plan"
    depth_volume = [
        item for item in plan["requirement_plans"]
        if item["normalized_requirement"] == "depth_volume"
    ]
    assert depth_volume[0]["event_types"] == ["orderbook", "trade"]
