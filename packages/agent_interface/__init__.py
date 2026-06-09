from packages.agent_interface.artifacts import (
    AgentArtifact,
    ArtifactKind,
    BacktestRequest,
    OpportunityReport,
    ResearchReport,
    StrategyProposal,
)
from packages.agent_interface.guardrails import AgentAction, AgentGuardrails, GuardrailDecision
from packages.agent_interface.research_funnel import (
    CRITERION_WEIGHTS,
    FunnelCandidate,
    FunnelRank,
    FunnelStatus,
    candidate_from_payload,
    rank_strategy_candidates,
    scoring_contract,
)
from packages.agent_interface.validation_plan import (
    RequirementPlan,
    RequirementStatus,
    ValidationPlan,
    ValidationReadiness,
    plan_strategy_validation,
    validation_planning_contract,
)
from packages.agent_interface.workflow import WorkflowStage, next_allowed_stages

__all__ = [
    "AgentAction",
    "AgentArtifact",
    "AgentGuardrails",
    "ArtifactKind",
    "BacktestRequest",
    "CRITERION_WEIGHTS",
    "FunnelCandidate",
    "FunnelRank",
    "FunnelStatus",
    "GuardrailDecision",
    "OpportunityReport",
    "RequirementPlan",
    "RequirementStatus",
    "ResearchReport",
    "StrategyProposal",
    "ToolResult",
    "ValidationPlan",
    "ValidationReadiness",
    "WorkflowStage",
    "available_tools",
    "candidate_from_payload",
    "next_allowed_stages",
    "plan_strategy_validation",
    "rank_strategy_candidates",
    "run_tool",
    "scoring_contract",
    "validation_planning_contract",
]

_TOOL_EXPORTS = {"ToolResult", "available_tools", "run_tool"}


def __getattr__(name: str):
    if name in _TOOL_EXPORTS:
        from packages.agent_interface import tools

        return getattr(tools, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
