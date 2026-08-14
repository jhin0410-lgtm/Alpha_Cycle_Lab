"""Source-bounded forward-input evidence for issuer-specific semiconductor models.

This layer is deliberately stricter than structural commentary. It records which
baseline metrics and forward drivers are actually supported for each issuer model
block and distinguishes qualitative evidence from numeric model inputs. Numeric
forecast readiness is never inferred from historical correlations or field names.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import date
from typing import cast
from urllib.parse import urlparse

import pandas as pd

from alpha_cycle.intelligence.semiconductor_forward_operating_model_contract import (
    SEMICONDUCTOR_FORWARD_MODEL_CONTRACTS,
)

_ALLOWED_CLAIM_TYPES = frozenset({"baseline", "forward_driver"})
_ALLOWED_KINDS = frozenset({"qualitative", "numeric"})
_ALLOWED_SOURCE_ROLES = frozenset(
    {
        "issuer_ir",
        "peer_ir",
        "customer_ir",
        "government",
        "exchange",
        "official_statistics",
        "certified_or_licensed_data",
    }
)


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
    source_role: str
    source_url: str
    source_published_date: date
    evaluation_date: date
    semantics_certified: bool
    source_vintage_certified: bool
    reuse_or_license_basis_documented: bool
    primary_source: bool
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
        if self.source_role not in _ALLOWED_SOURCE_ROLES:
            raise ValueError("Forward-input source_role is invalid")
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
            if not self.semantics_certified or not self.source_vintage_certified:
                raise ValueError(
                    "Numeric forward-input evidence requires certified semantics and source vintage"
                )
            if not self.primary_source and not self.reuse_or_license_basis_documented:
                raise ValueError(
                    "Non-primary numeric forward-input evidence requires documented reuse/license basis"
                )
        elif self.numeric_value is not None:
            raise ValueError("Qualitative forward-input evidence cannot publish numeric_value")
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
        if len(self.evidence_id) != 64:
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


def _block_contract(ticker: str, block_id: str) -> object:
    contract = SEMICONDUCTOR_FORWARD_MODEL_CONTRACTS[ticker]
    for block in contract.blocks:
        if block.block_id == block_id:
            return block
    raise ValueError(f"Forward-input block is not registered: {ticker}/{block_id}")


def validate_forward_input_claim(
    raw: dict[str, object],
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
        allowed = set(cast(object, block).required_baseline_metrics)
    elif claim_type == "forward_driver":
        allowed = set(cast(object, block).required_forward_drivers)
    else:
        raise ValueError("Forward-input claim_type is invalid")
    if metric_id not in allowed:
        raise ValueError(
            f"Forward-input metric is outside issuer block contract: {ticker}/{block_id}/{metric_id}"
        )

    kind = str(raw.get("evidence_kind", "qualitative")).strip()
    numeric_raw = raw.get("numeric_value")
    numeric_value = None if numeric_raw is None else float(str(numeric_raw))
    unit = str(raw.get("unit", "")).strip() or None
    published = date.fromisoformat(str(raw.get("source_published_date", "")))
    payload: dict[str, object] = {
        "ticker": ticker,
        "block_id": block_id,
        "claim_type": claim_type,
        "metric_id": metric_id,
        "evidence_kind": kind,
        "statement": str(raw.get("statement", "")).strip(),
        "numeric_value": numeric_value,
        "unit": unit,
        "period_start": str(raw.get("period_start", "")).strip() or None,
        "period_end": str(raw.get("period_end", "")).strip() or None,
        "source_role": str(raw.get("source_role", "")).strip(),
        "source_url": str(raw.get("source_url", "")).strip(),
        "source_published_date": published.isoformat(),
        "evaluation_date": evaluation_date.isoformat(),
        "semantics_certified": bool(raw.get("semantics_certified", False)),
        "source_vintage_certified": bool(raw.get("source_vintage_certified", False)),
        "reuse_or_license_basis_documented": bool(
            raw.get("reuse_or_license_basis_documented", False)
        ),
        "primary_source": bool(raw.get("primary_source", False)),
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
        period_start=_date_or_none(payload["period_start"]),
        period_end=_date_or_none(payload["period_end"]),
        source_role=str(payload["source_role"]),
        source_url=str(payload["source_url"]),
        source_published_date=published,
        evaluation_date=evaluation_date,
        semantics_certified=bool(payload["semantics_certified"]),
        source_vintage_certified=bool(payload["source_vintage_certified"]),
        reuse_or_license_basis_documented=bool(payload["reuse_or_license_basis_documented"]),
        primary_source=bool(payload["primary_source"]),
        decision_score_enabled=False,
    )


def _coverage(claims: tuple[SemiconductorForwardInputClaim, ...]) -> tuple[pd.DataFrame, pd.DataFrame]:
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
            numeric_driver_seen = {
                claim.metric_id
                for claim in block_claims
                if claim.claim_type == "forward_driver" and claim.evidence_kind == "numeric"
            }
            required_baselines = set(block.required_baseline_metrics)
            required_drivers = set(block.required_forward_drivers)
            block_rows.append(
                {
                    "ticker": ticker,
                    "block_id": block.block_id,
                    "required_baseline_count": len(required_baselines),
                    "covered_baseline_count": len(required_baselines & baseline_seen),
                    "required_forward_driver_count": len(required_drivers),
                    "covered_forward_driver_count": len(required_drivers & driver_seen),
                    "numeric_forward_driver_count": len(required_drivers & numeric_driver_seen),
                    "baseline_complete": required_baselines.issubset(baseline_seen),
                    "descriptive_driver_complete": required_drivers.issubset(driver_seen),
                    "numeric_driver_complete": required_drivers.issubset(numeric_driver_seen),
                    "numeric_model_input_ready": (
                        required_baselines.issubset(baseline_seen)
                        and required_drivers.issubset(numeric_driver_seen)
                    ),
                    "decision_score_enabled": False,
                }
            )
    block_frame = pd.DataFrame(block_rows).sort_values(
        ["ticker", "block_id"], kind="stable"
    ).reset_index(drop=True)
    issuer_rows: list[dict[str, object]] = []
    for ticker, group in block_frame.groupby("ticker", sort=True):
        required_blocks = len(group)
        issuer_rows.append(
            {
                "ticker": str(ticker),
                "required_block_count": required_blocks,
                "descriptive_ready_block_count": int(
                    group["descriptive_driver_complete"].astype(bool).sum()
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
    return block_frame, pd.DataFrame(issuer_rows).sort_values("ticker").reset_index(drop=True)


def build_semiconductor_forward_input_evidence(
    raw_claims: list[dict[str, object]],
    *,
    evaluation_date: date,
) -> SemiconductorForwardInputEvidence:
    claims = tuple(
        validate_forward_input_claim(raw, evaluation_date=evaluation_date) for raw in raw_claims
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
    "SemiconductorForwardInputClaim",
    "SemiconductorForwardInputEvidence",
    "build_semiconductor_forward_input_evidence",
    "validate_forward_input_claim",
]
