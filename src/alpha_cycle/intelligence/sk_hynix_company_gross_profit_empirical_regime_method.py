from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

import yaml

DEFAULT_COMPANY_GP_EMPIRICAL_METHOD = Path(
    "config/skhynix_company_gross_profit_empirical_regime_method.v5.yaml"
)


@dataclass(frozen=True)
class EmpiricalPrefitGate:
    required_row_count: int
    required_parameter_count: int
    required_residual_degrees_of_freedom: int
    require_full_design_column_rank: bool
    require_all_leave_one_out_designs_full_rank: bool


@dataclass(frozen=True)
class EmpiricalDevelopmentGate:
    require_full_fit_design_rank: bool
    require_all_leave_one_out_fit_designs_full_rank: bool
    require_loocv_mae_better_than_benchmark: bool
    benchmark: str


@dataclass(frozen=True)
class FrozenCompanyGPEmpiricalMethod:
    evidence_id: str
    method_id: str
    method_version: str
    status: str
    ticker: str
    target_metric: str
    training_periods: tuple[str, ...]
    contaminated_stress_periods: tuple[str, ...]
    untouched_future_holdout_period: str
    parameter_count: int
    parameters: tuple[str, ...]
    design_terms: tuple[str, ...]
    estimator_family: str
    prefit_gate: EmpiricalPrefitGate
    development_gate: EmpiricalDevelopmentGate
    coefficients_are_empirical_company_gp_weights: bool
    coefficients_are_literal_product_margins: bool
    product_margin_structural_interpretation_allowed: bool
    v4_outcome_seen_before_freeze: bool
    v5_coefficients_seen_before_freeze: bool
    v5_fit_metrics_seen_before_freeze: bool
    numeric_forward_forecast_enabled: bool
    target_price_enabled: bool
    decision_score_enabled: bool
    product_margin_output_enabled: bool

    def __post_init__(self) -> None:
        if len(self.evidence_id) != 64:
            raise ValueError("V5 method evidence id must be SHA-256")
        if self.method_version != "5.0-frozen-pre-fit" or self.status != "frozen_pre_fit":
            raise ValueError("V5 company-GP method is not frozen pre-fit")
        if self.ticker != "000660":
            raise ValueError("V5 company-GP ticker drifted")
        if self.target_metric != "company_gross_profit_krw_million":
            raise ValueError("V5 company-GP target drifted")
        if self.parameter_count != 7 or len(self.parameters) != 7 or len(self.design_terms) != 7:
            raise ValueError("V5 company-GP parameter contract drifted")
        if len(self.training_periods) != 21 or self.contaminated_stress_periods != ("2026Q1",):
            raise ValueError("V5 company-GP panel contract drifted")
        if self.untouched_future_holdout_period != "2026Q3":
            raise ValueError("V5 future holdout drifted")
        if self.estimator_family != "ordinary_least_squares":
            raise ValueError("V5 estimator family drifted")
        if not self.coefficients_are_empirical_company_gp_weights:
            raise ValueError("V5 coefficient scope must remain empirical")
        if self.coefficients_are_literal_product_margins:
            raise ValueError("V5 cannot label coefficients as literal product margins")
        if self.product_margin_structural_interpretation_allowed:
            raise ValueError("V5 structural product-margin interpretation must remain disabled")
        if not self.v4_outcome_seen_before_freeze:
            raise ValueError("V5 freeze provenance must disclose observed V4 outcome")
        if self.v5_coefficients_seen_before_freeze or self.v5_fit_metrics_seen_before_freeze:
            raise ValueError("V5 pre-fit freeze provenance is invalid")
        if any(
            (
                self.numeric_forward_forecast_enabled,
                self.target_price_enabled,
                self.decision_score_enabled,
                self.product_margin_output_enabled,
            )
        ):
            raise ValueError("V5 method exceeded development trust boundary")


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


def load_frozen_company_gp_empirical_method(
    path: str | Path = DEFAULT_COMPANY_GP_EMPIRICAL_METHOD,
) -> FrozenCompanyGPEmpiricalMethod:
    source = Path(path)
    payload = yaml.safe_load(source.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or payload.get("schema_version") != 1:
        raise ValueError("V5 company-GP method schema is invalid")
    method = payload.get("method")
    if not isinstance(method, dict):
        raise ValueError("V5 company-GP method body is invalid")
    prefit = method["prefit_identification_gate"]
    gate = method["development_gate"]
    semantics = method["semantics"]
    transition = method["scientific_transition"]
    trust = method["trust_boundary"]
    stable = {"schema_version": payload["schema_version"], "method": method}
    return FrozenCompanyGPEmpiricalMethod(
        evidence_id=_sha(stable),
        method_id=str(method["method_id"]),
        method_version=str(method["method_version"]),
        status=str(method["status"]),
        ticker=str(method["ticker"]),
        target_metric=str(method["target_metric"]),
        training_periods=tuple(str(value) for value in method["training_periods"]),
        contaminated_stress_periods=tuple(
            str(value) for value in method["contaminated_stress_periods"]
        ),
        untouched_future_holdout_period=str(method["untouched_future_holdout_period"]),
        parameter_count=int(method["parameter_count"]),
        parameters=tuple(str(value) for value in method["parameters"]),
        design_terms=tuple(str(value) for value in method["design_terms"]),
        estimator_family=str(method["estimator"]["family"]),
        prefit_gate=EmpiricalPrefitGate(
            required_row_count=int(prefit["required_row_count"]),
            required_parameter_count=int(prefit["required_parameter_count"]),
            required_residual_degrees_of_freedom=int(
                prefit["required_residual_degrees_of_freedom"]
            ),
            require_full_design_column_rank=bool(prefit["require_full_design_column_rank"]),
            require_all_leave_one_out_designs_full_rank=bool(
                prefit["require_all_leave_one_out_designs_full_rank"]
            ),
        ),
        development_gate=EmpiricalDevelopmentGate(
            require_full_fit_design_rank=bool(gate["require_full_fit_design_rank"]),
            require_all_leave_one_out_fit_designs_full_rank=bool(
                gate["require_all_leave_one_out_fit_designs_full_rank"]
            ),
            require_loocv_mae_better_than_benchmark=bool(
                gate["require_loocv_mae_better_than_benchmark"]
            ),
            benchmark=str(gate["benchmark"]),
        ),
        coefficients_are_empirical_company_gp_weights=bool(
            semantics["coefficients_are_empirical_company_gp_weights"]
        ),
        coefficients_are_literal_product_margins=bool(
            semantics["coefficients_are_literal_product_margins"]
        ),
        product_margin_structural_interpretation_allowed=bool(
            semantics["product_margin_structural_interpretation_allowed"]
        ),
        v4_outcome_seen_before_freeze=bool(transition["v4_outcome_seen_before_freeze"]),
        v5_coefficients_seen_before_freeze=bool(
            transition["v5_coefficients_seen_before_freeze"]
        ),
        v5_fit_metrics_seen_before_freeze=bool(transition["v5_fit_metrics_seen_before_freeze"]),
        numeric_forward_forecast_enabled=bool(trust["numeric_forward_forecast_enabled"]),
        target_price_enabled=bool(trust["target_price_enabled"]),
        decision_score_enabled=bool(trust["decision_score_enabled"]),
        product_margin_output_enabled=bool(trust["product_margin_output_enabled"]),
    )


__all__ = [
    "DEFAULT_COMPANY_GP_EMPIRICAL_METHOD",
    "EmpiricalDevelopmentGate",
    "EmpiricalPrefitGate",
    "FrozenCompanyGPEmpiricalMethod",
    "load_frozen_company_gp_empirical_method",
]
