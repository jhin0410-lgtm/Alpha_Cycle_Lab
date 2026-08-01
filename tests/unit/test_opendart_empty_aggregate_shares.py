"""Regression tests for empty issued-share totals on aggregate OpenDART rows."""

from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import date

from alpha_cycle.providers import OpenDartValuationClient
from alpha_cycle.providers.opendart import CorpCode, OpenDartCredentials
from alpha_cycle.providers.read_only_http import HttpBytesResponse

CORP = CorpCode("00126380", "Samsung", "005930", date(2026, 7, 1))


class FakeTransport:
    def __init__(self, rows: list[Mapping[str, object]]) -> None:
        self.rows = rows

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
        payload = {"status": "000", "list": [dict(row) for row in self.rows]}
        return HttpBytesResponse(200, {}, json.dumps(payload).encode())


def _row(name: str, issued: object) -> dict[str, object]:
    return {
        "rcept_no": "20260515000001",
        "corp_code": "00126380",
        "corp_name": "Samsung",
        "se": name,
        "stlm_dt": "2026-03-31",
        "isu_stock_totqy": "10,000",
        "now_to_isu_stock_totqy": "6,000",
        "now_to_dcrs_stock_totqy": "31",
        "istc_totqy": issued,
        "tesstk_co": "100",
        "distb_stock_co": "5,869",
    }


def _client(rows: list[Mapping[str, object]]) -> OpenDartValuationClient:
    return OpenDartValuationClient(
        OpenDartCredentials("secret"),
        transport=FakeTransport(rows),
    )


def test_empty_total_is_derived_from_validated_economic_classes() -> None:
    batch = _client(
        [
            _row("보통주", "5,969"),
            _row("우선주", "1,000"),
            _row("합계", ""),
        ]
    ).stock_totals(CORP, business_year=2026, report_code="11013")

    total = batch.frame.loc[batch.frame["security_class"] == "total"].iloc[0]
    assert total["issued_shares"] == 6969
    assert "derived_validated_economic_class_sum" in str(total["normalization_warning"])
    assert any("aggregate" not in warning for warning in batch.warnings)
    assert isinstance(batch.raw_payload, dict)
    raw_total = next(
        row
        for row in batch.raw_payload["list"]
        if isinstance(row, dict) and row.get("se") == "합계"
    )
    assert raw_total["_alpha_cycle_original_istc_totqy"] == ""
    assert raw_total["_alpha_cycle_istc_totqy_source"] == (
        "derived_validated_economic_class_sum"
    )


def test_empty_note_row_is_excluded_with_zero_schema_value() -> None:
    batch = _client([_row("보통주", "5,969"), _row("비고", "")]).stock_totals(
        CORP,
        business_year=2026,
        report_code="11013",
    )
    note = batch.frame.loc[batch.frame["security_class"] == "note"].iloc[0]
    assert note["issued_shares"] == 0
    assert "non_economic_note_row_zero" in str(note["normalization_warning"])


def test_empty_economic_share_class_is_recovered_from_cross_checked_identity() -> None:
    batch = _client([_row("보통주", "")]).stock_totals(
        CORP,
        business_year=2026,
        report_code="11013",
    )

    common = batch.frame.iloc[0]
    assert common["issued_shares"] == 5969
    assert "derived_cross_checked_share_identity" in str(
        common["normalization_warning"]
    )
    assert not any(
        "unresolved_missing_economic_share_count" in warning
        for warning in batch.warnings
    )


def test_empty_zero_preferred_class_is_recovered_without_false_incompleteness() -> None:
    preferred = _row("우선주", "")
    preferred.update(
        {
            "now_to_isu_stock_totqy": "0",
            "now_to_dcrs_stock_totqy": "0",
            "tesstk_co": "0",
            "distb_stock_co": "0",
        }
    )
    batch = _client([preferred]).stock_totals(
        CORP,
        business_year=2026,
        report_code="11013",
    )

    row = batch.frame.iloc[0]
    assert row["issued_shares"] == 0
    assert "derived_cross_checked_share_identity" in str(row["normalization_warning"])
    assert "unresolved_missing_economic_share_count" not in str(
        row["normalization_warning"]
    )


def test_conflicting_share_identities_remain_quarantined() -> None:
    conflicting = _row("보통주", "")
    conflicting["distb_stock_co"] = "5,800"
    batch = _client([conflicting]).stock_totals(
        CORP,
        business_year=2026,
        report_code="11013",
    )

    common = batch.frame.iloc[0]
    assert common["issued_shares"] == 0
    assert "unresolved_missing_economic_share_count" in str(
        common["normalization_warning"]
    )
