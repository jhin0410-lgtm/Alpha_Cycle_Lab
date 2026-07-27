"""Trading calendar protocol and helper exceptions."""

from __future__ import annotations

from datetime import date, datetime
from typing import Protocol
from zoneinfo import ZoneInfo


class TradingCalendar(Protocol):
    """Protocol for exchange calendars used by the backtest engine.

    Calendar dates represent calendar days; trading sessions are the exchange's
    valid business-day buckets. A session has a timezone-aware open and close
    timestamp, and strategies operate on session dates rather than raw rows.
    """

    timezone: ZoneInfo

    def is_session(self, value: date) -> bool:
        """Return True when the provided calendar date is a trading session."""
        ...

    def next_session(self, value: date) -> date:
        """Return the first trading session strictly after the provided date."""
        ...

    def previous_session(self, value: date) -> date:
        """Return the first trading session strictly before the provided date."""
        ...

    def sessions_between(
        self,
        start: date,
        end: date,
        *,
        inclusive: bool = True,
    ) -> list[date]:
        """Return trading sessions between the two dates.

        The returned list is sorted and excludes dates outside the requested range.
        """
        ...

    def session_open(self, value: date) -> datetime:
        """Return the timezone-aware session open timestamp for a trading session."""
        ...

    def session_close(self, value: date) -> datetime:
        """Return the timezone-aware session close timestamp for a trading session."""
        ...

    def session_label(self, timestamp: datetime) -> date:
        """Convert a timezone-aware timestamp back to its trading session date."""
        ...
