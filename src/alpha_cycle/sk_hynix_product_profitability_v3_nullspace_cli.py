from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from dataclasses import asdict
from pathlib import Path

from .intelligence.sk_hynix_product_profitability_regime_holdout import (
    DEFAULT_REGIME_VALIDATION_OUTPUT,
)
from .intelligence.sk_hynix_product_profitability_v3_nullspace_report import (
    diagnose_v3_fit_report,
)

DEFAULT_V3_FIT_REPORT = DEFAULT_REGIME_VALIDATION_OUTPUT / "latest_v3_expanded_logit_margin_fit.json"
DEFAULT_V3_NULLSPACE_REPORT = (
    DEFAULT_REGIME_VALIDATION_OUTPUT / "latest_v3_nonlinear_nullspace_diagnostic.json"
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Decompose the already-observed SK hynix V3 nonlinear Jacobian rank loss. "
            "No replacement model is selected and 2026Q3 is never loaded or evaluated."
        )
    )
    parser.add_argument("--fit-report", default=str(DEFAULT_V3_FIT_REPORT))
    parser.add_argument("--output", default=str(DEFAULT_V3_NULLSPACE_REPORT))
    return parser


def _write(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True, default=str),
        encoding="utf-8",
    )
    temporary.replace(path)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    result = diagnose_v3_fit_report(Path(args.fit_report))
    payload = {
        "schema_version": 1,
        "status": "skhynix_product_profitability_v3_nullspace_diagnostic_completed",
        "result": asdict(result),
        "replacement_model_selected": False,
        "2026q3_reserved_as_future_untouched_holdout": True,
        "2026q3_loaded": False,
        "2026q3_evaluated": False,
        "numeric_forward_forecast_enabled": False,
        "target_price_enabled": False,
        "decision_score_enabled": False,
    }
    output = Path(args.output)
    _write(output, payload)
    full = result.full_fit
    summary = {
        "status": payload["status"],
        "source_fit_evidence_id": result.source_fit_evidence_id,
        "method_evidence_id": result.method_evidence_id,
        "method_version": result.method_version,
        "row_count": result.row_count,
        "parameter_count": result.parameter_count,
        "linear_prefit_full_rank": result.linear_prefit_full_rank,
        "recomputed_full_jacobian_rank": full.rank,
        "normalized_condition_number_report_only": (
            full.normalized_condition_number_report_only
        ),
        "normalized_singular_values_report_only": (
            full.normalized_singular_values_report_only
        ),
        "smallest_to_largest_ratio_report_only": (
            full.smallest_to_largest_ratio_report_only
        ),
        "column_l2_norms_report_only": dict(full.column_l2_norms_report_only),
        "dominant_nullspace_direction_report_only": [
            asdict(item) for item in full.dominant_nullspace_direction_report_only
        ],
        "parameter_deletion_diagnostics_report_only": [
            asdict(item) for item in full.deletion_diagnostics_report_only
        ],
        "rank_deficient_loocv_fold_count": result.loocv_rank_deficient_count,
        "rank_deficient_loocv_periods": result.rank_deficient_loocv_periods,
        "loocv_diagnostics_report_only": [
            asdict(item) for item in result.loocv_diagnostics_report_only
        ],
        "nonlinear_rank_loss_after_link_fit": result.nonlinear_rank_loss_after_link_fit,
        "replacement_model_selected": False,
        "future_holdout_period": result.future_holdout_period,
        "2026q3_loaded": False,
        "2026q3_evaluated": False,
        "numeric_forward_forecast_enabled": False,
        "target_price_enabled": False,
        "decision_score_enabled": False,
        "report_path": str(output.resolve()),
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True, default=str))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
