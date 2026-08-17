from __future__ import annotations

import json
from datetime import date

import pytest

from alpha_cycle.intelligence.sk_hynix_product_profitability_second_wave_frontier import (
    load_second_wave_frontier,
)
from alpha_cycle.intelligence.sk_hynix_second_wave_company_name_recovery import (
    recover_second_wave_company_by_exact_names,
)


def _payload(revenue_name: str = "매출액") -> dict[str, object]:
    common = {
        "sj_div": "CIS",
        "bsns_year": "2019",
        "reprt_code": "11013",
        "rcept_no": "20190515002604",
    }
    return {
        "financials": {
            "list": [
                {
                    **common,
                    "account_id": "dart_legacy_Revenue",
                    "account_nm": revenue_name,
                    "thstrm_amount": "6772700000000",
                },
                {
                    **common,
                    "account_id": "dart_legacy_CostOfSales",
                    "account_nm": "매출원가",
                    "thstrm_amount": "4900000000000",
                },
                {
                    **common,
                    "account_id": "dart_legacy_GrossProfit",
                    "account_nm": "매출총이익",
                    "thstrm_amount": "1872700000000",
                },
            ]
        }
    }


def test_exact_name_recovery_accepts_legacy_account_ids(tmp_path) -> None:
    candidate = load_second_wave_frontier().candidates[0]
    path = tmp_path / "raw.json"
    path.write_text(json.dumps(_payload(), ensure_ascii=False), encoding="utf-8")

    recovery = recover_second_wave_company_by_exact_names(
        candidate,
        path,
        evaluation_date=date(2026, 8, 17),
    )

    assert recovery.observation.revenue_krw == 6_772_700_000_000
    assert recovery.observation.gross_profit_krw == 1_872_700_000_000
    assert recovery.revenue_selection.account_ids == ("dart_legacy_Revenue",)
    assert recovery.revenue_selection.selection_basis == "exact_account_name"
    assert recovery.accounting_identity_verified is True
    assert recovery.training_row_promoted is False
    assert recovery.fit_enabled is False


def test_exact_name_recovery_rejects_fuzzy_revenue_name(tmp_path) -> None:
    candidate = load_second_wave_frontier().candidates[0]
    path = tmp_path / "raw.json"
    path.write_text(
        json.dumps(_payload("연결 매출액 추정"), ensure_ascii=False),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="exact-name account must resolve uniquely"):
        recover_second_wave_company_by_exact_names(
            candidate,
            path,
            evaluation_date=date(2026, 8, 17),
        )
