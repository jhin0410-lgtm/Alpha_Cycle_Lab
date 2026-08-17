from __future__ import annotations

from datetime import date
from types import SimpleNamespace
from typing import cast

import numpy as np
import pytest

from alpha_cycle.intelligence import (
    sk_hynix_product_profitability_regime_training_fit as fit_module,
)
from alpha_cycle.intelligence.sk_hynix_product_profitability_regime_estimation_method import (
    load_frozen_regime_estimation_method,
)
from alpha_cycle.intelligence.sk_hynix_product_profitability_regime_training_fit import (
    RegimeTrainingRow,
    build_regime_training_fit,
)
from alpha_cycle.intelligence.sk_hynix_product_profitability_second_wave_closeout import (
    SecondWaveCloseout,
)
from alpha_cycle.intelligence.sk_hynix_product_profitability_second_wave_frontier import (
    load_second_wave_frontier,
)
from alpha_cycle.intelligence.sk_hynix_product_profitability_structural_method import (
    StructuralRankProbeResult,
)


def _synthetic_rows() -> tuple[RegimeTrainingRow, ...]:
    method = load_frozen_regime_estimation_method()
    rng = np.random.default_rng(41)
    matrix = rng.normal(size=(15, 7))
    beta = np.asarray([500.0, 75.0, -40.0, 350.0, 60.0, -30.0, 120.0])
    target = matrix @ beta
    rows: list[RegimeTrainingRow] = []
    for index, period_id in enumerate(method.training_periods):
        rows.append(
            RegimeTrainingRow(
                period_id=period_id,
                source_group=(
                    "second_wave_numeric_downcast" if index < 6 else "legacy_text_direction"
                ),
                product_revenue_evidence_id=(f"{index + 1:064x}"[-64:]),
                company_revenue_krw_million=10_000.0 + index * 100.0,
                company_gross_profit_krw_million=float(target[index]),
                dram_revenue_krw_million=4_000.0,
                nand_revenue_krw_million=3_000.0,
                other_revenue_krw_million=3_000.0,
                dram_asp_direction_code=1.0,
                dram_bit_volume_direction_code=-1.0,
                nand_asp_direction_code=1.0,
                nand_bit_volume_direction_code=-1.0,
                design_terms=tuple(float(value) for value in matrix[index]),
                company_product_revenue_reconciled=True,
            )
        )
    return tuple(rows)


def test_frozen_training_gate_can_open_holdout_only_after_loocv_pass(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    method = load_frozen_regime_estimation_method()
    frontier = load_second_wave_frontier()
    rows = _synthetic_rows()
    monkeypatch.setattr(fit_module, "_build_rows", lambda *_args: rows)
    base = cast(
        StructuralRankProbeResult,
        SimpleNamespace(method_version="0.1-draft", evidence_id="a" * 64),
    )
    closeout = cast(SecondWaveCloseout, object())

    result = build_regime_training_fit(
        method,
        base,
        closeout,
        frontier,
        evaluation_date=date(2026, 8, 17),
    )

    assert result.row_count == 15
    assert result.parameter_count == 7
    assert result.residual_degrees_of_freedom == 8
    assert result.full_column_rank is True
    assert result.all_loocv_folds_full_rank is True
    assert result.loocv_beats_benchmark is True
    assert result.training_gate_passed is True
    assert result.one_time_holdout_evaluation_ready is True
    assert result.holdout_loaded is False
    assert result.holdout_evaluated is False
