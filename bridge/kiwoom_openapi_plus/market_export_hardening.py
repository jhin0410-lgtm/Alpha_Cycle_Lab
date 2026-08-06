"""Production hardening for the read-only Kiwoom market exporter.

This module is stdlib-only so it remains usable in the isolated Python 3.10 x86
bridge. It adds rolling request limits, adjusted-price collection, corporate-
action response evidence, and immutable export-directory allocation without
expanding the public-market-data boundary.
"""

from __future__ import annotations

import json
import re
import time
from collections import deque
from collections.abc import Callable, Mapping
from dataclasses import asdict, dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

Clock = Callable[[], float]
Sleeper = Callable[[float], None]


@dataclass(frozen=True)
class AdjustedExportManifest:
    schema_version: str
    status: str
    provider: str
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
    request_count: int
    request_interval_seconds: float
    official_request_limits: dict[str, int]
    quote_tr_code: str
    daily_tr_code: str
    quotes_file: str
    daily_bars_file: str
    adjustment_evidence_file: str
    price_basis: str
    adjustment_request_value: str
    corporate_action_row_count: int
    account_api_enabled: bool
    order_api_enabled: bool
    warnings: tuple[str, ...]
    provider_messages: tuple[str, ...]


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


def _install_adjusted_daily_collection(namespace: dict[str, Any]) -> None:
    """Replace opt10081 parsing with adjusted-price, evidence-preserving logic."""

    exporter_type = namespace["KiwoomMarketExporter"]
    daily_type = namespace["DailyBar"]
    clean = namespace["_clean"]
    integer = namespace["_integer"]
    daily_tr_code = namespace["DAILY_TR_CODE"]

    def adjusted_daily_payload(
        self: Any,
        *,
        screen_no: str,
        request_name: str,
        tr_code: str,
        previous_next: str,
    ) -> dict[str, object]:
        repeat = int(
            self.control.dynamicCall(
                "GetRepeatCnt(QString, QString)",
                tr_code,
                request_name,
            )
        )
        fields = {
            "date": "일자",
            "current_price": "현재가",
            "volume": "거래량",
            "trading_value": "거래대금",
            "open_price": "시가",
            "high_price": "고가",
            "low_price": "저가",
            "adjustment_code": "수정주가구분",
            "adjustment_ratio": "수정비율",
            "adjustment_event": "수정주가이벤트",
            "previous_close": "전일종가",
        }
        rows: list[dict[str, str]] = []
        for index in range(max(repeat, 0)):
            rows.append(
                {
                    key: self._comm_data(tr_code, request_name, index, label)
                    for key, label in fields.items()
                }
            )
        return {
            "kind": "daily",
            "screen_no": screen_no,
            "request_name": request_name,
            "tr_code": tr_code,
            "previous_next": previous_next,
            "rows": rows,
        }

    def adjusted_daily_bars(
        self: Any,
        ticker: str,
        *,
        screen_no: str,
        reference_date: str,
        limit: int,
    ) -> list[Any]:
        request_name = f"daily_{ticker}"
        payload = self._request(
            request_name=request_name,
            tr_code=daily_tr_code,
            screen_no=screen_no,
            inputs=(
                ("종목코드", ticker),
                ("기준일자", reference_date),
                ("수정주가구분", "1"),
            ),
        )
        rows_object = payload.get("rows")
        if not isinstance(rows_object, list):
            raise RuntimeError(f"daily payload missing rows for {ticker}")
        bars: list[Any] = []
        evidence = getattr(self, "adjustment_evidence", None)
        if not isinstance(evidence, list):
            evidence = []
            self.adjustment_evidence = evidence
        for row_object in rows_object[:limit]:
            if not isinstance(row_object, dict):
                continue
            raw = {str(key): clean(value) for key, value in row_object.items()}
            date = raw.get("date", "")
            open_price = integer(raw.get("open_price", ""), absolute=True)
            high_price = integer(raw.get("high_price", ""), absolute=True)
            low_price = integer(raw.get("low_price", ""), absolute=True)
            close_price = integer(raw.get("current_price", ""), absolute=True)
            volume = integer(raw.get("volume", ""), absolute=True)
            if (
                not re.fullmatch(r"[0-9]{8}", date)
                or open_price is None
                or high_price is None
                or low_price is None
                or close_price is None
                or volume is None
            ):
                continue
            bars.append(
                daily_type(
                    ticker=ticker,
                    date=date,
                    open_price=open_price,
                    high_price=high_price,
                    low_price=low_price,
                    close_price=close_price,
                    volume=volume,
                    trading_value=integer(
                        raw.get("trading_value", ""), absolute=True
                    ),
                    open_price_raw=raw.get("open_price", ""),
                    high_price_raw=raw.get("high_price", ""),
                    low_price_raw=raw.get("low_price", ""),
                    close_price_raw=raw.get("current_price", ""),
                    volume_raw=raw.get("volume", ""),
                    trading_value_raw=raw.get("trading_value", ""),
                    adjusted=True,
                    request_name=request_name,
                    tr_code=str(payload.get("tr_code", daily_tr_code)),
                    screen_no=str(payload.get("screen_no", screen_no)),
                )
            )
            evidence.append(
                {
                    "ticker": ticker,
                    "date": date,
                    "requested_price_basis": "adjusted",
                    "adjustment_request_value": "1",
                    "response_adjustment_code_raw": raw.get(
                        "adjustment_code", ""
                    ),
                    "response_adjustment_ratio_raw": raw.get(
                        "adjustment_ratio", ""
                    ),
                    "response_adjustment_event_raw": raw.get(
                        "adjustment_event", ""
                    ),
                    "previous_close_raw": raw.get("previous_close", ""),
                }
            )
        if not bars:
            raise RuntimeError(f"no valid Kiwoom daily bars returned for {ticker}")
        return bars

    exporter_type._daily_payload = adjusted_daily_payload
    exporter_type.daily_bars = adjusted_daily_bars


def _has_corporate_action(row: Mapping[str, object]) -> bool:
    event = str(row.get("response_adjustment_event_raw", "")).strip()
    if event.casefold() not in {"", "0", "none", "null", "n/a"}:
        return True

    raw_ratio = str(row.get("response_adjustment_ratio_raw", "")).strip()
    if not raw_ratio:
        return False
    normalized = raw_ratio.replace(",", "").replace("%", "")
    try:
        ratio = Decimal(normalized)
    except InvalidOperation:
        return False
    return ratio.is_finite() and ratio != 0


def build_immutable_writer(namespace: Mapping[str, Any]) -> Callable[..., Any]:
    """Create an immutable writer for adjusted bars and source response evidence."""

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
        if not bars or any(getattr(bar, "adjusted", None) is not True for bar in bars):
            raise ValueError("Kiwoom primary export requires adjusted daily bars only")
        adjustment_rows = getattr(exporter, "adjustment_evidence", None)
        if not isinstance(adjustment_rows, list) or len(adjustment_rows) != len(bars):
            raise ValueError(
                "adjustment response evidence must cover every exported daily bar"
            )
        for row in adjustment_rows:
            if (
                row.get("requested_price_basis") != "adjusted"
                or row.get("adjustment_request_value") != "1"
            ):
                raise ValueError("adjustment evidence contains an unexpected price basis")

        captured_utc = capture_now(utc_zone)
        captured_kst = captured_utc.astimezone(kst_zone)
        quote_rows = [asdict(value) for value in quotes]
        bar_rows = [asdict(value) for value in bars]
        action_count = sum(_has_corporate_action(row) for row in adjustment_rows)
        hash_payload: dict[str, object] = {
            "provider": provider,
            "captured_at_utc": captured_utc.isoformat(),
            "symbols": list(symbols),
            "quotes": quote_rows,
            "daily_bars": bar_rows,
            "adjustment_evidence": adjustment_rows,
            "adjusted_prices": True,
            "price_basis": "adjusted",
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
        adjustment_path = export_directory / "adjustment_evidence.csv"
        manifest_path = export_directory / "manifest.json"
        latest_path = output_root / "latest_market_export.json"
        write_csv(quotes_path, quote_rows)
        write_csv(bars_path, bar_rows)
        write_csv(adjustment_path, adjustment_rows)

        warnings = (
            "Only the first OpenAPI+ daily-chart response page is collected.",
            "Adjusted-price basis was requested with opt10081 수정주가구분=1.",
            "Corporate-action response fields are preserved without inferring an "
            "event when the provider returns empty metadata.",
            "The login server mode is not inspected because account/login-info APIs "
            "are outside this read-only market-data boundary.",
            "Kiwoom evidence is exported independently and is not a silent replacement "
            "for another market-data provider.",
        )
        manifest = manifest_type(
            schema_version="1.2",
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
            adjusted_prices=True,
            request_count=exporter.request_count,
            request_interval_seconds=exporter.request_gate.interval_seconds,
            official_request_limits=official_limits,
            quote_tr_code=quote_tr_code,
            daily_tr_code=daily_tr_code,
            quotes_file=quotes_path.name,
            daily_bars_file=bars_path.name,
            adjustment_evidence_file=adjustment_path.name,
            price_basis="adjusted",
            adjustment_request_value="1",
            corporate_action_row_count=action_count,
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
            "adjusted_prices": True,
            "price_basis": "adjusted",
            "adjustment_evidence_file": manifest.adjustment_evidence_file,
            "corporate_action_row_count": action_count,
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
    """Apply request limits, adjusted-price collection, and immutable writing."""

    namespace["RequestGate"] = RollingRequestGate
    namespace["ExportManifest"] = AdjustedExportManifest
    _install_adjusted_daily_collection(namespace)
    namespace["write_export"] = build_immutable_writer(namespace)
