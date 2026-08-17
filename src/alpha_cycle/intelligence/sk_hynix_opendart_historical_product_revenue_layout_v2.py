"""Strict source-layout parser for observed SK hynix historical product revenue families.

This parser is intentionally narrow and is bound only to the historical product-revenue
parser id. It covers source shapes observed in preserved OpenDART evidence that the
current parser does not accept:

* 2023 filings: products are rows under the consolidated legacy note headed
  ``22. 매출액(1) ...``; and
* Q1 2024+ filings: product labels are columns in a current-period header table and the
  direct revenue row is the immediately adjacent table.

No amount is inferred from residuals or cumulative differences. DRAM, NAND, Other, and
Total must all be directly reported and reconcile through ``ProductRevenueMetrics``.
"""

from __future__ import annotations

import io
import re
import zipfile
from pathlib import PurePosixPath

from alpha_cycle.intelligence.sk_hynix_opendart_historical_product_revenue_fallback import (
    HISTORICAL_PRODUCT_REVENUE_PARSER_ID,
    _current_three_month_column,
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
_ANY_NOTE_HEADING = re.compile(r"^\s*\d+\.\s*.+$")
_CONNECTED_NOTE_HEADING = re.compile(r"^\s*\d+\.\s*매출액\s*\(연결\)\s*$")
_LEGACY_2023_CONNECTED_HEADING = re.compile(
    r"^\s*22\.\s*매출액\(1\)\s*당(?:분기|반기)와\s*전(?:분기|반기)\s*중\s*"
    r"매출액의\s*내역은\s*다음과\s*같습니다\.\s*$"
)


def _require_bound_spec(spec: PeriodicProductRevenueSpec) -> None:
    if spec.parser_id != HISTORICAL_PRODUCT_REVENUE_PARSER_ID:
        raise ValueError("Historical layout-v2 parser_id is not bound")


def _is_q1(spec: PeriodicProductRevenueSpec) -> bool:
    return spec.period_start.month == 1 and spec.period_end.month == 3


def _accepted(labels: tuple[str, ...]) -> frozenset[str]:
    return frozenset(_normalized(value) for value in labels)


def _normalize_lines(text: str) -> tuple[str, ...]:
    return tuple(
        " ".join(line.replace("\u00a0", " ").split())
        for line in text.splitlines()
        if line.strip()
    )


def _text_unit(lines: tuple[str, ...]) -> tuple[str, float]:
    found: list[tuple[str, float]] = []
    for line in lines:
        if "단위" not in line:
            continue
        if "백만원" in line:
            found.append(("KRW_million", 1.0))
        if "억원" in line:
            found.append(("KRW_million", 100.0))
    unique = list(dict.fromkeys(found))
    if len(unique) != 1:
        raise ValueError("Historical layout-v2 requires one supported KRW unit")
    return unique[0]


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


def _unique(
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
            f"Historical layout-v2 {family} must resolve uniquely: candidates={len(unique)}"
        )
    return next(iter(unique.values()))


def _section_from(lines: tuple[str, ...], start: int) -> tuple[str, ...]:
    end = len(lines)
    for position in range(start + 1, len(lines)):
        if _ANY_NOTE_HEADING.fullmatch(lines[position]) is not None:
            end = position
            break
    return lines[start:end]


def _label_index(lines: tuple[str, ...], labels: tuple[str, ...], *, start: int) -> int:
    accepted = _accepted(labels)
    for index in range(start, len(lines)):
        if _normalized(lines[index]) in accepted:
            return index
    raise ValueError(f"Historical layout-v2 label missing: {labels[0]}")


def _first_amount(
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
    raise ValueError(f"Historical layout-v2 amount missing: {label}")


def _legacy_2023_text_candidate(
    spec: PeriodicProductRevenueSpec,
    section: tuple[str, ...],
) -> ProductRevenueMetrics:
    if spec.period_end.year != 2023 or not _LEGACY_2023_CONNECTED_HEADING.fullmatch(section[0]):
        raise ValueError("Historical layout-v2 section is not the 2023 consolidated family")
    joined = "\n".join(section)
    if not any(marker in joined for marker in _CURRENT_MARKERS):
        raise ValueError("Historical 2023 row family lacks current-period marker")
    if not _is_q1(spec) and ("3개월" not in joined or "누적" not in joined):
        raise ValueError("Historical 2023 non-Q1 row family lacks 3-month/cumulative structure")

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
    unit, scale = _text_unit(section)
    return _metrics(
        unit=unit,
        scale=scale,
        dram=_first_amount(section, start=dram_index + 1, end=nand_index, label="DRAM"),
        nand=_first_amount(section, start=nand_index + 1, end=other_index, label="NAND"),
        other=_first_amount(section, start=other_index + 1, end=total_index, label="Other"),
        total=_first_amount(
            section,
            start=total_index + 1,
            end=min(len(section), total_index + 16),
            label="Total",
        ),
    )


def _connected_sections(lines: tuple[str, ...]) -> tuple[tuple[str, ...], ...]:
    return tuple(
        _section_from(lines, index)
        for index, line in enumerate(lines)
        if _CONNECTED_NOTE_HEADING.fullmatch(line) is not None
    )


def _q1_current_windows(section: tuple[str, ...]) -> tuple[tuple[str, ...], ...]:
    current = _accepted(("당분기",))
    prior = _accepted(("전분기",))
    windows: list[tuple[str, ...]] = []
    for start, value in enumerate(section):
        if _normalized(value) not in current:
            continue
        end = len(section)
        for position in range(start + 1, len(section)):
            if _normalized(section[position]) in prior:
                end = position
                break
        windows.append(section[start:end])
    return tuple(windows)


def _q1_column_text_candidate(
    spec: PeriodicProductRevenueSpec,
    section: tuple[str, ...],
    window: tuple[str, ...],
) -> ProductRevenueMetrics:
    if not _is_q1(spec):
        raise ValueError("Historical Q1 column family is unavailable outside Q1")
    dram_index = _label_index(window, spec.product_labels["dram_total"], start=0)
    nand_index = _label_index(
        window,
        spec.product_labels["nand_and_solutions"],
        start=dram_index + 1,
    )
    other_index = _label_index(
        window,
        spec.product_labels["other_products_services"],
        start=nand_index + 1,
    )
    total_index = _label_index(
        window,
        spec.product_labels["reported_company_revenue"],
        start=other_index + 1,
    )
    revenue_index = _label_index(window, _REVENUE_LABELS, start=total_index + 1)
    amounts = tuple(
        amount
        for token in window[revenue_index + 1 :]
        if (amount := _parse_amount(token)) is not None
    )
    if len(amounts) != 4:
        raise ValueError(
            "Historical Q1 current revenue row must contain four direct amounts: "
            f"count={len(amounts)}"
        )
    unit, scale = _text_unit(section)
    return _metrics(
        unit=unit,
        scale=scale,
        dram=amounts[0],
        nand=amounts[1],
        other=amounts[2],
        total=amounts[3],
    )


def parse_historical_product_revenue_text_v2(
    spec: PeriodicProductRevenueSpec,
    text: str,
) -> ProductRevenueMetrics:
    """Parse only the evidence-bound 2023 row or Q1 split-column historical families."""

    _require_bound_spec(spec)
    lines = _normalize_lines(text)
    if not lines:
        raise ValueError("Historical layout-v2 normalized text is empty")
    folded = "\n".join(lines).casefold()
    for anchor in spec.expected_identity_anchors:
        if _normalized(anchor) not in folded:
            raise ValueError(f"Historical layout-v2 identity anchor missing: {anchor}")

    if spec.period_end.year == 2023:
        candidates = [
            _legacy_2023_text_candidate(spec, _section_from(lines, index))
            for index, line in enumerate(lines)
            if _LEGACY_2023_CONNECTED_HEADING.fullmatch(line) is not None
        ]
        return _unique(candidates, family="2023_row_text")

    if _is_q1(spec):
        candidates: list[ProductRevenueMetrics] = []
        for section in _connected_sections(lines):
            for window in _q1_current_windows(section):
                try:
                    candidates.append(_q1_column_text_candidate(spec, section, window))
                except ValueError:
                    continue
        return _unique(candidates, family="q1_current_column_text")

    raise ValueError("Historical layout-v2 text family is not applicable")


def _nearest_note_heading(table: _RawTable) -> str | None:
    for value in reversed(table.prefix_text):
        normalized = " ".join(value.split())
        if _ANY_NOTE_HEADING.fullmatch(normalized) is not None:
            return normalized
    return None


def _nearest_period(table: _RawTable) -> str | None:
    accepted = {
        _normalized(value): value
        for value in (*_CURRENT_MARKERS, *_PRIOR_MARKERS)
    }
    for value in reversed(table.prefix_text):
        normalized = _normalized(value)
        if normalized in accepted:
            return accepted[normalized]
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
    raise ValueError(f"Historical layout-v2 structured row missing: {labels[0]}")


def _amount_at(
    grid: tuple[tuple[str, ...], ...],
    *,
    row: int,
    column: int,
    label: str,
) -> float:
    if column >= len(grid[row]):
        raise ValueError(f"Historical layout-v2 structured amount missing: {label}")
    amount = _parse_amount(grid[row][column])
    if amount is None:
        raise ValueError(f"Historical layout-v2 structured amount invalid: {label}")
    return amount


def _legacy_q1_current_column(
    grid: tuple[tuple[str, ...], ...],
    *,
    product_row: int,
    label_column: int,
) -> int:
    current: list[int] = []
    for column in range(label_column + 1, len(grid[product_row])):
        tokens = tuple(
            row[column]
            for row in grid[:product_row]
            if column < len(row) and row[column].strip()
        )
        folded = tuple(_normalized(token) for token in tokens)
        is_current = any(_normalized(marker) in token for marker in ("당분기",) for token in folded)
        is_prior = any(_normalized(marker) in token for marker in ("전분기",) for token in folded)
        if is_current and not is_prior:
            current.append(column)
    if len(current) != 1:
        raise ValueError(
            "Historical 2023 Q1 current product column must be unique: "
            f"count={len(current)}"
        )
    return current[0]


def _legacy_2023_table_metrics(
    spec: PeriodicProductRevenueSpec,
    table: _RawTable,
) -> ProductRevenueMetrics:
    heading = _nearest_note_heading(table)
    if spec.period_end.year != 2023 or heading is None:
        raise ValueError("Historical table is not a 2023 legacy candidate")
    if _LEGACY_2023_CONNECTED_HEADING.fullmatch(heading) is None:
        raise ValueError("Historical 2023 table is outside the consolidated legacy note")
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
        raise ValueError("Historical 2023 product labels do not share one row-label column")
    current_column = (
        _legacy_q1_current_column(
            grid,
            product_row=dram_row,
            label_column=label_column,
        )
        if _is_q1(spec)
        else _current_three_month_column(
            spec,
            grid,
            product_row=dram_row,
            label_column=label_column,
        )
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


def _unique_header_column(
    grid: tuple[tuple[str, ...], ...],
    labels: tuple[str, ...],
    *,
    label: str,
) -> int:
    accepted = _accepted(labels)
    positions = {
        column
        for row in grid
        for column, value in enumerate(row)
        if _normalized(value) in accepted
    }
    if len(positions) != 1:
        raise ValueError(
            f"Historical Q1 {label} header column must be unique: count={len(positions)}"
        )
    return next(iter(positions))


def _revenue_row(grid: tuple[tuple[str, ...], ...]) -> tuple[int, int]:
    accepted = _accepted(_REVENUE_LABELS)
    matches = [
        (row_index, column)
        for row_index, row in enumerate(grid)
        for column, value in enumerate(row)
        if _normalized(value) in accepted
    ]
    if len(matches) != 1:
        raise ValueError(
            "Historical Q1 adjacent data table requires one revenue row: "
            f"count={len(matches)}"
        )
    return matches[0]


def _q1_split_table_metrics(
    spec: PeriodicProductRevenueSpec,
    header: _RawTable,
    data: _RawTable,
) -> ProductRevenueMetrics:
    if not _is_q1(spec):
        raise ValueError("Historical Q1 split parser is unavailable outside Q1")
    heading = _nearest_note_heading(header)
    if heading is None or _CONNECTED_NOTE_HEADING.fullmatch(heading) is None:
        raise ValueError("Historical Q1 header is outside consolidated revenue note")
    if _nearest_period(header) != "당분기":
        raise ValueError("Historical Q1 header is outside current quarter")
    if _nearest_period(data) in _PRIOR_MARKERS:
        raise ValueError("Historical Q1 adjacent data table crossed into prior period")

    header_grid = _grid(header)
    data_grid = _grid(data)
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
        raise ValueError("Historical Q1 product header order is not canonical")
    revenue_row, label_column = _revenue_row(data_grid)
    if label_column != 0:
        raise ValueError("Historical Q1 revenue row label must occupy first column")
    unit, scale = _structured_unit(header, header_grid)
    return _metrics(
        unit=unit,
        scale=scale,
        dram=_amount_at(data_grid, row=revenue_row, column=columns["dram"], label="DRAM"),
        nand=_amount_at(data_grid, row=revenue_row, column=columns["nand"], label="NAND"),
        other=_amount_at(data_grid, row=revenue_row, column=columns["other"], label="Other"),
        total=_amount_at(data_grid, row=revenue_row, column=columns["total"], label="Total"),
    )


def parse_historical_product_revenue_archive_v2(
    spec: PeriodicProductRevenueSpec,
    archive_bytes: bytes,
) -> ProductRevenueMetrics:
    """Parse the evidence-bound historical raw-table families from retained ZIP bytes."""

    _require_bound_spec(spec)
    try:
        archive = zipfile.ZipFile(io.BytesIO(archive_bytes))
    except zipfile.BadZipFile as exc:
        raise ValueError("Historical layout-v2 source is not a ZIP") from exc

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
                if spec.period_end.year == 2023:
                    try:
                        candidates.append(_legacy_2023_table_metrics(spec, table))
                    except ValueError:
                        pass
                if not _is_q1(spec) or index + 1 >= len(parser.tables):
                    continue
                try:
                    candidates.append(
                        _q1_split_table_metrics(
                            spec,
                            table,
                            parser.tables[index + 1],
                        )
                    )
                except ValueError:
                    continue
    family = "2023_row_archive" if spec.period_end.year == 2023 else "q1_split_archive"
    return _unique(candidates, family=family)


__all__ = [
    "parse_historical_product_revenue_archive_v2",
    "parse_historical_product_revenue_text_v2",
]
