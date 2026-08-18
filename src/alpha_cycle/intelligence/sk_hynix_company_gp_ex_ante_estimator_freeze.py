"""Target-blind estimator freeze and sample preflight for SK hynix ex-ante GP research.

This module cannot load company-GP targets. It binds a preregistered candidate set and checks
whether the PIT feature panel is large enough to run the frozen chronological comparison.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import cast

import yaml

from alpha_cycle.intelligence.sk_hynix_company_gp_ex_ante_feature_frontier import (
    ExAnteFeatureFrontier,
)
from alpha_cycle.intelligence.sk_hynix_company_gp_ex_ante_pit import (
    PointInTimeFeatureBundle,
    audit_point_in_time_feature_bundle,
)
from alpha_cycle.intelligence.sk_hynix_company_gp_ex_ante_protocol import (
    FrozenCompanyGPExAnteProtocol,
)

DEFAULT_COMPANY_GP_EX_ANTE_ESTIMATOR_FREEZE = Path(
    "config/skhynix_company_gp_ex_ante_estimator_freeze.v1.yaml"
)
_EXPECTED_FEATURES = (
    "lagged_company_revenue",
    "lagged_company_gross_profit",
    "lagged_company_gross_margin",
    "lagged_nand_revenue_share",
    "lagged_other_revenue_share",
)
_EXPECTED_CANDIDATES = (
    "lagged_gp_affine_ols",
    "lagged_gp_nand_mix_ols",
    "lagged_gp_full_mix_ols",
)


def _mapping(value: object, label: str) -> dict[object, object]:
    if not isinstance(value, dict):
        raise ValueError(f"Ex-ante estimator freeze {label} must be an object")
    return cast(dict[object, object], value)


def _list(value: object, label: str) -> list[object]:
    if not isinstance(value, list):
        raise ValueError(f"Ex-ante estimator freeze {label} must be an array")
    return value


def _sha(payload: object) -> str:
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _heuristic_training_rows(parameter_count: int) -> int:
    return max(2 * parameter_count, parameter_count + 8)


@dataclass(frozen=True)
class FrozenExAnteEstimatorCandidate:
    candidate_id: str
    architecture: str
    estimator: str
    parameter_count: int
    predictors: tuple[str, ...]
    minimum_training_rows: int
    required_total_rows_for_eight_folds_if_scored_alone: int

    def __post_init__(self) -> None:
        if self.candidate_id not in _EXPECTED_CANDIDATES:
            raise ValueError("Ex-ante estimator candidate id drifted")
        if self.architecture != "direct_company_gp_from_pit_features":
            raise ValueError("Ex-ante estimator candidate architecture drifted")
        if self.estimator != "ordinary_least_squares":
            raise ValueError("Ex-ante estimator candidate estimator drifted")
        if self.parameter_count != len(self.predictors) + 1:
            raise ValueError("Ex-ante estimator parameter count must include intercept")
        expected_minimum = _heuristic_training_rows(self.parameter_count)
        if self.minimum_training_rows != expected_minimum:
            raise ValueError("Ex-ante estimator heuristic training floor drifted")
        expected_total = expected_minimum + 8
        if self.required_total_rows_for_eight_folds_if_scored_alone != expected_total:
            raise ValueError("Ex-ante estimator standalone panel requirement drifted")
        if not set(self.predictors).issubset(_EXPECTED_FEATURES):
            raise ValueError("Ex-ante estimator candidate uses a non-frozen feature")


@dataclass(frozen=True)
class FrozenExAnteEstimatorSelection:
    evidence_id: str
    freeze_id: str
    freeze_version: str
    status: str
    ticker: str
    target_metric: str
    protocol_path: str
    pit_certification_contract_path: str
    certified_base_target_rows: int
    certified_base_feature_observations: int
    feature_ids: tuple[str, ...]
    benchmark_id: str
    benchmark_prediction_rule: str
    candidates: tuple[FrozenExAnteEstimatorCandidate, ...]
    minimum_scored_folds: int
    shared_initial_training_rows: int
    required_rows_before_first_target_join: int
    parameter_count_includes_intercept: bool
    heuristic_is_statistical_theorem: bool
    require_every_candidate_sample_eligible: bool
    random_cross_validation_allowed: bool
    candidate_must_strictly_beat_benchmark: bool
    hyperparameter_tuning_allowed: bool
    candidate_addition_after_first_target_join_allowed: bool
    feature_subset_change_after_first_target_join_allowed: bool
    target_join_allowed_now: bool
    estimator_fit_allowed_now: bool
    first_pit_backtest_run: bool
    final_estimator_selected: bool
    q3_target_read: bool
    q3_source_outcome_loaded: bool
    numeric_forward_forecast_enabled: bool

    def __post_init__(self) -> None:
        if len(self.evidence_id) != 64:
            raise ValueError("Ex-ante estimator freeze evidence id must be SHA-256")
        if self.freeze_id != "skhynix_company_gp_ex_ante_estimator_selection":
            raise ValueError("Ex-ante estimator freeze id drifted")
        frozen = self.freeze_version == "1.0-frozen-pre-target-join"
        if not frozen or self.status != "frozen_pre_target_join":
            raise ValueError("Ex-ante estimator selection is not frozen pre-target-join")
        if self.ticker != "000660":
            raise ValueError("Ex-ante estimator ticker drifted")
        if self.target_metric != "company_gross_profit_krw_million":
            raise ValueError("Ex-ante estimator target drifted")
        expected_protocol = "config/skhynix_company_gp_ex_ante_forecast_protocol.v1.yaml"
        if self.protocol_path != expected_protocol:
            raise ValueError("Ex-ante estimator protocol path drifted")
        expected_pit = (
            "config/skhynix_company_gp_ex_ante_lagged_filing_certification.v1.yaml"
        )
        if self.pit_certification_contract_path != expected_pit:
            raise ValueError("Ex-ante estimator PIT certification path drifted")
        if self.certified_base_target_rows != 14:
            raise ValueError("Ex-ante estimator certified base row count drifted")
        if self.certified_base_feature_observations != 70:
            raise ValueError("Ex-ante estimator certified feature count drifted")
        if self.feature_ids != _EXPECTED_FEATURES:
            raise ValueError("Ex-ante estimator feature schema drifted")
        expected_benchmark = "previous_reported_quarter_gross_profit_persistence"
        if self.benchmark_id != expected_benchmark:
            raise ValueError("Ex-ante estimator benchmark drifted")
        if self.benchmark_prediction_rule != "lagged_company_gross_profit":
            raise ValueError("Ex-ante estimator benchmark prediction rule drifted")
        candidate_ids = tuple(item.candidate_id for item in self.candidates)
        if candidate_ids != _EXPECTED_CANDIDATES:
            raise ValueError("Ex-ante estimator candidate order drifted")
        if self.minimum_scored_folds != 8:
            raise ValueError("Ex-ante estimator scored-fold count drifted")
        if self.shared_initial_training_rows != 12:
            raise ValueError("Ex-ante estimator initial training size drifted")
        if self.required_rows_before_first_target_join != 20:
            raise ValueError("Ex-ante estimator first-target-join row floor drifted")
        maximum_candidate_floor = max(
            item.minimum_training_rows for item in self.candidates
        )
        if self.shared_initial_training_rows != maximum_candidate_floor:
            raise ValueError("Ex-ante estimator shared training floor is inconsistent")
        required = self.shared_initial_training_rows + self.minimum_scored_folds
        if self.required_rows_before_first_target_join != required:
            raise ValueError("Ex-ante estimator panel requirement is inconsistent")
        if not self.parameter_count_includes_intercept:
            raise ValueError("Ex-ante estimator p must include the intercept")
        if self.heuristic_is_statistical_theorem:
            raise ValueError("Ex-ante estimator sample heuristic cannot be a theorem")
        if not self.require_every_candidate_sample_eligible:
            raise ValueError("Ex-ante estimator must preserve all candidates before join")
        if self.random_cross_validation_allowed:
            raise ValueError("Ex-ante estimator cannot use random CV")
        if not self.candidate_must_strictly_beat_benchmark:
            raise ValueError("Ex-ante estimator must strictly beat the benchmark")
        prohibited = (
            self.hyperparameter_tuning_allowed,
            self.candidate_addition_after_first_target_join_allowed,
            self.feature_subset_change_after_first_target_join_allowed,
            self.target_join_allowed_now,
            self.estimator_fit_allowed_now,
            self.first_pit_backtest_run,
            self.final_estimator_selected,
            self.q3_target_read,
            self.q3_source_outcome_loaded,
            self.numeric_forward_forecast_enabled,
        )
        if any(prohibited):
            raise ValueError("Ex-ante estimator freeze opened prohibited scope")


@dataclass(frozen=True)
class ExAnteEstimatorCandidatePreflight:
    candidate_id: str
    parameter_count: int
    minimum_training_rows: int
    required_total_rows_for_eight_folds_if_scored_alone: int
    current_panel_rows: int
    individually_sample_eligible_now: bool


@dataclass(frozen=True)
class ExAnteEstimatorFreezePreflight:
    freeze_evidence_id: str
    bundle_evidence_id: str
    current_target_blind_feature_rows: int
    current_feature_observation_count: int
    expected_features_per_row: int
    all_rows_have_exact_frozen_feature_set: bool
    all_observations_point_in_time_eligible: bool
    rejected_observation_count: int
    shared_initial_training_rows: int
    minimum_scored_folds: int
    shared_scored_folds_available_now: int
    required_rows_before_first_target_join: int
    row_shortfall_before_first_target_join: int
    candidates: tuple[ExAnteEstimatorCandidatePreflight, ...]
    all_frozen_candidates_sample_eligible_now: bool
    target_join_authorized: bool = False
    estimator_fit_authorized: bool = False
    historical_backtest_run: bool = False
    q3_target_read: bool = False
    q3_source_outcome_loaded: bool = False

    def __post_init__(self) -> None:
        opened = (
            self.target_join_authorized,
            self.estimator_fit_authorized,
            self.historical_backtest_run,
        )
        if any(opened):
            raise ValueError("Estimator preflight cannot authorize target access or fitting")
        if self.q3_target_read or self.q3_source_outcome_loaded:
            raise ValueError("Estimator preflight cannot open protected Q3 state")


def load_frozen_ex_ante_estimator_selection(
    path: str | Path = DEFAULT_COMPANY_GP_EX_ANTE_ESTIMATOR_FREEZE,
) -> FrozenExAnteEstimatorSelection:
    with Path(path).open(encoding="utf-8") as handle:
        raw: object = yaml.safe_load(handle)
    root = _mapping(raw, "manifest")
    if root.get("schema_version") != 1:
        raise ValueError("Ex-ante estimator freeze schema is invalid")
    body = _mapping(root.get("freeze"), "body")
    freeze_state = _mapping(body.get("freeze_state"), "freeze_state")
    base = _mapping(body.get("certified_base_panel"), "certified_base_panel")
    benchmark = _mapping(body.get("benchmark"), "benchmark")
    sample = _mapping(body.get("sample_adequacy"), "sample_adequacy")
    selection = _mapping(body.get("chronological_selection"), "chronological_selection")
    trust = _mapping(body.get("trust_boundary"), "trust_boundary")

    feature_ids = tuple(
        str(item) for item in _list(base.get("feature_ids"), "feature_ids")
    )
    candidates: list[FrozenExAnteEstimatorCandidate] = []
    for raw_candidate in _list(body.get("candidates"), "candidates"):
        candidate = _mapping(raw_candidate, "candidate")
        predictors = tuple(
            str(item)
            for item in _list(candidate.get("predictors"), "candidate.predictors")
        )
        candidates.append(
            FrozenExAnteEstimatorCandidate(
                candidate_id=str(candidate.get("candidate_id", "")),
                architecture=str(candidate.get("architecture", "")),
                estimator=str(candidate.get("estimator", "")),
                parameter_count=int(str(candidate.get("parameter_count", -1))),
                predictors=predictors,
                minimum_training_rows=int(
                    str(
                        candidate.get(
                            "candidate_minimum_training_rows_from_heuristic",
                            -1,
                        )
                    )
                ),
                required_total_rows_for_eight_folds_if_scored_alone=int(
                    str(
                        candidate.get(
                            "required_total_rows_for_eight_folds_if_scored_alone",
                            -1,
                        )
                    )
                ),
            )
        )

    target_blind_keys = (
        "historical_target_values_read_for_this_freeze",
        "historical_target_join_run",
        "historical_backtest_run",
        "2026q1_used_for_selection",
        "2026q3_target_read",
        "2026q3_source_outcome_loaded",
        "2026q3_evaluated",
    )
    if any(freeze_state.get(key) is True for key in target_blind_keys):
        raise ValueError("Ex-ante estimator freeze was not target-blind")

    stable = {"schema_version": root["schema_version"], "freeze": body}
    return FrozenExAnteEstimatorSelection(
        evidence_id=_sha(stable),
        freeze_id=str(body.get("freeze_id", "")),
        freeze_version=str(body.get("freeze_version", "")),
        status=str(body.get("status", "")),
        ticker=str(body.get("ticker", "")).zfill(6),
        target_metric=str(body.get("target_metric", "")),
        protocol_path=str(body.get("protocol_path", "")),
        pit_certification_contract_path=str(
            body.get("pit_certification_contract_path", "")
        ),
        certified_base_target_rows=int(str(base.get("target_row_count", -1))),
        certified_base_feature_observations=int(
            str(base.get("feature_observation_count", -1))
        ),
        feature_ids=feature_ids,
        benchmark_id=str(benchmark.get("benchmark_id", "")),
        benchmark_prediction_rule=str(benchmark.get("prediction_rule", "")),
        candidates=tuple(candidates),
        minimum_scored_folds=int(str(sample.get("minimum_scored_folds", -1))),
        shared_initial_training_rows=int(
            str(sample.get("shared_initial_training_rows", -1))
        ),
        required_rows_before_first_target_join=int(
            str(
                sample.get(
                    "required_complete_target_rows_before_first_target_join",
                    -1,
                )
            )
        ),
        parameter_count_includes_intercept=(
            sample.get("parameter_count_includes_intercept") is True
        ),
        heuristic_is_statistical_theorem=(
            sample.get("heuristic_is_statistical_theorem") is True
        ),
        require_every_candidate_sample_eligible=(
            sample.get(
                "require_every_frozen_candidate_sample_eligible_before_first_target_join"
            )
            is True
        ),
        random_cross_validation_allowed=(
            selection.get("random_cross_validation_allowed") is True
        ),
        candidate_must_strictly_beat_benchmark=(
            selection.get("candidate_must_strictly_beat_benchmark") is True
        ),
        hyperparameter_tuning_allowed=(
            selection.get("hyperparameter_tuning_allowed") is True
        ),
        candidate_addition_after_first_target_join_allowed=(
            selection.get("candidate_addition_after_first_target_join_allowed") is True
        ),
        feature_subset_change_after_first_target_join_allowed=(
            selection.get("feature_subset_change_after_first_target_join_allowed") is True
        ),
        target_join_allowed_now=trust.get("target_join_allowed_now") is True,
        estimator_fit_allowed_now=trust.get("estimator_fit_allowed_now") is True,
        first_pit_backtest_run=trust.get("first_pit_backtest_run") is True,
        final_estimator_selected=trust.get("final_estimator_selected") is True,
        q3_target_read=trust.get("2026q3_target_read") is True,
        q3_source_outcome_loaded=(
            trust.get("2026q3_source_outcome_loaded") is True
        ),
        numeric_forward_forecast_enabled=(
            trust.get("numeric_forward_forecast_enabled") is True
        ),
    )


def build_ex_ante_estimator_freeze_preflight(
    freeze: FrozenExAnteEstimatorSelection,
    protocol: FrozenCompanyGPExAnteProtocol,
    frontier: ExAnteFeatureFrontier,
    bundle: PointInTimeFeatureBundle,
) -> ExAnteEstimatorFreezePreflight:
    """Inspect sample feasibility without loading any target values."""

    audit = audit_point_in_time_feature_bundle(protocol, frontier, bundle)
    rows: dict[str, set[str]] = {}
    for observation in bundle.observations:
        rows.setdefault(observation.period_id, set()).add(observation.feature_id)

    expected = set(freeze.feature_ids)
    exact = bool(rows) and all(
        feature_ids == expected for feature_ids in rows.values()
    )
    row_count = len(rows)
    candidate_preflight = tuple(
        ExAnteEstimatorCandidatePreflight(
            candidate_id=item.candidate_id,
            parameter_count=item.parameter_count,
            minimum_training_rows=item.minimum_training_rows,
            required_total_rows_for_eight_folds_if_scored_alone=(
                item.required_total_rows_for_eight_folds_if_scored_alone
            ),
            current_panel_rows=row_count,
            individually_sample_eligible_now=(
                row_count >= item.required_total_rows_for_eight_folds_if_scored_alone
            ),
        )
        for item in freeze.candidates
    )
    shared_folds = max(0, row_count - freeze.shared_initial_training_rows)
    all_candidate_ready = all(
        item.individually_sample_eligible_now for item in candidate_preflight
    )
    return ExAnteEstimatorFreezePreflight(
        freeze_evidence_id=freeze.evidence_id,
        bundle_evidence_id=bundle.evidence_id,
        current_target_blind_feature_rows=row_count,
        current_feature_observation_count=len(bundle.observations),
        expected_features_per_row=len(freeze.feature_ids),
        all_rows_have_exact_frozen_feature_set=exact,
        all_observations_point_in_time_eligible=(
            audit.all_observations_point_in_time_eligible
        ),
        rejected_observation_count=audit.rejected_observation_count,
        shared_initial_training_rows=freeze.shared_initial_training_rows,
        minimum_scored_folds=freeze.minimum_scored_folds,
        shared_scored_folds_available_now=shared_folds,
        required_rows_before_first_target_join=(
            freeze.required_rows_before_first_target_join
        ),
        row_shortfall_before_first_target_join=max(
            0,
            freeze.required_rows_before_first_target_join - row_count,
        ),
        candidates=candidate_preflight,
        all_frozen_candidates_sample_eligible_now=all_candidate_ready,
    )


__all__ = [
    "DEFAULT_COMPANY_GP_EX_ANTE_ESTIMATOR_FREEZE",
    "ExAnteEstimatorCandidatePreflight",
    "ExAnteEstimatorFreezePreflight",
    "FrozenExAnteEstimatorCandidate",
    "FrozenExAnteEstimatorSelection",
    "build_ex_ante_estimator_freeze_preflight",
    "load_frozen_ex_ante_estimator_selection",
]
