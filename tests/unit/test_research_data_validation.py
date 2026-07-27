from __future__ import annotations

import pandas as pd
import pytest

from alpha_cycle.data.research import validate_financial_statements, validate_macro_series


def valid_financial() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "ticker": "AAA",
                "metric": "revenue",
                "period_start": "2023-01-01",
                "period_end": "2023-12-31",
                "fiscal_period": "FY",
                "value": 100,
                "unit": "KRW_mn",
                "currency": "KRW",
                "available_date": "2024-02-10",
                "retrieved_at": "2024-02-10T12:00:00Z",
                "source": "fixture",
                "revision_id": "v1",
                "revision_sequence": 0,
            }
        ]
    )


def valid_macro() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "series_id": "CPI_KR",
                "observation_date": "2024-01-01",
                "frequency": "monthly",
                "value": 3.0,
                "unit": "percent_yoy",
                "available_date": "2024-02-02",
                "retrieved_at": "2024-02-02T01:00:00Z",
                "source": "fixture",
                "revision_id": "v1",
                "revision_sequence": 0,
            }
        ]
    )


def test_missing_required_revision_metadata_is_rejected() -> None:
    broken = valid_financial()
    broken.loc[0, "source"] = pd.NA
    with pytest.raises(ValueError, match="required values cannot be missing"):
        validate_financial_statements(broken)


def test_invalid_optional_financial_date_is_rejected() -> None:
    broken = valid_financial()
    broken.loc[0, "period_start"] = "not-a-date"
    with pytest.raises((ValueError, TypeError)):
        validate_financial_statements(broken)


def test_non_finite_values_are_rejected() -> None:
    financial = valid_financial()
    financial.loc[0, "value"] = float("inf")
    with pytest.raises(ValueError, match="must be finite"):
        validate_financial_statements(financial)

    macro = valid_macro()
    macro.loc[0, "value"] = float("-inf")
    with pytest.raises(ValueError, match="must be finite"):
        validate_macro_series(macro)
