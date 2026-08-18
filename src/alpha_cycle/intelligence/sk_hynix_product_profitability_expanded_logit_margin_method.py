"""Frozen v3 clean-panel bounded product-margin method for SK hynix.

V3 is registered only after the 2017Q1-2018Q3 source expansion closed and the 21-row clean
historical direction design plus 22-row contaminated-development design were both observed
full rank.  The already-seen 2026Q1 outcome is stress-report-only and is excluded from fit and
model-selection gates.  The reserved 2026Q3 outcome remains outside this module.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import cast

import yaml

DEFAULT_EXPANDED_LOGIT_MARGIN_METHOD = Path(
    "config/skhynix_product_profitability_expanded_logit_margin_method.v3.yaml"
)
_EXPECTED_TRAINING_PERIODS = (
    "2017Q1",
    "2017Q2",
    "2017Q3",
    "2018Q1",
    "2018Q2",
    "2018Q3",
    "2019Q1",
    "2019Q2",
    "2019Q3",
    "2020Q1",
    "2020Q2",
    "2020Q3",
    "2023Q1",
    "2023Q2",
    "2023Q3",
    "2024Q1",
    "2024Q2",
    "2024Q3",
    "2025Q1",
    "2025Q2",
    "2025Q3",
)
_EXPECTED_PARAMETERS = (
    "dram_logit_intercept",
    "dram_asp_direction_effect",
    "dram_bit_volume_direction_effect",
    "nand_logit_intercept",
    "nand_asp_direction_effect",
    "nand_bit_volume_direction_effect",
    "other_logit_margin",
)


def _mapping(value: object, label: str) -> dict[object, object]:
    if not isinstance(value, dict):
        raise ValueError(f"Expanded logit-margin {label} must be an object")
    return cast(dict[object, object], value)


def _strings(value: object, label: str) -> tuple[str, ...]:
    if not isinstance(value, list):
        raise ValueError(f"Expanded logit-margin {label} must be an array")
    result = tuple(str(item).strip() for item in value)
    if not result or any(not item for item in result):
        raise ValueError(f"Expanded logit-margin {label} cannot contain empty values")
    return result


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


@dataclass(frozen=True)
class ExpandedLogitMarginSolverContract:
    solver_id: str
    optimization_scale: str
    metrics_reported_in_original_krw_million: bool
    damping_matrix: str
    initial_damping: float
    damping_increase_factor: float
    damping_decrease_factor: float
    maximum_iterations: int
    maximum_rejected_steps_per_iteration: int
    parameter_step_tolerance: float
    relative_sse_tolerance: float
    minimum_initialization_probability: float
    maximum_initialization_probability: float

    def __post_init__(self) -> None:
        if self.solver_id != "deterministic_damped_gauss_newton_v1":
            raise ValueError("Expanded logit-margin solver id drifted")
        if self.optimization_scale != "mean_training_company_revenue_krw_million":
            raise ValueError("Expanded logit-margin optimization scale drifted")
        if not self.metrics_reported_in_original_krw_million:
            raise ValueError("Expanded logit-margin metrics unit contract drifted")
        if self.damping_matrix != "diagonal_jtj_with_floor_1e-12":
            raise ValueError("Expanded logit-margin damping matrix drifted")
        if self.initial_damping != 0.001:
            raise ValueError("Expanded logit-margin initial damping drifted")
        if (self.damping_increase_factor, self.damping_decrease_factor) != (10.0, 10.0):
            raise ValueError("Expanded logit-margin damping factors drifted")
        if (self.maximum_iterations, self.maximum_rejected_steps_per_iteration) != (500, 12):
            raise ValueError("Expanded logit-margin iteration contract drifted")
        if (self.parameter_step_tolerance, self.relative_sse_tolerance) != (1e-10, 1e-12):
            raise ValueError("Expanded logit-margin convergence tolerances drifted")
        if (
            self.minimum_initialization_probability,
            self.maximum_initialization_probability,
        ) != (1e-6, 0.999999):
            raise ValueError("Expanded logit-margin initialization bounds drifted")


@dataclass(frozen=True)
class ExpandedPrefitIdentificationGate:
    required_row_count: int
    required_parameter_count: int
    required_residual_degrees_of_freedom: int
    require_full_direction_design_rank: bool
    require_all_leave_one_out_direction_designs_full_rank: bool
    normalized_direction_design_condition_number_report_only: bool
    leave_one_out_condition_numbers_report_only: bool

    def __post_init__(self) -> None:
        if (self.required_row_count, self.required_parameter_count) != (21, 7):
            raise ValueError("Expanded prefit row/parameter gate drifted")
        if self.required_residual_degrees_of_freedom != 14:
            raise ValueError("Expanded prefit residual DOF gate drifted")
        if not all(
            (
                self.require_full_direction_design_rank,
                self.require_all_leave_one_out_direction_designs_full_rank,
                self.normalized_direction_design_condition_number_report_only,
                self.leave_one_out_condition_numbers_report_only,
            )
        ):
            raise ValueError("Expanded prefit identification gate must remain fail-closed")


@dataclass(frozen=True)
class ExpandedLogitMarginValidationGate:
    required_row_count: int
    required_parameter_count: int
    required_residual_degrees_of_freedom: int
    require_full_jacobian_column_rank: bool
    require_optimizer_convergence: bool
    require_all_leave_one_out_folds_converged: bool
    require_all_leave_one_out_jacobians_full_rank: bool
    benchmark_id: str
    require_loocv_mae_better_than_benchmark: bool
    require_all_component_margins_inside_unit_interval: bool
    normalized_jacobian_condition_number_report_only: bool
    parameter_jackknife_report_only: bool
    contaminated_2026q1_stress_report_only: bool

    def __post_init__(self) -> None:
        if (self.required_row_count, self.required_parameter_count) != (21, 7):
            raise ValueError("Expanded validation row/parameter gate drifted")
        if self.required_residual_degrees_of_freedom != 14:
            raise ValueError("Expanded validation residual DOF gate drifted")
        required = (
            self.require_full_jacobian_column_rank,
            self.require_optimizer_convergence,
            self.require_all_leave_one_out_folds_converged,
            self.require_all_leave_one_out_jacobians_full_rank,
            self.require_loocv_mae_better_than_benchmark,
            self.require_all_component_margins_inside_unit_interval,
            self.normalized_jacobian_condition_number_report_only,
            self.parameter_jackknife_report_only,
            self.contaminated_2026q1_stress_report_only,
        )
        if not all(required):
            raise ValueError("Expanded validation gate must remain fail-closed")
        if self.benchmark_id != "leave_one_out_mean_gross_margin_scaled_revenue":
            raise ValueError("Expanded benchmark id drifted")


@dataclass(frozen=True)
class FrozenExpandedLogitMarginMethod:
    evidence_id: str
    method_id: str
    method_version: str
    status: str
    ticker: str
    target_metric: str
    training_periods: tuple[str, ...]
    contaminated_stress_periods: tuple[str, ...]
    untouched_holdout_period: str
    parameters: tuple[str, ...]
    solver: ExpandedLogitMarginSolverContract
    prefit_identification_gate: ExpandedPrefitIdentificationGate
    validation_gate: ExpandedLogitMarginValidationGate
    v1_training_seen: bool
    v1_q1_holdout_seen: bool
    v2_coefficients_seen: bool
    v2_metrics_seen: bool
    v2_gate_failure_seen: bool
    third_wave_source_closeout_seen: bool
    third_wave_preflight_seen: bool
    clean_21_full_rank_seen: bool
    development_22_full_rank_seen: bool
    v3_coefficients_seen_before_freeze: bool
    v3_fit_metrics_seen_before_freeze: bool
    q3_outcome_seen_before_freeze: bool
    method_version_frozen: bool
    q1_stress_only: bool
    q1_used_for_fit: bool
    q1_used_for_model_selection_gate: bool
    q2_not_claimed_untouched: bool
    q3_reserved_future_holdout: bool
    numeric_forward_forecast_enabled: bool
    fair_value_estimate_enabled: bool
    target_price_enabled: bool
    decision_score_enabled: bool

    def __post_init__(self) -> None:
        if self.method_id != "skhynix_product_profitability_expanded_logit_margin_nls":
            raise ValueError("Expanded logit-margin method id drifted")
        if self.method_version != "3.0-frozen-pre-fit" or self.status != "frozen_pre_fit":
            raise ValueError("Expanded logit-margin method version/status drifted")
        if self.ticker != "000660" or self.target_metric != "company_gross_profit_krw_million":
            raise ValueError("Expanded logit-margin issuer/target drifted")
        if self.training_periods != _EXPECTED_TRAINING_PERIODS:
            raise ValueError("Expanded logit-margin training periods drifted")
        if self.contaminated_stress_periods != ("2026Q1",):
            raise ValueError("Expanded logit-margin contaminated stress binding drifted")
        if self.untouched_holdout_period != "2026Q3" or self.parameters != _EXPECTED_PARAMETERS:
            raise ValueError("Expanded logit-margin holdout/parameter contract drifted")
        exposure = (
            self.v1_training_seen,
            self.v1_q1_holdout_seen,
            self.v2_coefficients_seen,
            self.v2_metrics_seen,
            self.v2_gate_failure_seen,
            self.third_wave_source_closeout_seen,
            self.third_wave_preflight_seen,
            self.clean_21_full_rank_seen,
            self.development_22_full_rank_seen,
        )
        if not all(exposure):
            raise ValueError("Expanded logit-margin freeze provenance is incomplete")
        if self.v3_coefficients_seen_before_freeze or self.v3_fit_metrics_seen_before_freeze:
            raise ValueError("Expanded logit-margin v3 outcomes were seen before freeze")
        if self.q3_outcome_seen_before_freeze or not self.method_version_frozen:
            raise ValueError("Expanded logit-margin future holdout freeze boundary drifted")
        if not self.q1_stress_only or self.q1_used_for_fit or self.q1_used_for_model_selection_gate:
            raise ValueError("Expanded logit-margin Q1 contamination boundary drifted")
        if not self.q2_not_claimed_untouched or not self.q3_reserved_future_holdout:
            raise ValueError("Expanded logit-margin temporal boundary drifted")
        if any(
            (
                self.numeric_forward_forecast_enabled,
                self.fair_value_estimate_enabled,
                self.target_price_enabled,
                self.decision_score_enabled,
            )
        ):
            raise ValueError("Expanded logit-margin method opened downstream outputs")
        if len(self.evidence_id) != 64:
            raise ValueError("Expanded logit-margin method evidence id must be SHA-256")

    @property
    def parameter_count(self) -> int:
        return len(self.parameters)


def load_frozen_expanded_logit_margin_method(
    path: str | Path = DEFAULT_EXPANDED_LOGIT_MARGIN_METHOD,
) -> FrozenExpandedLogitMarginMethod:
    with Path(path).open(encoding="utf-8") as handle:
        raw: object = yaml.safe_load(handle)
    root = _mapping(raw, "manifest")
    if root.get("schema_version") != 1:
        raise ValueError("Expanded logit-margin manifest schema is invalid")
    method = _mapping(root.get("method"), "method")
    structural = _mapping(method.get("structural_parameterization"), "structural_parameterization")
    driver = _mapping(method.get("driver_encoding"), "driver_encoding")
    solver = _mapping(method.get("solver"), "solver")
    prefit = _mapping(method.get("prefit_identification_gate"), "prefit_identification_gate")
    gate = _mapping(method.get("validation_gate"), "validation_gate")
    freeze = _mapping(method.get("freeze_provenance"), "freeze_provenance")
    trust = _mapping(method.get("trust_boundary"), "trust_boundary")
    if str(structural.get("link", "")) != "logistic_sigmoid":
        raise ValueError("Expanded logit-margin link drifted")
    if structural.get("bounds_are_structural_by_link_function") is not True:
        raise ValueError("Expanded logit-margin structural bounds are not enabled")
    if float(str(structural.get("product_margin_lower_bound", -1))) != 0.0:
        raise ValueError("Expanded logit-margin lower bound drifted")
    if float(str(structural.get("product_margin_upper_bound", -1))) != 1.0:
        raise ValueError("Expanded logit-margin upper bound drifted")
    if structural.get("product_profitability_is_direct_source_fact") is True:
        raise ValueError("Expanded logit-margin outputs cannot become source facts")
    if str(driver.get("semantics", "")) != "categorical_direction_regime":
        raise ValueError("Expanded logit-margin driver semantics drifted")
    if driver.get("exact_numeric_magnitude_used_for_fit") is True:
        raise ValueError("Expanded logit-margin cannot silently use driver magnitude")
    return FrozenExpandedLogitMarginMethod(
        evidence_id=_sha(root),
        method_id=str(method.get("method_id", "")),
        method_version=str(method.get("method_version", "")),
        status=str(method.get("status", "")),
        ticker=str(method.get("ticker", "")).zfill(6),
        target_metric=str(method.get("target_metric", "")),
        training_periods=_strings(method.get("training_periods"), "training_periods"),
        contaminated_stress_periods=_strings(
            method.get("contaminated_stress_periods"), "contaminated_stress_periods"
        ),
        untouched_holdout_period=str(method.get("untouched_holdout_period", "")),
        parameters=_strings(structural.get("parameters"), "parameters"),
        solver=ExpandedLogitMarginSolverContract(
            solver_id=str(solver.get("solver_id", "")),
            optimization_scale=str(solver.get("optimization_scale", "")),
            metrics_reported_in_original_krw_million=(
                solver.get("metrics_reported_in_original_krw_million") is True
            ),
            damping_matrix=str(solver.get("damping_matrix", "")),
            initial_damping=float(str(solver.get("initial_damping", "nan"))),
            damping_increase_factor=float(str(solver.get("damping_increase_factor", "nan"))),
            damping_decrease_factor=float(str(solver.get("damping_decrease_factor", "nan"))),
            maximum_iterations=int(str(solver.get("maximum_iterations", 0))),
            maximum_rejected_steps_per_iteration=int(
                str(solver.get("maximum_rejected_steps_per_iteration", 0))
            ),
            parameter_step_tolerance=float(str(solver.get("parameter_step_tolerance", "nan"))),
            relative_sse_tolerance=float(str(solver.get("relative_sse_tolerance", "nan"))),
            minimum_initialization_probability=float(
                str(solver.get("minimum_sigmoid_probability_for_logit_initialization", "nan"))
            ),
            maximum_initialization_probability=float(
                str(solver.get("maximum_sigmoid_probability_for_logit_initialization", "nan"))
            ),
        ),
        prefit_identification_gate=ExpandedPrefitIdentificationGate(
            required_row_count=int(str(prefit.get("required_row_count", 0))),
            required_parameter_count=int(str(prefit.get("required_parameter_count", 0))),
            required_residual_degrees_of_freedom=int(
                str(prefit.get("required_residual_degrees_of_freedom", 0))
            ),
            require_full_direction_design_rank=(
                prefit.get("require_full_direction_design_rank") is True
            ),
            require_all_leave_one_out_direction_designs_full_rank=(
                prefit.get("require_all_leave_one_out_direction_designs_full_rank") is True
            ),
            normalized_direction_design_condition_number_report_only=(
                prefit.get("normalized_direction_design_condition_number_report_only") is True
            ),
            leave_one_out_condition_numbers_report_only=(
                prefit.get("leave_one_out_condition_numbers_report_only") is True
            ),
        ),
        validation_gate=ExpandedLogitMarginValidationGate(
            required_row_count=int(str(gate.get("required_row_count", 0))),
            required_parameter_count=int(str(gate.get("required_parameter_count", 0))),
            required_residual_degrees_of_freedom=int(
                str(gate.get("required_residual_degrees_of_freedom", 0))
            ),
            require_full_jacobian_column_rank=(
                gate.get("require_full_jacobian_column_rank") is True
            ),
            require_optimizer_convergence=gate.get("require_optimizer_convergence") is True,
            require_all_leave_one_out_folds_converged=(
                gate.get("require_all_leave_one_out_folds_converged") is True
            ),
            require_all_leave_one_out_jacobians_full_rank=(
                gate.get("require_all_leave_one_out_jacobians_full_rank") is True
            ),
            benchmark_id=str(gate.get("benchmark_id", "")),
            require_loocv_mae_better_than_benchmark=(
                gate.get("require_loocv_mae_better_than_benchmark") is True
            ),
            require_all_component_margins_inside_unit_interval=(
                gate.get("require_all_component_margins_inside_unit_interval") is True
            ),
            normalized_jacobian_condition_number_report_only=(
                gate.get("normalized_jacobian_condition_number_report_only") is True
            ),
            parameter_jackknife_report_only=gate.get("parameter_jackknife_report_only") is True,
            contaminated_2026q1_stress_report_only=(
                gate.get("contaminated_2026q1_stress_report_only") is True
            ),
        ),
        v1_training_seen=freeze.get("v1_training_results_seen_before_v3_freeze") is True,
        v1_q1_holdout_seen=freeze.get("v1_2026q1_holdout_seen_before_v3_freeze") is True,
        v2_coefficients_seen=freeze.get("v2_coefficients_seen_before_v3_freeze") is True,
        v2_metrics_seen=freeze.get("v2_fit_metrics_seen_before_v3_freeze") is True,
        v2_gate_failure_seen=(
            freeze.get("v2_development_gate_failure_seen_before_v3_freeze") is True
        ),
        third_wave_source_closeout_seen=(
            freeze.get("third_wave_source_closeout_seen_before_v3_freeze") is True
        ),
        third_wave_preflight_seen=(
            freeze.get("third_wave_identification_preflight_seen_before_v3_freeze") is True
        ),
        clean_21_full_rank_seen=(
            freeze.get("clean_21_direction_design_full_rank_seen_before_v3_freeze") is True
        ),
        development_22_full_rank_seen=(
            freeze.get("development_22_direction_design_full_rank_seen_before_v3_freeze") is True
        ),
        v3_coefficients_seen_before_freeze=(
            freeze.get("v3_coefficients_seen_before_freeze") is True
        ),
        v3_fit_metrics_seen_before_freeze=freeze.get("v3_fit_metrics_seen_before_freeze") is True,
        q3_outcome_seen_before_freeze=(
            freeze.get("2026q3_holdout_outcome_seen_before_freeze") is True
        ),
        method_version_frozen=freeze.get("method_version_frozen") is True,
        q1_stress_only=trust.get("2026q1_is_contaminated_stress_only") is True,
        q1_used_for_fit=trust.get("2026q1_used_for_fit") is True,
        q1_used_for_model_selection_gate=(
            trust.get("2026q1_used_for_model_selection_gate") is True
        ),
        q2_not_claimed_untouched=(
            trust.get("2026q2_is_not_claimed_as_untouched_holdout") is True
        ),
        q3_reserved_future_holdout=(
            trust.get("2026q3_reserved_as_future_untouched_holdout") is True
        ),
        numeric_forward_forecast_enabled=trust.get("numeric_forward_forecast_enabled") is True,
        fair_value_estimate_enabled=trust.get("fair_value_estimate_enabled") is True,
        target_price_enabled=trust.get("target_price_enabled") is True,
        decision_score_enabled=trust.get("decision_score_enabled") is True,
    )


__all__ = [
    "DEFAULT_EXPANDED_LOGIT_MARGIN_METHOD",
    "ExpandedLogitMarginSolverContract",
    "ExpandedLogitMarginValidationGate",
    "ExpandedPrefitIdentificationGate",
    "FrozenExpandedLogitMarginMethod",
    "load_frozen_expanded_logit_margin_method",
]
