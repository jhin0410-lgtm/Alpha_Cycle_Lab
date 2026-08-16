from __future__ import annotations

import pandas as pd

from alpha_cycle.intelligence.decision_semiconductor_product_profitability_identifiability_calibrated import (
    _attach,
    _defaults,
)


def _scorecards(*, sk_revenue_ready: bool) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "ticker": "000660",
                "decision_score": 4.0,
                "semiconductor_direct_product_revenue_model_input_ready": sk_revenue_ready,
            },
            {
                "ticker": "005930",
                "decision_score": 3.5,
                "semiconductor_direct_product_revenue_model_input_ready": False,
            },
        ]
    )


def test_profitability_defaults_do_not_invent_a_calibration_state() -> None:
    result = _defaults(_scorecards(sk_revenue_ready=False))
    assert not result[
        "semiconductor_product_profitability_identifiable_from_source_facts"
    ].any()
    assert not result["semiconductor_product_profitability_calibration_required"].any()
    assert result["semiconductor_product_profitability_calibration_status"].isna().all()
    assert not result["semiconductor_product_profitability_certified"].any()
    assert not result["semiconductor_product_profitability_numeric_forecast_enabled"].any()
    assert not result["semiconductor_product_profitability_decision_score_enabled"].any()
    assert result["decision_score"].tolist() == [4.0, 3.5]


def test_ready_skhynix_revenue_exposes_missing_profitability_as_calibration_gap() -> None:
    result = _attach(_scorecards(sk_revenue_ready=True))
    sk = result.loc[result["ticker"].eq("000660")].iloc[0]
    samsung = result.loc[result["ticker"].eq("005930")].iloc[0]

    assert bool(sk["semiconductor_product_profitability_identifiable_from_source_facts"]) is False
    assert bool(sk["semiconductor_product_profitability_calibration_required"]) is True
    assert (
        sk["semiconductor_product_profitability_calibration_status"]
        == "direct_product_profitability_source_facts_missing"
    )
    assert sk["semiconductor_product_profitability_direct_metrics_required"] == 2
    assert sk["semiconductor_product_profitability_direct_metrics_available"] == 0
    assert bool(sk["semiconductor_product_profitability_revenue_share_source_fact_allowed"]) is False
    assert bool(sk["semiconductor_product_profitability_residual_source_fact_allowed"]) is False
    assert bool(sk["semiconductor_product_profitability_peer_margin_source_fact_allowed"]) is False
    assert bool(sk["semiconductor_product_profitability_certified"]) is False
    assert bool(sk["semiconductor_product_profitability_numeric_forecast_enabled"]) is False
    assert bool(sk["semiconductor_product_profitability_decision_score_enabled"]) is False
    assert sk["decision_score"] == 4.0

    assert bool(samsung["semiconductor_product_profitability_calibration_required"]) is False
    assert pd.isna(samsung["semiconductor_product_profitability_calibration_status"])
    assert samsung["decision_score"] == 3.5


def test_profitability_gap_is_not_attached_before_direct_revenue_is_ready() -> None:
    result = _attach(_scorecards(sk_revenue_ready=False))
    sk = result.loc[result["ticker"].eq("000660")].iloc[0]
    assert bool(sk["semiconductor_product_profitability_calibration_required"]) is False
    assert pd.isna(sk["semiconductor_product_profitability_calibration_status"])
    assert bool(sk["semiconductor_product_profitability_certified"]) is False
    assert sk["decision_score"] == 4.0
