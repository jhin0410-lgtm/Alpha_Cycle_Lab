from __future__ import annotations

from datetime import date

import pandas as pd

from alpha_cycle.intelligence.semiconductor_cycle_proxy import (
    append_semiconductor_cycle_proxy_report,
    attach_semiconductor_cycle_proxy_to_records,
    attach_semiconductor_cycle_proxy_to_scorecards,
    build_semiconductor_cycle_proxy,
)


def _history() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "ticker": "005930",
                "period_label": "Q1",
                "period_order": 1,
                "period_end": date(2026, 3, 31),
                "available_date": date(2026, 5, 15),
                "derived": False,
                "revenue_yoy": 0.692,
                "operating_income_yoy": 7.561,
                "operating_margin_change_yoy_pp": 10.0,
                "inventory": 60.0,
                "inventory_prior_same": 55.0,
                "capex_ytd": -8.0,
                "capex_prior_ytd": -7.0,
            },
            {
                "ticker": "000660",
                "period_label": "Q1",
                "period_order": 1,
                "period_end": date(2026, 3, 31),
                "available_date": date(2026, 5, 15),
                "derived": False,
                "revenue_yoy": 1.981,
                "operating_income_yoy": 4.055,
                "operating_margin_change_yoy_pp": 18.0,
                "inventory": 20.0,
                "inventory_prior_same": 18.0,
                "capex_ytd": -6.0,
                "capex_prior_ytd": -4.0,
            },
        ]
    )


def _market(*, positive: bool) -> pd.DataFrame:
    value = 0.10 if positive else -0.10
    return pd.DataFrame(
        [
            {
                "ticker": "005930",
                "last_price": 100.0,
                "return_20": value,
                "return_60": value,
                "price_to_sma_20": value,
            },
            {
                "ticker": "000660",
                "last_price": 200.0,
                "return_20": value,
                "return_60": value,
                "price_to_sma_20": value,
            },
        ]
    )


def test_expanding_issuers_with_weak_prices_are_market_unconfirmed() -> None:
    proxy = build_semiconductor_cycle_proxy(_history(), _market(positive=False))

    assert proxy.industry_cycle_certified is False
    assert proxy.coverage_status == "complete_issuer_proxy"
    assert proxy.cycle_proxy_state == "issuer_expansion_market_unconfirmed"
    assert proxy.aggregate["operating_income_growth_breadth"] == 2
    assert proxy.aggregate["margin_improvement_breadth"] == 2
    assert proxy.aggregate["market_confirmation_breadth"] == 0
    assert all(row["issuer_phase"] == "earnings_expansion" for row in proxy.issuer_rows)


def test_expanding_issuers_with_positive_prices_are_market_confirmed() -> None:
    proxy = build_semiconductor_cycle_proxy(_history(), _market(positive=True))

    assert proxy.cycle_proxy_state == "issuer_expansion_market_confirmed"
    assert proxy.aggregate["market_confirmation_breadth"] == 2


def test_missing_issuer_fails_closed_to_partial_coverage() -> None:
    history = _history().loc[_history()["ticker"] == "005930"].copy()
    proxy = build_semiconductor_cycle_proxy(history, _market(positive=True))

    assert proxy.coverage_status == "partial"
    assert proxy.cycle_proxy_state == "insufficient_issuer_coverage"
    assert proxy.observed_tickers == ("005930",)


def test_cycle_proxy_is_attached_without_changing_existing_scores() -> None:
    proxy = build_semiconductor_cycle_proxy(_history(), _market(positive=False))
    scorecards = pd.DataFrame(
        [
            {"ticker": "005930", "composite_score": 3.38},
            {"ticker": "000660", "composite_score": 3.59},
        ]
    )

    enriched = attach_semiconductor_cycle_proxy_to_scorecards(scorecards, proxy)

    assert list(enriched["composite_score"]) == [3.38, 3.59]
    assert set(enriched["cycle_proxy_state"]) == {"issuer_expansion_market_unconfirmed"}
    assert enriched["industry_cycle_certified"].eq(False).all()

    records = pd.DataFrame(
        [
            {"ticker": "005930", "decision_state": "mixed_setup"},
            {"ticker": "000660", "decision_state": "mixed_setup"},
        ]
    )
    attached = attach_semiconductor_cycle_proxy_to_records(records, enriched)
    assert attached["cycle_proxy_period"].eq("Q1").all()
    assert attached["cycle_proxy_market_confirmed"].eq(False).all()


def test_report_states_limitations_and_non_scoring_scope() -> None:
    proxy = build_semiconductor_cycle_proxy(_history(), _market(positive=False))
    report = append_semiconductor_cycle_proxy_report("# Existing\n", proxy)

    assert "반도체 사이클 프록시" in report
    assert "산업지표 미인증" in report
    assert "현재 의사결정 점수에는 반영하지 않습니다" in report
    assert "issuer_expansion_market_unconfirmed" in report
    assert "KOSIS" in report
