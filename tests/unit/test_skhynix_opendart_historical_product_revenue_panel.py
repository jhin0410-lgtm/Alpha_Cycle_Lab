from __future__ import annotations

from datetime import UTC, date, datetime

from alpha_cycle.intelligence.sk_hynix_opendart_historical_product_revenue_panel import (
    HistoricalProductRevenuePanelEntry,
    build_historical_product_revenue_panel_evidence,
    capture_historical_product_revenue_panel,
    historical_period_id,
    load_historical_product_revenue_specs,
)


def _certified(period: str, document_id: str) -> HistoricalProductRevenuePanelEntry:
    return HistoricalProductRevenuePanelEntry(
        period_id=period,
        document_id=document_id,
        status="certified",
        pointer_path=f"/{period}/latest.json",
        certification_evidence_id="a" * 64,
        chain_evidence_id="b" * 64,
        rcept_no="20260515000001",
        error_type=None,
    )


def _failed(period: str, document_id: str) -> HistoricalProductRevenuePanelEntry:
    return HistoricalProductRevenuePanelEntry(
        period_id=period,
        document_id=document_id,
        status="failed",
        pointer_path=None,
        certification_evidence_id=None,
        chain_evidence_id=None,
        rcept_no=None,
        error_type="ValueError",
    )


def test_registry_binds_exact_ten_q1_q2_q3_direct_quarters() -> None:
    specs = load_historical_product_revenue_specs()
    periods = tuple(historical_period_id(spec) for spec in specs)
    assert periods == (
        "2023Q1",
        "2023Q2",
        "2023Q3",
        "2024Q1",
        "2024Q2",
        "2024Q3",
        "2025Q1",
        "2025Q2",
        "2025Q3",
        "2026Q1",
    )
    assert all(not period.endswith("Q4") for period in periods)
    assert all("3개월" in spec.expected_identity_anchors for spec in specs)


def test_partial_panel_preserves_failed_periods_without_promoting_them() -> None:
    specs = load_historical_product_revenue_specs()
    entries = tuple(
        _failed(historical_period_id(spec), spec.document_id)
        if index in {1, 6}
        else _certified(historical_period_id(spec), spec.document_id)
        for index, spec in enumerate(specs)
    )
    evidence = build_historical_product_revenue_panel_evidence(
        evaluation_date=date(2026, 8, 16),
        entries=entries,
    )
    assert len(evidence.successful_periods) == 8
    assert evidence.failed_periods == ("2023Q2", "2025Q1")
    assert evidence.full_source_coverage_certified is False
    assert evidence.product_profitability_source_fact is False
    assert evidence.numeric_forecast_enabled is False
    assert evidence.decision_score_enabled is False


def test_batch_capture_continues_after_one_period_failure(monkeypatch, tmp_path) -> None:
    specs = load_historical_product_revenue_specs()
    failing_period = "2024Q2"

    def fake_capture(client, spec, **kwargs):
        del client, kwargs
        if historical_period_id(spec) == failing_period:
            raise ValueError("historical layout differs")
        return {"status": "ok"}

    def fake_certified_entry(*, period_id, spec, pointer_path, evaluation_date):
        del pointer_path, evaluation_date
        return _certified(period_id, spec.document_id)

    import alpha_cycle.intelligence.sk_hynix_opendart_historical_product_revenue_panel as module

    monkeypatch.setattr(module, "capture_periodic_product_revenue_certification", fake_capture)
    monkeypatch.setattr(module, "_certified_entry", fake_certified_entry)
    result = capture_historical_product_revenue_panel(
        object(),
        evaluation_date=date(2026, 8, 16),
        output=tmp_path,
        captured_at=datetime(2026, 8, 16, 10, 0, tzinfo=UTC),
    )
    assert failing_period in result["failed_periods"]
    assert len(result["successful_periods"]) == len(specs) - 1
    assert result["full_source_coverage_certified"] is False
    assert (tmp_path / "historical_product_revenue_panel.json").is_file()
    assert (tmp_path / "latest_historical_product_revenue_panel.json").is_file()
