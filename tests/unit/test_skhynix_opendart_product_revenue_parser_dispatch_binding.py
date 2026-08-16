from __future__ import annotations


def test_capture_and_verifier_share_production_product_revenue_dispatch() -> None:
    from alpha_cycle.intelligence import (
        sk_hynix_opendart_product_revenue_parser_dispatch as dispatch,
    )
    from alpha_cycle.intelligence import (
        sk_hynix_opendart_q2_product_revenue_capture as capture,
    )
    from alpha_cycle.intelligence import (
        sk_hynix_opendart_q2_product_revenue_certification_verifier as verifier,
    )

    assert (
        capture.parse_periodic_product_revenue_text
        is dispatch.parse_periodic_product_revenue_text
    )
    assert (
        verifier.parse_periodic_product_revenue_text
        is dispatch.parse_periodic_product_revenue_text
    )
    assert (
        capture.parse_periodic_product_revenue_archive
        is dispatch.parse_periodic_product_revenue_archive
    )
    assert (
        verifier.parse_periodic_product_revenue_archive
        is dispatch.parse_periodic_product_revenue_archive
    )
