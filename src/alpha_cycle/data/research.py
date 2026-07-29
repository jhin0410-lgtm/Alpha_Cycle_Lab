"""Revision-aware point-in-time financial and macro research data contracts."""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date
from enum import StrEnum
from pathlib import Path
from typing import Any, Protocol, cast

import pandas as pd


class RevisionPolicy(StrEnum):
    """How a point-in-time snapshot selects among known revisions."""

    FIRST_RELEASE = "first_release"
    LATEST_KNOWN = "latest_known"


COMMON_REVISION_COLUMNS = (
    "available_date",
    "retrieved_at",
    "source",
    "revision_id",
    "revision_sequence",
)
FINANCIAL_REQUIRED = (
    "ticker",
    "metric",
    "period_end",
    "fiscal_period",
    "value",
    "unit",
    *COMMON_REVISION_COLUMNS,
)
FINANCIAL_OPTIONAL = ("period_start", "currency")
MACRO_REQUIRED = (
    "series_id",
    "observation_date",
    "frequency",
    "value",
    "unit",
    *COMMON_REVISION_COLUMNS,
)
MAX_CIVIL_UTC_OFFSET_HOURS = 14


class FinancialDataAdapter(Protocol):
    """Boundary for deterministic financial-data loaders."""

    def load(self) -> pd.DataFrame:
        """Return a validated canonical financial facts frame."""
        ...


class MacroDataAdapter(Protocol):
    """Boundary for deterministic macro-data loaders."""

    def load(self) -> pd.DataFrame:
        """Return a validated canonical macro observations frame."""
        ...


def _required_text(data: pd.DataFrame, column: str) -> None:
    if data[column].isna().any():
        raise ValueError(f"{column} cannot be missing")
    values = data[column].astype(str).str.strip()
    if values.eq("").any():
        raise ValueError(f"{column} cannot be empty")
    data[column] = values


def _optional_dates(series: pd.Series[Any]) -> pd.Series[Any]:
    def parse(value: Any) -> date | pd._libs.tslibs.nattype.NaTType:
        if pd.isna(value):
            return pd.NaT
        return pd.Timestamp(value).date()

    return series.map(parse)


def _validate_revision_columns(data: pd.DataFrame) -> None:
    if data[list(COMMON_REVISION_COLUMNS)].isna().any().any():
        raise ValueError("Revision required values cannot be missing")
    for column in ("source", "revision_id"):
        _required_text(data, column)
    data["available_date"] = pd.to_datetime(
        data["available_date"], errors="raise"
    ).dt.date
    data["retrieved_at"] = pd.to_datetime(
        data["retrieved_at"], errors="raise", utc=True
    )
    sequence = pd.to_numeric(data["revision_sequence"], errors="raise")
    if ((sequence % 1) != 0).any() or (sequence < 0).any():
        raise ValueError("revision_sequence must be a non-negative integer")
    data["revision_sequence"] = sequence.astype("int64")


def _retrieval_covers_available_date(retrieved: pd.Timestamp, available: date) -> bool:
    """Allow a source-local date to be up to the civil UTC+14 boundary."""

    latest_possible_source_date = (
        retrieved + pd.Timedelta(hours=MAX_CIVIL_UTC_OFFSET_HOURS)
    ).date()
    return latest_possible_source_date >= available


def _validate_revision_order(data: pd.DataFrame, key_columns: list[str]) -> None:
    if data.duplicated([*key_columns, "revision_sequence"]).any():
        raise ValueError("Duplicate revision_sequence for one observation")
    if data.duplicated([*key_columns, "revision_id"]).any():
        raise ValueError("Duplicate revision_id for one observation")
    ordered = data.sort_values(
        [*key_columns, "revision_sequence", "available_date", "retrieved_at"],
        kind="stable",
    )
    for _, group in ordered.groupby(key_columns, sort=True, dropna=False):
        previous_available: date | None = None
        for _, row in group.iterrows():
            available = cast(date, row["available_date"])
            if previous_available is not None and available < previous_available:
                raise ValueError(
                    "Revision available_date cannot move backwards as revision_sequence increases"
                )
            previous_available = available


def _select_revisions(
    data: pd.DataFrame,
    key_columns: list[str],
    evaluation_date: date,
    policy: RevisionPolicy,
) -> pd.DataFrame:
    known = data.loc[data["available_date"] <= evaluation_date].copy()
    if known.empty:
        return known
    ordered = known.sort_values(
        [*key_columns, "available_date", "revision_sequence", "retrieved_at", "revision_id"],
        kind="stable",
    )
    grouped = ordered.groupby(key_columns, sort=True, dropna=False, group_keys=False)
    selected = grouped.head(1) if policy is RevisionPolicy.FIRST_RELEASE else grouped.tail(1)
    return selected.sort_values(key_columns, kind="stable").reset_index(drop=True)


def validate_financial_statements(frame: pd.DataFrame) -> pd.DataFrame:
    """Validate versioned financial facts and return a deterministic canonical frame."""
    missing = sorted(set(FINANCIAL_REQUIRED) - set(frame.columns))
    if missing:
        raise ValueError(f"Missing financial columns: {', '.join(missing)}")
    data = frame.copy()
    for column in FINANCIAL_OPTIONAL:
        if column not in data.columns:
            data[column] = pd.NA
    canonical = [*FINANCIAL_REQUIRED, *FINANCIAL_OPTIONAL]
    if data.empty:
        return data.loc[:, canonical]
    if data[list(FINANCIAL_REQUIRED)].isna().any().any():
        raise ValueError("Financial required values cannot be missing")
    for column in ("ticker", "metric", "fiscal_period", "unit"):
        _required_text(data, column)
    data["period_end"] = pd.to_datetime(data["period_end"], errors="raise").dt.date
    data["period_start"] = _optional_dates(data["period_start"])
    data["value"] = pd.to_numeric(data["value"], errors="raise")
    if not data["value"].map(math.isfinite).all():
        raise ValueError("Financial value must be finite")
    currency_present = data["currency"].notna()
    if currency_present.any():
        currencies = data.loc[currency_present, "currency"].astype(str).str.strip()
        if currencies.eq("").any():
            raise ValueError("currency cannot be empty when provided")
        data.loc[currency_present, "currency"] = currencies
    _validate_revision_columns(data)
    for _, row in data.iterrows():
        period_end = cast(date, row["period_end"])
        period_start_value: Any = row["period_start"]
        period_start = None if pd.isna(period_start_value) else cast(date, period_start_value)
        available = cast(date, row["available_date"])
        retrieved = cast(pd.Timestamp, row["retrieved_at"])
        if period_start is not None and period_start > period_end:
            raise ValueError("period_start cannot follow period_end")
        if available < period_end:
            raise ValueError("Financial available_date cannot precede period_end")
        if not _retrieval_covers_available_date(retrieved, available):
            raise ValueError("retrieved_at cannot precede source-local available_date")
    keys = ["ticker", "metric", "period_end", "fiscal_period"]
    _validate_revision_order(data, keys)
    return data.loc[:, canonical].sort_values(
        [*keys, "revision_sequence", "available_date", "revision_id"],
        kind="stable",
    ).reset_index(drop=True)


def validate_macro_series(frame: pd.DataFrame) -> pd.DataFrame:
    """Validate versioned macro observations and return a deterministic canonical frame."""
    missing = sorted(set(MACRO_REQUIRED) - set(frame.columns))
    if missing:
        raise ValueError(f"Missing macro columns: {', '.join(missing)}")
    data = frame.copy()
    if data.empty:
        return data.loc[:, list(MACRO_REQUIRED)]
    if data[list(MACRO_REQUIRED)].isna().any().any():
        raise ValueError("Macro required values cannot be missing")
    for column in ("series_id", "frequency", "unit"):
        _required_text(data, column)
    data["observation_date"] = pd.to_datetime(
        data["observation_date"], errors="raise"
    ).dt.date
    data["value"] = pd.to_numeric(data["value"], errors="raise")
    if not data["value"].map(math.isfinite).all():
        raise ValueError("Macro value must be finite")
    _validate_revision_columns(data)
    for _, row in data.iterrows():
        observation = cast(date, row["observation_date"])
        available = cast(date, row["available_date"])
        retrieved = cast(pd.Timestamp, row["retrieved_at"])
        if available < observation:
            raise ValueError("Macro available_date cannot precede observation_date")
        if not _retrieval_covers_available_date(retrieved, available):
            raise ValueError("retrieved_at cannot precede source-local available_date")
    keys = ["series_id", "observation_date"]
    _validate_revision_order(data, keys)
    return data.loc[:, list(MACRO_REQUIRED)].sort_values(
        [*keys, "revision_sequence", "available_date", "revision_id"],
        kind="stable",
    ).reset_index(drop=True)


class FinancialStatementStore:
    """Point-in-time access to revisioned company financial facts."""

    def __init__(self, frame: pd.DataFrame) -> None:
        self._data = validate_financial_statements(frame)

    @classmethod
    def from_csv(cls, path: str | Path) -> FinancialStatementStore:
        """Load a local CSV without network access."""
        return cls(pd.read_csv(path))

    def as_of(
        self,
        evaluation_date: date,
        *,
        policy: RevisionPolicy = RevisionPolicy.LATEST_KNOWN,
        ticker: str | None = None,
        metric: str | None = None,
    ) -> pd.DataFrame:
        """Return one selected revision per financial observation known by the date."""
        selected = _select_revisions(
            self._data,
            ["ticker", "metric", "period_end", "fiscal_period"],
            evaluation_date,
            policy,
        )
        if ticker is not None:
            selected = selected.loc[selected["ticker"] == ticker]
        if metric is not None:
            selected = selected.loc[selected["metric"] == metric]
        return selected.reset_index(drop=True).copy()


class MacroSeriesStore:
    """Point-in-time access to revisioned macroeconomic observations."""

    def __init__(self, frame: pd.DataFrame) -> None:
        self._data = validate_macro_series(frame)

    @classmethod
    def from_csv(cls, path: str | Path) -> MacroSeriesStore:
        """Load a local CSV without network access."""
        return cls(pd.read_csv(path))

    def as_of(
        self,
        evaluation_date: date,
        *,
        policy: RevisionPolicy = RevisionPolicy.LATEST_KNOWN,
        series_id: str | None = None,
    ) -> pd.DataFrame:
        """Return one selected revision per macro observation known by the date."""
        selected = _select_revisions(
            self._data,
            ["series_id", "observation_date"],
            evaluation_date,
            policy,
        )
        if series_id is not None:
            selected = selected.loc[selected["series_id"] == series_id]
        return selected.reset_index(drop=True).copy()


@dataclass(frozen=True)
class CsvFinancialDataAdapter:
    """Local CSV adapter for financial facts."""

    path: Path

    def load(self) -> pd.DataFrame:
        return validate_financial_statements(pd.read_csv(self.path))


@dataclass(frozen=True)
class CsvMacroDataAdapter:
    """Local CSV adapter for macro observations."""

    path: Path

    def load(self) -> pd.DataFrame:
        return validate_macro_series(pd.read_csv(self.path))


@dataclass(frozen=True)
class ResearchSnapshot:
    """Immutable container of copies visible to research code on one evaluation date."""

    evaluation_date: date
    financials: pd.DataFrame
    macro: pd.DataFrame
    revision_policy: RevisionPolicy


class ResearchDataPortal:
    """Create synchronized financial and macro snapshots without future revisions."""

    def __init__(
        self,
        *,
        financials: FinancialStatementStore | None = None,
        macro: MacroSeriesStore | None = None,
        revision_policy: RevisionPolicy = RevisionPolicy.LATEST_KNOWN,
    ) -> None:
        self.financials = financials
        self.macro = macro
        self.revision_policy = RevisionPolicy(revision_policy)

    def snapshot(self, evaluation_date: date) -> ResearchSnapshot:
        """Return copies containing only observations and revisions known by the date."""
        financial_frame = (
            self.financials.as_of(evaluation_date, policy=self.revision_policy)
            if self.financials is not None
            else pd.DataFrame(columns=list(FINANCIAL_REQUIRED))
        )
        macro_frame = (
            self.macro.as_of(evaluation_date, policy=self.revision_policy)
            if self.macro is not None
            else pd.DataFrame(columns=list(MACRO_REQUIRED))
        )
        return ResearchSnapshot(
            evaluation_date=evaluation_date,
            financials=financial_frame.copy(),
            macro=macro_frame.copy(),
            revision_policy=self.revision_policy,
        )
