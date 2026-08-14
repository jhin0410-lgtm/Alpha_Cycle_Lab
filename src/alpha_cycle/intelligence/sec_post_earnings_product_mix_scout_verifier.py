"""Reverify archived SEC post-earnings scout artifacts from source bytes."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import cast

from alpha_cycle.intelligence.sec_post_earnings_product_mix_scout import (
    SecPostEarningsScoutEvidence,
    build_post_earnings_scout_evidence,
    discover_post_earnings_6k_filings,
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


def load_post_earnings_product_mix_scout_evidence(
    pointer_path: str | Path,
    *,
    evaluation_date: date,
) -> SecPostEarningsScoutEvidence:
    pointer = _json_object(Path(pointer_path), "SEC scout pointer")
    if pointer.get("status") != "sec_post_earnings_product_mix_scout_captured":
        raise ValueError("SEC scout pointer status is invalid")
    _require_discovery_only(pointer, "SEC scout pointer")
    observed_date = date.fromisoformat(str(pointer.get("observed_date", "")))
    after_date = date.fromisoformat(str(pointer.get("after_date", "")))
    if observed_date > evaluation_date:
        raise ValueError("SEC scout evidence was not yet observed")

    artifact_directory = Path(str(pointer.get("artifact_directory", "")))
    manifest = _json_object(
        Path(str(pointer.get("manifest_path", ""))),
        "SEC scout manifest",
    )
    if manifest.get("status") != "sec_post_earnings_product_mix_scout_captured":
        raise ValueError("SEC scout manifest status is invalid")
    _require_discovery_only(manifest, "SEC scout manifest")

    submissions_path = artifact_directory / "sec_submissions.json"
    try:
        submissions_bytes = submissions_path.read_bytes()
    except FileNotFoundError as exc:
        raise ValueError("SEC scout archived submissions bytes are missing") from exc
    filings = discover_post_earnings_6k_filings(
        submissions_bytes,
        after_date=after_date,
        observed_date=observed_date,
    )
    filing_bytes_by_accession: dict[str, bytes] = {}
    for filing in filings:
        if Path(filing.primary_document).name != filing.primary_document:
            raise ValueError("SEC scout primary document path is unsafe")
        filing_path = artifact_directory / (
            f"{filing.accession_number}__{filing.primary_document}"
        )
        try:
            filing_bytes_by_accession[filing.accession_number] = filing_path.read_bytes()
        except FileNotFoundError as exc:
            raise ValueError(
                f"SEC scout archived filing bytes are missing: {filing.accession_number}"
            ) from exc

    reconstructed = build_post_earnings_scout_evidence(
        observed_date=observed_date,
        after_date=after_date,
        submissions_bytes=submissions_bytes,
        filing_bytes_by_accession=filing_bytes_by_accession,
    )
    evidence_id = str(pointer.get("evidence_id", ""))
    if reconstructed.evidence_id != evidence_id or str(manifest.get("evidence_id", "")) != evidence_id:
        raise ValueError("SEC scout evidence does not reproduce from archived source bytes")
    if reconstructed.submissions_sha256 != str(pointer.get("submissions_sha256", "")):
        raise ValueError("SEC scout submissions hash does not reproduce")
    if reconstructed.submissions_sha256 != str(manifest.get("submissions_sha256", "")):
        raise ValueError("SEC scout manifest submissions hash does not reproduce")

    candidate_accessions = [
        item.accession_number
        for item in reconstructed.results
        if item.candidate_for_manual_parser_review
    ]
    expected_count = len(reconstructed.results)
    if int(str(pointer.get("filing_count", "-1"))) != expected_count:
        raise ValueError("SEC scout persisted filing count mismatch")
    if int(str(manifest.get("filing_count", "-1"))) != expected_count:
        raise ValueError("SEC scout manifest filing count mismatch")
    if int(str(pointer.get("candidate_count", "-1"))) != len(candidate_accessions):
        raise ValueError("SEC scout persisted candidate count mismatch")
    raw_candidates = pointer.get("candidate_accessions")
    if not isinstance(raw_candidates, list):
        raise ValueError("SEC scout pointer candidate_accessions must be an array")
    if [str(item) for item in raw_candidates] != candidate_accessions:
        raise ValueError("SEC scout persisted candidate accessions mismatch")

    results_path = Path(str(pointer.get("scout_results_path", "")))
    try:
        raw_results: object = json.loads(results_path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ValueError("SEC scout persisted results are missing") from exc
    except json.JSONDecodeError as exc:
        raise ValueError("SEC scout persisted results are invalid JSON") from exc
    if not isinstance(raw_results, list) or len(raw_results) != len(reconstructed.results):
        raise ValueError("SEC scout persisted result count mismatch")
    for raw, result in zip(raw_results, reconstructed.results, strict=True):
        if not isinstance(raw, dict):
            raise ValueError("SEC scout persisted result must be an object")
        row = cast(dict[object, object], raw)
        expected = {
            "accession_number": result.accession_number,
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
                raise ValueError(f"SEC scout persisted result mismatch: {key}")
    return reconstructed


__all__ = ["load_post_earnings_product_mix_scout_evidence"]
