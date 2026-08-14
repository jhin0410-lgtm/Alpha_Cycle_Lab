from __future__ import annotations

import hashlib
from dataclasses import replace
from datetime import date

import pytest

from alpha_cycle.intelligence.semiconductor_baseline_allocation import (
    BaselineAllocationMethod,
    build_direct_share_revenue_allocation,
    reconcile_company_revenue,
    validate_baseline_allocation_method,
    validate_source_bound_allocation_input,
)

PERIOD_START = date(2026, 4, 1)
PERIOD_END = date(2026, 6, 30)


def _id(label: str) -> str:
    return hashlib.sha256(label.encode("utf-8")).hexdigest()


def _input_raw(
    semantic_id: str,
    value: float,
    unit: str,
    evidence_label: str,
    *,
    ticker: str = "000660",
    period_start: date = PERIOD_START,
    period_end: date = PERIOD_END,
) -> dict[str, object]:
    return {
        "ticker": ticker,
        "semantic_id": semantic_id,
        "value": value,
        "unit": unit,
        "period_start": period_start.isoformat(),
        "period_end": period_end.isoformat(),
        "source_evidence_id": _id(evidence_label),
    }


def _method_raw(
    block_id: str,
    baseline_requirement_id: str,
    method_label: str,
    *,
    output_metric: str = "revenue",
    method_status: str = "observationally_calibrated",
    method_version_frozen: bool = True,
) -> dict[str, object]:
    return {
        "ticker": "000660",
        "block_id": block_id,
        "baseline_requirement_id": baseline_requirement_id,
        "output_metric": output_metric,
        "method_id": f"{method_label}_direct_share",
        "method_version": "1.0",
        "method_kind": "direct_share_allocation",
        "method_status": method_status,
        "method_version_frozen": method_version_frozen,
        "supporting_evidence_ids": [_id(f"{method_label}_method_evidence")],
        "rationale": "Allocate reported company revenue using a source-bounded product share.",
        "invalidation_condition": "Invalidate if share semantics or accounting scope changes.",
    }


def _verified_ids() -> set[str]:
    return {
        _id("company_revenue"),
        _id("dram_share"),
        _id("nand_share"),
        _id("other_share"),
        _id("dram_method_evidence"),
        _id("nand_method_evidence"),
        _id("other_method_evidence"),
    }


def _ready_inputs():
    verified = _verified_ids()
    company = validate_source_bound_allocation_input(
        _input_raw("reported_company_revenue", 100.0, "KRW_trillion", "company_revenue"),
        verified_evidence_ids=verified,
    )
    dram_share = validate_source_bound_allocation_input(
        _input_raw("dram_revenue_share", 70.0, "percent", "dram_share"),
        verified_evidence_ids=verified,
    )
    nand_share = validate_source_bound_allocation_input(
        _input_raw("nand_revenue_share", 30.0, "percent", "nand_share"),
        verified_evidence_ids=verified,
    )
    return company, dram_share, nand_share


def _ready_methods() -> tuple[BaselineAllocationMethod, BaselineAllocationMethod]:
    verified = _verified_ids()
    dram = validate_baseline_allocation_method(
        _method_raw(
            "dram_total",
            "dram_revenue_or_company_memory_bridge",
            "dram",
        ),
        verified_evidence_ids=verified,
    )
    nand = validate_baseline_allocation_method(
        _method_raw(
            "nand_and_solutions",
            "nand_solution_revenue_bridge",
            "nand",
        ),
        verified_evidence_ids=verified,
    )
    return dram, nand


def _other_method() -> BaselineAllocationMethod:
    return validate_baseline_allocation_method(
        _method_raw(
            "other_products_services",
            "other_products_services_revenue_bridge",
            "other",
        ),
        verified_evidence_ids=_verified_ids(),
    )


def test_derived_revenue_is_explicitly_not_a_source_fact() -> None:
    company, dram_share, _ = _ready_inputs()
    dram_method, _ = _ready_methods()

    allocation = build_direct_share_revenue_allocation(
        total_input=company,
        share_input=dram_share,
        method=dram_method,
    )

    assert allocation.value == pytest.approx(70.0)
    assert allocation.output_metric == "revenue"
    assert allocation.source_fact is False
    assert allocation.derived_not_source_fact is True
    assert allocation.residual_derivation_used is False
    assert allocation.profitability_allocation_used is False
    assert allocation.allocation_ready is True
    assert allocation.numeric_forecast_enabled is False

    with pytest.raises(ValueError, match="explicitly non-source-fact"):
        replace(allocation, source_fact=True)


def test_draft_or_unfrozen_method_never_becomes_allocation_ready() -> None:
    company, dram_share, _ = _ready_inputs()
    verified = _verified_ids()

    draft = validate_baseline_allocation_method(
        _method_raw(
            "dram_total",
            "dram_revenue_or_company_memory_bridge",
            "dram",
            method_status="documented",
        ),
        verified_evidence_ids=verified,
    )
    unfrozen = validate_baseline_allocation_method(
        _method_raw(
            "dram_total",
            "dram_revenue_or_company_memory_bridge",
            "dram",
            method_version_frozen=False,
        ),
        verified_evidence_ids=verified,
    )

    assert draft.method_use_ready is False
    assert unfrozen.method_use_ready is False
    assert build_direct_share_revenue_allocation(
        total_input=company,
        share_input=dram_share,
        method=draft,
    ).allocation_ready is False
    assert build_direct_share_revenue_allocation(
        total_input=company,
        share_input=dram_share,
        method=unfrozen,
    ).allocation_ready is False


def test_unverified_source_or_method_evidence_blocks_ready_allocation() -> None:
    company, dram_share, _ = _ready_inputs()
    method = validate_baseline_allocation_method(
        _method_raw(
            "dram_total",
            "dram_revenue_or_company_memory_bridge",
            "dram",
        ),
        verified_evidence_ids=set(),
    )
    unverified_share = validate_source_bound_allocation_input(
        _input_raw("dram_revenue_share", 70.0, "percent", "dram_share"),
        verified_evidence_ids=set(),
    )

    assert method.method_use_ready is False
    assert unverified_share.source_evidence_verified is False
    assert build_direct_share_revenue_allocation(
        total_input=company,
        share_input=dram_share,
        method=method,
    ).allocation_ready is False
    assert build_direct_share_revenue_allocation(
        total_input=company,
        share_input=unverified_share,
        method=_ready_methods()[0],
    ).allocation_ready is False


def test_v1_refuses_profitability_and_non_additive_hbm_allocation() -> None:
    verified = _verified_ids()

    with pytest.raises(ValueError, match="supports revenue outputs only"):
        validate_baseline_allocation_method(
            _method_raw(
                "dram_total",
                "dram_revenue_or_company_memory_bridge",
                "dram",
                output_metric="gross_profit_or_margin",
            ),
            verified_evidence_ids=verified,
        )

    with pytest.raises(ValueError, match="reconciliation-artifact baseline"):
        validate_baseline_allocation_method(
            _method_raw(
                "hbm_mix_overlay",
                "hbm_mix_or_revenue_share",
                "dram",
            ),
            verified_evidence_ids=verified,
        )


def test_dram_and_nand_only_never_certify_company_revenue_without_other_block() -> None:
    company, dram_share, nand_share = _ready_inputs()
    dram_method, nand_method = _ready_methods()
    dram = build_direct_share_revenue_allocation(
        total_input=company,
        share_input=dram_share,
        method=dram_method,
    )
    nand = build_direct_share_revenue_allocation(
        total_input=company,
        share_input=nand_share,
        method=nand_method,
    )

    reconciliation = reconcile_company_revenue(
        ticker="000660",
        allocations=(dram, nand),
        reported_company_revenue=company,
    )

    assert reconciliation.required_revenue_blocks == (
        "dram_total",
        "nand_and_solutions",
        "other_products_services",
    )
    assert reconciliation.allocated_revenue_blocks == ("dram_total", "nand_and_solutions")
    assert reconciliation.missing_revenue_blocks == ("other_products_services",)
    assert reconciliation.allocated_revenue_total == pytest.approx(100.0)
    assert reconciliation.reconciliation_delta == pytest.approx(0.0)
    assert reconciliation.revenue_reconciliation_certified is False
    assert reconciliation.revenue_model_input_ready is False
    assert reconciliation.profitability_baseline_certified is False
    assert reconciliation.full_baseline_certified is False
    assert reconciliation.residual_derivation_enabled is False


def test_all_three_explicit_revenue_blocks_can_reconcile_company_total() -> None:
    verified = _verified_ids()
    company = validate_source_bound_allocation_input(
        _input_raw("reported_company_revenue", 100.0, "KRW_trillion", "company_revenue"),
        verified_evidence_ids=verified,
    )
    dram_share = validate_source_bound_allocation_input(
        _input_raw("dram_revenue_share", 60.0, "percent", "dram_share"),
        verified_evidence_ids=verified,
    )
    nand_share = validate_source_bound_allocation_input(
        _input_raw("nand_revenue_share", 30.0, "percent", "nand_share"),
        verified_evidence_ids=verified,
    )
    other_share = validate_source_bound_allocation_input(
        _input_raw("other_products_services_revenue_share", 10.0, "percent", "other_share"),
        verified_evidence_ids=verified,
    )
    dram_method, nand_method = _ready_methods()
    allocations = (
        build_direct_share_revenue_allocation(
            total_input=company,
            share_input=dram_share,
            method=dram_method,
        ),
        build_direct_share_revenue_allocation(
            total_input=company,
            share_input=nand_share,
            method=nand_method,
        ),
        build_direct_share_revenue_allocation(
            total_input=company,
            share_input=other_share,
            method=_other_method(),
        ),
    )
    reconciliation = reconcile_company_revenue(
        ticker="000660",
        allocations=allocations,
        reported_company_revenue=company,
    )
    assert reconciliation.missing_revenue_blocks == ()
    assert reconciliation.allocated_revenue_total == pytest.approx(100.0)
    assert reconciliation.revenue_reconciliation_certified is True
    assert reconciliation.revenue_model_input_ready is True
    assert reconciliation.full_baseline_certified is False
    assert reconciliation.numeric_forecast_enabled is False
    assert reconciliation.decision_score_enabled is False


def test_company_reconciliation_mismatch_or_missing_block_remains_blocked() -> None:
    company, dram_share, _ = _ready_inputs()
    dram_method, nand_method = _ready_methods()
    verified = _verified_ids() | {_id("nand_share_20")}
    nand_share_20 = validate_source_bound_allocation_input(
        _input_raw("nand_revenue_share", 20.0, "percent", "nand_share_20"),
        verified_evidence_ids=verified,
    )
    dram = build_direct_share_revenue_allocation(
        total_input=company,
        share_input=dram_share,
        method=dram_method,
    )
    nand = build_direct_share_revenue_allocation(
        total_input=company,
        share_input=nand_share_20,
        method=nand_method,
    )

    mismatch = reconcile_company_revenue(
        ticker="000660",
        allocations=(dram, nand),
        reported_company_revenue=company,
    )
    missing = reconcile_company_revenue(
        ticker="000660",
        allocations=(dram,),
        reported_company_revenue=company,
    )

    assert mismatch.allocated_revenue_total == pytest.approx(90.0)
    assert mismatch.reconciliation_delta == pytest.approx(-10.0)
    assert mismatch.missing_revenue_blocks == ("other_products_services",)
    assert mismatch.revenue_reconciliation_certified is False
    assert mismatch.revenue_model_input_ready is False
    assert missing.missing_revenue_blocks == (
        "nand_and_solutions",
        "other_products_services",
    )
    assert missing.revenue_reconciliation_certified is False


def test_period_unit_and_duplicate_block_mismatches_fail_closed() -> None:
    company, dram_share, nand_share = _ready_inputs()
    dram_method, nand_method = _ready_methods()
    dram = build_direct_share_revenue_allocation(
        total_input=company,
        share_input=dram_share,
        method=dram_method,
    )
    nand = build_direct_share_revenue_allocation(
        total_input=company,
        share_input=nand_share,
        method=nand_method,
    )

    later_share = validate_source_bound_allocation_input(
        _input_raw(
            "dram_revenue_share",
            70.0,
            "percent",
            "dram_share",
            period_start=date(2026, 7, 1),
            period_end=date(2026, 9, 30),
        ),
        verified_evidence_ids=_verified_ids(),
    )
    with pytest.raises(ValueError, match="same accounting period"):
        build_direct_share_revenue_allocation(
            total_input=company,
            share_input=later_share,
            method=dram_method,
        )

    with pytest.raises(ValueError, match="duplicate revenue block"):
        reconcile_company_revenue(
            ticker="000660",
            allocations=(dram, dram, nand),
            reported_company_revenue=company,
        )

    company_won = validate_source_bound_allocation_input(
        _input_raw("reported_company_revenue", 100.0, "KRW_billion", "company_revenue"),
        verified_evidence_ids=_verified_ids(),
    )
    with pytest.raises(ValueError, match="units must match"):
        reconcile_company_revenue(
            ticker="000660",
            allocations=(dram, nand),
            reported_company_revenue=company_won,
        )
