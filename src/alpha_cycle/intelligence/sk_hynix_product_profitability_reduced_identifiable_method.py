"""Frozen SK hynix V4 reduced-identifiable bounded contribution method."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import cast

import yaml

DEFAULT_REDUCED_IDENTIFIABLE_METHOD = Path(
    "config/skhynix_product_profitability_reduced_identifiable_method.v4.yaml"
)
_EXPECTED_TRAINING_PERIODS = (
    "2017Q1", "2017Q2", "2017Q3", "2018Q1", "2018Q2", "2018Q3",
    "2019Q1", "2019Q2", "2019Q3", "2020Q1", "2020Q2", "2020Q3",
    "2023Q1", "2023Q2", "2023Q3", "2024Q1", "2024Q2", "2024Q3",
    "2025Q1", "2025Q2", "2025Q3",
)
_EXPECTED_PARAMETERS = (
    "dram_logit_intercept",
    "dram_asp_direction_effect",
    "dram_bit_volume_direction_effect",
    "nand_logit_intercept",
    "nand_asp_direction_effect",
)


def _mapping(value: object, label: str) -> dict[object, object]:
    if not isinstance(value, dict):
        raise ValueError(f"Reduced V4 {label} must be an object")
    return cast(dict[object, object], value)


def _strings(value: object, label: str) -> tuple[str, ...]:
    if not isinstance(value, list):
        raise ValueError(f"Reduced V4 {label} must be an array")
    result = tuple(str(item).strip() for item in value)
    if not result or any(not item for item in result):
        raise ValueError(f"Reduced V4 {label} cannot contain empty values")
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
class ReducedSolverContract:
    solver_id: str
    optimization_scale: str
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
            raise ValueError("Reduced V4 solver id drifted")
        if self.optimization_scale != "mean_training_company_revenue_krw_million":
            raise ValueError("Reduced V4 optimization scale drifted")
        if self.initial_damping != 0.001:
            raise ValueError("Reduced V4 initial damping drifted")
        if (self.damping_increase_factor, self.damping_decrease_factor) != (10.0, 10.0):
            raise ValueError("Reduced V4 damping factors drifted")
        if (self.maximum_iterations, self.maximum_rejected_steps_per_iteration) != (500, 12):
            raise ValueError("Reduced V4 iteration contract drifted")
        if (self.parameter_step_tolerance, self.relative_sse_tolerance) != (1e-10, 1e-12):
            raise ValueError("Reduced V4 convergence tolerances drifted")
        if (
            self.minimum_initialization_probability,
            self.maximum_initialization_probability,
        ) != (1e-6, 0.999999):
            raise ValueError("Reduced V4 initialization bounds drifted")


@dataclass(frozen=True)
class ReducedPrefitGate:
    required_row_count: int
    required_parameter_count: int
    required_residual_degrees_of_freedom: int
    require_full_reduced_direction_design_rank: bool
    require_all_leave_one_out_reduced_direction_designs_full_rank: bool
    condition_number_report_only: bool

    def __post_init__(self) -> None:
        if (self.required_row_count, self.required_parameter_count) != (21, 5):
            raise ValueError("Reduced V4 prefit row/parameter gate drifted")
        if self.required_residual_degrees_of_freedom != 16:
            raise ValueError("Reduced V4 prefit residual DOF drifted")
        if not all(
            (
                self.require_full_reduced_direction_design_rank,
                self.require_all_leave_one_out_reduced_direction_designs_full_rank,
                self.condition_number_report_only,
            )
        ):
            raise ValueError("Reduced V4 prefit gate must remain fail-closed")


@dataclass(frozen=True)
class ReducedValidationGate:
    required_row_count: int
    required_parameter_count: int
    required_residual_degrees_of_freedom: int
    require_optimizer_convergence: bool
    require_full_jacobian_column_rank: bool
    require_all_leave_one_out_folds_converged: bool
    require_all_leave_one_out_jacobians_full_rank: bool
    benchmark_id: str
    require_loocv_mae_better_than_benchmark: bool
    require_all_modeled_component_margins_inside_unit_interval: bool
    condition_number_report_only: bool
    parameter_jackknife_report_only: bool
    v3_performance_comparison_report_only: bool
    contaminated_q1_stress_report_only: bool

    def __post_init__(self) -> None:
        if (self.required_row_count, self.required_parameter_count) != (21, 5):
            raise ValueError("Reduced V4 validation row/parameter gate drifted")
        if self.required_residual_degrees_of_freedom != 16:
            raise ValueError("Reduced V4 validation residual DOF drifted")
        required = (
            self.require_optimizer_convergence,
            self.require_full_jacobian_column_rank,
            self.require_all_leave_one_out_folds_converged,
            self.require_all_leave_one_out_jacobians_full_rank,
            self.require_loocv_mae_better_than_benchmark,
            self.require_all_modeled_component_margins_inside_unit_interval,
            self.condition_number_report_only,
            self.parameter_jackknife_report_only,
            self.v3_performance_comparison_report_only,
            self.contaminated_q1_stress_report_only,
        )
        if not all(required):
            raise ValueError("Reduced V4 validation gate must remain fail-closed")
        if self.benchmark_id != "leave_one_out_mean_gross_margin_scaled_revenue":
            raise ValueError("Reduced V4 benchmark id drifted")


@dataclass(frozen=True)
class FrozenReducedIdentifiableMethod:
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
    solver: ReducedSolverContract
    prefit_gate: ReducedPrefitGate
    validation_gate: ReducedValidationGate
    v3_nullspace_seen_before_freeze: bool
    v4_coefficients_seen_before_freeze: bool
    v4_fit_metrics_seen_before_freeze: bool
    holdout_outcome_seen_before_freeze: bool
    method_version_frozen: bool
    other_margin_claimed_zero: bool
    other_contribution_role: str
    q1_is_contaminated_stress_only: bool
    q1_used_for_fit: bool
    q1_used_for_model_selection_gate: bool
    q3_reserved_future_holdout: bool
    numeric_forward_forecast_enabled: bool
    fair_value_estimate_enabled: bool
    target_price_enabled: bool
    decision_score_enabled: bool

    def __post_init__(self) -> None:
        if self.method_id != "skhynix_product_profitability_reduced_identifiable_logit_margin_nls":
            raise ValueError("Reduced V4 method id drifted")
        if self.method_version != "4.0-frozen-pre-fit" or self.status != "frozen_pre_fit":
            raise ValueError("Reduced V4 version/status drifted")
        if self.ticker != "000660" or self.target_metric != "company_gross_profit_krw_million":
            raise ValueError("Reduced V4 issuer/target drifted")
        if self.training_periods != _EXPECTED_TRAINING_PERIODS:
            raise ValueError("Reduced V4 training periods drifted")
        if self.contaminated_stress_periods != ("2026Q1",):
            raise ValueError("Reduced V4 contaminated stress binding drifted")
        if self.untouched_holdout_period != "2026Q3" or self.parameters != _EXPECTED_PARAMETERS:
            raise ValueError("Reduced V4 holdout/parameter contract drifted")
        if not self.v3_nullspace_seen_before_freeze:
            raise ValueError("Reduced V4 must disclose V3 nullspace exposure")
        if self.v4_coefficients_seen_before_freeze or self.v4_fit_metrics_seen_before_freeze:
            raise ValueError("Reduced V4 outcomes cannot predate freeze")
        if self.holdout_outcome_seen_before_freeze or not self.method_version_frozen:
            raise ValueError("Reduced V4 future holdout freeze boundary drifted")
        if self.other_margin_claimed_zero:
            raise ValueError("Reduced V4 cannot claim omitted Other margin is zero")
        if self.other_contribution_role != "unmodeled_company_gross_profit_residual":
            raise ValueError("Reduced V4 Other contribution role drifted")
        if not self.q1_is_contaminated_stress_only:
            raise ValueError("Reduced V4 Q1 contamination disclosure drifted")
        if self.q1_used_for_fit or self.q1_used_for_model_selection_gate:
            raise ValueError("Reduced V4 cannot use Q1 for fit or selection")
        if not self.q3_reserved_future_holdout:
            raise ValueError("Reduced V4 must reserve Q3")
        if any(
            (
                self.numeric_forward_forecast_enabled,
                self.fair_value_estimate_enabled,
                self.target_price_enabled,
                self.decision_score_enabled,
            )
        ):
            raise ValueError("Reduced V4 opened downstream outputs")
        if len(self.evidence_id) != 64:
            raise ValueError("Reduced V4 method evidence id must be SHA-256")

    @property
    def parameter_count(self) -> int:
        return len(self.parameters)


def load_frozen_reduced_identifiable_method(
    path: str | Path = DEFAULT_REDUCED_IDENTIFIABLE_METHOD,
) -> FrozenReducedIdentifiableMethod:
    with Path(path).open(encoding="utf-8") as handle:
        raw: object = yaml.safe_load(handle)
    root = _mapping(raw, "manifest")
    if root.get("schema_version") != 1:
        raise ValueError("Reduced V4 manifest schema is invalid")
    method = _mapping(root.get("method"), "method")
    structural = _mapping(method.get("structural_parameterization"), "structural")
    driver = _mapping(method.get("driver_encoding"), "driver")
    solver = _mapping(method.get("solver"), "solver")
    prefit = _mapping(method.get("prefit_identification_gate"), "prefit gate")
    gate = _mapping(method.get("validation_gate"), "validation gate")
    freeze = _mapping(method.get("freeze_provenance"), "freeze provenance")
    trust = _mapping(method.get("trust_boundary"), "trust boundary")
    if str(structural.get("link", "")) != "logistic_sigmoid":
        raise ValueError("Reduced V4 link drifted")
    if structural.get("nand_bit_volume_effect_removed") is not True:
        raise ValueError("Reduced V4 NAND bit removal drifted")
    if structural.get("other_independent_margin_parameter_removed") is not True:
        raise ValueError("Reduced V4 Other parameter removal drifted")
    if driver.get("exact_numeric_magnitude_used_for_fit") is True:
        raise ValueError("Reduced V4 cannot silently use numeric driver magnitude")
    return FrozenReducedIdentifiableMethod(
        evidence_id=_sha(root),
        method_id=str(method.get("method_id", "")),
        method_version=str(method.get("method_version", "")),
        status=str(method.get("status", "")),
        ticker=str(method.get("ticker", "")).zfill(6),
        target_metric=str(method.get("target_metric", "")),
        training_periods=_strings(method.get("training_periods"), "training periods"),
        contaminated_stress_periods=_strings(
            method.get("contaminated_stress_periods"), "contaminated stress periods"
        ),
        untouched_holdout_period=str(method.get("untouched_holdout_period", "")),
        parameters=_strings(structural.get("parameters"), "parameters"),
        solver=ReducedSolverContract(
            solver_id=str(solver.get("solver_id", "")),
            optimization_scale=str(solver.get("optimization_scale", "")),
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
        prefit_gate=ReducedPrefitGate(
            required_row_count=int(str(prefit.get("required_row_count", 0))),
            required_parameter_count=int(str(prefit.get("required_parameter_count", 0))),
            required_residual_degrees_of_freedom=int(
                str(prefit.get("required_residual_degrees_of_freedom", 0))
            ),
            require_full_reduced_direction_design_rank=(
                prefit.get("require_full_reduced_direction_design_rank") is True
            ),
            require_all_leave_one_out_reduced_direction_designs_full_rank=(
                prefit.get("require_all_leave_one_out_reduced_direction_designs_full_rank") is True
            ),
            condition_number_report_only=prefit.get("condition_number_report_only") is True,
        ),
        validation_gate=ReducedValidationGate(
            required_row_count=int(str(gate.get("required_row_count", 0))),
            required_parameter_count=int(str(gate.get("required_parameter_count", 0))),
            required_residual_degrees_of_freedom=int(
                str(gate.get("required_residual_degrees_of_freedom", 0))
            ),
            require_optimizer_convergence=gate.get("require_optimizer_convergence") is True,
            require_full_jacobian_column_rank=gate.get("require_full_jacobian_column_rank") is True,
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
            require_all_modeled_component_margins_inside_unit_interval=(
                gate.get("require_all_modeled_component_margins_inside_unit_interval") is True
            ),
            condition_number_report_only=gate.get("condition_number_report_only") is True,
            parameter_jackknife_report_only=gate.get("parameter_jackknife_report_only") is True,
            v3_performance_comparison_report_only=(
                gate.get("v3_performance_comparison_report_only") is True
            ),
            contaminated_q1_stress_report_only=(
                gate.get("contaminated_2026q1_stress_report_only") is True
            ),
        ),
        v3_nullspace_seen_before_freeze=(
            freeze.get("v3_nullspace_diagnostic_seen_before_v4_freeze") is True
        ),
        v4_coefficients_seen_before_freeze=freeze.get("v4_coefficients_seen_before_freeze") is True,
        v4_fit_metrics_seen_before_freeze=freeze.get("v4_fit_metrics_seen_before_freeze") is True,
        holdout_outcome_seen_before_freeze=(
            freeze.get("2026q3_holdout_outcome_seen_before_freeze") is True
        ),
        method_version_frozen=freeze.get("method_version_frozen") is True,
        other_margin_claimed_zero=structural.get("other_margin_claimed_zero") is True,
        other_contribution_role=str(structural.get("other_revenue_contribution_role", "")),
        q1_is_contaminated_stress_only=trust.get("2026q1_is_contaminated_stress_only") is True,
        q1_used_for_fit=trust.get("2026q1_used_for_fit") is True,
        q1_used_for_model_selection_gate=(
            trust.get("2026q1_used_for_model_selection_gate") is True
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
    "DEFAULT_REDUCED_IDENTIFIABLE_METHOD",
    "FrozenReducedIdentifiableMethod",
    "ReducedPrefitGate",
    "ReducedSolverContract",
    "ReducedValidationGate",
    "load_frozen_reduced_identifiable_method",
]
