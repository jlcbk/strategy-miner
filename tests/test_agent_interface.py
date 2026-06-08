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
    assert {tool["name"] for tool in tools} == {"list_strategies", "check_guardrail"}

    result = run_tool("check_guardrail", {"action": "place_order"})
    assert not result.ok
    assert result.payload["allowed"] is False

    strategies = run_tool("list_strategies")
    assert strategies.ok
    assert len(strategies.payload["strategies"]) == 3
