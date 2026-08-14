"""Source-specific official semiconductor IR document collection and parsing.

The collector is deliberately not a generic PDF scraper. Each supported document ID
binds issuer, source URL, publication date, accounting period, parser version, expected
page count, and identity anchors in a checked-in registry. A parser emits only fields
whose document semantics are explicitly encoded. Missing rows or changed layouts fail
closed instead of silently shifting numbers into the wrong issuer model block.
"""

from __future__ import annotations

import hashlib
import io
import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import cast
from urllib.parse import urlparse
from urllib.request import Request, urlopen

import yaml
from pypdf import PdfReader

DEFAULT_IR_DOCUMENT_REGISTRY = Path("config/semiconductor_ir_documents.yaml")


@dataclass(frozen=True)
class OfficialIrDocumentSpec:
    document_id: str
    ticker: str
    issuer_name: str
    source_id: str
    document_role: str
    content_type: str
    source_url: str
    source_published_date: date
    period_start: date
    period_end: date
    parser_id: str
    expected_page_count: int
    required_identity_anchors: tuple[str, ...]

    def __post_init__(self) -> None:
        if len(self.ticker) != 6 or not self.ticker.isdigit():
            raise ValueError("Official IR ticker must be six digits")
        if not all(
            value.strip()
            for value in (
                self.document_id,
                self.issuer_name,
                self.source_id,
                self.document_role,
                self.content_type,
                self.source_url,
                self.parser_id,
            )
        ):
            raise ValueError("Official IR document identity cannot be blank")
        if self.content_type != "pdf":
            raise ValueError("Official IR collector v1 supports PDF documents only")
        if not self.source_url.startswith("https://") or not urlparse(self.source_url).hostname:
            raise ValueError("Official IR document URL must be HTTPS")
        if self.period_start > self.period_end:
            raise ValueError("Official IR accounting period is invalid")
        if self.source_published_date < self.period_end:
            raise ValueError("Official IR publication date cannot precede period end")
        if self.expected_page_count <= 0 or not self.required_identity_anchors:
            raise ValueError("Official IR parser requires page count and identity anchors")


@dataclass(frozen=True)
class ParsedOfficialIrDocument:
    spec: OfficialIrDocumentSpec
    source_document_sha256: str
    pages: tuple[str, ...]
    baseline_facts: tuple[dict[str, object], ...]
    forward_input_claims: tuple[dict[str, object], ...]
    parser_semantics_certified: bool
    decision_score_enabled: bool = False
    numeric_forecast_enabled: bool = False

    def __post_init__(self) -> None:
        if len(self.source_document_sha256) != 64 or any(
            char not in "0123456789abcdef" for char in self.source_document_sha256
        ):
            raise ValueError("Official IR document hash must be SHA-256")
        if len(self.pages) != self.spec.expected_page_count:
            raise ValueError("Official IR parsed page count does not match registry")
        if not self.baseline_facts and not self.forward_input_claims:
            raise ValueError(
                "Official IR parser must emit at least one baseline fact or forward-input claim"
            )
        if not self.parser_semantics_certified:
            raise ValueError("Official IR parsed document semantics must be certified")
        if self.decision_score_enabled or self.numeric_forecast_enabled:
            raise ValueError("Official IR collection must remain non-scoring/non-forecast")


def _string_tuple(raw: object, label: str) -> tuple[str, ...]:
    if not isinstance(raw, list):
        raise ValueError(f"Official IR {label} must be an array")
    values: list[str] = []
    for item in raw:
        if not isinstance(item, str):
            raise ValueError(f"Official IR {label} entries must be strings")
        value = item.strip()
        if value:
            values.append(value)
    if not values:
        raise ValueError(f"Official IR {label} cannot be empty")
    return tuple(values)


def load_official_ir_document_registry(
    path: str | Path = DEFAULT_IR_DOCUMENT_REGISTRY,
) -> dict[str, OfficialIrDocumentSpec]:
    with Path(path).open(encoding="utf-8") as handle:
        payload: object = yaml.safe_load(handle)
    if not isinstance(payload, dict) or not isinstance(payload.get("issuers"), dict):
        raise ValueError("Official IR registry must contain issuers")
    specs: dict[str, OfficialIrDocumentSpec] = {}
    issuers = cast(dict[object, object], payload["issuers"])
    for ticker_raw, issuer_value in issuers.items():
        ticker = str(ticker_raw).strip().zfill(6)
        if not isinstance(issuer_value, dict):
            raise ValueError(f"Official IR issuer entry must be an object: {ticker}")
        issuer = cast(dict[object, object], issuer_value)
        issuer_name = str(issuer.get("issuer_name", "")).strip()
        documents = issuer.get("documents", {})
        if not isinstance(documents, dict):
            raise ValueError(f"Official IR documents must be an object: {ticker}")
        for document_id_raw, document_value in cast(dict[object, object], documents).items():
            document_id = str(document_id_raw).strip()
            if not isinstance(document_value, dict):
                raise ValueError(f"Official IR document must be an object: {document_id}")
            raw = cast(dict[object, object], document_value)
            spec = OfficialIrDocumentSpec(
                document_id=document_id,
                ticker=ticker,
                issuer_name=issuer_name,
                source_id=str(raw.get("source_id", "")).strip(),
                document_role=str(raw.get("document_role", "")).strip(),
                content_type=str(raw.get("content_type", "")).strip(),
                source_url=str(raw.get("source_url", "")).strip(),
                source_published_date=date.fromisoformat(
                    str(raw.get("source_published_date", ""))
                ),
                period_start=date.fromisoformat(str(raw.get("period_start", ""))),
                period_end=date.fromisoformat(str(raw.get("period_end", ""))),
                parser_id=str(raw.get("parser_id", "")).strip(),
                expected_page_count=int(str(raw.get("expected_page_count", 0))),
                required_identity_anchors=_string_tuple(
                    raw.get("required_identity_anchors", []),
                    "required_identity_anchors",
                ),
            )
            if document_id in specs:
                raise ValueError(f"Official IR document_id is duplicated: {document_id}")
            specs[document_id] = spec
    if not specs:
        raise ValueError("Official IR registry has no supported documents")
    return specs


def download_official_ir_document(
    spec: OfficialIrDocumentSpec,
    *,
    timeout_seconds: float = 20.0,
) -> bytes:
    request = Request(
        spec.source_url,
        headers={"User-Agent": "Alpha-Cycle-Lab/0.1 official-ir-readonly"},
        method="GET",
    )
    with urlopen(request, timeout=timeout_seconds) as response:  # noqa: S310
        content = bytes(response.read())
    if not content.startswith(b"%PDF-"):
        raise ValueError(f"Official IR document is not a PDF: {spec.document_id}")
    return content


def extract_pdf_pages(data: bytes) -> tuple[str, ...]:
    try:
        reader = PdfReader(io.BytesIO(data), strict=True)
    except Exception as exc:
        raise ValueError("Official IR PDF cannot be parsed") from exc
    pages: list[str] = []
    for page in reader.pages:
        text = page.extract_text() or ""
        pages.append(text.replace("\x00", ""))
    return tuple(pages)


def _normalized(text: str) -> str:
    return " ".join(text.replace("\u00a0", " ").split())


def _number(text: str, pattern: str, label: str) -> float:
    match = re.search(pattern, text, flags=re.IGNORECASE)
    if match is None:
        raise ValueError(f"Samsung 2Q26 parser could not locate {label}")
    token = match.group(1).strip()
    negative = token.startswith("(") and token.endswith(")")
    number = float(token.strip("()"))
    return -number if negative else number


def _source_fact(
    spec: OfficialIrDocumentSpec,
    document_sha256: str,
    *,
    scope_id: str,
    metric_id: str,
    value: float,
) -> dict[str, object]:
    return {
        "ticker": spec.ticker,
        "scope_id": scope_id,
        "metric_id": metric_id,
        "value": value,
        "unit": "KRW_trillion",
        "period_start": spec.period_start.isoformat(),
        "period_end": spec.period_end.isoformat(),
        "source_id": spec.source_id,
        "source_url": spec.source_url,
        "source_published_date": spec.source_published_date.isoformat(),
        "source_document_sha256": document_sha256,
        "source_bytes_archived": True,
        "semantics_certified": True,
        "source_vintage_certified": True,
    }


def _forward_claim(
    spec: OfficialIrDocumentSpec,
    document_sha256: str,
    *,
    block_id: str,
    metric_id: str,
    statement: str,
) -> dict[str, object]:
    return {
        "ticker": spec.ticker,
        "block_id": block_id,
        "claim_type": "forward_driver",
        "metric_id": metric_id,
        "evidence_kind": "qualitative",
        "statement": statement,
        "numeric_value": None,
        "unit": None,
        "period_start": "2026-07-01",
        "period_end": "2026-12-31",
        "source_id": spec.source_id,
        "source_url": spec.source_url,
        "source_published_date": spec.source_published_date.isoformat(),
        "semantics_certified": True,
        "source_vintage_certified": True,
        "reuse_or_license_basis_documented": False,
        "source_document_sha256": document_sha256,
        "source_bytes_archived": True,
        "parser_id": spec.parser_id,
    }


def parse_samsung_2026q2(
    spec: OfficialIrDocumentSpec,
    data: bytes,
    pages: tuple[str, ...],
) -> ParsedOfficialIrDocument:
    if spec.parser_id != "samsung_earnings_presentation_2026q2_v1":
        raise ValueError("Samsung 2Q26 parser received the wrong parser_id")
    if len(pages) != spec.expected_page_count:
        raise ValueError(
            "Samsung 2Q26 page count changed: "
            f"expected={spec.expected_page_count} actual={len(pages)}"
        )
    whole = _normalized("\n".join(pages))
    for anchor in spec.required_identity_anchors:
        if _normalized(anchor).casefold() not in whole.casefold():
            raise ValueError(f"Samsung 2Q26 identity anchor is missing: {anchor}")

    appendix = _normalized(pages[12])
    if "Appendix 2: Results by Business Segment".casefold() not in appendix.casefold():
        raise ValueError("Samsung 2Q26 Appendix 2 is missing from expected page")

    values = {
        ("dx", "revenue"): _number(
            appendix,
            r"\bDX\s+43\.6\s+52\.7\s+(48\.0)\b",
            "DX 2Q26 revenue",
        ),
        ("dx", "operating_income"): _number(
            appendix,
            r"\bDX\s+3\.3\s+3\.0\s+(\(0\.8\))",
            "DX 2Q26 operating income",
        ),
        ("ds_memory", "revenue"): _number(
            appendix,
            r"\bMemory\s+21\.2\s+74\.8\s+(120\.8)\b",
            "Memory 2Q26 revenue",
        ),
        ("sdc", "revenue"): _number(
            appendix,
            r"\bSDC\s+6\.4\s+6\.7\s+(7\.5)\b",
            "SDC 2Q26 revenue",
        ),
        ("sdc", "operating_income"): _number(
            appendix,
            r"\bSDC\s+0\.5\s+0\.4\s+(0\.7)\b",
            "SDC 2Q26 operating income",
        ),
        ("harman", "revenue"): _number(
            appendix,
            r"\bHarman\s+3\.8\s+3\.8\s+(4\.6)\b",
            "Harman 2Q26 revenue",
        ),
        ("harman", "operating_income"): _number(
            appendix,
            r"\bHarman\s+0\.5\s+0\.2\s+(0\.4)\b",
            "Harman 2Q26 operating income",
        ),
    }
    document_sha256 = hashlib.sha256(data).hexdigest()
    facts = tuple(
        _source_fact(
            spec,
            document_sha256,
            scope_id=scope_id,
            metric_id=metric_id,
            value=value,
        )
        for (scope_id, metric_id), value in values.items()
    )

    memory_page = _normalized(pages[6])
    foundry_page = _normalized(pages[7])
    if "Scaled up HBM4 sales".casefold() not in memory_page.casefold():
        raise ValueError("Samsung 2Q26 HBM outlook anchor is missing")
    if "Higher utilization, stronger advanced node demand".casefold() not in whole.casefold():
        raise ValueError("Samsung 2Q26 foundry utilization anchor is missing")
    if "2nm Gen 2 mobile ramp-up".casefold() not in foundry_page.casefold():
        raise ValueError("Samsung 2Q26 foundry ramp anchor is missing")

    claims = (
        _forward_claim(
            spec,
            document_sha256,
            block_id="ds_memory",
            metric_id="hbm_volume_and_mix",
            statement=(
                "Samsung reported scaling HBM4 sales and expects strong AI/server memory demand "
                "to remain an important mix driver in H2 2026."
            ),
        ),
        _forward_claim(
            spec,
            document_sha256,
            block_id="ds_foundry_system_lsi",
            metric_id="foundry_utilization",
            statement=(
                "Samsung reported higher foundry utilization and stronger advanced-node demand."
            ),
        ),
        _forward_claim(
            spec,
            document_sha256,
            block_id="ds_foundry_system_lsi",
            metric_id="customer_ramp",
            statement=(
                "Samsung outlined 2nm Gen 2 mobile and 4nm LPU/Base-Die ramps for H2 2026."
            ),
        ),
    )
    return ParsedOfficialIrDocument(
        spec=spec,
        source_document_sha256=document_sha256,
        pages=pages,
        baseline_facts=facts,
        forward_input_claims=claims,
        parser_semantics_certified=True,
    )


def parse_official_ir_document(
    spec: OfficialIrDocumentSpec,
    data: bytes,
) -> ParsedOfficialIrDocument:
    pages = extract_pdf_pages(data)
    if spec.parser_id == "samsung_earnings_presentation_2026q2_v1":
        return parse_samsung_2026q2(spec, data, pages)
    raise ValueError(f"Official IR parser is not implemented: {spec.parser_id}")


__all__ = [
    "DEFAULT_IR_DOCUMENT_REGISTRY",
    "OfficialIrDocumentSpec",
    "ParsedOfficialIrDocument",
    "download_official_ir_document",
    "extract_pdf_pages",
    "load_official_ir_document_registry",
    "parse_official_ir_document",
    "parse_samsung_2026q2",
]
