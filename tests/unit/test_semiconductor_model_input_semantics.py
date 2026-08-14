from __future__ import annotations

from alpha_cycle.intelligence.semiconductor_model_input_semantics import (
    audit_baseline_semantics_registry,
    baseline_requirement_semantics,
)


def test_every_forward_model_baseline_has_explicit_semantics() -> None:
    assert audit_baseline_semantics_registry() == ()


def test_composite_revenue_profit_bridge_is_not_one_scalar_source_fact() -> None:
    samsung = baseline_requirement_semantics(
        "005930",
        "ds_memory",
        "ds_memory_revenue_and_profit_bridge",
    )
    assert samsung.requirement_kind == "reconciliation_artifact"
    assert samsung.direct_numeric_source_fact_sufficient is False
    assert samsung.reconciliation_required is True


def test_hbm_mix_share_can_be_supported_by_direct_numeric_issuer_fact() -> None:
    hynix = baseline_requirement_semantics(
        "000660",
        "hbm_mix_overlay",
        "hbm_mix_or_revenue_share",
    )
    assert hynix.requirement_kind == "direct_numeric_or_share"
    assert hynix.direct_numeric_source_fact_sufficient is True
    assert hynix.reconciliation_required is False


def test_hynix_other_product_revenue_requires_reconciled_baseline_bridge() -> None:
    other = baseline_requirement_semantics(
        "000660",
        "other_products_services",
        "other_products_services_revenue_bridge",
    )
    assert other.requirement_kind == "reconciliation_artifact"
    assert other.direct_numeric_source_fact_sufficient is False
    assert other.reconciliation_required is True
