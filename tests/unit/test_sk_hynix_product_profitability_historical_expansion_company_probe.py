from __future__ import annotations

from alpha_cycle.intelligence.sk_hynix_product_profitability_historical_expansion_company_probe import (
    extract_expansion_company_profitability_observation,
)
from alpha_cycle.intelligence.sk_hynix_product_profitability_historical_expansion_frontier import (
    load_historical_expansion_frontier,
)


def _row(account_id: str, amount: int) -> dict[str, object]:
    return {
        "sj_div": "IS",
        "account_id": account_id,
        "bsns_year": "2021",
        "reprt_code": "11013",
        "rcept_no": "20210517000667",
        "thstrm_amount": str(amount),
    }


def test_expansion_company_profitability_extracts_direct_identity() -> None:
    candidate = load_historical_expansion_frontier().candidates[0]
    raw_payload = {
        "financials": {
            "list": [
                _row("ifrs-full_Revenue", 100_000_000),
                _row("ifrs-full_CostOfSales", 60_000_000),
                _row("ifrs-full_GrossProfit", 40_000_000),
            ]
        }
    }

    observation = extract_expansion_company_profitability_observation(
        candidate,
        raw_payload,
        revenue_account_ids=(
            "ifrs-full_Revenue",
            "ifrs-full_RevenueFromContractsWithCustomers",
        ),
        cost_of_sales_account_ids=("ifrs-full_CostOfSales",),
        gross_profit_account_ids=("ifrs-full_GrossProfit",),
    )

    assert observation.period_id == "2021Q1"
    assert observation.rcept_no == "20210517000667"
    assert observation.revenue_krw == 100_000_000
    assert observation.cost_of_sales_krw == 60_000_000
    assert observation.gross_profit_krw == 40_000_000
    assert observation.gross_margin_percent == 40.0
    assert observation.current_retrieval_historical_source_fact is True
    assert observation.historical_vintage_certified is False
    assert observation.point_in_time_backtest_eligible is False
    assert observation.product_profitability_source_fact is False
