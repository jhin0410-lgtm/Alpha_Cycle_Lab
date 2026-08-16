"""Offline verifier for archived SEC product-profitability calibration support."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import cast

from alpha_cycle.intelligence.sec_product_profitability_support import (
    DEFAULT_SEC_PRODUCT_PROFITABILITY_REGISTRY,
    SecProductProfitabilitySupportEvidence,
    build_sec_product_profitability_support_evidence,
    load_sec_product_profitability_registry,
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


def load_sec_product_profitability_support_evidence(
    pointer_path: str | Path,
    *,
    evaluation_date: date,
    registry_path: str | Path = DEFAULT_SEC_PRODUCT_PROFITABILITY_REGISTRY,
) -> SecProductProfitabilitySupportEvidence:
    """Replay archived first-party bytes and reproduce the calibration-support evidence."""

    pointer = _object(Path(pointer_path), "SEC product-profitability pointer")
    if pointer.get("status") != "sec_product_profitability_support_captured":
        raise ValueError("SEC product-profitability pointer status is invalid")
    observed_date = date.fromisoformat(str(pointer.get("observed_date", "")))
    if observed_date > evaluation_date:
        raise ValueError("SEC product-profitability support was not yet observed")
    specs = load_sec_product_profitability_registry(registry_path)
    document_id = str(pointer.get("document_id", ""))
    if document_id not in specs:
        raise ValueError("SEC product-profitability document is not registered")
    spec = specs[document_id]
    submissions_path = Path(str(pointer.get("submissions_path", "")))
    filing_path = Path(str(pointer.get("filing_path", "")))
    try:
        submissions_bytes = submissions_path.read_bytes()
        filing_bytes = filing_path.read_bytes()
    except FileNotFoundError as exc:
        raise ValueError("SEC product-profitability archived source bytes are missing") from exc
    reconstructed = build_sec_product_profitability_support_evidence(
        spec,
        observed_date=observed_date,
        submissions_bytes=submissions_bytes,
        filing_bytes=filing_bytes,
    )
    if reconstructed.evidence_id != str(pointer.get("evidence_id", "")):
        raise ValueError("SEC product-profitability evidence_id does not reproduce")
    if reconstructed.submissions_sha256 != str(pointer.get("submissions_sha256", "")):
        raise ValueError("SEC product-profitability submissions hash does not reproduce")
    if reconstructed.filing_sha256 != str(pointer.get("filing_sha256", "")):
        raise ValueError("SEC product-profitability filing hash does not reproduce")
    if reconstructed.observation_count != int(str(pointer.get("observation_count", -1))):
        raise ValueError("SEC product-profitability observation count does not reproduce")
    if reconstructed.independent_non_overlapping_period_count != int(
        str(pointer.get("independent_non_overlapping_period_count", -1))
    ):
        raise ValueError("SEC product-profitability independent period count does not reproduce")
    if pointer.get("calibration_support_only") is not True:
        raise ValueError("SEC product-profitability calibration-support flag is invalid")
    if pointer.get("product_profitability_source_fact") is not False:
        raise ValueError("SEC product-profitability source-fact boundary is invalid")
    if pointer.get("current_baseline_eligible") is not False:
        raise ValueError("SEC product-profitability current-baseline boundary is invalid")
    if int(str(pointer.get("direct_product_profitability_observations", -1))) != 0:
        raise ValueError("SEC support cannot claim direct product-profitability observations")
    for field in (
        "numeric_forecast_enabled",
        "fair_value_estimate_enabled",
        "target_price_enabled",
        "decision_score_enabled",
    ):
        if pointer.get(field) is not False:
            raise ValueError(f"SEC product-profitability downstream gate is invalid: {field}")
    support = _object(
        Path(str(pointer.get("support_path", ""))),
        "SEC product-profitability support payload",
    )
    manifest = _object(
        Path(str(pointer.get("manifest_path", ""))),
        "SEC product-profitability manifest",
    )
    for payload, label in ((support, "support"), (manifest, "manifest")):
        if str(payload.get("evidence_id", "")) != reconstructed.evidence_id:
            raise ValueError(f"SEC product-profitability {label} evidence mismatch")
        if str(payload.get("filing_sha256", "")) != reconstructed.filing_sha256:
            raise ValueError(f"SEC product-profitability {label} filing hash mismatch")
    return reconstructed


__all__ = ["load_sec_product_profitability_support_evidence"]
