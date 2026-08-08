"""Tests for non-scoring investor-flow decision evidence attachment."""

from __future__ import annotations

import json

import pandas as pd

from alpha_cycle.intelligence.decision_evidence_calibrated import (
    _reconcile_investor_flow_evidence_gaps,
)
from alpha_cycle.intelligence.investor_flow_evidence import (
    FlowWindowSummary,
    InvestorFlowEvidence,
    append_investor_flow_report,
    attach_investor_flow_to_records,
    attach_investor_flow_to_scorecards,
)


def _window(ticker: str, window: int, state: str) -> FlowWindowSummary:
    return FlowWindowSummary(
        ticker=ticker,
        window=window,
        observations=window,
        latest_date="20260807",
        oldest_date="20260710",
        latest_price_abs=100_000,
        oldest_price_abs=120_000,
        price_return_pct=-16.6667,
        cumulative_volume=100_000_000,
        individual_net_buy_shares=4_000_000,
        foreign_net_buy_shares=-2_500_000,
        institution_net_buy_shares=-1_500_000,
        pension_net_buy_shares=-200_000,
        foreign_institution_net_buy_shares=-4_000_000,
        foreign_institution_volume_ratio=-0.04,
        descriptive_state=state,
    )


def _evidence(*, verified: bool = True) -> InvestorFlowEvidence:
    windows = tuple(
        _window(ticker, window, "distribution_confirmation")
        for ticker in ("005930", "000660")
        for window in (5, 20)
    )
    return InvestorFlowEvidence(
        status="verified" if verified else "unverified",
        reason="verified_live_evidence" if verified else "reference_date_mismatch",
        source_scope="kiwoom_openapi_plus_opt10059_net_buy_quantity",
        snapshot_id="a" * 64,
        provider_semantic_status="provider_field_mapping_pending_live_certification",
        request_contract_status="verified_net_buy_quantity_single_share_unscored",
        field_mapping_verified=True,
        point_in_time_verified=verified,
        evidence_verified=verified,
        decision_score_enabled=False,
        evaluation_date="2026-08-08",
        reference_date="20260808" if verified else "20260807",
        captured_date="2026-08-08",
        tickers=(),
        windows=windows,
    )


def test_verified_flow_attachment_does_not_change_scores_or_actions() -> None:
    scorecards = pd.DataFrame(
        {
            "ticker": ["005930", "000660"],
            "composite_score": [3.38, 3.59],
            "decision_state": ["mixed_setup", "mixed_setup"],
            "action_bias": ["selective_or_wait", "selective_or_wait"],
        }
    )
    original = scorecards.copy(deep=True)

    attached = attach_investor_flow_to_scorecards(scorecards, _evidence())

    assert attached["composite_score"].tolist() == original["composite_score"].tolist()
    assert attached["decision_state"].tolist() == original["decision_state"].tolist()
    assert attached["action_bias"].tolist() == original["action_bias"].tolist()
    assert attached["investor_flow_evidence_verified"].tolist() == [True, True]
    assert attached["investor_flow_score_enabled"].tolist() == [False, False]
    assert attached["investor_flow_5d_state"].tolist() == [
        "distribution_confirmation",
        "distribution_confirmation",
    ]
    assert attached["investor_flow_20d_foreign_institution_volume_ratio"].tolist() == [
        -0.04,
        -0.04,
    ]

    records = pd.DataFrame(
        {
            "ticker": ["005930", "000660"],
            "decision_state": ["mixed_setup", "mixed_setup"],
        }
    )
    enriched_records = attach_investor_flow_to_records(records, attached)
    assert enriched_records["investor_flow_20d_state"].tolist() == [
        "distribution_confirmation",
        "distribution_confirmation",
    ]


def test_unverified_flow_fails_closed_for_descriptive_values() -> None:
    scorecards = pd.DataFrame(
        {
            "ticker": ["005930", "000660"],
            "composite_score": [3.38, 3.59],
        }
    )

    attached = attach_investor_flow_to_scorecards(scorecards, _evidence(verified=False))

    assert attached["investor_flow_evidence_verified"].tolist() == [False, False]
    assert attached["investor_flow_5d_state"].tolist() == ["unverified", "unverified"]
    assert attached["investor_flow_5d_foreign_net_buy_shares"].isna().all()


def test_verified_flow_removes_only_stale_flow_gap() -> None:
    scorecards = pd.DataFrame(
        {
            "ticker": ["005930", "000660"],
            "evidence_gaps": [
                json.dumps(
                    [
                        "컨센서스·실적 추정치 상향·하향 데이터 미연결",
                        "기관·외국인 수급 데이터 미연결",
                    ],
                    ensure_ascii=False,
                ),
                json.dumps(
                    [
                        "산업 가격·재고·공급·설비투자 사이클 데이터 미연결",
                        "기관·외국인 수급 데이터 미연결",
                    ],
                    ensure_ascii=False,
                ),
            ],
        }
    )

    reconciled = _reconcile_investor_flow_evidence_gaps(scorecards, _evidence())

    for raw in reconciled["evidence_gaps"]:
        gaps = json.loads(raw)
        assert "기관·외국인 수급 데이터 미연결" not in gaps
        assert len(gaps) == 1


def test_unverified_flow_keeps_flow_gap() -> None:
    gap = json.dumps(["기관·외국인 수급 데이터 미연결"], ensure_ascii=False)
    scorecards = pd.DataFrame(
        {
            "ticker": ["005930", "000660"],
            "evidence_gaps": [gap, gap],
        }
    )

    reconciled = _reconcile_investor_flow_evidence_gaps(
        scorecards,
        _evidence(verified=False),
    )

    assert reconciled["evidence_gaps"].tolist() == [gap, gap]


def test_report_labels_flow_as_non_scoring() -> None:
    report = append_investor_flow_report("# Decision\n", _evidence())

    assert "외국인·기관 수급 증거 (비점수)" in report
    assert "composite score, decision state, action bias를 변경하지 않습니다" in report
    assert "distribution_confirmation" in report
