"""Profile preserved pre-2023 SK hynix OpenDART failures before adding a parser family.

This diagnostic layer is intentionally parser-neutral. It verifies the newest preserved
failure bundle for each frontier period, then fingerprints normalized-text and ZIP layout
signals that are useful when designing a new historical parser. It does not extract or
certify product revenue and cannot promote a frontier row.
"""

from __future__ import annotations

import hashlib
import json
import re
import zipfile
from dataclasses import asdict, dataclass
from io import BytesIO
from pathlib import Path

from alpha_cycle.intelligence.sk_hynix_historical_product_failure_diagnostics import (
    HistoricalProductRevenueFailureDiagnostic,
    load_failure_diagnostic,
)
from alpha_cycle.intelligence.sk_hynix_product_profitability_historical_expansion_probe import (
    DEFAULT_PRODUCT_REVENUE_PROBE_OUTPUT,
)

_EXPECTED_PERIODS = (
    "2021Q1",
    "2021Q2",
    "2021Q3",
    "2022Q1",
    "2022Q2",
    "2022Q3",
)
_PRODUCT_TRIGGER_TERMS = (
    "DRAM",
    "NAND",
    "NAND Flash",
    "D램",
    "디램",
    "낸드",
    "낸드플래시",
    "메모리",
    "Memory",
)
_SIGNAL_TERMS = (
    *_PRODUCT_TRIGGER_TERMS,
    "3개월",
    "누적",
    "백만원",
    "억원",
    "매출액",
    "제품",
    "상품",
)
_AMOUNT_TOKEN = re.compile(r"^-?\(?[0-9][0-9,]*(?:\.[0-9]+)?\)?$")


def _normalize_line(value: str) -> str:
    return " ".join(value.replace("\u00a0", " ").split())


def _canonical_hash(payload: object) -> str:
    return hashlib.sha256(
        json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()


def _latest_diagnostic_path(period_root: Path) -> Path:
    failed_root = period_root / "failed"
    if not failed_root.is_dir():
        raise ValueError(f"Historical expansion failure directory is missing: {period_root}")
    candidates = sorted(
        (path / "diagnostic.json" for path in failed_root.iterdir() if path.is_dir()),
        key=lambda path: path.parent.name,
        reverse=True,
    )
    latest = next((path for path in candidates if path.is_file()), None)
    if latest is None:
        raise ValueError(f"Historical expansion failure diagnostic is missing: {period_root}")
    return latest


def _is_amount_token(value: str) -> bool:
    return _AMOUNT_TOKEN.fullmatch(value.replace(" ", "")) is not None


@dataclass(frozen=True)
class HistoricalExpansionLayoutContext:
    start_line: int
    end_line: int
    trigger_terms: tuple[str, ...]
    lines: tuple[str, ...]
    amount_token_count: int
    has_three_month_marker: bool
    has_cumulative_marker: bool
    unit_markers: tuple[str, ...]

    def __post_init__(self) -> None:
        if self.start_line < 1 or self.end_line < self.start_line or not self.lines:
            raise ValueError("Historical expansion layout context bounds are invalid")
        if self.amount_token_count < 0:
            raise ValueError("Historical expansion amount-token count cannot be negative")
        if not self.trigger_terms:
            raise ValueError("Historical expansion layout context requires a trigger")


@dataclass(frozen=True)
class HistoricalExpansionLayoutProfile:
    evidence_id: str
    period_id: str
    diagnostic_path: str
    rcept_no: str
    report_name: str
    normalized_text_path: str
    archive_path: str
    line_count: int
    nonempty_line_count: int
    signal_counts: tuple[tuple[str, int], ...]
    contexts: tuple[HistoricalExpansionLayoutContext, ...]
    context_count: int
    archive_member_count: int
    archive_member_suffix_counts: tuple[tuple[str, int], ...]
    archive_member_sample: tuple[str, ...]
    parser_family_inferred: bool = False
    product_revenue_extracted: bool = False
    source_certification_promoted: bool = False
    training_row_promoted: bool = False
    fit_enabled: bool = False

    def __post_init__(self) -> None:
        if self.period_id not in _EXPECTED_PERIODS:
            raise ValueError("Historical expansion layout profile period is unsupported")
        if len(self.evidence_id) != 64:
            raise ValueError("Historical expansion layout profile evidence id must be SHA-256")
        if self.line_count < self.nonempty_line_count or self.nonempty_line_count <= 0:
            raise ValueError("Historical expansion layout profile line counts are invalid")
        if self.context_count != len(self.contexts):
            raise ValueError("Historical expansion layout profile context count is inconsistent")
        if self.archive_member_count < len(self.archive_member_sample):
            raise ValueError("Historical expansion archive-member counts are inconsistent")
        if (
            self.parser_family_inferred
            or self.product_revenue_extracted
            or self.source_certification_promoted
            or self.training_row_promoted
            or self.fit_enabled
        ):
            raise ValueError("Historical expansion layout profile exceeds diagnostic boundary")


def _profile_contexts(lines: tuple[str, ...]) -> tuple[HistoricalExpansionLayoutContext, ...]:
    trigger_indices = [
        index
        for index, line in enumerate(lines)
        if any(term.casefold() in line.casefold() for term in _PRODUCT_TRIGGER_TERMS)
    ]
    if not trigger_indices:
        return ()

    windows: list[tuple[int, int]] = []
    for index in trigger_indices:
        start = max(0, index - 12)
        end = min(len(lines), index + 18)
        if windows and start <= windows[-1][1] + 1:
            prior_start, prior_end = windows[-1]
            windows[-1] = (prior_start, max(prior_end, end))
        else:
            windows.append((start, end))

    contexts: list[HistoricalExpansionLayoutContext] = []
    trigger_report_terms = (
        *_PRODUCT_TRIGGER_TERMS,
        "3개월",
        "누적",
        "백만원",
        "억원",
        "매출액",
    )
    for start, end in windows[:12]:
        block = lines[start:end]
        folded = "\n".join(block).casefold()
        triggers = tuple(term for term in trigger_report_terms if term.casefold() in folded)
        units = tuple(unit for unit in ("백만원", "억원") if unit in folded)
        contexts.append(
            HistoricalExpansionLayoutContext(
                start_line=start + 1,
                end_line=end,
                trigger_terms=triggers or ("memory-product",),
                lines=block,
                amount_token_count=sum(_is_amount_token(item) for item in block),
                has_three_month_marker="3개월" in folded,
                has_cumulative_marker="누적" in folded,
                unit_markers=units,
            )
        )
    return tuple(contexts)


def _archive_inventory(
    archive_bytes: bytes,
) -> tuple[int, tuple[tuple[str, int], ...], tuple[str, ...]]:
    with zipfile.ZipFile(BytesIO(archive_bytes)) as archive:
        names = tuple(item.filename for item in archive.infolist() if not item.is_dir())
    suffix_counts: dict[str, int] = {}
    for name in names:
        suffix = Path(name).suffix.casefold() or "<none>"
        suffix_counts[suffix] = suffix_counts.get(suffix, 0) + 1
    sample = tuple(names[:25])
    return len(names), tuple(sorted(suffix_counts.items())), sample


def build_historical_expansion_layout_profile(
    diagnostic: HistoricalProductRevenueFailureDiagnostic,
) -> HistoricalExpansionLayoutProfile:
    try:
        text = Path(diagnostic.normalized_text_path).read_text(encoding="utf-8")
        archive_bytes = Path(diagnostic.archive_path).read_bytes()
    except FileNotFoundError as exc:
        raise ValueError(
            f"Historical expansion preserved artifact is missing: {diagnostic.period_id}"
        ) from exc

    raw_lines = text.splitlines()
    lines = tuple(_normalize_line(item) for item in raw_lines if item.strip())
    folded_lines = tuple(item.casefold() for item in lines)
    signal_counts = tuple(
        (term, sum(term.casefold() in line for line in folded_lines)) for term in _SIGNAL_TERMS
    )
    contexts = _profile_contexts(lines)
    member_count, suffix_counts, member_sample = _archive_inventory(archive_bytes)
    stable = {
        "period_id": diagnostic.period_id,
        "rcept_no": diagnostic.rcept_no,
        "archive_sha256": diagnostic.archive_sha256,
        "text_sha256": diagnostic.text_sha256,
        "line_count": len(raw_lines),
        "nonempty_line_count": len(lines),
        "signal_counts": signal_counts,
        "contexts": [asdict(item) for item in contexts],
        "archive_member_count": member_count,
        "archive_member_suffix_counts": suffix_counts,
        "archive_member_sample": member_sample,
        "parser_family_inferred": False,
        "product_revenue_extracted": False,
    }
    return HistoricalExpansionLayoutProfile(
        evidence_id=_canonical_hash(stable),
        period_id=diagnostic.period_id,
        diagnostic_path=diagnostic.diagnostic_path,
        rcept_no=diagnostic.rcept_no,
        report_name=diagnostic.report_name,
        normalized_text_path=diagnostic.normalized_text_path,
        archive_path=diagnostic.archive_path,
        line_count=len(raw_lines),
        nonempty_line_count=len(lines),
        signal_counts=signal_counts,
        contexts=contexts,
        context_count=len(contexts),
        archive_member_count=member_count,
        archive_member_suffix_counts=suffix_counts,
        archive_member_sample=member_sample,
    )


def profile_historical_expansion_failures(
    *,
    output: str | Path = DEFAULT_PRODUCT_REVENUE_PROBE_OUTPUT,
) -> tuple[HistoricalExpansionLayoutProfile, ...]:
    root = Path(output)
    profiles: list[HistoricalExpansionLayoutProfile] = []
    for period_id in _EXPECTED_PERIODS:
        path = _latest_diagnostic_path(root / period_id)
        diagnostic = load_failure_diagnostic(period_id, path)
        profiles.append(build_historical_expansion_layout_profile(diagnostic))
    return tuple(profiles)


__all__ = [
    "HistoricalExpansionLayoutContext",
    "HistoricalExpansionLayoutProfile",
    "build_historical_expansion_layout_profile",
    "profile_historical_expansion_failures",
]
