from __future__ import annotations

from datetime import date

import pandas as pd

from alpha_cycle.intelligence.historical_pb_resilient import (
    build_historical_pb_evidence,
)


def test_newer_unusable_stock_report_falls_back_to_older_usable_report() -> None:
    prices = pd.DataFrame(
        [
            {
                "ticker": "000660",
                "date": "2026-05-14",
                "close_price": 100.0,
                "adjusted": False,
            },
            {
                "ticker": "000660",
                "date": "2026-05-15",
                "close_price": 110.0,
                "adjusted": False,
            },
        ]
    )
    shares = pd.DataFrame(
        [
            {
                "ticker": "000660",
                "business_year": 2025,
                "report_code": "11011",
                "period_end": "2025-12-31",
                "available_date": "2026-03-10",
                "security_name": "보통주",
                "security_class": "common",
                "issued_shares": 50,
                "normalization_warning": "",
            },
            {
                "ticker": "000660",
                "business_year": 2026,
                "report_code": "11013",
                "period_end": "2026-03-31",
                "available_date": "2026-05-15",
                "security_name": "합계",
                "security_class": "total",
                "issued_shares": 50,
                "normalization_warning": "",
            },
        ]
    )
    financials = pd.DataFrame(
        [
            {
                "ticker": "000660",
                "period_end": "2025-12-31",
                "available_date": "2026-03-10",
                "equity": 1_000.0,
                "derived": False,
            },
            {
                "ticker": "000660",
                "period_end": "2026-03-31",
                "available_date": "2026-05-15",
                "equity": 1_100.0,
                "derived": False,
            },
        ]
    )

    evidence = build_historical_pb_evidence(
        prices,
        shares,
        financials,
        evaluation_date=date(2026, 8, 10),
    )

    assert evidence.series["date"].tolist() == [
        date(2026, 5, 14),
        date(2026, 5, 15),
    ]
    assert evidence.series["share_available_date"].tolist() == [
        date(2026, 3, 10),
        date(2026, 3, 10),
    ]
    assert evidence.series.iloc[1]["market_cap"] == 5_500.0
    assert evidence.series.iloc[1]["equity"] == 1_100.0
    assert any(
        "ignored visible unusable stock-total report 2026/11013" in warning
        for warning in evidence.warnings
    )


def test_unresolved_newer_economic_report_is_not_used() -> None:
    prices = pd.DataFrame(
        [
            {
                "ticker": "000660",
                "date": "2026-05-15",
                "close_price": 110.0,
                "adjusted": False,
            }
        ]
    )
    shares = pd.DataFrame(
        [
            {
                "ticker": "000660",
                "business_year": 2025,
                "report_code": "11011",
                "period_end": "2025-12-31",
                "available_date": "2026-03-10",
                "security_name": "보통주",
                "security_class": "common",
                "issued_shares": 50,
                "normalization_warning": "",
            },
            {
                "ticker": "000660",
                "business_year": 2026,
                "report_code": "11013",
                "period_end": "2026-03-31",
                "available_date": "2026-05-15",
                "security_name": "보통주",
                "security_class": "common",
                "issued_shares": 0,
                "normalization_warning": "unresolved_missing_economic_share_count",
            },
        ]
    )
    financials = pd.DataFrame(
        [
            {
                "ticker": "000660",
                "period_end": "2026-03-31",
                "available_date": "2026-05-15",
                "equity": 1_100.0,
                "derived": False,
            }
        ]
    )

    evidence = build_historical_pb_evidence(
        prices,
        shares,
        financials,
        evaluation_date=date(2026, 8, 10),
    )

    assert evidence.series.iloc[0]["share_available_date"] == date(2026, 3, 10)
    assert evidence.series.iloc[0]["market_cap"] == 5_500.0
    assert any("2026/11013" in warning for warning in evidence.warnings)
