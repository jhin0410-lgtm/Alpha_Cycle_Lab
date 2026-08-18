"""Fit the frozen SK hynix V5 company-GP empirical regime model."""

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
from alpha_cycle.intelligence.sk_hynix_company_gross_profit_empirical_regime_method import (
    FrozenCompanyGPEmpiricalMethod,
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


def _condition(matrix: np.ndarray) -> float | None:
    norms = np.linalg.norm(matrix, axis=0)
    if np.any(norms == 0.0):
        return None
    value = float(np.linalg.cond(matrix / norms))
    return value if math.isfinite(value) else None


@dataclass(frozen=True)
class CompanyGPEmpiricalRow:
    period_id: str
    source_group: str
    company_revenue_krw_million: float
    company_gross_profit_krw_million: float
    nand_revenue_krw_million: float
    other_revenue_krw_million: float
    dram_asp_direction_code: float
    dram_bit_volume_direction_code: float
    nand_asp_direction_code: float
    nand_bit_volume_direction_code: float

    @property
    def design_terms(self) -> tuple[float, ...]:
        revenue = self.company_revenue_krw_million
        return (
            revenue,
            revenue * self.dram_asp_direction_code,
            revenue * self.dram_bit_volume_direction_code,
            revenue * self.nand_asp_direction_code,
            revenue * self.nand_bit_volume_direction_code,
            self.nand_revenue_krw_million,
            self.other_revenue_krw_million,
        )


@dataclass(frozen=True)
class EmpiricalPrefitIdentification:
    row_count: int
    parameter_count: int
    residual_degrees_of_freedom: int
    design_rank: int
    full_design_column_rank: bool
    normalized_condition_number_report_only: float | None
    leave_one_out_design_ranks: tuple[int, ...]
    all_leave_one_out_designs_full_rank: bool
    leave_one_out_condition_numbers_report_only: tuple[float | None, ...]
    prefit_gate_passed: bool


@dataclass(frozen=True)
class EmpiricalLeaveOneOut:
    held_out_period: str
    design_rank: int
    model_prediction_krw_million: float
    actual_krw_million: float
    model_absolute_error_krw_million: float
    benchmark_prediction_krw_million: float
    benchmark_absolute_error_krw_million: float
    coefficients_report_only: tuple[float, ...]


@dataclass(frozen=True)
class EmpiricalParameterJackknife:
    parameter_name: str
    full_fit_value: float
    leave_one_out_minimum: float
    leave_one_out_maximum: float
    sign_stability_ratio_report_only: float


@dataclass(frozen=True)
class EmpiricalQ1Stress:
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
            raise ValueError("V5 contaminated stress period drifted")
        if (
            self.used_for_fit
            or self.used_for_model_selection_gate
            or self.claimed_as_independent_holdout
        ):
            raise ValueError("V5 contaminated stress exceeded trust boundary")


@dataclass(frozen=True)
class CompanyGPEmpiricalFitResult:
    evidence_id: str
    evaluation_date: date
    method_evidence_id: str
    training_periods: tuple[str, ...]
    row_count: int
    parameter_count: int
    residual_degrees_of_freedom: int
    prefit_identification: EmpiricalPrefitIdentification
    coefficients: tuple[float, ...]
    design_rank: int
    full_design_column_rank: bool
    normalized_condition_number_report_only: float | None
    in_sample_mae_krw_million: float
    in_sample_rmse_krw_million: float
    in_sample_r_squared_report_only: float
    loocv: tuple[EmpiricalLeaveOneOut, ...]
    all_loocv_designs_full_rank: bool
    loocv_mae_krw_million: float
    benchmark_loocv_mae_krw_million: float
    loocv_beats_benchmark: bool
    parameter_jackknife_report_only: tuple[EmpiricalParameterJackknife, ...]
    contaminated_q1_stress_report_only: EmpiricalQ1Stress
    development_gate_passed: bool
    coefficient_interpretation: str = "empirical_company_gp_weights_not_product_margins"
    product_margin_structural_interpretation_allowed: bool = False
    product_margin_output_enabled: bool = False
    future_holdout_period: str = "2026Q3"
    future_holdout_evaluation_allowed: bool = False
    future_holdout_loaded: bool = False
    future_holdout_evaluated: bool = False
    numeric_forward_forecast_enabled: bool = False
    target_price_enabled: bool = False
    decision_score_enabled: bool = False

    def __post_init__(self) -> None:
        if len(self.evidence_id) != 64 or len(self.method_evidence_id) != 64:
            raise ValueError("V5 fit evidence ids must be SHA-256")
        if self.row_count != len(self.training_periods):
            raise ValueError("V5 fit row count is inconsistent")
        if self.parameter_count != len(self.coefficients):
            raise ValueError("V5 fit parameter count is inconsistent")
        if self.full_design_column_rank != (self.design_rank == self.parameter_count):
            raise ValueError("V5 fit rank flag is inconsistent")
        if self.loocv_beats_benchmark != (
            self.loocv_mae_krw_million < self.benchmark_loocv_mae_krw_million
        ):
            raise ValueError("V5 benchmark flag is inconsistent")
        if self.product_margin_structural_interpretation_allowed or self.product_margin_output_enabled:
            raise ValueError("V5 cannot reopen product-margin structural scope")
        if self.future_holdout_period != "2026Q3":
            raise ValueError("V5 future holdout drifted")
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
            raise ValueError("V5 exceeded development trust boundary")


def _from_expanded(row: ExpandedLogitMarginRow) -> CompanyGPEmpiricalRow:
    return CompanyGPEmpiricalRow(
        period_id=row.period_id,
        source_group=row.source_group,
        company_revenue_krw_million=row.company_revenue_krw_million,
        company_gross_profit_krw_million=row.company_gross_profit_krw_million,
        nand_revenue_krw_million=row.nand_revenue_krw_million,
        other_revenue_krw_million=row.other_revenue_krw_million,
        dram_asp_direction_code=row.dram_asp_direction_code,
        dram_bit_volume_direction_code=row.dram_bit_volume_direction_code,
        nand_asp_direction_code=row.nand_asp_direction_code,
        nand_bit_volume_direction_code=row.nand_bit_volume_direction_code,
    )


def load_company_gp_empirical_rows(
    method: FrozenCompanyGPEmpiricalMethod,
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
) -> tuple[tuple[CompanyGPEmpiricalRow, ...], CompanyGPEmpiricalRow]:
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
    converted = tuple(_from_expanded(row) for row in rows)
    converted_stress = _from_expanded(stress)
    if tuple(row.period_id for row in converted) != method.training_periods:
        raise ValueError("V5 source rows diverged from frozen training periods")
    if converted_stress.period_id not in method.contaminated_stress_periods:
        raise ValueError("V5 contaminated stress period diverged")
    return converted, converted_stress


def _matrix(rows: tuple[CompanyGPEmpiricalRow, ...]) -> np.ndarray:
    return np.asarray([row.design_terms for row in rows], dtype=float)


def _target(rows: tuple[CompanyGPEmpiricalRow, ...]) -> np.ndarray:
    return np.asarray([row.company_gross_profit_krw_million for row in rows], dtype=float)


def build_empirical_prefit_identification(
    method: FrozenCompanyGPEmpiricalMethod,
    rows: tuple[CompanyGPEmpiricalRow, ...],
) -> EmpiricalPrefitIdentification:
    if tuple(row.period_id for row in rows) != method.training_periods:
        raise ValueError("V5 prefit rows diverged from frozen periods")
    design = _matrix(rows)
    p = method.parameter_count
    rank = int(np.linalg.matrix_rank(design))
    loo_ranks: list[int] = []
    loo_conditions: list[float | None] = []
    for index in range(len(rows)):
        fold = np.delete(design, index, axis=0)
        loo_ranks.append(int(np.linalg.matrix_rank(fold)))
        loo_conditions.append(_condition(fold))
    n = len(rows)
    dof = n - p
    all_loo_rank = all(value == p for value in loo_ranks)
    gate = method.prefit_gate
    passed = all(
        (
            n == gate.required_row_count,
            p == gate.required_parameter_count,
            dof >= gate.required_residual_degrees_of_freedom,
            rank == p if gate.require_full_design_column_rank else True,
            all_loo_rank if gate.require_all_leave_one_out_designs_full_rank else True,
        )
    )
    return EmpiricalPrefitIdentification(
        row_count=n,
        parameter_count=p,
        residual_degrees_of_freedom=dof,
        design_rank=rank,
        full_design_column_rank=rank == p,
        normalized_condition_number_report_only=_condition(design),
        leave_one_out_design_ranks=tuple(loo_ranks),
        all_leave_one_out_designs_full_rank=all_loo_rank,
        leave_one_out_condition_numbers_report_only=tuple(loo_conditions),
        prefit_gate_passed=passed,
    )


def _ols(rows: tuple[CompanyGPEmpiricalRow, ...]) -> tuple[np.ndarray, int]:
    design = _matrix(rows)
    target = _target(rows)
    coefficients, _residuals, rank, _singular = np.linalg.lstsq(design, target, rcond=None)
    return np.asarray(coefficients, dtype=float), int(rank)


def _jackknife(
    method: FrozenCompanyGPEmpiricalMethod,
    full: tuple[float, ...],
    folds: tuple[tuple[float, ...], ...],
) -> tuple[EmpiricalParameterJackknife, ...]:
    diagnostics: list[EmpiricalParameterJackknife] = []
    for index, name in enumerate(method.parameters):
        values = tuple(row[index] for row in folds)
        full_value = full[index]
        full_sign = 1 if full_value > 0.0 else -1 if full_value < 0.0 else 0
        same = sum(
            (1 if value > 0.0 else -1 if value < 0.0 else 0) == full_sign
            for value in values
        )
        diagnostics.append(
            EmpiricalParameterJackknife(
                parameter_name=name,
                full_fit_value=full_value,
                leave_one_out_minimum=min(values),
                leave_one_out_maximum=max(values),
                sign_stability_ratio_report_only=same / len(values),
            )
        )
    return tuple(diagnostics)


def build_company_gp_empirical_fit(
    method: FrozenCompanyGPEmpiricalMethod,
    rows: tuple[CompanyGPEmpiricalRow, ...],
    contaminated_q1: CompanyGPEmpiricalRow,
    *,
    evaluation_date: date,
) -> CompanyGPEmpiricalFitResult:
    prefit = build_empirical_prefit_identification(method, rows)
    if not prefit.prefit_gate_passed:
        raise ValueError("V5 prefit identification gate failed; fit not attempted")
    design = _matrix(rows)
    target = _target(rows)
    coefficients_array, rank = _ols(rows)
    prediction = design @ coefficients_array
    errors = target - prediction
    total = float(np.sum(np.square(target - np.mean(target))))
    residual = float(np.sum(np.square(errors)))
    r_squared = 1.0 - residual / total if total > 0.0 else 0.0

    loocv: list[EmpiricalLeaveOneOut] = []
    fold_coefficients: list[tuple[float, ...]] = []
    for index, held_out in enumerate(rows):
        fold_rows = rows[:index] + rows[index + 1 :]
        fold_coefficients_array, fold_rank = _ols(fold_rows)
        fold_coefficients_tuple = tuple(float(value) for value in fold_coefficients_array)
        fold_coefficients.append(fold_coefficients_tuple)
        model_prediction = float(
            np.dot(np.asarray(held_out.design_terms, dtype=float), fold_coefficients_array)
        )
        train_margin = float(
            np.mean(
                [
                    row.company_gross_profit_krw_million / row.company_revenue_krw_million
                    for row in fold_rows
                ]
            )
        )
        benchmark_prediction = train_margin * held_out.company_revenue_krw_million
        loocv.append(
            EmpiricalLeaveOneOut(
                held_out_period=held_out.period_id,
                design_rank=fold_rank,
                model_prediction_krw_million=model_prediction,
                actual_krw_million=held_out.company_gross_profit_krw_million,
                model_absolute_error_krw_million=abs(
                    held_out.company_gross_profit_krw_million - model_prediction
                ),
                benchmark_prediction_krw_million=benchmark_prediction,
                benchmark_absolute_error_krw_million=abs(
                    held_out.company_gross_profit_krw_million - benchmark_prediction
                ),
                coefficients_report_only=fold_coefficients_tuple,
            )
        )

    loocv_mae = float(np.mean([item.model_absolute_error_krw_million for item in loocv]))
    benchmark_mae = float(
        np.mean([item.benchmark_absolute_error_krw_million for item in loocv])
    )
    all_loocv_rank = all(item.design_rank == method.parameter_count for item in loocv)
    full_coefficients = tuple(float(value) for value in coefficients_array)
    train_mean_margin = float(
        np.mean(
            [
                row.company_gross_profit_krw_million / row.company_revenue_krw_million
                for row in rows
            ]
        )
    )
    stress_prediction = float(
        np.dot(np.asarray(contaminated_q1.design_terms, dtype=float), coefficients_array)
    )
    stress_benchmark = train_mean_margin * contaminated_q1.company_revenue_krw_million
    stress = EmpiricalQ1Stress(
        period_id=contaminated_q1.period_id,
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
    gate = method.development_gate
    development_gate = all(
        (
            rank == method.parameter_count if gate.require_full_fit_design_rank else True,
            all_loocv_rank if gate.require_all_leave_one_out_fit_designs_full_rank else True,
            loocv_mae < benchmark_mae if gate.require_loocv_mae_better_than_benchmark else True,
        )
    )
    stable = {
        "evaluation_date": evaluation_date.isoformat(),
        "method_evidence_id": method.evidence_id,
        "training_periods": method.training_periods,
        "coefficients": full_coefficients,
        "rank": rank,
        "loocv": [asdict(item) for item in loocv],
        "development_gate_passed": development_gate,
    }
    return CompanyGPEmpiricalFitResult(
        evidence_id=_sha(stable),
        evaluation_date=evaluation_date,
        method_evidence_id=method.evidence_id,
        training_periods=method.training_periods,
        row_count=len(rows),
        parameter_count=method.parameter_count,
        residual_degrees_of_freedom=len(rows) - method.parameter_count,
        prefit_identification=prefit,
        coefficients=full_coefficients,
        design_rank=rank,
        full_design_column_rank=rank == method.parameter_count,
        normalized_condition_number_report_only=_condition(design),
        in_sample_mae_krw_million=float(np.mean(np.abs(errors))),
        in_sample_rmse_krw_million=float(np.sqrt(np.mean(np.square(errors)))),
        in_sample_r_squared_report_only=r_squared,
        loocv=tuple(loocv),
        all_loocv_designs_full_rank=all_loocv_rank,
        loocv_mae_krw_million=loocv_mae,
        benchmark_loocv_mae_krw_million=benchmark_mae,
        loocv_beats_benchmark=loocv_mae < benchmark_mae,
        parameter_jackknife_report_only=_jackknife(
            method,
            full_coefficients,
            tuple(fold_coefficients),
        ),
        contaminated_q1_stress_report_only=stress,
        development_gate_passed=development_gate,
    )


__all__ = [
    "CompanyGPEmpiricalFitResult",
    "CompanyGPEmpiricalRow",
    "EmpiricalLeaveOneOut",
    "EmpiricalParameterJackknife",
    "EmpiricalPrefitIdentification",
    "EmpiricalQ1Stress",
    "build_company_gp_empirical_fit",
    "build_empirical_prefit_identification",
    "load_company_gp_empirical_rows",
]
