from packages.research_agent import ResearchArtifact, ResearchGuardrails
from packages.risk import SafetyPolicy


def test_safety_policy_blocks_trading_and_auto_deploy_by_default() -> None:
    policy = SafetyPolicy()
    assert not policy.check("place_order").allowed
    assert not policy.check("auto_deploy_strategy").allowed
    assert policy.check("create_research_report").allowed


def test_research_guardrails_reject_production_targets() -> None:
    artifact = ResearchArtifact(
        title="候选 basis 策略",
        summary="仅用于研究。",
        candidate_files=["configs/production/strategies.toml", "packages/strategies/basis_candidate.py"],
    )

    issues = ResearchGuardrails().validate_artifact(artifact)

    assert "candidate_artifact_targets_production_config" in issues
    assert "候选文件触及受限路径：configs/production/strategies.toml" in issues
    assert not any(issue.startswith("policy_allows_blocked_action") for issue in issues)
