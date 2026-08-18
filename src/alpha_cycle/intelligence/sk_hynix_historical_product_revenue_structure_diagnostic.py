"""Diagnose near-miss historical SK hynix product-revenue tables without certifying them.

This module exists because a failed recovery with ``accepted=0`` does not reveal whether the
filing changed its row-label column, header semantics, unit marker, or product taxonomy.  The
diagnostic scans the already-preserved OpenDART ZIP bytes and reports structural facts only.
It never derives Other as a residual, never promotes a source row, never fits a model, and
never opens a future holdout.
"""

from __future__ import annotations

import hashlib
import io
import json
import zipfile
from dataclasses import asdict, dataclass
from pathlib import Path, PurePosixPath

from alpha_cycle.intelligence.sk_hynix_historical_product_failure_diagnostics import (
    load_failure_diagnostic,
)
from alpha_cycle.intelligence.sk_hynix_opendart_q2_product_revenue_table import (
    _grid,
    _TableExtractor,
)
from alpha_cycle.providers.opendart_documents import _decode_text, _safe_member_name

_TEXT_SUFFIXES = frozenset({".xml", ".html", ".htm", ".xhtml"})
_DRAM = frozenset({"dram", "d ram", "d램", "디램"})
_NAND = frozenset({"nand", "nand flash", "낸드", "낸드플래시"})
_OTHER = frozenset({"기타", "other", "others"})
_TOTAL = frozenset({"합계", "합 계", "total"})
_CURRENT_HEADERS = frozenset({"당분기", "당반기"})
_EXPECTED_PERIODS = frozenset(
    {
        "2017Q1",
        "2017Q2",
        "2017Q3",
        "2018Q1",
        "2018Q2",
        "2018Q3",
    }
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


def _latest_diagnostic(period_root: Path) -> Path:
    failed = period_root / "failed"
    if not failed.is_dir():
        raise ValueError(f"Historical product diagnostic failed root is missing: {period_root}")
    candidates = sorted(
        (item / "diagnostic.json" for item in failed.iterdir() if item.is_dir()),
        key=lambda path: path.parent.name,
        reverse=True,
    )
    found = next((path for path in candidates if path.is_file()), None)
    if found is None:
        raise ValueError(f"Historical product diagnostic bundle is missing: {period_root}")
    return found


def _label_columns(
    rows: tuple[tuple[str, ...], ...], labels: frozenset[str]
) -> tuple[int, ...]:
    columns: set[int] = set()
    for row in rows:
        for column, value in enumerate(row):
            if _norm(value) in labels:
                columns.add(column)
    return tuple(sorted(columns))


def _contains_product_token(rows: tuple[tuple[str, ...], ...]) -> bool:
    tokens = _DRAM | _NAND
    return any(_norm(cell) in tokens for row in rows for cell in row)


def _first_column_labels(rows: tuple[tuple[str, ...], ...]) -> tuple[str, ...]:
    labels: list[str] = []
    for row in rows:
        if not row:
            continue
        value = " ".join(row[0].split())
        if value and value not in labels:
            labels.append(value)
        if len(labels) >= 20:
            break
    return tuple(labels)


def _first_nonempty_labels(rows: tuple[tuple[str, ...], ...]) -> tuple[str, ...]:
    labels: list[str] = []
    for row in rows:
        value = next((" ".join(cell.split()) for cell in row if cell.strip()), "")
        if value and value not in labels:
            labels.append(value)
        if len(labels) >= 20:
            break
    return tuple(labels)


def _header_markers(
    rows: tuple[tuple[str, ...], ...]
) -> tuple[tuple[int, ...], tuple[int, ...]]:
    three_month: set[int] = set()
    current: set[int] = set()
    for row in rows[:6]:
        for column, value in enumerate(row):
            if column == 0:
                continue
            normalized = _norm(value)
            if normalized == "3개월":
                three_month.add(column)
            if normalized in _CURRENT_HEADERS:
                current.add(column)
    return tuple(sorted(three_month)), tuple(sorted(current))


@dataclass(frozen=True)
class HistoricalProductTableStructureReview:
    member_name: str
    table_index: int
    row_count: int
    maximum_column_count: int
    has_million_krw_unit_marker: bool
    has_revenue_context: bool
    dram_label_columns: tuple[int, ...]
    nand_label_columns: tuple[int, ...]
    other_label_columns: tuple[int, ...]
    total_label_columns: tuple[int, ...]
    shared_four_label_columns: tuple[int, ...]
    three_month_header_columns: tuple[int, ...]
    current_period_header_columns: tuple[int, ...]
    first_column_labels_sample: tuple[str, ...]
    first_nonempty_labels_sample: tuple[str, ...]
    current_recovery_shape_matches: bool
    structural_rejection_reasons: tuple[str, ...]
    source_certification_promoted: bool = False
    residual_other_derivation_allowed: bool = False
    training_row_promoted: bool = False
    fit_enabled: bool = False
    future_holdout_loaded: bool = False

    def __post_init__(self) -> None:
        if self.row_count <= 0 or self.maximum_column_count <= 0:
            raise ValueError("Historical product structure review dimensions are invalid")
        if self.current_recovery_shape_matches != (not self.structural_rejection_reasons):
            raise ValueError("Historical product structure review shape flag is inconsistent")
        forbidden = (
            self.source_certification_promoted,
            self.residual_other_derivation_allowed,
            self.training_row_promoted,
            self.fit_enabled,
            self.future_holdout_loaded,
        )
        if any(forbidden):
            raise ValueError("Historical product structure diagnostic exceeded read-only boundary")


@dataclass(frozen=True)
class HistoricalProductStructureDiagnostic:
    evidence_id: str
    period_id: str
    rcept_no: str
    source_archive_sha256: str
    structured_table_count: int
    malformed_table_count: int
    product_token_table_count: int
    reviews: tuple[HistoricalProductTableStructureReview, ...]
    current_recovery_shape_match_count: int
    source_certification_promoted: bool = False
    residual_other_derivation_allowed: bool = False
    training_row_promoted: bool = False
    fit_enabled: bool = False
    future_holdout_loaded: bool = False
    future_holdout_evaluated: bool = False

    def __post_init__(self) -> None:
        if self.period_id not in _EXPECTED_PERIODS:
            raise ValueError("Historical product structure diagnostic period is unsupported")
        if len(self.rcept_no) != 14 or not self.rcept_no.isdigit():
            raise ValueError("Historical product structure diagnostic receipt is invalid")
        if len(self.evidence_id) != 64 or len(self.source_archive_sha256) != 64:
            raise ValueError("Historical product structure diagnostic hashes must be SHA-256")
        if self.product_token_table_count != len(self.reviews):
            raise ValueError("Historical product structure diagnostic review count drifted")
        if self.current_recovery_shape_match_count != sum(
            item.current_recovery_shape_matches for item in self.reviews
        ):
            raise ValueError("Historical product structure diagnostic shape count drifted")
        forbidden = (
            self.source_certification_promoted,
            self.residual_other_derivation_allowed,
            self.training_row_promoted,
            self.fit_enabled,
            self.future_holdout_loaded,
            self.future_holdout_evaluated,
        )
        if any(forbidden):
            raise ValueError("Historical product structure diagnostic exceeded trust boundary")


def _review_table(
    member_name: str,
    table_index: int,
    rows: tuple[tuple[str, ...], ...],
    prefix_text: tuple[str, ...],
) -> HistoricalProductTableStructureReview:
    flattened = "\n".join((*prefix_text, *(cell for row in rows for cell in row)))
    normalized = _norm(flattened)
    dram_columns = _label_columns(rows, _DRAM)
    nand_columns = _label_columns(rows, _NAND)
    other_columns = _label_columns(rows, _OTHER)
    total_columns = _label_columns(rows, _TOTAL)
    shared = tuple(
        sorted(
            set(dram_columns)
            & set(nand_columns)
            & set(other_columns)
            & set(total_columns)
        )
    )
    three_month, current = _header_markers(rows)
    reasons: list[str] = []
    if "백만원" not in flattened:
        reasons.append("million_krw_unit_marker_missing")
    if "매출" not in normalized:
        reasons.append("revenue_context_missing")
    if 0 not in dram_columns:
        reasons.append("dram_not_in_first_column")
    if 0 not in nand_columns:
        reasons.append("nand_not_in_first_column")
    if 0 not in other_columns:
        reasons.append("other_not_in_first_column")
    if 0 not in total_columns:
        reasons.append("total_not_in_first_column")
    if not three_month and len(current) != 1:
        reasons.append("direct_quarter_header_not_uniquely_resolved")
    return HistoricalProductTableStructureReview(
        member_name=member_name,
        table_index=table_index,
        row_count=len(rows),
        maximum_column_count=max(len(row) for row in rows),
        has_million_krw_unit_marker="백만원" in flattened,
        has_revenue_context="매출" in normalized,
        dram_label_columns=dram_columns,
        nand_label_columns=nand_columns,
        other_label_columns=other_columns,
        total_label_columns=total_columns,
        shared_four_label_columns=shared,
        three_month_header_columns=three_month,
        current_period_header_columns=current,
        first_column_labels_sample=_first_column_labels(rows),
        first_nonempty_labels_sample=_first_nonempty_labels(rows),
        current_recovery_shape_matches=not reasons,
        structural_rejection_reasons=tuple(reasons),
    )


def diagnose_failed_historical_product_revenue_structure(
    period_id: str,
    period_output: str | Path,
) -> HistoricalProductStructureDiagnostic:
    """Inspect the latest preserved failed archive for one 2017-2018 period."""

    if period_id not in _EXPECTED_PERIODS:
        raise ValueError("Historical product structure diagnostic period is unsupported")
    diagnostic = load_failure_diagnostic(period_id, _latest_diagnostic(Path(period_output)))
    archive_bytes = Path(diagnostic.archive_path).read_bytes()
    archive_sha256 = hashlib.sha256(archive_bytes).hexdigest()
    if archive_sha256 != diagnostic.archive_sha256:
        raise ValueError("Historical product structure diagnostic archive hash mismatch")
    try:
        archive = zipfile.ZipFile(io.BytesIO(archive_bytes))
    except zipfile.BadZipFile as exc:
        raise ValueError("Historical product structure diagnostic source is not a ZIP") from exc

    reviews: list[HistoricalProductTableStructureReview] = []
    structured_count = 0
    malformed_count = 0
    with archive:
        for info in archive.infolist():
            if info.is_dir():
                continue
            member_name = _safe_member_name(info.filename)
            if PurePosixPath(member_name).suffix.casefold() not in _TEXT_SUFFIXES:
                continue
            decoded, _encoding = _decode_text(archive.read(info))
            parser = _TableExtractor()
            parser.feed(decoded)
            parser.close()
            for table_index, table in enumerate(parser.tables):
                try:
                    rows = _grid(table)
                except ValueError:
                    malformed_count += 1
                    continue
                structured_count += 1
                if not _contains_product_token(rows):
                    continue
                reviews.append(
                    _review_table(member_name, table_index, rows, table.prefix_text)
                )

    stable = {
        "period_id": period_id,
        "rcept_no": diagnostic.rcept_no,
        "source_archive_sha256": archive_sha256,
        "structured_table_count": structured_count,
        "malformed_table_count": malformed_count,
        "reviews": [asdict(item) for item in reviews],
    }
    return HistoricalProductStructureDiagnostic(
        evidence_id=_sha(stable),
        period_id=period_id,
        rcept_no=diagnostic.rcept_no,
        source_archive_sha256=archive_sha256,
        structured_table_count=structured_count,
        malformed_table_count=malformed_count,
        product_token_table_count=len(reviews),
        reviews=tuple(reviews),
        current_recovery_shape_match_count=sum(
            item.current_recovery_shape_matches for item in reviews
        ),
    )


__all__ = [
    "HistoricalProductStructureDiagnostic",
    "HistoricalProductTableStructureReview",
    "diagnose_failed_historical_product_revenue_structure",
]
