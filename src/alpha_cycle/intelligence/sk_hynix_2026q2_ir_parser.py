"""Parser contract for the SK hynix FY2026 Q2 earnings presentation.

The parser is available to the source-guarded official-IR dispatch path, but no SK hynix
2Q26 production document is registered.  Capture therefore remains impossible until an
exact official source URL and source bytes are independently verified and added to the
checked-in registry.

The candidate presentation provides useful forward operating guidance but does not
directly disclose the product-level profitability facts required by Alpha Cycle's
baseline-reconciliation contract.  The parser therefore emits forward-input claims only
and never manufactures DRAM/NAND accounting bridges.
"""

from __future__ import annotations

import hashlib
from datetime import date

from alpha_cycle.intelligence.official_semiconductor_ir_collector import (
    OfficialIrDocumentSpec,
    ParsedOfficialIrDocument,
)

_PARSER_ID = "sk_hynix_earnings_presentation_2026q2_v1"
_Q3_START = date(2026, 7, 1)
_Q3_END = date(2026, 9, 30)
_H2_START = date(2026, 7, 1)
_H2_END = date(2026, 12, 31)


def _normalized(text: str) -> str:
    return " ".join(text.replace("\u00a0", " ").split())


def _require_anchor(text: str, anchor: str, label: str) -> None:
    if _normalized(anchor).casefold() not in _normalized(text).casefold():
        raise ValueError(f"SK hynix 2Q26 {label} anchor is missing")


def _forward_claim(
    spec: OfficialIrDocumentSpec,
    document_sha256: str,
    *,
    block_id: str,
    metric_id: str,
    statement: str,
    period_start: date,
    period_end: date,
    numeric_value: float | None = None,
    unit: str | None = None,
) -> dict[str, object]:
    if (numeric_value is None) != (unit is None):
        raise ValueError("SK hynix numeric forward claim requires both value and unit")
    evidence_kind = "numeric" if numeric_value is not None else "qualitative"
    return {
        "ticker": spec.ticker,
        "block_id": block_id,
        "claim_type": "forward_driver",
        "metric_id": metric_id,
        "evidence_kind": evidence_kind,
        "statement": statement,
        "numeric_value": numeric_value,
        "unit": unit,
        "period_start": period_start.isoformat(),
        "period_end": period_end.isoformat(),
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


def parse_sk_hynix_2026q2(
    spec: OfficialIrDocumentSpec,
    data: bytes,
    pages: tuple[str, ...],
) -> ParsedOfficialIrDocument:
    """Parse only source-bounded forward guidance from the candidate 2Q26 deck."""

    if spec.parser_id != _PARSER_ID:
        raise ValueError("SK hynix 2Q26 parser received the wrong parser_id")
    if spec.ticker != "000660" or spec.source_id != "sk_hynix_ir":
        raise ValueError("SK hynix 2Q26 parser received the wrong issuer/source identity")
    if len(pages) != spec.expected_page_count:
        raise ValueError(
            "SK hynix 2Q26 page count changed: "
            f"expected={spec.expected_page_count} actual={len(pages)}"
        )

    whole = _normalized("\n".join(pages))
    for anchor in spec.required_identity_anchors:
        _require_anchor(whole, anchor, "identity")

    q3_guidance = _normalized(pages[8])
    hbm_outlook = _normalized(pages[9])
    _require_anchor(q3_guidance, "Q3 B/G : Approx. 10% increase QoQ", "DRAM Q3 B/G")
    _require_anchor(
        q3_guidance,
        "Q3 B/G : Low-single% increase QoQ",
        "NAND Q3 B/G",
    )
    _require_anchor(q3_guidance, "Active response centered on SV products", "DRAM product mix")
    _require_anchor(hbm_outlook, "Began HBM4 shipment in Q2", "HBM4 shipment")
    _require_anchor(hbm_outlook, "Full ramp up planned in 2H", "HBM4 generation mix")

    document_sha256 = hashlib.sha256(data).hexdigest()
    claims = (
        _forward_claim(
            spec,
            document_sha256,
            block_id="dram_total",
            metric_id="dram_bit_shipment_growth",
            statement=(
                "SK hynix guided Q3 2026 DRAM bit growth to approximately 10% quarter over "
                "quarter."
            ),
            period_start=_Q3_START,
            period_end=_Q3_END,
            numeric_value=10.0,
            unit="percent_qoq",
        ),
        _forward_claim(
            spec,
            document_sha256,
            block_id="nand_and_solutions",
            metric_id="nand_bit_shipment_growth",
            statement=(
                "SK hynix guided Q3 2026 NAND bit growth, including Solidigm, to a low-single-"
                "digit percentage increase quarter over quarter."
            ),
            period_start=_Q3_START,
            period_end=_Q3_END,
        ),
        _forward_claim(
            spec,
            document_sha256,
            block_id="dram_total",
            metric_id="dram_product_mix",
            statement=(
                "SK hynix described an active Q3 response centered on SV products; the parser "
                "preserves the issuer wording rather than expanding the abbreviation into an "
                "unsupported numeric mix assumption."
            ),
            period_start=_Q3_START,
            period_end=_Q3_END,
        ),
        _forward_claim(
            spec,
            document_sha256,
            block_id="hbm_mix_overlay",
            metric_id="hbm_generation_mix",
            statement=(
                "SK hynix stated that HBM4 shipments began in Q2 and a full HBM4 ramp is "
                "planned for the second half of 2026."
            ),
            period_start=_H2_START,
            period_end=_H2_END,
        ),
    )
    return ParsedOfficialIrDocument(
        spec=spec,
        source_document_sha256=document_sha256,
        pages=pages,
        baseline_facts=(),
        forward_input_claims=claims,
        parser_semantics_certified=True,
    )


__all__ = ["parse_sk_hynix_2026q2"]
