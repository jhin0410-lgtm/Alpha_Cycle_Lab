from __future__ import annotations

from datetime import date

import pandas as pd
import pytest

from alpha_cycle.intelligence.pb_roe_valuation_regime import (
    PbRoeValuationRegimeEvidence,
)
from alpha_cycle.intelligence.pb_roe_valuation_regime_readiness import (
    MINIMUM_TTM_ROE_PERCENTILE_OBSERVATIONS,
    append_pb_roe_regime_report,
    apply_pb_roe_history_readiness,
    attach_pb_roe_regime_to_scorecards,
    sync_record_pb_roe_regime_fields,
)


def _base_evidence(observation_count: int) -> PbRoeValuationRegimeEvidence:
    return PbRoeValuationRegimeEvidence(
        evidence_id="a" * 64,
        evaluation_date=date(2026, 8, 14),
        valuation_snapshot_id="b" * 64,
        historical_pb_artifact_id="c" * 64,
        rows=pd.DataFrame(
            [
                {
                    "ticker": "000660",
                    "pb_latest": 7.13,
                    "pb_median": 2.56,
                    "pb_percentile": 87.0,
                    "pb_current_usable": True,
                    "pb_premium_to_median_pct": 178.5,
                    "roe_basis": "consolidated_profitloss_over_average_total_equity",
                    "regime_evidence_available": True,
                    "regime_status": "descriptive_non_scoring",
                    "ttm_roe": 0.612,
                    "ttm_roe_percentile": 100.0,
                    "ttm_roe_p25": 0.20,
                    "ttm_roe_median": 0.35,
                    "ttm_roe_p75": 0.50,
                    "ttm_roe_observation_count": observation_count,
                    "ttm_period_end": date(2026, 3, 31),
                    "ttm_available_date": date(2026, 5, 15),
                    "ttm_roe_lag_days": 91,
                    "pb_minus_roe_percentile_pp": -13.0,
                    "decision_score_enabled": False,
                    "fair_value_estimate_enabled": False,
                    "target_price_enabled": False,
                    "point_in_time_backtest_eligible": False,
                }
            ]
        ),
    )


def test_shallow_roe_history_keeps_level_but_withholds_distribution() -> None:
    evidence = apply_pb_roe_history_readiness(_base_evidence(5))
    row = evidence.rows.iloc[0]

    assert float(row["ttm_roe"]) == pytest.approx(0.612)
    assert int(row["ttm_roe_observation_count"]) == 5
    assert bool(row["ttm_roe_history_ready"]) is False
    assert int(row["ttm_roe_history_minimum_observations"]) == 12
    assert float(row["ttm_roe_percentile_resolution_pct"]) == pytest.approx(20.0)
    assert pd.isna(row["ttm_roe_percentile"])
    assert pd.isna(row["ttm_roe_median"])
    assert pd.isna(row["pb_minus_roe_percentile_pp"])
    assert bool(row["regime_evidence_available"]) is True
    assert str(row["regime_status"]) == (
        "descriptive_level_only_roe_history_insufficient"
    )

    report = append_pb_roe_regime_report("# Base\n", evidence)
    assert "61.2%" in report
    assert "| N/A | 5 | 20.0%p | N/A |" in report
    assert "최소 12개" in report


def test_three_year_quarterly_history_allows_descriptive_percentile() -> None:
    evidence = apply_pb_roe_history_readiness(
        _base_evidence(MINIMUM_TTM_ROE_PERCENTILE_OBSERVATIONS)
    )
    row = evidence.rows.iloc[0]

    assert bool(row["ttm_roe_history_ready"]) is True
    assert float(row["ttm_roe_percentile"]) == pytest.approx(100.0)
    assert float(row["pb_minus_roe_percentile_pp"]) == pytest.approx(-13.0)
    assert float(row["ttm_roe_percentile_resolution_pct"]) == pytest.approx(
        100.0 / 12.0
    )
    assert str(row["regime_status"]) == "descriptive_non_scoring"


def test_readiness_attachment_preserves_scores_and_syncs_metadata() -> None:
    evidence = apply_pb_roe_history_readiness(_base_evidence(5))
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
    assert bool(after.iloc[0]["pb_roe_regime_ttm_roe_history_ready"]) is False

    records = sync_record_pb_roe_regime_fields(
        before.loc[:, ["ticker", "composite_score", "score_coverage"]].copy(),
        after,
    )
    assert "pb_roe_regime_ttm_roe_history_ready" in records.columns
    assert int(records.iloc[0]["pb_roe_regime_ttm_roe_history_minimum_observations"]) == 12
    assert float(records.iloc[0]["composite_score"]) == pytest.approx(3.72)
