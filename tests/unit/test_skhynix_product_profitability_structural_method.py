from __future__ import annotations

from datetime import date
from types import SimpleNamespace

import pytest

from alpha_cycle.intelligence.sk_hynix_product_profitability_structural_method import (
    build_structural_rank_probe,
    encode_direction_sign,
    load_structural_profitability_method,
)

_PERIODS = (
    "2023Q1",
    "2023Q2",
    "2023Q3",
    "2024Q1",
    "2024Q2",
    "2024Q3",
    "2025Q1",
    "2025Q2",
    "2025Q3",
)
_FULL_RANK_SIGNS = (
    (-1, 1, -1, 0),
    (-1, 0, 0, 0),
    (1, 0, -1, -1),
    (0, -1, 0, 0),
    (1, -1, 1, 0),
    (0, 1, -1, 1),
    (-1, 0, -1, -1),
)


def _text(sign: int) -> str:
    return {
        -1: "Around 10% Decrease",
        0: "Flat",
        1: "Mid-60% Increase",
    }[sign]


def _product(period_id: str, index: int, *, revenue_delta_million: int = 0):
    year = int(period_id[:4])
    quarter = int(period_id[-1])
    dram = 100 + index * 13
    nand = 70 + index * 9 + (index % 2) * 3
    other = 3 + index * 2 + (index % 3)
    total = dram + nand + other + revenue_delta_million
    return SimpleNamespace(
        evidence_id=f"{index + 1:064x}",
        period_end=date(year, quarter * 3, 28),
        metrics=SimpleNamespace(
            dram_total=float(dram),
            nand_and_solutions=float(nand),
            other_products_services=float(other),
            reported_company_revenue=float(total),
        ),
    )


def _company_observation(period_id: str, index: int, *, revenue_delta_krw: int = 0):
    product = _product(period_id, index)
    revenue_krw = int(product.metrics.reported_company_revenue * 1_000_000) + revenue_delta_krw
    return SimpleNamespace(
        period_id=period_id,
        revenue_krw=revenue_krw,
        gross_profit_krw=int(revenue_krw * 0.4),
    )


def _cycle(period_id: str, signs: tuple[int, int, int, int]):
    dram_asp, dram_bit, nand_asp, nand_bit = signs
    return SimpleNamespace(
        period_id=period_id,
        dram_asp_usd_qoq_text=_text(dram_asp),
        dram_bit_sales_volume_qoq_text=_text(dram_bit),
        nand_asp_usd_qoq_text=_text(nand_asp),
        nand_bit_sales_volume_qoq_text=_text(nand_bit),
    )


def _sources(
    periods: tuple[str, ...],
    signs: tuple[tuple[int, int, int, int], ...],
    *,
    mismatch_period: str | None = None,
):
    products = {
        period: _product(period, index)
        for index, period in enumerate(periods)
    }
    companies = tuple(
        _company_observation(
            period,
            index,
            revenue_delta_krw=(2_000_000 if period == mismatch_period else 0),
        )
        for index, period in enumerate(periods)
    )
    cycles = tuple(_cycle(period, signs[index]) for index, period in enumerate(periods))
    historical = SimpleNamespace(
        ticker="000660",
        evaluation_date=date(2026, 8, 16),
        evidence_id="a" * 64,
    )
    company = SimpleNamespace(
        ticker="000660",
        evaluation_date=date(2026, 8, 16),
        evidence_id="b" * 64,
        observations=companies,
    )
    cycle = SimpleNamespace(
        ticker="000660",
        observed_date=date(2026, 8, 16),
        evidence_id="c" * 64,
        numeric_driver_values_available=False,
        observations=cycles,
    )
    return historical, company, cycle, products


def test_direction_encoder_preserves_source_magnitude_and_only_maps_direction() -> None:
    increase = encode_direction_sign("Mid-60% Increase")
    decrease = encode_direction_sign("Around 10% Decrease")
    slight = encode_direction_sign("Slight Decrease")
    over = encode_direction_sign("Over 70% Increase")
    flat = encode_direction_sign("Flat")
    assert (increase.source_text, increase.code) == ("Mid-60% Increase", 1.0)
    assert decrease.code == -1.0
    assert slight.code == -1.0
    assert over.code == 1.0
    assert flat.code == 0.0
    assert increase.derived_numeric_source_fact is False
    assert increase.numeric_magnitude_assumed is False
    assert increase.estimation_input_ready is False
    with pytest.raises(ValueError, match="Unsupported issuer"):
        encode_direction_sign("Maybe higher")


def test_method_manifest_binds_exact_seven_parameter_rank_probe_and_keeps_fit_closed() -> None:
    method = load_structural_profitability_method()
    assert method.parameter_count == 7
    assert method.parameters == (
        "dram_margin_intercept",
        "dram_asp_direction_sensitivity",
        "dram_bit_volume_direction_sensitivity",
        "nand_margin_intercept",
        "nand_asp_direction_sensitivity",
        "nand_bit_volume_direction_sensitivity",
        "other_margin_constant",
    )
    assert method.holdout_period == "2026Q1"
    assert method.driver_encoding.numeric_magnitude_assumed is False
    assert method.driver_encoding.estimation_input_ready is False
    assert method.fit_enabled is False
    assert method.method_version_frozen is False


def test_zero_aligned_rows_returns_rank_zero_instead_of_crashing() -> None:
    method = load_structural_profitability_method()
    historical, company, cycle, _products = _sources((), ())
    result = build_structural_rank_probe(
        method,
        historical,
        company,
        cycle,
        {},
        evaluation_date=date(2026, 8, 16),
    )
    assert result.row_count == 0
    assert result.design_rank == 0
    assert result.full_column_rank is False
    assert result.normalized_condition_number is None
    assert result.rank_probe_ready is False
    assert result.fit_attempt_allowed is False
    assert result.block_reason == "insufficient_aligned_training_rows"


def test_six_rows_remain_insufficient_even_if_each_row_reconciles() -> None:
    method = load_structural_profitability_method()
    periods = _PERIODS[:6]
    historical, company, cycle, products = _sources(periods, _FULL_RANK_SIGNS[:6])
    result = build_structural_rank_probe(
        method,
        historical,
        company,
        cycle,
        products,
        evaluation_date=date(2026, 8, 16),
    )
    assert result.row_count == 6
    assert result.company_product_revenue_reconciliation_certified is True
    assert result.full_column_rank is False
    assert result.rank_probe_ready is False
    assert result.block_reason == "insufficient_aligned_training_rows"


def test_seven_independent_rows_can_pass_rank_probe_but_never_open_estimation() -> None:
    method = load_structural_profitability_method()
    periods = _PERIODS[:7]
    historical, company, cycle, products = _sources(periods, _FULL_RANK_SIGNS)
    result = build_structural_rank_probe(
        method,
        historical,
        company,
        cycle,
        products,
        evaluation_date=date(2026, 8, 16),
    )
    assert result.row_count == 7
    assert result.parameter_count == 7
    assert result.design_rank == 7
    assert result.full_column_rank is True
    assert result.normalized_condition_number is not None
    assert result.company_product_revenue_reconciliation_certified is True
    assert result.rank_probe_ready is True
    assert result.fit_attempt_allowed is False
    assert result.holdout_evaluation_allowed is False
    assert result.block_reason == "direction_only_rank_probe_not_estimation_method"
    assert result.numeric_magnitude_assumed is False
    assert result.numeric_forecast_enabled is False
    assert result.decision_score_enabled is False


def test_nine_rows_with_constant_driver_directions_remain_rank_deficient() -> None:
    method = load_structural_profitability_method()
    signs = tuple((1, 1, -1, -1) for _ in _PERIODS)
    historical, company, cycle, products = _sources(_PERIODS, signs)
    result = build_structural_rank_probe(
        method,
        historical,
        company,
        cycle,
        products,
        evaluation_date=date(2026, 8, 16),
    )
    assert result.row_count == 9
    assert result.design_rank < 7
    assert result.full_column_rank is False
    assert result.rank_probe_ready is False
    assert result.block_reason == "design_not_full_column_rank"


def test_revenue_mismatch_over_one_million_krw_fails_closed_and_excludes_row() -> None:
    method = load_structural_profitability_method()
    periods = _PERIODS[:7]
    mismatch = periods[2]
    historical, company, cycle, products = _sources(
        periods,
        _FULL_RANK_SIGNS,
        mismatch_period=mismatch,
    )
    result = build_structural_rank_probe(
        method,
        historical,
        company,
        cycle,
        products,
        evaluation_date=date(2026, 8, 16),
    )
    assert result.reconciliation_failed_periods == (mismatch,)
    assert mismatch not in result.training_periods
    assert result.company_product_revenue_reconciliation_certified is False
    assert result.rank_probe_ready is False
    assert result.fit_attempt_allowed is False
    assert result.block_reason == "company_product_revenue_reconciliation_failed"


def test_q1_2026_is_detected_as_candidate_but_never_enters_training_matrix() -> None:
    method = load_structural_profitability_method()
    periods = (*_PERIODS[:7], "2026Q1")
    signs = (*_FULL_RANK_SIGNS, (0, 1, -1, 1))
    historical, company, cycle, products = _sources(periods, signs)
    result = build_structural_rank_probe(
        method,
        historical,
        company,
        cycle,
        products,
        evaluation_date=date(2026, 8, 16),
    )
    assert "2026Q1" in result.candidate_aligned_periods
    assert result.holdout_excluded_periods == ("2026Q1",)
    assert "2026Q1" not in result.training_periods
    assert all(row.period_id != "2026Q1" for row in result.rows)
