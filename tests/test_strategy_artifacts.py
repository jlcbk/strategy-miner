import json
from pathlib import Path


ARTIFACT_ROOTS = {
    "cross_exchange_funding_dispersion": Path(
        "artifacts/strategies/cross_exchange_funding_dispersion"
    ),
    "funding_carry_vol_filter": Path("artifacts/strategies/funding_carry_vol_filter"),
}


def test_cross_exchange_funding_artifacts_are_machine_readable() -> None:
    report, proposal = _read_artifacts("cross_exchange_funding_dispersion")

    assert report["kind"] == "research_report"
    assert proposal["kind"] == "strategy_proposal"
    assert proposal["strategy_name"] == "cross_exchange_funding_dispersion"
    assert report["failure_modes"]
    assert proposal["data_requirements"] == report["required_data"]
    assert "depth_volume" in proposal["data_requirements"]
    assert any("Operator fit" in note for note in report["evidence_notes"])


def test_cross_exchange_funding_artifacts_match_supported_schema_fields() -> None:
    report, proposal = _read_artifacts("cross_exchange_funding_dispersion")

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


def test_funding_carry_artifacts_are_machine_readable() -> None:
    report, proposal = _read_artifacts("funding_carry_vol_filter")

    assert report["kind"] == "research_report"
    assert proposal["kind"] == "strategy_proposal"
    assert proposal["strategy_name"] == "funding_carry_vol_filter"
    assert proposal["data_requirements"] == report["required_data"]
    assert "funding" in proposal["data_requirements"]
    assert "mark_index_price" in proposal["data_requirements"]
    assert "spot_candles" in proposal["data_requirements"]
    assert "perp_candles" in proposal["data_requirements"]
    assert "instrument_metadata" in proposal["data_requirements"]
    assert any("Operator fit" in note for note in report["evidence_notes"])
    assert any("Fee boundary" in note for note in report["evidence_notes"])


def _read_artifacts(strategy_name: str) -> tuple[dict, dict]:
    root = ARTIFACT_ROOTS[strategy_name]
    return (
        _read_json(root / "research_report.json"),
        _read_json(root / "strategy_proposal.json"),
    )


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))
