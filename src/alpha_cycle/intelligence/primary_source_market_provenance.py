"""Strict degraded provenance for non-equivalent cross-provider market scopes."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from datetime import datetime
from pathlib import Path

from alpha_cycle.intelligence.market_consistency_provenance import (
    MarketConsistencyProvenance,
    _assessment_symbols,
    _boolean,
    _integer,
    _linked_file,
    _object,
    _recomputed_id,
    _safe_boundary,
    _same_path,
    _sha256,
    _symbols,
    _zero,
)
from alpha_cycle.market_consistency_cli import EXPECTED_SYMBOLS, _result_id
from alpha_cycle.market_consistency_runner_cli import (
    KRX_ONLY_CONTROL_SYMBOLS,
    VENUE_VARIABLE_SYMBOLS,
    _assessment_id,
)

_REQUIRED_CLASSIFICATION = "inferred_venue_scope_mismatch"
_REQUIRED_ASSESSMENT_STATUS = "blocked_market_scope_mismatch"
_REQUIRED_HISTORICAL_SCOPE_STATUS = "not_comparable"
_CONTROL_UNIVERSE = tuple(sorted(EXPECTED_SYMBOLS))
_SCOPE_INCOMPATIBLE_SYMBOLS = tuple(sorted(VENUE_VARIABLE_SYMBOLS))
_VERIFIED_CONTROL_SYMBOLS = tuple(sorted(KRX_ONLY_CONTROL_SYMBOLS))


class PrimarySourceMarketConsistencyProvenance(MarketConsistencyProvenance):
    """A pinned primary snapshot without cross-provider price certification."""

    @property
    def mode(self) -> str:
        return "primary_source_only"


def _normalized_required_symbols(values: Iterable[str]) -> tuple[str, ...]:
    normalized = tuple(sorted({str(value).strip().zfill(6) for value in values}))
    if not normalized:
        raise ValueError("decision_symbols cannot be empty")
    if any(len(value) != 6 or not value.isdigit() for value in normalized):
        raise ValueError("decision_symbols contains an invalid ticker")
    return normalized


def _string_tuple(value: object, field: str) -> tuple[str, ...]:
    if not isinstance(value, list):
        raise ValueError(f"{field} must be a list")
    normalized = tuple(sorted(str(item).strip().zfill(6) for item in value))
    if any(len(item) != 6 or not item.isdigit() for item in normalized):
        raise ValueError(f"{field} contains an invalid ticker")
    if len(set(normalized)) != len(normalized):
        raise ValueError(f"{field} contains duplicate tickers")
    return normalized


def _assessment_symbol_rows(
    value: object,
    *,
    required_days: int,
) -> Mapping[str, Mapping[str, object]]:
    if not isinstance(value, list):
        raise ValueError("assessment symbols must be a list")
    rows: dict[str, Mapping[str, object]] = {}
    for item in value:
        if not isinstance(item, dict):
            raise ValueError("assessment symbol evidence must contain objects")
        ticker = str(item.get("ticker", "")).strip().zfill(6)
        if ticker in rows:
            raise ValueError("assessment symbol evidence contains duplicate tickers")
        if ticker not in _CONTROL_UNIVERSE:
            raise ValueError(f"assessment symbol evidence has an invalid ticker: {ticker}")
        if _integer(item, "rows_compared") != required_days:
            raise ValueError(f"assessment coverage is incomplete for {ticker}")
        possible_mapping = item.get("possible_kiwoom_symbol")
        if possible_mapping not in {None, ""}:
            raise ValueError("possible cross-symbol mapping blocks primary-source mode")
        rows[ticker] = item
    if tuple(sorted(rows)) != _CONTROL_UNIVERSE:
        raise ValueError("assessment symbol evidence differs from the control universe")
    return rows


def _validate_scope_pattern(
    assessment: Mapping[str, object],
    raw: Mapping[str, object],
) -> None:
    required_days = _integer(raw, "historical_days_required_per_symbol")
    if required_days <= 0:
        raise ValueError("historical_days_required_per_symbol must be positive")
    expected_rows = required_days * len(_CONTROL_UNIVERSE)
    if _integer(raw, "historical_rows_compared") != expected_rows:
        raise ValueError("historical row coverage is incomplete")

    rows = _assessment_symbol_rows(
        assessment.get("symbols"),
        required_days=required_days,
    )
    for ticker in _SCOPE_INCOMPATIBLE_SYMBOLS:
        row = rows[ticker]
        if str(row.get("scope_role", "")) != "venue_variable_evidence":
            raise ValueError(f"unexpected scope role for {ticker}")
        if not _boolean(row, "full_series_price_difference"):
            raise ValueError(f"venue-variable price pattern is incomplete for {ticker}")
        if not _boolean(row, "full_series_volume_difference"):
            raise ValueError(f"venue-variable volume pattern is incomplete for {ticker}")
        if _integer(row, "price_difference_rows") != required_days:
            raise ValueError(f"venue-variable price rows are incomplete for {ticker}")
        if _integer(row, "volume_difference_rows") != required_days:
            raise ValueError(f"venue-variable volume rows are incomplete for {ticker}")

    for ticker in _VERIFIED_CONTROL_SYMBOLS:
        row = rows[ticker]
        if str(row.get("scope_role", "")) != "krx_only_control":
            raise ValueError(f"unexpected control scope role for {ticker}")
        _zero(row, "price_difference_rows")
        _zero(row, "tolerance_conflict_rows")
        _zero(row, "volume_difference_rows")
        if _boolean(row, "full_series_price_difference"):
            raise ValueError(f"control price series cannot be marked different: {ticker}")
        if _boolean(row, "full_series_volume_difference"):
            raise ValueError(f"control volume series cannot be marked different: {ticker}")


def _validate_eligibility_false(
    raw_pointer: Mapping[str, object],
    assessment_pointer: Mapping[str, object],
    raw: Mapping[str, object],
    assessment: Mapping[str, object],
) -> None:
    for payload, field in (
        (raw_pointer, "raw_decision_integration_eligible"),
        (raw_pointer, "decision_integration_eligible"),
        (assessment_pointer, "decision_integration_eligible"),
        (raw, "decision_integration_eligible"),
        (assessment, "decision_integration_eligible"),
    ):
        if _boolean(payload, field):
            raise ValueError("primary-source mode cannot claim decision integration eligibility")


def load_primary_source_market_provenance(
    root: str | Path,
    *,
    market_snapshot_id: str,
    decision_symbols: Iterable[str],
) -> PrimarySourceMarketConsistencyProvenance:
    """Verify the exact venue-scope mismatch pattern and preserve primary research.

    This mode does not certify current prices or historical OHLC across providers. It
    only permits a decision artifact to use the already-pinned TossInvest snapshot as
    its primary market source while recording that Kiwoom corroboration was not
    comparable. Provider substitution, account access, and order access stay disabled.
    """

    consistency_root = Path(root).resolve(strict=True)
    if not consistency_root.is_dir():
        raise ValueError(f"Consistency root is not a directory: {consistency_root}")
    market_id = _sha256(market_snapshot_id, "market_snapshot_id")
    required_symbols = _normalized_required_symbols(decision_symbols)

    raw_pointer = _object(consistency_root / "latest_market_consistency.json")
    assessment_pointer = _object(
        consistency_root / "latest_market_scope_assessment.json"
    )
    _safe_boundary(raw_pointer, "raw pointer")
    _safe_boundary(assessment_pointer, "assessment pointer")
    if str(raw_pointer.get("assessment_status", "")) != "completed":
        raise ValueError("Market consistency assessment is not complete")

    result_path = _linked_file(
        consistency_root,
        raw_pointer.get("result_path"),
        "result_path",
    )
    assessment_path = _linked_file(
        consistency_root,
        raw_pointer.get("assessment_path"),
        "assessment_path",
    )
    _same_path(
        assessment_pointer.get("assessment_path"),
        assessment_path,
        "assessment pointer",
    )
    _same_path(
        assessment_pointer.get("raw_result_path"),
        result_path,
        "raw result pointer",
    )

    raw = _object(result_path)
    assessment = _object(assessment_path)
    _safe_boundary(raw, "raw result")
    _safe_boundary(assessment, "assessment")
    result_id = _recomputed_id(raw, field="result_id", calculator=_result_id)
    assessment_id = _recomputed_id(
        assessment,
        field="assessment_id",
        calculator=_assessment_id,
    )

    if _sha256(raw_pointer.get("result_id"), "pointer result_id") != result_id:
        raise ValueError("Raw pointer result_id does not match the linked result")
    if _sha256(raw_pointer.get("assessment_id"), "pointer assessment_id") != assessment_id:
        raise ValueError("Raw pointer assessment_id does not match the linked assessment")
    if _sha256(assessment_pointer.get("assessment_id"), "assessment pointer id") != assessment_id:
        raise ValueError("Assessment pointer does not match the linked assessment")
    if _sha256(assessment.get("raw_result_id"), "assessment raw_result_id") != result_id:
        raise ValueError("Assessment is linked to a different raw result")
    _same_path(assessment.get("raw_result_path"), result_path, "assessment raw_result_path")

    if str(raw.get("status", "")) != "failed":
        raise ValueError("primary-source mode requires a failed raw consistency result")
    if str(assessment.get("raw_status", "")) != "failed":
        raise ValueError("assessment raw_status must remain failed")
    if str(assessment.get("status", "")) != _REQUIRED_ASSESSMENT_STATUS:
        raise ValueError("scope assessment does not identify a market-scope mismatch")
    if str(assessment.get("classification", "")) != _REQUIRED_CLASSIFICATION:
        raise ValueError("scope assessment classification blocks primary-source mode")
    if str(raw_pointer.get("classification", "")) != _REQUIRED_CLASSIFICATION:
        raise ValueError("raw pointer classification does not match the assessment")
    if str(assessment_pointer.get("classification", "")) != _REQUIRED_CLASSIFICATION:
        raise ValueError("assessment pointer classification does not match")
    if str(assessment.get("historical_scope_status", "")) != _REQUIRED_HISTORICAL_SCOPE_STATUS:
        raise ValueError("historical scope must be explicitly non-comparable")

    expected_symbols = _symbols(raw.get("expected_symbols"), "expected_symbols")
    if expected_symbols != _CONTROL_UNIVERSE:
        raise ValueError("consistency evidence does not cover the fixed control universe")
    if not set(required_symbols).issubset(expected_symbols):
        raise ValueError("consistency evidence is missing one or more decision symbols")
    if _assessment_symbols(assessment.get("symbols")) != expected_symbols:
        raise ValueError("assessment symbol evidence differs from the raw result")
    if _string_tuple(
        assessment.get("scope_incompatible_symbols"),
        "scope_incompatible_symbols",
    ) != _SCOPE_INCOMPATIBLE_SYMBOLS:
        raise ValueError("scope-incompatible symbols do not match the strict venue pattern")
    if _string_tuple(
        assessment.get("control_symbols_verified"),
        "control_symbols_verified",
    ) != _VERIFIED_CONTROL_SYMBOLS:
        raise ValueError("the KRX-only control symbol was not verified")
    if _symbols(
        raw.get("historical_symbols_passed"),
        "historical_symbols_passed",
    ) != _VERIFIED_CONTROL_SYMBOLS:
        raise ValueError("raw historical pass set must contain only the verified control")

    _validate_scope_pattern(assessment, raw)
    raw_difference_count = _integer(assessment, "raw_price_difference_count")
    tolerance_conflicts = _integer(assessment, "tolerance_conflict_count")
    scope_rows = _integer(assessment, "scope_incompatible_row_count")
    if raw_difference_count <= 0:
        raise ValueError("venue-scope mismatch must contain observed price differences")
    if len({raw_difference_count, tolerance_conflicts, scope_rows}) != 1:
        raise ValueError("scope mismatch row counts disagree")
    if _integer(raw, "historical_price_conflict_count") != tolerance_conflicts:
        raise ValueError("raw price conflict count does not match the assessment")
    if _integer(raw, "historical_volume_mismatch_count") != scope_rows:
        raise ValueError("raw volume mismatch count does not match the scope pattern")
    _zero(assessment, "comparable_scope_price_conflict_count")

    toss_scope = str(assessment.get("toss_historical_market_scope", "")).strip()
    kiwoom_scope = str(assessment.get("kiwoom_historical_market_scope", "")).strip()
    if not toss_scope or not kiwoom_scope or toss_scope == kiwoom_scope:
        raise ValueError("provider market scopes are not demonstrably non-equivalent")

    live_quote_status = str(raw.get("live_quote_status", ""))
    if live_quote_status not in {"passed", "not_comparable"}:
        raise ValueError("live quote conflict blocks primary-source mode")
    _zero(raw, "live_quote_conflict_count")
    _validate_eligibility_false(
        raw_pointer,
        assessment_pointer,
        raw,
        assessment,
    )

    if _sha256(raw.get("toss_snapshot_id"), "toss_snapshot_id") != market_id:
        raise ValueError("consistency evidence is linked to a different market snapshot")
    kiwoom_id = _sha256(raw.get("kiwoom_snapshot_id"), "kiwoom_snapshot_id")
    checked_at = str(raw.get("checked_at_utc", ""))
    parsed_checked_at = datetime.fromisoformat(checked_at)
    if parsed_checked_at.tzinfo is None or parsed_checked_at.utcoffset() is None:
        raise ValueError("checked_at_utc must be timezone-aware")
    if str(assessment.get("checked_at_utc", "")) != checked_at:
        raise ValueError("assessment checked_at_utc does not match the raw result")

    rationale = assessment.get("rationale", [])
    raw_warnings = raw.get("warnings", [])
    if not isinstance(rationale, list) or not isinstance(raw_warnings, list):
        raise ValueError("consistency warnings and rationale must be lists")
    warnings = tuple(
        dict.fromkeys(
            [
                "primary_market_snapshot_tossinvest_only",
                "cross_provider_historical_scope_not_comparable",
                "cross_provider_reference_price_not_certified",
                *(str(item) for item in raw_warnings),
                *(str(item) for item in rationale),
            ]
        )
    )
    return PrimarySourceMarketConsistencyProvenance(
        assessment_id=assessment_id,
        result_id=result_id,
        checked_at_utc=checked_at,
        raw_status="failed",
        classification=_REQUIRED_CLASSIFICATION,
        historical_scope_status=_REQUIRED_HISTORICAL_SCOPE_STATUS,
        market_snapshot_id=market_id,
        kiwoom_snapshot_id=kiwoom_id,
        expected_symbols=expected_symbols,
        live_quote_status=live_quote_status,
        historical_verified=False,
        live_price_certified=False,
        decision_integration_eligible=False,
        assessment_path=str(assessment_path),
        result_path=str(result_path),
        warnings=warnings,
    )


__all__ = [
    "PrimarySourceMarketConsistencyProvenance",
    "load_primary_source_market_provenance",
]
