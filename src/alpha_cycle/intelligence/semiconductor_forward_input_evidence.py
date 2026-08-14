"""Source-bounded forward-input evidence for issuer-specific semiconductor models.

This layer records which baseline metrics and forward drivers are supported for each
issuer model block. Source identity is never caller-declared: every claim must bind
to the existing semiconductor structural-source registry, which fixes role, domain,
and primary-source status. Qualitative evidence may improve descriptive coverage but
cannot become a numeric model input.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from urllib.parse import urlparse

import pandas as pd

from alpha_cycle.intelligence.semiconductor_forward_operating_model_contract import (
    SEMICONDUCTOR_FORWARD_MODEL_CONTRACTS,
    ForwardModelBlock,
)
from alpha_cycle.intelligence.semiconductor_structural_evidence import (
    SemiconductorStructuralSource,
    load_structural_source_registry,
)

DEFAULT_FORWARD_INPUT_SOURCE_REGISTRY = Path("config/semiconductor_structural_sources.yaml")
_ALLOWED_CLAIM_TYPES = frozenset({"baseline", "forward_driver"})
_ALLOWED_KINDS = frozenset({"qualitative", "numeric"})
_DIRECT_FORWARD_SOURCE_ROLES = frozenset({"issuer_ir", "peer_ir", "customer_ir"})
_ISSUER_SOURCE_IDS = {"000660": "sk_hynix_ir", "005930": "samsung_ir"}
_PEER_MEMORY_DRIVER_METRICS = frozenset(
    {
        "dram_bit_shipment_growth",
        "dram_asp_change",
        "dram_product_mix",
        "hbm_volume_growth",
        "hbm_generation_mix",
        "hbm_capacity",
        "hbm_yield",
        "advanced_packaging_capacity",
        "nand_bit_shipment_growth",
        "nand_asp_change",
        "enterprise_ssd_mix",
        "inventory",
    }
)
_CUSTOMER_DRIVER_METRICS = frozenset({"hbm_volume_growth", "customer_qualification"})


@dataclass(frozen=True)
class SemiconductorForwardInputClaim:
    claim_id: str
    ticker: str
    block_id: str
    claim_type: str
    metric_id: str
    evidence_kind: str
    statement: str
    numeric_value: float | None
    unit: str | None
    period_start: date | None
    period_end: date | None
    source_id: str
    source_role: str
    source_url: str
    source_published_date: date
    evaluation_date: date
    semantics_certified: bool
    source_vintage_certified: bool
    reuse_or_license_basis_documented: bool
    primary_source: bool
    numeric_model_input_eligible: bool
    decision_score_enabled: bool = False

    def __post_init__(self) -> None:
        if len(self.claim_id) != 64 or any(
            char not in "0123456789abcdef" for char in self.claim_id
        ):
            raise ValueError("Forward-input claim_id must be SHA-256")
        if self.ticker not in SEMICONDUCTOR_FORWARD_MODEL_CONTRACTS:
            raise ValueError(f"Forward-input issuer contract not registered: {self.ticker}")
        if self.claim_type not in _ALLOWED_CLAIM_TYPES:
            raise ValueError("Forward-input claim_type is invalid")
        if self.evidence_kind not in _ALLOWED_KINDS:
            raise ValueError("Forward-input evidence_kind is invalid")
        if not self.source_id.strip() or not self.source_role.strip():
            raise ValueError("Forward-input source identity cannot be blank")
        if not self.statement.strip() or not self.metric_id.strip():
            raise ValueError("Forward-input metric/statement cannot be blank")
        if not self.source_url.startswith("https://") or not urlparse(self.source_url).hostname:
            raise ValueError("Forward-input source_url must be a valid HTTPS URL")
        if self.source_published_date > self.evaluation_date:
            raise ValueError("Forward-input source cannot be published after evaluation date")
        if self.period_start and self.period_end and self.period_start > self.period_end:
            raise ValueError("Forward-input period_start cannot be after period_end")
        if self.evidence_kind == "numeric":
            if self.numeric_value is None or not self.unit:
                raise ValueError("Numeric forward-input evidence requires value and unit")
        elif self.numeric_value is not None:
            raise ValueError("Qualitative forward-input evidence cannot publish numeric_value")
        if self.numeric_model_input_eligible and self.evidence_kind != "numeric":
            raise ValueError("Only numeric evidence may be a numeric model input")
        if self.decision_score_enabled:
            raise ValueError("Forward-input evidence must remain non-scoring")


@dataclass(frozen=True)
class SemiconductorForwardInputEvidence:
    evidence_id: str
    evaluation_date: date
    claims: tuple[SemiconductorForwardInputClaim, ...]
    block_coverage: pd.DataFrame
    issuer_coverage: pd.DataFrame
    numeric_forecast_enabled: bool = False
    decision_score_enabled: bool = False

    def __post_init__(self) -> None:
        if len(self.evidence_id) != 64 or any(
            char not in "0123456789abcdef" for char in self.evidence_id
        ):
            raise ValueError("Forward-input evidence_id must be SHA-256")
        if not self.claims or self.block_coverage.empty or self.issuer_coverage.empty:
            raise ValueError("Forward-input evidence requires claims and coverage")
        if self.numeric_forecast_enabled or self.decision_score_enabled:
            raise ValueError("Forward-input evidence cannot itself enable forecasts or scoring")


def _claim_id(payload: dict[str, object]) -> str:
    return hashlib.sha256(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode(
            "utf-8"
        )
    ).hexdigest()


def _date_or_none(value: object) -> date | None:
    text = str(value or "").strip()
    return date.fromisoformat(text) if text else None


def _block_contract(ticker: str, block_id: str) -> ForwardModelBlock:
    contract = SEMICONDUCTOR_FORWARD_MODEL_CONTRACTS[ticker]
    for block in contract.blocks:
        if block.block_id == block_id:
            return block
    raise ValueError(f"Forward-input block is not registered: {ticker}/{block_id}")


def _host_allowed(source: SemiconductorStructuralSource, url: str) -> bool:
    host = (urlparse(url).hostname or "").casefold()
    return bool(host) and any(
        host == domain or host.endswith("." + domain) for domain in source.domains
    )


def _validate_source_metric_scope(
    *,
    ticker: str,
    claim_type: str,
    metric_id: str,
    source: SemiconductorStructuralSource,
) -> None:
    if source.role not in _DIRECT_FORWARD_SOURCE_ROLES:
        raise ValueError(
            f"Source role cannot directly support issuer forward-input claims: {source.role}"
        )
    if source.role == "issuer_ir":
        if source.source_id != _ISSUER_SOURCE_IDS[ticker]:
            raise ValueError(
                f"Issuer IR source does not belong to ticker {ticker}: {source.source_id}"
            )
        return
    if claim_type != "forward_driver":
        raise ValueError("Peer/customer IR cannot support issuer baseline metrics")
    if source.role == "peer_ir" and metric_id not in _PEER_MEMORY_DRIVER_METRICS:
        raise ValueError(f"Peer IR cannot support forward metric {metric_id}")
    if source.role == "customer_ir" and metric_id not in _CUSTOMER_DRIVER_METRICS:
        raise ValueError(f"Customer IR cannot support forward metric {metric_id}")


def _numeric_model_input_eligible(
    *,
    ticker: str,
    claim_type: str,
    kind: str,
    period_end: date | None,
    source: SemiconductorStructuralSource,
    semantics_certified: bool,
    source_vintage_certified: bool,
    evaluation_date: date,
) -> bool:
    if kind != "numeric" or source.source_id != _ISSUER_SOURCE_IDS[ticker]:
        return False
    if not semantics_certified or not source_vintage_certified or period_end is None:
        return False
    if claim_type == "baseline":
        return period_end <= evaluation_date
    return period_end > evaluation_date


def validate_forward_input_claim(
    raw: dict[str, object],
    registry: dict[str, SemiconductorStructuralSource],
    *,
    evaluation_date: date,
) -> SemiconductorForwardInputClaim:
    ticker = str(raw.get("ticker", "")).strip().zfill(6)
    if ticker not in SEMICONDUCTOR_FORWARD_MODEL_CONTRACTS:
        raise ValueError(f"Forward-input issuer contract not registered: {ticker}")
    block_id = str(raw.get("block_id", "")).strip()
    block = _block_contract(ticker, block_id)
    claim_type = str(raw.get("claim_type", "")).strip()
    metric_id = str(raw.get("metric_id", "")).strip()
    if claim_type == "baseline":
        allowed = set(block.required_baseline_metrics)
    elif claim_type == "forward_driver":
        allowed = set(block.required_forward_drivers)
    else:
        raise ValueError("Forward-input claim_type is invalid")
    if metric_id not in allowed:
        raise ValueError(
            f"Forward-input metric is outside issuer block contract: {ticker}/{block_id}/{metric_id}"
        )

    source_id = str(raw.get("source_id", "")).strip()
    if source_id not in registry:
        raise ValueError(f"Unknown forward-input source_id: {source_id}")
    source = registry[source_id]
    source_url = str(raw.get("source_url", "")).strip()
    if not source_url.startswith("https://") or not _host_allowed(source, source_url):
        raise ValueError(f"Forward-input source URL is outside registered domains: {source_id}")
    _validate_source_metric_scope(
        ticker=ticker,
        claim_type=claim_type,
        metric_id=metric_id,
        source=source,
    )

    kind = str(raw.get("evidence_kind", "qualitative")).strip()
    if kind not in _ALLOWED_KINDS:
        raise ValueError("Forward-input evidence_kind is invalid")
    numeric_raw = raw.get("numeric_value")
    numeric_value = None if numeric_raw is None else float(str(numeric_raw))
    unit = str(raw.get("unit", "")).strip() or None
    published = date.fromisoformat(str(raw.get("source_published_date", "")))
    period_start = _date_or_none(raw.get("period_start"))
    period_end = _date_or_none(raw.get("period_end"))
    semantics_certified = bool(raw.get("semantics_certified", False))
    source_vintage_certified = bool(raw.get("source_vintage_certified", False))
    reuse_documented = bool(raw.get("reuse_or_license_basis_documented", False))
    if kind == "numeric" and (numeric_value is None or not unit):
        raise ValueError("Numeric forward-input evidence requires value and unit")
    if kind == "numeric" and not source.primary_source and not reuse_documented:
        raise ValueError(
            "Non-primary numeric forward-input evidence requires documented reuse/license basis"
        )
    if kind == "qualitative" and numeric_value is not None:
        raise ValueError("Qualitative forward-input evidence cannot publish numeric_value")

    model_input_eligible = _numeric_model_input_eligible(
        ticker=ticker,
        claim_type=claim_type,
        kind=kind,
        period_end=period_end,
        source=source,
        semantics_certified=semantics_certified,
        source_vintage_certified=source_vintage_certified,
        evaluation_date=evaluation_date,
    )

    payload: dict[str, object] = {
        "ticker": ticker,
        "block_id": block_id,
        "claim_type": claim_type,
        "metric_id": metric_id,
        "evidence_kind": kind,
        "statement": str(raw.get("statement", "")).strip(),
        "numeric_value": numeric_value,
        "unit": unit,
        "period_start": period_start.isoformat() if period_start else None,
        "period_end": period_end.isoformat() if period_end else None,
        "source_id": source.source_id,
        "source_role": source.role,
        "source_url": source_url,
        "source_published_date": published.isoformat(),
        "evaluation_date": evaluation_date.isoformat(),
        "semantics_certified": semantics_certified,
        "source_vintage_certified": source_vintage_certified,
        "reuse_or_license_basis_documented": reuse_documented,
        "primary_source": source.primary_source,
        "numeric_model_input_eligible": model_input_eligible,
        "decision_score_enabled": False,
    }
    return SemiconductorForwardInputClaim(
        claim_id=_claim_id(payload),
        ticker=ticker,
        block_id=block_id,
        claim_type=claim_type,
        metric_id=metric_id,
        evidence_kind=kind,
        statement=str(payload["statement"]),
        numeric_value=numeric_value,
        unit=unit,
        period_start=period_start,
        period_end=period_end,
        source_id=source.source_id,
        source_role=source.role,
        source_url=source_url,
        source_published_date=published,
        evaluation_date=evaluation_date,
        semantics_certified=semantics_certified,
        source_vintage_certified=source_vintage_certified,
        reuse_or_license_basis_documented=reuse_documented,
        primary_source=source.primary_source,
        numeric_model_input_eligible=model_input_eligible,
        decision_score_enabled=False,
    )


def _coverage(
    claims: tuple[SemiconductorForwardInputClaim, ...],
) -> tuple[pd.DataFrame, pd.DataFrame]:
    block_rows: list[dict[str, object]] = []
    for ticker, contract in SEMICONDUCTOR_FORWARD_MODEL_CONTRACTS.items():
        ticker_claims = [claim for claim in claims if claim.ticker == ticker]
        for block in contract.blocks:
            block_claims = [claim for claim in ticker_claims if claim.block_id == block.block_id]
            baseline_seen = {
                claim.metric_id for claim in block_claims if claim.claim_type == "baseline"
            }
            driver_seen = {
                claim.metric_id for claim in block_claims if claim.claim_type == "forward_driver"
            }
            numeric_baseline_seen = {
                claim.metric_id
                for claim in block_claims
                if claim.claim_type == "baseline" and claim.numeric_model_input_eligible
            }
            numeric_driver_seen = {
                claim.metric_id
                for claim in block_claims
                if claim.claim_type == "forward_driver" and claim.numeric_model_input_eligible
            }
            required_baselines = set(block.required_baseline_metrics)
            required_drivers = set(block.required_forward_drivers)
            descriptive_baseline_complete = required_baselines.issubset(baseline_seen)
            descriptive_driver_complete = required_drivers.issubset(driver_seen)
            numeric_baseline_complete = required_baselines.issubset(numeric_baseline_seen)
            numeric_driver_complete = required_drivers.issubset(numeric_driver_seen)
            block_rows.append(
                {
                    "ticker": ticker,
                    "block_id": block.block_id,
                    "required_baseline_count": len(required_baselines),
                    "covered_baseline_count": len(required_baselines & baseline_seen),
                    "numeric_baseline_count": len(required_baselines & numeric_baseline_seen),
                    "required_forward_driver_count": len(required_drivers),
                    "covered_forward_driver_count": len(required_drivers & driver_seen),
                    "numeric_forward_driver_count": len(required_drivers & numeric_driver_seen),
                    "baseline_complete": descriptive_baseline_complete,
                    "numeric_baseline_complete": numeric_baseline_complete,
                    "descriptive_driver_complete": descriptive_driver_complete,
                    "numeric_driver_complete": numeric_driver_complete,
                    "numeric_model_input_ready": (
                        numeric_baseline_complete and numeric_driver_complete
                    ),
                    "decision_score_enabled": False,
                }
            )
    block_frame = pd.DataFrame(block_rows).sort_values(
        ["ticker", "block_id"], kind="stable"
    ).reset_index(drop=True)
    issuer_rows: list[dict[str, object]] = []
    for ticker_key, group in block_frame.groupby("ticker", sort=True):
        required_blocks = len(group)
        issuer_rows.append(
            {
                "ticker": str(ticker_key),
                "required_block_count": required_blocks,
                "descriptive_ready_block_count": int(
                    (
                        group["baseline_complete"].astype(bool)
                        & group["descriptive_driver_complete"].astype(bool)
                    ).sum()
                ),
                "numeric_input_ready_block_count": int(
                    group["numeric_model_input_ready"].astype(bool).sum()
                ),
                "all_descriptive_inputs_covered": bool(
                    group["baseline_complete"].astype(bool).all()
                    and group["descriptive_driver_complete"].astype(bool).all()
                ),
                "all_numeric_inputs_covered": bool(
                    group["numeric_model_input_ready"].astype(bool).all()
                ),
                "internal_forward_model_certified": False,
                "numeric_forecast_enabled": False,
                "decision_score_enabled": False,
            }
        )
    issuer_frame = pd.DataFrame(issuer_rows).sort_values("ticker").reset_index(drop=True)
    return block_frame, issuer_frame


def build_semiconductor_forward_input_evidence(
    raw_claims: list[dict[str, object]],
    registry: dict[str, SemiconductorStructuralSource] | None = None,
    *,
    evaluation_date: date,
) -> SemiconductorForwardInputEvidence:
    source_registry = registry or load_structural_source_registry(
        DEFAULT_FORWARD_INPUT_SOURCE_REGISTRY
    )
    claims = tuple(
        validate_forward_input_claim(
            raw,
            source_registry,
            evaluation_date=evaluation_date,
        )
        for raw in raw_claims
    )
    if not claims:
        raise ValueError("Forward-input evidence requires at least one claim")
    if len({claim.claim_id for claim in claims}) != len(claims):
        raise ValueError("Forward-input evidence contains duplicate claims")
    blocks, issuers = _coverage(claims)
    payload = {
        "evaluation_date": evaluation_date.isoformat(),
        "claims": [claim.claim_id for claim in claims],
        "block_coverage": blocks.to_dict(orient="records"),
        "issuer_coverage": issuers.to_dict(orient="records"),
        "numeric_forecast_enabled": False,
        "decision_score_enabled": False,
    }
    evidence_id = _claim_id(payload)
    return SemiconductorForwardInputEvidence(
        evidence_id=evidence_id,
        evaluation_date=evaluation_date,
        claims=claims,
        block_coverage=blocks,
        issuer_coverage=issuers,
        numeric_forecast_enabled=False,
        decision_score_enabled=False,
    )


__all__ = [
    "DEFAULT_FORWARD_INPUT_SOURCE_REGISTRY",
    "SemiconductorForwardInputClaim",
    "SemiconductorForwardInputEvidence",
    "build_semiconductor_forward_input_evidence",
    "validate_forward_input_claim",
]
