from __future__ import annotations

from datetime import date
from types import SimpleNamespace
from typing import cast

from alpha_cycle.intelligence.sk_hynix_product_profitability_logit_margin_fit import (
    LogitMarginTrainingRow,
)
from alpha_cycle.intelligence.sk_hynix_product_profitability_third_wave_closeout import (
    ThirdWaveCloseout,
)
from alpha_cycle.intelligence.sk_hynix_product_profitability_third_wave_frontier import (
    load_third_wave_frontier,
)
from alpha_cycle.intelligence.sk_hynix_product_profitability_third_wave_identification import (
    build_third_wave_identification_preflight,
)

_BASE_PERIODS = (
    "2019Q1",
    "2019Q2",
    "2019Q3",
    "2020Q1",
    "2020Q2",
    "2020Q3",
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


def _row(
    period_id: str,
    *,
    dram: float,
    nand: float,
    other: float,
    da: float = 0.0,
    db: float = 0.0,
    na: float = 0.0,
    nb: float = 0.0,
    source_group: str = "v1_training_reuse",
) -> LogitMarginTrainingRow:
    total = dram + nand + other
    return LogitMarginTrainingRow(
        period_id=period_id,
        source_group=source_group,
        company_revenue_krw_million=total,
        company_gross_profit_krw_million=total * 0.3,
        dram_revenue_krw_million=dram,
        nand_revenue_krw_million=nand,
        other_revenue_krw_million=other,
        dram_asp_direction_code=da,
        dram_bit_volume_direction_code=db,
        nand_asp_direction_code=na,
        nand_bit_volume_direction_code=nb,
    )


def _base_rows() -> tuple[LogitMarginTrainingRow, ...]:
    basis = (
        _row(_BASE_PERIODS[0], dram=100.0, nand=0.0, other=0.0),
        _row(_BASE_PERIODS[1], dram=100.0, nand=0.0, other=0.0, da=1.0),
        _row(_BASE_PERIODS[2], dram=100.0, nand=0.0, other=0.0, db=1.0),
        _row(_BASE_PERIODS[3], dram=0.0, nand=100.0, other=0.0),
        _row(_BASE_PERIODS[4], dram=0.0, nand=100.0, other=0.0, na=1.0),
        _row(_BASE_PERIODS[5], dram=0.0, nand=100.0, other=0.0, nb=1.0),
        _row(_BASE_PERIODS[6], dram=0.0, nand=0.0, other=100.0),
    )
    remaining = tuple(
        _row(
            period_id,
            dram=60.0,
            nand=30.0,
            other=10.0,
            da=1.0 if index % 2 == 0 else -1.0,
            db=-1.0 if index % 3 == 0 else 1.0,
            na=-1.0 if index % 2 == 0 else 1.0,
            nb=1.0 if index % 3 == 0 else -1.0,
        )
        for index, period_id in enumerate(_BASE_PERIODS[7:], start=7)
    )
    q1 = _row(
        "2026Q1",
        dram=65.0,
        nand=25.0,
        other=10.0,
        da=1.0,
        db=1.0,
        na=1.0,
        nb=1.0,
        source_group="spent_v1_holdout_development",
    )
    return basis + remaining + (q1,)


def _third_wave_closeout() -> ThirdWaveCloseout:
    frontier = load_third_wave_frontier()
    periods = []
    for index, candidate in enumerate(frontier.candidates, start=1):
        receipt = f"201805{index:02d}000001"
        company = SimpleNamespace(
            rcept_no=receipt,
            revenue_krw=100_000_000,
            gross_profit_krw=30_000_000,
        )
        product = SimpleNamespace(
            rcept_no=receipt,
            dram_revenue_million_krw=60,
            nand_revenue_million_krw=30,
            other_revenue_million_krw=10,
            total_revenue_million_krw=100,
        )
        periods.append(
            SimpleNamespace(
                period_id=candidate.period_id,
                company_observation=company,
                product_recovery=SimpleNamespace(observation=product),
            )
        )
    return cast(
        ThirdWaveCloseout,
        SimpleNamespace(
            all_six_source_layers_complete=True,
            source=SimpleNamespace(periods=tuple(periods)),
        ),
    )


def test_third_wave_preflight_requires_rank_before_any_replacement_fit(tmp_path) -> None:
    frontier = load_third_wave_frontier()
    result = build_third_wave_identification_preflight(
        evaluation_date=date(2026, 8, 18),
        base_v2_rows=_base_rows(),
        closeout=_third_wave_closeout(),
        frontier=frontier,
        product_output=tmp_path,
    )

    assert result.base_historical_row_count == 15
    assert result.third_wave_row_count == 6
    assert result.clean_historical_row_count == 21
    assert result.contaminated_development_row_count == 22
    assert result.exact_numeric_third_wave_driver_count == 24
    assert result.clean_historical_panel.design_rank == 7
    assert result.clean_historical_panel.full_column_rank is True
    assert result.contaminated_development_panel.design_rank == 7
    assert result.contaminated_development_panel.full_column_rank is True
    assert result.preflight_ready_for_new_method_registration is True
    assert result.fit_attempt_allowed is False
    assert result.spent_2026q1_reused_as_unseen_holdout is False
    assert result.future_holdout_period == "2026Q3"
    assert result.future_holdout_loaded is False
    assert result.future_holdout_evaluated is False
    assert "replacement_estimator_not_yet_preregistered" in result.block_reasons
