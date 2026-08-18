from __future__ import annotations

import hashlib
import json

import pytest

from alpha_cycle.intelligence.sk_hynix_product_profitability_regime_economic_audit import (
    build_regime_economic_audit,
)
from alpha_cycle.intelligence.sk_hynix_product_profitability_regime_estimation_method import (
    load_frozen_regime_estimation_method,
)


def _sha(payload: object) -> str:
    return hashlib.sha256(
        json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        ).encode("utf-8")
    ).hexdigest()


def _wrappers(coefficients: list[float]) -> tuple[dict[str, object], dict[str, object]]:
    method = load_frozen_regime_estimation_method()
    training_evidence = "1" * 64
    training = {
        "method_evidence_id": method.evidence_id,
        "result": {
            "evidence_id": training_evidence,
            "coefficients": coefficients,
            "training_gate_passed": True,
        },
    }
    holdout_result: dict[str, object] = {
        "method_evidence_id": method.evidence_id,
        "training_fit_evidence_id": training_evidence,
        "holdout_period": "2026Q1",
        "source_evaluation_date": "2026-08-17",
        "product_revenue_evidence_id": "2" * 64,
        "company_profitability_evidence_id": "3" * 64,
        "cycle_driver_evidence_id": "4" * 64,
        "company_revenue_krw_million": 100.0,
        "actual_gross_profit_krw_million": 40.0,
        "model_prediction_krw_million": 38.0,
        "model_absolute_error_krw_million": 2.0,
        "benchmark_prediction_krw_million": 20.0,
        "benchmark_absolute_error_krw_million": 20.0,
        "model_beats_benchmark": True,
        "company_product_revenue_reconciled": True,
        "holdout_validation_passed": True,
        "holdout_spent": True,
        "immutable_result": True,
        "refit_after_holdout_allowed": False,
        "product_profitability_is_direct_source_fact": False,
        "numeric_forecast_enabled": False,
        "fair_value_estimate_enabled": False,
        "target_price_enabled": False,
        "decision_score_enabled": False,
    }
    holdout_result["evidence_id"] = _sha(holdout_result)
    holdout = {
        "method_evidence_id": method.evidence_id,
        "training_fit_evidence_id": training_evidence,
        "result": holdout_result,
    }
    return training, holdout


def test_audit_retains_predictive_validation_but_blocks_literal_margin_interpretation() -> None:
    method = load_frozen_regime_estimation_method()
    training, holdout = _wrappers(
        [
            0.8701583265,
            -0.1261586189,
            -0.0250835909,
            0.7780803178,
            0.3144734382,
            0.2154791555,
            -9.4711136447,
        ]
    )

    result = build_regime_economic_audit(method, training, holdout)

    assert result.holdout_validation_passed is True
    assert result.predictive_validation_retained is True
    assert result.dram.minimum_implied_contribution_ratio == pytest.approx(0.7189161167)
    assert result.dram.maximum_implied_contribution_ratio == pytest.approx(1.0214005363)
    assert result.nand.minimum_implied_contribution_ratio == pytest.approx(0.2481277241)
    assert result.nand.maximum_implied_contribution_ratio == pytest.approx(1.3080329115)
    assert result.dram.maximum_exceeds_revenue_hard_bound is True
    assert result.nand.maximum_exceeds_revenue_hard_bound is True
    assert result.any_product_revenue_hard_bound_violation is True
    assert result.structural_product_margin_interpretation_allowed is False
    assert result.forward_structural_forecast_allowed is False
    assert result.v1_scope == "validated_empirical_regime_predictor_only"
    assert result.next_action.startswith("design_v2_with_pre_registered_economic_constraints")


def test_audit_rejects_tampered_holdout_hash() -> None:
    method = load_frozen_regime_estimation_method()
    training, holdout = _wrappers([0.5, 0.1, 0.1, 0.4, 0.1, 0.1, -0.5])
    result = holdout["result"]
    assert isinstance(result, dict)
    result["model_prediction_krw_million"] = 999.0

    with pytest.raises(ValueError, match="persisted hash mismatch"):
        build_regime_economic_audit(method, training, holdout)
