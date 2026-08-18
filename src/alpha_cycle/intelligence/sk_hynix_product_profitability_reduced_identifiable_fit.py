"""Fit the frozen SK hynix V4 five-parameter reduced-identifiable model."""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import asdict, dataclass
from datetime import date
from pathlib import Path

import numpy as np

from alpha_cycle.intelligence.sec_product_cycle_driver_support import (
    DEFAULT_SEC_PRODUCT_CYCLE_DRIVER_POINTER,
)
from alpha_cycle.intelligence.sk_hynix_opendart_historical_product_revenue_panel import (
    DEFAULT_HISTORICAL_PRODUCT_REVENUE_POINTER,
)
from alpha_cycle.intelligence.sk_hynix_opendart_quarterly_company_profitability import (
    DEFAULT_QUARTERLY_COMPANY_PROFITABILITY_POINTER,
)
from alpha_cycle.intelligence.sk_hynix_product_profitability_expanded_logit_margin_fit import (
    ExpandedLogitMarginRow,
    load_expanded_logit_margin_rows,
)
from alpha_cycle.intelligence.sk_hynix_product_profitability_expanded_logit_margin_method import (
    DEFAULT_EXPANDED_LOGIT_MARGIN_METHOD,
    load_frozen_expanded_logit_margin_method,
)
from alpha_cycle.intelligence.sk_hynix_product_profitability_logit_margin_method import (
    DEFAULT_LOGIT_MARGIN_METHOD,
)
from alpha_cycle.intelligence.sk_hynix_product_profitability_reduced_identifiable_method import (
    FrozenReducedIdentifiableMethod,
)
from alpha_cycle.intelligence.sk_hynix_product_profitability_regime_economic_audit import (
    DEFAULT_REGIME_TRAINING_FIT_POINTER,
)
from alpha_cycle.intelligence.sk_hynix_product_profitability_regime_holdout import (
    DEFAULT_REGIME_HOLDOUT_POINTER,
)
from alpha_cycle.intelligence.sk_hynix_product_profitability_third_wave_closeout import (
    ThirdWaveCloseout,
)
from alpha_cycle.intelligence.sk_hynix_product_profitability_third_wave_frontier import (
    ThirdWaveFrontier,
)


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


def _sigmoid(value: np.ndarray | float) -> np.ndarray | float:
    clipped = np.clip(value, -60.0, 60.0)
    result = 1.0 / (1.0 + np.exp(-clipped))
    if isinstance(value, np.ndarray):
        return result
    return float(result)


def _condition(matrix: np.ndarray) -> float | None:
    norms = np.linalg.norm(matrix, axis=0)
    if np.any(norms == 0.0):
        return None
    value = float(np.linalg.cond(matrix / norms))
    return value if math.isfinite(value) else None


@dataclass(frozen=True)
class ReducedPrefitIdentification:
    row_count: int
    parameter_count: int
    residual_degrees_of_freedom: int
    design_rank: int
    full_reduced_direction_design_rank: bool
    normalized_condition_number_report_only: float | None
    leave_one_out_design_ranks: tuple[int, ...]
    all_leave_one_out_reduced_direction_designs_full_rank: bool
    leave_one_out_condition_numbers_report_only: tuple[float | None, ...]
    prefit_gate_passed: bool


@dataclass(frozen=True)
class ReducedSolverResult:
    parameters: tuple[float, ...]
    converged: bool
    iterations: int
    rejected_steps: int
    final_sse_scaled: float
    jacobian_rank: int
    normalized_jacobian_condition_number_report_only: float | None


@dataclass(frozen=True)
class ReducedLeaveOneOut:
    held_out_period: str
    converged: bool
    jacobian_rank: int
    model_prediction_krw_million: float
    actual_krw_million: float
    model_absolute_error_krw_million: float
    benchmark_prediction_krw_million: float
    benchmark_absolute_error_krw_million: float
    parameters_report_only: tuple[float, ...]


@dataclass(frozen=True)
class ReducedMarginEnvelope:
    product: str
    minimum_margin: float
    maximum_margin: float
    all_regimes_inside_unit_interval: bool


@dataclass(frozen=True)
class ReducedParameterJackknife:
    parameter_name: str
    full_fit_value: float
    leave_one_out_minimum: float
    leave_one_out_maximum: float
    sign_stability_ratio_report_only: float


@dataclass(frozen=True)
class ReducedQ1StressDiagnostic:
    period_id: str
    model_prediction_krw_million: float
    actual_krw_million: float
    model_absolute_error_krw_million: float
    benchmark_prediction_krw_million: float
    benchmark_absolute_error_krw_million: float
    model_beats_benchmark_report_only: bool
    used_for_fit: bool = False
    used_for_model_selection_gate: bool = False
    claimed_as_independent_holdout: bool = False

    def __post_init__(self) -> None:
        if self.period_id != "2026Q1":
            raise ValueError("Reduced V4 contaminated stress period drifted")
        if (
            self.used_for_fit
            or self.used_for_model_selection_gate
            or self.claimed_as_independent_holdout
        ):
            raise ValueError("Reduced V4 Q1 stress exceeded contamination boundary")


@dataclass(frozen=True)
class ReducedIdentifiableFitResult:
    evidence_id: str
    evaluation_date: date
    method_evidence_id: str
    training_periods: tuple[str, ...]
    prefit_identification: ReducedPrefitIdentification
    row_count: int
    parameter_count: int
    residual_degrees_of_freedom: int
    parameters: tuple[float, ...]
    optimizer_converged: bool
    optimizer_iterations: int
    jacobian_rank: int
    full_jacobian_column_rank: bool
    normalized_jacobian_condition_number_report_only: float | None
    in_sample_mae_krw_million: float
    in_sample_rmse_krw_million: float
    loocv: tuple[ReducedLeaveOneOut, ...]
    all_loocv_folds_converged: bool
    all_loocv_jacobians_full_rank: bool
    loocv_mae_krw_million: float
    benchmark_loocv_mae_krw_million: float
    loocv_beats_benchmark: bool
    dram_margin_envelope: ReducedMarginEnvelope
    nand_margin_envelope: ReducedMarginEnvelope
    all_modeled_component_margins_inside_unit_interval: bool
    parameter_jackknife_report_only: tuple[ReducedParameterJackknife, ...]
    contaminated_q1_stress_report_only: ReducedQ1StressDiagnostic
    development_gate_passed: bool
    other_margin_claimed_zero: bool = False
    other_contribution_role: str = "unmodeled_company_gross_profit_residual"
    future_holdout_period: str = "2026Q3"
    future_holdout_evaluation_allowed: bool = False
    future_holdout_loaded: bool = False
    future_holdout_evaluated: bool = False
    numeric_forward_forecast_enabled: bool = False
    target_price_enabled: bool = False
    decision_score_enabled: bool = False

    def __post_init__(self) -> None:
        if len(self.evidence_id) != 64 or len(self.method_evidence_id) != 64:
            raise ValueError("Reduced V4 fit evidence ids must be SHA-256")
        if self.row_count != len(self.training_periods):
            raise ValueError("Reduced V4 row count is inconsistent")
        if self.parameter_count != len(self.parameters):
            raise ValueError("Reduced V4 parameter count is inconsistent")
        if self.residual_degrees_of_freedom != self.row_count - self.parameter_count:
            raise ValueError("Reduced V4 residual DOF is inconsistent")
        if self.full_jacobian_column_rank != (self.jacobian_rank == self.parameter_count):
            raise ValueError("Reduced V4 rank flag is inconsistent")
        if self.loocv_beats_benchmark != (
            self.loocv_mae_krw_million < self.benchmark_loocv_mae_krw_million
        ):
            raise ValueError("Reduced V4 benchmark flag is inconsistent")
        if self.other_margin_claimed_zero:
            raise ValueError("Reduced V4 cannot claim omitted Other margin is zero")
        if self.other_contribution_role != "unmodeled_company_gross_profit_residual":
            raise ValueError("Reduced V4 Other contribution role drifted")
        if self.future_holdout_period != "2026Q3":
            raise ValueError("Reduced V4 future holdout drifted")
        if any(
            (
                self.future_holdout_evaluation_allowed,
                self.future_holdout_loaded,
                self.future_holdout_evaluated,
                self.numeric_forward_forecast_enabled,
                self.target_price_enabled,
                self.decision_score_enabled,
            )
        ):
            raise ValueError("Reduced V4 fit exceeded development trust boundary")


def load_reduced_identifiable_rows(
    method: FrozenReducedIdentifiableMethod,
    closeout: ThirdWaveCloseout,
    frontier: ThirdWaveFrontier,
    *,
    v3_method_path: str | Path = DEFAULT_EXPANDED_LOGIT_MARGIN_METHOD,
    v2_method_path: str | Path = DEFAULT_LOGIT_MARGIN_METHOD,
    v1_training_pointer: str | Path = DEFAULT_REGIME_TRAINING_FIT_POINTER,
    v1_holdout_pointer: str | Path = DEFAULT_REGIME_HOLDOUT_POINTER,
    historical_product_revenue_pointer: str | Path = DEFAULT_HISTORICAL_PRODUCT_REVENUE_POINTER,
    company_profitability_pointer: str | Path = DEFAULT_QUARTERLY_COMPANY_PROFITABILITY_POINTER,
    cycle_driver_pointer: str | Path = DEFAULT_SEC_PRODUCT_CYCLE_DRIVER_POINTER,
) -> tuple[tuple[ExpandedLogitMarginRow, ...], ExpandedLogitMarginRow]:
    v3_method = load_frozen_expanded_logit_margin_method(v3_method_path)
    rows, stress = load_expanded_logit_margin_rows(
        v3_method,
        closeout,
        frontier,
        v2_method_path=v2_method_path,
        v1_training_pointer=v1_training_pointer,
        v1_holdout_pointer=v1_holdout_pointer,
        historical_product_revenue_pointer=historical_product_revenue_pointer,
        company_profitability_pointer=company_profitability_pointer,
        cycle_driver_pointer=cycle_driver_pointer,
    )
    if tuple(row.period_id for row in rows) != method.training_periods:
        raise ValueError("Reduced V4 clean periods diverged from frozen method")
    if stress.period_id not in method.contaminated_stress_periods:
        raise ValueError("Reduced V4 contaminated stress period drifted")
    return rows, stress


def _arrays(rows: tuple[ExpandedLogitMarginRow, ...]) -> tuple[np.ndarray, ...]:
    return (
        np.asarray([r.company_revenue_krw_million for r in rows], dtype=float),
        np.asarray([r.company_gross_profit_krw_million for r in rows], dtype=float),
        np.asarray([r.dram_revenue_krw_million for r in rows], dtype=float),
        np.asarray([r.nand_revenue_krw_million for r in rows], dtype=float),
        np.asarray([r.dram_asp_direction_code for r in rows], dtype=float),
        np.asarray([r.dram_bit_volume_direction_code for r in rows], dtype=float),
        np.asarray([r.nand_asp_direction_code for r in rows], dtype=float),
    )


def _design(rows: tuple[ExpandedLogitMarginRow, ...]) -> np.ndarray:
    return np.asarray(
        [
            (
                row.dram_revenue_krw_million,
                row.dram_revenue_krw_million * row.dram_asp_direction_code,
                row.dram_revenue_krw_million * row.dram_bit_volume_direction_code,
                row.nand_revenue_krw_million,
                row.nand_revenue_krw_million * row.nand_asp_direction_code,
            )
            for row in rows
        ],
        dtype=float,
    )


def build_reduced_prefit_identification(
    method: FrozenReducedIdentifiableMethod,
    rows: tuple[ExpandedLogitMarginRow, ...],
) -> ReducedPrefitIdentification:
    if tuple(row.period_id for row in rows) != method.training_periods:
        raise ValueError("Reduced V4 prefit rows diverged from frozen periods")
    matrix = _design(rows)
    p = method.parameter_count
    rank = int(np.linalg.matrix_rank(matrix))
    loo_ranks: list[int] = []
    loo_conditions: list[float | None] = []
    for index in range(len(rows)):
        fold = np.delete(matrix, index, axis=0)
        loo_ranks.append(int(np.linalg.matrix_rank(fold)))
        loo_conditions.append(_condition(fold))
    gate = method.prefit_gate
    n = len(rows)
    dof = n - p
    all_loo_rank = all(value == p for value in loo_ranks)
    passed = all(
        (
            n == gate.required_row_count,
            p == gate.required_parameter_count,
            dof >= gate.required_residual_degrees_of_freedom,
            rank == p if gate.require_full_reduced_direction_design_rank else True,
            all_loo_rank
            if gate.require_all_leave_one_out_reduced_direction_designs_full_rank
            else True,
        )
    )
    return ReducedPrefitIdentification(
        row_count=n,
        parameter_count=p,
        residual_degrees_of_freedom=dof,
        design_rank=rank,
        full_reduced_direction_design_rank=rank == p,
        normalized_condition_number_report_only=_condition(matrix),
        leave_one_out_design_ranks=tuple(loo_ranks),
        all_leave_one_out_reduced_direction_designs_full_rank=all_loo_rank,
        leave_one_out_condition_numbers_report_only=tuple(loo_conditions),
        prefit_gate_passed=passed,
    )


def _predict_jacobian(
    theta: np.ndarray,
    rows: tuple[ExpandedLogitMarginRow, ...],
    scale: float,
) -> tuple[np.ndarray, np.ndarray]:
    _revenue, _target, dram, nand, da, db, na = _arrays(rows)
    dram_scaled = dram / scale
    nand_scaled = nand / scale
    md = np.asarray(_sigmoid(theta[0] + theta[1] * da + theta[2] * db), dtype=float)
    mn = np.asarray(_sigmoid(theta[3] + theta[4] * na), dtype=float)
    prediction = dram_scaled * md + nand_scaled * mn
    dd = dram_scaled * md * (1.0 - md)
    dn = nand_scaled * mn * (1.0 - mn)
    jacobian = np.column_stack((dd, dd * da, dd * db, dn, dn * na))
    return prediction, jacobian


def _initial_theta(
    rows: tuple[ExpandedLogitMarginRow, ...],
    method: FrozenReducedIdentifiableMethod,
) -> np.ndarray:
    revenue, target, *_rest = _arrays(rows)
    probability = float(np.mean(target / revenue))
    probability = min(
        method.solver.maximum_initialization_probability,
        max(method.solver.minimum_initialization_probability, probability),
    )
    logit = math.log(probability / (1.0 - probability))
    return np.asarray([logit, 0.0, 0.0, logit, 0.0], dtype=float)


def _solve(
    rows: tuple[ExpandedLogitMarginRow, ...],
    method: FrozenReducedIdentifiableMethod,
) -> ReducedSolverResult:
    revenue, target, *_rest = _arrays(rows)
    scale = float(np.mean(revenue))
    if not math.isfinite(scale) or scale <= 0.0:
        raise ValueError("Reduced V4 optimization scale is invalid")
    y = target / scale
    theta = _initial_theta(rows, method)
    damping = method.solver.initial_damping
    rejected = 0
    converged = False
    iterations = 0
    for iteration in range(1, method.solver.maximum_iterations + 1):
        prediction, jacobian = _predict_jacobian(theta, rows, scale)
        residual = prediction - y
        sse = float(np.dot(residual, residual))
        normal = jacobian.T @ jacobian
        gradient = jacobian.T @ residual
        accepted = False
        for _attempt in range(method.solver.maximum_rejected_steps_per_iteration + 1):
            diagonal = np.maximum(np.diag(normal), 1e-12)
            hessian = normal + damping * np.diag(diagonal)
            try:
                step = np.linalg.solve(hessian, -gradient)
            except np.linalg.LinAlgError:
                step = np.linalg.lstsq(hessian, -gradient, rcond=None)[0]
            candidate = theta + step
            candidate_prediction, _candidate_jac = _predict_jacobian(
                candidate,
                rows,
                scale,
            )
            candidate_residual = candidate_prediction - y
            candidate_sse = float(np.dot(candidate_residual, candidate_residual))
            if candidate_sse < sse:
                relative = (sse - candidate_sse) / max(sse, 1e-30)
                theta = candidate
                damping /= method.solver.damping_decrease_factor
                accepted = True
                iterations = iteration
                if np.linalg.norm(step) <= method.solver.parameter_step_tolerance * (
                    1.0 + np.linalg.norm(theta)
                ) or relative <= method.solver.relative_sse_tolerance:
                    converged = True
                break
            damping *= method.solver.damping_increase_factor
            rejected += 1
        if not accepted:
            iterations = iteration
            break
        if converged:
            break
    prediction, jacobian = _predict_jacobian(theta, rows, scale)
    residual = prediction - y
    return ReducedSolverResult(
        parameters=tuple(float(value) for value in theta),
        converged=converged,
        iterations=iterations,
        rejected_steps=rejected,
        final_sse_scaled=float(np.dot(residual, residual)),
        jacobian_rank=int(np.linalg.matrix_rank(jacobian)),
        normalized_jacobian_condition_number_report_only=_condition(jacobian),
    )


def _prediction_original(
    parameters: tuple[float, ...],
    rows: tuple[ExpandedLogitMarginRow, ...],
) -> np.ndarray:
    revenue, _target, *_rest = _arrays(rows)
    scale = float(np.mean(revenue))
    prediction, _jacobian = _predict_jacobian(
        np.asarray(parameters, dtype=float),
        rows,
        scale,
    )
    return prediction * scale


def _dram_envelope(theta: tuple[float, ...]) -> ReducedMarginEnvelope:
    values = tuple(
        float(_sigmoid(theta[0] + theta[1] * asp + theta[2] * bit))
        for asp in (-1.0, 0.0, 1.0)
        for bit in (-1.0, 0.0, 1.0)
    )
    return ReducedMarginEnvelope(
        product="DRAM",
        minimum_margin=min(values),
        maximum_margin=max(values),
        all_regimes_inside_unit_interval=all(0.0 < value < 1.0 for value in values),
    )


def _nand_envelope(theta: tuple[float, ...]) -> ReducedMarginEnvelope:
    values = tuple(float(_sigmoid(theta[3] + theta[4] * asp)) for asp in (-1.0, 0.0, 1.0))
    return ReducedMarginEnvelope(
        product="NAND",
        minimum_margin=min(values),
        maximum_margin=max(values),
        all_regimes_inside_unit_interval=all(0.0 < value < 1.0 for value in values),
    )


def _jackknife(
    method: FrozenReducedIdentifiableMethod,
    full_parameters: tuple[float, ...],
    fold_parameters: tuple[tuple[float, ...], ...],
) -> tuple[ReducedParameterJackknife, ...]:
    result: list[ReducedParameterJackknife] = []
    for index, name in enumerate(method.parameters):
        values = tuple(item[index] for item in fold_parameters)
        full = full_parameters[index]
        full_sign = 1 if full > 0.0 else -1 if full < 0.0 else 0
        same = sum(
            (1 if value > 0.0 else -1 if value < 0.0 else 0) == full_sign
            for value in values
        )
        result.append(
            ReducedParameterJackknife(
                parameter_name=name,
                full_fit_value=full,
                leave_one_out_minimum=min(values),
                leave_one_out_maximum=max(values),
                sign_stability_ratio_report_only=same / len(values),
            )
        )
    return tuple(result)


def build_reduced_identifiable_fit(
    method: FrozenReducedIdentifiableMethod,
    rows: tuple[ExpandedLogitMarginRow, ...],
    contaminated_q1: ExpandedLogitMarginRow,
    *,
    evaluation_date: date,
) -> ReducedIdentifiableFitResult:
    prefit = build_reduced_prefit_identification(method, rows)
    if not prefit.prefit_gate_passed:
        raise ValueError("Reduced V4 prefit identification gate failed; fit not attempted")
    if contaminated_q1.period_id != "2026Q1":
        raise ValueError("Reduced V4 requires contaminated 2026Q1 stress row")
    full = _solve(rows, method)
    prediction = _prediction_original(full.parameters, rows)
    revenue, target, *_rest = _arrays(rows)
    errors = target - prediction
    loocv: list[ReducedLeaveOneOut] = []
    fold_parameters: list[tuple[float, ...]] = []
    for index, row in enumerate(rows):
        fold_rows = tuple(item for idx, item in enumerate(rows) if idx != index)
        fold = _solve(fold_rows, method)
        fold_parameters.append(fold.parameters)
        model_prediction = float(_prediction_original(fold.parameters, (row,))[0])
        train_revenue, train_target, *_fold_rest = _arrays(fold_rows)
        benchmark_margin = float(np.mean(train_target / train_revenue))
        benchmark_prediction = benchmark_margin * row.company_revenue_krw_million
        loocv.append(
            ReducedLeaveOneOut(
                held_out_period=row.period_id,
                converged=fold.converged,
                jacobian_rank=fold.jacobian_rank,
                model_prediction_krw_million=model_prediction,
                actual_krw_million=row.company_gross_profit_krw_million,
                model_absolute_error_krw_million=abs(
                    row.company_gross_profit_krw_million - model_prediction
                ),
                benchmark_prediction_krw_million=benchmark_prediction,
                benchmark_absolute_error_krw_million=abs(
                    row.company_gross_profit_krw_million - benchmark_prediction
                ),
                parameters_report_only=fold.parameters,
            )
        )
    loocv_mae = float(np.mean([item.model_absolute_error_krw_million for item in loocv]))
    benchmark_mae = float(
        np.mean([item.benchmark_absolute_error_krw_million for item in loocv])
    )
    dram = _dram_envelope(full.parameters)
    nand = _nand_envelope(full.parameters)
    all_bounds = dram.all_regimes_inside_unit_interval and nand.all_regimes_inside_unit_interval
    gate = method.validation_gate
    n = len(rows)
    p = method.parameter_count
    dof = n - p
    all_fold_converged = all(item.converged for item in loocv)
    all_fold_rank = all(item.jacobian_rank == p for item in loocv)
    full_rank = full.jacobian_rank == p
    development_gate = all(
        (
            n == gate.required_row_count,
            p == gate.required_parameter_count,
            dof >= gate.required_residual_degrees_of_freedom,
            full.converged if gate.require_optimizer_convergence else True,
            full_rank if gate.require_full_jacobian_column_rank else True,
            all_fold_converged if gate.require_all_leave_one_out_folds_converged else True,
            all_fold_rank if gate.require_all_leave_one_out_jacobians_full_rank else True,
            loocv_mae < benchmark_mae if gate.require_loocv_mae_better_than_benchmark else True,
            all_bounds
            if gate.require_all_modeled_component_margins_inside_unit_interval
            else True,
        )
    )
    q1_prediction = float(_prediction_original(full.parameters, (contaminated_q1,))[0])
    training_margin = float(np.mean(target / revenue))
    q1_benchmark = training_margin * contaminated_q1.company_revenue_krw_million
    q1_stress = ReducedQ1StressDiagnostic(
        period_id="2026Q1",
        model_prediction_krw_million=q1_prediction,
        actual_krw_million=contaminated_q1.company_gross_profit_krw_million,
        model_absolute_error_krw_million=abs(
            contaminated_q1.company_gross_profit_krw_million - q1_prediction
        ),
        benchmark_prediction_krw_million=q1_benchmark,
        benchmark_absolute_error_krw_million=abs(
            contaminated_q1.company_gross_profit_krw_million - q1_benchmark
        ),
        model_beats_benchmark_report_only=(
            abs(contaminated_q1.company_gross_profit_krw_million - q1_prediction)
            < abs(contaminated_q1.company_gross_profit_krw_million - q1_benchmark)
        ),
    )
    stable = {
        "evaluation_date": evaluation_date.isoformat(),
        "method_evidence_id": method.evidence_id,
        "training_periods": method.training_periods,
        "parameters": full.parameters,
        "loocv": [asdict(item) for item in loocv],
        "development_gate_passed": development_gate,
    }
    return ReducedIdentifiableFitResult(
        evidence_id=_sha(stable),
        evaluation_date=evaluation_date,
        method_evidence_id=method.evidence_id,
        training_periods=method.training_periods,
        prefit_identification=prefit,
        row_count=n,
        parameter_count=p,
        residual_degrees_of_freedom=dof,
        parameters=full.parameters,
        optimizer_converged=full.converged,
        optimizer_iterations=full.iterations,
        jacobian_rank=full.jacobian_rank,
        full_jacobian_column_rank=full_rank,
        normalized_jacobian_condition_number_report_only=(
            full.normalized_jacobian_condition_number_report_only
        ),
        in_sample_mae_krw_million=float(np.mean(np.abs(errors))),
        in_sample_rmse_krw_million=float(np.sqrt(np.mean(np.square(errors)))),
        loocv=tuple(loocv),
        all_loocv_folds_converged=all_fold_converged,
        all_loocv_jacobians_full_rank=all_fold_rank,
        loocv_mae_krw_million=loocv_mae,
        benchmark_loocv_mae_krw_million=benchmark_mae,
        loocv_beats_benchmark=loocv_mae < benchmark_mae,
        dram_margin_envelope=dram,
        nand_margin_envelope=nand,
        all_modeled_component_margins_inside_unit_interval=all_bounds,
        parameter_jackknife_report_only=_jackknife(
            method,
            full.parameters,
            tuple(fold_parameters),
        ),
        contaminated_q1_stress_report_only=q1_stress,
        development_gate_passed=development_gate,
    )


__all__ = [
    "ReducedIdentifiableFitResult",
    "ReducedLeaveOneOut",
    "ReducedMarginEnvelope",
    "ReducedParameterJackknife",
    "ReducedPrefitIdentification",
    "ReducedQ1StressDiagnostic",
    "ReducedSolverResult",
    "build_reduced_identifiable_fit",
    "build_reduced_prefit_identification",
    "load_reduced_identifiable_rows",
]
