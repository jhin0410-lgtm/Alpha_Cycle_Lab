from __future__ import annotations

import pandas as pd

from alpha_cycle.intelligence.decision_semiconductor_product_profitability_calibration import (
    _attach,
    _defaults,
)
from alpha_cycle.intelligence.semiconductor_product_profitability_calibration import (
    ProductProfitabilityCalibrationEvidence,
    ProductProfitabilityCalibrationMethod,
    assess_product_profitability_calibration_readiness,
)


def _scorecards() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "ticker": "000660",
                "decision_score": 4.0,
                "semiconductor_product_profitability_calibration_required": True,
            },
            {
                "ticker": "005930",
                "decision_score": 3.5,
                "semiconductor_product_profitability_calibration_required": False,
            },
        ]
    )


def _ready_assessment():
    evidence = ProductProfitabilityCalibrationEvidence(
        direct_product_revenue_evidence_id="r" * 64,
        direct_product_revenue_ready=True,
        historical_periods=("2025Q3", "2025Q4", "2026Q1"),
        holdout_periods=("2026Q2",),
        company_profitability_evidence_ids=("g" * 64,),
        cycle_driver_evidence_ids=("d" * 64, "n" * 64),
        source_evidence_verified=True,
    )
    method = ProductProfitabilityCalibrationMethod(
        method_id="skhynix_product_margin_structural_calibration",
        method_version="1.0.0",
        status="observationally_calibrated",
        method_version_frozen=True,
        supporting_evidence_ids=evidence.evidence_ids,
        holdout_validated=True,
    )
    return assess_product_profitability_calibration_readiness(evidence, method)


def test_defaults_keep_profitability_calibration_unavailable_and_non_scoring() -> None:
    result = _defaults(_scorecards())
    assert not result["semiconductor_product_profitability_method_registered"].any()
    assert not result["semiconductor_product_profitability_method_version_frozen"].any()
    assert not result["semiconductor_product_profitability_method_evidence_bound"].any()
    assert not result["semiconductor_product_profitability_holdout_validated"].any()
    assert not result["semiconductor_product_profitability_calibrated_model_input_ready"].any()
    assert result["decision_score"].tolist() == [4.0, 3.5]


def test_ready_calibration_attaches_only_after_profitability_identifiability_gate() -> None:
    result = _attach(_scorecards(), _ready_assessment())
    sk = result.loc[result["ticker"].eq("000660")].iloc[0]
    samsung = result.loc[result["ticker"].eq("005930")].iloc[0]
    assert bool(sk["semiconductor_product_profitability_method_registered"]) is True
    assert sk["semiconductor_product_profitability_method_status"] == "observationally_calibrated"
    assert bool(sk["semiconductor_product_profitability_method_version_frozen"]) is True
    assert bool(sk["semiconductor_product_profitability_method_evidence_bound"]) is True
    assert bool(sk["semiconductor_product_profitability_holdout_validated"]) is True
    assert bool(sk["semiconductor_product_profitability_calibrated_model_input_ready"]) is True
    assert sk["semiconductor_product_profitability_missing_requirements"] == ""
    assert sk["decision_score"] == 4.0
    assert bool(samsung["semiconductor_product_profitability_method_registered"]) is False
    assert samsung["decision_score"] == 3.5


def test_calibration_does_not_attach_when_identifiability_layer_does_not_require_it() -> None:
    scorecards = _scorecards()
    scorecards.loc[scorecards["ticker"].eq("000660"), "semiconductor_product_profitability_calibration_required"] = False
    result = _attach(scorecards, _ready_assessment())
    sk = result.loc[result["ticker"].eq("000660")].iloc[0]
    assert bool(sk["semiconductor_product_profitability_method_registered"]) is False
    assert bool(sk["semiconductor_product_profitability_calibrated_model_input_ready"]) is False
    assert sk["decision_score"] == 4.0
