"""Bounded raw-table diagnostics for failed SK hynix historical product revenue.

The normalized-text failure signature is useful for broad document structure, but it can
center on unrelated business-description DRAM mentions. This module instead inspects the
already preserved, hash-verified OpenDART ZIP and emits bounded signatures only for HTML
or XML tables that are plausibly tied to a revenue note. It does not parse or promote a
product-revenue source fact.
"""

from __future__ import annotations

import io
import re
import zipfile
from dataclasses import asdict, dataclass
from pathlib import Path, PurePosixPath

from alpha_cycle.intelligence.sk_hynix_historical_product_failure_diagnostics import (
    HistoricalProductRevenueFailureDiagnostic,
)
from alpha_cycle.intelligence.sk_hynix_opendart_historical_product_revenue_fallback import (
    _row_table_metrics,
)
from alpha_cycle.intelligence.sk_hynix_opendart_q2_product_revenue_certification import (
    PeriodicProductRevenueSpec,
)
from alpha_cycle.intelligence.sk_hynix_opendart_q2_product_revenue_table import (
    _grid,
    _normalized,
    _RawTable,
    _TableExtractor,
)
from alpha_cycle.providers.opendart_documents import _decode_text, _safe_member_name

_TEXT_SUFFIXES = frozenset({".xml", ".html", ".htm", ".xhtml"})
_CURRENT_MARKERS = ("당반기", "당분기", "당기")
_PRIOR_MARKERS = ("전반기", "전분기", "전기")
_REVENUE_ROW_LABELS = ("수익", "수익(매출액)", "수익 (매출액)")
_REVENUE_NOTE_HEADING = re.compile(r"^\s*\d+\.\s*매출액(?:\s*\(연결\))?.*$")
_UNIT_MARKERS = ("백만원", "억원")
_MAX_SIGNATURES = 12
_MAX_PREFIX_LINES = 12
_MAX_GRID_ROWS = 14
_MAX_GRID_COLUMNS = 16
_MAX_TEXT_CHARS = 140


def _accepted(labels: tuple[str, ...]) -> frozenset[str]:
    return frozenset(_normalized(value) for value in labels)


def _positions(
    grid: tuple[tuple[str, ...], ...],
    labels: tuple[str, ...],
) -> tuple[tuple[int, int], ...]:
    accepted = _accepted(labels)
    return tuple(
        (row_index, column_index)
        for row_index, row in enumerate(grid)
        for column_index, value in enumerate(row)
        if _normalized(value) in accepted
    )


def _tokens(
    prefix: tuple[str, ...],
    grid: tuple[tuple[str, ...], ...],
) -> tuple[str, ...]:
    return (*prefix, *(value for row in grid for value in row if value.strip()))


def _observed_markers(
    tokens: tuple[str, ...],
    markers: tuple[str, ...],
) -> tuple[str, ...]:
    observed: list[str] = []
    for marker in markers:
        target = _normalized(marker)
        if any(target in _normalized(token) for token in tokens):
            observed.append(marker)
    return tuple(observed)


def _observed_units(tokens: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(marker for marker in _UNIT_MARKERS if any(marker in token for token in tokens))


def _nearest_revenue_heading(prefix: tuple[str, ...]) -> str | None:
    for value in reversed(prefix):
        normalized = " ".join(value.split())
        if _REVENUE_NOTE_HEADING.fullmatch(normalized) is not None:
            return normalized
    return None


def _trim(value: str) -> str:
    return " ".join(value.replace("\u00a0", " ").split())[:_MAX_TEXT_CHARS]


def _prefix_tail(prefix: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(_trim(value) for value in prefix[-_MAX_PREFIX_LINES:] if value.strip())


def _grid_excerpt(
    grid: tuple[tuple[str, ...], ...],
    positions: tuple[tuple[int, int], ...],
) -> tuple[int, tuple[tuple[str, ...], ...]]:
    first_row = min((row for row, _column in positions), default=0)
    start = max(0, first_row - 4)
    end = min(len(grid), start + _MAX_GRID_ROWS)
    excerpt = tuple(
        tuple(_trim(value) for value in row[:_MAX_GRID_COLUMNS])
        for row in grid[start:end]
    )
    return start, excerpt


def _historical_row_parser_result(
    spec: PeriodicProductRevenueSpec,
    table: _RawTable,
) -> tuple[bool, str | None]:
    """Explain whether the strict historical row parser accepts one raw table."""

    try:
        _row_table_metrics(spec, table)
    except ValueError as exc:
        return False, str(exc)
    return True, None


@dataclass(frozen=True)
class HistoricalProductRevenueRawTableSignature:
    member_name: str
    table_index: int
    score: int
    revenue_heading: str | None
    connected_heading: bool
    prefix_tail: tuple[str, ...]
    row_count: int
    column_count: int
    current_period_markers: tuple[str, ...]
    prior_period_markers: tuple[str, ...]
    unit_markers: tuple[str, ...]
    label_positions: dict[str, tuple[tuple[int, int], ...]]
    revenue_row_positions: tuple[tuple[int, int], ...]
    historical_row_parser_succeeded: bool
    historical_row_parser_error: str | None
    grid_row_start: int
    grid_excerpt: tuple[tuple[str, ...], ...]
    source_fact_promoted: bool = False

    def __post_init__(self) -> None:
        if self.historical_row_parser_succeeded != (self.historical_row_parser_error is None):
            raise ValueError("Historical raw-table parser diagnostic is inconsistent")
        if self.source_fact_promoted:
            raise ValueError("Historical raw-table diagnostics cannot promote source facts")

    def as_dict(self) -> dict[str, object]:
        return asdict(self)


def _signature(
    spec: PeriodicProductRevenueSpec,
    *,
    member_name: str,
    table_index: int,
    table: _RawTable,
    grid: tuple[tuple[str, ...], ...],
) -> HistoricalProductRevenueRawTableSignature | None:
    label_positions = {
        "dram_total": _positions(grid, spec.product_labels["dram_total"]),
        "nand_and_solutions": _positions(grid, spec.product_labels["nand_and_solutions"]),
        "other_products_services": _positions(
            grid,
            spec.product_labels["other_products_services"],
        ),
        "reported_company_revenue": _positions(
            grid,
            spec.product_labels["reported_company_revenue"],
        ),
    }
    revenue_positions = _positions(grid, _REVENUE_ROW_LABELS)
    product_families = sum(bool(value) for value in label_positions.values())
    heading = _nearest_revenue_heading(table.prefix_text)
    if heading is None and not revenue_positions:
        return None
    if product_families < 2 and not (heading is not None and revenue_positions):
        return None

    tokens = _tokens(table.prefix_text, grid)
    current = _observed_markers(tokens, _CURRENT_MARKERS)
    prior = _observed_markers(tokens, _PRIOR_MARKERS)
    units = _observed_units(tokens)
    connected = heading is not None and "(연결)" in heading.replace(" ", "")
    row_parser_succeeded, row_parser_error = _historical_row_parser_result(spec, table)
    score = (
        product_families * 3
        + (4 if heading is not None else 0)
        + (2 if connected else 0)
        + (2 if revenue_positions else 0)
        + (1 if current else 0)
        + (1 if prior else 0)
        + (1 if units else 0)
    )
    all_positions = tuple(
        position
        for positions in label_positions.values()
        for position in positions
    ) + revenue_positions
    row_start, excerpt = _grid_excerpt(grid, all_positions)
    width = max((len(row) for row in grid), default=0)
    return HistoricalProductRevenueRawTableSignature(
        member_name=member_name,
        table_index=table_index,
        score=score,
        revenue_heading=heading,
        connected_heading=connected,
        prefix_tail=_prefix_tail(table.prefix_text),
        row_count=len(grid),
        column_count=width,
        current_period_markers=current,
        prior_period_markers=prior,
        unit_markers=units,
        label_positions=label_positions,
        revenue_row_positions=revenue_positions,
        historical_row_parser_succeeded=row_parser_succeeded,
        historical_row_parser_error=row_parser_error,
        grid_row_start=row_start,
        grid_excerpt=excerpt,
    )


def build_failure_raw_table_signatures(
    diagnostic: HistoricalProductRevenueFailureDiagnostic,
    spec: PeriodicProductRevenueSpec,
) -> tuple[HistoricalProductRevenueRawTableSignature, ...]:
    """Inspect preserved raw source bytes and return bounded revenue-table signatures."""

    archive_bytes = Path(diagnostic.archive_path).read_bytes()
    try:
        archive = zipfile.ZipFile(io.BytesIO(archive_bytes))
    except zipfile.BadZipFile as exc:
        raise ValueError("Historical failure diagnostic source is not a ZIP") from exc

    signatures: list[HistoricalProductRevenueRawTableSignature] = []
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
            for table_index, table in enumerate(parser.tables):
                try:
                    grid = _grid(table)
                except ValueError:
                    continue
                item = _signature(
                    spec,
                    member_name=safe_name,
                    table_index=table_index,
                    table=table,
                    grid=grid,
                )
                if item is not None:
                    signatures.append(item)

    signatures.sort(
        key=lambda item: (-item.score, item.member_name, item.table_index)
    )
    return tuple(signatures[:_MAX_SIGNATURES])


__all__ = [
    "HistoricalProductRevenueRawTableSignature",
    "build_failure_raw_table_signatures",
]
