from __future__ import annotations

from alpha_cycle.kis_expectation_semantic_crosscheck_cli import PeriodAxis
from alpha_cycle.kis_owner_net_income_crosscheck_cli import (
    OWNER_NET_INCOME_ACCOUNT_ID,
    OWNER_NET_INCOME_METRIC,
    _discover_owner_matches,
    _owner_actuals,
)


def _period(year: int, current: float, prior: float) -> dict[str, object]:
    return {
        "business_year": year,
        "report_code": "11011",
        "payload": {
            "list": [
                {
                    "sj_div": "CIS",
                    "account_id": OWNER_NET_INCOME_ACCOUNT_ID,
                    "account_nm": "Profit attributable to owners of the parent",
                    "account_detail": "-",
                    "thstrm_amount": str(current),
                    "frmtrm_amount": str(prior),
                }
            ]
        },
    }


def _raw_valuation() -> dict[str, object]:
    return {
        "000660": {
            "financial_periods": [
                _period(2024, 19_740_000_000_000, -9_112_400_000_000),
                _period(2025, 42_950_000_000_000, 19_740_000_000_000),
            ]
        },
        "005930": {
            "financial_periods": [
                _period(2024, 33_621_400_000_000, 14_473_400_000_000),
                _period(2025, 44_261_000_000_000, 33_621_400_000_000),
            ]
        },
    }


def _payloads() -> dict[str, dict[str, object]]:
    return {
        "000660": {
            "output2": [
                {"data1": "1", "data2": "1", "data3": "1", "data4": "1", "data5": "1"},
                {"data1": "2", "data2": "2", "data3": "2", "data4": "2", "data5": "2"},
                {"data1": "3", "data2": "3", "data3": "3", "data4": "3", "data5": "3"},
                {"data1": "4", "data2": "4", "data3": "4", "data4": "4", "data5": "4"},
                {
                    "data1": "-91124",
                    "data2": "197400",
                    "data3": "429500",
                    "data4": "999999",
                    "data5": "888888",
                },
                {"data1": "6", "data2": "6", "data3": "6", "data4": "6", "data5": "6"},
            ],
            "output3": [
                {"data1": "7", "data2": "7", "data3": "7", "data4": "7", "data5": "7"}
            ],
        },
        "005930": {
            "output2": [
                {"data1": "1", "data2": "1", "data3": "1", "data4": "1", "data5": "1"},
                {"data1": "2", "data2": "2", "data3": "2", "data4": "2", "data5": "2"},
                {"data1": "3", "data2": "3", "data3": "3", "data4": "3", "data5": "3"},
                {"data1": "4", "data2": "4", "data3": "4", "data4": "4", "data5": "4"},
                {
                    "data1": "144734",
                    "data2": "336214",
                    "data3": "442610",
                    "data4": "777777",
                    "data5": "666666",
                },
                {"data1": "6", "data2": "6", "data3": "6", "data4": "6", "data5": "6"},
            ],
            "output3": [
                {"data1": "7", "data2": "7", "data3": "7", "data4": "7", "data5": "7"}
            ],
        },
    }


def test_owner_actuals_use_comparative_then_current_year() -> None:
    actuals, basis = _owner_actuals(_raw_valuation(), years=(2023, 2024, 2025))

    assert actuals[("005930", 2023, OWNER_NET_INCOME_METRIC)] == 14_473_400_000_000
    assert actuals[("005930", 2024, OWNER_NET_INCOME_METRIC)] == 33_621_400_000_000
    assert actuals[("005930", 2025, OWNER_NET_INCOME_METRIC)] == 44_261_000_000_000
    assert basis["005930"]["2023"]["source"] == "2024_FY_prior_same"
    assert basis["005930"]["2025"]["source"] == "2025_FY_current"
    assert basis["005930"]["2023"]["account_id"] == OWNER_NET_INCOME_ACCOUNT_ID


def test_owner_crosscheck_identifies_output2_row5_without_forecast_values() -> None:
    actuals, _ = _owner_actuals(_raw_valuation(), years=(2023, 2024, 2025))
    axis = PeriodAxis(
        labels=("2023.12", "2024.12", "2025.12", "2026.12E", "2027.12E"),
        actual_years=(2023, 2024, 2025),
        actual_fields_positional=("data1", "data2", "data3"),
        forecast_labels=("2026.12E", "2027.12E"),
        forecast_fields_positional=("data4", "data5"),
    )

    matches = _discover_owner_matches(_payloads(), actuals, axis)

    assert len(matches) == 1
    match = matches[0]
    assert match.output_name == "output2"
    assert match.row_index == 4
    assert match.scale == 100_000_000.0
    assert match.year_to_field == (
        (2023, "data1"),
        (2024, "data2"),
        (2025, "data3"),
    )


def test_owner_actuals_require_exact_standard_account_id() -> None:
    raw = _raw_valuation()
    company = raw["005930"]
    assert isinstance(company, dict)
    periods = company["financial_periods"]
    assert isinstance(periods, list)
    payload = periods[0]["payload"]
    assert isinstance(payload, dict)
    rows = payload["list"]
    assert isinstance(rows, list)
    rows[0]["account_id"] = "custom_similar_profit_account"

    try:
        _owner_actuals(raw, years=(2023, 2024, 2025))
    except ValueError as exc:
        assert "owner-attributable net-income account not found" in str(exc)
    else:
        raise AssertionError("Expected exact account-id validation to fail")
