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


def test_launcher_reuses_completed_cycle_driver_and_company_profitability_steps() -> None:
    text = _script()
    assert "$cycleDriverReusable = $false" in text
    assert "cycleDriverJson.observed_date" in text
    assert "cycleDriverJson.observation_count -eq 13" in text
    assert "source_profitability_support_evidence_id" in text
    assert "Reusing 13-quarter SEC cycle-driver support" in text
    assert "$companyProfitabilityReusable = $false" in text
    assert "companyProfitabilityJson.evaluation_date" in text
    assert "companyProfitabilityJson.observation_count -eq 10" in text
    assert "Reusing 10-quarter OpenDART company-profitability panel" in text


def test_launcher_recaptures_historical_product_panel_after_exact_byte_fix() -> None:
    text = _script()
    message = "[5/7] Recapturing historical direct product-revenue periods with exact text bytes."
    assert message in text
    step5 = text.index("[5/7]")
    module = text.index("alpha_cycle.sk_hynix_opendart_historical_product_revenue_panel_cli")
    assert module > step5


def test_launcher_runs_complete_profitability_evidence_chain_and_rank_probe() -> None:
    text = _script()
    required_modules = (
        "alpha_cycle.sec_product_profitability_support_cli",
        "alpha_cycle.sec_product_cycle_driver_support_cli",
        "alpha_cycle.sk_hynix_opendart_quarterly_company_profitability_cli",
        "alpha_cycle.sk_hynix_opendart_historical_product_revenue_panel_cli",
        "alpha_cycle.sk_hynix_product_profitability_calibration_readiness_cli",
        "alpha_cycle.sk_hynix_product_profitability_structural_rank_probe_cli",
    )
    for module in required_modules:
        assert module in text
    assert "[7/7]" in text
    assert "does not estimate product margins" in text
    assert "rank readiness is not model readiness" in text
