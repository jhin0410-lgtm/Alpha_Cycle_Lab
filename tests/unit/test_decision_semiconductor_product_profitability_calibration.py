from __future__ import annotations

import pandas as pd

from alpha_cycle.intelligence.decision_semiconductor_product_profitability_calibration import (
    _attach,
    _defaults,
)
from alpha_cycle.intelligence.semiconductor_product_profitability_calibration import (
    ProductProfitabilityCalibrationMethod,
    ProfitabilityCalibrationEvidenceInventory,
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
    inventory = ProfitabilityCalibrationEvidenceInventory(
        direct_product_revenue_evidence_id="r" * 64,
        direct_product_revenue_ready=True,
        direct_product_profitability_periods=(),
        historical_product_revenue_periods=("2025Q3", "2025Q4", "2026Q1"),
        company_profitability_constraint_periods=("2025Q3", "2025Q4", "2026Q1"),
        cycle_driver_history_periods=("2025Q3", "2025Q4", "2026Q1"),
        holdout_periods=("2026Q2",),
        verified_evidence_ids=("g" * 64, "d" * 64, "n" * 64),
        source_evidence_verified=True,
    )
    method = ProductProfitabilityCalibrationMethod(
        method_id="skhynix_product_margin_structural_calibration",
        method_version="1.0.0",
        identification_strategy="aggregate_structural_model",
        target_metric="gross_margin",
        target_product_blocks=("dram_total", "nand_and_solutions"),
        minimum_direct_target_periods=0,
        minimum_product_revenue_periods=3,
        minimum_company_profitability_periods=3,
        minimum_cycle_driver_periods=3,
        minimum_holdout_periods=1,
        method_documented=True,
        historical_validation_complete=True,
        holdout_validation_complete=True,
        method_version_frozen=True,
        supporting_evidence_ids=inventory.all_required_evidence_ids,
    )
    return assess_product_profitability_calibration_readiness(inventory, method)


def test_defaults_keep_profitability_calibration_unavailable_and_non_scoring() -> None:
    result = _defaults(_scorecards())
    assert not result["semiconductor_product_profitability_method_registered"].any()
    assert not result["semiconductor_product_profitability_method_documented"].any()
    assert not result["semiconductor_product_profitability_method_version_frozen"].any()
    assert not result["semiconductor_product_profitability_method_evidence_bound"].any()
    assert not result[
        "semiconductor_product_profitability_historical_validation_complete"
    ].any()
    assert not result["semiconductor_product_profitability_holdout_validation_complete"].any()
    assert not result["semiconductor_product_profitability_calibrated_model_input_ready"].any()
    assert result["decision_score"].tolist() == [4.0, 3.5]


def test_ready_calibration_attaches_only_after_profitability_identifiability_gate() -> None:
    result = _attach(_scorecards(), _ready_assessment())
    sk = result.loc[result["ticker"].eq("000660")].iloc[0]
    samsung = result.loc[result["ticker"].eq("005930")].iloc[0]
    assert (
        sk["semiconductor_product_profitability_calibration_readiness_status"]
        == "observationally_calibrated"
    )
    assert bool(sk["semiconductor_product_profitability_method_registered"]) is True
    assert bool(sk["semiconductor_product_profitability_method_documented"]) is True
    assert (
        sk["semiconductor_product_profitability_identification_strategy"]
        == "aggregate_structural_model"
    )
    assert bool(sk["semiconductor_product_profitability_method_version_frozen"]) is True
    assert bool(sk["semiconductor_product_profitability_method_evidence_bound"]) is True
    assert (
        bool(sk["semiconductor_product_profitability_historical_validation_complete"])
        is True
    )
    assert (
        bool(sk["semiconductor_product_profitability_holdout_validation_complete"])
        is True
    )
    assert bool(sk["semiconductor_product_profitability_calibrated_model_input_ready"]) is True
    assert sk["semiconductor_product_profitability_missing_requirements"] == ""
    assert sk["decision_score"] == 4.0
    assert bool(samsung["semiconductor_product_profitability_method_registered"]) is False
    assert samsung["decision_score"] == 3.5


def test_calibration_does_not_attach_when_identifiability_layer_does_not_require_it() -> None:
    scorecards = _scorecards()
    scorecards.loc[
        scorecards["ticker"].eq("000660"),
        "semiconductor_product_profitability_calibration_required",
    ] = False
    result = _attach(scorecards, _ready_assessment())
    sk = result.loc[result["ticker"].eq("000660")].iloc[0]
    assert bool(sk["semiconductor_product_profitability_method_registered"]) is False
    assert bool(sk["semiconductor_product_profitability_calibrated_model_input_ready"]) is False
    assert sk["decision_score"] == 4.0
