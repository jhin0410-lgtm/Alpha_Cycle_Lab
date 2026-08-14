"""Canonical source-policy and parser dispatch for registered official semiconductor IR.

A parser implementation may exist before a document is production-registered.  This
module lets the capture path support that parser without weakening registry observability:
no document can be collected unless it is separately present in the checked-in registry.
"""

from __future__ import annotations

from urllib.parse import urlparse

from alpha_cycle.intelligence.official_semiconductor_ir_collector import (
    OfficialIrDocumentSpec,
    ParsedOfficialIrDocument,
    extract_pdf_pages,
    parse_samsung_2026q2,
)

_SK_HYNIX_PARSER_ID = "sk_hynix_earnings_presentation_2026q2_v1"
_SK_HYNIX_ALLOWED_HOSTS = frozenset(
    {
        "www.skhynix.com",
        "skhynix.com",
        "mis-prod-koce-homepage-cdn-01-blob-ep.azureedge.net",
    }
)


def validate_official_ir_source_policy(spec: OfficialIrDocumentSpec) -> None:
    """Fail closed when a source-specific registry entry points outside issuer-controlled IR."""

    host = (urlparse(spec.source_url).hostname or "").casefold()
    if spec.source_id == "sk_hynix_ir" and host not in _SK_HYNIX_ALLOWED_HOSTS:
        raise ValueError(
            "SK hynix official IR must stay on the issuer site or its registered official CDN"
        )


def parse_official_ir_document(
    spec: OfficialIrDocumentSpec,
    data: bytes,
) -> ParsedOfficialIrDocument:
    """Dispatch a registered document to its source-specific parser after source-policy checks."""

    validate_official_ir_source_policy(spec)
    pages = extract_pdf_pages(data)
    if spec.parser_id == "samsung_earnings_presentation_2026q2_v2":
        return parse_samsung_2026q2(spec, data, pages)
    if spec.parser_id == _SK_HYNIX_PARSER_ID:
        # Lazy import avoids a module cycle: the SK hynix parser uses the collector's
        # shared OfficialIrDocumentSpec/ParsedOfficialIrDocument contracts.
        from alpha_cycle.intelligence.sk_hynix_2026q2_ir_parser import parse_sk_hynix_2026q2

        return parse_sk_hynix_2026q2(spec, data, pages)
    raise ValueError(f"Official IR parser is not implemented: {spec.parser_id}")


__all__ = [
    "parse_official_ir_document",
    "validate_official_ir_source_policy",
]
