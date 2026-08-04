"""Fail-closed consistency checks for immutable TossInvest and Kiwoom evidence."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import shutil
import sys
from collections.abc import Iterable, Mapping
from dataclasses import asdict, dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from pathlib import Path
from zoneinfo import ZoneInfo

KOREA_TZ = ZoneInfo("Asia/Seoul")
DEFAULT_OUTPUT_ROOT = Path("data/private/live-research")
EXPECTED_SYMBOLS = ("000660", "005930", "005935")
TOSS_PROVIDER = "tossinvest-readonly"
KIWOOM_PROVIDER = "kiwoom_openapi_plus"
CandleValues = tuple[Decimal, Decimal, Decimal, Decimal, Decimal]


class ConsistencyError(ValueError):
    """Expected local evidence-validation failure."""


@dataclass(frozen=True)
class SnapshotEvidence:
    provider: str
    snapshot_id: str
    captured_at: datetime
    directory: Path
    prices: dict[str, Decimal]
    candles: dict[tuple[str, date], CandleValues]


@dataclass(frozen=True)
class DailyComparison:
    ticker: str
    date: str
    toss_open: str
    kiwoom_open: str
    toss_high: str
    kiwoom_high: str
    toss_low: str
    kiwoom_low: str
    toss_close: str
    kiwoom_close: str
    toss_volume: str
    kiwoom_volume: str
    max_price_difference_won: str
    price_match: bool
    volume_match: bool
    volume_difference_bps: str | None


@dataclass(frozen=True)
class QuoteComparison:
    ticker: str
    toss_price: str
    kiwoom_price: str
    absolute_difference_won: str
    difference_bps: str
    capture_gap_seconds: str
    comparable: bool
    within_tolerance: bool | None
    reason: str


@dataclass(frozen=True)
class ConsistencyResult:
    schema_version: str
    status: str
    checked_at_utc: str
    checked_at_kst: str
    expected_symbols: tuple[str, ...]
    toss_snapshot_id: str
    toss_captured_at: str
    toss_snapshot_age_seconds: float
    toss_directory: str
    toss_resolution_source: str
    kiwoom_snapshot_id: str
    kiwoom_captured_at: str
    kiwoom_snapshot_age_seconds: float
    kiwoom_directory: str
    historical_cutoff_date_exclusive: str
    historical_days_required_per_symbol: int
    historical_rows_compared: int
    historical_symbols_passed: tuple[str, ...]
    historical_price_conflict_count: int
    historical_volume_mismatch_count: int
    live_quote_status: str
    live_quote_comparable_count: int
    live_quote_conflict_count: int
    live_capture_gap_seconds: float
    decision_integration_eligible: bool
    automatic_provider_substitution_enabled: bool
    account_api_enabled: bool
    order_api_enabled: bool
    warnings: tuple[str, ...]
    failures: tuple[str, ...]
    daily_comparisons_file: str
    quote_comparisons_file: str
    result_id: str


def _load_json(path: Path) -> dict[str, object]:
    try:
        parsed: object = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ConsistencyError(f"cannot read JSON evidence {path}: {exc}") from exc
    if not isinstance(parsed, dict):
        raise ConsistencyError(f"JSON evidence must be an object: {path}")
    return {str(key): value for key, value in parsed.items()}


def _read_csv(path: Path) -> list[dict[str, str]]:
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            rows: list[dict[str, str]] = []
            for raw in csv.DictReader(handle):
                rows.append(
                    {
                        str(key): "" if value is None else value
                        for key, value in raw.items()
                    }
                )
            return rows
    except OSError as exc:
        raise ConsistencyError(f"cannot read CSV evidence {path}: {exc}") from exc


def _require_fields(
    row: Mapping[str, object],
    fields: Iterable[str],
    *,
    source: str,
) -> None:
    missing = [
        field
        for field in fields
        if field not in row or not str(row[field]).strip()
    ]
    if missing:
        raise ConsistencyError(f"missing fields in {source}: {', '.join(missing)}")


def _parse_datetime(value: object, *, field: str) -> datetime:
    text = str(value).strip()
    if not text:
        raise ConsistencyError(f"missing datetime field: {field}")
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ConsistencyError(f"invalid datetime field {field}: {text}") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ConsistencyError(f"datetime field must be timezone-aware: {field}")
    return parsed


def _decimal(value: object, *, field: str) -> Decimal:
    text = str(value).strip().replace(",", "")
    try:
        parsed = Decimal(text)
    except InvalidOperation as exc:
        raise ConsistencyError(f"invalid decimal field {field}: {value}") from exc
    if not parsed.is_finite():
        raise ConsistencyError(f"non-finite decimal field {field}: {value}")
    return parsed


def _boolean(value: object, *, field: str) -> bool:
    if isinstance(value, bool):
        return value
    normalized = str(value).strip().casefold()
    if normalized in {"true", "1", "yes"}:
        return True
    if normalized in {"false", "0", "no"}:
        return False
    raise ConsistencyError(f"invalid boolean field {field}: {value}")


def _validate_symbols(manifest: Mapping[str, object], *, provider: str) -> None:
    raw = manifest.get("symbols")
    if not isinstance(raw, list):
        raise ConsistencyError(f"{provider} manifest symbols must be a list")
    symbols = tuple(sorted(str(value).strip() for value in raw))
    if symbols != EXPECTED_SYMBOLS:
        raise ConsistencyError(
            f"{provider} symbol set mismatch: expected {EXPECTED_SYMBOLS}, got {symbols}"
        )


def _snapshot_candidates(root: Path) -> list[tuple[datetime, Path]]:
    candidates: list[tuple[datetime, Path]] = []
    if not root.is_dir():
        return candidates
    for path in root.glob("*/manifest.json"):
        if path.parent.name.startswith("."):
            continue
        try:
            manifest = _load_json(path)
            captured = _parse_datetime(
                manifest.get("captured_at"),
                field="captured_at",
            )
        except ConsistencyError:
            continue
        candidates.append((captured, path.parent))
    return sorted(candidates, key=lambda item: item[0], reverse=True)


def _resolve_toss_directory(output_root: Path) -> tuple[Path, str]:
    latest_path = output_root / "latest_run.json"
    if latest_path.is_file():
        latest = _load_json(latest_path)
        directory_text = str(latest.get("market_directory", "")).strip()
        if latest.get("status") == "completed" and directory_text:
            directory = Path(directory_text)
            if (directory / "manifest.json").is_file():
                return directory, "latest_run"
    candidates = _snapshot_candidates(output_root / "market-intelligence")
    if not candidates:
        raise ConsistencyError("no immutable TossInvest market snapshot is available")
    return candidates[0][1], "latest_immutable_snapshot"


def _resolve_kiwoom_directory(output_root: Path) -> Path:
    pointer_path = (
        output_root
        / "kiwoom-openapi-plus-market"
        / "latest_market_export.json"
    )
    pointer = _load_json(pointer_path)
    if pointer.get("status") != "completed":
        raise ConsistencyError("latest Kiwoom market export is not completed")
    directory_text = str(pointer.get("export_directory", "")).strip()
    if not directory_text:
        raise ConsistencyError("Kiwoom latest pointer has no export_directory")
    directory = Path(directory_text)
    if not directory.is_absolute():
        directory = Path.cwd() / directory
    manifest_path = directory / "manifest.json"
    if not manifest_path.is_file():
        raise ConsistencyError("Kiwoom export directory has no manifest.json")
    manifest = _load_json(manifest_path)
    if str(pointer.get("snapshot_id", "")).strip() != str(
        manifest.get("snapshot_id", "")
    ).strip():
        raise ConsistencyError("Kiwoom pointer and manifest snapshot IDs differ")
    return directory


def _load_toss(directory: Path) -> SnapshotEvidence:
    manifest = _load_json(directory / "manifest.json")
    if manifest.get("provider") != TOSS_PROVIDER:
        raise ConsistencyError("Toss snapshot provider is not tossinvest-readonly")
    if manifest.get("interval") != "1d":
        raise ConsistencyError("Toss snapshot interval is not 1d")
    if _boolean(manifest.get("adjusted"), field="Toss adjusted"):
        raise ConsistencyError("Toss snapshot uses adjusted prices")
    if _boolean(
        manifest.get("order_api_enabled"),
        field="Toss order_api_enabled",
    ):
        raise ConsistencyError("Toss snapshot unexpectedly enables order API")
    _validate_symbols(manifest, provider="TossInvest")
    snapshot_id = str(manifest.get("snapshot_id", "")).strip()
    if not snapshot_id:
        raise ConsistencyError("Toss manifest has no snapshot_id")
    captured_at = _parse_datetime(
        manifest.get("captured_at"),
        field="Toss captured_at",
    )

    prices: dict[str, Decimal] = {}
    for row in _read_csv(directory / "prices.csv"):
        _require_fields(
            row,
            ("symbol", "timestamp", "last_price", "currency"),
            source="prices.csv",
        )
        symbol = row["symbol"].strip()
        if row["currency"].strip().upper() != "KRW":
            raise ConsistencyError(f"Toss currency is not KRW for {symbol}")
        _parse_datetime(
            row["timestamp"],
            field=f"Toss price timestamp {symbol}",
        )
        prices[symbol] = _decimal(
            row["last_price"],
            field=f"Toss last_price {symbol}",
        )

    candles: dict[tuple[str, date], CandleValues] = {}
    required = (
        "symbol",
        "timestamp",
        "open",
        "high",
        "low",
        "close",
        "volume",
        "currency",
        "interval",
        "adjusted",
    )
    for row in _read_csv(directory / "candles.csv"):
        _require_fields(row, required, source="candles.csv")
        symbol = row["symbol"].strip()
        if row["currency"].strip().upper() != "KRW":
            raise ConsistencyError(f"Toss candle currency is not KRW for {symbol}")
        if row["interval"].strip() != "1d":
            raise ConsistencyError(f"Toss candle interval is not 1d for {symbol}")
        if _boolean(row["adjusted"], field=f"Toss adjusted {symbol}"):
            raise ConsistencyError(f"Toss candle is adjusted for {symbol}")
        timestamp = _parse_datetime(
            row["timestamp"],
            field=f"Toss candle timestamp {symbol}",
        )
        key = (symbol, timestamp.astimezone(KOREA_TZ).date())
        if key in candles:
            raise ConsistencyError(f"duplicate Toss candle for {key}")
        candles[key] = (
            _decimal(row["open"], field="Toss open"),
            _decimal(row["high"], field="Toss high"),
            _decimal(row["low"], field="Toss low"),
            _decimal(row["close"], field="Toss close"),
            _decimal(row["volume"], field="Toss volume"),
        )
    if tuple(sorted(prices)) != EXPECTED_SYMBOLS:
        raise ConsistencyError("Toss prices.csv symbol set is incomplete")
    return SnapshotEvidence(
        provider=TOSS_PROVIDER,
        snapshot_id=snapshot_id,
        captured_at=captured_at,
        directory=directory,
        prices=prices,
        candles=candles,
    )


def _load_kiwoom(directory: Path) -> SnapshotEvidence:
    manifest = _load_json(directory / "manifest.json")
    if (
        manifest.get("status") != "completed"
        or manifest.get("provider") != KIWOOM_PROVIDER
    ):
        raise ConsistencyError("Kiwoom manifest is not a completed export")
    if _boolean(
        manifest.get("adjusted_prices"),
        field="Kiwoom adjusted_prices",
    ):
        raise ConsistencyError("Kiwoom snapshot uses adjusted prices")
    for field in ("account_api_enabled", "order_api_enabled"):
        if _boolean(manifest.get(field), field=f"Kiwoom {field}"):
            raise ConsistencyError(f"Kiwoom manifest unexpectedly enables {field}")
    _validate_symbols(manifest, provider="Kiwoom")
    snapshot_id = str(manifest.get("snapshot_id", "")).strip()
    if not snapshot_id:
        raise ConsistencyError("Kiwoom manifest has no snapshot_id")
    captured_at = _parse_datetime(
        manifest.get("captured_at_utc"),
        field="Kiwoom captured_at_utc",
    )

    prices: dict[str, Decimal] = {}
    for row in _read_csv(directory / "quotes.csv"):
        _require_fields(row, ("ticker", "current_price"), source="quotes.csv")
        ticker = row["ticker"].strip()
        prices[ticker] = _decimal(
            row["current_price"],
            field=f"Kiwoom current_price {ticker}",
        )

    candles: dict[tuple[str, date], CandleValues] = {}
    required = (
        "ticker",
        "date",
        "open_price",
        "high_price",
        "low_price",
        "close_price",
        "volume",
        "adjusted",
    )
    for row in _read_csv(directory / "daily_bars.csv"):
        _require_fields(row, required, source="daily_bars.csv")
        ticker = row["ticker"].strip()
        if _boolean(row["adjusted"], field=f"Kiwoom adjusted {ticker}"):
            raise ConsistencyError(f"Kiwoom daily bar is adjusted for {ticker}")
        try:
            candle_date = datetime.strptime(row["date"].strip(), "%Y%m%d").date()
        except ValueError as exc:
            raise ConsistencyError(f"invalid Kiwoom daily date: {row['date']}") from exc
        key = (ticker, candle_date)
        if key in candles:
            raise ConsistencyError(f"duplicate Kiwoom daily bar for {key}")
        candles[key] = (
            _decimal(row["open_price"], field="Kiwoom open"),
            _decimal(row["high_price"], field="Kiwoom high"),
            _decimal(row["low_price"], field="Kiwoom low"),
            _decimal(row["close_price"], field="Kiwoom close"),
            _decimal(row["volume"], field="Kiwoom volume"),
        )
    if tuple(sorted(prices)) != EXPECTED_SYMBOLS:
        raise ConsistencyError("Kiwoom quotes.csv symbol set is incomplete")
    return SnapshotEvidence(
        provider=KIWOOM_PROVIDER,
        snapshot_id=snapshot_id,
        captured_at=captured_at,
        directory=directory,
        prices=prices,
        candles=candles,
    )


def _bps_difference(left: Decimal, right: Decimal) -> Decimal:
    denominator = max(abs(left), abs(right))
    if denominator == 0:
        return Decimal(0) if left == right else Decimal("Infinity")
    return abs(left - right) / denominator * Decimal(10000)


def _format_bps(value: Decimal) -> str | None:
    if not value.is_finite():
        return None
    return str(value.quantize(Decimal("0.0001")))


def _compare_daily(
    toss: SnapshotEvidence,
    kiwoom: SnapshotEvidence,
    *,
    required_days: int,
    price_tolerance_won: Decimal,
) -> tuple[list[DailyComparison], tuple[str, ...], list[str], list[str]]:
    cutoff = min(
        toss.captured_at.astimezone(KOREA_TZ).date(),
        kiwoom.captured_at.astimezone(KOREA_TZ).date(),
    )
    rows: list[DailyComparison] = []
    passed: list[str] = []
    failures: list[str] = []
    warnings: list[str] = []
    for ticker in EXPECTED_SYMBOLS:
        toss_dates = {
            candle_date
            for symbol, candle_date in toss.candles
            if symbol == ticker and candle_date < cutoff
        }
        kiwoom_dates = {
            candle_date
            for symbol, candle_date in kiwoom.candles
            if symbol == ticker and candle_date < cutoff
        }
        overlap = sorted(toss_dates & kiwoom_dates, reverse=True)
        if len(overlap) < required_days:
            failures.append(
                f"{ticker}: only {len(overlap)} overlapping completed daily bars; "
                f"require {required_days}"
            )
            continue
        symbol_conflicts = 0
        symbol_volume_mismatches = 0
        for candle_date in overlap[:required_days]:
            toss_values = toss.candles[(ticker, candle_date)]
            kiwoom_values = kiwoom.candles[(ticker, candle_date)]
            price_differences = [
                abs(toss_values[index] - kiwoom_values[index])
                for index in range(4)
            ]
            max_difference = max(price_differences)
            price_match = max_difference <= price_tolerance_won
            volume_match = toss_values[4] == kiwoom_values[4]
            if not price_match:
                symbol_conflicts += 1
            if not volume_match:
                symbol_volume_mismatches += 1
            rows.append(
                DailyComparison(
                    ticker=ticker,
                    date=candle_date.isoformat(),
                    toss_open=str(toss_values[0]),
                    kiwoom_open=str(kiwoom_values[0]),
                    toss_high=str(toss_values[1]),
                    kiwoom_high=str(kiwoom_values[1]),
                    toss_low=str(toss_values[2]),
                    kiwoom_low=str(kiwoom_values[2]),
                    toss_close=str(toss_values[3]),
                    kiwoom_close=str(kiwoom_values[3]),
                    toss_volume=str(toss_values[4]),
                    kiwoom_volume=str(kiwoom_values[4]),
                    max_price_difference_won=str(max_difference),
                    price_match=price_match,
                    volume_match=volume_match,
                    volume_difference_bps=_format_bps(
                        _bps_difference(toss_values[4], kiwoom_values[4])
                    ),
                )
            )
        if symbol_conflicts:
            failures.append(
                f"{ticker}: {symbol_conflicts} completed daily OHLC rows conflict"
            )
        else:
            passed.append(ticker)
        if symbol_volume_mismatches:
            warnings.append(
                f"{ticker}: {symbol_volume_mismatches} historical volume rows differ"
            )
    return rows, tuple(passed), failures, warnings


def _compare_quotes(
    toss: SnapshotEvidence,
    kiwoom: SnapshotEvidence,
    *,
    now: datetime,
    max_snapshot_age: timedelta,
    max_capture_gap: timedelta,
    tolerance_bps: Decimal,
) -> tuple[list[QuoteComparison], str, list[str], list[str]]:
    toss_age = now - toss.captured_at.astimezone(UTC)
    kiwoom_age = now - kiwoom.captured_at.astimezone(UTC)
    capture_gap = abs(
        toss.captured_at.astimezone(UTC) - kiwoom.captured_at.astimezone(UTC)
    )
    fresh = (
        timedelta(0) <= toss_age <= max_snapshot_age
        and timedelta(0) <= kiwoom_age <= max_snapshot_age
        and capture_gap <= max_capture_gap
    )
    failures: list[str] = []
    warnings: list[str] = []
    if not fresh:
        reasons: list[str] = []
        if toss_age < timedelta(0) or toss_age > max_snapshot_age:
            reasons.append("TossInvest snapshot is not fresh")
        if kiwoom_age < timedelta(0) or kiwoom_age > max_snapshot_age:
            reasons.append("Kiwoom snapshot is not fresh")
        if capture_gap > max_capture_gap:
            reasons.append("provider capture times are too far apart")
        reason = "; ".join(reasons)
        warnings.append(f"live quotes not compared: {reason}")
        rows = [
            QuoteComparison(
                ticker=ticker,
                toss_price=str(toss.prices[ticker]),
                kiwoom_price=str(kiwoom.prices[ticker]),
                absolute_difference_won=str(
                    abs(toss.prices[ticker] - kiwoom.prices[ticker])
                ),
                difference_bps=_format_bps(
                    _bps_difference(toss.prices[ticker], kiwoom.prices[ticker])
                )
                or "infinite",
                capture_gap_seconds=str(capture_gap.total_seconds()),
                comparable=False,
                within_tolerance=None,
                reason=reason,
            )
            for ticker in EXPECTED_SYMBOLS
        ]
        return rows, "not_comparable", failures, warnings

    rows: list[QuoteComparison] = []
    conflicts = 0
    for ticker in EXPECTED_SYMBOLS:
        difference = _bps_difference(toss.prices[ticker], kiwoom.prices[ticker])
        within = difference <= tolerance_bps
        if not within:
            conflicts += 1
            failures.append(
                f"{ticker}: live quote difference "
                f"{difference.quantize(Decimal('0.01'))} bps exceeds "
                f"{tolerance_bps} bps"
            )
        rows.append(
            QuoteComparison(
                ticker=ticker,
                toss_price=str(toss.prices[ticker]),
                kiwoom_price=str(kiwoom.prices[ticker]),
                absolute_difference_won=str(
                    abs(toss.prices[ticker] - kiwoom.prices[ticker])
                ),
                difference_bps=_format_bps(difference) or "infinite",
                capture_gap_seconds=str(capture_gap.total_seconds()),
                comparable=True,
                within_tolerance=within,
                reason="capture times and snapshot ages are comparable",
            )
        )
    return rows, "conflict" if conflicts else "passed", failures, warnings


def _write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    if rows:
        with temporary.open("w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)
    else:
        temporary.write_text("", encoding="utf-8")
    temporary.replace(path)


def _atomic_json(path: Path, payload: Mapping[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(dict(payload), ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    temporary.replace(path)


def _result_id(payload: Mapping[str, object]) -> str:
    canonical = json.dumps(
        dict(payload),
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def run_consistency_check(
    *,
    output_root: Path,
    required_days: int,
    price_tolerance_won: Decimal,
    live_tolerance_bps: Decimal,
    max_snapshot_age_minutes: int,
    max_capture_gap_seconds: int,
    now: datetime | None = None,
) -> tuple[ConsistencyResult, Path]:
    if required_days <= 0:
        raise ConsistencyError("required_days must be positive")
    if price_tolerance_won < 0 or live_tolerance_bps < 0:
        raise ConsistencyError("tolerances cannot be negative")
    if max_snapshot_age_minutes <= 0 or max_capture_gap_seconds <= 0:
        raise ConsistencyError("freshness limits must be positive")
    checked_at = now or datetime.now(UTC)
    if checked_at.tzinfo is None or checked_at.utcoffset() is None:
        raise ConsistencyError("checker clock must be timezone-aware")
    checked_at = checked_at.astimezone(UTC)

    toss_directory, toss_resolution = _resolve_toss_directory(output_root)
    kiwoom_directory = _resolve_kiwoom_directory(output_root)
    toss = _load_toss(toss_directory)
    kiwoom = _load_kiwoom(kiwoom_directory)

    daily_rows, historical_passed, daily_failures, daily_warnings = (
        _compare_daily(
            toss,
            kiwoom,
            required_days=required_days,
            price_tolerance_won=price_tolerance_won,
        )
    )
    quote_rows, quote_status, quote_failures, quote_warnings = _compare_quotes(
        toss,
        kiwoom,
        now=checked_at,
        max_snapshot_age=timedelta(minutes=max_snapshot_age_minutes),
        max_capture_gap=timedelta(seconds=max_capture_gap_seconds),
        tolerance_bps=live_tolerance_bps,
    )
    failures = tuple(daily_failures + quote_failures)
    warnings = tuple(daily_warnings + quote_warnings)
    daily_conflicts = sum(not row.price_match for row in daily_rows)
    volume_mismatches = sum(not row.volume_match for row in daily_rows)
    comparable_quotes = sum(row.comparable for row in quote_rows)
    live_conflicts = sum(row.within_tolerance is False for row in quote_rows)
    integration_eligible = (
        not failures
        and historical_passed == EXPECTED_SYMBOLS
        and quote_status == "passed"
        and comparable_quotes == len(EXPECTED_SYMBOLS)
    )
    status = "failed"
    if not failures:
        status = "passed" if integration_eligible else "passed_historical_only"

    cutoff = min(
        toss.captured_at.astimezone(KOREA_TZ).date(),
        kiwoom.captured_at.astimezone(KOREA_TZ).date(),
    )
    timestamp = checked_at.astimezone(KOREA_TZ).strftime("%Y%m%dT%H%M%S%z")
    destination = output_root / "market-source-consistency" / timestamp
    if destination.exists():
        shutil.rmtree(destination)
    destination.mkdir(parents=True)
    daily_path = destination / "daily_price_comparisons.csv"
    quote_path = destination / "live_quote_comparisons.csv"
    _write_csv(daily_path, [asdict(row) for row in daily_rows])
    _write_csv(quote_path, [asdict(row) for row in quote_rows])

    result_payload: dict[str, object] = {
        "schema_version": "1.0",
        "status": status,
        "checked_at_utc": checked_at.isoformat(),
        "checked_at_kst": checked_at.astimezone(KOREA_TZ).isoformat(),
        "expected_symbols": list(EXPECTED_SYMBOLS),
        "toss_snapshot_id": toss.snapshot_id,
        "toss_captured_at": toss.captured_at.isoformat(),
        "toss_snapshot_age_seconds": (
            checked_at - toss.captured_at.astimezone(UTC)
        ).total_seconds(),
        "toss_directory": str(toss.directory),
        "toss_resolution_source": toss_resolution,
        "kiwoom_snapshot_id": kiwoom.snapshot_id,
        "kiwoom_captured_at": kiwoom.captured_at.isoformat(),
        "kiwoom_snapshot_age_seconds": (
            checked_at - kiwoom.captured_at.astimezone(UTC)
        ).total_seconds(),
        "kiwoom_directory": str(kiwoom.directory),
        "historical_cutoff_date_exclusive": cutoff.isoformat(),
        "historical_days_required_per_symbol": required_days,
        "historical_rows_compared": len(daily_rows),
        "historical_symbols_passed": list(historical_passed),
        "historical_price_conflict_count": daily_conflicts,
        "historical_volume_mismatch_count": volume_mismatches,
        "live_quote_status": quote_status,
        "live_quote_comparable_count": comparable_quotes,
        "live_quote_conflict_count": live_conflicts,
        "live_capture_gap_seconds": abs(
            toss.captured_at.astimezone(UTC)
            - kiwoom.captured_at.astimezone(UTC)
        ).total_seconds(),
        "decision_integration_eligible": integration_eligible,
        "automatic_provider_substitution_enabled": False,
        "account_api_enabled": False,
        "order_api_enabled": False,
        "warnings": list(warnings),
        "failures": list(failures),
        "daily_comparisons_file": daily_path.name,
        "quote_comparisons_file": quote_path.name,
    }
    result_id = _result_id(result_payload)
    result = ConsistencyResult(
        schema_version="1.0",
        status=status,
        checked_at_utc=checked_at.isoformat(),
        checked_at_kst=checked_at.astimezone(KOREA_TZ).isoformat(),
        expected_symbols=EXPECTED_SYMBOLS,
        toss_snapshot_id=toss.snapshot_id,
        toss_captured_at=toss.captured_at.isoformat(),
        toss_snapshot_age_seconds=(
            checked_at - toss.captured_at.astimezone(UTC)
        ).total_seconds(),
        toss_directory=str(toss.directory),
        toss_resolution_source=toss_resolution,
        kiwoom_snapshot_id=kiwoom.snapshot_id,
        kiwoom_captured_at=kiwoom.captured_at.isoformat(),
        kiwoom_snapshot_age_seconds=(
            checked_at - kiwoom.captured_at.astimezone(UTC)
        ).total_seconds(),
        kiwoom_directory=str(kiwoom.directory),
        historical_cutoff_date_exclusive=cutoff.isoformat(),
        historical_days_required_per_symbol=required_days,
        historical_rows_compared=len(daily_rows),
        historical_symbols_passed=historical_passed,
        historical_price_conflict_count=daily_conflicts,
        historical_volume_mismatch_count=volume_mismatches,
        live_quote_status=quote_status,
        live_quote_comparable_count=comparable_quotes,
        live_quote_conflict_count=live_conflicts,
        live_capture_gap_seconds=abs(
            toss.captured_at.astimezone(UTC)
            - kiwoom.captured_at.astimezone(UTC)
        ).total_seconds(),
        decision_integration_eligible=integration_eligible,
        automatic_provider_substitution_enabled=False,
        account_api_enabled=False,
        order_api_enabled=False,
        warnings=warnings,
        failures=failures,
        daily_comparisons_file=daily_path.name,
        quote_comparisons_file=quote_path.name,
        result_id=result_id,
    )
    result_path = destination / "consistency.json"
    _atomic_json(result_path, asdict(result))
    _atomic_json(
        output_root / "latest_market_consistency.json",
        {
            "status": status,
            "result_id": result_id,
            "checked_at_utc": result.checked_at_utc,
            "result_path": str(result_path),
            "decision_integration_eligible": integration_eligible,
            "historical_price_conflict_count": daily_conflicts,
            "live_quote_status": quote_status,
            "automatic_provider_substitution_enabled": False,
            "order_api_enabled": False,
        },
    )
    return result, result_path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Cross-check immutable TossInvest and Kiwoom market evidence "
            "without fetching or substituting data"
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


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        result, result_path = run_consistency_check(
            output_root=args.output_root,
            required_days=args.required_days,
            price_tolerance_won=args.price_tolerance_won,
            live_tolerance_bps=args.live_tolerance_bps,
            max_snapshot_age_minutes=args.max_snapshot_age_minutes,
            max_capture_gap_seconds=args.max_capture_gap_seconds,
        )
    except (ConsistencyError, OSError, TypeError, ValueError) as exc:
        print("MARKET SOURCE CONSISTENCY: FAIL", file=sys.stderr)
        print(f"failure: {exc}", file=sys.stderr)
        print("automatic provider substitution: disabled", file=sys.stderr)
        print("order API: disabled", file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(asdict(result), ensure_ascii=False, indent=2, sort_keys=True))
    else:
        label = "PASS" if result.status != "failed" else "FAIL"
        print(f"MARKET SOURCE CONSISTENCY: {label}")
        print(f"status: {result.status}")
        print(f"historical rows compared: {result.historical_rows_compared}")
        print(
            "historical price conflicts: "
            f"{result.historical_price_conflict_count}"
        )
        print(
            "historical volume mismatches: "
            f"{result.historical_volume_mismatch_count}"
        )
        print(f"live quote status: {result.live_quote_status}")
        print(
            "decision integration eligible: "
            f"{result.decision_integration_eligible}"
        )
        print("automatic provider substitution: disabled")
        print("account API: disabled")
        print("order API: disabled")
        print(f"consistency artifact: {result_path}")
    return 2 if result.status == "failed" else 0


if __name__ == "__main__":
    raise SystemExit(main())
