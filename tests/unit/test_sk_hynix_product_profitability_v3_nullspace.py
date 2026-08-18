from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from alpha_cycle.intelligence.sk_hynix_product_profitability_v3_nullspace_math import (
    PARAMETER_NAMES,
    build_jacobian,
    decompose_jacobian,
)
from alpha_cycle.intelligence.sk_hynix_product_profitability_v3_nullspace_report import (
    diagnose_v3_fit_report,
)


def _rows() -> list[dict[str, object]]:
    codes = (-1.0, 0.0, 1.0)
    rows: list[dict[str, object]] = []
    for index in range(21):
        dram = 5_000.0 + 173.0 * index
        nand = 2_400.0 + 97.0 * index
        other = 180.0 + 19.0 * (index % 5)
        rows.append(
            {
                "period_id": f"T{index:02d}",
                "company_revenue_krw_million": dram + nand + other,
                "company_gross_profit_krw_million": 2_000.0 + 100.0 * index,
                "dram_revenue_krw_million": dram,
                "nand_revenue_krw_million": nand,
                "other_revenue_krw_million": other,
                "dram_asp_direction_code": codes[index % 3],
                "dram_bit_volume_direction_code": codes[(index // 3) % 3],
                "nand_asp_direction_code": codes[(index * 2 + 1) % 3],
                "nand_bit_volume_direction_code": codes[(index // 2 + 1) % 3],
            }
        )
    return rows


def _matrix(rows: list[dict[str, object]]) -> np.ndarray:
    return np.asarray(
        [
            (
                float(row["company_revenue_krw_million"]),
                float(row["dram_revenue_krw_million"]),
                float(row["nand_revenue_krw_million"]),
                float(row["other_revenue_krw_million"]),
                float(row["dram_asp_direction_code"]),
                float(row["dram_bit_volume_direction_code"]),
                float(row["nand_asp_direction_code"]),
                float(row["nand_bit_volume_direction_code"]),
            )
            for row in rows
        ],
        dtype=float,
    )


def test_decomposition_reports_single_parameter_deletion_geometry() -> None:
    base = np.arange(1.0, 22.0)
    jacobian = np.column_stack(
        (
            base,
            base**2,
            np.sin(base),
            np.cos(base),
            np.sqrt(base),
            np.log1p(base),
            base + np.sin(base),
        )
    )
    result = decompose_jacobian(jacobian)

    assert result.rank == 6
    assert len(result.normalized_singular_values_report_only) == 7
    assert len(result.dominant_nullspace_direction_report_only) == 7
    assert len(result.deletion_diagnostics_report_only) == 7
    assert any(item.full_remaining_rank for item in result.deletion_diagnostics_report_only)


def test_report_recomputes_v3_fold_ranks_without_selecting_replacement(tmp_path: Path) -> None:
    rows = _rows()
    matrix = _matrix(rows)
    theta = np.asarray([0.3, 0.45, -0.1, -25.0, 0.8, -22.0, -750.0], dtype=float)
    full_rank = int(np.linalg.matrix_rank(build_jacobian(matrix, theta)))
    loocv: list[dict[str, object]] = []
    for index, row in enumerate(rows):
        fold_matrix = np.delete(matrix, index, axis=0)
        loocv.append(
            {
                "held_out_period": row["period_id"],
                "jacobian_rank": int(np.linalg.matrix_rank(build_jacobian(fold_matrix, theta))),
                "parameters_report_only": theta.tolist(),
            }
        )
    payload = {
        "schema_version": 1,
        "status": "skhynix_product_profitability_v3_expanded_logit_margin_fit_completed",
        "method_evidence_id": "b" * 64,
        "result": {
            "evidence_id": "a" * 64,
            "method_evidence_id": "b" * 64,
            "rows": rows,
            "parameters": theta.tolist(),
            "jacobian_rank": full_rank,
            "prefit_identification": {"full_direction_design_rank": True},
            "loocv": loocv,
        },
        "2026q3_loaded": False,
        "2026q3_evaluated": False,
    }
    source = tmp_path / "v3.json"
    source.write_text(json.dumps(payload), encoding="utf-8")

    result = diagnose_v3_fit_report(source)

    assert result.row_count == 21
    assert result.parameter_count == len(PARAMETER_NAMES)
    assert result.full_fit.rank == full_rank
    assert result.linear_prefit_full_rank is True
    assert result.replacement_model_selected is False
    assert result.future_holdout_loaded is False
    assert result.future_holdout_evaluated is False
