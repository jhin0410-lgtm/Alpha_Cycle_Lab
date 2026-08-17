"""Production parser dispatch for current and historical SK hynix product revenue."""

from __future__ import annotations

from alpha_cycle.intelligence.sk_hynix_opendart_historical_product_revenue_fallback import (
    HISTORICAL_PRODUCT_REVENUE_PARSER_ID,
    parse_historical_product_revenue_archive_fallback,
)
from alpha_cycle.intelligence.sk_hynix_opendart_historical_product_revenue_layout_v2 import (
    parse_historical_product_revenue_archive_v2,
    parse_historical_product_revenue_text_v2,
)
from alpha_cycle.intelligence.sk_hynix_opendart_historical_product_revenue_text_policy import (
    parse_historical_product_revenue_text_prioritized,
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
    """Prefer current parsing, then evidence-bound historical families, then legacy fallback."""

    try:
        return _current_text_parser(spec, text)
    except ValueError as current_error:
        if spec.parser_id != HISTORICAL_PRODUCT_REVENUE_PARSER_ID:
            raise
        try:
            return parse_historical_product_revenue_text_v2(spec, text)
        except ValueError as v2_error:
            try:
                return parse_historical_product_revenue_text_prioritized(spec, text)
            except ValueError as historical_error:
                raise ValueError(
                    "OpenDART product revenue text failed current and historical parsers: "
                    f"current={current_error}; v2={v2_error}; historical={historical_error}"
                ) from historical_error


def parse_periodic_product_revenue_archive(
    spec: PeriodicProductRevenueSpec,
    archive_bytes: bytes,
) -> ProductRevenueMetrics:
    """Prefer current structural replay, then strict observed historical raw layouts."""

    try:
        return _current_archive_parser(spec, archive_bytes)
    except ValueError as current_error:
        if spec.parser_id != HISTORICAL_PRODUCT_REVENUE_PARSER_ID:
            raise
        try:
            return parse_historical_product_revenue_archive_v2(spec, archive_bytes)
        except ValueError as v2_error:
            try:
                return parse_historical_product_revenue_archive_fallback(spec, archive_bytes)
            except ValueError as historical_error:
                raise ValueError(
                    "OpenDART product revenue archive failed current and historical parsers: "
                    f"current={current_error}; v2={v2_error}; historical={historical_error}"
                ) from historical_error


__all__ = [
    "parse_periodic_product_revenue_archive",
    "parse_periodic_product_revenue_text",
]
