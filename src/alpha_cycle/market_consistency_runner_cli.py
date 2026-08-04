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
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
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
PRICE_FIELDS = ("open", "high", "low", "close")
Ohlcv = tuple[Decimal, Decimal, Decimal, Decimal, Decimal]


class ScopeAssessmentError(ValueError):
    """Expected failure while validating or classifying local evidence."""


@dataclass(frozen=True)
class SymbolScopeEvidence:
    ticker: str
    scope_role: str
    rows_compared: int
    price_difference_rows: int
    tolerance_conflict_rows: int
    volume_difference_rows: int
    full_series_price_difference: bool
    full_series_volume_difference: bool
    possible_kiwoom_symbol: str | None
    possible_symbol_match_rows: int


@dataclass(frozen=True)
class ScopeClassification:
    status: str
    classification: str
    scope_incompatible_symbols: tuple[str, ...]
    control_symbols_verified: tuple[str, ...]
    scope_incompatible_row_count: int
    comparable_scope_price_conflict_count: int
    historical_scope_status: str
    rationale: tuple[str, ...]
    toss_historical_market_scope: str
    kiwoom_historical_market_scope: str


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
    tolerance_conflict_count: int
    comparable_scope_price_conflict_count: int
    scope_incompatible_row_count: int
    historical_scope_status: str
    toss_historical_market_scope: str
    kiwoom_historical_market_scope: str
    scope_incompatible_symbols: tuple[str, ...]
    control_symbols_verified: tuple[str, ...]
    live_quote_status: str
    live_quote_conflict_count: int
    raw_failures: tuple[str, ...]
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


def _decimal(value: object, *, field: str) -> Decimal:
    try:
        parsed = Decimal(str(value).strip().replace(",", ""))
    except InvalidOperation as exc:
        raise ScopeAssessmentError(f"invalid decimal field {field}: {value}") from exc
    if not parsed.is_finite():
        raise ScopeAssessmentError(f"non-finite decimal field {field}: {value}")
    return parsed


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


def _ohlcv(row: Mapping[str, str], provider: str) -> Ohlcv:
    prefix = provider.casefold()
    values = tuple(
        _decimal(row.get(f"{prefix}_{field}"), field=f"{prefix}_{field}")
        for field in (*PRICE_FIELDS, "volume")
    )
    if len(values) != 5:
        raise ScopeAssessmentError("OHLCV evidence is incomplete")
    return values[0], values[1], values[2], values[3], values[4]


def _symbol_evidence(
    rows: list[dict[str, str]],
    result: ConsistencyResult,
) -> tuple[SymbolScopeEvidence, ...]:
    grouped: dict[str, list[dict[str, str]]] = {
        ticker: [] for ticker in EXPECTED_SYMBOLS
    }
    seen: set[tuple[str, str]] = set()
    toss_series: dict[str, dict[str, Ohlcv]] = defaultdict(dict)
    kiwoom_series: dict[str, dict[str, Ohlcv]] = defaultdict(dict)
    tolerance_conflicts = 0
    volume_mismatches = 0

    for row in rows:
        ticker = row.get("ticker", "").strip()
        candle_date = row.get("date", "").strip()
        if ticker not in EXPECTED_SYMBOLS:
            raise ScopeAssessmentError(f"unexpected comparison ticker: {ticker}")
        if not candle_date:
            raise ScopeAssessmentError(f"daily comparison row has no date for {ticker}")
        key = (ticker, candle_date)
        if key in seen:
            raise ScopeAssessmentError(f"duplicate daily comparison row: {key}")
        seen.add(key)

        toss_values = _ohlcv(row, "toss")
        kiwoom_values = _ohlcv(row, "kiwoom")
        toss_series[ticker][candle_date] = toss_values
        kiwoom_series[ticker][candle_date] = kiwoom_values
        grouped[ticker].append(row)
        tolerance_conflicts += not _boolean(
            row.get("price_match"), field=f"{ticker} price_match"
        )
        volume_mismatches += not _boolean(
            row.get("volume_match"), field=f"{ticker} volume_match"
        )

    if len(rows) != result.historical_rows_compared:
        raise ScopeAssessmentError(
            "daily comparison row count does not match the linked raw result"
        )
    if tolerance_conflicts != result.historical_price_conflict_count:
        raise ScopeAssessmentError(
            "tolerance conflict count does not match the linked raw result"
        )
    if volume_mismatches != result.historical_volume_mismatch_count:
        raise ScopeAssessmentError(
            "volume mismatch count does not match the linked raw result"
        )

    evidence: list[SymbolScopeEvidence] = []
    for ticker in EXPECTED_SYMBOLS:
        ticker_rows = grouped[ticker]
        exact_price_differences = 0
        ticker_tolerance_conflicts = 0
        ticker_volume_differences = 0
        for row in ticker_rows:
            toss_values = _ohlcv(row, "toss")
            kiwoom_values = _ohlcv(row, "kiwoom")
            exact_price_differences += toss_values[:4] != kiwoom_values[:4]
            ticker_tolerance_conflicts += not _boolean(
                row.get("price_match"), field=f"{ticker} price_match"
            )
            ticker_volume_differences += toss_values[4] != kiwoom_values[4]

        possible_symbol: str | None = None
        possible_matches = 0
        source_by_date = toss_series[ticker]
        for candidate in EXPECTED_SYMBOLS:
            if candidate == ticker:
                continue
            candidate_by_date = kiwoom_series[candidate]
            shared = set(source_by_date) & set(candidate_by_date)
            matches = sum(
                source_by_date[candle_date] == candidate_by_date[candle_date]
                for candle_date in shared
            )
            if (
                source_by_date
                and len(shared) == len(source_by_date)
                and matches == len(source_by_date)
                and matches > possible_matches
            ):
                possible_symbol = candidate
                possible_matches = matches

        evidence.append(
            SymbolScopeEvidence(
                ticker=ticker,
                scope_role=_scope_role(ticker),
                rows_compared=len(ticker_rows),
                price_difference_rows=exact_price_differences,
                tolerance_conflict_rows=ticker_tolerance_conflicts,
                volume_difference_rows=ticker_volume_differences,
                full_series_price_difference=(
                    bool(ticker_rows)
                    and exact_price_differences == len(ticker_rows)
                ),
                full_series_volume_difference=(
                    bool(ticker_rows)
                    and ticker_volume_differences == len(ticker_rows)
                ),
                possible_kiwoom_symbol=possible_symbol,
                possible_symbol_match_rows=possible_matches,
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
) -> ScopeClassification:
    by_ticker = {item.ticker: item for item in evidence}
    toss_scope, kiwoom_scope, source_contract_allows_inference = (
        _source_scope_contracts(result)
    )
    required_days = result.historical_days_required_per_symbol
    raw_exact_differences = sum(item.price_difference_rows for item in evidence)
    incomplete_symbols = tuple(
        ticker
        for ticker in EXPECTED_SYMBOLS
        if by_ticker[ticker].rows_compared < required_days
    )
    cross_mapping = tuple(
        item.ticker
        for item in evidence
        if item.possible_kiwoom_symbol is not None
    )

    if incomplete_symbols:
        return ScopeClassification(
            status=result.status,
            classification="insufficient_historical_overlap",
            scope_incompatible_symbols=(),
            control_symbols_verified=(),
            scope_incompatible_row_count=0,
            comparable_scope_price_conflict_count=raw_exact_differences,
            historical_scope_status="insufficient_evidence",
            rationale=(
                "The required completed-session overlap is unavailable for: "
                + ", ".join(incomplete_symbols),
                "Venue-scope inference is withheld and decision integration remains blocked.",
            ),
            toss_historical_market_scope=toss_scope,
            kiwoom_historical_market_scope=kiwoom_scope,
        )

    verified_controls = tuple(
        ticker
        for ticker in KRX_ONLY_CONTROL_SYMBOLS
        if by_ticker[ticker].price_difference_rows == 0
        and by_ticker[ticker].volume_difference_rows == 0
    )
    if cross_mapping:
        mappings = ", ".join(
            f"{ticker}->{by_ticker[ticker].possible_kiwoom_symbol}"
            for ticker in cross_mapping
        )
        return ScopeClassification(
            status=result.status,
            classification="possible_symbol_mapping_conflict",
            scope_incompatible_symbols=(),
            control_symbols_verified=verified_controls,
            scope_incompatible_row_count=0,
            comparable_scope_price_conflict_count=raw_exact_differences,
            historical_scope_status="unresolved_mapping",
            rationale=(
                f"Exact cross-symbol OHLCV matches were detected: {mappings}.",
                "Venue-scope inference is withheld until symbol association is resolved.",
            ),
            toss_historical_market_scope=toss_scope,
            kiwoom_historical_market_scope=kiwoom_scope,
        )

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
        return ScopeClassification(
            status="blocked_market_scope_mismatch",
            classification="inferred_venue_scope_mismatch",
            scope_incompatible_symbols=VENUE_VARIABLE_SYMBOLS,
            control_symbols_verified=KRX_ONLY_CONTROL_SYMBOLS,
            scope_incompatible_row_count=scope_rows,
            comparable_scope_price_conflict_count=0,
            historical_scope_status="not_comparable",
            rationale=(
                "Inference: exact OHLCV agrees for the KRX-only control security while "
                "every compared row differs for the venue-variable securities.",
                "The Toss candle contract exposes no venue selector in the stored "
                "evidence, while the Kiwoom series was collected through opt10081.",
                "No cross-symbol exact mapping was detected.",
                "The two historical series are treated as market-scope non-equivalent; "
                "no price tolerance was relaxed and decision integration remains blocked.",
            ),
            toss_historical_market_scope=toss_scope,
            kiwoom_historical_market_scope=kiwoom_scope,
        )

    if raw_exact_differences:
        return ScopeClassification(
            status=result.status,
            classification="true_or_unresolved_price_conflict",
            scope_incompatible_symbols=(),
            control_symbols_verified=verified_controls,
            scope_incompatible_row_count=0,
            comparable_scope_price_conflict_count=raw_exact_differences,
            historical_scope_status="comparable",
            rationale=(
                "No strict venue-scope mismatch or cross-symbol mapping pattern was established.",
                "Exact completed-session OHLC differences remain fail-closed conflicts.",
            ),
            toss_historical_market_scope=toss_scope,
            kiwoom_historical_market_scope=kiwoom_scope,
        )

    if result.live_quote_status == "conflict" or result.live_quote_conflict_count:
        classification = "live_quote_conflict"
        rationale = (
            "Completed-session historical OHLC values match exactly.",
            "Fresh live quotes conflict within the configured synchronization window; "
            "the failure is live-only and remains fail-closed.",
        )
    elif result.status == "failed":
        classification = "non_price_validation_failure"
        rationale = (
            "Completed-session historical OHLC values match exactly.",
            "The raw check failed for a non-historical-price reason recorded in raw_failures.",
        )
    else:
        classification = "equivalent_scope_observed"
        rationale = (
            "Completed-session historical OHLC values match exactly for all expected symbols.",
            "Live evidence remains governed by its independent freshness and tolerance status.",
        )
    return ScopeClassification(
        status=result.status,
        classification=classification,
        scope_incompatible_symbols=(),
        control_symbols_verified=verified_controls,
        scope_incompatible_row_count=0,
        comparable_scope_price_conflict_count=0,
        historical_scope_status="comparable",
        rationale=rationale,
        toss_historical_market_scope=toss_scope,
        kiwoom_historical_market_scope=kiwoom_scope,
    )


def _write_failed_assessment_pointer(
    *,
    output_root: Path,
    failure: BaseException,
    result: ConsistencyResult | None = None,
    result_path: Path | None = None,
) -> None:
    payload: dict[str, object] = {
        "status": "failed_assessment",
        "classification": "assessment_error",
        "assessment_id": None,
        "assessment_path": None,
        "raw_result_id": None if result is None else result.result_id,
        "raw_result_path": None if result_path is None else str(result_path),
        "checked_at_utc": datetime.now(UTC).isoformat(),
        "failure": str(failure),
        "decision_integration_eligible": False,
        "automatic_provider_substitution_enabled": False,
        "account_api_enabled": False,
        "order_api_enabled": False,
    }
    try:
        _atomic_json(output_root / "latest_market_scope_assessment.json", payload)
    except OSError:
        return


def assess_consistency_result(
    result: ConsistencyResult,
    result_path: Path,
    *,
    output_root: Path,
) -> tuple[MarketScopeAssessment, Path]:
    daily_path = result_path.parent / result.daily_comparisons_file
    rows = _read_csv(daily_path)
    evidence = _symbol_evidence(rows, result)
    raw_difference_count = sum(item.price_difference_rows for item in evidence)
    tolerance_conflicts = sum(item.tolerance_conflict_rows for item in evidence)
    classification = _classify_scope(result, evidence)
    integration_eligible = (
        classification.status == "passed"
        and bool(result.decision_integration_eligible)
    )

    payload: dict[str, object] = {
        "schema_version": "1.1",
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
    assessment_id = _assessment_id(payload)
    assessment = MarketScopeAssessment(
        schema_version="1.1",
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
    _atomic_json(assessment_path, asdict(assessment))
    _atomic_json(
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


def run_assessed_consistency(
    *,
    output_root: Path,
    required_days: int,
    price_tolerance_won: Decimal,
    live_tolerance_bps: Decimal,
    max_snapshot_age_minutes: int,
    max_capture_gap_seconds: int,
) -> tuple[ConsistencyResult, Path, MarketScopeAssessment, Path]:
    result: ConsistencyResult | None = None
    result_path: Path | None = None
    try:
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
    except (ConsistencyError, ScopeAssessmentError, OSError, TypeError, ValueError) as exc:
        _write_failed_assessment_pointer(
            output_root=output_root,
            failure=exc,
            result=result,
            result_path=result_path,
        )
        raise
    assert result is not None
    assert result_path is not None
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
    if assessment.status.startswith("blocked"):
        label = "BLOCKED"
    elif assessment.status.startswith("failed"):
        label = "FAIL"
    print(f"MARKET SOURCE CONSISTENCY: {label}")
    print(f"status: {assessment.status}")
    print(f"classification: {assessment.classification}")
    print(f"historical rows compared: {result.historical_rows_compared}")
    print(f"raw OHLC differences: {assessment.raw_price_difference_count}")
    print(f"tolerance conflicts: {assessment.tolerance_conflict_count}")
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
    print(f"live quote status: {assessment.live_quote_status}")
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
        if args.json:
            print(
                json.dumps(
                    {
                        "status": "failed_assessment",
                        "classification": "assessment_error",
                        "failure": str(exc),
                        "decision_integration_eligible": False,
                        "automatic_provider_substitution_enabled": False,
                        "account_api_enabled": False,
                        "order_api_enabled": False,
                    },
                    ensure_ascii=False,
                    indent=2,
                    sort_keys=True,
                )
            )
        else:
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
    return (
        0
        if not assessment.status.startswith(("failed", "blocked"))
        else 2
    )


if __name__ == "__main__":
    raise SystemExit(main())
