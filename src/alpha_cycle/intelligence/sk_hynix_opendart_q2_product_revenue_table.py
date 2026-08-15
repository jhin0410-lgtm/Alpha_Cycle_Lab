"""Structural table verification for SK hynix Q2 product revenue in raw OpenDART ZIPs.

The normalized-text parser is useful for discovery and diagnostics, but it cannot retain
HTML colspan/rowspan semantics. This verifier reconstructs the source table grid from the
archived official document and accepts values only from the unique column whose header
path contains both a current-period marker and the three-month marker.
"""

from __future__ import annotations

import io
import zipfile
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import PurePosixPath

from alpha_cycle.intelligence.sk_hynix_opendart_q2_product_revenue_certification import (
    PeriodicProductRevenueSpec,
    ProductRevenueMetrics,
    _parse_amount,
)
from alpha_cycle.providers.opendart_documents import _decode_text, _safe_member_name

_TEXT_SUFFIXES = frozenset({".xml", ".html", ".htm", ".xhtml"})
_CURRENT_MARKERS = ("당반기", "당분기", "당기")
_PRIOR_MARKERS = ("전반기", "전분기", "전기")
_THREE_MONTH_MARKER = "3개월"
_CUMULATIVE_MARKER = "누적"
_UNIT_MARKERS = {"백만원": ("KRW_million", 1.0), "억원": ("KRW_million", 100.0)}


@dataclass(frozen=True)
class _RawCell:
    text: str
    colspan: int
    rowspan: int


@dataclass(frozen=True)
class _RawTable:
    rows: tuple[tuple[_RawCell, ...], ...]
    prefix_text: tuple[str, ...]


class _TableExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.tables: list[_RawTable] = []
        self._recent: list[str] = []
        self._table_depth = 0
        self._rows: list[tuple[_RawCell, ...]] | None = None
        self._prefix: tuple[str, ...] = ()
        self._row: list[_RawCell] | None = None
        self._cell_parts: list[str] | None = None
        self._cell_colspan = 1
        self._cell_rowspan = 1

    @staticmethod
    def _span(attrs: list[tuple[str, str | None]], name: str) -> int:
        for key, value in attrs:
            if key == name and value is not None:
                try:
                    span = int(value)
                except ValueError:
                    return 1
                return span if 1 <= span <= 64 else 1
        return 1

    def handle_starttag(
        self,
        tag: str,
        attrs: list[tuple[str, str | None]],
    ) -> None:
        if tag == "table":
            if self._table_depth == 0:
                self._rows = []
                self._prefix = tuple(self._recent[-40:])
                self._row = None
                self._cell_parts = None
            self._table_depth += 1
            return
        if self._table_depth != 1:
            return
        if tag == "tr":
            self._row = []
            return
        if tag in {"td", "th"} and self._row is not None:
            self._cell_parts = []
            self._cell_colspan = self._span(attrs, "colspan")
            self._cell_rowspan = self._span(attrs, "rowspan")

    def handle_data(self, data: str) -> None:
        text = " ".join(data.replace("\u00a0", " ").split())
        if not text:
            return
        self._recent.append(text)
        if len(self._recent) > 200:
            del self._recent[:-200]
        if self._table_depth == 1 and self._cell_parts is not None:
            self._cell_parts.append(text)

    def handle_endtag(self, tag: str) -> None:
        if tag in {"td", "th"} and self._table_depth == 1:
            if self._row is not None and self._cell_parts is not None:
                self._row.append(
                    _RawCell(
                        text=" ".join(self._cell_parts).strip(),
                        colspan=self._cell_colspan,
                        rowspan=self._cell_rowspan,
                    )
                )
            self._cell_parts = None
            self._cell_colspan = 1
            self._cell_rowspan = 1
            return
        if tag == "tr" and self._table_depth == 1:
            if self._rows is not None and self._row:
                self._rows.append(tuple(self._row))
            self._row = None
            return
        if tag == "table" and self._table_depth > 0:
            self._table_depth -= 1
            if self._table_depth == 0:
                if self._rows:
                    self.tables.append(
                        _RawTable(rows=tuple(self._rows), prefix_text=self._prefix)
                    )
                self._rows = None
                self._row = None
                self._cell_parts = None


def _grid(table: _RawTable) -> tuple[tuple[str, ...], ...]:
    active: dict[int, tuple[int, str]] = {}
    row_maps: list[dict[int, str]] = []
    max_width = 0
    for raw_row in table.rows:
        row_map = {column: value for column, (_remaining, value) in active.items()}
        next_active: dict[int, tuple[int, str]] = {}
        for column, (remaining, value) in active.items():
            if remaining > 1:
                next_active[column] = (remaining - 1, value)
        column = 0
        for cell in raw_row:
            while column in row_map:
                column += 1
            for offset in range(cell.colspan):
                position = column + offset
                if position in row_map:
                    raise ValueError("OpenDART table colspan overlaps an active rowspan")
                row_map[position] = cell.text
                if cell.rowspan > 1:
                    next_active[position] = (cell.rowspan - 1, cell.text)
            column += cell.colspan
        active = next_active
        if row_map:
            max_width = max(max_width, max(row_map) + 1)
        row_maps.append(row_map)
    return tuple(
        tuple(row_map.get(column, "") for column in range(max_width))
        for row_map in row_maps
    )


def _normalized(value: str) -> str:
    return " ".join(value.split()).casefold()


def _row_index(
    grid: tuple[tuple[str, ...], ...],
    labels: tuple[str, ...],
    *,
    start: int,
) -> tuple[int, int]:
    accepted = {_normalized(label) for label in labels}
    matches: list[tuple[int, int]] = []
    for row_index in range(start, len(grid)):
        for column, value in enumerate(grid[row_index]):
            if _normalized(value) in accepted:
                matches.append((row_index, column))
    if not matches:
        raise ValueError(f"OpenDART structured product row missing: {labels[0]}")
    return matches[0]


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


def _contains_any(tokens: tuple[str, ...], markers: tuple[str, ...]) -> bool:
    folded = tuple(_normalized(token) for token in tokens)
    return any(
        _normalized(marker) in token
        for marker in markers
        for token in folded
    )


def _find_current_three_month_column(
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
        current = _contains_any(tokens, _CURRENT_MARKERS)
        prior = _contains_any(tokens, _PRIOR_MARKERS)
        three_month = _contains_any(tokens, (_THREE_MONTH_MARKER,))
        cumulative = _contains_any(tokens, (_CUMULATIVE_MARKER,))
        if current and prior:
            raise ValueError("OpenDART product-revenue header mixes current/prior period")
        if current and three_month and not cumulative:
            current_three_month.append(column)
        if current and cumulative and not three_month:
            current_cumulative.append(column)
        if prior and three_month and not cumulative:
            prior_three_month.append(column)
    if len(current_three_month) != 1:
        raise ValueError(
            "OpenDART current three-month product-revenue column must be unique: "
            f"count={len(current_three_month)}"
        )
    if len(current_cumulative) != 1 or len(prior_three_month) != 1:
        raise ValueError("OpenDART product-revenue header lacks current/prior period structure")
    return current_three_month[0]


def _unit(table: _RawTable, grid: tuple[tuple[str, ...], ...]) -> tuple[str, float]:
    context = "\n".join(
        (*table.prefix_text, *(cell for row in grid for cell in row if cell))
    )
    found = [normalized for marker, normalized in _UNIT_MARKERS.items() if marker in context]
    unique = list(dict.fromkeys(found))
    if len(unique) != 1:
        raise ValueError("OpenDART structured product table requires one supported KRW unit")
    return unique[0]


def _amount_at(
    grid: tuple[tuple[str, ...], ...],
    *,
    row: int,
    column: int,
    label: str,
) -> float:
    if column >= len(grid[row]):
        raise ValueError(f"OpenDART structured {label} row lacks current-quarter column")
    value = _parse_amount(grid[row][column])
    if value is None:
        raise ValueError(f"OpenDART structured {label} current-quarter amount is invalid")
    return value


def _metrics_from_table(
    spec: PeriodicProductRevenueSpec,
    table: _RawTable,
) -> ProductRevenueMetrics:
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
        raise ValueError("OpenDART product labels do not share one table label column")
    current_column = _find_current_three_month_column(
        grid,
        product_row=dram_row,
        label_column=label_column,
    )
    unit, scale = _unit(table, grid)
    dram = _amount_at(grid, row=dram_row, column=current_column, label="DRAM") * scale
    nand = _amount_at(grid, row=nand_row, column=current_column, label="NAND") * scale
    other = _amount_at(grid, row=other_row, column=current_column, label="Other") * scale
    total = _amount_at(grid, row=total_row, column=current_column, label="Total") * scale
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


def parse_periodic_product_revenue_archive(
    spec: PeriodicProductRevenueSpec,
    archive_bytes: bytes,
) -> ProductRevenueMetrics:
    """Rebuild table geometry and read the unique current-period three-month column."""

    if spec.parser_id != "skhynix_opendart_half_year_product_revenue_2026q2_v1":
        raise ValueError("Unsupported periodic product revenue structural parser_id")
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
                    candidates.append(_metrics_from_table(spec, table))
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
    if len(unique) != 1:
        raise ValueError(
            "OpenDART structured current-quarter product revenue must resolve uniquely: "
            f"candidates={len(unique)}"
        )
    return next(iter(unique.values()))


__all__ = ["parse_periodic_product_revenue_archive"]
