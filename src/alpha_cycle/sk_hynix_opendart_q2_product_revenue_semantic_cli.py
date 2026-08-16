"""Stable entrypoint for SK hynix OpenDART product-revenue certification."""

from __future__ import annotations

from alpha_cycle.sk_hynix_opendart_q2_product_revenue_certification_cli import (
    main as certification_main,
)


def main() -> int:
    """Run certification with production parser bindings declared by each component."""

    return certification_main()


if __name__ == "__main__":
    raise SystemExit(main())
