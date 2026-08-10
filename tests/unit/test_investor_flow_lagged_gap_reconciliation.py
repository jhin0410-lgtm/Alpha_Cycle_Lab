from __future__ import annotations

import json

import pandas as pd

from alpha_cycle.intelligence.decision_evidence_calibrated import (
    _flow_warnings,
    _lagged_flow_observation_date,
    _reconcile_investor_flow_evidence_gaps,
)
from alpha_cycle.intelligence.investor_flow_evidence import (
    FlowWindowSummary,
    InvestorFlowEvidence,
)


def _window(ticker: str) -> FlowWindowSummary:
    return FlowWindowSummary(
        ticker=ticker,
        window=20,
        observations=20,
        latest_date="20260807",
        oldest_date="20260710",
        latest_price_abs=100_000,
        oldest_price_abs=120_000,
        price_return_pct=-16.7,
        cumulative_volume=100_000_000,
        individual_net_buy_shares=4_000_000,
        foreign_net_buy_shares=-2_500_000,
        institution_net_buy_shares=-1_500_000,
        pension_net_buy_shares=-200_000,
        foreign_institution_net_buy_shares=-4_000_000,
        foreign_institution_volume_ratio=-0.04,
        descriptive_state="distribution_confirmation",
    )


def _evidence(reason: str, *, verified: bool = False) -> InvestorFlowEvidence:
    return InvestorFlowEvidence(
        status="verified" if verified else "unverified",
        reason=reason,
        source_scope="kiwoom_openapi_plus_opt10059_net_buy_quantity",
        snapshot_id="a" * 64,
        provider_semantic_status="provider_field_mapping_pending_live_certification",
        request_contract_status="verified_net_buy_quantity_single_share_unscored",
        field_mapping_verified=True,
        point_in_time_verified=verified,
        evidence_verified=verified,
        decision_score_enabled=False,
        evaluation_date="2026-08-10",
        reference_date="20260810",
        captured_date="2026-08-10",
        tickers=(),
        windows=(_window("000660"), _window("005930")),
    )


def _scorecards() -> pd.DataFrame:
    gap = json.dumps(
        [
            "기관·외국인 수급 데이터 미연결",
            "글로벌 비교기업과 과거 밸류에이션 밴드 미연결",
        ],
        ensure_ascii=False,
    )
    return pd.DataFrame(
        [
            {"ticker": "000660", "evidence_gaps": gap, "composite_score": 3.59},
            {"ticker": "005930", "evidence_gaps": gap, "composite_score": 3.38},
        ]
    )


def test_prior_session_flow_narrows_missing_gap_without_becoming_verified() -> None:
    evidence = _evidence(
        "market_session_mismatch:000660:flow=2026-08-07:market=2026-08-10"
    )
    original = _scorecards()

    reconciled = _reconcile_investor_flow_evidence_gaps(original, evidence)

    assert evidence.evidence_verified is False
    assert evidence.point_in_time_verified is False
    assert reconciled["composite_score"].tolist() == original["composite_score"].tolist()
    for raw in reconciled["evidence_gaps"]:
        gaps = json.loads(str(raw))
        assert "기관·외국인 수급 데이터 미연결" not in gaps
        assert any("동일세션 수급 미확인" in gap for gap in gaps)
        assert any("2026-08-07" in gap and "비점수" in gap for gap in gaps)
    assert _lagged_flow_observation_date(evidence).isoformat() == "2026-08-07"  # type: ignore[union-attr]
    assert "investor_flow_prior_session_available:2026-08-07" in _flow_warnings(evidence)


def test_non_session_unverified_reason_keeps_generic_gap() -> None:
    evidence = _evidence("field_mapping_unverified")
    original = _scorecards()

    reconciled = _reconcile_investor_flow_evidence_gaps(original, evidence)

    assert reconciled["evidence_gaps"].tolist() == original["evidence_gaps"].tolist()
    assert _lagged_flow_observation_date(evidence) is None


def test_same_or_future_flow_date_is_not_reclassified_as_prior_session() -> None:
    evidence = _evidence(
        "market_session_mismatch:000660:flow=2026-08-10:market=2026-08-10"
    )
    original = _scorecards()

    reconciled = _reconcile_investor_flow_evidence_gaps(original, evidence)

    assert reconciled["evidence_gaps"].tolist() == original["evidence_gaps"].tolist()
    assert _lagged_flow_observation_date(evidence) is None
