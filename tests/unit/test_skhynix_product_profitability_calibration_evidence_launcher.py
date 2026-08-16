from __future__ import annotations

from pathlib import Path


def _script() -> str:
    return Path(
        "scripts/report_skhynix_product_profitability_calibration_evidence.ps1"
    ).read_text(encoding="utf-8")


def test_launcher_refreshes_current_product_revenue_when_evaluation_date_is_stale() -> None:
    text = _script()
    assert "$currentProductMatchesEvaluationDate = $false" in text
    assert "ConvertFrom-Json" in text
    assert "currentPointerJson.evaluation_date" in text
    assert "-EvaluationDate $EvaluationDate" in text
    assert "missing/stale" in text


def test_launcher_runs_complete_profitability_evidence_chain() -> None:
    text = _script()
    required_modules = (
        "alpha_cycle.sec_product_profitability_support_cli",
        "alpha_cycle.sec_product_cycle_driver_support_cli",
        "alpha_cycle.sk_hynix_opendart_quarterly_company_profitability_cli",
        "alpha_cycle.sk_hynix_opendart_historical_product_revenue_panel_cli",
        "alpha_cycle.sk_hynix_product_profitability_calibration_readiness_cli",
    )
    for module in required_modules:
        assert module in text
