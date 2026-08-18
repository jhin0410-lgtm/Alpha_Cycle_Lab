from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from dataclasses import asdict
from pathlib import Path

from .intelligence.sk_hynix_company_gp_empirical_v5_q3_holdout import (
    DEFAULT_V5_Q3_HOLDOUT_BINDING,
    DEFAULT_V5_Q3_HOLDOUT_RESULT,
    load_v5_q3_certified_source_bundle,
    load_v5_q3_validation_binding,
    score_v5_q3_holdout_once,
)
from .intelligence.sk_hynix_company_gp_empirical_v5_q3_holdout_protocol import (
    DEFAULT_V5_Q3_HOLDOUT_PROTOCOL,
    load_frozen_v5_q3_holdout_protocol,
)
from .intelligence.sk_hynix_company_gross_profit_empirical_regime_method import (
    DEFAULT_COMPANY_GP_EMPIRICAL_METHOD,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Spend the frozen SK hynix V5 2026Q3 holdout exactly once from an "
            "explicit certified source bundle. This CLI performs no network acquisition."
        )
    )
    parser.add_argument("--source-bundle", required=True)
    parser.add_argument("--protocol", default=str(DEFAULT_V5_Q3_HOLDOUT_PROTOCOL))
    parser.add_argument("--method", default=str(DEFAULT_COMPANY_GP_EMPIRICAL_METHOD))
    parser.add_argument("--binding", default=str(DEFAULT_V5_Q3_HOLDOUT_BINDING))
    parser.add_argument("--output", default=str(DEFAULT_V5_Q3_HOLDOUT_RESULT))
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    protocol, method = load_frozen_v5_q3_holdout_protocol(
        Path(args.protocol),
        method_path=Path(args.method),
    )
    binding = load_v5_q3_validation_binding(Path(args.binding))
    if binding.method_evidence_id != method.evidence_id:
        raise ValueError(
            "V5 Q3 scorer binding does not match current frozen V5 method"
        )
    source = load_v5_q3_certified_source_bundle(Path(args.source_bundle))
    result, reused_existing = score_v5_q3_holdout_once(
        protocol,
        binding,
        source,
        output=Path(args.output),
    )
    summary = {
        "status": "skhynix_v5_q3_holdout_scored_or_reused",
        "protocol_version": protocol.protocol_version,
        "protocol_evidence_id": protocol.evidence_id,
        "method_evidence_id": method.evidence_id,
        "fit_evidence_id": binding.fit_evidence_id,
        "source_bundle_evidence_id": source.evidence_id,
        "holdout_period": result.holdout_period,
        "reused_existing_immutable_result": reused_existing,
        "company_revenue_reconciled": result.company_revenue_reconciled,
        "actual_gross_profit_krw_million": (
            result.actual_gross_profit_krw_million
        ),
        "model_prediction_krw_million": result.model_prediction_krw_million,
        "model_absolute_error_krw_million": (
            result.model_absolute_error_krw_million
        ),
        "benchmark_prediction_krw_million": (
            result.benchmark_prediction_krw_million
        ),
        "benchmark_absolute_error_krw_million": (
            result.benchmark_absolute_error_krw_million
        ),
        "model_beats_benchmark": result.model_beats_benchmark,
        "holdout_validation_passed": result.holdout_validation_passed,
        "validation_scope": result.validation_scope,
        "validates_pre_earnings_forecastability": False,
        "product_margin_structural_interpretation_allowed": False,
        "numeric_forward_forecast_enabled": False,
        "fair_value_estimate_enabled": False,
        "target_price_enabled": False,
        "decision_score_enabled": False,
        "investment_action_enabled": False,
        "result": asdict(result),
        "result_path": str(Path(args.output).resolve()),
    }
    print(
        json.dumps(
            summary,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
            default=str,
        )
    )
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
