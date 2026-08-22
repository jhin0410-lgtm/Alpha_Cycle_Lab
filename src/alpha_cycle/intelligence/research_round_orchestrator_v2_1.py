"""Point-in-time research-round orchestration for Decision System v2.1.

This module is an integration spine over existing typed research contracts. It never invents
missing evidence, mutates a thesis, chooses a target price, sizes a position, or executes a trade.
Missing or incompatible inputs become structured blockers so research fails closed.
"""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from datetime import date, datetime
from enum import StrEnum
from pathlib import Path

from alpha_cycle.calendar.base import TradingCalendar
from alpha_cycle.data.integrity import PriceBasis
from alpha_cycle.intelligence.decision_guardrails_v2_1 import (
    DecisionSystemV21Guardrails,
    load_decision_system_v21_guardrails,
)
from alpha_cycle.intelligence.decision_thesis_v2 import InvestmentThesisSnapshot
from alpha_cycle.intelligence.decision_view_v2_1 import (
    DecisionExpectationGapSnapshot,
    DecisionViewSnapshot,
)
from alpha_cycle.intelligence.expectation_gap_opportunity_set_v2_1 import (
    ExpectationAugmentedOpportunitySetSnapshot,
    ExpectationGapComparisonPolicySnapshot,
    build_expectation_augmented_opportunity_set,
    build_expectation_gap_opportunity_candidate,
)
from alpha_cycle.intelligence.opportunity_set_v2_1 import (
    OpportunityCandidateSnapshot,
    OpportunitySetSnapshot,
    build_opportunity_candidate,
    build_opportunity_set,
)
from alpha_cycle.intelligence.payoff_surface import PayoffSurfaceSnapshot
from alpha_cycle.intelligence.prospective_opportunity_scorekeeping_v2_1 import (
    ProspectiveOpportunityRegistration,
)
from alpha_cycle.intelligence.prospective_scorekeeping_registration_binding_v2_1 import (
    register_prospective_opportunity_set,
)
from alpha_cycle.intelligence.underwriter_v2_1 import UnderwritingReadinessSnapshot

RESEARCH_ROUND_ORCHESTRATOR_SCHEMA_VERSION = 1
_SUPPORTED_HORIZONS = frozenset({60, 120, 250})


class ResearchRoundMode(StrEnum):
    PROSPECTIVE = "prospective"
    REPLAY = "replay"


class ResearchRoundStatus(StrEnum):
    PROSPECTIVE_BLOCKED = "prospective_blocked"
    PROSPECTIVE_READY_FOR_REGISTRATION = "prospective_ready_for_registration"
    PROSPECTIVE_REGISTERED = "prospective_registered"
    REPLAY_BLOCKED = "replay_blocked"
    REPLAY_READY = "replay_ready"


@dataclass(frozen=True)
class ResearchRoundBlocker:
    """One fail-closed reason that prevents the round from advancing."""

    component: str
    code: str
    detail: str
    security_id: str | None = None
    snapshot_id: str | None = None

    def __post_init__(self) -> None:
        _require_text(self.component, "blocker component")
        _require_text(self.code, "blocker code")
        _require_text(self.detail, "blocker detail")
        if self.security_id is not None:
            _require_text(self.security_id, "blocker security_id")
        if self.snapshot_id is not None:
            _validate_sha(self.snapshot_id, "blocker snapshot_id")

    def payload(self) -> dict[str, object]:
        return {
            "component": self.component,
            "code": self.code,
            "detail": self.detail,
            "security_id": self.security_id,
            "snapshot_id": self.snapshot_id,
        }


@dataclass(frozen=True)
class ResearchSecurityPackage:
    """Typed source package for one security in a cross-sectional research round."""

    thesis: InvestmentThesisSnapshot
    underwriting: UnderwritingReadinessSnapshot | None = None
    payoff_surface: PayoffSurfaceSnapshot | None = None
    decision_view: DecisionViewSnapshot | None = None
    expectation_gap: DecisionExpectationGapSnapshot | None = None

    @property
    def security_id(self) -> str:
        return self.thesis.security_id


@dataclass(frozen=True)
class ProspectiveRegistrationRequest:
    """External scorekeeping inputs not derivable from research snapshots."""

    registration_id: str
    registered_at: datetime
    benchmark_security_id: str
    price_basis: PriceBasis
    source_evidence_ids: tuple[str, ...]
    calendar: TradingCalendar

    def __post_init__(self) -> None:
        _require_text(self.registration_id, "registration_id")
        _require_aware(self.registered_at, "registered_at")
        _require_text(self.benchmark_security_id, "benchmark_security_id")
        if not isinstance(self.price_basis, PriceBasis):
            raise ValueError("price_basis must be a PriceBasis")
        if self.price_basis is PriceBasis.RAW:
            raise ValueError("prospective registration requires an adjusted price basis")
        _validate_sha_tuple(self.source_evidence_ids, "source_evidence_ids")
        if not self.source_evidence_ids:
            raise ValueError("prospective registration requires source evidence")


@dataclass(frozen=True)
class ResearchRoundSnapshot:
    """Immutable integration result for one same-date/same-horizon research round."""

    round_id: str
    mode: ResearchRoundMode
    status: ResearchRoundStatus
    captured_at: datetime
    evaluation_date: date
    horizon_trading_days: int
    security_ids: tuple[str, ...]
    thesis_snapshot_ids: tuple[str, ...]
    underwriting_snapshot_ids: tuple[str, ...]
    payoff_surface_snapshot_ids: tuple[str, ...]
    decision_view_snapshot_ids: tuple[str, ...]
    expectation_gap_snapshot_ids: tuple[str, ...]
    opportunity_candidate_snapshot_ids: tuple[str, ...]
    opportunity_set_snapshot_id: str | None
    expectation_overlay_snapshot_id: str | None
    prospective_registration_snapshot_id: str | None
    comparable_security_ids: tuple[str, ...]
    base_pareto_frontier_security_ids: tuple[str, ...]
    expectation_pareto_frontier_security_ids: tuple[str, ...]
    blockers: tuple[ResearchRoundBlocker, ...]
    flags: tuple[str, ...]
    guardrail_evidence_id: str

    def __post_init__(self) -> None:
        _require_text(self.round_id, "round_id")
        _require_aware(self.captured_at, "captured_at")
        if self.horizon_trading_days not in _SUPPORTED_HORIZONS:
            raise ValueError("research round horizon must be 60, 120, or 250 trading days")
        _validate_text_tuple(self.security_ids, "security_ids")
        if len(self.security_ids) < 2:
            raise ValueError("cross-sectional research round requires at least two securities")
        if len(set(self.security_ids)) != len(self.security_ids):
            raise ValueError("research round security ids must be unique")
        for values, field in (
            (self.thesis_snapshot_ids, "thesis_snapshot_ids"),
            (self.underwriting_snapshot_ids, "underwriting_snapshot_ids"),
            (self.payoff_surface_snapshot_ids, "payoff_surface_snapshot_ids"),
            (self.decision_view_snapshot_ids, "decision_view_snapshot_ids"),
            (self.expectation_gap_snapshot_ids, "expectation_gap_snapshot_ids"),
            (
                self.opportunity_candidate_snapshot_ids,
                "opportunity_candidate_snapshot_ids",
            ),
        ):
            _validate_sha_tuple(values, field)
        if len(self.thesis_snapshot_ids) != len(self.security_ids):
            raise ValueError("every research-round security requires one thesis snapshot")
        for value, field in (
            (self.opportunity_set_snapshot_id, "opportunity_set_snapshot_id"),
            (self.expectation_overlay_snapshot_id, "expectation_overlay_snapshot_id"),
            (
                self.prospective_registration_snapshot_id,
                "prospective_registration_snapshot_id",
            ),
        ):
            if value is not None:
                _validate_sha(value, field)
        for values, field in (
            (self.comparable_security_ids, "comparable_security_ids"),
            (self.base_pareto_frontier_security_ids, "base_pareto_frontier_security_ids"),
            (
                self.expectation_pareto_frontier_security_ids,
                "expectation_pareto_frontier_security_ids",
            ),
            (self.flags, "flags"),
        ):
            _validate_text_tuple(values, field)
        security_set = set(self.security_ids)
        if not set(self.comparable_security_ids).issubset(security_set):
            raise ValueError("comparable securities must belong to the research round")
        if not set(self.base_pareto_frontier_security_ids).issubset(
            self.comparable_security_ids
        ):
            raise ValueError("base Pareto frontier must be a subset of comparable securities")
        if (
            self.expectation_pareto_frontier_security_ids
            and self.expectation_overlay_snapshot_id is None
        ):
            raise ValueError("expectation Pareto frontier requires an expectation overlay")
        _validate_sha(self.guardrail_evidence_id, "guardrail_evidence_id")
        blocked_statuses = {
            ResearchRoundStatus.PROSPECTIVE_BLOCKED,
            ResearchRoundStatus.REPLAY_BLOCKED,
        }
        if self.status in blocked_statuses and not self.blockers:
            raise ValueError("blocked research round requires at least one blocker")
        if self.status not in blocked_statuses and self.blockers:
            raise ValueError("ready or registered research round cannot contain blockers")
        self._validate_mode_status()

    def _validate_mode_status(self) -> None:
        if self.status is ResearchRoundStatus.PROSPECTIVE_REGISTERED:
            if self.mode is not ResearchRoundMode.PROSPECTIVE:
                raise ValueError("only a prospective round can be prospectively registered")
            if self.prospective_registration_snapshot_id is None:
                raise ValueError("prospective_registered status requires registration snapshot")
        elif self.prospective_registration_snapshot_id is not None:
            raise ValueError("registration snapshot requires prospective_registered status")
        if self.mode is ResearchRoundMode.REPLAY and self.status not in {
            ResearchRoundStatus.REPLAY_BLOCKED,
            ResearchRoundStatus.REPLAY_READY,
        }:
            raise ValueError("replay mode requires a replay status")
        if self.mode is ResearchRoundMode.PROSPECTIVE and self.status not in {
            ResearchRoundStatus.PROSPECTIVE_BLOCKED,
            ResearchRoundStatus.PROSPECTIVE_READY_FOR_REGISTRATION,
            ResearchRoundStatus.PROSPECTIVE_REGISTERED,
        }:
            raise ValueError("prospective mode requires a prospective status")

    @property
    def snapshot_id(self) -> str:
        return _sha(self.payload_without_id())

    def payload_without_id(self) -> dict[str, object]:
        return {
            "schema_version": RESEARCH_ROUND_ORCHESTRATOR_SCHEMA_VERSION,
            "round_id": self.round_id,
            "mode": self.mode.value,
            "status": self.status.value,
            "captured_at": self.captured_at.isoformat(),
            "evaluation_date": self.evaluation_date.isoformat(),
            "horizon_trading_days": self.horizon_trading_days,
            "security_ids": list(self.security_ids),
            "thesis_snapshot_ids": list(self.thesis_snapshot_ids),
            "underwriting_snapshot_ids": list(self.underwriting_snapshot_ids),
            "payoff_surface_snapshot_ids": list(self.payoff_surface_snapshot_ids),
            "decision_view_snapshot_ids": list(self.decision_view_snapshot_ids),
            "expectation_gap_snapshot_ids": list(self.expectation_gap_snapshot_ids),
            "opportunity_candidate_snapshot_ids": list(
                self.opportunity_candidate_snapshot_ids
            ),
            "opportunity_set_snapshot_id": self.opportunity_set_snapshot_id,
            "expectation_overlay_snapshot_id": self.expectation_overlay_snapshot_id,
            "prospective_registration_snapshot_id": (
                self.prospective_registration_snapshot_id
            ),
            "comparable_security_ids": list(self.comparable_security_ids),
            "base_pareto_frontier_security_ids": list(
                self.base_pareto_frontier_security_ids
            ),
            "expectation_pareto_frontier_security_ids": list(
                self.expectation_pareto_frontier_security_ids
            ),
            "blockers": [item.payload() for item in self.blockers],
            "flags": list(self.flags),
            "guardrail_evidence_id": self.guardrail_evidence_id,
            "point_in_time_fail_closed": True,
            "missing_evidence_neutralized": False,
            "research_logic_reimplemented": False,
            "automatic_investable_now_transition_enabled": False,
            "target_price_enabled": False,
            "optimal_position_size_enabled": False,
            "portfolio_recommendation_enabled": False,
            "automatic_execution_enabled": False,
            "future_outcome_claimed": False,
        }


@dataclass(frozen=True)
class ResearchRoundArtifacts:
    """Typed in-memory artifacts produced while assembling the round."""

    snapshot: ResearchRoundSnapshot
    opportunity_candidates: tuple[OpportunityCandidateSnapshot, ...]
    opportunity_set: OpportunitySetSnapshot | None
    expectation_overlay: ExpectationAugmentedOpportunitySetSnapshot | None
    prospective_registration: ProspectiveOpportunityRegistration | None


def run_research_round(
    packages: tuple[ResearchSecurityPackage, ...],
    *,
    round_id: str,
    mode: ResearchRoundMode,
    captured_at: datetime,
    evaluation_date: date,
    horizon_trading_days: int,
    expectation_policy: ExpectationGapComparisonPolicySnapshot | None = None,
    registration_request: ProspectiveRegistrationRequest | None = None,
    guardrails: DecisionSystemV21Guardrails | None = None,
) -> ResearchRoundArtifacts:
    """Assemble existing contracts and return blockers instead of inventing evidence."""

    active = guardrails or load_decision_system_v21_guardrails()
    _require_text(round_id, "round_id")
    _require_aware(captured_at, "captured_at")
    if horizon_trading_days not in _SUPPORTED_HORIZONS:
        raise ValueError("research round horizon must be 60, 120, or 250 trading days")
    if len(packages) < 2:
        raise ValueError("cross-sectional research round requires at least two packages")
    security_ids = tuple(item.security_id for item in packages)
    if len(set(security_ids)) != len(security_ids):
        raise ValueError("research round packages require unique securities")
    if mode is ResearchRoundMode.REPLAY and registration_request is not None:
        raise ValueError("replay mode cannot create a prospective scorekeeping registration")

    blockers: list[ResearchRoundBlocker] = []
    flags: list[str] = []
    candidates: list[OpportunityCandidateSnapshot] = []
    underwriting_ids: list[str] = []
    payoff_ids: list[str] = []
    decision_view_ids: list[str] = []
    expectation_gap_ids: list[str] = []

    for package in packages:
        _validate_package(
            package,
            captured_at=captured_at,
            evaluation_date=evaluation_date,
            horizon_trading_days=horizon_trading_days,
            guardrail_evidence_id=active.evidence_id,
            blockers=blockers,
        )
        if package.underwriting is not None:
            underwriting_ids.append(package.underwriting.snapshot_id)
            flags.extend(
                f"{package.security_id}:underwriter:{item}"
                for item in package.underwriting.flags
            )
        if package.payoff_surface is not None:
            payoff_ids.append(package.payoff_surface.snapshot_id)
        if package.decision_view is not None:
            decision_view_ids.append(package.decision_view.snapshot_id)
        if package.expectation_gap is not None:
            expectation_gap_ids.append(package.expectation_gap.snapshot_id)

        package_blocked = any(
            item.security_id == package.security_id for item in blockers
        )
        if (
            not package_blocked
            and package.underwriting is not None
            and package.payoff_surface is not None
        ):
            try:
                candidates.append(
                    build_opportunity_candidate(
                        package.thesis,
                        package.underwriting,
                        package.payoff_surface,
                        captured_at=captured_at,
                        evaluation_date=evaluation_date,
                        guardrails=active,
                    )
                )
            except ValueError as exc:
                _block(
                    blockers,
                    "opportunity_candidate",
                    "opportunity_candidate_build_failed",
                    str(exc),
                    package.security_id,
                )

    opportunity_set = _build_base_opportunity_set(
        candidates,
        packages=packages,
        captured_at=captured_at,
        evaluation_date=evaluation_date,
        horizon_trading_days=horizon_trading_days,
        guardrails=active,
        blockers=blockers,
    )
    overlay = _build_expectation_overlay(
        packages,
        candidates,
        opportunity_set=opportunity_set,
        expectation_policy=expectation_policy,
        captured_at=captured_at,
        evaluation_date=evaluation_date,
        guardrails=active,
        blockers=blockers,
        flags=flags,
    )
    registration = _register_prospective_if_requested(
        mode,
        opportunity_set=opportunity_set,
        expectation_overlay=overlay,
        request=registration_request,
        blockers=blockers,
        flags=flags,
    )
    status = _derive_status(mode, blockers=blockers, registration=registration)
    snapshot = ResearchRoundSnapshot(
        round_id=round_id,
        mode=mode,
        status=status,
        captured_at=captured_at,
        evaluation_date=evaluation_date,
        horizon_trading_days=horizon_trading_days,
        security_ids=security_ids,
        thesis_snapshot_ids=tuple(item.thesis.snapshot_id for item in packages),
        underwriting_snapshot_ids=tuple(underwriting_ids),
        payoff_surface_snapshot_ids=tuple(payoff_ids),
        decision_view_snapshot_ids=tuple(decision_view_ids),
        expectation_gap_snapshot_ids=tuple(expectation_gap_ids),
        opportunity_candidate_snapshot_ids=tuple(item.snapshot_id for item in candidates),
        opportunity_set_snapshot_id=(opportunity_set.snapshot_id if opportunity_set else None),
        expectation_overlay_snapshot_id=(overlay.snapshot_id if overlay else None),
        prospective_registration_snapshot_id=(registration.snapshot_id if registration else None),
        comparable_security_ids=(
            opportunity_set.comparable_security_ids if opportunity_set else ()
        ),
        base_pareto_frontier_security_ids=(
            opportunity_set.pareto_frontier_security_ids if opportunity_set else ()
        ),
        expectation_pareto_frontier_security_ids=(
            overlay.expectation_pareto_frontier_security_ids if overlay else ()
        ),
        blockers=tuple(blockers),
        flags=tuple(dict.fromkeys(flags)),
        guardrail_evidence_id=active.evidence_id,
    )
    return ResearchRoundArtifacts(
        snapshot=snapshot,
        opportunity_candidates=tuple(candidates),
        opportunity_set=opportunity_set,
        expectation_overlay=overlay,
        prospective_registration=registration,
    )


def _validate_package(
    package: ResearchSecurityPackage,
    *,
    captured_at: datetime,
    evaluation_date: date,
    horizon_trading_days: int,
    guardrail_evidence_id: str,
    blockers: list[ResearchRoundBlocker],
) -> None:
    thesis = package.thesis
    security_id = thesis.security_id
    if thesis.captured_at > captured_at:
        _block(
            blockers,
            "thesis",
            "thesis_after_round_cutoff",
            "thesis snapshot was captured after the research-round cutoff",
            security_id,
            thesis.snapshot_id,
        )
    if thesis.horizon_trading_days != horizon_trading_days:
        _block(
            blockers,
            "thesis",
            "thesis_horizon_mismatch",
            "thesis horizon differs from the research-round horizon",
            security_id,
            thesis.snapshot_id,
        )
    _validate_underwriting(
        package,
        captured_at=captured_at,
        evaluation_date=evaluation_date,
        guardrail_evidence_id=guardrail_evidence_id,
        blockers=blockers,
    )
    _validate_payoff(
        package,
        captured_at=captured_at,
        horizon_trading_days=horizon_trading_days,
        guardrail_evidence_id=guardrail_evidence_id,
        blockers=blockers,
    )
    _validate_decision_view(
        package,
        captured_at=captured_at,
        evaluation_date=evaluation_date,
        guardrail_evidence_id=guardrail_evidence_id,
        blockers=blockers,
    )
    _validate_expectation_gap(
        package,
        captured_at=captured_at,
        evaluation_date=evaluation_date,
        guardrail_evidence_id=guardrail_evidence_id,
        blockers=blockers,
    )


def _validate_underwriting(
    package: ResearchSecurityPackage,
    *,
    captured_at: datetime,
    evaluation_date: date,
    guardrail_evidence_id: str,
    blockers: list[ResearchRoundBlocker],
) -> None:
    item = package.underwriting
    thesis = package.thesis
    if item is None:
        _block(
            blockers,
            "underwriter",
            "underwriting_snapshot_missing",
            "typed UnderwritingReadinessSnapshot is required",
            thesis.security_id,
        )
        return
    checks = (
        (item.thesis_snapshot_id == thesis.snapshot_id, "underwriting_thesis_mismatch"),
        (item.security_id == thesis.security_id, "underwriting_security_mismatch"),
        (item.evaluation_date == evaluation_date, "underwriting_evaluation_date_mismatch"),
        (item.captured_at <= captured_at, "underwriting_after_round_cutoff"),
        (item.guardrail_evidence_id == guardrail_evidence_id, "underwriting_guardrail_mismatch"),
    )
    _apply_checks(blockers, "underwriter", thesis.security_id, item.snapshot_id, checks)


def _validate_payoff(
    package: ResearchSecurityPackage,
    *,
    captured_at: datetime,
    horizon_trading_days: int,
    guardrail_evidence_id: str,
    blockers: list[ResearchRoundBlocker],
) -> None:
    item = package.payoff_surface
    thesis = package.thesis
    if item is None:
        _block(
            blockers,
            "payoff_surface",
            "payoff_surface_missing",
            "typed PayoffSurfaceSnapshot is required",
            thesis.security_id,
        )
        return
    checks = (
        (item.thesis_snapshot_id == thesis.snapshot_id, "payoff_thesis_mismatch"),
        (item.security_id == thesis.security_id, "payoff_security_mismatch"),
        (item.horizon_trading_days == horizon_trading_days, "payoff_horizon_mismatch"),
        (item.captured_at <= captured_at, "payoff_after_round_cutoff"),
        (item.guardrail_evidence_id == guardrail_evidence_id, "payoff_guardrail_mismatch"),
    )
    _apply_checks(blockers, "payoff_surface", thesis.security_id, item.snapshot_id, checks)


def _validate_decision_view(
    package: ResearchSecurityPackage,
    *,
    captured_at: datetime,
    evaluation_date: date,
    guardrail_evidence_id: str,
    blockers: list[ResearchRoundBlocker],
) -> None:
    item = package.decision_view
    if item is None:
        return
    checks = (
        (item.security_id == package.security_id, "decision_view_security_mismatch"),
        (item.evaluation_date == evaluation_date, "decision_view_evaluation_date_mismatch"),
        (item.captured_at <= captured_at, "decision_view_after_round_cutoff"),
        (item.guardrail_evidence_id == guardrail_evidence_id, "decision_view_guardrail_mismatch"),
    )
    _apply_checks(blockers, "decision_view", package.security_id, item.snapshot_id, checks)


def _validate_expectation_gap(
    package: ResearchSecurityPackage,
    *,
    captured_at: datetime,
    evaluation_date: date,
    guardrail_evidence_id: str,
    blockers: list[ResearchRoundBlocker],
) -> None:
    gap = package.expectation_gap
    if gap is None:
        return
    view = package.decision_view
    if view is None:
        _block(
            blockers,
            "expectation_gap",
            "decision_view_missing_for_expectation_gap",
            "expectation-gap snapshot requires its typed Decision View in the package",
            package.security_id,
            gap.snapshot_id,
        )
        return
    checks = (
        (gap.decision_view_snapshot_id == view.snapshot_id, "expectation_gap_decision_view_mismatch"),
        (gap.security_id == package.security_id, "expectation_gap_security_mismatch"),
        (gap.evaluation_date == evaluation_date, "expectation_gap_evaluation_date_mismatch"),
        (gap.captured_at <= captured_at, "expectation_gap_after_round_cutoff"),
        (gap.guardrail_evidence_id == guardrail_evidence_id, "expectation_gap_guardrail_mismatch"),
        (
            gap.target_variable == view.target_variable
            and gap.target_date == view.target_date
            and gap.unit == view.unit,
            "expectation_gap_target_mismatch",
        ),
    )
    _apply_checks(blockers, "expectation_gap", package.security_id, gap.snapshot_id, checks)


def _apply_checks(
    blockers: list[ResearchRoundBlocker],
    component: str,
    security_id: str,
    snapshot_id: str,
    checks: tuple[tuple[bool, str], ...],
) -> None:
    for condition, code in checks:
        if not condition:
            detail = code.replace("_", " ")
            _block(blockers, component, code, detail, security_id, snapshot_id)


def _build_base_opportunity_set(
    candidates: list[OpportunityCandidateSnapshot],
    *,
    packages: tuple[ResearchSecurityPackage, ...],
    captured_at: datetime,
    evaluation_date: date,
    horizon_trading_days: int,
    guardrails: DecisionSystemV21Guardrails,
    blockers: list[ResearchRoundBlocker],
) -> OpportunitySetSnapshot | None:
    if len(candidates) != len(packages):
        _block(
            blockers,
            "opportunity_set",
            "opportunity_candidate_coverage_incomplete",
            "every research-round security must yield one typed opportunity candidate",
        )
        return None
    try:
        result = build_opportunity_set(
            tuple(candidates),
            captured_at=captured_at,
            evaluation_date=evaluation_date,
            horizon_trading_days=horizon_trading_days,
            guardrails=guardrails,
        )
    except ValueError as exc:
        _block(
            blockers,
            "opportunity_set",
            "opportunity_set_build_failed",
            str(exc),
        )
        return None
    if len(result.comparable_security_ids) < 2:
        detail = (
            "prospective cross-sectional comparison requires at least two "
            "Deep-Lane comparable securities"
        )
        _block(
            blockers,
            "opportunity_set",
            "insufficient_capital_allocation_comparable_candidates",
            detail,
            snapshot_id=result.snapshot_id,
        )
    return result


def _build_expectation_overlay(
    packages: tuple[ResearchSecurityPackage, ...],
    candidates: list[OpportunityCandidateSnapshot],
    *,
    opportunity_set: OpportunitySetSnapshot | None,
    expectation_policy: ExpectationGapComparisonPolicySnapshot | None,
    captured_at: datetime,
    evaluation_date: date,
    guardrails: DecisionSystemV21Guardrails,
    blockers: list[ResearchRoundBlocker],
    flags: list[str],
) -> ExpectationAugmentedOpportunitySetSnapshot | None:
    if expectation_policy is None:
        flags.append("expectation_overlay_not_requested")
        return None
    if expectation_policy.guardrail_evidence_id != guardrails.evidence_id:
        _block(
            blockers,
            "expectation_overlay",
            "expectation_policy_guardrail_mismatch",
            "expectation policy is not bound to the active v2.1 guardrail",
            snapshot_id=expectation_policy.snapshot_id,
        )
        return None
    if expectation_policy.evaluation_date != evaluation_date:
        _block(
            blockers,
            "expectation_overlay",
            "expectation_policy_evaluation_date_mismatch",
            "expectation policy uses another evaluation date",
            snapshot_id=expectation_policy.snapshot_id,
        )
        return None
    if opportunity_set is None:
        return None
    by_package = {item.security_id: item for item in packages}
    by_candidate = {item.security_id: item for item in candidates}
    expectation_candidates = []
    for security_id in opportunity_set.comparable_security_ids:
        package = by_package[security_id]
        gap = package.expectation_gap
        if gap is None:
            _block(
                blockers,
                "expectation_overlay",
                "expectation_gap_missing_for_comparable_security",
                "every base-comparable security requires a policy-aligned expectation gap",
                security_id,
            )
            continue
        try:
            expectation_candidates.append(
                build_expectation_gap_opportunity_candidate(
                    by_candidate[security_id],
                    gap,
                    expectation_policy,
                    captured_at=captured_at,
                    guardrails=guardrails,
                )
            )
        except ValueError as exc:
            _block(
                blockers,
                "expectation_overlay",
                "expectation_candidate_build_failed",
                str(exc),
                security_id,
                gap.snapshot_id,
            )
    expected_count = len(opportunity_set.comparable_security_ids)
    if expected_count < 2 or len(expectation_candidates) != expected_count:
        if expected_count >= 2:
            _block(
                blockers,
                "expectation_overlay",
                "expectation_candidate_coverage_incomplete",
                "expectation overlay cannot silently omit a base-comparable security",
                snapshot_id=opportunity_set.snapshot_id,
            )
        return None
    try:
        return build_expectation_augmented_opportunity_set(
            opportunity_set,
            expectation_policy,
            tuple(expectation_candidates),
            captured_at=captured_at,
            guardrails=guardrails,
        )
    except ValueError as exc:
        _block(
            blockers,
            "expectation_overlay",
            "expectation_overlay_build_failed",
            str(exc),
            snapshot_id=opportunity_set.snapshot_id,
        )
        return None


def _register_prospective_if_requested(
    mode: ResearchRoundMode,
    *,
    opportunity_set: OpportunitySetSnapshot | None,
    expectation_overlay: ExpectationAugmentedOpportunitySetSnapshot | None,
    request: ProspectiveRegistrationRequest | None,
    blockers: list[ResearchRoundBlocker],
    flags: list[str],
) -> ProspectiveOpportunityRegistration | None:
    if mode is not ResearchRoundMode.PROSPECTIVE or request is None:
        return None
    if blockers:
        flags.append("prospective_registration_skipped_due_to_research_blockers")
        return None
    if opportunity_set is None:
        _block(
            blockers,
            "prospective_registration",
            "opportunity_set_unavailable",
            "prospective registration requires an opportunity-set snapshot",
        )
        return None
    try:
        return register_prospective_opportunity_set(
            opportunity_set,
            registration_id=request.registration_id,
            registered_at=request.registered_at,
            benchmark_security_id=request.benchmark_security_id,
            price_basis=request.price_basis,
            source_evidence_ids=request.source_evidence_ids,
            calendar=request.calendar,
            expectation_overlay=expectation_overlay,
        )
    except ValueError as exc:
        _block(
            blockers,
            "prospective_registration",
            "prospective_registration_failed",
            str(exc),
            snapshot_id=opportunity_set.snapshot_id,
        )
        return None


def _derive_status(
    mode: ResearchRoundMode,
    *,
    blockers: list[ResearchRoundBlocker],
    registration: ProspectiveOpportunityRegistration | None,
) -> ResearchRoundStatus:
    if blockers:
        if mode is ResearchRoundMode.PROSPECTIVE:
            return ResearchRoundStatus.PROSPECTIVE_BLOCKED
        return ResearchRoundStatus.REPLAY_BLOCKED
    if mode is ResearchRoundMode.REPLAY:
        return ResearchRoundStatus.REPLAY_READY
    if registration is not None:
        return ResearchRoundStatus.PROSPECTIVE_REGISTERED
    return ResearchRoundStatus.PROSPECTIVE_READY_FOR_REGISTRATION


def persist_research_round(
    snapshot: ResearchRoundSnapshot,
    *,
    output_root: str | Path,
) -> Path:
    """Persist one immutable research-round integration snapshot."""

    path = Path(output_root) / "research_round_v2_1" / f"{snapshot.snapshot_id}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = dict(snapshot.payload_without_id())
    payload["snapshot_id"] = snapshot.snapshot_id
    encoded = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    fd: int | None = None
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            fd = None
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
    except BaseException:
        if fd is not None:
            os.close(fd)
        path.unlink(missing_ok=True)
        raise
    return path


def _block(
    blockers: list[ResearchRoundBlocker],
    component: str,
    code: str,
    detail: str,
    security_id: str | None = None,
    snapshot_id: str | None = None,
) -> None:
    value = ResearchRoundBlocker(
        component=component,
        code=code,
        detail=detail,
        security_id=security_id,
        snapshot_id=snapshot_id,
    )
    if value not in blockers:
        blockers.append(value)


def _require_aware(value: datetime, field: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field} must be timezone-aware")


def _require_text(value: str, field: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be non-empty text")


def _validate_text_tuple(values: tuple[str, ...], field: str) -> None:
    for value in values:
        _require_text(value, field)
    if len(set(values)) != len(values):
        raise ValueError(f"{field} cannot contain duplicates")


def _validate_sha(value: str, field: str) -> None:
    if len(value) != 64:
        raise ValueError(f"{field} must be a SHA-256 hex digest")
    try:
        int(value, 16)
    except ValueError as exc:
        raise ValueError(f"{field} must be a SHA-256 hex digest") from exc


def _validate_sha_tuple(values: tuple[str, ...], field: str) -> None:
    for value in values:
        _validate_sha(value, field)
    if len(set(values)) != len(values):
        raise ValueError(f"{field} cannot contain duplicates")


def _sha(payload: dict[str, object]) -> str:
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()
