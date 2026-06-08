from __future__ import annotations

from dataclasses import dataclass


BLOCKED_ACTIONS = {
    "place_order",
    "cancel_order",
    "modify_order",
    "auto_deploy_strategy",
    "write_production_strategy_config",
    "enable_live_trading",
}


@dataclass(frozen=True)
class SafetyDecision:
    allowed: bool
    reason: str


class SafetyPolicy:
    def __init__(self, *, allow_ordering: bool = False, allow_auto_deploy: bool = False) -> None:
        self.allow_ordering = allow_ordering
        self.allow_auto_deploy = allow_auto_deploy

    def check(self, action: str) -> SafetyDecision:
        if action in {"place_order", "cancel_order", "modify_order", "enable_live_trading"}:
            if not self.allow_ordering:
                return SafetyDecision(False, "v1 禁止自动交易")
        if action in {"auto_deploy_strategy", "write_production_strategy_config"}:
            if not self.allow_auto_deploy:
                return SafetyDecision(False, "v1 禁止自动部署策略")
        return SafetyDecision(True, "允许执行")
