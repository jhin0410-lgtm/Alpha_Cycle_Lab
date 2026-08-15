from __future__ import annotations

import pandas as pd

from alpha_cycle.intelligence.decision_semiconductor_product_revenue_calibrated import (
    _attach,
    _defaults,
)


def _scorecards() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"ticker": "000660", "decision_score": 4.0},
            {"ticker": "005930", "decision_score": 3.5},
        ]
    )


def test_direct_product_revenue_defaults_are_explicitly_unavailable_and_non_scoring() -> None:
    result = _defaults(_scorecards())
    assert not result["semiconductor_direct_product_revenue_available"].any()
    assert not result["semiconductor_direct_product_revenue_model_input_ready"].any()
    assert not result["semiconductor_direct_product_revenue_source_fact"].any()
    assert not result["semiconductor_direct_product_revenue_profitability_certified"].any()
    assert not result["semiconductor_direct_product_revenue_full_baseline_certified"].any()
    assert not result[
        "semiconductor_direct_product_revenue_allocation_resolver_registered"
    ].any()
    assert not result["semiconductor_direct_product_revenue_numeric_forecast_enabled"].any()
    assert not result["semiconductor_direct_product_revenue_decision_score_enabled"].any()
    assert result["decision_score"].tolist() == [4.0, 3.5]


def test_direct_product_revenue_attaches_only_to_skhynix_and_never_opens_profit_or_score() -> None:
    result = _attach(
        _scorecards(),
        evidence_id="a" * 64,
        dram_revenue=29_000_000.0,
        nand_revenue=10_500_000.0,
        other_revenue=500_000.0,
        total_revenue=40_000_000.0,
        reconciliation_certified=True,
        ir_crosscheck_certified=True,
    )
    sk = result.loc[result["ticker"].eq("000660")].iloc[0]
    samsung = result.loc[result["ticker"].eq("005930")].iloc[0]
    assert bool(sk["semiconductor_direct_product_revenue_available"]) is True
    assert bool(sk["semiconductor_direct_product_revenue_source_fact"]) is True
    assert bool(sk["semiconductor_direct_product_revenue_model_input_ready"]) is True
    assert sk["semiconductor_direct_product_revenue_other_krw_million"] == 500_000.0
    assert bool(sk["semiconductor_direct_product_revenue_profitability_certified"]) is False
    assert bool(sk["semiconductor_direct_product_revenue_full_baseline_certified"]) is False
    assert (
        bool(sk["semiconductor_direct_product_revenue_allocation_resolver_registered"])
        is False
    )
    assert bool(sk["semiconductor_direct_product_revenue_numeric_forecast_enabled"]) is False
    assert bool(sk["semiconductor_direct_product_revenue_decision_score_enabled"]) is False
    assert sk["decision_score"] == 4.0
    assert bool(samsung["semiconductor_direct_product_revenue_available"]) is False
    assert samsung["decision_score"] == 3.5


def test_revenue_model_input_readiness_requires_independent_ir_crosscheck() -> None:
    result = _attach(
        _scorecards(),
        evidence_id="b" * 64,
        dram_revenue=29_000_000.0,
        nand_revenue=10_500_000.0,
        other_revenue=500_000.0,
        total_revenue=40_000_000.0,
        reconciliation_certified=True,
        ir_crosscheck_certified=False,
    )
    sk = result.loc[result["ticker"].eq("000660")].iloc[0]
    assert bool(sk["semiconductor_direct_product_revenue_available"]) is True
    assert bool(sk["semiconductor_direct_product_revenue_reconciliation_certified"]) is True
    assert bool(sk["semiconductor_direct_product_revenue_ir_crosscheck_certified"]) is False
    assert bool(sk["semiconductor_direct_product_revenue_model_input_ready"]) is False
