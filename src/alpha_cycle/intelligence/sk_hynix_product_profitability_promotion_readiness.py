"""Fail-closed promotion readiness for the SK hynix latent profitability method.

This layer sits above the direction-only structural rank probe.  It does not estimate
DRAM/NAND margins.  It classifies issuer magnitude language into explicitly methodological
interval assumptions for sensitivity diagnostics, audits sample depth, protects the frozen
holdout, and determines whether a future *estimation-candidate promotion* may even be
considered.

The interval mapping is not an issuer numeric source fact and cannot itself enable fitting.
Open-ended phrases (for example ``Over 70% Increase``) remain open ended.  The optional
closed-interval design sensitivity is deliberately labelled diagnostic rather than formal
partial identification.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from dataclasses import asdict, dataclass
from datetime import date
from pathlib import Path
from typing import cast

import numpy as np
import yaml

from alpha_cycle.intelligence.sk_hynix_product_profitability_structural_method import (
    DEFAULT_STRUCTURAL_METHOD_PATH,
    StructuralProfitabilityMethodContract,
    StructuralRankProbeResult,
    StructuralRankProbeRow,
    load_structural_profitability_method,
)
from alpha_cycle.intelligence.sk_hynix_product_profitability_structural_rank_probe_report import (
    load_structural_rank_probe_report,
)

DEFAULT_PROMOTION_READINESS_POLICY = Path(
    "config/skhynix_product_profitability_promotion_readiness.v1.yaml"
)
DEFAULT_PROMOTION_READINESS_OUTPUT = Path(
    "data/private/research/skhynix-product-profitability-promotion-readiness"
)


def _sha_payload(payload: object) -> str:
    return hashlib.sha256(
        json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        ).encode("utf-8")
    ).hexdigest()


def _valid_sha(value: str) -> bool:
    return len(value) == 64 and all(char in "0123456789abcdef" for char in value)


@dataclass(frozen=True)
class MagnitudeBand:
    lower: float
    upper: float

    def __post_init__(self) -> None:
        if not (0.0 <= self.lower <= self.upper):
            raise ValueError("Promotion-readiness magnitude band is invalid")


@dataclass(frozen=True)
class PromotionReadinessPolicy:
    policy_id: str
    policy_version: str
    ticker: str
    holdout_period: str
    minimum_rows_per_parameter: float
    minimum_residual_degrees_of_freedom: int
    require_full_column_rank: bool
    require_company_product_revenue_reconciliation: bool
    require_closed_interval_sensitivity_coverage: bool
    require_estimation_driver_input_ready: bool
    require_method_version_frozen: bool
    bands: dict[str, MagnitudeBand]
    around_tolerance_percent_points: float
    over_upper_bound: float | None
    interval_source_fact: bool
    interval_method_assumption: bool
    interval_estimation_input_ready: bool
    interval_sensitivity_is_formal_partial_identification: bool
    interval_sensitivity_can_enable_fit: bool
    numeric_forecast_enabled: bool
    fair_value_estimate_enabled: bool
    target_price_enabled: bool
    decision_score_enabled: bool
    manifest_sha256: str

    def __post_init__(self) -> None:
        if self.policy_id != "skhynix_product_profitability_promotion_readiness":
            raise ValueError("Promotion-readiness policy id is unsupported")
        if self.policy_version != "0.1-draft" or self.ticker != "000660":
            raise ValueError("Promotion-readiness policy identity drifted")
        if self.holdout_period != "2026Q1":
            raise ValueError("Promotion-readiness holdout must remain 2026Q1")
        if self.minimum_rows_per_parameter < 1.0:
            raise ValueError("Promotion-readiness row/parameter policy is invalid")
        if self.minimum_residual_degrees_of_freedom < 1:
            raise ValueError("Promotion-readiness residual-DOF policy is invalid")
        required_true = (
            self.require_full_column_rank,
            self.require_company_product_revenue_reconciliation,
            self.require_closed_interval_sensitivity_coverage,
            self.require_estimation_driver_input_ready,
            self.require_method_version_frozen,
        )
        if not all(required_true):
            raise ValueError("Promotion-readiness v0.1 must remain fail-closed")
        if (
            self.interval_source_fact
            or not self.interval_method_assumption
            or self.interval_estimation_input_ready
            or self.interval_sensitivity_is_formal_partial_identification
            or self.interval_sensitivity_can_enable_fit
            or self.numeric_forecast_enabled
            or self.fair_value_estimate_enabled
            or self.target_price_enabled
            or self.decision_score_enabled
        ):
            raise ValueError("Promotion-readiness policy exceeded its trust boundary")
        if self.around_tolerance_percent_points <= 0:
            raise ValueError("Around tolerance must be positive")
        if self.over_upper_bound is not None:
            raise ValueError("Over-N language must remain open ended in v0.1")
        if not _valid_sha(self.manifest_sha256):
            raise ValueError("Promotion-readiness manifest hash must be SHA-256")


def _mapping(value: object, label: str) -> dict[object, object]:
    if not isinstance(value, dict):
        raise ValueError(f"Promotion-readiness {label} must be an object")
    return cast(dict[object, object], value)


def load_promotion_readiness_policy(
    path: str | Path = DEFAULT_PROMOTION_READINESS_POLICY,
) -> PromotionReadinessPolicy:
    policy_path = Path(path)
    with policy_path.open(encoding="utf-8") as handle:
        raw: object = yaml.safe_load(handle)
    root = _mapping(raw, "manifest")
    if root.get("schema_version") != 1:
        raise ValueError("Promotion-readiness manifest schema is invalid")
    policy = _mapping(root.get("policy"), "policy")
    semantics = _mapping(policy.get("interval_semantics"), "interval_semantics")
    trust = _mapping(policy.get("trust_boundary"), "trust_boundary")
    band_names = (
        "slight",
        "low-single",
        "mid-single",
        "high-single",
        "low-teen",
        "mid-teen",
        "mid-high-teen",
        "high-teen",
        "low-20",
        "mid-20",
        "mid-30",
    )
    bands: dict[str, MagnitudeBand] = {}
    for name in band_names:
        item = _mapping(semantics.get(name), f"interval_semantics.{name}")
        bands[name] = MagnitudeBand(float(item["lower"]), float(item["upper"]))
    manifest_sha256 = _sha_payload(root)
    over_raw = semantics.get("over_upper_bound")
    return PromotionReadinessPolicy(
        policy_id=str(policy.get("policy_id", "")),
        policy_version=str(policy.get("policy_version", "")),
        ticker=str(policy.get("ticker", "")).zfill(6),
        holdout_period=str(policy.get("holdout_period", "")),
        minimum_rows_per_parameter=float(policy.get("minimum_rows_per_parameter", 0.0)),
        minimum_residual_degrees_of_freedom=int(
            policy.get("minimum_residual_degrees_of_freedom", 0)
        ),
        require_full_column_rank=policy.get("require_full_column_rank") is True,
        require_company_product_revenue_reconciliation=(
            policy.get("require_company_product_revenue_reconciliation") is True
        ),
        require_closed_interval_sensitivity_coverage=(
            policy.get("require_closed_interval_sensitivity_coverage") is True
        ),
        require_estimation_driver_input_ready=(
            policy.get("require_estimation_driver_input_ready") is True
        ),
        require_method_version_frozen=policy.get("require_method_version_frozen") is True,
        bands=bands,
        around_tolerance_percent_points=float(
            semantics.get("around_tolerance_percent_points", 0.0)
        ),
        over_upper_bound=(None if over_raw is None else float(over_raw)),
        interval_source_fact=semantics.get("source_fact") is True,
        interval_method_assumption=semantics.get("method_assumption") is True,
        interval_estimation_input_ready=semantics.get("estimation_input_ready") is True,
        interval_sensitivity_is_formal_partial_identification=(
            trust.get("interval_sensitivity_is_formal_partial_identification") is True
        ),
        interval_sensitivity_can_enable_fit=(
            trust.get("interval_sensitivity_can_enable_fit") is True
        ),
        numeric_forecast_enabled=trust.get("numeric_forecast_enabled") is True,
        fair_value_estimate_enabled=trust.get("fair_value_estimate_enabled") is True,
        target_price_enabled=trust.get("target_price_enabled") is True,
        decision_score_enabled=trust.get("decision_score_enabled") is True,
        manifest_sha256=manifest_sha256,
    )


@dataclass(frozen=True)
class DriverIntervalAssumption:
    source_text: str
    direction: str
    interval_kind: str
    lower_abs_percent: float
    upper_abs_percent: float | None
    closed_interval: bool
    source_fact: bool = False
    method_assumption: bool = True
    estimation_input_ready: bool = False

    def __post_init__(self) -> None:
        if self.direction not in {"increase", "flat", "decrease"}:
            raise ValueError("Driver interval direction is invalid")
        if self.lower_abs_percent < 0:
            raise ValueError("Driver interval lower bound is invalid")
        if self.closed_interval != (self.upper_abs_percent is not None):
            raise ValueError("Driver interval closure flag is inconsistent")
        if self.upper_abs_percent is not None and self.upper_abs_percent < self.lower_abs_percent:
            raise ValueError("Driver interval upper bound is invalid")
        if self.source_fact or not self.method_assumption or self.estimation_input_ready:
            raise ValueError("Driver interval exceeded its sensitivity-only trust boundary")


def classify_driver_interval(
    source_text: str,
    policy: PromotionReadinessPolicy,
) -> DriverIntervalAssumption:
    text = " ".join(source_text.split())
    if text == "Flat":
        return DriverIntervalAssumption(text, "flat", "flat", 0.0, 0.0, True)
    if text.endswith(" Increase"):
        direction = "increase"
        magnitude = text[: -len(" Increase")]
    elif text.endswith(" Decrease"):
        direction = "decrease"
        magnitude = text[: -len(" Decrease")]
    else:
        raise ValueError(f"Unsupported issuer driver text: {source_text}")

    aliases = {
        "Slight": "slight",
        "Low-single%": "low-single",
        "Mid-single%": "mid-single",
        "High-single%": "high-single",
        "Low-teen%": "low-teen",
        "Mid-teen%": "mid-teen",
        "Mid-high-teen%": "mid-high-teen",
        "High-teen%": "high-teen",
        "Low-20%": "low-20",
        "Mid-20%": "mid-20",
        "Mid-30%": "mid-30",
    }
    band_name = aliases.get(magnitude)
    if band_name is not None:
        band = policy.bands[band_name]
        return DriverIntervalAssumption(
            text, direction, band_name, band.lower, band.upper, True
        )

    around = re.fullmatch(r"Around (\d+(?:\.\d+)?)%", magnitude)
    if around:
        center = float(around.group(1))
        tolerance = policy.around_tolerance_percent_points
        return DriverIntervalAssumption(
            text,
            direction,
            "around",
            max(0.0, center - tolerance),
            center + tolerance,
            True,
        )

    over = re.fullmatch(r"Over (\d+(?:\.\d+)?)%", magnitude)
    if over:
        lower = float(over.group(1))
        return DriverIntervalAssumption(
            text,
            direction,
            "open_over",
            lower,
            policy.over_upper_bound,
            False,
        )
    raise ValueError(f"Unsupported issuer magnitude language: {source_text}")


def _signed_fraction(interval: DriverIntervalAssumption, point: str) -> float:
    if not interval.closed_interval or interval.upper_abs_percent is None:
        raise ValueError("Open interval cannot enter closed sensitivity design")
    magnitude = {
        "lower": interval.lower_abs_percent,
        "midpoint": (interval.lower_abs_percent + interval.upper_abs_percent) / 2.0,
        "upper": interval.upper_abs_percent,
    }[point]
    sign = {"increase": 1.0, "flat": 0.0, "decrease": -1.0}[interval.direction]
    return sign * magnitude / 100.0


def _row_intervals(
    row: StructuralRankProbeRow,
    policy: PromotionReadinessPolicy,
) -> tuple[DriverIntervalAssumption, ...]:
    return tuple(
        classify_driver_interval(item.source_text, policy)
        for item in (row.dram_asp, row.dram_bit_volume, row.nand_asp, row.nand_bit_volume)
    )


def _sensitivity_rank(
    rows: tuple[StructuralRankProbeRow, ...],
    intervals: tuple[tuple[DriverIntervalAssumption, ...], ...],
    point: str,
) -> int:
    design: list[tuple[float, ...]] = []
    for row, driver_intervals in zip(rows, intervals, strict=True):
        dram_asp, dram_bit, nand_asp, nand_bit = (
            _signed_fraction(item, point) for item in driver_intervals
        )
        design.append(
            (
                row.dram_revenue_krw_million,
                row.dram_revenue_krw_million * dram_asp,
                row.dram_revenue_krw_million * dram_bit,
                row.nand_revenue_krw_million,
                row.nand_revenue_krw_million * nand_asp,
                row.nand_revenue_krw_million * nand_bit,
                row.other_revenue_krw_million,
            )
        )
    matrix = np.asarray(design, dtype=float)
    return int(np.linalg.matrix_rank(matrix)) if matrix.size else 0


@dataclass(frozen=True)
class PromotionReadinessResult:
    evidence_id: str
    evaluation_date: date
    policy_id: str
    policy_version: str
    policy_manifest_sha256: str
    structural_method_manifest_sha256: str
    rank_probe_evidence_id: str
    row_count: int
    parameter_count: int
    required_training_rows: int
    additional_training_rows_required: int
    residual_degrees_of_freedom: int
    sample_depth_gate_passed: bool
    rank_probe_ready: bool
    company_product_revenue_reconciliation_certified: bool
    interval_driver_count: int
    closed_interval_driver_count: int
    open_interval_source_texts: tuple[str, ...]
    interval_semantics_classified: bool
    closed_interval_sensitivity_coverage_complete: bool
    lower_design_rank: int | None
    midpoint_design_rank: int | None
    upper_design_rank: int | None
    interval_sensitivity_design_full_rank: bool
    interval_values_are_numeric_source_facts: bool
    interval_sensitivity_is_formal_partial_identification: bool
    interval_sensitivity_can_enable_fit: bool
    estimation_driver_input_ready: bool
    method_version_frozen: bool
    holdout_period: str
    holdout_sealed: bool
    promotion_to_frozen_estimation_candidate_allowed: bool
    fit_attempt_allowed: bool
    holdout_evaluation_allowed: bool
    block_reasons: tuple[str, ...]
    numeric_forecast_enabled: bool = False
    fair_value_estimate_enabled: bool = False
    target_price_enabled: bool = False
    decision_score_enabled: bool = False

    def __post_init__(self) -> None:
        if any(
            not _valid_sha(value)
            for value in (
                self.evidence_id,
                self.policy_manifest_sha256,
                self.structural_method_manifest_sha256,
                self.rank_probe_evidence_id,
            )
        ):
            raise ValueError("Promotion-readiness evidence hashes must be SHA-256")
        if self.required_training_rows < self.parameter_count:
            raise ValueError("Promotion-readiness required row count is invalid")
        if self.additional_training_rows_required != max(
            0, self.required_training_rows - self.row_count
        ):
            raise ValueError("Promotion-readiness row shortfall is inconsistent")
        if self.interval_driver_count != self.row_count * 4:
            raise ValueError("Promotion-readiness driver count is inconsistent")
        if self.closed_interval_driver_count > self.interval_driver_count:
            raise ValueError("Promotion-readiness closed interval count is invalid")
        if self.closed_interval_sensitivity_coverage_complete != (
            self.closed_interval_driver_count == self.interval_driver_count
        ):
            raise ValueError("Promotion-readiness interval coverage is inconsistent")
        if self.interval_values_are_numeric_source_facts:
            raise ValueError("Method interval assumptions cannot become source facts")
        if self.interval_sensitivity_is_formal_partial_identification:
            raise ValueError("Sensitivity diagnostic cannot claim formal partial identification")
        if self.interval_sensitivity_can_enable_fit or self.estimation_driver_input_ready:
            raise ValueError("Interval sensitivity cannot enable estimation in v0.1")
        if self.fit_attempt_allowed or self.holdout_evaluation_allowed:
            raise ValueError("Readiness audit cannot execute fit or holdout")
        if any(
            (
                self.numeric_forecast_enabled,
                self.fair_value_estimate_enabled,
                self.target_price_enabled,
                self.decision_score_enabled,
            )
        ):
            raise ValueError("Promotion-readiness audit exceeded downstream trust boundary")


def build_promotion_readiness(
    policy: PromotionReadinessPolicy,
    method: StructuralProfitabilityMethodContract,
    rank_probe: StructuralRankProbeResult,
    *,
    evaluation_date: date,
) -> PromotionReadinessResult:
    if policy.ticker != method.ticker:
        raise ValueError("Promotion-readiness policy/method ticker mismatch")
    if rank_probe.evaluation_date != evaluation_date:
        raise ValueError("Promotion-readiness rank-probe evaluation date mismatch")
    if rank_probe.method_manifest_sha256 != method.manifest_sha256:
        raise ValueError("Promotion-readiness method binding mismatch")
    if policy.holdout_period != method.holdout_period:
        raise ValueError("Promotion-readiness holdout contract mismatch")

    required_rows = max(
        math.ceil(policy.minimum_rows_per_parameter * rank_probe.parameter_count),
        rank_probe.parameter_count + policy.minimum_residual_degrees_of_freedom,
    )
    residual_dof = max(0, rank_probe.row_count - rank_probe.parameter_count)
    sample_passed = (
        rank_probe.row_count >= required_rows
        and residual_dof >= policy.minimum_residual_degrees_of_freedom
    )

    interval_rows = tuple(_row_intervals(row, policy) for row in rank_probe.rows)
    flat_intervals = tuple(item for row in interval_rows for item in row)
    closed_count = sum(item.closed_interval for item in flat_intervals)
    coverage_complete = closed_count == len(flat_intervals)
    open_texts = tuple(
        dict.fromkeys(item.source_text for item in flat_intervals if not item.closed_interval)
    )
    lower_rank: int | None = None
    midpoint_rank: int | None = None
    upper_rank: int | None = None
    sensitivity_full_rank = False
    if coverage_complete and rank_probe.rows:
        lower_rank = _sensitivity_rank(rank_probe.rows, interval_rows, "lower")
        midpoint_rank = _sensitivity_rank(rank_probe.rows, interval_rows, "midpoint")
        upper_rank = _sensitivity_rank(rank_probe.rows, interval_rows, "upper")
        sensitivity_full_rank = all(
            value == rank_probe.parameter_count
            for value in (lower_rank, midpoint_rank, upper_rank)
        )

    holdout_sealed = (
        policy.holdout_period not in rank_probe.training_periods
        and not rank_probe.holdout_evaluation_allowed
    )
    estimation_driver_input_ready = False
    gate_values = (
        rank_probe.rank_probe_ready,
        rank_probe.company_product_revenue_reconciliation_certified,
        sample_passed,
        coverage_complete,
        sensitivity_full_rank,
        estimation_driver_input_ready,
        method.method_version_frozen,
        holdout_sealed,
    )
    promotion_allowed = all(gate_values)
    reasons: list[str] = []
    if not rank_probe.rank_probe_ready:
        reasons.append("structural_rank_probe_not_ready")
    if not rank_probe.company_product_revenue_reconciliation_certified:
        reasons.append("company_product_revenue_reconciliation_not_certified")
    if not sample_passed:
        reasons.append("historical_sample_depth_insufficient")
    if not coverage_complete:
        reasons.append("open_ended_interval_language_present")
    elif not sensitivity_full_rank:
        reasons.append("closed_interval_sensitivity_design_not_full_rank")
    if not estimation_driver_input_ready:
        reasons.append("estimation_driver_input_not_source_certified")
    if not method.method_version_frozen:
        reasons.append("structural_method_not_frozen")
    if not holdout_sealed:
        reasons.append("holdout_not_sealed")

    stable = {
        "evaluation_date": evaluation_date.isoformat(),
        "policy_manifest_sha256": policy.manifest_sha256,
        "structural_method_manifest_sha256": method.manifest_sha256,
        "rank_probe_evidence_id": rank_probe.evidence_id,
        "row_count": rank_probe.row_count,
        "parameter_count": rank_probe.parameter_count,
        "required_training_rows": required_rows,
        "residual_degrees_of_freedom": residual_dof,
        "sample_depth_gate_passed": sample_passed,
        "closed_interval_driver_count": closed_count,
        "interval_driver_count": len(flat_intervals),
        "open_interval_source_texts": open_texts,
        "lower_design_rank": lower_rank,
        "midpoint_design_rank": midpoint_rank,
        "upper_design_rank": upper_rank,
        "interval_sensitivity_design_full_rank": sensitivity_full_rank,
        "estimation_driver_input_ready": False,
        "method_version_frozen": method.method_version_frozen,
        "holdout_sealed": holdout_sealed,
        "promotion_to_frozen_estimation_candidate_allowed": promotion_allowed,
        "block_reasons": tuple(reasons),
    }
    return PromotionReadinessResult(
        evidence_id=_sha_payload(stable),
        evaluation_date=evaluation_date,
        policy_id=policy.policy_id,
        policy_version=policy.policy_version,
        policy_manifest_sha256=policy.manifest_sha256,
        structural_method_manifest_sha256=method.manifest_sha256,
        rank_probe_evidence_id=rank_probe.evidence_id,
        row_count=rank_probe.row_count,
        parameter_count=rank_probe.parameter_count,
        required_training_rows=required_rows,
        additional_training_rows_required=max(0, required_rows - rank_probe.row_count),
        residual_degrees_of_freedom=residual_dof,
        sample_depth_gate_passed=sample_passed,
        rank_probe_ready=rank_probe.rank_probe_ready,
        company_product_revenue_reconciliation_certified=(
            rank_probe.company_product_revenue_reconciliation_certified
        ),
        interval_driver_count=len(flat_intervals),
        closed_interval_driver_count=closed_count,
        open_interval_source_texts=open_texts,
        interval_semantics_classified=True,
        closed_interval_sensitivity_coverage_complete=coverage_complete,
        lower_design_rank=lower_rank,
        midpoint_design_rank=midpoint_rank,
        upper_design_rank=upper_rank,
        interval_sensitivity_design_full_rank=sensitivity_full_rank,
        interval_values_are_numeric_source_facts=False,
        interval_sensitivity_is_formal_partial_identification=False,
        interval_sensitivity_can_enable_fit=False,
        estimation_driver_input_ready=False,
        method_version_frozen=method.method_version_frozen,
        holdout_period=policy.holdout_period,
        holdout_sealed=holdout_sealed,
        promotion_to_frozen_estimation_candidate_allowed=promotion_allowed,
        fit_attempt_allowed=False,
        holdout_evaluation_allowed=False,
        block_reasons=tuple(reasons),
    )


def load_promotion_readiness_from_rank_probe(
    *,
    evaluation_date: date,
    rank_probe_pointer: str | Path,
    policy_path: str | Path = DEFAULT_PROMOTION_READINESS_POLICY,
    method_path: str | Path = DEFAULT_STRUCTURAL_METHOD_PATH,
) -> PromotionReadinessResult:
    policy = load_promotion_readiness_policy(policy_path)
    method = load_structural_profitability_method(method_path)
    rank_probe = load_structural_rank_probe_report(
        rank_probe_pointer,
        evaluation_date=evaluation_date,
    )
    return build_promotion_readiness(
        policy,
        method,
        rank_probe,
        evaluation_date=evaluation_date,
    )


def promotion_readiness_payload(result: PromotionReadinessResult) -> dict[str, object]:
    payload = asdict(result)
    payload["evaluation_date"] = result.evaluation_date.isoformat()
    return cast(
        dict[str, object],
        json.loads(json.dumps(payload, ensure_ascii=False, sort_keys=True)),
    )


__all__ = [
    "DEFAULT_PROMOTION_READINESS_OUTPUT",
    "DEFAULT_PROMOTION_READINESS_POLICY",
    "DriverIntervalAssumption",
    "MagnitudeBand",
    "PromotionReadinessPolicy",
    "PromotionReadinessResult",
    "build_promotion_readiness",
    "classify_driver_interval",
    "load_promotion_readiness_from_rank_probe",
    "load_promotion_readiness_policy",
    "promotion_readiness_payload",
]
