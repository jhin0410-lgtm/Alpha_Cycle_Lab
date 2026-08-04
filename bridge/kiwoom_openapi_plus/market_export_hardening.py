"""Production hardening for the read-only Kiwoom market exporter.

This module is stdlib-only so it remains usable in the isolated Python 3.10 x86
bridge. It adds rolling OpenAPI+ request limits and immutable export-directory
allocation without changing TR parsing, account boundaries, or order behavior.
"""

from __future__ import annotations

import json
import time
from collections import deque
from collections.abc import Callable, Mapping
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Any

Clock = Callable[[], float]
Sleeper = Callable[[float], None]


class RollingRequestGate:
    """Enforce per-second, per-minute, and per-hour request ceilings."""

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


def build_immutable_writer(namespace: Mapping[str, Any]) -> Callable[..., Any]:
    """Create a writer using the exporter's own record and manifest contracts."""

    provider = namespace["PROVIDER"]
    quote_tr_code = namespace["QUOTE_TR_CODE"]
    daily_tr_code = namespace["DAILY_TR_CODE"]
    official_limits = namespace["OFFICIAL_LIMITS"]
    utc_zone = namespace["_UTC"]
    kst_zone = namespace["_KST"]
    manifest_type = namespace["ExportManifest"]
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
    ) -> tuple[Any, Path]:
        captured_utc = capture_now(utc_zone)
        captured_kst = captured_utc.astimezone(kst_zone)
        quote_rows = [asdict(value) for value in quotes]
        bar_rows = [asdict(value) for value in bars]
        hash_payload: dict[str, object] = {
            "provider": provider,
            "captured_at_utc": captured_utc.isoformat(),
            "symbols": list(symbols),
            "quotes": quote_rows,
            "daily_bars": bar_rows,
            "adjusted_prices": False,
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
        latest_path = output_root / "latest_market_export.json"
        write_csv(quotes_path, quote_rows)
        write_csv(bars_path, bar_rows)

        warnings = (
            "Only the first OpenAPI+ daily-chart response page is collected.",
            "The login server mode is not inspected because account/login-info APIs "
            "are outside this read-only market-data boundary.",
            "Kiwoom evidence is exported independently and is not a silent replacement "
            "for another market-data provider.",
        )
        manifest = manifest_type(
            schema_version="1.1",
            status="completed",
            provider=provider,
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
            request_count=exporter.request_count,
            request_interval_seconds=exporter.request_gate.interval_seconds,
            official_request_limits=official_limits,
            quote_tr_code=quote_tr_code,
            daily_tr_code=daily_tr_code,
            quotes_file=quotes_path.name,
            daily_bars_file=bars_path.name,
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
            "snapshot_id": manifest.snapshot_id,
            "captured_at_utc": manifest.captured_at_utc,
            "captured_at_kst": manifest.captured_at_kst,
            "symbols": list(manifest.symbols),
            "export_directory": str(export_directory),
            "manifest_path": str(manifest_path),
            "quote_count": manifest.quote_count,
            "daily_bar_count": manifest.daily_bar_count,
            "adjusted_prices": manifest.adjusted_prices,
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
    """Replace only the exporter request gate and artifact writer."""

    namespace["RequestGate"] = RollingRequestGate
    namespace["write_export"] = build_immutable_writer(namespace)
