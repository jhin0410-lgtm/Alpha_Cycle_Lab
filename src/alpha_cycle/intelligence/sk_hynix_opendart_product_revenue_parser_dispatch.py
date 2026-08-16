"""Production parser dispatch for current and historical SK hynix product revenue."""

from __future__ import annotations

from alpha_cycle.intelligence.sk_hynix_opendart_historical_product_revenue_fallback import (
    HISTORICAL_PRODUCT_REVENUE_PARSER_ID,
    parse_historical_product_revenue_archive_fallback,
    parse_historical_product_revenue_text_fallback,
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


def parse_periodic_product_revenue_text(
    spec: PeriodicProductRevenueSpec,
    text: str,
) -> ProductRevenueMetrics:
    """Prefer the current parser and use historical fallback only for its bound id."""

    try:
        return _current_text_parser(spec, text)
    except ValueError as current_error:
        if spec.parser_id != HISTORICAL_PRODUCT_REVENUE_PARSER_ID:
            raise
        try:
            return parse_historical_product_revenue_text_fallback(spec, text)
        except ValueError as historical_error:
            raise ValueError(
                "OpenDART product revenue text failed current and historical parsers: "
                f"current={current_error}; historical={historical_error}"
            ) from historical_error


def parse_periodic_product_revenue_archive(
    spec: PeriodicProductRevenueSpec,
    archive_bytes: bytes,
) -> ProductRevenueMetrics:
    """Prefer current structural replay and fall back only to strict historical rows."""

    try:
        return _current_archive_parser(spec, archive_bytes)
    except ValueError as current_error:
        if spec.parser_id != HISTORICAL_PRODUCT_REVENUE_PARSER_ID:
            raise
        try:
            return parse_historical_product_revenue_archive_fallback(spec, archive_bytes)
        except ValueError as historical_error:
            raise ValueError(
                "OpenDART product revenue archive failed current and historical parsers: "
                f"current={current_error}; historical={historical_error}"
            ) from historical_error


__all__ = [
    "parse_periodic_product_revenue_archive",
    "parse_periodic_product_revenue_text",
]
