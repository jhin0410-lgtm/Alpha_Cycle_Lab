"""Regression tests for OpenDART archive and pagination hardening."""

from __future__ import annotations

import io
import json
import zipfile
from collections.abc import Mapping
from datetime import date

import pytest

from alpha_cycle.providers.opendart import (
    CorpCode,
    OpenDartCredentials,
    OpenDartReadOnlyClient,
)
from alpha_cycle.providers.read_only_http import HttpBytesResponse


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


def _response(payload: object) -> HttpBytesResponse:
    return HttpBytesResponse(200, {}, json.dumps(payload).encode())


def _corp_zip(rows: list[dict[str, str]]) -> HttpBytesResponse:
    parts = ["<result>"]
    for row in rows:
        parts.append("<list>")
        for key in ("corp_code", "corp_name", "stock_code", "modify_date"):
            parts.append(f"<{key}>{row.get(key, '')}</{key}>")
        parts.append("</list>")
    parts.append("</result>")
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w") as archive:
        archive.writestr("CORPCODE.xml", "".join(parts).encode())
    return HttpBytesResponse(200, {}, stream.getvalue())


def test_archive_skips_unrelated_malformed_rows_and_resolves_requested_codes() -> None:
    transport = FakeTransport(
        [
            _corp_zip(
                [
                    {
                        "corp_code": "00126380",
                        "corp_name": "Samsung old",
                        "stock_code": "005930",
                        "modify_date": "20260101",
                    },
                    {
                        "corp_code": "00126380",
                        "corp_name": "Samsung",
                        "stock_code": "005930",
                        "modify_date": "20260701",
                    },
                    {
                        "corp_code": "00164779",
                        "corp_name": "SK hynix",
                        "stock_code": "00660",
                        "modify_date": "20260701",
                    },
                    {
                        "corp_code": "00999999",
                        "corp_name": "Malformed unrelated row",
                        "stock_code": "NOT-A-CODE",
                        "modify_date": "20260701",
                    },
                    {
                        "corp_code": "bad",
                        "corp_name": "Bad metadata",
                        "stock_code": "123456",
                        "modify_date": "20260701",
                    },
                    {
                        "corp_code": "00888888",
                        "corp_name": "Unlisted",
                        "stock_code": "",
                        "modify_date": "20260701",
                    },
                ]
            )
        ]
    )
    client = OpenDartReadOnlyClient(OpenDartCredentials("secret"), transport=transport)

    resolved = client.resolve_stock_codes(["005930", "000660"])

    assert resolved["005930"].corp_name == "Samsung"
    assert resolved["000660"].corp_code == "00164779"
    diagnostics = client.corp_code_diagnostics
    assert diagnostics is not None
    assert diagnostics.total_rows == 6
    assert diagnostics.listed_rows == 5
    assert diagnostics.accepted_rows == 3
    assert diagnostics.skipped_invalid_stock_codes == 1
    assert diagnostics.skipped_invalid_metadata == 1
    assert diagnostics.duplicate_stock_codes == 1


def test_archive_ambiguity_fails_only_for_requested_symbol() -> None:
    transport = FakeTransport(
        [
            _corp_zip(
                [
                    {
                        "corp_code": "00111111",
                        "corp_name": "One",
                        "stock_code": "005930",
                        "modify_date": "20260701",
                    },
                    {
                        "corp_code": "00222222",
                        "corp_name": "Two",
                        "stock_code": "005930",
                        "modify_date": "20260701",
                    },
                ]
            )
        ]
    )
    client = OpenDartReadOnlyClient(OpenDartCredentials("secret"), transport=transport)

    with pytest.raises(ValueError, match="ambiguous"):
        client.resolve_stock_codes(["005930"])


def test_archive_xml_error_is_reported_instead_of_bad_zip() -> None:
    body = (
        b"<result><status>010</status>"
        b"<message>unregistered key</message></result>"
    )
    client = OpenDartReadOnlyClient(
        OpenDartCredentials("secret"),
        transport=FakeTransport([HttpBytesResponse(200, {}, body)]),
    )

    with pytest.raises(ValueError, match="status=010"):
        client.corp_codes()


def test_disclosures_collect_all_pages_and_deduplicate() -> None:
    transport = FakeTransport(
        [
            _response(
                {
                    "status": "000",
                    "total_page": 2,
                    "list": [
                        {
                            "rcept_no": "20260101000001",
                            "rcept_dt": "20260101",
                            "corp_name": "Samsung",
                            "corp_cls": "Y",
                            "report_nm": "사업보고서",
                        }
                    ],
                }
            ),
            _response(
                {
                    "status": "000",
                    "total_page": 2,
                    "list": [
                        {
                            "rcept_no": "20260201000002",
                            "rcept_dt": "20260201",
                            "corp_name": "Samsung",
                            "corp_cls": "Y",
                            "report_nm": "[기재정정]사업보고서",
                        }
                    ],
                }
            ),
        ]
    )
    client = OpenDartReadOnlyClient(OpenDartCredentials("secret"), transport=transport)
    corp = CorpCode("00126380", "Samsung", "005930", date(2026, 7, 1))

    batch = client.disclosures(
        corp,
        begin_date=date(2026, 1, 1),
        end_date=date(2026, 7, 29),
    )

    assert batch.frame["rcept_no"].tolist() == [
        "20260101000001",
        "20260201000002",
    ]
    assert batch.frame["is_correction"].tolist() == [False, True]
    assert any("page_no=1" in url for url in transport.urls)
    assert any("page_no=2" in url for url in transport.urls)
    assert batch.raw_payload["page_count"] == 2


def test_disclosures_no_data_is_an_empty_valid_frame() -> None:
    client = OpenDartReadOnlyClient(
        OpenDartCredentials("secret"),
        transport=FakeTransport(
            [_response({"status": "013", "message": "no data"})]
        ),
    )
    corp = CorpCode("00126380", "Samsung", "005930", date(2026, 7, 1))

    batch = client.disclosures(
        corp,
        begin_date=date(2026, 1, 1),
        end_date=date(2026, 1, 31),
    )

    assert batch.frame.empty
    assert list(batch.frame.columns) == [
        "ticker",
        "corp_code",
        "corp_name",
        "rcept_no",
        "report_name",
        "receipt_date",
        "corp_class",
        "is_correction",
    ]
