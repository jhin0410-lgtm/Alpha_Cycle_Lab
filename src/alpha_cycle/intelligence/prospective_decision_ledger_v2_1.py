"""Prospective decision ledger for Alpha Cycle Lab Decision System v2.1.

The ledger aggregates completed, content-addressed prospective opportunity experiments. It
revalidates upstream opportunity/registration/outcome bindings and reports only descriptive
ex-post selection diagnostics. It does not infer causal investment skill or fit a new score.
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
from statistics import mean, median

from alpha_cycle.data.integrity import PriceBasis
from alpha_cycle.intelligence.expectation_gap_opportunity_set_v2_1 import (
    ExpectationAugmentedOpportunitySetSnapshot,
)
from alpha_cycle.intelligence.expectation_state import ExpectationMetric
from alpha_cycle.intelligence.opportunity_set_v2_1 import OpportunitySetSnapshot
from alpha_cycle.intelligence.prospective_opportunity_scorekeeping_v2_1 import (
    ProspectiveOpportunityOutcomeSnapshot,
    ProspectiveOpportunityRegistration,
)

PROSPECTIVE_DECISION_LEDGER_SCHEMA_VERSION = 1
_FLOAT_TOLERANCE = 1e-12


class ObservedDecisionAttribution(StrEnum):
    """Descriptive ex-post labels; none is a causal explanation of investment performance."""

    BASE_FRONTIER_RETAINED_BEST_REGISTERED_CANDIDATE = (
        "base_frontier_retained_best_registered_candidate"
    )
    BASE_FRONTIER_MISSED_BEST_REGISTERED_CANDIDATE = (
        "base_frontier_missed_best_registered_candidate"
    )
    UNIQUE_BASE_LEADER_MATCHED_BEST_REGISTERED_RETURN = (
        "unique_base_leader_matched_best_registered_return"
    )
    UNIQUE_BASE_LEADER_UNDERPERFORMED_BEST_REGISTERED_RETURN = (
        "unique_base_leader_underperformed_best_registered_return"
    )
    EXPECTATION_OVERLAY_NOT_REGISTERED = "expectation_overlay_not_registered"
    EXPECTATION_OVERLAY_IMPROVED_FRONTIER_BEST_RETURN = (
        "expectation_overlay_improved_frontier_best_return"
    )
    EXPECTATION_OVERLAY_DEGRADED_FRONTIER_BEST_RETURN = (
        "expectation_overlay_degraded_frontier_best_return"
    )
    EXPECTATION_OVERLAY_LEFT_FRONTIER_BEST_RETURN_UNCHANGED = (
        "expectation_overlay_left_frontier_best_return_unchanged"
    )
    UNIQUE_EXPECTATION_LEADER_MATCHED_BEST_REGISTERED_RETURN = (
        "unique_expectation_leader_matched_best_registered_return"
    )
    UNIQUE_EXPECTATION_LEADER_UNDERPERFORMED_BEST_REGISTERED_RETURN = (
        "unique_expectation_leader_underperformed_best_registered_return"
    )
    EXPECTATION_COVERAGE_PARTIAL = "expectation_coverage_partial"
    EXPECTATION_COVERAGE_COMPLETE = "expectation_coverage_complete"


@dataclass(frozen=True)
class ProspectiveDecisionLedgerEntry:
    """One completed prospective experiment with validated upstream provenance."""

    registration_id: str
    opportunity_set_snapshot_id: str
    expectation_overlay_snapshot_id: str | None
    registration_snapshot_id: str
    outcome_snapshot_id: str
    registered_at: datetime
    scored_at: datetime
    evaluation_date: date
    entry_session: date
    target_session: date
    horizon_trading_days: int
    price_basis: PriceBasis
    benchmark_security_id: str
    benchmark_return: float
    security_ids: tuple[str, ...]
    base_pareto_frontier_security_ids: tuple[str, ...]
    unique_base_leader_security_id: str | None
    expectation_comparable_security_ids: tuple[str, ...]
    expectation_blocked_security_ids: tuple[str, ...]
    expectation_pareto_frontier_security_ids: tuple[str, ...]
    unique_expectation_leader_security_id: str | None
    expectation_provider_id: str | None
    expectation_metric: ExpectationMetric | None
    expectation_target_date: date | None
    comparison_policy_snapshot_id: str | None
    ex_post_winner_security_ids: tuple[str, ...]
    best_registered_candidate_return: float
    base_frontier_best_return: float
    base_frontier_regret: float
    base_frontier_contains_ex_post_winner: bool
    unique_base_leader_regret: float | None
    expectation_frontier_best_return: float | None
    expectation_frontier_regret: float | None
    expectation_frontier_contains_ex_post_winner: bool | None
    unique_expectation_leader_regret: float | None
    expectation_overlay_incremental_best_return: float | None
    observed_attributions: tuple[ObservedDecisionAttribution, ...]
    flags: tuple[str, ...]

    def __post_init__(self) -> None:
        _require_text(self.registration_id, "registration_id")
        for value, field in (
            (self.opportunity_set_snapshot_id, "opportunity_set_snapshot_id"),
            (self.registration_snapshot_id, "registration_snapshot_id"),
            (self.outcome_snapshot_id, "outcome_snapshot_id"),
        ):
            _validate_sha(value, field)
        if self.expectation_overlay_snapshot_id is not None:
            _validate_sha(
                self.expectation_overlay_snapshot_id,
                "expectation_overlay_snapshot_id",
            )
        if self.comparison_policy_snapshot_id is not None:
            _validate_sha(
                self.comparison_policy_snapshot_id,
                "comparison_policy_snapshot_id",
            )
        _require_aware(self.registered_at, "registered_at")
        _require_aware(self.scored_at, "scored_at")
        if self.scored_at <= self.registered_at:
            raise ValueError("ledger outcome must be scored after registration")
        if self.target_session <= self.entry_session:
            raise ValueError("ledger target_session must follow entry_session")
        if self.horizon_trading_days not in {60, 120, 250}:
            raise ValueError("ledger horizon must be 60, 120, or 250 trading days")
        if not isinstance(self.price_basis, PriceBasis):
            raise ValueError("ledger price_basis must be a PriceBasis")
        _require_text(self.benchmark_security_id, "benchmark_security_id")
        _validate_security_tuple(self.security_ids, "security_ids", minimum=2)
        _validate_security_tuple(
            self.base_pareto_frontier_security_ids,
            "base_pareto_frontier_security_ids",
            minimum=1,
        )
        if not set(self.base_pareto_frontier_security_ids).issubset(self.security_ids):
            raise ValueError("ledger base frontier must be a subset of registered securities")
        _validate_security_tuple(
            self.ex_post_winner_security_ids,
            "ex_post_winner_security_ids",
            minimum=1,
        )
        if not set(self.ex_post_winner_security_ids).issubset(self.security_ids):
            raise ValueError("ledger winners must be registered securities")
        for values, field in (
            (self.expectation_comparable_security_ids, "expectation_comparable_security_ids"),
            (self.expectation_blocked_security_ids, "expectation_blocked_security_ids"),
            (
                self.expectation_pareto_frontier_security_ids,
                "expectation_pareto_frontier_security_ids",
            ),
        ):
            _validate_security_tuple(values, field, minimum=0)
            if not set(values).issubset(self.security_ids):
                raise ValueError(f"{field} must be a subset of registered securities")
        for numeric, field in (
            (self.benchmark_return, "benchmark_return"),
            (self.best_registered_candidate_return, "best_registered_candidate_return"),
            (self.base_frontier_best_return, "base_frontier_best_return"),
            (self.base_frontier_regret, "base_frontier_regret"),
        ):
            _require_finite(numeric, field)
        for numeric, field in (
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
            if numeric is not None:
                _require_finite(numeric, field)
        if self.base_frontier_regret < 0:
            raise ValueError("ledger base frontier regret cannot be negative")
        if self.expectation_frontier_regret is not None:
            if self.expectation_frontier_regret < 0:
                raise ValueError("ledger expectation frontier regret cannot be negative")
        if len(set(self.observed_attributions)) != len(self.observed_attributions):
            raise ValueError("ledger observed attributions must be unique")
        _validate_text_tuple(self.flags, "flags")
        _validate_expectation_entry_shape(self)

    @property
    def snapshot_id(self) -> str:
        return _sha(self.payload_without_id())

    def payload_without_id(self) -> dict[str, object]:
        return {
            "schema_version": PROSPECTIVE_DECISION_LEDGER_SCHEMA_VERSION,
            "registration_id": self.registration_id,
            "opportunity_set_snapshot_id": self.opportunity_set_snapshot_id,
            "expectation_overlay_snapshot_id": self.expectation_overlay_snapshot_id,
            "registration_snapshot_id": self.registration_snapshot_id,
            "outcome_snapshot_id": self.outcome_snapshot_id,
            "registered_at": self.registered_at.isoformat(),
            "scored_at": self.scored_at.isoformat(),
            "evaluation_date": self.evaluation_date.isoformat(),
            "entry_session": self.entry_session.isoformat(),
            "target_session": self.target_session.isoformat(),
            "horizon_trading_days": self.horizon_trading_days,
            "price_basis": self.price_basis.value,
            "benchmark_security_id": self.benchmark_security_id,
            "benchmark_return": self.benchmark_return,
            "security_ids": list(self.security_ids),
            "base_pareto_frontier_security_ids": list(
                self.base_pareto_frontier_security_ids
            ),
            "unique_base_leader_security_id": self.unique_base_leader_security_id,
            "expectation_comparable_security_ids": list(
                self.expectation_comparable_security_ids
            ),
            "expectation_blocked_security_ids": list(
                self.expectation_blocked_security_ids
            ),
            "expectation_pareto_frontier_security_ids": list(
                self.expectation_pareto_frontier_security_ids
            ),
            "unique_expectation_leader_security_id": (
                self.unique_expectation_leader_security_id
            ),
            "expectation_provider_id": self.expectation_provider_id,
            "expectation_metric": (
                self.expectation_metric.value if self.expectation_metric is not None else None
            ),
            "expectation_target_date": (
                self.expectation_target_date.isoformat()
                if self.expectation_target_date is not None
                else None
            ),
            "comparison_policy_snapshot_id": self.comparison_policy_snapshot_id,
            "ex_post_winner_security_ids": list(self.ex_post_winner_security_ids),
            "best_registered_candidate_return": self.best_registered_candidate_return,
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
            "observed_attributions": [item.value for item in self.observed_attributions],
            "flags": list(self.flags),
            "causal_skill_inference_enabled": False,
            "weighted_score_training_enabled": False,
            "portfolio_recommendation_enabled": False,
            "automatic_execution_enabled": False,
        }


@dataclass(frozen=True)
class ProspectiveDecisionCohortSummary:
    """Descriptive summary for one horizon and adjusted-price basis cohort."""

    horizon_trading_days: int
    price_basis: PriceBasis
    observation_count: int
    base_frontier_contains_winner_count: int
    base_frontier_contains_winner_rate: float
    mean_base_frontier_regret: float
    median_base_frontier_regret: float
    unique_base_leader_observation_count: int
    unique_base_leader_matched_best_count: int
    unique_base_leader_matched_best_rate: float | None
    expectation_overlay_observation_count: int
    expectation_complete_coverage_count: int
    expectation_partial_coverage_count: int
    expectation_frontier_contains_winner_count: int
    expectation_frontier_contains_winner_rate: float | None
    mean_expectation_frontier_regret: float | None
    median_expectation_frontier_regret: float | None
    expectation_overlay_improved_count: int
    expectation_overlay_degraded_count: int
    expectation_overlay_unchanged_count: int
    mean_expectation_overlay_incremental_best_return: float | None
    median_expectation_overlay_incremental_best_return: float | None

    def __post_init__(self) -> None:
        if self.horizon_trading_days not in {60, 120, 250}:
            raise ValueError("ledger cohort horizon must be 60, 120, or 250")
        if not isinstance(self.price_basis, PriceBasis):
            raise ValueError("ledger cohort price_basis must be a PriceBasis")
        if self.observation_count < 1:
            raise ValueError("ledger cohort requires at least one observation")
        for value, field in (
            (self.base_frontier_contains_winner_count, "base_frontier_contains_winner_count"),
            (self.unique_base_leader_observation_count, "unique_base_leader_observation_count"),
            (self.unique_base_leader_matched_best_count, "unique_base_leader_matched_best_count"),
            (self.expectation_overlay_observation_count, "expectation_overlay_observation_count"),
            (self.expectation_complete_coverage_count, "expectation_complete_coverage_count"),
            (self.expectation_partial_coverage_count, "expectation_partial_coverage_count"),
            (
                self.expectation_frontier_contains_winner_count,
                "expectation_frontier_contains_winner_count",
            ),
            (self.expectation_overlay_improved_count, "expectation_overlay_improved_count"),
            (self.expectation_overlay_degraded_count, "expectation_overlay_degraded_count"),
            (self.expectation_overlay_unchanged_count, "expectation_overlay_unchanged_count"),
        ):
            if value < 0 or value > self.observation_count:
                raise ValueError(f"{field} is outside cohort bounds")
        for value, field in (
            (self.base_frontier_contains_winner_rate, "base_frontier_contains_winner_rate"),
            (self.mean_base_frontier_regret, "mean_base_frontier_regret"),
            (self.median_base_frontier_regret, "median_base_frontier_regret"),
        ):
            _require_finite(value, field)
        for value, field in (
            (self.unique_base_leader_matched_best_rate, "unique_base_leader_matched_best_rate"),
            (
                self.expectation_frontier_contains_winner_rate,
                "expectation_frontier_contains_winner_rate",
            ),
            (self.mean_expectation_frontier_regret, "mean_expectation_frontier_regret"),
            (self.median_expectation_frontier_regret, "median_expectation_frontier_regret"),
            (
                self.mean_expectation_overlay_incremental_best_return,
                "mean_expectation_overlay_incremental_best_return",
            ),
            (
                self.median_expectation_overlay_incremental_best_return,
                "median_expectation_overlay_incremental_best_return",
            ),
        ):
            if value is not None:
                _require_finite(value, field)
        for rate in (
            self.base_frontier_contains_winner_rate,
            self.unique_base_leader_matched_best_rate,
            self.expectation_frontier_contains_winner_rate,
        ):
            if rate is not None and not 0 <= rate <= 1:
                raise ValueError("ledger cohort rates must be between zero and one")

    def payload(self) -> dict[str, object]:
        return {
            "horizon_trading_days": self.horizon_trading_days,
            "price_basis": self.price_basis.value,
            "observation_count": self.observation_count,
            "base_frontier_contains_winner_count": self.base_frontier_contains_winner_count,
            "base_frontier_contains_winner_rate": self.base_frontier_contains_winner_rate,
            "mean_base_frontier_regret": self.mean_base_frontier_regret,
            "median_base_frontier_regret": self.median_base_frontier_regret,
            "unique_base_leader_observation_count": self.unique_base_leader_observation_count,
            "unique_base_leader_matched_best_count": self.unique_base_leader_matched_best_count,
            "unique_base_leader_matched_best_rate": self.unique_base_leader_matched_best_rate,
            "expectation_overlay_observation_count": self.expectation_overlay_observation_count,
            "expectation_complete_coverage_count": self.expectation_complete_coverage_count,
            "expectation_partial_coverage_count": self.expectation_partial_coverage_count,
            "expectation_frontier_contains_winner_count": (
                self.expectation_frontier_contains_winner_count
            ),
            "expectation_frontier_contains_winner_rate": (
                self.expectation_frontier_contains_winner_rate
            ),
            "mean_expectation_frontier_regret": self.mean_expectation_frontier_regret,
            "median_expectation_frontier_regret": self.median_expectation_frontier_regret,
            "expectation_overlay_improved_count": self.expectation_overlay_improved_count,
            "expectation_overlay_degraded_count": self.expectation_overlay_degraded_count,
            "expectation_overlay_unchanged_count": self.expectation_overlay_unchanged_count,
            "mean_expectation_overlay_incremental_best_return": (
                self.mean_expectation_overlay_incremental_best_return
            ),
            "median_expectation_overlay_incremental_best_return": (
                self.median_expectation_overlay_incremental_best_return
            ),
        }


@dataclass(frozen=True)
class ProspectiveDecisionLedgerSnapshot:
    """Content-addressed collection of completed prospective decision observations."""

    built_at: datetime
    entries: tuple[ProspectiveDecisionLedgerEntry, ...]
    cohort_summaries: tuple[ProspectiveDecisionCohortSummary, ...]
    flags: tuple[str, ...]

    def __post_init__(self) -> None:
        _require_aware(self.built_at, "built_at")
        if not self.entries:
            raise ValueError("prospective decision ledger requires at least one entry")
        registration_ids = tuple(item.registration_id for item in self.entries)
        if len(set(registration_ids)) != len(registration_ids):
            raise ValueError("ledger registration ids must be unique")
        registration_snapshots = tuple(item.registration_snapshot_id for item in self.entries)
        if len(set(registration_snapshots)) != len(registration_snapshots):
            raise ValueError("ledger registration snapshots must be unique")
        outcome_snapshots = tuple(item.outcome_snapshot_id for item in self.entries)
        if len(set(outcome_snapshots)) != len(outcome_snapshots):
            raise ValueError("ledger outcome snapshots must be unique")
        if any(item.scored_at > self.built_at for item in self.entries):
            raise ValueError("ledger cannot be built before an included outcome was scored")
        summary_keys = tuple(
            (item.horizon_trading_days, item.price_basis) for item in self.cohort_summaries
        )
        if len(set(summary_keys)) != len(summary_keys):
            raise ValueError("ledger cohort summary keys must be unique")
        expected_keys = {
            (item.horizon_trading_days, item.price_basis) for item in self.entries
        }
        if set(summary_keys) != expected_keys:
            raise ValueError("ledger cohort summaries do not cover the entry cohorts exactly")
        _validate_text_tuple(self.flags, "flags")

    @property
    def snapshot_id(self) -> str:
        return _sha(self.payload_without_id())

    def payload_without_id(self) -> dict[str, object]:
        ordered_entries = sorted(
            self.entries,
            key=lambda item: (
                item.evaluation_date,
                item.horizon_trading_days,
                item.registration_id,
            ),
        )
        ordered_summaries = sorted(
            self.cohort_summaries,
            key=lambda item: (item.horizon_trading_days, item.price_basis.value),
        )
        return {
            "schema_version": PROSPECTIVE_DECISION_LEDGER_SCHEMA_VERSION,
            "built_at": self.built_at.isoformat(),
            "entries": [item.payload_without_id() for item in ordered_entries],
            "cohort_summaries": [item.payload() for item in ordered_summaries],
            "flags": list(self.flags),
            "descriptive_statistics_only": True,
            "causal_skill_inference_enabled": False,
            "weighted_score_training_enabled": False,
            "probability_estimation_enabled": False,
            "portfolio_optimization_enabled": False,
            "automatic_execution_enabled": False,
        }


def build_prospective_decision_ledger_entry(
    opportunity_set: OpportunitySetSnapshot,
    registration: ProspectiveOpportunityRegistration,
    outcome: ProspectiveOpportunityOutcomeSnapshot,
    *,
    expectation_overlay: ExpectationAugmentedOpportunitySetSnapshot | None = None,
) -> ProspectiveDecisionLedgerEntry:
    """Revalidate one completed experiment and convert it into a ledger observation."""

    _validate_upstream_binding(
        opportunity_set,
        registration,
        outcome,
        expectation_overlay=expectation_overlay,
    )
    returns = {item.security_id: item.realized_basis_return for item in outcome.candidate_outcomes}
    best_return = max(returns.values())
    _validate_outcome_metrics(registration, outcome, returns, best_return)

    expectation_comparable: tuple[str, ...] = ()
    expectation_blocked: tuple[str, ...] = ()
    provider: str | None = None
    metric: ExpectationMetric | None = None
    target_date: date | None = None
    policy_snapshot_id: str | None = None
    if expectation_overlay is not None:
        expectation_comparable = tuple(
            sorted(expectation_overlay.expectation_comparable_security_ids)
        )
        expectation_blocked = tuple(
            sorted(expectation_overlay.expectation_blocked_security_ids)
        )
        first = expectation_overlay.candidates[0]
        provider = first.consensus_provider_id
        metric = first.metric
        target_date = first.target_date
        policy_snapshot_id = expectation_overlay.comparison_policy_snapshot_id
        for candidate in expectation_overlay.candidates:
            if candidate.consensus_provider_id != provider:
                raise ValueError("ledger expectation overlay contains mixed providers")
            if candidate.metric is not metric:
                raise ValueError("ledger expectation overlay contains mixed metrics")
            if candidate.target_date != target_date:
                raise ValueError("ledger expectation overlay contains mixed target dates")
            if candidate.comparison_policy_snapshot_id != policy_snapshot_id:
                raise ValueError("ledger expectation overlay contains mixed comparison policies")

    attributions = _observed_attributions(
        registration,
        outcome,
        expectation_overlay=expectation_overlay,
    )
    flags = tuple(dict.fromkeys(outcome.flags))
    return ProspectiveDecisionLedgerEntry(
        registration_id=registration.registration_id,
        opportunity_set_snapshot_id=opportunity_set.snapshot_id,
        expectation_overlay_snapshot_id=(
            expectation_overlay.snapshot_id if expectation_overlay is not None else None
        ),
        registration_snapshot_id=registration.snapshot_id,
        outcome_snapshot_id=outcome.snapshot_id,
        registered_at=registration.registered_at,
        scored_at=outcome.scored_at,
        evaluation_date=registration.evaluation_date,
        entry_session=registration.entry_session,
        target_session=outcome.target_session,
        horizon_trading_days=registration.horizon_trading_days,
        price_basis=registration.price_basis,
        benchmark_security_id=registration.benchmark_security_id,
        benchmark_return=outcome.benchmark_return,
        security_ids=registration.security_ids,
        base_pareto_frontier_security_ids=registration.base_pareto_frontier_security_ids,
        unique_base_leader_security_id=registration.unique_base_leader_security_id,
        expectation_comparable_security_ids=expectation_comparable,
        expectation_blocked_security_ids=expectation_blocked,
        expectation_pareto_frontier_security_ids=(
            registration.expectation_pareto_frontier_security_ids
        ),
        unique_expectation_leader_security_id=(
            registration.unique_expectation_leader_security_id
        ),
        expectation_provider_id=provider,
        expectation_metric=metric,
        expectation_target_date=target_date,
        comparison_policy_snapshot_id=policy_snapshot_id,
        ex_post_winner_security_ids=outcome.ex_post_winner_security_ids,
        best_registered_candidate_return=best_return,
        base_frontier_best_return=outcome.base_frontier_best_return,
        base_frontier_regret=outcome.base_frontier_regret,
        base_frontier_contains_ex_post_winner=(
            outcome.base_frontier_contains_ex_post_winner
        ),
        unique_base_leader_regret=outcome.unique_base_leader_regret,
        expectation_frontier_best_return=outcome.expectation_frontier_best_return,
        expectation_frontier_regret=outcome.expectation_frontier_regret,
        expectation_frontier_contains_ex_post_winner=(
            outcome.expectation_frontier_contains_ex_post_winner
        ),
        unique_expectation_leader_regret=outcome.unique_expectation_leader_regret,
        expectation_overlay_incremental_best_return=(
            outcome.expectation_overlay_incremental_best_return
        ),
        observed_attributions=attributions,
        flags=flags,
    )


def build_prospective_decision_ledger(
    entries: tuple[ProspectiveDecisionLedgerEntry, ...],
    *,
    built_at: datetime,
) -> ProspectiveDecisionLedgerSnapshot:
    """Build descriptive cohort summaries without fitting or calibrating a ranking score."""

    _require_aware(built_at, "built_at")
    if not entries:
        raise ValueError("prospective decision ledger requires at least one entry")
    groups: dict[tuple[int, PriceBasis], list[ProspectiveDecisionLedgerEntry]] = {}
    for entry in entries:
        groups.setdefault((entry.horizon_trading_days, entry.price_basis), []).append(entry)
    summaries = tuple(
        _cohort_summary(horizon, basis, tuple(group))
        for (horizon, basis), group in sorted(
            groups.items(), key=lambda item: (item[0][0], item[0][1].value)
        )
    )
    return ProspectiveDecisionLedgerSnapshot(
        built_at=built_at,
        entries=entries,
        cohort_summaries=summaries,
        flags=(
            "descriptive_only_no_causal_skill_inference",
            "no_weighted_score_refit_from_prospective_ledger",
        ),
    )


def persist_prospective_decision_ledger(
    snapshot: ProspectiveDecisionLedgerSnapshot,
    path: Path,
) -> None:
    """Persist a ledger snapshot atomically without overwriting prior evidence."""

    if path.exists():
        raise FileExistsError(f"prospective decision ledger already exists: {path}")
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


def _validate_upstream_binding(
    opportunity_set: OpportunitySetSnapshot,
    registration: ProspectiveOpportunityRegistration,
    outcome: ProspectiveOpportunityOutcomeSnapshot,
    *,
    expectation_overlay: ExpectationAugmentedOpportunitySetSnapshot | None,
) -> None:
    if registration.opportunity_set_snapshot_id != opportunity_set.snapshot_id:
        raise ValueError("ledger registration is bound to a different opportunity set")
    derived_comparable = tuple(
        sorted(
            item.security_id
            for item in opportunity_set.candidates
            if item.capital_allocation_comparable
        )
    )
    if tuple(sorted(opportunity_set.comparable_security_ids)) != derived_comparable:
        raise ValueError("ledger base opportunity comparable-security registry has drifted")
    if registration.security_ids != derived_comparable:
        raise ValueError("ledger registration candidate universe differs from base opportunity set")
    if set(registration.base_pareto_frontier_security_ids) != set(
        opportunity_set.pareto_frontier_security_ids
    ):
        raise ValueError("ledger registration base frontier differs from opportunity set")
    if (
        registration.unique_base_leader_security_id
        != opportunity_set.unique_pareto_leader_security_id
    ):
        raise ValueError("ledger registration base leader differs from opportunity set")
    if registration.evaluation_date != opportunity_set.evaluation_date:
        raise ValueError("ledger registration evaluation_date differs from opportunity set")
    if registration.horizon_trading_days != opportunity_set.horizon_trading_days:
        raise ValueError("ledger registration horizon differs from opportunity set")
    if registration.guardrail_evidence_id != opportunity_set.guardrail_evidence_id:
        raise ValueError("ledger registration guardrail evidence differs from opportunity set")

    if outcome.registration_snapshot_id != registration.snapshot_id:
        raise ValueError("ledger outcome is bound to a different registration")
    if outcome.entry_session != registration.entry_session:
        raise ValueError("ledger outcome entry session differs from registration")
    if outcome.horizon_trading_days != registration.horizon_trading_days:
        raise ValueError("ledger outcome horizon differs from registration")
    if outcome.price_basis != registration.price_basis:
        raise ValueError("ledger outcome price basis differs from registration")
    if outcome.benchmark_security_id != registration.benchmark_security_id:
        raise ValueError("ledger outcome benchmark differs from registration")
    outcome_ids = tuple(item.security_id for item in outcome.candidate_outcomes)
    if outcome_ids != registration.security_ids:
        raise ValueError("ledger outcome candidate universe differs from registration")
    for candidate in outcome.candidate_outcomes:
        expected_excess = candidate.realized_basis_return - outcome.benchmark_return
        _assert_close(
            candidate.benchmark_excess_return,
            expected_excess,
            "candidate benchmark excess return",
        )

    if registration.expectation_overlay_snapshot_id is None:
        if expectation_overlay is not None:
            raise ValueError("ledger received an expectation overlay for a base-only registration")
        return
    if expectation_overlay is None:
        raise ValueError("ledger requires the registered expectation overlay snapshot")
    if expectation_overlay.snapshot_id != registration.expectation_overlay_snapshot_id:
        raise ValueError("ledger expectation overlay differs from registration")
    if expectation_overlay.base_opportunity_set_snapshot_id != opportunity_set.snapshot_id:
        raise ValueError("ledger expectation overlay is bound to a different opportunity set")
    if expectation_overlay.evaluation_date != registration.evaluation_date:
        raise ValueError("ledger expectation overlay evaluation_date differs from registration")
    if expectation_overlay.horizon_trading_days != registration.horizon_trading_days:
        raise ValueError("ledger expectation overlay horizon differs from registration")
    if expectation_overlay.guardrail_evidence_id != registration.guardrail_evidence_id:
        raise ValueError("ledger expectation overlay guardrail evidence differs from registration")
    overlay_ids = tuple(sorted(item.security_id for item in expectation_overlay.candidates))
    if overlay_ids != registration.security_ids:
        raise ValueError("ledger expectation overlay candidate universe differs from registration")
    derived_expectation_comparable = tuple(
        sorted(
            item.security_id
            for item in expectation_overlay.candidates
            if item.expectation_gap_comparable
        )
    )
    if tuple(sorted(expectation_overlay.expectation_comparable_security_ids)) != (
        derived_expectation_comparable
    ):
        raise ValueError("ledger expectation comparable-security registry has drifted")
    if set(registration.expectation_pareto_frontier_security_ids) != set(
        expectation_overlay.expectation_pareto_frontier_security_ids
    ):
        raise ValueError("ledger expectation frontier differs from registration")
    if (
        registration.unique_expectation_leader_security_id
        != expectation_overlay.unique_expectation_pareto_leader_security_id
    ):
        raise ValueError("ledger expectation leader differs from registration")


def _validate_outcome_metrics(
    registration: ProspectiveOpportunityRegistration,
    outcome: ProspectiveOpportunityOutcomeSnapshot,
    returns: dict[str, float],
    best_return: float,
) -> None:
    derived_winners = tuple(
        security_id
        for security_id in registration.security_ids
        if math.isclose(
            returns[security_id],
            best_return,
            rel_tol=0.0,
            abs_tol=_FLOAT_TOLERANCE,
        )
    )
    if outcome.ex_post_winner_security_ids != derived_winners:
        raise ValueError("ledger outcome ex-post winner registry has drifted")

    base_best = max(
        returns[item] for item in registration.base_pareto_frontier_security_ids
    )
    base_regret = max(0.0, best_return - base_best)
    _assert_close(outcome.base_frontier_best_return, base_best, "base frontier best return")
    _assert_close(outcome.base_frontier_regret, base_regret, "base frontier regret")
    base_contains = bool(
        set(derived_winners).intersection(registration.base_pareto_frontier_security_ids)
    )
    if outcome.base_frontier_contains_ex_post_winner is not base_contains:
        raise ValueError("ledger outcome base frontier containment has drifted")
    expected_base_leader_regret = _leader_regret(
        registration.unique_base_leader_security_id,
        returns,
        best_return,
    )
    _assert_optional_close(
        outcome.unique_base_leader_regret,
        expected_base_leader_regret,
        "unique base leader regret",
    )

    if registration.expectation_overlay_snapshot_id is None:
        for value in (
            outcome.expectation_frontier_best_return,
            outcome.expectation_frontier_regret,
            outcome.expectation_frontier_contains_ex_post_winner,
            outcome.unique_expectation_leader_regret,
            outcome.expectation_overlay_incremental_best_return,
        ):
            if value is not None:
                raise ValueError("base-only ledger outcome contains expectation metrics")
        return

    expectation_best = max(
        returns[item] for item in registration.expectation_pareto_frontier_security_ids
    )
    expectation_regret = max(0.0, best_return - expectation_best)
    _assert_optional_close(
        outcome.expectation_frontier_best_return,
        expectation_best,
        "expectation frontier best return",
    )
    _assert_optional_close(
        outcome.expectation_frontier_regret,
        expectation_regret,
        "expectation frontier regret",
    )
    expectation_contains = bool(
        set(derived_winners).intersection(
            registration.expectation_pareto_frontier_security_ids
        )
    )
    if outcome.expectation_frontier_contains_ex_post_winner is not expectation_contains:
        raise ValueError("ledger outcome expectation frontier containment has drifted")
    expected_expectation_leader_regret = _leader_regret(
        registration.unique_expectation_leader_security_id,
        returns,
        best_return,
    )
    _assert_optional_close(
        outcome.unique_expectation_leader_regret,
        expected_expectation_leader_regret,
        "unique expectation leader regret",
    )
    incremental = expectation_best - base_best
    _assert_optional_close(
        outcome.expectation_overlay_incremental_best_return,
        incremental,
        "expectation overlay incremental best return",
    )


def _observed_attributions(
    registration: ProspectiveOpportunityRegistration,
    outcome: ProspectiveOpportunityOutcomeSnapshot,
    *,
    expectation_overlay: ExpectationAugmentedOpportunitySetSnapshot | None,
) -> tuple[ObservedDecisionAttribution, ...]:
    labels: list[ObservedDecisionAttribution] = []
    if outcome.base_frontier_regret > _FLOAT_TOLERANCE:
        labels.append(
            ObservedDecisionAttribution.BASE_FRONTIER_MISSED_BEST_REGISTERED_CANDIDATE
        )
    else:
        labels.append(
            ObservedDecisionAttribution.BASE_FRONTIER_RETAINED_BEST_REGISTERED_CANDIDATE
        )
    if registration.unique_base_leader_security_id is not None:
        if (outcome.unique_base_leader_regret or 0.0) > _FLOAT_TOLERANCE:
            labels.append(
                ObservedDecisionAttribution.UNIQUE_BASE_LEADER_UNDERPERFORMED_BEST_REGISTERED_RETURN
            )
        else:
            labels.append(
                ObservedDecisionAttribution.UNIQUE_BASE_LEADER_MATCHED_BEST_REGISTERED_RETURN
            )

    if expectation_overlay is None:
        labels.append(ObservedDecisionAttribution.EXPECTATION_OVERLAY_NOT_REGISTERED)
        return tuple(labels)

    if expectation_overlay.expectation_blocked_security_ids:
        labels.append(ObservedDecisionAttribution.EXPECTATION_COVERAGE_PARTIAL)
    else:
        labels.append(ObservedDecisionAttribution.EXPECTATION_COVERAGE_COMPLETE)
    incremental = outcome.expectation_overlay_incremental_best_return
    if incremental is None:
        raise ValueError("registered expectation overlay requires an incremental return metric")
    if incremental > _FLOAT_TOLERANCE:
        labels.append(
            ObservedDecisionAttribution.EXPECTATION_OVERLAY_IMPROVED_FRONTIER_BEST_RETURN
        )
    elif incremental < -_FLOAT_TOLERANCE:
        labels.append(
            ObservedDecisionAttribution.EXPECTATION_OVERLAY_DEGRADED_FRONTIER_BEST_RETURN
        )
    else:
        labels.append(
            ObservedDecisionAttribution.EXPECTATION_OVERLAY_LEFT_FRONTIER_BEST_RETURN_UNCHANGED
        )
    if registration.unique_expectation_leader_security_id is not None:
        if (outcome.unique_expectation_leader_regret or 0.0) > _FLOAT_TOLERANCE:
            labels.append(
                ObservedDecisionAttribution.UNIQUE_EXPECTATION_LEADER_UNDERPERFORMED_BEST_REGISTERED_RETURN
            )
        else:
            labels.append(
                ObservedDecisionAttribution.UNIQUE_EXPECTATION_LEADER_MATCHED_BEST_REGISTERED_RETURN
            )
    return tuple(labels)


def _cohort_summary(
    horizon: int,
    basis: PriceBasis,
    entries: tuple[ProspectiveDecisionLedgerEntry, ...],
) -> ProspectiveDecisionCohortSummary:
    base_regrets = [item.base_frontier_regret for item in entries]
    base_contains_count = sum(item.base_frontier_contains_ex_post_winner for item in entries)
    base_leaders = [item for item in entries if item.unique_base_leader_security_id is not None]
    base_leader_matches = sum(
        (item.unique_base_leader_regret or 0.0) <= _FLOAT_TOLERANCE
        for item in base_leaders
    )

    expectation_entries = [
        item for item in entries if item.expectation_overlay_snapshot_id is not None
    ]
    expectation_regrets = [
        item.expectation_frontier_regret
        for item in expectation_entries
        if item.expectation_frontier_regret is not None
    ]
    incrementals = [
        item.expectation_overlay_incremental_best_return
        for item in expectation_entries
        if item.expectation_overlay_incremental_best_return is not None
    ]
    expectation_contains_count = sum(
        item.expectation_frontier_contains_ex_post_winner is True
        for item in expectation_entries
    )
    complete_coverage = sum(
        not item.expectation_blocked_security_ids for item in expectation_entries
    )
    partial_coverage = len(expectation_entries) - complete_coverage
    improved = sum(item > _FLOAT_TOLERANCE for item in incrementals)
    degraded = sum(item < -_FLOAT_TOLERANCE for item in incrementals)
    unchanged = len(incrementals) - improved - degraded

    return ProspectiveDecisionCohortSummary(
        horizon_trading_days=horizon,
        price_basis=basis,
        observation_count=len(entries),
        base_frontier_contains_winner_count=base_contains_count,
        base_frontier_contains_winner_rate=base_contains_count / len(entries),
        mean_base_frontier_regret=mean(base_regrets),
        median_base_frontier_regret=median(base_regrets),
        unique_base_leader_observation_count=len(base_leaders),
        unique_base_leader_matched_best_count=base_leader_matches,
        unique_base_leader_matched_best_rate=(
            base_leader_matches / len(base_leaders) if base_leaders else None
        ),
        expectation_overlay_observation_count=len(expectation_entries),
        expectation_complete_coverage_count=complete_coverage,
        expectation_partial_coverage_count=partial_coverage,
        expectation_frontier_contains_winner_count=expectation_contains_count,
        expectation_frontier_contains_winner_rate=(
            expectation_contains_count / len(expectation_entries)
            if expectation_entries
            else None
        ),
        mean_expectation_frontier_regret=(
            mean(expectation_regrets) if expectation_regrets else None
        ),
        median_expectation_frontier_regret=(
            median(expectation_regrets) if expectation_regrets else None
        ),
        expectation_overlay_improved_count=improved,
        expectation_overlay_degraded_count=degraded,
        expectation_overlay_unchanged_count=unchanged,
        mean_expectation_overlay_incremental_best_return=(
            mean(incrementals) if incrementals else None
        ),
        median_expectation_overlay_incremental_best_return=(
            median(incrementals) if incrementals else None
        ),
    )


def _validate_expectation_entry_shape(entry: ProspectiveDecisionLedgerEntry) -> None:
    overlay_fields = (
        entry.expectation_provider_id,
        entry.expectation_metric,
        entry.expectation_target_date,
        entry.comparison_policy_snapshot_id,
        entry.expectation_frontier_best_return,
        entry.expectation_frontier_regret,
        entry.expectation_frontier_contains_ex_post_winner,
        entry.expectation_overlay_incremental_best_return,
    )
    if entry.expectation_overlay_snapshot_id is None:
        if entry.expectation_comparable_security_ids:
            raise ValueError("base-only ledger entry cannot contain expectation comparables")
        if entry.expectation_blocked_security_ids:
            raise ValueError("base-only ledger entry cannot contain expectation blockers")
        if entry.expectation_pareto_frontier_security_ids:
            raise ValueError("base-only ledger entry cannot contain expectation frontier")
        if entry.unique_expectation_leader_security_id is not None:
            raise ValueError("base-only ledger entry cannot contain expectation leader")
        if any(value is not None for value in overlay_fields):
            raise ValueError("base-only ledger entry cannot contain expectation metrics")
        return
    if any(value is None for value in overlay_fields):
        raise ValueError("expectation ledger entry is missing registered overlay metadata")
    if len(entry.expectation_comparable_security_ids) < 2:
        raise ValueError("expectation ledger entry requires at least two comparable securities")
    if not set(entry.expectation_pareto_frontier_security_ids).issubset(
        entry.expectation_comparable_security_ids
    ):
        raise ValueError("expectation ledger frontier must be expectation-comparable")


def _leader_regret(
    leader: str | None,
    returns: dict[str, float],
    best_return: float,
) -> float | None:
    if leader is None:
        return None
    return max(0.0, best_return - returns[leader])


def _assert_close(actual: float, expected: float, field: str) -> None:
    if not math.isclose(actual, expected, rel_tol=0.0, abs_tol=_FLOAT_TOLERANCE):
        raise ValueError(f"ledger outcome {field} has drifted")


def _assert_optional_close(
    actual: float | None,
    expected: float | None,
    field: str,
) -> None:
    if actual is None or expected is None:
        if actual is not expected:
            raise ValueError(f"ledger outcome {field} optionality has drifted")
        return
    _assert_close(actual, expected, field)


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
