"""Build parser-contract readiness evidence from the captured official SK hynix 2Q26 PDF.

This module deliberately stops before numeric semantics.  It reverifies the issuer PDF,
extracts the page context around ``Revenue by Product``, and inventories raw percentage and
comma-formatted numeric tokens.  Those tokens are review material, not source facts.

The output exists so the next source-specific parser can be written against exact official
bytes instead of against a mirror, memory, or a guessed table layout.
"""

from __future__ import annotations

import hashlib
import json
import re
import shutil
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path

from alpha_cycle.intelligence import sk_hynix_official_ir_q2_attachment_capture as attachment
from alpha_cycle.intelligence.sk_hynix_official_ir_q2_attachment_capture import (
    DEFAULT_Q2_ATTACHMENT_POINTER,
    OfficialIrQ2AttachmentEvidence,
    load_q2_attachment_evidence,
)

DEFAULT_Q2_PARSER_READINESS_OUTPUT = Path(
    "data/private/research/skhynix-official-ir-q2-parser-readiness"
)
DEFAULT_Q2_PARSER_READINESS_POINTER = (
    DEFAULT_Q2_PARSER_READINESS_OUTPUT / "latest_skhynix_ir_q2_parser_readiness.json"
)

_REVENUE_BY_PRODUCT = re.compile(r"Revenue\s+by\s+Product", flags=re.IGNORECASE)
_PERCENTAGE = re.compile(r"(?<![\w.])\d{1,3}(?:\.\d+)?\s*%")
_COMMA_NUMBER = re.compile(r"(?<![\w.])\d{1,3}(?:,\d{3})+(?:\.\d+)?(?![\w.])")
_DRAM = re.compile(r"\bDRAM\b", flags=re.IGNORECASE)
_NAND = re.compile(r"\bNAND(?:\s+Flash)?\b", flags=re.IGNORECASE)
_REQUIRED_FALSE_FLAGS = (
    "numeric_semantics_certified",
    "registry_write_eligible",
    "product_baseline_eligible",
    "allocation_resolver_registered",
    "numeric_forecast_enabled",
    "decision_score_enabled",
)


@dataclass(frozen=True)
class ParserContext:
    page_number: int
    context: str
    relevant_lines: tuple[str, ...]
    percentage_tokens: tuple[str, ...]
    comma_number_tokens: tuple[str, ...]
    dram_anchor: bool
    nand_anchor: bool


@dataclass(frozen=True)
class OfficialIrQ2ParserReadiness:
    evidence_id: str
    attachment_evidence_id: str
    observed_date: date
    source_url: str
    source_published_date: str
    expected_page_count: int
    parser_id_candidate: str
    readiness_status: str
    contexts: tuple[ParserContext, ...]
    percentage_tokens: tuple[str, ...]
    comma_number_tokens: tuple[str, ...]
    numeric_semantics_certified: bool = False
    registry_write_eligible: bool = False
    product_baseline_eligible: bool = False
    allocation_resolver_registered: bool = False
    numeric_forecast_enabled: bool = False
    decision_score_enabled: bool = False

    def __post_init__(self) -> None:
        if not _valid_sha(self.evidence_id) or not _valid_sha(self.attachment_evidence_id):
            raise ValueError("SK hynix Q2 parser-readiness IDs must be SHA-256")
        if not self.source_url.startswith("https://"):
            raise ValueError("SK hynix Q2 parser-readiness source URL must be HTTPS")
        if self.expected_page_count <= 0:
            raise ValueError("SK hynix Q2 parser readiness requires a positive page count")
        if self.readiness_status not in {
            "identity_not_verified",
            "product_mix_context_missing",
            "context_ready_for_parser_contract_review",
        }:
            raise ValueError("SK hynix Q2 parser-readiness status is invalid")
        if (
            self.numeric_semantics_certified
            or self.registry_write_eligible
            or self.product_baseline_eligible
            or self.allocation_resolver_registered
            or self.numeric_forecast_enabled
            or self.decision_score_enabled
        ):
            raise ValueError("SK hynix Q2 parser readiness cannot widen model trust")


def _valid_sha(value: str) -> bool:
    return len(value) == 64 and all(char in "0123456789abcdef" for char in value)


def _sha_payload(payload: object) -> str:
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    return hashlib.sha256(encoded).hexdigest()


def _compact(value: str) -> str:
    return " ".join(value.split())


def _dedupe(values: list[str]) -> tuple[str, ...]:
    seen: set[str] = set()
    output: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        output.append(value)
    return tuple(output)


def _published_date(display_date: str) -> str:
    cleaned = display_date.strip().replace("/", ".").replace("-", ".")
    parts = [part for part in cleaned.split(".") if part]
    if len(parts) == 3 and all(part.isdigit() for part in parts):
        year, month, day = (int(part) for part in parts)
        try:
            return date(year, month, day).isoformat()
        except ValueError:
            pass
    raise ValueError("SK hynix Q2 parser readiness cannot normalize board display date")


def _bounded_context(text: str, match: re.Match[str], *, width: int = 2200) -> str:
    half = width // 2
    return text[max(0, match.start() - half) : min(len(text), match.end() + half)]


def _relevant_lines(context: str) -> tuple[str, ...]:
    selected: list[str] = []
    for raw_line in context.splitlines():
        line = _compact(raw_line)
        if not line:
            continue
        if (
            _REVENUE_BY_PRODUCT.search(line)
            or _DRAM.search(line)
            or _NAND.search(line)
            or _PERCENTAGE.search(line)
            or _COMMA_NUMBER.search(line)
        ):
            selected.append(line[:500])
        if len(selected) >= 40:
            break
    return tuple(selected)


def _context_payload(item: ParserContext) -> dict[str, object]:
    return {
        "page_number": item.page_number,
        "context": item.context,
        "relevant_lines": list(item.relevant_lines),
        "percentage_tokens": list(item.percentage_tokens),
        "comma_number_tokens": list(item.comma_number_tokens),
        "dram_anchor": item.dram_anchor,
        "nand_anchor": item.nand_anchor,
    }


def _readiness_payload(item: OfficialIrQ2ParserReadiness) -> dict[str, object]:
    return {
        "schema_version": 1,
        "status": "skhynix_official_ir_q2_parser_readiness_captured",
        "evidence_id": item.evidence_id,
        "attachment_evidence_id": item.attachment_evidence_id,
        "observed_date": item.observed_date.isoformat(),
        "source_url": item.source_url,
        "source_published_date": item.source_published_date,
        "expected_page_count": item.expected_page_count,
        "parser_id_candidate": item.parser_id_candidate,
        "readiness_status": item.readiness_status,
        "contexts": [_context_payload(value) for value in item.contexts],
        "percentage_tokens": list(item.percentage_tokens),
        "comma_number_tokens": list(item.comma_number_tokens),
        "proposed_period_start": "2026-04-01",
        "proposed_period_end": "2026-06-30",
        "numeric_semantics_certified": False,
        "registry_write_eligible": False,
        "product_baseline_eligible": False,
        "allocation_resolver_registered": False,
        "numeric_forecast_enabled": False,
        "decision_score_enabled": False,
    }


def build_q2_parser_readiness(
    evidence: OfficialIrQ2AttachmentEvidence,
    *,
    pdf_bytes: bytes,
) -> OfficialIrQ2ParserReadiness:
    fingerprint = attachment.fingerprint_q2_pdf(pdf_bytes)
    if fingerprint != evidence.fingerprint:
        raise ValueError("SK hynix Q2 parser readiness fingerprint differs from attachment evidence")
    page_texts = attachment._extract_page_texts(pdf_bytes)

    contexts: list[ParserContext] = []
    all_percentages: list[str] = []
    all_numbers: list[str] = []
    for page_number, page_text in enumerate(page_texts, start=1):
        for match in _REVENUE_BY_PRODUCT.finditer(page_text):
            raw_context = _bounded_context(page_text, match)
            percentages = _dedupe(
                [_compact(value.group(0)) for value in _PERCENTAGE.finditer(raw_context)]
            )
            numbers = _dedupe(
                [_compact(value.group(0)) for value in _COMMA_NUMBER.finditer(raw_context)]
            )
            contexts.append(
                ParserContext(
                    page_number=page_number,
                    context=_compact(raw_context)[:2200],
                    relevant_lines=_relevant_lines(raw_context),
                    percentage_tokens=percentages,
                    comma_number_tokens=numbers,
                    dram_anchor=_DRAM.search(raw_context) is not None,
                    nand_anchor=_NAND.search(raw_context) is not None,
                )
            )
            all_percentages.extend(percentages)
            all_numbers.extend(numbers)
            if len(contexts) >= 4:
                break
        if len(contexts) >= 4:
            break

    if not evidence.fingerprint.document_identity_verified:
        readiness_status = "identity_not_verified"
    elif not contexts or not any(item.dram_anchor and item.nand_anchor for item in contexts):
        readiness_status = "product_mix_context_missing"
    else:
        readiness_status = "context_ready_for_parser_contract_review"

    source_published_date = _published_date(evidence.candidate_display_date)
    payload = {
        "attachment_evidence_id": evidence.evidence_id,
        "observed_date": evidence.observed_date.isoformat(),
        "source_url": evidence.pdf_url,
        "source_published_date": source_published_date,
        "expected_page_count": evidence.fingerprint.page_count,
        "parser_id_candidate": "sk_hynix_earnings_release_2026q2_v1_candidate",
        "readiness_status": readiness_status,
        "contexts": [_context_payload(value) for value in contexts],
        "percentage_tokens": list(_dedupe(all_percentages)),
        "comma_number_tokens": list(_dedupe(all_numbers)),
        "proposed_period_start": "2026-04-01",
        "proposed_period_end": "2026-06-30",
        "numeric_semantics_certified": False,
        "registry_write_eligible": False,
        "product_baseline_eligible": False,
        "allocation_resolver_registered": False,
        "numeric_forecast_enabled": False,
        "decision_score_enabled": False,
    }
    return OfficialIrQ2ParserReadiness(
        evidence_id=_sha_payload(payload),
        attachment_evidence_id=evidence.evidence_id,
        observed_date=evidence.observed_date,
        source_url=evidence.pdf_url,
        source_published_date=source_published_date,
        expected_page_count=evidence.fingerprint.page_count,
        parser_id_candidate="sk_hynix_earnings_release_2026q2_v1_candidate",
        readiness_status=readiness_status,
        contexts=tuple(contexts),
        percentage_tokens=_dedupe(all_percentages),
        comma_number_tokens=_dedupe(all_numbers),
    )


def capture_q2_parser_readiness(
    attachment_pointer_path: str | Path = DEFAULT_Q2_ATTACHMENT_POINTER,
    *,
    evaluation_date: date,
    output: str | Path = DEFAULT_Q2_PARSER_READINESS_OUTPUT,
    captured_at: datetime | None = None,
) -> dict[str, object]:
    attachment_pointer = Path(attachment_pointer_path)
    evidence = load_q2_attachment_evidence(
        attachment_pointer,
        evaluation_date=evaluation_date,
    )
    try:
        pointer_obj: object = json.loads(attachment_pointer.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError) as exc:
        raise ValueError("SK hynix Q2 attachment pointer is unreadable for parser readiness") from exc
    if not isinstance(pointer_obj, dict):
        raise ValueError("SK hynix Q2 attachment pointer must be an object")
    pointer = {str(key): value for key, value in pointer_obj.items()}
    pdf_path = Path(str(pointer.get("pdf_path", "")))
    pdf_bytes = pdf_path.read_bytes()
    if hashlib.sha256(pdf_bytes).hexdigest() != evidence.pdf_sha256:
        raise ValueError("SK hynix Q2 parser readiness PDF hash differs from attachment evidence")
    readiness = build_q2_parser_readiness(evidence, pdf_bytes=pdf_bytes)

    root = Path(output)
    root.mkdir(parents=True, exist_ok=True)
    captured = captured_at or datetime.now(UTC)
    if captured.tzinfo is None or captured.utcoffset() is None:
        raise ValueError("captured_at must be timezone-aware")
    directory = root / (
        captured.astimezone(UTC).strftime("%Y%m%dT%H%M%S%fZ")
        + "__"
        + readiness.evidence_id[:12]
    )
    temporary = root / f".{directory.name}.tmp"
    if directory.exists() or temporary.exists():
        raise ValueError("SK hynix Q2 parser-readiness artifact path already exists")
    temporary.mkdir()
    try:
        (temporary / "parser_readiness.json").write_text(
            json.dumps(_readiness_payload(readiness), ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        temporary.rename(directory)
    except Exception:
        if temporary.exists():
            shutil.rmtree(temporary)
        raise

    pointer_payload = {
        **_readiness_payload(readiness),
        "attachment_pointer_path": str(attachment_pointer.resolve()),
        "artifact_directory": str(directory.resolve()),
        "report_path": str((directory / "parser_readiness.json").resolve()),
    }
    temporary_pointer = root / ".latest_skhynix_ir_q2_parser_readiness.json.tmp"
    temporary_pointer.write_text(
        json.dumps(pointer_payload, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    temporary_pointer.replace(root / DEFAULT_Q2_PARSER_READINESS_POINTER.name)
    return pointer_payload


def load_q2_parser_readiness(
    pointer_path: str | Path = DEFAULT_Q2_PARSER_READINESS_POINTER,
    *,
    evaluation_date: date,
) -> OfficialIrQ2ParserReadiness:
    pointer_file = Path(pointer_path)
    try:
        pointer_obj: object = json.loads(pointer_file.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError) as exc:
        raise ValueError("SK hynix Q2 parser-readiness pointer is unreadable") from exc
    if not isinstance(pointer_obj, dict):
        raise ValueError("SK hynix Q2 parser-readiness pointer must be an object")
    pointer = {str(key): value for key, value in pointer_obj.items()}
    if pointer.get("status") != "skhynix_official_ir_q2_parser_readiness_captured":
        raise ValueError("SK hynix Q2 parser-readiness pointer status is invalid")
    for flag in _REQUIRED_FALSE_FLAGS:
        if pointer.get(flag) is not False:
            raise ValueError(f"SK hynix Q2 parser readiness requires {flag}=false")

    attachment_pointer = Path(str(pointer.get("attachment_pointer_path", "")))
    evidence = load_q2_attachment_evidence(
        attachment_pointer,
        evaluation_date=evaluation_date,
    )
    attachment_pointer_obj = json.loads(attachment_pointer.read_text(encoding="utf-8"))
    if not isinstance(attachment_pointer_obj, dict):
        raise ValueError("SK hynix Q2 attachment pointer must be an object")
    pdf_bytes = Path(str(attachment_pointer_obj.get("pdf_path", ""))).read_bytes()
    reconstructed = build_q2_parser_readiness(evidence, pdf_bytes=pdf_bytes)
    if reconstructed.evidence_id != str(pointer.get("evidence_id", "")):
        raise ValueError("SK hynix Q2 parser readiness does not reproduce from official bytes")

    report_path = Path(str(pointer.get("report_path", "")))
    try:
        report_obj: object = json.loads(report_path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError) as exc:
        raise ValueError("SK hynix Q2 parser-readiness report is unreadable") from exc
    if not isinstance(report_obj, dict):
        raise ValueError("SK hynix Q2 parser-readiness report must be an object")
    report = {str(key): value for key, value in report_obj.items()}
    expected = _readiness_payload(reconstructed)
    for key, value in expected.items():
        if report.get(key) != value:
            raise ValueError(f"SK hynix Q2 parser-readiness report mismatch: {key}")
    return reconstructed


__all__ = [
    "DEFAULT_Q2_PARSER_READINESS_OUTPUT",
    "DEFAULT_Q2_PARSER_READINESS_POINTER",
    "OfficialIrQ2ParserReadiness",
    "ParserContext",
    "build_q2_parser_readiness",
    "capture_q2_parser_readiness",
    "load_q2_parser_readiness",
]
