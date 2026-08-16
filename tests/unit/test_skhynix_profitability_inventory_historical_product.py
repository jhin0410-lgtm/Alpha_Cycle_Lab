from __future__ import annotations

from datetime import date
from types import SimpleNamespace

from alpha_cycle.intelligence.sk_hynix_product_profitability_calibration_inventory import (
    build_skhynix_product_profitability_calibration_inventory,
)


def _period(period_id: str, start: date, end: date):
    return SimpleNamespace(period_id=period_id, period_start=start, period_end=end)


def test_historical_product_panel_adds_only_certified_non_holdout_quarters(
    monkeypatch,
    tmp_path,
) -> None:
    revenue = SimpleNamespace(
        ticker="000660",
        evidence_id="d" * 64,
        product_revenue_baseline_eligible=True,
    )
    support = SimpleNamespace(
        ticker="000660",
        evidence_id="a" * 64,
        observations=(
            _period("q1_2026", date(2026, 1, 1), date(2026, 3, 31)),
            _period("q1_2025", date(2025, 1, 1), date(2025, 3, 31)),
            _period("fy2025", date(2025, 1, 1), date(2025, 12, 31)),
            _period("fy2024", date(2024, 1, 1), date(2024, 12, 31)),
            _period("fy2023", date(2023, 1, 1), date(2023, 12, 31)),
        ),
        independent_non_overlapping_period_count=4,
        product_profitability_source_fact=False,
        direct_product_profitability_observations=0,
    )
    quarterly = SimpleNamespace(
        ticker="000660",
        evidence_id="b" * 64,
        calibration_support_only=True,
        product_profitability_source_fact=False,
        point_in_time_backtest_eligible=False,
        observations=tuple(
            SimpleNamespace(period_id=period)
            for period in (
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
        ),
    )
    historical = SimpleNamespace(
        ticker="000660",
        evidence_id="c" * 64,
        calibration_support_only=True,
        product_profitability_source_fact=False,
        successful_periods=("2023Q1", "2023Q2", "2024Q1", "2025Q1", "2026Q1"),
        failed_periods=("2023Q3", "2024Q2", "2024Q3", "2025Q2", "2025Q3"),
    )

    import alpha_cycle.intelligence.sk_hynix_product_profitability_calibration_inventory as module

    monkeypatch.setattr(
        module,
        "load_periodic_product_revenue_certification",
        lambda *args, **kwargs: revenue,
    )
    monkeypatch.setattr(
        module,
        "load_sec_product_profitability_support_evidence",
        lambda *args, **kwargs: support,
    )
    monkeypatch.setattr(
        module,
        "load_quarterly_company_profitability_evidence",
        lambda *args, **kwargs: quarterly,
    )
    monkeypatch.setattr(
        module,
        "load_historical_product_revenue_panel_evidence",
        lambda *args, **kwargs: historical,
    )
    pointer = tmp_path / "unused.json"
    result = build_skhynix_product_profitability_calibration_inventory(
        evaluation_date=date(2026, 8, 16),
        product_revenue_pointer=pointer,
        profitability_support_pointer=pointer,
        quarterly_company_profitability_pointer=pointer,
        historical_product_revenue_pointer=pointer,
        reserve_q1_2026_holdout=True,
    )

    assert "q1_2026" not in result.historical_product_revenue_periods
    assert "2026Q1" not in result.historical_product_revenue_periods
    assert "q1_2026" not in result.company_profitability_constraint_periods
    assert "2026Q1" not in result.company_profitability_constraint_periods
    assert "2023Q1" in result.historical_product_revenue_periods
    assert "2023Q2" in result.historical_product_revenue_periods
    assert "2023Q3" not in result.historical_product_revenue_periods
    assert "2025Q1" in result.historical_product_revenue_periods
    assert "2025Q2" not in result.historical_product_revenue_periods
    assert "2025Q2" in result.company_profitability_constraint_periods
    assert result.holdout_periods == ("q1_2026",)
    assert result.verified_evidence_ids == ("a" * 64, "b" * 64, "c" * 64)
