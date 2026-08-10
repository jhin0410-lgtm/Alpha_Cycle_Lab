from __future__ import annotations

import json
from datetime import datetime

import pandas as pd

from alpha_cycle.intelligence.kis_forward_decision_evidence import (
    KisForwardDecisionEvidence,
    append_kis_forward_report,
    attach_kis_forward_to_scorecards,
    reconcile_expectation_evidence_gaps,
    sync_record_forward_fields,
)


def _evidence(*, with_change: bool = False) -> KisForwardDecisionEvidence:
    summaries = pd.DataFrame(
        [
            {
                "symbol": "000660",
                "period_label": "2026.12E",
                "fiscal_year": 2026,
                "revenue_krw": 100_000_000_000_000.0,
                "operating_income_krw": 30_000_000_000_000.0,
                "net_income_attributable_to_owners_krw": 22_000_000_000_000.0,
                "operating_margin_pct": 30.0,
            }
        ]
    )
    estimates = pd.DataFrame(
        [
            {
                "symbol": "000660",
                "metric": "revenue",
                "period_label": "2026.12E",
                "growth_from_previous_pct": 20.0,
            },
            {
                "symbol": "000660",
                "metric": "operating_income",
                "period_label": "2026.12E",
                "growth_from_previous_pct": 50.0,
            },
            {
                "symbol": "000660",
                "metric": "net_income_attributable_to_owners",
                "period_label": "2026.12E",
                "growth_from_previous_pct": 40.0,
            },
        ]
    )
    changes = (
        pd.DataFrame(
            [
                {
                    "symbol": "000660",
                    "metric": "operating_income",
                    "period_label": "2026.12E",
                    "percent_change": 2.5,
                    "direction": "up",
                }
            ]
        )
        if with_change
        else pd.DataFrame()
    )
    return KisForwardDecisionEvidence(
        artifact_id="a" * 64,
        source_expectation_snapshot_id="b" * 64,
        source_expectation_captured_at=datetime.fromisoformat(
            "2026-08-10T13:33:13+09:00"
        ),
        summaries=summaries,
        estimates=estimates,
        change_status=(
            "estimate_snapshot_change_available"
            if with_change
            else "estimate_change_baseline_only"
        ),
        changes=changes,
        change_artifact_id="c" * 64 if with_change else "d" * 64,
    )


def _scorecards() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "ticker": "000660",
                "composite_score": 3.75,
                "score_coverage": 0.7,
                "decision_state": "mixed_setup",
                "evidence_gaps": json.dumps(
                    [
                        "컨센서스·실적 추정치 상향·하향 데이터 미연결",
                        "향후 촉매의 확정 일정·시장 기대치 데이터 미연결",
                    ],
                    ensure_ascii=False,
                ),
            },
            {
                "ticker": "035420",
                "composite_score": 3.25,
                "score_coverage": 0.7,
                "decision_state": "mixed_setup",
                "evidence_gaps": json.dumps(
                    ["컨센서스·실적 추정치 상향·하향 데이터 미연결"],
                    ensure_ascii=False,
                ),
            },
        ]
    )


def test_forward_evidence_is_non_scoring_and_narrows_gap_only_for_applicable_ticker() -> None:
    original = _scorecards()
    attached = attach_kis_forward_to_scorecards(original, _evidence())
    reconciled = reconcile_expectation_evidence_gaps(attached)

    assert reconciled["composite_score"].tolist() == original["composite_score"].tolist()
    assert reconciled["score_coverage"].tolist() == original["score_coverage"].tolist()
    hynix = reconciled.loc[reconciled["ticker"].astype(str).eq("000660")].iloc[0]
    naver = reconciled.loc[reconciled["ticker"].astype(str).eq("035420")].iloc[0]
    assert bool(hynix["kis_forward_evidence_available"]) is True
    assert bool(hynix["kis_forward_decision_score_enabled"]) is False
    assert "KIS forward 실적 추정 level 연결됨" in hynix["evidence_gaps"]
    assert "시장 컨센서스 출처" in hynix["evidence_gaps"]
    assert bool(naver["kis_forward_evidence_available"]) is False
    assert "컨센서스·실적 추정치 상향·하향 데이터 미연결" in naver["evidence_gaps"]


def test_verified_snapshot_change_still_keeps_consensus_gap_and_score_unchanged() -> None:
    original = _scorecards()
    reconciled = reconcile_expectation_evidence_gaps(
        attach_kis_forward_to_scorecards(original, _evidence(with_change=True))
    )
    hynix = reconciled.loc[reconciled["ticker"].astype(str).eq("000660")].iloc[0]

    assert hynix["composite_score"] == original.iloc[0]["composite_score"]
    assert bool(hynix["kis_estimate_snapshot_change_verified"]) is True
    assert "KIS forward 실적 추정 level·snapshot change 연결됨" in hynix["evidence_gaps"]
    assert "시장 컨센서스 출처 미확인" in hynix["evidence_gaps"]


def test_forward_fields_and_reconciled_gap_sync_to_compact_records() -> None:
    scorecards = reconcile_expectation_evidence_gaps(
        attach_kis_forward_to_scorecards(_scorecards(), _evidence())
    )
    records = pd.DataFrame(
        [
            {"ticker": "000660", "evidence_gaps": "old", "decision_state": "mixed_setup"},
            {"ticker": "035420", "evidence_gaps": "old", "decision_state": "mixed_setup"},
        ]
    )
    synced = sync_record_forward_fields(records, scorecards)
    hynix = synced.loc[synced["ticker"].astype(str).eq("000660")].iloc[0]

    assert "KIS forward 실적 추정 level 연결됨" in hynix["evidence_gaps"]
    assert bool(hynix["kis_forward_evidence_available"]) is True
    assert hynix["decision_state"] == "mixed_setup"


def test_report_labels_forward_levels_as_non_scoring_and_non_consensus() -> None:
    report = append_kis_forward_report("# Decision\n", _evidence())

    assert "## KIS forward 실적 추정 증거 (비점수)" in report
    assert "100.00조원" in report
    assert "30.00조원" in report
    assert "시장 컨센서스 출처·집계 방법은 인증되지 않았습니다" in report
    assert "baseline-only" in report
