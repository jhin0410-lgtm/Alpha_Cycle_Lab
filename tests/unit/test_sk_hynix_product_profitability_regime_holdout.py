from __future__ import annotations

from datetime import date
from types import SimpleNamespace
from typing import cast

import pytest

from alpha_cycle.intelligence.sk_hynix_product_profitability_regime_estimation_method import (
    FrozenRegimeEstimationMethod,
)
from alpha_cycle.intelligence.sk_hynix_product_profitability_regime_holdout import (
    RegimeHoldoutResult,
    spend_regime_holdout_once,
)
from alpha_cycle.intelligence.sk_hynix_product_profitability_regime_training_fit import (
    RegimeTrainingFitResult,
)
from alpha_cycle.intelligence.sk_hynix_product_profitability_regime_validation_protocol import (
    RegimeValidationProtocol,
)


def test_holdout_result_is_spent_and_immutable() -> None:
    result = RegimeHoldoutResult(
        evidence_id="a" * 64,
        method_evidence_id="b" * 64,
        training_fit_evidence_id="c" * 64,
        holdout_period="2026Q1",
        source_evaluation_date=date(2026, 8, 17),
        product_revenue_evidence_id="d" * 64,
        company_profitability_evidence_id="e" * 64,
        cycle_driver_evidence_id="f" * 64,
        company_revenue_krw_million=10_000.0,
        actual_gross_profit_krw_million=4_000.0,
        model_prediction_krw_million=3_900.0,
        model_absolute_error_krw_million=100.0,
        benchmark_prediction_krw_million=3_500.0,
        benchmark_absolute_error_krw_million=500.0,
        model_beats_benchmark=True,
        company_product_revenue_reconciled=True,
        holdout_validation_passed=True,
    )

    assert result.holdout_spent is True
    assert result.immutable_result is True
    assert result.refit_after_holdout_allowed is False


def test_holdout_cannot_score_before_training_gate(tmp_path) -> None:
    method = cast(
        FrozenRegimeEstimationMethod,
        SimpleNamespace(evidence_id="a" * 64),
    )
    protocol = cast(
        RegimeValidationProtocol,
        SimpleNamespace(method_evidence_id="a" * 64),
    )
    training = cast(
        RegimeTrainingFitResult,
        SimpleNamespace(
            one_time_holdout_evaluation_ready=False,
            method_evidence_id="a" * 64,
            evidence_id="b" * 64,
        ),
    )

    with pytest.raises(ValueError, match="before the training gate passes"):
        spend_regime_holdout_once(
            method,
            protocol,
            training,
            source_evaluation_date=date(2026, 8, 17),
            historical_product_revenue_pointer=tmp_path / "must_not_be_read.json",
            company_profitability_pointer=tmp_path / "must_not_be_read_company.json",
            cycle_driver_pointer=tmp_path / "must_not_be_read_cycle.json",
            output=tmp_path / "output",
        )
