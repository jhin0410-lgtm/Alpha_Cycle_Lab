from __future__ import annotations

from alpha_cycle.intelligence.semiconductor_forward_operating_model_contract import (
    SEMICONDUCTOR_FORWARD_MODEL_CONTRACTS,
    IssuerForwardModelCertification,
    ModelBlockCertification,
    evaluate_issuer_forward_model_readiness,
)


def _cert(block_id: str, ready: bool = True) -> ModelBlockCertification:
    return ModelBlockCertification(
        block_id=block_id,
        baseline_certified=ready,
        forward_drivers_certified=ready,
        output_method_certified=ready,
        source_vintage_certified=ready,
    )


def test_samsung_and_hynix_forward_models_are_not_the_same_company_model() -> None:
    hynix = SEMICONDUCTOR_FORWARD_MODEL_CONTRACTS["000660"]
    samsung = SEMICONDUCTOR_FORWARD_MODEL_CONTRACTS["005930"]
    assert {block.block_id for block in hynix.blocks} == {
        "dram_total",
        "hbm_mix_overlay",
        "nand_and_solutions",
        "other_products_services",
        "corporate_other",
    }
    assert {block.block_id for block in samsung.blocks} == {
        "ds_memory",
        "ds_foundry_system_lsi",
        "dx",
        "sdc",
        "harman",
        "corporate_eliminations",
    }
    assert "ds_memory_view_does_not_stand_in_for_total_company_earnings" in (
        samsung.reconciliation_requirements
    )
    hbm = next(block for block in hynix.blocks if block.block_id == "hbm_mix_overlay")
    assert hbm.additive_to_company_financials is False
    other = next(block for block in hynix.blocks if block.block_id == "other_products_services")
    assert other.additive_to_company_financials is True
    assert other.required_outputs == ("revenue",)
    assert "hbm_overlay_is_not_double_counted_as_additive_revenue" in (
        hynix.reconciliation_requirements
    )


def test_missing_one_samsung_business_block_blocks_total_company_forward_model() -> None:
    contract = SEMICONDUCTOR_FORWARD_MODEL_CONTRACTS["005930"]
    certifications = tuple(
        _cert(block.block_id)
        for block in contract.blocks
        if block.block_id != "ds_foundry_system_lsi"
    )
    readiness = evaluate_issuer_forward_model_readiness(
        IssuerForwardModelCertification(
            ticker="005930",
            horizon_quarters=6,
            block_certifications=certifications,
            company_reconciliation_certified=True,
            model_version_frozen=True,
        )
    )
    assert readiness.status == "blocked"
    assert readiness.internal_forward_model_certified is False
    assert readiness.numeric_forecast_enabled is False
    assert "block_missing:ds_foundry_system_lsi" in readiness.blockers


def test_source_vintage_and_company_reconciliation_are_required() -> None:
    contract = SEMICONDUCTOR_FORWARD_MODEL_CONTRACTS["000660"]
    certifications = []
    for block in contract.blocks:
        item = _cert(block.block_id)
        if block.block_id == "hbm_mix_overlay":
            item = ModelBlockCertification(
                block_id=block.block_id,
                baseline_certified=True,
                forward_drivers_certified=True,
                output_method_certified=True,
                source_vintage_certified=False,
            )
        certifications.append(item)
    readiness = evaluate_issuer_forward_model_readiness(
        IssuerForwardModelCertification(
            ticker="000660",
            horizon_quarters=6,
            block_certifications=tuple(certifications),
            company_reconciliation_certified=False,
            model_version_frozen=True,
        )
    )
    assert readiness.status == "blocked"
    assert "source_vintage_not_certified:hbm_mix_overlay" in readiness.blockers
    assert "company_reconciliation_not_certified" in readiness.blockers


def test_fully_certified_contract_can_enable_numeric_internal_forward_model() -> None:
    contract = SEMICONDUCTOR_FORWARD_MODEL_CONTRACTS["000660"]
    readiness = evaluate_issuer_forward_model_readiness(
        IssuerForwardModelCertification(
            ticker="000660",
            horizon_quarters=6,
            block_certifications=tuple(_cert(block.block_id) for block in contract.blocks),
            company_reconciliation_certified=True,
            model_version_frozen=True,
        )
    )
    assert readiness.status == "available"
    assert readiness.ready_blocks == readiness.required_blocks
    assert readiness.blockers == ()
    assert readiness.internal_forward_model_certified is True
    assert readiness.numeric_forecast_enabled is True
    assert readiness.decision_score_enabled is False


def test_model_horizon_must_stay_inside_contract() -> None:
    contract = SEMICONDUCTOR_FORWARD_MODEL_CONTRACTS["000660"]
    readiness = evaluate_issuer_forward_model_readiness(
        IssuerForwardModelCertification(
            ticker="000660",
            horizon_quarters=12,
            block_certifications=tuple(_cert(block.block_id) for block in contract.blocks),
            company_reconciliation_certified=True,
            model_version_frozen=True,
        )
    )
    assert readiness.status == "blocked"
    assert "model_horizon_outside_contract" in readiness.blockers
