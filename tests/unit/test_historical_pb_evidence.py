from __future__ import annotations

from datetime import date

import pandas as pd
import pytest

from alpha_cycle.intelligence.historical_pb import build_historical_pb_evidence
from alpha_cycle.intelligence.valuation import CompanySecurityMapping


def _prices(*, adjusted: bool = False) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    values = {
        "2026-03-09": {"005930": 90.0, "005935": 45.0, "000660": 180.0},
        "2026-03-10": {"005930": 100.0, "005935": 50.0, "000660": 200.0},
        "2026-05-14": {"005930": 110.0, "005935": 55.0, "000660": 220.0},
        "2026-05-15": {"005930": 120.0, "005935": 60.0, "000660": 240.0},
    }
    for day, by_symbol in values.items():
        for ticker, close in by_symbol.items():
            rows.append(
                {
                    "ticker": ticker,
                    "date": day,
                    "close_price": close,
                    "adjusted": adjusted,
                }
            )
    return pd.DataFrame(rows)


def _shares() -> pd.DataFrame:
    rows = [
        {
            "ticker": "005930",
            "business_year": 2025,
            "report_code": "11011",
            "period_end": "2025-12-31",
            "available_date": "2026-03-10",
            "security_name": "보통주",
            "security_class": "common",
            "issued_shares": 100,
        },
        {
            "ticker": "005930",
            "business_year": 2025,
            "report_code": "11011",
            "period_end": "2025-12-31",
            "available_date": "2026-03-10",
            "security_name": "우선주",
            "security_class": "preferred",
            "issued_shares": 10,
        },
        {
            "ticker": "005930",
            "business_year": 2026,
            "report_code": "11013",
            "period_end": "2026-03-31",
            "available_date": "2026-05-15",
            "security_name": "보통주",
            "security_class": "common",
            "issued_shares": 90,
        },
        {
            "ticker": "005930",
            "business_year": 2026,
            "report_code": "11013",
            "period_end": "2026-03-31",
            "available_date": "2026-05-15",
            "security_name": "우선주",
            "security_class": "preferred",
            "issued_shares": 10,
        },
        {
            "ticker": "000660",
            "business_year": 2025,
            "report_code": "11011",
            "period_end": "2025-12-31",
            "available_date": "2026-03-10",
            "security_name": "보통주",
            "security_class": "common",
            "issued_shares": 50,
        },
        {
            "ticker": "000660",
            "business_year": 2026,
            "report_code": "11013",
            "period_end": "2026-03-31",
            "available_date": "2026-05-15",
            "security_name": "보통주",
            "security_class": "common",
            "issued_shares": 48,
        },
    ]
    return pd.DataFrame(rows)


def _financials() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "ticker": "005930",
                "period_end": "2025-12-31",
                "available_date": "2026-03-10",
                "equity": 5_000.0,
                "derived": False,
            },
            {
                "ticker": "005930",
                "period_end": "2026-03-31",
                "available_date": "2026-05-15",
                "equity": 5_500.0,
                "derived": False,
            },
            {
                "ticker": "000660",
                "period_end": "2025-12-31",
                "available_date": "2026-03-10",
                "equity": 4_000.0,
                "derived": False,
            },
            {
                "ticker": "000660",
                "period_end": "2026-03-31",
                "available_date": "2026-05-15",
                "equity": 4_500.0,
                "derived": False,
            },
        ]
    )


def _mappings() -> dict[str, CompanySecurityMapping]:
    return {
        "005930": CompanySecurityMapping(
            securities={"보통주": "005930", "우선주": "005935"}
        )
    }


def test_pb_uses_only_share_and_equity_reports_available_by_each_price_date() -> None:
    evidence = build_historical_pb_evidence(
        _prices(),
        _shares(),
        _financials(),
        evaluation_date=date(2026, 8, 10),
        security_mappings=_mappings(),
    )

    samsung = evidence.series.loc[evidence.series["ticker"] == "005930"].reset_index(drop=True)
    hynix = evidence.series.loc[evidence.series["ticker"] == "000660"].reset_index(drop=True)
    assert samsung["date"].tolist() == [
        date(2026, 3, 10),
        date(2026, 5, 14),
        date(2026, 5, 15),
    ]
    assert hynix["date"].tolist() == [
        date(2026, 3, 10),
        date(2026, 5, 14),
        date(2026, 5, 15),
    ]

    # 2026-03-10: (100 common * 100 + 10 preferred * 50) / 5,000 equity.
    assert samsung.iloc[0]["pb"] == pytest.approx(2.1)
    assert samsung.iloc[0]["share_available_date"] == date(2026, 3, 10)
    assert samsung.iloc[0]["equity_available_date"] == date(2026, 3, 10)

    # 2026-05-14 still uses the FY report because Q1 was not visible yet.
    assert samsung.iloc[1]["market_cap"] == pytest.approx(11_550.0)
    assert samsung.iloc[1]["equity"] == pytest.approx(5_000.0)
    assert samsung.iloc[1]["pb"] == pytest.approx(2.31)

    # On 2026-05-15 both Q1 share count and Q1 equity become observable.
    assert samsung.iloc[2]["market_cap"] == pytest.approx(11_400.0)
    assert samsung.iloc[2]["equity"] == pytest.approx(5_500.0)
    assert samsung.iloc[2]["pb"] == pytest.approx(11_400.0 / 5_500.0)
    assert samsung.iloc[2]["share_available_date"] == date(2026, 5, 15)
    assert samsung.iloc[2]["equity_available_date"] == date(2026, 5, 15)

    assert evidence.decision_score_enabled is False
    assert evidence.historical_vintage_certified is False
    assert evidence.point_in_time_backtest_eligible is False
    assert set(evidence.summary["band_status"]) == {"insufficient_history"}


def test_pb_rejects_adjusted_prices() -> None:
    with pytest.raises(ValueError, match="unadjusted price rows only"):
        build_historical_pb_evidence(
            _prices(adjusted=True),
            _shares(),
            _financials(),
            evaluation_date=date(2026, 8, 10),
            security_mappings=_mappings(),
        )


def test_pb_requires_explicit_mapping_for_non_common_share_classes() -> None:
    evidence = build_historical_pb_evidence(
        _prices(),
        _shares(),
        _financials(),
        evaluation_date=date(2026, 8, 10),
        security_mappings={},
    )

    assert set(evidence.summary["ticker"]) == {"000660"}
    assert any("005930" in warning and "unmapped_security" in warning for warning in evidence.warnings)
