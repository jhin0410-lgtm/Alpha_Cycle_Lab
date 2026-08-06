"""Convert one fresh Kiwoom OpenAPI+ export into market-intelligence evidence.

The adapter is intentionally read-only. It accepts only immutable public quote and
unadjusted daily-bar artifacts produced by the isolated x86 bridge. Account, holdings,
balance, and order data are outside this boundary.
"""

from __future__ import annotations

import csv
import hashlib
import json
from collections import defaultdict
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, time
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import cast
from zoneinfo import ZoneInfo

from alpha_cycle.intelligence.market import (
    MarketIntelligenceSnapshot,
    write_market_intelligence_snapshot,
)
from alpha_cycle.intelligence.technical import (
    add_relative_strength_ranks,
    calculate_technical_features,
)
from alpha_cycle.providers.tossinvest import Candle, MarketPrice

KOREA_TZ = ZoneInfo("Asia/Seoul")
EXPECTED_SYMBOLS = ("000660", "005930", "005935")
SOURCE_PROVIDER = "kiwoom_openapi_plus"
PRIMARY_PROVIDER = "kiwoom_openapi_plus_readonly_primary"
DEFAULT_OUTPUT_ROOT = Path("data/private/live-research")
LATEST_EXPORT_NAME = "latest_market_export.json"
LATEST_PRIMARY_NAME = "latest_kiwoom_primary_market.json"
_HEX = frozenset("0123456789abcdef")


class KiwoomPrimaryMarketError(ValueError):
    """Expected validation failure at the read-only Kiwoom artifact boundary."""


@dataclass(frozen=True)
class ValidatedKiwoomExport:
    export_directory: Path
    manifest_path: Path
    snapshot_id: str
    captured_at: datetime
    symbols: tuple[str, ...]
    quote_rows: tuple[Mapping[str, str], ...]
    bar_rows: tuple[Mapping[str, str], ...]
    quotes_sha256: str
    daily_bars_sha256: str
    manifest_sha256: str


@dataclass(frozen=True)
class KiwoomPrimarySnapshot:
    snapshot: MarketIntelligenceSnapshot
    source: ValidatedKiwoomExport
    fallback_reason: str


def _object(path: Path) -> dict[str, object]:
    try:
        payload: object = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise KiwoomPrimaryMarketError(f"cannot read JSON evidence {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise KiwoomPrimaryMarketError(f"JSON evidence must be an object: {path}")
    return {str(key): value for key, value in payload.items()}


def _rows(path: Path) -> tuple[Mapping[str, str], ...]:
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            if reader.fieldnames is None:
                raise KiwoomPrimaryMarketError(f"CSV has no header: {path}")
            return tuple(
                {
                    str(key): "" if value is None else str(value)
                    for key, value in row.items()
                }
                for row in reader
            )
    except (OSError, csv.Error) as exc:
        raise KiwoomPrimaryMarketError(f"cannot read CSV evidence {path}: {exc}") from exc


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as handle:
            for block in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(block)
    except OSError as exc:
        raise KiwoomPrimaryMarketError(f"cannot hash evidence file {path}: {exc}") from exc
    return digest.hexdigest()


def _sha256(value: object, field: str) -> str:
    text = str(value).strip()
    if len(text) != 64 or any(character not in _HEX for character in text):
        raise KiwoomPrimaryMarketError(f"{field} must be a lowercase SHA-256 digest")
    return text


def _boolean(value: object, field: str) -> bool:
    if isinstance(value, bool):
        return value
    normalized = str(value).strip().casefold()
    if normalized in {"true", "1", "yes"}:
        return True
    if normalized in {"false", "0", "no"}:
        return False
    raise KiwoomPrimaryMarketError(f"{field} must be boolean")


def _integer(value: object, field: str, *, positive: bool = False) -> int:
    text = str(value).strip().replace(",", "")
    try:
        result = int(text)
    except ValueError as exc:
        raise KiwoomPrimaryMarketError(f"{field} must be an integer") from exc
    if positive and result <= 0:
        raise KiwoomPrimaryMarketError(f"{field} must be positive")
    return result


def _decimal(value: object, field: str, *, positive: bool = False) -> Decimal:
    text = str(value).strip().replace(",", "")
    try:
        result = Decimal(text)
    except InvalidOperation as exc:
        raise KiwoomPrimaryMarketError(f"{field} must be decimal") from exc
    if not result.is_finite():
        raise KiwoomPrimaryMarketError(f"{field} must be finite")
    if positive and result <= 0:
        raise KiwoomPrimaryMarketError(f"{field} must be positive")
    return result


def _aware_datetime(value: object, field: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(str(value).strip().replace("Z", "+00:00"))
    except ValueError as exc:
        raise KiwoomPrimaryMarketError(f"{field} must be ISO-8601 datetime") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise KiwoomPrimaryMarketError(f"{field} must be timezone-aware")
    return parsed.astimezone(UTC)


def _symbols(value: object, field: str) -> tuple[str, ...]:
    if not isinstance(value, list):
        raise KiwoomPrimaryMarketError(f"{field} must be a list")
    result = tuple(sorted(str(item).strip().zfill(6) for item in value))
    if result != EXPECTED_SYMBOLS:
        raise KiwoomPrimaryMarketError(
            f"{field} must equal the fixed market universe {EXPECTED_SYMBOLS}, got {result}"
        )
    return result


def _resolved_child(root: Path, value: object, field: str) -> Path:
    text = str(value).strip()
    if not text:
        raise KiwoomPrimaryMarketError(f"{field} is missing")
    candidate = Path(text)
    if not candidate.is_absolute():
        candidate = Path.cwd() / candidate
    try:
        resolved = candidate.resolve(strict=True)
        resolved.relative_to(root.resolve(strict=True))
    except (OSError, ValueError) as exc:
        raise KiwoomPrimaryMarketError(f"{field} escapes or is unavailable: {candidate}") from exc
    return resolved


def validate_latest_kiwoom_export(
    output_root: str | Path,
    *,
    max_age_minutes: int,
    now: datetime | None = None,
) -> ValidatedKiwoomExport:
    """Load and validate the latest immutable Kiwoom public-market export."""

    if max_age_minutes <= 0:
        raise KiwoomPrimaryMarketError("max_age_minutes must be positive")
    checked_at = (now or datetime.now(UTC)).astimezone(UTC)
    root = Path(output_root).resolve()
    source_root = root / "kiwoom-openapi-plus-market"
    pointer = _object(source_root / LATEST_EXPORT_NAME)
    if str(pointer.get("status", "")) != "completed":
        raise KiwoomPrimaryMarketError("latest Kiwoom export is not completed")
    if str(pointer.get("provider", "")) != SOURCE_PROVIDER:
        raise KiwoomPrimaryMarketError("latest Kiwoom pointer has an unexpected provider")
    export_directory = _resolved_child(
        source_root,
        pointer.get("export_directory"),
        "export_directory",
    )
    if not export_directory.is_dir():
        raise KiwoomPrimaryMarketError("Kiwoom export_directory is not a directory")
    manifest_path = _resolved_child(
        source_root,
        pointer.get("manifest_path"),
        "manifest_path",
    )
    if manifest_path.parent != export_directory:
        raise KiwoomPrimaryMarketError("Kiwoom pointer paths identify different exports")
    manifest = _object(manifest_path)
    if str(manifest.get("status", "")) != "completed":
        raise KiwoomPrimaryMarketError("Kiwoom manifest is not completed")
    if str(manifest.get("provider", "")) != SOURCE_PROVIDER:
        raise KiwoomPrimaryMarketError("Kiwoom manifest provider is invalid")
    source_id = _sha256(manifest.get("snapshot_id"), "Kiwoom snapshot_id")
    if _sha256(pointer.get("snapshot_id"), "pointer snapshot_id") != source_id:
        raise KiwoomPrimaryMarketError("Kiwoom pointer and manifest snapshot IDs differ")
    symbols = _symbols(manifest.get("symbols"), "Kiwoom symbols")
    if _symbols(pointer.get("symbols"), "pointer symbols") != symbols:
        raise KiwoomPrimaryMarketError("Kiwoom pointer and manifest symbol sets differ")
    if not _boolean(manifest.get("connected"), "Kiwoom connected"):
        raise KiwoomPrimaryMarketError("Kiwoom export was not connected")
    if _boolean(manifest.get("adjusted_prices"), "Kiwoom adjusted_prices"):
        raise KiwoomPrimaryMarketError("only unadjusted Kiwoom daily bars are supported")
    for field in ("account_api_enabled", "order_api_enabled"):
        if _boolean(manifest.get(field), f"Kiwoom {field}"):
            raise KiwoomPrimaryMarketError(f"Kiwoom export cannot enable {field}")
    captured_at = _aware_datetime(manifest.get("captured_at_utc"), "captured_at_utc")
    age_seconds = (checked_at - captured_at).total_seconds()
    if age_seconds < -60:
        raise KiwoomPrimaryMarketError("Kiwoom export capture time is in the future")
    if age_seconds > max_age_minutes * 60:
        raise KiwoomPrimaryMarketError(
            f"Kiwoom export is stale: {age_seconds / 60:.1f} minutes old"
        )

    quotes_name = str(manifest.get("quotes_file", "")).strip()
    bars_name = str(manifest.get("daily_bars_file", "")).strip()
    if not quotes_name or Path(quotes_name).name != quotes_name:
        raise KiwoomPrimaryMarketError("Kiwoom quotes_file is invalid")
    if not bars_name or Path(bars_name).name != bars_name:
        raise KiwoomPrimaryMarketError("Kiwoom daily_bars_file is invalid")
    quotes_path = export_directory / quotes_name
    bars_path = export_directory / bars_name
    quote_rows = _rows(quotes_path)
    bar_rows = _rows(bars_path)
    quote_symbols = tuple(sorted(str(row.get("ticker", "")).zfill(6) for row in quote_rows))
    if quote_symbols != symbols or len(set(quote_symbols)) != len(symbols):
        raise KiwoomPrimaryMarketError("Kiwoom quote rows do not cover the fixed universe")
    bar_symbols = tuple(sorted({str(row.get("ticker", "")).zfill(6) for row in bar_rows}))
    if bar_symbols != symbols:
        raise KiwoomPrimaryMarketError("Kiwoom daily bars do not cover the fixed universe")
    if _integer(manifest.get("quote_count"), "quote_count") != len(quote_rows):
        raise KiwoomPrimaryMarketError("Kiwoom quote_count does not match quotes.csv")
    if _integer(manifest.get("daily_bar_count"), "daily_bar_count") != len(bar_rows):
        raise KiwoomPrimaryMarketError("Kiwoom daily_bar_count does not match daily_bars.csv")

    return ValidatedKiwoomExport(
        export_directory=export_directory,
        manifest_path=manifest_path,
        snapshot_id=source_id,
        captured_at=captured_at,
        symbols=symbols,
        quote_rows=quote_rows,
        bar_rows=bar_rows,
        quotes_sha256=_sha256_file(quotes_path),
        daily_bars_sha256=_sha256_file(bars_path),
        manifest_sha256=_sha256_file(manifest_path),
    )


def build_kiwoom_primary_snapshot(
    output_root: str | Path,
    *,
    candle_count: int,
    max_age_minutes: int,
    fallback_reason: str,
    now: datetime | None = None,
) -> KiwoomPrimarySnapshot:
    """Build a market-intelligence snapshot from a fresh Kiwoom export."""

    if candle_count <= 0 or candle_count > 200:
        raise KiwoomPrimaryMarketError("candle_count must be between 1 and 200")
    if fallback_reason != "tossinvest_ip_allowlist":
        raise KiwoomPrimaryMarketError("unsupported Kiwoom primary fallback reason")
    source = validate_latest_kiwoom_export(
        output_root,
        max_age_minutes=max_age_minutes,
        now=now,
    )

    prices: list[MarketPrice] = []
    raw_quotes: list[dict[str, object]] = []
    for row in source.quote_rows:
        ticker = str(row.get("ticker", "")).zfill(6)
        current_price = _decimal(
            row.get("current_price"),
            f"{ticker} current_price",
            positive=True,
        )
        prices.append(
            MarketPrice(
                symbol=ticker,
                timestamp=source.captured_at,
                last_price=current_price,
                currency="KRW",
            )
        )
        raw_quotes.append(dict(row))

    grouped: dict[str, list[Mapping[str, str]]] = defaultdict(list)
    for row in source.bar_rows:
        grouped[str(row.get("ticker", "")).zfill(6)].append(row)
    candles: list[Candle] = []
    raw_candles: dict[str, object] = {}
    for ticker in source.symbols:
        ordered = sorted(grouped[ticker], key=lambda row: str(row.get("date", "")))[
            -candle_count:
        ]
        if len(ordered) < candle_count:
            raise KiwoomPrimaryMarketError(
                f"Kiwoom daily-bar history is incomplete for {ticker}: "
                f"required {candle_count}, got {len(ordered)}"
            )
        dates: set[str] = set()
        raw_candles[ticker] = [dict(row) for row in ordered]
        for row in ordered:
            date_text = str(row.get("date", "")).strip()
            if len(date_text) != 8 or not date_text.isdigit() or date_text in dates:
                raise KiwoomPrimaryMarketError(
                    f"Kiwoom daily-bar date is invalid or duplicated for {ticker}: {date_text}"
                )
            dates.add(date_text)
            session_date = datetime.strptime(date_text, "%Y%m%d").date()
            timestamp = datetime.combine(
                session_date,
                time(hour=15, minute=30),
                tzinfo=KOREA_TZ,
            )
            adjusted = _boolean(row.get("adjusted"), f"{ticker} adjusted")
            if adjusted:
                raise KiwoomPrimaryMarketError("adjusted Kiwoom daily bars are unsupported")
            candles.append(
                Candle(
                    symbol=ticker,
                    timestamp=timestamp,
                    open_price=_decimal(row.get("open_price"), f"{ticker} open", positive=True),
                    high_price=_decimal(row.get("high_price"), f"{ticker} high", positive=True),
                    low_price=_decimal(row.get("low_price"), f"{ticker} low", positive=True),
                    close_price=_decimal(row.get("close_price"), f"{ticker} close", positive=True),
                    volume=_decimal(row.get("volume"), f"{ticker} volume"),
                    currency="KRW",
                    interval="1d",
                    adjusted=False,
                )
            )

    calculated = tuple(
        calculate_technical_features(
            tuple(item for item in candles if item.symbol == ticker)
        )
        for ticker in source.symbols
    )
    features = add_relative_strength_ranks(calculated)
    source_payload: dict[str, object] = {
        "source_provider": SOURCE_PROVIDER,
        "source_snapshot_id": source.snapshot_id,
        "source_export_directory": str(source.export_directory),
        "source_manifest_path": str(source.manifest_path),
        "source_manifest_sha256": source.manifest_sha256,
        "source_quotes_sha256": source.quotes_sha256,
        "source_daily_bars_sha256": source.daily_bars_sha256,
        "fallback_reason": fallback_reason,
        "read_only_market_failover_used": True,
        "cross_provider_price_certified": False,
        "automatic_provider_substitution_enabled": False,
        "account_api_enabled": False,
        "order_api_enabled": False,
        "quotes": raw_quotes,
    }
    snapshot = MarketIntelligenceSnapshot(
        captured_at=source.captured_at,
        provider=PRIMARY_PROVIDER,
        interval="1d",
        adjusted=False,
        prices=tuple(sorted(prices, key=lambda item: item.symbol)),
        candles=tuple(sorted(candles, key=lambda item: (item.symbol, item.timestamp))),
        features=features,
        raw_prices=source_payload,
        raw_candles=raw_candles,
    )
    return KiwoomPrimarySnapshot(
        snapshot=snapshot,
        source=source,
        fallback_reason=fallback_reason,
    )


def write_kiwoom_primary_snapshot(
    output_root: str | Path,
    primary: KiwoomPrimarySnapshot,
) -> tuple[Path, ...]:
    """Write one immutable market snapshot and a non-authoritative latest pointer."""

    root = Path(output_root)
    files = write_market_intelligence_snapshot(
        root / "market-intelligence",
        primary.snapshot,
    )
    directory = files[0].parent.resolve()
    pointer = {
        "status": "completed",
        "provider": PRIMARY_PROVIDER,
        "snapshot_id": primary.snapshot.snapshot_id,
        "market_directory": str(directory),
        "captured_at": primary.snapshot.captured_at.isoformat(),
        "source_kiwoom_snapshot_id": primary.source.snapshot_id,
        "source_export_directory": str(primary.source.export_directory),
        "fallback_reason": primary.fallback_reason,
        "read_only_market_failover_used": True,
        "cross_provider_price_certified": False,
        "automatic_provider_substitution_enabled": False,
        "account_api_enabled": False,
        "order_api_enabled": False,
    }
    destination = root / LATEST_PRIMARY_NAME
    temporary = destination.with_suffix(destination.suffix + ".tmp")
    temporary.write_text(
        json.dumps(pointer, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    temporary.replace(destination)
    return files


def load_kiwoom_primary_manifest(
    market_directory: str | Path,
    *,
    max_age_minutes: int,
    now: datetime | None = None,
) -> dict[str, object]:
    """Validate a converted primary snapshot before the live pipeline consumes it."""

    if max_age_minutes <= 0:
        raise KiwoomPrimaryMarketError("max_age_minutes must be positive")
    directory = Path(market_directory).resolve(strict=True)
    manifest = _object(directory / "manifest.json")
    if str(manifest.get("provider", "")) != PRIMARY_PROVIDER:
        raise KiwoomPrimaryMarketError("market snapshot is not a Kiwoom primary snapshot")
    _sha256(manifest.get("snapshot_id"), "market snapshot_id")
    _symbols(manifest.get("symbols"), "market symbols")
    if _boolean(manifest.get("adjusted"), "market adjusted"):
        raise KiwoomPrimaryMarketError("Kiwoom primary market snapshot must be unadjusted")
    if str(manifest.get("interval", "")) != "1d":
        raise KiwoomPrimaryMarketError("Kiwoom primary market snapshot must use 1d candles")
    for name in ("prices.csv", "candles.csv", "technical_features.csv", "raw_prices.json"):
        if not (directory / name).is_file():
            raise KiwoomPrimaryMarketError(f"Kiwoom primary market file is missing: {name}")
    captured_at = _aware_datetime(manifest.get("captured_at"), "market captured_at")
    checked_at = (now or datetime.now(UTC)).astimezone(UTC)
    age_seconds = (checked_at - captured_at).total_seconds()
    if age_seconds < -60 or age_seconds > max_age_minutes * 60:
        raise KiwoomPrimaryMarketError("Kiwoom primary market snapshot is not fresh")
    source_payload = _object(directory / "raw_prices.json")
    if str(source_payload.get("source_provider", "")) != SOURCE_PROVIDER:
        raise KiwoomPrimaryMarketError("Kiwoom primary source provider is invalid")
    _sha256(source_payload.get("source_snapshot_id"), "source_snapshot_id")
    if str(source_payload.get("fallback_reason", "")) != "tossinvest_ip_allowlist":
        raise KiwoomPrimaryMarketError("Kiwoom primary fallback reason is invalid")
    if not _boolean(
        source_payload.get("read_only_market_failover_used"),
        "read_only_market_failover_used",
    ):
        raise KiwoomPrimaryMarketError("Kiwoom primary failover marker is missing")
    for field in (
        "cross_provider_price_certified",
        "automatic_provider_substitution_enabled",
        "account_api_enabled",
        "order_api_enabled",
    ):
        if _boolean(source_payload.get(field), field):
            raise KiwoomPrimaryMarketError(f"Kiwoom primary snapshot cannot enable {field}")
    return manifest


__all__ = [
    "DEFAULT_OUTPUT_ROOT",
    "EXPECTED_SYMBOLS",
    "KiwoomPrimaryMarketError",
    "KiwoomPrimarySnapshot",
    "LATEST_PRIMARY_NAME",
    "PRIMARY_PROVIDER",
    "ValidatedKiwoomExport",
    "build_kiwoom_primary_snapshot",
    "load_kiwoom_primary_manifest",
    "validate_latest_kiwoom_export",
    "write_kiwoom_primary_snapshot",
]
