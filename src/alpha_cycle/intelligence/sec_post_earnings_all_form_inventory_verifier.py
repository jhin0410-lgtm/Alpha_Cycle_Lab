"""Reverify archived SEC all-form inventory artifacts from source bytes."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import cast

from alpha_cycle.intelligence.sec_post_earnings_all_form_inventory import (
    SecPostEarningsAllFormEvidence,
    build_post_earnings_all_form_evidence,
    discover_post_earnings_primary_html_filings,
)

_REQUIRED_FALSE_FLAGS = (
    "product_baseline_eligible",
    "allocation_resolver_registered",
    "numeric_forecast_enabled",
    "decision_score_enabled",
)


def _json_object(path: Path, label: str) -> dict[str, object]:
    try:
        payload: object = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ValueError(f"{label} not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"{label} is invalid JSON: {path}") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"{label} must be a JSON object")
    return {str(key): value for key, value in cast(dict[object, object], payload).items()}


def _require_discovery_only(payload: dict[str, object], label: str) -> None:
    if payload.get("discovery_only") is not True:
        raise ValueError(f"{label} must remain discovery-only")
    for flag in _REQUIRED_FALSE_FLAGS:
        if payload.get(flag) is not False:
            raise ValueError(f"{label} requires {flag}=false")


def load_post_earnings_all_form_inventory_evidence(
    pointer_path: str | Path,
    *,
    evaluation_date: date,
) -> SecPostEarningsAllFormEvidence:
    pointer = _json_object(Path(pointer_path), "SEC all-form inventory pointer")
    if pointer.get("status") != "sec_post_earnings_all_form_inventory_captured":
        raise ValueError("SEC all-form inventory pointer status is invalid")
    _require_discovery_only(pointer, "SEC all-form inventory pointer")
    observed_date = date.fromisoformat(str(pointer.get("observed_date", "")))
    after_date = date.fromisoformat(str(pointer.get("after_date", "")))
    if observed_date > evaluation_date:
        raise ValueError("SEC all-form inventory evidence was not yet observed")

    artifact_directory = Path(str(pointer.get("artifact_directory", "")))
    manifest = _json_object(
        Path(str(pointer.get("manifest_path", ""))),
        "SEC all-form inventory manifest",
    )
    if manifest.get("status") != "sec_post_earnings_all_form_inventory_captured":
        raise ValueError("SEC all-form inventory manifest status is invalid")
    _require_discovery_only(manifest, "SEC all-form inventory manifest")

    try:
        submissions_bytes = (artifact_directory / "sec_submissions.json").read_bytes()
    except FileNotFoundError as exc:
        raise ValueError("SEC all-form archived submissions bytes are missing") from exc
    filings = discover_post_earnings_primary_html_filings(
        submissions_bytes,
        after_date=after_date,
        observed_date=observed_date,
    )
    filing_bytes_by_accession: dict[str, bytes] = {}
    for filing in filings:
        filing_path = artifact_directory / (
            f"{filing.accession_number}__{filing.primary_document}"
        )
        try:
            filing_bytes_by_accession[filing.accession_number] = filing_path.read_bytes()
        except FileNotFoundError as exc:
            raise ValueError(
                f"SEC all-form archived filing bytes are missing: {filing.accession_number}"
            ) from exc

    reconstructed = build_post_earnings_all_form_evidence(
        observed_date=observed_date,
        after_date=after_date,
        submissions_bytes=submissions_bytes,
        filing_bytes_by_accession=filing_bytes_by_accession,
    )
    evidence_id = str(pointer.get("evidence_id", ""))
    if reconstructed.evidence_id != evidence_id:
        raise ValueError("SEC all-form evidence does not reproduce from archived source bytes")
    if str(manifest.get("evidence_id", "")) != evidence_id:
        raise ValueError("SEC all-form manifest evidence ID mismatch")
    if reconstructed.submissions_sha256 != str(pointer.get("submissions_sha256", "")):
        raise ValueError("SEC all-form submissions hash does not reproduce")
    if reconstructed.submissions_sha256 != str(manifest.get("submissions_sha256", "")):
        raise ValueError("SEC all-form manifest submissions hash does not reproduce")

    results_path = Path(str(pointer.get("inventory_results_path", "")))
    try:
        raw_results: object = json.loads(results_path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ValueError("SEC all-form persisted results are missing") from exc
    except json.JSONDecodeError as exc:
        raise ValueError("SEC all-form persisted results are invalid JSON") from exc
    if not isinstance(raw_results, list) or len(raw_results) != len(reconstructed.results):
        raise ValueError("SEC all-form persisted result count mismatch")
    for raw, result in zip(raw_results, reconstructed.results, strict=True):
        if not isinstance(raw, dict):
            raise ValueError("SEC all-form persisted result must be an object")
        row = cast(dict[object, object], raw)
        expected = {
            "accession_number": result.accession_number,
            "form": result.form,
            "filing_sha256": result.filing_sha256,
            "visible_text_sha256": result.visible_text_sha256,
            "classification": result.classification,
            "candidate_for_manual_parser_review": result.candidate_for_manual_parser_review,
            "product_baseline_eligible": False,
            "allocation_resolver_registered": False,
            "numeric_forecast_enabled": False,
            "decision_score_enabled": False,
        }
        for key, value in expected.items():
            if row.get(key) != value:
                raise ValueError(f"SEC all-form persisted result mismatch: {key}")

    candidate_accessions = [
        item.accession_number
        for item in reconstructed.results
        if item.candidate_for_manual_parser_review
    ]
    if int(str(pointer.get("filing_count", "-1"))) != len(reconstructed.results):
        raise ValueError("SEC all-form persisted filing count mismatch")
    if int(str(pointer.get("candidate_count", "-1"))) != len(candidate_accessions):
        raise ValueError("SEC all-form persisted candidate count mismatch")
    raw_candidates = pointer.get("candidate_accessions")
    if not isinstance(raw_candidates, list):
        raise ValueError("SEC all-form candidate_accessions must be an array")
    if [str(item) for item in raw_candidates] != candidate_accessions:
        raise ValueError("SEC all-form persisted candidate accessions mismatch")
    return reconstructed


__all__ = ["load_post_earnings_all_form_inventory_evidence"]
