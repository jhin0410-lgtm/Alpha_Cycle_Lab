"""Tests for partial-evidence score calibration and report semantics."""

from __future__ import annotations

import json

import pandas as pd
import pytest

from alpha_cycle.intelligence.decision_scoring import DecisionPolicy
from alpha_cycle.intelligence.evidence_coverage_policy import (
    apply_evidence_coverage_policy,
    apply_evidence_report_policy,
)


def _scorecard(**overrides: object) -> pd.DataFrame:
    row: dict[str, object] = {
        "ticker": "000660",
        "earnings_momentum_score": 4.5,
        "financial_quality_score": 4.5,
        "catalyst_score": None,
        "market_timing_score": None,
        "macro_fit_score": 3.675,
        "valuation_score": None,
        "composite_score": 4.35,
        "score_coverage": 0.55,
        "decision_state": "positive_setup",
        "action_bias": "fundamental_positive_wait_for_adjusted_timing",
        "positive_evidence": json.dumps(["강한 관측 실적"], ensure_ascii=False),
        "opposing_evidence": json.dumps([], ensure_ascii=False),
    }
    row.update(overrides)
    return pd.DataFrame([row])


def test_partial_evidence_is_neutral_imputed_instead_of_renormalized() -> None:
    calibrated = apply_evidence_coverage_policy(_scorecard(), DecisionPolicy())
    row = calibrated.iloc[0]

    assert row["observed_component_score"] == pytest.approx(4.35)
    assert row["evidence_adjusted_score"] == pytest.approx(3.7425)
    assert row["composite_score"] == pytest.approx(3.7425)
    assert row["missing_component_weight"] == pytest.approx(0.45)
    assert row["decision_state"] == "mixed_setup"
    assert row["action_bias"] == "fundamental_mixed_wait_for_adjusted_timing"
    assert "미연결 점수 가중치 45.0%" in row["opposing_evidence"]


def test_full_coverage_score_is_unchanged() -> None:
    full = _scorecard(
        earnings_momentum_score=4.0,
        financial_quality_score=4.0,
        catalyst_score=4.0,
        market_timing_score=4.0,
        macro_fit_score=4.0,
        valuation_score=4.0,
        composite_score=4.0,
        score_coverage=1.0,
        action_bias="fundamental_positive_timing_confirmed",
    )
    row = apply_evidence_coverage_policy(full, DecisionPolicy()).iloc[0]

    assert row["observed_component_score"] == pytest.approx(4.0)
    assert row["evidence_adjusted_score"] == pytest.approx(4.0)
    assert row["missing_component_weight"] == pytest.approx(0.0)
    assert row["decision_state"] == "positive_setup"
    assert row["action_bias"] == "fundamental_positive_timing_confirmed"


def test_report_distinguishes_annual_and_single_quarter_yoy() -> None:
    scorecards = apply_evidence_coverage_policy(_scorecard(), DecisionPolicy())
    financial_kpis = pd.DataFrame(
        [
            {
                "ticker": "000660",
                "revenue": 1000.0,
                "operating_income": 400.0,
                "net_income": 300.0,
                "equity": 700.0,
            }
        ]
    )
    financial_history = pd.DataFrame(
        [
            {
                "ticker": "000660",
                "business_year": 2025,
                "period_label": "FY",
                "period_end": "2025-12-31",
                "derived": False,
                "revenue": 1000.0,
                "operating_income": 400.0,
                "net_income": 300.0,
                "equity": 700.0,
            },
            {
                "ticker": "000660",
                "business_year": 2026,
                "period_label": "Q1",
                "period_end": "2026-03-31",
                "derived": False,
                "revenue": 300.0,
                "operating_income": 180.0,
                "net_income": 140.0,
                "equity": 850.0,
            },
        ]
    )
    coverage_notice = (
        "- 점수 항목 커버리지는 전체 투자정보 완성도가 아니라 "
        "현재 연결된 점수 입력의 가용 비중"
    )
    report = "\n".join(
        [
            "# Alpha Cycle 투자 의사결정 리포트",
            "",
            coverage_notice,
            "",
            "## 000660",
            "",
            "### 1. 핵심 결론",
            "",
            "- 종합점수: 4.35/5",
            "",
            "### 2. 실적과 재무",
            "",
            "- 매출 YoY: 46.8%",
            "- 영업이익 YoY: 101.2%",
            "",
            "## 밸류에이션 및 다기간 실적",
            "",
            "### 000660",
            "",
            "- 최근 분기: 2026 Q1",
            "- 매출 YoY: 198.1%",
            "- 영업이익 YoY: 405.5%",
        ]
    )

    adjusted = apply_evidence_report_policy(
        report,
        scorecards,
        financial_kpis,
        financial_history,
    )

    assert "- 증거조정 종합점수: 3.74/5" in adjusted
    assert "- 관측 항목 평균: 4.35/5" in adjusted
    assert "- 미연결 점수 가중치: 45.0% (중립 3.0 반영)" in adjusted
    assert "- 기준 기간: 2025 FY 연간 실적(2024 FY 대비)" in adjusted
    assert "- 매출 YoY (2025 FY vs 2024 FY): 46.8%" in adjusted
    assert "- 최근 분기 기준: 2026 Q1 단일 분기(2025 Q1 대비)" in adjusted
    assert "- 매출 YoY (단일 분기, 전년 동기 대비): 198.1%" in adjusted
