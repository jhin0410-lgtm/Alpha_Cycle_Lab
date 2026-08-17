"""Post-holdout structural plausibility audit for the frozen SK hynix regime v1 model.

This audit does not revalidate predictive performance and does not refit v1. It verifies the
persisted training/holdout evidence bindings, preserves the pre-registered report-only
influence diagnostics, and asks a narrower accounting question: if the fitted coefficients
are interpreted literally as product gross-margin contribution ratios, do any allowed
(+1/0/-1) direction regimes imply gross margin above 100% under nonnegative COGS?
"""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import cast

import yaml

from alpha_cycle.intelligence.sk_hynix_product_profitability_regime_estimation_method import (
    DEFAULT_REGIME_ESTIMATION_METHOD,
    FrozenRegimeEstimationMethod,
    load_frozen_regime_estimation_method,
)
from alpha_cycle.intelligence.sk_hynix_product_profitability_regime_holdout import (
    DEFAULT_REGIME_HOLDOUT_POINTER,
    DEFAULT_REGIME_VALIDATION_OUTPUT,
)

DEFAULT_POST_VALIDATION_AUDIT_POLICY = Path(
    "config/skhynix_product_profitability_regime_v1_post_validation_audit.v1.yaml"
)
DEFAULT_REGIME_TRAINING_FIT_POINTER = DEFAULT_REGIME_VALIDATION_OUTPUT / "latest_training_fit.json"
DEFAULT_POST_VALIDATION_AUDIT_OUTPUT = DEFAULT_REGIME_VALIDATION_OUTPUT / (
    "latest_post_validation_audit.json"
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


def _sha(payload: object) -> str:
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _object(path: Path, label: str) -> dict[str, object]:
    try:
        raw: object = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ValueError(f"{label} not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"{label} is invalid JSON: {path}") from exc
    if not isinstance(raw, dict):
        raise ValueError(f"{label} must be an object")
    return {str(key): value for key, value in cast(dict[object, object], raw).items()}


def _mapping(value: object, label: str) -> dict[object, object]:
    if not isinstance(value, dict):
        raise ValueError(f"Post-validation audit {label} must be an object")
    return cast(dict[object, object], value)


def _string(value: object, label: str) -> str:
    result = str(value).strip()
    if not result:
        raise ValueError(f"Post-validation audit {label} cannot be empty")
    return result


def _number(value: object, label: str) -> float:
    try:
        result = float(str(value))
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Post-validation audit {label} must be numeric") from exc
    if not math.isfinite(result):
        raise ValueError(f"Post-validation audit {label} must be finite")
    return result


def _sequence(value: object, label: str) -> list[object]:
    if not isinstance(value, list):
        raise ValueError(f"Post-validation audit {label} must be an array")
    return list(value)


@dataclass(frozen=True)
class PostValidationAuditPolicy:
    evidence_id: str
    audit_id: str
    audit_version: str
    status: str
    method_id: str
    method_version: str
    coefficient_family: str
    direction_codes: tuple[float, ...]
    evaluate_full_direction_regime_grid: bool
    nonnegative_cogs_identity_upper_bound: float
    negative_margin_is_automatic_failure: bool
    require_no_upper_bound_violation_for_structural_margin_interpretation: bool
    predictive_validation_can_remain_passed_if_structural_interpretation_fails: bool
    structural_margin_interpretation_required_before_forward_forecast_contract: bool
    forward_forecast_enabled_on_structural_failure: bool
    fair_value_enabled_on_structural_failure: bool
    target_price_enabled_on_structural_failure: bool
    decision_score_enabled_on_structural_failure: bool
    refit_v1_after_holdout_allowed: bool
    reuse_2026q1_as_unseen_holdout_for_v2_allowed: bool

    def __post_init__(self) -> None:
        if len(self.evidence_id) != 64:
            raise ValueError("Post-validation audit policy evidence id must be SHA-256")
        if self.audit_id != "skhynix_product_profitability_regime_v1_structural_plausibility":
            raise ValueError("Post-validation audit policy id drifted")
        if self.audit_version != "1.0":
            raise ValueError("Post-validation audit policy version drifted")
        if self.status != "post_holdout_diagnostic_not_predictive_revalidation":
            raise ValueError("Post-validation audit policy status drifted")
        if self.method_id != "skhynix_product_profitability_regime_ols":
            raise ValueError("Post-validation audit method id drifted")
        if self.method_version != "1.0-frozen-pre-holdout":
            raise ValueError("Post-validation audit method version drifted")
        if self.coefficient_family != "revenue_weighted_gross_margin_contribution_ratio":
            raise ValueError("Post-validation audit coefficient semantics drifted")
        if self.direction_codes != (-1.0, 0.0, 1.0):
            raise ValueError("Post-validation audit direction grid drifted")
        if not self.evaluate_full_direction_regime_grid:
            raise ValueError("Post-validation audit must evaluate the full sign grid")
        if self.nonnegative_cogs_identity_upper_bound != 1.0:
            raise ValueError("Post-validation audit accounting upper bound drifted")
        if self.negative_margin_is_automatic_failure:
            raise ValueError("Post-validation audit cannot reject negative margins automatically")
        if not self.require_no_upper_bound_violation_for_structural_margin_interpretation:
            raise ValueError("Post-validation audit structural interpretation gate drifted")
        if not self.predictive_validation_can_remain_passed_if_structural_interpretation_fails:
            raise ValueError("Post-validation audit must separate predictive and structural status")
        if not self.structural_margin_interpretation_required_before_forward_forecast_contract:
            raise ValueError("Post-validation audit must block structural forecast handoff")
        forbidden = (
            self.forward_forecast_enabled_on_structural_failure,
            self.fair_value_enabled_on_structural_failure,
            self.target_price_enabled_on_structural_failure,
            self.decision_score_enabled_on_structural_failure,
            self.refit_v1_after_holdout_allowed,
            self.reuse_2026q1_as_unseen_holdout_for_v2_allowed,
        )
        if any(forbidden):
            raise ValueError("Post-validation audit opened a forbidden downstream boundary")


@dataclass(frozen=True)
class RegimeMarginPoint:
    asp_direction_code: float
    bit_volume_direction_code: float
    implied_margin_ratio: float
    exceeds_nonnegative_cogs_upper_bound: bool


@dataclass(frozen=True)
class ProductMarginEnvelope:
    product: str
    minimum_implied_margin_ratio: float
    maximum_implied_margin_ratio: float
    minimum_regimes: tuple[tuple[float, float], ...]
    maximum_regimes: tuple[tuple[float, float], ...]
    upper_bound_violation_count: int
    upper_bound_violation_regimes: tuple[tuple[float, float], ...]
    observed_upper_bound_violation_periods: tuple[str, ...]
    grid: tuple[RegimeMarginPoint, ...]

    def __post_init__(self) -> None:
        if self.product not in {"dram", "nand"}:
            raise ValueError("Post-validation audit product envelope is unsupported")
        if self.upper_bound_violation_count != len(self.upper_bound_violation_regimes):
            raise ValueError("Post-validation audit violation count is inconsistent")
        if len(self.grid) != 9:
            raise ValueError("Post-validation audit direction grid must contain nine points")


@dataclass(frozen=True)
class RegimeV1PostValidationAuditResult:
    evidence_id: str
    policy_evidence_id: str
    method_evidence_id: str
    training_fit_evidence_id: str
    holdout_evidence_id: str
    predictive_validation_passed: bool
    structural_margin_interpretation_passed: bool
    forward_forecast_contract_review_allowed: bool
    model_status: str
    dram_margin_envelope: ProductMarginEnvelope
    nand_margin_envelope: ProductMarginEnvelope
    other_margin_constant: float
    other_margin_absolute_value_gt_one_report_only: bool
    max_leverage_report_only: float
    max_cooks_distance_report_only: float | None
    coefficient_jackknife_report_only: bool
    refit_v1_after_holdout_allowed: bool = False
    reuse_2026q1_as_unseen_holdout_for_v2_allowed: bool = False
    product_profitability_is_direct_source_fact: bool = False
    numeric_forecast_enabled: bool = False
    fair_value_estimate_enabled: bool = False
    target_price_enabled: bool = False
    decision_score_enabled: bool = False

    def __post_init__(self) -> None:
        hashes = (
            self.evidence_id,
            self.policy_evidence_id,
            self.method_evidence_id,
            self.training_fit_evidence_id,
            self.holdout_evidence_id,
        )
        if any(len(value) != 64 for value in hashes):
            raise ValueError("Post-validation audit evidence ids must be SHA-256")
        expected_forward = (
            self.predictive_validation_passed and self.structural_margin_interpretation_passed
        )
        if self.forward_forecast_contract_review_allowed != expected_forward:
            raise ValueError("Post-validation audit forward-contract gate is inconsistent")
        if self.predictive_validation_passed and not self.structural_margin_interpretation_passed:
            expected_status = "predictively_validated_structurally_noninterpretable"
        elif self.predictive_validation_passed:
            expected_status = "predictively_validated_structural_review_passed"
        else:
            expected_status = "predictive_validation_not_passed"
        if self.model_status != expected_status:
            raise ValueError("Post-validation audit model status is inconsistent")
        forbidden = (
            self.refit_v1_after_holdout_allowed,
            self.reuse_2026q1_as_unseen_holdout_for_v2_allowed,
            self.product_profitability_is_direct_source_fact,
            self.numeric_forecast_enabled,
            self.fair_value_estimate_enabled,
            self.target_price_enabled,
            self.decision_score_enabled,
        )
        if any(forbidden):
            raise ValueError("Post-validation audit exceeded its trust boundary")


def load_post_validation_audit_policy(
    path: str | Path = DEFAULT_POST_VALIDATION_AUDIT_POLICY,
) -> PostValidationAuditPolicy:
    with Path(path).open(encoding="utf-8") as handle:
        raw: object = yaml.safe_load(handle)
    root = _mapping(raw, "manifest")
    if root.get("schema_version") != 1:
        raise ValueError("Post-validation audit policy schema is invalid")
    audit = _mapping(root.get("audit"), "audit")
    interpretation = _mapping(audit.get("interpretation_contract"), "interpretation_contract")
    decision = _mapping(audit.get("decision_boundary"), "decision_boundary")
    codes = tuple(
        _number(value, "direction code")
        for value in _sequence(interpretation.get("direction_codes"), "direction_codes")
    )
    return PostValidationAuditPolicy(
        evidence_id=_sha(root),
        audit_id=_string(audit.get("audit_id"), "audit_id"),
        audit_version=_string(audit.get("audit_version"), "audit_version"),
        status=_string(audit.get("status"), "status"),
        method_id=_string(audit.get("method_id"), "method_id"),
        method_version=_string(audit.get("method_version"), "method_version"),
        coefficient_family=_string(interpretation.get("coefficient_family"), "coefficient_family"),
        direction_codes=codes,
        evaluate_full_direction_regime_grid=(
            interpretation.get("evaluate_full_direction_regime_grid") is True
        ),
        nonnegative_cogs_identity_upper_bound=_number(
            interpretation.get("nonnegative_cogs_identity_upper_bound"),
            "nonnegative_cogs_identity_upper_bound",
        ),
        negative_margin_is_automatic_failure=(
            interpretation.get("negative_margin_is_automatic_failure") is True
        ),
        require_no_upper_bound_violation_for_structural_margin_interpretation=(
            interpretation.get(
                "require_no_upper_bound_violation_for_structural_margin_interpretation"
            )
            is True
        ),
        predictive_validation_can_remain_passed_if_structural_interpretation_fails=(
            decision.get(
                "predictive_validation_can_remain_passed_if_structural_interpretation_fails"
            )
            is True
        ),
        structural_margin_interpretation_required_before_forward_forecast_contract=(
            decision.get(
                "structural_margin_interpretation_required_before_forward_forecast_contract"
            )
            is True
        ),
        forward_forecast_enabled_on_structural_failure=(
            decision.get("forward_forecast_enabled_on_structural_failure") is True
        ),
        fair_value_enabled_on_structural_failure=(
            decision.get("fair_value_enabled_on_structural_failure") is True
        ),
        target_price_enabled_on_structural_failure=(
            decision.get("target_price_enabled_on_structural_failure") is True
        ),
        decision_score_enabled_on_structural_failure=(
            decision.get("decision_score_enabled_on_structural_failure") is True
        ),
        refit_v1_after_holdout_allowed=decision.get("refit_v1_after_holdout_allowed") is True,
        reuse_2026q1_as_unseen_holdout_for_v2_allowed=(
            decision.get("reuse_2026q1_as_unseen_holdout_for_v2_allowed") is True
        ),
    )


def _validated_training_result(
    path: Path,
    method: FrozenRegimeEstimationMethod,
) -> dict[str, object]:
    wrapper = _object(path, "Regime training-fit pointer")
    if wrapper.get("status") != "skhynix_product_profitability_regime_training_fit_completed":
        raise ValueError("Post-validation audit training pointer status is invalid")
    if str(wrapper.get("method_evidence_id", "")) != method.evidence_id:
        raise ValueError("Post-validation audit training pointer method binding diverged")
    result_raw = wrapper.get("result")
    if not isinstance(result_raw, dict):
        raise ValueError("Post-validation audit training result is invalid")
    result = {str(key): value for key, value in cast(dict[object, object], result_raw).items()}
    stable = {
        "evaluation_date": result.get("evaluation_date"),
        "method_evidence_id": result.get("method_evidence_id"),
        "base_rank_probe_evidence_id": result.get("base_rank_probe_evidence_id"),
        "training_periods": result.get("training_periods"),
        "rows": result.get("rows"),
        "coefficients": result.get("coefficients"),
        "loocv": result.get("loocv"),
        "training_gate_passed": result.get("training_gate_passed"),
    }
    if _sha(stable) != str(result.get("evidence_id", "")):
        raise ValueError("Post-validation audit training evidence hash mismatch")
    if str(result.get("method_evidence_id", "")) != method.evidence_id:
        raise ValueError("Post-validation audit training result method binding diverged")
    if result.get("training_gate_passed") is not True:
        raise ValueError("Post-validation audit requires a passed frozen training gate")
    return result


def _validated_holdout_result(
    path: Path,
    method: FrozenRegimeEstimationMethod,
    training_fit_evidence_id: str,
) -> dict[str, object]:
    wrapper = _object(path, "Regime holdout pointer")
    if wrapper.get("status") != "skhynix_product_profitability_regime_holdout_spent":
        raise ValueError("Post-validation audit holdout pointer status is invalid")
    result_raw = wrapper.get("result")
    if not isinstance(result_raw, dict):
        raise ValueError("Post-validation audit holdout result is invalid")
    result = {str(key): value for key, value in cast(dict[object, object], result_raw).items()}
    unhashed = {key: value for key, value in result.items() if key != "evidence_id"}
    if _sha(unhashed) != str(result.get("evidence_id", "")):
        raise ValueError("Post-validation audit holdout evidence hash mismatch")
    if str(result.get("method_evidence_id", "")) != method.evidence_id:
        raise ValueError("Post-validation audit holdout method binding diverged")
    if str(result.get("training_fit_evidence_id", "")) != training_fit_evidence_id:
        raise ValueError("Post-validation audit holdout/training binding diverged")
    if result.get("holdout_spent") is not True or result.get("immutable_result") is not True:
        raise ValueError("Post-validation audit requires an immutable spent holdout")
    return result


def _coefficient_map(
    method: FrozenRegimeEstimationMethod,
    training: dict[str, object],
) -> dict[str, float]:
    if method.parameters != _EXPECTED_PARAMETERS:
        raise ValueError("Post-validation audit parameter order drifted")
    raw = _sequence(training.get("coefficients"), "training coefficients")
    if len(raw) != len(method.parameters):
        raise ValueError("Post-validation audit coefficient count is invalid")
    return {
        parameter: _number(value, f"coefficient {parameter}")
        for parameter, value in zip(method.parameters, raw, strict=True)
    }


def _rows(training: dict[str, object]) -> tuple[dict[str, object], ...]:
    raw_rows = _sequence(training.get("rows"), "training rows")
    rows: list[dict[str, object]] = []
    for raw in raw_rows:
        if not isinstance(raw, dict):
            raise ValueError("Post-validation audit training row is invalid")
        rows.append({str(key): value for key, value in cast(dict[object, object], raw).items()})
    return tuple(rows)


def _envelope(
    *,
    product: str,
    base: float,
    asp_effect: float,
    bit_effect: float,
    rows: tuple[dict[str, object], ...],
    policy: PostValidationAuditPolicy,
) -> ProductMarginEnvelope:
    points: list[RegimeMarginPoint] = []
    violations: list[tuple[float, float]] = []
    for asp_code in policy.direction_codes:
        for bit_code in policy.direction_codes:
            margin = base + asp_effect * asp_code + bit_effect * bit_code
            exceeds = margin > policy.nonnegative_cogs_identity_upper_bound
            if exceeds:
                violations.append((asp_code, bit_code))
            points.append(
                RegimeMarginPoint(
                    asp_direction_code=asp_code,
                    bit_volume_direction_code=bit_code,
                    implied_margin_ratio=margin,
                    exceeds_nonnegative_cogs_upper_bound=exceeds,
                )
            )
    values = tuple(item.implied_margin_ratio for item in points)
    minimum = min(values)
    maximum = max(values)
    minimum_regimes = tuple(
        (item.asp_direction_code, item.bit_volume_direction_code)
        for item in points
        if item.implied_margin_ratio == minimum
    )
    maximum_regimes = tuple(
        (item.asp_direction_code, item.bit_volume_direction_code)
        for item in points
        if item.implied_margin_ratio == maximum
    )
    observed_violations: list[str] = []
    asp_key = f"{product}_asp_direction_code"
    bit_key = f"{product}_bit_volume_direction_code"
    for row in rows:
        period = _string(row.get("period_id"), "training row period_id")
        asp_code = _number(row.get(asp_key), f"{period} {asp_key}")
        bit_code = _number(row.get(bit_key), f"{period} {bit_key}")
        if asp_code not in policy.direction_codes or bit_code not in policy.direction_codes:
            raise ValueError("Post-validation audit observed direction code is outside policy")
        margin = base + asp_effect * asp_code + bit_effect * bit_code
        if margin > policy.nonnegative_cogs_identity_upper_bound:
            observed_violations.append(period)
    return ProductMarginEnvelope(
        product=product,
        minimum_implied_margin_ratio=minimum,
        maximum_implied_margin_ratio=maximum,
        minimum_regimes=minimum_regimes,
        maximum_regimes=maximum_regimes,
        upper_bound_violation_count=len(violations),
        upper_bound_violation_regimes=tuple(violations),
        observed_upper_bound_violation_periods=tuple(observed_violations),
        grid=tuple(points),
    )


def build_regime_v1_post_validation_audit(
    *,
    method_path: str | Path = DEFAULT_REGIME_ESTIMATION_METHOD,
    policy_path: str | Path = DEFAULT_POST_VALIDATION_AUDIT_POLICY,
    training_fit_path: str | Path = DEFAULT_REGIME_TRAINING_FIT_POINTER,
    holdout_path: str | Path = DEFAULT_REGIME_HOLDOUT_POINTER,
) -> RegimeV1PostValidationAuditResult:
    method = load_frozen_regime_estimation_method(method_path)
    policy = load_post_validation_audit_policy(policy_path)
    if policy.method_id != method.method_id or policy.method_version != method.method_version:
        raise ValueError("Post-validation audit policy/method binding diverged")
    training = _validated_training_result(Path(training_fit_path), method)
    training_evidence_id = _string(training.get("evidence_id"), "training evidence_id")
    holdout = _validated_holdout_result(Path(holdout_path), method, training_evidence_id)
    coefficients = _coefficient_map(method, training)
    rows = _rows(training)

    dram = _envelope(
        product="dram",
        base=coefficients["dram_margin_intercept"],
        asp_effect=coefficients["dram_asp_direction_regime_effect"],
        bit_effect=coefficients["dram_bit_volume_direction_regime_effect"],
        rows=rows,
        policy=policy,
    )
    nand = _envelope(
        product="nand",
        base=coefficients["nand_margin_intercept"],
        asp_effect=coefficients["nand_asp_direction_regime_effect"],
        bit_effect=coefficients["nand_bit_volume_direction_regime_effect"],
        rows=rows,
        policy=policy,
    )
    other_margin = coefficients["other_margin_constant"]
    product_upper_bound_clean = (
        dram.upper_bound_violation_count == 0 and nand.upper_bound_violation_count == 0
    )
    other_upper_bound_clean = other_margin <= policy.nonnegative_cogs_identity_upper_bound
    structural_pass = product_upper_bound_clean and other_upper_bound_clean
    predictive_pass = (
        training.get("training_gate_passed") is True
        and holdout.get("holdout_validation_passed") is True
    )
    forward_review_allowed = predictive_pass and structural_pass
    if predictive_pass and not structural_pass:
        model_status = "predictively_validated_structurally_noninterpretable"
    elif predictive_pass:
        model_status = "predictively_validated_structural_review_passed"
    else:
        model_status = "predictive_validation_not_passed"

    max_cooks_raw = training.get("max_cooks_distance")
    max_cooks = None if max_cooks_raw is None else _number(max_cooks_raw, "max_cooks_distance")
    stable = {
        "policy_evidence_id": policy.evidence_id,
        "method_evidence_id": method.evidence_id,
        "training_fit_evidence_id": training_evidence_id,
        "holdout_evidence_id": holdout.get("evidence_id"),
        "predictive_validation_passed": predictive_pass,
        "structural_margin_interpretation_passed": structural_pass,
        "dram_margin_envelope": asdict(dram),
        "nand_margin_envelope": asdict(nand),
        "other_margin_constant": other_margin,
        "forward_forecast_contract_review_allowed": forward_review_allowed,
    }
    return RegimeV1PostValidationAuditResult(
        evidence_id=_sha(stable),
        policy_evidence_id=policy.evidence_id,
        method_evidence_id=method.evidence_id,
        training_fit_evidence_id=training_evidence_id,
        holdout_evidence_id=_string(holdout.get("evidence_id"), "holdout evidence_id"),
        predictive_validation_passed=predictive_pass,
        structural_margin_interpretation_passed=structural_pass,
        forward_forecast_contract_review_allowed=forward_review_allowed,
        model_status=model_status,
        dram_margin_envelope=dram,
        nand_margin_envelope=nand,
        other_margin_constant=other_margin,
        other_margin_absolute_value_gt_one_report_only=abs(other_margin) > 1.0,
        max_leverage_report_only=_number(training.get("max_leverage"), "max_leverage"),
        max_cooks_distance_report_only=max_cooks,
        coefficient_jackknife_report_only=True,
    )


__all__ = [
    "DEFAULT_POST_VALIDATION_AUDIT_OUTPUT",
    "DEFAULT_POST_VALIDATION_AUDIT_POLICY",
    "DEFAULT_REGIME_TRAINING_FIT_POINTER",
    "PostValidationAuditPolicy",
    "ProductMarginEnvelope",
    "RegimeMarginPoint",
    "RegimeV1PostValidationAuditResult",
    "build_regime_v1_post_validation_audit",
    "load_post_validation_audit_policy",
]
