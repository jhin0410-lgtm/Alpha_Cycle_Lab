"""Tests for human-readable financial values in decision reports."""

from __future__ import annotations

import pandas as pd

from alpha_cycle.intelligence.report_financial_formatting import (
    apply_financial_report_formatting,
)


def test_financial_report_formats_percentage_points_and_krw_units() -> None:
    report = "\n".join(
        [
            "# Alpha Cycle 투자 의사결정 리포트",
            "",
            "## 000660",
            "",
            "- 영업이익률 변화: 13.139937803894902%p",
            "- FCF: 25854202000000.0",
            "",
            "## 005930",
            "",
            "- 영업이익률 변화: -2.1925493740502953%p",
            "- FCF: -37792969000000.0",
        ]
    )
    financial = pd.DataFrame(
        [
            {
                "ticker": "000660",
                "operating_margin_change_pp": 13.139937803894902,
                "free_cash_flow": 25_854_202_000_000.0,
            },
            {
                "ticker": "005930",
                "operating_margin_change_pp": -2.1925493740502953,
                "free_cash_flow": -37_792_969_000_000.0,
            },
        ]
    )

    formatted = apply_financial_report_formatting(report, financial)

    assert "- 영업이익률 변화: +13.1%p" in formatted
    assert "- FCF: 25.85조 원" in formatted
    assert "- 영업이익률 변화: -2.2%p" in formatted
    assert "- FCF: -37.79조 원" in formatted
    assert "13.139937803894902" not in formatted


def test_financial_report_is_unchanged_without_ticker_column() -> None:
    report = "# report\n"

    assert apply_financial_report_formatting(
        report,
        pd.DataFrame({"free_cash_flow": [1.0]}),
    ) == report
