"""Collection orchestration and immutable market-intelligence snapshots."""

from __future__ import annotations

import csv
import hashlib
import json
import shutil
from collections.abc import Callable, Mapping
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

from alpha_cycle.intelligence.technical import (
    TechnicalFeatures,
    add_relative_strength_ranks,
    calculate_technical_features,
)
from alpha_cycle.providers.tossinvest import Candle, MarketPrice, TossInvestReadOnlyClient

SNAPSHOT_SCHEMA_VERSION = 1


def _json_default(value: object) -> object:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    raise TypeError(f"Unsupported snapshot value: {type(value).__name__}")


def _canonical_json(value: object) -> str:
    return json.dumps(
        value,
        default=_json_default,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )


@dataclass(frozen=True)
class MarketIntelligenceSnapshot:
    captured_at: datetime
    provider: str
    interval: str
    adjusted: bool
    prices: tuple[MarketPrice, ...]
    candles: tuple[Candle, ...]
    features: tuple[TechnicalFeatures, ...]
    raw_prices: object
    raw_candles: Mapping[str, object]

    def __post_init__(self) -> None:
        if self.captured_at.tzinfo is None or self.captured_at.utcoffset() is None:
            raise ValueError("captured_at must be timezone-aware")
        if self.interval not in {"1m", "1d"}:
            raise ValueError("interval must be 1m or 1d")
        symbols = tuple(item.symbol for item in self.prices)
        if symbols != tuple(sorted(set(symbols))):
            raise ValueError("Snapshot prices must be unique and sorted by symbol")
        feature_symbols = tuple(item.symbol for item in self.features)
        if feature_symbols != symbols:
            raise ValueError("Snapshot feature symbols must match price symbols")
        candle_symbols = {item.symbol for item in self.candles}
        if candle_symbols != set(symbols):
            raise ValueError("Snapshot candle symbols must match price symbols")

    @property
    def symbols(self) -> tuple[str, ...]:
        return tuple(item.symbol for item in self.prices)

    def payload_without_id(self) -> dict[str, object]:
        return {
            "schema_version": SNAPSHOT_SCHEMA_VERSION,
            "captured_at": self.captured_at.isoformat(),
            "provider": self.provider,
            "interval": self.interval,
            "adjusted": self.adjusted,
            "prices": [asdict(item) for item in self.prices],
            "candles": [asdict(item) for item in self.candles],
            "features": [item.to_dict() for item in self.features],
            "raw_prices": self.raw_prices,
            "raw_candles": dict(self.raw_candles),
        }

    @property
    def snapshot_id(self) -> str:
        encoded = _canonical_json(self.payload_without_id()).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()


class MarketIntelligenceCollector:
    """Collect one read-only price/candle snapshot and calculate features."""

    def __init__(
        self,
        client: TossInvestReadOnlyClient,
        *,
        now: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self.client = client
        self.now = now

    def collect(
        self,
        symbols: list[str] | tuple[str, ...],
        *,
        interval: str,
        count: int,
        adjusted: bool,
    ) -> MarketIntelligenceSnapshot:
        normalized = tuple(
            sorted(set(symbol.strip().upper() for symbol in symbols if symbol.strip()))
        )
        if not normalized:
            raise ValueError("At least one symbol is required")
        price_batch = self.client.prices(normalized)
        all_candles: list[Candle] = []
        raw_candles: dict[str, object] = {}
        calculated: list[TechnicalFeatures] = []
        for symbol in normalized:
            batch = self.client.candles(
                symbol,
                interval=interval,
                count=count,
                adjusted=adjusted,
            )
            if not batch.candles:
                raise ValueError(f"TossInvest returned no candles for {symbol}")
            all_candles.extend(batch.candles)
            raw_candles[symbol] = batch.raw_payload
            calculated.append(calculate_technical_features(batch.candles))
        ranked = add_relative_strength_ranks(
            tuple(sorted(calculated, key=lambda item: item.symbol))
        )
        prices = tuple(sorted(price_batch.prices, key=lambda item: item.symbol))
        price_currency = {item.symbol: item.currency for item in prices}
        for candle in all_candles:
            if candle.currency != price_currency[candle.symbol]:
                raise ValueError(f"Currency mismatch for {candle.symbol}")
        captured_at = self.now()
        if captured_at.tzinfo is None or captured_at.utcoffset() is None:
            raise ValueError("Collector clock must return a timezone-aware datetime")
        return MarketIntelligenceSnapshot(
            captured_at=captured_at,
            provider="tossinvest-readonly",
            interval=interval,
            adjusted=adjusted,
            prices=prices,
            candles=tuple(sorted(all_candles, key=lambda item: (item.symbol, item.timestamp))),
            features=ranked,
            raw_prices=price_batch.raw_payload,
            raw_candles=raw_candles,
        )


def _write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, object]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def write_market_intelligence_snapshot(
    output_root: str | Path,
    snapshot: MarketIntelligenceSnapshot,
) -> tuple[Path, ...]:
    """Atomically write a content-addressed immutable local snapshot directory."""
    root = Path(output_root)
    root.mkdir(parents=True, exist_ok=True)
    timestamp = snapshot.captured_at.astimezone(UTC).strftime("%Y%m%dT%H%M%S%fZ")
    directory_name = f"{timestamp}__{snapshot.snapshot_id[:12]}"
    destination = root / directory_name
    expected_names = (
        "manifest.json",
        "prices.csv",
        "candles.csv",
        "technical_features.csv",
        "raw_prices.json",
        "raw_candles.json",
    )
    if destination.exists():
        manifest_path = destination / "manifest.json"
        if not manifest_path.is_file():
            raise ValueError("Existing snapshot directory is incomplete")
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if not isinstance(manifest, dict) or manifest.get("snapshot_id") != snapshot.snapshot_id:
            raise ValueError("Existing snapshot directory conflicts with the requested snapshot")
        return tuple(destination / name for name in expected_names)

    temporary = root / f".{directory_name}.tmp"
    if temporary.exists():
        shutil.rmtree(temporary)
    temporary.mkdir(parents=False)
    try:
        price_rows = [
            {
                "symbol": item.symbol,
                "timestamp": item.timestamp.isoformat(),
                "last_price": str(item.last_price),
                "currency": item.currency,
            }
            for item in snapshot.prices
        ]
        candle_rows = [
            {
                "symbol": item.symbol,
                "timestamp": item.timestamp.isoformat(),
                "open": str(item.open_price),
                "high": str(item.high_price),
                "low": str(item.low_price),
                "close": str(item.close_price),
                "volume": str(item.volume),
                "currency": item.currency,
                "interval": item.interval,
                "adjusted": item.adjusted,
            }
            for item in snapshot.candles
        ]
        feature_rows = [item.to_dict() for item in snapshot.features]
        _write_csv(
            temporary / "prices.csv",
            ["symbol", "timestamp", "last_price", "currency"],
            price_rows,
        )
        _write_csv(
            temporary / "candles.csv",
            [
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
            ],
            candle_rows,
        )
        _write_csv(
            temporary / "technical_features.csv",
            list(feature_rows[0].keys()),
            feature_rows,
        )
        (temporary / "raw_prices.json").write_text(
            json.dumps(snapshot.raw_prices, ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        (temporary / "raw_candles.json").write_text(
            json.dumps(dict(snapshot.raw_candles), ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        manifest = {
            "schema_version": SNAPSHOT_SCHEMA_VERSION,
            "snapshot_id": snapshot.snapshot_id,
            "captured_at": snapshot.captured_at.isoformat(),
            "provider": snapshot.provider,
            "interval": snapshot.interval,
            "adjusted": snapshot.adjusted,
            "symbols": list(snapshot.symbols),
            "files": list(expected_names[1:]),
            "order_api_enabled": False,
        }
        (temporary / "manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        temporary.rename(destination)
    except Exception:
        if temporary.exists():
            shutil.rmtree(temporary)
        raise
    return tuple(destination / name for name in expected_names)
