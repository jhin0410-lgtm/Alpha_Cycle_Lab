from __future__ import annotations

from datetime import date

import numpy as np

from alpha_cycle.intelligence.sk_hynix_company_gross_profit_empirical_regime_fit import (
    CompanyGPEmpiricalRow,
    build_company_gp_empirical_fit,
    build_empirical_prefit_identification,
)
from alpha_cycle.intelligence.sk_hynix_company_gross_profit_empirical_regime_method import (
    load_frozen_company_gp_empirical_method,
)


def _rows() -> tuple[CompanyGPEmpiricalRow, ...]:
    method = load_frozen_company_gp_empirical_method()
    codes = (-1.0, 0.0, 1.0)
    beta = np.asarray([0.35, 0.08, -0.04, 0.06, -0.03, 0.12, -0.20], dtype=float)
    rows: list[CompanyGPEmpiricalRow] = []
    for index, period_id in enumerate(method.training_periods):
        revenue = 10_000.0 + 431.0 * index
        nand = revenue * (0.20 + 0.015 * (index % 6))
        other = revenue * (0.025 + 0.004 * (index % 5))
        row = CompanyGPEmpiricalRow(
            period_id=period_id,
            source_group="synthetic_test",
            company_revenue_krw_million=revenue,
            company_gross_profit_krw_million=1.0,
            nand_revenue_krw_million=nand,
            other_revenue_krw_million=other,
            dram_asp_direction_code=codes[index % 3],
            dram_bit_volume_direction_code=codes[(index // 3) % 3],
            nand_asp_direction_code=codes[(index * 2 + index // 4) % 3],
            nand_bit_volume_direction_code=codes[(index * 2 + index // 2 + 1) % 3],
        )
        gross_profit = float(np.dot(np.asarray(row.design_terms, dtype=float), beta))
        rows.append(
            CompanyGPEmpiricalRow(
                period_id=row.period_id,
                source_group=row.source_group,
                company_revenue_krw_million=row.company_revenue_krw_million,
                company_gross_profit_krw_million=gross_profit,
                nand_revenue_krw_million=row.nand_revenue_krw_million,
                other_revenue_krw_million=row.other_revenue_krw_million,
                dram_asp_direction_code=row.dram_asp_direction_code,
                dram_bit_volume_direction_code=row.dram_bit_volume_direction_code,
                nand_asp_direction_code=row.nand_asp_direction_code,
                nand_bit_volume_direction_code=row.nand_bit_volume_direction_code,
            )
        )
    return tuple(rows)


def _stress() -> CompanyGPEmpiricalRow:
    return CompanyGPEmpiricalRow(
        period_id="2026Q1",
        source_group="spent_v1_holdout_contaminated_stress",
        company_revenue_krw_million=22_000.0,
        company_gross_profit_krw_million=8_000.0,
        nand_revenue_krw_million=5_500.0,
        other_revenue_krw_million=700.0,
        dram_asp_direction_code=1.0,
        dram_bit_volume_direction_code=0.0,
        nand_asp_direction_code=1.0,
        nand_bit_volume_direction_code=1.0,
    )


def test_v5_prefit_and_fit_are_full_rank_without_reopening_product_margin_scope() -> None:
    method = load_frozen_company_gp_empirical_method()
    rows = _rows()
    prefit = build_empirical_prefit_identification(method, rows)

    assert prefit.design_rank == 7
    assert prefit.all_leave_one_out_designs_full_rank is True
    assert prefit.prefit_gate_passed is True

    result = build_company_gp_empirical_fit(
        method,
        rows,
        _stress(),
        evaluation_date=date(2026, 8, 18),
    )

    assert result.design_rank == 7
    assert result.full_design_column_rank is True
    assert result.all_loocv_designs_full_rank is True
    assert result.loocv_beats_benchmark is True
    assert result.development_gate_passed is True
    assert result.product_margin_structural_interpretation_allowed is False
    assert result.product_margin_output_enabled is False
    assert result.contaminated_q1_stress_report_only.used_for_fit is False
    assert result.contaminated_q1_stress_report_only.used_for_model_selection_gate is False
    assert result.future_holdout_period == "2026Q3"
    assert result.future_holdout_evaluation_allowed is False
    assert result.numeric_forward_forecast_enabled is False
    assert result.target_price_enabled is False
    assert result.decision_score_enabled is False
