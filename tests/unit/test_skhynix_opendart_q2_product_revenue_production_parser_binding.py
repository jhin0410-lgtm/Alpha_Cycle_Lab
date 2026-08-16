from __future__ import annotations

from alpha_cycle.intelligence import sk_hynix_opendart_q2_product_revenue_capture as capture
from alpha_cycle.intelligence import (
    sk_hynix_opendart_q2_product_revenue_certification_verifier as verifier,
)
from alpha_cycle.intelligence.sk_hynix_opendart_q2_product_revenue_expected_replay import (
    parse_periodic_product_revenue_archive as production_archive_parser,
)
from alpha_cycle.intelligence.sk_hynix_opendart_q2_product_revenue_layout import (
    parse_periodic_product_revenue_archive as legacy_layout_archive_parser,
)


def test_capture_and_verifier_bind_directly_to_production_archive_parser() -> None:
    assert capture.parse_periodic_product_revenue_archive is production_archive_parser
    assert verifier.parse_periodic_product_revenue_archive is production_archive_parser
    assert production_archive_parser is not legacy_layout_archive_parser
