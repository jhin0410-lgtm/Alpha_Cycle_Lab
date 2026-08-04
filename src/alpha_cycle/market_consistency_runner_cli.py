"""Assess cross-provider market consistency with explicit venue-scope boundaries."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
from collections import defaultdict
from collections.abc import Mapping
from dataclasses import asdict, dataclass
from decimal import Decimal
from pathlib import Path

from alpha_cycle.market_consistency_cli import (
    DEFAULT_OUTPUT_ROOT,
    ConsistencyError,
    ConsistencyResult,
    run_consistency_check,
)

EXPECTED_SYMBOLS = ("000660", "005930", "005935")
VENUE_VARIABLE_SYMBOLS = ("000660", "005930")
KRX_ONLY_CONTROL_SYMBOLS = ("005935",)
KIWOOM_DAILY_TR_CODE = "opt10081"


class ScopeAssessmentError(ValueError):
    """Expected failure while validating or classifying local evidence."""


@dataclass(frozen=True)
class SymbolScopeEvidence:
    ticker: str
    scope_role: str
    rows_compared: int
    price_difference_rows: int
    volume_difference_rows: int
    full_series_price_difference: bool
    full_series_volume_difference: bool


@dataclass(frozen=True)
class MarketScopeAssessment:
    schema_version: str
    status: str
    classification: str
    checked_at_utc: str
    checked_at_kst: str
    raw_result_id: str
    raw_result_path: str
    raw_status: str
    raw_price_difference_count: int
    comparable_scope_price_conflict_count: int
    scope_incompatible_row_count: int
    historical_scope_status: str
    toss_historical_market_scope: str
    kiwoom_historical_market_scope: str
    scope_incompatible_symbols: tuple[str, ...]
    control_symbols_verified: tuple[str, ...]
    decision_integration_eligible: bool
    automatic_provider_substitution_enabled: bool
    account_api_enabled: bool
    order_api_enabled: bool
    rationale: tuple[str, ...]
    symbols: tuple[SymbolScopeEvidence, ...]
    assessment_id: str


def _load_json(path: Path) -> dict[str, object]:
    try:
        parsed: object = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ScopeAssessmentError(f"cannot read JSON evidence {path}: {exc}") from exc
    if not isinstance(parsed, dict):
        raise ScopeAssessmentError(f"JSON evidence must be an object: {path}")
    return {str(key): value for key, value in parsed.items()}


def _read_csv(path: Path) -> list[dict[str, str]]:
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            return [
                {
                    str(key): "" if value is None else value
                    for key, value in row.items()
                }
                for row in csv.DictReader(handle)
            ]
    except OSError as exc:
        raise ScopeAssessmentError(f"cannot read comparison CSV {path}: {exc}") from exc


def _boolean(value: object, *, field: str) -> bool:
    if isinstance(value, bool):
        return value
    normalized = str(value).strip().casefold()
    if normalized in {"true", "1", "yes"}:
        return True
    if normalized in {"false", "0", "no"}:
        return False
    raise ScopeAssessmentError(f"invalid boolean field {field}: {value}")


def _atomic_json(path: Path, payload: Mapping[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(dict(payload), ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    temporary.replace(path)


def _assessment_id(payload: Mapping[str, object]) -> str:
    canonical = json.dumps(
        dict(payload),
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _scope_role(ticker: str) -> str:
    if ticker in VENUE_VARIABLE_SYMBOLS:
        return "venue_variable_evidence"
    if ticker in KRX_ONLY_CONTROL_SYMBOLS:
        return "krx_only_control"
    return "unclassified"


def _symbol_evidence(
    rows: list[dict[str, str]],
) -> tuple[SymbolScopeEvidence, ...]:
    grouped: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        ticker = row.get("ticker", "").strip()
        if ticker not in EXPECTED_SYMBOLS:
            raise ScopeAssessmentError(f"unexpected comparison ticker: {ticker}")
        grouped[ticker].append(row)
    if tuple(sorted(grouped)) != EXPECTED_SYMBOLS:
        raise ScopeAssessmentError("daily comparison symbol set is incomplete")

    evidence: list[SymbolScopeEvidence] = []
    for ticker in EXPECTED_SYMBOLS:
        ticker_rows = grouped[ticker]
        price_differences = sum(
            not _boolean(row.get("price_match"), field=f"{ticker} price_match")
            for row in ticker_rows
        )
        volume_differences = sum(
            not _boolean(row.get("volume_match"), field=f"{ticker} volume_match")
            for row in ticker_rows
        )
        evidence.append(
            SymbolScopeEvidence(
                ticker=ticker,
                scope_role=_scope_role(ticker),
                rows_compared=len(ticker_rows),
                price_difference_rows=price_differences,
                volume_difference_rows=volume_differences,
                full_series_price_difference=(
                    bool(ticker_rows) and price_differences == len(ticker_rows)
                ),
                full_series_volume_difference=(
                    bool(ticker_rows) and volume_differences == len(ticker_rows)
                ),
            )
        )
    return tuple(evidence)


def _source_scope_contracts(
    result: ConsistencyResult,
) -> tuple[str, str, bool]:
    toss_manifest = _load_json(Path(result.toss_directory) / "manifest.json")
    kiwoom_manifest = _load_json(Path(result.kiwoom_directory) / "manifest.json")

    if toss_manifest.get("provider") != "tossinvest-readonly":
        raise ScopeAssessmentError("unexpected TossInvest provider contract")
    if kiwoom_manifest.get("provider") != "kiwoom_openapi_plus":
        raise ScopeAssessmentError("unexpected Kiwoom provider contract")
    if str(kiwoom_manifest.get("daily_tr_code", "")).strip() != KIWOOM_DAILY_TR_CODE:
        return "unknown", "unknown", False
    if _boolean(
        kiwoom_manifest.get("adjusted_prices"),
        field="Kiwoom adjusted_prices",
    ):
        return "unknown", "unknown", False
    if _boolean(toss_manifest.get("adjusted"), field="Toss adjusted"):
        return "unknown", "unknown", False

    toss_scope = str(
        toss_manifest.get("historical_market_scope", "provider_unspecified_domestic_scope")
    ).strip()
    kiwoom_scope = str(
        kiwoom_manifest.get("historical_market_scope", "krx_opt10081")
    ).strip()
    explicitly_equal = (
        "historical_market_scope" in toss_manifest
        and "historical_market_scope" in kiwoom_manifest
        and toss_scope == kiwoom_scope
    )
    return toss_scope, kiwoom_scope, not explicitly_equal


def _classify_scope(
    result: ConsistencyResult,
    evidence: tuple[SymbolScopeEvidence, ...],
) -> tuple[
    str,
    str,
    tuple[str, ...],
    tuple[str, ...],
    int,
    int,
    tuple[str, ...],
    str,
    str,
]:
    by_ticker = {item.ticker: item for item in evidence}
    toss_scope, kiwoom_scope, source_contract_allows_inference = (
        _source_scope_contracts(result)
    )
    required_days = result.historical_days_required_per_symbol

    venue_pattern = all(
        by_ticker[ticker].rows_compared == required_days
        and by_ticker[ticker].full_series_price_difference
        and by_ticker[ticker].full_series_volume_difference
        for ticker in VENUE_VARIABLE_SYMBOLS
    )
    control_pattern = all(
        by_ticker[ticker].rows_compared == required_days
        and by_ticker[ticker].price_difference_rows == 0
        and by_ticker[ticker].volume_difference_rows == 0
        for ticker in KRX_ONLY_CONTROL_SYMBOLS
    )
    inferred_scope_mismatch = (
        result.status == "failed"
        and venue_pattern
        and control_pattern
        and source_contract_allows_inference
    )

    if inferred_scope_mismatch:
        scope_rows = sum(
            by_ticker[ticker].price_difference_rows
            for ticker in VENUE_VARIABLE_SYMBOLS
        )
        rationale = (
            "Inference: exact OHLCV agrees for the KRX-only control security while "
            "every compared row differs for the venue-variable securities.",
            "The Toss candle contract exposes no venue selector in the stored "
            "evidence, while the Kiwoom series was collected through opt10081.",
            "The two historical series are therefore treated as market-scope "
            "non-equivalent, not as proven provider corruption.",
            "No price tolerance was relaxed and decision integration remains blocked.",
        )
        return (
            "blocked_market_scope_mismatch",
            "inferred_venue_scope_mismatch",
            VENUE_VARIABLE_SYMBOLS,
            KRX_ONLY_CONTROL_SYMBOLS,
            scope_rows,
            0,
            rationale,
            toss_scope,
            kiwoom_scope,
        )

    comparable_conflicts = result.historical_price_conflict_count
    classification = (
        "equivalent_scope_observed"
        if result.status != "failed"
        else "true_or_unresolved_price_conflict"
    )
    rationale = (
        "No strict venue-scope mismatch pattern was established from the local evidence.",
        "Raw completed-session OHLC differences remain fail-closed conflicts.",
    )
    return (
        result.status,
        classification,
        (),
        tuple(
            item.ticker
            for item in evidence
            if item.price_difference_rows == 0 and item.volume_difference_rows == 0
        ),
        0,
        comparable_conflicts,
        rationale,
        toss_scope,
        kiwoom_scope,
    )


def assess_consistency_result(
    result: ConsistencyResult,
    result_path: Path,
    *,
    output_root: Path,
) -> tuple[MarketScopeAssessment, Path]:
    daily_path = result_path.parent / result.daily_comparisons_file
    rows = _read_csv(daily_path)
    evidence = _symbol_evidence(rows)
    raw_difference_count = sum(item.price_difference_rows for item in evidence)
    if raw_difference_count != result.historical_price_conflict_count:
        raise ScopeAssessmentError(
            "raw result conflict count does not match daily comparison evidence"
        )

    (
        status,
        classification,
        scope_symbols,
        verified_controls,
        scope_rows,
        comparable_conflicts,
        rationale,
        toss_scope,
        kiwoom_scope,
    ) = _classify_scope(result, evidence)
    integration_eligible = (
        status == "passed" and bool(result.decision_integration_eligible)
    )
    scope_status = "not_comparable" if scope_symbols else "comparable"

    payload: dict[str, object] = {
        "schema_version": "1.0",
        "status": status,
        "classification": classification,
        "checked_at_utc": result.checked_at_utc,
        "checked_at_kst": result.checked_at_kst,
        "raw_result_id": result.result_id,
        "raw_result_path": str(result_path),
        "raw_status": result.status,
        "raw_price_difference_count": raw_difference_count,
        "comparable_scope_price_conflict_count": comparable_conflicts,
        "scope_incompatible_row_count": scope_rows,
        "historical_scope_status": scope_status,
        "toss_historical_market_scope": toss_scope,
        "kiwoom_historical_market_scope": kiwoom_scope,
        "scope_incompatible_symbols": list(scope_symbols),
        "control_symbols_verified": list(verified_controls),
        "decision_integration_eligible": integration_eligible,
        "automatic_provider_substitution_enabled": False,
        "account_api_enabled": False,
        "order_api_enabled": False,
        "rationale": list(rationale),
        "symbols": [asdict(item) for item in evidence],
    }
    assessment_id = _assessment_id(payload)
    assessment = MarketScopeAssessment(
        schema_version="1.0",
        status=status,
        classification=classification,
        checked_at_utc=result.checked_at_utc,
        checked_at_kst=result.checked_at_kst,
        raw_result_id=result.result_id,
        raw_result_path=str(result_path),
        raw_status=result.status,
        raw_price_difference_count=raw_difference_count,
        comparable_scope_price_conflict_count=comparable_conflicts,
        scope_incompatible_row_count=scope_rows,
        historical_scope_status=scope_status,
        toss_historical_market_scope=toss_scope,
        kiwoom_historical_market_scope=kiwoom_scope,
        scope_incompatible_symbols=scope_symbols,
        control_symbols_verified=verified_controls,
        decision_integration_eligible=integration_eligible,
        automatic_provider_substitution_enabled=False,
        account_api_enabled=False,
        order_api_enabled=False,
        rationale=rationale,
        symbols=evidence,
        assessment_id=assessment_id,
    )
    assessment_path = result_path.parent / "market_scope_assessment.json"
    _atomic_json(assessment_path, asdict(assessment))
    _atomic_json(
        output_root / "latest_market_scope_assessment.json",
        {
            "status": assessment.status,
            "classification": assessment.classification,
            "assessment_id": assessment.assessment_id,
            "assessment_path": str(assessment_path),
            "raw_result_id": assessment.raw_result_id,
            "decision_integration_eligible": False,
            "automatic_provider_substitution_enabled": False,
            "account_api_enabled": False,
            "order_api_enabled": False,
        },
    )
    return assessment, assessment_path


def run_assessed_consistency(
    *,
    output_root: Path,
    required_days: int,
    price_tolerance_won: Decimal,
    live_tolerance_bps: Decimal,
    max_snapshot_age_minutes: int,
    max_capture_gap_seconds: int,
) -> tuple[ConsistencyResult, Path, MarketScopeAssessment, Path]:
    result, result_path = run_consistency_check(
        output_root=output_root,
        required_days=required_days,
        price_tolerance_won=price_tolerance_won,
        live_tolerance_bps=live_tolerance_bps,
        max_snapshot_age_minutes=max_snapshot_age_minutes,
        max_capture_gap_seconds=max_capture_gap_seconds,
    )
    assessment, assessment_path = assess_consistency_result(
        result,
        result_path,
        output_root=output_root,
    )
    return result, result_path, assessment, assessment_path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Cross-check immutable market evidence and classify venue-scope "
            "non-equivalence without relaxing price gates"
        )
    )
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--required-days", type=int, default=20)
    parser.add_argument(
        "--price-tolerance-won",
        type=Decimal,
        default=Decimal(0),
    )
    parser.add_argument(
        "--live-tolerance-bps",
        type=Decimal,
        default=Decimal(50),
    )
    parser.add_argument("--max-snapshot-age-minutes", type=int, default=30)
    parser.add_argument("--max-capture-gap-seconds", type=int, default=60)
    parser.add_argument("--json", action="store_true")
    return parser


def _print_assessment(
    result: ConsistencyResult,
    result_path: Path,
    assessment: MarketScopeAssessment,
    assessment_path: Path,
) -> None:
    label = "PASS"
    if assessment.status == "blocked_market_scope_mismatch":
        label = "BLOCKED"
    elif assessment.status == "failed":
        label = "FAIL"
    print(f"MARKET SOURCE CONSISTENCY: {label}")
    print(f"status: {assessment.status}")
    print(f"classification: {assessment.classification}")
    print(f"historical rows compared: {result.historical_rows_compared}")
    print(f"raw OHLC differences: {assessment.raw_price_difference_count}")
    print(
        "comparable-scope price conflicts: "
        f"{assessment.comparable_scope_price_conflict_count}"
    )
    print(f"scope-incompatible rows: {assessment.scope_incompatible_row_count}")
    print(
        "scope-incompatible symbols: "
        + (", ".join(assessment.scope_incompatible_symbols) or "none")
    )
    print(
        "control symbols verified: "
        + (", ".join(assessment.control_symbols_verified) or "none")
    )
    print(f"historical scope status: {assessment.historical_scope_status}")
    print(f"live quote status: {result.live_quote_status}")
    print(
        "decision integration eligible: "
        f"{assessment.decision_integration_eligible}"
    )
    print("automatic provider substitution: disabled")
    print("account API: disabled")
    print("order API: disabled")
    print(f"scope assessment artifact: {assessment_path}")
    print(f"raw consistency artifact: {result_path}")


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        result, result_path, assessment, assessment_path = run_assessed_consistency(
            output_root=args.output_root,
            required_days=args.required_days,
            price_tolerance_won=args.price_tolerance_won,
            live_tolerance_bps=args.live_tolerance_bps,
            max_snapshot_age_minutes=args.max_snapshot_age_minutes,
            max_capture_gap_seconds=args.max_capture_gap_seconds,
        )
    except (
        ConsistencyError,
        ScopeAssessmentError,
        OSError,
        TypeError,
        ValueError,
    ) as exc:
        print("MARKET SOURCE CONSISTENCY: FAIL", file=sys.stderr)
        print(f"failure: {exc}", file=sys.stderr)
        print("automatic provider substitution: disabled", file=sys.stderr)
        print("account API: disabled", file=sys.stderr)
        print("order API: disabled", file=sys.stderr)
        return 2

    if args.json:
        print(json.dumps(asdict(assessment), ensure_ascii=False, indent=2, sort_keys=True))
    else:
        _print_assessment(result, result_path, assessment, assessment_path)
    return 0 if assessment.status != "failed" and not assessment.status.startswith("blocked") else 2


if __name__ == "__main__":
    raise SystemExit(main())
