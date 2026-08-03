"""Tests for correction priority and evidence-scope calibration."""

from __future__ import annotations

import json
from datetime import date

import pandas as pd

from alpha_cycle.intelligence.decision_calibration import (
    calibrate_decision_scorecards,
    clarify_report_coverage,
)


def _scorecards() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "ticker": "000660",
                "decision_state": "positive_setup",
                "review_priority": "urgent",
                "valuation_status": "insufficient_peer_universe",
                "evidence_gaps": json.dumps([], ensure_ascii=False),
            },
            {
                "ticker": "005930",
                "decision_state": "mixed_setup",
                "review_priority": "urgent",
                "valuation_status": "insufficient_peer_universe",
                "evidence_gaps": json.dumps([], ensure_ascii=False),
            },
            {
                "ticker": "035420",
                "decision_state": "mixed_setup",
                "review_priority": "urgent",
                "valuation_status": "complete_unscored",
                "evidence_gaps": json.dumps([], ensure_ascii=False),
            },
        ]
    )


def _catalysts() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "ticker": "000660",
                "receipt_date": date(2026, 3, 3),
                "age_days": 153,
                "category": "capex_investment",
                "is_correction": True,
            },
            {
                "ticker": "005930",
                "receipt_date": date(2026, 7, 30),
                "age_days": 4,
                "category": "earnings",
                "is_correction": True,
            },
            {
                "ticker": "035420",
                "receipt_date": date(2026, 7, 25),
                "age_days": 9,
                "category": "operational_risk",
                "is_correction": False,
            },
        ]
    )


def test_correction_priority_depends_on_recency_and_risk_category() -> None:
    calibrated = calibrate_decision_scorecards(
        _scorecards(),
        _catalysts(),
        evaluation_date=date(2026, 8, 3),
    ).set_index("ticker")

    assert calibrated.loc["000660", "review_priority"] == "normal"
    assert calibrated.loc["005930", "review_priority"] == "high"
    assert calibrated.loc["035420", "review_priority"] == "urgent"


def test_external_evidence_gaps_are_never_reported_as_complete() -> None:
    calibrated = calibrate_decision_scorecards(
        _scorecards(),
        _catalysts(),
        evaluation_date=date(2026, 8, 3),
    ).set_index("ticker")

    gaps = json.loads(str(calibrated.loc["005930", "evidence_gaps"]))
    assert "컨센서스·실적 추정치 상향·하향 데이터 미연결" in gaps
    assert "기관·외국인 수급 데이터 미연결" in gaps
    assert "정정공시 본문·변경 수치·투자 영향 미분석" in gaps
    assert "상대 밸류에이션 비교기업 수 부족" in gaps
    assert calibrated.loc["005930", "evidence_scope_status"] == (
        "partial_external_data"
    )


def test_report_calls_score_coverage_by_its_actual_scope() -> None:
    report = clarify_report_coverage(
        "# report\n"
        "- 밸류에이션 연결·컨센서스 미연결; 최종 매수 판단이 아닌 의사결정 보조\n"
        "- 데이터 커버리지: 100.0%\n"
    )

    assert "- 연결 점수 항목 커버리지: 100.0%" in report
    assert "전체 투자정보 완성도가 아니라" in report
    assert "- 데이터 커버리지:" not in report
