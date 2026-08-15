"""Semantic replay for SK hynix 2Q26 OpenDART product-revenue tables.

The live half-year XML does not guarantee that the product header grid and its revenue
row are adjacent HTML tables or share identical physical column geometry. This parser
therefore binds them by source semantics inside one current-period consolidated revenue
note: a unique DRAM/NAND/Other/Total header followed by a unique ``수익`` table carrying
exactly eight direct three-month/cumulative amounts.

No residual allocation is permitted. The four current-quarter values are read directly
from the source row in the product order certified by the header and must reconcile.
"""

from __future__ import annotations

import io
import re
import zipfile
from pathlib import PurePosixPath

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
_CURRENT_MARKERS = ("당반기", "당분기", "당기")
_PRIOR_MARKERS = ("전반기", "전분기", "전기")
_REVENUE_LABELS = ("수익", "수익(매출액)", "수익 (매출액)")
_NOTE_HEADING = re.compile(r"^\s*\d+\.\s*매출액(?:\s*\(연결\))?\s*$")
_PRODUCT_KEYS = ("dram", "nand", "other", "total")


def _accepted(labels: tuple[str, ...]) -> frozenset[str]:
    return frozenset(_normalized(value) for value in labels)


def _nearest_heading(table: _RawTable) -> str | None:
    for value in reversed(table.prefix_text):
        normalized = " ".join(value.split())
        if _NOTE_HEADING.fullmatch(normalized):
            return normalized
    return None


def _nearest_period(table: _RawTable) -> str | None:
    current = {_normalized(value): value for value in _CURRENT_MARKERS}
    prior = {_normalized(value): value for value in _PRIOR_MARKERS}
    for value in reversed(table.prefix_text):
        normalized = _normalized(value)
        if normalized in current:
            return current[normalized]
        if normalized in prior:
            return prior[normalized]
    return None


def _header_product_order(
    spec: PeriodicProductRevenueSpec,
    table: _RawTable,
) -> tuple[str, ...]:
    heading = _nearest_heading(table)
    if heading is None or "(연결)" not in heading.replace(" ", ""):
        raise ValueError("OpenDART product header is outside consolidated revenue note")
    if _nearest_period(table) not in _CURRENT_MARKERS:
        raise ValueError("OpenDART product header is outside current period")

    grid = _grid(table)
    width = max((len(row) for row in grid), default=0)
    label_sets = {
        "dram": _accepted(spec.product_labels["dram_total"]),
        "nand": _accepted(spec.product_labels["nand_and_solutions"]),
        "other": _accepted(spec.product_labels["other_products_services"]),
        "total": _accepted(spec.product_labels["reported_company_revenue"]),
    }
    three_month_columns: list[tuple[int, str]] = []
    for column in range(width):
        tokens = tuple(
            row[column]
            for row in grid
            if column < len(row) and row[column].strip()
        )
        normalized = tuple(_normalized(token) for token in tokens)
        if _normalized("3개월") not in normalized or _normalized("누적") in normalized:
            continue
        matched = [
            key
            for key, accepted in label_sets.items()
            if any(token in accepted for token in normalized)
        ]
        if len(matched) == 1:
            three_month_columns.append((column, matched[0]))

    ordered = tuple(key for _column, key in sorted(three_month_columns))
    if ordered != _PRODUCT_KEYS:
        raise ValueError(
            "OpenDART product header does not uniquely certify DRAM/NAND/Other/Total order: "
            f"order={ordered}"
        )
    return ordered


def _data_amounts(table: _RawTable) -> tuple[float, ...]:
    grid = _grid(table)
    accepted = _accepted(_REVENUE_LABELS)
    labels: list[tuple[int, int]] = []
    for row_index, row in enumerate(grid):
        for column, value in enumerate(row):
            if _normalized(value) in accepted:
                labels.append((row_index, column))
    if len(labels) != 1:
        raise ValueError("OpenDART product data table requires one revenue label")

    row_index, column = labels[0]
    same_row = [
        amount
        for token in grid[row_index][column + 1 :]
        if (amount := _parse_amount(token)) is not None
    ]
    if len(same_row) == 8:
        return tuple(same_row)

    flattened: list[float] = []
    seen_label = False
    for row in grid:
        for token in row:
            if not seen_label:
                if _normalized(token) in accepted:
                    seen_label = True
                continue
            amount = _parse_amount(token)
            if amount is not None:
                flattened.append(amount)
    if len(flattened) != 8:
        raise ValueError(
            "OpenDART product data table must expose exactly eight direct amounts: "
            f"count={len(flattened)}"
        )
    return tuple(flattened)


def _metrics(
    spec: PeriodicProductRevenueSpec,
    header: _RawTable,
    data: _RawTable,
) -> ProductRevenueMetrics:
    order = _header_product_order(spec, header)
    if order != _PRODUCT_KEYS:
        raise ValueError("OpenDART product order is not canonical")

    header_heading = _nearest_heading(header)
    data_heading = _nearest_heading(data)
    if data_heading is not None and _normalized(data_heading) != _normalized(header_heading or ""):
        raise ValueError("OpenDART product data crosses a revenue-note boundary")
    data_period = _nearest_period(data)
    if data_period is not None and data_period not in _CURRENT_MARKERS:
        raise ValueError("OpenDART product data crosses into prior period")

    amounts = _data_amounts(data)
    unit, scale = _structured_unit(header, _grid(header))
    dram = amounts[0] * scale
    nand = amounts[2] * scale
    other = amounts[4] * scale
    total = amounts[6] * scale
    direct_sum = dram + nand + other
    return ProductRevenueMetrics(
        unit=unit,
        dram_total=dram,
        nand_and_solutions=nand,
        other_products_services=other,
        reported_company_revenue=total,
        direct_sum=direct_sum,
        reconciliation_delta=direct_sum - total,
    )


def _table_candidates(
    spec: PeriodicProductRevenueSpec,
    tables: list[_RawTable],
) -> tuple[ProductRevenueMetrics, ...]:
    parsed: list[ProductRevenueMetrics] = []
    for header_index, header in enumerate(tables):
        try:
            _header_product_order(spec, header)
        except ValueError:
            continue
        heading = _nearest_heading(header)
        if heading is None:
            continue

        # Search the complete semantic note scope.  Physical distance between the
        # header and data row is intentionally irrelevant; a new revenue-note heading
        # terminates the search and prevents cross-note pairing.
        for data in tables[header_index:]:
            data_heading = _nearest_heading(data)
            if data_heading is not None and _normalized(data_heading) != _normalized(heading):
                break
            try:
                parsed.append(_metrics(spec, header, data))
            except ValueError:
                continue
    return tuple(parsed)


def _diagnostic_counts(
    spec: PeriodicProductRevenueSpec,
    tables: list[_RawTable],
) -> tuple[int, int]:
    headers = 0
    revenue_rows = 0
    for table in tables:
        try:
            _header_product_order(spec, table)
            headers += 1
        except ValueError:
            pass
        try:
            _data_amounts(table)
            revenue_rows += 1
        except ValueError:
            pass
    return headers, revenue_rows


def parse_periodic_product_revenue_archive(
    spec: PeriodicProductRevenueSpec,
    archive_bytes: bytes,
) -> ProductRevenueMetrics:
    """Replay the unique current consolidated product revenue from archived ZIP bytes."""

    try:
        archive = zipfile.ZipFile(io.BytesIO(archive_bytes))
    except zipfile.BadZipFile as exc:
        raise ValueError("OpenDART product-revenue semantic replay source is not a ZIP") from exc

    candidates: list[ProductRevenueMetrics] = []
    total_tables = 0
    header_candidates = 0
    revenue_row_candidates = 0
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
            total_tables += len(parser.tables)
            headers, rows = _diagnostic_counts(spec, parser.tables)
            header_candidates += headers
            revenue_row_candidates += rows
            candidates.extend(_table_candidates(spec, parser.tables))

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
            "OpenDART semantic current-quarter product revenue must resolve uniquely: "
            f"candidates={len(unique)} total_tables={total_tables} "
            f"current_consolidated_headers={header_candidates} "
            f"eight_amount_revenue_tables={revenue_row_candidates}"
        )
    return next(iter(unique.values()))


__all__ = ["parse_periodic_product_revenue_archive"]
