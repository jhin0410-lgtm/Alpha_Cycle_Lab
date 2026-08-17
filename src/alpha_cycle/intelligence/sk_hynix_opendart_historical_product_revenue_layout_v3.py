"""Narrow fallbacks for the remaining observed SK hynix historical OpenDART layouts.

This module handles only source shapes demonstrated by preserved raw evidence after the
layout-v2 parser was replayed:

* 2023 non-Q1 row tables whose cumulative marker is rendered with internal whitespace
  (for example ``누 적``); and
* 2024+ Q1 connected product tables rendered as an exact three-table sequence of
  current header, numeric data, and prior-period header.  The revenue label and current
  values are witnessed in the prior header's bounded raw prefix because the source HTML
  places the label outside the numeric table.

No product value is derived by subtraction.  DRAM, NAND, Other, and Total must all be
present directly, the direct sum must reconcile, and this parser remains behind the
existing strict parser families in production dispatch.
"""

from __future__ import annotations

import io
import re
import zipfile
from pathlib import PurePosixPath

from alpha_cycle.intelligence.sk_hynix_opendart_historical_product_revenue_fallback import (
    HISTORICAL_PRODUCT_REVENUE_PARSER_ID,
    _accepted,
    _amount_at,
    _is_q1,
    _metrics,
    _normalize_lines,
    _row_index,
)
from alpha_cycle.intelligence.sk_hynix_opendart_historical_product_revenue_layout_v2 import (
    _CONNECTED_NOTE_HEADING,
    _LEGACY_2023_CONNECTED_HEADING,
    _nearest_note_heading,
    _nearest_period,
    _unique_header_column,
    parse_historical_product_revenue_text_v2,
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
_CURRENT_MARKERS = ("당반기", "당분기", "당기")
_PRIOR_MARKERS = ("전반기", "전분기", "전기")
_REVENUE_LABELS = ("수익", "수익(매출액)", "수익 (매출액)")


def _require_bound_spec(spec: PeriodicProductRevenueSpec) -> None:
    if spec.parser_id != HISTORICAL_PRODUCT_REVENUE_PARSER_ID:
        raise ValueError("Historical layout-v3 parser_id is not bound")


def _compact(value: str) -> str:
    return re.sub(r"\s+", "", value).casefold()


def _contains_compact(tokens: tuple[str, ...], marker: str) -> bool:
    target = _compact(marker)
    return any(target in _compact(token) for token in tokens)


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


def _current_three_month_column_whitespace_tolerant(
    grid: tuple[tuple[str, ...], ...],
    *,
    product_row: int,
    label_column: int,
) -> int:
    current_three_month: list[int] = []
    current_cumulative: list[int] = []
    prior_three_month: list[int] = []
    prior_cumulative: list[int] = []
    for column in range(label_column + 1, len(grid[product_row])):
        tokens = _header_tokens(grid, row_end=product_row, column=column)
        current = any(_contains_compact(tokens, marker) for marker in _CURRENT_MARKERS)
        prior = any(_contains_compact(tokens, marker) for marker in _PRIOR_MARKERS)
        three_month = _contains_compact(tokens, "3개월")
        cumulative = _contains_compact(tokens, "누적")
        if current and prior:
            raise ValueError("Historical layout-v3 2023 header mixes current/prior period")
        if current and three_month and not cumulative:
            current_three_month.append(column)
        if current and cumulative and not three_month:
            current_cumulative.append(column)
        if prior and three_month and not cumulative:
            prior_three_month.append(column)
        if prior and cumulative and not three_month:
            prior_cumulative.append(column)
    if tuple(
        len(values)
        for values in (
            current_three_month,
            current_cumulative,
            prior_three_month,
            prior_cumulative,
        )
    ) != (1, 1, 1, 1):
        raise ValueError(
            "Historical layout-v3 2023 header must expose one current/prior "
            "3-month and cumulative column"
        )
    return current_three_month[0]


def _legacy_2023_non_q1_table_metrics(
    spec: PeriodicProductRevenueSpec,
    table: _RawTable,
) -> ProductRevenueMetrics:
    heading = _nearest_note_heading(table)
    if spec.period_end.year != 2023 or _is_q1(spec) or heading is None:
        raise ValueError("Historical layout-v3 table is not a 2023 non-Q1 candidate")
    if _LEGACY_2023_CONNECTED_HEADING.fullmatch(heading) is None:
        raise ValueError("Historical layout-v3 2023 table is outside consolidated legacy note")

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
        raise ValueError("Historical layout-v3 2023 product labels must share one column")
    current_column = _current_three_month_column_whitespace_tolerant(
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
            f"Historical layout-v3 {family} must resolve uniquely: candidates={len(unique)}"
        )
    return next(iter(unique.values()))


def _rewrite_cumulative_marker_lines(text: str) -> str:
    lines = _normalize_lines(text)
    rewritten = tuple("누적" if _compact(line) == "누적" else line for line in lines)
    return "\n".join(rewritten)


def parse_historical_product_revenue_text_v3(
    spec: PeriodicProductRevenueSpec,
    text: str,
) -> ProductRevenueMetrics:
    """Accept only the observed 2023 non-Q1 whitespace variant in normalized text."""

    _require_bound_spec(spec)
    if spec.period_end.year != 2023 or _is_q1(spec):
        raise ValueError("Historical layout-v3 text family is not applicable")
    return parse_historical_product_revenue_text_v2(
        spec,
        _rewrite_cumulative_marker_lines(text),
    )


def _numeric_grid_values(grid: tuple[tuple[str, ...], ...]) -> tuple[float, ...]:
    return tuple(
        amount
        for row in grid
        for token in row
        if (amount := _parse_amount(token)) is not None
    )


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
        raise ValueError("Historical layout-v3 Q1 witness lacks prior-quarter boundary")
    prior_index = prior_positions[-1]
    revenue = _accepted(_REVENUE_LABELS)
    revenue_positions = [
        index
        for index, token in enumerate(prefix[:prior_index])
        if _normalized(token) in revenue
    ]
    if not revenue_positions:
        raise ValueError("Historical layout-v3 Q1 witness lacks current revenue label")
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
            raise ValueError("Historical layout-v3 Q1 product label is ambiguous")
        if matches:
            categories.append(matches[0])
    if tuple(categories[-4:]) != ("dram", "nand", "other", "total"):
        raise ValueError("Historical layout-v3 Q1 witness lacks canonical product labels")

    amounts = tuple(
        amount
        for token in prefix[revenue_index + 1 : prior_index]
        if (amount := _parse_amount(token)) is not None
    )
    if len(amounts) != 4:
        raise ValueError(
            "Historical layout-v3 Q1 witness requires four direct current amounts: "
            f"count={len(amounts)}"
        )
    return amounts[0], amounts[1], amounts[2], amounts[3]


def _q1_three_table_metrics(
    spec: PeriodicProductRevenueSpec,
    header: _RawTable,
    data: _RawTable,
    witness: _RawTable,
) -> ProductRevenueMetrics:
    if spec.period_end.year < 2024 or not _is_q1(spec):
        raise ValueError("Historical layout-v3 Q1 family is limited to 2024+")
    heading = _nearest_note_heading(header)
    if heading is None or _CONNECTED_NOTE_HEADING.fullmatch(heading) is None:
        raise ValueError("Historical layout-v3 Q1 header is outside connected revenue note")
    if _nearest_note_heading(data) != heading or _nearest_note_heading(witness) != heading:
        raise ValueError("Historical layout-v3 Q1 tables do not share one connected note")
    if _nearest_period(header) != "당분기" or _nearest_period(data) != "당분기":
        raise ValueError("Historical layout-v3 Q1 current header/data scope is invalid")
    if _nearest_period(witness) != "전분기":
        raise ValueError("Historical layout-v3 Q1 witness is not the prior-quarter header")

    header_grid = _grid(header)
    columns = {
        "dram": _unique_header_column(
            header_grid,
            spec.product_labels["dram_total"],
            label="DRAM",
        ),
        "nand": _unique_header_column(
            header_grid,
            spec.product_labels["nand_and_solutions"],
            label="NAND",
        ),
        "other": _unique_header_column(
            header_grid,
            spec.product_labels["other_products_services"],
            label="Other",
        ),
        "total": _unique_header_column(
            header_grid,
            spec.product_labels["reported_company_revenue"],
            label="Total",
        ),
    }
    if tuple(columns.values()) != tuple(sorted(columns.values())):
        raise ValueError("Historical layout-v3 Q1 product header order is not canonical")

    witnessed = _prefix_current_values(spec, witness)
    data_values = _numeric_grid_values(_grid(data))
    if data_values != witnessed:
        raise ValueError(
            "Historical layout-v3 Q1 numeric data table does not match prefix witness"
        )
    unit, scale = _structured_unit(header, header_grid)
    return _metrics(
        unit=unit,
        scale=scale,
        dram=witnessed[0],
        nand=witnessed[1],
        other=witnessed[2],
        total=witnessed[3],
    )


def parse_historical_product_revenue_archive_v3(
    spec: PeriodicProductRevenueSpec,
    archive_bytes: bytes,
) -> ProductRevenueMetrics:
    """Parse only the two remaining raw layout families demonstrated by evidence."""

    _require_bound_spec(spec)
    try:
        archive = zipfile.ZipFile(io.BytesIO(archive_bytes))
    except zipfile.BadZipFile as exc:
        raise ValueError("Historical layout-v3 source is not a ZIP") from exc

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
            for index, table in enumerate(parser.tables):
                if spec.period_end.year == 2023 and not _is_q1(spec):
                    try:
                        candidates.append(_legacy_2023_non_q1_table_metrics(spec, table))
                    except ValueError:
                        pass
                    continue
                if spec.period_end.year < 2024 or not _is_q1(spec):
                    continue
                if index + 2 >= len(parser.tables):
                    continue
                try:
                    candidates.append(
                        _q1_three_table_metrics(
                            spec,
                            table,
                            parser.tables[index + 1],
                            parser.tables[index + 2],
                        )
                    )
                except ValueError:
                    continue
    family = "2023_whitespace_row_archive" if spec.period_end.year == 2023 else "q1_three_table_archive"
    return _resolve_unique(candidates, family=family)


__all__ = [
    "parse_historical_product_revenue_archive_v3",
    "parse_historical_product_revenue_text_v3",
]
