"""Post-holdout economic interpretation audit for the frozen SK hynix regime model.

The v1 model may be retained as an empirical predictor after passing its immutable holdout,
but coefficient combinations must not be relabeled as literal DRAM/NAND gross margins when
they violate accounting hard bounds. This audit is deliberately post-holdout and therefore
does not retroactively change the v1 validation gate.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import cast

from alpha_cycle.intelligence.sk_hynix_product_profitability_regime_estimation_method import (
    DEFAULT_REGIME_ESTIMATION_METHOD,
    FrozenRegimeEstimationMethod,
    load_frozen_regime_estimation_method,
)
from alpha_cycle.intelligence.sk_hynix_product_profitability_regime_holdout import (
    DEFAULT_REGIME_HOLDOUT_POINTER,
    DEFAULT_REGIME_VALIDATION_OUTPUT,
)

DEFAULT_REGIME_TRAINING_FIT_POINTER = DEFAULT_REGIME_VALIDATION_OUTPUT / "latest_training_fit.json"
DEFAULT_REGIME_ECONOMIC_AUDIT_OUTPUT = (
    DEFAULT_REGIME_VALIDATION_OUTPUT / "latest_economic_plausibility_audit.json"
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
    return {str(key): value for key, value in cast(dict[object, object], raw).items()}


def _mapping(payload: dict[str, object], key: str, label: str) -> dict[str, object]:
    raw = payload.get(key)
    if not isinstance(raw, dict):
        raise ValueError(f"{label} must contain object: {key}")
    return {str(k): v for k, v in cast(dict[object, object], raw).items()}


def _tuple_numbers(value: object, label: str) -> tuple[float, ...]:
    if not isinstance(value, list):
        raise ValueError(f"{label} must be an array")
    return tuple(float(str(item)) for item in value)


@dataclass(frozen=True)
class ProductRegimeRange:
    product: str
    minimum_implied_contribution_ratio: float
    maximum_implied_contribution_ratio: float
    maximum_exceeds_revenue_hard_bound: bool
    violating_regimes: tuple[str, ...]


@dataclass(frozen=True)
class RegimeEconomicAuditResult:
    evidence_id: str
    method_evidence_id: str
    training_fit_evidence_id: str
    holdout_evidence_id: str
    holdout_validation_passed: bool
    model_beats_holdout_benchmark: bool
    dram: ProductRegimeRange
    nand: ProductRegimeRange
    other_margin_constant: float
    any_product_revenue_hard_bound_violation: bool
    predictive_validation_retained: bool
    structural_product_margin_interpretation_allowed: bool
    forward_structural_forecast_allowed: bool
    target_price_enabled: bool
    decision_score_enabled: bool
    v1_scope: str
    next_action: str

    def __post_init__(self) -> None:
        hashes = (self.evidence_id, self.method_evidence_id, self.training_fit_evidence_id, self.holdout_evidence_id)
        if any(len(value) != 64 for value in hashes):
            raise ValueError("Economic audit evidence ids must be SHA-256")
        expected_hard = (
            self.dram.maximum_exceeds_revenue_hard_bound
            or self.nand.maximum_exceeds_revenue_hard_bound
        )
        if self.any_product_revenue_hard_bound_violation != expected_hard:
            raise ValueError("Economic audit hard-bound flag is inconsistent")
        if self.predictive_validation_retained != self.holdout_validation_passed:
            raise ValueError("Economic audit predictive validation flag is inconsistent")
        expected_structural = self.holdout_validation_passed and not expected_hard
        if self.structural_product_margin_interpretation_allowed != expected_structural:
            raise ValueError("Economic audit structural interpretation flag is inconsistent")
        if self.forward_structural_forecast_allowed or self.target_price_enabled or self.decision_score_enabled:
            raise ValueError("Economic audit cannot open forward decision outputs")
        if expected_hard and self.v1_scope != "validated_empirical_regime_predictor_only":
            raise ValueError("Economic audit must restrict v1 scope after hard-bound failure")


def _product_range(
    product: str,
    intercept: float,
    asp_effect: float,
    bit_effect: float,
) -> ProductRegimeRange:
    values: list[tuple[str, float]] = []
    for asp in (-1.0, 0.0, 1.0):
        for bit in (-1.0, 0.0, 1.0):
            value = intercept + asp_effect * asp + bit_effect * bit
            values.append((f"asp={asp:+.0f},bit={bit:+.0f}", value))
    violating = tuple(name for name, value in values if value > 1.0)
    ratios = tuple(value for _name, value in values)
    return ProductRegimeRange(
        product=product,
        minimum_implied_contribution_ratio=min(ratios),
        maximum_implied_contribution_ratio=max(ratios),
        maximum_exceeds_revenue_hard_bound=bool(violating),
        violating_regimes=violating,
    )


def build_regime_economic_audit(
    method: FrozenRegimeEstimationMethod,
    training_wrapper: dict[str, object],
    holdout_wrapper: dict[str, object],
) -> RegimeEconomicAuditResult:
    training = _mapping(training_wrapper, "result", "Regime training fit pointer")
    holdout = _mapping(holdout_wrapper, "result", "Regime holdout pointer")
    if str(training_wrapper.get("method_evidence_id", "")) != method.evidence_id:
        raise ValueError("Economic audit training/method binding diverged")
    if str(holdout_wrapper.get("method_evidence_id", "")) != method.evidence_id:
        raise ValueError("Economic audit holdout/method binding diverged")
    training_evidence_id = str(training.get("evidence_id", ""))
    if str(holdout_wrapper.get("training_fit_evidence_id", "")) != training_evidence_id:
        raise ValueError("Economic audit holdout/training binding diverged")
    holdout_evidence_id = str(holdout.get("evidence_id", ""))
    holdout_unhashed = {key: value for key, value in holdout.items() if key != "evidence_id"}
    if _sha(holdout_unhashed) != holdout_evidence_id:
        raise ValueError("Economic audit holdout persisted hash mismatch")
    coefficients = _tuple_numbers(training.get("coefficients"), "training coefficients")
    if len(coefficients) != 7:
        raise ValueError("Economic audit requires seven frozen coefficients")
    if not training.get("training_gate_passed") is True:
        raise ValueError("Economic audit requires a passed frozen training gate")
    holdout_passed = holdout.get("holdout_validation_passed") is True
    model_beats = holdout.get("model_beats_benchmark") is True
    if holdout_passed != model_beats:
        raise ValueError("Economic audit holdout pass/benchmark flags diverged")

    dram = _product_range("DRAM", coefficients[0], coefficients[1], coefficients[2])
    nand = _product_range("NAND", coefficients[3], coefficients[4], coefficients[5])
    hard = dram.maximum_exceeds_revenue_hard_bound or nand.maximum_exceeds_revenue_hard_bound
    structural = holdout_passed and not hard
    scope = (
        "validated_empirical_regime_predictor_only"
        if hard
        else "validated_regime_predictor_structural_interpretation_not_yet_pre_authorized"
    )
    next_action = (
        "design_v2_with_pre_registered_economic_constraints_and_future_holdout_without_refitting_v1"
        if hard
        else "pre_register_separate_forward_forecast_contract_before_any_live_prediction"
    )
    stable = {
        "method_evidence_id": method.evidence_id,
        "training_fit_evidence_id": training_evidence_id,
        "holdout_evidence_id": holdout_evidence_id,
        "holdout_validation_passed": holdout_passed,
        "model_beats_holdout_benchmark": model_beats,
        "dram": dram.__dict__,
        "nand": nand.__dict__,
        "other_margin_constant": coefficients[6],
        "any_product_revenue_hard_bound_violation": hard,
        "predictive_validation_retained": holdout_passed,
        "structural_product_margin_interpretation_allowed": structural,
        "forward_structural_forecast_allowed": False,
        "target_price_enabled": False,
        "decision_score_enabled": False,
        "v1_scope": scope,
        "next_action": next_action,
    }
    return RegimeEconomicAuditResult(evidence_id=_sha(stable), **stable)


def load_and_build_regime_economic_audit(
    *,
    method_path: str | Path = DEFAULT_REGIME_ESTIMATION_METHOD,
    training_fit_pointer: str | Path = DEFAULT_REGIME_TRAINING_FIT_POINTER,
    holdout_pointer: str | Path = DEFAULT_REGIME_HOLDOUT_POINTER,
) -> RegimeEconomicAuditResult:
    method = load_frozen_regime_estimation_method(method_path)
    training = _object(Path(training_fit_pointer), "Regime training fit pointer")
    holdout = _object(Path(holdout_pointer), "Regime holdout pointer")
    return build_regime_economic_audit(method, training, holdout)


__all__ = [
    "DEFAULT_REGIME_ECONOMIC_AUDIT_OUTPUT",
    "DEFAULT_REGIME_TRAINING_FIT_POINTER",
    "ProductRegimeRange",
    "RegimeEconomicAuditResult",
    "build_regime_economic_audit",
    "load_and_build_regime_economic_audit",
]
