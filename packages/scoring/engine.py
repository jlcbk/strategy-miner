from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import Enum


class OpportunityGrade(str, Enum):
    A = "A"
    B = "B"
    C = "C"


@dataclass(frozen=True)
class ScoreInput:
    gross_edge_usd: Decimal
    fees_usd: Decimal
    slippage_est_usd: Decimal
    capacity_usd: Decimal
    latency_sensitivity: Decimal
    funding_exposure: Decimal
    execution_complexity: Decimal


@dataclass(frozen=True)
class ScoreResult:
    fee_adjusted_edge_usd: Decimal
    slippage_adjusted_edge_usd: Decimal
    net_edge_usd: Decimal
    confidence: Decimal
    risk_score: Decimal
    grade: OpportunityGrade


def score_opportunity(inputs: ScoreInput) -> ScoreResult:
    fee_adjusted = inputs.gross_edge_usd - inputs.fees_usd
    net = fee_adjusted - inputs.slippage_est_usd
    risk_score = _clamp(
        Decimal("0.25") * inputs.latency_sensitivity
        + Decimal("0.25") * inputs.funding_exposure
        + Decimal("0.40") * inputs.execution_complexity
        + Decimal("0.10") * _capacity_risk(inputs.capacity_usd),
        Decimal("0"),
        Decimal("1"),
    )
    confidence = _clamp(Decimal("1") - risk_score, Decimal("0"), Decimal("1"))
    grade = _grade(inputs.gross_edge_usd, fee_adjusted, net)
    return ScoreResult(
        fee_adjusted_edge_usd=fee_adjusted,
        slippage_adjusted_edge_usd=net,
        net_edge_usd=net,
        confidence=confidence,
        risk_score=risk_score,
        grade=grade,
    )


def _grade(gross: Decimal, fee_adjusted: Decimal, net: Decimal) -> OpportunityGrade:
    if net > 0:
        return OpportunityGrade.A
    if fee_adjusted > 0:
        return OpportunityGrade.B
    if gross > 0:
        return OpportunityGrade.C
    return OpportunityGrade.C


def _capacity_risk(capacity_usd: Decimal) -> Decimal:
    if capacity_usd <= 0:
        return Decimal("1")
    if capacity_usd < Decimal("1000"):
        return Decimal("0.8")
    if capacity_usd < Decimal("10000"):
        return Decimal("0.4")
    return Decimal("0.1")


def _clamp(value: Decimal, lower: Decimal, upper: Decimal) -> Decimal:
    return max(lower, min(upper, value))
