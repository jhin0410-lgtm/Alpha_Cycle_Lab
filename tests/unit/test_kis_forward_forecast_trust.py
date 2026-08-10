from __future__ import annotations

from datetime import UTC, date, datetime
from pathlib import Path

import pandas as pd
import pytest

from alpha_cycle.intelligence.decision import InvestmentDecisionSnapshot
from alpha_cycle.intelligence.decision_scoring import DecisionPolicy
from alpha_cycle.intelligence import decision_forward_estimate_calibrated as decision_wrapper
from alpha_cycle.intelligence.kis_forward_forecast_trust import (
    FORECAST_COLUMN_PERIOD_ALIGNMENT_CERTIFIED,
    FORECAST_SCALE_CONTINUITY_CERTIFIED,
    FORWARD_BLOCK_REASON,
    FORWARD_NUMERIC_EVIDENCE_ELIGIBLE,
    require_forward_numeric_evidence_eligible,
)
from alpha_cycle.kis_forward_estimate_cli import run_normalization


def _empty_snapshot() -> InvestmentDecisionSnapshot:
    return InvestmentDecisionSnapshot(
        captured_at=datetime(2026, 8, 10, 5, 0, tzinfo=UTC),
        evaluation_date=date(2026, 8, 10),
        research_snapshot_id="a" * 64,
        market_snapshot_id="b" * 64,
        valuation_snapshot_id=None,
        policy=DecisionPolicy(),
        financial_kpis=pd.DataFrame(),
        financial_mapping=pd.DataFrame(),
        disclosure_events=pd.DataFrame(),
        catalysts=pd.DataFrame(),
        disclosure_summary=pd.DataFrame(),
        macro_regime=pd.DataFrame(),
        market_context=pd.DataFrame(),
        valuation_metrics=pd.DataFrame(),
        financial_history=pd.DataFrame(),
        scorecards=pd.DataFrame(),
        decision_records=pd.DataFrame(),
        report_markdown="# Base report\n",
        warnings=(),
    )


def test_forecast_numeric_evidence_is_fail_closed() -> None:
    assert FORECAST_COLUMN_PERIOD_ALIGNMENT_CERTIFIED is False
    assert FORECAST_SCALE_CONTINUITY_CERTIFIED is False
    assert FORWARD_NUMERIC_EVIDENCE_ELIGIBLE is False
    with pytest.raises(ValueError, match="forecast DATA-column-to-period alignment"):
        require_forward_numeric_evidence_eligible()


def test_forward_normalization_blocks_before_reading_local_artifacts(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="KIS forward numeric evidence is blocked"):
        run_normalization(
            expectation_root=tmp_path / "missing-expectations",
            general_crosscheck_pointer=tmp_path / "missing-general.json",
            owner_crosscheck_pointer=tmp_path / "missing-owner.json",
            output_root=tmp_path / "out",
            now=datetime(2026, 8, 10, 5, 0, tzinfo=UTC),
        )


def test_decision_wrapper_quarantines_existing_forward_pointer(monkeypatch: pytest.MonkeyPatch) -> None:
    base = _empty_snapshot()
    monkeypatch.setattr(decision_wrapper, "_build_industry_snapshot", lambda *args, **kwargs: base)

    result = decision_wrapper.build_investment_decision_snapshot(
        "unused-research",
        "unused-market",
        kis_forward_pointer="even-an-existing-old-pointer-must-not-be-read.json",
    )

    assert result.scorecards.equals(base.scorecards)
    assert result.decision_records.equals(base.decision_records)
    assert f"kis_forward_evidence_blocked:{FORWARD_BLOCK_REASON}" in result.warnings
    assert "KIS forward 실적 추정 증거 (사용 불가)" in result.report_markdown
    assert FORWARD_BLOCK_REASON in result.report_markdown
    assert "forecast DATA 열의 기간 대응" in result.report_markdown
