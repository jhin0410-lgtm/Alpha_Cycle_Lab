"""Frozen v2 bounded product-margin method for SK hynix.

This method is registered after v1's predictive holdout passed but before any v2 coefficient
or fit metric is inspected. The 2026Q1 outcome is explicitly contaminated development data;
2026Q3 is reserved as the future untouched holdout.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import cast

import yaml

DEFAULT_LOGIT_MARGIN_METHOD = Path(
    "config/skhynix_product_profitability_logit_margin_method.v2.yaml"
)
_EXPECTED_TRAINING_PERIODS = (
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
    "2026Q1",
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
        raise ValueError(f"Logit-margin {label} must be an object")
    return cast(dict[object, object], value)


def _strings(value: object, label: str) -> tuple[str, ...]:
    if not isinstance(value, list):
        raise ValueError(f"Logit-margin {label} must be an array")
    result = tuple(str(item).strip() for item in value)
    if not result or any(not item for item in result):
        raise ValueError(f"Logit-margin {label} cannot contain empty values")
    return result


def _sha(payload: object) -> str:
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


@dataclass(frozen=True)
class LogitMarginSolverContract:
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
            raise ValueError("Logit-margin solver id drifted")
        if self.optimization_scale != "mean_training_company_revenue_krw_million":
            raise ValueError("Logit-margin optimization scale drifted")
        if not self.metrics_reported_in_original_krw_million:
            raise ValueError("Logit-margin metrics unit contract drifted")
        if self.damping_matrix != "diagonal_jtj_with_floor_1e-12":
            raise ValueError("Logit-margin damping matrix drifted")
        if self.initial_damping != 0.001:
            raise ValueError("Logit-margin initial damping drifted")
        if (self.damping_increase_factor, self.damping_decrease_factor) != (10.0, 10.0):
            raise ValueError("Logit-margin damping factors drifted")
        if (self.maximum_iterations, self.maximum_rejected_steps_per_iteration) != (500, 12):
            raise ValueError("Logit-margin iteration contract drifted")
        if (self.parameter_step_tolerance, self.relative_sse_tolerance) != (1e-10, 1e-12):
            raise ValueError("Logit-margin convergence tolerances drifted")
        probability_bounds = (
            self.minimum_initialization_probability,
            self.maximum_initialization_probability,
        )
        if probability_bounds != (1e-6, 0.999999):
            raise ValueError("Logit-margin initialization probability bounds drifted")


@dataclass(frozen=True)
class LogitMarginValidationGate:
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
    leverage_report_only: bool
    parameter_jackknife_report_only: bool

    def __post_init__(self) -> None:
        if (self.required_row_count, self.required_parameter_count) != (16, 7):
            raise ValueError("Logit-margin row/parameter gate drifted")
        if self.required_residual_degrees_of_freedom != 9:
            raise ValueError("Logit-margin residual DOF gate drifted")
        required = (
            self.require_full_jacobian_column_rank,
            self.require_optimizer_convergence,
            self.require_all_leave_one_out_folds_converged,
            self.require_all_leave_one_out_jacobians_full_rank,
            self.require_loocv_mae_better_than_benchmark,
            self.require_all_component_margins_inside_unit_interval,
            self.leverage_report_only,
            self.parameter_jackknife_report_only,
        )
        if not all(required):
            raise ValueError("Logit-margin validation gate must remain fail-closed")
        if self.benchmark_id != "leave_one_out_mean_gross_margin_scaled_revenue":
            raise ValueError("Logit-margin benchmark id drifted")


@dataclass(frozen=True)
class FrozenLogitMarginMethod:
    evidence_id: str
    method_id: str
    method_version: str
    status: str
    ticker: str
    target_metric: str
    training_periods: tuple[str, ...]
    contaminated_development_periods: tuple[str, ...]
    untouched_holdout_period: str
    parameters: tuple[str, ...]
    solver: LogitMarginSolverContract
    validation_gate: LogitMarginValidationGate
    v1_training_results_seen_before_v2_freeze: bool
    v1_2026q1_holdout_seen_before_v2_freeze: bool
    v2_coefficients_seen_before_freeze: bool
    v2_fit_metrics_seen_before_freeze: bool
    holdout_outcome_seen_before_freeze: bool
    method_version_frozen: bool
    q1_is_development_not_holdout: bool
    q2_not_claimed_untouched: bool
    q3_reserved_future_holdout: bool
    numeric_forward_forecast_enabled: bool
    fair_value_estimate_enabled: bool
    target_price_enabled: bool
    decision_score_enabled: bool

    def __post_init__(self) -> None:
        if self.method_id != "skhynix_product_profitability_logit_margin_nls":
            raise ValueError("Logit-margin method id drifted")
        if self.method_version != "2.0-frozen-pre-fit" or self.status != "frozen_pre_fit":
            raise ValueError("Logit-margin method version/status drifted")
        if self.ticker != "000660" or self.target_metric != "company_gross_profit_krw_million":
            raise ValueError("Logit-margin issuer/target drifted")
        if self.training_periods != _EXPECTED_TRAINING_PERIODS:
            raise ValueError("Logit-margin training periods drifted")
        if self.contaminated_development_periods != ("2026Q1",):
            raise ValueError("Logit-margin contaminated development binding drifted")
        if self.untouched_holdout_period != "2026Q3" or self.parameters != _EXPECTED_PARAMETERS:
            raise ValueError("Logit-margin holdout/parameter contract drifted")
        if not self.v1_training_results_seen_before_v2_freeze:
            raise ValueError("Logit-margin freeze provenance must disclose v1 training exposure")
        if not self.v1_2026q1_holdout_seen_before_v2_freeze:
            raise ValueError("Logit-margin freeze provenance must disclose Q1 holdout exposure")
        if self.v2_coefficients_seen_before_freeze or self.v2_fit_metrics_seen_before_freeze:
            raise ValueError("Logit-margin v2 outcomes were seen before freeze")
        if self.holdout_outcome_seen_before_freeze or not self.method_version_frozen:
            raise ValueError("Logit-margin future holdout freeze boundary drifted")
        temporal_boundary = (
            self.q1_is_development_not_holdout
            and self.q2_not_claimed_untouched
            and self.q3_reserved_future_holdout
        )
        if not temporal_boundary:
            raise ValueError("Logit-margin temporal trust boundary drifted")
        downstream_open = any(
            (
                self.numeric_forward_forecast_enabled,
                self.fair_value_estimate_enabled,
                self.target_price_enabled,
                self.decision_score_enabled,
            )
        )
        if downstream_open:
            raise ValueError("Logit-margin method opened downstream outputs")
        if len(self.evidence_id) != 64:
            raise ValueError("Logit-margin method evidence id must be SHA-256")

    @property
    def parameter_count(self) -> int:
        return len(self.parameters)


def load_frozen_logit_margin_method(
    path: str | Path = DEFAULT_LOGIT_MARGIN_METHOD,
) -> FrozenLogitMarginMethod:
    with Path(path).open(encoding="utf-8") as handle:
        raw: object = yaml.safe_load(handle)
    root = _mapping(raw, "manifest")
    if root.get("schema_version") != 1:
        raise ValueError("Logit-margin manifest schema is invalid")
    method = _mapping(root.get("method"), "method")
    structural = _mapping(
        method.get("structural_parameterization"),
        "structural_parameterization",
    )
    driver = _mapping(method.get("driver_encoding"), "driver_encoding")
    solver = _mapping(method.get("solver"), "solver")
    gate = _mapping(method.get("validation_gate"), "validation_gate")
    freeze = _mapping(method.get("freeze_provenance"), "freeze_provenance")
    trust = _mapping(method.get("trust_boundary"), "trust_boundary")
    if str(structural.get("link", "")) != "logistic_sigmoid":
        raise ValueError("Logit-margin link drifted")
    if structural.get("bounds_are_structural_by_link_function") is not True:
        raise ValueError("Logit-margin structural bounds are not enabled")
    if float(str(structural.get("product_margin_lower_bound", -1))) != 0.0:
        raise ValueError("Logit-margin lower hard bound drifted")
    if float(str(structural.get("product_margin_upper_bound", -1))) != 1.0:
        raise ValueError("Logit-margin upper hard bound drifted")
    if structural.get("product_profitability_is_direct_source_fact") is True:
        raise ValueError("Logit-margin outputs cannot become source facts")
    if str(driver.get("semantics", "")) != "categorical_direction_regime":
        raise ValueError("Logit-margin driver semantics drifted")
    if driver.get("exact_numeric_magnitude_used_for_fit") is True:
        raise ValueError("Logit-margin v2 cannot silently use numeric driver magnitude")
    return FrozenLogitMarginMethod(
        evidence_id=_sha(root),
        method_id=str(method.get("method_id", "")),
        method_version=str(method.get("method_version", "")),
        status=str(method.get("status", "")),
        ticker=str(method.get("ticker", "")).zfill(6),
        target_metric=str(method.get("target_metric", "")),
        training_periods=_strings(method.get("training_periods"), "training_periods"),
        contaminated_development_periods=_strings(
            method.get("contaminated_development_periods"),
            "contaminated_development_periods",
        ),
        untouched_holdout_period=str(method.get("untouched_holdout_period", "")),
        parameters=_strings(structural.get("parameters"), "parameters"),
        solver=LogitMarginSolverContract(
            solver_id=str(solver.get("solver_id", "")),
            optimization_scale=str(solver.get("optimization_scale", "")),
            metrics_reported_in_original_krw_million=(
                solver.get("metrics_reported_in_original_krw_million") is True
            ),
            damping_matrix=str(solver.get("damping_matrix", "")),
            initial_damping=float(str(solver.get("initial_damping", "nan"))),
            damping_increase_factor=float(
                str(solver.get("damping_increase_factor", "nan"))
            ),
            damping_decrease_factor=float(
                str(solver.get("damping_decrease_factor", "nan"))
            ),
            maximum_iterations=int(str(solver.get("maximum_iterations", 0))),
            maximum_rejected_steps_per_iteration=int(
                str(solver.get("maximum_rejected_steps_per_iteration", 0))
            ),
            parameter_step_tolerance=float(
                str(solver.get("parameter_step_tolerance", "nan"))
            ),
            relative_sse_tolerance=float(
                str(solver.get("relative_sse_tolerance", "nan"))
            ),
            minimum_initialization_probability=float(
                str(solver.get("minimum_sigmoid_probability_for_logit_initialization", "nan"))
            ),
            maximum_initialization_probability=float(
                str(solver.get("maximum_sigmoid_probability_for_logit_initialization", "nan"))
            ),
        ),
        validation_gate=LogitMarginValidationGate(
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
            leverage_report_only=gate.get("leverage_report_only") is True,
            parameter_jackknife_report_only=gate.get("parameter_jackknife_report_only") is True,
        ),
        v1_training_results_seen_before_v2_freeze=(
            freeze.get("v1_training_results_seen_before_v2_freeze") is True
        ),
        v1_2026q1_holdout_seen_before_v2_freeze=(
            freeze.get("v1_2026q1_holdout_seen_before_v2_freeze") is True
        ),
        v2_coefficients_seen_before_freeze=(
            freeze.get("v2_coefficients_seen_before_freeze") is True
        ),
        v2_fit_metrics_seen_before_freeze=(
            freeze.get("v2_fit_metrics_seen_before_freeze") is True
        ),
        holdout_outcome_seen_before_freeze=(
            freeze.get("2026q3_holdout_outcome_seen_before_freeze") is True
        ),
        method_version_frozen=freeze.get("method_version_frozen") is True,
        q1_is_development_not_holdout=(
            trust.get("2026q1_is_development_data_not_holdout") is True
        ),
        q2_not_claimed_untouched=(
            trust.get("2026q2_is_not_claimed_as_untouched_holdout") is True
        ),
        q3_reserved_future_holdout=(
            trust.get("2026q3_reserved_as_future_untouched_holdout") is True
        ),
        numeric_forward_forecast_enabled=(
            trust.get("numeric_forward_forecast_enabled") is True
        ),
        fair_value_estimate_enabled=trust.get("fair_value_estimate_enabled") is True,
        target_price_enabled=trust.get("target_price_enabled") is True,
        decision_score_enabled=trust.get("decision_score_enabled") is True,
    )


__all__ = [
    "DEFAULT_LOGIT_MARGIN_METHOD",
    "FrozenLogitMarginMethod",
    "LogitMarginSolverContract",
    "LogitMarginValidationGate",
    "load_frozen_logit_margin_method",
]
