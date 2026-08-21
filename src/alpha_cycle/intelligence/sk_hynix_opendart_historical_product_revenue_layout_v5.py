"""Strict archive parser for the observed 2016 SK hynix product-revenue note layout.

The 2016 filings place the direct product table immediately after a local product-detail
sentence rather than requiring a numbered ``매출액`` note heading to remain within the
parser prefix window. This parser is deliberately period-scoped and does not loosen the
generic historical parser. A table is eligible only when nearby source context identifies
the applicable Q1/Q2 product-detail disclosure, DRAM/NAND/Other/Total are direct rows in
canonical order, and one supported KRW unit is present.

The observed source also spaces Korean row labels (for example ``기 타`` and ``합 계``).
Only this 2016 parser compares direct row labels after removing whitespace; it does not
apply fuzzy matching or derive values by subtraction.

Q1 accepts the unique direct ``당분기`` column because the reporting period itself is
exactly three months. Q2 accepts only the unique ``당반기 3개월`` column and requires
both current/prior cumulative structure. No value is derived by subtraction.
"""

from __future__ import annotations

import io
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
    _RawTable,
    _TableExtractor,
)
from alpha_cycle.intelligence.sk_hynix_opendart_q2_product_revenue_table import (
    _unit as _structured_unit,
)
from alpha_cycle.providers.opendart_documents import _decode_text, _safe_member_name

_HISTORICAL_PARSER_ID = "skhynix_opendart_periodic_product_revenue_v1"
_TEXT_SUFFIXES = frozenset({".xml", ".html", ".htm", ".xhtml"})
_Q1_PRODUCT_DETAIL_MARKERS = (
    "당분기와전분기중매출액의품목별세부내역",
    "당분기및전분기중매출액의품목별세부내역",
)
_Q2_PRODUCT_DETAIL_MARKERS = (
    "당반기와전반기중매출액의품목별세부내역",
    "당반기및전반기중매출액의품목별세부내역",
)
_CURRENT_MARKERS = ("당반기", "당분기", "당기")
_PRIOR_MARKERS = ("전반기", "전분기", "전기")
_THREE_MONTH = "3개월"
_CUMULATIVE = "누적"


def _period_kind(spec: PeriodicProductRevenueSpec) -> str:
    if spec.parser_id != _HISTORICAL_PARSER_ID:
        raise ValueError("Historical layout-v5 requires the historical parser id")
    if spec.period_end.year != 2016 or spec.period_start.year != 2016:
        raise ValueError("Historical layout-v5 is limited to observed 2016 Q1/Q2 layouts")
    if spec.period_start == date(2016, 1, 1) and spec.period_end == date(2016, 3, 31):
        return "q1"
    if spec.period_start == date(2016, 4, 1) and spec.period_end == date(2016, 6, 30):
        return "q2"
    raise ValueError("Historical layout-v5 is limited to observed 2016 Q1/Q2 layouts")


def _compact(value: str) -> str:
    return "".join(value.replace("\u00a0", " ").split()).casefold()


def _has_local_product_detail_context(table: _RawTable, *, period_kind: str) -> bool:
    nearby = "".join(_compact(value) for value in table.prefix_text[-48:])
    markers = _Q1_PRODUCT_DETAIL_MARKERS if period_kind == "q1" else _Q2_PRODUCT_DETAIL_MARKERS
    return any(marker in nearby for marker in markers)


def _accepted(labels: tuple[str, ...]) -> frozenset[str]:
    return frozenset(_compact(label) for label in labels)


def _unique_row_index(
    grid: tuple[tuple[str, ...], ...],
    labels: tuple[str, ...],
    *,
    start: int,
    label: str,
) -> tuple[int, int]:
    accepted = _accepted(labels)
    matches = [
        (row_index, column)
        for row_index in range(start, len(grid))
        for column, value in enumerate(grid[row_index])
        if _compact(value) in accepted
    ]
    if len(matches) != 1:
        raise ValueError(
            f"Historical layout-v5 {label} row must resolve uniquely: count={len(matches)}"
        )
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
    folded = tuple(_compact(token) for token in tokens)
    return any(_compact(marker) in token for marker in markers for token in folded)


def _q1_current_column(
    grid: tuple[tuple[str, ...], ...],
    *,
    product_row: int,
    label_column: int,
) -> int:
    current: list[int] = []
    prior: list[int] = []
    for column in range(label_column + 1, len(grid[product_row])):
        tokens = _header_tokens(grid, row_end=product_row, column=column)
        is_current = _contains_any(tokens, _CURRENT_MARKERS)
        is_prior = _contains_any(tokens, _PRIOR_MARKERS)
        cumulative = _contains_any(tokens, (_CUMULATIVE,))
        if is_current and is_prior:
            raise ValueError("Historical layout-v5 Q1 header mixes current/prior period")
        if cumulative:
            raise ValueError("Historical layout-v5 Q1 direct-quarter table cannot be cumulative")
        if is_current:
            current.append(column)
        if is_prior:
            prior.append(column)
    if len(current) != 1 or len(prior) != 1:
        raise ValueError(
            "Historical layout-v5 Q1 requires unique current/prior direct-period columns"
        )
    return current[0]


def _q2_current_three_month_column(
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
        current = _contains_any(tokens, _CURRENT_MARKERS)
        prior = _contains_any(tokens, _PRIOR_MARKERS)
        three_month = _contains_any(tokens, (_THREE_MONTH,))
        cumulative = _contains_any(tokens, (_CUMULATIVE,))
        if current and prior:
            raise ValueError("Historical layout-v5 Q2 header mixes current/prior period")
        if current and three_month and not cumulative:
            current_three_month.append(column)
        if current and cumulative and not three_month:
            current_cumulative.append(column)
        if prior and three_month and not cumulative:
            prior_three_month.append(column)
        if prior and cumulative and not three_month:
            prior_cumulative.append(column)
    if not all(
        len(columns) == 1
        for columns in (
            current_three_month,
            current_cumulative,
            prior_three_month,
            prior_cumulative,
        )
    ):
        raise ValueError(
            "Historical layout-v5 Q2 requires unique current/prior 3-month and cumulative columns"
        )
    return current_three_month[0]


def _amount_at(
    grid: tuple[tuple[str, ...], ...],
    *,
    row: int,
    column: int,
    label: str,
) -> float:
    if column >= len(grid[row]):
        raise ValueError(f"Historical layout-v5 {label} amount is missing")
    amount = _parse_amount(grid[row][column])
    if amount is None:
        raise ValueError(f"Historical layout-v5 {label} amount is invalid")
    return amount


def _table_metrics(
    spec: PeriodicProductRevenueSpec,
    table: _RawTable,
    *,
    period_kind: str,
) -> ProductRevenueMetrics:
    if not _has_local_product_detail_context(table, period_kind=period_kind):
        raise ValueError("Historical layout-v5 table lacks local product-detail context")
    grid = _grid(table)
    dram_row, label_column = _unique_row_index(
        grid,
        spec.product_labels["dram_total"],
        start=0,
        label="DRAM",
    )
    nand_row, nand_column = _unique_row_index(
        grid,
        spec.product_labels["nand_and_solutions"],
        start=dram_row + 1,
        label="NAND",
    )
    other_row, other_column = _unique_row_index(
        grid,
        spec.product_labels["other_products_services"],
        start=nand_row + 1,
        label="Other",
    )
    total_row, total_column = _unique_row_index(
        grid,
        spec.product_labels["reported_company_revenue"],
        start=other_row + 1,
        label="Total",
    )
    if not (dram_row < nand_row < other_row < total_row):
        raise ValueError("Historical layout-v5 product rows are not in canonical order")
    if len({label_column, nand_column, other_column, total_column}) != 1:
        raise ValueError("Historical layout-v5 product labels do not share one label column")

    current_column = (
        _q1_current_column(
            grid,
            product_row=dram_row,
            label_column=label_column,
        )
        if period_kind == "q1"
        else _q2_current_three_month_column(
            grid,
            product_row=dram_row,
            label_column=label_column,
        )
    )
    unit, scale = _structured_unit(table, grid)
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


def parse_historical_product_revenue_archive_v5(
    spec: PeriodicProductRevenueSpec,
    archive_bytes: bytes,
) -> ProductRevenueMetrics:
    """Parse the unique directly reported product-revenue table in 2016 Q1/Q2 filings."""

    period_kind = _period_kind(spec)
    try:
        archive = zipfile.ZipFile(io.BytesIO(archive_bytes))
    except zipfile.BadZipFile as exc:
        raise ValueError("Historical layout-v5 product-revenue source is not a ZIP") from exc

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
                    parsed.append(_table_metrics(spec, table, period_kind=period_kind))
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
            "Historical layout-v5 2016 product revenue must resolve uniquely: "
            f"candidates={len(unique)}"
        )
    return next(iter(unique.values()))


__all__ = ["parse_historical_product_revenue_archive_v5"]
