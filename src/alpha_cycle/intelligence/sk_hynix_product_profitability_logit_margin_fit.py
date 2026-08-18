"""Fit the frozen SK hynix v2 bounded product-margin model.

The fitter consumes the persisted v1 15-row training artifact plus the already-spent 2026Q1
holdout as explicitly contaminated development data. It never loads or evaluates 2026Q3.
"""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import asdict, dataclass
from datetime import date
from pathlib import Path
from typing import cast

import numpy as np

from alpha_cycle.intelligence.sec_product_cycle_driver_support import (
    DEFAULT_SEC_PRODUCT_CYCLE_DRIVER_POINTER,
)
from alpha_cycle.intelligence.sec_product_cycle_driver_support_verifier import (
    load_sec_product_cycle_driver_support_evidence,
)
from alpha_cycle.intelligence.sk_hynix_opendart_historical_product_revenue_panel import (
    DEFAULT_HISTORICAL_PRODUCT_REVENUE_POINTER,
)
from alpha_cycle.intelligence.sk_hynix_opendart_historical_product_revenue_panel_verifier import (
    load_historical_product_revenue_panel_evidence,
)
from alpha_cycle.intelligence.sk_hynix_opendart_quarterly_company_profitability import (
    DEFAULT_QUARTERLY_COMPANY_PROFITABILITY_POINTER,
)
from alpha_cycle.intelligence.sk_hynix_opendart_quarterly_company_profitability_verifier import (
    load_quarterly_company_profitability_evidence,
)
from alpha_cycle.intelligence.sk_hynix_product_profitability_logit_margin_method import (
    FrozenLogitMarginMethod,
)
from alpha_cycle.intelligence.sk_hynix_product_profitability_regime_economic_audit import (
    DEFAULT_REGIME_TRAINING_FIT_POINTER,
)
from alpha_cycle.intelligence.sk_hynix_product_profitability_regime_holdout import (
    DEFAULT_REGIME_HOLDOUT_POINTER,
)
from alpha_cycle.intelligence.sk_hynix_product_profitability_structural_method import (
    encode_direction_sign,
    load_product_certifications_for_historical_panel,
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


def _object(path: Path, label: str) -> dict[str, object]:
    try:
        raw: object = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ValueError(f"{label} not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"{label} is invalid JSON: {path}") from exc
    if not isinstance(raw, dict):
        raise ValueError(f"{label} must be an object")
    return {str(k): v for k, v in cast(dict[object, object], raw).items()}


def _mapping(value: object, label: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be an object")
    return {str(k): v for k, v in cast(dict[object, object], value).items()}


def _number(payload: dict[str, object], key: str) -> float:
    return float(str(payload.get(key, "nan")))


def _sigmoid(value: np.ndarray | float) -> np.ndarray | float:
    clipped = np.clip(value, -60.0, 60.0)
    result = 1.0 / (1.0 + np.exp(-clipped))
    if isinstance(value, np.ndarray):
        return result
    return float(result)


@dataclass(frozen=True)
class LogitMarginTrainingRow:
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
            "v1_training_reuse",
            "spent_v1_holdout_development",
        }:
            raise ValueError("Logit-margin training source group is invalid")
        if self.company_revenue_krw_million <= 0.0:
            raise ValueError("Logit-margin company revenue must be positive")
        if min(
            self.dram_revenue_krw_million,
            self.nand_revenue_krw_million,
            self.other_revenue_krw_million,
        ) < 0.0:
            raise ValueError("Logit-margin product revenue cannot be negative")
        codes = (
            self.dram_asp_direction_code,
            self.dram_bit_volume_direction_code,
            self.nand_asp_direction_code,
            self.nand_bit_volume_direction_code,
        )
        if any(value not in {-1.0, 0.0, 1.0} for value in codes):
            raise ValueError("Logit-margin direction code is invalid")


@dataclass(frozen=True)
class SolverResult:
    parameters: tuple[float, ...]
    converged: bool
    iterations: int
    rejected_steps: int
    final_sse_scaled: float
    jacobian_rank: int
    normalized_jacobian_condition_number: float | None


@dataclass(frozen=True)
class LogitMarginLeaveOneOut:
    held_out_period: str
    converged: bool
    jacobian_rank: int
    model_prediction_krw_million: float
    actual_krw_million: float
    model_absolute_error_krw_million: float
    benchmark_prediction_krw_million: float
    benchmark_absolute_error_krw_million: float


@dataclass(frozen=True)
class ProductMarginEnvelope:
    product: str
    minimum_margin: float
    maximum_margin: float
    all_regimes_inside_unit_interval: bool


@dataclass(frozen=True)
class LogitMarginFitResult:
    evidence_id: str
    evaluation_date: date
    method_evidence_id: str
    training_periods: tuple[str, ...]
    contaminated_development_periods: tuple[str, ...]
    untouched_holdout_period: str
    rows: tuple[LogitMarginTrainingRow, ...]
    row_count: int
    parameter_count: int
    residual_degrees_of_freedom: int
    parameters: tuple[float, ...]
    optimizer_converged: bool
    optimizer_iterations: int
    jacobian_rank: int
    full_jacobian_column_rank: bool
    normalized_jacobian_condition_number: float | None
    in_sample_mae_krw_million: float
    in_sample_rmse_krw_million: float
    loocv: tuple[LogitMarginLeaveOneOut, ...]
    all_loocv_folds_converged: bool
    all_loocv_jacobians_full_rank: bool
    loocv_mae_krw_million: float
    benchmark_loocv_mae_krw_million: float
    loocv_beats_benchmark: bool
    dram_margin_envelope: ProductMarginEnvelope
    nand_margin_envelope: ProductMarginEnvelope
    other_margin: float
    all_component_margins_inside_unit_interval: bool
    development_gate_passed: bool
    future_holdout_evaluation_allowed: bool = False
    q1_claimed_as_independent_holdout: bool = False
    q2_claimed_as_untouched_holdout: bool = False
    numeric_forward_forecast_enabled: bool = False
    target_price_enabled: bool = False
    decision_score_enabled: bool = False

    def __post_init__(self) -> None:
        if len(self.evidence_id) != 64 or len(self.method_evidence_id) != 64:
            raise ValueError("Logit-margin fit evidence ids must be SHA-256")
        if self.row_count != len(self.rows) or self.row_count != len(self.training_periods):
            raise ValueError("Logit-margin fit row counts are inconsistent")
        if self.parameter_count != len(self.parameters):
            raise ValueError("Logit-margin fit parameter count is inconsistent")
        if self.residual_degrees_of_freedom != self.row_count - self.parameter_count:
            raise ValueError("Logit-margin residual DOF is inconsistent")
        if self.full_jacobian_column_rank != (self.jacobian_rank == self.parameter_count):
            raise ValueError("Logit-margin rank flag is inconsistent")
        if self.loocv_beats_benchmark != (
            self.loocv_mae_krw_million < self.benchmark_loocv_mae_krw_million
        ):
            raise ValueError("Logit-margin benchmark flag is inconsistent")
        if self.all_component_margins_inside_unit_interval != all(
            (
                self.dram_margin_envelope.all_regimes_inside_unit_interval,
                self.nand_margin_envelope.all_regimes_inside_unit_interval,
                0.0 < self.other_margin < 1.0,
            )
        ):
            raise ValueError("Logit-margin component-bound flag is inconsistent")
        if (
            self.future_holdout_evaluation_allowed
            or self.q1_claimed_as_independent_holdout
            or self.q2_claimed_as_untouched_holdout
            or self.numeric_forward_forecast_enabled
            or self.target_price_enabled
            or self.decision_score_enabled
        ):
            raise ValueError("Logit-margin fit exceeded its development trust boundary")


def _parse_v1_rows(wrapper: dict[str, object]) -> tuple[LogitMarginTrainingRow, ...]:
    raw_result = _mapping(wrapper.get("result"), "v1 training result")
    raw_rows = raw_result.get("rows")
    if not isinstance(raw_rows, list):
        raise ValueError("v1 training result rows must be an array")
    rows: list[LogitMarginTrainingRow] = []
    for raw in raw_rows:
        item = _mapping(raw, "v1 training row")
        rows.append(
            LogitMarginTrainingRow(
                period_id=str(item.get("period_id", "")),
                source_group="v1_training_reuse",
                company_revenue_krw_million=_number(item, "company_revenue_krw_million"),
                company_gross_profit_krw_million=_number(
                    item, "company_gross_profit_krw_million"
                ),
                dram_revenue_krw_million=_number(item, "dram_revenue_krw_million"),
                nand_revenue_krw_million=_number(item, "nand_revenue_krw_million"),
                other_revenue_krw_million=_number(item, "other_revenue_krw_million"),
                dram_asp_direction_code=_number(item, "dram_asp_direction_code"),
                dram_bit_volume_direction_code=_number(
                    item, "dram_bit_volume_direction_code"
                ),
                nand_asp_direction_code=_number(item, "nand_asp_direction_code"),
                nand_bit_volume_direction_code=_number(
                    item, "nand_bit_volume_direction_code"
                ),
            )
        )
    return tuple(rows)


def _spent_q1_row(
    holdout_wrapper: dict[str, object],
    *,
    historical_product_revenue_pointer: str | Path,
    company_profitability_pointer: str | Path,
    cycle_driver_pointer: str | Path,
) -> LogitMarginTrainingRow:
    holdout = _mapping(holdout_wrapper.get("result"), "v1 holdout result")
    if holdout.get("holdout_spent") is not True or holdout.get("immutable_result") is not True:
        raise ValueError("Logit-margin v2 requires the immutable spent v1 holdout")
    if str(holdout.get("holdout_period", "")) != "2026Q1":
        raise ValueError("Logit-margin contaminated development period drifted")
    source_date = date.fromisoformat(str(holdout.get("source_evaluation_date", "")))
    historical = load_historical_product_revenue_panel_evidence(
        historical_product_revenue_pointer,
        evaluation_date=source_date,
    )
    products = load_product_certifications_for_historical_panel(
        historical,
        evaluation_date=source_date,
    )
    company = load_quarterly_company_profitability_evidence(
        company_profitability_pointer,
        evaluation_date=source_date,
    )
    cycle = load_sec_product_cycle_driver_support_evidence(
        cycle_driver_pointer,
        evaluation_date=source_date,
    )
    product = products.get("2026Q1")
    company_row = {item.period_id: item for item in company.observations}.get("2026Q1")
    cycle_row = {item.period_id: item for item in cycle.observations}.get("2026Q1")
    if product is None or company_row is None or cycle_row is None:
        raise ValueError("Logit-margin Q1 development source layers are incomplete")
    if product.evidence_id != str(holdout.get("product_revenue_evidence_id", "")):
        raise ValueError("Logit-margin Q1 product evidence binding diverged")
    if company.evidence_id != str(holdout.get("company_profitability_evidence_id", "")):
        raise ValueError("Logit-margin Q1 company evidence binding diverged")
    if cycle.evidence_id != str(holdout.get("cycle_driver_evidence_id", "")):
        raise ValueError("Logit-margin Q1 cycle evidence binding diverged")
    if company_row.gross_profit_krw / 1_000_000.0 != _number(
        holdout, "actual_gross_profit_krw_million"
    ):
        raise ValueError("Logit-margin Q1 gross-profit binding diverged")
    product_total = float(product.metrics.reported_company_revenue)
    if abs(product_total - company_row.revenue_krw / 1_000_000.0) > 1.0:
        raise ValueError("Logit-margin Q1 company/product revenue reconciliation failed")
    return LogitMarginTrainingRow(
        period_id="2026Q1",
        source_group="spent_v1_holdout_development",
        company_revenue_krw_million=company_row.revenue_krw / 1_000_000.0,
        company_gross_profit_krw_million=company_row.gross_profit_krw / 1_000_000.0,
        dram_revenue_krw_million=float(product.metrics.dram_total),
        nand_revenue_krw_million=float(product.metrics.nand_and_solutions),
        other_revenue_krw_million=float(product.metrics.other_products_services),
        dram_asp_direction_code=encode_direction_sign(cycle_row.dram_asp_usd_qoq_text).code,
        dram_bit_volume_direction_code=encode_direction_sign(
            cycle_row.dram_bit_sales_volume_qoq_text
        ).code,
        nand_asp_direction_code=encode_direction_sign(cycle_row.nand_asp_usd_qoq_text).code,
        nand_bit_volume_direction_code=encode_direction_sign(
            cycle_row.nand_bit_sales_volume_qoq_text
        ).code,
    )


def load_logit_margin_training_rows(
    method: FrozenLogitMarginMethod,
    *,
    v1_training_pointer: str | Path = DEFAULT_REGIME_TRAINING_FIT_POINTER,
    v1_holdout_pointer: str | Path = DEFAULT_REGIME_HOLDOUT_POINTER,
    historical_product_revenue_pointer: str | Path = DEFAULT_HISTORICAL_PRODUCT_REVENUE_POINTER,
    company_profitability_pointer: str | Path = DEFAULT_QUARTERLY_COMPANY_PROFITABILITY_POINTER,
    cycle_driver_pointer: str | Path = DEFAULT_SEC_PRODUCT_CYCLE_DRIVER_POINTER,
) -> tuple[LogitMarginTrainingRow, ...]:
    training = _object(Path(v1_training_pointer), "v1 training pointer")
    holdout = _object(Path(v1_holdout_pointer), "v1 holdout pointer")
    base = _parse_v1_rows(training)
    if tuple(item.period_id for item in base) != method.training_periods[:-1]:
        raise ValueError("Logit-margin v1 training periods diverged from frozen v2 method")
    q1 = _spent_q1_row(
        holdout,
        historical_product_revenue_pointer=historical_product_revenue_pointer,
        company_profitability_pointer=company_profitability_pointer,
        cycle_driver_pointer=cycle_driver_pointer,
    )
    rows = base + (q1,)
    if tuple(item.period_id for item in rows) != method.training_periods:
        raise ValueError("Logit-margin full training period order diverged")
    return rows


def _arrays(rows: tuple[LogitMarginTrainingRow, ...]) -> tuple[np.ndarray, ...]:
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


def _predict_jacobian(
    theta: np.ndarray,
    rows: tuple[LogitMarginTrainingRow, ...],
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
    rows: tuple[LogitMarginTrainingRow, ...],
    method: FrozenLogitMarginMethod,
) -> np.ndarray:
    revenue, target, *_rest = _arrays(rows)
    probability = float(np.mean(target / revenue))
    probability = min(
        method.solver.maximum_initialization_probability,
        max(method.solver.minimum_initialization_probability, probability),
    )
    logit = math.log(probability / (1.0 - probability))
    return np.asarray([logit, 0.0, 0.0, logit, 0.0, 0.0, logit], dtype=float)


def _condition(jac: np.ndarray) -> float | None:
    norms = np.linalg.norm(jac, axis=0)
    if np.any(norms == 0.0):
        return None
    value = float(np.linalg.cond(jac / norms))
    return value if math.isfinite(value) else None


def _solve(
    rows: tuple[LogitMarginTrainingRow, ...],
    method: FrozenLogitMarginMethod,
) -> SolverResult:
    revenue, target, *_rest = _arrays(rows)
    scale = float(np.mean(revenue))
    if not math.isfinite(scale) or scale <= 0.0:
        raise ValueError("Logit-margin optimization scale is invalid")
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
    return SolverResult(
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
    rows: tuple[LogitMarginTrainingRow, ...],
) -> np.ndarray:
    revenue, _target, *_rest = _arrays(rows)
    scale = float(np.mean(revenue))
    prediction, _jac = _predict_jacobian(np.asarray(parameters, dtype=float), rows, scale)
    return prediction * scale


def _envelope(product: str, intercept: float, asp: float, bit: float) -> ProductMarginEnvelope:
    values = tuple(
        float(_sigmoid(intercept + asp * asp_code + bit * bit_code))
        for asp_code in (-1.0, 0.0, 1.0)
        for bit_code in (-1.0, 0.0, 1.0)
    )
    return ProductMarginEnvelope(
        product=product,
        minimum_margin=min(values),
        maximum_margin=max(values),
        all_regimes_inside_unit_interval=all(0.0 < value < 1.0 for value in values),
    )


def build_logit_margin_fit(
    method: FrozenLogitMarginMethod,
    rows: tuple[LogitMarginTrainingRow, ...],
    *,
    evaluation_date: date,
) -> LogitMarginFitResult:
    if tuple(item.period_id for item in rows) != method.training_periods:
        raise ValueError("Logit-margin fit rows diverged from frozen training periods")
    full = _solve(rows, method)
    prediction = _prediction_original(full.parameters, rows)
    revenue, target, *_rest = _arrays(rows)
    errors = target - prediction
    loocv: list[LogitMarginLeaveOneOut] = []
    for index, row in enumerate(rows):
        fold_rows = tuple(item for idx, item in enumerate(rows) if idx != index)
        fold = _solve(fold_rows, method)
        held = (row,)
        model_prediction = float(_prediction_original(fold.parameters, held)[0])
        train_revenue, train_target, *_fold_rest = _arrays(fold_rows)
        benchmark_margin = float(np.mean(train_target / train_revenue))
        benchmark_prediction = benchmark_margin * row.company_revenue_krw_million
        loocv.append(
            LogitMarginLeaveOneOut(
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
            full_rank if gate.require_full_jacobian_column_rank else True,
            full.converged if gate.require_optimizer_convergence else True,
            all_fold_converged if gate.require_all_leave_one_out_folds_converged else True,
            all_fold_rank if gate.require_all_leave_one_out_jacobians_full_rank else True,
            loocv_mae < benchmark_mae if gate.require_loocv_mae_better_than_benchmark else True,
            all_bounds if gate.require_all_component_margins_inside_unit_interval else True,
        )
    )
    stable = {
        "evaluation_date": evaluation_date.isoformat(),
        "method_evidence_id": method.evidence_id,
        "training_periods": method.training_periods,
        "contaminated_development_periods": method.contaminated_development_periods,
        "untouched_holdout_period": method.untouched_holdout_period,
        "rows": [asdict(item) for item in rows],
        "parameters": full.parameters,
        "optimizer_converged": full.converged,
        "loocv": [asdict(item) for item in loocv],
        "development_gate_passed": development_gate,
    }
    return LogitMarginFitResult(
        evidence_id=_sha(stable),
        evaluation_date=evaluation_date,
        method_evidence_id=method.evidence_id,
        training_periods=method.training_periods,
        contaminated_development_periods=method.contaminated_development_periods,
        untouched_holdout_period=method.untouched_holdout_period,
        rows=rows,
        row_count=n,
        parameter_count=p,
        residual_degrees_of_freedom=dof,
        parameters=full.parameters,
        optimizer_converged=full.converged,
        optimizer_iterations=full.iterations,
        jacobian_rank=full.jacobian_rank,
        full_jacobian_column_rank=full_rank,
        normalized_jacobian_condition_number=full.normalized_jacobian_condition_number,
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
        development_gate_passed=development_gate,
    )


__all__ = [
    "LogitMarginFitResult",
    "LogitMarginLeaveOneOut",
    "LogitMarginTrainingRow",
    "ProductMarginEnvelope",
    "SolverResult",
    "build_logit_margin_fit",
    "load_logit_margin_training_rows",
]
