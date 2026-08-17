"""Frozen pre-holdout estimation contract for SK hynix product profitability.

The primary estimator deliberately collapses every issuer driver to a categorical direction
regime (+1/0/-1). Exact 2019-2020 numeric magnitudes remain source facts but are not used by
this v1 fit, which keeps the six second-wave rows semantically aligned with the nine legacy
source-text rows. The method is frozen before coefficients, fit metrics, or the 2026Q1
holdout outcome are inspected.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import cast

import yaml

DEFAULT_REGIME_ESTIMATION_METHOD = Path(
    "config/skhynix_product_profitability_regime_estimation_method.v1.yaml"
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
)
_EXPECTED_PARAMETERS = (
    "dram_margin_intercept",
    "dram_asp_direction_regime_effect",
    "dram_bit_volume_direction_regime_effect",
    "nand_margin_intercept",
    "nand_asp_direction_regime_effect",
    "nand_bit_volume_direction_regime_effect",
    "other_margin_constant",
)
_EXPECTED_TERMS = (
    "dram_revenue",
    "dram_revenue_x_dram_asp_direction",
    "dram_revenue_x_dram_bit_volume_direction",
    "nand_revenue",
    "nand_revenue_x_nand_asp_direction",
    "nand_revenue_x_nand_bit_volume_direction",
    "other_revenue",
)


def _mapping(value: object, label: str) -> dict[object, object]:
    if not isinstance(value, dict):
        raise ValueError(f"Regime estimation {label} must be an object")
    return cast(dict[object, object], value)


def _strings(value: object, label: str) -> tuple[str, ...]:
    if not isinstance(value, list):
        raise ValueError(f"Regime estimation {label} must be an array")
    result = tuple(str(item).strip() for item in value)
    if not result or any(not item for item in result):
        raise ValueError(f"Regime estimation {label} cannot contain empty values")
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
class RegimeDriverEncoding:
    encoding_id: str
    semantics: str
    increase_code: float
    flat_code: float
    decrease_code: float
    sign_transform_is_method_assumption: bool
    legacy_text_magnitude_used_for_fit: bool
    exact_numeric_second_wave_magnitude_used_for_fit: bool
    exact_numeric_second_wave_values_preserved_as_source_facts: bool
    estimation_input_ready: bool

    def __post_init__(self) -> None:
        if self.encoding_id != "issuer_direction_regime_sign_v1":
            raise ValueError("Regime estimation encoding id is unsupported")
        if self.semantics != "categorical_direction_regime":
            raise ValueError("Regime estimation encoding semantics drifted")
        if (self.increase_code, self.flat_code, self.decrease_code) != (1.0, 0.0, -1.0):
            raise ValueError("Regime estimation direction codes must remain +1/0/-1")
        if (
            not self.sign_transform_is_method_assumption
            or self.legacy_text_magnitude_used_for_fit
            or self.exact_numeric_second_wave_magnitude_used_for_fit
            or not self.exact_numeric_second_wave_values_preserved_as_source_facts
            or not self.estimation_input_ready
        ):
            raise ValueError("Regime estimation encoding exceeded its frozen semantics")


@dataclass(frozen=True)
class RegimeTrainingGate:
    required_row_count: int
    required_parameter_count: int
    required_residual_degrees_of_freedom: int
    require_full_column_rank: bool
    require_company_product_revenue_reconciliation: bool
    require_all_leave_one_out_folds_full_rank: bool
    benchmark_id: str
    require_loocv_mae_better_than_benchmark: bool
    cooks_distance_report_only: bool
    jackknife_coefficient_stability_report_only: bool

    def __post_init__(self) -> None:
        if (self.required_row_count, self.required_parameter_count) != (15, 7):
            raise ValueError("Regime estimation sample/parameter gate drifted")
        if self.required_residual_degrees_of_freedom != 8:
            raise ValueError("Regime estimation residual-DOF gate drifted")
        required = (
            self.require_full_column_rank,
            self.require_company_product_revenue_reconciliation,
            self.require_all_leave_one_out_folds_full_rank,
            self.require_loocv_mae_better_than_benchmark,
            self.cooks_distance_report_only,
            self.jackknife_coefficient_stability_report_only,
        )
        if not all(required):
            raise ValueError("Regime estimation training gate must remain fail-closed")
        if self.benchmark_id != "leave_one_out_mean_gross_margin_scaled_revenue":
            raise ValueError("Regime estimation benchmark id drifted")


@dataclass(frozen=True)
class FrozenRegimeEstimationMethod:
    evidence_id: str
    method_id: str
    method_version: str
    status: str
    ticker: str
    target_metric: str
    temporal_alignment: str
    training_periods: tuple[str, ...]
    holdout_period: str
    driver_encoding: RegimeDriverEncoding
    estimator_id: str
    include_global_intercept: bool
    rcond: float | None
    parameters: tuple[str, ...]
    equation_terms: tuple[str, ...]
    training_gate: RegimeTrainingGate
    design_rank_seen_before_freeze: bool
    normalized_condition_number_seen_before_freeze: bool
    coefficient_outcomes_seen_before_freeze: bool
    training_fit_metrics_seen_before_freeze: bool
    holdout_outcome_seen_before_freeze: bool
    method_version_frozen: bool
    product_profitability_is_direct_source_fact: bool
    coefficient_estimates_are_model_outputs: bool
    training_fit_can_enable_one_time_holdout_readiness: bool
    holdout_evaluation_enabled_by_manifest: bool
    numeric_forecast_enabled: bool
    fair_value_estimate_enabled: bool
    target_price_enabled: bool
    decision_score_enabled: bool

    def __post_init__(self) -> None:
        if self.method_id != "skhynix_product_profitability_regime_ols":
            raise ValueError("Regime estimation method id is unsupported")
        if self.method_version != "1.0-frozen-pre-holdout":
            raise ValueError("Regime estimation method version drifted")
        if self.status != "frozen_training_estimation" or self.ticker != "000660":
            raise ValueError("Regime estimation method identity drifted")
        if self.target_metric != "company_gross_profit_krw_million":
            raise ValueError("Regime estimation target metric drifted")
        if self.temporal_alignment != "contemporaneous_same_quarter":
            raise ValueError("Regime estimation temporal alignment drifted")
        if self.training_periods != _EXPECTED_TRAINING_PERIODS:
            raise ValueError("Regime estimation training periods drifted")
        if self.holdout_period != "2026Q1":
            raise ValueError("Regime estimation holdout drifted")
        if self.estimator_id != "ordinary_least_squares_numpy_lstsq":
            raise ValueError("Regime estimation estimator drifted")
        if self.include_global_intercept or self.rcond is not None:
            raise ValueError("Regime estimation OLS intercept/rcond contract drifted")
        if self.parameters != _EXPECTED_PARAMETERS or self.equation_terms != _EXPECTED_TERMS:
            raise ValueError("Regime estimation parameter/equation order drifted")
        if not self.design_rank_seen_before_freeze:
            raise ValueError("Regime estimation freeze provenance must disclose rank exposure")
        if not self.normalized_condition_number_seen_before_freeze:
            raise ValueError("Regime estimation freeze provenance must disclose condition exposure")
        forbidden_pre_freeze = (
            self.coefficient_outcomes_seen_before_freeze,
            self.training_fit_metrics_seen_before_freeze,
            self.holdout_outcome_seen_before_freeze,
        )
        if any(forbidden_pre_freeze) or not self.method_version_frozen:
            raise ValueError("Regime estimation was not frozen before outcome inspection")
        if self.product_profitability_is_direct_source_fact:
            raise ValueError("Regime coefficient outputs cannot become direct source facts")
        if not self.coefficient_estimates_are_model_outputs:
            raise ValueError("Regime coefficients must remain model outputs")
        if not self.training_fit_can_enable_one_time_holdout_readiness:
            raise ValueError("Regime training gate must control one-time holdout readiness")
        if self.holdout_evaluation_enabled_by_manifest:
            raise ValueError("Frozen v1 manifest cannot directly open the holdout")
        if any(
            (
                self.numeric_forecast_enabled,
                self.fair_value_estimate_enabled,
                self.target_price_enabled,
                self.decision_score_enabled,
            )
        ):
            raise ValueError("Regime estimation method opened downstream decision outputs")
        if len(self.evidence_id) != 64:
            raise ValueError("Regime estimation method evidence id must be SHA-256")

    @property
    def parameter_count(self) -> int:
        return len(self.parameters)


def load_frozen_regime_estimation_method(
    path: str | Path = DEFAULT_REGIME_ESTIMATION_METHOD,
) -> FrozenRegimeEstimationMethod:
    with Path(path).open(encoding="utf-8") as handle:
        raw: object = yaml.safe_load(handle)
    root = _mapping(raw, "manifest")
    if root.get("schema_version") != 1:
        raise ValueError("Regime estimation manifest schema is invalid")
    method = _mapping(root.get("method"), "method")
    encoding = _mapping(method.get("driver_encoding"), "driver_encoding")
    estimator = _mapping(method.get("estimator"), "estimator")
    gate = _mapping(method.get("training_gate"), "training_gate")
    freeze = _mapping(method.get("freeze_provenance"), "freeze_provenance")
    trust = _mapping(method.get("trust_boundary"), "trust_boundary")
    rcond_raw = estimator.get("rcond")
    return FrozenRegimeEstimationMethod(
        evidence_id=_sha(root),
        method_id=str(method.get("method_id", "")),
        method_version=str(method.get("method_version", "")),
        status=str(method.get("status", "")),
        ticker=str(method.get("ticker", "")).zfill(6),
        target_metric=str(method.get("target_metric", "")),
        temporal_alignment=str(method.get("temporal_alignment", "")),
        training_periods=_strings(method.get("training_periods"), "training_periods"),
        holdout_period=str(method.get("holdout_period", "")),
        driver_encoding=RegimeDriverEncoding(
            encoding_id=str(encoding.get("encoding_id", "")),
            semantics=str(encoding.get("semantics", "")),
            increase_code=float(str(encoding.get("increase_code", "nan"))),
            flat_code=float(str(encoding.get("flat_code", "nan"))),
            decrease_code=float(str(encoding.get("decrease_code", "nan"))),
            sign_transform_is_method_assumption=(
                encoding.get("sign_transform_is_method_assumption") is True
            ),
            legacy_text_magnitude_used_for_fit=(
                encoding.get("legacy_text_magnitude_used_for_fit") is True
            ),
            exact_numeric_second_wave_magnitude_used_for_fit=(
                encoding.get("exact_numeric_second_wave_magnitude_used_for_fit") is True
            ),
            exact_numeric_second_wave_values_preserved_as_source_facts=(
                encoding.get("exact_numeric_second_wave_values_preserved_as_source_facts") is True
            ),
            estimation_input_ready=encoding.get("estimation_input_ready") is True,
        ),
        estimator_id=str(estimator.get("estimator_id", "")),
        include_global_intercept=estimator.get("include_global_intercept") is True,
        rcond=None if rcond_raw is None else float(str(rcond_raw)),
        parameters=_strings(estimator.get("parameters"), "parameters"),
        equation_terms=_strings(estimator.get("equation_terms"), "equation_terms"),
        training_gate=RegimeTrainingGate(
            required_row_count=int(str(gate.get("required_row_count", 0))),
            required_parameter_count=int(str(gate.get("required_parameter_count", 0))),
            required_residual_degrees_of_freedom=int(
                str(gate.get("required_residual_degrees_of_freedom", 0))
            ),
            require_full_column_rank=gate.get("require_full_column_rank") is True,
            require_company_product_revenue_reconciliation=(
                gate.get("require_company_product_revenue_reconciliation") is True
            ),
            require_all_leave_one_out_folds_full_rank=(
                gate.get("require_all_leave_one_out_folds_full_rank") is True
            ),
            benchmark_id=str(gate.get("benchmark_id", "")),
            require_loocv_mae_better_than_benchmark=(
                gate.get("require_loocv_mae_better_than_benchmark") is True
            ),
            cooks_distance_report_only=gate.get("cooks_distance_report_only") is True,
            jackknife_coefficient_stability_report_only=(
                gate.get("jackknife_coefficient_stability_report_only") is True
            ),
        ),
        design_rank_seen_before_freeze=freeze.get("design_rank_seen_before_freeze") is True,
        normalized_condition_number_seen_before_freeze=(
            freeze.get("normalized_condition_number_seen_before_freeze") is True
        ),
        coefficient_outcomes_seen_before_freeze=(
            freeze.get("coefficient_outcomes_seen_before_freeze") is True
        ),
        training_fit_metrics_seen_before_freeze=(
            freeze.get("training_fit_metrics_seen_before_freeze") is True
        ),
        holdout_outcome_seen_before_freeze=freeze.get("holdout_outcome_seen_before_freeze") is True,
        method_version_frozen=freeze.get("method_version_frozen") is True,
        product_profitability_is_direct_source_fact=(
            trust.get("product_profitability_is_direct_source_fact") is True
        ),
        coefficient_estimates_are_model_outputs=(
            trust.get("coefficient_estimates_are_model_outputs") is True
        ),
        training_fit_can_enable_one_time_holdout_readiness=(
            trust.get("training_fit_can_enable_one_time_holdout_readiness") is True
        ),
        holdout_evaluation_enabled_by_manifest=(
            trust.get("holdout_evaluation_enabled_by_manifest") is True
        ),
        numeric_forecast_enabled=trust.get("numeric_forecast_enabled") is True,
        fair_value_estimate_enabled=trust.get("fair_value_estimate_enabled") is True,
        target_price_enabled=trust.get("target_price_enabled") is True,
        decision_score_enabled=trust.get("decision_score_enabled") is True,
    )


__all__ = [
    "DEFAULT_REGIME_ESTIMATION_METHOD",
    "FrozenRegimeEstimationMethod",
    "RegimeDriverEncoding",
    "RegimeTrainingGate",
    "load_frozen_regime_estimation_method",
]
