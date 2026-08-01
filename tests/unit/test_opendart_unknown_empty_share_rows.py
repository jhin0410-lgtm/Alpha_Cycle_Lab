"""Regression tests for unnamed OpenDART rows with empty issued-share counts."""

from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import UTC, date, datetime

import pandas as pd

from alpha_cycle.intelligence.valuation import ValuationEvidenceSnapshot
from alpha_cycle.intelligence.valuation_resilient import (
    apply_unresolved_share_count_guard,
)
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


def test_unknown_empty_row_is_quarantined_instead_of_aborting() -> None:
    unresolved_other = _row("기타", "")
    unresolved_other.update(
        {
            "now_to_isu_stock_totqy": "",
            "now_to_dcrs_stock_totqy": "",
            "tesstk_co": "",
            "distb_stock_co": "",
        }
    )
    client = OpenDartValuationClient(
        OpenDartCredentials("secret"),
        transport=FakeTransport(
            [
                _row("보통주", "5,969"),
                unresolved_other,
                _row("합계", ""),
            ]
        ),
    )

    batch = client.stock_totals(
        CORP,
        business_year=2026,
        report_code="11013",
    )

    other = batch.frame.loc[batch.frame["security_name"] == "기타"].iloc[0]
    total = batch.frame.loc[batch.frame["security_name"] == "합계"].iloc[0]
    assert other["issued_shares"] == 0
    assert total["issued_shares"] == 0
    assert "unresolved_missing_economic_share_count" in str(
        other["normalization_warning"]
    )
    assert "unresolved_aggregate_share_count" in str(total["normalization_warning"])
    assert isinstance(batch.raw_payload, dict)
    raw_other = next(
        row
        for row in batch.raw_payload["list"]
        if isinstance(row, dict) and row.get("se") == "기타"
    )
    assert raw_other["_alpha_cycle_original_istc_totqy"] == ""
    assert raw_other["_alpha_cycle_istc_totqy_source"] == (
        "unresolved_missing_economic_share_count"
    )


def _snapshot() -> ValuationEvidenceSnapshot:
    shares = pd.DataFrame(
        [
            {
                "ticker": "005930",
                "security_name": "보통주",
                "security_class": "common",
                "issued_shares": 5969,
                "period_end": date(2026, 3, 31),
                "available_date": date(2026, 5, 15),
                "normalization_warning": None,
            },
            {
                "ticker": "005930",
                "security_name": "기타",
                "security_class": "other",
                "issued_shares": 0,
                "period_end": date(2026, 3, 31),
                "available_date": date(2026, 5, 15),
                "normalization_warning": (
                    "기타: schema value set to zero via "
                    "unresolved_missing_economic_share_count"
                ),
            },
        ]
    )
    security_values = pd.DataFrame(
        [
            {
                **shares.iloc[0].to_dict(),
                "symbol": "005930",
                "mapping_source": "explicit",
                "price": 100.0,
                "price_timestamp": datetime(2026, 8, 1, tzinfo=UTC),
                "security_market_value": 596900.0,
                "priced": True,
            }
        ]
    )
    valuation_metrics = pd.DataFrame(
        [
            {
                "ticker": "005930",
                "market_cap_complete": True,
                "missing_security_names": "[]",
                "market_cap_proxy": 596900.0,
                "market_cap": 596900.0,
                "pe": 10.0,
                "pb": 1.0,
                "ps": 2.0,
                "fcf_yield": 0.05,
                "earnings_yield": 0.1,
                "valuation_score": 4.0,
                "valuation_status": "complete_peer_relative_scored",
            }
        ]
    )
    return ValuationEvidenceSnapshot(
        captured_at=datetime(2026, 8, 1, tzinfo=UTC),
        evaluation_date=date(2026, 8, 1),
        research_snapshot_id="a" * 64,
        market_snapshot_id="b" * 64,
        history_years=3,
        shares=shares,
        security_values=security_values,
        financial_history=pd.DataFrame(),
        valuation_metrics=valuation_metrics,
        raw_valuation={},
    )


def test_unresolved_row_disables_market_cap_and_all_valuation_multiples() -> None:
    guarded = apply_unresolved_share_count_guard(_snapshot())

    metric = guarded.valuation_metrics.iloc[0]
    assert not bool(metric["market_cap_complete"])
    assert not bool(metric["share_count_complete"])
    assert metric["valuation_status"] == "incomplete_share_count"
    for column in (
        "market_cap",
        "pe",
        "pb",
        "ps",
        "fcf_yield",
        "earnings_yield",
        "valuation_score",
    ):
        assert pd.isna(metric[column])
    assert json.loads(str(metric["missing_security_names"])) == ["기타"]
    unresolved = guarded.security_values.loc[
        guarded.security_values["security_name"] == "기타"
    ].iloc[0]
    assert not bool(unresolved["share_count_complete"])
    assert unresolved["mapping_source"] == "unresolved_share_count"
    assert any("valuation multiples disabled" in warning for warning in guarded.warnings)
