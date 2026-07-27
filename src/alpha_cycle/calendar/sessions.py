"""Deterministic explicit exchange calendar implementation."""

from __future__ import annotations

from collections.abc import Iterable
from datetime import date, datetime, time
from zoneinfo import ZoneInfo


class ExplicitTradingCalendar:
    """A deterministic calendar that uses an explicit list of trading sessions.

    This implementation does not download official exchange holidays. Instead it
    relies on a caller-provided session list, which is useful for tests and
    example configurations.
    """

    def __init__(
        self,
        *,
        name: str,
        sessions: Iterable[date],
        timezone: ZoneInfo,
        open_time: time,
        close_time: time,
    ) -> None:
        if not name:
            raise ValueError("Calendar name must be provided")
        if not isinstance(timezone, ZoneInfo):
            raise TypeError("timezone must be a ZoneInfo instance")
        if open_time.tzinfo is not None or close_time.tzinfo is not None:
            raise ValueError("Open/close times must be timezone-naive")
        if close_time <= open_time:
            raise ValueError("Session close time must be later than session open time")

        session_values = tuple(sessions)
        if not session_values:
            raise ValueError("Trading sessions must not be empty")
        normalized_sessions = sorted(set(session_values))
        if len(normalized_sessions) != len(session_values):
            raise ValueError("Trading sessions must be unique")

        self.name = name
        self.timezone = timezone
        self._sessions = tuple(normalized_sessions)
        self._open_time = open_time
        self._close_time = close_time

    @property
    def sessions(self) -> tuple[date, ...]:
        """Return the normalized trading session dates."""
        return self._sessions

    def is_session(self, value: date) -> bool:
        """Return True when the provided calendar date is a trading session."""
        return value in self._sessions

    def next_session(self, value: date) -> date:
        """Return the first trading session strictly after the provided date."""
        for session in self._sessions:
            if session > value:
                return session
        raise ValueError(f"No later trading session after {value}")

    def previous_session(self, value: date) -> date:
        """Return the first trading session strictly before the provided date."""
        for session in reversed(self._sessions):
            if session < value:
                return session
        raise ValueError(f"No earlier trading session before {value}")

    def sessions_between(
        self,
        start: date,
        end: date,
        *,
        inclusive: bool = True,
    ) -> list[date]:
        """Return trading sessions in the inclusive or exclusive range."""
        if start > end:
            raise ValueError("start date must be before or equal to end date")
        if inclusive:
            return [session for session in self._sessions if start <= session <= end]
        return [session for session in self._sessions if start < session < end]

    def session_open(self, value: date) -> datetime:
        """Return the timezone-aware session open timestamp for a trading session."""
        if not self.is_session(value):
            raise ValueError(f"{value} is not a trading session")
        return datetime.combine(value, self._open_time, tzinfo=self.timezone)

    def session_close(self, value: date) -> datetime:
        """Return the timezone-aware session close timestamp for a trading session."""
        if not self.is_session(value):
            raise ValueError(f"{value} is not a trading session")
        return datetime.combine(value, self._close_time, tzinfo=self.timezone)

    def session_label(self, timestamp: datetime) -> date:
        """Convert a timezone-aware timestamp to its local trading-session date."""
        if timestamp.tzinfo is None:
            raise ValueError("Timestamp must be timezone-aware")
        local_date = timestamp.astimezone(self.timezone).date()
        if not self.is_session(local_date):
            raise ValueError(f"{local_date} is not a trading session")
        return local_date
