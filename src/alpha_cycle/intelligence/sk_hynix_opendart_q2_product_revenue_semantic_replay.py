"""Semantic replay for SK hynix 2Q26 OpenDART product revenue.

The live half-year XML does not guarantee that the product header grid, the ``수익``
label, and its eight three-month/cumulative amounts live in one HTML table. This parser
therefore uses two independent views over the archived official bytes:

* table geometry certifies the unique current-period consolidated
  DRAM/NAND/Other/Total product order and unit;
* a raw-source text-token replay reconstructs the revenue row across arbitrary table or
  paragraph boundaries inside the same consolidated revenue note.

A candidate is accepted only when both the current-quarter and cumulative product sums
reconcile to their directly reported totals. The capture layer then additionally requires
this raw-source replay to equal the independently normalized-text parse.
"""

from __future__ import annotations

import io
import re
import zipfile
from html.parser import HTMLParser
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
_MAX_NUMBERS_AFTER_REVENUE_LABEL = 64
_RECONCILIATION_TOLERANCE = 0.5


class _SourceTokenExtractor(HTMLParser):
    """Preserve raw document text-token order without relying on HTML table grouping."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.tokens: list[str] = []

    def handle_data(self, data: str) -> None:
        text = " ".join(data.replace("\u00a0", " ").split())
        if text:
            self.tokens.append(text)


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


def _flatten_table_tokens(table: _RawTable) -> tuple[str, ...]:
    """Read raw cell order without expanding rowspan/colspan geometry.

    Geometry is a trust anchor only for the unique product header. Revenue labels and
    amounts may live in arbitrary helper/data tables, so unrelated span layouts must not
    abort the semantic note stream.
    """

    return tuple(
        cell.text
        for row in table.rows
        for cell in row
        if cell.text.strip()
    )


def _same_note_current_period_scope(
    tables: list[_RawTable],
    *,
    header_index: int,
    heading: str,
) -> tuple[_RawTable, ...]:
    scoped: list[_RawTable] = []
    normalized_heading = _normalized(heading)
    for table in tables[header_index:]:
        table_heading = _nearest_heading(table)
        if table_heading is not None and _normalized(table_heading) != normalized_heading:
            break
        period = _nearest_period(table)
        if period in _PRIOR_MARKERS:
            break
        scoped.append(table)
    return tuple(scoped)


def _reconciles(values: tuple[float, ...]) -> bool:
    if len(values) != 8:
        return False
    current_delta = values[0] + values[2] + values[4] - values[6]
    cumulative_delta = values[1] + values[3] + values[5] - values[7]
    return (
        abs(current_delta) <= _RECONCILIATION_TOLERANCE
        and abs(cumulative_delta) <= _RECONCILIATION_TOLERANCE
    )


def _metrics_from_window(
    *,
    unit: str,
    scale: float,
    values: tuple[float, ...],
) -> ProductRevenueMetrics:
    dram = values[0] * scale
    nand = values[2] * scale
    other = values[4] * scale
    total = values[6] * scale
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


def _windows_after_revenue_label(
    tokens: tuple[str, ...],
    *,
    unit: str,
    scale: float,
) -> tuple[ProductRevenueMetrics, ...]:
    accepted_revenue = _accepted(_REVENUE_LABELS)
    period_markers = _accepted((*_CURRENT_MARKERS, *_PRIOR_MARKERS))
    parsed: list[ProductRevenueMetrics] = []
    for position, token in enumerate(tokens):
        if _normalized(token) not in accepted_revenue:
            continue
        numeric_values: list[float] = []
        for value in tokens[position + 1 :]:
            normalized = _normalized(value)
            if normalized in accepted_revenue or normalized in period_markers:
                break
            amount = _parse_amount(value)
            if amount is None:
                continue
            numeric_values.append(amount)
            if len(numeric_values) >= _MAX_NUMBERS_AFTER_REVENUE_LABEL:
                break
        for offset in range(max(0, len(numeric_values) - 7)):
            window = tuple(numeric_values[offset : offset + 8])
            if not _reconciles(window):
                continue
            try:
                parsed.append(
                    _metrics_from_window(unit=unit, scale=scale, values=window)
                )
            except ValueError:
                continue
    return tuple(parsed)


def _table_stream_candidates(
    spec: PeriodicProductRevenueSpec,
    *,
    header: _RawTable,
    scoped_tables: tuple[_RawTable, ...],
) -> tuple[ProductRevenueMetrics, ...]:
    if _header_product_order(spec, header) != _PRODUCT_KEYS:
        raise ValueError("OpenDART product order is not canonical")
    unit, scale = _structured_unit(header, _grid(header))
    tokens = tuple(
        token for table in scoped_tables for token in _flatten_table_tokens(table)
    )
    return _windows_after_revenue_label(tokens, unit=unit, scale=scale)


def _product_header_sequence_present(
    spec: PeriodicProductRevenueSpec,
    tokens: tuple[str, ...],
    *,
    before: int,
) -> bool:
    label_sets = {
        "dram": _accepted(spec.product_labels["dram_total"]),
        "nand": _accepted(spec.product_labels["nand_and_solutions"]),
        "other": _accepted(spec.product_labels["other_products_services"]),
        "total": _accepted(spec.product_labels["reported_company_revenue"]),
    }
    observed: list[str] = []
    for token in tokens[:before]:
        normalized = _normalized(token)
        matched = [key for key, labels in label_sets.items() if normalized in labels]
        if len(matched) == 1 and (not observed or observed[-1] != matched[0]):
            observed.append(matched[0])
    for start in range(max(0, len(observed) - 3)):
        if tuple(observed[start : start + 4]) == _PRODUCT_KEYS:
            return True
    return False


def _latest_period_before(tokens: tuple[str, ...], position: int) -> str | None:
    current = {_normalized(value): value for value in _CURRENT_MARKERS}
    prior = {_normalized(value): value for value in _PRIOR_MARKERS}
    for token in reversed(tokens[:position]):
        normalized = _normalized(token)
        if normalized in current:
            return current[normalized]
        if normalized in prior:
            return prior[normalized]
    return None


def _source_note_sections(
    source_tokens: tuple[str, ...],
    heading: str,
) -> tuple[tuple[str, ...], ...]:
    normalized_heading = _normalized(heading)
    sections: list[tuple[str, ...]] = []
    for start, token in enumerate(source_tokens):
        if _normalized(token) != normalized_heading:
            continue
        end = len(source_tokens)
        for position in range(start + 1, len(source_tokens)):
            candidate = " ".join(source_tokens[position].split())
            if _NOTE_HEADING.fullmatch(candidate):
                end = position
                break
        sections.append(source_tokens[start + 1 : end])
    return tuple(sections)


def _raw_source_candidates(
    spec: PeriodicProductRevenueSpec,
    *,
    header: _RawTable,
    source_tokens: tuple[str, ...],
) -> tuple[ProductRevenueMetrics, ...]:
    if _header_product_order(spec, header) != _PRODUCT_KEYS:
        raise ValueError("OpenDART product order is not canonical")
    heading = _nearest_heading(header)
    if heading is None:
        return ()
    unit, scale = _structured_unit(header, _grid(header))
    accepted_revenue = _accepted(_REVENUE_LABELS)
    parsed: list[ProductRevenueMetrics] = []
    for section in _source_note_sections(source_tokens, heading):
        for revenue_position, token in enumerate(section):
            if _normalized(token) not in accepted_revenue:
                continue
            if _latest_period_before(section, revenue_position) not in _CURRENT_MARKERS:
                continue
            if not _product_header_sequence_present(
                spec,
                section,
                before=revenue_position,
            ):
                continue
            parsed.extend(
                _windows_after_revenue_label(
                    section[revenue_position:],
                    unit=unit,
                    scale=scale,
                )
            )
    return tuple(parsed)


def _header_candidates(
    spec: PeriodicProductRevenueSpec,
    tables: list[_RawTable],
) -> tuple[tuple[int, _RawTable], ...]:
    found: list[tuple[int, _RawTable]] = []
    for index, table in enumerate(tables):
        try:
            _header_product_order(spec, table)
        except ValueError:
            continue
        found.append((index, table))
    return tuple(found)


def parse_periodic_product_revenue_archive(
    spec: PeriodicProductRevenueSpec,
    archive_bytes: bytes,
) -> ProductRevenueMetrics:
    """Replay unique current consolidated product revenue from archived ZIP bytes."""

    try:
        archive = zipfile.ZipFile(io.BytesIO(archive_bytes))
    except zipfile.BadZipFile as exc:
        raise ValueError("OpenDART product-revenue semantic replay source is not a ZIP") from exc

    candidates: list[ProductRevenueMetrics] = []
    total_tables = 0
    structural_headers = 0
    table_revenue_labels = 0
    raw_revenue_labels = 0
    reconciling_windows = 0
    accepted_revenue = _accepted(_REVENUE_LABELS)
    with archive:
        for info in archive.infolist():
            if info.is_dir():
                continue
            safe_name = _safe_member_name(info.filename)
            if PurePosixPath(safe_name).suffix.casefold() not in _TEXT_SUFFIXES:
                continue
            decoded, _encoding = _decode_text(archive.read(info))

            table_parser = _TableExtractor()
            table_parser.feed(decoded)
            table_parser.close()
            total_tables += len(table_parser.tables)

            source_parser = _SourceTokenExtractor()
            source_parser.feed(decoded)
            source_parser.close()
            source_tokens = tuple(source_parser.tokens)
            raw_revenue_labels += sum(
                1 for token in source_tokens if _normalized(token) in accepted_revenue
            )
            table_revenue_labels += sum(
                1
                for table in table_parser.tables
                for token in _flatten_table_tokens(table)
                if _normalized(token) in accepted_revenue
            )

            headers = _header_candidates(spec, table_parser.tables)
            structural_headers += len(headers)
            for header_index, header in headers:
                heading = _nearest_heading(header)
                if heading is None:
                    continue
                scope = _same_note_current_period_scope(
                    table_parser.tables,
                    header_index=header_index,
                    heading=heading,
                )
                table_candidates = _table_stream_candidates(
                    spec,
                    header=header,
                    scoped_tables=scope,
                )
                raw_candidates = _raw_source_candidates(
                    spec,
                    header=header,
                    source_tokens=source_tokens,
                )
                reconciling_windows += len(table_candidates) + len(raw_candidates)
                candidates.extend(table_candidates)
                candidates.extend(raw_candidates)

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
            f"current_consolidated_headers={structural_headers} "
            f"table_revenue_labels={table_revenue_labels} "
            f"raw_source_revenue_labels={raw_revenue_labels} "
            f"reconciling_windows={reconciling_windows}"
        )
    return next(iter(unique.values()))


__all__ = ["parse_periodic_product_revenue_archive"]