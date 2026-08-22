"""Prospective scorekeeping for Decision System v2.1 opportunity sets.

This module freezes the decision set before future market outcomes exist and later scores the
same registered candidates on a fixed trading-session horizon. It is an evaluation layer, not a
portfolio recommendation or execution engine.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
from dataclasses import dataclass
from datetime import date, datetime
from enum import StrEnum
from pathlib import Path

import pandas as pd

from alpha_cycle.calendar.base import TradingCalendar
from alpha_cycle.data.integrity import PriceBasis
from alpha_cycle.data.market import validate_ohlcv

PROSPECTIVE_SCOREKEEPING_SCHEMA_VERSION = 1
SUPPORTED_HORIZONS = frozenset({60, 120, 250})


class ScorekeepingEntryRule(StrEnum):
    """Frozen rule that determines the first scored market close."""

    NEXT_AVAILABLE_SESSION_CLOSE = "next_available_session_close"


@dataclass(frozen=True)
class ProspectiveOpportunityRegistration:
    """Immutable ex-ante registration of one cross-sectional decision observation."""

    registration_id: str
    registered_at: datetime
    evaluation_date: date
    entry_session: date
    entry_rule: ScorekeepingEntryRule
    horizon_trading_days: int
    opportunity_set_snapshot_id: str
    expectation_overlay_snapshot_id: str | None
    security_ids: tuple[str, ...]
    base_pareto_frontier_security_ids: tuple[str, ...]
    expectation_pareto_frontier_security_ids: tuple[str, ...]
    unique_base_leader_security_id: str | None
    unique_expectation_leader_security_id: str | None
    benchmark_security_id: str
    price_basis: PriceBasis
    source_evidence_ids: tuple[str, ...]
    guardrail_evidence_id: str

    def __post_init__(self) -> None:
        _require_text(self.registration_id, "registration_id")
        _require_aware(self.registered_at, "registered_at")
        if self.horizon_trading_days not in SUPPORTED_HORIZONS:
            raise ValueError("scorekeeping horizon must be 60, 120, or 250 trading days")
        if self.entry_session < self.evaluation_date:
            raise ValueError("entry_session cannot precede evaluation_date")
        if self.price_basis is PriceBasis.RAW:
            raise ValueError("prospective scorekeeping requires an adjusted price basis")
        _validate_sha(self.opportunity_set_snapshot_id, "opportunity_set_snapshot_id")
        _validate_sha(self.guardrail_evidence_id, "guardrail_evidence_id")
        _validate_sha_tuple(self.source_evidence_ids, "source_evidence_ids")
        if not self.source_evidence_ids:
            raise ValueError("scorekeeping registration requires source evidence")
        _validate_security_tuple(self.security_ids, "security_ids", minimum=2)
        _validate_security_tuple(
            self.base_pareto_frontier_security_ids,
            "base_pareto_frontier_security_ids",
            minimum=1,
        )
        security_set = set(self.security_ids)
        if not set(self.base_pareto_frontier_security_ids).issubset(security_set):
            raise ValueError("base Pareto frontier must be a subset of registered securities")
        _require_text(self.benchmark_security_id, "benchmark_security_id")
        if self.benchmark_security_id in security_set:
            raise ValueError("benchmark security cannot also be a registered candidate")
        if self.unique_base_leader_security_id is not None:
            _require_text(self.unique_base_leader_security_id, "unique_base_leader_security_id")
            if self.unique_base_leader_security_id not in self.base_pareto_frontier_security_ids:
                raise ValueError("unique base leader must belong to the base Pareto frontier")
        if self.expectation_overlay_snapshot_id is None:
            if self.expectation_pareto_frontier_security_ids:
                raise ValueError("expectation frontier requires an overlay snapshot")
            if self.unique_expectation_leader_security_id is not None:
                raise ValueError("expectation leader requires an overlay snapshot")
        else:
            _validate_sha(
                self.expectation_overlay_snapshot_id,
                "expectation_overlay_snapshot_id",
            )
            _validate_security_tuple(
                self.expectation_pareto_frontier_security_ids,
                "expectation_pareto_frontier_security_ids",
                minimum=1,
            )
            if not set(self.expectation_pareto_frontier_security_ids).issubset(security_set):
                raise ValueError(
                    "expectation Pareto frontier must be a subset of registered securities"
                )
            if self.unique_expectation_leader_security_id is not None:
                _require_text(
                    self.unique_expectation_leader_security_id,
                    "unique_expectation_leader_security_id",
                )
                if (
                    self.unique_expectation_leader_security_id
                    not in self.expectation_pareto_frontier_security_ids
                ):
                    raise ValueError(
                        "unique expectation leader must belong to expectation frontier"
                    )

    @property
    def snapshot_id(self) -> str:
        return _sha(self.payload_without_id())

    def payload_without_id(self) -> dict[str, object]:
        return {
            "schema_version": PROSPECTIVE_SCOREKEEPING_SCHEMA_VERSION,
            "registration_id": self.registration_id,
            "registered_at": self.registered_at.isoformat(),
            "evaluation_date": self.evaluation_date.isoformat(),
            "entry_session": self.entry_session.isoformat(),
            "entry_rule": self.entry_rule.value,
            "horizon_trading_days": self.horizon_trading_days,
            "opportunity_set_snapshot_id": self.opportunity_set_snapshot_id,
            "expectation_overlay_snapshot_id": self.expectation_overlay_snapshot_id,
            "security_ids": list(self.security_ids),
            "base_pareto_frontier_security_ids": list(
                self.base_pareto_frontier_security_ids
            ),
            "expectation_pareto_frontier_security_ids": list(
                self.expectation_pareto_frontier_security_ids
            ),
            "unique_base_leader_security_id": self.unique_base_leader_security_id,
            "unique_expectation_leader_security_id": (
                self.unique_expectation_leader_security_id
            ),
            "benchmark_security_id": self.benchmark_security_id,
            "price_basis": self.price_basis.value,
            "source_evidence_ids": list(self.source_evidence_ids),
            "guardrail_evidence_id": self.guardrail_evidence_id,
            "candidate_set_selected_after_outcome": False,
            "benchmark_selected_after_outcome": False,
            "horizon_selected_after_outcome": False,
            "price_basis_selected_after_outcome": False,
            "target_price_enabled": False,
            "capital_allocation_recommendation_enabled": False,
            "automatic_execution_enabled": False,
        }


@dataclass(frozen=True)
class CandidateRealizedOutcome:
    """Observed path statistics for one preregistered security."""

    security_id: str
    entry_price: float
    exit_price: float
    realized_basis_return: float
    benchmark_excess_return: float
    max_close_favorable_excursion: float
    max_close_adverse_excursion: float

    def __post_init__(self) -> None:
        _require_text(self.security_id, "security_id")
        for value, field in (
            (self.entry_price, "entry_price"),
            (self.exit_price, "exit_price"),
            (self.realized_basis_return, "realized_basis_return"),
            (self.benchmark_excess_return, "benchmark_excess_return"),
            (self.max_close_favorable_excursion, "max_close_favorable_excursion"),
            (self.max_close_adverse_excursion, "max_close_adverse_excursion"),
        ):
            _require_finite(value, field)
        if self.entry_price <= 0 or self.exit_price <= 0:
            raise ValueError("outcome prices must be positive")
        if self.max_close_favorable_excursion < 0:
            raise ValueError("max close favorable excursion cannot be negative")
        if self.max_close_adverse_excursion > 0:
            raise ValueError("max close adverse excursion cannot be positive")

    def payload(self) -> dict[str, object]:
        return {
            "security_id": self.security_id,
            "entry_price": self.entry_price,
            "exit_price": self.exit_price,
            "realized_basis_return": self.realized_basis_return,
            "benchmark_excess_return": self.benchmark_excess_return,
            "max_close_favorable_excursion": self.max_close_favorable_excursion,
            "max_close_adverse_excursion": self.max_close_adverse_excursion,
        }


@dataclass(frozen=True)
class ProspectiveOpportunityOutcomeSnapshot:
    """Immutable ex-post score attached to one ex-ante registration."""

    scored_at: datetime
    registration_snapshot_id: str
    entry_session: date
    target_session: date
    horizon_trading_days: int
    price_basis: PriceBasis
    benchmark_security_id: str
    benchmark_return: float
    candidate_outcomes: tuple[CandidateRealizedOutcome, ...]
    ex_post_winner_security_ids: tuple[str, ...]
    base_frontier_best_return: float
    base_frontier_regret: float
    base_frontier_contains_ex_post_winner: bool
    unique_base_leader_regret: float | None
    expectation_frontier_best_return: float | None
    expectation_frontier_regret: float | None
    expectation_frontier_contains_ex_post_winner: bool | None
    unique_expectation_leader_regret: float | None
    expectation_overlay_incremental_best_return: float | None
    flags: tuple[str, ...]

    def __post_init__(self) -> None:
        _require_aware(self.scored_at, "scored_at")
        _validate_sha(self.registration_snapshot_id, "registration_snapshot_id")
        _require_text(self.benchmark_security_id, "benchmark_security_id")
        if self.horizon_trading_days not in SUPPORTED_HORIZONS:
            raise ValueError("outcome horizon must be 60, 120, or 250 trading days")
        if self.target_session <= self.entry_session:
            raise ValueError("target_session must follow entry_session")
        if self.price_basis is PriceBasis.RAW:
            raise ValueError("outcome cannot use raw price basis")
        for value, field in (
            (self.benchmark_return, "benchmark_return"),
            (self.base_frontier_best_return, "base_frontier_best_return"),
            (self.base_frontier_regret, "base_frontier_regret"),
        ):
            _require_finite(value, field)
        for value, field in (
            (self.unique_base_leader_regret, "unique_base_leader_regret"),
            (self.expectation_frontier_best_return, "expectation_frontier_best_return"),
            (self.expectation_frontier_regret, "expectation_frontier_regret"),
            (
                self.unique_expectation_leader_regret,
                "unique_expectation_leader_regret",
            ),
            (
                self.expectation_overlay_incremental_best_return,
                "expectation_overlay_incremental_best_return",
            ),
        ):
            if value is not None:
                _require_finite(value, field)
        if not self.candidate_outcomes:
            raise ValueError("outcome requires candidate observations")
        ids = tuple(item.security_id for item in self.candidate_outcomes)
        if len(set(ids)) != len(ids):
            raise ValueError("candidate outcome security ids must be unique")
        _validate_security_tuple(
            self.ex_post_winner_security_ids,
            "ex_post_winner_security_ids",
            minimum=1,
        )
        if not set(self.ex_post_winner_security_ids).issubset(set(ids)):
            raise ValueError("ex-post winners must belong to candidate outcomes")
        if self.base_frontier_regret < 0:
            raise ValueError("base frontier regret cannot be negative")
        if self.expectation_frontier_regret is not None:
            if self.expectation_frontier_regret < 0:
                raise ValueError("expectation frontier regret cannot be negative")
        _validate_text_tuple(self.flags, "flags")

    @property
    def snapshot_id(self) -> str:
        return _sha(self.payload_without_id())

    def payload_without_id(self) -> dict[str, object]:
        return {
            "schema_version": PROSPECTIVE_SCOREKEEPING_SCHEMA_VERSION,
            "scored_at": self.scored_at.isoformat(),
            "registration_snapshot_id": self.registration_snapshot_id,
            "entry_session": self.entry_session.isoformat(),
            "target_session": self.target_session.isoformat(),
            "horizon_trading_days": self.horizon_trading_days,
            "price_basis": self.price_basis.value,
            "benchmark_security_id": self.benchmark_security_id,
            "benchmark_return": self.benchmark_return,
            "candidate_outcomes": [item.payload() for item in self.candidate_outcomes],
            "ex_post_winner_security_ids": list(self.ex_post_winner_security_ids),
            "base_frontier_best_return": self.base_frontier_best_return,
            "base_frontier_regret": self.base_frontier_regret,
            "base_frontier_contains_ex_post_winner": (
                self.base_frontier_contains_ex_post_winner
            ),
            "unique_base_leader_regret": self.unique_base_leader_regret,
            "expectation_frontier_best_return": self.expectation_frontier_best_return,
            "expectation_frontier_regret": self.expectation_frontier_regret,
            "expectation_frontier_contains_ex_post_winner": (
                self.expectation_frontier_contains_ex_post_winner
            ),
            "unique_expectation_leader_regret": self.unique_expectation_leader_regret,
            "expectation_overlay_incremental_best_return": (
                self.expectation_overlay_incremental_best_return
            ),
            "flags": list(self.flags),
            "post_outcome_candidate_substitution_enabled": False,
            "post_outcome_benchmark_substitution_enabled": False,
            "weighted_ranking_retrofit_enabled": False,
            "automatic_execution_enabled": False,
        }


def derive_entry_session(
    registered_at: datetime,
    *,
    calendar: TradingCalendar,
) -> date:
    """Resolve the first session close not yet known at registration time."""
    _require_aware(registered_at, "registered_at")
    registration_date = registered_at.astimezone(calendar.timezone).date()
    if calendar.is_session(registration_date):
        close = calendar.session_close(registration_date)
        if registered_at < close:
            return registration_date
    return calendar.next_session(registration_date)


def score_prospective_opportunity(
    registration: ProspectiveOpportunityRegistration,
    market_data: pd.DataFrame,
    *,
    observed_price_basis: PriceBasis,
    calendar: TradingCalendar,
    scored_at: datetime,
) -> ProspectiveOpportunityOutcomeSnapshot:
    """Score one registration only after the full frozen trading horizon exists."""
    _require_aware(scored_at, "scored_at")
    if observed_price_basis is not registration.price_basis:
        raise ValueError("observed market price basis does not match registration")
    expected_entry = derive_entry_session(registration.registered_at, calendar=calendar)
    if registration.entry_rule is not ScorekeepingEntryRule.NEXT_AVAILABLE_SESSION_CLOSE:
        raise ValueError("unsupported scorekeeping entry rule")
    if registration.entry_session != expected_entry:
        raise ValueError("registered entry_session does not match frozen entry rule")

    required_sessions = _forward_sessions(
        registration.entry_session,
        registration.horizon_trading_days,
        calendar=calendar,
    )
    target_session = required_sessions[-1]
    if scored_at.astimezone(calendar.timezone) < calendar.session_close(target_session):
        raise ValueError("prospective outcome horizon has not closed yet")

    validated, _ = validate_ohlcv(market_data)
    if "adjusted_close" not in validated.columns:
        raise ValueError("adjusted_close is required for adjusted-basis scorekeeping")
    adjusted = pd.to_numeric(validated["adjusted_close"], errors="raise")
    if adjusted.isna().any() or (adjusted <= 0).any():
        raise ValueError("adjusted_close must be complete and positive")
    validated = validated.copy()
    validated["adjusted_close"] = adjusted.astype(float)

    required_ids = (*registration.security_ids, registration.benchmark_security_id)
    series_by_security = {
        security_id: _complete_adjusted_close_path(
            validated,
            security_id=security_id,
            required_sessions=required_sessions,
        )
        for security_id in required_ids
    }
    benchmark_path = series_by_security[registration.benchmark_security_id]
    benchmark_return = _basis_return(benchmark_path)

    outcomes = tuple(
        _candidate_outcome(
            security_id,
            series_by_security[security_id],
            benchmark_return=benchmark_return,
        )
        for security_id in registration.security_ids
    )
    returns = {item.security_id: item.realized_basis_return for item in outcomes}
    best_return = max(returns.values())
    winners = tuple(
        security_id
        for security_id in registration.security_ids
        if math.isclose(returns[security_id], best_return, rel_tol=0.0, abs_tol=1e-12)
    )

    base_best = max(returns[item] for item in registration.base_pareto_frontier_security_ids)
    base_regret = max(0.0, best_return - base_best)
    base_contains_winner = bool(
        set(winners).intersection(registration.base_pareto_frontier_security_ids)
    )
    base_leader_regret = _leader_regret(
        registration.unique_base_leader_security_id,
        returns,
        best_return,
    )

    expectation_best: float | None = None
    expectation_regret: float | None = None
    expectation_contains: bool | None = None
    expectation_leader_regret: float | None = None
    incremental: float | None = None
    if registration.expectation_overlay_snapshot_id is not None:
        expectation_best = max(
            returns[item] for item in registration.expectation_pareto_frontier_security_ids
        )
        expectation_regret = max(0.0, best_return - expectation_best)
        expectation_contains = bool(
            set(winners).intersection(registration.expectation_pareto_frontier_security_ids)
        )
        expectation_leader_regret = _leader_regret(
            registration.unique_expectation_leader_security_id,
            returns,
            best_return,
        )
        incremental = expectation_best - base_best

    flags: list[str] = []
    if len(winners) > 1:
        flags.append("ex_post_return_tie")
    if not base_contains_winner:
        flags.append("base_pareto_frontier_missed_ex_post_winner")
    if expectation_contains is False:
        flags.append("expectation_pareto_frontier_missed_ex_post_winner")
    if base_leader_regret is not None and base_leader_regret > 0:
        flags.append("unique_base_leader_underperformed_ex_post_winner")
    if expectation_leader_regret is not None and expectation_leader_regret > 0:
        flags.append("unique_expectation_leader_underperformed_ex_post_winner")

    return ProspectiveOpportunityOutcomeSnapshot(
        scored_at=scored_at,
        registration_snapshot_id=registration.snapshot_id,
        entry_session=registration.entry_session,
        target_session=target_session,
        horizon_trading_days=registration.horizon_trading_days,
        price_basis=registration.price_basis,
        benchmark_security_id=registration.benchmark_security_id,
        benchmark_return=benchmark_return,
        candidate_outcomes=outcomes,
        ex_post_winner_security_ids=winners,
        base_frontier_best_return=base_best,
        base_frontier_regret=base_regret,
        base_frontier_contains_ex_post_winner=base_contains_winner,
        unique_base_leader_regret=base_leader_regret,
        expectation_frontier_best_return=expectation_best,
        expectation_frontier_regret=expectation_regret,
        expectation_frontier_contains_ex_post_winner=expectation_contains,
        unique_expectation_leader_regret=expectation_leader_regret,
        expectation_overlay_incremental_best_return=incremental,
        flags=tuple(flags),
    )


def persist_scorekeeping_snapshot(
    snapshot: ProspectiveOpportunityRegistration | ProspectiveOpportunityOutcomeSnapshot,
    path: Path,
) -> None:
    """Persist a content-addressed snapshot without replacing an existing file."""
    if path.exists():
        raise FileExistsError(f"scorekeeping snapshot already exists: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"snapshot_id": snapshot.snapshot_id, **snapshot.payload_without_id()}
    encoded = json.dumps(payload, sort_keys=True, indent=2, ensure_ascii=False) + "\n"
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        temporary.write_text(encoded, encoding="utf-8")
        temporary.replace(path)
    finally:
        if temporary.exists():
            temporary.unlink()


def _forward_sessions(
    entry_session: date,
    horizon_trading_days: int,
    *,
    calendar: TradingCalendar,
) -> tuple[date, ...]:
    if not calendar.is_session(entry_session):
        raise ValueError("entry_session must be a valid trading session")
    sessions = [entry_session]
    current = entry_session
    for _ in range(horizon_trading_days):
        current = calendar.next_session(current)
        sessions.append(current)
    return tuple(sessions)


def _complete_adjusted_close_path(
    data: pd.DataFrame,
    *,
    security_id: str,
    required_sessions: tuple[date, ...],
) -> tuple[float, ...]:
    required_set = set(required_sessions)
    rows = data.loc[
        (data["ticker"] == security_id) & data["date"].isin(required_set),
        ["date", "adjusted_close"],
    ].sort_values("date", kind="stable")
    observed_sessions = tuple(rows["date"].tolist())
    if observed_sessions != required_sessions:
        missing = [item.isoformat() for item in required_sessions if item not in observed_sessions]
        raise ValueError(
            f"missing required scorekeeping sessions for {security_id}: {', '.join(missing)}"
        )
    return tuple(float(item) for item in rows["adjusted_close"].tolist())


def _candidate_outcome(
    security_id: str,
    path: tuple[float, ...],
    *,
    benchmark_return: float,
) -> CandidateRealizedOutcome:
    realized = _basis_return(path)
    origin = path[0]
    path_returns = tuple((value / origin) - 1.0 for value in path)
    return CandidateRealizedOutcome(
        security_id=security_id,
        entry_price=origin,
        exit_price=path[-1],
        realized_basis_return=realized,
        benchmark_excess_return=realized - benchmark_return,
        max_close_favorable_excursion=max(path_returns),
        max_close_adverse_excursion=min(path_returns),
    )


def _basis_return(path: tuple[float, ...]) -> float:
    if len(path) < 2:
        raise ValueError("return path requires at least two prices")
    return (path[-1] / path[0]) - 1.0


def _leader_regret(
    leader: str | None,
    returns: dict[str, float],
    best_return: float,
) -> float | None:
    if leader is None:
        return None
    return max(0.0, best_return - returns[leader])


def _require_aware(value: datetime, field: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field} must be timezone-aware")


def _require_text(value: str, field: str) -> None:
    if not value.strip():
        raise ValueError(f"{field} cannot be empty")


def _require_finite(value: float, field: str) -> None:
    if not math.isfinite(value):
        raise ValueError(f"{field} must be finite")


def _validate_sha(value: str, field: str) -> None:
    if len(value) != 64 or any(char not in "0123456789abcdef" for char in value):
        raise ValueError(f"{field} must be a lowercase SHA-256 hex digest")


def _validate_sha_tuple(values: tuple[str, ...], field: str) -> None:
    if len(set(values)) != len(values):
        raise ValueError(f"{field} must not contain duplicates")
    for value in values:
        _validate_sha(value, field)


def _validate_security_tuple(values: tuple[str, ...], field: str, *, minimum: int) -> None:
    if len(values) < minimum:
        raise ValueError(f"{field} requires at least {minimum} securities")
    if len(set(values)) != len(values):
        raise ValueError(f"{field} must not contain duplicates")
    for value in values:
        _require_text(value, field)


def _validate_text_tuple(values: tuple[str, ...], field: str) -> None:
    if len(set(values)) != len(values):
        raise ValueError(f"{field} must not contain duplicates")
    for value in values:
        _require_text(value, field)


def _sha(payload: dict[str, object]) -> str:
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()
