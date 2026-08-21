from __future__ import annotations

import inspect

from alpha_cycle.intelligence import sk_hynix_company_gp_ex_ante_pit_panel_replay as replay
from alpha_cycle.intelligence import sk_hynix_opendart_product_revenue_source_consensus as consensus


def test_pit_panel_replay_binds_product_parsing_to_source_consensus() -> None:
    assert (
        replay.parse_periodic_product_revenue_source_consensus
        is consensus.parse_periodic_product_revenue_source_consensus
    )

    source = inspect.getsource(replay._capture_product_source_for_replay)
    assert "parse_periodic_product_revenue_source_consensus" in source
    assert "parse_periodic_product_revenue_text" not in source
    assert "parse_periodic_product_revenue_archive" not in source


def test_pit_panel_replay_does_not_expose_duplicate_parser_authority() -> None:
    assert not hasattr(replay, "parse_periodic_product_revenue_text")
    assert not hasattr(replay, "parse_periodic_product_revenue_archive")
