from __future__ import annotations

from datetime import date
from types import SimpleNamespace

from alpha_cycle.intelligence.sk_hynix_product_profitability_holdout import (
    build_skhynix_product_profitability_holdout_plan,
)


def _observation(period_id: str, start: date, end: date):
    return SimpleNamespace(period_id=period_id, period_start=start, period_end=end)


def _support():
    return SimpleNamespace(
        ticker="000660",
        evidence_id="a" * 64,
        observations=(
            _observation("q1_2026", date(2026, 1, 1), date(2026, 3, 31)),
            _observation("q1_2025", date(2025, 1, 1), date(2025, 3, 31)),
            _observation("fy2025", date(2025, 1, 1), date(2025, 12, 31)),
            _observation("fy2024", date(2024, 1, 1), date(2024, 12, 31)),
            _observation("fy2023", date(2023, 1, 1), date(2023, 12, 31)),
        ),
        independent_non_overlapping_period_count=4,
    )


def test_q1_2026_is_reserved_from_fit_without_claiming_historical_blindness() -> None:
    plan = build_skhynix_product_profitability_holdout_plan(_support())
    assert plan.calibration_period_ids == ("fy2023", "fy2024", "q1_2025")
    assert plan.holdout_period_ids == ("q1_2026",)
    assert plan.holdout_cycle_driver_period_ids == ("2026Q1",)
    assert plan.retrospective_holdout is True
    assert plan.fully_label_blind_historically is False
    assert plan.fit_view_excludes_holdout_profitability_labels is True
    assert plan.validation_view_requires_frozen_method is True
    assert plan.holdout_validation_complete is False
    assert plan.numeric_forecast_enabled is False
    assert plan.decision_score_enabled is False
