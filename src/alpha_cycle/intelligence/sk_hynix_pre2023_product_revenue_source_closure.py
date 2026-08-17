"""Exhaustively profile preserved pre-2023 SK hynix filings for separable product revenue.

The earlier expansion probe established that production parsers cannot resolve 2021Q1-Q3
or 2022Q1-Q3. This module answers a narrower source question before another parser family
is written: does the preserved official filing contain any table that directly separates
DRAM and NAND revenue, or does the business-report product section expose only an aggregate
bucket such as ``DRAM, NAND Flash, CIS 등``?

The audit is diagnostic only. A candidate is not a certification, absence of a candidate
is not a synthetic allocation license, and aggregate revenue is never split by assumption.
"""

from __future__ import annotations

import hashlib
import io
import json
import re
import zipfile
from dataclasses import asdict, dataclass
from pathlib import Path, PurePosixPath

from alpha_cycle.intelligence.sk_hynix_historical_product_failure_diagnostics import (
    HistoricalProductRevenueFailureDiagnostic,
    load_failure_diagnostic,
)
from alpha_cycle.intelligence.sk_hynix_opendart_q2_product_revenue_certification import (
    _parse_amount,
)
from alpha_cycle.intelligence.sk_hynix_opendart_q2_product_revenue_table import (
    _grid,
    _RawTable,
    _TableExtractor,
)
from alpha_cycle.intelligence.sk_hynix_product_profitability_historical_expansion_probe import (
    DEFAULT_PRODUCT_REVENUE_PROBE_OUTPUT,
)
from alpha_cycle.providers.opendart_documents import _decode_text, _safe_member_name

_EXPECTED_PERIODS = (
    "2021Q1",
    "2021Q2",
    "2021Q3",
    "2022Q1",
    "2022Q2",
    "2022Q3",
)
_TEXT_SUFFIXES = frozenset({".xml", ".html", ".htm", ".xhtml"})
_DRAM_EXACT = frozenset({"dram", "d ram", "d램", "디램"})
_NAND_EXACT = frozenset({"nand", "nand flash", "낸드", "낸드플래시", "플래시메모리"})
_REVENUE_MARKERS = ("매출액", "수익", "revenue")
_PRODUCT_MARKERS = ("주요 제품", "제품 등의 현황", "제품 및 서비스", "제품", "product")
_UNIT_MARKERS = ("백만원", "억원")
_COMBINED_BUCKET = re.compile(
    r"dram.*(?:nand|낸드)|(?:nand|낸드).*dram",
    flags=re.IGNORECASE,
)


def _norm(value: str) -> str:
    return " ".join(value.replace("\u00a0", " ").split()).casefold()


def _sha(payload: object) -> str:
    return hashlib.sha256(
        json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        ).encode("utf-8")
    ).hexdigest()


def _latest_diagnostic_path(period_root: Path) -> Path:
    failed = period_root / "failed"
    if not failed.is_dir():
        raise ValueError(f"Pre-2023 product-revenue failure root is missing: {period_root}")
    candidates = sorted(
        (item / "diagnostic.json" for item in failed.iterdir() if item.is_dir()),
        key=lambda path: path.parent.name,
        reverse=True,
    )
    path = next((item for item in candidates if item.is_file()), None)
    if path is None:
        raise ValueError(f"Pre-2023 product-revenue diagnostic is missing: {period_root}")
    return path


def _table_text(table: _RawTable, grid: tuple[tuple[str, ...], ...]) -> str:
    return "\n".join((*table.prefix_text, *(cell for row in grid for cell in row if cell)))


def _amounts(row: tuple[str, ...]) -> tuple[float, ...]:
    return tuple(amount for token in row if (amount := _parse_amount(token)) is not None)


def _exact_label(value: str, accepted: frozenset[str]) -> bool:
    return _norm(value) in accepted


def _label_rows(
    grid: tuple[tuple[str, ...], ...],
    accepted: frozenset[str],
) -> tuple[tuple[int, int], ...]:
    return tuple(
        (row_index, column)
        for row_index, row in enumerate(grid)
        for column, value in enumerate(row)
        if _exact_label(value, accepted)
    )


def _combined_bucket_cells(grid: tuple[tuple[str, ...], ...]) -> tuple[str, ...]:
    found: list[str] = []
    for row in grid:
        for value in row:
            normalized = _norm(value)
            if _COMBINED_BUCKET.search(normalized) is not None:
                found.append(value)
    return tuple(dict.fromkeys(found))


def _revenue_context(text: str) -> bool:
    folded = _norm(text)
    return any(marker in folded for marker in _REVENUE_MARKERS)


def _product_context(text: str) -> bool:
    folded = _norm(text)
    return any(marker in folded for marker in _PRODUCT_MARKERS)


def _unit_context(text: str) -> tuple[str, ...]:
    return tuple(marker for marker in _UNIT_MARKERS if marker in text)


@dataclass(frozen=True)
class ProductRevenueTableWitness:
    member_name: str
    table_index: int
    witness_kind: str
    prefix_tail: tuple[str, ...]
    rows: tuple[tuple[str, ...], ...]
    combined_bucket_cells: tuple[str, ...]
    dram_label_rows: tuple[tuple[int, int], ...]
    nand_label_rows: tuple[tuple[int, int], ...]
    direct_labeled_amount_row_count: int
    unit_markers: tuple[str, ...]

    def __post_init__(self) -> None:
        if self.witness_kind not in {"aggregate_bucket", "direct_separable_candidate"}:
            raise ValueError("Pre-2023 product-revenue witness kind is invalid")
        if self.table_index < 0 or not self.member_name or not self.rows:
            raise ValueError("Pre-2023 product-revenue witness is incomplete")
        if self.direct_labeled_amount_row_count < 0:
            raise ValueError("Pre-2023 direct labeled amount count is invalid")
        if self.witness_kind == "aggregate_bucket" and not self.combined_bucket_cells:
            raise ValueError("Aggregate product-revenue witness lacks combined bucket")
        if self.witness_kind == "direct_separable_candidate" and (
            not self.dram_label_rows or not self.nand_label_rows
        ):
            raise ValueError("Direct product-revenue candidate lacks separate labels")
        if not self.unit_markers:
            raise ValueError("Pre-2023 product-revenue witness lacks a KRW unit marker")


@dataclass(frozen=True)
class ProductRevenueSourceClosurePeriod:
    evidence_id: str
    period_id: str
    rcept_no: str
    archive_sha256: str
    member_count: int
    table_count: int
    aggregate_bucket_witnesses: tuple[ProductRevenueTableWitness, ...]
    direct_separable_candidates: tuple[ProductRevenueTableWitness, ...]
    aggregate_bucket_witness_count: int
    direct_separable_candidate_count: int
    exhaustive_preserved_archive_scan_complete: bool = True
    direct_product_revenue_certified: bool = False
    synthetic_product_allocation_allowed: bool = False
    training_row_promoted: bool = False
    fit_enabled: bool = False

    def __post_init__(self) -> None:
        if self.period_id not in _EXPECTED_PERIODS:
            raise ValueError("Pre-2023 source-closure period is unsupported")
        if len(self.evidence_id) != 64 or len(self.archive_sha256) != 64:
            raise ValueError("Pre-2023 source-closure hashes must be SHA-256")
        if self.member_count < 1 or self.table_count < 1:
            raise ValueError("Pre-2023 source-closure archive/table counts are invalid")
        if self.aggregate_bucket_witness_count != len(self.aggregate_bucket_witnesses):
            raise ValueError("Aggregate product-revenue witness count is inconsistent")
        if self.direct_separable_candidate_count != len(self.direct_separable_candidates):
            raise ValueError("Direct product-revenue candidate count is inconsistent")
        if not self.exhaustive_preserved_archive_scan_complete:
            raise ValueError("Pre-2023 source closure must scan the full preserved archive")
        if (
            self.direct_product_revenue_certified
            or self.synthetic_product_allocation_allowed
            or self.training_row_promoted
            or self.fit_enabled
        ):
            raise ValueError("Pre-2023 source closure exceeded diagnostic trust boundary")

    @property
    def aggregate_only_observed(self) -> bool:
        return (
            self.aggregate_bucket_witness_count > 0
            and self.direct_separable_candidate_count == 0
        )


def _witness(
    *,
    member_name: str,
    table_index: int,
    kind: str,
    table: _RawTable,
    grid: tuple[tuple[str, ...], ...],
    combined: tuple[str, ...],
    dram_rows: tuple[tuple[int, int], ...],
    nand_rows: tuple[tuple[int, int], ...],
) -> ProductRevenueTableWitness:
    labeled_rows = {row for row, _column in (*dram_rows, *nand_rows)}
    labeled_amounts = sum(bool(_amounts(grid[row])) for row in labeled_rows)
    return ProductRevenueTableWitness(
        member_name=member_name,
        table_index=table_index,
        witness_kind=kind,
        prefix_tail=tuple(table.prefix_text[-16:]),
        rows=grid,
        combined_bucket_cells=combined,
        dram_label_rows=dram_rows,
        nand_label_rows=nand_rows,
        direct_labeled_amount_row_count=labeled_amounts,
        unit_markers=_unit_context(_table_text(table, grid)),
    )


def build_product_revenue_source_closure(
    diagnostic: HistoricalProductRevenueFailureDiagnostic,
) -> ProductRevenueSourceClosurePeriod:
    archive_bytes = Path(diagnostic.archive_path).read_bytes()
    if hashlib.sha256(archive_bytes).hexdigest() != diagnostic.archive_sha256:
        raise ValueError("Pre-2023 source closure archive hash mismatch")
    try:
        archive = zipfile.ZipFile(io.BytesIO(archive_bytes))
    except zipfile.BadZipFile as exc:
        raise ValueError("Pre-2023 source closure source is not a ZIP") from exc

    aggregate: list[ProductRevenueTableWitness] = []
    direct: list[ProductRevenueTableWitness] = []
    member_count = 0
    table_count = 0
    with archive:
        for info in archive.infolist():
            if info.is_dir():
                continue
            safe_name = _safe_member_name(info.filename)
            if PurePosixPath(safe_name).suffix.casefold() not in _TEXT_SUFFIXES:
                continue
            member_count += 1
            decoded, _encoding = _decode_text(archive.read(info))
            parser = _TableExtractor()
            parser.feed(decoded)
            parser.close()
            table_count += len(parser.tables)
            for table_index, table in enumerate(parser.tables):
                grid = _grid(table)
                if not grid:
                    continue
                context = _table_text(table, grid)
                combined = _combined_bucket_cells(grid)
                dram_rows = _label_rows(grid, _DRAM_EXACT)
                nand_rows = _label_rows(grid, _NAND_EXACT)
                has_revenue = _revenue_context(context)
                has_product = _product_context(context)
                has_unit = bool(_unit_context(context))
                if combined and has_revenue and has_product and has_unit:
                    aggregate.append(
                        _witness(
                            member_name=safe_name,
                            table_index=table_index,
                            kind="aggregate_bucket",
                            table=table,
                            grid=grid,
                            combined=combined,
                            dram_rows=dram_rows,
                            nand_rows=nand_rows,
                        )
                    )
                if dram_rows and nand_rows and has_revenue and has_product and has_unit:
                    labeled_rows = {row for row, _column in (*dram_rows, *nand_rows)}
                    amount_rows = sum(bool(_amounts(grid[row])) for row in labeled_rows)
                    if amount_rows >= 2:
                        direct.append(
                            _witness(
                                member_name=safe_name,
                                table_index=table_index,
                                kind="direct_separable_candidate",
                                table=table,
                                grid=grid,
                                combined=combined,
                                dram_rows=dram_rows,
                                nand_rows=nand_rows,
                            )
                        )

    stable = {
        "period_id": diagnostic.period_id,
        "rcept_no": diagnostic.rcept_no,
        "archive_sha256": diagnostic.archive_sha256,
        "member_count": member_count,
        "table_count": table_count,
        "aggregate": [asdict(item) for item in aggregate],
        "direct": [asdict(item) for item in direct],
        "direct_product_revenue_certified": False,
        "synthetic_product_allocation_allowed": False,
    }
    return ProductRevenueSourceClosurePeriod(
        evidence_id=_sha(stable),
        period_id=diagnostic.period_id,
        rcept_no=diagnostic.rcept_no,
        archive_sha256=diagnostic.archive_sha256,
        member_count=member_count,
        table_count=table_count,
        aggregate_bucket_witnesses=tuple(aggregate),
        direct_separable_candidates=tuple(direct),
        aggregate_bucket_witness_count=len(aggregate),
        direct_separable_candidate_count=len(direct),
    )


def audit_pre2023_product_revenue_sources(
    *,
    output: str | Path = DEFAULT_PRODUCT_REVENUE_PROBE_OUTPUT,
) -> tuple[ProductRevenueSourceClosurePeriod, ...]:
    root = Path(output)
    results: list[ProductRevenueSourceClosurePeriod] = []
    for period_id in _EXPECTED_PERIODS:
        diagnostic = load_failure_diagnostic(
            period_id,
            _latest_diagnostic_path(root / period_id),
        )
        results.append(build_product_revenue_source_closure(diagnostic))
    return tuple(results)


__all__ = [
    "ProductRevenueSourceClosurePeriod",
    "ProductRevenueTableWitness",
    "audit_pre2023_product_revenue_sources",
    "build_product_revenue_source_closure",
]
