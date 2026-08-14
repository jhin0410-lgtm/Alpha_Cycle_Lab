from __future__ import annotations

from pathlib import Path


def test_package_routes_final_decision_builder_through_transmission_wrapper() -> None:
    package = Path("src/alpha_cycle/intelligence/__init__.py").read_text(encoding="utf-8")
    transmission = Path(
        "src/alpha_cycle/intelligence/decision_semiconductor_transmission_calibrated.py"
    ).read_text(encoding="utf-8")
    sector = Path(
        "src/alpha_cycle/intelligence/decision_sector_vertical_calibrated.py"
    ).read_text(encoding="utf-8")

    assert "decision_industry_evidence_calibrated" in package
    assert "decision_forward_estimate_calibrated" in package
    assert "decision_historical_pb_calibrated" in package
    assert "decision_sector_vertical_calibrated" in package
    assert "decision_semiconductor_transmission_calibrated" in package
    assert (
        "from alpha_cycle.intelligence.decision_semiconductor_transmission_calibrated import"
        in package
    )
    assert "build_investment_decision_snapshot" in package

    assert "decision_sector_vertical_calibrated" in transmission
    assert "_build_sector_vertical_snapshot" in transmission
    assert "build_semiconductor_transmission_evidence" in transmission

    assert "decision_historical_pb_calibrated" in sector
    assert "_build_historical_pb_snapshot" in sector
    assert "build_semiconductor_vertical_assessment" in sector
    assert "sector_vertical_missing_evidence_not_zero_scored" in sector
