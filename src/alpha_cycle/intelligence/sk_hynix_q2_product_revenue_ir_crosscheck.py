"""Cross-check direct OpenDART product revenue against certified SK hynix Q2 IR shares."""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass

from alpha_cycle.intelligence.sk_hynix_official_ir_q2_product_assignment_certification import (
    OfficialIrQ2ProductAssignmentCertification,
)
from alpha_cycle.intelligence.sk_hynix_opendart_q2_product_revenue_certification import (
    OpenDartPeriodicProductRevenueCertification,
)


@dataclass(frozen=True)
class ProductRevenueIrCrosscheck:
    evidence_id: str
    product_revenue_evidence_id: str
    ir_assignment_evidence_id: str
    dram_direct_share_percent: float
    nand_direct_share_percent: float
    other_direct_share_percent: float
    dram_ir_rounded_percent: int
    nand_ir_rounded_percent: int
    dram_rounded_match: bool
    nand_rounded_match: bool
    others_presence_match: bool
    period_match: bool
    crosscheck_certified: bool
    product_revenue_promotion_ready: bool
    allocation_resolver_registered: bool = False
    product_profitability_certified: bool = False
    numeric_forecast_enabled: bool = False
    decision_score_enabled: bool = False

    def __post_init__(self) -> None:
        if len(self.evidence_id) != 64:
            raise ValueError("Product revenue IR cross-check evidence_id must be SHA-256")
        expected = (
            self.dram_rounded_match
            and self.nand_rounded_match
            and self.others_presence_match
            and self.period_match
        )
        if self.crosscheck_certified != expected:
            raise ValueError("Product revenue IR cross-check certification flags diverged")
        if self.product_revenue_promotion_ready != self.crosscheck_certified:
            raise ValueError("Product revenue promotion readiness must follow cross-check")
        if (
            self.allocation_resolver_registered
            or self.product_profitability_certified
            or self.numeric_forecast_enabled
            or self.decision_score_enabled
        ):
            raise ValueError("Product revenue IR cross-check exceeds its trust boundary")


def _round_percent(value: float) -> int:
    return int(math.floor(value + 0.5))


def build_product_revenue_ir_crosscheck(
    product_revenue: OpenDartPeriodicProductRevenueCertification,
    ir_assignment: OfficialIrQ2ProductAssignmentCertification,
) -> ProductRevenueIrCrosscheck:
    if product_revenue.ticker != "000660":
        raise ValueError("Product revenue IR cross-check only supports SK hynix")
    if not product_revenue.product_revenue_baseline_eligible:
        raise ValueError("Direct product revenue is not baseline eligible")
    if not ir_assignment.product_assignment_certified:
        raise ValueError("Official IR product assignment is not certified")
    if ir_assignment.other_share_percent is not None or ir_assignment.other_zero_certified:
        raise ValueError("Official IR Other numeric share must remain unresolved")

    total = product_revenue.metrics.reported_company_revenue
    dram_share = 100.0 * product_revenue.metrics.dram_total / total
    nand_share = 100.0 * product_revenue.metrics.nand_and_solutions / total
    other_share = 100.0 * product_revenue.metrics.other_products_services / total
    dram_ir = int(ir_assignment.dram_share_percent)
    nand_ir = int(ir_assignment.nand_share_percent)
    dram_match = _round_percent(dram_share) == dram_ir
    nand_match = _round_percent(nand_share) == nand_ir
    others_match = (
        ir_assignment.others_segment_present
        and product_revenue.metrics.other_products_services > 0.0
    )
    period_match = (
        product_revenue.period_start.isoformat() == "2026-04-01"
        and product_revenue.period_end.isoformat() == "2026-06-30"
        and ir_assignment.current_period_label == "'26 Q2"
    )
    certified = dram_match and nand_match and others_match and period_match
    payload: dict[str, object] = {
        "product_revenue_evidence_id": product_revenue.evidence_id,
        "ir_assignment_evidence_id": ir_assignment.evidence_id,
        "dram_direct_share_percent": dram_share,
        "nand_direct_share_percent": nand_share,
        "other_direct_share_percent": other_share,
        "dram_ir_rounded_percent": dram_ir,
        "nand_ir_rounded_percent": nand_ir,
        "dram_rounded_match": dram_match,
        "nand_rounded_match": nand_match,
        "others_presence_match": others_match,
        "period_match": period_match,
        "crosscheck_certified": certified,
        "product_revenue_promotion_ready": certified,
        "allocation_resolver_registered": False,
        "product_profitability_certified": False,
        "numeric_forecast_enabled": False,
        "decision_score_enabled": False,
    }
    evidence_id = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return ProductRevenueIrCrosscheck(
        evidence_id=evidence_id,
        product_revenue_evidence_id=product_revenue.evidence_id,
        ir_assignment_evidence_id=ir_assignment.evidence_id,
        dram_direct_share_percent=dram_share,
        nand_direct_share_percent=nand_share,
        other_direct_share_percent=other_share,
        dram_ir_rounded_percent=dram_ir,
        nand_ir_rounded_percent=nand_ir,
        dram_rounded_match=dram_match,
        nand_rounded_match=nand_match,
        others_presence_match=others_match,
        period_match=period_match,
        crosscheck_certified=certified,
        product_revenue_promotion_ready=certified,
        allocation_resolver_registered=False,
        product_profitability_certified=False,
        numeric_forecast_enabled=False,
        decision_score_enabled=False,
    )


__all__ = ["ProductRevenueIrCrosscheck", "build_product_revenue_ir_crosscheck"]
