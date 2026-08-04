"""Explain fail-closed cross-provider market-data conflicts without relaxing gates."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from collections import defaultdict
from collections.abc import Mapping
from dataclasses import asdict, dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path
from statistics import median

DEFAULT_POINTER = Path("data/private/live-research/latest_market_consistency.json")
PRICE_FIELDS = ("open", "high", "low", "close")


class DiagnosticError(ValueError):
    """Expected diagnostic-artifact validation failure."""


@dataclass(frozen=True)
class SymbolConflictDiagnostics:
    ticker: str
    rows_compared: int
    price_conflicts: int
    volume_mismatches: int
    open_conflicts: int
    high_conflicts: int
    low_conflicts: int
    close_conflicts: int
    median_close_ratio: str | None
    close_ratio_max_deviation_bps: str | None
    suspected_patterns: tuple[str, ...]
    possible_kiwoom_symbol: str | None
    possible_symbol_match_rows: int
    representative_rows: tuple[str, ...]


@dataclass(frozen=True)
class ConflictDiagnosticReport:
    result_path: str
    result_id: str
    status: str
    rows_compared: int
    price_conflicts: int
    volume_mismatches: int
    live_quote_status: str
    live_quote_comparable_count: int
    live_quote_conflict_count: int
    raw_failures: tuple[str, ...]
    symbols: tuple[SymbolConflictDiagnostics, ...]


def _load_json(path: Path) -> dict[str, object]:
    try:
        parsed: object = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise DiagnosticError(f"cannot read diagnostic JSON {path}: {exc}") from exc
    if not isinstance(parsed, dict):
        raise DiagnosticError(f"diagnostic JSON must be an object: {path}")
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
        raise DiagnosticError(f"cannot read comparison CSV {path}: {exc}") from exc


def _decimal(value: object, *, field: str) -> Decimal:
    try:
        parsed = Decimal(str(value).strip().replace(",", ""))
    except InvalidOperation as exc:
        raise DiagnosticError(f"invalid decimal {field}: {value}") from exc
    if not parsed.is_finite():
        raise DiagnosticError(f"non-finite decimal {field}: {value}")
    return parsed


def _boolean(value: object, *, field: str) -> bool:
    if isinstance(value, bool):
        return value
    normalized = str(value).strip().casefold()
    if normalized in {"true", "1", "yes"}:
        return True
    if normalized in {"false", "0", "no"}:
        return False
    raise DiagnosticError(f"invalid boolean {field}: {value}")


def _integer(value: object, *, field: str) -> int:
    text = str(value).strip()
    try:
        parsed = int(text)
    except ValueError as exc:
        raise DiagnosticError(f"invalid integer {field}: {value}") from exc
    if parsed < 0:
        raise DiagnosticError(f"negative integer {field}: {value}")
    return parsed


def _string_tuple(value: object, *, field: str) -> tuple[str, ...]:
    if not isinstance(value, list):
        raise DiagnosticError(f"{field} must be a list")
    return tuple(str(item) for item in value)


def _resolve_path(text: object, *, relative_to: Path) -> Path:
    raw = str(text).strip()
    if not raw:
        raise DiagnosticError("artifact path is empty")
    path = Path(raw)
    if not path.is_absolute():
        path = relative_to / path
    return path.resolve()


def _result_id(payload: Mapping[str, object]) -> str:
    canonical_payload = dict(payload)
    canonical_payload.pop("result_id", None)
    canonical = json.dumps(
        canonical_payload,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _validate_linkage(
    pointer: Mapping[str, object],
    result: Mapping[str, object],
) -> str:
    pointer_id = str(pointer.get("result_id", "")).strip()
    result_id = str(result.get("result_id", "")).strip()
    if not pointer_id or pointer_id != result_id:
        raise DiagnosticError("latest pointer and consistency result IDs differ")
    computed = _result_id(result)
    if computed != result_id:
        raise DiagnosticError("consistency result ID does not match canonical payload")
    if _boolean(
        result.get("automatic_provider_substitution_enabled"),
        field="automatic_provider_substitution_enabled",
    ):
        raise DiagnosticError("automatic provider substitution must remain disabled")
    for field in ("account_api_enabled", "order_api_enabled"):
        if _boolean(result.get(field), field=field):
            raise DiagnosticError(f"{field} must remain disabled")
    return result_id


def _ohlcv(row: Mapping[str, str], provider: str) -> tuple[Decimal, ...]:
    prefix = provider.casefold()
    return tuple(
        _decimal(row.get(f"{prefix}_{field}"), field=f"{provider} {field}")
        for field in (*PRICE_FIELDS, "volume")
    )


def _format_decimal(value: Decimal, places: str = "0.000001") -> str:
    return str(value.quantize(Decimal(places)))


def _close_ratio_summary(
    rows: list[dict[str, str]],
) -> tuple[str | None, str | None, bool]:
    ratios: list[Decimal] = []
    for row in rows:
        toss = _decimal(row.get("toss_close"), field="toss_close")
        kiwoom = _decimal(row.get("kiwoom_close"), field="kiwoom_close")
        if toss != 0:
            ratios.append(kiwoom / toss)
    if not ratios:
        return None, None, False
    center = median(ratios)
    if center == 0:
        return _format_decimal(center), None, False
    max_deviation = max(abs(ratio / center - Decimal(1)) for ratio in ratios)
    deviation_bps = max_deviation * Decimal(10000)
    stable = deviation_bps <= Decimal(1)
    return (
        _format_decimal(center),
        _format_decimal(deviation_bps, "0.0001"),
        stable,
    )


def _possible_symbol_mapping(
    ticker: str,
    rows_by_symbol: Mapping[str, list[dict[str, str]]],
) -> tuple[str | None, int]:
    source_rows = rows_by_symbol[ticker]
    source_by_date = {row["date"]: _ohlcv(row, "toss") for row in source_rows}
    same_matches = sum(
        source_by_date.get(row["date"]) == _ohlcv(row, "kiwoom")
        for row in source_rows
    )
    best_symbol: str | None = None
    best_matches = same_matches
    for candidate, candidate_rows in rows_by_symbol.items():
        if candidate == ticker:
            continue
        candidate_by_date = {
            row["date"]: _ohlcv(row, "kiwoom") for row in candidate_rows
        }
        matches = sum(
            source_value == candidate_by_date.get(candle_date)
            for candle_date, source_value in source_by_date.items()
        )
        if matches > best_matches:
            best_symbol = candidate
            best_matches = matches
    threshold = max(3, int(len(source_rows) * 0.8))
    if best_symbol is None or best_matches < threshold:
        return None, 0
    return best_symbol, best_matches


def _representative_row(row: Mapping[str, str]) -> str:
    toss = "/".join(row[f"toss_{field}"] for field in PRICE_FIELDS)
    kiwoom = "/".join(row[f"kiwoom_{field}"] for field in PRICE_FIELDS)
    return (
        f"{row['date']} toss={toss} kiwoom={kiwoom} "
        f"max_diff_won={row['max_price_difference_won']} "
        f"volume={row['toss_volume']}/{row['kiwoom_volume']}"
    )


def _diagnose_symbol(
    ticker: str,
    rows_by_symbol: Mapping[str, list[dict[str, str]]],
) -> SymbolConflictDiagnostics:
    rows = rows_by_symbol[ticker]
    conflict_rows = [
        row
        for row in rows
        if not _boolean(row.get("price_match"), field="price_match")
    ]
    field_counts: dict[str, int] = {}
    for field in PRICE_FIELDS:
        field_counts[field] = sum(
            _decimal(row.get(f"toss_{field}"), field=f"toss_{field}")
            != _decimal(row.get(f"kiwoom_{field}"), field=f"kiwoom_{field}")
            for row in rows
        )
    volume_mismatches = sum(
        not _boolean(row.get("volume_match"), field="volume_match") for row in rows
    )
    ratio, ratio_deviation, stable_ratio = _close_ratio_summary(conflict_rows)
    possible_symbol, mapping_rows = _possible_symbol_mapping(ticker, rows_by_symbol)

    patterns: list[str] = []
    if conflict_rows and len(conflict_rows) == len(rows):
        patterns.append("full_series_price_mismatch")
    if rows and volume_mismatches == len(rows):
        patterns.append("full_series_volume_mismatch")
    if stable_ratio and ratio is not None and Decimal(ratio) != Decimal(1):
        patterns.append("stable_scale_or_adjustment_ratio")
    if possible_symbol is not None:
        patterns.append("possible_symbol_mapping_conflict")
    if not patterns and conflict_rows:
        patterns.append("sporadic_price_conflict")
    if not conflict_rows and volume_mismatches:
        patterns.append("volume_definition_only")

    representatives = tuple(
        _representative_row(row)
        for row in sorted(
            conflict_rows,
            key=lambda value: value["date"],
            reverse=True,
        )[:3]
    )
    return SymbolConflictDiagnostics(
        ticker=ticker,
        rows_compared=len(rows),
        price_conflicts=len(conflict_rows),
        volume_mismatches=volume_mismatches,
        open_conflicts=field_counts["open"],
        high_conflicts=field_counts["high"],
        low_conflicts=field_counts["low"],
        close_conflicts=field_counts["close"],
        median_close_ratio=ratio,
        close_ratio_max_deviation_bps=ratio_deviation,
        suspected_patterns=tuple(patterns),
        possible_kiwoom_symbol=possible_symbol,
        possible_symbol_match_rows=mapping_rows,
        representative_rows=representatives,
    )


def _validate_daily_aggregates(
    result: Mapping[str, object],
    rows: list[dict[str, str]],
    symbols: tuple[SymbolConflictDiagnostics, ...],
) -> None:
    expected = set(_string_tuple(result.get("expected_symbols"), field="expected_symbols"))
    actual = {symbol.ticker for symbol in symbols}
    if not actual.issubset(expected):
        raise DiagnosticError("daily comparison contains an unexpected symbol")
    if len(rows) != _integer(
        result.get("historical_rows_compared"), field="historical_rows_compared"
    ):
        raise DiagnosticError("daily comparison row count differs from linked result")
    conflicts = sum(symbol.price_conflicts for symbol in symbols)
    if conflicts != _integer(
        result.get("historical_price_conflict_count"),
        field="historical_price_conflict_count",
    ):
        raise DiagnosticError("daily price conflict count differs from linked result")
    mismatches = sum(symbol.volume_mismatches for symbol in symbols)
    if mismatches != _integer(
        result.get("historical_volume_mismatch_count"),
        field="historical_volume_mismatch_count",
    ):
        raise DiagnosticError("daily volume mismatch count differs from linked result")


def _validate_live_aggregates(
    result: Mapping[str, object],
    result_path: Path,
) -> tuple[int, int]:
    quote_file = str(result.get("quote_comparisons_file", "")).strip()
    if not quote_file:
        raise DiagnosticError("consistency result has no live quote comparison file")
    rows = _read_csv(result_path.parent / quote_file)
    comparable = sum(
        _boolean(row.get("comparable"), field="live comparable") for row in rows
    )
    conflicts = sum(
        str(row.get("within_tolerance", "")).strip().casefold() == "false"
        for row in rows
    )
    if comparable != _integer(
        result.get("live_quote_comparable_count"), field="live_quote_comparable_count"
    ):
        raise DiagnosticError("live comparable count differs from linked result")
    if conflicts != _integer(
        result.get("live_quote_conflict_count"), field="live_quote_conflict_count"
    ):
        raise DiagnosticError("live conflict count differs from linked result")
    return comparable, conflicts


def diagnose_latest_consistency(
    pointer_path: Path = DEFAULT_POINTER,
) -> ConflictDiagnosticReport:
    pointer_path = pointer_path.resolve()
    pointer = _load_json(pointer_path)
    result_path = _resolve_path(pointer.get("result_path"), relative_to=Path.cwd())
    result = _load_json(result_path)
    result_id = _validate_linkage(pointer, result)
    daily_file = str(result.get("daily_comparisons_file", "")).strip()
    if not daily_file:
        raise DiagnosticError("consistency result has no daily comparison file")
    rows = _read_csv(result_path.parent / daily_file)
    rows_by_symbol: dict[str, list[dict[str, str]]] = defaultdict(list)
    seen: set[tuple[str, str]] = set()
    for row in rows:
        ticker = row.get("ticker", "").strip()
        candle_date = row.get("date", "").strip()
        if not ticker or not candle_date:
            raise DiagnosticError("daily comparison row has no ticker or date")
        key = (ticker, candle_date)
        if key in seen:
            raise DiagnosticError(f"duplicate daily comparison row: {key}")
        seen.add(key)
        rows_by_symbol[ticker].append(row)
    symbols = tuple(
        _diagnose_symbol(ticker, rows_by_symbol) for ticker in sorted(rows_by_symbol)
    )
    _validate_daily_aggregates(result, rows, symbols)
    live_comparable, live_conflicts = _validate_live_aggregates(result, result_path)
    failures = _string_tuple(result.get("failures"), field="failures")
    return ConflictDiagnosticReport(
        result_path=str(result_path),
        result_id=result_id,
        status=str(result.get("status", "")).strip(),
        rows_compared=len(rows),
        price_conflicts=sum(symbol.price_conflicts for symbol in symbols),
        volume_mismatches=sum(symbol.volume_mismatches for symbol in symbols),
        live_quote_status=str(result.get("live_quote_status", "")).strip(),
        live_quote_comparable_count=live_comparable,
        live_quote_conflict_count=live_conflicts,
        raw_failures=failures,
        symbols=symbols,
    )


def _print_report(report: ConflictDiagnosticReport) -> None:
    print("MARKET SOURCE CONFLICT DIAGNOSTICS")
    print(f"status: {report.status}")
    print(f"result id: {report.result_id}")
    print(f"rows compared: {report.rows_compared}")
    print(f"price conflicts: {report.price_conflicts}")
    print(f"volume mismatches: {report.volume_mismatches}")
    print(f"live quote status: {report.live_quote_status}")
    print(f"live comparable quotes: {report.live_quote_comparable_count}")
    print(f"live quote conflicts: {report.live_quote_conflict_count}")
    if report.raw_failures:
        print("raw failures: " + " | ".join(report.raw_failures))
    for symbol in report.symbols:
        print("")
        print(
            f"{symbol.ticker}: rows={symbol.rows_compared} "
            f"price_conflicts={symbol.price_conflicts} "
            f"volume_mismatches={symbol.volume_mismatches}"
        )
        print(
            "  field conflicts: "
            f"open={symbol.open_conflicts} high={symbol.high_conflicts} "
            f"low={symbol.low_conflicts} close={symbol.close_conflicts}"
        )
        if symbol.median_close_ratio is not None:
            print(
                "  kiwoom/toss close ratio: "
                f"median={symbol.median_close_ratio} "
                f"max_deviation_bps={symbol.close_ratio_max_deviation_bps}"
            )
        print(
            "  suspected patterns: "
            + (", ".join(symbol.suspected_patterns) or "none")
        )
        if symbol.possible_kiwoom_symbol is not None:
            print(
                "  possible symbol mapping: "
                f"Toss {symbol.ticker} -> Kiwoom {symbol.possible_kiwoom_symbol} "
                f"({symbol.possible_symbol_match_rows}/{symbol.rows_compared} exact OHLCV rows)"
            )
        for representative in symbol.representative_rows:
            print(f"  example: {representative}")
    print("")
    print("price tolerance was not relaxed; provider substitution remains disabled")
    print(f"diagnosed artifact: {report.result_path}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Explain a linked cross-provider market consistency result."
    )
    parser.add_argument(
        "--pointer",
        type=Path,
        default=DEFAULT_POINTER,
        help="Path to latest_market_consistency.json",
    )
    parser.add_argument("--json", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        report = diagnose_latest_consistency(args.pointer)
    except DiagnosticError as exc:
        if args.json:
            print(json.dumps({"status": "error", "failure": str(exc)}, sort_keys=True))
        else:
            print(f"MARKET SOURCE CONFLICT DIAGNOSTICS: ERROR\n{exc}")
        return 2
    if args.json:
        print(json.dumps(asdict(report), ensure_ascii=False, indent=2, sort_keys=True))
    else:
        _print_report(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
