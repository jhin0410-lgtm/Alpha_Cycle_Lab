"""Archived decision evidence for source-separated semiconductor revenue allocation.

V1 deliberately has no production source resolver.  A source-specific resolver must first
prove the numeric inputs from an independently verified upstream artifact.  Persisted
"verified" booleans are never enough to activate this layer.
"""

from __future__ import annotations

import hashlib
import json
import shutil
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from typing import cast

from alpha_cycle.intelligence.semiconductor_baseline_allocation import (
    BaselineAllocationMethod,
    CompanyRevenueReconciliation,
    DerivedBaselineAllocation,
    SourceBoundAllocationInput,
    build_direct_share_revenue_allocation,
    reconcile_company_revenue,
    validate_baseline_allocation_method,
)

DEFAULT_BASELINE_ALLOCATION_OUTPUT = Path(
    "data/private/live-research/semiconductor-baseline-allocation"
)
DEFAULT_BASELINE_ALLOCATION_POINTER = (
    DEFAULT_BASELINE_ALLOCATION_OUTPUT / "latest_semiconductor_baseline_allocation.json"
)
SK_HYNIX_TICKER = "000660"
_REQUIRED_SEMANTICS = (
    "reported_company_revenue",
    "dram_revenue_share",
    "nand_revenue_share",
)
_REQUIRED_FALSE_FLAGS = (
    "source_fact",
    "residual_derivation_enabled",
    "profitability_allocation_enabled",
    "profitability_baseline_certified",
    "full_baseline_certified",
    "numeric_forecast_enabled",
    "decision_score_enabled",
    "fair_value_estimate_enabled",
    "target_price_enabled",
    "account_api_enabled",
    "holdings_api_enabled",
    "balance_api_enabled",
    "order_api_enabled",
)


def _sha(payload: object) -> str:
    return hashlib.sha256(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode(
            "utf-8"
        )
    ).hexdigest()


def _valid_sha(value: str) -> bool:
    return len(value) == 64 and all(char in "0123456789abcdef" for char in value)


@dataclass(frozen=True)
class VerifiedAllocationSourceBundle:
    """Inputs produced by a source-specific resolver, not by persisted trust flags."""

    resolver_id: str
    ticker: str
    evaluation_date: date
    source_reference_id: str
    inputs: tuple[SourceBoundAllocationInput, ...]

    def __post_init__(self) -> None:
        if not self.resolver_id.strip() or self.ticker != SK_HYNIX_TICKER:
            raise ValueError("Allocation source bundle identity is invalid")
        if not _valid_sha(self.source_reference_id):
            raise ValueError("Allocation source reference must be SHA-256")
        by_semantic = {item.semantic_id: item for item in self.inputs}
        if tuple(sorted(by_semantic)) != tuple(sorted(_REQUIRED_SEMANTICS)):
            raise ValueError("Allocation source bundle must contain exact SK hynix v1 semantics")
        if len(by_semantic) != len(self.inputs):
            raise ValueError("Allocation source bundle contains duplicate semantics")
        if any(item.ticker != self.ticker for item in self.inputs):
            raise ValueError("Allocation source bundle cannot mix issuers")
        if any(not item.source_evidence_verified for item in self.inputs):
            raise ValueError("Allocation source bundle requires independently verified inputs")
        periods = {(item.period_start, item.period_end) for item in self.inputs}
        if len(periods) != 1:
            raise ValueError("Allocation source bundle inputs must share one accounting period")


AllocationSourceResolver = Callable[[str | Path, date], VerifiedAllocationSourceBundle]
# Intentionally empty. Activating 000660 requires a separate source-specific resolver PR
# after exact official SK hynix 2Q26 source bytes/URL and numeric share semantics are verified.
ALLOCATION_SOURCE_RESOLVERS: dict[str, AllocationSourceResolver] = {}


@dataclass(frozen=True)
class SemiconductorBaselineAllocationEvidence:
    evidence_id: str
    resolver_id: str
    source_reference_id: str
    evaluation_date: date
    reconciliation: CompanyRevenueReconciliation
    allocations: tuple[DerivedBaselineAllocation, ...]
    source_fact: bool = False
    residual_derivation_enabled: bool = False
    profitability_allocation_enabled: bool = False
    profitability_baseline_certified: bool = False
    full_baseline_certified: bool = False
    numeric_forecast_enabled: bool = False
    decision_score_enabled: bool = False

    def __post_init__(self) -> None:
        if not _valid_sha(self.evidence_id) or not _valid_sha(self.source_reference_id):
            raise ValueError("Baseline allocation evidence IDs must be SHA-256")
        if self.reconciliation.ticker != SK_HYNIX_TICKER:
            raise ValueError("Baseline allocation evidence v1 supports SK hynix only")
        if not self.allocations:
            raise ValueError("Baseline allocation evidence requires derived allocations")
        if self.source_fact:
            raise ValueError("Derived baseline allocation evidence cannot be a source fact")
        if (
            self.residual_derivation_enabled
            or self.profitability_allocation_enabled
            or self.profitability_baseline_certified
            or self.full_baseline_certified
            or self.numeric_forecast_enabled
            or self.decision_score_enabled
        ):
            raise ValueError("Revenue allocation evidence cannot widen model/scoring gates")


def _method_raw(
    *,
    block_id: str,
    baseline_requirement_id: str,
    method_id: str,
    supporting_evidence_ids: tuple[str, ...],
) -> dict[str, object]:
    return {
        "ticker": SK_HYNIX_TICKER,
        "block_id": block_id,
        "baseline_requirement_id": baseline_requirement_id,
        "output_metric": "revenue",
        "method_id": method_id,
        "method_version": "1.0",
        "method_kind": "direct_share_allocation",
        "method_status": "observationally_calibrated",
        "method_version_frozen": True,
        "supporting_evidence_ids": list(supporting_evidence_ids),
        "rationale": (
            "Allocate directly reported company revenue using a directly evidenced "
            "issuer product-revenue share; no residual or profitability arithmetic."
        ),
        "invalidation_condition": (
            "Invalidate if the issuer share definition, accounting scope, period, or "
            "source semantics change."
        ),
    }


def build_skhynix_revenue_allocation_evidence(
    source_reference: str | Path,
    *,
    evaluation_date: date,
    resolver_id: str,
    resolvers: Mapping[str, AllocationSourceResolver] | None = None,
) -> SemiconductorBaselineAllocationEvidence:
    resolver_map = ALLOCATION_SOURCE_RESOLVERS if resolvers is None else resolvers
    resolver = resolver_map.get(resolver_id)
    if resolver is None:
        raise ValueError(
            f"Baseline allocation source resolver is not registered: {resolver_id}"
        )
    bundle = resolver(source_reference, evaluation_date)
    if bundle.resolver_id != resolver_id or bundle.evaluation_date != evaluation_date:
        raise ValueError("Baseline allocation source resolver identity/date mismatch")
    by_semantic = {item.semantic_id: item for item in bundle.inputs}
    company = by_semantic["reported_company_revenue"]
    dram_share = by_semantic["dram_revenue_share"]
    nand_share = by_semantic["nand_revenue_share"]
    verified_ids = {item.source_evidence_id for item in bundle.inputs}

    dram_method: BaselineAllocationMethod = validate_baseline_allocation_method(
        _method_raw(
            block_id="dram_total",
            baseline_requirement_id="dram_revenue_or_company_memory_bridge",
            method_id="skhynix_dram_direct_share_v1",
            supporting_evidence_ids=(company.source_evidence_id, dram_share.source_evidence_id),
        ),
        verified_evidence_ids=verified_ids,
    )
    nand_method: BaselineAllocationMethod = validate_baseline_allocation_method(
        _method_raw(
            block_id="nand_and_solutions",
            baseline_requirement_id="nand_solution_revenue_bridge",
            method_id="skhynix_nand_direct_share_v1",
            supporting_evidence_ids=(company.source_evidence_id, nand_share.source_evidence_id),
        ),
        verified_evidence_ids=verified_ids,
    )
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
    )
    reconciliation = reconcile_company_revenue(
        ticker=SK_HYNIX_TICKER,
        allocations=allocations,
        reported_company_revenue=company,
    )
    payload = {
        "resolver_id": resolver_id,
        "source_reference_id": bundle.source_reference_id,
        "evaluation_date": evaluation_date.isoformat(),
        "input_ids": [item.input_id for item in bundle.inputs],
        "allocation_ids": [item.allocation_id for item in allocations],
        "reconciliation_id": reconciliation.reconciliation_id,
        "source_fact": False,
        "residual_derivation_enabled": False,
        "profitability_allocation_enabled": False,
        "profitability_baseline_certified": False,
        "full_baseline_certified": False,
        "numeric_forecast_enabled": False,
        "decision_score_enabled": False,
    }
    return SemiconductorBaselineAllocationEvidence(
        evidence_id=_sha(payload),
        resolver_id=resolver_id,
        source_reference_id=bundle.source_reference_id,
        evaluation_date=evaluation_date,
        reconciliation=reconciliation,
        allocations=allocations,
    )


def _allocation_payload(
    evidence: SemiconductorBaselineAllocationEvidence,
) -> dict[str, object]:
    item = evidence.reconciliation
    return {
        "evidence_id": evidence.evidence_id,
        "resolver_id": evidence.resolver_id,
        "source_reference_id": evidence.source_reference_id,
        "evaluation_date": evidence.evaluation_date.isoformat(),
        "ticker": item.ticker,
        "period_start": item.period_start.isoformat(),
        "period_end": item.period_end.isoformat(),
        "unit": item.unit,
        "required_revenue_blocks": list(item.required_revenue_blocks),
        "allocated_revenue_blocks": list(item.allocated_revenue_blocks),
        "missing_revenue_blocks": list(item.missing_revenue_blocks),
        "allocated_revenue_total": item.allocated_revenue_total,
        "reported_company_revenue": item.reported_company_revenue,
        "reconciliation_delta": item.reconciliation_delta,
        "absolute_tolerance": item.absolute_tolerance,
        "all_allocations_ready": item.all_allocations_ready,
        "revenue_reconciliation_certified": item.revenue_reconciliation_certified,
        "revenue_model_input_ready": item.revenue_model_input_ready,
        "allocation_ids": [allocation.allocation_id for allocation in evidence.allocations],
        "source_fact": False,
        "residual_derivation_enabled": False,
        "profitability_allocation_enabled": False,
        "profitability_baseline_certified": False,
        "full_baseline_certified": False,
        "numeric_forecast_enabled": False,
        "decision_score_enabled": False,
        "fair_value_estimate_enabled": False,
        "target_price_enabled": False,
        "account_api_enabled": False,
        "holdings_api_enabled": False,
        "balance_api_enabled": False,
        "order_api_enabled": False,
    }


def capture_semiconductor_baseline_allocation(
    source_reference: str | Path,
    *,
    evaluation_date: date,
    resolver_id: str,
    output: str | Path = DEFAULT_BASELINE_ALLOCATION_OUTPUT,
    captured_at: datetime | None = None,
    resolvers: Mapping[str, AllocationSourceResolver] | None = None,
) -> dict[str, object]:
    evidence = build_skhynix_revenue_allocation_evidence(
        source_reference,
        evaluation_date=evaluation_date,
        resolver_id=resolver_id,
        resolvers=resolvers,
    )
    captured = captured_at or datetime.now(UTC)
    if captured.tzinfo is None or captured.utcoffset() is None:
        raise ValueError("captured_at must be timezone-aware")
    root = Path(output)
    root.mkdir(parents=True, exist_ok=True)
    directory = root / (
        captured.astimezone(UTC).strftime("%Y%m%dT%H%M%S%fZ")
        + "__"
        + evidence.evidence_id[:12]
    )
    if directory.exists():
        raise ValueError(f"Baseline allocation artifact already exists: {directory}")
    temporary = root / f".{directory.name}.tmp"
    if temporary.exists():
        shutil.rmtree(temporary)
    temporary.mkdir()
    try:
        payload = _allocation_payload(evidence)
        (temporary / "baseline_allocation.json").write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        manifest = {
            **payload,
            "schema_version": 1,
            "status": "semiconductor_baseline_allocation_captured",
            "captured_at": captured.isoformat(),
            "source_reference_path": str(Path(source_reference).resolve()),
            "files": ["baseline_allocation.json"],
        }
        (temporary / "manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        temporary.rename(directory)
    except Exception:
        if temporary.exists():
            shutil.rmtree(temporary)
        raise

    pointer = {
        **_allocation_payload(evidence),
        "schema_version": 1,
        "status": "semiconductor_baseline_allocation_captured",
        "manifest_path": str((directory / "manifest.json").resolve()),
        "baseline_allocation_path": str(
            (directory / "baseline_allocation.json").resolve()
        ),
    }
    pointer_path = root / "latest_semiconductor_baseline_allocation.json"
    temporary_pointer = root / ".latest_semiconductor_baseline_allocation.json.tmp"
    temporary_pointer.write_text(
        json.dumps(pointer, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    temporary_pointer.replace(pointer_path)
    return {**pointer, "artifact_directory": str(directory.resolve())}


def _json_object(path: Path, label: str) -> dict[str, object]:
    try:
        raw: object = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ValueError(f"{label} not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"{label} is invalid JSON: {path}") from exc
    if not isinstance(raw, dict):
        raise ValueError(f"{label} must be a JSON object")
    return {str(key): value for key, value in cast(dict[object, object], raw).items()}


def _require_false_flags(payload: dict[str, object]) -> None:
    for flag in _REQUIRED_FALSE_FLAGS:
        if payload.get(flag) is not False:
            raise ValueError(f"Baseline allocation artifact requires {flag}=false")


def load_semiconductor_baseline_allocation_evidence(
    pointer_path: str | Path,
    *,
    evaluation_date: date,
    resolvers: Mapping[str, AllocationSourceResolver] | None = None,
) -> SemiconductorBaselineAllocationEvidence:
    pointer = _json_object(Path(pointer_path), "Baseline allocation pointer")
    if pointer.get("status") != "semiconductor_baseline_allocation_captured":
        raise ValueError("Baseline allocation pointer status is invalid")
    _require_false_flags(pointer)
    if date.fromisoformat(str(pointer.get("evaluation_date", ""))) != evaluation_date:
        raise ValueError("Baseline allocation evaluation date mismatch")
    if str(pointer.get("ticker", "")).zfill(6) != SK_HYNIX_TICKER:
        raise ValueError("Baseline allocation v1 supports SK hynix only")
    manifest = _json_object(
        Path(str(pointer.get("manifest_path", ""))),
        "Baseline allocation manifest",
    )
    _require_false_flags(manifest)
    evidence_id = str(pointer.get("evidence_id", ""))
    if not _valid_sha(evidence_id) or evidence_id != str(manifest.get("evidence_id", "")):
        raise ValueError("Baseline allocation pointer/manifest evidence mismatch")
    resolver_id = str(manifest.get("resolver_id", ""))
    source_reference = Path(str(manifest.get("source_reference_path", "")))
    reconstructed = build_skhynix_revenue_allocation_evidence(
        source_reference,
        evaluation_date=evaluation_date,
        resolver_id=resolver_id,
        resolvers=resolvers,
    )
    if reconstructed.evidence_id != evidence_id:
        raise ValueError("Baseline allocation evidence does not reproduce from source resolver")
    payload = _json_object(
        Path(str(pointer.get("baseline_allocation_path", ""))),
        "Baseline allocation payload",
    )
    _require_false_flags(payload)
    expected = _allocation_payload(reconstructed)
    for key, value in expected.items():
        if payload.get(key) != value or pointer.get(key) != value:
            raise ValueError(f"Baseline allocation persisted field mismatch: {key}")
    return reconstructed


__all__ = [
    "ALLOCATION_SOURCE_RESOLVERS",
    "AllocationSourceResolver",
    "DEFAULT_BASELINE_ALLOCATION_OUTPUT",
    "DEFAULT_BASELINE_ALLOCATION_POINTER",
    "SK_HYNIX_TICKER",
    "SemiconductorBaselineAllocationEvidence",
    "VerifiedAllocationSourceBundle",
    "build_skhynix_revenue_allocation_evidence",
    "capture_semiconductor_baseline_allocation",
    "load_semiconductor_baseline_allocation_evidence",
]
