"""Offline verifier for the SK hynix historical direct product-revenue panel."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import cast

from alpha_cycle.intelligence.sk_hynix_opendart_historical_product_revenue_panel import (
    HistoricalProductRevenuePanelEntry,
    HistoricalProductRevenuePanelEvidence,
    build_historical_product_revenue_panel_evidence,
)
from alpha_cycle.intelligence.sk_hynix_opendart_q2_product_revenue_certification_verifier import (
    load_periodic_product_revenue_certification,
)


def _object(path: Path, label: str) -> dict[str, object]:
    try:
        raw: object = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ValueError(f"{label} not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"{label} is invalid JSON: {path}") from exc
    if not isinstance(raw, dict):
        raise ValueError(f"{label} must be a JSON object")
    return {str(key): value for key, value in cast(dict[object, object], raw).items()}


def _entry(raw: object) -> HistoricalProductRevenuePanelEntry:
    if not isinstance(raw, dict):
        raise ValueError("Historical product-revenue panel entry must be an object")
    item = cast(dict[object, object], raw)
    return HistoricalProductRevenuePanelEntry(
        period_id=str(item.get("period_id", "")),
        document_id=str(item.get("document_id", "")),
        status=str(item.get("status", "")),
        pointer_path=(
            str(item.get("pointer_path")) if item.get("pointer_path") is not None else None
        ),
        certification_evidence_id=(
            str(item.get("certification_evidence_id"))
            if item.get("certification_evidence_id") is not None
            else None
        ),
        chain_evidence_id=(
            str(item.get("chain_evidence_id"))
            if item.get("chain_evidence_id") is not None
            else None
        ),
        rcept_no=str(item.get("rcept_no")) if item.get("rcept_no") is not None else None,
        error_type=(
            str(item.get("error_type")) if item.get("error_type") is not None else None
        ),
    )


def load_historical_product_revenue_panel_evidence(
    pointer_path: str | Path,
    *,
    evaluation_date: date,
) -> HistoricalProductRevenuePanelEvidence:
    pointer = _object(Path(pointer_path), "Historical product-revenue panel pointer")
    if pointer.get("status") != "skhynix_opendart_historical_product_revenue_panel_captured":
        raise ValueError("Historical product-revenue panel pointer status is invalid")
    source_evaluation_date = date.fromisoformat(str(pointer.get("evaluation_date", "")))
    if source_evaluation_date != evaluation_date:
        raise ValueError("Historical product-revenue panel evaluation date mismatch")
    raw_entries = pointer.get("entries")
    if not isinstance(raw_entries, list):
        raise ValueError("Historical product-revenue panel entries must be an array")
    entries = tuple(_entry(item) for item in raw_entries)

    for item in entries:
        if item.status != "certified":
            continue
        if item.pointer_path is None:
            raise ValueError("Certified historical product revenue pointer is missing")
        period_pointer_path = Path(item.pointer_path)
        certification = load_periodic_product_revenue_certification(
            period_pointer_path,
            evaluation_date=evaluation_date,
        )
        if certification.evidence_id != item.certification_evidence_id:
            raise ValueError(
                f"Historical product revenue certification mismatch: {item.period_id}"
            )
        if certification.rcept_no != item.rcept_no:
            raise ValueError(f"Historical product revenue receipt mismatch: {item.period_id}")
        period_pointer = _object(
            period_pointer_path,
            f"Historical product revenue period pointer {item.period_id}",
        )
        if str(period_pointer.get("chain_evidence_id", "")) != item.chain_evidence_id:
            raise ValueError(f"Historical product revenue chain mismatch: {item.period_id}")

    reconstructed = build_historical_product_revenue_panel_evidence(
        evaluation_date=evaluation_date,
        entries=entries,
    )
    if reconstructed.evidence_id != str(pointer.get("evidence_id", "")):
        raise ValueError("Historical product-revenue panel evidence_id does not reproduce")
    if tuple(pointer.get("successful_periods", ())) != reconstructed.successful_periods:
        raise ValueError("Historical product-revenue successful period set does not reproduce")
    if tuple(pointer.get("failed_periods", ())) != reconstructed.failed_periods:
        raise ValueError("Historical product-revenue failed period set does not reproduce")
    coverage = pointer.get("full_source_coverage_certified")
    if coverage is not reconstructed.full_source_coverage_certified:
        raise ValueError("Historical product-revenue full-coverage flag does not reproduce")
    for field, expected in (
        ("calibration_support_only", True),
        ("product_profitability_source_fact", False),
        ("numeric_forecast_enabled", False),
        ("fair_value_estimate_enabled", False),
        ("target_price_enabled", False),
        ("decision_score_enabled", False),
    ):
        if pointer.get(field) is not expected:
            raise ValueError(f"Historical product-revenue trust boundary is invalid: {field}")

    panel = _object(Path(str(pointer.get("panel_path", ""))), "Historical product revenue panel")
    if str(panel.get("evidence_id", "")) != reconstructed.evidence_id:
        raise ValueError("Historical product-revenue panel file evidence mismatch")
    return reconstructed


__all__ = ["load_historical_product_revenue_panel_evidence"]
