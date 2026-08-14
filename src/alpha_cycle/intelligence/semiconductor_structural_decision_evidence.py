"""Load structural semiconductor evidence artifacts and summarize decision coverage.

The bridge remains non-scoring.  It distinguishes self-reported issuer evidence
from customer confirmation and government policy evidence.  Qualitative evidence
may improve research coverage but does not enable a numeric memory-price signal.
"""

from __future__ import annotations

import json
from collections import defaultdict
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import cast

import pandas as pd

from alpha_cycle.intelligence.semiconductor_structural_evidence import (
    SemiconductorStructuralClaim,
    SemiconductorStructuralEvidenceBundle,
    SemiconductorStructuralSource,
    build_structural_evidence_bundle,
    load_structural_source_registry,
)

DEFAULT_STRUCTURAL_REGISTRY = Path("config/semiconductor_structural_sources.yaml")
DEFAULT_STRUCTURAL_POINTER = Path(
    "data/private/live-research/semiconductor-structural-evidence/"
    "latest_semiconductor_structural_evidence.json"
)
SEMICONDUCTOR_TICKERS = ("005930", "000660")


@dataclass(frozen=True)
class SemiconductorStructuralCoverage:
    ticker: str
    hbm_demand_mix_status: str
    hbm_capacity_yield_status: str
    competitive_position_status: str
    end_demand_status: str
    memory_pricing_status: str
    export_control_status: str
    issuer_claim_count: int
    customer_claim_count: int
    peer_claim_count: int
    government_claim_count: int
    decision_score_enabled: bool = False

    def __post_init__(self) -> None:
        if len(self.ticker) != 6 or not self.ticker.isdigit():
            raise ValueError("Structural coverage ticker must be six digits")
        allowed = {"available", "partial", "missing", "blocked_numeric"}
        for value in (
            self.hbm_demand_mix_status,
            self.hbm_capacity_yield_status,
            self.competitive_position_status,
            self.end_demand_status,
            self.memory_pricing_status,
            self.export_control_status,
        ):
            if value not in allowed:
                raise ValueError(f"Unsupported structural coverage status: {value}")
        if self.decision_score_enabled:
            raise ValueError("Structural coverage must remain non-scoring")


@dataclass(frozen=True)
class SemiconductorStructuralDecisionEvidence:
    bundle: SemiconductorStructuralEvidenceBundle
    coverages: tuple[SemiconductorStructuralCoverage, ...]
    decision_score_enabled: bool = False

    def __post_init__(self) -> None:
        if not self.coverages:
            raise ValueError("Structural decision evidence requires ticker coverage")
        if self.decision_score_enabled:
            raise ValueError("Structural decision evidence must remain non-scoring")


def _json_object(path: Path, label: str) -> Mapping[str, object]:
    try:
        payload: object = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ValueError(f"{label} not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"{label} is invalid JSON: {path}") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"{label} must be a JSON object")
    return cast(Mapping[str, object], payload)


def _require_false(payload: Mapping[str, object], key: str) -> None:
    if payload.get(key) is not False:
        raise ValueError(f"Structural evidence requires {key}=false")


def _raw_claims(path: Path) -> list[dict[str, object]]:
    try:
        payload: object = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ValueError(f"Structural claims not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"Structural claims are invalid JSON: {path}") from exc
    if not isinstance(payload, list) or not payload:
        raise ValueError("Structural claims artifact must be a non-empty array")
    result: list[dict[str, object]] = []
    for value in payload:
        if not isinstance(value, dict):
            raise ValueError("Structural claims artifact row must be an object")
        raw = cast(dict[object, object], value)
        result.append(
            {
                "subject": raw.get("subject"),
                "dimension": raw.get("dimension"),
                "source_id": raw.get("source_id"),
                "source_url": raw.get("source_url"),
                "source_published_date": raw.get("source_published_date"),
                "evidence_kind": raw.get("evidence_kind"),
                "statement": raw.get("statement"),
                "numeric_value": raw.get("numeric_value"),
                "unit": raw.get("unit"),
                "product_scope": raw.get("product_scope"),
                "semantics_certified": raw.get("semantics_certified", False),
                "reuse_basis_documented": raw.get("reuse_basis_documented", False),
                "issuer_specific": raw.get("issuer_specific", False),
            }
        )
    return result


def load_structural_decision_evidence(
    pointer_path: str | Path,
    *,
    evaluation_date: date,
    registry_path: str | Path = DEFAULT_STRUCTURAL_REGISTRY,
) -> SemiconductorStructuralDecisionEvidence:
    pointer = _json_object(Path(pointer_path), "Structural evidence pointer")
    if str(pointer.get("status", "")) != "semiconductor_structural_evidence_captured":
        raise ValueError("Structural evidence pointer status is invalid")
    for key in (
        "source_bytes_archived",
        "historical_snapshot_certified",
        "numeric_memory_price_signal_enabled",
        "decision_score_enabled",
        "account_api_enabled",
        "holdings_api_enabled",
        "balance_api_enabled",
        "order_api_enabled",
    ):
        _require_false(pointer, key)
    pointer_date = date.fromisoformat(str(pointer.get("evaluation_date", "")))
    if pointer_date != evaluation_date:
        raise ValueError(
            "Structural evidence evaluation date mismatch: "
            f"evidence={pointer_date.isoformat()} decision={evaluation_date.isoformat()}"
        )
    bundle_id = str(pointer.get("bundle_id", "")).strip()
    if len(bundle_id) != 64:
        raise ValueError("Structural evidence pointer bundle_id is invalid")
    manifest_path = Path(str(pointer.get("manifest_path", "")).strip())
    claims_path = Path(str(pointer.get("claims_path", "")).strip())
    manifest = _json_object(manifest_path, "Structural evidence manifest")
    if str(manifest.get("bundle_id", "")) != bundle_id:
        raise ValueError("Structural evidence pointer/manifest bundle mismatch")
    for key in (
        "source_bytes_archived",
        "historical_snapshot_certified",
        "numeric_memory_price_signal_enabled",
        "decision_score_enabled",
        "account_api_enabled",
        "holdings_api_enabled",
        "balance_api_enabled",
        "order_api_enabled",
    ):
        _require_false(manifest, key)

    registry = load_structural_source_registry(registry_path)
    bundle = build_structural_evidence_bundle(
        _raw_claims(claims_path),
        registry,
        evaluation_date=evaluation_date,
    )
    if bundle.bundle_id != bundle_id:
        raise ValueError("Structural evidence bundle hash does not reproduce artifact bundle_id")
    return SemiconductorStructuralDecisionEvidence(
        bundle=bundle,
        coverages=build_structural_coverages(bundle, registry),
        decision_score_enabled=False,
    )


def _claims_for_ticker(
    bundle: SemiconductorStructuralEvidenceBundle,
    ticker: str,
) -> tuple[SemiconductorStructuralClaim, ...]:
    result: list[SemiconductorStructuralClaim] = []
    for claim in bundle.claims:
        if claim.issuer_specific:
            if claim.subject == ticker:
                result.append(claim)
        else:
            result.append(claim)
    return tuple(result)


def _role_counts(
    claims: tuple[SemiconductorStructuralClaim, ...],
    registry: dict[str, SemiconductorStructuralSource],
) -> dict[str, int]:
    counts: defaultdict[str, int] = defaultdict(int)
    for claim in claims:
        counts[registry[claim.source_id].role] += 1
    return dict(counts)


def _has(
    claims: tuple[SemiconductorStructuralClaim, ...],
    registry: dict[str, SemiconductorStructuralSource],
    *,
    dimension: str,
    roles: set[str] | None = None,
    issuer_specific: bool | None = None,
) -> bool:
    for claim in claims:
        if claim.dimension != dimension:
            continue
        if roles is not None and registry[claim.source_id].role not in roles:
            continue
        if issuer_specific is not None and claim.issuer_specific is not issuer_specific:
            continue
        return True
    return False


def build_structural_coverages(
    bundle: SemiconductorStructuralEvidenceBundle,
    registry: dict[str, SemiconductorStructuralSource],
) -> tuple[SemiconductorStructuralCoverage, ...]:
    coverages: list[SemiconductorStructuralCoverage] = []
    for ticker in SEMICONDUCTOR_TICKERS:
        claims = _claims_for_ticker(bundle, ticker)
        counts = _role_counts(claims, registry)
        issuer_hbm = _has(
            claims,
            registry,
            dimension="hbm_demand_mix",
            roles={"issuer_ir"},
            issuer_specific=True,
        )
        customer_hbm = _has(
            claims,
            registry,
            dimension="hbm_demand_mix",
            roles={"customer_ir"},
        ) or _has(
            claims,
            registry,
            dimension="qualification",
            roles={"customer_ir"},
            issuer_specific=True,
        )
        hbm_demand_status = (
            "available" if issuer_hbm and customer_hbm else "partial" if issuer_hbm or customer_hbm else "missing"
        )

        hbm_capacity = _has(
            claims,
            registry,
            dimension="hbm_capacity_yield",
            roles={"issuer_ir"},
            issuer_specific=True,
        )
        hbm_capacity_status = "partial" if hbm_capacity else "missing"

        issuer_competition = _has(
            claims,
            registry,
            dimension="competitive_position",
            roles={"issuer_ir"},
            issuer_specific=True,
        )
        customer_qualification = _has(
            claims,
            registry,
            dimension="qualification",
            roles={"customer_ir"},
            issuer_specific=True,
        )
        competition_status = (
            "available"
            if issuer_competition and customer_qualification
            else "partial"
            if issuer_competition or customer_qualification
            else "missing"
        )

        end_demand = _has(
            claims,
            registry,
            dimension="end_demand",
            roles={"customer_ir", "peer_ir"},
        )
        end_demand_status = "partial" if end_demand else "missing"

        pricing_direction = _has(
            claims,
            registry,
            dimension="memory_pricing_direction",
            roles={"issuer_ir", "peer_ir"},
        )
        numeric_price = _has(
            claims,
            registry,
            dimension="memory_numeric_price",
            roles={"certified_price_data"},
        )
        pricing_status = (
            "blocked_numeric" if numeric_price else "partial" if pricing_direction else "missing"
        )

        export_control = _has(
            claims,
            registry,
            dimension="export_control",
            roles={"government_regulation"},
        )
        coverages.append(
            SemiconductorStructuralCoverage(
                ticker=ticker,
                hbm_demand_mix_status=hbm_demand_status,
                hbm_capacity_yield_status=hbm_capacity_status,
                competitive_position_status=competition_status,
                end_demand_status=end_demand_status,
                memory_pricing_status=pricing_status,
                export_control_status="available" if export_control else "missing",
                issuer_claim_count=counts.get("issuer_ir", 0),
                customer_claim_count=counts.get("customer_ir", 0),
                peer_claim_count=counts.get("peer_ir", 0),
                government_claim_count=counts.get("government_regulation", 0),
                decision_score_enabled=False,
            )
        )
    return tuple(coverages)


def structural_coverage_frame(
    evidence: SemiconductorStructuralDecisionEvidence,
) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "ticker": coverage.ticker,
                "structural_bundle_id": evidence.bundle.bundle_id,
                "structural_hbm_demand_mix_status": coverage.hbm_demand_mix_status,
                "structural_hbm_capacity_yield_status": coverage.hbm_capacity_yield_status,
                "structural_competitive_position_status": coverage.competitive_position_status,
                "structural_end_demand_status": coverage.end_demand_status,
                "structural_memory_pricing_status": coverage.memory_pricing_status,
                "structural_export_control_status": coverage.export_control_status,
                "structural_issuer_claim_count": coverage.issuer_claim_count,
                "structural_customer_claim_count": coverage.customer_claim_count,
                "structural_peer_claim_count": coverage.peer_claim_count,
                "structural_government_claim_count": coverage.government_claim_count,
                "structural_numeric_memory_price_signal_enabled": False,
                "structural_decision_score_enabled": False,
            }
            for coverage in evidence.coverages
        ]
    )


def append_structural_evidence_report(
    report: str,
    evidence: SemiconductorStructuralDecisionEvidence,
) -> str:
    lines = [
        report.rstrip(),
        "",
        "## 반도체 structural primary-source evidence (비점수)",
        "",
        f"- bundle: `{evidence.bundle.bundle_id[:12]}` / evaluation `{evidence.bundle.evaluation_date.isoformat()}`",
        "- issuer 자기주장과 customer confirmation을 구분하며, 없는 evidence는 채워 넣지 않습니다.",
        "- qualitative pricing commentary는 numeric DRAM/NAND/HBM price signal로 승격하지 않습니다.",
        "- source bytes가 아직 archive되지 않아 historical snapshot certification은 비활성입니다.",
        "",
        "| 종목 | HBM 수요/믹스 | HBM 캐파/수율 | 경쟁포지션 | 최종수요 | 메모리가격 | 수출규제 | issuer/customer/peer/gov claims |",
        "|---|---|---|---|---|---|---|---:|",
    ]
    for coverage in evidence.coverages:
        lines.append(
            f"| {coverage.ticker} | {coverage.hbm_demand_mix_status} | "
            f"{coverage.hbm_capacity_yield_status} | {coverage.competitive_position_status} | "
            f"{coverage.end_demand_status} | {coverage.memory_pricing_status} | "
            f"{coverage.export_control_status} | {coverage.issuer_claim_count}/"
            f"{coverage.customer_claim_count}/{coverage.peer_claim_count}/"
            f"{coverage.government_claim_count} |"
        )
    lines.extend(["", "### Captured claims", ""])
    for claim in evidence.bundle.claims:
        lines.append(
            f"- `{claim.dimension}` / `{claim.source_id}` / `{claim.subject}` / "
            f"{claim.source_published_date.isoformat()}: {claim.statement}"
        )
    return "\n".join(lines).rstrip() + "\n"


__all__ = [
    "DEFAULT_STRUCTURAL_POINTER",
    "DEFAULT_STRUCTURAL_REGISTRY",
    "SemiconductorStructuralCoverage",
    "SemiconductorStructuralDecisionEvidence",
    "append_structural_evidence_report",
    "build_structural_coverages",
    "load_structural_decision_evidence",
    "structural_coverage_frame",
]
