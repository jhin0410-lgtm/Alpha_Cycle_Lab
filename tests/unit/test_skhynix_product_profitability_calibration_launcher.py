SCRIPT = "scripts/report_skhynix_product_profitability_calibration_evidence.ps1"


def _script_text() -> str:
    with open(SCRIPT, encoding="utf-8") as handle:
        return handle.read()


def test_launcher_runs_offline_historical_diagnostics_after_failed_capture() -> None:
    text = _script_text()
    capture = "alpha_cycle.sk_hynix_opendart_historical_product_revenue_panel_cli"
    diagnostics = "alpha_cycle.sk_hynix_opendart_historical_product_revenue_diagnostics_cli"
    readiness = "alpha_cycle.sk_hynix_product_profitability_calibration_readiness_cli"

    assert "latest_historical_product_revenue_panel.json" in text
    assert "$historicalProductJson.failed_period_count" in text
    assert "$historicalFailedPeriodCount -gt 0" in text
    assert "These signatures are diagnostics only and never promote source facts." in text
    assert capture in text
    assert diagnostics in text
    assert readiness in text
    assert text.index(capture) < text.index(diagnostics) < text.index(readiness)


def test_launcher_keeps_readiness_and_rank_fail_closed_after_diagnostics() -> None:
    text = _script_text()
    assert "Historical direct product-revenue source coverage is complete." in text
    assert "calibration readiness will remain fail-closed" in text
    assert "alpha_cycle.sk_hynix_product_profitability_structural_rank_probe_cli" in text
    assert "Numeric product-margin fitting remains disabled" in text
