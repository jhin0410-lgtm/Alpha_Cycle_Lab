"""Simple rebalance scheduling utilities rooted in the trading calendar."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Protocol

from alpha_cycle.calendar.base import TradingCalendar


class RebalanceSchedule(Protocol):
    """Determine whether a rebalance should occur for a trading session."""

    def should_rebalance(self, session: date, calendar: TradingCalendar) -> bool:
        """Return True when the supplied session should trigger a rebalance."""
        ...


@dataclass(frozen=True)
class WeeklyRebalanceSchedule:
    """Rebalance on each week's first trading session by default."""

    anchor: str = "first_session"

    def should_rebalance(self, session: date, calendar: TradingCalendar) -> bool:
        if self.anchor != "first_session":
            raise ValueError("Only first_session anchor is supported")
        if not calendar.is_session(session):
            raise ValueError(f"{session} is not a trading session")
        month_start = date(session.year, session.month, 1)
        first_session = calendar.next_session(month_start - timedelta(days=1))
        return session == first_session


@dataclass(frozen=True)
class MonthlyRebalanceSchedule:
    """Rebalance on each month's first trading session by default."""

    anchor: str = "first_session"

    def should_rebalance(self, session: date, calendar: TradingCalendar) -> bool:
        if self.anchor != "first_session":
            raise ValueError("Only first_session anchor is supported")
        if not calendar.is_session(session):
            raise ValueError(f"{session} is not a trading session")
        month_start = date(session.year, session.month, 1)
        first_session = calendar.next_session(month_start - timedelta(days=1))
        return session == first_session
