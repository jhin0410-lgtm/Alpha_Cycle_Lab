from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest
import yaml

from alpha_cycle.intelligence.sk_hynix_company_gp_ex_ante_historical_evaluation import (
    extract_historical_target_observation,
)
from alpha_cycle.intelligence.sk_hynix_company_gp_ex_ante_historical_evaluation_v2 import (
    load_frozen_historical_schema_repair_v2,
    load_historical_raw_target_capture,
    persist_historical_raw_target_capture,
)

_PERIODS = tuple(
    f"{year}Q{quarter}" for year in range(2016, 2026) for quarter in (2, 3)
)


def _receipt(period_id: str) -> str:
    month_day = "0815" if period_id.endswith("Q2") else "1115"
    return f"{period_id[:4]}{month_day}000001"


def _legacy_payload(period_id: str, gross_profit_million: float = 1_500.0) -> object:
    report_code = "11012" if period_id.endswith("Q2") else "11014"
    receipt = _receipt(period_id)
    gross = int(round(gross_profit_million * 1_000_000.0))
    revenue = 20_000_000_000_000 + int(period_id[:4]) * 1_000_000
    cost = revenue - gross
    common = {
        "sj_div": "IS",
        "bsns_year": period_id[:4],
        "reprt_code": report_code,
        "rcept_no": receipt,
    }
    return {
        "company": {"stock_code": "000660"},
        "financials": {
            "status": "000",
            "list": [
                {
                    **common,
                    "account_id": "ifrs_Revenue",
                    "account_nm": "수익(매출액)",
                    "thstrm_amount": str(revenue),
                },
                {
                    **common,
                    "account_id": "ifrs_CostOfSales",
                    "account_nm": "매출원가",
                    "thstrm_amount": str(cost),
                },
                {
                    **common,
                    "account_id": "ifrs_GrossProfit",
                    "account_nm": "매출총이익",
                    "thstrm_amount": str(gross),
                },
            ],
        },
    }


def test_v2_freeze_discloses_v1_schema_failure_without_model_drift() -> None:
    repair = load_frozen_historical_schema_repair_v2()

    assert repair.execution_version == (
        "1.1-frozen-after-schema-failure-before-target-resolution"
    )
    assert repair.raw_payloads_retrieved_in_v1
    assert not repair.target_observation_constructed_in_v1
    assert not repair.target_join_persisted_in_v1
    assert not repair.estimator_fit_run_in_v1
    assert not repair.historical_backtest_run_in_v1
    assert not repair.outcome_value_inspection_used_for_repair
    assert repair.runtime_execution.exact_target_periods == _PERIODS
    assert repair.runtime_execution.shared_initial_training_rows == 12
    assert repair.runtime_execution.scored_fold_count == 8
    assert repair.runtime_execution.benchmark_id == (
        "previous_reported_quarter_gross_profit_persistence"
    )
    assert repair.runtime_execution.revenue_account_ids[0] == "ifrs_Revenue"
    assert repair.runtime_execution.cost_of_sales_account_ids[0] == "ifrs_CostOfSales"
    assert repair.runtime_execution.gross_profit_account_ids[0] == "ifrs_GrossProfit"


def test_v2_legacy_taxonomy_aliases_resolve_exact_standard_account_ids() -> None:
    repair = load_frozen_historical_schema_repair_v2()
    observation = extract_historical_target_observation(
        repair.runtime_execution,
        "2016Q2",
        _legacy_payload("2016Q2"),
        evaluation_date=date(2026, 8, 21),
    )

    assert observation.period_id == "2016Q2"
    assert observation.report_code == "11012"
    assert observation.gross_profit_krw_million == 1_500.0
    assert observation.receipt_no == _receipt("2016Q2")


def test_v2_raw_capture_is_locked_before_target_extraction(tmp_path: Path) -> None:
    repair = load_frozen_historical_schema_repair_v2()
    payloads = {period: _legacy_payload(period) for period in _PERIODS}
    capture, pointer = persist_historical_raw_target_capture(
        repair.runtime_execution,
        evaluation_date=date(2026, 8, 21),
        raw_payloads=payloads,
        output=tmp_path,
    )
    replayed, replayed_payloads = load_historical_raw_target_capture(pointer)

    assert replayed.evidence_id == capture.evidence_id
    assert replayed.execution_evidence_id == repair.evidence_id
    assert tuple(replayed_payloads) == _PERIODS
    assert replayed_payloads == payloads

    changed = dict(payloads)
    changed["2025Q3"] = _legacy_payload("2025Q3", gross_profit_million=9_999.0)
    with pytest.raises(ValueError, match="already locked and cannot refresh"):
        persist_historical_raw_target_capture(
            repair.runtime_execution,
            evaluation_date=date(2026, 8, 21),
            raw_payloads=changed,
            output=tmp_path,
        )


def test_v2_manifest_rejects_post_failure_fold_geometry_change(tmp_path: Path) -> None:
    source = Path(
        "config/skhynix_company_gp_ex_ante_historical_evaluation_execution.v2.yaml"
    )
    payload = yaml.safe_load(source.read_text(encoding="utf-8"))
    payload["execution"]["chronological_evaluation"]["scored_fold_count"] = 7
    drifted = tmp_path / "drifted-v2.yaml"
    drifted.write_text(
        yaml.safe_dump(payload, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="changed frozen model field"):
        load_frozen_historical_schema_repair_v2(drifted)
