"""Tests for the read-only Kiwoom OpenAPI+ market exporter."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import Any

import pytest

MARKET_PATH = Path("bridge/kiwoom_openapi_plus/market_export.py")


def _load_market() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "kiwoom_market_export_test",
        MARKET_PATH,
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class FakeSignal:
    def __init__(self) -> None:
        self.callback: Any = None

    def connect(self, callback: Any) -> None:
        self.callback = callback

    def emit(self, *arguments: object) -> None:
        assert self.callback is not None
        self.callback(*arguments)


class FakeEventLoop:
    def __init__(self) -> None:
        self.quit_requested = False

    def quit(self) -> None:
        self.quit_requested = True

    def exec_(self) -> int:
        return 0


class FakeTimer:
    def __init__(self) -> None:
        self.timeout = FakeSignal()

    def setSingleShot(self, _single_shot: bool) -> None:
        return None

    def start(self, _milliseconds: int) -> None:
        return None

    def stop(self) -> None:
        return None


class FakeApplication:
    @staticmethod
    def instance() -> None:
        return None

    def __init__(self, _arguments: list[str]) -> None:
        pass


class FakeMarketControl:
    quote_fields = {
        "종목명": "삼성전자",
        "현재가": "-75000",
        "전일대비": "-1000",
        "등락율": "-1.32",
        "거래량": "12345678",
        "시가": "-76000",
        "고가": "+76500",
        "저가": "-74800",
        "기준가": "76000",
    }
    daily_rows = [
        {
            "일자": "20260804",
            "현재가": "-75000",
            "거래량": "12345678",
            "거래대금": "925000",
            "시가": "-76000",
            "고가": "+76500",
            "저가": "-74800",
        },
        {
            "일자": "20260803",
            "현재가": "+76000",
            "거래량": "10000000",
            "거래대금": "760000",
            "시가": "+75500",
            "고가": "+77000",
            "저가": "+75200",
        },
    ]

    def __init__(self) -> None:
        self.OnEventConnect = FakeSignal()
        self.OnReceiveTrData = FakeSignal()
        self.OnReceiveMsg = FakeSignal()
        self.connected = False
        self.inputs: dict[str, str] = {}
        self.request_name = ""
        self.tr_code = ""

    def setControl(self, value: str) -> bool:
        return value == "KHOPENAPI.KHOpenAPICtrl.1"

    def isNull(self) -> bool:
        return False

    def dynamicCall(self, signature: str, *arguments: object) -> object:
        if signature == "GetConnectState()":
            return 1 if self.connected else 0
        if signature == "CommConnect()":
            self.connected = True
            self.OnEventConnect.emit(0)
            return 0
        if signature == "SetInputValue(QString, QString)":
            self.inputs[str(arguments[0])] = str(arguments[1])
            return None
        if signature == "CommRqData(QString, QString, int, QString)":
            self.request_name = str(arguments[0])
            self.tr_code = str(arguments[1])
            screen_no = str(arguments[3])
            self.OnReceiveTrData.emit(
                screen_no,
                self.request_name,
                self.tr_code,
                "",
                "0",
                0,
                "0",
                "",
                "",
            )
            return 0
        if signature == "GetRepeatCnt(QString, QString)":
            return len(self.daily_rows)
        if signature == "GetCommData(QString, QString, int, QString)":
            index = int(arguments[2])
            field = str(arguments[3])
            if self.tr_code == "opt10001":
                return self.quote_fields[field]
            return self.daily_rows[index][field]
        raise AssertionError(f"unexpected ActiveX call: {signature}")


def _fake_qt() -> tuple[object, object, object, str, str]:
    qt_core = SimpleNamespace(QEventLoop=FakeEventLoop, QTimer=FakeTimer)
    qt_widgets = SimpleNamespace(QApplication=FakeApplication)
    return qt_core, qt_widgets, FakeMarketControl, "5.15.11", "5.15.2"


class NoWaitGate:
    interval_seconds = 0.25

    def wait(self) -> None:
        return None


def _exporter_factory(market: ModuleType) -> Any:
    def create(*, timeout_seconds: int) -> object:
        return market.KiwoomMarketExporter(
            timeout_seconds=timeout_seconds,
            request_gate=NoWaitGate(),
        )

    return create


def test_market_export_collects_quote_and_unadjusted_daily_bars(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    market = _load_market()
    monkeypatch.setattr(market.platform, "system", lambda: "Windows")
    monkeypatch.setattr(market.struct, "calcsize", lambda _format: 4)
    monkeypatch.setattr(market, "_load_qt", _fake_qt)

    quotes, bars, exporter = market.collect_market_data(
        symbols=("005930",),
        daily_count=2,
        timeout_seconds=30,
        exporter_factory=_exporter_factory(market),
    )

    assert exporter.connected is True
    assert exporter.login_event_code == 0
    assert exporter.request_count == 2
    assert len(quotes) == 1
    assert quotes[0].ticker == "005930"
    assert quotes[0].current_price == 75000
    assert quotes[0].change == -1000
    assert quotes[0].open_price == 76000
    assert quotes[0].current_price_raw == "-75000"
    assert [bar.date for bar in bars] == ["20260804", "20260803"]
    assert [bar.close_price for bar in bars] == [75000, 76000]
    assert all(bar.adjusted is False for bar in bars)


def test_market_export_writes_provenance_and_latest_pointer(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    market = _load_market()
    monkeypatch.setattr(market.platform, "system", lambda: "Windows")
    monkeypatch.setattr(market.struct, "calcsize", lambda _format: 4)
    monkeypatch.setattr(market, "_load_qt", _fake_qt)
    quotes, bars, exporter = market.collect_market_data(
        symbols=("005930",),
        daily_count=2,
        timeout_seconds=30,
        exporter_factory=_exporter_factory(market),
    )

    manifest, export_directory = market.write_export(
        output_root=tmp_path,
        symbols=("005930",),
        daily_count=2,
        quotes=quotes,
        bars=bars,
        exporter=exporter,
    )

    assert manifest.status == "completed"
    assert manifest.provider == "kiwoom_openapi_plus"
    assert manifest.adjusted_prices is False
    assert manifest.account_api_enabled is False
    assert manifest.order_api_enabled is False
    assert manifest.request_count == 2
    assert len(manifest.snapshot_id) == 64
    assert (export_directory / "quotes.csv").is_file()
    assert (export_directory / "daily_bars.csv").is_file()
    payload = json.loads(
        (export_directory / "manifest.json").read_text(encoding="utf-8")
    )
    latest = json.loads(
        (tmp_path / "latest_market_export.json").read_text(encoding="utf-8")
    )
    assert payload["snapshot_id"] == manifest.snapshot_id
    assert latest["snapshot_id"] == manifest.snapshot_id
    assert latest["symbols"] == ["005930"]
    assert latest["adjusted_prices"] is False


def test_market_export_defaults_match_live_market_universe() -> None:
    market = _load_market()

    assert market.DEFAULT_SYMBOLS == ("005930", "005935", "000660")
    assert market.MAX_REQUESTS_PER_SECOND == 4
    assert market.MIN_REQUEST_INTERVAL_SECONDS == 0.25
    assert market.OFFICIAL_LIMITS == {
        "per_second": 5,
        "per_minute": 100,
        "per_hour": 1000,
    }


def test_market_export_exposes_no_account_or_order_calls() -> None:
    combined = "\n".join(
        path.read_text(encoding="utf-8")
        for path in (
            MARKET_PATH,
            Path("scripts/export_kiwoom_openapi_plus_market.ps1"),
            Path("scripts/export_kiwoom_openapi_plus_market.cmd"),
        )
    )

    for forbidden in (
        "SendOrder",
        "GetLoginInfo",
        "OPW000",
        "KOA_NORMAL_BUY",
        "주문비밀번호",
    ):
        assert forbidden not in combined
    assert "opt10001" in combined
    assert "opt10081" in combined
    assert '("수정주가구분", "0")' in combined


def test_market_export_launcher_initializes_qt_before_execution() -> None:
    script = Path("scripts/export_kiwoom_openapi_plus_market.ps1").read_text(
        encoding="utf-8"
    )

    initialization = script.index(". $QtInitializer -BridgePython")
    invocation = script.index("& $BridgePython $Exporter")
    assert initialization < invocation
