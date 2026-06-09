from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any


class RequirementStatus(str, Enum):
    COVERED = "covered"
    DERIVABLE = "derivable"
    NEEDS_COLLECTION_POLICY = "needs_collection_policy"
    NEEDS_MANUAL_REVIEW = "needs_manual_review"
    UNSUPPORTED = "unsupported"


class ValidationReadiness(str, Enum):
    READY_FOR_FIXTURE = "ready_for_fixture"
    NEEDS_DATA_COLLECTION_PLAN = "needs_data_collection_plan"
    NEEDS_MANUAL_GATE = "needs_manual_gate"
    BLOCKED_MISSING_DATA_MODEL = "blocked_missing_data_model"


@dataclass(frozen=True)
class RequirementPlan:
    raw_requirement: str
    normalized_requirement: str
    status: RequirementStatus
    event_types: list[str]
    notes: list[str]
    next_actions: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "raw_requirement": self.raw_requirement,
            "normalized_requirement": self.normalized_requirement,
            "status": self.status.value,
            "event_types": self.event_types,
            "notes": self.notes,
            "next_actions": self.next_actions,
        }


@dataclass(frozen=True)
class ValidationPlan:
    strategy_name: str
    readiness: ValidationReadiness
    requirement_plans: list[RequirementPlan]
    fixture_scope: dict[str, list[str]]
    next_actions: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "strategy_name": self.strategy_name,
            "readiness": self.readiness.value,
            "requirement_plans": [plan.to_dict() for plan in self.requirement_plans],
            "fixture_scope": self.fixture_scope,
            "next_actions": self.next_actions,
        }


def plan_strategy_validation(
    proposal: dict[str, Any],
    *,
    symbols: list[str] | None = None,
    exchanges: list[str] | None = None,
) -> ValidationPlan:
    if not isinstance(proposal, dict):
        raise ValueError("proposal 必须是对象")

    raw_requirements = proposal.get("data_requirements")
    if not isinstance(raw_requirements, list) or not raw_requirements:
        raise ValueError("proposal.data_requirements 必须是非空数组")

    requirement_plans = [
        _plan_requirement(str(requirement)) for requirement in raw_requirements
    ]
    readiness = _readiness(requirement_plans)
    strategy_name = proposal.get("strategy_name") or proposal.get("title") or "未命名策略"
    return ValidationPlan(
        strategy_name=str(strategy_name),
        readiness=readiness,
        requirement_plans=requirement_plans,
        fixture_scope={
            "symbols": symbols or ["BTCUSDT", "ETHUSDT", "SOLUSDT"],
            "exchanges": exchanges or ["binance", "okx", "bybit", "bitget"],
        },
        next_actions=_next_actions(readiness, requirement_plans),
    )


def validation_planning_contract() -> dict[str, Any]:
    return {
        "required": ["proposal.data_requirements"],
        "optional": ["symbols", "exchanges"],
        "readiness": [
            readiness.value for readiness in ValidationReadiness
        ],
        "requirement_statuses": [
            status.value for status in RequirementStatus
        ],
    }


def _plan_requirement(raw: str) -> RequirementPlan:
    normalized = _normalize_requirement(raw)
    if normalized in _COVERED_REQUIREMENTS:
        event_types, notes = _COVERED_REQUIREMENTS[normalized]
        return RequirementPlan(
            raw_requirement=raw,
            normalized_requirement=normalized,
            status=RequirementStatus.COVERED,
            event_types=event_types,
            notes=notes,
            next_actions=[f"检查 data lake 是否已有 {normalized} 分区覆盖目标窗口"],
        )
    if normalized in _DERIVABLE_REQUIREMENTS:
        event_types, notes, action = _DERIVABLE_REQUIREMENTS[normalized]
        return RequirementPlan(
            raw_requirement=raw,
            normalized_requirement=normalized,
            status=RequirementStatus.DERIVABLE,
            event_types=event_types,
            notes=notes,
            next_actions=[action],
        )
    if normalized in _POLICY_REQUIREMENTS:
        event_types, notes, action = _POLICY_REQUIREMENTS[normalized]
        return RequirementPlan(
            raw_requirement=raw,
            normalized_requirement=normalized,
            status=RequirementStatus.NEEDS_COLLECTION_POLICY,
            event_types=event_types,
            notes=notes,
            next_actions=[action],
        )
    if normalized in _MANUAL_REQUIREMENTS:
        notes, action = _MANUAL_REQUIREMENTS[normalized]
        return RequirementPlan(
            raw_requirement=raw,
            normalized_requirement=normalized,
            status=RequirementStatus.NEEDS_MANUAL_REVIEW,
            event_types=[],
            notes=notes,
            next_actions=[action],
        )
    return RequirementPlan(
        raw_requirement=raw,
        normalized_requirement=normalized,
        status=RequirementStatus.UNSUPPORTED,
        event_types=[],
        notes=["当前 MarketEvent / EventType 未建模该数据需求"],
        next_actions=[f"新增 {normalized} 数据模型、连接器映射和覆盖率检查"],
    )


def _readiness(requirement_plans: list[RequirementPlan]) -> ValidationReadiness:
    statuses = {plan.status for plan in requirement_plans}
    if RequirementStatus.UNSUPPORTED in statuses:
        return ValidationReadiness.BLOCKED_MISSING_DATA_MODEL
    if RequirementStatus.NEEDS_MANUAL_REVIEW in statuses:
        return ValidationReadiness.NEEDS_MANUAL_GATE
    if RequirementStatus.NEEDS_COLLECTION_POLICY in statuses:
        return ValidationReadiness.NEEDS_DATA_COLLECTION_PLAN
    return ValidationReadiness.READY_FOR_FIXTURE


def _next_actions(
    readiness: ValidationReadiness,
    requirement_plans: list[RequirementPlan],
) -> list[str]:
    actions: list[str] = []
    for plan in requirement_plans:
        actions.extend(plan.next_actions)
    if readiness == ValidationReadiness.READY_FOR_FIXTURE:
        actions.append("创建最小 fixture，并用目标市场跑确定性单元测试")
    elif readiness == ValidationReadiness.NEEDS_DATA_COLLECTION_PLAN:
        actions.append("先确定采样频率、盘口深度、保留期和容量估计方法")
    elif readiness == ValidationReadiness.NEEDS_MANUAL_GATE:
        actions.append("人工门禁通过前，只允许生成 blocked alert，不进入自动验证队列")
    else:
        actions.append("补齐缺失数据模型前，不进入 validation_queue")
    return _dedupe(actions)


def _normalize_requirement(value: str) -> str:
    normalized = value.strip().lower()
    normalized = normalized.replace("/", " ")
    normalized = normalized.replace("-", "_")
    normalized = normalized.replace(" ", "_")
    while "__" in normalized:
        normalized = normalized.replace("__", "_")
    aliases = {
        "mark": "mark_price",
        "mark_index_price": "mark_index_price",
        "mark/index_price": "mark_index_price",
        "index": "index_price",
        "volume": "trades",
        "depth": "orderbook",
        "fee": "fees",
        "instrument": "instrument_metadata",
        "metadata": "instrument_metadata",
        "future_mark": "future_mark_price",
        "perp_mark": "perp_mark_price",
        "oi": "open_interest",
        "depth_volume": "depth_volume",
        "stablecoin_issuer_status": "manual_stablecoin_status_checklist",
        "issuer_status": "manual_stablecoin_status_checklist",
        "redemption_status": "manual_stablecoin_status_checklist",
        "stablecoin_redemption_status": "manual_stablecoin_status_checklist",
    }
    return aliases.get(normalized, normalized)


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    deduped: list[str] = []
    for value in values:
        if value not in seen:
            seen.add(value)
            deduped.append(value)
    return deduped


_COVERED_REQUIREMENTS: dict[str, tuple[list[str], list[str]]] = {
    "funding": (["funding"], ["EventType.FUNDING 已建模，主流 perp websocket 已有边界"]),
    "open_interest": (
        ["open_interest"],
        ["EventType.OPEN_INTEREST 已建模，四家交易所有 REST 采集边界"],
    ),
    "mark_price": (["mark"], ["EventType.MARK 已建模"]),
    "index_price": (["index"], ["EventType.INDEX 已建模"]),
    "mark_index_price": (["mark", "index"], ["mark 和 index 均已建模"]),
    "future_mark_price": (["mark"], ["用 future market_type + EventType.MARK 表达"]),
    "perp_mark_price": (["mark"], ["用 perp market_type + EventType.MARK 表达"]),
    "trades": (["trade"], ["EventType.TRADE 已建模，部分历史归档 parser 已接入"]),
    "orderbook": (
        ["orderbook"],
        [
            "EventType.ORDERBOOK 已建模；默认 MVP 政策为 top20 1s snapshot，staleness 上限 3s，热数据保留 7-14 天"
        ],
    ),
    "fees": (["fee"], ["EventType.FEE 已建模，仍需按交易所补具体费率源"]),
    "instrument_metadata": (["instrument"], ["EventType.INSTRUMENT 已建模"]),
}

_DERIVABLE_REQUIREMENTS: dict[str, tuple[list[str], list[str], str]] = {
    "candles": (
        ["trade"],
        ["当前未单独建模 candle，默认从 trade 聚合；mark/index candle 应显式声明为 mark_price 或 mark_index_price"],
        "创建 candle 聚合 fixture，固定 interval 和价格源",
    ),
    "spot_candles": (
        ["trade"],
        ["用 spot market_type 的 trade 聚合 candle"],
        "创建 spot candle 聚合 fixture，固定 interval 和价格源",
    ),
    "perp_candles": (
        ["trade"],
        ["用 perp market_type 的 trade 聚合 candle；mark/index 价格源应显式声明为 mark_price 或 mark_index_price"],
        "创建 perp candle 聚合 fixture，固定 interval 和价格源",
    ),
    "depth_volume": (
        ["orderbook", "trade"],
        [
            "MVP depth_volume 用 top20 orderbook 1s snapshot 和 trade 聚合为 1m/5m 容量代理",
            "staleness 上限 3s；orderbook 热数据保留 7-14 天，trades 保留 14-30 天",
        ],
        "按 docs/PIPELINES_AND_STORAGE_ZH.md 的 depth_volume MVP 政策检查 orderbook 和 trade 分区",
    ),
}

_POLICY_REQUIREMENTS: dict[str, tuple[list[str], list[str], str]] = {
    "orderbook_full_depth": (
        ["orderbook"],
        ["全量 orderbook 或 100ms 级 orderbook 尚未作为默认采集政策"],
        "若策略需要全量深度或亚秒级盘口，先单独评估磁盘、延迟和保留期",
    ),
}

_MANUAL_REQUIREMENTS: dict[str, tuple[list[str], str]] = {
    "manual_stablecoin_status_checklist": (
        [
            "稳定币发行方、储备、赎回通道、交易所充提和监管状态不是 MarketEvent；必须作为人工审核门禁记录",
            "未通过人工门禁时，策略只能输出 blocked alert，不能进入自动买入或 validation-ready 状态",
        ],
        "填写 stablecoin 手工状态 checklist，并把结论绑定到具体资产、交易所、时间窗口和来源链接",
    ),
}
