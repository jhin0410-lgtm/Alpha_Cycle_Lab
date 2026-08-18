from __future__ import annotations

from datetime import date

import pytest

from alpha_cycle.intelligence.sk_hynix_company_gp_empirical_v5_q3_holdout import (
    V5Q3CertifiedSourceBundle,
    V5Q3ValidationBinding,
    score_v5_q3_holdout_once,
)
from alpha_cycle.intelligence.sk_hynix_company_gp_empirical_v5_q3_holdout_protocol import (
    load_frozen_v5_q3_holdout_protocol,
)


def _binding(method_evidence_id: str, protocol_evidence_id: str) -> V5Q3ValidationBinding:
    return V5Q3ValidationBinding(
        evidence_id="a" * 64,
        protocol_evidence_id=protocol_evidence_id,
        method_evidence_id=method_evidence_id,
        fit_evidence_id="b" * 64,
        fit_evaluation_date=date(2026, 8, 18),
        training_periods=tuple(f"P{index:02d}" for index in range(21)),
        coefficients=(0.5, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0),
        training_mean_company_gross_margin=0.4,
        training_snapshot_hash="c" * 64,
        development_gate_passed=True,
        training_fit_reproduced_exactly=True,
    )


def _source(evidence_id: str = "d" * 64) -> V5Q3CertifiedSourceBundle:
    return V5Q3CertifiedSourceBundle(
        evidence_id=evidence_id,
        period_id="2026Q3",
        source_evaluation_date=date(2026, 10, 31),
        company_profitability_evidence_id="e" * 64,
        product_revenue_evidence_id="f" * 64,
        cycle_driver_evidence_id="1" * 64,
        company_revenue_krw_million=1000.0,
        product_total_revenue_krw_million=1000.0,
        actual_gross_profit_krw_million=500.0,
        nand_revenue_krw_million=200.0,
        other_revenue_krw_million=50.0,
        dram_asp_direction_code=0.0,
        dram_bit_volume_direction_code=0.0,
        nand_asp_direction_code=0.0,
        nand_bit_volume_direction_code=0.0,
        company_profitability_certified=True,
        product_revenue_mix_certified=True,
        cycle_driver_directions_certified=True,
        source_bundle_certified_complete=True,
    )


def test_frozen_v5_q3_protocol_binds_current_v5_method() -> None:
    protocol, method = load_frozen_v5_q3_holdout_protocol()
    assert protocol.bound_method_evidence_id == method.evidence_id
    assert protocol.holdout_period == "2026Q3"
    assert protocol.conditional_one_time_evaluation_pre_authorized
    assert protocol.readiness_checker_must_not_load_holdout
    assert not protocol.validates_pre_earnings_forecastability
    assert not protocol.product_margin_structural_interpretation_allowed
    assert not protocol.numeric_forward_forecast_enabled


def test_v5_q3_score_is_immutable_and_reuses_first_result(tmp_path) -> None:
    protocol, method = load_frozen_v5_q3_holdout_protocol()
    binding = _binding(method.evidence_id, protocol.evidence_id)
    source = _source()
    output = tmp_path / "holdout.json"

    first, reused_first = score_v5_q3_holdout_once(
        protocol,
        binding,
        source,
        output=output,
    )
    assert not reused_first
    assert first.model_prediction_krw_million == pytest.approx(500.0)
    assert first.benchmark_prediction_krw_million == pytest.approx(400.0)
    assert first.model_beats_benchmark
    assert first.holdout_validation_passed
    assert not first.validates_pre_earnings_forecastability
    assert not first.investment_action_enabled

    second, reused_second = score_v5_q3_holdout_once(
        protocol,
        binding,
        source,
        output=output,
    )
    assert reused_second
    assert second.evidence_id == first.evidence_id

    with pytest.raises(ValueError, match="source bundle changed"):
        score_v5_q3_holdout_once(
            protocol,
            binding,
            _source("9" * 64),
            output=output,
        )


def test_v5_q3_source_bundle_rejects_uncertified_input() -> None:
    with pytest.raises(ValueError, match="not completely certified"):
        V5Q3CertifiedSourceBundle(
            evidence_id="d" * 64,
            period_id="2026Q3",
            source_evaluation_date=date(2026, 10, 31),
            company_profitability_evidence_id="e" * 64,
            product_revenue_evidence_id="f" * 64,
            cycle_driver_evidence_id="1" * 64,
            company_revenue_krw_million=1000.0,
            product_total_revenue_krw_million=1000.0,
            actual_gross_profit_krw_million=500.0,
            nand_revenue_krw_million=200.0,
            other_revenue_krw_million=50.0,
            dram_asp_direction_code=0.0,
            dram_bit_volume_direction_code=0.0,
            nand_asp_direction_code=0.0,
            nand_bit_volume_direction_code=0.0,
            company_profitability_certified=True,
            product_revenue_mix_certified=True,
            cycle_driver_directions_certified=False,
            source_bundle_certified_complete=False,
        )
