"""Tests for OpenDART share-count and multi-period financial evidence."""

from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import UTC, date, datetime

import pandas as pd
import pytest

from alpha_cycle.providers.opendart import CorpCode, OpenDartCredentials
from alpha_cycle.providers.opendart_valuation import OpenDartValuationClient
from alpha_cycle.providers.read_only_http import HttpBytesResponse

NOW = datetime(2026, 7, 29, 3, tzinfo=UTC)
CORP = CorpCode("00126380", "Samsung", "005930", date(2026, 7, 1))


class FakeTransport:
    def __init__(self, responses: list[HttpBytesResponse]) -> None:
        self.responses = responses
        self.urls: list[str] = []

    def get(
        self,
        url: str,
        *,
        headers: Mapping[str, str],
        timeout_seconds: float,
    ) -> HttpBytesResponse:
        assert timeout_seconds > 0
        assert isinstance(headers, Mapping)
        self.urls.append(url)
        if not self.responses:
            raise AssertionError("No fake response remains")
        return self.responses.pop(0)


def _json(payload: object) -> HttpBytesResponse:
    return HttpBytesResponse(200, {}, json.dumps(payload).encode())


def test_stock_totals_preserve_common_preferred_and_total_rows() -> None:
    transport = FakeTransport(
        [
            _json(
                {
                    "status": "000",
                    "list": [
                        {
                            "rcept_no": "20260515000001",
                            "corp_code": "00126380",
                            "corp_name": "Samsung",
                            "se": "보통주",
                            "istc_totqy": "5,000",
                            "tesstk_co": "100",
                            "distb_stock_co": "4,900",
                            "stlm_dt": "2026-03-31",
                        },
                        {
                            "rcept_no": "20260515000001",
                            "corp_code": "00126380",
                            "corp_name": "Samsung",
                            "se": "우선주",
                            "istc_totqy": "500",
                            "tesstk_co": "0",
                            "distb_stock_co": "500",
                            "stlm_dt": "2026-03-31",
                        },
                        {
                            "rcept_no": "20260515000001",
                            "corp_code": "00126380",
                            "corp_name": "Samsung",
                            "se": "합계",
                            "istc_totqy": "5,500",
                            "tesstk_co": "100",
                            "distb_stock_co": "5,400",
                            "stlm_dt": "2026-03-31",
                        },
                    ],
                }
            )
        ]
    )
    client = OpenDartValuationClient(
        OpenDartCredentials("secret"),
        transport=transport,
        now=lambda: NOW,
    )
    batch = client.stock_totals(CORP, business_year=2026, report_code="11013")
    assert batch.frame["security_class"].tolist() == ["common", "preferred", "total"]
    assert batch.frame["issued_shares"].tolist() == [5000, 500, 5500]
    assert set(batch.frame["available_date"].astype(str)) == {"2026-05-15"}
    assert "stockTotqySttus.json" in transport.urls[0]
    assert "secret" in transport.urls[0]


def test_financial_period_payload_filters_future_receipt() -> None:
    transport = FakeTransport(
        [
            _json(
                {
                    "status": "000",
                    "list": [
                        {
                            "rcept_no": "20260814000001",
                            "corp_code": "00126380",
                            "stock_code": "005930",
                            "bsns_year": "2026",
                            "reprt_code": "11012",
                            "sj_div": "IS",
                            "account_id": "ifrs-full_Revenue",
                            "account_nm": "Revenue",
                            "thstrm_amount": "100",
                        }
                    ],
                }
            )
        ]
    )
    client = OpenDartValuationClient(OpenDartCredentials("secret"), transport=transport)
    payload = client.financial_period_payload(
        CORP,
        business_year=2026,
        report_code="11012",
        evaluation_date=date(2026, 7, 29),
    )
    assert payload is None


def test_financial_period_payload_preserves_quarter_and_cumulative_fields() -> None:
    transport = FakeTransport(
        [
            _json(
                {
                    "status": "000",
                    "list": [
                        {
                            "rcept_no": "20260515000001",
                            "corp_code": "00126380",
                            "stock_code": "005930",
                            "bsns_year": "2026",
                            "reprt_code": "11013",
                            "sj_div": "IS",
                            "account_id": "ifrs-full_Revenue",
                            "account_nm": "Revenue",
                            "thstrm_amount": "100",
                            "thstrm_add_amount": "100",
                            "frmtrm_q_amount": "80",
                            "frmtrm_add_amount": "80",
                        }
                    ],
                }
            )
        ]
    )
    client = OpenDartValuationClient(OpenDartCredentials("secret"), transport=transport)
    period = client.financial_period_payload(
        CORP,
        business_year=2026,
        report_code="11013",
        evaluation_date=date(2026, 7, 29),
    )
    assert period is not None
    rows = period.payload["list"]
    assert isinstance(rows, list)
    assert rows[0]["thstrm_add_amount"] == "100"
    assert period.available_date == date(2026, 5, 15)


def test_stock_totals_reject_wrong_settlement_date() -> None:
    transport = FakeTransport(
        [
            _json(
                {
                    "status": "000",
                    "list": [
                        {
                            "rcept_no": "20260515000001",
                            "corp_code": "00126380",
                            "se": "보통주",
                            "istc_totqy": "5,000",
                            "stlm_dt": "2026-06-30",
                        }
                    ],
                }
            )
        ]
    )
    client = OpenDartValuationClient(OpenDartCredentials("secret"), transport=transport)
    with pytest.raises(ValueError, match="settlement date"):
        client.stock_totals(CORP, business_year=2026, report_code="11013")


def test_no_data_stock_totals_returns_typed_empty_frame() -> None:
    client = OpenDartValuationClient(
        OpenDartCredentials("secret"),
        transport=FakeTransport([_json({"status": "013", "message": "no data"})]),
    )
    batch = client.stock_totals(CORP, business_year=2026, report_code="11012")
    assert batch.frame.empty
    assert isinstance(batch.frame, pd.DataFrame)
