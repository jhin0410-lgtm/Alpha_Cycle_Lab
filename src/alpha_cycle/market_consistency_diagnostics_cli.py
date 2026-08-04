"""Explain fail-closed cross-provider market-data conflicts without relaxing gates."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from collections import defaultdict
from collections.abc import Mapping
from dataclasses import dataclass
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
    normalized = str(value).strip().casefold()
    if normalized in {"true", "1", "yes"}:
        return True
    if normalized in {"false", "0", "no"}:
        return False
    raise DiagnosticError(f"invalid boolean {field}: {value}")


def _resolve_path(text: object, *, relative_to: Path) -> Path:
    path = Path(str(text).strip())
    if not str(path):
        raise DiagnosticError("artifact path is empty")
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
        _decimal(row[f"{prefix}_{field}"], field=f"{provider} {field}")
        for field in (*PRICE_FIELDS, "volume")
    )


def _format_decimal(value: Decimal, places: str = "0.000001") -> str:
    return str(value.quantize(Decimal(places)))


def _close_ratio_summary(
    rows: list[dict[str, str]],
) -> tuple[str | None, str | None, bool]:
    ratios: list[Decimal] = []
    for row in rows:
        toss = _decimal(row["toss_close"], field="toss_close")
        kiwoom = _decimal(row["kiwoom_close"], field="kiwoom_close")
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
        row for row in rows if not _boolean(row["price_match"], field="price_match")
    ]
    field_counts: dict[str, int] = {}
    for field in PRICE_FIELDS:
        field_counts[field] = sum(
            _decimal(row[f"toss_{field}"], field=f"toss_{field}")
            != _decimal(row[f"kiwoom_{field}"], field=f"kiwoom_{field}")
            for row in rows
        )
    volume_mismatches = sum(
        not _boolean(row["volume_match"], field="volume_match") for row in rows
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
        for row in sorted(conflict_rows, key=lambda value: value["date"], reverse=True)[:3]
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
    daily_path = result_path.parent / daily_file
    rows = _read_csv(daily_path)
    rows_by_symbol: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        ticker = row.get("ticker", "").strip()
        if not ticker:
            raise DiagnosticError("daily comparison row has no ticker")
        rows_by_symbol[ticker].append(row)
    symbols = tuple(
        _diagnose_symbol(ticker, rows_by_symbol) for ticker in sorted(rows_by_symbol)
    )
    return ConflictDiagnosticReport(
        result_path=str(result_path),
        result_id=result_id,
        status=str(result.get("status", "")).strip(),
        rows_compared=len(rows),
        price_conflicts=sum(symbol.price_conflicts for symbol in symbols),
        volume_mismatches=sum(symbol.volume_mismatches for symbol in symbols),
        symbols=symbols,
    )


def _print_report(report: ConflictDiagnosticReport) -> None:
    print("MARKET SOURCE CONFLICT DIAGNOSTICS")
    print(f"status: {report.status}")
    print(f"result id: {report.result_id}")
    print(f"rows compared: {report.rows_compared}")
    print(f"price conflicts: {report.price_conflicts}")
    print(f"volume mismatches: {report.volume_mismatches}")
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
        description="Explain the latest cross-provider market consistency result."
    )
    parser.add_argument(
        "--pointer",
        type=Path,
        default=DEFAULT_POINTER,
        help="Path to latest_market_consistency.json",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        report = diagnose_latest_consistency(args.pointer)
    except DiagnosticError as exc:
        print(f"MARKET SOURCE CONFLICT DIAGNOSTICS: ERROR\n{exc}")
        return 2
    _print_report(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
