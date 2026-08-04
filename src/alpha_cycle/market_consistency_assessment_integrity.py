"""Fail-closed integrity additions for market scope assessment artifacts."""

from __future__ import annotations

import csv
from dataclasses import asdict
from pathlib import Path

from alpha_cycle import market_consistency_runner_cli as runner
from alpha_cycle.market_consistency_cli import ConsistencyResult


def _validate_live_quote_rows(
    result: ConsistencyResult,
    result_path: Path,
) -> None:
    quote_path = result_path.parent / result.quote_comparisons_file
    try:
        rows = runner._read_csv(quote_path)
    except csv.Error as exc:
        raise runner.ScopeAssessmentError(
            f"malformed live quote comparison CSV: {exc}"
        ) from exc

    expected = tuple(sorted(result.expected_symbols))
    seen: set[str] = set()
    duplicates: set[str] = set()
    for row in rows:
        ticker = row.get("ticker", "").strip()
        if not ticker:
            raise runner.ScopeAssessmentError(
                "live quote comparison row has no ticker"
            )
        if ticker in seen:
            duplicates.add(ticker)
        seen.add(ticker)
    if duplicates:
        raise runner.ScopeAssessmentError(
            "live quote comparison has duplicate tickers: "
            + ", ".join(sorted(duplicates))
        )
    actual = tuple(sorted(seen))
    if actual != expected or len(rows) != len(expected):
        raise runner.ScopeAssessmentError(
            f"live quote comparison symbol set mismatch: expected {expected}, got {actual}"
        )


def assess_consistency_result(
    result: ConsistencyResult,
    result_path: Path,
    *,
    output_root: Path,
) -> tuple[runner.MarketScopeAssessment, Path]:
    """Assess exact evidence and write an eligibility-safe linked artifact."""

    daily_path = result_path.parent / result.daily_comparisons_file
    try:
        rows = runner._read_csv(daily_path)
    except csv.Error as exc:
        raise runner.ScopeAssessmentError(
            f"malformed daily comparison CSV: {exc}"
        ) from exc
    _validate_live_quote_rows(result, result_path)

    evidence = runner._symbol_evidence(rows, result)
    raw_difference_count = sum(item.price_difference_rows for item in evidence)
    tolerance_conflicts = sum(item.tolerance_conflict_rows for item in evidence)
    classification = runner._classify_scope(result, evidence)
    integration_eligible = (
        classification.status == "passed"
        and classification.classification == "equivalent_scope_observed"
        and raw_difference_count == 0
        and tolerance_conflicts == 0
        and classification.comparable_scope_price_conflict_count == 0
        and bool(result.decision_integration_eligible)
    )

    payload: dict[str, object] = {
        "schema_version": "1.2",
        "status": classification.status,
        "classification": classification.classification,
        "checked_at_utc": result.checked_at_utc,
        "checked_at_kst": result.checked_at_kst,
        "raw_result_id": result.result_id,
        "raw_result_path": str(result_path),
        "raw_status": result.status,
        "raw_price_difference_count": raw_difference_count,
        "tolerance_conflict_count": tolerance_conflicts,
        "comparable_scope_price_conflict_count": (
            classification.comparable_scope_price_conflict_count
        ),
        "scope_incompatible_row_count": classification.scope_incompatible_row_count,
        "historical_scope_status": classification.historical_scope_status,
        "toss_historical_market_scope": (
            classification.toss_historical_market_scope
        ),
        "kiwoom_historical_market_scope": (
            classification.kiwoom_historical_market_scope
        ),
        "scope_incompatible_symbols": list(
            classification.scope_incompatible_symbols
        ),
        "control_symbols_verified": list(classification.control_symbols_verified),
        "live_quote_status": result.live_quote_status,
        "live_quote_conflict_count": result.live_quote_conflict_count,
        "raw_failures": list(result.failures),
        "decision_integration_eligible": integration_eligible,
        "automatic_provider_substitution_enabled": False,
        "account_api_enabled": False,
        "order_api_enabled": False,
        "rationale": list(classification.rationale),
        "symbols": [asdict(item) for item in evidence],
    }
    assessment_id = runner._assessment_id(payload)
    assessment = runner.MarketScopeAssessment(
        schema_version="1.2",
        status=classification.status,
        classification=classification.classification,
        checked_at_utc=result.checked_at_utc,
        checked_at_kst=result.checked_at_kst,
        raw_result_id=result.result_id,
        raw_result_path=str(result_path),
        raw_status=result.status,
        raw_price_difference_count=raw_difference_count,
        tolerance_conflict_count=tolerance_conflicts,
        comparable_scope_price_conflict_count=(
            classification.comparable_scope_price_conflict_count
        ),
        scope_incompatible_row_count=classification.scope_incompatible_row_count,
        historical_scope_status=classification.historical_scope_status,
        toss_historical_market_scope=classification.toss_historical_market_scope,
        kiwoom_historical_market_scope=classification.kiwoom_historical_market_scope,
        scope_incompatible_symbols=classification.scope_incompatible_symbols,
        control_symbols_verified=classification.control_symbols_verified,
        live_quote_status=result.live_quote_status,
        live_quote_conflict_count=result.live_quote_conflict_count,
        raw_failures=result.failures,
        decision_integration_eligible=integration_eligible,
        automatic_provider_substitution_enabled=False,
        account_api_enabled=False,
        order_api_enabled=False,
        rationale=classification.rationale,
        symbols=evidence,
        assessment_id=assessment_id,
    )
    assessment_path = result_path.parent / "market_scope_assessment.json"
    runner._atomic_json(assessment_path, asdict(assessment))
    runner._atomic_json(
        output_root / "latest_market_scope_assessment.json",
        {
            "status": assessment.status,
            "classification": assessment.classification,
            "assessment_id": assessment.assessment_id,
            "assessment_path": str(assessment_path),
            "raw_result_id": assessment.raw_result_id,
            "raw_result_path": assessment.raw_result_path,
            "decision_integration_eligible": assessment.decision_integration_eligible,
            "automatic_provider_substitution_enabled": False,
            "account_api_enabled": False,
            "order_api_enabled": False,
        },
    )
    return assessment, assessment_path
