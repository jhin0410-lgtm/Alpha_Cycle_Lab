"""Decision-facing Expectation Gap v1 readiness.

Market expectation levels/revisions and the internal operating view are certified
independently. Current KIS estimate-perform semantics remain blocked. The internal
side now reads explicit issuer/block forward-input coverage before falling back to
historical transmission diagnostics; historical correlations are never forecasts.
"""

from __future__ import annotations

import json
from dataclasses import dataclass

import pandas as pd

from alpha_cycle.intelligence.expectation_gap_contract import (
    ExpectationReadiness,
    ExpectationSemantics,
    evaluate_expectation_readiness,
)

KIS_PROVIDER_ID = "kis_estimate_perform_raw_unclassified"


@dataclass(frozen=True)
class ExpectationGapDecisionEvidence:
    rows: pd.DataFrame
    provider_id: str = KIS_PROVIDER_ID
    decision_score_enabled: bool = False
    expectation_gap_enabled: bool = False

    def __post_init__(self) -> None:
        if self.rows.empty:
            raise ValueError("Expectation gap decision evidence cannot be empty")
        if self.decision_score_enabled or self.expectation_gap_enabled:
            raise ValueError("Expectation Gap v1 must remain readiness-only")


def _bool(value: object) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().casefold() in {"1", "true", "yes"}


def kis_expectation_semantics(
    *,
    raw_artifact_available: bool,
    prior_snapshot_available: bool,
) -> ExpectationSemantics:
    """Describe the current certified boundary of KIS estimate-perform."""

    return ExpectationSemantics(
        provider_id=KIS_PROVIDER_ID,
        provider_semantics_certified=False,
        target_period_semantics_certified=False,
        metric_semantics_certified=False,
        aggregation_semantics_certified=False,
        observation_timestamp_certified=raw_artifact_available,
        provider_vintage_certified=False,
        comparable_prior_snapshot_available=prior_snapshot_available,
        comparable_snapshot_scope_certified=False,
        revision_calculation_certified=False,
        numeric_evidence_available=False,
        source_scope=(
            "KIS estimate-perform raw structure; forward period/consensus "
            "semantics uncertified"
        ),
    )


def _internal_forward_status(row: dict[str, object]) -> tuple[str, tuple[str, ...]]:
    if _bool(row.get("semiconductor_forward_internal_forward_model_certified")):
        return "certified_forward_operating_view", ()
    if _bool(row.get("semiconductor_forward_all_numeric_inputs_covered")):
        return (
            "numeric_inputs_complete_model_certification_pending",
            (
                "output_method_not_certified",
                "company_reconciliation_not_certified",
                "model_version_not_frozen",
            ),
        )
    if _bool(row.get("semiconductor_forward_all_descriptive_inputs_covered")):
        return (
            "descriptive_forward_inputs_only",
            (
                "numeric_forward_drivers_incomplete",
                "output_method_not_certified",
                "company_reconciliation_not_certified",
                "model_version_not_frozen",
            ),
        )
    if "semiconductor_forward_required_block_count" in row:
        return (
            "forward_input_coverage_incomplete",
            (
                "issuer_block_baseline_or_driver_coverage_incomplete",
                "numeric_forward_drivers_incomplete",
                "internal_forward_model_not_certified",
            ),
        )
    if _bool(row.get("semiconductor_transmission_history_ready")):
        return (
            "historical_transmission_only_not_forward_model",
            (
                "forward_operating_assumptions_missing",
                "memory_price_and_hbm_forward_inputs_missing",
                "historical_transmission_not_a_forecast",
            ),
        )
    return (
        "internal_forward_view_missing",
        (
            "forward_operating_model_missing",
            "certified_forward_industry_inputs_missing",
        ),
    )


def build_expectation_gap_decision_evidence(
    scorecards: pd.DataFrame,
) -> ExpectationGapDecisionEvidence:
    if scorecards.empty or "ticker" not in scorecards.columns:
        raise ValueError("Expectation Gap v1 requires decision scorecards with ticker")
    rows: list[dict[str, object]] = []
    for raw_value in scorecards.to_dict(orient="records"):
        row = {str(key): value for key, value in raw_value.items()}
        ticker = str(row["ticker"]).strip().zfill(6)
        raw_available = _bool(row.get("kis_forward_evidence_available"))
        prior_available = _bool(row.get("kis_estimate_snapshot_change_available")) or _bool(
            row.get("kis_estimate_snapshot_change_verified")
        )
        semantics = kis_expectation_semantics(
            raw_artifact_available=raw_available,
            prior_snapshot_available=prior_available,
        )
        readiness: ExpectationReadiness = evaluate_expectation_readiness(semantics)
        internal_status, internal_blockers = _internal_forward_status(row)
        gap_blockers = tuple(
            dict.fromkeys(
                (
                    *readiness.level_blockers,
                    *internal_blockers,
                    "certified_market_expectation_level_required",
                    "certified_internal_forward_operating_view_required",
                )
            )
        )
        rows.append(
            {
                "ticker": ticker,
                "expectation_provider_id": readiness.provider_id,
                "expectation_level_status": readiness.level_status,
                "expectation_revision_status": readiness.revision_status,
                "expectation_level_blockers_json": json.dumps(
                    list(readiness.level_blockers), ensure_ascii=False
                ),
                "expectation_revision_blockers_json": json.dumps(
                    list(readiness.revision_blockers), ensure_ascii=False
                ),
                "internal_forward_view_status": internal_status,
                "internal_forward_view_blockers_json": json.dumps(
                    list(internal_blockers), ensure_ascii=False
                ),
                "expectation_gap_status": "blocked",
                "expectation_gap_blockers_json": json.dumps(
                    list(gap_blockers), ensure_ascii=False
                ),
                "numeric_expectation_level_enabled": readiness.numeric_level_enabled,
                "numeric_expectation_revision_enabled": readiness.numeric_revision_enabled,
                "expectation_gap_enabled": False,
                "decision_score_enabled": False,
            }
        )
    frame = pd.DataFrame(rows).sort_values("ticker", kind="stable").reset_index(drop=True)
    if frame["ticker"].duplicated().any():
        raise ValueError("Expectation Gap v1 contains duplicate tickers")
    return ExpectationGapDecisionEvidence(rows=frame)


def append_expectation_gap_report(
    report: str,
    evidence: ExpectationGapDecisionEvidence,
) -> str:
    lines = [
        report.rstrip(),
        "",
        "## Expectation Gap v1 (인증상태·비점수)",
        "",
        (
            "- 시장 forward expectation의 '수준'과 'revision', 내부 forward "
            "operating view를 서로 독립적으로 인증합니다."
        ),
        (
            "- 현재 KIS raw estimate-perform는 forward 기간·metric·집계·"
            "consensus/revision semantics가 인증되지 않아 numeric evidence를 "
            "사용하지 않습니다."
        ),
        (
            "- issuer/block forward-input coverage가 있어도 output method·company "
            "reconciliation·model version이 인증되기 전에는 numeric forecast가 아닙니다."
        ),
        (
            "- 이 섹션은 composite/valuation score, fair value, target price를 "
            "변경하지 않습니다."
        ),
        "",
        "| 종목 | provider | 기대수준 | revision | 내부 forward view | expectation gap |",
        "|---|---|---|---|---|---|",
    ]
    for raw in evidence.rows.to_dict(orient="records"):
        lines.append(
            f"| {raw['ticker']} | {raw['expectation_provider_id']} | "
            f"{raw['expectation_level_status']} | {raw['expectation_revision_status']} | "
            f"{raw['internal_forward_view_status']} | {raw['expectation_gap_status']} |"
        )
        blockers = json.loads(str(raw["expectation_gap_blockers_json"]))
        lines.append("  - blockers: " + ", ".join(str(item) for item in blockers))
    return "\n".join(lines).rstrip() + "\n"


__all__ = [
    "ExpectationGapDecisionEvidence",
    "KIS_PROVIDER_ID",
    "append_expectation_gap_report",
    "build_expectation_gap_decision_evidence",
    "kis_expectation_semantics",
]
