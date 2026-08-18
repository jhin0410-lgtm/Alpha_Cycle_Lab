"""Recover historical SK hynix product revenue from preserved failed parser archives.

This is a narrow, fail-closed replay path for the exact-numeric 2017Q1-2020Q3 Q1-Q3
frontiers. It never guesses a product split. It scans only structured tables with explicit
DRAM/NAND/Other/Total rows and certifies a table only when the direct-quarter product sum
exactly equals the independently verified consolidated company revenue. Q4 remains outside
this recovery contract.
"""

from __future__ import annotations

import hashlib
import io
import json
import zipfile
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
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
        "2019Q1",
        "2019Q2",
        "2019Q3",
        "2020Q1",
        "2020Q2",
        "2020Q3",
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


def _amount(value: str, label: str) -> int:
    text = value.strip().replace(",", "")
    if not text or text == "-":
        raise ValueError(f"Historical product {label} is missing")
    try:
        parsed = Decimal(text)
    except InvalidOperation as exc:
        raise ValueError(f"Historical product {label} is not numeric") from exc
    if not parsed.is_finite() or parsed != parsed.to_integral_value() or parsed < 0:
        raise ValueError(f"Historical product {label} must be non-negative integral million KRW")
    return int(parsed)


def _label_row(
    rows: tuple[tuple[str, ...], ...], labels: frozenset[str], label: str
) -> tuple[str, ...]:
    matches = tuple(row for row in rows if row and _norm(row[0]) in labels)
    if len(matches) != 1:
        raise ValueError(f"Historical product {label} row count={len(matches)}")
    return matches[0]


def _direct_column(rows: tuple[tuple[str, ...], ...]) -> tuple[int, str]:
    three_month = sorted(
        {
            column
            for row in rows[:4]
            for column, value in enumerate(row)
            if column > 0 and _norm(value) == "3개월"
        }
    )
    if three_month:
        return three_month[0], "direct_quarter_3_month"
    current = sorted(
        {
            column
            for row in rows[:3]
            for column, value in enumerate(row)
            if column > 0 and _norm(value) in _CURRENT_HEADERS
        }
    )
    if len(current) != 1:
        raise ValueError(f"Historical direct-quarter column is ambiguous: {current}")
    return current[0], "direct_quarter_current_period"


def _at(row: tuple[str, ...], column: int, label: str) -> int:
    if column >= len(row):
        raise ValueError(f"Historical product {label} lacks selected quarter column")
    return _amount(row[column], label)


@dataclass(frozen=True)
class SecondWaveRecoveredProductRevenue:
    evidence_id: str
    period_id: str
    rcept_no: str
    source_archive_sha256: str
    member_name: str
    table_index: int
    direct_quarter_column_index: int
    direct_quarter_semantics: str
    dram_revenue_million_krw: int
    nand_revenue_million_krw: int
    other_revenue_million_krw: int
    total_revenue_million_krw: int
    company_revenue_krw: int
    direct_product_revenue_certified: bool = True
    current_retrieval_historical_source_fact: bool = True
    historical_vintage_certified: bool = False
    point_in_time_backtest_eligible: bool = False
    training_row_promoted: bool = False
    fit_enabled: bool = False

    def __post_init__(self) -> None:
        if self.period_id not in _EXPECTED_PERIODS:
            raise ValueError("Historical recovered product period is unsupported")
        if len(self.rcept_no) != 14 or not self.rcept_no.isdigit():
            raise ValueError("Historical recovered product receipt is invalid")
        if len(self.evidence_id) != 64 or len(self.source_archive_sha256) != 64:
            raise ValueError("Historical recovered product hashes must be SHA-256")
        if (
            self.dram_revenue_million_krw
            + self.nand_revenue_million_krw
            + self.other_revenue_million_krw
            != self.total_revenue_million_krw
        ):
            raise ValueError("Historical recovered product sum identity failed")
        if self.total_revenue_million_krw * 1_000_000 != self.company_revenue_krw:
            raise ValueError("Historical recovered product does not tie to company revenue")
        if (
            not self.direct_product_revenue_certified
            or not self.current_retrieval_historical_source_fact
            or self.historical_vintage_certified
            or self.point_in_time_backtest_eligible
            or self.training_row_promoted
            or self.fit_enabled
        ):
            raise ValueError("Historical recovered product exceeded source boundary")


@dataclass(frozen=True)
class SecondWaveProductCandidateReview:
    member_name: str
    table_index: int
    reconciles_to_company_revenue: bool
    rejection_reason: str | None


@dataclass(frozen=True)
class SecondWaveProductRecoveryResult:
    period_id: str
    certified: bool
    observation: SecondWaveRecoveredProductRevenue | None
    candidate_reviews: tuple[SecondWaveProductCandidateReview, ...]
    structured_table_count: int
    malformed_table_count: int
    error: str | None

    def __post_init__(self) -> None:
        if self.certified != (self.observation is not None):
            raise ValueError("Historical product recovery success state is inconsistent")
        if self.certified == (self.error is not None):
            raise ValueError("Historical product recovery error state is inconsistent")


def certify_rows(
    rows: tuple[tuple[str, ...], ...], company_revenue_krw: int
) -> tuple[int, str, int, int, int, int]:
    column, semantics = _direct_column(rows)
    dram = _at(_label_row(rows, _DRAM, "DRAM"), column, "DRAM")
    nand = _at(_label_row(rows, _NAND, "NAND"), column, "NAND")
    other = _at(_label_row(rows, _OTHER, "other"), column, "other")
    total = _at(_label_row(rows, _TOTAL, "total"), column, "total")
    if dram + nand + other != total:
        raise ValueError("DRAM + NAND + other does not equal table total")
    if total * 1_000_000 != company_revenue_krw:
        raise ValueError("table total does not equal verified consolidated revenue")
    return column, semantics, dram, nand, other, total


def _latest_diagnostic(period_root: Path) -> Path:
    failed = period_root / "failed"
    if not failed.is_dir():
        raise ValueError(f"Historical failed product root is missing: {period_root}")
    paths = sorted(
        (item / "diagnostic.json" for item in failed.iterdir() if item.is_dir()),
        key=lambda path: path.parent.name,
        reverse=True,
    )
    found = next((path for path in paths if path.is_file()), None)
    if found is None:
        raise ValueError(f"Historical failed product diagnostic is missing: {period_root}")
    return found


def recover_failed_second_wave_product_revenue(
    period_id: str,
    period_output: str | Path,
    *,
    company_revenue_krw: int,
    company_rcept_no: str,
) -> SecondWaveProductRecoveryResult:
    if period_id not in _EXPECTED_PERIODS:
        raise ValueError("Historical recovery period is unsupported")
    diagnostic = load_failure_diagnostic(period_id, _latest_diagnostic(Path(period_output)))
    if diagnostic.rcept_no != company_rcept_no:
        return SecondWaveProductRecoveryResult(
            period_id=period_id,
            certified=False,
            observation=None,
            candidate_reviews=(),
            structured_table_count=0,
            malformed_table_count=0,
            error="product and company filing receipts differ",
        )
    archive_bytes = Path(diagnostic.archive_path).read_bytes()
    if hashlib.sha256(archive_bytes).hexdigest() != diagnostic.archive_sha256:
        raise ValueError("Historical recovery archive hash mismatch")
    try:
        archive = zipfile.ZipFile(io.BytesIO(archive_bytes))
    except zipfile.BadZipFile as exc:
        raise ValueError("Historical recovery source is not a ZIP") from exc

    reviews: list[SecondWaveProductCandidateReview] = []
    accepted: list[SecondWaveRecoveredProductRevenue] = []
    structured_count = 0
    malformed_count = 0
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
                    rows = _grid(table)
                except ValueError:
                    malformed_count += 1
                    continue
                structured_count += 1
                text = "\n".join((*table.prefix_text, *(cell for row in rows for cell in row)))
                normalized = _norm(text)
                if "백만원" not in text or "매출" not in normalized:
                    continue
                first_cells = {_norm(row[0]) for row in rows if row}
                if not (_DRAM & first_cells and _NAND & first_cells):
                    continue
                if not (_OTHER & first_cells and _TOTAL & first_cells):
                    continue
                try:
                    column, semantics, dram, nand, other, total = certify_rows(
                        rows, company_revenue_krw
                    )
                except ValueError as exc:
                    reviews.append(
                        SecondWaveProductCandidateReview(
                            member_name=safe_name,
                            table_index=table_index,
                            reconciles_to_company_revenue=False,
                            rejection_reason=str(exc),
                        )
                    )
                    continue
                stable = {
                    "period_id": period_id,
                    "rcept_no": diagnostic.rcept_no,
                    "source_archive_sha256": diagnostic.archive_sha256,
                    "member_name": safe_name,
                    "table_index": table_index,
                    "direct_quarter_column_index": column,
                    "direct_quarter_semantics": semantics,
                    "dram": dram,
                    "nand": nand,
                    "other": other,
                    "total": total,
                    "company_revenue_krw": company_revenue_krw,
                }
                observation = SecondWaveRecoveredProductRevenue(
                    evidence_id=_sha(stable),
                    period_id=period_id,
                    rcept_no=diagnostic.rcept_no,
                    source_archive_sha256=diagnostic.archive_sha256,
                    member_name=safe_name,
                    table_index=table_index,
                    direct_quarter_column_index=column,
                    direct_quarter_semantics=semantics,
                    dram_revenue_million_krw=dram,
                    nand_revenue_million_krw=nand,
                    other_revenue_million_krw=other,
                    total_revenue_million_krw=total,
                    company_revenue_krw=company_revenue_krw,
                )
                accepted.append(observation)
                reviews.append(
                    SecondWaveProductCandidateReview(
                        member_name=safe_name,
                        table_index=table_index,
                        reconciles_to_company_revenue=True,
                        rejection_reason=None,
                    )
                )
    unique = {
        (
            item.member_name,
            item.table_index,
            item.dram_revenue_million_krw,
            item.nand_revenue_million_krw,
            item.other_revenue_million_krw,
            item.total_revenue_million_krw,
        ): item
        for item in accepted
    }
    if len(unique) != 1:
        return SecondWaveProductRecoveryResult(
            period_id=period_id,
            certified=False,
            observation=None,
            candidate_reviews=tuple(reviews),
            structured_table_count=structured_count,
            malformed_table_count=malformed_count,
            error=f"exactly one consolidated product table required; accepted={len(unique)}",
        )
    return SecondWaveProductRecoveryResult(
        period_id=period_id,
        certified=True,
        observation=next(iter(unique.values())),
        candidate_reviews=tuple(reviews),
        structured_table_count=structured_count,
        malformed_table_count=malformed_count,
        error=None,
    )


__all__ = [
    "SecondWaveProductCandidateReview",
    "SecondWaveProductRecoveryResult",
    "SecondWaveRecoveredProductRevenue",
    "certify_rows",
    "recover_failed_second_wave_product_revenue",
]
