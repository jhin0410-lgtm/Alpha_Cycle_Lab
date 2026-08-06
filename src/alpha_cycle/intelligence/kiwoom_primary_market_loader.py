"""Reload and verify a converted Kiwoom primary market snapshot."""

from __future__ import annotations

import csv
import json
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import cast

from alpha_cycle.intelligence.kiwoom_primary_market import (
    KiwoomPrimaryMarketError,
    load_kiwoom_primary_manifest,
)
from alpha_cycle.intelligence.market import MarketIntelligenceSnapshot
from alpha_cycle.intelligence.technical import (
    add_relative_strength_ranks,
    calculate_technical_features,
)
from alpha_cycle.providers.tossinvest import Candle, MarketPrice

SNAPSHOT_FILES = (
    "manifest.json",
    "prices.csv",
    "candles.csv",
    "technical_features.csv",
    "raw_prices.json",
    "raw_candles.json",
)


def _decimal(value: object, field: str, *, positive: bool = False) -> Decimal:
    try:
        parsed = Decimal(str(value).strip())
    except InvalidOperation as exc:
        raise KiwoomPrimaryMarketError(f"{field} must be decimal") from exc
    if not parsed.is_finite() or (positive and parsed <= 0):
        raise KiwoomPrimaryMarketError(f"{field} is invalid")
    return parsed


def _boolean(value: object, field: str) -> bool:
    if isinstance(value, bool):
        return value
    normalized = str(value).strip().casefold()
    if normalized in {"true", "1", "yes"}:
        return True
    if normalized in {"false", "0", "no"}:
        return False
    raise KiwoomPrimaryMarketError(f"{field} must be boolean")


def _aware(value: object, field: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(str(value).strip().replace("Z", "+00:00"))
    except ValueError as exc:
        raise KiwoomPrimaryMarketError(f"{field} must be ISO-8601 datetime") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise KiwoomPrimaryMarketError(f"{field} must be timezone-aware")
    return parsed


def _csv_rows(path: Path) -> list[dict[str, str]]:
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            return [
                {
                    str(key): "" if value is None else str(value)
                    for key, value in row.items()
                }
                for row in csv.DictReader(handle)
            ]
    except (OSError, csv.Error) as exc:
        raise KiwoomPrimaryMarketError(f"cannot read snapshot CSV {path}: {exc}") from exc


def _json(path: Path) -> object:
    try:
        return cast(object, json.loads(path.read_text(encoding="utf-8")))
    except (OSError, json.JSONDecodeError) as exc:
        raise KiwoomPrimaryMarketError(f"cannot read snapshot JSON {path}: {exc}") from exc


def load_kiwoom_primary_snapshot(
    market_directory: str | Path,
    *,
    max_age_minutes: int = 30,
) -> MarketIntelligenceSnapshot:
    """Reconstruct one immutable Kiwoom primary snapshot and verify its digest."""

    directory = Path(market_directory).resolve(strict=True)
    manifest = load_kiwoom_primary_manifest(
        directory,
        max_age_minutes=max_age_minutes,
    )
    prices: list[MarketPrice] = []
    for row in _csv_rows(directory / "prices.csv"):
        symbol = str(row.get("symbol", "")).strip().zfill(6)
        prices.append(
            MarketPrice(
                symbol=symbol,
                timestamp=_aware(row.get("timestamp"), f"{symbol} price timestamp"),
                last_price=_decimal(
                    row.get("last_price"),
                    f"{symbol} last_price",
                    positive=True,
                ),
                currency=str(row.get("currency", "")).strip().upper(),
            )
        )

    candles: list[Candle] = []
    for row in _csv_rows(directory / "candles.csv"):
        symbol = str(row.get("symbol", "")).strip().zfill(6)
        candles.append(
            Candle(
                symbol=symbol,
                timestamp=_aware(row.get("timestamp"), f"{symbol} candle timestamp"),
                open_price=_decimal(row.get("open"), f"{symbol} open", positive=True),
                high_price=_decimal(row.get("high"), f"{symbol} high", positive=True),
                low_price=_decimal(row.get("low"), f"{symbol} low", positive=True),
                close_price=_decimal(row.get("close"), f"{symbol} close", positive=True),
                volume=_decimal(row.get("volume"), f"{symbol} volume"),
                currency=str(row.get("currency", "")).strip().upper(),
                interval=str(row.get("interval", "")).strip(),
                adjusted=_boolean(row.get("adjusted"), f"{symbol} adjusted"),
            )
        )
    symbols = tuple(sorted(item.symbol for item in prices))
    calculated = tuple(
        calculate_technical_features(
            tuple(item for item in candles if item.symbol == symbol)
        )
        for symbol in symbols
    )
    snapshot = MarketIntelligenceSnapshot(
        captured_at=_aware(manifest.get("captured_at"), "market captured_at"),
        provider=str(manifest.get("provider", "")),
        interval=str(manifest.get("interval", "")),
        adjusted=_boolean(manifest.get("adjusted"), "market adjusted"),
        prices=tuple(sorted(prices, key=lambda item: item.symbol)),
        candles=tuple(sorted(candles, key=lambda item: (item.symbol, item.timestamp))),
        features=add_relative_strength_ranks(calculated),
        raw_prices=_json(directory / "raw_prices.json"),
        raw_candles=cast(dict[str, object], _json(directory / "raw_candles.json")),
    )
    if snapshot.snapshot_id != str(manifest.get("snapshot_id", "")):
        raise KiwoomPrimaryMarketError(
            "Kiwoom primary market snapshot digest does not match its manifest"
        )
    if snapshot.symbols != tuple(manifest.get("symbols", [])):
        raise KiwoomPrimaryMarketError(
            "Kiwoom primary market snapshot symbols do not match its manifest"
        )
    return snapshot


def existing_kiwoom_primary_files(
    market_directory: str | Path,
) -> tuple[Path, ...]:
    directory = Path(market_directory).resolve(strict=True)
    files = tuple(directory / name for name in SNAPSHOT_FILES)
    missing = [path.name for path in files if not path.is_file()]
    if missing:
        raise KiwoomPrimaryMarketError(
            "Kiwoom primary market snapshot is incomplete: " + ", ".join(missing)
        )
    return files


__all__ = [
    "existing_kiwoom_primary_files",
    "load_kiwoom_primary_snapshot",
]
