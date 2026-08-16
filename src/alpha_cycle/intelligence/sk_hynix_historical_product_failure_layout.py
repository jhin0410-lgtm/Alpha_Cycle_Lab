"""Summarize preserved historical SK hynix product-revenue parser failures offline.

This module does not parse or promote product revenue. It reads already-preserved,
hash-verified failure diagnostics and emits compact structural signatures so historical
OpenDART layout families can be fixed from evidence instead of guesswork.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from pathlib import Path

from alpha_cycle.intelligence.sk_hynix_historical_product_failure_diagnostics import (
    HistoricalProductRevenueFailureDiagnostic,
)
from alpha_cycle.intelligence.sk_hynix_opendart_q2_product_revenue_certification import (
    PeriodicProductRevenueSpec,
)
from alpha_cycle.intelligence.sk_hynix_opendart_q2_product_revenue_table import _normalized

_CURRENT_MARKERS = ("당반기", "당분기", "당기")
_PRIOR_MARKERS = ("전반기", "전분기", "전기")
_REVENUE_LABELS = ("수익", "수익(매출액)", "수익 (매출액)")
_NOTE_HEADING = re.compile(r"^\s*\d+\.\s*.+$")
_MAX_HEADINGS = 16
_MAX_EXCERPT_LINES = 36
_MAX_EXCERPT_LINE_CHARS = 180


def _lines(path: str) -> tuple[str, ...]:
    text = Path(path).read_bytes().decode("utf-8")
    return tuple(
        " ".join(line.replace("\u00a0", " ").split())
        for line in text.splitlines()
        if line.strip()
    )


def _accepted(values: tuple[str, ...]) -> frozenset[str]:
    return frozenset(_normalized(value) for value in values)


def _label_count(lines: tuple[str, ...], labels: tuple[str, ...]) -> int:
    accepted = _accepted(labels)
    return sum(1 for line in lines if _normalized(line) in accepted)


def _marker_values(lines: tuple[str, ...], markers: tuple[str, ...]) -> tuple[str, ...]:
    accepted = {_normalized(marker): marker for marker in markers}
    observed: list[str] = []
    for line in lines:
        marker = accepted.get(_normalized(line))
        if marker is not None and marker not in observed:
            observed.append(marker)
    return tuple(observed)


def _excerpt(lines: tuple[str, ...], spec: PeriodicProductRevenueSpec) -> tuple[str, ...]:
    dram = _accepted(spec.product_labels["dram_total"])
    positions = [index for index, line in enumerate(lines) if _normalized(line) in dram]
    if not positions:
        return ()
    center = positions[0]
    half = _MAX_EXCERPT_LINES // 2
    start = max(0, center - half)
    end = min(len(lines), start + _MAX_EXCERPT_LINES)
    return tuple(line[:_MAX_EXCERPT_LINE_CHARS] for line in lines[start:end])


@dataclass(frozen=True)
class HistoricalProductFailureLayoutSignature:
    period_id: str
    error_type: str
    error: str
    revenue_note_headings: tuple[str, ...]
    connected_revenue_note_headings: tuple[str, ...]
    current_period_markers: tuple[str, ...]
    prior_period_markers: tuple[str, ...]
    three_month_count: int
    cumulative_count: int
    revenue_label_count: int
    dram_label_count: int
    nand_label_count: int
    other_label_count: int
    total_label_count: int
    relevant_excerpt: tuple[str, ...]
    source_fact_promoted: bool = False

    def as_dict(self) -> dict[str, object]:
        return asdict(self)


def build_failure_layout_signature(
    diagnostic: HistoricalProductRevenueFailureDiagnostic,
    spec: PeriodicProductRevenueSpec,
) -> HistoricalProductFailureLayoutSignature:
    """Build a bounded structural signature from one verified failure bundle."""

    lines = _lines(diagnostic.normalized_text_path)
    note_headings = tuple(
        line
        for line in lines
        if _NOTE_HEADING.fullmatch(line) is not None and "매출" in line
    )[:_MAX_HEADINGS]
    connected = tuple(line for line in note_headings if "연결" in line)
    return HistoricalProductFailureLayoutSignature(
        period_id=diagnostic.period_id,
        error_type=diagnostic.error_type,
        error=diagnostic.error,
        revenue_note_headings=note_headings,
        connected_revenue_note_headings=connected,
        current_period_markers=_marker_values(lines, _CURRENT_MARKERS),
        prior_period_markers=_marker_values(lines, _PRIOR_MARKERS),
        three_month_count=sum(1 for line in lines if _normalized(line) == _normalized("3개월")),
        cumulative_count=sum(1 for line in lines if _normalized(line) == _normalized("누적")),
        revenue_label_count=_label_count(lines, _REVENUE_LABELS),
        dram_label_count=_label_count(lines, spec.product_labels["dram_total"]),
        nand_label_count=_label_count(lines, spec.product_labels["nand_and_solutions"]),
        other_label_count=_label_count(lines, spec.product_labels["other_products_services"]),
        total_label_count=_label_count(lines, spec.product_labels["reported_company_revenue"]),
        relevant_excerpt=_excerpt(lines, spec),
    )


__all__ = [
    "HistoricalProductFailureLayoutSignature",
    "build_failure_layout_signature",
]
