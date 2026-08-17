from __future__ import annotations

from alpha_cycle.intelligence.sk_hynix_product_profitability_second_wave_frontier import (
    load_second_wave_frontier,
)


def test_second_wave_frontier_is_exact_six_rows_with_numeric_driver_facts() -> None:
    frontier = load_second_wave_frontier()

    assert [item.period_id for item in frontier.candidates] == [
        "2019Q1",
        "2019Q2",
        "2019Q3",
        "2020Q1",
        "2020Q2",
        "2020Q3",
    ]
    assert frontier.target_additional_training_rows == 6
    assert frontier.issuer_driver_values_are_exact_numeric_source_facts is True
    assert frontier.candidates[0].drivers_qoq_percent.dram_bit_volume == -8
    assert frontier.candidates[0].drivers_qoq_percent.dram_asp == -27
    assert frontier.candidates[0].drivers_qoq_percent.nand_bit_volume == -6
    assert frontier.candidates[0].drivers_qoq_percent.nand_asp == -32
    assert frontier.candidates[-1].drivers_qoq_percent.dram_bit_volume == 4
    assert frontier.candidates[-1].drivers_qoq_percent.dram_asp == -7
    assert frontier.candidates[-1].drivers_qoq_percent.nand_bit_volume == 9
    assert frontier.candidates[-1].drivers_qoq_percent.nand_asp == -10
    assert frontier.product_revenue_certified is False
    assert frontier.company_profitability_certified is False
    assert frontier.training_row_promoted is False
    assert frontier.candidate_registration_enables_fit is False
    assert frontier.candidate_registration_enables_holdout is False
    assert frontier.holdout_period == "2026Q1"
