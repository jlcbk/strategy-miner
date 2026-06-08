from __future__ import annotations

from dataclasses import dataclass, field

from packages.risk import SafetyPolicy


@dataclass(frozen=True)
class ResearchArtifact:
    title: str
    summary: str
    source_url: str | None = None
    formulas: list[str] = field(default_factory=list)
    cost_items: list[str] = field(default_factory=list)
    failure_modes: list[str] = field(default_factory=list)
    candidate_files: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "title": self.title,
            "summary": self.summary,
            "source_url": self.source_url,
            "formulas": list(self.formulas),
            "cost_items": list(self.cost_items),
            "failure_modes": list(self.failure_modes),
            "candidate_files": list(self.candidate_files),
        }


class ResearchGuardrails:
    def __init__(self, policy: SafetyPolicy | None = None) -> None:
        self.policy = policy or SafetyPolicy()

    def validate_artifact(self, artifact: ResearchArtifact) -> list[str]:
        issues: list[str] = []
        blocked_markers = ("order", "execution", "live", "production")
        for candidate in artifact.candidate_files:
            lowered = candidate.lower()
            if "configs/production" in lowered:
                issues.append("candidate_artifact_targets_production_config")
            if any(marker in lowered for marker in blocked_markers) and "report" not in lowered:
                issues.append(f"candidate_artifact_may_touch_blocked_surface:{candidate}")
        for action in ("place_order", "auto_deploy_strategy", "write_production_strategy_config"):
            decision = self.policy.check(action)
            if decision.allowed:
                issues.append(f"policy_allows_blocked_action:{action}")
        return issues
