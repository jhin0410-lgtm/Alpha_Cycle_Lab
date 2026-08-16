from __future__ import annotations

from datetime import date
from types import SimpleNamespace

from alpha_cycle.intelligence.sk_hynix_product_profitability_calibration_inventory import (
    build_skhynix_product_profitability_calibration_inventory,
)


def test_inventory_reserves_q1_2026_and_keeps_cycle_features_available(monkeypatch, tmp_path) -> None:
    observations = (
        SimpleNamespace(period_id="q1_2026", period_start=date(2026, 1, 1), period_end=date(2026, 3, 31)),
        SimpleNamespace(period_id="q1_2025", period_start=date(2025, 1, 1), period_end=date(2025, 3, 31)),
        SimpleNamespace(period_id="fy2025", period_start=date(2025, 1, 1), period_end=date(2025, 12, 31)),
        SimpleNamespace(period_id="fy2024", period_start=date(2024, 1, 1), period_end=date(2024, 12, 31)),
        SimpleNamespace(period_id="fy2023", period_start=date(2023, 1, 1), period_end=date(2023, 12, 31)),
    )
    revenue = SimpleNamespace(
        ticker="000660",
        evidence_id="d" * 64,
        product_revenue_baseline_eligible=True,
    )
    support = SimpleNamespace(
        ticker="000660",
        evidence_id="a" * 64,
        observations=observations,
        independent_non_overlapping_period_count=4,
        product_profitability_source_fact=False,
        direct_product_profitability_observations=0,
    )
    cycle = SimpleNamespace(
        ticker="000660",
        evidence_id="c" * 64,
        source_profitability_support_evidence_id="a" * 64,
        textual_band_source_facts=True,
        numeric_driver_values_available=False,
        observations=tuple(
            SimpleNamespace(period_id=f"{year}Q{quarter}")
            for year, quarters in ((2023, 4), (2024, 4), (2025, 4), (2026, 1))
            for quarter in range(1, quarters + 1)
        ),
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
        "load_sec_product_cycle_driver_support_evidence",
        lambda *args, **kwargs: cycle,
    )
    pointer = tmp_path / "unused.json"
    result = build_skhynix_product_profitability_calibration_inventory(
        evaluation_date=date(2026, 8, 16),
        product_revenue_pointer=pointer,
        profitability_support_pointer=pointer,
        cycle_driver_support_pointer=pointer,
        reserve_q1_2026_holdout=True,
    )
    assert result.historical_product_revenue_periods == (
        "fy2023",
        "fy2024",
        "q1_2025",
    )
    assert result.company_profitability_constraint_periods == (
        "fy2023",
        "fy2024",
        "q1_2025",
    )
    assert result.holdout_periods == ("q1_2026",)
    assert result.cycle_driver_history_periods[-1] == "2026Q1"
    assert len(result.cycle_driver_history_periods) == 13
