from __future__ import annotations

from alpha_cycle.intelligence.sk_hynix_pre2023_certified_product_revenue_registry import (
    load_certified_pre2023_product_revenue_registry,
)


def test_pre2023_certified_product_revenue_registry_is_complete_and_fail_closed() -> None:
    registry = load_certified_pre2023_product_revenue_registry()

    assert registry.ticker == "000660"
    assert [item.period_id for item in registry.periods] == [
        "2021Q1",
        "2021Q2",
        "2021Q3",
        "2022Q1",
        "2022Q2",
        "2022Q3",
    ]
    assert all(item.direct_product_revenue_certified for item in registry.periods)
    assert all(
        item.dram_revenue_million_krw
        + item.nand_revenue_million_krw
        + item.other_revenue_million_krw
        == item.total_revenue_million_krw
        for item in registry.periods
    )
    assert all(
        item.total_revenue_million_krw * 1_000_000 == item.company_revenue_krw
        for item in registry.periods
    )
    assert registry.current_retrieval_historical_source_fact is True
    assert registry.historical_vintage_certified is False
    assert registry.point_in_time_backtest_eligible is False
    assert registry.training_row_promoted is False
    assert registry.fit_enabled is False
    assert registry.holdout_evaluation_allowed is False
