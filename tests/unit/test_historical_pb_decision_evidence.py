from __future__ import annotations

import json
from datetime import UTC, date, datetime
from pathlib import Path

import pandas as pd
import pytest

from alpha_cycle.intelligence import decision_historical_pb_calibrated as wrapper
from alpha_cycle.intelligence.decision import InvestmentDecisionSnapshot
from alpha_cycle.intelligence.decision_scoring import DecisionPolicy


def _write_pb_artifact(tmp_path: Path) -> Path:
    artifact_id = "a" * 64
    directory = tmp_path / "pb-artifact"
    directory.mkdir()
    summary = pd.DataFrame(
        [
            {
                "ticker": "000660",
                "observation_count": 544,
                "first_date": "2024-05-16",
                "last_date": "2026-08-10",
                "latest_pb": 6.1567,
                "pb_min": 1.6231,
                "pb_p25": 2.1757,
                "pb_median": 2.5522,
                "pb_p75": 5.3911,
                "pb_max": 12.6559,
                "latest_pb_percentile": 80.5147,
                "band_status": "observational_2y_ready",
            },
            {
                "ticker": "005930",
                "observation_count": 544,
                "first_date": "2024-05-16",
                "last_date": "2026-08-10",
                "latest_pb": 3.0862,
                "pb_min": 0.8627,
                "pb_p25": 0.9852,
                "pb_median": 1.3444,
                "pb_p75": 2.3524,
                "pb_max": 4.7927,
                "latest_pb_percentile": 85.1103,
                "band_status": "observational_2y_ready",
            },
        ]
    )
    summary_path = directory / "historical_pb_summary.csv"
    summary.to_csv(summary_path, index=False)
    manifest_path = directory / "manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "status": "historical_pb_observational_evidence_built",
                "artifact_id": artifact_id,
                "evaluation_date": "2026-08-10",
                "warnings": [],
            }
        ),
        encoding="utf-8",
    )
    pointer_path = tmp_path / "latest_historical_pb_evidence.json"
    pointer_path.write_text(
        json.dumps(
            {
                "status": "historical_pb_observational_evidence_built",
                "artifact_id": artifact_id,
                "artifact_directory": str(directory),
                "manifest_path": str(manifest_path),
                "summary_path": str(summary_path),
                "evaluation_date": "2026-08-10",
                "historical_vintage_certified": False,
                "point_in_time_backtest_eligible": False,
                "fair_value_estimate_enabled": False,
                "target_price_enabled": False,
                "decision_score_enabled": False,
                "account_api_enabled": False,
                "holdings_api_enabled": False,
                "balance_api_enabled": False,
                "order_api_enabled": False,
            }
        ),
        encoding="utf-8",
    )
    return pointer_path


def _base_snapshot() -> InvestmentDecisionSnapshot:
    scorecards = pd.DataFrame(
        [
            {
                "ticker": "000660",
                "composite_score": 4.05,
                "score_coverage": 0.85,
                "valuation_score": pd.NA,
                "valuation_status": "complete_unscored",
            },
            {
                "ticker": "005930",
                "composite_score": 3.80,
                "score_coverage": 0.85,
                "valuation_score": pd.NA,
                "valuation_status": "complete_unscored",
            },
        ]
    )
    records = scorecards.loc[:, ["ticker", "composite_score", "score_coverage"]].copy()
    empty = pd.DataFrame()
    return InvestmentDecisionSnapshot(
        captured_at=datetime(2026, 8, 10, 9, 0, tzinfo=UTC),
        evaluation_date=date(2026, 8, 10),
        research_snapshot_id="b" * 64,
        market_snapshot_id="c" * 64,
        valuation_snapshot_id="d" * 64,
        policy=DecisionPolicy(),
        financial_kpis=empty,
        financial_mapping=empty,
        disclosure_events=empty,
        catalysts=empty,
        disclosure_summary=empty,
        macro_regime=empty,
        market_context=empty,
        valuation_metrics=empty,
        financial_history=empty,
        scorecards=scorecards,
        decision_records=records,
        report_markdown="# Base report\n",
        warnings=(),
    )


def test_historical_pb_wrapper_attaches_current_bands_without_changing_scores(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pointer = _write_pb_artifact(tmp_path)
    before = _base_snapshot()
    monkeypatch.setattr(wrapper, "_build_forward_snapshot", lambda *args, **kwargs: before)

    after = wrapper.build_investment_decision_snapshot(
        "unused-research",
        "unused-market",
        historical_pb_pointer=pointer,
    )

    pd.testing.assert_series_equal(
        after.scorecards["composite_score"],
        before.scorecards["composite_score"],
        check_names=False,
    )
    pd.testing.assert_series_equal(
        after.scorecards["score_coverage"],
        before.scorecards["score_coverage"],
        check_names=False,
    )
    assert after.scorecards["valuation_score"].isna().all()
    assert set(after.scorecards["valuation_status"].astype(str)) == {"complete_unscored"}
    assert after.scorecards["historical_pb_evidence_available"].astype(bool).all()
    hynix = after.scorecards.loc[after.scorecards["ticker"].astype(str).eq("000660")].iloc[0]
    samsung = after.scorecards.loc[after.scorecards["ticker"].astype(str).eq("005930")].iloc[0]
    assert float(hynix["historical_pb_latest_pb"]) == pytest.approx(6.1567)
    assert float(hynix["historical_pb_latest_pb_percentile"]) == pytest.approx(80.5147)
    assert float(samsung["historical_pb_latest_pb"]) == pytest.approx(3.0862)
    assert float(samsung["historical_pb_latest_pb_percentile"]) == pytest.approx(85.1103)
    assert not after.scorecards["historical_pb_decision_score_enabled"].astype(bool).any()
    assert "## 자사 역사 P/B 증거 (비점수)" in after.report_markdown
    assert "6.16x" in after.report_markdown
    assert "85.1%" in after.report_markdown
    assert "historical_pb_own_history_observational_non_scoring" in after.warnings
    assert "historical_pb_latest_pb" in after.decision_records.columns


def test_historical_pb_wrapper_rejects_mismatched_evaluation_date(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pointer = _write_pb_artifact(tmp_path)
    before = _base_snapshot()
    changed = InvestmentDecisionSnapshot(
        **{
            **before.__dict__,
            "evaluation_date": date(2026, 8, 9),
        }
    )
    monkeypatch.setattr(wrapper, "_build_forward_snapshot", lambda *args, **kwargs: changed)

    after = wrapper.build_investment_decision_snapshot(
        "unused-research",
        "unused-market",
        historical_pb_pointer=pointer,
    )

    assert after.scorecards.equals(changed.scorecards)
    assert "historical_pb_evidence_unavailable:ValueError" in after.warnings
    assert "## 자사 역사 P/B 증거 (사용 불가)" in after.report_markdown
