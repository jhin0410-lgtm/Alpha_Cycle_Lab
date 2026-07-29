"""Tests for explainable investment decision feature engineering."""

from __future__ import annotations

from datetime import date

import pandas as pd
import pytest

from alpha_cycle.intelligence.decision_features import (
    build_macro_regime,
    build_market_context,
    classify_disclosures,
    extract_financial_kpis,
)


def _financial_row(
    statement: str,
    account_id: str,
    account_name: str,
    current: str,
    prior: str,
) -> dict[str, str]:
    return {
        "sj_div": statement,
        "account_id": account_id,
        "account_nm": account_name,
        "thstrm_amount": current,
        "frmtrm_amount": prior,
        "bfefrmtrm_amount": "80",
        "rcept_no": "20260315000001",
        "account_detail": "-",
        "ord": "1",
    }


def test_extract_financial_kpis_calculates_growth_margins_and_fcf() -> None:
    rows = [
        _financial_row("IS", "ifrs-full_Revenue", "매출액", "120", "100"),
        _financial_row(
            "IS",
            "dart_OperatingIncomeLoss",
            "영업이익",
            "24",
            "10",
        ),
        _financial_row("IS", "ifrs-full_ProfitLoss", "당기순이익", "18", "9"),
        _financial_row("BS", "ifrs-full_Assets", "자산총계", "300", "250"),
        _financial_row("BS", "ifrs-full_Liabilities", "부채총계", "120", "110"),
        _financial_row("BS", "ifrs-full_Equity", "자본총계", "180", "140"),
        _financial_row(
            "CF",
            "ifrs-full_CashFlowsFromUsedInOperatingActivities",
            "영업활동현금흐름",
            "30",
            "20",
        ),
        _financial_row(
            "CF",
            "ifrs-full_PurchaseOfPropertyPlantAndEquipmentClassifiedAsInvestingActivities",
            "유형자산의 취득",
            "8",
            "7",
        ),
        _financial_row("BS", "ifrs-full_CashAndCashEquivalents", "현금", "50", "45"),
        _financial_row("BS", "ifrs-full_Inventories", "재고자산", "40", "30"),
        _financial_row(
            "BS",
            "ifrs-full_TradeAndOtherCurrentReceivables",
            "매출채권",
            "20",
            "18",
        ),
    ]
    raw = {"005930": {"financial": {"financials": {"list": rows}}}}
    wide, mapping, warnings = extract_financial_kpis(raw)
    assert warnings == ()
    assert len(mapping) == 11
    result = wide.iloc[0]
    assert result["revenue_yoy"] == pytest.approx(0.2)
    assert result["operating_income_yoy"] == pytest.approx(1.4)
    assert result["operating_margin"] == pytest.approx(0.2)
    assert result["operating_margin_change_pp"] == pytest.approx(10.0)
    assert result["free_cash_flow"] == pytest.approx(22.0)
    assert result["kpi_coverage"] == pytest.approx(1.0)


def test_disclosure_classifier_removes_insider_noise_from_catalysts() -> None:
    disclosures = pd.DataFrame(
        [
            {
                "ticker": "005930",
                "rcept_no": "20260728000001",
                "report_name": "임원ㆍ주요주주특정증권등소유상황보고서",
                "receipt_date": "2026-07-28",
                "is_correction": False,
            },
            {
                "ticker": "005930",
                "rcept_no": "20260728000002",
                "report_name": "연결재무제표기준영업(잠정)실적(공정공시)",
                "receipt_date": "2026-07-28",
                "is_correction": False,
            },
            {
                "ticker": "005930",
                "rcept_no": "20260728000003",
                "report_name": "신규시설투자등",
                "receipt_date": "2026-07-28",
                "is_correction": False,
            },
        ]
    )
    events, catalysts, summary = classify_disclosures(
        disclosures,
        evaluation_date=date(2026, 7, 29),
    )
    assert len(events) == 3
    assert set(catalysts["category"]) == {"earnings", "capex_investment"}
    assert summary.iloc[0]["noise_disclosures"] == 1
    assert summary.iloc[0]["recent_material_disclosures"] == 2


def test_macro_regime_distinguishes_rate_direction_and_fx_trend() -> None:
    dates = pd.date_range("2026-07-01", periods=21, freq="D")
    macro = pd.DataFrame(
        [
            *[
                {
                    "series_id": "kr_base_rate",
                    "observation_date": day.date(),
                    "value": 2.5 if index < 10 else 2.25,
                    "unit": "%",
                }
                for index, day in enumerate(dates)
            ],
            *[
                {
                    "series_id": "usd_krw",
                    "observation_date": day.date(),
                    "value": 1300 + index * 3,
                    "unit": "KRW/USD",
                }
                for index, day in enumerate(dates)
            ],
        ]
    )
    regimes = build_macro_regime(macro).set_index("series_id")
    assert regimes.loc["kr_base_rate", "regime"] == "easing_last_move"
    assert regimes.loc["usd_krw", "regime"] == "krw_weakening"


def test_market_context_calculates_multi_horizon_and_relative_rank() -> None:
    rows: list[dict[str, object]] = []
    for symbol, slope in (("005930", 1.0), ("000660", 2.0)):
        for index, day in enumerate(pd.date_range("2026-01-01", periods=70, freq="D")):
            price = 100.0 + slope * index
            rows.append(
                {
                    "symbol": symbol,
                    "timestamp": day.isoformat(),
                    "close": price,
                    "high": price + 1,
                    "low": price - 1,
                    "volume": 1000 + index,
                }
            )
    technical = pd.DataFrame(
        [
            {
                "symbol": "005930",
                "rsi_14": 55,
                "trend_efficiency_20": 0.8,
                "trend_direction_20": 1,
            },
            {
                "symbol": "000660",
                "rsi_14": 60,
                "trend_efficiency_20": 0.9,
                "trend_direction_20": 1,
            },
        ]
    )
    context = build_market_context(pd.DataFrame(rows), technical).set_index("ticker")
    assert context.loc["000660", "return_60"] > context.loc["005930", "return_60"]
    assert context.loc["000660", "relative_strength_rank_20"] == pytest.approx(1.0)
    assert context.loc["005930", "rsi_14"] == 55
