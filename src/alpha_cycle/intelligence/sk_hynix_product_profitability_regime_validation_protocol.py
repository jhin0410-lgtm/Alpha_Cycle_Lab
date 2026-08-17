"""Validate training and one-time holdout rules bound into the frozen regime manifest."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import cast

import yaml

from alpha_cycle.intelligence.sk_hynix_product_profitability_regime_estimation_method import (
    DEFAULT_REGIME_ESTIMATION_METHOD,
    FrozenRegimeEstimationMethod,
)


def _mapping(value: object, label: str) -> dict[object, object]:
    if not isinstance(value, dict):
        raise ValueError(f"Regime validation {label} must be an object")
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
class RegimeValidationProtocol:
    method_evidence_id: str
    company_revenue_reconciliation_tolerance_krw: int
    conditional_one_time_evaluation_pre_authorized: bool
    holdout_may_be_scored_before_training_gate: bool
    require_training_gate_passed: bool
    require_immutable_result_reuse: bool
    holdout_benchmark_id: str
    require_model_absolute_error_better_than_benchmark: bool
    refit_after_holdout_allowed: bool

    def __post_init__(self) -> None:
        if len(self.method_evidence_id) != 64:
            raise ValueError("Regime validation method evidence id must be SHA-256")
        if self.company_revenue_reconciliation_tolerance_krw != 1_000_000:
            raise ValueError("Regime validation reconciliation tolerance drifted")
        if not self.conditional_one_time_evaluation_pre_authorized:
            raise ValueError("Regime validation must pre-authorize conditional holdout use")
        if self.holdout_may_be_scored_before_training_gate:
            raise ValueError("Regime validation cannot score holdout before training gate")
        if not self.require_training_gate_passed or not self.require_immutable_result_reuse:
            raise ValueError("Regime validation holdout gate must remain fail-closed")
        if self.holdout_benchmark_id != "training_mean_gross_margin_scaled_revenue":
            raise ValueError("Regime validation holdout benchmark drifted")
        if not self.require_model_absolute_error_better_than_benchmark:
            raise ValueError("Regime validation holdout comparison must remain strict")
        if self.refit_after_holdout_allowed:
            raise ValueError("Regime validation cannot refit v1 after holdout exposure")


def load_regime_validation_protocol(
    method: FrozenRegimeEstimationMethod,
    path: str | Path = DEFAULT_REGIME_ESTIMATION_METHOD,
) -> RegimeValidationProtocol:
    with Path(path).open(encoding="utf-8") as handle:
        raw: object = yaml.safe_load(handle)
    root = _mapping(raw, "manifest")
    if root.get("schema_version") != 1:
        raise ValueError("Regime validation manifest schema is invalid")
    if _sha(root) != method.evidence_id:
        raise ValueError("Regime validation protocol/method evidence binding diverged")
    raw_method = _mapping(root.get("method"), "method")
    if str(raw_method.get("method_id", "")) != method.method_id:
        raise ValueError("Regime validation method id binding diverged")
    if str(raw_method.get("method_version", "")) != method.method_version:
        raise ValueError("Regime validation method version binding diverged")
    training = _mapping(raw_method.get("training_gate"), "training_gate")
    holdout = _mapping(raw_method.get("holdout_protocol"), "holdout_protocol")
    return RegimeValidationProtocol(
        method_evidence_id=method.evidence_id,
        company_revenue_reconciliation_tolerance_krw=int(
            str(training.get("company_revenue_reconciliation_tolerance_krw", -1))
        ),
        conditional_one_time_evaluation_pre_authorized=(
            holdout.get("conditional_one_time_evaluation_pre_authorized") is True
        ),
        holdout_may_be_scored_before_training_gate=(
            holdout.get("holdout_may_be_scored_before_training_gate") is True
        ),
        require_training_gate_passed=holdout.get("require_training_gate_passed") is True,
        require_immutable_result_reuse=holdout.get("require_immutable_result_reuse") is True,
        holdout_benchmark_id=str(holdout.get("benchmark_id", "")),
        require_model_absolute_error_better_than_benchmark=(
            holdout.get("require_model_absolute_error_better_than_benchmark") is True
        ),
        refit_after_holdout_allowed=holdout.get("refit_after_holdout_allowed") is True,
    )


__all__ = ["RegimeValidationProtocol", "load_regime_validation_protocol"]
