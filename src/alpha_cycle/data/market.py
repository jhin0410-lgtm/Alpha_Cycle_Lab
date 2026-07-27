"""OHLCV schema validation and chronological market-data feed."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

import pandas as pd

from alpha_cycle.calendar.base import TradingCalendar

REQUIRED_COLUMNS = (
    "date",
    "ticker",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "trading_value",
)
OPTIONAL_COLUMNS = ("adjusted_close", "market", "sector", "theme")
NUMERIC_COLUMNS = ("open", "high", "low", "close", "volume", "trading_value")


@dataclass(frozen=True)
class ValidationReport:
    """Useful diagnostics returned with validated market data."""

    rows: int
    tickers: int
    start_date: date
    end_date: date
    periods_by_ticker: dict[str, tuple[date, date, int]]
    age_days: int | None


def validate_ohlcv(
    frame: pd.DataFrame, *, as_of: date | None = None, max_age_days: int | None = None
) -> tuple[pd.DataFrame, ValidationReport]:
    """Validate and return a canonical date/ticker-sorted OHLCV frame."""
    missing = sorted(set(REQUIRED_COLUMNS) - set(frame.columns))
    if missing:
        raise ValueError(f"Missing required columns: {', '.join(missing)}")
    if frame.empty:
        raise ValueError("OHLCV data is empty")

    data = frame.copy()
    data["date"] = pd.to_datetime(data["date"], errors="raise").dt.date
    if data[list(REQUIRED_COLUMNS)].isna().any().any():
        columns = data[list(REQUIRED_COLUMNS)].columns[
            data[list(REQUIRED_COLUMNS)].isna().any()
        ].tolist()
        raise ValueError(f"Missing values in required columns: {', '.join(columns)}")
    if data.duplicated(["date", "ticker"]).any():
        raise ValueError("Duplicate date-ticker rows detected")
    for column in NUMERIC_COLUMNS:
        data[column] = pd.to_numeric(data[column], errors="raise")
        if (data[column] < 0).any():
            raise ValueError(f"Negative values in {column}")
    if (data[["open", "high", "low", "close"]] <= 0).any().any():
        raise ValueError("Prices must be greater than zero")
    if (
        data["high"]
        < data[["open", "close", "low"]].max(axis=1)
    ).any():
        raise ValueError("high is below open, close, or low")
    if (
        data["low"]
        > data[["open", "close", "high"]].min(axis=1)
    ).any():
        raise ValueError("low is above open, close, or high")

    data["ticker"] = data["ticker"].astype(str)
    data = data.sort_values(["date", "ticker"], kind="stable").reset_index(drop=True)
    start = data["date"].min()
    end = data["date"].max()
    periods = {
        str(ticker): (group["date"].min(), group["date"].max(), len(group))
        for ticker, group in data.groupby("ticker", sort=True)
    }
    age = (as_of - end).days if as_of else None
    if max_age_days is not None and age is not None and age > max_age_days:
        raise ValueError(f"Market data is stale by {age} days (maximum {max_age_days})")
    return data, ValidationReport(len(data), data["ticker"].nunique(), start, end, periods, age)


class MarketDataFeed:
    """Chronological market bars that never expose rows after the current event."""

    def __init__(self, data: pd.DataFrame, *, calendar: TradingCalendar | None = None) -> None:
        self.data, self.report = validate_ohlcv(data)
        self._dates = sorted(self.data["date"].unique())
        self.calendar = calendar
        if self.calendar is not None:
            self._validate_calendar_dates()

    def _validate_calendar_dates(self) -> None:
        for event_date in self._dates:
            if not self.calendar.is_session(event_date):
                raise ValueError(f"Market data contains non-trading session date {event_date}")
        for previous, current in zip(self._dates, self._dates[1:], strict=False):
            if current <= previous:
                raise ValueError("Market data dates must be strictly increasing")

    @classmethod
    def from_csv(cls, path: str, *, calendar: TradingCalendar | None = None) -> MarketDataFeed:
        """Load and validate a CSV file."""
        return cls(pd.read_csv(path), calendar=calendar)

    @property
    def dates(self) -> list[date]:
        """Available event dates."""
        return list(self._dates)

    def bars_on(self, event_date: date) -> pd.DataFrame:
        """Return a copy of bars for exactly one date."""
        return self.data.loc[self.data["date"] == event_date].copy()

    def history_through(self, event_date: date) -> pd.DataFrame:
        """Return only information available on or before the event date."""
        return self.data.loc[self.data["date"] <= event_date].copy()

