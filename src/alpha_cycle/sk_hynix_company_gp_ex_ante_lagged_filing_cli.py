from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from dataclasses import asdict
from datetime import date
from pathlib import Path

from .intelligence.sk_hynix_company_gp_ex_ante_feature_frontier import (
    DEFAULT_COMPANY_GP_EX_ANTE_FEATURE_FRONTIER,
    load_ex_ante_feature_frontier,
)
from .intelligence.sk_hynix_company_gp_ex_ante_lagged_filing import (
    DEFAULT_LAGGED_FILING_BUNDLE,
    DEFAULT_LAGGED_FILING_CERTIFICATION,
    DEFAULT_LAGGED_FILING_REPORT,
    build_lagged_filing_source_records,
    certify_lagged_filing_records,
    load_lagged_filing_certification_contract,
    persist_locked_pit_feature_bundle,
)
from .intelligence.sk_hynix_company_gp_ex_ante_protocol import (
    DEFAULT_COMPANY_GP_EX_ANTE_PROTOCOL,
    load_frozen_company_gp_ex_ante_protocol,
)
from .intelligence.sk_hynix_opendart_historical_product_revenue_panel import (
    DEFAULT_HISTORICAL_PRODUCT_REVENUE_POINTER,
)
from .intelligence.sk_hynix_opendart_quarterly_company_profitability import (
    DEFAULT_QUARTERLY_COMPANY_PROFITABILITY_POINTER,
)
from .intelligence.sk_hynix_product_profitability_second_wave_acquisition import (
    DEFAULT_SECOND_WAVE_COMPANY_OUTPUT,
    DEFAULT_SECOND_WAVE_PRODUCT_OUTPUT,
)
from .intelligence.sk_hynix_product_profitability_second_wave_closeout import (
    run_second_wave_closeout,
)
from .intelligence.sk_hynix_product_profitability_second_wave_frontier import (
    DEFAULT_SECOND_WAVE_FRONTIER,
    load_second_wave_frontier,
)
from .intelligence.sk_hynix_product_profitability_third_wave_closeout import (
    DEFAULT_THIRD_WAVE_COMPANY_OUTPUT,
    DEFAULT_THIRD_WAVE_PRODUCT_OUTPUT,
    run_third_wave_closeout,
)
from .intelligence.sk_hynix_product_profitability_third_wave_frontier import (
    DEFAULT_THIRD_WAVE_FRONTIER,
    load_third_wave_frontier,
)
from .providers.opendart import OpenDartReadOnlyClient


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Certify 14 SK hynix Q2/Q3 ex-ante rows from lagged immutable OpenDART "
            "filing facts. Targets are not loaded and no estimator is fit."
        )
    )
    parser.add_argument("--evaluation-date", required=True, type=date.fromisoformat)
    parser.add_argument("--protocol", default=str(DEFAULT_COMPANY_GP_EX_ANTE_PROTOCOL))
    parser.add_argument(
        "--feature-frontier",
        default=str(DEFAULT_COMPANY_GP_EX_ANTE_FEATURE_FRONTIER),
    )
    parser.add_argument(
        "--certification",
        default=str(DEFAULT_LAGGED_FILING_CERTIFICATION),
    )
    parser.add_argument("--second-frontier", default=str(DEFAULT_SECOND_WAVE_FRONTIER))
    parser.add_argument("--third-frontier", default=str(DEFAULT_THIRD_WAVE_FRONTIER))
    parser.add_argument(
        "--second-product-output",
        default=str(DEFAULT_SECOND_WAVE_PRODUCT_OUTPUT),
    )
    parser.add_argument(
        "--second-company-output",
        default=str(DEFAULT_SECOND_WAVE_COMPANY_OUTPUT),
    )
    parser.add_argument(
        "--third-product-output",
        default=str(DEFAULT_THIRD_WAVE_PRODUCT_OUTPUT),
    )
    parser.add_argument(
        "--third-company-output",
        default=str(DEFAULT_THIRD_WAVE_COMPANY_OUTPUT),
    )
    parser.add_argument(
        "--modern-product-pointer",
        default=str(DEFAULT_HISTORICAL_PRODUCT_REVENUE_POINTER),
    )
    parser.add_argument(
        "--modern-company-pointer",
        default=str(DEFAULT_QUARTERLY_COMPANY_PROFITABILITY_POINTER),
    )
    parser.add_argument("--bundle-output", default=str(DEFAULT_LAGGED_FILING_BUNDLE))
    parser.add_argument("--report-output", default=str(DEFAULT_LAGGED_FILING_REPORT))
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
    protocol = load_frozen_company_gp_ex_ante_protocol(Path(args.protocol))
    frontier = load_ex_ante_feature_frontier(Path(args.feature_frontier))
    contract = load_lagged_filing_certification_contract(Path(args.certification))
    second_frontier = load_second_wave_frontier(Path(args.second_frontier))
    third_frontier = load_third_wave_frontier(Path(args.third_frontier))
    client = OpenDartReadOnlyClient.from_env()

    second_closeout = run_second_wave_closeout(
        client,
        second_frontier,
        evaluation_date=args.evaluation_date,
        product_output=Path(args.second_product_output),
        company_output=Path(args.second_company_output),
    )
    third_closeout = run_third_wave_closeout(
        client,
        third_frontier,
        evaluation_date=args.evaluation_date,
        product_output=Path(args.third_product_output),
        company_output=Path(args.third_company_output),
    )
    records = build_lagged_filing_source_records(
        contract,
        third_wave_closeout=third_closeout,
        second_wave_closeout=second_closeout,
        evaluation_date=args.evaluation_date,
        third_product_output=Path(args.third_product_output),
        third_company_output=Path(args.third_company_output),
        second_product_output=Path(args.second_product_output),
        second_company_output=Path(args.second_company_output),
        modern_product_pointer=Path(args.modern_product_pointer),
        modern_company_pointer=Path(args.modern_company_pointer),
    )
    result, bundle = certify_lagged_filing_records(
        contract,
        protocol,
        frontier,
        records,
    )
    bundle_path = persist_locked_pit_feature_bundle(bundle, Path(args.bundle_output))
    report_payload: dict[str, object] = {
        "schema_version": 1,
        "status": "skhynix_ex_ante_lagged_filing_pit_certified",
        "evaluation_date": args.evaluation_date.isoformat(),
        "protocol_evidence_id": protocol.evidence_id,
        "feature_frontier_evidence_id": frontier.evidence_id,
        "certification_contract_evidence_id": contract.evidence_id,
        "result": asdict(result),
        "bundle_path": str(bundle_path.resolve()),
        "target_values_included": False,
        "target_join_allowed": False,
        "estimator_fit_allowed": False,
        "first_pit_backtest_run": False,
        "2026q3_target_read": False,
        "2026q3_source_outcome_loaded": False,
        "numeric_forward_forecast_enabled": False,
        "target_price_enabled": False,
        "decision_score_enabled": False,
    }
    report_path = Path(args.report_output)
    _write(report_path, report_payload)

    summary: dict[str, object] = {
        "status": report_payload["status"],
        "certification_contract_evidence_id": contract.evidence_id,
        "expected_target_row_count": contract.expected_target_row_count,
        "certified_target_row_count": result.certified_target_row_count,
        "expected_feature_observation_count": (
            contract.expected_feature_observation_count
        ),
        "feature_observation_count": result.feature_observation_count,
        "eligible_feature_observation_count": (
            result.pit_audit.eligible_observation_count
        ),
        "rejected_feature_observation_count": (
            result.pit_audit.rejected_observation_count
        ),
        "all_observations_point_in_time_eligible": (
            result.pit_audit.all_observations_point_in_time_eligible
        ),
        "certified_source_periods": [
            item.source_period for item in result.period_certifications
        ],
        "certified_target_periods": result.certified_target_periods,
        "features_per_target_row": contract.feature_ids,
        "completion_gate_passed": result.completion_gate_passed,
        "q1_target_rows_unavailable": result.q1_target_rows_unavailable,
        "bundle_evidence_id": bundle.evidence_id,
        "bundle_path": str(bundle_path.resolve()),
        "report_path": str(report_path.resolve()),
        "target_values_included": False,
        "target_join_allowed": False,
        "estimator_fit_allowed": False,
        "first_pit_backtest_run": False,
        "2026q3_target_read": False,
        "2026q3_source_outcome_loaded": False,
        "numeric_forward_forecast_enabled": False,
        "target_price_enabled": False,
        "decision_score_enabled": False,
        "next_action": (
            "freeze_low_dimensional_ex_ante_estimator_candidates_and_chronological_"
            "selection_rule_before_first_target_join_or_backtest"
        ),
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True, default=str))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
