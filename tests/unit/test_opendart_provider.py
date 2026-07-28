"""Tests for official OpenDART read-only normalization."""

from __future__ import annotations

import io
import json
import zipfile
from collections.abc import Mapping
from datetime import UTC, datetime

import pytest

from alpha_cycle.providers.opendart import OpenDartCredentials, OpenDartReadOnlyClient
from alpha_cycle.providers.read_only_http import HttpBytesResponse

NOW = datetime(2026, 7, 28, 6, 0, tzinfo=UTC)


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


def _corp_zip() -> HttpBytesResponse:
    xml = b"""<result><list><corp_code>00126380</corp_code><corp_name>Samsung</corp_name><stock_code>005930</stock_code><modify_date>20260701</modify_date></list></result>"""
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w") as archive:
        archive.writestr("CORPCODE.xml", xml)
    return HttpBytesResponse(200, {}, stream.getvalue())


def test_credentials_reject_missing_placeholder_and_non_official_host() -> None:
    with pytest.raises(ValueError, match="must be set"):
        OpenDartCredentials.from_env({})
    with pytest.raises(ValueError, match="placeholder"):
        OpenDartCredentials.from_env({"OPENDART_API_KEY": "replace_with_local_secret"})
    with pytest.raises(ValueError, match="official"):
        OpenDartCredentials("secret", base_url="https://example.com")


def test_financials_and_disclosures_use_filing_dates_and_pit_contract() -> None:
    transport = FakeTransport(
        [
            _corp_zip(),
            _json({"status": "000", "acc_mt": "12"}),
            _json(
                {
                    "status": "000",
                    "list": [
                        {
                            "rcept_no": "20260315000001",
                            "sj_div": "IS",
                            "account_id": "ifrs-full_Revenue",
                            "account_nm": "Revenue",
                            "thstrm_amount": "1,234",
                        },
                        {
                            "rcept_no": "20260315000001",
                            "sj_div": "IS",
                            "account_id": "ifrs-full_ProfitLoss",
                            "account_nm": "Profit",
                            "thstrm_amount": "(50)",
                        },
                        {
                            "rcept_no": "20260315000001",
                            "sj_div": "CF",
                            "account_id": "-",
                            "account_nm": "Blank fact",
                            "thstrm_amount": "-",
                        },
                    ],
                }
            ),
            _json(
                {
                    "status": "000",
                    "list": [
                        {
                            "rcept_no": "20260315000001",
                            "corp_name": "Samsung",
                            "corp_cls": "Y",
                            "report_nm": "사업보고서",
                        },
                        {
                            "rcept_no": "20260401000002",
                            "corp_name": "Samsung",
                            "corp_cls": "Y",
                            "report_nm": "[정정]사업보고서",
                        },
                    ],
                }
            ),
        ]
    )
    client = OpenDartReadOnlyClient(
        OpenDartCredentials("secret"),
        transport=transport,
        now=lambda: NOW,
    )
    corp = client.resolve_stock_codes(["005930"])["005930"]
    financial = client.financial_statements(
        corp,
        business_year=2025,
        report_code="11011",
        fs_div="CFS",
    )
    disclosures = client.disclosures(
        corp,
        begin_date=datetime(2025, 1, 1).date(),
        end_date=datetime(2026, 7, 28).date(),
    )
    assert list(financial.frame["value"]) == [-50, 1234]
    assert set(financial.frame["available_date"].astype(str)) == {"2026-03-15"}
    assert set(financial.frame["period_end"].astype(str)) == {"2025-12-31"}
    assert disclosures.frame["is_correction"].tolist() == [False, True]


def test_non_december_fiscal_year_fails_closed() -> None:
    transport = FakeTransport([_corp_zip(), _json({"status": "000", "acc_mt": "03"})])
    client = OpenDartReadOnlyClient(
        OpenDartCredentials("secret"),
        transport=transport,
        now=lambda: NOW,
    )
    corp = client.resolve_stock_codes(["005930"])["005930"]
    with pytest.raises(ValueError, match="December fiscal year"):
        client.financial_statements(
            corp,
            business_year=2025,
            report_code="11011",
        )


def test_dart_api_error_does_not_expose_key() -> None:
    transport = FakeTransport([_json({"status": "010", "message": "등록되지 않은 키"})])
    client = OpenDartReadOnlyClient(OpenDartCredentials("secret"), transport=transport)
    with pytest.raises(ValueError) as exc_info:
        client.company("00126380")
    assert "status=010" in str(exc_info.value)
    assert "secret" not in str(exc_info.value)
