"""Exact prefix-witness parser for observed SK hynix historical Q1 raw layouts.

Preserved OpenDART raw-table diagnostics for 2024Q1, 2025Q1, and 2026Q1 show the
same connected disclosure shape:

* table i is the current-quarter product header;
* table i+2 is the prior-quarter product header; and
* table i+2's bounded raw prefix directly contains the current product labels,
  ``수익(매출액)``, four direct current-quarter amounts, then ``전분기``.

The intervening table exists in the source sequence but its internal rendering shape was
not established by the diagnostic evidence.  This parser therefore does not invent a
contract for that table.  It accepts only the exact two-index header spacing and uses the
bounded prefix witness for direct values.  No residual product value is derived.
"""

from __future__ import annotations

import io
import zipfile
from pathlib import PurePosixPath

from alpha_cycle.intelligence.sk_hynix_opendart_historical_product_revenue_fallback import (
    HISTORICAL_PRODUCT_REVENUE_PARSER_ID,
    _accepted,
    _is_q1,
    _metrics,
)
from alpha_cycle.intelligence.sk_hynix_opendart_historical_product_revenue_layout_v2 import (
    _CONNECTED_NOTE_HEADING,
    _nearest_note_heading,
    _nearest_period,
    _unique_header_column,
)
from alpha_cycle.intelligence.sk_hynix_opendart_q2_product_revenue_certification import (
    PeriodicProductRevenueSpec,
    ProductRevenueMetrics,
    _parse_amount,
)
from alpha_cycle.intelligence.sk_hynix_opendart_q2_product_revenue_table import (
    _grid,
    _normalized,
    _RawTable,
    _TableExtractor,
)
from alpha_cycle.intelligence.sk_hynix_opendart_q2_product_revenue_table import (
    _unit as _structured_unit,
)
from alpha_cycle.providers.opendart_documents import _decode_text, _safe_member_name

_TEXT_SUFFIXES = frozenset({".xml", ".html", ".htm", ".xhtml"})
_REVENUE_LABELS = ("수익", "수익(매출액)", "수익 (매출액)")


def _require_bound_q1_spec(spec: PeriodicProductRevenueSpec) -> None:
    if spec.parser_id != HISTORICAL_PRODUCT_REVENUE_PARSER_ID:
        raise ValueError("Historical layout-v4 parser_id is not bound")
    if spec.period_end.year < 2024 or not _is_q1(spec):
        raise ValueError("Historical layout-v4 is limited to observed 2024+ Q1 layouts")


def _canonical_header_columns(
    spec: PeriodicProductRevenueSpec,
    table: _RawTable,
) -> tuple[int, int, int, int]:
    grid = _grid(table)
    columns = (
        _unique_header_column(
            grid,
            spec.product_labels["dram_total"],
            label="DRAM",
        ),
        _unique_header_column(
            grid,
            spec.product_labels["nand_and_solutions"],
            label="NAND",
        ),
        _unique_header_column(
            grid,
            spec.product_labels["other_products_services"],
            label="Other",
        ),
        _unique_header_column(
            grid,
            spec.product_labels["reported_company_revenue"],
            label="Total",
        ),
    )
    if columns != tuple(sorted(columns)):
        raise ValueError("Historical layout-v4 Q1 product header order is not canonical")
    return columns


def _prefix_current_values(
    spec: PeriodicProductRevenueSpec,
    witness: _RawTable,
) -> tuple[float, float, float, float]:
    prefix = witness.prefix_text
    prior = _accepted(("전분기",))
    prior_positions = [
        index for index, token in enumerate(prefix) if _normalized(token) in prior
    ]
    if not prior_positions:
        raise ValueError("Historical layout-v4 Q1 witness lacks prior-quarter boundary")
    prior_index = prior_positions[-1]

    revenue = _accepted(_REVENUE_LABELS)
    revenue_positions = [
        index
        for index, token in enumerate(prefix[:prior_index])
        if _normalized(token) in revenue
    ]
    if not revenue_positions:
        raise ValueError("Historical layout-v4 Q1 witness lacks current revenue label")
    revenue_index = revenue_positions[-1]

    product_window = prefix[max(0, revenue_index - 8) : revenue_index]
    label_sets = (
        ("dram", _accepted(spec.product_labels["dram_total"])),
        ("nand", _accepted(spec.product_labels["nand_and_solutions"])),
        ("other", _accepted(spec.product_labels["other_products_services"])),
        ("total", _accepted(spec.product_labels["reported_company_revenue"])),
    )
    categories: list[str] = []
    for token in product_window:
        normalized = _normalized(token)
        matches = [name for name, accepted in label_sets if normalized in accepted]
        if len(matches) > 1:
            raise ValueError("Historical layout-v4 Q1 product label is ambiguous")
        if matches:
            categories.append(matches[0])
    if tuple(categories[-4:]) != ("dram", "nand", "other", "total"):
        raise ValueError("Historical layout-v4 Q1 witness lacks canonical product labels")

    amount_tokens = prefix[revenue_index + 1 : prior_index]
    if len(amount_tokens) != 4:
        raise ValueError(
            "Historical layout-v4 Q1 witness requires exactly four tokens between "
            f"revenue and prior boundary: count={len(amount_tokens)}"
        )
    amounts = tuple(_parse_amount(token) for token in amount_tokens)
    if any(amount is None for amount in amounts):
        raise ValueError("Historical layout-v4 Q1 witness contains a non-numeric amount")
    return (
        float(amounts[0]),
        float(amounts[1]),
        float(amounts[2]),
        float(amounts[3]),
    )


def _prefix_witness_metrics(
    spec: PeriodicProductRevenueSpec,
    current_header: _RawTable,
    prior_header: _RawTable,
) -> ProductRevenueMetrics:
    heading = _nearest_note_heading(current_header)
    if heading is None or _CONNECTED_NOTE_HEADING.fullmatch(heading) is None:
        raise ValueError("Historical layout-v4 Q1 current header is outside connected note")
    if _nearest_period(current_header) != "당분기":
        raise ValueError("Historical layout-v4 Q1 current header is outside current quarter")
    if _nearest_note_heading(prior_header) != heading:
        raise ValueError("Historical layout-v4 Q1 header pair does not share connected note")
    if _nearest_period(prior_header) != "전분기":
        raise ValueError("Historical layout-v4 Q1 witness is not the prior-quarter header")

    current_columns = _canonical_header_columns(spec, current_header)
    prior_columns = _canonical_header_columns(spec, prior_header)
    if current_columns != prior_columns:
        raise ValueError("Historical layout-v4 Q1 current/prior header columns disagree")

    witnessed = _prefix_current_values(spec, prior_header)
    current_grid = _grid(current_header)
    unit, scale = _structured_unit(current_header, current_grid)
    return _metrics(
        unit=unit,
        scale=scale,
        dram=witnessed[0],
        nand=witnessed[1],
        other=witnessed[2],
        total=witnessed[3],
    )


def _resolve_unique(candidates: list[ProductRevenueMetrics]) -> ProductRevenueMetrics:
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
            "Historical layout-v4 q1_prefix_witness_archive must resolve uniquely: "
            f"candidates={len(unique)}"
        )
    return next(iter(unique.values()))


def parse_historical_product_revenue_archive_v4(
    spec: PeriodicProductRevenueSpec,
    archive_bytes: bytes,
) -> ProductRevenueMetrics:
    """Parse the exact connected Q1 header/prefix witness family from raw ZIP bytes."""

    _require_bound_q1_spec(spec)
    try:
        archive = zipfile.ZipFile(io.BytesIO(archive_bytes))
    except zipfile.BadZipFile as exc:
        raise ValueError("Historical layout-v4 source is not a ZIP") from exc

    candidates: list[ProductRevenueMetrics] = []
    with archive:
        for info in archive.infolist():
            if info.is_dir():
                continue
            safe_name = _safe_member_name(info.filename)
            if PurePosixPath(safe_name).suffix.casefold() not in _TEXT_SUFFIXES:
                continue
            decoded, _encoding = _decode_text(archive.read(info))
            parser = _TableExtractor()
            parser.feed(decoded)
            parser.close()
            for index, current_header in enumerate(parser.tables):
                if index + 2 >= len(parser.tables):
                    continue
                try:
                    candidates.append(
                        _prefix_witness_metrics(
                            spec,
                            current_header,
                            parser.tables[index + 2],
                        )
                    )
                except ValueError:
                    continue
    return _resolve_unique(candidates)


__all__ = ["parse_historical_product_revenue_archive_v4"]
