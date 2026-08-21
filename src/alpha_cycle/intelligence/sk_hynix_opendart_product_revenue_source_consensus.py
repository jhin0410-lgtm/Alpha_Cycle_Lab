"""Reconcile normalized text with authoritative OpenDART product-revenue structure.

For current and frozen-anchor periods, both normalized text and raw archive parsers must
produce the same metrics. Older historical filings can lose table structure during text
normalization; for those periods only, the raw archive parser is authoritative and the
normalized text is retained as a local label/unit/value witness. This module never chooses
values from the text witness and never relaxes frozen 2021-2022 source anchors.
"""

from __future__ import annotations

from alpha_cycle.intelligence.sk_hynix_opendart_historical_product_revenue_fallback import (
    HISTORICAL_PRODUCT_REVENUE_PARSER_ID,
)
from alpha_cycle.intelligence.sk_hynix_opendart_pre2023_certified_replay import (
    is_pre2023_certified_product_revenue_period,
)
from alpha_cycle.intelligence.sk_hynix_opendart_product_revenue_parser_dispatch import (
    parse_periodic_product_revenue_archive,
    parse_periodic_product_revenue_text,
)
from alpha_cycle.intelligence.sk_hynix_opendart_q2_product_revenue_certification import (
    PeriodicProductRevenueSpec,
    ProductRevenueMetrics,
    _parse_amount,
)

_UNIT_SCALES_TO_KRW_MILLION = {"백만원": 1.0, "억원": 100.0}
_BLOCK_IDS = (
    "dram_total",
    "nand_and_solutions",
    "other_products_services",
    "reported_company_revenue",
)


def _normalized(value: str) -> str:
    return " ".join(value.replace("\u00a0", " ").split()).casefold()


def _lines(text: str) -> tuple[str, ...]:
    return tuple(
        " ".join(line.replace("\u00a0", " ").split())
        for line in text.splitlines()
        if line.strip()
    )


def _label_matches(value: str, labels: tuple[str, ...]) -> bool:
    normalized = _normalized(value)
    return normalized in {_normalized(label) for label in labels}


def _next_label(
    lines: tuple[str, ...],
    labels: tuple[str, ...],
    *,
    start: int,
    stop: int,
) -> int | None:
    return next(
        (
            index
            for index in range(start, min(stop, len(lines)))
            if _label_matches(lines[index], labels)
        ),
        None,
    )


def _segment_reproduces_metric(
    lines: tuple[str, ...],
    *,
    start: int,
    stop: int,
    metric_krw_million: float,
    scale: float,
) -> bool:
    for token in lines[start:stop]:
        amount = _parse_amount(token)
        if amount is None:
            continue
        if abs((amount * scale) - metric_krw_million) <= 0.5:
            return True
    return False


def verify_historical_product_revenue_text_witness(
    spec: PeriodicProductRevenueSpec,
    text: str,
    metrics: ProductRevenueMetrics,
) -> None:
    """Require one coherent normalized-text block to reproduce archive-derived values."""

    lines = _lines(text)
    if not lines:
        raise ValueError("Historical product revenue normalized-text witness is empty")
    folded = "\n".join(lines).casefold()
    for anchor in spec.expected_identity_anchors:
        if _normalized(anchor) not in folded:
            raise ValueError(
                f"Historical product revenue normalized-text anchor missing: {anchor}"
            )

    expected = {
        "dram_total": metrics.dram_total,
        "nand_and_solutions": metrics.nand_and_solutions,
        "other_products_services": metrics.other_products_services,
        "reported_company_revenue": metrics.reported_company_revenue,
    }
    dram_indices = [
        index
        for index, line in enumerate(lines)
        if _label_matches(line, spec.product_labels["dram_total"])
    ]
    for dram_index in dram_indices:
        search_stop = min(len(lines), dram_index + 120)
        nand_index = _next_label(
            lines,
            spec.product_labels["nand_and_solutions"],
            start=dram_index + 1,
            stop=search_stop,
        )
        if nand_index is None:
            continue
        other_index = _next_label(
            lines,
            spec.product_labels["other_products_services"],
            start=nand_index + 1,
            stop=search_stop,
        )
        if other_index is None:
            continue
        total_index = _next_label(
            lines,
            spec.product_labels["reported_company_revenue"],
            start=other_index + 1,
            stop=search_stop,
        )
        if total_index is None:
            continue

        witness_start = max(0, dram_index - 48)
        witness_end = min(len(lines), total_index + 32)
        unit_scales = {
            scale
            for marker, scale in _UNIT_SCALES_TO_KRW_MILLION.items()
            if any(marker in line for line in lines[witness_start:witness_end])
        }
        if not unit_scales:
            continue
        segment_bounds = {
            "dram_total": (dram_index + 1, nand_index),
            "nand_and_solutions": (nand_index + 1, other_index),
            "other_products_services": (other_index + 1, total_index),
            "reported_company_revenue": (total_index + 1, witness_end),
        }
        for scale in unit_scales:
            if all(
                _segment_reproduces_metric(
                    lines,
                    start=segment_bounds[block_id][0],
                    stop=segment_bounds[block_id][1],
                    metric_krw_million=expected[block_id],
                    scale=scale,
                )
                for block_id in _BLOCK_IDS
            ):
                return

    raise ValueError(
        "Historical product revenue normalized-text witness does not reproduce one "
        "coherent DRAM/NAND/Other/Total block from archive-derived metrics"
    )


def parse_periodic_product_revenue_source_consensus(
    spec: PeriodicProductRevenueSpec,
    text: str,
    archive_bytes: bytes,
) -> ProductRevenueMetrics:
    """Return metrics only when text/archive evidence satisfies the applicable contract."""

    try:
        text_metrics = parse_periodic_product_revenue_text(spec, text)
    except ValueError as text_error:
        historical_unanchored = (
            spec.parser_id == HISTORICAL_PRODUCT_REVENUE_PARSER_ID
            and not is_pre2023_certified_product_revenue_period(spec)
        )
        if not historical_unanchored:
            raise
        try:
            structured_metrics = parse_periodic_product_revenue_archive(spec, archive_bytes)
        except ValueError as archive_error:
            raise ValueError(
                "Historical OpenDART product revenue failed normalized text and authoritative "
                f"archive parsing: text={text_error}; archive={archive_error}"
            ) from archive_error
        try:
            verify_historical_product_revenue_text_witness(spec, text, structured_metrics)
        except ValueError as witness_error:
            raise ValueError(
                "Historical OpenDART product revenue archive parsed, but normalized-text "
                f"witness failed: text={text_error}; witness={witness_error}"
            ) from witness_error
        return structured_metrics

    structured_metrics = parse_periodic_product_revenue_archive(spec, archive_bytes)
    if structured_metrics != text_metrics:
        raise ValueError(
            "OpenDART normalized text and certified product structure disagree: "
            f"text={text_metrics} structured={structured_metrics}"
        )
    return text_metrics


__all__ = [
    "parse_periodic_product_revenue_source_consensus",
    "verify_historical_product_revenue_text_witness",
]
