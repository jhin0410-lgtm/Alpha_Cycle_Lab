from __future__ import annotations

import hashlib
from datetime import date

import pytest

from alpha_cycle.intelligence.semiconductor_baseline_allocation import (
    build_direct_share_revenue_allocation,
    validate_baseline_allocation_method,
    validate_source_bound_allocation_input,
)

PERIOD_START = date(2026, 4, 1)
PERIOD_END = date(2026, 6, 30)


def _id(label: str) -> str:
    return hashlib.sha256(label.encode("utf-8")).hexdigest()


def _input(semantic_id: str, value: float, unit: str, evidence_label: str):
    evidence_id = _id(evidence_label)
    return validate_source_bound_allocation_input(
        {
            "ticker": "000660",
            "semantic_id": semantic_id,
            "value": value,
            "unit": unit,
            "period_start": PERIOD_START.isoformat(),
            "period_end": PERIOD_END.isoformat(),
            "source_evidence_id": evidence_id,
        },
        verified_evidence_ids={evidence_id},
    )


def _method(block_id: str, requirement: str, share_label: str):
    company_id = _id("company")
    share_id = _id(share_label)
    calibration_id = _id("calibration")
    return validate_baseline_allocation_method(
        {
            "ticker": "000660",
            "block_id": block_id,
            "baseline_requirement_id": requirement,
            "output_metric": "revenue",
            "method_id": f"{block_id}_direct_share",
            "method_version": "1.0",
            "method_kind": "direct_share_allocation",
            "method_status": "observationally_calibrated",
            "method_version_frozen": True,
            "supporting_evidence_ids": [company_id, share_id, calibration_id],
            "rationale": "Use only the registered issuer share semantic.",
            "invalidation_condition": "Invalidate on source semantic drift.",
        },
        verified_evidence_ids={company_id, share_id, calibration_id},
    )


def test_dram_block_rejects_nand_share_semantic() -> None:
    company = _input("reported_company_revenue", 100.0, "KRW_billion", "company")
    wrong_share = _input("nand_revenue_share", 70.0, "percent", "dram_share")
    method = _method(
        "dram_total",
        "dram_revenue_or_company_memory_bridge",
        "dram_share",
    )
    with pytest.raises(ValueError, match="share semantic is outside"):
        build_direct_share_revenue_allocation(
            total_input=company,
            share_input=wrong_share,
            method=method,
        )


def test_nand_block_rejects_unregistered_other_share_semantic() -> None:
    company = _input("reported_company_revenue", 100.0, "KRW_billion", "company")
    wrong_share = _input(
        "other_products_services_revenue_share",
        10.0,
        "percent",
        "nand_share",
    )
    method = _method(
        "nand_and_solutions",
        "nand_solution_revenue_bridge",
        "nand_share",
    )
    with pytest.raises(ValueError, match="share semantic is outside"):
        build_direct_share_revenue_allocation(
            total_input=company,
            share_input=wrong_share,
            method=method,
        )
