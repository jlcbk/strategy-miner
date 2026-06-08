from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any


class ArtifactKind(str, Enum):
    RESEARCH_REPORT = "research_report"
    STRATEGY_PROPOSAL = "strategy_proposal"
    BACKTEST_REQUEST = "backtest_request"
    OPPORTUNITY_REPORT = "opportunity_report"


def utc_timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class AgentArtifact:
    kind: ArtifactKind
    title: str
    created_by: str
    created_at: str = field(default_factory=utc_timestamp)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["kind"] = self.kind.value
        return data


@dataclass(frozen=True)
class ResearchReport(AgentArtifact):
    summary: str = ""
    source_urls: list[str] = field(default_factory=list)
    claims: list[str] = field(default_factory=list)
    formulas: list[str] = field(default_factory=list)
    cost_items: list[str] = field(default_factory=list)
    failure_modes: list[str] = field(default_factory=list)
    required_data: list[str] = field(default_factory=list)
    evidence_notes: list[str] = field(default_factory=list)

    def __init__(
        self,
        *,
        title: str,
        created_by: str,
        summary: str,
        source_urls: list[str] | None = None,
        claims: list[str] | None = None,
        formulas: list[str] | None = None,
        cost_items: list[str] | None = None,
        failure_modes: list[str] | None = None,
        required_data: list[str] | None = None,
        evidence_notes: list[str] | None = None,
        created_at: str | None = None,
    ) -> None:
        object.__setattr__(self, "kind", ArtifactKind.RESEARCH_REPORT)
        object.__setattr__(self, "title", title)
        object.__setattr__(self, "created_by", created_by)
        object.__setattr__(self, "created_at", created_at or utc_timestamp())
        object.__setattr__(self, "summary", summary)
        object.__setattr__(self, "source_urls", source_urls or [])
        object.__setattr__(self, "claims", claims or [])
        object.__setattr__(self, "formulas", formulas or [])
        object.__setattr__(self, "cost_items", cost_items or [])
        object.__setattr__(self, "failure_modes", failure_modes or [])
        object.__setattr__(self, "required_data", required_data or [])
        object.__setattr__(self, "evidence_notes", evidence_notes or [])


@dataclass(frozen=True)
class StrategyProposal(AgentArtifact):
    strategy_name: str = ""
    hypothesis: str = ""
    evaluator_contract: dict[str, Any] = field(default_factory=dict)
    data_requirements: list[str] = field(default_factory=list)
    test_plan: list[str] = field(default_factory=list)
    risk_controls: list[str] = field(default_factory=list)
    candidate_files: list[str] = field(default_factory=list)

    def __init__(
        self,
        *,
        title: str,
        created_by: str,
        strategy_name: str,
        hypothesis: str,
        evaluator_contract: dict[str, Any] | None = None,
        data_requirements: list[str] | None = None,
        test_plan: list[str] | None = None,
        risk_controls: list[str] | None = None,
        candidate_files: list[str] | None = None,
        created_at: str | None = None,
    ) -> None:
        object.__setattr__(self, "kind", ArtifactKind.STRATEGY_PROPOSAL)
        object.__setattr__(self, "title", title)
        object.__setattr__(self, "created_by", created_by)
        object.__setattr__(self, "created_at", created_at or utc_timestamp())
        object.__setattr__(self, "strategy_name", strategy_name)
        object.__setattr__(self, "hypothesis", hypothesis)
        object.__setattr__(self, "evaluator_contract", evaluator_contract or {})
        object.__setattr__(self, "data_requirements", data_requirements or [])
        object.__setattr__(self, "test_plan", test_plan or [])
        object.__setattr__(self, "risk_controls", risk_controls or [])
        object.__setattr__(self, "candidate_files", candidate_files or [])


@dataclass(frozen=True)
class BacktestRequest(AgentArtifact):
    strategy_name: str = ""
    strategy_version: str = ""
    data_window: dict[str, str] = field(default_factory=dict)
    symbols: list[str] = field(default_factory=list)
    exchanges: list[str] = field(default_factory=list)
    parameters: dict[str, Any] = field(default_factory=dict)

    def __init__(
        self,
        *,
        title: str,
        created_by: str,
        strategy_name: str,
        strategy_version: str,
        data_window: dict[str, str],
        symbols: list[str] | None = None,
        exchanges: list[str] | None = None,
        parameters: dict[str, Any] | None = None,
        created_at: str | None = None,
    ) -> None:
        object.__setattr__(self, "kind", ArtifactKind.BACKTEST_REQUEST)
        object.__setattr__(self, "title", title)
        object.__setattr__(self, "created_by", created_by)
        object.__setattr__(self, "created_at", created_at or utc_timestamp())
        object.__setattr__(self, "strategy_name", strategy_name)
        object.__setattr__(self, "strategy_version", strategy_version)
        object.__setattr__(self, "data_window", data_window)
        object.__setattr__(self, "symbols", symbols or [])
        object.__setattr__(self, "exchanges", exchanges or [])
        object.__setattr__(self, "parameters", parameters or {})


@dataclass(frozen=True)
class OpportunityReport(AgentArtifact):
    strategy_name: str = ""
    strategy_version: str = ""
    data_window: dict[str, str] = field(default_factory=dict)
    opportunity_count: int = 0
    opportunities: list[dict[str, Any]] = field(default_factory=list)
    result_hash: str | None = None

    def __init__(
        self,
        *,
        title: str,
        created_by: str,
        strategy_name: str,
        strategy_version: str,
        data_window: dict[str, str],
        opportunity_count: int,
        opportunities: list[dict[str, Any]] | None = None,
        result_hash: str | None = None,
        created_at: str | None = None,
    ) -> None:
        object.__setattr__(self, "kind", ArtifactKind.OPPORTUNITY_REPORT)
        object.__setattr__(self, "title", title)
        object.__setattr__(self, "created_by", created_by)
        object.__setattr__(self, "created_at", created_at or utc_timestamp())
        object.__setattr__(self, "strategy_name", strategy_name)
        object.__setattr__(self, "strategy_version", strategy_version)
        object.__setattr__(self, "data_window", data_window)
        object.__setattr__(self, "opportunity_count", opportunity_count)
        object.__setattr__(self, "opportunities", opportunities or [])
        object.__setattr__(self, "result_hash", result_hash)
