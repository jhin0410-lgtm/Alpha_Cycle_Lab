from __future__ import annotations

from datetime import date, datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd
import pytest

from alpha_cycle.data.integrity import PriceBasis
from alpha_cycle.intelligence.prospective_opportunity_scorekeeping_v2_1 import (
    ProspectiveOpportunityRegistration,
    ScorekeepingEntryRule,
    derive_entry_session,
    persist_scorekeeping_snapshot,
    score_prospective_opportunity,
)

SHA_A = "a" * 64
SHA_B = "b" * 64
SHA_C = "c" * 64
SEOUL = ZoneInfo("Asia/Seoul")


class WeekdayCalendar:
    timezone = SEOUL

    def is_session(self, value: date) -> bool:
        return value.weekday() < 5

    def next_session(self, value: date) -> date:
        current = value + timedelta(days=1)
        while not self.is_session(current):
            current += timedelta(days=1)
        return current

    def previous_session(self, value: date) -> date:
        current = value - timedelta(days=1)
        while not self.is_session(current):
            current -= timedelta(days=1)
        return current

    def sessions_between(
        self,
        start: date,
        end: date,
        *,
        inclusive: bool = True,
    ) -> list[date]:
        sessions: list[date] = []
        current = start
        while current <= end:
            if self.is_session(current):
                sessions.append(current)
            current += timedelta(days=1)
        if inclusive:
            return sessions
        return [item for item in sessions if start < item < end]

    def session_open(self, value: date) -> datetime:
        return datetime.combine(value, time(9, 0), tzinfo=self.timezone)

    def session_close(self, value: date) -> datetime:
        return datetime.combine(value, time(15, 30), tzinfo=self.timezone)

    def session_label(self, timestamp: datetime) -> date:
        return timestamp.astimezone(self.timezone).date()


def _registration(
    *,
    registered_at: datetime | None = None,
    price_basis: PriceBasis = PriceBasis.TOTAL_RETURN_ADJUSTED,
) -> ProspectiveOpportunityRegistration:
    timestamp = registered_at or datetime(2026, 8, 21, 18, 0, tzinfo=SEOUL)
    return ProspectiveOpportunityRegistration(
        registration_id="decision-set-2026-08-21-60d",
        registered_at=timestamp,
        evaluation_date=date(2026, 8, 21),
        entry_session=date(2026, 8, 24),
        entry_rule=ScorekeepingEntryRule.NEXT_AVAILABLE_SESSION_CLOSE,
        horizon_trading_days=60,
        opportunity_set_snapshot_id=SHA_A,
        expectation_overlay_snapshot_id=SHA_B,
        security_ids=("A", "B", "C"),
        base_pareto_frontier_security_ids=("B", "C"),
        expectation_pareto_frontier_security_ids=("A", "C"),
        unique_base_leader_security_id="B",
        unique_expectation_leader_security_id="A",
        benchmark_security_id="BM",
        price_basis=price_basis,
        source_evidence_ids=(SHA_C,),
        guardrail_evidence_id=SHA_A,
    )


def _sessions(calendar: WeekdayCalendar, start: date, horizon: int) -> tuple[date, ...]:
    values = [start]
    current = start
    for _ in range(horizon):
        current = calendar.next_session(current)
        values.append(current)
    return tuple(values)


def _market_data(calendar: WeekdayCalendar) -> pd.DataFrame:
    sessions = _sessions(calendar, date(2026, 8, 24), 60)
    terminal = {"A": 130.0, "B": 110.0, "C": 120.0, "BM": 105.0}
    rows: list[dict[str, object]] = []
    denominator = len(sessions) - 1
    for ticker, final_price in terminal.items():
        for index, session in enumerate(sessions):
            price = 100.0 + (final_price - 100.0) * index / denominator
            rows.append(
                {
                    "date": session,
                    "ticker": ticker,
                    "open": price,
                    "high": price,
                    "low": price,
                    "close": price,
                    "adjusted_close": price,
                    "volume": 1000.0,
                    "trading_value": price * 1000.0,
                }
            )
    return pd.DataFrame(rows)


def test_entry_session_uses_first_not_yet_closed_session() -> None:
    calendar = WeekdayCalendar()
    before_close = datetime(2026, 8, 21, 14, 0, tzinfo=SEOUL)
    after_close = datetime(2026, 8, 21, 18, 0, tzinfo=SEOUL)

    assert derive_entry_session(before_close, calendar=calendar) == date(2026, 8, 21)
    assert derive_entry_session(after_close, calendar=calendar) == date(2026, 8, 24)


def test_registration_rejects_raw_prices() -> None:
    with pytest.raises(ValueError, match="adjusted price basis"):
        _registration(price_basis=PriceBasis.RAW)


def test_scorekeeping_rejects_basis_mismatch_and_unclosed_horizon() -> None:
    calendar = WeekdayCalendar()
    registration = _registration()
    market = _market_data(calendar)
    target = _sessions(calendar, registration.entry_session, 60)[-1]

    with pytest.raises(ValueError, match="price basis"):
        score_prospective_opportunity(
            registration,
            market,
            observed_price_basis=PriceBasis.SPLIT_ADJUSTED,
            calendar=calendar,
            scored_at=calendar.session_close(target) + timedelta(minutes=1),
        )

    with pytest.raises(ValueError, match="has not closed"):
        score_prospective_opportunity(
            registration,
            market,
            observed_price_basis=PriceBasis.TOTAL_RETURN_ADJUSTED,
            calendar=calendar,
            scored_at=calendar.session_close(target) - timedelta(minutes=1),
        )


def test_scorekeeping_fails_closed_when_any_required_session_is_missing() -> None:
    calendar = WeekdayCalendar()
    registration = _registration()
    market = _market_data(calendar)
    sessions = _sessions(calendar, registration.entry_session, 60)
    missing_session = sessions[17]
    market = market.loc[
        ~((market["ticker"] == "B") & (market["date"] == missing_session))
    ].copy()

    with pytest.raises(ValueError, match="missing required scorekeeping sessions for B"):
        score_prospective_opportunity(
            registration,
            market,
            observed_price_basis=PriceBasis.TOTAL_RETURN_ADJUSTED,
            calendar=calendar,
            scored_at=calendar.session_close(sessions[-1]) + timedelta(minutes=1),
        )


def test_scorekeeping_measures_regret_and_expectation_overlay_incremental_value() -> None:
    calendar = WeekdayCalendar()
    registration = _registration()
    market = _market_data(calendar)
    target = _sessions(calendar, registration.entry_session, 60)[-1]

    outcome = score_prospective_opportunity(
        registration,
        market,
        observed_price_basis=PriceBasis.TOTAL_RETURN_ADJUSTED,
        calendar=calendar,
        scored_at=calendar.session_close(target) + timedelta(minutes=1),
    )

    by_security = {item.security_id: item for item in outcome.candidate_outcomes}
    assert outcome.ex_post_winner_security_ids == ("A",)
    assert outcome.benchmark_return == pytest.approx(0.05)
    assert by_security["A"].realized_basis_return == pytest.approx(0.30)
    assert by_security["A"].benchmark_excess_return == pytest.approx(0.25)
    assert by_security["A"].max_close_favorable_excursion == pytest.approx(0.30)
    assert by_security["A"].max_close_adverse_excursion == pytest.approx(0.0)

    assert outcome.base_frontier_best_return == pytest.approx(0.20)
    assert outcome.base_frontier_regret == pytest.approx(0.10)
    assert outcome.base_frontier_contains_ex_post_winner is False
    assert outcome.unique_base_leader_regret == pytest.approx(0.20)

    assert outcome.expectation_frontier_best_return == pytest.approx(0.30)
    assert outcome.expectation_frontier_regret == pytest.approx(0.0)
    assert outcome.expectation_frontier_contains_ex_post_winner is True
    assert outcome.unique_expectation_leader_regret == pytest.approx(0.0)
    assert outcome.expectation_overlay_incremental_best_return == pytest.approx(0.10)
    assert "base_pareto_frontier_missed_ex_post_winner" in outcome.flags


def test_persistence_is_content_addressed_and_refuses_overwrite(tmp_path: Path) -> None:
    registration = _registration()
    target = tmp_path / "registration.json"

    persist_scorekeeping_snapshot(registration, target)
    payload = target.read_text(encoding="utf-8")
    assert registration.snapshot_id in payload

    with pytest.raises(FileExistsError, match="already exists"):
        persist_scorekeeping_snapshot(registration, target)
