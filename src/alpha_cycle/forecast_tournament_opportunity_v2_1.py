"""Replayable prospective forecast tournament and horizon opportunity evidence v2.1.

This module deliberately emits no synthetic score.  It adapts the one genuinely frozen
prospective experiment that exists today, preserves its original authority boundary, and builds
3/6/12-month evidence maps whose unsupported dimensions remain typed blockers.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import tempfile
from dataclasses import dataclass
from datetime import UTC, date, datetime
from enum import StrEnum
from pathlib import Path

from alpha_cycle.intelligence.sk_hynix_company_gp_ex_ante_2026q3_numeric_forecast import (
    LockedNumericForecast,
    load_locked_numeric_forecast,
)
from alpha_cycle.intelligence.sk_hynix_company_gp_ex_ante_2026q3_prospective_feature import (
    FrozenProspectiveFeatureVector,
    ProspectiveSourceCapture,
    load_prospective_feature_vector,
    load_prospective_source_capture,
    load_selected_estimator_artifact,
)
from alpha_cycle.intelligence.sk_hynix_company_gp_ex_ante_selected_estimator_freeze import (
    FrozenSelectedEstimatorFullFit,
)

SCHEMA_VERSION = 1
PARSER_ID = "alpha_cycle.forecast_tournament_opportunity_v2_1"
PARSER_VERSION = "1.0.0"
SUPPORTED_SECURITIES = ("000660", "005930")
SUPPORTED_HORIZONS = (63, 126, 252)
DEFAULT_FEATURE = Path(
    "data/private/research/skhynix-company-gp-ex-ante-2026q3-prospective/"
    "feature-vector-139d50940b27582dbaa9206989439c7b9253d75d65e12e45bcb7a14512214bda.json"
)
DEFAULT_ESTIMATOR = Path(
    "data/private/research/skhynix-company-gp-ex-ante-selected-estimator/"
    "selected-estimator-4ddf0e7206fcbb6a58ba2e7fcb93b48bf79195171dfc96a894481dbfa612a2d1.json"
)
DEFAULT_SOURCE_CAPTURE_DIRECTORY = Path(
    "data/private/research/skhynix-company-gp-ex-ante-2026q3-prospective/"
    "source-capture-81be10f546a65c6f2e89ec8b82779c7ac2c529846750e95320c1cb8e0980db5a"
)


class ForecastTournamentError(ValueError):
    """Raised when prospective lineage or a persisted tournament fails replay."""


class CandidateClass(StrEnum):
    INTERNAL_DETERMINISTIC_MODEL = "internal_deterministic_model"
    PREREGISTERED_BENCHMARK = "preregistered_benchmark"


class EvidenceStatus(StrEnum):
    SUPPORTED = "supported"
    BLOCKED = "blocked"
    UNAVAILABLE = "unavailable"
    INCOMPARABLE = "incomparable"
    MEASURED_BUT_NON_DIRECTIONAL = "measured_but_non_directional"
    NON_AUTHORITATIVE = "non_authoritative"


@dataclass(frozen=True)
class ProspectiveCandidate:
    candidate_id: str
    candidate_class: CandidateClass
    security_id: str
    metric: str
    target_period: str
    horizon_semantics: str
    model_identity: str
    model_version_id: str
    code_identity: str
    source_artifact_id: str
    source_bytes_sha256: str
    input_artifact_ids: tuple[str, ...]
    input_cutoff: datetime
    feature_cutoff: datetime
    training_cutoff: datetime | None
    registered_at: datetime
    forecast_origin: datetime
    forecast_value: float
    interval_lower: float | None
    interval_upper: float | None
    unit: str
    currency: str | None
    accounting_basis: str
    transformation_semantics: str
    outcome_definition: str
    scoring_rule: str
    tournament_identity: str
    selection_rule: str
    lineage_ids: tuple[str, ...]
    tournament_eligible: bool
    eligibility_blockers: tuple[str, ...]

    def __post_init__(self) -> None:
        for text_value, field in (
            (self.candidate_id, "candidate_id"),
            (self.security_id, "security_id"),
            (self.metric, "metric"),
            (self.target_period, "target_period"),
            (self.horizon_semantics, "horizon_semantics"),
            (self.model_identity, "model_identity"),
            (self.code_identity, "code_identity"),
            (self.unit, "unit"),
            (self.accounting_basis, "accounting_basis"),
            (self.transformation_semantics, "transformation_semantics"),
            (self.outcome_definition, "outcome_definition"),
            (self.scoring_rule, "scoring_rule"),
            (self.tournament_identity, "tournament_identity"),
            (self.selection_rule, "selection_rule"),
        ):
            _text(text_value, field)
        for sha_value, field in (
            (self.model_version_id, "model_version_id"),
            (self.source_artifact_id, "source_artifact_id"),
            (self.source_bytes_sha256, "source_bytes_sha256"),
        ):
            _sha_text(sha_value, field)
        _sha_tuple(self.input_artifact_ids, "input_artifact_ids")
        _sha_tuple(self.lineage_ids, "lineage_ids")
        for timestamp_value, field in (
            (self.input_cutoff, "input_cutoff"),
            (self.feature_cutoff, "feature_cutoff"),
            (self.registered_at, "registered_at"),
            (self.forecast_origin, "forecast_origin"),
        ):
            _aware(timestamp_value, field)
        if self.training_cutoff is not None:
            _aware(self.training_cutoff, "training_cutoff")
        cutoffs = (self.input_cutoff, self.feature_cutoff) + (
            (self.training_cutoff,) if self.training_cutoff is not None else ()
        )
        if max(cutoffs) > self.registered_at:
            raise ForecastTournamentError("forecast cutoff follows registration")
        if self.registered_at > self.forecast_origin:
            raise ForecastTournamentError("forecast registration follows forecast origin")
        if type(self.forecast_value) is not float or not math.isfinite(self.forecast_value):
            raise ForecastTournamentError("forecast value must be a canonical finite float")
        if self.interval_lower is not None or self.interval_upper is not None:
            if type(self.interval_lower) is not float or type(self.interval_upper) is not float:
                raise ForecastTournamentError("forecast interval must use canonical floats")
            if (
                self.interval_lower > self.forecast_value
                or self.interval_upper < self.forecast_value
            ):
                raise ForecastTournamentError("forecast interval does not contain point forecast")
        if self.tournament_eligible:
            if (
                self.candidate_class is CandidateClass.INTERNAL_DETERMINISTIC_MODEL
                and self.training_cutoff is None
            ) or self.eligibility_blockers:
                raise ForecastTournamentError(
                    "eligible candidate requires every applicable cutoff and no blockers"
                )
        elif not self.eligibility_blockers:
            raise ForecastTournamentError("ineligible candidate requires blockers")

    @property
    def comparability_key(self) -> tuple[str, str, str, str, str, str | None, str]:
        return (
            self.security_id,
            self.metric,
            self.target_period,
            self.horizon_semantics,
            self.unit,
            self.currency,
            self.accounting_basis,
        )

    def payload(self) -> dict[str, object]:
        return {
            "candidate_id": self.candidate_id,
            "candidate_class": self.candidate_class.value,
            "security_id": self.security_id,
            "metric": self.metric,
            "target_period": self.target_period,
            "horizon_semantics": self.horizon_semantics,
            "model_identity": self.model_identity,
            "model_version_id": self.model_version_id,
            "code_identity": self.code_identity,
            "source_artifact_id": self.source_artifact_id,
            "source_bytes_sha256": self.source_bytes_sha256,
            "input_artifact_ids": list(self.input_artifact_ids),
            "input_cutoff": self.input_cutoff.isoformat(),
            "feature_cutoff": self.feature_cutoff.isoformat(),
            "training_cutoff": (
                self.training_cutoff.isoformat() if self.training_cutoff is not None else None
            ),
            "registered_at": self.registered_at.isoformat(),
            "forecast_origin": self.forecast_origin.isoformat(),
            "forecast_value": self.forecast_value,
            "interval_lower": self.interval_lower,
            "interval_upper": self.interval_upper,
            "unit": self.unit,
            "currency": self.currency,
            "accounting_basis": self.accounting_basis,
            "transformation_semantics": self.transformation_semantics,
            "outcome_definition": self.outcome_definition,
            "scoring_rule": self.scoring_rule,
            "tournament_identity": self.tournament_identity,
            "selection_rule": self.selection_rule,
            "lineage_ids": list(self.lineage_ids),
            "tournament_eligible": self.tournament_eligible,
            "eligibility_blockers": list(self.eligibility_blockers),
            "outcome_available": False,
            "evaluation_available": False,
        }


@dataclass(frozen=True)
class ForecastTournament:
    tournament_id: str
    captured_at: datetime
    candidates: tuple[ProspectiveCandidate, ...]
    comparable_candidate_ids: tuple[str, ...]
    winner_candidate_id: str | None
    outcome_scoring_available: bool
    blockers: tuple[str, ...]

    def __post_init__(self) -> None:
        _text(self.tournament_id, "tournament_id")
        _aware(self.captured_at, "captured_at")
        ids = tuple(item.candidate_id for item in self.candidates)
        aliases = tuple(_alias(item) for item in self.candidates)
        if len(ids) != len(set(ids)) or len(aliases) != len(set(aliases)):
            raise ForecastTournamentError("forecast tournament contains duplicate candidate")
        if any(item.registered_at > self.captured_at for item in self.candidates):
            raise ForecastTournamentError("tournament capture precedes candidate registration")
        if not set(self.comparable_candidate_ids).issubset(ids):
            raise ForecastTournamentError("comparable candidate identity is unknown")
        if any(
            not item.tournament_eligible
            for item in self.candidates
            if item.candidate_id in self.comparable_candidate_ids
        ):
            raise ForecastTournamentError("ineligible candidate cannot be tournament-comparable")
        if self.winner_candidate_id is not None:
            if len(self.comparable_candidate_ids) < 2:
                raise ForecastTournamentError("winner requires at least two comparable candidates")
            if not self.outcome_scoring_available:
                raise ForecastTournamentError("winner requires authenticated outcome scoring")
        if self.outcome_scoring_available:
            raise ForecastTournamentError("2026Q3 authenticated outcome is not available")

    @property
    def snapshot_id(self) -> str:
        return _digest(_canonical(self.payload_without_id()))

    def payload_without_id(self) -> dict[str, object]:
        return {
            "schema_version": SCHEMA_VERSION,
            "tournament_id": self.tournament_id,
            "captured_at": self.captured_at.isoformat(),
            "candidates": [item.payload() for item in self.candidates],
            "comparable_candidate_ids": list(self.comparable_candidate_ids),
            "winner_candidate_id": self.winner_candidate_id,
            "outcome_scoring_available": self.outcome_scoring_available,
            "blockers": list(self.blockers),
            "hindsight_selection_enabled": False,
        }


@dataclass(frozen=True)
class OpportunityDimension:
    name: str
    status: EvidenceStatus
    evidence_ids: tuple[str, ...]
    blocker: str | None

    def __post_init__(self) -> None:
        _text(self.name, "dimension name")
        _sha_tuple(self.evidence_ids, "dimension evidence_ids")
        if self.status is EvidenceStatus.SUPPORTED and not self.evidence_ids:
            raise ForecastTournamentError("supported dimension requires evidence")
        if self.status is EvidenceStatus.SUPPORTED and self.blocker is not None:
            raise ForecastTournamentError("supported dimension cannot have blocker")
        if self.status is not EvidenceStatus.SUPPORTED and self.blocker is None:
            raise ForecastTournamentError("unsupported dimension requires blocker")

    def payload(self) -> dict[str, object]:
        return {
            "name": self.name,
            "status": self.status.value,
            "evidence_ids": list(self.evidence_ids),
            "blocker": self.blocker,
            "numeric_score": None,
        }


@dataclass(frozen=True)
class HorizonOpportunity:
    security_id: str
    horizon_months: int
    horizon_trading_days: int
    dimensions: tuple[OpportunityDimension, ...]
    evidence_coverage: float
    partial_rank: int | None
    overall_rank: int | None
    blockers: tuple[str, ...]

    def __post_init__(self) -> None:
        if self.security_id not in SUPPORTED_SECURITIES:
            raise ForecastTournamentError("unsupported opportunity security")
        expected = {3: 63, 6: 126, 12: 252}
        if expected.get(self.horizon_months) != self.horizon_trading_days:
            raise ForecastTournamentError("opportunity horizon semantics mismatch")
        names = tuple(item.name for item in self.dimensions)
        if names != tuple(sorted(set(names))):
            raise ForecastTournamentError("opportunity dimensions must be unique and sorted")
        if type(self.evidence_coverage) is not float or not 0 <= self.evidence_coverage <= 1:
            raise ForecastTournamentError("evidence coverage must be a canonical ratio")
        if self.partial_rank is not None or self.overall_rank is not None:
            raise ForecastTournamentError("current evidence cannot authorize numeric ranking")

    def payload(self) -> dict[str, object]:
        return {
            "security_id": self.security_id,
            "horizon_months": self.horizon_months,
            "horizon_trading_days": self.horizon_trading_days,
            "dimensions": [item.payload() for item in self.dimensions],
            "evidence_coverage": self.evidence_coverage,
            "partial_rank": self.partial_rank,
            "overall_rank": self.overall_rank,
            "blockers": list(self.blockers),
        }


@dataclass(frozen=True)
class ForecastOpportunityBundle:
    captured_at: datetime
    evaluation_date: date
    market_snapshot_id: str
    research_snapshot_id: str
    frozen_forecast_bytes_sha256: str
    frozen_feature_bytes_sha256: str
    frozen_estimator_bytes_sha256: str
    frozen_source_capture_bytes_sha256: str
    frozen_source_raw_bytes_sha256: str
    tournament: ForecastTournament
    opportunities: tuple[HorizonOpportunity, ...]

    def __post_init__(self) -> None:
        _aware(self.captured_at, "captured_at")
        _sha_text(self.market_snapshot_id, "market_snapshot_id")
        _sha_text(self.research_snapshot_id, "research_snapshot_id")
        _sha_text(self.frozen_forecast_bytes_sha256, "frozen_forecast_bytes_sha256")
        _sha_text(self.frozen_feature_bytes_sha256, "frozen_feature_bytes_sha256")
        _sha_text(self.frozen_estimator_bytes_sha256, "frozen_estimator_bytes_sha256")
        _sha_text(self.frozen_source_capture_bytes_sha256, "frozen_source_capture_bytes_sha256")
        _sha_text(self.frozen_source_raw_bytes_sha256, "frozen_source_raw_bytes_sha256")
        keys = tuple((item.security_id, item.horizon_months) for item in self.opportunities)
        expected = tuple(
            (security, horizon)
            for security in SUPPORTED_SECURITIES
            for horizon in (3, 6, 12)
        )
        if keys != expected:
            raise ForecastTournamentError("bundle requires 000660/005930 x 3/6/12M exactly")
        if self.tournament.captured_at > self.captured_at:
            raise ForecastTournamentError("bundle capture precedes tournament")

    @property
    def artifact_id(self) -> str:
        return _digest(_canonical(self.payload_without_id()))

    def payload_without_id(self) -> dict[str, object]:
        return {
            "schema_version": SCHEMA_VERSION,
            "parser_id": PARSER_ID,
            "parser_version": PARSER_VERSION,
            "captured_at": self.captured_at.isoformat(),
            "evaluation_date": self.evaluation_date.isoformat(),
            "market_snapshot_id": self.market_snapshot_id,
            "research_snapshot_id": self.research_snapshot_id,
            "frozen_forecast_bytes_sha256": self.frozen_forecast_bytes_sha256,
            "frozen_feature_bytes_sha256": self.frozen_feature_bytes_sha256,
            "frozen_estimator_bytes_sha256": self.frozen_estimator_bytes_sha256,
            "frozen_source_capture_bytes_sha256": self.frozen_source_capture_bytes_sha256,
            "frozen_source_raw_bytes_sha256": self.frozen_source_raw_bytes_sha256,
            "tournament": {
                **self.tournament.payload_without_id(),
                "snapshot_id": self.tournament.snapshot_id,
            },
            "opportunities": [item.payload() for item in self.opportunities],
            "missing_data_policy": "never_numeric_neutral_never_weight_renormalize",
            "partial_ranking_available": False,
            "overall_ranking_available": False,
            "probabilities_available": False,
            "valuation_available": False,
            "price_implied_available": False,
            "scenario_payoff_available": False,
            "current_state_status": "partial_evidence_ranking_blocked",
            "stale_ready_state_allowed": False,
            "automatic_execution_enabled": False,
        }

    def payload(self) -> dict[str, object]:
        return {**self.payload_without_id(), "artifact_id": self.artifact_id}


def build_forecast_opportunity_bundle(
    *,
    frozen_forecast_path: str | Path,
    captured_at: datetime,
    evaluation_date: date,
    market_snapshot_id: str,
    research_snapshot_id: str,
    frozen_feature_path: str | Path = DEFAULT_FEATURE,
    selected_estimator_path: str | Path = DEFAULT_ESTIMATOR,
    source_capture_directory: str | Path = DEFAULT_SOURCE_CAPTURE_DIRECTORY,
) -> ForecastOpportunityBundle:
    """Replay the frozen 2026Q3 experiment and build an honest six-cell evidence map."""

    _aware(captured_at, "captured_at")
    if captured_at.date() < evaluation_date:
        raise ForecastTournamentError("bundle capture cannot precede evaluation date")
    content = _read_frozen_once(Path(frozen_forecast_path))
    frozen = _load_frozen_from_exact_bytes(content)
    lineage = _load_exact_upstream_lineage(
        feature_path=Path(frozen_feature_path),
        estimator_path=Path(selected_estimator_path),
        source_capture_directory=Path(source_capture_directory),
    )
    feature, estimator, capture, feature_bytes, estimator_bytes, capture_bytes, raw_bytes = lineage
    if (
        feature.evidence_id != frozen.feature_vector_evidence_id
        or estimator.evidence_id != frozen.selected_estimator_evidence_id
        or capture.evidence_id != frozen.source_capture_evidence_id
        or feature.selected_estimator_evidence_id != estimator.evidence_id
        or feature.source_capture_evidence_id != capture.evidence_id
    ):
        raise ForecastTournamentError("frozen forecast upstream identity binding mismatch")
    recomputed = estimator.raw_unit_intercept + sum(
        coefficient * value
        for coefficient, value in zip(
            estimator.raw_unit_coefficients, feature.feature_values, strict=True
        )
    )
    if not math.isclose(
        recomputed, frozen.selected_forecast_krw_million, rel_tol=1e-12, abs_tol=1e-6
    ) or not math.isclose(
        feature.feature_values[0],
        frozen.benchmark_forecast_krw_million,
        rel_tol=1e-12,
        abs_tol=1e-6,
    ):
        raise ForecastTournamentError("frozen forecast does not reconstruct from exact inputs")
    if frozen.q3_source_outcome_loaded or frozen.q3_evaluated:
        raise ForecastTournamentError("frozen 2026Q3 artifact unexpectedly contains outcome state")
    model = _candidate_from_frozen(
        frozen,
        content,
        input_cutoff=feature.source_available_at,
        feature_cutoff=feature.frozen_at,
        benchmark=False,
    )
    benchmark = _candidate_from_frozen(
        frozen,
        content,
        input_cutoff=feature.source_available_at,
        feature_cutoff=feature.frozen_at,
        benchmark=True,
    )
    candidates = tuple(sorted((model, benchmark), key=lambda item: item.candidate_id))
    # These remain valid frozen scientific forecasts, but the legacy artifact lacks an exact
    # training-cutoff timestamp required by this newer generic registration contract.
    tournament = ForecastTournament(
        tournament_id="skhynix_company_gp_2026q3_prospective_v1",
        captured_at=captured_at,
        candidates=candidates,
        comparable_candidate_ids=(),
        winner_candidate_id=None,
        outcome_scoring_available=False,
        blockers=(
            "authenticated_2026q3_outcome_unavailable",
            "candidate_training_cutoff_authority_unavailable",
            "insufficient_tournament_eligible_candidates",
        ),
    )
    opportunities = tuple(
        _opportunity(
            security_id=security,
            horizon_months=horizon,
            market_snapshot_id=market_snapshot_id,
            research_snapshot_id=research_snapshot_id,
            forecast_id=(tournament.snapshot_id if security == "000660" and horizon == 3 else None),
        )
        for security in SUPPORTED_SECURITIES
        for horizon in (3, 6, 12)
    )
    return ForecastOpportunityBundle(
        captured_at=captured_at,
        evaluation_date=evaluation_date,
        market_snapshot_id=market_snapshot_id,
        research_snapshot_id=research_snapshot_id,
        frozen_forecast_bytes_sha256=_digest(content),
        frozen_feature_bytes_sha256=_digest(feature_bytes),
        frozen_estimator_bytes_sha256=_digest(estimator_bytes),
        frozen_source_capture_bytes_sha256=_digest(capture_bytes),
        frozen_source_raw_bytes_sha256=_digest(raw_bytes),
        tournament=tournament,
        opportunities=opportunities,
    )


def persist_forecast_opportunity_bundle(
    bundle: ForecastOpportunityBundle,
    *,
    output_root: str | Path,
    frozen_forecast_path: str | Path,
    frozen_feature_path: str | Path = DEFAULT_FEATURE,
    selected_estimator_path: str | Path = DEFAULT_ESTIMATOR,
    source_capture_directory: str | Path = DEFAULT_SOURCE_CAPTURE_DIRECTORY,
) -> Path:
    """Rebuild from frozen upstream bytes before one immutable directory publication."""

    rebuilt = build_forecast_opportunity_bundle(
        frozen_forecast_path=frozen_forecast_path,
        captured_at=bundle.captured_at,
        evaluation_date=bundle.evaluation_date,
        market_snapshot_id=bundle.market_snapshot_id,
        research_snapshot_id=bundle.research_snapshot_id,
        frozen_feature_path=frozen_feature_path,
        selected_estimator_path=selected_estimator_path,
        source_capture_directory=source_capture_directory,
    )
    if _canonical(rebuilt.payload()) != _canonical(bundle.payload()):
        raise ForecastTournamentError("caller bundle differs from frozen upstream replay")
    root = _plain_repository(Path(output_root), create=True)
    name = (
        f"{bundle.captured_at.astimezone(UTC).strftime('%Y%m%dT%H%M%S%fZ')}"
        f"__{bundle.artifact_id[:12]}"
    )
    destination = root / name
    if destination.exists() or destination.is_symlink():
        replayed = replay_forecast_opportunity_bundle(
            destination,
            frozen_forecast_path=frozen_forecast_path,
            expected_artifact_id=bundle.artifact_id,
            frozen_feature_path=frozen_feature_path,
            selected_estimator_path=selected_estimator_path,
            source_capture_directory=source_capture_directory,
        )
        if _canonical(replayed.payload()) != _canonical(bundle.payload()):
            raise ForecastTournamentError("immutable bundle identity conflicts with content")
        return destination
    temporary = Path(tempfile.mkdtemp(prefix=f".{name}.", dir=root))
    try:
        payload_bytes = (json.dumps(bundle.payload(), indent=2, sort_keys=True) + "\n").encode()
        manifest = {
            "schema_version": SCHEMA_VERSION,
            "artifact_id": bundle.artifact_id,
            "files": {"bundle.json": _digest(payload_bytes)},
        }
        _write_new(temporary / "bundle.json", payload_bytes)
        _write_new(
            temporary / "manifest.json",
            (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode(),
        )
        _fsync_directory(temporary)
        os.rename(temporary, destination)
        _fsync_directory(root)
    finally:
        if temporary.exists():
            for child in temporary.iterdir():
                child.unlink()
            temporary.rmdir()
    return destination


def replay_forecast_opportunity_bundle(
    directory: str | Path,
    *,
    frozen_forecast_path: str | Path,
    expected_artifact_id: str | None = None,
    frozen_feature_path: str | Path = DEFAULT_FEATURE,
    selected_estimator_path: str | Path = DEFAULT_ESTIMATOR,
    source_capture_directory: str | Path = DEFAULT_SOURCE_CAPTURE_DIRECTORY,
) -> ForecastOpportunityBundle:
    root = _plain_directory(Path(directory))
    manifest_bytes = _read_plain(root / "manifest.json", root)
    bundle_bytes = _read_plain(root / "bundle.json", root)
    manifest = _object(_load_json(manifest_bytes, "manifest"), "manifest")
    _exact(manifest, {"schema_version", "artifact_id", "files"}, "manifest")
    if type(manifest["schema_version"]) is not int or manifest["schema_version"] != 1:
        raise ForecastTournamentError("unsupported bundle manifest schema")
    if manifest["files"] != {"bundle.json": _digest(bundle_bytes)}:
        raise ForecastTournamentError("bundle digest mismatch")
    payload = _object(_load_json(bundle_bytes, "bundle"), "bundle")
    _exact(
        payload,
        {
            "schema_version", "parser_id", "parser_version", "captured_at",
            "evaluation_date", "market_snapshot_id", "research_snapshot_id",
            "frozen_forecast_bytes_sha256", "frozen_feature_bytes_sha256",
            "frozen_estimator_bytes_sha256", "frozen_source_capture_bytes_sha256",
            "frozen_source_raw_bytes_sha256", "tournament", "opportunities",
            "missing_data_policy", "partial_ranking_available", "overall_ranking_available",
            "probabilities_available", "valuation_available", "price_implied_available",
            "scenario_payoff_available", "current_state_status", "stale_ready_state_allowed",
            "automatic_execution_enabled", "artifact_id",
        },
        "bundle",
    )
    artifact_id = str(payload["artifact_id"])
    if manifest["artifact_id"] != artifact_id:
        raise ForecastTournamentError("bundle manifest identity mismatch")
    if expected_artifact_id is not None and artifact_id != expected_artifact_id:
        raise ForecastTournamentError("unexpected bundle identity")
    rebuilt = build_forecast_opportunity_bundle(
        frozen_forecast_path=frozen_forecast_path,
        captured_at=datetime.fromisoformat(str(payload["captured_at"])),
        evaluation_date=date.fromisoformat(str(payload["evaluation_date"])),
        market_snapshot_id=str(payload["market_snapshot_id"]),
        research_snapshot_id=str(payload["research_snapshot_id"]),
        frozen_feature_path=frozen_feature_path,
        selected_estimator_path=selected_estimator_path,
        source_capture_directory=source_capture_directory,
    )
    if _canonical(rebuilt.payload()) != _canonical(payload):
        raise ForecastTournamentError("persisted bundle differs from frozen upstream replay")
    expected_name = (
        f"{rebuilt.captured_at.astimezone(UTC).strftime('%Y%m%dT%H%M%S%fZ')}"
        f"__{rebuilt.artifact_id[:12]}"
    )
    if root.name != expected_name:
        raise ForecastTournamentError("bundle directory identity mismatch")
    return rebuilt


def _candidate_from_frozen(
    frozen: LockedNumericForecast,
    content: bytes,
    *,
    input_cutoff: datetime,
    feature_cutoff: datetime,
    benchmark: bool,
) -> ProspectiveCandidate:
    candidate_id = frozen.benchmark_id if benchmark else frozen.selected_candidate_id
    value = (
        frozen.benchmark_forecast_krw_million
        if benchmark
        else frozen.selected_forecast_krw_million
    )
    model_version = (
        frozen.protocol_evidence_id
        if benchmark
        else frozen.selected_estimator_evidence_id
    )
    candidate_class = (
        CandidateClass.PREREGISTERED_BENCHMARK
        if benchmark
        else CandidateClass.INTERNAL_DETERMINISTIC_MODEL
    )
    return ProspectiveCandidate(
        candidate_id=candidate_id,
        candidate_class=candidate_class,
        security_id="000660",
        metric="company_gross_profit",
        target_period=frozen.target_period,
        horizon_semantics="next_reported_fiscal_quarter",
        model_identity=candidate_id,
        model_version_id=model_version,
        code_identity="sk_hynix_company_gp_ex_ante_2026q3_numeric_forecast:v1",
        source_artifact_id=frozen.evidence_id,
        source_bytes_sha256=_digest(content),
        input_artifact_ids=(
            frozen.contract_evidence_id,
            frozen.feature_vector_evidence_id,
            frozen.source_capture_evidence_id,
        ),
        input_cutoff=input_cutoff,
        feature_cutoff=feature_cutoff,
        training_cutoff=None,
        registered_at=frozen.forecast_locked_at,
        forecast_origin=frozen.forecast_origin,
        forecast_value=float(value),
        interval_lower=None,
        interval_upper=None,
        unit="KRW million",
        currency="KRW",
        accounting_basis="company_reported_gross_profit",
        transformation_semantics=(
            "lagged_company_gross_profit_persistence"
            if benchmark
            else "frozen_affine_ols_on_lagged_company_gross_profit"
        ),
        outcome_definition="SK hynix company gross profit for 2026Q3 from authenticated filing",
        scoring_rule="absolute_error_primary;signed_error_and_percentage_error_diagnostic",
        tournament_identity="skhynix_company_gp_2026q3_prospective_v1",
        selection_rule="minimum_historical_pit_mae_frozen_before_2026q3_outcome",
        lineage_ids=(frozen.evidence_id, frozen.protocol_evidence_id),
        tournament_eligible=benchmark,
        eligibility_blockers=(
            () if benchmark else ("exact_training_cutoff_timestamp_unavailable",)
        ),
    )


def _opportunity(
    *,
    security_id: str,
    horizon_months: int,
    market_snapshot_id: str,
    research_snapshot_id: str,
    forecast_id: str | None,
) -> HorizonOpportunity:
    dimensions = [
        OpportunityDimension(
            "actual_earnings_trajectory",
            EvidenceStatus.UNAVAILABLE,
            (research_snapshot_id,),
            "period_and_statement_basis_not_proven_for_opportunity_comparison",
        ),
        OpportunityDimension(
            "catalyst",
            EvidenceStatus.UNAVAILABLE,
            (),
            "dated_source_backed_horizon_catalyst_unavailable",
        ),
        OpportunityDimension(
            "estimate_revision",
            EvidenceStatus.NON_AUTHORITATIVE,
            (),
            "authoritative_estimate_revision_history_unavailable",
        ),
        OpportunityDimension(
            "market_state",
            EvidenceStatus.UNAVAILABLE,
            (market_snapshot_id,),
            "market_snapshot_bytes_not_replayed_at_opportunity_boundary",
        ),
        OpportunityDimension(
            "price_implied_expectation",
            EvidenceStatus.BLOCKED,
            (),
            "price_implied_requirement_authority_missing",
        ),
        OpportunityDimension(
            "prospective_forecast",
            EvidenceStatus.INCOMPARABLE if forecast_id else EvidenceStatus.UNAVAILABLE,
            (forecast_id,) if forecast_id else (),
            (
                "prospective_registration_contract_incomplete"
                if forecast_id
                else "comparable_prospective_forecast_unavailable"
            ),
        ),
        OpportunityDimension(
            "scenario_payoff",
            EvidenceStatus.BLOCKED,
            (),
            "scenario_input_authority_missing",
        ),
        OpportunityDimension(
            "valuation",
            EvidenceStatus.BLOCKED,
            (),
            "valuation_method_ineligible",
        ),
    ]
    supported = sum(item.status is EvidenceStatus.SUPPORTED for item in dimensions)
    blockers = tuple(sorted({item.blocker for item in dimensions if item.blocker is not None}))
    return HorizonOpportunity(
        security_id=security_id,
        horizon_months=horizon_months,
        horizon_trading_days={3: 63, 6: 126, 12: 252}[horizon_months],
        dimensions=tuple(sorted(dimensions, key=lambda item: item.name)),
        evidence_coverage=float(supported / len(dimensions)),
        partial_rank=None,
        overall_rank=None,
        blockers=blockers,
    )


def _alias(candidate: ProspectiveCandidate) -> str:
    return "".join(char for char in candidate.candidate_id.lower() if char.isalnum())


def _read_frozen_once(path: Path) -> bytes:
    trusted = _plain_file(path)
    with trusted.open("rb") as handle:
        opened = os.fstat(handle.fileno())
        content = handle.read()
    current = trusted.stat()
    if (
        trusted.is_symlink()
        or trusted.resolve() != trusted.absolute()
        or (opened.st_dev, opened.st_ino, opened.st_size, opened.st_mtime_ns)
        != (current.st_dev, current.st_ino, current.st_size, current.st_mtime_ns)
    ):
        raise ForecastTournamentError("frozen forecast changed during validated read")
    return content


def _load_frozen_from_exact_bytes(content: bytes) -> LockedNumericForecast:
    root = _object(_load_json(content, "frozen forecast"), "frozen forecast")
    _exact(root, {"schema_version", "status", "forecast"}, "frozen forecast")
    if type(root["schema_version"]) is not int or root["schema_version"] != 1:
        raise ForecastTournamentError("frozen forecast schema is noncanonical")
    body = _object(root["forecast"], "frozen forecast body")
    _exact(
        body,
        {
            "benchmark_forecast_krw_million", "benchmark_id", "contract_evidence_id",
            "evidence_id", "feature_values", "feature_vector_evidence_id",
            "forecast_locked_at", "forecast_origin", "historical_benchmark_mae_krw_million",
            "historical_selected_candidate_mae_krw_million", "numeric_forward_forecast_enabled",
            "prediction_interval", "predictors", "prospective_feature_vector_frozen",
            "prospective_forecast_run", "protocol_evidence_id", "q1_used_for_selection",
            "q3_evaluated", "q3_source_outcome_loaded", "q3_target_read",
            "raw_unit_coefficients", "raw_unit_intercept", "selected_candidate_id",
            "selected_estimator_evidence_id", "selected_forecast_krw_million",
            "source_capture_evidence_id", "standardized_input", "status", "target_period",
        },
        "frozen forecast body",
    )
    for field, expected in {
        "numeric_forward_forecast_enabled": True,
        "prospective_feature_vector_frozen": True,
        "prospective_forecast_run": True,
        "q1_used_for_selection": False,
        "q3_evaluated": False,
        "q3_source_outcome_loaded": False,
        "q3_target_read": False,
    }.items():
        if type(body[field]) is not bool or body[field] is not expected:
            raise ForecastTournamentError(f"frozen forecast boolean field drifted: {field}")
    numeric_fields = (
        "benchmark_forecast_krw_million",
        "historical_benchmark_mae_krw_million",
        "historical_selected_candidate_mae_krw_million",
        "raw_unit_intercept",
        "selected_forecast_krw_million",
    )
    if any(type(body[field]) is not float for field in numeric_fields):
        raise ForecastTournamentError("frozen forecast numerics must be canonical floats")
    for field in ("feature_values", "raw_unit_coefficients", "standardized_input"):
        values = body[field]
        if not isinstance(values, list) or any(type(value) is not float for value in values):
            raise ForecastTournamentError(f"frozen forecast array is noncanonical: {field}")
    if body["prediction_interval"] is not None:
        raise ForecastTournamentError("frozen forecast unexpectedly contains interval")
    with tempfile.TemporaryDirectory(prefix="alpha-cycle-frozen-replay-") as temporary:
        exact = Path(temporary) / "frozen.json"
        exact.write_bytes(content)
        return load_locked_numeric_forecast(exact)


def _load_exact_upstream_lineage(
    *,
    feature_path: Path,
    estimator_path: Path,
    source_capture_directory: Path,
) -> tuple[
    FrozenProspectiveFeatureVector,
    FrozenSelectedEstimatorFullFit,
    ProspectiveSourceCapture,
    bytes,
    bytes,
    bytes,
    bytes,
]:
    feature_bytes = _read_frozen_once(feature_path)
    estimator_bytes = _read_frozen_once(estimator_path)
    capture_root = _plain_directory(source_capture_directory)
    capture_bytes = _read_plain(capture_root / "capture.json", capture_root)
    raw_root = _plain_directory(capture_root / "raw")
    raw_bytes = _read_plain(raw_root / "2026Q2.json", raw_root)
    _load_json(raw_bytes, "raw OpenDART capture")
    _validate_upstream_schemas(feature_bytes, estimator_bytes, capture_bytes)
    with tempfile.TemporaryDirectory(prefix="alpha-cycle-lineage-replay-") as temporary:
        root = Path(temporary)
        feature_file = root / "feature.json"
        estimator_file = root / "estimator.json"
        capture_directory = root / "capture"
        raw_directory = capture_directory / "raw"
        raw_directory.mkdir(parents=True)
        feature_file.write_bytes(feature_bytes)
        estimator_file.write_bytes(estimator_bytes)
        (capture_directory / "capture.json").write_bytes(capture_bytes)
        (raw_directory / "2026Q2.json").write_bytes(raw_bytes)
        capture_pointer = _object(
            _load_json(capture_bytes, "source capture"), "source capture"
        )
        capture_pointer["artifact_directory"] = str(capture_directory)
        pointer = root / "capture-pointer.json"
        pointer.write_text(json.dumps(capture_pointer), encoding="utf-8")
        feature = load_prospective_feature_vector(feature_file)
        estimator = load_selected_estimator_artifact(estimator_file)
        capture, _ = load_prospective_source_capture(pointer)
    if (
        feature.source_captured_payload_bytes_sha256 != _digest(raw_bytes)
        or capture.captured_payload_bytes_sha256 != _digest(raw_bytes)
        or feature.source_raw_payload_sha256 != capture.raw_payload_sha256
    ):
        raise ForecastTournamentError("feature/source capture raw byte binding mismatch")
    return (
        feature,
        estimator,
        capture,
        feature_bytes,
        estimator_bytes,
        capture_bytes,
        raw_bytes,
    )


def _validate_upstream_schemas(
    feature_bytes: bytes, estimator_bytes: bytes, capture_bytes: bytes
) -> None:
    feature_root = _object(_load_json(feature_bytes, "feature"), "feature")
    _exact(feature_root, {"schema_version", "status", "feature_vector"}, "feature")
    if type(feature_root["schema_version"]) is not int or feature_root["schema_version"] != 1:
        raise ForecastTournamentError("feature schema version is noncanonical")
    feature = _object(feature_root["feature_vector"], "feature body")
    _exact(
        feature,
        {
            "contract_evidence_id", "evidence_id", "feature_values", "forecast_origin",
            "frozen_at", "historical_execution_evidence_id", "numeric_forward_forecast_enabled",
            "predictors", "prospective_feature_vector_frozen", "prospective_forecast_run",
            "protocol_evidence_id", "q1_used_for_selection", "q3_evaluated",
            "q3_source_outcome_loaded", "q3_target_read", "selected_estimator_evidence_id",
            "source_available_at", "source_capture_evidence_id",
            "source_captured_payload_bytes_sha256", "source_period", "source_raw_payload_sha256",
            "source_receipt_date", "source_receipt_no", "status", "target_period",
        },
        "feature body",
    )
    _exact_booleans(
        feature,
        {
            "numeric_forward_forecast_enabled": False,
            "prospective_feature_vector_frozen": True,
            "prospective_forecast_run": False,
            "q1_used_for_selection": False,
            "q3_evaluated": False,
            "q3_source_outcome_loaded": False,
            "q3_target_read": False,
        },
        "feature",
    )
    if not isinstance(feature["feature_values"], list) or any(
        type(value) is not float for value in feature["feature_values"]
    ):
        raise ForecastTournamentError("feature values must be canonical floats")
    estimator_root = _object(_load_json(estimator_bytes, "estimator"), "estimator")
    _exact(
        estimator_root, {"schema_version", "status", "selected_estimator"}, "estimator"
    )
    if (
        type(estimator_root["schema_version"]) is not int
        or estimator_root["schema_version"] != 1
    ):
        raise ForecastTournamentError("estimator schema version is noncanonical")
    estimator = _object(estimator_root["selected_estimator"], "estimator body")
    _exact(
        estimator,
        {
            "backtest_evidence_id", "combined_bundle_evidence_id", "condition_number",
            "contract_evidence_id", "design_rank", "estimator", "estimator_freeze_evidence_id",
            "evidence_id", "execution_evidence_id", "historical_benchmark_mae_krw_million",
            "historical_relative_mae_improvement", "historical_selected_candidate_mae_krw_million",
            "numeric_forward_forecast_enabled", "parameter_count", "predictor_means",
            "predictor_scales", "predictors", "prospective_feature_vector_frozen",
            "prospective_forecast_run", "q1_used_for_selection", "q3_evaluated",
            "q3_source_outcome_loaded", "q3_target_read", "raw_target_capture_evidence_id",
            "raw_unit_coefficients", "raw_unit_intercept", "residual_degrees_of_freedom",
            "scaling_ddof", "scope_evidence_id", "selected_candidate_id",
            "standardized_coefficients", "status", "target_join_evidence_id",
            "target_source_evidence_id", "training_mae_krw_million", "training_periods",
            "training_rmse_krw_million", "training_row_count",
        },
        "estimator body",
    )
    _exact_booleans(
        estimator,
        {
            "numeric_forward_forecast_enabled": False,
            "prospective_feature_vector_frozen": False,
            "prospective_forecast_run": False,
            "q1_used_for_selection": False,
            "q3_evaluated": False,
            "q3_source_outcome_loaded": False,
            "q3_target_read": False,
        },
        "estimator",
    )
    for field in (
        "design_rank",
        "parameter_count",
        "residual_degrees_of_freedom",
        "scaling_ddof",
        "training_row_count",
    ):
        if type(estimator[field]) is not int:
            raise ForecastTournamentError(f"estimator integer field is noncanonical: {field}")
    capture_root = _object(_load_json(capture_bytes, "source capture"), "source capture")
    _exact(capture_root, {"schema_version", "status", "capture"}, "source capture")
    if type(capture_root["schema_version"]) is not int or capture_root["schema_version"] != 1:
        raise ForecastTournamentError("source capture schema version is noncanonical")
    capture = _object(capture_root["capture"], "source capture body")
    _exact(
        capture,
        {
            "captured_at", "captured_payload_bytes_sha256", "contract_evidence_id",
            "evidence_id", "forecast_origin", "historical_execution_evidence_id",
            "raw_payload_sha256", "source_period", "status", "target_period",
        },
        "source capture body",
    )


def _exact_booleans(
    value: dict[str, object], expected: dict[str, bool], field: str
) -> None:
    for name, expected_value in expected.items():
        if type(value[name]) is not bool or value[name] is not expected_value:
            raise ForecastTournamentError(f"{field} boolean field drifted: {name}")


def _plain_file(path: Path) -> Path:
    if path.is_symlink() or not path.is_file() or path.resolve() != path.absolute():
        raise ForecastTournamentError("frozen forecast must be a plain immutable file path")
    return path.resolve()


def _plain_repository(path: Path, *, create: bool) -> Path:
    lexical = path.absolute()
    existing = lexical
    while not existing.exists() and not existing.is_symlink():
        if existing.parent == existing:
            raise ForecastTournamentError("repository has no trusted ancestor")
        existing = existing.parent
    if existing.is_symlink() or not existing.is_dir() or existing.resolve() != existing.absolute():
        raise ForecastTournamentError("repository ancestor contains an alias")
    if not path.exists() and create:
        path.mkdir(parents=True)
    if path.is_symlink() or not path.is_dir() or path.resolve() != lexical:
        raise ForecastTournamentError("repository must be a plain directory")
    return path.resolve()


def _plain_directory(path: Path) -> Path:
    if path.is_symlink() or not path.is_dir() or path.resolve() != path.absolute():
        raise ForecastTournamentError("artifact directory contains an alias")
    return path.resolve()


def _read_plain(path: Path, root: Path) -> bytes:
    if path.is_symlink() or not path.is_file() or path.resolve().parent != root:
        raise ForecastTournamentError("artifact file escapes its directory")
    return path.read_bytes()


def _write_new(path: Path, content: bytes) -> None:
    with path.open("xb") as handle:
        handle.write(content)
        handle.flush()
        os.fsync(handle.fileno())


def _fsync_directory(path: Path) -> None:
    if os.name != "posix":
        return
    descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _load_json(content: bytes, field: str) -> object:
    def unique(pairs: list[tuple[str, object]]) -> dict[str, object]:
        result: dict[str, object] = {}
        for key, value in pairs:
            if key in result:
                raise ForecastTournamentError(f"{field} contains duplicate JSON key {key!r}")
            result[key] = value
        return result

    try:
        return json.loads(content.decode("utf-8"), object_pairs_hook=unique)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ForecastTournamentError(f"{field} is malformed UTF-8/JSON") from exc


def _object(value: object, field: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise ForecastTournamentError(f"{field} must be an object")
    return {str(key): item for key, item in value.items()}


def _exact(value: dict[str, object], expected: set[str], field: str) -> None:
    if set(value) != expected:
        raise ForecastTournamentError(f"{field} fields differ from canonical schema")


def _text(value: str, field: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ForecastTournamentError(f"{field} must be non-empty text")


def _aware(value: datetime, field: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ForecastTournamentError(f"{field} must be timezone-aware")


def _sha_text(value: str, field: str) -> None:
    if len(value) != 64 or any(char not in "0123456789abcdef" for char in value):
        raise ForecastTournamentError(f"{field} must be a lowercase SHA-256")


def _sha_tuple(values: tuple[str, ...], field: str) -> None:
    for value in values:
        _sha_text(value, field)
    if len(values) != len(set(values)):
        raise ForecastTournamentError(f"{field} cannot contain duplicates")


def _canonical(value: object) -> bytes:
    return json.dumps(
        value, allow_nan=False, ensure_ascii=False, separators=(",", ":"), sort_keys=True
    ).encode()


def _digest(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


__all__ = [
    "CandidateClass",
    "EvidenceStatus",
    "ForecastOpportunityBundle",
    "ForecastTournament",
    "ForecastTournamentError",
    "HorizonOpportunity",
    "OpportunityDimension",
    "ProspectiveCandidate",
    "build_forecast_opportunity_bundle",
    "persist_forecast_opportunity_bundle",
    "replay_forecast_opportunity_bundle",
]
