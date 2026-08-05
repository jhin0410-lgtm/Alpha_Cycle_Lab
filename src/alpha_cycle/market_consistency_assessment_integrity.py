"""Fail-closed integrity additions for market scope assessment artifacts."""

from __future__ import annotations

import csv
from dataclasses import asdict
from decimal import Decimal, InvalidOperation
from pathlib import Path

from alpha_cycle import market_consistency_integrity as raw_integrity
from alpha_cycle import market_consistency_runner_cli as runner
from alpha_cycle.market_consistency_cli import ConsistencyError, ConsistencyResult

_REQUIRED_QUOTE_FIELDS = (
    "ticker",
    "toss_price",
    "kiwoom_price",
    "absolute_difference_won",
    "difference_bps",
    "capture_gap_seconds",
    "comparable",
    "within_tolerance",
    "reason",
)


def _decimal_field(value: object, *, field: str) -> Decimal:
    text = str(value).strip()
    if not text:
        raise runner.ScopeAssessmentError(f"live quote field is empty: {field}")
    try:
        parsed = Decimal(text)
    except InvalidOperation as exc:
        raise runner.ScopeAssessmentError(
            f"invalid live quote decimal {field}: {value}"
        ) from exc
    if not parsed.is_finite():
        raise runner.ScopeAssessmentError(
            f"non-finite live quote decimal {field}: {value}"
        )
    return parsed


def _boolean_field(value: object, *, field: str) -> bool:
    normalized = str(value).strip().casefold()
    if normalized in {"true", "1", "yes"}:
        return True
    if normalized in {"false", "0", "no"}:
        return False
    raise runner.ScopeAssessmentError(
        f"invalid live quote boolean {field}: {value}"
    )


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
    expected_gap = Decimal(str(result.live_capture_gap_seconds))
    seen: set[str] = set()
    duplicates: set[str] = set()
    comparable_count = 0
    conflict_count = 0

    for index, row in enumerate(rows):
        missing_columns = [field for field in _REQUIRED_QUOTE_FIELDS if field not in row]
        if missing_columns:
            raise runner.ScopeAssessmentError(
                "live quote comparison row is missing fields: "
                + ", ".join(missing_columns)
            )
        ticker = row["ticker"].strip()
        if not ticker:
            raise runner.ScopeAssessmentError(
                "live quote comparison row has no ticker"
            )
        if ticker in seen:
            duplicates.add(ticker)
        seen.add(ticker)

        source = f"row {index + 1} ({ticker})"
        toss_price = _decimal_field(
            row["toss_price"],
            field=f"{source} toss_price",
        )
        kiwoom_price = _decimal_field(
            row["kiwoom_price"],
            field=f"{source} kiwoom_price",
        )
        absolute_difference = _decimal_field(
            row["absolute_difference_won"],
            field=f"{source} absolute_difference_won",
        )
        difference_bps = _decimal_field(
            row["difference_bps"],
            field=f"{source} difference_bps",
        )
        capture_gap = _decimal_field(
            row["capture_gap_seconds"],
            field=f"{source} capture_gap_seconds",
        )
        if toss_price <= 0 or kiwoom_price <= 0:
            raise runner.ScopeAssessmentError(
                f"live quote prices must be positive: {source}"
            )
        if absolute_difference < 0 or difference_bps < 0 or capture_gap < 0:
            raise runner.ScopeAssessmentError(
                f"live quote differences cannot be negative: {source}"
            )

        expected_difference = abs(toss_price - kiwoom_price)
        if absolute_difference != expected_difference:
            raise runner.ScopeAssessmentError(
                f"live quote absolute difference mismatch: {source}"
            )
        denominator = max(abs(toss_price), abs(kiwoom_price))
        expected_bps = (
            expected_difference / denominator * Decimal(10000)
        ).quantize(Decimal("0.0001"))
        if difference_bps != expected_bps:
            raise runner.ScopeAssessmentError(
                f"live quote bps difference mismatch: {source}"
            )
        if capture_gap != expected_gap:
            raise runner.ScopeAssessmentError(
                f"live quote capture gap mismatch: {source}"
            )
        if not row["reason"].strip():
            raise runner.ScopeAssessmentError(
                f"live quote comparison reason is empty: {source}"
            )

        comparable = _boolean_field(
            row["comparable"],
            field=f"{source} comparable",
        )
        within_text = row["within_tolerance"].strip()
        if comparable:
            comparable_count += 1
            if not within_text:
                raise runner.ScopeAssessmentError(
                    f"comparable live quote has no tolerance result: {source}"
                )
            within = _boolean_field(
                within_text,
                field=f"{source} within_tolerance",
            )
            if not within:
                conflict_count += 1
        elif within_text:
            raise runner.ScopeAssessmentError(
                f"non-comparable live quote has a tolerance result: {source}"
            )

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
    if comparable_count not in {0, len(expected)}:
        raise runner.ScopeAssessmentError(
            "live quote comparison mixes comparable and non-comparable rows"
        )
    if comparable_count != result.live_quote_comparable_count:
        raise runner.ScopeAssessmentError(
            "live quote comparable count does not match the raw result"
        )
    if conflict_count != result.live_quote_conflict_count:
        raise runner.ScopeAssessmentError(
            "live quote conflict count does not match the raw result"
        )

    expected_status = "not_comparable"
    if comparable_count == len(expected):
        expected_status = "conflict" if conflict_count else "passed"
    if result.live_quote_status != expected_status:
        raise runner.ScopeAssessmentError(
            "live quote status does not match the linked comparison rows"
        )


def assess_consistency_result(
    result: ConsistencyResult,
    result_path: Path,
    *,
    output_root: Path,
) -> tuple[runner.MarketScopeAssessment, Path]:
    """Assess exact evidence and publish eligibility only after full validation."""

    try:
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
            "schema_version": "1.3",
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
            "control_symbols_verified": list(
                classification.control_symbols_verified
            ),
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
            schema_version="1.3",
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
            toss_historical_market_scope=(
                classification.toss_historical_market_scope
            ),
            kiwoom_historical_market_scope=(
                classification.kiwoom_historical_market_scope
            ),
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
        raw_integrity._atomic_json(assessment_path, asdict(assessment))
        raw_integrity._atomic_json(
            output_root / "latest_market_scope_assessment.json",
            {
                "status": assessment.status,
                "classification": assessment.classification,
                "assessment_id": assessment.assessment_id,
                "assessment_path": str(assessment_path),
                "raw_result_id": assessment.raw_result_id,
                "raw_result_path": assessment.raw_result_path,
                "decision_integration_eligible": (
                    assessment.decision_integration_eligible
                ),
                "automatic_provider_substitution_enabled": False,
                "account_api_enabled": False,
                "order_api_enabled": False,
            },
        )
        raw_integrity.publish_assessed_consistency_pointer(
            output_root=output_root,
            result=result,
            result_path=result_path,
            assessment_id=assessment.assessment_id,
            assessment_path=assessment_path,
            classification=assessment.classification,
            decision_integration_eligible=assessment.decision_integration_eligible,
        )
        return assessment, assessment_path
    except (
        csv.Error,
        ConsistencyError,
        runner.ScopeAssessmentError,
        OSError,
        TypeError,
        ValueError,
    ) as exc:
        raw_integrity.mark_consistency_assessment_failed(
            output_root=output_root,
            result=result,
            result_path=result_path,
            failure=exc,
        )
        raise
