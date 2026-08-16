from __future__ import annotations

import json
from types import SimpleNamespace

from alpha_cycle.sk_hynix_opendart_historical_product_revenue_panel_cli import main


def test_cli_exposes_verified_and_invalid_failure_diagnostic_paths(
    monkeypatch, tmp_path, capsys
) -> None:
    import alpha_cycle.sk_hynix_opendart_historical_product_revenue_panel_cli as module

    monkeypatch.setattr(
        module.OpenDartReadOnlyClient,
        "from_env",
        staticmethod(lambda: object()),
    )
    monkeypatch.setattr(
        module,
        "capture_historical_product_revenue_panel",
        lambda *args, **kwargs: {"status": "captured"},
    )
    monkeypatch.setattr(
        module,
        "load_historical_product_revenue_panel_evidence",
        lambda *args, **kwargs: SimpleNamespace(
            evidence_id="a" * 64,
            successful_periods=("2023Q1",),
            failed_periods=("2024Q2", "2025Q3", "2023Q2"),
            full_source_coverage_certified=False,
            product_profitability_source_fact=False,
            numeric_forecast_enabled=False,
        ),
    )
    monkeypatch.setattr(
        module,
        "inventory_historical_product_revenue_failure_diagnostics",
        lambda *args, **kwargs: SimpleNamespace(
            diagnostics=(object(),),
            diagnostic_paths={"2024Q2": "/tmp/2024Q2/diagnostic.json"},
            diagnostic_errors={"2024Q2": "historical layout differs"},
            invalid_diagnostics=(object(),),
            invalid_diagnostic_paths={"2023Q2": "/tmp/2023Q2/diagnostic.json"},
            invalid_diagnostic_errors={"2023Q2": "normalized text hash mismatch"},
            missing_diagnostic_periods=("2025Q3",),
            diagnostic_bundle_coverage_complete=False,
            diagnostic_bundle_integrity_complete=False,
        ),
    )
    exit_code = main(
        [
            "--evaluation-date",
            "2026-08-16",
            "--output",
            str(tmp_path),
        ]
    )
    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert payload["failed_diagnostic_bundle_count"] == 1
    assert payload["failed_diagnostic_paths"] == {
        "2024Q2": "/tmp/2024Q2/diagnostic.json"
    }
    assert payload["failed_diagnostic_errors"] == {
        "2024Q2": "historical layout differs"
    }
    assert payload["failed_diagnostic_invalid_count"] == 1
    assert payload["failed_diagnostic_invalid_paths"] == {
        "2023Q2": "/tmp/2023Q2/diagnostic.json"
    }
    assert payload["failed_diagnostic_invalid_errors"] == {
        "2023Q2": "normalized text hash mismatch"
    }
    assert payload["failed_diagnostic_missing_periods"] == ["2025Q3"]
    assert payload["failed_diagnostic_bundle_coverage_complete"] is False
    assert payload["failed_diagnostic_bundle_integrity_complete"] is False
    assert payload["numeric_forecast_enabled"] is False
