"""Bootstrap the live SK hynix product-revenue CLI with semantic archive replay."""

from __future__ import annotations


def main() -> int:
    """Patch only the structural replay entrypoint before loading the existing CLI."""

    from alpha_cycle.intelligence import sk_hynix_opendart_q2_product_revenue_layout as layout
    from alpha_cycle.intelligence.sk_hynix_opendart_q2_product_revenue_semantic_replay import (
        parse_periodic_product_revenue_archive,
    )

    layout.parse_periodic_product_revenue_archive = parse_periodic_product_revenue_archive

    from alpha_cycle.sk_hynix_opendart_q2_product_revenue_certification_cli import (
        main as certification_main,
    )

    return certification_main()


if __name__ == "__main__":
    raise SystemExit(main())
