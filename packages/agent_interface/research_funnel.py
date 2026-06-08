from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from enum import Enum
from typing import Any


class FunnelStatus(str, Enum):
    RESEARCHED = "researched"
    PROPOSED = "proposed"
    QUEUED_FOR_VALIDATION = "queued_for_validation"
    NEEDS_HUMAN_REVIEW = "needs_human_review"


CRITERION_WEIGHTS: dict[str, Decimal] = {
    "verifiability": Decimal("0.25"),
    "data_availability": Decimal("0.20"),
    "capacity_potential": Decimal("0.15"),
    "cost_robustness": Decimal("0.15"),
    "overfit_resilience": Decimal("0.15"),
    "implementation_simplicity": Decimal("0.10"),
}

CRITERION_LABELS: dict[str, str] = {
    "verifiability": "验证路径清晰",
    "data_availability": "数据可得",
    "capacity_potential": "容量潜力",
    "cost_robustness": "交易成本稳健",
    "overfit_resilience": "抗过拟合",
    "implementation_simplicity": "实现简单",
}


@dataclass(frozen=True)
class FunnelCandidate:
    proposal: dict[str, Any]
    scores: dict[str, Decimal]
    research_report: dict[str, Any] | None = None


@dataclass(frozen=True)
class FunnelRank:
    rank: int
    strategy_name: str
    total_score: Decimal
    recommended_status: FunnelStatus
    criterion_scores: dict[str, Decimal]
    missing_fields: list[str]
    strengths: list[str]
    next_actions: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "rank": self.rank,
            "strategy_name": self.strategy_name,
            "total_score": _format_decimal(self.total_score),
            "recommended_status": self.recommended_status.value,
            "criterion_scores": {
                name: _format_decimal(score) for name, score in self.criterion_scores.items()
            },
            "missing_fields": self.missing_fields,
            "strengths": self.strengths,
            "next_actions": self.next_actions,
        }


def rank_strategy_candidates(
    candidates: list[FunnelCandidate],
    *,
    limit: int | None = None,
) -> list[FunnelRank]:
    ranked = [_score_candidate(candidate) for candidate in candidates]
    ranked.sort(key=lambda item: (item.total_score, item.strategy_name), reverse=True)
    if limit is not None:
        ranked = ranked[: max(0, limit)]
    return [
        FunnelRank(
            rank=index,
            strategy_name=item.strategy_name,
            total_score=item.total_score,
            recommended_status=item.recommended_status,
            criterion_scores=item.criterion_scores,
            missing_fields=item.missing_fields,
            strengths=item.strengths,
            next_actions=item.next_actions,
        )
        for index, item in enumerate(ranked, start=1)
    ]


def candidate_from_payload(payload: dict[str, Any]) -> FunnelCandidate:
    if not isinstance(payload, dict):
        raise ValueError("candidate 必须是对象")

    proposal = payload.get("proposal")
    if not isinstance(proposal, dict):
        raise ValueError("candidate 缺少 proposal 对象")

    raw_scores = payload.get("scores")
    if not isinstance(raw_scores, dict):
        raise ValueError("candidate 缺少 scores 对象")

    research_report = payload.get("research_report")
    if research_report is not None and not isinstance(research_report, dict):
        raise ValueError("research_report 必须是对象")

    return FunnelCandidate(
        proposal=proposal,
        scores={name: _normalize_score(raw_scores.get(name, 0)) for name in CRITERION_WEIGHTS},
        research_report=research_report,
    )


def scoring_contract() -> dict[str, Any]:
    return {
        "score_range": {"min": 0, "max": 5},
        "criteria": [
            {
                "name": name,
                "label": CRITERION_LABELS[name],
                "weight": _format_decimal(weight),
            }
            for name, weight in CRITERION_WEIGHTS.items()
        ],
        "status_thresholds": {
            FunnelStatus.QUEUED_FOR_VALIDATION.value: ">= 75 且核心字段完整",
            FunnelStatus.NEEDS_HUMAN_REVIEW.value: ">= 60 或高分但核心字段缺失",
            FunnelStatus.PROPOSED.value: ">= 40",
            FunnelStatus.RESEARCHED.value: "< 40",
        },
    }


@dataclass(frozen=True)
class _ScoredCandidate:
    strategy_name: str
    total_score: Decimal
    recommended_status: FunnelStatus
    criterion_scores: dict[str, Decimal]
    missing_fields: list[str]
    strengths: list[str]
    next_actions: list[str]


def _score_candidate(candidate: FunnelCandidate) -> _ScoredCandidate:
    missing_fields = _missing_core_fields(candidate)
    weighted_score = sum(
        candidate.scores[name] * Decimal("20") * weight
        for name, weight in CRITERION_WEIGHTS.items()
    )
    completeness_penalty = Decimal(len(missing_fields) * 4)
    total_score = max(Decimal("0"), weighted_score - completeness_penalty).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )

    return _ScoredCandidate(
        strategy_name=str(
            candidate.proposal.get("strategy_name")
            or candidate.proposal.get("title")
            or "未命名策略"
        ),
        total_score=total_score,
        recommended_status=_recommended_status(total_score, missing_fields),
        criterion_scores=candidate.scores,
        missing_fields=missing_fields,
        strengths=_strengths(candidate.scores),
        next_actions=_next_actions(total_score, missing_fields, candidate.scores),
    )


def _missing_core_fields(candidate: FunnelCandidate) -> list[str]:
    proposal = candidate.proposal
    missing: list[str] = []
    for field in ("strategy_name", "hypothesis"):
        if not str(proposal.get(field, "")).strip():
            missing.append(f"proposal.{field}")

    for field in ("data_requirements", "test_plan", "risk_controls"):
        value = proposal.get(field)
        if not isinstance(value, list) or not value:
            missing.append(f"proposal.{field}")

    report = candidate.research_report or {}
    if not proposal.get("failure_modes") and not report.get("failure_modes"):
        missing.append("failure_modes")
    return missing


def _recommended_status(score: Decimal, missing_fields: list[str]) -> FunnelStatus:
    if score >= Decimal("75") and not missing_fields:
        return FunnelStatus.QUEUED_FOR_VALIDATION
    if score >= Decimal("60"):
        return FunnelStatus.NEEDS_HUMAN_REVIEW
    if score >= Decimal("40"):
        return FunnelStatus.PROPOSED
    return FunnelStatus.RESEARCHED


def _strengths(scores: dict[str, Decimal]) -> list[str]:
    strengths = [
        CRITERION_LABELS[name]
        for name, score in scores.items()
        if score >= Decimal("4")
    ]
    return strengths[:3]


def _next_actions(
    total_score: Decimal,
    missing_fields: list[str],
    scores: dict[str, Decimal],
) -> list[str]:
    actions: list[str] = []
    if missing_fields:
        actions.append("补齐核心字段：" + "、".join(missing_fields))
    if scores["data_availability"] < Decimal("3"):
        actions.append("先确认数据源、采样频率和历史覆盖范围")
    if scores["cost_robustness"] < Decimal("3"):
        actions.append("补充手续费、滑点、资金费和冲击成本假设")
    if scores["overfit_resilience"] < Decimal("3"):
        actions.append("增加跨时间窗口、跨交易所或跨品种稳定性检查")
    if total_score >= Decimal("75") and not missing_fields:
        actions.append("进入 validation_queue，准备数据覆盖检查和 fixture 测试")
    if not actions:
        actions.append("保留在 research_backlog，等待同主题候选横向比较")
    return actions


def _normalize_score(value: Any) -> Decimal:
    try:
        score = Decimal(str(value))
    except InvalidOperation as exc:
        raise ValueError("scores 中每个维度必须是数字") from exc
    if score < Decimal("0") or score > Decimal("5"):
        raise ValueError("scores 中每个维度必须在 0 到 5 之间")
    return score.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _format_decimal(value: Decimal) -> str:
    return str(value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))
