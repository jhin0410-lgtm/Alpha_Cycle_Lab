"""Tests for correction priority and evidence-scope calibration."""

from __future__ import annotations

import json
from datetime import date

import pandas as pd

from alpha_cycle.intelligence.decision_calibration import (
    append_review_priority_audit,
    attach_priority_audit_to_records,
    calibrate_decision_scorecards,
    clarify_report_coverage,
    clarify_valuation_report,
)


def _scorecards() -> pd.DataFrame:
    duplicate_gaps = json.dumps(
        [
            "밸류에이션 미평가",
            "밸류에이션 근거 불완전: insufficient_peer_universe",
            "상대 밸류에이션 비교기업 수 부족",
        ],
        ensure_ascii=False,
    )
    return pd.DataFrame(
        [
            {
                "ticker": "000660",
                "decision_state": "positive_setup",
                "review_priority": "urgent",
                "valuation_status": "insufficient_peer_universe",
                "valuation_peer_count": 2,
                "valuation_peer_minimum": 5,
                "evidence_gaps": duplicate_gaps,
            },
            {
                "ticker": "005930",
                "decision_state": "mixed_setup",
                "review_priority": "urgent",
                "valuation_status": "insufficient_peer_universe",
                "valuation_peer_count": 2,
                "valuation_peer_minimum": 5,
                "evidence_gaps": duplicate_gaps,
            },
            {
                "ticker": "035420",
                "decision_state": "mixed_setup",
                "review_priority": "urgent",
                "valuation_status": "complete_unscored",
                "valuation_peer_count": 5,
                "valuation_peer_minimum": 5,
                "evidence_gaps": json.dumps([], ensure_ascii=False),
            },
        ]
    )


def _catalysts() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "ticker": "000660",
                "receipt_date": "20260303",
                "age_days": 1,
                "category": "capex_investment",
                "report_name": "[기재정정]타법인주식및출자증권취득결정",
                "is_correction": True,
            },
            {
                "ticker": "000660",
                "receipt_date": date(2026, 7, 29),
                "age_days": 5,
                "category": "earnings",
                "report_name": "연결재무제표기준영업(잠정)실적(공정공시)",
                "is_correction": "False",
            },
            {
                "ticker": "005930",
                "receipt_date": date(2026, 7, 30),
                "age_days": 100,
                "category": "earnings",
                "report_name": "[기재정정]연결재무제표기준영업(잠정)실적(공정공시)",
                "is_correction": "False",
            },
            {
                "ticker": "035420",
                "receipt_date": date(2026, 7, 25),
                "age_days": 9,
                "category": "operational_risk",
                "report_name": "생산중단",
                "is_correction": False,
            },
        ]
    )


def _calibrated() -> pd.DataFrame:
    return calibrate_decision_scorecards(
        _scorecards(),
        _catalysts(),
        evaluation_date=date(2026, 8, 3),
    )


def test_correction_priority_uses_title_and_receipt_date() -> None:
    calibrated = _calibrated().set_index("ticker")

    assert calibrated.loc["000660", "review_priority"] == "normal"
    assert calibrated.loc["000660", "review_priority_reason"] == (
        "중요 공시 또는 긍정 상태 정기 검토"
    )
    assert calibrated.loc["005930", "review_priority"] == "high"
    assert calibrated.loc["005930", "review_priority_reason"] == (
        "최근 30일 이내 정정공시 존재"
    )
    assert "2026-07-30" in str(
        calibrated.loc["005930", "review_priority_evidence"]
    )
    assert calibrated.loc["035420", "review_priority"] == "urgent"
    assert calibrated.loc["035420", "review_priority_reason"] == (
        "운영 리스크 공시 존재"
    )


def test_false_like_correction_flag_does_not_override_normal_title() -> None:
    calibrated = _calibrated().set_index("ticker")

    assert calibrated.loc["000660", "review_priority"] == "normal"
    evidence = json.loads(
        str(calibrated.loc["000660", "review_priority_evidence"])
    )
    assert evidence == []


def test_external_evidence_gaps_are_specific_and_deduplicated() -> None:
    calibrated = _calibrated().set_index("ticker")

    gaps = json.loads(str(calibrated.loc["005930", "evidence_gaps"]))
    assert "컨센서스·실적 추정치 상향·하향 데이터 미연결" in gaps
    assert "기관·외국인 수급 데이터 미연결" in gaps
    assert "정정공시 본문·변경 수치·투자 영향 미분석" in gaps
    assert "상대 밸류에이션 비교기업 수 부족 (2개/최소 5개)" in gaps
    assert "밸류에이션 미평가" not in gaps
    assert "밸류에이션 근거 불완전: insufficient_peer_universe" not in gaps
    assert gaps.count("상대 밸류에이션 비교기업 수 부족 (2개/최소 5개)") == 1
    assert calibrated.loc["005930", "evidence_scope_status"] == (
        "partial_external_data"
    )


def test_priority_audit_is_carried_into_decision_records() -> None:
    scorecards = _calibrated()
    records = attach_priority_audit_to_records(
        pd.DataFrame(
            [
                {"ticker": "000660", "review_priority": "normal"},
                {"ticker": "005930", "review_priority": "high"},
                {"ticker": "035420", "review_priority": "urgent"},
            ]
        ),
        scorecards,
    ).set_index("ticker")

    assert records.loc["005930", "review_priority_reason"] == (
        "최근 30일 이내 정정공시 존재"
    )
    assert "2026-07-30" in str(records.loc["005930", "review_priority_evidence"])


def test_playbook_report_exposes_priority_reason_and_trigger() -> None:
    report = append_review_priority_audit(
        "## 실행 플레이북\n\n"
        "### 005930\n\n"
        "- 행동 준비도: **wait_for_timing_confirmation**\n"
        "- 재검토 우선순위: **high**\n",
        _calibrated(),
    )

    assert "- 우선순위 근거: 최근 30일 이내 정정공시 존재" in report
    assert "- 우선순위 촉발 공시" in report
    assert "[기재정정]연결재무제표기준영업" in report


def test_report_calls_score_coverage_by_its_actual_scope() -> None:
    report = clarify_report_coverage(
        "# report\n"
        "- 밸류에이션 연결·컨센서스 미연결; 최종 매수 판단이 아닌 의사결정 보조\n"
        "- 데이터 커버리지: 100.0%\n"
    )

    assert "- 연결 점수 항목 커버리지: 100.0%" in report
    assert "전체 투자정보 완성도가 아니라" in report
    assert "- 데이터 커버리지:" not in report


def test_valuation_report_explains_why_relative_score_is_missing() -> None:
    report = clarify_valuation_report(
        "## 밸류에이션 및 다기간 실적\n\n"
        "### 000660\n\n"
        "- 밸류에이션 상태: insufficient_peer_universe\n"
        "- 밸류에이션 점수: 미평가\n"
        "- 점수는 완전한 기업끼리의 상대순위를 중립값으로 축소한 값\n",
        pd.DataFrame(
            [
                {
                    "ticker": "000660",
                    "valuation_status": "insufficient_peer_universe",
                    "valuation_peer_count": 2,
                    "valuation_peer_minimum": 5,
                }
            ]
        ),
    )

    assert "- 상대 점수 미산출: 비교기업 2개 / 최소 5개 필요" in report
    assert "- 점수는 완전한 기업끼리의 상대순위를" not in report
