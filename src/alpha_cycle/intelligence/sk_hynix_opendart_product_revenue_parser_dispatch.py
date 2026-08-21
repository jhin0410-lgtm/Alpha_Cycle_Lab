"""Production parser dispatch for current and historical SK hynix product revenue."""

from __future__ import annotations

import io
import re
import zipfile

from alpha_cycle.intelligence.sk_hynix_opendart_historical_product_revenue_fallback import (
    HISTORICAL_PRODUCT_REVENUE_PARSER_ID,
    parse_historical_product_revenue_archive_fallback,
)
from alpha_cycle.intelligence.sk_hynix_opendart_historical_product_revenue_layout_v2 import (
    parse_historical_product_revenue_archive_v2,
    parse_historical_product_revenue_text_v2,
)
from alpha_cycle.intelligence.sk_hynix_opendart_historical_product_revenue_layout_v3 import (
    parse_historical_product_revenue_archive_v3,
    parse_historical_product_revenue_text_v3,
)
from alpha_cycle.intelligence.sk_hynix_opendart_historical_product_revenue_layout_v4 import (
    parse_historical_product_revenue_archive_v4,
)
from alpha_cycle.intelligence.sk_hynix_opendart_historical_product_revenue_text_policy import (
    parse_historical_product_revenue_text_prioritized,
)
from alpha_cycle.intelligence.sk_hynix_opendart_pre2023_certified_replay import (
    is_pre2023_certified_product_revenue_period,
    parse_pre2023_certified_product_revenue_archive,
    parse_pre2023_certified_product_revenue_text,
)
from alpha_cycle.intelligence.sk_hynix_opendart_q2_product_revenue_certification import (
    PeriodicProductRevenueSpec,
    ProductRevenueMetrics,
)
from alpha_cycle.intelligence.sk_hynix_opendart_q2_product_revenue_expected_replay import (
    parse_periodic_product_revenue_archive as _current_archive_parser,
)
from alpha_cycle.intelligence.sk_hynix_opendart_q2_product_revenue_layout import (
    parse_periodic_product_revenue_text as _current_text_parser,
)
from alpha_cycle.providers.opendart_documents import MAX_DOCUMENT_UNCOMPRESSED_BYTES

_LEGACY_ROOT_RECEIPT_MEMBER = re.compile(r"^/([0-9]{14}\.xml)$", re.IGNORECASE)


def _legacy_root_receipt_archive_parse_view(archive_bytes: bytes) -> bytes:
    """Return a parser-only safe-name ZIP for one observed legacy OpenDART shape.

    The source bytes are never replaced in provenance evidence.  A view is created only
    when the archive has exactly one file and its member is `/14-digit-receipt.xml`.
    All other archives are returned unchanged so the normal strict path checks remain in
    force downstream.
    """

    try:
        source = zipfile.ZipFile(io.BytesIO(archive_bytes))
    except zipfile.BadZipFile:
        return archive_bytes
    with source:
        infos = [info for info in source.infolist() if not info.is_dir()]
        if len(infos) != 1:
            return archive_bytes
        info = infos[0]
        match = _LEGACY_ROOT_RECEIPT_MEMBER.fullmatch(info.filename.replace("\\", "/"))
        if match is None:
            return archive_bytes
        if info.file_size < 0 or info.compress_size < 0:
            raise ValueError("OpenDART document archive has invalid member sizes")
        if info.file_size > MAX_DOCUMENT_UNCOMPRESSED_BYTES:
            raise ValueError("OpenDART document archive exceeds the uncompressed-size limit")
        payload = source.read(info)
        if len(payload) != info.file_size:
            raise ValueError("OpenDART document member size changed while reading")

    output = io.BytesIO()
    with zipfile.ZipFile(output, mode="w", compression=zipfile.ZIP_DEFLATED) as target:
        target.writestr(match.group(1), payload)
    return output.getvalue()


def parse_periodic_product_revenue_text(
    spec: PeriodicProductRevenueSpec,
    text: str,
) -> ProductRevenueMetrics:
    """Preserve strict current precedence, then exact legacy anchors and historical fallbacks."""

    try:
        return _current_text_parser(spec, text)
    except ValueError as current_error:
        if spec.parser_id != HISTORICAL_PRODUCT_REVENUE_PARSER_ID:
            raise
        try:
            return parse_pre2023_certified_product_revenue_text(spec, text)
        except ValueError as anchored_error:
            if is_pre2023_certified_product_revenue_period(spec):
                raise
            try:
                return parse_historical_product_revenue_text_prioritized(spec, text)
            except ValueError as historical_error:
                try:
                    return parse_historical_product_revenue_text_v2(spec, text)
                except ValueError as v2_error:
                    try:
                        return parse_historical_product_revenue_text_v3(spec, text)
                    except ValueError as v3_error:
                        raise ValueError(
                            "OpenDART product revenue text failed current and historical parsers: "
                            f"current={current_error}; anchored={anchored_error}; "
                            f"historical={historical_error}; v2={v2_error}; v3={v3_error}"
                        ) from v3_error


def parse_periodic_product_revenue_archive(
    spec: PeriodicProductRevenueSpec,
    archive_bytes: bytes,
) -> ProductRevenueMetrics:
    """Preserve raw-source anchors, then use a narrow view for legacy parser compatibility."""

    try:
        return _current_archive_parser(spec, archive_bytes)
    except ValueError as current_error:
        if spec.parser_id != HISTORICAL_PRODUCT_REVENUE_PARSER_ID:
            raise
        try:
            return parse_pre2023_certified_product_revenue_archive(spec, archive_bytes)
        except ValueError as anchored_error:
            if is_pre2023_certified_product_revenue_period(spec):
                raise
            parse_archive = _legacy_root_receipt_archive_parse_view(archive_bytes)
            try:
                return parse_historical_product_revenue_archive_fallback(spec, parse_archive)
            except ValueError as historical_error:
                try:
                    return parse_historical_product_revenue_archive_v2(spec, parse_archive)
                except ValueError as v2_error:
                    try:
                        return parse_historical_product_revenue_archive_v3(spec, parse_archive)
                    except ValueError as v3_error:
                        try:
                            return parse_historical_product_revenue_archive_v4(
                                spec,
                                parse_archive,
                            )
                        except ValueError as v4_error:
                            raise ValueError(
                                "OpenDART product revenue archive failed current and historical "
                                "parsers: "
                                f"current={current_error}; anchored={anchored_error}; "
                                f"historical={historical_error}; v2={v2_error}; "
                                f"v3={v3_error}; v4={v4_error}"
                            ) from v4_error


__all__ = [
    "parse_periodic_product_revenue_archive",
    "parse_periodic_product_revenue_text",
]
