from __future__ import annotations

from types import SimpleNamespace
from typing import cast

from alpha_cycle.intelligence.sk_hynix_product_profitability_second_wave_closeout import (
    SecondWaveCloseout,
)
from alpha_cycle.intelligence.sk_hynix_product_profitability_third_wave_closeout import (
    ThirdWaveCloseout,
)
from alpha_cycle.intelligence.sk_hynix_product_profitability_third_wave_frontier import (
    load_third_wave_frontier,
)


def test_third_wave_frontier_registers_six_exact_numeric_periods() -> None:
    frontier = load_third_wave_frontier()

    assert tuple(item.period_id for item in frontier.candidates) == (
        "2017Q1",
        "2017Q2",
        "2017Q3",
        "2018Q1",
        "2018Q2",
        "2018Q3",
    )
    assert frontier.candidates[0].drivers_qoq_percent.dram_bit_volume == -5.0
    assert frontier.candidates[0].drivers_qoq_percent.dram_asp == 24.0
    assert frontier.candidates[0].drivers_qoq_percent.nand_bit_volume == -3.0
    assert frontier.candidates[0].drivers_qoq_percent.nand_asp == 15.0
    assert frontier.candidates[-1].drivers_qoq_percent.dram_bit_volume == 5.0
    assert frontier.candidates[-1].drivers_qoq_percent.dram_asp == 1.0
    assert frontier.candidates[-1].drivers_qoq_percent.nand_bit_volume == 19.0
    assert frontier.candidates[-1].drivers_qoq_percent.nand_asp == -10.0
    assert frontier.issuer_driver_values_are_exact_numeric_source_facts is True
    assert frontier.product_revenue_certified is False
    assert frontier.company_profitability_certified is False
    assert frontier.v1_refit_enabled is False
    assert frontier.v2_fit_enabled is False
    assert frontier.reuse_2026q1_as_unseen_holdout_for_v2_allowed is False


def test_third_wave_closeout_never_opens_fit_or_reuses_spent_holdout() -> None:
    periods = tuple(
        SimpleNamespace(period_id=period)
        for period in ("2017Q1", "2017Q2", "2017Q3", "2018Q1", "2018Q2", "2018Q3")
    )
    source = cast(SecondWaveCloseout, SimpleNamespace(periods=periods))

    result = ThirdWaveCloseout(
        source=source,
        period_ids=tuple(item.period_id for item in periods),
        projected_v2_training_rows_if_all_promoted=21,
    )

    assert result.projected_v2_training_rows_if_all_promoted == 21
    assert result.v1_refit_enabled is False
    assert result.v2_fit_enabled is False
    assert result.reuse_2026q1_as_unseen_holdout_for_v2_allowed is False
    assert result.numeric_forecast_enabled is False
