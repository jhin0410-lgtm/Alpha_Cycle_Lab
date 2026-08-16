"""Deterministic precedence for historical SK hynix product-revenue text layouts.

Q1 filings can expose both an explicit product-row table and a looser single-period
revenue presentation in the same consolidated revenue note. When the explicit row
parser succeeds, it is the more structurally constrained source representation and must
win rather than being combined with additional Q1 fallback candidates.
"""

from __future__ import annotations

from alpha_cycle.intelligence.sk_hynix_opendart_historical_product_revenue_fallback import (
    _connected_sections,
    _normalize_lines,
    _q1_revenue_row_candidates,
    _require_historical_spec,
    _row_text_candidate,
)
from alpha_cycle.intelligence.sk_hynix_opendart_q2_product_revenue_certification import (
    PeriodicProductRevenueSpec,
    ProductRevenueMetrics,
)
from alpha_cycle.intelligence.sk_hynix_opendart_q2_product_revenue_table import _normalized


def _resolve_unique(
    candidates: list[ProductRevenueMetrics],
    *,
    family: str,
) -> ProductRevenueMetrics:
    unique = {
        (
            item.unit,
            item.dram_total,
            item.nand_and_solutions,
            item.other_products_services,
            item.reported_company_revenue,
        ): item
        for item in candidates
    }
    if len(unique) != 1:
        raise ValueError(
            "Historical OpenDART product revenue text must resolve uniquely within "
            f"{family}: candidates={len(unique)}"
        )
    return next(iter(unique.values()))


def parse_historical_product_revenue_text_prioritized(
    spec: PeriodicProductRevenueSpec,
    text: str,
) -> ProductRevenueMetrics:
    """Prefer explicit row-layout evidence before considering the Q1 loose fallback."""

    _require_historical_spec(spec)
    lines = _normalize_lines(text)
    if not lines:
        raise ValueError("Historical periodic document text is empty")
    folded = "\n".join(lines).casefold()
    for anchor in spec.expected_identity_anchors:
        if _normalized(anchor) not in folded:
            raise ValueError(f"Historical product revenue anchor missing: {anchor}")

    sections = _connected_sections(lines)
    row_candidates: list[ProductRevenueMetrics] = []
    for section in sections:
        try:
            row_candidates.append(_row_text_candidate(spec, section))
        except ValueError:
            continue
    if row_candidates:
        return _resolve_unique(row_candidates, family="explicit_row_layout")

    q1_candidates: list[ProductRevenueMetrics] = []
    for section in sections:
        q1_candidates.extend(_q1_revenue_row_candidates(spec, section))
    return _resolve_unique(q1_candidates, family="q1_single_period_fallback")


__all__ = ["parse_historical_product_revenue_text_prioritized"]
