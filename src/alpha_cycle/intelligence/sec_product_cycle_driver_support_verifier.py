"""Offline verifier for archived SK hynix SEC product cycle-driver support."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import cast

from alpha_cycle.intelligence.sec_product_cycle_driver_support import (
    SecProductCycleDriverSupportEvidence,
    build_sec_product_cycle_driver_support_evidence,
)
from alpha_cycle.intelligence.sec_product_profitability_support_verifier import (
    load_sec_product_profitability_support_evidence,
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


def load_sec_product_cycle_driver_support_evidence(
    pointer_path: str | Path,
    *,
    evaluation_date: date,
) -> SecProductCycleDriverSupportEvidence:
    pointer = _object(Path(pointer_path), "SEC product cycle-driver pointer")
    if pointer.get("status") != "sec_product_cycle_driver_support_captured":
        raise ValueError("SEC product cycle-driver pointer status is invalid")
    observed_date = date.fromisoformat(str(pointer.get("observed_date", "")))
    if observed_date > evaluation_date:
        raise ValueError("SEC product cycle-driver support was not yet observable")

    source_pointer_path = Path(str(pointer.get("source_profitability_support_pointer", "")))
    source = load_sec_product_profitability_support_evidence(
        source_pointer_path,
        evaluation_date=evaluation_date,
    )
    if source.evidence_id != str(pointer.get("source_profitability_support_evidence_id", "")):
        raise ValueError("SEC product cycle-driver source support evidence binding is invalid")

    filing_path = Path(str(pointer.get("source_filing_path", "")))
    try:
        filing_bytes = filing_path.read_bytes()
    except FileNotFoundError as exc:
        raise ValueError("SEC product cycle-driver archived filing bytes are missing") from exc
    reconstructed = build_sec_product_cycle_driver_support_evidence(
        observed_date=observed_date,
        ticker=source.ticker,
        accession_number=source.accession_number,
        source_profitability_support_evidence_id=source.evidence_id,
        expected_filing_sha256=source.filing_sha256,
        filing_bytes=filing_bytes,
    )
    if reconstructed.evidence_id != str(pointer.get("evidence_id", "")):
        raise ValueError("SEC product cycle-driver evidence_id does not reproduce")
    if reconstructed.source_filing_sha256 != str(pointer.get("source_filing_sha256", "")):
        raise ValueError("SEC product cycle-driver filing hash does not reproduce")
    if reconstructed.observation_count != int(str(pointer.get("observation_count", -1))):
        raise ValueError("SEC product cycle-driver observation count does not reproduce")

    for field, expected in (
        ("textual_band_source_facts", True),
        ("numeric_driver_values_available", False),
        ("calibration_support_only", True),
        ("current_baseline_eligible", False),
        ("product_profitability_source_fact", False),
        ("numeric_forecast_enabled", False),
        ("fair_value_estimate_enabled", False),
        ("target_price_enabled", False),
        ("decision_score_enabled", False),
    ):
        if pointer.get(field) is not expected:
            raise ValueError(f"SEC product cycle-driver trust boundary is invalid: {field}")

    support = _object(Path(str(pointer.get("support_path", ""))), "cycle-driver support payload")
    manifest = _object(Path(str(pointer.get("manifest_path", ""))), "cycle-driver manifest")
    for payload, label in ((support, "support"), (manifest, "manifest")):
        if str(payload.get("evidence_id", "")) != reconstructed.evidence_id:
            raise ValueError(f"SEC product cycle-driver {label} evidence mismatch")
        if str(payload.get("source_filing_sha256", "")) != reconstructed.source_filing_sha256:
            raise ValueError(f"SEC product cycle-driver {label} filing hash mismatch")
    return reconstructed


__all__ = ["load_sec_product_cycle_driver_support_evidence"]
