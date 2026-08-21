"""Freeze the historically selected SK hynix GP estimator on all twenty locked rows.

This stage runs only after the preregistered chronological comparison has selected a
candidate. It does not reopen candidate choice, features, folds, benchmark, or tuning.
It deterministically refits the already-selected OLS architecture on the exact twenty
locked historical rows and persists coefficients plus scaling statistics as immutable
evidence. Protected 2026Q3 inputs/outcomes are not accessed here.
"""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass, replace
from pathlib import Path
from typing import cast

import numpy as np
import yaml

from alpha_cycle.intelligence.sk_hynix_company_gp_ex_ante_estimator_freeze import (
    FrozenExAnteEstimatorCandidate,
    load_frozen_ex_ante_estimator_selection,
)
from alpha_cycle.intelligence.sk_hynix_company_gp_ex_ante_historical_evaluation import (
    HistoricalBacktestResult,
    HistoricalTargetJoin,
    load_historical_target_join,
    run_frozen_historical_backtest,
)
from alpha_cycle.intelligence.sk_hynix_company_gp_ex_ante_historical_evaluation_v2 import (
    load_frozen_historical_schema_repair_v2,
    load_historical_raw_target_capture,
)
from alpha_cycle.intelligence.sk_hynix_company_gp_ex_ante_scope_freeze import (
    load_frozen_exact_twenty_period_ex_ante_scope,
)

DEFAULT_SELECTED_ESTIMATOR_FULL_FIT_CONTRACT = Path(
    "config/skhynix_company_gp_ex_ante_selected_estimator_full_fit.v1.yaml"
)
DEFAULT_SELECTED_ESTIMATOR_OUTPUT = Path(
    "data/private/research/skhynix-company-gp-ex-ante-selected-estimator"
)
DEFAULT_SELECTED_ESTIMATOR_POINTER = (
    DEFAULT_SELECTED_ESTIMATOR_OUTPUT / "latest_selected_estimator.json"
)
_STATUS = "skhynix_ex_ante_selected_estimator_full_twenty_row_fit_frozen"
_EXPECTED_PERIODS = tuple(
    f"{year}Q{quarter}" for year in range(2016, 2026) for quarter in (2, 3)
)
_BACKTEST_STATUS = "skhynix_ex_ante_first_chronological_historical_backtest_complete"


def _mapping(value: object, label: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be an object")
    return {str(key): item for key, item in cast(dict[object, object], value).items()}


def _array(value: object, label: str) -> list[object]:
    if not isinstance(value, list):
        raise ValueError(f"{label} must be an array")
    return value


def _canonical_bytes(payload: object) -> bytes:
    return json.dumps(
        payload,
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
        default=str,
    ).encode("utf-8")


def _sha(payload: object) -> str:
    return hashlib.sha256(
        json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        ).encode("utf-8")
    ).hexdigest()


def _valid_sha(value: str) -> bool:
    return len(value) == 64 and all(char in "0123456789abcdef" for char in value)


@dataclass(frozen=True)
class SelectedEstimatorFullFitContract:
    evidence_id: str
    freeze_version: str
    status: str
    execution_path: str
    scope_path: str
    estimator_freeze_path: str
    target_join_path: str
    backtest_path: str
    raw_capture_path: str
    training_rows: int
    scaling_ddof: int

    def __post_init__(self) -> None:
        if not _valid_sha(self.evidence_id):
            raise ValueError("Selected-estimator contract evidence id must be SHA-256")
        expected_version = "1.0-post-historical-selection-deterministic-full-fit"
        if self.freeze_version != expected_version:
            raise ValueError("Selected-estimator full-fit contract version drifted")
        expected_status = "frozen_post_historical_selection_before_prospective_forecast"
        if self.status != expected_status:
            raise ValueError("Selected-estimator full-fit contract status drifted")
        if self.training_rows != 20 or self.scaling_ddof != 0:
            raise ValueError("Selected-estimator full-fit geometry drifted")


def load_selected_estimator_full_fit_contract(
    path: str | Path = DEFAULT_SELECTED_ESTIMATOR_FULL_FIT_CONTRACT,
) -> SelectedEstimatorFullFitContract:
    with Path(path).open(encoding="utf-8") as handle:
        raw: object = yaml.safe_load(handle)
    root = _mapping(raw, "Selected-estimator full-fit manifest")
    if root.get("schema_version") != 1:
        raise ValueError("Selected-estimator full-fit schema is invalid")
    body = _mapping(root.get("freeze"), "Selected-estimator full-fit body")
    if body.get("freeze_id") != "skhynix_company_gp_ex_ante_selected_estimator_full_fit":
        raise ValueError("Selected-estimator full-fit freeze id drifted")
    if str(body.get("ticker", "")).zfill(6) != "000660":
        raise ValueError("Selected-estimator full-fit ticker drifted")
    if body.get("target_metric") != "company_gross_profit_krw_million":
        raise ValueError("Selected-estimator full-fit target drifted")

    inputs = _mapping(body.get("locked_inputs"), "Selected-estimator locked inputs")
    inheritance = _mapping(
        body.get("selected_estimator_inheritance"),
        "Selected-estimator inheritance",
    )
    deterministic = _mapping(
        body.get("deterministic_full_fit"),
        "Selected-estimator deterministic full fit",
    )
    protected = _mapping(
        body.get("protected_prospective_boundary"),
        "Selected-estimator protected boundary",
    )

    if inheritance.get("selected_candidate_source") != (
        "frozen_historical_backtest_selected_candidate_id"
    ):
        raise ValueError("Selected-estimator candidate inheritance drifted")
    if inheritance.get("candidate_definition_source") != "pre_target_estimator_freeze":
        raise ValueError("Selected-estimator candidate definition source drifted")
    prohibited_inheritance = (
        "new_candidate_allowed",
        "predictor_change_allowed",
        "feature_addition_allowed",
        "hyperparameter_tuning_allowed",
        "benchmark_reselection_allowed",
        "fold_reselection_allowed",
    )
    if any(inheritance.get(key) is not False for key in prohibited_inheritance):
        raise ValueError("Selected-estimator contract reopened historical model choice")

    expected_fit = {
        "training_rows": 20,
        "training_period_source": "exact_frozen_historical_target_join_order",
        "estimator": "ordinary_least_squares",
        "include_intercept": True,
        "fit_predictor_center_and_scale_on_all_twenty_training_rows": True,
        "scaling_standard_deviation_ddof": 0,
        "target_standardization_allowed": False,
        "require_full_column_rank": True,
        "require_positive_residual_degrees_of_freedom": True,
        "condition_number_role": "report_only",
        "training_error_metrics_role": "report_only",
        "coefficient_stability_role": "historical_backtest_report_only",
    }
    for key, expected in expected_fit.items():
        if deterministic.get(key) != expected:
            raise ValueError(f"Selected-estimator deterministic fit field drifted: {key}")

    protected_false = (
        "prospective_feature_vector_frozen",
        "prospective_forecast_run",
        "2026q1_used_for_selection",
        "2026q3_target_read",
        "2026q3_source_outcome_loaded",
        "2026q3_evaluated",
        "numeric_forward_forecast_enabled",
        "fair_value_estimate_enabled",
        "target_price_enabled",
        "decision_score_enabled",
        "investment_action_enabled",
    )
    if any(protected.get(key) is not False for key in protected_false):
        raise ValueError("Selected-estimator contract opened prospective state")

    stable = {"schema_version": 1, "freeze": body}
    return SelectedEstimatorFullFitContract(
        evidence_id=_sha(stable),
        freeze_version=str(body.get("freeze_version", "")),
        status=str(body.get("status", "")),
        execution_path=str(inputs.get("historical_execution_v2_path", "")),
        scope_path=str(inputs.get("scope_freeze_path", "")),
        estimator_freeze_path=str(inputs.get("estimator_freeze_path", "")),
        target_join_path=str(inputs.get("historical_target_join_path", "")),
        backtest_path=str(inputs.get("historical_backtest_path", "")),
        raw_capture_path=str(inputs.get("historical_raw_target_capture_path", "")),
        training_rows=int(str(deterministic.get("training_rows", -1))),
        scaling_ddof=int(
            str(deterministic.get("scaling_standard_deviation_ddof", -1))
        ),
    )


@dataclass(frozen=True)
class FrozenSelectedEstimatorFullFit:
    evidence_id: str
    contract_evidence_id: str
    execution_evidence_id: str
    scope_evidence_id: str
    combined_bundle_evidence_id: str
    target_join_evidence_id: str
    target_source_evidence_id: str
    raw_target_capture_evidence_id: str
    backtest_evidence_id: str
    estimator_freeze_evidence_id: str
    selected_candidate_id: str
    estimator: str
    parameter_count: int
    predictors: tuple[str, ...]
    training_periods: tuple[str, ...]
    training_row_count: int
    scaling_ddof: int
    predictor_means: tuple[float, ...]
    predictor_scales: tuple[float, ...]
    standardized_coefficients: tuple[float, ...]
    raw_unit_intercept: float
    raw_unit_coefficients: tuple[float, ...]
    design_rank: int
    residual_degrees_of_freedom: int
    condition_number: float
    training_mae_krw_million: float
    training_rmse_krw_million: float
    historical_benchmark_mae_krw_million: float
    historical_selected_candidate_mae_krw_million: float
    historical_relative_mae_improvement: float
    status: str = _STATUS
    prospective_feature_vector_frozen: bool = False
    prospective_forecast_run: bool = False
    q1_used_for_selection: bool = False
    q3_target_read: bool = False
    q3_source_outcome_loaded: bool = False
    q3_evaluated: bool = False
    numeric_forward_forecast_enabled: bool = False

    def __post_init__(self) -> None:
        hashes = (
            self.evidence_id,
            self.contract_evidence_id,
            self.execution_evidence_id,
            self.scope_evidence_id,
            self.combined_bundle_evidence_id,
            self.target_join_evidence_id,
            self.target_source_evidence_id,
            self.raw_target_capture_evidence_id,
            self.backtest_evidence_id,
            self.estimator_freeze_evidence_id,
        )
        if any(not _valid_sha(value) for value in hashes):
            raise ValueError("Selected-estimator artifact evidence ids must be SHA-256")
        if self.status != _STATUS:
            raise ValueError("Selected-estimator artifact status drifted")
        if self.estimator != "ordinary_least_squares":
            raise ValueError("Selected-estimator artifact estimator drifted")
        if self.training_periods != _EXPECTED_PERIODS or self.training_row_count != 20:
            raise ValueError("Selected-estimator artifact training scope drifted")
        if self.parameter_count != len(self.predictors) + 1:
            raise ValueError("Selected-estimator artifact parameter count drifted")
        if self.scaling_ddof != 0:
            raise ValueError("Selected-estimator artifact scaling rule drifted")
        if len(self.predictor_means) != len(self.predictors):
            raise ValueError("Selected-estimator artifact predictor mean count drifted")
        if len(self.predictor_scales) != len(self.predictors):
            raise ValueError("Selected-estimator artifact predictor scale count drifted")
        if len(self.standardized_coefficients) != self.parameter_count:
            raise ValueError("Selected-estimator artifact coefficient count drifted")
        if len(self.raw_unit_coefficients) != len(self.predictors):
            raise ValueError("Selected-estimator raw coefficient count drifted")
        if self.design_rank != self.parameter_count:
            raise ValueError("Selected-estimator full design is not full rank")
        if self.residual_degrees_of_freedom <= 0:
            raise ValueError("Selected-estimator residual DOF must be positive")
        numbers = (
            *self.predictor_means,
            *self.predictor_scales,
            *self.standardized_coefficients,
            self.raw_unit_intercept,
            *self.raw_unit_coefficients,
            self.condition_number,
            self.training_mae_krw_million,
            self.training_rmse_krw_million,
            self.historical_benchmark_mae_krw_million,
            self.historical_selected_candidate_mae_krw_million,
            self.historical_relative_mae_improvement,
        )
        if not all(math.isfinite(value) for value in numbers):
            raise ValueError("Selected-estimator artifact contains non-finite values")
        if any(value <= 0.0 for value in self.predictor_scales):
            raise ValueError("Selected-estimator predictor scales must be positive")
        if not 0.0 < self.historical_relative_mae_improvement < 1.0:
            raise ValueError("Selected-estimator historical improvement must be positive")
        if any(
            (
                self.prospective_feature_vector_frozen,
                self.prospective_forecast_run,
                self.q1_used_for_selection,
                self.q3_target_read,
                self.q3_source_outcome_loaded,
                self.q3_evaluated,
                self.numeric_forward_forecast_enabled,
            )
        ):
            raise ValueError("Selected-estimator artifact opened prospective boundary")


def _artifact_payload(item: FrozenSelectedEstimatorFullFit) -> dict[str, object]:
    return {
        "contract_evidence_id": item.contract_evidence_id,
        "execution_evidence_id": item.execution_evidence_id,
        "scope_evidence_id": item.scope_evidence_id,
        "combined_bundle_evidence_id": item.combined_bundle_evidence_id,
        "target_join_evidence_id": item.target_join_evidence_id,
        "target_source_evidence_id": item.target_source_evidence_id,
        "raw_target_capture_evidence_id": item.raw_target_capture_evidence_id,
        "backtest_evidence_id": item.backtest_evidence_id,
        "estimator_freeze_evidence_id": item.estimator_freeze_evidence_id,
        "selected_candidate_id": item.selected_candidate_id,
        "estimator": item.estimator,
        "parameter_count": item.parameter_count,
        "predictors": list(item.predictors),
        "training_periods": list(item.training_periods),
        "training_row_count": item.training_row_count,
        "scaling_ddof": item.scaling_ddof,
        "predictor_means": list(item.predictor_means),
        "predictor_scales": list(item.predictor_scales),
        "standardized_coefficients": list(item.standardized_coefficients),
        "raw_unit_intercept": item.raw_unit_intercept,
        "raw_unit_coefficients": list(item.raw_unit_coefficients),
        "design_rank": item.design_rank,
        "residual_degrees_of_freedom": item.residual_degrees_of_freedom,
        "condition_number": item.condition_number,
        "training_mae_krw_million": item.training_mae_krw_million,
        "training_rmse_krw_million": item.training_rmse_krw_million,
        "historical_benchmark_mae_krw_million": (
            item.historical_benchmark_mae_krw_million
        ),
        "historical_selected_candidate_mae_krw_million": (
            item.historical_selected_candidate_mae_krw_million
        ),
        "historical_relative_mae_improvement": item.historical_relative_mae_improvement,
        "status": item.status,
        "prospective_feature_vector_frozen": item.prospective_feature_vector_frozen,
        "prospective_forecast_run": item.prospective_forecast_run,
        "q1_used_for_selection": item.q1_used_for_selection,
        "q3_target_read": item.q3_target_read,
        "q3_source_outcome_loaded": item.q3_source_outcome_loaded,
        "q3_evaluated": item.q3_evaluated,
        "numeric_forward_forecast_enabled": item.numeric_forward_forecast_enabled,
    }


def _candidate_for_result(
    result: HistoricalBacktestResult,
    candidates: tuple[FrozenExAnteEstimatorCandidate, ...],
) -> tuple[FrozenExAnteEstimatorCandidate, float]:
    if result.selected_candidate_id is None or not result.final_estimator_selected:
        raise ValueError("Historical backtest selected no estimator")
    candidate = next(
        (item for item in candidates if item.candidate_id == result.selected_candidate_id),
        None,
    )
    scored = next(
        (item for item in result.candidates if item.candidate_id == result.selected_candidate_id),
        None,
    )
    if candidate is None or scored is None:
        raise ValueError("Historical selected candidate is absent from frozen candidates")
    if not scored.every_fold_valid or not scored.strictly_beats_benchmark:
        raise ValueError("Historical selected candidate did not pass the frozen benchmark gate")
    if scored.aggregate_mae_krw_million is None:
        raise ValueError("Historical selected candidate lacks aggregate MAE")
    return candidate, scored.aggregate_mae_krw_million


def build_selected_estimator_full_fit(
    contract: SelectedEstimatorFullFitContract,
    join: HistoricalTargetJoin,
    result: HistoricalBacktestResult,
    candidate: FrozenExAnteEstimatorCandidate,
    *,
    raw_target_capture_evidence_id: str,
) -> FrozenSelectedEstimatorFullFit:
    if join.target_periods != _EXPECTED_PERIODS or result.target_periods != _EXPECTED_PERIODS:
        raise ValueError("Selected-estimator full fit requires the exact twenty periods")
    if result.target_join_evidence_id != join.evidence_id:
        raise ValueError("Selected-estimator full fit backtest/join binding drifted")
    if result.selected_candidate_id != candidate.candidate_id:
        raise ValueError("Selected-estimator full fit candidate binding drifted")
    if candidate.estimator != "ordinary_least_squares":
        raise ValueError("Selected-estimator full fit requires frozen OLS")

    x = np.asarray(
        [
            [row.feature_map()[feature_id] for feature_id in candidate.predictors]
            for row in join.rows
        ],
        dtype=float,
    )
    y = np.asarray(
        [row.target_company_gross_profit_krw_million for row in join.rows],
        dtype=float,
    )
    if x.shape != (20, len(candidate.predictors)) or y.shape != (20,):
        raise ValueError("Selected-estimator full fit array geometry drifted")
    if not np.isfinite(x).all() or not np.isfinite(y).all():
        raise ValueError("Selected-estimator full fit contains non-finite training values")

    means = np.mean(x, axis=0)
    scales = np.std(x, axis=0, ddof=contract.scaling_ddof)
    if np.any(~np.isfinite(scales)) or np.any(scales <= 0.0):
        raise ValueError("Selected-estimator full fit has invalid predictor scales")
    standardized = (x - means) / scales
    design = np.column_stack((np.ones(len(join.rows), dtype=float), standardized))
    rank = int(np.linalg.matrix_rank(design))
    residual_dof = len(join.rows) - rank
    if rank != candidate.parameter_count:
        raise ValueError("Selected-estimator full fit design is not full column rank")
    if residual_dof <= 0:
        raise ValueError("Selected-estimator full fit residual DOF is not positive")
    condition = float(np.linalg.cond(design))
    coefficients, _residuals, _rank, _singular = np.linalg.lstsq(design, y, rcond=None)
    fitted = design @ coefficients
    residuals = y - fitted
    if not np.isfinite(coefficients).all() or not np.isfinite(fitted).all():
        raise ValueError("Selected-estimator full fit produced non-finite output")

    raw_slopes = coefficients[1:] / scales
    raw_intercept = float(coefficients[0] - np.sum(coefficients[1:] * means / scales))
    training_mae = float(np.mean(np.abs(residuals)))
    training_rmse = float(np.sqrt(np.mean(np.square(residuals))))
    selected_mae = next(
        cast(float, item.aggregate_mae_krw_million)
        for item in result.candidates
        if item.candidate_id == candidate.candidate_id
    )
    relative_improvement = 1.0 - selected_mae / result.benchmark_mae_krw_million

    provisional = FrozenSelectedEstimatorFullFit(
        evidence_id="0" * 64,
        contract_evidence_id=contract.evidence_id,
        execution_evidence_id=result.execution_evidence_id,
        scope_evidence_id=result.scope_evidence_id,
        combined_bundle_evidence_id=join.combined_bundle_evidence_id,
        target_join_evidence_id=join.evidence_id,
        target_source_evidence_id=join.target_source_evidence_id,
        raw_target_capture_evidence_id=raw_target_capture_evidence_id,
        backtest_evidence_id=result.evidence_id,
        estimator_freeze_evidence_id=result.estimator_freeze_evidence_id,
        selected_candidate_id=candidate.candidate_id,
        estimator=candidate.estimator,
        parameter_count=candidate.parameter_count,
        predictors=candidate.predictors,
        training_periods=join.target_periods,
        training_row_count=len(join.rows),
        scaling_ddof=contract.scaling_ddof,
        predictor_means=tuple(float(value) for value in means),
        predictor_scales=tuple(float(value) for value in scales),
        standardized_coefficients=tuple(float(value) for value in coefficients),
        raw_unit_intercept=raw_intercept,
        raw_unit_coefficients=tuple(float(value) for value in raw_slopes),
        design_rank=rank,
        residual_degrees_of_freedom=residual_dof,
        condition_number=condition,
        training_mae_krw_million=training_mae,
        training_rmse_krw_million=training_rmse,
        historical_benchmark_mae_krw_million=result.benchmark_mae_krw_million,
        historical_selected_candidate_mae_krw_million=selected_mae,
        historical_relative_mae_improvement=relative_improvement,
    )
    return replace(provisional, evidence_id=_sha(_artifact_payload(provisional)))


def persist_selected_estimator_full_fit(
    item: FrozenSelectedEstimatorFullFit,
    *,
    output: str | Path = DEFAULT_SELECTED_ESTIMATOR_OUTPUT,
) -> Path:
    if _sha(_artifact_payload(item)) != item.evidence_id:
        raise ValueError("Selected-estimator evidence hash drifted before persistence")
    root = Path(output)
    root.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": 1,
        "status": _STATUS,
        "selected_estimator": {
            "evidence_id": item.evidence_id,
            **_artifact_payload(item),
        },
    }
    encoded = _canonical_bytes(payload)
    immutable = root / f"selected-estimator-{item.evidence_id}.json"
    if immutable.exists():
        if immutable.read_bytes() != encoded:
            raise ValueError("Selected-estimator immutable artifact drifted")
    else:
        immutable.write_bytes(encoded)
    pointer = root / "latest_selected_estimator.json"
    if pointer.exists() and pointer.read_bytes() != encoded:
        raise ValueError("Selected-estimator freeze is already locked to different evidence")
    temporary = root / ".latest_selected_estimator.json.tmp"
    temporary.write_bytes(encoded)
    temporary.replace(pointer)
    return pointer


def _expected_backtest_evidence(path: str | Path) -> str:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    root = _mapping(raw, "Historical backtest artifact")
    if root.get("schema_version") != 1 or root.get("status") != _BACKTEST_STATUS:
        raise ValueError("Historical backtest artifact status is invalid")
    body = _mapping(root.get("backtest"), "Historical backtest body")
    evidence_id = str(body.get("evidence_id", ""))
    if not _valid_sha(evidence_id):
        raise ValueError("Historical backtest artifact evidence id is invalid")
    return evidence_id


def freeze_selected_estimator_from_locked_artifacts(
    *,
    contract_path: str | Path = DEFAULT_SELECTED_ESTIMATOR_FULL_FIT_CONTRACT,
    output: str | Path = DEFAULT_SELECTED_ESTIMATOR_OUTPUT,
) -> tuple[FrozenSelectedEstimatorFullFit, Path, bool]:
    contract = load_selected_estimator_full_fit_contract(contract_path)
    repair = load_frozen_historical_schema_repair_v2(contract.execution_path)
    execution = repair.runtime_execution
    scope = load_frozen_exact_twenty_period_ex_ante_scope(contract.scope_path)
    estimator = load_frozen_ex_ante_estimator_selection(contract.estimator_freeze_path)
    join = load_historical_target_join(contract.target_join_path)
    capture, _payloads = load_historical_raw_target_capture(contract.raw_capture_path)

    if join.execution_evidence_id != execution.evidence_id:
        raise ValueError("Selected-estimator target join execution binding drifted")
    if capture.execution_evidence_id != execution.evidence_id:
        raise ValueError("Selected-estimator raw capture execution binding drifted")
    if join.scope_evidence_id != scope.evidence_id:
        raise ValueError("Selected-estimator target join scope binding drifted")
    if scope.estimator_freeze_evidence_id != estimator.evidence_id:
        raise ValueError("Selected-estimator pre-target estimator binding drifted")

    result = run_frozen_historical_backtest(execution, scope, estimator, join)
    expected_backtest = _expected_backtest_evidence(contract.backtest_path)
    if result.evidence_id != expected_backtest:
        raise ValueError("Selected-estimator recomputed backtest evidence drifted")
    candidate, _selected_mae = _candidate_for_result(result, estimator.candidates)
    item = build_selected_estimator_full_fit(
        contract,
        join,
        result,
        candidate,
        raw_target_capture_evidence_id=capture.evidence_id,
    )
    pointer = Path(output) / "latest_selected_estimator.json"
    reused = pointer.is_file()
    persisted = persist_selected_estimator_full_fit(item, output=output)
    return item, persisted, reused


__all__ = [
    "DEFAULT_SELECTED_ESTIMATOR_FULL_FIT_CONTRACT",
    "DEFAULT_SELECTED_ESTIMATOR_OUTPUT",
    "DEFAULT_SELECTED_ESTIMATOR_POINTER",
    "FrozenSelectedEstimatorFullFit",
    "SelectedEstimatorFullFitContract",
    "build_selected_estimator_full_fit",
    "freeze_selected_estimator_from_locked_artifacts",
    "load_selected_estimator_full_fit_contract",
    "persist_selected_estimator_full_fit",
]
