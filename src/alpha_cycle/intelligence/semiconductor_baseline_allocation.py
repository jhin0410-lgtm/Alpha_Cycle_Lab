"""Derived semiconductor baseline allocation without weakening source-fact boundaries.

The direct-fact baseline reconciliation layer remains authoritative for disclosed
accounting facts. This module is a separate model layer for combining verified company
revenue and directly evidenced product shares, while also allowing an explicitly reported
product-revenue amount to be referenced without relabeling the wrapper as a source fact.

V1 supports only direct-share revenue allocation and direct-amount revenue references.
Profitability allocation, residual arithmetic, peer substitution, and automatic company-
model certification remain disabled. A direct-share method must be observationally
calibrated; a direct-amount reference must be source-mapped. Both paths must be frozen and
evidence-backed. Even a certified revenue bridge cannot enable a numeric forward forecast
by itself.
"""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from datetime import date

from alpha_cycle.intelligence.semiconductor_forward_operating_model_contract import (
    SEMICONDUCTOR_FORWARD_MODEL_CONTRACTS,
    ForwardModelBlock,
)
from alpha_cycle.intelligence.semiconductor_model_input_semantics import (
    baseline_requirement_semantics,
)

_ALLOWED_METHOD_KINDS = frozenset({"direct_share_allocation", "direct_amount_reference"})
_ALLOWED_METHOD_STATUS = frozenset(
    {"draft", "documented", "observationally_calibrated", "source_mapped"}
)
_SHARE_UNITS = frozenset({"fraction", "percent"})
_DIRECT_SHARE_SEMANTICS = {
    ("000660", "dram_total"): "dram_revenue_share",
    ("000660", "nand_and_solutions"): "nand_revenue_share",
}
_DIRECT_AMOUNT_SEMANTICS = {
    ("000660", "other_products_services"): "other_products_services_revenue",
}


def _sha(payload: dict[str, object]) -> str:
    return hashlib.sha256(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode(
            "utf-8"
        )
    ).hexdigest()


def _valid_sha(value: str) -> bool:
    return len(value) == 64 and all(char in "0123456789abcdef" for char in value)


def _registered_block(ticker: str, block_id: str) -> ForwardModelBlock:
    contract = SEMICONDUCTOR_FORWARD_MODEL_CONTRACTS.get(ticker)
    if contract is None:
        raise ValueError(f"Baseline allocation issuer is not registered: {ticker}")
    block = next((item for item in contract.blocks if item.block_id == block_id), None)
    if block is None:
        raise ValueError(f"Baseline allocation block is not registered: {ticker}/{block_id}")
    return block


def _ready_method_status(method_kind: str, method_status: str) -> bool:
    if method_kind == "direct_share_allocation":
        return method_status == "observationally_calibrated"
    if method_kind == "direct_amount_reference":
        return method_status == "source_mapped"
    return False


@dataclass(frozen=True)
class SourceBoundAllocationInput:
    input_id: str
    ticker: str
    semantic_id: str
    value: float
    unit: str
    period_start: date
    period_end: date
    source_evidence_id: str
    source_evidence_verified: bool
    source_fact_reference: bool = True
    decision_score_enabled: bool = False

    def __post_init__(self) -> None:
        if not _valid_sha(self.input_id) or not _valid_sha(self.source_evidence_id):
            raise ValueError("Baseline allocation input IDs must be SHA-256")
        if self.ticker not in SEMICONDUCTOR_FORWARD_MODEL_CONTRACTS:
            raise ValueError(f"Baseline allocation issuer is not registered: {self.ticker}")
        if not self.semantic_id.strip() or not self.unit.strip():
            raise ValueError("Baseline allocation input semantic/unit cannot be blank")
        if not math.isfinite(self.value):
            raise ValueError("Baseline allocation input value must be finite")
        if self.period_start > self.period_end:
            raise ValueError("Baseline allocation input period is invalid")
        if not self.source_fact_reference:
            raise ValueError("Baseline allocation input must reference source-bounded evidence")
        if self.decision_score_enabled:
            raise ValueError("Baseline allocation inputs must remain non-scoring")


@dataclass(frozen=True)
class BaselineAllocationMethod:
    method_id: str
    method_version: str
    ticker: str
    block_id: str
    baseline_requirement_id: str
    output_metric: str
    method_kind: str
    method_status: str
    method_version_frozen: bool
    supporting_evidence_ids: tuple[str, ...]
    supporting_evidence_verified: bool
    rationale: str
    invalidation_condition: str
    method_use_ready: bool
    source_fact: bool = False
    residual_derivation_enabled: bool = False
    profitability_allocation_enabled: bool = False
    decision_score_enabled: bool = False

    def __post_init__(self) -> None:
        if not self.method_id.strip() or not self.method_version.strip():
            raise ValueError("Baseline allocation method identity cannot be blank")
        if self.method_kind not in _ALLOWED_METHOD_KINDS:
            raise ValueError("Baseline allocation method_kind is invalid")
        if self.method_status not in _ALLOWED_METHOD_STATUS:
            raise ValueError("Baseline allocation method_status is invalid")
        block = _registered_block(self.ticker, self.block_id)
        if self.baseline_requirement_id not in block.required_baseline_metrics:
            raise ValueError("Baseline allocation requirement is outside block contract")
        semantics = baseline_requirement_semantics(
            self.ticker,
            self.block_id,
            self.baseline_requirement_id,
        )
        if not semantics.reconciliation_required:
            raise ValueError("Baseline allocation requires a reconciliation-artifact baseline")
        if self.output_metric != "revenue" or self.output_metric not in block.required_outputs:
            raise ValueError("Baseline allocation v1 supports revenue outputs only")
        if not block.additive_to_company_financials:
            raise ValueError("Baseline allocation cannot target a non-additive overlay block")
        if not self.rationale.strip() or not self.invalidation_condition.strip():
            raise ValueError("Baseline allocation method requires rationale and invalidation")
        if not self.supporting_evidence_ids or any(
            not _valid_sha(item) for item in self.supporting_evidence_ids
        ):
            raise ValueError("Baseline allocation method evidence IDs must be SHA-256")
        if self.source_fact:
            raise ValueError("Baseline allocation method cannot be labeled a source fact")
        if self.residual_derivation_enabled or self.profitability_allocation_enabled:
            raise ValueError("Baseline allocation v1 prohibits residual/profitability allocation")
        if self.decision_score_enabled:
            raise ValueError("Baseline allocation method must remain non-scoring")
        if self.method_use_ready and (
            not _ready_method_status(self.method_kind, self.method_status)
            or not self.method_version_frozen
            or not self.supporting_evidence_verified
        ):
            raise ValueError("Ready allocation method has an invalid status/evidence boundary")


@dataclass(frozen=True)
class DerivedBaselineAllocation:
    allocation_id: str
    ticker: str
    block_id: str
    baseline_requirement_id: str
    output_metric: str
    value: float
    unit: str
    period_start: date
    period_end: date
    method_id: str
    method_version: str
    source_input_ids: tuple[str, ...]
    source_evidence_ids: tuple[str, ...]
    allocation_ready: bool
    source_fact: bool = False
    derived_not_source_fact: bool = True
    residual_derivation_used: bool = False
    profitability_allocation_used: bool = False
    numeric_forecast_enabled: bool = False
    decision_score_enabled: bool = False

    def __post_init__(self) -> None:
        if not _valid_sha(self.allocation_id):
            raise ValueError("Derived baseline allocation_id must be SHA-256")
        block = _registered_block(self.ticker, self.block_id)
        if self.baseline_requirement_id not in block.required_baseline_metrics:
            raise ValueError("Derived baseline requirement is outside block contract")
        if self.output_metric != "revenue" or self.output_metric not in block.required_outputs:
            raise ValueError("Derived baseline allocation v1 supports revenue only")
        if not math.isfinite(self.value) or not self.unit.strip():
            raise ValueError("Derived baseline value/unit is invalid")
        if self.period_start > self.period_end:
            raise ValueError("Derived baseline period is invalid")
        if not self.source_input_ids or any(not _valid_sha(item) for item in self.source_input_ids):
            raise ValueError("Derived baseline source input IDs must be SHA-256")
        if not self.source_evidence_ids or any(
            not _valid_sha(item) for item in self.source_evidence_ids
        ):
            raise ValueError("Derived baseline source evidence IDs must be SHA-256")
        if self.source_fact or not self.derived_not_source_fact:
            raise ValueError("Derived baseline must remain explicitly non-source-fact")
        if self.residual_derivation_used or self.profitability_allocation_used:
            raise ValueError("Derived baseline v1 cannot use residual/profitability allocation")
        if self.numeric_forecast_enabled or self.decision_score_enabled:
            raise ValueError("Derived baseline allocation cannot enable forecast/scoring")


@dataclass(frozen=True)
class CompanyRevenueReconciliation:
    reconciliation_id: str
    ticker: str
    period_start: date
    period_end: date
    unit: str
    required_revenue_blocks: tuple[str, ...]
    allocated_revenue_blocks: tuple[str, ...]
    missing_revenue_blocks: tuple[str, ...]
    allocated_revenue_total: float
    reported_company_revenue: float
    reconciliation_delta: float
    absolute_tolerance: float
    all_allocations_ready: bool
    revenue_reconciliation_certified: bool
    revenue_model_input_ready: bool
    profitability_baseline_certified: bool = False
    full_baseline_certified: bool = False
    residual_derivation_enabled: bool = False
    numeric_forecast_enabled: bool = False
    decision_score_enabled: bool = False

    def __post_init__(self) -> None:
        if not _valid_sha(self.reconciliation_id):
            raise ValueError("Company revenue reconciliation_id must be SHA-256")
        if self.ticker not in SEMICONDUCTOR_FORWARD_MODEL_CONTRACTS:
            raise ValueError(f"Company reconciliation issuer is not registered: {self.ticker}")
        if self.period_start > self.period_end or not self.unit.strip():
            raise ValueError("Company revenue reconciliation period/unit is invalid")
        if not math.isfinite(self.allocated_revenue_total) or not math.isfinite(
            self.reported_company_revenue
        ):
            raise ValueError("Company revenue reconciliation values must be finite")
        if not math.isfinite(self.reconciliation_delta) or self.absolute_tolerance < 0:
            raise ValueError("Company revenue reconciliation delta/tolerance is invalid")
        if self.revenue_model_input_ready != self.revenue_reconciliation_certified:
            raise ValueError("Revenue model readiness must equal certified reconciliation")
        if self.profitability_baseline_certified or self.full_baseline_certified:
            raise ValueError("Revenue allocation v1 cannot certify profitability/full baseline")
        if self.residual_derivation_enabled:
            raise ValueError("Company revenue reconciliation v1 prohibits residual derivation")
        if self.numeric_forecast_enabled or self.decision_score_enabled:
            raise ValueError("Company revenue reconciliation cannot enable forecast/scoring")


def validate_source_bound_allocation_input(
    raw: dict[str, object],
    *,
    verified_evidence_ids: set[str] | None = None,
) -> SourceBoundAllocationInput:
    ticker = str(raw.get("ticker", "")).strip().zfill(6)
    semantic_id = str(raw.get("semantic_id", "")).strip()
    value = float(str(raw.get("value", "nan")))
    unit = str(raw.get("unit", "")).strip()
    period_start = date.fromisoformat(str(raw.get("period_start", "")))
    period_end = date.fromisoformat(str(raw.get("period_end", "")))
    evidence_id = str(raw.get("source_evidence_id", "")).strip().casefold()
    evidence_verified = bool(
        verified_evidence_ids is not None and evidence_id in verified_evidence_ids
    )
    payload: dict[str, object] = {
        "ticker": ticker,
        "semantic_id": semantic_id,
        "value": value,
        "unit": unit,
        "period_start": period_start.isoformat(),
        "period_end": period_end.isoformat(),
        "source_evidence_id": evidence_id,
        "source_evidence_verified": evidence_verified,
        "source_fact_reference": True,
        "decision_score_enabled": False,
    }
    return SourceBoundAllocationInput(
        input_id=_sha(payload),
        ticker=ticker,
        semantic_id=semantic_id,
        value=value,
        unit=unit,
        period_start=period_start,
        period_end=period_end,
        source_evidence_id=evidence_id,
        source_evidence_verified=evidence_verified,
    )


def validate_baseline_allocation_method(
    raw: dict[str, object],
    *,
    verified_evidence_ids: set[str] | None = None,
) -> BaselineAllocationMethod:
    ticker = str(raw.get("ticker", "")).strip().zfill(6)
    block_id = str(raw.get("block_id", "")).strip()
    baseline_requirement_id = str(raw.get("baseline_requirement_id", "")).strip()
    output_metric = str(raw.get("output_metric", "")).strip()
    method_id = str(raw.get("method_id", "")).strip()
    method_version = str(raw.get("method_version", "")).strip()
    method_kind = str(raw.get("method_kind", "")).strip()
    method_status = str(raw.get("method_status", "draft")).strip()
    method_version_frozen = bool(raw.get("method_version_frozen", False))
    raw_support = raw.get("supporting_evidence_ids", [])
    if not isinstance(raw_support, list):
        raise ValueError("Baseline allocation supporting_evidence_ids must be an array")
    supporting_ids = tuple(
        dict.fromkeys(str(item).strip().casefold() for item in raw_support if str(item).strip())
    )
    known = verified_evidence_ids
    supporting_verified = bool(
        known is not None and supporting_ids and set(supporting_ids).issubset(known)
    )
    rationale = str(raw.get("rationale", "")).strip()
    invalidation = str(raw.get("invalidation_condition", "")).strip()
    method_use_ready = bool(
        _ready_method_status(method_kind, method_status)
        and method_version_frozen
        and supporting_verified
        and supporting_ids
    )
    return BaselineAllocationMethod(
        method_id=method_id,
        method_version=method_version,
        ticker=ticker,
        block_id=block_id,
        baseline_requirement_id=baseline_requirement_id,
        output_metric=output_metric,
        method_kind=method_kind,
        method_status=method_status,
        method_version_frozen=method_version_frozen,
        supporting_evidence_ids=supporting_ids,
        supporting_evidence_verified=supporting_verified,
        rationale=rationale,
        invalidation_condition=invalidation,
        method_use_ready=method_use_ready,
    )


def build_direct_share_revenue_allocation(
    *,
    total_input: SourceBoundAllocationInput,
    share_input: SourceBoundAllocationInput,
    method: BaselineAllocationMethod,
) -> DerivedBaselineAllocation:
    if method.method_kind != "direct_share_allocation":
        raise ValueError("Revenue allocation requires direct_share_allocation method")
    if total_input.ticker != share_input.ticker or total_input.ticker != method.ticker:
        raise ValueError("Revenue allocation ticker identities must match")
    expected_semantic = _DIRECT_SHARE_SEMANTICS.get((method.ticker, method.block_id))
    if expected_semantic is None or share_input.semantic_id != expected_semantic:
        raise ValueError("Revenue allocation share semantic is outside the registered mapping")
    if (
        total_input.period_start != share_input.period_start
        or total_input.period_end != share_input.period_end
    ):
        raise ValueError("Revenue allocation inputs must use the same accounting period")
    if share_input.unit not in _SHARE_UNITS:
        raise ValueError("Revenue allocation share unit must be fraction or percent")
    if total_input.unit in _SHARE_UNITS:
        raise ValueError("Revenue allocation total input must be an amount, not a share")
    if share_input.unit == "fraction":
        if not 0 <= share_input.value <= 1:
            raise ValueError("Revenue allocation fraction must be between 0 and 1")
        share = share_input.value
    else:
        if not 0 <= share_input.value <= 100:
            raise ValueError("Revenue allocation percent must be between 0 and 100")
        share = share_input.value / 100.0
    value = total_input.value * share
    allocation_ready = bool(
        total_input.source_evidence_verified
        and share_input.source_evidence_verified
        and method.method_use_ready
    )
    payload: dict[str, object] = {
        "ticker": method.ticker,
        "block_id": method.block_id,
        "baseline_requirement_id": method.baseline_requirement_id,
        "output_metric": method.output_metric,
        "value": value,
        "unit": total_input.unit,
        "period_start": total_input.period_start.isoformat(),
        "period_end": total_input.period_end.isoformat(),
        "method_id": method.method_id,
        "method_version": method.method_version,
        "source_input_ids": [total_input.input_id, share_input.input_id],
        "source_evidence_ids": [
            total_input.source_evidence_id,
            share_input.source_evidence_id,
        ],
        "allocation_ready": allocation_ready,
        "source_fact": False,
        "derived_not_source_fact": True,
        "residual_derivation_used": False,
        "profitability_allocation_used": False,
        "numeric_forecast_enabled": False,
        "decision_score_enabled": False,
    }
    return DerivedBaselineAllocation(
        allocation_id=_sha(payload),
        ticker=method.ticker,
        block_id=method.block_id,
        baseline_requirement_id=method.baseline_requirement_id,
        output_metric=method.output_metric,
        value=value,
        unit=total_input.unit,
        period_start=total_input.period_start,
        period_end=total_input.period_end,
        method_id=method.method_id,
        method_version=method.method_version,
        source_input_ids=(total_input.input_id, share_input.input_id),
        source_evidence_ids=(
            total_input.source_evidence_id,
            share_input.source_evidence_id,
        ),
        allocation_ready=allocation_ready,
    )


def build_direct_amount_revenue_reference(
    *,
    amount_input: SourceBoundAllocationInput,
    method: BaselineAllocationMethod,
) -> DerivedBaselineAllocation:
    if method.method_kind != "direct_amount_reference":
        raise ValueError("Direct revenue reference requires direct_amount_reference method")
    if amount_input.ticker != method.ticker:
        raise ValueError("Direct revenue reference ticker identities must match")
    expected_semantic = _DIRECT_AMOUNT_SEMANTICS.get((method.ticker, method.block_id))
    if expected_semantic is None or amount_input.semantic_id != expected_semantic:
        raise ValueError("Direct revenue reference semantic is outside the registered mapping")
    if amount_input.unit in _SHARE_UNITS:
        raise ValueError("Direct revenue reference must use an amount unit")
    allocation_ready = bool(amount_input.source_evidence_verified and method.method_use_ready)
    payload: dict[str, object] = {
        "ticker": method.ticker,
        "block_id": method.block_id,
        "baseline_requirement_id": method.baseline_requirement_id,
        "output_metric": method.output_metric,
        "value": amount_input.value,
        "unit": amount_input.unit,
        "period_start": amount_input.period_start.isoformat(),
        "period_end": amount_input.period_end.isoformat(),
        "method_id": method.method_id,
        "method_version": method.method_version,
        "source_input_ids": [amount_input.input_id],
        "source_evidence_ids": [amount_input.source_evidence_id],
        "allocation_ready": allocation_ready,
        "source_fact": False,
        "derived_not_source_fact": True,
        "residual_derivation_used": False,
        "profitability_allocation_used": False,
        "numeric_forecast_enabled": False,
        "decision_score_enabled": False,
    }
    return DerivedBaselineAllocation(
        allocation_id=_sha(payload),
        ticker=method.ticker,
        block_id=method.block_id,
        baseline_requirement_id=method.baseline_requirement_id,
        output_metric=method.output_metric,
        value=amount_input.value,
        unit=amount_input.unit,
        period_start=amount_input.period_start,
        period_end=amount_input.period_end,
        method_id=method.method_id,
        method_version=method.method_version,
        source_input_ids=(amount_input.input_id,),
        source_evidence_ids=(amount_input.source_evidence_id,),
        allocation_ready=allocation_ready,
    )


def reconcile_company_revenue(
    *,
    ticker: str,
    allocations: tuple[DerivedBaselineAllocation, ...],
    reported_company_revenue: SourceBoundAllocationInput,
    absolute_tolerance: float = 1e-9,
) -> CompanyRevenueReconciliation:
    ticker_key = str(ticker).zfill(6)
    contract = SEMICONDUCTOR_FORWARD_MODEL_CONTRACTS.get(ticker_key)
    if contract is None:
        raise ValueError(f"Company reconciliation issuer is not registered: {ticker_key}")
    if reported_company_revenue.ticker != ticker_key:
        raise ValueError("Reported company revenue ticker does not match reconciliation issuer")
    if not math.isfinite(absolute_tolerance) or absolute_tolerance < 0:
        raise ValueError("Company revenue reconciliation tolerance must be finite/non-negative")
    required_blocks = tuple(
        block.block_id
        for block in contract.blocks
        if block.additive_to_company_financials and "revenue" in block.required_outputs
    )
    by_block: dict[str, DerivedBaselineAllocation] = {}
    for allocation in allocations:
        if allocation.ticker != ticker_key:
            raise ValueError("Company revenue reconciliation cannot mix issuers")
        block = _registered_block(ticker_key, allocation.block_id)
        if not block.additive_to_company_financials:
            raise ValueError("Company revenue reconciliation cannot add a non-additive overlay")
        if allocation.output_metric != "revenue":
            raise ValueError("Company revenue reconciliation accepts revenue allocations only")
        if allocation.block_id not in required_blocks:
            raise ValueError("Company revenue reconciliation received unexpected revenue block")
        if allocation.block_id in by_block:
            raise ValueError("Company revenue reconciliation contains duplicate revenue block")
        if (
            allocation.period_start != reported_company_revenue.period_start
            or allocation.period_end != reported_company_revenue.period_end
        ):
            raise ValueError("Company revenue reconciliation periods must match")
        if allocation.unit != reported_company_revenue.unit:
            raise ValueError("Company revenue reconciliation units must match")
        by_block[allocation.block_id] = allocation

    allocated_blocks = tuple(block_id for block_id in required_blocks if block_id in by_block)
    missing_blocks = tuple(block_id for block_id in required_blocks if block_id not in by_block)
    allocated_total = sum(by_block[block_id].value for block_id in allocated_blocks)
    delta = allocated_total - reported_company_revenue.value
    all_ready = bool(
        allocated_blocks
        and all(by_block[block_id].allocation_ready for block_id in allocated_blocks)
        and reported_company_revenue.source_evidence_verified
    )
    certified = bool(
        not missing_blocks
        and all_ready
        and abs(delta) <= absolute_tolerance
    )
    payload: dict[str, object] = {
        "ticker": ticker_key,
        "period_start": reported_company_revenue.period_start.isoformat(),
        "period_end": reported_company_revenue.period_end.isoformat(),
        "unit": reported_company_revenue.unit,
        "required_revenue_blocks": list(required_blocks),
        "allocated_revenue_blocks": list(allocated_blocks),
        "missing_revenue_blocks": list(missing_blocks),
        "allocated_revenue_total": allocated_total,
        "reported_company_revenue": reported_company_revenue.value,
        "reconciliation_delta": delta,
        "absolute_tolerance": absolute_tolerance,
        "all_allocations_ready": all_ready,
        "revenue_reconciliation_certified": certified,
        "revenue_model_input_ready": certified,
        "profitability_baseline_certified": False,
        "full_baseline_certified": False,
        "residual_derivation_enabled": False,
        "numeric_forecast_enabled": False,
        "decision_score_enabled": False,
    }
    return CompanyRevenueReconciliation(
        reconciliation_id=_sha(payload),
        ticker=ticker_key,
        period_start=reported_company_revenue.period_start,
        period_end=reported_company_revenue.period_end,
        unit=reported_company_revenue.unit,
        required_revenue_blocks=required_blocks,
        allocated_revenue_blocks=allocated_blocks,
        missing_revenue_blocks=missing_blocks,
        allocated_revenue_total=allocated_total,
        reported_company_revenue=reported_company_revenue.value,
        reconciliation_delta=delta,
        absolute_tolerance=absolute_tolerance,
        all_allocations_ready=all_ready,
        revenue_reconciliation_certified=certified,
        revenue_model_input_ready=certified,
    )


__all__ = [
    "BaselineAllocationMethod",
    "CompanyRevenueReconciliation",
    "DerivedBaselineAllocation",
    "SourceBoundAllocationInput",
    "build_direct_amount_revenue_reference",
    "build_direct_share_revenue_allocation",
    "reconcile_company_revenue",
    "validate_baseline_allocation_method",
    "validate_source_bound_allocation_input",
]
