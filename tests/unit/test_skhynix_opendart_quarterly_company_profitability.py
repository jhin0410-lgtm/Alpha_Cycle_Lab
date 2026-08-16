from __future__ import annotations

import json
from datetime import date, timedelta

import pytest

from alpha_cycle.intelligence.sk_hynix_opendart_quarterly_company_profitability import (
    build_quarterly_company_profitability_evidence,
    extract_quarterly_company_profitability_raw_payload,
    load_quarterly_company_profitability_registry,
)


def _receipt(period_end: date, suffix: str = "000001") -> str:
    filing_date = period_end + timedelta(days=25)
    return filing_date.strftime("%Y%m%d") + suffix


def _raw(spec, *, revenue: int = 1_000, cost: int = 700, receipt: str | None = None):
    rcept_no = receipt or _receipt(spec.period_end)
    gross = revenue - cost

    def row(account_id: str, amount: int, *, override_receipt: str | None = None):
        return {
            "bsns_year": str(spec.business_year),
            "reprt_code": spec.report_code,
            "sj_div": "IS",
            "account_id": account_id,
            "thstrm_amount": f"{amount:,}",
            "rcept_no": override_receipt or rcept_no,
        }

    return {
        "company": {"stock_code": "000660"},
        "financials": {
            "status": "000",
            "list": [
                row("ifrs-full_Revenue", revenue),
                row("ifrs-full_CostOfSales", cost),
                row("ifrs-full_GrossProfit", gross),
            ],
        },
    }


def test_registry_binds_ten_direct_q1_q2_q3_periods_and_excludes_q4() -> None:
    registry = load_quarterly_company_profitability_registry()
    periods = tuple(item.period_id for item in registry.periods)
    assert periods == (
        "2023Q1",
        "2023Q2",
        "2023Q3",
        "2024Q1",
        "2024Q2",
        "2024Q3",
        "2025Q1",
        "2025Q2",
        "2025Q3",
        "2026Q1",
    )
    assert all(not item.endswith("Q4") for item in periods)
    assert registry.fs_div == "CFS"


def test_raw_current_three_month_accounts_reconcile_exactly() -> None:
    registry = load_quarterly_company_profitability_registry()
    spec = registry.periods[0]
    observation = extract_quarterly_company_profitability_raw_payload(
        registry,
        spec,
        _raw(spec, revenue=1_000, cost=1_200),
    )
    assert observation.revenue_krw == 1_000
    assert observation.cost_of_sales_krw == 1_200
    assert observation.gross_profit_krw == -200
    assert observation.accounting_identity_delta_krw == 0
    assert observation.gross_margin_percent == -20.0
    assert observation.company_profitability_source_facts is True
    assert observation.product_profitability_source_fact is False


def test_raw_accounts_cannot_cross_filing_revisions() -> None:
    registry = load_quarterly_company_profitability_registry()
    spec = registry.periods[0]
    raw = _raw(spec)
    rows = raw["financials"]["list"]
    rows[-1]["rcept_no"] = _receipt(spec.period_end, "000002")
    with pytest.raises(ValueError, match="cross filing revisions"):
        extract_quarterly_company_profitability_raw_payload(registry, spec, raw)


def test_raw_accounting_identity_fails_closed() -> None:
    registry = load_quarterly_company_profitability_registry()
    spec = registry.periods[0]
    raw = _raw(spec)
    raw["financials"]["list"][-1]["thstrm_amount"] = "301"
    with pytest.raises(ValueError, match="identity fails"):
        extract_quarterly_company_profitability_raw_payload(registry, spec, raw)


def test_ten_period_evidence_is_calibration_only_and_not_pit_certified() -> None:
    registry = load_quarterly_company_profitability_registry()
    raw_payloads = {
        spec.period_id: _raw(
            spec,
            revenue=1_000 + index * 100,
            cost=700 + index * 70,
        )
        for index, spec in enumerate(registry.periods)
    }
    evidence = build_quarterly_company_profitability_evidence(
        registry,
        evaluation_date=date(2026, 8, 16),
        raw_payloads=raw_payloads,
    )
    assert evidence.observation_count == 10
    assert evidence.observations[0].period_id == "2023Q1"
    assert evidence.observations[-1].period_id == "2026Q1"
    assert evidence.calibration_support_only is True
    assert evidence.historical_vintage_certified is False
    assert evidence.point_in_time_backtest_eligible is False
    assert evidence.product_profitability_source_fact is False
    assert evidence.numeric_forecast_enabled is False
    assert evidence.fair_value_estimate_enabled is False
    assert evidence.target_price_enabled is False
    assert evidence.decision_score_enabled is False
    json.dumps(raw_payloads)
