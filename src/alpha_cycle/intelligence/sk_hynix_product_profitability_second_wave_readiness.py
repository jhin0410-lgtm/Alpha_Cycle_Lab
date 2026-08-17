"""Evaluate source-complete second-wave rows against the existing structural rank design.

This report is rank/sample-depth only. The legacy nine rows still use direction-only driver
semantics while the six second-wave rows have exact numeric issuer driver facts. Therefore a
green readiness report can support method-freeze review, but cannot enable estimation, the
2026Q1 holdout, forecasts, valuation, or decisions.
"""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from datetime import date

import numpy as np

from alpha_cycle.intelligence.sk_hynix_product_profitability_promotion_readiness import (
    PromotionReadinessPolicy,
)
from alpha_cycle.intelligence.sk_hynix_product_profitability_second_wave_closeout import (
    SecondWaveCloseout,
)
from alpha_cycle.intelligence.sk_hynix_product_profitability_second_wave_frontier import (
    SecondWaveFrontier,
)
from alpha_cycle.intelligence.sk_hynix_product_profitability_structural_method import (
    StructuralProfitabilityMethodContract,
    StructuralRankProbeResult,
)


def _sha(payload: object) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode()
    ).hexdigest()


def _sign(value: float) -> float:
    return 1.0 if value > 0 else -1.0 if value < 0 else 0.0


def _condition(matrix: np.ndarray) -> float | None:
    norms = np.linalg.norm(matrix, axis=0)
    if np.any(norms == 0.0):
        return None
    value = float(np.linalg.cond(matrix / norms))
    return value if math.isfinite(value) else None


@dataclass(frozen=True)
class SecondWaveReadiness:
    evidence_id: str
    evaluation_date: date
    base_rank_probe_evidence_id: str
    base_row_count: int
    second_wave_row_count: int
    combined_row_count: int
    parameter_count: int
    required_training_rows: int
    residual_degrees_of_freedom: int
    sample_depth_gate_passed: bool
    combined_design_rank: int
    full_column_rank: bool
    normalized_condition_number: float | None
    company_product_revenue_reconciliation_certified: bool
    exact_numeric_second_wave_driver_count: int
    method_version_frozen: bool
    method_freeze_review_ready: bool
    fit_attempt_allowed: bool
    holdout_evaluation_allowed: bool
    block_reasons: tuple[str, ...]

    def __post_init__(self) -> None:
        if len(self.evidence_id) != 64 or len(self.base_rank_probe_evidence_id) != 64:
            raise ValueError("Second-wave readiness evidence IDs must be SHA-256")
        if self.combined_row_count != self.base_row_count + self.second_wave_row_count:
            raise ValueError("Second-wave readiness row counts are inconsistent")
        if self.residual_degrees_of_freedom != self.combined_row_count - self.parameter_count:
            raise ValueError("Second-wave readiness residual DOF is inconsistent")
        if self.sample_depth_gate_passed != (
            self.combined_row_count >= self.required_training_rows
        ):
            raise ValueError("Second-wave readiness sample-depth flag is inconsistent")
        if self.full_column_rank != (self.combined_design_rank == self.parameter_count):
            raise ValueError("Second-wave readiness rank flag is inconsistent")
        if self.exact_numeric_second_wave_driver_count != self.second_wave_row_count * 4:
            raise ValueError("Second-wave readiness driver count is inconsistent")
        if self.fit_attempt_allowed or self.holdout_evaluation_allowed:
            raise ValueError("Second-wave readiness cannot open fit or holdout")


def build_second_wave_readiness(
    *,
    evaluation_date: date,
    closeout: SecondWaveCloseout,
    frontier: SecondWaveFrontier,
    base_rank_probe: StructuralRankProbeResult,
    method: StructuralProfitabilityMethodContract,
    policy: PromotionReadinessPolicy,
) -> SecondWaveReadiness:
    if not closeout.all_six_source_layers_complete:
        raise ValueError("Second-wave readiness requires six source-complete periods")
    if base_rank_probe.evaluation_date > evaluation_date:
        raise ValueError("Second-wave readiness baseline is from the future")
    if base_rank_probe.method_manifest_sha256 != method.manifest_sha256:
        raise ValueError("Second-wave readiness baseline/method binding diverged")
    holdout_diverged = (
        method.holdout_period != frontier.holdout_period
        or method.holdout_period != policy.holdout_period
    )
    if holdout_diverged:
        raise ValueError("Second-wave readiness holdout binding diverged")

    candidate_by_period = {item.period_id: item for item in frontier.candidates}
    second_terms: list[tuple[float, ...]] = []
    reconciled = base_rank_probe.company_product_revenue_reconciliation_certified
    for period in closeout.periods:
        company = period.company_observation
        recovery = period.product_recovery
        if company is None or recovery is None or recovery.observation is None:
            raise ValueError(
                f"Second-wave readiness lacks recovered source row: {period.period_id}"
            )
        product = recovery.observation
        candidate = candidate_by_period[period.period_id]
        if product.rcept_no != company.rcept_no:
            raise ValueError("Second-wave readiness product/company receipts diverged")
        delta = product.total_revenue_million_krw * 1_000_000 - company.revenue_krw
        reconciled = reconciled and delta == 0
        dram = float(product.dram_revenue_million_krw)
        nand = float(product.nand_revenue_million_krw)
        other = float(product.other_revenue_million_krw)
        drivers = candidate.drivers_qoq_percent
        second_terms.append(
            (
                dram,
                dram * _sign(drivers.dram_asp),
                dram * _sign(drivers.dram_bit_volume),
                nand,
                nand * _sign(drivers.nand_asp),
                nand * _sign(drivers.nand_bit_volume),
                other,
            )
        )

    base_terms = [row.design_terms for row in base_rank_probe.rows]
    matrix = np.asarray([*base_terms, *second_terms], dtype=float)
    rank = int(np.linalg.matrix_rank(matrix))
    p = method.parameter_count
    required = max(
        math.ceil(p * policy.minimum_rows_per_parameter),
        p + policy.minimum_residual_degrees_of_freedom,
    )
    n = len(matrix)
    sample_ok = n >= required
    full_rank = rank == p
    review_ready = sample_ok and full_rank and reconciled and len(second_terms) == 6
    reasons: list[str] = []
    if not sample_ok:
        reasons.append("sample_depth_gate_failed")
    if not full_rank:
        reasons.append("combined_direction_design_not_full_rank")
    if not reconciled:
        reasons.append("company_product_revenue_reconciliation_failed")
    if not method.method_version_frozen:
        reasons.append("method_version_not_frozen")
    reasons.append("mixed_driver_semantics_not_registered_for_estimation")

    stable = {
        "evaluation_date": evaluation_date.isoformat(),
        "base_rank_probe_evidence_id": base_rank_probe.evidence_id,
        "second_wave_periods": [item.period_id for item in closeout.periods],
        "combined_design_rank": rank,
        "required_training_rows": required,
        "reconciled": reconciled,
    }
    return SecondWaveReadiness(
        evidence_id=_sha(stable),
        evaluation_date=evaluation_date,
        base_rank_probe_evidence_id=base_rank_probe.evidence_id,
        base_row_count=len(base_rank_probe.rows),
        second_wave_row_count=len(second_terms),
        combined_row_count=n,
        parameter_count=p,
        required_training_rows=required,
        residual_degrees_of_freedom=n - p,
        sample_depth_gate_passed=sample_ok,
        combined_design_rank=rank,
        full_column_rank=full_rank,
        normalized_condition_number=_condition(matrix),
        company_product_revenue_reconciliation_certified=reconciled,
        exact_numeric_second_wave_driver_count=len(second_terms) * 4,
        method_version_frozen=method.method_version_frozen,
        method_freeze_review_ready=review_ready,
        fit_attempt_allowed=False,
        holdout_evaluation_allowed=False,
        block_reasons=tuple(reasons),
    )


__all__ = ["SecondWaveReadiness", "build_second_wave_readiness"]
