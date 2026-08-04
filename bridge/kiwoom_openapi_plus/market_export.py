"""Read-only Kiwoom OpenAPI+ quote and daily-bar exporter.

The exporter runs only in the isolated Windows x86 bridge. It requests public
market data, writes source-provenanced local artifacts, and exposes no holdings,
balance, account-number, or order functions.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import platform
import re
import struct
import sys
import time
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

OPENAPI_PROGID = "KHOPENAPI.KHOpenAPICtrl.1"
PROVIDER = "kiwoom_openapi_plus"
QUOTE_TR_CODE = "opt10001"
DAILY_TR_CODE = "opt10081"
DEFAULT_SYMBOLS = ("005930", "005935", "000660")
DEFAULT_OUTPUT_ROOT = Path(
    "data/private/live-research/kiwoom-openapi-plus-market"
)
MAX_REQUESTS_PER_SECOND = 4
MIN_REQUEST_INTERVAL_SECONDS = 1.0 / MAX_REQUESTS_PER_SECOND
OFFICIAL_LIMITS = {
    "per_second": 5,
    "per_minute": 100,
    "per_hour": 1000,
}
_TICKER = re.compile(r"^[0-9]{6}$")
_KST = ZoneInfo("Asia/Seoul")
_UTC = ZoneInfo("UTC")


@dataclass(frozen=True)
class QuoteRecord:
    ticker: str
    name: str
    current_price: int
    change: int | None
    change_percent: float | None
    volume: int | None
    open_price: int | None
    high_price: int | None
    low_price: int | None
    base_price: int | None
    current_price_raw: str
    change_raw: str
    change_percent_raw: str
    volume_raw: str
    open_price_raw: str
    high_price_raw: str
    low_price_raw: str
    base_price_raw: str
    request_name: str
    tr_code: str
    screen_no: str
    previous_next: str


@dataclass(frozen=True)
class DailyBar:
    ticker: str
    date: str
    open_price: int
    high_price: int
    low_price: int
    close_price: int
    volume: int
    trading_value: int | None
    open_price_raw: str
    high_price_raw: str
    low_price_raw: str
    close_price_raw: str
    volume_raw: str
    trading_value_raw: str
    adjusted: bool
    request_name: str
    tr_code: str
    screen_no: str


@dataclass(frozen=True)
class ExportManifest:
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
    account_api_enabled: bool
    order_api_enabled: bool
    warnings: tuple[str, ...]
    provider_messages: tuple[str, ...]


class RequestGate:
    """Serialize TR requests below the documented OpenAPI+ per-second limit."""

    def __init__(self, interval_seconds: float = MIN_REQUEST_INTERVAL_SECONDS) -> None:
        if interval_seconds < MIN_REQUEST_INTERVAL_SECONDS:
            raise ValueError("request interval must enforce at most four requests per second")
        self.interval_seconds = interval_seconds
        self._last_request_at: float | None = None

    def wait(self) -> None:
        now = time.monotonic()
        if self._last_request_at is not None:
            remaining = self.interval_seconds - (now - self._last_request_at)
            if remaining > 0:
                time.sleep(remaining)
        self._last_request_at = time.monotonic()


def _load_qt() -> tuple[Any, Any, Any, str, str]:
    try:
        from PyQt5 import QtCore, QtWidgets
        from PyQt5.QAxContainer import QAxWidget
    except ImportError as exc:
        raise RuntimeError(
            "PyQt5 with QAxContainer is not installed in the x86 bridge environment"
        ) from exc
    return QtCore, QtWidgets, QAxWidget, QtCore.PYQT_VERSION_STR, QtCore.QT_VERSION_STR


def _create_control(qax_widget: Any) -> Any:
    control = qax_widget()
    created = bool(control.setControl(OPENAPI_PROGID))
    if not created or bool(control.isNull()):
        raise RuntimeError("KHOpenAPI ActiveX control could not be created")
    return control


def _clean(raw: object) -> str:
    return str(raw).strip()


def _integer(raw: object, *, absolute: bool = False) -> int | None:
    text = _clean(raw).replace(",", "")
    if not text:
        return None
    try:
        value = int(text)
    except ValueError:
        try:
            value = int(float(text))
        except ValueError:
            return None
    return abs(value) if absolute else value


def _decimal(raw: object) -> float | None:
    text = _clean(raw).replace(",", "").replace("%", "")
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _validate_symbols(symbols: list[str] | tuple[str, ...]) -> tuple[str, ...]:
    normalized: list[str] = []
    seen: set[str] = set()
    for raw in symbols:
        ticker = raw.strip()
        if not _TICKER.fullmatch(ticker):
            raise ValueError(f"invalid six-digit Korean ticker: {raw}")
        if ticker not in seen:
            seen.add(ticker)
            normalized.append(ticker)
    if not normalized:
        raise ValueError("at least one ticker is required")
    return tuple(normalized)


class KiwoomMarketExporter:
    """Single-process, sequential, read-only OpenAPI+ TR collector."""

    def __init__(
        self,
        *,
        timeout_seconds: int,
        request_gate: RequestGate | None = None,
    ) -> None:
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        if platform.system() != "Windows":
            raise RuntimeError("Kiwoom OpenAPI+ market export requires Windows")
        if struct.calcsize("P") * 8 != 32:
            raise RuntimeError("Kiwoom OpenAPI+ market export requires 32-bit Python")

        qt_core, qt_widgets, qax_widget, pyqt_version, qt_version = _load_qt()
        self.qt_core = qt_core
        self.pyqt_version = pyqt_version
        self.qt_version = qt_version
        self.timeout_seconds = timeout_seconds
        self.request_gate = request_gate or RequestGate()
        self.application = qt_widgets.QApplication.instance()
        if self.application is None:
            self.application = qt_widgets.QApplication(
                ["alpha-cycle-kiwoom-market-export"]
            )
        self.control = _create_control(qax_widget)
        self.control.OnEventConnect.connect(self._on_event_connect)
        self.control.OnReceiveTrData.connect(self._on_receive_tr_data)
        if hasattr(self.control, "OnReceiveMsg"):
            self.control.OnReceiveMsg.connect(self._on_receive_message)

        self.login_event_code: int | None = None
        self.connected = False
        self._login_loop: Any = None
        self._request_loop: Any = None
        self._pending_request_name: str | None = None
        self._pending_payload: dict[str, object] | None = None
        self._provider_messages: list[str] = []
        self.request_count = 0

    def _connection_state(self) -> bool:
        try:
            return int(self.control.dynamicCall("GetConnectState()")) == 1
        except (TypeError, ValueError):
            return False

    def _on_event_connect(self, error_code: int) -> None:
        self.login_event_code = int(error_code)
        self.connected = self.login_event_code == 0 and self._connection_state()
        if self._login_loop is not None:
            self._login_loop.quit()

    def _on_receive_message(
        self,
        screen_no: object,
        request_name: object,
        tr_code: object,
        message: object,
    ) -> None:
        safe_message = " ".join(_clean(message).split())
        if safe_message:
            self._provider_messages.append(
                f"screen={_clean(screen_no)} request={_clean(request_name)} "
                f"tr={_clean(tr_code)} message={safe_message}"
            )

    def _comm_data(
        self,
        tr_code: str,
        request_name: str,
        index: int,
        field: str,
    ) -> str:
        value = self.control.dynamicCall(
            "GetCommData(QString, QString, int, QString)",
            tr_code,
            request_name,
            index,
            field,
        )
        return _clean(value)

    def _quote_payload(
        self,
        *,
        screen_no: str,
        request_name: str,
        tr_code: str,
        previous_next: str,
    ) -> dict[str, object]:
        fields = {
            "name": "종목명",
            "current_price": "현재가",
            "change": "전일대비",
            "change_percent": "등락율",
            "volume": "거래량",
            "open_price": "시가",
            "high_price": "고가",
            "low_price": "저가",
            "base_price": "기준가",
        }
        raw = {
            key: self._comm_data(tr_code, request_name, 0, label)
            for key, label in fields.items()
        }
        return {
            "kind": "quote",
            "screen_no": screen_no,
            "request_name": request_name,
            "tr_code": tr_code,
            "previous_next": previous_next,
            "raw": raw,
        }

    def _daily_payload(
        self,
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

    def _on_receive_tr_data(
        self,
        screen_no: object,
        request_name: object,
        tr_code: object,
        _record_name: object,
        previous_next: object,
        _data_length: object,
        error_code: object,
        message: object,
        supplementary_message: object,
    ) -> None:
        received_request = _clean(request_name)
        if self._pending_request_name != received_request:
            return

        tr = _clean(tr_code)
        screen = _clean(screen_no)
        previous = _clean(previous_next)
        if received_request.startswith("quote_"):
            payload = self._quote_payload(
                screen_no=screen,
                request_name=received_request,
                tr_code=tr,
                previous_next=previous,
            )
        elif received_request.startswith("daily_"):
            payload = self._daily_payload(
                screen_no=screen,
                request_name=received_request,
                tr_code=tr,
                previous_next=previous,
            )
        else:
            payload = {"kind": "unknown"}

        payload["error_code"] = _clean(error_code)
        payload["message"] = _clean(message)
        payload["supplementary_message"] = _clean(supplementary_message)
        self._pending_payload = payload
        if self._request_loop is not None:
            self._request_loop.quit()

    def login(self) -> None:
        self._login_loop = self.qt_core.QEventLoop()
        timed_out = False

        def on_timeout() -> None:
            nonlocal timed_out
            timed_out = True
            self._login_loop.quit()

        timer = self.qt_core.QTimer()
        timer.setSingleShot(True)
        timer.timeout.connect(on_timeout)
        timer.start(self.timeout_seconds * 1000)
        try:
            result = int(self.control.dynamicCall("CommConnect()"))
        except (TypeError, ValueError) as exc:
            raise RuntimeError(f"CommConnect returned an invalid result: {exc}") from exc
        if result != 0:
            raise RuntimeError(f"CommConnect returned {result}")

        self._login_loop.exec_()
        timer.stop()
        self._login_loop = None
        if timed_out:
            raise TimeoutError("Kiwoom login event was not received before timeout")
        if self.login_event_code != 0 or not self.connected:
            raise RuntimeError(
                f"Kiwoom login failed with event code {self.login_event_code}"
            )

    def _request(
        self,
        *,
        request_name: str,
        tr_code: str,
        screen_no: str,
        inputs: tuple[tuple[str, str], ...],
    ) -> dict[str, object]:
        if not self.connected or not self._connection_state():
            raise RuntimeError("Kiwoom session is not connected")
        self.request_gate.wait()
        for name, value in inputs:
            self.control.dynamicCall(
                "SetInputValue(QString, QString)",
                name,
                value,
            )

        self._pending_request_name = request_name
        self._pending_payload = None
        self._request_loop = self.qt_core.QEventLoop()
        timed_out = False

        def on_timeout() -> None:
            nonlocal timed_out
            timed_out = True
            self._request_loop.quit()

        timer = self.qt_core.QTimer()
        timer.setSingleShot(True)
        timer.timeout.connect(on_timeout)
        timer.start(self.timeout_seconds * 1000)
        result = int(
            self.control.dynamicCall(
                "CommRqData(QString, QString, int, QString)",
                request_name,
                tr_code,
                0,
                screen_no,
            )
        )
        self.request_count += 1
        if result != 0:
            self._pending_request_name = None
            self._request_loop = None
            timer.stop()
            raise RuntimeError(
                f"CommRqData returned {result} for {request_name}/{tr_code}"
            )

        self._request_loop.exec_()
        timer.stop()
        self._request_loop = None
        self._pending_request_name = None
        if timed_out:
            raise TimeoutError(f"TR response timeout: {request_name}/{tr_code}")
        if self._pending_payload is None:
            raise RuntimeError(f"TR response payload missing: {request_name}/{tr_code}")
        payload = self._pending_payload
        self._pending_payload = None
        return payload

    def quote(self, ticker: str, screen_no: str) -> QuoteRecord:
        request_name = f"quote_{ticker}"
        payload = self._request(
            request_name=request_name,
            tr_code=QUOTE_TR_CODE,
            screen_no=screen_no,
            inputs=(("종목코드", ticker),),
        )
        raw_object = payload.get("raw")
        if not isinstance(raw_object, dict):
            raise RuntimeError(f"quote payload missing raw fields for {ticker}")
        raw = {str(key): _clean(value) for key, value in raw_object.items()}
        current_price = _integer(raw.get("current_price", ""), absolute=True)
        if current_price is None or current_price <= 0:
            raise RuntimeError(f"invalid Kiwoom current price for {ticker}")
        return QuoteRecord(
            ticker=ticker,
            name=raw.get("name", ""),
            current_price=current_price,
            change=_integer(raw.get("change", "")),
            change_percent=_decimal(raw.get("change_percent", "")),
            volume=_integer(raw.get("volume", ""), absolute=True),
            open_price=_integer(raw.get("open_price", ""), absolute=True),
            high_price=_integer(raw.get("high_price", ""), absolute=True),
            low_price=_integer(raw.get("low_price", ""), absolute=True),
            base_price=_integer(raw.get("base_price", ""), absolute=True),
            current_price_raw=raw.get("current_price", ""),
            change_raw=raw.get("change", ""),
            change_percent_raw=raw.get("change_percent", ""),
            volume_raw=raw.get("volume", ""),
            open_price_raw=raw.get("open_price", ""),
            high_price_raw=raw.get("high_price", ""),
            low_price_raw=raw.get("low_price", ""),
            base_price_raw=raw.get("base_price", ""),
            request_name=request_name,
            tr_code=str(payload.get("tr_code", QUOTE_TR_CODE)),
            screen_no=str(payload.get("screen_no", screen_no)),
            previous_next=str(payload.get("previous_next", "")),
        )

    def daily_bars(
        self,
        ticker: str,
        *,
        screen_no: str,
        reference_date: str,
        limit: int,
    ) -> list[DailyBar]:
        request_name = f"daily_{ticker}"
        payload = self._request(
            request_name=request_name,
            tr_code=DAILY_TR_CODE,
            screen_no=screen_no,
            inputs=(
                ("종목코드", ticker),
                ("기준일자", reference_date),
                ("수정주가구분", "0"),
            ),
        )
        rows_object = payload.get("rows")
        if not isinstance(rows_object, list):
            raise RuntimeError(f"daily payload missing rows for {ticker}")
        bars: list[DailyBar] = []
        for row_object in rows_object[:limit]:
            if not isinstance(row_object, dict):
                continue
            raw = {str(key): _clean(value) for key, value in row_object.items()}
            date = raw.get("date", "")
            open_price = _integer(raw.get("open_price", ""), absolute=True)
            high_price = _integer(raw.get("high_price", ""), absolute=True)
            low_price = _integer(raw.get("low_price", ""), absolute=True)
            close_price = _integer(raw.get("current_price", ""), absolute=True)
            volume = _integer(raw.get("volume", ""), absolute=True)
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
                DailyBar(
                    ticker=ticker,
                    date=date,
                    open_price=open_price,
                    high_price=high_price,
                    low_price=low_price,
                    close_price=close_price,
                    volume=volume,
                    trading_value=_integer(
                        raw.get("trading_value", ""), absolute=True
                    ),
                    open_price_raw=raw.get("open_price", ""),
                    high_price_raw=raw.get("high_price", ""),
                    low_price_raw=raw.get("low_price", ""),
                    close_price_raw=raw.get("current_price", ""),
                    volume_raw=raw.get("volume", ""),
                    trading_value_raw=raw.get("trading_value", ""),
                    adjusted=False,
                    request_name=request_name,
                    tr_code=str(payload.get("tr_code", DAILY_TR_CODE)),
                    screen_no=str(payload.get("screen_no", screen_no)),
                )
            )
        if not bars:
            raise RuntimeError(f"no valid Kiwoom daily bars returned for {ticker}")
        return bars

    @property
    def provider_messages(self) -> tuple[str, ...]:
        return tuple(self._provider_messages)


def collect_market_data(
    *,
    symbols: tuple[str, ...],
    daily_count: int,
    timeout_seconds: int,
    exporter_factory: Any = KiwoomMarketExporter,
) -> tuple[list[QuoteRecord], list[DailyBar], KiwoomMarketExporter]:
    if daily_count <= 0 or daily_count > 600:
        raise ValueError("daily_count must be between 1 and 600")
    exporter = exporter_factory(timeout_seconds=timeout_seconds)
    exporter.login()
    reference_date = datetime.now(_KST).strftime("%Y%m%d")
    quotes: list[QuoteRecord] = []
    bars: list[DailyBar] = []
    for index, ticker in enumerate(symbols):
        quote_screen = f"{9100 + index:04d}"
        daily_screen = f"{9200 + index:04d}"
        quotes.append(exporter.quote(ticker, quote_screen))
        bars.extend(
            exporter.daily_bars(
                ticker,
                screen_no=daily_screen,
                reference_date=reference_date,
                limit=daily_count,
            )
        )
    return quotes, bars, exporter


def _atomic_text(path: Path, text: str, *, encoding: str = "utf-8") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(text, encoding=encoding)
    temporary.replace(path)


def _write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    if not rows:
        raise ValueError(f"cannot write empty CSV: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    fieldnames = list(rows[0].keys())
    with temporary.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    temporary.replace(path)


def _snapshot_id(payload: dict[str, object]) -> str:
    canonical = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def write_export(
    *,
    output_root: Path,
    symbols: tuple[str, ...],
    daily_count: int,
    quotes: list[QuoteRecord],
    bars: list[DailyBar],
    exporter: KiwoomMarketExporter,
) -> tuple[ExportManifest, Path]:
    captured_utc = datetime.now(_UTC)
    captured_kst = captured_utc.astimezone(_KST)
    directory_name = captured_kst.strftime("%Y%m%dT%H%M%S%z")
    export_directory = output_root / directory_name
    quotes_path = export_directory / "quotes.csv"
    bars_path = export_directory / "daily_bars.csv"
    manifest_path = export_directory / "manifest.json"
    latest_path = output_root / "latest_market_export.json"

    quote_rows = [asdict(value) for value in quotes]
    bar_rows = [asdict(value) for value in bars]
    _write_csv(quotes_path, quote_rows)
    _write_csv(bars_path, bar_rows)

    warnings = (
        "Only the first OpenAPI+ daily-chart response page is collected.",
        "The login server mode is not inspected because account/login-info APIs "
        "are outside this read-only market-data boundary.",
        "Kiwoom evidence is exported independently and is not a silent replacement "
        "for another market-data provider.",
    )
    hash_payload: dict[str, object] = {
        "provider": PROVIDER,
        "captured_at_utc": captured_utc.isoformat(),
        "symbols": list(symbols),
        "quotes": quote_rows,
        "daily_bars": bar_rows,
        "adjusted_prices": False,
    }
    snapshot_id = _snapshot_id(hash_payload)
    manifest = ExportManifest(
        schema_version="1.0",
        status="completed",
        provider=PROVIDER,
        snapshot_id=snapshot_id,
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
        official_request_limits=OFFICIAL_LIMITS,
        quote_tr_code=QUOTE_TR_CODE,
        daily_tr_code=DAILY_TR_CODE,
        quotes_file=quotes_path.name,
        daily_bars_file=bars_path.name,
        account_api_enabled=False,
        order_api_enabled=False,
        warnings=warnings,
        provider_messages=exporter.provider_messages,
    )
    manifest_payload = asdict(manifest)
    _atomic_text(
        manifest_path,
        json.dumps(manifest_payload, ensure_ascii=False, indent=2, sort_keys=True),
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
    _atomic_text(
        latest_path,
        json.dumps(latest_payload, ensure_ascii=False, indent=2, sort_keys=True),
    )
    return manifest, export_directory


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Log in through the official Kiwoom window and export read-only quote "
            "and unadjusted daily-bar evidence"
        )
    )
    parser.add_argument("--symbols", nargs="+", default=list(DEFAULT_SYMBOLS))
    parser.add_argument("--daily-count", type=int, default=120)
    parser.add_argument("--timeout-seconds", type=int, default=600)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--json", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        symbols = _validate_symbols(args.symbols)
        quotes, bars, exporter = collect_market_data(
            symbols=symbols,
            daily_count=args.daily_count,
            timeout_seconds=args.timeout_seconds,
        )
        manifest, export_directory = write_export(
            output_root=args.output_root,
            symbols=symbols,
            daily_count=args.daily_count,
            quotes=quotes,
            bars=bars,
            exporter=exporter,
        )
    except (OSError, RuntimeError, TimeoutError, TypeError, ValueError) as exc:
        print("KIWOOM OPENAPI+ MARKET EXPORT: FAIL", file=sys.stderr)
        print(f"failure: {exc}", file=sys.stderr)
        return 2

    if args.json:
        print(json.dumps(asdict(manifest), ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print("KIWOOM OPENAPI+ MARKET EXPORT: PASS")
        print(f"snapshot: {manifest.snapshot_id}")
        print(f"symbols: {', '.join(manifest.symbols)}")
        print(f"quotes: {manifest.quote_count}")
        print(f"daily bars: {manifest.daily_bar_count}")
        print(f"adjusted prices: {manifest.adjusted_prices}")
        print(f"requests: {manifest.request_count}")
        print("account API: disabled")
        print("order API: disabled")
        print(f"export directory: {export_directory}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
