from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class AgentAction(str, Enum):
    CREATE_RESEARCH_REPORT = "create_research_report"
    CREATE_STRATEGY_PROPOSAL = "create_strategy_proposal"
    CREATE_CANDIDATE_EVALUATOR = "create_candidate_evaluator"
    RUN_TESTS = "run_tests"
    RUN_REPLAY = "run_replay"
    CREATE_PULL_REQUEST = "create_pull_request"
    WRITE_PRODUCTION_CONFIG = "write_production_config"
    PLACE_ORDER = "place_order"
    ENABLE_LIVE_TRADING = "enable_live_trading"
    AUTO_DEPLOY_STRATEGY = "auto_deploy_strategy"


@dataclass(frozen=True)
class GuardrailDecision:
    allowed: bool
    reason: str


class AgentGuardrails:
    def __init__(
        self,
        *,
        allow_production_config: bool = False,
        allow_ordering: bool = False,
        allow_auto_deploy: bool = False,
    ) -> None:
        self.allow_production_config = allow_production_config
        self.allow_ordering = allow_ordering
        self.allow_auto_deploy = allow_auto_deploy

    def check_action(self, action: AgentAction | str) -> GuardrailDecision:
        action = AgentAction(action)
        if action == AgentAction.WRITE_PRODUCTION_CONFIG and not self.allow_production_config:
            return GuardrailDecision(False, "agent 不能修改生产策略配置")
        if action in {AgentAction.PLACE_ORDER, AgentAction.ENABLE_LIVE_TRADING}:
            if not self.allow_ordering:
                return GuardrailDecision(False, "agent 不能触发下单或开启真实交易")
        if action == AgentAction.AUTO_DEPLOY_STRATEGY and not self.allow_auto_deploy:
            return GuardrailDecision(False, "agent 不能自动部署策略")
        return GuardrailDecision(True, "允许执行")

    def validate_candidate_files(self, files: list[str]) -> list[str]:
        issues: list[str] = []
        blocked_fragments = (
            "configs/production",
            "production/strategies",
            "live_trading",
            "order_router",
            "broker",
        )
        for file_path in files:
            lowered = file_path.lower()
            for fragment in blocked_fragments:
                if fragment in lowered:
                    issues.append(f"候选文件触及受限路径：{file_path}")
                    break
        return issues
