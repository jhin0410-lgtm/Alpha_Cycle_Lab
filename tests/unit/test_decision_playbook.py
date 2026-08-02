"""Tests for deterministic investment execution playbooks."""

from __future__ import annotations

import json
from datetime import date

import pandas as pd

from alpha_cycle.intelligence.decision_playbook import (
    append_execution_playbook_report,
    build_decision_records,
    enrich_scorecards_with_playbook,
)


def _scorecards() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "ticker": "005930",
                "decision_state": "positive_setup",
                "action_bias": "fundamental_positive_timing_confirmed",
                "composite_score": 4.1,
                "score_coverage": 1.0,
                "earnings_momentum_score": 4.5,
                "financial_quality_score": 4.0,
                "catalyst_score": 4.0,
                "market_timing_score": 4.0,
                "macro_fit_score": 3.5,
                "valuation_score": 3.8,
                "valuation_status": "complete_peer_relative_scored",
                "positive_evidence": json.dumps(["영업이익 증가"], ensure_ascii=False),
                "opposing_evidence": json.dumps([], ensure_ascii=False),
                "invalidation_triggers": json.dumps(
                    ["영업이익 YoY가 0% 이하로 전환"],
                    ensure_ascii=False,
                ),
            },
            {
                "ticker": "000660",
                "decision_state": "negative_setup",
                "action_bias": "avoid_or_reduce_candidate",
                "composite_score": 2.2,
                "score_coverage": 0.85,
                "earnings_momentum_score": 2.0,
                "financial_quality_score": 3.0,
                "catalyst_score": 2.0,
                "market_timing_score": 1.5,
                "macro_fit_score": 3.0,
                "valuation_score": None,
                "valuation_status": "valuation_not_available",
                "positive_evidence": json.dumps([], ensure_ascii=False),
                "opposing_evidence": json.dumps(["20일 약세"], ensure_ascii=False),
                "invalidation_triggers": json.dumps(
                    ["영업이익률이 추가로 3%p 이상 악화"],
                    ensure_ascii=False,
                ),
            },
        ]
    )


def _financials() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "ticker": "005930",
                "revenue_yoy": 0.18,
                "operating_income_yoy": 0.35,
                "operating_margin_change_pp": 2.0,
                "inventory_growth": 0.12,
                "receivables_growth": 0.10,
            },
            {
                "ticker": "000660",
                "revenue_yoy": -0.05,
                "operating_income_yoy": -0.30,
                "operating_margin_change_pp": -4.0,
                "inventory_growth": 0.20,
                "receivables_growth": 0.18,
            },
        ]
    )


def _catalysts() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "ticker": "005930",
                "receipt_date": date(2026, 7, 20),
                "category": "contract_order",
                "priority": "critical",
                "material_score": 5,
                "report_name": "단일판매ㆍ공급계약체결",
                "is_correction": False,
            },
            {
                "ticker": "000660",
                "receipt_date": date(2026, 7, 25),
                "category": "operational_risk",
                "priority": "critical",
                "material_score": 5,
                "report_name": "생산중단",
                "is_correction": True,
            },
        ]
    )


def _market() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "ticker": "005930",
                "last_price": 100.0,
                "return_20": 0.12,
                "price_to_sma_20": 0.05,
                "relative_strength_rank_20": 0.8,
            },
            {
                "ticker": "000660",
                "last_price": 80.0,
                "return_20": -0.15,
                "price_to_sma_20": -0.08,
                "relative_strength_rank_20": 0.2,
            },
        ]
    )


def test_playbook_translates_snapshot_evidence_into_action_conditions() -> None:
    enriched = enrich_scorecards_with_playbook(
        _scorecards(),
        _financials(),
        _catalysts(),
        _market(),
        evaluation_date=date(2026, 8, 3),
    )

    samsung = enriched.loc[enriched["ticker"].astype(str).eq("005930")].iloc[0]
    assert samsung["action_readiness"] == "position_review_ready"
    assert samsung["review_priority"] == "normal"
    assert "단일판매ㆍ공급계약체결" in str(samsung["known_catalysts"])
    assert "수주가 매출과 영업이익으로 실제 전환" in str(samsung["monitor_3_6m"])
    assert samsung["playbook_basis"] == (
        "deterministic_snapshot_rules_no_future_event_dates"
    )

    hynix = enriched.loc[enriched["ticker"].astype(str).eq("000660")].iloc[0]
    assert hynix["action_readiness"] == "avoid_or_reduce_review"
    assert hynix["review_priority"] == "urgent"
    assert "신규 진입 보류" in str(hynix["entry_conditions"])
    assert "운영 중단·소송·회생 관련 정상화" in str(hynix["monitor_0_3m"])


def test_decision_records_preserve_playbook_and_reference_prices() -> None:
    enriched = enrich_scorecards_with_playbook(
        _scorecards(),
        _financials(),
        _catalysts(),
        _market(),
        evaluation_date=date(2026, 8, 3),
    )
    records = build_decision_records(
        enriched,
        evaluation_date=date(2026, 8, 3),
        price_lookup={"005930": 100.0, "000660": 80.0},
    )

    assert list(records["reference_price"]) == [80.0, 100.0]
    assert "monitor_0_3m" in records.columns
    assert "exit_conditions" in records.columns
    assert set(records["action_readiness"]) == {
        "position_review_ready",
        "avoid_or_reduce_review",
    }


def test_report_append_exposes_horizons_without_target_price_claims() -> None:
    enriched = enrich_scorecards_with_playbook(
        _scorecards(),
        _financials(),
        _catalysts(),
        _market(),
        evaluation_date=date(2026, 8, 3),
    )
    report = append_execution_playbook_report("# Existing report\n", enriched)

    assert "## 실행 플레이북" in report
    assert "0~3개월 확인 항목" in report
    assert "3~6개월 확인 항목" in report
    assert "6~12개월 확인 항목" in report
    assert "미래 공시일·목표주가를 추정하지 않고" in report
    assert "실제 주문 기능은 비활성화" in report
