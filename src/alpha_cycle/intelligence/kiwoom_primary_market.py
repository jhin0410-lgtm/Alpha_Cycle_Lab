"""Build a market-intelligence snapshot from immutable Kiwoom read-only exports."""

from __future__ import annotations

import csv
import json
from collections import defaultdict
from datetime import UTC, datetime, time
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import cast
from zoneinfo import ZoneInfo

from alpha_cycle.intelligence.market import MarketIntelligenceSnapshot
from alpha_cycle.intelligence.technical import (
    add_relative_strength_ranks,
    calculate_technical_features,
)
from alpha_cycle.providers.tossinvest import Candle, MarketPrice

KOREA_TZ = ZoneInfo("Asia/Seoul")
EXPECTED_SYMBOLS = ("000660", "005930", "005935")
PROVIDER = "kiwoom_openapi_plus_primary_readonly"


class KiwoomPrimaryEvidenceError(ValueError):
    """Raised when a Kiwoom export cannot be used as primary market evidence."""


def _object(path: Path) -> dict[str, object]:
    try:
        value: object = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise KiwoomPrimaryEvidenceError(
            f"cannot read Kiwoom JSON evidence: {path}"
        ) from exc
    if not isinstance(value, dict):
        raise KiwoomPrimaryEvidenceError(
            f"Kiwoom JSON evidence must be an object: {path}"
        )
    return {str(key): item for key, item in value.items()}


def _rows(path: Path) -> list[dict[str, str]]:
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            return [
                {
                    str(key): "" if value is None else value
                    for key, value in row.items()
                }
                for row in csv.DictReader(handle)
            ]
    except (OSError, csv.Error) as exc:
        raise KiwoomPrimaryEvidenceError(
            f"cannot read Kiwoom CSV evidence: {path}"
        ) from exc


def _decimal(value: object, field: str) -> Decimal:
    try:
        parsed = Decimal(str(value).strip().replace(",", ""))
    except InvalidOperation as exc:
        raise KiwoomPrimaryEvidenceError(
            f"invalid Kiwoom decimal {field}: {value}"
        ) from exc
    if not parsed.is_finite() or parsed < 0:
        raise KiwoomPrimaryEvidenceError(
            f"invalid Kiwoom decimal {field}: {value}"
        )
    return parsed


def _aware(value: object, field: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(str(value).strip().replace("Z", "+00:00"))
    except ValueError as exc:
        raise KiwoomPrimaryEvidenceError(
            f"invalid datetime {field}: {value}"
        ) from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise KiwoomPrimaryEvidenceError(
            f"datetime must be timezone-aware: {field}"
        )
    return parsed.astimezone(UTC)


def _true(value: object, field: str) -> bool:
    if value is True:
        return True
    if isinstance(value, str) and value.strip().casefold() in {"true", "1", "yes"}:
        return True
    raise KiwoomPrimaryEvidenceError(f"Kiwoom evidence must be true: {field}")


def _evidence_path(directory: Path, raw_name: object, field: str) -> Path:
    name = str(raw_name).strip()
    if not name or Path(name).name != name:
        raise KiwoomPrimaryEvidenceError(f"invalid Kiwoom evidence filename: {field}")
    path = (directory / name).resolve()
    try:
        path.relative_to(directory.resolve())
    except ValueError as exc:
        raise KiwoomPrimaryEvidenceError(
            f"Kiwoom evidence path escapes export directory: {field}"
        ) from exc
    if not path.is_file():
        raise KiwoomPrimaryEvidenceError(f"Kiwoom evidence file is missing: {field}")
    return path


def _source_directory(output_root: Path) -> tuple[Path, dict[str, object], Path]:
    root = output_root / "kiwoom-openapi-plus-market"
    pointer_path = root / "latest_market_export.json"
    pointer = _object(pointer_path)
    if (
        pointer.get("status") != "completed"
        or pointer.get("provider") != "kiwoom_openapi_plus"
    ):
        raise KiwoomPrimaryEvidenceError(
            "latest Kiwoom market export is not completed"
        )
    directory = Path(str(pointer.get("export_directory", "")).strip())
    if not directory.is_absolute():
        directory = Path.cwd() / directory
    try:
        directory = directory.resolve(strict=True)
    except OSError as exc:
        raise KiwoomPrimaryEvidenceError(
            "latest Kiwoom export directory is unavailable"
        ) from exc
    manifest_path = directory / "manifest.json"
    manifest = _object(manifest_path)
    if manifest.get("snapshot_id") != pointer.get("snapshot_id"):
        raise KiwoomPrimaryEvidenceError(
            "Kiwoom pointer snapshot_id does not match manifest"
        )
    if (
        manifest.get("provider") != "kiwoom_openapi_plus"
        or manifest.get("status") != "completed"
    ):
        raise KiwoomPrimaryEvidenceError(
            "unexpected Kiwoom manifest provider or status"
        )
    if bool(manifest.get("account_api_enabled")) or bool(
        manifest.get("order_api_enabled")
    ):
        raise KiwoomPrimaryEvidenceError(
            "Kiwoom primary evidence cannot enable account or order APIs"
        )
    _true(manifest.get("adjusted_prices"), "manifest.adjusted_prices")
    _true(pointer.get("adjusted_prices"), "pointer.adjusted_prices")
    if manifest.get("price_basis") != "adjusted":
        raise KiwoomPrimaryEvidenceError("Kiwoom manifest price basis is not adjusted")
    if pointer.get("price_basis") != "adjusted":
        raise KiwoomPrimaryEvidenceError("Kiwoom pointer price basis is not adjusted")
    if str(manifest.get("adjustment_request_value", "")) != "1":
        raise KiwoomPrimaryEvidenceError(
            "Kiwoom manifest did not record 수정주가구분=1"
        )
    symbol_values = cast(list[object], manifest.get("symbols", []))
    symbols = tuple(sorted(str(item).zfill(6) for item in symbol_values))
    if symbols != EXPECTED_SYMBOLS:
        raise KiwoomPrimaryEvidenceError(
            f"Kiwoom symbol set mismatch: expected {EXPECTED_SYMBOLS}, got {symbols}"
        )
    return directory, manifest, manifest_path


def _indexed_adjustment_evidence(
    rows: list[dict[str, str]],
) -> dict[tuple[str, str], dict[str, str]]:
    indexed: dict[tuple[str, str], dict[str, str]] = {}
    for row in rows:
        symbol = row.get("ticker", "").strip().zfill(6)
        day = row.get("date", "").strip()
        key = (symbol, day)
        if key in indexed:
            raise KiwoomPrimaryEvidenceError(
                f"duplicate Kiwoom adjustment evidence: {key}"
            )
        if (
            row.get("requested_price_basis", "").strip() != "adjusted"
            or row.get("adjustment_request_value", "").strip() != "1"
        ):
            raise KiwoomPrimaryEvidenceError(
                f"unexpected Kiwoom adjustment request evidence: {key}"
            )
        indexed[key] = row
    return indexed


def build_kiwoom_primary_snapshot(
    output_root: str | Path,
    *,
    count: int,
    max_age_minutes: int = 30,
    now: datetime | None = None,
) -> MarketIntelligenceSnapshot:
    """Convert verified adjusted Kiwoom evidence into a standard market snapshot."""

    if count <= 0 or count > 600:
        raise KiwoomPrimaryEvidenceError(
            "Kiwoom candle count must be between 1 and 600"
        )
    if max_age_minutes <= 0:
        raise KiwoomPrimaryEvidenceError("Kiwoom max age must be positive")
    root = Path(output_root)
    directory, manifest, manifest_path = _source_directory(root)
    captured_at = _aware(manifest.get("captured_at_utc"), "captured_at_utc")
    clock = now or datetime.now(UTC)
    if clock.tzinfo is None or clock.utcoffset() is None:
        raise KiwoomPrimaryEvidenceError(
            "Kiwoom adapter clock must be timezone-aware"
        )
    age_seconds = (clock.astimezone(UTC) - captured_at).total_seconds()
    if age_seconds < -60 or age_seconds > max_age_minutes * 60:
        raise KiwoomPrimaryEvidenceError(
            "latest Kiwoom market export is not fresh enough: "
            f"age_seconds={age_seconds:.1f}"
        )

    quote_rows = _rows(
        _evidence_path(directory, manifest.get("quotes_file"), "quotes_file")
    )
    bar_rows = _rows(
        _evidence_path(directory, manifest.get("daily_bars_file"), "daily_bars_file")
    )
    adjustment_rows = _rows(
        _evidence_path(
            directory,
            manifest.get("adjustment_evidence_file"),
            "adjustment_evidence_file",
        )
    )
    adjustment_by_key = _indexed_adjustment_evidence(adjustment_rows)

    quote_by_symbol: dict[str, dict[str, str]] = {}
    for row in quote_rows:
        symbol = row.get("ticker", "").strip().zfill(6)
        if symbol in quote_by_symbol:
            raise KiwoomPrimaryEvidenceError(f"duplicate Kiwoom quote: {symbol}")
        quote_by_symbol[symbol] = row
    if tuple(sorted(quote_by_symbol)) != EXPECTED_SYMBOLS:
        raise KiwoomPrimaryEvidenceError("Kiwoom quote symbol set is incomplete")

    bars_by_symbol: dict[str, list[dict[str, str]]] = defaultdict(list)
    seen_bars: set[tuple[str, str]] = set()
    for row in bar_rows:
        symbol = row.get("ticker", "").strip().zfill(6)
        candle_date = row.get("date", "").strip()
        key = (symbol, candle_date)
        if key in seen_bars:
            raise KiwoomPrimaryEvidenceError(f"duplicate Kiwoom daily bar: {key}")
        seen_bars.add(key)
        _true(row.get("adjusted"), f"daily_bars.adjusted:{key}")
        if key not in adjustment_by_key:
            raise KiwoomPrimaryEvidenceError(
                f"Kiwoom daily bar lacks adjustment evidence: {key}"
            )
        bars_by_symbol[symbol].append(row)
    if seen_bars != set(adjustment_by_key):
        raise KiwoomPrimaryEvidenceError(
            "Kiwoom adjustment evidence does not match the daily-bar universe"
        )

    prices = tuple(
        MarketPrice(
            symbol=symbol,
            timestamp=captured_at,
            last_price=_decimal(
                quote_by_symbol[symbol].get("current_price"),
                "current_price",
            ),
            currency="KRW",
        )
        for symbol in EXPECTED_SYMBOLS
    )
    candles: list[Candle] = []
    raw_candles: dict[str, object] = {}
    features = []
    for symbol in EXPECTED_SYMBOLS:
        selected = sorted(
            bars_by_symbol.get(symbol, []),
            key=lambda row: row.get("date", ""),
        )[-count:]
        if not selected:
            raise KiwoomPrimaryEvidenceError(f"no Kiwoom daily bars for {symbol}")
        selected_evidence = [
            adjustment_by_key[(symbol, row.get("date", "").strip())]
            for row in selected
        ]
        symbol_candles: list[Candle] = []
        for row in selected:
            try:
                day = datetime.strptime(row["date"], "%Y%m%d").date()
            except (KeyError, ValueError) as exc:
                raise KiwoomPrimaryEvidenceError(
                    f"invalid Kiwoom daily date for {symbol}: {row.get('date')}"
                ) from exc
            timestamp = datetime.combine(day, time(15, 30), tzinfo=KOREA_TZ)
            symbol_candles.append(
                Candle(
                    symbol=symbol,
                    timestamp=timestamp,
                    open_price=_decimal(row.get("open_price"), "open_price"),
                    high_price=_decimal(row.get("high_price"), "high_price"),
                    low_price=_decimal(row.get("low_price"), "low_price"),
                    close_price=_decimal(row.get("close_price"), "close_price"),
                    volume=_decimal(row.get("volume"), "volume"),
                    currency="KRW",
                    interval="1d",
                    adjusted=True,
                )
            )
        candles.extend(symbol_candles)
        features.append(calculate_technical_features(tuple(symbol_candles)))
        raw_candles[symbol] = {
            "price_basis": "adjusted",
            "bars": selected,
            "adjustment_evidence": selected_evidence,
        }

    ranked = add_relative_strength_ranks(
        tuple(sorted(features, key=lambda item: item.symbol))
    )
    raw_prices: dict[str, object] = {
        "source_provider": "kiwoom_openapi_plus",
        "source_snapshot_id": manifest.get("snapshot_id"),
        "source_manifest_path": str(manifest_path.resolve()),
        "source_export_directory": str(directory.resolve()),
        "captured_at_utc": captured_at.isoformat(),
        "price_basis": "adjusted",
        "adjustment_request_value": "1",
        "corporate_action_row_count": manifest.get("corporate_action_row_count", 0),
        "quotes": quote_rows,
        "account_api_enabled": False,
        "order_api_enabled": False,
    }
    return MarketIntelligenceSnapshot(
        captured_at=captured_at,
        provider=PROVIDER,
        interval="1d",
        adjusted=True,
        prices=prices,
        candles=tuple(
            sorted(candles, key=lambda item: (item.symbol, item.timestamp))
        ),
        features=ranked,
        raw_prices=raw_prices,
        raw_candles=raw_candles,
    )


__all__ = [
    "KiwoomPrimaryEvidenceError",
    "PROVIDER",
    "build_kiwoom_primary_snapshot",
]
