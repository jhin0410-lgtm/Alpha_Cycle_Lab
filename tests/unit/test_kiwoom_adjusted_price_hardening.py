"""Contract tests for production Kiwoom adjusted-price hardening."""

from __future__ import annotations

import importlib.util
import runpy
import sys
from pathlib import Path
from types import ModuleType, MethodType
from typing import Any

import pytest

EXPORTER_PATH = Path("bridge/kiwoom_openapi_plus/market_export.py")
HARDENING_PATH = Path("bridge/kiwoom_openapi_plus/market_export_hardening.py")


def _load_hardening() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "kiwoom_adjusted_price_hardening_test",
        HARDENING_PATH,
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _runtime() -> dict[str, Any]:
    namespace = runpy.run_path(
        str(EXPORTER_PATH),
        run_name="kiwoom_adjusted_runtime",
    )
    _load_hardening().apply_hardening(namespace)
    return namespace


def test_adjusted_daily_bars_request_and_preserve_response_evidence() -> None:
    namespace = _runtime()
    exporter_type = namespace["KiwoomMarketExporter"]
    exporter = object.__new__(exporter_type)
    captured: dict[str, object] = {}

    def request(self: object, **kwargs: object) -> dict[str, object]:
        captured.update(kwargs)
        return {
            "tr_code": "opt10081",
            "screen_no": "9200",
            "rows": [
                {
                    "date": "20260806",
                    "current_price": "-180000",
                    "volume": "123456",
                    "trading_value": "222222",
                    "open_price": "-181000",
                    "high_price": "+183000",
                    "low_price": "-179000",
                    "adjustment_code": "4",
                    "adjustment_ratio": "10.00",
                    "adjustment_event": "액면분할",
                    "previous_close": "178000",
                }
            ],
        }

    exporter._request = MethodType(request, exporter)
    bars = exporter.daily_bars(
        "000660",
        screen_no="9200",
        reference_date="20260806",
        limit=120,
    )

    assert captured["tr_code"] == "opt10081"
    assert ("수정주가구분", "1") in captured["inputs"]
    assert len(bars) == 1
    assert bars[0].adjusted is True
    assert bars[0].close_price == 180000
    assert exporter.adjustment_evidence == [
        {
            "ticker": "000660",
            "date": "20260806",
            "requested_price_basis": "adjusted",
            "adjustment_request_value": "1",
            "response_adjustment_code_raw": "4",
            "response_adjustment_ratio_raw": "10.00",
            "response_adjustment_event_raw": "액면분할",
            "previous_close_raw": "178000",
        }
    ]


def test_adjusted_daily_bars_reject_empty_valid_row_set() -> None:
    namespace = _runtime()
    exporter_type = namespace["KiwoomMarketExporter"]
    exporter = object.__new__(exporter_type)

    def request(self: object, **_kwargs: object) -> dict[str, object]:
        return {"tr_code": "opt10081", "screen_no": "9200", "rows": []}

    exporter._request = MethodType(request, exporter)
    with pytest.raises(RuntimeError, match="no valid Kiwoom daily bars"):
        exporter.daily_bars(
            "005930",
            screen_no="9200",
            reference_date="20260806",
            limit=120,
        )


def test_corporate_action_count_ignores_zero_and_unknown_metadata() -> None:
    hardening = _load_hardening()

    for ratio in ("", "0", "0.0", "0.00", "+0.0000", "-0.00"):
        assert not hardening._has_corporate_action(
            {
                "response_adjustment_event_raw": "0",
                "response_adjustment_ratio_raw": ratio,
            }
        )
    assert not hardening._has_corporate_action(
        {
            "response_adjustment_event_raw": "",
            "response_adjustment_ratio_raw": "not-provided",
        }
    )
    assert hardening._has_corporate_action(
        {
            "response_adjustment_event_raw": "액면분할",
            "response_adjustment_ratio_raw": "0.00",
        }
    )
    assert hardening._has_corporate_action(
        {
            "response_adjustment_event_raw": "",
            "response_adjustment_ratio_raw": "10.00%",
        }
    )


def test_hardening_contains_no_account_or_order_api_surface() -> None:
    combined = "\n".join(
        path.read_text(encoding="utf-8")
        for path in (EXPORTER_PATH, HARDENING_PATH)
    )
    for forbidden in (
        "SendOrder",
        "GetLoginInfo",
        "OPW000",
        "KOA_NORMAL_BUY",
        "주문비밀번호",
    ):
        assert forbidden not in combined
    assert '("수정주가구분", "1")' in combined
    assert '"수정주가이벤트"' in combined
    assert '"수정비율"' in combined
