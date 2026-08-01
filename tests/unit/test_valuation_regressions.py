"""Regression tests for valuation calculation boundaries."""

from __future__ import annotations

from datetime import date

import pandas as pd

from alpha_cycle.intelligence.valuation import (
    append_valuation_report,
    build_financial_history,
)
from alpha_cycle.providers.opendart_valuation import FinancialPeriodPayload


def _period_with_zero_cumulative() -> FinancialPeriodPayload:
    return FinancialPeriodPayload(
        ticker="005930",
        corp_code="00126380",
        business_year=2026,
        report_code="11013",
        period_end=date(2026, 3, 31),
        available_date=date(2026, 5, 15),
        payload={
            "status": "000",
            "list": [
                {
                    "sj_div": "IS",
                    "account_id": "ifrs-full_Revenue",
                    "account_nm": "Revenue",
                    "account_detail": "-",
                    "ord": "1",
                    "thstrm_amount": "10",
                    "thstrm_add_amount": "0",
                    "frmtrm_q_amount": "8",
                    "frmtrm_add_amount": "0",
                },
                {
                    "sj_div": "IS",
                    "account_id": "dart_OperatingIncomeLoss",
                    "account_nm": "Operating income",
                    "account_detail": "-",
                    "ord": "2",
                    "thstrm_amount": "1",
                    "thstrm_add_amount": "0",
                    "frmtrm_q_amount": "1",
                    "frmtrm_add_amount": "0",
                },
                {
                    "sj_div": "IS",
                    "account_id": "ifrs-full_ProfitLoss",
                    "account_nm": "Net income",
                    "account_detail": "-",
                    "ord": "3",
                    "thstrm_amount": "1",
                    "thstrm_add_amount": "0",
                    "frmtrm_q_amount": "1",
                    "frmtrm_add_amount": "0",
                },
            ],
        },
    )


def test_zero_cumulative_amount_is_not_replaced_by_quarter_amount() -> None:
    history = build_financial_history((_period_with_zero_cumulative(),))
    row = history.iloc[0]
    assert row["revenue"] == 10
    assert row["revenue_ytd"] == 0
    assert row["revenue_prior_ytd"] == 0
    assert row["operating_income_ytd"] == 0


def test_connected_valuation_report_removes_unconnected_wording() -> None:
    report = "\n".join(
        [
            "# Alpha Cycle 투자 의사결정 리포트",
            "- 밸류에이션·컨센서스 미연결 시 최종 매수 판단이 아닌 의사결정 보조",
            "- 밸류에이션: 미평가",
        ]
    )
    valuation = pd.DataFrame(
        [
            {
                "ticker": "005930",
                "valuation_status": "complete_peer_relative_scored",
                "market_cap": 1000,
                "market_cap_proxy": 1000,
                "pe": 10,
                "pb": 1.5,
                "ps": 2,
                "fcf_yield": 0.04,
                "valuation_score": 3.5,
            }
        ]
    )
    history = pd.DataFrame(
        [
            {
                "ticker": "005930",
                "business_year": 2026,
                "period_label": "Q1",
                "period_end": date(2026, 3, 31),
                "revenue_yoy": 0.2,
                "operating_income_yoy": 0.3,
                "operating_income_yoy_acceleration": 0.1,
            }
        ]
    )
    updated = append_valuation_report(report, valuation, history)
    assert "밸류에이션 연결·컨센서스 미연결" in updated
    assert "밸류에이션: 하단 상세 섹션 참조" in updated
    assert "밸류에이션·컨센서스 미연결 시" not in updated
