from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any

from packages.agent_interface.guardrails import AgentAction, AgentGuardrails
from packages.agent_interface.research_funnel import (
    candidate_from_payload,
    rank_strategy_candidates,
    scoring_contract,
)
from packages.agent_interface.validation_plan import (
    plan_strategy_validation,
    validation_planning_contract,
)
from packages.data_lake.coverage import check_data_coverage
from packages.strategies import (
    CrossExchangeSpreadStrategy,
    FundingCarryStrategy,
    FuturesBasisStrategy,
    OpenInterestMomentumStrategy,
)


@dataclass(frozen=True)
class ToolResult:
    ok: bool
    payload: dict[str, Any]
    message: str = ""


def available_tools() -> list[dict[str, Any]]:
    return [
        {
            "name": "list_strategies",
            "description": "列出当前内置策略及其 required_data。",
            "allowed_action": AgentAction.CREATE_STRATEGY_PROPOSAL.value,
        },
        {
            "name": "check_guardrail",
            "description": "检查某个 agent 动作是否被当前安全边界允许。",
            "allowed_action": AgentAction.CREATE_RESEARCH_REPORT.value,
        },
        {
            "name": "rank_strategy_candidates",
            "description": "按研究漏斗评分策略候选。",
            "allowed_action": AgentAction.CREATE_STRATEGY_PROPOSAL.value,
            "input_contract": {
                "candidates": "数组；每项包含 proposal、scores，可选 research_report",
                "scores": scoring_contract(),
                "limit": "可选；最多返回多少个候选",
            },
        },
        {
            "name": "plan_strategy_validation",
            "description": "检查 strategy_proposal 的数据需求是否可进入验证准备。",
            "allowed_action": AgentAction.CREATE_STRATEGY_PROPOSAL.value,
            "input_contract": validation_planning_contract(),
        },
        {
            "name": "check_data_coverage",
            "description": "检查 data lake 是否已有验证所需事件分区。",
            "allowed_action": AgentAction.CREATE_STRATEGY_PROPOSAL.value,
            "input_contract": {
                "required": [
                    "root",
                    "proposal",
                    "exchanges",
                    "market_types",
                    "symbols",
                    "start_date",
                    "end_date",
                ],
            },
        },
    ]


def run_tool(name: str, payload: dict[str, Any] | None = None) -> ToolResult:
    payload = payload or {}
    if name == "list_strategies":
        strategies = [
            CrossExchangeSpreadStrategy(),
            FundingCarryStrategy(),
            FuturesBasisStrategy(),
            OpenInterestMomentumStrategy(),
        ]
        return ToolResult(
            ok=True,
            payload={
                "strategies": [
                    {
                        "name": strategy.name,
                        "version": strategy.version,
                        "required_data": sorted(event.value for event in strategy.required_data()),
                    }
                    for strategy in strategies
                ]
            },
        )
    if name == "check_guardrail":
        action = payload.get("action")
        if not action:
            return ToolResult(ok=False, payload={}, message="缺少 action")
        decision = AgentGuardrails().check_action(action)
        return ToolResult(
            ok=decision.allowed,
            payload={"action": action, "allowed": decision.allowed, "reason": decision.reason},
            message=decision.reason,
        )
    if name == "rank_strategy_candidates":
        raw_candidates = payload.get("candidates")
        if not isinstance(raw_candidates, list) or not raw_candidates:
            return ToolResult(ok=False, payload={}, message="缺少 candidates 数组")
        try:
            candidates = [candidate_from_payload(candidate) for candidate in raw_candidates]
            limit = payload.get("limit")
            if limit is not None:
                limit = int(limit)
            ranks = rank_strategy_candidates(candidates, limit=limit)
        except (ValueError, ArithmeticError) as exc:
            return ToolResult(ok=False, payload={}, message=str(exc))
        return ToolResult(
            ok=True,
            payload={
                "ranked_candidates": [rank.to_dict() for rank in ranks],
                "scoring_contract": scoring_contract(),
            },
        )
    if name == "plan_strategy_validation":
        proposal = payload.get("proposal")
        symbols = payload.get("symbols")
        exchanges = payload.get("exchanges")
        if symbols is not None and not isinstance(symbols, list):
            return ToolResult(ok=False, payload={}, message="symbols 必须是数组")
        if exchanges is not None and not isinstance(exchanges, list):
            return ToolResult(ok=False, payload={}, message="exchanges 必须是数组")
        try:
            plan = plan_strategy_validation(
                proposal,
                symbols=symbols,
                exchanges=exchanges,
            )
        except ValueError as exc:
            return ToolResult(ok=False, payload={}, message=str(exc))
        return ToolResult(ok=True, payload={"validation_plan": plan.to_dict()})
    if name == "check_data_coverage":
        try:
            report = check_data_coverage(
                root=payload["root"],
                proposal=payload["proposal"],
                exchanges=_required_list(payload, "exchanges"),
                market_types=_required_list(payload, "market_types"),
                symbols=_required_list(payload, "symbols"),
                start_date=date.fromisoformat(str(payload["start_date"])),
                end_date=date.fromisoformat(str(payload["end_date"])),
            )
        except (KeyError, TypeError, ValueError) as exc:
            return ToolResult(ok=False, payload={}, message=str(exc))
        return ToolResult(ok=True, payload={"coverage": report.to_dict()})
    return ToolResult(ok=False, payload={}, message=f"未知工具：{name}")


def _required_list(payload: dict[str, Any], key: str) -> list[str]:
    value = payload[key]
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise ValueError(f"{key} 必须是字符串数组")
    return value
