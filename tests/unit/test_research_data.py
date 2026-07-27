from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from alpha_cycle.data.research import (
    CsvFinancialDataAdapter,
    CsvMacroDataAdapter,
    FinancialStatementStore,
    MacroSeriesStore,
    ResearchDataPortal,
    RevisionPolicy,
    validate_financial_statements,
    validate_macro_series,
)


def financial_frame() -> pd.DataFrame:
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
                "revision_id": "filing-v1",
                "revision_sequence": 0,
            },
            {
                "ticker": "AAA",
                "metric": "revenue",
                "period_start": "2023-01-01",
                "period_end": "2023-12-31",
                "fiscal_period": "FY",
                "value": 110,
                "unit": "KRW_mn",
                "currency": "KRW",
                "available_date": "2024-03-01",
                "retrieved_at": "2024-03-01T09:00:00Z",
                "source": "fixture",
                "revision_id": "filing-v2",
                "revision_sequence": 1,
            },
            {
                "ticker": "BBB",
                "metric": "operating_income",
                "period_start": "2023-01-01",
                "period_end": "2023-12-31",
                "fiscal_period": "FY",
                "value": 25,
                "unit": "KRW_mn",
                "currency": "KRW",
                "available_date": "2024-02-15",
                "retrieved_at": "2024-02-15T12:00:00Z",
                "source": "fixture",
                "revision_id": "bbb-v1",
                "revision_sequence": 0,
            },
        ]
    )


def macro_frame() -> pd.DataFrame:
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
                "revision_id": "cpi-v1",
                "revision_sequence": 0,
            },
            {
                "series_id": "CPI_KR",
                "observation_date": "2024-01-01",
                "frequency": "monthly",
                "value": 3.1,
                "unit": "percent_yoy",
                "available_date": "2024-02-20",
                "retrieved_at": "2024-02-20T01:00:00Z",
                "source": "fixture",
                "revision_id": "cpi-v2",
                "revision_sequence": 1,
            },
            {
                "series_id": "POLICY_RATE_KR",
                "observation_date": "2024-01-11",
                "frequency": "event",
                "value": 3.5,
                "unit": "percent",
                "available_date": "2024-01-11",
                "retrieved_at": "2024-01-11T05:00:00Z",
                "source": "fixture",
                "revision_id": "rate-v1",
                "revision_sequence": 0,
            },
        ]
    )


def test_financial_latest_known_and_first_release_differ() -> None:
    store = FinancialStatementStore(financial_frame())
    before_revision = store.as_of(date(2024, 2, 20), ticker="AAA")
    latest = store.as_of(date(2024, 3, 2), ticker="AAA")
    first = store.as_of(
        date(2024, 3, 2),
        policy=RevisionPolicy.FIRST_RELEASE,
        ticker="AAA",
    )
    assert before_revision["value"].tolist() == [100]
    assert latest["value"].tolist() == [110]
    assert first["value"].tolist() == [100]


def test_macro_future_revision_is_not_visible() -> None:
    store = MacroSeriesStore(macro_frame())
    early = store.as_of(date(2024, 2, 10), series_id="CPI_KR")
    late = store.as_of(date(2024, 2, 21), series_id="CPI_KR")
    assert early["value"].tolist() == [3.0]
    assert late["value"].tolist() == [3.1]


def test_revision_sequence_must_be_unique_and_chronological() -> None:
    duplicate = financial_frame()
    duplicate.loc[1, "revision_sequence"] = 0
    with pytest.raises(ValueError, match="Duplicate revision_sequence"):
        validate_financial_statements(duplicate)

    backwards = macro_frame()
    backwards.loc[1, "available_date"] = "2024-02-01"
    with pytest.raises(ValueError, match="cannot move backwards"):
        validate_macro_series(backwards)


def test_release_and_retrieval_chronology_is_enforced() -> None:
    early_release = financial_frame()
    early_release.loc[0, "available_date"] = "2023-12-01"
    with pytest.raises(ValueError, match="cannot precede period_end"):
        validate_financial_statements(early_release)

    early_retrieval = macro_frame()
    early_retrieval.loc[0, "retrieved_at"] = "2024-02-01T00:00:00Z"
    with pytest.raises(ValueError, match="retrieved_at cannot precede"):
        validate_macro_series(early_retrieval)


def test_non_integer_revision_sequence_is_rejected() -> None:
    broken = macro_frame()
    broken["revision_sequence"] = broken["revision_sequence"].astype(float)
    broken.loc[0, "revision_sequence"] = 0.5
    with pytest.raises(ValueError, match="non-negative integer"):
        validate_macro_series(broken)


def test_filters_are_deterministic() -> None:
    store = FinancialStatementStore(financial_frame().sample(frac=1, random_state=3))
    selected = store.as_of(date(2024, 3, 2), metric="operating_income")
    assert selected["ticker"].tolist() == ["BBB"]
    assert selected["revision_id"].tolist() == ["bbb-v1"]


def test_csv_adapters_validate_local_files(tmp_path: Path) -> None:
    financial_path = tmp_path / "financials.csv"
    macro_path = tmp_path / "macro.csv"
    financial_frame().to_csv(financial_path, index=False)
    macro_frame().to_csv(macro_path, index=False)
    financials = CsvFinancialDataAdapter(financial_path).load()
    macro = CsvMacroDataAdapter(macro_path).load()
    assert len(financials) == 3
    assert len(macro) == 3
    assert isinstance(macro["retrieved_at"].dtype, pd.DatetimeTZDtype)
    assert str(macro["retrieved_at"].dt.tz) == "UTC"


def test_portal_builds_synchronized_defensive_snapshots() -> None:
    portal = ResearchDataPortal(
        financials=FinancialStatementStore(financial_frame()),
        macro=MacroSeriesStore(macro_frame()),
        revision_policy=RevisionPolicy.LATEST_KNOWN,
    )
    snapshot = portal.snapshot(date(2024, 2, 12))
    assert snapshot.financials["ticker"].tolist() == ["AAA"]
    assert snapshot.macro["series_id"].tolist() == ["CPI_KR", "POLICY_RATE_KR"]
    snapshot.financials.loc[:, "value"] = -999
    fresh = portal.snapshot(date(2024, 2, 12))
    assert fresh.financials["value"].tolist() == [100]


def test_empty_portal_side_has_stable_schema() -> None:
    portal = ResearchDataPortal(macro=MacroSeriesStore(macro_frame()))
    snapshot = portal.snapshot(date(2024, 2, 10))
    assert snapshot.financials.empty
    assert "revision_sequence" in snapshot.financials.columns
    assert not snapshot.macro.empty
