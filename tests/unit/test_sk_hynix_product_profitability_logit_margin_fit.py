from __future__ import annotations

import math
from datetime import date

from alpha_cycle.intelligence.sk_hynix_product_profitability_logit_margin_fit import (
    LogitMarginTrainingRow,
    build_logit_margin_fit,
)
from alpha_cycle.intelligence.sk_hynix_product_profitability_logit_margin_method import (
    load_frozen_logit_margin_method,
)


def _sigmoid(value: float) -> float:
    return 1.0 / (1.0 + math.exp(-value))


def _synthetic_rows() -> tuple[LogitMarginTrainingRow, ...]:
    method = load_frozen_logit_margin_method()
    theta = (0.2, 0.35, -0.2, -0.4, 0.45, 0.25, -1.0)
    codes = (-1.0, 0.0, 1.0)
    rows: list[LogitMarginTrainingRow] = []
    for index, period_id in enumerate(method.training_periods):
        da = codes[index % 3]
        db = codes[(index // 3) % 3]
        na = codes[(index * 2 + index // 4) % 3]
        nb = codes[(index * 2 + index // 2 + 1) % 3]
        dram = 4_000.0 + 173.0 * index + 37.0 * (index % 4)
        nand = 2_600.0 + 131.0 * index + 29.0 * (index % 5)
        other = 500.0 + 41.0 * index + 17.0 * (index % 3)
        md = _sigmoid(theta[0] + theta[1] * da + theta[2] * db)
        mn = _sigmoid(theta[3] + theta[4] * na + theta[5] * nb)
        mo = _sigmoid(theta[6])
        gross_profit = dram * md + nand * mn + other * mo
        revenue = dram + nand + other
        rows.append(
            LogitMarginTrainingRow(
                period_id=period_id,
                source_group=(
                    "spent_v1_holdout_development"
                    if period_id == "2026Q1"
                    else "v1_training_reuse"
                ),
                company_revenue_krw_million=revenue,
                company_gross_profit_krw_million=gross_profit,
                dram_revenue_krw_million=dram,
                nand_revenue_krw_million=nand,
                other_revenue_krw_million=other,
                dram_asp_direction_code=da,
                dram_bit_volume_direction_code=db,
                nand_asp_direction_code=na,
                nand_bit_volume_direction_code=nb,
            )
        )
    return tuple(rows)


def test_v2_fit_is_bounded_and_does_not_open_future_holdout() -> None:
    method = load_frozen_logit_margin_method()
    result = build_logit_margin_fit(
        method,
        _synthetic_rows(),
        evaluation_date=date(2026, 8, 18),
    )

    assert result.row_count == 16
    assert result.parameter_count == 7
    assert result.residual_degrees_of_freedom == 9
    assert result.optimizer_converged is True
    assert result.full_jacobian_column_rank is True
    assert result.all_loocv_folds_converged is True
    assert result.all_loocv_jacobians_full_rank is True
    assert result.loocv_beats_benchmark is True
    assert result.dram_margin_envelope.all_regimes_inside_unit_interval is True
    assert result.nand_margin_envelope.all_regimes_inside_unit_interval is True
    assert 0.0 < result.other_margin < 1.0
    assert result.all_component_margins_inside_unit_interval is True
    assert result.development_gate_passed is True
    assert result.untouched_holdout_period == "2026Q3"
    assert result.future_holdout_evaluation_allowed is False
    assert result.q1_claimed_as_independent_holdout is False
    assert result.q2_claimed_as_untouched_holdout is False
    assert result.numeric_forward_forecast_enabled is False
    assert result.target_price_enabled is False
