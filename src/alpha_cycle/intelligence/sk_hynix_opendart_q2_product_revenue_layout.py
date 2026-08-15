"""Parse SK hynix OpenDART product revenue using the filing's actual column layout.

SK hynix periodic filings publish DRAM, NAND Flash, Other, and total as column groups
under the consolidated revenue note. In the live 2026 half-year filing the product
header grid and the single revenue data row are emitted as adjacent HTML tables rather
than one table. This module supports both that split-table production shape and the
older single-table fixture shape, while preserving the legacy row-layout parser only as
a compatibility fallback.
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
from alpha_cycle.intelligence.sk_hynix_opendart_q2_product_revenue_certification import (
    parse_periodic_product_revenue_text as _legacy_text_parser,
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
from alpha_cycle.intelligence.sk_hynix_opendart_q2_product_revenue_table import (
    parse_periodic_product_revenue_archive as _legacy_archive_parser,
)
from alpha_cycle.providers.opendart_documents import _decode_text, _safe_member_name

_TEXT_SUFFIXES = frozenset({".xml", ".html", ".htm", ".xhtml"})
_CURRENT_MARKERS = ("당반기", "당분기", "당기")
_PRIOR_MARKERS = ("전반기", "전분기", "전기")
_REVENUE_ROW_LABELS = ("수익", "수익(매출액)", "수익 (매출액)")
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
            for value in (
                "3개월",
                "누적",
                "3개월",
                "누적",
                "3개월",
                "누적",
                "3개월",
                "누적",
            )
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
    """Parse the consolidated product-as-columns text, with legacy fixture fallback."""

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


def _current_period_table(table: _RawTable) -> bool:
    accepted = {_normalized(marker) for marker in (*_CURRENT_MARKERS, *_PRIOR_MARKERS)}
    for value in reversed(table.prefix_text):
        normalized = _normalized(value)
        if normalized in accepted:
            return normalized in {_normalized(marker) for marker in _CURRENT_MARKERS}
    return False


def _product_columns_from_header(
    spec: PeriodicProductRevenueSpec,
    grid: tuple[tuple[str, ...], ...],
) -> dict[str, int]:
    width = max((len(row) for row in grid), default=0)
    matches: dict[str, list[int]] = {
        "dram": [],
        "nand": [],
        "other": [],
        "total": [],
    }
    for column in range(width):
        tokens = tuple(
            row[column]
            for row in grid
            if column < len(row) and row[column].strip()
        )
        normalized_tokens = {_normalized(token) for token in tokens}
        if _normalized("3개월") not in normalized_tokens:
            continue
        if _normalized("누적") in normalized_tokens:
            continue
        if _header_has_label(tokens, spec.product_labels["dram_total"]):
            matches["dram"].append(column)
        if _header_has_label(tokens, spec.product_labels["nand_and_solutions"]):
            matches["nand"].append(column)
        if _header_has_label(tokens, spec.product_labels["other_products_services"]):
            matches["other"].append(column)
        if _header_has_label(tokens, spec.product_labels["reported_company_revenue"]):
            matches["total"].append(column)
    if any(len(columns) != 1 for columns in matches.values()):
        counts = {key: len(value) for key, value in matches.items()}
        raise ValueError(f"OpenDART product 3-month header columns are not unique: {counts}")
    return {key: columns[0] for key, columns in matches.items()}


def _revenue_row(
    grid: tuple[tuple[str, ...], ...],
) -> tuple[int, int]:
    accepted = _accepted(_REVENUE_ROW_LABELS)
    matches: list[tuple[int, int]] = []
    for row_index, row in enumerate(grid):
        for column, value in enumerate(row):
            if _normalized(value) in accepted:
                matches.append((row_index, column))
    if len(matches) != 1:
        raise ValueError(
            "OpenDART product-column data table requires one revenue row: "
            f"count={len(matches)}"
        )
    return matches[0]


def _metrics_from_header_and_data(
    spec: PeriodicProductRevenueSpec,
    *,
    header_table: _RawTable,
    header_grid: tuple[tuple[str, ...], ...],
    data_grid: tuple[tuple[str, ...], ...],
) -> ProductRevenueMetrics:
    heading = _nearest_table_note_heading(header_table)
    if heading is None or "(연결)" not in heading.replace(" ", ""):
        raise ValueError("OpenDART product table is outside consolidated revenue note")
    if not _current_period_table(header_table):
        raise ValueError("OpenDART product-column table is not the current period")

    product_columns = _product_columns_from_header(spec, header_grid)
    revenue_row, label_column = _revenue_row(data_grid)
    if label_column != 0:
        raise ValueError("OpenDART split product revenue row label must occupy first column")

    unit, scale = _structured_unit(header_table, header_grid)
    values: dict[str, float] = {}
    for key, column in product_columns.items():
        if column >= len(data_grid[revenue_row]):
            raise ValueError(f"OpenDART structured {key} 3-month amount is missing")
        amount = _parse_amount(data_grid[revenue_row][column])
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


def _column_metrics_from_table(
    spec: PeriodicProductRevenueSpec,
    table: _RawTable,
) -> ProductRevenueMetrics:
    grid = _grid(table)
    return _metrics_from_header_and_data(
        spec,
        header_table=table,
        header_grid=grid,
        data_grid=grid,
    )


def _split_column_metrics_from_tables(
    spec: PeriodicProductRevenueSpec,
    header_table: _RawTable,
    data_table: _RawTable,
) -> ProductRevenueMetrics:
    header_grid = _grid(header_table)
    data_grid = _grid(data_table)
    header_heading = _nearest_table_note_heading(header_table)
    data_heading = _nearest_table_note_heading(data_table)
    if (
        header_heading is not None
        and data_heading is not None
        and _normalized(header_heading) != _normalized(data_heading)
    ):
        raise ValueError("OpenDART split product tables cross a revenue-note boundary")
    return _metrics_from_header_and_data(
        spec,
        header_table=header_table,
        header_grid=header_grid,
        data_grid=data_grid,
    )


def parse_periodic_product_revenue_archive(
    spec: PeriodicProductRevenueSpec,
    archive_bytes: bytes,
) -> ProductRevenueMetrics:
    """Parse the unique consolidated current-period product table from raw source bytes."""

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
            for index, table in enumerate(parser.tables):
                try:
                    candidates.append(_column_metrics_from_table(spec, table))
                except ValueError:
                    pass
                if index + 1 >= len(parser.tables):
                    continue
                try:
                    candidates.append(
                        _split_column_metrics_from_tables(
                            spec,
                            table,
                            parser.tables[index + 1],
                        )
                    )
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
