from __future__ import annotations

from datetime import date

import pandas as pd
import pytest

from alpha_cycle.intelligence.historical_pb_decision_evidence import (
    HistoricalPbDecisionEvidence,
)
from alpha_cycle.intelligence.pb_roe_valuation_regime import (
    append_pb_roe_regime_report,
    attach_pb_roe_regime_to_scorecards,
    build_pb_roe_valuation_regime_evidence,
    sync_record_pb_roe_regime_fields,
)


def _historical_pb() -> HistoricalPbDecisionEvidence:
    return HistoricalPbDecisionEvidence(
        artifact_id="a" * 64,
        evaluation_date=date(2026, 8, 14),
        symbols=pd.DataFrame(
            [
                {
                    "ticker": "000660",
                    "observation_count": 548,
                    "first_date": "2024-05-16",
                    "last_date": "2026-08-14",
                    "latest_observation_lag_days": 0,
                    "current_observation_available": True,
                    "historical_band_status": "observational_2y_ready",
                    "historical_band_history_ready": True,
                    "current_observational_band_usable": True,
                    "latest_pb": 7.13,
                    "pb_min": 1.62,
                    "pb_p25": 2.18,
                    "pb_median": 2.56,
                    "pb_p75": 5.41,
                    "pb_max": 12.66,
                    "latest_pb_percentile": 87.0,
                }
            ]
        ),
    )


def _history() -> pd.DataFrame:
    rows = [
        (2024, "Q1", "2024-03-31", "2024-05-15", False, 10.0, 100.0),
        (2024, "Q2", "2024-06-30", "2024-08-14", False, 12.0, 110.0),
        (2024, "Q3", "2024-09-30", "2024-11-14", False, 14.0, 120.0),
        (2024, "FY", "2024-12-31", "2025-03-10", False, 60.0, 130.0),
        (2024, "Q4", "2024-12-31", "2025-03-10", True, 24.0, 130.0),
        (2025, "Q1", "2025-03-31", "2025-05-15", False, 20.0, 150.0),
        (2025, "Q2", "2025-06-30", "2025-08-14", False, 22.0, 160.0),
        (2025, "Q3", "2025-09-30", "2025-11-14", False, 24.0, 170.0),
        (2025, "FY", "2025-12-31", "2026-03-10", False, 100.0, 180.0),
        (2025, "Q4", "2025-12-31", "2026-03-10", True, 34.0, 180.0),
        (2026, "Q1", "2026-03-31", "2026-05-15", False, 40.0, 200.0),
        # Future-visible row must not affect the 2026-08-14 decision.
        (2026, "Q2", "2026-06-30", "2026-08-20", False, 500.0, 210.0),
    ]
    return pd.DataFrame(
        [
            {
                "ticker": "000660",
                "business_year": year,
                "period_label": label,
                "period_end": period_end,
                "available_date": available_date,
                "derived": derived,
                "net_income": net_income,
                "equity": equity,
            }
            for year, label, period_end, available_date, derived, net_income, equity in rows
        ]
    )


def test_pb_roe_regime_uses_visible_ttm_flows_and_non_derived_equity() -> None:
    evidence = build_pb_roe_valuation_regime_evidence(
        _history(),
        _historical_pb(),
        evaluation_date=date(2026, 8, 14),
        valuation_snapshot_id="b" * 64,
    )

    assert evidence.decision_score_enabled is False
    assert evidence.fair_value_estimate_enabled is False
    assert evidence.target_price_enabled is False
    assert evidence.point_in_time_backtest_eligible is False
    row = evidence.rows.iloc[0]
    # 2025Q2 + 2025Q3 + 2025Q4 + 2026Q1 = 120; average equity=(150+200)/2=175.
    assert float(row["ttm_roe"]) == pytest.approx(120.0 / 175.0)
    assert str(row["ttm_period_end"]) == "2026-03-31"
    assert str(row["ttm_available_date"]) == "2026-05-15"
    assert int(row["ttm_roe_lag_days"]) == 91
    assert int(row["ttm_roe_observation_count"]) == 5
    assert float(row["ttm_roe_percentile"]) == pytest.approx(100.0)
    assert float(row["pb_minus_roe_percentile_pp"]) == pytest.approx(-13.0)
    assert bool(row["regime_evidence_available"]) is True
    assert str(row["regime_status"]) == "descriptive_non_scoring"


def test_pb_roe_regime_attachment_does_not_change_scores() -> None:
    evidence = build_pb_roe_valuation_regime_evidence(
        _history(),
        _historical_pb(),
        evaluation_date=date(2026, 8, 14),
        valuation_snapshot_id="b" * 64,
    )
    before = pd.DataFrame(
        [
            {
                "ticker": "000660",
                "composite_score": 3.72,
                "score_coverage": 0.70,
                "valuation_score": pd.NA,
            }
        ]
    )
    after = attach_pb_roe_regime_to_scorecards(before, evidence)

    assert float(after.iloc[0]["composite_score"]) == pytest.approx(3.72)
    assert float(after.iloc[0]["score_coverage"]) == pytest.approx(0.70)
    assert pd.isna(after.iloc[0]["valuation_score"])
    assert bool(after.iloc[0]["pb_roe_regime_regime_evidence_available"]) is True
    assert bool(after.iloc[0]["pb_roe_regime_decision_score_enabled"]) is False

    records = sync_record_pb_roe_regime_fields(
        before.loc[:, ["ticker", "composite_score", "score_coverage"]].copy(),
        after,
    )
    assert "pb_roe_regime_ttm_roe" in records.columns
    assert float(records.iloc[0]["composite_score"]) == pytest.approx(3.72)

    report = append_pb_roe_regime_report("# Base\n", evidence)
    assert "## P/B-ROE 밸류에이션 레짐 (비점수)" in report
    assert "68.6%" in report
    assert "87.0%" in report
    assert "fair value" in report
