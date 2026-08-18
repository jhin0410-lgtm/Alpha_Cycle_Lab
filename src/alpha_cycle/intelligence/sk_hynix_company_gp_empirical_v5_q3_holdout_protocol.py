"""Load and validate the frozen SK hynix V5 2026Q3 prospective holdout protocol."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from dateutil.parser import isoparse
from datetime import date
from pathlib import Path
from typing import cast

import yaml

from alpha_cycle.intelligence.sk_hynix_company_gross_profit_empirical_regime_method import (
    DEFAULT_COMPANY_GP_EMPIRICAL_METHOD,
    FrozenCompanyGPEmpiricalMethod,
    load_frozen_company_gp_empirical_method,
)

DEFAULT_V5_Q3_HOLDOUT_PROTOCOL = Path(
    "config/skhynix_company_gp_empirical_v5_q3_holdout_protocol.v1.yaml"
)


def _mapping(value: object, label: str) -> dict[object, object]:
    if not isinstance(value, dict):
        raise ValueError(f"V5 Q3 holdout {label} must be an object")
    return cast(dict[object, object], value)


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
class FrozenV5Q3HoldoutProtocol:
    evidence_id: str
    protocol_id: str
    protocol_version: str
    status: str
    bound_method_id: str
    bound_method_version: str
    bound_method_evidence_id: str
    bound_fit_evaluation_date: date
    holdout_period: str
    parameter_count: int
    benchmark_id: str
    company_revenue_reconciliation_tolerance_krw: int
    require_model_absolute_error_better_than_benchmark: bool
    conditional_one_time_evaluation_pre_authorized: bool
    require_bound_v5_development_gate_passed: bool
    require_immutable_result_reuse: bool
    refit_before_holdout_allowed: bool
    refit_after_holdout_allowed: bool
    readiness_checker_must_not_load_holdout: bool
    scorer_requires_explicit_source_bundle: bool
    validates_pre_earnings_forecastability: bool
    product_margin_structural_interpretation_allowed: bool
    numeric_forward_forecast_enabled: bool
    fair_value_estimate_enabled: bool
    target_price_enabled: bool
    decision_score_enabled: bool
    investment_action_enabled: bool

    def __post_init__(self) -> None:
        if len(self.evidence_id) != 64 or len(self.bound_method_evidence_id) != 64:
            raise ValueError("V5 Q3 holdout evidence ids must be SHA-256")
        if self.protocol_id != "skhynix_company_gp_empirical_v5_q3_prospective_holdout":
            raise ValueError("V5 Q3 holdout protocol id drifted")
        if self.protocol_version != "1.0-frozen-pre-outcome" or self.status != "frozen_pre_outcome":
            raise ValueError("V5 Q3 holdout protocol is not frozen pre-outcome")
        if self.bound_method_id != "skhynix_company_gross_profit_empirical_regime_ols":
            raise ValueError("V5 Q3 holdout method id drifted")
        if self.bound_method_version != "5.0-frozen-pre-fit":
            raise ValueError("V5 Q3 holdout method version drifted")
        if self.bound_fit_evaluation_date != date(2026, 8, 18):
            raise ValueError("V5 Q3 holdout fit-evaluation binding drifted")
        if self.holdout_period != "2026Q3" or self.parameter_count != 7:
            raise ValueError("V5 Q3 holdout period or parameter count drifted")
        if self.benchmark_id != "training_mean_company_gross_margin_scaled_by_holdout_company_revenue":
            raise ValueError("V5 Q3 holdout benchmark drifted")
        if self.company_revenue_reconciliation_tolerance_krw != 1_000_000:
            raise ValueError("V5 Q3 holdout reconciliation tolerance drifted")
        if not (
            self.require_model_absolute_error_better_than_benchmark
            and self.conditional_one_time_evaluation_pre_authorized
            and self.require_bound_v5_development_gate_passed
            and self.require_immutable_result_reuse
            and self.readiness_checker_must_not_load_holdout
            and self.scorer_requires_explicit_source_bundle
        ):
            raise ValueError("V5 Q3 holdout fail-closed gates drifted")
        if self.refit_before_holdout_allowed or self.refit_after_holdout_allowed:
            raise ValueError("V5 Q3 holdout cannot permit refit around holdout exposure")
        if self.validates_pre_earnings_forecastability:
            raise ValueError("V5 Q3 holdout cannot claim pre-earnings forecast validation")
        if self.product_margin_structural_interpretation_allowed:
            raise ValueError("V5 Q3 holdout cannot reopen product-margin interpretation")
        if any(
            (
                self.numeric_forward_forecast_enabled,
                self.fair_value_estimate_enabled,
                self.target_price_enabled,
                self.decision_score_enabled,
                self.investment_action_enabled,
            )
        ):
            raise ValueError("V5 Q3 holdout protocol opened downstream investment outputs")


def load_frozen_v5_q3_holdout_protocol(
    path: str | Path = DEFAULT_V5_Q3_HOLDOUT_PROTOCOL,
    *,
    method_path: str | Path = DEFAULT_COMPANY_GP_EMPIRICAL_METHOD,
) -> tuple[FrozenV5Q3HoldoutProtocol, FrozenCompanyGPEmpiricalMethod]:
    method = load_frozen_company_gp_empirical_method(method_path)
    with Path(path).open(encoding="utf-8") as handle:
        raw: object = yaml.safe_load(handle)
    root = _mapping(raw, "manifest")
    if root.get("schema_version") != 1:
        raise ValueError("V5 Q3 holdout manifest schema is invalid")
    evidence_id = _sha(root)
    protocol = _mapping(root.get("protocol"), "protocol")
    preauth = _mapping(protocol.get("pre_authorization"), "pre_authorization")
    holdout_design = _mapping(protocol.get("holdout_design"), "holdout_design")
    source_policy = _mapping(protocol.get("source_policy"), "source_policy")
    scientific_scope = _mapping(protocol.get("scientific_scope"), "scientific_scope")
    closeout = _mapping(protocol.get("structural_closeout"), "structural_closeout")
    trust = _mapping(protocol.get("trust_boundary"), "trust_boundary")
    bound_evidence = str(protocol.get("bound_method_evidence_id", ""))
    if bound_evidence != method.evidence_id:
        raise ValueError("V5 Q3 holdout protocol does not bind current frozen V5 method")
    if str(protocol.get("bound_method_id", "")) != method.method_id:
        raise ValueError("V5 Q3 holdout method id binding diverged")
    if str(protocol.get("bound_method_version", "")) != method.method_version:
        raise ValueError("V5 Q3 holdout method version binding diverged")
    if str(protocol.get("holdout_period", "")) != method.future_holdout_period:
        raise ValueError("V5 Q3 holdout period binding diverged")
    raw_date = protocol.get("bound_fit_evaluation_date")
    fit_date = raw_date if isinstance(raw_date, date) else isoparse(str(raw_date)).date()
    result = FrozenV5Q3HoldoutProtocol(
        evidence_id=evidence_id,
        protocol_id=str(protocol.get("protocol_id", "")),
        protocol_version=str(protocol.get("protocol_version", "")),
        status=str(protocol.get("status", "")),
        bound_method_id=str(protocol.get("bound_method_id", "")),
        bound_method_version=str(protocol.get("bound_method_version", "")),
        bound_method_evidence_id=bound_evidence,
        bound_fit_evaluation_date=fit_date,
        holdout_period=str(protocol.get("holdout_period", "")),
        parameter_count=int(str(holdout_design.get("parameter_count", -1))),
        benchmark_id=str(holdout_design.get("benchmark_id", "")),
        company_revenue_reconciliation_tolerance_krw=int(
            str(preauth.get("company_revenue_reconciliation_tolerance_krw", -1))
        ),
        require_model_absolute_error_better_than_benchmark=(
            holdout_design.get("require_model_absolute_error_better_than_benchmark") is True
        ),
        conditional_one_time_evaluation_pre_authorized=(
            preauth.get("conditional_one_time_evaluation_pre_authorized") is True
        ),
        require_bound_v5_development_gate_passed=(
            preauth.get("require_bound_v5_development_gate_passed") is True
        ),
        require_immutable_result_reuse=(
            preauth.get("require_immutable_result_reuse") is True
        ),
        refit_before_holdout_allowed=preauth.get("refit_before_holdout_allowed") is True,
        refit_after_holdout_allowed=preauth.get("refit_after_holdout_allowed") is True,
        readiness_checker_must_not_load_holdout=(
            source_policy.get("readiness_checker_must_not_load_2026q3_source_outcome") is True
        ),
        scorer_requires_explicit_source_bundle=(
            source_policy.get("scorer_may_load_2026q3_only_after_explicit_source_completeness_gate")
            is True
        ),
        validates_pre_earnings_forecastability=(
            scientific_scope.get("validates_pre_earnings_forecastability") is True
        ),
        product_margin_structural_interpretation_allowed=(
            closeout.get("product_margin_structural_interpretation_allowed") is True
        ),
        numeric_forward_forecast_enabled=trust.get("numeric_forward_forecast_enabled") is True,
        fair_value_estimate_enabled=trust.get("fair_value_estimate_enabled") is True,
        target_price_enabled=trust.get("target_price_enabled") is True,
        decision_score_enabled=trust.get("decision_score_enabled") is True,
        investment_action_enabled=trust.get("investment_action_enabled") is True,
    )
    return result, method


__all__ = [
    "DEFAULT_V5_Q3_HOLDOUT_PROTOCOL",
    "FrozenV5Q3HoldoutProtocol",
    "load_frozen_v5_q3_holdout_protocol",
]
