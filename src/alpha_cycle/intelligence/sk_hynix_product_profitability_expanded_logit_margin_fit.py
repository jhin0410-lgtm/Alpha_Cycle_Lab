"""Fit the frozen SK hynix v3 expanded clean-panel bounded margin model.

The training panel is exactly 21 clean historical rows: six source-complete 2017Q1-2018Q3
rows plus the original fifteen v1 training rows. The already-seen 2026Q1 outcome is loaded
only as a retrospective contaminated stress diagnostic and never enters estimation, LOOCV,
or a model-selection gate. 2026Q3 is not loaded here.
"""

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
from alpha_cycle.intelligence.sk_hynix_product_profitability_expanded_logit_margin_method import (
    FrozenExpandedLogitMarginMethod,
)
from alpha_cycle.intelligence.sk_hynix_product_profitability_logit_margin_fit import (
    load_logit_margin_training_rows,
)
from alpha_cycle.intelligence.sk_hynix_product_profitability_logit_margin_method import (
    DEFAULT_LOGIT_MARGIN_METHOD,
    load_frozen_logit_margin_method,
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


def _sign(value: float) -> float:
    if value > 0.0:
        return 1.0
    if value < 0.0:
        return -1.0
    return 0.0


def _condition(matrix: np.ndarray) -> float | None:
    norms = np.linalg.norm(matrix, axis=0)
    if np.any(norms == 0.0):
        return None
    value = float(np.linalg.cond(matrix / norms))
    return value if math.isfinite(value) else None


@dataclass(frozen=True)
class ExpandedLogitMarginRow:
    period_id: str
    source_group: str
    company_revenue_krw_million: float
    company_gross_profit_krw_million: float
    dram_revenue_krw_million: float
    nand_revenue_krw_million: float
    other_revenue_krw_million: float
    dram_asp_direction_code: float
    dram_bit_volume_direction_code: float
    nand_asp_direction_code: float
    nand_bit_volume_direction_code: float

    def __post_init__(self) -> None:
        if self.source_group not in {
            "third_wave_exact_numeric_downcast",
            "v1_training_reuse",
            "spent_v1_holdout_contaminated_stress",
        }:
            raise ValueError("Expanded logit-margin row source group is invalid")
        if self.company_revenue_krw_million <= 0.0:
            raise ValueError("Expanded logit-margin company revenue must be positive")
        if min(
            self.dram_revenue_krw_million,
            self.nand_revenue_krw_million,
            self.other_revenue_krw_million,
        ) < 0.0:
            raise ValueError("Expanded logit-margin product revenue cannot be negative")
        total = (
            self.dram_revenue_krw_million
            + self.nand_revenue_krw_million
            + self.other_revenue_krw_million
        )
        if abs(total - self.company_revenue_krw_million) > 1.0:
            raise ValueError("Expanded logit-margin product/company revenue does not reconcile")
        codes = (
            self.dram_asp_direction_code,
            self.dram_bit_volume_direction_code,
            self.nand_asp_direction_code,
            self.nand_bit_volume_direction_code,
        )
        if any(value not in {-1.0, 0.0, 1.0} for value in codes):
            raise ValueError("Expanded logit-margin direction code is invalid")

    @property
    def design_terms(self) -> tuple[float, ...]:
        dram = self.dram_revenue_krw_million
        nand = self.nand_revenue_krw_million
        return (
            dram,
            dram * self.dram_asp_direction_code,
            dram * self.dram_bit_volume_direction_code,
            nand,
            nand * self.nand_asp_direction_code,
            nand * self.nand_bit_volume_direction_code,
            self.other_revenue_krw_million,
        )


@dataclass(frozen=True)
class ExpandedPrefitIdentification:
    row_count: int
    parameter_count: int
    residual_degrees_of_freedom: int
    design_rank: int
    full_direction_design_rank: bool
    normalized_condition_number_report_only: float | None
    leave_one_out_design_ranks: tuple[int, ...]
    all_leave_one_out_direction_designs_full_rank: bool
    leave_one_out_condition_numbers_report_only: tuple[float | None, ...]
    prefit_gate_passed: bool


@dataclass(frozen=True)
class ExpandedSolverResult:
    parameters: tuple[float, ...]
    converged: bool
    iterations: int
    rejected_steps: int
    final_sse_scaled: float
    jacobian_rank: int
    normalized_jacobian_condition_number: float | None


@dataclass(frozen=True)
class ExpandedLeaveOneOut:
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
class ExpandedProductMarginEnvelope:
    product: str
    minimum_margin: float
    maximum_margin: float
    all_regimes_inside_unit_interval: bool


@dataclass(frozen=True)
class ParameterJackknifeDiagnostic:
    parameter_name: str
    full_fit_value: float
    leave_one_out_minimum: float
    leave_one_out_maximum: float
    sign_stability_ratio_report_only: float


@dataclass(frozen=True)
class ContaminatedQ1StressDiagnostic:
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
            raise ValueError("Expanded contaminated stress period drifted")
        if (
            self.used_for_fit
            or self.used_for_model_selection_gate
            or self.claimed_as_independent_holdout
        ):
            raise ValueError("Expanded Q1 stress diagnostic exceeded contamination boundary")


@dataclass(frozen=True)
class ExpandedLogitMarginFitResult:
    evidence_id: str
    evaluation_date: date
    method_evidence_id: str
    training_periods: tuple[str, ...]
    rows: tuple[ExpandedLogitMarginRow, ...]
    prefit_identification: ExpandedPrefitIdentification
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
    loocv: tuple[ExpandedLeaveOneOut, ...]
    all_loocv_folds_converged: bool
    all_loocv_jacobians_full_rank: bool
    loocv_mae_krw_million: float
    benchmark_loocv_mae_krw_million: float
    loocv_beats_benchmark: bool
    dram_margin_envelope: ExpandedProductMarginEnvelope
    nand_margin_envelope: ExpandedProductMarginEnvelope
    other_margin: float
    all_component_margins_inside_unit_interval: bool
    parameter_jackknife_report_only: tuple[ParameterJackknifeDiagnostic, ...]
    contaminated_q1_stress_report_only: ContaminatedQ1StressDiagnostic
    development_gate_passed: bool
    future_holdout_period: str
    future_holdout_evaluation_allowed: bool = False
    future_holdout_loaded: bool = False
    future_holdout_evaluated: bool = False
    numeric_forward_forecast_enabled: bool = False
    target_price_enabled: bool = False
    decision_score_enabled: bool = False

    def __post_init__(self) -> None:
        if len(self.evidence_id) != 64 or len(self.method_evidence_id) != 64:
            raise ValueError("Expanded fit evidence ids must be SHA-256")
        if self.row_count != len(self.rows) or self.row_count != len(self.training_periods):
            raise ValueError("Expanded fit row counts are inconsistent")
        if self.parameter_count != len(self.parameters):
            raise ValueError("Expanded fit parameter count is inconsistent")
        if self.residual_degrees_of_freedom != self.row_count - self.parameter_count:
            raise ValueError("Expanded fit residual DOF is inconsistent")
        if self.full_jacobian_column_rank != (self.jacobian_rank == self.parameter_count):
            raise ValueError("Expanded fit rank flag is inconsistent")
        if self.loocv_beats_benchmark != (
            self.loocv_mae_krw_million < self.benchmark_loocv_mae_krw_million
        ):
            raise ValueError("Expanded fit benchmark flag is inconsistent")
        if self.future_holdout_period != "2026Q3":
            raise ValueError("Expanded fit future holdout drifted")
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
            raise ValueError("Expanded fit exceeded development trust boundary")


def _from_v2_row(row: object, *, stress: bool = False) -> ExpandedLogitMarginRow:
    return ExpandedLogitMarginRow(
        period_id=str(getattr(row, "period_id")),
        source_group=(
            "spent_v1_holdout_contaminated_stress" if stress else "v1_training_reuse"
        ),
        company_revenue_krw_million=float(getattr(row, "company_revenue_krw_million")),
        company_gross_profit_krw_million=float(
            getattr(row, "company_gross_profit_krw_million")
        ),
        dram_revenue_krw_million=float(getattr(row, "dram_revenue_krw_million")),
        nand_revenue_krw_million=float(getattr(row, "nand_revenue_krw_million")),
        other_revenue_krw_million=float(getattr(row, "other_revenue_krw_million")),
        dram_asp_direction_code=float(getattr(row, "dram_asp_direction_code")),
        dram_bit_volume_direction_code=float(getattr(row, "dram_bit_volume_direction_code")),
        nand_asp_direction_code=float(getattr(row, "nand_asp_direction_code")),
        nand_bit_volume_direction_code=float(getattr(row, "nand_bit_volume_direction_code")),
    )


def _third_wave_rows(
    closeout: ThirdWaveCloseout,
    frontier: ThirdWaveFrontier,
) -> tuple[ExpandedLogitMarginRow, ...]:
    if not closeout.all_six_source_layers_complete:
        raise ValueError("Expanded fit requires six source-complete third-wave rows")
    candidate_by_period = {item.period_id: item for item in frontier.candidates}
    rows: list[ExpandedLogitMarginRow] = []
    for period in closeout.source.periods:
        company = period.company_observation
        recovery = period.product_recovery
        if company is None or recovery is None or recovery.observation is None:
            raise ValueError(
                "Expanded fit requires the source-closed third-wave recovery observations"
            )
        product = recovery.observation
        if product.rcept_no != company.rcept_no:
            raise ValueError("Expanded fit third-wave filing receipts diverged")
        candidate = candidate_by_period[period.period_id]
        drivers = candidate.drivers_qoq_percent
        rows.append(
            ExpandedLogitMarginRow(
                period_id=period.period_id,
                source_group="third_wave_exact_numeric_downcast",
                company_revenue_krw_million=company.revenue_krw / 1_000_000.0,
                company_gross_profit_krw_million=company.gross_profit_krw / 1_000_000.0,
                dram_revenue_krw_million=float(product.dram_revenue_million_krw),
                nand_revenue_krw_million=float(product.nand_revenue_million_krw),
                other_revenue_krw_million=float(product.other_revenue_million_krw),
                dram_asp_direction_code=_sign(drivers.dram_asp),
                dram_bit_volume_direction_code=_sign(drivers.dram_bit_volume),
                nand_asp_direction_code=_sign(drivers.nand_asp),
                nand_bit_volume_direction_code=_sign(drivers.nand_bit_volume),
            )
        )
    return tuple(rows)


def load_expanded_logit_margin_rows(
    method: FrozenExpandedLogitMarginMethod,
    closeout: ThirdWaveCloseout,
    frontier: ThirdWaveFrontier,
    *,
    v2_method_path: str | Path = DEFAULT_LOGIT_MARGIN_METHOD,
    v1_training_pointer: str | Path = DEFAULT_REGIME_TRAINING_FIT_POINTER,
    v1_holdout_pointer: str | Path = DEFAULT_REGIME_HOLDOUT_POINTER,
    historical_product_revenue_pointer: str | Path = DEFAULT_HISTORICAL_PRODUCT_REVENUE_POINTER,
    company_profitability_pointer: str | Path = DEFAULT_QUARTERLY_COMPANY_PROFITABILITY_POINTER,
    cycle_driver_pointer: str | Path = DEFAULT_SEC_PRODUCT_CYCLE_DRIVER_POINTER,
) -> tuple[tuple[ExpandedLogitMarginRow, ...], ExpandedLogitMarginRow]:
    v2_method = load_frozen_logit_margin_method(v2_method_path)
    v2_rows = load_logit_margin_training_rows(
        v2_method,
        v1_training_pointer=v1_training_pointer,
        v1_holdout_pointer=v1_holdout_pointer,
        historical_product_revenue_pointer=historical_product_revenue_pointer,
        company_profitability_pointer=company_profitability_pointer,
        cycle_driver_pointer=cycle_driver_pointer,
    )
    if len(v2_rows) != 16 or v2_rows[-1].period_id != "2026Q1":
        raise ValueError("Expanded fit requires the canonical 15+Q1 v2 source-row contract")
    historical = tuple(_from_v2_row(row) for row in v2_rows[:-1])
    stress = _from_v2_row(v2_rows[-1], stress=True)
    third = _third_wave_rows(closeout, frontier)
    clean = third + historical
    if tuple(row.period_id for row in clean) != method.training_periods:
        raise ValueError("Expanded fit clean periods diverged from frozen v3 method")
    if stress.period_id not in method.contaminated_stress_periods:
        raise ValueError("Expanded fit contaminated stress period diverged")
    return clean, stress


def _arrays(rows: tuple[ExpandedLogitMarginRow, ...]) -> tuple[np.ndarray, ...]:
    return (
        np.asarray([r.company_revenue_krw_million for r in rows], dtype=float),
        np.asarray([r.company_gross_profit_krw_million for r in rows], dtype=float),
        np.asarray([r.dram_revenue_krw_million for r in rows], dtype=float),
        np.asarray([r.nand_revenue_krw_million for r in rows], dtype=float),
        np.asarray([r.other_revenue_krw_million for r in rows], dtype=float),
        np.asarray([r.dram_asp_direction_code for r in rows], dtype=float),
        np.asarray([r.dram_bit_volume_direction_code for r in rows], dtype=float),
        np.asarray([r.nand_asp_direction_code for r in rows], dtype=float),
        np.asarray([r.nand_bit_volume_direction_code for r in rows], dtype=float),
    )


def build_expanded_prefit_identification(
    method: FrozenExpandedLogitMarginMethod,
    rows: tuple[ExpandedLogitMarginRow, ...],
) -> ExpandedPrefitIdentification:
    if tuple(row.period_id for row in rows) != method.training_periods:
        raise ValueError("Expanded prefit rows diverged from frozen periods")
    matrix = np.asarray([row.design_terms for row in rows], dtype=float)
    p = method.parameter_count
    rank = int(np.linalg.matrix_rank(matrix))
    loo_ranks: list[int] = []
    loo_conditions: list[float | None] = []
    for index in range(len(rows)):
        fold = np.delete(matrix, index, axis=0)
        loo_ranks.append(int(np.linalg.matrix_rank(fold)))
        loo_conditions.append(_condition(fold))
    gate = method.prefit_identification_gate
    n = len(rows)
    dof = n - p
    all_loo_rank = all(value == p for value in loo_ranks)
    passed = all(
        (
            n == gate.required_row_count,
            p == gate.required_parameter_count,
            dof >= gate.required_residual_degrees_of_freedom,
            rank == p if gate.require_full_direction_design_rank else True,
            all_loo_rank if gate.require_all_leave_one_out_direction_designs_full_rank else True,
        )
    )
    return ExpandedPrefitIdentification(
        row_count=n,
        parameter_count=p,
        residual_degrees_of_freedom=dof,
        design_rank=rank,
        full_direction_design_rank=rank == p,
        normalized_condition_number_report_only=_condition(matrix),
        leave_one_out_design_ranks=tuple(loo_ranks),
        all_leave_one_out_direction_designs_full_rank=all_loo_rank,
        leave_one_out_condition_numbers_report_only=tuple(loo_conditions),
        prefit_gate_passed=passed,
    )


def _predict_jacobian(
    theta: np.ndarray,
    rows: tuple[ExpandedLogitMarginRow, ...],
    scale: float,
) -> tuple[np.ndarray, np.ndarray]:
    _revenue, _target, dram, nand, other, da, db, na, nb = _arrays(rows)
    dram_scaled = dram / scale
    nand_scaled = nand / scale
    other_scaled = other / scale
    md = np.asarray(_sigmoid(theta[0] + theta[1] * da + theta[2] * db), dtype=float)
    mn = np.asarray(_sigmoid(theta[3] + theta[4] * na + theta[5] * nb), dtype=float)
    mo = float(_sigmoid(float(theta[6])))
    prediction = dram_scaled * md + nand_scaled * mn + other_scaled * mo
    dd = dram_scaled * md * (1.0 - md)
    dn = nand_scaled * mn * (1.0 - mn)
    do = other_scaled * mo * (1.0 - mo)
    jac = np.column_stack((dd, dd * da, dd * db, dn, dn * na, dn * nb, do))
    return prediction, jac


def _initial_theta(
    rows: tuple[ExpandedLogitMarginRow, ...],
    method: FrozenExpandedLogitMarginMethod,
) -> np.ndarray:
    revenue, target, *_rest = _arrays(rows)
    probability = float(np.mean(target / revenue))
    probability = min(
        method.solver.maximum_initialization_probability,
        max(method.solver.minimum_initialization_probability, probability),
    )
    logit = math.log(probability / (1.0 - probability))
    return np.asarray([logit, 0.0, 0.0, logit, 0.0, 0.0, logit], dtype=float)


def _solve(
    rows: tuple[ExpandedLogitMarginRow, ...],
    method: FrozenExpandedLogitMarginMethod,
) -> ExpandedSolverResult:
    revenue, target, *_rest = _arrays(rows)
    scale = float(np.mean(revenue))
    if not math.isfinite(scale) or scale <= 0.0:
        raise ValueError("Expanded optimization scale is invalid")
    y = target / scale
    theta = _initial_theta(rows, method)
    damping = method.solver.initial_damping
    total_rejected = 0
    converged = False
    iterations = 0
    for iteration in range(1, method.solver.maximum_iterations + 1):
        prediction, jac = _predict_jacobian(theta, rows, scale)
        residual = prediction - y
        sse = float(np.dot(residual, residual))
        normal = jac.T @ jac
        gradient = jac.T @ residual
        accepted = False
        for _attempt in range(method.solver.maximum_rejected_steps_per_iteration + 1):
            diagonal = np.maximum(np.diag(normal), 1e-12)
            hessian = normal + damping * np.diag(diagonal)
            try:
                step = np.linalg.solve(hessian, -gradient)
            except np.linalg.LinAlgError:
                step = np.linalg.lstsq(hessian, -gradient, rcond=None)[0]
            candidate = theta + step
            candidate_prediction, _candidate_jac = _predict_jacobian(candidate, rows, scale)
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
            total_rejected += 1
        if not accepted:
            iterations = iteration
            break
        if converged:
            break
    prediction, jac = _predict_jacobian(theta, rows, scale)
    residual = prediction - y
    return ExpandedSolverResult(
        parameters=tuple(float(value) for value in theta),
        converged=converged,
        iterations=iterations,
        rejected_steps=total_rejected,
        final_sse_scaled=float(np.dot(residual, residual)),
        jacobian_rank=int(np.linalg.matrix_rank(jac)),
        normalized_jacobian_condition_number=_condition(jac),
    )


def _prediction_original(
    parameters: tuple[float, ...],
    rows: tuple[ExpandedLogitMarginRow, ...],
) -> np.ndarray:
    revenue, _target, *_rest = _arrays(rows)
    scale = float(np.mean(revenue))
    prediction, _jac = _predict_jacobian(np.asarray(parameters, dtype=float), rows, scale)
    return prediction * scale


def _envelope(
    product: str,
    intercept: float,
    asp: float,
    bit: float,
) -> ExpandedProductMarginEnvelope:
    values = tuple(
        float(_sigmoid(intercept + asp * asp_code + bit * bit_code))
        for asp_code in (-1.0, 0.0, 1.0)
        for bit_code in (-1.0, 0.0, 1.0)
    )
    return ExpandedProductMarginEnvelope(
        product=product,
        minimum_margin=min(values),
        maximum_margin=max(values),
        all_regimes_inside_unit_interval=all(0.0 < value < 1.0 for value in values),
    )


def _jackknife(
    method: FrozenExpandedLogitMarginMethod,
    full_parameters: tuple[float, ...],
    fold_parameters: tuple[tuple[float, ...], ...],
) -> tuple[ParameterJackknifeDiagnostic, ...]:
    result: list[ParameterJackknifeDiagnostic] = []
    for index, name in enumerate(method.parameters):
        values = tuple(item[index] for item in fold_parameters)
        full = full_parameters[index]
        full_sign = 1 if full > 0.0 else -1 if full < 0.0 else 0
        same = sum(
            (1 if value > 0.0 else -1 if value < 0.0 else 0) == full_sign
            for value in values
        )
        result.append(
            ParameterJackknifeDiagnostic(
                parameter_name=name,
                full_fit_value=full,
                leave_one_out_minimum=min(values),
                leave_one_out_maximum=max(values),
                sign_stability_ratio_report_only=same / len(values),
            )
        )
    return tuple(result)


def build_expanded_logit_margin_fit(
    method: FrozenExpandedLogitMarginMethod,
    rows: tuple[ExpandedLogitMarginRow, ...],
    contaminated_q1: ExpandedLogitMarginRow,
    *,
    evaluation_date: date,
) -> ExpandedLogitMarginFitResult:
    prefit = build_expanded_prefit_identification(method, rows)
    if not prefit.prefit_gate_passed:
        raise ValueError("Expanded prefit identification gate failed; fit not attempted")
    if contaminated_q1.period_id != "2026Q1":
        raise ValueError("Expanded fit requires the contaminated 2026Q1 stress row")
    full = _solve(rows, method)
    prediction = _prediction_original(full.parameters, rows)
    revenue, target, *_rest = _arrays(rows)
    errors = target - prediction
    loocv: list[ExpandedLeaveOneOut] = []
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
            ExpandedLeaveOneOut(
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
    dram = _envelope("DRAM", full.parameters[0], full.parameters[1], full.parameters[2])
    nand = _envelope("NAND", full.parameters[3], full.parameters[4], full.parameters[5])
    other_margin = float(_sigmoid(full.parameters[6]))
    all_bounds = all(
        (
            dram.all_regimes_inside_unit_interval,
            nand.all_regimes_inside_unit_interval,
            0.0 < other_margin < 1.0,
        )
    )
    p = method.parameter_count
    all_fold_converged = all(item.converged for item in loocv)
    all_fold_rank = all(item.jacobian_rank == p for item in loocv)
    full_rank = full.jacobian_rank == p
    gate = method.validation_gate
    n = len(rows)
    dof = n - p
    development_gate = all(
        (
            prefit.prefit_gate_passed,
            n == gate.required_row_count,
            p == gate.required_parameter_count,
            dof >= gate.required_residual_degrees_of_freedom,
            full_rank if gate.require_full_jacobian_column_rank else True,
            full.converged if gate.require_optimizer_convergence else True,
            all_fold_converged if gate.require_all_leave_one_out_folds_converged else True,
            all_fold_rank if gate.require_all_leave_one_out_jacobians_full_rank else True,
            loocv_mae < benchmark_mae if gate.require_loocv_mae_better_than_benchmark else True,
            all_bounds if gate.require_all_component_margins_inside_unit_interval else True,
        )
    )
    stress_prediction = float(_prediction_original(full.parameters, (contaminated_q1,))[0])
    training_margin = float(np.mean(target / revenue))
    stress_benchmark = training_margin * contaminated_q1.company_revenue_krw_million
    stress = ContaminatedQ1StressDiagnostic(
        period_id="2026Q1",
        model_prediction_krw_million=stress_prediction,
        actual_krw_million=contaminated_q1.company_gross_profit_krw_million,
        model_absolute_error_krw_million=abs(
            contaminated_q1.company_gross_profit_krw_million - stress_prediction
        ),
        benchmark_prediction_krw_million=stress_benchmark,
        benchmark_absolute_error_krw_million=abs(
            contaminated_q1.company_gross_profit_krw_million - stress_benchmark
        ),
        model_beats_benchmark_report_only=(
            abs(contaminated_q1.company_gross_profit_krw_million - stress_prediction)
            < abs(contaminated_q1.company_gross_profit_krw_million - stress_benchmark)
        ),
    )
    jackknife = _jackknife(method, full.parameters, tuple(fold_parameters))
    stable = {
        "evaluation_date": evaluation_date.isoformat(),
        "method_evidence_id": method.evidence_id,
        "training_periods": method.training_periods,
        "rows": [asdict(item) for item in rows],
        "prefit": asdict(prefit),
        "parameters": full.parameters,
        "loocv": [asdict(item) for item in loocv],
        "stress": asdict(stress),
        "development_gate_passed": development_gate,
    }
    return ExpandedLogitMarginFitResult(
        evidence_id=_sha(stable),
        evaluation_date=evaluation_date,
        method_evidence_id=method.evidence_id,
        training_periods=method.training_periods,
        rows=rows,
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
            full.normalized_jacobian_condition_number
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
        other_margin=other_margin,
        all_component_margins_inside_unit_interval=all_bounds,
        parameter_jackknife_report_only=jackknife,
        contaminated_q1_stress_report_only=stress,
        development_gate_passed=development_gate,
        future_holdout_period=method.untouched_holdout_period,
    )


__all__ = [
    "ContaminatedQ1StressDiagnostic",
    "ExpandedLeaveOneOut",
    "ExpandedLogitMarginFitResult",
    "ExpandedLogitMarginRow",
    "ExpandedPrefitIdentification",
    "ExpandedProductMarginEnvelope",
    "ParameterJackknifeDiagnostic",
    "build_expanded_logit_margin_fit",
    "build_expanded_prefit_identification",
    "load_expanded_logit_margin_rows",
]
