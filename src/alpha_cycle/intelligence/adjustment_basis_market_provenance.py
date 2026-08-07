"""Primary-source provenance for a pinned adjusted Toss snapshot versus legacy Kiwoom.

This degraded path is intentionally narrower than general market-consistency
fallbacks.  It is accepted only when the current Toss market snapshot is strictly
adjusted, the linked Kiwoom corroboration snapshot is strictly unadjusted, and the
raw consistency engine refused to compare historical OHLC across those bases.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from datetime import datetime
from pathlib import Path

from alpha_cycle.adjusted_market_consistency_compat import BASIS_MISMATCH_PREFIX
from alpha_cycle.intelligence.market_consistency_provenance import (
    _assessment_symbols,
    _boolean,
    _linked_file,
    _object,
    _recomputed_id,
    _safe_boundary,
    _same_path,
    _sha256,
    _symbols,
    _zero,
)
from alpha_cycle.intelligence.primary_source_market_provenance import (
    PrimarySourceMarketConsistencyProvenance,
    _normalized_required_symbols,
    _validate_eligibility_false,
)
from alpha_cycle.market_consistency_cli import EXPECTED_SYMBOLS, _result_id
from alpha_cycle.market_consistency_runner_cli import _assessment_id

_REQUIRED_CLASSIFICATION = "adjustment_basis_mismatch"
_REQUIRED_ASSESSMENT_STATUS = "blocked_adjustment_basis_mismatch"
_REQUIRED_SCOPE_STATUS = "not_comparable"
_CONTROL_UNIVERSE = tuple(sorted(EXPECTED_SYMBOLS))


def _strict_manifest_bool(payload: Mapping[str, object], field: str) -> bool:
    value = payload.get(field)
    if not isinstance(value, bool):
        raise ValueError(f"{field} must be a JSON boolean")
    return value


def _validate_zero_symbol_evidence(value: object) -> None:
    if _assessment_symbols(value) != _CONTROL_UNIVERSE:
        raise ValueError("assessment symbol evidence differs from the control universe")
    if not isinstance(value, list):
        raise ValueError("assessment symbols must be a list")
    for item in value:
        if not isinstance(item, dict):
            raise ValueError("assessment symbol evidence must contain objects")
        for field in (
            "rows_compared",
            "price_difference_rows",
            "tolerance_conflict_rows",
            "volume_difference_rows",
            "possible_symbol_match_rows",
        ):
            _zero(item, field)
        if _boolean(item, "full_series_price_difference"):
            raise ValueError("basis-mismatch evidence cannot claim compared price rows")
        if _boolean(item, "full_series_volume_difference"):
            raise ValueError("basis-mismatch evidence cannot claim compared volume rows")
        if item.get("possible_kiwoom_symbol") not in {None, ""}:
            raise ValueError("basis-mismatch evidence cannot claim a symbol mapping")


def _validate_basis_contract(raw: Mapping[str, object]) -> None:
    toss_manifest = _object(Path(str(raw.get("toss_directory", ""))) / "manifest.json")
    kiwoom_manifest = _object(Path(str(raw.get("kiwoom_directory", ""))) / "manifest.json")
    if toss_manifest.get("provider") != "tossinvest-readonly":
        raise ValueError("unexpected Toss provider in basis-mismatch evidence")
    if kiwoom_manifest.get("provider") != "kiwoom_openapi_plus":
        raise ValueError("unexpected Kiwoom provider in basis-mismatch evidence")
    if not _strict_manifest_bool(toss_manifest, "adjusted"):
        raise ValueError("basis-mismatch degraded mode requires adjusted Toss evidence")
    if _strict_manifest_bool(kiwoom_manifest, "adjusted_prices"):
        raise ValueError("basis-mismatch degraded mode requires legacy unadjusted Kiwoom")
    if _boolean(toss_manifest, "order_api_enabled"):
        raise ValueError("Toss market evidence cannot enable order API")
    for field in ("account_api_enabled", "order_api_enabled"):
        if _boolean(kiwoom_manifest, field):
            raise ValueError(f"Kiwoom market evidence cannot enable {field}")


def load_adjustment_basis_primary_source_provenance(
    root: str | Path,
    *,
    market_snapshot_id: str,
    decision_symbols: Iterable[str],
) -> PrimarySourceMarketConsistencyProvenance:
    """Verify one exact adjusted-vs-unadjusted mismatch and preserve Toss research."""

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
        consistency_root, raw_pointer.get("result_path"), "result_path"
    )
    assessment_path = _linked_file(
        consistency_root, raw_pointer.get("assessment_path"), "assessment_path"
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
        assessment, field="assessment_id", calculator=_assessment_id
    )
    if _sha256(raw_pointer.get("result_id"), "pointer result_id") != result_id:
        raise ValueError("Raw pointer result_id does not match the linked result")
    if _sha256(raw_pointer.get("assessment_id"), "pointer assessment_id") != assessment_id:
        raise ValueError("Raw pointer assessment_id does not match the linked assessment")
    if _sha256(
        assessment_pointer.get("assessment_id"), "assessment pointer id"
    ) != assessment_id:
        raise ValueError("Assessment pointer does not match the linked assessment")
    if _sha256(assessment.get("raw_result_id"), "assessment raw_result_id") != result_id:
        raise ValueError("Assessment is linked to a different raw result")
    _same_path(
        assessment.get("raw_result_path"), result_path, "assessment raw_result_path"
    )

    if str(raw.get("status", "")) != "failed":
        raise ValueError("basis-mismatch primary mode requires a failed raw result")
    if str(assessment.get("raw_status", "")) != "failed":
        raise ValueError("assessment raw_status must remain failed")
    if str(assessment.get("status", "")) != _REQUIRED_ASSESSMENT_STATUS:
        raise ValueError("assessment does not identify adjustment-basis mismatch")
    if str(assessment.get("classification", "")) != _REQUIRED_CLASSIFICATION:
        raise ValueError("assessment classification blocks basis-mismatch primary mode")
    if str(raw_pointer.get("classification", "")) != _REQUIRED_CLASSIFICATION:
        raise ValueError("raw pointer classification does not match assessment")
    if str(assessment_pointer.get("classification", "")) != _REQUIRED_CLASSIFICATION:
        raise ValueError("assessment pointer classification does not match")
    if str(assessment.get("historical_scope_status", "")) != _REQUIRED_SCOPE_STATUS:
        raise ValueError("historical adjustment bases must be explicitly non-comparable")

    expected_symbols = _symbols(raw.get("expected_symbols"), "expected_symbols")
    if expected_symbols != _CONTROL_UNIVERSE:
        raise ValueError("consistency evidence does not cover the fixed control universe")
    if not set(required_symbols).issubset(expected_symbols):
        raise ValueError("consistency evidence is missing decision symbols")
    if raw.get("historical_symbols_passed") != []:
        raise ValueError("basis-mismatch result cannot claim historical symbols passed")
    _zero(raw, "historical_rows_compared")
    _zero(raw, "historical_price_conflict_count")
    _zero(raw, "historical_volume_mismatch_count")
    for field in (
        "raw_price_difference_count",
        "tolerance_conflict_count",
        "comparable_scope_price_conflict_count",
        "scope_incompatible_row_count",
    ):
        _zero(assessment, field)
    if assessment.get("scope_incompatible_symbols") != []:
        raise ValueError("basis mismatch cannot claim scope-incompatible symbols")
    if assessment.get("control_symbols_verified") != []:
        raise ValueError("basis mismatch cannot claim verified control symbols")
    _validate_zero_symbol_evidence(assessment.get("symbols"))

    failures = raw.get("failures")
    if not isinstance(failures, list) or len(failures) != 1:
        raise ValueError("basis mismatch requires one explicit raw failure")
    failure = str(failures[0])
    if not failure.startswith(BASIS_MISMATCH_PREFIX):
        raise ValueError("raw failure does not identify an adjustment-basis mismatch")
    if "TossInvest adjusted=true" not in failure or "Kiwoom adjusted=false" not in failure:
        raise ValueError("raw basis mismatch direction is not the supported degraded case")

    live_quote_status = str(raw.get("live_quote_status", ""))
    if live_quote_status not in {"passed", "not_comparable"}:
        raise ValueError("live quote conflict blocks basis-mismatch primary mode")
    _zero(raw, "live_quote_conflict_count")
    _validate_eligibility_false(
        raw_pointer,
        assessment_pointer,
        raw,
        assessment,
    )
    _validate_basis_contract(raw)

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
                "cross_provider_historical_adjustment_basis_not_comparable",
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
        historical_scope_status=_REQUIRED_SCOPE_STATUS,
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


__all__ = ["load_adjustment_basis_primary_source_provenance"]
