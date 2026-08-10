"""Fail-closed regression test for unresolved economic share counts."""

from datetime import date

import pandas as pd

from alpha_cycle.intelligence.historical_pb import _market_cap_for_date


def test_market_cap_rejects_unresolved_zero_share_class() -> None:
    report_rows = pd.DataFrame(
        [
            {
                "security_name": "보통주",
                "security_class": "common",
                "issued_shares": 100,
                "normalization_warning": None,
            },
            {
                "security_name": "우선주",
                "security_class": "preferred",
                "issued_shares": 0,
                "normalization_warning": (
                    "우선주: schema value set to zero via "
                    "unresolved_missing_economic_share_count"
                ),
            },
        ]
    )

    market_cap, parts, reason = _market_cap_for_date(
        ticker="005930",
        as_of=date(2026, 8, 10),
        report_rows=report_rows,
        price_lookup={
            ("005930", date(2026, 8, 10)): 100.0,
            ("005935", date(2026, 8, 10)): 80.0,
        },
        mappings={},
    )

    assert market_cap is None
    assert parts == []
    assert reason == "unresolved_share_count:우선주"
