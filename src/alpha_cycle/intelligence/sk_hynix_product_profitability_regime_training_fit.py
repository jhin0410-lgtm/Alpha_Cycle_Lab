"""Fit and diagnose the frozen 15-row SK hynix direction-regime estimator.

This module operates only after the frozen method manifest exists. It combines the nine
legacy rank-probe rows with six source-complete second-wave rows, maps every driver to the
same categorical sign regime, runs OLS, and applies pre-registered training diagnostics.
It never loads or evaluates the 2026Q1 holdout.
"""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import asdict, dataclass
from datetime import date

import numpy as np

from alpha_cycle.intelligence.sk_hynix_product_profitability_regime_estimation_method import (
    FrozenRegimeEstimationMethod,
)
from alpha_cycle.intelligence.sk_hynix_product_profitability_second_wave_closeout import (
    SecondWaveCloseout,
)
from alpha_cycle.intelligence.sk_hynix_product_profitability_second_wave_frontier import (
    SecondWaveFrontier,
)
from alpha_cycle.intelligence.sk_hynix_product_profitability_structural_method import (
    StructuralRankProbeResult,
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


def _sign(value: float) -> float:
    if value > 0.0:
        return 1.0
    if value < 0.0:
        return -1.0
    return 0.0


def _rmse(errors: np.ndarray) -> float:
    return float(np.sqrt(np.mean(np.square(errors))))


def _r2(actual: np.ndarray, predicted: np.ndarray) -> float | None:
    centered = actual - float(np.mean(actual))
    denominator = float(np.dot(centered, centered))
    if denominator == 0.0:
        return None
    residual = actual - predicted
    return 1.0 - float(np.dot(residual, residual)) / denominator


@dataclass(frozen=True)
class RegimeTrainingRow:
    period_id: str
    source_group: str
    product_revenue_evidence_id: str
    company_revenue_krw_million: float
    company_gross_profit_krw_million: float
    dram_revenue_krw_million: float
    nand_revenue_krw_million: float
    other_revenue_krw_million: float
    dram_asp_direction_code: float
    dram_bit_volume_direction_code: float
    nand_asp_direction_code: float
    nand_bit_volume_direction_code: float
    design_terms: tuple[float, ...]
    company_product_revenue_reconciled: bool

    def __post_init__(self) -> None:
        if self.source_group not in {"legacy_text_direction", "second_wave_numeric_downcast"}:
            raise ValueError("Regime training row source group is invalid")
        if len(self.product_revenue_evidence_id) != 64:
            raise ValueError("Regime training row product evidence id must be SHA-256")
        if len(self.design_terms) != 7:
            raise ValueError("Regime training row must retain seven design terms")
        if self.company_revenue_krw_million <= 0.0:
            raise ValueError("Regime training row company revenue must be positive")
        codes = (
            self.dram_asp_direction_code,
            self.dram_bit_volume_direction_code,
            self.nand_asp_direction_code,
            self.nand_bit_volume_direction_code,
        )
        if any(value not in {-1.0, 0.0, 1.0} for value in codes):
            raise ValueError("Regime training row driver code is invalid")
        if not self.company_product_revenue_reconciled:
            raise ValueError("Regime training row requires exact company/product reconciliation")


@dataclass(frozen=True)
class LeaveOneOutDiagnostic:
    held_out_period: str
    training_rank: int
    full_rank: bool
    model_prediction_krw_million: float
    actual_krw_million: float
    model_absolute_error_krw_million: float
    benchmark_prediction_krw_million: float
    benchmark_absolute_error_krw_million: float


@dataclass(frozen=True)
class CoefficientStabilityDiagnostic:
    parameter: str
    full_fit_value: float
    leave_one_out_min: float
    leave_one_out_max: float
    sign_stability_ratio: float

    def __post_init__(self) -> None:
        if not 0.0 <= self.sign_stability_ratio <= 1.0:
            raise ValueError("Coefficient sign stability ratio is invalid")


@dataclass(frozen=True)
class RegimeTrainingFitResult:
    evidence_id: str
    evaluation_date: date
    method_evidence_id: str
    base_rank_probe_evidence_id: str
    training_periods: tuple[str, ...]
    rows: tuple[RegimeTrainingRow, ...]
    row_count: int
    parameter_count: int
    residual_degrees_of_freedom: int
    design_rank: int
    full_column_rank: bool
    normalized_condition_number: float | None
    coefficients: tuple[float, ...]
    in_sample_mae_krw_million: float
    in_sample_rmse_krw_million: float
    in_sample_r2: float | None
    loocv: tuple[LeaveOneOutDiagnostic, ...]
    all_loocv_folds_full_rank: bool
    loocv_mae_krw_million: float
    benchmark_loocv_mae_krw_million: float
    loocv_beats_benchmark: bool
    mean_training_gross_margin: float
    max_leverage: float
    max_cooks_distance: float | None
    coefficient_stability: tuple[CoefficientStabilityDiagnostic, ...]
    training_gate_passed: bool
    one_time_holdout_evaluation_ready: bool
    coefficient_estimates_are_model_outputs: bool = True
    product_profitability_is_direct_source_fact: bool = False
    holdout_loaded: bool = False
    holdout_evaluated: bool = False
    numeric_forecast_enabled: bool = False
    fair_value_estimate_enabled: bool = False
    target_price_enabled: bool = False
    decision_score_enabled: bool = False

    def __post_init__(self) -> None:
        if len(self.evidence_id) != 64 or len(self.method_evidence_id) != 64:
            raise ValueError("Regime training fit evidence ids must be SHA-256")
        if len(self.base_rank_probe_evidence_id) != 64:
            raise ValueError("Regime training fit base evidence id must be SHA-256")
        if self.row_count != len(self.rows) or self.row_count != len(self.training_periods):
            raise ValueError("Regime training fit row counts are inconsistent")
        if self.parameter_count != len(self.coefficients):
            raise ValueError("Regime training fit coefficient count is inconsistent")
        if self.residual_degrees_of_freedom != self.row_count - self.parameter_count:
            raise ValueError("Regime training fit residual DOF is inconsistent")
        if self.full_column_rank != (self.design_rank == self.parameter_count):
            raise ValueError("Regime training fit rank flag is inconsistent")
        if self.all_loocv_folds_full_rank != all(item.full_rank for item in self.loocv):
            raise ValueError("Regime training fit LOOCV rank flag is inconsistent")
        if self.loocv_beats_benchmark != (
            self.loocv_mae_krw_million < self.benchmark_loocv_mae_krw_million
        ):
            raise ValueError("Regime training fit benchmark flag is inconsistent")
        if self.one_time_holdout_evaluation_ready != self.training_gate_passed:
            raise ValueError("Regime training fit holdout-readiness flag is inconsistent")
        if (
            not self.coefficient_estimates_are_model_outputs
            or self.product_profitability_is_direct_source_fact
            or self.holdout_loaded
            or self.holdout_evaluated
            or self.numeric_forecast_enabled
            or self.fair_value_estimate_enabled
            or self.target_price_enabled
            or self.decision_score_enabled
        ):
            raise ValueError("Regime training fit exceeded its pre-holdout trust boundary")


def _normalized_condition_number(matrix: np.ndarray) -> float | None:
    norms = np.linalg.norm(matrix, axis=0)
    if np.any(norms == 0.0):
        return None
    value = float(np.linalg.cond(matrix / norms))
    return value if math.isfinite(value) else None


def _build_rows(
    method: FrozenRegimeEstimationMethod,
    base_rank_probe: StructuralRankProbeResult,
    closeout: SecondWaveCloseout,
    frontier: SecondWaveFrontier,
) -> tuple[RegimeTrainingRow, ...]:
    if not closeout.all_six_source_layers_complete:
        raise ValueError("Regime training fit requires six source-complete second-wave rows")
    base_by_period = {item.period_id: item for item in base_rank_probe.rows}
    candidate_by_period = {item.period_id: item for item in frontier.candidates}
    closeout_by_period = {item.period_id: item for item in closeout.periods}
    rows: list[RegimeTrainingRow] = []
    for period_id in method.training_periods:
        if period_id in base_by_period:
            item = base_by_period[period_id]
            rows.append(
                RegimeTrainingRow(
                    period_id=period_id,
                    source_group="legacy_text_direction",
                    product_revenue_evidence_id=item.product_revenue_evidence_id,
                    company_revenue_krw_million=item.company_revenue_krw_million,
                    company_gross_profit_krw_million=item.company_gross_profit_krw_million,
                    dram_revenue_krw_million=item.dram_revenue_krw_million,
                    nand_revenue_krw_million=item.nand_revenue_krw_million,
                    other_revenue_krw_million=item.other_revenue_krw_million,
                    dram_asp_direction_code=item.dram_asp.code,
                    dram_bit_volume_direction_code=item.dram_bit_volume.code,
                    nand_asp_direction_code=item.nand_asp.code,
                    nand_bit_volume_direction_code=item.nand_bit_volume.code,
                    design_terms=item.design_terms,
                    company_product_revenue_reconciled=(
                        item.revenue_reconciliation_delta_krw == 0
                    ),
                )
            )
            continue
        closeout_item = closeout_by_period.get(period_id)
        candidate = candidate_by_period.get(period_id)
        if closeout_item is None or candidate is None:
            raise ValueError(f"Regime training fit lacks source row: {period_id}")
        company = closeout_item.company_observation
        recovery = closeout_item.product_recovery
        if company is None or recovery is None or recovery.observation is None:
            raise ValueError(f"Regime training fit lacks certified second-wave row: {period_id}")
        product = recovery.observation
        if product.rcept_no != company.rcept_no:
            raise ValueError("Regime training fit second-wave receipt binding diverged")
        total_delta = product.total_revenue_million_krw * 1_000_000 - company.revenue_krw
        drivers = candidate.drivers_qoq_percent
        dram = float(product.dram_revenue_million_krw)
        nand = float(product.nand_revenue_million_krw)
        other = float(product.other_revenue_million_krw)
        dram_asp = _sign(drivers.dram_asp)
        dram_bit = _sign(drivers.dram_bit_volume)
        nand_asp = _sign(drivers.nand_asp)
        nand_bit = _sign(drivers.nand_bit_volume)
        rows.append(
            RegimeTrainingRow(
                period_id=period_id,
                source_group="second_wave_numeric_downcast",
                product_revenue_evidence_id=product.evidence_id,
                company_revenue_krw_million=company.revenue_krw / 1_000_000.0,
                company_gross_profit_krw_million=company.gross_profit_krw / 1_000_000.0,
                dram_revenue_krw_million=dram,
                nand_revenue_krw_million=nand,
                other_revenue_krw_million=other,
                dram_asp_direction_code=dram_asp,
                dram_bit_volume_direction_code=dram_bit,
                nand_asp_direction_code=nand_asp,
                nand_bit_volume_direction_code=nand_bit,
                design_terms=(
                    dram,
                    dram * dram_asp,
                    dram * dram_bit,
                    nand,
                    nand * nand_asp,
                    nand * nand_bit,
                    other,
                ),
                company_product_revenue_reconciled=total_delta == 0,
            )
        )
    if tuple(item.period_id for item in rows) != method.training_periods:
        raise ValueError("Regime training fit period order diverged from frozen method")
    return tuple(rows)


def _fit(matrix: np.ndarray, target: np.ndarray) -> tuple[np.ndarray, int]:
    coefficients, _residuals, rank, _singular = np.linalg.lstsq(matrix, target, rcond=None)
    return coefficients, int(rank)


def build_regime_training_fit(
    method: FrozenRegimeEstimationMethod,
    base_rank_probe: StructuralRankProbeResult,
    closeout: SecondWaveCloseout,
    frontier: SecondWaveFrontier,
    *,
    evaluation_date: date,
) -> RegimeTrainingFitResult:
    """Run the frozen training fit without loading the sealed holdout."""

    if method.ticker != frontier.ticker:
        raise ValueError("Regime training fit issuer binding diverged")
    if method.holdout_period != frontier.holdout_period:
        raise ValueError("Regime training fit holdout binding diverged")
    if base_rank_probe.method_version != "0.1-draft":
        raise ValueError("Regime training fit baseline rank-probe version drifted")
    rows = _build_rows(method, base_rank_probe, closeout, frontier)
    matrix = np.asarray([item.design_terms for item in rows], dtype=float)
    target = np.asarray([item.company_gross_profit_krw_million for item in rows], dtype=float)
    revenue = np.asarray([item.company_revenue_krw_million for item in rows], dtype=float)
    coefficients, rank = _fit(matrix, target)
    prediction = matrix @ coefficients
    errors = target - prediction
    p = method.parameter_count
    n = len(rows)
    dof = n - p
    full_rank = rank == p
    condition = _normalized_condition_number(matrix)

    loocv: list[LeaveOneOutDiagnostic] = []
    jackknife: list[np.ndarray] = []
    for index, row in enumerate(rows):
        keep = np.ones(n, dtype=bool)
        keep[index] = False
        fold_x = matrix[keep]
        fold_y = target[keep]
        fold_beta, fold_rank = _fit(fold_x, fold_y)
        jackknife.append(fold_beta)
        model_prediction = float(matrix[index] @ fold_beta)
        actual = float(target[index])
        training_margins = fold_y / revenue[keep]
        benchmark_prediction = float(np.mean(training_margins) * revenue[index])
        loocv.append(
            LeaveOneOutDiagnostic(
                held_out_period=row.period_id,
                training_rank=fold_rank,
                full_rank=fold_rank == p,
                model_prediction_krw_million=model_prediction,
                actual_krw_million=actual,
                model_absolute_error_krw_million=abs(actual - model_prediction),
                benchmark_prediction_krw_million=benchmark_prediction,
                benchmark_absolute_error_krw_million=abs(actual - benchmark_prediction),
            )
        )

    loocv_mae = float(np.mean([item.model_absolute_error_krw_million for item in loocv]))
    benchmark_mae = float(
        np.mean([item.benchmark_absolute_error_krw_million for item in loocv])
    )
    all_fold_rank = all(item.full_rank for item in loocv)

    pseudo_inverse = np.linalg.pinv(matrix)
    leverage = np.diag(matrix @ pseudo_inverse)
    max_leverage = float(np.max(leverage))
    mse = float(np.dot(errors, errors) / dof) if dof > 0 else math.nan
    cooks: np.ndarray | None = None
    if math.isfinite(mse) and mse > 0.0:
        denominator = np.square(1.0 - leverage)
        valid = denominator > 0.0
        cooks = np.full(n, np.nan, dtype=float)
        cooks[valid] = (
            np.square(errors[valid]) / (p * mse)
        ) * leverage[valid] / denominator[valid]
    max_cooks = None
    if cooks is not None and np.any(np.isfinite(cooks)):
        max_cooks = float(np.nanmax(cooks))

    jackknife_matrix = np.asarray(jackknife, dtype=float)
    stability: list[CoefficientStabilityDiagnostic] = []
    for column, parameter in enumerate(method.parameters):
        values = jackknife_matrix[:, column]
        full_value = float(coefficients[column])
        full_sign = _sign(full_value)
        ratio = float(np.mean([_sign(float(value)) == full_sign for value in values]))
        stability.append(
            CoefficientStabilityDiagnostic(
                parameter=parameter,
                full_fit_value=full_value,
                leave_one_out_min=float(np.min(values)),
                leave_one_out_max=float(np.max(values)),
                sign_stability_ratio=ratio,
            )
        )

    gate = method.training_gate
    reconciliation = all(item.company_product_revenue_reconciled for item in rows)
    training_gate_passed = all(
        (
            n == gate.required_row_count,
            p == gate.required_parameter_count,
            dof >= gate.required_residual_degrees_of_freedom,
            full_rank if gate.require_full_column_rank else True,
            reconciliation if gate.require_company_product_revenue_reconciliation else True,
            all_fold_rank if gate.require_all_leave_one_out_folds_full_rank else True,
            loocv_mae < benchmark_mae if gate.require_loocv_mae_better_than_benchmark else True,
        )
    )
    stable = {
        "evaluation_date": evaluation_date.isoformat(),
        "method_evidence_id": method.evidence_id,
        "base_rank_probe_evidence_id": base_rank_probe.evidence_id,
        "training_periods": method.training_periods,
        "rows": [asdict(item) for item in rows],
        "coefficients": tuple(float(value) for value in coefficients),
        "loocv": [asdict(item) for item in loocv],
        "training_gate_passed": training_gate_passed,
    }
    return RegimeTrainingFitResult(
        evidence_id=_sha(stable),
        evaluation_date=evaluation_date,
        method_evidence_id=method.evidence_id,
        base_rank_probe_evidence_id=base_rank_probe.evidence_id,
        training_periods=method.training_periods,
        rows=rows,
        row_count=n,
        parameter_count=p,
        residual_degrees_of_freedom=dof,
        design_rank=rank,
        full_column_rank=full_rank,
        normalized_condition_number=condition,
        coefficients=tuple(float(value) for value in coefficients),
        in_sample_mae_krw_million=float(np.mean(np.abs(errors))),
        in_sample_rmse_krw_million=_rmse(errors),
        in_sample_r2=_r2(target, prediction),
        loocv=tuple(loocv),
        all_loocv_folds_full_rank=all_fold_rank,
        loocv_mae_krw_million=loocv_mae,
        benchmark_loocv_mae_krw_million=benchmark_mae,
        loocv_beats_benchmark=loocv_mae < benchmark_mae,
        mean_training_gross_margin=float(np.mean(target / revenue)),
        max_leverage=max_leverage,
        max_cooks_distance=max_cooks,
        coefficient_stability=tuple(stability),
        training_gate_passed=training_gate_passed,
        one_time_holdout_evaluation_ready=training_gate_passed,
    )


__all__ = [
    "CoefficientStabilityDiagnostic",
    "LeaveOneOutDiagnostic",
    "RegimeTrainingFitResult",
    "RegimeTrainingRow",
    "build_regime_training_fit",
]
