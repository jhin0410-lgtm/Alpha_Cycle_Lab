"""Direct-fact baseline reconciliation for semiconductor issuer forward models.

Composite model baselines are not single source scalars.  V1 certifies a baseline
bridge only when every required block output is directly supported by exactly one
archived, semantics-certified issuer fact for the same block scope and accounting
period.  Residual arithmetic, peer substitution, and internal estimates are
intentionally prohibited in this layer.
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
)
from alpha_cycle.intelligence.semiconductor_model_input_semantics import (
    baseline_requirement_semantics,
)
from alpha_cycle.intelligence.semiconductor_structural_evidence import (
    SemiconductorStructuralSource,
    load_structural_source_registry,
)

DEFAULT_BASELINE_SOURCE_REGISTRY = Path("config/semiconductor_structural_sources.yaml")
_ISSUER_SOURCE_IDS = {"000660": "sk_hynix_ir", "005930": "samsung_ir"}


@dataclass(frozen=True)
class SemiconductorBaselineFact:
    fact_id: str
    ticker: str
    scope_id: str
    metric_id: str
    value: float
    unit: str
    period_start: date
    period_end: date
    source_id: str
    source_url: str
    source_published_date: date
    source_document_sha256: str
    source_bytes_archived: bool
    semantics_certified: bool
    source_vintage_certified: bool
    primary_source: bool
    bridge_eligible: bool
    decision_score_enabled: bool = False

    def __post_init__(self) -> None:
        if len(self.fact_id) != 64 or any(
            char not in "0123456789abcdef" for char in self.fact_id
        ):
            raise ValueError("Baseline fact_id must be SHA-256")
        if self.ticker not in SEMICONDUCTOR_FORWARD_MODEL_CONTRACTS:
            raise ValueError(f"Baseline issuer contract not registered: {self.ticker}")
        if not self.scope_id.strip() or not self.metric_id.strip() or not self.unit.strip():
            raise ValueError("Baseline fact scope/metric/unit cannot be blank")
        if self.period_start > self.period_end:
            raise ValueError("Baseline fact period_start cannot be after period_end")
        if self.source_published_date < self.period_end:
            raise ValueError("Baseline fact source cannot be published before period end")
        if len(self.source_document_sha256) != 64 or any(
            char not in "0123456789abcdef" for char in self.source_document_sha256
        ):
            raise ValueError("Baseline source document hash must be SHA-256")
        if self.bridge_eligible and not (
            self.source_bytes_archived
            and self.semantics_certified
            and self.source_vintage_certified
            and self.primary_source
        ):
            raise ValueError("Bridge-eligible baseline fact requires archived certified primary evidence")
        if self.decision_score_enabled:
            raise ValueError("Baseline facts must remain non-scoring")


@dataclass(frozen=True)
class SemiconductorBaselineReconciliationEvidence:
    evidence_id: str
    evaluation_date: date
    facts: tuple[SemiconductorBaselineFact, ...]
    bridge_coverage: pd.DataFrame
    issuer_summary: pd.DataFrame
    residual_derivation_enabled: bool = False
    internal_estimate_enabled: bool = False
    numeric_forecast_enabled: bool = False
    decision_score_enabled: bool = False

    def __post_init__(self) -> None:
        if len(self.evidence_id) != 64 or any(
            char not in "0123456789abcdef" for char in self.evidence_id
        ):
            raise ValueError("Baseline reconciliation evidence_id must be SHA-256")
        if not self.facts or self.bridge_coverage.empty or self.issuer_summary.empty:
            raise ValueError("Baseline reconciliation evidence requires facts and coverage")
        if self.residual_derivation_enabled or self.internal_estimate_enabled:
            raise ValueError("Baseline reconciliation v1 prohibits residual/internal derivation")
        if self.numeric_forecast_enabled or self.decision_score_enabled:
            raise ValueError("Baseline reconciliation must remain non-forecast/non-scoring")


def _sha(payload: dict[str, object]) -> str:
    return hashlib.sha256(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode(
            "utf-8"
        )
    ).hexdigest()


def _host_allowed(source: SemiconductorStructuralSource, url: str) -> bool:
    host = (urlparse(url).hostname or "").casefold()
    return bool(host) and any(
        host == domain or host.endswith("." + domain) for domain in source.domains
    )


def _block_outputs(ticker: str, scope_id: str) -> tuple[str, ...]:
    contract = SEMICONDUCTOR_FORWARD_MODEL_CONTRACTS[ticker]
    block = next((item for item in contract.blocks if item.block_id == scope_id), None)
    if block is None:
        raise ValueError(f"Baseline fact scope is not a registered issuer block: {ticker}/{scope_id}")
    return block.required_outputs


def validate_baseline_fact(
    raw: dict[str, object],
    registry: dict[str, SemiconductorStructuralSource],
    *,
    evaluation_date: date,
) -> SemiconductorBaselineFact:
    ticker = str(raw.get("ticker", "")).strip().zfill(6)
    if ticker not in SEMICONDUCTOR_FORWARD_MODEL_CONTRACTS:
        raise ValueError(f"Baseline issuer contract not registered: {ticker}")
    scope_id = str(raw.get("scope_id", "")).strip()
    metric_id = str(raw.get("metric_id", "")).strip()
    if metric_id not in _block_outputs(ticker, scope_id):
        raise ValueError(
            f"Baseline metric is outside block output contract: {ticker}/{scope_id}/{metric_id}"
        )
    source_id = str(raw.get("source_id", "")).strip()
    if source_id not in registry:
        raise ValueError(f"Unknown baseline source_id: {source_id}")
    source = registry[source_id]
    if source.role != "issuer_ir" or source.source_id != _ISSUER_SOURCE_IDS[ticker]:
        raise ValueError(f"Baseline accounting fact requires matching issuer IR source: {ticker}")
    source_url = str(raw.get("source_url", "")).strip()
    if not source_url.startswith("https://") or not _host_allowed(source, source_url):
        raise ValueError(f"Baseline source URL is outside registered domains: {source_id}")
    period_start = date.fromisoformat(str(raw.get("period_start", "")))
    period_end = date.fromisoformat(str(raw.get("period_end", "")))
    published = date.fromisoformat(str(raw.get("source_published_date", "")))
    if period_end > evaluation_date or published > evaluation_date:
        raise ValueError("Baseline fact cannot use future period/publication")
    document_hash = str(raw.get("source_document_sha256", "")).strip().casefold()
    source_bytes_archived = bool(raw.get("source_bytes_archived", False))
    semantics_certified = bool(raw.get("semantics_certified", False))
    source_vintage_certified = bool(raw.get("source_vintage_certified", False))
    bridge_eligible = bool(
        source.primary_source
        and source_bytes_archived
        and semantics_certified
        and source_vintage_certified
    )
    payload: dict[str, object] = {
        "ticker": ticker,
        "scope_id": scope_id,
        "metric_id": metric_id,
        "value": float(str(raw.get("value", "nan"))),
        "unit": str(raw.get("unit", "")).strip(),
        "period_start": period_start.isoformat(),
        "period_end": period_end.isoformat(),
        "source_id": source_id,
        "source_url": source_url,
        "source_published_date": published.isoformat(),
        "source_document_sha256": document_hash,
        "source_bytes_archived": source_bytes_archived,
        "semantics_certified": semantics_certified,
        "source_vintage_certified": source_vintage_certified,
        "primary_source": source.primary_source,
        "bridge_eligible": bridge_eligible,
        "decision_score_enabled": False,
    }
    return SemiconductorBaselineFact(
        fact_id=_sha(payload),
        ticker=ticker,
        scope_id=scope_id,
        metric_id=metric_id,
        value=float(payload["value"]),
        unit=str(payload["unit"]),
        period_start=period_start,
        period_end=period_end,
        source_id=source_id,
        source_url=source_url,
        source_published_date=published,
        source_document_sha256=document_hash,
        source_bytes_archived=source_bytes_archived,
        semantics_certified=semantics_certified,
        source_vintage_certified=source_vintage_certified,
        primary_source=source.primary_source,
        bridge_eligible=bridge_eligible,
    )


def _required_reconciliation_rows() -> list[tuple[str, str, str, tuple[str, ...]]]:
    rows: list[tuple[str, str, str, tuple[str, ...]]] = []
    for ticker, contract in SEMICONDUCTOR_FORWARD_MODEL_CONTRACTS.items():
        for block in contract.blocks:
            for baseline_metric in block.required_baseline_metrics:
                semantics = baseline_requirement_semantics(ticker, block.block_id, baseline_metric)
                if semantics.reconciliation_required:
                    rows.append(
                        (
                            ticker,
                            block.block_id,
                            baseline_metric,
                            block.required_outputs,
                        )
                    )
    return rows


def _bridge_coverage(facts: tuple[SemiconductorBaselineFact, ...]) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for ticker, block_id, baseline_metric, required_outputs in _required_reconciliation_rows():
        eligible = [
            fact
            for fact in facts
            if fact.ticker == ticker and fact.scope_id == block_id and fact.bridge_eligible
        ]
        periods = sorted({fact.period_end for fact in eligible}, reverse=True)
        selected_period: date | None = None
        selected: dict[str, SemiconductorBaselineFact] = {}
        ambiguous = False
        for period_end in periods:
            candidates: dict[str, list[SemiconductorBaselineFact]] = {
                metric: [
                    fact
                    for fact in eligible
                    if fact.period_end == period_end and fact.metric_id == metric
                ]
                for metric in required_outputs
            }
            if any(len(values) > 1 for values in candidates.values()):
                ambiguous = True
                continue
            if all(len(values) == 1 for values in candidates.values()):
                period_starts = {values[0].period_start for values in candidates.values()}
                units = {values[0].unit for values in candidates.values()}
                if len(period_starts) != 1 or len(units) != 1:
                    ambiguous = True
                    continue
                selected_period = period_end
                selected = {metric: values[0] for metric, values in candidates.items()}
                break
        certified = selected_period is not None and len(selected) == len(required_outputs)
        seen_outputs = sorted({fact.metric_id for fact in eligible if fact.metric_id in required_outputs})
        missing_outputs = [metric for metric in required_outputs if metric not in selected]
        status = "certified_direct_fact_bridge" if certified else (
            "ambiguous_direct_fact_bridge" if ambiguous else "missing_required_direct_facts"
        )
        rows.append(
            {
                "ticker": ticker,
                "block_id": block_id,
                "baseline_requirement_id": baseline_metric,
                "required_output_count": len(required_outputs),
                "eligible_output_count_any_period": len(set(required_outputs) & set(seen_outputs)),
                "certified_output_count": len(selected),
                "bridge_period_end": selected_period.isoformat() if selected_period else None,
                "bridge_fact_ids_json": json.dumps(
                    {metric: fact.fact_id for metric, fact in sorted(selected.items())},
                    ensure_ascii=False,
                    sort_keys=True,
                ),
                "missing_outputs_json": json.dumps(missing_outputs, ensure_ascii=False),
                "baseline_bridge_status": status,
                "baseline_bridge_certified": certified,
                "residual_derivation_used": False,
                "internal_estimate_used": False,
                "decision_score_enabled": False,
            }
        )
    return pd.DataFrame(rows).sort_values(["ticker", "block_id"], kind="stable").reset_index(
        drop=True
    )


def _issuer_summary(bridges: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for ticker_key, group in bridges.groupby("ticker", sort=True):
        required = len(group)
        certified = int(group["baseline_bridge_certified"].astype(bool).sum())
        rows.append(
            {
                "ticker": str(ticker_key),
                "baseline_reconciliation_required_count": required,
                "baseline_reconciliation_certified_count": certified,
                "baseline_reconciliation_certified": certified == required and required > 0,
                "residual_derivation_enabled": False,
                "internal_estimate_enabled": False,
                "numeric_forecast_enabled": False,
                "decision_score_enabled": False,
            }
        )
    return pd.DataFrame(rows).sort_values("ticker").reset_index(drop=True)


def build_semiconductor_baseline_reconciliation(
    raw_facts: list[dict[str, object]],
    registry: dict[str, SemiconductorStructuralSource] | None = None,
    *,
    evaluation_date: date,
) -> SemiconductorBaselineReconciliationEvidence:
    source_registry = registry or load_structural_source_registry(DEFAULT_BASELINE_SOURCE_REGISTRY)
    facts = tuple(
        validate_baseline_fact(raw, source_registry, evaluation_date=evaluation_date)
        for raw in raw_facts
    )
    if not facts:
        raise ValueError("Baseline reconciliation requires at least one accounting fact")
    if len({fact.fact_id for fact in facts}) != len(facts):
        raise ValueError("Baseline reconciliation contains duplicate facts")
    bridges = _bridge_coverage(facts)
    summary = _issuer_summary(bridges)
    payload: dict[str, object] = {
        "evaluation_date": evaluation_date.isoformat(),
        "fact_ids": [fact.fact_id for fact in facts],
        "bridge_coverage": bridges.to_dict(orient="records"),
        "issuer_summary": summary.to_dict(orient="records"),
        "residual_derivation_enabled": False,
        "internal_estimate_enabled": False,
        "numeric_forecast_enabled": False,
        "decision_score_enabled": False,
    }
    return SemiconductorBaselineReconciliationEvidence(
        evidence_id=_sha(payload),
        evaluation_date=evaluation_date,
        facts=facts,
        bridge_coverage=bridges,
        issuer_summary=summary,
    )


__all__ = [
    "DEFAULT_BASELINE_SOURCE_REGISTRY",
    "SemiconductorBaselineFact",
    "SemiconductorBaselineReconciliationEvidence",
    "build_semiconductor_baseline_reconciliation",
    "validate_baseline_fact",
]
