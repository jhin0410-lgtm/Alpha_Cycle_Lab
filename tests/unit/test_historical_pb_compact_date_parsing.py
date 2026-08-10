from __future__ import annotations

from datetime import date

import pandas as pd

from alpha_cycle.intelligence.historical_pb import build_historical_pb_evidence


def test_compact_numeric_kiwoom_dates_remain_distinct_calendar_dates() -> None:
    prices = pd.DataFrame(
        [
            {
                "ticker": "005930",
                "date": 20260807,
                "close_price": 100.0,
                "adjusted": False,
            },
            {
                "ticker": "005930",
                "date": 20260810,
                "close_price": 110.0,
                "adjusted": False,
            },
        ]
    )
    shares = pd.DataFrame(
        [
            {
                "ticker": "005930",
                "business_year": 2025,
                "report_code": "11011",
                "period_end": "2025-12-31",
                "available_date": "2026-03-10",
                "security_name": "보통주",
                "security_class": "common",
                "issued_shares": 100,
                "normalization_warning": None,
            }
        ]
    )
    financials = pd.DataFrame(
        [
            {
                "ticker": "005930",
                "period_end": "2025-12-31",
                "available_date": "2026-03-10",
                "equity": 1000.0,
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

    assert evidence.series["date"].tolist() == [
        date(2026, 8, 7),
        date(2026, 8, 10),
    ]
    assert evidence.series["pb"].tolist() == [10.0, 11.0]
    assert evidence.summary.iloc[0]["observation_count"] == 2
    assert evidence.summary.iloc[0]["first_date"] == date(2026, 8, 7)
    assert evidence.summary.iloc[0]["last_date"] == date(2026, 8, 10)
