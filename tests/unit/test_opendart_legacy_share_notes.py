"""Regression tests for narrative notes in optional OpenDART share-count fields."""

from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import date

import pytest

from alpha_cycle.providers.opendart import CorpCode, OpenDartCredentials
from alpha_cycle.providers.opendart_valuation import OpenDartValuationClient
from alpha_cycle.providers.read_only_http import HttpBytesResponse

CORP = CorpCode("00126380", "Samsung", "005930", date(2026, 7, 1))
LEGACY_NOTE = "-.2003.03.31주식병합(21:1)"


class FakeTransport:
    def __init__(self, payload: object) -> None:
        self.payload = payload

    def get(
        self,
        url: str,
        *,
        headers: Mapping[str, str],
        timeout_seconds: float,
    ) -> HttpBytesResponse:
        assert url
        assert isinstance(headers, Mapping)
        assert timeout_seconds > 0
        return HttpBytesResponse(200, {}, json.dumps(self.payload).encode())


def _client(row: Mapping[str, object]) -> OpenDartValuationClient:
    return OpenDartValuationClient(
        OpenDartCredentials("secret"),
        transport=FakeTransport({"status": "000", "list": [dict(row)]}),
    )


def _base_row() -> dict[str, object]:
    return {
        "rcept_no": "20260515000001",
        "corp_code": "00126380",
        "corp_name": "Samsung",
        "se": "보통주",
        "stlm_dt": "2026-03-31",
        "isu_stock_totqy": "10,000",
        "now_to_isu_stock_totqy": "6,000",
        "now_to_dcrs_stock_totqy": LEGACY_NOTE,
        "istc_totqy": "5,969",
        "tesstk_co": "100",
        "distb_stock_co": "5,869",
    }


def test_optional_legacy_note_is_quarantined_without_blocking_valuation() -> None:
    batch = _client(_base_row()).stock_totals(
        CORP,
        business_year=2026,
        report_code="11013",
    )

    row = batch.frame.iloc[0]
    assert row["issued_shares"] == 5969
    assert row["shares_reduced_to_date"] is None
    assert LEGACY_NOTE in str(row["normalization_warning"])
    assert len(batch.warnings) == 1
    assert "now_to_dcrs_stock_totqy" in batch.warnings[0]
    assert LEGACY_NOTE in batch.warnings[0]
    assert isinstance(batch.raw_payload, dict)
    assert batch.raw_payload["_normalization_warnings"] == list(batch.warnings)


def test_critical_issued_share_field_remains_strict() -> None:
    row = _base_row()
    row["istc_totqy"] = LEGACY_NOTE

    with pytest.raises(ValueError, match="istc_totqy"):
        _client(row).stock_totals(
            CORP,
            business_year=2026,
            report_code="11013",
        )


def test_optional_fraction_without_narrative_note_remains_invalid() -> None:
    row = _base_row()
    row["tesstk_co"] = "0.5"

    with pytest.raises(ValueError, match="tesstk_co"):
        _client(row).stock_totals(
            CORP,
            business_year=2026,
            report_code="11013",
        )
