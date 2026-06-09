import json
from pathlib import Path


ARTIFACT_ROOT = Path("artifacts/strategies/cross_exchange_funding_dispersion")


def test_cross_exchange_funding_artifacts_are_machine_readable() -> None:
    report = _read_json(ARTIFACT_ROOT / "research_report.json")
    proposal = _read_json(ARTIFACT_ROOT / "strategy_proposal.json")

    assert report["kind"] == "research_report"
    assert proposal["kind"] == "strategy_proposal"
    assert proposal["strategy_name"] == "cross_exchange_funding_dispersion"
    assert report["failure_modes"]
    assert proposal["data_requirements"] == report["required_data"]
    assert "depth_volume" in proposal["data_requirements"]
    assert any("Operator fit" in note for note in report["evidence_notes"])


def test_cross_exchange_funding_artifacts_match_supported_schema_fields() -> None:
    report = _read_json(ARTIFACT_ROOT / "research_report.json")
    proposal = _read_json(ARTIFACT_ROOT / "strategy_proposal.json")

    assert set(report) == {
        "kind",
        "title",
        "created_by",
        "created_at",
        "summary",
        "source_urls",
        "claims",
        "formulas",
        "cost_items",
        "failure_modes",
        "required_data",
        "evidence_notes",
    }
    assert set(proposal) == {
        "kind",
        "title",
        "created_by",
        "created_at",
        "strategy_name",
        "hypothesis",
        "evaluator_contract",
        "data_requirements",
        "test_plan",
        "risk_controls",
        "candidate_files",
    }


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))
