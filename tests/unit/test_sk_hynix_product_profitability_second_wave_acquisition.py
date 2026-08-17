from __future__ import annotations

from alpha_cycle.intelligence.sk_hynix_product_profitability_second_wave_acquisition import (
    SecondWaveAcquisitionResult,
)


def test_second_wave_source_completion_does_not_promote_training_or_fit() -> None:
    result = SecondWaveAcquisitionResult(
        period_id="2019Q1",
        driver_four_field_numeric_source_certified=True,
        product_revenue_probe_success=True,
        company_profitability_verified=True,
        product_artifact_pointer="artifact.json",
        company_observation=None,
        product_error=None,
        company_error=None,
    )

    assert result.source_layer_complete is True
    assert result.training_row_promoted is False
    assert result.fit_enabled is False
    assert result.holdout_evaluation_allowed is False
