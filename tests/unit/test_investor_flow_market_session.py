"""Tests for decision-time investor-flow market-session freshness."""

from __future__ import annotations

from datetime import date

import pandas as pd

from alpha_cycle.intelligence.investor_flow_evidence import (
    FlowWindowSummary,
    InvestorFlowEvidence,
)
from alpha_cycle.intelligence.investor_flow_market_session import (
    align_investor_flow_to_market_session,
    extract_market_session_dates,
)


def _window(ticker: str, window: int) -> FlowWindowSummary:
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
        descriptive_state="distribution_confirmation",
    )


def _capture_verified_evidence(
    *,
    reference_date: str = "20260808",
    captured_date: str = "2026-08-08",
) -> InvestorFlowEvidence:
    return InvestorFlowEvidence(
        status="verified",
        reason="verified_live_evidence",
        source_scope="kiwoom_openapi_plus_opt10059_net_buy_quantity",
        snapshot_id="a" * 64,
        provider_semantic_status="provider_field_mapping_pending_live_certification",
        request_contract_status="verified_net_buy_quantity_single_share_unscored",
        field_mapping_verified=True,
        point_in_time_verified=True,
        evidence_verified=True,
        decision_score_enabled=False,
        evaluation_date="2026-08-08",
        reference_date=reference_date,
        captured_date=captured_date,
        tickers=(),
        windows=tuple(
            _window(ticker, window)
            for ticker in ("005930", "000660")
            for window in (5, 20)
        ),
    )


def _market_context(session_timestamp: str) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "ticker": ["005930", "000660", "005935"],
            "last_timestamp": [
                pd.Timestamp(session_timestamp),
                pd.Timestamp(session_timestamp),
                pd.Timestamp(session_timestamp),
            ],
        }
    )


def test_market_session_dates_convert_utc_back_to_korea_session() -> None:
    sessions = extract_market_session_dates(
        _market_context("2026-08-06T15:00:00Z")
    )

    assert sessions["005930"] == date(2026, 8, 7)
    assert sessions["000660"] == date(2026, 8, 7)


def test_weekend_evaluation_keeps_latest_friday_flow_verified() -> None:
    evidence = align_investor_flow_to_market_session(
        _capture_verified_evidence(),
        evaluation_date=date(2026, 8, 9),
        market_context=_market_context("2026-08-06T15:00:00Z"),
    )

    assert evidence.evidence_verified is True
    assert evidence.point_in_time_verified is True
    assert evidence.reason == "verified_live_market_session_evidence"
    assert evidence.evaluation_date == "2026-08-09"
    assert evidence.window("005930", 20) is not None
    assert evidence.window("005930", 20).latest_date == "20260807"  # type: ignore[union-attr]


def test_flow_fails_closed_when_market_advances_to_new_session() -> None:
    evidence = align_investor_flow_to_market_session(
        _capture_verified_evidence(),
        evaluation_date=date(2026, 8, 10),
        market_context=_market_context("2026-08-09T15:00:00Z"),
    )

    assert evidence.evidence_verified is False
    assert evidence.point_in_time_verified is False
    assert evidence.reason == (
        "market_session_mismatch:000660:flow=2026-08-07:market=2026-08-10"
    )


def test_future_capture_is_never_admissible() -> None:
    evidence = align_investor_flow_to_market_session(
        _capture_verified_evidence(
            reference_date="20260810",
            captured_date="2026-08-10",
        ),
        evaluation_date=date(2026, 8, 9),
        market_context=_market_context("2026-08-06T15:00:00Z"),
    )

    assert evidence.evidence_verified is False
    assert evidence.reason == "reference_date_after_evaluation"


def test_missing_ticker_market_session_fails_closed() -> None:
    market = pd.DataFrame(
        {
            "ticker": ["005930"],
            "last_timestamp": [pd.Timestamp("2026-08-06T15:00:00Z")],
        }
    )
    evidence = align_investor_flow_to_market_session(
        _capture_verified_evidence(),
        evaluation_date=date(2026, 8, 9),
        market_context=market,
    )

    assert evidence.evidence_verified is False
    assert evidence.reason == "market_session_unavailable:000660"
