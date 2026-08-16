"""Offline verifier for archived SK hynix quarterly company-profitability evidence."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import cast

from alpha_cycle.intelligence.sk_hynix_opendart_quarterly_company_profitability import (
    DEFAULT_QUARTERLY_COMPANY_PROFITABILITY_REGISTRY,
    QuarterlyCompanyProfitabilityEvidence,
    build_quarterly_company_profitability_evidence,
    load_quarterly_company_profitability_registry,
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


def load_quarterly_company_profitability_evidence(
    pointer_path: str | Path,
    *,
    evaluation_date: date,
    registry_path: str | Path = DEFAULT_QUARTERLY_COMPANY_PROFITABILITY_REGISTRY,
) -> QuarterlyCompanyProfitabilityEvidence:
    """Rebuild the panel from archived raw all-accounts JSON and verify all boundaries."""

    pointer = _object(Path(pointer_path), "Quarterly profitability pointer")
    if pointer.get("status") != "skhynix_opendart_quarterly_company_profitability_captured":
        raise ValueError("Quarterly profitability pointer status is invalid")
    source_evaluation_date = date.fromisoformat(str(pointer.get("evaluation_date", "")))
    if source_evaluation_date > evaluation_date:
        raise ValueError("Quarterly profitability panel was not yet observable")

    registry = load_quarterly_company_profitability_registry(registry_path)
    raw_directory = Path(str(pointer.get("raw_directory", "")))
    raw_payloads: dict[str, object] = {}
    for spec in registry.periods:
        raw_payloads[spec.period_id] = _object(
            raw_directory / f"{spec.period_id}.json",
            f"Quarterly profitability raw payload {spec.period_id}",
        )
    reconstructed = build_quarterly_company_profitability_evidence(
        registry,
        evaluation_date=source_evaluation_date,
        raw_payloads=raw_payloads,
    )
    if reconstructed.evidence_id != str(pointer.get("evidence_id", "")):
        raise ValueError("Quarterly profitability evidence_id does not reproduce")
    if reconstructed.observation_count != int(str(pointer.get("observation_count", -1))):
        raise ValueError("Quarterly profitability observation count does not reproduce")

    raw_pointer_observations = pointer.get("observations")
    if not isinstance(raw_pointer_observations, list):
        raise ValueError("Quarterly profitability pointer observations must be an array")
    pointer_hashes = {
        str(item.get("period_id", "")): str(item.get("raw_payload_sha256", ""))
        for item in raw_pointer_observations
        if isinstance(item, dict)
    }
    for observation in reconstructed.observations:
        if pointer_hashes.get(observation.period_id) != observation.raw_payload_sha256:
            raise ValueError(
                f"Quarterly profitability raw payload hash mismatch: {observation.period_id}"
            )

    for field, expected in (
        ("calibration_support_only", True),
        ("historical_vintage_certified", False),
        ("point_in_time_backtest_eligible", False),
        ("product_profitability_source_fact", False),
        ("numeric_forecast_enabled", False),
        ("fair_value_estimate_enabled", False),
        ("target_price_enabled", False),
        ("decision_score_enabled", False),
    ):
        if pointer.get(field) is not expected:
            raise ValueError(f"Quarterly profitability trust boundary is invalid: {field}")

    panel = _object(Path(str(pointer.get("panel_path", ""))), "Quarterly profitability panel")
    manifest = _object(
        Path(str(pointer.get("manifest_path", ""))),
        "Quarterly profitability manifest",
    )
    for payload, label in ((panel, "panel"), (manifest, "manifest")):
        if str(payload.get("evidence_id", "")) != reconstructed.evidence_id:
            raise ValueError(f"Quarterly profitability {label} evidence mismatch")
        if int(str(payload.get("observation_count", -1))) != reconstructed.observation_count:
            raise ValueError(f"Quarterly profitability {label} count mismatch")
    return reconstructed


__all__ = ["load_quarterly_company_profitability_evidence"]
