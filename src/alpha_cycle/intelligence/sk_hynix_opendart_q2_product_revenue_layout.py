"""Parse SK hynix OpenDART product revenue using the filing's actual column layout.

SK hynix periodic filings publish DRAM, NAND Flash, Other, and total as column groups
under the consolidated revenue note. Each product column has 3-month/cumulative
subcolumns and a single ``수익(매출액)`` data row. This module preserves compatibility
with the earlier row-layout parser for archived synthetic fixtures, but production
column-layout evidence must be scoped to the nearest ``매출액 (연결)`` note.
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
    parse_periodic_product_revenue_text as _legacy_text_parser,
)
from alpha_cycle.intelligence.sk_hynix_opendart_q2_product_revenue_table import (
    _RawTable,
    _TableExtractor,
    _grid,
    _normalized,
    _unit as _structured_unit,
    parse_periodic_product_revenue_archive as _legacy_archive_parser,
)
from alpha_cycle.providers.opendart_documents import _decode_text, _safe_member_name

_TEXT_SUFFIXES = frozenset({".xml", ".html", ".htm", ".xhtml"})
_CURRENT_MARKERS = ("당반기", "당분기", "당기")
_PRIOR_MARKERS = ("전반기", "전분기", "전기")
_REVENUE_ROW_LABELS = ("수익(매출액)", "수익 (매출액)")
_NOTE_HEADING = re.compile(r"^\s*\d+\.\s*매출액(?:\s*\(연결\))?\s*$")
_ALLOWED_UNIT_MARKERS = {"백만원": ("KRW_million", 1.0), "억원": ("KRW_million", 100.0)}


def _normalize_lines(text: str) -> tuple[str, ...]:
    return tuple(
        " ".join(line.replace("\u00a0", " ").split())
        for line in text.splitlines()
        if line.strip()
    )


def _accepted(labels: tuple[str, ...]) -> frozenset[str]:
    return frozenset(_normalized(label) for label in labels)


def _matching_indices(
    lines: tuple[str, ...],
    labels: tuple[str, ...],
    *,
    start: int,
    end: int,
) -> list[int]:
    accepted = _accepted(labels)
    return [
        index
        for index in range(start, min(end, len(lines)))
        if _normalized(lines[index]) in accepted
    ]


def _nearest_note_heading(lines: tuple[str, ...], index: int) -> str | None:
    for position in range(index - 1, max(-1, index - 180), -1):
        value = lines[position]
        if _NOTE_HEADING.fullmatch(value):
            return value
    return None


def _nearest_period_marker(lines: tuple[str, ...], index: int) -> str | None:
    markers = (*_CURRENT_MARKERS, *_PRIOR_MARKERS)
    for position in range(index - 1, max(-1, index - 80), -1):
        folded = _normalized(lines[position])
        for marker in markers:
            if _normalized(marker) == folded:
                return marker
    return None


def _text_unit(lines: tuple[str, ...], start: int, end: int) -> tuple[str, float]:
    found: list[tuple[str, float]] = []
    for line in lines[max(0, start) : min(len(lines), end)]:
        if "단위" not in line:
            continue
        for marker, normalized in _ALLOWED_UNIT_MARKERS.items():
            if marker in line:
                found.append(normalized)
    unique = list(dict.fromkeys(found))
    if len(unique) != 1:
        raise ValueError("OpenDART product revenue column table requires one KRW unit")
    return unique[0]


def _column_text_candidates(
    spec: PeriodicProductRevenueSpec,
    text: str,
) -> tuple[ProductRevenueMetrics, ...]:
    lines = _normalize_lines(text)
    if not lines:
        return ()
    folded = "\n".join(lines).casefold()
    for anchor in spec.expected_identity_anchors:
        if _normalized(anchor) not in folded:
            raise ValueError(f"OpenDART periodic product revenue anchor missing: {anchor}")

    dram_indices = _matching_indices(
        lines,
        spec.product_labels["dram_total"],
        start=0,
        end=len(lines),
    )
    parsed: list[ProductRevenueMetrics] = []
    for dram_index in dram_indices:
        heading = _nearest_note_heading(lines, dram_index)
        if heading is None or "(연결)" not in heading.replace(" ", ""):
            continue
        period = _nearest_period_marker(lines, dram_index)
        if period not in _CURRENT_MARKERS:
            continue
        window_start = max(0, dram_index - 40)
        window_end = min(len(lines), dram_index + 80)
        nand_indices = _matching_indices(
            lines,
            spec.product_labels["nand_and_solutions"],
            start=dram_index + 1,
            end=window_end,
        )
        if not nand_indices:
            continue
        nand_index = nand_indices[0]
        other_indices = _matching_indices(
            lines,
            spec.product_labels["other_products_services"],
            start=nand_index + 1,
            end=window_end,
        )
        if not other_indices:
            continue
        other_index = other_indices[0]
        revenue_indices = _matching_indices(
            lines,
            _REVENUE_ROW_LABELS,
            start=other_index + 1,
            end=window_end,
        )
        if not revenue_indices:
            continue
        revenue_index = revenue_indices[0]
        total_indices = _matching_indices(
            lines,
            spec.product_labels["reported_company_revenue"],
            start=window_start,
            end=revenue_index,
        )
        if not total_indices:
            continue

        period_tokens = [
            _normalized(line)
            for line in lines[other_index + 1 : revenue_index]
            if _normalized(line) in {_normalized("3개월"), _normalized("누적")}
        ]
        expected_period_tokens = [
            _normalized(value)
            for value in ("3개월", "누적", "3개월", "누적", "3개월", "누적", "3개월", "누적")
        ]
        if period_tokens != expected_period_tokens:
            continue

        next_period = len(lines)
        for position in range(revenue_index + 1, min(len(lines), revenue_index + 40)):
            normalized = _normalized(lines[position])
            if normalized in {
                *(_normalized(value) for value in _CURRENT_MARKERS),
                *(_normalized(value) for value in _PRIOR_MARKERS),
            }:
                next_period = position
                break
        amounts = [
            amount
            for token in lines[revenue_index + 1 : next_period]
            if (amount := _parse_amount(token)) is not None
        ]
        if len(amounts) != 8:
            continue
        unit, scale = _text_unit(lines, window_start, revenue_index)
        dram = amounts[0] * scale
        nand = amounts[2] * scale
        other = amounts[4] * scale
        total = amounts[6] * scale
        direct_sum = dram + nand + other
        try:
            parsed.append(
                ProductRevenueMetrics(
                    unit=unit,
                    dram_total=dram,
                    nand_and_solutions=nand,
                    other_products_services=other,
                    reported_company_revenue=total,
                    direct_sum=direct_sum,
                    reconciliation_delta=direct_sum - total,
                )
            )
        except ValueError:
            continue
    return tuple(parsed)


def parse_periodic_product_revenue_text(
    spec: PeriodicProductRevenueSpec,
    text: str,
) -> ProductRevenueMetrics:
    """Parse the consolidated product-as-columns table, with legacy fixture fallback."""

    candidates = _column_text_candidates(spec, text)
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
    if len(unique) == 1:
        return next(iter(unique.values()))
    if len(unique) > 1:
        raise ValueError(
            "OpenDART consolidated product-column revenue must resolve uniquely: "
            f"candidates={len(unique)}"
        )
    return _legacy_text_parser(spec, text)


def _nearest_table_note_heading(table: _RawTable) -> str | None:
    for value in reversed(table.prefix_text):
        normalized = " ".join(value.split())
        if _NOTE_HEADING.fullmatch(normalized):
            return normalized
    return None


def _header_has_label(tokens: tuple[str, ...], labels: tuple[str, ...]) -> bool:
    accepted = _accepted(labels)
    return any(_normalized(token) in accepted for token in tokens)


def _column_metrics_from_table(
    spec: PeriodicProductRevenueSpec,
    table: _RawTable,
) -> ProductRevenueMetrics:
    heading = _nearest_table_note_heading(table)
    if heading is None or "(연결)" not in heading.replace(" ", ""):
        raise ValueError("OpenDART product table is outside consolidated revenue note")
    grid = _grid(table)
    revenue_labels = _accepted(_REVENUE_ROW_LABELS)
    revenue_rows = [
        row_index
        for row_index, row in enumerate(grid)
        if any(_normalized(value) in revenue_labels for value in row)
    ]
    if len(revenue_rows) != 1:
        raise ValueError("OpenDART product-column table requires one revenue data row")
    revenue_row = revenue_rows[0]
    period_context = tuple(_normalized(value) for value in table.prefix_text[-30:])
    last_period: str | None = None
    for value in reversed(period_context):
        if value in {_normalized(marker) for marker in (*_CURRENT_MARKERS, *_PRIOR_MARKERS)}:
            last_period = value
            break
    if last_period not in {_normalized(marker) for marker in _CURRENT_MARKERS}:
        raise ValueError("OpenDART product-column table is not the current period")

    product_columns: dict[str, list[int]] = {
        "dram": [],
        "nand": [],
        "other": [],
        "total": [],
    }
    for column in range(len(grid[revenue_row])):
        tokens = tuple(
            row[column]
            for row in grid[:revenue_row]
            if column < len(row) and row[column].strip()
        )
        if not any(_normalized("3개월") == _normalized(token) for token in tokens):
            continue
        if any(_normalized("누적") == _normalized(token) for token in tokens):
            continue
        if _header_has_label(tokens, spec.product_labels["dram_total"]):
            product_columns["dram"].append(column)
        if _header_has_label(tokens, spec.product_labels["nand_and_solutions"]):
            product_columns["nand"].append(column)
        if _header_has_label(tokens, spec.product_labels["other_products_services"]):
            product_columns["other"].append(column)
        if _header_has_label(tokens, spec.product_labels["reported_company_revenue"]):
            product_columns["total"].append(column)
    if any(len(columns) != 1 for columns in product_columns.values()):
        counts = {key: len(value) for key, value in product_columns.items()}
        raise ValueError(f"OpenDART product 3-month columns are not unique: {counts}")

    unit, scale = _structured_unit(table, grid)
    values: dict[str, float] = {}
    for key, columns in product_columns.items():
        column = columns[0]
        amount = _parse_amount(grid[revenue_row][column])
        if amount is None:
            raise ValueError(f"OpenDART structured {key} 3-month amount is invalid")
        values[key] = amount * scale
    direct_sum = values["dram"] + values["nand"] + values["other"]
    return ProductRevenueMetrics(
        unit=unit,
        dram_total=values["dram"],
        nand_and_solutions=values["nand"],
        other_products_services=values["other"],
        reported_company_revenue=values["total"],
        direct_sum=direct_sum,
        reconciliation_delta=direct_sum - values["total"],
    )


def parse_periodic_product_revenue_archive(
    spec: PeriodicProductRevenueSpec,
    archive_bytes: bytes,
) -> ProductRevenueMetrics:
    """Parse the unique consolidated current-period product-as-columns source table."""

    try:
        archive = zipfile.ZipFile(io.BytesIO(archive_bytes))
    except zipfile.BadZipFile as exc:
        raise ValueError("OpenDART product-revenue structural source is not a ZIP") from exc
    candidates: list[ProductRevenueMetrics] = []
    with archive:
        for info in archive.infolist():
            if info.is_dir():
                continue
            safe_name = _safe_member_name(info.filename)
            if PurePosixPath(safe_name).suffix.casefold() not in _TEXT_SUFFIXES:
                continue
            raw = archive.read(info)
            decoded, _encoding = _decode_text(raw)
            parser = _TableExtractor()
            parser.feed(decoded)
            parser.close()
            for table in parser.tables:
                try:
                    candidates.append(_column_metrics_from_table(spec, table))
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
        for item in candidates
    }
    if len(unique) == 1:
        return next(iter(unique.values()))
    if len(unique) > 1:
        raise ValueError(
            "OpenDART consolidated structured product revenue must resolve uniquely: "
            f"candidates={len(unique)}"
        )
    return _legacy_archive_parser(spec, archive_bytes)


__all__ = [
    "parse_periodic_product_revenue_archive",
    "parse_periodic_product_revenue_text",
]
