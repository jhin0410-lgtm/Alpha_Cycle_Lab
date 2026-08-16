from __future__ import annotations

import json
from dataclasses import asdict
from datetime import date, timedelta

from alpha_cycle.intelligence.sk_hynix_opendart_quarterly_company_profitability import (
    build_quarterly_company_profitability_evidence,
    load_quarterly_company_profitability_registry,
)
from alpha_cycle.intelligence.sk_hynix_opendart_quarterly_company_profitability_verifier import (
    load_quarterly_company_profitability_evidence,
)


def _raw(spec, index: int):
    rcept_no = (spec.period_end + timedelta(days=25)).strftime("%Y%m%d") + "000001"
    revenue = 1_000 + index * 100
    cost = 700 + index * 70
    gross = revenue - cost
    rows = [
        {
            "bsns_year": str(spec.business_year),
            "reprt_code": spec.report_code,
            "sj_div": "IS",
            "account_id": account,
            "thstrm_amount": str(amount),
            "rcept_no": rcept_no,
        }
        for account, amount in (
            ("ifrs-full_Revenue", revenue),
            ("ifrs-full_CostOfSales", cost),
            ("ifrs-full_GrossProfit", gross),
        )
    ]
    return {"company": {"stock_code": "000660"}, "financials": {"list": rows}}


def test_verifier_rebuilds_all_ten_periods_from_archived_raw_payloads(tmp_path) -> None:
    registry = load_quarterly_company_profitability_registry()
    raw_payloads = {
        spec.period_id: _raw(spec, index)
        for index, spec in enumerate(registry.periods)
    }
    evidence = build_quarterly_company_profitability_evidence(
        registry,
        evaluation_date=date(2026, 8, 16),
        raw_payloads=raw_payloads,
    )
    raw_directory = tmp_path / "raw"
    raw_directory.mkdir()
    for period_id, raw in raw_payloads.items():
        (raw_directory / f"{period_id}.json").write_text(
            json.dumps(raw, sort_keys=True),
            encoding="utf-8",
        )

    observations = [
        {
            **asdict(item),
            "period_end": item.period_end.isoformat(),
            "available_date": item.available_date.isoformat(),
        }
        for item in evidence.observations
    ]
    panel = {"evidence_id": evidence.evidence_id, "observation_count": 10}
    panel_path = tmp_path / "panel.json"
    manifest_path = tmp_path / "manifest.json"
    panel_path.write_text(json.dumps(panel), encoding="utf-8")
    manifest_path.write_text(json.dumps(panel), encoding="utf-8")
    pointer = {
        "status": "skhynix_opendart_quarterly_company_profitability_captured",
        "evaluation_date": "2026-08-16",
        "evidence_id": evidence.evidence_id,
        "observation_count": 10,
        "observations": observations,
        "calibration_support_only": True,
        "historical_vintage_certified": False,
        "point_in_time_backtest_eligible": False,
        "product_profitability_source_fact": False,
        "numeric_forecast_enabled": False,
        "fair_value_estimate_enabled": False,
        "target_price_enabled": False,
        "decision_score_enabled": False,
        "raw_directory": str(raw_directory),
        "panel_path": str(panel_path),
        "manifest_path": str(manifest_path),
    }
    pointer_path = tmp_path / "latest.json"
    pointer_path.write_text(json.dumps(pointer), encoding="utf-8")

    verified = load_quarterly_company_profitability_evidence(
        pointer_path,
        evaluation_date=date(2026, 8, 16),
    )
    assert verified.evidence_id == evidence.evidence_id
    assert verified.observation_count == 10
    assert verified.observations[-1].period_id == "2026Q1"
    assert verified.point_in_time_backtest_eligible is False
