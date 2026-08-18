from __future__ import annotations

import math
from datetime import date

from alpha_cycle.intelligence.sk_hynix_product_profitability_expanded_logit_margin_fit import (
    ExpandedLogitMarginRow,
    build_expanded_logit_margin_fit,
    build_expanded_prefit_identification,
)
from alpha_cycle.intelligence.sk_hynix_product_profitability_expanded_logit_margin_method import (
    load_frozen_expanded_logit_margin_method,
)


def _sigmoid(value: float) -> float:
    return 1.0 / (1.0 + math.exp(-value))


def _row(
    period_id: str,
    index: int,
    *,
    source_group: str,
    theta: tuple[float, ...],
) -> ExpandedLogitMarginRow:
    codes = (-1.0, 0.0, 1.0)
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
    return ExpandedLogitMarginRow(
        period_id=period_id,
        source_group=source_group,
        company_revenue_krw_million=dram + nand + other,
        company_gross_profit_krw_million=gross_profit,
        dram_revenue_krw_million=dram,
        nand_revenue_krw_million=nand,
        other_revenue_krw_million=other,
        dram_asp_direction_code=da,
        dram_bit_volume_direction_code=db,
        nand_asp_direction_code=na,
        nand_bit_volume_direction_code=nb,
    )


def _synthetic_rows() -> tuple[tuple[ExpandedLogitMarginRow, ...], ExpandedLogitMarginRow]:
    method = load_frozen_expanded_logit_margin_method()
    theta = (0.2, 0.35, -0.2, -0.4, 0.45, 0.25, -1.0)
    rows = tuple(
        _row(
            period_id,
            index,
            source_group=(
                "third_wave_exact_numeric_downcast" if index < 6 else "v1_training_reuse"
            ),
            theta=theta,
        )
        for index, period_id in enumerate(method.training_periods)
    )
    stress = _row(
        "2026Q1",
        len(rows),
        source_group="spent_v1_holdout_contaminated_stress",
        theta=theta,
    )
    return rows, stress


def test_v3_prefit_requires_full_rank_after_every_single_row_deletion() -> None:
    method = load_frozen_expanded_logit_margin_method()
    rows, _stress = _synthetic_rows()
    prefit = build_expanded_prefit_identification(method, rows)

    assert prefit.row_count == 21
    assert prefit.parameter_count == 7
    assert prefit.residual_degrees_of_freedom == 14
    assert prefit.design_rank == 7
    assert prefit.full_direction_design_rank is True
    assert prefit.all_leave_one_out_direction_designs_full_rank is True
    assert set(prefit.leave_one_out_design_ranks) == {7}
    assert prefit.prefit_gate_passed is True


def test_v3_fit_uses_clean_panel_and_keeps_q1_report_only() -> None:
    method = load_frozen_expanded_logit_margin_method()
    rows, stress = _synthetic_rows()
    result = build_expanded_logit_margin_fit(
        method,
        rows,
        stress,
        evaluation_date=date(2026, 8, 18),
    )

    assert result.row_count == 21
    assert result.parameter_count == 7
    assert result.residual_degrees_of_freedom == 14
    assert result.prefit_identification.prefit_gate_passed is True
    assert result.optimizer_converged is True
    assert result.full_jacobian_column_rank is True
    assert result.all_loocv_folds_converged is True
    assert result.all_loocv_jacobians_full_rank is True
    assert result.loocv_beats_benchmark is True
    assert result.dram_margin_envelope.all_regimes_inside_unit_interval is True
    assert result.nand_margin_envelope.all_regimes_inside_unit_interval is True
    assert 0.0 < result.other_margin < 1.0
    assert result.all_component_margins_inside_unit_interval is True
    assert len(result.parameter_jackknife_report_only) == 7
    q1 = result.contaminated_q1_stress_report_only
    assert q1.period_id == "2026Q1"
    assert q1.used_for_fit is False
    assert q1.used_for_model_selection_gate is False
    assert q1.claimed_as_independent_holdout is False
    assert result.development_gate_passed is True
    assert result.future_holdout_period == "2026Q3"
    assert result.future_holdout_evaluation_allowed is False
    assert result.future_holdout_loaded is False
    assert result.future_holdout_evaluated is False
    assert result.numeric_forward_forecast_enabled is False
    assert result.target_price_enabled is False
    assert result.decision_score_enabled is False
