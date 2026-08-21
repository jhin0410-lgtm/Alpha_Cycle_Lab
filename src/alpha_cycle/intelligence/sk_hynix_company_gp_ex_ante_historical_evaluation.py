"""First historical target join and frozen chronological backtest for SK hynix ex-ante GP.

This module is intentionally written and merged before the first historical target read. It
binds the exact twenty-period target-blind scope, acquires one frozen definition of realized
company gross profit from official OpenDART filings, locks the captured payloads, and then
executes only the estimator candidates and expanding-window geometry preregistered by the
existing estimator freeze. Protected 2026Q3/2026Q4 outcomes are never requested here.
"""

from __future__ import annotations

import hashlib
import json
import math
import shutil
from dataclasses import asdict, dataclass, replace
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import cast

import numpy as np
import yaml

from alpha_cycle.intelligence.sk_hynix_company_gp_ex_ante_estimator_freeze import (
    DEFAULT_COMPANY_GP_EX_ANTE_ESTIMATOR_FREEZE,
    FrozenExAnteEstimatorCandidate,
    FrozenExAnteEstimatorSelection,
    load_frozen_ex_ante_estimator_selection,
)
from alpha_cycle.intelligence.sk_hynix_company_gp_ex_ante_pit import (
    PointInTimeFeatureBundle,
    load_point_in_time_feature_bundle,
)
from alpha_cycle.intelligence.sk_hynix_company_gp_ex_ante_pit_panel_expansion import (
    DEFAULT_EX_ANTE_PIT_PANEL_EXPANSION_BUNDLE,
)
from alpha_cycle.intelligence.sk_hynix_company_gp_ex_ante_scope_freeze import (
    DEFAULT_COMPANY_GP_EX_ANTE_SCOPE_FREEZE,
    FrozenExactTwentyPeriodExAnteScope,
    load_frozen_exact_twenty_period_ex_ante_scope,
)
from alpha_cycle.providers.opendart import OpenDartReadOnlyClient

DEFAULT_COMPANY_GP_EX_ANTE_HISTORICAL_EXECUTION = Path(
    "config/skhynix_company_gp_ex_ante_historical_evaluation_execution.v1.yaml"
)
DEFAULT_COMPANY_GP_EX_ANTE_HISTORICAL_OUTPUT = Path(
    "data/private/research/skhynix-company-gp-ex-ante-first-historical-evaluation"
)
DEFAULT_COMPANY_GP_EX_ANTE_TARGET_JOIN = (
    DEFAULT_COMPANY_GP_EX_ANTE_HISTORICAL_OUTPUT / "latest_historical_target_join.json"
)
DEFAULT_COMPANY_GP_EX_ANTE_HISTORICAL_BACKTEST = (
    DEFAULT_COMPANY_GP_EX_ANTE_HISTORICAL_OUTPUT / "latest_historical_backtest.json"
)

_EXPECTED_PERIODS = tuple(
    f"{year}Q{quarter}" for year in range(2016, 2026) for quarter in (2, 3)
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
_TARGET_JOIN_STATUS = "skhynix_ex_ante_exact_twenty_period_historical_target_join_locked"
_BACKTEST_STATUS = "skhynix_ex_ante_first_chronological_historical_backtest_complete"
_NO_SELECTION = "no_candidate_strictly_beat_frozen_benchmark"
_SELECTION_COMPLETE = "frozen_candidate_selected_by_preregistered_order"
_ALLOWED_STATEMENTS = frozenset({"IS", "CIS"})


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


def _sha_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _valid_sha(value: str) -> bool:
    return len(value) == 64 and all(char in "0123456789abcdef" for char in value)


def _mapping(value: object, label: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be an object")
    return {str(key): item for key, item in cast(dict[object, object], value).items()}


def _array(value: object, label: str) -> list[object]:
    if not isinstance(value, list):
        raise ValueError(f"{label} must be an array")
    return value


def _canonical_json_bytes(payload: object) -> bytes:
    return json.dumps(
        payload,
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
        default=str,
    ).encode("utf-8")


def _integral_krw(value: object, label: str) -> int:
    text = str(value).strip().replace(",", "")
    if text in {"", "-", "None", "nan"}:
        raise ValueError(f"Historical target {label} is missing")
    negative = text.startswith("(") and text.endswith(")")
    if negative:
        text = text[1:-1]
    try:
        amount = Decimal(text)
    except InvalidOperation as exc:
        raise ValueError(f"Historical target {label} is not numeric") from exc
    if negative:
        amount = -amount
    if not amount.is_finite() or amount != amount.to_integral_value():
        raise ValueError(f"Historical target {label} must be integral KRW")
    return int(amount)


def _receipt_date(receipt: str) -> date:
    if len(receipt) != 14 or not receipt.isdigit():
        raise ValueError("Historical target receipt number must be fourteen digits")
    return date(int(receipt[:4]), int(receipt[4:6]), int(receipt[6:8]))


@dataclass(frozen=True)
class FrozenHistoricalEvaluationExecution:
    evidence_id: str
    execution_id: str
    execution_version: str
    status: str
    ticker: str
    target_metric: str
    scientific_scope: str
    scope_freeze_path: str
    combined_feature_bundle_path: str
    estimator_freeze_path: str
    exact_target_periods: tuple[str, ...]
    provider: str
    endpoint: str
    fs_div: str
    q2_report_code: str
    q3_report_code: str
    amount_field: str
    allowed_statement_divisions: tuple[str, ...]
    revenue_account_ids: tuple[str, ...]
    cost_of_sales_account_ids: tuple[str, ...]
    gross_profit_account_ids: tuple[str, ...]
    require_accounting_identity: bool
    require_same_receipt: bool
    require_receipt_not_after_evaluation_date: bool
    post_join_target_refresh_allowed: bool
    correction_search_or_selection_allowed: bool
    source_fallback_allowed: bool
    partial_target_join_allowed: bool
    fit_scaling_from_training_fold_only: bool
    scaling_standard_deviation_ddof: int
    target_standardization_allowed: bool
    future_fold_statistics_allowed: bool
    scheme: str
    shared_initial_training_rows: int
    scored_fold_count: int
    primary_metric: str
    benchmark_id: str
    benchmark_prediction_feature: str
    candidate_must_strictly_beat_benchmark: bool
    every_fold_full_rank_required: bool
    every_fold_positive_residual_dof_required: bool
    condition_number_report_only: bool
    coefficient_stability_report_only: bool
    selection_order: tuple[str, ...]
    no_candidate_pass_action: str
    q1_may_change_selection: bool
    q3_target_read_before_run: bool
    q3_source_outcome_loaded_before_run: bool
    historical_target_values_read_before_run: bool
    historical_target_join_run_before_run: bool
    estimator_fit_run_before_run: bool
    historical_backtest_run_before_run: bool
    numeric_forward_forecast_enabled_before_run: bool

    def __post_init__(self) -> None:
        if not _valid_sha(self.evidence_id):
            raise ValueError("Historical execution evidence id must be SHA-256")
        if self.execution_id != "skhynix_company_gp_ex_ante_first_historical_evaluation":
            raise ValueError("Historical execution id drifted")
        if (
            self.execution_version != "1.0-frozen-pre-first-target-read"
            or self.status != "frozen_pre_first_target_read"
        ):
            raise ValueError("Historical execution is not frozen before first target read")
        if self.ticker != "000660" or self.target_metric != "company_gross_profit_krw_million":
            raise ValueError("Historical execution ticker/target drifted")
        if self.exact_target_periods != _EXPECTED_PERIODS:
            raise ValueError("Historical execution exact target periods drifted")
        if self.provider != "opendart" or self.endpoint != "fnlttSinglAcntAll":
            raise ValueError("Historical execution target provider drifted")
        if self.fs_div != "CFS" or self.q2_report_code != "11012" or self.q3_report_code != "11014":
            raise ValueError("Historical execution filing geometry drifted")
        if self.amount_field != "thstrm_amount":
            raise ValueError("Historical execution amount-field definition drifted")
        if frozenset(self.allowed_statement_divisions) != _ALLOWED_STATEMENTS:
            raise ValueError("Historical execution statement divisions drifted")
        if not self.revenue_account_ids or not self.cost_of_sales_account_ids or not self.gross_profit_account_ids:
            raise ValueError("Historical execution account ids cannot be empty")
        if not (
            self.require_accounting_identity
            and self.require_same_receipt
            and self.require_receipt_not_after_evaluation_date
        ):
            raise ValueError("Historical execution target source gates drifted")
        if any(
            (
                self.post_join_target_refresh_allowed,
                self.correction_search_or_selection_allowed,
                self.source_fallback_allowed,
                self.partial_target_join_allowed,
            )
        ):
            raise ValueError("Historical execution opened a target-source adaptation path")
        if not self.fit_scaling_from_training_fold_only or self.scaling_standard_deviation_ddof != 0:
            raise ValueError("Historical execution scaling policy drifted")
        if self.target_standardization_allowed or self.future_fold_statistics_allowed:
            raise ValueError("Historical execution preprocessing opened future information")
        if self.scheme != "chronological_expanding_window":
            raise ValueError("Historical execution evaluation scheme drifted")
        if self.shared_initial_training_rows != 12 or self.scored_fold_count != 8:
            raise ValueError("Historical execution fold geometry drifted")
        if self.primary_metric != "mae_krw_million":
            raise ValueError("Historical execution metric drifted")
        if self.benchmark_id != "previous_reported_quarter_gross_profit_persistence":
            raise ValueError("Historical execution benchmark id drifted")
        if self.benchmark_prediction_feature != "lagged_company_gross_profit":
            raise ValueError("Historical execution benchmark rule drifted")
        if not (
            self.candidate_must_strictly_beat_benchmark
            and self.every_fold_full_rank_required
            and self.every_fold_positive_residual_dof_required
            and self.condition_number_report_only
            and self.coefficient_stability_report_only
        ):
            raise ValueError("Historical execution model-selection gates drifted")
        expected_selection = (
            "lowest_aggregate_chronological_mae",
            "lower_parameter_count_on_exact_mae_tie",
            "earlier_estimator_freeze_manifest_order_on_remaining_exact_tie",
        )
        if self.selection_order != expected_selection:
            raise ValueError("Historical execution selection order drifted")
        if self.no_candidate_pass_action != "select_no_estimator_and_keep_forward_forecast_disabled":
            raise ValueError("Historical execution no-pass action drifted")
        if self.q1_may_change_selection:
            raise ValueError("Historical execution cannot use contaminated 2026Q1 for selection")
        if any(
            (
                self.q3_target_read_before_run,
                self.q3_source_outcome_loaded_before_run,
                self.historical_target_values_read_before_run,
                self.historical_target_join_run_before_run,
                self.estimator_fit_run_before_run,
                self.historical_backtest_run_before_run,
                self.numeric_forward_forecast_enabled_before_run,
            )
        ):
            raise ValueError("Historical execution manifest was not frozen before first run")

    def report_code_for(self, period_id: str) -> str:
        if period_id not in self.exact_target_periods:
            raise ValueError(f"Historical target period is outside frozen scope: {period_id}")
        quarter = period_id[-1]
        if quarter == "2":
            return self.q2_report_code
        if quarter == "3":
            return self.q3_report_code
        raise ValueError(f"Historical execution does not support quarter: {period_id}")


@dataclass(frozen=True)
class HistoricalTargetObservation:
    period_id: str
    report_code: str
    receipt_no: str
    receipt_date: date
    revenue_krw: int
    cost_of_sales_krw: int
    gross_profit_krw: int
    gross_profit_krw_million: float
    raw_payload_sha256: str
    captured_payload_bytes_sha256: str

    def __post_init__(self) -> None:
        if self.period_id not in _EXPECTED_PERIODS:
            raise ValueError("Historical target observation period drifted")
        expected_code = "11012" if self.period_id.endswith("Q2") else "11014"
        if self.report_code != expected_code:
            raise ValueError("Historical target observation report code drifted")
        if self.receipt_date != _receipt_date(self.receipt_no):
            raise ValueError("Historical target receipt/date identity drifted")
        if self.revenue_krw <= 0 or self.cost_of_sales_krw < 0:
            raise ValueError("Historical target revenue/cost values are invalid")
        if self.revenue_krw - self.cost_of_sales_krw != self.gross_profit_krw:
            raise ValueError("Historical target accounting identity failed")
        expected_million = self.gross_profit_krw / 1_000_000.0
        if not math.isfinite(self.gross_profit_krw_million):
            raise ValueError("Historical target gross profit must be finite")
        if self.gross_profit_krw_million != expected_million:
            raise ValueError("Historical target million-unit conversion drifted")
        if not _valid_sha(self.raw_payload_sha256) or not _valid_sha(
            self.captured_payload_bytes_sha256
        ):
            raise ValueError("Historical target source hashes must be SHA-256")


@dataclass(frozen=True)
class JoinedHistoricalRow:
    period_id: str
    features: tuple[tuple[str, float], ...]
    target_company_gross_profit_krw_million: float
    target_receipt_no: str
    target_raw_payload_sha256: str
    target_captured_payload_bytes_sha256: str

    def __post_init__(self) -> None:
        if self.period_id not in _EXPECTED_PERIODS:
            raise ValueError("Historical joined row period drifted")
        if tuple(key for key, _value in self.features) != _EXPECTED_FEATURES:
            raise ValueError("Historical joined row feature schema drifted")
        values = tuple(value for _key, value in self.features)
        if not all(math.isfinite(value) for value in values):
            raise ValueError("Historical joined row contains a non-finite feature")
        if not math.isfinite(self.target_company_gross_profit_krw_million):
            raise ValueError("Historical joined row target must be finite")
        if not _valid_sha(self.target_raw_payload_sha256) or not _valid_sha(
            self.target_captured_payload_bytes_sha256
        ):
            raise ValueError("Historical joined row target hashes are invalid")

    def feature_map(self) -> dict[str, float]:
        return dict(self.features)


@dataclass(frozen=True)
class HistoricalTargetJoin:
    evidence_id: str
    execution_evidence_id: str
    scope_evidence_id: str
    combined_bundle_evidence_id: str
    target_source_evidence_id: str
    evaluation_date: date
    target_periods: tuple[str, ...]
    target_observations: tuple[HistoricalTargetObservation, ...]
    rows: tuple[JoinedHistoricalRow, ...]
    status: str = _TARGET_JOIN_STATUS
    historical_target_values_read: bool = True
    target_join_run: bool = True
    estimator_fit_run: bool = False
    historical_backtest_run: bool = False
    q1_used_for_selection: bool = False
    q3_target_read: bool = False
    q3_source_outcome_loaded: bool = False
    numeric_forward_forecast_enabled: bool = False

    def __post_init__(self) -> None:
        hashes = (
            self.evidence_id,
            self.execution_evidence_id,
            self.scope_evidence_id,
            self.combined_bundle_evidence_id,
            self.target_source_evidence_id,
        )
        if any(not _valid_sha(value) for value in hashes):
            raise ValueError("Historical target join evidence ids must be SHA-256")
        if self.status != _TARGET_JOIN_STATUS:
            raise ValueError("Historical target join status drifted")
        if self.target_periods != _EXPECTED_PERIODS:
            raise ValueError("Historical target join periods drifted")
        if tuple(item.period_id for item in self.target_observations) != self.target_periods:
            raise ValueError("Historical target observations are out of frozen order")
        if tuple(item.period_id for item in self.rows) != self.target_periods:
            raise ValueError("Historical joined rows are out of frozen order")
        if len(self.target_observations) != 20 or len(self.rows) != 20:
            raise ValueError("Historical target join requires exactly twenty complete rows")
        if not self.historical_target_values_read or not self.target_join_run:
            raise ValueError("Historical target join did not record its target boundary crossing")
        if any(
            (
                self.estimator_fit_run,
                self.historical_backtest_run,
                self.q1_used_for_selection,
                self.q3_target_read,
                self.q3_source_outcome_loaded,
                self.numeric_forward_forecast_enabled,
            )
        ):
            raise ValueError("Historical target join exceeded join-only boundary")


@dataclass(frozen=True)
class BenchmarkFoldScore:
    fold_number: int
    score_period: str
    training_row_count: int
    actual_krw_million: float
    prediction_krw_million: float
    absolute_error_krw_million: float


@dataclass(frozen=True)
class CandidateFoldScore:
    fold_number: int
    score_period: str
    training_row_count: int
    prediction_krw_million: float | None
    absolute_error_krw_million: float | None
    design_rank: int | None
    residual_degrees_of_freedom: int | None
    condition_number: float | None
    standardized_coefficients: tuple[float, ...] | None
    valid: bool
    failure_reason: str | None

    def __post_init__(self) -> None:
        if self.valid:
            required = (
                self.prediction_krw_million,
                self.absolute_error_krw_million,
                self.design_rank,
                self.residual_degrees_of_freedom,
                self.condition_number,
                self.standardized_coefficients,
            )
            if any(item is None for item in required) or self.failure_reason is not None:
                raise ValueError("Valid historical candidate fold is incomplete")
        elif self.failure_reason is None:
            raise ValueError("Invalid historical candidate fold requires a reason")


@dataclass(frozen=True)
class CandidateBacktestResult:
    candidate_id: str
    parameter_count: int
    predictors: tuple[str, ...]
    folds: tuple[CandidateFoldScore, ...]
    aggregate_mae_krw_million: float | None
    every_fold_valid: bool
    strictly_beats_benchmark: bool
    max_standardized_coefficient_delta_l2: float | None

    def __post_init__(self) -> None:
        if self.candidate_id not in _EXPECTED_CANDIDATES or len(self.folds) != 8:
            raise ValueError("Historical candidate backtest geometry drifted")
        if self.parameter_count != len(self.predictors) + 1:
            raise ValueError("Historical candidate parameter count drifted")
        if self.every_fold_valid != all(item.valid for item in self.folds):
            raise ValueError("Historical candidate fold-validity flag drifted")
        if self.every_fold_valid:
            if self.aggregate_mae_krw_million is None:
                raise ValueError("Historical candidate valid backtest lacks aggregate MAE")
            if not math.isfinite(self.aggregate_mae_krw_million):
                raise ValueError("Historical candidate aggregate MAE must be finite")
        elif self.aggregate_mae_krw_million is not None or self.strictly_beats_benchmark:
            raise ValueError("Failed historical candidate cannot retain MAE/pass status")


@dataclass(frozen=True)
class HistoricalBacktestResult:
    evidence_id: str
    execution_evidence_id: str
    scope_evidence_id: str
    target_join_evidence_id: str
    estimator_freeze_evidence_id: str
    target_periods: tuple[str, ...]
    benchmark_id: str
    benchmark_folds: tuple[BenchmarkFoldScore, ...]
    benchmark_mae_krw_million: float
    candidates: tuple[CandidateBacktestResult, ...]
    selected_candidate_id: str | None
    selection_status: str
    status: str = _BACKTEST_STATUS
    historical_target_values_read: bool = True
    target_join_run: bool = True
    estimator_fit_run: bool = True
    historical_backtest_run: bool = True
    final_estimator_selected: bool = False
    q1_used_for_selection: bool = False
    q3_target_read: bool = False
    q3_source_outcome_loaded: bool = False
    q3_evaluated: bool = False
    numeric_forward_forecast_enabled: bool = False

    def __post_init__(self) -> None:
        hashes = (
            self.evidence_id,
            self.execution_evidence_id,
            self.scope_evidence_id,
            self.target_join_evidence_id,
            self.estimator_freeze_evidence_id,
        )
        if any(not _valid_sha(value) for value in hashes):
            raise ValueError("Historical backtest evidence ids must be SHA-256")
        if self.status != _BACKTEST_STATUS or self.target_periods != _EXPECTED_PERIODS:
            raise ValueError("Historical backtest scope/status drifted")
        if len(self.benchmark_folds) != 8 or len(self.candidates) != 3:
            raise ValueError("Historical backtest scored geometry drifted")
        if not math.isfinite(self.benchmark_mae_krw_million):
            raise ValueError("Historical benchmark MAE must be finite")
        if tuple(item.candidate_id for item in self.candidates) != _EXPECTED_CANDIDATES:
            raise ValueError("Historical backtest candidate order drifted")
        expected_selected = self.selected_candidate_id is not None
        if self.final_estimator_selected != expected_selected:
            raise ValueError("Historical backtest selected-estimator flag drifted")
        if expected_selected:
            if self.selection_status != _SELECTION_COMPLETE:
                raise ValueError("Historical backtest selection status drifted")
            selected = next(
                (item for item in self.candidates if item.candidate_id == self.selected_candidate_id),
                None,
            )
            if selected is None or not selected.strictly_beats_benchmark:
                raise ValueError("Historical backtest selected a non-passing candidate")
        elif self.selection_status != _NO_SELECTION:
            raise ValueError("Historical backtest no-selection status drifted")
        if not all(
            (
                self.historical_target_values_read,
                self.target_join_run,
                self.estimator_fit_run,
                self.historical_backtest_run,
            )
        ):
            raise ValueError("Historical backtest did not record executed boundaries")
        if any(
            (
                self.q1_used_for_selection,
                self.q3_target_read,
                self.q3_source_outcome_loaded,
                self.q3_evaluated,
                self.numeric_forward_forecast_enabled,
            )
        ):
            raise ValueError("Historical backtest opened protected prospective scope")


def load_frozen_historical_evaluation_execution(
    path: str | Path = DEFAULT_COMPANY_GP_EX_ANTE_HISTORICAL_EXECUTION,
) -> FrozenHistoricalEvaluationExecution:
    source = Path(path)
    with source.open(encoding="utf-8") as handle:
        raw: object = yaml.safe_load(handle)
    root = _mapping(raw, "Historical execution manifest")
    if root.get("schema_version") != 1:
        raise ValueError("Historical execution schema is invalid")
    body = _mapping(root.get("execution"), "Historical execution body")
    inputs = _mapping(body.get("frozen_inputs"), "Historical execution frozen inputs")
    source_policy = _mapping(body.get("target_source_policy"), "Historical target source policy")
    preprocessing = _mapping(body.get("preprocessing"), "Historical preprocessing")
    evaluation = _mapping(body.get("chronological_evaluation"), "Historical evaluation")
    protected = _mapping(body.get("protected_outcomes"), "Historical protected outcomes")
    trust = _mapping(body.get("trust_boundary_before_first_run"), "Historical trust boundary")
    stable = {"schema_version": 1, "execution": body}
    return FrozenHistoricalEvaluationExecution(
        evidence_id=_sha(stable),
        execution_id=str(body.get("execution_id", "")),
        execution_version=str(body.get("execution_version", "")),
        status=str(body.get("status", "")),
        ticker=str(body.get("ticker", "")).zfill(6),
        target_metric=str(body.get("target_metric", "")),
        scientific_scope=str(body.get("scientific_scope", "")),
        scope_freeze_path=str(inputs.get("scope_freeze_path", "")),
        combined_feature_bundle_path=str(inputs.get("combined_feature_bundle_path", "")),
        estimator_freeze_path=str(inputs.get("estimator_freeze_path", "")),
        exact_target_periods=tuple(
            str(item) for item in _array(body.get("exact_target_periods"), "exact_target_periods")
        ),
        provider=str(source_policy.get("provider", "")),
        endpoint=str(source_policy.get("endpoint", "")),
        fs_div=str(source_policy.get("fs_div", "")),
        q2_report_code=str(source_policy.get("q2_report_code", "")),
        q3_report_code=str(source_policy.get("q3_report_code", "")),
        amount_field=str(source_policy.get("current_term_amount_field", "")),
        allowed_statement_divisions=tuple(
            str(item)
            for item in _array(
                source_policy.get("allowed_statement_divisions"),
                "allowed_statement_divisions",
            )
        ),
        revenue_account_ids=tuple(
            str(item)
            for item in _array(source_policy.get("revenue_account_ids"), "revenue_account_ids")
        ),
        cost_of_sales_account_ids=tuple(
            str(item)
            for item in _array(
                source_policy.get("cost_of_sales_account_ids"),
                "cost_of_sales_account_ids",
            )
        ),
        gross_profit_account_ids=tuple(
            str(item)
            for item in _array(
                source_policy.get("gross_profit_account_ids"),
                "gross_profit_account_ids",
            )
        ),
        require_accounting_identity=(
            source_policy.get("require_revenue_minus_cost_equals_gross_profit") is True
        ),
        require_same_receipt=(
            source_policy.get("require_same_receipt_for_selected_accounts") is True
        ),
        require_receipt_not_after_evaluation_date=(
            source_policy.get("require_receipt_date_not_after_evaluation_date") is True
        ),
        post_join_target_refresh_allowed=(
            source_policy.get("post_join_target_refresh_allowed") is True
        ),
        correction_search_or_selection_allowed=(
            source_policy.get("correction_search_or_selection_allowed") is True
        ),
        source_fallback_allowed=source_policy.get("source_fallback_allowed") is True,
        partial_target_join_allowed=(
            source_policy.get("partial_target_join_allowed") is True
        ),
        fit_scaling_from_training_fold_only=(
            preprocessing.get("fit_predictor_center_and_scale_from_training_fold_only") is True
        ),
        scaling_standard_deviation_ddof=int(
            str(preprocessing.get("scaling_standard_deviation_ddof", -1))
        ),
        target_standardization_allowed=(
            preprocessing.get("target_standardization_allowed") is True
        ),
        future_fold_statistics_allowed=(
            preprocessing.get("future_fold_statistics_allowed") is True
        ),
        scheme=str(evaluation.get("scheme", "")),
        shared_initial_training_rows=int(
            str(evaluation.get("shared_initial_training_rows", -1))
        ),
        scored_fold_count=int(str(evaluation.get("scored_fold_count", -1))),
        primary_metric=str(evaluation.get("primary_metric", "")),
        benchmark_id=str(evaluation.get("benchmark_id", "")),
        benchmark_prediction_feature=str(
            evaluation.get("benchmark_prediction_feature", "")
        ),
        candidate_must_strictly_beat_benchmark=(
            evaluation.get("candidate_must_strictly_beat_benchmark") is True
        ),
        every_fold_full_rank_required=(
            evaluation.get("every_scored_fold_design_must_have_full_column_rank") is True
        ),
        every_fold_positive_residual_dof_required=(
            evaluation.get("every_scored_fold_residual_dof_must_be_positive") is True
        ),
        condition_number_report_only=(
            evaluation.get("condition_number_report_only") is True
        ),
        coefficient_stability_report_only=(
            evaluation.get("coefficient_stability_report_only") is True
        ),
        selection_order=tuple(
            str(item)
            for item in _array(evaluation.get("selection_order"), "selection_order")
        ),
        no_candidate_pass_action=str(evaluation.get("no_candidate_pass_action", "")),
        q1_may_change_selection=(
            protected.get("2026Q1_may_change_candidate_selection") is True
        ),
        q3_target_read_before_run=protected.get("2026Q3_target_read") is True,
        q3_source_outcome_loaded_before_run=(
            protected.get("2026Q3_source_outcome_loaded") is True
        ),
        historical_target_values_read_before_run=(
            trust.get("historical_target_values_read") is True
        ),
        historical_target_join_run_before_run=(
            trust.get("historical_target_join_run") is True
        ),
        estimator_fit_run_before_run=trust.get("estimator_fit_run") is True,
        historical_backtest_run_before_run=(
            trust.get("historical_backtest_run") is True
        ),
        numeric_forward_forecast_enabled_before_run=(
            trust.get("numeric_forward_forecast_enabled") is True
        ),
    )


def _financial_rows(raw_payload: object) -> tuple[dict[str, object], ...]:
    root = _mapping(raw_payload, "Historical OpenDART raw payload")
    financials = _mapping(root.get("financials"), "Historical OpenDART financials")
    rows_raw = _array(financials.get("list"), "Historical OpenDART financial list")
    rows = tuple(_mapping(item, "Historical OpenDART financial row") for item in rows_raw)
    if not rows:
        raise ValueError("Historical OpenDART financial list is empty")
    return rows


def _select_account(
    rows: tuple[dict[str, object], ...],
    account_ids: tuple[str, ...],
    *,
    business_year: int,
    report_code: str,
    amount_field: str,
    label: str,
) -> tuple[int, str]:
    accepted = {item.casefold() for item in account_ids}
    matches: list[tuple[int, str]] = []
    for row in rows:
        if str(row.get("sj_div", "")).strip() not in _ALLOWED_STATEMENTS:
            continue
        if str(row.get("account_id", "")).strip().casefold() not in accepted:
            continue
        row_year = str(row.get("bsns_year", "")).strip()
        row_code = str(row.get("reprt_code", "")).strip()
        if row_year and row_year != str(business_year):
            continue
        if row_code and row_code != report_code:
            continue
        receipt = str(row.get("rcept_no", "")).strip()
        _receipt_date(receipt)
        matches.append((_integral_krw(row.get(amount_field), label), receipt))
    unique = tuple(dict.fromkeys(matches))
    if len(unique) != 1:
        raise ValueError(
            f"Historical target account must resolve uniquely: {business_year} "
            f"report_code={report_code} label={label} count={len(unique)}"
        )
    return unique[0]


def extract_historical_target_observation(
    execution: FrozenHistoricalEvaluationExecution,
    period_id: str,
    raw_payload: object,
    *,
    evaluation_date: date,
) -> HistoricalTargetObservation:
    if period_id not in execution.exact_target_periods:
        raise ValueError("Historical target extraction period is outside frozen scope")
    business_year = int(period_id[:4])
    report_code = execution.report_code_for(period_id)
    rows = _financial_rows(raw_payload)
    revenue, revenue_receipt = _select_account(
        rows,
        execution.revenue_account_ids,
        business_year=business_year,
        report_code=report_code,
        amount_field=execution.amount_field,
        label="revenue",
    )
    cost, cost_receipt = _select_account(
        rows,
        execution.cost_of_sales_account_ids,
        business_year=business_year,
        report_code=report_code,
        amount_field=execution.amount_field,
        label="cost_of_sales",
    )
    gross, gross_receipt = _select_account(
        rows,
        execution.gross_profit_account_ids,
        business_year=business_year,
        report_code=report_code,
        amount_field=execution.amount_field,
        label="gross_profit",
    )
    receipts = {revenue_receipt, cost_receipt, gross_receipt}
    if len(receipts) != 1:
        raise ValueError(f"Historical target accounts cross filing receipts: {period_id}")
    receipt = next(iter(receipts))
    available = _receipt_date(receipt)
    if available > evaluation_date:
        raise ValueError(f"Historical target filing is later than evaluation date: {period_id}")
    if revenue - cost != gross:
        raise ValueError(f"Historical target accounting identity failed: {period_id}")
    captured_bytes = _canonical_json_bytes(raw_payload)
    return HistoricalTargetObservation(
        period_id=period_id,
        report_code=report_code,
        receipt_no=receipt,
        receipt_date=available,
        revenue_krw=revenue,
        cost_of_sales_krw=cost,
        gross_profit_krw=gross,
        gross_profit_krw_million=gross / 1_000_000.0,
        raw_payload_sha256=_sha(raw_payload),
        captured_payload_bytes_sha256=_sha_bytes(captured_bytes),
    )


def collect_historical_target_payloads(
    client: OpenDartReadOnlyClient,
    execution: FrozenHistoricalEvaluationExecution,
) -> dict[str, object]:
    """Read only the twenty frozen historical outcomes; never request protected future rows."""

    corp = client.resolve_stock_codes([execution.ticker])[execution.ticker]
    payloads: dict[str, object] = {}
    for period_id in execution.exact_target_periods:
        batch = client.financial_statements(
            corp,
            business_year=int(period_id[:4]),
            report_code=execution.report_code_for(period_id),
            fs_div=execution.fs_div,
        )
        if batch.corp.stock_code != execution.ticker:
            raise ValueError("Historical target OpenDART batch ticker drifted")
        payloads[period_id] = batch.raw_payload
    if tuple(payloads) != execution.exact_target_periods:
        raise ValueError("Historical target payload collection order drifted")
    return payloads


def _validate_scope_and_bundle(
    execution: FrozenHistoricalEvaluationExecution,
    scope: FrozenExactTwentyPeriodExAnteScope,
    bundle: PointInTimeFeatureBundle,
    estimator: FrozenExAnteEstimatorSelection,
) -> dict[str, tuple[tuple[str, float], ...]]:
    if scope.target_periods != execution.exact_target_periods:
        raise ValueError("Historical execution diverged from frozen scope periods")
    if scope.combined_bundle_evidence_id != bundle.evidence_id:
        raise ValueError("Historical execution combined bundle evidence drifted")
    if scope.estimator_freeze_evidence_id != estimator.evidence_id:
        raise ValueError("Historical execution estimator-freeze evidence drifted")
    if scope.feature_ids != estimator.feature_ids or scope.feature_ids != _EXPECTED_FEATURES:
        raise ValueError("Historical execution feature schema drifted")
    if scope.target_join_authorized or scope.historical_target_values_read:
        raise ValueError("Historical execution input scope is no longer target-blind")
    if bundle.target_values_included or len(bundle.observations) != 100:
        raise ValueError("Historical execution feature bundle boundary drifted")
    feature_order = {feature_id: index for index, feature_id in enumerate(_EXPECTED_FEATURES)}
    by_period: dict[str, list[tuple[str, float]]] = {}
    for observation in bundle.observations:
        by_period.setdefault(observation.period_id, []).append(
            (observation.feature_id, float(observation.value))
        )
    if tuple(sorted(by_period)) != execution.exact_target_periods:
        raise ValueError("Historical execution bundle period set drifted")
    result: dict[str, tuple[tuple[str, float], ...]] = {}
    for period_id in execution.exact_target_periods:
        ordered = tuple(
            sorted(by_period[period_id], key=lambda item: feature_order[item[0]])
        )
        if tuple(key for key, _value in ordered) != _EXPECTED_FEATURES:
            raise ValueError(f"Historical execution feature row drifted: {period_id}")
        result[period_id] = ordered
    return result


def _target_observation_payload(item: HistoricalTargetObservation) -> dict[str, object]:
    payload = asdict(item)
    payload["receipt_date"] = item.receipt_date.isoformat()
    return payload


def _joined_row_payload(item: JoinedHistoricalRow) -> dict[str, object]:
    return {
        "period_id": item.period_id,
        "features": [[key, value] for key, value in item.features],
        "target_company_gross_profit_krw_million": (
            item.target_company_gross_profit_krw_million
        ),
        "target_receipt_no": item.target_receipt_no,
        "target_raw_payload_sha256": item.target_raw_payload_sha256,
        "target_captured_payload_bytes_sha256": (
            item.target_captured_payload_bytes_sha256
        ),
    }


def _target_join_payload(join: HistoricalTargetJoin) -> dict[str, object]:
    return {
        "execution_evidence_id": join.execution_evidence_id,
        "scope_evidence_id": join.scope_evidence_id,
        "combined_bundle_evidence_id": join.combined_bundle_evidence_id,
        "target_source_evidence_id": join.target_source_evidence_id,
        "evaluation_date": join.evaluation_date.isoformat(),
        "target_periods": list(join.target_periods),
        "target_observations": [
            _target_observation_payload(item) for item in join.target_observations
        ],
        "rows": [_joined_row_payload(item) for item in join.rows],
        "status": join.status,
        "historical_target_values_read": join.historical_target_values_read,
        "target_join_run": join.target_join_run,
        "estimator_fit_run": join.estimator_fit_run,
        "historical_backtest_run": join.historical_backtest_run,
        "q1_used_for_selection": join.q1_used_for_selection,
        "q3_target_read": join.q3_target_read,
        "q3_source_outcome_loaded": join.q3_source_outcome_loaded,
        "numeric_forward_forecast_enabled": join.numeric_forward_forecast_enabled,
    }


def build_historical_target_join(
    execution: FrozenHistoricalEvaluationExecution,
    scope: FrozenExactTwentyPeriodExAnteScope,
    bundle: PointInTimeFeatureBundle,
    estimator: FrozenExAnteEstimatorSelection,
    *,
    evaluation_date: date,
    raw_payloads: dict[str, object],
) -> HistoricalTargetJoin:
    """Cross the historical target boundary once, against only the already-frozen scope."""

    features = _validate_scope_and_bundle(execution, scope, bundle, estimator)
    if tuple(raw_payloads) != execution.exact_target_periods:
        raise ValueError("Historical target join requires all twenty raw payloads in frozen order")
    observations = tuple(
        extract_historical_target_observation(
            execution,
            period_id,
            raw_payloads[period_id],
            evaluation_date=evaluation_date,
        )
        for period_id in execution.exact_target_periods
    )
    source_payload = {
        "execution_evidence_id": execution.evidence_id,
        "evaluation_date": evaluation_date.isoformat(),
        "target_observations": [_target_observation_payload(item) for item in observations],
    }
    target_source_evidence_id = _sha(source_payload)
    rows = tuple(
        JoinedHistoricalRow(
            period_id=item.period_id,
            features=features[item.period_id],
            target_company_gross_profit_krw_million=item.gross_profit_krw_million,
            target_receipt_no=item.receipt_no,
            target_raw_payload_sha256=item.raw_payload_sha256,
            target_captured_payload_bytes_sha256=item.captured_payload_bytes_sha256,
        )
        for item in observations
    )
    provisional = HistoricalTargetJoin(
        evidence_id="0" * 64,
        execution_evidence_id=execution.evidence_id,
        scope_evidence_id=scope.evidence_id,
        combined_bundle_evidence_id=bundle.evidence_id,
        target_source_evidence_id=target_source_evidence_id,
        evaluation_date=evaluation_date,
        target_periods=execution.exact_target_periods,
        target_observations=observations,
        rows=rows,
    )
    return replace(provisional, evidence_id=_sha(_target_join_payload(provisional)))


def persist_historical_target_join(
    join: HistoricalTargetJoin,
    raw_payloads: dict[str, object],
    *,
    output: str | Path = DEFAULT_COMPANY_GP_EX_ANTE_HISTORICAL_OUTPUT,
) -> Path:
    """Lock target payloads immutably and refuse any later target refresh."""

    if _sha(_target_join_payload(join)) != join.evidence_id:
        raise ValueError("Historical target join evidence hash drifted before persistence")
    if tuple(raw_payloads) != join.target_periods:
        raise ValueError("Historical target join raw payload set drifted before persistence")
    for observation in join.target_observations:
        raw_bytes = _canonical_json_bytes(raw_payloads[observation.period_id])
        if _sha_bytes(raw_bytes) != observation.captured_payload_bytes_sha256:
            raise ValueError(f"Historical target captured bytes drifted: {observation.period_id}")
        if _sha(raw_payloads[observation.period_id]) != observation.raw_payload_sha256:
            raise ValueError(f"Historical target canonical payload drifted: {observation.period_id}")

    root = Path(output)
    root.mkdir(parents=True, exist_ok=True)
    pointer = root / "latest_historical_target_join.json"
    if pointer.exists():
        existing = load_historical_target_join(pointer)
        if existing.evidence_id != join.evidence_id:
            raise ValueError(
                "Historical target join is already locked; post-join target refresh is prohibited"
            )
        return pointer

    artifact = root / f"target-{join.evidence_id}"
    temporary = root / f".{artifact.name}.tmp"
    if artifact.exists() or temporary.exists():
        raise ValueError("Historical target join artifact path already exists unexpectedly")
    temporary.mkdir()
    try:
        raw_root = temporary / "raw"
        raw_root.mkdir()
        for observation in join.target_observations:
            (raw_root / f"{observation.period_id}.json").write_bytes(
                _canonical_json_bytes(raw_payloads[observation.period_id])
            )
        artifact_payload = {
            "schema_version": 1,
            "status": _TARGET_JOIN_STATUS,
            "join": {"evidence_id": join.evidence_id, **_target_join_payload(join)},
        }
        artifact_bytes = _canonical_json_bytes(artifact_payload)
        (temporary / "target_join.json").write_bytes(artifact_bytes)
        temporary.rename(artifact)
        pointer_payload = {
            **artifact_payload,
            "artifact_directory": str(artifact.resolve()),
        }
        pointer_tmp = root / ".latest_historical_target_join.json.tmp"
        pointer_tmp.write_bytes(_canonical_json_bytes(pointer_payload))
        pointer_tmp.replace(pointer)
    except Exception:
        if temporary.exists():
            shutil.rmtree(temporary)
        raise
    replayed = load_historical_target_join(pointer)
    if replayed.evidence_id != join.evidence_id:
        raise ValueError("Historical target join failed exact persistence replay")
    return pointer


def load_historical_target_join(
    path: str | Path = DEFAULT_COMPANY_GP_EX_ANTE_TARGET_JOIN,
) -> HistoricalTargetJoin:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    root = _mapping(raw, "Historical target join artifact")
    if root.get("schema_version") != 1 or root.get("status") != _TARGET_JOIN_STATUS:
        raise ValueError("Historical target join artifact status is invalid")
    body = _mapping(root.get("join"), "Historical target join body")
    observations: list[HistoricalTargetObservation] = []
    for raw_item in _array(body.get("target_observations"), "target_observations"):
        item = _mapping(raw_item, "Historical target observation")
        observations.append(
            HistoricalTargetObservation(
                period_id=str(item.get("period_id", "")),
                report_code=str(item.get("report_code", "")),
                receipt_no=str(item.get("receipt_no", "")),
                receipt_date=date.fromisoformat(str(item.get("receipt_date", ""))),
                revenue_krw=int(str(item.get("revenue_krw", "0"))),
                cost_of_sales_krw=int(str(item.get("cost_of_sales_krw", "0"))),
                gross_profit_krw=int(str(item.get("gross_profit_krw", "0"))),
                gross_profit_krw_million=float(
                    str(item.get("gross_profit_krw_million", "nan"))
                ),
                raw_payload_sha256=str(item.get("raw_payload_sha256", "")),
                captured_payload_bytes_sha256=str(
                    item.get("captured_payload_bytes_sha256", "")
                ),
            )
        )
    rows: list[JoinedHistoricalRow] = []
    for raw_item in _array(body.get("rows"), "Historical joined rows"):
        item = _mapping(raw_item, "Historical joined row")
        features_raw = _array(item.get("features"), "Historical joined features")
        features: list[tuple[str, float]] = []
        for raw_pair in features_raw:
            pair = _array(raw_pair, "Historical joined feature pair")
            if len(pair) != 2:
                raise ValueError("Historical joined feature pair must have two entries")
            features.append((str(pair[0]), float(str(pair[1]))))
        rows.append(
            JoinedHistoricalRow(
                period_id=str(item.get("period_id", "")),
                features=tuple(features),
                target_company_gross_profit_krw_million=float(
                    str(item.get("target_company_gross_profit_krw_million", "nan"))
                ),
                target_receipt_no=str(item.get("target_receipt_no", "")),
                target_raw_payload_sha256=str(item.get("target_raw_payload_sha256", "")),
                target_captured_payload_bytes_sha256=str(
                    item.get("target_captured_payload_bytes_sha256", "")
                ),
            )
        )
    join = HistoricalTargetJoin(
        evidence_id=str(body.get("evidence_id", "")),
        execution_evidence_id=str(body.get("execution_evidence_id", "")),
        scope_evidence_id=str(body.get("scope_evidence_id", "")),
        combined_bundle_evidence_id=str(body.get("combined_bundle_evidence_id", "")),
        target_source_evidence_id=str(body.get("target_source_evidence_id", "")),
        evaluation_date=date.fromisoformat(str(body.get("evaluation_date", ""))),
        target_periods=tuple(
            str(item) for item in _array(body.get("target_periods"), "target_periods")
        ),
        target_observations=tuple(observations),
        rows=tuple(rows),
        status=str(body.get("status", "")),
        historical_target_values_read=body.get("historical_target_values_read") is True,
        target_join_run=body.get("target_join_run") is True,
        estimator_fit_run=body.get("estimator_fit_run") is True,
        historical_backtest_run=body.get("historical_backtest_run") is True,
        q1_used_for_selection=body.get("q1_used_for_selection") is True,
        q3_target_read=body.get("q3_target_read") is True,
        q3_source_outcome_loaded=body.get("q3_source_outcome_loaded") is True,
        numeric_forward_forecast_enabled=(
            body.get("numeric_forward_forecast_enabled") is True
        ),
    )
    if _sha(_target_join_payload(join)) != join.evidence_id:
        raise ValueError("Historical target join evidence hash mismatch")
    artifact_directory = root.get("artifact_directory")
    if artifact_directory:
        raw_root = Path(str(artifact_directory)) / "raw"
        for observation in join.target_observations:
            raw_path = raw_root / f"{observation.period_id}.json"
            if not raw_path.is_file():
                raise ValueError(f"Historical target raw archive missing: {observation.period_id}")
            raw_bytes = raw_path.read_bytes()
            if _sha_bytes(raw_bytes) != observation.captured_payload_bytes_sha256:
                raise ValueError(f"Historical target raw archive hash mismatch: {observation.period_id}")
    return join


def _benchmark_folds(
    execution: FrozenHistoricalEvaluationExecution,
    join: HistoricalTargetJoin,
) -> tuple[BenchmarkFoldScore, ...]:
    folds: list[BenchmarkFoldScore] = []
    start = execution.shared_initial_training_rows
    for fold_index, score_index in enumerate(
        range(start, start + execution.scored_fold_count),
        start=1,
    ):
        row = join.rows[score_index]
        features = row.feature_map()
        prediction = features[execution.benchmark_prediction_feature]
        actual = row.target_company_gross_profit_krw_million
        folds.append(
            BenchmarkFoldScore(
                fold_number=fold_index,
                score_period=row.period_id,
                training_row_count=score_index,
                actual_krw_million=actual,
                prediction_krw_million=prediction,
                absolute_error_krw_million=abs(actual - prediction),
            )
        )
    return tuple(folds)


def _failed_candidate_fold(
    *,
    fold_number: int,
    score_period: str,
    training_row_count: int,
    reason: str,
    design_rank: int | None = None,
    residual_dof: int | None = None,
    condition_number: float | None = None,
) -> CandidateFoldScore:
    return CandidateFoldScore(
        fold_number=fold_number,
        score_period=score_period,
        training_row_count=training_row_count,
        prediction_krw_million=None,
        absolute_error_krw_million=None,
        design_rank=design_rank,
        residual_degrees_of_freedom=residual_dof,
        condition_number=condition_number,
        standardized_coefficients=None,
        valid=False,
        failure_reason=reason,
    )


def _candidate_fold(
    candidate: FrozenExAnteEstimatorCandidate,
    join: HistoricalTargetJoin,
    *,
    fold_number: int,
    score_index: int,
) -> CandidateFoldScore:
    train_rows = join.rows[:score_index]
    score_row = join.rows[score_index]
    x_train = np.asarray(
        [
            [row.feature_map()[feature_id] for feature_id in candidate.predictors]
            for row in train_rows
        ],
        dtype=float,
    )
    y_train = np.asarray(
        [row.target_company_gross_profit_krw_million for row in train_rows],
        dtype=float,
    )
    x_score = np.asarray(
        [score_row.feature_map()[feature_id] for feature_id in candidate.predictors],
        dtype=float,
    )
    if not np.isfinite(x_train).all() or not np.isfinite(y_train).all() or not np.isfinite(x_score).all():
        return _failed_candidate_fold(
            fold_number=fold_number,
            score_period=score_row.period_id,
            training_row_count=score_index,
            reason="non_finite_training_or_score_value",
        )
    means = np.mean(x_train, axis=0)
    scales = np.std(x_train, axis=0, ddof=0)
    if np.any(~np.isfinite(scales)) or np.any(scales <= 0.0):
        return _failed_candidate_fold(
            fold_number=fold_number,
            score_period=score_row.period_id,
            training_row_count=score_index,
            reason="zero_or_non_finite_training_predictor_scale",
        )
    standardized_train = (x_train - means) / scales
    standardized_score = (x_score - means) / scales
    design = np.column_stack((np.ones(len(train_rows), dtype=float), standardized_train))
    rank = int(np.linalg.matrix_rank(design))
    residual_dof = len(train_rows) - rank
    if rank != candidate.parameter_count:
        return _failed_candidate_fold(
            fold_number=fold_number,
            score_period=score_row.period_id,
            training_row_count=score_index,
            reason="training_design_not_full_column_rank",
            design_rank=rank,
            residual_dof=residual_dof,
        )
    condition_number = float(np.linalg.cond(design))
    if residual_dof <= 0:
        return _failed_candidate_fold(
            fold_number=fold_number,
            score_period=score_row.period_id,
            training_row_count=score_index,
            reason="training_residual_degrees_of_freedom_not_positive",
            design_rank=rank,
            residual_dof=residual_dof,
            condition_number=condition_number,
        )
    coefficients, _residuals, _rank, _singular = np.linalg.lstsq(design, y_train, rcond=None)
    score_design = np.concatenate((np.ones(1, dtype=float), standardized_score))
    prediction = float(score_design @ coefficients)
    actual = score_row.target_company_gross_profit_krw_million
    if not math.isfinite(prediction) or not math.isfinite(condition_number):
        return _failed_candidate_fold(
            fold_number=fold_number,
            score_period=score_row.period_id,
            training_row_count=score_index,
            reason="non_finite_fit_output",
            design_rank=rank,
            residual_dof=residual_dof,
            condition_number=condition_number,
        )
    return CandidateFoldScore(
        fold_number=fold_number,
        score_period=score_row.period_id,
        training_row_count=score_index,
        prediction_krw_million=prediction,
        absolute_error_krw_million=abs(actual - prediction),
        design_rank=rank,
        residual_degrees_of_freedom=residual_dof,
        condition_number=condition_number,
        standardized_coefficients=tuple(float(value) for value in coefficients),
        valid=True,
        failure_reason=None,
    )


def _coefficient_stability(folds: tuple[CandidateFoldScore, ...]) -> float | None:
    valid = [item for item in folds if item.standardized_coefficients is not None]
    if len(valid) < 2:
        return None
    deltas: list[float] = []
    for previous, current in zip(valid, valid[1:], strict=False):
        assert previous.standardized_coefficients is not None
        assert current.standardized_coefficients is not None
        left = np.asarray(previous.standardized_coefficients, dtype=float)
        right = np.asarray(current.standardized_coefficients, dtype=float)
        deltas.append(float(np.linalg.norm(right - left, ord=2)))
    return max(deltas) if deltas else None


def _candidate_backtest(
    execution: FrozenHistoricalEvaluationExecution,
    candidate: FrozenExAnteEstimatorCandidate,
    join: HistoricalTargetJoin,
    *,
    benchmark_mae: float,
) -> CandidateBacktestResult:
    folds = tuple(
        _candidate_fold(
            candidate,
            join,
            fold_number=fold_number,
            score_index=score_index,
        )
        for fold_number, score_index in enumerate(
            range(
                execution.shared_initial_training_rows,
                execution.shared_initial_training_rows + execution.scored_fold_count,
            ),
            start=1,
        )
    )
    every_valid = all(item.valid for item in folds)
    aggregate: float | None = None
    beats = False
    if every_valid:
        errors = [
            cast(float, item.absolute_error_krw_million)
            for item in folds
        ]
        aggregate = float(np.mean(np.asarray(errors, dtype=float)))
        beats = aggregate < benchmark_mae
    return CandidateBacktestResult(
        candidate_id=candidate.candidate_id,
        parameter_count=candidate.parameter_count,
        predictors=candidate.predictors,
        folds=folds,
        aggregate_mae_krw_million=aggregate,
        every_fold_valid=every_valid,
        strictly_beats_benchmark=beats,
        max_standardized_coefficient_delta_l2=_coefficient_stability(folds),
    )


def _benchmark_mae(folds: tuple[BenchmarkFoldScore, ...]) -> float:
    return float(
        np.mean(np.asarray([item.absolute_error_krw_million for item in folds], dtype=float))
    )


def _backtest_payload(result: HistoricalBacktestResult) -> dict[str, object]:
    return {
        "execution_evidence_id": result.execution_evidence_id,
        "scope_evidence_id": result.scope_evidence_id,
        "target_join_evidence_id": result.target_join_evidence_id,
        "estimator_freeze_evidence_id": result.estimator_freeze_evidence_id,
        "target_periods": list(result.target_periods),
        "benchmark_id": result.benchmark_id,
        "benchmark_folds": [asdict(item) for item in result.benchmark_folds],
        "benchmark_mae_krw_million": result.benchmark_mae_krw_million,
        "candidates": [asdict(item) for item in result.candidates],
        "selected_candidate_id": result.selected_candidate_id,
        "selection_status": result.selection_status,
        "status": result.status,
        "historical_target_values_read": result.historical_target_values_read,
        "target_join_run": result.target_join_run,
        "estimator_fit_run": result.estimator_fit_run,
        "historical_backtest_run": result.historical_backtest_run,
        "final_estimator_selected": result.final_estimator_selected,
        "q1_used_for_selection": result.q1_used_for_selection,
        "q3_target_read": result.q3_target_read,
        "q3_source_outcome_loaded": result.q3_source_outcome_loaded,
        "q3_evaluated": result.q3_evaluated,
        "numeric_forward_forecast_enabled": result.numeric_forward_forecast_enabled,
    }


def run_frozen_historical_backtest(
    execution: FrozenHistoricalEvaluationExecution,
    scope: FrozenExactTwentyPeriodExAnteScope,
    estimator: FrozenExAnteEstimatorSelection,
    join: HistoricalTargetJoin,
) -> HistoricalBacktestResult:
    if join.execution_evidence_id != execution.evidence_id:
        raise ValueError("Historical backtest execution evidence drifted")
    if join.scope_evidence_id != scope.evidence_id:
        raise ValueError("Historical backtest scope evidence drifted")
    if scope.estimator_freeze_evidence_id != estimator.evidence_id:
        raise ValueError("Historical backtest estimator freeze evidence drifted")
    if join.target_periods != execution.exact_target_periods:
        raise ValueError("Historical backtest joined period scope drifted")
    if tuple(item.candidate_id for item in estimator.candidates) != _EXPECTED_CANDIDATES:
        raise ValueError("Historical backtest candidate manifest order drifted")
    if estimator.shared_initial_training_rows != execution.shared_initial_training_rows:
        raise ValueError("Historical backtest initial training geometry drifted")
    if estimator.minimum_scored_folds != execution.scored_fold_count:
        raise ValueError("Historical backtest scored-fold geometry drifted")
    if estimator.benchmark_id != execution.benchmark_id:
        raise ValueError("Historical backtest benchmark binding drifted")
    if estimator.benchmark_prediction_rule != execution.benchmark_prediction_feature:
        raise ValueError("Historical backtest benchmark rule drifted")
    if not estimator.candidate_must_strictly_beat_benchmark:
        raise ValueError("Historical backtest estimator freeze no longer requires strict beat")

    benchmark_folds = _benchmark_folds(execution, join)
    benchmark_mae = _benchmark_mae(benchmark_folds)
    candidates = tuple(
        _candidate_backtest(
            execution,
            candidate,
            join,
            benchmark_mae=benchmark_mae,
        )
        for candidate in estimator.candidates
    )
    passing = [
        (index, item)
        for index, item in enumerate(candidates)
        if item.strictly_beats_benchmark and item.aggregate_mae_krw_million is not None
    ]
    selected_id: str | None = None
    selection_status = _NO_SELECTION
    if passing:
        _selected_index, selected = min(
            passing,
            key=lambda pair: (
                cast(float, pair[1].aggregate_mae_krw_million),
                pair[1].parameter_count,
                pair[0],
            ),
        )
        selected_id = selected.candidate_id
        selection_status = _SELECTION_COMPLETE
    provisional = HistoricalBacktestResult(
        evidence_id="0" * 64,
        execution_evidence_id=execution.evidence_id,
        scope_evidence_id=scope.evidence_id,
        target_join_evidence_id=join.evidence_id,
        estimator_freeze_evidence_id=estimator.evidence_id,
        target_periods=execution.exact_target_periods,
        benchmark_id=execution.benchmark_id,
        benchmark_folds=benchmark_folds,
        benchmark_mae_krw_million=benchmark_mae,
        candidates=candidates,
        selected_candidate_id=selected_id,
        selection_status=selection_status,
        final_estimator_selected=selected_id is not None,
    )
    return replace(provisional, evidence_id=_sha(_backtest_payload(provisional)))


def persist_historical_backtest(
    result: HistoricalBacktestResult,
    *,
    output: str | Path = DEFAULT_COMPANY_GP_EX_ANTE_HISTORICAL_OUTPUT,
) -> Path:
    if _sha(_backtest_payload(result)) != result.evidence_id:
        raise ValueError("Historical backtest evidence hash drifted before persistence")
    root = Path(output)
    root.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": 1,
        "status": _BACKTEST_STATUS,
        "backtest": {"evidence_id": result.evidence_id, **_backtest_payload(result)},
    }
    encoded = _canonical_json_bytes(payload)
    immutable = root / f"backtest-{result.evidence_id}.json"
    if immutable.exists():
        if immutable.read_bytes() != encoded:
            raise ValueError("Historical backtest immutable artifact drifted")
    else:
        immutable.write_bytes(encoded)
    pointer = root / "latest_historical_backtest.json"
    temporary = root / ".latest_historical_backtest.json.tmp"
    temporary.write_bytes(encoded)
    temporary.replace(pointer)
    return pointer


def run_first_historical_evaluation(
    client: OpenDartReadOnlyClient,
    *,
    evaluation_date: date,
    execution_path: str | Path = DEFAULT_COMPANY_GP_EX_ANTE_HISTORICAL_EXECUTION,
    scope_path: str | Path = DEFAULT_COMPANY_GP_EX_ANTE_SCOPE_FREEZE,
    bundle_path: str | Path = DEFAULT_EX_ANTE_PIT_PANEL_EXPANSION_BUNDLE,
    estimator_path: str | Path = DEFAULT_COMPANY_GP_EX_ANTE_ESTIMATOR_FREEZE,
    output: str | Path = DEFAULT_COMPANY_GP_EX_ANTE_HISTORICAL_OUTPUT,
) -> tuple[HistoricalTargetJoin, HistoricalBacktestResult, bool]:
    """Run or replay the first target join; an existing join can never be refreshed."""

    execution = load_frozen_historical_evaluation_execution(execution_path)
    scope = load_frozen_exact_twenty_period_ex_ante_scope(scope_path)
    bundle = load_point_in_time_feature_bundle(bundle_path)
    estimator = load_frozen_ex_ante_estimator_selection(estimator_path)
    _validate_scope_and_bundle(execution, scope, bundle, estimator)
    root = Path(output)
    target_pointer = root / "latest_historical_target_join.json"
    reused_locked_targets = target_pointer.is_file()
    if reused_locked_targets:
        join = load_historical_target_join(target_pointer)
        if join.execution_evidence_id != execution.evidence_id:
            raise ValueError("Locked historical target join execution evidence drifted")
        if join.scope_evidence_id != scope.evidence_id:
            raise ValueError("Locked historical target join scope evidence drifted")
        if join.combined_bundle_evidence_id != bundle.evidence_id:
            raise ValueError("Locked historical target join feature-bundle evidence drifted")
    else:
        raw_payloads = collect_historical_target_payloads(client, execution)
        join = build_historical_target_join(
            execution,
            scope,
            bundle,
            estimator,
            evaluation_date=evaluation_date,
            raw_payloads=raw_payloads,
        )
        persist_historical_target_join(join, raw_payloads, output=root)
    result = run_frozen_historical_backtest(execution, scope, estimator, join)
    persist_historical_backtest(result, output=root)
    return join, result, reused_locked_targets


__all__ = [
    "DEFAULT_COMPANY_GP_EX_ANTE_HISTORICAL_BACKTEST",
    "DEFAULT_COMPANY_GP_EX_ANTE_HISTORICAL_EXECUTION",
    "DEFAULT_COMPANY_GP_EX_ANTE_HISTORICAL_OUTPUT",
    "DEFAULT_COMPANY_GP_EX_ANTE_TARGET_JOIN",
    "BenchmarkFoldScore",
    "CandidateBacktestResult",
    "CandidateFoldScore",
    "FrozenHistoricalEvaluationExecution",
    "HistoricalBacktestResult",
    "HistoricalTargetJoin",
    "HistoricalTargetObservation",
    "JoinedHistoricalRow",
    "build_historical_target_join",
    "collect_historical_target_payloads",
    "extract_historical_target_observation",
    "load_frozen_historical_evaluation_execution",
    "load_historical_target_join",
    "persist_historical_backtest",
    "persist_historical_target_join",
    "run_first_historical_evaluation",
    "run_frozen_historical_backtest",
]
