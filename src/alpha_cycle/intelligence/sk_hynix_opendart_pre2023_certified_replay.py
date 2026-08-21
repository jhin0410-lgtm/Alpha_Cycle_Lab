"""Replay exact 2021-2022 SK hynix product revenue from frozen source anchors.

The canonical pre-2023 registry was created from direct rows in preserved OpenDART
archives, but intentionally did not claim point-in-time eligibility.  This module does not
promote those old registry rows by themselves.  Instead, an immutable-receipt PIT replay
may use a registry row only as an identity anchor when the newly reacquired official ZIP
has the exact registered SHA-256 and the exact registered member/table/column reproduces
all four direct revenue values.

Normalized document text is retained as secondary evidence.  For this legacy layout it is
not used to choose a table: the text witness only proves that the four exact registered
amounts and the DRAM/NAND labels survive normalization.  The raw structured table remains
the authoritative value source.
"""

from __future__ import annotations

import hashlib
import io
import re
import zipfile
from pathlib import PurePosixPath

from alpha_cycle.intelligence.sk_hynix_opendart_historical_product_revenue_fallback import (
    HISTORICAL_PRODUCT_REVENUE_PARSER_ID,
)
from alpha_cycle.intelligence.sk_hynix_opendart_q2_product_revenue_certification import (
    PeriodicProductRevenueSpec,
    ProductRevenueMetrics,
    _parse_amount,
)
from alpha_cycle.intelligence.sk_hynix_opendart_q2_product_revenue_table import (
    _grid,
    _TableExtractor,
)
from alpha_cycle.intelligence.sk_hynix_pre2023_certified_product_revenue_registry import (
    CertifiedPre2023ProductRevenue,
    load_certified_pre2023_product_revenue_registry,
)
from alpha_cycle.intelligence.sk_hynix_pre2023_product_revenue_certification import (
    _DRAM_LABELS,
    _NAND_LABELS,
    _OTHER_LABELS,
    _TOTAL_LABELS,
    _amount_at,
    _direct_quarter_column,
    _row_for_label,
)
from alpha_cycle.intelligence.sk_hynix_pre2023_product_revenue_source_closure import (
    ProductRevenueTableWitness,
)
from alpha_cycle.providers.opendart_documents import _decode_text, _safe_member_name

_SUPPORTED_YEARS = frozenset({2021, 2022})
_QUARTER_BY_END_MONTH = {3: 1, 6: 2, 9: 3}
_TEXT_SUFFIXES = frozenset({".xml", ".html", ".htm", ".xhtml"})


def _normalized(value: str) -> str:
    return " ".join(value.replace("\u00a0", " ").split()).casefold()


def _period_id(spec: PeriodicProductRevenueSpec) -> str:
    if spec.parser_id != HISTORICAL_PRODUCT_REVENUE_PARSER_ID:
        raise ValueError("Pre-2023 certified replay requires the historical parser contract")
    year = spec.period_end.year
    quarter = _QUARTER_BY_END_MONTH.get(spec.period_end.month)
    if year not in _SUPPORTED_YEARS or quarter is None:
        raise ValueError("Pre-2023 certified replay is limited to 2021Q1-2022Q3")
    return f"{year}Q{quarter}"


def _anchor(spec: PeriodicProductRevenueSpec) -> CertifiedPre2023ProductRevenue:
    registry = load_certified_pre2023_product_revenue_registry()
    if registry.ticker != spec.ticker:
        raise ValueError("Pre-2023 certified replay ticker does not match registry")
    period_id = _period_id(spec)
    matches = [item for item in registry.periods if item.period_id == period_id]
    if len(matches) != 1:
        raise ValueError(f"Pre-2023 certified replay anchor must be unique: {period_id}")
    return matches[0]


def _metrics(anchor: CertifiedPre2023ProductRevenue) -> ProductRevenueMetrics:
    direct_sum = float(
        anchor.dram_revenue_million_krw
        + anchor.nand_revenue_million_krw
        + anchor.other_revenue_million_krw
    )
    total = float(anchor.total_revenue_million_krw)
    return ProductRevenueMetrics(
        unit="KRW_million",
        dram_total=float(anchor.dram_revenue_million_krw),
        nand_and_solutions=float(anchor.nand_revenue_million_krw),
        other_products_services=float(anchor.other_revenue_million_krw),
        reported_company_revenue=total,
        direct_sum=direct_sum,
        reconciliation_delta=direct_sum - total,
    )


def _contains_exact_integer(text: str, value: int) -> bool:
    without_grouping = text.replace(",", "")
    return re.search(rf"(?<!\d){value}(?!\d)", without_grouping) is not None


def parse_pre2023_certified_product_revenue_text(
    spec: PeriodicProductRevenueSpec,
    text: str,
) -> ProductRevenueMetrics:
    """Verify a non-authoritative normalized-text witness for an exact legacy anchor."""

    anchor = _anchor(spec)
    folded = _normalized(text)
    if "dram" not in folded or "nand" not in folded:
        raise ValueError("Pre-2023 certified text witness lacks direct DRAM/NAND labels")
    amounts = (
        anchor.dram_revenue_million_krw,
        anchor.nand_revenue_million_krw,
        anchor.other_revenue_million_krw,
        anchor.total_revenue_million_krw,
    )
    missing = [value for value in amounts if not _contains_exact_integer(text, value)]
    if missing:
        raise ValueError(
            "Pre-2023 certified text witness does not retain all exact anchored amounts: "
            f"missing={missing}"
        )
    return _metrics(anchor)


def _label_positions(
    rows: tuple[tuple[str, ...], ...],
    labels: frozenset[str],
) -> tuple[tuple[int, int], ...]:
    accepted = {_normalized(label) for label in labels}
    return tuple(
        (row_index, column)
        for row_index, row in enumerate(rows)
        for column, value in enumerate(row)
        if _normalized(value) in accepted
    )


def _witness_for_anchor(
    decoded: str,
    *,
    anchor: CertifiedPre2023ProductRevenue,
) -> ProductRevenueTableWitness:
    parser = _TableExtractor()
    parser.feed(decoded)
    parser.close()
    if anchor.table_index >= len(parser.tables):
        raise ValueError(
            "Pre-2023 certified replay table index is outside reacquired member: "
            f"index={anchor.table_index} tables={len(parser.tables)}"
        )
    table = parser.tables[anchor.table_index]
    rows = _grid(table)
    if not rows:
        raise ValueError("Pre-2023 certified replay anchored table is empty")
    context = "\n".join((*table.prefix_text, *(cell for row in rows for cell in row if cell)))
    unit_markers = tuple(marker for marker in ("백만원", "억원") if marker in context)
    dram_rows = _label_positions(rows, _DRAM_LABELS)
    nand_rows = _label_positions(rows, _NAND_LABELS)
    if not dram_rows or not nand_rows:
        raise ValueError("Pre-2023 certified replay anchored table lacks direct DRAM/NAND rows")
    labeled_rows = {row for row, _column in (*dram_rows, *nand_rows)}
    amount_row_count = sum(
        any(_parse_amount(token) is not None for token in rows[row]) for row in labeled_rows
    )
    return ProductRevenueTableWitness(
        member_name=anchor.member_name,
        table_index=anchor.table_index,
        witness_kind="direct_separable_candidate",
        layout_mode="structured_grid",
        prefix_tail=tuple(table.prefix_text[-16:]),
        rows=rows,
        combined_bucket_cells=(),
        dram_label_rows=dram_rows,
        nand_label_rows=nand_rows,
        direct_labeled_amount_row_count=amount_row_count,
        unit_markers=unit_markers,
    )


def parse_pre2023_certified_product_revenue_archive(
    spec: PeriodicProductRevenueSpec,
    archive_bytes: bytes,
) -> ProductRevenueMetrics:
    """Reproduce the exact registered member/table/column from reacquired raw ZIP bytes."""

    anchor = _anchor(spec)
    archive_hash = hashlib.sha256(archive_bytes).hexdigest()
    if archive_hash != anchor.source_archive_sha256:
        raise ValueError(
            "Pre-2023 certified replay archive SHA-256 does not match frozen source anchor"
        )
    try:
        archive = zipfile.ZipFile(io.BytesIO(archive_bytes))
    except zipfile.BadZipFile as exc:
        raise ValueError("Pre-2023 certified replay source is not a ZIP") from exc

    matching_members: list[bytes] = []
    with archive:
        for info in archive.infolist():
            if info.is_dir():
                continue
            safe_name = _safe_member_name(info.filename)
            if PurePosixPath(safe_name).suffix.casefold() not in _TEXT_SUFFIXES:
                continue
            if safe_name == anchor.member_name:
                matching_members.append(archive.read(info))
    if len(matching_members) != 1:
        raise ValueError(
            "Pre-2023 certified replay exact member must resolve uniquely: "
            f"member={anchor.member_name} count={len(matching_members)}"
        )
    decoded, _encoding = _decode_text(matching_members[0])
    witness = _witness_for_anchor(decoded, anchor=anchor)
    column, semantics = _direct_quarter_column(witness)
    if column != anchor.direct_quarter_column_index:
        raise ValueError("Pre-2023 certified replay direct-quarter column drifted")
    if semantics != anchor.direct_quarter_semantics:
        raise ValueError("Pre-2023 certified replay direct-quarter semantics drifted")

    observed = (
        _amount_at(_row_for_label(witness, _DRAM_LABELS, "DRAM"), column, "DRAM"),
        _amount_at(_row_for_label(witness, _NAND_LABELS, "NAND"), column, "NAND"),
        _amount_at(_row_for_label(witness, _OTHER_LABELS, "other"), column, "other"),
        _amount_at(_row_for_label(witness, _TOTAL_LABELS, "total"), column, "total"),
    )
    expected = (
        anchor.dram_revenue_million_krw,
        anchor.nand_revenue_million_krw,
        anchor.other_revenue_million_krw,
        anchor.total_revenue_million_krw,
    )
    if observed != expected:
        raise ValueError(
            "Pre-2023 certified replay exact table values drifted from frozen source anchor: "
            f"observed={observed} expected={expected}"
        )
    if observed[0] + observed[1] + observed[2] != observed[3]:
        raise ValueError("Pre-2023 certified replay direct product rows do not reconcile")
    if observed[3] * 1_000_000 != anchor.company_revenue_krw:
        raise ValueError("Pre-2023 certified replay total no longer ties to company revenue anchor")
    return _metrics(anchor)


__all__ = [
    "parse_pre2023_certified_product_revenue_archive",
    "parse_pre2023_certified_product_revenue_text",
]
