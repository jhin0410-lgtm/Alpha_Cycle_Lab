from __future__ import annotations

from datetime import date
from types import SimpleNamespace

from alpha_cycle.intelligence.sec_product_profitability_support import (
    HistoricalProductProfitabilityConstraint,
)
from alpha_cycle.intelligence.sk_hynix_product_profitability_calibration_inventory import (
    _independent_period_ids,
    build_skhynix_product_profitability_calibration_inventory,
)


def _observation(period_id: str) -> HistoricalProductProfitabilityConstraint:
    dates = {
        "q1_2026": (date(2026, 1, 1), date(2026, 3, 31)),
        "q1_2025": (date(2025, 1, 1), date(2025, 3, 31)),
        "fy2025": (date(2025, 1, 1), date(2025, 12, 31)),
        "fy2024": (date(2024, 1, 1), date(2024, 12, 31)),
        "fy2023": (date(2023, 1, 1), date(2023, 12, 31)),
    }
    period_start, period_end = dates[period_id]
    total = 100.0
    dram = 70.0
    nand = 29.0
    other = 1.0
    gross_profit = 50.0
    gross_margin = 50.0
    return HistoricalProductProfitabilityConstraint(
        period_id=period_id,
        period_start=period_start,
        period_end=period_end,
        unit="KRW_billion",
        total_revenue=total,
        dram_revenue=dram,
        nand_revenue=nand,
        other_products_revenue=other,
        dram_share_percent=70.0,
        nand_share_percent=29.0,
        other_share_percent=1.0,
        product_revenue_reconciliation_delta_krw_billion=0.0,
        gross_profit=gross_profit,
        gross_margin_percent=gross_margin,
        gross_margin_reconciliation_delta_pp=0.0,
        direct_product_revenue_reconciled=True,
        company_gross_margin_reconciled=True,
    )


def test_independent_period_selection_does_not_double_count_q1_2025_and_fy2025() -> None:
    observations = tuple(
        _observation(period)
        for period in ("q1_2026", "q1_2025", "fy2025", "fy2024", "fy2023")
    )
    selected = _independent_period_ids(observations)
    assert len(selected) == 4
    assert "q1_2025" in selected
    assert "fy2025" not in selected
    assert set(selected) == {"fy2023", "fy2024", "q1_2025", "q1_2026"}


def test_verified_source_artifacts_build_four_period_inventory(monkeypatch, tmp_path) -> None:
    observations = tuple(
        _observation(period)
        for period in ("q1_2026", "q1_2025", "fy2025", "fy2024", "fy2023")
    )
    revenue = SimpleNamespace(
        ticker="000660",
        evidence_id="r" * 64,
        product_revenue_baseline_eligible=True,
    )
    support = SimpleNamespace(
        ticker="000660",
        evidence_id="s" * 64,
        observations=observations,
        independent_non_overlapping_period_count=4,
        product_profitability_source_fact=False,
        direct_product_profitability_observations=0,
    )
    import alpha_cycle.intelligence.sk_hynix_product_profitability_calibration_inventory as module

    monkeypatch.setattr(module, "load_periodic_product_revenue_certification", lambda *a, **k: revenue)
    monkeypatch.setattr(
        module,
        "load_sec_product_profitability_support_evidence",
        lambda *a, **k: support,
    )
    pointer = tmp_path / "unused.json"
    result = build_skhynix_product_profitability_calibration_inventory(
        evaluation_date=date(2026, 8, 16),
        product_revenue_pointer=pointer,
        profitability_support_pointer=pointer,
    )
    assert result.direct_product_revenue_ready is True
    assert result.direct_product_revenue_evidence_id == "r" * 64
    assert result.direct_product_profitability_periods == ()
    assert len(result.historical_product_revenue_periods) == 4
    assert result.historical_product_revenue_periods == result.company_profitability_constraint_periods
    assert result.cycle_driver_history_periods == ()
    assert result.holdout_periods == ()
    assert result.verified_evidence_ids == ("s" * 64,)
    assert result.source_evidence_verified is True
