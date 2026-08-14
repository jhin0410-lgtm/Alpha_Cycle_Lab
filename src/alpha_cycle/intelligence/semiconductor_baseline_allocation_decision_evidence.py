"""Decision-facing verified derived-revenue baseline allocation evidence."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path

from alpha_cycle.intelligence.semiconductor_baseline_allocation_artifact import (
    DEFAULT_BASELINE_ALLOCATION_POINTER,
    AllocationSourceResolver,
    SemiconductorBaselineAllocationEvidence,
    load_semiconductor_baseline_allocation_evidence,
)


@dataclass(frozen=True)
class BaselineAllocationDecisionEvidence:
    evidence: SemiconductorBaselineAllocationEvidence
    decision_score_enabled: bool = False
    numeric_forecast_enabled: bool = False
    expectation_gap_enabled: bool = False

    def __post_init__(self) -> None:
        if (
            self.decision_score_enabled
            or self.numeric_forecast_enabled
            or self.expectation_gap_enabled
        ):
            raise ValueError("Baseline allocation decision evidence must remain non-scoring")


def load_semiconductor_baseline_allocation_decision_evidence(
    pointer_path: str | Path,
    *,
    evaluation_date: date,
    resolvers: dict[str, AllocationSourceResolver] | None = None,
) -> BaselineAllocationDecisionEvidence:
    evidence = load_semiconductor_baseline_allocation_evidence(
        pointer_path,
        evaluation_date=evaluation_date,
        resolvers=resolvers,
    )
    if evidence.source_fact:
        raise ValueError("Derived baseline allocation cannot enter decision layer as source fact")
    if (
        evidence.profitability_baseline_certified
        or evidence.full_baseline_certified
        or evidence.numeric_forecast_enabled
        or evidence.decision_score_enabled
    ):
        raise ValueError("Derived revenue allocation cannot widen decision/model gates")
    return BaselineAllocationDecisionEvidence(evidence=evidence)


def append_semiconductor_baseline_allocation_report(
    report: str,
    evidence: BaselineAllocationDecisionEvidence,
) -> str:
    item = evidence.evidence
    reconciliation = item.reconciliation
    required = ", ".join(reconciliation.required_revenue_blocks) or "-"
    allocated = ", ".join(reconciliation.allocated_revenue_blocks) or "-"
    missing = ", ".join(reconciliation.missing_revenue_blocks) or "-"
    lines = [
        report.rstrip(),
        "",
        "## Semiconductor Derived Revenue Allocation (파생매출·비점수)",
        "",
        (
            f"- evidence: `{item.evidence_id[:12]}` / resolver `{item.resolver_id}` / "
            f"evaluation `{item.evaluation_date.isoformat()}`"
        ),
        (
            "- 직접 공시 source fact를 대체하지 않습니다. 검증된 company revenue와 "
            "직접 근거가 있는 product share에 고정된 산술만 적용합니다."
        ),
        (
            "- revenue bridge가 reconcile되더라도 profitability/full baseline, numeric "
            "forecast, Expectation Gap, decision score는 자동으로 열리지 않습니다."
        ),
        "",
        "| 항목 | 상태/값 |",
        "|---|---|",
        f"| ticker | {reconciliation.ticker} |",
        f"| required revenue blocks | {required} |",
        f"| allocated revenue blocks | {allocated} |",
        f"| missing revenue blocks | {missing} |",
        f"| allocated revenue total | {reconciliation.allocated_revenue_total:.6g} |",
        f"| reported company revenue | {reconciliation.reported_company_revenue:.6g} |",
        f"| reconciliation delta | {reconciliation.reconciliation_delta:.6g} |",
        (
            "| revenue reconciliation certified | "
            f"{reconciliation.revenue_reconciliation_certified} |"
        ),
        f"| revenue model input ready | {reconciliation.revenue_model_input_ready} |",
        "| profitability baseline certified | False |",
        "| full baseline certified | False |",
        "| source fact | False |",
        "| numeric forecast / decision score | False / False |",
    ]
    return "\n".join(lines).rstrip() + "\n"


__all__ = [
    "BaselineAllocationDecisionEvidence",
    "DEFAULT_BASELINE_ALLOCATION_POINTER",
    "append_semiconductor_baseline_allocation_report",
    "load_semiconductor_baseline_allocation_decision_evidence",
]
