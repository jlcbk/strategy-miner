from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from packages.agent_interface.guardrails import AgentAction, AgentGuardrails
from packages.strategies import (
    CrossExchangeSpreadStrategy,
    FundingCarryStrategy,
    FuturesBasisStrategy,
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
    ]


def run_tool(name: str, payload: dict[str, Any] | None = None) -> ToolResult:
    payload = payload or {}
    if name == "list_strategies":
        strategies = [CrossExchangeSpreadStrategy(), FundingCarryStrategy(), FuturesBasisStrategy()]
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
    return ToolResult(ok=False, payload={}, message=f"未知工具：{name}")
