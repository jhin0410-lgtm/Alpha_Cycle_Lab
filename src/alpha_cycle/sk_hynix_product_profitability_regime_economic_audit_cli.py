from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from dataclasses import asdict
from pathlib import Path

from .intelligence.sk_hynix_product_profitability_regime_economic_audit import (
    DEFAULT_REGIME_ECONOMIC_AUDIT_OUTPUT,
    DEFAULT_REGIME_TRAINING_FIT_POINTER,
    load_and_build_regime_economic_audit,
)
from .intelligence.sk_hynix_product_profitability_regime_estimation_method import (
    DEFAULT_REGIME_ESTIMATION_METHOD,
)
from .intelligence.sk_hynix_product_profitability_regime_holdout import (
    DEFAULT_REGIME_HOLDOUT_POINTER,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Audit the already-spent SK hynix v1 holdout model for accounting-hard-bound "
            "violations before any coefficient is interpreted as literal product margin."
        )
    )
    parser.add_argument("--method", default=str(DEFAULT_REGIME_ESTIMATION_METHOD))
    parser.add_argument("--training-fit", default=str(DEFAULT_REGIME_TRAINING_FIT_POINTER))
    parser.add_argument("--holdout", default=str(DEFAULT_REGIME_HOLDOUT_POINTER))
    parser.add_argument("--output", default=str(DEFAULT_REGIME_ECONOMIC_AUDIT_OUTPUT))
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    result = load_and_build_regime_economic_audit(
        method_path=Path(args.method),
        training_fit_pointer=Path(args.training_fit),
        holdout_pointer=Path(args.holdout),
    )
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": 1,
        "status": "skhynix_product_profitability_regime_v1_economic_audit_completed",
        "result": asdict(result),
        "refit_v1_after_holdout_allowed": False,
        "numeric_forecast_enabled": False,
        "target_price_enabled": False,
        "decision_score_enabled": False,
    }
    temporary = output.with_name(f".{output.name}.tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    temporary.replace(output)
    summary = {
        "status": payload["status"],
        "evidence_id": result.evidence_id,
        "holdout_validation_passed": result.holdout_validation_passed,
        "predictive_validation_retained": result.predictive_validation_retained,
        "dram_implied_ratio_range": [
            result.dram.minimum_implied_contribution_ratio,
            result.dram.maximum_implied_contribution_ratio,
        ],
        "dram_hard_bound_violating_regimes": result.dram.violating_regimes,
        "nand_implied_ratio_range": [
            result.nand.minimum_implied_contribution_ratio,
            result.nand.maximum_implied_contribution_ratio,
        ],
        "nand_hard_bound_violating_regimes": result.nand.violating_regimes,
        "other_margin_constant": result.other_margin_constant,
        "any_product_revenue_hard_bound_violation": (
            result.any_product_revenue_hard_bound_violation
        ),
        "structural_product_margin_interpretation_allowed": (
            result.structural_product_margin_interpretation_allowed
        ),
        "forward_structural_forecast_allowed": result.forward_structural_forecast_allowed,
        "v1_scope": result.v1_scope,
        "next_action": result.next_action,
        "report_path": str(output.resolve()),
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
