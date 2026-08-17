from __future__ import annotations

from alpha_cycle.intelligence.sk_hynix_product_profitability_regime_post_validation_audit import (
    RegimeV1PostValidationAuditResult,
    _envelope,
    load_post_validation_audit_policy,
)


def _row(period: str, *, dram_asp: float, dram_bit: float, nand_asp: float, nand_bit: float):
    return {
        "period_id": period,
        "dram_asp_direction_code": dram_asp,
        "dram_bit_volume_direction_code": dram_bit,
        "nand_asp_direction_code": nand_asp,
        "nand_bit_volume_direction_code": nand_bit,
    }


def test_policy_keeps_post_holdout_diagnostics_fail_closed() -> None:
    policy = load_post_validation_audit_policy()

    assert policy.status == "post_holdout_diagnostic_not_predictive_revalidation"
    assert policy.direction_codes == (-1.0, 0.0, 1.0)
    assert policy.nonnegative_cogs_identity_upper_bound == 1.0
    assert policy.negative_margin_is_automatic_failure is False
    assert policy.refit_v1_after_holdout_allowed is False
    assert policy.reuse_2026q1_as_unseen_holdout_for_v2_allowed is False


def test_margin_envelope_flags_upper_bound_but_not_negative_margin() -> None:
    policy = load_post_validation_audit_policy()
    rows = (
        _row(
            "2025Q1",
            dram_asp=1.0,
            dram_bit=1.0,
            nand_asp=-1.0,
            nand_bit=-1.0,
        ),
    )

    envelope = _envelope(
        product="dram",
        base=0.90,
        asp_effect=0.20,
        bit_effect=0.10,
        rows=rows,
        policy=policy,
    )
    negative = _envelope(
        product="nand",
        base=-0.50,
        asp_effect=0.10,
        bit_effect=0.10,
        rows=rows,
        policy=policy,
    )

    assert envelope.maximum_implied_margin_ratio == 1.20
    assert envelope.upper_bound_violation_count > 0
    assert envelope.observed_upper_bound_violation_periods == ("2025Q1",)
    assert negative.minimum_implied_margin_ratio == -0.70
    assert negative.upper_bound_violation_count == 0


def test_predictive_pass_does_not_override_structural_failure() -> None:
    policy = load_post_validation_audit_policy()
    rows = (
        _row(
            "2025Q1",
            dram_asp=1.0,
            dram_bit=1.0,
            nand_asp=1.0,
            nand_bit=1.0,
        ),
    )
    dram = _envelope(
        product="dram",
        base=0.90,
        asp_effect=0.20,
        bit_effect=0.10,
        rows=rows,
        policy=policy,
    )
    nand = _envelope(
        product="nand",
        base=0.40,
        asp_effect=0.10,
        bit_effect=0.10,
        rows=rows,
        policy=policy,
    )

    result = RegimeV1PostValidationAuditResult(
        evidence_id="a" * 64,
        policy_evidence_id="b" * 64,
        method_evidence_id="c" * 64,
        training_fit_evidence_id="d" * 64,
        holdout_evidence_id="e" * 64,
        predictive_validation_passed=True,
        structural_margin_interpretation_passed=False,
        forward_forecast_contract_review_allowed=False,
        model_status="predictively_validated_structurally_noninterpretable",
        dram_margin_envelope=dram,
        nand_margin_envelope=nand,
        other_margin_constant=-5.0,
        other_margin_absolute_value_gt_one_report_only=True,
        max_leverage_report_only=0.80,
        max_cooks_distance_report_only=0.95,
        coefficient_jackknife_report_only=True,
    )

    assert result.predictive_validation_passed is True
    assert result.structural_margin_interpretation_passed is False
    assert result.forward_forecast_contract_review_allowed is False
    assert result.refit_v1_after_holdout_allowed is False
    assert result.numeric_forecast_enabled is False
