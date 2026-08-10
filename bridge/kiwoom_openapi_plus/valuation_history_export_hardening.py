"""Hardening for isolated unadjusted Kiwoom valuation-history exports.

This module deliberately preserves the base exporter's opt10081
``수정주가구분=0`` request.  The resulting prices are intended only for
historical market-cap / valuation reconstruction with contemporaneous share
counts.  They must never replace the adjusted primary market series used for
technical analysis or live market evidence.

The module is stdlib-only so it remains usable in the isolated Python 3.10 x86
Kiwoom bridge.
"""

from __future__ import annotations

import json
import time
from collections import deque
from collections.abc import Callable, Mapping
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

Clock = Callable[[], float]
Sleeper = Callable[[float], None]

SOURCE_SCOPE = "kiwoom_opt10081_unadjusted_historical_valuation_prices"
PURPOSE = "historical_valuation_price_reconstruction"
LATEST_POINTER_NAME = "latest_valuation_history_export.json"


@dataclass(frozen=True)
class ValuationHistoryExportManifest:
    schema_version: str
    status: str
    provider: str
    source_scope: str
    purpose: str
    snapshot_id: str
    captured_at_utc: str
    captured_at_kst: str
    login_event_code: int
    connected: bool
    session_mode: str
    symbols: tuple[str, ...]
    quote_count: int
    daily_bar_count: int
    daily_bar_limit_per_symbol: int
    adjusted_prices: bool
    price_basis: str
    adjustment_request_value: str
    request_count: int
    request_interval_seconds: float
    official_request_limits: dict[str, int]
    quote_tr_code: str
    daily_tr_code: str
    quotes_file: str
    daily_bars_file: str
    historical_valuation_use_only: bool
    primary_market_evidence_eligible: bool
    technical_indicator_eligible: bool
    decision_score_enabled: bool
    point_in_time_backtest_eligible: bool
    account_api_enabled: bool
    order_api_enabled: bool
    warnings: tuple[str, ...]
    provider_messages: tuple[str, ...]


class RollingRequestGate:
    """Enforce conservative per-second, per-minute, and per-hour TR limits."""

    def __init__(
        self,
        interval_seconds: float = 0.25,
        *,
        per_minute: int = 100,
        per_hour: int = 1000,
        clock: Clock = time.monotonic,
        sleeper: Sleeper = time.sleep,
    ) -> None:
        if interval_seconds < 0.25:
            raise ValueError("request interval must enforce at most four requests per second")
        if per_minute <= 0 or per_hour <= 0:
            raise ValueError("rolling request limits must be positive")
        self.interval_seconds = interval_seconds
        self.per_minute = per_minute
        self.per_hour = per_hour
        self._clock = clock
        self._sleeper = sleeper
        self._requests: deque[float] = deque()

    def _prune(self, now: float) -> None:
        while self._requests and now - self._requests[0] >= 3600.0:
            self._requests.popleft()

    def _required_delay(self, now: float) -> float:
        delay = 0.0
        if self._requests:
            delay = max(delay, self.interval_seconds - (now - self._requests[-1]))
        minute_requests = [
            timestamp for timestamp in self._requests if now - timestamp < 60.0
        ]
        if len(minute_requests) >= self.per_minute:
            delay = max(delay, 60.0 - (now - minute_requests[0]))
        if len(self._requests) >= self.per_hour:
            delay = max(delay, 3600.0 - (now - self._requests[0]))
        return max(delay, 0.0)

    def wait(self) -> None:
        while True:
            now = self._clock()
            self._prune(now)
            delay = self._required_delay(now)
            if delay <= 0:
                self._requests.append(now)
                return
            self._sleeper(delay)


def _strict_unadjusted_bars(bars: list[Any]) -> None:
    if not bars:
        raise ValueError("Kiwoom valuation-history export requires daily bars")
    if any(getattr(bar, "adjusted", None) is not False for bar in bars):
        raise ValueError("Kiwoom valuation-history export requires unadjusted daily bars only")


def build_immutable_writer(namespace: Mapping[str, Any]) -> Callable[..., Any]:
    """Create a separate immutable writer for valuation-history evidence."""

    provider = namespace["PROVIDER"]
    quote_tr_code = namespace["QUOTE_TR_CODE"]
    daily_tr_code = namespace["DAILY_TR_CODE"]
    official_limits = namespace["OFFICIAL_LIMITS"]
    utc_zone = namespace["_UTC"]
    kst_zone = namespace["_KST"]
    snapshot_id = namespace["_snapshot_id"]
    write_csv = namespace["_write_csv"]
    atomic_text = namespace["_atomic_text"]
    capture_now = namespace.get("_capture_now", datetime.now)

    def write_export(
        *,
        output_root: Path,
        symbols: tuple[str, ...],
        daily_count: int,
        quotes: list[Any],
        bars: list[Any],
        exporter: Any,
    ) -> tuple[ValuationHistoryExportManifest, Path]:
        _strict_unadjusted_bars(bars)
        captured_utc = capture_now(utc_zone)
        captured_kst = captured_utc.astimezone(kst_zone)
        quote_rows = [asdict(value) for value in quotes]
        bar_rows = [asdict(value) for value in bars]
        hash_payload: dict[str, object] = {
            "provider": provider,
            "source_scope": SOURCE_SCOPE,
            "purpose": PURPOSE,
            "captured_at_utc": captured_utc.isoformat(),
            "symbols": list(symbols),
            "quotes": quote_rows,
            "daily_bars": bar_rows,
            "adjusted_prices": False,
            "price_basis": "unadjusted",
            "adjustment_request_value": "0",
        }
        identity = snapshot_id(hash_payload)
        directory_name = (
            captured_kst.strftime("%Y%m%dT%H%M%S%f%z")
            + "__"
            + identity[:12]
        )
        output_root.mkdir(parents=True, exist_ok=True)
        export_directory = output_root / directory_name
        export_directory.mkdir(exist_ok=False)

        quotes_path = export_directory / "quotes.csv"
        bars_path = export_directory / "daily_bars.csv"
        manifest_path = export_directory / "manifest.json"
        latest_path = output_root / LATEST_POINTER_NAME
        write_csv(quotes_path, quote_rows)
        write_csv(bars_path, bar_rows)

        warnings = (
            "Only the first OpenAPI+ daily-chart response page is collected.",
            "opt10081 수정주가구분=0 is preserved for historical valuation reconstruction.",
            "Unadjusted prices must be paired with contemporaneous share counts; do not "
            "use this artifact for live technical indicators or as primary market evidence.",
            "Point-in-time valuation/backtest eligibility remains disabled until historical "
            "share-count and financial-statement availability dates are bound and verified.",
            "Account, holdings, balance, and order APIs remain outside this evidence boundary.",
        )
        manifest = ValuationHistoryExportManifest(
            schema_version="1.0",
            status="completed",
            provider=provider,
            source_scope=SOURCE_SCOPE,
            purpose=PURPOSE,
            snapshot_id=identity,
            captured_at_utc=captured_utc.isoformat(),
            captured_at_kst=captured_kst.isoformat(),
            login_event_code=int(exporter.login_event_code or 0),
            connected=bool(exporter.connected),
            session_mode="user_selected_login_server",
            symbols=symbols,
            quote_count=len(quotes),
            daily_bar_count=len(bars),
            daily_bar_limit_per_symbol=daily_count,
            adjusted_prices=False,
            price_basis="unadjusted",
            adjustment_request_value="0",
            request_count=exporter.request_count,
            request_interval_seconds=exporter.request_gate.interval_seconds,
            official_request_limits=official_limits,
            quote_tr_code=quote_tr_code,
            daily_tr_code=daily_tr_code,
            quotes_file=quotes_path.name,
            daily_bars_file=bars_path.name,
            historical_valuation_use_only=True,
            primary_market_evidence_eligible=False,
            technical_indicator_eligible=False,
            decision_score_enabled=False,
            point_in_time_backtest_eligible=False,
            account_api_enabled=False,
            order_api_enabled=False,
            warnings=warnings,
            provider_messages=exporter.provider_messages,
        )
        atomic_text(
            manifest_path,
            json.dumps(asdict(manifest), ensure_ascii=False, indent=2, sort_keys=True),
        )
        latest_payload = {
            "status": manifest.status,
            "provider": manifest.provider,
            "source_scope": manifest.source_scope,
            "purpose": manifest.purpose,
            "snapshot_id": manifest.snapshot_id,
            "captured_at_utc": manifest.captured_at_utc,
            "captured_at_kst": manifest.captured_at_kst,
            "symbols": list(manifest.symbols),
            "export_directory": str(export_directory),
            "manifest_path": str(manifest_path),
            "quote_count": manifest.quote_count,
            "daily_bar_count": manifest.daily_bar_count,
            "adjusted_prices": False,
            "price_basis": "unadjusted",
            "adjustment_request_value": "0",
            "historical_valuation_use_only": True,
            "primary_market_evidence_eligible": False,
            "technical_indicator_eligible": False,
            "decision_score_enabled": False,
            "point_in_time_backtest_eligible": False,
            "account_api_enabled": False,
            "order_api_enabled": False,
        }
        atomic_text(
            latest_path,
            json.dumps(latest_payload, ensure_ascii=False, indent=2, sort_keys=True),
        )
        return manifest, export_directory

    return write_export


def apply_hardening(namespace: dict[str, Any]) -> None:
    """Keep base unadjusted collection and install only safety/immutable layers."""

    exporter_type = namespace["KiwoomMarketExporter"]
    original_daily_bars = exporter_type.daily_bars
    namespace["RequestGate"] = RollingRequestGate
    namespace["ExportManifest"] = ValuationHistoryExportManifest
    namespace["DEFAULT_OUTPUT_ROOT"] = Path(
        "data/private/live-research/kiwoom-openapi-plus-valuation-history"
    )
    namespace["write_export"] = build_immutable_writer(namespace)
    if exporter_type.daily_bars is not original_daily_bars:
        raise RuntimeError("valuation-history hardening must preserve base unadjusted collector")
