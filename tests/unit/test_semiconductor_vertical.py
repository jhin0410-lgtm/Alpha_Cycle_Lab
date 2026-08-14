from __future__ import annotations

from datetime import date

import pandas as pd
import pytest

from alpha_cycle.intelligence.semiconductor_vertical import (
    append_semiconductor_vertical_report,
    attach_semiconductor_vertical_to_scorecards,
    build_semiconductor_vertical_assessment,
    sync_record_semiconductor_vertical_fields,
)


def _scorecards() -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for ticker, pb, pb_pct, roe, r20, r60, confirmed in (
        ("000660", 7.13, 87.0, 0.612, -0.101, 0.20, False),
        ("005930", 3.67, 92.0, 0.189, 0.065, 0.14, True),
    ):
        rows.append(
            {
                "ticker": ticker,
                "composite_score": 3.8,
                "score_coverage": 0.70,
                "valuation_score": pd.NA,
                "industry_evidence_available": True,
                "industry_shipment_yoy_pct": 18.0,
                "industry_shipment_mom_sa_pct": 2.0,
                "industry_inventory_yoy_pct": -7.0,
                "industry_inventory_mom_sa_pct": -1.0,
                "industry_capacity_yoy_pct": 4.0,
                "industry_utilization_yoy_pct": 8.0,
                "industry_utilization_mom_sa_pct": 1.5,
                "historical_pb_evidence_available": True,
                "historical_pb_latest_pb": pb,
                "historical_pb_latest_pb_percentile": pb_pct,
                "pb_roe_regime_ttm_roe": roe,
                "pb_roe_regime_ttm_roe_history_ready": False,
                "kis_forward_evidence_available": True,
                "kis_estimate_snapshot_change_verified": False,
                "return_20": r20,
                "return_60": r60,
                "cycle_proxy_market_confirmed": confirmed,
                "investor_flow_evidence_verified": False,
                "investor_flow_available": True,
            }
        )
    return pd.DataFrame(rows)


def _financial_history() -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for ticker, revenue_yoy, operating_yoy, margin_change in (
        ("000660", 0.35, 0.55, 7.0),
        ("005930", 0.16, 0.28, 3.5),
    ):
        rows.append(
            {
                "ticker": ticker,
                "business_year": 2026,
                "period_label": "Q1",
                "period_end": "2026-03-31",
                "available_date": "2026-05-15",
                "derived": False,
                "revenue_yoy": revenue_yoy,
                "operating_income_yoy": operating_yoy,
                "operating_margin_change_yoy_pp": margin_change,
                "capex_ytd": -120.0,
                "capex_prior_ytd": -100.0,
            }
        )
    return pd.DataFrame(rows)


def test_semiconductor_vertical_exposes_real_missing_research_without_zero_scoring() -> None:
    before = _scorecards()
    assessment = build_semiconductor_vertical_assessment(
        before,
        _financial_history(),
        pd.DataFrame([{"ticker": "000660"}, {"ticker": "005930"}]),
        pd.DataFrame([{"series_id": "kr_base_rate", "value": 2.75}]),
        evaluation_date=date(2026, 8, 14),
    )

    assert assessment.decision_score_enabled is False
    assert len(assessment.coverages) == 2
    for coverage in assessment.coverages:
        assert coverage.required_total == 10
        assert coverage.required_available == 3
        assert coverage.readiness_status == "required_evidence_missing"
        assert "memory_pricing" in coverage.missing_required
        assert "hbm_demand_mix" in coverage.missing_required
        assert "hbm_capacity_yield" in coverage.missing_required
        assert "competitive_position" in coverage.missing_required
        assert "end_demand" in coverage.partial_required
        assert "valuation_regime" in coverage.partial_required
        assert coverage.blocked_required == ("expectation_revision",)

    after = attach_semiconductor_vertical_to_scorecards(before, assessment)
    for ticker in ("000660", "005930"):
        left = before.loc[before["ticker"].eq(ticker)].iloc[0]
        right = after.loc[after["ticker"].eq(ticker)].iloc[0]
        assert float(right["composite_score"]) == pytest.approx(float(left["composite_score"]))
        assert float(right["score_coverage"]) == pytest.approx(float(left["score_coverage"]))
        assert pd.isna(right["valuation_score"])
        assert bool(right["sector_vertical_decision_score_enabled"]) is False

    records = sync_record_semiconductor_vertical_fields(
        before.loc[:, ["ticker", "composite_score", "score_coverage"]].copy(),
        after,
    )
    assert "sector_vertical_missing_required_json" in records.columns
    assert float(records.iloc[0]["composite_score"]) == pytest.approx(3.8)

    report = append_semiconductor_vertical_report("# Base\n", assessment)
    assert "Semiconductor Vertical v1 연구 커버리지 (비점수)" in report
    assert "memory_pricing" in report
    assert "HBM 수요·믹스·세대" in report
    assert "consensus_and_revision_semantics_not_certified" in report
    assert "없는 데이터를 proxy로 임의 대체하지 않습니다" in report


def test_semiconductor_vertical_keeps_company_specific_market_confirmation_separate() -> None:
    assessment = build_semiconductor_vertical_assessment(
        _scorecards(),
        _financial_history(),
        pd.DataFrame([{"ticker": "000660"}, {"ticker": "005930"}]),
        pd.DataFrame([{"series_id": "usd_krw", "value": 1430.0}]),
        evaluation_date=date(2026, 8, 14),
    )
    by_ticker = {coverage.ticker: coverage for coverage in assessment.coverages}
    h = {state.requirement_key: state for state in by_ticker["000660"].states}
    s = {state.requirement_key: state for state in by_ticker["005930"].states}

    assert h["flow_price_confirmation"].status == "partial"
    assert s["flow_price_confirmation"].status == "partial"
    assert "cycle proxy 시장확인=no" in h["flow_price_confirmation"].evidence_summary
    assert "cycle proxy 시장확인=yes" in s["flow_price_confirmation"].evidence_summary
