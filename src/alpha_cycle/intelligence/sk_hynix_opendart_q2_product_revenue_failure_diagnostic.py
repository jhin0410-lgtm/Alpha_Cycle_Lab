"""Inspect a preserved failed SK hynix OpenDART product-revenue capture offline.

The live capture intentionally fails closed when the source layout is not proven. This
module never calls OpenDART. It reads the already archived public filing ZIP and
normalized text, then emits a compact structural inventory that is safe to paste into a
bug report: relevant normalized-text contexts plus raw table grids around product and
revenue labels. API keys are neither required nor inspected.
"""

from __future__ import annotations

import hashlib
import io
import json
import zipfile
from dataclasses import asdict, dataclass
from pathlib import Path, PurePosixPath
from typing import cast

from alpha_cycle.intelligence.sk_hynix_opendart_q2_product_revenue_table import (
    _grid,
    _TableExtractor,
)
from alpha_cycle.providers.opendart_documents import _decode_text, _safe_member_name

_TEXT_SUFFIXES = frozenset({".xml", ".html", ".htm", ".xhtml"})
_KEY_TERMS = (
    "dram",
    "nand",
    "기타",
    "부문 합계",
    "합계",
    "수익(매출액)",
    "수익 (매출액)",
    "매출액",
    "연결",
    "별도",
    "당반기",
    "전반기",
    "당분기",
    "전분기",
    "3개월",
    "누적",
    "백만원",
)
_TABLE_RELEVANCE_TERMS = (
    "dram",
    "nand",
    "수익(매출액)",
    "수익 (매출액)",
    "기타",
    "부문 합계",
)


def _normalized(value: str) -> str:
    return " ".join(value.replace("\u00a0", " ").split()).casefold()


def _load_object(path: Path) -> dict[str, object]:
    try:
        payload: object = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ValueError(f"diagnostic file not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"diagnostic file is invalid JSON: {path}") from exc
    if not isinstance(payload, dict):
        raise ValueError("diagnostic file must contain a JSON object")
    return {str(key): value for key, value in cast(dict[object, object], payload).items()}


def latest_failure_diagnostic(root: str | Path) -> Path:
    failures = Path(root) / "failed"
    candidates = sorted(failures.glob("*/diagnostic.json"), reverse=True)
    if not candidates:
        raise ValueError(f"no failed product-revenue diagnostic found under: {failures}")
    return candidates[0]


def _verified_path(raw: object, *, base: Path, label: str) -> Path:
    value = str(raw or "").strip()
    if not value:
        raise ValueError(f"diagnostic lacks {label}")
    path = Path(value)
    if not path.is_absolute():
        path = base / path
    if not path.is_file():
        raise ValueError(f"diagnostic {label} does not exist: {path}")
    return path


def _text_contexts(text: str, *, radius: int = 10) -> list[dict[str, object]]:
    lines = [
        " ".join(line.replace("\u00a0", " ").split())
        for line in text.splitlines()
    ]
    relevant_indices = [
        index
        for index, line in enumerate(lines)
        if line
        and any(_normalized(term) in _normalized(line) for term in _KEY_TERMS)
    ]
    blocks: list[tuple[int, int]] = []
    for index in relevant_indices:
        start = max(0, index - radius)
        end = min(len(lines), index + radius + 1)
        if blocks and start <= blocks[-1][1] + 2:
            blocks[-1] = (blocks[-1][0], max(blocks[-1][1], end))
        else:
            blocks.append((start, end))
    contexts: list[dict[str, object]] = []
    for start, end in blocks[:24]:
        rows = [
            {"line": index + 1, "text": lines[index]}
            for index in range(start, end)
            if lines[index]
        ]
        contexts.append({"start_line": start + 1, "end_line": end, "rows": rows})
    return contexts


def _table_is_relevant(grid: tuple[tuple[str, ...], ...]) -> bool:
    flattened = "\n".join(value for row in grid for value in row if value)
    normalized = _normalized(flattened)
    hits = sum(_normalized(term) in normalized for term in _TABLE_RELEVANCE_TERMS)
    return hits >= 2 and ("dram" in normalized or "nand" in normalized)


def _trim_grid(
    grid: tuple[tuple[str, ...], ...],
    *,
    max_rows: int = 24,
    max_columns: int = 20,
) -> list[list[str]]:
    return [list(row[:max_columns]) for row in grid[:max_rows]]


def _table_inventory(archive_bytes: bytes) -> list[dict[str, object]]:
    try:
        archive = zipfile.ZipFile(io.BytesIO(archive_bytes))
    except zipfile.BadZipFile as exc:
        raise ValueError("diagnostic OpenDART source is not a ZIP") from exc

    inventory: list[dict[str, object]] = []
    with archive:
        for info in archive.infolist():
            if info.is_dir():
                continue
            safe_name = _safe_member_name(info.filename)
            if PurePosixPath(safe_name).suffix.casefold() not in _TEXT_SUFFIXES:
                continue
            decoded, encoding = _decode_text(archive.read(info))
            parser = _TableExtractor()
            parser.feed(decoded)
            parser.close()
            for table_index, table in enumerate(parser.tables):
                try:
                    grid = _grid(table)
                except ValueError as exc:
                    inventory.append(
                        {
                            "member": safe_name,
                            "encoding": encoding,
                            "table_index": table_index,
                            "grid_error": str(exc),
                            "prefix_tail": list(table.prefix_text[-80:]),
                        }
                    )
                    continue
                if not grid or not _table_is_relevant(grid):
                    continue
                width = max((len(row) for row in grid), default=0)
                flattened = "\n".join(
                    value for row in grid for value in row if value
                )
                normalized = _normalized(flattened)
                inventory.append(
                    {
                        "member": safe_name,
                        "encoding": encoding,
                        "table_index": table_index,
                        "rows": len(grid),
                        "columns": width,
                        "contains": {
                            term: _normalized(term) in normalized
                            for term in _KEY_TERMS
                        },
                        "prefix_tail": list(table.prefix_text[-80:]),
                        "grid": _trim_grid(grid),
                    }
                )
    return inventory


@dataclass(frozen=True)
class FailureDiagnosticReport:
    status: str
    rcept_no: str
    report_name: str
    original_error: str
    diagnostic_path: str
    archive_path: str
    archive_sha256: str
    normalized_text_path: str
    text_sha256: str
    normalized_text_contexts: list[dict[str, object]]
    relevant_tables: list[dict[str, object]]


def diagnose_failure(diagnostic_path: str | Path) -> FailureDiagnosticReport:
    path = Path(diagnostic_path)
    payload = _load_object(path)
    if payload.get("status") != "skhynix_opendart_q2_product_revenue_parse_failed":
        raise ValueError("unsupported product-revenue diagnostic status")

    archive_path = _verified_path(
        payload.get("archive_path"),
        base=path.parent,
        label="archive_path",
    )
    text_path = _verified_path(
        payload.get("normalized_text_path"),
        base=path.parent,
        label="normalized_text_path",
    )
    archive_bytes = archive_path.read_bytes()
    text = text_path.read_text(encoding="utf-8")
    archive_hash = hashlib.sha256(archive_bytes).hexdigest()
    text_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()
    if archive_hash != str(payload.get("archive_sha256", "")):
        raise ValueError("failed-capture archive SHA-256 mismatch")
    if text_hash != str(payload.get("text_sha256", "")):
        raise ValueError("failed-capture normalized-text SHA-256 mismatch")

    return FailureDiagnosticReport(
        status="skhynix_opendart_q2_product_revenue_failure_diagnosed",
        rcept_no=str(payload.get("rcept_no", "")),
        report_name=str(payload.get("report_name", "")),
        original_error=str(payload.get("error", "")),
        diagnostic_path=str(path),
        archive_path=str(archive_path),
        archive_sha256=archive_hash,
        normalized_text_path=str(text_path),
        text_sha256=text_hash,
        normalized_text_contexts=_text_contexts(text),
        relevant_tables=_table_inventory(archive_bytes),
    )


def write_failure_diagnostic_report(
    diagnostic_path: str | Path,
    *,
    output_path: str | Path | None = None,
) -> tuple[FailureDiagnosticReport, Path]:
    report = diagnose_failure(diagnostic_path)
    target = (
        Path(output_path)
        if output_path is not None
        else Path(diagnostic_path).with_name("table_shape_diagnostic.json")
    )
    target.write_text(
        json.dumps(asdict(report), ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return report, target


__all__ = [
    "FailureDiagnosticReport",
    "diagnose_failure",
    "latest_failure_diagnostic",
    "write_failure_diagnostic_report",
]
