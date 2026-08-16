"""Strict historical layout fallbacks for SK hynix OpenDART product revenue.

Historical quarterly filings predate the 2025/2026 product-as-columns layout used by
current certifications.  This module covers only the registered historical parser id and
only two source shapes that remain directly auditable:

* row-layout periodic tables, where products are rows and current 3-month revenue is a
  dedicated column; and
* Q1 single-period presentations, where the current quarter does not require a separate
  cumulative value to identify the direct product amounts.

The parser never derives Other by subtraction and never converts cumulative revenue into
a quarterly amount.  Every accepted candidate must report DRAM, NAND, Other, and Total
directly and reconcile within the ProductRevenueMetrics tolerance.
"""

from __future__ import annotations

import io
import re
import zipfile
from datetime import date
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

HISTORICAL_PRODUCT_REVENUE_PARSER_ID = "skhynix_opendart_periodic_product_revenue_v1"
_TEXT_SUFFIXES = frozenset({".xml", ".html", ".htm", ".xhtml"})
_CURRENT_MARKERS = ("당반기", "당분기", "당기")
_PRIOR_MARKERS = ("전반기", "전분기", "전기")
_REVENUE_LABELS = ("수익", "수익(매출액)", "수익 (매출액)")
_NOTE_HEADING = re.compile(r"^\s*\d+\.\s*매출액\s*\(연결\)\s*$")
_ANY_NOTE_HEADING = re.compile(r"^\s*\d+\.\s*.+$")
_RECONCILIATION_TOLERANCE = 0.5


def _is_q1(spec: PeriodicProductRevenueSpec) -> bool:
    return (
        spec.period_start == date(spec.period_end.year, 1, 1)
        and spec.period_end == date(spec.period_end.year, 3, 31)
    )


def _require_historical_spec(spec: PeriodicProductRevenueSpec) -> None:
    if spec.parser_id != HISTORICAL_PRODUCT_REVENUE_PARSER_ID:
        raise ValueError("Unsupported historical periodic product revenue parser_id")


def _normalize_lines(text: str) -> tuple[str, ...]:
    return tuple(
        " ".join(line.replace("\u00a0", " ").split())
        for line in text.splitlines()
        if line.strip()
    )


def _accepted(labels: tuple[str, ...]) -> frozenset[str]:
    return frozenset(_normalized(value) for value in labels)


def _metrics(
    *,
    unit: str,
    scale: float,
    dram: float,
    nand: float,
    other: float,
    total: float,
) -> ProductRevenueMetrics:
    dram *= scale
    nand *= scale
    other *= scale
    total *= scale
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


def _connected_sections(lines: tuple[str, ...]) -> tuple[tuple[str, ...], ...]:
    sections: list[tuple[str, ...]] = []
    for start, line in enumerate(lines):
        if _NOTE_HEADING.fullmatch(line) is None:
            continue
        end = len(lines)
        for position in range(start + 1, len(lines)):
            if _ANY_NOTE_HEADING.fullmatch(lines[position]) is not None:
                end = position
                break
        sections.append(lines[start:end])
    return tuple(sections)


def _text_unit(section: tuple[str, ...]) -> tuple[str, float]:
    found: list[tuple[str, float]] = []
    for line in section:
        if "단위" not in line:
            continue
        if "백만원" in line:
            found.append(("KRW_million", 1.0))
        if "억원" in line:
            found.append(("KRW_million", 100.0))
    unique = list(dict.fromkeys(found))
    if len(unique) != 1:
        raise ValueError("Historical product revenue requires one supported KRW unit")
    return unique[0]


def _label_index(
    lines: tuple[str, ...],
    labels: tuple[str, ...],
    *,
    start: int,
) -> int:
    accepted = _accepted(labels)
    for index in range(start, len(lines)):
        if _normalized(lines[index]) in accepted:
            return index
    raise ValueError(f"Historical product revenue label missing: {labels[0]}")


def _first_amount_between(
    lines: tuple[str, ...],
    *,
    start: int,
    end: int,
    label: str,
) -> float:
    for token in lines[start:end]:
        amount = _parse_amount(token)
        if amount is not None:
            return amount
    raise ValueError(f"Historical product revenue row has no amount: {label}")


def _row_text_candidate(
    spec: PeriodicProductRevenueSpec,
    section: tuple[str, ...],
) -> ProductRevenueMetrics:
    joined = "\n".join(section)
    if not any(marker in joined for marker in _CURRENT_MARKERS):
        raise ValueError("Historical product revenue row table lacks a current-period marker")
    if "3개월" not in joined:
        raise ValueError("Historical product revenue row table lacks a 3-month marker")
    if not _is_q1(spec) and "누적" not in joined:
        raise ValueError("Historical non-Q1 product revenue row table lacks cumulative structure")

    dram_index = _label_index(section, spec.product_labels["dram_total"], start=0)
    nand_index = _label_index(
        section,
        spec.product_labels["nand_and_solutions"],
        start=dram_index + 1,
    )
    other_index = _label_index(
        section,
        spec.product_labels["other_products_services"],
        start=nand_index + 1,
    )
    total_index = _label_index(
        section,
        spec.product_labels["reported_company_revenue"],
        start=other_index + 1,
    )
    if not (dram_index < nand_index < other_index < total_index):
        raise ValueError("Historical product revenue row labels are not canonical")
    end = min(len(section), total_index + 16)
    unit, scale = _text_unit(section)
    return _metrics(
        unit=unit,
        scale=scale,
        dram=_first_amount_between(
            section,
            start=dram_index + 1,
            end=nand_index,
            label="DRAM",
        ),
        nand=_first_amount_between(
            section,
            start=nand_index + 1,
            end=other_index,
            label="NAND",
        ),
        other=_first_amount_between(
            section,
            start=other_index + 1,
            end=total_index,
            label="Other",
        ),
        total=_first_amount_between(
            section,
            start=total_index + 1,
            end=end,
            label="Total",
        ),
    )


def _q1_revenue_row_candidates(
    spec: PeriodicProductRevenueSpec,
    section: tuple[str, ...],
) -> tuple[ProductRevenueMetrics, ...]:
    if not _is_q1(spec):
        return ()
    accepted_revenue = _accepted(_REVENUE_LABELS)
    product_sets = (
        _accepted(spec.product_labels["dram_total"]),
        _accepted(spec.product_labels["nand_and_solutions"]),
        _accepted(spec.product_labels["other_products_services"]),
        _accepted(spec.product_labels["reported_company_revenue"]),
    )
    unit, scale = _text_unit(section)
    parsed: list[ProductRevenueMetrics] = []
    for revenue_index, token in enumerate(section):
        if _normalized(token) not in accepted_revenue:
            continue
        preceding = tuple(_normalized(value) for value in section[:revenue_index])
        cursor = 0
        for accepted in product_sets:
            matched = False
            for position in range(cursor, len(preceding)):
                if preceding[position] in accepted:
                    cursor = position + 1
                    matched = True
                    break
            if not matched:
                break
        else:
            numeric: list[float] = []
            for value in section[revenue_index + 1 : revenue_index + 40]:
                normalized = _normalized(value)
                if normalized in _accepted((*_CURRENT_MARKERS, *_PRIOR_MARKERS)):
                    break
                amount = _parse_amount(value)
                if amount is not None:
                    numeric.append(amount)
            for offset in range(max(0, len(numeric) - 3)):
                values = numeric[offset : offset + 4]
                try:
                    parsed.append(
                        _metrics(
                            unit=unit,
                            scale=scale,
                            dram=values[0],
                            nand=values[1],
                            other=values[2],
                            total=values[3],
                        )
                    )
                except ValueError:
                    continue
    return tuple(parsed)


def parse_historical_product_revenue_text_fallback(
    spec: PeriodicProductRevenueSpec,
    text: str,
) -> ProductRevenueMetrics:
    """Parse a unique connected historical row/Q1 layout from normalized text."""

    _require_historical_spec(spec)
    lines = _normalize_lines(text)
    if not lines:
        raise ValueError("Historical periodic document text is empty")
    folded = "\n".join(lines).casefold()
    for anchor in spec.expected_identity_anchors:
        if _normalized(anchor) not in folded:
            raise ValueError(f"Historical product revenue anchor missing: {anchor}")

    parsed: list[ProductRevenueMetrics] = []
    for section in _connected_sections(lines):
        try:
            parsed.append(_row_text_candidate(spec, section))
        except ValueError:
            pass
        parsed.extend(_q1_revenue_row_candidates(spec, section))
    unique = {
        (
            item.unit,
            item.dram_total,
            item.nand_and_solutions,
            item.other_products_services,
            item.reported_company_revenue,
        ): item
        for item in parsed
    }
    if len(unique) != 1:
        raise ValueError(
            "Historical OpenDART product revenue text must resolve uniquely: "
            f"candidates={len(unique)}"
        )
    return next(iter(unique.values()))


def _nearest_connected_heading(table: _RawTable) -> str | None:
    for value in reversed(table.prefix_text):
        normalized = " ".join(value.split())
        if _ANY_NOTE_HEADING.fullmatch(normalized) is None:
            continue
        if _NOTE_HEADING.fullmatch(normalized) is not None:
            return normalized
        return None
    return None


def _row_index(
    grid: tuple[tuple[str, ...], ...],
    labels: tuple[str, ...],
    *,
    start: int,
) -> tuple[int, int]:
    accepted = _accepted(labels)
    for row_index in range(start, len(grid)):
        for column, value in enumerate(grid[row_index]):
            if _normalized(value) in accepted:
                return row_index, column
    raise ValueError(f"Historical structured product row missing: {labels[0]}")


def _header_tokens(
    grid: tuple[tuple[str, ...], ...],
    *,
    row_end: int,
    column: int,
) -> tuple[str, ...]:
    return tuple(
        value
        for row in grid[:row_end]
        if column < len(row) and (value := row[column].strip())
    )


def _contains(tokens: tuple[str, ...], marker: str) -> bool:
    target = _normalized(marker)
    return any(target in _normalized(token) for token in tokens)


def _current_three_month_column(
    spec: PeriodicProductRevenueSpec,
    grid: tuple[tuple[str, ...], ...],
    *,
    product_row: int,
    label_column: int,
) -> int:
    current_three_month: list[int] = []
    current_cumulative: list[int] = []
    prior_three_month: list[int] = []
    for column in range(label_column + 1, len(grid[product_row])):
        tokens = _header_tokens(grid, row_end=product_row, column=column)
        current = any(_contains(tokens, marker) for marker in _CURRENT_MARKERS)
        prior = any(_contains(tokens, marker) for marker in _PRIOR_MARKERS)
        three_month = _contains(tokens, "3개월")
        cumulative = _contains(tokens, "누적")
        if current and prior:
            raise ValueError("Historical product header mixes current/prior period")
        if current and three_month and not cumulative:
            current_three_month.append(column)
        if current and cumulative and not three_month:
            current_cumulative.append(column)
        if prior and three_month and not cumulative:
            prior_three_month.append(column)
    if len(current_three_month) != 1:
        raise ValueError("Historical current 3-month product column must be unique")
    if _is_q1(spec):
        if len(prior_three_month) > 1 or len(current_cumulative) > 1:
            raise ValueError("Historical Q1 product header is ambiguous")
        return current_three_month[0]
    if len(current_cumulative) != 1 or len(prior_three_month) != 1:
        raise ValueError("Historical product header lacks cumulative/prior structure")
    return current_three_month[0]


def _amount_at(
    grid: tuple[tuple[str, ...], ...],
    *,
    row: int,
    column: int,
    label: str,
) -> float:
    if column >= len(grid[row]):
        raise ValueError(f"Historical structured {label} amount is missing")
    amount = _parse_amount(grid[row][column])
    if amount is None:
        raise ValueError(f"Historical structured {label} amount is invalid")
    return amount


def _row_table_metrics(
    spec: PeriodicProductRevenueSpec,
    table: _RawTable,
) -> ProductRevenueMetrics:
    if _nearest_connected_heading(table) is None:
        raise ValueError("Historical product row table is outside consolidated revenue note")
    grid = _grid(table)
    dram_row, label_column = _row_index(grid, spec.product_labels["dram_total"], start=0)
    nand_row, nand_column = _row_index(
        grid,
        spec.product_labels["nand_and_solutions"],
        start=dram_row + 1,
    )
    other_row, other_column = _row_index(
        grid,
        spec.product_labels["other_products_services"],
        start=nand_row + 1,
    )
    total_row, total_column = _row_index(
        grid,
        spec.product_labels["reported_company_revenue"],
        start=other_row + 1,
    )
    if len({label_column, nand_column, other_column, total_column}) != 1:
        raise ValueError("Historical product labels do not share one row-label column")
    current_column = _current_three_month_column(
        spec,
        grid,
        product_row=dram_row,
        label_column=label_column,
    )
    unit, scale = _structured_unit(table, grid)
    return _metrics(
        unit=unit,
        scale=scale,
        dram=_amount_at(grid, row=dram_row, column=current_column, label="DRAM"),
        nand=_amount_at(grid, row=nand_row, column=current_column, label="NAND"),
        other=_amount_at(grid, row=other_row, column=current_column, label="Other"),
        total=_amount_at(grid, row=total_row, column=current_column, label="Total"),
    )


def parse_historical_product_revenue_archive_fallback(
    spec: PeriodicProductRevenueSpec,
    archive_bytes: bytes,
) -> ProductRevenueMetrics:
    """Rebuild the unique connected historical row-layout table from raw ZIP bytes."""

    _require_historical_spec(spec)
    try:
        archive = zipfile.ZipFile(io.BytesIO(archive_bytes))
    except zipfile.BadZipFile as exc:
        raise ValueError("Historical product-revenue source is not a ZIP") from exc
    parsed: list[ProductRevenueMetrics] = []
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
            for table in parser.tables:
                try:
                    parsed.append(_row_table_metrics(spec, table))
                except ValueError:
                    continue
    unique = {
        (
            item.unit,
            item.dram_total,
            item.nand_and_solutions,
            item.other_products_services,
            item.reported_company_revenue,
        ): item
        for item in parsed
    }
    if len(unique) != 1:
        raise ValueError(
            "Historical OpenDART structured row product revenue must resolve uniquely: "
            f"candidates={len(unique)}"
        )
    return next(iter(unique.values()))


__all__ = [
    "HISTORICAL_PRODUCT_REVENUE_PARSER_ID",
    "parse_historical_product_revenue_archive_fallback",
    "parse_historical_product_revenue_text_fallback",
]
