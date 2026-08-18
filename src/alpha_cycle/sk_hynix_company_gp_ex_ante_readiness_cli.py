from __future__ import annotations

import argparse
import json
from collections import Counter
from collections.abc import Sequence
from dataclasses import asdict
from pathlib import Path

from .intelligence.sk_hynix_company_gp_empirical_v5_q3_holdout import (
    DEFAULT_V5_Q3_HOLDOUT_BINDING,
    load_v5_q3_validation_binding,
)
from .intelligence.sk_hynix_company_gp_ex_ante_capture import (
    DEFAULT_EX_ANTE_CAPTURE_OUTPUT,
    load_prospective_capture_ledger,
)
from .intelligence.sk_hynix_company_gp_ex_ante_feature_frontier import (
    DEFAULT_COMPANY_GP_EX_ANTE_FEATURE_FRONTIER,
    load_ex_ante_feature_frontier,
)
from .intelligence.sk_hynix_company_gp_ex_ante_pit import (
    audit_point_in_time_feature_bundle,
    load_point_in_time_feature_bundle,
)
from .intelligence.sk_hynix_company_gp_ex_ante_protocol import (
    DEFAULT_COMPANY_GP_EX_ANTE_PROTOCOL,
    load_frozen_company_gp_ex_ante_protocol,
)

DEFAULT_EX_ANTE_READINESS_OUTPUT = Path(
    "data/private/research/skhynix-company-gp-ex-ante-pit/"
    "latest_ex_ante_foundation_readiness.json"
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Audit the frozen SK hynix ex-ante company-GP forecasting foundation without "
            "reading 2026Q3/Q4 targets or fitting an estimator."
        )
    )
    parser.add_argument("--protocol", default=str(DEFAULT_COMPANY_GP_EX_ANTE_PROTOCOL))
    parser.add_argument(
        "--feature-frontier",
        default=str(DEFAULT_COMPANY_GP_EX_ANTE_FEATURE_FRONTIER),
    )
    parser.add_argument(
        "--q3-binding",
        default=str(DEFAULT_V5_Q3_HOLDOUT_BINDING),
    )
    parser.add_argument(
        "--capture-output",
        default=str(DEFAULT_EX_ANTE_CAPTURE_OUTPUT),
    )
    parser.add_argument("--feature-bundle", default=None)
    parser.add_argument("--output", default=str(DEFAULT_EX_ANTE_READINESS_OUTPUT))
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

    q3_binding_path = Path(args.q3_binding)
    q3_binding_verified = False
    q3_binding_evidence_id: str | None = None
    if q3_binding_path.exists():
        binding = load_v5_q3_validation_binding(q3_binding_path)
        if binding.method_evidence_id != protocol.bound_v5_method_evidence_id:
            raise ValueError("Ex-ante readiness Q3 binding method evidence diverged")
        if binding.holdout_loaded or binding.holdout_evaluated:
            raise ValueError("Ex-ante readiness detected prior Q3 holdout exposure")
        q3_binding_verified = True
        q3_binding_evidence_id = binding.evidence_id

    ledger = load_prospective_capture_ledger(
        protocol,
        frontier,
        output_root=Path(args.capture_output),
        verify_blobs=True,
    )
    family_counts = Counter(item.family for item in frontier.features)
    prospective_eligible = sum(item.prospective_capture_eligible for item in frontier.features)
    historical_eligible_now = sum(
        item.historical_pit_fit_eligible_now for item in frontier.features
    )
    captures_before_q3_origin = sum(
        item.period_id == "2026Q3" and item.eligible_for_frozen_origin
        for item in ledger.receipts
    )

    pit_audit: dict[str, object] | None = None
    if args.feature_bundle is not None:
        bundle = load_point_in_time_feature_bundle(Path(args.feature_bundle))
        pit_audit = asdict(audit_point_in_time_feature_bundle(protocol, frontier, bundle))

    payload: dict[str, object] = {
        "schema_version": 1,
        "status": "skhynix_company_gp_ex_ante_foundation_ready_for_pit_source_certification",
        "protocol_evidence_id": protocol.evidence_id,
        "protocol_version": protocol.protocol_version,
        "feature_frontier_evidence_id": frontier.evidence_id,
        "feature_frontier_version": frontier.frontier_version,
        "development_period_count": len(protocol.development_periods),
        "contaminated_report_only_periods": protocol.contaminated_report_only_periods,
        "q3_forecast_origin": protocol.origin_for("2026Q3").isoformat(),
        "q4_fallback_forecast_origin": protocol.origin_for("2026Q4").isoformat(),
        "q3_binding_verified_if_present": q3_binding_verified,
        "q3_binding_evidence_id": q3_binding_evidence_id,
        "registered_feature_count": len(frontier.features),
        "feature_family_counts": dict(sorted(family_counts.items())),
        "historical_pit_fit_eligible_feature_count_now": historical_eligible_now,
        "prospective_capture_eligible_feature_count": prospective_eligible,
        "prospective_capture_receipt_count": len(ledger.receipts),
        "q3_eligible_prospective_capture_receipt_count": captures_before_q3_origin,
        "point_in_time_feature_audit": pit_audit,
        "first_pit_backtest_run": False,
        "final_feature_set_frozen": False,
        "estimator_frozen": False,
        "estimator_fit_allowed": False,
        "target_join_allowed": False,
        "2026q3_target_read": False,
        "2026q3_source_outcome_loaded": False,
        "2026q3_evaluated": False,
        "2026q4_target_read": False,
        "numeric_forward_forecast_enabled": False,
        "target_price_enabled": False,
        "decision_score_enabled": False,
        "investment_action_enabled": False,
        "next_actions": [
            "certify lagged immutable issuer filing receipts and publication timestamps",
            "pin exact ECOS USDKRW series identity before prospective capture",
            "pin exact KOSIS semiconductor classification before prospective capture",
            "build PIT-complete historical feature rows without joining targets",
            "freeze model-specific feature set and estimator before any prospective forecast",
        ],
    }
    output = Path(args.output)
    _write(output, payload)
    summary = dict(payload)
    summary["report_path"] = str(output.resolve())
    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True, default=str))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
