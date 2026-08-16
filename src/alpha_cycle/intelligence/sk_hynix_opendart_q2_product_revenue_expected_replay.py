"""Structural replay for SK hynix 2Q26 OpenDART product revenue.

The exact OpenDART ZIP is already retained and hash-bound, and its normalized text is
reproduced from those bytes by the document provider.  This module therefore gives the
raw-source side one narrow job: certify that the archive contains exactly one current
consolidated DRAM/NAND/Other/Total product header with the same KRW unit as the values
parsed from normalized text.

It intentionally does not try to rediscover the four amounts from HTML text-token order.
OpenDART may split labels, values, layout tables, and comparative-period markers in ways
that are presentation-specific.  Requiring a second value-discovery algorithm over that
layout created false negatives without adding an independent source.  Value provenance
remains fail-closed through exact ZIP retention, normalized-text reproduction, direct
product parsing, company-revenue reconciliation, and parser-contract binding.
"""

from __future__ import annotations

import io
import zipfile
from datetime import UTC, datetime
from pathlib import PurePosixPath

from alpha_cycle.intelligence.sk_hynix_opendart_q2_product_revenue_certification import (
    PeriodicProductRevenueSpec,
    ProductRevenueMetrics,
)
from alpha_cycle.intelligence.sk_hynix_opendart_q2_product_revenue_layout import (
    parse_periodic_product_revenue_text,
)
from alpha_cycle.intelligence.sk_hynix_opendart_q2_product_revenue_semantic_replay import (
    _PRODUCT_KEYS,
    _REVENUE_LABELS,
    _TEXT_SUFFIXES,
    _accepted,
    _header_candidates,
    _header_product_order,
    _SourceTokenExtractor,
)
from alpha_cycle.intelligence.sk_hynix_opendart_q2_product_revenue_table import (
    _grid,
    _normalized,
    _TableExtractor,
)
from alpha_cycle.intelligence.sk_hynix_opendart_q2_product_revenue_table import (
    _unit as _structured_unit,
)
from alpha_cycle.providers.opendart_documents import (
    _decode_text,
    _parse_document_archive,
    _safe_member_name,
)


def _expected_from_archive(
    spec: PeriodicProductRevenueSpec,
    archive_bytes: bytes,
) -> ProductRevenueMetrics:
    document = _parse_document_archive(
        archive_bytes,
        receipt="offline-replay",
        retrieved_at=datetime(2000, 1, 1, tzinfo=UTC),
    )
    if document.text_truncated:
        raise ValueError("OpenDART structural replay refuses truncated normalized text")
    return parse_periodic_product_revenue_text(spec, document.text)


def parse_periodic_product_revenue_archive(
    spec: PeriodicProductRevenueSpec,
    archive_bytes: bytes,
) -> ProductRevenueMetrics:
    """Certify one current consolidated product header for normalized direct amounts."""

    expected = _expected_from_archive(spec, archive_bytes)
    try:
        archive = zipfile.ZipFile(io.BytesIO(archive_bytes))
    except zipfile.BadZipFile as exc:
        raise ValueError("OpenDART structural replay source is not a ZIP") from exc

    structural_headers = 0
    matching_units = 0
    raw_revenue_labels = 0
    accepted_revenue = _accepted(_REVENUE_LABELS)

    with archive:
        for info in archive.infolist():
            if info.is_dir():
                continue
            safe_name = _safe_member_name(info.filename)
            if PurePosixPath(safe_name).suffix.casefold() not in _TEXT_SUFFIXES:
                continue
            decoded, _encoding = _decode_text(archive.read(info))

            table_parser = _TableExtractor()
            table_parser.feed(decoded)
            table_parser.close()
            headers = _header_candidates(spec, table_parser.tables)
            structural_headers += len(headers)

            source_parser = _SourceTokenExtractor()
            source_parser.feed(decoded)
            source_parser.close()
            raw_revenue_labels += sum(
                1
                for token in source_parser.tokens
                if _normalized(token) in accepted_revenue
            )

            for _header_index, header in headers:
                if _header_product_order(spec, header) != _PRODUCT_KEYS:
                    continue
                unit, _scale = _structured_unit(header, _grid(header))
                if unit == expected.unit:
                    matching_units += 1

    if structural_headers != 1 or matching_units != 1 or raw_revenue_labels < 1:
        raise ValueError(
            "OpenDART structural product-revenue gate did not certify normalized facts: "
            f"current_consolidated_headers={structural_headers} "
            f"matching_unit_headers={matching_units} "
            f"raw_source_revenue_labels={raw_revenue_labels} "
            f"expected={expected}"
        )
    return expected


__all__ = ["parse_periodic_product_revenue_archive"]
