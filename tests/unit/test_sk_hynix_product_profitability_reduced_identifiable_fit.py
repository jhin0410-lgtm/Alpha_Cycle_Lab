from __future__ import annotations

import math
from datetime import date

from alpha_cycle.intelligence.sk_hynix_product_profitability_expanded_logit_margin_fit import (
    ExpandedLogitMarginRow,
)
from alpha_cycle.intelligence.sk_hynix_product_profitability_reduced_identifiable_fit import (
    build_reduced_identifiable_fit,
    build_reduced_prefit_identification,
)
from alpha_cycle.intelligence.sk_hynix_product_profitability_reduced_identifiable_method import (
    load_frozen_reduced_identifiable_method,
)


def _sigmoid(value: float) -> float:
    return 1.0 / (1.0 + math.exp(-value))


def _synthetic_rows() -> tuple[tuple[ExpandedLogitMarginRow, ...], ExpandedLogitMarginRow]:
    method = load_frozen_reduced_identifiable_method()
    theta = (0.15, 0.30, -0.18, -0.55, 0.35)
    codes = (-1.0, 0.0, 1.0)
    rows: list[ExpandedLogitMarginRow] = []
    for index, period_id in enumerate(method.training_periods):
        da = codes[index % 3]
        db = codes[(index // 3) % 3]
        na = codes[(index * 2 + index // 4) % 3]
        nb = codes[(index + 1) % 3]
        dram = 4_200.0 + 191.0 * index + 31.0 * (index % 4)
        nand = 2_500.0 + 137.0 * index + 23.0 * (index % 5)
        other = 450.0 + 37.0 * index + 11.0 * (index % 3)
        dram_margin = _sigmoid(theta[0] + theta[1] * da + theta[2] * db)
        nand_margin = _sigmoid(theta[3] + theta[4] * na)
        gross_profit = dram * dram_margin + nand * nand_margin
        revenue = dram + nand + other
        rows.append(
            ExpandedLogitMarginRow(
                period_id=period_id,
                source_group=(
                    "third_wave_exact_numeric_downcast"
                    if period_id.startswith(("2017", "2018"))
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
    stress_dram = 8_000.0
    stress_nand = 4_000.0
    stress_other = 700.0
    stress_da = 1.0
    stress_db = 0.0
    stress_na = -1.0
    stress_gp = stress_dram * _sigmoid(theta[0] + theta[1] * stress_da) + stress_nand * _sigmoid(
        theta[3] + theta[4] * stress_na
    )
    stress = ExpandedLogitMarginRow(
        period_id="2026Q1",
        source_group="spent_v1_holdout_contaminated_stress",
        company_revenue_krw_million=stress_dram + stress_nand + stress_other,
        company_gross_profit_krw_million=stress_gp,
        dram_revenue_krw_million=stress_dram,
        nand_revenue_krw_million=stress_nand,
        other_revenue_krw_million=stress_other,
        dram_asp_direction_code=stress_da,
        dram_bit_volume_direction_code=stress_db,
        nand_asp_direction_code=stress_na,
        nand_bit_volume_direction_code=1.0,
    )
    return tuple(rows), stress


def test_v4_reduced_prefit_and_fit_are_full_rank_without_opening_q3() -> None:
    method = load_frozen_reduced_identifiable_method()
    rows, stress = _synthetic_rows()
    prefit = build_reduced_prefit_identification(method, rows)

    assert prefit.row_count == 21
    assert prefit.parameter_count == 5
    assert prefit.residual_degrees_of_freedom == 16
    assert prefit.design_rank == 5
    assert prefit.all_leave_one_out_reduced_direction_designs_full_rank is True
    assert prefit.prefit_gate_passed is True

    result = build_reduced_identifiable_fit(
        method,
        rows,
        stress,
        evaluation_date=date(2026, 8, 18),
    )

    assert result.optimizer_converged is True
    assert result.jacobian_rank == 5
    assert result.full_jacobian_column_rank is True
    assert result.all_loocv_folds_converged is True
    assert result.all_loocv_jacobians_full_rank is True
    assert result.loocv_beats_benchmark is True
    assert result.dram_margin_envelope.all_regimes_inside_unit_interval is True
    assert result.nand_margin_envelope.all_regimes_inside_unit_interval is True
    assert result.all_modeled_component_margins_inside_unit_interval is True
    assert result.development_gate_passed is True
    assert result.other_margin_claimed_zero is False
    assert result.other_contribution_role == "unmodeled_company_gross_profit_residual"
    assert result.contaminated_q1_stress_report_only.used_for_fit is False
    assert result.contaminated_q1_stress_report_only.used_for_model_selection_gate is False
    assert result.future_holdout_period == "2026Q3"
    assert result.future_holdout_evaluation_allowed is False
    assert result.future_holdout_loaded is False
    assert result.future_holdout_evaluated is False
    assert result.numeric_forward_forecast_enabled is False
    assert result.target_price_enabled is False
    assert result.decision_score_enabled is False
